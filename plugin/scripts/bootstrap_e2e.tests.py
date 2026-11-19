import atexit
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLUGIN = AQUI.parent
SCRIPT = AQUI / "bootstrap.py"
CAPA = "capa-a"
IDS_DE_INSTANCIA = ("plugin-root", "config", "instancia-hooks", "instancia-eol", "instancia-plugin", f"writer-{CAPA}", "agentes-skills", "agentes-hooks")
VARIABLES_DE_GIT_AISLADAS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
IDENTIDAD = ("-c", "user.name=Prueba", "-c", "user.email=prueba@example.com", "-c", "commit.gpgsign=false")
IDENTIDAD_ENV = {"GIT_AUTHOR_NAME": "Prueba", "GIT_AUTHOR_EMAIL": "prueba@example.com",
                 "GIT_COMMITTER_NAME": "Prueba", "GIT_COMMITTER_EMAIL": "prueba@example.com"}
DOCTOR = (
    "import json, sys\n"
    "sys.path.insert(0, %r)\n"
    "import doctor\n"
    "ctx = doctor.Contexto()\n"
    "filas = [doctor.chequear_plugin_root(ctx), *doctor.chequear_instancia(ctx), *doctor.chequear_writers(ctx), *doctor.chequear_agentes(ctx)]\n"
    "print(json.dumps([[r.id, r.estado, r.detalle] for r in filas]))\n"
) % str(AQUI)
LIMPIEZA = []
CAJAS = []
SUITE_EN_VERDE = b"suites: 1, todas en verde"


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def _limpiar():
    while LIMPIEZA:
        shutil.rmtree(LIMPIEZA.pop(), onexc=_forzar_borrado)


atexit.register(_limpiar)


class Caja:
    def __init__(self):
        self.base = Path(tempfile.mkdtemp(prefix="bootstrap-e2e-"))
        LIMPIEZA.append(self.base)
        CAJAS.append(self)
        self.global_ = self.base / "gitconfig-global"
        self.sistema = self.base / "gitconfig-sistema"
        self.global_.write_bytes(b"")
        self.sistema.write_bytes(b"")
        self.entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "CLAUDE_PROJECT_DIR"}
        self.entorno.update(GIT_CONFIG_GLOBAL=str(self.global_), GIT_CONFIG_SYSTEM=str(self.sistema), GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
        self.repo = self.base / "repo-a"
        self.repo.mkdir()
        self.git(self.repo, "init", "-q")
        (self.repo / "a.txt").write_bytes(b"a\n")
        self.git(self.repo, "add", "a.txt")
        self.git(self.repo, *IDENTIDAD, "commit", "-q", "-m", "base")
        self.raiz = self.base / "instancia"

    def git(self, cwd, *args):
        resultado = subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=self.entorno, timeout=120)
        assert resultado.returncode == 0, (args, resultado.stderr)
        return resultado.stdout.decode("utf-8").strip()

    def spec(self, con_prefijo=True):
        capa = {"extensions": [".ext"], "repos": ["repo-a"]}
        if con_prefijo:
            capa["rule_prefix"] = "CA"
        return {
            "spec_version": 1,
            "config": {"schema_version": 1, "repos": {"repo-a": {}}, "layers": {CAPA: capa}},
            "local": {"repos": {"repo-a": {"path": str(self.repo)}}},
            "proyecto": {"nombre": "Proyecto Sintetico"},
        }

    def cli(self, spec, *extra, entorno=None):
        ruta = self.base / "spec.json"
        ruta.write_text(json.dumps(spec), encoding="utf-8")
        resultado = subprocess.run(
            [sys.executable, "-W", "error", str(SCRIPT), "--spec", str(ruta), "--raiz", str(self.raiz), *extra],
            capture_output=True, env={**self.entorno, **(entorno or {})}, timeout=300,
        )
        return (
            resultado.returncode,
            resultado.stdout.decode("utf-8").replace("\r\n", "\n"),
            resultado.stderr.decode("utf-8").replace("\r\n", "\n"),
        )

    def doctor(self):
        resultado = subprocess.run([sys.executable, "-I", "-W", "error", "-c", DOCTOR], cwd=self.raiz, capture_output=True, env=self.entorno, timeout=300)
        assert resultado.returncode == 0, resultado.stderr.decode("utf-8", "replace")
        return {fila[0]: (fila[1], fila[2]) for fila in json.loads(resultado.stdout.decode("utf-8"))}

    def arbol(self):
        vista = {}
        for ruta in sorted(self.raiz.rglob("*")):
            relativa = ruta.relative_to(self.raiz).as_posix()
            if relativa == ".git" or relativa.startswith(".git/"):
                continue
            vista[relativa] = None if ruta.is_dir() else ruta.read_bytes()
        return vista


def localizar_sh():
    encontrado = shutil.which("sh")
    if encontrado:
        return encontrado
    git = shutil.which("git")
    if git:
        for relativa in (("bin", "sh.exe"), ("usr", "bin", "sh.exe")):
            candidato = Path(git).resolve().parents[1].joinpath(*relativa)
            if candidato.is_file():
                return str(candidato)
    return None


def hay_repo_arriba(ruta):
    ruta = Path(ruta).resolve()
    return any((p / ".git").exists() for p in (ruta, *ruta.parents))


def verificar_instancia_ok(doctor):
    for id in IDS_DE_INSTANCIA:
        assert id in doctor, (id, sorted(doctor))
        assert doctor[id][0] == "OK", (id, doctor[id])
    assert not [id for id, (estado, _) in doctor.items() if estado == "FALTA"], doctor


class InstanciaNueva:
    def __init__(self):
        self.caja = Caja()
        self.spec = self.caja.spec()
        self.cli = self.caja.cli(self.spec, "--commitear", entorno=IDENTIDAD_ENV)
        self.doctor = self.caja.doctor() if self.cli[0] == 0 else None
        self.sh = localizar_sh()
        self.pre_commit = None
        self.arbol_tras_el_commit = None
        if self.cli[0] == 0:
            if self.sh:
                self.pre_commit = subprocess.run([self.sh, ".githooks/pre-commit"], cwd=self.caja.raiz, capture_output=True, env=self.caja.entorno, timeout=300)
            self.arbol_tras_el_commit = self.caja.arbol()


_NUEVA = []


def instancia_nueva():
    if not _NUEVA:
        _NUEVA.append(InstanciaNueva())
    return _NUEVA[0]


def archivos_esperados():
    return [
        "workspace.config.json", "workspace.local.json", ".gitignore",
        f".claude/agents/writer-{CAPA}.md", f".claude/agents/revisor-{CAPA}.md", f".claude/skills/capa-{CAPA}/SKILL.md", ".claude/agents/revisor-diseno.md", ".claude/skills/criterios/SKILL.md",
        ".claude/reglas/matriz.csv", ".claude/reglas/evidencia.md", f".claude/reglas/verificar_{CAPA}.py", f".claude/reglas/verificar_{CAPA}.tests.py",
        "CLAUDE.md", "tickets/_plantilla/CLAUDE.md",
        ".githooks/pre-commit", ".gitattributes", ".claude/settings.json", "tickets/_plantilla/.claude/settings.json",
    ]


def test_una_instancia_nueva_sale_con_cero_y_crea_todo():
    nueva = instancia_nueva()
    codigo, salida, errores = nueva.cli
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    for ruta in archivos_esperados():
        assert (nueva.caja.raiz / ruta).is_file(), ruta
        assert f"creado {ruta}" in lineas, (ruta, lineas)
    assert "git init: repo creado" in lineas and "core.hooksPath = .githooks: configurado (--local)" in lineas, lineas
    assert nueva.caja.git(nueva.caja.raiz, "config", "--local", "--get", "core.hooksPath") == ".githooks"


def test_el_hook_de_la_instancia_nueva_queda_en_lf_aunque_git_convierta_los_saltos():
    nueva = instancia_nueva()
    atributos = nueva.caja.git(nueva.caja.raiz, "check-attr", "text", "eol", "--", ".githooks/pre-commit")
    assert atributos.splitlines() == [".githooks/pre-commit: text: set", ".githooks/pre-commit: eol: lf"], atributos


def test_el_doctor_da_ok_en_los_items_de_la_instancia_nueva():
    nueva = instancia_nueva()
    assert nueva.doctor is not None, nueva.cli
    verificar_instancia_ok(nueva.doctor)


def test_el_pre_commit_generado_sale_con_cero():
    nueva = instancia_nueva()
    if nueva.sh is None:
        print("      (no hay sh: prueba omitida)")
        return
    assert nueva.pre_commit is not None and nueva.pre_commit.returncode == 0, (nueva.pre_commit.stdout, nueva.pre_commit.stderr)
    assert SUITE_EN_VERDE in nueva.pre_commit.stdout + nueva.pre_commit.stderr, (nueva.pre_commit.stdout, nueva.pre_commit.stderr)


def test_el_bootstrap_hace_el_primer_commit_con_el_hook_ejecutable_y_sin_lo_local():
    nueva = instancia_nueva()
    commit = [linea for linea in nueva.cli[1].splitlines() if linea.startswith("commit: ")]
    esperados = [ruta for ruta in archivos_esperados() if ruta != "workspace.local.json"]
    assert len(commit) == 1 and commit[0].endswith(f"con {len(esperados)} archivos (el hook, ejecutable)"), (commit, nueva.cli)
    assert nueva.caja.git(nueva.caja.raiz, "log", "--format=%s") == "chore: crea la instancia con odd-ws"
    rastreados = set(nueva.caja.git(nueva.caja.raiz, "ls-files").splitlines())
    assert rastreados == set(esperados), sorted(rastreados ^ set(esperados))
    assert nueva.caja.git(nueva.caja.raiz, "ls-files", "-s", ".githooks/pre-commit").startswith("100755 ")
    assert nueva.caja.git(nueva.caja.raiz, "status", "--porcelain") == ""


def test_el_pre_commit_corre_de_verdad_en_el_commit_y_lo_frena_si_falla():
    nueva = instancia_nueva()
    raiz = nueva.caja.raiz
    pre_commit = raiz / ".githooks" / "pre-commit"
    original = pre_commit.read_bytes()
    pre_commit.write_bytes(b"#!/bin/sh\necho 'hook de prueba corrio' >&2\nexit 1\n")
    try:
        (raiz / "cambio.txt").write_bytes(b"x\n")
        nueva.caja.git(raiz, "add", "cambio.txt")
        resultado = subprocess.run(["git", *IDENTIDAD, "commit", "-m", "debe frenarse"], cwd=raiz, capture_output=True, env=nueva.caja.entorno, timeout=300)
        assert resultado.returncode != 0 and b"hook de prueba corrio" in resultado.stderr, (resultado.stdout, resultado.stderr)
    finally:
        nueva.caja.git(raiz, "reset", "-q")
        (raiz / "cambio.txt").unlink()
        pre_commit.write_bytes(original)
    assert nueva.caja.arbol() == nueva.arbol_tras_el_commit


def test_una_segunda_corrida_da_todo_ya_existia_y_no_cambia_ningun_byte():
    nueva = instancia_nueva()
    assert nueva.arbol_tras_el_commit is not None
    codigo, salida, errores = nueva.caja.cli(nueva.spec)
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    for ruta in archivos_esperados():
        assert f"ya existía {ruta}" in lineas, (ruta, lineas)
    assert not any(l.startswith("creado ") for l in lineas)
    assert lineas[-1] == f"resumen: 0 creados, {len(archivos_esperados())} ya existían"
    assert "git init: no hace falta, la raíz ya es un repo git" in lineas and "core.hooksPath = .githooks: ya estaba" in lineas
    assert nueva.caja.arbol() == nueva.arbol_tras_el_commit
    assert nueva.caja.git(nueva.caja.raiz, "status", "--porcelain") == ""


def instancia_a_mano(caja, con_prefijo):
    spec = caja.spec(con_prefijo)
    caja.raiz.mkdir()
    config = (json.dumps(spec["config"], indent=4) + "\r\n").encode("utf-8")
    local = (json.dumps({**spec["local"], "plugin_root": str(PLUGIN)}, indent=2) + "\n").encode("utf-8")
    (caja.raiz / "workspace.config.json").write_bytes(b"\xef\xbb\xbf" + config)
    (caja.raiz / "workspace.local.json").write_bytes(local)
    return spec, b"\xef\xbb\xbf" + config, local


def test_se_completa_una_instancia_que_solo_tiene_la_config_y_el_local_a_mano():
    caja = Caja()
    spec, config, local = instancia_a_mano(caja, True)
    codigo, salida, errores = caja.cli(spec)
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    assert "ya existía workspace.config.json" in lineas and "ya existía workspace.local.json" in lineas
    for ruta in archivos_esperados():
        assert (caja.raiz / ruta).is_file(), ruta
        if ruta not in ("workspace.config.json", "workspace.local.json"):
            assert f"creado {ruta}" in lineas, (ruta, lineas)
    assert (caja.raiz / "workspace.config.json").read_bytes() == config
    assert (caja.raiz / "workspace.local.json").read_bytes() == local
    assert lineas[-1] == f"resumen: {len(archivos_esperados()) - 2} creados, 2 ya existían"
    verificar_instancia_ok(caja.doctor())


def test_una_instancia_anterior_a_t8_sin_rule_prefix_se_rechaza_sin_escribir_nada():
    caja = Caja()
    spec, config, local = instancia_a_mano(caja, False)
    antes = caja.arbol()
    codigo, salida, errores = caja.cli(spec)
    assert codigo == 2 and salida == "", (codigo, salida, errores)
    assert errores == (
        f"error: layers.{CAPA}.rule_prefix falta: la entrevista lo deriva de la capa y lo confirma, "
        "y sin él la capa no tiene matriz de reglas\n"
    ), errores
    assert caja.arbol() == antes and not (caja.raiz / ".git").exists()
    assert (caja.raiz / "workspace.config.json").read_bytes() == config


def test_agregando_el_prefijo_a_mano_la_misma_cli_completa_la_instancia_anterior_a_t8():
    caja = Caja()
    spec, _, local = instancia_a_mano(caja, False)
    assert caja.cli(spec)[0] == 2
    con_prefijo = caja.spec(True)
    config_a_mano = (json.dumps(con_prefijo["config"], indent=2) + "\n").encode("utf-8")
    (caja.raiz / "workspace.config.json").write_bytes(config_a_mano)
    codigo, salida, errores = caja.cli(con_prefijo)
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    assert "ya existía workspace.config.json" in lineas and f"creado .claude/reglas/matriz.csv" in lineas
    assert (caja.raiz / "workspace.config.json").read_bytes() == config_a_mano
    assert (caja.raiz / "workspace.local.json").read_bytes() == local
    verificar_instancia_ok(caja.doctor())


def test_una_instancia_con_codex_declarado_suma_sus_toml_validos_y_la_segunda_corrida_no_cambia_ningun_byte():
    import tomllib

    caja = Caja()
    spec = caja.spec()
    spec["config"]["hosts"] = ["claude-code", "codex"]
    codigo, salida, errores = caja.cli(spec)
    assert codigo == 0 and errores == "", (codigo, errores)
    de_codex = [f".codex/agents/writer-{CAPA}.toml", f".codex/agents/revisor-{CAPA}.toml", ".codex/agents/revisor-diseno.toml",
                ".codex/config.toml"]
    lineas = salida.splitlines()
    for ruta in archivos_esperados() + de_codex:
        assert f"creado {ruta}" in lineas, (ruta, lineas)
    for ruta in de_codex[:3]:
        datos = tomllib.loads((caja.raiz / ruta).read_bytes().decode("utf-8"))
        assert set(datos) == {"name", "description", "developer_instructions"}, (ruta, datos)
        assert datos["name"] == ruta.rsplit("/", 1)[1][:-len(".toml")], (ruta, datos["name"])
    verificar_instancia_ok(caja.doctor())
    antes = caja.arbol()
    codigo, salida, errores = caja.cli(spec)
    assert codigo == 0 and errores == "" and caja.arbol() == antes, (codigo, errores)
    assert salida.splitlines()[-1] == f"resumen: 0 creados, {len(archivos_esperados()) + len(de_codex)} ya existían"


def agentes_de_pi():
    return [f".pi/agents/writer-{CAPA}.md", f".pi/agents/revisor-{CAPA}.md", ".pi/agents/revisor-diseno.md"]


def test_una_instancia_con_pi_declarado_suma_sus_agentes_de_pi_y_la_segunda_corrida_no_cambia_ningun_byte():
    sys.path.insert(0, str(AQUI))
    from odd_ws.hosts import pi

    caja = Caja()
    spec = caja.spec()
    spec["config"]["hosts"] = ["claude-code", "pi"]
    codigo, salida, errores = caja.cli(spec)
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    for ruta in archivos_esperados() + agentes_de_pi():
        assert f"creado {ruta}" in lineas, (ruta, lineas)
    assert lineas[-1] == f"resumen: {len(archivos_esperados()) + len(agentes_de_pi())} creados, 0 ya existían", lineas[-1]
    for ruta in agentes_de_pi():
        texto = (caja.raiz / ruta).read_bytes().decode("utf-8")
        nombre = ruta.rsplit("/", 1)[1][:-len(".md")]
        cabecera = texto.split("\n---\n", 1)[0].split("\n")
        assert cabecera[0] == "---" and f"name: {nombre}" in cabecera and any(l.startswith("tools: read") for l in cabecera), cabecera
        assert f"# odd-ws-hash: {pi.huella(texto)}" in cabecera, cabecera
        assert texto.split("\n---\n", 1)[1].strip(), ruta
    assert not (caja.raiz / ".codex").exists() and not (caja.raiz / "AGENTS.md").exists()
    verificar_instancia_ok(caja.doctor())
    antes = caja.arbol()
    codigo, salida, errores = caja.cli(spec)
    assert codigo == 0 and errores == "" and caja.arbol() == antes, (codigo, errores)
    assert salida.splitlines()[-1] == f"resumen: 0 creados, {len(archivos_esperados()) + len(agentes_de_pi())} ya existían"


def test_sumar_pi_a_una_instancia_que_ya_existe_deja_sus_agentes_al_doctor_y_lo_dice_sin_escribirlos():
    caja = Caja()
    spec = caja.spec()
    assert caja.cli(spec)[0] == 0
    spec["config"]["hosts"] = ["claude-code", "pi"]
    (caja.raiz / "workspace.config.json").write_bytes((json.dumps(spec["config"], indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    antes = caja.arbol()
    for extra, verbo, existe in ((("--ensayo",), "no se crearía", "existe"), ((), "no se creó", "existía")):
        codigo, salida, errores = caja.cli(spec, *extra)
        assert codigo == 0 and errores == "", (extra, codigo, errores)
        lineas = salida.splitlines()
        for ruta in agentes_de_pi():
            fuente = ".claude/agents/" + ruta.rsplit("/", 1)[1]
            assert (f"{verbo} {ruta}: {fuente} ya {existe}, así que lo deriva de ahí el doctor (doctor --arreglar pi-agentes)"
                    in lineas), (extra, ruta, lineas)
        assert caja.arbol() == antes and not (caja.raiz / ".pi").exists(), extra
    assert lineas[-1] == f"resumen: 0 creados, {len(archivos_esperados())} ya existían, 3 los deriva el doctor", lineas[-1]


SETTINGS_DEL_PLUGIN = {"enabledPlugins": {"odd-ws@odd-workspace-template": True}}
COMMIT_HECHO = r"commit: [0-9a-f]{7,} con %d archivos \(el hook, ejecutable\)"
AVISO_SETTINGS = ("no entró al commit .claude/settings.json: ya existía con otro contenido que el que escribe el bootstrap; "
                  "si es tuyo, commitealo vos")
AVISO_RUTA_ABSOLUTA = "no entró al commit %s: lista carpetas con ruta absoluta, que solo valen en esta máquina; queda sin trackear"


def primer_commit(preparar, *extra):
    caja = Caja()
    caja.raiz.mkdir()
    preparar(caja)
    return caja, caja.cli(caja.spec(), "--commitear", *extra, entorno=IDENTIDAD_ENV)


def rastreados(caja):
    return set(caja.git(caja.raiz, "ls-files").splitlines())


def lineas_de_commit(salida):
    return [linea for linea in salida.splitlines() if linea.startswith("commit: ")]


def sin_lo_local():
    return [ruta for ruta in archivos_esperados() if ruta != "workspace.local.json"]


def escribir_settings(caja, datos, **formato):
    (caja.raiz / ".claude").mkdir(exist_ok=True)
    (caja.raiz / ".claude" / "settings.json").write_bytes(json.dumps(datos, **formato).replace("\n", "\r\n").encode("utf-8"))


def escribir_workspace(caja, nombre, *rutas):
    datos = {"folders": [{"path": ruta} for ruta in rutas], "settings": {}}
    (caja.raiz / nombre).write_text(json.dumps(datos, indent=2), encoding="utf-8")


def test_un_settings_del_plugin_que_ya_existia_sin_trackear_entra_al_primer_commit():
    caja, (codigo, salida, errores) = primer_commit(lambda c: escribir_settings(c, SETTINGS_DEL_PLUGIN, indent=4))
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    assert "ya existía .claude/settings.json" in lineas, lineas
    commit = lineas_de_commit(salida)
    patron = COMMIT_HECHO % len(sin_lo_local()) + r"; entraron también los que ya existían: \.claude/settings\.json"
    assert len(commit) == 1 and re.fullmatch(patron, commit[0]), commit
    assert rastreados(caja) == set(sin_lo_local()), sorted(rastreados(caja) ^ set(sin_lo_local()))
    assert caja.git(caja.raiz, "status", "--porcelain") == ""


def test_un_settings_distinto_no_entra_al_primer_commit_y_la_salida_lo_nombra():
    distinto = {**SETTINGS_DEL_PLUGIN, "permissions": {"allow": ["Bash(ls)"]}}
    caja, (codigo, salida, errores) = primer_commit(lambda c: escribir_settings(c, distinto))
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(COMMIT_HECHO % (len(sin_lo_local()) - 1), commit[0]), commit
    assert AVISO_SETTINGS in lineas and lineas.index(AVISO_SETTINGS) == lineas.index(commit[0]) + 1, lineas
    assert ".claude/settings.json" not in rastreados(caja)
    assert caja.git(caja.raiz, "status", "--porcelain") == "?? .claude/settings.json"


def test_un_code_workspace_con_rutas_relativas_entra_al_primer_commit():
    caja, (codigo, salida, errores) = primer_commit(lambda c: escribir_workspace(c, "mi-proyecto.code-workspace", ".", "../repo-a"))
    assert codigo == 0 and errores == "", (codigo, errores)
    commit = lineas_de_commit(salida)
    patron = COMMIT_HECHO % (len(sin_lo_local()) + 1) + r"; entraron también los que ya existían: mi-proyecto\.code-workspace"
    assert len(commit) == 1 and re.fullmatch(patron, commit[0]), commit
    assert "mi-proyecto.code-workspace" in rastreados(caja)
    assert caja.git(caja.raiz, "status", "--porcelain") == ""


def test_un_code_workspace_con_alguna_ruta_absoluta_queda_sin_trackear_y_la_salida_dice_por_que():
    formas = {"letra": "C:/repos/a", "barra": "/srv/repos/a", "contrabarra": "\\repos\\a", "unc": "\\\\servidor\\repos\\a"}

    def preparar(c):
        for nombre, ruta in formas.items():
            escribir_workspace(c, f"{nombre}.code-workspace", ".", ruta)

    caja, (codigo, salida, errores) = primer_commit(preparar)
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(COMMIT_HECHO % len(sin_lo_local()), commit[0]), commit
    for nombre in sorted(formas):
        assert AVISO_RUTA_ABSOLUTA % f"{nombre}.code-workspace" in lineas, (nombre, lineas)
    assert not [ruta for ruta in rastreados(caja) if ruta.endswith(".code-workspace")], rastreados(caja)
    pendientes = sorted(caja.git(caja.raiz, "status", "--porcelain").splitlines())
    assert pendientes == sorted(f"?? {nombre}.code-workspace" for nombre in formas), pendientes


def test_lo_que_ignora_el_gitignore_no_entra_al_commit_aunque_ya_existiera_igual():
    def preparar(c):
        (c.raiz / ".gitignore").write_bytes(b"workspace.local.json\n.claude/estado/\n.claude/settings.json\n*.code-workspace\n")
        escribir_settings(c, SETTINGS_DEL_PLUGIN)
        escribir_workspace(c, "mi-proyecto.code-workspace", ".")

    caja, (codigo, salida, errores) = primer_commit(preparar)
    assert codigo == 0 and errores == "", (codigo, errores)
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(COMMIT_HECHO % (len(sin_lo_local()) - 2), commit[0]), commit
    assert "no entró al commit" not in salida, salida
    assert not {".claude/settings.json", "mi-proyecto.code-workspace", ".gitignore"} & rastreados(caja), rastreados(caja)


def test_un_code_workspace_ignorado_con_nombre_no_ascii_no_frena_el_primer_commit():
    def preparar(c):
        (c.raiz / ".gitignore").write_bytes(b"workspace.local.json\n.claude/estado/\n*.code-workspace\n")
        escribir_workspace(c, "facturación.code-workspace", ".")

    caja, (codigo, salida, errores) = primer_commit(preparar)
    assert codigo == 0 and errores == "", (codigo, errores)
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(COMMIT_HECHO % (len(sin_lo_local()) - 1), commit[0]), commit
    assert "no entró al commit" not in salida, salida
    assert caja.git(caja.raiz, "diff", "--cached", "--name-only") == "", "el índice quedó con archivos sin commitear"
    estado = caja.git(caja.raiz, "-c", "core.quotePath=false", "status", "--porcelain", "--ignored").splitlines()
    assert "!! facturación.code-workspace" in estado, estado


def test_un_settings_ya_trackeado_y_cambiado_no_se_stagea_ni_se_nombra_al_completar_la_instancia():
    caja = Caja()
    spec = caja.spec()
    assert caja.cli(spec, "--commitear", entorno=IDENTIDAD_ENV)[0] == 0
    caja.git(caja.raiz, "rm", "-q", "CLAUDE.md")
    caja.git(caja.raiz, *IDENTIDAD, "commit", "-q", "-m", "sin indice")
    escribir_settings(caja, {**SETTINGS_DEL_PLUGIN, "env": {"X": "1"}})
    codigo, salida, errores = caja.cli(spec, "--commitear", entorno=IDENTIDAD_ENV)
    assert codigo == 0 and errores == "", (codigo, errores)
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(r"commit: [0-9a-f]{7,} con 1 archivos", commit[0]), commit
    assert "no entró al commit" not in salida, salida
    assert caja.git(caja.raiz, "status", "--porcelain") == "M .claude/settings.json"


def test_el_ensayo_dice_que_entraria_lo_que_ya_existia_igual_y_relativo_y_que_no_lo_demas():
    caja = Caja()
    caja.raiz.mkdir()
    escribir_settings(caja, SETTINGS_DEL_PLUGIN)
    escribir_workspace(caja, "a.code-workspace", ".", "../repo-a")
    escribir_workspace(caja, "b.code-workspace", ".", "C:/repos/a")
    (caja.raiz / "c.code-workspace").write_text('{\n  // con comentarios\n  "folders": [{"path": "."}]\n}\n', encoding="utf-8")
    (caja.raiz / "d.code-workspace").write_text(json.dumps({"folders": [{"path": "."}, {"uri": "vscode-remote://ssh-remote+x/repo"}]}),
                                                encoding="utf-8")
    antes = caja.arbol()
    codigo, salida, errores = caja.cli(caja.spec(), "--ensayo", "--commitear")
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    assert lineas_de_commit(salida) == ["commit: se haría con los archivos nuevos (el hook, ejecutable); "
                                        "entrarían también los que ya existían: .claude/settings.json, a.code-workspace"], lineas
    absoluta = "lista carpetas con ruta absoluta, que solo valen en esta máquina; quedaría sin trackear"
    assert f"no entraría al commit b.code-workspace: {absoluta}" in lineas, lineas
    assert f"no entraría al commit d.code-workspace: {absoluta}" in lineas, lineas
    ilegible = [l for l in lineas if l.startswith("no entraría al commit c.code-workspace: no se pudo leer sus carpetas (")]
    assert len(ilegible) == 1 and ilegible[0].endswith("así que no se sabe si usan rutas relativas; si las usa, commitealo vos"), lineas
    assert caja.arbol() == antes and not (caja.raiz / ".git").exists()


REPO_DE_CODIGO = ("error: la raíz {} es la raíz de un repo de código (tiene archivos versionados y no tiene workspace.config.json): "
                  "la instancia quedaría en su git, con el hook y el primer commit. Conviene una carpeta aparte, al lado del repo; "
                  "si igual la querés acá, confirmalo con --confirmar-repo\n")


def repo_de_codigo(caja, carpeta):
    carpeta.mkdir(parents=True)
    caja.git(carpeta, "init", "-q")
    (carpeta / "src").mkdir()
    (carpeta / "src" / "app.ts").write_bytes(b"export const a = 1;\n")
    (carpeta / ".gitignore").write_bytes(b"node_modules/\n")
    caja.git(carpeta, "add", "-A")
    caja.git(carpeta, *IDENTIDAD, "commit", "-q", "-m", "base")
    return carpeta


def foto_del_repo(caja, carpeta):
    return caja.arbol(), (carpeta / ".git" / "config").read_bytes(), caja.git(carpeta, "rev-parse", "HEAD")


def test_en_la_raiz_de_un_repo_de_codigo_sin_confirmar_se_rechaza_sin_escribir_nada():
    caja = Caja()
    repo_de_codigo(caja, caja.raiz)
    antes = foto_del_repo(caja, caja.raiz)
    for extra in (("--ensayo", "--commitear"), ("--commitear",), ()):
        codigo, salida, errores = caja.cli(caja.spec(), *extra, entorno=IDENTIDAD_ENV)
        assert codigo == 2 and salida == "", (extra, codigo, salida, errores)
        assert errores == REPO_DE_CODIGO.format(caja.raiz), (extra, errores)
        assert foto_del_repo(caja, caja.raiz) == antes, extra
    assert caja.git(caja.raiz, "status", "--porcelain") == ""


def test_en_la_raiz_de_un_repo_de_codigo_con_confirmacion_se_aplica_sin_commitear_workspace_local():
    caja = Caja()
    repo_de_codigo(caja, caja.raiz)
    codigo, salida, errores = caja.cli(caja.spec(), "--commitear", "--confirmar-repo", entorno=IDENTIDAD_ENV)
    assert codigo == 0 and errores == "", (codigo, errores)
    lineas = salida.splitlines()
    assert "ya existía .gitignore" in lineas and "falta en .gitignore: workspace.local.json" in lineas, lineas
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(COMMIT_HECHO % (len(sin_lo_local()) - 1), commit[0]), commit
    assert caja.git(caja.raiz, "log", "--format=%s") == "chore: crea la instancia con odd-ws\nbase"
    assert "workspace.local.json" not in rastreados(caja)
    assert caja.git(caja.raiz, "status", "--porcelain") == "?? workspace.local.json"


def test_workspace_local_nunca_entra_al_commit_aunque_el_gitignore_no_lo_excluya():
    caja, (codigo, salida, errores) = primer_commit(lambda c: (c.raiz / ".gitignore").write_bytes(b"*.log\n"))
    assert codigo == 0 and errores == "", (codigo, errores)
    assert "falta en .gitignore: workspace.local.json" in salida.splitlines(), salida
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(COMMIT_HECHO % (len(sin_lo_local()) - 1), commit[0]), commit
    assert "workspace.local.json" not in rastreados(caja)
    (caja.raiz / "workspace.local.json").unlink()
    codigo, salida, errores = caja.cli(caja.spec(), "--commitear", entorno=IDENTIDAD_ENV)
    assert codigo == 0 and errores == "", (codigo, errores)
    assert lineas_de_commit(salida) == ["commit: no hace falta; lo que se creó lo ignora git o es workspace.local.json, "
                                        "que nunca entra a un commit"], salida
    assert caja.git(caja.raiz, "rev-list", "--count", "HEAD") == "1"
    assert caja.git(caja.raiz, "status", "--porcelain") == "?? .gitignore\n?? workspace.local.json"


def test_una_subcarpeta_de_un_repo_de_codigo_sigue_sin_preguntar_y_sin_tocar_su_git():
    caja = Caja()
    externo = repo_de_codigo(caja, caja.base / "externo")
    antes = (externo / ".git" / "config").read_bytes(), caja.git(externo, "rev-parse", "HEAD")
    caja.raiz = externo / "sub" / "instancia"
    codigo, salida, errores = caja.cli(caja.spec(), "--commitear", entorno=IDENTIDAD_ENV)
    assert codigo == 0 and errores == "", (codigo, errores)
    assert any(l.startswith("commit: no se hizo; la raíz está dentro del repo ") for l in salida.splitlines()), salida
    assert ((externo / ".git" / "config").read_bytes(), caja.git(externo, "rev-parse", "HEAD")) == antes
    assert (caja.raiz / "workspace.config.json").is_file()


def test_completar_una_instancia_que_vive_en_la_raiz_de_un_repo_no_pide_confirmacion():
    caja = Caja()
    repo_de_codigo(caja, caja.raiz)
    assert caja.cli(caja.spec(), "--commitear", "--confirmar-repo", entorno=IDENTIDAD_ENV)[0] == 0
    caja.git(caja.raiz, "rm", "-q", "CLAUDE.md")
    caja.git(caja.raiz, *IDENTIDAD, "commit", "-q", "-m", "sin indice")
    codigo, salida, errores = caja.cli(caja.spec(), "--commitear", entorno=IDENTIDAD_ENV)
    assert codigo == 0 and errores == "", (codigo, errores)
    assert "creado CLAUDE.md" in salida.splitlines(), salida
    commit = lineas_de_commit(salida)
    assert len(commit) == 1 and re.fullmatch(r"commit: [0-9a-f]{7,} con 1 archivos", commit[0]), commit


def test_el_aislamiento_de_git_dejo_vacias_las_config_global_y_del_sistema():
    assert CAJAS
    for caja in CAJAS:
        assert caja.global_.read_bytes() == b"" and caja.sistema.read_bytes() == b"", caja.base


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if hay_repo_arriba(tempfile.gettempdir()):
        print("el directorio temporal está dentro de un repo: el aislamiento de las pruebas no vale")
        return 1
    pruebas = [(nombre, funcion) for nombre, funcion in globals().items() if nombre.startswith("test_") and callable(funcion)]
    fallas = 0
    inicio = time.perf_counter()
    try:
        for nombre, prueba in pruebas:
            desde = time.perf_counter()
            try:
                prueba()
                print(f"ok    {nombre} ({time.perf_counter() - desde:.1f} s)")
            except AssertionError as error:
                fallas += 1
                print(f"FALLA {nombre}: {error}")
            except Exception as error:
                fallas += 1
                print(f"ERROR {nombre}: {type(error).__name__}: {error}")
    finally:
        _limpiar()
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde en {time.perf_counter() - inicio:.1f} s")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
