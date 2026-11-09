import contextlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent.parent))
PLUGIN = AQUI.parent.parent.parent
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


def negado(motivo):
    return 0, json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": motivo}}), b""


def bloqueado(motivo):
    return 0, json.dumps({"decision": "block", "reason": motivo}), b""


def json_estricto(texto):
    texto.encode("ascii")
    datos = json.loads(texto)
    json.dumps(datos, ensure_ascii=False).encode("utf-8")
    return datos


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
    assert m().atender(json.dumps(payload).encode("utf-8"), nucleo) == negado("no")
    assert vistos == [m().leer(payload)]
    assert m().atender({"hook_event_name": "Stop"}, nucleo) == SILENCIO and len(vistos) == 1
    sin = {k: v for k, v in payload.items() if k != "hook_event_name"}
    assert m().atender(sin, nucleo) == SILENCIO
    assert m().atender(sin, nucleo, pre_por_defecto=True) == negado("no")


def test_responder_en_pre_bloquea_por_json_y_degrada_preguntar_a_bloquear():
    E, e = ev(), m().leer(pre("Bash", {"command": "ls"}))
    assert m().responder(e, E.Permitir()) == SILENCIO
    assert m().responder(e, E.Bloquear("guard bloqueó: ñ")) == (
        0, '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", '
           '"permissionDecisionReason": "guard bloque\\u00f3: \\u00f1"}}', b"")
    assert m().responder(e, E.Preguntar("¿correr git commit?")) == negado("¿correr git commit?\n" + SIN_CONFIRMACION)
    assert m().responder(e, E.Contexto("dato")) == SILENCIO
    assert m().responder(e, E.Seguir("falta")) == SILENCIO
    parche_ = m().leer(de_parche(parche("*** Add File: a.py", "+x")))
    assert m().responder(parche_, E.Bloquear("primer toque")) == negado("primer toque")


def test_responder_en_post_bloquea_por_json():
    E, e = ev(), m().leer(post("apply_patch", {"command": parche("*** Add File: a.py", "+x")}))
    assert m().responder(e, E.Permitir()) == SILENCIO
    assert m().responder(e, E.Bloquear("corregir y reintentar")) == (
        0, '{"decision": "block", "reason": "corregir y reintentar"}', b"")
    assert m().responder(e, E.Contexto("línea 1\nlínea 2")) == (
        0, '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "l\\u00ednea 1\\nl\\u00ednea 2"}}', b"")
    assert m().responder(e, E.Preguntar("x")) == SILENCIO, "preguntar en post no existe ni degradado"
    assert m().responder(e, E.Seguir("x")) == SILENCIO


def test_un_bloqueo_que_no_se_puede_codificar_igual_bloquea_con_json_valido():
    E = ev()
    en_pre, en_post = m().leer(pre("Bash", {"command": "ls"})), m().leer(post("Bash", {"command": "ls"}))
    assert m().responder(en_pre, E.Bloquear("temporal C:\\t\ud800")) == negado("temporal C:\\t?")
    assert m().responder(en_post, E.Bloquear("temporal C:\\t\ud800")) == bloqueado("temporal C:\\t?")
    codigo, salida, error = m().responder(en_pre, E.Preguntar("x\ud800"))
    assert (codigo, error) == (0, b""), (codigo, error)
    motivo = json_estricto(salida)["hookSpecificOutput"]["permissionDecisionReason"]
    assert motivo == "x?\n" + SIN_CONFIRMACION, motivo
    for e, decision in ((en_pre, E.Bloquear("\udcff solo")), (en_post, E.Bloquear("a\ud800b\udfffc"))):
        json_estricto(m().responder(e, decision)[1])


def test_en_codex_nada_sale_con_exit_2_ni_por_stderr():
    E = ev()
    eventos = (m().leer(pre("Bash", {"command": "ls"})), m().leer(de_parche(parche("*** Add File: a.py", "+x"))),
               m().leer(post("apply_patch", {"command": parche("*** Add File: a.py", "+x")})), m().leer(inicio("startup")),
               m().leer(fin()))
    for e in eventos:
        for decision in (E.Permitir(), E.Bloquear("x ñ"), E.Preguntar("x ñ"), E.Contexto("x ñ"), E.Seguir("x ñ"),
                         E.Bloquear("x\ud800"), E.Contexto("x\ud800"), E.Seguir("x\udfff")):
            codigo, salida, error = m().responder(e, decision)
            assert (codigo, error) == (0, b""), (e, decision, codigo, error)
            if salida:
                json_estricto(salida)


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
    for clave in ("P2", "P3", "P4"):
        nota = m().MANIFIESTO[clave][1]
        assert "JSON con exit 0" in nota and "stderr" not in nota, (clave, nota)
    assert ".codex-plugin" in m().MANIFIESTO["P9"][1] and "F1c" not in m().MANIFIESTO["P9"][1], m().MANIFIESTO["P9"]


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


CONFIG_MINIMA = {"schema_version": 1, "repos": {}, "layers": {"doc": {"extensions": [".x"]}}}


def comando_registrado(script):
    datos = json.loads((PLUGIN / "hooks" / "hooks.codex.json").read_text(encoding="utf-8"))
    comandos = [h["command"] for grupos in datos["hooks"].values() for grupo in grupos for h in grupo["hooks"]
                if "/scripts/%s.py" % script in h["command"]]
    assert len(comandos) == 1, comandos
    return comandos[0]


def shell_del_turno(comando):
    return ["powershell.exe", "-NoProfile", "-Command", comando] if os.name == "nt" else ["sh", "-c", comando]


def entorno_de_codex(base):
    carpeta = Path(sys.executable).parent
    if os.name != "nt" and Path(sys.executable).name != "python":
        carpeta = base / "bin"
        carpeta.mkdir()
        (carpeta / "python").symlink_to(sys.executable)
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith(("GIT_", "CLAUDE_", "PYTHON"))}
    entorno["PATH"] = str(carpeta) + os.pathsep + entorno.get("PATH", "")
    config = base / "gitconfig"
    config.write_text("", encoding="utf-8")
    entorno.update(GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_SYSTEM=str(config), GIT_CONFIG_NOSYSTEM="1")
    return entorno


def test_de_punta_a_punta_el_shell_de_codex_entrega_el_bloqueo_con_exit_0():
    with temporal() as base:
        raiz = base / "con espacio" / "plugin"
        shutil.copytree(PLUGIN, raiz, ignore=shutil.ignore_patterns("__pycache__", "*.tests.py"))
        inst = base / "inst"
        inst.mkdir()
        (inst / "workspace.config.json").write_text(json.dumps(CONFIG_MINIMA), encoding="utf-8")
        comando = comando_registrado("guard_comandos").replace("${PLUGIN_ROOT}", str(raiz))
        entorno = entorno_de_codex(base)

        def hook(linea):
            entrada = json.dumps(pre("Bash", {"command": linea}, cwd=str(inst))).encode("utf-8")
            return subprocess.run(shell_del_turno(comando), input=entrada, capture_output=True, env=entorno, cwd=str(inst),
                                  timeout=60)

        r = hook("git push --force origin main")
        assert (r.returncode, r.stderr) == (0, b""), "PowerShell convierte el exit 2 en 1, que no bloquea: %r" % (r,)
        decision = json_estricto(r.stdout.decode("ascii"))["hookSpecificOutput"]
        assert (decision["hookEventName"], decision["permissionDecision"]) == ("PreToolUse", "deny"), decision
        assert decision["permissionDecisionReason"].startswith("guard-comandos bloqueó el comando: "), decision
        r = hook("git status")
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), "control: lo que no bloquea calla: %r" % (r,)


def agente(**cambios):
    plantilla_writer = importlib.import_module("plantilla_writer")
    datos = {"nombre": "writer-sql", "descripcion": "Escribe la capa sql.", "herramientas": ("Read", "Edit", "Bash"),
             "skills": ("criterios", "capa-sql"), "version": 3, "instrucciones": "Primera línea.\n\nÚltima línea."}
    datos.update(cambios)
    return plantilla_writer.Agente(**datos)


def toml_de(texto):
    import tomllib

    return tomllib.loads(texto)


def test_archivos_da_un_toml_por_agente_y_la_config_del_proyecto_al_final():
    capas = importlib.import_module("odd_ws.capas")
    archivo = importlib.import_module("odd_ws.hosts").Archivo
    archivos = m().archivos([agente(), agente(nombre="revisor-sql", herramientas=("Read",))])
    assert [a.ruta for a in archivos] == [capas.agente_codex("writer-sql"), capas.agente_codex("revisor-sql"), capas.CODEX_CONFIG]
    assert all(isinstance(a, archivo) for a in archivos), archivos
    assert [a.fuente for a in archivos] == [capas.agente("writer-sql"), capas.agente("revisor-sql"), None], archivos
    assert archivos[0].contenido == m().toml(agente())
    assert archivos[-1].contenido == 'project_doc_fallback_filenames = ["CLAUDE.md"]\n'
    assert m().archivos([]) == [archivo(capas.CODEX_CONFIG, 'project_doc_fallback_filenames = ["CLAUDE.md"]\n', None)]


def test_los_toml_derivados_llevan_el_arreglo_del_doctor_y_la_config_no():
    archivos = m().archivos([agente(), agente(nombre="revisor-sql")])
    assert [a.arreglo for a in archivos] == ["codex-agentes", "codex-agentes", None], archivos
    assert m().ID_AGENTES == "codex-agentes"


def test_las_claves_de_confianza_son_las_de_codex_para_cada_handler_de_hooks_codex_json():
    datos = json.loads((PLUGIN / "hooks" / "hooks.codex.json").read_text(encoding="utf-8"))
    prefijo = "odd-ws@odd-workspace-template:hooks/hooks.codex.json:"
    assert m().claves_de_confianza(datos, "odd-ws@odd-workspace-template") == [prefijo + clave for clave in (
        "session_start:0:0", "pre_tool_use:0:0", "pre_tool_use:1:0", "pre_tool_use:2:0", "post_tool_use:0:0", "subagent_stop:0:0")]
    dos = {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "a"}, {"type": "command", "command": "b"}]}],
                     "UserPromptSubmit": [{"hooks": []}, {"hooks": [{"type": "command", "command": "c"}]}]}}
    assert m().claves_de_confianza(dos, "p@m") == ["p@m:hooks/hooks.codex.json:pre_tool_use:0:0", "p@m:hooks/hooks.codex.json:pre_tool_use:0:1",
                                                   "p@m:hooks/hooks.codex.json:user_prompt_submit:1:0"]
    assert m().claves_de_confianza({"hooks": "roto"}, "p@m") == [] and m().claves_de_confianza(None, "p@m") == []


def test_el_archivo_de_hooks_es_el_que_declara_el_manifiesto_de_codex():
    manifiesto = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert os.path.normpath(manifiesto["hooks"]) == os.path.normpath(m().ARCHIVO_DE_HOOKS)
    assert (PLUGIN / m().ARCHIVO_DE_HOOKS).is_file()


class Ctx:
    def __init__(self, plugin, home, entorno=None, windows=True):
        self.plugin, self.home, self.entorno, self.windows = Path(plugin), Path(home), entorno or {}, windows


def test_los_hooks_json_de_codex_home_y_de_la_instancia_tambien_se_registran():
    with temporal() as base:
        hook = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python w.py --host codex"}]}]}}
        raiz = base / "instancia"
        for carpeta in (base / "home" / ".codex", raiz / ".codex"):
            carpeta.mkdir(parents=True)
            (carpeta / "hooks.json").write_text(json.dumps(hook), encoding="utf-8")
        (raiz / ".codex" / "config.toml").write_text('model = "x"\n', encoding="utf-8")
        resto = list(m().hooks_registrados(Ctx(PLUGIN, base / "home"), raiz))[6:]
        assert resto == [
            ("%s Stop[0][0]" % (base / "home" / ".codex" / "hooks.json"), ["python", "w.py", "--host", "codex"], False),
            (".codex/hooks.json Stop[0][0]", ["python", "w.py", "--host", "codex"], False),
        ], resto
        (raiz / ".codex" / "hooks.json").write_text("{roto", encoding="utf-8")
        assert list(m().hooks_registrados(Ctx(PLUGIN, base / "home"), raiz))[-1] == (".codex/hooks.json", None, False)


def test_los_comandos_de_windows_se_parten_sin_comerse_las_barras_y_command_windows_es_alias():
    with temporal() as base:
        usuario = base / "home" / ".codex" / "config.toml"
        usuario.parent.mkdir(parents=True)
        usuario.write_text('[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\n'
                           'command = %s\ncommand_windows = %s\n' % (json.dumps(r"python C:\x\y\guard_comandos.py --host gemini"),
                                                                     json.dumps(r'py "C:\a b\w.py" --host=')), encoding="utf-8")
        en_windows = list(m().hooks_registrados(Ctx(PLUGIN, base / "home", windows=True), None))[6:]
        assert en_windows == [
            ("%s Stop[0][0]" % usuario, ["python", "C:/x/y/guard_comandos.py", "--host", "gemini"], False),
            ("%s Stop[0][0] (commandWindows)" % usuario, ["py", "C:/a b/w.py", "--host="], False),
        ], en_windows
        en_posix = list(m().hooks_registrados(Ctx(PLUGIN, base / "home", windows=False), None))[6:]
        assert en_posix[0][1] == ["python", "C:xyguard_comandos.py", "--host", "gemini"], en_posix
        assert en_posix[1] == en_windows[1], en_posix


def test_los_hooks_registrados_salen_del_plugin_y_de_cada_config_toml_de_codex():
    with temporal() as base:
        ctx = Ctx(PLUGIN, base / "home")
        propios = list(m().hooks_registrados(ctx, None))
        assert len(propios) == 6 and all(propio for _, _, propio in propios), propios
        origen, tokens, _ = propios[-1]
        assert origen == "hooks/hooks.codex.json SubagentStop[0][0]", origen
        assert tokens == ["python", "${PLUGIN_ROOT}/scripts/writer_stop.py", "--plazo", "50", "--host", "codex"], tokens
        usuario = base / "home" / ".codex" / "config.toml"
        usuario.parent.mkdir(parents=True)
        usuario.write_text('[hooks.state."x"]\ntrusted_hash = "h"\n\n[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\n'
                           'command = "python \\"C:/a b/w.py\\" --host=codex"\ncommandWindows = "py w.py --host"\n', encoding="utf-8")
        raiz = base / "instancia"
        (raiz / ".codex").mkdir(parents=True)
        (raiz / ".codex" / "config.toml").write_text("roto = [\n", encoding="utf-8")
        resto = list(m().hooks_registrados(ctx, raiz))[6:]
        assert resto == [
            ("%s Stop[0][0]" % usuario, ["python", "C:/a b/w.py", "--host=codex"], False),
            ("%s Stop[0][0] (commandWindows)" % usuario, ["py", "w.py", "--host"], False),
            (".codex/config.toml", None, False),
        ], resto
        sin_plugin = list(m().hooks_registrados(Ctx(base / "sin-plugin", base / "home"), None))
        assert sin_plugin[0] == ("hooks/hooks.codex.json", None, True), sin_plugin
        otra = base / "otra"
        otra.mkdir()
        (otra / "config.toml").write_text('[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "x \'sin cerrar"\n', encoding="utf-8")
        de_otra = list(m().hooks_registrados(Ctx(PLUGIN, base / "home", {"CODEX_HOME": str(otra)}), None))[6:]
        assert de_otra == [("%s Stop[0][0]" % (otra / "config.toml"), ["x", "'sin", "cerrar"], False)], de_otra


def test_el_toml_de_un_agente_tiene_solo_sus_tres_claves_y_un_encabezado_comentado():
    texto = m().toml(agente())
    datos = toml_de(texto)
    assert datos == {
        "name": "writer-sql",
        "description": "Escribe la capa sql.",
        "developer_instructions": datos["developer_instructions"],
    }, datos
    cuerpo = datos["developer_instructions"]
    assert cuerpo.endswith("Primera línea.\n\nÚltima línea.\n"), cuerpo
    assert "**Herramientas de este agente:** Read, Edit, Bash." in cuerpo, cuerpo
    assert "`.claude/skills/criterios/SKILL.md` y `.claude/skills/capa-sql/SKILL.md`" in cuerpo, cuerpo
    lineas = texto.split("\n")
    assert lineas[0].startswith("# ") and ".claude/agents/writer-sql.md" in lineas[0], lineas[0]
    assert lineas[1] == "# odd-ws-plantilla: 3" and lineas[2] == "# odd-ws-hash: " + m().huella(texto), lineas[:3]
    assert lineas[3].startswith("name = "), lineas[3]


def test_el_toml_es_valido_con_cualquier_texto():
    raros = ["'''", '"""', "\\", "\\\n", "a\tb", "\r", "\x00\x01\x1b\x1f", "\x7f", "  y \u0085", "termina en \"",
             "termina en '", "termina en \\", "\ud800 suelto", "ñ y 😀", "]]\n[tabla]\nname = \"x\""]
    for raro in raros:
        datos = toml_de(m().toml(agente(descripcion="d " + raro, instrucciones="i " + raro)))
        esperado = raro.replace("\ud800", "�")
        assert datos["description"] == "d " + esperado, (raro, datos["description"])
        assert datos["developer_instructions"].endswith("i " + esperado + "\n"), (raro, datos["developer_instructions"])
        assert set(datos) == {"name", "description", "developer_instructions"}, raro


def test_el_toml_sin_herramientas_ni_skills_no_inventa_esas_lineas():
    cuerpo = toml_de(m().toml(agente(herramientas=(), skills=())))["developer_instructions"]
    assert "Herramientas" not in cuerpo and "Skills" not in cuerpo and cuerpo == "Primera línea.\n\nÚltima línea.\n", cuerpo
    assert "`.claude/skills/criterios/SKILL.md`." in toml_de(m().toml(agente(skills=("criterios",))))["developer_instructions"]


def test_el_toml_rechaza_un_agente_sin_nombre_description_o_instrucciones():
    for cambio in ({"nombre": ""}, {"nombre": None}, {"descripcion": ""}, {"descripcion": None}, {"descripcion": "  "},
                   {"instrucciones": ""}, {"instrucciones": "\n \n"}, {"nombre": "writer sql"}, {"nombre": "a/b"}):
        try:
            m().toml(agente(**cambio))
        except ValueError:
            continue
        raise AssertionError("armó un TOML con %r" % (cambio,))


def test_el_error_de_un_agente_sin_textos_concuerda_en_genero_y_numero():
    for cambio, mensaje in (({"descripcion": " "}, "el agente necesita una description no vacía para su TOML de Codex"),
                            ({"instrucciones": ""}, "el agente necesita instrucciones no vacías para su TOML de Codex")):
        try:
            m().toml(agente(**cambio))
        except ValueError as error:
            assert str(error) == mensaje, str(error)
            continue
        raise AssertionError("armó un TOML con %r" % (cambio,))


def test_la_huella_del_toml_no_cubre_su_valor_y_tolera_crlf_y_bom():
    texto = m().toml(agente())
    huella = m().huella(texto)
    assert m().huella("﻿" + texto.replace("\n", "\r\n")) == huella
    assert m().huella(texto.replace("# odd-ws-hash: " + huella, "# odd-ws-hash: " + "0" * 64)) == huella
    for editado in (texto.replace("Primera", "Segunda"), texto.replace("# odd-ws-plantilla: 3", "# odd-ws-plantilla: 4"),
                    texto + "model = \"x\"\n"):
        assert m().huella(editado) != huella, editado


def test_los_textos_de_codex_describen_su_realidad():
    textos = m().TEXTOS
    juntos = "\n".join(textos.values())
    for frase in ("apply_patch", "herramienta de shell (en Windows corre PowerShell)", "por la shell", "bitácora", "SKILL.md"):
        assert frase in juntos, frase
    for frase in ("Edit o Write", "con Read", "transcript", "Tu contexto trae precargada", "Bash"):
        assert frase not in juntos, frase
    assert "`Bash`" not in m().HERRAMIENTAS and "herramienta de shell" in m().HERRAMIENTAS, m().HERRAMIENTAS


def test_el_manifiesto_ya_no_deja_p7_ni_p10_para_despues():
    for clave, cita in (("P7", "developer_instructions"), ("P10", "project_doc_fallback_filenames")):
        estado, nota = m().MANIFIESTO[clave]
        assert "(F1d)" not in nota and cita in nota, (clave, nota)
    assert "confianza" in m().MANIFIESTO["P7"][1] and "confianza" in m().MANIFIESTO["P10"][1]


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
