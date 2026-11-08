import json

from odd_ws.comun import SILENCIO


def cargar(crudo):
    return json.loads(crudo) if isinstance(crudo, (str, bytes, bytearray)) else crudo


def atender(leer, responder, crudo, decidir, pre_por_defecto=False):
    evento = leer(cargar(crudo), pre_por_defecto)
    return SILENCIO if evento is None else responder(evento, decidir(evento))
