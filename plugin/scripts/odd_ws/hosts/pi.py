import hashlib
import json
import ntpath
import os
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from odd_ws import capas
from odd_ws.capacidades import DEGRADADO, FIN_SUBAGENTE, INICIO, NO_DISPONIBLE, POST, PRE, SOPORTADO
from odd_ws.comun import SILENCIO, archivos_de_la_bitacora, comandos_de_la_bitacora
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, FinSubagente, Herramienta, InicioSesion, Preguntar, Seguir
from odd_ws.hosts import Archivo, base, leer_hooks, manejadores

cargar = base.cargar
EXPRESABLES = {PRE: (Bloquear, Preguntar), POST: (Bloquear, Contexto), INICIO: (Contexto,), FIN_SUBAGENTE: (Seguir,)}
DEGRADACIONES = {PRE: {Preguntar: Bloquear}}
BITACORA = True
PRECARGA_SKILLS = False
MANIFIESTO = {
    "P1": (SOPORTADO, "session_start (startup, reload, new, resume y fork) y session_compact: el adaptador los pasa a los orígenes "
                      "de verificar_capa (new es clear; reload es resume, porque recarga las extensiones sin perder la "
                      "conversación; y session_compact es compact) y responde la acción contexto por JSON con exit 0, que el shim "
                      "de F2b suma una vez a systemPromptOptions.appendSystemPrompt en before_agent_start, donde lo ven Pi y los "
                      "puentes de proveedor, y al systemPrompt solo si otra extensión ya lo forzó"),
    "P2": (SOPORTADO, "tool_call de edit y write: la acción bloquear por JSON con exit 0, que el shim de F2b devuelve como block "
                      "(un error del shim también bloquea); una ruta por llamada, resuelta como Pi: sin la @ inicial, con ~ "
                      "expandido, en Windows las rutas de Git Bash pasan a su unidad, y las relativas van contra el cwd"),
    "P3": (DEGRADADO, "tool_call de bash (POSIX en todas las plataformas: en Windows es Git Bash) y de powershell: la acción "
                      "bloquear por JSON con exit 0; preguntar sale como la acción preguntar, que el shim de F2b confirma con "
                      "ctx.ui.confirm, solo si ctx.hasUI es true: sin pantalla, o con hasUI ausente o raro, se degrada a bloquear, "
                      "con el motivo y el pedido de que el usuario corra el comando"),
    "P4": (SOPORTADO, "tool_result de edit, write y read: las acciones bloquear y contexto por JSON con exit 0, que el shim de F2b "
                      "pone en el resultado de la herramienta; read es la lectura, y grep, find y ls no, como Glob y Grep en "
                      "Claude Code"),
    "P5": (DEGRADADO, "solo en gentle-shell, dentro del proceso hijo: el shim corre writer_stop en agent_before_settle si el hijo "
                      "es un writer marcado (P6) y el cierre es completed, con los archivos y los comandos de la bitácora de writer_guard, y la acción "
                      "seguir vuelve como una entrada custom_message y continue: true, una sola vez por cierre; si la compuerta "
                      "misma falla (el shim o Python), el writer cierra, como con un SubagentStop que no corre en Claude Code; "
                      "sin probar en un Pi real hasta F2g; con Pi a secas no hay subagent_run ni hijos, y un writer queda sin "
                      "compuerta"),
    "P6": (DEGRADADO, "ni Pi ni gentle-shell le pasan al hijo el nombre del agente: la extensión del padre lo pone en la tarea "
                      "de subagent_run (una marca en su última línea), borra las marcas que haya escrito el modelo y bloquea "
                      "el lanzamiento de un writer que no puede marcar; el hijo (GENTLE_PI_AGENTS_CHILD=1) la lee del primer "
                      "mensaje del usuario de su sesión y la fija en memoria, con su id de sesión como id del agente, y la manda "
                      "en oddWs; con Pi a secas no hay subagent_run y todo corre como el agente principal; el rodeo se borra "
                      "cuando gentle-shell pase el nombre al hijo"),
    "P7": (DEGRADADO, "los agentes de gentle-shell son .pi/agents/<nombre>.md, derivados del .md de .claude/agents, que es la "
                      "fuente, y generados solo si la instancia declara pi en hosts: name, description y tools en el frontmatter, "
                      "y de cuerpo el del .md con los textos de Pi; las herramientas son las del frontmatter pasadas a las de Pi "
                      "(Read a read, Glob a find, Grep a grep, Edit a edit, Write a write, Bash a bash y PowerShell a "
                      "powershell), que gentle-shell le da al hijo con --tools; sin skills precargadas: el agente abre sus SKILL.md "
                      "con read al arrancar; sin model, thinking ni mode, así que rigen los de subagents.json; gentle-shell lee "
                      "solo <cwd>/.pi/agents y no sube a los padres, así que se abre en la raíz de la instancia; con Pi a secas no "
                      "hay subagentes"),
    "P8": (NO_DISPONIBLE, "las skills del plugin no llegan a Pi hasta que su paquete las traiga por la clave pi de package.json, en "
                          "F2f (Pi las carga sin namespace y respeta disable-model-invocation); las de la instancia sí llegan: Pi "
                          "no lee .claude/skills, así que la extensión las publica por resources_discover con la carpeta "
                          ".claude/skills de la raíz de la instancia (la más cercana que tiene workspace.config.json, subiendo "
                          "desde el cwd), y Pi carga las que traen description en su frontmatter, como las que genera el bootstrap"),
    "P9": (NO_DISPONIBLE, "el paquete de Pi (la clave pi de package.json, que se instala con gentle-shell install y no tiene "
                          "PLUGIN_ROOT) llega en F2f; el shim (shim/pi.ts) y sus hooks (hooks/hooks.pi.json) ya están desde F2b, "
                          "y el shim saca la raíz del plugin de su propia carpeta"),
    "P10": (DEGRADADO, "Pi lee un archivo de instrucciones por carpeta, desde el cwd hasta la raíz y solo al arrancar: el primero "
                       "que encuentra de AGENTS.override.md, AGENTS.md y CLAUDE.md, así que un AGENTS.md tapa el CLAUDE.md de su "
                       "carpeta, y los de las subcarpetas que se tocan después no se cargan; no se genera nada"),
}
TEXTOS = {
    "{{host:arranque-writer}}": (
        "Las skills `criterios` y `capa-{{capa}}` no vienen precargadas en tu contexto: antes de escribir, abre\n"
        "y lee entero el `SKILL.md` de cada una con `read` (`.claude/skills/<skill>/SKILL.md`, desde la raíz de la\n"
        "instancia: la carpeta que tiene `workspace.config.json`). Si alguno no está en el disco, no escribes\n"
        "código: cierras con `estado: blocked` y `regla: falta la skill <skill>`."),
    "{{host:arranque-revisor}}": (
        "Las skills `criterios` y `capa-{{capa}}` no vienen precargadas en tu contexto: antes de revisar, abre\n"
        "y lee entero el `SKILL.md` de cada una con `read` (`.claude/skills/<skill>/SKILL.md`, desde la raíz de la\n"
        "instancia: la carpeta que tiene `workspace.config.json`). Si alguno no está en el disco, no revisas: lo\n"
        "dices en el reporte y no inventas criterios."),
    "{{host:arranque-revisor-diseno}}": (
        "La skill `criterios` no viene precargada en tu contexto: antes de revisar, abre y lee entero\n"
        "`.claude/skills/criterios/SKILL.md` con `read`, desde la raíz de la instancia (la carpeta que tiene\n"
        "`workspace.config.json`). Si no está en el disco, no revisas: lo dices en el reporte y no inventas\n"
        "criterios."),
    "{{host:en-contexto}}": "están en la skill que leíste al arrancar",
    "{{host:edicion}}": "`edit` o `write`",
    "{{host:shell}}": "`bash` (en Windows corre Git Bash)",
    "{{host:por-shell}}": "por `bash`",
    "{{host:origen-de-archivos}}": "de la bitácora que anota el guard",
    "{{host:solo-lees}}": ("Tus herramientas son `read`, `grep` y `find`: no editas, no escribes, no corres comandos y no\n"
                           "  cambias el árbol de git."),
    "{{host:leida-con}}": "leída con `read`, `grep` o `find`",
    "{{host:la-busqueda}}": "el `grep` o el `find`",
}
MEMORIAS = (NO_DISPONIBLE, "la memoria en archivos de Claude Code no aplica en Pi; Pi 1.5.2 no documenta una memoria en archivos que "
                           "memorias.py pueda leer, y si gentle-shell trae la suya no se miró: es un supuesto a verificar, y la "
                           "fuente que queda es engram, si está")
SIN_PANTALLA = ("Esta sesión de Pi no tiene pantalla para pedir confirmación, así que este comando queda bloqueado: si hace "
                "falta, pídele al usuario que lo corra él.")
SIN_DOCTOR = "no se revisa: el doctor de Pi (la versión de pi y el paquete instalado en el home activo) llega en F2e"
SIN_AGENTES = ("no se revisa: desde F2d el bootstrap genera los .pi/agents desde el .md de .claude/agents, pero el chequeo que los "
               "compara con su .md y deriva los que faltan llega en F2e")
ENCABEZADO = "# Lo genera odd-ws desde %s, que es la fuente: los cambios van en ese .md, no acá."
CLAVE_VERSION = "# odd-ws-plantilla:"
CLAVE_HASH = "# odd-ws-hash:"
DELIMITADOR = "---"
NOMBRE_DE_AGENTE = re.compile(r"[a-z0-9][a-z0-9-]*")
HERRAMIENTAS = {"Read": "read", "Glob": "find", "Grep": "grep", "Edit": "edit", "Write": "write", "Bash": "bash",
                "PowerShell": "powershell"}
ESPACIOS_DE_JS = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f"
                  "\u205f\u3000\ufeff")
FIN_DE_LINEA_DE_JS = re.compile("[\r\n\u2028\u2029]")
SURROGATE = re.compile("[\ud800-\udfff]")
FASES = {"tool_call": "pre", "tool_result": "post"}
INICIOS = ("session_start", "session_compact")
FIN = "agent_before_settle"
TIPOS = {"edit": "edicion", "write": "edicion", "read": "lectura", "bash": "shell", "powershell": "shell"}
DIALECTOS = {"bash": POSIX, "powershell": POWERSHELL}
ORIGENES = {"new": "clear", "reload": "resume"}
SISTEMA = os.name
ESPACIOS = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")
RUTA_DE_GIT_BASH = re.compile("/(?:mnt/|cygdrive/)?([a-z])(?:/([^\n\r\u2028\u2029]*))?", re.IGNORECASE | re.ASCII)
UNIDAD = re.compile(r"/?([a-z])[:|]", re.IGNORECASE | re.ASCII)
CONTROL_O_ESPACIO = "".join(map(chr, range(0x21)))
TAB_O_SALTO = re.compile("[\t\n\r]")
ID_VERSION = "pi"
ID_AGENTES = "pi-agentes"
ARCHIVO_DE_HOOKS = "hooks/hooks.pi.json"
PYTHON = "python3"
PYTHON_EN_WINDOWS = "python"
CLAVE_PYTHON = "python"
CLAVE_PYTHON_EN_WINDOWS = "pythonWindows"


def _en_windows():
    return SISTEMA == "nt"


def _camino():
    return ntpath if _en_windows() else posixpath


def _de_git_bash(ruta):
    if not ruta.startswith("/") or ruta.startswith("//") or "\\" in ruta:
        return ruta
    encontrada = RUTA_DE_GIT_BASH.fullmatch(ruta)
    if encontrada is None:
        return ruta
    return "%s:\\%s" % (encontrada.group(1).upper(), (encontrada.group(2) or "").replace("/", "\\"))


def _de_url(ruta):
    ruta = TAB_O_SALTO.sub("", ruta.strip(CONTROL_O_ESPACIO)).replace("\\", "/")
    partes = urlsplit(ruta)
    servidor, camino = partes.netloc.lower(), partes.path
    if UNIDAD.fullmatch(servidor):
        servidor, camino = "", "/" + servidor + camino
    servidor = "" if servidor == "localhost" else servidor
    camino = unquote(camino)
    if not _en_windows():
        return camino
    if servidor:
        return "\\\\" + servidor + camino.replace("/", "\\")
    unidad = UNIDAD.match(camino)
    if unidad:
        return unidad.group(1).upper() + ":" + camino[unidad.end():].replace("/", "\\")
    return camino.replace("/", "\\")


def _normal(ruta, de_la_herramienta):
    if de_la_herramienta:
        ruta = ESPACIOS.sub(" ", ruta)
        ruta = ruta[1:] if ruta.startswith("@") else ruta
    if _en_windows():
        ruta = _de_git_bash(ruta)
    if ruta == "~":
        return os.path.expanduser("~")
    if ruta.startswith("~/") or (_en_windows() and ruta.startswith("~\\")):
        return _camino().join(os.path.expanduser("~"), ruta[2:])
    if ruta.startswith("file://"):
        return _de_url(ruta)
    return ruta


def resolver(ruta, cwd):
    ruta = _normal(ruta, True)
    if not isinstance(cwd, str) or not cwd:
        return ruta
    resuelta = _camino().normpath(_camino().join(_normal(cwd, False), ruta))
    return resuelta if _en_windows() or not resuelta.startswith("//") else "/" + resuelta.lstrip("/")


def _objeto(valor):
    return valor if isinstance(valor, dict) else {}


def _herramienta(payload, fase):
    nombre = payload.get("toolName")
    nombre = nombre if isinstance(nombre, str) else None
    entrada, contexto, identidad = _objeto(payload.get("input")), _objeto(payload.get("ctx")), _objeto(payload.get("oddWs"))
    tipo = TIPOS.get(nombre, "otra")
    ruta, comando = entrada.get("path"), entrada.get("command")
    con_ruta = tipo in ("edicion", "lectura") and isinstance(ruta, str) and ruta
    return Herramienta(
        fase=fase, tipo=tipo, herramienta=nombre, rutas=(resolver(ruta, contexto.get("cwd")),) if con_ruta else (),
        comando=comando if tipo == "shell" and isinstance(comando, str) else None, dialecto=DIALECTOS.get(nombre),
        agente=identidad.get("agent"), id_agente=identidad.get("agentId"),
        sesion=contexto.get("sessionId"), cwd=contexto.get("cwd"),
    )


def leer(payload, pre_por_defecto=False):
    if not isinstance(payload, dict):
        return None
    tipo = payload.get("type", "tool_call" if pre_por_defecto else None)
    if not isinstance(tipo, str):
        return None
    if tipo in FASES:
        return _herramienta(payload, FASES[tipo])
    contexto = _objeto(payload.get("ctx"))
    if tipo in INICIOS:
        razon = "compact" if tipo == "session_compact" else payload.get("reason")
        return InicioSesion(origen=ORIGENES.get(razon, razon) if isinstance(razon, str) else razon,
                            sesion=contexto.get("sessionId"), cwd=contexto.get("cwd"))
    if tipo == FIN:
        identidad = _objeto(payload.get("oddWs"))
        return FinSubagente(
            agente=identidad.get("agent"), id_agente=identidad.get("agentId"), sesion=contexto.get("sessionId"),
            cwd=contexto.get("cwd"), ultimo_mensaje=identidad.get("lastAssistantMessage"),
            ya_reintentado=identidad.get("continued") is True,
        )
    return None


def con_pantalla(payload):
    contexto = payload.get("ctx") if isinstance(payload, dict) else None
    return isinstance(contexto, dict) and contexto.get("hasUI") is True


def _limpio(texto):
    return texto.encode("utf-8", "replace").decode("utf-8")


def _accion(accion, texto):
    return 0, json.dumps({"accion": accion, "texto": _limpio(texto)}), b""


def responder(evento, decision, pantalla=False):
    if isinstance(evento, Herramienta):
        if isinstance(decision, Preguntar) and evento.fase == "pre":
            if pantalla:
                return _accion("preguntar", decision.motivo)
            decision = Bloquear(decision.motivo + "\n" + SIN_PANTALLA)
        if isinstance(decision, Bloquear):
            return _accion("bloquear", decision.motivo)
        if isinstance(decision, Contexto) and evento.fase == "post":
            return _accion("contexto", decision.texto)
    elif isinstance(evento, InicioSesion) and isinstance(decision, Contexto):
        return _accion("contexto", decision.texto)
    elif isinstance(evento, FinSubagente) and isinstance(decision, Seguir):
        return _accion("seguir", decision.motivo)
    return SILENCIO


def atender(crudo, decidir, pre_por_defecto=False):
    pantallas = []

    def leer_y_mirar_la_pantalla(payload, pre_por_defecto=False):
        pantallas.append(con_pantalla(payload))
        return leer(payload, pre_por_defecto)

    def responder_con_la_pantalla(evento, decision):
        return responder(evento, decision, pantallas[-1])

    return base.atender(leer_y_mirar_la_pantalla, responder_con_la_pantalla, crudo, decidir, pre_por_defecto)


def archivos_del_writer(evento, fotos):
    return archivos_de_la_bitacora(fotos)


def comandos_del_writer(evento, fotos):
    return comandos_de_la_bitacora(fotos)


def _con_texto(valor, clave):
    if not isinstance(valor, str) or not valor.strip(ESPACIOS_DE_JS):
        raise ValueError("el agente necesita %s para su .md de Pi" % clave)
    return SURROGATE.sub("\ufffd", valor)


def _herramientas(agente):
    propias = []
    for herramienta in agente.herramientas or ():
        de_pi = HERRAMIENTAS.get(herramienta)
        if de_pi is None:
            raise ValueError("la herramienta %r de %s no tiene equivalente en Pi" % (herramienta, capas.agente(agente.nombre)))
        if de_pi not in propias:
            propias.append(de_pi)
    return propias


def huella(texto):
    lineas = texto.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    esqueleto, en_cabecera = [], lineas[0] == DELIMITADOR
    for indice, linea in enumerate(lineas):
        en_cabecera = en_cabecera and (indice == 0 or linea.startswith("#"))
        esqueleto.append(CLAVE_HASH if en_cabecera and linea.startswith(CLAVE_HASH) else linea)
    return hashlib.sha256("\n".join(esqueleto).encode("utf-8", "surrogatepass")).hexdigest()


def md(agente):
    nombre = agente.nombre
    if not isinstance(nombre, str) or not NOMBRE_DE_AGENTE.fullmatch(nombre):
        raise ValueError("el nombre de agente %r no sirve para %s" % (nombre, capas.PI_AGENTES))
    descripcion = FIN_DE_LINEA_DE_JS.sub(" ", _con_texto(agente.descripcion, "una description no vacía"))
    cuerpo = _con_texto(agente.instrucciones, "instrucciones no vacías")
    herramientas = _herramientas(agente)
    lineas = [
        DELIMITADOR,
        ENCABEZADO % capas.agente(nombre),
        CLAVE_VERSION if agente.version is None else "%s %s" % (CLAVE_VERSION, agente.version),
        CLAVE_HASH,
        "name: %s" % nombre,
        'description: "%s"' % descripcion,
        *(["tools: %s" % ", ".join(herramientas)] if herramientas else []),
        DELIMITADOR,
        cuerpo,
        "",
    ]
    texto = "\n".join(lineas)
    return texto.replace("\n%s\n" % CLAVE_HASH, "\n%s %s\n" % (CLAVE_HASH, huella(texto)), 1)


def archivos(agentes):
    return [Archivo(capas.agente_pi(agente.nombre), md(agente), capas.agente(agente.nombre), ID_AGENTES) for agente in agentes]


def version(ctx, nucleo):
    return nucleo.resultado(ID_VERSION, nucleo.AVISO, SIN_DOCTOR), False


def chequeos(ctx, raiz, nucleo, cli):
    return [] if raiz is None else [nucleo.resultado(ID_AGENTES, nucleo.AVISO, SIN_AGENTES)]


def _tokens(manejador, python, plugin):
    script = manejador.get("script") if isinstance(manejador, dict) else None
    argumentos = manejador.get("args") if isinstance(manejador, dict) else None
    if not isinstance(script, str) or not isinstance(argumentos, list) or not all(isinstance(argumento, str) for argumento in argumentos):
        return None
    return [python, str(Path(plugin) / "scripts" / script), *argumentos]


def hooks_registrados(ctx, raiz):
    datos = leer_hooks(Path(ctx.plugin) / ARCHIVO_DE_HOOKS)
    python = datos.get(CLAVE_PYTHON_EN_WINDOWS if ctx.windows else CLAVE_PYTHON) if datos is not None else None
    if not isinstance(python, str) or not python:
        yield ARCHIVO_DE_HOOKS, None, True
        return
    for evento, grupo, indice, manejador in manejadores(datos):
        yield "%s %s[%d][%d]" % (ARCHIVO_DE_HOOKS, evento, grupo, indice), _tokens(manejador, python, ctx.plugin), True
