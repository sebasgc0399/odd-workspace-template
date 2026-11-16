import hashlib
import json
import os
import re
from collections import namedtuple

import odd_ws
from config_loader import NOMBRE as CONFIG
from config_loader import PREFIJO_RE
from odd_ws import capas as convencion

LOCK = convencion.PAQUETES_LOCK
VERSION_DEL_LOCK = 1
FORMATO = 1
MANIFIESTO = "odd-ws-paquete.json"
MODULO = "verificar.py"
SUITE = "verificar.tests.py"
MATRIZ = "matriz.csv"
NO_NEGOCIABLES = "no-negociables.md"
EVIDENCIA = "evidencia.md"
LICENCIA = "LICENSE"
OBLIGATORIOS = (MANIFIESTO, MODULO, SUITE, MATRIZ, NO_NEGOCIABLES, EVIDENCIA)
LISTA_BLANCA = OBLIGATORIOS + (LICENCIA,)
NOMBRE_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
HUELLA_RE = re.compile(r"sha256:[0-9a-f]{64}")
CLAVES_DEL_LOCK = ("version", "paquetes")
CLAVES_DE_UN_PAQUETE = ("capa", "prefijo", "fuente", "etiqueta", "commit", "huella")
CLAVES_DEL_MANIFIESTO = ("formato", "nombre", "prefijo", "odd_ws_api", "descripcion")
FORMA_DEL_NOMBRE = "minúsculas, dígitos y guiones, empezando por letra o dígito"
FORMA_DEL_PREFIJO = "mayúsculas y dígitos, empezando por letra"

Paquete = namedtuple("Paquete", ("nombre",) + CLAVES_DE_UN_PAQUETE)


class LockRoto(Exception):
    pass


class ManifiestoInvalido(Exception):
    pass


def carpeta(nombre):
    return convencion.paquete(nombre)


def _sin_desconocidas(datos, conocidas, donde, error):
    desconocidas = sorted(set(datos) - set(conocidas))
    if desconocidas:
        raise error(f"{donde}{desconocidas[0]} no es una clave conocida ({', '.join(conocidas)})")


def _texto(valor):
    return isinstance(valor, str) and bool(valor.strip())


def _prefijo(valor):
    return isinstance(valor, str) and PREFIJO_RE.fullmatch(valor) is not None


def _entrada(nombre, datos):
    if not NOMBRE_RE.fullmatch(nombre):
        raise LockRoto(f"el paquete {nombre!r} no tiene un nombre válido ({FORMA_DEL_NOMBRE})")
    donde = f"paquetes.{nombre}"
    if not isinstance(datos, dict):
        raise LockRoto(f"{donde} debe ser un objeto")
    _sin_desconocidas(datos, CLAVES_DE_UN_PAQUETE, donde + ".", LockRoto)
    for clave in CLAVES_DE_UN_PAQUETE:
        if clave not in datos:
            raise LockRoto(f"falta {donde}.{clave}")
    for clave in ("capa", "fuente", "etiqueta"):
        if not _texto(datos[clave]):
            raise LockRoto(f"{donde}.{clave} debe ser un texto no vacío")
    if not _prefijo(datos["prefijo"]):
        raise LockRoto(f"{donde}.prefijo {datos['prefijo']!r} debe ser {FORMA_DEL_PREFIJO}")
    if not isinstance(datos["commit"], str) or not COMMIT_RE.fullmatch(datos["commit"]):
        raise LockRoto(f"{donde}.commit {datos['commit']!r} debe ser un hash de 40 caracteres hexadecimales en minúsculas")
    if not isinstance(datos["huella"], str) or not HUELLA_RE.fullmatch(datos["huella"]):
        raise LockRoto(f"{donde}.huella {datos['huella']!r} debe ser sha256:<64 hexadecimales en minúsculas>")
    return Paquete(nombre, *(datos[clave] for clave in CLAVES_DE_UN_PAQUETE))


def validar_lock(datos):
    if not isinstance(datos, dict):
        raise LockRoto("debe ser un objeto JSON")
    _sin_desconocidas(datos, CLAVES_DEL_LOCK, "", LockRoto)
    version = datos.get("version")
    if isinstance(version, bool) or version != VERSION_DEL_LOCK:
        raise LockRoto(f"version {version!r} no es la que entiende este plugin ({VERSION_DEL_LOCK})")
    crudos = datos.get("paquetes")
    if not isinstance(crudos, dict):
        raise LockRoto("paquetes debe ser un objeto con un paquete por clave")
    paquetes, duenos = {}, {}
    for nombre, entrada in crudos.items():
        paquete = _entrada(nombre, entrada)
        if paquete.prefijo in duenos:
            raise LockRoto(f"el prefijo {paquete.prefijo} lo usan {duenos[paquete.prefijo]} y {nombre}: cada paquete lleva el suyo")
        duenos[paquete.prefijo] = nombre
        paquetes[nombre] = paquete
    return paquetes


def leer_lock(raiz):
    ruta = os.path.join(str(raiz), LOCK)
    if not os.path.lexists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.loads(f.read())
    except (OSError, ValueError) as error:
        raise LockRoto(f"no se puede leer como JSON: {error}")
    return validar_lock(datos)


def datos_del_lock(lock):
    return {"version": VERSION_DEL_LOCK,
            "paquetes": {paquete.nombre: {clave: getattr(paquete, clave) for clave in CLAVES_DE_UN_PAQUETE}
                         for paquete in sorted(lock.values(), key=lambda paquete: paquete.nombre)}}


def escribir_lock(raiz, lock):
    ruta = os.path.join(str(raiz), LOCK)
    if not lock:
        if os.path.lexists(ruta):
            os.remove(ruta)
        return
    datos = datos_del_lock(lock)
    validar_lock(datos)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    temporal = ruta + ".nuevo"
    try:
        with open(temporal, "wb") as f:
            f.write((json.dumps(datos, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        os.replace(temporal, ruta)
    finally:
        if os.path.lexists(temporal):
            os.remove(temporal)


def de_la_capa(lock, capa):
    return sorted((paquete for paquete in lock.values() if paquete.capa == capa), key=lambda paquete: paquete.nombre)


def validar_manifiesto(datos):
    if not isinstance(datos, dict):
        raise ManifiestoInvalido("debe ser un objeto JSON")
    _sin_desconocidas(datos, CLAVES_DEL_MANIFIESTO, "", ManifiestoInvalido)
    for clave in CLAVES_DEL_MANIFIESTO:
        if clave not in datos:
            raise ManifiestoInvalido(f"falta la clave {clave}")
    if isinstance(datos["formato"], bool) or datos["formato"] != FORMATO:
        raise ManifiestoInvalido(f"formato {datos['formato']!r} no es el que entiende este plugin ({FORMATO})")
    if not isinstance(datos["nombre"], str) or not NOMBRE_RE.fullmatch(datos["nombre"]):
        raise ManifiestoInvalido(f"nombre {datos['nombre']!r} debe ser {FORMA_DEL_NOMBRE}")
    if not _prefijo(datos["prefijo"]):
        raise ManifiestoInvalido(f"prefijo {datos['prefijo']!r} debe ser {FORMA_DEL_PREFIJO}")
    api = datos["odd_ws_api"]
    if isinstance(api, bool) or not isinstance(api, int) or api < 1:
        raise ManifiestoInvalido(f"odd_ws_api {api!r} debe ser un entero mayor o igual que 1")
    if not isinstance(datos["descripcion"], str):
        raise ManifiestoInvalido("descripcion debe ser un texto")
    return datos


def leer_manifiesto(carpeta_del_paquete):
    ruta = os.path.join(str(carpeta_del_paquete), MANIFIESTO)
    if not _archivo(ruta):
        raise ManifiestoInvalido(f"falta {MANIFIESTO}")
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.loads(f.read())
    except (OSError, ValueError) as error:
        raise ManifiestoInvalido(f"{MANIFIESTO} no se puede leer como JSON: {error}")
    try:
        return validar_manifiesto(datos)
    except ManifiestoInvalido as error:
        raise ManifiestoInvalido(f"{MANIFIESTO} no es válido: {error}")


def api_soportada(manifiesto):
    return manifiesto["odd_ws_api"] <= odd_ws.API


def _archivo(ruta):
    return os.path.isfile(ruta) and not os.path.islink(ruta)


def presentes(carpeta_del_paquete):
    return [nombre for nombre in sorted(LISTA_BLANCA) if _archivo(os.path.join(str(carpeta_del_paquete), nombre))]


def huella(carpeta_del_paquete):
    suma = hashlib.sha256()
    for nombre in presentes(carpeta_del_paquete):
        ruta = os.path.join(str(carpeta_del_paquete), nombre)
        with open(ruta, "rb") as f:
            contenido = f.read().replace(b"\r\n", b"\n")
        suma.update(nombre.encode("utf-8") + b"\0" + str(len(contenido)).encode("ascii") + b"\0")
        suma.update(contenido)
    return "sha256:" + suma.hexdigest()


def id_del_paquete(prefijo, id_):
    return isinstance(id_, str) and re.fullmatch(r"%s-[0-9]{2,}" % re.escape(prefijo), id_) is not None


def _prefijos_de_las_capas(capas):
    return {datos["rule_prefix"]: nombre for nombre, datos in capas.items() if isinstance(datos, dict) and "rule_prefix" in datos}


def choques_con_las_capas(lock, capas):
    ocupados = _prefijos_de_las_capas(capas)
    return {paquete.nombre: f"el prefijo {paquete.prefijo} ya lo usa layers.{ocupados[paquete.prefijo]}.rule_prefix"
            for paquete in sorted(lock.values(), key=lambda paquete: paquete.nombre) if paquete.prefijo in ocupados}


def leer_lock_contra(raiz, capas):
    lock = leer_lock(raiz)
    choques = choques_con_las_capas(lock or {}, capas)
    if choques:
        raise LockRoto("; ".join(f"{nombre}: {choque}" for nombre, choque in choques.items()))
    return lock


def es_enlace(ruta):
    es_junction = getattr(os.path, "isjunction", None)
    return os.path.islink(ruta) or bool(es_junction and es_junction(ruta))


def _fuera_de_lugar(ruta):
    return es_enlace(ruta) or os.path.normcase(os.path.realpath(ruta)) != os.path.normcase(ruta)


def _enlazados(base):
    return [archivo for archivo in LISTA_BLANCA
            if os.path.lexists(os.path.join(base, archivo)) and _fuera_de_lugar(os.path.join(base, archivo))]


def enlaces(raiz, nombre):
    relativa = carpeta(nombre)
    base = os.path.join(os.path.realpath(str(raiz)), *relativa.split("/"))
    if os.path.lexists(base) and _fuera_de_lugar(base):
        return [relativa]
    return [f"{relativa}/{archivo}" for archivo in _enlazados(base)]


def enlaces_en(carpeta_suelta):
    return _enlazados(os.path.realpath(str(carpeta_suelta)))


def destino_enlazado(raiz, nombre):
    partes = carpeta(nombre).split("/")
    base = os.path.realpath(str(raiz))
    for hasta in range(len(partes), 0, -1):
        ruta = os.path.join(base, *partes[:hasta])
        if os.path.lexists(ruta):
            return "/".join(partes[:hasta]) if _fuera_de_lugar(ruta) else None
    return None


def activos(raiz, capa, capas):
    lock = leer_lock(raiz)
    if not lock:
        return []
    choques = choques_con_las_capas(lock, capas)
    cargables = []
    for paquete in de_la_capa(lock, capa):
        if paquete.nombre in choques or enlaces(raiz, paquete.nombre):
            continue
        try:
            manifiesto = leer_manifiesto(os.path.join(str(raiz), carpeta(paquete.nombre)))
        except ManifiestoInvalido:
            continue
        if (manifiesto["nombre"], manifiesto["prefijo"]) == (paquete.nombre, paquete.prefijo) and api_soportada(manifiesto):
            cargables.append(paquete)
    return cargables


def _problemas_de(raiz, paquete, capas, choques):
    problemas = []
    if paquete.capa not in capas:
        problemas.append(f"la capa {paquete.capa} no está declarada en {CONFIG}")
    if paquete.nombre in choques:
        problemas.append(choques[paquete.nombre])
    relativa = carpeta(paquete.nombre)
    absoluta = os.path.join(str(raiz), relativa)
    if not os.path.isdir(absoluta):
        return problemas + [f"falta la carpeta {relativa}"]
    malos = enlaces(raiz, paquete.nombre)
    if malos:
        problemas.append(f"enlace o fuera de {relativa}, así que no se carga: {', '.join(malos)}")
    faltan = [nombre for nombre in OBLIGATORIOS if not _archivo(os.path.join(absoluta, nombre))]
    if faltan:
        problemas.append(f"falta{'n' if len(faltan) > 1 else ''} {', '.join(faltan)} en {relativa}")
    if MANIFIESTO not in faltan:
        try:
            manifiesto = leer_manifiesto(absoluta)
        except ManifiestoInvalido as error:
            problemas.append(str(error))
        else:
            for clave, del_lock in (("nombre", paquete.nombre), ("prefijo", paquete.prefijo)):
                if manifiesto[clave] != del_lock:
                    problemas.append(f"el manifiesto dice {clave} {manifiesto[clave]} y el lock {del_lock}")
            if not api_soportada(manifiesto):
                problemas.append(f"pide odd_ws_api {manifiesto['odd_ws_api']} y este plugin da {odd_ws.API}, así que no se carga")
    if huella(absoluta) != paquete.huella:
        problemas.append(f"la huella no coincide con el lock: lo copiado en {relativa} cambió desde que se importó")
    return problemas


def problemas(raiz, lock, capas):
    choques = choques_con_las_capas(lock, capas)
    return [f"{paquete.nombre}: {problema}" for paquete in sorted(lock.values(), key=lambda paquete: paquete.nombre)
            for problema in _problemas_de(raiz, paquete, capas, choques)]
