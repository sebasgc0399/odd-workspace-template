import bisect
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

LISTA_POR_DEFECTO = Path.home() / ".odd-ws" / "denylist.txt"
ESPACIOS = re.compile(r"\s+")
SEPARADORES = re.compile(r"[\\/]+")
CEROS = "0" * 40
FILTRO = "--diff-filter=ACMRT"
MODOS = ("--staged", "--paths", "--mensaje", "--pre-push", "--autoprueba")
USO = "uso: barrido.py --staged | --paths <ruta>... | --mensaje <archivo> | --pre-push | --autoprueba"


class NoSePuedeBarrer(Exception):
    pass


def normalizar(texto):
    descompuesto = unicodedata.normalize("NFKD", texto)
    visible = "".join(c for c in descompuesto if not unicodedata.combining(c) and unicodedata.category(c) != "Cf")
    return ESPACIOS.sub(" ", SEPARADORES.sub("/", visible.casefold()))


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
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


def ruta_de_la_lista():
    return Path(os.environ.get("ODD_WS_DENYLIST") or LISTA_POR_DEFECTO)


def cargar_lista(ruta):
    if not ruta.is_file():
        raise NoSePuedeBarrer(f"no existe la lista negra ({ruta})")
    terminos = []
    for linea in decodificar(ruta.read_bytes()).splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("#"):
            continue
        if "�" in limpia:
            raise NoSePuedeBarrer(f"la lista negra tiene caracteres ilegibles en «{limpia}» ({ruta}); guardala en UTF-8")
        normalizado = normalizar(limpia).strip()
        if normalizado:
            terminos.append((limpia, normalizado))
    if not terminos:
        raise NoSePuedeBarrer(f"la lista negra está vacía ({ruta})")
    return terminos


def buscar(texto, terminos):
    partes, inicios, posicion = [], [], 0
    for linea in texto.splitlines():
        normalizada = normalizar(linea).strip()
        inicios.append(posicion)
        partes.append(normalizada)
        posicion += len(normalizada) + 1
    completo = " ".join(partes)
    hallazgos = set()
    for original, termino in terminos:
        indice = completo.find(termino)
        while indice != -1:
            hallazgos.add((bisect.bisect_right(inicios, indice), original))
            indice = completo.find(termino, indice + 1)
    return sorted(hallazgos)


def en_la_ruta(ruta_visible, ruta, terminos):
    return [(ruta_visible, 0, termino) for _, termino in buscar(ruta, terminos)]


def en_el_contenido(ruta_visible, datos, terminos):
    return [(ruta_visible, numero, termino) for numero, termino in buscar(decodificar(datos), terminos)]


def git(raiz, *args):
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True)


def lista_z(salida):
    return [parte for parte in salida.decode("utf-8").split("\0") if parte]


def raiz_del_repo():
    resultado = git(os.getcwd(), "rev-parse", "--show-toplevel")
    if resultado.returncode != 0:
        raise NoSePuedeBarrer("este modo necesita correr dentro de un repositorio git")
    return resultado.stdout.decode("utf-8").strip()


def es_submodulo(raiz, ruta, commit=None):
    entrada = git(raiz, "ls-files", "-s", "--", ruta) if commit is None else git(raiz, "ls-tree", commit, "--", ruta)
    return entrada.stdout.startswith(b"160000")


def barrer_stageado(terminos):
    raiz = raiz_del_repo()
    listado = git(raiz, "diff", "--cached", "--name-only", FILTRO, "-z")
    if listado.returncode != 0:
        raise NoSePuedeBarrer("git no pudo listar lo stageado: " + listado.stderr.decode("utf-8", "replace").strip())
    hallazgos = []
    for ruta in lista_z(listado.stdout):
        hallazgos += en_la_ruta(ruta, ruta, terminos)
        if es_submodulo(raiz, ruta):
            continue
        contenido = git(raiz, "show", f":{ruta}")
        if contenido.returncode != 0:
            raise NoSePuedeBarrer(f"git no pudo leer {ruta} del índice")
        hallazgos += en_el_contenido(ruta, contenido.stdout, terminos)
    return hallazgos


def commits_a_empujar(raiz, local, remoto):
    if remoto != CEROS:
        rango = git(raiz, "rev-list", local, f"^{remoto}")
        if rango.returncode == 0:
            return rango.stdout.decode("utf-8").split()
    rango = git(raiz, "rev-list", local, "--not", "--remotes")
    if rango.returncode != 0:
        raise NoSePuedeBarrer(f"git no pudo calcular qué commits se empujan hasta {local[:7]}")
    return rango.stdout.decode("utf-8").split()


def archivos_del_commit(raiz, commit):
    padres = git(raiz, "rev-list", "--parents", "-n", "1", commit).stdout.decode("utf-8").split()[1:]
    base = [padres[0]] if padres else ["--root"]
    cambios = git(raiz, "diff-tree", "-r", "--no-commit-id", "--name-only", "-z", FILTRO, *base, commit)
    if cambios.returncode != 0:
        raise NoSePuedeBarrer(f"git no pudo listar los archivos de {commit[:7]}")
    return lista_z(cambios.stdout)


def barrer_pre_push(entrada, terminos):
    raiz = raiz_del_repo()
    hallazgos, vistos = [], set()
    for linea in entrada.splitlines():
        partes = linea.split()
        if len(partes) != 4 or partes[1] == CEROS:
            continue
        for commit in commits_a_empujar(raiz, partes[1], partes[3]):
            if commit in vistos:
                continue
            vistos.add(commit)
            corto = commit[:7]
            mensaje = git(raiz, "log", "-1", "--format=%B", commit).stdout
            hallazgos += en_el_contenido(f"{corto} mensaje", mensaje, terminos)
            for ruta in archivos_del_commit(raiz, commit):
                visible = f"{ruta}@{corto}"
                hallazgos += en_la_ruta(visible, ruta, terminos)
                if es_submodulo(raiz, ruta, commit):
                    continue
                contenido = git(raiz, "show", f"{commit}:{ruta}")
                if contenido.returncode != 0:
                    raise NoSePuedeBarrer(f"git no pudo leer {ruta} en {corto}")
                hallazgos += en_el_contenido(visible, contenido.stdout, terminos)
    return hallazgos


def barrer_mensaje(ruta, terminos):
    texto = decodificar(Path(ruta).read_bytes())
    sin_comentarios = "\n".join(linea for linea in texto.splitlines() if not linea.startswith("#"))
    return en_el_contenido("mensaje", sin_comentarios.encode("utf-8"), terminos)


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
        hallazgos += en_la_ruta(archivo.as_posix(), archivo.as_posix(), terminos)
        hallazgos += en_el_contenido(archivo.as_posix(), archivo.read_bytes(), terminos)
    return hallazgos


def autoprueba(terminos, ruta):
    for original, normalizado in terminos:
        solo = [(original, normalizado)]
        controles = [f"control {original.upper()} positivo".encode("utf-8"), f"control {original} positivo".encode("utf-16")]
        try:
            controles.append(f"control {original} positivo".encode("cp1252"))
        except UnicodeEncodeError:
            pass
        for datos in controles:
            if not buscar(decodificar(datos), solo):
                raise NoSePuedeBarrer(f"la autoprueba no detectó «{original}» en su control positivo: el barrido está mudo")
    print(f"autoprueba ok: {len(terminos)} términos de {ruta}; cada uno se detecta en UTF-8, UTF-16 y cp1252")


def main(argv):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    modo = argv[0] if argv else None
    if modo not in MODOS or (modo == "--mensaje" and len(argv) != 2) or (modo == "--paths" and len(argv) < 2):
        print(USO, file=sys.stderr)
        return 2
    try:
        ruta = ruta_de_la_lista()
        terminos = cargar_lista(ruta)
        if modo == "--autoprueba":
            autoprueba(terminos, ruta)
            return 0
        if modo == "--staged":
            hallazgos = barrer_stageado(terminos)
        elif modo == "--mensaje":
            hallazgos = barrer_mensaje(argv[1], terminos)
        elif modo == "--pre-push":
            hallazgos = barrer_pre_push(sys.stdin.buffer.read().decode("utf-8", "replace"), terminos)
        else:
            hallazgos = barrer_en_disco(argv[1:], terminos)
    except NoSePuedeBarrer as error:
        print(f"BARRIDO BLOQUEADO: {error}. Sin barrido no se commitea ni se empuja a ciegas.", file=sys.stderr)
        return 2
    for ruta_visible, numero, termino in hallazgos:
        donde = f"{ruta_visible} (nombre)" if numero == 0 else f"{ruta_visible}:{numero}"
        print(f"{donde}: «{termino}»")
    if hallazgos:
        print(f"BARRIDO: {len(hallazgos)} coincidencias con la lista negra.", file=sys.stderr)
        return 1
    print("barrido limpio")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
