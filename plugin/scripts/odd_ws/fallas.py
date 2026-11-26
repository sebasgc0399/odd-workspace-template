import json
import os
import re
import time
import uuid

from odd_ws import archivos, capas

TOPE = 20
TOPE_DEL_MENSAJE = 200
LINEAS_DEL_AVISO = 5
EVENTO_RE = re.compile(r"[A-Za-z_]{1,64}")
ID_RE = re.compile(r"[0-9a-f]{12}")
TEXTOS = ("momento", "hook", "tipo", "mensaje")
AVISO = ("odd-ws: desde el último aviso hubo %d %s de los hooks. Un hook que falla deja pasar lo que le tocaba revisar, así que "
         "eso quedó sin chequeo:")
CIERRE = "Cuéntaselo al usuario: el detalle sale en /odd-ws:doctor, en el ítem hooks-fallas."


def _ruta(raiz, relativa):
    return os.path.join(str(raiz), *relativa.split("/"))


def _payload(crudo):
    if isinstance(crudo, (str, bytes, bytearray)):
        try:
            crudo = json.loads(crudo)
        except ValueError:
            return {}
    return crudo if isinstance(crudo, dict) else {}


def _evento(payload):
    nombre = payload.get("hook_event_name", payload.get("type"))
    return nombre if isinstance(nombre, str) and EVENTO_RE.fullmatch(nombre) else None


def _cwd(payload):
    contexto = payload.get("ctx")
    cwd = payload.get("cwd", contexto.get("cwd") if isinstance(contexto, dict) else None)
    return cwd if isinstance(cwd, str) and cwd else None


def _raiz(inicio, entorno, payload):
    import config_loader
    from odd_ws.comun import raiz_de_instancia

    if inicio is not None:
        return config_loader.encontrar_raiz(inicio)
    return raiz_de_instancia(os.environ if entorno is None else entorno, _cwd(payload) or os.getcwd())


def _mensaje(error):
    texto = " ".join(str(error).split())
    return texto if len(texto) <= TOPE_DEL_MENSAJE else texto[:TOPE_DEL_MENSAJE] + "..."


def _agregar(raiz, entrada):
    ruta = _ruta(raiz, capas.FALLAS_DE_HOOKS)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    descriptor = os.open(ruta, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        os.write(descriptor, (json.dumps(entrada, ensure_ascii=True) + "\n").encode("ascii"))
    finally:
        os.close(descriptor)
    with open(ruta, "rb") as archivo:
        lineas = archivo.read().splitlines(keepends=True)
    if len(lineas) > TOPE:
        archivos.reemplazar(ruta, b"".join(lineas[-TOPE:]))


def anotar(hook, crudo, error, inicio=None, entorno=None):
    try:
        payload = _payload(crudo)
        raiz = _raiz(inicio, entorno, payload)
        if raiz is not None:
            _agregar(raiz, {"id": uuid.uuid4().hex[:12], "momento": time.strftime("%Y-%m-%dT%H:%M:%S"), "hook": hook,
                            "evento": _evento(payload), "tipo": type(error).__name__, "mensaje": _mensaje(error)})
    except (Exception, SystemExit):
        pass


def _valida(entrada):
    if not isinstance(entrada, dict) or not all(isinstance(entrada.get(campo), str) for campo in TEXTOS):
        return False
    identidad, evento = entrada.get("id"), entrada.get("evento")
    return isinstance(identidad, str) and ID_RE.fullmatch(identidad) is not None and (evento is None or isinstance(evento, str))


def leer(raiz):
    try:
        with open(_ruta(raiz, capas.FALLAS_DE_HOOKS), "rb") as archivo:
            crudo = archivo.read()
    except FileNotFoundError:
        return []
    except OSError:
        return None
    entradas = []
    for linea_cruda in crudo.splitlines():
        try:
            entrada = json.loads(linea_cruda.decode("utf-8"))
        except ValueError:
            continue
        if _valida(entrada):
            entradas.append(entrada)
    return entradas


def linea(entrada):
    error = entrada["tipo"] + (": " + entrada["mensaje"] if entrada["mensaje"] else "")
    return "%s %s (%s): %s" % (entrada["momento"], entrada["hook"], entrada.get("evento") or "sin evento", error)


def _vista(raiz):
    try:
        with open(_ruta(raiz, capas.FALLAS_VISTAS), "rb") as archivo:
            return archivo.read().decode("ascii").strip()
    except (OSError, ValueError):
        return None


def _texto(nuevas):
    mostradas = nuevas[-LINEAS_DEL_AVISO:]
    partes = [AVISO % (len(nuevas), "falla" if len(nuevas) == 1 else "fallas")]
    partes += ["- " + linea(entrada) for entrada in mostradas]
    if len(nuevas) > len(mostradas):
        partes.append("- y %d más antiguas" % (len(nuevas) - len(mostradas)))
    partes.append(CIERRE)
    return "\n".join(partes)


def aviso_de_inicio(raiz):
    try:
        entradas = leer(raiz) or []
        ids = [entrada["id"] for entrada in entradas]
        vista = _vista(raiz)
        nuevas = entradas[ids.index(vista) + 1:] if vista in ids else entradas
        if not nuevas:
            return None
        try:
            archivos.reemplazar(_ruta(raiz, capas.FALLAS_VISTAS), nuevas[-1]["id"].encode("ascii"))
        except OSError:
            pass
        return _texto(nuevas)
    except Exception:
        return None


def vaciar(raiz):
    for relativa in (capas.FALLAS_DE_HOOKS, capas.FALLAS_VISTAS):
        try:
            os.remove(_ruta(raiz, relativa))
        except FileNotFoundError:
            pass
    return "%s, vacío" % capas.FALLAS_DE_HOOKS
