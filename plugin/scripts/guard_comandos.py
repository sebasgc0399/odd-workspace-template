import sys

sys.dont_write_bytecode = True

import json
import os
import re
import time

import config_loader
from odd_ws.comun import PLAZO_POR_DEFECTO, SILENCIO, correr_hook, plazo_de, raiz_de_instancia, temporal

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


def _capa_1(comando, entorno):
    _vigente()
    m = HEREDOC_ABRE.match(comando)
    alimenta = m is not None and ALIMENTA_SHELL.search(m.group(1)) is not None
    base = comando if alimenta else HEREDOC.sub(" ", comando)
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


def analizar(comando, cwd=None, entorno=None):
    entorno = os.environ if entorno is None else entorno
    if os.name == "nt":
        entorno = {k.upper(): v for k, v in entorno.items()}
    motivo = _capa_1(comando, entorno)
    return ("block", motivo) if motivo else (None, None)


def _mensaje(motivo):
    return "guard-comandos bloqueó el comando: %s. Si la operación es deliberada, que la corra el usuario a mano." % motivo


def correr(evento, entorno=None, plazo=PLAZO_POR_DEFECTO):
    global _LIMITE
    try:
        if isinstance(evento, (str, bytes, bytearray)):
            evento = json.loads(evento)
        if not isinstance(evento, dict) or evento.get("hook_event_name", "PreToolUse") != "PreToolUse":
            return SILENCIO
        entrada = evento.get("tool_input")
        comando = entrada.get("command") if isinstance(entrada, dict) else None
        if not isinstance(comando, str) or not comando.strip():
            return SILENCIO
        _LIMITE = time.monotonic() + plazo
        entorno = os.environ if entorno is None else entorno
        cwd = evento.get("cwd") if isinstance(evento.get("cwd"), str) else None
        if raiz_de_instancia(entorno, cwd or os.getcwd()) is None:
            return SILENCIO
        resultado, motivo = analizar(comando, cwd, entorno)
        if resultado == "block":
            return 2, "", (_mensaje(motivo) + "\n").encode("utf-8")
        return SILENCIO
    except (Exception, SystemExit):
        return SILENCIO
    finally:
        _LIMITE = None


def main():
    plazo = plazo_de(sys.argv[1:])
    return correr_hook(lambda crudo: correr(crudo, plazo=plazo))


if __name__ == "__main__":
    sys.exit(main())
