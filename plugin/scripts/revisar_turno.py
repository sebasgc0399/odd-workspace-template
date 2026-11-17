import sys

sys.dont_write_bytecode = True

import json
import os
import shutil
import time
import uuid

import config_loader
from odd_ws import capas as convencion
from odd_ws import hosts
from odd_ws.capacidades import FIN_TURNO
from odd_ws.comun import (HOST_POR_DEFECTO, PLAZO_POR_DEFECTO, SILENCIO, clave_foto, correr_hook, decodificar, host_de, id_valido,
                          plazo_de, raiz_de_instancia)
from odd_ws.eventos import FinTurno, InicioTurno, Permitir, Seguir

EMITE = {FIN_TURNO: (Seguir,)}
TURNOS = convencion.ESTADO + "/turnos"
MANIFIESTO = "manifiesto.json"
RENOMBRES = (b"R", b"C")
NO_ES_TUYO = "si este cambio no es tuyo, avísale al usuario y no lo toques"
EDICION = "{{host:edicion}}"
EDICION_POR_DEFECTO = "la herramienta de edición"

_CIERRE = []


def _cierre():
    if not _CIERRE:
        import writer_stop
        _CIERRE.append(writer_stop)
    return _CIERRE[0]


def _verificar_capa():
    return _cierre()._verificar_capa()


def carpeta_del_turno(raiz, sesion):
    return os.path.join(raiz, TURNOS, sesion)


def _arriba(carpeta, limite):
    if os.path.exists(os.path.join(carpeta, ".git")):
        return carpeta
    r = _cierre()._git(carpeta, "rev-parse", "--show-toplevel", limite=limite)
    arriba = os.fsdecode(r.stdout).strip() if r.returncode == 0 else ""
    return arriba or None


def _sucios(carpeta, limite):
    arriba = _arriba(carpeta, limite)
    if arriba is None:
        return []
    r = _cierre()._git(carpeta, "--no-optional-locks", "status", "--porcelain", "-z", "-uall", "--", ".", limite=limite)
    if r.returncode != 0:
        return []
    rutas, campos, i = [], r.stdout.split(b"\0"), 0
    while i < len(campos):
        registro = campos[i]
        i += 1
        if len(registro) < 4:
            continue
        if registro[:1] in RENOMBRES or registro[1:2] in RENOMBRES:
            i += 1
        relativa = registro[3:]
        if relativa.endswith(b"/"):
            continue
        try:
            rutas.append(os.path.normpath(os.path.join(arriba, os.fsdecode(relativa))))
        except (UnicodeDecodeError, ValueError):
            continue
    return rutas


def _raices(config):
    raices = []
    for repo in config["repos"].values():
        raices += [repo["path"], *repo.get("worktrees", [])]
    return raices + [config["raiz"]]


def archivos_de_capa_sucios(config, limite):
    vistos, archivos = set(), []
    for carpeta in _raices(config):
        if not os.path.isdir(carpeta):
            continue
        for ruta in _sucios(carpeta, limite):
            clave = config_loader.canonica(ruta)
            if clave in vistos or not os.path.isfile(ruta):
                continue
            vistos.add(clave)
            if config_loader.clasificar(ruta, config) is not None:
                archivos.append(ruta)
    return archivos


def _leer(ruta):
    try:
        with open(ruta, "rb") as f:
            return f.read()
    except OSError:
        return None


def _entrada(ruta, destino, tope):
    try:
        grande = os.path.getsize(ruta) > tope
    except OSError:
        return None
    if grande:
        return {"ruta": ruta, "foto": None}
    contenido = _leer(ruta)
    if contenido is None:
        return None
    nombre = clave_foto(ruta) + ".foto"
    with open(os.path.join(destino, nombre), "xb") as f:
        f.write(contenido)
    return {"ruta": ruta, "foto": nombre}


def _sacar_foto(raiz, sesion, turno, archivos):
    carpeta = carpeta_del_turno(raiz, sesion)
    padre = os.path.dirname(carpeta)
    os.makedirs(padre, exist_ok=True)
    temporal = os.path.join(padre, "%s.%s.tmp" % (sesion, uuid.uuid4().hex))
    os.mkdir(temporal)
    try:
        tope = _verificar_capa().TOPE_BYTES
        entradas = [entrada for entrada in (_entrada(ruta, temporal, tope) for ruta in archivos) if entrada is not None]
        datos = {"sesion": sesion, "turno": turno if isinstance(turno, str) else None,
                 "momento": time.strftime("%Y-%m-%dT%H:%M:%S"), "archivos": entradas}
        with open(os.path.join(temporal, MANIFIESTO), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.rename(temporal, carpeta)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    _verificar_capa()._podar(padre, sesion)


def _config(evento, raiz):
    if not id_valido(evento.sesion):
        return None
    if raiz is None:
        raiz = raiz_de_instancia(os.environ, evento.cwd or os.getcwd())
    if raiz is None:
        return None
    estado = config_loader.estado(raiz)
    return estado.config if estado.tipo == "ok" else None


def _inicio(evento, raiz, limite):
    if evento.agente or evento.id_agente:
        return
    config = _config(evento, raiz)
    if config is None or os.path.isdir(carpeta_del_turno(config["raiz"], evento.sesion)):
        return
    _sacar_foto(config["raiz"], evento.sesion, evento.turno, archivos_de_capa_sucios(config, limite))


def _del_turno(hallazgos, anterior, ruta, verificar):
    actual = _leer(ruta)
    if actual is None:
        return []
    hunks = verificar._hunks_contra(decodificar(anterior), decodificar(actual))
    nuevas = {n for hunk in hunks for n, _ in hunk["agregadas"]}
    propios = [h for h in hallazgos if h.get("linea") is None or h.get("linea") in nuevas]
    return verificar.filtrar_preexistentes(propios, hunks)


def _chequear(archivos, config, limite):
    verificar, describir = _verificar_capa(), _cierre()._describir
    bloqueos, avisos = [], []
    for ruta, anterior in archivos:
        try:
            resultado = verificar.verificar_archivo(ruta, config, limite, aislar_la_capa=True)
            if resultado is None:
                continue
            hallazgos = resultado[1] if anterior is None else _del_turno(resultado[1], anterior, ruta, verificar)
        except (Exception, SystemExit):
            continue
        for h in hallazgos:
            (bloqueos if h.get("modo") == "bloqueo" else avisos).append(describir(h, ruta))
    return bloqueos, avisos


def _cambiados(config, carpeta, limite):
    with open(os.path.join(carpeta, MANIFIESTO), encoding="utf-8") as f:
        manifiesto = json.load(f)
    sin_foto = {clave_foto(entrada["ruta"]) for entrada in manifiesto["archivos"] if not entrada.get("foto")}
    cambiados = []
    for ruta in archivos_de_capa_sucios(config, limite):
        base, foto = _cierre()._base_del_archivo(carpeta, ruta)
        if base == "foto":
            anterior = _leer(foto)
            if anterior is not None and anterior != _leer(ruta):
                cambiados.append((ruta, anterior))
        elif clave_foto(ruta) not in sin_foto:
            cambiados.append((ruta, None))
    return cambiados


def _razon(bloqueos, avisos, host):
    textos = getattr(hosts.adaptador(host), "TEXTOS", {})
    partes = ["revisar-turno: todavía no cierres el turno. Estos archivos de capa cambiaron en este turno, sin importar cómo se "
              "escribieron, y tienen chequeos de capa en bloqueo; corrígelos con %s (es tu única vuelta):"
              % textos.get(EDICION, EDICION_POR_DEFECTO)]
    partes += ["- " + texto for texto in bloqueos]
    if avisos:
        partes.append("Avisos (no bloquean; corrígelos si son tuyos):")
        partes += ["- " + texto for texto in avisos]
    partes.append("El chequeo no distingue quién escribió cada cambio: %s." % NO_ES_TUYO)
    return "\n".join(partes)


def _revisar(config, carpeta, limite, host):
    bloqueos, avisos = _chequear(_cambiados(config, carpeta, limite), config, limite)
    return Seguir(_razon(bloqueos, avisos, host)) if bloqueos else Permitir()


def _fin(evento, raiz, limite, host):
    config = _config(evento, raiz)
    if config is None:
        return Permitir()
    carpeta = carpeta_del_turno(config["raiz"], evento.sesion)
    if not os.path.isdir(carpeta):
        return Permitir()
    decision = Permitir()
    try:
        if not evento.continuado:
            decision = _revisar(config, carpeta, limite, host)
    finally:
        if not isinstance(decision, Seguir):
            shutil.rmtree(carpeta, ignore_errors=True)
    return decision


def decidir(evento, raiz=None, plazo=PLAZO_POR_DEFECTO, host=HOST_POR_DEFECTO):
    limite = time.monotonic() + plazo
    try:
        if isinstance(evento, InicioTurno):
            _inicio(evento, raiz, limite)
        elif isinstance(evento, FinTurno):
            return _fin(evento, raiz, limite, host)
    except (Exception, SystemExit):
        pass
    return Permitir()


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
