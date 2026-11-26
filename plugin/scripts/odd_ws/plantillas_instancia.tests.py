import sys

sys.dont_write_bytecode = True

import hashlib
import importlib
import json
import os
import shutil
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
PLUGIN = AQUI.parent.parent


def m():
    return importlib.import_module("odd_ws.plantillas_instancia")


def spec_de(perfil, nombre="Mi proyecto"):
    config = {"schema_version": 1, "layers": {"sql": {"extensions": [".sql"], "rule_prefix": "SQL"}, "web": {"extensions": [".ts"]}}}
    if perfil == "controles":
        config["profile"] = "controles"
    return {"proyecto": {"nombre": nombre}, "config": config}


def generado_por_el_bootstrap(spec):
    import bootstrap
    import bootstrap_instalacion
    import bootstrap_reglas
    import bootstrap_textos

    sys.modules.setdefault("bootstrap", bootstrap)
    archivos = {}
    for generar in (bootstrap_textos.generar, bootstrap_reglas.generar, bootstrap_instalacion.generar):
        for accion in generar(spec):
            if isinstance(accion, tuple) and not isinstance(accion, bootstrap.AccionDeGit):
                ruta, contenido = accion[0], accion[1]
                archivos[ruta] = contenido.encode("utf-8") if isinstance(contenido, str) else contenido
    return archivos


class Instancia:
    def __init__(self, config):
        self.config = config

    def __enter__(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="odd-plantillas-"))
        (self.raiz / "workspace.config.json").write_text(json.dumps(self.config), encoding="utf-8")
        return self.raiz

    def __exit__(self, *_):
        shutil.rmtree(self.raiz, ignore_errors=True)


def test_cada_copia_es_la_ruta_y_el_contenido_que_escribe_el_bootstrap():
    for perfil in ("completo", "controles"):
        spec = spec_de(perfil, nombre="Acme — sede 2")
        archivos = generado_por_el_bootstrap(spec)
        with Instancia(spec["config"]) as raiz:
            copias = m().copias(raiz)
        assert all(copia.ruta in archivos for copia in copias), (perfil, copias, sorted(archivos))
        esperadas = ["CLAUDE.md"] + ([] if perfil == "controles" else ["tickets/_plantilla/CLAUDE.md"]) + [
            ".githooks/pre-commit", ".claude/reglas/verificar_sql.tests.py", ".claude/reglas/verificar_web.tests.py"]
        assert [copia.ruta for copia in copias] == esperadas, (perfil, copias)
        for copia in copias:
            nuevo = m().contenido_nuevo(PLUGIN, copia.plantilla, "Acme — sede 2")
            assert nuevo == archivos[copia.ruta], (perfil, copia)


def test_lo_que_copia_el_bootstrap_sale_al_dia_con_las_plantillas_reales_del_plugin():
    for perfil in ("completo", "controles"):
        spec = spec_de(perfil)
        with Instancia(spec["config"]) as raiz:
            for ruta, contenido in generado_por_el_bootstrap(spec).items():
                destino = raiz / ruta
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(contenido)
            revision = m().revisar(raiz, PLUGIN)
        assert revision.error is None and revision.rota is None, revision
        assert revision.pendientes == () and revision.anotada is None, revision


def tabla_real():
    return json.loads((PLUGIN / "plantillas" / "huellas.json").read_text(encoding="utf-8"))


def copiar(raiz, archivos):
    for ruta, contenido in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido.encode("utf-8") if isinstance(contenido, str) else contenido)


def de_la_version(plantilla, version, nombre="Mi proyecto"):
    texto = m().texto_del_historial(PLUGIN, tabla_real()[plantilla][version])
    assert texto is not None, (plantilla, version)
    return m().renderizar(plantilla, texto, nombre)


def test_cada_huella_de_la_tabla_del_plugin_tiene_en_el_historial_su_texto_en_su_forma():
    for plantilla, versiones in tabla_real().items():
        for version, huella in versiones.items():
            texto = m().texto_del_historial(PLUGIN, huella)
            assert texto is not None, (plantilla, version, huella)
            crudo = (PLUGIN / "plantillas" / "historial" / huella[len("sha256:"):]).read_bytes()
            assert "sha256:" + hashlib.sha256(crudo).hexdigest() == huella, (plantilla, version)
            assert b"\r" not in crudo and not crudo.startswith(m().BOM), (plantilla, version)
            if plantilla in m().INDICES:
                assert m().MARCA_NOMBRE in texto and m().MARCA_TICKETS not in texto, (plantilla, version)


def test_el_historial_no_da_un_texto_que_falta_o_que_no_da_la_huella_de_su_nombre():
    texto = "# {{nombre}}\nuno\n"
    huella = m().huella(texto.encode("utf-8"))
    with Instancia({}) as plugin:
        assert m().texto_del_historial(plugin, huella) is None, "sin el archivo"
        copiar(plugin, {f"plantillas/historial/{huella[len('sha256:'):]}": "# {{nombre}}\ndos\n"})
        assert m().texto_del_historial(plugin, huella) is None, "con otro texto"
        copiar(plugin, {f"plantillas/historial/{huella[len('sha256:'):]}": m().BOM + texto.replace("\n", "\r\n").encode("utf-8")})
        assert m().texto_del_historial(plugin, huella) == texto, "el BOM y los CRLF de un checkout no lo rompen"


def test_el_texto_de_la_huella_es_la_forma_que_da_la_huella_de_la_plantilla():
    crudo = m().BOM + "# {{nombre}}\r\n`{{tickets}}/`\r\n".encode("utf-8")
    for plantilla in m().PLANTILLAS:
        forma = m().texto_de_la_huella(plantilla, crudo)
        assert "sha256:" + hashlib.sha256(forma).hexdigest() == m().huella_de_la_plantilla(plantilla, crudo), plantilla
    assert m().texto_de_la_huella("CLAUDE.md", crudo) == b"# {{nombre}}\n`tickets/`\n"
    assert m().texto_de_la_huella("CLAUDE.controles.md", crudo) == b"# {{nombre}}\n`{{tickets}}/`\n"


def test_una_copia_sin_tocar_se_reconoce_aunque_el_nombre_del_proyecto_salga_en_el_texto_de_la_plantilla():
    spec = spec_de("completo", nombre="tickets")
    with Instancia(spec["config"]) as raiz:
        copiar(raiz, generado_por_el_bootstrap(spec))
        revision = m().revisar(raiz, PLUGIN)
        assert revision.error is None and revision.pendientes == (), revision
        indice = next(r for r in revision.revisadas if r.ruta == "CLAUDE.md")
        assert indice.estado == m().AL_DIA and indice.nombre == "tickets", indice
        copiar(raiz, {"CLAUDE.md": de_la_version("CLAUDE.md", "0.9.0", "tickets")})
        indice = next(r for r in m().revisar(raiz, PLUGIN).revisadas if r.ruta == "CLAUDE.md")
        assert indice.estado == m().SIN_TOCAR and indice.versiones == ("0.9.0", "0.9.1") and indice.nombre == "tickets", indice


def test_sin_la_clave_la_revision_dice_hasta_que_version_coinciden_las_copias_y_sigue_desde_la_menor():
    spec = spec_de("completo")
    with Instancia(spec["config"]) as raiz:
        copiar(raiz, generado_por_el_bootstrap(spec))
        copiar(raiz, {"CLAUDE.md": de_la_version("CLAUDE.md", "0.9.0"),
                      "tickets/_plantilla/CLAUDE.md": de_la_version("ticket.md", "0.9.0"),
                      ".githooks/pre-commit": de_la_version("pre-commit", "0.9.0"),
                      ".claude/reglas/verificar_sql.tests.py": de_la_version("reglas/verificar.tests.py", "0.9.0"),
                      ".claude/reglas/verificar_web.tests.py": de_la_version("reglas/verificar.tests.py", "0.9.0")})
        revision = m().revisar(raiz, PLUGIN)
        assert (revision.inferida, revision.base, revision.hasta) == ("0.9.0", "0.9.0", "0.9.1"), revision
        config = json.loads((raiz / "workspace.config.json").read_text(encoding="utf-8"))
        (raiz / "workspace.config.json").write_text(json.dumps({**config, "plantillas": "0.9.0"}), encoding="utf-8")
        revision = m().revisar(raiz, PLUGIN)
        assert (revision.anotada, revision.inferida, revision.base, revision.hasta) == ("0.9.0", None, "0.9.0", None), revision


def test_una_copia_que_es_un_enlace_cuenta_como_editada_y_no_se_reemplaza():
    spec = spec_de("completo")
    with Instancia(spec["config"]) as raiz:
        afuera = raiz.parent / (raiz.name + "-afuera")
        afuera.mkdir()
        try:
            for ruta, contenido in generado_por_el_bootstrap(spec).items():
                destino = raiz / ruta
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(contenido)
            original = (raiz / ".githooks" / "pre-commit").read_bytes()
            (afuera / "pre-commit").write_bytes(original)
            (raiz / ".githooks" / "pre-commit").unlink()
            try:
                os.symlink(afuera / "pre-commit", raiz / ".githooks" / "pre-commit")
            except OSError:
                print("      (sin permiso para crear enlaces: prueba omitida)")
                return
            config = json.loads((raiz / "workspace.config.json").read_text(encoding="utf-8"))
            (raiz / "workspace.config.json").write_text(json.dumps({**config, "plantillas": "0.2.0"}), encoding="utf-8")
            revision = m().revisar(raiz, PLUGIN)
            enlazada = [r for r in revision.pendientes if r.ruta == ".githooks/pre-commit"]
            assert enlazada and enlazada[0].estado == m().EDITADA, revision.pendientes
            m().reemplazar(raiz, PLUGIN)
            assert (afuera / "pre-commit").read_bytes() == original
        finally:
            shutil.rmtree(afuera, ignore_errors=True)


def test_la_huella_no_ve_el_bom_ni_los_crlf_y_solo_el_claude_md_raiz_completo_renderiza_tickets():
    texto = b"# {{nombre}}\n`{{tickets}}/`\n"
    assert m().huella(b"\xef\xbb\xbf" + texto.replace(b"\n", b"\r\n")) == m().huella(texto)
    assert m().huella(texto).startswith("sha256:") and len(m().huella(texto)) == len("sha256:") + 64
    assert m().huella_de_la_plantilla("CLAUDE.md", texto) == m().huella(b"# {{nombre}}\n`tickets/`\n")
    for plantilla in ("CLAUDE.controles.md", "ticket.md", "pre-commit", "reglas/verificar.tests.py"):
        assert m().huella_de_la_plantilla(plantilla, texto) == m().huella(texto), plantilla


def test_las_versiones_se_ordenan_por_numero_y_la_previa_va_antes():
    versiones = ["0.10.0", "0.2.0", "0.13.3", "0.9.1", "0.14.0", "0.14.0-rc.1"]
    assert sorted(versiones, key=m().orden) == ["0.2.0", "0.9.1", "0.10.0", "0.13.3", "0.14.0-rc.1", "0.14.0"]


def test_anotar_la_version_cambia_solo_esa_linea_de_la_config():
    base = {"schema_version": 1, "layers": {"sql": {"extensions": [".sql"]}}}
    casos = [
        (json.dumps(base, indent=2) + "\n", json.dumps({**base, "plantillas": "0.14.0"}, indent=2) + "\n"),
        (json.dumps({**base, "plantillas": "0.9.1"}, indent=4).replace("\n", "\r\n") + "\r\n",
         json.dumps({**base, "plantillas": "0.14.0"}, indent=4).replace("\n", "\r\n") + "\r\n"),
        (json.dumps(base), json.dumps(base)[:-1] + ',\n  "plantillas": "0.14.0"\n}'),
    ]
    anidada = {"schema_version": 1, "layers": {"sql": {"extensions": [".sql"], "plantillas": "propia"}}}
    casos.append((json.dumps(anidada, indent=2) + "\n", json.dumps({**anidada, "plantillas": "0.14.0"}, indent=2) + "\n"))
    for previo, esperado in casos:
        for bom in (b"", b"\xef\xbb\xbf"):
            with Instancia({}) as raiz:
                (raiz / "workspace.config.json").write_bytes(bom + previo.encode("utf-8"))
                m().anotar_version(raiz, "0.14.0")
                assert (raiz / "workspace.config.json").read_bytes() == bom + esperado.encode("utf-8"), (previo, bom)


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    pruebas = [(nombre, funcion) for nombre, funcion in globals().items() if nombre.startswith("test_") and callable(funcion)]
    fallas = 0
    for nombre, prueba in pruebas:
        try:
            prueba()
            print(f"ok    {nombre}")
        except AssertionError as error:
            fallas += 1
            print(f"FALLA {nombre}: {error}")
        except Exception as error:
            fallas += 1
            print(f"ERROR {nombre}: {type(error).__name__}: {error}")
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
