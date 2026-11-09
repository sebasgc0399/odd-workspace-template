import json

from odd_ws import transcripcion
from odd_ws.capacidades import FIN_SUBAGENTE, INICIO, POST, PRE, SOPORTADO
from odd_ws.comun import SILENCIO
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, FinSubagente, Herramienta, InicioSesion, Preguntar, Seguir
from odd_ws.hosts import base

cargar = base.cargar
EXPRESABLES = {PRE: (Bloquear, Preguntar), POST: (Bloquear, Contexto), INICIO: (Contexto,), FIN_SUBAGENTE: (Seguir,)}
DEGRADACIONES = {}
BITACORA = False
MANIFIESTO = {
    "P1": (SOPORTADO, "SessionStart con additionalContext en startup, resume, compact y clear"),
    "P2": (SOPORTADO, "PreToolUse de Edit y Write: exit 2 con el motivo en stderr"),
    "P3": (SOPORTADO, "PreToolUse de Bash y PowerShell: exit 2, o permissionDecision ask"),
    "P4": (SOPORTADO, "PostToolUse de Edit, Write y Read: exit 2 o additionalContext"),
    "P5": (SOPORTADO, "SubagentStop con matcher por agent_type y decision block"),
    "P6": (SOPORTADO, "agent_type y agent_id dentro de un subagente"),
    "P7": (SOPORTADO, ".claude/agents con tools y skills precargadas"),
    "P8": (SOPORTADO, "skills del plugin con el namespace /odd-ws:"),
    "P9": (SOPORTADO, "marketplace y CLAUDE_PLUGIN_ROOT"),
    "P10": (SOPORTADO, "CLAUDE.md que se apilan por carpeta"),
}
FASES = {"PreToolUse": "pre", "PostToolUse": "post"}
NOMBRES = {fase: nombre for nombre, fase in FASES.items()}
TIPOS = {"Edit": "edicion", "Write": "edicion", "MultiEdit": "edicion", "Read": "lectura", "Bash": "shell",
         "PowerShell": "shell"}
DIALECTOS = {"Bash": POSIX, "PowerShell": POWERSHELL}
HERRAMIENTAS_DE_ESCRITURA = ("Edit", "Write", "MultiEdit")
HERRAMIENTAS_DE_SHELL = ("Bash", "PowerShell")
TEXTOS = {
    "{{host:arranque-writer}}": (
        "Tu contexto trae precargadas `criterios` y `capa-{{capa}}`. Si NO está la\n"
        "línea `CENTINELA criterios` o la línea `CENTINELA capa-{{capa}}` (cada una suelta, seguida de una fecha,\n"
        "fuera de este párrafo), lee la skill que falte con Read (`.claude/skills/<skill>/SKILL.md`, desde la raíz\n"
        "de la instancia: la carpeta que tiene `workspace.config.json`) antes de escribir, y avísalo en la PRIMERA\n"
        "línea de tu último mensaje: «<skill> no venía precargada; la leí del disco». Si tampoco está en el disco,\n"
        "no escribes código: cierras con `estado: blocked` y `regla: falta la skill <skill>`."),
    "{{host:arranque-revisor}}": (
        "Tu contexto trae precargadas `criterios` y `capa-{{capa}}`. Si NO está la\n"
        "línea `CENTINELA criterios` o la línea `CENTINELA capa-{{capa}}` (cada una suelta, seguida de una fecha,\n"
        "fuera de este párrafo), lee la skill que falte con Read (`.claude/skills/<skill>/SKILL.md`, desde la raíz\n"
        "de la instancia: la carpeta que tiene `workspace.config.json`) antes de revisar, y avísalo en la PRIMERA\n"
        "línea de tu reporte: «<skill> no venía precargada; la leí del disco». Si tampoco está en el disco, no\n"
        "revisas: lo dices en el reporte y no inventas criterios."),
    "{{host:arranque-revisor-diseno}}": (
        "Tu contexto trae precargada `criterios`. Si NO está la línea\n"
        "`CENTINELA criterios` (suelta, seguida de una fecha, fuera de este párrafo), lee\n"
        "`.claude/skills/criterios/SKILL.md` con Read, desde la raíz de la instancia (la carpeta que tiene\n"
        "`workspace.config.json`), antes de revisar, y avísalo en la PRIMERA línea de tu reporte: «criterios no venía\n"
        "precargada; la leí del disco». Si tampoco está en el disco, no revisas: lo dices en el reporte y no\n"
        "inventas criterios."),
    "{{host:en-contexto}}": "ya están en tu contexto",
    "{{host:edicion}}": "Edit o Write",
    "{{host:shell}}": "Bash",
    "{{host:por-shell}}": "por Bash",
    "{{host:origen-de-archivos}}": "del transcript",
    "{{host:solo-lees}}": ("Tus herramientas son Read, Glob y Grep: no editas, no escribes, no corres comandos y no\n"
                           "  cambias el árbol de git."),
    "{{host:leida-con}}": "leída con Read, Glob o Grep",
    "{{host:la-busqueda}}": "el Glob o el Grep",
}


def _herramienta(payload, fase):
    nombre = payload.get("tool_name")
    nombre = nombre if isinstance(nombre, str) else None
    entrada = payload.get("tool_input")
    entrada = entrada if isinstance(entrada, dict) else {}
    ruta, comando = entrada.get("file_path"), entrada.get("command")
    return Herramienta(
        fase=fase, tipo=TIPOS.get(nombre, "otra"), herramienta=nombre,
        rutas=(ruta,) if isinstance(ruta, str) and ruta else (),
        comando=comando if isinstance(comando, str) else None, dialecto=DIALECTOS.get(nombre),
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


def _contexto(nombre, texto):
    return 0, json.dumps({"hookSpecificOutput": {"hookEventName": nombre, "additionalContext": texto}}), b""


def responder(evento, decision):
    if isinstance(evento, Herramienta):
        nombre = NOMBRES[evento.fase]
        if isinstance(decision, Bloquear):
            return 2, "", (decision.motivo + "\n").encode("utf-8", "replace")
        if isinstance(decision, Preguntar) and evento.fase == "pre":
            salida = {"hookSpecificOutput": {"hookEventName": nombre, "permissionDecision": "ask",
                                             "permissionDecisionReason": decision.motivo}}
            return 0, json.dumps(salida) + "\n", b""
        if isinstance(decision, Contexto) and evento.fase == "post":
            return _contexto(nombre, decision.texto)
    elif isinstance(evento, InicioSesion) and isinstance(decision, Contexto):
        return _contexto("SessionStart", decision.texto)
    elif isinstance(evento, FinSubagente) and isinstance(decision, Seguir):
        return 0, json.dumps({"decision": "block", "reason": decision.motivo}), b""
    return SILENCIO


def atender(crudo, decidir, pre_por_defecto=False):
    return base.atender(leer, responder, crudo, decidir, pre_por_defecto)


def usos(transcript, herramientas):
    leidos = transcripcion.leer(transcript)
    if leidos is None:
        return None
    entradas = []
    for registro in leidos[0]:
        for bloque in transcripcion.bloques(registro):
            if isinstance(bloque, dict) and bloque.get("type") == "tool_use" and bloque.get("name") in herramientas:
                entrada = bloque.get("input")
                if isinstance(entrada, dict):
                    entradas.append((bloque.get("name"), entrada))
    return entradas


def archivos_tocados(transcript):
    archivos = []
    for _, entrada in usos(transcript, HERRAMIENTAS_DE_ESCRITURA) or []:
        ruta = entrada.get("file_path")
        if isinstance(ruta, str) and ruta and ruta not in archivos:
            archivos.append(ruta)
    return archivos


def comandos_de_shell(transcript):
    encontrados = usos(transcript, HERRAMIENTAS_DE_SHELL)
    if encontrados is None:
        return None
    return [(DIALECTOS[herramienta], entrada["command"]) for herramienta, entrada in encontrados
            if isinstance(entrada.get("command"), str) and entrada["command"]]


def archivos(agentes):
    return []


def archivos_del_writer(evento, fotos):
    return archivos_tocados(evento.transcript), []


def comandos_del_writer(evento, fotos):
    return comandos_de_shell(evento.transcript)
