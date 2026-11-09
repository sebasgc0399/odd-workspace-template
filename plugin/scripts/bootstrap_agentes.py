import datetime
from pathlib import Path

import config_loader
import plantilla_writer
from odd_ws import capas, hosts

CLAVES = ()
PLANTILLAS = Path(__file__).resolve().parents[1] / "plantillas"
PLANTILLA_REVISOR = PLANTILLAS / "revisor.md"
PLANTILLA_REVISOR_DISENO = PLANTILLAS / "revisor-diseno.md"
PLANTILLA_CAPA = PLANTILLAS / "capa.md"
PLANTILLA_CRITERIOS = PLANTILLAS / "criterios.md"


def _fecha(hoy):
    if hoy is None:
        return datetime.date.today().isoformat()
    if isinstance(hoy, datetime.datetime):
        return hoy.date().isoformat()
    if isinstance(hoy, datetime.date):
        return hoy.isoformat()
    if isinstance(hoy, str):
        try:
            return datetime.date.fromisoformat(hoy).isoformat()
        except ValueError:
            pass
    raise ValueError("hoy debe ser una fecha o un texto AAAA-MM-DD, no %r" % (hoy,))


def _capas_de(spec):
    config = spec.get("config") if isinstance(spec, dict) else None
    declaradas = config.get("layers") if isinstance(config, dict) else None
    if not isinstance(declaradas, dict):
        return []
    return [capa for capa in declaradas if isinstance(capa, str) and capas.es_writer("writer-%s" % capa)]


def _hosts_de(spec):
    config = spec.get("config") if isinstance(spec, dict) else None
    return config_loader.hosts_de(config if isinstance(config, dict) else {})


def _sustituir(ruta, capa, fecha):
    texto = plantilla_writer.leer_plantilla(ruta)
    return texto.replace("{{capa}}", capa).replace("{{fecha}}", fecha)


def generar_revisor(capa, actual=None, host=hosts.FUENTE):
    return plantilla_writer.armar(capa, plantilla_writer.leer_plantilla(PLANTILLA_REVISOR), actual, plantilla_writer.textos(host))


def generar_revisor_diseno(actual=None, host=hosts.FUENTE):
    return plantilla_writer.armar("diseno", plantilla_writer.leer_plantilla(PLANTILLA_REVISOR_DISENO), actual,
                                  plantilla_writer.textos(host))


def nombres_de_agentes(declaradas):
    por_capa = [capa for capa in declaradas if isinstance(capa, str) and capas.es_writer("writer-%s" % capa)]
    nombres = [nombre for capa in por_capa for nombre in ("writer-%s" % capa, "revisor-%s" % capa)]
    return nombres + ["revisor-diseno"] if por_capa else nombres


def armar(nombre, actual=None, host=hosts.FUENTE):
    tipo, _, capa = nombre.partition("-") if isinstance(nombre, str) else ("", "", "")
    if nombre == "revisor-diseno":
        return generar_revisor_diseno(actual, host)
    if tipo == "writer":
        return plantilla_writer.generar(capa, actual, host=host)
    if tipo == "revisor":
        return generar_revisor(capa, actual, host)
    raise ValueError("%r no es un agente de la plantilla (writer-<capa>, revisor-<capa> o revisor-diseno)" % (nombre,))


def _accion(archivo):
    if archivo.fuente is None:
        return archivo.ruta, archivo.contenido
    from bootstrap import AccionDerivada

    return AccionDerivada(archivo.ruta, archivo.contenido, archivo.fuente, archivo.arreglo)


def _armados(por_capa, host):
    return [armar(nombre, host=host) for nombre in nombres_de_agentes(por_capa)]


def generar(spec, hoy=None):
    fecha = _fecha(hoy)
    acciones = []
    por_capa = _capas_de(spec)
    for capa in por_capa:
        acciones.append((capas.writer(capa), plantilla_writer.generar(capa)))
        acciones.append((capas.revisor(capa), generar_revisor(capa)))
        acciones.append((capas.skill(capa), _sustituir(PLANTILLA_CAPA, capa, fecha)))
    if por_capa:
        acciones.append((capas.REVISOR_DISENO, generar_revisor_diseno()))
    acciones.append((capas.CRITERIOS_SKILL, _sustituir(PLANTILLA_CRITERIOS, "", fecha)))
    for host in _hosts_de(spec):
        agentes = [plantilla_writer.agente(texto) for texto in _armados(por_capa, host)]
        acciones.extend(_accion(archivo) for archivo in hosts.adaptador(host).archivos(agentes))
    return acciones
