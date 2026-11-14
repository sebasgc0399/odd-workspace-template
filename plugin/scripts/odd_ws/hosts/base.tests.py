import contextlib
import importlib
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent.parent))
SILENCIO = (0, "", b"")


def base():
    return importlib.import_module("odd_ws.hosts.base")


def hosts():
    return importlib.import_module("odd_ws.hosts")


def ev():
    return importlib.import_module("odd_ws.eventos")


def pre(**extra):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "s1"}
    payload.update(extra)
    return payload


def bloquea(resultado, texto):
    codigo, salida, error = resultado
    return codigo == 2 and salida == "" and texto.encode("utf-8") in error and error.startswith(b"odd-ws: host desconocido")


def test_cargar_acepta_texto_bytes_bom_y_lo_ya_cargado():
    payload = pre()
    assert base().cargar(json.dumps(payload)) == payload
    assert base().cargar(json.dumps(payload).encode("utf-8")) == payload
    assert base().cargar(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")) == payload
    assert base().cargar(payload) is payload and base().cargar(None) is None
    for roto in (b"no es json", b"", "{cortado", b"\xff\xfe"):
        try:
            base().cargar(roto)
        except ValueError:
            continue
        raise AssertionError("cargo %r" % (roto,))


def test_atender_generico_lee_decide_y_responde_con_las_funciones_que_recibe():
    vistos = []

    def leer(payload, pre_por_defecto=False):
        vistos.append(("leer", payload, pre_por_defecto))
        return None if payload.get("nada") else "evento"

    def responder(evento, decision):
        vistos.append(("responder", evento, decision))
        return 2, "", b"x\n"

    assert base().atender(leer, responder, json.dumps({"a": 1}), lambda e: "decision", True) == (2, "", b"x\n")
    assert vistos == [("leer", {"a": 1}, True), ("responder", "evento", "decision")], vistos
    assert base().atender(leer, responder, {"nada": True}, lambda e: 1 / 0) == SILENCIO, "sin evento, el núcleo no corre"


def test_un_host_conocido_atiende_con_su_adaptador():
    E = ev()
    negado = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                "permissionDecisionReason": "no"}})
    for nombre, modulo, bloqueo in (("claude-code", "claude_code", (2, "", b"no\n")), ("codex", "codex", (0, negado, b""))):
        adaptador = importlib.import_module("odd_ws.hosts." + modulo)
        vistos = []

        def nucleo(evento):
            vistos.append(evento)
            return E.Bloquear("no")

        assert hosts().atender(nombre, pre(), nucleo) == bloqueo, nombre
        assert vistos == [adaptador.leer(pre())], nombre
        sin = {k: v for k, v in pre().items() if k != "hook_event_name"}
        assert hosts().atender(nombre, sin, nucleo) == SILENCIO
        assert hosts().atender(nombre, sin, nucleo, pre_por_defecto=True) == bloqueo, nombre


def test_un_host_desconocido_bloquea_en_pre_sin_correr_el_nucleo():
    def nucleo(evento):
        raise AssertionError("con un host desconocido el núcleo no corre")

    for nombre, texto in (("gemini", "'gemini'"), ("Codex", "'Codex'"), ("", "''"), (None, "sin valor"), (7, "7")):
        resultado = hosts().atender(nombre, pre(), nucleo)
        assert bloquea(resultado, texto), (nombre, resultado)
        assert b"claude-code" in resultado[2] and b"codex" in resultado[2] and b" y pi." in resultado[2], resultado
    sin = {k: v for k, v in pre().items() if k != "hook_event_name"}
    assert bloquea(hosts().atender("otro", sin, nucleo, pre_por_defecto=True), "'otro'")
    assert bloquea(hosts().atender("otro", json.dumps(pre()).encode("utf-8"), nucleo), "'otro'")
    for roto in (b"no es json", b"", "[]", b"\xff\xfe"):
        assert bloquea(hosts().atender("otro", roto, nucleo, pre_por_defecto=True), "'otro'"), roto


@contextlib.contextmanager
def registro(nombres):
    previo = hosts().NOMBRES
    hosts().NOMBRES = nombres
    try:
        yield
    finally:
        hosts().NOMBRES = previo


def mensaje(validos):
    return ("odd-ws: host desconocido en --host ('gemini'); los válidos son %s. El hook está mal configurado y bloquea hasta "
            "que se corrija su comando.\n" % validos).encode("utf-8")


def test_el_mensaje_de_host_desconocido_enumera_los_validos_y_con_dos_es_el_de_antes():
    def nucleo(evento):
        raise AssertionError("con un host desconocido el núcleo no corre")

    assert hosts().atender("gemini", pre(), nucleo) == (2, "", mensaje("claude-code, codex y pi"))
    with registro({"claude-code": "claude_code", "codex": "codex"}):
        assert hosts().atender("gemini", pre(), nucleo) == (2, "", mensaje("claude-code y codex")), "con dos, el texto de 318864e"
    with registro({"claude-code": "claude_code"}):
        assert hosts().atender("gemini", pre(), nucleo) == (2, "", mensaje("claude-code"))


def test_un_host_desconocido_bloquea_un_tool_call_de_pi_aunque_el_hook_no_sea_un_guard_de_pre():
    def nucleo(evento):
        raise AssertionError("con un host desconocido el núcleo no corre")

    de_pi = {"type": "tool_call", "toolName": "edit", "input": {"path": "a.sql"}, "ctx": {"cwd": "/w", "sessionId": "s1"}}
    for pre_por_defecto in (False, True):
        assert bloquea(hosts().atender("pii", de_pi, nucleo, pre_por_defecto=pre_por_defecto), "'pii'"), pre_por_defecto
        assert bloquea(hosts().atender("pii", json.dumps(de_pi).encode("utf-8"), nucleo, pre_por_defecto=pre_por_defecto), "'pii'")
    for tipo in ("tool_result", "session_start", "session_compact", "agent_before_settle", "TOOL_CALL", None, 7):
        assert hosts().atender("pii", dict(de_pi, type=tipo), nucleo) == SILENCIO, tipo


def test_un_payload_de_claude_code_o_de_codex_decide_igual_que_antes_con_un_host_desconocido():
    def nucleo(evento):
        raise AssertionError("con un host desconocido el núcleo no corre")

    for nombre in ("PreToolUse", "PostToolUse", "SessionStart", "SubagentStop", None):
        payload = pre(hook_event_name=nombre) if nombre else {k: v for k, v in pre().items() if k != "hook_event_name"}
        for pre_por_defecto in (False, True):
            esperado = nombre == "PreToolUse" or (nombre is None and pre_por_defecto)
            resultado = hosts().atender("gemini", payload, nucleo, pre_por_defecto=pre_por_defecto)
            assert bloquea(resultado, "'gemini'") if esperado else resultado == SILENCIO, (nombre, pre_por_defecto, resultado)


def test_un_host_desconocido_calla_fuera_de_pre():
    def nucleo(evento):
        raise AssertionError("con un host desconocido el núcleo no corre")

    for nombre in ("PostToolUse", "SessionStart", "SubagentStop", "Stop", None, 5):
        assert hosts().atender("otro", pre(hook_event_name=nombre), nucleo) == SILENCIO, nombre
        assert hosts().atender("otro", pre(hook_event_name=nombre), nucleo, pre_por_defecto=True) == SILENCIO, nombre
    sin = {k: v for k, v in pre().items() if k != "hook_event_name"}
    assert hosts().atender("otro", sin, nucleo) == SILENCIO, "sin nombre, solo es pre en los guards de pre"
    for roto in (b"no es json", b"", "[]"):
        assert hosts().atender("otro", roto, nucleo) == SILENCIO, roto


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
