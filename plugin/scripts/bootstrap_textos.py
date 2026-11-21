import sys

sys.dont_write_bytecode = True

from pathlib import Path

import config_loader
from odd_ws import capas as convencion

CLAVES = ("proyecto",)
CLAVES_DEL_PROYECTO = ("nombre",)
PLANTILLAS = Path(__file__).resolve().parent.parent / "plantillas"
PLANTILLA_INDICE = "CLAUDE.md"
PLANTILLA_INDICE_DE_CONTROLES = "CLAUDE.controles.md"
PLANTILLA_TICKET = "ticket.md"


def _error(mensaje):
    from bootstrap import SpecInvalida

    return SpecInvalida(mensaje)


def _nombre_valido(nombre):
    return isinstance(nombre, str) and nombre.strip() != "" and nombre == nombre.strip() and nombre.isprintable()


def validar(spec):
    proyecto = spec.get("proyecto")
    if not isinstance(proyecto, dict):
        raise _error('proyecto es obligatorio y debe ser un objeto: {"nombre": "<texto>"}')
    desconocidas = sorted(set(proyecto) - set(CLAVES_DEL_PROYECTO))
    if desconocidas:
        raise _error(f"proyecto.{desconocidas[0]} no es una clave conocida ({', '.join(CLAVES_DEL_PROYECTO)})")
    if not _nombre_valido(proyecto.get("nombre")):
        raise _error("proyecto.nombre es obligatorio: un texto de una línea, sin espacios en los bordes")


def _plantilla(nombre):
    return (PLANTILLAS / nombre).read_text(encoding="utf-8-sig")


def generar(spec):
    nombre = spec["proyecto"]["nombre"]
    if config_loader.perfil_de(spec["config"]) == config_loader.CONTROLES:
        return [(convencion.INDICE, _plantilla(PLANTILLA_INDICE_DE_CONTROLES).replace("{{nombre}}", nombre))]
    indice = _plantilla(PLANTILLA_INDICE).replace("{{tickets}}", convencion.TICKETS).replace("{{nombre}}", nombre)
    return [(convencion.INDICE, indice), (convencion.TICKET_PLANTILLA, _plantilla(PLANTILLA_TICKET))]
