import hashlib
import json
import os
import re
from collections import namedtuple
from pathlib import Path

from odd_ws import capas
from odd_ws.capacidades import DEGRADADO, FIN_SUBAGENTE, INICIO, POST, PRE, SOPORTADO
from odd_ws.comun import SILENCIO, archivos_de_la_bitacora, comandos_de_la_bitacora
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, FinSubagente, Herramienta, InicioSesion, Preguntar, Seguir
from odd_ws.hosts import Archivo, base, leer_hooks, manejadores, tokens_de

cargar = base.cargar
EXPRESABLES = {PRE: (Bloquear, Preguntar), POST: (Bloquear, Contexto), INICIO: (Contexto,), FIN_SUBAGENTE: (Seguir,)}
DEGRADACIONES = {PRE: {Preguntar: Bloquear}}
BITACORA = True
PRECARGA_SKILLS = False
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
ID_AGENTES = "codex-agentes"
ARCHIVO_DE_HOOKS = "hooks/hooks.codex.json"
PYTHON = "python3"
PYTHON_EN_WINDOWS = "python"
VERSION_MINIMA = (0, 144, 0)
CONFIANZA = "trusted"
FALLBACK = "CLAUDE.md"
FRESCURA = "la frescura del hash no se verifica: si el plugin cambió, Codex pide confiar de nuevo"
NO_CARGA = "Codex no carga .codex/ (ni los agentes ni el fallback a CLAUDE.md)"
AYUDA_CODEX = "Instalá o actualizá Codex a 0.144 o superior (npm i -g @openai/codex)."
AYUDA_TOML = "Arreglalo a mano: tiene que ser TOML en UTF-8, y así tampoco lo lee Codex. Después, otra vez el doctor."
SIN_TOMLLIB = "requiere Python 3.11 o más para leer la config de Codex"
AYUDA_SIN_TOMLLIB = "Corré el doctor con Python 3.11 o más: lo necesita para leer la config de Codex (tomllib)."
AYUDA_PLUGIN = ("En Codex, agregá el marketplace %s, instalá odd-ws y dejalo habilitado. El doctor no escribe en la carpeta de "
                "Codex.")
AYUDA_HOOKS = ("Abrí Codex, entrá a /hooks y confiá los hooks de odd-ws (y activá los apagados): Codex no corre un hook sin "
               "confianza, y en 0.167 la pide de nuevo con cada actualización del plugin. El doctor no escribe en la carpeta de Codex.")
AYUDA_PROYECTO = ("Abrí Codex en la raíz de la instancia y aceptá confiar en la carpeta, o agregá a %s la tabla %s, con la ruta tal "
                  "cual: entre comillas simples, con sus barras y sin barra al final, porque Codex compara el texto (en Windows, sin "
                  "distinguir mayúsculas). El doctor no escribe en la carpeta de Codex.")
ASCII_MINUSCULAS = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
HOOKS_DEL_PROYECTO = capas.CODEX + "/hooks.json"
AYUDA_CONFIG = ("Agregá a .codex/config.toml la línea %s, o sumá \"CLAUDE.md\" a esa lista si ya la tiene. El doctor no pisa un "
                "archivo que ya existe.")
AYUDA_AGENTES = ("El .md de .claude/agents es la fuente de su TOML: pasá tu cambio al .md (a la description o a un bloque "
                 "<!-- instancia:... -->), sacá el TOML y corré --arreglar codex-agentes. Si el .md se editó fuera de sus bloques, "
                 "arreglalo primero; el TOML de un agente que ya no existe lo borrás vos.")
EVENTO_RE = re.compile(r"(?<!^)(?=[A-Z])")

RevisionDeAgente = namedtuple("RevisionDeAgente", "nombre codigo esperado motivo")


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
        raise ValueError("el agente necesita %s para su TOML de Codex" % clave)
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
    descripcion = _con_texto(agente.descripcion, "una description no vacía")
    partes = []
    if agente.herramientas:
        partes.append(HERRAMIENTAS % ", ".join(agente.herramientas))
    if agente.skills:
        partes.append(SKILLS % _enumerar(["`%s`" % capas.skill_de(skill) for skill in agente.skills]))
    partes.append(_con_texto(agente.instrucciones, "instrucciones no vacías"))
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
    derivados = [Archivo(capas.agente_codex(agente.nombre), toml(agente), capas.agente(agente.nombre), ID_AGENTES) for agente in agentes]
    return derivados + [Archivo(capas.CODEX_CONFIG, CONFIG_DEL_PROYECTO)]


def carpeta_de_codex(ctx):
    valor = ctx.entorno.get("CODEX_HOME")
    return Path(valor) if valor else Path(ctx.home) / ".codex"


def leer_toml(ruta):
    try:
        crudo = Path(ruta).read_bytes()
    except FileNotFoundError:
        return {}, None
    except OSError as error:
        return None, error.strerror or str(error)
    try:
        import tomllib
    except ImportError:
        return None, SIN_TOMLLIB
    try:
        return tomllib.loads(crudo.decode("utf-8-sig")), None
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return None, str(error)


def _ayuda_del_toml(error):
    return AYUDA_SIN_TOMLLIB if error == SIN_TOMLLIB else AYUDA_TOML


def claves_de_confianza(datos, plugin):
    return ["%s:%s:%s:%d:%d" % (plugin, ARCHIVO_DE_HOOKS, EVENTO_RE.sub("_", evento).lower(), grupo, indice)
            for evento, grupo, indice, _ in manejadores(datos)]


def _comandos(manejador, windows):
    campos = (("command", "", windows), ("commandWindows", " (commandWindows)", True), ("command_windows", " (commandWindows)", True))
    for campo, sufijo, de_windows in campos:
        valor = manejador.get(campo) if isinstance(manejador, dict) else None
        if isinstance(valor, str):
            yield sufijo, tokens_de(valor, de_windows)


def hooks_registrados(ctx, raiz):
    carpeta = carpeta_de_codex(ctx)
    fuentes = [(ARCHIVO_DE_HOOKS, Path(ctx.plugin) / ARCHIVO_DE_HOOKS, leer_hooks, True),
               (str(carpeta / "config.toml"), carpeta / "config.toml", lambda ruta: leer_toml(ruta)[0], False),
               (str(carpeta / "hooks.json"), carpeta / "hooks.json", leer_hooks, False)]
    if raiz is not None:
        fuentes += [(capas.CODEX_CONFIG, Path(raiz) / capas.CODEX_CONFIG, lambda ruta: leer_toml(ruta)[0], False),
                    (HOOKS_DEL_PROYECTO, Path(raiz) / HOOKS_DEL_PROYECTO, leer_hooks, False)]
    for nombre, ruta, leer, propio in fuentes:
        if not propio and not ruta.is_file():
            continue
        datos = leer(ruta)
        if datos is None:
            yield nombre, None, propio
            continue
        for evento, grupo, indice, manejador in manejadores(datos):
            for sufijo, tokens in _comandos(manejador, ctx.windows):
                yield "%s %s[%d][%d]%s" % (nombre, evento, grupo, indice, sufijo), tokens, propio


def version(ctx, nucleo):
    ruta = ctx.which("codex")
    resultado, instalado = nucleo.chequear_version(ctx, "codex", [ruta or "codex", "--version"], VERSION_MINIMA, AYUDA_CODEX)
    if not instalado and ruta:
        resultado = resultado._replace(detalle=f"{ruta} no se pudo ejecutar")
    return resultado, instalado


def chequeos(ctx, raiz, nucleo, cli):
    resultados = []
    de_la_maquina = ["codex-plugin", "codex-hooks"] + (["codex-proyecto"] if raiz is not None else [])
    if cli == nucleo.CLI_INSTALADO:
        usuario = carpeta_de_codex(ctx) / "config.toml"
        datos, error = leer_toml(usuario)
        resultados += [_plugin(ctx, nucleo, usuario, datos, error), _confianza_de_hooks(ctx, nucleo, usuario, datos, error)]
        if raiz is not None:
            resultados.append(_proyecto(ctx, raiz, nucleo, usuario, datos, error))
    else:
        resultados += [nucleo.resultado(id, nucleo.NO_APLICA, "codex no está instalado") for id in de_la_maquina]
    if raiz is not None:
        resultados += [_config_del_proyecto(Path(raiz), nucleo), _agentes(Path(raiz), nucleo)]
    return resultados


def _ilegible(id, nucleo, usuario, error):
    return nucleo.resultado(id, nucleo.AVISO, f"no se revisa: {usuario} no se puede leer como TOML ({error})", None, _ayuda_del_toml(error))


def _versiones(carpeta):
    try:
        return sorted(entrada.name for entrada in carpeta.iterdir() if entrada.is_dir())
    except OSError:
        return []


def _plugin(ctx, nucleo, usuario, datos, error):
    id = "codex-plugin"
    if error is not None:
        return nucleo.resultado(id, nucleo.FALTA, f"{usuario} no se puede leer como TOML ({error})", None, _ayuda_del_toml(error))
    ayuda = AYUDA_PLUGIN % nucleo.MARKETPLACE
    cache = carpeta_de_codex(ctx) / "plugins" / "cache" / nucleo.MARKETPLACE / nucleo.PLUGIN
    versiones = _versiones(cache)
    if not versiones:
        return nucleo.resultado(id, nucleo.FALTA, f"{nucleo.PLUGIN} no está instalado en Codex: no hay ninguna versión en {cache}", None, ayuda)
    plugins = datos.get("plugins")
    entrada = plugins.get(nucleo.CLAVE_PLUGIN) if isinstance(plugins, dict) else None
    en_cache = ", ".join(versiones)
    if not isinstance(entrada, dict):
        return nucleo.resultado(id, nucleo.FALTA, f"{nucleo.CLAVE_PLUGIN} está en el caché ({en_cache}) pero no está en [plugins] de "
                                                  f"{usuario}: Codex no lo carga", None, ayuda)
    if entrada.get("enabled") is False:
        return nucleo.resultado(id, nucleo.FALTA, f"{nucleo.CLAVE_PLUGIN} tiene enabled = false en {usuario}", None, ayuda)
    return nucleo.resultado(id, nucleo.OK, f"{nucleo.CLAVE_PLUGIN} habilitado en {usuario}, con {en_cache} en el caché")


def _confiado(estado):
    valor = estado.get("trusted_hash") if isinstance(estado, dict) else None
    return isinstance(valor, str) and bool(valor.strip())


def _corta(clave):
    return clave.split(ARCHIVO_DE_HOOKS + ":", 1)[-1]


def _confianza_de_hooks(ctx, nucleo, usuario, datos, error):
    id = "codex-hooks"
    if error is not None:
        return _ilegible(id, nucleo, usuario, error)
    del_plugin = leer_hooks(Path(ctx.plugin) / ARCHIVO_DE_HOOKS)
    if del_plugin is None:
        return nucleo.resultado(id, nucleo.AVISO, f"no se puede leer {ARCHIVO_DE_HOOKS} del plugin: no se pueden calcular sus claves")
    claves = claves_de_confianza(del_plugin, nucleo.CLAVE_PLUGIN)
    hooks = datos.get("hooks")
    estados = hooks.get("state") if isinstance(hooks, dict) else None
    estados = {clave.strip(): valor for clave, valor in estados.items()} if isinstance(estados, dict) else {}
    sin_confianza = [clave for clave in claves if not _confiado(estados.get(clave))]
    apagados = [clave for clave in claves if isinstance(estados.get(clave), dict) and estados[clave].get("enabled") is False]
    if not sin_confianza and not apagados:
        return nucleo.resultado(id, nucleo.OK, f"los {len(claves)} handlers de {ARCHIVO_DE_HOOKS} tienen trusted_hash en [hooks.state]; "
                                               f"{FRESCURA}")
    partes = []
    if sin_confianza:
        partes.append(f"{len(sin_confianza)} de {len(claves)} handlers sin trusted_hash en [hooks.state] de {usuario} "
                      f"({', '.join(map(_corta, sin_confianza))}): Codex no los corre")
    if apagados:
        partes.append(f"{len(apagados)} con enabled = false ({', '.join(map(_corta, apagados))})")
    return nucleo.resultado(id, nucleo.AVISO, "; ".join(partes + [FRESCURA]), None, AYUDA_HOOKS)


def _clave_de_busqueda(texto, windows):
    return texto.translate(ASCII_MINUSCULAS) if windows else texto


def claves_de_busqueda(carpeta, windows):
    original = _clave_de_busqueda(str(carpeta), windows)
    canonica = _clave_de_busqueda(os.path.realpath(carpeta), windows)
    return [canonica] if canonica == original else [canonica, original]


def confianza_del_proyecto(proyectos, claves, windows):
    for clave in claves:
        if clave in proyectos:
            return clave, proyectos[clave]
        if windows:
            iguales = sorted(propia for propia in proyectos if _clave_de_busqueda(propia, True) == clave)
            if iguales:
                return iguales[0], proyectos[iguales[0]]
    return None


def _tabla_de_confianza(raiz):
    ruta = os.path.realpath(raiz)
    clave = "'%s'" % ruta if "'" not in ruta and ruta.isprintable() else json.dumps(ruta, ensure_ascii=False)
    return '[projects.%s] con trust_level = "%s"' % (clave, CONFIANZA)


def _proyecto(ctx, raiz, nucleo, usuario, datos, error):
    id = "codex-proyecto"
    if error is not None:
        return _ilegible(id, nucleo, usuario, error)
    proyectos = datos.get("projects")
    niveles = {clave: valor.get("trust_level") for clave, valor in proyectos.items()
               if isinstance(valor, dict) and isinstance(valor.get("trust_level"), str)} if isinstance(proyectos, dict) else {}
    claves = claves_de_busqueda(raiz, ctx.windows)
    repo = nucleo.raiz_del_repo_de(ctx, raiz)
    if repo is not None:
        claves += [clave for clave in claves_de_busqueda(repo, ctx.windows) if clave not in claves]
    ayuda = AYUDA_PROYECTO % (usuario, _tabla_de_confianza(raiz))
    encontrada = confianza_del_proyecto(niveles, claves, ctx.windows)
    if encontrada is None:
        return nucleo.resultado(id, nucleo.AVISO, f"ni la instancia ni su repo tienen confianza en [projects] de {usuario}: {NO_CARGA}",
                                None, ayuda)
    clave, nivel = encontrada
    if nivel == CONFIANZA:
        return nucleo.resultado(id, nucleo.OK, f"{clave} tiene trust_level = {CONFIANZA} en {usuario}")
    return nucleo.resultado(id, nucleo.AVISO, f"{clave} tiene trust_level = {nivel} en {usuario}: {NO_CARGA}", None, ayuda)


def _crear(ruta, texto):
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "xb") as archivo:
            archivo.write(texto.encode("utf-8"))
    except FileExistsError:
        return f"{ruta} ya existe: no se pisa"
    except OSError as error:
        return f"no se pudo crear {ruta}: {error.strerror or error}"
    return str(ruta)


def _config_del_proyecto(raiz, nucleo):
    id = "codex-config"
    ruta = raiz / capas.CODEX_CONFIG
    if not os.path.lexists(ruta):
        return nucleo.resultado(id, nucleo.FALTA, f"falta {capas.CODEX_CONFIG}: Codex no lee los CLAUDE.md de la instancia",
                                arreglo=lambda: _crear(ruta, CONFIG_DEL_PROYECTO))
    datos, error = leer_toml(ruta)
    if error is not None:
        return nucleo.resultado(id, nucleo.FALTA, f"{capas.CODEX_CONFIG} no se puede leer como TOML ({error})", None, _ayuda_del_toml(error))
    lista = datos.get("project_doc_fallback_filenames")
    if isinstance(lista, list) and FALLBACK in lista:
        return nucleo.resultado(id, nucleo.OK, f"{capas.CODEX_CONFIG} trae {FALLBACK} en project_doc_fallback_filenames")
    return nucleo.resultado(id, nucleo.FALTA, f"{capas.CODEX_CONFIG} no trae \"{FALLBACK}\" en project_doc_fallback_filenames: Codex no "
                                              "lee los CLAUDE.md de la instancia", None, AYUDA_CONFIG % CONFIG_DEL_PROYECTO.strip())


def _normal(texto):
    return texto.lstrip("﻿").replace("\r\n", "\n")


def _declarada(lineas, clave, en_cabecera):
    for linea in lineas:
        if en_cabecera and not linea.startswith("#"):
            return None
        if linea.startswith(clave):
            return linea[len(clave):].strip()
        if not en_cabecera and linea == "---":
            return None
    return None


def _md_intacto(texto, plantilla_writer):
    lineas = texto.split("\n")
    if not lineas or lineas[0] != "---":
        return False
    sello = plantilla_writer.huella(texto)
    return sello is not None and sello == _declarada(lineas[1:], plantilla_writer.CLAVE_HASH + ":", False)


def _derivado_por_odd_ws(texto):
    return _normal(texto).startswith(ENCABEZADO.split("%s", 1)[0])


def _leer_utf8(ruta):
    try:
        return ruta.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _revisar_agente(raiz, nombre, bootstrap_agentes, plantilla_writer):
    texto = _leer_utf8(raiz / capas.agente(nombre))
    if texto is None:
        return RevisionDeAgente(nombre, "fuente", None, "no se puede leer como UTF-8")
    texto = plantilla_writer.normalizar(texto)
    if not _md_intacto(texto, plantilla_writer):
        return RevisionDeAgente(nombre, "fuente", None, "se editó fuera de sus bloques o no lo generó la plantilla")
    try:
        esperado = toml(plantilla_writer.agente(bootstrap_agentes.armar(nombre, texto, "codex")))
    except ValueError as error:
        return RevisionDeAgente(nombre, "fuente", None, str(error))
    ruta = raiz / capas.agente_codex(nombre)
    if not os.path.lexists(ruta):
        return RevisionDeAgente(nombre, "falta", esperado, None)
    actual = _leer_utf8(ruta) if ruta.is_file() else None
    if actual is None:
        return RevisionDeAgente(nombre, "ilegible", None, None)
    if _normal(actual) == esperado:
        return RevisionDeAgente(nombre, "ok", esperado, None)
    if _declarada(_normal(actual).split("\n"), CLAVE_HASH, True) == huella(actual):
        return RevisionDeAgente(nombre, "atrasado", esperado, None)
    return RevisionDeAgente(nombre, "editado", None, None)


def revisar_agentes(raiz, declaradas):
    import bootstrap_agentes
    import plantilla_writer

    raiz = Path(raiz)
    revisiones, con_md = [], set()
    for nombre in dict.fromkeys(bootstrap_agentes.nombres_de_agentes(declaradas)):
        if (raiz / capas.agente(nombre)).is_file():
            con_md.add(nombre)
            revisiones.append(_revisar_agente(raiz, nombre, bootstrap_agentes, plantilla_writer))
    carpeta = raiz / capas.CODEX_AGENTES
    for ruta in sorted(carpeta.glob("*.toml")) if carpeta.is_dir() else ():
        texto = _leer_utf8(ruta) if ruta.is_file() else None
        if ruta.stem not in con_md and texto is not None and _derivado_por_odd_ws(texto):
            revisiones.append(RevisionDeAgente(ruta.stem, "sobrante", None, None))
    return revisiones


def _problema(revision):
    nombre, codigo = revision.nombre, revision.codigo
    toml_del_agente, md = capas.agente_codex(nombre), capas.agente(nombre)
    return {
        "falta": f"falta {toml_del_agente}",
        "atrasado": f"{toml_del_agente} quedó atrás de {md}",
        "editado": f"{toml_del_agente} se editó a mano: no se pisa",
        "ilegible": f"{toml_del_agente} no se puede leer como UTF-8: no se pisa",
        "fuente": f"{md} {revision.motivo}: su TOML no se deriva",
        "sobrante": f"{toml_del_agente} es de un agente que ya no existe (falta {md} o su capa salió de la config): no se borra",
    }[codigo]


def _escribir_agentes(raiz):
    import config_loader

    escritos = []
    for revision in revisar_agentes(raiz, config_loader.capas(raiz)):
        if revision.codigo not in ("falta", "atrasado"):
            continue
        ruta = raiz / capas.agente_codex(revision.nombre)
        if revision.codigo == "falta":
            escritos.append(_crear(ruta, revision.esperado))
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
        return nucleo.resultado(id, nucleo.FALTA, f"no se pueden revisar los agentes de Codex: {error}", None, nucleo.AYUDA_CONFIG)
    revisiones = revisar_agentes(raiz, declaradas)
    if not revisiones:
        return nucleo.resultado(id, nucleo.NO_APLICA, f"no hay agentes de la plantilla en {capas.AGENTES} que derivar")
    problemas = [revision for revision in revisiones if revision.codigo != "ok"]
    if not problemas:
        return nucleo.resultado(id, nucleo.OK, f"{len(revisiones)} TOML de {capas.CODEX_AGENTES} al día con su .md")
    a_mano = any(revision.codigo not in ("falta", "atrasado") for revision in problemas)
    detalle = "; ".join(map(_problema, problemas))
    ayuda = AYUDA_AGENTES if a_mano else ""
    if any(revision.codigo in ("falta", "atrasado") for revision in problemas):
        return nucleo.resultado(id, nucleo.FALTA, detalle, None, ayuda, lambda: _escribir_agentes(raiz))
    return nucleo.resultado(id, nucleo.AVISO, detalle, None, ayuda)
