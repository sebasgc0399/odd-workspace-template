import sys

sys.dont_write_bytecode = True

import argparse
import json
import re
from pathlib import Path

from odd_ws.transcripcion import HANDBACK, LECTURA, bloques, leer

SHELL = ("Bash", "PowerShell")
MAX_SALIDA = 2000
CODIGO_DE_SALIDA_RE = re.compile(r"Exit code (-?[0-9]+)")
CLAVES_REPORTE = ("message", "result", "report")


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
            "comandos": comandos, "no_auditadas": no_auditadas, "salteadas": salteadas}


def resolver_dir_subagents(sesion):
    sesion = Path(sesion)
    if (sesion / "subagents").is_dir():
        return sesion / "subagents"
    return sesion


def rescatar(sesion, destino, corridas):
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
        if not datos["reporte"]:
            resultados.append({"corrida": nombre, "agente": agente, "estado": "sin_reporte",
                               "lecturas": len(datos["lecturas"]), "salteadas": datos["salteadas"]})
            continue
        destino.mkdir(parents=True, exist_ok=True)
        (destino / ("%s.md" % nombre)).write_text(datos["reporte"], encoding="utf-8", newline="\n")
        (destino / ("%s.prompt.txt" % nombre)).write_text(datos["prompt"] or "", encoding="utf-8", newline="\n")
        (destino / ("%s.lecturas.json" % nombre)).write_text(
            json.dumps({"agente": agente, "meta": meta, "lecturas": datos["lecturas"], "no_auditadas": datos["no_auditadas"]},
                       ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        if datos["comandos"]:
            (destino / ("%s.comandos.json" % nombre)).write_text(
                json.dumps({"agente": agente, "meta": meta, "comandos": datos["comandos"]},
                           ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        resultados.append({"corrida": nombre, "agente": agente, "estado": "ok", "comandos": len(datos["comandos"]),
                           "caracteres": len(datos["reporte"]), "lecturas": len(datos["lecturas"]),
                           "agentType": meta.get("agentType"), "model": meta.get("model"),
                           "no_auditadas": datos["no_auditadas"], "salteadas": datos["salteadas"]})
    return resultados


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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Rescata reporte, prompt y lecturas de corridas de subagentes desde su JSONL.")
    parser.add_argument("--sesion", required=True, help="carpeta subagents (o la de la sesion que la contiene)")
    parser.add_argument("--destino", required=True, help="carpeta donde se escriben los archivos de cada corrida")
    parser.add_argument("--corrida", action="append", required=True, metavar="NOMBRE=AGENTID",
                        help="repetible; el nombre es el de los archivos a escribir")
    args = parser.parse_args(argv)

    try:
        corridas = _parsear_corridas(args.corrida)
    except ValueError as exc:
        print("rescatar: %s" % exc)
        return 2
    sub = resolver_dir_subagents(args.sesion)
    if not sub.is_dir():
        print("rescatar: no existe la carpeta de subagentes %s" % sub)
        return 2

    fallos = 0
    for r in rescatar(sub, args.destino, corridas):
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
