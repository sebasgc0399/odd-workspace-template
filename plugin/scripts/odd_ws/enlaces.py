import os
import re
from collections import namedtuple
from pathlib import Path

ESQUEMA_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]+:")
LINK_MD_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)(#[^)\s]*)?\)")
ENLACE_RE = re.compile(r"\[([^\]]*)\]\((?:<([^<>\n]*)>|([^)\s]+))\)")
RUTA_DE_LA_MAQUINA_RE = re.compile(r"[a-zA-Z]:|[/\\]|~(?:[/\\]|\Z)")
ARCHIVO, CARPETA = "archivo", "carpeta"
NO_EXISTE, DE_LA_MAQUINA = "no existe", "ruta de la máquina"

Enlace = namedtuple("Enlace", "texto destino ruta tipo")
Revisado = namedtuple("Revisado", "texto destino motivo")


def existe(ruta):
    try:
        return ruta.exists()
    except (OSError, ValueError):
        return False


def resolver(ruta):
    try:
        return ruta.resolve()
    except (OSError, ValueError):
        return ruta


def _absoluta(ruta):
    try:
        return Path(os.path.abspath(ruta)).as_posix()
    except (OSError, ValueError):
        return ruta.as_posix()


def _tipo(ruta):
    real = resolver(ruta)
    if not existe(real):
        return None
    return CARPETA if real.is_dir() else ARCHIVO


def es_ruta_de_la_maquina(destino):
    return RUTA_DE_LA_MAQUINA_RE.match(destino) is not None


def _crudos(texto):
    for m in ENLACE_RE.finditer(texto):
        crudo = m.group(2) if m.group(2) is not None else m.group(3)
        destino = crudo.split("#", 1)[0]
        if destino:
            yield " ".join(m.group(1).split()), crudo, destino


def enlaces(texto, carpeta):
    for nombre, crudo, destino in _crudos(texto):
        if ESQUEMA_RE.match(destino):
            yield Enlace(nombre, crudo, None, None)
            continue
        ruta = Path(carpeta) / destino
        yield Enlace(nombre, destino, _absoluta(ruta), _tipo(ruta))


def revisar(texto, carpeta):
    for nombre, _, destino in _crudos(texto):
        if es_ruta_de_la_maquina(destino):
            yield Revisado(nombre, destino, DE_LA_MAQUINA)
        elif not ESQUEMA_RE.match(destino):
            yield Revisado(nombre, destino, None if existe(resolver(Path(carpeta) / destino)) else NO_EXISTE)
