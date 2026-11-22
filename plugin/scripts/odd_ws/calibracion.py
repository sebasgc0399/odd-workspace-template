import functools
import hashlib
import json
import os
import re
import shutil
import sys
from collections import namedtuple

from odd_ws import capas as convencion
from odd_ws.paquetes import HUELLA_RE, NOMBRE_RE

RUTA = convencion.CALIBRACION
DISPUTAS = convencion.REGISTRO + "/disputas"
VERSION = 1
MODOS = ("aviso", "bloqueo")
CLAVE = "aviso_por"
CLAVES_DEL_REGISTRO = ("version", "capas")
OPCIONALES_DEL_REGISTRO = ("paquetes",)
CLAVES_DE_UNA_REGLA = ("huella", "atrapa_su_sembrado", "aciertos", "aciertos_en_bloqueo", "archivos_del_corpus", "corpus", "fecha")
CLAVES_DEL_CORPUS = ("repo", "commit", "ruta")
CLAVES_DEL_SEMBRADO = ("ruta", "texto")
FALLAS_DEL_MODULO = (Exception, SystemExit)
CONTADORES = ("aciertos", "aciertos_en_bloqueo", "archivos_del_corpus")
COMMIT_RE = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
FECHA_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
SIN_CARPETA = "<carpeta>"
REGLAS_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reglas.py")
PYTHONS_DEL_PATH = ("python", "python3") if os.name == "nt" else ("python3",)
PYTHON_DE_RESPALDO = "python3"

SIN_CALIBRAR = "sin calibrar"
VIEJA = "calibración vieja"
NO_PASO = "no pasó la calibración"
ROTO = "registro de calibración roto"
MODO_INVALIDO = "modo inválido"
ID_INVALIDO = "id inválido"
DISPUTADA = "disputada"
DISPUTAS_ILEGIBLES = "disputas ilegibles"

Fuente = namedtuple("Fuente", ("capa", "huella", "sembrados", "paquete"), defaults=(None,))
Registro = namedtuple("Registro", ("capas", "roto", "paquetes", "disputas", "disputas_ilegibles"), defaults=({}, frozenset(), False))
Calibradas = namedtuple("Calibradas", ("capas", "paquetes"))


class RegistroRoto(Exception):
    pass


def huella(contenido):
    return "sha256:" + hashlib.sha256(contenido.replace(b"\r\n", b"\n")).hexdigest()


def huella_del_archivo(ruta):
    with open(ruta, "rb") as f:
        return huella(f.read())


def _texto(valor):
    return isinstance(valor, str) and bool(valor.strip())


def _ruta_del_sembrado(valor):
    return _ruta_relativa(valor) and all(parte.strip() not in ("", ".", "..") for parte in valor.split("/"))


def _sembrado(sembrado):
    if _texto(sembrado):
        return sembrado
    if (isinstance(sembrado, dict) and set(sembrado) == set(CLAVES_DEL_SEMBRADO) and _ruta_del_sembrado(sembrado["ruta"])
            and _texto(sembrado["texto"])):
        return {"ruta": sembrado["ruta"], "texto": sembrado["texto"]}
    return None


def sembrados(modulo):
    try:
        reglas = getattr(modulo, "REGLAS", None)
        encontrados = {}
        for regla in () if reglas is None else reglas:
            id_ = getattr(regla, "id", None)
            if isinstance(id_, str) and id_:
                encontrados[id_] = _sembrado(getattr(regla, "sembrado", None))
        return encontrados
    except FALLAS_DEL_MODULO:
        return {}


def fuente_del_modulo(capa, modulo, ruta):
    try:
        actual = huella_del_archivo(ruta)
    except OSError:
        actual = None
    return Fuente(capa, actual, sembrados(modulo))


def fuente_del_paquete(paquete, modulo):
    return Fuente(paquete.capa, paquete.huella, sembrados(modulo), paquete.nombre)


def _claves(datos, claves, donde, opcionales=()):
    if not isinstance(datos, dict):
        raise RegistroRoto(f"{donde or 'el registro'} debe ser un objeto")
    prefijo = donde + "." if donde else ""
    sobran = sorted(set(datos) - set(claves) - set(opcionales))
    if sobran:
        raise RegistroRoto(f"{prefijo}{sobran[0]} no es una clave conocida ({', '.join(claves + opcionales)})")
    faltan = [clave for clave in claves if clave not in datos]
    if faltan:
        raise RegistroRoto(f"falta {prefijo}{faltan[0]}")


def _contador(valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def _ruta_relativa(valor):
    return (isinstance(valor, str) and bool(valor) and not valor.startswith("/") and "\\" not in valor and ":" not in valor
            and ".." not in valor.split("/"))


def _corpus(corpus, donde):
    _claves(corpus, CLAVES_DEL_CORPUS, donde)
    repo, commit = corpus["repo"], corpus["commit"]
    if repo is not None and not (isinstance(repo, str) and repo.strip()):
        raise RegistroRoto(f"{donde}.repo debe ser el nombre de un repo de la config o null")
    if commit is not None and not (isinstance(commit, str) and COMMIT_RE.fullmatch(commit)):
        raise RegistroRoto(f"{donde}.commit debe ser un hash en hexadecimal en minúsculas o null")
    if not _ruta_relativa(corpus["ruta"]):
        raise RegistroRoto(f"{donde}.ruta debe ser una ruta relativa con /, sin ..")


def _regla(datos, donde):
    _claves(datos, CLAVES_DE_UNA_REGLA, donde)
    if not isinstance(datos["huella"], str) or not HUELLA_RE.fullmatch(datos["huella"]):
        raise RegistroRoto(f"{donde}.huella debe ser sha256:<64 hexadecimales en minúsculas>")
    if not isinstance(datos["atrapa_su_sembrado"], bool):
        raise RegistroRoto(f"{donde}.atrapa_su_sembrado debe ser true o false")
    for clave in CONTADORES:
        if not _contador(datos[clave]):
            raise RegistroRoto(f"{donde}.{clave} debe ser un entero de 0 en adelante")
    _corpus(datos["corpus"], donde + ".corpus")
    if not isinstance(datos["fecha"], str) or not FECHA_RE.fullmatch(datos["fecha"]):
        raise RegistroRoto(f"{donde}.fecha debe ser AAAA-MM-DD")


def _reglas(reglas, donde):
    if not isinstance(reglas, dict):
        raise RegistroRoto(f"{donde} debe ser un objeto con una regla por clave")
    for id_, regla in reglas.items():
        _regla(regla, f"{donde}.{id_}")


def validar(datos):
    _claves(datos, CLAVES_DEL_REGISTRO, "", OPCIONALES_DEL_REGISTRO)
    version = datos["version"]
    if isinstance(version, bool) or version != VERSION:
        raise RegistroRoto(f"version {version!r} no es la que entiende este plugin ({VERSION})")
    capas = datos["capas"]
    if not isinstance(capas, dict):
        raise RegistroRoto("capas debe ser un objeto con una capa por clave")
    for capa, reglas in capas.items():
        _reglas(reglas, f"capas.{capa}")
    de_paquetes = datos.get("paquetes", {})
    if not isinstance(de_paquetes, dict):
        raise RegistroRoto("paquetes debe ser un objeto con una capa por clave")
    for capa, de_la_capa in de_paquetes.items():
        if not isinstance(de_la_capa, dict):
            raise RegistroRoto(f"paquetes.{capa} debe ser un objeto con un paquete por clave")
        for nombre, reglas in de_la_capa.items():
            if not NOMBRE_RE.fullmatch(nombre):
                raise RegistroRoto(f"paquetes.{capa}.{nombre} no es el nombre de un paquete")
            _reglas(reglas, f"paquetes.{capa}.{nombre}")
    return Calibradas(capas, de_paquetes)


def cargar(raiz):
    ruta = os.path.join(str(raiz), RUTA)
    if not os.path.lexists(ruta):
        return Calibradas({}, {})
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.loads(f.read())
    except (OSError, ValueError, RecursionError) as error:
        raise RegistroRoto(f"no se puede leer como JSON: {error}")
    return validar(datos)


def disputas(raiz):
    ruta = os.path.join(str(raiz), *DISPUTAS.split("/"))
    if not os.path.lexists(ruta):
        return frozenset()
    nombres = (os.path.splitext(nombre) for nombre in os.listdir(ruta))
    return frozenset(base.upper() for base, extension in nombres if base and extension.lower() == ".md")


def registro(raiz):
    try:
        abiertas, ilegibles = disputas(raiz), False
    except OSError:
        abiertas, ilegibles = frozenset(), True
    try:
        guardadas = cargar(raiz)
    except RegistroRoto as error:
        return Registro({}, str(error), {}, abiertas, ilegibles)
    return Registro(guardadas.capas, None, guardadas.paquetes, abiertas, ilegibles)


def _ordenada(regla):
    ordenada = {clave: regla[clave] for clave in CLAVES_DE_UNA_REGLA}
    ordenada["corpus"] = {clave: regla["corpus"][clave] for clave in CLAVES_DEL_CORPUS}
    return ordenada


def _ordenadas(reglas):
    return {id_: _ordenada(reglas[id_]) for id_ in sorted(reglas)}


def escribir(raiz, capas, de_paquetes=None):
    datos = {"version": VERSION, "capas": {capa: _ordenadas(capas[capa]) for capa in sorted(capas)}}
    de_paquetes = {capa: {nombre: _ordenadas(de_la_capa[nombre]) for nombre in sorted(de_la_capa)}
                   for capa, de_la_capa in sorted((de_paquetes or {}).items()) if de_la_capa}
    if de_paquetes:
        datos["paquetes"] = de_paquetes
    validar(datos)
    ruta = os.path.join(str(raiz), RUTA)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    temporal = ruta + ".nuevo"
    try:
        with open(temporal, "wb") as f:
            f.write((json.dumps(datos, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        os.replace(temporal, ruta)
    finally:
        if os.path.lexists(temporal):
            os.remove(temporal)


def _entre_comillas(ruta):
    return '"%s"' % (ruta + "\\" if ruta.endswith("\\") else ruta)


@functools.lru_cache(maxsize=8)
def _interprete(path, ejecutable):
    for nombre in PYTHONS_DEL_PATH:
        if shutil.which(nombre, path=path):
            return nombre
    return _entre_comillas(ejecutable) if ejecutable else PYTHON_DE_RESPALDO


def interprete():
    return _interprete(os.environ.get("PATH"), sys.executable or "")


def _carpeta(id_, reglas, repos, otras=(), repos_de_la_capa=()):
    for calibrada in ([reglas[id_]] if id_ in reglas else []) + list(reglas.values()) + list(otras):
        repo = repos.get(calibrada["corpus"]["repo"]) if calibrada["corpus"]["repo"] else None
        if isinstance(repo, dict) and repo.get("path"):
            return _entre_comillas(os.path.normpath(os.path.join(repo["path"], *calibrada["corpus"]["ruta"].split("/"))))
    primero = repos.get(repos_de_la_capa[0]) if repos_de_la_capa else None
    if isinstance(primero, dict) and primero.get("path"):
        return _entre_comillas(os.path.normpath(primero["path"]))
    return SIN_CARPETA


def _repos_de_la_capa(capas, capa):
    declarada = (capas or {}).get(capa)
    return list(declarada.get("repos") or []) if isinstance(declarada, dict) else []


def _aviso(motivo, accion):
    return {"motivo": motivo, "accion": accion}


def _motivo(id_, fuente, actual, repos, capas):
    de_la_capa = actual.capas.get(fuente.capa) or {}
    if fuente.paquete is None:
        reglas, otras, donde = de_la_capa, (), ""
    else:
        reglas = (actual.paquetes.get(fuente.capa) or {}).get(fuente.paquete) or {}
        otras, donde = de_la_capa.values(), " (en el repo del paquete %s, con una etiqueta nueva)" % fuente.paquete
    carpeta = _carpeta(id_, reglas, repos, otras, _repos_de_la_capa(capas, fuente.capa))
    comando = "`%s %s --calibrar %s %s --guardar`" % (interprete(), _entre_comillas(REGLAS_PY), fuente.capa, carpeta)
    corregir = "corregir los hallazgos y después correr %s" % comando
    if actual.disputas_ilegibles:
        return _aviso(DISPUTAS_ILEGIBLES, "para que bloquee, %s tiene que ser una carpeta legible, con un <ID>.md por disputa abierta"
                      % DISPUTAS)
    if str(id_).upper() in actual.disputas:
        return _aviso(DISPUTADA, "se cierra borrando %s/%s.md en el commit que arregla el chequeo, y después correr %s"
                      % (DISPUTAS, id_, comando))
    if actual.roto is not None:
        return _aviso(ROTO, "para que bloquee, arreglar o borrar %s, %s" % (RUTA, corregir))
    if not fuente.sembrados.get(id_):
        return _aviso(SIN_CALIBRAR, "para que bloquee, declarar su `sembrado` en REGLAS%s, %s" % (donde, corregir))
    calibrada = reglas.get(id_)
    if calibrada is None:
        return _aviso(SIN_CALIBRAR, "para que bloquee, %s" % corregir)
    if calibrada["huella"] != fuente.huella:
        return _aviso(VIEJA, "para que bloquee, %s" % corregir)
    if not calibrada["atrapa_su_sembrado"]:
        return _aviso(NO_PASO, "no atrapa su sembrado: para que bloquee, arreglar la regla%s y correr %s" % (donde, comando))
    if calibrada["aciertos_en_bloqueo"]:
        return _aviso(NO_PASO, "%d aciertos en bloqueo en el corpus: para que bloquee, corregir esos hallazgos, o arreglar la regla%s si "
                      "son falsos positivos, y después correr %s" % (calibrada["aciertos_en_bloqueo"], donde, comando))
    return None


def modo_efectivo(hallazgo, fuente, actual, repos, capas=None):
    propio = {k: v for k, v in hallazgo.items() if k != CLAVE} if CLAVE in hallazgo else hallazgo
    modo = propio.get("modo")
    if not (isinstance(modo, str) and modo in MODOS):
        return dict(propio, modo="aviso", **{CLAVE: _aviso(MODO_INVALIDO, "el módulo tiene que devolver modo aviso o bloqueo")})
    if modo == "aviso":
        return propio
    if fuente is None:
        return dict(propio, modo="aviso", **{CLAVE: _aviso(SIN_CALIBRAR, "no viene de un módulo de capa ni de un paquete")})
    id_ = propio.get("id")
    if not (isinstance(id_, str) and id_):
        return dict(propio, modo="aviso", **{CLAVE: _aviso(ID_INVALIDO, "el hallazgo tiene que traer el id de su regla, como texto")})
    motivo = _motivo(id_, fuente, actual, repos, capas)
    return propio if motivo is None else dict(propio, modo="aviso", **{CLAVE: motivo})


def aplicar(grupos, raiz, repos, capas=None):
    pide_bloqueo = any(fuente is not None and h.get("modo") == "bloqueo" for fuente, hallazgos in grupos for h in hallazgos)
    actual = registro(raiz) if pide_bloqueo else Registro({}, None)
    return [modo_efectivo(h, fuente, actual, repos, capas) for fuente, hallazgos in grupos for h in hallazgos]


def sufijo(hallazgo):
    aviso = hallazgo.get(CLAVE)
    if not isinstance(aviso, dict) or not {"motivo", "accion"} <= set(aviso):
        return ""
    return " (aviso: %s; %s)" % (aviso["motivo"], aviso["accion"])
