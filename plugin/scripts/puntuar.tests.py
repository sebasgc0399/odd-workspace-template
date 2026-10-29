import contextlib
import datetime
import importlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
SCRIPT = AQUI / "puntuar.py"

REPORTE_BASE = """# Puntaje: sintético

Ratificado por: nadie todavía (puntaje del orquestador, sin ratificar)

Fuera del puntaje (verdad de terreno disputada con evidencia): O5

## Corridas

| Corrida | ok | parcial | contra | puntaje | derivado | contaminado |
|---|---|---|---|---|---|---|
| a-1 | 1 | 1 | 1 | 1,5 | 1 | 0 |
| a-2 | 2 | 0 | 0 | 2,0 | 0 | 0 |
| b-1 | 1 | 1 | 0 | 1,5 | 0 | 1 |

puntaje = ok + 0,5 x parcial; contra = reves + elogio; derivado y contaminado no cuentan.

"""

REPORTE_BRAZOS = REPORTE_BASE + """## Brazos

| Brazo | Corridas | Media | Unión | Puntaje unión | Estables | Conflictos |
|---|---|---|---|---|---|---|
| a | 2 | 1,75 | 2 ok, 1 parcial, 0 contra | 2,5 | O1 | O3 |
| b | 1 | 1,5 | 1 ok, 1 parcial, 0 contra | 1,5 | — | — |

### Brazo a (2 corridas)

| Corrida | ok | parcial | contra | puntaje |
|---|---|---|---|---|
| a-1 | 1 | 1 | 1 | 1,5 |
| a-2 | 2 | 0 | 0 | 2,0 |
| **Unión** | 2 | 1 | 0 | 2,5 |

- Media por corrida: 1,75
- Estables (ok en 2/2): O1
- Conflictos (una corrida acierta y otra va en contra; decide el líder o se revisa a mano):
  - O3: a-1 reves / a-2 ok

k/N de ok por observación (solo las que alguna corrida tocó):

| Obs | ok k/N | Unión | Veredicto por corrida (en el orden de la tabla) |
|---|---|---|---|
| O1 | 2/2 | ok | ok / ok |
| O2 | 0/2 | parcial | parcial / - |
| O3 | 1/2 | ok | reves / ok |
| O4 | 0/2 | derivado | derivado / - |

### Brazo b (1 corrida)

| Corrida | ok | parcial | contra | puntaje |
|---|---|---|---|---|
| b-1 | 1 | 1 | 0 | 1,5 |
| **Unión** | 1 | 1 | 0 | 1,5 |

- Media por corrida: 1,5
- Estables: no aplica con una sola corrida
- Conflictos: ninguno

k/N de ok por observación (solo las que alguna corrida tocó):

| Obs | ok k/N | Unión | Veredicto por corrida (en el orden de la tabla) |
|---|---|---|---|
| O1 | 0/1 | parcial | parcial |
| O2 | 1/1 | ok | ok |
| O10 | 0/1 | contaminado | contaminado |

## Tabla pareada por observación

| Obs | a ok k/N | a unión | b ok k/N | b unión |
|---|---|---|---|---|
| O1 | 2/2 | ok | 0/1 | parcial |
| O2 | 0/2 | parcial | 1/1 | ok |
| O3 | 1/2 | ok | 0/1 | — |
| O4 | 0/2 | derivado | 0/1 | — |
| O10 | 0/2 | — | 0/1 | contaminado |

Solo cuenta como mejora un acierto que cita el mecanismo nuevo; la tabla atribuye, no concluye.

"""


def p():
    return importlib.import_module("puntuar")


def base():
    return {
        "fixture": "sintético",
        "escala": {"ok": "acierto", "-": "no lo toca"},
        "ratificado_por": None,
        "corridas": {
            "a-1": {"O1": "ok", "O2": "parcial", "O3": "reves", "O4": "derivado", "O5": "elogio"},
            "a-2": {"O1": "ok", "O2": "-", "O3": "ok", "O5": "elogio"},
            "b-1": {"O1": "parcial", "O2": "ok", "O3": "-", "O10": "contaminado"},
        },
        "observaciones": ["O1", "O2", "O3", "O4", "O5", "O10"],
        "citas": {"a-1": {"O1": "cita de a-1 con | barra"}},
        "descripciones": {"O1": "primera observación"},
        "disputadas": {"O5": "contraejemplo verificado"},
    }


def sintetico():
    return {
        "fixture": "sintetico",
        "escala": {"ok": "x"},
        "ratificado_por": None,
        "corridas": {
            "v1-r1": {"A1": "ok", "A2": "ok", "A3": "elogio", "A4": "parcial", "A5": "-"},
            "v1-r2": {"A1": "ok", "A2": "reves", "A3": "elogio", "A4": "-", "A6": "derivado"},
            "v2-r1": {"A1": "ok", "A2": "ok", "A3": "parcial", "A5": "ok"},
            "v2-r2": {"A1": "parcial", "A2": "ok", "A3": "ok", "A6": "contaminado"},
        },
        "observaciones": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"],
        "citas": {"v1-r1": {"A1": "cita de v1-r1 sobre A1 | con barra"}},
    }


class Escenario:
    def __enter__(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = Path(self.temporal.name)
        return self

    def __exit__(self, *args):
        self.temporal.cleanup()

    def puntajes(self, datos, nombre="puntajes.json"):
        ruta = self.base / nombre
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        return ruta


def correr(args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        codigo = p().main([str(a) for a in args])
    return codigo, buffer.getvalue()


def correr_script(args):
    entorno = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    r = subprocess.run([sys.executable, str(SCRIPT), *[str(a) for a in args]], capture_output=True, env=entorno)
    return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n")


def leer(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def responder(tabla, clave, respuestas):
    inversa = {(c["corrida"], c["obs"]): i for i, c in clave["celdas"].items()}
    por_id = {inversa[k]: v for k, v in respuestas.items()}
    salida = []
    for linea in tabla.splitlines():
        m = re.match(r"^\| ([0-9a-f]{4}) \|", linea)
        if m:
            linea = linea.rstrip()
            assert linea.endswith("|"), linea
            linea = linea[:-1].rstrip() + " " + por_id.get(m.group(1), "sí") + " |"
        salida.append(linea)
    return "\n".join(salida) + "\n"


def plantilla(e, ruta, semilla, tabla="tabla.md", clave="clave.json"):
    codigo, salida = correr([ruta, "--plantilla-ratificacion", e.base / tabla, "--clave", e.base / clave, "--semilla", semilla])
    assert codigo == 0, salida
    return e.base / tabla, e.base / clave, salida


def ratificar(e, ruta, semilla, respuestas, extra=()):
    tabla, clave, _ = plantilla(e, ruta, semilla)
    datos_clave = leer(clave)
    tabla.write_text(responder(tabla.read_text(encoding="utf-8"), datos_clave, respuestas), encoding="utf-8")
    return correr([ruta, "--aplicar-ratificacion", tabla, clave, *extra])


def test_fmt_num_usa_coma_decimal():
    for x, esperado in ((5.5, "5,5"), (3.0, "3,0"), (4.25, "4,25"), (0, "0,0"), (2.5, "2,5"), (0.75, "0,75")):
        assert p().fmt_num(x) == esperado, (x, p().fmt_num(x))


def test_conteo_corrida():
    c = p().conteo_corrida({"A": "ok", "B": "parcial", "C": "reves", "D": "elogio", "E": "derivado",
                            "F": "contaminado", "G": "-", "H": "ok"})
    assert c == {"ok": 2, "parcial": 1, "contra": 2, "derivado": 1, "contaminado": 1, "puntaje": 2.5}, c


def test_veredicto_union_reglas():
    casos = [
        (["ok", "reves"], "ok"), (["parcial", "elogio"], "parcial"), (["parcial", "ok"], "ok"),
        (["reves", "elogio"], "contra"), (["reves", "-"], "contra"), (["derivado", "reves"], "contra"),
        (["derivado", "-"], "derivado"), (["contaminado", "-"], "contaminado"), (["-", "-"], "-"), ([], "-"),
        (["contaminado", "ok"], "ok"), (["derivado", "contaminado"], "derivado"),
    ]
    for entrada, esperado in casos:
        assert p().veredicto_union(entrada) == esperado, (entrada, p().veredicto_union(entrada))


def test_analizar_brazo_puntajes_media_union_estables_conflictos_y_k_sobre_n():
    b = p().analizar_brazo(sintetico(), "v1", ["v1-r1", "v1-r2"])
    assert [c["puntaje"] for c in b["corridas"]] == [2.5, 1.0], b["corridas"]
    assert b["media"] == 1.75, b["media"]
    u = b["union"]["conteo"]
    assert (u["ok"], u["parcial"], u["contra"], u["puntaje"]) == (2, 1, 1, 2.5), u
    assert b["estables"] == ["A1"], b["estables"]
    assert [x["obs"] for x in b["conflictos"]] == ["A2"], b["conflictos"]
    assert b["k_n"]["A1"] == (2, 2) and b["k_n"]["A2"] == (1, 2) and b["k_n"]["A3"] == (0, 2), b["k_n"]


def test_un_brazo_de_una_corrida_no_tiene_estables():
    b = p().analizar_brazo(sintetico(), "solo", ["v2-r1"])
    assert b["estables"] == [], b["estables"]
    assert b["media"] == b["corridas"][0]["puntaje"], b["media"]


def test_la_celda_contaminada_no_suma_pero_el_ok_de_otra_corrida_si():
    b = p().analizar_brazo(sintetico(), "v2", ["v2-r1", "v2-r2"])
    assert b["union"]["por_obs"]["A6"] == "contaminado", b["union"]["por_obs"]
    assert b["corridas"][1]["contaminado"] == 1 and b["corridas"][1]["ok"] == 2, b["corridas"][1]


def test_las_observaciones_van_en_orden_natural():
    datos = {"corridas": {"c": {"O10": "ok", "O2": "ok", "O1": "ok"}}, "observaciones": []}
    b = p().analizar_brazo(datos, "x", ["c"])
    assert list(b["k_n"]) == ["O1", "O2", "O10"], list(b["k_n"])


def test_un_brazo_con_una_corrida_inexistente_lanza_keyerror():
    try:
        p().analizar_brazo(sintetico(), "x", ["v1-r1", "no-existe"])
    except KeyError as error:
        assert "no-existe" in str(error), error
    else:
        raise AssertionError("tenía que lanzar KeyError")


def test_tabla_pareada_de_dos_brazos():
    d = sintetico()
    a = p().analizar_brazo(d, "v1", ["v1-r1", "v1-r2"])
    b = p().analizar_brazo(d, "v2", ["v2-r1", "v2-r2"])
    filas = p().tabla_pareada(d["observaciones"], [a, b])
    por = {f["obs"]: f for f in filas}
    assert len(filas) == 7, len(filas)
    assert por["A1"]["brazos"] == [{"k_n": (2, 2), "union": "ok"}, {"k_n": (1, 2), "union": "ok"}], por["A1"]
    assert por["A7"]["brazos"][0]["union"] == "-", por["A7"]


def test_cargar_puntajes_deja_las_disputadas_en_su_lugar():
    with Escenario() as e:
        ruta = e.puntajes(base())
        cargados = p().cargar_puntajes(ruta)
    assert cargados == base(), cargados
    assert "_excluidas" not in cargados, cargados


def test_cargar_puntajes_rechaza_un_veredicto_fuera_de_la_escala_y_la_falta_de_corridas():
    with Escenario() as e:
        malo = base()
        malo["corridas"]["a-1"]["O1"] = "excelente"
        try:
            p().cargar_puntajes(e.puntajes(malo))
        except ValueError as error:
            assert "excelente" in str(error) and "a-1/O1" in str(error), error
        else:
            raise AssertionError("tenía que lanzar ValueError")
        try:
            p().cargar_puntajes(e.puntajes({"fixture": "x"}, "sin-corridas.json"))
        except ValueError as error:
            assert "'corridas'" in str(error), error
        else:
            raise AssertionError("tenía que lanzar ValueError")


def test_excluir_disputadas_devuelve_una_copia_y_no_toca_el_original():
    original = base()
    copia = p().excluir_disputadas(original)
    assert original == base(), "el original cambió"
    assert all("O5" not in celdas for celdas in copia["corridas"].values()), copia["corridas"]
    assert "O5" not in copia["observaciones"], copia["observaciones"]
    assert copia["_excluidas"] == {"a-1": {"O5": "elogio"}, "a-2": {"O5": "elogio"}}, copia["_excluidas"]
    assert p().conteo_corrida(copia["corridas"]["a-1"])["contra"] == 1


def test_sin_disputadas_la_copia_queda_igual_salvo_excluidas_vacio():
    sin = sintetico()
    copia = p().excluir_disputadas(sin)
    assert copia["corridas"] == sin["corridas"] and copia["observaciones"] == sin["observaciones"]
    assert copia["_excluidas"] == {}


def test_el_reporte_sin_brazos_sale_exacto():
    with Escenario() as e:
        codigo, salida = correr([e.puntajes(base())])
    assert codigo == 0
    assert salida == REPORTE_BASE, salida


def test_el_reporte_con_dos_brazos_sale_exacto():
    with Escenario() as e:
        codigo, salida = correr([e.puntajes(base()), "--brazo", "a=a-1,a-2", "--brazo", "b=b-1"])
    assert codigo == 0
    assert salida == REPORTE_BRAZOS, salida


def test_el_reporte_nombra_a_quien_ratifico():
    with Escenario() as e:
        datos = base()
        datos["ratificado_por"] = "revisor-1 2026-10-21"
        codigo, salida = correr([e.puntajes(datos)])
    assert codigo == 0
    assert "Ratificado por: revisor-1 2026-10-21\n" in salida, salida
    assert "nadie todavía" not in salida


def test_el_reporte_no_escribe_ningun_archivo():
    with Escenario() as e:
        ruta = e.puntajes(base())
        antes = ruta.read_bytes()
        correr([ruta, "--brazo", "a=a-1,a-2"])
        assert ruta.read_bytes() == antes
        assert sorted(f.name for f in e.base.iterdir()) == ["puntajes.json"]


def test_errores_de_lectura_y_de_brazo_salen_con_2():
    with Escenario() as e:
        ruta = e.puntajes(base())
        codigo, salida = correr([e.base / "no.json"])
        assert codigo == 2 and salida.startswith("puntuar: no pude leer los puntajes ("), (codigo, salida)
        (e.base / "roto.json").write_text("{", encoding="utf-8")
        codigo, salida = correr([e.base / "roto.json"])
        assert codigo == 2 and salida.startswith("puntuar: no pude leer los puntajes ("), (codigo, salida)
        codigo, salida = correr([e.puntajes({"fixture": "x"}, "sc.json")])
        assert codigo == 2 and "no tiene el objeto 'corridas'" in salida, (codigo, salida)
        codigo, salida = correr([ruta, "--brazo", "x=no-existe"])
        assert (codigo, salida) == (2, "puntuar: corridas inexistentes en el puntaje: no-existe\n"), (codigo, salida)
        for malo in ("sin-igual", "=a-1", "x="):
            codigo, salida = correr([ruta, "--brazo", malo])
            assert codigo == 2 and "--brazo espera nombre=corrida,corrida" in salida, (malo, codigo, salida)


def test_la_plantilla_es_ciega_y_la_clave_la_descifra():
    d = sintetico()
    tabla, clave = p().generar_plantilla(d, semilla=7, ruta_puntajes="x.json")
    filas = [l for l in tabla.splitlines() if l.startswith("| ") and not l.startswith("| ID")]
    assert len(filas) == 15 and len(clave["celdas"]) == 15, (len(filas), len(clave["celdas"]))
    assert not re.search(r"v1|v2|r1|r2", tabla), tabla
    assert len(set(clave["celdas"])) == 15
    assert all(re.fullmatch(r"[0-9a-f]{4}", i) for i in clave["celdas"])
    assert all(c["veredicto"] not in ("-", "derivado") for c in clave["celdas"].values())
    assert "cita de [corrida] sobre A1 \\| con barra" in tabla, tabla
    assert set(next(iter(clave["celdas"].values()))) == {"corrida", "obs", "veredicto"}
    assert (clave["fixture"], clave["puntajes"]) == ("sintetico", "x.json")
    assert p().generar_plantilla(d, semilla=7, ruta_puntajes="x.json") == (tabla, clave)
    assert p().generar_plantilla(d, semilla=8, ruta_puntajes="x.json") != (tabla, clave)


def test_la_plantilla_muestra_la_escala_y_la_descripcion_de_la_observacion():
    tabla, _ = p().generar_plantilla(base(), semilla=1)
    assert "- **ok**: acierto\n- **-**: no lo toca\n" in tabla, tabla
    assert "O1 — primera observación" in tabla, tabla


def test_la_plantilla_por_cli_escribe_tabla_y_clave_en_utf8_y_deja_fuera_las_disputadas():
    with Escenario() as e:
        ruta = e.puntajes(base())
        tabla, clave, salida = plantilla(e, ruta, 5)
        assert salida == "plantilla: 8 fila(s) a ratificar; clave en %s (NO se la muestres a quien ratifica antes de que ratifique)\n" % clave, salida
        assert "Ratificación a ciegas: sintético".encode("utf-8") in tabla.read_bytes()
        datos_clave = leer(clave)
        assert len(datos_clave["celdas"]) == 8
        assert datos_clave["fixture"] == "sintético" and datos_clave["puntajes"] == str(ruta)
        assert all(c["obs"] != "O5" for c in datos_clave["celdas"].values())
        assert "O5" not in tabla.read_text(encoding="utf-8")


def test_la_plantilla_a_stdout_con_guion_no_escribe_la_tabla():
    with Escenario() as e:
        codigo, salida = correr([e.puntajes(base()), "--plantilla-ratificacion", "-", "--clave", e.base / "clave.json", "--semilla", 5])
        assert codigo == 0
        assert salida.startswith("# Ratificación a ciegas: sintético\n"), salida
        assert salida.rstrip().endswith("antes de que ratifique)"), salida
        assert sorted(f.name for f in e.base.iterdir()) == ["clave.json", "puntajes.json"]


def test_la_plantilla_sin_clave_sale_con_2_y_no_escribe():
    with Escenario() as e:
        codigo, salida = correr([e.puntajes(base()), "--plantilla-ratificacion", e.base / "tabla.md"])
        assert (codigo, salida) == (2, "puntuar: --plantilla-ratificacion exige --clave\n"), (codigo, salida)
        assert sorted(f.name for f in e.base.iterdir()) == ["puntajes.json"]


def test_interpretar_respuesta():
    f = p().interpretar_respuesta
    for texto in ("sí", "SI", " Si ", "**sí**", "`si`", "yes", "confirmado"):
        assert f(texto) == ("confirma", None), texto
    for texto, veredicto in (("no → parcial", "parcial"), ("No -> ok", "ok"), ("no: reves", "reves"),
                             ("no, elogio", "elogio"), ("no=>contaminado", "contaminado"), ("no → -", "-")):
        assert f(texto) == ("cambia", veredicto), texto
    for texto in ("", "   ", "?", "…", "...", "no → <veredicto>"):
        assert f(texto) == ("pendiente", None), texto
    for texto in ("tal vez", "no → excelente", "no"):
        try:
            f(texto)
        except p().RatificacionInvalida:
            continue
        raise AssertionError("tenía que ser inválida: %r" % texto)


def test_aplicar_ratificacion_confirma_y_corrige_sin_mutar_el_original():
    d = sintetico()
    tabla, clave = p().generar_plantilla(d, semilla=3, ruta_puntajes="x.json")
    resp = responder(tabla, clave, {("v1-r1", "A1"): "no → parcial", ("v1-r1", "A3"): "No -> ok", ("v2-r2", "A6"): "no → reves"})
    nuevo, cambios, pendientes = p().aplicar_ratificacion(resp, clave, d, "revisor-1", "2026-10-21")
    assert pendientes == []
    assert nuevo["corridas"]["v1-r1"]["A1"] == "parcial" and nuevo["corridas"]["v1-r1"]["A3"] == "ok"
    assert nuevo["corridas"]["v2-r2"]["A6"] == "reves"
    assert nuevo["corridas"]["v1-r1"]["A2"] == "ok"
    assert sorted((c["corrida"], c["obs"], c["de"], c["a"]) for c in cambios) == [
        ("v1-r1", "A1", "ok", "parcial"), ("v1-r1", "A3", "elogio", "ok"), ("v2-r2", "A6", "contaminado", "reves")]
    assert nuevo["ratificado_por"] == "revisor-1 2026-10-21"
    assert nuevo["ratificacion"] == {"por": "revisor-1", "fecha": "2026-10-21", "filas": 15, "pendientes": 0, "cambios": cambios}
    assert d["ratificado_por"] is None and d == sintetico()


def test_aplicar_ratificacion_con_pendientes_y_con_veredicto_invalido():
    d = sintetico()
    tabla, clave = p().generar_plantilla(d, semilla=3, ruta_puntajes="x.json")
    try:
        p().aplicar_ratificacion(tabla, clave, d, "r", "2026-10-21")
    except p().RatificacionIncompleta as error:
        assert len(error.pendientes) == 15
    else:
        raise AssertionError("la tabla sin responder tenía que fallar")
    malo = responder(tabla, clave, {("v1-r1", "A1"): "no → excelente"})
    try:
        p().aplicar_ratificacion(malo, clave, d, "r", "2026-10-21")
    except p().RatificacionInvalida:
        pass
    else:
        raise AssertionError("un veredicto fuera de la escala tenía que fallar")
    nuevo, _, pendientes = p().aplicar_ratificacion(tabla, clave, d, "r", "2026-10-21", permitir_pendientes=True)
    assert len(pendientes) == 15 and nuevo["corridas"] == d["corridas"]
    assert nuevo["ratificado_por"] == "r 2026-10-21 (parcial: 15 fila(s) sin responder)"


def test_aplicar_ratificacion_rechaza_un_id_de_otra_ronda():
    d = sintetico()
    tabla, clave = p().generar_plantilla(d, semilla=3)
    otra, _ = p().generar_plantilla(d, semilla=4)
    try:
        p().aplicar_ratificacion(otra, clave, d, "r", "2026-10-21")
    except p().RatificacionInvalida as error:
        assert "otra ronda" in str(error), error
    else:
        raise AssertionError("tenía que rechazar el ID")


def test_sin_quien_ratifica_la_funcion_lanza():
    d = sintetico()
    tabla, clave = p().generar_plantilla(d, semilla=3)
    for nadie in (None, "", "   "):
        try:
            p().aplicar_ratificacion(responder(tabla, clave, {}), clave, d, nadie, "2026-10-21")
        except p().RatificacionInvalida as error:
            assert "--ratificado-por" in str(error), error
        else:
            raise AssertionError("tenía que lanzar con %r" % (nadie,))


def test_ratificar_por_cli_corrige_el_archivo_y_cuenta_los_cambios():
    with Escenario() as e:
        ruta = e.puntajes(sintetico())
        codigo, salida = ratificar(e, ruta, 5, {("v2-r1", "A5"): "no → reves"}, ("--ratificado-por", "revisor-1"))
        assert codigo == 0, salida
        assert salida == "ratificado: 15 celda(s) revisadas, 1 corregida(s), 0 pendiente(s)\n  v2-r1 / A5: ok -> reves\n", salida
        nuevo = leer(ruta)
        assert nuevo["corridas"]["v2-r1"]["A5"] == "reves"
        assert nuevo["ratificado_por"] == "revisor-1 %s" % datetime.date.today().isoformat()
        assert nuevo["ratificacion"]["por"] == "revisor-1" and nuevo["ratificacion"]["cambios"] == [
            {"corrida": "v2-r1", "obs": "A5", "de": "ok", "a": "reves"}]
        assert "_excluidas" not in nuevo, nuevo.keys()
        esperado = sintetico()
        esperado["corridas"]["v2-r1"]["A5"] = "reves"
        esperado["ratificado_por"] = nuevo["ratificado_por"]
        esperado["ratificacion"] = nuevo["ratificacion"]
        assert nuevo == esperado, nuevo


def test_los_archivos_que_escribe_van_en_lf_sin_bom():
    with Escenario() as e:
        ruta = e.puntajes(sintetico())
        tabla, clave, _ = plantilla(e, ruta, 5)
        for escrito in (tabla, clave):
            crudo = escrito.read_bytes()
            assert b"\r\n" not in crudo and b"\n" in crudo and not crudo.startswith(b"\xef\xbb\xbf"), (escrito.name, crudo[:80])
        codigo, salida = ratificar(e, ruta, 5, {}, ("--ratificado-por", "revisor-1"))
        assert codigo == 0, salida
        crudo = ruta.read_bytes()
        assert b"\r\n" not in crudo and b"\n" in crudo and not crudo.startswith(b"\xef\xbb\xbf"), crudo[:80]


def test_sin_ratificado_por_el_cli_sale_con_2_y_no_toca_el_archivo():
    with Escenario() as e:
        ruta = e.puntajes(sintetico())
        tabla, clave, _ = plantilla(e, ruta, 5)
        tabla.write_text(responder(tabla.read_text(encoding="utf-8"), leer(clave), {}), encoding="utf-8")
        antes = ruta.read_bytes()
        for extra in ((), ("--ratificado-por", ""), ("--ratificado-por", "  ")):
            codigo, salida = correr([ruta, "--aplicar-ratificacion", tabla, clave, *extra])
            assert codigo == 2, (extra, codigo, salida)
            assert salida.startswith("puntuar: ") and "--ratificado-por" in salida and "obligatorio" in salida, salida
            assert ruta.read_bytes() == antes


def test_los_textos_de_la_plantilla_no_nombran_a_nadie():
    with Escenario() as e:
        _, _, salida = plantilla(e, e.puntajes(sintetico()), 5)
        assert salida.endswith("(NO se la muestres a quien ratifica antes de que ratifique)\n"), salida
        codigo, ayuda = correr_script(["-h"])
        assert codigo == 0
        assert "(obligatorio)" in ayuda and "default" not in ayuda.lower(), ayuda


def test_ratificar_dos_veces_conserva_las_celdas_disputadas_y_las_observaciones():
    with Escenario() as e:
        inicial = sintetico()
        inicial["disputadas"] = {"A3": "contraejemplo verificado"}
        ruta = e.puntajes(inicial)

        codigo, salida = ratificar(e, ruta, 1, {("v1-r1", "A1"): "no → parcial"}, ("--ratificado-por", "revisor-1"))
        assert codigo == 0, salida
        assert salida == "ratificado: 11 celda(s) revisadas, 1 corregida(s), 0 pendiente(s)\n  v1-r1 / A1: ok -> parcial\n", salida
        primera = leer(ruta)
        esperado = sintetico()
        esperado["disputadas"] = {"A3": "contraejemplo verificado"}
        esperado["corridas"]["v1-r1"]["A1"] = "parcial"
        esperado["ratificado_por"] = primera["ratificado_por"]
        esperado["ratificacion"] = primera["ratificacion"]
        assert primera == esperado, primera
        assert "_excluidas" not in primera, primera.keys()

        codigo, salida = ratificar(e, ruta, 2, {("v2-r1", "A2"): "no → reves"}, ("--ratificado-por", "revisor-2"))
        assert codigo == 0, salida
        segunda = leer(ruta)
        esperado["corridas"]["v2-r1"]["A2"] = "reves"
        esperado["ratificado_por"] = segunda["ratificado_por"]
        esperado["ratificacion"] = segunda["ratificacion"]
        assert segunda == esperado, segunda
        assert segunda["ratificacion"]["por"] == "revisor-2" and segunda["ratificacion"]["cambios"] == [
            {"corrida": "v2-r1", "obs": "A2", "de": "ok", "a": "reves"}]
        assert [c.get("A3") for c in segunda["corridas"].values()] == ["elogio", "elogio", "parcial", "ok"]
        assert "A3" in segunda["observaciones"] and segunda["disputadas"] == {"A3": "contraejemplo verificado"}


def test_el_reporte_tras_ratificar_sigue_dejando_fuera_las_disputadas():
    with Escenario() as e:
        ruta = e.puntajes(base())
        codigo, _ = ratificar(e, ruta, 1, {("a-1", "O1"): "no → parcial"}, ("--ratificado-por", "revisor-1"))
        assert codigo == 0
        codigo, salida = correr([ruta])
        assert codigo == 0
        assert "Fuera del puntaje (verdad de terreno disputada con evidencia): O5" in salida
        assert "| a-1 | 0 | 2 | 1 | 1,0 | 1 | 0 |" in salida, salida


def test_ratificar_con_pendientes_sale_con_1_y_no_escribe():
    with Escenario() as e:
        ruta = e.puntajes(base())
        tabla, clave, _ = plantilla(e, ruta, 5)
        antes = ruta.read_bytes()
        codigo, salida = correr([ruta, "--aplicar-ratificacion", tabla, clave, "--ratificado-por", "revisor-1"])
        assert codigo == 1, (codigo, salida)
        ids = ", ".join(leer(clave)["celdas"])
        assert salida == ("puntuar: faltan 8 fila(s) por responder (IDs: %s); no se escribio nada. "
                          "Usa --permitir-pendientes para aplicar el resto.\n" % ids), salida
        assert ruta.read_bytes() == antes


def test_permitir_pendientes_aplica_el_resto():
    with Escenario() as e:
        ruta = e.puntajes(base())
        tabla, clave, _ = plantilla(e, ruta, 5)
        datos_clave = leer(clave)
        tabla.write_text(responder(tabla.read_text(encoding="utf-8"), datos_clave, {("a-1", "O1"): "no → parcial"}).replace(
            "| sí |", "|  |", 3), encoding="utf-8")
        codigo, salida = correr([ruta, "--aplicar-ratificacion", tabla, clave, "--ratificado-por", "revisor-1", "--permitir-pendientes"])
        assert codigo == 0, salida
        assert salida.startswith("ratificado: 8 celda(s) revisadas, "), salida
        nuevo = leer(ruta)
        assert nuevo["ratificado_por"].endswith(" (parcial: 3 fila(s) sin responder)"), nuevo["ratificado_por"]
        assert nuevo["ratificacion"]["pendientes"] == 3


def test_ratificar_con_una_respuesta_invalida_o_un_archivo_que_falta_sale_con_2():
    with Escenario() as e:
        ruta = e.puntajes(base())
        tabla, clave, _ = plantilla(e, ruta, 5)
        antes = ruta.read_bytes()
        invalida = responder(tabla.read_text(encoding="utf-8"), leer(clave), {("a-1", "O1"): "no → excelente"})
        tabla.write_text(invalida, encoding="utf-8")
        codigo, salida = correr([ruta, "--aplicar-ratificacion", tabla, clave, "--ratificado-por", "r"])
        assert codigo == 2 and salida.startswith("puntuar: respuesta no reconocida: "), (codigo, salida)
        codigo, salida = correr([ruta, "--aplicar-ratificacion", e.base / "no.md", clave, "--ratificado-por", "r"])
        assert codigo == 2 and salida.startswith("puntuar: "), (codigo, salida)
        assert ruta.read_bytes() == antes


def test_serializar_puntajes_ida_y_vuelta_con_una_corrida_por_linea():
    d = sintetico()
    d["escala"] = {"ok": "acierto", "-": "no lo toca"}
    d["versiones"] = {"v1": "observación"}
    texto = p().serializar_puntajes(d)
    assert json.loads(texto) == d
    assert list(json.loads(texto)) == list(d)
    assert '    "v1-r1": {"A1": "ok"' in texto and '\n  "observaciones": ["A1"' in texto, texto
    assert "observación" in texto and texto.endswith("}\n")


def test_la_salida_va_en_utf8_aunque_la_consola_sea_otra():
    with Escenario() as e:
        ruta = e.puntajes(base())
        entorno = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        r = subprocess.run([sys.executable, str(SCRIPT), str(ruta), "--brazo", "a=a-1,a-2", "--brazo", "b=b-1"],
                           capture_output=True, env=entorno)
        assert r.returncode == 0, r.stderr
        assert "Unión".encode("utf-8") in r.stdout and "—".encode("utf-8") in r.stdout
        assert r.stdout.decode("utf-8").replace("\r\n", "\n") == REPORTE_BRAZOS


def test_un_error_interno_sale_con_2_por_stderr_y_sin_stdout():
    with Escenario() as e:
        roto = base()
        roto["corridas"]["a-1"] = ["no", "es", "un", "objeto"]
        ruta = e.puntajes(roto)
        r = subprocess.run([sys.executable, str(SCRIPT), str(ruta)], capture_output=True)
        assert r.returncode == 2, r
        assert r.stdout == b"", r.stdout
        assert r.stderr.decode("utf-8").startswith("puntuar: error interno ("), r.stderr


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
