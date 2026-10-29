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
