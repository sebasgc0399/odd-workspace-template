import json
import os
import re
import subprocess
import sys

CEROS = "0" * 40
REF_MAIN = "refs/heads/main"
PATRON_ETIQUETA = "odd-ws--v*"
PREFIJO_ETIQUETA = "odd-ws--v"
PLUGIN_JSON = "plugin/.claude-plugin/plugin.json"
SHA = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
USO = "uso: entrega.py   (lee de stdin las líneas del pre-push)"


class NoSePuedeVerificar(Exception):
    pass


def git(raiz, *args):
    return subprocess.run(["git", "-C", raiz, *args], capture_output=True)


def error_de(resultado):
    return resultado.stderr.decode("utf-8", "replace").strip() or f"salió con {resultado.returncode}"


def raiz_del_repo():
    resultado = subprocess.run(["git", "-C", os.getcwd(), "rev-parse", "--show-toplevel"], capture_output=True)
    if resultado.returncode != 0:
        raise NoSePuedeVerificar("este chequeo necesita correr dentro de un repositorio git: " + error_de(resultado))
    return resultado.stdout.decode("utf-8").strip()


def ultima_etiqueta(raiz, sha):
    resultado = git(raiz, "describe", "--tags", "--match", PATRON_ETIQUETA, "--abbrev=0", sha)
    if resultado.returncode == 0:
        return resultado.stdout.decode("utf-8").strip()
    alcanzables = git(raiz, "tag", "--merged", sha, "--list", PATRON_ETIQUETA)
    if alcanzables.returncode == 0 and not alcanzables.stdout.strip():
        return None
    raise NoSePuedeVerificar(f"git no pudo buscar la última etiqueta {PATRON_ETIQUETA} desde {sha[:7]}: " + error_de(resultado))


def plugin_cambio(raiz, etiqueta, sha):
    resultado = git(raiz, "diff", "--quiet", f"refs/tags/{etiqueta}", sha, "--", "plugin/")
    if resultado.returncode in (0, 1):
        return resultado.returncode == 1
    raise NoSePuedeVerificar(f"git no pudo comparar plugin/ entre {etiqueta} y {sha[:7]}: " + error_de(resultado))


def version_del_plugin(raiz, sha):
    resultado = git(raiz, "show", f"{sha}:{PLUGIN_JSON}")
    if resultado.returncode != 0:
        raise NoSePuedeVerificar(f"git no pudo leer {PLUGIN_JSON} en {sha[:7]}: " + error_de(resultado))
    try:
        datos = json.loads(resultado.stdout.decode("utf-8-sig"))
    except ValueError as error:
        raise NoSePuedeVerificar(f"{PLUGIN_JSON} en {sha[:7]} no es un JSON legible: {error}")
    version = datos.get("version") if isinstance(datos, dict) else None
    if not isinstance(version, str) or not VERSION.match(version):
        raise NoSePuedeVerificar(f"{PLUGIN_JSON} en {sha[:7]} no tiene un «version» válido (X.Y.Z): {version!r}")
    return version


def commit_de_la_etiqueta(raiz, etiqueta):
    resultado = git(raiz, "rev-parse", "--verify", "-q", f"refs/tags/{etiqueta}^{{commit}}")
    if resultado.returncode == 0:
        return resultado.stdout.decode("utf-8").strip()
    if resultado.returncode == 1 and not resultado.stderr.strip():
        return None
    raise NoSePuedeVerificar(f"git no pudo resolver la etiqueta {etiqueta}: " + error_de(resultado))


def revisar_push_a_main(raiz, sha):
    ultima = ultima_etiqueta(raiz, sha)
    if ultima is not None and not plugin_cambio(raiz, ultima, sha):
        return None
    version = version_del_plugin(raiz, sha)
    etiqueta = PREFIJO_ETIQUETA + version
    apunta_a = commit_de_la_etiqueta(raiz, etiqueta)
    if apunta_a == sha:
        return None
    desde = ultima if ultima is not None else "el inicio"
    if etiqueta == ultima:
        faltante = f"{sha[:7]} no tiene la etiqueta {etiqueta}: la versión sigue en {version}, la de la última etiqueta"
    elif apunta_a is None:
        faltante = f"{sha[:7]} no tiene la etiqueta {etiqueta}"
    else:
        faltante = f"la etiqueta {etiqueta} apunta a {apunta_a[:7]} y no a {sha[:7]}"
    return (
        f"el push a main cambia plugin/ desde {desde} y {faltante}. "
        f"Subí «version» en {PLUGIN_JSON}, etiquetá con «claude plugin tag ./plugin» y empujá la etiqueta junto con la rama"
    )


def revisar(entrada):
    raiz = None
    revisadas = 0
    for linea in entrada.splitlines():
        if not linea.strip():
            continue
        partes = linea.split()
        if len(partes) != 4 or not SHA.match(partes[1]) or not SHA.match(partes[3]):
            raise NoSePuedeVerificar(f"línea ilegible en la entrada del pre-push: {linea!r}")
        if partes[2] != REF_MAIN or partes[1] == CEROS:
            continue
        if raiz is None:
            raiz = raiz_del_repo()
        revisadas += 1
        problema = revisar_push_a_main(raiz, partes[1])
        if problema:
            return revisadas, problema
    return revisadas, None


def main(argv):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if argv:
        print(USO, file=sys.stderr)
        return 2
    try:
        revisadas, problema = revisar(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except NoSePuedeVerificar as error:
        print(f"ENTREGA BLOQUEADA: {error}. Sin verificar la entrega no se empuja a main.", file=sys.stderr)
        return 2
    if problema:
        print(f"ENTREGA BLOQUEADA: {problema}.", file=sys.stderr)
        return 1
    if revisadas:
        print("entrega limpia")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
