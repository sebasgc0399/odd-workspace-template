import importlib

from odd_ws.comun import SILENCIO
from odd_ws.hosts.base import cargar

ADAPTADORES = ("claude_code", "codex")
NOMBRES = {"claude-code": "claude_code", "codex": "codex"}
PRE = "PreToolUse"


def adaptador(nombre):
    modulo = NOMBRES.get(nombre) if isinstance(nombre, str) else None
    return importlib.import_module("odd_ws.hosts." + modulo) if modulo else None


def necesita_bitacora(nombre):
    elegido = adaptador(nombre)
    return elegido is not None and elegido.BITACORA


def _es_pre(crudo, pre_por_defecto):
    try:
        payload = cargar(crudo)
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return pre_por_defecto
    return payload.get("hook_event_name", PRE if pre_por_defecto else None) == PRE


def host_desconocido(nombre, crudo, pre_por_defecto=False):
    if not _es_pre(crudo, pre_por_defecto):
        return SILENCIO
    valor = "sin valor" if nombre is None else repr(nombre)
    motivo = ("odd-ws: host desconocido en --host (%s); los válidos son %s. El hook está mal configurado y bloquea hasta "
              "que se corrija su comando." % (valor, " y ".join(NOMBRES)))
    return 2, "", (motivo + "\n").encode("utf-8", "replace")


def atender(nombre, crudo, decidir, pre_por_defecto=False):
    elegido = adaptador(nombre)
    if elegido is None:
        return host_desconocido(nombre, crudo, pre_por_defecto)
    return elegido.atender(crudo, decidir, pre_por_defecto)
