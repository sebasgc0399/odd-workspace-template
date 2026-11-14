import importlib
import json
from collections import namedtuple
from pathlib import Path

from odd_ws.comun import SILENCIO
from odd_ws.hosts.base import cargar

ADAPTADORES = ("claude_code", "codex", "pi")
NOMBRES = {"claude-code": "claude_code", "codex": "codex", "pi": "pi"}
FUENTE = "claude-code"
PRE = "PreToolUse"
PRE_DE_PI = "tool_call"

Archivo = namedtuple("Archivo", "ruta contenido fuente arreglo", defaults=(None, None))


def leer_hooks(ruta):
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def manejadores(datos):
    eventos = datos.get("hooks") if isinstance(datos, dict) else None
    if not isinstance(eventos, dict):
        return
    for evento, grupos in eventos.items():
        if not isinstance(grupos, list):
            continue
        for grupo, entrada in enumerate(grupos):
            lista = entrada.get("hooks") if isinstance(entrada, dict) else None
            for indice, manejador in enumerate(lista if isinstance(lista, list) else []):
                yield evento, grupo, indice, manejador


def tokens_de(texto, windows=False):
    import shlex

    if windows:
        texto = texto.replace("\\", "/")
    try:
        return shlex.split(texto)
    except ValueError:
        return texto.split()


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
    if payload.get("type") == PRE_DE_PI:
        return True
    return payload.get("hook_event_name", PRE if pre_por_defecto else None) == PRE


def _enumerar(partes):
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def host_desconocido(nombre, crudo, pre_por_defecto=False):
    if not _es_pre(crudo, pre_por_defecto):
        return SILENCIO
    valor = "sin valor" if nombre is None else repr(nombre)
    motivo = ("odd-ws: host desconocido en --host (%s); los válidos son %s. El hook está mal configurado y bloquea hasta "
              "que se corrija su comando." % (valor, _enumerar(list(NOMBRES))))
    return 2, "", (motivo + "\n").encode("utf-8", "replace")


def atender(nombre, crudo, decidir, pre_por_defecto=False):
    elegido = adaptador(nombre)
    if elegido is None:
        return host_desconocido(nombre, crudo, pre_por_defecto)
    return elegido.atender(crudo, decidir, pre_por_defecto)
