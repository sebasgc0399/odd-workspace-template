import sys

sys.dont_write_bytecode = True

import argparse
import datetime
import os
import runpy
import subprocess
import traceback
from collections import namedtuple
from pathlib import Path

import config_loader
from odd_ws import calibracion
from odd_ws import capas as convencion
from odd_ws import paquetes
from odd_ws.comun import cargar_por_ruta, decodificar, entorno_git, lineas, raiz_de_instancia
from verificar_capa import es_hallazgo

IGNORADAS = (".git", "node_modules")
TOPE_DETALLE = 20
TODAS = object()
TOPE_DE_UNA_SUITE_DE_PAQUETE = 300
TOPE_DE_GIT = 10
SEMBRADO = "sembrado"
FALLAS_DE_UN_PAQUETE = (Exception, SystemExit)
Guardado = namedtuple("Guardado", ("raiz", "extension", "previas", "paquetes"))
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ARRANQUE_DE_UNA_SUITE = ("import runpy, sys\n"
                         "sys.dont_write_bytecode = True\n"
                         "for flujo in (sys.stdout, sys.stderr):\n"
                         "    flujo.reconfigure(encoding='utf-8', errors='replace', newline='\\n')\n"
                         "sys.path.insert(0, sys.argv[1])\n"
                         "sys.argv = sys.argv[2:]\n"
                         "runpy.run_path(sys.argv[0], run_name='__main__')\n")


class ErrorEntorno(Exception):
    pass


def _declaradas(raiz):
    if not (Path(raiz) / config_loader.NOMBRE).is_file():
        raise ErrorEntorno("no hay %s en %s" % (config_loader.NOMBRE, raiz))
    try:
        return config_loader.capas(raiz)
    except config_loader.ConfigRota as exc:
        raise ErrorEntorno("%s roto: %s" % (config_loader.NOMBRE, exc))


def _capa(raiz, capa):
    declaradas = _declaradas(raiz)
    if capa not in declaradas:
        raise ErrorEntorno("la capa %s no esta declarada en %s (capas: %s)"
                           % (capa, config_loader.NOMBRE, ", ".join(declaradas)))
    return declaradas[capa]


def _lock(raiz, capas):
    try:
        return paquetes.leer_lock_contra(raiz, capas) or {}
    except paquetes.LockRoto as exc:
        raise ErrorEntorno("%s roto: %s" % (paquetes.LOCK, exc))


def _existente(raiz, relativa, que, capa):
    ruta = Path(raiz) / relativa
    if not ruta.is_file():
        raise ErrorEntorno("la capa %s no tiene %s: no existe %s" % (capa, que, relativa))
    return ruta


def archivos_de(carpeta, extensiones):
    res = []
    for actual, subcarpetas, archivos in os.walk(carpeta):
        subcarpetas[:] = sorted(d for d in subcarpetas if d not in IGNORADAS)
        res += [os.path.join(actual, a) for a in sorted(archivos) if os.path.splitext(a)[1].lower() in extensiones]
    return res


def _ctx(ruta, relativa, crudo, capa):
    texto = decodificar(crudo)
    agregadas = lineas(texto)
    return {
        "ruta": ruta, "relativa": relativa, "relativa_repo": relativa,
        "origen": "repo", "capa": capa, "bytes": crudo, "texto": texto, "es_nuevo": True,
        "agregadas": agregadas, "hunks": [{"agregadas": agregadas, "quitadas": []}] if agregadas else [],
        "limite": None,
    }


def ctx_de(carpeta, ruta, capa):
    crudo = Path(ruta).read_bytes()
    return _ctx(os.path.abspath(ruta), Path(ruta).relative_to(carpeta).as_posix(), crudo, capa)


def _ids(modulo, errores):
    reglas = getattr(modulo, "REGLAS", None)
    if reglas is None:
        return None
    try:
        return [regla.id for regla in reglas]
    except (TypeError, AttributeError):
        errores.append("REGLAS del modulo no es una secuencia de objetos con id")
        return []


def _commit(carpeta):
    try:
        r = subprocess.run(["git", "-C", carpeta, "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True,
                           timeout=TOPE_DE_GIT, env=entorno_git())
    except (OSError, subprocess.SubprocessError):
        return None
    commit = r.stdout.decode("ascii", errors="replace").strip()
    return commit if r.returncode == 0 and calibracion.COMMIT_RE.fullmatch(commit) else None


def _corpus(raiz, carpeta):
    real = os.path.realpath(carpeta)
    nombre = {"repo": None, "commit": None, "ruta": os.path.basename(real) or "raiz"}
    try:
        repos = config_loader.cargar(raiz)["repos"]
    except config_loader.ConfigRota as exc:
        print("reglas: aviso, no se pudieron leer los repos declarados (%s): el corpus queda registrado solo por su nombre (%s)"
              % (exc, nombre["ruta"]), file=sys.stderr)
        return nombre
    canonica = config_loader.canonica(real)
    arboles = [(len(config_loader.canonica(arbol)), clave, arbol) for clave, repo in repos.items()
               for arbol in [repo["path"], *repo.get("worktrees", [])]
               if config_loader._dentro(canonica, config_loader.canonica(arbol))]
    if not arboles:
        print("reglas: aviso, %s no esta en ningun repo declarado: el corpus queda registrado solo por su nombre (%s)"
              % (carpeta, nombre["ruta"]), file=sys.stderr)
        return nombre
    _, clave, arbol = max(arboles)
    return {"repo": clave, "commit": _commit(real), "ruta": Path(os.path.relpath(real, os.path.realpath(arbol))).as_posix()}


def _atrapa(modulo, id_, sembrado, capa, carpeta, extension, errores, fallas=Exception):
    relativa = SEMBRADO + extension
    ctx = _ctx(os.path.join(os.path.abspath(carpeta), relativa), relativa, sembrado.encode("utf-8"), capa)
    try:
        hallazgos = list(modulo.verificar(ctx))
    except fallas as exc:
        errores.append("sembrado de %s: %s: %s" % (id_, type(exc).__name__, exc))
        return False
    invalidos = [h for h in hallazgos if not es_hallazgo(h)]
    for h in invalidos:
        errores.append("sembrado de %s: hallazgo invalido %r" % (id_, h))
    return not invalidos and any(h["id"] == id_ for h in hallazgos)


def _disputas(raiz):
    try:
        return calibracion.disputas(raiz)
    except OSError:
        return None


def _veredicto(id_, calibrada, sembrado, abiertas):
    if sembrado is None:
        return "solo avisa: sin sembrado"
    if not calibrada["atrapa_su_sembrado"]:
        return "solo avisa: no atrapa su sembrado"
    if calibrada["aciertos_en_bloqueo"]:
        return "solo avisa: %d aciertos en bloqueo en el corpus" % calibrada["aciertos_en_bloqueo"]
    if abiertas is None:
        return "solo avisa: %s no se puede leer" % calibracion.DISPUTAS
    if str(id_).upper() in abiertas:
        return "solo avisa: disputada (%s/%s.md)" % (calibracion.DISPUTAS, id_)
    return "puede bloquear"


def _no_se_guarda(errores):
    for error in errores:
        print("reglas: %s" % error, file=sys.stderr)
    print("reglas: hubo errores, asi que no se guarda la calibracion", file=sys.stderr)
    return 1


def _mostrar(por_regla, detalle):
    for id_, aciertos in por_regla.items():
        print("%s archivos=%d aciertos=%d" % (id_, len({a[0] for a in aciertos}), len(aciertos)))
        if detalle:
            for relativa, linea, fragmento, _ in aciertos[:TOPE_DETALLE]:
                print("  %s:%d%s" % (relativa, linea or 0, " " + fragmento if fragmento else ""))


def _calibrar_paquete(raiz, paquete, capa, carpeta, archivos, detalle, extension):
    relativa = "%s/%s" % (paquetes.carpeta(paquete.nombre), paquetes.MODULO)
    print("== %s/%s: %s" % (capa, paquete.nombre, relativa))
    if paquetes.huella(os.path.join(raiz, paquetes.carpeta(paquete.nombre))) != paquete.huella:
        return None, ["no coincide con la huella de su lock: lo copiado cambio desde que se importo (reimportalo antes de calibrar)"]
    sufijo = paquete.nombre.replace("-", "_")
    try:
        modulo = cargar_por_ruta(os.path.join(raiz, relativa), "reglas_paquete_%s" % sufijo)
    except FALLAS_DE_UN_PAQUETE as exc:
        return None, ["no se pudo cargar %s: %s: %s" % (relativa, type(exc).__name__, exc)]
    errores = []
    ctxs = [ctx_de(carpeta, ruta, capa) for ruta in archivos]
    precalcular = getattr(modulo, "precalcular", None)
    if callable(precalcular):
        try:
            precalcular(ctxs)
        except FALLAS_DE_UN_PAQUETE as exc:
            errores.append("precalcular: %s: %s" % (type(exc).__name__, exc))
    ids = _ids(modulo, errores)
    por_regla = {id_: [] for id_ in ids or []}
    for ctx in ctxs:
        try:
            hallazgos = list(modulo.verificar(ctx))
        except FALLAS_DE_UN_PAQUETE as exc:
            errores.append("%s: %s: %s" % (ctx["relativa"], type(exc).__name__, exc))
            continue
        for h in hallazgos:
            if not (es_hallazgo(h) and paquetes.id_del_paquete(paquete.prefijo, h["id"])):
                errores.append("%s: hallazgo invalido %r" % (ctx["relativa"], h))
                continue
            por_regla.setdefault(h["id"], []).append((ctx["relativa"], h.get("linea"), h.get("fragmento"), h.get("modo")))
    _mostrar(por_regla, detalle)
    if errores:
        return None, errores
    if ids is None:
        print("reglas: el paquete %s no declara REGLAS: no se calibra, y sus reglas solo avisan" % paquete.nombre, file=sys.stderr)
        return None, []
    try:
        fresco = cargar_por_ruta(os.path.join(raiz, relativa), "reglas_sembrado_paquete_%s" % sufijo)
    except FALLAS_DE_UN_PAQUETE as exc:
        return None, ["no se pudo cargar %s: %s: %s" % (relativa, type(exc).__name__, exc)]
    sembrados = calibracion.sembrados(fresco)
    atrapa = {id_: sembrados.get(id_) is not None
              and _atrapa(fresco, id_, sembrados[id_], capa, carpeta, extension, errores, FALLAS_DE_UN_PAQUETE) for id_ in ids}
    return (paquete.nombre, paquete.huella, ids, sembrados, atrapa, por_regla), errores


def guardar(ruta_modulo, capa, carpeta, ids, por_regla, archivos, errores, guardado, detalle):
    if errores:
        return _no_se_guarda([])
    calibradas = []
    if ruta_modulo is not None:
        if ids is None:
            print("reglas: el modulo de la capa %s no declara REGLAS: no se guarda la calibracion" % capa, file=sys.stderr)
            return 2
        try:
            modulo = cargar_por_ruta(ruta_modulo, "reglas_sembrado_%s" % capa)
        except Exception as exc:
            return _no_se_guarda(["no se pudo cargar %s: %s: %s" % (ruta_modulo, type(exc).__name__, exc)])
        sembrados = calibracion.sembrados(modulo)
        atrapa = {id_: sembrados.get(id_) is not None
                  and _atrapa(modulo, id_, sembrados[id_], capa, carpeta, guardado.extension, errores) for id_ in ids}
        if errores:
            return _no_se_guarda(errores)
        calibradas.append((None, calibracion.huella_del_archivo(ruta_modulo), ids, sembrados, atrapa, por_regla))
    for paquete in guardado.paquetes:
        calibrada, propios = _calibrar_paquete(guardado.raiz, paquete, capa, carpeta, archivos, detalle, guardado.extension)
        errores += ["paquete %s: %s" % (paquete.nombre, error) for error in propios]
        if calibrada is not None:
            calibradas.append(calibrada)
    if errores:
        return _no_se_guarda(errores)
    comun = {"archivos_del_corpus": len(archivos), "corpus": _corpus(guardado.raiz, carpeta), "fecha": datetime.date.today().isoformat()}
    capas, de_paquetes = dict(guardado.previas.capas), dict(guardado.previas.paquetes)
    capas.pop(capa, None)
    de_paquetes[capa] = {}
    veredictos = []
    for nombre, huella, ids_, sembrados, atrapa, por_regla_ in calibradas:
        reglas = {id_: dict(comun, huella=huella, atrapa_su_sembrado=atrapa[id_], aciertos=len(por_regla_[id_]),
                            aciertos_en_bloqueo=sum(1 for acierto in por_regla_[id_] if acierto[3] == "bloqueo")) for id_ in ids_}
        if nombre is None:
            capas[capa] = reglas
        else:
            de_paquetes[capa][nombre] = reglas
        veredictos += [(id_, reglas[id_], sembrados.get(id_)) for id_ in ids_]
    calibracion.escribir(guardado.raiz, capas, de_paquetes)
    print("calibracion guardada en %s" % calibracion.RUTA)
    abiertas = _disputas(guardado.raiz)
    for id_, calibrada, sembrado in veredictos:
        print("%s %s" % (id_, _veredicto(id_, calibrada, sembrado, abiertas)))
    return 0


def calibrar(ruta_modulo, capa, carpeta, extensiones, detalle, guardado=None):
    if ruta_modulo is None:
        return guardar(None, capa, carpeta, None, {}, archivos_de(carpeta, extensiones), [], guardado, detalle)
    try:
        modulo = cargar_por_ruta(ruta_modulo, "reglas_modulo_%s" % capa)
    except Exception as exc:
        print("reglas: no se pudo cargar %s: %s: %s" % (ruta_modulo, type(exc).__name__, exc), file=sys.stderr)
        return 1
    errores = []
    archivos = archivos_de(carpeta, extensiones)
    ctxs = [ctx_de(carpeta, ruta, capa) for ruta in archivos]
    precalcular = getattr(modulo, "precalcular", None)
    if callable(precalcular):
        try:
            precalcular(ctxs)
        except Exception as exc:
            errores.append("precalcular: %s: %s" % (type(exc).__name__, exc))
    ids = _ids(modulo, errores)
    por_regla = {id_: [] for id_ in ids or []}
    for ctx in ctxs:
        try:
            hallazgos = modulo.verificar(ctx)
        except Exception as exc:
            errores.append("%s: %s: %s" % (ctx["relativa"], type(exc).__name__, exc))
            continue
        for h in hallazgos:
            if not es_hallazgo(h):
                errores.append("%s: hallazgo invalido %r" % (ctx["relativa"], h))
                continue
            por_regla.setdefault(h["id"], []).append((ctx["relativa"], h.get("linea"), h.get("fragmento"), h.get("modo")))
    _mostrar(por_regla, detalle)
    if ids is None:
        print("reglas: el modulo de la capa %s no declara REGLAS: las reglas con 0 aciertos no aparecen" % capa,
              file=sys.stderr)
    for error in errores:
        print("reglas: %s" % error, file=sys.stderr)
    if guardado is None:
        return 1 if errores else 0
    return guardar(ruta_modulo, capa, carpeta, ids, por_regla, archivos, errores, guardado, detalle)


def correr_suite(suite):
    previo = sys.argv
    sys.argv = [str(suite)]
    try:
        runpy.run_path(str(suite), run_name="__main__")
    except SystemExit as exc:
        if exc.code is None or isinstance(exc.code, int):
            return exc.code or 0
        print(exc.code, file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        sys.argv = previo
    return 0


def _volcar(salida, error):
    for crudo, flujo in ((salida, sys.stdout), (error, sys.stderr)):
        if crudo:
            flujo.write(crudo.decode("utf-8", errors="replace").replace("\r\n", "\n"))
            flujo.flush()


def correr_suite_de_paquete(raiz, paquete, relativa):
    malos = paquetes.enlaces(raiz, paquete.nombre)
    if malos:
        print("reglas: %s: enlace o fuera de su carpeta, no se corre" % ", ".join(malos), file=sys.stderr)
        return 1
    sys.stdout.flush()
    try:
        r = subprocess.run([sys.executable, "-I", "-c", ARRANQUE_DE_UNA_SUITE, SCRIPTS, str(Path(raiz) / relativa)],
                           capture_output=True, timeout=TOPE_DE_UNA_SUITE_DE_PAQUETE)
    except subprocess.TimeoutExpired as exc:
        _volcar(exc.stdout, exc.stderr)
        print("reglas: la suite %s no termino en %s s" % (relativa, TOPE_DE_UNA_SUITE_DE_PAQUETE), file=sys.stderr)
        return 1
    except OSError as exc:
        print("reglas: no se pudo correr la suite %s: %s" % (relativa, exc), file=sys.stderr)
        return 1
    _volcar(r.stdout, r.stderr)
    return r.returncode


def suites_de(capas, lock):
    suites = []
    for capa in capas:
        suites.append((capa, convencion.prueba(capa), None))
        suites += [("%s/%s" % (capa, paquete.nombre), "%s/%s" % (paquetes.carpeta(paquete.nombre), paquetes.SUITE), paquete)
                   for paquete in paquetes.de_la_capa(lock, capa)]
    return suites


def correr_todas(raiz, capas, lock=None):
    suites = suites_de(capas, lock or {})
    con = [suite for suite in suites if (Path(raiz) / suite[1]).is_file()]
    sin = [suite[0] for suite in suites if suite not in con]
    if sin:
        print("sin suite: %s" % ", ".join(sin))
    if not con:
        print("ninguna capa tiene suite")
        return 0
    rojas = []
    for nombre, relativa, paquete in con:
        print("== %s: %s" % (nombre, relativa))
        codigo = correr_suite(Path(raiz) / relativa) if paquete is None else correr_suite_de_paquete(raiz, paquete, relativa)
        if codigo != 0:
            rojas.append(nombre)
    print("suites en rojo: %s" % ", ".join(rojas) if rojas else "suites: %d, todas en verde" % len(con))
    return 1 if rojas else 0


def construir_parser():
    p = argparse.ArgumentParser(prog="reglas.py", allow_abbrev=False,
                                description="Corridas sueltas del modulo de una capa de la instancia: su suite y su calibracion.")
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--test", nargs="?", const=TODAS, metavar="CAPA",
                      help="corre %s como __main__ y sale con su codigo; sin CAPA, la suite de cada capa que tenga una. "
                      "Con paquetes en %s, corre tambien %s de cada paquete de la capa, tras la suya y en su propio "
                      "proceso (tope de %d s), y sale con 1 si alguna queda en rojo"
                      % (convencion.prueba("<capa>"), paquetes.LOCK, "%s/%s" % (paquetes.carpeta("<paquete>"), paquetes.SUITE),
                         TOPE_DE_UNA_SUITE_DE_PAQUETE))
    modo.add_argument("--calibrar", nargs=2, metavar=("CAPA", "CARPETA"),
                      help="pasa los archivos de la capa bajo CARPETA por %s como nuevos y cuenta los aciertos por regla"
                      % convencion.chequeo("<capa>"))
    p.add_argument("--detalle", action="store_true",
                   help="con --calibrar: <relativa>:<linea> <fragmento> por acierto (hasta %d por regla)" % TOPE_DETALLE)
    p.add_argument("--guardar", action="store_true",
                   help="con --calibrar: guarda en %s, por cada regla de REGLAS, la huella del modulo, si atrapa su sembrado, "
                   "los aciertos y el corpus. Calibra tambien cada paquete de la capa en %s, aparte y con la huella de su lock; "
                   "una capa sin modulo propio calibra solo sus paquetes. Una regla bloquea solo con esa calibracion al dia y sin "
                   "disputa abierta en %s. No guarda si hubo errores (sale con 1) ni si el modulo no declara REGLAS (sale con 2)"
                   % (calibracion.RUTA, paquetes.LOCK, calibracion.DISPUTAS))
    p.add_argument("--raiz", help="raiz de la instancia (por defecto, la de la sesion)")
    return p


def _previas(raiz):
    try:
        return calibracion.cargar(raiz)
    except calibracion.RegistroRoto as exc:
        raise ErrorEntorno("%s roto: %s (arreglalo o borralo y volve a calibrar)" % (calibracion.RUTA, exc))


def _activos(raiz, capa):
    declaradas = _declaradas(raiz)
    _lock(raiz, declaradas)
    return paquetes.activos(raiz, capa, declaradas)


def main(argv=None):
    parser = construir_parser()
    try:
        args = parser.parse_args(argv)
        if args.detalle and not args.calibrar:
            parser.error("--detalle solo va con --calibrar")
        if args.guardar and not args.calibrar:
            parser.error("--guardar solo va con --calibrar")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    capa = args.calibrar[0] if args.calibrar else args.test
    try:
        raiz = args.raiz or raiz_de_instancia(os.environ, os.getcwd())
        if raiz is None:
            raise ErrorEntorno("no hay %s en la carpeta de la sesion ni en sus padres (pasa --raiz)" % config_loader.NOMBRE)
        if capa is TODAS:
            declaradas = _declaradas(raiz)
            capas = list(declaradas)
            lock = _lock(raiz, declaradas)
        else:
            datos = _capa(raiz, capa)
            if args.test:
                lock = _lock(raiz, _declaradas(raiz))
                if not paquetes.de_la_capa(lock, capa):
                    suite = _existente(raiz, convencion.prueba(capa), "suite", capa)
            else:
                carpeta = args.calibrar[1]
                if not os.path.isdir(carpeta):
                    raise ErrorEntorno("%s no es una carpeta" % carpeta)
                activos = _activos(raiz, capa) if args.guardar else []
                sin_modulo = bool(activos) and not (Path(raiz) / convencion.chequeo(capa)).is_file()
                modulo = None if sin_modulo else _existente(raiz, convencion.chequeo(capa), "modulo", capa)
                guardado = Guardado(raiz, datos["extensions"][0].lower(), _previas(raiz), activos) if args.guardar else None
    except ErrorEntorno as exc:
        print("reglas: %s" % exc, file=sys.stderr)
        return 2
    if capa is TODAS:
        return correr_todas(raiz, capas, lock)
    if args.test:
        return correr_todas(raiz, [capa], lock) if paquetes.de_la_capa(lock, capa) else correr_suite(suite)
    return calibrar(modulo, capa, carpeta, {e.lower() for e in datos["extensions"]}, args.detalle, guardado)


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("reglas: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
