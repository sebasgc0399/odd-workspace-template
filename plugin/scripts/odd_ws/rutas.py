import os
import posixpath
import re
import sys
import unicodedata

PLATAFORMA = sys.platform
DRIVE = re.compile(r"^[a-z]:")
UNIDAD_ABSOLUTA = re.compile(r"^[a-z]:/")
UNIDAD_SOLA = re.compile(r"[A-Za-z]:")
GIT_BASH_DRIVE = re.compile(r"^/([a-z])/")
COMODIN = re.compile(r"[*?\[{]|[@+!]$")
VARIABLE_RE = re.compile(r"\$\{(\w+)\}|\$env:(\w+)|\$(\w+)|%(\w+)%", re.IGNORECASE)


def normalizar(ruta):
    r = ruta.strip().replace("\\", "/")
    m = GIT_BASH_DRIVE.match(r.lower())
    if m and len(r) > 2:
        r = m.group(1) + ":" + r[2:]
    return r


def es_relativa(r):
    low = r.lower()
    return not (low.startswith(("/", "~", "$", "%")) or DRIVE.match(low))


def caso(r):
    return r.lower() if os.name == "nt" else r


def plegar(r):
    return unicodedata.normalize("NFC", r).lower() if PLATAFORMA == "darwin" else r


def _valor(nombre, cwd, de_entorno, variable):
    if not de_entorno and nombre.upper() == "PWD":
        return cwd or None
    return variable(nombre)


def expandir(ruta, cwd, variable):
    if ruta.startswith("~"):
        if ruta[1:2] not in ("", "/", "\\"):
            return None, None
        casa = _valor("HOME", cwd, True, variable) or _valor("USERPROFILE", cwd, True, variable)
        if not casa:
            return None, None
        ruta = casa + ruta[1:]
    salida, i = [], 0
    for m in VARIABLE_RE.finditer(ruta):
        nombre = next(g for g in m.groups() if g)
        valor = _valor(nombre, cwd, m.group(0).lower().startswith("$env:"), variable)
        if valor is None:
            previo = "".join(salida) + ruta[i:m.start()]
            corte = max(previo.rfind("/"), previo.rfind("\\"))
            return None, (previo[:corte + 1] if corte >= 0 else None)
        salida.append(ruta[i:m.start()] + valor)
        i = m.end()
    salida.append(ruta[i:])
    return "".join(salida), None


def unidad(cwd):
    c = normalizar(cwd) if cwd else ""
    return c[:2] if UNIDAD_ABSOLUTA.match(c.lower()) else None


def ubicar(ruta, cwd):
    r = normalizar(ruta)
    if es_relativa(r):
        if not cwd:
            return None
        r = normalizar(cwd) + "/" + r
    elif os.name == "nt" and r.startswith("/") and not r.startswith("//"):
        letra = unidad(cwd)
        if letra is None:
            return None
        r = letra + r
    if not absoluta(r):
        return None
    if PLATAFORMA == "win32" or not r.startswith("/") or ".." not in r.split("/"):
        r = posixpath.normpath(r)
    if UNIDAD_SOLA.fullmatch(r):
        r += "/"
    return caso(r) if absoluta(r) else None


def absoluta(r):
    return r.startswith("/") or UNIDAD_ABSOLUTA.match(r.lower()) is not None


def resolver(ruta, cwd, variable):
    expandida, _ = expandir(ruta.strip(), cwd, variable)
    return None if expandida is None else ubicar(expandida, cwd)


def antes_del_comodin(ruta):
    m = COMODIN.search(ruta)
    if m is None:
        return None
    previo = ruta[:m.start()]
    corte = max(previo.rfind("/"), previo.rfind("\\"))
    return previo[:corte + 1]
