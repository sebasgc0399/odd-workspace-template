import sys

sys.dont_write_bytecode = True

from pathlib import Path

from doctor import CLAVE_PLUGIN, HOOKS_PATH, PRE_COMMIT, SETTINGS

CLAVES = ()
PLANTILLAS = Path(__file__).resolve().parent.parent / "plantillas"
PLANTILLA_PRE_COMMIT = "pre-commit"
PERMISOS_DEL_PRE_COMMIT = 0o755


def generar(spec):
    from bootstrap import GIT_HOOKS, GIT_INIT, AccionDeGit, serializar

    return [
        (PRE_COMMIT, (PLANTILLAS / PLANTILLA_PRE_COMMIT).read_bytes(), PERMISOS_DEL_PRE_COMMIT),
        (SETTINGS, serializar({"enabledPlugins": {CLAVE_PLUGIN: True}})),
        AccionDeGit(GIT_INIT, None),
        AccionDeGit(GIT_HOOKS, HOOKS_PATH),
    ]
