import importlib.util
import os
import re
import sys

ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
SILENCIO = (0, "", b"")

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
