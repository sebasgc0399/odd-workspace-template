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


def _linea(lineas, patron, desde=0):
    for inicio in (desde, 0):
        for linea in lineas[inicio:]:
            if patron.search(linea):
                return linea.strip()
    return None


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
    lineas, salida = texto.splitlines(), {}
    for seccion in SECCIONES_DE_PACKAGE:
        valor = datos.get(seccion)
        if not isinstance(valor, dict):
            continue
        desde = next((i for i, l in enumerate(lineas) if re.search(r'"%s"\s*:' % re.escape(seccion), l)), 0)
        for nombre in valor:
            salida.setdefault(nombre, (nombre, _linea(lineas, re.compile(r'"%s"\s*:' % re.escape(nombre)), desde)))
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
    lineas, salida = texto.splitlines(), {}
    for requisito in requisitos:
        nombre = _requisito(requisito) if isinstance(requisito, str) else None
        if nombre:
            salida.setdefault(_pep503(nombre), (nombre, _linea(lineas, re.compile(re.escape(requisito.strip())))))
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
    lineas, salida = texto.splitlines(), {}
    for m in PACKAGE_REFERENCE_RE.finditer(texto):
        numero = texto.count("\n", 0, m.start(1))
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
    datos, lineas, salida = _toml(texto), texto.splitlines(), {}
    for seccion in SECCIONES_DE_CARGO:
        tabla = datos.get(seccion)
        if not isinstance(tabla, dict):
            continue
        for nombre in tabla:
            e = re.escape(nombre)
            patron = re.compile(r'^\s*(?:"%s"|%s)\s*=|^\s*\[%s\.%s\]' % (e, e, re.escape(seccion), e))
            salida.setdefault(nombre, (nombre, _linea(lineas, patron)))
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
