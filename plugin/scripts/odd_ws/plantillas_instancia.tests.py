import sys

sys.dont_write_bytecode = True

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
