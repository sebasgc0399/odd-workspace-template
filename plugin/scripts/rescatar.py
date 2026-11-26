import sys

sys.dont_write_bytecode = True

import argparse
import codecs
import datetime
import json
import math
import os
import re
import types
from pathlib import Path

from odd_ws import secretos
from odd_ws.capas import TICKETS
from odd_ws.hosts import codex, pi
from odd_ws.transcripcion import HANDBACK, LECTURA, bloques, comandos, costo, costo_codex, en_serie, lanzamientos, leer

HOSTS = ("claude-code", "pi", "codex")
CLAUDE_CODE, PI, CODEX = HOSTS
SHELL = ("Bash", "PowerShell")
LECTURA_PI = tuple(pi.HERRAMIENTAS[h] for h in LECTURA)
SHELL_PI = tuple(pi.DIALECTOS)
COMPLETADA = "completed"
TAREA_RE = re.compile(r"[A-Za-z0-9-]+")
SESIONES_CODEX = "sessions"
ROLLOUT_CODEX = "*/*/*/rollout-*-%s.jsonl"
REVISOR_RE = re.compile(r"revisor-[a-z0-9][a-z0-9-]*")
LECTURA_CODEX = "CommandExecution"
MENSAJE_CODEX = "AgentMessage"
SIN_HERRAMIENTA_CODEX = (MENSAJE_CODEX, "UserMessage", "Reasoning")
SIN_PROMPT_CODEX = "  (sin .prompt.txt: en Codex el prompt viaja cifrado y lo guarda el orquestador antes de lanzar)"
CARPETAS = {CLAUDE_CODE: "subagentes", PI: "tareas de gentle-shell", CODEX: "sesiones de Codex"}
USO_PI = {"salida": "output", "cache_escrita": "cacheWrite", "cache_leida": "cacheRead"}
CAMPOS_DE_TOKENS = ("contexto_inicial", "contexto_final", "salida", "cache_escrita", "cache_leida", "tokens_total")
CAMPOS_DEL_ANUNCIO = (("contexto final", "contexto_final"), ("salida", "salida"), ("caché escrita", "cache_escrita"),
                      ("caché leída", "cache_leida"))
SIN_MEDIR = "sin medir"
MAX_SALIDA = 2000
CODIGO_DE_SALIDA_RE = re.compile(r"Exit code (-?[0-9]+)")
CLAVES_REPORTE = ("message", "result", "report")
MARCAS_DE_MARKDOWN_RE = re.compile(r"[*_`]")
ENCABEZADO_DEL_VEREDICTO = r"[\W\d_]*(?:veredicto(?:\s+final)?|verdict)\s*:"
CUENTAS_DEL_VEREDICTO = r"\d+ critical, \d+ warning, \d+ suggestion"
VEREDICTO_RE = re.compile(ENCABEZADO_DEL_VEREDICTO, re.IGNORECASE)
CUENTAS_RE = re.compile(CUENTAS_DEL_VEREDICTO, re.IGNORECASE)
SOLO_EL_VEREDICTO_RE = re.compile(r"(?:%s\s*)?%s\.?" % (ENCABEZADO_DEL_VEREDICTO, CUENTAS_DEL_VEREDICTO), re.IGNORECASE)
MODOS = ("0", "rapido", "completo")
CARPETA_RE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})-(0|rapido|completo)(?:-([2-9]|[1-9][0-9]+))?")
COSTO = "costo.json"
DESTINO_DE_COSTO = "<ticket>/revision/<fecha>-<modo>[-<n>]/corridas"
TRIAJE_RE = re.compile(r"(?<![\w.-])triaje\.py(?![\w.])")
RECIBO_RE = re.compile(r"(?<![\w.-])recibo\.py(?![\w.])")
ESCRIBIR_RE = re.compile(r"(?<!\S)--write(?!\S)")


def texto_usuario(obj):
    m = obj.get("message")
    if not isinstance(m, dict):
        return None
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        partes = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(partes) if partes else None
    return None


def es_veredicto(texto):
    if not isinstance(texto, str):
        return False
    limpio = MARCAS_DE_MARKDOWN_RE.sub("", texto.strip())
    if "\n" not in limpio and (VEREDICTO_RE.match(limpio) or CUENTAS_RE.search(limpio)):
        return True
    return bool(SOLO_EL_VEREDICTO_RE.fullmatch(" ".join(limpio.split())))


def _reporte_de(entrada):
    for clave in CLAVES_REPORTE:
        valor = entrada.get(clave)
        if valor:
            return valor
    return json.dumps(entrada, ensure_ascii=False)


def _texto_resultado(contenido):
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return "\n".join(b.get("text", "") for b in contenido if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _cerrar_comando(comando, bloque):
    texto = _texto_resultado(bloque.get("content"))
    m = CODIGO_DE_SALIDA_RE.match(texto)
    comando["salida"] = texto[:MAX_SALIDA]
    comando["exit"] = int(m.group(1)) if m else (1 if bloque.get("is_error") else 0)
    comando["error"] = texto[:MAX_SALIDA] if bloque.get("is_error") else None


def extraer_corrida(jsonl):
    leidos = leer(jsonl)
    if leidos is None:
        raise OSError("no se pudo leer %s" % jsonl)
    registros, salteadas = leidos
    prompt = None
    reporte = None
    lecturas = []
    comandos = []
    pendientes = {}
    no_auditadas = {}
    texto_final = []
    previo = None
    for obj in registros:
        if obj.get("type") == "user" and prompt is None:
            prompt = texto_usuario(obj)
        if obj.get("type") == "user":
            for b in bloques(obj):
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in pendientes:
                    _cerrar_comando(pendientes.pop(b["tool_use_id"]), b)
        if obj.get("type") != "assistant":
            continue
        for b in bloques(obj):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text", "").strip():
                texto_final.append(b["text"])
                continue
            if b.get("type") != "tool_use":
                continue
            nombre = b.get("name")
            if nombre == HANDBACK:
                previo = "\n\n".join(texto_final)
            texto_final = []
            if nombre in LECTURA:
                lecturas.append({"tool": nombre, "input": b.get("input", {})})
            elif nombre == HANDBACK:
                reporte = _reporte_de(b.get("input", {}))
            else:
                no_auditadas[nombre] = no_auditadas.get(nombre, 0) + 1
                if nombre in SHELL:
                    comando = {"tool": nombre, "comando": b.get("input", {}).get("command"),
                               "exit": None, "error": None, "salida": None}
                    comandos.append(comando)
                    if b.get("id"):
                        pendientes[b["id"]] = comando
    origen = "handback" if reporte else None
    veredicto = None
    if es_veredicto(reporte):
        veredicto = reporte.strip()
        reporte = previo or None
        origen = "texto_previo" if reporte else "solo_veredicto"
    elif not reporte and texto_final:
        reporte = "\n\n".join(texto_final)
        origen = "texto_final"
    return {"prompt": prompt, "reporte": reporte, "origen": origen, "veredicto": veredicto, "lecturas": lecturas,
            "comandos": comandos, "no_auditadas": no_auditadas, "salteadas": salteadas, "costo": costo(registros)}


def resolver_dir_subagents(sesion):
    sesion = Path(sesion)
    if (sesion / "subagents").is_dir():
        return sesion / "subagents"
    return sesion


def _prompt_guardado(ruta):
    if not ruta.is_file():
        return None, 0
    return secretos.tapar(_leer_texto(ruta))


def _guardar(destino, nombre, agente, meta, datos, costos, con_prompt=True):
    if costos is not None:
        costos.append({"corrida": nombre, "agente": agente, "estado": "ok" if datos["reporte"] else "sin_reporte",
                       "agentType": meta.get("agentType"), "model": meta.get("model"), "costo": datos["costo"]})
    if not datos["reporte"]:
        return {"corrida": nombre, "agente": agente, "estado": "solo_veredicto" if datos.get("origen") == "solo_veredicto" else "sin_reporte",
                "lecturas": len(datos["lecturas"]), "salteadas": datos["salteadas"]}
    reporte, tapados = secretos.tapar(datos["reporte"])
    ruta_del_prompt = destino / ("%s.prompt.txt" % nombre)
    prompt, en_el_prompt = secretos.tapar(datos["prompt"] or "") if con_prompt else _prompt_guardado(ruta_del_prompt)
    lecturas, en_las_lecturas = secretos.tapar_valores({"agente": agente, "meta": meta, "lecturas": datos["lecturas"],
                                                        "no_auditadas": datos["no_auditadas"], "costo": datos["costo"]})
    tapados += en_el_prompt + en_las_lecturas
    destino.mkdir(parents=True, exist_ok=True)
    (destino / ("%s.md" % nombre)).write_text(reporte, encoding="utf-8", newline="\n")
    if con_prompt or en_el_prompt:
        ruta_del_prompt.write_text(prompt, encoding="utf-8", newline="\n")
    (destino / ("%s.lecturas.json" % nombre)).write_text(
        json.dumps(lecturas, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    if datos["comandos"]:
        comandos, en_los_comandos = secretos.tapar_valores({"agente": agente, "meta": meta, "comandos": datos["comandos"]})
        tapados += en_los_comandos
        (destino / ("%s.comandos.json" % nombre)).write_text(
            json.dumps(comandos, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    resultado = {"corrida": nombre, "agente": agente, "estado": "ok", "comandos": len(datos["comandos"]),
                 "caracteres": len(reporte), "lecturas": len(datos["lecturas"]),
                 "agentType": meta.get("agentType"), "model": meta.get("model"),
                 "no_auditadas": datos["no_auditadas"], "salteadas": datos["salteadas"]}
    if tapados:
        resultado["tapados"] = tapados
    return resultado


def rescatar(sesion, destino, corridas, costos=None):
    sub = resolver_dir_subagents(sesion)
    destino = Path(destino)
    resultados = []
    for nombre, agente in corridas.items():
        jsonl = sub / ("agent-%s.jsonl" % agente)
        if not jsonl.is_file():
            resultados.append({"corrida": nombre, "agente": agente, "estado": "no_encontrado"})
            continue
        meta_ruta = sub / ("agent-%s.meta.json" % agente)
        meta = json.loads(meta_ruta.read_text(encoding="utf-8")) if meta_ruta.is_file() else {}
        resultados.append(_guardar(destino, nombre, agente, meta, extraer_corrida(jsonl), costos))
    return resultados


def _tarea(ruta):
    try:
        datos = json.loads(Path(ruta).read_bytes().decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    tarea = datos.get("task") if isinstance(datos, dict) else None
    if not isinstance(tarea, dict) or not all(isinstance(tarea.get(clave), str) for clave in ("id", "agent", "status")):
        return None
    hilo = datos.get("thread")
    return tarea, hilo if isinstance(hilo, dict) else {}


def _instante_pi(ms):
    if not _es_entero(ms) or ms < 0:
        return None
    try:
        instante = datetime.datetime.fromtimestamp(ms // 1000, datetime.timezone.utc) + datetime.timedelta(milliseconds=ms % 1000)
    except (OverflowError, OSError, ValueError):
        return None
    return instante.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _costo_pi(tarea):
    uso = tarea.get("usage") if isinstance(tarea.get("usage"), dict) else {}
    medida = {"turnos": tarea.get("turns") if _es_entero(tarea.get("turns")) else None,
              "contexto_inicial": None, "contexto_final": None}
    medida.update({campo: uso.get(clave) if _es_entero(uso.get(clave)) else None for campo, clave in USO_PI.items()})
    medida.update({"inicio": _instante_pi(tarea.get("startedAt")), "fin": _instante_pi(tarea.get("endedAt")), "pausa_mayor": None,
                   "tokens_total": tarea.get("tokens") if _es_entero(tarea.get("tokens")) else None,
                   "costo_usd": tarea.get("cost") if _es_numero(tarea.get("cost")) else None})
    return medida if any(valor is not None for valor in medida.values()) else None


def _corrida_de_tarea(tarea, hilo):
    lecturas, corridos, no_auditadas = [], [], {}
    items = hilo.get("items") if isinstance(hilo.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict) or item.get("kind") != "tool":
            continue
        nombre = item.get("name")
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        if nombre in LECTURA_PI:
            lecturas.append({"tool": nombre, "input": args})
            continue
        no_auditadas[nombre] = no_auditadas.get(nombre, 0) + 1
        if nombre in SHELL_PI:
            comando = {"tool": nombre, "comando": args.get("command"), "exit": None, "error": None, "salida": None}
            if item.get("running") is False:
                _cerrar_comando(comando, {"content": item.get("output"), "is_error": item.get("isError") is True})
            corridos.append(comando)
    resultado = tarea.get("result")
    reporte = resultado if tarea.get("status") == COMPLETADA and isinstance(resultado, str) and resultado else None
    origen = "resultado" if reporte else None
    veredicto = None
    if es_veredicto(reporte):
        veredicto = reporte.strip()
        textos = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("kind") == "tool":
                textos = []
            elif item.get("kind") == "text" and isinstance(item.get("text"), str) and item["text"].strip() not in ("", veredicto):
                textos.append(item["text"])
        reporte = "\n\n".join(textos) or None
        origen = "texto_previo" if reporte else "solo_veredicto"
    prompt = tarea.get("prompt")
    descartados = hilo.get("dropped")
    return {"prompt": prompt if isinstance(prompt, str) else None, "reporte": reporte, "origen": origen, "veredicto": veredicto,
            "lecturas": lecturas, "comandos": corridos, "no_auditadas": no_auditadas,
            "salteadas": descartados if _es_entero(descartados) and descartados > 0 else 0, "costo": _costo_pi(tarea)}


def extraer_corrida_pi(ruta):
    leida = _tarea(ruta)
    if leida is None:
        raise OSError("%s no es una tarea de gentle-shell que se pueda leer" % ruta)
    return _corrida_de_tarea(*leida)


def _es_la_carpeta_de_tareas(carpeta):
    partes = Path(os.path.normcase(os.path.abspath(carpeta))).parts
    return partes[-len(pi.TAREAS_DE_GENTLE_AGENTS.parts):] == tuple(map(os.path.normcase, pi.TAREAS_DE_GENTLE_AGENTS.parts))


def carpeta_de_tareas(sesion=None):
    if sesion is not None:
        sesion = Path(sesion)
        return sesion if _es_la_carpeta_de_tareas(sesion) else sesion / pi.TAREAS_DE_GENTLE_AGENTS
    ctx = types.SimpleNamespace(home=Path.home(), entorno=os.environ, windows=os.name == "nt")
    return pi.home_de_gentle_agents(ctx) / pi.TAREAS_DE_GENTLE_AGENTS


def rescatar_pi(tareas, destino, corridas, costos=None):
    tareas, destino = Path(tareas), Path(destino)
    resultados = []
    for nombre, id_ in corridas.items():
        ruta = tareas / ("%s.json" % id_)
        leida = _tarea(ruta) if ruta.is_file() else None
        if leida is None:
            resultados.append({"corrida": nombre, "agente": id_, "estado": "ilegible" if ruta.is_file() else "no_encontrado"})
            continue
        tarea, hilo = leida
        meta = {"agentType": tarea.get("agent"), "model": tarea.get("model")}
        resultado = _guardar(destino, nombre, id_, meta, _corrida_de_tarea(tarea, hilo), costos)
        resultado["tarea"] = tarea["status"]
        resultados.append(resultado)
    return resultados


def _rol_codex(meta):
    origen = meta.get("source") if isinstance(meta, dict) else None
    subagente = origen.get("subagent") if isinstance(origen, dict) else None
    lanzado = subagente.get("thread_spawn") if isinstance(subagente, dict) else None
    rol = lanzado.get("agent_role") if isinstance(lanzado, dict) else None
    return rol if isinstance(rol, str) else None


def _texto_codex(item):
    contenido = item.get("content")
    if not isinstance(contenido, list):
        return ""
    return "\n".join(b["text"] for b in contenido if isinstance(b, dict) and isinstance(b.get("text"), str))


def _sin_el_veredicto(texto):
    lineas = texto.rstrip().split("\n")
    for n in (2, 1):
        cola = "\n".join(lineas[-n:])
        if len(lineas) >= n and es_veredicto(cola):
            return "\n".join(lineas[:-n]).rstrip(), cola.strip()
    return texto, None


def _corrida_de_rollout(registros, salteadas):
    lecturas, no_auditadas, textos, final, modelo = [], {}, [], None, None
    for registro in registros:
        carga = registro.get("payload") if isinstance(registro.get("payload"), dict) else {}
        if registro.get("type") == "turn_context" and isinstance(carga.get("model"), str):
            modelo = carga["model"]
        if registro.get("type") != "event_msg":
            continue
        if carga.get("type") == "task_complete":
            final = carga.get("last_agent_message")
            continue
        item = carga.get("item")
        if carga.get("type") != "item_completed" or not isinstance(item, dict):
            continue
        tipo = item.get("type") if isinstance(item.get("type"), str) else "sin tipo"
        if tipo == MENSAJE_CODEX:
            textos.append(_texto_codex(item))
        elif tipo == LECTURA_CODEX:
            lecturas.append({"tool": tipo, "input": {"command": item.get("command"), "cwd": item.get("cwd")}, "exit": item.get("exit_code")})
            textos = []
        elif tipo not in SIN_HERRAMIENTA_CODEX:
            no_auditadas[tipo] = no_auditadas.get(tipo, 0) + 1
            textos = []
    reporte, veredicto = _sin_el_veredicto(final) if isinstance(final, str) and final.strip() else (None, None)
    origen = "task_complete" if reporte else None
    if veredicto is not None and not reporte:
        previos = [t for t in textos if t.strip() and t.strip() != final.strip() and not es_veredicto(t)]
        reporte = "\n\n".join(_sin_el_veredicto(t)[0] for t in previos) or None
        origen = "texto_previo" if reporte else "solo_veredicto"
    return {"prompt": None, "reporte": reporte, "origen": origen, "veredicto": veredicto, "lecturas": lecturas, "comandos": [],
            "no_auditadas": no_auditadas, "salteadas": salteadas, "costo": costo_codex(registros),
            "rol": _rol_codex(registros[0].get("payload")), "modelo": modelo}


def _rollout(ruta):
    leidos = leer(ruta)
    if leidos is None or not leidos[0] or leidos[0][0].get("type") != "session_meta":
        return None
    return _corrida_de_rollout(*leidos)


def extraer_corrida_codex(ruta):
    datos = _rollout(ruta)
    if datos is None:
        raise OSError("%s no es un rollout de Codex que se pueda leer" % ruta)
    return datos


def carpeta_de_sesiones(sesion=None):
    if sesion is not None:
        sesion = Path(sesion)
        return sesion if sesion.name == SESIONES_CODEX else sesion / SESIONES_CODEX
    return codex.carpeta_de_codex(types.SimpleNamespace(home=Path.home(), entorno=os.environ)) / SESIONES_CODEX


def rescatar_codex(sesiones, destino, corridas, costos=None):
    sesiones, destino = Path(sesiones), Path(destino)
    resultados = []
    for nombre, hilo in corridas.items():
        rollouts = sorted(sesiones.glob(ROLLOUT_CODEX % hilo))
        datos = _rollout(rollouts[-1]) if rollouts else None
        if datos is None:
            resultados.append({"corrida": nombre, "agente": hilo, "estado": "ilegible" if rollouts else "no_encontrado"})
            continue
        if not REVISOR_RE.fullmatch(datos["rol"] or ""):
            resultados.append({"corrida": nombre, "agente": hilo, "estado": "no_es_revisor", "rol": datos["rol"]})
            continue
        meta = {"agentType": datos["rol"], "model": datos["modelo"]}
        resultados.append(_guardar(destino, nombre, hilo, meta, datos, costos, con_prompt=False))
    return resultados


def _leer_texto(ruta):
    crudo = Path(ruta).read_bytes()
    if crudo.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return crudo.decode("utf-16", errors="replace")
    return crudo.decode("utf-8-sig", errors="replace")


def lineas_del_diff(texto):
    lineas, en_hunk = 0, False
    for linea in texto.split("\n"):
        if linea.startswith("diff "):
            en_hunk = False
        elif linea.startswith("@@"):
            en_hunk = True
        elif en_hunk and linea[:1] in ("+", "-"):
            lineas += 1
    return lineas


def revision_del_destino(destino):
    revision = Path(os.path.abspath(destino)).parent
    return revision if CARPETA_RE.fullmatch(revision.name) and revision.parent.name == "revision" else None


def _corridas_previas(ruta, avisos):
    if not ruta.exists():
        return []
    try:
        corridas = json.loads(ruta.read_text(encoding="utf-8"))["corridas"]
        if isinstance(corridas, list) and all(isinstance(c, dict) and isinstance(c.get("agente"), str) for c in corridas):
            return corridas
    except (OSError, ValueError, KeyError, TypeError):
        pass
    avisos.append("%s no se pudo leer; se reescribe con las corridas de este rescate" % ruta)
    return []


def _motivos(entrada, avisos):
    ruta = entrada / "triaje.json"
    try:
        datos = json.loads(_leer_texto(ruta))
    except (OSError, ValueError):
        datos = None
    motivos = datos.get("motivos") if isinstance(datos, dict) else None
    if isinstance(motivos, list):
        return motivos
    avisos.append("no hay motivos en %s; quedan en null" % ruta)
    return None


def _lineas_de_la_entrada(entrada, avisos):
    diffs = sorted(d for d in entrada.glob("*.diff") if d.is_file()) if entrada.is_dir() else []
    if not diffs:
        avisos.append("no hay diffs en %s; lineas_diff queda en null" % entrada)
        return None
    return sum(lineas_del_diff(_leer_texto(d)) for d in diffs)


def transcript_principal(sub):
    sub = Path(os.path.abspath(sub))
    sesion = sub.parent if sub.name == "subagents" else sub
    return sesion.parent / (sesion.name + ".jsonl")


def _sin_orquestador(avisos, motivo):
    avisos.append("%s; orquestador queda en null" % motivo)


def costo_del_orquestador(sub, agentes, avisos):
    ruta = transcript_principal(sub)
    leidos = leer(ruta)
    if leidos is None:
        return _sin_orquestador(avisos, "no hay transcript de la sesion principal en %s" % ruta)
    registros = leidos[0]
    lanzados = lanzamientos(registros)
    primero = min((lanzados[a] for a in agentes if a in lanzados), default=None)
    if primero is None:
        return _sin_orquestador(avisos, "no se encontro el lanzamiento de ninguna corrida en %s" % ruta)
    llamadas = list(comandos(registros))
    triajes = [i for i, c in llamadas if i < primero and TRIAJE_RE.search(c)]
    if not triajes:
        return _sin_orquestador(avisos, "no hay un triaje.py antes del primer lanzamiento de las corridas en %s" % ruta)
    recibos = [i for i, c in llamadas if i > primero and RECIBO_RE.search(c) and ESCRIBIR_RE.search(c)]
    medida = costo(registros[triajes[-1]:recibos[0] + 1 if recibos else None])
    if medida is None:
        return _sin_orquestador(avisos, "el tramo de %s no tiene datos de uso" % ruta)
    medida["contexto_dejado"] = medida["contexto_final"] - medida["contexto_inicial"]
    return medida


def escribir_costo(destino, costos, sub, agentes, host=CLAUDE_CODE):
    destino = Path(destino)
    revision = revision_del_destino(destino)
    entrada = revision / "entrada"
    ruta = destino / COSTO
    avisos = []
    por_agente = {c["agente"]: c for c in _corridas_previas(ruta, avisos)}
    for c in costos:
        por_agente[c["agente"]] = c
    datos = {"modo": CARPETA_RE.fullmatch(revision.name).group(2), "motivos": _motivos(entrada, avisos),
             "corridas": list(por_agente.values()), "lineas_diff": _lineas_de_la_entrada(entrada, avisos)}
    datos["orquestador"] = (costo_del_orquestador(sub, agentes, avisos) if host == CLAUDE_CODE
                            else _sin_orquestador(avisos, "el costo del orquestador solo se mide en Claude Code"))
    datos["en_serie"] = en_serie([c.get("costo") for c in datos["corridas"]])
    destino.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return ruta, datos, avisos


def _es_entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _con_datos_de_uso(medida):
    return isinstance(medida, dict) and (any(_es_entero(medida.get(campo)) for campo in CAMPOS_DE_TOKENS)
                                         or _es_numero(medida.get("costo_usd")))


def _promedio(medidas, clave):
    valores = [m[clave] for m in medidas if _es_entero(m.get(clave))]
    return "{:,}".format(round(sum(valores) / len(valores))).replace(",", " ") if valores else SIN_MEDIR


def _en_tokens(promedio):
    textos = ["%s %s" % (nombre, promedio[clave]) for nombre, clave in CAMPOS_DEL_ANUNCIO]
    medidos = [i for i, (_, clave) in enumerate(CAMPOS_DEL_ANUNCIO) if promedio[clave] != SIN_MEDIR]
    if medidos:
        textos[medidos[-1]] += " tokens"
    return "%s y %s" % (", ".join(textos[:-1]), textos[-1])


def _totales(medidas):
    partes = []
    tokens = _promedio(medidas, "tokens_total")
    if tokens != SIN_MEDIR:
        partes.append("%s tokens en total" % tokens)
    costos = [m["costo_usd"] for m in medidas if _es_numero(m.get("costo_usd"))]
    if costos:
        partes.append(("%.4f USD" % (sum(costos) / len(costos))).replace(".", ","))
    return " y ".join(partes)


def _por_corrida(medidas):
    promedio = {clave: _promedio(medidas, clave) for _, clave in CAMPOS_DEL_ANUNCIO}
    totales = _totales(medidas)
    if totales and all(valor == SIN_MEDIR for valor in promedio.values()):
        return totales
    return _en_tokens(promedio)


def _medida(ruta, avisos):
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        corridas = [c for c in datos["corridas"] if isinstance(c, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        avisos.append("se ignora %s (no es un costo.json legible)" % ruta)
        return None
    medidas = [c["costo"] for c in corridas if _con_datos_de_uso(c.get("costo"))]
    if not medidas:
        return None
    fines = [m["fin"] for m in medidas if isinstance(m.get("fin"), str)]
    lineas = datos.get("lineas_diff")
    return {"medidas": medidas, "total": len(corridas), "fin": max(fines) if fines else "",
            "lineas": lineas if _es_entero(lineas) else None, "en_serie": datos.get("en_serie") is True}


def _mas_nueva(carpeta, patron, avisos, excluir=None):
    candidatas = []
    for ruta in sorted(carpeta.glob(patron)):
        revision = ruta.parent.parent
        m = CARPETA_RE.fullmatch(revision.name)
        if not m or revision.parent.name != "revision" or (excluir is not None and excluir in ruta.parents):
            continue
        medida = _medida(ruta, avisos)
        if medida is not None:
            orden = (m.group(1), medida["fin"], MODOS.index(m.group(2)), int(m.group(3) or 1), ruta.as_posix())
            candidatas.append((orden, m.group(2), revision, medida))
    return max(candidatas, key=lambda c: c[0])[1:] if candidatas else None


def _raiz_de_tickets(ticket):
    for carpeta in ticket.parents:
        if carpeta.name == TICKETS:
            return carpeta
    return None


def ultimo_costo(ticket):
    ticket = Path(os.path.abspath(ticket))
    avisos = []
    tickets = _raiz_de_tickets(ticket)
    elegida, origen = _mas_nueva(ticket, "revision/*/corridas/" + COSTO, avisos), "del ticket"
    if elegida is None and tickets is not None:
        elegida = _mas_nueva(tickets, "**/revision/*/corridas/" + COSTO, avisos, excluir=ticket)
        origen = "de la instancia (el ticket no tiene)"
    if elegida is None:
        return None, avisos
    modo, revision, medida = elegida
    relativa = Path(os.path.relpath(revision, tickets.parent if tickets is not None else ticket.parent)).as_posix()
    n = len(medida["medidas"])
    corridas = "%d corrida(s)" % n if n == medida["total"] else "%d de %d corrida(s) con datos de uso" % (n, medida["total"])
    lineas = "líneas de diff sin medir" if medida["lineas"] is None else "%d líneas de diff" % medida["lineas"]
    return ("último costo medido, %s: %s: modo %s, %s, %s; por corrida, en promedio: %s turnos, %s%s" % (
        origen, relativa, modo, corridas, lineas, _promedio(medida["medidas"], "turnos"), _por_corrida(medida["medidas"]),
        "; las corridas corrieron en serie" if medida["en_serie"] else "")), avisos


def _parsear_corridas(crudas, host=CLAUDE_CODE):
    forma = {PI: "<nombre>=<task_id>", CODEX: "<nombre>=<thread_id>"}.get(host, "<nombre>=<agentId>")
    corridas = {}
    for c in crudas:
        nombre, igual, agente = c.partition("=")
        nombre, agente = nombre.strip(), agente.strip()
        if not igual or not nombre or not agente or (host in (PI, CODEX) and not TAREA_RE.fullmatch(agente)):
            raise ValueError("--corrida espera %s, recibio %r" % (forma, c))
        if host == CLAUDE_CODE and agente.startswith("agent-"):
            agente = agente[len("agent-"):]
        corridas[nombre] = agente
    return corridas


def _main_ultimo_costo(args):
    if args.sesion is not None or args.destino is not None or args.corrida is not None or args.costo:
        print("rescatar: --ultimo-costo no se combina con --sesion, --destino, --corrida ni --costo")
        return 2
    if not os.path.isdir(args.ultimo_costo):
        print("rescatar: no existe la carpeta del ticket %s" % args.ultimo_costo)
        return 2
    linea, avisos = ultimo_costo(args.ultimo_costo)
    for aviso in avisos:
        print("aviso costo: %s" % aviso, file=sys.stderr)
    print(linea or "sin costo medido en el ticket ni en la instancia")
    return 0 if linea else 1


def _parser():
    parser = argparse.ArgumentParser(
        usage="%(prog)s --sesion SESION --destino DESTINO --corrida NOMBRE=AGENTID [--corrida ...] [--costo]\n"
              "       %(prog)s --host pi --destino DESTINO --corrida NOMBRE=TASK_ID [--corrida ...] [--sesion CARPETA] [--costo]\n"
              "       %(prog)s --host codex --destino DESTINO --corrida NOMBRE=THREAD_ID [--corrida ...] [--sesion CODEX_HOME] "
              "[--costo]\n"
              "       %(prog)s --ultimo-costo TICKET",
        description="Rescata reporte, prompt, lecturas y costo de corridas de subagentes desde su JSONL de Claude Code, "
                    "desde la tarea que guarda gentle-shell o desde el rollout de Codex.")
    parser.add_argument("--host", choices=HOSTS, default=CLAUDE_CODE,
                        help="claude-code (por defecto) lee subagents/agent-<agentId>.jsonl; pi lee la tarea que guarda "
                             "gentle-shell, <agentHome>/gentle-agents/tasks/<task_id>.json, con agentHome "
                             "GENTLE_PI_AGENT_HOME, si no PI_CODING_AGENT_DIR, si no ~/.pi/agent; codex lee el rollout del "
                             "revisor, <CODEX_HOME>/sessions/*/*/*/rollout-*-<thread_id>.jsonl, con CODEX_HOME por defecto "
                             "~/.codex, si su agent_role es el de un revisor (revisor-<...>), y no escribe .prompt.txt, porque "
                             "el prompt viaja cifrado")
    parser.add_argument("--sesion", help="carpeta subagents (o la de la sesion que la contiene); con --host pi es opcional: "
                                         "la carpeta de tareas de gentle-shell (<agentHome>/gentle-agents/tasks), o el "
                                         "agentHome que la contiene; si no la tiene, sale con 2; con --host codex es "
                                         "opcional: el CODEX_HOME o su carpeta sessions")
    parser.add_argument("--destino", help="carpeta donde se escriben los archivos de cada corrida")
    parser.add_argument("--corrida", action="append", metavar="NOMBRE=AGENTID",
                        help="repetible; el nombre es el de los archivos a escribir; con --host pi va el task_id; con --host "
                             "codex, el thread_id")
    parser.add_argument("--costo", action="store_true",
                        help="escribe tambien costo.json en --destino, que tiene que ser %s: el modo de la carpeta, "
                             "los motivos de entrada/triaje.json, el costo de cada corrida, las lineas de entrada/*.diff, "
                             "el costo del orquestador desde el ultimo triaje.py, leido de <sesion>.jsonl (en Pi y en Codex "
                             "queda en null), y si las corridas corrieron en serie" % DESTINO_DE_COSTO)
    parser.add_argument("--ultimo-costo", metavar="TICKET",
                        help="imprime en una linea el ultimo costo medido del ticket o, si no tiene, de la instancia; "
                             "sale con 1 si no hay ninguno")
    return parser


def _avisar_fallo(r, sub, host):
    if r["estado"] == "solo_veredicto":
        print("FAIL %s: el revisor devolvio solo el veredicto y su reporte no quedo como texto antes de la devolucion, "
              "%d lecturas, no se escribio nada" % (r["corrida"], r.get("lecturas", 0)))
    elif r["estado"] == "sin_reporte" and host == PI:
        print("FAIL %s: tarea %s en estado %s, sin reporte (corrida cortada), %d lecturas, no se escribio nada" % (
            r["corrida"], r["agente"], r["tarea"], r.get("lecturas", 0)))
    elif r["estado"] == "sin_reporte" and host == CODEX:
        print("FAIL %s: hilo %s sin task_complete con su mensaje final (corrida cortada), %d lecturas, no se escribio nada" % (
            r["corrida"], r["agente"], r.get("lecturas", 0)))
    elif r["estado"] == "sin_reporte":
        print("FAIL %s: sin SubagentHandback (corrida cortada), %d lecturas, no se escribio nada" % (
            r["corrida"], r.get("lecturas", 0)))
    elif r["estado"] == "no_es_revisor":
        print("FAIL %s: el hilo %s es de %s, no de un revisor, no se escribio nada: lanza cada revisor con su agent_type y "
              "fork_turns \"none\"" % (r["corrida"], r["agente"], r["rol"] or "un agente sin agent_role"))
    elif r["estado"] == "ilegible" and host == CODEX:
        print("FAIL %s: rollout-*-%s.jsonl no es un rollout de Codex que se pueda leer, no se escribio nada" % (r["corrida"], r["agente"]))
    elif r["estado"] == "ilegible":
        print("FAIL %s: %s.json no es una tarea de gentle-shell que se pueda leer, no se escribio nada" % (r["corrida"], r["agente"]))
    elif host == PI:
        print("FAIL %s: no existe %s.json en %s" % (r["corrida"], r["agente"], sub))
    elif host == CODEX:
        print("FAIL %s: no existe rollout-*-%s.jsonl en %s" % (r["corrida"], r["agente"], sub))
    else:
        print("FAIL %s: no existe agent-%s.jsonl en %s" % (r["corrida"], r["agente"], sub))


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if args.ultimo_costo is not None:
        return _main_ultimo_costo(args)
    obligatorias = (("--sesion", args.sesion),) if args.host == CLAUDE_CODE else ()
    faltan = [o for o, v in obligatorias + (("--destino", args.destino), ("--corrida", args.corrida)) if v is None]
    if faltan:
        parser.error("the following arguments are required: %s" % ", ".join(faltan))

    try:
        corridas = _parsear_corridas(args.corrida, args.host)
    except ValueError as exc:
        print("rescatar: %s" % exc)
        return 2
    if args.costo and revision_del_destino(args.destino) is None:
        print("rescatar: --costo espera --destino %s, recibio %s" % (DESTINO_DE_COSTO, args.destino))
        return 2
    carpeta, rescate = {PI: (carpeta_de_tareas, rescatar_pi), CODEX: (carpeta_de_sesiones, rescatar_codex)}.get(
        args.host, (resolver_dir_subagents, rescatar))
    sub = carpeta(args.sesion)
    if not sub.is_dir():
        print("rescatar: no existe la carpeta de %s %s" % (CARPETAS[args.host], sub))
        return 2

    fallos = 0
    costos = [] if args.costo else None
    for r in rescate(sub, args.destino, corridas, costos):
        if r["estado"] == "ok":
            extra = ""
            if r["no_auditadas"]:
                extra = "  (herramientas NO auditadas: %s)" % ", ".join(
                    "%s x%d" % kv for kv in sorted(r["no_auditadas"].items()))
            if r["comandos"]:
                extra += "  (comandos Bash/PowerShell: %d en %s.comandos.json)" % (r["comandos"], r["corrida"])
            if r.get("tapados"):
                extra += "  (%d secreto(s) tapado(s) antes de guardar)" % r["tapados"]
            if args.host == CODEX:
                extra += SIN_PROMPT_CODEX
            print("ok   %s: %d car., %d lecturas, %s/%s%s" % (
                r["corrida"], r["caracteres"], r["lecturas"], r["agentType"], r["model"], extra))
        else:
            fallos += 1
            _avisar_fallo(r, sub, args.host)
        if r.get("salteadas") and args.host == PI:
            print("aviso %s: gentle-shell descarto %d elemento(s) del hilo de la tarea %s (dropped): las lecturas y las "
                  "herramientas pueden estar incompletas" % (r["corrida"], r["salteadas"], r["agente"]), file=sys.stderr)
        elif r.get("salteadas"):
            print("aviso %s: %d linea(s) de %s.jsonl no se pudieron leer y se saltearon" % (
                r["corrida"], r["salteadas"], ("rollout-*-%s" if args.host == CODEX else "agent-%s") % r["agente"]), file=sys.stderr)
    if costos is not None:
        ruta, datos, avisos = escribir_costo(args.destino, costos, sub, list(corridas.values()), args.host)
        for aviso in avisos:
            print("aviso costo: %s" % aviso, file=sys.stderr)
        sin_uso = sum(1 for c in datos["corridas"] if not _con_datos_de_uso(c.get("costo")))
        print("costo: %d corrida(s) en %s%s" % (len(datos["corridas"]), ruta, " (%d sin datos de uso)" % sin_uso if sin_uso else ""))
    return 1 if fallos else 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("rescatar: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
