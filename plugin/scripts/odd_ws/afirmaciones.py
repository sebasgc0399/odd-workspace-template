import json
import math
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from collections import namedtuple
from pathlib import Path

from odd_ws.comun import decodificar, entorno_git

VERSION = 1
CLAVES_DEL_ARCHIVO = ("version", "reglas", "claims", "rechazados", "cobertura_triada")
TIPOS = ("estructura", "contrato")
NATURALEZAS = ("invariante", "inventario")
EJECUTORES = ("repo", "sql")
FAIL, WARN, INFO = "FAIL", "warn", "info"
OK, CRECIO, DRIFT, ERROR = "OK", "CRECIO", "DRIFT", "ERROR"
REF_POR_DEFECTO = "origin/HEAD"
REF_VALIDO = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/@~^-]*")
PLAZO_POR_DEFECTO = 60
MARGEN_DEL_PLAZO = 10
SALIDAS_DE_PLAZO = (124, 137)
GUION_DEL_PLAZO = 'timeout -k 2 "$1" bash -c "$2"'
FETCH_MAX_DIAS = 7

GIT_VERBOS_SEGUROS = frozenset(("ls-tree", "show", "log", "cat-file", "rev-parse", "diff-tree", "grep"))
FILTROS_SEGUROS = frozenset(("grep", "wc", "sort", "uniq", "head", "tail", "cut", "tr"))
GIT_VERBOS_CON_REF = frozenset(("ls-tree", "show", "grep", "diff-tree", "log", "cat-file"))
SORT_LARGAS_PROHIBIDAS = ("output", "compress-program")
SORT_LARGAS_TEMPORALES = ("temporary-directory",)
SORT_CORTAS_CON_ARGUMENTO = "kStTy"
UNIQ_CORTAS_CON_ARGUMENTO = "fsw"
UNIQ_LARGAS_CON_ARGUMENTO = ("skip-fields", "skip-chars", "check-chars")
GIT_LARGAS_PROHIBIDAS = ("output", "open-files-in-pager", "ext-diff", "textconv", "filters", "no-index",
                         "show-signature")
ENTORNO_DE_ARRANQUE = frozenset(("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "BASH_XTRACEFD", "POSIXLY_CORRECT",
                                 "GREP_OPTIONS"))
PREFIJO_DE_FUNCIONES_EXPORTADAS = "BASH_FUNC_"
GIT_CONSERVADAS = frozenset(("GIT_OPTIONAL_LOCKS", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"))
PREFIJO_DE_GIT = ('git() { local v="$1"; shift; case "$v" in '
                  'show|log) command git "$v" --no-textconv --no-ext-diff --no-show-signature "$@" ;; '
                  'diff-tree) command git "$v" --no-textconv --no-ext-diff "$@" ;; '
                  '*) command git "$v" "$@" ;; esac; }; ')

Hallazgo = namedtuple("Hallazgo", "sev texto arreglo claim")
Veredicto = namedtuple("Veredicto", "estado detalle")


def _sin_duplicados(pares):
    claves = [k for k, _ in pares]
    repetidas = sorted({k for k in claves if claves.count(k) > 1})
    if repetidas:
        raise ValueError("clave(s) duplicada(s): %s" % ", ".join(repetidas))
    return dict(pares)


def cargar(ruta):
    texto = decodificar(Path(ruta).read_bytes())
    try:
        datos = json.loads(texto, object_pairs_hook=_sin_duplicados)
    except json.JSONDecodeError as exc:
        raise ValueError("%s no es JSON válido (%s)" % (ruta, exc))
    except ValueError as exc:
        raise ValueError("%s: %s" % (ruta, exc))
    if not isinstance(datos, dict):
        raise ValueError("%s tiene que ser un objeto JSON con las claves %s" % (ruta, ", ".join(CLAVES_DEL_ARCHIVO)))
    return datos


def partir_comandos(texto):
    partes, buf, comilla, i = [], [], None, 0
    while i < len(texto):
        c = texto[i]
        if comilla:
            buf.append(c)
            if c == comilla:
                comilla = None
        elif c in "'\"":
            comilla = c
            buf.append(c)
        elif c == "\n" or c == ";" or texto.startswith("&&", i):
            partes.append("".join(buf))
            buf = []
            i += 1 if c != "&" else 2
            continue
        else:
            buf.append(c)
        i += 1
    partes.append("".join(buf))
    return [p.strip() for p in partes if p.strip()]


def partir_tramos(cmd):
    tramos, buf, comilla = [], [], None
    for c in cmd:
        if comilla:
            buf.append(c)
            if c == comilla:
                comilla = None
        elif c in "'\"":
            comilla = c
            buf.append(c)
        elif c == "|":
            tramos.append("".join(buf))
            buf = []
        else:
            buf.append(c)
    tramos.append("".join(buf))
    return [t.strip() for t in tramos]


def metacaracter_activo(texto):
    comilla, i = None, 0
    while i < len(texto):
        c = texto[i]
        if comilla == "'":
            if c == "'":
                comilla = None
        elif c == "$":
            return "expansión ('$') fuera de comillas simples"
        elif c == "`":
            return "sustitución de comandos ('`') fuera de comillas simples"
        elif c == "\\":
            return "barra invertida fuera de comillas simples"
        elif comilla == '"':
            if c == '"':
                comilla = None
        elif c in "'\"":
            comilla = c
        elif c == "#":
            return "apertura de comentario ('#') fuera de comillas"
        elif texto.startswith("&&", i):
            i += 2
            continue
        elif c in "<>" or texto.startswith("&>", i):
            return "redirección ('%s') fuera de comillas" % ("&>" if c == "&" else c)
        elif c == "&":
            return "ejecución en background ('&') fuera de comillas"
        i += 1
    return None


def _larga_prohibida(tok, nombres):
    nombre = tok[2:].split("=", 1)[0]
    return bool(nombre) and any(n.startswith(nombre) for n in nombres)


def _motivo_sort(toks):
    for t in toks[1:]:
        if t.startswith("--"):
            if _larga_prohibida(t, SORT_LARGAS_PROHIBIDAS):
                return "sort %s escribe un archivo o ejecuta un programa" % t
            if _larga_prohibida(t, SORT_LARGAS_TEMPORALES):
                return "sort %s escribe archivos temporales" % t
        elif t.startswith("-") and t != "-":
            for ch in t[1:]:
                if ch == "o":
                    return "sort -o escribe un archivo (%s)" % t
                if ch == "T":
                    return "sort -T escribe archivos temporales (%s)" % t
                if ch in SORT_CORTAS_CON_ARGUMENTO:
                    break
    return None


def _motivo_uniq(toks):
    operandos, i, solo_operandos = [], 1, False
    while i < len(toks):
        t = toks[i]
        if solo_operandos or t == "-" or not t.startswith("-"):
            operandos.append(t)
        elif t == "--":
            solo_operandos = True
        elif t.startswith("--"):
            if "=" not in t and t[2:] in UNIQ_LARGAS_CON_ARGUMENTO:
                i += 1
        else:
            for j, ch in enumerate(t[1:], 2):
                if ch in UNIQ_CORTAS_CON_ARGUMENTO:
                    i += 0 if t[j:] else 1
                    break
        i += 1
    if len(operandos) >= 2:
        return "uniq con dos operandos escribe el segundo (%s)" % operandos[1]
    return None


def _motivo_git(toks):
    for t in toks[2:]:
        if "%G" in t:
            return "git %s ejecuta el programa de firmas de la config del repo" % t
        if t.startswith("--"):
            if t[2:].startswith("output") or _larga_prohibida(t, GIT_LARGAS_PROHIBIDAS):
                return "git %s escribe un archivo o ejecuta un programa" % t
        elif t.startswith("-") and "O" in t[1:]:
            return "git -O ejecuta un pager o lee un archivo (%s)" % t
    return None


def flag_que_escribe(toks):
    revisor = {"sort": _motivo_sort, "uniq": _motivo_uniq, "git": _motivo_git}.get(toks[0])
    return revisor(toks) if revisor else None


def comando_seguro(texto):
    if not isinstance(texto, str):
        return False, "comando vacío"
    texto = texto.replace("\\\n", " ")
    segmentos = []
    for comando in partir_comandos(texto):
        for posicion, tramo in enumerate(partir_tramos(comando)):
            try:
                segmentos.append((posicion == 0, shlex.split(tramo, posix=True)))
            except ValueError as exc:
                return False, "comando mal formado (%s)" % exc
    if not segmentos:
        return False, "comando vacío"
    motivo = metacaracter_activo(texto)
    if motivo:
        return False, motivo + " no permitida"
    for primero, toks in segmentos:
        if not toks:
            return False, "tramo vacío"
        if any(t in ("&", "||", ">", ">>", "<") for t in toks):
            return False, "redirección o ejecución en background no permitida"
        if toks[0] == "git":
            if len(toks) < 2 or toks[1] not in GIT_VERBOS_SEGUROS:
                return False, "verbo git no permitido: %s" % (" ".join(toks[:2]))
        elif toks[0] not in FILTROS_SEGUROS:
            return False, "comando no permitido: %s" % toks[0]
        elif primero:
            return False, "el primer tramo de cada comando tiene que ser git: un filtro al comienzo lee archivos del disco"
        motivo = flag_que_escribe(toks)
        if motivo:
            return False, motivo
    return True, None


def ref_de(afirmacion):
    ref = afirmacion.get("ref")
    return REF_POR_DEFECTO if ref is None else ref


def ref_valido(ref):
    return isinstance(ref, str) and REF_VALIDO.fullmatch(ref) is not None


def comando_sustituido(afirmacion):
    comando = afirmacion.get("comando")
    if not isinstance(comando, str):
        return ""
    return comando.replace("{ref}", str(ref_de(afirmacion)))


def tramo_git_sin_ref(comando):
    for cmd in partir_comandos(comando.replace("\\\n", " ")):
        for tramo in partir_tramos(cmd):
            try:
                toks = shlex.split(tramo, posix=True)
            except ValueError:
                continue
            if len(toks) > 1 and toks[0] == "git" and toks[1] in GIT_VERBOS_CON_REF and "{ref}" not in tramo:
                return tramo
    return None


def _git_de_instalacion():
    git_exe = shutil.which("git")
    if git_exe:
        for padre in Path(git_exe).parents:
            candidato = padre / "bin" / "bash.exe"
            if candidato.exists():
                return str(candidato)
    return None


def bash_ejecutable():
    derivado = _git_de_instalacion()
    if derivado:
        return derivado
    encontrado = shutil.which("bash")
    if encontrado and "system32" not in encontrado.lower():
        return encontrado
    return None


def entorno_de_corrida(base=None):
    resultado = {}
    for k, v in entorno_git(base).items():
        mayus = k.upper()
        if mayus in ENTORNO_DE_ARRANQUE or mayus.startswith(PREFIJO_DE_FUNCIONES_EXPORTADAS):
            continue
        if mayus.startswith("GIT_") and k not in GIT_CONSERVADAS:
            continue
        resultado[k] = v
    return resultado


def _plazo_valido(plazo):
    ok = isinstance(plazo, (int, float)) and not isinstance(plazo, bool) and math.isfinite(plazo) and plazo > 0
    return plazo if ok else PLAZO_POR_DEFECTO


def _ejecutar(argv, cwd, env, plazo):
    with tempfile.TemporaryFile() as salida, tempfile.TemporaryFile() as error:
        proceso = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=salida, stderr=error, cwd=cwd, env=env)
        try:
            proceso.wait(timeout=plazo + MARGEN_DEL_PLAZO)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait()
            raise
        salida.seek(0)
        error.seek(0)
        return proceso.returncode, salida.read(), error.read()


def juzgar(afirmacion, obtenidos):
    if "expected" not in afirmacion:
        return Veredicto(ERROR, "sin 'expected': no hay contra qué juzgar")
    esperado = afirmacion["expected"]
    esp = [str(v) for v in (esperado.values() if isinstance(esperado, dict) else [esperado])]
    if len(esp) != len(obtenidos):
        return Veredicto(ERROR, "el comando produjo %d valor(es) y 'expected' declara %d" % (len(obtenidos), len(esp)))
    if esp == obtenidos:
        return Veredicto(OK, ", ".join(obtenidos))
    if afirmacion.get("naturaleza") != "inventario":
        return Veredicto(DRIFT, "esperado %s, obtenido %s" % (esp, obtenidos))
    deltas, bajo = [], False
    for e, o in zip(esp, obtenidos):
        try:
            d = int(o) - int(e)
        except ValueError:
            return Veredicto(DRIFT, "valor no numerico: esperado %s, obtenido %s" % (esp, obtenidos))
        deltas.append("=" if d == 0 else "%+d" % d)
        bajo = bajo or d < 0
    detalle = "%s (linea base %s -> %s)" % (", ".join(deltas), ", ".join(esp), ", ".join(obtenidos))
    if bajo:
        return Veredicto(DRIFT, "BAJO " + detalle)
    return Veredicto(CRECIO, detalle)


def correr(afirmacion, ruta_repo, entorno=None, plazo=PLAZO_POR_DEFECTO):
    if not isinstance(afirmacion, dict) or afirmacion.get("ejecutor") != "repo":
        return Veredicto(ERROR, "no es una afirmación de repo")
    if "expected" not in afirmacion:
        return Veredicto(ERROR, "sin 'expected': no hay contra qué juzgar")
    repo = Path(ruta_repo)
    if not repo.is_dir():
        return Veredicto(ERROR, "repo inexistente: %s" % repo)
    if not (repo / ".git").exists():
        return Veredicto(ERROR, "no es un repo git (falta .git): %s" % repo)
    ref = ref_de(afirmacion)
    if not ref_valido(ref):
        return Veredicto(ERROR, "ref no válido: %r" % (ref,))
    comando = comando_sustituido(afirmacion)
    ok, motivo = comando_seguro(comando)
    if not ok:
        return Veredicto(ERROR, motivo)
    plazo = _plazo_valido(plazo)
    env = entorno_de_corrida(entorno)
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "%s^{commit}" % ref],
                           capture_output=True, stdin=subprocess.DEVNULL, timeout=plazo, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Veredicto(ERROR, "no se pudo ejecutar git (%s)" % exc)
    if r.returncode != 0:
        causa = decodificar(r.stderr).strip().splitlines()
        return Veredicto(ERROR, "el ref '%s' no resuelve a un commit en %s%s" % (
            ref, repo, " (%s)" % causa[0].strip() if causa else ""))
    bash = bash_ejecutable()
    if not bash:
        return Veredicto(ERROR, "bash no encontrado (ni junto a git ni en el PATH)")
    modo = "-c" if bash == _git_de_instalacion() else "-lc"
    obtenidos = []
    for cmd in partir_comandos(comando.replace("\\\n", " ")):
        try:
            codigo, salida, error = _ejecutar([bash, modo, GUION_DEL_PLAZO, "_", str(plazo), PREFIJO_DE_GIT + cmd],
                                              str(repo), env, plazo)
        except subprocess.TimeoutExpired:
            return Veredicto(ERROR, "plazo de %s s agotado: %s" % (plazo, cmd))
        except OSError as exc:
            return Veredicto(ERROR, "no se pudo ejecutar (%s)" % exc)
        if codigo in SALIDAS_DE_PLAZO:
            return Veredicto(ERROR, "plazo de %s s agotado: %s" % (plazo, cmd))
        causa = decodificar(error).strip().splitlines()
        if causa:
            return Veredicto(ERROR, "stderr: %s" % causa[0].strip())
        valores = decodificar(salida).strip().splitlines()
        if not valores:
            return Veredicto(ERROR, "sin salida: %s" % cmd)
        obtenidos.append(valores[-1].strip())
    return juzgar(afirmacion, obtenidos)


def lint(datos, repos_conocidos=None):
    salida = []

    def agregar(sev, texto, arreglo=None, claim=None):
        salida.append(Hallazgo(sev, texto, arreglo, claim))

    if not isinstance(datos, dict):
        agregar(FAIL, "el archivo tiene que ser un objeto con las claves %s" % ", ".join(CLAVES_DEL_ARCHIVO))
        return salida
    conocidos = None if repos_conocidos is None else set(repos_conocidos)
    version = datos.get("version")
    if type(version) is not int or version != VERSION:
        agregar(FAIL, "version: %s (este lector entiende la %d)" % (
            repr(version) if "version" in datos else "ausente", VERSION))
    for clave in datos:
        if clave not in CLAVES_DEL_ARCHIVO:
            agregar(WARN, "clave '%s' desconocida en el archivo" % clave,
                    "claves del archivo: %s; una clave mal escrita deja sin leer lo que contiene" % ", ".join(CLAVES_DEL_ARCHIVO))
    afirmaciones = datos.get("claims")
    if not isinstance(afirmaciones, list):
        agregar(FAIL, "claims: tiene que ser una lista de afirmaciones")
        return salida
    ids = [c["id"] for c in afirmaciones if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"]]
    for cid in sorted({i for i in ids if ids.count(i) > 1}):
        agregar(FAIL, "%s: id repetido en %d afirmaciones" % (cid, ids.count(cid)),
                "cada afirmación lleva un id único: el juicio busca por id")
    rechazados = datos.get("rechazados")
    for r in rechazados if isinstance(rechazados, list) else []:
        if isinstance(r, dict) and r.get("id") in ids:
            agregar(FAIL, "%s: el id está en claims y en rechazados" % r["id"],
                    "renombrar uno de los dos: un rechazado no puede compartir id con una afirmación viva")
    for i, c in enumerate(afirmaciones):
        if not isinstance(c, dict):
            agregar(FAIL, "afirmación %d: no es un objeto" % i, claim=i)
            continue
        if not isinstance(c.get("id"), str) or not c["id"]:
            agregar(FAIL, "afirmación %d: sin id (una cadena no vacía)" % i, claim=i)
        cid = c.get("id") if isinstance(c.get("id"), str) and c.get("id") else "<sin id>"
        if c.get("tipo") not in TIPOS:
            agregar(WARN, "%s: tipo %r no es %s" % (cid, c.get("tipo"), "|".join(TIPOS)),
                    "los volúmenes de datos vivos se rechazan", i)
        if c.get("naturaleza") not in NATURALEZAS:
            agregar(FAIL, "%s: naturaleza %r no es %s" % (cid, c.get("naturaleza"), "|".join(NATURALEZAS)),
                    "declarar la naturaleza: el criterio es si el documento ENUMERA los items (invariante) o solo los cuenta (inventario)", i)
        if "expected" not in c:
            agregar(FAIL, "%s: sin 'expected'" % cid, "una afirmación sin esperado no verifica nada", i)
        ejecutor = c.get("ejecutor")
        if ejecutor == "repo":
            _lint_de_repo(c, cid, i, conocidos, agregar)
        elif ejecutor != "sql":
            agregar(WARN, "%s: ejecutor %r desconocido" % (cid, ejecutor),
                    "ejecutores válidos: %s" % ", ".join(sorted(EJECUTORES)), i)
    return salida


def _lint_de_repo(c, cid, i, conocidos, agregar):
    repo = c.get("repo")
    if not isinstance(repo, str) or not repo:
        agregar(FAIL, "%s: afirmación de repo sin 'repo'" % cid, "la clave de un repo declarado en repos de la config", i)
    elif conocidos is not None and repo not in conocidos:
        agregar(FAIL, "%s: el repo %r no es una clave de repos de la config" % (cid, repo),
                "claves declaradas: %s" % (", ".join(sorted(conocidos)) or "(ninguna)"), i)
    ref = ref_de(c)
    if not ref_valido(ref):
        agregar(FAIL, "%s: ref %r no es válido" % (cid, ref),
                "un nombre de rama, etiqueta o commit; sin 'ref' vale %s" % REF_POR_DEFECTO, i)
    tramo = tramo_git_sin_ref(c.get("comando") if isinstance(c.get("comando"), str) else "")
    if tramo:
        agregar(FAIL, "%s: tramo git sin {ref}: %r" % (cid, tramo),
                "escribir {ref} donde va el árbol (git show {ref}:ruta, git ls-tree -r {ref}); sin él, la afirmación "
                "mide el working tree o un ref escrito a mano que el campo no gobierna", i)
    ok, motivo = comando_seguro(comando_sustituido(c))
    if not ok:
        agregar(FAIL, "%s: comando no ejecutable (%s)" % (cid, motivo),
                "el motor solo corre git de lectura y filtros de texto", i)


def antiguedad_fetch(ruta_repo):
    try:
        r = subprocess.run(["git", "-C", str(ruta_repo), "rev-parse", "--git-path", "FETCH_HEAD"],
                           capture_output=True, stdin=subprocess.DEVNULL, timeout=PLAZO_POR_DEFECTO,
                           env=entorno_de_corrida())
    except (OSError, subprocess.TimeoutExpired):
        return None
    ruta = decodificar(r.stdout).strip()
    if r.returncode != 0 or not ruta:
        return None
    fetch_head = Path(ruta)
    if not fetch_head.is_absolute():
        fetch_head = Path(ruta_repo) / fetch_head
    if not fetch_head.is_file():
        return None
    return int((time.time() - fetch_head.stat().st_mtime) // 86400)


def fetch_viejo(ruta_repo, dias=FETCH_MAX_DIAS, nombre=None):
    etiqueta = nombre or str(ruta_repo)
    antiguedad = antiguedad_fetch(ruta_repo)
    arreglo = "git -C %s fetch (el motor no lo hace: solo lee)" % ruta_repo
    if antiguedad is None:
        return Hallazgo(WARN, "%s: sin FETCH_HEAD: nunca se hizo fetch en este clon, origin/* es la foto del clon" % etiqueta,
                        arreglo, None)
    if antiguedad > dias:
        return Hallazgo(WARN, "%s: último fetch hace %d días (> %d): origin/* es una foto vieja" % (etiqueta, antiguedad, dias),
                        arreglo, None)
    return Hallazgo(INFO, "%s: último fetch hace %d día(s)" % (etiqueta, antiguedad), None, None)
