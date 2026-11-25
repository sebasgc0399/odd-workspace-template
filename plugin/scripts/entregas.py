import sys

sys.dont_write_bytecode = True

import argparse
import os
import subprocess
import time
from pathlib import Path

import config_loader
from odd_ws import capas
from odd_ws import entregas
from odd_ws import porque
from odd_ws.comun import raiz_de_instancia

DESCRIPCION = ("Lista los tickets activos con la entrega pendiente: por cada repo de su «Worktree y rama», cambios sin commitear en la "
               "carpeta de la rama, commits que no están en origin/<rama> o una rama que nunca se empujó. Mira solo las refs locales, "
               "sin fetch. Con --confirmar, anota la huella del ticket en %s y el aviso de inicio de sesión calla hasta que cambien sus "
               "ramas o sus archivos." % capas.ENTREGAS)
CODIGOS = ("Sale con 0 si no hay nada pendiente o si confirmó; con 1 si lista algo pendiente o si quedaron tickets sin revisar; con 2 "
           "por un error de uso o de entorno.")


class ErrorEntorno(Exception):
    pass


def _raiz(argumento):
    if argumento:
        if not (Path(argumento) / config_loader.NOMBRE).is_file():
            raise ErrorEntorno("%s no es la raíz de una instancia: no tiene %s" % (argumento, config_loader.NOMBRE))
        return argumento
    raiz = raiz_de_instancia(os.environ, os.getcwd())
    if raiz is None:
        raise ErrorEntorno("no hay %s en la carpeta de la sesión ni en sus padres (pasa --raiz)" % config_loader.NOMBRE)
    return str(raiz)


def _confirmar(config, nombre, limite):
    try:
        ticket, guardado = entregas.confirmar(config, nombre, limite, time.strftime("%Y-%m-%dT%H:%M:%S"))
    except entregas.Rechazo as exc:
        print("entregas: %s" % exc, file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("entregas: %s para revisar %s, así que no se confirmó nada" % (entregas.SIN_TIEMPO, nombre), file=sys.stderr)
        return 2
    if guardado:
        print("%s: confirmado. Calla hasta que cambien sus ramas o sus archivos." % ticket)
    else:
        print("%s: no tiene nada pendiente, así que no hace falta confirmarlo." % ticket)
    return 0


def _listar(config, limite):
    revision = entregas.revisar(config, limite)
    for ticket, pendiente in revision.pendientes:
        print(entregas.linea(ticket, pendiente))
    quedaron = entregas.sin_revisar(revision)
    if quedaron:
        print(quedaron + ".")
    if not revision.pendientes and not quedaron:
        print(entregas.NADA)
    return 1 if revision.pendientes or quedaron else 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="entregas.py", allow_abbrev=False, description=DESCRIPCION, epilog=CODIGOS)
    p.add_argument("--confirmar", metavar="TICKET", help="anota la huella del ticket (el nombre de su carpeta, o su id si no hay otro "
                                                         "con el mismo)")
    p.add_argument("--raiz", help="raíz de la instancia (por defecto, la de la sesión)")
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        config = config_loader.cargar(_raiz(args.raiz))
    except ErrorEntorno as exc:
        print("entregas: %s" % exc, file=sys.stderr)
        return 2
    except config_loader.ConfigRota as exc:
        print("entregas: la config está rota (%s)" % exc, file=sys.stderr)
        return 2
    limite = porque.hasta(entregas.PLAZO_DEL_CLI)
    if args.confirmar is not None:
        return _confirmar(config, args.confirmar, limite)
    return _listar(config, limite)


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("entregas: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
