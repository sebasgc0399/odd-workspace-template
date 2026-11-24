import contextlib
import importlib
import io
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

PYTHON_PATH = "C:/py/bin/python.exe"
PYTHON_REAL = "C:/py/core/python.exe"
ALIAS_DE_LA_STORE = "C:/Users/u/AppData/Local/Microsoft/WindowsApps/python3.exe"
SIN_PYTHON = "Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut.\n"
RESPUESTAS_OK = {
    ("git", "config", "--get", "credential.helper"): (0, "manager\n"),
    ("git", "rev-parse", "--show-toplevel"): (128, "fatal: not a git repository\n"),
    (PYTHON_PATH, "-c"): (0, "Python 3.14.3\n"),
    ("claude", "--version"): (0, "2.1.295 (Claude Code)\n"),
    ("gentle-ai", "version"): (0, "gentle-ai 4.2.0\n"),
    ("gentle-ai", "review", "mode", "status"): (0, "receipt-driven development: off (decided by global)\n  global:      off\n"),
    ("gentle-ai", "telemetry", "status"): (0, "telemetry: disabled (source: GENTLE_AI_TELEMETRY)\n"),
    ("engram", "version"): (0, "engram 3.5.1\n"),
    ("jq", "--version"): (0, "jq-1.8.2\n"),
}
GENTLE_DE_LECTURA = {("gentle-ai", "version"), ("gentle-ai", "review", "mode", "status"), ("gentle-ai", "telemetry", "status")}


def d():
    return importlib.import_module("doctor")


def entorno_sin_git():
    return {**{clave: valor for clave, valor in os.environ.items() if not clave.startswith("GIT_")},
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Falso:
    def __init__(self, base, respuestas=None, which=None, tiempos=None, git_real=False, cwd=None, marketplace=True):
        propias = respuestas or {}
        tapadas = [clave for clave in RESPUESTAS_OK if any(isinstance(p, tuple) and clave[:len(p)] == p for p in propias)]
        self.respuestas = {**{c: v for c, v in RESPUESTAS_OK.items() if c not in tapadas}, **propias}
        self.rutas = {"python3": PYTHON_PATH, "python": PYTHON_PATH, **(which or {})}
        self.tiempos = {PYTHON_PATH: 50.0, PYTHON_REAL: 49.0, **(tiempos or {})}
        self.git_real = git_real
        self.home = base / "home"
        self.cwd = cwd or base / "afuera"
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.ejecutable = PYTHON_REAL
        self.windows = True
        self.llamadas = []
        self.entorno = {}
        self.plugin = base / "plugin-instalado"
        (self.plugin / "scripts").mkdir(parents=True, exist_ok=True)
        (self.plugin / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        plugins = self.home / ".claude" / "plugins"
        plugins.mkdir(parents=True, exist_ok=True)
        if marketplace is not None:
            conocidos = {"claude-plugins-official": {}, **({"odd-workspace-template": {}} if marketplace else {})}
            (plugins / "known_marketplaces.json").write_text(json.dumps(conocidos), encoding="utf-8")

    def ejecutar(self, args, cwd=None):
        self.llamadas.append(tuple(args))
        if args and args[-1] == "--autoprueba":
            return self.respuestas.get("autoprueba", (0, "autoprueba ok: 3 términos\n"))
        if self.git_real and args[0] == "git":
            resultado = subprocess.run(args, cwd=cwd or self.cwd, capture_output=True, env=entorno_sin_git())
            return resultado.returncode, resultado.stdout.decode("utf-8", "replace") + resultado.stderr.decode("utf-8", "replace")
        for largo in range(len(args), 0, -1):
            clave = tuple(args[:largo])
            if clave in self.respuestas:
                valor = self.respuestas[clave]
                return (None, "") if valor is None else valor
        return (None, "")

    def which(self, nombre):
        return self.rutas.get(nombre)

    def medir(self, ruta):
        return self.tiempos.get(ruta, 50.0)


class Escenario:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="doctor-"))
        return self

    def clon(self, hooks=None):
        raiz = self.base / "clon"
        raiz.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=raiz, env=entorno_sin_git(), check=True)
        (raiz / ".claude-plugin").mkdir()
        (raiz / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"name": "odd-workspace-template"}), encoding="utf-8")
        if hooks:
            subprocess.run(["git", "config", "core.hooksPath", hooks], cwd=raiz, env=entorno_sin_git(), check=True)
        return raiz

    def instancia(self, local=None, capas=("sql",)):
        raiz = self.base / "instancia"
        (raiz / "tickets" / "T-1").mkdir(parents=True)
        layers = {capa: {"extensions": [".%s" % capa]} for capa in capas}
        (raiz / "workspace.config.json").write_text(json.dumps({"schema_version": 1, "layers": layers}), encoding="utf-8")
        if local is not None:
            (raiz / "workspace.local.json").write_bytes(local.encode("utf-8") if isinstance(local, str) else local)
        return raiz

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_forzar_borrado)


def correr(argv, ctx):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        codigo = d().principal(argv, ctx)
    return codigo, salida.getvalue()


def por_id(ctx):
    return {r.id: r for r in d().diagnosticar(ctx)}


def test_maquina_sana_sale_cero():
    with Escenario() as e:
        ctx = Falso(e.base)
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida
        estados = {r.id: r.estado for r in d().diagnosticar(ctx)}
        assert set(estados.values()) <= {"OK", "NO APLICA"}, estados


def test_fuera_de_un_clon_los_items_del_repo_no_aplican():
    with Escenario() as e:
        r = por_id(Falso(e.base))
        assert r["repo-hooks"].estado == "NO APLICA" and r["lista-negra"].estado == "NO APLICA", r


def test_clon_sin_hookspath_es_falta_y_arreglar_lo_configura():
    with Escenario() as e:
        raiz = e.clon()
        ctx = Falso(e.base, git_real=True, cwd=raiz)
        assert por_id(ctx)["repo-hooks"].estado == "FALTA"
        codigo, salida = correr(["--arreglar", "repo-hooks"], ctx)
        assert codigo == 0, salida
        configurado = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=raiz, env=entorno_sin_git(), capture_output=True).stdout.decode().strip()
        assert configurado == ".githooks", configurado
        assert por_id(ctx)["repo-hooks"].estado == "OK"


def test_clon_con_hookspath_es_ok():
    with Escenario() as e:
        raiz = e.clon(hooks=".githooks")
        assert por_id(Falso(e.base, git_real=True, cwd=raiz))["repo-hooks"].estado == "OK"


def test_lista_negra_que_falla_la_autoprueba_es_falta_sin_arreglo_automatico():
    with Escenario() as e:
        raiz = e.clon(hooks=".githooks")
        ctx = Falso(e.base, git_real=True, cwd=raiz, respuestas={"autoprueba": (2, "BARRIDO BLOQUEADO: no existe la lista negra (x)\n")})
        r = por_id(ctx)["lista-negra"]
        assert r.estado == "FALTA" and "no existe la lista negra" in r.detalle and r.comando is None and r.ayuda, r


def leer_local(raiz):
    return (raiz / "workspace.local.json").read_bytes()


def test_fuera_de_una_instancia_plugin_root_no_aplica():
    with Escenario() as e:
        r = por_id(Falso(e.base))["plugin-root"]
        assert r.estado == "NO APLICA" and "workspace.config.json" in r.detalle, r


def test_instancia_sin_plugin_root_es_falta_y_arreglar_lo_anota_conservando_el_resto():
    with Escenario() as e:
        raiz = e.instancia(json.dumps({"repos": {"db": {"path": "C:/repos/db"}}, "extra": "ñ"}, ensure_ascii=False))
        ctx = Falso(e.base, cwd=raiz / "tickets" / "T-1")
        r = por_id(ctx)["plugin-root"]
        assert r.estado == "FALTA" and "plugin_root" in r.detalle and r.arreglo is not None, r
        codigo, salida = correr([], ctx)
        assert codigo == 1 and "arreglo: --arreglar plugin-root" in salida, salida
        codigo, salida = correr(["--arreglar", "plugin-root"], ctx)
        assert codigo == 0, salida
        crudo = leer_local(raiz)
        assert not crudo.startswith(b"\xef\xbb\xbf"), crudo[:3]
        datos = json.loads(crudo.decode("utf-8"))
        assert datos == {"repos": {"db": {"path": "C:/repos/db"}}, "extra": "ñ", "plugin_root": str(ctx.plugin)}, datos
        assert por_id(ctx)["plugin-root"].estado == "OK"
        assert "plugin-root: OK" in salida, salida


def test_sin_workspace_local_arreglar_lo_crea():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz)
        assert por_id(ctx)["plugin-root"].estado == "FALTA"
        codigo, salida = correr(["--arreglar", "plugin-root"], ctx)
        assert codigo == 0, salida
        assert json.loads(leer_local(raiz).decode("utf-8")) == {"plugin_root": str(ctx.plugin)}


def test_plugin_root_viejo_o_de_otra_copia_es_falta_y_arreglar_lo_corrige():
    with Escenario() as e:
        otra = e.base / "otra-version"
        (otra / "scripts").mkdir(parents=True)
        (otra / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        ctx = Falso(e.base)
        for anotado, rastro in ((str(e.base / "borrada"), "no existe"), (str(otra), "otra copia")):
            raiz = e.instancia(json.dumps({"plugin_root": anotado}))
            ctx.cwd = raiz
            r = por_id(ctx)["plugin-root"]
            assert r.estado == "FALTA" and rastro in r.detalle and anotado in r.detalle, (anotado, r)
            codigo, salida = correr(["--arreglar", "plugin-root"], ctx)
            assert codigo == 0, salida
            assert json.loads(leer_local(raiz).decode("utf-8")) == {"plugin_root": str(ctx.plugin)}
            shutil.rmtree(raiz, onexc=_forzar_borrado)


def enlazar(enlace, destino):
    try:
        os.symlink(destino, enlace, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        return subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], capture_output=True).returncode == 0
    return False


def test_plugin_root_que_apunta_al_mismo_plugin_con_otra_forma_es_ok():
    with Escenario() as e:
        ctx = Falso(e.base)
        formas = [os.path.join(str(ctx.plugin), "scripts", os.pardir) + os.sep]
        if os.path.isdir(str(ctx.plugin).upper()):
            formas.append(str(ctx.plugin).upper() + os.sep)
        enlace = e.base / "enlace-al-plugin"
        if enlazar(enlace, ctx.plugin):
            formas.append(str(enlace))
        try:
            for forma in formas:
                raiz = e.instancia(json.dumps({"plugin_root": forma}))
                ctx.cwd = raiz
                r = por_id(ctx)["plugin-root"]
                assert r.estado == "OK", (forma, r)
                shutil.rmtree(raiz, onexc=_forzar_borrado)
        finally:
            if os.path.lexists(enlace):
                (os.rmdir if os.name == "nt" else os.unlink)(enlace)


def test_plugin_root_con_otras_mayusculas_es_ok_aunque_la_plataforma_no_las_pliegue():
    with Escenario() as e:
        ctx = Falso(e.base)
        otra = str(ctx.plugin).swapcase()
        if not os.path.isdir(otra):
            print("      (el disco distingue mayúsculas: prueba omitida)")
            return
        raiz = e.instancia(json.dumps({"plugin_root": otra}))
        ctx.cwd = raiz
        normcase, realpath = os.path.normcase, os.path.realpath
        os.path.normcase, os.path.realpath = posixpath.normcase, os.path.abspath
        try:
            r = por_id(ctx)["plugin-root"]
        finally:
            os.path.normcase, os.path.realpath = normcase, realpath
        assert r.estado == "OK" and r.arreglo is None, r


def test_con_la_copia_de_emergencia_plugin_root_es_ok():
    with Escenario() as e:
        raiz = e.instancia()
        (raiz / ".claude" / "plugin" / "scripts").mkdir(parents=True)
        (raiz / ".claude" / "plugin" / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        r = por_id(Falso(e.base, cwd=raiz))["plugin-root"]
        assert r.estado == "OK" and ".claude/plugin" in r.detalle, r


def test_workspace_local_ilegible_es_falta_sin_arreglo_y_no_se_pisa():
    for malo in ("{no es json", "[1, 2]"):
        with Escenario() as e:
            raiz = e.instancia(malo)
            ctx = Falso(e.base, cwd=raiz)
            r = por_id(ctx)["plugin-root"]
            assert r.estado == "FALTA" and r.arreglo is None and r.comando is None and r.ayuda, (malo, r)
            codigo, salida = correr(["--arreglar", "plugin-root"], ctx)
            assert codigo == 2, salida
            assert leer_local(raiz) == malo.encode("utf-8")


def test_la_instancia_sale_de_la_carpeta_de_la_sesion():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base)
        ctx.entorno = {"CLAUDE_PROJECT_DIR": str(raiz / "tickets" / "T-1")}
        assert por_id(ctx)["plugin-root"].estado == "FALTA"


DEL_CACHE = (".claude", "plugins", "cache", "odd-workspace-template", "odd-ws", "0.13.0")


def plugin_bajo_el_home(ctx):
    plugin = ctx.home.joinpath(*DEL_CACHE)
    (plugin / "scripts").mkdir(parents=True, exist_ok=True)
    (plugin / "scripts" / "reglas.py").write_text("", encoding="utf-8")
    ctx.plugin = plugin
    return plugin


def test_plugin_root_bajo_el_home_se_muestra_desde_la_virgulilla_y_el_archivo_no_cambia():
    with Escenario() as e:
        ctx = Falso(e.base)
        plugin = plugin_bajo_el_home(ctx)
        esperado = "plugin_root = " + os.path.join("~", *DEL_CACHE)
        for anotado in (str(plugin), plugin.as_posix()):
            local = json.dumps({"plugin_root": anotado})
            raiz = e.instancia(local)
            ctx.cwd = raiz
            r = por_id(ctx)["plugin-root"]
            assert r.estado == "OK" and r.detalle == esperado and str(ctx.home) not in r.detalle, (anotado, r)
            assert linea_del_doctor(ctx, "plugin-root").split(None, 2)[1:] == ["OK", esperado]
            assert leer_local(raiz) == local.encode("utf-8")
            shutil.rmtree(raiz, onexc=_forzar_borrado)


def test_plugin_root_fuera_del_home_se_muestra_absoluta_como_antes():
    with Escenario() as e:
        ctx = Falso(e.base)
        vecino = e.base / (ctx.home.name + "-vecino") / "plugin"
        (vecino / "scripts").mkdir(parents=True)
        (vecino / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        for plugin in (ctx.plugin, vecino):
            ctx.plugin = plugin
            raiz = e.instancia(json.dumps({"plugin_root": str(plugin)}))
            ctx.cwd = raiz
            r = por_id(ctx)["plugin-root"]
            assert r.estado == "OK" and r.detalle == f"plugin_root = {plugin}", r
            assert linea_del_doctor(ctx, "plugin-root").split(None, 2)[1:] == ["OK", f"plugin_root = {plugin}"]
            shutil.rmtree(raiz, onexc=_forzar_borrado)


def test_bajo_el_home_los_falta_de_plugin_root_y_su_arreglo_siguen_con_la_ruta_absoluta():
    with Escenario() as e:
        ctx = Falso(e.base)
        plugin = plugin_bajo_el_home(ctx)
        otra = ctx.home / ".claude" / "plugins" / "cache" / "odd-workspace-template" / "odd-ws" / "0.12.1"
        (otra / "scripts").mkdir(parents=True)
        (otra / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        borrada = ctx.home / ".claude" / "plugins" / "cache" / "odd-workspace-template" / "odd-ws" / "0.11.0"
        for anotado, detalle in ((str(borrada), f"plugin_root = {borrada} no existe (una versión desinstalada o movida)"),
                                 (str(otra), f"plugin_root = {otra} es otra copia del plugin; el doctor corre desde {plugin}")):
            raiz = e.instancia(json.dumps({"plugin_root": anotado}))
            ctx.cwd = raiz
            r = por_id(ctx)["plugin-root"]
            assert r.estado == "FALTA" and r.detalle == detalle, (anotado, r)
            codigo, salida = correr(["--arreglar", "plugin-root"], ctx)
            local = raiz / "workspace.local.json"
            assert codigo == 0 and salida.splitlines() == [
                f"escribiendo: plugin_root = {plugin} en {local}",
                "plugin-root: OK — plugin_root = " + os.path.join("~", *DEL_CACHE)], salida
            assert json.loads(leer_local(raiz).decode("utf-8")) == {"plugin_root": str(plugin)}
            shutil.rmtree(raiz, onexc=_forzar_borrado)
        raiz = e.instancia()
        ctx.cwd = raiz
        r = por_id(ctx)["plugin-root"]
        assert r.estado == "FALTA" and r.detalle == f"plugin_root sin anotar en {raiz / 'workspace.local.json'}: el pre-commit de la " \
            "instancia no encuentra el plugin", r


def pw():
    return importlib.import_module("plantilla_writer")


def writer_de(raiz, capa):
    return raiz / ".claude" / "agents" / ("writer-%s.md" % capa)


def poner_writer(raiz, capa, texto, crlf=False):
    ruta = writer_de(raiz, capa)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes((texto.replace("\n", "\r\n") if crlf else texto).encode("utf-8"))
    return ruta


def plantilla_sin_limites():
    texto = re.sub(r"<!-- instancia:limites -->\n.*?<!-- /instancia:limites -->\n", "", pw().leer_plantilla(), count=1, flags=re.S)
    return re.sub(r"(?m)^odd-ws-plantilla: \d+$", "odd-ws-plantilla: 0", texto, count=1)


def test_fuera_de_una_instancia_no_hay_items_de_writers():
    with Escenario() as e:
        ids = list(por_id(Falso(e.base)))
        assert not [i for i in ids if i.startswith("writer")], ids


def test_writer_que_falta_es_aviso_con_arreglo_y_no_hace_fallar_la_salida():
    with Escenario() as e:
        raiz = e.instancia(json.dumps({"plugin_root": str(e.base / "plugin-instalado")}))
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["writer-sql"]
        assert r.estado == "AVISO" and ".claude/agents/writer-sql.md" in r.detalle and r.arreglo is not None, r
        codigo, salida = correr([], ctx)
        assert codigo == 0 and "arreglo: --arreglar writer-sql" in salida, salida


def test_arreglar_crea_el_writer_que_falta():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz / "tickets" / "T-1")
        codigo, salida = correr(["--arreglar", "writer-sql"], ctx)
        assert codigo == 0 and "writer-sql: OK" in salida, salida
        crudo = writer_de(raiz, "sql").read_bytes()
        assert crudo.decode("utf-8") == pw().generar("sql") and b"\r\n" not in crudo and not crudo.startswith(b"\xef\xbb\xbf")
        assert por_id(ctx)["writer-sql"].estado == "OK"


def test_arreglar_va_de_a_un_writer():
    with Escenario() as e:
        raiz = e.instancia(capas=("sql", "web"))
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)
        assert r["writer-sql"].estado == "AVISO" and r["writer-web"].estado == "AVISO", r
        codigo, salida = correr(["--arreglar", "writer-web"], ctx)
        assert codigo == 0, salida
        assert writer_de(raiz, "web").is_file() and not writer_de(raiz, "sql").exists()
        r = por_id(ctx)
        assert r["writer-web"].estado == "OK" and r["writer-sql"].estado == "AVISO", r


def test_writer_al_dia_es_ok_aunque_el_checkout_lo_deje_en_crlf():
    with Escenario() as e:
        raiz = e.instancia()
        poner_writer(raiz, "sql", pw().generar("sql"), crlf=True)
        r = por_id(Falso(e.base, cwd=raiz))["writer-sql"]
        assert r.estado == "OK" and "v%d" % pw().version() in r.detalle, r


def test_writer_atrasado_es_aviso_y_arreglar_lo_regenera_conservando_lo_de_la_instancia():
    with Escenario() as e:
        raiz = e.instancia()
        viejo = pw().generar("sql", plantilla=plantilla_sin_limites())
        viejo = re.sub(r"(<!-- instancia:identidad -->\n).*?(<!-- /instancia:identidad -->)",
                       lambda m: m.group(1) + "Identidad propia.\n" + m.group(2), viejo, count=1, flags=re.S)
        viejo = re.sub(r"(?m)^description:.*$", 'description: "Description propia"', viejo, count=1)
        poner_writer(raiz, "sql", viejo)
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["writer-sql"]
        assert r.estado == "AVISO" and "v0" in r.detalle and "v%d" % pw().version() in r.detalle and r.arreglo, r
        codigo, salida = correr(["--arreglar", "writer-sql"], ctx)
        assert codigo == 0 and "writer-sql: OK" in salida, salida
        nuevo = writer_de(raiz, "sql").read_text(encoding="utf-8")
        assert "Identidad propia.\n" in nuevo and 'description: "Description propia"' in nuevo and "instancia:limites" in nuevo, nuevo


def test_writer_editado_fuera_de_los_bloques_es_falta_sin_arreglo_y_no_se_pisa():
    with Escenario() as e:
        raiz = e.instancia()
        texto = pw().generar("sql").replace("Nunca reviertas", "Revierte si hace falta", 1)
        ruta = poner_writer(raiz, "sql", texto)
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["writer-sql"]
        assert r.estado == "FALTA" and "fuera de los bloques" in r.detalle and r.arreglo is None and r.comando is None and r.ayuda, r
        codigo, salida = correr([], ctx)
        assert codigo == 1, salida
        codigo, salida = correr(["--arreglar", "writer-sql"], ctx)
        assert codigo == 2 and r.ayuda in salida, salida
        assert ruta.read_bytes() == texto.encode("utf-8")


def test_writer_escrito_a_mano_ilegible_o_con_bloques_rotos_es_falta_sin_arreglo():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz)
        casos = (("---\nname: writer-sql\ndescription: \"a mano\"\n---\nEscrito a mano.\n", "plantilla"),
                 (pw().generar("sql").replace("<!-- /instancia:limites -->\n", "", 1), "bloques"))
        for texto, rastro in casos:
            poner_writer(raiz, "sql", texto)
            r = por_id(ctx)["writer-sql"]
            assert r.estado == "FALTA" and rastro in r.detalle and r.arreglo is None and r.ayuda, (rastro, r)
        writer_de(raiz, "sql").write_bytes(b"\xff\xfe")
        r = por_id(ctx)["writer-sql"]
        assert r.estado == "FALTA" and "UTF-8" in r.detalle and r.arreglo is None, r


def test_capa_cuyo_nombre_no_sirve_para_un_writer_es_aviso_sin_arreglo():
    with Escenario() as e:
        raiz = e.instancia(capas=("sql", "C_Sharp"))
        r = por_id(Falso(e.base, cwd=raiz))
        assert r["writer-sql"].estado == "AVISO", r
        malo = r["writer-C_Sharp"]
        assert malo.estado == "AVISO" and malo.arreglo is None and malo.comando is None and "writer-[a-z0-9]" in malo.detalle and malo.ayuda, malo


def test_config_rota_da_un_solo_item_de_writers_en_falta():
    with Escenario() as e:
        raiz = e.instancia()
        (raiz / "workspace.config.json").write_text('{"schema_version": 1, "layers": {}}', encoding="utf-8")
        r = por_id(Falso(e.base, cwd=raiz))
        assert [i for i in r if i.startswith("writer")] == ["writers"], list(r)
        assert r["writers"].estado == "FALTA" and "layers" in r["writers"].detalle and r["writers"].arreglo is None and r["writers"].ayuda, r


def poner(base, relativa, texto):
    ruta = base / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)
    return ruta


def skill_con(nombre, cabecera="", cuerpo=None):
    marca = "CENTINELA %s 2026-10-29" % nombre if cuerpo is None else cuerpo
    return "---\nname: %s\n%s---\n%s\nReglas.\n" % (nombre, cabecera, marca)


def agente_con(nombre, cabecera):
    return "---\nname: %s\ndescription: x\n%s---\nCuerpo.\n" % (nombre, cabecera)


def instancia_sana(e):
    raiz = e.instancia(json.dumps({"plugin_root": str(e.base / "plugin-instalado")}))
    poner(raiz, ".claude/agents/writer-sql.md", pw().generar("sql"))
    poner(raiz, ".claude/skills/criterios/SKILL.md", "﻿" + skill_con("criterios").replace("\n", "\r\n"))
    poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql"))
    return raiz


def test_fuera_de_una_instancia_no_hay_items_de_agentes():
    with Escenario() as e:
        ids = list(por_id(Falso(e.base)))
        assert not [i for i in ids if i.startswith("agentes")], ids


def test_instancia_sin_agentes_los_items_de_agentes_no_aplican():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)
        assert r["agentes-skills"].estado == "NO APLICA" and r["agentes-hooks"].estado == "NO APLICA", r
        poner(raiz, ".claude/agents/solo.md", agente_con("solo", "tools: Read\n"))
        r = por_id(ctx)
        assert r["agentes-skills"].estado == "NO APLICA" and "ningún agente" in r["agentes-skills"].detalle, r
        assert r["agentes-hooks"].estado == "OK", r


def test_writer_con_sus_skills_en_la_instancia_es_ok_y_sale_cero():
    with Escenario() as e:
        ctx = Falso(e.base, cwd=instancia_sana(e))
        r = por_id(ctx)
        assert r["agentes-skills"].estado == "OK" and "2" in r["agentes-skills"].detalle, r["agentes-skills"]
        assert r["agentes-hooks"].estado == "OK", r["agentes-hooks"]
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida


def test_skill_precargada_que_no_existe_es_falta_sin_arreglo():
    with Escenario() as e:
        raiz = instancia_sana(e)
        (raiz / ".claude/skills/capa-sql/SKILL.md").unlink()
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["agentes-skills"]
        assert r.estado == "FALTA" and "writer-sql.md" in r.detalle and ".claude/skills/capa-sql/SKILL.md" in r.detalle, r
        assert "criterios" not in r.detalle and r.arreglo is None and r.comando is None and r.ayuda, r
        codigo, salida = correr([], ctx)
        assert codigo == 1, salida
        codigo, salida = correr(["--arreglar", "agentes-skills"], ctx)
        assert codigo == 2 and r.ayuda in salida, salida


def test_skill_precargada_que_claude_code_saltea_es_falta():
    casos = (("paths: src/**\n", "paths:"), ("paths:\n  - src/**\n", "paths:"),
             ("disable-model-invocation: true\n", "disable-model-invocation"),
             ("disable-model-invocation: True  # manual\n", "disable-model-invocation"))
    with Escenario() as e:
        raiz = instancia_sana(e)
        ctx = Falso(e.base, cwd=raiz)
        for cabecera, rastro in casos:
            for texto in (skill_con("capa-sql", cabecera), "﻿" + skill_con("capa-sql", cabecera).replace("\n", "\r\n")):
                poner(raiz, ".claude/skills/capa-sql/SKILL.md", texto)
                r = por_id(ctx)["agentes-skills"]
                assert r.estado == "FALTA" and rastro in r.detalle and "capa-sql" in r.detalle and "criterios" not in r.detalle, (texto, r)


def test_skill_que_no_lo_declara_en_el_frontmatter_se_precarga():
    casos = ("disable-model-invocation: false\n", "metadata:\n  paths: src/**\n", "# paths: src/**\n",
             "user-invocable: false\n")
    with Escenario() as e:
        raiz = instancia_sana(e)
        ctx = Falso(e.base, cwd=raiz)
        for cabecera in casos:
            poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql", cabecera) + "paths: fuera del frontmatter\n")
            r = por_id(ctx)["agentes-skills"]
            assert r.estado == "OK", (cabecera, r)


def test_criterios_y_capa_sin_su_centinela_es_aviso_y_no_hace_fallar():
    cuerpos = ("Sin marca.", "CENTINELA capa-sql-extra 2026-10-29", "La línea CENTINELA capa-sql va suelta.", "CENTINELA capa-sqlx 2026-10-29")
    with Escenario() as e:
        raiz = instancia_sana(e)
        ctx = Falso(e.base, cwd=raiz)
        for cuerpo in cuerpos:
            poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql", cuerpo=cuerpo))
            r = por_id(ctx)["agentes-skills"]
            assert r.estado == "AVISO" and "CENTINELA capa-sql" in r.detalle and "criterios" not in r.detalle and r.ayuda, (cuerpo, r)
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida
        poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql", cuerpo="CENTINELA capa-sql"))
        assert por_id(ctx)["agentes-skills"].estado == "OK"


def test_otras_skills_no_piden_centinela_las_personales_existen_y_las_de_plugins_no_se_verifican():
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner(raiz, ".claude/agents/revisor.md", agente_con("revisor", "skills: [criterios-viejos, 'personal', odd-ws:doctor]\n"))
        poner(raiz, ".claude/skills/criterios-viejos/SKILL.md", skill_con("criterios-viejos", cuerpo="Sin marca."))
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["agentes-skills"]
        assert r.estado == "FALTA" and "revisor.md precarga personal" in r.detalle and "viejos" not in r.detalle, r
        assert "odd-ws:doctor" not in r.detalle, r
        poner(ctx.home, ".claude/skills/personal/SKILL.md", skill_con("personal", cuerpo="Sin marca."))
        r = por_id(ctx)["agentes-skills"]
        assert r.estado == "OK" and "4" in r.detalle and "1 de plugins" in r.detalle, r


def test_agente_o_skill_ilegible_es_falta():
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner(raiz, ".claude/skills/capa-sql/SKILL.md", b"---\nname: capa-sql\n---\n\xff\xfe\n")
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["agentes-skills"]
        assert r.estado == "FALTA" and "writer-sql.md: capa-sql no se puede leer como UTF-8" in r.detalle, r
        poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql"))
        poner(raiz, ".claude/agents/roto.md", b"---\nname: roto\nskills: [x]\n---\n\xff\xfe\n")
        r = por_id(ctx)
        assert r["agentes-skills"].estado == "FALTA" and "roto.md" in r["agentes-skills"].detalle and "UTF-8" in r["agentes-skills"].detalle, r
        assert r["agentes-hooks"].estado == "OK", r


def test_agente_con_hooks_en_el_frontmatter_es_aviso_sin_arreglo():
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner(raiz, ".claude/agents/revisor.md", agente_con("revisor", "hooks:\n  PreToolUse: []\n"))
        poner(raiz, ".claude/agents/otro.md", agente_con("otro", "metadata:\n  hooks: x\n# hooks: no\n") + "hooks: en el cuerpo\n")
        poner(raiz, ".claude/agents/suelto.md", "Sin frontmatter.\nhooks: en el cuerpo\n---\nMás.\n")
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["agentes-hooks"]
        assert r.estado == "AVISO" and "revisor.md" in r.detalle and "otro.md" not in r.detalle and "suelto.md" not in r.detalle, r
        assert r.arreglo is None and r.comando is None and "confianza" in r.ayuda and "-p" in r.ayuda, r
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida


def test_el_plugin_del_contexto_real_es_la_carpeta_del_plugin():
    ctx = d().Contexto()
    assert ctx.plugin == AQUI.parent and (ctx.plugin / "scripts" / "reglas.py").is_file(), ctx.plugin
    assert ctx.entorno is os.environ


def test_python3_lento_por_el_alias_es_aviso_con_la_ayuda():
    with Escenario() as e:
        r = por_id(Falso(e.base, tiempos={PYTHON_PATH: 214.0}))["python"]
        assert r.estado == "AVISO" and "214" in r.detalle and "python3" in r.detalle, r
        assert "WindowsApps" in r.ayuda and "python3.exe" in r.ayuda, r


def test_python3_que_resuelve_al_mismo_interprete_es_ok():
    with Escenario() as e:
        ctx = Falso(e.base, which={"python3": PYTHON_REAL}, respuestas={(PYTHON_REAL, "-c"): (0, "Python 3.14.3\n")})
        r = por_id(ctx)["python"]
        assert (r.estado, r.detalle) == ("OK", "Python 3.14.3 (%s)" % PYTHON_REAL), r


def test_con_python_y_python3_sanos_el_item_da_lo_mismo_que_antes():
    with Escenario() as e:
        ctx = Falso(e.base, which={"python": PYTHON_PATH, "python3": PYTHON_PATH},
                    respuestas={(PYTHON_PATH, "--version"): (0, "Python 3.14.3\n"), (PYTHON_PATH, "-c"): (0, "Python 3.14.3\n")})
        r = por_id(ctx)["python"]
        assert (r.id, r.estado, r.detalle, r.comando, r.ayuda) == ("python", "OK", "Python 3.14.3: arranca en 50 ms", None, ""), r


def test_python3_sano_se_prueba_corriendo_python3_c_y_no_hace_falta_python():
    with Escenario() as e:
        ctx = Falso(e.base, which={"python": None})
        r = por_id(ctx)["python"]
        assert r.estado == "OK", r
        sondas = [llamada for llamada in ctx.llamadas if llamada[0] == PYTHON_PATH]
        assert len(sondas) == 1 and sondas[0][1] == "-c" and "sys.version_info" in sondas[0][2], ctx.llamadas


def test_python3_ausente_es_falta_aunque_haya_python_y_dice_como_tenerlo_en_windows():
    with Escenario() as e:
        ctx = Falso(e.base, which={"python3": None, "python": PYTHON_PATH}, respuestas={(PYTHON_PATH, "--version"): (0, "Python 3.14.3\n")})
        r = por_id(ctx)["python"]
        assert r.estado == "FALTA" and "python3 no está en el PATH" in r.detalle, r
        assert "install manager" in r.ayuda and "Microsoft Store" in r.ayuda and "instalador clásico" in r.ayuda, r


def test_en_mac_y_linux_la_ayuda_de_python3_es_instalar_python_3():
    with Escenario() as e:
        ctx = Falso(e.base, which={"python3": None})
        ctx.windows = False
        r = por_id(ctx)["python"]
        assert r.estado == "FALTA" and "Python 3" in r.ayuda and "install manager" not in r.ayuda, r


def test_python3_que_no_corre_con_argumentos_es_falta_como_el_alias_de_la_store():
    with Escenario() as e:
        ctx = Falso(e.base, which={"python3": ALIAS_DE_LA_STORE}, respuestas={(ALIAS_DE_LA_STORE,): (9009, SIN_PYTHON)})
        r = por_id(ctx)["python"]
        assert r.estado == "FALTA" and ALIAS_DE_LA_STORE in r.detalle and "no corre" in r.detalle, r
        assert "install manager" in r.ayuda, r
        assert [llamada[1] for llamada in ctx.llamadas if llamada[0] == ALIAS_DE_LA_STORE] == ["-c"], ctx.llamadas
        sin_version = Falso(e.base / "b", which={"python3": ALIAS_DE_LA_STORE}, respuestas={(ALIAS_DE_LA_STORE,): (0, SIN_PYTHON)})
        assert por_id(sin_version)["python"].estado == "FALTA"
        sin_ejecutar = por_id(Falso(e.base / "c", which={"python3": ALIAS_DE_LA_STORE}, respuestas={(ALIAS_DE_LA_STORE,): None}))["python"]
        assert (sin_ejecutar.estado, sin_ejecutar.detalle) == ("FALTA", f"{ALIAS_DE_LA_STORE} no corre: no se pudo ejecutar"), sin_ejecutar


def test_python3_que_da_la_version_pero_sale_con_error_es_falta():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={(PYTHON_PATH, "-c"): (1, "Python 3.14.3\nFatal Python error: init_import_site\n")})
        r = por_id(ctx)["python"]
        assert r.estado == "FALTA" and PYTHON_PATH in r.detalle and "no corre" in r.detalle, r


def test_python3_anterior_a_3_7_es_falta_y_3_7_alcanza():
    with Escenario() as e:
        r = por_id(Falso(e.base, respuestas={(PYTHON_PATH, "-c"): (0, "Python 3.6.9\n")}))["python"]
        assert r.estado == "FALTA" and "3.6.9" in r.detalle and "3.7" in r.detalle, r
        assert por_id(Falso(e.base / "b", respuestas={(PYTHON_PATH, "-c"): (0, "Python 3.7.0\n")}))["python"].estado == "OK"


PYTHON_CLASICO = "C:/Python312/python.exe"
PYTHON3_SANO = "C:/py/bin/python3.exe"


def item_python_con_hosts(e, hosts, windows=True, **extra):
    raiz = e.instancia() if hosts is None else con_hosts(e.instancia(), hosts)
    ctx = Falso(e.base, cwd=raiz, **extra)
    ctx.windows = windows
    return por_id(ctx)["python"], [llamada[0] for llamada in ctx.llamadas if len(llamada) > 1 and llamada[1] == "-c"]


def test_en_windows_con_codex_y_el_instalador_clasico_revisa_python_y_no_el_alias_de_python3():
    with Escenario() as e:
        r, sondas = item_python_con_hosts(e, ["codex"], which={"python3": ALIAS_DE_LA_STORE, "python": PYTHON_CLASICO},
                                          respuestas={(ALIAS_DE_LA_STORE,): (9009, SIN_PYTHON), (PYTHON_CLASICO, "-c"): (0, "Python 3.12.4\n")})
        assert (r.estado, r.detalle) == ("OK", "Python 3.12.4: arranca en 50 ms"), r
        assert sondas == [PYTHON_CLASICO], sondas


def test_en_windows_con_codex_sin_python_es_falta_aunque_python3_este_sano():
    with Escenario() as e:
        r, sondas = item_python_con_hosts(e, ["codex"], which={"python3": PYTHON3_SANO, "python": None},
                                          respuestas={(PYTHON3_SANO, "-c"): (0, "Python 3.12.4\n")})
        assert (r.estado, r.detalle) == ("FALTA", "python no está en el PATH: los hooks de codex lo llaman por nombre"), r
        assert "python.exe to PATH" in r.ayuda and "Microsoft Store" in r.ayuda, r
        assert sondas == [], sondas


def test_en_windows_con_los_dos_hosts_revisa_python3_y_python_y_nombra_al_host_que_no_arranca():
    with Escenario() as e:
        r, sondas = item_python_con_hosts(e, ["claude-code", "codex"], which={"python3": PYTHON3_SANO, "python": PYTHON_CLASICO},
                                          respuestas={(PYTHON3_SANO, "-c"): (0, "Python 3.14.3\n"), (PYTHON_CLASICO, "-c"): (0, "Python 3.12.4\n")})
        assert (r.estado, r.detalle) == ("OK", "python3: Python 3.14.3: arranca en 50 ms; python: Python 3.12.4: arranca en 50 ms"), r
        assert sondas == [PYTHON3_SANO, PYTHON_CLASICO], sondas
    with Escenario() as e:
        r, _ = item_python_con_hosts(e, ["claude-code", "codex"], which={"python3": PYTHON3_SANO, "python": None},
                                     respuestas={(PYTHON3_SANO, "-c"): (0, "Python 3.14.3\n")})
        assert r.estado == "FALTA" and "python no está en el PATH: los hooks de codex" in r.detalle and "claude-code" not in r.detalle, r
    with Escenario() as e:
        r, _ = item_python_con_hosts(e, ["claude-code", "codex"], which={"python3": ALIAS_DE_LA_STORE, "python": PYTHON_CLASICO},
                                     respuestas={(ALIAS_DE_LA_STORE,): (9009, SIN_PYTHON), (PYTHON_CLASICO, "-c"): (0, "Python 3.12.4\n")})
        assert r.estado == "FALTA" and "los hooks de claude-code no arrancan" in r.detalle and "codex" not in r.detalle, r
        assert "python: Python 3.12.4" in r.detalle and "install manager" in r.ayuda, r


def test_fuera_de_windows_con_codex_declarado_se_sigue_revisando_solo_python3():
    with Escenario() as e:
        r, sondas = item_python_con_hosts(e, ["codex"], windows=False, which={"python3": PYTHON3_SANO, "python": None},
                                          respuestas={(PYTHON3_SANO, "-c"): (0, "Python 3.9.6\n")})
        assert (r.estado, sondas) == ("OK", [PYTHON3_SANO]), (r, sondas)
    with Escenario() as e:
        r, sondas = item_python_con_hosts(e, ["claude-code", "codex"], windows=False, which={"python3": None, "python": PYTHON_CLASICO})
        assert (r.estado, r.detalle) == ("FALTA", "python3 no está en el PATH: los hooks de claude-code, codex lo llaman por nombre"), r
        assert sondas == [] and "Python 3" in r.ayuda, (r, sondas)


def test_solo_con_claude_code_o_con_hosts_invalido_el_item_python_es_el_de_fuera_de_una_instancia():
    for hosts in (None, ["claude-code"], "codex", []):
        with Escenario() as e:
            afuera = por_id(Falso(e.base / "afuera", which={"python3": None}))["python"]
            r, sondas = item_python_con_hosts(e, hosts, which={"python3": None, "python": None})
            assert r == afuera, (hosts, r, afuera)
            assert r.detalle == "python3 no está en el PATH: los hooks lo llaman por nombre", r


def test_sin_credential_helper_es_aviso_opcional_y_sin_git_es_falta():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={("git", "config", "--get", "credential.helper"): (1, "")})
        r = por_id(ctx)["git-credenciales"]
        assert r.estado == "AVISO" and "opcional" in r.detalle and "empujar" in r.detalle, r
        sin_git = Falso(e.base / "b", respuestas={("git", "config", "--get", "credential.helper"): None})
        assert por_id(sin_git)["git-credenciales"].estado == "FALTA"


def test_claude_viejo_es_falta_y_version_ilegible_es_aviso():
    with Escenario() as e:
        assert por_id(Falso(e.base, respuestas={("claude", "--version"): (0, "2.1.200 (Claude Code)\n")}))["claude"].estado == "FALTA"
        assert por_id(Falso(e.base / "b", respuestas={("claude", "--version"): (0, "sin numeros\n")}))["claude"].estado == "AVISO"


def test_claude_anterior_a_2_1_295_es_aviso_y_no_hace_fallar_la_salida():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={("claude", "--version"): (0, "2.1.284 (Claude Code)\n")})
        r = por_id(ctx)["claude"]
        assert (r.estado, r.detalle) == ("AVISO", "2.1.284: un hook que no arranca deja pasar"), r
        codigo, salida = correr([], ctx)
        assert codigo == 0 and "un hook que no arranca deja pasar" in salida and "2.1.295" in salida, salida


def test_marketplace_no_registrado_es_falta_con_arreglo_automatico():
    with Escenario() as e:
        r = por_id(Falso(e.base, marketplace=False))["marketplace"]
        assert r.estado == "FALTA" and r.comando[:4] == ["claude", "plugin", "marketplace", "add"], r
        assert por_id(Falso(e.base / "b", marketplace=None))["marketplace"].estado == "FALTA"


def test_gentle_ai_ausente_es_aviso_opcional_y_rdd_y_telemetria_no_aplican():
    with Escenario() as e:
        r = por_id(Falso(e.base, respuestas={("gentle-ai",): None}))
        assert r["gentle-ai"].estado == "AVISO" and "opcional" in r["gentle-ai"].detalle, r
        assert r["rdd"].estado == "NO APLICA" and r["telemetria"].estado == "NO APLICA", r


RDD_ENCENDIDO = {("gentle-ai", "review", "mode", "status"): (0, "receipt-driven development: on (decided by default)\n")}
APAGAR_RDD = ("gentle-ai", "review", "mode", "disable")


def test_rdd_encendido_en_una_instancia_con_repo_es_aviso_y_el_arreglo_lo_apaga_solo_en_ese_clon():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz, respuestas={**RDD_ENCENDIDO, ("git", "-C", str(raiz), "rev-parse", "--show-toplevel"): (0, str(raiz) + "\n")})
        r = por_id(ctx)["rdd"]
        assert r.estado == "AVISO" and r.comando == [*APAGAR_RDD, "--scope", "clone", "--cwd", str(raiz)], r
        assert "solo en el clon de esta instancia" in r.ayuda and "tus otros proyectos" in r.ayuda, r.ayuda
        correr(["--arreglar", "rdd"], ctx)
        apagados = [c for c in ctx.llamadas if c[:4] == APAGAR_RDD]
        assert apagados == [(*APAGAR_RDD, "--scope", "clone", "--cwd", str(raiz))], apagados


def test_rdd_encendido_fuera_de_una_instancia_no_aplica_y_no_ofrece_apagarlo():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas=RDD_ENCENDIDO)
        r = por_id(ctx)["rdd"]
        assert r.estado == "NO APLICA" and r.comando is None and "fuera de una instancia" in r.detalle, r
        codigo, _ = correr(["--arreglar", "rdd"], ctx)
        assert codigo == 0 and not [c for c in ctx.llamadas if c[:4] == APAGAR_RDD], ctx.llamadas


def test_rdd_encendido_en_una_instancia_sin_repo_git_es_aviso_sin_arreglo_automatico():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz, respuestas=RDD_ENCENDIDO)
        r = por_id(ctx)["rdd"]
        assert r.estado == "AVISO" and r.comando is None and r.arreglo is None, r
        assert "no está en un repo git" in r.ayuda and "por clon" in r.ayuda, r.ayuda
        codigo, salida = correr(["--arreglar", "rdd"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida and not [c for c in ctx.llamadas if c[:4] == APAGAR_RDD], salida


def test_telemetria_activa_es_aviso():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={("gentle-ai", "telemetry", "status"): (0, "telemetry: enabled\n")})
        assert por_id(ctx)["telemetria"].estado == "AVISO"


def test_engram_viejo_es_aviso_opcional():
    with Escenario() as e:
        r = por_id(Falso(e.base, respuestas={("engram", "version"): (0, "engram 3.4.9\n")}))["engram"]
        assert r.estado == "AVISO" and "3.4.9" in r.detalle and "opcional" in r.detalle, r


def test_jq_ausente_es_aviso_opcional():
    with Escenario() as e:
        r = por_id(Falso(e.base, respuestas={("jq",): None}))["jq"]
        assert r.estado == "AVISO" and "opcional" in r.detalle, r


def test_las_herramientas_opcionales_ausentes_no_hacen_fallar_la_salida():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={
            ("gentle-ai",): None,
            ("engram",): None,
            ("jq",): None,
            ("git", "config", "--get", "credential.helper"): (1, ""),
        })
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida
        assert "0 FALTA" in salida, salida


def test_nunca_pide_help_ni_upgrade_a_gentle_ai():
    with Escenario() as e:
        ctx = Falso(e.base)
        correr([], ctx)
        for llamada in ctx.llamadas:
            assert "--help" not in llamada and "-h" not in llamada, llamada
            if llamada and llamada[0] == "gentle-ai":
                assert llamada in GENTLE_DE_LECTURA, llamada


def test_arreglar_un_item_sin_arreglo_automatico_muestra_la_ayuda_y_sale_dos():
    with Escenario() as e:
        codigo, salida = correr(["--arreglar", "jq"], Falso(e.base, respuestas={("jq",): None}))
        assert codigo == 2 and "scoop install jq" in salida, salida


def test_arreglar_un_id_desconocido_sale_dos():
    with Escenario() as e:
        codigo, salida = correr(["--arreglar", "inventado"], Falso(e.base))
        assert codigo == 2 and "inventado" in salida, salida


def test_arreglar_un_item_que_ya_esta_bien_no_ejecuta_nada():
    with Escenario() as e:
        ctx = Falso(e.base)
        codigo, salida = correr(["--arreglar", "rdd"], ctx)
        assert codigo == 0, salida
        assert not [c for c in ctx.llamadas if c[:4] == ("gentle-ai", "review", "mode", "disable")], ctx.llamadas


def test_los_avisos_no_hacen_fallar_la_salida():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={
            ("gentle-ai", "review", "mode", "status"): (0, "receipt-driven development: on (decided by default)\n"),
            ("gentle-ai", "telemetry", "status"): (0, "telemetry: enabled\n"),
        }, tiempos={PYTHON_PATH: 214.0})
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida
        assert salida.count("AVISO") >= 3, salida


def test_una_falta_hace_fallar_la_salida():
    with Escenario() as e:
        codigo, salida = correr([], Falso(e.base, respuestas={("claude", "--version"): (0, "2.1.200 (Claude Code)\n")}))
        assert codigo == 1, salida


def test_los_subprocesos_corren_sin_claudecode():
    previo = os.environ.get("CLAUDECODE")
    os.environ["CLAUDECODE"] = "1"
    try:
        assert "CLAUDECODE" not in d().entorno_de_subprocesos()
    finally:
        if previo is None:
            del os.environ["CLAUDECODE"]
        else:
            os.environ["CLAUDECODE"] = previo


def test_leer_version():
    assert d().leer_version("gentle-ai 4.2.0") == (4, 2, 0)
    assert d().leer_version("2.1.284 (Claude Code)") == (2, 1, 284)
    assert d().leer_version("jq-1.8.2") == (1, 8, 2)
    assert d().leer_version("sin numeros") is None


NUEVOS = ("config", "instancia-hooks", "instancia-eol", "instancia-plugin", "capas-cobertura", "hooks-apagados", "hooks-de-repos", "hooks-fallas")
CLAVE_PLUGIN = "odd-ws@odd-workspace-template"
ANTES_EN_INSTANCIA = ["repo-hooks", "lista-negra", "plugin-root", "writer-sql", "paquetes", "agentes-skills", "agentes-hooks", "python",
                      "git-credenciales", "claude", "marketplace", "gentle-ai", "rdd", "telemetria", "engram", "jq"]


def git_en(raiz, *args):
    subprocess.run(["git", *args], cwd=raiz, env=entorno_sin_git(), check=True, capture_output=True)


def hooks_path(raiz):
    r = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=raiz, env=entorno_sin_git(), capture_output=True)
    return r.stdout.decode("utf-8").strip()


def instancia_git(e, hooks=None, precommit=True):
    raiz = e.instancia()
    git_en(raiz, "init", "-q")
    if hooks:
        git_en(raiz, "config", "core.hooksPath", hooks)
    if precommit:
        poner(raiz, ".githooks/pre-commit", "#!/bin/sh\n")
    return raiz


def instancia_con_repos(e, local):
    raiz = e.base / "instancia"
    raiz.mkdir()
    config = {"schema_version": 1, "repos": {"db": {}}, "layers": {"sql": {"extensions": [".sql"], "repos": ["db"]}}}
    (raiz / "workspace.config.json").write_text(json.dumps(config), encoding="utf-8")
    if local is not None:
        (raiz / "workspace.local.json").write_text(json.dumps(local), encoding="utf-8")
    return raiz


def poner_settings(raiz, contenido):
    return poner(raiz, ".claude/settings.json", contenido if isinstance(contenido, (str, bytes)) else json.dumps(contenido))


def test_fuera_de_una_instancia_no_hay_items_nuevos_de_instancia():
    with Escenario() as e:
        ids = list(por_id(Falso(e.base)))
        assert not [i for i in ids if i in NUEVOS], ids


def test_los_items_de_antes_conservan_su_orden_y_los_nuevos_van_tras_plugin_root():
    with Escenario() as e:
        raiz = instancia_sana(e)
        ids = [r.id for r in d().diagnosticar(Falso(e.base, cwd=raiz))]
        assert [i for i in ids if i not in NUEVOS] == ANTES_EN_INSTANCIA, ids
        assert ids[ids.index("plugin-root") + 1:ids.index("plugin-root") + 1 + len(NUEVOS)] == list(NUEVOS), ids


PLANTILLA, MAQUINA, INSTANCIA = ENCABEZADOS = ("La plantilla (solo en un clon de odd-workspace-template):", "Tu máquina:", "Esta instancia:")
RESUMEN = re.compile(r"\d+ FALTA, \d+ AVISO")
DE_LA_MAQUINA = ["plugin-root", "python", "git-credenciales", "claude", "marketplace", "gentle-ai", "rdd", "telemetria", "engram", "jq"]
DE_LA_INSTANCIA = ["config", "instancia-hooks", "instancia-eol", "instancia-plugin", "capas-cobertura", "hooks-apagados", "hooks-de-repos", "hooks-fallas",
                   "writer-sql",
                   "paquetes", "agentes-skills", "agentes-hooks"]


def grupos_del_doctor(salida):
    grupos, actual = {}, None
    for linea in salida.splitlines():
        if linea in ENCABEZADOS:
            assert linea not in grupos, salida
            actual = grupos[linea] = []
        elif linea and not linea.startswith(" ") and not RESUMEN.fullmatch(linea):
            assert actual is not None, salida
            actual.append(linea.split(" ", 1)[0])
    return grupos


def imprimir_en_texto(resultados):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        d().imprimir(resultados)
    return salida.getvalue()


def test_la_salida_va_en_grupos_plantilla_maquina_e_instancia_y_el_resumen_queda_al_final():
    with Escenario() as e:
        ctx = Falso(e.base, cwd=instancia_sana(e))
        resultados = d().diagnosticar(ctx)
        lineas = correr([], ctx)[1].splitlines()
        grupos = grupos_del_doctor("\n".join(lineas))
        assert list(grupos.items()) == [(PLANTILLA, ["repo-hooks", "lista-negra"]), (MAQUINA, DE_LA_MAQUINA),
                                        (INSTANCIA, DE_LA_INSTANCIA)], lineas
        assert sorted(sum(grupos.values(), [])) == sorted(r.id for r in resultados), lineas
        assert lineas[0] == PLANTILLA and all(lineas[lineas.index(encabezado) - 1] == "" for encabezado in (MAQUINA, INSTANCIA)), lineas
        faltas, avisos = (sum(r.estado == estado for r in resultados) for estado in ("FALTA", "AVISO"))
        assert lineas[-2:] == ["", f"{faltas} FALTA, {avisos} AVISO"], lineas


def test_las_filas_de_los_hosts_van_a_la_maquina_y_lo_que_derivan_en_la_instancia_queda_en_la_instancia():
    with Escenario() as e:
        raiz = con_hosts(instancia_sana(e), ["claude-code", "codex", "pi"])
        grupos = grupos_del_doctor(correr([], con_hooks_del_plugin(Falso(e.base, cwd=raiz)))[1])
        assert grupos[MAQUINA] == ["plugin-root", "python", "git-credenciales", "claude", "marketplace", "codex", "codex-plugin", "codex-hooks",
                                   "codex-proyecto", "pi", "gentle-shell", "pi-plugin", "pi-confianza", "hooks-host", "gentle-ai", "rdd",
                                   "telemetria", "engram", "jq"], grupos
        assert grupos[INSTANCIA] == DE_LA_INSTANCIA + ["codex-config", "codex-agentes", "pi-agentes"], grupos


def filas_de_maquina_fuera_del_grupo(ctx, raiz, adaptadores):
    nucleo, encontradas = d().NUCLEO, []
    for adaptador in adaptadores:
        version, _ = adaptador.version(ctx, nucleo)
        sin_cli = [r for r in adaptador.chequeos(ctx, raiz, nucleo, nucleo.CLI_DE_OTRO_HOST)
                   if r.estado == nucleo.NO_APLICA and r.detalle.endswith("no está instalado")]
        encontradas += [r.id for r in (version, *sin_cli)]
    fuera = [id for id in encontradas if id not in d().DE_LA_MAQUINA]
    return encontradas, fuera


def test_cada_fila_que_un_host_hace_depender_de_su_cli_esta_en_el_grupo_de_la_maquina():
    hosts = importlib.import_module("odd_ws.hosts")
    adaptadores = [hosts.adaptador(nombre) for nombre in hosts.NOMBRES]
    codex = hosts.adaptador("codex")
    con_ficticia = type("ConFicticia", (), {
        "version": staticmethod(codex.version),
        "chequeos": staticmethod(lambda *args: [*codex.chequeos(*args), d().resultado("codex-ficticio", "NO APLICA", "codex no está instalado")]),
    })
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz)
        encontradas, fuera = filas_de_maquina_fuera_del_grupo(ctx, raiz, adaptadores)
        assert fuera == [], fuera
        assert {"claude", "marketplace", "codex", "codex-proyecto", "pi", "pi-confianza"} <= set(encontradas), encontradas
        assert filas_de_maquina_fuera_del_grupo(ctx, raiz, [con_ficticia])[1] == ["codex-ficticio"]


def test_un_grupo_sin_filas_no_imprime_su_encabezado():
    with Escenario() as e:
        salida = correr([], Falso(e.base))[1]
        assert list(grupos_del_doctor(salida)) == [PLANTILLA, MAQUINA] and INSTANCIA not in salida, salida
    salida = imprimir_en_texto([d().resultado("python", "OK", "Python 3.14.3")])
    assert salida == "Tu máquina:\npython  OK         Python 3.14.3\n\n0 FALTA, 0 AVISO\n", salida


def test_un_id_que_no_es_de_la_plantilla_ni_de_la_maquina_cae_en_la_instancia():
    resultados = [d().resultado("item-nuevo", "AVISO", "algo nuevo", None, "Revisa esto."), d().resultado("jq", "OK", "1.8.2"),
                  d().resultado("repo-hooks", "OK", "core.hooksPath = .githooks")]
    salida = imprimir_en_texto(resultados)
    assert list(grupos_del_doctor(salida).items()) == [(PLANTILLA, ["repo-hooks"]), (MAQUINA, ["jq"]), (INSTANCIA, ["item-nuevo"])], salida
    assert salida.splitlines()[-4:] == ["item-nuevo  AVISO      algo nuevo", " " * 23 + "cómo: Revisa esto.", "", "0 FALTA, 1 AVISO"], salida


def test_las_columnas_se_alinean_con_el_id_mas_largo_de_toda_la_salida():
    largo = "un-item-de-instancia-largo"
    resultados = [d().resultado("repo-hooks", "FALTA", "core.hooksPath = (sin configurar)", ["git", "config", "core.hooksPath", ".githooks"]),
                  d().resultado("jq", "AVISO", "jq no está instalado", None, "scoop install jq."),
                  d().resultado(largo, "AVISO", "falta algo", arreglo=lambda: "escrito")]
    sangria = " " * (len(largo) + 13)
    assert imprimir_en_texto(resultados).splitlines() == [
        PLANTILLA,
        "repo-hooks".ljust(len(largo) + 2) + "FALTA".ljust(11) + "core.hooksPath = (sin configurar)",
        sangria + "arreglo: --arreglar repo-hooks  (git config core.hooksPath .githooks)",
        "",
        MAQUINA,
        "jq".ljust(len(largo) + 2) + "AVISO".ljust(11) + "jq no está instalado",
        sangria + "cómo: scoop install jq.",
        "",
        INSTANCIA,
        largo + "  " + "AVISO".ljust(11) + "falta algo",
        sangria + "arreglo: --arreglar " + largo,
        "",
        "1 FALTA, 2 AVISO",
    ]


def test_cada_fila_sale_con_el_formato_de_antes_y_el_resumen_cuenta_lo_mismo():
    with Escenario() as e:
        ctx = Falso(e.base, cwd=e.instancia(), marketplace=False, respuestas={("jq", "--version"): None})
        resultados = d().diagnosticar(ctx)
        assert {"FALTA", "AVISO"} <= {r.estado for r in resultados} and any(r.comando for r in resultados), resultados
        assert any(r.arreglo for r in resultados) and any(r.ayuda and r.estado == "AVISO" for r in resultados), resultados
        ancho = max(len(r.id) for r in resultados)
        sangria = " " * (ancho + 13)
        codigo, salida = correr([], ctx)
        lineas = salida.splitlines()
        for r in resultados:
            i = lineas.index(f"{r.id:<{ancho}}  {r.estado:<9}  {r.detalle}")
            debajo = []
            if r.estado in ("FALTA", "AVISO"):
                if r.comando:
                    debajo.append(f"{sangria}arreglo: --arreglar {r.id}  ({' '.join(r.comando)})")
                elif r.arreglo:
                    debajo.append(f"{sangria}arreglo: --arreglar {r.id}")
                if r.ayuda:
                    debajo.append(f"{sangria}cómo: {r.ayuda}")
            assert lineas[i + 1:i + 1 + len(debajo)] == debajo and not lineas[i + 1 + len(debajo)].startswith(" "), (r, lineas[i:i + 4])
        faltas, avisos = (sum(r.estado == estado for r in resultados) for estado in ("FALTA", "AVISO"))
        assert codigo == 1 and lineas[-2:] == ["", f"{faltas} FALTA, {avisos} AVISO"], salida


def test_config_con_la_ruta_del_repo_que_existe_es_ok():
    with Escenario() as e:
        repo = e.base / "db"
        repo.mkdir()
        raiz = instancia_con_repos(e, {"repos": {"db": {"path": str(repo)}}})
        r = por_id(Falso(e.base, cwd=raiz))["config"]
        assert r.estado == "OK" and r.arreglo is None and r.comando is None, r


def test_config_sin_repos_es_ok():
    with Escenario() as e:
        r = por_id(Falso(e.base, cwd=e.instancia()))["config"]
        assert r.estado == "OK", r


def test_config_con_la_ruta_de_un_repo_que_falta_es_falta_sin_arreglo_y_writers_no_la_ve():
    for local, rastro in ((None, "falta la ruta del repo 'db'"), ({"repos": {}}, "falta la ruta del repo 'db'"),
                          ({"repos": {"db": {}}}, "falta la ruta del repo 'db'")):
        with Escenario() as e:
            raiz = instancia_con_repos(e, local)
            ctx = Falso(e.base, cwd=raiz)
            r = por_id(ctx)
            assert r["config"].estado == "FALTA" and rastro in r["config"].detalle, (local, r["config"])
            assert r["config"].arreglo is None and r["config"].comando is None, r["config"]
            assert "workspace.local.json" in r["config"].ayuda and "repos" in r["config"].ayuda, r["config"]
            assert r["writer-sql"].estado == "AVISO" and "writers" not in r, "el hueco: writers no ve la ruta"
            codigo, salida = correr([], ctx)
            assert codigo == 1 and "config" in salida and "cómo:" in salida, salida


def test_config_con_la_ruta_de_un_repo_que_no_existe_es_falta_con_su_ruta_en_el_detalle():
    with Escenario() as e:
        ausente = str(e.base / "no-existe")
        raiz = instancia_con_repos(e, {"repos": {"db": {"path": ausente}}})
        r = por_id(Falso(e.base, cwd=raiz))["config"]
        assert r.estado == "FALTA" and "no existe" in r.detalle and ausente in r.detalle, r


def test_config_con_el_prefijo_de_tickets_mal_formado_es_falta_y_uno_valido_es_ok():
    for prefijo, estado in (("S-M", "FALTA"), ("SM", "OK")):
        with Escenario() as e:
            repo = e.base / "db"
            repo.mkdir()
            raiz = instancia_con_repos(e, {"repos": {"db": {"path": str(repo)}}})
            config = json.loads((raiz / "workspace.config.json").read_text(encoding="utf-8"))
            config["tickets"] = {"prefix": prefijo}
            (raiz / "workspace.config.json").write_text(json.dumps(config), encoding="utf-8")
            r = por_id(Falso(e.base, cwd=raiz))["config"]
            assert r.estado == estado, (prefijo, r)
            assert estado == "OK" or "tickets.prefix" in r.detalle, r


def test_config_con_ask_before_commit_u_own_mal_formados_es_falta_y_bien_formados_es_ok():
    casos = (
        (lambda c: c.update(ask_before_commit="si"), "FALTA", "ask_before_commit"),
        (lambda c: c["repos"]["db"].update(own="si"), "FALTA", "repos.db.own"),
        (lambda c: c["repos"]["db"].update(own=True, agent_readonly=True), "FALTA", "own y agent_readonly"),
        (lambda c: (c.update(ask_before_commit=True), c["repos"]["db"].update(own=True)), "OK", ""),
    )
    for cambiar, estado, fragmento in casos:
        with Escenario() as e:
            repo = e.base / "db"
            repo.mkdir()
            raiz = instancia_con_repos(e, {"repos": {"db": {"path": str(repo)}}})
            config = json.loads((raiz / "workspace.config.json").read_text(encoding="utf-8"))
            cambiar(config)
            (raiz / "workspace.config.json").write_text(json.dumps(config), encoding="utf-8")
            r = por_id(Falso(e.base, cwd=raiz))["config"]
            assert r.estado == estado and fragmento in r.detalle, (fragmento, r)


def test_config_arreglar_sin_arreglo_automatico_sale_dos_y_no_toca_nada():
    with Escenario() as e:
        raiz = instancia_con_repos(e, {"repos": {"db": {}}})
        antes = leer_local(raiz)
        codigo, salida = correr(["--arreglar", "config"], Falso(e.base, cwd=raiz))
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert leer_local(raiz) == antes


def test_config_rota_por_otra_causa_tambien_es_falta_con_el_mensaje_de_config_rota():
    with Escenario() as e:
        raiz = e.instancia()
        (raiz / "workspace.config.json").write_text('{"schema_version": 7, "layers": {}}', encoding="utf-8")
        r = por_id(Falso(e.base, cwd=raiz))["config"]
        assert r.estado == "FALTA" and "schema_version" in r.detalle, r


def con_disabled_hooks(raiz, valor):
    ruta = raiz / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["disabled_hooks"] = valor
    ruta.write_text(json.dumps(config), encoding="utf-8")


def test_config_con_disabled_hooks_invalido_es_falta_y_valido_es_ok():
    for valor, estado in (("guard_comandos", "FALTA"), (["guard-comandos"], "FALTA"), ([3], "FALTA"),
                          (["writer_stop", "writer_stop"], "FALTA"), ([], "OK"), (["guard_comandos", "revisar_turno"], "OK")):
        with Escenario() as e:
            raiz = e.instancia()
            con_disabled_hooks(raiz, valor)
            r = por_id(Falso(e.base, cwd=raiz))["config"]
            assert r.estado == estado, (valor, r)
            assert estado == "OK" or (r.detalle.startswith("disabled_hooks") and "workspace.config.json" in r.ayuda), (valor, r)


def test_hooks_apagados_es_ok_sin_la_clave_y_aviso_con_sus_nombres_sin_arreglo():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["hooks-apagados"]
        assert r.estado == "OK" and r.comando is None and r.arreglo is None, r
        con_disabled_hooks(raiz, [])
        assert por_id(ctx)["hooks-apagados"].estado == "OK"
        con_disabled_hooks(raiz, ["revisar_turno", "verificar_capa"])
        r = por_id(ctx)["hooks-apagados"]
        assert r.estado == "AVISO" and "revisar_turno, verificar_capa" in r.detalle, r
        assert r.comando is None and r.arreglo is None and "disabled_hooks" in r.ayuda and "guard_comandos" not in r.ayuda, r
        con_disabled_hooks(raiz, ["guard_comandos"])
        r = por_id(ctx)["hooks-apagados"]
        assert r.estado == "AVISO" and "guard_comandos" in r.detalle and "force push" in r.ayuda, r
        lineas = correr([], ctx)[1].splitlines()
        i = next(i for i, linea in enumerate(lineas) if linea.startswith("hooks-apagados "))
        assert lineas[i].split()[:2] == ["hooks-apagados", "AVISO"] and "cómo:" in lineas[i + 1], lineas[i:i + 2]
        codigo, salida = correr(["--arreglar", "hooks-apagados"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert json.loads((raiz / "workspace.config.json").read_text(encoding="utf-8"))["disabled_hooks"] == ["guard_comandos"]


def test_hooks_fallas_es_ok_sin_fallas_aviso_con_las_ultimas_y_arreglar_las_vacia():
    from odd_ws import fallas
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["hooks-fallas"]
        assert r.estado == "OK" and r.comando is None and r.arreglo is None, r
        for numero in range(5):
            fallas.anotar("guard_comandos", {"hook_event_name": "PreToolUse", "tool_input": {"command": "secreto"}},
                          RuntimeError("falla %d" % numero), raiz)
        r = por_id(ctx)["hooks-fallas"]
        assert r.estado == "AVISO" and r.detalle.startswith("5 fallas anotadas en .claude/estado/fallas-de-hooks.jsonl"), r
        assert [n for n in range(5) if "falla %d" % n in r.detalle] == [2, 3, 4], r
        assert r.detalle.index("falla 4") < r.detalle.index("falla 2"), "de la más nueva a la más vieja"
        assert "guard_comandos (PreToolUse): RuntimeError: falla 4" in r.detalle and "secreto" not in r.detalle, r
        lineas = correr([], ctx)[1].splitlines()
        i = next(i for i, linea in enumerate(lineas) if linea.startswith("hooks-fallas "))
        assert lineas[i].split()[:2] == ["hooks-fallas", "AVISO"], lineas[i]
        assert "arreglo: --arreglar hooks-fallas" in lineas[i + 1] and "cómo:" in lineas[i + 2], lineas[i:i + 3]
        codigo, salida = correr(["--arreglar", "hooks-fallas"], ctx)
        assert codigo == 0 and "hooks-fallas: OK" in salida, salida
        assert not (raiz / ".claude" / "estado" / "fallas-de-hooks.jsonl").exists()
        (raiz / ".claude" / "estado" / "fallas-de-hooks.jsonl").mkdir()
        r = por_id(ctx)["hooks-fallas"]
        assert r.estado == "AVISO" and r.detalle.startswith("no se puede leer") and r.arreglo is None and r.ayuda, r


def test_hooks_apagados_con_la_clave_invalida_no_aplica_y_lo_dice_el_item_config():
    with Escenario() as e:
        raiz = e.instancia()
        con_disabled_hooks(raiz, ["guard_comandos", "otro"])
        r = por_id(Falso(e.base, cwd=raiz))
        assert r["config"].estado == "FALTA", r["config"]
        assert r["hooks-apagados"].estado == "NO APLICA" and "config" in r["hooks-apagados"].detalle, r["hooks-apagados"]


def test_instancia_hooks_no_aplica_si_la_raiz_no_esta_en_un_repo_git():
    for git_real in (False, True):
        with Escenario() as e:
            raiz = e.instancia()
            r = por_id(Falso(e.base, cwd=raiz, git_real=git_real))["instancia-hooks"]
            assert r.estado == "NO APLICA" and r.arreglo is None and r.comando is None, (git_real, r)
            assert "no está en un repo git" in r.detalle, (git_real, r)


def test_instancia_hooks_si_git_falla_al_leer_el_valor_no_toma_el_error_por_valor():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz, respuestas={
            ("git", "-C", str(raiz), "rev-parse", "--show-toplevel"): (0, str(raiz) + "\n"),
            ("git", "-C", str(raiz), "config", "--get", "core.hooksPath"): (128, "fatal: bad config line 1\n"),
            ("git", "-C", str(raiz), "rev-parse", "--git-path", "hooks", "--git-dir", "--git-common-dir"): (0, f"{raiz}/.git/hooks\n{raiz}/.git\n{raiz}/.git\n"),
        })
        r = por_id(ctx)["instancia-hooks"]
        assert r.estado == "FALTA" and "sin configurar" in r.detalle and "fatal" not in r.detalle and r.comando is not None, r


def test_instancia_hooks_sin_poder_leer_los_hooks_del_repo_no_ofrece_arreglo():
    with Escenario() as e:
        raiz = e.instancia()
        ctx = Falso(e.base, cwd=raiz, respuestas={
            ("git", "-C", str(raiz), "rev-parse", "--show-toplevel"): (0, str(raiz) + "\n"),
            ("git", "-C", str(raiz), "config", "--get", "core.hooksPath"): (1, ""),
            ("git", "-C", str(raiz), "rev-parse", "--git-path", "hooks", "--git-dir", "--git-common-dir"): (128, "fatal: algo\n"),
        })
        r = por_id(ctx)["instancia-hooks"]
        assert r.estado == "FALTA" and r.comando is None and r.arreglo is None and "git no dijo dónde están los hooks del repo" in r.detalle, r


def hook_propio(raiz, nombre="pre-commit"):
    (raiz / ".git" / "hooks" / nombre).write_bytes(b"#!/bin/sh\nexit 0\n")


def test_instancia_hooks_con_hooks_propios_es_falta_sin_arreglo_y_no_toca_nada():
    for precommit in (True, False):
        with Escenario() as e:
            raiz = instancia_git(e, precommit=precommit)
            hook_propio(raiz, "pre-commit")
            hook_propio(raiz, "commit-msg")
            ctx = Falso(e.base, cwd=raiz, git_real=True)
            r = por_id(ctx)["instancia-hooks"]
            carpeta = os.path.normpath(str(raiz / ".git" / "hooks"))
            assert r.estado == "FALTA" and r.comando is None and r.arreglo is None, r
            assert f"hay hooks propios en {carpeta} (commit-msg, pre-commit), que dejarían de correr" in r.detalle, r.detalle
            assert "sin configurar" in r.detalle and r.ayuda and "integra .githooks/pre-commit" in r.ayuda.lower(), r
            assert ("falta .githooks/pre-commit" in r.detalle) == (not precommit), r.detalle
            codigo, salida = correr(["--arreglar", "instancia-hooks"], ctx)
            assert codigo == 2 and "no tiene arreglo automático" in salida, salida
            assert hooks_path(raiz) == ""


def test_instancia_hooks_en_un_worktree_enlazado_es_falta_sin_arreglo_y_no_toca_el_principal():
    with Escenario() as e:
        principal = e.base / "principal"
        principal.mkdir()
        git_en(principal, "init", "-q")
        (principal / "x.txt").write_text("x\n", encoding="utf-8")
        git_en(principal, "add", "x.txt")
        git_en(principal, "-c", "user.name=p", "-c", "user.email=p@p", "commit", "-q", "-m", "x")
        raiz = e.base / "wt"
        git_en(principal, "worktree", "add", "-q", str(raiz))
        poner(raiz, ".githooks/pre-commit", "#!/bin/sh\n")
        (raiz / "workspace.config.json").write_text(json.dumps({"schema_version": 1, "layers": {"sql": {"extensions": [".sql"]}}}), encoding="utf-8")
        antes = (principal / ".git" / "config").read_bytes()
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["instancia-hooks"]
        assert r.estado == "FALTA" and r.comando is None and r.arreglo is None and r.ayuda, r
        assert "la raíz es un worktree enlazado y --local cambiaría la config de todos sus checkouts" in r.detalle, r.detalle
        codigo, salida = correr(["--arreglar", "instancia-hooks"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert (principal / ".git" / "config").read_bytes() == antes


def test_instancia_hooks_con_solo_hooks_de_ejemplo_sigue_ofreciendo_el_arreglo():
    with Escenario() as e:
        raiz = instancia_git(e)
        assert any(n.endswith(".sample") for n in os.listdir(raiz / ".git" / "hooks"))
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-hooks"]
        assert r.estado == "FALTA" and r.comando is not None, r


def test_instancia_hooks_con_hookspath_y_pre_commit_es_ok():
    with Escenario() as e:
        raiz = instancia_git(e, hooks=".githooks")
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-hooks"]
        assert r.estado == "OK" and ".githooks" in r.detalle, r


def test_instancia_hooks_sin_valor_es_falta_y_arreglar_lo_configura():
    with Escenario() as e:
        raiz = instancia_git(e)
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["instancia-hooks"]
        assert r.estado == "FALTA" and "sin configurar" in r.detalle and r.comando is not None, r
        assert hooks_path(raiz) == ""
        codigo, salida = correr(["--arreglar", "instancia-hooks"], ctx)
        assert codigo == 0 and "instancia-hooks: OK" in salida, salida
        assert hooks_path(raiz) == ".githooks"


def test_instancia_hooks_con_otro_valor_es_falta_sin_arreglo_y_no_lo_pisa():
    with Escenario() as e:
        raiz = instancia_git(e, hooks="otros-hooks")
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["instancia-hooks"]
        assert r.estado == "FALTA" and "otros-hooks" in r.detalle and r.comando is None and r.arreglo is None and r.ayuda, r
        codigo, salida = correr(["--arreglar", "instancia-hooks"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert hooks_path(raiz) == "otros-hooks"


def instancia_con_repo_versionado(e, archivos):
    repo = e.base / "db"
    for relativa, texto in archivos.items():
        poner(repo, relativa, texto)
    git_en(repo, "init", "-q")
    git_en(repo, "add", "-A")
    return instancia_con_repos(e, {"repos": {"db": {"path": str(repo)}}})


def test_capas_cobertura_ok_cuando_todo_lo_versionado_tiene_capa_o_es_doc():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x", "sub/b.SQL": "x", "README.md": "x", "notas.txt": "x", "guia.rst": "x"})
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["capas-cobertura"]
        assert r.estado == "OK" and r.arreglo is None and r.comando is None, r
        assert r.detalle == "todo lo versionado en los repos tiene capa o es doc", r.detalle


def test_capas_cobertura_con_solo_esperados_es_ok_y_los_nombra_con_su_conteo():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x", "package.json": "{}", "tsconfig.json": "{}", ".gitignore": "x",
                                                 "README.md": "x"})
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["capas-cobertura"]
        detalle = "sin capa y esperados: .json (2), (sin extensión) (1); un cambio en ellos lleva /odd-ws:revisar a modo completo"
        assert (r.estado, r.detalle, r.comando, r.arreglo) == ("OK", detalle, None, None), r
        salida = correr([], ctx)[1].splitlines()
        linea = next(i for i, l in enumerate(salida) if l.startswith("capas-cobertura "))
        assert salida[linea].split()[:2] == ["capas-cobertura", "OK"] and salida[linea].endswith(detalle), salida[linea]
        assert "cómo:" not in salida[linea + 1], salida[linea + 1]


def test_capas_cobertura_avisa_las_extensiones_sin_capa_con_su_cantidad():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x", "scripts/x.mjs": "x", "scripts/y.mjs": "x", "scripts/z.sh": "x",
                                                 "package.json": "{}", "Makefile": "x", "README.md": "x"})
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["capas-cobertura"]
        assert r.estado == "AVISO" and r.arreglo is None, r
        assert r.detalle == "extensiones versionadas sin capa: .mjs (2), .sh (1)", "solo las no esperadas, de la más frecuente a la menos"
        assert "completo" in r.ayuda and "extensions" in r.ayuda, r.ayuda


def test_capas_cobertura_no_aplica_sin_repos_o_con_la_config_rota():
    with Escenario() as e:
        r = por_id(Falso(e.base, cwd=e.instancia(), git_real=True))["capas-cobertura"]
        assert r.estado == "NO APLICA", r
    with Escenario() as e:
        raiz = instancia_con_repos(e, {"repos": {}})
        assert por_id(Falso(e.base, cwd=raiz, git_real=True))["capas-cobertura"].estado == "NO APLICA"


def test_capas_cobertura_sale_igual_que_antes_con_la_ayuda_compartida():
    import config_loader
    with Escenario() as e:
        archivos = {"a.sql": "x", "scripts/x.mjs": "x", "scripts/y.mjs": "x", "package.json": "{}", "Makefile": "x", "README.md": "x"}
        archivos.update({"otros/a%d.e%d" % (n, n): "x" for n in range(8)})
        raiz = instancia_con_repo_versionado(e, archivos)
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["capas-cobertura"]
        assert r.detalle == ("extensiones versionadas sin capa: .mjs (2), .e0 (1), .e1 (1), .e2 (1), .e3 (1), .e4 (1), .e5 (1), "
                             ".e6 (1) y 1 más"), r.detalle
        cuenta = {".mjs": 2, **{".e%d" % n: 1 for n in range(8)}}
        assert r.ayuda == config_loader.ayuda_de_cobertura(cuenta) and r.comando is None and r.arreglo is None, r
        resultados = d().diagnosticar(ctx)
        sangria = " " * (max(len(x.id) for x in resultados) + 13)
        salida = correr([], ctx)[1].splitlines()
        linea = next(i for i, l in enumerate(salida) if l.startswith("capas-cobertura "))
        assert salida[linea].split()[:2] == ["capas-cobertura", "AVISO"] and salida[linea].endswith(r.detalle), salida[linea]
        assert salida[linea + 1] == sangria + "cómo: Un cambio en esos archivos lleva el triaje de /odd-ws:revisar a modo completo, porque no " \
            "puede clasificarlos. Si son del mismo lenguaje que una capa (por ejemplo, .mjs o .js en una capa ts), súmalos a sus " \
            "extensions en workspace.config.json. Si van sin capa a propósito (imágenes, recursos, archivos de build), reconócelos una "             "vez en workspace.config.json con esta línea, sin las extensiones que sí son código: "             '"sin_capa": [".mjs", ".e0", ".e1", ".e2", ".e3", ".e4", ".e5", ".e6", ".e7"]', salida[linea + 1]


def con_sin_capa(raiz, valor):
    ruta = raiz / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["sin_capa"] = valor
    ruta.write_text(json.dumps(config), encoding="utf-8")


def test_capas_cobertura_con_sin_capa_pasa_sus_extensiones_a_las_esperadas_y_el_como_trae_la_linea():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x", "res/i.png": "x", "res/j.png": "x", "res/k.xml": "x", "package.json": "{}"})
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["capas-cobertura"]
        assert (r.estado, r.detalle, r.comando, r.arreglo) == ("AVISO", "extensiones versionadas sin capa: .png (2), .xml (1)", None, None), r
        assert r.ayuda.endswith('con esta línea, sin las extensiones que sí son código: "sin_capa": [".png", ".xml"]'), r.ayuda
        codigo, salida = correr(["--arreglar", "capas-cobertura"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert "sin_capa" not in json.loads((raiz / "workspace.config.json").read_text(encoding="utf-8")), "el doctor no toca la config"
        con_sin_capa(raiz, [".png", ".xml"])
        r = por_id(ctx)["capas-cobertura"]
        detalle = "sin capa y esperados: .png (2), .json (1), .xml (1); un cambio en ellos lleva /odd-ws:revisar a modo completo"
        assert (r.estado, r.detalle, r.ayuda) == ("OK", detalle, ""), r
        assert por_id(ctx)["config"].estado == "OK"
        con_sin_capa(raiz, [".png"])
        r = por_id(ctx)["capas-cobertura"]
        assert (r.estado, r.detalle) == ("AVISO", "extensiones versionadas sin capa: .xml (1)"), r
        assert r.ayuda.endswith('"sin_capa": [".png", ".xml"]'), r.ayuda


def test_sin_capa_invalido_es_falta_en_config_y_capas_cobertura_no_aplica():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x", "res/i.png": "x"})
        for malo in (".png", ["png"], [".png", 3], {".png": True}):
            con_sin_capa(raiz, malo)
            r = por_id(Falso(e.base, cwd=raiz, git_real=True))
            assert r["config"].estado == "FALTA" and r["config"].detalle.startswith("sin_capa"), (malo, r["config"])
            assert "workspace.config.json" in r["config"].ayuda, r["config"]
            assert r["capas-cobertura"].estado == "NO APLICA" and "config" in r["capas-cobertura"].detalle, (malo, r["capas-cobertura"])


def poner_hooks_en(repo, nombre="settings.json", contenido=None):
    hooks = {"hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "npx prettier --write"}]}]}}
    return poner(repo, ".claude/" + nombre, json.dumps(hooks) if contenido is None else contenido)


def test_hooks_de_repos_avisa_los_repos_de_la_config_con_hooks_propios_y_no_tiene_arreglo():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x"})
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["hooks-de-repos"]
        assert r.estado == "OK" and r.comando is None and r.arreglo is None, r
        poner_hooks_en(e.base / "db")
        poner_hooks_en(e.base / "db", "settings.local.json")
        r = por_id(ctx)["hooks-de-repos"]
        assert r.estado == "AVISO" and r.comando is None and r.arreglo is None, r
        assert r.detalle == "repos con hooks propios: db (.claude/settings.json, .claude/settings.local.json)", r.detalle
        assert "corren solo si la sesión arranca en el repo" in r.ayuda, r.ayuda
        lineas = correr([], ctx)[1].splitlines()
        i = next(i for i, linea in enumerate(lineas) if linea.startswith("hooks-de-repos "))
        assert lineas[i].split()[:2] == ["hooks-de-repos", "AVISO"] and lineas[i + 1].strip() == "cómo: " + r.ayuda, lineas[i:i + 2]
        codigo, salida = correr(["--arreglar", "hooks-de-repos"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida


def test_hooks_de_repos_no_aplica_si_la_instancia_no_declara_claude_code():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x"})
        ruta = raiz / "workspace.config.json"
        config = json.loads(ruta.read_text(encoding="utf-8"))
        config["hosts"] = ["codex"]
        ruta.write_text(json.dumps(config), encoding="utf-8")
        poner_hooks_en(e.base / "db")
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["hooks-de-repos"]
        assert r.estado == "NO APLICA" and "Claude Code" in r.detalle and r.arreglo is None, r


def test_hooks_de_repos_calla_con_un_settings_ilegible_o_sin_hooks_y_no_aplica_sin_repos_o_con_la_config_rota():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x"})
        poner_hooks_en(e.base / "db", contenido="{roto")
        poner_hooks_en(e.base / "db", "settings.local.json", contenido=json.dumps({"permissions": {"allow": ["Bash(git status)"]}}))
        poner_hooks_en(raiz, contenido=None)
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["hooks-de-repos"]
        assert r.estado == "OK", r
    with Escenario() as e:
        assert "hooks-de-repos" not in por_id(Falso(e.base)), "fuera de una instancia no sale"
        r = por_id(Falso(e.base, cwd=e.instancia()))["hooks-de-repos"]
        assert r.estado == "NO APLICA" and "no declara repos" in r.detalle, r
    with Escenario() as e:
        raiz = instancia_con_repos(e, {"repos": {}})
        r = por_id(Falso(e.base, cwd=raiz))["hooks-de-repos"]
        assert r.estado == "NO APLICA" and "config" in r.detalle, r


def test_las_extensiones_de_docs_del_doctor_son_las_del_triaje():
    import config_loader
    import triaje
    assert config_loader.EXTENSIONES_DE_DOCS == triaje.DOC_EXT


def test_instancia_eol_no_aplica_si_la_raiz_no_esta_en_un_repo_git():
    with Escenario() as e:
        raiz = e.instancia()
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-eol"]
        assert r.estado == "NO APLICA" and r.arreglo is None and r.comando is None, r


def test_instancia_eol_no_aplica_sin_pre_commit():
    with Escenario() as e:
        raiz = instancia_git(e, hooks=".githooks", precommit=False)
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-eol"]
        assert r.estado == "NO APLICA" and ".githooks/pre-commit" in r.detalle and r.arreglo is None, r


def test_instancia_eol_con_la_linea_del_bootstrap_es_ok():
    with Escenario() as e:
        raiz = instancia_git(e, hooks=".githooks")
        (raiz / ".gitattributes").write_bytes(b".githooks/* text eol=lf\n")
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-eol"]
        assert r.estado == "OK" and r.arreglo is None and r.comando is None, r


def test_instancia_eol_reconoce_una_regla_mas_amplia_que_ya_deja_el_hook_en_lf():
    with Escenario() as e:
        raiz = instancia_git(e, hooks=".githooks")
        (raiz / ".gitattributes").write_bytes(b"* text=auto eol=lf\n")
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-eol"]
        assert r.estado == "OK", r


def test_instancia_eol_sin_la_regla_es_aviso_y_arreglar_la_agrega_sin_tocar_lo_demas():
    for previo in (None, b"*.png binary", b"*.png binary\r\n"):
        with Escenario() as e:
            raiz = instancia_git(e, hooks=".githooks")
            if previo is not None:
                (raiz / ".gitattributes").write_bytes(previo)
            ctx = Falso(e.base, cwd=raiz, git_real=True)
            r = por_id(ctx)["instancia-eol"]
            assert r.estado == "AVISO" and "CRLF" in r.detalle and r.arreglo is not None and r.comando is None, (previo, r)
            codigo, salida = correr(["--arreglar", "instancia-eol"], ctx)
            assert codigo == 0 and "instancia-eol: OK" in salida, (previo, salida)
            esperado = previo or b""
            if esperado and not esperado.endswith(b"\n"):
                esperado += b"\n"
            assert (raiz / ".gitattributes").read_bytes() == esperado + b".githooks/* text eol=lf\n", previo


def test_instancia_hooks_apuntando_bien_pero_sin_pre_commit_es_falta_sin_arreglo():
    with Escenario() as e:
        raiz = instancia_git(e, hooks=".githooks", precommit=False)
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-hooks"]
        assert r.estado == "FALTA" and "pre-commit" in r.detalle and r.comando is None and r.arreglo is None and r.ayuda, r


def test_instancia_hooks_sin_valor_y_sin_pre_commit_lo_dice_y_el_arreglo_no_lo_da_por_bueno():
    with Escenario() as e:
        raiz = instancia_git(e, precommit=False)
        ctx = Falso(e.base, cwd=raiz, git_real=True)
        r = por_id(ctx)["instancia-hooks"]
        assert r.estado == "FALTA" and "falta .githooks/pre-commit" in r.detalle and r.comando is not None and r.ayuda, r
        codigo, salida = correr(["--arreglar", "instancia-hooks"], ctx)
        assert codigo == 1 and hooks_path(raiz) == ".githooks", (codigo, salida)


def test_instancia_hooks_no_aplica_si_la_instancia_esta_dentro_de_otro_repo():
    with Escenario() as e:
        git_en(e.base, "init", "-q")
        raiz = e.instancia()
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["instancia-hooks"]
        assert r.estado == "NO APLICA" and r.comando is None, r
        assert hooks_path(e.base) == "", "no toca el repo de afuera"


def test_instancia_plugin_habilitado_es_ok_con_o_sin_bom():
    for crudo in (json.dumps({"enabledPlugins": {CLAVE_PLUGIN: True, "otro@mercado": False}}),
                  b"\xef\xbb\xbf" + json.dumps({"enabledPlugins": {CLAVE_PLUGIN: True}}).encode("utf-8")):
        with Escenario() as e:
            raiz = e.instancia()
            poner_settings(raiz, crudo)
            r = por_id(Falso(e.base, cwd=raiz))["instancia-plugin"]
            assert r.estado == "OK" and CLAVE_PLUGIN in r.detalle and r.arreglo is None, r


def test_instancia_plugin_sin_habilitar_es_aviso_sin_arreglo_y_no_toca_el_archivo():
    casos = [None, {}, {"enabledPlugins": {}}, {"enabledPlugins": {"otro@mercado": True}}, {"enabledPlugins": {CLAVE_PLUGIN: False}},
             {"enabledPlugins": [CLAVE_PLUGIN]}, {"enabledPlugins": {CLAVE_PLUGIN: "true"}}, {"enabledPlugins": {CLAVE_PLUGIN: None}}]
    for contenido in casos:
        with Escenario() as e:
            raiz = e.instancia()
            if contenido is not None:
                poner_settings(raiz, contenido)
            ctx = Falso(e.base, cwd=raiz)
            r = por_id(ctx)["instancia-plugin"]
            assert r.estado == "AVISO" and r.arreglo is None and r.comando is None, (contenido, r)
            assert CLAVE_PLUGIN in r.ayuda and "enabledPlugins" in r.ayuda, r
            codigo, salida = correr(["--arreglar", "instancia-plugin"], ctx)
            assert codigo == 2, (contenido, salida)
            assert (raiz / ".claude" / "settings.json").is_file() == (contenido is not None)
            if contenido is not None:
                assert json.loads((raiz / ".claude" / "settings.json").read_text(encoding="utf-8")) == contenido


def test_instancia_plugin_con_settings_roto_es_falta_sin_arreglo():
    for malo in ("{no es json", "[1]", "null", b"\xff\xfe\x00 roto"):
        with Escenario() as e:
            raiz = e.instancia()
            poner_settings(raiz, malo)
            ctx = Falso(e.base, cwd=raiz)
            r = por_id(ctx)["instancia-plugin"]
            assert r.estado == "FALTA" and ".claude/settings.json" in r.detalle and r.arreglo is None and r.comando is None, (malo, r)
            codigo, salida = correr([], ctx)
            assert codigo == 1, salida
            assert (raiz / ".claude" / "settings.json").read_bytes() == (malo if isinstance(malo, bytes) else malo.encode("utf-8"))


CLAVE_PLUGIN = "odd-ws@odd-workspace-template"
CLAVES_DE_CODEX = [CLAVE_PLUGIN + ":hooks/hooks.codex.json:" + clave for clave in (
    "session_start:0:0", "pre_tool_use:0:0", "pre_tool_use:1:0", "pre_tool_use:2:0", "post_tool_use:0:0", "subagent_stop:0:0",
    "user_prompt_submit:0:0", "stop:0:0")]
ITEMS_DE_CODEX = ["codex", "codex-plugin", "codex-hooks", "codex-proyecto", "codex-config", "codex-agentes"]
ITEMS_DE_CLAUDE = {"claude", "marketplace", "instancia-plugin", "agentes-skills", "agentes-hooks"}


def ba():
    return importlib.import_module("bootstrap_agentes")


def cx():
    return importlib.import_module("odd_ws.hosts.codex")


def con_hosts(raiz, hosts):
    ruta = raiz / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["hosts"] = hosts
    ruta.write_text(json.dumps(config), encoding="utf-8")
    return raiz


def con_hooks_del_plugin(ctx):
    shutil.copytree(AQUI.parent / "hooks", ctx.plugin / "hooks", dirs_exist_ok=True)
    return ctx


def falso_de_codex(e, raiz, version="codex-cli 0.167.0\n", **extra):
    respuestas = {**extra.pop("respuestas", {}), ("codex", "--version"): (0, version) if version else None}
    return con_hooks_del_plugin(Falso(e.base, cwd=raiz, respuestas=respuestas, **extra))


def texto_toml(valor):
    return json.dumps(valor)


def poner_config_de_codex(ctx, plugin=True, claves=CLAVES_DE_CODEX, proyecto=None, extra="", carpeta=None):
    partes = []
    if plugin is not None:
        partes.append('[plugins."%s"]\n%s' % (CLAVE_PLUGIN, "" if plugin is True else "enabled = %s\n" % plugin))
    if proyecto is not None:
        ruta, nivel = proyecto
        partes.append('[projects.%s]\ntrust_level = "%s"\n' % (texto_toml(str(ruta)), nivel))
    partes += ['[hooks.state."%s"]\ntrusted_hash = "sha256:abc"\n' % clave for clave in claves]
    return poner(carpeta or ctx.home / ".codex", "config.toml", "\n".join(partes) + extra)


def poner_cache_de_codex(ctx, *versiones):
    for version in versiones or ("0.3.0",):
        (ctx.home / ".codex" / "plugins" / "cache" / "odd-workspace-template" / "odd-ws" / version).mkdir(parents=True)


def poner_agentes(raiz, capa="sql"):
    poner(raiz, ".claude/agents/writer-%s.md" % capa, pw().generar(capa))
    poner(raiz, ".claude/agents/revisor-%s.md" % capa, ba().generar_revisor(capa))
    poner(raiz, ".claude/agents/revisor-diseno.md", ba().generar_revisor_diseno())


def toml_de_la_plantilla(nombre):
    if nombre == "revisor-diseno":
        armado = ba().generar_revisor_diseno(host="codex")
    elif nombre.startswith("writer-"):
        armado = pw().generar(nombre[len("writer-"):], host="codex")
    else:
        armado = ba().generar_revisor(nombre[len("revisor-"):], host="codex")
    return cx().toml(pw().agente(armado))


def toml_en(raiz, nombre):
    return raiz / ".codex" / "agents" / ("%s.toml" % nombre)


def resellar_toml(texto):
    lineas = texto.split("\n")
    sello = cx().huella(texto)
    return "\n".join("# odd-ws-hash: " + sello if linea.startswith("# odd-ws-hash:") else linea for linea in lineas)


def instancia_codex_sana(e, hosts=("codex",)):
    raiz = con_hosts(e.instancia(json.dumps({"plugin_root": str(e.base / "plugin-instalado")})), list(hosts))
    poner_agentes(raiz)
    for nombre in ("writer-sql", "revisor-sql", "revisor-diseno"):
        poner(raiz, ".codex/agents/%s.toml" % nombre, toml_de_la_plantilla(nombre))
    poner(raiz, ".codex/config.toml", cx().CONFIG_DEL_PROYECTO)
    ctx = falso_de_codex(e, raiz)
    poner_cache_de_codex(ctx)
    poner_config_de_codex(ctx, proyecto=(raiz, "trusted"))
    return raiz, ctx


def test_con_hosts_claude_code_la_salida_es_la_misma_que_sin_la_clave():
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner(raiz, ".claude/agents/writer-sql.md", pw().generar("sql").replace("Nunca reviertas", "Revierte", 1))
        ctx = Falso(e.base, cwd=raiz)
        sin = [correr(argv, ctx) for argv in ([], ["--arreglar", "writer-sql"], ["--arreglar", "no-existe"])]
        ids_sin = [r.id for r in d().diagnosticar(ctx)]
        con_hosts(raiz, ["claude-code"])
        con = [correr(argv, ctx) for argv in ([], ["--arreglar", "writer-sql"], ["--arreglar", "no-existe"])]
        assert con == sin, (con, sin)
        assert [r.id for r in d().diagnosticar(ctx)] == ids_sin == [i for i in ANTES_EN_INSTANCIA[:3]] + list(NUEVOS) + ANTES_EN_INSTANCIA[3:], ids_sin
        assert not [i for i in ids_sin if i.startswith("codex") or i in ("hosts", "hooks-host")], ids_sin


def test_sin_claude_code_declarado_sus_items_no_salen_y_claude_ausente_no_hace_fallar():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        ctx.respuestas[("claude", "--version")] = None
        ids = [r.id for r in d().diagnosticar(ctx)]
        assert not ITEMS_DE_CLAUDE & set(ids), ids
        codigo, salida = correr([], ctx)
        assert codigo == 0 and not [l for l in salida.splitlines() if l.split(" ", 1)[0] in ITEMS_DE_CLAUDE], salida
        codigo, salida = correr(["--arreglar", "claude"], ctx)
        assert codigo == 2 and "no existe el ítem «claude»" in salida, salida


def test_con_los_dos_hosts_salen_los_de_claude_code_y_los_de_codex_en_su_orden():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e, hosts=("claude-code", "codex"))
        ids = [r.id for r in d().diagnosticar(ctx)]
        assert ITEMS_DE_CLAUDE <= set(ids), ids
        assert ids[ids.index("claude"):ids.index("claude") + 9] == ["claude", "marketplace", *ITEMS_DE_CODEX, "hooks-host"], ids
        con_hosts(raiz, ["codex", "claude-code"])
        ids = [r.id for r in d().diagnosticar(ctx)]
        assert ids[ids.index("codex"):ids.index("codex") + 9] == [*ITEMS_DE_CODEX, "claude", "marketplace", "hooks-host"], ids


def test_hosts_invalido_es_una_falta_clara_y_no_revienta():
    for malo, rastro in ((["gemini"], "'gemini' no es un host conocido"), ([], "lista no vacía"), (["codex", "codex"], "repetido"),
                         ("codex", "lista no vacía")):
        with Escenario() as e:
            raiz = con_hosts(instancia_sana(e), malo)
            ctx = con_hooks_del_plugin(Falso(e.base, cwd=raiz))
            r = por_id(ctx)
            assert r["hosts"].estado == "FALTA" and rastro in r["hosts"].detalle and r["hosts"].arreglo is None and r["hosts"].ayuda, (malo, r["hosts"])
            assert not [i for i in r if i.startswith("codex") or i in ITEMS_DE_CLAUDE or i == "hooks-host"], (malo, list(r))
            assert r["config"].estado == "OK", r["config"]
            codigo, salida = correr([], ctx)
            assert codigo == 1 and "hosts" in salida, salida
            codigo, salida = correr(["--arreglar", "hosts"], ctx)
            assert codigo == 2 and "workspace.config.json" in salida, salida


def test_config_ilegible_sigue_con_los_items_de_claude_code_como_antes():
    with Escenario() as e:
        raiz = instancia_sana(e)
        (raiz / "workspace.config.json").write_text("{roto", encoding="utf-8")
        ids = list(por_id(Falso(e.base, cwd=raiz)))
        assert "claude" in ids and "marketplace" in ids and "hosts" not in ids and "hooks-host" not in ids, ids


def test_una_instancia_codex_sana_da_ok_en_todos_sus_items():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        r = por_id(ctx)
        assert all(r[i].estado == "OK" for i in ITEMS_DE_CODEX + ["hooks-host"]), {i: r[i] for i in ITEMS_DE_CODEX + ["hooks-host"]}
        assert r["codex"].detalle == "0.167.0", r["codex"]
        assert "frescura" in r["codex-hooks"].detalle and "no se verifica" in r["codex-hooks"].detalle, r["codex-hooks"]
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida


def test_hooks_host_cuenta_handlers_y_aparte_los_comandos_cuando_un_handler_trae_command_windows():
    with Escenario() as e:
        _, ctx = instancia_codex_sana(e)
        assert por_id(ctx)["hooks-host"].detalle == "8 hooks de codex (16 comandos), cada uno con el --host de su archivo"
    with Escenario() as e:
        _, ctx = instancia_codex_sana(e, hosts=("claude-code", "codex"))
        assert por_id(ctx)["hooks-host"].detalle == "17 hooks de claude-code, codex (25 comandos), cada uno con el --host de su archivo"


def test_hooks_host_ve_el_host_de_revisar_turno_al_empezar_y_al_terminar_el_turno():
    with Escenario() as e:
        _, ctx = instancia_codex_sana(e, hosts=("claude-code", "codex"))
        archivo = ctx.plugin / "hooks" / "hooks.codex.json"
        original = archivo.read_text(encoding="utf-8")
        for evento in ("UserPromptSubmit", "Stop"):
            datos = json.loads(original)
            hook = datos["hooks"][evento][0]["hooks"][0]
            hook["command"] = hook["command"].replace(" --host codex", "")
            archivo.write_text(json.dumps(datos), encoding="utf-8")
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and ("hooks/hooks.codex.json %s[0][0]: revisar_turno.py sin --host" % evento) in r.detalle, (evento, r)
            assert "(commandWindows)" not in r.detalle, "el de Windows sigue con su --host: %r" % r.detalle
        archivo.write_text(original, encoding="utf-8")
        assert por_id(ctx)["hooks-host"].estado == "OK"


def test_codex_por_version_ausente_o_vieja_y_sin_codex_lo_de_la_maquina_no_aplica():
    with Escenario() as e:
        raiz, _ = instancia_codex_sana(e)
        r = por_id(falso_de_codex(e, raiz, version="codex-cli 0.143.9\n"))["codex"]
        assert r.estado == "FALTA" and "0.143.9" in r.detalle and "0.144.0" in r.detalle and r.ayuda, r
        assert por_id(falso_de_codex(e, raiz, version="codex-cli 0.144.0\n"))["codex"].estado == "OK"
        ctx = falso_de_codex(e, raiz, version=None)
        r = por_id(ctx)
        assert r["codex"].estado == "FALTA" and "no está instalado" in r["codex"].detalle, r["codex"]
        assert all(r[i].estado == "NO APLICA" for i in ("codex-plugin", "codex-hooks", "codex-proyecto")), r
        assert r["codex-config"].estado == "OK" and r["codex-agentes"].estado == "OK", r


def test_codex_se_corre_por_la_ruta_que_da_which_para_alcanzar_un_cmd():
    with Escenario() as e:
        raiz, _ = instancia_codex_sana(e)
        ruta = "C:/npm/codex.CMD"
        ctx = falso_de_codex(e, raiz, respuestas={(ruta, "--version"): (0, "codex-cli 0.150.1\n")}, which={"codex": ruta})
        assert por_id(ctx)["codex"].detalle == "0.150.1"
        assert (ruta, "--version") in ctx.llamadas, ctx.llamadas


def test_codex_plugin_sale_del_cache_y_de_plugins_y_respeta_codex_home():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        cache = ctx.home / ".codex" / "plugins" / "cache"
        shutil.rmtree(cache)
        r = por_id(ctx)["codex-plugin"]
        assert r.estado == "FALTA" and "no está instalado" in r.detalle and r.arreglo is None and r.ayuda, r
        poner_cache_de_codex(ctx, "0.2.2", "0.3.0")
        for plugin, rastro in ((None, "no está en [plugins]"), ("false", "enabled = false")):
            poner_config_de_codex(ctx, plugin=plugin, proyecto=(raiz, "trusted"))
            r = por_id(ctx)["codex-plugin"]
            assert r.estado == "FALTA" and rastro in r.detalle and r.ayuda, (plugin, r)
        poner_config_de_codex(ctx, plugin="true", proyecto=(raiz, "trusted"))
        r = por_id(ctx)["codex-plugin"]
        assert r.estado == "OK" and "0.2.2" in r.detalle and "0.3.0" in r.detalle, r
        poner(ctx.home, ".codex/config.toml", "[plugins\nroto")
        r = por_id(ctx)
        assert r["codex-plugin"].estado == "FALTA" and "TOML" in r["codex-plugin"].detalle, r["codex-plugin"]
        assert r["codex-hooks"].estado == "AVISO" and r["codex-proyecto"].estado == "AVISO", r
        otra = e.base / "otro-codex-home"
        shutil.move(str(ctx.home / ".codex"), str(otra))
        poner_config_de_codex(ctx, plugin="true", proyecto=(raiz, "trusted"), carpeta=otra)
        ctx.entorno = {"CODEX_HOME": str(otra)}
        r = por_id(ctx)
        assert r["codex-plugin"].estado == "OK" and str(otra) in r["codex-plugin"].detalle, r["codex-plugin"]
        assert not (ctx.home / ".codex").exists()


def test_codex_hooks_pide_la_clave_exacta_de_cada_handler_con_trusted_hash():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        assert por_id(ctx)["codex-hooks"].estado == "OK"
        for falta in CLAVES_DE_CODEX:
            poner_config_de_codex(ctx, claves=[c for c in CLAVES_DE_CODEX if c != falta], proyecto=(raiz, "trusted"))
            r = por_id(ctx)["codex-hooks"]
            assert r.estado == "AVISO" and "1 de 8" in r.detalle and falta.split("json:")[1] in r.detalle, (falta, r)
            assert "/hooks" in r.ayuda and r.arreglo is None and "no se verifica" in r.detalle, r
        claves = [c for c in CLAVES_DE_CODEX if c != CLAVES_DE_CODEX[2]]
        poner_config_de_codex(ctx, claves=claves, proyecto=(raiz, "trusted"),
                              extra='\n[hooks.state."%s"]\nenabled = false\ntrusted_hash = "sha256:abc"\n' % CLAVES_DE_CODEX[2])
        r = por_id(ctx)["codex-hooks"]
        assert r.estado == "AVISO" and "enabled = false" in r.detalle and "pre_tool_use:1:0" in r.detalle, r
        poner_config_de_codex(ctx, claves=[c.replace("hooks.codex.json", "hooks.json") for c in CLAVES_DE_CODEX], proyecto=(raiz, "trusted"))
        assert por_id(ctx)["codex-hooks"].estado == "AVISO"
        assert correr([], ctx)[0] == 0


def test_codex_proyecto_busca_la_raiz_y_su_repo_en_projects():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        assert por_id(ctx)["codex-proyecto"].estado == "OK"
        for proyecto in (None, (raiz, "untrusted"), (e.base / "otra", "trusted")):
            poner_config_de_codex(ctx, proyecto=proyecto)
            r = por_id(ctx)["codex-proyecto"]
            assert r.estado == "AVISO" and ".codex/" in r.detalle and r.ayuda and r.arreglo is None, (proyecto, r)
        poner_config_de_codex(ctx, proyecto=(str(raiz).upper() if os.name == "nt" else str(raiz), "trusted"))
        assert por_id(ctx)["codex-proyecto"].estado == "OK"


def test_codex_proyecto_compara_la_clave_como_codex_sin_normalizar_barras_ni_la_barra_final():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        malas = [str(raiz) + os.sep] + ([str(raiz).replace("\\", "/"), str(raiz).replace("\\", "/") + "/"] if os.name == "nt" else [])
        for clave in malas:
            poner_config_de_codex(ctx, proyecto=(clave, "trusted"))
            r = por_id(ctx)["codex-proyecto"]
            assert r.estado == "AVISO" and r.ayuda, (clave, r)
        for clave in (str(raiz), os.path.realpath(raiz)) + ((str(raiz).upper(), str(raiz).lower()) if os.name == "nt" else ()):
            poner_config_de_codex(ctx, proyecto=(clave, "trusted"))
            assert por_id(ctx)["codex-proyecto"].estado == "OK", clave


def test_codex_proyecto_solo_ignora_las_mayusculas_ascii_como_codex():
    codex = cx()
    proyectos = {"C:\\Árbol\\Inst": "trusted", "c:\\otra": "untrusted"}
    assert codex.confianza_del_proyecto(proyectos, ["c:\\Árbol\\inst"], True) == ("C:\\Árbol\\Inst", "trusted")
    assert codex.confianza_del_proyecto(proyectos, ["c:\\árbol\\inst"], True) is None
    assert codex.confianza_del_proyecto(proyectos, ["c:\\Árbol\\inst"], False) is None
    assert codex.confianza_del_proyecto(proyectos, ["C:\\Árbol\\Inst"], False) == ("C:\\Árbol\\Inst", "trusted")
    assert codex.confianza_del_proyecto({"C:\\X": "untrusted", "c:\\x": "trusted"}, ["c:\\x"], True) == ("c:\\x", "trusted")
    assert codex.confianza_del_proyecto({"C:\\X": "untrusted", "C:\\x": "trusted"}, ["c:\\x"], True) == ("C:\\X", "untrusted")


def test_la_ayuda_de_codex_proyecto_da_una_tabla_toml_que_codex_reconoce():
    import tomllib

    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        poner_config_de_codex(ctx, proyecto=None)
        r = por_id(ctx)["codex-proyecto"]
        tabla = re.search(r"(\[projects\..*?\]) con (trust_level = \"trusted\")", r.ayuda)
        assert tabla and "'" in tabla.group(1), r.ayuda
        datos = tomllib.loads("%s\n%s\n" % tabla.groups())
        assert list(datos["projects"]) == [os.path.realpath(raiz)], datos
        poner_config_de_codex(ctx, proyecto=None, extra="\n%s\n%s\n" % tabla.groups())
        assert por_id(ctx)["codex-proyecto"].estado == "OK"


def test_codex_proyecto_acepta_la_confianza_del_repo_que_contiene_la_instancia():
    with Escenario() as e:
        repo = e.base / "repo"
        repo.mkdir()
        git_en(repo, "init", "-q")
        raiz = con_hosts(e.instancia(), ["codex"])
        destino = repo / "instancia"
        shutil.move(str(raiz), str(destino))
        ctx = falso_de_codex(e, destino, git_real=True)
        poner_cache_de_codex(ctx)
        repo_canonico = os.path.realpath(repo)
        poner_config_de_codex(ctx, proyecto=(repo_canonico, "trusted"))
        assert por_id(ctx)["codex-proyecto"].estado == "OK"
        poner_config_de_codex(ctx, proyecto=(repo_canonico, "trusted"),
                              extra='\n[projects.%s]\ntrust_level = "untrusted"\n' % texto_toml(str(destino)))
        assert por_id(ctx)["codex-proyecto"].estado == "AVISO"


def test_codex_config_que_falta_se_crea_y_la_que_existe_no_se_pisa():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        ruta = raiz / ".codex" / "config.toml"
        ruta.unlink()
        r = por_id(ctx)["codex-config"]
        assert r.estado == "FALTA" and r.arreglo is not None, r
        codigo, salida = correr(["--arreglar", "codex-config"], ctx)
        assert codigo == 0 and "codex-config: OK" in salida, salida
        assert ruta.read_bytes() == b'project_doc_fallback_filenames = ["CLAUDE.md"]\n'
        for propio in ('model = "propio"\n', 'project_doc_fallback_filenames = ["OTRO.md"]\n', "roto = [\n"):
            ruta.write_bytes(propio.encode("utf-8"))
            r = por_id(ctx)["codex-config"]
            assert r.estado == "FALTA" and r.arreglo is None and r.ayuda, (propio, r)
            if "roto" not in propio:
                assert 'project_doc_fallback_filenames = ["CLAUDE.md"]' in r.ayuda, r
            codigo, salida = correr(["--arreglar", "codex-config"], ctx)
            assert codigo == 2 and ruta.read_bytes() == propio.encode("utf-8"), salida
        ruta.write_bytes(b'model = "propio"\nproject_doc_fallback_filenames = ["AGENTS.md", "CLAUDE.md"]\n')
        assert por_id(ctx)["codex-config"].estado == "OK"


def test_codex_agentes_que_faltan_son_falta_y_arreglar_los_deriva_de_su_md():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        shutil.rmtree(raiz / ".codex" / "agents")
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "FALTA" and r.arreglo is not None and ".codex/agents/writer-sql.toml" in r.detalle, r
        codigo, salida = correr(["--arreglar", "codex-agentes"], ctx)
        assert codigo == 0 and "codex-agentes: OK" in salida, salida
        for nombre in ("writer-sql", "revisor-sql", "revisor-diseno"):
            crudo = toml_en(raiz, nombre).read_bytes()
            assert crudo == toml_de_la_plantilla(nombre).encode("utf-8") and b"\r\n" not in crudo, nombre


def test_codex_agentes_lleva_al_toml_la_description_y_los_bloques_del_md():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        md = raiz / ".claude" / "agents" / "writer-sql.md"
        propio = pw().generar("sql", re.sub(r"(?m)^description:.*$", 'description: "Writer propio de capa-a"',
                                            pw().generar("sql").replace("<!-- /instancia:limites -->", "- REGLA PROPIA.\n<!-- /instancia:limites -->", 1), count=1))
        md.write_bytes(propio.encode("utf-8"))
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "FALTA" and "writer-sql.toml" in r.detalle and "revisor" not in r.detalle and r.arreglo, r
        codigo, salida = correr(["--arreglar", "codex-agentes"], ctx)
        assert codigo == 0, salida
        nuevo = toml_en(raiz, "writer-sql").read_text(encoding="utf-8")
        assert 'description = "Writer propio de capa-a"' in nuevo and "- REGLA PROPIA." in nuevo, nuevo
        assert md.read_bytes() == propio.encode("utf-8")


def test_codex_agentes_compara_contra_la_derivacion_y_no_contra_la_version():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        ruta = toml_en(raiz, "writer-sql")
        viejo = resellar_toml(ruta.read_text(encoding="utf-8").replace("`apply_patch`", "`apply-patch`"))
        assert "# odd-ws-plantilla: %d" % pw().version() in viejo
        ruta.write_bytes(viejo.encode("utf-8"))
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "FALTA" and "writer-sql.toml" in r.detalle and r.arreglo, r
        assert correr(["--arreglar", "codex-agentes"], ctx)[0] == 0
        assert ruta.read_bytes() == toml_de_la_plantilla("writer-sql").encode("utf-8")


def test_codex_agentes_editado_a_mano_es_aviso_y_arreglar_no_lo_pisa():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        editado = toml_en(raiz, "revisor-sql").read_text(encoding="utf-8").replace("description = \"", "description = \"Mío: ", 1)
        toml_en(raiz, "revisor-sql").write_bytes(editado.encode("utf-8"))
        ajeno = 'name = "revisor-diseno"\ndescription = "a mano"\ndeveloper_instructions = "x"\n'
        toml_en(raiz, "revisor-diseno").write_bytes(ajeno.encode("utf-8"))
        toml_en(raiz, "writer-sql").unlink()
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "FALTA" and "revisor-sql.toml" in r.detalle and "revisor-diseno.toml" in r.detalle and r.ayuda, r
        assert ".md" in r.ayuda, r
        codigo, salida = correr(["--arreglar", "codex-agentes"], ctx)
        assert codigo == 0 and "codex-agentes: AVISO" in salida, salida
        assert toml_en(raiz, "revisor-sql").read_bytes() == editado.encode("utf-8")
        assert toml_en(raiz, "revisor-diseno").read_bytes() == ajeno.encode("utf-8")
        assert toml_en(raiz, "writer-sql").read_bytes() == toml_de_la_plantilla("writer-sql").encode("utf-8")
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "AVISO" and r.arreglo is None and "writer-sql" not in r.detalle, r
        assert correr([], ctx)[0] == 0


def test_codex_agentes_al_dia_aunque_el_checkout_lo_deje_en_crlf_o_con_bom():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        ruta = toml_en(raiz, "writer-sql")
        ruta.write_bytes(b"\xef\xbb\xbf" + ruta.read_bytes().replace(b"\n", b"\r\n"))
        assert por_id(ctx)["codex-agentes"].estado == "OK"


def test_codex_agentes_avisa_del_toml_de_un_agente_que_ya_no_existe_sin_borrarlo():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        viejo = toml_de_la_plantilla("writer-sql").replace("writer-sql", "writer-vieja")
        poner(raiz, ".codex/agents/writer-vieja.toml", viejo)
        poner(raiz, ".codex/agents/propio.toml", 'name = "propio"\ndescription = "mío"\ndeveloper_instructions = "x"\n')
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "AVISO" and "writer-vieja.toml" in r.detalle and "propio" not in r.detalle and r.arreglo is None, r
        (raiz / ".claude" / "agents" / "revisor-sql.md").unlink()
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "AVISO" and "revisor-sql.toml" in r.detalle, r
        codigo, salida = correr(["--arreglar", "codex-agentes"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert toml_en(raiz, "writer-vieja").read_bytes() == viejo.encode("utf-8") and toml_en(raiz, "revisor-sql").is_file()


def test_codex_agentes_no_deriva_de_un_md_editado_fuera_de_sus_bloques():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        md = raiz / ".claude" / "agents" / "revisor-sql.md"
        md.write_bytes(md.read_bytes().replace(b"1. **Lee la entrada.**", b"1. **Lee todo.**", 1))
        toml_en(raiz, "revisor-sql").unlink()
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "AVISO" and ".claude/agents/revisor-sql.md" in r.detalle and r.arreglo is None, r
        assert not toml_en(raiz, "revisor-sql").exists()


def test_codex_agentes_con_la_config_rota_es_una_sola_falta():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        (raiz / "workspace.config.json").write_text('{"schema_version": 1, "layers": {}, "hosts": ["codex"]}', encoding="utf-8")
        r = por_id(ctx)["codex-agentes"]
        assert r.estado == "FALTA" and "layers" in r.detalle and r.arreglo is None and r.ayuda, r


def test_arreglar_un_writer_sigue_igual_en_una_instancia_con_codex():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e, hosts=("claude-code", "codex"))
        (raiz / ".claude" / "agents" / "writer-sql.md").unlink()
        codigo, salida = correr(["--arreglar", "writer-sql"], ctx)
        assert codigo == 0 and "writer-sql: OK" in salida, salida
        assert por_id(ctx)["codex-agentes"].estado == "OK"


def poner_hooks_de_codex_del_usuario(ctx, comando, script="writer_guard.py"):
    agregar_hook_de_codex(ctx, comando % ('python "C:/x/scripts/%s"' % script))


def agregar_hook_de_codex(ctx, linea, campo="command"):
    texto = (ctx.home / ".codex" / "config.toml").read_text(encoding="utf-8")
    texto += '\n[[hooks.PreToolUse]]\nmatcher = "Bash"\n[[hooks.PreToolUse.hooks]]\ntype = "command"\n'
    if campo != "command":
        texto += 'command = "echo ok"\n'
    texto += "%s = %s\n" % (campo, texto_toml(linea))
    poner(ctx.home, ".codex/config.toml", texto)


def test_hooks_host_marca_un_host_desconocido_vacio_o_ausente_en_los_hooks_de_codex():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        assert por_id(ctx)["hooks-host"].estado == "OK"
        base = (ctx.home / ".codex" / "config.toml").read_text(encoding="utf-8")
        for comando, rastro in (("%s --host gemini", "gemini"), ("%s --host=", "vacío"), ("%s --host", "vacío"), ("%s --plazo 8", "sin --host"),
                                ("%s --host claude-code", "claude-code")):
            poner(ctx.home, ".codex/config.toml", base)
            poner_hooks_de_codex_del_usuario(ctx, comando)
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and rastro in r.detalle and "writer_guard.py" in r.detalle and "PreToolUse" in r.detalle, (comando, r)
            assert r.arreglo is None and r.ayuda, r
        for comando in ("%s --host codex", "%s --host=codex"):
            poner(ctx.home, ".codex/config.toml", base)
            poner_hooks_de_codex_del_usuario(ctx, comando)
            assert por_id(ctx)["hooks-host"].estado == "OK", comando
        poner(ctx.home, ".codex/config.toml", base)
        poner_hooks_de_codex_del_usuario(ctx, "%s --host gemini", script="otro_script.py")
        assert por_id(ctx)["hooks-host"].estado == "OK"


def test_hooks_host_revisa_los_archivos_de_hooks_del_plugin_de_cada_host_declarado():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e, hosts=("claude-code", "codex"))
        assert por_id(ctx)["hooks-host"].estado == "OK"
        archivo = ctx.plugin / "hooks" / "hooks.codex.json"
        original = archivo.read_text(encoding="utf-8")
        archivo.write_text(original.replace("writer_stop.py\\\" --plazo 50 --host codex", "writer_stop.py\\\" --plazo 50 --host codex2"), encoding="utf-8")
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "hooks/hooks.codex.json SubagentStop" in r.detalle and "codex2" in r.detalle, r
        archivo.write_text(original, encoding="utf-8")
        claude = ctx.plugin / "hooks" / "hooks.json"
        datos = json.loads(claude.read_text(encoding="utf-8"))
        datos["hooks"]["PostToolUse"][1]["hooks"][0]["args"] += ["--host", "codex"]
        claude.write_text(json.dumps(datos), encoding="utf-8")
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "hooks/hooks.json PostToolUse[1]" in r.detalle and "verificar_capa.py" in r.detalle, r
        con_hosts(raiz, ["codex"])
        assert por_id(ctx)["hooks-host"].estado == "OK"
        archivo.unlink()
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "hooks/hooks.codex.json" in r.detalle, r


ITEMS_DE_PI = ["pi", "gentle-shell", "pi-plugin", "pi-confianza", "pi-agentes"]
AGENTES_DE_LA_PLANTILLA = ("writer-sql", "revisor-sql", "revisor-diseno")
USOS_DE_PI = ("agent_before_settle", "appendSystemPrompt", "resources_discover", "isProjectTrusted")


def pim():
    return importlib.import_module("odd_ws.hosts.pi")


def md_de_pi_de_la_plantilla(nombre, armado=None):
    if armado is None and nombre == "revisor-diseno":
        armado = ba().generar_revisor_diseno(host="pi")
    elif armado is None and nombre.startswith("writer-"):
        armado = pw().generar(nombre[len("writer-"):], host="pi")
    elif armado is None:
        armado = ba().generar_revisor(nombre[len("revisor-"):], host="pi")
    return pim().md(pw().agente(armado))


def md_de_pi_en(raiz, nombre):
    return raiz / ".pi" / "agents" / ("%s.md" % nombre)


def resellar_md_de_pi(texto):
    sello = pim().huella(texto)
    return "\n".join("# odd-ws-hash: " + sello if linea.startswith("# odd-ws-hash:") else linea for linea in texto.split("\n"))


def aislado(ctx):
    return ctx.home / ".gentle-shell" / "agent"


def de_pi(ctx):
    return ctx.home / ".pi" / "agent"


def gentle_shell_dice(ctx, pi="1.5.2", modo="isolated", home=None):
    return 0, "gentle-shell 4.7.0\npi %s\nhome %s %s\n" % (pi, modo, home or aislado(ctx))


def home_de_la_maquina(e):
    ajenas = [padre for padre in Path(os.path.realpath(e.base)).parents if (padre / ".agents" / "skills").exists()]
    assert len(ajenas) <= 1, "más de una carpeta arriba del temporal tiene .agents/skills, y Pi pediría confianza: %r" % ajenas
    return str(ajenas[0]) if ajenas else str(e.base / "home")


MANIFIESTO_DE_F2F = {"name": "odd-ws", "pi": {"extensions": ["shim/pi.ts"]}}
SCRIPTS_DE_LOS_HOOKS = ("verificar_capa.py", "writer_guard.py", "guard_comandos.py", "writer_stop.py", "revisar_turno.py")


def como_paquete_de_pi(carpeta, manifiesto=MANIFIESTO_DE_F2F):
    shutil.copytree(AQUI.parent / "hooks", carpeta / "hooks", dirs_exist_ok=True)
    poner(carpeta, "shim/pi.ts", "export default function () {}\n")
    for script in SCRIPTS_DE_LOS_HOOKS:
        poner(carpeta, "scripts/" + script, "")
    if manifiesto is not None:
        poner(carpeta, "package.json", json.dumps(manifiesto))
    return carpeta


def falso_de_pi(e, raiz, version="1.5.2\n", gentle=True, **extra):
    respuestas = {**extra.pop("respuestas", {}), ("pi", "--version"): (0, version) if version else None}
    ctx = con_hooks_del_plugin(Falso(e.base, cwd=raiz, respuestas=respuestas, **extra))
    ctx.entorno = {"HOME": home_de_la_maquina(e)}
    como_paquete_de_pi(ctx.plugin)
    ctx.respuestas[("gentle-shell", "--version")] = gentle_shell_dice(ctx) if gentle is True else gentle or None
    return ctx


def poner_paquetes(home, *paquetes):
    return poner(home, "settings.json", json.dumps({"packages": list(paquetes)}))


def instancia_pi_sana(e, hosts=("pi",)):
    raiz = con_hosts(e.instancia(json.dumps({"plugin_root": str(e.base / "plugin-instalado")})), list(hosts))
    poner_agentes(raiz)
    poner(raiz, ".claude/skills/criterios/SKILL.md", skill_con("criterios"))
    poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql"))
    for nombre in AGENTES_DE_LA_PLANTILLA:
        poner(raiz, ".pi/agents/%s.md" % nombre, md_de_pi_de_la_plantilla(nombre))
    ctx = falso_de_pi(e, raiz)
    poner_paquetes(aislado(ctx), str(ctx.plugin))
    return raiz, ctx


def arbol_de(*carpetas):
    return {str(ruta): ruta.read_bytes() for carpeta in carpetas if carpeta.is_dir() for ruta in sorted(carpeta.rglob("*")) if ruta.is_file()}


def test_una_instancia_pi_sana_da_ok_en_todos_sus_items_en_su_orden():
    for hosts, items, hooks in ((("pi",), ITEMS_DE_PI, "10 hooks de pi, cada uno con el --host de su archivo"),
                                (("claude-code", "pi"), ["claude", "marketplace", *ITEMS_DE_PI],
                                 "19 hooks de claude-code, pi, cada uno con el --host de su archivo")):
        with Escenario() as e:
            raiz, ctx = instancia_pi_sana(e, hosts)
            r = por_id(ctx)
            ids = list(r)
            assert ids[ids.index("git-credenciales") + 1:ids.index("hooks-host") + 1] == [*items, "hooks-host"], (hosts, ids)
            assert all(r[i].estado == "OK" for i in ITEMS_DE_PI + ["hooks-host"]), {i: r[i] for i in ITEMS_DE_PI + ["hooks-host"]}
            assert r["pi"].detalle == "1.5.2" and r["hooks-host"].detalle == hooks, (r["pi"], r["hooks-host"])
            for parte in ("4.7.0", "pi 1.5.2", "isolated", str(aislado(ctx))):
                assert parte in r["gentle-shell"].detalle, (parte, r["gentle-shell"])
            assert str(aislado(ctx) / "settings.json") in r["pi-plugin"].detalle and str(ctx.plugin) in r["pi-plugin"].detalle, r["pi-plugin"]
            assert "3 .md de .pi/agents al día" in r["pi-agentes"].detalle, r["pi-agentes"]
            assert not [i for i in ids if i.startswith("codex")], ids
            codigo, salida = correr([], ctx)
            assert codigo == 0, salida


def test_sin_pi_declarado_no_sale_ningun_item_de_pi():
    for hosts in (None, ["claude-code"], ["claude-code", "codex"], ["codex"]):
        with Escenario() as e:
            raiz = instancia_sana(e) if hosts is None else con_hosts(instancia_sana(e), hosts)
            ctx = falso_de_pi(e, raiz)
            ids = list(por_id(ctx))
            assert not set(ITEMS_DE_PI) & set(ids), (hosts, ids)
            assert ("pi", "--version") not in ctx.llamadas and ("gentle-shell", "--version") not in ctx.llamadas, (hosts, ctx.llamadas)


def test_pi_menor_que_la_minima_es_aviso_con_lo_que_usa_odd_ws_e_igual_o_mayor_es_ok():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        r = por_id(falso_de_pi(e, raiz, version="1.4.9\n"))["pi"]
        assert r.estado == "AVISO" and "1.4.9" in r.detalle and "1.5.0" in r.detalle and r.ayuda and r.arreglo is None, r
        assert all(uso in r.detalle for uso in USOS_DE_PI), r
        ctx = falso_de_pi(e, raiz, version="1.4.9\n")
        poner_paquetes(aislado(ctx), str(ctx.plugin))
        assert correr([], ctx)[0] == 0
        for version in ("1.5.0\n", "1.5.2\n", "2.0.0\n"):
            assert por_id(falso_de_pi(e, raiz, version=version))["pi"].estado == "OK", version
        for version in ("0.87.0\n", "1.4.0\n"):
            assert por_id(falso_de_pi(e, raiz, version=version))["pi"].estado == "AVISO", version


SIN_AGENT_BEFORE_SETTLE = ("0.87.0", "agent_before_settle", "CHANGELOG", "compuerta")


def test_pi_sin_agent_before_settle_es_falta_porque_la_compuerta_del_writer_no_correria():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        ctx = falso_de_pi(e, raiz, version="0.86.3\n")
        r = por_id(ctx)["pi"]
        assert r.estado == "FALTA" and "0.86.3" in r.detalle and all(parte in r.detalle for parte in SIN_AGENT_BEFORE_SETTLE), r
        assert "1.5.0" in r.ayuda and r.arreglo is None and r.comando is None, r
        assert por_id(ctx)["pi-plugin"].estado == "OK", "un Pi viejo sigue instalado: lo de la máquina se revisa"
        assert correr([], ctx)[0] == 1


def test_el_pi_que_reporta_gentle_shell_sigue_el_mismo_corte():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        for pi, estado in (("0.86.3", "FALTA"), ("0.87.0", "AVISO"), ("1.4.9", "AVISO"), ("1.5.0", "OK")):
            r = por_id(falso_de_pi(e, raiz, gentle=gentle_shell_dice(ctx, pi=pi)))["gentle-shell"]
            assert r.estado == estado and pi in r.detalle, (pi, r)
            r = por_id(falso_de_pi(e, raiz, version=None, gentle=gentle_shell_dice(ctx, pi=pi)))["pi"]
            assert r.estado == estado and r.detalle.startswith(pi) and "gentle-shell" in r.detalle, (pi, r)
            if estado == "FALTA":
                assert all(parte in r.detalle for parte in SIN_AGENT_BEFORE_SETTLE) and "1.5.0" in r.ayuda, r


def test_pi_ausente_es_falta_y_lo_de_la_maquina_no_aplica():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        ctx = falso_de_pi(e, raiz, version=None, gentle=False)
        r = por_id(ctx)
        assert (r["pi"].estado, r["pi"].detalle) == ("FALTA", "pi no está instalado"), r["pi"]
        assert "npm i -g" in r["pi"].ayuda and "1.5.0" in r["pi"].ayuda, r["pi"]
        assert all((r[i].estado, r[i].detalle) == ("NO APLICA", "pi no está instalado") for i in ("gentle-shell", "pi-plugin", "pi-confianza")), r
        assert r["pi-agentes"].estado == "OK", r["pi-agentes"]
        assert correr([], ctx)[0] == 1


def test_pi_que_no_se_puede_ejecutar_o_cuya_version_no_se_lee_no_dice_que_no_esta():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        ruta = "C:/npm/pi.CMD"
        ctx = falso_de_pi(e, raiz, respuestas={(ruta, "--version"): None}, which={"pi": ruta})
        r = por_id(ctx)
        assert (r["pi"].estado, r["pi"].detalle) == ("FALTA", "C:/npm/pi.CMD no se pudo ejecutar"), r["pi"]
        assert r["pi-plugin"].estado == "NO APLICA", r["pi-plugin"]
        ctx = falso_de_pi(e, raiz, respuestas={(ruta, "--version"): (0, "1.5.1\n")}, which={"pi": ruta})
        assert por_id(ctx)["pi"].detalle == "1.5.1" and (ruta, "--version") in ctx.llamadas, ctx.llamadas
        r = por_id(falso_de_pi(e, raiz, version="pi sin numero\n"))["pi"]
        assert r.estado == "AVISO" and "no se pudo leer la versión" in r.detalle, r


def test_sin_pi_en_el_path_vale_el_pi_que_corre_gentle_shell():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        ctx = falso_de_pi(e, raiz, version=None)
        poner_paquetes(aislado(ctx), str(ctx.plugin))
        r = por_id(ctx)
        assert r["pi"].estado == "OK" and r["pi"].detalle.startswith("1.5.2") and "gentle-shell" in r["pi"].detalle, r["pi"]
        assert r["pi-plugin"].estado == "OK" and r["gentle-shell"].estado == "OK", (r["pi-plugin"], r["gentle-shell"])
        ctx = falso_de_pi(e, raiz, version=None, gentle=gentle_shell_dice(ctx, pi="1.4.0"))
        r = por_id(ctx)["pi"]
        assert r.estado == "AVISO" and "1.4.0" in r.detalle and "gentle-shell" in r.detalle and "isProjectTrusted" in r.detalle, r
        ctx = falso_de_pi(e, raiz, version=None, gentle=gentle_shell_dice(ctx, pi="not found"))
        assert (por_id(ctx)["pi"].estado, por_id(ctx)["pi"].detalle) == ("FALTA", "pi no está instalado")


def test_sin_pi_en_el_path_y_con_gentle_shell_roto_el_item_pi_dice_lo_que_paso():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        for respuesta, rastro in (((1, "gentle-shell: pi 1.1.0 is older than 1.2.0\n"), "sale con 1: gentle-shell: pi 1.1.0 is older"),
                                  ((124, "se pasó del tiempo"), "sale con 124: se pasó del tiempo")):
            ctx = falso_de_pi(e, raiz, version=None, gentle=respuesta)
            r = por_id(ctx)
            assert r["pi"].estado == "FALTA" and "pi no está en el PATH" in r["pi"].detalle and rastro in r["pi"].detalle, (respuesta, r["pi"])
            assert r["pi"].ayuda and r["pi-plugin"].estado == "NO APLICA", (respuesta, r["pi-plugin"])


def test_gentle_shell_ausente_o_raro_es_aviso_porque_sin_el_el_writer_no_tiene_compuerta():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        ctx = falso_de_pi(e, raiz, gentle=False)
        poner_paquetes(de_pi(ctx), str(ctx.plugin))
        r = por_id(ctx)
        g = r["gentle-shell"]
        assert g.estado == "AVISO" and "gentle-shell no está instalado" in g.detalle and "compuerta" in g.detalle, g
        assert "npm i -g gentle-pi" in g.ayuda and g.arreglo is None and g.comando is None, g
        assert r["pi-plugin"].estado == "OK" and str(de_pi(ctx)) in r["pi-plugin"].detalle, r["pi-plugin"]
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida
        for respuesta, rastro in ((gentle_shell_dice(ctx, pi="1.4.0"), "1.4.0"), (gentle_shell_dice(ctx, pi="not found"), "not found"),
                                  ((1, "gentle-shell: algo se rompió\n"), "sale con 1"), ((0, "sin numeros\n"), "no se pudo leer")):
            g = por_id(falso_de_pi(e, raiz, gentle=respuesta))["gentle-shell"]
            assert g.estado == "AVISO" and rastro in g.detalle and g.ayuda, (respuesta, g)


def test_pi_plugin_se_busca_en_el_home_activo_de_gentle_shell():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        (aislado(ctx) / "settings.json").unlink()
        poner_paquetes(de_pi(ctx), str(ctx.plugin))
        antes = arbol_de(ctx.home, raiz)
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and str(aislado(ctx) / "settings.json") in r.detalle and str(de_pi(ctx) / "settings.json") in r.detalle, r
        assert "gentle-shell install" in r.ayuda and "no escribe" in r.ayuda and r.arreglo is None and r.comando is None, r
        codigo, salida = correr(["--arreglar", "pi-plugin"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert arbol_de(ctx.home, raiz) == antes
        ctx.respuestas[("gentle-shell", "--version")] = gentle_shell_dice(ctx, modo="link", home=de_pi(ctx))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "OK" and str(de_pi(ctx) / "settings.json") in r.detalle, r
        propio = e.base / "home-propio"
        poner_paquetes(propio, {"source": str(ctx.plugin)})
        ctx.respuestas[("gentle-shell", "--version")] = gentle_shell_dice(ctx, modo="path", home=propio)
        assert por_id(ctx)["pi-plugin"].estado == "OK"


def test_pi_plugin_sin_gentle_shell_usa_el_home_de_pi_y_respeta_pi_coding_agent_dir():
    with Escenario() as e:
        raiz, _ = instancia_pi_sana(e)
        ctx = falso_de_pi(e, raiz, gentle=False)
        assert por_id(ctx)["pi-plugin"].estado == "FALTA"
        otro = e.base / "otro-home"
        poner_paquetes(otro, str(ctx.plugin))
        ctx.entorno = {"PI_CODING_AGENT_DIR": str(otro)}
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "OK" and str(otro / "settings.json") in r.detalle, r
        ctx.entorno = {"GENTLE_PI_AGENT_HOME": str(otro)}
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and str(otro / "settings.json") in r.detalle, r


REPO_DE_ODD_WS = "sebasgc0399/odd-workspace-template"


def checkout_de_git(home, manifiesto=None):
    raiz = home / "git" / "github.com" / REPO_DE_ODD_WS
    como_paquete_de_pi(raiz / "plugin", None)
    poner(raiz, "package.json", json.dumps(manifiesto or {"name": "odd-ws", "pi": {"extensions": ["plugin/shim/pi.ts"]}}))
    return raiz


def test_pi_plugin_reconoce_el_plugin_por_su_ruta_y_los_que_no_lo_cargan_son_falta():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        relativa = os.path.relpath(ctx.plugin, aislado(ctx))
        for paquete in (str(ctx.plugin), relativa, {"source": str(ctx.plugin)}, {"source": str(ctx.plugin), "skills": []},
                        str(ctx.plugin / "shim" / "pi.ts"), {"source": str(ctx.plugin / "shim" / "pi.ts"), "extensions": []}):
            poner_paquetes(aislado(ctx), "npm:otro-paquete", paquete)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "OK", (paquete, r)
        for paquete in ("npm:odd-ws", "git:github.com/otro/odd-workspace-template", "https://github.com/sebasgc0399/odd-workspace-template-fork",
                        str(e.base / "no-existe"), str(raiz), {"source": 7}, 7, {"source": str(ctx.plugin), "extensions": []}):
            poner_paquetes(aislado(ctx), paquete)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA", (paquete, r)
        poner_paquetes(aislado(ctx), {"source": str(ctx.plugin), "extensions": []})
        assert "extensions" in por_id(ctx)["pi-plugin"].detalle
        poner_paquetes(aislado(ctx), "~/../plugin-instalado")
        ctx.entorno = {"HOME": str(e.base / "home")}
        assert por_id(ctx)["pi-plugin"].estado == "OK", "la ~ es HOME, como en Pi"
        ctx.entorno = {"HOME": str(e.base / "otra" / "home")}
        assert por_id(ctx)["pi-plugin"].estado == "FALTA"


def test_pi_plugin_con_una_fuente_git_mira_el_checkout_que_clona_pi():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        fuentes = ("git:github.com/" + REPO_DE_ODD_WS, "git:github.com/%s@v0.6.0" % REPO_DE_ODD_WS, "https://github.com/%s.git" % REPO_DE_ODD_WS,
                   "git:git@github.com:%s.git@main" % REPO_DE_ODD_WS, "ssh://git@github.com/" + REPO_DE_ODD_WS)
        for fuente in fuentes:
            poner_paquetes(aislado(ctx), fuente)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA" and "clona" in r.detalle, (fuente, r)
        checkout = checkout_de_git(aislado(ctx))
        for fuente in fuentes:
            poner_paquetes(aislado(ctx), fuente)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "AVISO" and "otra copia" in r.detalle and str(checkout / "plugin") in r.detalle, (fuente, r)
        poner(checkout, "package.json", json.dumps({"name": "odd-ws"}))
        poner_paquetes(aislado(ctx), fuentes[0])
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "pi.extensions" in r.detalle, r


def test_pi_plugin_las_fuentes_que_pi_no_toma_como_git_son_rutas_que_no_existen():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        checkout_de_git(aislado(ctx))
        for fuente in ("github:" + REPO_DE_ODD_WS, "ssh:git@github.com:" + REPO_DE_ODD_WS, "git@github.com:%s.git" % REPO_DE_ODD_WS):
            poner_paquetes(aislado(ctx), fuente)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA" and "ruta local" in r.detalle and "git:" in r.detalle, (fuente, r)
        for fuente in ("git:" + REPO_DE_ODD_WS, "https://www.github.com/" + REPO_DE_ODD_WS, "https://github.com/%s/tree/main" % REPO_DE_ODD_WS):
            poner_paquetes(aislado(ctx), fuente)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA" and "no se puede decidir" in r.detalle, (fuente, r)


RAIZ_DEL_REPO = AQUI.parent.parent
CARPETAS_QUE_LEE_PI = ("hooks", "shim", "skills")


def copia_del_repo(destino):
    destino.mkdir(parents=True, exist_ok=True)
    for archivo in RAIZ_DEL_REPO.iterdir():
        if archivo.is_file():
            shutil.copy2(archivo, destino / archivo.name)
    for carpeta in CARPETAS_QUE_LEE_PI:
        shutil.copytree(RAIZ_DEL_REPO / "plugin" / carpeta, destino / "plugin" / carpeta)
    return destino


def test_pi_plugin_con_el_paquete_real_por_la_ruta_del_clon_es_ok():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        clon = copia_del_repo(e.base / "clon de odd-ws")
        ctx.plugin = clon / "plugin"
        shim = clon / "plugin" / "shim" / "pi.ts"
        for paquete in (str(clon), os.path.relpath(clon, aislado(ctx)), {"source": str(clon)}, {"source": str(clon), "skills": []}):
            poner_paquetes(aislado(ctx), paquete)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "OK" and str(shim) in r.detalle, (paquete, r)
        poner_paquetes(aislado(ctx), str(clon / "plugin"))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "la carpeta plugin/" in r.detalle and "la raíz del repositorio, %s," % clon in r.detalle, r
        poner_paquetes(aislado(ctx), str(clon / "plugin"), str(clon))
        assert por_id(ctx)["pi-plugin"].estado == "OK"


def test_pi_plugin_con_el_paquete_real_por_git_es_ok():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        checkout = copia_del_repo(aislado(ctx) / "git" / "github.com" / REPO_DE_ODD_WS)
        ctx.plugin = checkout / "plugin"
        for fuente in ("git:github.com/%s@odd-ws--v0.6.0" % REPO_DE_ODD_WS, "git:github.com/" + REPO_DE_ODD_WS,
                       "https://github.com/%s.git" % REPO_DE_ODD_WS):
            poner_paquetes(aislado(ctx), fuente)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "OK" and str(checkout / "plugin" / "shim" / "pi.ts") in r.detalle and fuente in r.detalle, (fuente, r)


def test_pi_plugin_no_cuenta_npm_y_dice_que_odd_ws_se_instala_por_git_o_por_ruta():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        instalado = copia_del_repo(aislado(ctx) / "npm" / "node_modules" / "odd-ws")
        ctx.plugin = instalado / "plugin"
        for fuente in ("npm:odd-ws", "npm:odd-ws@0.5.0", "npm:@alguien/odd-ws", "npm:odd-workspace-template"):
            poner_paquetes(aislado(ctx), fuente)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA" and fuente in r.detalle and "npm" in r.detalle, (fuente, r)
            assert "por git" in r.detalle and "por la ruta de un clon" in r.detalle, (fuente, r)
        poner_paquetes(aislado(ctx), "npm:otro-paquete")
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "npm:otro-paquete" not in r.detalle, r
        poner_paquetes(aislado(ctx), "npm:odd-ws", str(instalado))
        assert por_id(ctx)["pi-plugin"].estado == "OK"


def test_pi_plugin_sin_manifiesto_de_pi_no_carga_el_shim_y_es_falta():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        (ctx.plugin / "package.json").unlink()
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "pi.extensions" in r.detalle and "extensions/" in r.detalle and "F2f" not in r.detalle, r
        poner(ctx.plugin, "extensions/otra/index.ts", "")
        assert por_id(ctx)["pi-plugin"].estado == "FALTA"
        for manifiesto, estado in (({"pi": {"skills": ["skills"]}}, "FALTA"), ({"pi": {"extensions": ["shim"]}}, "OK"),
                                   ({"pi": {"extensions": ["./shim/pi.ts"]}}, "OK"), ({"pi": {"extensions": ["shim/pi.ts", "!shim/pi.ts"]}}, "FALTA"),
                                   ({"pi": {"extensions": "shim/pi.ts"}}, "FALTA"), ({"pi": {"extensions": []}}, "FALTA")):
            poner(ctx.plugin, "package.json", json.dumps(manifiesto))
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == estado, (manifiesto, r)
        poner(ctx.plugin, "package.json", json.dumps({"pi": {"extensions": ["shim/*.ts"]}}))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "no se puede decidir" in r.detalle, r
        poner(ctx.plugin, "package.json", "{roto")
        assert por_id(ctx)["pi-plugin"].estado == "FALTA"


def test_pi_plugin_sigue_los_filtros_de_extensions_como_pi():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        for filtro, estado in ((["-shim/pi.ts"], "FALTA"), (["!**/*.ts"], "FALTA"), (["otro/x.ts"], "FALTA"), ([], "FALTA"),
                               (["+shim/pi.ts"], "OK"), (["shim/pi.ts"], "OK"), (["**/*.ts"], "OK"), (["*.ts"], "OK"), (["shim/*"], "OK"),
                               (["!*.ts", "+shim/pi.ts"], "OK"), (["+shim/pi.ts", "-shim/pi.ts"], "FALTA"), (["-./shim/pi.ts"], "FALTA"),
                               (["!.shim/*"], "OK"), (["!shim/p?.ts"], "FALTA"), (["!s*.ts"], "OK"), (["!**/.*/pi.ts"], "OK")):
            poner_paquetes(aislado(ctx), {"source": str(ctx.plugin), "extensions": filtro})
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == estado, (filtro, r)
            if estado == "FALTA":
                assert "extensions" in r.detalle, (filtro, r)
        poner_paquetes(aislado(ctx), {"source": str(ctx.plugin), "extensions": ["!shim/{pi,x}.ts"]})
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "no se puede decidir" in r.detalle, r


def test_pi_plugin_con_autoload_false_solo_carga_lo_que_dicen_sus_patrones():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        for entrada, estado in (({"autoload": False}, "FALTA"), ({"autoload": False, "extensions": []}, "FALTA"),
                                ({"autoload": False, "extensions": ["+shim/pi.ts"]}, "OK"), ({"autoload": False, "extensions": ["shim/pi.ts"]}, "OK"),
                                ({"autoload": False, "extensions": ["-shim/pi.ts"]}, "FALTA"),
                                ({"autoload": False, "extensions": ["shim/pi.ts", "!shim/pi.ts"]}, "FALTA")):
            poner_paquetes(aislado(ctx), {"source": str(ctx.plugin), **entrada})
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == estado, (entrada, r)
        poner_paquetes(aislado(ctx), {"source": str(ctx.plugin), "autoload": False})
        assert "autoload" in por_id(ctx)["pi-plugin"].detalle


def confiar(ctx, raiz, decision=True):
    poner(aislado(ctx), "trust.json", json.dumps({os.path.realpath(raiz): decision}))


def test_pi_plugin_la_entrada_del_proyecto_con_confianza_reemplaza_la_del_home():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        relativa = os.path.relpath(ctx.plugin, raiz / ".pi")
        for del_proyecto in ({"source": str(ctx.plugin), "extensions": []}, {"source": relativa, "extensions": ["-shim/pi.ts"]},
                             {"source": str(ctx.plugin), "autoload": False, "extensions": ["-shim/pi.ts"]}):
            poner(raiz, ".pi/settings.json", json.dumps({"packages": [del_proyecto]}))
            confiar(ctx, raiz)
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA" and ".pi/settings.json" in r.detalle, (del_proyecto, r)
            confiar(ctx, raiz, False)
            assert por_id(ctx)["pi-plugin"].estado == "OK", "sin confianza Pi no lee el proyecto y vale el home"
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [{"source": relativa, "autoload": False, "extensions": ["+shim/pi.ts"]}]}))
        confiar(ctx, raiz)
        assert por_id(ctx)["pi-plugin"].estado == "OK"
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [relativa, {"source": str(ctx.plugin), "extensions": []}]}))
        assert por_id(ctx)["pi-plugin"].estado == "FALTA", "entre dos del proyecto con la misma identidad gana la última"


def test_pi_plugin_con_la_misma_fuente_git_en_el_proyecto_y_en_el_home_gana_la_del_proyecto():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        fuente = "git:github.com/" + REPO_DE_ODD_WS
        checkout_de_git(aislado(ctx))
        poner_paquetes(aislado(ctx), fuente)
        confiar(ctx, raiz)
        assert por_id(ctx)["pi-plugin"].estado == "AVISO", "el checkout del home carga el shim"
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [fuente + "@v0.6.0"]}))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "clona" in r.detalle and ".pi/settings.json" in r.detalle, "gana la del proyecto, que no está clonada"
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [{"source": fuente, "autoload": False, "extensions": ["-plugin/shim/pi.ts"]}]}))
        assert por_id(ctx)["pi-plugin"].estado == "FALTA", "el delta del proyecto se aplica sobre el checkout del home"
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [{"source": fuente, "autoload": False, "extensions": ["+plugin/shim/pi.ts"]}]}))
        assert por_id(ctx)["pi-plugin"].estado == "AVISO"


def test_pi_plugin_solo_en_el_proyecto_cuenta_solo_con_confianza():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        poner_paquetes(aislado(ctx))
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [os.path.relpath(ctx.plugin, raiz / ".pi")]}))
        for preparar in (lambda: confiar(ctx, raiz, False), lambda: (aislado(ctx) / "trust.json").unlink()):
            preparar()
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA" and ".pi/settings.json" in r.detalle and "confianza" in r.detalle and "home" in r.detalle, r
            assert "/trust" in r.ayuda, r
        poner(aislado(ctx), "settings.json", json.dumps({"packages": [], "defaultProjectTrust": "always"}))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "OK" and ".pi/settings.json" in r.detalle and "confianza" in r.detalle, r
        poner_paquetes(aislado(ctx))
        confiar(ctx, raiz)
        assert por_id(ctx)["pi-plugin"].estado == "OK"


def test_pi_plugin_avisa_si_pi_carga_otra_copia_del_plugin():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        copia = como_paquete_de_pi(e.base / "otra-copia")
        poner_paquetes(aislado(ctx), str(copia))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "AVISO" and "otra copia" in r.detalle and str(copia) in r.detalle and str(ctx.plugin) in r.detalle, r


def test_pi_plugin_acepta_el_paquete_del_proyecto_y_no_lee_un_settings_roto_como_vacio():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        (aislado(ctx) / "settings.json").unlink()
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [os.path.relpath(ctx.plugin, raiz / ".pi")]}))
        confiar(ctx, raiz)
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "OK" and ".pi/settings.json" in r.detalle and "confianza" in r.detalle, r
        poner(aislado(ctx), "settings.json", "{roto")
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "no se puede leer" in r.detalle and str(aislado(ctx) / "settings.json") in r.detalle and r.ayuda, r
        assert (aislado(ctx) / "settings.json").read_bytes() == b"{roto"


def sombra_del_plugin(ctx, nombre="enlace-al-plugin"):
    enlace = ctx.plugin.parent / nombre
    if not enlazar(enlace, ctx.plugin):
        return None
    assert os.path.realpath(enlace) == os.path.realpath(ctx.plugin)
    return enlace


def test_pi_plugin_agrupa_por_la_ruta_real_y_la_primera_copia_deshabilitada_por_un_enlace_es_falta():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        enlace = sombra_del_plugin(ctx)
        if enlace is None:
            return
        poner_paquetes(aislado(ctx), {"source": str(enlace), "extensions": ["-shim/pi.ts"]}, str(ctx.plugin))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "extensions" in r.detalle, ("en un mismo settings gana la primera, que Pi descarta por la ruta real", r)
        poner_paquetes(aislado(ctx), str(ctx.plugin), {"source": str(enlace), "extensions": ["-shim/pi.ts"]})
        assert por_id(ctx)["pi-plugin"].estado == "OK", "con el orden al revés gana la que carga"


def test_pi_plugin_la_copia_del_proyecto_por_un_enlace_tapa_a_la_del_home_con_la_misma_ruta_real():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        enlace = sombra_del_plugin(ctx)
        if enlace is None:
            return
        poner(raiz, ".pi/settings.json", json.dumps({"packages": [{"source": str(enlace), "extensions": ["-shim/pi.ts"]}]}))
        confiar(ctx, raiz)
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA", r
        confiar(ctx, raiz, False)
        assert por_id(ctx)["pi-plugin"].estado == "OK", "sin confianza Pi no lee el proyecto y vale el home"


def test_pi_plugin_una_extension_de_nivel_superior_por_un_enlace_es_la_misma_que_la_del_paquete():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        enlace = sombra_del_plugin(ctx)
        if enlace is None:
            return
        poner(aislado(ctx), "settings.json", json.dumps({"packages": [str(ctx.plugin)], "extensions": [str(enlace / "shim" / "pi.ts")]}))
        r = por_id(ctx)["pi-plugin"]
        assert r.estado == "FALTA" and "nivel superior" in r.detalle, r
        poner(aislado(ctx), "settings.json", json.dumps({"packages": [str(ctx.plugin)], "extensions": [str(ctx.plugin / "shim" / "pi.ts")]}))
        assert por_id(ctx)["pi-plugin"].estado == "FALTA", "el mismo archivo por su ruta directa ya era FALTA"


def test_pi_plugin_un_settings_con_nan_o_infinity_no_lo_lee_pi_y_es_falta():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        for constante in ("NaN", "Infinity", "-Infinity"):
            poner(aislado(ctx), "settings.json", '{"packages": [%s], "x": %s}' % (json.dumps(str(ctx.plugin)), constante))
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == "FALTA" and "no se puede leer" in r.detalle and constante.lstrip("-") in r.detalle, (constante, r)
        poner(aislado(ctx), "settings.json", json.dumps({"packages": [str(ctx.plugin)], "x": 1.5}))
        assert por_id(ctx)["pi-plugin"].estado == "OK"


def test_pi_plugin_un_filtro_con_una_url_file_se_normaliza_como_lo_hace_pi():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        shim = ctx.plugin / "shim" / "pi.ts"
        url = "file:///" + str(shim).replace("\\", "/").lstrip("/")
        for filtro, estado in ((["-" + url], "FALTA"), (["!" + url], "FALTA"), (["+" + url], "OK"),
                               (["-" + url.replace("/shim/pi.ts", "/shim/otro.ts")], "OK")):
            poner_paquetes(aislado(ctx), {"source": str(ctx.plugin), "extensions": filtro})
            r = por_id(ctx)["pi-plugin"]
            assert r.estado == estado, (filtro, r)


def test_gentle_shell_avisa_si_la_instancia_es_una_subcarpeta_de_su_repo_y_no_si_es_su_raiz():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        ctx.respuestas[("git", "-C", str(raiz), "rev-parse", "--show-toplevel")] = (0, str(raiz.parent) + "\n")
        r = por_id(ctx)["gentle-shell"]
        assert r.estado == "AVISO" and str(raiz.parent) in r.detalle and "writers" in r.detalle and r.ayuda, r
        assert por_id(ctx)["pi-plugin"].estado == "OK", "el aviso es solo del ítem gentle-shell"
        codigo, salida = correr([], ctx)
        assert codigo == 0, "un AVISO no hace fallar el doctor: " + salida
        ctx.respuestas[("git", "-C", str(raiz), "rev-parse", "--show-toplevel")] = (0, str(raiz) + "\n")
        assert por_id(ctx)["gentle-shell"].estado == "OK"
        ctx.respuestas[("git", "-C", str(raiz), "rev-parse", "--show-toplevel")] = (128, "fatal: not a git repository\n")
        assert por_id(ctx)["gentle-shell"].estado == "OK"
        poner(aislado(ctx), "settings.json", json.dumps({"packages": "no es una lista"}))
        poner(raiz, ".pi/settings.json", json.dumps({}))
        assert por_id(ctx)["pi-plugin"].estado == "FALTA"


def test_pi_confianza_sin_recursos_que_la_pidan_y_sin_decision_es_ok():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        r = por_id(ctx)["pi-confianza"]
        assert r.estado == "OK" and "no tiene recursos que pidan confianza" in r.detalle, r


def test_pi_confianza_avisa_un_no_confiar_guardado_para_la_raiz_o_su_padre_mas_cercano():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        canonica = os.path.realpath(raiz)
        trust = aislado(ctx) / "trust.json"
        for decisiones, estado in (({canonica: False}, "AVISO"), ({canonica.upper(): False}, "AVISO"),
                                   ({os.path.dirname(canonica): False}, "AVISO"), ({canonica: True, os.path.dirname(canonica): False}, "OK"),
                                   ({canonica: None, os.path.dirname(canonica): True}, "OK"), ({canonica: True}, "OK")):
            poner(aislado(ctx), "trust.json", json.dumps(decisiones))
            antes = trust.read_bytes()
            r = por_id(ctx)["pi-confianza"]
            assert r.estado == estado, (decisiones, r)
            if estado == "AVISO":
                assert str(trust) in r.detalle and ".claude/skills" in r.detalle and "/trust" in r.ayuda and r.arreglo is None, r
            assert trust.read_bytes() == antes
        assert correr([], ctx)[0] == 0
        poner(de_pi(ctx), "trust.json", json.dumps({canonica: False}))
        poner(aislado(ctx), "trust.json", json.dumps({}))
        assert por_id(ctx)["pi-confianza"].estado == "OK", "solo cuenta el trust.json del home activo"


def test_pi_confianza_con_recursos_que_la_piden_sigue_el_default_del_home():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        poner(raiz, ".pi/settings.json", "{}")
        r = por_id(ctx)["pi-confianza"]
        assert r.estado == "AVISO" and ".pi/settings.json" in r.detalle and "pregunta" in r.detalle, r
        for valor, estado in (("always", "OK"), ("never", "AVISO"), ("ask", "AVISO"), (7, "AVISO")):
            poner(aislado(ctx), "settings.json", json.dumps({"packages": [str(ctx.plugin)], "defaultProjectTrust": valor}))
            r = por_id(ctx)["pi-confianza"]
            assert r.estado == estado and ("defaultProjectTrust" in r.detalle or valor == 7), (valor, r)
        poner(aislado(ctx), "trust.json", json.dumps({os.path.realpath(raiz): True}))
        assert por_id(ctx)["pi-confianza"].estado == "OK"
        (raiz / ".pi" / "settings.json").unlink()
        (aislado(ctx) / "trust.json").unlink()
        poner(raiz.parent, ".agents/skills/x/SKILL.md", "x")
        de_un_padre = os.path.join(os.path.realpath(raiz.parent), ".agents", "skills")
        r = por_id(ctx)["pi-confianza"]
        assert r.estado == "AVISO" and de_un_padre in r.detalle, r
        ctx.entorno = {"HOME": str(raiz.parent)}
        assert de_un_padre not in por_id(ctx)["pi-confianza"].detalle, "las skills personales de HOME no piden confianza, como en Pi"


def test_pi_confianza_con_un_trust_json_que_pi_no_lee_es_aviso():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        for roto in ("{roto", "[]", json.dumps({os.path.realpath(raiz): 1}), b"\xff\xfe"):
            poner(aislado(ctx), "trust.json", roto)
            r = por_id(ctx)["pi-confianza"]
            assert r.estado == "AVISO" and "no se puede leer" in r.detalle and "trust.json" in r.detalle, (roto, r)
        poner(aislado(ctx), "trust.json", b"\xef\xbb\xbf" + json.dumps({os.path.realpath(raiz): True}).encode("utf-8"))
        assert por_id(ctx)["pi-confianza"].estado == "OK"


def test_pi_agentes_que_faltan_son_falta_y_arreglar_los_deriva_de_su_md():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        shutil.rmtree(raiz / ".pi")
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "FALTA" and r.arreglo is not None and ".pi/agents/writer-sql.md" in r.detalle, r
        codigo, salida = correr(["--arreglar", "pi-agentes"], ctx)
        assert codigo == 0 and "pi-agentes: OK" in salida, salida
        for nombre in AGENTES_DE_LA_PLANTILLA:
            crudo = md_de_pi_en(raiz, nombre).read_bytes()
            assert crudo == md_de_pi_de_la_plantilla(nombre).encode("utf-8") and b"\r\n" not in crudo, nombre


def test_la_linea_del_bootstrap_doctor_arreglar_pi_agentes_deriva_los_md_con_rc_0():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e, ("claude-code", "pi"))
        md = raiz / ".claude" / "agents" / "writer-sql.md"
        propio = pw().generar("sql", re.sub(r"(?m)^description:.*$", 'description: "Writer propio de capa-a"', pw().generar("sql"), count=1))
        md.write_bytes(propio.encode("utf-8"))
        shutil.rmtree(raiz / ".pi")
        archivos = {a.ruta: a for a in pim().archivos([pw().agente(ba().armar(n, None, "pi")) for n in AGENTES_DE_LA_PLANTILLA])}
        assert {a.arreglo for a in archivos.values()} == {"pi-agentes"} and "pi-agentes" in por_id(ctx), archivos
        codigo, salida = correr(["--arreglar", "pi-agentes"], ctx)
        assert codigo == 0 and "pi-agentes: OK" in salida, salida
        nuevo = md_de_pi_en(raiz, "writer-sql").read_text(encoding="utf-8")
        assert 'description: "Writer propio de capa-a"' in nuevo and md.read_bytes() == propio.encode("utf-8"), nuevo


def test_pi_agentes_atrasado_con_su_huella_es_falta_y_arreglar_lo_rederiva():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        ruta = md_de_pi_en(raiz, "writer-sql")
        viejo = resellar_md_de_pi(ruta.read_text(encoding="utf-8").replace("`edit` o `write`", "`edit` o `escribir`"))
        assert "# odd-ws-plantilla: %d" % pw().version() in viejo and viejo != ruta.read_text(encoding="utf-8")
        ruta.write_bytes(viejo.encode("utf-8"))
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "FALTA" and "writer-sql.md quedó atrás" in r.detalle and r.arreglo, r
        assert correr(["--arreglar", "pi-agentes"], ctx)[0] == 0
        assert ruta.read_bytes() == md_de_pi_de_la_plantilla("writer-sql").encode("utf-8")


def test_pi_agentes_editado_a_mano_es_aviso_y_arreglar_no_lo_pisa():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        editado = md_de_pi_en(raiz, "revisor-sql").read_text(encoding="utf-8").replace('description: "', 'description: "Mío: ', 1)
        md_de_pi_en(raiz, "revisor-sql").write_bytes(editado.encode("utf-8"))
        ajeno = "---\nname: revisor-diseno\ndescription: a mano\n---\nCuerpo.\n"
        md_de_pi_en(raiz, "revisor-diseno").write_bytes(ajeno.encode("utf-8"))
        md_de_pi_en(raiz, "writer-sql").unlink()
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "FALTA" and "revisor-sql.md se editó a mano" in r.detalle and "revisor-diseno.md" in r.detalle and r.ayuda, r
        assert ".claude/agents" in r.ayuda and "--arreglar pi-agentes" in r.ayuda, r
        codigo, salida = correr(["--arreglar", "pi-agentes"], ctx)
        assert codigo == 0 and "pi-agentes: AVISO" in salida, salida
        assert md_de_pi_en(raiz, "revisor-sql").read_bytes() == editado.encode("utf-8")
        assert md_de_pi_en(raiz, "revisor-diseno").read_bytes() == ajeno.encode("utf-8")
        assert md_de_pi_en(raiz, "writer-sql").read_bytes() == md_de_pi_de_la_plantilla("writer-sql").encode("utf-8")
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "AVISO" and r.arreglo is None and "writer-sql" not in r.detalle, r
        assert correr([], ctx)[0] == 0


def test_pi_agentes_al_dia_aunque_el_checkout_lo_deje_en_crlf_o_con_bom():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        ruta = md_de_pi_en(raiz, "writer-sql")
        ruta.write_bytes(b"\xef\xbb\xbf" + ruta.read_bytes().replace(b"\n", b"\r\n"))
        assert por_id(ctx)["pi-agentes"].estado == "OK"


def test_pi_agentes_avisa_del_md_de_un_agente_que_ya_no_existe_sin_borrarlo():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        viejo = md_de_pi_de_la_plantilla("writer-sql").replace("writer-sql", "writer-vieja")
        poner(raiz, ".pi/agents/writer-vieja.md", viejo)
        poner(raiz, ".pi/agents/propio.md", "---\nname: propio\ndescription: mío\n---\nx\n")
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "AVISO" and "writer-vieja.md" in r.detalle and "propio" not in r.detalle and r.arreglo is None, r
        codigo, salida = correr(["--arreglar", "pi-agentes"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert md_de_pi_en(raiz, "writer-vieja").read_bytes() == viejo.encode("utf-8")


def test_pi_agentes_no_deriva_de_un_md_editado_fuera_de_sus_bloques():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        md = raiz / ".claude" / "agents" / "revisor-sql.md"
        md.write_bytes(md.read_bytes().replace(b"1. **Lee la entrada.**", b"1. **Lee todo.**", 1))
        md_de_pi_en(raiz, "revisor-sql").unlink()
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "AVISO" and ".claude/agents/revisor-sql.md" in r.detalle and r.arreglo is None, r
        assert not md_de_pi_en(raiz, "revisor-sql").exists()


def test_pi_agentes_con_un_md_que_pi_no_acepta_avisa_sin_reventar_y_deriva_los_demas():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        md = raiz / ".claude" / "agents" / "writer-sql.md"
        md.write_bytes(pw().generar("sql", re.sub(r"(?m)^description:.*$", 'description: "\ufeff"', pw().generar("sql"), count=1)).encode("utf-8"))
        shutil.rmtree(raiz / ".pi")
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "FALTA" and "description no vacía" in r.detalle and ".claude/agents/writer-sql.md" in r.detalle, r
        codigo, salida = correr(["--arreglar", "pi-agentes"], ctx)
        assert codigo == 0 and "pi-agentes: AVISO" in salida and "Traceback" not in salida, salida
        assert not md_de_pi_en(raiz, "writer-sql").exists() and md_de_pi_en(raiz, "revisor-sql").is_file()
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "AVISO" and r.arreglo is None and "description no vacía" in r.detalle and r.ayuda, r
        codigo, salida = correr([], ctx)
        assert codigo == 0 and "Traceback" not in salida, salida


def test_pi_agentes_con_la_config_rota_es_una_sola_falta():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        (raiz / "workspace.config.json").write_text('{"schema_version": 1, "layers": {}, "hosts": ["pi"]}', encoding="utf-8")
        r = por_id(ctx)["pi-agentes"]
        assert r.estado == "FALTA" and "layers" in r.detalle and r.arreglo is None and r.ayuda, r
        assert "overlays" not in r.detalle, r


SIN_OVERLAYS = ("el doctor no ve los overlays de herramientas de gentle-shell (#3223), que pueden cambiar las herramientas de "
                "un agente al cargarlo")


def linea_del_doctor(ctx, id_):
    salida = correr([], ctx)[1]
    lineas = [linea for linea in salida.splitlines() if linea.split(" ", 1)[0] == id_]
    assert len(lineas) == 1, salida
    return lineas[0]


def test_la_linea_de_pi_agentes_dice_que_el_doctor_no_ve_los_overlays_de_herramientas():
    with Escenario() as e:
        raiz, ctx = instancia_pi_sana(e)
        assert linea_del_doctor(ctx, "pi-agentes").split(None, 2)[1:] == [
            "OK", "3 .md de .pi/agents al día con su .md de .claude/agents; " + SIN_OVERLAYS]
        poner(raiz, ".pi/agents/writer-vieja.md", md_de_pi_de_la_plantilla("writer-sql").replace("writer-sql", "writer-vieja"))
        linea = linea_del_doctor(ctx, "pi-agentes")
        assert linea.split(None, 2)[1] == "AVISO" and "writer-vieja.md" in linea and linea.endswith("; " + SIN_OVERLAYS), linea
        md_de_pi_en(raiz, "writer-sql").unlink()
        linea = linea_del_doctor(ctx, "pi-agentes")
        assert linea.split(None, 2)[1] == "FALTA" and "writer-sql.md" in linea and linea.endswith("; " + SIN_OVERLAYS), linea


def test_con_pi_declarado_en_windows_python_revisa_el_python_de_pi_y_lo_nombra():
    with Escenario() as e:
        r, sondas = item_python_con_hosts(e, ["pi"], which={"python3": PYTHON3_SANO, "python": None},
                                          respuestas={(PYTHON3_SANO, "-c"): (0, "Python 3.12.4\n")})
        assert (r.estado, r.detalle) == ("FALTA", "python no está en el PATH: los hooks de pi lo llaman por nombre"), r
        assert sondas == [], sondas
    with Escenario() as e:
        r, _ = item_python_con_hosts(e, ["codex", "pi"], which={"python3": PYTHON3_SANO, "python": None})
        assert r.estado == "FALTA" and "los hooks de codex, pi lo llaman por nombre" in r.detalle, r
    with Escenario() as e:
        r, sondas = item_python_con_hosts(e, ["pi"], windows=False, which={"python3": PYTHON3_SANO, "python": None},
                                          respuestas={(PYTHON3_SANO, "-c"): (0, "Python 3.9.6\n")})
        assert (r.estado, sondas) == ("OK", [PYTHON3_SANO]), (r, sondas)


def escribir_hooks_de_pi(ctx, cambiar=None, texto=None):
    archivo = ctx.plugin / "hooks" / "hooks.pi.json"
    datos = json.loads((AQUI.parent / "hooks" / "hooks.pi.json").read_text(encoding="utf-8"))
    if cambiar:
        cambiar(datos)
    archivo.write_text(texto if texto is not None else json.dumps(datos), encoding="utf-8")


def test_hooks_host_de_pi_es_falta_con_un_hooks_pi_json_que_el_shim_rechaza():
    def hook(datos, **cambio):
        datos["hooks"]["tool_call"][1]["hooks"][0].update(cambio)

    casos = ((lambda d: hook(d, script="../writer_guard.py"), "tool_call[1][0]: script"),
             (lambda d: hook(d, script="writer_guard.sh"), "tool_call[1][0]: script"),
             (lambda d: hook(d, timeout=0), "tool_call[1][0]: timeout"), (lambda d: hook(d, timeout="10"), "tool_call[1][0]: timeout"),
             (lambda d: hook(d, timeout=True), "tool_call[1][0]: timeout"),
             (lambda d: d["hooks"]["tool_call"][1].update(tools="bash"), "tool_call[1]: tools"),
             (lambda d: d["hooks"]["tool_call"][1].update(tools=["bash", ""]), "tool_call[1]: tools"),
             (lambda d: d.update(pythonWindows=""), "pythonWindows"), (lambda d: d.update(writer=7), "writer"),
             (lambda d: d["hooks"].update(session_start={}), "session_start"))
    with Escenario() as e:
        _, ctx = instancia_pi_sana(e)
        for cambiar, rastro in casos:
            escribir_hooks_de_pi(ctx, cambiar)
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and "hooks/hooks.pi.json: " + rastro in r.detalle and "shim" in r.detalle, (rastro, r)
            assert pim().AYUDA_HOOKS in r.ayuda and r.arreglo is None and r.comando is None, (rastro, r)
        texto = json.dumps(json.loads((AQUI.parent / "hooks" / "hooks.pi.json").read_text(encoding="utf-8")))
        escribir_hooks_de_pi(ctx, texto=texto.replace('"timeout": 10', '"timeout": NaN', 1))
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "no es JSON" in r.detalle, r
        escribir_hooks_de_pi(ctx)
        assert por_id(ctx)["hooks-host"].estado == "OK"


def test_hooks_host_de_pi_es_falta_con_lo_que_el_shim_acepta_pero_apaga_un_guard():
    casos = ((lambda d: d["hooks"]["tool_call"][2].update(tools=[]),
              ("tool_call[2] tiene tools vacía", "tool_call de bash no corre guard_comandos.py", "tool_call de powershell no corre guard_comandos.py")),
             (lambda d: d["hooks"]["tool_call"].append({"tools": [], "hooks": [{"script": "guard_comandos.py", "args": [], "timeout": 1}]}),
              ("tool_call[3] tiene tools vacía",)),
             (lambda d: d["hooks"]["session_start"][0].update(tools=["bash"]),
              ("session_start[0] tiene tools", "session_start no corre verificar_capa.py")),
             (lambda d: d["hooks"].pop("session_compact"), ("session_compact no corre verificar_capa.py",)),
             (lambda d: d["hooks"]["tool_result"][1].update(tools=["grep"]), ("tool_result de read no corre verificar_capa.py",)),
             (lambda d: d.pop("writer"), ("falta writer",)),
             (lambda d: d.update(writer="^nadie$"), ("writer es '^nadie$'", "^writer-[a-z0-9][a-z0-9-]*$")))
    with Escenario() as e:
        _, ctx = instancia_pi_sana(e)
        for cambiar, rastros in casos:
            escribir_hooks_de_pi(ctx, cambiar)
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and all(rastro in r.detalle for rastro in rastros), (rastros, r)
            assert pim().AYUDA_HOOKS in r.ayuda, r
        escribir_hooks_de_pi(ctx, lambda d: d["hooks"]["tool_call"][0].pop("tools"))
        assert por_id(ctx)["hooks-host"].estado == "OK", "un grupo sin tools corre en toda herramienta y no apaga nada"


def test_hooks_host_de_pi_es_falta_si_bash_background_o_monitor_de_gentle_shell_quedan_sin_guard():
    def sin(*herramientas):
        def cambiar(datos):
            for grupo in datos["hooks"]["tool_call"]:
                grupo["tools"] = [nombre for nombre in grupo.get("tools", []) if nombre not in herramientas]
        return cambiar

    with Escenario() as e:
        _, ctx = instancia_pi_sana(e)
        for herramientas in (("bash_background",), ("monitor",), ("bash_background", "monitor")):
            escribir_hooks_de_pi(ctx, sin(*herramientas))
            r = por_id(ctx)["hooks-host"]
            rastros = ["tool_call de %s no corre %s" % (herramienta, script) for herramienta in herramientas
                       for script in ("writer_guard.py", "guard_comandos.py")]
            assert r.estado == "FALTA" and all(rastro in r.detalle for rastro in rastros), (herramientas, r)
            assert pim().AYUDA_HOOKS in r.ayuda and r.arreglo is None, r
        escribir_hooks_de_pi(ctx)
        assert por_id(ctx)["hooks-host"].estado == "OK"


def test_hooks_host_de_pi_revisa_que_cada_script_exista_y_que_la_compuerta_pueda_seguir():
    otro = {"script": "verificar_capa.py", "args": ["--plazo", "8", "--host", "pi"], "timeout": 10}
    casos = ((lambda d: d["hooks"]["agent_before_settle"][0]["hooks"][0].update(timeout=50),
              ("agent_before_settle[0][0]", "timeout 50", "--plazo 50")),
             (lambda d: d["hooks"]["tool_call"][1]["hooks"][0].update(timeout=5), ("tool_call[1][0]", "timeout 5", "--plazo 8")),
             (lambda d: d["hooks"]["agent_before_settle"].append({"agente": "writer", "hooks": [otro]}),
              ("agent_before_settle", "verificar_capa.py", "seguir")),
             (lambda d: d["hooks"]["agent_before_settle"][0]["hooks"].append(dict(otro, script="writer_stop.py", args=["--plazo", "50", "--host", "pi"],
                                                                                  timeout=60)),
              ("agent_before_settle", "2 hooks")))
    with Escenario() as e:
        _, ctx = instancia_pi_sana(e)
        for cambiar, rastros in casos:
            escribir_hooks_de_pi(ctx, cambiar)
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and all(rastro in r.detalle for rastro in rastros), (rastros, r)
            assert pim().AYUDA_HOOKS in r.ayuda and r.arreglo is None, r
        escribir_hooks_de_pi(ctx)
        assert por_id(ctx)["hooks-host"].estado == "OK"
        (ctx.plugin / "scripts" / "writer_stop.py").unlink()
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "agent_before_settle[0][0]: writer_stop.py no existe en" in r.detalle, r
        escribir_hooks_de_pi(ctx, lambda d: d["hooks"]["tool_call"][1]["hooks"][0].update(timeout=0))
        r = por_id(ctx)["hooks-host"]
        assert "writer_stop.py no existe" not in r.detalle and "el shim no puede leer" in r.detalle, "con la forma rota basta el motivo del shim"


def test_hooks_host_de_pi_revisa_que_el_padre_corra_solo_revisar_turno_y_el_hijo_solo_writer_stop():
    revision = {"script": "revisar_turno.py", "args": ["--plazo", "50", "--host", "pi"], "timeout": 60}
    casos = (
        (lambda d: d["hooks"]["agent_before_settle"].pop(1), ("agent_before_settle del principal no corre revisar_turno.py",)),
        (lambda d: d["hooks"].pop("before_agent_start"), ("before_agent_start del principal no corre revisar_turno.py",)),
        (lambda d: d["hooks"]["agent_before_settle"][0].pop("agente"),
         ("agent_before_settle[0] no tiene agente", "agent_before_settle del writer no corre writer_stop.py")),
        (lambda d: d["hooks"]["agent_before_settle"][1].update(agente="writer"),
         ("agent_before_settle del writer corre 2 hooks (writer_stop.py, revisar_turno.py)", "el writer cierra sin compuerta",
          "agent_before_settle del principal no corre revisar_turno.py")),
        (lambda d: d["hooks"]["agent_before_settle"][0].update(agente="principal"),
         ("agent_before_settle del principal corre 2 hooks (writer_stop.py, revisar_turno.py)", "el turno cierra sin revisión")),
        (lambda d: d["hooks"]["agent_before_settle"][0]["hooks"].append(revision),
         ("agent_before_settle del writer corre 2 hooks", "seguir")),
        (lambda d: d["hooks"]["agent_before_settle"][1]["hooks"][0].update(script="writer_stop.py"),
         ("agent_before_settle del principal corre writer_stop.py: ahí corre solo revisar_turno.py",
          "agent_before_settle del principal no corre revisar_turno.py")),
    )
    with Escenario() as e:
        _, ctx = instancia_pi_sana(e)
        assert por_id(ctx)["hooks-host"].estado == "OK"
        for cambiar, rastros in casos:
            escribir_hooks_de_pi(ctx, cambiar)
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and all(rastro in r.detalle for rastro in rastros), (rastros, r)
            assert pim().AYUDA_HOOKS in r.ayuda and r.arreglo is None, r
        escribir_hooks_de_pi(ctx)
        (ctx.plugin / "scripts" / "revisar_turno.py").unlink()
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "before_agent_start[0][0]: revisar_turno.py no existe en" in r.detalle, r
        assert "agent_before_settle[1][0]: revisar_turno.py no existe en" in r.detalle, r


def test_hooks_host_revisa_que_cada_hook_de_hooks_pi_json_lleve_host_pi():
    with Escenario() as e:
        _, ctx = instancia_codex_sana(e, hosts=("pi",))
        como_paquete_de_pi(ctx.plugin)
        archivo = ctx.plugin / "hooks" / "hooks.pi.json"
        original = json.loads(archivo.read_text(encoding="utf-8"))
        for cambio, rastro in ((["--host", "pi2"], "con --host 'pi2', que no es un host conocido"), ([], "sin --host (corre como claude-code)"),
                               (["--host", "codex"], "con --host codex"), (["--host="], "con --host vacío"),
                               (["--host", "claude-code"], "con --host claude-code")):
            datos = json.loads(json.dumps(original))
            datos["hooks"]["tool_call"][2]["hooks"][0]["args"] = ["--plazo", "8", *cambio]
            archivo.write_text(json.dumps(datos), encoding="utf-8")
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and r.ayuda and r.arreglo is None, (cambio, r)
            assert "hooks/hooks.pi.json tool_call[2][0]: guard_comandos.py %s, y el hook es de pi" % rastro in r.detalle, (cambio, r)
        datos = json.loads(json.dumps(original))
        datos["hooks"]["tool_result"][1]["hooks"][0] = {"script": 7}
        archivo.write_text(json.dumps(datos), encoding="utf-8")
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "hooks/hooks.pi.json tool_result[1][0] no se puede leer" in r.detalle, r
        archivo.write_text(json.dumps(original), encoding="utf-8")
        assert por_id(ctx)["hooks-host"].estado == "OK"
        archivo.unlink()
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "hooks/hooks.pi.json no se puede leer" in r.detalle, r
        codigo, salida = correr([], ctx)
        assert codigo == 1 and "hooks/hooks.pi.json" in salida, salida


def instancia_de_los_dos(e, claude=True, codex=True, marketplace=True):
    raiz, _ = instancia_codex_sana(e, hosts=("claude-code", "codex"))
    poner(raiz, ".claude/skills/criterios/SKILL.md", skill_con("criterios"))
    poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql"))
    respuestas = {} if claude is True else {("claude", "--version"): claude}
    return raiz, falso_de_codex(e, raiz, version="codex-cli 0.167.0\n" if codex else None, respuestas=respuestas, marketplace=marketplace)


def test_con_los_dos_hosts_y_los_dos_cli_instalados_sus_versiones_son_ok():
    with Escenario() as e:
        _, ctx = instancia_de_los_dos(e)
        r = por_id(ctx)
        assert (r["claude"].estado, r["codex"].estado) == ("OK", "OK"), (r["claude"], r["codex"])
        assert correr([], ctx)[0] == 0


def test_con_los_dos_hosts_y_solo_claude_instalado_codex_es_aviso_y_no_hace_fallar():
    with Escenario() as e:
        _, ctx = instancia_de_los_dos(e, codex=False)
        r = por_id(ctx)
        assert r["claude"].estado == "OK", r["claude"]
        assert r["codex"].estado == "AVISO" and r["codex"].detalle.startswith("codex no está instalado") and "claude-code" in r["codex"].detalle, r["codex"]
        assert r["codex"].ayuda and r["codex"].arreglo is None, r["codex"]
        assert all(r[i].estado == "NO APLICA" for i in ("codex-plugin", "codex-hooks", "codex-proyecto")), r
        assert r["codex-config"].estado == "OK" and r["codex-agentes"].estado == "OK", r
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida


def test_con_los_dos_hosts_y_solo_codex_instalado_claude_es_aviso_y_no_hace_fallar():
    with Escenario() as e:
        raiz, ctx = instancia_de_los_dos(e, claude=None, marketplace=False)
        poner(raiz, ".claude/agents/revisor.md", agente_con("revisor", "skills: [personal]\n"))
        r = por_id(ctx)
        assert r["codex"].estado == "OK", r["codex"]
        assert r["claude"].estado == "AVISO" and r["claude"].detalle.startswith("claude no está instalado") and "codex" in r["claude"].detalle, r["claude"]
        for item in ("marketplace", "agentes-skills"):
            assert (r[item].estado, r[item].detalle) == ("NO APLICA", "claude no está instalado"), r[item]
            assert r[item].arreglo is None and r[item].comando is None, r[item]
        assert r["agentes-hooks"].estado == "OK" and r["instancia-plugin"].estado == "AVISO", (r["agentes-hooks"], r["instancia-plugin"])
        codigo, salida = correr([], ctx)
        assert codigo == 0, salida
        codigo, salida = correr(["--arreglar", "marketplace"], ctx)
        assert codigo == 0 and "NO APLICA" in salida and not [l for l in ctx.llamadas if l[:4] == ("claude", "plugin", "marketplace", "add")], salida


def test_lo_de_claude_que_depende_del_cli_sigue_como_hoy_si_claude_esta_o_si_no_hay_ningun_cli():
    for claude, codex in ((True, True), (True, False), (None, False)):
        with Escenario() as e:
            raiz, ctx = instancia_de_los_dos(e, claude=claude, codex=codex, marketplace=False)
            poner(raiz, ".claude/agents/revisor.md", agente_con("revisor", "skills: [personal]\n"))
            r = por_id(ctx)
            assert r["marketplace"].estado == "FALTA" and r["marketplace"].comando, (claude, codex, r["marketplace"])
            assert r["agentes-skills"].estado == "FALTA" and "personal" in r["agentes-skills"].detalle, (claude, codex, r["agentes-skills"])


def test_con_los_dos_hosts_y_ningun_cli_instalado_los_dos_son_falta():
    with Escenario() as e:
        _, ctx = instancia_de_los_dos(e, claude=None, codex=False)
        r = por_id(ctx)
        assert (r["claude"].estado, r["claude"].detalle) == ("FALTA", "claude no está instalado"), r["claude"]
        assert (r["codex"].estado, r["codex"].detalle) == ("FALTA", "codex no está instalado"), r["codex"]
        assert correr([], ctx)[0] == 1


def test_un_cli_instalado_pero_viejo_sigue_en_falta_aunque_el_otro_este_instalado():
    with Escenario() as e:
        raiz, ctx = instancia_de_los_dos(e, claude=(0, "2.1.200 (Claude Code)\n"))
        r = por_id(ctx)
        assert r["claude"].estado == "FALTA" and "2.1.200" in r["claude"].detalle and r["codex"].estado == "OK", (r["claude"], r["codex"])
        r = por_id(falso_de_codex(e, raiz, version="codex-cli 0.143.0\n"))
        assert r["codex"].estado == "FALTA" and "0.143.0" in r["codex"].detalle and r["claude"].estado == "OK", (r["claude"], r["codex"])


def test_con_un_solo_host_declarado_el_cli_que_falta_sigue_en_falta_como_hoy():
    with Escenario() as e:
        raiz = instancia_sana(e)
        ctx = Falso(e.base, cwd=raiz, respuestas={("claude", "--version"): None})
        sin = correr([], ctx)
        r = por_id(ctx)["claude"]
        assert (r.estado, r.detalle) == ("FALTA", "claude no está instalado"), r
        con_hosts(raiz, ["claude-code"])
        assert correr([], ctx) == sin and sin[0] == 1, (sin, correr([], ctx))
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner(raiz, ".claude/agents/revisor.md", agente_con("revisor", "skills: [personal]\n"))
        ctx = Falso(e.base, cwd=raiz, respuestas={("claude", "--version"): None}, marketplace=False)
        sin = correr([], ctx)
        r = por_id(ctx)
        assert r["marketplace"].estado == "FALTA" and r["agentes-skills"].estado == "FALTA", (r["marketplace"], r["agentes-skills"])
        con_hosts(raiz, ["claude-code"])
        assert correr([], ctx) == sin, (sin, correr([], ctx))
    with Escenario() as e:
        raiz, _ = instancia_codex_sana(e)
        r = por_id(falso_de_codex(e, raiz, version=None))["codex"]
        assert (r.estado, r.detalle) == ("FALTA", "codex no está instalado"), r


def test_hooks_host_revisa_tambien_los_hooks_json_que_carga_codex():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        hook = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": 'python "C:/x/scripts/guard_comandos.py" --host gemini'}]}]}}
        for carpeta, rastro in ((ctx.home / ".codex", str(ctx.home / ".codex" / "hooks.json")), (raiz / ".codex", ".codex/hooks.json")):
            poner(carpeta, "hooks.json", json.dumps(hook))
            r = por_id(ctx)["hooks-host"]
            assert r.estado == "FALTA" and rastro + " PreToolUse[0][0]" in r.detalle and "gemini" in r.detalle, (rastro, r)
            (carpeta / "hooks.json").unlink()
        assert por_id(ctx)["hooks-host"].estado == "OK"
        poner(raiz / ".codex", "hooks.json", "{roto")
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "AVISO" and ".codex/hooks.json no se puede leer" in r.detalle, r


def test_hooks_host_ve_el_alias_command_windows_y_las_rutas_de_windows_sin_comillas():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        base = (ctx.home / ".codex" / "config.toml").read_text(encoding="utf-8")
        agregar_hook_de_codex(ctx, r"python C:\x\scripts\guard_comandos.py --host gemini")
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "guard_comandos.py con --host 'gemini'" in r.detalle, r
        poner(ctx.home, ".codex/config.toml", base)
        agregar_hook_de_codex(ctx, r"python C:\x\scripts\writer_stop.py --host=", campo="command_windows")
        r = por_id(ctx)["hooks-host"]
        assert r.estado == "FALTA" and "PreToolUse[0][0] (commandWindows)" in r.detalle and "writer_stop.py con --host vacío" in r.detalle, r


@contextlib.contextmanager
def sin_tomllib():
    previo = sys.modules.get("tomllib", importlib)
    sys.modules["tomllib"] = None
    try:
        yield
    finally:
        if previo is importlib:
            del sys.modules["tomllib"]
        else:
            sys.modules["tomllib"] = previo


def test_sin_tomllib_lo_que_lee_toml_da_una_falta_clara_y_no_revienta():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        with sin_tomllib():
            r = por_id(ctx)
            codigo, salida = correr([], ctx)
        assert codigo == 1, salida
        for item in ("codex-plugin", "codex-config"):
            assert r[item].estado == "FALTA" and "requiere Python 3.11 o más para leer la config de Codex" in r[item].detalle, r[item]
            assert "3.11" in r[item].ayuda and r[item].arreglo is None, r[item]
        for item in ("codex-hooks", "codex-proyecto"):
            assert r[item].estado == "AVISO" and "3.11" in r[item].detalle, r[item]
        assert r["hooks-host"].estado == "AVISO" and "config.toml no se puede leer" in r["hooks-host"].detalle, r["hooks-host"]
        assert r["codex-agentes"].estado == "OK" and r["codex"].estado == "OK", (r["codex-agentes"], r["codex"])


def test_arreglar_codex_agentes_con_un_toml_atrasado_de_solo_lectura_no_revienta():
    with Escenario() as e:
        raiz, ctx = instancia_codex_sana(e)
        ruta = toml_en(raiz, "writer-sql")
        viejo = resellar_toml(ruta.read_text(encoding="utf-8").replace("`apply_patch`", "`apply-patch`"))
        ruta.write_bytes(viejo.encode("utf-8"))
        os.chmod(ruta, stat.S_IREAD)
        try:
            codigo, salida = correr(["--arreglar", "codex-agentes"], ctx)
        finally:
            os.chmod(ruta, stat.S_IWRITE | stat.S_IREAD)
        assert codigo == 1 and "no se pudo escribir" in salida and "codex-agentes: FALTA" in salida, salida
        assert ruta.read_bytes() == viejo.encode("utf-8")


def test_codex_que_existe_pero_no_se_puede_ejecutar_no_dice_que_no_esta_instalado():
    with Escenario() as e:
        raiz, _ = instancia_codex_sana(e)
        ruta = "C:/npm/codex.CMD"
        ctx = falso_de_codex(e, raiz, respuestas={(ruta, "--version"): None}, which={"codex": ruta})
        r = por_id(ctx)
        assert r["codex"].estado == "FALTA" and r["codex"].detalle == "C:/npm/codex.CMD no se pudo ejecutar", r["codex"]
        assert r["codex-plugin"].estado == "NO APLICA", r["codex-plugin"]


def test_hooks_host_no_sale_en_una_instancia_solo_de_claude_code():
    with Escenario() as e:
        ctx = con_hooks_del_plugin(Falso(e.base, cwd=instancia_sana(e)))
        assert "hooks-host" not in por_id(ctx)
        assert "hooks-host" not in por_id(Falso(e.base))


def biblioteca_de_paquetes():
    return importlib.import_module("odd_ws.paquetes")


ARCHIVOS_DE_PAQUETE = {"verificar.py": "def verificar(ctx):\n    return []\n", "verificar.tests.py": "print('suite')\n",
                       "matriz.csv": "id,origen,tipo,destino,severidad,numeros,resumen,motivo\n", "no-negociables.md": "- regla\n",
                       "evidencia.md": "# Evidencia\n"}


def poner_paquete(raiz, nombre="alfa", capa="sql", prefijo="ALF", manifiesto=None):
    carpeta = ".claude/reglas/paquetes/%s/" % nombre
    for archivo, texto in ARCHIVOS_DE_PAQUETE.items():
        poner(raiz, carpeta + archivo, texto)
    datos = {"formato": 1, "nombre": nombre, "prefijo": prefijo, "odd_ws_api": 1, "descripcion": "de prueba"}
    poner(raiz, carpeta + "odd-ws-paquete.json", json.dumps({**datos, **(manifiesto or {})}))
    return {"capa": capa, "prefijo": prefijo, "fuente": "https://example.com/%s.git" % nombre, "etiqueta": "v1.0.0",
            "commit": "d" * 40, "huella": biblioteca_de_paquetes().huella(str(raiz / carpeta))}


def poner_lock(raiz, entradas):
    return poner(raiz, ".claude/reglas/paquetes.json", entradas if isinstance(entradas, str) else
                 json.dumps({"version": 1, "paquetes": entradas}))


def test_paquetes_sin_lock_no_aplica_y_va_tras_los_writers():
    with Escenario() as e:
        raiz = e.instancia(capas=("sql", "web"))
        resultados = d().diagnosticar(Falso(e.base, cwd=raiz))
        ids = [r.id for r in resultados]
        assert ids[ids.index("writer-web") + 1] == "paquetes", ids
        r = next(r for r in resultados if r.id == "paquetes")
        assert r.estado == "NO APLICA" and ".claude/reglas/paquetes.json" in r.detalle and r.arreglo is None and r.comando is None, r


def test_paquetes_fuera_de_una_instancia_no_hay_item():
    with Escenario() as e:
        assert "paquetes" not in por_id(Falso(e.base))


def test_paquetes_sanos_es_ok():
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner_lock(raiz, {"alfa": poner_paquete(raiz), "beta": poner_paquete(raiz, "beta", prefijo="BET")})
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)["paquetes"]
        assert r.estado == "OK" and r.detalle.startswith("2 paquetes"), r
        codigo, salida = correr([], ctx)
        assert codigo == 0 and "paquetes" in salida, salida


def test_paquetes_cada_inconsistencia_es_falta_con_su_detalle_y_sin_arreglo():
    def capa_no_declarada(raiz):
        poner_lock(raiz, {"alfa": poner_paquete(raiz, capa="rust")})

    def sin_carpeta(raiz):
        poner_lock(raiz, {"alfa": poner_paquete(raiz)})
        shutil.rmtree(raiz / ".claude" / "reglas" / "paquetes" / "alfa", onexc=_forzar_borrado)

    def sin_un_archivo(raiz):
        entrada = poner_paquete(raiz)
        os.remove(raiz / ".claude" / "reglas" / "paquetes" / "alfa" / "evidencia.md")
        entrada["huella"] = biblioteca_de_paquetes().huella(str(raiz / ".claude" / "reglas" / "paquetes" / "alfa"))
        poner_lock(raiz, {"alfa": entrada})

    def editado_a_mano(raiz):
        poner_lock(raiz, {"alfa": poner_paquete(raiz)})
        poner(raiz, ".claude/reglas/paquetes/alfa/verificar.py", "def verificar(ctx):\n    return []  # retocado\n")

    def prefijo_de_una_capa(raiz):
        poner(raiz, "workspace.config.json", json.dumps({"schema_version": 1, "layers": {"sql": {"extensions": [".sql"], "rule_prefix": "ALF"}}}))
        poner_lock(raiz, {"alfa": poner_paquete(raiz)})

    def prefijo_de_otro_paquete(raiz):
        poner_lock(raiz, {"alfa": poner_paquete(raiz), "beta": poner_paquete(raiz, "beta", prefijo="ALF")})

    def api_mas_nueva(raiz):
        poner_lock(raiz, {"alfa": poner_paquete(raiz, manifiesto={"odd_ws_api": 2})})

    def manifiesto_ajeno(raiz):
        poner_lock(raiz, {"alfa": poner_paquete(raiz, manifiesto={"nombre": "otro", "prefijo": "OTR"})})

    def lock_roto(raiz):
        poner_lock(raiz, "{roto")

    def lock_de_otra_version(raiz):
        poner(raiz, ".claude/reglas/paquetes.json", json.dumps({"version": 2, "paquetes": {}}))

    def carpeta_enlazada(raiz):
        entrada = poner_paquete(raiz)
        carpeta = raiz / ".claude" / "reglas" / "paquetes" / "alfa"
        real = raiz.parent / "alfa-real"
        shutil.move(str(carpeta), str(real))
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(real), str(carpeta))
        else:
            os.symlink(str(real), str(carpeta), target_is_directory=True)
        poner_lock(raiz, {"alfa": entrada})

    casos = [
        (carpeta_enlazada, "alfa: enlace o fuera de .claude/reglas/paquetes/alfa, así que no se carga: .claude/reglas/paquetes/alfa"),
        (capa_no_declarada, "alfa: la capa rust no está declarada en workspace.config.json"),
        (sin_carpeta, "alfa: falta la carpeta .claude/reglas/paquetes/alfa"),
        (sin_un_archivo, "alfa: falta evidencia.md en .claude/reglas/paquetes/alfa"),
        (editado_a_mano, "alfa: la huella no coincide con el lock"),
        (prefijo_de_una_capa, "alfa: el prefijo ALF ya lo usa layers.sql.rule_prefix"),
        (prefijo_de_otro_paquete, ".claude/reglas/paquetes.json: el prefijo ALF lo usan alfa y beta"),
        (api_mas_nueva, "alfa: pide odd_ws_api 2 y este plugin da 1, así que no se carga"),
        (manifiesto_ajeno, "alfa: el manifiesto dice nombre otro y el lock alfa; alfa: el manifiesto dice prefijo OTR y el lock ALF"),
        (lock_roto, ".claude/reglas/paquetes.json: no se puede leer como JSON"),
        (lock_de_otra_version, ".claude/reglas/paquetes.json: version 2 no es la que entiende este plugin (1)"),
    ]
    for preparar, rastro in casos:
        with Escenario() as e:
            raiz = instancia_sana(e)
            preparar(raiz)
            ctx = Falso(e.base, cwd=raiz)
            r = por_id(ctx)["paquetes"]
            assert r.estado == "FALTA" and rastro in r.detalle, (preparar.__name__, r)
            assert r.arreglo is None and r.comando is None and "/odd-ws:paquetes" in r.ayuda, (preparar.__name__, r)
            codigo, salida = correr([], ctx)
            assert codigo == 1 and "cómo: " + r.ayuda in salida and "arreglo: --arreglar paquetes" not in salida, salida


def test_paquetes_arreglar_no_tiene_arreglo_automatico_y_dice_como():
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner_lock(raiz, "{roto")
        codigo, salida = correr(["--arreglar", "paquetes"], Falso(e.base, cwd=raiz))
        assert codigo == 2 and salida.startswith("paquetes no tiene arreglo automático.") and "/odd-ws:paquetes" in salida, salida
    with Escenario() as e:
        raiz = instancia_sana(e)
        codigo, salida = correr(["--arreglar", "paquetes"], Falso(e.base, cwd=raiz))
        assert codigo == 0 and salida.strip() == "paquetes: NO APLICA; no hay nada que arreglar", salida


def test_paquetes_con_la_config_rota_y_un_lock_es_falta():
    with Escenario() as e:
        raiz = instancia_sana(e)
        poner_lock(raiz, {"alfa": poner_paquete(raiz)})
        poner(raiz, "workspace.config.json", '{"schema_version": 1, "layers": {}}')
        r = por_id(Falso(e.base, cwd=raiz))["paquetes"]
        assert r.estado == "FALTA" and "no se pueden revisar los paquetes" in r.detalle and "layers" in r.detalle, r


def con_profile(raiz, valor):
    ruta = raiz / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["profile"] = valor
    ruta.write_text(json.dumps(config), encoding="utf-8")


def test_config_con_profile_invalido_es_falta_y_valido_es_ok():
    for valor, estado in (("control", "FALTA"), ("Controles", "FALTA"), (3, "FALTA"), (["controles"], "FALTA"), ("completo", "OK"),
                          ("controles", "OK")):
        with Escenario() as e:
            raiz = e.instancia()
            con_profile(raiz, valor)
            r = por_id(Falso(e.base, cwd=raiz))["config"]
            assert r.estado == estado, (valor, r)
            assert estado == "OK" or (r.detalle.startswith("profile") and "completo | controles" in r.detalle
                                      and "workspace.config.json" in r.ayuda and r.comando is None and r.arreglo is None), (valor, r)


def test_en_controles_writers_es_un_solo_no_aplica_que_no_propone_crear_writers():
    with Escenario() as e:
        raiz = e.instancia(json.dumps({"plugin_root": str(e.base / "plugin-instalado")}), capas=("sql", "web", "C_Sharp"))
        con_profile(raiz, "controles")
        ctx = Falso(e.base, cwd=raiz)
        r = por_id(ctx)
        assert [i for i in r if i.startswith("writer")] == ["writers"], list(r)
        writers = r["writers"]
        assert writers.estado == "NO APLICA" and writers.comando is None and writers.arreglo is None and writers.ayuda == "", writers
        assert "controles" in writers.detalle and "falta" not in writers.detalle, writers
        codigo, salida = correr([], ctx)
        assert "--arreglar writer" not in salida, salida
        poner(raiz, "workspace.config.json", '{"schema_version": 1, "profile": "controles", "layers": {}}')
        r = por_id(ctx)
        assert [i for i in r if i.startswith("writer")] == ["writers"] and r["writers"].estado == "NO APLICA", r["writers"]


def test_con_profile_completo_los_writers_son_los_de_siempre():
    with Escenario() as e:
        raiz = e.instancia(json.dumps({"plugin_root": str(e.base / "plugin-instalado")}))
        sin_clave = por_id(Falso(e.base, cwd=raiz))["writer-sql"]
        con_profile(raiz, "completo")
        r = por_id(Falso(e.base, cwd=raiz))
        assert "writers" not in r and r["writer-sql"]._replace(arreglo=None) == sin_clave._replace(arreglo=None), r["writer-sql"]
        assert r["writer-sql"].estado == "AVISO" and r["writer-sql"].arreglo is not None, r["writer-sql"]


RDD_APAGADO = {("gentle-ai", "review", "mode", "status"): (0, "receipt-driven development: off (decided by global)\n")}


def test_en_controles_el_rdd_encendido_es_ok_porque_es_la_revision_y_no_se_ofrece_apagarlo():
    with Escenario() as e:
        raiz = e.instancia()
        con_profile(raiz, "controles")
        ctx = Falso(e.base, cwd=raiz, respuestas={**RDD_ENCENDIDO, ("git", "-C", str(raiz), "rev-parse", "--show-toplevel"): (0, str(raiz) + "\n")})
        r = por_id(ctx)["rdd"]
        assert r.estado == "OK" and r.comando is None and r.arreglo is None, r
        assert r.detalle.startswith("receipt-driven development: on") and "controles" in r.detalle, r.detalle
        codigo, salida = correr(["--arreglar", "rdd"], ctx)
        assert codigo == 0 and "no hay nada que arreglar" in salida and not [c for c in ctx.llamadas if c[:4] == APAGAR_RDD], salida


def test_en_controles_el_rdd_apagado_o_ilegible_es_aviso_sin_arreglo_porque_la_instancia_queda_sin_revision():
    for respuestas, inicio in ((RDD_APAGADO, "receipt-driven development: off"),
                               ({("gentle-ai", "review", "mode", "status"): (1, "boom\n")}, "no se pudo leer el estado del RDD")):
        with Escenario() as e:
            raiz = e.instancia()
            con_profile(raiz, "controles")
            ctx = Falso(e.base, cwd=raiz, respuestas=respuestas)
            r = por_id(ctx)["rdd"]
            assert r.estado == "AVISO" and r.comando is None and r.arreglo is None, r
            assert r.detalle.startswith(inicio) and "sin revisión" in r.detalle, r.detalle
            assert "controles" in r.ayuda and "D3" not in r.ayuda and "disable" not in r.ayuda, r.ayuda
            codigo, salida = correr(["--arreglar", "rdd"], ctx)
            assert codigo == 2 and "no tiene arreglo automático" in salida and not [c for c in ctx.llamadas if c[:4] == APAGAR_RDD], salida


def test_en_completo_el_rdd_apagado_sigue_ok_y_sin_gentle_ai_sigue_no_aplicando():
    for valor in (None, "completo"):
        with Escenario() as e:
            raiz = e.instancia()
            if valor:
                con_profile(raiz, valor)
            r = por_id(Falso(e.base, cwd=raiz, respuestas=RDD_APAGADO))["rdd"]
            assert (r.estado, r.detalle, r.comando, r.ayuda) == ("OK", "receipt-driven development: off (decided by global)", None, ""), r
    with Escenario() as e:
        raiz = e.instancia()
        con_profile(raiz, "controles")
        r = por_id(Falso(e.base, cwd=raiz, respuestas={("gentle-ai",): None}))["rdd"]
        assert (r.estado, r.detalle) == ("NO APLICA", "gentle-ai no está instalado"), r


def test_en_controles_la_ayuda_de_capas_cobertura_no_habla_de_revisar():
    import config_loader
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x", "scripts/x.mjs": "x"})
        con_profile(raiz, "controles")
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["capas-cobertura"]
        assert r.estado == "AVISO" and r.detalle == "extensiones versionadas sin capa: .mjs (1)", r
        assert r.ayuda == config_loader.ayuda_de_cobertura({".mjs": 1}, controles=True) and r.comando is None and r.arreglo is None, r
        assert "revisar" not in r.ayuda and "triaje" not in r.ayuda and "extensions" in r.ayuda and "workspace.config.json" in r.ayuda, r.ayuda
        con_profile(raiz, "completo")
        assert por_id(Falso(e.base, cwd=raiz, git_real=True))["capas-cobertura"].ayuda == config_loader.ayuda_de_cobertura({".mjs": 1})


def test_en_controles_los_esperados_son_ok_sin_hablar_de_revisar():
    with Escenario() as e:
        raiz = instancia_con_repo_versionado(e, {"a.sql": "x", "package.json": "{}", "Dockerfile": "x"})
        con_profile(raiz, "controles")
        r = por_id(Falso(e.base, cwd=raiz, git_real=True))["capas-cobertura"]
        assert (r.estado, r.detalle) == ("OK", "sin capa y esperados: (sin extensión) (1), .json (1); ninguna regla de capa los chequea"), r
        assert "revisar" not in r.detalle and "triaje" not in r.detalle, r.detalle


def test_el_claude_md_reducido_con_el_perfil_completo_es_aviso_sin_arreglo():
    with Escenario() as e:
        raiz = instancia_sana(e)
        ctx = Falso(e.base, cwd=raiz)
        assert "perfil" not in por_id(ctx)
        poner(raiz, "CLAUDE.md", "# X\n\n%s\n\nTexto.\n" % d().MARCA_CONTROLES)
        ids = [r.id for r in d().diagnosticar(ctx)]
        assert ids.index("perfil") == ids.index("hooks-apagados") + 1, ids
        r = por_id(ctx)["perfil"]
        assert r.estado == "AVISO" and r.comando is None and r.arreglo is None, r
        assert "CLAUDE.md" in r.detalle and "controles" in r.detalle, r.detalle
        assert "/odd-ws:bootstrap" in r.ayuda and "borr" in r.ayuda, r.ayuda
        codigo, salida = correr(["--arreglar", "perfil"], ctx)
        assert codigo == 2 and "no tiene arreglo automático" in salida, salida
        assert (raiz / "CLAUDE.md").read_text(encoding="utf-8").count(d().MARCA_CONTROLES) == 1
        con_profile(raiz, "controles")
        assert "perfil" not in por_id(ctx)
        con_profile(raiz, "completo")
        assert por_id(ctx)["perfil"].estado == "AVISO"
        poner(raiz, "CLAUDE.md", "# X\n\nLa marca %s citada en un texto no cuenta.\n" % d().MARCA_CONTROLES)
        assert "perfil" not in por_id(ctx)


def instancia_pi_de_controles(e):
    raiz = con_hosts(e.instancia(json.dumps({"plugin_root": str(e.base / "plugin-instalado")})), ["pi"])
    con_profile(raiz, "controles")
    poner(raiz, ".claude/skills/capa-sql/SKILL.md", skill_con("capa-sql"))
    return raiz


def pi_de_controles(e, raiz, **extra):
    ctx = falso_de_pi(e, raiz, **extra)
    poner_paquetes(de_pi(ctx), str(ctx.plugin))
    poner_paquetes(aislado(ctx), str(ctx.plugin))
    ctx.respuestas[("git", "-C", str(raiz), "rev-parse", "--show-toplevel")] = (0, str(raiz.parent) + "\n")
    return ctx


def sin_writers(r):
    return not [(i, r[i]) for i in ITEMS_DE_PI if "writer" in (r[i].detalle + r[i].ayuda).lower()]


def test_en_controles_los_items_de_pi_no_hablan_de_writers():
    with Escenario() as e:
        raiz = instancia_pi_de_controles(e)
        r = por_id(pi_de_controles(e, raiz, gentle=False))
        assert sin_writers(r), {i: r[i] for i in ITEMS_DE_PI}
        g = r["gentle-shell"]
        assert g.estado == "NO APLICA" and "gentle-shell no está instalado" in g.detalle and "controles" in g.detalle, g
        assert r["pi"].estado == "OK" and r["pi-plugin"].estado == "OK" and r["pi-agentes"].estado == "NO APLICA", r
        r = por_id(pi_de_controles(e, raiz))
        assert sin_writers(r) and r["gentle-shell"].estado == "OK", r["gentle-shell"]
        r = por_id(pi_de_controles(e, raiz, version="0.86.3\n", gentle=False))
        assert sin_writers(r), r["pi"]
        assert r["pi"].estado == "FALTA" and "agent_before_settle" in r["pi"].detalle and "revisión del fin del turno" in r["pi"].detalle, r["pi"]
        ctx = pi_de_controles(e, raiz)
        for respuesta, estado in ((gentle_shell_dice(ctx, pi="0.86.3"), "FALTA"), ((1, "gentle-shell: algo se rompió\n"), "AVISO"),
                                  ((0, "sin numeros\n"), "AVISO")):
            r = por_id(pi_de_controles(e, raiz, gentle=respuesta))
            assert sin_writers(r) and r["gentle-shell"].estado == estado and r["gentle-shell"].ayuda, (respuesta, r["gentle-shell"])
        r = por_id(pi_de_controles(e, raiz, version=None, gentle=gentle_shell_dice(ctx, pi="0.86.3")))
        assert sin_writers(r) and r["pi"].estado == "FALTA" and "gentle-shell" in r["pi"].detalle, r["pi"]


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
