import contextlib
import importlib
import io
import json
import os
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
RESPUESTAS_OK = {
    ("git", "config", "--get", "credential.helper"): (0, "manager\n"),
    ("git", "rev-parse", "--show-toplevel"): (128, "fatal: not a git repository\n"),
    (PYTHON_PATH, "--version"): (0, "Python 3.14.3\n"),
    ("claude", "--version"): (0, "2.1.284 (Claude Code)\n"),
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
    return {clave: valor for clave, valor in os.environ.items() if not clave.startswith("GIT_")}


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Falso:
    def __init__(self, base, respuestas=None, which=None, tiempos=None, git_real=False, cwd=None, marketplace=True):
        propias = respuestas or {}
        tapadas = [clave for clave in RESPUESTAS_OK if any(isinstance(p, tuple) and clave[:len(p)] == p for p in propias)]
        self.respuestas = {**{c: v for c, v in RESPUESTAS_OK.items() if c not in tapadas}, **propias}
        self.rutas = {"python": PYTHON_PATH, **(which or {})}
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
        plugins.mkdir(parents=True)
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

    def instancia(self, local=None):
        raiz = self.base / "instancia"
        (raiz / "tickets" / "T-1").mkdir(parents=True)
        (raiz / "workspace.config.json").write_text(json.dumps({"schema_version": 1, "layers": {"sql": {"extensions": [".sql"]}}}), encoding="utf-8")
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


def test_plugin_root_que_apunta_al_mismo_plugin_con_otra_forma_es_ok():
    with Escenario() as e:
        ctx = Falso(e.base)
        raiz = e.instancia(json.dumps({"plugin_root": str(ctx.plugin).upper() + os.sep}))
        ctx.cwd = raiz
        r = por_id(ctx)["plugin-root"]
        assert r.estado == "OK", r


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


def test_el_plugin_del_contexto_real_es_la_carpeta_del_plugin():
    ctx = d().Contexto()
    assert ctx.plugin == AQUI.parent and (ctx.plugin / "scripts" / "reglas.py").is_file(), ctx.plugin
    assert ctx.entorno is os.environ


def test_python_lento_por_el_alias_es_aviso_con_la_ayuda():
    with Escenario() as e:
        r = por_id(Falso(e.base, tiempos={PYTHON_PATH: 214.0}))["python"]
        assert r.estado == "AVISO" and "214" in r.detalle and "WindowsApps" in r.ayuda, r


def test_python_que_resuelve_al_mismo_interprete_es_ok():
    with Escenario() as e:
        ctx = Falso(e.base, which={"python": PYTHON_REAL}, respuestas={(PYTHON_REAL, "--version"): (0, "Python 3.14.3\n")})
        assert por_id(ctx)["python"].estado == "OK"


def test_python_ausente_es_falta():
    with Escenario() as e:
        assert por_id(Falso(e.base, which={"python": None}))["python"].estado == "FALTA"


def test_sin_credential_helper_es_falta():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={("git", "config", "--get", "credential.helper"): (1, "")})
        assert por_id(ctx)["git-credenciales"].estado == "FALTA"


def test_claude_viejo_es_falta_y_version_ilegible_es_aviso():
    with Escenario() as e:
        assert por_id(Falso(e.base, respuestas={("claude", "--version"): (0, "2.1.200 (Claude Code)\n")}))["claude"].estado == "FALTA"
        assert por_id(Falso(e.base / "b", respuestas={("claude", "--version"): (0, "sin numeros\n")}))["claude"].estado == "AVISO"


def test_marketplace_no_registrado_es_falta_con_arreglo_automatico():
    with Escenario() as e:
        r = por_id(Falso(e.base, marketplace=False))["marketplace"]
        assert r.estado == "FALTA" and r.comando[:4] == ["claude", "plugin", "marketplace", "add"], r
        assert por_id(Falso(e.base / "b", marketplace=None))["marketplace"].estado == "FALTA"


def test_gentle_ai_ausente_es_falta_y_rdd_y_telemetria_no_aplican():
    with Escenario() as e:
        r = por_id(Falso(e.base, respuestas={("gentle-ai",): None}))
        assert r["gentle-ai"].estado == "FALTA", r
        assert r["rdd"].estado == "NO APLICA" and r["telemetria"].estado == "NO APLICA", r


def test_rdd_encendido_es_aviso_y_el_arreglo_usa_scope_global():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={("gentle-ai", "review", "mode", "status"): (0, "receipt-driven development: on (decided by default)\n")})
        r = por_id(ctx)["rdd"]
        assert r.estado == "AVISO" and r.comando == ["gentle-ai", "review", "mode", "disable", "--scope", "global"], r


def test_telemetria_activa_es_aviso():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={("gentle-ai", "telemetry", "status"): (0, "telemetry: enabled\n")})
        assert por_id(ctx)["telemetria"].estado == "AVISO"


def test_engram_viejo_es_falta():
    with Escenario() as e:
        assert por_id(Falso(e.base, respuestas={("engram", "version"): (0, "engram 3.4.9\n")}))["engram"].estado == "FALTA"


def test_jq_ausente_es_falta():
    with Escenario() as e:
        assert por_id(Falso(e.base, respuestas={("jq",): None}))["jq"].estado == "FALTA"


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
        assert ("gentle-ai", "review", "mode", "disable", "--scope", "global") not in ctx.llamadas, ctx.llamadas


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
        codigo, salida = correr([], Falso(e.base, respuestas={("jq",): None}))
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
