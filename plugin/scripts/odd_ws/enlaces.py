import os
import re
from collections import namedtuple
from pathlib import Path

ESQUEMA_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]+:")
LINK_MD_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)(#[^)\s]*)?\)")
ENLACE_RE = re.compile(r"\[([^\]]*)\]\((?:<([^<>\n]*)>|([^)\s]+))\)")
ARCHIVO, CARPETA = "archivo", "carpeta"

Enlace = namedtuple("Enlace", "texto destino ruta tipo")


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


def enlaces(texto, carpeta):
    for m in ENLACE_RE.finditer(texto):
        crudo = m.group(2) if m.group(2) is not None else m.group(3)
        destino = crudo.split("#", 1)[0]
        if not destino:
            continue
        nombre = " ".join(m.group(1).split())
        if ESQUEMA_RE.match(destino):
            yield Enlace(nombre, crudo, None, None)
            continue
        ruta = Path(carpeta) / destino
        yield Enlace(nombre, destino, _absoluta(ruta), _tipo(ruta))
