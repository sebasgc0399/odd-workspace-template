import sys

sys.dont_write_bytecode = True

import datetime
import os
import re
import subprocess
import time

from odd_ws import desviaciones
from odd_ws.comun import decodificar, entorno_git, lineas

PLAZO = 1.5
TOPE_DE_LINEAS = 400
TOPE_DE_COMMITS = 2
TOPE_BYTES = 2000000
LARGO_DEL_PORQUE = 200
LARGO_DEL_HASH = 7
SIN_COMMIT = "0" * 40
NO_SE_PUDO = "no se pudo chequear el porqué de estas líneas"
SIN_HISTORIA = "sin historia"
ENCABEZADO = ("porqué de lo que reemplazaste en %s (git blame en HEAD, de lo más nuevo a lo más viejo; si un porqué choca con "
              "tu cambio, reconsidéralo):")
FALLA = "porqué de lo que reemplazaste en %s: " + NO_SE_PUDO + " (%s)."
SIN_HISTORIA_EN = "porqué de lo que reemplazaste en %s: " + SIN_HISTORIA + " (no está en HEAD), así que git no tiene un porqué que mostrar."
PAUSA = ("porqué antes de editar: esta edición de %s toca una desviación conocida, código que parece un error y es a propósito "
         "(%s):")
DESVIACION = "- %s, anotada el %s, hoy en las líneas %d-%d (%s): %s. Porqué: %s"
CIERRE_DE_LA_PAUSA = "Confirma la edición solo si cambiar esas líneas es a propósito; si no, deja la desviación como está."
ENCABEZADO_DEL_BLAME = re.compile(r"([0-9a-f]{40}) \d+ \d+(?: \d+)?")
ZONA = re.compile(r"([+-])(\d\d)(\d\d)")
TRAILERS_CONOCIDOS = ("Co-Authored-By", "Signed-off-by", "Reviewed-by", "Acked-by", "Tested-by", "Reported-by", "Suggested-by", "Helped-by",
                      "Cc", "Change-Id")
TRAILER = re.compile(r"(?:%s):(?:\s|$)" % "|".join(re.escape(clave) for clave in TRAILERS_CONOCIDOS), re.IGNORECASE)
VINETA = re.compile(r"\s*[-*]\s+")
EPOCA = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


class FallaDeGit(Exception):
    pass


def hasta(segundos):
    return time.monotonic() + segundos


def _git(arbol, limite, *args, entrada=None):
    restante = limite - time.monotonic()
    if restante <= 0:
        raise subprocess.TimeoutExpired(["git", *args], 0)
    return subprocess.run(["git", "-C", str(arbol), *args], input=entrada, capture_output=True, timeout=restante, env=entorno_git())


def relativa(ruta, arbol):
    try:
        rel = os.path.relpath(os.path.realpath(ruta), os.path.realpath(arbol)).replace("\\", "/")
    except ValueError:
        return None
    return None if rel in (".", "..") or rel.startswith("../") else rel


def _normal(texto):
    return texto.replace("\r\n", "\n")


def _leer(ruta):
    if os.path.getsize(ruta) > TOPE_BYTES:
        return None
    with open(ruta, "rb") as archivo:
        return decodificar(archivo.read())


def rangos_del_texto(texto, fragmento):
    texto = _normal(texto)
    if fragmento is None:
        total = len(lineas(texto))
        return [(1, total)] if total else []
    fragmento = _normal(fragmento)
    if not fragmento.strip():
        return []
    rangos, desde = [], 0
    while True:
        inicio = texto.find(fragmento, desde)
        if inicio < 0:
            return rangos
        fin = inicio + len(fragmento) - 1
        rangos.append((texto.count("\n", 0, inicio) + 1, texto.count("\n", 0, fin) + 1))
        desde = inicio + len(fragmento)


def rangos_de_las_lineas(texto, buscadas):
    buscadas = [linea.strip() for linea in buscadas]
    while buscadas and not buscadas[0]:
        buscadas.pop(0)
    while buscadas and not buscadas[-1]:
        buscadas.pop()
    if not buscadas:
        return []
    actuales = [linea.strip() for _, linea in lineas(_normal(texto))]
    largo = len(buscadas)
    return [(i + 1, i + largo) for i in range(len(actuales) - largo + 1)
            if actuales[i] == buscadas[0] and actuales[i:i + largo] == buscadas]


def rango_de_la_desviacion(texto, buscadas, ini):
    rangos = rangos_de_las_lineas(texto, buscadas)
    if not rangos:
        return None
    original = ini + next(n for n, linea in enumerate(buscadas) if linea.strip())
    return min(rangos, key=lambda rango: (abs(rango[0] - original), rango[0]))


def se_tocan(uno, otro):
    return uno[0] <= otro[1] and otro[0] <= uno[1]


def unir(rangos):
    unidos = []
    for ini, fin in sorted(rangos):
        if unidos and ini <= unidos[-1][1] + 1:
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], fin))
        else:
            unidos.append((ini, fin))
    return unidos


def con_tope(rangos, tope=TOPE_DE_LINEAS):
    salida = []
    for ini, fin in rangos:
        if tope <= 0:
            break
        fin = min(fin, ini + tope - 1)
        salida.append((ini, fin))
        tope -= fin - ini + 1
    return salida


def _una_linea(texto):
    return " ".join(texto.split())


def _recortar(texto):
    if len(texto) <= LARGO_DEL_PORQUE:
        return texto
    espacio = texto.rfind(" ", 0, LARGO_DEL_PORQUE)
    return (texto[:espacio] if espacio > 0 else texto[:LARGO_DEL_PORQUE - 1]) + "…"


def desviaciones_del_archivo(raiz, repo, rel):
    clave = os.path.normcase(rel)
    return [fila for fila in desviaciones.cargar(raiz)[0] if fila["repo"] == repo and os.path.normcase(fila["ruta"]) == clave]


def _lineas_de_la_desviacion(arbol, fila, limite, vistas):
    clave = (fila["hash"], fila["ruta"])
    if clave not in vistas:
        try:
            r = _git(arbol, limite, "cat-file", "blob", "%s:%s" % clave)
        except (OSError, subprocess.SubprocessError):
            r = None
        vistas[clave] = lineas(decodificar(r.stdout)) if r is not None and r.returncode == 0 else None
    numeradas = vistas[clave]
    return None if numeradas is None else [texto for n, texto in numeradas if fila["ini"] <= n <= fila["fin"]]


def texto_de_la_pausa(rel, halladas):
    partes = [PAUSA % (rel, desviaciones.ARCHIVO)]
    for fila, (ini, fin) in halladas:
        partes.append(DESVIACION % (fila["id"], fila["fecha"], ini, fin, fila["ubicacion"], _una_linea(fila["resumen"]).rstrip("."),
                                    _una_linea(fila["porque"])))
    partes.append(CIERRE_DE_LA_PAUSA)
    return "\n".join(partes)


def pausa(raiz, repo, arbol, ruta, fragmentos, limite):
    rel = relativa(ruta, arbol)
    if rel is None:
        return None
    filas = desviaciones_del_archivo(raiz, repo, rel)
    if not filas or not os.path.isfile(ruta):
        return None
    texto = _leer(ruta)
    tocados = [rango for fragmento in fragmentos for rango in rangos_del_texto(texto, fragmento)] if texto is not None else []
    if not tocados:
        return None
    halladas, vistas = [], {}
    for fila in filas:
        rango = rango_de_la_desviacion(texto, _lineas_de_la_desviacion(arbol, fila, limite, vistas) or [], fila["ini"])
        if rango is not None and any(se_tocan(rango, tocado) for tocado in tocados):
            halladas.append((fila, rango))
    return texto_de_la_pausa(rel, halladas) if halladas else None


def _commits_del_blame(salida):
    commits, actual = {}, None
    for linea in salida.split("\n"):
        if linea.startswith("\t"):
            actual = None
            continue
        encontrado = ENCABEZADO_DEL_BLAME.fullmatch(linea) if actual is None else None
        if encontrado:
            actual = encontrado.group(1)
            if actual != SIN_COMMIT:
                commits.setdefault(actual, {})
            continue
        if actual in commits and " " in linea:
            clave, valor = linea.split(" ", 1)
            commits[actual].setdefault(clave, valor)
    return [(hash_, datos) for hash_, datos in commits.items() if datos.get("author-time", "").isdigit()]


def fecha(momento, zona):
    encontrada = ZONA.fullmatch(zona.strip())
    minutos = (int(encontrada.group(2)) * 60 + int(encontrada.group(3))) * (-1 if encontrada.group(1) == "-" else 1) if encontrada else 0
    return (EPOCA + datetime.timedelta(seconds=momento, minutes=minutos)).date().isoformat()


def _parrafos(mensaje):
    parrafos, actual = [], []
    for linea in _normal(mensaje).split("\n"):
        if linea.strip():
            actual.append(linea.rstrip())
        elif actual:
            parrafos.append(actual)
            actual = []
    if actual:
        parrafos.append(actual)
    return parrafos


def _sin_trailers(parrafo):
    salida, en_trailer = [], False
    for linea in parrafo:
        en_trailer = TRAILER.match(linea) is not None or (en_trailer and linea[:1] in (" ", "\t"))
        if not en_trailer:
            salida.append(linea)
    return salida


def _primera_vineta(parrafo):
    vineta = VINETA.match(parrafo[0])
    if vineta is None:
        return parrafo
    siguiente = next((n for n in range(1, len(parrafo)) if VINETA.match(parrafo[n])), len(parrafo))
    return [parrafo[0][vineta.end():]] + parrafo[1:siguiente]


def primera_linea_del_cuerpo(mensaje):
    cuerpo = _parrafos(mensaje or "")[1:]
    if cuerpo:
        cuerpo[-1] = _sin_trailers(cuerpo[-1])
    cuerpo = [parrafo for parrafo in cuerpo if parrafo]
    return _recortar(_una_linea(" ".join(_primera_vineta(cuerpo[0])))) if cuerpo else None


def _mensaje(objeto):
    partes = objeto.split(b"\n\n", 1)
    return partes[1].decode("utf-8", "replace") if len(partes) == 2 else ""


def _mensajes(arbol, limite, hashes):
    r = _git(arbol, limite, "cat-file", "--batch", entrada=("\n".join(hashes) + "\n").encode("ascii"))
    if r.returncode != 0:
        raise FallaDeGit("git cat-file salió con %d" % r.returncode)
    mensajes, datos, i = {}, r.stdout, 0
    while i < len(datos):
        fin = datos.find(b"\n", i)
        if fin < 0:
            break
        cabecera = datos[i:fin].decode("ascii", "replace").split()
        i = fin + 1
        if len(cabecera) != 3 or not cabecera[2].isdigit():
            continue
        tamano = int(cabecera[2])
        mensajes[cabecera[0]] = _mensaje(datos[i:i + tamano]) if cabecera[1] == "commit" else ""
        i += tamano + 1
    return mensajes


def _blame(arbol, rel, rangos, limite):
    argumentos = ["blame", "-w", "--porcelain"]
    for ini, fin in rangos:
        argumentos += ["-L", "%d,%d" % (ini, fin)]
    r = _git(arbol, limite, *argumentos, "HEAD", "--", rel)
    if r.returncode != 0:
        raise FallaDeGit("git blame salió con %d" % r.returncode)
    return _commits_del_blame(decodificar(r.stdout))


def _porque(arbol, rel, fragmentos, limite, en_disco):
    r = _git(arbol, limite, "cat-file", "blob", "HEAD:" + rel)
    if r.returncode != 0:
        if not en_disco:
            return None
        existe = _git(arbol, limite, "rev-parse", "-q", "--verify", "HEAD:" + rel)
        if existe.returncode == 1:
            return SIN_HISTORIA_EN % rel if any(fragmento is not None for fragmento in fragmentos) else None
        raise FallaDeGit("git no pudo leer HEAD:%s" % rel)
    en_head = decodificar(r.stdout)
    rangos = con_tope(unir([rango for fragmento in fragmentos for rango in rangos_del_texto(en_head, fragmento)]))
    if not rangos:
        return None
    commits = sorted(_blame(arbol, rel, rangos, limite), key=lambda par: -int(par[1]["author-time"]))
    if not commits:
        return None
    mensajes = _mensajes(arbol, limite, [hash_ for hash_, _ in commits])
    lineas_ = []
    for hash_, datos in commits:
        primera = primera_linea_del_cuerpo(mensajes.get(hash_))
        if primera:
            lineas_.append("%s %s: %s" % (fecha(int(datos["author-time"]), datos.get("author-tz", "")), hash_[:LARGO_DEL_HASH], primera))
        if len(lineas_) == TOPE_DE_COMMITS:
            break
    return "\n".join([ENCABEZADO % rel] + lineas_) if lineas_ else None


def contexto(arbol, ruta, fragmentos, limite):
    en_disco = os.path.isfile(ruta)
    if not en_disco and (os.path.exists(ruta) or all(fragmento is None for fragmento in fragmentos)):
        return None
    rel = relativa(ruta, arbol)
    if rel is None:
        return None
    try:
        return _porque(arbol, rel, fragmentos, limite, en_disco)
    except subprocess.TimeoutExpired:
        motivo = "git no terminó a tiempo"
    except OSError as error:
        motivo = "git no arrancó: %s" % (error.strerror or error)
    except (subprocess.SubprocessError, FallaDeGit) as error:
        motivo = _una_linea(str(error)) or type(error).__name__
    return FALLA % (rel, motivo)
