import datetime
import json
import os

HANDBACK = "SubagentHandback"
LECTURA = ("Read", "Grep", "Glob")
USO = "usage"
ENTRADA = "input_tokens"
CACHE_ESCRITA = "cache_creation_input_tokens"
CACHE_LEIDA = "cache_read_input_tokens"
SALIDA = "output_tokens"


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


def _tokens(uso, clave):
    valor = uso.get(clave)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0 else 0


def _contexto(uso):
    return _tokens(uso, ENTRADA) + _tokens(uso, CACHE_ESCRITA) + _tokens(uso, CACHE_LEIDA)


def _instante(texto):
    if not isinstance(texto, str):
        return None
    try:
        instante = datetime.datetime.fromisoformat(texto[:-1] + "+00:00" if texto.endswith("Z") else texto)
    except ValueError:
        return None
    return instante if instante.tzinfo else instante.replace(tzinfo=datetime.timezone.utc)


def _usos_por_mensaje(registros):
    usos = {}
    for i, registro in enumerate(registros):
        mensaje = registro.get("message")
        if registro.get("type") != "assistant" or not isinstance(mensaje, dict) or not isinstance(mensaje.get(USO), dict):
            continue
        usos[mensaje.get("id") or ("sin-id", i)] = mensaje[USO]
    return list(usos.values())


def costo(registros):
    usos = _usos_por_mensaje(registros)
    if not usos:
        return None
    instantes = sorted((i, r["timestamp"]) for i, r in ((_instante(r.get("timestamp")), r) for r in registros) if i)
    pausas = [(b[0] - a[0]).total_seconds() for a, b in zip(instantes, instantes[1:])]
    return {
        "turnos": len(usos),
        "contexto_inicial": _contexto(usos[0]),
        "contexto_final": _contexto(usos[-1]),
        "salida": sum(_tokens(u, SALIDA) for u in usos),
        "cache_escrita": sum(_tokens(u, CACHE_ESCRITA) for u in usos),
        "cache_leida": sum(_tokens(u, CACHE_LEIDA) for u in usos),
        "inicio": instantes[0][1] if instantes else None,
        "fin": instantes[-1][1] if instantes else None,
        "pausa_mayor": round(max(pausas), 3) if pausas else None,
    }
