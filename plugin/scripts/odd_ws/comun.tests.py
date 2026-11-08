import hashlib
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


VARIABLES_DE_GIT_AISLADAS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def _entorno_limpio():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in VARIABLES_DE_GIT_AISLADAS}


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


def test_host_de_lee_el_argumento_y_sin_el_es_claude_code():
    assert m().HOST_POR_DEFECTO == "claude-code"
    assert m().host_de([]) == "claude-code"
    assert m().host_de(["--plazo", "8"]) == "claude-code"
    assert m().host_de(["--host", "codex"]) == "codex"
    assert m().host_de(["--plazo", "8", "--host", "codex", "--host", "otro"]) == "codex", "cuenta el primero, como --plazo"
    assert m().host_de(["--host", "gemini"]) == "gemini", "el nombre lo valida el registro de hosts"
    assert m().host_de(["--plazo", "8", "--host"]) is None, "un --host sin valor no vuelve al default"


def test_host_de_acepta_la_forma_con_igual():
    assert m().host_de(["--host=codex"]) == "codex"
    assert m().host_de(["--plazo", "8", "--host=gemini"]) == "gemini", "el nombre lo valida el registro de hosts"
    assert m().host_de(["--host=codex", "--host", "otro"]) == "codex", "cuenta el primero, con o sin igual"
    assert m().host_de(["--host", "codex", "--host=otro"]) == "codex"
    assert m().host_de(["--host="]) is None, "un --host= vacío no vuelve al default"


def test_los_cuatro_hooks_usan_el_mismo_host_de():
    for nombre in ("verificar_capa", "writer_guard", "guard_comandos", "writer_stop"):
        assert importlib.import_module(nombre).host_de is m().host_de, nombre


def eventos():
    return importlib.import_module("odd_ws.eventos")


def test_combinar_gana_el_bloqueo_con_todos_los_mensajes_en_orden():
    E = eventos()
    assert m().combinar([]) == E.Permitir()
    assert m().combinar([E.Permitir(), E.Permitir()]) == E.Permitir()
    assert m().combinar([E.Contexto("a"), E.Permitir(), E.Contexto("b")]) == E.Contexto("a\n\nb")
    assert m().combinar([E.Contexto("a"), E.Bloquear("b"), E.Permitir(), E.Bloquear("c")]) == E.Bloquear("a\n\nb\n\nc")
    assert m().combinar([E.Bloquear("b"), E.Contexto("a")]) == E.Bloquear("b\n\na")
    assert m().combinar([E.Contexto("a"), E.Preguntar("p")]) == E.Preguntar("a\n\np"), "preguntar no se pierde"
    assert m().combinar([E.Preguntar("p"), E.Bloquear("b")]) == E.Bloquear("p\n\nb")


def test_por_ruta_decide_cada_ruta_aparte_y_combina():
    E = eventos()
    vistos = []

    def decidir(evento):
        vistos.append(evento)
        return {"/a": E.Bloquear("A"), "/b": E.Contexto("B")}.get(evento.rutas[0] if evento.rutas else None, E.Permitir())

    dos = E.Herramienta(fase="post", tipo="edicion", rutas=("/b", "/c", "/a"), sesion="s1")
    assert m().por_ruta(dos, decidir) == E.Bloquear("B\n\nA")
    assert vistos == [E.Herramienta(fase="post", tipo="edicion", rutas=(r,), sesion="s1") for r in ("/b", "/c", "/a")], vistos


def test_por_ruta_con_una_ruta_o_ninguna_pasa_el_evento_y_la_decision_tal_cual():
    E = eventos()
    for rutas in ((), ("/a",)):
        evento, vistos = E.Herramienta(fase="pre", tipo="edicion", rutas=rutas), []
        for decision in (E.Seguir("s"), E.Permitir(), E.Bloquear("b"), None):
            assert m().por_ruta(evento, lambda e: vistos.append(e) or decision) is decision, (rutas, decision)
        assert all(visto is evento for visto in vistos), rutas


def test_por_ruta_aisla_la_ruta_que_revienta_y_las_demas_deciden():
    E = eventos()

    def decidir(evento):
        if evento.rutas[0].startswith("/roto"):
            raise RuntimeError("roto")
        return {"/a": E.Bloquear("A"), "/b": E.Contexto("B")}.get(evento.rutas[0], E.Permitir())

    assert m().por_ruta(E.Herramienta(fase="post", tipo="edicion", rutas=("/roto", "/a", "/b")), decidir) == E.Bloquear("A\n\nB")
    assert m().por_ruta(E.Herramienta(fase="post", tipo="edicion", rutas=("/b", "/a", "/roto")), decidir) == E.Bloquear("B\n\nA")
    assert m().por_ruta(E.Herramienta(fase="pre", tipo="edicion", rutas=("/roto", "/roto2")), decidir) == E.Permitir()
    try:
        m().por_ruta(E.Herramienta(fase="pre", tipo="edicion", rutas=("/roto",)), decidir)
    except RuntimeError:
        pass
    else:
        raise AssertionError("con una sola ruta la excepción sigue llegando a correr, como en Claude Code")


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


def capas():
    return importlib.import_module("odd_ws.capas")


def edicion(*rutas):
    return {"tipo": "edicion", "rutas": list(rutas)}


def shell(comando, dialecto="posix"):
    return {"tipo": "shell", "comando": comando, "dialecto": dialecto}


def carpeta_de_fotos(base, nombre="a1.fotos"):
    carpeta = base / nombre
    carpeta.mkdir()
    return carpeta


def foto(carpeta, ruta, tipo="foto", contenido=b"x\n"):
    destino = Path(carpeta) / ("%s.%s" % (m().clave_foto(ruta), tipo))
    destino.write_bytes(contenido)
    return destino


def test_la_clave_de_la_foto_es_la_de_writer_guard():
    assert importlib.import_module("writer_guard").clave_foto is m().clave_foto
    ruta = os.path.abspath(os.path.join("x", "A.sql"))
    assert m().clave_foto(ruta) == hashlib.sha1(os.path.normcase(ruta).encode("utf-8")).hexdigest()
    assert m().clave_foto(os.path.join("x", "A.sql")) == m().clave_foto(ruta), "la relativa se resuelve contra el cwd"


def test_la_bitacora_guarda_un_registro_por_linea_en_ascii_y_se_lee_en_orden():
    with Temporal() as base:
        carpeta = carpeta_de_fotos(base)
        registros = [edicion(str(base / "á.sql")), shell("ls ñ", "powershell"), edicion(str(base / "b.sql"), str(base / "c.sql"))]
        for registro in registros:
            m().anotar_en_bitacora(str(carpeta), registro)
        crudo = (carpeta / capas().BITACORA).read_bytes()
        assert capas().BITACORA == "bitacora.jsonl"
        assert crudo.count(b"\n") == 3 and crudo.endswith(b"\n") and all(b < 128 for b in crudo), crudo
        assert [json.loads(linea) for linea in crudo.splitlines()] == registros
        assert m().leer_bitacora(str(carpeta)) == (registros, 0)


def test_una_linea_rota_o_con_otra_forma_se_cuenta_y_no_tapa_las_demas():
    with Temporal() as base:
        carpeta = carpeta_de_fotos(base)
        buenas = [edicion("/x/a.sql"), shell("ls")]
        rotas = ["{rota", json.dumps(edicion()), json.dumps(edicion("")), json.dumps({"tipo": "edicion", "rutas": "x"}),
                 json.dumps(edicion("/x/b.sql", 7)), json.dumps(shell("")), json.dumps(shell("ls", "cmd")),
                 json.dumps({"tipo": "otro"}), "[1]", "ÿ", json.dumps(edicion("/x/a\ud800b.sql")),
                 json.dumps(shell("ls \udfff"))]
        lineas = [json.dumps(buenas[0])] + rotas + ["", "  ", json.dumps(buenas[1])]
        (carpeta / capas().BITACORA).write_bytes(("\n".join(lineas) + "\n").encode("utf-8") + b"\x80{\n")
        assert m().leer_bitacora(str(carpeta)) == (buenas, len(rotas) + 1)


def test_archivos_de_la_bitacora_en_orden_sin_repetir_con_cada_ruta_del_parche():
    with Temporal() as base:
        carpeta = carpeta_de_fotos(base)
        a, b, c = (str(base / nombre) for nombre in ("a.sql", "b.sql", "c.sql"))
        for registro in (edicion(a), shell("echo x > " + str(base / "d.sql")), edicion(b, a, c), edicion(b)):
            m().anotar_en_bitacora(str(carpeta), registro)
        foto(carpeta, a)
        foto(carpeta, c, "nuevo", c.encode("utf-8"))
        assert m().archivos_de_la_bitacora(str(carpeta)) == ([a, b, c], [])


def test_sin_bitacora_y_sin_fotos_el_writer_no_toco_nada():
    with Temporal() as base:
        assert m().archivos_de_la_bitacora(str(base / "no-existe.fotos")) == ([], [])
        assert m().comandos_de_la_bitacora(str(base / "no-existe.fotos")) is None
        carpeta = carpeta_de_fotos(base)
        assert m().archivos_de_la_bitacora(str(carpeta)) == ([], [])
        (carpeta / "otro.txt").write_text("no es una foto", encoding="utf-8")
        assert m().archivos_de_la_bitacora(str(carpeta)) == ([], [])


def test_no_poder_leer_la_bitacora_nunca_es_que_no_toco_nada():
    with Temporal() as base:
        a = str(base / "a.sql")
        sin = carpeta_de_fotos(base, "sin.fotos")
        foto(sin, a)
        archivos, faltas = m().archivos_de_la_bitacora(str(sin))
        assert archivos == [] and any("bitácora no está" in f for f in faltas), faltas
        assert any("1 archivos con foto" in f for f in faltas), faltas
        vacia = carpeta_de_fotos(base, "vacia.fotos")
        (vacia / capas().BITACORA).write_bytes(b"")
        assert m().archivos_de_la_bitacora(str(vacia)) == ([], ["la bitácora está vacía"])
        foto(vacia, a)
        archivos, faltas = m().archivos_de_la_bitacora(str(vacia))
        assert archivos == [] and faltas[0] == "la bitácora está vacía" and len(faltas) == 2, faltas
        ilegible = carpeta_de_fotos(base, "ilegible.fotos")
        (ilegible / capas().BITACORA).mkdir()
        archivos, faltas = m().archivos_de_la_bitacora(str(ilegible))
        assert archivos == [] and any("no se pudo leer la bitácora" in f for f in faltas), faltas
        tapon = base / "tapon.fotos"
        tapon.write_text("no soy una carpeta", encoding="utf-8")
        archivos, faltas = m().archivos_de_la_bitacora(str(tapon))
        assert archivos == [] and any("no se pudo leer la carpeta de fotos" in f for f in faltas), faltas


def test_una_foto_sin_su_ruta_es_una_falta_y_la_marca_nuevo_se_recupera():
    with Temporal() as base:
        carpeta = carpeta_de_fotos(base)
        a, b, n, x = (str(base / nombre) for nombre in ("a.sql", "b.sql", "n.sql", "x.sql"))
        m().anotar_en_bitacora(str(carpeta), edicion(a))
        foto(carpeta, a)
        foto(carpeta, b)
        foto(carpeta, n, "nuevo", n.encode("utf-8"))
        foto(carpeta, x, "nuevo", b"")
        (carpeta / ("0" * 40 + ".tmp")).write_bytes(b"x")
        archivos, faltas = m().archivos_de_la_bitacora(str(carpeta))
        assert archivos == [a, n], archivos
        assert faltas == ["1 archivos nuevos no estaban en la bitácora y salen de su marca .nuevo",
                          "2 archivos con foto no están en la bitácora y la compuerta no los puede medir"], faltas


def test_una_ruta_que_no_se_codifica_es_una_linea_rota_y_no_revienta():
    with Temporal() as base:
        carpeta = carpeta_de_fotos(base)
        a, n = str(base / "a.sql"), str(base / "n.sql")
        m().anotar_en_bitacora(str(carpeta), edicion(a))
        m().anotar_en_bitacora(str(carpeta), edicion(n, str(base / "z\ud800.sql")))
        m().anotar_en_bitacora(str(carpeta), shell("echo \udfff > x"))
        foto(carpeta, n, "nuevo", n.encode("utf-8"))
        assert m().archivos_de_la_bitacora(str(carpeta)) == (
            [a, n], ["la bitácora tiene 2 líneas rotas", "1 archivos nuevos no estaban en la bitácora y salen de su marca .nuevo"])
        assert m().comandos_de_la_bitacora(str(carpeta)) == []


def test_comandos_de_la_bitacora_con_su_dialecto_y_none_si_no_se_lee():
    with Temporal() as base:
        carpeta = carpeta_de_fotos(base)
        for registro in (shell("ls"), edicion(str(base / "a.sql")), shell("Get-Item x", "powershell"), shell("ls")):
            m().anotar_en_bitacora(str(carpeta), registro)
        with open(carpeta / capas().BITACORA, "ab") as f:
            f.write(b"{rota\n")
        assert m().comandos_de_la_bitacora(str(carpeta)) == [("posix", "ls"), ("powershell", "Get-Item x"), ("posix", "ls")]
        ilegible = carpeta_de_fotos(base, "ilegible.fotos")
        (ilegible / capas().BITACORA).mkdir()
        assert m().comandos_de_la_bitacora(str(ilegible)) is None


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


def salida_de_git(carpeta_hooks, git_dir, git_comun, fin="\n"):
    return fin.join([carpeta_hooks, git_dir, git_comun]) + fin


def decidir(raiz, salida):
    return m().decidir_hooks(raiz, salida)


def repo_con_hooks(base, hooks):
    raiz = base / "r"
    (raiz / ".git" / "hooks").mkdir(parents=True)
    for nombre, contenido in hooks.items():
        (raiz / ".git" / "hooks" / nombre).write_bytes(contenido)
    return raiz


def test_el_comando_de_rutas_de_hooks_es_el_que_pregunta_las_tres_cosas():
    assert m().COMANDO_RUTAS_DE_HOOKS == ("rev-parse", "--git-path", "hooks", "--git-dir", "--git-common-dir")


def test_hooks_solo_de_ejemplo_se_pueden_tocar():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {"pre-commit.sample": b"x", "commit-msg.sample": b"y", "pre-push.sample": b"z"})
        decision = decidir(raiz, salida_de_git(".git/hooks", ".git", ".git"))
        assert decision.puede is True and decision.motivo == ""


def test_una_carpeta_de_hooks_que_no_existe_o_esta_vacia_se_puede_tocar():
    with Temporal() as base:
        raiz = base / "r"
        raiz.mkdir()
        assert decidir(raiz, salida_de_git(".git/hooks", ".git", ".git")).puede is True
        (raiz / ".git" / "hooks").mkdir(parents=True)
        assert decidir(raiz, salida_de_git(".git/hooks", ".git", ".git")).puede is True


def test_un_hook_propio_impide_tocarlo_y_el_motivo_lo_nombra():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {"pre-commit": b"#!/bin/sh\n", "commit-msg": b"#!/bin/sh\n", "pre-commit.sample": b"x"})
        decision = decidir(raiz, salida_de_git(".git/hooks", ".git", ".git"))
        carpeta = os.path.normpath(str(raiz / ".git" / "hooks"))
        assert decision.puede is False
        assert decision.motivo == f"hay hooks propios en {carpeta} (commit-msg, pre-commit), que dejarían de correr", decision.motivo


def test_solo_el_sufijo_sample_exacto_se_ignora():
    with Temporal() as base:
        for nombre in ("pre-commit.sample.bak", "sample", "post-commit.samples", "hook.SAMPLE"):
            raiz = repo_con_hooks(base, {nombre: b"x"})
            decision = decidir(raiz, salida_de_git(".git/hooks", ".git", ".git"))
            assert decision.puede is False and nombre in decision.motivo, (nombre, decision)
            shutil.rmtree(raiz, onerror=_forzar_borrado)


def test_una_subcarpeta_en_hooks_cuenta_como_propia():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {})
        (raiz / ".git" / "hooks" / "pre-commit.d").mkdir()
        decision = decidir(raiz, salida_de_git(".git/hooks", ".git", ".git"))
        assert decision.puede is False and "pre-commit.d" in decision.motivo


def test_las_rutas_relativas_se_normalizan_contra_la_raiz_y_las_absolutas_se_respetan():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {"pre-commit": b"x"})
        absolutas = decidir(raiz, salida_de_git((raiz / ".git" / "hooks").as_posix(), (raiz / ".git").as_posix(), (raiz / ".git").as_posix()))
        relativas = decidir(raiz, salida_de_git(".git/hooks", ".git", ".git"))
        assert absolutas == relativas and absolutas.puede is False
        con_rodeos = decidir(raiz, salida_de_git(".git/../.git/hooks", "./.git", "./.git/../.git"))
        assert con_rodeos == relativas


def test_un_worktree_enlazado_no_se_toca_aunque_no_haya_hooks_propios():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {})
        decision = decidir(raiz, salida_de_git("../principal/.git/hooks", "../principal/.git/worktrees/wt", "../principal/.git"))
        assert decision.puede is False
        assert decision.motivo == "la raíz es un worktree enlazado y --local cambiaría la config de todos sus checkouts"


def test_el_worktree_enlazado_se_decide_antes_que_los_hooks_propios():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {"pre-commit": b"x"})
        decision = decidir(raiz, salida_de_git(".git/hooks", ".git/worktrees/wt", ".git"))
        assert decision.puede is False and "worktree enlazado" in decision.motivo


def test_git_dir_y_git_common_dir_iguales_con_otra_escritura_no_son_un_worktree():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {})
        for comun in (".git", "./.git", ".git/", str((raiz / ".git").resolve()), (raiz / ".git").as_posix()):
            assert decidir(raiz, salida_de_git(".git/hooks", ".git", comun)).puede is True, comun


def enlazar_carpeta(destino, origen):
    try:
        os.symlink(origen, destino, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        return subprocess.run(["cmd", "/c", "mklink", "/J", str(destino), str(origen)], capture_output=True).returncode == 0
    return False


def test_el_git_dir_y_el_comun_escritos_distinto_pero_iguales_no_son_un_worktree():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {})
        if not enlazar_carpeta(raiz / "git-enlazado", raiz / ".git"):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert decidir(raiz, salida_de_git(".git/hooks", ".git", "git-enlazado")).puede is True
        if os.name == "nt":
            mayusculas = str(raiz / ".git").upper()
            assert decidir(raiz, salida_de_git(".git/hooks", ".git", mayusculas)).puede is True


def test_una_salida_que_no_son_tres_rutas_no_se_toca():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {})
        for salida in ("", "\n\n", ".git/hooks\n", ".git/hooks\n.git\n", ".git/hooks\n.git\n.git\nextra\n", None):
            decision = decidir(raiz, salida)
            assert decision.puede is False and decision.motivo == "git no dijo dónde están los hooks del repo", (salida, decision)


def test_la_salida_con_crlf_y_espacios_se_lee():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {"pre-commit": b"x"})
        decision = decidir(raiz, "  .git/hooks \r\n.git\r\n .git \r\n")
        assert decision.puede is False and "pre-commit" in decision.motivo


def test_una_carpeta_de_hooks_que_no_se_puede_leer_no_se_toca():
    with Temporal() as base:
        raiz = base / "r"
        (raiz / ".git").mkdir(parents=True)
        (raiz / ".git" / "hooks").write_bytes(b"soy un archivo")
        decision = decidir(raiz, salida_de_git(".git/hooks", ".git", ".git"))
        assert decision.puede is False and "no se puede leer la carpeta de hooks" in decision.motivo, decision


def test_la_decision_no_corre_git():
    with Temporal() as base:
        raiz = repo_con_hooks(base, {"pre-commit": b"x"})
        original = subprocess.run
        popen = subprocess.Popen

        def prohibido(*a, **k):
            raise AssertionError("corrió un proceso")

        subprocess.run, subprocess.Popen = prohibido, prohibido
        try:
            decidir(raiz, salida_de_git(".git/hooks", ".git", ".git"))
        finally:
            subprocess.run, subprocess.Popen = original, popen


def test_con_git_real_un_repo_recien_creado_se_puede_tocar_y_con_un_hook_ya_no():
    with Temporal() as base:
        raiz = base / "real"
        raiz.mkdir()
        git(raiz, "init", "-q")

        def preguntar():
            r = subprocess.run(["git", "-C", str(raiz), *m().COMANDO_RUTAS_DE_HOOKS], capture_output=True, check=True, env=_entorno_limpio())
            return decidir(raiz, r.stdout.decode("utf-8"))

        assert preguntar().puede is True
        (raiz / ".git" / "hooks" / "pre-commit").write_bytes(b"#!/bin/sh\nexit 0\n")
        assert preguntar().puede is False


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
