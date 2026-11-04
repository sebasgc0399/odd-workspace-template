import os
import re
import sys
from pathlib import Path

import bootstrap
import config_loader
from odd_ws import capas
from odd_ws.comun import id_valido, raiz_de_instancia

USO = "uso: ticket.py <id> <slug> [--raiz <carpeta>] [--ensayo]"
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PLANTILLA_FALTANTE = "falta {}: corré /odd-ws:bootstrap para generarla"
AVISO_SIN_SETTINGS = (
    "ticket: aviso: la plantilla no tiene {}, así que una sesión abierta dentro del ticket no carga el plugin: "
    "completá la instancia con /odd-ws:bootstrap y volvé a correr ticket.py"
)


class Rechazo(Exception):
    pass


class ErrorDeEntorno(Exception):
    pass


def carpeta_del_ticket(id, slug):
    return f"{capas.TICKETS}/{id}-{slug}"


def _validar(id, slug):
    if not id_valido(id):
        raise Rechazo(f"el id {id!r} no es válido: usá letras, números, guion y guion bajo (hasta 128 caracteres)")
    if SLUG_RE.fullmatch(slug) is None:
        raise Rechazo(f"el slug {slug!r} no es válido: usá minúsculas y números, con guiones entre ellos (por ejemplo, lector-de-codigo)")


def _recorrer(carpeta):
    for actual, carpetas, archivos in os.walk(carpeta):
        carpetas.sort()
        yield Path(actual), carpetas, sorted(archivos)


def _es_el_destino(raiz, relativa, destino):
    if relativa == destino:
        return True
    try:
        return os.path.samefile(Path(raiz) / relativa, Path(raiz) / destino)
    except OSError:
        return False


def conflictos(raiz, id, slug):
    base = Path(raiz) / capas.TICKETS
    plantilla = Path(raiz) / capas.TICKET_PLANTILLA_DIR
    destino = carpeta_del_ticket(id, slug)
    prefijo = f"{id}-".casefold()
    hallados = []
    for actual, carpetas, _ in _recorrer(base):
        if actual == plantilla.parent and plantilla.name in carpetas:
            carpetas.remove(plantilla.name)
        for nombre in carpetas:
            relativa = (actual / nombre).relative_to(raiz).as_posix()
            if nombre.casefold().startswith(prefijo) and not _es_el_destino(raiz, relativa, destino):
                hallados.append(relativa)
    return sorted(hallados)


def archivos_de_la_plantilla(raiz):
    carpeta = Path(raiz) / capas.TICKET_PLANTILLA_DIR
    real = os.path.realpath(carpeta)
    hallados = []
    for actual, carpetas, archivos in _recorrer(carpeta):
        for nombre in (*carpetas, *archivos):
            ruta = actual / nombre
            if not bootstrap._dentro(os.path.realpath(ruta), real):
                raise Rechazo(f"{ruta.relative_to(raiz).as_posix()} sale de la plantilla: no se copia nada")
        for nombre in archivos:
            ruta = actual / nombre
            hallados.append((ruta.relative_to(carpeta).as_posix(), ruta.read_bytes()))
    return sorted(hallados)


def planificar(raiz, id, slug):
    _validar(id, slug)
    raiz = Path(raiz)
    bootstrap._revisar_destino(raiz, capas.TICKET_PLANTILLA)
    if not (raiz / capas.TICKET_PLANTILLA).is_file():
        raise Rechazo(PLANTILLA_FALTANTE.format(capas.TICKET_PLANTILLA))
    otros = conflictos(raiz, id, slug)
    if otros:
        raise Rechazo(f"el id {id} ya tiene carpeta en {', '.join(otros)}: un id es una sola carpeta (la pedida era {carpeta_del_ticket(id, slug)})")
    destino = carpeta_del_ticket(id, slug)
    return bootstrap.planificar_archivos(raiz, [(f"{destino}/{ruta}", datos) for ruta, datos in archivos_de_la_plantilla(raiz)], "ticket")


def _argumentos(argv):
    posicionales = []
    raiz = None
    ensayo = False
    i = 0
    while i < len(argv):
        argumento = argv[i]
        if argumento == "--ensayo" and not ensayo:
            ensayo = True
            i += 1
        elif argumento == "--raiz" and raiz is None and i + 1 < len(argv) and argv[i + 1] and not argv[i + 1].startswith("--"):
            raiz = argv[i + 1]
            i += 2
        elif argumento.startswith("--"):
            return None
        else:
            posicionales.append(argumento)
            i += 1
    if len(posicionales) != 2:
        return None
    return posicionales[0], posicionales[1], raiz, ensayo


def _raiz(texto):
    if texto is None:
        raiz = raiz_de_instancia(os.environ, os.getcwd())
        if raiz is None:
            raise ErrorDeEntorno(f"no hay {config_loader.NOMBRE} en la carpeta de la sesión ni en sus padres (pasá --raiz)")
    else:
        raiz = Path(texto)
        if not (raiz / config_loader.NOMBRE).is_file():
            raise ErrorDeEntorno(f"no hay {config_loader.NOMBRE} en {raiz}")
    try:
        config_loader.cargar(raiz)
    except config_loader.ConfigRota as error:
        raise ErrorDeEntorno(f"la config de {raiz} está rota ({error})")
    return Path(raiz)


def _error(mensaje, codigo):
    print("ticket: " + mensaje, file=sys.stderr)
    return codigo


def principal(argv):
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    argumentos = _argumentos(argv)
    if argumentos is None:
        print(USO, file=sys.stderr)
        return 2
    id, slug, texto_de_raiz, ensayo = argumentos
    plan = []
    raiz = None
    try:
        raiz = _raiz(texto_de_raiz)
        plan = planificar(raiz, id, slug)
        if not (raiz / capas.TICKET_SETTINGS).is_file():
            print(AVISO_SIN_SETTINGS.format(capas.TICKET_SETTINGS), file=sys.stderr)
        if ensayo:
            lineas = bootstrap.informe(plan, None, raiz, True)
        else:
            lineas = bootstrap.informe(plan, bootstrap.aplicar(plan, raiz), raiz, False)
    except ErrorDeEntorno as error:
        return _error(str(error), 2)
    except (Rechazo, bootstrap.ErrorDePlan) as error:
        return _error(str(error), 1)
    except bootstrap.ErrorDeAplicacion as error:
        if error.resultados:
            print("\n".join(bootstrap.informe(plan, error.resultados, raiz, False, con_resumen=False)))
        return _error(str(error), 2)
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}", 2)
    lineas.append(f"ticket: {Path(os.path.abspath(raiz / carpeta_del_ticket(id, slug))).as_posix()}")
    print("\n".join(lineas))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
