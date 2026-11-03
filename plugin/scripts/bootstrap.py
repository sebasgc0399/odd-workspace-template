import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from collections import namedtuple
from pathlib import Path

import config_loader
from odd_ws import capas as convencion
from odd_ws.comun import COMANDO_RUTAS_DE_HOOKS, decidir_hooks, entorno_git

VERSION_DE_SPEC = 1
USO = "uso: bootstrap.py --spec <ruta.json> [--raiz <carpeta>] [--ensayo]"
CREAR, YA_EXISTE = "crear", "ya_existe"
CREADO, YA_EXISTIA = "creado", "ya_existia"
CLAVES_BASE = ("spec_version",)
LINEAS_DE_GITIGNORE = (config_loader.NOMBRE_LOCAL, convencion.ESTADO + "/")
CARACTERES_INVALIDOS = frozenset('<>:"|?*')
SUFIJOS_DE_PUERTO = "123456789¹²³"
RESERVADOS = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {"com" + n for n in SUFIJOS_DE_PUERTO}
    | {"lpt" + n for n in SUFIJOS_DE_PUERTO}
)
INTENTOS_DE_TEMPORAL = 5
PLAZO_DE_GIT = 60
SEPARADORES = re.compile(r"[\\/]+")

GIT_INIT, GIT_HOOKS = "init", "hooks_path"
EN_WINDOWS = os.name == "nt"
RAIZ_DEL_PLUGIN = Path(__file__).resolve().parents[1]

Accion = namedtuple("Accion", "ruta contenido modo permisos", defaults=(None,))
AccionDeGit = namedtuple("AccionDeGit", "tipo valor")
PasoDeGit = namedtuple("PasoDeGit", "tipo valor modo motivo")
Resultado = namedtuple("Resultado", "ruta estado")
Generador = namedtuple("Generador", "nombre funcion claves validar")
Opciones = namedtuple("Opciones", "spec raiz ensayo")

GENERADORES = []


class Plan(list):
    raiz_real = None
    acciones_git = ()
    pasos_git = ()


class Resultados(list):
    def __init__(self, *argumentos):
        super().__init__(*argumentos)
        self.sobrantes = []
        self.git = []


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
        return (json.dumps(objeto, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except ValueError as error:
        raise SpecInvalida(f"la spec trae un valor que no se puede escribir como JSON válido en UTF-8: {error}")


def leer_spec(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise SpecInvalida(f"no se puede leer la spec {ruta} como JSON: {error}")


def _cargar_en_temporal(contenidos, prefijo):
    with tempfile.TemporaryDirectory(prefix="bootstrap-") as carpeta:
        copia = Path(carpeta)
        for nombre, datos in contenidos.items():
            (copia / nombre).write_bytes(datos)
        try:
            config_loader.cargar(copia)
            config_loader.conocimiento(copia)
        except config_loader.ConfigRota as error:
            raise SpecInvalida(f"{prefijo}: {error}")


def _validar_config(spec, raiz):
    contenidos = {
        config_loader.NOMBRE: serializar(spec["config"]),
        config_loader.NOMBRE_LOCAL: serializar(spec.get("local", {})),
    }
    _cargar_en_temporal(contenidos, "la config no es válida")
    if raiz is None:
        return
    previos = {}
    for nombre in contenidos:
        destino = Path(raiz) / nombre
        if os.path.lexists(destino):
            try:
                previos[nombre] = destino.read_bytes()
            except OSError as error:
                raise SpecInvalida(f"la config no es válida: {nombre} ya existe en la instancia y no se puede leer: {error.strerror or error}")
    if previos:
        _cargar_en_temporal({**contenidos, **previos}, "la config no es válida (combinada con lo que ya existe en la instancia)")


def _validar_local(local):
    repos = local.get("repos")
    if repos is None:
        return
    if not isinstance(repos, dict):
        raise SpecInvalida("local.repos debe ser un objeto con un repo por clave")
    for clave, valores in repos.items():
        if not isinstance(valores, dict):
            raise SpecInvalida(f"local.repos.{clave} debe ser un objeto con path")
        if "path" not in valores:
            continue
        ruta = valores["path"]
        if not isinstance(ruta, str):
            raise SpecInvalida(f"local.repos.{clave}.path debe ser un texto con una ruta absoluta, no {ruta!r}")
        if not os.path.isabs(ruta):
            raise SpecInvalida(f"local.repos.{clave}.path debe ser una ruta absoluta, no {ruta!r}")


def _canonico(valor):
    return json.dumps(valor, sort_keys=True, ensure_ascii=False)


def _objeto_existente(ruta):
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def _coincidir_con_lo_existente(spec, raiz):
    if raiz is None:
        return
    config = _objeto_existente(Path(raiz) / config_loader.NOMBRE)
    if config is not None and _canonico(config) != _canonico(spec["config"]):
        raise SpecInvalida(
            f"la config de la spec no es la de {raiz}/{config_loader.NOMBRE}, que ya existe: el bootstrap no la reescribe, "
            "así que la spec tiene que traerla tal cual (o cambiala a mano antes)")
    local = _objeto_existente(Path(raiz) / config_loader.NOMBRE_LOCAL)
    if local is not None and _canonico({k: v for k, v in local.items() if k != "plugin_root"}) != _canonico(spec.get("local", {})):
        raise SpecInvalida(
            f"el local de la spec no es el de {raiz}/{config_loader.NOMBRE_LOCAL} (sin plugin_root), que ya existe: "
            "el bootstrap no lo reescribe, así que la spec tiene que traerlo tal cual")


def validar_spec(spec, raiz=None):
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
    _validar_local(local)
    _coincidir_con_lo_existente(spec, raiz)
    for generador in GENERADORES:
        if generador.validar is not None:
            generador.validar(spec)
    _validar_config(spec, raiz)


def _generar_config(spec):
    return [
        (config_loader.NOMBRE, serializar(spec["config"])),
        (config_loader.NOMBRE_LOCAL, serializar({**spec.get("local", {}), "plugin_root": str(RAIZ_DEL_PLUGIN)})),
        (convencion.GITIGNORE, "".join(linea + "\n" for linea in LINEAS_DE_GITIGNORE)),
    ]


def _ruta_relativa(ruta):
    if not isinstance(ruta, str) or "\\" in ruta:
        raise ErrorDePlan(f"la ruta {ruta!r} debe ser un texto relativo a la raíz, con /")
    for segmento in ruta.split("/"):
        if segmento in ("", ".", "..") or segmento != segmento.rstrip(" ."):
            raise ErrorDePlan(f"la ruta {ruta!r} debe ser relativa a la raíz, sin '.', '..', segmentos vacíos ni segmentos que terminen en punto o espacio")
        if any(c in CARACTERES_INVALIDOS or ord(c) < 32 for c in segmento):
            raise ErrorDePlan(f"la ruta {ruta!r} trae caracteres que Windows no admite en un nombre (<>:\"|?* o de control)")
        if segmento.split(".", 1)[0].rstrip(" ").casefold() in RESERVADOS:
            raise ErrorDePlan(f"la ruta {ruta!r} usa un nombre reservado de Windows ({segmento})")
    return ruta


def _permisos(valor, ruta):
    if valor is None:
        return None
    if type(valor) is not int or not 0 <= valor <= 0o777:
        raise ErrorDePlan(f"los permisos de {ruta} deben ser un entero entre 0 y 0o777, no {valor!r}")
    if not valor & 0o200:
        raise ErrorDePlan(f"los permisos de {ruta} deben incluir la escritura del dueño (0o200), no {oct(valor)}")
    return valor


def _paso_de_git(valor, generador):
    if valor.tipo not in (GIT_INIT, GIT_HOOKS):
        raise ErrorDePlan(f"el generador {generador} pidió una acción de git desconocida: {valor.tipo!r}")
    if valor.tipo == GIT_INIT and valor.valor is not None:
        raise ErrorDePlan("la acción git init no lleva valor")
    if valor.tipo == GIT_HOOKS:
        _ruta_relativa(valor.valor)
        if valor.valor.startswith("-"):
            raise ErrorDePlan(f"el valor de core.hooksPath {valor.valor!r} no puede empezar con -")
    return valor


def _accion(valor, generador):
    if not isinstance(valor, (tuple, list)) or len(valor) not in (2, 3):
        raise ErrorDePlan(f"el generador {generador} devolvió una acción que no es (ruta, contenido[, permisos]): {valor!r}")
    ruta, contenido, *resto = valor
    ruta = _ruta_relativa(ruta)
    permisos = _permisos(resto[0] if resto else None, ruta)
    if isinstance(contenido, str):
        try:
            contenido = contenido.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ErrorDePlan(f"el contenido de {ruta} no se puede escribir en UTF-8: {error}")
    if not isinstance(contenido, bytes):
        raise ErrorDePlan(f"el contenido de {ruta} debe ser un texto o bytes")
    return ruta, contenido, permisos


def _dentro(ruta, carpeta):
    ruta, carpeta = os.path.normcase(ruta), os.path.normcase(carpeta)
    try:
        return os.path.commonpath([ruta, carpeta]) == carpeta
    except ValueError:
        return False


def _revisar_destino(raiz, ruta, real=None):
    real = real or os.path.realpath(raiz)
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
    acciones_git = []
    for generador in GENERADORES:
        for valor in generador.funcion(spec):
            if isinstance(valor, AccionDeGit):
                if any(a.tipo == valor.tipo for a in acciones_git):
                    raise ErrorDePlan(f"la acción de git {valor.tipo} está repetida")
                acciones_git.append(_paso_de_git(valor, generador.nombre))
                continue
            ruta, contenido, permisos = _accion(valor, generador.nombre)
            clave = ruta.casefold()
            if clave in vistas:
                raise ErrorDePlan(f"la ruta {ruta} está repetida (generadores {vistas[clave][1]} y {generador.nombre})")
            vistas[clave] = (ruta, generador.nombre)
            _revisar_destino(raiz, ruta)
            acciones.append((ruta, contenido, permisos))
    _revisar_choques(vistas)
    plan = Plan(Accion(ruta, contenido, YA_EXISTE if os.path.lexists(raiz / ruta) else CREAR, permisos) for ruta, contenido, permisos in acciones)
    plan.raiz_real = os.path.realpath(raiz)
    plan.acciones_git = acciones_git
    plan.pasos_git = _planificar_git(raiz, acciones_git)
    return plan


EstadoGit = namedtuple("EstadoGit", "disponible toplevel ilegible detalle")


def _git(argumentos):
    try:
        resultado = subprocess.run(["git", *argumentos], capture_output=True, stdin=subprocess.DEVNULL, env=entorno_git(), timeout=PLAZO_DE_GIT)
    except (FileNotFoundError, PermissionError):
        return None
    except subprocess.TimeoutExpired:
        return 124, "", f"git no respondió en {PLAZO_DE_GIT} segundos"
    return resultado.returncode, resultado.stdout.decode("utf-8", "replace").strip(), resultado.stderr.decode("utf-8", "replace").strip()


def _carpeta_existente(raiz):
    actual = Path(os.path.abspath(raiz))
    while not os.path.isdir(actual) and actual.parent != actual:
        actual = actual.parent
    return actual


def _hay_git_arriba(carpeta):
    return any(os.path.lexists(p / ".git") for p in (carpeta, *carpeta.parents))


def _consultar_repo(raiz):
    carpeta = _carpeta_existente(raiz)
    respuesta = _git(["-C", str(carpeta), "rev-parse", "--show-toplevel"])
    if respuesta is None:
        return EstadoGit(False, None, False, "")
    codigo, salida, error = respuesta
    if codigo == 0 and salida:
        return EstadoGit(True, Path(salida), False, "")
    if _hay_git_arriba(carpeta):
        return EstadoGit(True, None, True, error or salida)
    return EstadoGit(True, None, False, "")


def _es_la_raiz(toplevel, raiz):
    return config_loader.canonica(toplevel) == config_loader.canonica(raiz)


def _decidir_init(raiz, estado):
    if not estado.disponible:
        return PasoDeGit(GIT_INIT, None, "no_disponible", "git init: no se hizo; git no está instalado")
    if estado.ilegible:
        detalle = f" ({estado.detalle})" if estado.detalle else ""
        return PasoDeGit(GIT_INIT, None, "omitir", f"git init: no se hizo; hay un repo git arriba de la raíz que git no pudo leer{detalle}")
    if estado.toplevel is None:
        return PasoDeGit(GIT_INIT, None, "hacer", "git init: se haría (la raíz no está en ningún repo)")
    if _es_la_raiz(estado.toplevel, raiz):
        return PasoDeGit(GIT_INIT, None, "omitir", "git init: no hace falta, la raíz ya es un repo git")
    return PasoDeGit(GIT_INIT, None, "omitir", f"git init: no se hizo; la raíz está dentro del repo {estado.toplevel}")


def _valor_de_hooks(raiz):
    respuesta = _git(["-C", str(raiz), "config", "--local", "--includes", "--get", "core.hooksPath"])
    if respuesta is None:
        return "error", "git no está instalado"
    codigo, salida, error = respuesta
    if codigo == 0:
        return "valor", salida
    if codigo == 1:
        return "sin_valor", ""
    return "error", error or salida


def _decision_de_hooks(raiz):
    respuesta = _git(["-C", str(raiz), *COMANDO_RUTAS_DE_HOOKS])
    return decidir_hooks(raiz, respuesta[1] if respuesta is not None and respuesta[0] == 0 else "")


def _decidir_hooks(raiz, valor, estado, init_pendiente):
    def omitir(motivo, modo="omitir"):
        return PasoDeGit(GIT_HOOKS, valor, modo, f"core.hooksPath: no se tocó; {motivo}")

    if not estado.disponible:
        return omitir("git no está instalado", "no_disponible")
    if init_pendiente:
        return PasoDeGit(GIT_HOOKS, valor, "hacer", f"core.hooksPath = {valor}: se configuraría (--local)")
    if estado.ilegible:
        return omitir("hay un repo git arriba de la raíz que git no pudo leer")
    if estado.toplevel is None:
        return omitir("la raíz no está en un repo git")
    if not _es_la_raiz(estado.toplevel, raiz):
        return omitir(f"la raíz está dentro del repo {estado.toplevel}, que no es la instancia")
    lectura, actual = _valor_de_hooks(raiz)
    if lectura == "error":
        return omitir(f"no se pudo leer su valor ({actual})")
    if lectura == "valor":
        if actual == valor:
            return PasoDeGit(GIT_HOOKS, valor, "omitir", f"core.hooksPath = {valor}: ya estaba")
        return PasoDeGit(GIT_HOOKS, valor, "omitir", f"core.hooksPath = {actual or '(vacío)'}: no se tocó; el pre-commit no va a correr")
    decision = _decision_de_hooks(raiz)
    if not decision.puede:
        return omitir(decision.motivo)
    return PasoDeGit(GIT_HOOKS, valor, "hacer", f"core.hooksPath = {valor}: se configuraría (--local)")


def _decidir(accion, raiz, estado, init_pendiente):
    if accion.tipo == GIT_INIT:
        return _decidir_init(raiz, estado)
    return _decidir_hooks(raiz, accion.valor, estado, init_pendiente)


def _planificar_git(raiz, acciones):
    if not acciones:
        return []
    estado = _consultar_repo(raiz)
    pasos = []
    init_pendiente = False
    for accion in acciones:
        paso = _decidir(accion, raiz, estado, init_pendiente)
        init_pendiente = init_pendiente or (accion.tipo == GIT_INIT and paso.modo == "hacer")
        pasos.append(paso)
    return pasos


def _ejecutar_paso(paso, raiz):
    if paso.tipo == GIT_INIT:
        etiqueta, argumentos, exito = "git init", ["-C", str(raiz), "init", "-q"], "git init: repo creado"
    else:
        etiqueta = f"core.hooksPath = {paso.valor}"
        argumentos = ["-C", str(raiz), "config", "--local", "core.hooksPath", paso.valor]
        exito = f"core.hooksPath = {paso.valor}: configurado (--local)"
    respuesta = _git(argumentos)
    if respuesta is None:
        return f"{etiqueta}: no se hizo; git no está instalado"
    codigo, salida, error = respuesta
    if codigo != 0:
        return f"{etiqueta}: falló: {error or salida or 'código ' + str(codigo)}"
    return exito


def _aplicar_git(plan, raiz, referencia, resultados):
    for accion in getattr(plan, "acciones_git", ()):
        if os.path.normcase(os.path.realpath(raiz)) != os.path.normcase(referencia):
            raise ErrorDeAplicacion(f"la raíz {raiz} apunta a otro lado que cuando se armó el plan", resultados)
        paso = _decidir(accion, raiz, _consultar_repo(raiz), False)
        resultados.git.append(_ejecutar_paso(paso, raiz) if paso.modo == "hacer" else paso.motivo)


def _confirmar(raiz, ruta, referencia):
    if os.path.normcase(os.path.realpath(raiz)) != os.path.normcase(referencia):
        raise ErrorDePlan(f"la raíz {raiz} apunta a otro lado que cuando se armó el plan")
    _revisar_destino(raiz, ruta, referencia)


def _temporal_libre(destino):
    for _ in range(INTENTOS_DE_TEMPORAL):
        candidato = destino.parent / f".{destino.name}.{uuid.uuid4().hex}.tmp"
        if not os.path.lexists(candidato):
            return candidato
    raise OSError(f"no se encontró un nombre libre para el temporal de {destino.name}")


def _publicar(raiz, accion, raiz_real=None, sobrantes=None):
    referencia = raiz_real or os.path.realpath(raiz)
    destino = raiz / accion.ruta
    _confirmar(raiz, accion.ruta, referencia)
    os.makedirs(destino.parent, exist_ok=True)
    _confirmar(raiz, accion.ruta, referencia)
    temporal = _temporal_libre(destino)
    archivo = open(temporal, "xb")
    try:
        with archivo:
            archivo.write(accion.contenido)
        if accion.permisos is not None:
            os.chmod(temporal, accion.permisos)
        _confirmar(raiz, accion.ruta, referencia)
        try:
            os.link(temporal, destino)
        except FileExistsError:
            return YA_EXISTIA
        return CREADO
    finally:
        try:
            os.unlink(temporal)
        except FileNotFoundError:
            pass
        except OSError:
            if sobrantes is not None:
                sobrantes.append((temporal.relative_to(raiz).as_posix(), accion.ruta))


def aplicar(plan, raiz):
    raiz = Path(raiz)
    resultados = Resultados()
    declarada = getattr(plan, "raiz_real", None)
    actual = os.path.realpath(raiz)
    if declarada is not None and os.path.normcase(actual) != os.path.normcase(declarada):
        raise ErrorDeAplicacion(f"la raíz {raiz} apunta a otro lado que cuando se armó el plan", resultados)
    referencia = declarada or actual
    try:
        os.makedirs(raiz, exist_ok=True)
    except OSError as error:
        raise ErrorDeAplicacion(f"no se pudo crear la raíz {raiz}: {error}", resultados)
    for accion in plan:
        if accion.modo != CREAR:
            resultados.append(Resultado(accion.ruta, YA_EXISTIA))
            continue
        try:
            estado = _publicar(raiz, accion, referencia, resultados.sobrantes)
        except ErrorDePlan as error:
            raise ErrorDeAplicacion(str(error), resultados)
        except OSError as error:
            raise ErrorDeAplicacion(f"no se pudo escribir {accion.ruta}: {error}", resultados)
        resultados.append(Resultado(accion.ruta, estado))
    _aplicar_git(plan, raiz, referencia, resultados)
    return resultados


def _normal(linea):
    return linea.rstrip().strip("/")


def _pedidas(contenido):
    return [l for l in contenido.decode("utf-8").splitlines() if l.strip()]


def _cubre(existentes, pedida):
    nombre = _normal(pedida)
    es_carpeta = pedida.rstrip().endswith("/")
    for linea in existentes:
        patron = _normal(linea)
        if not patron:
            continue
        solo_carpeta = linea.rstrip().endswith("/")
        if nombre.startswith(patron + "/") or (nombre == patron and (es_carpeta or not solo_carpeta)):
            return True
    return False


def _lineas_que_faltan(pedidas, destino):
    existentes = destino.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    return [l for l in pedidas if not _cubre(existentes, l)]


def _motivo(error, destino):
    return "es una carpeta" if destino.is_dir() else (error.strerror or str(error))


def informe(plan, resultados, raiz, ensayo, con_resumen=True):
    contenidos = {a.ruta: a.contenido for a in plan}
    if ensayo:
        hechos = [(a.ruta, a.modo == YA_EXISTE) for a in plan]
        fraseo = ("crearía", "ya existe")
    else:
        hechos = [(r.ruta, r.estado == YA_EXISTIA) for r in resultados]
        fraseo = (CREADO, "ya existía")
    ejecutables = {a.ruta for a in plan if a.permisos and a.permisos & 0o111}
    lineas = []
    for ruta, existe in hechos:
        lineas.append(f"{fraseo[1] if existe else fraseo[0]} {ruta}")
        if EN_WINDOWS and not existe and ruta in ejecutables:
            lineas.append(f"al commitear, marcalo ejecutable: git add --chmod=+x {ruta}")
        if existe and ruta == convencion.GITIGNORE:
            destino = Path(raiz) / ruta
            pedidas = _pedidas(contenidos[ruta])
            try:
                faltan = _lineas_que_faltan(pedidas, destino)
            except OSError as error:
                lineas.append(f"no se pudo leer {convencion.GITIGNORE}: {_motivo(error, destino)}; revisá a mano que ignore: {', '.join(pedidas)}")
                continue
            for linea in faltan:
                lineas.append(f"falta en {convencion.GITIGNORE}: {linea}")
    for temporal, destino in getattr(resultados, "sobrantes", ()):
        lineas.append(f"no se pudo borrar {temporal}: borralo a mano (es una copia de {destino})")
    if ensayo:
        lineas.extend(paso.motivo for paso in getattr(plan, "pasos_git", ()))
    else:
        lineas.extend(getattr(resultados, "git", ()))
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


def resolver_raiz(texto, cwd):
    if texto is None:
        return Path(config_loader.encontrar_raiz(cwd) or cwd)
    for componente in SEPARADORES.split(texto):
        if componente not in ("", ".", "..") and componente != componente.rstrip(" ."):
            raise ErrorDePlan(f"la raíz {texto!r} tiene un componente que termina en punto o espacio, que Windows recorta")
    raiz = Path(texto)
    instancia = config_loader.encontrar_raiz(raiz)
    if instancia is not None and config_loader.canonica(instancia) != config_loader.canonica(raiz):
        raise ErrorDePlan(f"la raíz {raiz} está dentro de la instancia {instancia}: usá esa carpeta como raíz o una fuera de ella")
    return raiz


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
    raiz = None
    try:
        raiz = resolver_raiz(opciones.raiz, Path(os.getcwd()))
        spec = leer_spec(opciones.spec)
        validar_spec(spec, raiz)
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
        if error.resultados or getattr(error.resultados, "sobrantes", ()):
            print("\n".join(informe(plan, error.resultados, raiz, False, con_resumen=False)))
        return _error(str(error))
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}")
    print("\n".join(informe(plan, resultados, raiz, False)))
    return 0


registrar_generador("config", _generar_config, claves=("config", "local"))


def registrar_estandar():
    import bootstrap_agentes
    import bootstrap_instalacion
    import bootstrap_reglas
    import bootstrap_textos

    registrar_generador("agentes", bootstrap_agentes.generar, claves=bootstrap_agentes.CLAVES)
    registrar_generador("reglas", bootstrap_reglas.generar, claves=bootstrap_reglas.CLAVES, validar=bootstrap_reglas.validar)
    registrar_generador("textos", bootstrap_textos.generar, claves=bootstrap_textos.CLAVES, validar=bootstrap_textos.validar)
    registrar_generador("instalacion", bootstrap_instalacion.generar, claves=bootstrap_instalacion.CLAVES)


if __name__ == "__main__":
    sys.modules.setdefault("bootstrap", sys.modules[__name__])
    registrar_estandar()
    sys.exit(principal(sys.argv[1:]))
