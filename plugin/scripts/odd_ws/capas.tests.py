import importlib
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))


def m():
    return importlib.import_module("odd_ws.capas")


def solo_texto(lineas):
    return [l for l in lineas if l.strip()]


def test_partir_bloque_completo():
    ls = ["antes", "<!-- no-negociables -->", "dentro 1", "dentro 2", "<!-- /no-negociables -->", "despues"]
    dentro, fuera, estado = m().partir_bloque(ls)
    assert estado == "ok"
    assert solo_texto(dentro) == ["dentro 1", "dentro 2"]
    assert solo_texto(fuera) == ["antes", "despues"]
    assert not any("no-negociables" in l for l in dentro + fuera), "los marcadores no son de ninguna zona"
    assert fuera == ["antes", "", "despues"], "el bloque deja un blanco en fuera para que un segmento no lo cruce"
    assert dentro == ["dentro 1", "dentro 2", ""]


def test_partir_bloque_ausente():
    dentro, fuera, estado = m().partir_bloque(["a", "b"])
    assert (dentro, fuera, estado) == ([], ["a", "b"], "ausente")


def test_partir_bloque_abierto_no_cuenta_como_dentro():
    dentro, fuera, estado = m().partir_bloque(["a", "  <!-- no-negociables -->  ", "b"])
    assert (dentro, solo_texto(fuera), estado) == ([], ["a"], "abierto")


def test_partir_bloque_abierto_despues_de_uno_cerrado_conserva_el_cerrado():
    dentro, fuera, estado = m().partir_bloque(
        ["<!-- no-negociables -->", "x", "<!-- /no-negociables -->", "<!-- no-negociables -->", "y"])
    assert (solo_texto(dentro), estado) == (["x"], "abierto")


def test_partir_bloque_dos_bloques_se_suman():
    dentro, fuera, estado = m().partir_bloque(
        ["<!-- no-negociables -->", "x", "<!-- /no-negociables -->", "y",
         "<!-- no-negociables -->", "z", "<!-- /no-negociables -->"])
    assert (solo_texto(dentro), solo_texto(fuera), estado) == (["x", "z"], ["y"], "ok")


def test_partir_bloque_el_marcador_ocupa_la_linea_entera():
    assert m().partir_bloque(["a <!-- no-negociables --> b", "c"])[2] == "ausente"


def test_partir_bloque_cierre_suelto_queda_fuera():
    dentro, fuera, estado = m().partir_bloque(["<!-- /no-negociables -->", "a"])
    assert (dentro, fuera, estado) == ([], ["<!-- /no-negociables -->", "a"], "ausente")


def test_rutas_de_la_convencion():
    assert m().chequeo("sql") == ".claude/reglas/verificar_sql.py"
    assert m().prueba("sql") == ".claude/reglas/verificar_sql.tests.py"
    assert m().skill("sql") == ".claude/skills/capa-sql/SKILL.md"
    assert m().revisor("sql") == ".claude/agents/revisor-sql.md"
    assert m().writer("sql") == ".claude/agents/writer-sql.md"
    assert m().REVISOR_DISENO == ".claude/agents/revisor-diseno.md"
    assert m().REVISOR_DISENO.startswith(m().AGENTES + "/")
    assert m().agente("writer-sql") == ".claude/agents/writer-sql.md"
    assert m().PRIMER_TOQUE == ".claude/estado/primer-toque"
    assert m().ESTADO_WRITERS == ".claude/estado/writers"
    assert m().CRITERIOS_SKILL == ".claude/skills/criterios/SKILL.md"
    assert m().CRITERIOS_REFS == ".claude/skills/criterios/references/"
    assert m().EVIDENCIA == ".claude/reglas/evidencia.md"
    assert m().MATRIZ == ".claude/reglas/matriz.csv"
    assert m().SENALES == ".claude/reglas/senales.py"


def test_las_rutas_son_relativas_y_con_barra():
    for ruta in (m().chequeo("x"), m().prueba("x"), m().skill("x"), m().revisor("x"), m().writer("x"), m().agente("x"), m().CRITERIOS_SKILL, m().REVISOR_DISENO,
                 m().CRITERIOS_REFS, m().EVIDENCIA, m().MATRIZ, m().PRIMER_TOQUE, m().ESTADO_WRITERS, m().SENALES):
        assert not ruta.startswith("/") and "\\" not in ruta and ":" not in ruta, ruta


def test_carpetas_de_la_verdad_de_terreno_y_de_lo_oculto():
    assert m().CARPETA_VERDAD == "revision"
    assert m().CARPETA_OCULTA == "oculto"
    for nombre in (m().CARPETA_VERDAD, m().CARPETA_OCULTA):
        assert nombre and not any(c in nombre for c in "/\\:."), nombre


def test_rutas_de_la_instancia_para_el_bootstrap():
    assert m().ESTADO == ".claude/estado"
    assert m().GITIGNORE == ".gitignore"
    assert m().PRIMER_TOQUE.startswith(m().ESTADO + "/")
    assert m().ESTADO_WRITERS.startswith(m().ESTADO + "/")


def test_rutas_de_los_textos_del_bootstrap():
    import config_loader

    assert m().TICKETS == "tickets"
    assert m().INDICE == "CLAUDE.md"
    assert m().TICKET_PLANTILLA == "tickets/_plantilla/CLAUDE.md"
    assert m().INDICE == config_loader.INDICE_POR_DEFECTO
    assert m().TICKET_PLANTILLA.startswith(m().TICKETS + "/")
    for ruta in (m().TICKETS, m().INDICE, m().TICKET_PLANTILLA):
        assert not ruta.startswith("/") and "\\" not in ruta and ":" not in ruta, ruta


def test_rutas_de_la_plantilla_del_ticket():
    assert m().TICKET_PLANTILLA_DIR == "tickets/_plantilla"
    assert m().TICKET_SETTINGS == "tickets/_plantilla/.claude/settings.json"
    assert m().TICKET_PLANTILLA_DIR.startswith(m().TICKETS + "/")
    assert m().TICKET_PLANTILLA == m().TICKET_PLANTILLA_DIR + "/CLAUDE.md"
    assert m().TICKET_SETTINGS.startswith(m().TICKET_PLANTILLA_DIR + "/")
    for ruta in (m().TICKET_PLANTILLA_DIR, m().TICKET_SETTINGS):
        assert not ruta.startswith("/") and "\\" not in ruta and ":" not in ruta, ruta


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
