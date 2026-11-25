import sys

sys.dont_write_bytecode = True

import os
import re

CLAVE_PRIVADA = "PRIVATE_KEY"
BLOQUE_RE = re.compile(r"(-----BEGIN[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----)([\s\S]{1,12000}?)"
                       r"(-----END[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----)")
PATRONES = tuple((nombre, re.compile(patron)) for nombre, patron in (
    ("ANTHROPIC_API_KEY", r"(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_-]{32,}"),
    ("OPENAI_API_KEY", r"(?<![A-Za-z0-9])sk-(?:(?:proj|svcacct|admin)-[A-Za-z0-9_-]{32,}|[A-Za-z0-9]{40,})"),
    ("GITHUB_TOKEN", r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{36,})"),
    ("SLACK_TOKEN", r"(?<![A-Za-z0-9])xox[baprs]-[0-9]+-[A-Za-z0-9-]{10,}"),
    ("GOOGLE_API_KEY", r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])"),
    ("AWS_ACCESS_KEY_ID", r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])"),
    ("STRIPE_KEY", r"(?<![A-Za-z0-9])[sr]k_live_[A-Za-z0-9]{20,}"),
))


def marcador(nombre):
    return "<%s>" % nombre


def _linea_tapada(linea, prefijo):
    contenido, fin = (linea[:-1], "\r") if linea.endswith("\r") else (linea, "")
    conservado = os.path.commonprefix([contenido, prefijo])
    resto = contenido[len(conservado):]
    return conservado + (marcador(CLAVE_PRIVADA) if resto.strip() else resto) + fin


def _cuerpo_tapado(m):
    lineas = m.group(2).split("\n")
    if len(lineas) == 1:
        return marcador(CLAVE_PRIVADA)
    texto = m.string
    prefijo = texto[texto.rfind("\n", 0, m.start()) + 1:m.start()]
    primera = _linea_tapada(lineas[0], "")
    return "\n".join([primera] + [_linea_tapada(linea, prefijo) for linea in lineas[1:]])


def _tapar_bloques(texto):
    cuantos = 0

    def reemplazo(m):
        nonlocal cuantos
        cuerpo = _cuerpo_tapado(m)
        if cuerpo == m.group(2):
            return m.group(0)
        cuantos += 1
        return m.group(1) + cuerpo + m.group(3)

    return BLOQUE_RE.sub(reemplazo, texto), cuantos


def intentar_tapar(texto):
    if not isinstance(texto, str):
        return texto, 0, None
    try:
        tapado, cuantos = _tapar_bloques(texto)
        for nombre, patron in PATRONES:
            tapado, n = patron.subn(marcador(nombre), tapado)
            cuantos += n
    except Exception as exc:
        return texto, 0, exc
    return (tapado, cuantos, None) if cuantos else (texto, 0, None)


def tapar(texto):
    tapado, cuantos, _ = intentar_tapar(texto)
    return tapado, cuantos


def tapar_valores(dato):
    try:
        return _tapar_valores(dato)
    except Exception:
        return dato, 0


def _tapar_valores(dato):
    if isinstance(dato, str):
        return tapar(dato)
    if isinstance(dato, dict):
        copia, cuantos = {}, 0
        for clave, valor in dato.items():
            copia[clave], n = _tapar_valores(valor)
            cuantos += n
        return copia, cuantos
    if isinstance(dato, (list, tuple)):
        pares = [_tapar_valores(valor) for valor in dato]
        return type(dato)(valor for valor, _ in pares), sum(n for _, n in pares)
    return dato, 0
