import json
import os
import re
from pathlib import Path

from odd_ws import transcripcion
from odd_ws.capacidades import FIN_SUBAGENTE, INICIO, POST, PRE, SOPORTADO
from odd_ws.comun import SILENCIO
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, FinSubagente, Herramienta, InicioSesion, Preguntar, Seguir
from odd_ws.hosts import base, leer_hooks, manejadores, tokens_de

cargar = base.cargar
ARCHIVO_DE_HOOKS = "hooks/hooks.json"
PYTHON = "python3"
PYTHON_EN_WINDOWS = "python3"
VERSION_MINIMA = (2, 1, 284)
AYUDA_CLAUDE = "Actualizá Claude Code a 2.1.284 o superior."
VERSION_ON_FAILURE = (2, 1, 295)
AVISO_ON_FAILURE = "un hook que no arranca deja pasar"
AYUDA_ON_FAILURE = ("Actualizá Claude Code a 2.1.295 o superior: desde esa versión, onFailure: block hace que un hook que no arranca "
                    "(por ejemplo, sin python3) bloquee la herramienta en vez de dejarla pasar.")
EXPRESABLES = {PRE: (Bloquear, Preguntar), POST: (Bloquear, Contexto), INICIO: (Contexto,), FIN_SUBAGENTE: (Seguir,)}
DEGRADACIONES = {}
BITACORA = False
PRECARGA_SKILLS = True
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
MEMORIAS = (SOPORTADO, "memoria en archivos: --memorias, autoMemoryDirectory de los settings (local, proyecto y usuario), o "
                       "CLAUDE_CONFIG_DIR (o ~/.claude) con projects/<proyecto>/memory, donde <proyecto> sale de la raíz del repo git")
AUTO_MEMORIA = "autoMemoryDirectory"
NOMBRE_PROPIO = "CLAUDE_CODE_PROJECT_DIR_NAME"
PROYECTOS = "projects"
SETTINGS_DEL_PROYECTO = (".claude/settings.local.json", ".claude/settings.json")
LARGO_MAXIMO_DEL_PROYECTO = 200
NOMBRE_PROPIO_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
DISPOSITIVOS = frozenset(["con", "prn", "aux", "nul"] + ["com%d" % n for n in range(1, 10)] + ["lpt%d" % n for n in range(1, 10)])


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


def version(ctx, nucleo):
    item, instalado = nucleo.chequear_version(ctx, "claude", ["claude", "--version"], VERSION_MINIMA, AYUDA_CLAUDE)
    if item.estado == nucleo.OK and nucleo.leer_version(item.detalle) < VERSION_ON_FAILURE:
        item = item._replace(estado=nucleo.AVISO, detalle=f"{item.detalle}: {AVISO_ON_FAILURE}", ayuda=AYUDA_ON_FAILURE)
    return item, instalado


def chequeos(ctx, raiz, nucleo, cli):
    if cli == nucleo.CLI_DE_OTRO_HOST:
        return [nucleo.resultado("marketplace", nucleo.NO_APLICA, "claude no está instalado")]
    return [_marketplace(ctx, nucleo)]


def _marketplace(ctx, nucleo):
    try:
        datos = json.loads((ctx.home / ".claude" / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = None
    if isinstance(datos, dict) and nucleo.MARKETPLACE in datos:
        return nucleo.resultado("marketplace", nucleo.OK, f"{nucleo.MARKETPLACE} registrado")
    return nucleo.resultado("marketplace", nucleo.FALTA, f"{nucleo.MARKETPLACE} no está registrado",
                            ["claude", "plugin", "marketplace", "add", nucleo.URL_MARKETPLACE])


def hooks_registrados(ctx, raiz):
    datos = leer_hooks(Path(ctx.plugin) / ARCHIVO_DE_HOOKS)
    if datos is None:
        yield ARCHIVO_DE_HOOKS, None, True
        return
    for evento, grupo, indice, manejador in manejadores(datos):
        comando = manejador.get("command") if isinstance(manejador, dict) else None
        if not isinstance(comando, str):
            continue
        argumentos = manejador.get("args")
        if isinstance(argumentos, list) and all(isinstance(argumento, str) for argumento in argumentos):
            tokens = [comando, *argumentos]
        else:
            tokens = tokens_de(comando)
        yield "%s %s[%d][%d]" % (ARCHIVO_DE_HOOKS, evento, grupo, indice), tokens, True


def archivos_del_writer(evento, fotos):
    return archivos_tocados(evento.transcript), []


def comandos_del_writer(evento, fotos):
    return comandos_de_shell(evento.transcript)


def nombre_de_proyecto(ruta):
    return "".join(letra if letra.isascii() and letra.isalnum() else "-" * (2 if ord(letra) > 0xFFFF else 1) for letra in str(ruta))


def _raiz_comun(carpeta, marca):
    try:
        texto = marca.read_text(encoding="utf-8-sig").strip()
    except (OSError, ValueError):
        return carpeta
    if not texto.startswith("gitdir:"):
        return carpeta
    gitdir = os.path.normpath(os.path.join(carpeta, texto[len("gitdir:"):].strip()))
    try:
        comun = Path(gitdir, "commondir").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return carpeta
    comun = Path(os.path.normpath(os.path.join(gitdir, comun)))
    return comun.parent if comun.name == ".git" else carpeta


def raiz_del_proyecto(raiz):
    actual = Path(raiz)
    for carpeta in (actual, *actual.parents):
        marca = carpeta / ".git"
        if marca.is_dir():
            return carpeta
        if marca.is_file():
            return _raiz_comun(carpeta, marca)
    return actual


def carpeta_de_config(entorno, home):
    valor = entorno.get("CLAUDE_CONFIG_DIR")
    return Path(valor) if valor else Path(home) / ".claude"


def _valor_de_settings(ruta):
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return datos.get(AUTO_MEMORIA) if isinstance(datos, dict) else None


def _auto_memoria(entorno, home, raiz):
    candidatos = [Path(raiz) / relativa for relativa in SETTINGS_DEL_PROYECTO] + [carpeta_de_config(entorno, home) / "settings.json"]
    for settings in candidatos:
        valor = _valor_de_settings(settings)
        if valor is None:
            continue
        if isinstance(valor, str) and valor.startswith("~/"):
            return Path(home) / valor[2:], settings
        if isinstance(valor, str) and os.path.isabs(valor):
            return Path(valor), settings
        raise base.SinMemorias("%s %r en %s no es una ruta absoluta ni empieza con ~/: corregilo o pasá --memorias <dir>"
                               % (AUTO_MEMORIA, valor, settings))
    return None


def _nombre_propio(entorno):
    valor = entorno.get(NOMBRE_PROPIO)
    if not entorno.get("CLAUDE_CONFIG_DIR") or not valor or not NOMBRE_PROPIO_RE.fullmatch(valor) or valor.lower() in DISPOSITIVOS:
        return None
    return valor


def _en_disco(proyectos, nombre, windows):
    if not windows:
        return proyectos / nombre
    try:
        iguales = sorted(entrada.name for entrada in os.scandir(proyectos) if entrada.name.lower() == nombre.lower())
    except OSError:
        iguales = []
    return proyectos / (nombre if nombre in iguales or not iguales else iguales[0])


def directorio_de_memorias(entorno, home, raiz, windows, pasado=None):
    if pasado is not None:
        return base.DirectorioDeMemorias(Path(pasado), base.PASADA, "--memorias", None)
    ajuste = _auto_memoria(entorno, home, raiz)
    if ajuste is not None:
        return base.DirectorioDeMemorias(ajuste[0], base.DERIVADA, AUTO_MEMORIA, str(ajuste[1]))
    config = carpeta_de_config(entorno, home)
    propio = _nombre_propio(entorno)
    if propio is not None:
        return base.DirectorioDeMemorias(config / PROYECTOS / propio / "memory", base.DERIVADA, NOMBRE_PROPIO, str(config))
    proyecto = raiz_del_proyecto(raiz)
    nombre = nombre_de_proyecto(proyecto)
    if len(nombre) > LARGO_MAXIMO_DEL_PROYECTO:
        raise base.SinMemorias("la carpeta de %s en %s tendría %d caracteres, más de %d: Claude Code la corta y le agrega un hash "
                               "que no está documentado, así que no se adivina; pasá --memorias <dir>"
                               % (proyecto, config / PROYECTOS, len(nombre), LARGO_MAXIMO_DEL_PROYECTO))
    return base.DirectorioDeMemorias(_en_disco(config / PROYECTOS, nombre, windows) / "memory", base.DERIVADA, PROYECTOS, str(proyecto))
