import sys

sys.dont_write_bytecode = True

import argparse
import os
import runpy
import traceback
from pathlib import Path

import config_loader
from odd_ws import capas as convencion
from odd_ws.comun import cargar_por_ruta, decodificar, lineas, raiz_de_instancia
from verificar_capa import es_hallazgo

IGNORADAS = (".git", "node_modules")
TOPE_DETALLE = 20


class ErrorEntorno(Exception):
    pass


def _capa(raiz, capa):
    if not (Path(raiz) / config_loader.NOMBRE).is_file():
        raise ErrorEntorno("no hay %s en %s" % (config_loader.NOMBRE, raiz))
    try:
        declaradas = config_loader.capas(raiz)
    except config_loader.ConfigRota as exc:
        raise ErrorEntorno("%s roto: %s" % (config_loader.NOMBRE, exc))
    if capa not in declaradas:
        raise ErrorEntorno("la capa %s no esta declarada en %s (capas: %s)"
                           % (capa, config_loader.NOMBRE, ", ".join(declaradas)))
    return declaradas[capa]


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


def ctx_de(carpeta, ruta, capa):
    crudo = Path(ruta).read_bytes()
    texto = decodificar(crudo)
    agregadas = lineas(texto)
    relativa = Path(ruta).relative_to(carpeta).as_posix()
    return {
        "ruta": os.path.abspath(ruta), "relativa": relativa, "relativa_repo": relativa,
        "origen": "repo", "capa": capa, "bytes": crudo, "texto": texto, "es_nuevo": True,
        "agregadas": agregadas, "hunks": [{"agregadas": agregadas, "quitadas": []}] if agregadas else [],
        "limite": None,
    }


def _ids(modulo, errores):
    reglas = getattr(modulo, "REGLAS", None)
    if reglas is None:
        return None
    try:
        return [regla.id for regla in reglas]
    except (TypeError, AttributeError):
        errores.append("REGLAS del modulo no es una secuencia de objetos con id")
        return []


def calibrar(ruta_modulo, capa, carpeta, extensiones, detalle):
    try:
        modulo = cargar_por_ruta(ruta_modulo, "reglas_modulo_%s" % capa)
    except Exception as exc:
        print("reglas: no se pudo cargar %s: %s: %s" % (ruta_modulo, type(exc).__name__, exc), file=sys.stderr)
        return 1
    errores = []
    ctxs = [ctx_de(carpeta, ruta, capa) for ruta in archivos_de(carpeta, extensiones)]
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
            por_regla.setdefault(h["id"], []).append((ctx["relativa"], h.get("linea"), h.get("fragmento")))
    for id_, aciertos in por_regla.items():
        print("%s archivos=%d aciertos=%d" % (id_, len({a[0] for a in aciertos}), len(aciertos)))
        if detalle:
            for relativa, linea, fragmento in aciertos[:TOPE_DETALLE]:
                print("  %s:%d%s" % (relativa, linea or 0, " " + fragmento if fragmento else ""))
    if ids is None:
        print("reglas: el modulo de la capa %s no declara REGLAS: las reglas con 0 aciertos no aparecen" % capa,
              file=sys.stderr)
    for error in errores:
        print("reglas: %s" % error, file=sys.stderr)
    return 1 if errores else 0


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


def construir_parser():
    p = argparse.ArgumentParser(prog="reglas.py", allow_abbrev=False,
                                description="Corridas sueltas del modulo de una capa de la instancia: su suite y su calibracion.")
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--test", metavar="CAPA",
                      help="corre %s como __main__ y sale con su codigo" % convencion.prueba("<capa>"))
    modo.add_argument("--calibrar", nargs=2, metavar=("CAPA", "CARPETA"),
                      help="pasa los archivos de la capa bajo CARPETA por %s como nuevos y cuenta los aciertos por regla"
                      % convencion.chequeo("<capa>"))
    p.add_argument("--detalle", action="store_true",
                   help="con --calibrar: <relativa>:<linea> <fragmento> por acierto (hasta %d por regla)" % TOPE_DETALLE)
    p.add_argument("--raiz", help="raiz de la instancia (por defecto, la de la sesion)")
    return p


def main(argv=None):
    parser = construir_parser()
    try:
        args = parser.parse_args(argv)
        if args.detalle and not args.calibrar:
            parser.error("--detalle solo va con --calibrar")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    capa = args.test or args.calibrar[0]
    try:
        raiz = args.raiz or raiz_de_instancia(os.environ, os.getcwd())
        if raiz is None:
            raise ErrorEntorno("no hay %s en la carpeta de la sesion ni en sus padres (pasa --raiz)" % config_loader.NOMBRE)
        datos = _capa(raiz, capa)
        if args.test:
            suite = _existente(raiz, convencion.prueba(capa), "suite", capa)
        else:
            carpeta = args.calibrar[1]
            if not os.path.isdir(carpeta):
                raise ErrorEntorno("%s no es una carpeta" % carpeta)
            modulo = _existente(raiz, convencion.chequeo(capa), "modulo", capa)
    except ErrorEntorno as exc:
        print("reglas: %s" % exc, file=sys.stderr)
        return 2
    if args.test:
        return correr_suite(suite)
    return calibrar(modulo, capa, carpeta, {e.lower() for e in datos["extensions"]}, args.detalle)


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
