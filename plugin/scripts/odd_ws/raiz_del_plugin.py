import json
import os
import re
from pathlib import Path

import config_loader

COPIA_DE_EMERGENCIA = ".claude/plugin"
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")


def vigente():
    return Path(__file__).resolve().parents[2]


def misma_carpeta(a, b):
    if config_loader.canonica(a) == config_loader.canonica(b):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def anotar(local, datos, plugin):
    local.write_bytes((json.dumps({**datos, "plugin_root": str(plugin)}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return f"plugin_root = {plugin} en {local}"


def seguir_al_vigente(raiz, plugin=None):
    plugin = Path(plugin) if plugin is not None else vigente()
    raiz = Path(raiz)
    if (raiz / COPIA_DE_EMERGENCIA / "scripts" / "reglas.py").is_file():
        return None
    local = raiz / config_loader.NOMBRE_LOCAL
    try:
        datos = json.loads(local.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    anotado = datos.get("plugin_root") if isinstance(datos, dict) else None
    if not isinstance(anotado, str) or not anotado:
        return None
    anterior = Path(anotado)
    if not (VERSION.fullmatch(anterior.name) and VERSION.fullmatch(plugin.name)):
        return None
    if misma_carpeta(anterior, plugin) or not misma_carpeta(anterior.parent, plugin.parent):
        return None
    if not (plugin / "scripts" / "reglas.py").is_file():
        return None
    try:
        anotar(local, datos, plugin)
    except OSError:
        return None
    return (f"odd-ws: {config_loader.NOMBRE_LOCAL} apuntaba a la versión {anterior.name} del plugin y ahora apunta a la "
            f"{plugin.name}, la de esta sesión: el pre-commit de la instancia corre las reglas de la versión vigente.")
