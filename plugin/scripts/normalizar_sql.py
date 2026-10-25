import sys

sys.dont_write_bytecode = True

import argparse
import re
from pathlib import Path

ANCHO_TAB = 4
BOM = b"\xef\xbb\xbf"
RE_FIN = re.compile(r"\r\n|\r|\n")
TERMINADORES = {"crlf": "\r\n", "lf": "\n"}
DESCRIPCION = "Normaliza archivos .sql: UTF-8 sin BOM y un solo tipo de fin de línea (CRLF por defecto); con --tabs, también la indentación."


def lineas_con_fin(texto):
    res, pos = [], 0
    for m in RE_FIN.finditer(texto):
        res.append((texto[pos:m.start()], m.group()))
        pos = m.end()
    if pos < len(texto):
        res.append((texto[pos:], ""))
    return res


def empiezan_dentro(lineas):
    res = []
    en_literal, profundidad = False, 0
    for contenido, _ in lineas:
        res.append(en_literal or profundidad > 0)
        i, n = 0, len(contenido)
        while i < n:
            c = contenido[i]
            if en_literal:
                if c == "'":
                    if i + 1 < n and contenido[i + 1] == "'":
                        i += 1
                    else:
                        en_literal = False
            elif profundidad:
                if contenido.startswith("*/", i):
                    profundidad -= 1
                    i += 1
                elif contenido.startswith("/*", i):
                    profundidad += 1
                    i += 1
            elif contenido.startswith("--", i):
                break
            elif contenido.startswith("/*", i):
                profundidad += 1
                i += 1
            elif c == "'":
                en_literal = True
            i += 1
    return res


def _solo_espacios(contenido):
    m = re.match(r" +(?=[^ \t\r\n])", contenido)
    return len(m.group()) if m else 0


def analizar(datos, tabs=False, fin="crlf"):
    bom = datos.startswith(BOM)
    cuerpo = datos[len(BOM):] if bom else datos
    terminador = TERMINADORES[fin]
    fin_incorrecto = [n for n, (_, f) in enumerate(lineas_con_fin(cuerpo.decode("latin-1")), start=1)
                      if f and f != terminador]
    no_utf8, espacios = None, []
    try:
        texto = cuerpo.decode("utf-8")
    except UnicodeDecodeError as exc:
        no_utf8 = exc.start
        texto = None
    if texto is not None and tabs:
        lineas = lineas_con_fin(texto)
        dentro = empiezan_dentro(lineas)
        espacios = [n for n, (contenido, _) in enumerate(lineas, start=1)
                    if not dentro[n - 1] and _solo_espacios(contenido)]
    return {"bom": bom, "fin_incorrecto": fin_incorrecto, "no_utf8": no_utf8, "espacios": espacios}


def corregir(datos, tabs=False, fin="crlf"):
    cuerpo = datos[len(BOM):] if datos.startswith(BOM) else datos
    try:
        texto = cuerpo.decode("utf-8")
    except UnicodeDecodeError:
        return None
    terminador = TERMINADORES[fin]
    lineas = lineas_con_fin(texto)
    dentro = empiezan_dentro(lineas)
    salida = []
    for n, (contenido, terminado) in enumerate(lineas):
        if tabs and not dentro[n]:
            k = _solo_espacios(contenido)
            if k and k % ANCHO_TAB == 0:
                contenido = "\t" * (k // ANCHO_TAB) + contenido[k:]
        salida.append(contenido + (terminador if terminado else ""))
    return "".join(salida).encode("utf-8")


def _primera(lineas):
    return "%d lineas (primera: %d)" % (len(lineas), lineas[0])


def reporte(ruta, datos, tabs=False, fin="crlf"):
    a = analizar(datos, tabs, fin)
    res = []
    if a["bom"]:
        res.append("%s: tiene BOM" % ruta)
    if a["fin_incorrecto"]:
        res.append("%s: fin de linea que no es %s en %s" % (ruta, fin.upper(), _primera(a["fin_incorrecto"])))
    if a["no_utf8"] is not None:
        res.append("%s: no es UTF-8 valido (byte %d)" % (ruta, a["no_utf8"]))
    if a["espacios"]:
        res.append("%s: indentacion solo con espacios (ancho de tab %d) en %s"
                   % (ruta, ANCHO_TAB, _primera(a["espacios"])))
    return res


def _leer(ruta):
    try:
        return Path(ruta).read_bytes()
    except OSError as exc:
        print("%s: no se pudo leer (%s)" % (ruta, exc.strerror or exc), file=sys.stderr)
        return None


def modo_check(archivos, tabs=False, fin="crlf"):
    datos_por_ruta = []
    for ruta in archivos:
        datos = _leer(ruta)
        if datos is None:
            return 2
        datos_por_ruta.append((ruta, datos))
    hay = False
    for ruta, datos in datos_por_ruta:
        for linea in reporte(ruta, datos, tabs, fin):
            print(linea)
            hay = True
    return 1 if hay else 0


def modo_fix(archivos, tabs=False, fin="crlf"):
    codigo = 0
    for ruta in archivos:
        datos = _leer(ruta)
        if datos is None:
            return 2
        nuevo = corregir(datos, tabs, fin)
        if nuevo is None:
            print("%s: no es UTF-8 valido, no se escribe nada" % ruta, file=sys.stderr)
            codigo = 1
            continue
        if nuevo != datos:
            Path(ruta).write_bytes(nuevo)
            print("%s: corregido" % ruta)
    return codigo


def main(argv=None):
    p = argparse.ArgumentParser(prog="normalizar_sql.py", description=DESCRIPCION)
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--check", nargs="+", metavar="ARCHIVO", help="reporta, no escribe")
    grupo.add_argument("--fix", nargs="+", metavar="ARCHIVO", help="corrige en el lugar")
    p.add_argument("--tabs", action="store_true",
                   help="también la indentación de solo espacios (opt-in); --fix la convierte a tabs de ancho 4")
    p.add_argument("--fin", choices=sorted(TERMINADORES, reverse=True), default="crlf",
                   help="fin de línea esperado: crlf (por defecto) o lf")
    args = p.parse_args(argv)
    if args.check:
        return modo_check(args.check, args.tabs, args.fin)
    return modo_fix(args.fix, args.tabs, args.fin)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
