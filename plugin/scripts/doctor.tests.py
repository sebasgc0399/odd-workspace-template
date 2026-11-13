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


def test_rdd_encendido_es_aviso_y_el_arreglo_usa_scope_global():
    with Escenario() as e:
        ctx = Falso(e.base, respuestas={("gentle-ai", "review", "mode", "status"): (0, "receipt-driven development: on (decided by default)\n")})
        r = por_id(ctx)["rdd"]
        assert r.estado == "AVISO" and r.comando == ["gentle-ai", "review", "mode", "disable", "--scope", "global"], r


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


NUEVOS = ("config", "instancia-hooks", "instancia-plugin")
CLAVE_PLUGIN = "odd-ws@odd-workspace-template"
ANTES_EN_INSTANCIA = ["repo-hooks", "lista-negra", "plugin-root", "writer-sql", "agentes-skills", "agentes-hooks", "python",
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
        assert ids[ids.index("plugin-root") + 1:ids.index("plugin-root") + 4] == list(NUEVOS), ids


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
            assert "sin configurar" in r.detalle and r.ayuda and "integrá" in r.ayuda.lower(), r
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
    "session_start:0:0", "pre_tool_use:0:0", "pre_tool_use:1:0", "pre_tool_use:2:0", "post_tool_use:0:0", "subagent_stop:0:0")]
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
        assert por_id(ctx)["hooks-host"].detalle == "6 hooks de codex (12 comandos), cada uno con el --host de su archivo"
    with Escenario() as e:
        _, ctx = instancia_codex_sana(e, hosts=("claude-code", "codex"))
        assert por_id(ctx)["hooks-host"].detalle == "13 hooks de claude-code, codex (19 comandos), cada uno con el --host de su archivo"


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
            assert r.estado == "AVISO" and "1 de 6" in r.detalle and falta.split("json:")[1] in r.detalle, (falta, r)
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


def test_con_pi_declarado_el_doctor_dice_lo_que_falta_y_ningun_item_de_pi_da_ok():
    for hosts in (("claude-code", "pi"), ("pi",)):
        with Escenario() as e:
            _, ctx = instancia_codex_sana(e, hosts=hosts)
            r = por_id(ctx)
            assert r["pi"].estado == "AVISO" and "F2e" in r["pi"].detalle and "no se revisa" in r["pi"].detalle, (hosts, r["pi"])
            assert r["pi-agentes"].estado == "AVISO" and "F2d" in r["pi-agentes"].detalle, (hosts, r["pi-agentes"])
            assert r["hooks-host"].estado == "FALTA" and "hooks/hooks.pi.json no se puede leer" in r["hooks-host"].detalle, (hosts, r["hooks-host"])
            assert not [i for i in r if i.startswith("codex")], (hosts, list(r))
            codigo, salida = correr([], ctx)
            assert codigo == 1 and "hooks/hooks.pi.json" in salida, (hosts, salida)


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
