import sys

sys.dont_write_bytecode = True

import argparse
import difflib
import os
import subprocess
import tempfile
from collections import namedtuple
from pathlib import Path

import config_loader
from odd_ws import plantillas_instancia as plantillas
from odd_ws.archivos import reemplazar
from odd_ws.comun import raiz_de_instancia

DESCRIPCION = ("Ayuda a fusionar una copia editada de una plantilla del plugin (el CLAUDE.md raíz, la plantilla de los tickets, el "
               ".githooks/pre-commit o la prueba de las reglas de una capa). --diff muestra qué cambió la plantilla entre la versión "
               "de tu copia y la del plugin, con el nombre de tu proyecto; no escribe. --fusionar propone la fusión de 3 vías "
               "(git merge-file) y, con --escribir, reemplaza la copia por ella. Si la fusión choca, muestra solo los bloques en "
               "conflicto y no escribe nada.")
CODIGOS = "Sale con 0; con --fusionar, con la cantidad de conflictos; con 255 por un error de uso o de entorno."
ERROR = 255
MAXIMO_DE_CONFLICTOS = 254
TU_COPIA = "tu copia"
INICIO, FIN = "<<<<<<< ", ">>>>>>> "

Fusion = namedtuple("Fusion", "ruta plantilla desde actual copia base nueva")


class NoSePuede(Exception):
    pass


def _raiz(argumento):
    if argumento:
        if not (Path(argumento) / config_loader.NOMBRE).is_file():
            raise NoSePuede(f"{argumento} no es la raíz de una instancia: no tiene {config_loader.NOMBRE}")
        return Path(argumento)
    raiz = raiz_de_instancia(os.environ, os.getcwd())
    if raiz is None:
        raise NoSePuede(f"no hay {config_loader.NOMBRE} en la carpeta de la sesión ni en sus padres (pasa --raiz)")
    return Path(raiz)


def _relativa(raiz, ruta):
    camino = Path(ruta)
    if camino.is_absolute():
        try:
            camino = Path(os.path.abspath(camino)).relative_to(os.path.abspath(raiz))
        except ValueError:
            raise NoSePuede(f"{ruta} está fuera de la instancia {raiz}")
    return camino.as_posix()


def _version_de_la_copia(revisada, revision):
    return max(revisada.versiones, key=plantillas.orden) if revisada.versiones else revision.base


def preparar(raiz, plugin, ruta):
    revision = plantillas.revisar(raiz, plugin)
    if revision.rota:
        raise NoSePuede(f"la config está rota ({revision.rota}): lo dice el ítem config de /odd-ws:doctor")
    if revision.error:
        raise NoSePuede(f"{revision.error}. {revision.ayuda}")
    revisada = next((r for r in revision.revisadas if r.ruta == ruta), None)
    if revisada is None:
        rutas = [copia.ruta for copia in plantillas.copias(raiz)]
        if ruta in rutas:
            raise NoSePuede(f"{ruta} no existe en la instancia: no hay nada que fusionar")
        raise NoSePuede(f"{ruta} no es una copia de una plantilla del plugin; las de esta instancia son {', '.join(rutas)}")
    desde = _version_de_la_copia(revisada, revision)
    if desde is None:
        raise NoSePuede(f"no se sabe de qué versión del plugin es {ruta}: {config_loader.NOMBRE} no anota "
                        f"«{config_loader.CLAVE_PLANTILLAS}» y ninguna copia coincide con una versión publicada. Fusiónala a mano con "
                        f"{plantillas.DONDE_LEER}")
    tabla, _ = plantillas.leer_tabla(plugin)
    if desde != revision.actual and tabla.get(revisada.plantilla, {}).get(desde) is None:
        raise NoSePuede(f"la plantilla {revisada.plantilla} no existía en la {desde}: no hay una base para fusionar. Fusiónala a mano "
                        f"con {plantillas.DONDE_LEER}")
    base = plantillas.texto_de_la_version(plugin, revisada.plantilla, desde, revision.actual, tabla)
    nueva = plantillas.texto_de_la_version(plugin, revisada.plantilla, revision.actual, revision.actual, tabla)
    if base is None or nueva is None:
        version = desde if base is None else revision.actual
        raise NoSePuede(f"el plugin no trae el texto de la plantilla {revisada.plantilla} de la {version}. {plantillas.AYUDA_DEL_PLUGIN}")
    try:
        copia = plantillas.leer_texto(Path(raiz) / ruta)
    except (OSError, UnicodeDecodeError) as error:
        raise NoSePuede(f"no se puede leer {ruta} como texto UTF-8 ({error})")
    nombre = None
    if revisada.plantilla in plantillas.INDICES:
        nombre = revisada.nombre or plantillas.nombre_de(copia, base)
        if nombre is None:
            raise NoSePuede(f"la primera línea de {ruta} no es la de la plantilla («{base.split(chr(10), 1)[0]}», con el nombre de tu "
                            f"proyecto en lugar de {plantillas.MARCA_NOMBRE}), así que no se sabe el nombre. Fusiónala a mano con "
                            f"{plantillas.DONDE_LEER}")
    return Fusion(ruta, revisada.plantilla, desde, revision.actual, copia, plantillas.renderizar(revisada.plantilla, base, nombre),
                  plantillas.renderizar(revisada.plantilla, nueva, nombre))


def _etiqueta(version):
    return f"plantilla de la {version}"


def diff(fusion):
    lineas = difflib.unified_diff(fusion.base.splitlines(keepends=True), fusion.nueva.splitlines(keepends=True),
                                  fromfile=f"{fusion.ruta} en la {fusion.desde}", tofile=f"{fusion.ruta} en la {fusion.actual}")
    return "".join(linea if linea.endswith("\n") else linea + "\n" for linea in lineas)


def fusionar(fusion):
    with tempfile.TemporaryDirectory(prefix="odd-ws-fusion-") as carpeta:
        rutas = []
        for nombre, texto in (("copia", fusion.copia), ("base", fusion.base), ("nueva", fusion.nueva)):
            rutas.append(os.path.join(carpeta, nombre))
            with open(rutas[-1], "wb") as archivo:
                archivo.write(texto.encode("utf-8"))
        try:
            resultado = subprocess.run(["git", "merge-file", "-p", "-L", TU_COPIA, "-L", _etiqueta(fusion.desde),
                                        "-L", _etiqueta(fusion.actual), *rutas], capture_output=True, stdin=subprocess.DEVNULL)
        except OSError as error:
            raise NoSePuede(f"no se pudo correr git merge-file ({error})")
    if not 0 <= resultado.returncode <= 127:
        raise NoSePuede("git merge-file falló: " + (resultado.stderr.decode("utf-8", "replace").strip() or f"salió con {resultado.returncode}"))
    texto = resultado.stdout.decode("utf-8")
    bloques = _bloques(texto, _etiqueta(fusion.actual))
    if resultado.returncode and not bloques:
        raise NoSePuede(f"git merge-file dice que hay {resultado.returncode} conflictos y no se encuentran sus marcadores")
    return texto, bloques


def _bloques(texto, final):
    bloques, actual = [], None
    for linea in texto.splitlines(keepends=True):
        limpia = linea.rstrip("\r\n")
        if actual is None and limpia == INICIO + TU_COPIA:
            actual = [linea]
        elif actual is not None:
            actual.append(linea)
            if limpia == FIN + final:
                bloques.append("".join(actual))
                actual = None
    return bloques


def _conflictos(fusion, bloques):
    cuantos = "1 conflicto" if len(bloques) == 1 else f"{len(bloques)} conflictos"
    resuelvelos = "resuélvelo" if len(bloques) == 1 else "resuélvelos"
    cabecera = (f"{fusion.ruta}: {cuantos} entre tu copia y la plantilla de la {fusion.actual}, desde la de la {fusion.desde}. "
                f"No se escribió nada: {resuelvelos} en la copia.\n")
    return cabecera + "".join("\n" + (bloque if bloque.endswith("\n") else bloque + "\n") for bloque in bloques)


def correr(args):
    raiz = _raiz(args.raiz)
    plugin = Path(args.plugin) if args.plugin else Path(__file__).resolve().parent.parent
    ruta = _relativa(raiz, args.diff or args.fusionar)
    fusion = preparar(raiz, plugin, ruta)
    if fusion.desde == fusion.actual:
        print(f"{ruta} ya está al día con la plantilla de la {fusion.actual}, la del plugin: no hay nada que fusionar")
        return 0
    if fusion.base == fusion.nueva:
        print(f"{ruta}: la plantilla no cambió de la {fusion.desde} a la {fusion.actual}: no hay nada que fusionar")
        return 0
    if args.diff:
        sys.stdout.write(diff(fusion))
        return 0
    fusionada, bloques = fusionar(fusion)
    if bloques:
        sys.stdout.write(_conflictos(fusion, bloques))
        return min(len(bloques), MAXIMO_DE_CONFLICTOS)
    if fusionada == fusion.copia:
        print(f"{ruta} ya tiene los cambios de la plantilla de la {fusion.actual}: no hay nada que escribir")
        return 0
    if not args.escribir:
        sys.stdout.write(fusionada)
        return 0
    if os.path.islink(raiz / ruta):
        raise NoSePuede(f"{ruta} es un enlace: escribe la fusión a mano en el archivo al que apunta")
    try:
        reemplazar(raiz / ruta, fusionada.encode("utf-8"))
    except OSError as error:
        raise NoSePuede(f"no se pudo escribir {ruta} ({error})")
    print(f"{ruta}: fusionada con la plantilla de la {fusion.actual}. Revisa el cambio con git diff y commitéala.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="fusionar_plantillas.py", allow_abbrev=False, description=DESCRIPCION, epilog=CODIGOS)
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--diff", metavar="COPIA", help="muestra qué cambió la plantilla de esa copia desde su versión; no escribe")
    modo.add_argument("--fusionar", metavar="COPIA", help="propone la fusión de 3 vías de esa copia con la plantilla del plugin")
    p.add_argument("--escribir", action="store_true", help="con --fusionar, si no choca: reemplaza la copia por la fusión")
    p.add_argument("--raiz", help="raíz de la instancia (por defecto, la de la sesión)")
    p.add_argument("--plugin", help="raíz del plugin (por defecto, la de este script)")
    try:
        args = p.parse_args(argv)
    except SystemExit as exc:
        return ERROR if exc.code else 0
    if args.escribir and args.fusionar is None:
        print("fusionar_plantillas: --escribir va con --fusionar", file=sys.stderr)
        return ERROR
    try:
        return correr(args)
    except NoSePuede as exc:
        print(f"fusionar_plantillas: {exc}", file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"fusionar_plantillas: error interno ({exc})", file=sys.stderr)
        sys.exit(ERROR)
