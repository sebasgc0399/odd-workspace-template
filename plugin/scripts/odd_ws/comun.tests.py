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
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent
PLUGIN = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))


def m():
    return importlib.import_module("odd_ws.comun")


def paquete():
    return importlib.import_module("odd_ws")


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Temporal:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="comun-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onerror=_forzar_borrado)


def _entorno_limpio():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, env=_entorno_limpio())


def repo_con_archivo(base):
    repo = base / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "prueba@example.com")
    git(repo, "config", "user.name", "Prueba")
    archivo = repo / "a.txt"
    archivo.write_text("uno\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "update-index", "--refresh")
    return repo, archivo


def ensuciar_stat(archivo):
    time.sleep(1.2)
    os.utime(archivo, None)


def test_entorno_git_quita_las_variables_que_apuntan_a_otro_repo():
    base = {nombre: "x" for nombre in m().VARIABLES_DE_REPO_GIT}
    base["PATH"] = "ruta"
    env = m().entorno_git(base)
    for nombre in m().VARIABLES_DE_REPO_GIT:
        if nombre != "GIT_CONFIG_COUNT":
            assert nombre not in env, nombre
    assert env["PATH"] == "ruta"


def test_entorno_git_fija_auto_refresh_index_por_proceso():
    env = m().entorno_git({"GIT_CONFIG_COUNT": "3", "GIT_CONFIG_KEY_0": "core.pager"})
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    assert (env["GIT_CONFIG_COUNT"], env["GIT_CONFIG_KEY_0"], env["GIT_CONFIG_VALUE_0"]) == ("1", "diff.autoRefreshIndex", "false")


def test_entorno_git_no_toca_el_entorno_que_recibe():
    base = {"GIT_DIR": "x"}
    m().entorno_git(base)
    assert base == {"GIT_DIR": "x"}


def test_entorno_git_por_defecto_parte_del_entorno_del_proceso():
    previo = os.environ.get("ODD_WS_PRUEBA")
    os.environ["ODD_WS_PRUEBA"] = "si"
    try:
        assert m().entorno_git()["ODD_WS_PRUEBA"] == "si"
    finally:
        if previo is None:
            del os.environ["ODD_WS_PRUEBA"]
        else:
            os.environ["ODD_WS_PRUEBA"] = previo


def test_git_diff_con_entorno_git_no_reescribe_el_indice():
    with Temporal() as base:
        repo, archivo = repo_con_archivo(base)
        ensuciar_stat(archivo)
        indice = repo / ".git" / "index"
        antes = indice.read_bytes()
        subprocess.run(["git", "-C", str(repo), "diff", "--stat"], capture_output=True, check=True, env=m().entorno_git(_entorno_limpio()))
        assert indice.read_bytes() == antes


def test_control_positivo_sin_entorno_git_el_diff_si_reescribe_el_indice():
    with Temporal() as base:
        repo, archivo = repo_con_archivo(base)
        ensuciar_stat(archivo)
        indice = repo / ".git" / "index"
        antes = indice.read_bytes()
        subprocess.run(["git", "-C", str(repo), "diff", "--stat"], capture_output=True, check=True, env=_entorno_limpio())
        assert indice.read_bytes() != antes, "el instrumento no sabe decir que si: el diff tampoco reescribio el indice"


def test_git_con_indice_heredado_de_un_hook_lee_el_repo_correcto():
    with Temporal() as base:
        repo, _ = repo_con_archivo(base)
        contaminado = _entorno_limpio()
        contaminado["GIT_INDEX_FILE"] = str(base / "no-existe")
        sucio = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, env=contaminado)
        limpio = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, env=m().entorno_git(contaminado))
        assert sucio.stdout.strip() == b"", "control: con el indice heredado git no ve el archivo"
        assert limpio.stdout.strip() == b"a.txt"


def test_id_valido_acepta_letras_numeros_guion_y_guion_bajo():
    for valor in ("a", "Sesion-1_x", "0" * 128, "abc123"):
        assert m().id_valido(valor), valor


def test_id_valido_rechaza_lo_que_podria_salirse_de_la_carpeta():
    for valor in ("", "../x", "a/b", "a\\b", "a.b", "a b", "a\n", "0" * 129, "plugin:agente", None, 7, b"abc"):
        assert not m().id_valido(valor), repr(valor)


def test_decodificar_quita_el_bom_y_no_lanza_con_bytes_invalidos():
    assert m().decodificar("﻿hola ñ".encode("utf-8")) == "hola ñ"
    assert m().decodificar(b"a\xffb") == "a�b"
    assert m().decodificar(b"") == ""


def test_decodificar_solo_quita_el_bom_del_comienzo():
    assert m().decodificar("a﻿b".encode("utf-8")) == "a﻿b"


def test_lineas_numera_desde_uno_y_quita_el_cr():
    assert m().lineas("a\r\nb\nc") == [(1, "a"), (2, "b"), (3, "c")]


def test_lineas_no_cuenta_la_linea_vacia_del_salto_final():
    assert m().lineas("a\n") == [(1, "a")]
    assert m().lineas("a\n\n") == [(1, "a"), (2, "")]
    assert m().lineas("") == []


def test_cargar_por_ruta_carga_un_archivo_con_guion():
    with Temporal() as base:
        ruta = base / "con-guion.py"
        ruta.write_text("VALOR = 41 + 1\n", encoding="utf-8")
        modulo = m().cargar_por_ruta(ruta, "con_guion")
        assert modulo.VALOR == 42 and modulo.__name__ == "con_guion"


class Flujo:
    def __init__(self):
        self.buffer = io.BytesIO()
        self.texto = io.StringIO()

    def write(self, texto):
        self.texto.write(texto)

    def flush(self):
        pass


def test_correr_hook_escribe_stdout_texto_y_stderr_en_bytes_utf8():
    entrada, salida, error = io.BytesIO(b'{"a": 1}'), Flujo(), Flujo()
    recibido = []

    def manejador(crudo):
        recibido.append(crudo)
        return 2, "fuera", "está mal → así".encode("utf-8")

    codigo = m().correr_hook(manejador, entrada, salida, error)
    assert codigo == 2
    assert recibido == [b'{"a": 1}']
    assert salida.texto.getvalue() == "fuera"
    assert error.buffer.getvalue() == "está mal → así".encode("utf-8")


def test_correr_hook_falla_abierto_si_el_manejador_lanza():
    salida, error = Flujo(), Flujo()

    def manejador(_crudo):
        raise RuntimeError("roto")

    assert m().correr_hook(manejador, io.BytesIO(b""), salida, error) == 0
    assert salida.texto.getvalue() == "" and error.buffer.getvalue() == b""


def test_correr_hook_falla_abierto_ante_system_exit():
    def manejador(_crudo):
        sys.exit(3)

    assert m().correr_hook(manejador, io.BytesIO(b""), Flujo(), Flujo()) == 0


def test_silencio_no_escribe_nada_y_sale_con_cero():
    salida, error = Flujo(), Flujo()
    assert m().correr_hook(lambda _crudo: m().SILENCIO, io.BytesIO(b""), salida, error) == 0
    assert salida.texto.getvalue() == "" and error.buffer.getvalue() == b""


HOOK = """import sys
from odd_ws.comun import correr_hook

sys.exit(correr_hook(lambda crudo: (2, "", "bloqueado: está mal → así".encode("utf-8"))))
"""


def test_hook_real_importa_el_paquete_sin_tocar_sys_path_y_bloquea_en_utf8():
    with Temporal() as base:
        scripts = base / "cache" / "plugin" / "scripts"
        shutil.copytree(SCRIPTS / "odd_ws", scripts / "odd_ws", ignore=shutil.ignore_patterns("__pycache__", "*.tests.py"))
        (scripts / "hook.py").write_text(HOOK, encoding="utf-8")
        env = dict(_entorno_limpio(), PYTHONIOENCODING="cp1252")
        env.pop("PYTHONPATH", None)
        r = subprocess.run([sys.executable, str(scripts / "hook.py")], input=b"{}", capture_output=True, timeout=60, cwd=str(base), env=env)
        assert r.returncode == 2, r.stderr
        assert r.stdout == b""
        assert r.stderr == "bloqueado: está mal → así".encode("utf-8")


def test_raiz_de_instancia_prefiere_claude_project_dir():
    with Temporal() as base:
        instancia = base / "instancia"
        ticket = instancia / "tickets" / "T-1"
        ticket.mkdir(parents=True)
        (instancia / "workspace.config.json").write_text("{}", encoding="utf-8")
        otra = base / "otra"
        otra.mkdir()
        assert m().raiz_de_instancia({"CLAUDE_PROJECT_DIR": str(ticket)}, str(otra)) == instancia
        assert m().raiz_de_instancia({}, str(ticket)) == instancia
        assert m().raiz_de_instancia({}, str(otra)) is None


def test_plazo_de_lee_el_argumento_sin_poder_fallar():
    assert m().PLAZO_POR_DEFECTO == 8
    assert m().plazo_de([]) == 8
    assert m().plazo_de(["--plazo", "25"]) == 25
    assert m().plazo_de(["x", "--plazo", "2.5"]) == 2.5
    for malo in (["--plazo"], ["--plazo", "x"], ["--plazo", "0"], ["--plazo", "-3"], ["--plazo", "nan"], ["--plazo", "inf"]):
        assert m().plazo_de(malo) == 8, malo


def test_el_dispatcher_usa_el_mismo_plazo_de():
    assert importlib.import_module("verificar_capa").plazo_de is m().plazo_de


def test_temporal_sigue_el_orden_de_os_tmpdir_de_node():
    if os.name == "nt":
        assert m().temporal({"TEMP": "C:\\a", "TMP": "C:\\b", "SYSTEMROOT": "C:\\w"}) == "C:\\a"
        assert m().temporal({"TMP": "C:\\b", "SYSTEMROOT": "C:\\w"}) == "C:\\b"
        assert m().temporal({"SYSTEMROOT": "C:\\w"}) == os.path.join("C:\\w", "temp")
        assert m().temporal({"WINDIR": "C:\\v"}) == os.path.join("C:\\v", "temp")
        assert m().temporal({"TMPDIR": "C:\\c"}) is None
    else:
        assert m().temporal({"TMPDIR": "/a", "TEMP": "/b"}) == "/a"
        assert m().temporal({"TEMP": "/b"}) == "/tmp"


def test_los_dos_guards_usan_el_mismo_temporal():
    for nombre in ("writer_guard", "guard_comandos"):
        assert importlib.import_module(nombre).temporal is m().temporal, nombre


def _version_plugin():
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def test_la_api_es_la_version_del_schema():
    assert paquete().API == importlib.import_module("config_loader").VERSION_SOPORTADA


def test_la_mayor_del_plugin_es_la_api():
    mayor = int(_version_plugin().split(".")[0])
    assert mayor == paquete().API or (mayor == 0 and paquete().API == 1), (mayor, paquete().API)


PUBLICO_V1 = {
    "comun": ("VARIABLES_DE_REPO_GIT", "decodificar", "entorno_git", "id_valido", "lineas"),
    "tsql": ("analizar", "argumentos", "bloques_catch", "comentarios_agregados", "depurar", "linea_de",
             "precalcular", "problemas_de_bytes", "sql_dinamico"),
}


def test_la_superficie_publica_esta_congelada():
    assert paquete().PUBLICO == PUBLICO_V1, "cambio la API publica: decidir si sube la version mayor y actualizar PUBLICO_V1"


def test_cada_nombre_publico_existe():
    for modulo, nombres in paquete().PUBLICO.items():
        cargado = importlib.import_module("odd_ws." + modulo)
        for nombre in nombres:
            assert hasattr(cargado, nombre), f"{modulo}.{nombre}"


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
