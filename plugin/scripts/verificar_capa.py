import sys

sys.dont_write_bytecode = True

import difflib
import json
import math
import os
import re
import subprocess
import time

import config_loader
from odd_ws import capas as convencion
from odd_ws.comun import SILENCIO, cargar_por_ruta, correr_hook, decodificar, entorno_git, lineas, raiz_de_instancia

PLAZO_POR_DEFECTO = 8
TIMEOUT_GIT = 5
TOPE_BYTES = 2000000
REMOTO_HEAD = "refs/remotes/origin/HEAD"
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

_LIMITE = None


def plazo_de(argv):
    try:
        valor = float(argv[argv.index("--plazo") + 1])
    except (ValueError, IndexError):
        return PLAZO_POR_DEFECTO
    return valor if math.isfinite(valor) and valor > 0 else PLAZO_POR_DEFECTO


def _restante(tope):
    if _LIMITE is None:
        return tope
    return min(tope, _LIMITE - time.monotonic())


def _git(cwd, *args):
    timeout = _restante(TIMEOUT_GIT)
    if timeout <= 0:
        raise subprocess.TimeoutExpired(["git", *args], 0)
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, timeout=timeout, env=entorno_git())


def _hunks_del_diff(salida):
    hunks, actual, n = [], None, 0
    for linea in salida.split("\n"):
        m = HUNK_RE.match(linea)
        if m:
            actual = {"agregadas": [], "quitadas": []}
            hunks.append(actual)
            n = int(m.group(1))
            continue
        if actual is None or not linea:
            continue
        marca, resto = linea[0], linea[1:].rstrip("\r")
        if marca == "+":
            actual["agregadas"].append((n, resto.lstrip("﻿") if n == 1 else resto))
            n += 1
        elif marca == "-":
            actual["quitadas"].append(resto.lstrip("﻿"))
    return hunks


def _hunks_contra(base, actual):
    a = [t for _, t in lineas(base)]
    b = [t for _, t in lineas(actual)]
    hunks = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            hunks.append({"agregadas": [(j + 1, b[j]) for j in range(j1, j2)], "quitadas": a[i1:i2]})
    return hunks


def _rama_por_defecto(repo):
    r = _git(repo, "symbolic-ref", "--quiet", "--short", REMOTO_HEAD)
    return r.stdout.decode("utf-8", errors="replace").strip() if r.returncode == 0 else None


def _contraparte(ruta, base, config):
    repo = config["repos"][base["repo"]]["path"]
    if not os.path.isdir(repo):
        return None
    rama = _rama_por_defecto(repo)
    if not rama:
        return None
    nombre = os.path.basename(ruta).lower()
    prefijo = (base.get("strip_prefix") or "").lower()
    if prefijo and nombre.startswith(prefijo):
        nombre = nombre[len(prefijo):]
    r = _git(repo, "ls-tree", "-r", "--name-only", rama, "--", *([base["under"]] if base.get("under") else []))
    if r.returncode != 0:
        return None
    candidatos = [l for l in r.stdout.decode("utf-8", errors="replace").splitlines()
                  if l.rsplit("/", 1)[-1].lower() == nombre]
    return (repo, rama, candidatos[0]) if len(candidatos) == 1 else None


def _contenido(contraparte):
    repo, rama, ruta = contraparte
    r = _git(repo, "show", "%s:%s" % (rama, ruta))
    return decodificar(r.stdout) if r.returncode == 0 else None


def armar_ctx(ruta, capa, origen, config):
    ruta = os.path.abspath(ruta)
    if not os.path.isfile(ruta) or os.path.getsize(ruta) > TOPE_BYTES:
        return None
    r = _git(os.path.dirname(ruta), "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        return None
    raiz = r.stdout.decode("utf-8", errors="replace").strip()
    rel_git = os.path.relpath(os.path.realpath(ruta), os.path.realpath(raiz)).replace("\\", "/")
    if rel_git.startswith(".."):
        return None
    with open(ruta, "rb") as f:
        crudo = f.read()
    texto = decodificar(crudo)
    taller = origen == "taller"
    base_cfg = config["layers"][capa].get("workshop_baseline") if taller else None
    contraparte = _contraparte(ruta, base_cfg, config) if base_cfg else None
    sin_trackear = _git(raiz, "ls-files", "--error-unmatch", "--", rel_git).returncode != 0
    es_nuevo = sin_trackear or _git(raiz, "cat-file", "-e", "HEAD:" + rel_git).returncode != 0
    base = _contenido(contraparte) if es_nuevo and contraparte else None
    if base is not None:
        es_nuevo = False
        hunks = _hunks_contra(base, texto)
        agregadas = [par for h in hunks for par in h["agregadas"]]
    elif es_nuevo:
        agregadas = lineas(texto)
        hunks = [{"agregadas": agregadas, "quitadas": []}] if agregadas else []
    else:
        d = _git(raiz, "diff", "-U0", "--no-color", "--no-ext-diff", "HEAD", "--", rel_git)
        if d.returncode != 0:
            return None
        hunks = _hunks_del_diff(d.stdout.decode("utf-8", errors="replace"))
        agregadas = [par for h in hunks for par in h["agregadas"]]
    if taller:
        relativa, relativa_repo = os.path.basename(ruta), (contraparte[2] if contraparte else None)
    else:
        relativa = relativa_repo = rel_git
    return {
        "ruta": ruta, "relativa": relativa, "relativa_repo": relativa_repo,
        "origen": "taller" if taller else "repo", "capa": capa,
        "bytes": crudo, "texto": texto, "es_nuevo": es_nuevo, "agregadas": agregadas, "hunks": hunks,
        "limite": _LIMITE,
    }


def filtrar_preexistentes(hallazgos, hunks):
    por_linea = {}
    for h in hunks:
        for n, _ in h["agregadas"]:
            por_linea[n] = h
    cupos, descartados = {}, set()
    orden = sorted(range(len(hallazgos)), key=lambda i: (hallazgos[i].get("linea") is None, hallazgos[i].get("linea") or 0))
    for i in orden:
        hallazgo = hallazgos[i]
        fragmento, linea = hallazgo.get("fragmento"), hallazgo.get("linea")
        hunk = por_linea.get(linea) if fragmento and linea is not None else None
        if hunk is None:
            continue
        clave = (id(hunk), hallazgo.get("id"), fragmento)
        if clave not in cupos:
            cupos[clave] = sum(1 for quitada in hunk["quitadas"] if fragmento in quitada)
        if cupos[clave] > 0:
            cupos[clave] -= 1
            descartados.add(i)
    return [h for i, h in enumerate(hallazgos) if i not in descartados]


def _formatear(h):
    severidad = h.get("severidad") or ""
    etiqueta = "[%s %s]" % (h["id"], severidad) if severidad else "[%s]" % h["id"]
    linea = h.get("linea")
    donde = "linea %d" % linea if linea is not None else "archivo"
    return "%s %s: %s" % (etiqueta, donde, h["mensaje"])


def _salida(relativa, hallazgos):
    bloqueos = [h for h in hallazgos if h["modo"] == "bloqueo"]
    avisos = [h for h in hallazgos if h["modo"] != "bloqueo"]
    if bloqueos:
        encabezado = "verificar-capa: %s tiene %d problema(s): corregir y reintentar." % (relativa, len(hallazgos))
    else:
        encabezado = ("verificar-capa (aviso): %s tiene %d aviso(s); el cambio ya quedó escrito: "
                      "corregirlo si es propio (no hace falta reintentar)." % (relativa, len(hallazgos)))
    texto = "\n".join([encabezado] + [_formatear(h) for h in bloqueos + avisos])
    if bloqueos:
        return 2, "", (texto + "\n").encode("utf-8")
    contexto = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": texto}}
    return 0, json.dumps(contexto), b""


def verificar_archivo(ruta, config):
    info = config_loader.clasificar(ruta, config)
    if info is None:
        return None
    capa, origen = info
    archivo_modulo = os.path.join(config["raiz"], convencion.chequeo(capa))
    if not os.path.isfile(archivo_modulo):
        return None
    ctx = armar_ctx(ruta, capa, origen, config)
    if ctx is None:
        return None
    modulo = cargar_por_ruta(archivo_modulo, "verificar_capa_modulo_%s" % capa)
    encontrados = modulo.verificar(ctx)
    hallazgos = [h for h in encontrados if isinstance(h, dict) and h.get("id") and h.get("mensaje")]
    if len(hallazgos) != len(encontrados):
        return None
    return ctx["relativa"], filtrar_preexistentes(hallazgos, ctx["hunks"])


def _post_tool_use(evento, config):
    if evento.get("tool_name") not in ("Edit", "Write"):
        return SILENCIO
    ruta = (evento.get("tool_input") or {}).get("file_path")
    if not isinstance(ruta, str) or not ruta:
        return SILENCIO
    resultado = verificar_archivo(ruta, config)
    if resultado is None or not resultado[1]:
        return SILENCIO
    return _salida(*resultado)


MANEJADORES = {
    "PostToolUse": _post_tool_use,
}


def correr(evento, raiz=None, plazo=PLAZO_POR_DEFECTO):
    global _LIMITE
    try:
        if isinstance(evento, (str, bytes, bytearray)):
            evento = json.loads(evento)
        if not isinstance(evento, dict):
            return SILENCIO
        manejador = MANEJADORES.get(evento.get("hook_event_name"))
        if manejador is None:
            return SILENCIO
        _LIMITE = time.monotonic() + plazo
        if raiz is None:
            raiz = raiz_de_instancia(os.environ, evento.get("cwd") or os.getcwd())
        if raiz is None:
            return SILENCIO
        estado = config_loader.estado(raiz)
        if estado.tipo != "ok":
            return SILENCIO
        return manejador(evento, estado.config)
    except (Exception, SystemExit):
        return SILENCIO
    finally:
        _LIMITE = None


def main():
    plazo = plazo_de(sys.argv[1:])
    return correr_hook(lambda crudo: correr(crudo, plazo=plazo))


if __name__ == "__main__":
    sys.exit(main())
