import hashlib
import importlib.util
import json
import math
import os
import posixpath
import re
import sys
from collections import namedtuple
from dataclasses import replace

from odd_ws import rutas
from odd_ws.capas import BITACORA
from odd_ws.eventos import POSIX, POWERSHELL, Bloquear, Contexto, Permitir, Preguntar

COMANDO_RUTAS_DE_HOOKS = ("rev-parse", "--git-path", "hooks", "--git-dir", "--git-common-dir")
DecisionDeHooks = namedtuple("DecisionDeHooks", "puede motivo")

ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
FOTO_RE = re.compile(r"([0-9a-f]{40})\.(foto|nuevo)")
DIALECTOS = (POSIX, POWERSHELL)
SILENCIO = (0, "", b"")
PLAZO_POR_DEFECTO = 8
HOST_POR_DEFECTO = "claude-code"
PRECEDENCIA = (Bloquear, Preguntar, Contexto)

VARIABLES_DE_REPO_GIT = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX",
    "GIT_SHALLOW_FILE", "GIT_COMMON_DIR",
)


def entorno_git(base=None):
    origen = os.environ if base is None else base
    env = {k: v for k, v in origen.items() if k not in VARIABLES_DE_REPO_GIT}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "diff.autoRefreshIndex"
    env["GIT_CONFIG_VALUE_0"] = "false"
    return env


def _ruta_de_git(texto, raiz):
    ruta = texto.strip()
    return os.path.normpath(ruta if os.path.isabs(ruta) else os.path.join(str(raiz), ruta))


def _misma_carpeta(a, b):
    from config_loader import canonica

    return canonica(a) == canonica(b)


def decidir_hooks(raiz, salida):
    lineas = [linea for linea in (salida or "").splitlines() if linea.strip()]
    if len(lineas) != 3:
        return DecisionDeHooks(False, "git no dijo dónde están los hooks del repo")
    carpeta, git_dir, git_comun = (_ruta_de_git(linea, raiz) for linea in lineas)
    if not _misma_carpeta(git_dir, git_comun):
        return DecisionDeHooks(False, "la raíz es un worktree enlazado y --local cambiaría la config de todos sus checkouts")
    try:
        with os.scandir(carpeta) as entradas:
            propios = sorted(entrada.name for entrada in entradas if not entrada.name.endswith(".sample"))
    except FileNotFoundError:
        propios = []
    except OSError as error:
        return DecisionDeHooks(False, f"no se puede leer la carpeta de hooks {carpeta} ({error.strerror or error})")
    if propios:
        return DecisionDeHooks(False, f"hay hooks propios en {carpeta} ({', '.join(propios)}), que dejarían de correr")
    return DecisionDeHooks(True, "")


def plazo_de(argv):
    try:
        valor = float(argv[argv.index("--plazo") + 1])
    except (ValueError, IndexError):
        return PLAZO_POR_DEFECTO
    return valor if math.isfinite(valor) and valor > 0 else PLAZO_POR_DEFECTO


def host_de(argv):
    for posicion, argumento in enumerate(argv):
        if argumento.startswith("--host="):
            return argumento[len("--host="):] or None
        if argumento == "--host":
            return argv[posicion + 1] if posicion + 1 < len(argv) else None
    return HOST_POR_DEFECTO


def _texto(decision):
    if isinstance(decision, (Bloquear, Preguntar)):
        return decision.motivo
    return decision.texto if isinstance(decision, Contexto) else None


def combinar(decisiones):
    textos = [texto for texto in map(_texto, decisiones) if texto is not None]
    for tipo in PRECEDENCIA:
        if any(isinstance(decision, tipo) for decision in decisiones):
            return tipo("\n\n".join(textos))
    return Permitir()


def _aislada(decidir, evento):
    try:
        return decidir(evento)
    except Exception:
        return Permitir()


def por_ruta(evento, decidir):
    if len(evento.rutas) < 2:
        return decidir(evento)
    return combinar([_aislada(decidir, replace(evento, rutas=(ruta,))) for ruta in evento.rutas])


def temporal(entorno):
    if os.name == "nt":
        sistema = entorno.get("SYSTEMROOT") or entorno.get("WINDIR")
        return entorno.get("TEMP") or entorno.get("TMP") or (os.path.join(sistema, "temp") if sistema else None)
    return _temporal_posix(entorno)


def _temporal_posix(entorno):
    return entorno.get("TMPDIR") or "/tmp"


def _uid():
    return os.getuid()


def carpeta_scratch(entorno):
    if rutas.PLATAFORMA == "win32":
        carpeta = temporal(entorno)
        return os.path.join(carpeta, "claude") if carpeta else None
    carpeta = "/tmp" if rutas.PLATAFORMA == "darwin" else _temporal_posix(entorno)
    return posixpath.join(carpeta, "claude-%d" % _uid())


def id_valido(valor):
    return isinstance(valor, str) and ID_RE.fullmatch(valor) is not None


def clave_foto(ruta):
    return hashlib.sha1(os.path.normcase(os.path.abspath(ruta)).encode("utf-8")).hexdigest()


def anotar_en_bitacora(carpeta, registro):
    linea = (json.dumps(registro, ensure_ascii=True) + "\n").encode("ascii")
    banderas = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
    descriptor = os.open(os.path.join(carpeta, BITACORA), banderas, 0o644)
    try:
        os.write(descriptor, linea)
    finally:
        os.close(descriptor)


def _cadena_valida(valor):
    if not isinstance(valor, str) or valor == "":
        return False
    try:
        valor.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _registro_valido(registro):
    if not isinstance(registro, dict):
        return False
    if registro.get("tipo") == "edicion":
        rutas = registro.get("rutas")
        return isinstance(rutas, list) and bool(rutas) and all(_cadena_valida(ruta) for ruta in rutas)
    if registro.get("tipo") == "shell":
        return _cadena_valida(registro.get("comando")) and registro.get("dialecto") in DIALECTOS
    return False


def leer_bitacora(carpeta):
    with open(os.path.join(carpeta, BITACORA), "rb") as f:
        crudo = f.read()
    registros, rotas = [], 0
    for linea in crudo.split(b"\n"):
        if not linea.strip():
            continue
        try:
            registro = json.loads(linea.decode("utf-8"))
        except ValueError:
            registro = None
        if _registro_valido(registro):
            registros.append(registro)
        else:
            rotas += 1
    return registros, rotas


def _fotos(carpeta):
    return [(encontrada.group(1), encontrada.group(2), os.path.join(carpeta, nombre)) for nombre in sorted(os.listdir(carpeta))
            for encontrada in [FOTO_RE.fullmatch(nombre)] if encontrada]


def _ruta_de_la_marca(marca, clave):
    try:
        with open(marca, encoding="utf-8") as f:
            ruta = f.read()
    except (OSError, ValueError):
        return None
    return ruta if ruta and os.path.isabs(ruta) and clave_foto(ruta) == clave else None


def archivos_de_la_bitacora(carpeta):
    faltas, registros, rotas, existe, leida = [], [], 0, True, False
    try:
        registros, rotas = leer_bitacora(carpeta)
        leida = True
    except FileNotFoundError:
        existe = False
    except OSError as error:
        faltas.append("no se pudo leer la bitácora: %r" % error)
    try:
        fotos = _fotos(carpeta)
    except FileNotFoundError:
        fotos = []
    except OSError as error:
        fotos = []
        faltas.append("no se pudo leer la carpeta de fotos: %r" % error)
    if not existe and fotos:
        faltas.append("la bitácora no está, aunque writer_guard sacó %d fotos de este writer" % len(fotos))
    if leida and not registros and not rotas:
        faltas.append("la bitácora está vacía")
    if rotas:
        faltas.append("la bitácora tiene %d líneas rotas" % rotas)
    archivos = []
    for registro in registros:
        for ruta in registro.get("rutas", ()):
            if ruta not in archivos:
                archivos.append(ruta)
    claves = {clave_foto(ruta) for ruta in archivos}
    recuperadas = perdidas = 0
    for clave, tipo, marca in fotos:
        if clave in claves:
            continue
        ruta = _ruta_de_la_marca(marca, clave) if tipo == "nuevo" else None
        if ruta is None:
            perdidas += 1
            continue
        archivos.append(ruta)
        claves.add(clave)
        recuperadas += 1
    if recuperadas:
        faltas.append("%d archivos nuevos no estaban en la bitácora y salen de su marca .nuevo" % recuperadas)
    if perdidas:
        faltas.append("%d archivos con foto no están en la bitácora y la compuerta no los puede medir" % perdidas)
    return archivos, faltas


def comandos_de_la_bitacora(carpeta):
    try:
        registros, _ = leer_bitacora(carpeta)
    except OSError:
        return None
    return [(registro["dialecto"], registro["comando"]) for registro in registros if registro["tipo"] == "shell"]


def decodificar(crudo):
    texto = crudo.decode("utf-8", errors="replace")
    return texto[1:] if texto.startswith("﻿") else texto


def lineas(texto):
    partes = texto.split("\n")
    if partes and partes[-1] == "":
        partes.pop()
    return [(i + 1, t.rstrip("\r")) for i, t in enumerate(partes)]


def cargar_por_ruta(ruta, nombre):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def raiz_de_instancia(entorno, cwd):
    from config_loader import encontrar_raiz, inicio_de_sesion

    return encontrar_raiz(inicio_de_sesion(entorno, cwd))


def correr_hook(manejador, entrada=None, salida=None, error=None):
    entrada = entrada or sys.stdin.buffer
    salida = salida or sys.stdout
    error = error or sys.stderr
    try:
        codigo, texto, crudo = manejador(entrada.read())
        if texto:
            salida.write(texto)
            salida.flush()
        if crudo:
            error.buffer.write(crudo)
            error.buffer.flush()
        return codigo
    except (Exception, SystemExit):
        return 0
