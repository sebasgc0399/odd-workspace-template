import sys

sys.dont_write_bytecode = True

import argparse
import os
import posixpath
import re
import subprocess
import unicodedata
from collections import namedtuple
from datetime import date
from pathlib import Path

import config_loader
from odd_ws.comun import decodificar, entorno_git, raiz_de_instancia

FAIL, WARN, INFO, WORKLIST, NOAPLICA = "FAIL", "warn", "info", "worklist", "n/a"
MAX_ITEMS = 6
CRUCE_MIN_DOCS = 6
VOLATILIDAD_DIAS = {"alta": 30, "media": 90, "baja": None}
IGNORADAS = (".git", "node_modules")
ESQUEMA_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]+:")
LINK_MD_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)(#[^)\s]*)?\)")
LINK_SECCION_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)?#([^)\s]+)\)")
ANCLA_HTML_RE = re.compile(r"""<a\s[^>]*\b(?:id|name)\s*=\s*["']([^"']+)["']""")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
HEADING_CON_CIFRA_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$", re.M)
ENTIDAD_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]{2,})`")
CITA_RE = re.compile(r"[\"“”«»][^\"“”«»]{0,80}[\"“”«»]")
PORCELAIN_RE = re.compile(r"^([A-Z?! ]{2}) (.*)$")

Modo = namedtuple("Modo", "funcion argumentos ayuda", defaults=("",))


class Hallazgo:
    def __init__(self, sev, texto, arreglo=None):
        self.sev, self.texto, self.arreglo = sev, texto, arreglo


class Contexto:
    def __init__(self, raiz, datos, hoy):
        self.raiz = Path(raiz)
        self.docs, self.indice, self.tope = datos["docs"], datos["index"], datos["index_max_lines"]
        self.escaneo, self.cantidades, self.afirmaciones = datos["scan"], datos["quantities"], datos["claims"]
        self.hoy = hoy

    @property
    def ruta_docs(self):
        return self.raiz / self.docs if self.docs is not None else None

    @property
    def ruta_indice(self):
        return self.raiz / self.indice

    def relativa(self, ruta):
        return Path(os.path.relpath(ruta, self.raiz)).as_posix()


def contexto_de(raiz, hoy=None):
    return Contexto(raiz, config_loader.conocimiento(raiz), hoy or date.today())


def leer(ruta):
    return decodificar(Path(ruta).read_bytes())


def _existe(ruta):
    try:
        return ruta.exists()
    except (OSError, ValueError):
        return False


def _resolver(ruta):
    try:
        return ruta.resolve()
    except (OSError, ValueError):
        return ruta


def slug(titulo):
    t = titulo.strip().lower()
    t = "".join(c for c in t if unicodedata.category(c)[0] in "LN" or c in " -_")
    return re.sub(r"\s", "-", t)


def headings(ruta):
    return {slug(m.group(1)) for m in HEADING_RE.finditer(leer(ruta))}


def anclas_de(ruta):
    ids = ANCLA_HTML_RE.finditer(leer(ruta))
    return headings(ruta) | {m.group(1).lower() for m in ids}


def frontmatter(ruta):
    texto = leer(ruta)
    if not texto.startswith("---"):
        return None
    fin = texto.find("\n---", 3)
    if fin == -1:
        return None
    campos = {}
    for linea in texto[3:fin].splitlines():
        if ":" in linea:
            clave, _, valor = linea.partition(":")
            campos[clave.strip()] = valor.split("#")[0].strip()
    return campos


def rol_de(ruta):
    declarado = (frontmatter(ruta) or {}).get("rol")
    return declarado if declarado in ("resumen", "autoritativo") else None


def docs_de_dominio(ctx):
    carpeta = ctx.ruta_docs
    if carpeta is None or not carpeta.is_dir():
        return []
    return sorted(carpeta.glob("*.md"))


def _prefijo_fijo(patron):
    fijas = []
    for parte in patron.split("/"):
        if any(c in parte for c in "*?["):
            break
        fijas.append(parte)
    return fijas


def _recorrer(base):
    for carpeta, subcarpetas, archivos in os.walk(base):
        subcarpetas[:] = sorted(s for s in subcarpetas if s.lower() not in IGNORADAS)
        for nombre in sorted(archivos):
            yield Path(carpeta) / nombre


def archivos_de_escaneo(ctx):
    vistos = {}
    for patron in ctx.escaneo:
        base = ctx.raiz.joinpath(*_prefijo_fijo(patron))
        if base.is_file():
            candidatos = [base]
        elif base.is_dir():
            candidatos = _recorrer(base)
        else:
            continue
        for ruta in candidatos:
            if ruta.suffix.lower() == ".md" and config_loader.coincide(ctx.relativa(ruta), patron):
                vistos.setdefault(config_loader.canonica(ruta), ruta)
    return sorted(vistos.values())


def docs_md(ctx):
    vistos = {}
    for ruta in [ctx.ruta_indice, *docs_de_dominio(ctx), *archivos_de_escaneo(ctx)]:
        if ruta.is_file():
            vistos.setdefault(config_loader.canonica(ruta), ruta)
    return list(vistos.values())


def _sin_docs(ctx, propio=False):
    if ctx.docs is None:
        return [Hallazgo(NOAPLICA, "sin knowledge.docs en la config")]
    if not ctx.ruta_docs.is_dir():
        if propio:
            return [Hallazgo(FAIL, "knowledge.docs %r no es una carpeta" % ctx.docs, "crear la carpeta o corregir knowledge.docs en workspace.config.json")]
        return [Hallazgo(NOAPLICA, "knowledge.docs %r no es una carpeta (lo reporta el chequeo de indexados)" % ctx.docs)]
    return None


def chequear_indexados(ctx):
    ausente = _sin_docs(ctx, propio=True)
    if ausente:
        return ausente
    if not ctx.ruta_indice.is_file():
        return [Hallazgo(FAIL, "no existe %s en la raíz" % ctx.indice)]
    texto = leer(ctx.ruta_indice)
    salida = []
    for doc in docs_de_dominio(ctx):
        if doc.name == "README.md":
            continue
        if doc.name not in texto:
            salida.append(Hallazgo(WARN, "%s no está linkeado desde %s" % (ctx.relativa(doc), ctx.indice), "agregarlo al índice (%s)" % ctx.indice))
    return salida


def chequear_links(ctx):
    salida = []
    for archivo in docs_md(ctx):
        for m in LINK_MD_RE.finditer(leer(archivo)):
            if ESQUEMA_RE.match(m.group(1)):
                continue
            if not _existe(_resolver(archivo.parent / m.group(1))):
                salida.append(Hallazgo(FAIL, "%s -> %s (destino inexistente)" % (ctx.relativa(archivo), m.group(1)), "corregir la ruta o crear el destino"))
    return salida


def links_a_seccion(archivo):
    for m in LINK_SECCION_RE.finditer(leer(archivo)):
        if m.group(1) and ESQUEMA_RE.match(m.group(1)):
            continue
        destino = _resolver(archivo.parent / m.group(1)) if m.group(1) else _resolver(archivo)
        yield destino, m.group(2), m.group(1)


def chequear_anclas(ctx):
    salida, cache = [], {}
    for archivo in docs_md(ctx):
        for destino, ancla, ruta in links_a_seccion(archivo):
            if ruta is None or not _existe(destino):
                continue
            if destino not in cache:
                cache[destino] = anclas_de(destino)
            if ancla.lower() not in cache[destino]:
                salida.append(Hallazgo(WARN, "%s -> %s#%s (sección inexistente)" % (ctx.relativa(archivo), ruta, ancla), "revisar el título de la sección destino"))
    return salida


def patron_de_cantidad(cantidades):
    return re.compile(r"(\d{1,4}\+?)\s+(%s)\b" % "|".join(re.escape(c) for c in cantidades), re.I)


def chequear_cifras_en_headings(ctx):
    ausente = _sin_docs(ctx)
    if ausente:
        return ausente
    if not ctx.cantidades:
        return [Hallazgo(NOAPLICA, "sin knowledge.quantities en la config")]
    patron = patron_de_cantidad(ctx.cantidades)
    entrantes = {}
    for archivo in docs_md(ctx):
        for destino, ancla, _ in links_a_seccion(archivo):
            entrantes.setdefault((destino, ancla.lower()), []).append(ctx.relativa(archivo))
    salida, libres = [], 0
    for doc in docs_de_dominio(ctx):
        for m in HEADING_CON_CIFRA_RE.finditer(leer(doc)):
            cantidad = patron.search(m.group(1))
            if not cantidad:
                continue
            refs = entrantes.get((_resolver(doc), slug(m.group(1))), [])
            if refs:
                salida.append(Hallazgo(
                    WARN,
                    "%s: heading con cantidad '%s' y %d link(s) entrante(s) -- corregir la cifra rompe el ancla" % (doc.name, cantidad.group(0), len(refs)),
                    "sacar la cifra del título y dejarla en el cuerpo (citada por %s)" % ", ".join(sorted(set(refs))),
                ))
            else:
                libres += 1
    if libres:
        salida.append(Hallazgo(INFO, "%d heading(s) con cantidad y CERO links entrantes -- gratis sacarles la cifra ahora" % libres))
    return salida


def chequear_tope_del_indice(ctx):
    n = len(leer(ctx.ruta_indice).splitlines()) if ctx.ruta_indice.is_file() else 0
    if n > ctx.tope:
        return [Hallazgo(WARN, "%s tiene %d líneas (límite %d)" % (ctx.indice, n, ctx.tope), "podar: mover el detalle estable a los docs y dejar solo el índice")]
    return []


def chequear_frescura(ctx):
    ausente = _sin_docs(ctx)
    if ausente:
        return ausente
    sin_campo, sin_rol, salida, total = [], [], [], 0
    for doc in docs_de_dominio(ctx):
        if doc.name == "README.md":
            continue
        total += 1
        campos = frontmatter(doc) or {}
        if rol_de(doc) is None:
            sin_rol.append(doc.name)
        verificado = campos.get("verificado")
        if not verificado:
            sin_campo.append(doc.name)
            continue
        try:
            fecha = date.fromisoformat(verificado)
        except ValueError:
            salida.append(Hallazgo(WARN, "%s: 'verificado: %s' no es una fecha ISO" % (doc.name, verificado), "usar formato YYYY-MM-DD"))
            continue
        volatilidad = campos.get("volatilidad", "media")
        limite = VOLATILIDAD_DIAS.get(volatilidad, 90)
        dias = (ctx.hoy - fecha).days
        if limite is not None and dias > limite:
            salida.append(Hallazgo(
                WARN,
                "%s sin verificar hace %dd (volatilidad %s -> %dd)" % (doc.name, dias, volatilidad, limite),
                "revisarlo contra el código y actualizar 'verificado:'",
            ))
    salida.append(Hallazgo(INFO, "%d/%d docs declaran 'verificado:' (opt-in) y %d sin 'rol:' en el frontmatter" % (total - len(sin_campo), total, len(sin_rol))))
    return salida


def _es_conocimiento(ctx, ruta):
    clave = ruta.casefold()
    if ctx.afirmaciones is not None and clave == ctx.afirmaciones.casefold():
        return True
    if not clave.endswith(".md"):
        return False
    if clave == ctx.indice.casefold():
        return True
    if ctx.docs is not None and posixpath.dirname(ruta).casefold() == ("" if ctx.docs == "." else ctx.docs.casefold()):
        return True
    return any(config_loader.coincide(ruta, patron) for patron in ctx.escaneo)


def agrupar_porcelain(salida, es_conocimiento, prefijo=""):
    grupos = {"conflictos": [], "borrados": [], "modificados": [], "nuevos": []}
    for linea in salida.splitlines():
        coincidencia = PORCELAIN_RE.match(linea)
        if not coincidencia:
            continue
        estado = coincidencia.group(1).strip()
        partes = [p.strip().strip('"') for p in coincidencia.group(2).split(" -> ")]
        if prefijo:
            if not all(p.startswith(prefijo) for p in partes):
                continue
            partes = [p[len(prefijo):] for p in partes]
        if not es_conocimiento(partes[-1]):
            continue
        ruta = " -> ".join(partes)
        if estado == "??":
            grupos["nuevos"].append(ruta)
        elif "U" in estado or estado in ("AA", "DD"):
            grupos["conflictos"].append(ruta)
        elif "D" in estado:
            grupos["borrados"].append(ruta)
        else:
            grupos["modificados"].append(ruta)
    return grupos


def _git(ctx, *args):
    entorno = entorno_git()
    entorno["LC_ALL"] = "C"
    try:
        return subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(ctx.raiz), *args], capture_output=True, env=entorno, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("git %s falló: %s" % (" ".join(args), error))


def _pathspecs(ctx):
    rutas = []
    if ctx.docs is not None:
        rutas.append(ctx.docs)
    rutas.append(ctx.indice)
    if ctx.afirmaciones is not None:
        rutas.append(ctx.afirmaciones)
    for patron in ctx.escaneo:
        rutas.append("/".join(_prefijo_fijo(patron)) or ".")
    return list(dict.fromkeys(rutas))


def _lista(rutas):
    return ", ".join(rutas[:4]) + (" ..." if len(rutas) > 4 else "")


def chequear_sin_trackear(ctx):
    prefijo = _git(ctx, "rev-parse", "--show-prefix")
    if prefijo.returncode != 0:
        if prefijo.returncode == 128 and b"not a git repository" in prefijo.stderr.lower():
            return [Hallazgo(NOAPLICA, "la raíz no está dentro de un repo git")]
        raise RuntimeError("git rev-parse falló: %s" % decodificar(prefijo.stderr).strip())
    estado = _git(ctx, "status", "--porcelain", "--untracked-files=all", "--", *_pathspecs(ctx))
    if estado.returncode != 0:
        raise RuntimeError("git status falló: %s" % decodificar(estado.stderr).strip())
    grupos = agrupar_porcelain(decodificar(estado.stdout), lambda ruta: _es_conocimiento(ctx, ruta), decodificar(prefijo.stdout).strip())
    salida = []
    if grupos["conflictos"]:
        salida.append(Hallazgo(
            WARN,
            "%d doc(s) EN CONFLICTO sin resolver: %s" % (len(grupos["conflictos"]), _lista(grupos["conflictos"])),
            "resolverlo antes de seguir: el doc tiene los marcadores del merge y no se puede commitear hasta sacarlos",
        ))
    if grupos["borrados"]:
        salida.append(Hallazgo(
            WARN,
            "%d doc(s) BORRADOS sin commitear: %s" % (len(grupos["borrados"]), _lista(grupos["borrados"])),
            "si el borrado es a propósito, corregir los links que lo citaban y commitearlo; si no, recuperarlo",
        ))
    if grupos["modificados"]:
        salida.append(Hallazgo(
            WARN,
            "%d doc(s) MODIFICADOS sin commitear: %s" % (len(grupos["modificados"]), _lista(grupos["modificados"])),
            "un doc ya citado y editado a medias es el estado más riesgoso: commitear o revertir antes de seguir",
        ))
    if grupos["nuevos"]:
        salida.append(Hallazgo(
            WARN,
            "%d ruta(s) nuevas sin commitear: %s" % (len(grupos["nuevos"]), _lista(grupos["nuevos"])),
            "git add + commit, o borrarlas si eran temporales",
        ))
    return salida


def docs_de_cruce(ctx):
    return [d for d in [ctx.ruta_indice, *docs_de_dominio(ctx)] if d.is_file()]


def superficie_de_cruce(ctx):
    presencia = {}
    for doc in docs_de_cruce(ctx):
        for entidad in {m.group(1) for m in ENTIDAD_RE.finditer(leer(doc))}:
            presencia.setdefault(entidad, set()).add(doc.name)
    return sorted(((e, d) for e, d in presencia.items() if len(d) >= CRUCE_MIN_DOCS), key=lambda x: -len(x[1]))


def cifras_comparables(ctx):
    if not ctx.cantidades:
        return {}
    patron = patron_de_cantidad(ctx.cantidades)
    grupos = {}
    for doc in docs_de_cruce(ctx):
        for n, linea in enumerate(leer(doc).splitlines(), 1):
            limpia = CITA_RE.sub(" ", linea)
            for m in patron.finditer(limpia):
                frase = linea.strip()
                if len(frase) > 150:
                    i = max(0, m.start() - 60)
                    frase = ("..." if i else "") + frase[i:i + 150] + "..."
                grupos.setdefault(m.group(2).lower(), []).append((doc, n, m.group(1), frase))
    return {s: filas for s, filas in sorted(grupos.items()) if len({f[0] for f in filas}) > 1 and len({f[2] for f in filas}) > 1}


def modo_cruce(ctx, args):
    ausente = _sin_docs(ctx)
    if ausente:
        print("  no aplica: %s" % ausente[0].texto)
        return 0
    docs = docs_de_cruce(ctx)
    resumenes = [d.name for d in docs if rol_de(d) == "resumen"]
    print("\n[Prioridad de lectura]")
    print("  El desfase entre docs vive sobre todo en los resúmenes: se leen primero.")
    print("  Empezar por: %s" % (", ".join(resumenes) or "(ninguno declarado)"))
    sin_rol = [d.name for d in docs if d.name != "README.md" and rol_de(d) is None]
    if sin_rol:
        print("  %d doc(s) sin 'rol:' declarado -- se leen al final, sin prioridad." % len(sin_rol))

    print("\n[Detector 1 - superficie de cruce (entidades en >=%d docs)]" % CRUCE_MIN_DOCS)
    for entidad, nombres in superficie_de_cruce(ctx)[:15]:
        print("  %-32s %2d docs  %s" % (entidad, len(nombres), ", ".join(sorted(nombres)[:4]) + (" ..." if len(nombres) > 4 else "")))

    print("\n[Detector 2 - cifras comparables (CANDIDATOS, no hallazgos)]")
    if not ctx.cantidades:
        print("  no aplica: sin knowledge.quantities en la config")
    else:
        grupos = cifras_comparables(ctx)
        if not grupos:
            print("  (ninguna cifra del mismo sustantivo difiere entre docs)")
        marca = {"resumen": "R", "autoritativo": "A", None: "?"}
        for sustantivo, filas in grupos.items():
            print("  ~ %s" % sustantivo)
            for doc, linea, cifra, frase in filas[:8]:
                print("      (%s) %s:%d  [%s]  %s" % (marca[rol_de(doc)], doc.name, linea, cifra, frase))
        if grupos:
            print("\n  (A)=autoritativo (R)=resumen (?)=sin declarar. Desempate: gana el")
            print("  autoritativo. Si ambos discrepan, verificar contra el código o los datos vivos.")
            print("  NUNCA promediar ni 'conciliar' dos cifras en una tercera.")
    print("\n  RECORDATORIO: una cifra distinta NO es una divergencia. Dos conteos pueden medir")
    print("  cosas distintas (una lista de interfaz y un catálogo completo). Leer la frase")
    print("  antes de reportar nada.")
    print("\n  La propagación no se automatiza: al CORREGIR un dato, buscar sus copias en el")
    print("  resto de los docs antes de cerrar.")
    return 0


GRUPOS = [
    ("Índice y navegación", [
        ("docs indexados en el índice", chequear_indexados),
        ("links .md", chequear_links),
        ("anclas de sección", chequear_anclas),
        ("cifras en headings", chequear_cifras_en_headings),
        ("tope del índice", chequear_tope_del_indice),
    ]),
    ("Frescura", [
        ("verificación de docs", chequear_frescura),
    ]),
    ("Higiene", [
        ("todo commiteado", chequear_sin_trackear),
    ]),
]

MODOS = {
    "cruce": Modo(modo_cruce, (), "tier 3: candidatos de divergencia entre docs (siempre sale con 0)"),
}


def informe(ctx, verboso):
    fallas = advertencias = listas = 0
    for grupo, chequeos in GRUPOS:
        lineas = []
        for etiqueta, chequeo in chequeos:
            hallazgos = chequeo(ctx)
            duros = [h for h in hallazgos if h.sev in (FAIL, WARN, WORKLIST)]
            if not duros:
                no_aplica = [h for h in hallazgos if h.sev == NOAPLICA]
                infos = [h for h in hallazgos if h.sev == INFO]
                if no_aplica:
                    lineas.append("  n/a  %s -- %s" % (etiqueta, no_aplica[0].texto))
                else:
                    lineas.append("  ok   %s%s" % (etiqueta, (" -- " + infos[0].texto) if infos else ""))
                continue
            peor = next(s for s in (FAIL, WARN, WORKLIST) if any(h.sev == s for h in duros))
            fallas += sum(1 for h in duros if h.sev == FAIL)
            advertencias += sum(1 for h in duros if h.sev == WARN)
            listas += sum(1 for h in duros if h.sev == WORKLIST)
            lineas.append("  %s %s (%d)" % (peor.ljust(4), etiqueta, len(duros)))
            mostrar = duros if verboso else duros[:MAX_ITEMS]
            for h in mostrar:
                marca = "(worklist) " if h.sev == WORKLIST and peor != WORKLIST else ""
                lineas.append("       - %s%s" % (marca, h.texto))
                if h.arreglo:
                    lineas.append("         -> %s" % h.arreglo)
            if len(duros) > len(mostrar):
                lineas.append("       (+%d más -- correr con --v)" % (len(duros) - len(mostrar)))
            for h in hallazgos:
                if h.sev == INFO:
                    lineas.append("       info: %s" % h.texto)
        print("\n[%s]" % grupo)
        print("\n".join(lineas))
    print()
    if fallas:
        print("DIAGNÓSTICO: %d falla(s), %d advertencia(s). Las FAIL rompen un mecanismo -- atenderlas primero." % (fallas, advertencias))
    elif advertencias:
        print("DIAGNÓSTICO: sin fallas, %d advertencia(s) de deuda." % advertencias)
    else:
        print("DIAGNÓSTICO: sistema de conocimiento SANO.")
    if listas:
        print("WORKLIST: %d item(s) para cruzar o decidir. No son deuda ni cuentan en el exit." % listas)
    return 1 if fallas else 3 if advertencias else 0


def _parser():
    parser = argparse.ArgumentParser(prog="conocimiento", allow_abbrev=False, description="Chequeo de salud de los documentos de conocimiento de la instancia (solo lectura).")
    parser.add_argument("--v", "-v", dest="verboso", action="store_true", help="lista todos los hallazgos, sin acotar")
    exclusivos = parser.add_mutually_exclusive_group()
    for nombre, modo in MODOS.items():
        exclusivos.add_argument("--" + nombre, dest="modo", action="store_const", const=nombre, help=modo.ayuda)
        for bandera, opciones in modo.argumentos:
            parser.add_argument(bandera, **opciones)
    return parser


def main(argv=None, entorno=None, cwd=None):
    entorno = os.environ if entorno is None else entorno
    cwd = os.getcwd() if cwd is None else cwd
    try:
        args = _parser().parse_args(argv)
    except SystemExit as salida:
        return salida.code if isinstance(salida.code, int) else 2
    try:
        raiz = raiz_de_instancia(entorno, cwd)
        if raiz is None:
            print("conocimiento: no hay %s en %s ni en sus carpetas padre" % (config_loader.NOMBRE, cwd), file=sys.stderr)
            return 2
        ctx = contexto_de(raiz)
        modo = MODOS.get(args.modo)
        if modo is not None:
            return modo.funcion(ctx, args)
        return informe(ctx, args.verboso)
    except config_loader.ConfigRota as error:
        print("conocimiento: config rota (%s)" % error, file=sys.stderr)
        return 2
    except Exception as error:
        print("conocimiento: error interno (%s)" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
