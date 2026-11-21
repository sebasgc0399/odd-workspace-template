import sys

sys.dont_write_bytecode = True

from pathlib import Path

import config_loader
from doctor import CLAVE_PLUGIN, GITATTRIBUTES, HOOKS_PATH, LINEA_EOL, PRE_COMMIT, SETTINGS
from odd_ws import capas

CLAVES = ()
PLANTILLAS = Path(__file__).resolve().parent.parent / "plantillas"
PLANTILLA_PRE_COMMIT = "pre-commit"
PERMISOS_DEL_PRE_COMMIT = 0o755


def generar(spec):
    from bootstrap import GIT_HOOKS, GIT_INIT, AccionDeGit, serializar

    settings = serializar({"enabledPlugins": {CLAVE_PLUGIN: True}})
    del_ticket = [] if config_loader.perfil_de(spec["config"]) == config_loader.CONTROLES else [(capas.TICKET_SETTINGS, settings)]
    return [
        (PRE_COMMIT, (PLANTILLAS / PLANTILLA_PRE_COMMIT).read_bytes(), PERMISOS_DEL_PRE_COMMIT),
        (GITATTRIBUTES, (LINEA_EOL + "\n").encode("utf-8")),
        (SETTINGS, settings),
        *del_ticket,
        AccionDeGit(GIT_INIT, None),
        AccionDeGit(GIT_HOOKS, HOOKS_PATH),
    ]
