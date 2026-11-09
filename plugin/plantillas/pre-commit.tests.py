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
PLANTILLA = AQUI / "pre-commit"
PLUGIN = AQUI.parent
REPO = PLUGIN.parent
HOOKS_DEL_REPO = REPO / ".githooks"
SONDA = HOOKS_DEL_REPO / "python.sh"
BARRIDO = REPO / "tools" / "barrido.py"
CARGA = '. "${0%/*}/python.sh"'
ORDEN = ("python3", "python", "py")
INTERPRETES = ("python", "python.exe", "python3", "python3.exe", "py", "py.exe")
SIN_PYTHON = "Python was not found; run without arguments to install from the Microsoft Store"
SOBRANTES = []
CASOS = (
    ({"python3": True}, "python3"),
    ({"python3": False, "python": True}, "python"),
    ({"python3": False, "python": False, "py": True}, "py"),
    ({"python3": True, "python": True, "py": True}, "python3"),
)

SUITE = "import sys\nprint('suite sql corrio')\nsys.exit(%d)\n"


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def entorno(base):
    for nombre in ("gitconfig-global", "gitconfig-sistema"):
        if not (base / nombre).exists():
            (base / nombre).write_bytes(b"")
    propio = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    propio.update(GIT_CONFIG_GLOBAL=str(base / "gitconfig-global"), GIT_CONFIG_SYSTEM=str(base / "gitconfig-sistema"),
                  GIT_CONFIG_NOSYSTEM="1")
    return propio


def localizar_sh():
    encontrado = shutil.which("sh")
    if encontrado:
        return encontrado
    for relativa in (("bin", "sh.exe"), ("usr", "bin", "sh.exe")):
        candidato = Path(shutil.which("git")).resolve().parents[1].joinpath(*relativa)
        if candidato.is_file():
            return str(candidato)
    raise AssertionError("no hay un sh para correr los hooks")


def sin_python(base):
    if os.name == "nt":
        carpetas = [os.path.dirname(shutil.which("git")), os.path.dirname(localizar_sh())]
    else:
        carpeta = base / "sistema"
        carpeta.mkdir()
        for nombre in ("git", "sh"):
            (carpeta / nombre).symlink_to(shutil.which(nombre))
        carpetas = [str(carpeta)]
    assert not any(Path(c, n).exists() for c in carpetas for n in INTERPRETES), carpetas
    return carpetas


def interpretes(base, sanos):
    carpeta = base / "interpretes"
    carpeta.mkdir()
    registro = base / "llamados.txt"
    real = Path(sys.executable).as_posix()
    for nombre, sano in sanos.items():
        anotar = "printf '%s\\n' {} >> \"{}\"\n".format(nombre, registro.as_posix())
        cuerpo = 'exec "{}" "$@"\n'.format(real) if sano else 'echo "{}" >&2\nexit 9\n'.format(SIN_PYTHON)
        ruta = carpeta / nombre
        ruta.write_bytes(("#!/bin/sh\n" + anotar + cuerpo).encode("utf-8"))
        ruta.chmod(0o755)
    return carpeta, registro


def path_con(base, sanos):
    carpeta, registro = interpretes(base, sanos)
    return os.pathsep.join([str(carpeta), *sin_python(base)]), registro


def llamados(registro):
    return registro.read_text(encoding="utf-8").split() if registro.exists() else []


def esperados(sanos, elegido):
    return {nombre for nombre in ORDEN[:ORDEN.index(elegido) + 1] if nombre in sanos}


class Temporal:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="pre-commit-test-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


class Instancia:
    def __init__(self, suite=0):
        self.suite = suite

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="pre-commit-test-"))
        self.raiz = self.base / "instancia"
        self.raiz.mkdir()
        try:
            return self._armar()
        except BaseException:
            self.__exit__()
            raise

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.raiz, capture_output=True, env=entorno(self.base))

    def _armar(self):
        self.git("init", "-q")
        for clave, valor in (("user.name", "prueba"), ("user.email", "prueba@example.com"), ("core.hooksPath", "ganchos"),
                             ("core.autocrlf", "false")):
            self.git("config", clave, valor)
        (self.raiz / "ganchos").mkdir()
        shutil.copy(PLANTILLA, self.raiz / "ganchos" / "pre-commit")
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
        self.git("add", "-A")
        r = subprocess.run(["git", "commit", "-q", "-m", "prueba"], cwd=self.raiz, capture_output=True,
                           env={**entorno(self.base), **(extra or {})})
        return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")

    def commits(self):
        r = self.git("rev-list", "--count", "HEAD")
        return int(r.stdout) if r.returncode == 0 else 0

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


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
        codigo, salida = w.commit({"PATH": os.pathsep.join(sin_python(w.base))})
        assert codigo != 0 and w.commits() == 0, salida
        assert "python no corre" in salida and "sin anotar" not in salida, salida


def test_la_plantilla_corre_con_el_primero_que_arranca_de_python3_python_y_py():
    for sanos, elegido in CASOS:
        with Instancia() as w:
            w.local({"plugin_root": str(PLUGIN)})
            path, registro = path_con(w.base, sanos)
            codigo, salida = w.commit({"PATH": path})
            assert codigo == 0 and "suite sql corrio" in salida and w.commits() == 1, (sanos, salida)
            usados = llamados(registro)
            assert usados[-1:] == [elegido] and set(usados) == esperados(sanos, elegido), (sanos, usados)


def test_un_python3_que_no_corre_no_cuenta_y_sin_otro_bloquea_nombrando_los_tres():
    with Instancia() as w:
        w.local({"plugin_root": str(PLUGIN)})
        path, registro = path_con(w.base, {"python3": False})
        codigo, salida = w.commit({"PATH": path})
        assert codigo != 0 and w.commits() == 0, salida
        assert "pre-commit: python no corre" in salida and "python3, python y py" in salida and "sin anotar" not in salida, salida
        assert llamados(registro) == ["python3"], llamados(registro)


def correr_sonda(base, sanos):
    carpeta = base / "ganchos-del-repo"
    carpeta.mkdir()
    shutil.copyfile(SONDA, carpeta / "python.sh")
    hook = carpeta / "probar"
    hook.write_bytes(("#!/bin/sh\n%s\nprintf '%%s\\n' \"$python\"\n" % CARGA).encode("ascii"))
    path, registro = path_con(base, sanos)
    r = subprocess.run([localizar_sh(), hook.as_posix()], capture_output=True, env={**entorno(base), "PATH": path}, timeout=60)
    return r.returncode, r.stdout.decode("utf-8", "replace").strip(), r.stderr.decode("utf-8", "replace"), llamados(registro)


def test_la_sonda_de_los_hooks_del_repo_elige_el_primero_que_arranca():
    for sanos, elegido in CASOS:
        with Temporal() as base:
            codigo, salida, errores, usados = correr_sonda(base, sanos)
            assert (codigo, salida) == (0, elegido), (sanos, codigo, salida, errores)
            assert usados[-1:] == [elegido] and set(usados) == esperados(sanos, elegido), (sanos, usados)


def test_la_sonda_de_los_hooks_del_repo_sin_ningun_python_que_corra_sale_con_uno_y_lo_dice():
    for sanos in ({}, {"python3": False, "python": False, "py": False}):
        with Temporal() as base:
            codigo, salida, errores, _ = correr_sonda(base, sanos)
            assert (codigo, salida) == (1, ""), (sanos, codigo, salida, errores)
            assert "probar: python no corre desde el PATH" in errores and "python3, python y py" in errores, errores


def test_los_hooks_del_repo_cargan_la_sonda_antes_de_usar_python_y_no_lo_llaman_por_su_nombre():
    for nombre in ("commit-msg", "pre-commit", "pre-push"):
        lineas = (HOOKS_DEL_REPO / nombre).read_text(encoding="ascii").splitlines()
        assert lineas[0] == "#!/bin/sh" and CARGA in lineas, (nombre, lineas)
        con_python = [n for n, linea in enumerate(lineas) if '"$python"' in linea]
        assert con_python and min(con_python) > lineas.index(CARGA), (nombre, lineas)
        por_nombre = [linea for linea in lineas if re.search(r"(^|[\s;|&(])(python3?|py)\s", linea)]
        assert not por_nombre, (nombre, por_nombre)


def test_el_commit_msg_del_repo_barre_con_python3_cuando_no_hay_python():
    with Temporal() as base:
        repo = base / "repo"
        (repo / "ganchos").mkdir(parents=True)
        (repo / "tools").mkdir()
        for origen, destino in ((HOOKS_DEL_REPO / "commit-msg", "ganchos/commit-msg"), (SONDA, "ganchos/python.sh"),
                                (BARRIDO, "tools/barrido.py")):
            shutil.copy(origen, repo / destino)
        lista = base / "lista.txt"
        lista.write_text("terminoinventadoxyz\n", encoding="utf-8")
        path, registro = path_con(base, {"python3": True})
        env = {**entorno(base), "PATH": path, "ODD_WS_DENYLIST": str(lista)}
        for args in (("init", "-q"), ("config", "core.hooksPath", "ganchos"), ("config", "user.name", "prueba"),
                     ("config", "user.email", "prueba@example.com")):
            subprocess.run(["git", *args], cwd=repo, capture_output=True, env=entorno(base), check=True)

        def commit(mensaje):
            r = subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", mensaje], cwd=repo, capture_output=True, env=env, timeout=120)
            return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")

        codigo, salida = commit("chore: un mensaje limpio")
        assert codigo == 0 and "barrido limpio" in salida, salida
        assert llamados(registro) == ["python3", "python3"], llamados(registro)
        codigo, salida = commit("chore: menciona terminoinventadoxyz")
        assert codigo != 0 and "terminoinventadoxyz" in salida, salida


def test_la_plantilla_trae_la_misma_sonda_que_los_hooks_del_repo():
    sonda = SONDA.read_bytes()
    sonda.decode("ascii")
    assert b"\r" not in sonda and sonda.endswith(b"\n"), sonda
    assert sonda in PLANTILLA.read_bytes(), "la sonda de python.sh tiene que estar entera, tal cual, en la plantilla"


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
