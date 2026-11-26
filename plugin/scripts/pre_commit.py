import sys

sys.dont_write_bytecode = True

import argparse
import codecs
import os
import shlex
import subprocess
from collections import namedtuple
from fnmatch import fnmatchcase

from odd_ws import secretos

REGLAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reglas.py")
SIN_TOCAR_EL_INDICE = ("--no-optional-locks", "-c", "diff.autoRefreshIndex=false")
LO_STAGEADO = ("diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev", "--no-color", "--diff-filter=ACMRT")
SUBMODULO = "160000"
NOMBRES_SECRETOS = (".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_ed25519", "credentials*.json")
DE_EJEMPLO = frozenset({"example", "sample", "template"})
CON_BOM = ((codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"))

Stageado = namedtuple("Stageado", "ruta modo blob")


class GitNoRespondio(Exception):
    pass


def git(raiz, *args, entrada=None):
    try:
        r = subprocess.run(["git", *SIN_TOCAR_EL_INDICE, *args], cwd=raiz, input=entrada, capture_output=True)
    except OSError as error:
        raise GitNoRespondio("git no arrancó: %s" % (error.strerror or error)) from None
    if r.returncode != 0:
        lineas = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitNoRespondio("git %s: %s" % (args[0], lineas[0] if lineas else "salió con %d" % r.returncode))
    return r.stdout


def stageados(raiz):
    partes = git(raiz, *LO_STAGEADO).split(b"\0")
    archivos = []
    for meta, ruta in zip(partes[0::2], partes[1::2]):
        campos = meta.decode("ascii").split()
        archivos.append(Stageado(ruta.decode("utf-8", "replace"), campos[1], campos[3]))
    return archivos


def contenidos(raiz, blobs):
    if not blobs:
        return {}
    salida = git(raiz, "cat-file", "--batch", entrada="".join(blob + "\n" for blob in blobs).encode("ascii"))
    datos, desde = {}, 0
    for blob in blobs:
        fin = salida.index(b"\n", desde)
        cabecera = salida[desde:fin].decode("ascii", "replace").split()
        if len(cabecera) != 3 or cabecera[0] != blob:
            raise GitNoRespondio("git cat-file no devolvió %s: %s" % (blob, " ".join(cabecera)))
        tamano = int(cabecera[2])
        datos[blob] = salida[fin + 1:fin + 1 + tamano]
        desde = fin + 1 + tamano + 1
    return datos


def es_secreto(ruta):
    nombre = ruta.rsplit("/", 1)[-1].lower()
    if DE_EJEMPLO.intersection(nombre.split(".")[1:]):
        return False
    return any(fnmatchcase(nombre, patron) for patron in NOMBRES_SECRETOS)


def texto(datos):
    for bom, codificacion in CON_BOM:
        if datos.startswith(bom):
            return datos[len(bom):].decode(codificacion, "replace")
    return datos.decode("utf-8", "replace")


def revisar(raiz):
    archivos = stageados(raiz)
    nombres = [archivo.ruta for archivo in archivos if es_secreto(archivo.ruta)]
    a_leer = [archivo for archivo in archivos if archivo.modo != SUBMODULO and not es_secreto(archivo.ruta)]
    datos = contenidos(raiz, list(dict.fromkeys(archivo.blob for archivo in a_leer)))
    claves, rutas = [], []
    for archivo in a_leer:
        contenido = texto(datos[archivo.blob])
        if secretos.claves_privadas(contenido):
            claves.append(archivo.ruta)
        primeras = {}
        for linea, fragmento in secretos.rutas_personales(contenido):
            primeras.setdefault(fragmento, linea)
        rutas += [(archivo.ruta, linea, fragmento) for fragmento, linea in primeras.items()]
    return nombres, claves, rutas


def explicar_frenado(nombres, claves):
    lineas = ["pre-commit: commit frenado. Esto no debe salir de tu máquina:"]
    lineas += ["  %s: su nombre es de un archivo de secretos (.env, una clave o un credentials*.json)" % ruta for ruta in nombres]
    lineas += ["  %s: tiene una clave privada pegada" % ruta for ruta in claves]
    lineas.append("Sácalo del stage; el archivo sigue en tu disco:" if len(nombres + claves) == 1 else
                  "Sácalos del stage; los archivos siguen en tu disco:")
    lineas += ["  git restore --staged %s" % shlex.quote(ruta) for ruta in nombres + claves]
    if nombres:
        lineas.append("Si es un ejemplo sin secretos, nómbralo con .example, .sample o .template (como .env.example).")
    if claves:
        lineas.append("Si la clave no va en el repo, bórrala del archivo y vuelve a stagearlo.")
    return "\n".join(lineas)


def explicar_rutas(rutas):
    lineas = ["pre-commit: aviso, lo stageado trae rutas personales (no frena el commit):"]
    lineas += ["  %s:%d: %s" % hallazgo for hallazgo in rutas]
    lineas.append("Si no van a propósito, cámbialas por un marcador como <usuario> antes de que salgan de tu máquina.")
    return "\n".join(lineas)


def correr_reglas(raiz):
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run([sys.executable, REGLAS, "--test", "--raiz", raiz]).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pre_commit.py", allow_abbrev=False,
                                     description="El pre-commit de la instancia: frena los archivos de secretos y las claves "
                                     "privadas stageadas, avisa de las rutas personales y corre reglas.py --test.")
    parser.add_argument("--raiz", required=True, help="raíz de la instancia (la del repo que commitea)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        nombres, claves, rutas = revisar(args.raiz)
    except GitNoRespondio as error:
        print("pre-commit: no se pudo revisar lo stageado (%s); el commit no sigue." % error, file=sys.stderr)
        return 1
    if rutas:
        print(explicar_rutas(rutas), file=sys.stderr)
    if nombres or claves:
        print(explicar_frenado(nombres, claves), file=sys.stderr)
        return 1
    return correr_reglas(args.raiz)


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("pre-commit: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
