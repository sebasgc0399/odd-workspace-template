import json
import os

from odd_ws.capacidades import DEGRADADO, FIN_SUBAGENTE, INICIO, POST, PRE, SOPORTADO
from odd_ws.comun import SILENCIO, archivos_de_la_bitacora, comandos_de_la_bitacora
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, FinSubagente, Herramienta, InicioSesion, Preguntar, Seguir
from odd_ws.hosts import base

cargar = base.cargar
EXPRESABLES = {PRE: (Bloquear, Preguntar), POST: (Bloquear, Contexto), INICIO: (Contexto,), FIN_SUBAGENTE: (Seguir,)}
DEGRADACIONES = {PRE: {Preguntar: Bloquear}}
BITACORA = True
MANIFIESTO = {
    "P1": (SOPORTADO, "SessionStart con additionalContext en startup, resume, clear, compact y fork"),
    "P2": (SOPORTADO, "PreToolUse de apply_patch: permissionDecision deny por JSON con exit 0, con las rutas sacadas del "
                      "parche (Add, Update, Delete y Move to); nunca exit 2, que PowerShell convierte en 1 y no bloquea"),
    "P3": (DEGRADADO, "PreToolUse de Bash: permissionDecision deny por JSON con exit 0; preguntar se degrada a bloquear, "
                      "porque permissionDecision ask falla abierto, y el motivo pide que el usuario corra el comando"),
    "P4": (DEGRADADO, "PostToolUse de apply_patch: decision block o additionalContext por JSON con exit 0; no hay "
                      "herramienta de lectura, así que el primer toque no llega al leer sino al editar, con el bloqueo de pre"),
    "P5": (SOPORTADO, "SubagentStop con matcher por agent_type y decision block; los archivos y los comandos del writer "
                      "salen de la bitácora que writer_guard anota en pre, no del transcript (F1b)"),
    "P6": (SOPORTADO, "agent_type y agent_id dentro de un subagente"),
    "P7": (DEGRADADO, "agentes TOML en .codex/agents, sin lista de herramientas ni skills precargadas: van en "
                      "developer_instructions (F1d)"),
    "P8": (DEGRADADO, "skills del plugin (SKILL.md), pero no respeta disable-model-invocation; el equivalente es "
                      "agents/openai.yaml con allow_implicit_invocation: false"),
    "P9": (SOPORTADO, ".codex-plugin/plugin.json apunta a hooks/hooks.codex.json, con cada comando como texto, la ruta de "
                      "PLUGIN_ROOT entre comillas y --host codex; los hooks necesitan confianza en /hooks, que se pide de "
                      "nuevo con cada actualización"),
    "P10": (DEGRADADO, "CLAUDE.md por project_doc_fallback_filenames, desde la raíz hasta el cwd y solo al arrancar (F1d)"),
}
SIN_CONFIRMACION = ("Codex no puede pedir confirmación desde un hook, así que este comando queda bloqueado: si hace falta, "
                    "pídele al usuario que lo corra él.")
FASES = {"PreToolUse": "pre", "PostToolUse": "post"}
NOMBRES = {fase: nombre for nombre, fase in FASES.items()}
PARCHE = "apply_patch"
SHELL = "Bash"
MARCAS = (("*** Add File: ", False), ("*** Update File: ", True), ("*** Delete File: ", False), ("*** Move to: ", True))
FIN_DE_ARCHIVO = "*** End of File"
SISTEMA = os.name


def _dialecto():
    return POWERSHELL if SISTEMA == "nt" else POSIX


def _en_el_parche(texto):
    rutas, cambiando = [], False
    for linea in texto.split("\n"):
        linea = linea.rstrip("\r")
        if cambiando and not linea.startswith("***"):
            continue
        marca = linea.strip()
        if marca == FIN_DE_ARCHIVO:
            continue
        cambiando = False
        for prefijo, abre in MARCAS:
            if marca.startswith(prefijo):
                rutas.append(marca[len(prefijo):])
                cambiando = abre
                break
    return rutas


def rutas_del_parche(texto, cwd):
    rutas = []
    for ruta in _en_el_parche(texto):
        if not os.path.isabs(ruta) and isinstance(cwd, str) and cwd:
            ruta = os.path.normpath(os.path.join(cwd, ruta))
        if ruta not in rutas:
            rutas.append(ruta)
    return tuple(rutas)


def _herramienta(payload, fase):
    nombre = payload.get("tool_name")
    nombre = nombre if isinstance(nombre, str) else None
    entrada = payload.get("tool_input")
    entrada = entrada if isinstance(entrada, dict) else {}
    comando = entrada.get("command")
    comando = comando if isinstance(comando, str) else None
    tipo, rutas, dialecto = "otra", (), None
    if nombre == PARCHE:
        tipo, rutas, comando = "edicion", rutas_del_parche(comando or "", payload.get("cwd")), None
    elif nombre == SHELL:
        tipo, dialecto = "shell", _dialecto()
    else:
        comando = None
    return Herramienta(
        fase=fase, tipo=tipo, herramienta=nombre, rutas=rutas, comando=comando, dialecto=dialecto,
        agente=payload.get("agent_type"), id_agente=payload.get("agent_id"),
        sesion=payload.get("session_id"), cwd=payload.get("cwd"),
    )


def leer(payload, pre_por_defecto=False):
    if not isinstance(payload, dict):
        return None
    nombre = payload.get("hook_event_name", "PreToolUse" if pre_por_defecto else None)
    if not isinstance(nombre, str):
        return None
    if nombre in FASES:
        return _herramienta(payload, FASES[nombre])
    if nombre == "SessionStart":
        return InicioSesion(origen=payload.get("source"), sesion=payload.get("session_id"), cwd=payload.get("cwd"))
    if nombre == "SubagentStop":
        return FinSubagente(
            agente=payload.get("agent_type"), id_agente=payload.get("agent_id"), sesion=payload.get("session_id"),
            cwd=payload.get("cwd"), transcript=payload.get("agent_transcript_path"),
            ultimo_mensaje=payload.get("last_assistant_message"), ya_reintentado=payload.get("stop_hook_active") is True,
        )
    return None


def _limpio(texto):
    return texto.encode("utf-8", "replace").decode("utf-8")


def _contexto(nombre, texto):
    return 0, json.dumps({"hookSpecificOutput": {"hookEventName": nombre, "additionalContext": _limpio(texto)}}), b""


def _bloqueo(fase, motivo):
    motivo = _limpio(motivo)
    if fase == "pre":
        return 0, json.dumps({"hookSpecificOutput": {"hookEventName": NOMBRES[fase], "permissionDecision": "deny",
                                                     "permissionDecisionReason": motivo}}), b""
    return 0, json.dumps({"decision": "block", "reason": motivo}), b""


def responder(evento, decision):
    if isinstance(evento, Herramienta):
        if isinstance(decision, Preguntar) and evento.fase == "pre":
            decision = Bloquear(decision.motivo + "\n" + SIN_CONFIRMACION)
        if isinstance(decision, Bloquear):
            return _bloqueo(evento.fase, decision.motivo)
        if isinstance(decision, Contexto) and evento.fase == "post":
            return _contexto(NOMBRES[evento.fase], decision.texto)
    elif isinstance(evento, InicioSesion) and isinstance(decision, Contexto):
        return _contexto("SessionStart", decision.texto)
    elif isinstance(evento, FinSubagente) and isinstance(decision, Seguir):
        return 0, json.dumps({"decision": "block", "reason": _limpio(decision.motivo)}), b""
    return SILENCIO


def atender(crudo, decidir, pre_por_defecto=False):
    return base.atender(leer, responder, crudo, decidir, pre_por_defecto)


def archivos_del_writer(evento, fotos):
    return archivos_de_la_bitacora(fotos)


def comandos_del_writer(evento, fotos):
    return comandos_de_la_bitacora(fotos)
