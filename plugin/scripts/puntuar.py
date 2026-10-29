import argparse
import copy
import datetime
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

ESCALA = ("ok", "parcial", "reves", "elogio", "derivado", "contaminado", "-")
CONTRA = ("reves", "elogio")
SIN_TOQUE = ("-",)
NOMBRE_MARCA = "[corrida]"
_ID_CELDA = re.compile(r"^[0-9a-f]{4}$")

DESCRIPCION = """Puntaje por celda (corrida x observacion), brazos y ratificacion a ciegas.

Escala de los veredictos:
  ok           acierto: mismo problema y misma direccion que la verdad de terreno
  parcial      mismo objeto, otra solucion o cobertura incompleta
  reves        toca el tema y recomienda lo contrario  (contra)
  elogio       marca como correcto lo que la verdad de terreno objeto  (contra)
  derivado     lo anota para otro reviewer, sin direccion  (no cuenta)
  contaminado  el reviewer vio la verdad de terreno  (no cuenta)
  -            no lo toca

puntaje de una corrida = ok + 0,5 x parcial. Salidas: 0 = ok, 1 = ratificacion con filas pendientes, 2 = error."""


class RatificacionIncompleta(Exception):
    def __init__(self, pendientes):
        super().__init__("%d fila(s) sin responder" % len(pendientes))
        self.pendientes = pendientes


class RatificacionInvalida(Exception):
    pass


def fmt_num(x):
    if abs(x * 10 - round(x * 10)) < 1e-9:
        return ("%.1f" % x).replace(".", ",")
    return ("%.2f" % x).rstrip("0").replace(".", ",")


def _clave_natural(obs):
    m = re.match(r"^(\D*)(\d+)(.*)$", obs)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (obs, 0, "")


def conteo_corrida(celdas):
    ok = sum(1 for v in celdas.values() if v == "ok")
    parcial = sum(1 for v in celdas.values() if v == "parcial")
    contra = sum(1 for v in celdas.values() if v in CONTRA)
    return {"ok": ok, "parcial": parcial, "contra": contra,
            "derivado": sum(1 for v in celdas.values() if v == "derivado"),
            "contaminado": sum(1 for v in celdas.values() if v == "contaminado"),
            "puntaje": ok + 0.5 * parcial}


def veredicto_union(veredictos):
    vs = list(veredictos)
    if "ok" in vs:
        return "ok"
    if "parcial" in vs:
        return "parcial"
    if any(v in CONTRA for v in vs):
        return "contra"
    if "derivado" in vs:
        return "derivado"
    if "contaminado" in vs:
        return "contaminado"
    return "-"


def cargar_puntajes(ruta):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if not isinstance(datos, dict) or not isinstance(datos.get("corridas"), dict):
        raise ValueError("%s no tiene el objeto 'corridas'" % ruta)
    for corrida, celdas in datos["corridas"].items():
        for obs, v in celdas.items():
            if v not in ESCALA:
                raise ValueError("%s: veredicto %r fuera de la escala en %s/%s" % (ruta, v, corrida, obs))
    return datos


def excluir_disputadas(datos):
    nuevo = copy.deepcopy(datos)
    disputadas = set((nuevo.get("disputadas") or {}).keys())
    excluidas = {}
    if disputadas:
        for corrida, celdas in nuevo["corridas"].items():
            for obs in [o for o in celdas if o in disputadas]:
                excluidas.setdefault(corrida, {})[obs] = celdas.pop(obs)
        nuevo["observaciones"] = [o for o in nuevo.get("observaciones", []) if o not in disputadas]
    nuevo["_excluidas"] = excluidas
    return nuevo


def _observaciones(datos, corridas=None):
    vistas = list(datos.get("observaciones", []))
    for c in (corridas if corridas is not None else datos["corridas"]):
        for obs in datos["corridas"][c]:
            if obs not in vistas:
                vistas.append(obs)
    return sorted(vistas, key=_clave_natural)


def analizar_brazo(datos, nombre, corridas):
    faltan = [c for c in corridas if c not in datos["corridas"]]
    if faltan:
        raise KeyError("corridas inexistentes en el puntaje: %s" % ", ".join(faltan))
    celdas = {c: datos["corridas"][c] for c in corridas}
    detalle = []
    for c in corridas:
        d = conteo_corrida(celdas[c])
        d["corrida"] = c
        detalle.append(d)
    media = sum(d["puntaje"] for d in detalle) / len(detalle) if detalle else 0.0
    observaciones = _observaciones(datos, corridas)

    por_obs = {}
    for obs in observaciones:
        por_obs[obs] = veredicto_union(celdas[c].get(obs, "-") for c in corridas)
    conteo_union = conteo_corrida({o: ("reves" if v == "contra" else v) for o, v in por_obs.items()})

    k_n = {obs: (sum(1 for c in corridas if celdas[c].get(obs) == "ok"), len(corridas)) for obs in observaciones}
    estables = ([obs for obs in observaciones if all(celdas[c].get(obs) == "ok" for c in corridas)]
                if len(corridas) >= 2 else [])
    conflictos = []
    for obs in observaciones:
        vs = {c: celdas[c].get(obs, "-") for c in corridas}
        if any(v in ("ok", "parcial") for v in vs.values()) and any(v in CONTRA for v in vs.values()):
            conflictos.append({"obs": obs, "detalle": vs})
    return {"nombre": nombre, "corridas": detalle, "media": media,
            "union": {"por_obs": por_obs, "conteo": conteo_union},
            "estables": estables, "conflictos": conflictos, "k_n": k_n,
            "veredictos": {obs: {c: celdas[c].get(obs, "-") for c in corridas} for obs in observaciones}}


def tabla_pareada(observaciones, brazos):
    filas = []
    for obs in observaciones:
        filas.append({"obs": obs, "brazos": [
            {"k_n": b["k_n"].get(obs, (0, len(b["corridas"]))), "union": b["union"]["por_obs"].get(obs, "-")}
            for b in brazos]})
    return filas


def _md(encabezados, filas):
    out = ["| " + " | ".join(encabezados) + " |", "|" + "|".join("---" for _ in encabezados) + "|"]
    for f in filas:
        out.append("| " + " | ".join(str(x) for x in f) + " |")
    return "\n".join(out)


def render_reporte(datos, brazos):
    out = ["# Puntaje: %s" % datos.get("fixture", "(sin nombre)"), ""]
    if datos.get("ratificado_por"):
        out.append("Ratificado por: %s" % datos["ratificado_por"])
    else:
        out.append("Ratificado por: nadie todavía (puntaje del orquestador, sin ratificar)")
    if datos.get("disputadas"):
        out.append("")
        out.append("Fuera del puntaje (verdad de terreno disputada con evidencia): %s"
                   % ", ".join(sorted(datos["disputadas"], key=_clave_natural)))
    out += ["", "## Corridas", ""]
    filas = []
    for c in datos["corridas"]:
        d = conteo_corrida(datos["corridas"][c])
        filas.append([c, d["ok"], d["parcial"], d["contra"], fmt_num(d["puntaje"]), d["derivado"], d["contaminado"]])
    out.append(_md(["Corrida", "ok", "parcial", "contra", "puntaje", "derivado", "contaminado"], filas))
    out += ["", "puntaje = ok + 0,5 x parcial; contra = reves + elogio; derivado y contaminado no cuentan.", ""]

    if not brazos:
        return "\n".join(out) + "\n"

    out += ["## Brazos", ""]
    filas = []
    for b in brazos:
        cu = b["union"]["conteo"]
        filas.append([b["nombre"], len(b["corridas"]), fmt_num(b["media"]),
                      "%d ok, %d parcial, %d contra" % (cu["ok"], cu["parcial"], cu["contra"]),
                      fmt_num(cu["puntaje"]), ", ".join(b["estables"]) or "—",
                      ", ".join(x["obs"] for x in b["conflictos"]) or "—"])
    out.append(_md(["Brazo", "Corridas", "Media", "Unión", "Puntaje unión", "Estables", "Conflictos"], filas))
    out.append("")

    for b in brazos:
        n = len(b["corridas"])
        out += ["### Brazo %s (%d corrida%s)" % (b["nombre"], n, "" if n == 1 else "s"), ""]
        filas = [[d["corrida"], d["ok"], d["parcial"], d["contra"], fmt_num(d["puntaje"])] for d in b["corridas"]]
        cu = b["union"]["conteo"]
        filas.append(["**Unión**", cu["ok"], cu["parcial"], cu["contra"], fmt_num(cu["puntaje"])])
        out.append(_md(["Corrida", "ok", "parcial", "contra", "puntaje"], filas))
        out += ["", "- Media por corrida: %s" % fmt_num(b["media"])]
        if n >= 2:
            out.append("- Estables (ok en %d/%d): %s" % (n, n, ", ".join(b["estables"]) or "ninguna"))
        else:
            out.append("- Estables: no aplica con una sola corrida")
        if b["conflictos"]:
            out.append("- Conflictos (una corrida acierta y otra va en contra; decide el líder o se revisa a mano):")
            for x in b["conflictos"]:
                out.append("  - %s: %s" % (x["obs"], " / ".join("%s %s" % (c, v) for c, v in x["detalle"].items())))
        else:
            out.append("- Conflictos: ninguno")
        tocadas = [o for o, vs in b["veredictos"].items() if any(v != "-" for v in vs.values())]
        filas = []
        for obs in tocadas:
            k, nn = b["k_n"][obs]
            filas.append([obs, "%d/%d" % (k, nn), b["union"]["por_obs"][obs],
                          " / ".join(b["veredictos"][obs].values())])
        out += ["", "k/N de ok por observación (solo las que alguna corrida tocó):", ""]
        out.append(_md(["Obs", "ok k/N", "Unión", "Veredicto por corrida (en el orden de la tabla)"], filas))
        out.append("")

    if len(brazos) >= 2:
        out += ["## Tabla pareada por observación", ""]
        enc = ["Obs"]
        for b in brazos:
            enc += ["%s ok k/N" % b["nombre"], "%s unión" % b["nombre"]]
        filas = []
        for f in tabla_pareada(_observaciones(datos), brazos):
            fila = [f["obs"]]
            for celda in f["brazos"]:
                fila += ["%d/%d" % celda["k_n"], "—" if celda["union"] == "-" else celda["union"]]
            filas.append(fila)
        out.append(_md(enc, filas))
        out += ["", "Solo cuenta como mejora un acierto que cita el mecanismo nuevo; la tabla atribuye, no concluye.", ""]
    return "\n".join(out) + "\n"


def _escapar(texto):
    return str(texto).replace("\n", " ").replace("\r", " ").replace("|", "\\|").strip()


def _scrub_corridas(texto, nombres):
    for n in sorted(nombres, key=len, reverse=True):
        texto = texto.replace(n, NOMBRE_MARCA)
    return texto


def generar_plantilla(datos, semilla=None, ruta_puntajes=None):
    rng = random.Random(semilla) if semilla is not None else random.SystemRandom()
    nombres = list(datos["corridas"])
    citas = datos.get("citas", {})
    desc = datos.get("descripciones", {})
    celdas = []
    for corrida in nombres:
        for obs in sorted(datos["corridas"][corrida], key=_clave_natural):
            v = datos["corridas"][corrida][obs]
            if v in SIN_TOQUE or v == "derivado":
                continue
            celdas.append((corrida, obs, v))
    rng.shuffle(celdas)
    usados = set()
    filas, clave_celdas = [], {}
    for corrida, obs, v in celdas:
        while True:
            cid = "%04x" % rng.randrange(0x10000)
            if cid not in usados:
                usados.add(cid)
                break
        cita = _scrub_corridas(str(citas.get(corrida, {}).get(obs, "")), nombres)
        obs_txt = obs + (" — " + desc[obs] if obs in desc else "")
        filas.append("| %s | %s | %s | %s |  |" % (cid, _escapar(obs_txt), v, _escapar(cita)))
        clave_celdas[cid] = {"corrida": corrida, "obs": obs, "veredicto": v}
    escala = datos.get("escala")
    out = ["# Ratificación a ciegas: %s" % datos.get("fixture", ""), ""]
    out.append("Para cada fila responde en la última columna: `sí` si confirmas el veredicto propuesto, "
               "o `no → <veredicto>` si lo corriges (ok, parcial, reves, elogio, derivado, contaminado o -).")
    out.append("Las filas están mezcladas y no dicen qué corrida ni qué versión las produjo.")
    out.append("")
    if isinstance(escala, dict):
        for k, v in escala.items():
            out.append("- **%s**: %s" % (k, v))
        out.append("")
    out.append("| ID | Observación | Veredicto propuesto | Cita del reporte | Ratificado: sí / no → <veredicto> |")
    out.append("|---|---|---|---|---|")
    out += filas
    clave = {"fixture": datos.get("fixture"), "puntajes": str(ruta_puntajes) if ruta_puntajes else None,
             "celdas": clave_celdas}
    return "\n".join(out) + "\n", clave


def _celdas_de_fila(linea):
    partes = re.split(r"(?<!\\)\|", linea.strip())
    if partes and partes[0] == "":
        partes = partes[1:]
    if partes and partes[-1].strip() == "":
        partes = partes[:-1]
    return [p.strip().replace("\\|", "|") for p in partes]


def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_CONFIRMA = {"si", "s", "yes", "y", "confirmo", "confirmado"}
_CAMBIA = re.compile(r"^no\s*(?:→|->|=>|:|,)?\s*([a-z\-]+)$")


def interpretar_respuesta(texto):
    t = _sin_acentos(texto.strip().lower()).replace("*", "").replace("`", "").strip()
    if not t or "<veredicto>" in t or t in ("?", "…", "..."):
        return "pendiente", None
    if t in _CONFIRMA:
        return "confirma", None
    m = _CAMBIA.match(t)
    if m and m.group(1) in ESCALA:
        return "cambia", m.group(1)
    raise RatificacionInvalida("respuesta no reconocida: %r (usa «sí» o «no → <veredicto>» con veredicto de %s)"
                               % (texto, ", ".join(ESCALA)))


def aplicar_ratificacion(tabla_md, clave, datos, ratificado_por, fecha, permitir_pendientes=False):
    if not isinstance(ratificado_por, str) or not ratificado_por.strip():
        raise RatificacionInvalida("falta quien ratifica: --ratificado-por es obligatorio al aplicar la ratificación")
    respuestas = {}
    for linea in tabla_md.splitlines():
        if not linea.lstrip().startswith("|"):
            continue
        celdas = _celdas_de_fila(linea)
        if len(celdas) < 2 or not _ID_CELDA.match(celdas[0]):
            continue
        if celdas[0] not in clave["celdas"]:
            raise RatificacionInvalida("ID %s no esta en la clave (¿tabla de otra ronda?)" % celdas[0])
        respuestas[celdas[0]] = celdas[-1]
    nuevo = copy.deepcopy(datos)
    cambios, pendientes = [], []
    for cid, info in clave["celdas"].items():
        tipo, valor = interpretar_respuesta(respuestas.get(cid, ""))
        if tipo == "pendiente":
            pendientes.append(cid)
        elif tipo == "cambia" and valor != info["veredicto"]:
            actual = nuevo["corridas"][info["corrida"]].get(info["obs"])
            nuevo["corridas"][info["corrida"]][info["obs"]] = valor
            cambios.append({"corrida": info["corrida"], "obs": info["obs"], "de": actual, "a": valor})
    if pendientes and not permitir_pendientes:
        raise RatificacionIncompleta(pendientes)
    sello = "%s %s" % (ratificado_por.strip(), fecha)
    nuevo["ratificado_por"] = sello + (" (parcial: %d fila(s) sin responder)" % len(pendientes) if pendientes else "")
    nuevo["ratificacion"] = {"por": ratificado_por.strip(), "fecha": fecha, "filas": len(clave["celdas"]),
                             "pendientes": len(pendientes), "cambios": cambios}
    return nuevo, cambios, pendientes


def serializar_puntajes(datos):
    claves = list(datos)
    lineas = ["{"]
    for i, k in enumerate(claves):
        v = datos[k]
        coma = "," if i < len(claves) - 1 else ""
        if k == "corridas":
            lineas.append('  "corridas": {')
            items = list(v.items())
            for j, (c, celdas) in enumerate(items):
                lineas.append("    %s: %s%s" % (json.dumps(c, ensure_ascii=False), json.dumps(celdas, ensure_ascii=False),
                                               "," if j < len(items) - 1 else ""))
            lineas.append("  }" + coma)
        elif isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v):
            lineas.append("  %s: %s%s" % (json.dumps(k, ensure_ascii=False), json.dumps(v, ensure_ascii=False), coma))
        else:
            cuerpo = json.dumps(v, ensure_ascii=False, indent=2).replace("\n", "\n  ")
            lineas.append("  %s: %s%s" % (json.dumps(k, ensure_ascii=False), cuerpo, coma))
    lineas.append("}")
    return "\n".join(lineas) + "\n"


def _parsear_brazo(texto):
    if "=" not in texto:
        raise ValueError("--brazo espera nombre=corrida,corrida, recibio %r" % texto)
    nombre, resto = texto.split("=", 1)
    corridas = [c.strip() for c in resto.split(",") if c.strip()]
    if not nombre.strip() or not corridas:
        raise ValueError("--brazo espera nombre=corrida,corrida, recibio %r" % texto)
    return nombre.strip(), corridas


def _parser():
    parser = argparse.ArgumentParser(description=DESCRIPCION, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("puntajes", help="JSON de puntajes: corridas -> observacion -> veredicto")
    parser.add_argument("--brazo", action="append", default=[], metavar="NOMBRE=CORRIDA,CORRIDA")
    parser.add_argument("--plantilla-ratificacion", metavar="TABLA.md",
                        help="escribe la tabla a ratificar ('-' = stdout); exige --clave")
    parser.add_argument("--clave", metavar="CLAVE.json", help="con --plantilla-ratificacion: donde guardar la clave")
    parser.add_argument("--semilla", type=int, help="con --plantilla-ratificacion: IDs y orden reproducibles")
    parser.add_argument("--aplicar-ratificacion", nargs=2, metavar=("TABLA.md", "CLAVE.json"))
    parser.add_argument("--ratificado-por", metavar="NOMBRE", help="con --aplicar-ratificacion: quien ratifico (obligatorio)")
    parser.add_argument("--permitir-pendientes", action="store_true")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)

    try:
        crudo = cargar_puntajes(args.puntajes)
    except (OSError, ValueError) as exc:
        print("puntuar: no pude leer los puntajes (%s)" % exc)
        return 2
    datos = excluir_disputadas(crudo)

    if args.plantilla_ratificacion:
        if not args.clave:
            print("puntuar: --plantilla-ratificacion exige --clave")
            return 2
        tabla, clave = generar_plantilla(datos, args.semilla, args.puntajes)
        if args.plantilla_ratificacion == "-":
            print(tabla)
        else:
            Path(args.plantilla_ratificacion).write_text(tabla, encoding="utf-8", newline="\n")
        Path(args.clave).write_text(json.dumps(clave, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print("plantilla: %d fila(s) a ratificar; clave en %s (NO se la muestres a quien ratifica antes de que ratifique)"
              % (len(clave["celdas"]), args.clave))
        return 0

    if args.aplicar_ratificacion:
        tabla_ruta, clave_ruta = args.aplicar_ratificacion
        try:
            tabla = Path(tabla_ruta).read_text(encoding="utf-8")
            clave = json.loads(Path(clave_ruta).read_text(encoding="utf-8"))
            nuevo, cambios, pendientes = aplicar_ratificacion(
                tabla, clave, crudo, args.ratificado_por, datetime.date.today().isoformat(),
                permitir_pendientes=args.permitir_pendientes)
        except RatificacionIncompleta as exc:
            print("puntuar: faltan %d fila(s) por responder (IDs: %s); no se escribio nada. "
                  "Usa --permitir-pendientes para aplicar el resto." % (len(exc.pendientes), ", ".join(exc.pendientes)))
            return 1
        except (RatificacionInvalida, OSError, ValueError) as exc:
            print("puntuar: %s" % exc)
            return 2
        Path(args.puntajes).write_text(serializar_puntajes(nuevo), encoding="utf-8", newline="\n")
        print("ratificado: %d celda(s) revisadas, %d corregida(s), %d pendiente(s)" % (
            len(clave["celdas"]), len(cambios), len(pendientes)))
        for c in cambios:
            print("  %s / %s: %s -> %s" % (c["corrida"], c["obs"], c["de"], c["a"]))
        return 0

    try:
        brazos = []
        for texto in args.brazo:
            nombre, corridas = _parsear_brazo(texto)
            brazos.append(analizar_brazo(datos, nombre, corridas))
    except (ValueError, KeyError) as exc:
        print("puntuar: %s" % (exc.args[0] if exc.args else exc))
        return 2
    print(render_reporte(datos, brazos), end="")
    return 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("puntuar: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
