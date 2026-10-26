import sys

sys.dont_write_bytecode = True

import argparse
import codecs
import json
import os
import re
import subprocess
from pathlib import Path

import config_loader
import recibo
import verificar_capa
from odd_ws import capas as convencion
from odd_ws import tsql
from odd_ws.comun import cargar_por_ruta, lineas, raiz_de_instancia

TOPE_BYTES = 2000000
UMBRAL_CONSUMIDORES = 2
TOPE_OBJETOS = 20
DOC_EXT = (".md", ".txt", ".rst")
SENALES = ("efecto", "consumidores", "dinero", "migracion", "contrato", "capas")
LENGUAJES = {".sql": tsql}
COTA = "solo en los repos declarados en workspace.config.json"
CAMPOS_MARCADOR = ("id", "patron", "ejemplo", "fuente", "ancla", "descripcion")
SIN_HALLAZGOS = {
    "efecto": "sin marcadores de efecto en el archivo entero (base y actual)",
    "dinero": "sin hallazgos en las líneas agregadas ni quitadas",
}
NO_DETECTABLE = (
    "«antes de mostrarle el cambio a un líder»: el modo completo lo pide quien revisa, no el diff.",
    "consumidores fuera de los repos declarados: el conteo es una cota inferior ({cota}).",
    "consumidores por reflexión, textos armados o configuración en datos: solo se cuenta el nombre literal.",
    "forma del result set de un SP, códigos de error y estados numéricos que consume otra capa.",
    "enums y constantes compartidas entre capas; la semántica de un valor que cambia sin cambiar su tipo.",
    "contrato y tipos de dinero de los lenguajes sin biblioteca de señales (hoy solo hay T-SQL); sus consumidores dejan la señal inválida.",
    "efecto hacia un sistema que no esté en los marcadores de la instancia ({marcadores} en {senales}).",
    "dinero con un nombre fuera de la lista de la instancia ({nombres} nombres; el tipo se detecta donde hay biblioteca).",
)


class ErrorUso(Exception):
    pass


class ErrorEntorno(Exception):
    pass


def _git(repo, *args):
    try:
        return recibo.git(repo, *args)
    except recibo.ErrorEntorno as exc:
        raise ErrorEntorno(str(exc))


def _git_ok(repo, *args):
    r = _git(repo, *args)
    if r.returncode != 0:
        raise ErrorEntorno("git %s falló en %s: %s" % (args[0], repo, r.stderr.decode("utf-8", errors="replace").strip()))
    return r


def decodificar(crudo):
    if crudo.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return crudo.decode("utf-16", errors="replace")
    if crudo.startswith(codecs.BOM_UTF8):
        crudo = crudo[len(codecs.BOM_UTF8):]
    return crudo.decode("utf-8", errors="replace")


def lineas_de(texto):
    return [t for _, t in lineas(texto or "")]


def leer_archivo(ruta):
    if os.path.getsize(ruta) > TOPE_BYTES:
        return None
    with open(ruta, "rb") as f:
        return decodificar(f.read())


def es_doc(ruta):
    return os.path.splitext(ruta)[1].lower() in DOC_EXT


def _lenguaje(c):
    return LENGUAJES.get(os.path.splitext(c["ruta"])[1].lower())


# ---------------------------------------------------------------- módulo de la instancia

def _problema_de_fuente(m, raiz):
    ruta, _, n = m["fuente"].rpartition(":")
    if (not ruta or not n.isdigit() or int(n) < 1 or "\\" in ruta or ":" in ruta or ruta.startswith("/")
            or ".." in ruta.split("/")):
        return "%s: la fuente %r debe ser <ruta relativa a la raíz de la instancia>:<línea>" % (m["id"], m["fuente"])
    archivo = Path(raiz) / ruta
    if not archivo.is_file():
        return "%s: no existe %s" % (m["id"], ruta)
    try:
        texto = lineas_de(decodificar(archivo.read_bytes()))
    except OSError as exc:
        return "%s: no se puede leer %s (%s)" % (m["id"], ruta, exc)
    if int(n) > len(texto):
        return "%s: %s no tiene la línea %s" % (m["id"], ruta, n)
    if m["ancla"] not in texto[int(n) - 1]:
        return "%s: la línea %s no contiene «%s»" % (m["id"], m["fuente"], m["ancla"])
    return None


def _marcadores(crudos, raiz, problemas):
    if not isinstance(crudos, (list, tuple)):
        problemas.append("MARCADORES debe ser una lista de marcadores")
        return []
    validos, vistos = [], set()
    for i, m in enumerate(crudos, 1):
        faltan = [c for c in CAMPOS_MARCADOR if not isinstance(m, dict) or not isinstance(m.get(c), str) or not m.get(c)]
        if faltan:
            problemas.append("marcador %d: faltan campos o no son texto: %s" % (i, ", ".join(faltan)))
            continue
        if m["id"] in vistos:
            problemas.append("%s: id repetido" % m["id"])
            continue
        vistos.add(m["id"])
        try:
            regex = re.compile(m["patron"], re.IGNORECASE)
        except re.error as exc:
            problemas.append("%s: el patrón no compila (%s)" % (m["id"], exc))
            continue
        if not regex.search(m["ejemplo"]):
            problemas.append("%s: su patrón no detecta su ejemplo" % m["id"])
            continue
        problema = _problema_de_fuente(m, raiz)
        if problema:
            problemas.append(problema)
            continue
        validos.append((m, regex))
    return validos


def cargar_senales(raiz):
    datos = {"marcadores": [], "dinero": None, "nombres": 0, "cota": COTA, "no_detectable": [], "problemas": []}
    ruta = Path(raiz) / convencion.SENALES
    if not ruta.is_file():
        return datos
    try:
        modulo = cargar_por_ruta(ruta, "senales_de_la_instancia")
    except Exception as exc:
        datos["problemas"].append("el módulo no carga (%s: %s)" % (type(exc).__name__, exc))
        return datos
    problemas = datos["problemas"]
    datos["marcadores"] = _marcadores(getattr(modulo, "MARCADORES", ()), raiz, problemas)
    nombres = getattr(modulo, "DINERO_NOMBRES", ())
    if not isinstance(nombres, (list, tuple)) or not all(isinstance(n, str) and n for n in nombres):
        problemas.append("DINERO_NOMBRES debe ser una lista de palabras")
    elif nombres:
        datos["nombres"] = len(nombres)
        datos["dinero"] = re.compile(r"\w*(?:%s)\w*" % "|".join(re.escape(n) for n in nombres), re.IGNORECASE)
    cota = getattr(modulo, "COTA", COTA)
    if not isinstance(cota, str) or not cota:
        problemas.append("COTA debe ser un texto")
    else:
        datos["cota"] = cota
    extra = getattr(modulo, "NO_DETECTABLE", ())
    if not isinstance(extra, (list, tuple)) or not all(isinstance(x, str) and x for x in extra):
        problemas.append("NO_DETECTABLE debe ser una lista de textos")
    else:
        datos["no_detectable"] = list(extra)
    return datos


# ---------------------------------------------------------------- señales puras

def buscar_marcadores(texto_lineas, marcadores):
    hallados, vistos = [], set()
    for linea in texto_lineas:
        for m, regex in marcadores:
            if m["id"] not in vistos and regex.search(linea):
                vistos.add(m["id"])
                hallados.append(m)
    return hallados


def buscar_dinero(texto_lineas, regexes):
    hallados = []
    for linea in texto_lineas:
        for regex in regexes:
            encontrado = regex.search(linea)
            if encontrado:
                hallados.append(encontrado.group(0))
    return hallados


def es_migracion_por_ruta(ruta):
    partes = ruta.replace("\\", "/").lower().split("/")
    return any("seed" in p or "migration" in p or "migracion" in p for p in partes)


# ---------------------------------------------------------------- cambios

def _de_hunks(hunks):
    return [t for h in hunks for _, t in h["agregadas"]], [t for h in hunks for t in h["quitadas"]]


def _capa(abs_, config):
    clase = config_loader.clasificar(abs_, config)
    if not clase:
        return None, None
    return clase[0], "taller" if clase[1] == "taller" else "repo"


def _nuevo_cambio(ruta, abs_, estado, capa, origen, taller=False):
    return {"ruta": ruta, "abs": abs_, "estado": estado, "capa": capa, "origen": origen, "taller": taller,
            "agregadas": [], "quitadas": [], "actual": None, "base_texto": None, "contraparte": None,
            "nuevo": estado in ("A", "?"), "ilegible": False}


def recolectar_repo(ruta, base_arg, config):
    top = recibo.raiz_del_repo(ruta)
    base = recibo.resolver_base(top, base_arg)
    salida = _git_ok(top, "diff", "--name-status", "-z", "--no-renames", "--no-ext-diff", base).stdout.split(b"\0")
    estados = {}
    for i in range(0, len(salida) - 1, 2):
        if salida[i]:
            estados[salida[i + 1].decode("utf-8", errors="replace")] = salida[i].decode("ascii", errors="replace")[:1]
    for crudo in _git_ok(top, "ls-files", "--others", "--exclude-standard", "-z").stdout.split(b"\0"):
        if crudo:
            estados.setdefault(crudo.decode("utf-8", errors="replace"), "?")
    cambios = []
    for rel in sorted(estados):
        texto_diff = None
        if estados[rel] == "M":
            d = _git(top, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames", "--no-textconv", base, "--", rel)
            texto_diff = d.stdout.decode("utf-8", errors="replace")
            if d.returncode == 0 and not texto_diff.strip():
                continue
        abs_ = os.path.join(top, rel)
        c = _nuevo_cambio(rel, abs_, estados[rel], *_capa(abs_, config))
        if os.path.isfile(abs_):
            c["actual"] = leer_archivo(abs_)
            c["ilegible"] = c["actual"] is None
        if c["estado"] != "?":
            existe = _git(top, "show", "%s:%s" % (base, rel))
            if existe.returncode == 0:
                c["base_texto"] = decodificar(existe.stdout)
        if c["estado"] == "M" and c["base_texto"] is not None and c["actual"] is not None:
            if "Binary files" in texto_diff or "GIT binary patch" in texto_diff:
                c["agregadas"], c["quitadas"] = _de_hunks(verificar_capa._hunks_contra(c["base_texto"], c["actual"]))
            else:
                c["agregadas"], c["quitadas"] = _de_hunks(verificar_capa._hunks_del_diff(texto_diff))
        elif c["estado"] in ("A", "?"):
            c["agregadas"] = lineas_de(c["actual"])
        elif c["estado"] == "D":
            c["quitadas"] = lineas_de(c["base_texto"])
        cambios.append(c)
    return {"ruta": top, "base": base, "cambios": cambios}


def recolectar_taller(ruta, config):
    if not os.path.isfile(ruta):
        raise ErrorEntorno("el archivo del taller no existe: %s" % ruta)
    abs_ = os.path.abspath(ruta)
    c = _nuevo_cambio(os.path.basename(abs_), abs_, "T", *_capa(abs_, config), taller=True)
    c["actual"] = leer_archivo(abs_)
    c["ilegible"] = c["actual"] is None
    c["agregadas"] = lineas_de(c["actual"])
    linea_base = config["layers"][c["capa"]].get("workshop_baseline") if c["origen"] == "taller" else None
    if linea_base:
        try:
            contraparte = verificar_capa._contraparte(abs_, linea_base, config)
            texto = verificar_capa._contenido(contraparte) if contraparte else None
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ErrorEntorno("no se pudo buscar la contraparte de %s (%s)" % (ruta, exc))
        if texto is not None:
            c["base_texto"], c["contraparte"] = texto, "%s:%s" % (Path(contraparte[0]).as_posix(), contraparte[2])
            if c["actual"] is not None:
                c["quitadas"] = _de_hunks(verificar_capa._hunks_contra(texto, c["actual"]))[1]
    c["nuevo"] = c["base_texto"] is None
    return c


# ---------------------------------------------------------------- consumidores

def _rama_y_hash(clon):
    try:
        rama = recibo.rama_por_defecto(clon)
    except recibo.ErrorEntorno:
        return None, None
    r = _git(clon, "rev-parse", "--verify", "--quiet", rama + "^{commit}")
    return (rama, r.stdout.decode("utf-8", errors="replace").strip()) if r.returncode == 0 else (None, None)


def grep_archivos(clon, rama, patron, fijo=False, ci=False):
    args = ["grep", "-l", "-I"] + (["-i"] if ci else []) + (["-w", "-F"] if fijo else ["-E"])
    r = _git(clon, *args, "-e", patron, rama, "--")
    if r.returncode == 1:
        return set()
    if r.returncode != 0:
        raise ErrorEntorno("git grep falló en %s: %s" % (clon, r.stderr.decode("utf-8", errors="replace").strip()))
    prefijo = rama + ":"
    return {l[len(prefijo):] if l.startswith(prefijo) else l
            for l in r.stdout.decode("utf-8", errors="replace").splitlines() if l}


class Clones:
    def __init__(self, rutas):
        self.rutas = list(rutas)
        self.ramas = {c: _rama_y_hash(c) for c in self.rutas}
        self.ok = [c for c in self.rutas if self.ramas[c][0]]

    def hashes(self):
        return {c: self.ramas[c][1] for c in self.rutas}

    def faltantes(self):
        return [c for c in self.rutas if not self.ramas[c][0]]


def evaluar_consumidores(cambios, clones, cota):
    detalle, nivel, objetos, vistos = [], "negativa", [], set()
    for c in cambios:
        lenguaje = _lenguaje(c)
        if c["ilegible"]:
            nivel = "invalida"
            detalle.append("%s: archivo demasiado grande para leer, el conteo no vale" % c["ruta"])
        elif lenguaje is None:
            nivel = "invalida"
            detalle.append("%s: sin biblioteca de señales para %s, el conteo no vale"
                           % (c["ruta"], os.path.splitext(c["ruta"])[1].lower() or "un archivo sin extensión"))
        else:
            for o in lenguaje.objetos(c["actual"], c["base_texto"]):
                if (o["nombre"], c["ruta"]) not in vistos:
                    vistos.add((o["nombre"], c["ruta"]))
                    objetos.append((c, o))
    if not objetos:
        return (nivel, detalle) if detalle else ("negativa", ["sin objetos con consumidores que contar en el diff"])
    if len(objetos) > TOPE_OBJETOS:
        return "invalida", detalle + ["%d objetos (más de %d): el conteo sería parcial, revisar a mano" % (len(objetos), TOPE_OBJETOS)]
    if clones.faltantes():
        return "invalida", detalle + ["repo(s) sin origin/HEAD o inexistentes (haz el fetch y `git remote set-head origin -a`, "
                                      "o pasa --clon): %s" % ", ".join(clones.faltantes())]
    for c, o in objetos:
        if o["nuevo"] and not (c["taller"] and c["base_texto"] is None):
            detalle.append("%s: objeto nuevo, sin consumidores previos" % o["nombre"])
            continue
        defs, refs = set(), set()
        try:
            for clon in clones.ok:
                rama = clones.ramas[clon][0]
                defs |= {(clon, p) for p in grep_archivos(clon, rama, o["ere_def"], False, o["ci"])}
                refs |= {(clon, p) for p in grep_archivos(clon, rama, o["ref"], o["fijo"], o["ci"])}
        except ErrorEntorno as exc:
            nivel = "invalida"
            detalle.append("%s: %s" % (o["nombre"], exc))
            continue
        if not defs:
            nivel = "invalida"
            detalle.append("%s: no encontré la definición del objeto en la rama de origin/HEAD de los repos "
                           "(control positivo): el conteo no vale" % o["nombre"])
            continue
        consumidores = sorted(p for clon, p in refs - defs if not (p == c["ruta"] and not c["taller"]))
        nombres = ", ".join(p.rsplit("/", 1)[-1] for p in consumidores[:6])
        detalle.append("%s: ≥ %d, %s%s" % (o["nombre"], len(consumidores), cota, " (%s)" % nombres if consumidores else ""))
        if len(consumidores) >= UMBRAL_CONSUMIDORES and nivel != "invalida":
            nivel = "positiva"
    return nivel, detalle


# ---------------------------------------------------------------- análisis

def _cargar_config(raiz):
    if raiz is None:
        raiz = raiz_de_instancia(os.environ, os.getcwd())
        if raiz is None:
            raise ErrorEntorno("no hay %s en la carpeta de la sesión ni en sus padres (pasa --raiz)" % config_loader.NOMBRE)
    if not (Path(raiz) / config_loader.NOMBRE).is_file():
        raise ErrorEntorno("no hay %s en %s" % (config_loader.NOMBRE, raiz))
    try:
        return str(raiz), config_loader.cargar(raiz)
    except config_loader.ConfigRota as exc:
        raise ErrorEntorno("la configuración de %s está rota: %s" % (raiz, exc))


def analizar(repos, taller=(), raiz=None, clones=None):
    raiz, config = _cargar_config(raiz)
    instancia = cargar_senales(raiz)
    clones_ = Clones(clones if clones is not None else [repo["path"] for repo in config["repos"].values()])
    recolectados = [recolectar_repo(ruta, base, config) for ruta, base in repos]
    del_taller = [recolectar_taller(t, config) for t in taller]
    todos = [c for r in recolectados for c in r["cambios"]] + del_taller
    activos = [c for c in todos if not es_doc(c["ruta"])]
    senales = {id_: {"nivel": "negativa", "detalle": []} for id_ in SENALES}
    if activos:
        _evaluar_senales(senales, activos, instancia, clones_)
    else:
        for id_ in SENALES:
            senales[id_]["detalle"].append("no aplica: no hay cambios fuera de docs")
    if not todos:
        modo, motivos = "sin-cambios", ["no hay cambios contra la base"]
    elif not activos:
        modo, motivos = "0", ["solo docs o notas del taller: lectura estructural"]
    else:
        escalan = [i for i in SENALES if senales[i]["nivel"] != "negativa"]
        if escalan:
            modo, motivos = "completo", ["señal %s: %s" % (i, senales[i]["nivel"]) for i in escalan]
        else:
            modo, motivos = "rapido", ["todas las señales en negativo y el instrumento verificado"]
    no_detectable = [n.format(cota=instancia["cota"], marcadores=len(instancia["marcadores"]), senales=convencion.SENALES,
                              nombres=instancia["nombres"]) for n in NO_DETECTABLE] + instancia["no_detectable"]
    return {
        "raiz": raiz,
        "origin_head": clones_.hashes(),
        "repos": [{"ruta": r["ruta"], "base": r["base"],
                   "archivos": [{"ruta": c["ruta"], "estado": c["estado"], "capa": c["capa"], "origen": c["origen"]}
                                for c in r["cambios"]]} for r in recolectados],
        "taller": [{"ruta": Path(c["abs"]).as_posix(), "capa": c["capa"], "origen": c["origen"], "contraparte": c["contraparte"]}
                   for c in del_taller],
        "senales": senales, "modo": modo, "motivos": motivos, "no_detectable": no_detectable,
    }


def _evaluar_senales(senales, activos, instancia, clones):
    for c in activos:
        lenguaje = _lenguaje(c)
        agregadas = c["agregadas"]
        en_actual = buscar_marcadores(lineas_de(c["actual"]) if c["actual"] is not None else [], instancia["marcadores"])
        en_base = buscar_marcadores(lineas_de(c["base_texto"]) if c["base_texto"] is not None else [], instancia["marcadores"])
        for m in en_actual:
            senales["efecto"]["detalle"].append("%s: %s (%s) %s" % (c["ruta"], m["id"], m["fuente"], m["descripcion"]))
        vistos = {m["id"] for m in en_actual}
        for m in en_base:
            if m["id"] not in vistos:
                senales["efecto"]["detalle"].append("%s: %s (%s) %s [solo en la base: quitado o movido]"
                                                    % (c["ruta"], m["id"], m["fuente"], m["descripcion"]))
        regexes = [r for r in (lenguaje.TIPOS_DINERO if lenguaje else None, instancia["dinero"]) if r is not None]
        tokens = sorted(set(buscar_dinero(agregadas + c["quitadas"], regexes)), key=str.lower)
        if tokens:
            resto = " (+%d más)" % (len(tokens) - 5) if len(tokens) > 5 else ""
            senales["dinero"]["detalle"].append("%s: %s%s" % (c["ruta"], ", ".join("«%s»" % t for t in tokens[:5]), resto))
        if c["estado"] != "D" and (es_migracion_por_ruta(c["ruta"]) or
                                   (lenguaje is not None and lenguaje.es_migracion("\n".join(agregadas), c["actual"] or ""))):
            senales["migracion"]["detalle"].append("%s: seed, migration, DDL de tabla o script de datos" % c["ruta"])
        cambios = []
        if lenguaje is not None:
            if c["estado"] == "D":
                cambios = lenguaje.cambios_de_contrato(c["base_texto"], None) if c["base_texto"] is not None else []
            elif c["actual"] is not None:
                cambios = lenguaje.cambios_de_contrato(c["base_texto"], c["actual"])
        for h in cambios:
            senales["contrato"]["detalle"].append("%s: %s" % (c["ruta"], h))
        if c["ilegible"]:
            for id_ in ("efecto", "dinero", "migracion", "contrato"):
                senales[id_]["nivel"] = "invalida"
                senales[id_]["detalle"].append("%s: archivo demasiado grande para leer, la señal no vale" % c["ruta"])
    if instancia["problemas"]:
        for id_ in ("efecto", "dinero"):
            senales[id_]["nivel"] = "invalida"
            senales[id_]["detalle"] += ["módulo de señales de la instancia (%s): %s" % (convencion.SENALES, p)
                                        for p in instancia["problemas"]]
    for id_ in ("efecto", "dinero", "migracion", "contrato"):
        if senales[id_]["nivel"] != "invalida":
            senales[id_]["nivel"] = "positiva" if senales[id_]["detalle"] else "negativa"
        if not senales[id_]["detalle"]:
            senales[id_]["detalle"].append(SIN_HALLAZGOS.get(id_, "sin hallazgos en las líneas agregadas"))
    if not instancia["marcadores"] and not instancia["problemas"]:
        senales["efecto"]["detalle"] = ["0 marcadores en la instancia: el efecto hacia otros sistemas no se mide "
                                        "(ver lo que el triaje no detecta)"]
    capas = sorted({c["capa"] for c in activos if c["capa"]})
    sin_capa = sorted(c["ruta"] for c in activos if not c["capa"])
    if len(capas) > 1:
        senales["capas"]["detalle"].append("más de una capa: %s" % ", ".join(capas))
    if sin_capa:
        senales["capas"]["detalle"].append("archivo(s) sin capa reconocida (no se puede triar): %s" % ", ".join(sin_capa))
    senales["capas"]["nivel"] = "positiva" if senales["capas"]["detalle"] else "negativa"
    if not senales["capas"]["detalle"]:
        senales["capas"]["detalle"].append("una sola capa: %s" % (capas[0] if capas else "ninguna"))
    nivel, detalle = evaluar_consumidores(activos, clones, instancia["cota"])
    senales["consumidores"] = {"nivel": nivel, "detalle": detalle}


# ---------------------------------------------------------------- salida

def formatear(r):
    salida = ["triaje — modo: %s" % r["modo"].upper()]
    salida += ["  " + m for m in r["motivos"]]
    salida.append("instancia: %s" % r["raiz"])
    salida.append("origin/HEAD usado (sin fetch; si está viejo, hazlo antes):")
    for clon, h in r["origin_head"].items():
        salida.append("  %s: %s" % (clon, h or "SIN origin/HEAD"))
    for repo in r["repos"]:
        salida.append("repo %s (base %s): %d archivo(s)" % (repo["ruta"], repo["base"][:10], len(repo["archivos"])))
        for a in repo["archivos"]:
            salida.append("  %s %s [%s]" % (a["estado"], a["ruta"], a["capa"] or "sin capa"))
    for t in r["taller"]:
        salida.append("taller %s [%s]%s" % (t["ruta"], t["capa"] or "sin capa",
                                            " contraparte " + t["contraparte"] if t["contraparte"] else ""))
    salida.append("señales:")
    for id_ in SENALES:
        s = r["senales"][id_]
        salida.append("  [%s] %s" % (s["nivel"], id_))
        salida += ["      " + d for d in s["detalle"]]
    salida.append("el triaje NO detecta (queda para el criterio de quien revisa):")
    salida += ["  - " + n for n in r["no_detectable"]]
    return "\n".join(salida)


def _parser():
    p = argparse.ArgumentParser(prog="triaje.py", description="Triaje por riesgo sobre el diff: propone el modo de la revisión.")
    p.add_argument("--repo", action="append", default=[], metavar="RUTA[#BASE]",
                   help="repo o worktree; base por defecto: merge-base con la rama de origin/HEAD")
    p.add_argument("--taller", action="append", default=[], metavar="ARCHIVO", help="archivo del taller del ticket")
    p.add_argument("--clon", action="append", default=None, metavar="RUTA",
                   help="repo donde contar consumidores en la rama de origin/HEAD (por defecto, los repos del config)")
    p.add_argument("--raiz", help="raíz de la instancia (por defecto, la de la sesión)")
    p.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    if not args.repo and not args.taller:
        print("triaje: falta --repo o --taller", file=sys.stderr)
        return 2
    try:
        r = analizar([recibo._partir_repo(t) for t in args.repo], taller=args.taller, raiz=args.raiz, clones=args.clon)
    except (ErrorUso, ErrorEntorno, recibo.ErrorUso, recibo.ErrorEntorno) as exc:
        print("triaje: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=2) if args.json else formatear(r))
    return 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("triaje: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
