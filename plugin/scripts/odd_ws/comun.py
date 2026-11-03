import importlib.util
import math
import os
import re
import sys
from collections import namedtuple

COMANDO_RUTAS_DE_HOOKS = ("rev-parse", "--git-path", "hooks", "--git-dir", "--git-common-dir")
DecisionDeHooks = namedtuple("DecisionDeHooks", "puede motivo")

ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
SILENCIO = (0, "", b"")
PLAZO_POR_DEFECTO = 8

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
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


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


def temporal(entorno):
    if os.name == "nt":
        sistema = entorno.get("SYSTEMROOT") or entorno.get("WINDIR")
        return entorno.get("TEMP") or entorno.get("TMP") or (os.path.join(sistema, "temp") if sistema else None)
    return entorno.get("TMPDIR") or "/tmp"


def id_valido(valor):
    return isinstance(valor, str) and ID_RE.fullmatch(valor) is not None


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
