import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from odd_ws.comun import entorno_git, lineas

RUTA_HELPER = Path(__file__).resolve().with_name("scriptdom.ps1")
TOPE_HELPER = 20
MIN_HELPER = 1.0
INVOCACIONES_HELPER = 0

SIN_TIEMPO = "sin_tiempo"
SIN_HELPER = "sin_helper"
_VENCIDO = "vencido"

RE_FIN_SENTENCIA = re.compile(
    r"\n[ \t\r]*(?:END|SET|IF|DECLARE|RAISERROR|THROW|SELECT|INSERT|UPDATE|EXEC|EXECUTE|RETURN|WHILE|BEGIN)\b", re.I)

BOM = b"\xef\xbb\xbf"
FINES = ("crlf", "lf")

_CACHE = {}
_ESTADO = {"roto": False}


def depurar(texto, literales=False):
    salida = list(texto)
    n, i, profundidad = len(texto), 0, 0
    while i < n:
        c = texto[i]
        if profundidad:
            if texto.startswith("*/", i):
                profundidad -= 1
                salida[i] = salida[i + 1] = " "
                i += 2
                continue
            if texto.startswith("/*", i):
                profundidad += 1
                salida[i] = salida[i + 1] = " "
                i += 2
                continue
            if c not in "\r\n":
                salida[i] = " "
            i += 1
        elif texto.startswith("--", i):
            while i < n and texto[i] not in "\r\n":
                salida[i] = " "
                i += 1
        elif texto.startswith("/*", i):
            profundidad = 1
            salida[i] = salida[i + 1] = " "
            i += 2
        elif c == "'":
            i += 1
            while i < n:
                if texto[i] == "'":
                    if i + 1 < n and texto[i + 1] == "'":
                        if literales:
                            salida[i] = salida[i + 1] = " "
                        i += 2
                        continue
                    break
                if literales and texto[i] not in "\r\n":
                    salida[i] = " "
                i += 1
            i += 1
        else:
            i += 1
    return "".join(salida)


def linea_de(texto, pos):
    return texto.count("\n", 0, pos) + 1


def bloques_catch(depurado):
    bloques, pila = [], []
    for m in re.finditer(r"\b(BEGIN\s+CATCH|END\s+CATCH)\b", depurado, re.I):
        if m.group(1).split()[0].upper() == "BEGIN":
            pila.append(m.start())
        elif pila:
            ini = pila.pop()
            bloques.append((ini, m.end(), linea_de(depurado, ini), linea_de(depurado, m.end())))
    for ini in pila:
        bloques.append((ini, len(depurado), linea_de(depurado, ini), linea_de(depurado, len(depurado))))
    return sorted(bloques)


def argumentos(texto, inicio):
    fin, profundidad, i, n = len(texto), 0, inicio, len(texto)
    while i < n:
        c = texto[i]
        if c == "(":
            profundidad += 1
        elif c == ")":
            profundidad -= 1
        elif c == ";" and profundidad <= 0:
            fin = i
            break
        elif c == "\n" and profundidad <= 0:
            if RE_FIN_SENTENCIA.match(texto, i):
                fin = i
                break
        i += 1
    args, actual, profundidad = [], [], 0
    for c in texto[inicio:fin]:
        if c == "(":
            profundidad += 1
        elif c == ")":
            profundidad -= 1
        if c == "," and profundidad == 0:
            args.append("".join(actual).strip())
            actual = []
        else:
            actual.append(c)
    resto = "".join(actual).strip()
    if resto or args:
        args.append(resto)
    return args


def limpiar_cache():
    _CACHE.clear()
    _ESTADO["roto"] = False


def _huella(ctx):
    return (ctx["ruta"], hashlib.sha1(ctx["bytes"]).hexdigest())


def _entrada_valida(entrada):
    return entrada if isinstance(entrada, dict) and "error" not in entrada else None


def _correr_helper(rutas, timeout):
    global INVOCACIONES_HELPER
    if _ESTADO["roto"] or not RUTA_HELPER.exists() or not rutas:
        return None, SIN_HELPER
    if timeout < MIN_HELPER:
        return None, SIN_TIEMPO
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return None, SIN_HELPER
    tmp = tempfile.mkdtemp(prefix="tsql-scriptdom-")
    try:
        lista, salida = os.path.join(tmp, "lista.txt"), os.path.join(tmp, "salida.json")
        with open(lista, "wb") as f:
            f.write("\n".join(rutas).encode("utf-8"))
        INVOCACIONES_HELPER += 1
        r = subprocess.run(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUTA_HELPER),
             "-Lista", lista, "-Salida", salida],
            capture_output=True, timeout=timeout, env=entorno_git())
        if r.returncode != 0 or not os.path.exists(salida):
            _ESTADO["roto"] = True
            return None, SIN_HELPER
        with open(salida, "rb") as f:
            datos = json.loads(f.read().decode("utf-8"))
        if not datos.get("ok"):
            _ESTADO["roto"] = True
            return None, SIN_HELPER
        return {a["ruta"]: a for a in datos["archivos"]}, None
    except subprocess.TimeoutExpired:
        return None, _VENCIDO
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, AttributeError, TypeError):
        _ESTADO["roto"] = True
        return None, SIN_HELPER
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _resultado(entrada):
    analisis = _entrada_valida(entrada)
    return (analisis, None) if analisis is not None else (None, SIN_HELPER)


def analizar(ctx):
    clave = _huella(ctx)
    if clave in _CACHE:
        return _CACHE[clave]
    timeout = TOPE_HELPER
    if ctx.get("limite") is not None:
        timeout = min(TOPE_HELPER, ctx["limite"] - time.monotonic())
    res, motivo = _correr_helper([ctx["ruta"]], timeout)
    if motivo == _VENCIDO:
        _CACHE[clave] = (None, SIN_TIEMPO)
        return _CACHE[clave]
    if motivo is not None:
        return None, motivo
    _CACHE[clave] = _resultado(res.get(ctx["ruta"]))
    return _CACHE[clave]


def precalcular(ctxs):
    pendientes = {}
    for ctx in ctxs:
        clave = _huella(ctx)
        if clave not in _CACHE:
            pendientes.setdefault(clave, ctx)
    if not pendientes:
        return
    res, motivo = _correr_helper([c["ruta"] for c in pendientes.values()], min(900, 30 + 2 * len(pendientes)))
    if motivo == _VENCIDO:
        for clave in pendientes:
            _CACHE[clave] = (None, SIN_TIEMPO)
        return
    if motivo is not None:
        return
    for clave, ctx in pendientes.items():
        _CACHE[clave] = _resultado(res.get(ctx["ruta"]))


def _agregadas(ctx):
    return {n for n, _ in ctx["agregadas"]}


def sql_dinamico(ctx):
    analisis, _ = analizar(ctx)
    if not analisis:
        return []
    agregadas, texto_por_linea = _agregadas(ctx), dict(lineas(ctx["texto"]))
    res = []
    for d in analisis.get("dinamico", []):
        n = d.get("linea")
        if n in agregadas and n in texto_por_linea:
            res.append((n, texto_por_linea[n].strip()))
    return res


def comentarios_agregados(ctx):
    analisis, _ = analizar(ctx)
    if not analisis:
        return []
    agregadas, texto_por_linea = _agregadas(ctx), dict(lineas(ctx["texto"]))
    res = []
    for c in analisis.get("comentarios", []):
        ini, fin = c.get("linea"), c.get("linea_fin", c.get("linea"))
        dentro = [n for n in range(ini, fin + 1) if n in agregadas]
        if not dentro:
            continue
        n = dentro[0]
        if ini == fin:
            fragmento = c["texto"].strip()
        elif n in texto_por_linea:
            fragmento = texto_por_linea[n].strip()
        else:
            fragmento = c["texto"].strip().split("\n")[0].strip()
        res.append((n, fragmento))
    return res


def problemas_de_bytes(datos, bom=False, fin="crlf"):
    if fin not in FINES:
        raise ValueError("fin debe ser uno de %s, no %r" % (", ".join(FINES), fin))
    problemas = []
    tiene_bom = datos.startswith(BOM)
    if tiene_bom and not bom:
        problemas.append("tiene BOM")
    if bom and not tiene_bom:
        problemas.append("no tiene BOM")
    if fin == "crlf":
        resto = datos.replace(b"\r\n", b"")
        fin_incorrecto = b"\n" in resto or b"\r" in resto
    else:
        fin_incorrecto = b"\r" in datos
    if fin_incorrecto:
        problemas.append("tiene finales de línea que no son %s" % fin.upper())
    try:
        datos.decode("utf-8")
    except UnicodeDecodeError:
        problemas.append("no es UTF-8 válido")
    return problemas
