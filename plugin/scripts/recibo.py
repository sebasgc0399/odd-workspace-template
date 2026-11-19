import sys

sys.dont_write_bytecode = True

import argparse
import codecs
import datetime
import hashlib
import json
import os
import re
import subprocess

from odd_ws.comun import entorno_git

VERSION = 1
TIMEOUT_GIT = 120
MODOS = ("0", "rapido", "completo")
FECHA_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
CARPETA_RE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})-(0|rapido|completo)(?:-([2-9]|[1-9][0-9]+))?")
RONDA_RE = re.compile(r"[1-9][0-9]*")
ESTADOS = ("limpio", "con-hallazgos", "pendiente")
AJENAS_A_SELLAR = ("ticket", "repo", "archivo", "modo", "recibo", "reviewer", "verificacion", "estado", "fecha", "ronda",
                   "previo", "derivado", "bajada", "va_a_lider")
SOLO_DE_WRITE = ("previo", "derivado", "bajada", "va_a_lider")
BAJADA = ("completo", "rapido")
TRIAJE = ("entrada", "triaje.json")
MODOS_DEL_TRIAJE = ("sin-cambios",) + MODOS
NIVELES = ("positiva", "negativa", "invalida")
AUSENTE = hashlib.sha256(b"<ausente>").hexdigest()
REMOTO_HEAD = "refs/remotes/origin/HEAD"
OPCIONES_DIFF = (
    "--no-color", "--no-ext-diff", "--no-renames", "--no-textconv", "--binary",
    "--diff-algorithm=myers", "--indent-heuristic", "--inter-hunk-context=0", "-U3",
    "--src-prefix=a/", "--dst-prefix=b/",
)
CONFIG_FIJA = (
    "-c", "core.quotepath=false", "-c", "diff.suppressBlankEmpty=false", "-c", "color.ui=false",
    "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false", "-c", "diff.renames=false",
)


class ErrorUso(Exception):
    pass


class ErrorEntorno(Exception):
    pass


def _entorno():
    env = entorno_git()
    for clave in ("GIT_DIFF_OPTS", "GIT_EXTERNAL_DIFF", "GIT_PAGER"):
        env.pop(clave, None)
    return env


def git(repo, *args):
    try:
        return subprocess.run(["git", *CONFIG_FIJA, "-C", repo, *args], capture_output=True,
                              timeout=TIMEOUT_GIT, env=_entorno())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ErrorEntorno("no se pudo correr git en %s (%s)" % (repo, exc))


def _texto(proceso):
    return proceso.stdout.decode("utf-8", errors="replace").strip()


def raiz_del_repo(ruta):
    if not os.path.isdir(ruta):
        raise ErrorEntorno("el repo no existe: %s" % ruta)
    r = git(ruta, "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        raise ErrorEntorno("no es un repo git: %s" % ruta)
    return _texto(r).replace("\\", "/")


def rama_por_defecto(repo):
    r = git(repo, "symbolic-ref", "--quiet", "--short", REMOTO_HEAD)
    if r.returncode != 0:
        raise ErrorEntorno("%s no tiene origin/HEAD: corre `git remote set-head origin -a` (despues del fetch) "
                           "o pasa la base con --repo RUTA#BASE" % repo)
    rama = _texto(r)
    if git(repo, "rev-parse", "--verify", "--quiet", rama + "^{commit}").returncode != 0:
        raise ErrorEntorno("origin/HEAD de %s apunta a %s, que no existe: corre `git remote set-head origin -a` "
                           "o pasa la base con --repo RUTA#BASE" % (repo, rama))
    return rama


def resolver_base(repo, base=None):
    if base:
        r = git(repo, "rev-parse", "--verify", "--quiet", base + "^{commit}")
        if r.returncode != 0:
            raise ErrorEntorno("la base %s no existe en %s" % (base, repo))
        return _texto(r)
    rama = rama_por_defecto(repo)
    r = git(repo, "merge-base", rama, "HEAD")
    if r.returncode != 0:
        raise ErrorEntorno("no hay merge-base entre %s y HEAD en %s" % (rama, repo))
    return _texto(r)


def normalizar(raiz, ruta):
    if os.path.isabs(ruta):
        ruta = os.path.relpath(os.path.realpath(ruta), os.path.realpath(raiz))
    limpia = os.path.normpath(ruta).replace("\\", "/")
    if limpia == ".." or limpia.startswith("../") or os.path.isabs(limpia) or limpia == ".":
        raise ErrorUso("la ruta %s esta fuera del repo %s" % (ruta, raiz))
    return limpia


def diff_de_ruta(repo, base, rel, permitir_ausente=False):
    completa = os.path.join(repo, rel)
    if os.path.isdir(completa):
        raise ErrorUso("%s es una carpeta: pasa archivos, no carpetas" % rel)
    en_base = git(repo, "cat-file", "-e", "%s:%s" % (base, rel)).returncode == 0
    trackeado = git(repo, "ls-files", "--error-unmatch", "--", rel).returncode == 0
    if en_base or trackeado:
        r = git(repo, "diff", *OPCIONES_DIFF, base, "--", rel)
        if r.returncode != 0:
            raise ErrorEntorno("git diff fallo en %s: %s" % (rel, r.stderr.decode("utf-8", errors="replace")))
        return r.stdout
    if os.path.isfile(completa):
        r = git(repo, "diff", *OPCIONES_DIFF, "--no-index", "--", "/dev/null", rel)
        if r.returncode not in (0, 1):
            raise ErrorEntorno("git diff --no-index fallo en %s: %s" % (rel, r.stderr.decode("utf-8", errors="replace")))
        return r.stdout
    if permitir_ausente:
        return None
    raise ErrorUso("%s no existe en %s (ni en la base, ni trackeado, ni en el working tree)" % (rel, repo))


def calcular(repo, base, rutas, permitir_ausentes=False):
    raiz = raiz_del_repo(repo)
    base = resolver_base(raiz, base)
    archivos = sorted({normalizar(raiz, r) for r in rutas})
    por_archivo, total = {}, hashlib.sha256()
    for rel in archivos:
        diff = diff_de_ruta(raiz, base, rel, permitir_ausentes)
        if diff is None:
            por_archivo[rel] = AUSENTE
            total.update(b"<ausente>\0" + rel.encode("utf-8"))
        else:
            por_archivo[rel] = hashlib.sha256(diff).hexdigest()
            total.update(diff)
    return {"base": base, "archivos": archivos, "sha256": total.hexdigest(), "sha256_por_archivo": por_archivo}


def _partir_repo(texto):
    ruta, _, base = texto.partition("#")
    return ruta, (base or None)


def _clave_ruta(ruta):
    return os.path.normcase(os.path.realpath(ruta))


def asignar(repos, archivos):
    por_repo = {raiz: [] for raiz, _ in repos}
    for archivo in archivos:
        if os.path.isabs(archivo):
            dueno = None
            for raiz, _ in repos:
                clave = _clave_ruta(raiz)
                if _clave_ruta(archivo).startswith(clave + os.sep) or _clave_ruta(archivo) == clave:
                    dueno = raiz
            if dueno is None:
                raise ErrorUso("el archivo %s no es de ninguno de los repos dados" % archivo)
            por_repo[dueno].append(archivo)
        elif len(repos) == 1:
            por_repo[repos[0][0]].append(archivo)
        else:
            raise ErrorUso("con varios --repo, --archivo tiene que ser absoluto (se recibio %s)" % archivo)
    for raiz, lista in por_repo.items():
        if not lista:
            raise ErrorUso("el repo %s no tiene ningun --archivo: el recibo cubre una lista explicita" % raiz)
    return por_repo


def _repos_y_archivos(args):
    if not os.path.isdir(args.ticket):
        raise ErrorUso("la carpeta del ticket no existe: %s" % args.ticket)
    if not args.repo:
        raise ErrorUso("falta al menos un --repo")
    if not args.archivo:
        raise ErrorUso("falta al menos un --archivo: el recibo cubre una lista explicita, no el working tree")
    repos, vistos = [], set()
    for texto in args.repo:
        ruta, base = _partir_repo(texto)
        raiz = raiz_del_repo(ruta)
        if raiz not in vistos:
            vistos.add(raiz)
            repos.append((raiz, base))
    return repos, asignar(repos, args.archivo)


def _entrada(raiz, resultado, args):
    return {
        "ruta": raiz, "base": resultado["base"], "archivos": resultado["archivos"],
        "sha256": resultado["sha256"], "sha256_por_archivo": resultado["sha256_por_archivo"],
        "modo": args.modo, "reviewers": list(args.reviewer or []),
        "verificacion": list(args.verificacion or []), "estado": args.estado,
    }


def armar_recibo(args):
    repos, por_repo = _repos_y_archivos(args)
    entradas = [_entrada(raiz, calcular(raiz, base, por_repo[raiz]), args) for raiz, base in repos]
    return {"version": VERSION, "fecha": args.fecha, "ticket": os.path.basename(os.path.abspath(args.ticket)),
            "repos": entradas}


def _orden_de_carpeta(m):
    return (m.group(1), MODOS.index(m.group(2)), int(m.group(3) or 1))


def recibo_previo(ticket, previo, carpeta):
    archivo = ubicar_recibo(previo)
    datos = cargar_recibo(archivo)
    suya = os.path.dirname(os.path.abspath(archivo))
    m = CARPETA_RE.fullmatch(os.path.basename(suya))
    if not m or _clave_ruta(os.path.dirname(suya)) != _clave_ruta(os.path.join(ticket, "revision")):
        raise ErrorUso("--previo tiene que ser un recibo de este ticket (%s/revision/<fecha>-<modo>[-<ronda>]/), no %s"
                       % (ticket.replace("\\", "/"), archivo.replace("\\", "/")))
    nueva = CARPETA_RE.fullmatch(os.path.basename(carpeta))
    if _orden_de_carpeta(nueva) <= _orden_de_carpeta(m):
        raise ErrorUso("el rechequeo tiene que quedar despues de revision/%s: misma fecha y modo con --ronda %d, "
                       "o una fecha posterior; si no, --check y --sellar sobre el ticket tomarian el recibo previo"
                       % (m.group(0), _orden_de_carpeta(m)[2] + 1))
    return archivo, datos, "revision/" + m.group(0)


def _informar_sin_escribir(archivo, motivo, malos, arreglo):
    print("recibo NO se escribe (previo %s): %s" % (archivo.replace("\\", "/"), motivo))
    for ruta, cosas in malos:
        print("  repo %s: %s" % (ruta, ", ".join(cosas)))
    print(arreglo)
    return 1


def armar_rechequeo(args, carpeta):
    repos, por_repo = _repos_y_archivos(args)
    archivo, previo, nombre = recibo_previo(args.ticket, args.previo, carpeta)
    dados = {_clave_ruta(raiz): (raiz, base) for raiz, base in repos}
    plan, claves = [], set()
    for previa in previo["repos"]:
        clave = _clave_ruta(previa["ruta"])
        if clave in claves:
            continue
        claves.add(clave)
        raiz, base = dados.get(clave) or (raiz_del_repo(previa["ruta"]), None)
        plan.append((raiz, resolver_base(raiz, base or previa["base"]), por_repo.get(raiz, []), previa))
    for raiz, base in repos:
        if _clave_ruta(raiz) not in claves:
            plan.append((raiz, resolver_base(raiz, base), por_repo[raiz], None))
    otras = [(raiz, ["%s en vez de %s" % (base, previa["base"])]) for raiz, base, _, previa in plan
             if previa and base != previa["base"]]
    if otras:
        return None, _informar_sin_escribir(archivo, "la base no es la del recibo previo", otras,
                                            "un rechequeo parte de la base del recibo previo; con otra base, revisa la unidad entera sin --previo"), None
    partes, cambiados = [], []
    for raiz, base, rutas, previa in plan:
        nombres = sorted({normalizar(raiz, r) for r in rutas})
        previos = sorted(previa["archivos"]) if previa else []
        heredados = [a for a in previos if a not in nombres]
        retirados = [a for a in nombres if a in previos and diff_de_ruta(raiz, base, a, permitir_ausente=True) is None]
        if heredados:
            guardado = previa.get("sha256_por_archivo") or {}
            ahora = calcular(raiz, base, heredados, permitir_ausentes=True)["sha256_por_archivo"]
            distintos = [a for a in heredados if guardado.get(a) != ahora[a]]
            if distintos:
                cambiados.append((raiz, distintos))
        partes.append((raiz, base, [a for a in nombres if a not in retirados], heredados, retirados))
    if cambiados:
        return None, _informar_sin_escribir(archivo, "cambiaron archivos del recibo previo que esta ronda no rechequeo", cambiados,
                                            "rechequealos (van con --archivo) o revisa por que cambiaron"), None
    entradas = []
    for raiz, base, rechequeados, heredados, retirados in partes:
        entrada = _entrada(raiz, calcular(raiz, base, rechequeados + heredados), args)
        entrada.update(rechequeados=rechequeados, heredados=heredados, retirados=retirados)
        entradas.append(entrada)
    return {"version": VERSION, "fecha": args.fecha, "ticket": os.path.basename(os.path.abspath(args.ticket)),
            "previo": nombre, "repos": entradas}, 0, previo.get("bajada")


def leer_triaje(carpeta):
    ruta = os.path.join(carpeta, *TRIAJE)
    nombre = ruta.replace("\\", "/")
    if not os.path.isfile(ruta):
        raise ErrorUso("la bajada se valida contra el triaje de la revision, y no esta: %s (guardalo con triaje.py --json)" % nombre)
    try:
        with open(ruta, "rb") as f:
            crudo = f.read()
        utf16 = crudo.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
        datos = json.loads(crudo.decode("utf-16" if utf16 else "utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ErrorUso("triaje ilegible (%s): %s" % (nombre, exc))
    senales = datos.get("senales") if isinstance(datos, dict) else None
    if not (isinstance(senales, dict) and senales and datos.get("modo") in MODOS_DEL_TRIAJE
            and all(isinstance(s, dict) and s.get("nivel") in NIVELES for s in senales.values())):
        raise ErrorUso("triaje con forma invalida (%s): le faltan el modo o las senales con su nivel" % nombre)
    return datos


def _repos_del_triaje(triaje):
    repos = triaje.get("repos") if isinstance(triaje.get("repos"), list) else []
    return {_clave_ruta(r["ruta"]): (r["ruta"], r.get("base")) for r in repos if isinstance(r, dict) and isinstance(r.get("ruta"), str)}


def leer_triaje_del_diff(carpeta, repos):
    triaje = leer_triaje(carpeta)
    del_triaje = _repos_del_triaje(triaje)
    distintos = []
    for entrada in repos:
        ruta, base = del_triaje.pop(_clave_ruta(entrada["ruta"]), (None, None))
        if ruta is None:
            distintos.append("%s no esta en el triaje" % entrada["ruta"])
        elif base != entrada["base"]:
            distintos.append("%s tiene base %s en el triaje y %s en el recibo" % (entrada["ruta"], base, entrada["base"]))
    distintos += ["%s esta en el triaje y no en el recibo" % ruta for ruta, _ in del_triaje.values()]
    if distintos:
        raise ErrorUso("el triaje de %s no es de este diff: %s; guardalo con triaje.py --json con los mismos --repo y la misma "
                       "base que el recibo" % (os.path.join(carpeta, *TRIAJE).replace("\\", "/"), "; ".join(distintos)))
    return triaje


def riesgos_reales(triaje):
    sin_capa = triaje.get("sin_capa")
    solo_sin_capa = isinstance(sin_capa, dict) and sin_capa.get("unico_motivo_de_capas") is True
    return [id_ for id_, senal in triaje["senales"].items()
            if senal["nivel"] == "positiva" and not (id_ == "capas" and solo_sin_capa)]


def _sin_riesgo_real(carpeta, triaje):
    reales = riesgos_reales(triaje)
    if reales:
        raise ErrorUso("el triaje de %s vio un riesgo real (%s): no se baja, la revision va en completo"
                       % (os.path.join(carpeta, *TRIAJE).replace("\\", "/"), ", ".join("senal %s: positiva" % r for r in reales)))


def bajada_de_la_ronda(args, carpeta, heredada, repos):
    if args.bajada is not None:
        triaje = leer_triaje_del_diff(carpeta, repos)
        if (triaje["modo"], args.modo) != BAJADA:
            raise ErrorUso("una bajada es un solo escalon, de completo a rapido (nunca a 0): el triaje propuso %s y --modo es %s"
                           % (triaje["modo"], args.modo))
        _sin_riesgo_real(carpeta, triaje)
        return {"de": triaje["modo"], "a": args.modo, "motivo": args.bajada, "va_a_lider": False}
    if heredada is None:
        return None
    if not (isinstance(heredada, dict) and (heredada.get("de"), heredada.get("a")) == BAJADA
            and isinstance(heredada.get("motivo"), str) and heredada.get("va_a_lider") is False):
        raise ErrorUso("el recibo previo trae una bajada con forma invalida: %s" % json.dumps(heredada, ensure_ascii=False))
    if args.modo != heredada["a"]:
        return None
    _sin_riesgo_real(carpeta, leer_triaje_del_diff(carpeta, repos))
    return heredada


def _avisar_si_pisa(destino, datos):
    if not os.path.isfile(destino):
        return
    try:
        with open(destino, encoding="utf-8-sig") as f:
            viejos = [r["ruta"] for r in json.load(f)["repos"]]
    except (OSError, ValueError, KeyError, TypeError):
        return
    nuevos = {r["ruta"] for r in datos["repos"]}
    perdidos = [r for r in viejos if r not in nuevos]
    if perdidos:
        print("recibo: aviso, el recibo %s se pisa entero y la llamada nueva no trae: %s (pasa todos los --repo en una sola llamada)"
              % (destino.replace("\\", "/"), ", ".join(perdidos)), file=sys.stderr)


def _guardar(destino, datos):
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _detalle(datos):
    detalle = ""
    if "previo" in datos:
        cuenta = {c: sum(len(r[c]) for r in datos["repos"]) for c in ("rechequeados", "heredados", "retirados")}
        detalle = "; %d rechequeado(s) y %d heredado(s) de %s" % (cuenta["rechequeados"], cuenta["heredados"], datos["previo"])
        if cuenta["retirados"]:
            detalle += ", %d retirado(s)" % cuenta["retirados"]
    if "derivados" in datos:
        detalle += "; %d derivado(s)" % len(datos["derivados"])
    if "bajada" in datos:
        detalle += "; bajado de %s a %s" % (datos["bajada"]["de"], datos["bajada"]["a"])
    return detalle


def escribir_recibo(args):
    sufijo = "-%d" % args.ronda if args.ronda and args.ronda > 1 else ""
    carpeta = os.path.join(args.ticket, "revision", "%s-%s%s" % (args.fecha, args.modo, sufijo))
    heredada = None
    if args.previo is not None:
        datos, codigo, heredada = armar_rechequeo(args, carpeta)
        if datos is None:
            return codigo
    else:
        datos = armar_recibo(args)
    bajada = bajada_de_la_ronda(args, carpeta, heredada, datos["repos"])
    if args.derivado:
        datos["derivados"] = list(args.derivado)
    if bajada is not None:
        datos["bajada"] = bajada
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, "recibo.json")
    _avisar_si_pisa(destino, datos)
    _guardar(destino, datos)
    print("recibo escrito: %s (%d repo(s), %d archivo(s)%s)" % (
        destino.replace("\\", "/"), len(datos["repos"]), sum(len(r["archivos"]) for r in datos["repos"]), _detalle(datos)))
    return 0


def _recibos_del_ticket(revision, modo=None):
    hallados = []
    for d in os.listdir(revision):
        m = CARPETA_RE.fullmatch(d)
        candidato = os.path.join(revision, d, "recibo.json")
        if m and (modo is None or m.group(2) == modo) and os.path.isfile(candidato):
            hallados.append((m.group(1), m.group(2), int(m.group(3) or 1), candidato))
    return hallados


def _avisar_carpetas_viejas(revision):
    for d in sorted(os.listdir(revision)):
        candidato = os.path.join(revision, d, "recibo.json")
        if FECHA_RE.fullmatch(d) and os.path.isfile(candidato):
            print("recibo: aviso, se ignora %s (carpeta vieja sin modo; el recibo se escribe en revision/<fecha>-<modo>/)"
                  % candidato.replace("\\", "/"), file=sys.stderr)


def modo_del_recibo(archivo, datos):
    m = CARPETA_RE.fullmatch(os.path.basename(os.path.dirname(os.path.abspath(archivo))))
    if m:
        return m.group(2)
    modos = {e.get("modo") for e in datos["repos"] if isinstance(e, dict)}
    return modos.pop() if len(modos) == 1 else None


def ubicar_recibo(ruta, modo=None):
    if os.path.isfile(ruta):
        return ruta
    if os.path.isdir(ruta):
        directo = os.path.join(ruta, "recibo.json")
        if os.path.isfile(directo):
            return directo
        revision = os.path.join(ruta, "revision")
        if os.path.isdir(revision):
            _avisar_carpetas_viejas(revision)
            candidatas = sorted(_recibos_del_ticket(revision, modo), key=lambda c: (c[0], MODOS.index(c[1]), c[2]))
            if candidatas:
                return candidatas[-1][3]
    raise ErrorUso("no hay un recibo.json en %s" % ruta)


def cargar_recibo(ruta):
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.load(f)
    except (OSError, ValueError) as exc:
        raise ErrorUso("recibo ilegible (%s): %s" % (ruta, exc))
    if not isinstance(datos, dict) or datos.get("version") != VERSION:
        raise ErrorUso("recibo con version desconocida o forma invalida: %s" % ruta)
    repos = datos.get("repos")
    if not isinstance(repos, list) or not repos:
        raise ErrorUso("recibo sin repos: %s" % ruta)
    for entrada in repos:
        if not (isinstance(entrada, dict) and all(k in entrada for k in ("ruta", "base", "archivos", "sha256"))):
            raise ErrorUso("entrada de repo incompleta en %s" % ruta)
    return datos


def divergencias(entrada):
    guardado = entrada.get("sha256_por_archivo") or {}
    actual = calcular(entrada["ruta"], entrada["base"], entrada["archivos"], permitir_ausentes=True)
    distintos = [a for a in actual["archivos"] if guardado.get(a) != actual["sha256_por_archivo"][a]]
    if not distintos and actual["sha256"] != entrada["sha256"]:
        distintos = ["(la lista de archivos o su hash total cambiaron)"]
    return distintos


def chequear_recibo(ruta, modo=None, recibo=None):
    archivo = ubicar_recibo(recibo or ruta, modo)
    datos = cargar_recibo(archivo)
    del_recibo = modo_del_recibo(archivo, datos)
    if modo and del_recibo and modo != del_recibo:
        raise ErrorUso("--modo %s contradice el recibo %s, que es de modo %s" % (modo, archivo.replace("\\", "/"), del_recibo))
    malos, archivos = [], 0
    for entrada in datos["repos"]:
        if not os.path.isdir(entrada["ruta"]):
            raise ErrorEntorno("el repo del recibo ya no existe: %s" % entrada["ruta"])
        distintos = divergencias(entrada)
        archivos += len(entrada["archivos"])
        if distintos:
            malos.append((entrada["ruta"], distintos))
    if malos:
        print("recibo NO vale (%s): cambio el diff revisado" % archivo.replace("\\", "/"))
        for ruta, distintos in malos:
            print("  repo %s: divergen %s" % (ruta, ", ".join(distintos)))
        print("revisa la divergencia y escribe un recibo nuevo con --write")
        return 1
    print("recibo vale: %d repo(s), %d archivo(s) (%s)" % (len(datos["repos"]), archivos, archivo.replace("\\", "/")))
    return 0


def sin_commitear(raiz, head, archivos):
    return [rel for rel in archivos if diff_de_ruta(raiz, head, rel, permitir_ausente=True)]


def fuera_de_lo_revisado(raiz, base, head, archivos):
    r = git(raiz, "diff", "--name-only", "-z", "--no-renames", "--no-ext-diff", base, head)
    if r.returncode != 0:
        raise ErrorEntorno("git diff fallo en %s: %s" % (raiz, r.stderr.decode("utf-8", errors="replace")))
    revisados = set(archivos)
    return sorted(p for p in r.stdout.decode("utf-8", errors="replace").split("\0") if p and p not in revisados)


def _informar_sin_sello(archivo, motivo, malos, arreglo):
    print("recibo NO se sella (%s): %s" % (archivo.replace("\\", "/"), motivo))
    for ruta, archivos in malos:
        print("  repo %s: %s" % (ruta, ", ".join(archivos)))
    print(arreglo)
    return 1


def sellar_recibo(ruta):
    archivo = ubicar_recibo(ruta)
    datos = cargar_recibo(archivo)
    for entrada in datos["repos"]:
        if not os.path.isdir(entrada["ruta"]):
            raise ErrorEntorno("el repo del recibo ya no existe: %s" % entrada["ruta"])
    divergentes = [(e["ruta"], d) for e in datos["repos"] for d in [divergencias(e)] if d]
    if divergentes:
        return _informar_sin_sello(archivo, "cambio el diff revisado", divergentes,
                                   "revisa la divergencia y escribe un recibo nuevo con --write")
    heads = [resolver_base(e["ruta"], "HEAD") for e in datos["repos"]]
    sucios = [(e["ruta"], s) for e, head in zip(datos["repos"], heads) for s in [sin_commitear(e["ruta"], head, e["archivos"])] if s]
    if sucios:
        return _informar_sin_sello(archivo, "hay archivos revisados sin commitear", sucios,
                                   "commitea primero lo revisado y vuelve a sellar")
    ajenos = [(e["ruta"], f) for e, head in zip(datos["repos"], heads)
              for f in [fuera_de_lo_revisado(e["ruta"], e["base"], head, e["archivos"])] if f]
    if ajenos:
        return _informar_sin_sello(archivo, "HEAD trae cambios fuera de lo revisado", ajenos,
                                   "sella justo despues del commit de lo revisado; lo demas va en una revision nueva")
    for entrada, head in zip(datos["repos"], heads):
        entrada["sellado"] = head
    _guardar(archivo, datos)
    print("recibo sellado: %s (%s en %d repo(s))" % (archivo.replace("\\", "/"), ", ".join(h[:10] for h in heads), len(heads)))
    return 0


def _fecha(texto):
    if not FECHA_RE.fullmatch(texto):
        raise argparse.ArgumentTypeError("la fecha tiene que ser AAAA-MM-DD, no %r" % texto)
    try:
        datetime.date.fromisoformat(texto)
    except ValueError:
        raise argparse.ArgumentTypeError("la fecha %r no existe en el calendario" % texto)
    return texto


def _ronda(texto):
    if not RONDA_RE.fullmatch(texto):
        raise argparse.ArgumentTypeError("la ronda tiene que ser un entero desde 1, sin ceros a la izquierda, no %r" % texto)
    return int(texto)


def _derivado(texto):
    hallazgo, igual, destino = texto.rpartition("=")
    if not igual or not hallazgo.strip() or not destino.strip():
        raise argparse.ArgumentTypeError("tiene que ser '<hallazgo>=<destino>', con los dos lados no vacios, no %r" % texto)
    return {"hallazgo": hallazgo.strip(), "destino": destino.strip()}


def _motivo(texto):
    if not texto.strip():
        raise argparse.ArgumentTypeError("la bajada necesita su motivo, no un texto vacio")
    return texto.strip()


def _opcion(nombre):
    return "--" + nombre.replace("_", "-")


def _parser():
    p = argparse.ArgumentParser(prog="recibo.py", description="Recibo de la revision atado al diff.")
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--write", action="store_true", help="escribe <ticket>/revision/<fecha>-<modo>[-<ronda>]/recibo.json")
    modo.add_argument("--check", metavar="RUTA", help="recalcula y compara: recibo.json, carpeta de la revision o del ticket")
    modo.add_argument("--sellar", metavar="RUTA",
                      help="con lo revisado ya commiteado, anota el HEAD de cada repo en el recibo (recibo.json, carpeta de la revision o del ticket)")
    p.add_argument("--ticket", help="carpeta del ticket (con --write)")
    p.add_argument("--repo", action="append", metavar="RUTA[#BASE]", help="repo o worktree; base por defecto: merge-base con la rama de origin/HEAD")
    p.add_argument("--archivo", action="append", help="archivo revisado (absoluto, o relativo con un unico --repo); repetible")
    p.add_argument("--modo", choices=MODOS, default=None, help="0, rapido o completo: obligatorio con --write; con --check filtra los recibos del ticket")
    p.add_argument("--recibo", metavar="RUTA", help="con --check: chequea ese recibo.json (o su carpeta) en vez del mas reciente del ticket")
    p.add_argument("--reviewer", action="append", help="reviewer corrido; repetible")
    p.add_argument("--verificacion", action="append", help="'<comando>: <resultado>'; repetible")
    p.add_argument("--estado", choices=ESTADOS, default=None)
    p.add_argument("--fecha", default=None, type=_fecha, help="AAAA-MM-DD valido (por defecto, hoy)")
    p.add_argument("--ronda", default=None, type=_ronda,
                   help="con --write: la ronda de una revision del mismo dia y modo; desde la 2, la carpeta lleva -<ronda>")
    p.add_argument("--previo", metavar="RUTA",
                   help="con --write: rechequeo; --archivo es lo rechequeado y el recibo hereda del previo (recibo.json, su carpeta o la del ticket) "
                        "los archivos que no cambiaron")
    p.add_argument("--derivado", action="append", type=_derivado, metavar="HALLAZGO=DESTINO",
                   help="con --write: hallazgo que se deriva a otra tarea, otro ticket o el backlog; repetible")
    p.add_argument("--bajada", type=_motivo, metavar="MOTIVO",
                   help="con --write y --modo rapido: el usuario baja un escalon lo que propuso el triaje guardado en "
                        "<carpeta>/entrada/triaje.json (completo, sin un riesgo real); el motivo queda en el recibo")
    p.add_argument("--va-a-lider", dest="va_a_lider", choices=("si", "no"), default=None,
                   help="con --bajada, obligatorio: si el cambio va a un lider antes del commit; con si, no se baja")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.sellar:
            sobran = [_opcion(o) for o in AJENAS_A_SELLAR if getattr(args, o) is not None]
            if sobran:
                raise ErrorUso("--sellar solo toma la ruta del recibo, de su carpeta o del ticket: sobra %s" % ", ".join(sobran))
            return sellar_recibo(args.sellar)
        if args.check:
            if args.ronda is not None:
                raise ErrorUso("--ronda es de --write: --check toma la ronda mas alta, o la de --recibo")
            for opcion in SOLO_DE_WRITE:
                if getattr(args, opcion) is not None:
                    raise ErrorUso("%s es de --write: --check no escribe el recibo" % _opcion(opcion))
            return chequear_recibo(args.check, args.modo, args.recibo)
        if args.recibo:
            raise ErrorUso("--recibo es de --check: --write escribe el recibo en revision/<fecha>-<modo>/")
        if not args.ticket:
            raise ErrorUso("--write necesita --ticket")
        if not args.modo:
            raise ErrorUso("--write necesita --modo (0, rapido o completo)")
        if args.bajada is None and args.va_a_lider is not None:
            raise ErrorUso("--va-a-lider va con --bajada: es la respuesta a si el cambio que se baja va a un lider")
        if args.bajada is not None and args.va_a_lider is None:
            raise ErrorUso("--bajada necesita --va-a-lider no: solo se baja un cambio que no va a un lider, y el recibo guarda la respuesta")
        if args.va_a_lider == "si":
            raise ErrorUso("nunca se baja un cambio que va a un lider: revisalo en completo")
        args.fecha = args.fecha or datetime.date.today().isoformat()
        args.estado = args.estado or "pendiente"
        return escribir_recibo(args)
    except (ErrorUso, ErrorEntorno) as exc:
        print("recibo: %s" % exc, file=sys.stderr)
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
        print("recibo: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
