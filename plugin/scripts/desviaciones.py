import sys

sys.dont_write_bytecode = True

import argparse
import os
from pathlib import Path

import config_loader
from odd_ws import desviaciones
from odd_ws.comun import raiz_de_instancia

DESCRIPCION = ("Imprime las desviaciones conocidas de la instancia (%s: código que parece un error y es a propósito, con su "
               "porqué), una por línea, para el prompt de los revisores de /odd-ws:revisar; sin el archivo, «%s». Solo lectura."
               % (desviaciones.ARCHIVO, desviaciones.NINGUNA))
CODIGOS = ("Sale con 0; con 1 si alguna fila está mal formada (las válidas se imprimen igual y los problemas van a stderr); "
           "con 2 por un error de uso o de entorno.")


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
    return raiz


def main(argv=None):
    p = argparse.ArgumentParser(prog="desviaciones.py", allow_abbrev=False, description=DESCRIPCION, epilog=CODIGOS)
    p.add_argument("--raiz", help="raíz de la instancia (por defecto, la de la sesión)")
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        filas, problemas = desviaciones.cargar(_raiz(args.raiz))
    except ErrorEntorno as exc:
        print("desviaciones: %s" % exc, file=sys.stderr)
        return 2
    except config_loader.ConfigRota as exc:
        print("desviaciones: la config está rota (%s)" % exc, file=sys.stderr)
        return 2
    print("\n".join(desviaciones.linea(fila) for fila in filas) if filas else desviaciones.NINGUNA)
    for problema in problemas:
        print("desviaciones: %s" % desviaciones.texto_del_problema(problema), file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("desviaciones: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
