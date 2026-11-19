import os
import re
import subprocess
import sys
from pathlib import Path

import bootstrap
import config_loader
from odd_ws import abridor, capas, enlaces
from odd_ws.comun import decodificar, entorno_git, id_valido, raiz_de_instancia

USO = ("uso: ticket.py <id> <slug> [--raiz <carpeta>] [--ensayo]\n"
       "     ticket.py --siguiente [<prefijo>] [--raiz <carpeta>]\n"
       "     ticket.py --activar <id> [--raiz <carpeta>]\n"
       "     ticket.py --desactivar <id> [--raiz <carpeta>]\n"
       "     ticket.py --cobertura [--raiz <carpeta>]\n"
       "     ticket.py --enlaces <id> [--raiz <carpeta>] [--copiar | --abrir <n>]\n"
       "     ticket.py --enlaces <ruta a un .md> [--copiar | --abrir <n>]")
NUMERO_RE = re.compile(r"-?[0-9]+")
MODOS = {"--siguiente": "siguiente", "--activar": "activar", "--desactivar": "desactivar", "--cobertura": "cobertura", "--enlaces": "enlaces"}
DOCUMENTO_DEL_TICKET = Path(capas.TICKET_PLANTILLA).name
COPIAR_CON_POWERSHELL = ("$m = New-Object System.IO.MemoryStream; [Console]::OpenStandardInput().CopyTo($m); "
                         "Set-Clipboard -Value ([Text.Encoding]::UTF8.GetString($m.ToArray()))")
COBERTURA_COMPLETA = "todo lo versionado en los repos tiene capa o es doc"
SIN_PREFIJO = (f"la config no fija {config_loader.CLAVE_DE_TICKETS}.prefix: pasá el prefijo (ticket.py --siguiente <prefijo>) "
               f"o fijalo en {config_loader.NOMBRE} como \"{config_loader.CLAVE_DE_TICKETS}\": {{\"prefix\": \"T\"}}")
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


def carpetas_del_id(raiz, id):
    base = Path(raiz) / capas.TICKETS
    plantilla = Path(raiz) / capas.TICKET_PLANTILLA_DIR
    prefijo = f"{id}-".casefold()
    hallados = []
    for actual, carpetas, _ in _recorrer(base):
        if actual == plantilla.parent and plantilla.name in carpetas:
            carpetas.remove(plantilla.name)
        for nombre in carpetas:
            if nombre.casefold().startswith(prefijo):
                hallados.append((actual / nombre).relative_to(raiz).as_posix())
    return sorted(hallados)


def conflictos(raiz, id, slug):
    destino = carpeta_del_ticket(id, slug)
    return [relativa for relativa in carpetas_del_id(raiz, id) if not _es_el_destino(raiz, relativa, destino)]


def ticket_activo(raiz):
    try:
        return (Path(raiz) / capas.TICKET_ACTIVO).read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def marcar_activo(raiz, relativa):
    ruta = Path(raiz) / capas.TICKET_ACTIVO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes((relativa + "\n").encode("utf-8"))


def siguiente(raiz, prefijo):
    if config_loader.PREFIJO_DE_TICKETS_RE.fullmatch(prefijo) is None:
        raise Rechazo(f"el prefijo {prefijo!r} no es válido: empezá por una letra y seguí con letras, números o guion bajo (hasta 32)")
    numerado = re.compile(re.escape(prefijo.casefold()) + r"-([0-9]+)-")
    base = Path(raiz) / capas.TICKETS
    plantilla = Path(raiz) / capas.TICKET_PLANTILLA_DIR
    mayor = 0
    for actual, carpetas, _ in _recorrer(base):
        if actual == plantilla.parent and plantilla.name in carpetas:
            carpetas.remove(plantilla.name)
        for nombre in carpetas:
            encontrado = numerado.match(nombre.casefold())
            if encontrado:
                mayor = max(mayor, int(encontrado.group(1)))
    return f"{prefijo}-{mayor + 1}"


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
    copiar = False
    numero = None
    modo = None
    i = 0
    while i < len(argv):
        argumento = argv[i]
        if argumento == "--ensayo" and not ensayo:
            ensayo = True
            i += 1
        elif argumento == "--copiar" and not copiar:
            copiar = True
            i += 1
        elif argumento == "--abrir" and numero is None and i + 1 < len(argv) and NUMERO_RE.fullmatch(argv[i + 1]):
            try:
                numero = int(argv[i + 1])
            except ValueError:
                return None
            i += 2
        elif argumento in MODOS and modo is None:
            modo = MODOS[argumento]
            i += 1
        elif argumento == "--raiz" and raiz is None and i + 1 < len(argv) and argv[i + 1] and not argv[i + 1].startswith("--"):
            raiz = argv[i + 1]
            i += 2
        elif argumento.startswith("--"):
            return None
        else:
            posicionales.append(argumento)
            i += 1
    if (copiar or numero is not None) and modo != "enlaces":
        return None
    if modo == "enlaces":
        if ensayo or len(posicionales) != 1 or (copiar and numero is not None):
            return None
        return "enlaces", posicionales[0], raiz, copiar, numero
    if modo == "siguiente":
        if ensayo or len(posicionales) > 1:
            return None
        return "siguiente", (posicionales[0] if posicionales else None), raiz
    if modo == "cobertura":
        if ensayo or posicionales:
            return None
        return "cobertura", raiz
    if modo is not None:
        if ensayo or len(posicionales) != 1:
            return None
        return modo, posicionales[0], raiz
    if len(posicionales) != 2:
        return None
    return "crear", posicionales[0], posicionales[1], raiz, ensayo


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


def _siguiente(prefijo, texto_de_raiz):
    try:
        raiz = _raiz(texto_de_raiz)
        if prefijo is None:
            try:
                prefijo = config_loader.prefijo_de_tickets(raiz)
            except config_loader.ConfigRota as error:
                raise ErrorDeEntorno(f"la config de {raiz} está rota ({error})")
            if prefijo is None:
                raise Rechazo(SIN_PREFIJO)
        print(f"siguiente: {siguiente(raiz, prefijo)}")
    except ErrorDeEntorno as error:
        return _error(str(error), 2)
    except Rechazo as error:
        return _error(str(error), 1)
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}", 2)
    return 0


def _marcar(modo, id, texto_de_raiz):
    try:
        raiz = _raiz(texto_de_raiz)
        if not id_valido(id):
            raise Rechazo(f"el id {id!r} no es válido: usá letras, números, guion y guion bajo (hasta 128 caracteres)")
        if modo == "activar":
            carpetas = carpetas_del_id(raiz, id)
            if not carpetas:
                raise Rechazo(f"el id {id} no tiene carpeta en {capas.TICKETS}/")
            if len(carpetas) > 1:
                raise Rechazo(f"el id {id} tiene varias carpetas: {', '.join(carpetas)}; activá la que corresponde a mano o renombrá las otras")
            marcar_activo(raiz, carpetas[0])
            print(f"ticket activo: {carpetas[0]}")
            return 0
        actual = ticket_activo(raiz)
        if actual is not None and not Path(actual).name.casefold().startswith(f"{id}-".casefold()):
            print(f"ticket activo: {actual} (no es el {id})")
            return 0
        try:
            (raiz / capas.TICKET_ACTIVO).unlink()
        except FileNotFoundError:
            pass
        print("sin ticket activo")
    except ErrorDeEntorno as error:
        return _error(str(error), 2)
    except Rechazo as error:
        return _error(str(error), 1)
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}", 2)
    return 0


def versionados(ruta):
    try:
        resultado = subprocess.run(["git", "-C", ruta, "ls-files", "-z"], capture_output=True, timeout=120, env=entorno_git())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if resultado.returncode != 0:
        return None
    return list(filter(None, resultado.stdout.decode("utf-8", "replace").split("\0")))


def _cobertura(texto_de_raiz):
    try:
        raiz = _raiz(texto_de_raiz)
        detalle = config_loader.cobertura_de_los_repos(config_loader.cargar(raiz), versionados)
    except ErrorDeEntorno as error:
        return _error(str(error), 2)
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}", 2)
    if detalle is None:
        print(f"{config_loader.ID_COBERTURA}: {COBERTURA_COMPLETA}")
    else:
        print(f"aviso {config_loader.ID_COBERTURA}: {detalle}")
        print(f"  cómo: {config_loader.AYUDA_COBERTURA}")
    return 0


def documento_de(objetivo, texto_de_raiz):
    if id_valido(objetivo):
        raiz = _raiz(texto_de_raiz)
        carpetas = carpetas_del_id(raiz, objetivo)
        if not carpetas:
            raise Rechazo(f"el id {objetivo} no tiene carpeta en {capas.TICKETS}/")
        if len(carpetas) > 1:
            raise Rechazo(f"el id {objetivo} tiene varias carpetas: {', '.join(carpetas)}; pasá la ruta del {DOCUMENTO_DEL_TICKET} que querés revisar")
        documento = raiz / carpetas[0] / DOCUMENTO_DEL_TICKET
        if not documento.is_file():
            raise Rechazo(f"{carpetas[0]} no tiene {DOCUMENTO_DEL_TICKET}")
        return documento
    if texto_de_raiz is not None:
        raise Rechazo("--raiz va con un id: una ruta ya dice dónde está el documento")
    documento = Path(objetivo)
    if documento.suffix.lower() != ".md" or not documento.is_file():
        raise Rechazo(f"{objetivo} no es un .md que exista: pasá el id de un ticket o la ruta a un .md")
    return documento


def numerados(hallados):
    return [e for e in hallados if e.tipo is not None]


def _de_la_maquina(enlace):
    return f"  ({enlaces.DE_LA_MAQUINA})" if enlaces.es_ruta_de_la_maquina(enlace.destino) else ""


def listado(documento, hallados):
    sanos = numerados(hallados)
    rotos = [e for e in hallados if e.ruta is not None and e.tipo is None]
    con_esquema = [e for e in hallados if e.ruta is None]
    lineas = [f"enlaces de {Path(os.path.abspath(documento)).as_posix()}: {len(hallados)}"]
    lineas += [f"  {n}  {e.tipo}  {e.texto} -> {e.ruta}{_de_la_maquina(e)}" for n, e in enumerate(sanos, 1)]
    if rotos:
        lineas.append(f"rotos: {len(rotos)}")
        lineas += [f"  {enlaces.NO_EXISTE}  {e.texto} -> {e.ruta}{_de_la_maquina(e)}" for e in rotos]
    if con_esquema:
        lineas.append(f"con esquema, sin verificar: {len(con_esquema)}")
        lineas += [f"  {e.texto} -> {e.destino}" for e in con_esquema]
    return lineas, [e.ruta for e in sanos + rotos]


def herramientas_de_portapapeles():
    if os.name == "nt":
        return [[nombre, "-NoProfile", "-NonInteractive", "-Command", COPIAR_CON_POWERSHELL] for nombre in ("powershell", "pwsh")]
    if sys.platform == "darwin":
        return [["pbcopy"]]
    return [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]


def copiar_al_portapapeles(texto):
    herramientas = herramientas_de_portapapeles()
    fallidas = []
    for argv in herramientas:
        programa = abridor.buscar(argv[0], os.environ)
        if programa is None:
            continue
        try:
            resultado = subprocess.run([programa, *argv[1:]], input=texto.encode("utf-8"), stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=30)
            if resultado.returncode == 0:
                return None
        except (OSError, subprocess.TimeoutExpired):
            pass
        fallidas.append(argv[0])
    if fallidas:
        return f"el portapapeles no aceptó la lista ({', '.join(fallidas)} falló)"
    return f"no hay herramienta de portapapeles (busqué {', '.join(argv[0] for argv in herramientas)})"


def elegido(hallados, numero):
    abribles = numerados(hallados)
    if not abribles:
        raise Rechazo("no hay enlaces para abrir: la lista no tiene ninguno que exista")
    if not 1 <= numero <= len(abribles):
        rango = "1 enlace para abrir, el 1" if len(abribles) == 1 else f"{len(abribles)} enlaces para abrir, del 1 al {len(abribles)}"
        raise Rechazo(f"el {numero} no está en la lista: tiene {rango}")
    return abribles[numero - 1]


def _abrir(enlace):
    try:
        abierto, mensaje = abridor.abrir(enlace.ruta, os.environ, sys.platform)
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}", 2)
    if not abierto:
        return _error(mensaje, 1)
    print(mensaje)
    return 0


def _enlaces(objetivo, texto_de_raiz, copiar, numero):
    try:
        documento = documento_de(objetivo, texto_de_raiz)
        hallados = list(enlaces.enlaces(decodificar(documento.read_bytes()), documento.parent))
        lineas, rutas = listado(documento, hallados)
        enlace = None if numero is None else elegido(hallados, numero)
    except ErrorDeEntorno as error:
        return _error(str(error), 2)
    except Rechazo as error:
        return _error(str(error), 1)
    except Exception as error:
        return _error(f"error interno: {type(error).__name__}: {error}", 2)
    print("\n".join(lineas))
    if enlace is not None:
        sys.stdout.flush()
        return _abrir(enlace)
    if not copiar:
        return 0
    if not rutas:
        print("portapapeles: no hay rutas que copiar")
        return 0
    problema = copiar_al_portapapeles(os.linesep.join(rutas))
    if problema is not None:
        print(f"ticket: aviso: {problema}: la lista sale solo por pantalla", file=sys.stderr)
    else:
        print("portapapeles: 1 ruta copiada" if len(rutas) == 1 else f"portapapeles: {len(rutas)} rutas copiadas")
    return 0


def principal(argv):
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    argumentos = _argumentos(argv)
    if argumentos is None:
        print(USO, file=sys.stderr)
        return 2
    if argumentos[0] == "enlaces":
        return _enlaces(*argumentos[1:])
    if argumentos[0] == "siguiente":
        return _siguiente(*argumentos[1:])
    if argumentos[0] == "cobertura":
        return _cobertura(argumentos[1])
    if argumentos[0] in ("activar", "desactivar"):
        return _marcar(*argumentos)
    _, id, slug, texto_de_raiz, ensayo = argumentos
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
            marcar_activo(raiz, carpeta_del_ticket(id, slug))
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
