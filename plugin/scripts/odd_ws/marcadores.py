import os
import re
import subprocess
import sys
from collections import namedtuple

LADOS = (b"<", b">")
SIN_REGLAS_DE_ESPACIOS = "core.whitespace=-trailing-space,-space-before-tab,-indent-with-non-tab,-tab-in-indent"
AVISO_DE_GIT = re.compile(rb"(.+):([0-9]+): leftover conflict marker")
SALIDAS_DEL_CHEQUEO = (0, 2)
COMODINES = re.compile(r"[*?\[\\]")
PIDE_COMILLAS = re.compile(r'[ \t\r\n"]|^#')
ESCAPES_DE_C = {"\\": "\\\\", '"': '\\"', "\t": "\\t", "\r": "\\r", "\n": "\\n"}
USO = "uso: marcadores.py   (revisa lo stageado desde la raíz del repo; no recibe argumentos)"

Marcador = namedtuple("Marcador", "ruta numero linea")


class GitNoRespondio(Exception):
    pass


def git(raiz, *args):
    try:
        resultado = subprocess.run(["git", *args], cwd=raiz, capture_output=True)
    except OSError as error:
        raise GitNoRespondio(f"git no arrancó: {error.strerror or error}") from None
    return resultado


def _motivo(resultado):
    lineas = resultado.stderr.decode("utf-8", "replace").strip().splitlines()
    return lineas[0] if lineas else f"salió con {resultado.returncode}"


def avisos_del_chequeo(raiz):
    chequeo = git(raiz, "-c", SIN_REGLAS_DE_ESPACIOS, "diff", "--cached", "--check", "--no-color")
    if chequeo.returncode not in SALIDAS_DEL_CHEQUEO:
        raise GitNoRespondio(f"git diff --cached --check: {_motivo(chequeo)}")
    if chequeo.returncode == 0:
        return {}
    nombres = git(raiz, "diff", "--cached", "--name-only", "-z")
    if nombres.returncode != 0:
        raise GitNoRespondio(f"git diff --cached --name-only: {_motivo(nombres)}")
    stageados = set(nombres.stdout.split(b"\0"))
    avisos = {}
    for linea in chequeo.stdout.split(b"\n"):
        encontrado = AVISO_DE_GIT.fullmatch(linea)
        if encontrado and encontrado.group(1) in stageados:
            avisos.setdefault(encontrado.group(1), []).append(int(encontrado.group(2)))
    return avisos


def marcadores_de(raiz, ruta, numeros):
    contenido = git(raiz, "cat-file", "blob", ":0:" + os.fsdecode(ruta))
    if contenido.returncode != 0:
        raise GitNoRespondio(f"git cat-file: {_motivo(contenido)}")
    lineas = contenido.stdout.split(b"\n")
    visible = ruta.decode("utf-8", "replace")
    return [Marcador(visible, numero, lineas[numero - 1].rstrip(b"\r").decode("utf-8", "replace"))
            for numero in sorted(set(numeros)) if 0 < numero <= len(lineas) and lineas[numero - 1][:1] in LADOS]


def marcadores_stageados(raiz):
    hallazgos = []
    for ruta, numeros in avisos_del_chequeo(raiz).items():
        marcadores = marcadores_de(raiz, ruta, numeros)
        if len({marcador.linea[:1] for marcador in marcadores}) == len(LADOS):
            hallazgos += marcadores
    return hallazgos


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
