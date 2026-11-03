import copy
import importlib
import importlib.util
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
PLANTILLAS = AQUI.parent / "plantillas"
BARRIDO = AQUI.parent.parent / "tools" / "barrido.py"
NOMBRE = "Proyecto Ñandú & Cía"
SECCIONES_DEL_TICKET = (
    "- **Estado:**",
    "- **Conocimiento:**",
    "## Objetivo",
    "## Criterios de aceptación",
    "## Alcance y no-goals",
    "## Decisiones",
    "## Gotchas",
    "## Bitácora",
    "## Candidatos a graduar",
    "## Cierre",
)


def t():
    return importlib.import_module("bootstrap_textos")


def b():
    return importlib.import_module("bootstrap")


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def spec_de(nombre=NOMBRE):
    return {"spec_version": 1, "config": {"schema_version": 1, "repos": {"repo-a": {}}, "layers": {"capa-a": {"extensions": [".ext"], "repos": ["repo-a"]}}},
            "proyecto": {"nombre": nombre}}


def textos(nombre=NOMBRE):
    return dict(t().generar(spec_de(nombre)))


class Escenario:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="btextos-"))
        self.raiz = self.base / "instancia"
        return self

    def generar_instancia(self, previo=None):
        spec = spec_de()
        spec["local"] = {"repos": {"repo-a": {"path": str(self.base)}}}
        self.raiz.mkdir(exist_ok=True)
        for ruta, contenido in (previo or {}).items():
            destino = self.raiz / ruta
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido)
        copia = list(b().GENERADORES)
        try:
            propios = [g for g in copia if g.nombre == "config"]
            b().GENERADORES[:] = propios + [b().Generador("textos", t().generar, t().CLAVES, t().validar)]
            plan = b().planificar(spec, self.raiz)
            return b().aplicar(plan, self.raiz)
        finally:
            b().GENERADORES[:] = copia

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_forzar_borrado)


def invalida(spec, *fragmentos):
    try:
        t().validar(spec)
    except b().SpecInvalida as error:
        assert type(error) is b().SpecInvalida
        for fragmento in fragmentos:
            assert fragmento in str(error), (fragmento, str(error))
    else:
        assert False, f"debía fallar: {spec.get('proyecto')!r}"


def test_las_claves_de_la_spec_son_proyecto():
    assert t().CLAVES == ("proyecto",)


def test_genera_el_indice_y_la_plantilla_del_ticket_en_orden():
    assert [ruta for ruta, _ in t().generar(spec_de())] == ["CLAUDE.md", "tickets/_plantilla/CLAUDE.md"]


def test_validar_acepta_un_nombre_con_acentos_y_simbolos():
    assert t().validar(spec_de()) is None
    assert t().validar(spec_de("a")) is None


def test_validar_exige_proyecto_y_su_nombre():
    sin = spec_de()
    del sin["proyecto"]
    invalida(sin, "proyecto", "nombre")
    for malo in (None, "texto", [], 3):
        invalida({**spec_de(), "proyecto": malo}, "proyecto")
    invalida({**spec_de(), "proyecto": {}}, "proyecto.nombre")
    for nombre in (None, 3, [], "", "   ", " x", "x ", "a\nb", "a\tb", "a\x00b", "a\rb"):
        invalida(spec_de(nombre), "proyecto.nombre")


def test_validar_rechaza_claves_desconocidas_del_proyecto():
    spec = spec_de()
    spec["proyecto"]["otra"] = "x"
    invalida(spec, "proyecto", "otra")


def test_validar_no_modifica_la_spec():
    spec = spec_de()
    antes = copy.deepcopy(spec)
    t().validar(spec)
    t().generar(spec)
    assert spec == antes


def test_el_indice_lleva_el_nombre_y_no_deja_marcas_sin_reemplazar():
    texto = textos()["CLAUDE.md"]
    primera = texto.splitlines()[0]
    assert primera.startswith("# ") and NOMBRE in primera, primera
    assert "{{" not in texto and "}}" not in texto
    assert textos("{{tickets}}")["CLAUDE.md"].splitlines()[0].count("{{tickets}}") == 1


def test_el_indice_tiene_menos_de_200_lineas_segun_el_chequeo_de_conocimiento():
    import conocimiento

    texto = textos()["CLAUDE.md"]
    assert 60 < len(texto.splitlines()) < 200, len(texto.splitlines())
    with Escenario() as e:
        e.generar_instancia()
        assert conocimiento.chequear_tope_del_indice(conocimiento.contexto_de(e.raiz)) == []
        (e.raiz / "CLAUDE.md").write_text("x\n" * 201, encoding="utf-8")
        assert len(conocimiento.chequear_tope_del_indice(conocimiento.contexto_de(e.raiz))) == 1


def test_el_indice_trae_la_metodologia_generica():
    texto = textos()["CLAUDE.md"]
    for pedazo in (
        "se apilan",
        "tickets/_plantilla/CLAUDE.md",
        "tickets/**/",
        "no-goals",
        "Explorar",
        "Implementar",
        "Revisar",
        "Paso 0",
        "writer-<capa>",
        "revisor-<capa>",
        "criterios",
        "capa-<capa>",
        "commit",
        "git push -u origin",
        "git fetch",
        "worktree",
        "no es evidencia",
        "¿rápida o profunda?",
        "definitivo",
        "COMMIT",
        "git grep",
        "candidatos a graduar",
        "/odd-ws:doctor",
        "/odd-ws:conocimiento",
        "/odd-ws:eval-reviewers",
        "/odd-ws:bootstrap",
    ):
        assert pedazo in texto, pedazo


def test_el_indice_declara_la_carpeta_de_tickets_con_el_glob_recursivo():
    texto = textos()["CLAUDE.md"]
    assert "tickets/**/" in texto
    assert "`tickets/*`" not in texto and "tickets/<" in texto


def test_el_indice_no_trae_rutas_de_una_maquina_ni_links_a_sistemas_externos():
    texto = textos()["CLAUDE.md"] + textos()["tickets/_plantilla/CLAUDE.md"]
    for ajeno in ("http://", "https://", "C:\\", "C:/", "@"):
        assert ajeno not in texto, ajeno


def test_los_textos_no_traen_terminos_de_la_lista_negra_y_el_instrumento_sabe_decir_que_si():
    especificacion = importlib.util.spec_from_file_location("barrido_de_prueba", BARRIDO)
    barrido = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(barrido)
    lista = barrido.ruta_de_la_lista()
    if not lista.is_file():
        return
    terminos = barrido.cargar_lista(lista)
    assert barrido.buscar("hay " + terminos[0][0] + " aquí", terminos), "el barrido no ve su propio término"
    for ruta, texto in textos().items():
        assert barrido.buscar(texto, terminos) == [], ruta
    for plantilla in PLANTILLAS.glob("*.md"):
        assert barrido.buscar(plantilla.read_text(encoding="utf-8"), terminos) == [], plantilla.name


def test_la_plantilla_del_ticket_trae_todas_sus_secciones_en_orden():
    texto = textos()["tickets/_plantilla/CLAUDE.md"]
    posiciones = [texto.find(s) for s in SECCIONES_DEL_TICKET]
    assert all(p >= 0 for p in posiciones), [s for s, p in zip(SECCIONES_DEL_TICKET, posiciones) if p < 0]
    assert posiciones == sorted(posiciones)
    assert re.match(r"# ", texto)
    assert "../../CLAUDE.md" in texto


def test_la_plantilla_del_ticket_no_trae_tracker_ni_el_nombre_del_proyecto():
    texto = textos()["tickets/_plantilla/CLAUDE.md"]
    assert "{{" not in texto and NOMBRE not in texto
    assert "tracker" not in texto.lower() and "sprint" not in texto.lower()
    assert texto == (PLANTILLAS / "ticket.md").read_text(encoding="utf-8")


def test_el_vinculo_de_la_plantilla_llega_al_indice_desde_un_ticket():
    with Escenario() as e:
        e.generar_instancia()
        ticket = e.raiz / "tickets" / "T-1"
        ticket.mkdir()
        (ticket / "CLAUDE.md").write_bytes((e.raiz / "tickets" / "_plantilla" / "CLAUDE.md").read_bytes())
        assert (ticket / ".." / ".." / "CLAUDE.md").resolve() == (e.raiz / "CLAUDE.md").resolve()


def test_todo_sale_en_utf8_con_lf_sin_bom_y_salto_final():
    for ruta, texto in t().generar(spec_de()):
        assert isinstance(texto, str), ruta
        crudo = texto.encode("utf-8")
        assert b"\r" not in crudo and not crudo.startswith(b"\xef\xbb\xbf"), ruta
        assert crudo.endswith(b"\n") and not crudo.endswith(b"\n\n"), ruta


def test_las_plantillas_con_crlf_o_bom_salen_con_lf_sin_bom():
    with Escenario() as e:
        (e.base / "CLAUDE.md").write_bytes("\ufeff# {{nombre}}\r\nlínea\r\n".encode("utf-8"))
        (e.base / "ticket.md").write_bytes("\ufeff# T\r\nlínea\r\n".encode("utf-8"))
        anterior = t().PLANTILLAS
        t().PLANTILLAS = e.base
        try:
            salida = dict(t().generar(spec_de("X")))
        finally:
            t().PLANTILLAS = anterior
        assert salida["CLAUDE.md"] == "# X\nlínea\n"
        assert salida["tickets/_plantilla/CLAUDE.md"] == "# T\nlínea\n"


def test_las_plantillas_son_lf_sin_bom():
    for nombre in ("CLAUDE.md", "ticket.md"):
        crudo = (PLANTILLAS / nombre).read_bytes()
        assert b"\r" not in crudo and not crudo.startswith(b"\xef\xbb\xbf") and crudo.endswith(b"\n"), nombre


def test_la_instancia_generada_no_pisa_un_indice_existente():
    with Escenario() as e:
        resultados = e.generar_instancia({"CLAUDE.md": b"el mio\n"})
        assert (e.raiz / "CLAUDE.md").read_bytes() == b"el mio\n"
        assert {x.ruta: x.estado for x in resultados}["CLAUDE.md"] == "ya_existia"
        assert (e.raiz / "tickets" / "_plantilla" / "CLAUDE.md").is_file()


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
