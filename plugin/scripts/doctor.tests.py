import contextlib
import importlib
import io
import json
import os
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
