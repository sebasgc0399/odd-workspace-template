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
import verificar_capa
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
AYUDA_AGENTES_SKILLS = ("Creá la skill en .claude/skills/<skill>/SKILL.md o sacala del skills: del agente. Una skill precargada no puede llevar "
                        "paths: ni disable-model-invocation: true (Claude Code la saltea en silencio), y criterios y capa-<capa> llevan una "
                        "línea suelta CENTINELA <skill> <fecha>: sin ella, el writer cree que no vino y la vuelve a leer del disco.")
AYUDA_AGENTES_HOOKS = ("Pasá esos hooks al .claude/settings.json de la instancia y filtrá por agent_type en el script: los del frontmatter de "
                       "un agente del proyecto solo corren si la carpeta aceptó el diálogo de confianza, y nunca en una sesión -p.")
AYUDA_RUTAS = (f"Poné en {config_loader.NOMBRE_LOCAL} la ruta de cada repo de {config_loader.NOMBRE} (repos.<repo>.path, una carpeta que "
               "exista en esta máquina) o corregí lo que diga el detalle. Después, otra vez el doctor.")
AYUDA_HOOKS_AJENO = ("core.hooksPath apunta a otro lado y el doctor no lo pisa: cambialo a mano a .githooks o integrá .githooks/pre-commit "
                     "a esos hooks.")
AYUDA_PRE_COMMIT = "Falta .githooks/pre-commit: generalo con /odd-ws:bootstrap, que completa la instancia sin pisar lo que ya existe."
AYUDA_SETTINGS = "Arreglalo a mano: tiene que ser un objeto JSON en UTF-8. Después, otra vez el doctor."
COPIA_DE_EMERGENCIA = ".claude/plugin"
SETTINGS = ".claude/settings.json"
PLUGIN = "odd-ws"
CLAVE_PLUGIN = f"{PLUGIN}@{MARKETPLACE}"
HOOKS_PATH = ".githooks"
PRE_COMMIT = f"{HOOKS_PATH}/pre-commit"
AYUDA_PLUGIN = (f'Agregá "enabledPlugins": {{"{CLAVE_PLUGIN}": true}} a {SETTINGS} de la instancia (es tu archivo: el doctor no lo toca) '
                "y reiniciá Claude Code.")
CON_CENTINELA = re.compile(r"criterios|capa-.+")
SIN_INVOCACION = re.compile(r"disable-model-invocation\s*:\s*(?:true|True|TRUE)\s*(?:#.*)?$")

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


def chequear_instancia(ctx):
    raiz = raiz_de_instancia(ctx)
    if raiz is None:
        return []
    return [chequear_config(raiz), chequear_hooks_de_instancia(ctx, raiz), chequear_plugin_habilitado(raiz)]


def chequear_config(raiz):
    try:
        config = config_loader.cargar(raiz)
    except config_loader.ConfigRota as error:
        return resultado("config", FALTA, str(error), None, AYUDA_RUTAS)
    return resultado("config", OK, f"{len(config['repos'])} repos con su ruta y {len(config['layers'])} capas")


def raiz_del_repo_de(ctx, raiz):
    codigo, salida = ctx.ejecutar(["git", "-C", str(raiz), "rev-parse", "--show-toplevel"])
    return Path(primera_linea(salida)) if codigo == 0 and primera_linea(salida) else None


def chequear_hooks_de_instancia(ctx, raiz):
    id = "instancia-hooks"
    repo = raiz_del_repo_de(ctx, raiz)
    if repo is None:
        return resultado(id, NO_APLICA, "la raíz de la instancia no está en un repo git")
    if config_loader.canonica(repo) != config_loader.canonica(raiz):
        return resultado(id, NO_APLICA, f"la instancia está dentro del repo {repo} y no es la raíz de uno: el doctor no toca sus hooks")
    codigo, salida = ctx.ejecutar(["git", "-C", str(raiz), "config", "--get", "core.hooksPath"])
    valor = primera_linea(salida) if codigo == 0 else ""
    hay_pre_commit = (raiz / PRE_COMMIT).is_file()
    if valor and valor != HOOKS_PATH:
        return resultado(id, FALTA, f"core.hooksPath = {valor}: en esta instancia no corre su pre-commit", None, AYUDA_HOOKS_AJENO)
    if valor and hay_pre_commit:
        return resultado(id, OK, f"core.hooksPath = {HOOKS_PATH} y existe {PRE_COMMIT}")
    if valor:
        return resultado(id, FALTA, f"core.hooksPath = {HOOKS_PATH}, pero falta {PRE_COMMIT}", None, AYUDA_PRE_COMMIT)
    arreglo = ["git", "-C", str(raiz), "config", "core.hooksPath", HOOKS_PATH]
    detalle = "core.hooksPath = (sin configurar): en esta instancia no corre ningún pre-commit"
    if hay_pre_commit:
        return resultado(id, FALTA, detalle, arreglo)
    return resultado(id, FALTA, f"{detalle}, y además falta {PRE_COMMIT}", arreglo, AYUDA_PRE_COMMIT)


def chequear_plugin_habilitado(raiz):
    id = "instancia-plugin"
    ruta = raiz / SETTINGS
    if not ruta.is_file():
        return resultado(id, AVISO, f"no hay {SETTINGS}: el plugin {PLUGIN} no está habilitado en esta instancia", None, AYUDA_PLUGIN)
    texto = leer_texto(ruta)
    try:
        datos = json.loads(texto) if texto is not None else None
    except ValueError:
        datos = None
    if not isinstance(datos, dict):
        return resultado(id, FALTA, f"{SETTINGS} no se puede leer como un objeto JSON", None, AYUDA_SETTINGS)
    habilitados = datos.get("enabledPlugins")
    if isinstance(habilitados, dict) and habilitados.get(CLAVE_PLUGIN) is True:
        return resultado(id, OK, f"{CLAVE_PLUGIN} habilitado en {SETTINGS}")
    return resultado(id, AVISO, f"{CLAVE_PLUGIN} no está habilitado en {SETTINGS}: sin el plugin, la instancia no tiene sus hooks", None,
                     AYUDA_PLUGIN)


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


def leer_texto(ruta):
    try:
        return ruta.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def frontmatter(texto):
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        return []
    fin = next((i for i in range(1, len(lineas)) if lineas[i].strip() == "---"), None)
    return lineas[1:fin] if fin else []


def declara(cabecera, patron):
    return any(re.match(patron, linea) for linea in cabecera)


def chequear_agentes(ctx):
    raiz = raiz_de_instancia(ctx)
    if raiz is None:
        return []
    carpeta = raiz / convencion.AGENTES
    agentes = [(ruta, leer_texto(ruta)) for ruta in sorted(carpeta.glob("*.md"))] if carpeta.is_dir() else []
    return [chequear_skills_precargadas(ctx, raiz, agentes), chequear_hooks_de_agentes(agentes)]


def problemas_de_skill(nombre, ruta):
    texto = leer_texto(ruta)
    if texto is None:
        return [(FALTA, f"{nombre} no se puede leer como UTF-8")]
    cabecera, problemas = frontmatter(texto), []
    if declara(cabecera, r"paths\s*:"):
        problemas.append((FALTA, f"{nombre} tiene paths: en el frontmatter y Claude Code no la precarga"))
    if declara(cabecera, SIN_INVOCACION):
        problemas.append((FALTA, f"{nombre} tiene disable-model-invocation: true y Claude Code no la precarga"))
    if CON_CENTINELA.fullmatch(nombre) and not re.search(r"(?m)^CENTINELA %s(?=\s|$)" % re.escape(nombre), texto):
        problemas.append((AVISO, f"{nombre} no tiene su línea CENTINELA {nombre}"))
    return problemas


def chequear_skills_precargadas(ctx, raiz, agentes):
    id = "agentes-skills"
    if not agentes:
        return resultado(id, NO_APLICA, f"la instancia no tiene agentes en {convencion.AGENTES}")
    problemas, revisadas, de_plugins = [], 0, 0
    for ruta, texto in agentes:
        if texto is None:
            problemas.append((FALTA, f"{ruta.name} no se puede leer como UTF-8"))
            continue
        for nombre in verificar_capa.skills_del_frontmatter(texto) or []:
            if ":" in nombre:
                de_plugins += 1
                continue
            revisadas += 1
            relativa = convencion.skill_de(nombre)
            skill = next((base / relativa for base in (raiz, ctx.home) if (base / relativa).is_file()), None)
            if skill is None:
                problemas.append((FALTA, f"{ruta.name} precarga {nombre} y no existe {relativa}"))
                continue
            problemas += [(estado, f"{ruta.name}: {detalle}") for estado, detalle in problemas_de_skill(nombre, skill)]
    if problemas:
        estado = FALTA if any(estado == FALTA for estado, _ in problemas) else AVISO
        return resultado(id, estado, "; ".join(detalle for _, detalle in problemas), None, AYUDA_AGENTES_SKILLS)
    if not revisadas + de_plugins:
        return resultado(id, NO_APLICA, "ningún agente precarga skills")
    sin_verificar = f"; {de_plugins} de plugins, sin verificar" if de_plugins else ""
    return resultado(id, OK, f"{revisadas} skills precargadas, todas en disco y sin nada que las saltee{sin_verificar}")


def chequear_hooks_de_agentes(agentes):
    id = "agentes-hooks"
    if not agentes:
        return resultado(id, NO_APLICA, f"la instancia no tiene agentes en {convencion.AGENTES}")
    con_hooks = [ruta.name for ruta, texto in agentes if texto is not None and declara(frontmatter(texto), r"hooks\s*:")]
    if con_hooks:
        return resultado(id, AVISO, f"{', '.join(con_hooks)}: hooks: en el frontmatter, que Claude Code saltea en silencio sin la confianza "
                                    "de la carpeta", None, AYUDA_AGENTES_HOOKS)
    return resultado(id, OK, "ningún agente declara hooks: en el frontmatter")


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
        *chequear_instancia(ctx),
        *chequear_writers(ctx),
        *chequear_agentes(ctx),
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
