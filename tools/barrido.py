import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

LISTA_POR_DEFECTO = Path.home() / ".odd-ws" / "denylist.txt"
ESPACIOS = re.compile(r"\s+")
USO = "uso: barrido.py --staged | --paths <ruta>... | --autoprueba"


class NoSePuedeBarrer(Exception):
    pass


def normalizar(texto):
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(caracter for caracter in descompuesto if not unicodedata.combining(caracter))
    return ESPACIOS.sub(" ", sin_tildes.casefold())


def decodificar(datos):
    if datos.startswith((b"\xff\xfe", b"\xfe\xff")):
        return datos.decode("utf-16", errors="replace")
    if datos.startswith(b"\xef\xbb\xbf"):
        return datos[3:].decode("utf-8", errors="replace")
    muestra = datos[:4096]
    if len(muestra) >= 4:
        if muestra[1::2].count(0) > len(muestra) // 4 and muestra[0::2].count(0) == 0:
            return datos.decode("utf-16-le", errors="replace")
        if muestra[0::2].count(0) > len(muestra) // 4 and muestra[1::2].count(0) == 0:
            return datos.decode("utf-16-be", errors="replace")
    return datos.decode("utf-8", errors="replace")


def ruta_de_la_lista():
    return Path(os.environ.get("ODD_WS_DENYLIST") or LISTA_POR_DEFECTO)


def cargar_lista(ruta):
    if not ruta.is_file():
        raise NoSePuedeBarrer(f"no existe la lista negra ({ruta})")
    terminos = []
    for linea in decodificar(ruta.read_bytes()).splitlines():
        limpia = linea.strip()
        if limpia and not limpia.startswith("#"):
            normalizado = normalizar(limpia).strip()
            if normalizado:
                terminos.append((limpia, normalizado))
    if not terminos:
        raise NoSePuedeBarrer(f"la lista negra está vacía ({ruta})")
    return terminos


def buscar(texto, terminos):
    hallazgos = []
    for numero, linea in enumerate(texto.splitlines(), 1):
        normalizada = normalizar(linea)
        for original, termino in terminos:
            if termino in normalizada:
                hallazgos.append((numero, original))
    return hallazgos


def barrer(ruta_visible, datos, terminos):
    hallazgos = [(ruta_visible, 0, termino) for _, termino in buscar(ruta_visible, terminos)]
    hallazgos += [(ruta_visible, numero, termino) for numero, termino in buscar(decodificar(datos), terminos)]
    return hallazgos


def git(raiz, *args):
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True)


def raiz_del_repo():
    resultado = git(os.getcwd(), "rev-parse", "--show-toplevel")
    if resultado.returncode != 0:
        raise NoSePuedeBarrer("--staged necesita correr dentro de un repositorio git")
    return resultado.stdout.decode("utf-8").strip()


def barrer_stageado(terminos):
    raiz = raiz_del_repo()
    listado = git(raiz, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    if listado.returncode != 0:
        raise NoSePuedeBarrer("git no pudo listar lo stageado: " + listado.stderr.decode("utf-8", "replace").strip())
    hallazgos = []
    for ruta in (parte for parte in listado.stdout.decode("utf-8").split("\0") if parte):
        contenido = git(raiz, "show", f":{ruta}")
        if contenido.returncode != 0:
            raise NoSePuedeBarrer(f"git no pudo leer {ruta} del índice")
        hallazgos += barrer(ruta, contenido.stdout, terminos)
    return hallazgos


def archivos_en_disco(rutas):
    for ruta in map(Path, rutas):
        if ruta.is_dir():
            yield from (archivo for archivo in sorted(ruta.rglob("*")) if archivo.is_file() and ".git" not in archivo.parts)
        elif ruta.is_file():
            yield ruta
        else:
            raise NoSePuedeBarrer(f"no existe {ruta}")


def barrer_en_disco(rutas, terminos):
    hallazgos = []
    for archivo in archivos_en_disco(rutas):
        hallazgos += barrer(archivo.as_posix(), archivo.read_bytes(), terminos)
    return hallazgos


def autoprueba(terminos):
    original = terminos[0][0]
    controles = (f"control {original.upper()} positivo".encode("utf-8"), f"control {original} positivo".encode("utf-16"))
    for datos in controles:
        if not buscar(decodificar(datos), terminos):
            raise NoSePuedeBarrer("la autoprueba no detectó su control positivo: el barrido está mudo")
    print(f"autoprueba ok: {len(terminos)} términos; detecta UTF-8 y UTF-16")


def main(argv):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if not argv or argv[0] not in ("--staged", "--paths", "--autoprueba"):
        print(USO, file=sys.stderr)
        return 2
    try:
        terminos = cargar_lista(ruta_de_la_lista())
        if argv[0] == "--autoprueba":
            autoprueba(terminos)
            return 0
        hallazgos = barrer_stageado(terminos) if argv[0] == "--staged" else barrer_en_disco(argv[1:], terminos)
    except NoSePuedeBarrer as error:
        print(f"BARRIDO BLOQUEADO: {error}. Sin barrido no se commitea a ciegas.", file=sys.stderr)
        return 2
    for ruta, numero, termino in hallazgos:
        donde = f"{ruta} (nombre)" if numero == 0 else f"{ruta}:{numero}"
        print(f"{donde}: «{termino}»")
    if hallazgos:
        print(f"BARRIDO: {len(hallazgos)} coincidencias con la lista negra.", file=sys.stderr)
        return 1
    print("barrido limpio")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
