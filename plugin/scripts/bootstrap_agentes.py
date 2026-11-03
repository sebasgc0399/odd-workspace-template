import datetime
from pathlib import Path

import plantilla_writer
from odd_ws import capas

CLAVES = ()
PLANTILLAS = Path(__file__).resolve().parents[1] / "plantillas"
PLANTILLA_REVISOR = PLANTILLAS / "revisor.md"
PLANTILLA_CAPA = PLANTILLAS / "capa.md"
PLANTILLA_CRITERIOS = PLANTILLAS / "criterios.md"


def _fecha(hoy):
    if hoy is None:
        return datetime.date.today().isoformat()
    if isinstance(hoy, datetime.datetime):
        return hoy.date().isoformat()
    if isinstance(hoy, datetime.date):
        return hoy.isoformat()
    if isinstance(hoy, str):
        try:
            return datetime.date.fromisoformat(hoy).isoformat()
        except ValueError:
            pass
    raise ValueError("hoy debe ser una fecha o un texto AAAA-MM-DD, no %r" % (hoy,))


def _capas_de(spec):
    config = spec.get("config") if isinstance(spec, dict) else None
    declaradas = config.get("layers") if isinstance(config, dict) else None
    if not isinstance(declaradas, dict):
        return []
    return [capa for capa in declaradas if isinstance(capa, str) and capas.es_writer("writer-%s" % capa)]


def _sustituir(ruta, capa, fecha):
    texto = plantilla_writer.leer_plantilla(ruta)
    return texto.replace("{{capa}}", capa).replace("{{fecha}}", fecha)


def generar_revisor(capa, actual=None):
    return plantilla_writer.armar(capa, plantilla_writer.leer_plantilla(PLANTILLA_REVISOR), actual)


def generar(spec, hoy=None):
    fecha = _fecha(hoy)
    acciones = []
    for capa in _capas_de(spec):
        acciones.append((capas.writer(capa), plantilla_writer.generar(capa)))
        acciones.append((capas.revisor(capa), generar_revisor(capa)))
        acciones.append((capas.skill(capa), _sustituir(PLANTILLA_CAPA, capa, fecha)))
    acciones.append((capas.CRITERIOS_SKILL, _sustituir(PLANTILLA_CRITERIOS, "", fecha)))
    return acciones
