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
LANZAR = "Agent"
RESULTADO = "toolUseResult"
ID_DEL_AGENTE = "agentId"
USO_DE_CODEX = "token_usage_record"
CACHE_LEIDA_DE_CODEX = "cached_input_tokens"
CACHE_ESCRITA_DE_CODEX = "cache_write_input_tokens"
TOTAL_DE_CODEX = "total_tokens"


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


def _tiempos(registros):
    instantes = sorted((i, r["timestamp"]) for i, r in ((_instante(r.get("timestamp")), r) for r in registros) if i)
    pausas = [(b[0] - a[0]).total_seconds() for a, b in zip(instantes, instantes[1:])]
    return {
        "inicio": instantes[0][1] if instantes else None,
        "fin": instantes[-1][1] if instantes else None,
        "pausa_mayor": round(max(pausas), 3) if pausas else None,
    }


def costo(registros):
    usos = _usos_por_mensaje(registros)
    if not usos:
        return None
    return {
        "turnos": len(usos),
        "contexto_inicial": _contexto(usos[0]),
        "contexto_final": _contexto(usos[-1]),
        "salida": sum(_tokens(u, SALIDA) for u in usos),
        "cache_escrita": sum(_tokens(u, CACHE_ESCRITA) for u in usos),
        "cache_leida": sum(_tokens(u, CACHE_LEIDA) for u in usos),
        **_tiempos(registros),
    }


def _usos_de_codex(registros):
    usos = {}
    for i, registro in enumerate(registros):
        carga = registro.get("payload")
        if registro.get("type") != USO_DE_CODEX or not isinstance(carga, dict) or not isinstance(carga.get(USO), dict):
            continue
        usos[carga.get("response_id") or ("sin-id", i)] = carga[USO]
    return list(usos.values())


def costo_codex(registros):
    usos = _usos_de_codex(registros)
    if not usos:
        return None
    return {
        "turnos": len(usos),
        "contexto_inicial": _tokens(usos[0], ENTRADA),
        "contexto_final": _tokens(usos[-1], ENTRADA),
        "salida": sum(_tokens(u, SALIDA) for u in usos),
        "cache_escrita": sum(_tokens(u, CACHE_ESCRITA_DE_CODEX) for u in usos),
        "cache_leida": sum(_tokens(u, CACHE_LEIDA_DE_CODEX) for u in usos),
        **_tiempos(registros),
        "tokens_total": sum(_tokens(u, TOTAL_DE_CODEX) for u in usos),
        "costo_usd": None,
    }


def lanzamientos(registros):
    usos, lanzados = {}, {}
    for i, registro in enumerate(registros):
        for b in bloques(registro):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") == LANZAR and b.get("id"):
                usos[b["id"]] = i
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in usos:
                resultado = registro.get(RESULTADO)
                agente = resultado.get(ID_DEL_AGENTE) if isinstance(resultado, dict) else None
                if isinstance(agente, str) and agente:
                    lanzados.setdefault(agente, usos[b["tool_use_id"]])
    return lanzados


def comandos(registros):
    for i, registro in enumerate(registros):
        if registro.get("type") != "assistant":
            continue
        for b in bloques(registro):
            entrada = b.get("input") if isinstance(b, dict) and b.get("type") == "tool_use" else None
            if isinstance(entrada, dict) and isinstance(entrada.get("command"), str):
                yield i, entrada["command"]


def en_serie(medidas):
    intervalos = []
    for medida in medidas:
        inicio, fin = (_instante(medida.get("inicio")), _instante(medida.get("fin"))) if isinstance(medida, dict) else (None, None)
        if inicio and fin:
            intervalos.append((inicio, fin))
    intervalos.sort()
    if any(siguiente[0] < anterior[1] for anterior, siguiente in zip(intervalos, intervalos[1:])):
        return False
    return True if len(intervalos) >= 2 and len(intervalos) == len(medidas) else None
