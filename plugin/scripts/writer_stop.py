import sys

sys.dont_write_bytecode = True

import json
import os
import re
import shutil
import subprocess
import time

import config_loader
from odd_ws import capas as convencion
from odd_ws import hosts
from odd_ws.capacidades import FIN_SUBAGENTE
from odd_ws.comun import (HOST_POR_DEFECTO, PLAZO_POR_DEFECTO, SILENCIO, correr_hook, entorno_git, host_de, id_valido, plazo_de,
                          raiz_de_instancia)
from odd_ws.eventos import FinSubagente, Permitir, Seguir

EMITE = {FIN_SUBAGENTE: (Seguir,)}
ESTADOS = ("ok", "partial", "blocked")
CAMPOS = ("estado", "regla", "intento", "presupuesto", "reales", "arbol", "verificacion", "limites")
LISTAS = ("verificacion", "limites")
SIN_PLACEHOLDER = ("regla", "intento", "presupuesto", "arbol")
LIMITE_PLACEHOLDER = "<qué no demuestra la verificación>"

PLANTILLA = """## Resultado
estado: ok | partial | blocked
regla: <regla o chequeo que te frenó (ej. el ID de la regla de capa o el bloqueo del hook); «ninguna» si estado es ok>
intento: <qué intentaste en tu única corrección; «ninguno» si no hubo>
presupuesto: <archivos y techo de líneas declarados, ej. B.cs y C.cs, techo 40 líneas>
reales: <lo completa la compuerta; déjalo así>
arbol: sucio (<archivos y hunks>) | sin cambios
verificacion:
- <comando>: <resultado observado>
limites:
- %s""" % LIMITE_PLACEHOLDER

ENCABEZADO_RE = re.compile(r"^#{1,6}\s")
RESULTADO_RE = re.compile(r"^##\s+Resultado\s*$")
CAMPO_RE = re.compile(r"^\s*(?:[-*]\s+)?(%s)\s*:\s*(.*?)\s*$" % "|".join(CAMPOS))
ENTRADA_RE = re.compile(r"^\s*[-*]\s+(\S.*?)\s*$")
CON_RESULTADO_RE = re.compile(r"\S:\s+\S")
PLACEHOLDER_RE = re.compile(r"<[^<>\n]+>")
ARBOL_RE = re.compile(r"^(sin cambios|sucio\s*\(.+\))\.?$", re.IGNORECASE)
NINGUNO_RE = re.compile(r"^[`*_\s\"'«“]*ningun[oa][`*_\s.\"'»”]*$", re.IGNORECASE)

_VERIFICAR = []
_GUARDIA = []


def _verificar_capa():
    if not _VERIFICAR:
        import verificar_capa
        _VERIFICAR.append(verificar_capa)
    return _VERIFICAR[0]


def _guardia():
    if not _GUARDIA:
        import writer_guard
        _GUARDIA.append(writer_guard)
    return _GUARDIA[0]


def archivos_tocados(evento, fotos, anfitrion):
    return anfitrion.archivos_del_writer(evento, fotos)


def escritos_por_bash(evento, fotos, anfitrion):
    comandos = anfitrion.comandos_del_writer(evento, fotos)
    if comandos is None:
        return []
    destinos, escritos = _guardia().destinos, []
    for dialecto, comando in comandos:
        escritos.extend(d for d in destinos(comando, herramienta=dialecto) if d not in escritos)
    return escritos


def parsear_resultado(mensaje):
    lineas = mensaje.splitlines() if isinstance(mensaje, str) else []
    inicios = [i for i, l in enumerate(lineas) if RESULTADO_RE.match(l.strip())]
    if not inicios:
        return {}, ["falta el bloque `## Resultado` en tu último mensaje"]
    bloque = []
    for l in lineas[inicios[-1] + 1:]:
        if ENCABEZADO_RE.match(l.strip()):
            break
        bloque.append(l)
    campos, listas, lista = {}, {nombre: [] for nombre in LISTAS}, None
    for l in bloque:
        m = CAMPO_RE.match(l)
        if m:
            nombre, valor = m.group(1), m.group(2)
            lista = nombre if nombre in LISTAS else None
            if lista:
                if valor:
                    listas[lista].append(re.sub(r"^[-*]\s+", "", valor))
            else:
                campos[nombre] = valor
            continue
        e = ENTRADA_RE.match(l)
        if lista and e:
            listas[lista].append(e.group(1))
    errores = []
    estado = campos.get("estado", "").strip("`").lower()
    if "estado" not in campos:
        errores.append("falta `estado:` (ok, partial o blocked)")
    elif estado not in ESTADOS:
        errores.append("`estado:` tiene que ser ok, partial o blocked, no %r" % campos["estado"])
    else:
        campos["estado"] = estado
    for nombre in ("regla", "intento", "presupuesto", "reales"):
        if not campos.get(nombre):
            errores.append("falta `%s:` (o está vacío)" % nombre)
    for nombre in SIN_PLACEHOLDER:
        if campos.get(nombre) and PLACEHOLDER_RE.search(campos[nombre]):
            errores.append("`%s:` conserva un <placeholder> de la plantilla; complétalo" % nombre)
    if not campos.get("arbol"):
        errores.append("falta `arbol:` («sucio (archivos y hunks)» o «sin cambios»)")
    elif not ARBOL_RE.match(campos["arbol"]):
        errores.append("`arbol:` tiene que ser «sucio (archivos y hunks)» o «sin cambios», no %r" % campos["arbol"])
    validas = [e for e in listas["verificacion"] if CON_RESULTADO_RE.search(e) and "<comando>" not in e]
    if not validas:
        errores.append("falta `verificacion:` con al menos una línea `- <comando>: <resultado observado>`")
    if not [e for e in listas["limites"] if LIMITE_PLACEHOLDER not in e and not NINGUNO_RE.match(e)]:
        errores.append("falta `limites:` con al menos una línea `- %s`; «ninguno» no vale: una suite verde demuestra "
                       "los casos que ejecuta, nada más" % LIMITE_PLACEHOLDER)
    campos.update(listas)
    return campos, errores


def _git(cwd, *args, limite=None):
    timeout = _verificar_capa().TIMEOUT_GIT
    if limite is not None:
        timeout = min(timeout, limite - time.monotonic())
        if timeout <= 0:
            raise subprocess.TimeoutExpired(["git", *args], 0)
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, timeout=timeout, env=entorno_git())


def _numstat(salida):
    for linea in salida.decode("utf-8", errors="replace").splitlines():
        partes = linea.split("\t")
        if len(partes) >= 3:
            return tuple(int(x) if x.isdigit() else 0 for x in partes[:2])
    return 0, 0


def _base_del_archivo(carpeta_fotos, ruta):
    if carpeta_fotos:
        try:
            clave = _guardia().clave_foto(ruta)
            foto = os.path.join(carpeta_fotos, clave + ".foto")
            if os.path.isfile(foto):
                return "foto", foto
            if os.path.isfile(os.path.join(carpeta_fotos, clave + ".nuevo")):
                return "nuevo", None
        except (Exception, SystemExit):
            pass
    return "HEAD", None


def lineas_reales(archivos, carpeta_fotos=None, limite=None):
    datos = []
    for ruta in archivos:
        try:
            ruta = os.path.abspath(ruta)
            if not os.path.isfile(ruta):
                continue
            r = _git(os.path.dirname(ruta), "rev-parse", "--show-toplevel", limite=limite)
            if r.returncode != 0:
                continue
            raiz = r.stdout.decode("utf-8", errors="replace").strip()
            relativa = os.path.relpath(os.path.realpath(ruta), os.path.realpath(raiz)).replace("\\", "/")
            if relativa.startswith(".."):
                continue
            base, foto = _base_del_archivo(carpeta_fotos, ruta)
            if base == "foto":
                d = _git(raiz, "diff", "--no-index", "--numstat", "--ignore-cr-at-eol", "--", foto, ruta, limite=limite)
            elif base == "nuevo":
                d = _git(raiz, "diff", "--no-index", "--numstat", "--", "/dev/null", ruta, limite=limite)
            else:
                trackeado = _git(raiz, "ls-files", "--error-unmatch", "--", relativa, limite=limite).returncode == 0
                d = _git(raiz, "diff", "--numstat", "HEAD", "--", relativa, limite=limite) if trackeado else None
                if d is None or d.returncode != 0:
                    d = _git(raiz, "diff", "--no-index", "--numstat", "--", "/dev/null", ruta, limite=limite)
            if d.returncode not in (0, 1):
                continue
            agregadas, quitadas = _numstat(d.stdout)
            datos.append({"ruta": ruta, "relativa": relativa, "agregadas": agregadas, "quitadas": quitadas, "base": base})
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
    return datos


def _describir(h, relativa):
    severidad = h.get("severidad") or ""
    etiqueta = "[%s %s]" % (h["id"], severidad) if severidad else "[%s]" % h["id"]
    linea = h.get("linea")
    return "%s %s %s: %s" % (etiqueta, relativa, "línea %d" % linea if linea is not None else "archivo", h["mensaje"])


def _chequear(archivos, config, limite):
    verificar = _verificar_capa()
    bloqueos, avisos, internos = [], [], []
    for ruta in archivos:
        try:
            r = verificar.verificar_archivo(ruta, config, limite)
        except (Exception, SystemExit) as exc:
            internos.append("%s: %r" % (ruta, exc))
            continue
        if r is None:
            continue
        relativa, hallazgos = r
        for h in hallazgos:
            registro = {"ruta": ruta, "relativa": relativa, "id": h["id"], "severidad": h.get("severidad") or "",
                        "linea": h.get("linea"), "mensaje": h["mensaje"], "texto": _describir(h, relativa)}
            (bloqueos if h.get("modo") == "bloqueo" else avisos).append(registro)
    return bloqueos, avisos, internos


def _texto_reales(numstat):
    marca = {"HEAD": " (contra HEAD: sin foto)", "nuevo": " (nuevo)"}
    partes = ["%s +%d -%d%s" % (n["relativa"], n["agregadas"], n["quitadas"], marca.get(n.get("base"), "")) for n in numstat]
    return "; ".join(partes) + " (total +%d -%d)" % (sum(n["agregadas"] for n in numstat), sum(n["quitadas"] for n in numstat))


def _razon(bloqueos, errores, numstat):
    partes = ["writer-stop: todavía no puedes cerrar. Esto es todo lo que falta, junto; es tu único aviso."]
    if bloqueos:
        partes.append("Chequeos de capa en bloqueo (corrígelos con Edit o Write; es tu única corrección):")
        partes += ["- " + b["texto"] for b in bloqueos]
    if errores:
        partes.append("Formato del cierre:")
        partes += ["- " + e for e in errores]
    if numstat:
        partes.append("Líneas reales, medidas con git (quedan en el sidecar; `reales:` puede quedar como está): " + _texto_reales(numstat))
    partes.append("Cierra con este bloque, completo:")
    partes.append(PLANTILLA)
    return "\n".join(partes)


def _carpeta(raiz, sesion):
    return os.path.join(raiz, convencion.ESTADO_WRITERS, sesion)


def _escribir_estado(raiz, sesion, agente, datos):
    try:
        carpeta = _carpeta(raiz, sesion)
        os.makedirs(carpeta, exist_ok=True)
        destino = os.path.join(carpeta, agente + ".json")
        tmp = destino + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, destino)
    except OSError:
        pass


def _borrar_fotos(raiz, sesion, agente):
    try:
        shutil.rmtree(os.path.join(_carpeta(raiz, sesion), agente + ".fotos"), ignore_errors=True)
    except (Exception, SystemExit):
        pass


def _estado_parcial(evento, sesion, agente, archivos, activo, internos):
    return {
        "session_id": sesion, "agent_id": agente, "agent_type": evento.agente,
        "stop_hook_active": activo, "archivos": archivos, "escritos_por_bash": [], "numstat": [], "bloqueos": [], "avisos": [],
        "formato_ok": None, "formato_errores": [], "resultado": {}, "errores_internos": internos,
        "momento": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _etapa(internos, nombre, funcion, defecto):
    try:
        return funcion()
    except (Exception, SystemExit) as exc:
        internos.append("%s: %r" % (nombre, exc))
        return defecto


def decidir(evento, raiz=None, plazo=PLAZO_POR_DEFECTO, host=HOST_POR_DEFECTO):
    if not isinstance(evento, FinSubagente) or not convencion.es_writer(evento.agente):
        return Permitir()
    sesion, agente = evento.sesion, evento.id_agente
    if not (id_valido(sesion) and id_valido(agente)):
        return Permitir()
    limite = time.monotonic() + plazo
    if raiz is None:
        raiz = raiz_de_instancia(os.environ, evento.cwd or os.getcwd())
    if raiz is None:
        return Permitir()
    estado = config_loader.estado(raiz)
    if estado.tipo != "ok":
        return Permitir()
    config, raiz = estado.config, estado.config["raiz"]
    activo = evento.ya_reintentado
    internos = []
    anfitrion = hosts.adaptador(host)
    fotos = os.path.join(_carpeta(raiz, sesion), agente + ".fotos")
    archivos, faltas = _etapa(internos, "archivos_tocados", lambda: archivos_tocados(evento, fotos, anfitrion), ([], []))
    internos.extend("archivos_tocados: " + falta for falta in faltas)
    datos = _estado_parcial(evento, sesion, agente, archivos, activo, internos)
    _escribir_estado(raiz, sesion, agente, datos)
    numstat = _etapa(internos, "lineas reales", lambda: lineas_reales(archivos, fotos, limite), [])
    bloqueos, avisos, por_archivo = _etapa(internos, "chequeos de capa", lambda: _chequear(archivos, config, limite), ([], [], []))
    campos, errores = _etapa(internos, "formato del cierre", lambda: parsear_resultado(evento.ultimo_mensaje), ({}, []))
    etapa_rota = len(internos) > len(faltas)
    escritos = _etapa(internos, "escritos por bash", lambda: escritos_por_bash(evento, fotos, anfitrion), [])
    internos.extend(por_archivo)
    total = sum(n["agregadas"] + n["quitadas"] for n in numstat)
    if campos.get("arbol", "").lower().startswith("sin cambios") and total:
        errores.append("`arbol:` dice «sin cambios» pero git mide %s; di «sucio (archivos y hunks)» "
                       "(nunca revertir)" % _texto_reales(numstat))
    datos.update({
        "numstat": numstat, "escritos_por_bash": escritos,
        "bloqueos": [{k: v for k, v in b.items() if k != "texto"} for b in bloqueos],
        "avisos": [{k: v for k, v in a.items() if k != "texto"} for a in avisos],
        "formato_ok": not errores, "formato_errores": errores, "resultado": campos,
        "momento": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _escribir_estado(raiz, sesion, agente, datos)
    if activo or etapa_rota or not (bloqueos or errores):
        _borrar_fotos(raiz, sesion, agente)
        return Permitir()
    return Seguir(_razon(bloqueos, errores, numstat))


def correr(evento, raiz=None, plazo=PLAZO_POR_DEFECTO, host=HOST_POR_DEFECTO):
    try:
        return hosts.atender(host, evento, lambda leido: decidir(leido, raiz, plazo, host))
    except (Exception, SystemExit):
        return SILENCIO


def main():
    plazo, host = plazo_de(sys.argv[1:]), host_de(sys.argv[1:])
    return correr_hook(lambda crudo: correr(crudo, plazo=plazo, host=host))


if __name__ == "__main__":
    sys.exit(main())
