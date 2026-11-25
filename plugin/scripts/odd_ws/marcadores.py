import os
import re
import subprocess
import sys
from collections import namedtuple

LADOS = (b"<", b">")
SIN_REGLAS_DE_ESPACIOS = "core.whitespace=-trailing-space,-space-before-tab,-indent-with-non-tab,-tab-in-indent"
AVISO_DE_GIT = re.compile(rb"(.+):([0-9]+): leftover conflict marker")
SALIDAS_DEL_CHEQUEO = (0, 2)
SALIDAS_SIN_INDICE = (0, 1, 2, 3)
ERROR_DE_GIT = re.compile(rb"^(?:error|fatal):", re.MULTILINE)
NULO = "/dev/null"
SIN_TOCAR_EL_INDICE = ("--no-optional-locks", "-c", "diff.autoRefreshIndex=false")
COMODINES = re.compile(r"[*?\[\\]")
PIDE_COMILLAS = re.compile(r'[ \t\r\n"]|^#')
ESCAPES_DE_C = {"\\": "\\\\", '"': '\\"', "\t": "\\t", "\r": "\\r", "\n": "\\n"}
USO = "uso: marcadores.py   (revisa lo stageado desde la raíz del repo; no recibe argumentos)"

Marcador = namedtuple("Marcador", "ruta numero linea")


class GitNoRespondio(Exception):
    pass


def git(raiz, *args, entorno=None):
    try:
        resultado = subprocess.run(["git", *args], cwd=raiz, capture_output=True, env=entorno)
    except OSError as error:
        raise GitNoRespondio(f"git no arrancó: {error.strerror or error}") from None
    return resultado


def _motivo(resultado):
    lineas = resultado.stderr.decode("utf-8", "replace").strip().splitlines()
    return lineas[0] if lineas else f"salió con {resultado.returncode}"


def _avisos(salida, validas):
    avisos = {}
    for linea in salida.split(b"\n"):
        encontrado = AVISO_DE_GIT.fullmatch(linea)
        if encontrado and encontrado.group(1) in validas:
            avisos.setdefault(encontrado.group(1), []).append(int(encontrado.group(2)))
    return avisos


def _chequeo_del_diff(raiz, contra, *globales, entorno=None):
    chequeo = git(raiz, *globales, "-c", SIN_REGLAS_DE_ESPACIOS, "diff", contra, "--check", "--no-color", entorno=entorno)
    if chequeo.returncode not in SALIDAS_DEL_CHEQUEO:
        raise GitNoRespondio(f"git diff {contra} --check: {_motivo(chequeo)}")
    if chequeo.returncode == 0:
        return {}
    nombres = git(raiz, *globales, "diff", contra, "--name-only", "-z", entorno=entorno)
    if nombres.returncode != 0:
        raise GitNoRespondio(f"git diff {contra} --name-only: {_motivo(nombres)}")
    return _avisos(chequeo.stdout, set(nombres.stdout.split(b"\0")))


def avisos_del_chequeo(raiz):
    return _chequeo_del_diff(raiz, "--cached")


def _en_lineas(contenido, ruta, numeros):
    lineas = contenido.split(b"\n")
    visible = ruta.decode("utf-8", "replace")
    return [Marcador(visible, numero, lineas[numero - 1].rstrip(b"\r").decode("utf-8", "replace"))
            for numero in sorted(set(numeros)) if 0 < numero <= len(lineas) and lineas[numero - 1][:1] in LADOS]


def marcadores_de(raiz, ruta, numeros):
    contenido = git(raiz, "cat-file", "blob", ":0:" + os.fsdecode(ruta))
    if contenido.returncode != 0:
        raise GitNoRespondio(f"git cat-file: {_motivo(contenido)}")
    return _en_lineas(contenido.stdout, ruta, numeros)


def _del_arbol(raiz, ruta, numeros):
    try:
        with open(os.path.join(raiz, os.fsdecode(ruta)), "rb") as archivo:
            contenido = archivo.read()
    except OSError as error:
        raise GitNoRespondio(f"no se pudo leer {os.fsdecode(ruta)}: {error.strerror or error}") from None
    return _en_lineas(contenido, ruta, numeros)


def _con_los_dos_lados(avisos, leer):
    hallazgos = []
    for ruta, numeros in avisos.items():
        marcadores = leer(ruta, numeros)
        if len({marcador.linea[:1] for marcador in marcadores}) == len(LADOS):
            hallazgos += marcadores
    return hallazgos


def marcadores_stageados(raiz):
    return _con_los_dos_lados(avisos_del_chequeo(raiz), lambda ruta, numeros: marcadores_de(raiz, ruta, numeros))


def marcadores_nuevos(raiz, rutas, entorno=None):
    avisos = {}
    for ruta in rutas:
        chequeo = git(raiz, "-c", SIN_REGLAS_DE_ESPACIOS, "diff", "--no-index", "--check", "--no-color", "--", NULO, ruta,
                      entorno=entorno)
        if chequeo.returncode not in SALIDAS_SIN_INDICE or ERROR_DE_GIT.search(chequeo.stderr):
            raise GitNoRespondio(f"git diff --no-index --check {ruta}: {_motivo(chequeo)}")
        avisos.update(_avisos(chequeo.stdout, {os.fsencode(ruta)}))
    return _con_los_dos_lados(avisos, lambda ruta, numeros: _del_arbol(raiz, ruta, numeros))


def sin_trackear(raiz, entorno=None):
    otros = git(raiz, "ls-files", "--others", "--exclude-standard", "-z", entorno=entorno)
    if otros.returncode != 0:
        raise GitNoRespondio(f"git ls-files --others: {_motivo(otros)}")
    return [os.fsdecode(ruta) for ruta in otros.stdout.split(b"\0") if ruta and not ruta.endswith(b"/")]


def marcadores_contra(raiz, base, nuevos=None, entorno=None):
    hallazgos = _con_los_dos_lados(_chequeo_del_diff(raiz, base, *SIN_TOCAR_EL_INDICE, entorno=entorno),
                                   lambda ruta, numeros: _del_arbol(raiz, ruta, numeros))
    return hallazgos + marcadores_nuevos(raiz, sin_trackear(raiz, entorno) if nuevos is None else nuevos, entorno)


def patron_de_gitattributes(ruta):
    patron = COMODINES.sub(lambda comodin: "\\" + comodin.group(0), ruta)
    if patron.startswith("!"):
        patron = "\\" + patron
    if not PIDE_COMILLAS.search(patron):
        return patron
    return '"' + "".join(ESCAPES_DE_C.get(caracter, caracter) for caracter in patron) + '"'


def explicar(hallazgos):
    separador = "=" * 7
    lineas = ["COMMIT FRENADO: lo stageado agrega marcadores de conflicto (apertura y cierre en un mismo archivo):"]
    lineas += [f"  {h.ruta}:{h.numero}: {h.linea}" for h in hallazgos]
    lineas += [
        f"Resuelve el conflicto en cada archivo: deja el contenido que va, borra las líneas de los marcadores (también la de {separador})"
        " y vuelve a stagearlo con git add.",
        "Si esas líneas son contenido a propósito (un ejemplo o un fixture), saca el archivo del chequeo en .gitattributes con un"
        f" tamaño de marcador que no use, por ejemplo: {patron_de_gitattributes(hallazgos[0].ruta)} conflict-marker-size=32",
    ]
    return "\n".join(lineas)


def main(argv):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if argv:
        print(USO, file=sys.stderr)
        return 2
    try:
        hallazgos = marcadores_stageados(os.getcwd())
    except GitNoRespondio as error:
        print(f"marcadores: no se pudo revisar si hay marcadores de conflicto ({error}); el commit sigue sin este chequeo.",
              file=sys.stderr)
        return 0
    if hallazgos:
        print(explicar(hallazgos), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
