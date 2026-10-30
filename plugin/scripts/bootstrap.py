import json
import os
import sys
import tempfile
from collections import namedtuple
from pathlib import Path

import config_loader
from odd_ws import capas as convencion

VERSION_DE_SPEC = 1
USO = "uso: bootstrap.py --spec <ruta.json> [--raiz <carpeta>] [--ensayo]"
CREAR, YA_EXISTE = "crear", "ya_existe"
CREADO, YA_EXISTIA = "creado", "ya_existia"
CLAVES_BASE = ("spec_version",)
LINEAS_DE_GITIGNORE = (config_loader.NOMBRE_LOCAL, convencion.ESTADO + "/")

Accion = namedtuple("Accion", "ruta contenido modo")
Resultado = namedtuple("Resultado", "ruta estado")
Generador = namedtuple("Generador", "nombre funcion claves validar")
Opciones = namedtuple("Opciones", "spec raiz ensayo")

GENERADORES = []


class SpecInvalida(Exception):
    pass


class ErrorDePlan(Exception):
    pass


class ErrorDeAplicacion(Exception):
    def __init__(self, mensaje, resultados):
        super().__init__(mensaje)
        self.resultados = resultados


def registrar_generador(nombre, funcion, claves=(), validar=None):
    if any(g.nombre == nombre for g in GENERADORES):
        raise ValueError(f"el generador {nombre!r} ya está registrado")
    for clave in claves:
        if clave in claves_conocidas():
            raise ValueError(f"la clave {clave!r} de la spec ya la registra otro generador")
    GENERADORES.append(Generador(nombre, funcion, tuple(claves), validar))


def claves_conocidas():
    conocidas = list(CLAVES_BASE)
    for generador in GENERADORES:
        conocidas.extend(generador.claves)
    return tuple(conocidas)


def serializar(objeto):
    try:
        return (json.dumps(objeto, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    except UnicodeEncodeError as error:
        raise SpecInvalida(f"la spec trae un texto que no se puede escribir en UTF-8: {error}")


def leer_spec(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise SpecInvalida(f"no se puede leer la spec {ruta} como JSON: {error}")


def _validar_config(spec):
    with tempfile.TemporaryDirectory(prefix="bootstrap-") as carpeta:
        copia = Path(carpeta)
        (copia / config_loader.NOMBRE).write_bytes(serializar(spec["config"]))
        (copia / config_loader.NOMBRE_LOCAL).write_bytes(serializar(spec.get("local", {})))
        try:
            config_loader.cargar(copia)
            config_loader.conocimiento(copia)
        except config_loader.ConfigRota as error:
            raise SpecInvalida(f"la config no es válida: {error}")


def validar_spec(spec):
    if not isinstance(spec, dict):
        raise SpecInvalida("la spec debe ser un objeto JSON")
    version = spec.get("spec_version")
    if type(version) is not int or version != VERSION_DE_SPEC:
        raise SpecInvalida(f"spec_version {version!r} no es la que entiende este script ({VERSION_DE_SPEC})")
    conocidas = claves_conocidas()
    desconocidas = sorted(set(spec) - set(conocidas))
    if desconocidas:
        raise SpecInvalida(f"{desconocidas[0]} no es una clave conocida de la spec ({', '.join(conocidas)})")
    if not isinstance(spec.get("config"), dict):
        raise SpecInvalida(f"config debe ser un objeto: el contenido de {config_loader.NOMBRE}")
    local = spec.get("local", {})
    if not isinstance(local, dict):
        raise SpecInvalida(f"local debe ser un objeto: el contenido de {config_loader.NOMBRE_LOCAL} sin plugin_root")
    if "plugin_root" in local:
        raise SpecInvalida("local.plugin_root no va en la spec: lo anota el doctor")
    for generador in GENERADORES:
        if generador.validar is not None:
            generador.validar(spec)
    _validar_config(spec)


def _generar_config(spec):
    return [
        (config_loader.NOMBRE, serializar(spec["config"])),
        (config_loader.NOMBRE_LOCAL, serializar(spec.get("local", {}))),
        (convencion.GITIGNORE, "".join(linea + "\n" for linea in LINEAS_DE_GITIGNORE)),
    ]


def _ruta_relativa(ruta):
    if not isinstance(ruta, str) or "\x00" in ruta or "\\" in ruta or ":" in ruta:
        raise ErrorDePlan(f"la ruta {ruta!r} debe ser un texto relativo a la raíz, con /")
    for segmento in ruta.split("/"):
        if segmento in ("", ".", "..") or segmento != segmento.rstrip(" ."):
            raise ErrorDePlan(f"la ruta {ruta!r} debe ser relativa a la raíz, sin '.', '..', segmentos vacíos ni segmentos que terminen en punto o espacio")
    return ruta


def _accion(valor, generador):
    if not isinstance(valor, (tuple, list)) or len(valor) != 2:
        raise ErrorDePlan(f"el generador {generador} devolvió una acción que no es (ruta, contenido): {valor!r}")
    ruta, contenido = valor
    ruta = _ruta_relativa(ruta)
    if isinstance(contenido, str):
        try:
            contenido = contenido.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ErrorDePlan(f"el contenido de {ruta} no se puede escribir en UTF-8: {error}")
    if not isinstance(contenido, bytes):
        raise ErrorDePlan(f"el contenido de {ruta} debe ser un texto o bytes")
    return ruta, contenido


def _dentro(ruta, carpeta):
    ruta, carpeta = os.path.normcase(ruta), os.path.normcase(carpeta)
    try:
        return os.path.commonpath([ruta, carpeta]) == carpeta
    except ValueError:
        return False


def _revisar_destino(raiz, ruta):
    real = os.path.realpath(raiz)
    actual = raiz
    previas = []
    for segmento in ruta.split("/")[:-1]:
        actual = actual / segmento
        previas.append(segmento)
        if not os.path.lexists(actual):
            return
        nombre = "/".join(previas)
        if not os.path.isdir(actual):
            raise ErrorDePlan(f"{nombre} existe y no es una carpeta: no se puede crear {ruta}")
        if not _dentro(os.path.realpath(actual), real):
            raise ErrorDePlan(f"{nombre} sale de la raíz de la instancia: no se puede crear {ruta}")


def _revisar_choques(rutas):
    for clave, (ruta, generador) in rutas.items():
        partes = clave.split("/")
        for largo in range(1, len(partes)):
            padre = "/".join(partes[:largo])
            if padre in rutas:
                raise ErrorDePlan(f"{rutas[padre][0]} es un archivo y {ruta} lo usa como carpeta (generadores {rutas[padre][1]} y {generador})")


def planificar(spec, raiz):
    raiz = Path(raiz)
    if os.path.lexists(raiz) and not os.path.isdir(raiz):
        raise ErrorDePlan(f"la raíz {raiz} existe y no es una carpeta")
    vistas = {}
    acciones = []
    for generador in GENERADORES:
        for valor in generador.funcion(spec):
            ruta, contenido = _accion(valor, generador.nombre)
            clave = ruta.casefold()
            if clave in vistas:
                raise ErrorDePlan(f"la ruta {ruta} está repetida (generadores {vistas[clave][1]} y {generador.nombre})")
            vistas[clave] = (ruta, generador.nombre)
            _revisar_destino(raiz, ruta)
            acciones.append((ruta, contenido))
    _revisar_choques(vistas)
    return [Accion(ruta, contenido, YA_EXISTE if os.path.lexists(raiz / ruta) else CREAR) for ruta, contenido in acciones]


def aplicar(plan, raiz):
    raiz = Path(raiz)
    resultados = []
    try:
        os.makedirs(raiz, exist_ok=True)
    except OSError as error:
        raise ErrorDeAplicacion(f"no se pudo crear la raíz {raiz}: {error}", resultados)
    for accion in plan:
        if accion.modo != CREAR:
            resultados.append(Resultado(accion.ruta, YA_EXISTIA))
            continue
        destino = raiz / accion.ruta
        try:
            os.makedirs(destino.parent, exist_ok=True)
        except OSError as error:
            raise ErrorDeAplicacion(f"no se pudo crear la carpeta de {accion.ruta}: {error}", resultados)
        try:
            with open(destino, "xb") as archivo:
                archivo.write(accion.contenido)
        except FileExistsError:
            resultados.append(Resultado(accion.ruta, YA_EXISTIA))
        except OSError as error:
            raise ErrorDeAplicacion(f"no se pudo escribir {accion.ruta}: {error}", resultados)
        else:
            resultados.append(Resultado(accion.ruta, CREADO))
    return resultados


def _normal(linea):
    return linea.rstrip().strip("/")


def _lineas_que_faltan(contenido, destino):
    try:
        existentes = destino.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    presentes = {_normal(l) for l in existentes if l.strip()}
    pedidas = [l for l in contenido.decode("utf-8").splitlines() if l.strip()]
    return [l for l in pedidas if _normal(l) not in presentes]


def informe(plan, resultados, raiz, ensayo, con_resumen=True):
    contenidos = {a.ruta: a.contenido for a in plan}
    if ensayo:
        hechos = [(a.ruta, a.modo == YA_EXISTE) for a in plan]
        fraseo = ("crearía", "ya existe")
    else:
        hechos = [(r.ruta, r.estado == YA_EXISTIA) for r in resultados]
        fraseo = (CREADO, "ya existía")
    lineas = []
    for ruta, existe in hechos:
        lineas.append(f"{fraseo[1] if existe else fraseo[0]} {ruta}")
        if existe and ruta == convencion.GITIGNORE:
            for linea in _lineas_que_faltan(contenidos[ruta], Path(raiz) / ruta):
                lineas.append(f"falta en {convencion.GITIGNORE}: {linea}")
    if con_resumen:
        nuevos = sum(1 for _, existe in hechos if not existe)
        previos = len(hechos) - nuevos
        if ensayo:
            lineas.append(f"ensayo: {nuevos} se crearían, {previos} ya existen, no se escribió nada")
        else:
            lineas.append(f"resumen: {nuevos} creados, {previos} ya existían")
    return lineas


def _argumentos(argv):
    valores = {}
    ensayo = False
    i = 0
    while i < len(argv):
        argumento = argv[i]
        if argumento == "--ensayo" and not ensayo:
            ensayo = True
            i += 1
        elif argumento in ("--spec", "--raiz") and argumento not in valores and i + 1 < len(argv) and argv[i + 1] and not argv[i + 1].startswith("--"):
            valores[argumento] = argv[i + 1]
            i += 2
        else:
            return None
    if "--spec" not in valores:
        return None
    return Opciones(valores["--spec"], valores.get("--raiz"), ensayo)


def _error(mensaje):
    print("error: " + mensaje, file=sys.stderr)
    return 2


def principal(argv):
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    opciones = _argumentos(argv)
    if opciones is None:
        print(USO, file=sys.stderr)
        return 2
    plan = []
    raiz = Path(opciones.raiz) if opciones.raiz else Path(os.getcwd())
    try:
        spec = leer_spec(opciones.spec)
        validar_spec(spec)
        plan = planificar(spec, raiz)
        if opciones.ensayo:
            print("\n".join(informe(plan, None, raiz, True)))
            return 0
        resultados = aplicar(plan, raiz)
    except SpecInvalida as error:
        return _error(str(error))
    except ErrorDePlan as error:
        return _error(f"el plan no es válido: {error}")
    except ErrorDeAplicacion as error:
        if error.resultados:
            print("\n".join(informe(plan, error.resultados, raiz, False, con_resumen=False)))
        return _error(str(error))
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}")
    print("\n".join(informe(plan, resultados, raiz, False)))
    return 0


registrar_generador("config", _generar_config, claves=("config", "local"))


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
