import importlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
SOBRANTES = []


def m():
    return importlib.import_module("odd_ws.transcripcion")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Temporal:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="transcripcion-test-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def escribir(base, lineas, nombre="t.jsonl"):
    ruta = base / nombre
    ruta.write_bytes(("\n".join(l if isinstance(l, str) else json.dumps(l) for l in lineas) + "\n").encode("utf-8"))
    return ruta


def test_constantes_de_claude_code():
    assert m().HANDBACK == "SubagentHandback"
    assert m().LECTURA == ("Read", "Grep", "Glob")


def test_leer_devuelve_los_objetos_en_orden_y_cuenta_la_linea_rota():
    with Temporal() as base:
        ruta = escribir(base, [{"n": 1}, "{esto no es json", "", "   ", {"n": 2}, '{"n": 3, "cortada'])
        registros, salteadas = m().leer(ruta)
        assert registros == [{"n": 1}, {"n": 2}], registros
        assert salteadas == 2, salteadas


def test_leer_saltea_lo_que_es_json_pero_no_es_un_objeto():
    with Temporal() as base:
        ruta = escribir(base, ["[1, 2]", "5", '"texto"', "null", {"n": 1}])
        registros, salteadas = m().leer(ruta)
        assert (registros, salteadas) == ([{"n": 1}], 4), (registros, salteadas)


def test_leer_acepta_str_y_pathlike_y_el_archivo_vacio():
    with Temporal() as base:
        ruta = escribir(base, [{"n": 1}])
        assert m().leer(str(ruta)) == ([{"n": 1}], 0)
        assert m().leer(ruta) == ([{"n": 1}], 0)
        (base / "vacio.jsonl").write_bytes(b"")
        assert m().leer(base / "vacio.jsonl") == ([], 0)


def test_leer_devuelve_none_si_no_es_una_ruta_o_no_abre():
    with Temporal() as base:
        for no_ruta in (None, 5, ["x"], b"bytes", {"a": 1}):
            assert m().leer(no_ruta) is None, no_ruta
        assert m().leer(base / "no-existe.jsonl") is None
        assert m().leer(base) is None, "una carpeta no se abre como archivo"


def test_leer_tolera_bytes_que_no_son_utf8():
    with Temporal() as base:
        ruta = base / "bin.jsonl"
        ruta.write_bytes(b'{"n": 1}\n\xff\xfe\x00{\n{"t": "a\xe9b"}\n')
        registros, salteadas = m().leer(ruta)
        assert registros == [{"n": 1}, {"t": "a�b"}], registros
        assert salteadas == 1, salteadas


def test_bloques_solo_de_un_mensaje_con_contenido_en_lista():
    lista = [{"type": "text", "text": "x"}]
    assert m().bloques({"message": {"content": lista}}) == lista
    for registro in ({}, {"message": None}, {"message": "texto"}, {"message": {"content": "texto"}},
                     {"message": {"content": None}}, {"message": {}}, {"message": [1]}):
        assert m().bloques(registro) == [], registro


def mensaje(id_, entrada, escrita, leida, salida, ts=None):
    registro = {"type": "assistant", "message": {"id": id_, "role": "assistant", "content": [], "usage": {
        "input_tokens": entrada, "cache_creation_input_tokens": escrita, "cache_read_input_tokens": leida,
        "output_tokens": salida}}}
    if ts:
        registro["timestamp"] = ts
    return registro


def test_constantes_del_uso_de_claude_code():
    assert m().USO == "usage"
    assert (m().ENTRADA, m().CACHE_ESCRITA, m().CACHE_LEIDA, m().SALIDA) == (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def test_costo_cuenta_cada_mensaje_una_vez_por_id():
    registros = [
        {"type": "user", "timestamp": "2026-11-18T10:00:00.000Z", "message": {"content": "p"}},
        mensaje("m1", 3, 40000, 0, 100, "2026-11-18T10:00:05.000Z"),
        mensaje("m1", 3, 40000, 0, 100, "2026-11-18T10:00:05.500Z"),
        {"type": "user", "timestamp": "2026-11-18T10:00:06.000Z", "message": {"content": []}},
        mensaje("m2", 2, 5000, 40000, 300, "2026-11-18T10:00:09.000Z"),
        mensaje("m2", 2, 5000, 40000, 300, "2026-11-18T10:00:09.100Z"),
        mensaje("m2", 2, 5000, 40000, 300, "2026-11-18T10:00:09.200Z"),
        mensaje("m3", 1, 700, 45000, 50, "2026-11-18T10:01:30.000Z"),
    ]
    assert m().costo(registros) == {
        "turnos": 3, "contexto_inicial": 40003, "contexto_final": 45701, "salida": 450,
        "cache_escrita": 45700, "cache_leida": 85000, "inicio": "2026-11-18T10:00:00.000Z",
        "fin": "2026-11-18T10:01:30.000Z", "pausa_mayor": 80.8}, m().costo(registros)
    assert list(m().costo(registros)) == ["turnos", "contexto_inicial", "contexto_final", "salida", "cache_escrita",
                                          "cache_leida", "inicio", "fin", "pausa_mayor"]


def test_costo_de_una_transcripcion_sin_uso_es_none():
    viejos = [{"type": "user", "timestamp": "2026-11-18T10:00:00.000Z", "message": {"content": "p"}},
              {"type": "assistant", "timestamp": "2026-11-18T10:00:01.000Z", "message": {"id": "m1", "content": []}},
              {"type": "assistant", "message": {"id": "m2", "content": [], "usage": None}},
              {"type": "assistant", "message": "texto"}, {"type": "user", "message": {"usage": {"output_tokens": 9}}}]
    assert m().costo(viejos) is None
    assert m().costo([]) is None


def test_costo_toma_la_ultima_linea_de_cada_id_en_el_lugar_de_la_primera():
    registros = [mensaje("m1", 1, 10, 0, 1), mensaje("m2", 1, 20, 0, 5), mensaje("m1", 1, 10, 0, 7)]
    c = m().costo(registros)
    assert (c["turnos"], c["salida"], c["contexto_inicial"], c["contexto_final"]) == (2, 12, 11, 21), c


def test_costo_cuenta_aparte_cada_mensaje_sin_id():
    registros = [mensaje(None, 1, 10, 0, 1), mensaje(None, 1, 10, 0, 1), mensaje("", 1, 10, 0, 1)]
    c = m().costo(registros)
    assert (c["turnos"], c["salida"], c["cache_escrita"]) == (3, 3, 30), c


def test_costo_toma_como_cero_los_tokens_que_no_son_un_entero():
    registros = [{"type": "assistant", "message": {"id": "m1", "usage": {
        "input_tokens": None, "cache_creation_input_tokens": "9", "cache_read_input_tokens": True, "output_tokens": -4}}},
        {"type": "assistant", "message": {"id": "m2", "usage": {"output_tokens": 6}}}]
    c = m().costo(registros)
    assert (c["turnos"], c["contexto_inicial"], c["contexto_final"], c["salida"], c["cache_escrita"], c["cache_leida"]) == (
        2, 0, 0, 6, 0, 0), c


def test_costo_ordena_los_tiempos_y_saltea_los_que_no_se_leen():
    registros = [
        mensaje("m1", 1, 1, 1, 1, "2026-11-18T10:05:00.000Z"),
        {"type": "user", "timestamp": "2026-11-18T10:00:00.000Z"},
        {"type": "user", "timestamp": "no es una fecha"},
        {"type": "user", "timestamp": 1731924000},
        {"type": "user", "timestamp": "2026-11-18T10:06:00"},
        {"type": "attachment", "timestamp": "2026-11-18T05:02:00-05:00"},
    ]
    c = m().costo(registros)
    assert (c["inicio"], c["fin"], c["pausa_mayor"]) == ("2026-11-18T10:00:00.000Z", "2026-11-18T10:06:00", 180.0), c


def test_costo_sin_tiempos_o_con_uno_solo():
    c = m().costo([mensaje("m1", 1, 1, 1, 1)])
    assert (c["inicio"], c["fin"], c["pausa_mayor"]) == (None, None, None), c
    c = m().costo([mensaje("m1", 1, 1, 1, 1, "2026-11-18T10:00:00.000Z")])
    assert (c["inicio"], c["fin"], c["pausa_mayor"]) == ("2026-11-18T10:00:00.000Z", "2026-11-18T10:00:00.000Z", None), c


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
    if SOBRANTES:
        fallas += 1
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
