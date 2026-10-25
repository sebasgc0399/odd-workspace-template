import json
import os
from collections import namedtuple
from fnmatch import fnmatch
from pathlib import Path

NOMBRE = "workspace.config.json"
NOMBRE_LOCAL = "workspace.local.json"
VERSION_SOPORTADA = 1
MOLDES = ("repo", "propio")

Estado = namedtuple("Estado", "tipo raiz config razon")


class ConfigRota(Exception):
    pass


def inicio_de_sesion(entorno, cwd):
    return entorno.get("CLAUDE_PROJECT_DIR") or cwd


def canonica(ruta):
    return os.path.normcase(os.path.realpath(ruta))


def encontrar_raiz(inicio):
    actual = Path(os.path.abspath(inicio))
    for carpeta in (actual, *actual.parents):
        if (carpeta / NOMBRE).is_file():
            return carpeta
    return None


def _leer_objeto(ruta):
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ConfigRota(f"{ruta.name} no se puede leer como JSON: {error}")
    if not isinstance(datos, dict):
        raise ConfigRota(f"{ruta.name} debe ser un objeto JSON")
    return datos


def _version(config):
    version = config.get("schema_version")
    if isinstance(version, bool) or version != VERSION_SOPORTADA:
        raise ConfigRota(f"schema_version {version!r} no es la que entiende este plugin ({VERSION_SOPORTADA})")
    return version


def _molde(valor, donde):
    if valor not in MOLDES:
        raise ConfigRota(f"{donde} {valor!r} no es válido (repo | propio)")
    return valor


def _repos(config, local):
    rutas = local.get("repos") or {}
    repos = {}
    for clave, valores in (config.get("repos") or {}).items():
        ruta = (rutas.get(clave) or {}).get("path")
        if not ruta:
            raise ConfigRota(f"falta la ruta del repo {clave!r} en {NOMBRE_LOCAL}")
        if not os.path.isdir(ruta):
            raise ConfigRota(f"la ruta del repo {clave!r} no existe: {ruta}")
        repos[clave] = {**(valores or {}), "path": ruta}
    return repos


def _capas(config, repos, molde):
    capas = config.get("layers")
    if not isinstance(capas, dict) or not capas:
        raise ConfigRota("layers debe declarar al menos una capa")
    for nombre, capa in capas.items():
        if not isinstance(capa, dict):
            raise ConfigRota(f"layers.{nombre} debe ser un objeto")
        extensiones = capa.get("extensions")
        if not isinstance(extensiones, list) or not extensiones or not all(isinstance(e, str) and len(e) > 1 and e.startswith(".") for e in extensiones):
            raise ConfigRota(f"layers.{nombre}.extensions debe ser una lista de extensiones con punto")
        for clave in capa.get("repos") or []:
            if clave not in repos:
                raise ConfigRota(f"layers.{nombre} usa el repo {clave!r}, que no está declarado en repos")
        _molde(capa.get("mold_source", molde), f"layers.{nombre}.mold_source")
    return capas


def cargar(raiz):
    raiz = Path(raiz)
    config = _leer_objeto(raiz / NOMBRE)
    version = _version(config)
    ruta_local = raiz / NOMBRE_LOCAL
    local = _leer_objeto(ruta_local) if ruta_local.is_file() else {}
    molde = _molde((config.get("defaults") or {}).get("mold_source", "repo"), "defaults.mold_source")
    repos = _repos(config, local)
    capas = _capas(config, repos, molde)
    return {"raiz": str(raiz), "schema_version": version, "defaults": {"mold_source": molde}, "repos": repos, "layers": capas}


def estado(inicio):
    raiz = encontrar_raiz(inicio)
    if raiz is None:
        return Estado("ausente", None, None, None)
    try:
        return Estado("ok", str(raiz), cargar(raiz), None)
    except ConfigRota as error:
        return Estado("rota", str(raiz), None, str(error))


def molde_de(config, capa):
    return config["layers"][capa].get("mold_source", config["defaults"]["mold_source"])


def _dentro(ruta, carpeta):
    try:
        return os.path.commonpath([ruta, carpeta]) == carpeta
    except ValueError:
        return False


def _reclama(capa, extension):
    return extension in (e.lower() for e in capa["extensions"])


def clasificar(ruta, config):
    archivo = canonica(ruta)
    extension = os.path.splitext(archivo)[1].lower()
    for clave, repo in config["repos"].items():
        if _dentro(archivo, canonica(repo["path"])):
            for nombre, capa in config["layers"].items():
                if clave in (capa.get("repos") or []) and _reclama(capa, extension):
                    return (nombre, clave)
            return None
    raiz = canonica(config["raiz"])
    if _dentro(archivo, raiz):
        relativa = Path(os.path.relpath(archivo, raiz)).as_posix()
        for nombre, capa in config["layers"].items():
            if _reclama(capa, extension) and any(fnmatch(relativa, patron) for patron in capa.get("workshop") or []):
                return (nombre, "taller")
    return None
