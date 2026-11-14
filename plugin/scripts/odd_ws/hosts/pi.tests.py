import contextlib
import importlib
import json
import ntpath
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent.parent
sys.path.insert(0, str(SCRIPTS))
PLUGIN = SCRIPTS.parent
SILENCIO = (0, "", b"")
CWD = os.path.abspath(os.path.join(os.sep, "w"))
EN_WINDOWS = "C:\\Proyecto"
EN_POSIX = "/home/u/mi_repo"
SIN_PANTALLA = ("Esta sesión de Pi no tiene pantalla para pedir confirmación, así que este comando queda bloqueado: si hace "
                "falta, pídele al usuario que lo corra él.")
CONFIG_MINIMA = {"schema_version": 1, "repos": {}, "layers": {"doc": {"extensions": [".x"]}}}
AGENTES = ("writer-sql", "revisor-sql", "revisor-diseno")
HERRAMIENTAS_DE_PI = {"read", "bash", "powershell", "edit", "write", "grep", "find", "ls"}
HERRAMIENTAS_ESPERADAS = {"writer-sql": ["read", "find", "grep", "edit", "write", "bash"], "revisor-sql": ["read", "find", "grep"],
                          "revisor-diseno": ["read", "find", "grep"]}
FRASES_DE_CLAUDE_CODE = ("Edit o Write", "con Read", "Read, Glob o Grep", "Tus herramientas son Read", "transcript",
                         "Tu contexto trae precargada", "el Glob o el Grep", "ya están en tu contexto", "por Bash",
                         ". Bash te sirve", "apply_patch", "herramienta de shell")
ESPACIOS_DE_JS = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f"
                  "\u205f\u3000\ufeff")
CLASE_DE_ESPACIOS_DE_JS = "[\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]"
PUNTO_DE_JS = "[^\\n\\r\\u2028\\u2029]"
FRONTMATTER_DE_GENTLE_PI = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)\Z")
ITEM_DE_GENTLE_PI = re.compile("^%s*-%s+(%s*)\\Z" % (CLASE_DE_ESPACIOS_DE_JS, CLASE_DE_ESPACIOS_DE_JS, PUNTO_DE_JS))
PAR_DE_GENTLE_PI = re.compile("^([A-Za-z0-9_-]+):%s*(%s*)\\Z" % (CLASE_DE_ESPACIOS_DE_JS, PUNTO_DE_JS))
NIVELES_DE_GENTLE_PI = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
MODOS_DE_GENTLE_PI = ("task", "background")


def m():
    return importlib.import_module("odd_ws.hosts.pi")


def ev():
    return importlib.import_module("odd_ws.eventos")


def cap():
    return importlib.import_module("odd_ws.capacidades")


def en(*partes):
    return os.path.join(CWD, *partes)


@contextlib.contextmanager
def sistema(nombre):
    previo = m().SISTEMA
    m().SISTEMA = nombre
    try:
        yield
    finally:
        m().SISTEMA = previo


def ctx(**cambios):
    datos = {"cwd": CWD, "sessionId": "s1", "hasUI": False, "mode": "rpc"}
    datos.update(cambios)
    return datos


def odd_ws(**cambios):
    datos = {"agent": None, "agentId": None, "lastAssistantMessage": "", "continued": False}
    datos.update(cambios)
    return datos


def payload(tipo, **extra):
    datos = {"type": tipo, "ctx": ctx(), "oddWs": odd_ws()}
    datos.update(extra)
    return datos


def llamada(herramienta, entrada, **extra):
    return payload("tool_call", toolName=herramienta, input=entrada, **extra)


def resultado(herramienta, entrada, **extra):
    datos = {"isError": False}
    datos.update(extra)
    return payload("tool_result", toolName=herramienta, input=entrada, **datos)


def inicio(razon, tipo="session_start"):
    return payload(tipo, reason=razon)


def cierre(**cambios):
    datos = {"agent": "writer-x", "agentId": "a1", "lastAssistantMessage": "Listo."}
    datos.update(cambios)
    return payload("agent_before_settle", oddWs=odd_ws(**datos))


def herramienta(**sobre):
    campos = {"fase": "pre", "tipo": "otra", "herramienta": None, "rutas": (), "comando": None, "dialecto": None,
              "agente": None, "id_agente": None, "sesion": "s1", "cwd": CWD}
    campos.update(sobre)
    return ev().Herramienta(**campos)


def atendido(crudo, decision=None, pre_por_defecto=False):
    vistos = []

    def nucleo(evento):
        vistos.append(evento)
        return ev().Permitir() if decision is None else decision

    entrada = json.dumps(crudo).encode("utf-8")
    salida = m().atender(entrada, nucleo, pre_por_defecto)
    assert len(vistos) <= 1, vistos
    return salida, (vistos[0] if vistos else None)


def visto(crudo, pre_por_defecto=False):
    salida, evento = atendido(crudo, pre_por_defecto=pre_por_defecto)
    assert salida == SILENCIO, "permitir es silencio con exit 0: %r" % (salida,)
    return evento


def rutas_de(ruta, cwd=CWD):
    return visto(llamada("edit", {"path": ruta, "edits": []}, ctx=ctx(cwd=cwd))).rutas


def accion(nombre, texto):
    return 0, json.dumps({"accion": nombre, "texto": texto}), b""


def recortar_como_js(texto):
    return texto.strip(ESPACIOS_DE_JS)


def sin_comillas_como_gentle_pi(valor):
    recortado = recortar_como_js(valor)
    entre = (recortado.startswith('"') and recortado.endswith('"')) or (recortado.startswith("'") and recortado.endswith("'"))
    return recortado[1:-1] if entre and len(recortado) >= 2 else recortado


def frontmatter_de_gentle_pi(texto):
    encontrado = FRONTMATTER_DE_GENTLE_PI.match(texto)
    if encontrado is None:
        return {}, recortar_como_js(texto)
    datos, lista = {}, None
    for crudo in re.split(r"\r?\n", encontrado.group(1)):
        item = ITEM_DE_GENTLE_PI.match(crudo)
        if item and lista is not None:
            datos[lista].append(sin_comillas_como_gentle_pi(item.group(1)))
            continue
        par = PAR_DE_GENTLE_PI.match(crudo)
        if par is None:
            continue
        clave, valor = par.groups()
        recortado = recortar_como_js(valor)
        if not recortado:
            datos[clave], lista = [], clave
            continue
        lista = None
        if recortado.startswith("[") and recortado.endswith("]"):
            datos[clave] = [parte for parte in map(sin_comillas_como_gentle_pi, recortado[1:-1].split(",")) if parte]
        else:
            datos[clave] = sin_comillas_como_gentle_pi(recortado)
    return datos, recortar_como_js(encontrado.group(2))


def escalar_de_gentle_pi(valor):
    return valor if isinstance(valor, str) else None


def nivel_de_gentle_pi(valor, opciones, clave):
    if valor is None:
        return None, None
    normal = recortar_como_js(valor).lower()
    return (normal, None) if normal in opciones else (None, '%s "%s" is not one of %s' % (clave, valor, ", ".join(opciones)))


def cargar_en_gentle_pi(texto, archivo):
    datos, cuerpo = frontmatter_de_gentle_pi(texto)

    def primero(*claves):
        return next((valor for valor in (escalar_de_gentle_pi(datos.get(clave)) for clave in claves) if valor is not None), None)

    pensar, error = nivel_de_gentle_pi(primero("thinking", "effort", "thinking_level"), NIVELES_DE_GENTLE_PI, "thinking")
    if error:
        return {"error": error}
    modo, error = nivel_de_gentle_pi(primero("subagent_mode", "mode"), MODOS_DE_GENTLE_PI, "mode")
    if error:
        return {"error": error}
    if not cuerpo:
        return {"error": "no instructions after the frontmatter"}
    modelo = escalar_de_gentle_pi(datos.get("model"))
    herramientas = datos.get("tools")
    if herramientas is not None and not isinstance(herramientas, list):
        herramientas = herramientas.split(",")
    return {
        "name": recortar_como_js(escalar_de_gentle_pi(datos.get("name")) or "") or re.sub(r"\.md\Z", "", archivo, flags=re.IGNORECASE),
        "description": recortar_como_js(escalar_de_gentle_pi(datos.get("description")) or ""),
        "instructions": cuerpo,
        "model": (recortar_como_js(modelo) or None) if modelo is not None else None,
        "thinking": pensar,
        "mode": modo,
        "tools": [h for h in map(recortar_como_js, herramientas or []) if h],
        "claves": sorted(datos),
    }


def armado_para_pi(nombre, actual=None):
    return importlib.import_module("bootstrap_agentes").armar(nombre, actual, "pi")


def agente_de_pi(nombre, actual=None):
    return importlib.import_module("plantilla_writer").agente(armado_para_pi(nombre, actual))


def nombradas_en(texto):
    return set(re.findall(r"`([a-z]+)`", texto)) & HERRAMIENTAS_DE_PI


def con_identidad(nombre, descripcion, identidad):
    texto = armado_para_pi(nombre)
    texto = re.sub(r"(?m)^description:.*$", lambda _m: "description: " + json.dumps(descripcion, ensure_ascii=False), texto, count=1)
    texto = re.sub(r"(<!-- instancia:identidad -->\n).*?(<!-- /instancia:identidad -->)", lambda e: e.group(1) + identidad + e.group(2),
                   texto, count=1, flags=re.S)
    return agente_de_pi(nombre, texto)


def test_edit_y_write_son_edicion_con_su_ruta_contra_el_cwd():
    for nombre, entrada in (("edit", {"path": "src/a.sql", "edits": [{"oldText": "a", "newText": "b"}]}),
                            ("write", {"path": "src/a.sql", "content": "x"})):
        salida, leido = atendido(llamada(nombre, entrada))
        assert salida == SILENCIO, (nombre, salida)
        assert leido == herramienta(tipo="edicion", herramienta=nombre, rutas=(en("src", "a.sql"),)), leido


def test_la_ruta_se_resuelve_como_la_resuelve_pi():
    casa = os.path.expanduser("~")
    absoluta = os.path.abspath(os.path.join(os.sep, "otra", "x.sql"))
    casos = (
        ("@src/a.sql", en("src", "a.sql")),
        ("~/x.sql", os.path.normpath(os.path.join(casa, "x.sql"))),
        ("@~/x.sql", os.path.normpath(os.path.join(casa, "x.sql"))),
        ("~", os.path.normpath(casa)),
        ("~x/a.sql", en("~x", "a.sql")),
        ("@@a.sql", en("@a.sql")),
        ("a/../b/./c.sql", en("b", "c.sql")),
        ("mi\u00a0archivo\u3000.sql", en("mi archivo .sql")),
        ("@", CWD),
        (absoluta, absoluta),
        ("@" + absoluta, absoluta),
    )
    for crudo, esperado in casos:
        assert rutas_de(crudo) == (esperado,), (crudo, rutas_de(crudo), esperado)


def test_sin_cwd_la_relativa_queda_sin_resolver():
    for raro in (None, 7, ""):
        assert rutas_de("@src/a.sql", cwd=raro) == ("src/a.sql",), raro


def test_en_windows_las_rutas_de_git_bash_y_la_tilde_con_barra_invertida_son_las_de_pi():
    casa = os.path.expanduser("~")
    with sistema("nt"):
        for crudo, esperado in (("/c/Proyecto/a.sql", "C:\\Proyecto\\a.sql"), ("/mnt/d/x/y.sql", "D:\\x\\y.sql"),
                                ("/cygdrive/e/z.sql", "E:\\z.sql"), ("/MNT/c/a.sql", "C:\\a.sql"), ("/c", "C:\\"),
                                ("@/c/a.sql", "C:\\a.sql"), ("//servidor/x/a.sql", "\\\\servidor\\x\\a.sql"),
                                ("/cc/a.sql", "C:\\cc\\a.sql"), ("/c/x\\a.sql", "C:\\c\\x\\a.sql"), ("src/a.sql", "C:\\Proyecto\\src\\a.sql"),
                                ("D:/otra/a.sql", "D:\\otra\\a.sql"), ("~\\x.sql", ntpath.normpath(ntpath.join(EN_WINDOWS, casa, "x.sql")))):
            assert rutas_de(crudo, cwd=EN_WINDOWS) == (esperado,), (crudo, rutas_de(crudo, cwd=EN_WINDOWS), esperado)
        assert rutas_de("a.sql", cwd="/c/Proyecto") == ("C:\\Proyecto\\a.sql",), "el cwd también pasa por la regla de Pi"
    with sistema("posix"):
        assert rutas_de("/c/Proyecto/a.sql", cwd=EN_POSIX) == ("/c/Proyecto/a.sql",), "fuera de Windows /c/ es una carpeta"
        assert rutas_de("~\\x.sql", cwd=EN_POSIX) == (posixpath.join(EN_POSIX, "~\\x.sql"),), "y ~\\ no es la casa"
        for doble in ("//home/u/a.sql", "///home/u/a.sql", "@//home/u/a.sql"):
            assert rutas_de(doble, cwd=EN_POSIX) == ("/home/u/a.sql",), (doble, "path.resolve de POSIX deja una sola barra")


def test_una_url_file_es_la_ruta_que_nombra():
    with sistema("posix"):
        for crudo, esperado in (("file:///home/u/mi_repo/a%20b.sql", "/home/u/mi_repo/a b.sql"),
                                ("file://localhost/home/u/x.sql", "/home/u/x.sql"), ("@file:///tmp/../home/y.sql", "/home/y.sql")):
            assert rutas_de(crudo, cwd=EN_POSIX) == (esperado,), (crudo, rutas_de(crudo, cwd=EN_POSIX))
        assert rutas_de("FILE:///home/u/x.sql", cwd=EN_POSIX) == ("/home/u/mi_repo/FILE:/home/u/x.sql",), "solo file:// en minúsculas"
    with sistema("nt"):
        for crudo, esperado in (("file:///C:/Proyecto/a%20b.sql", "C:\\Proyecto\\a b.sql"), ("file://servidor/x/a.sql", "\\\\servidor\\x\\a.sql"),
                                ("file://C:/x.sql", "C:\\x.sql"), ("file:///D|/x.sql", "D:\\x.sql")):
            assert rutas_de(crudo, cwd=EN_WINDOWS) == (esperado,), (crudo, rutas_de(crudo, cwd=EN_WINDOWS))


def test_una_url_file_se_limpia_como_whatwg_antes_de_resolverla():
    with sistema("posix"):
        for crudo in ("file:///home/u/mi_repo/a.sql\x01", "file:///home/u/mi_repo/a.sql\x1f", "file:///home/u/mi_repo/a.sql\x00",
                      "file:///home/u/mi_repo/a.sql ", "file:///home/u/mi_repo/a.sql \x01 ", "file:///home/u/mi\t_repo/a.sql",
                      "file:///home/u/\nmi_repo/a.s\rql", "@file:///home/u/mi_repo/a.sql\x01"):
            assert rutas_de(crudo, cwd=EN_POSIX) == ("/home/u/mi_repo/a.sql",), (crudo, rutas_de(crudo, cwd=EN_POSIX))
        assert rutas_de("file:///repo\\.claude\\x.sql", cwd=EN_POSIX) == ("/repo/.claude/x.sql",), "en file, \\ es /"
        assert rutas_de("file:///home/u/a\x01b.sql", cwd=EN_POSIX) == ("/home/u/a\x01b.sql",), "un control del medio queda"
        assert rutas_de("nota.sql ", cwd=EN_POSIX) == ("/home/u/mi_repo/nota.sql ",), "fuera de una URL no se limpia nada"
        assert rutas_de("/x\\y.sql\x01", cwd=EN_POSIX) == ("/x\\y.sql\x01",), "ni la \\ ni los controles"
    with sistema("nt"):
        for crudo, esperado in (("file:///C:/Proyecto/a.sql\x01", "C:\\Proyecto\\a.sql"), ("file:///C:/Proyecto/a.sql ", "C:\\Proyecto\\a.sql"),
                                ("file:///C:\\Proyecto\\b.sql", "C:\\Proyecto\\b.sql"), ("file://servidor\\x\\a.sql", "\\\\servidor\\x\\a.sql"),
                                ("file:///C:/Pro\tyecto/a.sql\x1f", "C:\\Proyecto\\a.sql")):
            assert rutas_de(crudo, cwd=EN_WINDOWS) == (esperado,), (crudo, rutas_de(crudo, cwd=EN_WINDOWS))
        assert rutas_de("a.sql ", cwd=EN_WINDOWS) == ("C:\\Proyecto\\a.sql ",), "fuera de una URL no se limpia nada"


def test_read_es_lectura_y_grep_find_y_ls_son_otra_como_glob_y_grep_en_claude_code():
    assert visto(resultado("read", {"path": "@src/a.sql", "offset": 1, "limit": 5})) == herramienta(
        fase="post", tipo="lectura", herramienta="read", rutas=(en("src", "a.sql"),))
    assert visto(llamada("read", {"path": "a.sql"})).tipo == "lectura"
    for nombre, entrada in (("grep", {"pattern": "x", "path": "src"}), ("find", {"pattern": "*.sql", "path": "src"}),
                            ("ls", {"path": "src"}), ("Read", {"path": "a.sql"}), ("Edit", {"path": "a.sql"}), ("Bash", {"command": "ls"}),
                            ("subagent_run", {"agent": "writer-x", "command": "ls"}), ("mcp__srv__run", {"command": "git push --force"}),
                            (None, {"command": "ls"}), (7, {"path": "a.sql"})):
        leido = visto(llamada(nombre, entrada))
        assert (leido.tipo, leido.rutas, leido.comando, leido.dialecto) == ("otra", (), None, None), (nombre, leido)
        assert leido.herramienta == (nombre if isinstance(nombre, str) else None), nombre


def test_bash_es_posix_en_todas_las_plataformas_y_powershell_es_powershell():
    for nombre in ("nt", "posix"):
        with sistema(nombre):
            assert visto(llamada("bash", {"command": "ls -la", "timeout": 5})) == herramienta(
                tipo="shell", herramienta="bash", comando="ls -la", dialecto="posix"), nombre
            assert visto(llamada("powershell", {"command": "Get-ChildItem"})) == herramienta(
                tipo="shell", herramienta="powershell", comando="Get-ChildItem", dialecto="powershell"), nombre


def test_tool_call_es_pre_y_tool_result_es_post():
    assert visto(llamada("bash", {"command": "ls"})).fase == "pre"
    assert visto(resultado("bash", {"command": "ls"}, isError=True)) == herramienta(
        fase="post", tipo="shell", herramienta="bash", comando="ls", dialecto="posix")
    assert visto(resultado("write", {"path": "a.sql", "content": "x"})) == herramienta(
        fase="post", tipo="edicion", herramienta="write", rutas=(en("a.sql"),))


def test_entradas_malformadas_quedan_vacias():
    for entrada in (None, "texto", [1], 7, {}, {"path": 7}, {"path": None}, {"path": ["a.sql"]}, {"command": 7}, {"command": None}):
        assert (visto(llamada("edit", entrada)).tipo, visto(llamada("edit", entrada)).rutas) == ("edicion", ()), entrada
        assert (visto(llamada("bash", entrada)).tipo, visto(llamada("bash", entrada)).comando) == ("shell", None), entrada
    assert visto(llamada("edit", {"path": ""})).rutas == (), "una ruta vacía no es una ruta"
    assert visto(llamada("bash", {"command": ""})).comando == "", "el núcleo decide qué es un comando vacío"
    assert visto(llamada("edit", {"path": "a.sql", "command": "ls"})).comando is None, "una edición no trae comando"


def test_la_identidad_sale_de_odd_ws_y_la_sesion_y_el_cwd_del_ctx():
    principal = visto(llamada("bash", {"command": "ls"}))
    assert (principal.agente, principal.id_agente, principal.sesion, principal.cwd) == (None, None, "s1", CWD)
    writer = visto(llamada("bash", {"command": "ls"}, oddWs=odd_ws(agent="writer-x", agentId="a1")))
    assert (writer.agente, writer.id_agente) == ("writer-x", "a1")
    crudo = visto(llamada("bash", {"command": "ls"}, oddWs=odd_ws(agent=7, agentId=5), ctx=ctx(sessionId=["s"])))
    assert (crudo.agente, crudo.id_agente, crudo.sesion) == (7, 5, ["s"]), "la identidad la valida el núcleo"
    for raro in (None, "writer-x", [1]):
        sin = visto(llamada("bash", {"command": "ls"}, oddWs=raro, ctx=raro))
        assert (sin.agente, sin.id_agente, sin.sesion, sin.cwd) == (None, None, None, None), raro


def test_session_start_y_session_compact_pasan_al_origen_que_usa_verificar_capa():
    E = ev()
    for razon, origen in (("startup", "startup"), ("resume", "resume"), ("new", "clear"), ("reload", "resume"), ("fork", "fork")):
        assert visto(inicio(razon)) == E.InicioSesion(origen=origen, sesion="s1", cwd=CWD), razon
    for razon in ("manual", "threshold", "overflow", None, "otra"):
        assert visto(inicio(razon, "session_compact")) == E.InicioSesion(origen="compact", sesion="s1", cwd=CWD), razon
    for raro in ("otra", "clear", "compact", 7, None):
        assert visto(inicio(raro)).origen == raro, raro
    assert visto({"type": "session_start"}) == E.InicioSesion()


def test_agent_before_settle_es_el_fin_del_subagente_con_lo_que_trae_odd_ws():
    E = ev()
    esperado = E.FinSubagente(agente="writer-x", id_agente="a1", sesion="s1", cwd=CWD, transcript=None,
                              ultimo_mensaje="Listo.", ya_reintentado=False)
    assert visto(cierre()) == esperado
    assert visto(cierre(continued=True)) == E.FinSubagente(**dict(vars(esperado), ya_reintentado=True))
    for casi in ("true", 1, [True], None, False):
        assert visto(cierre(continued=casi)).ya_reintentado is False, casi
    assert visto({"type": "agent_before_settle"}) == E.FinSubagente()


def test_lo_que_no_es_un_evento_calla_sin_correr_el_nucleo():
    bash = llamada("bash", {"command": "ls"})
    for no_es in (None, 5, "texto", [], [bash]):
        assert atendido(no_es) == (SILENCIO, None), no_es
    for tipo in ("tool_execution_start", "before_agent_start", "agent_settled", "subagent_run", "session_shutdown",
                 "PreToolUse", "TOOL_CALL", "", None, 5):
        assert atendido(dict(bash, type=tipo), ev().Bloquear("no")) == (SILENCIO, None), tipo
    sin = {clave: valor for clave, valor in bash.items() if clave != "type"}
    assert atendido(sin, ev().Bloquear("no")) == (SILENCIO, None)
    assert atendido(sin, ev().Bloquear("no"), pre_por_defecto=True) == atendido(bash, ev().Bloquear("no"))
    assert atendido(dict(bash, type=None), ev().Bloquear("no"), pre_por_defecto=True) == (SILENCIO, None), "solo la clave ausente"


def test_cargar_y_atender_son_los_compartidos():
    base = importlib.import_module("odd_ws.hosts.base")
    assert m().cargar is base.cargar
    for roto in (b"no es json", b"", b"\xff\xfe"):
        try:
            m().atender(roto, lambda evento: ev().Bloquear("no"))
        except ValueError:
            continue
        raise AssertionError("atendió %r" % (roto,))


def test_bloquear_sale_como_accion_con_exit_0_en_pre_y_en_post():
    E = ev()
    for crudo in (llamada("bash", {"command": "ls"}), llamada("powershell", {"command": "ls"}), llamada("edit", {"path": "a.sql"}),
                  llamada("write", {"path": "a.sql"}), resultado("edit", {"path": "a.sql"}), resultado("read", {"path": "a.sql"})):
        assert atendido(crudo, E.Bloquear("guard bloqueó: ñ"))[0] == (
            0, '{"accion": "bloquear", "texto": "guard bloque\\u00f3: \\u00f1"}', b""), crudo


def test_preguntar_con_pantalla_sale_como_preguntar_para_que_el_shim_confirme():
    E = ev()
    for modo in ("tui", "rpc", None):
        crudo = llamada("bash", {"command": "git commit -m x"}, ctx=ctx(hasUI=True, mode=modo))
        assert atendido(crudo, E.Preguntar("¿correr git commit?"))[0] == accion("preguntar", "¿correr git commit?"), modo


def test_sin_pantalla_preguntar_se_degrada_a_bloquear_con_el_pedido_al_usuario():
    E = ev()
    degradado = accion("bloquear", "¿correr git commit?\n" + SIN_PANTALLA)
    for valor in (False, None, "true", 1, [True], {}):
        crudo = llamada("bash", {"command": "git commit -m x"}, ctx=ctx(hasUI=valor))
        assert atendido(crudo, E.Preguntar("¿correr git commit?"))[0] == degradado, valor
    sin_clave = llamada("bash", {"command": "git commit -m x"}, ctx={"cwd": CWD, "sessionId": "s1", "mode": "tui"})
    assert atendido(sin_clave, E.Preguntar("¿correr git commit?"))[0] == degradado
    for raro in (None, "tui", [True]):
        assert atendido(llamada("bash", {"command": "ls"}, ctx=raro), E.Preguntar("¿correr git commit?"))[0] == degradado, raro
    assert atendido(llamada("edit", {"path": "a.sql"}), E.Preguntar("x"))[0] == accion("bloquear", "x\n" + SIN_PANTALLA)


def test_contexto_en_post_y_al_iniciar_y_seguir_al_cerrar_un_subagente():
    E = ev()
    assert atendido(resultado("edit", {"path": "a.sql"}), E.Contexto("línea 1\nlínea 2"))[0] == accion("contexto", "línea 1\nlínea 2")
    assert atendido(resultado("read", {"path": "a.sql"}), E.Contexto("reglas"))[0] == accion("contexto", "reglas")
    for crudo in (inicio("startup"), inicio("reload"), inicio("manual", "session_compact")):
        assert atendido(crudo, E.Contexto("config rota (ñ)"))[0] == (
            0, '{"accion": "contexto", "texto": "config rota (\\u00f1)"}', b""), crudo
    assert atendido(cierre(), E.Seguir("todavía no"))[0] == (0, '{"accion": "seguir", "texto": "todav\\u00eda no"}', b"")


def test_lo_que_el_protocolo_no_tiene_calla():
    E = ev()
    con_pantalla = ctx(hasUI=True)
    casos = (
        (llamada("bash", {"command": "ls"}), (E.Permitir(), E.Contexto("x"), E.Seguir("x"), None, "bloquear")),
        (resultado("edit", {"path": "a.sql"}), (E.Permitir(), E.Preguntar("x"), E.Seguir("x"))),
        (resultado("edit", {"path": "a.sql"}, ctx=con_pantalla), (E.Preguntar("x"),)),
        (inicio("startup"), (E.Permitir(), E.Bloquear("x"), E.Preguntar("x"), E.Seguir("x"))),
        (cierre(), (E.Permitir(), E.Bloquear("x"), E.Preguntar("x"), E.Contexto("x"), None, "seguir")),
    )
    for crudo, decisiones in casos:
        for decision in decisiones:
            assert atendido(crudo, decision)[0] == SILENCIO, (crudo["type"], decision)


def test_un_texto_con_surrogates_sueltos_sale_limpio_y_en_ascii():
    E = ev()
    con_pantalla = llamada("bash", {"command": "ls"}, ctx=ctx(hasUI=True))
    casos = ((llamada("bash", {"command": "ls"}), E.Bloquear("temporal C:\\t\ud800"), "bloquear", "temporal C:\\t?"),
             (resultado("write", {"path": "a.sql"}), E.Bloquear("a\ud800b\udfffc"), "bloquear", "a?b?c"),
             (resultado("read", {"path": "a.sql"}), E.Contexto("x\udfff"), "contexto", "x?"),
             (inicio("startup"), E.Contexto("\udcff solo"), "contexto", "? solo"),
             (cierre(), E.Seguir("x\ud800"), "seguir", "x?"),
             (con_pantalla, E.Preguntar("x\ud800"), "preguntar", "x?"),
             (llamada("bash", {"command": "ls"}), E.Preguntar("x\ud800"), "bloquear", "x?\n" + SIN_PANTALLA))
    for crudo, decision, nombre, texto in casos:
        codigo, salida, error = atendido(crudo, decision)[0]
        assert (codigo, error) == (0, b""), (decision, codigo, error)
        salida.encode("ascii")
        assert json.loads(salida) == {"accion": nombre, "texto": texto}, (decision, salida)
        json.dumps(json.loads(salida), ensure_ascii=False).encode("utf-8")


def test_en_pi_nada_sale_con_exit_distinto_de_0_ni_por_stderr():
    E = ev()
    eventos = (llamada("bash", {"command": "ls"}), llamada("bash", {"command": "ls"}, ctx=ctx(hasUI=True)), llamada("edit", {"path": "a"}),
               resultado("write", {"path": "a"}), resultado("read", {"path": "a"}), inicio("startup"), inicio("x", "session_compact"),
               cierre())
    for crudo in eventos:
        for decision in (E.Permitir(), E.Bloquear("x ñ"), E.Preguntar("x ñ"), E.Contexto("x ñ"), E.Seguir("x ñ"),
                         E.Bloquear("x\ud800"), E.Contexto("x\ud800"), E.Seguir("x\udfff")):
            codigo, salida, error = atendido(crudo, decision)[0]
            assert (codigo, error) == (0, b""), (crudo["type"], decision, codigo, error)
            if salida:
                datos = json.loads(salida)
                assert set(datos) == {"accion", "texto"} and datos["accion"] in ("bloquear", "preguntar", "contexto", "seguir"), datos


def test_el_registro_suma_pi_sin_mover_a_claude_code_ni_a_codex():
    hosts = importlib.import_module("odd_ws.hosts")
    assert hosts.ADAPTADORES == ("claude_code", "codex", "pi")
    assert hosts.NOMBRES == {"claude-code": "claude_code", "codex": "codex", "pi": "pi"}
    assert hosts.adaptador("pi") is m()
    assert hosts.adaptador("claude-code") is importlib.import_module("odd_ws.hosts.claude_code")
    assert hosts.adaptador("codex") is importlib.import_module("odd_ws.hosts.codex")
    for desconocido in ("Pi", "PI", "pi ", "gentle-shell", "gentle-pi", "", None, ["pi"]):
        assert hosts.adaptador(desconocido) is None, desconocido
    assert m().BITACORA is True and hosts.necesita_bitacora("pi") is True
    assert m().PRECARGA_SKILLS is False


def test_un_host_conocido_atiende_un_payload_de_pi_por_el_registro():
    hosts = importlib.import_module("odd_ws.hosts")
    crudo = json.dumps(llamada("bash", {"command": "ls"})).encode("utf-8")
    assert hosts.atender("pi", crudo, lambda evento: ev().Bloquear("no")) == accion("bloquear", "no")
    assert hosts.atender("pi", crudo, lambda evento: ev().Permitir()) == SILENCIO


@contextlib.contextmanager
def temporal():
    base = Path(tempfile.mkdtemp(prefix="pi-test-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_los_archivos_y_los_comandos_del_writer_salen_de_la_bitacora():
    comun = importlib.import_module("odd_ws.comun")
    with temporal() as base:
        carpeta = base / "a1.fotos"
        carpeta.mkdir()
        a, b = str(base / "a.sql"), str(base / "b.sql")
        for registro in ({"tipo": "edicion", "rutas": [a, b]}, {"tipo": "shell", "comando": "ls", "dialecto": "posix"}):
            comun.anotar_en_bitacora(str(carpeta), registro)
        e = visto(cierre())
        assert m().archivos_del_writer(e, str(carpeta)) == ([a, b], [])
        assert m().comandos_del_writer(e, str(carpeta)) == [("posix", "ls")]
        assert m().archivos_del_writer(e, str(base / "otra.fotos")) == ([], [])
        assert m().comandos_del_writer(e, str(base / "otra.fotos")) is None


def test_las_degradaciones_estan_declaradas_y_preguntar_solo_se_degrada_sin_pantalla():
    E, C = ev(), cap()
    assert m().EXPRESABLES == {C.PRE: (E.Bloquear, E.Preguntar), C.POST: (E.Bloquear, E.Contexto), C.INICIO: (E.Contexto,),
                               C.FIN_SUBAGENTE: (E.Seguir,)}
    assert m().DEGRADACIONES == {C.PRE: {E.Preguntar: E.Bloquear}}
    estado, nota = m().MANIFIESTO["P3"]
    assert estado == C.DEGRADADO and "hasUI" in nota and "ctx.ui.confirm" in nota and "Git Bash" in nota, nota
    crudo = llamada("bash", {"command": "ls"})
    bloqueo = atendido(crudo, E.Bloquear("x"))[0]
    assert atendido(crudo, E.Preguntar("x"))[0][0] == bloqueo[0] and json.loads(atendido(crudo, E.Preguntar("x"))[0][1])["accion"] == "bloquear"
    con_pantalla = dict(crudo, ctx=ctx(hasUI=True))
    assert json.loads(atendido(con_pantalla, E.Preguntar("x"))[0][1])["accion"] == "preguntar"


def test_el_manifiesto_dice_lo_que_falta_y_la_tarea_que_lo_trae():
    C = cap()
    estados = {clave: estado for clave, (estado, _) in m().MANIFIESTO.items()}
    assert estados == {"P1": C.SOPORTADO, "P2": C.SOPORTADO, "P3": C.DEGRADADO, "P4": C.SOPORTADO, "P5": C.DEGRADADO,
                       "P6": C.DEGRADADO, "P7": C.DEGRADADO, "P8": C.NO_DISPONIBLE, "P9": C.NO_DISPONIBLE,
                       "P10": C.DEGRADADO}, estados
    for clave, tareas in (("P5", ("F2g",)), ("P8", ("F2f",)), ("P9", ("F2f", "F2b"))):
        nota = m().MANIFIESTO[clave][1]
        assert all(tarea in nota for tarea in tareas), (clave, nota)
    for clave in ("P7", "P8"):
        assert "F2d" not in m().MANIFIESTO[clave][1], "F2d ya no es lo que falta: %r" % (m().MANIFIESTO[clave],)
    assert "new es clear" in m().MANIFIESTO["P1"][1] and "reload es resume" in m().MANIFIESTO["P1"][1], m().MANIFIESTO["P1"]
    assert "@" in m().MANIFIESTO["P2"][1] and "~" in m().MANIFIESTO["P2"][1], m().MANIFIESTO["P2"]
    assert "read" in m().MANIFIESTO["P4"][1], m().MANIFIESTO["P4"]
    assert "CLAUDE.md" in m().MANIFIESTO["P10"][1] and "AGENTS.md" in m().MANIFIESTO["P10"][1], m().MANIFIESTO["P10"]


def test_p7_dice_el_mecanismo_de_los_agentes_de_pi_y_su_fallback_y_p8_las_skills_de_la_instancia():
    p7, p8 = m().MANIFIESTO["P7"][1], m().MANIFIESTO["P8"][1]
    for frase in (".pi/agents", ".claude/agents", "hosts", "gentle-shell", "--tools", "Read a read", "Glob a find", "Grep a grep",
                  "Edit a edit", "Write a write", "Bash a bash", "sin skills precargadas", "raíz de la instancia", "no sube",
                  "subagents.json", "Pi a secas"):
        assert frase in p7, (frase, p7)
    for frase in ("resources_discover", ".claude/skills", "workspace.config.json", "description", "F2f", "disable-model-invocation"):
        assert frase in p8, (frase, p8)


def test_p5_y_p6_dicen_el_rodeo_de_gentle_shell_y_que_con_pi_a_secas_el_writer_queda_sin_compuerta():
    p5, p6 = m().MANIFIESTO["P5"][1], m().MANIFIESTO["P6"][1]
    for frase in ("gentle-shell", "agent_before_settle", "hijo", "writer_stop", "continue", "sin probar", "F2g", "Pi a secas",
                  "sin compuerta", "SubagentStop"):
        assert frase in p5, (frase, p5)
    for frase in ("Pi", "gentle-shell", "subagent_run", "marca", "GENTLE_PI_AGENTS_CHILD", "id de sesión", "Pi a secas",
                  "el rodeo se borra"):
        assert frase in p6, (frase, p6)
    assert "F2c" not in p5 + p6, "F2c ya no es lo que falta"


def test_los_textos_de_pi_describen_su_realidad():
    juntos = "\n".join(m().TEXTOS.values())
    for frase in ("`edit` o `write`", "`bash` (en Windows corre Git Bash)", "por `bash`", "bitácora", "con `read`", "SKILL.md",
                  "no vienen precargadas"):
        assert frase in juntos, frase
    for frase in ("Edit o Write", "con Read", "transcript", "Tu contexto trae precargada", "apply_patch", "PowerShell",
                  "herramienta de shell"):
        assert frase not in juntos, frase
    assert set(m().TEXTOS) == set(importlib.import_module("odd_ws.hosts.codex").TEXTOS)


def test_la_memoria_de_claude_code_no_esta_disponible_en_pi_y_su_nota_lo_dice():
    estado, nota = m().MEMORIAS
    assert estado == cap().NO_DISPONIBLE, m().MEMORIAS
    assert "Claude Code" in nota and "Pi" in nota and "supuesto" in nota, nota
    assert not hasattr(m(), "directorio_de_memorias"), "un puerto no disponible no resuelve nada"


def nucleo_del_doctor():
    return importlib.import_module("doctor").NUCLEO


def contexto_del_doctor(base, windows=False):
    def ejecutar(args):
        raise AssertionError("el doctor de Pi todavía no corre nada: %r" % (args,))

    return types.SimpleNamespace(plugin=PLUGIN, home=base / "home", entorno={}, windows=windows, which=lambda nombre: None,
                                 ejecutar=ejecutar)


def test_los_puertos_del_doctor_dicen_lo_que_falta_y_no_fingen_un_ok():
    nucleo = nucleo_del_doctor()
    with temporal() as base:
        ctx_ = contexto_del_doctor(base)
        version, instalado = m().version(ctx_, nucleo)
        assert (version.id, version.estado, instalado) == ("pi", nucleo.AVISO, False), version
        assert "F2e" in version.detalle and "no se revisa" in version.detalle, version
        for cli in (nucleo.CLI_INSTALADO, nucleo.CLI_AUSENTE, nucleo.CLI_DE_OTRO_HOST):
            con_raiz = m().chequeos(ctx_, base, nucleo, cli)
            assert [(r.id, r.estado) for r in con_raiz] == [("pi-agentes", nucleo.AVISO)], con_raiz
            assert "llega en F2e" in con_raiz[0].detalle and "desde F2d" in con_raiz[0].detalle, con_raiz
            assert ".pi/agents" in con_raiz[0].detalle and "el bootstrap genera" in con_raiz[0].detalle, con_raiz
            assert m().chequeos(ctx_, None, nucleo, cli) == [], "fuera de una instancia no hay agentes que revisar"
        assert (m().PYTHON, m().PYTHON_EN_WINDOWS) == ("python3", "python")


HOOKS_DE_PI = [("session_start[0][0]", "verificar_capa", "8"), ("session_compact[0][0]", "verificar_capa", "8"),
               ("tool_call[0][0]", "verificar_capa", "8"), ("tool_call[1][0]", "writer_guard", "8"),
               ("tool_call[2][0]", "guard_comandos", "8"), ("tool_result[0][0]", "verificar_capa", "25"),
               ("tool_result[1][0]", "verificar_capa", "8"), ("agent_before_settle[0][0]", "writer_stop", "50")]


def test_hooks_registrados_lee_hooks_pi_json_con_el_python_que_lanza_el_shim_en_cada_sistema():
    with temporal() as base:
        for windows, python in ((False, "python3"), (True, "python")):
            ctx_ = contexto_del_doctor(base, windows)
            registrados = list(m().hooks_registrados(ctx_, None))
            assert registrados == list(m().hooks_registrados(ctx_, base)), "la instancia no suma hooks de Pi"
            esperados = [("hooks/hooks.pi.json " + origen, [python, str(PLUGIN / "scripts" / (script + ".py")), "--plazo", plazo,
                                                           "--host", "pi"], True) for origen, script, plazo in HOOKS_DE_PI]
            assert registrados == esperados, (windows, registrados)


def test_hooks_registrados_no_finge_un_ok_con_hooks_pi_json_ausente_o_roto():
    original = json.loads((PLUGIN / "hooks" / "hooks.pi.json").read_text(encoding="utf-8"))
    with temporal() as base:
        ctx_ = contexto_del_doctor(base)
        ctx_.plugin = base / "plugin"
        archivo = ctx_.plugin / "hooks" / "hooks.pi.json"
        archivo.parent.mkdir(parents=True)
        assert list(m().hooks_registrados(ctx_, None)) == [("hooks/hooks.pi.json", None, True)], "sin el archivo"
        for roto in ("{no es json", "[]", json.dumps(dict(original, python=7)), json.dumps({k: v for k, v in original.items() if k != "python"})):
            archivo.write_text(roto, encoding="utf-8")
            assert list(m().hooks_registrados(ctx_, None)) == [("hooks/hooks.pi.json", None, True)], roto
        for malo in ({"script": 7, "args": [], "timeout": 10}, {"script": "x.py", "args": "--host pi", "timeout": 10},
                     {"script": "x.py", "args": ["--host", 7], "timeout": 10}, "verificar_capa.py --host pi"):
            datos = json.loads(json.dumps(original))
            datos["hooks"]["tool_call"][2]["hooks"][0] = malo
            archivo.write_text(json.dumps(datos), encoding="utf-8")
            registrados = list(m().hooks_registrados(ctx_, None))
            assert ("hooks/hooks.pi.json tool_call[2][0]", None, True) in registrados and len(registrados) == len(HOOKS_DE_PI), (malo, registrados)


def test_archivos_da_un_md_de_pi_agents_por_agente_derivado_de_su_md_y_nada_mas():
    agentes = [agente_de_pi(nombre) for nombre in AGENTES]
    archivos = m().archivos(agentes)
    assert [(a.ruta, a.fuente, a.arreglo) for a in archivos] == [
        (".pi/agents/%s.md" % nombre, ".claude/agents/%s.md" % nombre, "pi-agentes") for nombre in AGENTES], archivos
    assert [a.contenido for a in archivos] == [m().md(agente) for agente in agentes]
    assert m().ID_AGENTES == "pi-agentes" and m().archivos([]) == []


def test_gentle_pi_carga_cada_md_con_su_nombre_su_description_y_las_herramientas_de_pi():
    for nombre in AGENTES:
        agente = agente_de_pi(nombre)
        texto = m().md(agente)
        cargado = cargar_en_gentle_pi(texto, nombre + ".md")
        assert "error" not in cargado, (nombre, cargado)
        assert cargado["claves"] == ["description", "name", "tools"], (nombre, cargado["claves"])
        assert (cargado["name"], cargado["description"]) == (nombre, agente.descripcion), (nombre, cargado)
        assert cargado["tools"] == HERRAMIENTAS_ESPERADAS[nombre], (nombre, cargado["tools"])
        assert (cargado["model"], cargado["thinking"], cargado["mode"]) == (None, None, None), (nombre, cargado)
        assert texto.endswith("\n") and "\r" not in texto and not texto.startswith("\ufeff"), nombre
        texto.encode("utf-8")


def test_las_herramientas_de_claude_code_pasan_a_las_de_pi_y_dicen_lo_mismo_que_los_textos_de_pi():
    assert m().HERRAMIENTAS == {"Read": "read", "Glob": "find", "Grep": "grep", "Edit": "edit", "Write": "write", "Bash": "bash",
                                "PowerShell": "powershell"}, m().HERRAMIENTAS
    assert set(m().HERRAMIENTAS.values()) <= HERRAMIENTAS_DE_PI
    textos = m().TEXTOS
    solo_lees = nombradas_en(textos["{{host:solo-lees}}"])
    assert solo_lees == {"read", "grep", "find"} == nombradas_en(textos["{{host:leida-con}}"]), solo_lees
    assert nombradas_en(textos["{{host:la-busqueda}}"]) == {m().HERRAMIENTAS["Glob"], m().HERRAMIENTAS["Grep"]}
    assert nombradas_en(textos["{{host:edicion}}"]) == {m().HERRAMIENTAS["Edit"], m().HERRAMIENTAS["Write"]}
    assert nombradas_en(textos["{{host:shell}}"] + textos["{{host:por-shell}}"]) == {m().HERRAMIENTAS["Bash"]}
    for nombre in AGENTES:
        cargado = cargar_en_gentle_pi(m().md(agente_de_pi(nombre)), nombre + ".md")
        assert nombradas_en(cargado["instructions"]) <= set(cargado["tools"]), (nombre, nombradas_en(cargado["instructions"]))
        if nombre.startswith("revisor-"):
            assert set(cargado["tools"]) == solo_lees, (nombre, cargado["tools"])


def test_el_cuerpo_es_el_md_con_los_marcadores_resueltos_con_los_textos_de_pi():
    for nombre in AGENTES:
        agente = agente_de_pi(nombre)
        cuerpo = cargar_en_gentle_pi(m().md(agente), nombre + ".md")["instructions"]
        assert cuerpo == agente.instrucciones.strip(), nombre
        for marca in ("{{", "<!-- instancia:", "<!-- /instancia:", "Lo genera odd-ws desde su plantilla", "odd-ws-hash",
                      "odd-ws-plantilla"):
            assert marca not in cuerpo, (nombre, marca)
        for frase in FRASES_DE_CLAUDE_CODE:
            assert frase not in cuerpo, (nombre, frase)
        assert "con `read`" in cuerpo and "precargada" in cuerpo, nombre
        for skill in agente.skills:
            assert "`%s`" % skill in cuerpo, ("la skill del frontmatter tiene que estar nombrada en el arranque", nombre, skill)
    assert "de la bitácora" in cargar_en_gentle_pi(m().md(agente_de_pi("writer-sql")), "w.md")["instructions"]


def test_la_version_y_la_huella_van_en_comentarios_del_frontmatter_que_gentle_pi_ignora():
    for nombre in AGENTES:
        agente = agente_de_pi(nombre)
        texto = m().md(agente)
        lineas = texto.split("\n")
        assert lineas[0] == "---", lineas[:2]
        assert lineas[1] == "# Lo genera odd-ws desde .claude/agents/%s.md, que es la fuente: los cambios van en ese .md, no acá." % nombre
        assert lineas[2] == "# odd-ws-plantilla: %d" % agente.version, lineas[2]
        huella = re.fullmatch(r"# odd-ws-hash: ([0-9a-f]{64})", lineas[3])
        assert huella and huella.group(1) == m().huella(texto), (nombre, lineas[3])
        assert m().huella(texto.replace(huella.group(1), "0" * 64)) == huella.group(1), nombre
        assert m().huella(texto.replace("\n", "\r\n")) == m().huella("\ufeff" + texto) == huella.group(1), nombre
        cambios = (texto.replace("Arranque", "Arranco", 1), texto.replace("name: ", "name:  ", 1), texto[len("---\n"):],
                   texto.replace("tools: read", "tools: read, ls", 1), texto.replace("# odd-ws-plantilla", "# odd-ws-plantila", 1),
                   texto.replace("\n---\n", "\n---\n# odd-ws-hash: %s\n" % huella.group(1), 1))
        for cambiado in cambios:
            assert cambiado != texto and m().huella(cambiado) != huella.group(1), (nombre, cambiado[:200])
        cargado = cargar_en_gentle_pi(texto, nombre + ".md")
        assert not [clave for clave in cargado["claves"] if "odd" in clave], cargado["claves"]
    sin_version = m().md(agente_de_pi("writer-sql")._replace(version=None))
    assert sin_version.split("\n")[2] == "# odd-ws-plantilla:", sin_version.split("\n")[:4]


def test_gentle_pi_carga_los_md_con_textos_raros_en_la_description_y_en_los_bloques_de_la_instancia():
    raras = ['Mía: \'\'\' y """ con C:\\x\\y, ñ y # no es comentario', '"entre comillas dobles"', "'entre simples'", "[a, b]",
             "  con espacios  ", "---", "a\n---\nb", "x\r\ny\rz", "uno\u2028dos\u2029tres", "tab\taquí", "clave: valor", "- item",
             "\ud800 suelto", '\\"', "#", "termina en \"", "' y \"", "\x00\x01\x7f", "\u00a0rodeada de espacios raros\u3000", "{{host:x}}"]
    identidad = ("Identidad '''propia''' con \"\"\"comillas\"\"\", una \\ barra al final\\\n---\n# odd-ws-hash: 0\nname: falso\n"
                 "<!-- un comentario -->\n\tcon tab y \x7f.\n")
    for rara in raras:
        agente = con_identidad("writer-sql", rara, identidad)
        texto = m().md(agente)
        texto.encode("utf-8")
        cargado = cargar_en_gentle_pi(texto, "writer-sql.md")
        esperada = recortar_como_js(re.sub("[\r\n\u2028\u2029]", " ", re.sub("[\ud800-\udfff]", "\ufffd", rara)))
        assert "error" not in cargado, (rara, cargado)
        assert cargado["description"] == esperada, (rara, cargado["description"], esperada)
        assert (cargado["name"], cargado["tools"]) == ("writer-sql", HERRAMIENTAS_ESPERADAS["writer-sql"]), (rara, cargado)
        assert identidad.rstrip("\n") in cargado["instructions"], rara
        assert m().huella(texto) == re.search(r"(?m)^# odd-ws-hash: (\S+)$", texto).group(1), rara


def test_un_comentario_html_en_el_cuerpo_o_una_clave_desconocida_en_el_frontmatter_no_rompen_la_carga():
    texto = m().md(agente_de_pi("revisor-sql"))
    base = cargar_en_gentle_pi(texto, "revisor-sql.md")
    con_html = cargar_en_gentle_pi(texto.replace("\n---\n", "\n---\n<!-- odd-ws-hash: 0 -->\n", 1), "revisor-sql.md")
    assert {k: v for k, v in con_html.items() if k != "instructions"} == {k: v for k, v in base.items() if k != "instructions"}, con_html
    assert con_html["instructions"] == "<!-- odd-ws-hash: 0 -->\n" + base["instructions"], con_html["instructions"][:80]
    con_clave = cargar_en_gentle_pi(texto.replace("\nname: ", "\nodd-ws-hash: 0\nname: ", 1), "revisor-sql.md")
    assert con_clave["claves"] == ["description", "name", "odd-ws-hash", "tools"], con_clave["claves"]
    assert {k: v for k, v in con_clave.items() if k != "claves"} == {k: v for k, v in base.items() if k != "claves"}, con_clave


def test_el_parser_de_gentle_pi_de_estas_pruebas_sabe_decir_que_no():
    texto = m().md(agente_de_pi("revisor-sql"))
    for clave, valor in (("thinking", "muchisimo"), ("effort", "x"), ("mode", "siempre"), ("subagent_mode", "y")):
        assert "error" in cargar_en_gentle_pi(texto.replace("\nname: ", "\n%s: %s\nname: " % (clave, valor), 1), "r.md"), clave
    assert cargar_en_gentle_pi(texto.replace("\nname: ", "\nthinking: High\nname: ", 1), "r.md")["thinking"] == "high"
    cabecera = texto.split("\n---\n", 1)[0]
    assert cargar_en_gentle_pi(cabecera + "\n---\n \n\t\n", "r.md") == {"error": "no instructions after the frontmatter"}
    con_bom = cargar_en_gentle_pi("\ufeff" + texto, "otro.md")
    assert (con_bom["name"], con_bom["description"], con_bom["tools"]) == ("otro", "", []), con_bom
    cortado = cargar_en_gentle_pi(texto.replace("\nname: ", "\n---corta\nname: ", 1), "otro.md")
    assert (cortado["name"], cortado["description"], cortado["tools"]) == ("otro", "", []), cortado
    en_dos_lineas = cargar_en_gentle_pi(re.sub(r"(?m)^description: .*$", 'description: "a\nb"', texto, count=1), "r.md")
    assert en_dos_lineas["description"] == '"a', en_dos_lineas["description"]
    con_retorno = cargar_en_gentle_pi(re.sub(r"(?m)^description: .*$", 'description: "a\rb"', texto, count=1), "r.md")
    assert con_retorno["description"] == "" and "description" not in con_retorno["claves"], con_retorno
    entre_corchetes = cargar_en_gentle_pi(re.sub(r"(?m)^description: .*$", "description: [a, b]", texto, count=1), "r.md")
    assert entre_corchetes["description"] == "", entre_corchetes
    en_lista = cargar_en_gentle_pi(texto.replace("tools: read, find, grep", "tools:\n  - read\n  - grep", 1), "r.md")
    assert en_lista["tools"] == ["read", "grep"], en_lista["tools"]


def test_un_agente_que_gentle_pi_no_cargaria_o_cuya_herramienta_no_existe_en_pi_hace_fallar_la_generacion():
    base = agente_de_pi("writer-sql")
    malos = (base._replace(nombre="Writer_SQL"), base._replace(nombre=None), base._replace(nombre="../x"), base._replace(nombre=""),
             base._replace(descripcion=None), base._replace(descripcion=" \n "), base._replace(descripcion="\ufeff\u3000\u2028"),
             base._replace(instrucciones=" \n\t"), base._replace(instrucciones="\u2029\ufeff"), base._replace(instrucciones=None),
             base._replace(herramientas=("Read", "WebFetch")), base._replace(herramientas=("MultiEdit",)), base._replace(herramientas=("read",)))
    for malo in malos:
        try:
            m().md(malo)
        except ValueError:
            continue
        raise AssertionError("generó %r" % (malo[:4],))
    repetidas = cargar_en_gentle_pi(m().md(base._replace(herramientas=("Read", "Glob", "Read", "Bash", "PowerShell"))), "w.md")
    assert repetidas["tools"] == ["read", "find", "bash", "powershell"], repetidas["tools"]
    sin = m().md(base._replace(herramientas=()))
    assert "\ntools:" not in sin.split("\n---\n", 1)[0], "sin herramientas en el .md, gentle-shell le da al hijo las de Pi por defecto"
    assert cargar_en_gentle_pi(sin, "w.md")["tools"] == []


def entorno_aislado(base):
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith(("GIT_", "CLAUDE_", "PYTHON"))}
    config = base / "gitconfig"
    config.write_text("", encoding="utf-8")
    entorno.update(GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_SYSTEM=str(config), GIT_CONFIG_NOSYSTEM="1")
    return entorno


def correr_hook(script, crudo, inst, entorno, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / (script + ".py")), "--plazo", "8", *args],
                          input=json.dumps(crudo).encode("utf-8"), capture_output=True, env=entorno, cwd=str(inst), timeout=60)


def decision_de(r):
    assert (r.returncode, r.stderr) == (0, b""), r
    return json.loads(r.stdout.decode("ascii")) if r.stdout else None


def test_de_punta_a_punta_guard_comandos_con_host_pi_bloquea_por_json_con_exit_0():
    with temporal() as base:
        inst = base / "inst"
        inst.mkdir()
        (inst / "workspace.config.json").write_text(json.dumps(CONFIG_MINIMA), encoding="utf-8")
        entorno = entorno_aislado(base)
        en_inst = ctx(cwd=str(inst))
        for herramienta_, bandera in (("bash", ("--host", "pi")), ("powershell", ("--host=pi",))):
            r = correr_hook("guard_comandos", llamada(herramienta_, {"command": "git push --force origin main"}, ctx=en_inst), inst, entorno,
                            *bandera)
            datos = decision_de(r)
            assert datos["accion"] == "bloquear" and datos["texto"].startswith("guard-comandos bloqueó el comando: "), datos
            r = correr_hook("guard_comandos", llamada(herramienta_, {"command": "git status"}, ctx=en_inst), inst, entorno, *bandera)
            assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), "control: lo que no bloquea calla: %r" % (r,)


def test_de_punta_a_punta_un_host_mal_escrito_con_un_payload_de_pi_bloquea_en_tool_call_y_calla_en_lo_demas():
    with temporal() as base:
        inst = base / "inst"
        inst.mkdir()
        (inst / "workspace.config.json").write_text(json.dumps(CONFIG_MINIMA), encoding="utf-8")
        entorno = entorno_aislado(base)
        en_inst = ctx(cwd=str(inst))
        llamadas = (("verificar_capa", llamada("edit", {"path": "a.x"}, ctx=en_inst)),
                    ("guard_comandos", llamada("bash", {"command": "git status"}, ctx=en_inst)),
                    ("writer_guard", llamada("write", {"path": "a.x"}, ctx=en_inst, oddWs=odd_ws(agent="writer-doc", agentId="a1"))))
        for script, crudo in llamadas:
            for bandera in (("--host", "pii"), ("--host=Pi",), ("--host",)):
                r = correr_hook(script, crudo, inst, entorno, *bandera)
                assert r.returncode == 2 and r.stdout == b"" and r.stderr.startswith(b"odd-ws: host desconocido"), (script, bandera, r)
                assert b"claude-code, codex y pi." in r.stderr, r.stderr
        for crudo in (resultado("edit", {"path": "a.x"}, ctx=en_inst), dict(inicio("startup"), ctx=en_inst)):
            r = correr_hook("verificar_capa", crudo, inst, entorno, "--host", "pii")
            assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), (crudo["type"], r)


def test_de_punta_a_punta_verificar_capa_avisa_de_la_config_rota_segun_el_origen():
    with temporal() as base:
        inst = base / "inst"
        inst.mkdir()
        (inst / "workspace.config.json").write_text("{roto", encoding="utf-8")
        entorno = entorno_aislado(base)
        for razon, avisa in (("startup", True), ("resume", True), ("reload", True), ("new", False), ("fork", False)):
            crudo = dict(inicio(razon), ctx=ctx(cwd=str(inst)))
            datos = decision_de(correr_hook("verificar_capa", crudo, inst, entorno, "--host", "pi"))
            if avisa:
                assert datos["accion"] == "contexto" and "configuración de esta instancia está rota" in datos["texto"], (razon, datos)
            else:
                assert datos is None, (razon, datos)


def test_de_punta_a_punta_el_writer_de_pi_anota_en_la_bitacora_y_la_compuerta_lo_frena():
    with temporal() as base:
        inst = base / "inst"
        inst.mkdir()
        (inst / "workspace.config.json").write_text(json.dumps(CONFIG_MINIMA), encoding="utf-8")
        entorno = entorno_aislado(base)
        writer = odd_ws(agent="writer-doc", agentId="a1", lastAssistantMessage="Listo.")
        edicion = llamada("write", {"path": "@nota.x", "content": "hola\n"}, ctx=ctx(cwd=str(inst)), oddWs=writer)
        assert decision_de(correr_hook("writer_guard", edicion, inst, entorno, "--host", "pi")) is None
        bitacora = inst / ".claude" / "estado" / "writers" / "s1" / "a1.fotos" / "bitacora.jsonl"
        registros = [json.loads(linea) for linea in bitacora.read_text(encoding="ascii").splitlines()]
        assert registros == [{"tipo": "edicion", "rutas": [str(inst / "nota.x")]}], registros
        fin = payload("agent_before_settle", ctx=ctx(cwd=str(inst)), oddWs=writer)
        datos = decision_de(correr_hook("writer_stop", fin, inst, entorno, "--host", "pi"))
        assert datos["accion"] == "seguir" and datos["texto"], datos
        otra_vez = dict(fin, oddWs=dict(writer, continued=True))
        assert decision_de(correr_hook("writer_stop", otra_vez, inst, entorno, "--host", "pi")) is None


SKILL_SQL = "---\nname: capa-sql\n---\n# capa-sql\n\n<!-- no-negociables -->\n- NN-SQL: regla uno de la capa\n<!-- /no-negociables -->\n"
REGLAS_SQL = ('def verificar(ctx):\n'
              '    return [{"id": "T-01", "modo": "bloqueo", "severidad": "CRITICAL", "linea": n, "fragmento": "MALO",\n'
              '             "mensaje": "no va, molde: x/y.sql"} for n, t in ctx["agregadas"] if "MALO" in t]\n')
RESULTADO_OK = ("## Resultado\nestado: ok\nregla: ninguna\nintento: ninguno\npresupuesto: x.sql, techo 10 líneas\nreales: x\n"
                "arbol: sucio (x.sql)\nverificacion:\n- python x: ok\nlimites:\n- no cubre la base\n")


def git(carpeta, entorno, *args):
    subprocess.run(["git", "-c", "user.name=prueba", "-c", "user.email=prueba@example.com", "-c", "commit.gpgsign=false",
                    "-c", "core.autocrlf=false", *args], cwd=str(carpeta), check=True, capture_output=True, env=entorno, timeout=60)


def mundo_sql(base):
    entorno = entorno_aislado(base)
    inst, db = base / "inst", base / "repos" / "db"
    for repo, archivos in ((inst, {"README.md": "x\n"}), (db, {"x.sql": "SELECT 1;\n"})):
        repo.mkdir(parents=True)
        git(repo, entorno, "init", "-q")
        for nombre, texto in archivos.items():
            (repo / nombre).write_text(texto, encoding="utf-8")
        git(repo, entorno, "add", "-A")
        git(repo, entorno, "commit", "-q", "-m", "base")
    config = {"schema_version": 1, "repos": {"db": {}}, "layers": {"sql": {"extensions": [".sql"], "repos": ["db"]}}}
    (inst / "workspace.config.json").write_text(json.dumps(config), encoding="utf-8")
    (inst / "workspace.local.json").write_text(json.dumps({"repos": {"db": {"path": str(db)}}}), encoding="utf-8")
    for relativa, texto in ((".claude/skills/capa-sql/SKILL.md", SKILL_SQL), (".claude/reglas/verificar_sql.py", REGLAS_SQL),
                            (".claude/agents/writer-sql.md", "---\nname: writer-sql\nskills: [criterios, capa-sql]\n---\n\ncuerpo\n")):
        (inst / relativa).parent.mkdir(parents=True, exist_ok=True)
        (inst / relativa).write_text(texto, encoding="utf-8")
    (db / "malo.sql").write_text("SELECT 1; -- MALO\n", encoding="utf-8")
    return inst, db, entorno


def suciedades(uri):
    corte = uri.rindex("/") + 1
    return {"limpia": uri, "\\x01 al final": uri + "\x01", "\\x1f al final": uri + "\x1f", "espacio al final": uri + " ",
            "\\t en el medio": uri[:corte] + "\t" + uri[corte:]}


def test_de_punta_a_punta_una_url_file_sucia_decide_como_la_limpia_en_pre_en_post_y_al_leer():
    with temporal() as base:
        inst, db, entorno = mundo_sql(base)
        en_inst = lambda sesion: ctx(cwd=str(inst), sessionId=sesion)
        for indice, (nombre, uri) in enumerate(suciedades((db / "x.sql").as_uri()).items()):
            datos = decision_de(correr_hook("verificar_capa", llamada("edit", {"path": uri, "edits": []}, ctx=en_inst("e%d" % indice)),
                                            inst, entorno, "--host", "pi"))
            assert datos and datos["accion"] == "bloquear" and datos["texto"].startswith("primer toque (capa-sql)"), (nombre, datos)
            datos = decision_de(correr_hook("verificar_capa", resultado("read", {"path": uri}, ctx=en_inst("r%d" % indice)),
                                            inst, entorno, "--host", "pi"))
            assert datos and datos["accion"] == "contexto" and "NN-SQL" in datos["texto"], (nombre, datos)
        for indice, (nombre, uri) in enumerate(suciedades((db / "malo.sql").as_uri()).items()):
            datos = decision_de(correr_hook("verificar_capa", resultado("edit", {"path": uri, "edits": []}, ctx=en_inst("p%d" % indice)),
                                            inst, entorno, "--host", "pi"))
            assert datos and datos["accion"] == "bloquear" and "T-01" in datos["texto"], (nombre, datos)


def test_de_punta_a_punta_la_compuerta_frena_al_writer_que_escribio_por_una_url_sucia():
    with temporal() as base:
        inst, db, entorno = mundo_sql(base)
        nuevo = db / "nuevo.sql"
        for indice, (nombre, uri) in enumerate(suciedades(nuevo.as_uri()).items()):
            if nuevo.exists():
                nuevo.unlink()
            sesion = "w%d" % indice
            writer = odd_ws(agent="writer-sql", agentId="a1", lastAssistantMessage=RESULTADO_OK)
            escritura = llamada("write", {"path": uri, "content": "x"}, ctx=ctx(cwd=str(inst), sessionId=sesion), oddWs=writer)
            correr_hook("writer_guard", escritura, inst, entorno, "--host", "pi")
            bitacora = inst / ".claude" / "estado" / "writers" / sesion / "a1.fotos" / "bitacora.jsonl"
            registros = [json.loads(linea) for linea in bitacora.read_text(encoding="ascii").splitlines()]
            assert registros == [{"tipo": "edicion", "rutas": [str(nuevo)]}], (nombre, registros)
            nuevo.write_text("SELECT 9; -- MALO\n", encoding="utf-8")
            fin = payload("agent_before_settle", ctx=ctx(cwd=str(inst), sessionId=sesion), oddWs=writer)
            datos = decision_de(correr_hook("writer_stop", fin, inst, entorno, "--host", "pi"))
            assert datos and datos["accion"] == "seguir" and "T-01" in datos["texto"], (nombre, datos)


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
