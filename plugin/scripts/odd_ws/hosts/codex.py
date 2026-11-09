import hashlib
import json
import os
import re

from odd_ws import capas
from odd_ws.capacidades import DEGRADADO, FIN_SUBAGENTE, INICIO, POST, PRE, SOPORTADO
from odd_ws.comun import SILENCIO, archivos_de_la_bitacora, comandos_de_la_bitacora
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, FinSubagente, Herramienta, InicioSesion, Preguntar, Seguir
from odd_ws.hosts import Archivo, base

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
    "P7": (DEGRADADO, "agentes TOML en .codex/agents (name, description y developer_instructions), derivados del .md de "
                      ".claude/agents, que es la fuente, y generados solo si la instancia declara codex en hosts; sin lista "
                      "de herramientas ni skills precargadas: las del frontmatter van escritas en developer_instructions, el "
                      "agente lee los SKILL.md por la shell y el límite de herramientas es solo de texto. Codex carga "
                      ".codex/ solo con el proyecto en confianza ([projects] de ~/.codex/config.toml)"),
    "P8": (DEGRADADO, "skills del plugin (SKILL.md), pero no respeta disable-model-invocation; el equivalente es "
                      "agents/openai.yaml con allow_implicit_invocation: false"),
    "P9": (SOPORTADO, ".codex-plugin/plugin.json apunta a hooks/hooks.codex.json, con cada comando como texto, la ruta de "
                      "PLUGIN_ROOT entre comillas y --host codex; los hooks necesitan confianza en /hooks, que se pide de "
                      "nuevo con cada actualización"),
    "P10": (DEGRADADO, "CLAUDE.md por project_doc_fallback_filenames en .codex/config.toml, que el bootstrap genera si la "
                       "instancia declara codex en hosts y el archivo no existe, sin ningún AGENTS.md; se lee desde la raíz "
                       "hasta el cwd, solo al arrancar y con un tope de 32 KiB, y .codex/ carga solo con el proyecto en "
                       "confianza"),
}
TEXTOS = {
    "{{host:arranque-writer}}": (
        "Las skills `criterios` y `capa-{{capa}}` no vienen precargadas en tu contexto: antes de escribir, abre\n"
        "y lee entero el `SKILL.md` de cada una con la herramienta de shell (`.claude/skills/<skill>/SKILL.md`, desde\n"
        "la raíz de la instancia: la carpeta que tiene `workspace.config.json`). Si alguno no está en el disco, no\n"
        "escribes código: cierras con `estado: blocked` y `regla: falta la skill <skill>`."),
    "{{host:arranque-revisor}}": (
        "Las skills `criterios` y `capa-{{capa}}` no vienen precargadas en tu contexto: antes de revisar, abre\n"
        "y lee entero el `SKILL.md` de cada una con la herramienta de shell (`.claude/skills/<skill>/SKILL.md`, desde\n"
        "la raíz de la instancia: la carpeta que tiene `workspace.config.json`). Si alguno no está en el disco, no\n"
        "revisas: lo dices en el reporte y no inventas criterios."),
    "{{host:arranque-revisor-diseno}}": (
        "La skill `criterios` no viene precargada en tu contexto: antes de revisar, abre y lee entero\n"
        "`.claude/skills/criterios/SKILL.md` con la herramienta de shell, desde la raíz de la instancia (la carpeta que\n"
        "tiene `workspace.config.json`). Si no está en el disco, no revisas: lo dices en el reporte y no inventas\n"
        "criterios."),
    "{{host:en-contexto}}": "están en la skill que leíste al arrancar",
    "{{host:edicion}}": "`apply_patch`",
    "{{host:shell}}": "La herramienta de shell (en Windows corre PowerShell)",
    "{{host:por-shell}}": "por la shell",
    "{{host:origen-de-archivos}}": "de la bitácora que anota el guard",
    "{{host:solo-lees}}": ("No tienes herramienta de lectura: lees con la herramienta de shell (en Windows corre PowerShell),\n"
                           "  solo con comandos que no escriben. No usas `apply_patch`, no escribes y no cambias el árbol de git."),
    "{{host:leida-con}}": "leída con la herramienta de shell",
    "{{host:la-busqueda}}": "el comando de búsqueda",
}
CONFIG_DEL_PROYECTO = 'project_doc_fallback_filenames = ["CLAUDE.md"]\n'
NOMBRE_DE_AGENTE = re.compile(r"[a-z0-9][a-z0-9-]*")
ENCABEZADO = "# Lo genera odd-ws desde %s, que es la fuente: los cambios van en ese .md, no acá."
CLAVE_VERSION = "# odd-ws-plantilla:"
CLAVE_HASH = "# odd-ws-hash:"
HERRAMIENTAS = ("**Herramientas de este agente:** %s. Son los nombres de Claude Code, y Codex no tiene una lista de "
                "herramientas por agente, así que el límite lo pones tú: Read, Glob y Grep son lecturas con la herramienta de "
                "shell; Edit y Write, `apply_patch`; y Bash, la herramienta de shell, que en Windows corre PowerShell. Lo que "
                "no está en esta lista no lo usas.")
SKILLS = "**Skills de este agente:** %s. Las rutas son desde la raíz de la instancia."
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


def _escapar(texto, multilinea=False):
    salida = []
    for letra in texto:
        codigo = ord(letra)
        if letra in '"\\':
            salida.append("\\" + letra)
        elif letra == "\t" or (letra == "\n" and multilinea):
            salida.append(letra)
        elif codigo < 0x20 or codigo == 0x7f:
            salida.append("\\u%04x" % codigo)
        elif 0xd800 <= codigo <= 0xdfff:
            salida.append("�")
        else:
            salida.append(letra)
    return "".join(salida)


def _enumerar(partes):
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def _con_texto(valor, clave):
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError("el agente necesita %s no vacío para su TOML de Codex" % clave)
    return valor


def huella(texto):
    lineas = texto.lstrip("﻿").replace("\r\n", "\n").split("\n")
    esqueleto, en_cabecera = [], True
    for linea in lineas:
        en_cabecera = en_cabecera and linea.startswith("#")
        esqueleto.append(CLAVE_HASH if en_cabecera and linea.startswith(CLAVE_HASH) else linea)
    return hashlib.sha256("\n".join(esqueleto).encode("utf-8", "surrogatepass")).hexdigest()


def toml(agente):
    nombre = agente.nombre
    if not isinstance(nombre, str) or not NOMBRE_DE_AGENTE.fullmatch(nombre):
        raise ValueError("el nombre de agente %r no sirve para %s" % (nombre, capas.CODEX_AGENTES))
    descripcion = _con_texto(agente.descripcion, "una description")
    partes = []
    if agente.herramientas:
        partes.append(HERRAMIENTAS % ", ".join(agente.herramientas))
    if agente.skills:
        partes.append(SKILLS % _enumerar(["`%s`" % capas.skill_de(skill) for skill in agente.skills]))
    partes.append(_con_texto(agente.instrucciones, "instrucciones"))
    lineas = [
        ENCABEZADO % capas.agente(nombre),
        CLAVE_VERSION if agente.version is None else "%s %s" % (CLAVE_VERSION, agente.version),
        CLAVE_HASH,
        'name = "%s"' % _escapar(nombre),
        'description = "%s"' % _escapar(descripcion),
        'developer_instructions = """',
        _escapar("\n\n".join(partes), multilinea=True),
        '"""',
        "",
    ]
    texto = "\n".join(lineas)
    return texto.replace("\n%s\n" % CLAVE_HASH, "\n%s %s\n" % (CLAVE_HASH, huella(texto)), 1)


def archivos(agentes):
    derivados = [Archivo(capas.agente_codex(agente.nombre), toml(agente), capas.agente(agente.nombre)) for agente in agentes]
    return derivados + [Archivo(capas.CODEX_CONFIG, CONFIG_DEL_PROYECTO)]
