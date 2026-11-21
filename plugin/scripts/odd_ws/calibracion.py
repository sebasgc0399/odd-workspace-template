import hashlib
import json
import os
import re
from collections import namedtuple

from odd_ws import capas as convencion
from odd_ws.paquetes import HUELLA_RE

RUTA = convencion.CALIBRACION
VERSION = 1
MODOS = ("aviso", "bloqueo")
CLAVE = "aviso_por"
CLAVES_DEL_REGISTRO = ("version", "capas")
CLAVES_DE_UNA_REGLA = ("huella", "atrapa_su_sembrado", "aciertos", "aciertos_en_bloqueo", "archivos_del_corpus", "corpus", "fecha")
CLAVES_DEL_CORPUS = ("repo", "commit", "ruta")
CONTADORES = ("aciertos", "aciertos_en_bloqueo", "archivos_del_corpus")
COMMIT_RE = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
FECHA_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
SIN_CARPETA = "<carpeta>"

SIN_CALIBRAR = "sin calibrar"
VIEJA = "calibración vieja"
NO_PASO = "no pasó la calibración"
ROTO = "registro de calibración roto"
MODO_INVALIDO = "modo inválido"

Fuente = namedtuple("Fuente", ("capa", "huella", "sembrados"))
Registro = namedtuple("Registro", ("capas", "roto"))


class RegistroRoto(Exception):
    pass


def huella(contenido):
    return "sha256:" + hashlib.sha256(contenido.replace(b"\r\n", b"\n")).hexdigest()


def huella_del_archivo(ruta):
    with open(ruta, "rb") as f:
        return huella(f.read())


def sembrados(modulo):
    try:
        reglas = getattr(modulo, "REGLAS", None)
        encontrados = {}
        for regla in () if reglas is None else reglas:
            id_ = getattr(regla, "id", None)
            if isinstance(id_, str) and id_:
                sembrado = getattr(regla, "sembrado", None)
                encontrados[id_] = sembrado if isinstance(sembrado, str) and sembrado.strip() else None
        return encontrados
    except Exception:
        return {}


def fuente_del_modulo(capa, modulo, ruta):
    try:
        actual = huella_del_archivo(ruta)
    except OSError:
        actual = None
    return Fuente(capa, actual, sembrados(modulo))


def _claves(datos, claves, donde):
    if not isinstance(datos, dict):
        raise RegistroRoto(f"{donde or 'el registro'} debe ser un objeto")
    prefijo = donde + "." if donde else ""
    sobran = sorted(set(datos) - set(claves))
    if sobran:
        raise RegistroRoto(f"{prefijo}{sobran[0]} no es una clave conocida ({', '.join(claves)})")
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


def validar(datos):
    _claves(datos, CLAVES_DEL_REGISTRO, "")
    version = datos["version"]
    if isinstance(version, bool) or version != VERSION:
        raise RegistroRoto(f"version {version!r} no es la que entiende este plugin ({VERSION})")
    capas = datos["capas"]
    if not isinstance(capas, dict):
        raise RegistroRoto("capas debe ser un objeto con una capa por clave")
    for capa, reglas in capas.items():
        if not isinstance(reglas, dict):
            raise RegistroRoto(f"capas.{capa} debe ser un objeto con una regla por clave")
        for id_, regla in reglas.items():
            _regla(regla, f"capas.{capa}.{id_}")
    return capas


def cargar(raiz):
    ruta = os.path.join(str(raiz), RUTA)
    if not os.path.lexists(ruta):
        return {}
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.loads(f.read())
    except (OSError, ValueError) as error:
        raise RegistroRoto(f"no se puede leer como JSON: {error}")
    return validar(datos)


def registro(raiz):
    try:
        return Registro(cargar(raiz), None)
    except RegistroRoto as error:
        return Registro({}, str(error))


def _ordenada(regla):
    ordenada = {clave: regla[clave] for clave in CLAVES_DE_UNA_REGLA}
    ordenada["corpus"] = {clave: regla["corpus"][clave] for clave in CLAVES_DEL_CORPUS}
    return ordenada


def escribir(raiz, capas):
    datos = {"version": VERSION,
             "capas": {capa: {id_: _ordenada(capas[capa][id_]) for id_ in sorted(capas[capa])} for capa in sorted(capas)}}
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


def _carpeta(id_, reglas, repos):
    for calibrada in ([reglas[id_]] if id_ in reglas else []) + list(reglas.values()):
        repo = repos.get(calibrada["corpus"]["repo"]) if calibrada["corpus"]["repo"] else None
        if isinstance(repo, dict) and repo.get("path"):
            carpeta = os.path.normpath(os.path.join(repo["path"], *calibrada["corpus"]["ruta"].split("/")))
            return '"%s"' % carpeta if any(c.isspace() for c in carpeta) else carpeta
    return SIN_CARPETA


def _aviso(motivo, accion):
    return {"motivo": motivo, "accion": accion}


def _motivo(id_, fuente, actual, repos):
    reglas = actual.capas.get(fuente.capa) or {}
    comando = "`reglas.py --calibrar %s %s --guardar`" % (fuente.capa, _carpeta(id_, reglas, repos))
    if actual.roto is not None:
        return _aviso(ROTO, "para que bloquee, arreglar o borrar %s y correr %s" % (RUTA, comando))
    if not fuente.sembrados.get(id_):
        return _aviso(SIN_CALIBRAR, "para que bloquee, declarar su `sembrado` en REGLAS y correr %s" % comando)
    calibrada = reglas.get(id_)
    if calibrada is None:
        return _aviso(SIN_CALIBRAR, "para que bloquee, correr %s" % comando)
    if calibrada["huella"] != fuente.huella:
        return _aviso(VIEJA, "para que bloquee, correr %s" % comando)
    if not calibrada["atrapa_su_sembrado"]:
        return _aviso(NO_PASO, "no atrapa su sembrado: para que bloquee, arreglar la regla y correr %s" % comando)
    if calibrada["aciertos_en_bloqueo"]:
        return _aviso(NO_PASO, "%d aciertos en bloqueo en el corpus: para que bloquee, arreglar la regla y correr %s"
                      % (calibrada["aciertos_en_bloqueo"], comando))
    return None


def modo_efectivo(hallazgo, fuente, actual, repos):
    propio = {k: v for k, v in hallazgo.items() if k != CLAVE} if CLAVE in hallazgo else hallazgo
    modo = propio.get("modo")
    if not (isinstance(modo, str) and modo in MODOS):
        return dict(propio, modo="aviso", **{CLAVE: _aviso(MODO_INVALIDO, "el módulo tiene que devolver modo aviso o bloqueo")})
    if modo == "aviso" or fuente is None:
        return propio
    motivo = _motivo(propio["id"], fuente, actual, repos)
    return propio if motivo is None else dict(propio, modo="aviso", **{CLAVE: motivo})


def aplicar(grupos, raiz, repos):
    pide_bloqueo = any(fuente is not None and h.get("modo") == "bloqueo" for fuente, hallazgos in grupos for h in hallazgos)
    actual = registro(raiz) if pide_bloqueo else Registro({}, None)
    return [modo_efectivo(h, fuente, actual, repos) for fuente, hallazgos in grupos for h in hallazgos]


def sufijo(hallazgo):
    aviso = hallazgo.get(CLAVE)
    if not isinstance(aviso, dict) or not {"motivo", "accion"} <= set(aviso):
        return ""
    return " (aviso: %s; %s)" % (aviso["motivo"], aviso["accion"])
