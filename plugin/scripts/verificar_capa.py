import sys

sys.dont_write_bytecode = True

import difflib
import json
import os
import re
import shutil
import subprocess
import time

import config_loader
from odd_ws import capas as convencion
from odd_ws.comun import (PLAZO_POR_DEFECTO, SILENCIO, cargar_por_ruta, correr_hook, decodificar, entorno_git, id_valido, lineas,
                          plazo_de, raiz_de_instancia)

TIMEOUT_GIT = 5
TOPE_BYTES = 2000000
DIAS_PODA = 7
REMOTO_HEAD = "refs/remotes/origin/HEAD"
ORIGENES_DEL_AVISO = ("startup", "resume")
TOPE_DEL_MOTIVO = 200
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

_LIMITE = None


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


def es_hallazgo(h):
    return isinstance(h, dict) and bool(h.get("id")) and bool(h.get("mensaje"))


def verificar_archivo(ruta, config, limite=None):
    global _LIMITE
    previo = _LIMITE
    _LIMITE = limite
    try:
        return _verificar_archivo(ruta, config)
    finally:
        _LIMITE = previo


def _verificar_archivo(ruta, config):
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
    hallazgos = [h for h in encontrados if es_hallazgo(h)]
    if len(hallazgos) != len(encontrados):
        return None
    return ctx["relativa"], filtrar_preexistentes(hallazgos, ctx["hunks"])


def _post_tool_use(evento, config):
    if evento.get("tool_name") not in ("Edit", "Write"):
        return SILENCIO
    ruta = (evento.get("tool_input") or {}).get("file_path")
    if not isinstance(ruta, str) or not ruta:
        return SILENCIO
    resultado = verificar_archivo(ruta, config, _LIMITE)
    if resultado is None or not resultado[1]:
        return SILENCIO
    return _salida(*resultado)


def no_negociables(capa, raiz):
    ruta = os.path.join(raiz, convencion.skill(capa))
    if not os.path.isfile(ruta):
        return None
    with open(ruta, encoding="utf-8-sig") as f:
        dentro, _, estado = convencion.partir_bloque(f.read().splitlines())
    texto = "\n".join(dentro).strip()
    return texto if estado == "ok" and texto else None


def _clave(evento):
    sesion = evento.get("session_id")
    agente = evento.get("agent_id") or "principal"
    if not (id_valido(sesion) and id_valido(agente)):
        return None
    return sesion, agente


def _marcas_dir(raiz):
    return os.path.join(raiz, convencion.PRIMER_TOQUE)


def _podar(base, actual):
    limite = time.time() - DIAS_PODA * 86400
    try:
        for nombre in os.listdir(base):
            ruta = os.path.join(base, nombre)
            if nombre != actual and os.path.isdir(ruta) and os.path.getmtime(ruta) < limite:
                shutil.rmtree(ruta, ignore_errors=True)
    except OSError:
        pass


def _marcar(raiz, sesion, agente, capa):
    base = _marcas_dir(raiz)
    carpeta = os.path.join(base, sesion)
    try:
        if not os.path.isdir(carpeta):
            os.makedirs(carpeta, exist_ok=True)
            _podar(base, sesion)
        with open(os.path.join(carpeta, "%s.%s" % (agente, capa)), "x"):
            pass
        return True
    except OSError:
        return False


def skills_del_frontmatter(texto):
    lineas_ = texto.lstrip("﻿").splitlines()
    if not lineas_ or lineas_[0].strip() != "---":
        return None
    try:
        fin = next(i for i in range(1, len(lineas_)) if lineas_[i].strip() == "---")
    except StopIteration:
        return None
    skills, en_skills = [], False
    for linea in lineas_[1:fin]:
        linea = re.sub(r"(^|\s)#.*$", "", linea)
        if re.match(r"skills\s*:", linea):
            resto = linea.split(":", 1)[1].strip()
            en_skills = not resto
            if resto.startswith("[") and resto.endswith("]"):
                skills += [x.strip().strip("'\"") for x in resto[1:-1].split(",") if x.strip()]
            continue
        if en_skills:
            m = re.match(r"\s*-\s+(\S+)\s*$", linea)
            if m:
                skills.append(m.group(1).strip("'\""))
            elif linea.strip() and not linea.startswith((" ", "\t")):
                en_skills = False
    return skills


def _precarga(evento, capa, raiz):
    tipo = evento.get("agent_type")
    if not id_valido(tipo):
        return False
    try:
        with open(os.path.join(raiz, convencion.agente(tipo)), encoding="utf-8-sig") as f:
            skills = skills_del_frontmatter(f.read())
    except (OSError, ValueError):
        return False
    return bool(skills) and "capa-%s" % capa in skills


def _tocar(evento, config):
    ruta = (evento.get("tool_input") or {}).get("file_path")
    if not isinstance(ruta, str) or not ruta:
        return None
    info = config_loader.clasificar(ruta, config)
    clave = _clave(evento) if info else None
    if clave is None:
        return None
    capa, raiz = info[0], config["raiz"]
    sesion, agente = clave
    if _precarga(evento, capa, raiz):
        return None
    if os.path.exists(os.path.join(_marcas_dir(raiz), sesion, "%s.%s" % (agente, capa))):
        return None
    bloque = no_negociables(capa, raiz)
    if bloque is None or not _marcar(raiz, sesion, agente, capa):
        return None
    return capa, bloque


def _texto_primer_toque(capa, raiz, encabezado, bloque):
    partes = [encabezado, bloque]
    if os.path.isfile(os.path.join(raiz, convencion.writer(capa))):
        partes.append("Para más que un ajuste mínimo, delegar en `writer-%s`." % capa)
    return "\n".join(partes)


def _primer_read(evento, config):
    toque = _tocar(evento, config)
    if toque is None:
        return SILENCIO
    capa, bloque = toque
    encabezado = ("primer toque (capa-%s): los no negociables de la capa %s, una vez por sesión y agente. "
                  "Aplicarlos en todo lo que se escriba en esta capa (fuente: %s)." % (capa, capa, convencion.skill(capa)))
    contexto = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                       "additionalContext": _texto_primer_toque(capa, config["raiz"], encabezado, bloque)}}
    return 0, json.dumps(contexto), b""


def _pre_tool_use(evento, config):
    if evento.get("tool_name") not in ("Edit", "Write"):
        return SILENCIO
    toque = _tocar(evento, config)
    if toque is None:
        return SILENCIO
    capa, bloque = toque
    encabezado = ("primer toque (capa-%s): este %s no se aplicó. Antes de escribir en la capa %s, leer sus no "
                  "negociables y reintentar el mismo cambio, ajustado a ellos (el reintento pasa)."
                  % (capa, evento["tool_name"], capa))
    return 2, "", (_texto_primer_toque(capa, config["raiz"], encabezado, bloque) + "\n").encode("utf-8")


def _session_start(evento, config):
    sesion = evento.get("session_id")
    if evento.get("source") not in ("compact", "clear") or not id_valido(sesion):
        return SILENCIO
    carpeta = os.path.join(_marcas_dir(config["raiz"]), sesion)
    if os.path.isdir(carpeta):
        for nombre in os.listdir(carpeta):
            if nombre.startswith("principal."):
                try:
                    os.remove(os.path.join(carpeta, nombre))
                except OSError:
                    pass
    return SILENCIO


def _post_tool_use_o_read(evento, config):
    if evento.get("tool_name") == "Read":
        return _primer_read(evento, config)
    return _post_tool_use(evento, config)


def _aviso_de_config_rota(evento, razon):
    if evento.get("hook_event_name") != "SessionStart" or evento.get("source") not in ORIGENES_DEL_AVISO:
        return SILENCIO
    motivo = " ".join(str(razon).split())
    if len(motivo) > TOPE_DEL_MOTIVO:
        motivo = motivo[:TOPE_DEL_MOTIVO] + "..."
    texto = ("odd-ws: la configuración de esta instancia está rota y los hooks no verifican nada hasta arreglarla (%s). "
             "Correr /odd-ws:doctor." % motivo)
    contexto = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texto}}
    return 0, json.dumps(contexto), b""


MANEJADORES = {
    "PostToolUse": _post_tool_use_o_read,
    "PreToolUse": _pre_tool_use,
    "SessionStart": _session_start,
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
        if estado.tipo == "rota":
            return _aviso_de_config_rota(evento, estado.razon)
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
