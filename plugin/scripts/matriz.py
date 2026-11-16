import sys

sys.dont_write_bytecode = True

import argparse
import csv
import io
import os
import re
from pathlib import Path

import config_loader
from odd_ws import capas as convencion
from odd_ws import paquetes
from odd_ws.capas import partir_bloque
from odd_ws.comun import raiz_de_instancia

ENCABEZADO = ["id", "origen", "tipo", "destino", "severidad", "numeros", "resumen", "motivo"]
TIPOS = ("CE", "CC", "PR", "CR", "MT", "META")
DESTINOS = ("chequeo", "pasiva", "skill", "reviewer-PR", "criterios", "evidencia", "descarte")
DESTINOS_DE_PAQUETE = ("chequeo", "pasiva", "evidencia", "descarte")
ARCHIVO_DE_PAQUETE = {"chequeo": paquetes.MODULO, "pasiva": paquetes.NO_NEGOCIABLES, "evidencia": paquetes.EVIDENCIA}
SEVERIDADES = ("CRITICAL", "WARNING", "SUGGESTION")

RE_MEMORIA = re.compile(r"memoria:([\w.\-]+)")
RE_RANGO = re.compile(r"([^@:\\\s]+)(?:@([0-9a-f]{7,40}))?:([0-9]+)-([0-9]+)")


class ErrorEntorno(Exception):
    pass


def lineas_de(texto):
    ls = texto.split("\n")
    if ls and ls[-1] == "":
        ls.pop()
    return [l.rstrip("\r") for l in ls]


def contar_id(id_, texto):
    patron = r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(id_)
    return len(re.findall(patron, texto))


def numero_en_texto(numero, texto):
    patron = r"(?<![0-9])(?<![0-9]\.)%s(?![0-9])(?!\.[0-9])" % re.escape(numero)
    return re.search(patron, texto) is not None


def severidad_en_texto(severidad, texto):
    return re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(severidad), texto) is not None


def segmentos(id_, lineas, ids):
    otros = sorted((i for i in ids if i != id_), key=len, reverse=True)
    re_otros = re.compile(
        r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(re.escape(i) for i in otros)) if otros else None
    res = []
    for i, l in enumerate(lineas):
        if contar_id(id_, l) == 0:
            continue
        j = i + 1
        while j < len(lineas) and lineas[j].strip() and not (re_otros and re_otros.search(lineas[j])):
            j += 1
        res.append("\n".join(lineas[i:j]))
    return res


def parsear_origen(ref):
    m = RE_MEMORIA.fullmatch(ref)
    if m:
        return {"tipo": "memoria", "slug": m.group(1), "crudo": ref}
    m = RE_RANGO.fullmatch(ref)
    if not m:
        raise ValueError("'%s' no es <ruta>:<ini>-<fin>, <ruta>@<hash>:<ini>-<fin> ni memoria:<slug>" % ref)
    ruta, hash_, ini, fin = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
    if ruta.startswith("/") or ".." in ruta.split("/"):
        raise ValueError("'%s': la ruta debe ser relativa a la raiz" % ref)
    if ini < 1 or ini > fin:
        raise ValueError("'%s': el rango es 1-based con ini <= fin" % ref)
    return {"tipo": "rango", "ruta": ruta, "hash": hash_, "ini": ini, "fin": fin, "crudo": ref}


def _re_id(prefijos):
    if not prefijos:
        return None, "ninguna capa declara rule_prefix"
    alternativas = "|".join(re.escape(p) for p in prefijos)
    return re.compile(r"(%s)-[0-9]{2,}" % alternativas), "^(%s)-[0-9]{2,}$" % alternativas


def _errores_fila(reg, vistos, n, prefijos, re_id, forma, destinos=DESTINOS):
    errores = []
    d = dict(zip(ENCABEZADO, reg))
    capa, origenes, numeros = None, [], []

    if re_id is not None and re_id.fullmatch(d["id"]):
        capa = prefijos[d["id"].split("-")[0]]
        if d["id"] in vistos:
            errores.append("id duplicado '%s' (ya en fila %d)" % (d["id"], vistos[d["id"]]))
        else:
            vistos[d["id"]] = n
    else:
        errores.append("id '%s' no cumple %s" % (d["id"], forma))

    if not d["origen"]:
        errores.append("origen vacio")
    else:
        for pieza in d["origen"].split(";"):
            try:
                o = parsear_origen(pieza)
            except ValueError as exc:
                errores.append("origen: %s" % exc)
                continue
            if o["tipo"] == "rango" and o["hash"] is None:
                errores.append("origen: '%s' sin @hash: todo rango se fija a un commit "
                               "(<ruta>@<hash>:<ini>-<fin>); solo memoria: va sin hash" % pieza)
            origenes.append(o)
    if d["tipo"] not in TIPOS:
        errores.append("tipo '%s' no es %s" % (d["tipo"], "|".join(TIPOS)))
    if d["destino"] not in destinos:
        errores.append("destino '%s' no es %s" % (d["destino"], "|".join(destinos)))
    if d["severidad"] and d["severidad"] not in SEVERIDADES:
        errores.append("severidad '%s' no es %s (o vacia)" % (d["severidad"], "|".join(SEVERIDADES)))
    if d["numeros"]:
        numeros = d["numeros"].split(";")
        if any(not p.strip() for p in numeros):
            errores.append("numeros '%s' tiene una pieza vacia" % d["numeros"])
    if not d["resumen"].strip():
        errores.append("resumen vacio")
    if not d["motivo"].strip():
        errores.append("motivo vacio")

    if errores:
        return None, errores
    d.update({"n": n, "capa": capa, "origenes": origenes, "numeros": numeros})
    return d, []


def cargar_matriz(texto, prefijos, destinos=DESTINOS):
    try:
        lector = csv.reader(io.StringIO(texto, newline=""))
        registros, previa = [], 0
        for reg in lector:
            registros.append((previa + 1, reg))
            previa = lector.line_num
    except csv.Error as exc:
        return [], [(1, "csv ilegible: %s" % exc)]
    registros = [(n, reg) for n, reg in registros if reg]
    if not registros:
        return [], [(1, "archivo vacio: falta el encabezado %s" % ",".join(ENCABEZADO))]
    n0, cabecera = registros[0]
    if cabecera != ENCABEZADO:
        bom = " (empieza con BOM: tiene que ser UTF-8 sin BOM)" if cabecera and cabecera[0].startswith("﻿") else ""
        return [], [(n0, "encabezado distinto de %s%s" % (",".join(ENCABEZADO), bom))]
    re_id, forma = _re_id(prefijos)
    filas, errores, vistos = [], [], {}
    for n, reg in registros[1:]:
        if len(reg) != len(ENCABEZADO):
            errores.append((n, "%d columnas en vez de %d" % (len(reg), len(ENCABEZADO))))
            continue
        fila, errs = _errores_fila(reg, vistos, n, prefijos, re_id, forma, destinos)
        errores += [(n, e) for e in errs]
        if fila:
            filas.append(fila)
    return filas, errores


def archivos_destino(destino, capa, archivos, paquete=None):
    if paquete is not None:
        if destino not in ARCHIVO_DE_PAQUETE:
            return [], None
        canon = "%s/%s" % (paquete, ARCHIVO_DE_PAQUETE[destino])
        return [r for r in [canon] if r in archivos], canon
    if destino == "chequeo":
        canon = convencion.chequeo(capa)
        cand = [canon]
    elif destino in ("pasiva", "skill"):
        canon = convencion.skill(capa)
        cand = [canon]
    elif destino == "reviewer-PR":
        canon = convencion.revisor(capa)
        cand = [canon]
    elif destino == "evidencia":
        canon = convencion.EVIDENCIA
        cand = [canon]
    elif destino == "criterios":
        canon = convencion.CRITERIOS_SKILL
        refs = convencion.CRITERIOS_REFS
        cand = [canon] + sorted(r for r in archivos
                                if r.startswith(refs) and r.endswith(".md") and "/" not in r[len(refs):])
    else:
        return [], None
    return [r for r in cand if r in archivos], canon


def todos_los_destinos(capa, archivos, paquete=None):
    res = []
    for d in ("chequeo", "pasiva", "skill", "reviewer-PR", "criterios", "evidencia"):
        for r in archivos_destino(d, capa, archivos, paquete)[0]:
            if r not in res:
                res.append(r)
    return res


def _alcance(destino, ruta, archivos, paquete=None):
    ls = lineas_de(archivos[ruta])
    if destino not in ("pasiva", "skill") or paquete is not None:
        return ls, None
    dentro, fuera, estado = partir_bloque(ls)
    if destino == "pasiva":
        if estado == "ausente":
            return [], "%s no tiene el bloque %s" % (ruta, convencion.MARCA_ABRE)
        if estado == "abierto":
            return [], "en %s el bloque %s no se cierra con %s" % (ruta, convencion.MARCA_ABRE, convencion.MARCA_CIERRA)
        return dentro, None
    return fuera, None


_ZONA = {"pasiva": " (dentro del bloque no-negociables)", "skill": " (fuera del bloque no-negociables)"}


def _zona(destino, paquete):
    return "" if paquete is not None else _ZONA.get(destino, "")


def verificar_destinos(filas, capa, archivos, paquete=None):
    fallas, pendientes = [], []
    for f in filas:
        if f["capa"] != capa:
            continue
        id_, destino = f["id"], f["destino"]
        if destino == "descarte":
            for ruta in todos_los_destinos(capa, archivos, paquete):
                if contar_id(id_, archivos[ruta]):
                    fallas.append("FALLA %s: descarte aparece en %s" % (id_, ruta))
            continue
        existentes, canon = archivos_destino(destino, capa, archivos, paquete)
        if not existentes:
            pendientes.append("PENDIENTE %s: %s no existe todavia" % (id_, canon))
            continue
        total, problema = 0, None
        for ruta in existentes:
            ls, problema = _alcance(destino, ruta, archivos, paquete)
            if problema:
                break
            total += contar_id(id_, "\n".join(ls))
        rutas = ", ".join(existentes)
        if problema:
            fallas.append("FALLA %s: %s" % (id_, problema))
        elif total == 0:
            fallas.append("FALLA %s: no aparece en %s%s" % (id_, rutas, _zona(destino, paquete)))
        elif total > 1:
            fallas.append("FALLA %s: aparece %d veces en %s%s (debe ser exactamente 1)"
                          % (id_, total, rutas, _zona(destino, paquete)))
    return fallas, pendientes


def verificar_severidad(filas, capa, archivos, paquete=None):
    fallas, pendientes = [], []
    ids = {f["id"] for f in filas}
    for f in filas:
        if f["capa"] != capa or f["destino"] == "descarte" or not (f["severidad"] or f["numeros"]):
            continue
        id_ = f["id"]
        existentes, canon = archivos_destino(f["destino"], capa, archivos, paquete)
        if not existentes:
            pendientes.append("PENDIENTE %s: %s no existe todavia" % (id_, canon))
            continue
        candidatos, problema = [], None
        for ruta in existentes:
            ls, problema = _alcance(f["destino"], ruta, archivos, paquete)
            if problema:
                break
            candidatos += [(ruta, s) for s in segmentos(id_, ls, ids)]
        if problema:
            fallas.append("FALLA %s: %s" % (id_, problema))
            continue
        if not candidatos:
            fallas.append("FALLA %s: no aparece en %s%s"
                          % (id_, ", ".join(existentes), _zona(f["destino"], paquete)))
            continue
        mejor = None
        for ruta, seg in candidatos:
            faltan = []
            if f["severidad"] and not severidad_en_texto(f["severidad"], seg):
                faltan.append("severidad %s" % f["severidad"])
            faltan += ["numero %s" % n for n in f["numeros"] if not numero_en_texto(n, seg)]
            if mejor is None or len(faltan) < len(mejor[1]):
                mejor = (ruta, faltan)
            if not faltan:
                break
        if mejor[1]:
            fallas.append("FALLA %s: el segmento en %s no contiene %s" % (id_, mejor[0], ", ".join(mejor[1])))
    return fallas, pendientes


def leer_texto(ruta):
    return Path(ruta).read_bytes().decode("utf-8", errors="replace")


def cargar_archivos(raiz, nombres_de_capas):
    raiz = Path(raiz)
    rutas = [convencion.EVIDENCIA, convencion.CRITERIOS_SKILL]
    for capa in nombres_de_capas:
        rutas += [convencion.chequeo(capa), convencion.skill(capa), convencion.revisor(capa)]
    carpeta = raiz / convencion.CRITERIOS_REFS
    if carpeta.is_dir():
        rutas += sorted("%s%s" % (convencion.CRITERIOS_REFS, p.name) for p in carpeta.glob("*.md") if p.is_file())
    return {r: leer_texto(raiz / r) for r in rutas if (raiz / r).is_file()}


def cargar_archivos_del_paquete(raiz, carpeta):
    rutas = ["%s/%s" % (carpeta, nombre) for nombre in ARCHIVO_DE_PAQUETE.values()]
    return {r: leer_texto(Path(raiz) / r) for r in rutas if (Path(raiz) / r).is_file()}


def _decodificada(crudo, prefijos, destinos):
    try:
        return cargar_matriz(crudo.decode("utf-8"), prefijos, destinos)
    except UnicodeDecodeError:
        return [], [(1, "no es UTF-8 valido")]


def _reportar(filas, errores, archivos, capa, modo, paquete=None, prefijo=""):
    fallas, pendientes = [], []
    if not any(n == 1 for n, _ in errores):
        verificar = verificar_destinos if modo == "destinos" else verificar_severidad
        fallas, pendientes = verificar(filas, capa, archivos(), paquete)
    filas = [f for f in filas if f["capa"] == capa]
    for n, msg in errores:
        print("%sESQUEMA fila %d: %s" % (prefijo, n, msg))
    for linea in fallas + pendientes:
        print(prefijo + linea)
    print("%sRESUMEN %s: filas=%d esquema=%d fallas=%d pendientes=%d"
          % (prefijo, modo, len(filas), len(errores), len(fallas), len(pendientes)))
    return bool(errores or fallas)


def validar_paquete(raiz, paquete, capa, modo):
    carpeta = paquetes.carpeta(paquete.nombre)
    relativa = "%s/%s" % (carpeta, paquetes.MATRIZ)
    try:
        crudo = (Path(raiz) / relativa).read_bytes()
    except OSError as exc:
        filas, errores = [], [(1, "no se puede leer %s (%s)" % (relativa, exc.strerror or exc))]
    else:
        filas, errores = _decodificada(crudo, {paquete.prefijo: capa}, DESTINOS_DE_PAQUETE)
    return _reportar(filas, errores, lambda: cargar_archivos_del_paquete(raiz, carpeta), capa, modo, carpeta,
                     "paquete %s: " % paquete.nombre)


def _paquetes_de(raiz, capa):
    try:
        return paquetes.de_la_capa(paquetes.leer_lock_contra(raiz, config_loader.capas(raiz)) or {}, capa)
    except paquetes.LockRoto as exc:
        raise ErrorEntorno("%s roto: %s" % (paquetes.LOCK, exc))


def _prefijos(raiz, capa):
    if not (Path(raiz) / config_loader.NOMBRE).is_file():
        raise ErrorEntorno("no hay %s en %s" % (config_loader.NOMBRE, raiz))
    try:
        declaradas = config_loader.capas(raiz)
    except config_loader.ConfigRota as exc:
        raise ErrorEntorno("%s roto: %s" % (config_loader.NOMBRE, exc))
    if capa not in declaradas:
        raise ErrorEntorno("la capa %s no esta declarada en %s (capas: %s)"
                           % (capa, config_loader.NOMBRE, ", ".join(declaradas)))
    if "rule_prefix" not in declaradas[capa]:
        raise ErrorEntorno("la capa %s no tiene rule_prefix en %s: sin prefijo no tiene matriz"
                           % (capa, config_loader.NOMBRE))
    return {datos["rule_prefix"]: nombre for nombre, datos in declaradas.items() if "rule_prefix" in datos}


def construir_parser():
    p = argparse.ArgumentParser(prog="matriz.py", allow_abbrev=False,
                                description="Valida la matriz de reglas de la instancia contra sus destinos y, con paquetes "
                                            "de la capa en %s, la de cada paquete contra sus propios archivos (destinos "
                                            "%s; sus lineas empiezan con 'paquete <nombre>:'). Solo lectura."
                                            % (paquetes.LOCK, "|".join(DESTINOS_DE_PAQUETE)))
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--destinos", dest="modo", action="store_const", const="destinos",
                      help="cada regla de la capa aparece una vez en su destino")
    modo.add_argument("--severidad", dest="modo", action="store_const", const="severidad",
                      help="severidad y numeros presentes en el segmento del ID")
    p.add_argument("--capa", required=True, help="capa declarada en workspace.config.json, con rule_prefix")
    p.add_argument("--raiz", help="raiz de la instancia (por defecto, la de la sesion)")
    p.add_argument("--matriz", help="CSV de la matriz (por defecto <raiz>/%s)" % convencion.MATRIZ)
    return p


def main(argv=None):
    try:
        args = construir_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        raiz = args.raiz or raiz_de_instancia(os.environ, os.getcwd())
        if raiz is None:
            raise ErrorEntorno("no hay %s en la carpeta de la sesion ni en sus padres (pasa --raiz)" % config_loader.NOMBRE)
        prefijos = _prefijos(raiz, args.capa)
        de_paquetes = _paquetes_de(raiz, args.capa)
        matriz = Path(args.matriz) if args.matriz else Path(raiz) / convencion.MATRIZ
        try:
            crudo = matriz.read_bytes()
        except OSError as exc:
            raise ErrorEntorno("no se puede leer la matriz %s (%s)" % (matriz, exc.strerror or exc))
    except ErrorEntorno as exc:
        print("matriz: %s" % exc, file=sys.stderr)
        return 2
    filas, errores = _decodificada(crudo, prefijos, DESTINOS)
    malo = _reportar(filas, errores, lambda: cargar_archivos(raiz, sorted(set(prefijos.values()))), args.capa, args.modo)
    for paquete in de_paquetes:
        malo = validar_paquete(raiz, paquete, args.capa, args.modo) or malo
    return 1 if malo else 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("matriz: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
