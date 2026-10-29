import json
import os

HANDBACK = "SubagentHandback"
LECTURA = ("Read", "Grep", "Glob")


def leer(transcript):
    if not isinstance(transcript, (str, os.PathLike)):
        return None
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            lineas = f.read().splitlines()
    except OSError:
        return None
    registros, salteadas = [], 0
    for linea in lineas:
        if not linea.strip():
            continue
        try:
            registro = json.loads(linea)
        except ValueError:
            salteadas += 1
            continue
        if isinstance(registro, dict):
            registros.append(registro)
        else:
            salteadas += 1
    return registros, salteadas


def bloques(registro):
    mensaje = registro.get("message")
    contenido = mensaje.get("content") if isinstance(mensaje, dict) else None
    return contenido if isinstance(contenido, list) else []
