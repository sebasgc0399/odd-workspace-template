import sys

sys.dont_write_bytecode = True

import argparse
import codecs
import glob
import os

from odd_ws import secretos
from odd_ws.archivos import reemplazar

DESCRIPCION = ("Tapa en el lugar los secretos de cada archivo (tokens y claves con un formato concreto), cada uno con su "
               "marcador, como <GITHUB_TOKEN>; conserva la codificacion y los fines de linea, y dice cuantos tapo en cada uno.")
COMODINES = "*?["
BOMS = ((codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"))
ERRORES = {"utf-8": "surrogateescape", "utf-16-le": "strict", "utf-16-be": "strict"}


class NoSePuede(Exception):
    pass


def _visible(ruta):
    return str(ruta).replace("\\", "/")


def archivos(rutas):
    vistos, lista = set(), []
    for ruta in rutas:
        if os.path.isdir(ruta):
            raise NoSePuede("%s es una carpeta: pasa archivos, no carpetas" % _visible(ruta))
        if os.path.isfile(ruta):
            hallados = [ruta]
        elif any(c in ruta for c in COMODINES):
            hallados = sorted(r for r in glob.glob(ruta) if os.path.isfile(r))
            if not hallados:
                raise NoSePuede("ningun archivo coincide con %s" % _visible(ruta))
        else:
            raise NoSePuede("no existe %s" % _visible(ruta))
        for hallado in hallados:
            clave = os.path.normcase(os.path.abspath(hallado))
            if clave not in vistos:
                vistos.add(clave)
                lista.append(hallado)
    return lista


def leer(ruta):
    try:
        with open(ruta, "rb") as f:
            crudo = f.read()
    except OSError as exc:
        raise NoSePuede("no se pudo leer %s (%s)" % (_visible(ruta), exc.strerror or exc))
    bom, codificacion = next(((b, c) for b, c in BOMS if crudo.startswith(b)), (b"", "utf-8"))
    try:
        return bom, codificacion, crudo[len(bom):].decode(codificacion, ERRORES[codificacion])
    except UnicodeDecodeError as exc:
        raise NoSePuede("%s no se puede leer como %s (%s)" % (_visible(ruta), codificacion, exc.reason))


def tapado(ruta, bom, codificacion, texto):
    nuevo, cuantos, error = secretos.intentar_tapar(texto)
    try:
        if error is None:
            return (bom + nuevo.encode(codificacion, ERRORES[codificacion]) if cuantos else None), cuantos
    except Exception as exc:
        error = exc
    raise NoSePuede("error interno al tapar %s (%s)" % (_visible(ruta), error))


def main(argv=None):
    p = argparse.ArgumentParser(prog="tapar.py", description=DESCRIPCION)
    p.add_argument("archivo", nargs="+", metavar="ARCHIVO",
                   help="archivo que se reescribe en el lugar; acepta comodines (entrada/*.diff) aunque el shell no los expanda")
    args = p.parse_args(argv)
    try:
        plan = [(ruta, *tapado(ruta, *leer(ruta))) for ruta in archivos(args.archivo)]
    except NoSePuede as exc:
        print("tapar: %s; no se escribio nada" % exc, file=sys.stderr)
        return 2
    for ruta, nuevo, cuantos in plan:
        if nuevo is not None:
            try:
                reemplazar(ruta, nuevo)
            except OSError as exc:
                print("tapar: no se pudo escribir %s (%s)" % (_visible(ruta), exc.strerror or exc), file=sys.stderr)
                return 2
        print("%s: %d secreto(s) tapado(s)" % (_visible(ruta), cuantos))
    return 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("tapar: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
