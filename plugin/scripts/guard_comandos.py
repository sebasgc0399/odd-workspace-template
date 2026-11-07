import sys

sys.dont_write_bytecode = True

import os
import posixpath
import re
import time

import config_loader
from odd_ws import rutas
from odd_ws.comun import PLAZO_POR_DEFECTO, SILENCIO, correr_hook, plazo_de, raiz_de_instancia, temporal
from odd_ws.eventos import POWERSHELL, Bloquear, Herramienta, Permitir, Preguntar
from odd_ws.hosts import claude_code as anfitrion

HEREDOC_ABRE = re.compile(r"(?s)^(.*?)<<-?\s*['\"]?\w+['\"]?\r?\n")
ALIMENTA_SHELL = re.compile(r"(?i)\b(bash|sh|zsh|pwsh|powershell|python|node)\b[^\n]*$")
HEREDOC = re.compile(r"(?si)<<-?\s*['\"]?(\w+)['\"]?\r?\n.*?\r?\n\s*\1")
DOBLES = re.compile(r'"[^"]*"')
SIMPLES = re.compile(r"'[^']*'")
GIT = re.compile(r"(?i)\bgit\b")
PUSH = re.compile(r"(?i)\bpush\b")
FORCE = re.compile(r"(?i)(^|\s)--force(\s|$)")
FORCE_CORTO = re.compile(r"(?i)(^|\s)-f(\s|$)")
LEASE = re.compile(r"(?i)--force-with-lease")
PUSHES = re.compile(r"(?i)\bgit(?:\.exe)?(?:\s+(?:-C\s+\S+|-c\s+\S+|--git-dir\s+\S+|--work-tree\s+\S+|--namespace\s+\S+|"
                    r"--?[\w-]+(?:=\S+)?))*\s+push\b([^;&|)}\r\n]*)")
CONTINUACION = re.compile(r"[\\`]\r?\n")
REDIRECCION = re.compile(r"(^|\s)\d?[<>]+&?\S*")
PEGADA = re.compile(r"[<>]\S*")
ESPACIOS = re.compile(r"\s+")
LEASE_REF = re.compile(r"(?i)^--force-with-lease=([^:]*)")
PUSH_CON_VALOR = re.compile(r"(?i)^--(push-option|repo|receive-pack|exec|recurse-submodules)$")
CORTA = re.compile(r"^-[^-]")
REFS = re.compile(r"(?i)^refs/")
HEADS = re.compile(r"(?i)^heads/")
RESET = re.compile(r"(?i)\breset\b")
HARD = re.compile(r"(?i)(^|\s)--h(a(r(d)?)?)?(?=[\s;&|)}>]|$)")
CLEAN = re.compile(r"(?i)\bclean\b")
CLEAN_F = re.compile(r"(?i)(^|\s)(-[a-z]*f[a-z]*|--f(o(r(c(e)?)?)?)?)(?=[\s;&|)}>]|$)")
RM = re.compile(r"(?i)(^|\s|;|&)\s*rm\s")
BANDERA_R = re.compile(r"(?i)(^|\s)-[a-z]*r[a-z]*(\s|$)")
BANDERA_F = re.compile(r"(?i)(^|\s)-[a-z]*f[a-z]*(\s|$)")
REMOVE_ITEM = re.compile(r"(?i)(^|\s|;|\|)\s*(Remove-Item|ri|del)\s")
RECURSE = re.compile(r"(?i)-Recurse")
FORCE_PS = re.compile(r"(?i)-Force")
BORRA_PALABRA = re.compile(r"""(?i)(^|[\s;&|(\{`/\\$!=%"'])(rm|remove-item|ri|del|erase|rd|rmdir)(\.exe)?([\s;&|)}"']|$)""")
BORRA_BANDERA = re.compile(r"""(?i)(^|[\s"'])(-[dfirv]*r|--r|(/[a-z](:[^/\s]*)?)*/s)""")
AMBIGUO = re.compile(r"""[\\`]['"]|[@$]['"]""")
PREFIJO_COMANDO = re.compile(r"^[$({!@&`]+")
BARRA = re.compile(r"[\\/]")
EXE = re.compile(r"(?i)\.exe$")
PROHIBIDOS = re.compile(r"[$`%(){}<>\[\]?;|&!]")
TILDE = re.compile(r"^~/(.*)$")
UNIDAD = re.compile(r"^([A-Za-z]):/(.*)$")
GIT_BASH = re.compile(r"^/([A-Za-z])(/(.*))?$")
PUNTOS = re.compile(r"^[. ]+$")
REDIRIGE = re.compile(r"^(\d*|&|\*)>|^<")
REDIRIGE_SOLA = re.compile(r"^(\d*|&|\*)>>?$|^<<?$")
RUTA_PEGADA = re.compile(r"(?i)^-(path|literalpath|pspath|lp):(.*)$")
RUTA_SUELTA = re.compile(r"(?i)^-(path|literalpath|pspath|lp)$")
PS_CON_VALOR = re.compile(r"(?i)^-(filter|include|exclude|credential|stream|erroraction|ea|warningaction|wa|informationaction|infa|"
                          r"errorvariable|ev|warningvariable|wv|outvariable|ov|outbuffer|ob|pipelinevariable|pv|progressaction|"
                          r"proga)$")
CIERRES = re.compile(r"[)}]+$")
SWITCH_S = re.compile(r"(?i)^(/[a-z](:[^/\s]*)?)*/s(/[a-z](:[^/\s]*)?)*$")
RECURSIVA = re.compile(r"(?i)^(-[dfirv]*r[dfirv]*|--r(e(c(u(r(s(i(v(e)?)?)?)?)?)?)?)?|-r(e(c(u(r(s(e)?)?)?)?)?)?(:\$true)?)$")
ABRIDORES = re.compile(r"^[$({`%=!]+$")
ABRE = re.compile(r"^[$({`!@&%]+.")
PEGADO = re.compile(r".[({]([^({]+)$")
ESTILO_CMD = re.compile(r"(?i)^(rd|rmdir|del|erase)$")
ASIGNACION = re.compile(r"^\w+=")
PALABRA_GIT = re.compile(r"(?i)^[$({!@&`]*(?:[^\\/]*[\\/])*git(\.exe)?$")
ENVOLTORIO = re.compile(r"(?i)^[$({!@&`%]*(?:[^\\/]*[\\/])*(sudo|doas|xargs|command|builtin|exec|eval|env|nohup|nice|time|timeout|"
                        r"stdbuf|ionice|watch|winpty|busybox|powershell|pwsh|if|then|else|elif|do|while|until|cmd|foreach-object|"
                        r"foreach|invoke-command|start-job|-exec|-execdir|-ok|-okdir)(\.exe)?$")
BORRAN = ("rm", "remove-item", "ri", "del", "erase", "rd", "rmdir")

GIT_LECTURA = ("status", "log", "diff", "show", "grep", "ls-tree", "ls-files", "ls-remote", "rev-parse", "rev-list",
               "cat-file", "blame", "annotate", "describe", "shortlog", "merge-base", "name-rev", "for-each-ref", "show-ref",
               "show-branch", "check-ignore", "check-attr", "count-objects", "diff-tree", "diff-files", "diff-index",
               "whatchanged", "range-diff", "cherry", "var", "help", "version", "fetch")
GIT_AUTORIZA = ("push", "commit", "merge", "rebase", "cherry-pick", "revert", "tag", "pull", "am", "add")
LARGAS_MALAS = ("--output", "--output-directory", "--open-files-in-pager", "--ext-diff", "--upload-pack", "--exec", "--receive-pack")
LARGAS_FETCH = ("--update-head-ok", "--set-upstream", "--stdin")
LARGAS_LISTA = ("--all", "--remotes", "--verbose", "--list", "--contains", "--no-contains", "--merged", "--no-merged",
                "--show-current", "--points-at", "--sort", "--format", "--color", "--no-color", "--column", "--no-column",
                "--ignore-case", "--abbrev", "--no-abbrev", "--omit-empty", "--quiet")
CONFIG_ESCRIBE = ("--add", "--replace-all", "--unset", "--unset-all", "--rename-section", "--remove-section", "--edit")
GIT_TOKEN = re.compile(r"(?i)^(?:.*[({`])?[$!@&<>]*(?:[^\\/]*[\\/])*git(?:\.exe)?[)}`;]*$")
SHELL = re.compile(r"(?i)^(?:[^\\/]*[\\/])*(bash|sh|zsh|dash|pwsh|powershell|cmd|eval|iex|invoke-expression|wsl|start-process)(\.exe)?$")
GIT_VARIABLE = re.compile(r"(?i)(^|[\s;&|(:])GIT_(CONFIG\w*|EXTERNAL_DIFF|EXEC_PATH|SSH|SSH_COMMAND|ASKPASS|PROXY_COMMAND)\s*=")
HEREDOC_A_SHELL = re.compile(r"(?i)<<-?\s*['\"]?\w+['\"]?[^\r\n]*\|\s*(bash|sh|zsh|pwsh|powershell)\b")
HERE_STRING_ABRE = re.compile(r"@['\"]\r?\n")
HERE_STRING = re.compile(r"(?s)@(['\"])\r?\n(.*?)\r?\n\1@")
HERE_STRING_COMILLAS = re.compile(r"['\"`]")
REDIRIGE_GIT = re.compile(r"^[\d&]?[<>]")
REDIRIGE_GIT_SOLA = re.compile(r"^[\d&]?[<>]+$")
TRAS_REDIRECCION = re.compile(r"[<>].*$")
CIERRES_GIT = re.compile(r"[)}`;]+$")
RUTA_PROPIA = re.compile(r"(?i)^--(git-dir|work-tree)$")
RUTA_PROPIA_PEGADA = re.compile(r"(?i)^--(git-dir|work-tree)=(.*)$")
VERSION = re.compile(r"(?i)^(--version|-v|--help|-h)$")
GLOBAL_INOCUA = re.compile(r"(?i)^(-p|--no-pager|--paginate|--no-optional-locks|--(literal|glob|noglob|icase)-pathspecs|"
                           r"--no-replace-objects)$")
LISTA_ACTIVA = re.compile(r"(?i)^--(list|verbose|contains|no-contains|merged|no-merged|points-at)$")
LISTA_CON_VALOR = re.compile(r"(?i)^--(sort|format|points-at)$")
CORTA_GIT = re.compile(r"^-.")
CONFIG_LEE = re.compile(r"(?i)^--(get|get-all|get-regexp|list)$")
FETCH_CORTA = re.compile(r"^-[^-]*[uP]")
FETCH_PODA = re.compile(r"(?i)^--prune-t")
LARGA = re.compile(r"(?i)^--[^=]+")
GREP_O = re.compile(r"^-[^-]*O")
WORKTREE_B = re.compile(r"^-[^-]*B")
REMOTE_V = re.compile(r"(?i)^(-v|--verbose)$")
OPCION = re.compile(r"^-")
DESCARTA = re.compile(r"(?i)^(restore|clean|reset)$")
CHECKOUT_DESCARTA = re.compile(r"(?i)(^|\s)(--\s+\S|\.(\s|$))")
STASH_DESCARTA = re.compile(r"(?i)^(drop|clear|pop)$")
ABRE_GIT = re.compile(r"[({`]")
ABRE_AL_FINAL = re.compile(r"[({`]$")
ABRIDORES_INICIO = re.compile(r"^[({`]+")
VARIABLE_SOLA = re.compile(r"^\$\{?[\w:]+\}?$")
SUSTITUCION = re.compile(r"^\$(\{?[\w:]+\}?|\(.*\))$")
OPERADOR = re.compile(r"^([-=.\[<>]|[+*/%?]+=)")
ALIAS = re.compile(r"(?i)^(set-alias|new-alias|sal|nal|alias|doskey)$")
MENCIONA_GIT = re.compile(r"(?i)git")
CODIGO = re.compile(r"\$\(|`")
ESPACIO = re.compile(r"\s")
SEPARA = re.compile(r"[\s;|&]")
MENCION_ABRE = re.compile(r"^(?:\$\(|[({`!@&]|\d*[<>]+&?)+")
MENCION_CIERRA = re.compile(r"[)}`;]+$")
OPCION_PEGADA = re.compile(r"^-[A-Za-z][\w-]*:(.+)$", re.DOTALL)
SOLO_BARRAS = re.compile(r"^[\\/]+$")
DELIMITA = re.compile(r"[=,]")
ESCAPE_FINAL = re.compile(r"(?<!\\)\\$")
SHELL_UNE = re.compile(r"(?i)^(?:[^\\/]*[\\/])*(bash|sh|zsh|dash|wsl|eval)(\.exe)?$")
PREFIJO_LARGO = re.compile(r"^//(?:[?.]/)?(?=[a-z]:/)", re.IGNORECASE)
NO_ES_RUTA = re.compile(r"[\x00\r\n]")
MAX_RUTA = 4096
MAX_PROFUNDIDAD_MENCION = 3
ROTA = object()

_LIMITE = None


class _SinTiempo(Exception):
    pass


def _vigente():
    if _LIMITE is not None and time.monotonic() > _LIMITE:
        raise _SinTiempo()


class Segmentos:
    def __init__(self, texto):
        self.segmentos = []
        self.ambiguo = AMBIGUO.search(texto) is not None
        self._tokens, self._actual = [], []
        self._en_token = self._citado = self._tras_tubo = False
        self._leer(texto)

    def _token(self):
        if self._en_token:
            self._tokens.append(("".join(self._actual), self._citado))
        self._actual = []
        self._en_token = self._citado = False

    def _cerrar(self, tubo):
        _vigente()
        self._token()
        if self._tokens:
            self.segmentos.append((self._tokens, self._tras_tubo))
            self._tokens = []
            self._tras_tubo = tubo
        else:
            self._tras_tubo = self._tras_tubo or tubo

    def _leer(self, texto):
        comilla, i, n = None, 0, len(texto)
        while i < n:
            c = texto[i]
            sig = texto[i + 1] if i + 1 < n else ""
            if comilla:
                if c == comilla:
                    comilla = None
                else:
                    self._actual.append(c)
                i += 1
            elif c in "'\"":
                comilla, self._en_token, self._citado = c, True, True
                i += 1
            elif c in "\\`" and sig in ("\n", "\r"):
                self._token()
                i += 2
                if sig == "\r" and i < n and texto[i] == "\n":
                    i += 1
            elif c in "\\`" and sig and sig in ";|&":
                self._actual += [c, sig]
                self._en_token = True
                i += 2
            elif c in " \t":
                self._token()
                i += 1
            elif c in ";\n\r":
                self._cerrar(False)
                i += 1
            elif c == "|":
                self._cerrar(sig != "|")
                i += 2 if sig == "|" else 1
            elif c == "&":
                previo = texto[i - 1] if i > 0 else ""
                if previo == ">" or sig == ">":
                    self._actual.append(c)
                    self._en_token = True
                    i += 1
                else:
                    self._cerrar(False)
                    i += 2 if sig == "&" else 1
            else:
                self._actual.append(c)
                self._en_token = True
                i += 1
        if comilla:
            self.ambiguo = True
        self._cerrar(False)


def _palabra(token):
    return EXE.sub("", BARRA.split(PREFIJO_COMANDO.sub("", token))[-1])


def _es_comando(token, palabras):
    return _palabra(token).lower() in palabras


def _sin_prefijo(ref):
    return HEADS.sub("", REFS.sub("", ref))


def _push(argumentos):
    limpio = PEGADA.sub("", REDIRECCION.sub(" ", argumentos))
    tokens = [t for t in ESPACIOS.split(limpio) if t]
    posicionales, forzado, lease, cubiertas = [], False, False, []
    k = 0
    while k < len(tokens):
        t = tokens[k]
        k += 1
        bajo = t.lower()
        if bajo == "--force-with-lease":
            lease = True
            continue
        m = LEASE_REF.match(t)
        if m:
            cubiertas.append(_sin_prefijo(m.group(1)))
            continue
        if bajo == "--no-force-with-lease":
            lease = False
            cubiertas.clear()
            continue
        if bajo == "--force":
            forzado = True
            continue
        if PUSH_CON_VALOR.match(t):
            k += 1
            continue
        if CORTA.match(t):
            o = t.find("o", 1)
            letras = t[1:o] if o >= 1 else t[1:]
            if "f" in letras.lower():
                forzado = True
            if o == len(t) - 1:
                k += 1
            continue
        if t.startswith("-"):
            continue
        posicionales.append(t)
    return posicionales, forzado, lease, cubiertas


def _push_forzado(texto):
    for m in PUSHES.finditer(CONTINUACION.sub(" ", texto)):
        _vigente()
        posicionales, forzado, lease, cubiertas = _push(m.group(1))
        if forzado:
            return "git push --force/-f (anula también el --force-with-lease del mismo push: usa --force-with-lease solo)"
        if lease:
            continue
        for ref in posicionales[1:]:
            if not ref.startswith("+"):
                continue
            ref = ref.lstrip("+")
            c = ref.find(":")
            if c >= 0 and ref[c + 1:] != "":
                ref = ref[c + 1:]
            elif c >= 0:
                ref = ref[:c]
            if _sin_prefijo(ref) not in cubiertas:
                return 'git push con un refspec "+" sin un --force-with-lease sobre esa misma ref (es un push forzado)'
    return None


def _bajo_scratch(pieza, scratch, casa):
    if PROHIBIDOS.search(pieza):
        return False
    ruta = pieza.replace("\\", "/")
    m = TILDE.match(ruta)
    if m:
        if not casa:
            return False
        ruta = casa.replace("\\", "/").rstrip("/") + "/" + m.group(1)
    m = UNIDAD.match(ruta)
    if m:
        unidad, resto = m.group(1), m.group(2)
    else:
        m = GIT_BASH.match(ruta)
        if not m:
            return False
        unidad, resto = m.group(1), m.group(3) or ""
    pila = []
    for parte in resto.split("/"):
        if parte in ("", "."):
            continue
        if parte == "..":
            if pila:
                pila.pop()
            continue
        if PUNTOS.match(parte) or (parte.startswith(".") and "*" in parte):
            return False
        pila.append(parte)
    destino = config_loader.canonica(unidad + ":/" + "/".join(pila))
    return destino != scratch and config_loader._dentro(destino, scratch)


def _solo_scratch(segmentos, palabras, scratch, casa):
    if segmentos.ambiguo or scratch is None:
        return False
    hallado = False
    for tokens, tras_tubo in segmentos.segmentos:
        indice = next((k for k, (t, _) in enumerate(tokens) if _es_comando(t, palabras)), -1)
        if indice < 0:
            continue
        hallado = True
        if indice != 0 or tras_tubo:
            return False
        destinos, fin_de_opciones, k = 0, False, 1
        while k < len(tokens):
            t, citado = tokens[k]
            if not citado and REDIRIGE.match(t):
                k += 2 if REDIRIGE_SOLA.match(t) else 1
                continue
            valor = None
            if not fin_de_opciones and t.startswith("-"):
                m = RUTA_PEGADA.match(t)
                if t == "--":
                    fin_de_opciones = True
                    k += 1
                    continue
                if m:
                    valor = m.group(2)
                    k += 1
                elif RUTA_SUELTA.match(t):
                    valor = tokens[k + 1][0] if k + 1 < len(tokens) else None
                    k += 2
                elif PS_CON_VALOR.match(t):
                    k += 2
                    continue
                else:
                    k += 1
                    continue
            else:
                valor = t
                k += 1
            if valor is None:
                continue
            for pieza in valor.split(","):
                if pieza == "":
                    continue
                if not _bajo_scratch(pieza, scratch, casa):
                    return False
                destinos += 1
        if destinos == 0:
            return False
    return hallado


def _recursiva(token, estilo_cmd):
    token = CIERRES.sub("", token)
    if estilo_cmd and SWITCH_S.match(token):
        return True
    return RECURSIVA.match(token) is not None


def _borrado_recursivo(segmentos):
    for tokens, tras_tubo in segmentos.segmentos:
        _vigente()
        posicion, envuelto = True, False
        for k, (t, citado) in enumerate(tokens):
            suelto = not citado
            if suelto and ABRIDORES.match(t):
                posicion = True
                continue
            if suelto and posicion and t == ".":
                continue
            abre = suelto and ABRE.match(t) is not None
            candidato = t[1:] if t.startswith("%") else t
            m = PEGADO.search(t) if suelto else None
            if m:
                candidato, abre = m.group(1), True
            if (posicion or abre or envuelto) and _es_comando(candidato, BORRAN):
                estilo = ESTILO_CMD.match(_palabra(candidato)) is not None
                if any(_recursiva(tokens[j][0], estilo) for j in range(k + 1, len(tokens))):
                    return True
                if tras_tubo and any(_recursiva(u, estilo) for toks, _ in segmentos.segmentos for u, _ in toks):
                    return True
            if (posicion or envuelto) and PALABRA_GIT.match(t):
                posicion = envuelto = False
                continue
            if ENVOLTORIO.match(t):
                posicion = envuelto = True
                continue
            if posicion and ASIGNACION.match(t):
                continue
            posicion = False
    return False


def _base(comando):
    m = HEREDOC_ABRE.match(comando)
    alimenta = m is not None and ALIMENTA_SHELL.search(m.group(1)) is not None
    return comando if alimenta else HEREDOC.sub(" ", comando)


def _capa_1(base, entorno):
    _vigente()
    scan = SIMPLES.sub(" ", DOBLES.sub(" ", base))
    if GIT.search(scan) and PUSH.search(scan) and (FORCE.search(scan) or FORCE_CORTO.search(scan)) and not LEASE.search(scan):
        return "git push --force (si de verdad hace falta forzar, usa --force-with-lease)"
    motivo = _push_forzado(SIMPLES.sub(" QARG ", DOBLES.sub(" QARG ", base)))
    if motivo:
        return motivo
    if GIT.search(scan) and RESET.search(scan) and HARD.search(scan):
        return "git reset --hard descarta sin vuelta atrás el trabajo sin commitear"
    if GIT.search(scan) and CLEAN.search(scan) and CLEAN_F.search(scan):
        return "git clean -f borra sin vuelta atrás los archivos sin trackear"
    carpeta = temporal(entorno)
    scratch = config_loader.canonica(os.path.join(carpeta, "claude")) if carpeta else None
    casa = entorno.get("HOME") or entorno.get("USERPROFILE")
    pista = " (solo pasa si todos los destinos son rutas absolutas literales dentro de %s)" % (
        os.path.join(carpeta, "claude").replace("\\", "/") if carpeta else "<temporal>/claude")
    partes = []

    def segmentos():
        if not partes:
            partes.append(Segmentos(base))
        return partes[0]

    def solo_scratch(palabras):
        try:
            return _solo_scratch(segmentos(), palabras, scratch, casa)
        except _SinTiempo:
            raise
        except Exception:
            return False

    if RM.search(scan) and BANDERA_R.search(scan) and BANDERA_F.search(scan) and not solo_scratch(("rm",)):
        return "rm -rf fuera del scratch" + pista
    if REMOVE_ITEM.search(scan) and RECURSE.search(scan) and FORCE_PS.search(scan) and not solo_scratch(("remove-item", "ri", "del")):
        return "Remove-Item -Recurse -Force fuera del scratch" + pista
    if BORRA_PALABRA.search(base) and BORRA_BANDERA.search(base):
        try:
            borra = _borrado_recursivo(segmentos())
        except _SinTiempo:
            raise
        except Exception:
            borra = True
        if borra and not solo_scratch(BORRAN):
            return "borrado recursivo (rm -r, Remove-Item -Recurse, rd /s) fuera del scratch" + pista
    return None


class Protegidos:
    def __init__(self, config=None, rota=None):
        self.rota = rota
        self.arboles = []
        for clave, repo in ((config or {}).get("repos") or {}).items():
            if repo.get("agent_readonly") is True:
                for ruta in [repo["path"], *repo.get("worktrees", [])]:
                    self.arboles.append((config_loader.canonica(ruta), clave))
        self.activa = rota is not None or bool(self.arboles)
        self._carpetas, self._menciones, self._reales = {}, {}, {}

    @classmethod
    def de_instancia(cls, raiz):
        try:
            return cls(config_loader.cargar(raiz))
        except config_loader.ConfigRota as error:
            return cls(None, str(error))
        except Exception as error:
            return cls(None, "%s: %s" % (type(error).__name__, error))

    def _canonica(self, ruta):
        ruta = PREFIJO_LARGO.sub("", ruta)
        if ruta.startswith("//"):
            return os.path.normcase(ruta)
        pendientes, actual = [], ruta
        while actual not in self._reales:
            _vigente()
            padre, nombre = posixpath.split(actual)
            if rutas.UNIDAD_SOLA.fullmatch(padre):
                padre += "/"
            if not nombre or padre == actual or _existe(actual):
                self._reales[actual] = config_loader.canonica(actual)
                break
            pendientes.append((actual, nombre))
            actual = padre
        canonica = self._reales[actual]
        for camino, nombre in reversed(pendientes):
            canonica = os.path.join(canonica, os.path.normcase(nombre))
            self._reales[camino] = canonica
        return self._reales[ruta]

    def _carpeta(self, ruta):
        if ruta is None:
            return None
        if ruta not in self._carpetas:
            _vigente()
            c = self._canonica(ruta)
            self._carpetas[ruta] = next((clave for arbol, clave in self.arboles if _bajo(c, arbol) or _bajo(arbol, c)), None)
        return self._carpetas[ruta]

    def _toca(self, texto, cwd, base, variable):
        if not texto or len(texto) > MAX_RUTA or NO_ES_RUTA.search(texto):
            return None
        expandida, prefijo = rutas.expandir(texto.strip(), cwd, variable)
        if expandida is None:
            return self._carpeta(rutas.ubicar(prefijo, base)) if prefijo else None
        r = rutas.ubicar(expandida, base)
        if r is None:
            return None
        clave = self._carpeta(r)
        if clave is None:
            prefijo = rutas.antes_del_comodin(expandida)
            if prefijo is not None:
                clave = self._carpeta(rutas.ubicar(prefijo, base))
        return clave

    def del_cwd(self, cwd):
        if self.rota is not None:
            return ROTA
        r = rutas.ubicar(cwd, None) if isinstance(cwd, str) and cwd else None
        if r is None:
            return None
        c = self._canonica(r)
        return next((clave for arbol, clave in self.arboles if _bajo(c, arbol)), None)

    def menciona(self, texto, cwd, variable, profundidad=0):
        if self.rota is not None:
            return ROTA
        llave = (texto, cwd, profundidad, variable)
        if llave not in self._menciones:
            self._menciones[llave] = self._mencion(texto, cwd, variable, profundidad)
        return self._menciones[llave]

    def _mencion(self, texto, cwd, variable, profundidad):
        for candidato in _candidatos(texto):
            clave = self._toca(candidato, cwd, cwd, variable)
            if clave is not None:
                return clave
        if profundidad < MAX_PROFUNDIDAD_MENCION and SEPARA.search(texto):
            for vista in _vistas(texto):
                for tokens, _ in vista.segmentos:
                    for t, _ in tokens:
                        _vigente()
                        clave = self.menciona(t, cwd, variable, profundidad + 1)
                        if clave is not None:
                            return clave
        return None

    def compuerta(self, base, segmentos, cwd, variable):
        clave = self.del_cwd(cwd)
        if clave is not None:
            return clave
        for tokens, _ in segmentos.segmentos:
            for t, _ in tokens:
                clave = self.menciona(t, cwd, variable)
                if clave is not None:
                    return clave
        return None

    def propias(self, propias, cwd, variable):
        if self.rota is not None:
            return ROTA, False
        base, clave, absoluta = None, None, False
        for opcion, texto in propias:
            expandida, _ = rutas.expandir(texto.strip(), cwd, variable)
            r = rutas.ubicar(expandida, base) if expandida is not None else None
            if r is not None:
                absoluta = True
            if clave is None:
                clave = self._toca(texto, cwd, base, variable)
            if opcion == "-C":
                base = r
        return clave, absoluta

    def donde(self, clave):
        if clave is ROTA:
            return ("un repo cualquiera, con la configuración de la instancia rota (%s; mientras no se arregle, todo git que no "
                    "sea de lectura pregunta)" % self.rota)
        if clave is not None:
            return "el repo «%s», que el agente solo lee (repos.%s.agent_readonly en workspace.config.json)" % (clave, clave)
        return "una instancia con repos que el agente solo lee (agent_readonly en workspace.config.json)"


def _bajo(ruta, carpeta):
    return ruta == carpeta or ruta.startswith(carpeta if carpeta.endswith(os.sep) else carpeta + os.sep)


def _existe(ruta):
    try:
        os.lstat(ruta)
    except (OSError, ValueError):
        return False
    return True


def _candidatos(texto):
    vistos, salida = set(), []
    for base in (texto, MENCION_CIERRA.sub("", MENCION_ABRE.sub("", texto))):
        piezas = [base] + base.split("=", 1)[1:]
        m = OPCION_PEGADA.match(base)
        if m:
            piezas.append(m.group(1))
        for candidato in [c for pieza in piezas for c in pieza.split(",")] + DELIMITA.split(base):
            _vigente()
            if candidato and candidato not in vistos and (candidato == texto or not SOLO_BARRAS.search(candidato)):
                vistos.add(candidato)
                salida.append(candidato)
    return salida


class _Vista:
    def __init__(self, segmentos, ambiguo):
        self.segmentos, self.ambiguo = segmentos, ambiguo


def _vistas(texto, unir=True):
    segmentos = Segmentos(texto)
    if not unir:
        return [segmentos]
    unidos, cambio = [], False
    for tokens, tubo in segmentos.segmentos:
        nuevos = []
        for t, citado in tokens:
            if nuevos and not nuevos[-1][1] and ESCAPE_FINAL.search(nuevos[-1][0]):
                nuevos[-1] = (nuevos[-1][0][:-1] + " " + t, False)
                cambio = True
            else:
                nuevos.append((t, citado))
        unidos.append((nuevos, tubo))
    return [segmentos, _Vista(unidos, segmentos.ambiguo)] if cambio else [segmentos]


def _pregunta(prot, que, porque, clave):
    return "git %s en %s: %s. Confirmar solo si es deliberado y autorizado." % (que, prot.donde(clave), porque)


def _forma_de_lista(resto, cortas, disparan):
    lista, posicionales, k = False, 0, 0
    while k < len(resto):
        t = resto[k]
        if t == "--":
            posicionales += len(resto) - k - 1
            break
        if t.startswith("--"):
            n = t.split("=", 1)[0]
            if n.lower() not in LARGAS_LISTA:
                return False
            if LISTA_ACTIVA.search(n):
                lista = True
            if LISTA_CON_VALOR.search(n) and "=" not in t:
                k += 1
        elif CORTA_GIT.search(t):
            if not re.search("^-[%s]+$" % cortas, t):
                return False
            if re.search("[%s]" % disparan, t):
                lista = True
        else:
            posicionales += 1
        k += 1
    return posicionales == 0 or lista


def _config_de_lectura(resto):
    lectura = bool(resto) and resto[0] in ("get", "list")
    for t in resto:
        n = t.split("=", 1)[0]
        if CONFIG_LEE.search(n) or n == "-l":
            lectura = True
            continue
        if n == "-e":
            return False
        if n.startswith("--") and len(n) >= 3 and any(w.startswith(n) for w in CONFIG_ESCRIBE):
            return False
    return lectura


def _opcion_mala(sub, resto):
    malas = LARGAS_MALAS + LARGAS_FETCH if sub == "fetch" else LARGAS_MALAS
    for t in resto:
        if t == "--":
            break
        if sub == "fetch" and (":" in t or FETCH_CORTA.search(t) or FETCH_PODA.search(t)):
            return t
        m = LARGA.search(t)
        if m:
            if any(f.lower().startswith(m.group(0).lower()) for f in malas):
                return t
        elif sub == "grep" and GREP_O.search(t):
            return t
    return ""


def _invocacion(tokens, desde, hasta, ambiente, prot, cwd, variable):
    av, k = [], desde
    while k < hasta:
        t, citado = tokens[k]
        k += 1
        if not citado:
            if REDIRIGE_GIT.search(t):
                if REDIRIGE_GIT_SOLA.search(t):
                    k += 1
                continue
            t = CIERRES_GIT.sub("", TRAS_REDIRECCION.sub("", t))
            if t == "":
                continue
        av.append(t)
    propias, mala, sub, i = [], "", "", 0
    while i < len(av):
        t = av[i]
        i += 1
        pegada = RUTA_PROPIA_PEGADA.search(t)
        if t == "-C" or RUTA_PROPIA.search(t):
            if i < len(av):
                propias.append((t, av[i]))
            i += 1
        elif pegada:
            propias.append(("--" + pegada.group(1), pegada.group(2)))
        elif t == "-c" or t.lower() == "--config-env":
            mala = t
            i += 1
        elif VERSION.search(t):
            sub = "version"
            break
        elif GLOBAL_INOCUA.search(t):
            pass
        elif t.startswith("-"):
            mala = t
        else:
            sub = t
            break
    clave, absoluta = prot.propias(propias, cwd, variable)
    if clave is None and (absoluta or ambiente is None):
        return None
    clave = ambiente if clave is None else clave
    if mala:
        return _pregunta(prot, mala, "opción global fuera de la lista (-c, --config-env y --exec-path pueden ejecutar cualquier "
                                     "comando)", clave)
    if not sub:
        return None
    resto = av[i:]
    s = sub.lower()
    a0 = resto[0] if resto else ""
    if s == "branch":
        ok = _forma_de_lista(resto, "arvliq", "vl")
    elif s == "tag":
        ok = _forma_de_lista(resto, "lni0-9", "l")
    elif s == "stash":
        ok = a0 in ("list", "show")
    elif s == "worktree":
        ok = a0 == "list" or (a0 == "add" and not any(WORKTREE_B.search(t) for t in resto))
    elif s == "config":
        ok = _config_de_lectura(resto)
    elif s == "remote":
        r = [t for t in resto if not REMOTE_V.search(t)]
        ok = not r or r[0] in ("show", "get-url")
    elif s == "reflog":
        ok = a0 == "show" or not [t for t in resto if not OPCION.search(t)]
    elif s == "notes":
        ok = a0 in ("", "list", "show")
    else:
        ok = s in GIT_LECTURA
    if ok:
        f = _opcion_mala(s, resto)
        if not f:
            return None
        return _pregunta(prot, "%s %s" % (sub, f), "esa opción escribe o ejecuta", clave)
    porque = "fuera de la lista de git de solo lectura"
    if s in GIT_AUTORIZA:
        porque = "requiere autorización puntual"
    elif (DESCARTA.search(s) or (s == "checkout" and CHECKOUT_DESCARTA.search(" ".join(resto)))
          or (s == "stash" and STASH_DESCARTA.search(a0)) or (s == "worktree" and a0.lower() == "remove")):
        porque = "descarta trabajo sin commitear, sin reflog para recuperarlo"
    elif s in ("checkout", "switch"):
        porque = ("el working tree puede tener trabajo sin commitear; para otra rama, usar un worktree "
                  "(git -C <repo> worktree add <ruta> <rama>)")
    return _pregunta(prot, sub, porque, clave)


def _equipo(segmentos, ambiente, profundidad, texto, clave, prot, cwd, variable, unir):
    if clave is not None and segmentos.ambiguo and MENCIONA_GIT.search(texto):
        return _pregunta(prot, "(comillas escapadas o ambiguas)", "no se puede leer qué git corre",
                         clave if ambiente is None else ambiente)
    datos = []
    for tokens, _ in segmentos.segmentos:
        _vigente()
        inicios, shell, abierto, envuelto, riesgo, une = [], False, False, False, "", unir
        for k, (t, citado) in enumerate(tokens):
            if GIT_TOKEN.search(t) and (not inicios or abierto or (not citado and ABRE_GIT.search(t))):
                inicios.append(k)
            else:
                if ambiente is None and not (citado and inicios and ESPACIO.search(t)):
                    ambiente = prot.menciona(t, cwd, variable)
                if k == 0 or envuelto:
                    tv = ABRIDORES_INICIO.sub("", t) if k == 0 else t
                    siguiente = tokens[k + 1][0] if k + 1 < len(tokens) else ""
                    if ((VARIABLE_SOLA.search(tv) and (envuelto or profundidad > 0))
                            or (SUSTITUCION.search(tv) and siguiente != "" and not OPERADOR.search(siguiente))):
                        riesgo = "(un comando en una variable o una sustitución)"
            if k == 0 and ALIAS.search(t) and any(MENCIONA_GIT.search(x) for x, _ in tokens):
                riesgo = "(un alias hacia git)"
            if not citado and SHELL.search(t):
                shell = True
                une = SHELL_UNE.search(t) is not None
            abierto = not citado and ABRE_AL_FINAL.search(t) is not None
            envuelto = not citado and ENVOLTORIO.search(t) is not None
        datos.append((tokens, inicios, shell, riesgo, une))
    for tokens, inicios, shell, riesgo, une in datos:
        if ambiente is not None and riesgo:
            return _pregunta(prot, riesgo, "no se puede leer si es git ni qué hace", ambiente)
        if profundidad < 2:
            for t, citado in tokens:
                if citado and (shell or CODIGO.search(t)):
                    for vista in _vistas(t, une):
                        motivo = _equipo(vista, ambiente, profundidad + 1, t, clave, prot, cwd, variable, une)
                        if motivo:
                            return motivo
        for i, inicio in enumerate(inicios):
            fin = inicios[i + 1] if i + 1 < len(inicios) else len(tokens)
            motivo = _invocacion(tokens, inicio + 1, fin, ambiente, prot, cwd, variable)
            if motivo:
                return motivo
    return None


def _capa_2(comando, base, cwd, variable, prot, unir):
    texto = comando if HEREDOC_A_SHELL.search(comando) else base
    if HERE_STRING_ABRE.search(texto):
        texto = HERE_STRING.sub(lambda m: '"' + HERE_STRING_COMILLAS.sub(" ", m.group(2)).replace("\\", "/") + '"', texto)
    vistas = _vistas(texto, unir)
    clave = next((c for c in (prot.compuerta(base, vista, cwd, variable) for vista in vistas) if c is not None), None)
    if clave is not None and GIT_VARIABLE.search(base):
        return _pregunta(prot, "(con una variable GIT_* que equivale a -c o nombra un programa)", "puede ejecutar cualquier comando",
                         clave)
    try:
        for vista in vistas:
            motivo = _equipo(vista, prot.del_cwd(cwd), 0, texto, clave, prot, cwd, variable, unir)
            if motivo:
                return motivo
        return None
    except _SinTiempo:
        raise
    except Exception as error:
        return _pregunta(prot, "(el guard falló al leerlo)", "error interno: %s" % error, clave)


def analizar(comando, cwd=None, entorno=None, protegidos=None, herramienta=None):
    entorno = os.environ if entorno is None else entorno
    if os.name == "nt":
        entorno = {k.upper(): v for k, v in entorno.items()}
    base = _base(comando)
    motivo = _capa_1(base, entorno)
    if motivo:
        return "block", motivo
    if protegidos is not None and protegidos.activa:
        variable = (lambda nombre: entorno.get(nombre.upper())) if os.name == "nt" else entorno.get
        motivo = _capa_2(comando, base, cwd, variable, protegidos, herramienta not in ("PowerShell", POWERSHELL))
        if motivo:
            return "ask", motivo
    return None, None


def _mensaje(motivo):
    return "guard-comandos bloqueó el comando: %s. Si la operación es deliberada, que la corra el usuario a mano." % motivo


def _preguntar(motivo):
    return Preguntar("guard-comandos pregunta antes de correr el comando: " + motivo)


def decidir(evento, entorno=None, plazo=PLAZO_POR_DEFECTO):
    global _LIMITE
    protegidos = None
    try:
        if not isinstance(evento, Herramienta) or evento.fase != "pre":
            return Permitir()
        comando = evento.comando
        if not comando or not comando.strip():
            return Permitir()
        _LIMITE = time.monotonic() + plazo
        entorno = os.environ if entorno is None else entorno
        cwd = evento.cwd if isinstance(evento.cwd, str) else None
        raiz = raiz_de_instancia(entorno, cwd or os.getcwd())
        if raiz is None:
            return Permitir()
        protegidos = Protegidos.de_instancia(raiz)
        resultado, motivo = analizar(comando, cwd, entorno, protegidos, evento.dialecto)
        if resultado == "block":
            return Bloquear(_mensaje(motivo))
        if resultado == "ask":
            return _preguntar(motivo)
        return Permitir()
    except _SinTiempo:
        if protegidos is not None and protegidos.activa:
            return _preguntar(_pregunta(protegidos, "(el análisis no terminó dentro del plazo)", "no se puede leer qué git corre",
                                        ROTA if protegidos.rota is not None else None))
        return Permitir()
    except (Exception, SystemExit) as error:
        if protegidos is not None and protegidos.activa:
            return _preguntar(_pregunta(protegidos, "(el guard falló al leerlo)", "error interno: %s" % error,
                                        ROTA if protegidos.rota is not None else None))
        return Permitir()
    finally:
        _LIMITE = None


def correr(evento, entorno=None, plazo=PLAZO_POR_DEFECTO):
    try:
        return anfitrion.atender(evento, lambda leido: decidir(leido, entorno, plazo), pre_por_defecto=True)
    except (Exception, SystemExit):
        return SILENCIO


def main():
    plazo = plazo_de(sys.argv[1:])
    return correr_hook(lambda crudo: correr(crudo, plazo=plazo))


if __name__ == "__main__":
    sys.exit(main())
