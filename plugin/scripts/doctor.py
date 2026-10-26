import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import namedtuple
from pathlib import Path

import config_loader
import plantilla_writer
from odd_ws import capas as convencion

MARKETPLACE = "odd-workspace-template"
URL_MARKETPLACE = "https://github.com/sebasgc0399/odd-workspace-template.git"
UMBRAL_MS = 100
OK, FALTA, AVISO, NO_APLICA = "OK", "FALTA", "AVISO", "NO APLICA"
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
USO = "uso: doctor.py [--arreglar <id>]"
COMANDO_RDD = ["gentle-ai", "review", "mode", "disable", "--scope", "global"]

AYUDA_LISTA = "Creá ~/.odd-ws/denylist.txt en UTF-8, un término por línea (o apuntá ODD_WS_DENYLIST a otra ruta). Sin ella, el barrido bloquea todos los commits."
AYUDA_PYTHON = ("Desactivá el alias de ejecución de python.exe (Configuración > Aplicaciones > Configuración avanzada de aplicaciones > "
                "Alias de ejecución de aplicaciones) o poné %LOCALAPPDATA%\\Python\\bin antes de WindowsApps en el PATH de usuario.")
AYUDA_CREDENCIALES = "Instalá Git for Windows con Git Credential Manager, o corré git config --global credential.helper manager."
AYUDA_CLAUDE = "Actualizá Claude Code a 2.1.284 o superior."
AYUDA_GENTLE = "Instalá o actualizá gentle-ai (en Windows: go install github.com/gentleman-programming/gentle-ai/v4/cmd/gentle-ai@latest) y corré sync con Claude Code cerrado."
AYUDA_RDD = "D3: el RDD nativo no ve el dominio (su reviewer corre sin herramientas); la plantilla trae el propio. Solo se apaga si lo pedís con --arreglar rdd."
AYUDA_TELEMETRIA = "Apagala en sus dos capas: enabled: false en ~/.gentle-ai/telemetry.json y la variable de usuario GENTLE_AI_TELEMETRY=0 (la variable gana aunque el json se regenere)."
AYUDA_ENGRAM = "Actualizá engram a 3.5 o superior desde su release oficial (en Windows, renombrá el .exe en uso antes de reemplazarlo)."
AYUDA_JQ = "scoop install jq (lo exige engram setup)."
AYUDA_LOCAL = "Se arregla a mano: tiene que ser un objeto JSON en UTF-8. Después, otra vez el doctor."
AYUDA_CONFIG = f"Arreglá {config_loader.NOMBRE} (el detalle dice qué está roto) y volvé a correr el doctor."
AYUDA_WRITER_EDITADO = ("Pasá tu cambio a la description (en una sola línea) o a un bloque <!-- instancia:... -->. Para volver a la plantilla, "
                        "sacá el archivo de .claude/agents, corré --arreglar con su id y copiá tu texto a los bloques del nuevo.")
AYUDA_WRITER_AJENO = ("Sacalo de .claude/agents, corré --arreglar con su id y pasá tu texto a la description y a los bloques "
                      "<!-- instancia:... --> del nuevo: así la plantilla lo mantiene.")
AYUDA_WRITER_NOMBRE = f"Renombrá la capa en {config_loader.NOMBRE} con minúsculas, dígitos y guiones, empezando por letra o dígito."
AYUDA_WRITER_ILEGIBLE = "Guardalo en UTF-8 y volvé a correr el doctor."
COPIA_DE_EMERGENCIA = ".claude/plugin"

Resultado = namedtuple("Resultado", "id estado detalle comando ayuda arreglo")


def resultado(id, estado, detalle, comando=None, ayuda="", arreglo=None):
    return Resultado(id, estado, detalle, comando, ayuda, arreglo)


def leer_version(texto):
    encontrada = VERSION.search(texto or "")
    return tuple(int(parte) for parte in encontrada.groups()) if encontrada else None


def texto_version(version):
    return ".".join(map(str, version))


def primera_linea(texto):
    return next((linea.strip() for linea in (texto or "").splitlines() if linea.strip()), "")


def entorno_de_subprocesos():
    return {clave: valor for clave, valor in os.environ.items() if clave != "CLAUDECODE"}


class Contexto:
    def __init__(self, cwd=None):
        self.home = Path.home()
        self.cwd = Path(cwd or os.getcwd())
        self.ejecutable = sys.executable
        self.windows = os.name == "nt"
        self.entorno = os.environ
        self.plugin = Path(__file__).resolve().parents[1]

    def ejecutar(self, args, cwd=None):
        try:
            completado = subprocess.run(args, cwd=cwd or self.cwd, capture_output=True, timeout=120, env=entorno_de_subprocesos())
        except subprocess.TimeoutExpired:
            return 124, "se pasó del tiempo"
        except OSError:
            return None, ""
        return completado.returncode, completado.stdout.decode("utf-8", "replace") + completado.stderr.decode("utf-8", "replace")

    def which(self, nombre):
        return shutil.which(nombre)

    def medir(self, ruta):
        tiempos = []
        for _ in range(5):
            inicio = time.perf_counter()
            subprocess.run([ruta, "-c", "pass"], capture_output=True, env=entorno_de_subprocesos())
            tiempos.append((time.perf_counter() - inicio) * 1000)
        return statistics.median(tiempos)


def raiz_del_clon(ctx):
    codigo, salida = ctx.ejecutar(["git", "rev-parse", "--show-toplevel"], cwd=ctx.cwd)
    if codigo != 0 or not primera_linea(salida):
        return None
    raiz = Path(primera_linea(salida))
    try:
        datos = json.loads((raiz / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raiz if isinstance(datos, dict) and datos.get("name") == MARKETPLACE else None


def chequear_repo_hooks(ctx, raiz):
    if raiz is None:
        return resultado("repo-hooks", NO_APLICA, "no estás dentro de un clon de odd-workspace-template")
    valor = primera_linea(ctx.ejecutar(["git", "-C", str(raiz), "config", "--get", "core.hooksPath"])[1])
    if valor == ".githooks":
        return resultado("repo-hooks", OK, "core.hooksPath = .githooks")
    return resultado("repo-hooks", FALTA, f"core.hooksPath = {valor or '(sin configurar)'}: en este clon no corre ningún barrido",
                     ["git", "-C", str(raiz), "config", "core.hooksPath", ".githooks"])


def chequear_lista_negra(ctx, raiz):
    if raiz is None:
        return resultado("lista-negra", NO_APLICA, "no estás dentro de un clon de odd-workspace-template")
    codigo, salida = ctx.ejecutar([ctx.ejecutable, str(raiz / "tools" / "barrido.py"), "--autoprueba"], cwd=raiz)
    lineas = [linea.strip() for linea in salida.splitlines() if linea.strip()]
    if codigo == 0:
        return resultado("lista-negra", OK, lineas[0] if lineas else "autoprueba ok")
    return resultado("lista-negra", FALTA, lineas[-1] if lineas else "la autoprueba del barrido falló", None, AYUDA_LISTA)


def anotar_plugin_root(local, datos, plugin):
    local.write_bytes((json.dumps({**datos, "plugin_root": str(plugin)}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return f"plugin_root = {plugin} en {local}"


def raiz_de_instancia(ctx):
    return config_loader.encontrar_raiz(config_loader.inicio_de_sesion(ctx.entorno, str(ctx.cwd)))


def chequear_plugin_root(ctx):
    raiz = raiz_de_instancia(ctx)
    if raiz is None:
        return resultado("plugin-root", NO_APLICA, f"no estás dentro de una instancia (no hay {config_loader.NOMBRE})")
    if (raiz / COPIA_DE_EMERGENCIA / "scripts" / "reglas.py").is_file():
        return resultado("plugin-root", OK, f"la instancia usa la copia de emergencia en {COPIA_DE_EMERGENCIA}")
    local = raiz / config_loader.NOMBRE_LOCAL
    try:
        datos = json.loads(local.read_text(encoding="utf-8-sig")) if local.is_file() else {}
    except (OSError, ValueError):
        datos = None
    if not isinstance(datos, dict):
        return resultado("plugin-root", FALTA, f"{local} no se puede leer como un objeto JSON", None, AYUDA_LOCAL)
    anotado = datos.get("plugin_root")

    def arreglo():
        return anotar_plugin_root(local, datos, ctx.plugin)

    if not isinstance(anotado, str) or not anotado:
        return resultado("plugin-root", FALTA, f"plugin_root sin anotar en {local}: el pre-commit de la instancia no encuentra el plugin",
                         arreglo=arreglo)
    if not (Path(anotado) / "scripts" / "reglas.py").is_file():
        return resultado("plugin-root", FALTA, f"plugin_root = {anotado} no existe (una versión desinstalada o movida)", arreglo=arreglo)
    if config_loader.canonica(anotado) != config_loader.canonica(ctx.plugin):
        return resultado("plugin-root", FALTA, f"plugin_root = {anotado} es otra copia del plugin; el doctor corre desde {ctx.plugin}",
                         arreglo=arreglo)
    return resultado("plugin-root", OK, f"plugin_root = {anotado}")


def chequear_writers(ctx):
    raiz = raiz_de_instancia(ctx)
    if raiz is None:
        return []
    try:
        declaradas = config_loader.capas(raiz)
    except config_loader.ConfigRota as error:
        return [resultado("writers", FALTA, f"no se pueden revisar los writers: {error}", None, AYUDA_CONFIG)]
    return [chequear_writer(raiz, capa) for capa in declaradas]


def chequear_writer(raiz, capa):
    id, ruta = f"writer-{capa}", convencion.writer(capa)
    revision = plantilla_writer.revisar(raiz, capa)
    actual = plantilla_writer.version()

    def arreglo():
        return f"{plantilla_writer.escribir(raiz, capa)} (plantilla v{actual})"

    if revision.codigo == "nombre":
        return resultado(id, AVISO, f"la capa «{capa}» no puede tener writer: {id} no cumple {convencion.WRITER_RE.pattern}, "
                                    "y ni el guard ni la compuerta lo reconocerían", None, AYUDA_WRITER_NOMBRE)
    if revision.codigo == "falta":
        return resultado(id, AVISO, f"falta {ruta}: sin writer, la capa {capa} no se puede delegar", arreglo=arreglo)
    if revision.codigo == "ilegible":
        return resultado(id, FALTA, f"{ruta} no se puede leer como UTF-8", None, AYUDA_WRITER_ILEGIBLE)
    if revision.codigo == "ajeno":
        return resultado(id, FALTA, f"{ruta} no lo generó la plantilla (le faltan odd-ws-plantilla u odd-ws-hash)", None, AYUDA_WRITER_AJENO)
    if revision.codigo == "malformado":
        return resultado(id, FALTA, f"{ruta}: los bloques de la instancia están mal formados (sin cerrar, cruzados o repetidos)", None,
                         AYUDA_WRITER_EDITADO)
    if revision.codigo == "editado":
        return resultado(id, FALTA, f"{ruta} se editó fuera de los bloques de la instancia: regenerarlo pisaría ese cambio", None,
                         AYUDA_WRITER_EDITADO)
    if revision.codigo == "atrasado":
        detalle = (f"{ruta} está en la plantilla v{revision.version} y el plugin trae la v{actual}" if revision.version != actual
                   else f"{ruta}: regenerarlo lo cambiaría (plantilla v{actual})")
        return resultado(id, AVISO, detalle, arreglo=arreglo)
    return resultado(id, OK, f"{ruta} al día (plantilla v{actual})")


def chequear_python(ctx):
    ruta = ctx.which("python")
    if not ruta:
        return resultado("python", FALTA, "python no está en el PATH: los hooks lo llaman por nombre", None, "Instalá Python y agregalo al PATH.")
    codigo, salida = ctx.ejecutar([ruta, "--version"])
    if codigo != 0:
        return resultado("python", FALTA, f"{ruta} no corre", None, "Reinstalá Python o revisá el PATH.")
    version = primera_linea(salida) or "Python"
    if os.path.normcase(os.path.abspath(ruta)) == os.path.normcase(os.path.abspath(ctx.ejecutable)):
        return resultado("python", OK, f"{version} ({ruta})")
    del_path, real = ctx.medir(ruta), ctx.medir(ctx.ejecutable)
    if del_path - real > UMBRAL_MS:
        return resultado("python", AVISO, f"{version}: el python del PATH ({ruta}) arranca en {del_path:.0f} ms y el intérprete real en {real:.0f} ms; cada hook paga la diferencia", None, AYUDA_PYTHON)
    return resultado("python", OK, f"{version}: arranca en {del_path:.0f} ms")


def chequear_credenciales(ctx):
    codigo, salida = ctx.ejecutar(["git", "config", "--get", "credential.helper"])
    if codigo is None:
        return resultado("git-credenciales", FALTA, "git no está instalado", None, "Instalá Git for Windows.")
    if codigo == 0 and primera_linea(salida):
        return resultado("git-credenciales", OK, f"credential.helper = {primera_linea(salida)}")
    return resultado("git-credenciales", FALTA, "sin credential.helper: git no puede guardar la credencial de GitHub", None, AYUDA_CREDENCIALES)


def chequear_version(ctx, id, args, minimo, ayuda):
    codigo, salida = ctx.ejecutar(args)
    if codigo is None:
        return resultado(id, FALTA, f"{args[0]} no está instalado", None, ayuda), False
    version = leer_version(salida)
    if version is None:
        return resultado(id, AVISO, f"no se pudo leer la versión: {primera_linea(salida)[:80] or '(vacío)'}", None, ayuda), True
    if minimo and version < minimo:
        return resultado(id, FALTA, f"{texto_version(version)} es menor que {texto_version(minimo)}", None, ayuda), True
    return resultado(id, OK, texto_version(version)), True


def chequear_marketplace(ctx):
    try:
        datos = json.loads((ctx.home / ".claude" / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = None
    if isinstance(datos, dict) and MARKETPLACE in datos:
        return resultado("marketplace", OK, f"{MARKETPLACE} registrado")
    return resultado("marketplace", FALTA, f"{MARKETPLACE} no está registrado", ["claude", "plugin", "marketplace", "add", URL_MARKETPLACE])


def chequear_rdd(ctx, hay_gentle):
    if not hay_gentle:
        return resultado("rdd", NO_APLICA, "gentle-ai no está instalado")
    codigo, salida = ctx.ejecutar(["gentle-ai", "review", "mode", "status"])
    estado = primera_linea(salida)
    if codigo == 0 and re.search(r":\s*off\b", estado):
        return resultado("rdd", OK, estado)
    if codigo == 0 and re.search(r":\s*on\b", estado):
        return resultado("rdd", AVISO, estado, COMANDO_RDD, AYUDA_RDD)
    return resultado("rdd", AVISO, f"no se pudo leer el estado del RDD: {estado or '(vacío)'}", None, AYUDA_RDD)


def chequear_telemetria(ctx, hay_gentle):
    if not hay_gentle:
        return resultado("telemetria", NO_APLICA, "gentle-ai no está instalado")
    codigo, salida = ctx.ejecutar(["gentle-ai", "telemetry", "status"])
    estado = primera_linea(salida)
    if codigo == 0 and "disabled" in estado:
        return resultado("telemetria", OK, estado)
    return resultado("telemetria", AVISO, estado or "no se pudo leer el estado de la telemetría", None, AYUDA_TELEMETRIA)


def diagnosticar(ctx):
    raiz = raiz_del_clon(ctx)
    claude, _ = chequear_version(ctx, "claude", ["claude", "--version"], (2, 1, 284), AYUDA_CLAUDE)
    gentle, hay_gentle = chequear_version(ctx, "gentle-ai", ["gentle-ai", "version"], (4, 2, 0), AYUDA_GENTLE)
    engram, _ = chequear_version(ctx, "engram", ["engram", "version"], (3, 5, 0), AYUDA_ENGRAM)
    jq, _ = chequear_version(ctx, "jq", ["jq", "--version"], None, AYUDA_JQ)
    return [
        chequear_repo_hooks(ctx, raiz),
        chequear_lista_negra(ctx, raiz),
        chequear_plugin_root(ctx),
        *chequear_writers(ctx),
        chequear_python(ctx),
        chequear_credenciales(ctx),
        claude,
        chequear_marketplace(ctx),
        gentle,
        chequear_rdd(ctx, hay_gentle),
        chequear_telemetria(ctx, hay_gentle),
        engram,
        jq,
    ]


def imprimir(resultados):
    ancho = max(len(r.id) for r in resultados)
    sangria = " " * (ancho + 13)
    for r in resultados:
        print(f"{r.id:<{ancho}}  {r.estado:<9}  {r.detalle}")
        if r.estado in (FALTA, AVISO):
            if r.comando:
                print(f"{sangria}arreglo: --arreglar {r.id}  ({' '.join(r.comando)})")
            elif r.arreglo:
                print(f"{sangria}arreglo: --arreglar {r.id}")
            if r.ayuda:
                print(f"{sangria}cómo: {r.ayuda}")
    faltas = sum(r.estado == FALTA for r in resultados)
    avisos = sum(r.estado == AVISO for r in resultados)
    print(f"\n{faltas} FALTA, {avisos} AVISO")


def arreglar(ctx, resultados, objetivo):
    elegido = next((r for r in resultados if r.id == objetivo), None)
    if elegido is None:
        print(f"no existe el ítem «{objetivo}». Ítems: {', '.join(r.id for r in resultados)}")
        return 2
    if elegido.estado in (OK, NO_APLICA):
        print(f"{objetivo}: {elegido.estado}; no hay nada que arreglar")
        return 0
    if not elegido.comando and not elegido.arreglo:
        print(f"{objetivo} no tiene arreglo automático. {elegido.ayuda}")
        return 2
    if elegido.arreglo:
        print("escribiendo: " + elegido.arreglo())
    else:
        print("ejecutando: " + " ".join(elegido.comando))
        _, salida = ctx.ejecutar(elegido.comando)
        if salida.strip():
            print(salida.strip())
    nuevo = next(r for r in diagnosticar(ctx) if r.id == objetivo)
    print(f"{objetivo}: {nuevo.estado} — {nuevo.detalle}")
    return 1 if nuevo.estado == FALTA else 0


def principal(argv, ctx=None):
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    if argv and (argv[0] != "--arreglar" or len(argv) != 2):
        print(USO)
        return 2
    ctx = ctx or Contexto()
    resultados = diagnosticar(ctx)
    if argv:
        return arreglar(ctx, resultados, argv[1])
    imprimir(resultados)
    return 1 if any(r.estado == FALTA for r in resultados) else 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
