import sys

sys.dont_write_bytecode = True

import csv
import io
from pathlib import Path

import matriz
from odd_ws import capas as convencion

CLAVES = ()
PLANTILLAS = Path(__file__).resolve().parent.parent / "plantillas" / "reglas"
STUB = "verificar.py"
STUB_PRUEBAS = "verificar.tests.py"
EVIDENCIA = (
    "# Evidencia de las reglas\n"
    "\n"
    "Aquí se anota la evidencia de cada regla de `matriz.csv`: el incidente o el hallazgo del que nació y cómo se midió. "
    "Una regla sin evidencia no entra a la matriz.\n"
)


def _capas(spec):
    config = spec.get("config")
    capas = config.get("layers") if isinstance(config, dict) else None
    return capas if isinstance(capas, dict) else {}


def validar(spec):
    from bootstrap import SpecInvalida

    for nombre, datos in _capas(spec).items():
        if isinstance(datos, dict) and "rule_prefix" not in datos:
            raise SpecInvalida(
                f"layers.{nombre}.rule_prefix falta: la entrevista lo deriva de la capa y lo confirma, "
                "y sin él la capa no tiene matriz de reglas")


def _plantilla(nombre):
    return (PLANTILLAS / nombre).read_text(encoding="utf-8-sig")


def _matriz_vacia():
    salida = io.StringIO()
    csv.writer(salida, lineterminator="\n").writerow(matriz.ENCABEZADO)
    return salida.getvalue()


def generar(spec):
    acciones = [(convencion.MATRIZ, _matriz_vacia()), (convencion.EVIDENCIA, EVIDENCIA)]
    stub, pruebas = _plantilla(STUB), _plantilla(STUB_PRUEBAS)
    for capa in _capas(spec):
        acciones.append((convencion.chequeo(capa), stub))
        acciones.append((convencion.prueba(capa), pruebas))
    return acciones
