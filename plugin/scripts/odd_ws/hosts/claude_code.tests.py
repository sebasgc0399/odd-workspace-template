import importlib
import json
import os
import shutil
import stat
import subprocess
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


def test_el_puerto_de_generacion_no_suma_archivos_porque_los_md_son_la_fuente():
    plantilla_writer = importlib.import_module("plantilla_writer")
    assert m().archivos([]) == []
    assert m().archivos([plantilla_writer.agente(plantilla_writer.generar("sql"))]) == []


def test_los_textos_de_claude_code_son_los_de_sus_herramientas():
    juntos = "\n".join(m().TEXTOS.values())
    for frase in ("Edit o Write", "Read, Glob o Grep", "transcript", "Tu contexto trae precargada", "CENTINELA"):
        assert frase in juntos, frase
    assert "apply_patch" not in juntos and "bitácora" not in juntos


class Ctx:
    def __init__(self, base, version="2.1.295 (Claude Code)\n", marketplaces=None):
        self.plugin, self.home, self.llamadas, self.version = AQUI.parent.parent.parent, base / "home", [], version
        if marketplaces is not None:
            (self.home / ".claude" / "plugins").mkdir(parents=True)
            (self.home / ".claude" / "plugins" / "known_marketplaces.json").write_text(json.dumps(marketplaces), encoding="utf-8")

    def ejecutar(self, args, cwd=None):
        self.llamadas.append(tuple(args))
        return (0, self.version) if self.version else (None, "")


def test_el_puerto_del_doctor_da_la_version_de_claude_y_el_marketplace_como_antes():
    doctor = importlib.import_module("doctor")
    with Temporal() as base:
        ctx = Ctx(base, marketplaces={"odd-workspace-template": {}})
        claude, instalado = m().version(ctx, doctor.NUCLEO)
        assert (claude.id, claude.estado, claude.detalle, instalado) == ("claude", "OK", "2.1.295", True), claude
        assert [(r.id, r.estado, r.detalle) for r in m().chequeos(ctx, None, doctor.NUCLEO, doctor.NUCLEO.CLI_INSTALADO)] == [
            ("marketplace", "OK", "odd-workspace-template registrado")]
        assert ctx.llamadas == [("claude", "--version")], ctx.llamadas
    with Temporal() as base:
        ctx = Ctx(base, version="2.1.200 (Claude Code)\n")
        claude, instalado = m().version(ctx, doctor.NUCLEO)
        assert (claude.estado, claude.ayuda, instalado) == ("FALTA", "Actualizá Claude Code a 2.1.284 o superior.", True), claude
        for cli in (doctor.NUCLEO.CLI_INSTALADO, doctor.NUCLEO.CLI_AUSENTE):
            [marketplace] = m().chequeos(ctx, None, doctor.NUCLEO, cli)
            assert marketplace.estado == "FALTA" and marketplace.comando == [
                "claude", "plugin", "marketplace", "add", "https://github.com/sebasgc0399/odd-workspace-template.git"], (cli, marketplace)
        [marketplace] = m().chequeos(ctx, None, doctor.NUCLEO, doctor.NUCLEO.CLI_DE_OTRO_HOST)
        assert (marketplace.id, marketplace.estado, marketplace.detalle, marketplace.comando) == (
            "marketplace", "NO APLICA", "claude no está instalado", None), marketplace
    with Temporal() as base:
        claude, instalado = m().version(Ctx(base, version=None), doctor.NUCLEO)
        assert (claude.estado, claude.detalle, instalado) == ("FALTA", "claude no está instalado", False), claude


def test_claude_code_anterior_a_2_1_295_es_aviso_porque_un_hook_que_no_arranca_deja_pasar():
    doctor = importlib.import_module("doctor")
    for version in ("2.1.284", "2.1.294"):
        with Temporal() as base:
            claude, instalado = m().version(Ctx(base, version="%s (Claude Code)\n" % version), doctor.NUCLEO)
            assert (claude.id, claude.estado, claude.detalle, instalado) == (
                "claude", "AVISO", "%s: un hook que no arranca deja pasar" % version, True), claude
            assert "2.1.295" in claude.ayuda and "onFailure" in claude.ayuda and claude.comando is None, claude
    for version in ("2.1.295", "2.1.319", "2.2.0", "3.0.0"):
        with Temporal() as base:
            claude, _ = m().version(Ctx(base, version="%s (Claude Code)\n" % version), doctor.NUCLEO)
            assert (claude.estado, claude.detalle) == ("OK", version), claude
    with Temporal() as base:
        claude, _ = m().version(Ctx(base, version="2.1.283 (Claude Code)\n"), doctor.NUCLEO)
        assert (claude.estado, claude.ayuda) == ("FALTA", "Actualizá Claude Code a 2.1.284 o superior."), claude


def test_los_hooks_registrados_de_claude_code_son_command_y_args_de_hooks_json():
    with Temporal() as base:
        registrados = list(m().hooks_registrados(Ctx(base), None))
        assert len(registrados) == 7 and all(propio for _, _, propio in registrados), registrados
        assert registrados[0] == ("hooks/hooks.json SessionStart[0][0]",
                                  ["python3", "${CLAUDE_PLUGIN_ROOT}/scripts/verificar_capa.py", "--plazo", "8"], True), registrados[0]
        ctx = Ctx(base)
        ctx.plugin = base / "sin-plugin"
        assert list(m().hooks_registrados(ctx, None)) == [("hooks/hooks.json", None, True)]
        (ctx.plugin / "hooks").mkdir(parents=True)
        (ctx.plugin / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "python w.py --host codex"}, {"type": "command", "command": "python", "args": ["w.py", 3]}]}]}}),
            encoding="utf-8")
        assert list(m().hooks_registrados(ctx, None)) == [("hooks/hooks.json Stop[0][0]", ["python", "w.py", "--host", "codex"], True),
                                                         ("hooks/hooks.json Stop[0][1]", ["python"], True)]


def base_de_hosts():
    return importlib.import_module("odd_ws.hosts.base")


def carpeta(*partes):
    ruta = Path(*partes)
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def repo_falso(*partes):
    raiz = carpeta(*partes)
    (raiz / ".git").mkdir()
    return raiz


def real(base):
    return Path(os.path.realpath(base))


def resolver(entorno, home, raiz, windows=False, pasado=None):
    return m().directorio_de_memorias(entorno, home, raiz, windows, pasado)


def sin_memorias(entorno, home, raiz, windows=False, pasado=None):
    try:
        resolver(entorno, home, raiz, windows, pasado)
    except base_de_hosts().SinMemorias as error:
        return str(error)
    raise AssertionError("se esperaba SinMemorias")


def git_aislado(cwd, scratch, *argumentos):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    entorno.update(GIT_CONFIG_GLOBAL=str(Path(scratch) / "gitconfig-global"), GIT_CONFIG_SYSTEM=str(Path(scratch) / "gitconfig-sistema"),
                   GIT_CONFIG_NOSYSTEM="1")
    comando = ["git", "-c", "init.defaultBranch=main", "-c", "user.name=prueba", "-c", "user.email=prueba@example.invalid",
               "-c", "commit.gpgsign=false", "-c", "core.hooksPath=", *argumentos]
    resultado = subprocess.run(comando, cwd=str(cwd), env=entorno, capture_output=True)
    assert resultado.returncode == 0, (comando, resultado.stderr)


def test_el_nombre_del_proyecto_cambia_por_guion_todo_lo_que_no_es_alfanumerico_ascii():
    nombre = m().nombre_de_proyecto
    assert nombre("C:\\Proyecto") == "C--Proyecto"
    assert nombre("c:\\Repos\\mi_app") == "c--Repos-mi-app"
    assert nombre("/home/u/mi_repo.git") == "-home-u-mi-repo-git"
    assert nombre("/srv/año/x") == "-srv-a-o-x"
    assert nombre("/srv/\U0001F600/x") == "-srv----x", "un carácter fuera del BMP son dos unidades de UTF-16, como en Claude Code"


def test_la_memoria_derivada_sale_de_la_raiz_del_repo_aunque_la_instancia_este_en_una_subcarpeta():
    with Temporal() as base:
        base = real(base)
        repo = repo_falso(base, "repo")
        instancia = carpeta(repo, "instancia")
        config = carpeta(base, "config")
        esperado = config / "projects" / m().nombre_de_proyecto(repo) / "memory"
        for raiz in (repo, instancia):
            resultado = resolver({"CLAUDE_CONFIG_DIR": str(config)}, base / "casa", raiz)
            assert resultado == (esperado, "derivada", "projects", str(repo)), resultado


def test_sin_claude_config_dir_la_configuracion_es_punto_claude_en_el_home():
    with Temporal() as base:
        base = real(base)
        repo = repo_falso(base, "repo")
        resultado = resolver({}, base / "casa", repo)
        assert resultado.ruta == base / "casa" / ".claude" / "projects" / m().nombre_de_proyecto(repo) / "memory", resultado
        assert resultado.origen == "derivada", resultado


def test_fuera_de_un_repo_git_cuenta_la_raiz_de_la_instancia():
    with Temporal() as base:
        base = real(base)
        assert not any((padre / ".git").exists() for padre in (base, *base.parents)), "el temporal no puede estar dentro de un repo"
        instancia = carpeta(base, "instancia")
        resultado = resolver({"CLAUDE_CONFIG_DIR": str(base / "config")}, base, instancia)
        assert resultado.ruta == base / "config" / "projects" / m().nombre_de_proyecto(instancia) / "memory", resultado
        assert resultado.detalle == str(instancia), resultado


def test_un_worktree_enlazado_comparte_la_memoria_del_repo_principal():
    with Temporal() as base:
        base = real(base)
        principal = carpeta(base, "principal")
        git_aislado(principal, base, "init", "-q")
        git_aislado(principal, base, "commit", "-q", "--allow-empty", "-m", "inicio")
        git_aislado(principal, base, "worktree", "add", "-q", str(base / "enlazado"))
        carpeta(base, "enlazado", "instancia")
        entorno = {"CLAUDE_CONFIG_DIR": str(base / "config")}
        del_principal = resolver(entorno, base, principal)
        assert del_principal.ruta.parent.name == m().nombre_de_proyecto(principal), del_principal
        for raiz in (base / "enlazado", base / "enlazado" / "instancia"):
            assert resolver(entorno, base, raiz) == del_principal, (raiz, resolver(entorno, base, raiz), del_principal)


def test_un_gitdir_sin_commondir_como_el_de_un_submodulo_es_su_propio_proyecto():
    with Temporal() as base:
        base = real(base)
        carpeta(base, "externo", "modulos", "sub")
        sub = carpeta(base, "repo", "sub")
        (sub / ".git").write_text("gitdir: ../../externo/modulos/sub\n", encoding="utf-8")
        resultado = resolver({"CLAUDE_CONFIG_DIR": str(base / "config")}, base, sub)
        assert resultado.ruta.parent.name == m().nombre_de_proyecto(sub), resultado


def test_un_nombre_de_proyecto_de_mas_de_200_caracteres_no_se_adivina():
    with Temporal() as base:
        base = real(base)
        largo = 200 - len(str(base)) - len(os.sep)
        assert largo > 0, base
        justo = repo_falso(base, "a" * largo)
        assert len(m().nombre_de_proyecto(justo)) == 200
        assert resolver({"CLAUDE_CONFIG_DIR": str(base / "config")}, base, justo).ruta.parent.name == m().nombre_de_proyecto(justo)
        largo_de_mas = repo_falso(base, "b" * (largo + 1))
        motivo = sin_memorias({"CLAUDE_CONFIG_DIR": str(base / "config")}, base, largo_de_mas)
        assert "201" in motivo and "200" in motivo and "--memorias" in motivo, motivo


def test_en_windows_la_carpeta_del_proyecto_tolera_otra_mayuscula_y_la_exacta_gana():
    with Temporal() as base:
        base = real(base)
        repo = repo_falso(base, "Repo")
        config = base / "config"
        nombre = m().nombre_de_proyecto(repo)
        carpeta(config, "projects", nombre.swapcase(), "memory")
        entorno = {"CLAUDE_CONFIG_DIR": str(config)}
        assert resolver(entorno, base, repo, windows=True).ruta == config / "projects" / nombre.swapcase() / "memory"
        assert resolver(entorno, base, repo, windows=False).ruta == config / "projects" / nombre / "memory"


def escribir_settings(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos if isinstance(datos, bytes) else json.dumps(datos).encode("utf-8"))
    return ruta


def test_auto_memory_directory_de_los_settings_con_su_precedencia():
    with Temporal() as base:
        base = real(base)
        repo = repo_falso(base, "repo")
        config, casa = base / "config", base / "casa"
        entorno = {"CLAUDE_CONFIG_DIR": str(config)}
        usuario = escribir_settings(config / "settings.json", b"\xef\xbb\xbf" + json.dumps({"autoMemoryDirectory": "~/mem-usuario"}).encode())
        assert resolver(entorno, casa, repo) == (casa / "mem-usuario", "derivada", "autoMemoryDirectory", str(usuario))
        absoluta = str(base / "mem-proyecto")
        proyecto = escribir_settings(repo / ".claude" / "settings.json", {"autoMemoryDirectory": absoluta})
        assert resolver(entorno, casa, repo) == (Path(absoluta), "derivada", "autoMemoryDirectory", str(proyecto))
        local = escribir_settings(repo / ".claude" / "settings.local.json", {"autoMemoryDirectory": "~/mem-local"})
        assert resolver(entorno, casa, repo) == (casa / "mem-local", "derivada", "autoMemoryDirectory", str(local))
        escribir_settings(local, b"{esto no es json")
        assert resolver(entorno, casa, repo).detalle == str(proyecto), "un settings roto no cuenta, como en Claude Code"
        escribir_settings(local, {"autoMemoryDirectory": "relativa/mem"})
        motivo = sin_memorias(entorno, casa, repo)
        assert "relativa/mem" in motivo and str(local) in motivo and "--memorias" in motivo, motivo


def test_claude_code_project_dir_name_vale_solo_con_claude_config_dir_y_un_nombre_valido():
    with Temporal() as base:
        base = real(base)
        repo = repo_falso(base, "repo")
        config, casa = base / "config", base / "casa"
        derivado = config / "projects" / m().nombre_de_proyecto(repo) / "memory"
        con_nombre = {"CLAUDE_CONFIG_DIR": str(config), "CLAUDE_CODE_PROJECT_DIR_NAME": "trabajo_1"}
        assert resolver(con_nombre, casa, repo) == (config / "projects" / "trabajo_1" / "memory", "derivada",
                                                   "CLAUDE_CODE_PROJECT_DIR_NAME", str(config))
        assert resolver({"CLAUDE_CODE_PROJECT_DIR_NAME": "trabajo_1"}, casa, repo).ruta == (
            casa / ".claude" / "projects" / m().nombre_de_proyecto(repo) / "memory")
        for invalido in ("con", "NUL", "a/b", "x" * 65, ""):
            entorno = {"CLAUDE_CONFIG_DIR": str(config), "CLAUDE_CODE_PROJECT_DIR_NAME": invalido}
            assert resolver(entorno, casa, repo).ruta == derivado, invalido


def test_memorias_pasada_gana_a_los_settings_y_a_la_derivacion():
    with Temporal() as base:
        base = real(base)
        repo = repo_falso(base, "repo")
        escribir_settings(repo / ".claude" / "settings.json", {"autoMemoryDirectory": str(base / "otra")})
        resultado = resolver({"CLAUDE_CONFIG_DIR": str(base / "config")}, base, repo, pasado=str(base / "pasada"))
        assert resultado == (base / "pasada", "pasada", "--memorias", None), resultado


def test_el_puerto_de_memorias_se_declara_soportado_sin_tocar_el_manifiesto():
    capacidades = importlib.import_module("odd_ws.capacidades")
    estado, nota = m().MEMORIAS
    assert estado == capacidades.SOPORTADO and nota.strip(), m().MEMORIAS
    assert list(m().MANIFIESTO) == ["P%d" % n for n in range(1, 11)]
    assert all(estado == capacidades.SOPORTADO for estado, _ in m().MANIFIESTO.values())


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
