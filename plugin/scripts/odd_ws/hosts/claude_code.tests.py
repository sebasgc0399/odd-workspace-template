import importlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent.parent))
SOBRANTES = []
SILENCIO = (0, "", b"")


def m():
    return importlib.import_module("odd_ws.hosts.claude_code")


def ev():
    return importlib.import_module("odd_ws.eventos")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Temporal:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="claude-code-test-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def pre(herramienta, entrada, **extra):
    payload = {"hook_event_name": "PreToolUse", "tool_name": herramienta, "tool_input": entrada, "session_id": "s1",
               "cwd": "/w"}
    payload.update(extra)
    return payload


def post(herramienta, entrada, **extra):
    return pre(herramienta, entrada, hook_event_name="PostToolUse", **extra)


def herramienta(**sobre):
    campos = {"fase": "pre", "tipo": "otra", "herramienta": None, "rutas": (), "comando": None, "dialecto": None,
              "agente": None, "id_agente": None, "sesion": "s1", "cwd": "/w"}
    campos.update(sobre)
    return ev().Herramienta(**campos)


def inicio(origen):
    return {"hook_event_name": "SessionStart", "source": origen, "session_id": "s1", "cwd": "/w"}


def fin(**extra):
    payload = {"hook_event_name": "SubagentStop", "session_id": "s1", "agent_id": "a1", "agent_type": "writer-x",
               "cwd": "/w", "agent_transcript_path": "/t/agent-a1.jsonl", "last_assistant_message": "Listo."}
    payload.update(extra)
    return payload


def transcript(base, usos, nombre="agent-1.jsonl"):
    lineas = [json.dumps({"type": "user", "message": {"role": "user", "content": "haz esto"}}), "{esto no es json"]
    for nombre_h, entrada in usos:
        lineas.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "voy"}, {"type": "tool_use", "id": "t", "name": nombre_h, "input": entrada}]}}))
        lineas.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}))
    ruta = Path(base) / nombre
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


def test_pre_tool_use_de_cada_herramienta():
    casos = [
        (pre("Edit", {"file_path": "/w/a.txt", "old_string": "a", "new_string": "b"}),
         herramienta(tipo="edicion", herramienta="Edit", rutas=("/w/a.txt",))),
        (pre("Write", {"file_path": "/w/b.txt", "content": "z"}),
         herramienta(tipo="edicion", herramienta="Write", rutas=("/w/b.txt",))),
        (pre("MultiEdit", {"file_path": "/w/m.txt", "edits": []}),
         herramienta(tipo="edicion", herramienta="MultiEdit", rutas=("/w/m.txt",))),
        (pre("Read", {"file_path": "/w/c.txt"}), herramienta(tipo="lectura", herramienta="Read", rutas=("/w/c.txt",))),
        (pre("Bash", {"command": "ls -la"}), herramienta(tipo="shell", herramienta="Bash", comando="ls -la", dialecto="posix")),
        (pre("PowerShell", {"command": "Get-ChildItem"}),
         herramienta(tipo="shell", herramienta="PowerShell", comando="Get-ChildItem", dialecto="powershell")),
        (pre("Grep", {"pattern": "x", "path": "/w"}), herramienta(herramienta="Grep")),
    ]
    for payload, esperado in casos:
        leido = m().leer(payload)
        assert leido == esperado, (payload["tool_name"], leido)


def test_post_tool_use_cambia_solo_la_fase():
    for nombre, entrada in (("Edit", {"file_path": "/w/a.txt"}), ("Write", {"file_path": "/w/a.txt"}),
                            ("Read", {"file_path": "/w/a.txt"}), ("Bash", {"command": "ls"}), ("Grep", {})):
        assert m().leer(post(nombre, entrada)) == ev().Herramienta(**dict(vars(m().leer(pre(nombre, entrada))), fase="post")), nombre


def test_el_comando_viaja_con_cualquier_herramienta():
    leido = m().leer(pre("Edit", {"file_path": "/w/a.txt", "command": "git push --force"}))
    assert (leido.tipo, leido.rutas, leido.comando, leido.dialecto) == ("edicion", ("/w/a.txt",), "git push --force", None)
    assert m().leer(pre(None, {"command": "ls"})).comando == "ls"


def test_agente_principal_y_writer():
    principal = m().leer(pre("Bash", {"command": "ls"}))
    assert (principal.agente, principal.id_agente) == (None, None)
    writer = m().leer(pre("Bash", {"command": "ls"}, agent_type="writer-x", agent_id="a1"))
    assert (writer.agente, writer.id_agente) == ("writer-x", "a1")
    crudo = m().leer(pre("Bash", {"command": "ls"}, agent_type=7, agent_id=5, session_id=["s"], cwd=3))
    assert (crudo.agente, crudo.id_agente, crudo.sesion, crudo.cwd) == (7, 5, ["s"], 3), "la identidad la valida el núcleo"


def test_session_start_en_cada_origen():
    for origen in ("startup", "resume", "compact", "clear"):
        assert m().leer(inicio(origen)) == ev().InicioSesion(origen=origen, sesion="s1", cwd="/w"), origen
    assert m().leer({"hook_event_name": "SessionStart"}) == ev().InicioSesion()


def test_subagent_stop_con_y_sin_reintento():
    esperado = ev().FinSubagente(agente="writer-x", id_agente="a1", sesion="s1", cwd="/w", transcript="/t/agent-a1.jsonl",
                                 ultimo_mensaje="Listo.", ya_reintentado=False)
    assert m().leer(fin()) == esperado
    assert m().leer(fin(stop_hook_active=False)) == esperado
    assert m().leer(fin(stop_hook_active=True)) == ev().FinSubagente(**dict(vars(esperado), ya_reintentado=True))
    for casi in ("true", 1, "True", [True]):
        assert m().leer(fin(stop_hook_active=casi)).ya_reintentado is False, casi
    assert m().leer({"hook_event_name": "SubagentStop"}) == ev().FinSubagente()


def test_json_invalido_y_lo_que_no_es_un_evento():
    for crudo in (b"no es json", b"", b"\xff\xfe basura", "{cortado"):
        try:
            m().cargar(crudo)
        except ValueError:
            continue
        raise AssertionError("cargo %r" % (crudo,))
    payload = pre("Bash", {"command": "ls"})
    assert m().cargar(json.dumps(payload).encode("utf-8")) == payload
    assert m().cargar(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")) == payload, "acepta el BOM, como json.loads"
    assert m().cargar(json.dumps(payload)) == payload and m().cargar(payload) is payload
    for no_es in (None, 5, "texto", [], [payload], b"{}"):
        assert m().leer(no_es) is None, no_es
    for nombre in ("Stop", "Notification", "UserPromptSubmit", "", None, 5, ["PreToolUse"], "pretooluse"):
        assert m().leer(dict(payload, hook_event_name=nombre)) is None, nombre


def test_sin_nombre_de_evento_solo_cuenta_como_pre_si_se_pide():
    sin = {k: v for k, v in pre("Bash", {"command": "ls"}).items() if k != "hook_event_name"}
    assert m().leer(sin) is None
    assert m().leer(sin, pre_por_defecto=True) == m().leer(pre("Bash", {"command": "ls"}))
    assert m().leer(dict(sin, hook_event_name=None), pre_por_defecto=True) is None, "solo la clave ausente"
    assert m().leer(dict(sin, hook_event_name="PostToolUse"), pre_por_defecto=True).fase == "post"


def test_entradas_malformadas_quedan_vacias():
    for entrada in (None, "texto", [1], 7, {}, {"file_path": 7}, {"file_path": ""}, {"command": 7}, {"command": None}):
        leido = m().leer(pre("Edit", entrada))
        assert (leido.rutas, leido.comando) == ((), None), entrada
    for nombre in (7, None, ["Bash"], {"x": 1}):
        leido = m().leer(pre(nombre, {"command": "ls"}))
        assert (leido.herramienta, leido.tipo, leido.dialecto, leido.comando) == (None, "otra", None, "ls"), nombre
    assert m().leer(pre("Bash", {"command": ""})).comando == "", "el núcleo decide qué es un comando vacío"


def test_responder_en_pre():
    E, e = ev(), m().leer(pre("Bash", {"command": "ls"}))
    assert m().responder(e, E.Permitir()) == SILENCIO
    assert m().responder(e, E.Bloquear("guard bloqueó: ñ")) == (2, "", "guard bloqueó: ñ\n".encode("utf-8"))
    assert m().responder(e, E.Preguntar("¿correr?")) == (
        0, '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", '
           '"permissionDecisionReason": "\\u00bfcorrer?"}}\n', b"")
    assert m().responder(e, E.Contexto("dato")) == SILENCIO
    assert m().responder(e, E.Seguir("falta")) == SILENCIO
    sin = {k: v for k, v in pre("Bash", {"command": "ls"}).items() if k != "hook_event_name"}
    assert m().responder(m().leer(sin, pre_por_defecto=True), E.Bloquear("x")) == (2, "", b"x\n")


def test_responder_en_post():
    E, e = ev(), m().leer(post("Edit", {"file_path": "/w/a.txt"}))
    assert m().responder(e, E.Permitir()) == SILENCIO
    assert m().responder(e, E.Bloquear("corregir y reintentar")) == (2, "", b"corregir y reintentar\n")
    assert m().responder(e, E.Contexto("línea 1\nlínea 2")) == (
        0, '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "l\\u00ednea 1\\nl\\u00ednea 2"}}', b"")
    assert m().responder(e, E.Preguntar("x")) == SILENCIO
    assert m().responder(e, E.Seguir("x")) == SILENCIO


def test_un_bloqueo_que_no_se_puede_codificar_igual_bloquea():
    E = ev()
    for e in (m().leer(pre("Bash", {"command": "ls"})), m().leer(post("Edit", {"file_path": "/w/a.txt"}))):
        assert m().responder(e, E.Bloquear("temporal C:\\t\ud800")) == (2, "", b"temporal C:\\t?\n")


def test_responder_al_iniciar_la_sesion():
    E = ev()
    for origen in ("startup", "resume", "compact", "clear"):
        e = m().leer(inicio(origen))
        assert m().responder(e, E.Contexto("config rota (ñ)")) == (
            0, '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "config rota (\\u00f1)"}}', b"")
        for decision in (E.Permitir(), E.Bloquear("x"), E.Preguntar("x"), E.Seguir("x")):
            assert m().responder(e, decision) == SILENCIO, (origen, decision)


def test_responder_al_cerrar_un_subagente():
    E = ev()
    for e in (m().leer(fin()), m().leer(fin(stop_hook_active=True))):
        assert m().responder(e, E.Seguir("todavía no: razón")) == (
            0, '{"decision": "block", "reason": "todav\\u00eda no: raz\\u00f3n"}', b"")
        for decision in (E.Permitir(), E.Bloquear("x"), E.Preguntar("x"), E.Contexto("x")):
            assert m().responder(e, decision) == SILENCIO, decision


def test_responder_con_algo_que_no_es_una_decision_calla():
    e = m().leer(pre("Bash", {"command": "ls"}))
    for decision in (None, "bloquear", (2, "", b"x"), {"decision": "block"}):
        assert m().responder(e, decision) == SILENCIO, decision


def test_atender_lee_decide_y_responde():
    E, vistos = ev(), []

    def nucleo(evento):
        vistos.append(evento)
        return E.Bloquear("no")

    payload = pre("Bash", {"command": "ls"})
    assert m().atender(json.dumps(payload).encode("utf-8"), nucleo) == (2, "", b"no\n")
    assert vistos == [m().leer(payload)] and isinstance(vistos[0], E.Herramienta), "el núcleo recibe el evento, no el payload"
    sin = {k: v for k, v in payload.items() if k != "hook_event_name"}
    for ajeno in ({"hook_event_name": "Stop"}, sin, [], 5):
        assert m().atender(ajeno, nucleo) == SILENCIO, ajeno
    assert len(vistos) == 1, "sin evento, el núcleo no corre"
    assert m().atender(sin, nucleo, pre_por_defecto=True) == (2, "", b"no\n") and len(vistos) == 2
    try:
        m().atender(b"no es json", nucleo)
    except ValueError:
        pass
    else:
        raise AssertionError("un JSON roto lo calla el script que llama, no el adaptador")


def test_archivos_tocados_lee_edit_write_y_multiedit_en_orden_y_sin_repetir():
    with Temporal() as base:
        t = transcript(base, [
            ("Read", {"file_path": "/x/leido.txt"}), ("Edit", {"file_path": "/x/a.txt", "old_string": "a", "new_string": "b"}),
            ("Bash", {"command": "echo hola > /x/c.txt"}), ("Write", {"file_path": "/x/b.txt", "content": "z"}),
            ("Edit", {"file_path": "/x/a.txt"}), ("MultiEdit", {"file_path": "/x/m.txt", "edits": []}),
            ("Edit", {"old_string": "sin ruta"}), ("Write", {"file_path": 7}), ("Write", {"file_path": ""}),
        ])
        assert m().archivos_tocados(t) == ["/x/a.txt", "/x/b.txt", "/x/m.txt"], m().archivos_tocados(t)
        assert m().archivos_tocados(str(t)) == ["/x/a.txt", "/x/b.txt", "/x/m.txt"]
        for ilegible in (base / "no-existe.jsonl", None, 5, ["x"]):
            assert m().archivos_tocados(ilegible) == [], ilegible


def test_comandos_de_shell_con_su_dialecto_y_none_si_no_hay_transcripcion():
    with Temporal() as base:
        t = transcript(base, [
            ("Bash", {"command": "ls"}), ("Edit", {"file_path": "/x/a.txt"}), ("PowerShell", {"command": "Get-Item x"}),
            ("Bash", {"command": 5}), ("Bash", {}), ("Bash", {"command": ""}), ("Bash", {"command": "ls"}),
        ])
        assert m().comandos_de_shell(t) == [("posix", "ls"), ("powershell", "Get-Item x"), ("posix", "ls")]
        assert m().comandos_de_shell(transcript(base, [("Read", {"file_path": "x"})], nombre="sin.jsonl")) == []
        for ilegible in (base / "no-existe.jsonl", None, 5):
            assert m().comandos_de_shell(ilegible) is None, ilegible


def test_usos_devuelve_nombre_y_entrada_en_orden():
    with Temporal() as base:
        t = transcript(base, [("Read", {"file_path": "a"}), ("Edit", {"file_path": "b"}), ("Bash", {"command": "ls"}),
                              ("Edit", "no es dict"), ("Edit", None)])
        assert m().usos(t, ("Edit", "Write")) == [("Edit", {"file_path": "b"})]
        assert m().usos(t, ("Bash", "PowerShell")) == [("Bash", {"command": "ls"})]
        assert m().usos(t, ()) == []
        assert m().usos(base / "no-existe.jsonl", ("Edit",)) is None


def test_el_writer_de_claude_code_sale_del_transcript_y_no_de_la_bitacora():
    comun = importlib.import_module("odd_ws.comun")
    hosts = importlib.import_module("odd_ws.hosts")
    assert m().BITACORA is False and hosts.necesita_bitacora("claude-code") is False
    with Temporal() as base:
        t = transcript(base, [("Edit", {"file_path": "/x/a.txt"}), ("Bash", {"command": "ls"}),
                              ("PowerShell", {"command": "Get-Item x"})])
        carpeta = base / "a1.fotos"
        carpeta.mkdir()
        comun.anotar_en_bitacora(str(carpeta), {"tipo": "edicion", "rutas": ["/x/de-la-bitacora.txt"]})
        comun.anotar_en_bitacora(str(carpeta), {"tipo": "shell", "comando": "rm x", "dialecto": "posix"})
        e = m().leer(fin(agent_transcript_path=str(t)))
        assert m().archivos_del_writer(e, str(carpeta)) == (["/x/a.txt"], [])
        assert m().comandos_del_writer(e, str(carpeta)) == [("posix", "ls"), ("powershell", "Get-Item x")]
        ilegible = m().leer(fin(agent_transcript_path=str(base / "no-existe.jsonl")))
        assert m().archivos_del_writer(ilegible, str(carpeta)) == ([], []), "como antes: un transcript ilegible no deja faltas"
        assert m().comandos_del_writer(ilegible, str(carpeta)) is None


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
