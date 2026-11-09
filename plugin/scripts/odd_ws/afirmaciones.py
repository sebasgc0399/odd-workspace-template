import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from collections import namedtuple
from pathlib import Path

from odd_ws.comun import decodificar, entorno_git

VERSION = 1
SISTEMA = os.name
CLAVES_DEL_ARCHIVO = ("version", "reglas", "claims", "rechazados", "cobertura_triada")
TIPOS = ("estructura", "contrato")
NATURALEZAS = ("invariante", "inventario")
EJECUTORES = ("repo", "sql")
FAIL, WARN, INFO = "FAIL", "warn", "info"
OK, CRECIO, DRIFT, ERROR = "OK", "CRECIO", "DRIFT", "ERROR"
REF_POR_DEFECTO = "origin/HEAD"
REF_VALIDO = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/@^-]*")
PLAZO_POR_DEFECTO = 60
MARGEN_DEL_PLAZO = 10
ESPERA_TRAS_MATAR = 5
PLAZO_MINIMO = 0.000001
PLAZO_DE_TASKKILL = 20
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
GIT_CONSERVADAS = frozenset(("GIT_OPTIONAL_LOCKS",))
CARACTERES_DE_EXPANSION = "{}*?[]~"
REGEX_DE_FIRMAS = re.compile(r"%[-+ ]?G")
SIN_PROGRAMA = "/odd-ws-sin-programa/no-existe"
CONFIG_FORZADA = (
    ("core.fsmonitor", "false"),
    ("log.showSignature", "false"),
    ("gpg.program", SIN_PROGRAMA),
    ("gpg.openpgp.program", SIN_PROGRAMA),
    ("gpg.ssh.program", SIN_PROGRAMA),
    ("gpg.x509.program", SIN_PROGRAMA),
)
PROTECCIONES_DE_GIT = {
    "show": ("--no-textconv", "--no-ext-diff", "--no-show-signature"),
    "log": ("--no-textconv", "--no-ext-diff", "--no-show-signature"),
    "diff-tree": ("--no-textconv", "--no-ext-diff"),
}

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
        elif c in CARACTERES_DE_EXPANSION:
            return "expansión de llaves, globs o '~' ('%s') fuera de comillas" % c
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


def _guion_en_grupo_corto(tok, cortas_con_argumento):
    if not tok.startswith("-") or tok.startswith("--"):
        return False
    for ch in tok[1:]:
        if ch == "-":
            return True
        if ch in cortas_con_argumento:
            return False
    return False


def _motivo_guion_en_grupo_corto(toks, cortas_con_argumento):
    for t in toks[1:]:
        if _guion_en_grupo_corto(t, cortas_con_argumento):
            return "%s %s: un '-' dentro de un grupo de opciones cortas abre una opción larga que la lista blanca no revisa" % (
                toks[0], t)
    return None


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
    return _motivo_guion_en_grupo_corto(toks, SORT_CORTAS_CON_ARGUMENTO)


def _operandos_de_uniq(toks, permuta):
    operandos, i, solo_operandos = [], 1, False
    while i < len(toks):
        t = toks[i]
        if solo_operandos or t == "-" or not t.startswith("-"):
            operandos.append(t)
            solo_operandos = solo_operandos or not permuta
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
    return operandos


def _motivo_uniq(toks):
    for permuta in (True, False):
        operandos = _operandos_de_uniq(toks, permuta)
        if len(operandos) >= 2:
            return "uniq con dos operandos escribe el segundo (%s)" % operandos[1]
    return _motivo_guion_en_grupo_corto(toks, UNIQ_CORTAS_CON_ARGUMENTO)


def _motivo_git(toks):
    for t in toks[2:]:
        if REGEX_DE_FIRMAS.search(t):
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


def plan_de_comando(texto):
    if not isinstance(texto, str):
        return None, "comando vacío"
    if "\x00" in texto:
        return None, "carácter NUL no permitido"
    texto = texto.replace("\\\n", " ")
    comandos = []
    for comando in partir_comandos(texto):
        tramos = []
        for tramo in partir_tramos(comando):
            try:
                tramos.append(shlex.split(tramo, posix=True))
            except ValueError as exc:
                return None, "comando mal formado (%s)" % exc
        comandos.append((comando, tramos))
    if not comandos:
        return None, "comando vacío"
    motivo = metacaracter_activo(texto)
    if motivo:
        return None, motivo + " no permitida"
    for _, tramos in comandos:
        for posicion, toks in enumerate(tramos):
            if not toks:
                return None, "tramo vacío"
            if any(t in ("&", "||", ">", ">>", "<") for t in toks):
                return None, "redirección o ejecución en background no permitida"
            if toks[0] == "git":
                if len(toks) < 2 or toks[1] not in GIT_VERBOS_SEGUROS:
                    return None, "verbo git no permitido: %s" % (" ".join(toks[:2]))
            elif toks[0] not in FILTROS_SEGUROS:
                return None, "comando no permitido: %s" % toks[0]
            elif posicion == 0:
                return None, "el primer tramo de cada comando tiene que ser git: un filtro al comienzo lee archivos del disco"
            motivo = flag_que_escribe(toks)
            if motivo:
                return None, motivo
    return comandos, None


def comando_seguro(texto):
    comandos, motivo = plan_de_comando(texto)
    return motivo is None, motivo


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


def carpeta_de_filtros():
    if os.name == "nt":
        git_exe = shutil.which("git")
        if git_exe:
            for padre in Path(git_exe).parents:
                candidato = padre / "usr" / "bin"
                if (candidato / "sort.exe").is_file():
                    return str(candidato)
        return None
    return "/usr/bin" if os.path.isdir("/usr/bin") else None


def resolver_argv(argv):
    if not argv:
        return None, "tramo vacío"
    nombre = argv[0]
    if nombre == "git":
        git_exe = shutil.which("git")
        if not git_exe:
            return None, "git no encontrado en el PATH"
        verbo = argv[1:2]
        return [git_exe, *verbo, *PROTECCIONES_DE_GIT.get(verbo[0] if verbo else "", ()), *argv[2:]], None
    if nombre not in FILTROS_SEGUROS:
        return None, "comando no permitido: %s" % nombre
    carpeta = carpeta_de_filtros()
    if carpeta is None:
        return None, "no se encontró la carpeta usr/bin de Git for Windows (de ahí salen los filtros, nunca del PATH)"
    ruta = os.path.join(carpeta, nombre + (".exe" if os.name == "nt" else ""))
    if not os.path.isfile(ruta):
        return None, "no existe el filtro %s en %s" % (nombre, carpeta)
    return ["/usr/bin/" + nombre, *argv[1:]], None


def ruta_de_bash():
    if os.name == "nt":
        carpeta = carpeta_de_filtros()
        if carpeta:
            ruta = os.path.join(carpeta, "bash.exe")
            if os.path.isfile(ruta):
                return ruta
        return None
    return "/bin/bash" if os.path.isfile("/bin/bash") else shutil.which("bash")


def entorno_de_corrida(base=None):
    propio = entorno_git(base)
    resultado = {}
    for k, v in propio.items():
        mayus = k.upper()
        if mayus in ENTORNO_DE_ARRANQUE or mayus.startswith(PREFIJO_DE_FUNCIONES_EXPORTADAS):
            continue
        if mayus.startswith("GIT_") and k not in GIT_CONSERVADAS:
            continue
        resultado[k] = v
    pares = [(propio["GIT_CONFIG_KEY_%d" % i], propio["GIT_CONFIG_VALUE_%d" % i]) for i in range(int(propio.get("GIT_CONFIG_COUNT", "0")))]
    pares.extend(CONFIG_FORZADA)
    resultado["GIT_CONFIG_COUNT"] = str(len(pares))
    for i, (clave, valor) in enumerate(pares):
        resultado["GIT_CONFIG_KEY_%d" % i] = clave
        resultado["GIT_CONFIG_VALUE_%d" % i] = valor
    resultado["GIT_NO_LAZY_FETCH"] = "1"
    return resultado


def _plazo_valido(plazo):
    ok = isinstance(plazo, (int, float)) and not isinstance(plazo, bool) and math.isfinite(plazo) and plazo > 0
    return plazo if ok else PLAZO_POR_DEFECTO


def _matar_arboles(procesos):
    for proceso in procesos:
        if proceso.poll() is not None:
            continue
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proceso.pid)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=PLAZO_DE_TASKKILL)
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(proceso.pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            proceso.kill()
        except OSError:
            pass
    for proceso in procesos:
        try:
            proceso.wait(timeout=ESPERA_TRAS_MATAR)
        except subprocess.TimeoutExpired:
            pass


def _lanzar(argvs, cwd, env, plazo):
    plazo = _plazo_valido(plazo)
    opciones = {} if os.name == "nt" else {"start_new_session": True}
    with tempfile.TemporaryFile() as salida, tempfile.TemporaryFile() as error:
        procesos = []
        try:
            previo = None
            for i, argv in enumerate(argvs):
                proceso = subprocess.Popen(
                    argv, stdin=subprocess.DEVNULL if previo is None else previo.stdout,
                    stdout=salida if i == len(argvs) - 1 else subprocess.PIPE, stderr=error, cwd=cwd, env=env, **opciones)
                if previo is not None:
                    previo.stdout.close()
                procesos.append(proceso)
                previo = proceso
            limite = time.monotonic() + plazo
            for proceso in procesos:
                proceso.wait(timeout=max(0.0, limite - time.monotonic()))
        except BaseException:
            _matar_arboles(procesos)
            raise
        salida.seek(0)
        error.seek(0)
        return salida.read(), error.read(), [proceso.returncode for proceso in procesos]


def ejecutar_tramos(argvs, cwd, env, plazo):
    salida, error, _ = _lanzar(argvs, cwd, env, plazo)
    return salida, error


def _texto_de_plazo(plazo):
    texto = ("%.6f" % max(plazo, PLAZO_MINIMO)).rstrip("0").rstrip(".")
    return texto or "%g" % PLAZO_MINIMO


def _prefijo_de_plazo(plazo):
    if SISTEMA != "nt":
        return []
    return ["/usr/bin/timeout", "-k", "2", _texto_de_plazo(plazo)]


def generar_guion(argvs, cwd, plazo):
    prefijo = _prefijo_de_plazo(plazo)
    tuberia = []
    for i, argv in enumerate(argvs):
        linea = " ".join(shlex.quote(t) for t in [*prefijo, *argv])
        tuberia.append(linea + " </dev/null" if i == 0 else linea)
    return "\n".join([
        "cd -- %s || exit 125" % shlex.quote(cwd),
        " | ".join(tuberia),
        'estados=("${PIPESTATUS[@]}")',
        'for estado in "${estados[@]}"; do',
        '    if [ "$estado" = 124 ] || [ "$estado" = 137 ]; then exit 124; fi',
        "done",
        "exit 0",
    ]) + "\n"


def ejecutar_con_bash(argvs, cwd, env, plazo):
    plazo = _plazo_valido(plazo)
    bash = ruta_de_bash()
    if bash is None:
        raise OSError("no se encontró el bash de Git for Windows")
    guion = generar_guion(argvs, str(cwd), plazo)
    limite = plazo + MARGEN_DEL_PLAZO if _prefijo_de_plazo(plazo) else plazo
    descriptor, ruta = tempfile.mkstemp(prefix="afirmaciones-", suffix=".sh")
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(guion.encode("utf-8"))
        carpeta, nombre = os.path.split(ruta)
        salida, error, codigos = _lanzar([[bash, nombre]], carpeta, env, limite)
    except subprocess.TimeoutExpired:
        raise subprocess.TimeoutExpired(argvs, plazo) from None
    finally:
        try:
            os.unlink(ruta)
        except OSError:
            pass
    if codigos[0] == 124:
        raise subprocess.TimeoutExpired(argvs, plazo)
    return salida, error


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
    comandos, motivo = plan_de_comando(comando_sustituido(afirmacion))
    if motivo:
        return Veredicto(ERROR, motivo)
    ejecuciones = []
    for texto, tramos in comandos:
        argvs = []
        for tramo in tramos:
            argv, motivo = resolver_argv(tramo)
            if motivo:
                return Veredicto(ERROR, motivo)
            argvs.append(argv)
        ejecuciones.append((texto, argvs))
    argv_ref, motivo = resolver_argv(["git", "rev-parse", "--verify", "--quiet", "%s^{commit}" % ref])
    if motivo:
        return Veredicto(ERROR, motivo)
    plazo = _plazo_valido(plazo)
    env = entorno_de_corrida(entorno)
    try:
        salida, error = ejecutar_tramos([argv_ref], str(repo), env, plazo)
    except subprocess.TimeoutExpired:
        return Veredicto(ERROR, "plazo de %s s agotado: la verificación del ref" % plazo)
    except (OSError, ValueError) as exc:
        return Veredicto(ERROR, "no se pudo ejecutar git (%s)" % exc)
    if not decodificar(salida).strip():
        causa = decodificar(error).strip().splitlines()
        return Veredicto(ERROR, "el ref '%s' no resuelve a un commit en %s%s" % (ref, repo, " (%s)" % causa[0].strip() if causa else ""))
    obtenidos = []
    for texto, argvs in ejecuciones:
        try:
            salida, error = ejecutar_con_bash(argvs, str(repo), env, plazo)
        except subprocess.TimeoutExpired:
            return Veredicto(ERROR, "plazo de %s s agotado: %s" % (plazo, texto))
        except (OSError, ValueError) as exc:
            return Veredicto(ERROR, "no se pudo ejecutar (%s)" % exc)
        causa = decodificar(error).strip().splitlines()
        if causa:
            return Veredicto(ERROR, "stderr: %s" % causa[0].strip())
        valores = decodificar(salida).strip().splitlines()
        if not valores:
            return Veredicto(ERROR, "sin salida: %s" % texto)
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
    argv, motivo = resolver_argv(["git", "rev-parse", "--git-path", "FETCH_HEAD"])
    if motivo:
        return None
    try:
        salida, _ = ejecutar_tramos([argv], str(ruta_repo), entorno_de_corrida(), PLAZO_POR_DEFECTO)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    ruta = decodificar(salida).strip()
    if not ruta:
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
