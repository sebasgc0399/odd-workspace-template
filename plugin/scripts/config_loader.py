import json
import os
import re
from collections import namedtuple
from functools import lru_cache
from pathlib import Path

NOMBRE = "workspace.config.json"
NOMBRE_LOCAL = "workspace.local.json"
VERSION_SOPORTADA = 1
MOLDES = ("repo", "propio")
PREFIJO_RE = re.compile(r"[A-Z][A-Z0-9]*")

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
        repos[clave] = {**(valores or {}), "path": ruta, "worktrees": _worktrees(ruta)}
    return repos


def _worktrees(ruta):
    registro = Path(ruta) / ".git" / "worktrees"
    try:
        entradas = sorted(registro.iterdir())
    except OSError:
        return []
    arboles = []
    for entrada in entradas:
        try:
            texto = (entrada / "gitdir").read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            continue
        if not texto:
            continue
        gitdir = texto if os.path.isabs(texto) else os.path.join(entrada, texto)
        arbol = os.path.dirname(os.path.normpath(gitdir))
        if os.path.isdir(arbol):
            arboles.append(arbol)
    return arboles


def _globs(capa, nombre, campo):
    if campo not in capa:
        return
    valor = capa[campo]
    if campo == "workshop" and valor in (None, []):
        return
    if not isinstance(valor, list) or not valor or not all(isinstance(p, str) and p for p in valor):
        raise ConfigRota(f"layers.{nombre}.{campo} debe ser una lista de globs no vacíos")
    for patron in valor:
        try:
            _glob_a_regex(patron)
        except re.error as error:
            raise ConfigRota(f"layers.{nombre}.{campo}: el glob {patron!r} no es válido ({error})")


def _cierre_de_clase(parte, i):
    j = i + 1
    if j < len(parte) and parte[j] in "!^":
        j += 1
    if j < len(parte) and parte[j] == "]":
        j += 1
    return parte.find("]", j)


def _segmento(parte):
    salida, i = [], 0
    while i < len(parte):
        letra = parte[i]
        if letra == "*":
            salida.append("[^/]*")
        elif letra == "?":
            salida.append("[^/]")
        elif letra == "[" and _cierre_de_clase(parte, i) != -1:
            fin = _cierre_de_clase(parte, i)
            inicio = i + 1
            negada = parte[inicio] in "!^"
            clase = parte[inicio + 1 if negada else inicio:fin]
            clase = "".join("\\" + ch if ch in "\\[]&~|^" else ch for ch in clase)
            salida.append("[%s%s]" % ("^/" if negada else "", clase))
            i = fin
        else:
            salida.append(re.escape(letra))
        i += 1
    return "".join(salida)


@lru_cache(maxsize=256)
def _glob_a_regex(patron):
    partes = patron.split("/")
    salida = []
    for i, parte in enumerate(partes):
        ultima = i == len(partes) - 1
        if parte == "**":
            salida.append(".*" if ultima else "(?:[^/]*/)*")
        else:
            salida.append(_segmento(parte) + ("" if ultima else "/"))
    return re.compile("".join(salida), re.IGNORECASE | re.DOTALL)


def coincide(ruta, patron):
    return _glob_a_regex(patron).fullmatch(ruta) is not None


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
        _globs(capa, nombre, "workshop")
        _globs(capa, nombre, "match")
        if "rule_prefix" in capa:
            prefijo = capa["rule_prefix"]
            if not isinstance(prefijo, str) or not PREFIJO_RE.fullmatch(prefijo):
                raise ConfigRota(f"layers.{nombre}.rule_prefix {prefijo!r} debe ser mayúsculas y dígitos, empezando por letra")
            duenos = [otra for otra, datos in capas.items() if otra != nombre and isinstance(datos, dict) and datos.get("rule_prefix") == prefijo]
            if duenos:
                raise ConfigRota(f"layers.{nombre}.rule_prefix {prefijo!r} ya lo usa layers.{duenos[0]}")
    return capas


def capas(raiz):
    config = _leer_objeto(Path(raiz) / NOMBRE)
    _version(config)
    molde = _molde((config.get("defaults") or {}).get("mold_source", "repo"), "defaults.mold_source")
    return _capas(config, config.get("repos") or {}, molde)


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


def _relativa(archivo, carpeta):
    return Path(os.path.relpath(archivo, carpeta)).as_posix()


def clasificar(ruta, config):
    archivo = canonica(ruta)
    extension = os.path.splitext(archivo)[1].lower()
    for clave, repo in config["repos"].items():
        arboles = [canonica(r) for r in [repo["path"], *repo.get("worktrees", [])]]
        arboles = [r for r in arboles if _dentro(archivo, r)]
        if not arboles:
            continue
        arbol = max(arboles, key=len)
        relativa = _relativa(archivo, arbol)
        for nombre, capa in config["layers"].items():
            if clave in (capa.get("repos") or []) and _reclama(capa, extension):
                if "match" not in capa or any(coincide(relativa, patron) for patron in capa["match"]):
                    return (nombre, clave)
        return None
    raiz = canonica(config["raiz"])
    if _dentro(archivo, raiz):
        relativa = _relativa(archivo, raiz)
        for nombre, capa in config["layers"].items():
            if _reclama(capa, extension) and any(coincide(relativa, patron) for patron in capa.get("workshop") or []):
                return (nombre, "taller")
    return None
