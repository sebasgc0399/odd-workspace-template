import ast
import re
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SEGURIDAD = "SECURITY.md"
PARTES = ("## Reportar una vulnerabilidad", "## El modelo de amenaza", "## Lo que sale de tu máquina")
INVENTARIO = PARTES[2]
CARPETAS = ("plugin", "tools")
VERBOS = frozenset({"fetch", "push", "pull", "ls-remote", "clone", "marketplace", "curl", "wget", "gh"})
ESQUEMAS = ("http://", "https://")
MODULOS_DE_RED = ("socket", "http", "requests", "urllib.request", "urllib3", "httpx", "aiohttp", "ftplib", "smtplib", "xmlrpc")
RUTA_DECLARADA_RE = re.compile(r"`((?:plugin|tools)/[^`\s:]+\.py)(?::\d+)?`")
ENLACE_A_DOC_RE = re.compile(r"\]\((Doc/[^)#\s]+\.md)#([^)\s]+)\)")
TITULO_RE = re.compile(r"(?m)^#{1,6} (.+?)\s*$")
EXCEPCIONES = {
    "plugin/scripts/guard_comandos.py": "lee push, pull, fetch y ls-remote como datos, para frenar o preguntar antes de que el "
                                        "agente los corra; no corre ninguno",
    "plugin/scripts/writer_guard.py": "lee push y pull como datos, para bloquear el git de escritura de un writer; no corre ninguno",
}


def fuentes(raiz):
    return sorted(ruta for carpeta in CARPETAS for ruta in (raiz / carpeta).rglob("*.py")
                  if ruta.is_file() and "__pycache__" not in ruta.parts and not ruta.name.endswith(".tests.py"))


def _de_red(modulo):
    return any(modulo == base or modulo.startswith(base + ".") for base in MODULOS_DE_RED)


def indicios(texto, nombre="<fuente>"):
    hallados = set()
    for nodo in ast.walk(ast.parse(texto, nombre)):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (str, bytes)):
            valor = nodo.value.decode("latin-1") if isinstance(nodo.value, bytes) else nodo.value
            if valor.strip().lower() in VERBOS:
                hallados.add((nodo.lineno, valor.strip()))
            hallados.update((nodo.lineno, esquema) for esquema in ESQUEMAS if esquema in valor.lower())
        elif isinstance(nodo, ast.Import):
            hallados.update((nodo.lineno, "import " + alias.name) for alias in nodo.names if _de_red(alias.name))
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
            if any(_de_red(modulo) for modulo in [nodo.module] + ["%s.%s" % (nodo.module, alias.name) for alias in nodo.names]):
                hallados.add((nodo.lineno, "from %s import %s" % (nodo.module, ", ".join(alias.name for alias in nodo.names))))
    return sorted(hallados)


def seccion(texto, titulo):
    texto = "\n" + texto.replace("\r\n", "\n")
    inicio = texto.find("\n" + titulo + "\n")
    if inicio < 0:
        return ""
    fin = texto.find("\n## ", inicio + 1)
    return texto[inicio:fin if fin >= 0 else len(texto)]


def declarados(texto):
    return set(RUTA_DECLARADA_RE.findall(seccion(texto, INVENTARIO)))


def con_red(raiz):
    return {ruta.relative_to(raiz).as_posix(): encontrados for ruta in fuentes(raiz)
            for encontrados in [indicios(ruta.read_text(encoding="utf-8-sig"), str(ruta))] if encontrados}


def sin_declarar(raiz, nombrados, excepciones):
    return ["%s:%d: %s" % (relativa, linea, indicio) for relativa, encontrados in sorted(con_red(raiz).items())
            if relativa not in nombrados and relativa not in excepciones for linea, indicio in encontrados]


def ancla(titulo):
    return re.sub(r"[^\w\- ]", "", titulo.strip().lower()).replace(" ", "-")


def _seguridad():
    return (RAIZ / SEGURIDAD).read_text(encoding="utf-8")


def test_detecta_lo_sembrado_y_no_lo_que_no_sale_a_la_red():
    arbol = {
        "plugin/scripts/sembrado.py": "import subprocess\nsubprocess.run(['git', 'fetch', 'origin'])\n",
        "tools/envoltorio.py": "FETCH = ('-c', 'gc.auto=0', 'fetch')\n\n\ndef _git(*args):\n    return args\n\n\n_git(*FETCH)\n",
        "plugin/scripts/odd_ws/red.py": "import urllib.request\nfrom http import client\nimport socket as s\n",
        "plugin/scripts/url.py": "API = f'https://example.invalid/{1}'\n",
        "plugin/scripts/descarga.py": "import subprocess\nsubprocess.run(['curl', '-s', 'x'])\nsubprocess.run([b'git', b'push'])\n",
        "plugin/scripts/prosa.py": "# git push origin main\nAYUDA = 'corre git push origin main a mano'\nfrom urllib.parse import urlsplit\n"
                                   "from . import http\n",
        "plugin/scripts/sembrado.tests.py": "import subprocess\nsubprocess.run(['git', 'push'])\n",
        "plugin/scripts/declarado.py": "import subprocess\nsubprocess.run(['git', 'clone', 'x'])\n",
        "plugin/scripts/exceptuado.py": "VERBOS = ('push',)\n",
        "otra/fuera.py": "import socket\n",
        SEGURIDAD: "# Seguridad\n\n%s\n\n| `git clone` | `plugin/scripts/declarado.py` |\n\n## Otra\n\n`plugin/scripts/url.py`\n" % INVENTARIO,
    }
    base = Path(tempfile.mkdtemp(prefix="inventario-de-red-"))
    try:
        for relativa, texto in arbol.items():
            (base / relativa).parent.mkdir(parents=True, exist_ok=True)
            (base / relativa).write_text(texto, encoding="utf-8")
        nombrados = declarados((base / SEGURIDAD).read_text(encoding="utf-8"))
        assert nombrados == {"plugin/scripts/declarado.py"}, "solo cuenta lo que está en la sección del inventario: %r" % nombrados
        faltan = sin_declarar(base, nombrados, {"plugin/scripts/exceptuado.py": "lo lee como dato"})
        assert faltan == [
            "plugin/scripts/descarga.py:2: curl", "plugin/scripts/descarga.py:3: push",
            "plugin/scripts/odd_ws/red.py:1: import urllib.request", "plugin/scripts/odd_ws/red.py:2: from http import client",
            "plugin/scripts/odd_ws/red.py:3: import socket",
            "plugin/scripts/sembrado.py:2: fetch",
            "plugin/scripts/url.py:1: https://",
            "tools/envoltorio.py:1: fetch",
        ], faltan
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_el_codigo_que_puede_salir_a_la_red_esta_en_el_inventario_de_security_md():
    faltan = sin_declarar(RAIZ, declarados(_seguridad()), EXCEPCIONES)
    assert not faltan, ("%d llamadas que pueden salir a la red sin estar en «%s» de %s: súmalas al inventario, o a EXCEPCIONES "
                        "con su porqué si leen el verbo como dato:\n  " % (len(faltan), INVENTARIO, SEGURIDAD)) + "\n  ".join(faltan)


def test_cada_excepcion_tiene_su_porque_y_sigue_haciendo_falta():
    con, nombrados = con_red(RAIZ), declarados(_seguridad())
    for relativa, porque in EXCEPCIONES.items():
        assert (RAIZ / relativa).is_file(), "la excepción %s ya no existe: sácala" % relativa
        assert len(porque.split()) >= 5, "la excepción %s necesita su porqué" % relativa
        assert relativa in con, "%s ya no nombra ningún verbo de red: sácala de EXCEPCIONES" % relativa
        assert relativa not in nombrados, "%s está en el inventario y en EXCEPCIONES: va en uno solo" % relativa


def test_security_md_tiene_las_tres_partes_y_lo_que_nombra_existe():
    texto = _seguridad()
    titulos = TITULO_RE.findall(texto)
    assert [titulo for titulo in titulos if "## " + titulo in PARTES] == [parte[3:] for parte in PARTES], titulos
    nombrados = declarados(texto)
    assert nombrados, "el inventario nombra los archivos con su ruta entre comillas invertidas"
    for relativa in sorted(nombrados):
        assert (RAIZ / relativa).is_file(), "%s nombra %s, que no existe" % (SEGURIDAD, relativa)
    enlaces = ENLACE_A_DOC_RE.findall(texto)
    assert ("Doc/diseno.md", "guard-de-comandos-guard_comandospy-l48-l49-l52-l53") in enlaces, "el modelo de amenaza enlaza su fuente"
    for doc, destino in enlaces:
        anclas = {ancla(titulo) for titulo in TITULO_RE.findall((RAIZ / doc).read_text(encoding="utf-8"))}
        assert destino in anclas, "%s enlaza %s#%s, y ese título no existe" % (SEGURIDAD, doc, destino)


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    pruebas = [(nombre, funcion) for nombre, funcion in globals().items() if nombre.startswith("test_") and callable(funcion)]
    fallas = 0
    for nombre, prueba in pruebas:
        try:
            prueba()
            print(f"ok    {nombre}")
        except AssertionError as error:
            fallas += 1
            print(f"FALLA {nombre}: {error}")
        except Exception as error:
            fallas += 1
            print(f"ERROR {nombre}: {type(error).__name__}: {error}")
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
