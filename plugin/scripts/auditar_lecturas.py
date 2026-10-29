import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import posixpath
import re
from pathlib import Path

import config_loader
from odd_ws import capas as convencion
from odd_ws.comun import raiz_de_instancia
from odd_ws.transcripcion import HANDBACK, LECTURA, bloques, leer

_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_MSYS = re.compile(r"^/([A-Za-z])(?:/|$)")


def normalizar_ruta(ruta, cwd):
    r = str(ruta).strip().replace("\\", "/")
    if r.startswith("//?/"):
        r = r[4:]
    m = _MSYS.match(r)
    if m:
        r = "%s:/%s" % (m.group(1), r[m.end():])
    elif not (re.match(r"^[A-Za-z]:", r) or r.startswith("/")):
        base = str(cwd).replace("\\", "/").rstrip("/")
        r = "%s/%s" % (base, r)
    r = posixpath.normpath(r)
    return r.lower().rstrip("/") if len(r) > 3 else r.lower()


def es_bajo(ruta, raiz):
    if ruta == raiz:
        return True
    return ruta.startswith(raiz.rstrip("/") + "/")


def _es_fisica(ruta_norm):
    return convencion.CARPETA_VERDAD in ruta_norm.split("/")


def armar_reglas(prohibidas, permitidas, cwd):
    reglas = []
    for original in prohibidas:
        n = normalizar_ruta(original, cwd)
        reglas.append({"ruta": n, "original": original, "tipo": "prohibida", "fisica": _es_fisica(n)})
    for original in permitidas:
        n = normalizar_ruta(original, cwd)
        reglas.append({"ruta": n, "original": original, "tipo": "permitida", "fisica": False})
    return reglas


def regla_que_cubre(ruta_norm, reglas):
    mejor = None
    for r in reglas:
        if not es_bajo(ruta_norm, r["ruta"]):
            continue
        if (mejor is None or len(r["ruta"]) > len(mejor["ruta"])
                or (len(r["ruta"]) == len(mejor["ruta"]) and r["tipo"] == "prohibida")):
            mejor = r
    return mejor


def _prefijo_literal(patron):
    p = patron.replace("\\", "/")
    cortes = [i for i in (p.find(c) for c in "*?[{") if i != -1]
    if not cortes:
        return p
    cabeza = p[:min(cortes)]
    if "/" not in cabeza:
        return ""
    pref = cabeza.rsplit("/", 1)[0]
    if re.fullmatch(r"[A-Za-z]:", pref):
        pref += "/"
    return pref or "/"


def _es_absoluta(ruta):
    r = ruta.replace("\\", "/")
    return bool(_DRIVE.match(ruta) or r.startswith("/"))


def alcances_de_busqueda(tool, entrada, cwd):
    ruta = entrada.get("path")
    if tool == "Glob" and isinstance(entrada.get("pattern"), str):
        patron = entrada["pattern"]
        pref = _prefijo_literal(patron)
        if _es_absoluta(patron):
            return [normalizar_ruta(pref or "/", cwd)]
        base = ruta if ruta else cwd
        return [normalizar_ruta("%s/%s" % (str(base).replace("\\", "/").rstrip("/"), pref) if pref else base, cwd)]
    return [normalizar_ruta(ruta if ruta else cwd, cwd)]


def _resumen_entrada(entrada):
    claves = ("file_path", "path", "pattern", "glob", "type")
    return {k: entrada[k] for k in claves if k in entrada}


def clasificar(indice, tool, entrada, reglas, cwd, ceguera_fisica):
    base = {"indice": indice, "tool": tool, "entrada": _resumen_entrada(entrada)}
    if tool == "Read":
        ruta = entrada.get("file_path") or entrada.get("path")
        if not ruta:
            return None
        n = normalizar_ruta(ruta, cwd)
        r = regla_que_cubre(n, reglas)
        if r and r["tipo"] == "prohibida":
            base.update({"tipo": "lectura_prohibida", "nivel": "contaminado", "alcance": ruta,
                         "reglas": [r["original"]],
                         "motivo": "Read de un archivo bajo una ruta prohibida"})
            return base
        return None
    if tool not in ("Grep", "Glob"):
        return None
    pegadas = {}
    for alcance in alcances_de_busqueda(tool, entrada, cwd):
        for r in reglas:
            if r["tipo"] != "prohibida":
                continue
            if es_bajo(r["ruta"], alcance):
                pegadas[r["original"]] = r
            elif es_bajo(alcance, r["ruta"]):
                cubre = regla_que_cubre(alcance, reglas)
                if cubre is not None and cubre["tipo"] == "prohibida":
                    pegadas[r["original"]] = r
    if not pegadas:
        return None
    todas_fisicas = ceguera_fisica and all(r["fisica"] for r in pegadas.values())
    base.update({"tipo": "busqueda_alcance_prohibido",
                 "revela": "nombres" if tool == "Glob" else "contenido",
                 "nivel": "info" if todas_fisicas else "exposicion",
                 "alcance": entrada.get("path") or "(cwd %s)" % cwd,
                 "reglas": sorted(pegadas),
                 "motivo": "el alcance de la busqueda contiene o esta dentro de una ruta prohibida"
                           + (" (no estaba en disco: ceguera fisica)" if todas_fisicas else "")})
    return base


def auditar(lecturas, reglas, cwd, ceguera_fisica=False):
    hallazgos = []
    for i, lec in enumerate(lecturas):
        h = clasificar(i, lec.get("tool"), lec.get("input") or {}, reglas, cwd, ceguera_fisica)
        if h:
            hallazgos.append(h)
    niveles = [h["nivel"] for h in hallazgos]
    if "contaminado" in niveles:
        estado = "contaminado"
    elif "exposicion" in niveles:
        estado = "exposicion"
    else:
        estado = "limpio"
    return {"total": len(lecturas), "estado": estado, "hallazgos": hallazgos}


def leer_lecturas(ruta):
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".jsonl":
        leidos = leer(ruta)
        if leidos is None:
            raise OSError("no se pudo leer %s" % ruta)
        registros, salteadas = leidos
        lecturas, no_auditadas = [], {}
        for obj in registros:
            if obj.get("type") != "assistant":
                continue
            for b in bloques(obj):
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                if b.get("name") in LECTURA:
                    lecturas.append({"tool": b["name"], "input": b.get("input", {})})
                elif b.get("name") != HANDBACK:
                    no_auditadas[b.get("name")] = no_auditadas.get(b.get("name"), 0) + 1
        agente = ruta.stem[len("agent-"):] if ruta.stem.startswith("agent-") else ruta.stem
        return {"agente": agente, "meta": {}, "lecturas": lecturas, "no_auditadas": no_auditadas, "salteadas": salteadas}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, dict) or "lecturas" not in datos:
        raise ValueError("%s no tiene la clave 'lecturas'" % ruta)
    return {"agente": datos.get("agente"), "meta": datos.get("meta", {}),
            "lecturas": datos["lecturas"], "no_auditadas": datos.get("no_auditadas", {}), "salteadas": 0}


def rutas_de_manifest(manifest, scratch):
    datos = json.loads(Path(manifest).read_text(encoding="utf-8"))
    prohibidas = list(datos.get("prohibidas", []))
    permitidas = []
    for p in datos.get("permitidas", []):
        if "{scratch}" in p:
            if scratch:
                permitidas.append(p.replace("{scratch}", str(scratch)))
        else:
            permitidas.append(p)
    return prohibidas, permitidas


def rutas_ocultas(scratch):
    s = str(scratch).rstrip("\\/")
    rutas = [s + "." + convencion.CARPETA_OCULTA, s + "\\" + convencion.CARPETA_OCULTA]
    try:
        datos = json.loads((Path(s) / "movidos.json").read_text(encoding="utf-8"))
        if datos.get("oculto_raiz"):
            rutas = [datos["oculto_raiz"]]
    except (OSError, ValueError):
        pass
    return rutas


def _imprimir(informe, ver):
    print("auditar_lecturas: %d archivo(s); %d regla(s) prohibida(s), %d permitida(s); ceguera fisica: %s"
          % (len(informe["archivos"]), len(informe["reglas"]["prohibidas"]),
             len(informe["reglas"]["permitidas"]), "si" if informe["ceguera_fisica"] else "no"))
    marca = {"contaminado": "CONTAMINADO", "exposicion": "EXPOSICION", "limpio": "LIMPIO"}
    for a in informe["archivos"]:
        print("\n[%s] %s  (agente %s, %d lecturas auditadas)" % (
            marca[a["estado"]], a["fuente"], a["agente"], a["total"]))
        if a["no_auditadas"]:
            print("   aviso: herramientas NO auditadas: %s" % ", ".join(
                "%s x%d" % kv for kv in sorted(a["no_auditadas"].items())))
        for h in a["hallazgos"]:
            if h["nivel"] == "info" and not ver:
                continue
            e = h["entrada"]
            donde = e.get("file_path") or e.get("path") or e.get("pattern") or "(cwd)"
            extra = "  glob=%s" % e["glob"] if "glob" in e else ""
            revela = "  [revela %s]" % h["revela"] if h.get("revela") else ""
            print("   #%d %-6s %-11s %s%s%s" % (h["indice"], h["tool"], h["nivel"].upper(), donde, extra, revela))
            print("        regla: %s" % "; ".join(h["reglas"]))
        ocultos = sum(1 for h in a["hallazgos"] if h["nivel"] == "info")
        if ocultos and not ver:
            print("   (%d hallazgo(s) en INFO por ceguera fisica; --v los lista)" % ocultos)
    r = informe["resumen"]
    print("\nRESUMEN: %d limpio(s), %d con exposicion posible, %d contaminado(s)"
          % (r["limpio"], r["exposicion"], r["contaminado"]))
    print("Recordatorio: EXPOSICION es «pudo ver», no «vio» -- se resuelve leyendo el reporte (¿cito algo")
    print("de esa ruta?). CONTAMINADO descarta la corrida de la medicion salvo prueba en contrario.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audita las lecturas (Read/Grep/Glob) de corridas a ciegas contra las rutas prohibidas.")
    parser.add_argument("archivos", nargs="+", help="*.lecturas.json o agent-<id>.jsonl")
    parser.add_argument("--manifest", help="manifest.json del caso (prohibidas / permitidas)")
    parser.add_argument("--scratch", help="carpeta scratch de la corrida: sustituye {scratch} en permitidas")
    parser.add_argument("--prohibida", action="append", default=[], metavar="RUTA")
    parser.add_argument("--permitida", action="append", default=[], metavar="RUTA")
    parser.add_argument("--ceguera-fisica", action="store_true",
                        help="las carpetas de la verdad de terreno estaban fuera del disco: sus exposiciones bajan a info")
    parser.add_argument("--cwd", help="cwd de las busquedas sin path (por defecto, la raiz de la instancia)")
    parser.add_argument("--json", action="store_true", help="imprime el informe JSON en lugar del resumen")
    parser.add_argument("--salida", help="escribe ademas el informe JSON en este archivo")
    parser.add_argument("--v", action="store_true", help="lista tambien los hallazgos en INFO")
    args = parser.parse_args(argv)

    cwd = args.cwd
    if not cwd:
        raiz = raiz_de_instancia(os.environ, os.getcwd())
        if raiz is None:
            print("auditar_lecturas: no hay %s en la carpeta de la sesion ni en sus padres (pasa --cwd)" % config_loader.NOMBRE)
            return 2
        cwd = str(raiz)

    prohibidas, permitidas = [], []
    if args.manifest:
        try:
            prohibidas, permitidas = rutas_de_manifest(args.manifest, args.scratch)
        except (OSError, ValueError) as exc:
            print("auditar_lecturas: no pude leer el manifest (%s)" % exc)
            return 2
    if args.scratch:
        prohibidas += rutas_ocultas(args.scratch)
    prohibidas += args.prohibida
    permitidas += args.permitida
    if not prohibidas:
        print("auditar_lecturas: no hay rutas prohibidas (usa --manifest o --prohibida)")
        return 2
    reglas = armar_reglas(prohibidas, permitidas, cwd)

    archivos = []
    for fuente in args.archivos:
        try:
            datos = leer_lecturas(fuente)
        except (OSError, ValueError) as exc:
            print("auditar_lecturas: no pude leer %s (%s)" % (fuente, exc))
            return 2
        if datos["salteadas"]:
            print("aviso %s: %d linea(s) no se pudieron leer y se saltearon" % (fuente, datos["salteadas"]), file=sys.stderr)
        informe = auditar(datos["lecturas"], reglas, cwd, args.ceguera_fisica)
        informe.update({"fuente": str(fuente), "agente": datos["agente"], "no_auditadas": datos["no_auditadas"]})
        archivos.append(informe)

    conteo = {"limpio": 0, "exposicion": 0, "contaminado": 0}
    for a in archivos:
        conteo[a["estado"]] += 1
    informe_total = {"ceguera_fisica": args.ceguera_fisica, "cwd": cwd,
                     "reglas": {"prohibidas": prohibidas, "permitidas": permitidas},
                     "archivos": archivos, "resumen": conteo}
    if args.salida:
        Path(args.salida).write_text(json.dumps(informe_total, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    if args.json:
        print(json.dumps(informe_total, ensure_ascii=False, indent=1))
    else:
        _imprimir(informe_total, args.v)
    return 1 if (conteo["exposicion"] or conteo["contaminado"]) else 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("auditar_lecturas: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
