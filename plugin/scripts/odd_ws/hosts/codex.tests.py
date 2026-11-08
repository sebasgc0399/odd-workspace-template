import contextlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent.parent))
SILENCIO = (0, "", b"")
CWD = os.path.abspath(os.path.join(os.sep, "w"))
OTRA = os.path.abspath(os.path.join(os.sep, "otra", "x.sql"))
SIN_CONFIRMACION = ("Codex no puede pedir confirmación desde un hook, así que este comando queda bloqueado: si hace falta, "
                    "pídele al usuario que lo corra él.")


def m():
    return importlib.import_module("odd_ws.hosts.codex")


def ev():
    return importlib.import_module("odd_ws.eventos")


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


def parche(*lineas, fin="\n"):
    return fin.join(("*** Begin Patch",) + lineas + ("*** End Patch",)) + fin


def pre(herramienta, entrada, **extra):
    payload = {"hook_event_name": "PreToolUse", "tool_name": herramienta, "tool_input": entrada, "session_id": "s1",
               "cwd": CWD, "turn_id": "t1", "model": "gpt-x", "permission_mode": "default"}
    payload.update(extra)
    return payload


def post(herramienta, entrada, **extra):
    return pre(herramienta, entrada, hook_event_name="PostToolUse", tool_response={"ok": True}, **extra)


def de_parche(texto, **extra):
    return pre("apply_patch", {"command": texto}, **extra)


def rutas(texto, cwd=CWD):
    return m().leer(de_parche(texto, cwd=cwd)).rutas


def herramienta(**sobre):
    campos = {"fase": "pre", "tipo": "otra", "herramienta": None, "rutas": (), "comando": None, "dialecto": None,
              "agente": None, "id_agente": None, "sesion": "s1", "cwd": CWD}
    campos.update(sobre)
    return ev().Herramienta(**campos)


def inicio(origen):
    return {"hook_event_name": "SessionStart", "source": origen, "session_id": "s1", "cwd": CWD, "model": "gpt-x"}


def fin(**extra):
    payload = {"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a1", "agent_type": "writer-x",
               "cwd": CWD, "agent_transcript_path": "/t/rollout-a1.jsonl", "last_assistant_message": "Listo."}
    payload.update(extra)
    return payload


def test_apply_patch_es_edicion_con_las_rutas_de_cada_marca():
    texto = parche("*** Add File: src/nuevo.py", "+print(1)", "*** Update File: src/viejo.py", "@@", "-a", "+b",
                   "*** Delete File: docs/borrar.md", "*** Update File: src/mover.py", "*** Move to: src/movido.py", "@@",
                   " x", "-y", "+z")
    leido = m().leer(de_parche(texto, agent_type="writer-x", agent_id="a1"))
    assert leido == herramienta(tipo="edicion", herramienta="apply_patch", agente="writer-x", id_agente="a1", rutas=(
        en("src", "nuevo.py"), en("src", "viejo.py"), en("docs", "borrar.md"), en("src", "mover.py"), en("src", "movido.py"))), leido
    assert leido.comando is None and leido.dialecto is None, "el parche no es un comando de shell"


def test_las_rutas_absolutas_se_respetan_y_las_relativas_van_contra_el_cwd():
    assert rutas(parche("*** Update File: %s" % OTRA, " x")) == (OTRA,)
    assert rutas(parche("*** Add File: a/../b/c.txt", "+x")) == (en("b", "c.txt"),), "la relativa sale normalizada"
    assert rutas(parche("*** Add File: c.txt", "+x"), cwd=None) == ("c.txt",), "sin cwd, la relativa queda como viene"
    assert rutas(parche("*** Add File: c.txt", "+x"), cwd=7) == ("c.txt",)


def test_las_rutas_salen_en_orden_y_sin_repetir():
    texto = parche("*** Update File: b.py", " x", "*** Update File: a.py", " y", "*** Update File: b.py", " z",
                   "*** Update File: ./a.py", "*** Move to: b.py", " w")
    assert rutas(texto) == (en("b.py"), en("a.py")), rutas(texto)


def test_tolera_crlf_la_linea_de_environment_id_y_el_relleno_de_las_marcas():
    texto = parche("*** Environment ID: env-1", "*** Add File: a.py ", "+x", "  *** Delete File: b.py", fin="\r\n")
    assert rutas(texto) == (en("a.py"), en("b.py")), rutas(texto)
    assert rutas("*** Begin Patch\r\n*** Update File: c.py\r\n*** Move to: d.py\r\n@@\r\n-a\r\n+b\r\n*** End Patch") == (
        en("c.py"), en("d.py"))


def test_el_espacio_de_mas_tras_la_marca_es_parte_de_la_ruta_como_en_codex():
    assert rutas(parche("*** Add File:  a.py", "+x")) == (en(" a.py"),), rutas(parche("*** Add File:  a.py", "+x"))


def test_un_texto_sin_marcas_da_rutas_vacias():
    for texto in ("", "no es un parche", parche("@@", "+x"), "*** Add File:", "*** Add File: ", "*** Add File:x.py",
                  parche("*** Begin Patch")):
        leido = m().leer(de_parche(texto))
        assert (leido.tipo, leido.rutas) == ("edicion", ()), (texto, leido.rutas)


def test_las_lineas_de_contenido_que_parecen_marcas_no_son_rutas():
    texto = parche("*** Add File: a.py", "+*** Delete File: falsa1.py", "*** Update File: b.py", "@@",
                   " *** Add File: falsa2.py", "-*** Update File: falsa3.py", "+*** Move to: falsa4.py",
                   "*** End of File", "*** Delete File: c.py")
    assert rutas(texto) == (en("a.py"), en("b.py"), en("c.py")), rutas(texto)


def test_un_parche_de_dos_archivos_en_dos_capas():
    texto = parche("*** Update File: %s" % OTRA, "@@", "-a", "+b", "*** Add File: web/A.cs", "+int a;")
    assert rutas(texto) == (OTRA, en("web", "A.cs"))
    assert m().leer(post("apply_patch", {"command": texto})).rutas == (OTRA, en("web", "A.cs")), "post lee lo mismo"


def test_bash_es_shell_y_el_dialecto_sale_de_la_plataforma():
    with sistema("nt"):
        assert m().leer(pre("Bash", {"command": "Get-ChildItem"})) == herramienta(
            tipo="shell", herramienta="Bash", comando="Get-ChildItem", dialecto="powershell")
    with sistema("posix"):
        assert m().leer(pre("Bash", {"command": "ls -la"})) == herramienta(
            tipo="shell", herramienta="Bash", comando="ls -la", dialecto="posix")
        assert m().leer(post("Bash", {"command": "ls"})).fase == "post"
    assert m().leer(pre("Bash", {"command": "ls"})).dialecto == ("powershell" if os.name == "nt" else "posix"), "sin parche"


def test_las_demas_herramientas_son_otra_y_no_llevan_comando_ni_rutas():
    for nombre, entrada in (("view_image", {"path": "/w/a.png"}), ("mcp__srv__run", {"command": "git push --force"}),
                            ("spawn_agent", {"command": "ls"}), ("Edit", {"file_path": "/w/a.txt"}),
                            ("Read", {"file_path": "/w/a.txt"}), ("PowerShell", {"command": "ls"}), (None, {"command": "ls"}),
                            (7, {"command": "ls"})):
        leido = m().leer(pre(nombre, entrada))
        assert (leido.tipo, leido.rutas, leido.comando, leido.dialecto) == ("otra", (), None, None), (nombre, leido)
        assert leido.herramienta == (nombre if isinstance(nombre, str) else None), nombre


def test_entradas_malformadas_quedan_vacias():
    for entrada in (None, "texto", [1], 7, {}, {"command": 7}, {"command": None}, {"command": ["apply_patch", "x"]}):
        leido = m().leer(pre("apply_patch", entrada))
        assert (leido.tipo, leido.rutas, leido.comando) == ("edicion", (), None), entrada
        leido = m().leer(pre("Bash", entrada))
        assert (leido.tipo, leido.comando) == ("shell", None), entrada
    assert m().leer(pre("Bash", {"command": ""})).comando == "", "el núcleo decide qué es un comando vacío"


def test_agente_principal_y_writer():
    principal = m().leer(pre("Bash", {"command": "ls"}))
    assert (principal.agente, principal.id_agente, principal.sesion, principal.cwd) == (None, None, "s1", CWD)
    writer = m().leer(pre("Bash", {"command": "ls"}, agent_type="writer-x", agent_id="a1"))
    assert (writer.agente, writer.id_agente) == ("writer-x", "a1")
    crudo = m().leer(pre("Bash", {"command": "ls"}, agent_type=7, agent_id=5, session_id=["s"]))
    assert (crudo.agente, crudo.id_agente, crudo.sesion) == (7, 5, ["s"]), "la identidad la valida el núcleo"


def test_session_start_en_cada_origen_con_fork():
    for origen in ("startup", "resume", "clear", "compact", "fork"):
        assert m().leer(inicio(origen)) == ev().InicioSesion(origen=origen, sesion="s1", cwd=CWD), origen
    assert m().leer({"hook_event_name": "SessionStart"}) == ev().InicioSesion()


def test_subagent_stop_con_y_sin_reintento():
    esperado = ev().FinSubagente(agente="writer-x", id_agente="a1", sesion="s1", cwd=CWD, transcript="/t/rollout-a1.jsonl",
                                 ultimo_mensaje="Listo.", ya_reintentado=False)
    assert m().leer(fin()) == esperado
    assert m().leer(fin(stop_hook_active=True)) == ev().FinSubagente(**dict(vars(esperado), ya_reintentado=True))
    for casi in ("true", 1, [True], False):
        assert m().leer(fin(stop_hook_active=casi)).ya_reintentado is False, casi


def test_lo_que_no_es_un_evento_y_el_nombre_ausente():
    payload = pre("Bash", {"command": "ls"})
    for no_es in (None, 5, "texto", [], [payload]):
        assert m().leer(no_es) is None, no_es
    for nombre in ("Stop", "UserPromptSubmit", "PermissionRequest", "", None, 5, "pretooluse"):
        assert m().leer(dict(payload, hook_event_name=nombre)) is None, nombre
    sin = {k: v for k, v in payload.items() if k != "hook_event_name"}
    assert m().leer(sin) is None
    assert m().leer(sin, pre_por_defecto=True) == m().leer(payload)
    assert m().leer(dict(sin, hook_event_name=None), pre_por_defecto=True) is None, "solo la clave ausente"


def test_cargar_y_atender_son_los_compartidos():
    base = importlib.import_module("odd_ws.hosts.base")
    claude = importlib.import_module("odd_ws.hosts.claude_code")
    assert m().cargar is base.cargar and claude.cargar is base.cargar
    E, vistos = ev(), []

    def nucleo(evento):
        vistos.append(evento)
        return E.Bloquear("no")

    payload = pre("Bash", {"command": "ls"})
    assert m().atender(json.dumps(payload).encode("utf-8"), nucleo) == (2, "", b"no\n")
    assert vistos == [m().leer(payload)]
    assert m().atender({"hook_event_name": "Stop"}, nucleo) == SILENCIO and len(vistos) == 1
    sin = {k: v for k, v in payload.items() if k != "hook_event_name"}
    assert m().atender(sin, nucleo) == SILENCIO
    assert m().atender(sin, nucleo, pre_por_defecto=True) == (2, "", b"no\n")


def test_responder_en_pre_degrada_preguntar_a_bloquear():
    E, e = ev(), m().leer(pre("Bash", {"command": "ls"}))
    assert m().responder(e, E.Permitir()) == SILENCIO
    assert m().responder(e, E.Bloquear("guard bloqueó: ñ")) == (2, "", "guard bloqueó: ñ\n".encode("utf-8"))
    assert m().responder(e, E.Preguntar("¿correr git commit?")) == (
        2, "", ("¿correr git commit?\n" + SIN_CONFIRMACION + "\n").encode("utf-8"))
    assert m().responder(e, E.Contexto("dato")) == SILENCIO
    assert m().responder(e, E.Seguir("falta")) == SILENCIO
    parche_ = m().leer(de_parche(parche("*** Add File: a.py", "+x")))
    assert m().responder(parche_, E.Bloquear("primer toque")) == (2, "", b"primer toque\n")


def test_responder_en_post():
    E, e = ev(), m().leer(post("apply_patch", {"command": parche("*** Add File: a.py", "+x")}))
    assert m().responder(e, E.Permitir()) == SILENCIO
    assert m().responder(e, E.Bloquear("corregir y reintentar")) == (2, "", b"corregir y reintentar\n")
    assert m().responder(e, E.Contexto("línea 1\nlínea 2")) == (
        0, '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "l\\u00ednea 1\\nl\\u00ednea 2"}}', b"")
    assert m().responder(e, E.Preguntar("x")) == SILENCIO, "preguntar en post no existe ni degradado"
    assert m().responder(e, E.Seguir("x")) == SILENCIO


def test_un_bloqueo_que_no_se_puede_codificar_igual_bloquea():
    E = ev()
    for e in (m().leer(pre("Bash", {"command": "ls"})), m().leer(post("Bash", {"command": "ls"}))):
        assert m().responder(e, E.Bloquear("temporal C:\\t\ud800")) == (2, "", b"temporal C:\\t?\n")
    codigo, salida, error = m().responder(m().leer(pre("Bash", {"command": "ls"})), E.Preguntar("x\ud800"))
    assert (codigo, salida) == (2, "") and error.startswith(b"x?\n"), error


def test_responder_al_iniciar_la_sesion_y_al_cerrar_un_subagente():
    E = ev()
    for origen in ("startup", "fork"):
        e = m().leer(inicio(origen))
        assert m().responder(e, E.Contexto("config rota (ñ)")) == (
            0, '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "config rota (\\u00f1)"}}', b"")
        for decision in (E.Permitir(), E.Bloquear("x"), E.Preguntar("x"), E.Seguir("x")):
            assert m().responder(e, decision) == SILENCIO, (origen, decision)
    e = m().leer(fin())
    assert m().responder(e, E.Seguir("todavía no")) == (0, '{"decision": "block", "reason": "todav\\u00eda no"}', b"")
    for decision in (E.Permitir(), E.Bloquear("x"), E.Preguntar("x"), E.Contexto("x"), None, "bloquear"):
        assert m().responder(e, decision) == SILENCIO, decision


def test_las_degradaciones_estan_declaradas():
    E = ev()
    cap = importlib.import_module("odd_ws.capacidades")
    assert m().DEGRADACIONES == {cap.PRE: {E.Preguntar: E.Bloquear}}
    assert importlib.import_module("odd_ws.hosts.claude_code").DEGRADACIONES == {}
    assert m().MANIFIESTO["P3"][0] == cap.DEGRADADO and "bloque" in m().MANIFIESTO["P3"][1], m().MANIFIESTO["P3"]
    assert m().MANIFIESTO["P5"][0] == cap.SOPORTADO and "bitácora" in m().MANIFIESTO["P5"][1], m().MANIFIESTO["P5"]


def test_el_registro_elige_el_adaptador_por_su_nombre_de_cli():
    hosts = importlib.import_module("odd_ws.hosts")
    assert hosts.ADAPTADORES == ("claude_code", "codex")
    assert hosts.NOMBRES == {"claude-code": "claude_code", "codex": "codex"}
    assert hosts.adaptador("codex") is m()
    assert hosts.adaptador("claude-code") is importlib.import_module("odd_ws.hosts.claude_code")
    for desconocido in ("Codex", "claude_code", "", None, 7, ["codex"], "gemini"):
        assert hosts.adaptador(desconocido) is None, desconocido


@contextlib.contextmanager
def temporal():
    base = Path(tempfile.mkdtemp(prefix="codex-test-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_el_writer_de_codex_sale_de_la_bitacora_y_no_del_transcript():
    comun = importlib.import_module("odd_ws.comun")
    hosts = importlib.import_module("odd_ws.hosts")
    assert m().BITACORA is True and hosts.necesita_bitacora("codex") is True
    with temporal() as base:
        transcript = base / "rollout-a1.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": str(base / "del-transcript.sql")}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls transcript"}}]}}) + "\n", encoding="utf-8")
        carpeta = base / "a1.fotos"
        carpeta.mkdir()
        a, b = str(base / "a.sql"), str(base / "b.sql")
        for registro in ({"tipo": "edicion", "rutas": [a, b]}, {"tipo": "shell", "comando": "ls", "dialecto": "powershell"}):
            comun.anotar_en_bitacora(str(carpeta), registro)
        e = m().leer(fin(agent_transcript_path=str(transcript)))
        assert m().archivos_del_writer(e, str(carpeta)) == ([a, b], [])
        assert m().comandos_del_writer(e, str(carpeta)) == [("powershell", "ls")]
        archivos, faltas = m().archivos_del_writer(e, str(base / "otra.fotos"))
        assert archivos == [] and faltas == [], "sin bitácora ni fotos el writer no tocó nada"
        assert m().comandos_del_writer(e, str(base / "otra.fotos")) is None


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
