import importlib.util
import sys
from pathlib import Path

MODOS = ("aviso", "bloqueo")
MUESTRAS = ("", "una línea\n", "línea ñ\notra línea\n\n", "x" * 5000 + "\n")

ARCHIVO = Path(__file__).with_name(Path(__file__).name.replace(".tests.py", ".py"))
especificacion = importlib.util.spec_from_file_location("verificar_de_la_capa", ARCHIVO)
M = importlib.util.module_from_spec(especificacion)
especificacion.loader.exec_module(M)


def ctx_de(texto):
    agregadas = [(n, linea) for n, linea in enumerate(texto.split("\n"), 1) if linea] if texto else []
    return {
        "ruta": str(ARCHIVO), "relativa": "muestra.ext", "relativa_repo": None, "origen": "taller", "capa": "capa",
        "bytes": texto.encode("utf-8"), "texto": texto, "es_nuevo": True, "agregadas": agregadas,
        "hunks": [{"agregadas": agregadas, "quitadas": []}] if agregadas else [], "limite": None,
    }


def hallazgos_de(texto):
    encontrados = M.verificar(ctx_de(texto))
    assert isinstance(encontrados, list), f"verificar(ctx) debe devolver una lista, no {type(encontrados).__name__}"
    return encontrados


def test_el_modulo_declara_verificar_y_reglas():
    assert callable(getattr(M, "verificar", None)), "falta verificar(ctx)"
    reglas = getattr(M, "REGLAS", None)
    assert reglas is not None, "falta REGLAS (puede ser una tupla vacía)"
    assert all(isinstance(getattr(regla, "id", None), str) and regla.id for regla in reglas), "cada regla de REGLAS lleva un id"
    ids = [regla.id for regla in reglas]
    assert len(ids) == len(set(ids)), "los ids de REGLAS no se repiten"


def test_cada_hallazgo_cumple_el_contrato():
    ids = {regla.id for regla in M.REGLAS}
    for texto in MUESTRAS:
        for h in hallazgos_de(texto):
            assert isinstance(h, dict), f"un hallazgo debe ser un dict: {h!r}"
            assert isinstance(h.get("id"), str) and h["id"], f"el hallazgo no trae id: {h!r}"
            assert isinstance(h.get("mensaje"), str) and h["mensaje"], f"el hallazgo no trae mensaje: {h!r}"
            assert h.get("modo") in MODOS, f"modo debe ser {' o '.join(MODOS)}: {h!r}"
            assert not ids or h["id"] in ids, f"el id {h['id']} no está en REGLAS"
            assert h.get("linea") is None or isinstance(h["linea"], int), f"linea debe ser un entero o None: {h!r}"


def test_verificar_es_determinista():
    for texto in MUESTRAS:
        assert hallazgos_de(texto) == hallazgos_de(texto)


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
