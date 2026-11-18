import json
from collections import namedtuple

from odd_ws.comun import SILENCIO

PASADA = "pasada"
DERIVADA = "derivada"

DirectorioDeMemorias = namedtuple("DirectorioDeMemorias", "ruta origen fuente detalle")
RevisionDeAgente = namedtuple("RevisionDeAgente", "nombre codigo esperado motivo")


class SinMemorias(Exception):
    pass


def cargar(crudo):
    return json.loads(crudo) if isinstance(crudo, (str, bytes, bytearray)) else crudo


def atender(leer, responder, crudo, decidir, pre_por_defecto=False):
    evento = leer(cargar(crudo), pre_por_defecto)
    return SILENCIO if evento is None else responder(evento, decidir(evento))


def crear(ruta, texto):
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "xb") as archivo:
            archivo.write(texto.encode("utf-8"))
    except FileExistsError:
        return f"{ruta} ya existe: no se pisa"
    except OSError as error:
        return f"no se pudo crear {ruta}: {error.strerror or error}"
    return str(ruta)


def normal(texto):
    return texto.lstrip("﻿").replace("\r\n", "\n")


def declarada(lineas, clave, en_cabecera):
    for linea in lineas:
        if en_cabecera and not linea.startswith("#"):
            return None
        if linea.startswith(clave):
            return linea[len(clave):].strip()
        if not en_cabecera and linea == "---":
            return None
    return None


def md_intacto(texto, plantilla_writer):
    lineas = texto.split("\n")
    if not lineas or lineas[0] != "---":
        return False
    sello = plantilla_writer.huella(texto)
    return sello is not None and sello == declarada(lineas[1:], plantilla_writer.CLAVE_HASH + ":", False)


def leer_utf8(ruta):
    try:
        return ruta.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
