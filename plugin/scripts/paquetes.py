import sys

sys.dont_write_bytecode = True

import argparse
import contextlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit

from config_loader import NOMBRE as CONFIG
import config_loader
from odd_ws import paquetes
from odd_ws.comun import entorno_git, raiz_de_instancia

PLAZO_DE_GIT = 120
MODOS_QUE_NO_SON_ARCHIVOS = ("120000", "160000")
PROTOCOLOS = ("file", "https", "ssh", "git")
CONFIG_DE_GIT = ("-c", "protocol.allow=never", *[pieza for protocolo in PROTOCOLOS for pieza in ("-c", "protocol.%s.allow=always" % protocolo)],
                 "-c", "protocol.ext.allow=never", "-c", "advice.detachedHead=false")
REVISAR = ("Antes de commitear, revisa en el diff lo copiado, sobre todo %s y %s: es código que corre en los hooks de esta "
           "instancia y en reglas.py --test." % (paquetes.MODULO, paquetes.SUITE))
CON_CREDENCIALES = ("la fuente trae usuario o contraseña en la URL y quedaría en el lock, que se commitea: configura las credenciales "
                    "en git (un credential helper o ssh) y pasa la URL sin ellas")
AVISO_LOCAL = "aviso: la fuente es una ruta local (%s): el lock solo sirve en esta máquina; para un equipo, importa desde una URL"


class Rechazo(Exception):
    pass


class ErrorEntorno(Exception):
    pass


def _entorno():
    env = entorno_git()
    env.update(GIT_TERMINAL_PROMPT="0", GIT_PROTOCOL_FROM_USER="0", GCM_INTERACTIVE="never")
    return env


def _git(*args):
    try:
        r = subprocess.run(["git", *CONFIG_DE_GIT, *args], capture_output=True, stdin=subprocess.DEVNULL, env=_entorno(),
                           timeout=PLAZO_DE_GIT)
    except FileNotFoundError:
        raise ErrorEntorno("git no está instalado o no está en el PATH")
    except subprocess.TimeoutExpired:
        raise ErrorEntorno("git %s no respondió en %d s" % (args[0], PLAZO_DE_GIT))
    except OSError as exc:
        raise ErrorEntorno("no se pudo correr git (%s)" % exc)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def _primera_linea(texto):
    return next((l.strip() for l in texto.splitlines() if l.strip() and not l.startswith("warning:")), "sin detalle")


def _forzar(funcion, ruta, _info):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def _borrar(ruta):
    try:
        if paquetes.es_enlace(ruta):
            os.unlink(ruta) if os.path.islink(ruta) else os.rmdir(ruta)
        elif sys.version_info >= (3, 12):
            shutil.rmtree(ruta, onexc=_forzar)
        else:
            shutil.rmtree(ruta, onerror=_forzar)
    except FileNotFoundError:
        pass


def _dentro(ruta, carpeta):
    ruta, carpeta = os.path.normcase(os.path.realpath(ruta)), os.path.normcase(os.path.realpath(carpeta))
    try:
        return os.path.commonpath([ruta, carpeta]) == carpeta
    except ValueError:
        return False


def fuente_para_el_lock(fuente):
    if "://" in fuente:
        partes = urlsplit(fuente)
        if "@" in partes.netloc:
            raise Rechazo(CON_CREDENCIALES)
        return fuente, partes.scheme.lower() == "file"
    if "::" not in fuente and os.path.exists(fuente):
        return os.path.normpath(os.path.abspath(fuente)), True
    return fuente, False


def _sin_enlaces_en_el_destino(raiz, nombre):
    enlazado = paquetes.destino_enlazado(raiz, nombre)
    if enlazado:
        raise Rechazo("%s es un enlace o apunta fuera de la instancia: el paquete no se escribe ahí" % enlazado)


def resolver_etiqueta(fuente, etiqueta):
    codigo, salida, error = _git("ls-remote", "--tags", "--", fuente)
    if codigo != 0:
        raise ErrorEntorno("git ls-remote no pudo leer %s: %s" % (fuente, _primera_linea(error)))
    refs = {}
    for linea in salida.splitlines():
        partes = linea.split("\t")
        if len(partes) == 2:
            refs[partes[1].strip()] = partes[0].strip()
    directa = refs.get("refs/tags/%s" % etiqueta)
    if directa is None:
        raise Rechazo("la etiqueta %s no existe en %s" % (etiqueta, fuente))
    return refs.get("refs/tags/%s^{}" % etiqueta, directa)


@contextlib.contextmanager
def clon(fuente, etiqueta, raiz):
    commit = resolver_etiqueta(fuente, etiqueta)
    temporal = tempfile.mkdtemp(prefix="odd-ws-paquete-")
    try:
        if _dentro(temporal, raiz):
            raise ErrorEntorno("la carpeta temporal %s queda dentro de la instancia: apunta TEMP o TMPDIR a otro lado" % temporal)
        destino = os.path.join(temporal, "clon")
        codigo, _, error = _git("clone", "-q", "--depth", "1", "--branch=%s" % etiqueta, "--no-recurse-submodules", "--", fuente, destino)
        if codigo != 0:
            raise ErrorEntorno("git clone no pudo traer la etiqueta %s de %s: %s" % (etiqueta, fuente, _primera_linea(error)))
        codigo, head, error = _git("-C", destino, "rev-parse", "HEAD")
        if codigo != 0 or head.strip() != commit:
            raise Rechazo("el clon de %s quedó en %s y la etiqueta apunta a %s: ¿hay una rama con el mismo nombre?"
                          % (etiqueta, head.strip()[:12] or "?", commit[:12]))
        yield commit, destino
    finally:
        _borrar(temporal)


def validar_clon(carpeta):
    codigo, arbol, error = _git("-C", carpeta, "ls-tree", "-z", "HEAD", "--", *paquetes.LISTA_BLANCA)
    if codigo != 0:
        raise ErrorEntorno("git ls-tree no pudo leer el clon: %s" % _primera_linea(error))
    for entrada in filter(None, arbol.split("\0")):
        datos, nombre = entrada.split("\t", 1)
        modo, tipo = datos.split(" ")[:2]
        if modo in MODOS_QUE_NO_SON_ARCHIVOS or tipo != "blob":
            raise Rechazo("%s es un enlace o no es un archivo común en la etiqueta: un paquete solo lleva archivos" % nombre)
    enlazados = paquetes.enlaces_en(carpeta)
    if enlazados:
        raise Rechazo("%s es un enlace o apunta fuera del paquete" % ", ".join(enlazados))
    presentes = paquetes.presentes(carpeta)
    faltan = [nombre for nombre in paquetes.OBLIGATORIOS if nombre not in presentes]
    if faltan:
        raise Rechazo("falta%s %s en la etiqueta" % ("n" if len(faltan) > 1 else "", ", ".join(faltan)))
    try:
        manifiesto = paquetes.leer_manifiesto(carpeta)
    except paquetes.ManifiestoInvalido as exc:
        raise Rechazo(str(exc))
    if not paquetes.api_soportada(manifiesto):
        raise Rechazo("%s pide odd_ws_api %d y este plugin da %d: actualiza el plugin antes de importarlo"
                      % (manifiesto["nombre"], manifiesto["odd_ws_api"], paquetes.odd_ws.API))
    return manifiesto


def _capas(raiz):
    try:
        return config_loader.capas(raiz)
    except config_loader.ConfigRota as exc:
        raise ErrorEntorno("%s roto: %s" % (CONFIG, exc))


def _lock(raiz):
    try:
        return paquetes.leer_lock(raiz)
    except paquetes.LockRoto as exc:
        raise ErrorEntorno("%s roto: %s" % (paquetes.LOCK, exc))


def _validar_entrada(otros, nuevo, capas):
    try:
        paquetes.validar_lock(paquetes.datos_del_lock({**otros, nuevo.nombre: nuevo}))
    except paquetes.LockRoto as exc:
        raise Rechazo(str(exc))
    choque = paquetes.choques_con_las_capas({nuevo.nombre: nuevo}, capas).get(nuevo.nombre)
    if choque:
        raise Rechazo("%s: %s" % (nuevo.nombre, choque))


def _normalizado(ruta):
    with open(ruta, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def cambios(actual, nueva):
    viejos = set(paquetes.presentes(actual)) if os.path.isdir(actual) else set()
    nuevos = set(paquetes.presentes(nueva))
    lineas = []
    for archivo in sorted(viejos | nuevos):
        if archivo not in viejos:
            lineas.append("  nuevo %s" % archivo)
        elif archivo not in nuevos:
            lineas.append("  sale %s" % archivo)
        elif _normalizado(os.path.join(actual, archivo)) != _normalizado(os.path.join(nueva, archivo)):
            lineas.append("  cambia %s" % archivo)
    return lineas or ["  sin cambios en los archivos"]


def _entrada_del_lock(paquete):
    return json.dumps(paquetes.datos_del_lock({paquete.nombre: paquete})["paquetes"], ensure_ascii=False)


def instalar(raiz, paquete, carpeta_del_clon, otros):
    destino = os.path.join(raiz, paquetes.carpeta(paquete.nombre))
    padre = os.path.dirname(destino)
    os.makedirs(padre, exist_ok=True)
    preparada = tempfile.mkdtemp(prefix=".%s.nuevo." % paquete.nombre, dir=padre)
    anterior, instalada = None, False
    try:
        os.chmod(preparada, 0o755)
        for archivo in paquetes.presentes(carpeta_del_clon):
            shutil.copyfile(os.path.join(carpeta_del_clon, archivo), os.path.join(preparada, archivo))
        if os.path.lexists(destino):
            anterior = tempfile.mkdtemp(prefix=".%s.anterior." % paquete.nombre, dir=padre)
            os.rmdir(anterior)
            os.replace(destino, anterior)
        os.replace(preparada, destino)
        instalada = True
        paquete = paquete._replace(huella=paquetes.huella(destino))
        paquetes.escribir_lock(raiz, {**otros, paquete.nombre: paquete})
    except (OSError, paquetes.LockRoto) as exc:
        _borrar(destino if instalada else preparada)
        if anterior is not None:
            os.replace(anterior, destino)
        raise ErrorEntorno("no se pudo instalar %s: %s" % (paquetes.carpeta(paquete.nombre), exc))
    if anterior is not None:
        _borrar(anterior)
    return paquete


def _avisar_si_es_local(fuente, local):
    if local:
        print("paquetes: " + AVISO_LOCAL % fuente, file=sys.stderr)


def importar(raiz, args):
    fuente, local = fuente_para_el_lock(args.fuente)
    capas = _capas(raiz)
    if args.capa not in capas:
        raise Rechazo("la capa %s no está declarada en %s (capas: %s)" % (args.capa, CONFIG, ", ".join(capas)))
    if "rule_prefix" not in capas[args.capa]:
        raise Rechazo("la capa %s no tiene rule_prefix en %s: sin prefijo no tiene matriz, y matriz.py no podría validar la del paquete"
                      % (args.capa, CONFIG))
    lock = _lock(raiz) or {}
    with clon(fuente, args.etiqueta, raiz) as (commit, carpeta_del_clon):
        manifiesto = validar_clon(carpeta_del_clon)
        nombre = manifiesto["nombre"]
        if nombre in lock:
            raise Rechazo("%s ya está en %s: para cambiar su etiqueta, actualizar" % (nombre, paquetes.LOCK))
        _sin_enlaces_en_el_destino(raiz, nombre)
        if os.path.lexists(os.path.join(raiz, paquetes.carpeta(nombre))):
            raise Rechazo("ya existe %s y no está en el lock: sácala o elige otro paquete" % paquetes.carpeta(nombre))
        nuevo = paquetes.Paquete(nombre, args.capa, manifiesto["prefijo"], fuente, args.etiqueta, commit,
                                 paquetes.huella(carpeta_del_clon))
        _validar_entrada(lock, nuevo, capas)
        archivos = paquetes.presentes(carpeta_del_clon)
        if args.ensayo:
            print("ensayo: no se escribe nada")
            print("paquete: %s (prefijo %s, capa %s)" % (nombre, nuevo.prefijo, nuevo.capa))
            print("fuente: %s" % nuevo.fuente)
            print("etiqueta: %s (commit %s)" % (nuevo.etiqueta, commit))
            print("archivos que se copian a %s:" % paquetes.carpeta(nombre))
            for archivo in archivos:
                print("  %s (%d bytes)" % (archivo, os.path.getsize(os.path.join(carpeta_del_clon, archivo))))
            print("entrada del lock:")
            print(_entrada_del_lock(nuevo))
            _avisar_si_es_local(fuente, local)
            return 0
        instalar(raiz, nuevo, carpeta_del_clon, lock)
    print("importado: %s (prefijo %s, capa %s), etiqueta %s (commit %s), en %s"
          % (nombre, nuevo.prefijo, nuevo.capa, nuevo.etiqueta, commit[:12], paquetes.carpeta(nombre)))
    print("archivos: %s" % ", ".join(archivos))
    print("lock: %s" % paquetes.LOCK)
    print(REVISAR)
    _avisar_si_es_local(fuente, local)
    return 0


def actualizar(raiz, args):
    capas = _capas(raiz)
    lock = _lock(raiz) or {}
    if args.nombre not in lock:
        raise Rechazo("%s no está en %s" % (args.nombre, paquetes.LOCK))
    actual = lock[args.nombre]
    _sin_enlaces_en_el_destino(raiz, actual.nombre)
    otros = {nombre: paquete for nombre, paquete in lock.items() if nombre != args.nombre}
    with clon(actual.fuente, args.etiqueta, raiz) as (commit, carpeta_del_clon):
        manifiesto = validar_clon(carpeta_del_clon)
        if manifiesto["nombre"] != actual.nombre:
            raise Rechazo("el manifiesto dice nombre %s y el lock %s" % (manifiesto["nombre"], actual.nombre))
        nuevo = actual._replace(prefijo=manifiesto["prefijo"], etiqueta=args.etiqueta, commit=commit,
                                huella=paquetes.huella(carpeta_del_clon))
        _validar_entrada(otros, nuevo, capas)
        lineas = cambios(os.path.join(raiz, paquetes.carpeta(actual.nombre)), carpeta_del_clon)
        resumen = "%s, etiqueta %s -> %s (commit %s -> %s)" % (actual.nombre, actual.etiqueta, nuevo.etiqueta, actual.commit[:12],
                                                               commit[:12])
        if args.ensayo:
            print("ensayo: no se escribe nada")
            print("paquete: %s" % resumen)
            for linea in lineas:
                print(linea)
            print("entrada del lock:")
            print(_entrada_del_lock(nuevo))
            return 0
        instalar(raiz, nuevo, carpeta_del_clon, otros)
    print("actualizado: %s" % resumen)
    for linea in lineas:
        print(linea)
    print(REVISAR)
    return 0


def quitar(raiz, args):
    lock = _lock(raiz) or {}
    if args.nombre not in lock:
        raise Rechazo("%s no está en %s" % (args.nombre, paquetes.LOCK))
    resto = {nombre: paquete for nombre, paquete in lock.items() if nombre != args.nombre}
    paquetes.escribir_lock(raiz, resto)
    _borrar(os.path.join(raiz, paquetes.carpeta(args.nombre)))
    print("quitado: %s (%s y su entrada en el lock)" % (args.nombre, paquetes.carpeta(args.nombre)))
    if not resto:
        print("el lock quedó vacío: se borró %s" % paquetes.LOCK)
    return 0


def listar(raiz, args):
    lock = _lock(raiz)
    if lock is None:
        print("no hay paquetes: no existe %s" % paquetes.LOCK)
        return 0
    if not lock:
        print("no hay paquetes en %s" % paquetes.LOCK)
    for paquete in sorted(lock.values(), key=lambda paquete: paquete.nombre):
        carpeta = os.path.join(raiz, paquetes.carpeta(paquete.nombre))
        if not os.path.isdir(carpeta):
            estado = "sin carpeta"
        else:
            estado = "al día" if paquetes.huella(carpeta) == paquete.huella else "no coincide"
        print("%s  capa %s  prefijo %s  etiqueta %s  commit %s  huella %s"
              % (paquete.nombre, paquete.capa, paquete.prefijo, paquete.etiqueta, paquete.commit[:12], estado))
    return 0


COMANDOS = {"importar": importar, "actualizar": actualizar, "quitar": quitar, "listar": listar}


def construir_parser():
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--raiz", help="raíz de la instancia (por defecto, la de la sesión)")
    p = argparse.ArgumentParser(prog="paquetes.py", allow_abbrev=False,
                                description="Paquetes de reglas importados desde git por etiqueta: los copia a %s/<nombre> y los "
                                            "fija en %s. Nunca ejecuta código del paquete." % (paquetes.carpeta("").rstrip("/"),
                                                                                              paquetes.LOCK))
    sub = p.add_subparsers(dest="comando", metavar="{importar,actualizar,quitar,listar}")
    sub.required = True
    importar_ = sub.add_parser("importar", parents=[comun], allow_abbrev=False,
                               help="trae un paquete de <fuente> en la etiqueta dada y lo suma a una capa")
    importar_.add_argument("fuente", help="URL o ruta del repo git del paquete")
    importar_.add_argument("--etiqueta", required=True, help="etiqueta (tag) del repo; una rama o un hash no valen")
    importar_.add_argument("--capa", required=True, help="capa declarada en %s, con rule_prefix" % CONFIG)
    importar_.add_argument("--ensayo", action="store_true", help="muestra el plan sin escribir nada")
    actualizar_ = sub.add_parser("actualizar", parents=[comun], allow_abbrev=False,
                                 help="lleva un paquete del lock a otra etiqueta de su misma fuente")
    actualizar_.add_argument("nombre")
    actualizar_.add_argument("--etiqueta", required=True)
    actualizar_.add_argument("--ensayo", action="store_true", help="muestra qué cambia sin escribir nada")
    quitar_ = sub.add_parser("quitar", parents=[comun], allow_abbrev=False, help="borra la carpeta del paquete y su entrada del lock")
    quitar_.add_argument("nombre")
    sub.add_parser("listar", parents=[comun], allow_abbrev=False, help="cada paquete con su capa, prefijo, etiqueta, commit y huella")
    return p


def main(argv=None):
    try:
        args = construir_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        raiz = args.raiz or raiz_de_instancia(os.environ, os.getcwd())
        if raiz is None:
            raise ErrorEntorno("no hay %s en la carpeta de la sesión ni en sus padres (pasa --raiz)" % CONFIG)
        raiz = str(raiz)
        if not os.path.isfile(os.path.join(raiz, CONFIG)):
            raise ErrorEntorno("no hay %s en %s" % (CONFIG, raiz))
        return COMANDOS[args.comando](raiz, args)
    except Rechazo as exc:
        print("paquetes: %s" % exc, file=sys.stderr)
        return 1
    except ErrorEntorno as exc:
        print("paquetes: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("paquetes: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("paquetes: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
