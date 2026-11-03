import atexit
import json
import os
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
IDS_DE_INSTANCIA = ("plugin-root", "config", "instancia-hooks", "instancia-plugin", f"writer-{CAPA}", "agentes-skills", "agentes-hooks")
VARIABLES_DE_GIT_AISLADAS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
IDENTIDAD = ("-c", "user.name=Prueba", "-c", "user.email=prueba@example.com", "-c", "commit.gpgsign=false")
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

    def cli(self, spec, *extra):
        ruta = self.base / "spec.json"
        ruta.write_text(json.dumps(spec), encoding="utf-8")
        resultado = subprocess.run(
            [sys.executable, "-W", "error", str(SCRIPT), "--spec", str(ruta), "--raiz", str(self.raiz), *extra],
            capture_output=True, env=self.entorno, timeout=300,
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
        self.cli = self.caja.cli(self.spec)
        self.doctor = self.caja.doctor() if self.cli[0] == 0 else None
        self.sh = localizar_sh()
        self.pre_commit = None
        self.commit = None
        self.arbol_tras_el_commit = None
        if self.cli[0] == 0:
            if self.sh:
                self.pre_commit = subprocess.run([self.sh, ".githooks/pre-commit"], cwd=self.caja.raiz, capture_output=True, env=self.caja.entorno, timeout=300)
            self.caja.git(self.caja.raiz, "add", "-A")
            self.commit = subprocess.run(["git", *IDENTIDAD, "commit", "-m", "primer commit de la instancia"], cwd=self.caja.raiz, capture_output=True, env=self.caja.entorno, timeout=300)
            self.arbol_tras_el_commit = self.caja.arbol()


_NUEVA = []


def instancia_nueva():
    if not _NUEVA:
        _NUEVA.append(InstanciaNueva())
    return _NUEVA[0]


def archivos_esperados():
    return [
        "workspace.config.json", "workspace.local.json", ".gitignore",
        f".claude/agents/writer-{CAPA}.md", f".claude/agents/revisor-{CAPA}.md", f".claude/skills/capa-{CAPA}/SKILL.md", ".claude/skills/criterios/SKILL.md",
        ".claude/reglas/matriz.csv", ".claude/reglas/evidencia.md", f".claude/reglas/verificar_{CAPA}.py", f".claude/reglas/verificar_{CAPA}.tests.py",
        "CLAUDE.md", "tickets/_plantilla/CLAUDE.md",
        ".githooks/pre-commit", ".claude/settings.json",
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


def test_el_primer_commit_de_la_instancia_corre_el_pre_commit_y_sale_con_cero():
    nueva = instancia_nueva()
    assert nueva.commit is not None and nueva.commit.returncode == 0, (nueva.commit.stdout, nueva.commit.stderr)
    assert SUITE_EN_VERDE in nueva.commit.stdout + nueva.commit.stderr, (nueva.commit.stdout, nueva.commit.stderr)
    assert nueva.caja.git(nueva.caja.raiz, "log", "--format=%s") == "primer commit de la instancia"
    rastreados = set(nueva.caja.git(nueva.caja.raiz, "ls-files").splitlines())
    for ruta in archivos_esperados():
        if ruta != "workspace.local.json":
            assert ruta in rastreados, ruta
    assert "workspace.local.json" not in rastreados


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
