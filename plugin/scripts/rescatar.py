import sys

sys.dont_write_bytecode = True

import argparse
import codecs
import json
import os
import re
from pathlib import Path

from odd_ws.capas import TICKETS
from odd_ws.transcripcion import HANDBACK, LECTURA, bloques, costo, leer

SHELL = ("Bash", "PowerShell")
MAX_SALIDA = 2000
CODIGO_DE_SALIDA_RE = re.compile(r"Exit code (-?[0-9]+)")
CLAVES_REPORTE = ("message", "result", "report")
MODOS = ("0", "rapido", "completo")
CARPETA_RE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})-(0|rapido|completo)(?:-([2-9]|[1-9][0-9]+))?")
COSTO = "costo.json"
DESTINO_DE_COSTO = "<ticket>/revision/<fecha>-<modo>[-<n>]/corridas"


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
            texto_final = []
            nombre = b.get("name")
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
    if not reporte and texto_final:
        reporte = "\n\n".join(texto_final)
        origen = "texto_final"
    return {"prompt": prompt, "reporte": reporte, "origen": origen, "lecturas": lecturas,
            "comandos": comandos, "no_auditadas": no_auditadas, "salteadas": salteadas, "costo": costo(registros)}


def resolver_dir_subagents(sesion):
    sesion = Path(sesion)
    if (sesion / "subagents").is_dir():
        return sesion / "subagents"
    return sesion


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
        datos = extraer_corrida(jsonl)
        if costos is not None:
            costos.append({"corrida": nombre, "agente": agente, "estado": "ok" if datos["reporte"] else "sin_reporte",
                           "agentType": meta.get("agentType"), "model": meta.get("model"), "costo": datos["costo"]})
        if not datos["reporte"]:
            resultados.append({"corrida": nombre, "agente": agente, "estado": "sin_reporte",
                               "lecturas": len(datos["lecturas"]), "salteadas": datos["salteadas"]})
            continue
        destino.mkdir(parents=True, exist_ok=True)
        (destino / ("%s.md" % nombre)).write_text(datos["reporte"], encoding="utf-8", newline="\n")
        (destino / ("%s.prompt.txt" % nombre)).write_text(datos["prompt"] or "", encoding="utf-8", newline="\n")
        (destino / ("%s.lecturas.json" % nombre)).write_text(
            json.dumps({"agente": agente, "meta": meta, "lecturas": datos["lecturas"], "no_auditadas": datos["no_auditadas"],
                        "costo": datos["costo"]}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        if datos["comandos"]:
            (destino / ("%s.comandos.json" % nombre)).write_text(
                json.dumps({"agente": agente, "meta": meta, "comandos": datos["comandos"]},
                           ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        resultados.append({"corrida": nombre, "agente": agente, "estado": "ok", "comandos": len(datos["comandos"]),
                           "caracteres": len(datos["reporte"]), "lecturas": len(datos["lecturas"]),
                           "agentType": meta.get("agentType"), "model": meta.get("model"),
                           "no_auditadas": datos["no_auditadas"], "salteadas": datos["salteadas"]})
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


def escribir_costo(destino, costos):
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
    destino.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return ruta, datos, avisos


def _es_entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _entero(valor):
    return valor if _es_entero(valor) else 0


def _medida(ruta, avisos):
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        corridas = [c for c in datos["corridas"] if isinstance(c, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        avisos.append("se ignora %s (no es un costo.json legible)" % ruta)
        return None
    medidas = [c["costo"] for c in corridas if isinstance(c.get("costo"), dict)]
    if not medidas:
        return None
    fines = [m["fin"] for m in medidas if isinstance(m.get("fin"), str)]
    lineas = datos.get("lineas_diff")
    return {"medidas": medidas, "total": len(corridas), "fin": max(fines) if fines else "",
            "lineas": lineas if _es_entero(lineas) else None}


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
    promedio = {clave: "{:,}".format(round(sum(_entero(m.get(clave)) for m in medida["medidas"]) / n)).replace(",", " ")
                for clave in ("turnos", "contexto_final", "salida", "cache_escrita", "cache_leida")}
    return ("último costo medido, %s: %s: modo %s, %s, %s; por corrida, en promedio: %s turnos, contexto final %s, "
            "salida %s, caché escrita %s y caché leída %s tokens" % (
                origen, relativa, modo, corridas, lineas, promedio["turnos"], promedio["contexto_final"],
                promedio["salida"], promedio["cache_escrita"], promedio["cache_leida"])), avisos


def _parsear_corridas(crudas):
    corridas = {}
    for c in crudas:
        if "=" not in c:
            raise ValueError("--corrida espera <nombre>=<agentId>, recibio %r" % c)
        nombre, agente = c.split("=", 1)
        nombre, agente = nombre.strip(), agente.strip()
        if not nombre or not agente:
            raise ValueError("--corrida espera <nombre>=<agentId>, recibio %r" % c)
        if agente.startswith("agent-"):
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        usage="%(prog)s --sesion SESION --destino DESTINO --corrida NOMBRE=AGENTID [--corrida ...] [--costo]\n"
              "       %(prog)s --ultimo-costo TICKET",
        description="Rescata reporte, prompt, lecturas y costo de corridas de subagentes desde su JSONL.")
    parser.add_argument("--sesion", help="carpeta subagents (o la de la sesion que la contiene)")
    parser.add_argument("--destino", help="carpeta donde se escriben los archivos de cada corrida")
    parser.add_argument("--corrida", action="append", metavar="NOMBRE=AGENTID",
                        help="repetible; el nombre es el de los archivos a escribir")
    parser.add_argument("--costo", action="store_true",
                        help="escribe tambien costo.json en --destino, que tiene que ser %s: el modo de la carpeta, "
                             "los motivos de entrada/triaje.json, el costo de cada corrida y las lineas de entrada/*.diff"
                             % DESTINO_DE_COSTO)
    parser.add_argument("--ultimo-costo", metavar="TICKET",
                        help="imprime en una linea el ultimo costo medido del ticket o, si no tiene, de la instancia; "
                             "sale con 1 si no hay ninguno")
    args = parser.parse_args(argv)
    if args.ultimo_costo is not None:
        return _main_ultimo_costo(args)
    faltan = [o for o, v in (("--sesion", args.sesion), ("--destino", args.destino), ("--corrida", args.corrida)) if v is None]
    if faltan:
        parser.error("the following arguments are required: %s" % ", ".join(faltan))

    try:
        corridas = _parsear_corridas(args.corrida)
    except ValueError as exc:
        print("rescatar: %s" % exc)
        return 2
    if args.costo and revision_del_destino(args.destino) is None:
        print("rescatar: --costo espera --destino %s, recibio %s" % (DESTINO_DE_COSTO, args.destino))
        return 2
    sub = resolver_dir_subagents(args.sesion)
    if not sub.is_dir():
        print("rescatar: no existe la carpeta de subagentes %s" % sub)
        return 2

    fallos = 0
    costos = [] if args.costo else None
    for r in rescatar(sub, args.destino, corridas, costos):
        if r["estado"] == "ok":
            extra = ""
            if r["no_auditadas"]:
                extra = "  (herramientas NO auditadas: %s)" % ", ".join(
                    "%s x%d" % kv for kv in sorted(r["no_auditadas"].items()))
            if r["comandos"]:
                extra += "  (comandos Bash/PowerShell: %d en %s.comandos.json)" % (r["comandos"], r["corrida"])
            print("ok   %s: %d car., %d lecturas, %s/%s%s" % (
                r["corrida"], r["caracteres"], r["lecturas"], r["agentType"], r["model"], extra))
        elif r["estado"] == "sin_reporte":
            fallos += 1
            print("FAIL %s: sin SubagentHandback (corrida cortada), %d lecturas, no se escribio nada" % (
                r["corrida"], r.get("lecturas", 0)))
        else:
            fallos += 1
            print("FAIL %s: no existe agent-%s.jsonl en %s" % (r["corrida"], r["agente"], sub))
        if r.get("salteadas"):
            print("aviso %s: %d linea(s) de agent-%s.jsonl no se pudieron leer y se saltearon" % (
                r["corrida"], r["salteadas"], r["agente"]), file=sys.stderr)
    if costos is not None:
        ruta, datos, avisos = escribir_costo(args.destino, costos)
        for aviso in avisos:
            print("aviso costo: %s" % aviso, file=sys.stderr)
        sin_uso = sum(1 for c in datos["corridas"] if c.get("costo") is None)
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
