import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLUGIN = AQUI.parent
sys.path.insert(0, str(AQUI))

import verificar_capa  # noqa: E402
import writer_stop  # noqa: E402
from odd_ws import capas as convencion  # noqa: E402

CAPAS = ("sql", "web", "movil")
BLOQUES = ("identidad", "limites", "verificacion")
HUELLAS_POR_VERSION = {1: "e20a7bdca2eba9d355a04ebd6faca3758fad17b686b3477933c5be7fc89a8eb3"}
DESCRIPCION_RARA = 'Capa "rara": C:\\ruta\\x, # no es comentario, ## Verification y ñ al final'


def p():
    return importlib.import_module("plantilla_writer")


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Instancia:
    def __enter__(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="plantilla-writer-"))
        return self

    def ruta(self, capa):
        return self.raiz / convencion.writer(capa)

    def poner(self, capa, texto, crlf=False, bom=False):
        ruta = self.ruta(capa)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = (texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8")
        ruta.write_bytes((b"\xef\xbb\xbf" if bom else b"") + datos)
        return ruta

    def __exit__(self, *_):
        shutil.rmtree(self.raiz, onexc=_forzar_borrado)


def frontmatter(texto):
    return texto.split("\n---\n", 1)[0]


def descripcion(texto):
    linea = next(l for l in frontmatter(texto).splitlines() if l.startswith("description:"))
    return linea, json.loads(linea.split(":", 1)[1].strip())


def bloque(texto, nombre):
    m = re.search(r"<!-- instancia:%s -->\n(.*?)<!-- /instancia:%s -->" % (nombre, nombre), texto, re.S)
    assert m, "falta el bloque %s" % nombre
    return m.group(1)


def con_bloque(texto, nombre, interior):
    return re.sub(r"(<!-- instancia:%s -->\n).*?(<!-- /instancia:%s -->)" % (nombre, nombre),
                  lambda m: m.group(1) + interior + m.group(2), texto, count=1, flags=re.S)


def con_descripcion(texto, valor):
    return re.sub(r"(?m)^description:.*$", lambda _m: "description: " + valor, texto, count=1)


def plantilla_vieja():
    texto = p().leer_plantilla()
    sin_limites = re.sub(r"<!-- instancia:limites -->\n.*?<!-- /instancia:limites -->\n", "", texto, count=1, flags=re.S)
    assert sin_limites != texto, "la plantilla tiene el bloque limites"
    return re.sub(r"(?m)^odd-ws-plantilla: \d+$", "odd-ws-plantilla: 0", sin_limites, count=1)


def test_los_writers_generados_citan_la_plantilla_tal_cual():
    for capa in CAPAS:
        generado = p().generar(capa)
        assert writer_stop.PLANTILLA in generado, capa
        propio = con_bloque(con_bloque(generado, "identidad", "Otra identidad.\n"), "verificacion", "- `x --check`\n")
        assert writer_stop.PLANTILLA in p().generar(capa, propio), capa


def test_la_plantilla_de_writer_no_guarda_una_copia_del_cierre():
    texto = (PLUGIN / "plantillas" / "writer.md").read_text(encoding="utf-8")
    assert "{{resultado}}" in texto, "la plantilla inserta el cierre de writer_stop"
    assert "estado: ok | partial | blocked" not in texto, "sin copia de la PLANTILLA: una sola fuente"


def test_b3_la_description_va_entre_comillas_y_completa():
    colas = set()
    for capa in CAPAS:
        linea, valor = descripcion(p().generar(capa))
        assert re.fullmatch(r'description: "((?:[^"\\]|\\.)*)"', linea), linea
        assert valor.rstrip(".").endswith("## Resultado"), valor
        assert "## Verification" in valor, valor
        assert capa in valor.partition(" cuando el cambio ")[0], valor
        colas.add(valor.partition(" cuando el cambio ")[2])
    assert len(colas) == 1 and "" not in colas, colas


def test_b3_la_description_de_la_instancia_vuelve_entre_comillas_y_sin_perder_nada():
    base = p().generar("sql")
    for escrita in (json.dumps(DESCRIPCION_RARA, ensure_ascii=False), "'Capa ''sql'' de la instancia'", "Capa sql # sin comillas"):
        regenerado = p().generar("sql", con_descripcion(base, escrita))
        linea, valor = descripcion(regenerado)
        assert re.fullmatch(r'description: "((?:[^"\\]|\\.)*)"', linea), linea
        esperado = {"'": "Capa 'sql' de la instancia", "C": "Capa sql # sin comillas"}.get(escrita[0], DESCRIPCION_RARA)
        assert valor == esperado, (escrita, valor)
        assert len(frontmatter(regenerado).splitlines()) == len(frontmatter(base).splitlines()), "una sola línea"


def test_s21_el_frontmatter_no_cablea_hooks_ni_fija_el_modelo():
    for capa in CAPAS:
        cabecera = frontmatter(p().generar(capa))
        for prohibido in ("hooks:", "model:", "writer-guard", "writer-stop", "writer_guard", "writer_stop"):
            assert prohibido not in cabecera, (capa, prohibido)


def test_el_frontmatter_nombra_al_writer_y_precarga_criterios_y_su_capa():
    for capa in CAPAS:
        generado = p().generar(capa)
        cabecera = frontmatter(generado).splitlines()
        assert cabecera[0] == "---" and "name: writer-%s" % capa in cabecera, cabecera
        assert convencion.es_writer("writer-%s" % capa)
        assert "tools: Read, Glob, Grep, Edit, Write, Bash" in cabecera, cabecera
        assert verificar_capa.skills_del_frontmatter(generado) == ["criterios", "capa-%s" % capa]


def test_la_version_sale_de_la_plantilla_y_va_en_el_frontmatter():
    version = p().version()
    assert isinstance(version, int) and version >= 1, version
    assert "odd-ws-plantilla: %d" % version in frontmatter(p().generar("sql")).splitlines()
    assert p().version(plantilla_vieja()) == 0


def test_cambiar_lo_generado_obliga_a_subir_la_version():
    version = p().version()
    huella = hashlib.sha256(p().generar("x").encode("utf-8")).hexdigest()
    if version not in HUELLAS_POR_VERSION:
        raise AssertionError("anotá %d: %r en HUELLAS_POR_VERSION" % (version, huella))
    assert HUELLAS_POR_VERSION[version] == huella, (
        "lo generado cambió: subí odd-ws-plantilla en plugin/plantillas/writer.md y anotá %d: %r en HUELLAS_POR_VERSION"
        % (version + 1, huella))


def test_los_bloques_por_defecto_nombran_la_capa_y_los_demas_arrancan_vacios():
    generado = p().generar("web")
    for nombre in BLOQUES:
        bloque(generado, nombre)
    assert "web" in bloque(generado, "identidad")
    assert bloque(generado, "limites") == "" and bloque(generado, "verificacion") == ""
    propio = p().generar("web", con_bloque(generado, "verificacion", "- `npm test`\n"))
    assert "<!-- /instancia:verificacion -->\n- Lo que el brief ponga en `## Verification`, literal." in propio


def test_regenerar_conserva_los_bloques_y_la_description_y_es_idempotente():
    base = p().generar("sql")
    propio = con_descripcion(base, json.dumps(DESCRIPCION_RARA, ensure_ascii=False))
    interiores = {"identidad": "Eres el writer de {{capa}} literal.\n\nSegundo párrafo.\n",
                  "limites": "- Sin comentarios en el código.\n",
                  "verificacion": "- `python normalizar.py --check <archivos>`\n"}
    for nombre, interior in interiores.items():
        propio = con_bloque(propio, nombre, interior)
    regenerado = p().generar("sql", propio)
    for nombre, interior in interiores.items():
        assert bloque(regenerado, nombre) == interior, nombre
    assert descripcion(regenerado)[1] == DESCRIPCION_RARA
    assert p().generar("sql", regenerado) == regenerado
    assert p().generar("sql", p().generar("sql")) == p().generar("sql")


def test_un_bloque_que_falta_sale_con_el_texto_por_defecto():
    viejo = p().generar("sql", plantilla=plantilla_vieja())
    assert "instancia:limites" not in viejo
    viejo = con_bloque(viejo, "identidad", "Identidad de la instancia.\n")
    nuevo = p().generar("sql", viejo)
    assert bloque(nuevo, "limites") == bloque(p().generar("sql"), "limites")
    assert bloque(nuevo, "identidad") == "Identidad de la instancia.\n"
    assert "odd-ws-plantilla: %d" % p().version() in nuevo


def test_la_huella_no_cambia_con_bloques_description_crlf_ni_bom():
    base = p().generar("sql")
    huella = p().huella(base)
    assert re.fullmatch(r"[0-9a-f]{64}", huella or ""), huella
    assert "odd-ws-hash: %s" % huella in frontmatter(base).splitlines()
    variantes = [con_bloque(base, "identidad", "otra cosa\n"), con_bloque(base, "limites", "- uno\n- dos\n"),
                 con_descripcion(base, '"otra description"'), base.replace("\n", "\r\n"), "\ufeff" + base]
    for variante in variantes:
        assert p().huella(variante) == huella, variante[:80]


def test_la_huella_cambia_con_cualquier_edicion_fuera_de_los_bloques():
    base = p().generar("sql")
    huella = p().huella(base)
    ediciones = {
        "cuerpo": base.replace("Nunca reviertas", "Puedes revertir", 1),
        "tools": base.replace("tools: Read,", "tools: Read, PowerShell,", 1),
        "version": re.sub(r"(?m)^odd-ws-plantilla: \d+$", "odd-ws-plantilla: 99", base),
        "skills": base.replace("  - criterios\n", "  - otra\n", 1),
        "linea nueva": base.replace("\n---\n", "\n---\n\nTexto suelto.\n", 1),
        "bloque nuevo": base.replace("## Tus límites", "<!-- instancia:extra -->\nx\n<!-- /instancia:extra -->\n## Tus límites", 1),
    }
    for nombre, editado in ediciones.items():
        assert editado != base, nombre
        assert p().huella(editado) not in (None, huella), nombre
    sin_hash = re.sub(r"(?m)^odd-ws-hash: .*$", "odd-ws-hash: " + "0" * 64, base)
    assert p().huella(sin_hash) == huella, "la huella no cubre su propio valor"


def test_bloques_mal_formados_no_tienen_huella():
    base = p().generar("sql")
    malos = {
        "sin cerrar hasta el final": base.replace("<!-- /instancia:verificacion -->\n", "", 1),
        "abierto antes de otro": base.replace("<!-- /instancia:identidad -->\n", "", 1),
        "cierre suelto": base.replace("<!-- instancia:identidad -->\n", "", 1),
        "anidado": con_bloque(base, "identidad", "<!-- instancia:limites -->\nx\n<!-- /instancia:limites -->\n"),
        "cruzado": base.replace("<!-- /instancia:identidad -->", "<!-- /instancia:otro -->", 1),
        "repetido": base.replace("## Tus límites", "<!-- instancia:identidad -->\nx\n<!-- /instancia:identidad -->\n## Tus límites", 1),
    }
    for nombre, texto in malos.items():
        assert p().huella(texto) is None, nombre


def test_generar_rechaza_una_capa_que_no_cumple_writer_re():
    for capa in ("SQL", "c_sharp", "-web", "", "a/b"):
        try:
            p().generar(capa)
        except ValueError:
            continue
        raise AssertionError("generó writer-%s" % capa)


def test_el_cierre_no_trae_convenciones_del_harness():
    generado = p().generar("sql")
    assert "Key Learnings" not in generado
    assert "{{" not in generado and "}}" not in generado, re.findall(r"\{\{\w+\}\}", generado)


def test_revisar_reconoce_cada_estado():
    with Instancia() as i:
        assert p().revisar(i.raiz, "sql").codigo == "falta"
        assert p().revisar(i.raiz, "SQL").codigo == "nombre"
        i.poner("sql", p().generar("sql"))
        revision = p().revisar(i.raiz, "sql")
        assert revision.codigo == "ok" and revision.version == p().version(), revision
        i.poner("sql", p().generar("sql"), crlf=True, bom=True)
        assert p().revisar(i.raiz, "sql").codigo == "ok", "un checkout con CRLF y BOM no es una edición"
        i.poner("sql", con_bloque(p().generar("sql"), "limites", "- propio\n"))
        assert p().revisar(i.raiz, "sql").codigo == "ok"
        i.poner("sql", p().generar("sql", plantilla=plantilla_vieja()))
        revision = p().revisar(i.raiz, "sql")
        assert revision.codigo == "atrasado" and revision.version == 0, revision
        i.poner("sql", con_descripcion(p().generar("sql"), "sin comillas # y con almohadilla"))
        assert p().revisar(i.raiz, "sql").codigo == "atrasado", "regenerarlo lo cambiaría"
        i.poner("sql", p().generar("sql").replace("Nunca reviertas", "Revierte", 1))
        assert p().revisar(i.raiz, "sql").codigo == "editado"
        i.poner("sql", p().generar("sql").replace("<!-- /instancia:limites -->\n", "", 1))
        assert p().revisar(i.raiz, "sql").codigo == "malformado"
        i.poner("sql", "---\nname: writer-sql\ndescription: \"a mano\"\n---\nEscrito a mano.\n")
        assert p().revisar(i.raiz, "sql").codigo == "ajeno"
        i.poner("sql", re.sub(r"(?m)^odd-ws-hash: .*\n", "", p().generar("sql")))
        assert p().revisar(i.raiz, "sql").codigo == "ajeno", "con la versión y sin el hash"
        i.poner("sql", re.sub(r"(?m)^odd-ws-plantilla: \d+$", "odd-ws-plantilla: uno", p().generar("sql")))
        assert p().revisar(i.raiz, "sql").codigo == "ajeno", "con el hash y sin una versión entera"
        i.ruta("sql").write_bytes(b"---\nname: writer-sql\n\xff\xfe\n---\n")
        assert p().revisar(i.raiz, "sql").codigo == "ilegible"


def test_escribir_crea_con_lf_sin_bom_y_regenera_conservando_los_bloques():
    with Instancia() as i:
        ruta = p().escribir(i.raiz, "sql")
        crudo = ruta.read_bytes()
        assert ruta == i.ruta("sql") and not crudo.startswith(b"\xef\xbb\xbf") and b"\r\n" not in crudo
        assert crudo.decode("utf-8") == p().generar("sql")
        viejo = con_bloque(p().generar("sql", plantilla=plantilla_vieja()), "identidad", "Mía.\n")
        i.poner("sql", viejo, crlf=True)
        p().escribir(i.raiz, "sql")
        nuevo = i.ruta("sql").read_bytes().decode("utf-8")
        assert bloque(nuevo, "identidad") == "Mía.\n" and "instancia:limites" in nuevo and "\r" not in nuevo
        assert p().revisar(i.raiz, "sql").codigo == "ok"


def test_escribir_nunca_pisa_un_writer_editado_o_ajeno():
    with Instancia() as i:
        for texto in (p().generar("sql").replace("Nunca reviertas", "Revierte", 1), "---\nname: writer-sql\n---\nA mano.\n"):
            ruta = i.poner("sql", texto)
            try:
                p().escribir(i.raiz, "sql")
            except ValueError:
                pass
            else:
                raise AssertionError("pisó un writer %s" % p().revisar(i.raiz, "sql").codigo)
            assert ruta.read_bytes() == texto.encode("utf-8")


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
