import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLANTILLA = AQUI / "pre-commit"
PLUGIN = AQUI.parent
SOBRANTES = []

SUITE = "import sys\nprint('suite sql corrio')\nsys.exit(%d)\n"


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def entorno():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=entorno())


class Instancia:
    def __init__(self, suite=0):
        self.suite = suite

    def __enter__(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="pre-commit-test-"))
        try:
            return self._armar()
        except BaseException:
            self.__exit__()
            raise

    def _armar(self):
        git(self.raiz, "init", "-q")
        for clave, valor in (("user.name", "prueba"), ("user.email", "prueba@example.com"), ("core.hooksPath", "ganchos"),
                             ("core.autocrlf", "false")):
            git(self.raiz, "config", clave, valor)
        (self.raiz / "ganchos").mkdir()
        shutil.copyfile(PLANTILLA, self.raiz / "ganchos" / "pre-commit")
        (self.raiz / "workspace.config.json").write_text(
            json.dumps({"schema_version": 1, "layers": {"sql": {"extensions": [".sql"]}}}), encoding="utf-8")
        suites = self.raiz / ".claude" / "reglas"
        suites.mkdir(parents=True)
        (suites / "verificar_sql.tests.py").write_text(SUITE % self.suite, encoding="utf-8")
        return self

    def local(self, contenido):
        datos = json.dumps(contenido) if isinstance(contenido, dict) else contenido
        (self.raiz / "workspace.local.json").write_text(datos, encoding="utf-8")

    def commit(self, extra=None):
        (self.raiz / "a.txt").write_text("cambio\n", encoding="utf-8")
        git(self.raiz, "add", "-A")
        r = subprocess.run(["git", "commit", "-q", "-m", "prueba"], cwd=self.raiz, capture_output=True, env={**entorno(), **(extra or {})})
        return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")

    def commits(self):
        r = git(self.raiz, "rev-list", "--count", "HEAD")
        return int(r.stdout) if r.returncode == 0 else 0

    def __exit__(self, *_):
        shutil.rmtree(self.raiz, onexc=_quitar)
        if self.raiz.exists():
            SOBRANTES.append(str(self.raiz))


def test_con_plugin_root_valido_corre_las_suites_y_deja_commitear():
    assert os.sep == "/" or "\\" in str(PLUGIN), str(PLUGIN)
    with Instancia() as w:
        w.local({"plugin_root": str(PLUGIN), "repos": {}})
        codigo, salida = w.commit()
        assert codigo == 0, salida
        assert "== sql: .claude/reglas/verificar_sql.tests.py" in salida and "suite sql corrio" in salida, salida
        assert w.commits() == 1


def test_corre_las_suites_de_esta_instancia_aunque_la_sesion_sea_de_otra_carpeta():
    with Instancia(suite=1) as w, Instancia() as otra:
        w.local({"plugin_root": str(PLUGIN)})
        codigo, salida = w.commit({"CLAUDE_PROJECT_DIR": str(otra.raiz)})
        assert codigo != 0 and "suites en rojo: sql" in salida and w.commits() == 0, salida


def test_una_suite_en_rojo_bloquea_el_commit():
    with Instancia(suite=1) as w:
        w.local({"plugin_root": str(PLUGIN)})
        codigo, salida = w.commit()
        assert codigo != 0 and "suite sql corrio" in salida and "suites en rojo: sql" in salida, salida
        assert w.commits() == 0


def test_sin_plugin_root_bloquea_con_el_arreglo():
    with Instancia() as w:
        codigo, salida = w.commit()
        assert codigo != 0 and w.commits() == 0, salida
        assert "sin anotar" in salida and "/odd-ws:doctor --arreglar plugin-root" in salida, salida
    with Instancia() as w:
        w.local({"repos": {}})
        codigo, salida = w.commit()
        assert codigo != 0 and "sin anotar" in salida, salida


def test_plugin_root_viejo_bloquea_y_nombra_la_ruta():
    with Instancia() as w:
        vieja = str(w.raiz / "version-borrada")
        w.local({"plugin_root": vieja})
        codigo, salida = w.commit()
        assert codigo != 0 and w.commits() == 0, salida
        assert "version-borrada" in salida and "/odd-ws:doctor --arreglar plugin-root" in salida, salida


def test_sin_python_en_el_path_bloquea_y_lo_dice_en_vez_de_culpar_a_plugin_root():
    with Instancia() as w:
        w.local({"plugin_root": str(PLUGIN)})
        carpetas = [os.path.dirname(shutil.which("git")), os.path.dirname(shutil.which("sh"))]
        assert not any(Path(c, n).exists() for c in carpetas for n in ("python.exe", "python", "python3")), carpetas
        codigo, salida = w.commit({"PATH": os.pathsep.join(carpetas)})
        assert codigo != 0 and w.commits() == 0, salida
        assert "python no corre" in salida and "sin anotar" not in salida, salida


def test_workspace_local_ilegible_bloquea_sin_traceback():
    for malo in ("{no es json", "[1, 2]", '{"plugin_root": 7}'):
        with Instancia() as w:
            w.local(malo)
            codigo, salida = w.commit()
            assert codigo != 0 and w.commits() == 0 and "Traceback" not in salida, (malo, salida)
            assert "/odd-ws:doctor --arreglar plugin-root" in salida, (malo, salida)


def test_la_copia_de_emergencia_gana_aunque_plugin_root_este_viejo():
    with Instancia() as w:
        shutil.copytree(PLUGIN / "scripts", w.raiz / ".claude" / "plugin" / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__", "*.tests.py"))
        w.local({"plugin_root": str(w.raiz / "version-borrada")})
        codigo, salida = w.commit()
        assert codigo == 0 and "suite sql corrio" in salida, salida
        assert w.commits() == 1


def test_la_plantilla_es_ascii_con_fin_de_linea_lf_y_empieza_con_sh():
    crudo = PLANTILLA.read_bytes()
    assert crudo.startswith(b"#!/bin/sh\n"), crudo[:20]
    assert b"\r" not in crudo, "un CR rompe el script en el sh de git"
    crudo.decode("ascii")


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
    if SOBRANTES:
        fallas += 1
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
