import sys

sys.dont_write_bytecode = True

import os
import re

CLAVE_PRIVADA = "PRIVATE_KEY"
BLOQUE_RE = re.compile(r"(-----BEGIN[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----)([\s\S]{1,64000}?)"
                       r"(-----END[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----)")
CUERPO_DE_CLAVE_RE = re.compile(r"[A-Za-z0-9+/=]+")
ENCABEZADO_DE_CLAVE_RE = re.compile(r"(?:Proc-Type|DEK-Info|Version|Comment|Hash):")
ESCAPES_RE = re.compile(r"\\[nr]")
RUTA_PERSONAL_RE = re.compile(r"(?<![\w.-])/(?:home|[Uu]sers)/([^\W_][\w.-]*)/"
                              r"|(?<![A-Za-z0-9])[A-Za-z]:[\\/]+(?i:users)[\\/]+([^\W_][\w.-]*)[\\/]+")
CARPETAS_COMUNES = frozenset({"shared", "public", "default"})
MARCAS_DE_DIFF = "+- "
SEPARADORES_DE_DIFF = ("@@", "\\ ")
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


def _sin_fin(linea):
    return (linea[:-1], "\r") if linea.endswith("\r") else (linea, "")


def _prefijo_de(contenido, prefijo):
    if prefijo[:1] and prefijo[0] in MARCAS_DE_DIFF and contenido[:1] in MARCAS_DE_DIFF:
        return contenido[0] + os.path.commonprefix([contenido[1:], prefijo[1:]])
    return os.path.commonprefix([contenido, prefijo])


def _es_de_clave(resto):
    limpio = resto.strip()
    return not limpio or bool(CUERPO_DE_CLAVE_RE.fullmatch(limpio) or ENCABEZADO_DE_CLAVE_RE.match(limpio))


def _linea_tapada(contenido, fin, conservado):
    resto = contenido[len(conservado):]
    if not resto.strip():
        return contenido + fin
    return conservado + resto[:len(resto) - len(resto.lstrip())] + marcador(CLAVE_PRIVADA) + fin


def _cuerpo_tapado(m):
    lineas = m.group(2).split("\n")
    if len(lineas) == 1:
        limpio = ESCAPES_RE.sub("", lineas[0]).strip()
        return marcador(CLAVE_PRIVADA) if CUERPO_DE_CLAVE_RE.fullmatch(limpio) else None
    if lineas[0].strip():
        return None
    texto = m.string
    prefijo = texto[texto.rfind("\n", 0, m.start()) + 1:m.start()]
    salida = [lineas[0]]
    for linea in lineas[1:-1]:
        contenido, fin = _sin_fin(linea)
        if contenido.startswith(SEPARADORES_DE_DIFF):
            salida.append(linea)
            continue
        conservado = _prefijo_de(contenido, prefijo)
        if not _es_de_clave(contenido[len(conservado):]):
            return None
        salida.append(_linea_tapada(contenido, fin, conservado))
    final = lineas[-1]
    if final[len(_prefijo_de(final, prefijo)):].strip():
        return None
    return "\n".join(salida + [final])


def _tapar_bloques(texto):
    cuantos, partes, hecho, desde = 0, [], 0, 0
    while True:
        m = BLOQUE_RE.search(texto, desde)
        if not m:
            break
        cuerpo = _cuerpo_tapado(m)
        if cuerpo is None:
            desde = m.start() + 1
            continue
        if cuerpo != m.group(2):
            partes += [texto[hecho:m.start()], m.group(1), cuerpo, m.group(3)]
            hecho = m.end()
            cuantos += 1
        desde = m.end()
    if not cuantos:
        return texto, 0
    return "".join(partes + [texto[hecho:]]), cuantos


def claves_privadas(texto):
    return _tapar_bloques(texto)[1] if isinstance(texto, str) else 0


def rutas_personales(texto):
    if not isinstance(texto, str):
        return []
    hallazgos, linea, desde = [], 1, 0
    for m in RUTA_PERSONAL_RE.finditer(texto):
        if (m.group(1) or m.group(2)).lower() in CARPETAS_COMUNES:
            continue
        linea += texto.count("\n", desde, m.start())
        desde = m.start()
        hallazgos.append((linea, m.group(0)))
    return hallazgos


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
