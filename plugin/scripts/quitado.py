import sys

sys.dont_write_bytecode = True

import argparse
import fnmatch
import json
import os
import re

import recibo
from triaje import decodificar

SIN_TOMLLIB = "requiere Python 3.11 o más para leer TOML"
REQUISITO_RE = re.compile(r"\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")
ESQUEMA_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
COMENTARIO_RE = re.compile(r"(?:^|\s)#.*")
PACKAGE_REFERENCE_RE = re.compile(r"<PackageReference\b[^>]*?\bInclude\s*=\s*[\"']([^\"']+)[\"']", re.I)
CONFIGURACION_GRADLE = (r"(?:[a-z][A-Za-z]*(?:Implementation|Api|CompileOnly|RuntimeOnly|AnnotationProcessor)"
                        r"|implementation|api|compileOnly|runtimeOnly|annotationProcessor|kapt|ksp|compile|testCompile)")
GRADLE_RE = re.compile(r"\s*" + CONFIGURACION_GRADLE + r"\s*\(?\s*(?:(?:platform|enforcedPlatform)\s*\(\s*)?"
                       r"(?:[\"']([^\"'\s:]+:[^\"'\s:]+)(?::[^\"']*)?[\"']|([A-Za-z_]\w*(?:\.\w+)+))")
GRADLE_MAPA_RE = re.compile(r"\s*" + CONFIGURACION_GRADLE + r"\s*\(?\s*group\s*[:=]\s*[\"']([^\"']+)[\"']\s*,"
                            r"\s*name\s*[:=]\s*[\"']([^\"']+)[\"']")
COMENTARIO_XML_RE = re.compile(r"<!--.*?-->", re.S)
PIEZA_TOML = r"""(?:[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|'[^']*')"""
CLAVE_TOML = r"%s(?:\s*\.\s*%s)*" % (PIEZA_TOML, PIEZA_TOML)
ASIGNACION_TOML_RE = re.compile(r"\s*(%s)\s*=" % CLAVE_TOML)
ENCABEZADO_TOML_RE = re.compile(r"\s*(\[\[?)\s*(%s)\s*\]\]?\s*(?:#.*)?$" % CLAVE_TOML)
PIEZA_TOML_RE = re.compile(r"""[A-Za-z0-9_-]+|"((?:[^"\\]|\\.)*)"|'([^']*)'""")
SECCIONES_DE_PACKAGE = ("dependencies", "devDependencies")
SECCIONES_DE_CARGO = ("dependencies", "dev-dependencies")
VACIO = ("el diff desde la base está vacío: si el ticket ya se mergeó, el merge-base es su propia punta; "
         "pasa la base de antes del ticket con --repo RUTA#BASE")
VACIO_EXPLICITA = "el diff desde la base explícita está vacío"


class ErrorEntorno(Exception):
    pass


class NoSePuedeLeer(Exception):
    pass


def _git_ok(top, *args):
    r = recibo.git(top, *args)
    if r.returncode != 0:
        raise ErrorEntorno("git %s falló en %s: %s" % (args[0], top, r.stderr.decode("utf-8", errors="replace").strip()))
    return r


def cambios(top, base):
    partes = _git_ok(top, "diff", "--name-status", "-z", "--find-renames", "--no-color", "--no-ext-diff", base).stdout.split(b"\0")
    salida, i = [], 0
    while i < len(partes) - 1:
        estado = partes[i].decode("ascii", errors="replace")[:1]
        if not estado:
            i += 1
            continue
        antes = partes[i + 1].decode("utf-8", errors="replace")
        if estado in "RC":
            salida.append((estado, antes, partes[i + 2].decode("utf-8", errors="replace")))
            i += 3
        else:
            salida.append((estado, antes, antes))
            i += 2
    return salida


def cambia_de_verdad(top, base, estado, ruta):
    if estado != "M":
        return True
    return bool(_git_ok(top, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", base, "--", ruta).stdout.strip())


def _claves_de_cada_seccion_json(texto):
    secciones, pila, clave, numero, i = {}, [], None, 0, 0
    while i < len(texto):
        c = texto[i]
        if c == '"':
            fin = i + 1
            while texto[fin] != '"':
                fin += 2 if texto[fin] == "\\" else 1
            despues = fin + 1
            while despues < len(texto) and texto[despues] in " \t\r\n":
                despues += 1
            if despues < len(texto) and texto[despues] == ":":
                clave = json.loads(texto[i:fin + 1])
                if len(pila) == 2 and pila[0] == ("{", None) and pila[1][0] == "{":
                    secciones.setdefault(pila[1][1], {})[clave] = numero
            i = fin + 1
            continue
        if c == "\n":
            numero += 1
        elif c in "{[":
            pila.append((c, clave))
            clave = None
        elif c in "}]":
            pila.pop()
        elif c == ",":
            clave = None
        i += 1
    return secciones


def _piezas_toml(clave):
    return tuple(next((citada for citada in m.groups() if citada is not None), m.group(0)) for m in PIEZA_TOML_RE.finditer(clave))


def _cadenas_toml(valor):
    cadenas, codigo, i = [], [], 0
    while i < len(valor) and valor[i] != "#":
        c = valor[i]
        if c in "\"'":
            fin = i + 1
            while fin < len(valor) and valor[fin] != c:
                fin += 2 if c == '"' and valor[fin] == "\\" else 1
            cadenas.append(valor[i + 1:fin])
            i = fin + 1
            continue
        codigo.append(c)
        i += 1
    return cadenas, "".join(codigo)


def _lineas_toml(texto):
    tabla, clave, abiertos = (), (), 0
    for numero, linea in enumerate(texto.split("\n")):
        valor = linea
        if abiertos <= 0:
            abiertos, clave = 0, ()
            encabezado = ENCABEZADO_TOML_RE.match(linea)
            if encabezado:
                tabla = _piezas_toml(encabezado.group(2)) if encabezado.group(1) == "[" else None
                if tabla is not None:
                    yield numero, tabla, []
                continue
            asignacion = ASIGNACION_TOML_RE.match(linea)
            if asignacion is None:
                continue
            clave, valor = _piezas_toml(asignacion.group(1)), linea[asignacion.end():]
        cadenas, codigo = _cadenas_toml(valor)
        abiertos += codigo.count("[") + codigo.count("{") - codigo.count("]") - codigo.count("}")
        if tabla is not None:
            yield numero, tabla + clave, cadenas


def _toml(texto):
    try:
        import tomllib
    except ImportError:
        raise NoSePuedeLeer(SIN_TOMLLIB)
    try:
        return tomllib.loads(texto)
    except tomllib.TOMLDecodeError as exc:
        raise NoSePuedeLeer(str(exc))


def _pep503(nombre):
    return re.sub(r"[-_.]+", "-", nombre).lower()


def _requisito(texto):
    limpio = texto.strip()
    if not limpio or limpio.startswith("-") or ESQUEMA_RE.match(limpio):
        return None
    m = REQUISITO_RE.match(limpio)
    return m.group(1) if m else None


def de_package_json(texto):
    try:
        datos = json.loads(texto)
    except ValueError as exc:
        raise NoSePuedeLeer(str(exc))
    if not isinstance(datos, dict):
        raise NoSePuedeLeer("no es un objeto JSON")
    lineas, ubicadas, salida = texto.split("\n"), _claves_de_cada_seccion_json(texto), {}
    for seccion in SECCIONES_DE_PACKAGE:
        valor = datos.get(seccion)
        if not isinstance(valor, dict):
            continue
        for nombre in valor:
            numero = ubicadas.get(seccion, {}).get(nombre)
            salida.setdefault(nombre, (nombre, None if numero is None else lineas[numero].strip()))
    return salida


def de_requirements(texto):
    salida = {}
    for linea in texto.splitlines():
        nombre = _requisito(COMENTARIO_RE.sub("", linea))
        if nombre:
            salida.setdefault(_pep503(nombre), (nombre, linea.strip()))
    return salida


def de_pyproject(texto):
    proyecto = _toml(texto).get("project")
    if not isinstance(proyecto, dict):
        return {}
    requisitos = list(proyecto.get("dependencies")) if isinstance(proyecto.get("dependencies"), list) else []
    opcionales = proyecto.get("optional-dependencies")
    if isinstance(opcionales, dict):
        for grupo in opcionales.values():
            requisitos += grupo if isinstance(grupo, list) else []
    lineas, ubicadas, salida = texto.split("\n"), {}, {}
    for numero, ruta, cadenas in _lineas_toml(texto):
        if ruta == ("project", "dependencies") or ruta[:2] == ("project", "optional-dependencies"):
            for cadena in cadenas:
                nombre = _requisito(cadena)
                if nombre:
                    ubicadas.setdefault(_pep503(nombre), lineas[numero].strip())
    for requisito in requisitos:
        nombre = _requisito(requisito) if isinstance(requisito, str) else None
        if nombre:
            salida.setdefault(_pep503(nombre), (nombre, ubicadas.get(_pep503(nombre))))
    return salida


def de_go_mod(texto):
    salida, en_bloque = {}, False
    for linea in texto.splitlines():
        sin_comentario = linea.split("//", 1)[0].strip()
        if en_bloque:
            if sin_comentario.startswith(")"):
                en_bloque = False
            elif sin_comentario:
                salida.setdefault(sin_comentario.split()[0], (sin_comentario.split()[0], linea.strip()))
        elif re.fullmatch(r"require\s*\(", sin_comentario):
            en_bloque = True
        elif re.match(r"require\s+\S", sin_comentario):
            modulo = sin_comentario.split()[1]
            salida.setdefault(modulo, (modulo, linea.strip()))
    return salida


def de_csproj(texto):
    sin_comentarios = COMENTARIO_XML_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), texto)
    lineas, salida = texto.split("\n"), {}
    for m in PACKAGE_REFERENCE_RE.finditer(sin_comentarios):
        numero = sin_comentarios.count("\n", 0, m.start(1))
        salida.setdefault(m.group(1).lower(), (m.group(1), lineas[numero].strip()))
    return salida


def de_gradle(texto):
    salida = {}
    for linea in texto.splitlines():
        m = GRADLE_MAPA_RE.match(linea)
        nombre = "%s:%s" % m.groups() if m else None
        if nombre is None:
            m = GRADLE_RE.match(linea)
            nombre = (m.group(1) or m.group(2)) if m else None
        if nombre:
            salida.setdefault(nombre, (nombre, linea.strip()))
    return salida


def de_cargo(texto):
    datos, lineas, ubicadas, salida = _toml(texto), texto.split("\n"), {}, {}
    for numero, ruta, _ in _lineas_toml(texto):
        if len(ruta) >= 2 and ruta[0] in SECCIONES_DE_CARGO:
            ubicadas.setdefault(ruta[:2], lineas[numero].strip())
    for seccion in SECCIONES_DE_CARGO:
        tabla = datos.get(seccion)
        if not isinstance(tabla, dict):
            continue
        for nombre in tabla:
            salida.setdefault(nombre, (nombre, ubicadas.get((seccion, nombre))))
    return salida


def lector_de(ruta):
    nombre = ruta.rsplit("/", 1)[-1]
    if nombre == "package.json":
        return de_package_json
    if fnmatch.fnmatchcase(nombre, "requirements*.txt"):
        return de_requirements
    if nombre == "pyproject.toml":
        return de_pyproject
    if nombre == "go.mod":
        return de_go_mod
    if nombre.endswith(".csproj"):
        return de_csproj
    if nombre in ("build.gradle", "build.gradle.kts"):
        return de_gradle
    if nombre == "Cargo.toml":
        return de_cargo
    return None


def _actual(top, ruta):
    try:
        with open(os.path.join(top, ruta), "rb") as f:
            return decodificar(f.read())
    except OSError as exc:
        raise NoSePuedeLeer(exc.strerror or str(exc))


def dependencias_quitadas(top, base, antes, ahora, lector):
    previas = lector(decodificar(_git_ok(top, "cat-file", "blob", "%s:%s" % (base, antes)).stdout))
    actuales = lector(_actual(top, ahora))
    return [{"manifiesto": ahora, "nombre": nombre, "linea": linea}
            for clave, (nombre, linea) in previas.items() if clave not in actuales]


def quitado_del_repo(ruta, base_arg):
    top = recibo.raiz_del_repo(ruta)
    base, origen, _ = recibo.elegir_base(top, base_arg, None)
    entradas = cambios(top, base)
    vacio = not any(cambia_de_verdad(top, base, estado, ahora) for estado, _, ahora in entradas)
    archivos, dependencias, avisos = [], [], []
    for estado, antes, ahora in entradas:
        if estado == "D":
            archivos.append(antes)
            continue
        lector = lector_de(ahora) if estado in "MR" else None
        if lector is None or lector_de(antes) is not lector:
            continue
        try:
            dependencias += dependencias_quitadas(top, base, antes, ahora, lector)
        except NoSePuedeLeer as exc:
            avisos.append("%s: no se pudo leer (%s)" % (ahora, exc))
    dependencias.sort(key=lambda d: (d["manifiesto"], d["nombre"].lower()))
    return {"ruta": top, "base": base, "base_origen": origen, "vacio": vacio, "archivos": sorted(archivos),
            "dependencias": dependencias, "avisos": avisos}


def formatear(repos):
    salida = ["quitado: lo que el diff de cada repo quitó desde su base"]
    for r in repos:
        origen = "explícita" if r["base_origen"] == "explicita" else "merge-base con origin/HEAD"
        if r["vacio"]:
            resumen = VACIO_EXPLICITA if r["base_origen"] == "explicita" else VACIO
        elif r["archivos"] or r["dependencias"]:
            resumen = "%d archivo(s) y %d dependencia(s) quitados" % (len(r["archivos"]), len(r["dependencias"]))
        else:
            resumen = "nada quitado"
        salida.append("repo %s (base %s, %s): %s" % (r["ruta"], r["base"][:10], origen, resumen))
        salida += ["  archivo %s" % a for a in r["archivos"]]
        salida += ["  dependencia %s (%s): %s" % (d["nombre"], d["manifiesto"], d["linea"] or "sin línea ubicada")
                   for d in r["dependencias"]]
        salida += ["  aviso %s" % a for a in r["avisos"]]
    return "\n".join(salida)


def construir_parser():
    p = argparse.ArgumentParser(prog="quitado.py",
                                description="Lista lo que el diff del ticket quitó: archivos borrados y dependencias que salieron de un manifiesto.")
    p.add_argument("--repo", action="append", default=[], metavar="RUTA[#BASE]",
                   help="repo o worktree del ticket; base por defecto: el merge-base con la rama de origin/HEAD")
    p.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = construir_parser().parse_args(argv)
    if not args.repo:
        print("quitado: falta --repo", file=sys.stderr)
        return 2
    try:
        repos = [quitado_del_repo(*recibo._partir_repo(t)) for t in args.repo]
    except (ErrorEntorno, recibo.ErrorUso, recibo.ErrorEntorno) as exc:
        print("quitado: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps({"repos": repos}, ensure_ascii=False, indent=2) if args.json else formatear(repos))
    return 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.exit(main())
    except Exception as exc:
        print("quitado: error interno (%s)" % exc, file=sys.stderr)
        sys.exit(2)
