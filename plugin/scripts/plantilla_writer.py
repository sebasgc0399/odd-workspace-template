import hashlib
import json
import re
from collections import namedtuple
from pathlib import Path

import writer_stop
from odd_ws import capas, hosts

RUTA = Path(__file__).resolve().parents[1] / "plantillas" / "writer.md"
ABRE_RE = re.compile(r"<!-- instancia:([a-z][a-z0-9-]*) -->")
CIERRA_RE = re.compile(r"<!-- /instancia:([a-z][a-z0-9-]*) -->")
COMENTARIO_RE = re.compile(r"<!--.*-->")
ITEM_RE = re.compile(r"\s+-\s+(\S.*?)\s*")
CLAVE_VERSION = "odd-ws-plantilla"
CLAVE_HASH = "odd-ws-hash"
CLAVE_DESCRIPCION = "description"

Revision = namedtuple("Revision", "codigo version")
Agente = namedtuple("Agente", "nombre descripcion herramientas skills version instrucciones")


def normalizar(texto):
    return texto.lstrip("\ufeff").replace("\r\n", "\n")


def leer_plantilla(ruta=RUTA):
    return normalizar(Path(ruta).read_bytes().decode("utf-8"))


def _fin_de_cabecera(lineas):
    if not lineas or lineas[0] != "---":
        return 0
    return next((i for i in range(1, len(lineas)) if lineas[i] == "---"), 0)


def _es_clave(linea, clave):
    return linea.startswith(clave + ":")


def _meta(lineas):
    meta = {}
    for linea in lineas[1:_fin_de_cabecera(lineas)]:
        clave, dos_puntos, valor = linea.partition(":")
        if dos_puntos and clave and not clave[0].isspace() and not clave.startswith("-"):
            meta.setdefault(clave.strip(), valor.strip())
    return meta


def _entero(valor):
    return int(valor) if isinstance(valor, str) and valor.isdigit() else None


def version(plantilla=None):
    texto = leer_plantilla() if plantilla is None else normalizar(plantilla)
    return _entero(_meta(texto.split("\n")).get(CLAVE_VERSION))


def _bloques(lineas):
    bloques, abierto = {}, None
    for i, linea in enumerate(lineas):
        marca = linea.strip()
        abre, cierra = ABRE_RE.fullmatch(marca), CIERRA_RE.fullmatch(marca)
        if abre:
            if abierto is not None or abre.group(1) in bloques:
                return None
            abierto = (abre.group(1), i)
        elif cierra:
            if abierto is None or cierra.group(1) != abierto[0]:
                return None
            bloques[abierto[0]] = (abierto[1], i)
            abierto = None
    return None if abierto is not None else bloques


def huella(texto):
    lineas = normalizar(texto).split("\n")
    bloques = _bloques(lineas)
    if bloques is None:
        return None
    adentro = {i for inicio, cierre in bloques.values() for i in range(inicio + 1, cierre)}
    fin = _fin_de_cabecera(lineas)
    esqueleto = []
    for i, linea in enumerate(lineas):
        if i in adentro:
            continue
        for clave in (CLAVE_DESCRIPCION, CLAVE_HASH):
            if 0 < i < fin and _es_clave(linea, clave):
                linea = clave + ":"
        esqueleto.append(linea)
    return hashlib.sha256("\n".join(esqueleto).encode("utf-8")).hexdigest()


def _descripcion(lineas):
    linea = next((l for l in lineas[1:_fin_de_cabecera(lineas)] if _es_clave(l, CLAVE_DESCRIPCION)), None)
    if linea is None:
        return None
    crudo = linea.split(":", 1)[1].strip()
    if len(crudo) >= 2 and crudo[0] == crudo[-1] == '"':
        try:
            return json.loads(crudo)
        except ValueError:
            return crudo[1:-1]
    if len(crudo) >= 2 and crudo[0] == crudo[-1] == "'":
        return crudo[1:-1].replace("''", "'")
    return crudo


def textos(host=hosts.FUENTE):
    adaptador = hosts.adaptador(host)
    if adaptador is None:
        raise ValueError("el host %r no está en el registro (%s)" % (host, ", ".join(hosts.NOMBRES)))
    return tuple(adaptador.TEXTOS.items())


def generar(capa, actual=None, plantilla=None, host=hosts.FUENTE):
    if not isinstance(capa, str) or not capas.es_writer("writer-%s" % capa):
        raise ValueError("writer-%s no cumple %s" % (capa, capas.WRITER_RE.pattern))
    base = leer_plantilla() if plantilla is None else plantilla
    return armar(capa, base, actual, (("{{resultado}}", writer_stop.PLANTILLA),) + textos(host))


def armar(capa, plantilla, actual=None, sustituciones=()):
    if not isinstance(capa, str) or not capas.es_writer("writer-%s" % capa):
        raise ValueError("la capa %r no cumple %s" % (capa, capas.WRITER_RE.pattern))
    texto = normalizar(plantilla)
    for marca, valor in sustituciones:
        texto = texto.replace(marca, valor)
    lineas = texto.replace("{{capa}}", capa).split("\n")
    propios, descripcion = {}, None
    if actual is not None:
        previas = normalizar(actual).split("\n")
        bloques = _bloques(previas)
        if bloques is None:
            raise ValueError("los bloques de la instancia están mal formados")
        propios = {nombre: previas[inicio + 1:cierre] for nombre, (inicio, cierre) in bloques.items()}
        descripcion = _descripcion(previas)
    bloques = _bloques(lineas)
    if bloques is None:
        raise ValueError("los bloques de la plantilla están mal formados")
    for nombre, (inicio, cierre) in sorted(bloques.items(), key=lambda par: -par[1][0]):
        if nombre in propios:
            lineas[inicio + 1:cierre] = propios[nombre]
    fin = _fin_de_cabecera(lineas)
    if descripcion is not None:
        lineas = [CLAVE_DESCRIPCION + ": " + json.dumps(descripcion, ensure_ascii=False) if 0 < i < fin and _es_clave(l, CLAVE_DESCRIPCION) else l
                  for i, l in enumerate(lineas)]
    sello = huella("\n".join(lineas))
    return "\n".join(CLAVE_HASH + ": " + sello if 0 < i < fin and _es_clave(l, CLAVE_HASH) else l for i, l in enumerate(lineas))


def _lista(lineas, clave):
    fin = _fin_de_cabecera(lineas)
    inicio = next((i for i in range(1, fin) if _es_clave(lineas[i], clave)), None)
    if inicio is None:
        return ()
    items = []
    for linea in lineas[inicio + 1:fin]:
        item = ITEM_RE.fullmatch(linea)
        if item is None:
            break
        items.append(item.group(1))
    return tuple(items)


def _es_del_plugin(linea, es_la_primera):
    marca = linea.strip()
    return bool(ABRE_RE.fullmatch(marca) or CIERRA_RE.fullmatch(marca) or (es_la_primera and COMENTARIO_RE.fullmatch(marca)))


def agente(texto):
    lineas = normalizar(texto).split("\n")
    meta = _meta(lineas)
    fin = _fin_de_cabecera(lineas)
    cuerpo = lineas[fin + 1:] if fin else lineas
    primera = next((i for i, linea in enumerate(cuerpo) if linea.strip()), None)
    instrucciones = [linea for i, linea in enumerate(cuerpo) if not _es_del_plugin(linea, i == primera)]
    return Agente(
        nombre=meta.get("name"),
        descripcion=_descripcion(lineas),
        herramientas=tuple(h.strip() for h in meta.get("tools", "").split(",") if h.strip()),
        skills=_lista(lineas, "skills"),
        version=_entero(meta.get(CLAVE_VERSION)),
        instrucciones="\n".join(instrucciones).strip("\n"),
    )


def revisar(raiz, capa, plantilla=None):
    if not isinstance(capa, str) or not capas.es_writer("writer-%s" % capa):
        return Revision("nombre", None)
    ruta = Path(raiz) / capas.writer(capa)
    if not ruta.is_file():
        return Revision("falta", None)
    try:
        texto = normalizar(ruta.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return Revision("ilegible", None)
    meta = _meta(texto.split("\n"))
    previa = _entero(meta.get(CLAVE_VERSION))
    if previa is None or CLAVE_HASH not in meta:
        return Revision("ajeno", None)
    sello = huella(texto)
    if sello is None:
        return Revision("malformado", previa)
    if sello != meta[CLAVE_HASH]:
        return Revision("editado", previa)
    if generar(capa, texto, plantilla) != texto:
        return Revision("atrasado", previa)
    return Revision("ok", previa)


def escribir(raiz, capa, plantilla=None):
    revision = revisar(raiz, capa, plantilla)
    if revision.codigo not in ("falta", "atrasado"):
        raise ValueError("writer-%s: %s, no se genera encima" % (capa, revision.codigo))
    ruta = Path(raiz) / capas.writer(capa)
    actual = None if revision.codigo == "falta" else ruta.read_bytes().decode("utf-8")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(generar(capa, actual, plantilla).encode("utf-8"))
    return ruta
