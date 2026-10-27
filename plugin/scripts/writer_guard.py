import sys

sys.dont_write_bytecode = True

PREFILTRO = b"writer-"
ENTRADA = None
if __name__ == "__main__":
    try:
        ENTRADA = sys.stdin.buffer.read()
        if PREFILTRO not in ENTRADA:
            sys.exit(0)
    except Exception:
        sys.exit(0)

import hashlib
import json
import os
import posixpath
import re
import time

import config_loader
from odd_ws import capas as convencion
from odd_ws import rutas
from odd_ws.comun import PLAZO_POR_DEFECTO, SILENCIO, correr_hook, id_valido, plazo_de, raiz_de_instancia, temporal

HERRAMIENTAS_DE_ESCRITURA = ("Edit", "Write", "MultiEdit")
MAX_FOTO = 8 * 1024 * 1024
PROFUNDIDAD_MAX = 6
MAX_SUBS = 50
NULOS = ("/dev/null", "nul", "nul:")

GIT_ESCRIBE = {
    "add", "commit", "push", "checkout", "switch", "stash", "restore", "reset", "rebase", "merge",
    "cherry-pick", "clean", "rm", "mv", "worktree", "pull", "revert", "apply", "am", "update-index",
}
GIT_LECTURA_DE = {"stash": {"list", "show"}, "worktree": {"list"}}
RAMA_BORRA = re.compile(r"^-[A-Za-z]*[dD]")
GIT_OPCIONES_CON_VALOR = {"-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env", "--attr-source"}
ENVOLTORIOS = {"time", "nohup", "command", "exec", "sudo", "env", "xargs", "start", "call", "builtin", "nice", "{", "}", "!",
               "if", "then", "do", "else", "elif", "while", "until", "&"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "powershell", "pwsh", "cmd", "eval"}
SHELLS_DE_CUERPO = SHELLS - {"eval"}
ESCAPE_DE_SHELL = {"bash": "\\", "sh": "\\", "zsh": "\\", "dash": "\\", "ksh": "\\", "eval": "\\", "powershell": "`", "pwsh": "`",
                   "cmd": None}
ESCAPE_QUE_CAMBIA = {"\\": re.compile(r"\\[ \t\r\n\"']"), "`": re.compile(r"`[ \t\r\n\"']|\\\"")}
ESCAPE_ALGUNO = re.compile(r"[\\`][ \t\r\n\"']")
GRAVE_ESCAPADO = re.compile(r"`([` \t\r\n])")
COMILLAS_PS = re.compile(r"`.|'[^']*'?|\"(?:`.|[^\"`])*\"?", re.DOTALL)
CUERPO_ALGUNO = re.compile(r"(?<!<)<<(?!<)|@['\"][ \t]*\r?\n")
HEREDOC_APERTURA = re.compile(r"<<(-?)[ \t]*((?:[^\s;&|()<>'\"\\]|\\.|'[^']*'|\"[^\"]*\")+)")
HEREDOC_COMILLAS = re.compile(r"'([^']*)'|\"([^\"]*)\"|\\(.)")
HEREDOC_A_SHELL = re.compile(r"(?i)\|\s*(?:[^\s|;&]*[\\/])?(?:bash|sh|zsh|dash|ksh|pwsh|powershell|cmd)(?:\.exe)?(?![\w.-])")
HERE_STRING_APERTURA = re.compile(r"@(['\"])[ \t]*\r?\n")
CAMBIAR_DIR = {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}
ESCRIBEN_TODO = {
    "tee", "set-content", "add-content", "out-file", "clear-content", "new-item", "remove-item", "rename-item", "set-item",
    "ni", "sc", "ac", "rm", "del", "erase", "rmdir", "rd", "ri", "ren", "rni", "rename", "mv", "move", "move-item", "mi",
    "touch", "truncate", "unlink", "shred",
}
PRIMER_POSICIONAL = {"set-content", "add-content", "out-file", "clear-content", "new-item", "set-item", "sc", "ac", "ni"}
COPIAN = {"cp", "copy", "copy-item", "cpi", "xcopy", "robocopy", "install"}
COPIAN_CON_BARRAS = {"xcopy", "robocopy"}
XARGS_CON_VALOR = {"-I", "-L", "-n", "-P", "-s", "-E", "-d", "-a", "--max-args", "--max-procs", "--max-lines", "--delimiter",
                   "--replace", "--arg-file", "--max-chars", "--eof"}
OPCION_BARRA = re.compile(r"^/[A-Za-z?][A-Za-z0-9_]*(:.*)?$")
PERL_EN_SITIO = re.compile(r"^-(?:(?![MmIdDxFCeE])[A-Za-z0-9])*i")
CLR_LLAMADA = re.compile(
    r"\[(?:System\.)?IO\.File\]::(WriteAll\w+|AppendAll\w+|Delete|Create|OpenWrite|CreateText|AppendText|Copy|Move|Replace)\s*\(",
    re.IGNORECASE)
CLR_LITERAL = re.compile(r"^\s*(?:'([^']*)'|\"([^\"$`]*)\")\s*$", re.DOTALL)
CLR_VARIABLE = re.compile(r"^\s*\$(\w+)\s*$")
CLR_COMILLADO = re.compile(r"'([^']*)'|\"([^\"]*)\"")
SP_CON_VALOR = {"-workingdirectory", "-windowstyle", "-verb", "-redirectstandardinput", "-redirectstandardoutput",
                "-redirectstandarderror", "-credential", "-environment"}
FIND_FIN_EXEC = {"+", ";", "\\"}
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
FIND_OPCIONES_INICIO = {"-h", "-l", "-p"}
PY_BANDERAS_C = re.compile(r"^-[A-Za-z]+c$")
CLR_DESTINO_SEGUNDO = {"copy", "move"}
PY_COMILLADO = re.compile(r"""(['"])((?:\\.|(?!\1).)*)\1""", re.DOTALL)
PY_ESCRIBE = re.compile(
    r"""open\s*\(\s*[^,)]+,\s*['"][rwabxt+]*[wax+][rwabxt+]*['"]|\.open\s*\(\s*['"][rwabxt+]*[wax+][rwabxt+]*['"]|"""
    r"""mode\s*=\s*['"][rwabxt+]*[wax+][rwabxt+]*['"]|write_text|write_bytes|\.write\s*\(|shutil\.|"""
    r"""os\.(remove|rename|replace|unlink|rmdir|removedirs|makedirs|mkdir)|\.unlink\s*\(|\.rename\s*\(|\.rmdir\s*\(|\.touch\s*\(""")
PY_PROCESO = re.compile(r"subprocess|os\.system|os\.popen|\bPopen\b|check_call|check_output|os\.exec|os\.spawn")
PY_GIT = re.compile(r"\bgit(?:\.exe)?\b")
PYTHON_RE = re.compile(r"python[0-9.]*|py|pythonw")
HEREDOC_MARCA = re.compile(r"^<<(-?)([\w.-]*)$")
PY_OPCIONES_CON_VALOR = {"-X", "-W"}
OPCIONES_DESTINO = {"-destination", "-t", "--target-directory", "-dest"}
SED_EN_SITIO = re.compile(r"^-[A-Za-z]*i")
ASIGNACION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

_COLECTOR = None
_UNIR = False
_CUERPOS = False
_ZONAS = None
_LIMITE = None
_VERIFICAR = []


class _SinTiempo(Exception):
    pass


def _vigente():
    if _LIMITE is not None and time.monotonic() > _LIMITE:
        raise _SinTiempo()


def _verificar_capa():
    if not _VERIFICAR:
        import verificar_capa
        _VERIFICAR.append(verificar_capa)
    return _VERIFICAR[0]


class Zonas:
    def __init__(self, config, entorno=None):
        origen = os.environ if entorno is None else entorno
        self.entorno = {k.upper(): v for k, v in origen.items()} if os.name == "nt" else dict(origen)
        self.config = config
        self.raiz = config_loader.canonica(config["raiz"])
        self.arboles = [config_loader.canonica(r) for repo in config["repos"].values()
                        for r in [repo["path"], *repo.get("worktrees", [])]]
        self.padres = []
        for capa in config["layers"].values():
            for patron in capa.get("workshop") or []:
                partes = patron.split("/")
                self.padres.append("/".join(partes[:-1]))
                if partes[-1] == "**":
                    self.padres.append(patron)
        carpeta = temporal(self.entorno)
        self.scratch = config_loader.canonica(os.path.join(carpeta, "claude")) if carpeta else None
        self._archivos, self._carpetas = {}, {}

    def variable(self, nombre):
        return self.entorno.get(nombre.upper() if os.name == "nt" else nombre)

    def _scratch_canonica(self, canonica):
        return self.scratch is not None and config_loader._dentro(canonica, self.scratch)

    def es_scratch(self, ruta):
        return isinstance(ruta, str) and bool(ruta) and self._scratch_canonica(config_loader.canonica(ruta))

    def _alcanza_un_repo(self, canonica):
        return any(config_loader._dentro(canonica, arbol) or config_loader._dentro(arbol, canonica) for arbol in self.arboles)

    def archivo(self, ruta):
        if ruta not in self._archivos:
            _vigente()
            c = config_loader.canonica(ruta)
            if self._scratch_canonica(c):
                self._archivos[ruta] = False
            elif self._alcanza_un_repo(c):
                self._archivos[ruta] = True
            else:
                self._archivos[ruta] = (config_loader._dentro(c, self.raiz)
                                        and config_loader.clasificar(ruta, self.config) is not None)
        return self._archivos[ruta]

    def carpeta(self, ruta):
        if ruta not in self._carpetas:
            _vigente()
            c = config_loader.canonica(ruta)
            if self._scratch_canonica(c):
                self._carpetas[ruta] = False
            elif self._alcanza_un_repo(c):
                self._carpetas[ruta] = True
            elif not config_loader._dentro(c, self.raiz):
                self._carpetas[ruta] = False
            else:
                relativa = config_loader._relativa(c, self.raiz)
                relativa = "" if relativa == "." else relativa
                self._carpetas[ruta] = any(config_loader.coincide(relativa, p) for p in self.padres)
        return self._carpetas[ruta]


def _salto(texto, i):
    if texto.startswith("\r\n", i):
        return 2
    return 1 if texto.startswith("\n", i) else 0


def _segmentar(texto, escape=None, cuerpos=None):
    segmentos, subs = [], []
    actual = {"tokens": [], "redirs": []}
    palabra, hay_palabra, pendiente = [], False, None
    comilla = None
    heredocs = []
    n, i = len(texto), 0

    def cerrar_palabra():
        nonlocal palabra, hay_palabra, pendiente
        if not hay_palabra:
            return
        valor = "".join(palabra)
        palabra, hay_palabra = [], False
        if pendiente == "dup":
            pendiente = None
        elif pendiente == "redir":
            actual["redirs"].append(valor)
            pendiente = None
        else:
            actual["tokens"].append(valor)

    def cerrar_segmento():
        nonlocal actual, pendiente
        cerrar_palabra()
        pendiente = None
        if actual["tokens"] or actual["redirs"]:
            segmentos.append(actual)
        actual = {"tokens": [], "redirs": []}

    def capturar_sustitucion(desde):
        profundidad, j = 1, desde
        while j < n and profundidad:
            if texto[j] == "(":
                profundidad += 1
            elif texto[j] == ")":
                profundidad -= 1
            j += 1
        return texto[desde:j - 1 if profundidad == 0 else j], j

    def sustituciones(desde, hasta, graves):
        j = desde
        while j < hasta and len(subs) < MAX_SUBS:
            if texto.startswith("$(", j):
                interior, j = capturar_sustitucion(j + 2)
                subs.append(interior)
            elif graves and texto[j] == "`":
                k = texto.find("`", j + 1, hasta)
                if k < 0:
                    return
                subs.append(texto[j + 1:k])
                j = k + 1
            else:
                j += 1

    def saltar_heredocs(desde):
        nonlocal heredocs
        pendientes, heredocs = heredocs, []
        if any(tuberia or _comando(seg["tokens"])[1] in SHELLS_DE_CUERPO for _, _, _, seg, tuberia in pendientes):
            return desde
        j = desde
        for delimitador, literal, tabs, _, _ in pendientes:
            inicio = j
            while j < n:
                fin = texto.find("\n", j)
                linea = texto[j:n if fin < 0 else fin].rstrip("\r")
                siguiente = n if fin < 0 else fin + 1
                if (linea.lstrip("\t") if tabs else linea) == delimitador:
                    if not literal:
                        sustituciones(inicio, j, True)
                    j = siguiente
                    break
                j = siguiente
            else:
                if not literal:
                    sustituciones(inicio, n, True)
        return j

    while i < n:
        c = texto[i]
        if comilla == "'":
            if c == "'":
                comilla = None
            else:
                palabra.append(c)
            i += 1
            continue
        if comilla == '"':
            if c == "\\" and escape != "`" and i + 1 < n and texto[i + 1] == '"':
                palabra.append('"')
                i += 2
                continue
            if escape == "\\" and c == "\\" and (texto.startswith("\\", i + 1) or _salto(texto, i + 1)):
                if texto.startswith("\\", i + 1):
                    palabra.append(c)
                i += 1 + (_salto(texto, i + 1) or 1)
                continue
            if escape == "`" and c == "`" and texto[i + 1:i + 2] in ("`", '"', " ", "\t", "\r", "\n"):
                palabra.append(texto[i + 1])
                i += 2
                continue
            if c == '"':
                comilla = None
            elif c == "$" and texto.startswith("$(", i):
                if len(subs) < MAX_SUBS:
                    interior, j = capturar_sustitucion(i + 2)
                    subs.append(interior)
                palabra.append(c)
            elif c == "`":
                j = texto.find("`", i + 1)
                if j > i and len(subs) < MAX_SUBS:
                    subs.append(texto[i + 1:j])
                palabra.append(c)
            else:
                palabra.append(c)
            i += 1
            continue
        if escape and c == escape and i + 1 < n:
            salto = _salto(texto, i + 1)
            if salto:
                i += 1 + salto
                continue
            if texto[i + 1] == escape or texto[i + 1] in " \t\r\"'":
                palabra.append(texto[i + 1])
                hay_palabra = True
                i += 2
                continue
        apertura = HERE_STRING_APERTURA.match(texto, i) if cuerpos == "`" and c == "@" else None
        if apertura:
            cierre = texto.find("\n" + apertura.group(1) + "@", apertura.end() - 1)
            fin = n if cierre < 0 else cierre
            if apertura.group(1) == '"':
                sustituciones(apertura.end(), fin, False)
            palabra.append(texto[apertura.end():fin])
            hay_palabra = True
            i = n if cierre < 0 else cierre + 3
            continue
        if cuerpos == "\\" and texto.startswith("<<", i):
            k = i + 3 if texto.startswith("<<<", i) else i + 2
            linea = texto.rfind("\n", 0, i) + 1
            aritmetica = texto.rfind("((", linea, i) > texto.rfind("))", linea, i)
            apertura = HEREDOC_APERTURA.match(texto, i) if k == i + 2 and not aritmetica else None
            if apertura:
                fin_linea = texto.find("\n", i)
                crudo = apertura.group(2)
                heredocs.append((HEREDOC_COMILLAS.sub(lambda m: next(g for g in m.groups() if g is not None), crudo),
                                 any(x in crudo for x in "'\"\\"), apertura.group(1) == "-", actual,
                                 bool(HEREDOC_A_SHELL.search(texto, i, n if fin_linea < 0 else fin_linea))))
            palabra.append(texto[i:k])
            hay_palabra = True
            i = k
            continue
        if c in "'\"":
            comilla = c
            hay_palabra = True
            i += 1
            continue
        if c == "$" and texto.startswith("$(", i):
            if len(subs) < MAX_SUBS:
                interior, _ = capturar_sustitucion(i + 2)
                subs.append(interior)
            palabra.append(c)
            hay_palabra = True
            i += 1
            continue
        if c == "`":
            j = texto.find("`", i + 1)
            if j > i and len(subs) < MAX_SUBS:
                subs.append(texto[i + 1:j])
            palabra.append(c)
            hay_palabra = True
            i += 1
            continue
        if c == "#" and not hay_palabra:
            j = texto.find("\n", i)
            i = n if j < 0 else j
            continue
        if c in " \t\r":
            cerrar_palabra()
            i += 1
            continue
        if c in "\n;|()":
            cerrar_segmento()
            i += 1
            if c == "\n" and heredocs:
                i = saltar_heredocs(i)
            continue
        if c == "&" and not texto.startswith("&>", i):
            cerrar_segmento()
            i += 1
            continue
        if c == ">" or c == "&":
            if c == "&":
                i += 1
            if hay_palabra and "".join(palabra).isdigit():
                palabra, hay_palabra = [], False
            else:
                cerrar_palabra()
            i += 1
            while i < n and texto[i] == ">":
                i += 1
            if i < n and texto[i] == "&" and c == ">":
                pendiente = "dup"
                i += 1
            else:
                if i < n and texto[i] == "|":
                    i += 1
                pendiente = "redir"
            continue
        palabra.append(c)
        hay_palabra = True
        i += 1
    cerrar_segmento()
    return segmentos, subs


def _nombre_comando(token):
    base = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for sufijo in (".exe", ".cmd", ".bat", ".ps1"):
        if base.endswith(sufijo):
            return base[:-len(sufijo)]
    return base


_normalizar = rutas.normalizar
_es_relativa = rutas.es_relativa
_caso = rutas.caso
_unidad = rutas.unidad
_ubicar = rutas.ubicar
_absoluta = rutas.absoluta
_antes_del_comodin = rutas.antes_del_comodin


def _variable(nombre):
    if _ZONAS is not None:
        return _ZONAS.variable(nombre)
    return os.environ.get(nombre)


def _expandir(ruta, cwd):
    return rutas.expandir(ruta, cwd, _variable)


def _resolver(ruta, cwd):
    return rutas.resolver(ruta, cwd, _variable)


def _recoger(ruta, cwd):
    r = _normalizar(ruta)
    if r.lower() in NULOS or len(_COLECTOR) >= 100:
        return
    if _es_relativa(r) and cwd:
        r = _normalizar(cwd) + "/" + r
    r = posixpath.normpath(r)
    if r not in _COLECTOR:
        _COLECTOR.append(r)


def _protegida(ruta, cwd):
    if not ruta or ruta.startswith("&"):
        return False
    if _COLECTOR is not None:
        _recoger(ruta, cwd)
        return False
    return _decidir(ruta, cwd)


def _decidir(ruta, cwd):
    if not ruta or ruta.startswith("&") or _ZONAS is None:
        return False
    expandida, prefijo = _expandir(ruta.strip(), cwd)
    if expandida is None:
        carpeta = _ubicar(prefijo, cwd) if prefijo else None
        return carpeta is not None and _ZONAS.carpeta(carpeta)
    r = _ubicar(expandida, cwd)
    if r is None or r.lower() in NULOS:
        return False
    if _ZONAS.archivo(r):
        return True
    prefijo = _antes_del_comodin(expandida)
    carpeta = _ubicar(prefijo, cwd) if prefijo is not None else None
    return carpeta is not None and _ZONAS.carpeta(carpeta)


def _zona(ruta, cwd):
    if not ruta:
        return False
    if _decidir(ruta, cwd):
        return True
    r = _resolver(ruta.rstrip("\\/"), cwd)
    return r is not None and _ZONAS is not None and _ZONAS.carpeta(r)


def _git(rest):
    i, n = 0, len(rest)
    alias = {}
    while i < n:
        t = rest[i]
        if t == "-c" and i + 1 < n:
            clave, _, valor = rest[i + 1].partition("=")
            if clave.lower().startswith("alias."):
                alias[clave[6:].lower()] = valor
        elif t.lower() == "--config-env" and i + 1 < n or t.lower().startswith("--config-env="):
            especificacion = rest[i + 1] if t.lower() == "--config-env" else t.partition("=")[2]
            clave = especificacion.partition("=")[0]
            if clave.lower().startswith("alias."):
                alias[clave[6:].lower()] = None
        if t in GIT_OPCIONES_CON_VALOR or t == "-C":
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            break
    if i >= n:
        return None, None
    sub = rest[i].lower()
    for _ in range(5):
        if sub not in alias:
            break
        if alias[sub] is None:
            return "alias " + sub, None
        valor = alias[sub].strip()
        if valor.startswith("!"):
            return None, valor[1:]
        sub = (valor.split() or [""])[0].lower()
    if sub == "config":
        posicionales = [t for t in rest[i + 1:] if not t.startswith("-")]
        k = next((k for k, t in enumerate(posicionales) if t.lower().startswith("alias.")), None)
        if k is None or k + 1 >= len(posicionales):
            return None, None
        valor = posicionales[k + 1].strip()
        if valor.startswith("!"):
            return None, valor[1:]
        primera = (valor.split() or [""])[0].lower()
        return (primera, None) if primera in GIT_ESCRIBE else (None, None)
    if sub == "branch":
        borra = any(RAMA_BORRA.match(t) or t == "--delete" for t in rest[i + 1:])
        return ("branch", None) if borra else (None, None)
    if sub not in GIT_ESCRIBE:
        return None, None
    if sub in GIT_LECTURA_DE:
        siguientes = [t.lower() for t in rest[i + 1:] if not t.startswith("-")]
        if siguientes and siguientes[0] in GIT_LECTURA_DE[sub]:
            return None, None
    return sub, None


def _posicionales(tokens):
    return [t for t in tokens if not t.startswith("-")]


def _python_escribe(rest, cwd, texto=None):
    codigo = next((rest[k + 1] for k, t in enumerate(rest[:-1]) if t == "-c" or PY_BANDERAS_C.match(t)), None)
    if isinstance(codigo, str):
        return _python_codigo_escribe(codigo, cwd)
    if texto is None or "-m" in rest:
        return None
    return _python_heredoc_escribe(rest, texto, cwd)


def _python_heredoc_escribe(rest, texto, cwd):
    marca = next((k for k, t in enumerate(rest) if HEREDOC_MARCA.match(t)), None)
    if marca is None:
        return None
    delimitador = HEREDOC_MARCA.match(rest[marca]).group(2)
    resto = rest[:marca] + rest[marca + 1:]
    if not delimitador:
        if marca + 1 >= len(rest):
            return None
        delimitador = rest[marca + 1]
        resto = rest[:marca] + rest[marca + 2:]
    if "-" not in resto:
        posicionales = [t for k, t in enumerate(resto) if not t.startswith("-")
                        and not (k > 0 and resto[k - 1] in PY_OPCIONES_CON_VALOR)]
        if posicionales:
            return None
    for cuerpo in _cuerpos_heredoc(texto, delimitador):
        motivo = _python_codigo_escribe(cuerpo, cwd)
        if motivo:
            return motivo
    return None


def _cuerpos_heredoc(texto, delimitador):
    inicio = re.compile(r"<<-?[ \t]*(['\"]?)%s\1(?!\w)" % re.escape(delimitador))
    lineas = texto.split("\n")
    cuerpos, i = [], 0
    while i < len(lineas) and len(cuerpos) < MAX_SUBS:
        if inicio.search(lineas[i]):
            j = i + 1
            while j < len(lineas) and lineas[j].rstrip("\r").lstrip("\t") != delimitador:
                j += 1
            cuerpos.append("\n".join(lineas[i + 1:j]))
            i = j + 1
        else:
            i += 1
    return cuerpos


def _python_codigo_escribe(codigo, cwd):
    if PY_PROCESO.search(codigo) and PY_GIT.search(codigo):
        palabras = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]*", codigo)}
        escritura = sorted(palabras & GIT_ESCRIBE)
        if escritura:
            return "git %s" % escritura[0]
    if PY_ESCRIBE.search(codigo):
        for m in PY_COMILLADO.finditer(codigo):
            if (_COLECTOR is None or re.search(r"[\\/.]", m.group(2))) and _protegida(m.group(2), cwd):
                return m.group(2)
    return None


def _objetivos(rest, opciones_script, quitar_script):
    posicionales, script, i = [], False, 0
    while i < len(rest):
        t = rest[i]
        if t in opciones_script or t.startswith(("--expression", "--file")):
            script = True
            i += 1 if "=" in t else 2
            continue
        if not t.startswith("-"):
            posicionales.append(t)
        i += 1
    if quitar_script and not script and posicionales:
        posicionales = posicionales[1:]
    return posicionales


def _escribe(cmd, rest, cwd, texto=None):
    if cmd in ("sed", "gsed"):
        if not any(SED_EN_SITIO.match(t) or t.startswith("--in-place") for t in rest):
            return None
        objetivos = _objetivos(rest, ("-e", "-f"), True) if _COLECTOR is not None else _posicionales(rest)
        return next((t for t in objetivos if _protegida(t, cwd)), None)
    if cmd == "perl":
        if not any(PERL_EN_SITIO.match(t) for t in rest if t.startswith("-")):
            return None
        objetivos = _objetivos(rest, ("-e", "-E"), False) if _COLECTOR is not None else _posicionales(rest)
        return next((t for t in objetivos if _protegida(t, cwd)), None)
    if PYTHON_RE.fullmatch(cmd):
        return _python_escribe(rest, cwd, texto)
    if cmd in COPIAN_CON_BARRAS:
        posicionales = [t for t in rest if not t.startswith("-") and not OPCION_BARRA.match(t)]
        destino = posicionales[1] if len(posicionales) >= 2 else None
        if destino and (_protegida(destino, cwd) or _zona(destino, cwd)):
            return destino
        return None
    if cmd in ESCRIBEN_TODO:
        objetivos = _posicionales(rest)
        if _COLECTOR is not None and cmd in PRIMER_POSICIONAL:
            objetivos = objetivos[:1]
        return next((t for t in objetivos if _protegida(t, cwd)), None)
    if cmd in COPIAN:
        destino, posicionales, i = None, [], 0
        while i < len(rest):
            t = rest[i]
            if t.lower() in OPCIONES_DESTINO and i + 1 < len(rest):
                destino = rest[i + 1]
                i += 2
                continue
            if not t.startswith("-"):
                posicionales.append(t)
            i += 1
        if destino is None and len(posicionales) >= 2:
            destino = posicionales[-1]
        return destino if destino and _protegida(destino, cwd) else None
    if cmd == "dd":
        return next((t[3:] for t in rest if t.startswith("of=") and _protegida(t[3:], cwd)), None)
    return None


def _comando(tokens):
    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        if ASIGNACION.match(t):
            i += 1
        elif _nombre_comando(t) in ENVOLTORIOS:
            xargs = _nombre_comando(t) == "xargs"
            i += 1
            while i < n and (tokens[i].startswith("-") or ASIGNACION.match(tokens[i]) or tokens[i].isdigit()):
                if xargs and tokens[i] in XARGS_CON_VALOR:
                    i += 1
                i += 1
        else:
            return i, _nombre_comando(t)
    return n, ""


def _argumentos(texto, desde, maximo=2):
    args, actual, profundidad, comilla = [], [], 0, None
    for c in texto[desde:desde + 2000]:
        if comilla:
            actual.append(c)
            if c == comilla:
                comilla = None
        elif c in "'\"":
            comilla = c
            actual.append(c)
        elif c in "([{":
            profundidad += 1
            actual.append(c)
        elif c in ")]}" and profundidad == 0:
            break
        elif c in ")]}":
            profundidad -= 1
            actual.append(c)
        elif c == "," and profundidad == 0:
            args.append("".join(actual))
            actual = []
            if len(args) >= maximo:
                return args
        else:
            actual.append(c)
    args.append("".join(actual))
    return args


def _clr_destino(expresion, cwd, texto=""):
    variable = CLR_VARIABLE.match(expresion)
    if variable:
        asignado = re.search(r"\$" + re.escape(variable.group(1)) + r"\s*=\s*('[^']*'|\"[^\"$`]*\")", texto, re.IGNORECASE)
        if asignado:
            expresion = asignado.group(1)
    literal = CLR_LITERAL.match(expresion)
    if literal:
        ruta = literal.group(1) if literal.group(1) is not None else literal.group(2)
        return ruta if _protegida(ruta, cwd) else None
    if _COLECTOR is not None:
        return None
    literales = [a or b for a, b in CLR_COMILLADO.findall(expresion)]
    if _ZONAS is not None and any(_ZONAS.es_scratch(_resolver(l, None)) for l in literales):
        return None
    candidatos = literales + (["/".join(l.strip("\\/") for l in literales)] if len(literales) > 1 else [])
    if any(_zona(c, cwd) for c in candidatos):
        return expresion.strip()
    return expresion.strip() if cwd and _zona(cwd, None) else None


def _clr(texto, cwd):
    for m in CLR_LLAMADA.finditer(texto):
        args = _argumentos(texto, m.end())
        indice = 1 if m.group(1).lower() in CLR_DESTINO_SEGUNDO else 0
        if indice >= len(args):
            continue
        destino = _clr_destino(args[indice], cwd, texto)
        if destino:
            return "[IO.File]::%s sobre %s" % (m.group(1), destino)
    return None


def _texto_start_process(rest):
    archivo, args, posicionales, i = None, None, [], 0
    while i < len(rest):
        low = rest[i].lower()
        if low.startswith("-"):
            if low in ("-filepath", "-argumentlist", "-args") and i + 1 < len(rest):
                if low == "-filepath":
                    archivo = rest[i + 1]
                else:
                    args = rest[i + 1]
                i += 2
            else:
                i += 2 if low in SP_CON_VALOR and i + 1 < len(rest) else 1
            continue
        posicionales.append(rest[i])
        i += 1
    if archivo is None and posicionales:
        archivo = posicionales.pop(0)
    if args is None and posicionales:
        args = posicionales[0]
    if not archivo:
        return None
    if " " in archivo:
        archivo = '"' + archivo + '"'
    return archivo + " " + (args or "").replace(",", " ")


def _lote_sin_ruta(cmd, rest):
    if cmd in ("sed", "gsed"):
        return any(SED_EN_SITIO.match(t) or t.startswith("--in-place") for t in rest)
    if cmd == "perl":
        return any(PERL_EN_SITIO.match(t) for t in rest if t.startswith("-"))
    if cmd in COPIAN_CON_BARRAS:
        return False
    if cmd in COPIAN:
        destino, posicionales, i = None, [], 0
        while i < len(rest):
            if rest[i].lower() in OPCIONES_DESTINO and i + 1 < len(rest):
                destino = rest[i + 1]
                i += 2
                continue
            if not rest[i].startswith("-"):
                posicionales.append(rest[i])
            i += 1
        if destino is None and len(posicionales) >= 2:
            destino = posicionales[-1]
        return destino is None or "{" in destino
    return cmd in ESCRIBEN_TODO


def _en_lote(cmd, rest, cwd, zona, rotulo):
    ruta = _escribe(cmd, rest, cwd)
    if ruta:
        return "%s sobre %s" % (cmd, ruta)
    if _COLECTOR is None and _lote_sin_ruta(cmd, rest) and zona():
        return "%s %s en una zona protegida" % (rotulo, cmd)
    return None


def _comando_suelto(tokens, estado, profundidad, zona, rotulo):
    i, cmd = _comando(tokens)
    rest = tokens[i + 1:]
    if cmd == "git":
        sub, texto_shell = _git(rest)
        if sub:
            return "git %s" % sub
        return _analizar(texto_shell, estado, profundidad + 1, ESCAPE_DE_SHELL["sh"]) if texto_shell else None
    if cmd in SHELLS:
        while rest and rest[0].startswith("-"):
            rest = rest[1:]
        return _analizar(" ".join(rest), estado, profundidad + 1, ESCAPE_DE_SHELL.get(cmd))
    return _en_lote(cmd, rest, estado["cwd"], zona, rotulo)


def _find(rest, estado, profundidad):
    cwd = estado["cwd"]
    i = 0
    while i < len(rest) and rest[i].lower() in FIND_OPCIONES_INICIO:
        i += 1
    raices = []
    while i < len(rest) and not rest[i].startswith("-"):
        raices.append(rest[i])
        i += 1
    resto = rest[i:]
    cache = []

    def zona():
        if not cache:
            cache.append(any(_zona(r, cwd) for r in raices) if raices else bool(cwd and _zona(cwd, None)))
        return cache[0]

    if "-delete" in resto and _COLECTOR is None and zona():
        return "find -delete en una zona protegida"
    k = 0
    while k < len(resto):
        if resto[k].lower() in FIND_EXEC:
            j, sub = k + 1, []
            while j < len(resto) and resto[j] not in FIND_FIN_EXEC:
                sub.append(resto[j])
                j += 1
            motivo = _comando_suelto(sub, estado, profundidad, zona, "find -exec")
            if motivo:
                return motivo
            k = j
        k += 1
    return None


def _zona_del_comando(segmentos, cwd):
    if cwd and _zona(cwd, None):
        return True
    for seg in segmentos:
        for t in seg["tokens"]:
            if t and not t.startswith("-") and ("/" in t or "\\" in t) and _zona(t, cwd):
                return True
    return False


def _graves_fuera_de_simples(texto):
    return COMILLAS_PS.sub(lambda m: m.group(0) if m.group(0)[0] == "'" else GRAVE_ESCAPADO.sub(r"\1", m.group(0)), texto)


def _analizar(texto, estado, profundidad, escape):
    if profundidad > PROFUNDIDAD_MAX:
        return None
    _vigente()
    parar = _COLECTOR is None
    leer = escape if _UNIR and escape and ESCAPE_QUE_CAMBIA[escape].search(texto) else None
    motivo = _clr(_graves_fuera_de_simples(texto) if leer == "`" else texto, estado["cwd"])
    if motivo and parar:
        return motivo
    segmentos, subs = _segmentar(texto, leer, escape if _CUERPOS else None)
    cache = []

    def zona():
        if not cache:
            cache.append(_zona_del_comando(segmentos, estado["cwd"]))
        return cache[0]

    for seg in segmentos:
        for destino in seg["redirs"]:
            if _protegida(destino, estado["cwd"]) and parar:
                return "redirección (>) a %s" % destino
        i, cmd = _comando(seg["tokens"])
        rest = seg["tokens"][i + 1:]
        lote = any(_nombre_comando(t) == "xargs" for t in seg["tokens"][:i])
        motivo = None
        if cmd == "git":
            sub, texto_shell = _git(rest)
            if sub:
                motivo = "git %s" % sub
            elif texto_shell:
                motivo = _analizar(texto_shell, estado, profundidad + 1, ESCAPE_DE_SHELL["sh"])
        elif cmd in SHELLS:
            while rest and (rest[0].startswith("-") or (cmd == "cmd" and rest[0].startswith("/"))):
                rest = rest[1:]
            motivo = _analizar(" ".join(rest), estado, profundidad + 1, ESCAPE_DE_SHELL.get(cmd))
        elif cmd in CAMBIAR_DIR:
            destino = next((t for t in rest if not t.startswith("-")), None)
            estado["cwd"] = _resolver(destino, estado["cwd"]) if destino else None
        elif cmd in ("iex", "invoke-expression"):
            motivo = _analizar(" ".join(t for t in rest if not t.startswith("-")), estado, profundidad + 1,
                               ESCAPE_DE_SHELL["powershell"])
        elif cmd in ("start-process", "saps"):
            texto_sp = _texto_start_process(rest)
            motivo = _analizar(texto_sp, estado, profundidad + 1, None) if texto_sp else None
        elif cmd == "find":
            motivo = _find(rest, estado, profundidad)
        elif lote:
            motivo = _en_lote(cmd, rest, estado["cwd"], zona, "xargs")
        else:
            ruta = _escribe(cmd, rest, estado["cwd"], texto)
            motivo = "%s sobre %s" % (cmd, ruta) if ruta else None
        if motivo and parar:
            return motivo
    for sub in subs:
        motivo = _analizar(sub, estado, profundidad + 1, escape)
        if motivo and parar:
            return motivo
    return None


def _escape(herramienta):
    return ESCAPE_DE_SHELL["powershell"] if herramienta == "PowerShell" else ESCAPE_DE_SHELL["bash"]


def _pasadas(comando, cwd, herramienta):
    global _UNIR, _CUERPOS
    previo = _UNIR, _CUERPOS
    try:
        motivo = None
        for _UNIR, _CUERPOS, dispara in ((False, False, None), (True, False, ESCAPE_ALGUNO), (True, True, CUERPO_ALGUNO)):
            if dispara is None or dispara.search(comando):
                motivo = _analizar(comando, {"cwd": cwd}, 0, _escape(herramienta))
                if motivo and _COLECTOR is None:
                    return motivo
        return motivo
    finally:
        _UNIR, _CUERPOS = previo


def analizar(comando, cwd=None, zonas=None, herramienta=None):
    global _ZONAS
    previo = _ZONAS
    _ZONAS = zonas
    try:
        return _pasadas(comando, cwd, herramienta)
    finally:
        _ZONAS = previo


def destinos(comando, cwd=None, herramienta=None):
    global _COLECTOR
    if not isinstance(comando, str) or not comando.strip():
        return []
    previo = _COLECTOR
    _COLECTOR = []
    try:
        _pasadas(comando, cwd if isinstance(cwd, str) else None, herramienta)
        return list(_COLECTOR)
    finally:
        _COLECTOR = previo


def _mensaje(motivo):
    if motivo.startswith("git "):
        que = ("`%s`: los writers no commitean, no cambian de rama ni tocan el índice; eso lo decide el orquestador o el "
               "usuario. Deja el árbol como está y reporta los archivos en el bloque `## Resultado`." % motivo)
    else:
        que = ("%s: una escritura por shell esquiva a verificar_capa en los archivos de capa y en los repos declarados en "
               "workspace.config.json." % motivo)
    return "writer-guard bloqueó el comando. %s Para cambiar código usa Edit o Write." % que


def clave_foto(ruta):
    return hashlib.sha1(os.path.normcase(os.path.abspath(ruta)).encode("utf-8")).hexdigest()


def carpeta_fotos(raiz, sesion, agente):
    return os.path.join(raiz, convencion.ESTADO_WRITERS, sesion, agente + ".fotos")


def _podar_sesiones_viejas(base, actual):
    try:
        _verificar_capa()._podar(base, actual)
    except (Exception, SystemExit):
        return


def tomar_foto(evento, raiz):
    try:
        sesion, agente = evento.get("session_id"), evento.get("agent_id")
        entrada = evento.get("tool_input")
        ruta = entrada.get("file_path") if isinstance(entrada, dict) else None
        if not (id_valido(sesion) and id_valido(agente)):
            return
        if not isinstance(ruta, str) or not ruta:
            return
        cwd = evento.get("cwd")
        if not os.path.isabs(ruta) and isinstance(cwd, str):
            ruta = os.path.join(cwd, ruta)
        carpeta = carpeta_fotos(raiz, sesion, agente)
        clave = clave_foto(ruta)
        foto, nuevo = os.path.join(carpeta, clave + ".foto"), os.path.join(carpeta, clave + ".nuevo")
        if os.path.exists(foto) or os.path.exists(nuevo):
            return
        sesion_nueva = not os.path.isdir(os.path.dirname(carpeta))
        os.makedirs(carpeta, exist_ok=True)
        if sesion_nueva:
            _podar_sesiones_viejas(os.path.dirname(os.path.dirname(carpeta)), sesion)
        if os.path.isfile(ruta):
            if os.path.getsize(ruta) > MAX_FOTO:
                return
            with open(ruta, "rb") as f:
                contenido = f.read()
            try:
                with open(foto, "xb") as f:
                    f.write(contenido)
            except FileExistsError:
                return
            except BaseException:
                try:
                    os.remove(foto)
                except OSError:
                    pass
                raise
        else:
            with open(nuevo, "x", encoding="utf-8") as f:
                f.write(os.path.abspath(ruta))
    except (Exception, SystemExit):
        return


def correr(evento, raiz=None, plazo=PLAZO_POR_DEFECTO):
    global _LIMITE
    try:
        if isinstance(evento, (str, bytes, bytearray)):
            evento = json.loads(evento)
        if not isinstance(evento, dict) or not convencion.es_writer(evento.get("agent_type")):
            return SILENCIO
        if evento.get("hook_event_name", "PreToolUse") != "PreToolUse":
            return SILENCIO
        herramienta = evento.get("tool_name")
        if herramienta not in HERRAMIENTAS_DE_ESCRITURA and herramienta not in ("Bash", "PowerShell"):
            return SILENCIO
        _LIMITE = time.monotonic() + plazo
        if raiz is None:
            raiz = raiz_de_instancia(os.environ, evento.get("cwd") or os.getcwd())
        if raiz is None:
            return SILENCIO
        estado = config_loader.estado(raiz)
        if estado.tipo != "ok":
            return SILENCIO
        if herramienta in HERRAMIENTAS_DE_ESCRITURA:
            tomar_foto(evento, estado.config["raiz"])
            return SILENCIO
        comando = (evento.get("tool_input") or {}).get("command")
        if not isinstance(comando, str) or not comando.strip():
            return SILENCIO
        cwd = evento.get("cwd")
        motivo = analizar(comando, cwd if isinstance(cwd, str) else None, Zonas(estado.config), herramienta)
        if not motivo:
            return SILENCIO
        return 2, "", (_mensaje(motivo) + "\n").encode("utf-8")
    except (Exception, SystemExit):
        return SILENCIO
    finally:
        _LIMITE = None


def main():
    plazo = plazo_de(sys.argv[1:])
    return correr_hook(lambda crudo: correr(ENTRADA if ENTRADA is not None else crudo, plazo=plazo))


if __name__ == "__main__":
    sys.exit(main())
