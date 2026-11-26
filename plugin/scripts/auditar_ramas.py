import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
from pathlib import Path

import config_loader
from odd_ws import auditoria_de_ramas
from odd_ws import entregas
from odd_ws.comun import raiz_de_instancia

DESCRIPCION = ("Audita, antes de publicar, las ramas de los tickets activos: hace fetch de cada repo de la config, que solo actualiza "
               "sus refs de origin, y lista por ticket y repo los cambios sin commitear, los commits sin empujar y el trabajo que no "
               "llegó a la rama principal (origin/HEAD, y si no hay, origin/main u origin/master), comparando los parches con git "
               "cherry para que un squash cuente como llegado. Si el fetch de un repo falla, ese repo sale en rojo y sus ramas no se "
               "juzgan con refs viejas. Diagnostica y no opera: no toca ramas, archivos ni el índice.")
CODIGOS = ("Sale con 0 si todo llegó; con 1 si hay algo pendiente, una rama sin juzgar, un ticket sin revisar o un repo en rojo; con 2 "
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="auditar_ramas.py", allow_abbrev=False, description=DESCRIPCION, epilog=CODIGOS)
    p.add_argument("--archivados", action="store_true", help="suma los tickets archivados (las carpetas más hondas de tickets/)")
    p.add_argument("--json", action="store_true", help="da el resultado en JSON, con cada rama, su estado y sus faltas")
    p.add_argument("--raiz", help="raíz de la instancia (por defecto, la de la sesión)")
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        config = config_loader.cargar(_raiz(args.raiz))
    except ErrorEntorno as exc:
        print("auditar_ramas: %s" % exc, file=sys.stderr)
        return 2
    except config_loader.ConfigRota as exc:
        print("auditar_ramas: la config está rota (%s)" % exc, file=sys.stderr)
        return 2
    raiz = config["raiz"]
    tickets = entregas.activos(raiz) + (auditoria_de_ramas.archivados(raiz) if args.archivados else [])
    auditoria = auditoria_de_ramas.auditar(config, tickets)
    if args.json:
        print(json.dumps(auditoria_de_ramas.a_json(auditoria), ensure_ascii=False, indent=2))
    else:
        print("\n".join(auditoria_de_ramas.lineas(auditoria)))
    return 0 if auditoria_de_ramas.todo_llego(auditoria) else 1


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("auditar_ramas: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
