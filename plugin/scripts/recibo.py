import sys

sys.dont_write_bytecode = True

import argparse
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
CARPETA_RE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})-(0|rapido|completo)")
ESTADOS = ("limpio", "con-hallazgos", "pendiente")
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


def armar_recibo(args):
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
    por_repo = asignar(repos, args.archivo)
    entradas = []
    for raiz, base in repos:
        resultado = calcular(raiz, base, por_repo[raiz])
        entradas.append({
            "ruta": raiz, "base": resultado["base"], "archivos": resultado["archivos"],
            "sha256": resultado["sha256"], "sha256_por_archivo": resultado["sha256_por_archivo"],
            "modo": args.modo, "reviewers": list(args.reviewer or []),
            "verificacion": list(args.verificacion or []), "estado": args.estado,
        })
    return {"version": VERSION, "fecha": args.fecha, "ticket": os.path.basename(os.path.abspath(args.ticket)),
            "repos": entradas}


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


def escribir_recibo(args):
    datos = armar_recibo(args)
    carpeta = os.path.join(args.ticket, "revision", "%s-%s" % (args.fecha, args.modo))
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, "recibo.json")
    _avisar_si_pisa(destino, datos)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("recibo escrito: %s (%d repo(s), %d archivo(s))" % (
        destino.replace("\\", "/"), len(datos["repos"]), sum(len(r["archivos"]) for r in datos["repos"])))
    return 0


def _recibos_del_ticket(revision, modo=None):
    hallados = []
    for d in os.listdir(revision):
        m = CARPETA_RE.fullmatch(d)
        candidato = os.path.join(revision, d, "recibo.json")
        if m and (modo is None or m.group(2) == modo) and os.path.isfile(candidato):
            hallados.append((m.group(1), m.group(2), candidato))
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
            candidatas = sorted(_recibos_del_ticket(revision, modo), key=lambda c: (c[0], MODOS.index(c[1])))
            if candidatas:
                return candidatas[-1][2]
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


def _fecha(texto):
    if not FECHA_RE.fullmatch(texto):
        raise argparse.ArgumentTypeError("la fecha tiene que ser AAAA-MM-DD, no %r" % texto)
    try:
        datetime.date.fromisoformat(texto)
    except ValueError:
        raise argparse.ArgumentTypeError("la fecha %r no existe en el calendario" % texto)
    return texto


def _parser():
    p = argparse.ArgumentParser(prog="recibo.py", description="Recibo de la revision atado al diff.")
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--write", action="store_true", help="escribe <ticket>/revision/<fecha>-<modo>/recibo.json")
    modo.add_argument("--check", metavar="RUTA", help="recalcula y compara: recibo.json, carpeta de la revision o del ticket")
    p.add_argument("--ticket", help="carpeta del ticket (con --write)")
    p.add_argument("--repo", action="append", metavar="RUTA[#BASE]", help="repo o worktree; base por defecto: merge-base con la rama de origin/HEAD")
    p.add_argument("--archivo", action="append", help="archivo revisado (absoluto, o relativo con un unico --repo); repetible")
    p.add_argument("--modo", choices=MODOS, default=None, help="0, rapido o completo: obligatorio con --write; con --check filtra los recibos del ticket")
    p.add_argument("--recibo", metavar="RUTA", help="con --check: chequea ese recibo.json (o su carpeta) en vez del mas reciente del ticket")
    p.add_argument("--reviewer", action="append", help="reviewer corrido; repetible")
    p.add_argument("--verificacion", action="append", help="'<comando>: <resultado>'; repetible")
    p.add_argument("--estado", choices=ESTADOS, default="pendiente")
    p.add_argument("--fecha", default=None, type=_fecha, help="AAAA-MM-DD valido (por defecto, hoy)")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.check:
            return chequear_recibo(args.check, args.modo, args.recibo)
        if args.recibo:
            raise ErrorUso("--recibo es de --check: --write escribe el recibo en revision/<fecha>-<modo>/")
        if not args.ticket:
            raise ErrorUso("--write necesita --ticket")
        if not args.modo:
            raise ErrorUso("--write necesita --modo (0, rapido o completo)")
        args.fecha = args.fecha or datetime.date.today().isoformat()
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
