import sys

sys.dont_write_bytecode = True

import json
import os
import re
from collections import namedtuple
from pathlib import Path

import config_loader
from odd_ws import capas as convencion
from odd_ws.calibracion import huella as _huella_sin_bom

ID = "plantillas"
MANIFIESTO = ".claude-plugin/plugin.json"
CARPETA = "plantillas"
TABLA = CARPETA + "/huellas.json"
INDICE, INDICE_DE_CONTROLES, TICKET, PRE_COMMIT, PRUEBA = ("CLAUDE.md", "CLAUDE.controles.md", "ticket.md", "pre-commit",
                                                           "reglas/verificar.tests.py")
PLANTILLAS = (INDICE, INDICE_DE_CONTROLES, TICKET, PRE_COMMIT, PRUEBA)
INDICES = (INDICE, INDICE_DE_CONTROLES)
PRE_COMMIT_DE_LA_INSTANCIA = ".githooks/pre-commit"
MARCA_NOMBRE, MARCA_TICKETS = "{{nombre}}", "{{tickets}}"
BOM = b"\xef\xbb\xbf"
HUELLA_RE = re.compile(r"sha256:[0-9a-f]{64}")
VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(.*)")
AL_DIA, SIN_TOCAR, EDITADA = "al día", "sin tocar", "editada"
QUE_HACER = {SIN_TOCAR: "sin tocar: se reemplaza", EDITADA: "editada: fusiónala a mano"}
DONDE_LEER = "Doc/actualizar.md"
AYUDA_DEL_PLUGIN = "Reinstala el plugin: le falta o tiene roto un archivo que trae de fábrica. Después, otra vez el doctor."

Copia = namedtuple("Copia", "ruta plantilla")
Revisada = namedtuple("Revisada", "ruta plantilla estado versiones nombre")
Revision = namedtuple("Revision", "rota error ayuda actual anotada inferida base cambiaron pendientes",
                      defaults=(None, None, None, None, None, None, None, False, ()))


def orden(version):
    partes = VERSION_RE.fullmatch(version or "")
    if partes is None:
        return (-1, -1, -1, 0, "")
    sufijo = partes.group(4)
    return (int(partes.group(1)), int(partes.group(2)), int(partes.group(3)), 0 if sufijo else 1, sufijo)


def huella(contenido):
    return _huella_sin_bom(contenido[len(BOM):] if contenido.startswith(BOM) else contenido)


def forma_de_la_plantilla(plantilla, contenido):
    if plantilla == INDICE:
        return contenido.replace(MARCA_TICKETS.encode("utf-8"), convencion.TICKETS.encode("utf-8"))
    return contenido


def huella_de_la_plantilla(plantilla, contenido):
    return huella(forma_de_la_plantilla(plantilla, contenido))


def version_del_plugin(plugin):
    ruta = Path(plugin) / MANIFIESTO
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        return None, f"no se puede leer la versión del plugin en {ruta} ({error})"
    version = datos.get("version") if isinstance(datos, dict) else None
    if not isinstance(version, str) or config_loader.VERSION_DEL_PLUGIN_RE.fullmatch(version) is None:
        return None, f"{ruta} no trae una «version» X.Y.Z: {version!r}"
    return version, None


def leer_tabla(plugin):
    ruta = Path(plugin) / TABLA
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        return None, f"no se puede leer la tabla de huellas del plugin, {ruta} ({error})"
    if not isinstance(datos, dict) or not all(isinstance(versiones, dict) and all(map(_entrada_valida, versiones.items()))
                                              for versiones in datos.values()):
        return None, f"la tabla de huellas del plugin, {ruta}, no es un objeto plantilla → {{versión: huella}}"
    return datos, None


def _entrada_valida(entrada):
    version, huella_de_la_version = entrada
    return (isinstance(version, str) and config_loader.VERSION_DEL_PLUGIN_RE.fullmatch(version) is not None
            and isinstance(huella_de_la_version, str) and HUELLA_RE.fullmatch(huella_de_la_version) is not None)


def copias(raiz):
    capas = config_loader.capas(raiz)
    if config_loader.perfil(raiz) == config_loader.CONTROLES:
        lista = [Copia(convencion.INDICE, INDICE_DE_CONTROLES)]
    else:
        lista = [Copia(convencion.INDICE, INDICE), Copia(convencion.TICKET_PLANTILLA, TICKET)]
    lista.append(Copia(PRE_COMMIT_DE_LA_INSTANCIA, PRE_COMMIT))
    return lista + [Copia(convencion.prueba(capa), PRUEBA) for capa in capas]


def _normal(contenido):
    return (contenido[len(BOM):] if contenido.startswith(BOM) else contenido).replace(b"\r\n", b"\n")


def nombre_de(copia, plantilla):
    primera = plantilla.split("\n", 1)[0]
    if primera.count(MARCA_NOMBRE) != 1:
        return None
    antes, despues = primera.split(MARCA_NOMBRE)
    suya = copia.split("\n", 1)[0]
    if len(suya) <= len(antes) + len(despues) or not (suya.startswith(antes) and suya.endswith(despues)):
        return None
    nombre = suya[len(antes):len(suya) - len(despues)]
    return nombre if nombre == nombre.strip() and MARCA_NOMBRE not in nombre else None


def _huella_de_la_copia(plantilla, contenido, texto_de_la_plantilla):
    if plantilla not in INDICES:
        return huella(contenido), None
    try:
        texto = _normal(contenido).decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    nombre = nombre_de(texto, texto_de_la_plantilla)
    if nombre is None:
        return None, None
    return huella(texto.replace(nombre, MARCA_NOMBRE).encode("utf-8")), nombre


def renderizar(plantilla, texto, nombre=None):
    if plantilla == INDICE:
        return texto.replace(MARCA_TICKETS, convencion.TICKETS).replace(MARCA_NOMBRE, nombre)
    if plantilla == INDICE_DE_CONTROLES:
        return texto.replace(MARCA_NOMBRE, nombre)
    return texto


def contenido_nuevo(plugin, plantilla, nombre=None):
    ruta = Path(plugin) / CARPETA / plantilla
    if plantilla == PRE_COMMIT:
        return ruta.read_bytes()
    return renderizar(plantilla, ruta.read_text(encoding="utf-8-sig"), nombre).encode("utf-8")


def _base(anotada, revisadas):
    if anotada is not None:
        return anotada, None
    conjuntos = [set(r.versiones) for r in revisadas if r.versiones]
    if not conjuntos:
        return None, None
    comunes = set.intersection(*conjuntos) or set.union(*conjuntos)
    inferida = min(comunes, key=orden)
    return inferida, inferida


def revisar(raiz, plugin):
    raiz, plugin = Path(raiz), Path(plugin)
    try:
        anotada = config_loader.plantillas(raiz)
        lista = copias(raiz)
    except config_loader.ConfigRota as error:
        return Revision(rota=str(error))
    actual, error = version_del_plugin(plugin)
    if error:
        return Revision(error=error, ayuda=AYUDA_DEL_PLUGIN)
    tabla, error = leer_tabla(plugin)
    if error:
        return Revision(error=error, ayuda=AYUDA_DEL_PLUGIN, actual=actual)
    vivas, textos = {}, {}
    for plantilla in dict.fromkeys(c.plantilla for c in lista):
        ruta = plugin / CARPETA / plantilla
        try:
            contenido = ruta.read_bytes()
            textos[plantilla] = _normal(contenido).decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return Revision(error=f"no se puede leer la plantilla {ruta} del plugin ({error})", ayuda=AYUDA_DEL_PLUGIN, actual=actual)
        vivas[plantilla] = huella_de_la_plantilla(plantilla, contenido)
    revisadas = []
    for copia in lista:
        ruta = raiz / copia.ruta
        if not os.path.lexists(ruta):
            continue
        try:
            contenido = ruta.read_bytes()
        except OSError as error:
            return Revision(error=f"no se puede leer {copia.ruta} de la instancia ({error.strerror or error})",
                            ayuda=f"Revisa que {copia.ruta} sea un archivo que se pueda leer y vuelve a correr el doctor.", actual=actual)
        suya, nombre = (None, None) if os.path.islink(ruta) else _huella_de_la_copia(copia.plantilla, contenido, textos[copia.plantilla])
        conocidas = tabla.get(copia.plantilla, {})
        versiones = [v for v, h in conocidas.items() if h == suya and suya is not None]
        if suya is not None and suya == vivas[copia.plantilla]:
            versiones.append(actual)
            estado = AL_DIA
        else:
            estado = SIN_TOCAR if versiones else EDITADA
        revisadas.append(Revisada(copia.ruta, copia.plantilla, estado, tuple(dict.fromkeys(versiones)), nombre))
    base, inferida = _base(anotada, revisadas)

    def en(plantilla, version):
        return vivas[plantilla] if version == actual else tabla.get(plantilla, {}).get(version)

    cambiaron = [p for p in vivas if base is None or en(p, base) != vivas[p]]
    pendientes = tuple(r for r in revisadas if r.plantilla in cambiaron and r.estado != AL_DIA)
    return Revision(actual=actual, anotada=anotada, inferida=inferida, base=base, cambiaron=bool(cambiaron), pendientes=pendientes)


def al_dia(revision):
    return revision.anotada is not None and (revision.anotada == revision.actual or not revision.cambiaron)


def _clave_con_la_version(texto, version):
    datos = json.loads(texto)
    esperado = {**datos, config_loader.CLAVE_PLANTILLAS: version}
    valor = json.dumps(version)

    def igual(candidato):
        try:
            return json.loads(candidato) == esperado
        except ValueError:
            return False

    clave = json.dumps(config_loader.CLAVE_PLANTILLAS)
    for hallada in re.finditer(re.escape(clave) + r'(\s*:\s*)"(?:[^"\\]|\\.)*"', texto):
        candidato = texto[:hallada.start()] + clave + hallada.group(1) + valor + texto[hallada.end():]
        if igual(candidato):
            return candidato
    fin = texto.rstrip().rfind("}")
    previo = texto[:fin].rstrip()
    sangria = re.search(r'\n([ \t]+)"', texto)
    salto = "\r\n" if "\r\n" in texto else "\n"
    coma = "" if previo.endswith("{") else ","
    candidato = f"{previo}{coma}{salto}{sangria.group(1) if sangria else '  '}{clave}: {valor}{salto}{texto[fin:]}"
    if igual(candidato):
        return candidato
    return json.dumps(esperado, indent=2, ensure_ascii=False) + "\n"


def anotar_version(raiz, version):
    ruta = Path(raiz) / config_loader.NOMBRE
    crudo = ruta.read_bytes()
    bom = crudo.startswith(BOM)
    texto = _clave_con_la_version(crudo[len(BOM):].decode("utf-8") if bom else crudo.decode("utf-8"), version)
    ruta.write_bytes((BOM if bom else b"") + texto.encode("utf-8"))


def reemplazar(raiz, plugin):
    raiz, plugin = Path(raiz), Path(plugin)
    revision = revisar(raiz, plugin)
    if revision.rota or revision.error:
        return f"nada: {revision.rota or revision.error}"
    reemplazadas = []
    try:
        for revisada in revision.pendientes:
            if revisada.estado == SIN_TOCAR:
                (raiz / revisada.ruta).write_bytes(contenido_nuevo(plugin, revisada.plantilla, revisada.nombre))
                reemplazadas.append(revisada.ruta)
        anotar_version(raiz, revision.actual)
    except (OSError, ValueError) as error:
        hechas = f" (alcanzó a reemplazar {', '.join(reemplazadas)})" if reemplazadas else ""
        return f"no se pudo terminar{hechas}: {error}"
    anotada = f'"{config_loader.CLAVE_PLANTILLAS}": "{revision.actual}" en {config_loader.NOMBRE}'
    if not reemplazadas:
        return anotada
    return f"{', '.join(reemplazadas)} con la plantilla de la {revision.actual}; {anotada}"


def aviso_de_inicio(raiz, plugin):
    revision = revisar(raiz, plugin)
    if not revision.pendientes:
        return None
    nombres = ", ".join(r.ruta for r in revision.pendientes)
    return (f"odd-ws: con la {revision.actual} cambiaron plantillas que esta instancia copió y que no se actualizan solas: {nombres}. "
            f"Cuéntaselo al usuario: /odd-ws:doctor, en el ítem {ID}, dice cuáles se reemplazan con --arreglar y cuáles se fusionan a mano.")
