import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import config_loader
import matriz
from odd_ws import capas
from odd_ws.capacidades import SOPORTADO
from odd_ws.comun import raiz_de_instancia
from odd_ws.hosts import NOMBRES, adaptador
from odd_ws.hosts.base import SinMemorias
from odd_ws.hosts.claude_code import nombre_de_proyecto, raiz_del_proyecto

INDICE = "MEMORY.md"
POR_DEFECTO = ("feedback",)
OPCIONAL = "project"
NUNCA = ("user", "reference")
OTROS = "otros"
CAMPOS = ("name", "description", "type")
ORDEN = ("nueva", "cambiada", "ilegible", "vista", "descartada", "graduada")
PRECEDENCIA = ("graduada", "ilegible", "cambiada", "descartada", "vista", "nueva")
REGISTRABLES = ("vista", "descartada")
CARPETA_DEL_REGISTRO = (".odd-ws", "memorias")
VERSION_DEL_REGISTRO = 1
CAMPOS_DEL_REGISTRO = ("slug", "modified", "estado", "fecha")
FORMA_DEL_REGISTRO = '{"version": 1, "memorias": {"<slug>@<modified>": {"slug", "modified", "estado", "fecha"}}}'
HOST_POR_DEFECTO = "claude-code"
WINDOWS = os.name == "nt"
CLAVE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?")
BLOQUE_RE = re.compile(r"[|>][+-]?")
LINK_RE = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
COMENTARIO_RE = re.compile(r"\s#")


class ErrorDeEntorno(Exception):
    pass


class Ilegible(Exception):
    pass


def _escalar(valor, n):
    if valor[:1] == '"':
        if len(valor) < 2 or not valor.endswith('"'):
            raise Ilegible("línea %d del frontmatter: comillas sin cerrar" % n)
        try:
            return json.loads(valor)
        except ValueError:
            return valor[1:-1]
    if valor[:1] == "'":
        if len(valor) < 2 or not valor.endswith("'"):
            raise Ilegible("línea %d del frontmatter: comillas sin cerrar" % n)
        return valor[1:-1].replace("''", "'")
    return COMENTARIO_RE.split(valor, 1)[0].rstrip()


def _sangria(linea):
    return len(linea) - len(linea.lstrip(" \t"))


def _bloque(lineas, desde, sangria, plegado):
    partes, i = [], desde
    while i < len(lineas) and (not lineas[i].strip() or _sangria(lineas[i]) > sangria):
        partes.append(lineas[i].strip())
        i += 1
    return (" " if plegado else "\n").join(parte for parte in partes if parte), i


def frontmatter(crudo):
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        raise Ilegible("no es UTF-8")
    lineas = texto[1:].split("\n") if texto.startswith("﻿") else texto.split("\n")
    lineas = [linea.rstrip("\r") for linea in lineas]
    if lineas[0].rstrip() != "---":
        raise Ilegible("no empieza con un frontmatter (---)")
    fin = next((i for i in range(1, len(lineas)) if lineas[i].rstrip() == "---"), None)
    if fin is None:
        raise Ilegible("el frontmatter no se cierra con ---")
    cuerpo, raiz, anidados, padre, i = lineas[1:fin], {}, {}, None, 0
    while i < len(cuerpo):
        linea, n = cuerpo[i], i + 2
        i += 1
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        sangrada = _sangria(linea) > 0
        if sangrada and linea.strip().startswith("- ") and padre is not None:
            continue
        encontrada = CLAVE_RE.fullmatch(linea.strip())
        if encontrada is None:
            raise Ilegible("línea %d del frontmatter no es «clave: valor»" % n)
        clave, valor = encontrada.group(1), (encontrada.group(2) or "").strip()
        if BLOQUE_RE.fullmatch(valor):
            valor, i = _bloque(cuerpo, i, _sangria(linea), valor[0] == ">")
        elif valor:
            valor = _escalar(valor, n)
        if not sangrada:
            raiz[clave] = valor if valor != "" else None
            padre = clave if valor == "" else None
        elif padre is None:
            raise Ilegible("línea %d del frontmatter: sangría fuera de un bloque" % n)
        else:
            anidados.setdefault(padre, {})[clave] = valor
    metadata = anidados.get("metadata", {})
    return {clave: _texto(raiz.get(clave) if raiz.get(clave) is not None else metadata.get(clave))
            for clave in ("name", "description", "type", "modified")}


def _texto(valor):
    return valor if isinstance(valor, str) and valor.strip() else None


def leer_memoria(carpeta, archivo):
    registro = {"slug": archivo[:-3], "archivo": archivo, "nombre": None, "descripcion": None, "tipo": None,
                "modificada": None, "estado": None, "motivo": None, "filas": []}
    try:
        campos = frontmatter((Path(carpeta) / archivo).read_bytes())
    except OSError as error:
        registro["motivo"] = "no se puede leer (%s)" % (error.strerror or error)
    except Ilegible as error:
        registro["motivo"] = str(error)
    else:
        registro.update(nombre=campos["name"], descripcion=campos["description"], tipo=campos["type"], modificada=campos["modified"])
        faltan = [clave for clave in CAMPOS if campos[clave] is None]
        if faltan:
            registro["motivo"] = "al frontmatter le falta %s" % ", ".join(faltan)
    return registro


def enumerar(carpeta):
    try:
        with os.scandir(carpeta) as entradas:
            return sorted(entrada.name for entrada in entradas
                          if os.path.normcase(entrada.name).endswith(".md") and os.path.normcase(entrada.name) != os.path.normcase(INDICE)
                          and entrada.is_file())
    except OSError as error:
        raise ErrorDeEntorno("no se puede leer el directorio de memoria %s (%s)" % (carpeta, error.strerror or error))


def revisar_indice(carpeta, archivos, listados):
    ruta = Path(carpeta) / INDICE
    try:
        texto = ruta.read_bytes().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return ["falta %s en %s: no se revisan huérfanas ni links" % (INDICE, carpeta)]
    except OSError as error:
        return ["no se puede leer %s (%s): no se revisan huérfanas ni links" % (ruta, error.strerror or error)]
    destinos = []
    for encontrado in LINK_RE.finditer(texto):
        destino = unquote(encontrado.group(1).split("#", 1)[0])
        if destino and "://" not in destino and not destino.startswith("mailto:") and destino not in destinos:
            destinos.append(destino)
    citados = {os.path.normcase(os.path.normpath(destino)) for destino in destinos}
    huerfanas = [archivo for archivo in archivos if os.path.normcase(archivo) not in citados]
    avisos = ["huérfana: %s no figura en %s" % (archivo, INDICE) for archivo in huerfanas if archivo in listados]
    ocultas = sum(1 for archivo in huerfanas if archivo not in listados)
    if ocultas:
        avisos.append("huérfanas entre las excluidas por tipo: %d, sin nombrarlas" % ocultas)
    avisos += ["link roto: %s enlaza %s, que no existe" % (INDICE, destino) for destino in destinos
               if not (Path(carpeta) / destino).is_file()]
    return avisos


def _prefijos(raiz):
    try:
        declaradas = config_loader.capas(raiz)
    except config_loader.ConfigRota as error:
        raise ErrorDeEntorno("%s roto: %s" % (config_loader.NOMBRE, error))
    return {datos["rule_prefix"]: nombre for nombre, datos in declaradas.items() if "rule_prefix" in datos}


def graduaciones(raiz):
    prefijos = _prefijos(raiz)
    ruta = Path(raiz) / capas.MATRIZ
    try:
        texto = ruta.read_bytes().decode("utf-8")
    except OSError as error:
        raise ErrorDeEntorno("no se puede leer la matriz %s (%s)" % (ruta, error.strerror or error))
    except UnicodeDecodeError:
        raise ErrorDeEntorno("la matriz %s no es UTF-8 válido" % ruta)
    filas, errores = matriz.cargar_matriz(texto, prefijos)
    ilegible = [mensaje for n, mensaje in errores if n == 1]
    if ilegible:
        raise ErrorDeEntorno("la matriz %s es ilegible: %s" % (ruta, "; ".join(ilegible)))
    citas = {}
    for fila in filas:
        for origen in fila["origenes"]:
            if origen["tipo"] == "memoria" and fila["id"] not in citas.setdefault(origen["slug"], []):
                citas[origen["slug"]].append(fila["id"])
    return citas, ["matriz fila %d: %s (no cuenta para graduada)" % (n, mensaje) for n, mensaje in errores]


def ruta_del_registro(entorno, raiz, pasado=None):
    if pasado:
        return Path(os.path.abspath(pasado))
    return _home(entorno).joinpath(*CARPETA_DEL_REGISTRO, nombre_de_proyecto(raiz_del_proyecto(raiz)) + ".json")


def _clave(slug, modificada):
    return "%s@%s" % (slug, modificada or "")


def _entrada_valida(clave, entrada):
    return (isinstance(entrada, dict) and set(entrada) == set(CAMPOS_DEL_REGISTRO) and isinstance(entrada["slug"], str)
            and (entrada["modified"] is None or isinstance(entrada["modified"], str)) and entrada["estado"] in REGISTRABLES
            and isinstance(entrada["fecha"], str) and clave == _clave(entrada["slug"], entrada["modified"]))


def leer_registro(ruta):
    try:
        crudo = Path(ruta).read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        raise ErrorDeEntorno("no se puede leer el registro %s (%s): corregilo o pasá --registro <archivo>" % (ruta, error.strerror or error))
    try:
        datos = json.loads(crudo.decode("utf-8-sig"))
    except ValueError:
        raise ErrorDeEntorno("el registro %s es ilegible: no es JSON en UTF-8; corregilo o borralo" % ruta)
    completo = isinstance(datos, dict) and set(datos) == {"version", "memorias"}
    version, entradas = (datos["version"], datos["memorias"]) if completo else (None, None)
    if (type(version) is not int or version != VERSION_DEL_REGISTRO or not isinstance(entradas, dict)
            or not all(_entrada_valida(clave, entrada) for clave, entrada in entradas.items())):
        raise ErrorDeEntorno("el registro %s es ilegible: no tiene la forma %s; corregilo o borralo" % (ruta, FORMA_DEL_REGISTRO))
    registradas = {}
    for entrada in entradas.values():
        if entrada["slug"] in registradas:
            raise ErrorDeEntorno("el registro %s es ilegible: tiene dos entradas para %s; corregilo o borralo" % (ruta, entrada["slug"]))
        registradas[entrada["slug"]] = entrada
    return registradas


def escribir_registro(ruta, registradas):
    entradas = {_clave(entrada["slug"], entrada["modified"]): {campo: entrada[campo] for campo in CAMPOS_DEL_REGISTRO}
                for entrada in sorted(registradas.values(), key=lambda entrada: entrada["slug"])}
    texto = json.dumps({"version": VERSION_DEL_REGISTRO, "memorias": entradas}, ensure_ascii=False, indent=2) + "\n"
    temporal = None
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporal = tempfile.mkstemp(prefix=ruta.name + ".", suffix=".tmp", dir=ruta.parent)
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(texto.encode("utf-8"))
        os.replace(temporal, ruta)
    except OSError as error:
        if temporal is not None:
            try:
                os.unlink(temporal)
            except OSError:
                pass
        raise ErrorDeEntorno("no se puede escribir el registro %s (%s): pasá --registro <archivo>" % (ruta, error.strerror or error))


def registrar(ruta, registradas, directorio, slugs, estado, fecha):
    archivos = {archivo[:-3]: archivo for archivo in enumerar(directorio.ruta)}
    faltan = [slug for slug in slugs if slug not in archivos]
    if faltan:
        raise ErrorDeEntorno("no hay memoria %s en %s: no se registró nada" % (", ".join(faltan), directorio.ruta))
    nuevas = dict(registradas or {})
    for slug in dict.fromkeys(slugs):
        modificada = leer_memoria(directorio.ruta, archivos[slug])["modificada"]
        previa = nuevas.get(slug)
        if previa is None or (previa["modified"], previa["estado"]) != (modificada, estado):
            nuevas[slug] = {"slug": slug, "modified": modificada, "estado": estado, "fecha": fecha}
    escribir_registro(ruta, nuevas)
    return nuevas


def estado_de(memoria, entrada):
    aplica = {"graduada": bool(memoria["filas"]), "ilegible": memoria["motivo"] is not None,
              "cambiada": entrada is not None and entrada["modified"] != memoria["modificada"],
              "descartada": entrada is not None and entrada["estado"] == "descartada",
              "vista": entrada is not None and entrada["estado"] == "vista", "nueva": True}
    return next(estado for estado in PRECEDENCIA if aplica[estado])


def analizar(directorio, citas, avisos_de_la_matriz, tipos, host, registradas=None):
    archivos = enumerar(directorio.ruta)
    memorias, excluidas = [], {OPCIONAL: 0, **{tipo: 0 for tipo in NUNCA}, OTROS: 0}
    for archivo in archivos:
        registro = leer_memoria(directorio.ruta, archivo)
        tipo = registro["tipo"]
        if tipo is not None and tipo not in tipos:
            excluidas[tipo if tipo in excluidas else OTROS] += 1
            continue
        registro["filas"] = list(citas.get(registro["slug"], []))
        registro["estado"] = estado_de(registro, (registradas or {}).get(registro["slug"]))
        memorias.append(registro)
    cobertura = {"estado": "completa", "total": len(archivos), "directorio": str(directorio.ruta), "origen": directorio.origen,
                 "fuente": directorio.fuente, "detalle": directorio.detalle}
    return {"host": host, "cobertura": cobertura, "tipos": list(tipos), "memorias": memorias, "excluidas": excluidas,
            "avisos": revisar_indice(directorio.ruta, archivos, {registro["archivo"] for registro in memorias}) + avisos_de_la_matriz}


def no_disponible(host, nota, tipos):
    return {"host": host, "cobertura": {"estado": "no disponible", "motivo": nota}, "tipos": list(tipos), "memorias": None,
            "excluidas": None, "avisos": []}


def _celdas(registro):
    detalle = registro["motivo"] if registro["estado"] == "ilegible" else registro["descripcion"]
    if registro["filas"]:
        detalle = "%s [%s]" % (detalle or "", ", ".join(registro["filas"]))
    return [registro["estado"], registro["tipo"] or "-", registro["slug"], detalle or ""]


def formatear(informe, registro_local=None):
    cobertura = informe["cobertura"]
    if informe["memorias"] is None:
        return "COBERTURA %s: %s (%s)" % (informe["host"], cobertura["estado"], cobertura["motivo"])
    ordenadas = sorted(informe["memorias"], key=lambda registro: (ORDEN.index(registro["estado"]), registro["slug"]))
    filas = [["ESTADO", "TIPO", "MEMORIA", "DESCRIPCION"]] + [_celdas(registro) for registro in ordenadas]
    anchos = [max(len(fila[columna]) for fila in filas) for columna in range(3)]
    salida = ["  ".join(fila[columna].ljust(anchos[columna]) for columna in range(3)) + "  " + fila[3] for fila in filas]
    if not ordenadas:
        salida.append("(ninguna memoria de tipo %s)" % " ni ".join(informe["tipos"]))
    salida += ["AVISO %s" % aviso for aviso in informe["avisos"]]
    salida.append("EXCLUIDAS " + " ".join("%s=%d" % (tipo, cuantas) for tipo, cuantas in informe["excluidas"].items()))
    if registro_local is not None:
        salida.append("REGISTRO %s (%d)" % registro_local)
    salida.append("COBERTURA %s: %s (%d, %s, %s)" % (informe["host"], cobertura["estado"], cobertura["total"],
                                                    cobertura["directorio"], cobertura["origen"]))
    return "\n".join(salida)


def _home(entorno):
    valor = entorno.get("USERPROFILE" if WINDOWS else "HOME")
    return Path(valor) if valor else Path.home()


def _raiz(args, entorno):
    raiz = Path(os.path.abspath(args.raiz)) if args.raiz else raiz_de_instancia(entorno, os.getcwd())
    if raiz is None:
        raise ErrorDeEntorno("no hay %s en la carpeta de la sesión ni en sus padres (pasá --raiz)" % config_loader.NOMBRE)
    if not (raiz / config_loader.NOMBRE).is_file():
        raise ErrorDeEntorno("no hay %s en %s" % (config_loader.NOMBRE, raiz))
    return raiz


def _directorio(elegido, args, entorno, raiz):
    pasado = os.path.abspath(args.memorias) if args.memorias else None
    directorio = elegido.directorio_de_memorias(entorno, _home(entorno), raiz, WINDOWS, pasado)
    if not directorio.ruta.is_dir():
        problema = "no es un directorio" if directorio.ruta.exists() else "no existe"
        de_donde = "pasado por --memorias" if pasado else "derivado de %s%s" % (
            directorio.fuente, ", %s" % directorio.detalle if directorio.detalle else "")
        raise ErrorDeEntorno("el directorio de memoria %s %s (%s)%s" % (
            directorio.ruta, problema, de_donde, "" if pasado else ": pasá --memorias <dir>"))
    return directorio


def construir_parser():
    p = argparse.ArgumentParser(prog="memorias.py", allow_abbrev=False,
                                description="Lista las memorias del proyecto como candidatas a graduar a la matriz. "
                                            "Solo escribe con --registrar, y solo en el registro local.",
                                epilog="Estados, del que más pesa al que menos: %s." % ", ".join(PRECEDENCIA))
    p.add_argument("--memorias", metavar="DIR", help="directorio de memoria (por defecto, el que resuelve el host)")
    p.add_argument("--raiz", help="raíz de la instancia (por defecto, la de la sesión)")
    p.add_argument("--host", choices=sorted(NOMBRES), default=HOST_POR_DEFECTO, help="CLI cuya memoria se lee (por defecto, claude-code)")
    p.add_argument("--con-project", action="store_true", help="suma las memorias de tipo project; user y reference nunca entran")
    p.add_argument("--json", action="store_true", help="imprime el informe en JSON")
    p.add_argument("--registro", metavar="ARCHIVO",
                   help="registro local de lo visto o descartado (por defecto, ~/%s/<proyecto>.json)" % "/".join(CARPETA_DEL_REGISTRO))
    p.add_argument("--registrar", nargs="+", metavar="SLUG",
                   help="anota esas memorias en el registro, con su modified de hoy, y después lista; va con --como")
    p.add_argument("--como", choices=REGISTRABLES, help="con --registrar: vista o descartada")
    return p


def main(argv=None, entorno=None):
    entorno = os.environ if entorno is None else entorno
    try:
        parser = construir_parser()
        args = parser.parse_args(argv)
        if (args.registrar is None) != (args.como is None):
            parser.error("--registrar y --como van juntos")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    elegido = adaptador(args.host)
    estado, nota = elegido.MEMORIAS
    tipos = POR_DEFECTO + ((OPCIONAL,) if args.con_project else ())
    registro_local = None
    try:
        if estado != SOPORTADO:
            opcion = next((opcion for opcion, valor in (("--memorias", args.memorias), ("--registro", args.registro),
                                                        ("--registrar", args.registrar)) if valor), None)
            if opcion:
                raise ErrorDeEntorno("en %s la memoria de Claude Code está %s (%s): %s vale con --host claude-code"
                                     % (args.host, estado, nota, opcion))
            informe = no_disponible(args.host, nota, tipos)
        else:
            raiz = _raiz(args, entorno)
            directorio = _directorio(elegido, args, entorno, raiz)
            citas, avisos = graduaciones(raiz)
            ruta = ruta_del_registro(entorno, raiz, args.registro)
            registradas = leer_registro(ruta)
            if args.registrar:
                registradas = registrar(ruta, registradas, directorio, args.registrar, args.como, date.today().isoformat())
            informe = analizar(directorio, citas, avisos, tipos, args.host, registradas)
            registro_local = None if registradas is None else (ruta, len(registradas))
    except (ErrorDeEntorno, SinMemorias) as exc:
        print("memorias: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(informe, ensure_ascii=False, indent=2) if args.json else formatear(informe, registro_local))
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
        print("memorias: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
