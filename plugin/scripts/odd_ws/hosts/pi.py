import hashlib
import json
import math
import ntpath
import os
import posixpath
import re
from collections import namedtuple
from pathlib import Path
from urllib.parse import unquote, urlsplit

from odd_ws import capas
from odd_ws.capacidades import DEGRADADO, FIN_SUBAGENTE, INICIO, NO_DISPONIBLE, POST, PRE, SOPORTADO
from odd_ws.comun import SILENCIO, archivos_de_la_bitacora, comandos_de_la_bitacora, plazo_de
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, FinSubagente, Herramienta, InicioSesion, Preguntar, Seguir
from odd_ws.hosts import Archivo, base, codex, leer_hooks, manejadores

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
                      "compuerta, cosa que el doctor avisa en el ítem gentle-shell"),
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
    "P8": (SOPORTADO, "las skills del plugin llegan por el paquete de Pi: pi.skills del package.json de la raíz del repositorio "
                      "apunta a plugin/skills, y Pi carga cada SKILL.md que trae description, sin namespace, con los nombres que "
                      "valida su regla, sin chocar con las de gentle-pi, que se llaman gentle-, y respetando "
                      "disable-model-invocation: esas se invocan solo con /skill:<nombre>, como /skill:bootstrap; sus comandos "
                      "usan ${CLAUDE_PLUGIN_ROOT}, que Pi no define: la define la extensión al registrarse, con la carpeta del "
                      "plugin, si no estaba, y el bash de Pi la hereda; las de la instancia llegan aparte: Pi no lee "
                      ".claude/skills, así que la extensión las publica por resources_discover con la carpeta .claude/skills de "
                      "la raíz de la instancia (la más cercana que tiene workspace.config.json, subiendo desde el cwd), y Pi "
                      "carga las que traen description en su frontmatter, como las que genera el bootstrap; solo con el "
                      "proyecto en confianza, que revisa el ítem pi-confianza del doctor"),
    "P9": (SOPORTADO, "el paquete de Pi es la raíz del repositorio: su package.json (privado, sin dependencias ni scripts) "
                      "declara pi.extensions = ./plugin/shim/pi.ts y pi.skills = ./plugin/skills, y se instala con "
                      "gentle-shell install (o pi install) desde git, con la etiqueta de la versión, o desde la ruta de un clon; "
                      "va en la raíz porque Pi clona el repositorio entero y no admite un paquete en una subcarpeta, y no se "
                      "publica en npm; sin PLUGIN_ROOT: el shim saca la raíz del plugin de su propia carpeta; el ítem pi-plugin "
                      "del doctor decide, con la regla de Pi (las fuentes, el manifiesto pi.extensions, los filtros, autoload y "
                      "el proyecto contra el home), si los packages del home activo y de .pi/settings.json, este solo con "
                      "confianza, cargan shim/pi.ts; sin probar en un Pi real hasta F2g"),
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
VERSION_MINIMA = (1, 5, 0)
VERSION_DE_LA_COMPUERTA = (0, 87, 0)
SIN_COMPUERTA = ("no existe agent_before_settle (CHANGELOG de Pi, 0.87.0: «Added actionable `turn_end` and `agent_before_settle` "
                 "extension boundaries»), así que la compuerta de cierre del writer no corre y el writer cierra sin ella")
USOS = ("odd-ws usa agent_before_settle (desde 0.87.0), appendSystemPrompt de systemPromptOptions en before_agent_start (desde "
        "0.68.0), resources_discover (desde 0.50.8) e isProjectTrusted (desde 0.79.1, y Pi respeta un «Do not trust» guardado recién "
        "desde 1.5.0)")
AYUDA_PI = ("Instalá o actualizá Pi a 1.5.0 o superior (npm i -g @earendil-works/pi-coding-agent), o gentle-shell, que corre el suyo "
            "(npm i -g gentle-pi).")
SIN_GENTLE_SHELL = ("con Pi a secas no hay subagentes, así que un writer corre sin su compuerta de cierre y sin su identidad "
                    "(P5 y P6)")
AYUDA_GENTLE_SHELL = ("Instalá gentle-shell (npm i -g gentle-pi) y abrí la instancia con gentle-shell desde su raíz, que es donde lee "
                      ".pi/agents. Pi a secas también sirve, pero sin writers.")
AYUDA_PAQUETE = ("Instalá el paquete de odd-ws en el home activo, con gentle-shell install <fuente> (o pi install <fuente> con Pi a "
                 "secas): la fuente es git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v<versión>, o la raíz de un clon "
                 "del repositorio, no su carpeta plugin/. odd-ws no está en npm. El doctor no escribe en los homes de Pi.")
AYUDA_SETTINGS = "Arreglalo a mano: tiene que ser un objeto JSON en UTF-8. El doctor no escribe en los homes de Pi."
AYUDA_CONFIANZA = ("Abrí Pi (o gentle-shell) en la raíz de la instancia y confiá en la carpeta con /trust, que guarda la decisión. El "
                   "doctor no escribe en los homes de Pi.")
AYUDA_HOOKS = ("hooks/hooks.pi.json es del plugin: reinstalá o actualizá odd-ws en lugar de editarlo. Si el shim no lo puede leer, "
               "bloquea toda herramienta, y un grupo que no corre deja a su guard sin ver nada.")
AYUDA_AGENTES = ("El .md de .claude/agents es la fuente de su .md de .pi/agents: pasá tu cambio al de .claude/agents (a la "
                 "description o a un bloque <!-- instancia:... -->), sacá el de .pi/agents y corré --arreglar pi-agentes. Si el .md "
                 "se editó fuera de sus bloques, arreglalo primero; el de un agente que ya no existe lo borrás vos.")
SIN_SKILLS = "sin confianza, la extensión no publica las skills de la instancia (.claude/skills) por resources_discover"
CON_CONFIANZA = "que Pi lee solo con el proyecto en confianza"
DEL_GENTLE_SHELL = " (el que corre gentle-shell; pi no está en el PATH)"
RECHAZADO = "el shim no puede leer ese hooks.pi.json, así que bloquea toda herramienta"
SIN_WRITER = ("falta writer, la regex de los writers: el shim no reconoce a ningún writer y bloquea todo lanzamiento de "
              "subagentes")
OTRO_WRITER = ("writer es %r y no %s, la regex de los writers: el shim no los reconocería, y correrían sin su compuerta de "
               "cierre")
ID_GENTLE_SHELL = "gentle-shell"
ID_PLUGIN = "pi-plugin"
ID_CONFIANZA = "pi-confianza"
FORMA = "forma"
SCRIPT_DEL_SHIM = re.compile(r"[A-Za-z0-9_]+\.py")
REGEX_DE_WRITER = "^%s$" % capas.WRITER_RE.pattern
COBERTURA = {
    "session_start": {None: ("verificar_capa.py",)},
    "session_compact": {None: ("verificar_capa.py",)},
    "tool_call": {"edit": ("verificar_capa.py", "writer_guard.py"), "write": ("verificar_capa.py", "writer_guard.py"),
                  "bash": ("writer_guard.py", "guard_comandos.py"), "powershell": ("writer_guard.py", "guard_comandos.py")},
    "tool_result": {"edit": ("verificar_capa.py",), "write": ("verificar_capa.py",), "read": ("verificar_capa.py",)},
    "agent_before_settle": {None: ("writer_stop.py",)},
}
NO_LOCALES = ("npm:", "git:", "github:", "http:", "https:", "ssh:", "builtin:")
CAMPOS_DE_RECURSOS = ("extensions", "skills", "prompts", "themes")
IGNORADOS = (".gitignore", ".ignore", ".fdignore")
CON_ESQUEMA = re.compile(r"(?i)^(?:https?|ssh|git)://")
GIT_SIMPLE = re.compile(r"(?i)^(?:(?:https?|ssh|git)://(?:[^@/]*@)?)?([^/@:]+)/([^/@]+)/([^/@]+?)(?:\.git)?/?(?:@[^/]+)?$")
GIT_SCP = re.compile(r"^git@([^:/]+):([^/@]+)/([^/@]+?)(?:\.git)?(?:@[^/]+)?$")
COMODIN = re.compile(r"[*?]")
FUERA_DE_MINIMATCH = re.compile(r"[\[\]{}()!#\\:]")
DUDOSA = "dudosa"
AUSENTE = "ausente"
DE_ODD_WS = "odd-workspace-template"
NOMBRES_DE_ODD_WS = ("odd-ws", DE_ODD_WS)
FUENTE_GIT = "para Pi, una fuente git empieza con git: o con un esquema como https://"
SIN_MANIFIESTO = "el paquete no trae pi.extensions en su package.json ni una carpeta extensions/, así que Pi no carga shim/pi.ts"
EN_PLUGIN = ("esa es la carpeta plugin/, que no trae el manifiesto: el paquete de Pi es la raíz del repositorio, %s, con el "
             "package.json que carga shim/pi.ts")
POR_NPM = ("odd-ws no se publica en npm, y ese nombre puede ser de otro paquete, así que el doctor no cuenta una fuente npm: se "
           "instala por git, con la etiqueta de su versión, o por la ruta de un clon")
SIN_CLONAR = ("no está clonado en %s; Pi lo clona al arrancar o con gentle-shell install, y corre npm install en el clon, así que "
              "necesita npm en el PATH")
FILTRADO = "el filtro extensions de la entrada deja afuera shim/pi.ts"
SIN_AUTOLOAD = "autoload: false sin patrones en extensions no carga nada del paquete"
INDECIDIBLE = "una entrada que el doctor no sabe leer como Pi"
RECURSOS_CON_CONFIANZA = ("settings.json", "mcp.json", "extensions", "skills", "prompts", "themes", "SYSTEM.md", "APPEND_SYSTEM.md")
SETTINGS = "settings.json"
CONFIANZA = "trust.json"
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
EVENTOS_DE_HERRAMIENTA = tuple(FASES)
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

GentleShell = namedtuple("GentleShell", "ruta codigo salida version pi modo home")


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


def _gentle_shell(ctx, nucleo):
    ruta = ctx.which("gentle-shell")
    codigo, salida = ctx.ejecutar([ruta or "gentle-shell", "--version"])
    lineas = [linea.strip() for linea in (salida or "").splitlines()]

    def tras(prefijo):
        return next((linea[len(prefijo):].strip() for linea in lineas if linea.startswith(prefijo)), None)

    hogar = (tras("home ") or "").split(" ", 1)
    modo, home = hogar if codigo == 0 and len(hogar) == 2 and hogar[1] else (None, None)
    return GentleShell(ruta, codigo, salida, nucleo.leer_version(tras("gentle-shell ")), tras("pi "), modo, home)


def _segun_la_version(numero, nucleo, cual=""):
    texto = nucleo.texto_version(numero) + cual
    if numero < VERSION_DE_LA_COMPUERTA:
        return nucleo.FALTA, f"{texto}, menor que {nucleo.texto_version(VERSION_DE_LA_COMPUERTA)}: {SIN_COMPUERTA}"
    if numero < VERSION_MINIMA:
        return nucleo.AVISO, f"{texto}, menor que {nucleo.texto_version(VERSION_MINIMA)}: {USOS}"
    return nucleo.OK, texto


def _item_de_version(numero, nucleo, cual=""):
    estado, detalle = _segun_la_version(numero, nucleo, cual)
    return nucleo.resultado(ID_VERSION, estado, detalle, None, "" if estado == nucleo.OK else AYUDA_PI)


def _de_gentle_shell(ctx, nucleo, ausente):
    gentle = _gentle_shell(ctx, nucleo)
    if gentle.codigo not in (None, 0):
        primera = nucleo.primera_linea(gentle.salida)[:80] or "(vacío)"
        return ausente._replace(detalle=f"pi no está en el PATH, y gentle-shell --version sale con {gentle.codigo}: {primera}"), False
    numero = nucleo.leer_version(gentle.pi) if gentle.codigo == 0 else None
    if numero is None:
        return ausente, False
    return _item_de_version(numero, nucleo, DEL_GENTLE_SHELL), True


def version(ctx, nucleo):
    ruta = ctx.which("pi")
    resultado, instalado = nucleo.chequear_version(ctx, ID_VERSION, [ruta or "pi", "--version"], VERSION_MINIMA, AYUDA_PI)
    if not instalado and ruta:
        return resultado._replace(detalle=f"{ruta} no se pudo ejecutar"), False
    if not instalado:
        return _de_gentle_shell(ctx, nucleo, resultado)
    if resultado.estado == nucleo.AVISO:
        return resultado, True
    return _item_de_version(nucleo.leer_version(resultado.detalle), nucleo), True


def chequeos(ctx, raiz, nucleo, cli):
    resultados = []
    if cli == nucleo.CLI_INSTALADO:
        gentle = _gentle_shell(ctx, nucleo)
        resultados += [_item_gentle_shell(gentle, nucleo), _paquete(ctx, raiz, nucleo, gentle)]
        if raiz is not None:
            resultados.append(_confianza(ctx, Path(raiz), nucleo, gentle))
    else:
        de_la_maquina = [ID_GENTLE_SHELL, ID_PLUGIN] + ([ID_CONFIANZA] if raiz is not None else [])
        resultados += [nucleo.resultado(id, nucleo.NO_APLICA, "pi no está instalado") for id in de_la_maquina]
    if raiz is not None:
        resultados.append(_agentes(Path(raiz), nucleo))
    return resultados


def _item_gentle_shell(gentle, nucleo):
    id = ID_GENTLE_SHELL
    if gentle.codigo is None:
        quien = f"{gentle.ruta} no se pudo ejecutar" if gentle.ruta else "gentle-shell no está instalado"
        return nucleo.resultado(id, nucleo.AVISO, f"{quien}: {SIN_GENTLE_SHELL}", None, AYUDA_GENTLE_SHELL)
    primera = nucleo.primera_linea(gentle.salida)[:80] or "(vacío)"
    if gentle.codigo != 0:
        return nucleo.resultado(id, nucleo.AVISO, f"gentle-shell --version sale con {gentle.codigo}: {primera}", None, AYUDA_GENTLE_SHELL)
    if gentle.version is None or gentle.home is None:
        return nucleo.resultado(id, nucleo.AVISO, f"no se pudo leer la versión y el home de gentle-shell --version: {primera}", None,
                                AYUDA_GENTLE_SHELL)
    propia = nucleo.texto_version(gentle.version)
    numero = nucleo.leer_version(gentle.pi)
    if numero is None:
        return nucleo.resultado(id, nucleo.AVISO, f"gentle-shell {propia} no encuentra Pi (pi {gentle.pi or '(vacío)'})", None, AYUDA_PI)
    estado, detalle = _segun_la_version(numero, nucleo)
    if estado != nucleo.OK:
        return nucleo.resultado(id, estado, f"gentle-shell {propia} corre pi {detalle}", None, AYUDA_PI)
    return nucleo.resultado(id, nucleo.OK, f"{propia}, con pi {nucleo.texto_version(numero)} y el home {gentle.modo} {gentle.home}")


def _expandida(ctx, valor):
    if valor == "~":
        return Path(ctx.home)
    if valor.startswith("~/") or (ctx.windows and valor.startswith("~\\")):
        return Path(ctx.home) / valor[2:]
    return Path(valor)


def _home_de_pi(ctx):
    valor = ctx.entorno.get("PI_CODING_AGENT_DIR")
    return _expandida(ctx, valor) if valor else Path(ctx.home) / ".pi" / "agent"


def _misma(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _homes(ctx, gentle):
    activo = Path(gentle.home) if gentle.home else _home_de_pi(ctx)
    etiqueta = f"el home activo de gentle-shell, {gentle.modo}" if gentle.home else "el home de Pi"
    otros = [Path(ctx.entorno.get("GENTLE_SHELL_HOME") or Path(ctx.home) / ".gentle-shell" / "agent"), _home_de_pi(ctx)]
    if ctx.entorno.get("GENTLE_PI_AGENT_HOME"):
        otros.append(_expandida(ctx, ctx.entorno["GENTLE_PI_AGENT_HOME"]))
    unicos = []
    for otro in otros:
        if not _misma(otro, activo) and not any(_misma(otro, visto) for visto in unicos):
            unicos.append(otro)
    return activo, etiqueta, unicos


def _objeto_json(ruta):
    if not ruta.is_file():
        return {}, None
    try:
        datos = json.loads(ruta.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as error:
        return None, str(error)
    return (datos, None) if isinstance(datos, dict) else (None, "no es un objeto JSON")


def _paquetes(datos):
    paquetes = datos.get("packages") if isinstance(datos, dict) else None
    if paquetes is None or isinstance(paquetes, str):
        return []
    return paquetes if isinstance(paquetes, list) else None


def _es_un_plugin(carpeta):
    return (carpeta / ARCHIVO_DE_HOOKS).is_file() and (carpeta / "shim" / "pi.ts").is_file()


def _es_shim(archivo):
    return archivo.name == "pi.ts" and archivo.parent.name == "shim" and _es_un_plugin(archivo.parent.parent)


def _de_odd_ws(carpeta):
    return _es_un_plugin(carpeta) or _es_un_plugin(carpeta / "plugin")


def _git(fuente):
    texto = fuente.strip()
    con_prefijo = texto.startswith("git:")
    url = texto[len("git:"):].strip() if con_prefijo else texto
    if not con_prefijo and not CON_ESQUEMA.match(url):
        return None
    encontrada = (GIT_SCP if url.startswith("git@") else GIT_SIMPLE).match(url)
    if encontrada is None:
        return DUDOSA
    anfitrion = encontrada.group(1).lower()
    desnuda = "://" not in url and not url.startswith("git@")
    if anfitrion.startswith("www.") or (desnuda and "." not in anfitrion and anfitrion != "localhost"):
        return DUDOSA
    return anfitrion, "%s/%s" % (encontrada.group(2), encontrada.group(3))


def _local(fuente, base, ctx):
    texto = fuente.strip()
    texto = _de_git_bash(texto) if ctx.windows else texto
    hogar = ctx.entorno.get("HOME") or str(ctx.home)
    if texto == "~":
        texto = hogar
    elif texto.startswith("~/") or (ctx.windows and texto.startswith("~\\")):
        texto = os.path.join(hogar, texto[2:])
    return Path(os.path.normpath(os.path.join(base, texto)))


def _identidad(fuente, base, ctx):
    if fuente.startswith("npm:"):
        spec = fuente[len("npm:"):].strip()
        nombre = re.fullmatch(r"(@?[^@]+(?:/[^@]+)?)(?:@(.+))?", spec, re.DOTALL)
        return "npm:" + (nombre.group(1) if nombre else spec)
    git = _git(fuente) if fuente.strip().startswith(NO_LOCALES) else None
    if git is DUDOSA:
        return None
    if git is not None:
        return "git:%s/%s" % git
    return "local:" + _clave(_local(fuente, base, ctx), ctx.windows)


def _manifiesto(ruta):
    try:
        texto = ruta.read_bytes().decode("utf-8", "replace")
        datos = json.loads(texto[1:] if texto.startswith("﻿") else texto, parse_constant=_sin_constantes)
    except (OSError, ValueError, RecursionError):
        return None
    propio = datos.get("pi") if isinstance(datos, dict) else None
    if not isinstance(propio, dict):
        return None
    return {campo: propio[campo] for campo in CAMPOS_DE_RECURSOS
            if isinstance(propio.get(campo), list) and all(isinstance(entrada, str) for entrada in propio[campo])}


def _es_override(entrada):
    return entrada.startswith(("!", "+", "-"))


def _entradas_de_extension(carpeta):
    if (carpeta / "package.json").exists():
        manifiesto = _manifiesto(carpeta / "package.json")
        existentes = [Path(os.path.normpath(os.path.join(carpeta, entrada))) for entrada in (manifiesto or {}).get("extensions", [])
                      if os.path.exists(os.path.join(carpeta, entrada))]
        if existentes:
            return existentes
    return next(([carpeta / indice] for indice in ("index.ts", "index.js") if (carpeta / indice).exists()), None)


def _auto(carpeta):
    if not carpeta.exists():
        return []
    propias = _entradas_de_extension(carpeta)
    if propias:
        return propias
    if any((carpeta / nombre).exists() for nombre in IGNORADOS):
        return None
    try:
        entradas = list(os.scandir(carpeta))
    except OSError:
        return []
    hallados = []
    for entrada in entradas:
        ruta = Path(entrada.path)
        if entrada.name.startswith(".") or entrada.name == "node_modules":
            continue
        if ruta.is_file() and entrada.name.endswith((".ts", ".js")):
            hallados.append(ruta)
        elif ruta.is_dir():
            hallados += _entradas_de_extension(ruta) or []
    return hallados


def _de_las_entradas(raiz, entradas):
    archivos = []
    for entrada in entradas:
        if _es_override(entrada):
            continue
        if COMODIN.search(entrada):
            return None
        ruta = Path(os.path.normpath(os.path.join(raiz, entrada)))
        de_la_entrada = [] if not ruta.exists() else [ruta] if ruta.is_file() else _auto(ruta) if ruta.is_dir() else []
        if de_la_entrada is None:
            return None
        archivos += de_la_entrada
    return archivos


def _alguno(valores):
    return True if True in valores else None if None in valores else False


def _segmento(patron, texto):
    if "**" in patron or (texto == "" and COMODIN.search(patron)):
        return None
    if texto.startswith(".") and patron[:1] in ("*", "?"):
        return False
    regex = "".join("[^/]*" if letra == "*" else "[^/]" if letra == "?" else re.escape(letra) for letra in patron)
    return re.fullmatch(regex, texto, re.DOTALL) is not None


def _minimatch(texto, patron):
    partes, segmentos = patron.split("/"), texto.split("/")
    if not patron or FUERA_DE_MINIMATCH.search(patron) or "//" in patron or patron.endswith("/") or {".", ".."} & set(partes):
        return None

    def desde(i, j):
        if i == len(partes):
            return j == len(segmentos)
        if partes[i] == "**":
            if i == len(partes) - 1 and j == len(segmentos):
                return None
            valores = [desde(i + 1, j)]
            if j < len(segmentos) and segmentos[j] == "":
                valores.append(None)
            elif j < len(segmentos) and not segmentos[j].startswith("."):
                valores.append(desde(i, j + 1))
            return _alguno(valores)
        if j == len(segmentos):
            return False
        coincide = _segmento(partes[i], segmentos[j])
        return coincide if not coincide else desde(i + 1, j + 1)

    return desde(0, 0)


def _relativa(archivo, base):
    try:
        return os.path.relpath(archivo, base).replace(os.sep, "/")
    except ValueError:
        return str(archivo).replace(os.sep, "/")


def _patron_de_pi(patron, ctx):
    patron = _de_git_bash(patron) if ctx.windows else patron
    if patron == "~" or patron.startswith(("~/", "~\\")):
        patron = os.path.join(str(ctx.home), patron[2:])
    return patron.replace(os.sep, "/")


def _coincide(archivo, patrones, base, ctx):
    textos = (_relativa(archivo, base), archivo.name, str(archivo).replace(os.sep, "/"))
    return _alguno([_minimatch(texto, _patron_de_pi(patron, ctx)) for patron in patrones for texto in textos])


def _exacta(archivo, patrones, base, ctx):
    textos = (_relativa(archivo, base), str(archivo).replace(os.sep, "/"))
    return any(_patron_de_pi(patron[2:] if patron.startswith(("./", ".\\")) else patron, ctx) in textos for patron in patrones)


def _habilitado(archivo, patrones, base, ctx):
    incluir = [patron for patron in patrones if not _es_override(patron)]
    excluir, forzar, quitar = ([patron[1:] for patron in patrones if patron.startswith(marca)] for marca in "!+-")
    estado = True if not incluir else _coincide(archivo, incluir, base, ctx)
    if excluir:
        fuera = _coincide(archivo, excluir, base, ctx)
        estado = False if fuera is True or estado is False else None if fuera is None else estado
    if forzar and _exacta(archivo, forzar, base, ctx):
        estado = True
    if quitar and _exacta(archivo, quitar, base, ctx):
        estado = False
    return estado


def _con_autoload_apagado(archivo, patrones, base, ctx):
    estado = AUSENTE
    for patron in patrones:
        objetivo = patron[1:] if _es_override(patron) else patron
        exacta = patron.startswith(("+", "-"))
        coincide = _exacta(archivo, [objetivo], base, ctx) if exacta else _coincide(archivo, [objetivo], base, ctx)
        if coincide is True:
            estado = not patron.startswith(("-", "!"))
        elif coincide is None:
            estado = None
    return estado


def _archivos_del_paquete(raiz, manifiesto, ctx):
    entradas = (manifiesto or {}).get("extensions")
    if entradas:
        todos = _de_las_entradas(raiz, entradas)
        patrones = [entrada for entrada in entradas if _es_override(entrada)]
        if todos is None or not patrones:
            return None if todos is None else {archivo: True for archivo in todos}
        dentro = {archivo: _habilitado(archivo, patrones, raiz, ctx) for archivo in todos}
        return {archivo: estado for archivo, estado in dentro.items() if estado is not False}
    todos = _auto(raiz / "extensions")
    return None if todos is None else {archivo: True for archivo in todos}


def _del_manifiesto(raiz, entradas, ctx):
    todos = _de_las_entradas(raiz, entradas or [])
    if todos is None:
        return None
    patrones = [entrada for entrada in entradas or [] if _es_override(entrada)]
    estados = {archivo: _habilitado(archivo, patrones, raiz, ctx) if patrones else True for archivo in todos if _es_shim(archivo)}
    return {archivo: estado for archivo, estado in estados.items() if estado is not False}


def _con_filtro(raiz, manifiesto, filtro, ctx):
    patrones = filtro.get("extensions")
    if patrones is not None and not (isinstance(patrones, list) and all(isinstance(patron, str) for patron in patrones)):
        return None
    if filtro.get("autoload") is False and not patrones:
        return {}
    if patrones is None:
        entradas = (manifiesto or {}).get("extensions")
        return _del_manifiesto(raiz, entradas, ctx) if entradas is not None else _sin_manifiesto(raiz)
    todos = _archivos_del_paquete(raiz, manifiesto, ctx)
    if todos is None:
        return None
    estados = {}
    for archivo, dentro in todos.items():
        if not _es_shim(archivo):
            continue
        if filtro.get("autoload") is False:
            estado = _con_autoload_apagado(archivo, patrones, raiz, ctx)
        else:
            estado = _habilitado(archivo, patrones, raiz, ctx) if patrones else False
        if estado is not AUSENTE:
            estados[archivo] = None if dentro is None else estado
    return estados


def _sin_manifiesto(raiz):
    todos = _auto(raiz / "extensions")
    return None if todos is None else {archivo: True for archivo in todos if _es_shim(archivo)}


def _del_paquete(raiz, filtro, ctx):
    manifiesto = _manifiesto(raiz / "package.json")
    if filtro is not None:
        return _con_filtro(raiz, manifiesto, filtro, ctx)
    if manifiesto:
        return _del_manifiesto(raiz, manifiesto.get("extensions"), ctx)
    return _sin_manifiesto(raiz)


def _por_que_no(raiz, filtro, ctx):
    if _del_paquete(raiz, None, ctx):
        return SIN_AUTOLOAD if filtro.get("autoload") is False and not filtro.get("extensions") else FILTRADO
    arriba = _del_paquete(raiz.parent, None, ctx) if _es_un_plugin(raiz) else None
    if arriba and any(_misma(archivo.parent.parent, raiz) for archivo in arriba):
        return EN_PLUGIN % raiz.parent
    return SIN_MANIFIESTO


def _de_odd_ws_en_npm(fuente, ctx):
    return _identidad(fuente, None, ctx)[len("npm:"):].lower().rsplit("/", 1)[-1] in NOMBRES_DE_ODD_WS


def _aporte(paquete, base, base_git, ctx):
    fuente = paquete.get("source") if isinstance(paquete, dict) else paquete
    filtro = paquete if isinstance(paquete, dict) else None
    if not isinstance(fuente, str):
        return None, f"una entrada de packages no tiene una fuente de texto ({json.dumps(paquete)[:60]}), y Pi no la puede leer"
    git = _git(fuente) if fuente.strip().startswith(NO_LOCALES) and not fuente.startswith("npm:") else None
    if fuente.startswith("npm:"):
        return {}, (f"{fuente}: {POR_NPM}" if _de_odd_ws_en_npm(fuente, ctx) else None)
    if git is DUDOSA and DE_ODD_WS not in fuente.lower():
        return {}, None
    if git is DUDOSA:
        return {}, f"{fuente}: no se puede decidir dónde la clona Pi (la parte hosted-git-info), así que el doctor no la cuenta"
    raiz = base_git / git[0] / git[1] if git is not None else _local(fuente, base, ctx)
    if git is not None and not raiz.is_dir():
        return {}, f"{fuente}: {SIN_CLONAR % raiz}" if DE_ODD_WS in fuente.lower() or DE_ODD_WS in str(raiz).lower() else None
    if not raiz.exists():
        sin_git = fuente.strip().startswith(("github:", "ssh:", "git@")) and DE_ODD_WS in fuente.lower()
        return {}, f"{fuente}: Pi la toma como una ruta local, que no existe ({FUENTE_GIT})" if sin_git else None
    if raiz.is_file():
        return ({raiz: True} if _es_shim(raiz) else {}), None
    estados = _del_paquete(raiz, filtro, ctx)
    if estados is None:
        return None, f"{fuente}: no se puede decidir qué archivos carga Pi de {raiz} (un glob, un .gitignore o un filtro raro)"
    if not any(estado is True for estado in estados.values()) and _de_odd_ws(raiz):
        if any(estado is None for estado in estados.values()):
            return estados, f"{fuente}: no se puede decidir si el filtro extensions deja shim/pi.ts"
        return estados, f"{fuente}: {_por_que_no(raiz, filtro or {}, ctx)}"
    return estados, None


def _fuente(paquete):
    return paquete.get("source") if isinstance(paquete, dict) else paquete


def _identidad_de(entrada, bases, ctx):
    paquete, alcance, _ = entrada
    return _identidad(_fuente(paquete), bases[alcance], ctx) if isinstance(_fuente(paquete), str) else None


def _deduplicadas(entradas, bases, ctx):
    resultado, vistas, reemplazos = [], {}, []
    for entrada in entradas:
        identidad = _identidad_de(entrada, bases, ctx)
        indice = vistas.get(identidad) if identidad is not None else None
        if indice is None:
            if identidad is not None:
                vistas[identidad] = len(resultado)
            resultado.append(entrada)
            continue
        existente = resultado[indice]
        if existente[1] == "project" and entrada[1] == "user":
            if isinstance(existente[0], dict) and existente[0].get("autoload") is False:
                resultado.append(entrada)
            else:
                reemplazos.append(f"la entrada {_fuente(entrada[0])} de {entrada[2]} la reemplaza la de {existente[2]}, que gana por ser "
                                  "del proyecto")
        elif entrada[1] == "project":
            resultado[indice] = entrada
    return resultado, reemplazos


def _resolver_paquetes(ctx, raiz, activo, confia):
    datos_del_home, _ = _objeto_json(activo / SETTINGS)
    proyecto = Path(raiz) / capas.PI if raiz is not None else None
    datos_del_proyecto = (_objeto_json(proyecto / SETTINGS)[0] or {}) if proyecto is not None and confia else {}
    if _paquetes(datos_del_home) is None or _paquetes(datos_del_proyecto) is None:
        return [], True, ["packages no es una lista, y Pi no la puede recorrer"]
    entradas = ([(paquete, "project", f"{capas.PI}/{SETTINGS}") for paquete in _paquetes(datos_del_proyecto)] +
                [(paquete, "user", str(activo / SETTINGS)) for paquete in _paquetes(datos_del_home)])
    bases = {"project": proyecto, "user": activo}
    deduplicadas, motivos = _deduplicadas(entradas, bases, ctx)
    estados, dudoso = {}, False
    for entrada in deduplicadas:
        paquete, alcance, settings = entrada
        delta = alcance == "project" and isinstance(paquete, dict) and paquete.get("autoload") is False
        del_home = [otra for otra in deduplicadas if delta and otra[1] == "user"
                    and _identidad_de(otra, bases, ctx) == _identidad_de(entrada, bases, ctx) is not None]
        if del_home:
            aporte, motivo = _aporte(dict(paquete, source=_fuente(del_home[0][0])), activo, activo / "git", ctx)
        else:
            aporte, motivo = _aporte(paquete, bases[alcance], bases[alcance] / "git", ctx)
        motivos += [motivo] if motivo else []
        if aporte is None:
            dudoso = True
            continue
        for archivo, estado in aporte.items():
            estados.setdefault(_clave(archivo, ctx.windows), (archivo, None if dudoso else estado, _fuente(paquete), settings, alcance))
    return list(estados.values()), dudoso, motivos


def _de_nivel_superior(datos, base, archivos, ctx):
    entradas = datos.get("extensions") if isinstance(datos, dict) else None
    planas = [entrada for entrada in entradas if isinstance(entrada, str) and not _es_override(entrada) and not COMODIN.search(entrada)] \
        if isinstance(entradas, list) else []
    claves = [(ruta, _clave(ruta, ctx.windows)) for ruta in (_local(entrada, base, ctx) for entrada in planas)]
    return list(dict.fromkeys(str(ruta) for ruta, clave in claves for archivo in archivos
                              if _clave(archivo, ctx.windows) == clave or _clave(archivo, ctx.windows).startswith(clave.rstrip(os.sep) + os.sep)))


def _paquete(ctx, raiz, nucleo, gentle):
    id = ID_PLUGIN
    activo, etiqueta, otros = _homes(ctx, gentle)
    datos_del_home, error = _objeto_json(activo / SETTINGS)
    if error is not None:
        return nucleo.resultado(id, nucleo.FALTA, f"{activo / SETTINGS} no se puede leer como un objeto JSON ({error})", None, AYUDA_SETTINGS)
    confia = raiz is not None and _veredicto_de_confianza(ctx, Path(raiz), nucleo, activo)[0] == nucleo.OK
    estados, dudoso, motivos = _resolver_paquetes(ctx, raiz, activo, confia)
    cargados = [estado for estado in estados if estado[1] is True]
    archivos = [estado[0] for estado in estados] + [Path(ctx.plugin) / "shim" / "pi.ts"]
    datos_del_proyecto = (_objeto_json(Path(raiz) / capas.PI / SETTINGS)[0] or {}) if raiz is not None and confia else {}
    arriba = _de_nivel_superior(datos_del_home, activo, archivos, ctx) + \
        (_de_nivel_superior(datos_del_proyecto, Path(raiz) / capas.PI, archivos, ctx) if raiz is not None else [])
    ayuda = AYUDA_PAQUETE
    if raiz is not None and not confia:
        sin_confianza, _, _ = _resolver_paquetes(ctx, raiz, activo, True)
        if any(estado[1] is True and estado[4] == "project" for estado in sin_confianza):
            motivos.append(f"{capas.PI}/{SETTINGS} declara odd-ws, pero Pi no carga la config del proyecto sin confianza "
                           f"({_veredicto_de_confianza(ctx, Path(raiz), nucleo, activo)[1]}): instalalo en el home activo o dale "
                           "confianza al proyecto")
            ayuda = f"{AYUDA_PAQUETE} {AYUDA_CONFIANZA}"
    if arriba:
        motivos.append(f"la clave extensions de nivel superior apunta a {', '.join(arriba)}, y el doctor no decide cómo la combina Pi "
                       "con el paquete")
    if cargados and not dudoso and not arriba:
        archivo, _, fuente, settings, alcance = cargados[0]
        donde = f"Pi carga {archivo} desde {fuente}, en los packages de {settings}" + (f", {CON_CONFIANZA}" if alcance == "project" else "")
        if not _misma(archivo.parent.parent, ctx.plugin):
            return nucleo.resultado(id, nucleo.AVISO, f"Pi carga otra copia de odd-ws, {archivo.parent.parent} ({donde}), y el doctor corre "
                                                      f"desde {ctx.plugin}: lo que revisa no es lo que corre", None, AYUDA_PAQUETE)
        return nucleo.resultado(id, nucleo.OK, donde)
    if dudoso or arriba or any(estado[1] is None for estado in estados):
        return nucleo.resultado(id, nucleo.FALTA, "no se puede decidir si Pi carga shim/pi.ts de odd-ws: " + "; ".join(motivos or [INDECIDIBLE]),
                                None, ayuda)
    lugares = f"{activo / SETTINGS} ({etiqueta})" + (f" ni de {capas.PI}/{SETTINGS}" if raiz is not None else "")
    if motivos:
        return nucleo.resultado(id, nucleo.FALTA, f"Pi no carga shim/pi.ts de odd-ws desde los packages de {lugares}: " + "; ".join(motivos),
                                None, ayuda)
    detalle = f"odd-ws no está en los packages de {lugares}"
    en_otros = [str(otro / SETTINGS) for otro in otros if any(estado[1] is True for estado in _resolver_paquetes(ctx, None, otro, False)[0])]
    if en_otros:
        detalle += f"; está en {', '.join(en_otros)}, que no es el home activo"
    return nucleo.resultado(id, nucleo.FALTA, detalle, None, ayuda)


def _clave(ruta, windows):
    resuelta = os.path.normpath(os.path.abspath(ruta))
    return resuelta.lower() if windows else resuelta


def _piden_confianza(ctx, raiz):
    actual = Path(os.path.realpath(raiz))
    propios = ["%s/%s" % (capas.PI, nombre) for nombre in RECURSOS_CON_CONFIANZA if (actual / capas.PI / nombre).exists()]
    personal = _clave(os.path.realpath(Path(ctx.entorno.get("HOME") or ctx.home) / ".agents" / "skills"), ctx.windows)
    while True:
        skills = actual / ".agents" / "skills"
        if _clave(skills, ctx.windows) != personal and skills.exists():
            propios.append(str(skills))
        if actual.parent == actual:
            return propios
        actual = actual.parent


def _decisiones(ruta):
    datos, error = _objeto_json(ruta)
    if error is None and any(not (valor is True or valor is False or valor is None) for valor in datos.values()):
        error = "cada valor tiene que ser true, false o null"
    return datos, error


def _mas_cercana(decisiones, raiz, windows):
    actual = os.path.realpath(raiz)
    while True:
        clave = _clave(actual, windows)
        for propia, decision in decisiones.items():
            if isinstance(decision, bool) and _clave(propia, windows) == clave:
                return propia, decision
        padre = os.path.dirname(actual)
        if padre == actual:
            return None
        actual = padre


def _veredicto_de_confianza(ctx, raiz, nucleo, activo):
    trust = activo / CONFIANZA
    decisiones, error = _decisiones(trust)
    if error is not None:
        return nucleo.AVISO, f"no se revisa: {trust} no se puede leer como el {CONFIANZA} de Pi ({error}), y Pi tampoco lo lee"
    cercana = _mas_cercana(decisiones, raiz, ctx.windows)
    if cercana is not None:
        return (nucleo.OK, f"{trust} confía en {cercana[0]}") if cercana[1] else \
            (nucleo.AVISO, f"{trust} guarda «Do not trust» para {cercana[0]}")
    piden = _piden_confianza(ctx, raiz)
    if not piden:
        return nucleo.OK, (f"Pi confía solo: la instancia no tiene recursos que pidan confianza y {trust} no guarda una decisión para "
                           "ella")
    datos, _ = _objeto_json(activo / SETTINGS)
    defecto = (datos or {}).get("defaultProjectTrust")
    defecto = defecto if defecto in ("always", "never") else "ask"
    if defecto == "always":
        return nucleo.OK, f"{trust} no guarda una decisión y defaultProjectTrust = always en {activo / SETTINGS}"
    motivo = ("Pi no confía" if defecto == "never" else
              "Pi pregunta al abrir y, sin pantalla (print, json o rpc, como los subagentes de gentle-shell), no confía")
    return nucleo.AVISO, (f"la instancia tiene recursos que piden confianza ({', '.join(piden)}), {trust} no guarda una decisión para "
                          f"ella, y con defaultProjectTrust = {defecto}, {motivo}")


def _confianza(ctx, raiz, nucleo, gentle):
    activo, _, _ = _homes(ctx, gentle)
    estado, detalle = _veredicto_de_confianza(ctx, raiz, nucleo, activo)
    if estado == nucleo.OK:
        return nucleo.resultado(ID_CONFIANZA, estado, detalle)
    return nucleo.resultado(ID_CONFIANZA, estado, detalle if detalle.startswith("no se revisa") else f"{detalle}: {SIN_SKILLS}", None,
                            AYUDA_CONFIANZA)


def _derivado_por_odd_ws(texto):
    return codex._normal(texto).startswith(DELIMITADOR + "\n" + ENCABEZADO.split("%s", 1)[0])


def _revisar_agente(raiz, nombre, bootstrap_agentes, plantilla_writer):
    texto = codex._leer_utf8(raiz / capas.agente(nombre))
    if texto is None:
        return codex.RevisionDeAgente(nombre, "fuente", None, "no se puede leer como UTF-8")
    texto = plantilla_writer.normalizar(texto)
    if not codex._md_intacto(texto, plantilla_writer):
        return codex.RevisionDeAgente(nombre, "fuente", None, "se editó fuera de sus bloques o no lo generó la plantilla")
    try:
        esperado = md(plantilla_writer.agente(bootstrap_agentes.armar(nombre, texto, "pi")))
    except ValueError as error:
        return codex.RevisionDeAgente(nombre, "fuente", None, str(error))
    ruta = raiz / capas.agente_pi(nombre)
    if not os.path.lexists(ruta):
        return codex.RevisionDeAgente(nombre, "falta", esperado, None)
    actual = codex._leer_utf8(ruta) if ruta.is_file() else None
    if actual is None:
        return codex.RevisionDeAgente(nombre, "ilegible", None, None)
    lineas = codex._normal(actual).split("\n")
    if "\n".join(lineas) == esperado:
        return codex.RevisionDeAgente(nombre, "ok", esperado, None)
    if lineas[0] == DELIMITADOR and codex._declarada(lineas[1:], CLAVE_HASH, True) == huella(actual):
        return codex.RevisionDeAgente(nombre, "atrasado", esperado, None)
    return codex.RevisionDeAgente(nombre, "editado", None, None)


def revisar_agentes(raiz, declaradas):
    import bootstrap_agentes
    import plantilla_writer

    raiz = Path(raiz)
    revisiones, con_md = [], set()
    for nombre in dict.fromkeys(bootstrap_agentes.nombres_de_agentes(declaradas)):
        if (raiz / capas.agente(nombre)).is_file():
            con_md.add(nombre)
            revisiones.append(_revisar_agente(raiz, nombre, bootstrap_agentes, plantilla_writer))
    carpeta = raiz / capas.PI_AGENTES
    for ruta in sorted(carpeta.glob("*.md")) if carpeta.is_dir() else ():
        texto = codex._leer_utf8(ruta) if ruta.is_file() else None
        if ruta.stem not in con_md and texto is not None and _derivado_por_odd_ws(texto):
            revisiones.append(codex.RevisionDeAgente(ruta.stem, "sobrante", None, None))
    return revisiones


def _problema(revision):
    nombre, codigo = revision.nombre, revision.codigo
    de_pi, fuente = capas.agente_pi(nombre), capas.agente(nombre)
    return {
        "falta": f"falta {de_pi}",
        "atrasado": f"{de_pi} quedó atrás de {fuente}",
        "editado": f"{de_pi} se editó a mano: no se pisa",
        "ilegible": f"{de_pi} no se puede leer como UTF-8: no se pisa",
        "fuente": f"{fuente} {revision.motivo}: su .md de Pi no se deriva",
        "sobrante": f"{de_pi} es de un agente que ya no existe (falta {fuente} o su capa salió de la config): no se borra",
    }[codigo]


def _escribir_agentes(raiz):
    import config_loader

    escritos = []
    for revision in revisar_agentes(raiz, config_loader.capas(raiz)):
        if revision.codigo not in ("falta", "atrasado"):
            continue
        ruta = raiz / capas.agente_pi(revision.nombre)
        if revision.codigo == "falta":
            escritos.append(codex._crear(ruta, revision.esperado))
            continue
        try:
            ruta.write_bytes(revision.esperado.encode("utf-8"))
        except OSError as error:
            escritos.append(f"no se pudo escribir {ruta}: {error.strerror or error}")
            continue
        escritos.append(str(ruta))
    return ", ".join(escritos) or "nada que derivar"


def _agentes(raiz, nucleo):
    import config_loader

    id = ID_AGENTES
    try:
        declaradas = config_loader.capas(raiz)
    except config_loader.ConfigRota as error:
        return nucleo.resultado(id, nucleo.FALTA, f"no se pueden revisar los agentes de Pi: {error}", None, nucleo.AYUDA_CONFIG)
    revisiones = revisar_agentes(raiz, declaradas)
    if not revisiones:
        return nucleo.resultado(id, nucleo.NO_APLICA, f"no hay agentes de la plantilla en {capas.AGENTES} que derivar")
    problemas = [revision for revision in revisiones if revision.codigo != "ok"]
    if not problemas:
        return nucleo.resultado(id, nucleo.OK, f"{len(revisiones)} .md de {capas.PI_AGENTES} al día con su .md de {capas.AGENTES}")
    a_mano = any(revision.codigo not in ("falta", "atrasado") for revision in problemas)
    detalle = "; ".join(map(_problema, problemas))
    ayuda = AYUDA_AGENTES if a_mano else ""
    if any(revision.codigo in ("falta", "atrasado") for revision in problemas):
        return nucleo.resultado(id, nucleo.FALTA, detalle, None, ayuda, lambda: _escribir_agentes(raiz))
    return nucleo.resultado(id, nucleo.AVISO, detalle, None, ayuda)


def _sin_constantes(nombre):
    raise ValueError("%s no es JSON" % nombre)


def _leer_como_el_shim(ruta):
    try:
        texto = Path(ruta).read_bytes().decode("utf-8", "replace")
    except OSError as error:
        return None, "no se puede leer (%s)" % (error.strerror or error)
    try:
        return json.loads(texto, parse_constant=_sin_constantes), None
    except (ValueError, RecursionError) as error:
        return None, "no es JSON (%s)" % error


def _texto(valor):
    return isinstance(valor, str) and valor != ""


def _segundos(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    try:
        return math.isfinite(valor) and valor > 0
    except OverflowError:
        return False


def _problema_del_hook(hook):
    if not isinstance(hook, dict):
        return "no es un objeto con script, args y timeout"
    if not isinstance(hook.get("script"), str) or not SCRIPT_DEL_SHIM.fullmatch(hook["script"]):
        return "script tiene que ser el nombre de un .py de scripts/, sin ruta"
    if not isinstance(hook.get("args"), list) or not all(isinstance(argumento, str) for argumento in hook["args"]):
        return "args tiene que ser una lista de textos"
    if not _segundos(hook.get("timeout")):
        return "timeout tiene que ser un número de segundos mayor que 0"
    return None


def _forma(datos):
    if not isinstance(datos, dict):
        return ["no es un objeto JSON"]
    problemas = ["%s tiene que ser un texto no vacío" % clave for clave in (CLAVE_PYTHON, CLAVE_PYTHON_EN_WINDOWS) if not _texto(datos.get(clave))]
    if "writer" in datos and not _texto(datos["writer"]):
        problemas.append("writer tiene que ser un texto no vacío con la regex de los writers")
    eventos = datos.get("hooks")
    if not isinstance(eventos, dict):
        return problemas + ["hooks tiene que ser un objeto con la lista de grupos de cada evento"]
    for evento, grupos in eventos.items():
        if not isinstance(grupos, list):
            problemas.append("%s tiene que ser una lista de grupos" % evento)
            continue
        for indice, grupo in enumerate(grupos):
            lugar = "%s[%d]" % (evento, indice)
            if not isinstance(grupo, dict):
                problemas.append("%s no es un objeto con tools y hooks" % lugar)
                continue
            if "tools" in grupo and not (isinstance(grupo["tools"], list) and all(_texto(nombre) for nombre in grupo["tools"])):
                problemas.append("%s: tools tiene que ser una lista de nombres de herramienta" % lugar)
            if not isinstance(grupo.get("hooks"), list):
                problemas.append("%s: hooks tiene que ser una lista" % lugar)
                continue
            problemas += ["%s[%d]: %s" % (lugar, orden, problema) for orden, problema in
                          ((orden, _problema_del_hook(hook)) for orden, hook in enumerate(grupo["hooks"])) if problema]
    return problemas


def _corren(eventos, evento, herramienta):
    return {hook["script"] for grupo in eventos.get(evento, [])
            if "tools" not in grupo or (herramienta is not None and herramienta in grupo["tools"]) for hook in grupo["hooks"]}


def _estricto(datos):
    problemas = []
    if "writer" not in datos:
        problemas.append(("writer", SIN_WRITER))
    elif datos["writer"] != REGEX_DE_WRITER:
        problemas.append(("writer", OTRO_WRITER % (datos["writer"], REGEX_DE_WRITER)))
    for evento, grupos in datos["hooks"].items():
        de_herramienta = evento in EVENTOS_DE_HERRAMIENTA
        for indice, grupo in enumerate(grupos):
            lugar = "%s[%d]" % (evento, indice)
            if de_herramienta and grupo.get("tools") == []:
                problemas.append(("muerto %s %d" % (evento, indice), "%s tiene tools vacía: ese grupo no corre nunca" % lugar))
            elif not de_herramienta and "tools" in grupo:
                problemas.append(("muerto %s %d" % (evento, indice),
                                  "%s tiene tools, y %s no es de una herramienta: ese grupo no corre nunca" % (lugar, evento)))
    for evento, por_herramienta in COBERTURA.items():
        for herramienta, scripts in por_herramienta.items():
            corren = _corren(datos["hooks"], evento, herramienta)
            donde = evento if herramienta is None else "%s de %s" % (evento, herramienta)
            problemas += [("cobertura %s %s %s" % (evento, herramienta or "-", script), "%s no corre %s" % (donde, script))
                          for script in scripts if script not in corren]
    return problemas


def revisar_lista(ruta):
    datos, error = _leer_como_el_shim(ruta)
    if error is not None:
        return [(FORMA, error)]
    forma = _forma(datos)
    return [(FORMA, problema) for problema in forma] if forma else _estricto(datos)


def _de_la_compuerta(datos, plugin):
    scripts, problemas = Path(plugin) / "scripts", []
    for evento, grupos in datos["hooks"].items():
        for grupo, entrada in enumerate(grupos):
            for orden, hook in enumerate(entrada["hooks"]):
                lugar = "%s[%d][%d]" % (evento, grupo, orden)
                if not (scripts / hook["script"]).is_file():
                    problemas.append("%s: %s no existe en %s, así que el hook falla" % (lugar, hook["script"], scripts))
                plazo = plazo_de(hook["args"])
                if hook["timeout"] <= plazo:
                    problemas.append("%s: timeout %s no es mayor que su --plazo %s, así que el shim corta el hook antes de su plazo" % (
                        lugar, hook["timeout"], "%g" % plazo))
    cierre = [hook["script"] for entrada in datos["hooks"].get(FIN, []) for hook in entrada["hooks"]]
    if len(cierre) > 1 or set(cierre) - set(COBERTURA[FIN][None]):
        problemas.append("%s corre %d hooks (%s): la compuerta corre solo %s, porque cualquier falla le gana a seguir y el writer cierra "
                         "sin compuerta" % (FIN, len(cierre), ", ".join(cierre), ", ".join(COBERTURA[FIN][None])))
    return problemas


def problemas_de_hooks(ctx):
    ruta = Path(ctx.plugin) / ARCHIVO_DE_HOOKS
    if leer_hooks(ruta) is None:
        return []
    revision = revisar_lista(ruta)
    problemas = ["%s: %s" % (ARCHIVO_DE_HOOKS, texto) for _, texto in revision]
    if any(clave == FORMA for clave, _ in revision):
        return problemas + [RECHAZADO]
    return problemas + ["%s: %s" % (ARCHIVO_DE_HOOKS, texto) for texto in _de_la_compuerta(_leer_como_el_shim(ruta)[0], ctx.plugin)]


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
