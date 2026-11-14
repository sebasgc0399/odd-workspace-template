import ast
import importlib
import json
import re
import sys
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent
PLUGIN = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
SILENCIO = (0, "", b"")
HOOKS = ("verificar_capa", "writer_guard", "writer_stop", "guard_comandos")
DECISIONES_DE_HOOK = ("Bloquear", "Preguntar", "Contexto", "Seguir")
MOTIVO = "motivo-de-prueba"
HOOKS_CLAUDE = PLUGIN / "hooks" / "hooks.json"
HOOKS_CODEX = PLUGIN / "hooks" / "hooks.codex.json"
HOOKS_PI = PLUGIN / "hooks" / "hooks.pi.json"
MANIFIESTO_CLAUDE = PLUGIN / ".claude-plugin" / "plugin.json"
MANIFIESTO_CODEX = PLUGIN / ".codex-plugin" / "plugin.json"
EVENTOS_DE_HERRAMIENTA = ("PreToolUse", "PostToolUse")
MATCHERS_DE_CODEX = {"Edit|Write": "apply_patch", "Bash|PowerShell": "Bash", "Bash|PowerShell|Edit|Write": "Bash|apply_patch",
                     "Read": None}
SCRIPT_DE_CLAUDE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/scripts/([a-z_]+)\.py")
COMANDO_DE_CODEX = re.compile(r'python3 "\$\{PLUGIN_ROOT\}/scripts/([a-z_]+)\.py" --plazo (\d+) --host codex')
COMANDO_WINDOWS_DE_CODEX = re.compile(r'python "\$\{PLUGIN_ROOT\}/scripts/([a-z_]+)\.py" --plazo (\d+) --host codex')
EVENTOS_DE_PI = {"SessionStart": ("session_start", "session_compact"), "PreToolUse": ("tool_call",), "PostToolUse": ("tool_result",),
                 "SubagentStop": ("agent_before_settle",)}
EVENTOS_DE_HERRAMIENTA_DE_PI = ("tool_call", "tool_result")
HERRAMIENTAS_DE_PI = {"Edit": "edit", "Write": "write", "Read": "read", "Bash": "bash", "PowerShell": "powershell"}
SCRIPT_DE_PI = re.compile(r"([a-z_]+)\.py")


def cap():
    return importlib.import_module("odd_ws.capacidades")


def ev():
    return importlib.import_module("odd_ws.eventos")


def adaptadores():
    registro = importlib.import_module("odd_ws.hosts")
    return [(nombre, importlib.import_module("odd_ws.hosts." + nombre)) for nombre in registro.ADAPTADORES]


def hooks():
    return [(nombre, importlib.import_module(nombre)) for nombre in HOOKS]


def eventos_por_punto():
    C, E = cap(), ev()
    return {
        C.PRE: E.Herramienta(fase="pre", tipo="shell", herramienta="Bash", comando="ls"),
        C.POST: E.Herramienta(fase="post", tipo="edicion", herramienta="Edit", rutas=("/w/a.txt",)),
        C.INICIO: E.InicioSesion(origen="startup"),
        C.FIN_SUBAGENTE: E.FinSubagente(agente="writer-x"),
    }


def decisiones():
    E = ev()
    return (E.Bloquear("x"), E.Preguntar("x"), E.Contexto("x"), E.Seguir("x"))


def test_hay_al_menos_un_adaptador_y_es_el_de_claude_code():
    assert [nombre for nombre, _ in adaptadores()][:1] == ["claude_code"]


def test_los_adaptadores_son_claude_code_codex_y_pi_en_ese_orden():
    assert [nombre for nombre, _ in adaptadores()] == ["claude_code", "codex", "pi"]


def test_los_puntos_de_evento_son_los_cuatro_del_modelo():
    C = cap()
    assert C.PUNTOS_DE_EVENTO == (C.PRE, C.POST, C.INICIO, C.FIN_SUBAGENTE)
    assert set(eventos_por_punto()) == set(C.PUNTOS_DE_EVENTO)


def test_cada_adaptador_responde_justo_lo_que_declara_expresable():
    C, E = cap(), ev()
    for nombre, adaptador in adaptadores():
        assert set(adaptador.EXPRESABLES) <= set(C.PUNTOS_DE_EVENTO), nombre
        for punto, evento in eventos_por_punto().items():
            assert adaptador.responder(evento, E.Permitir()) == SILENCIO, (nombre, punto)
            for decision in decisiones():
                expresable = type(decision) in adaptador.EXPRESABLES.get(punto, ())
                salida = adaptador.responder(evento, decision)
                assert (salida != SILENCIO) == expresable, (
                    "%s: %s en %s %s, pero EXPRESABLES dice %s"
                    % (nombre, type(decision).__name__, punto, "responde" if salida != SILENCIO else "calla", expresable))


def test_cada_hook_emite_solo_lo_que_cada_adaptador_puede_expresar():
    for hook, modulo in hooks():
        for nombre, adaptador in adaptadores():
            for punto, tipos in modulo.EMITE.items():
                for tipo in tipos:
                    assert tipo in adaptador.EXPRESABLES.get(punto, ()), (
                        "%s emite %s en %s y el host %s no lo puede expresar: hay que degradarlo en su adaptador, "
                        "que falle cerrado, y declararlo en su MANIFIESTO" % (hook, tipo.__name__, punto, nombre))


def test_emite_usa_puntos_y_decisiones_del_modelo():
    C, E = cap(), ev()
    validas = {getattr(E, nombre) for nombre in DECISIONES_DE_HOOK}
    for hook, modulo in hooks():
        assert modulo.EMITE, hook
        assert set(modulo.EMITE) <= set(C.PUNTOS_DE_EVENTO), hook
        for tipos in modulo.EMITE.values():
            assert tipos and set(tipos) <= validas, hook


def test_emite_nombra_cada_tipo_de_decision_que_el_hook_construye():
    for hook, modulo in hooks():
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
        construidas = {nodo.func.id for nodo in ast.walk(arbol)
                       if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id in DECISIONES_DE_HOOK}
        declaradas = {tipo.__name__ for tipos in modulo.EMITE.values() for tipo in tipos}
        assert construidas == declaradas, "%s construye %s y EMITE declara %s" % (hook, sorted(construidas), sorted(declaradas))


def test_el_manifiesto_de_cada_adaptador_declara_los_diez_puntos():
    C = cap()
    assert list(C.CAPACIDADES) == ["P%d" % n for n in range(1, 11)]
    for nombre, adaptador in adaptadores():
        assert list(adaptador.MANIFIESTO) == list(C.CAPACIDADES), nombre
        for clave, (estado, nota) in adaptador.MANIFIESTO.items():
            assert estado in C.ESTADOS, (nombre, clave, estado)
            assert isinstance(nota, str), (nombre, clave)
            if estado != C.SOPORTADO:
                assert nota.strip(), "%s: %s es %s y no escribe su fallback" % (nombre, clave, estado)


def test_el_registro_tiene_un_nombre_de_cli_por_adaptador():
    registro = importlib.import_module("odd_ws.hosts")
    assert sorted(registro.NOMBRES.values()) == sorted(registro.ADAPTADORES), registro.NOMBRES
    for cli, nombre in registro.NOMBRES.items():
        assert registro.adaptador(cli) is importlib.import_module("odd_ws.hosts." + nombre), cli


def nativo(adaptador, punto, tipo):
    return tipo in adaptador.EXPRESABLES.get(punto, ()) and tipo not in adaptador.DEGRADACIONES.get(punto, {})


def _enmascarar(valor):
    if isinstance(valor, dict):
        return {clave: _enmascarar(dato) for clave, dato in valor.items()}
    if isinstance(valor, list):
        return [_enmascarar(dato) for dato in valor]
    return MOTIVO if isinstance(valor, str) and MOTIVO in valor else valor


def forma(salida):
    codigo, texto, crudo = salida
    try:
        datos = json.loads(texto) if texto else texto
    except ValueError:
        datos = texto
    return codigo, _enmascarar(datos), MOTIVO if MOTIVO.encode("utf-8") in crudo else crudo


def test_la_forma_de_una_salida_tapa_solo_el_motivo():
    C, E = cap(), ev()
    claude = importlib.import_module("odd_ws.hosts.claude_code")
    evento = eventos_por_punto()[C.PRE]
    bloqueo = forma(claude.responder(evento, E.Bloquear(MOTIVO + " y algo más")))
    assert bloqueo == (2, "", MOTIVO) == forma(claude.responder(evento, E.Bloquear(MOTIVO))), bloqueo
    assert forma(claude.responder(evento, E.Preguntar(MOTIVO))) != bloqueo, "preguntar no tiene la forma de bloquear"
    assert forma(claude.responder(evento, E.Bloquear("otro"))) != bloqueo, "el motivo enmascarado tiene que estar"


def test_cada_degradacion_falla_cerrada_y_se_responde_como_su_destino():
    C, E = cap(), ev()
    for nombre, adaptador in adaptadores():
        assert isinstance(adaptador.DEGRADACIONES, dict), nombre
        assert set(adaptador.DEGRADACIONES) <= set(C.PUNTOS_DE_EVENTO), nombre
        for punto, cambios in adaptador.DEGRADACIONES.items():
            evento = eventos_por_punto()[punto]
            for origen, destino in cambios.items():
                assert origen in adaptador.EXPRESABLES.get(punto, ()), "%s: degrada %s en %s sin declararlo expresable" % (
                    nombre, origen.__name__, punto)
                assert destino is E.Bloquear, "%s: %s en %s se degrada a %s, y solo bloquear falla cerrado" % (
                    nombre, origen.__name__, punto, destino.__name__)
                degradada, propia = adaptador.responder(evento, origen(MOTIVO)), adaptador.responder(evento, destino(MOTIVO))
                assert degradada != SILENCIO and forma(degradada) == forma(propia), (nombre, punto, degradada, propia)


def test_una_decision_que_sale_como_bloqueo_esta_declarada_como_degradada():
    E = ev()
    for nombre, adaptador in adaptadores():
        for punto, evento in eventos_por_punto().items():
            bloqueo = forma(adaptador.responder(evento, E.Bloquear(MOTIVO)))
            for tipo in (E.Preguntar, E.Contexto, E.Seguir):
                salida = adaptador.responder(evento, tipo(MOTIVO))
                if salida == SILENCIO:
                    continue
                declarada = adaptador.DEGRADACIONES.get(punto, {}).get(tipo) is E.Bloquear
                assert (forma(salida) == bloqueo) == declarada, "%s: %s en %s sale %s como un bloqueo y DEGRADACIONES dice %s" % (
                    nombre, tipo.__name__, punto, "igual que" if forma(salida) == bloqueo else "distinto de", declarada)


def test_soportado_implica_que_el_adaptador_expresa_lo_que_pide_sin_degradarlo():
    C = cap()
    assert set(C.REQUISITOS) <= set(C.CAPACIDADES)
    for nombre, adaptador in adaptadores():
        for clave, requisitos in C.REQUISITOS.items():
            cumple = all(nativo(adaptador, punto, tipo) for punto, tipo in requisitos)
            estado, nota = adaptador.MANIFIESTO[clave]
            if estado == C.SOPORTADO:
                assert cumple, "%s: %s está declarado soportado, pero el adaptador no expresa en forma nativa lo que pide" % (
                    nombre, clave)
            else:
                assert nota.strip(), "%s: %s es %s y su nota no explica por qué" % (nombre, clave, estado)


def test_cada_adaptador_dice_si_su_cli_precarga_skills():
    for nombre, adaptador in adaptadores():
        assert isinstance(getattr(adaptador, "PRECARGA_SKILLS", None), bool), (
            "%s: PRECARGA_SKILLS decide si verificar_capa saltea el primer toque de un agente que precarga la skill" % nombre)


def test_p5_soportado_implica_saber_que_toco_el_writer():
    C = cap()
    for nombre, adaptador in adaptadores():
        assert isinstance(adaptador.BITACORA, bool), "%s: BITACORA dice si writer_guard le anota al writer" % nombre
        if adaptador.MANIFIESTO["P5"][0] == C.SOPORTADO:
            for puerto in ("archivos_del_writer", "comandos_del_writer"):
                assert callable(getattr(adaptador, puerto, None)), "%s: P5 soportado sin %s" % (nombre, puerto)


def test_un_requisito_degradado_no_puede_figurar_como_soportado():
    C, E = cap(), ev()
    codex = importlib.import_module("odd_ws.hosts.codex")
    assert not nativo(codex, C.PRE, E.Preguntar) and nativo(codex, C.PRE, E.Bloquear)
    assert codex.MANIFIESTO["P3"][0] == C.DEGRADADO, codex.MANIFIESTO["P3"]
    assert all(nativo(codex, punto, tipo) for punto, tipo in C.REQUISITOS["P5"]), "P5 se expresa en Codex"
    assert codex.MANIFIESTO["P5"][0] == C.SOPORTADO, "y writer_stop corre en Codex con la bitácora (F1b)"
    claude = importlib.import_module("odd_ws.hosts.claude_code")
    for clave, requisitos in C.REQUISITOS.items():
        assert all(nativo(claude, punto, tipo) for punto, tipo in requisitos), clave
        assert claude.MANIFIESTO[clave][0] == C.SOPORTADO, clave
    pi = importlib.import_module("odd_ws.hosts.pi")
    assert not nativo(pi, C.PRE, E.Preguntar) and pi.MANIFIESTO["P3"][0] == C.DEGRADADO, pi.MANIFIESTO["P3"]
    assert all(nativo(pi, punto, tipo) for punto, tipo in C.REQUISITOS["P5"]), "P5 se expresa en Pi"
    assert pi.MANIFIESTO["P5"][0] == C.DEGRADADO, "la compuerta corre solo en el hijo de gentle-shell, con el rodeo de F2c"
    assert pi.MANIFIESTO["P6"][0] == C.DEGRADADO, "el nombre lo pone en la tarea la extensión del padre"


def leer_json(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


def entradas(datos):
    for evento, grupos in datos["hooks"].items():
        for grupo in grupos:
            for hook in grupo["hooks"]:
                yield evento, grupo, hook


def par_de_codex(evento, grupo, hook):
    claves = {"type", "command", "args", "timeout"} | ({"onFailure"} if evento in EVENTOS_DE_HERRAMIENTA else set())
    assert set(hook) == claves and (hook["type"], hook["command"]) == ("command", "python3"), hook
    ruta, bandera, plazo = hook["args"]
    script = SCRIPT_DE_CLAUDE.fullmatch(ruta)
    assert script and bandera == "--plazo", hook
    matcher = grupo["matcher"]
    if evento in EVENTOS_DE_HERRAMIENTA:
        assert matcher in MATCHERS_DE_CODEX, "el matcher %r de Claude Code no tiene su traducción a Codex" % matcher
        matcher = MATCHERS_DE_CODEX[matcher]
    return None if matcher is None else (evento, matcher, script.group(1), plazo, hook["timeout"])


def de_codex(evento, grupo, hook):
    assert set(grupo) == {"matcher", "hooks"}, grupo
    assert set(hook) == {"type", "command", "commandWindows", "timeout"} and hook["type"] == "command", (
        "Codex ignora args, no tiene onFailure y en Windows corre commandWindows: %r" % hook)
    comando = COMANDO_DE_CODEX.fullmatch(hook["command"])
    assert comando, '%r no es python3 "${PLUGIN_ROOT}/scripts/<script>.py" --plazo N --host codex' % hook["command"]
    en_windows = COMANDO_WINDOWS_DE_CODEX.fullmatch(hook["commandWindows"])
    assert en_windows and en_windows.groups() == comando.groups(), (
        "commandWindows es el mismo comando con python, que es lo que hay en Windows: %r" % hook)
    return evento, grupo["matcher"], comando.group(1), comando.group(2), hook["timeout"]


def test_los_hooks_de_claude_code_lanzan_python3_y_los_de_herramienta_bloquean_si_no_arrancan():
    revisados = 0
    for evento, _, hook in entradas(leer_json(HOOKS_CLAUDE)):
        revisados += 1
        assert hook["command"] == "python3", "macOS, Ubuntu y Debian no traen python, y entonces el hook no arranca: %r" % hook
        if evento in EVENTOS_DE_HERRAMIENTA:
            assert hook.get("onFailure") == "block", "sin onFailure, un hook que no arranca deja pasar la herramienta: %r" % hook
        else:
            assert "onFailure" not in hook, "en %s, onFailure no bloquea: %r" % (evento, hook)
    assert revisados == 7, revisados


def test_cada_hook_de_claude_code_tiene_su_par_en_codex():
    esperados = [par for par in (par_de_codex(*entrada) for entrada in entradas(leer_json(HOOKS_CLAUDE))) if par is not None]
    registrados = [de_codex(*entrada) for entrada in entradas(leer_json(HOOKS_CODEX))]
    assert registrados == esperados, "\nCodex:  %r\nespera: %r" % (registrados, esperados)
    assert {script for _, _, script, _, _ in esperados} == set(HOOKS), "los cuatro hooks corren en Codex"


def test_los_hooks_de_codex_solo_traen_description_y_hooks():
    datos = leer_json(HOOKS_CODEX)
    assert set(datos) == {"description", "hooks"}, "Codex rechaza cualquier otra clave arriba: %r" % sorted(datos)
    assert isinstance(datos["description"], str) and datos["description"].strip(), datos["description"]


def pares_de_pi(evento, grupo, hook):
    ruta, _, plazo = hook["args"]
    script = SCRIPT_DE_CLAUDE.fullmatch(ruta).group(1)
    herramientas = None
    if evento in EVENTOS_DE_HERRAMIENTA:
        nombres = grupo["matcher"].split("|")
        assert all(nombre in HERRAMIENTAS_DE_PI for nombre in nombres), (
            "el matcher %r de Claude Code no tiene su traducción a Pi" % grupo["matcher"])
        herramientas = [HERRAMIENTAS_DE_PI[nombre] for nombre in nombres]
    return [(de_pi, herramientas, script, plazo, hook["timeout"]) for de_pi in EVENTOS_DE_PI[evento]]


def de_pi(evento, grupo, hook):
    claves = {"tools", "hooks"} if evento in EVENTOS_DE_HERRAMIENTA_DE_PI else {"hooks"}
    assert set(grupo) == claves, "un grupo de %s lleva %s: %r" % (evento, sorted(claves), grupo)
    if "tools" in grupo:
        assert grupo["tools"] and all(isinstance(nombre, str) for nombre in grupo["tools"]), grupo
    assert set(hook) == {"script", "args", "timeout"}, "cada hook de Pi es script, args y timeout, sin comando que partir: %r" % hook
    script = SCRIPT_DE_PI.fullmatch(hook["script"])
    assert script, "script es el nombre del .py en scripts/: %r" % hook
    argumentos = hook["args"]
    assert (len(argumentos), argumentos[0], argumentos[2:]) == (4, "--plazo", ["--host", "pi"]) and argumentos[1].isdigit(), (
        "los args de Pi son --plazo N --host pi: %r" % hook)
    assert isinstance(hook["timeout"], int) and hook["timeout"] > int(argumentos[1]), "el timeout va en segundos, sobre el plazo: %r" % hook
    return evento, grupo.get("tools"), script.group(1), argumentos[1], hook["timeout"]


def test_cada_hook_de_claude_code_tiene_su_par_en_pi():
    esperados = [par for entrada in entradas(leer_json(HOOKS_CLAUDE)) for par in pares_de_pi(*entrada)]
    registrados = [de_pi(*entrada) for entrada in entradas(leer_json(HOOKS_PI))]
    assert registrados == esperados, "\nPi:     %r\nespera: %r" % (registrados, esperados)
    assert {script for _, _, script, _, _ in esperados} == set(HOOKS), "los cuatro hooks corren en Pi"
    cierre = [par for par in registrados if par[2] == "writer_stop"]
    assert cierre == [("agent_before_settle", None, "writer_stop", "50", 60)], cierre


def test_la_regex_de_los_writers_de_pi_es_el_matcher_de_subagent_stop():
    regex = "^%s$" % importlib.import_module("odd_ws.capas").WRITER_RE.pattern
    for ruta in (HOOKS_CLAUDE, HOOKS_CODEX):
        matchers = [grupo["matcher"] for evento, grupo, _ in entradas(leer_json(ruta)) if evento == "SubagentStop"]
        assert matchers == [regex], (ruta.name, matchers)
    assert leer_json(HOOKS_PI)["writer"] == regex, (
        "el shim marca la tarea de subagent_run y corre la compuerta del hijo con la regex de hooks.pi.json: %r"
        % leer_json(HOOKS_PI).get("writer"))
    assert [grupo for evento, grupo, _ in entradas(leer_json(HOOKS_PI)) if evento == "agent_before_settle"] == [
        {"hooks": [{"script": "writer_stop.py", "args": ["--plazo", "50", "--host", "pi"], "timeout": 60}]}]


def test_los_tres_archivos_de_hooks_corren_los_mismos_scripts_con_el_mismo_plazo_y_timeout():
    def juego(pares):
        return sorted({(script, plazo, timeout) for script, plazo, timeout in pares})

    claude = juego((SCRIPT_DE_CLAUDE.fullmatch(hook["args"][0]).group(1), hook["args"][2], hook["timeout"])
                   for _, _, hook in entradas(leer_json(HOOKS_CLAUDE)))
    codex = juego(de_codex(*entrada)[2:] for entrada in entradas(leer_json(HOOKS_CODEX)))
    pi = juego(de_pi(*entrada)[2:] for entrada in entradas(leer_json(HOOKS_PI)))
    assert claude == codex, (claude, codex)
    assert pi == claude, (pi, claude)


def test_los_hooks_de_pi_traen_el_python_de_cada_sistema_y_es_el_de_su_adaptador():
    datos = leer_json(HOOKS_PI)
    assert set(datos) == {"description", "python", "pythonWindows", "writer", "hooks"}, sorted(datos)
    assert isinstance(datos["description"], str) and "shim" in datos["description"] and "writer" in datos["description"], datos["description"]
    assert list(datos["hooks"]) == ["session_start", "session_compact", "tool_call", "tool_result", "agent_before_settle"], list(datos["hooks"])
    pi = importlib.import_module("odd_ws.hosts.pi")
    assert (datos["python"], datos["pythonWindows"]) == (pi.PYTHON, pi.PYTHON_EN_WINDOWS), (
        "el shim lanza el python de hooks.pi.json, y el doctor revisa el de pi.py: tienen que ser el mismo")
    assert pi.ARCHIVO_DE_HOOKS == "hooks/hooks.pi.json" and (PLUGIN / pi.ARCHIVO_DE_HOOKS).resolve() == HOOKS_PI.resolve()


def test_el_manifiesto_de_codex_es_el_de_claude_code_con_sus_hooks():
    claude, codex = leer_json(MANIFIESTO_CLAUDE), leer_json(MANIFIESTO_CODEX)
    assert codex["version"] == claude["version"], "las dos versiones tienen que subir juntas: %r" % (
        (codex.get("version"), claude.get("version")),)
    assert (codex["name"], codex["description"]) == (claude["name"], claude["description"]), codex
    assert codex["interface"] == {"displayName": "ODD Workspace"}, codex.get("interface")
    hooks = codex["hooks"]
    assert hooks.startswith("./") and (PLUGIN / hooks).resolve() == HOOKS_CODEX.resolve() and HOOKS_CODEX.is_file(), hooks
    assert "skills" not in codex, "sin skills, Codex descubre skills/ solo"
    assert not (PLUGIN / "plugin.json").exists(), "un plugin.json en la raíz gana sobre los dos y apaga los hooks"


def test_cada_adaptador_tiene_su_puerto_de_generacion_con_los_mismos_marcadores():
    marcadores = None
    for nombre, adaptador in adaptadores():
        assert callable(adaptador.archivos), nombre
        assert isinstance(adaptador.TEXTOS, dict) and adaptador.TEXTOS, nombre
        for marca, valor in adaptador.TEXTOS.items():
            assert re.fullmatch(r"\{\{host:[a-z][a-z0-9-]*\}\}", marca), (nombre, marca)
            assert isinstance(valor, str) and valor.strip() and "{{host:" not in valor, (nombre, marca)
        marcadores = set(adaptador.TEXTOS) if marcadores is None else marcadores
        assert set(adaptador.TEXTOS) == marcadores, (nombre, set(adaptador.TEXTOS) ^ marcadores)
    assert importlib.import_module("odd_ws.hosts").FUENTE == "claude-code"


def test_cada_adaptador_declara_el_python_que_lanzan_sus_hooks_en_cada_sistema():
    lanzados = {}
    for nombre, adaptador in adaptadores():
        for windows in (False, True):
            ctx = types.SimpleNamespace(plugin=PLUGIN, home=PLUGIN / "sin-home", entorno={}, windows=windows)
            propios = [(origen, tokens) for origen, tokens, propio in adaptador.hooks_registrados(ctx, None) if propio]
            assert propios and all(tokens for _, tokens in propios), (nombre, windows, propios)
            en_windows = {tokens[0] for origen, tokens in propios if origen.endswith(" (commandWindows)")}
            comunes = {tokens[0] for origen, tokens in propios if not origen.endswith(" (commandWindows)")}
            if windows:
                assert (en_windows or comunes) == {adaptador.PYTHON_EN_WINDOWS}, (nombre, en_windows, comunes, adaptador.PYTHON_EN_WINDOWS)
            else:
                assert comunes == {adaptador.PYTHON}, (nombre, comunes, adaptador.PYTHON)
        lanzados[nombre] = (adaptador.PYTHON, adaptador.PYTHON_EN_WINDOWS)
    assert lanzados == {"claude_code": ("python3", "python3"), "codex": ("python3", "python"), "pi": ("python3", "python")}, lanzados


def test_cada_adaptador_tiene_su_puerto_del_doctor_con_su_archivo_de_hooks_en_el_plugin():
    archivos = {}
    for nombre, adaptador in adaptadores():
        assert callable(adaptador.version) and callable(adaptador.chequeos) and callable(adaptador.hooks_registrados), nombre
        assert (PLUGIN / adaptador.ARCHIVO_DE_HOOKS).is_file(), (nombre, adaptador.ARCHIVO_DE_HOOKS)
        archivos[nombre] = adaptador.ARCHIVO_DE_HOOKS
    assert archivos == {"claude_code": "hooks/hooks.json", "codex": "hooks/hooks.codex.json", "pi": "hooks/hooks.pi.json"}, archivos


def test_cada_adaptador_declara_su_memoria_y_soportado_implica_el_puerto_que_la_resuelve():
    C = cap()
    estados = {}
    for nombre, adaptador in adaptadores():
        estado, nota = getattr(adaptador, "MEMORIAS", (None, None))
        assert estado in C.ESTADOS and isinstance(nota, str) and nota.strip(), (
            "%s: MEMORIAS dice si el host tiene la memoria en archivos que lee memorias.py, con su nota" % nombre)
        resuelve = callable(getattr(adaptador, "directorio_de_memorias", None))
        assert resuelve == (estado == C.SOPORTADO), "%s: MEMORIAS %s y directorio_de_memorias %s" % (
            nombre, estado, "existe" if resuelve else "falta")
        estados[nombre] = estado
    assert estados == {"claude_code": C.SOPORTADO, "codex": C.NO_DISPONIBLE, "pi": C.NO_DISPONIBLE}, estados


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
