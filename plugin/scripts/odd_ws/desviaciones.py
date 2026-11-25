import sys

sys.dont_write_bytecode = True

import csv
import datetime
import io
import re
from pathlib import Path

import config_loader
import matriz

ID = "desviaciones"
ARCHIVO = ".claude/reglas/desviaciones.csv"
ENCABEZADO = ("id", "ubicacion", "resumen", "porque", "fecha")
NINGUNA = "ninguna"
FECHA_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
RUTA_RE = re.compile(r"[^@:\\\s]+")
FORMA = "ubicacion '%s' no es <repo>:<ruta>@<hash>:<ini>-<fin> ni la <ruta> de un archivo de la instancia"


def repos_de_la_config(raiz):
    config = config_loader._leer_objeto(Path(raiz) / config_loader.NOMBRE)
    config_loader._version(config)
    config_loader._banderas(config)
    return set(config.get("repos") or {})


def _fecha_valida(texto):
    if FECHA_RE.fullmatch(texto) is None:
        return False
    try:
        datetime.date(int(texto[:4]), int(texto[5:7]), int(texto[8:]))
    except ValueError:
        return False
    return True


def _repo_ajeno(repo, repos):
    cuales = "repos: %s" % ", ".join(sorted(repos)) if repos else "no declara repos"
    return "el repo '%s' no está en %s (%s)" % (repo, config_loader.NOMBRE, cuales)


def _ubicacion(texto, repos):
    if ":" not in texto:
        if RUTA_RE.fullmatch(texto) is None:
            return None, FORMA % texto
        if texto.startswith("/") or ".." in texto.split("/"):
            return None, "ubicacion '%s': la ruta de un archivo de la instancia va relativa a su raíz, sin '..'" % texto
        return {"repo": None, "ruta": texto, "hash": None, "ini": None, "fin": None}, None
    repo, resto = texto.split(":", 1)
    if not repo or matriz.RE_RANGO.fullmatch(resto) is None:
        return None, FORMA % texto
    try:
        origen = matriz.parsear_origen(resto)
    except ValueError as exc:
        return None, "ubicacion '%s': %s" % (texto, exc)
    if origen["tipo"] != "rango":
        return None, FORMA % texto
    if origen["hash"] is None:
        return None, "ubicacion '%s' sin @hash: el código de un repo va fijado a un commit (<repo>:<ruta>@<hash>:<ini>-<fin>)" % texto
    if repo not in repos:
        return None, _repo_ajeno(repo, repos)
    return {"repo": repo, "ruta": origen["ruta"], "hash": origen["hash"], "ini": origen["ini"], "fin": origen["fin"]}, None


def _fila(n, registro, repos, vistos):
    if len(registro) > len(ENCABEZADO):
        return None, ["tiene %d campos y el encabezado %d" % (len(registro), len(ENCABEZADO))]
    valores = [campo.strip() for campo in registro] + [""] * (len(ENCABEZADO) - len(registro))
    fila = dict(zip(ENCABEZADO, valores))
    defectos, partes = [], None
    faltan = [campo for campo in ENCABEZADO if not fila[campo]]
    if faltan:
        defectos.append("falta %s" % ", ".join(faltan))
    if fila["id"]:
        if fila["id"] in vistos:
            defectos.append("id '%s' repetido (ya en la línea %d)" % (fila["id"], vistos[fila["id"]]))
        else:
            vistos[fila["id"]] = n
    if fila["ubicacion"]:
        partes, defecto = _ubicacion(fila["ubicacion"], repos)
        if defecto:
            defectos.append(defecto)
    if fila["fecha"] and not _fecha_valida(fila["fecha"]):
        defectos.append("fecha '%s' no es AAAA-MM-DD" % fila["fecha"])
    if defectos:
        return None, defectos
    return {"linea": n, **fila, **partes}, []


def _registros(texto):
    lector = csv.reader(io.StringIO(texto, newline=""))
    registros, previa = [], 0
    for registro in lector:
        registros.append((previa + 1, registro))
        previa = lector.line_num
    return [(n, registro) for n, registro in registros if registro]


def cargar(raiz):
    ruta = Path(raiz) / ARCHIVO
    try:
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            texto = f.read()
    except FileNotFoundError:
        return [], []
    except UnicodeDecodeError as exc:
        return [], [(1, "no está en UTF-8 (%s)" % exc.reason)]
    except OSError as exc:
        return [], [(1, "no se puede leer (%s)" % (exc.strerror or exc))]
    repos = repos_de_la_config(raiz)
    try:
        registros = _registros(texto)
    except csv.Error as exc:
        return [], [(1, "csv ilegible: %s" % exc)]
    if not registros:
        return [], [(1, "falta el encabezado %s" % ",".join(ENCABEZADO))]
    n, cabecera = registros[0]
    if tuple(campo.strip() for campo in cabecera) != ENCABEZADO:
        return [], [(n, "el encabezado no es %s" % ",".join(ENCABEZADO))]
    filas, problemas, vistos = [], [], {}
    for n, registro in registros[1:]:
        fila, defectos = _fila(n, registro, repos, vistos)
        if defectos:
            problemas.append((n, "; ".join(defectos)))
        else:
            filas.append(fila)
    return filas, problemas


def _una_linea(texto):
    return " ".join(texto.split())


def linea(fila):
    return "%s %s — %s: %s" % tuple(_una_linea(fila[campo]) for campo in ("id", "ubicacion", "resumen", "porque"))


def texto_del_problema(problema):
    n, mensaje = problema
    return "%s:%d: %s" % (ARCHIVO, n, mensaje)
