import contextlib
import importlib.util
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
PLUGIN = AQUI.parent
_RUTA = AQUI / "writer_stop.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
SILENCIO = (0, "", b"")

from odd_ws import capas as convencion  # noqa: E402
from odd_ws import comun  # noqa: E402
from odd_ws.comun import plazo_de  # noqa: E402
from odd_ws.eventos import FinSubagente  # noqa: E402
from odd_ws.hosts import claude_code as anfitrion  # noqa: E402


def _cargar():
    spec = importlib.util.spec_from_file_location("writer_stop", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


W = _cargar() if _RUTA.exists() else None

STUB_MALO = '''def verificar(ctx):
    out = []
    for n, t in ctx["agregadas"]:
        if "MALO" in t:
            out.append({"id": "T-02", "modo": "bloqueo" if "BLOQ" in t else "aviso", "severidad": "CRITICAL",
                        "linea": n, "fragmento": "MALO", "mensaje": "est\\u00e1 mal \\u2192 as\\u00ed"})
    return out
'''
STUB_EXPLOTA = '''def verificar(ctx):
    raise SystemExit(7)
'''
STUB_LENTO = '''import time
def verificar(ctx):
    limite = ctx["limite"]
    time.sleep(5 if limite is None else max(0.0, limite - time.monotonic()))
    return []
'''


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    base = Path(tempfile.mkdtemp(prefix="writer-stop-test-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, onexc=_quitar)
        if base.exists():
            SOBRANTES.append(str(base))


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "core.autocrlf=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno_sin_git())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def escribir(raiz, rel, texto):
    p = Path(raiz) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)
    return p


def repo_web(base, archivos):
    repo = Path(base) / "equipo" / "web"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    for rel, texto in archivos.items():
        escribir(repo, rel, texto)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return repo


def instancia(base, modulo=STUB_MALO):
    inst = Path(base) / "inst"
    repo = Path(base) / "equipo" / "web"
    repo.mkdir(parents=True, exist_ok=True)
    config = {"schema_version": 1, "repos": {"web": {}}, "layers": {"web": {"extensions": [".cs"], "repos": ["web"]}}}
    escribir(inst, "workspace.config.json", json.dumps(config))
    escribir(inst, "workspace.local.json", json.dumps({"repos": {"web": {"path": str(repo)}}}))
    if modulo is not None:
        escribir(inst, convencion.chequeo("web"), modulo)
    return inst


def transcript(base, herramientas, nombre="agent-1.jsonl", basura=True):
    lineas = [json.dumps({"type": "user", "message": {"role": "user", "content": "haz esto"}})]
    for nombre_h, entrada in herramientas:
        lineas.append(json.dumps({"type": "assistant", "agentId": "a1", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "voy"}, {"type": "tool_use", "id": "t", "name": nombre_h, "input": entrada}]}}))
        lineas.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}))
    if basura:
        lineas.insert(2, "{esto no es json")
        lineas.append("")
    p = Path(base) / nombre
    p.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return p


def resultado(estado="ok", **sobre):
    campos = {
        "estado": estado, "regla": "ninguna", "intento": "ninguno", "presupuesto": "B.cs, techo 20 líneas",
        "reales": "lo completa la compuerta", "arbol": "sucio (B.cs, 1 hunk)",
        "verificacion": "- python -m unittest: 12 pasan, 0 fallan",
        "limites": "- no corrió contra la base real, solo contra los datos de prueba",
    }
    campos.update(sobre)
    cuerpo = "\n".join("%s: %s" % (k, v) if k not in ("verificacion", "limites") else "%s:\n%s" % (k, v)
                       for k, v in campos.items() if v is not None)
    return "Listo, cambié lo pedido.\n\n## Resultado\n%s\n\n## Key Learnings\n1. Algo aprendido que sirve después.\n" % cuerpo


def evento(trans, mensaje, activo=False, sesion="sesion1", agente="a1b2", **extra):
    e = {"hook_event_name": "SubagentStop", "session_id": sesion, "agent_id": agente, "agent_type": "writer-web",
         "agent_transcript_path": str(trans), "last_assistant_message": mensaje, "stop_hook_active": activo, "cwd": ""}
    e.update(extra)
    return e


def correr(e, inst, **extra):
    return W.correr(e, raiz=str(inst), **extra)


def fin(trans):
    return FinSubagente(agente="writer-web", id_agente="a1b2", sesion="sesion1", transcript=trans)


def tocados(trans):
    archivos, faltas = W.archivos_tocados(fin(trans), None, anfitrion)
    assert faltas == [], faltas
    return archivos


def escritos(trans):
    return W.escritos_por_bash(fin(trans), None, anfitrion)


def estado_escrito(inst, sesion="sesion1", agente="a1b2"):
    p = Path(inst) / convencion.ESTADO_WRITERS / sesion / ("%s.json" % agente)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def bloqueo(salida):
    try:
        d = json.loads(salida)
    except ValueError:
        return None
    return d.get("reason") if isinstance(d, dict) and d.get("decision") == "block" else None


def negado_en_codex(salida):
    codigo, texto, error = salida
    if (codigo, error) != (0, b"") or not texto:
        return None
    try:
        decision = json.loads(texto)
    except ValueError:
        return None
    decision = decision.get("hookSpecificOutput") if isinstance(decision, dict) else None
    if not isinstance(decision, dict) or (decision.get("hookEventName"), decision.get("permissionDecision")) != ("PreToolUse", "deny"):
        return None
    return decision.get("permissionDecisionReason")


def escenario(base, nuevo_texto="a\nB\nc\ny = MALO BLOQ;\n", extra=None, modulo=STUB_MALO):
    repo = repo_web(base, {"Core/A/B.cs": "a\nb\nc\n"})
    escribir(repo, "Core/A/B.cs", nuevo_texto)
    for rel, texto in (extra or {}).items():
        escribir(repo, rel, texto)
    return repo, repo / "Core" / "A" / "B.cs", instancia(base, modulo)


def hook(entrada, inst=None, args=("--plazo", "50")):
    env = _entorno_sin_git()
    env.pop("CLAUDE_PROJECT_DIR", None)
    if inst is not None:
        env["CLAUDE_PROJECT_DIR"] = str(inst)
    return subprocess.run([sys.executable, str(_RUTA), *args], input=entrada, capture_output=True, env=env,
                          cwd=str(inst) if inst is not None else None, timeout=120)


def test_s20_solo_actua_para_un_writer():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        e = evento(t, "sin formato")
        assert bloqueo(correr(e, inst)[1]) is not None, "un writer sin formato sigue bloqueando"
        for writer in ("writer-sql", "writer-web", "writer-a-b", "writer-9", "writer-x-"):
            assert correr(dict(e, agent_type=writer, agent_id="w" + re.sub(r"\W", "", writer)), inst)[1] != "", writer
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        e = evento(t, "sin formato")
        sin = {k: v for k, v in e.items() if k != "agent_type"}
        ajenos = ("Explore", "revisor-web", "", None, 3, ["writer-web"], "writer-", "writer-Web", "Writer-web",
                  "xwriter-web", "writer--x", "writer-web ", "writer-web\n", "odd-ws:writer-web", "writer_web")
        for caso in [sin] + [dict(e, agent_type=a) for a in ajenos]:
            assert correr(caso, inst) == SILENCIO, caso.get("agent_type")
        assert not (inst / convencion.ESTADO_WRITERS).exists(), "un ajeno no escribe sidecar"


def test_s20_main_como_hook_real_con_un_ajeno():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        e = evento(t, "sin formato", agente="ajeno1", agent_type="revisor-web")
        r = hook(json.dumps(e).encode("utf-8"), inst)
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r
        assert not (inst / convencion.ESTADO_WRITERS).exists()


def test_archivos_tocados_solo_edit_y_write_en_orden_y_sin_repetir():
    with temporal() as base:
        t = transcript(base, [
            ("Read", {"file_path": "C:/x/leido.cs"}), ("Edit", {"file_path": "C:/x/a.cs", "old_string": "a", "new_string": "b"}),
            ("Bash", {"command": "echo hola > C:/x/c.cs"}), ("Write", {"file_path": "C:/x/b.cs", "content": "z"}),
            ("Edit", {"file_path": "C:/x/a.cs", "old_string": "b", "new_string": "c"}), ("MultiEdit", {"file_path": "C:/x/m.cs", "edits": []}),
            ("Edit", {"old_string": "sin ruta"}), ("Write", {"file_path": 7}),
        ])
        assert tocados(t) == ["C:/x/a.cs", "C:/x/b.cs", "C:/x/m.cs"], tocados(t)
        assert tocados(base / "no-existe.jsonl") == []
        assert tocados(None) == [] and tocados(5) == []
        (base / "vacio.jsonl").write_bytes(b"")
        assert tocados(base / "vacio.jsonl") == []
        (base / "bin.jsonl").write_bytes(b"\xff\xfe\x00{\n\x80")
        assert tocados(base / "bin.jsonl") == []


def test_usos_devuelve_nombre_y_entrada_en_orden_y_none_si_no_hay_transcripcion():
    with temporal() as base:
        t = transcript(base, [
            ("Read", {"file_path": "a"}), ("Edit", {"file_path": "b"}), ("Bash", {"command": "ls"}),
            ("Write", {"file_path": "c"}), ("Edit", {"file_path": "b"}), ("Edit", "no es dict"), ("Edit", None),
        ])
        assert anfitrion.usos(t, ("Edit", "Write")) == [("Edit", {"file_path": "b"}), ("Write", {"file_path": "c"}), ("Edit", {"file_path": "b"})]
        assert anfitrion.usos(str(t), ("Bash", "PowerShell")) == [("Bash", {"command": "ls"})]
        assert anfitrion.usos(t, ()) == []
        assert anfitrion.usos(t, ("Grep",)) == []
        for no_ruta in (None, 5, ["x"], b"bytes"):
            assert anfitrion.usos(no_ruta, ("Edit",)) is None, no_ruta
        assert anfitrion.usos(base / "no-existe.jsonl", ("Edit",)) is None
        (base / "mixto.jsonl").write_bytes(
            b'{"message": 5}\n[1]\n{"message": {"content": "texto"}}\n{"message": {"content": [7, {"type": "tool_use", "name": "Edit", "input": {"file_path": "x\xe9"}},'
            b' {"type": "tool_use", "name": "Edit"}, {"type": "text", "name": "Edit", "input": {"a": 1}}]}}\n{"message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"cortada')
        assert anfitrion.usos(base / "mixto.jsonl", ("Edit",)) == [("Edit", {"file_path": "x�"})]


def test_resultado_valido_para_los_tres_estados():
    for estado in ("ok", "partial", "blocked"):
        campos, errores = W.parsear_resultado(resultado(estado))
        assert errores == [], (estado, errores)
        assert campos.get("estado") == estado and campos.get("regla") == "ninguna", campos
    _, errores = W.parsear_resultado(resultado("blocked", regla="T-12 (chequeo de capa)", intento="agregue el log en el CATCH de B.cs",
                                               arbol="sin cambios", verificacion="- normalizar_sql.py --check: 1 hallazgo\n- python -m unittest: no corrió"))
    assert errores == [], errores
    _, errores = W.parsear_resultado("## Resultado\n- estado: ok\n- regla: ninguna\n- intento: ninguno\n- presupuesto: B.cs 10\n"
                                     "- reales: x\n- arbol: sin cambios\n- verificacion:\n  - cmd: ok\n- limites:\n  - no cubre Windows\n")
    assert errores == [], "tolera las viñetas de lista: %r" % errores
    _, errores = W.parsear_resultado(resultado("ok", verificacion="- a: uno\n- b: dos") + "\n## Otra cosa\nestado: raro\n")
    assert errores == [], "el bloque termina en el siguiente encabezado: %r" % errores


def test_resultado_invalido_dice_que_falta():
    casos = [
        ("sin bloque", "Listo, todo bien.", "## Resultado"),
        ("mensaje vacio", "", "## Resultado"),
        ("mensaje que no es texto", None, "## Resultado"),
        ("estado desconocido", resultado("terminado"), "estado"),
        ("estado en blanco", resultado(""), "estado"),
        ("sin regla", resultado(regla=None), "regla"),
        ("regla vacia", resultado(regla=""), "regla"),
        ("sin intento", resultado(intento=None), "intento"),
        ("sin presupuesto", resultado(presupuesto=None), "presupuesto"),
        ("sin reales", resultado(reales=None), "reales"),
        ("sin arbol", resultado(arbol=None), "arbol"),
        ("arbol con otro texto", resultado(arbol="revertido"), "arbol"),
        ("arbol sucio sin detalle", resultado(arbol="sucio"), "arbol"),
        ("arbol con placeholder", resultado(arbol="sucio (<archivos y hunks>)"), "arbol"),
        ("presupuesto con placeholder", resultado(presupuesto="<archivos y techo de líneas>"), "presupuesto"),
        ("sin verificacion", resultado(verificacion=None), "verificacion"),
        ("verificacion sin entradas", resultado(verificacion=""), "verificacion"),
        ("verificacion sin resultado", resultado(verificacion="- python -m unittest"), "verificacion"),
        ("verificacion con la plantilla", resultado(verificacion="- <comando>: <resultado observado>"), "verificacion"),
        ("sin limites", resultado(limites=None), "limites"),
        ("limites sin entradas", resultado(limites=""), "limites"),
        ("limites que solo dice ninguno", resultado(limites="- ninguno"), "limites"),
        ("limites que solo dice ninguna", resultado(limites="- Ninguna."), "limites"),
        ("limites con ninguno entre comillas", resultado(limites="- `ninguno`\n- **ninguna**"), "limites"),
        ("limites con ninguno entre comillas de texto", resultado(limites="- \"ninguno\"\n- «ninguna»\n- “Ninguno.”"), "limites"),
        ("limites en la misma linea con ninguno", resultado(limites=None).replace("\n\n## Key", "\nlimites: ninguno\n\n## Key"), "limites"),
        ("limites con la plantilla", resultado(limites="- <qué no demuestra la verificación>"), "limites"),
        ("el bloque cortado a mitad", "## Resultado\nestado: ok\n", "regla"),
    ]
    for etiqueta, mensaje, esperado in casos:
        _, errores = W.parsear_resultado(mensaje)
        assert errores and any(esperado in e for e in errores), (etiqueta, esperado, errores)
    _, errores = W.parsear_resultado("## Resultado\nestado: raro\n")
    assert len(errores) >= 5, "junta todo lo que falta, no solo lo primero: %r" % errores
    ultimo = "## Resultado\nestado: raro\n\ntexto\n\n" + resultado("ok")
    assert W.parsear_resultado(ultimo)[1] == [], "vale el ultimo bloque ## Resultado"


def test_limites_vale_en_los_tres_estados_y_queda_en_lo_declarado():
    for estado in ("ok", "partial", "blocked"):
        campos, errores = W.parsear_resultado(resultado(estado, limites="- no cubre Windows\n- no probó la integración con la API"))
        assert errores == [], (estado, errores)
        assert campos["limites"] == ["no cubre Windows", "no probó la integración con la API"], campos
    en_linea = resultado(limites=None).replace("\n\n## Key", "\nlimites: no cubre otro sistema operativo\n\n## Key")
    campos, errores = W.parsear_resultado(en_linea)
    assert errores == [] and campos["limites"] == ["no cubre otro sistema operativo"], (campos, errores)
    _, errores = W.parsear_resultado(resultado(limites="- ninguno\n- no cubre datos reales"))
    assert errores == [], "un límite real junto a «ninguno» vale: %r" % errores
    campos, _ = W.parsear_resultado(resultado(limites="- no cubre Windows"))
    assert campos["verificacion"] == ["python -m unittest: 12 pasan, 0 fallan"], "verificacion no se mezcla con limites: %r" % campos


def test_la_plantilla_es_un_bloque_resultado_que_no_valida():
    assert W.PLANTILLA.startswith("## Resultado\n"), W.PLANTILLA[:20]
    assert W.PLANTILLA.endswith("\nlimites:\n- <qué no demuestra la verificación>"), W.PLANTILLA[-80:]
    for campo in ("estado", "regla", "intento", "presupuesto", "reales", "arbol", "verificacion", "limites"):
        assert "\n%s:" % campo in W.PLANTILLA, campo
    assert W.parsear_resultado(W.PLANTILLA)[1] != [], "copiar la plantilla sin completar no valida"


def test_lineas_reales_trackeado_nuevo_y_fuera_de_repo():
    with temporal() as base:
        repo, archivo, inst = escenario(base, extra={"Core/A/Nuevo.cs": "uno\ndos\ntres\n"})
        fuera = escribir(base, "suelto/x.txt", "hola\n")
        datos = W.lineas_reales([archivo, repo / "Core" / "A" / "Nuevo.cs", fuera, repo / "Core" / "A" / "Borrado.cs"])
        por = {Path(d["ruta"]).name: d for d in datos}
        assert "B.cs" in por and (por["B.cs"]["agregadas"], por["B.cs"]["quitadas"]) == (2, 1), por.get("B.cs")
        assert por["B.cs"]["relativa"] == "Core/A/B.cs", por["B.cs"]
        assert "Nuevo.cs" in por and (por["Nuevo.cs"]["agregadas"], por["Nuevo.cs"]["quitadas"]) == (3, 0), por.get("Nuevo.cs")
        assert "x.txt" not in por and "Borrado.cs" not in por, sorted(por)


def test_lineas_reales_nunca_tocan_el_indice_ni_el_working_tree():
    with temporal() as base:
        repo, archivo, inst = escenario(base, extra={"Core/A/Nuevo.cs": "uno\ndos\n"})
        indice = repo / ".git" / "index"
        antes_indice = indice.read_bytes()
        antes_stage = git(repo, "ls-files", "--stage")
        antes_estado = git(repo, "status", "--porcelain")
        antes_texto = archivo.read_bytes()
        entorno = dict(os.environ)
        os.environ["GIT_INDEX_FILE"] = str(base / "indice-ajeno")
        os.environ["GIT_DIR"] = str(base / "ajeno.git")
        try:
            datos = W.lineas_reales([archivo, repo / "Core" / "A" / "Nuevo.cs"])
        finally:
            os.environ.clear()
            os.environ.update(entorno)
        assert len(datos) == 2, "con GIT_INDEX_FILE y GIT_DIR heredados igual mide el repo del archivo: %r" % datos
        assert indice.read_bytes() == antes_indice
        assert git(repo, "ls-files", "--stage") == antes_stage
        assert git(repo, "status", "--porcelain") == antes_estado
        assert archivo.read_bytes() == antes_texto
        assert not (base / "indice-ajeno").exists()


def test_bloquea_una_vez_con_todo_junto_y_las_lineas_reales():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        c, o, e = correr(evento(t, resultado("ok", arbol="sin cambios", verificacion="- python -m unittest")), inst)
        razon = bloqueo(o)
        assert c == 0 and e == b"" and razon is not None, (c, o, e)
        assert "[T-02" in razon and "Core/A/B.cs" in razon, razon
        assert "está mal" in razon, razon
        assert "+2" in razon and "-1" in razon, razon
        assert "arbol" in razon and "verificacion" in razon, razon
        assert W.PLANTILLA in razon
        assert "Edit" in razon or "corrige" in razon.lower()
        est = estado_escrito(inst)
        assert est is not None
        assert est["agent_type"] == "writer-web" and est["stop_hook_active"] is False, est
        assert est["formato_ok"] is False and est["archivos"] == [str(archivo)], est
        assert [b["id"] for b in est["bloqueos"]] == ["T-02"], est["bloqueos"]
        assert [(n["relativa"], n["agregadas"], n["quitadas"]) for n in est["numstat"]] == [("Core/A/B.cs", 2, 1)], est["numstat"]


def test_con_stop_hook_active_deja_pasar_y_escribe_la_verdad():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Write", {"file_path": str(archivo)})])
        e = evento(t, resultado("blocked", regla="T-02", intento="no pude", arbol="sucio (B.cs, 1 hunk)"))
        assert bloqueo(correr(e, inst)[1]) is not None, "el primer stop bloquea"
        assert correr(dict(e, stop_hook_active=True), inst) == SILENCIO, "el segundo stop deja pasar aunque siga el bloqueo"
        est = estado_escrito(inst)
        assert est is not None and est["stop_hook_active"] is True, est
        assert est["formato_ok"] is True and [b["id"] for b in est["bloqueos"]] == ["T-02"], est
        assert est["resultado"]["estado"] == "blocked", est["resultado"]


def test_un_writer_de_la_plantilla_1_sin_limites_se_come_un_bloqueo_y_el_segundo_cierre_pasa():
    with temporal() as base:
        repo, archivo, inst = escenario(base, nuevo_texto="a\nB\nc\nlimpio\n")
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        e = evento(t, resultado("ok", limites=None))
        razon = bloqueo(correr(e, inst)[1])
        assert razon is not None and "limites" in razon and "\nlimites:\n" in razon, razon
        assert "verificacion" not in razon.split("Cierra con este bloque")[0], "solo falta limites: %s" % razon
        assert correr(dict(e, stop_hook_active=True), inst) == SILENCIO, "el segundo cierre pasa aunque siga sin limites"
        est = estado_escrito(inst)
        assert est["formato_ok"] is False and est["resultado"]["limites"] == [], est
        assert correr(evento(t, resultado("ok")), inst) == SILENCIO, "con limites cierra a la primera"


def test_todo_en_orden_deja_pasar_en_silencio_y_deja_el_estado():
    with temporal() as base:
        repo, archivo, inst = escenario(base, nuevo_texto="a\nB\nc\nlimpio\n")
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        assert correr(evento(t, resultado("ok")), inst) == SILENCIO
        est = estado_escrito(inst)
        assert est and est["formato_ok"] is True and est["bloqueos"] == [] and est["stop_hook_active"] is False, est
        escribir(repo, "Core/A/B.cs", "a\nB\nc\ny = MALO;\n")
        assert correr(evento(t, resultado("ok")), inst) == SILENCIO, "un aviso no bloquea"
        est = estado_escrito(inst)
        assert est and est["bloqueos"] == [] and [a["id"] for a in est["avisos"]] == ["T-02"], est


def test_solo_el_formato_tambien_bloquea_y_sin_archivos_no_mide_nada():
    with temporal() as base:
        inst = instancia(base)
        t = transcript(base, [("Read", {"file_path": "C:/x/a.cs"})])
        razon = bloqueo(correr(evento(t, "Listo."), inst)[1])
        assert razon is not None and "## Resultado" in razon and W.PLANTILLA in razon, razon
        assert "reales" not in razon.split(W.PLANTILLA)[0].lower().replace("`reales:`", ""), "sin archivos no hay lineas reales"
        assert correr(evento(t, resultado("ok", arbol="sin cambios")), inst) == SILENCIO
        est = estado_escrito(inst)
        assert est and est["archivos"] == [] and est["numstat"] == [], est


def test_arbol_sin_cambios_con_lineas_reales_es_incoherente():
    with temporal() as base:
        repo, archivo, inst = escenario(base, nuevo_texto="a\nB\nc\nlimpio\n")
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        razon = bloqueo(correr(evento(t, resultado("ok", arbol="sin cambios")), inst)[1])
        assert razon is not None and "arbol" in razon and "sin cambios" in razon, razon
        assert "+2" in razon, razon


def test_ids_invalidos_o_ausentes_callan_y_no_escriben():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        for sesion, agente in (("../fuera", "a1"), ("s1", "a/b"), ("s1", "a.b"), ("", "a1"), ("s1", ""), (None, "a1"), ("s1", None), (7, "a1")):
            assert correr(evento(t, "Listo.", sesion=sesion, agente=agente), inst) == SILENCIO, (sesion, agente)
        assert not (inst / ".claude" / "estado").exists() and not (base / "fuera").exists()


def test_otros_eventos_y_basura_callan():
    with temporal() as base:
        inst = instancia(base)
        for caso in ({"hook_event_name": "Stop", "session_id": "s1", "agent_id": "a1"}, {"hook_event_name": "PostToolUse"},
                     {"hook_event_name": "PreToolUse", "agent_type": "writer-web", "session_id": "s1", "agent_id": "a1"},
                     {}, [], "no es json", None, 5, b"\xff"):
            assert correr(caso, inst) == SILENCIO, caso
        assert not (inst / ".claude" / "estado").exists()


def test_falla_abierto_ante_cualquier_error_interno():
    with temporal() as base:
        repo, archivo, inst = escenario(base, modulo=STUB_EXPLOTA)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        assert correr(evento(t, resultado("ok")), inst)[0] == 0, "un modulo que sale con SystemExit no tumba la compuerta"
        assert bloqueo(correr(evento(t, resultado("ok")), inst)[1]) is None, "y no bloquea sin poder explicarlo"
        original = W.archivos_tocados
        try:
            W.archivos_tocados = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
            assert correr(evento(t, "Listo."), inst) == SILENCIO, "un error interno: exit 0 en silencio"
        finally:
            W.archivos_tocados = original
        assert correr(evento(base / "no" / "existe.jsonl", "Listo."), inst)[0] == 0, "transcript ilegible no lanza"


def test_la_compuerta_mide_con_el_dispatcher_real_y_una_capa_sin_modulo():
    with temporal() as base:
        repo, archivo, inst = escenario(base, modulo=None)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        assert correr(evento(t, resultado("ok")), inst) == SILENCIO
        est = estado_escrito(inst)
        assert est["bloqueos"] == [] and est["avisos"] == [] and est["errores_internos"] == [], est


def test_main_lee_stdin_y_falla_abierto():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        e = evento(t, "Listo.", sesion="smain", agente="amain")
        r = hook(json.dumps(e).encode("utf-8"), inst)
        salida = r.stdout.decode("ascii", errors="replace")
        assert r.returncode == 0 and r.stderr == b"" and bloqueo(salida) is not None, r
        assert all(b < 128 for b in r.stdout), "stdout es ASCII puro (JSON escapado)"
        assert estado_escrito(inst, "smain", "amain") is not None, "main escribio el estado en la instancia"
    r = hook(b"\xff\xfe basura")
    assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r
    r = hook(b"")
    assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r


def test_b1_lineas_reales_no_reescribe_la_cache_de_stat_del_indice():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        git(repo, "stash", "-q")
        git(repo, "update-index", "--refresh")
        git(repo, "stash", "pop", "-q")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "cambio")
        git(repo, "update-index", "--refresh")
        time.sleep(1.2)
        os.utime(archivo, None)
        indice = repo / ".git" / "index"
        antes = indice.read_bytes()
        datos = W.lineas_reales([archivo])
        assert len(datos) == 1 and (datos[0]["agregadas"], datos[0]["quitadas"]) == (0, 0), datos
        assert indice.read_bytes() == antes, "el .git/index quedo byte a byte igual con el archivo stat-sucio"


def test_e1_el_estado_se_escribe_aunque_no_cargue_verificar_capa():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        original = W._verificar_capa
        try:
            W._verificar_capa = lambda: (_ for _ in ()).throw(ImportError("no carga"))
            r = correr(evento(t, resultado("ok"), activo=True), inst)
        finally:
            W._verificar_capa = original
        assert r == SILENCIO, r
        e = estado_escrito(inst)
        assert e is not None, "el sidecar existe igual"
        assert e["archivos"] == [str(archivo)] and e["stop_hook_active"] is True and e["agent_type"] == "writer-web", e
        assert e["errores_internos"] and "no carga" in " ".join(e["errores_internos"]), e["errores_internos"]


def test_e1_el_estado_se_escribe_aunque_las_lineas_reales_revienten():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        original = W.lineas_reales
        try:
            W.lineas_reales = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom git"))
            r = correr(evento(t, resultado("ok")), inst)
        finally:
            W.lineas_reales = original
        assert r == SILENCIO, "falla abierto y sin bloquear sin poder explicarlo: %r" % (r,)
        e = estado_escrito(inst)
        assert e is not None and e["archivos"] == [str(archivo)], e
        assert "boom git" in " ".join(e["errores_internos"]), e["errores_internos"]


def test_e1_un_error_fuera_de_las_etapas_deja_el_sidecar_parcial():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        original = W.lineas_reales
        try:
            W.lineas_reales = lambda *a, **k: [{"relativa": "x", "agregadas": "x", "quitadas": 0}]
            r = correr(evento(t, resultado("ok")), inst)
        finally:
            W.lineas_reales = original
        assert r == SILENCIO, r
        e = estado_escrito(inst)
        assert e is not None and e["archivos"] == [str(archivo)] and e["formato_ok"] is None, e


def tocar(inst, archivo, herramienta="Edit", sesion="sesion1", agente="a1b2"):
    e = {"hook_event_name": "PreToolUse", "tool_name": herramienta, "session_id": sesion, "agent_id": agente,
         "agent_type": "writer-web", "cwd": str(inst), "tool_input": {"file_path": str(archivo)}}
    return W._guardia().correr(e, raiz=str(inst))


def carpeta_de_fotos(inst, sesion="sesion1", agente="a1b2"):
    return Path(W._guardia().carpeta_fotos(str(inst), sesion, agente))


def numstat_de(est):
    return [(n["relativa"], n["agregadas"], n["quitadas"], n.get("base")) for n in (est or {}).get("numstat", [])]


def test_s9_un_archivo_sucio_antes_del_writer_cuenta_solo_lo_del_writer():
    with temporal() as base:
        repo, archivo, inst = escenario(base, nuevo_texto="a\nb\nc\nSUCIO 1\nSUCIO 2\nSUCIO 3\n")
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        assert tocar(inst, archivo) == SILENCIO, "el primer toque no bloquea"
        escribir(repo, "Core/A/B.cs", "a\nb\nc\nSUCIO 1\nSUCIO 2\nSUCIO 3\nlo del writer\n")
        c, o, e = correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        assert numstat_de(estado_escrito(inst)) == [("Core/A/B.cs", 1, 0, "foto")], numstat_de(estado_escrito(inst))
        razon = bloqueo(o) or ""
        assert "+1 -0" in razon and "contra HEAD" not in razon, razon
        assert W.lineas_reales([archivo])[0]["agregadas"] == 4, "contra HEAD seria +4 (control positivo del instrumento)"


def test_s9_un_archivo_nuevo_cuenta_todo_como_agregado_con_su_marca():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        nuevo = repo / "Core" / "A" / "Nuevo.cs"
        t = transcript(base, [("Write", {"file_path": str(nuevo)})])
        assert tocar(inst, nuevo, "Write") == SILENCIO
        escribir(repo, "Core/A/Nuevo.cs", "uno\ndos\ntres\n")
        correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        assert numstat_de(estado_escrito(inst)) == [("Core/A/Nuevo.cs", 3, 0, "nuevo")], numstat_de(estado_escrito(inst))


def test_s9_un_archivo_sin_foto_cae_a_head_con_su_marca_visible():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        c, o, e = correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        est = estado_escrito(inst) or {}
        assert numstat_de(est) == [("Core/A/B.cs", 2, 1, "HEAD")], numstat_de(est)
        assert "contra HEAD: sin foto" in (bloqueo(o) or ""), bloqueo(o)
        assert est.get("errores_internos") == [], est.get("errores_internos")


def test_s9_si_la_foto_no_se_pudo_escribir_el_edit_pasa_y_la_compuerta_cae_a_head():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        tapon = carpeta_de_fotos(inst)
        tapon.parent.mkdir(parents=True)
        tapon.write_text("x", encoding="utf-8")
        assert tocar(inst, archivo) == SILENCIO, "el Edit no se bloquea si el guard no puede escribir la foto"
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        c, o, e = correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        assert numstat_de(estado_escrito(inst)) == [("Core/A/B.cs", 2, 1, "HEAD")], numstat_de(estado_escrito(inst))
        assert "contra HEAD: sin foto" in (bloqueo(o) or "")


def test_s9_un_archivo_de_mas_de_8_mb_no_tiene_foto_y_cae_a_head():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        grande = escribir(repo, "Core/A/Grande.cs", b"x\n" * (W._guardia().MAX_FOTO // 2 + 1))
        t = transcript(base, [("Edit", {"file_path": str(grande)})])
        assert tocar(inst, grande) == SILENCIO
        carpeta = carpeta_de_fotos(inst)
        assert not carpeta.is_dir() or not any(carpeta.iterdir()), "el guard no saca foto de un archivo de mas de 8 MB"
        escribir(repo, "Core/A/Grande.cs", b"x\n" * (W._guardia().MAX_FOTO // 2 + 1) + b"y\n")
        c, o, e = correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        assert numstat_de(estado_escrito(inst)) == [("Core/A/Grande.cs", W._guardia().MAX_FOTO // 2 + 2, 0, "HEAD")], numstat_de(estado_escrito(inst))
        assert "Core/A/Grande.cs" in (bloqueo(o) or "") and "contra HEAD: sin foto" in (bloqueo(o) or "")


def test_s9_la_segunda_foto_no_pisa_la_primera_al_contar():
    with temporal() as base:
        repo, archivo, inst = escenario(base, nuevo_texto="a\nb\nc\n")
        t = transcript(base, [("Edit", {"file_path": str(archivo)}), ("Edit", {"file_path": str(archivo)})])
        tocar(inst, archivo)
        escribir(repo, "Core/A/B.cs", "a\nb\nc\nprimera\n")
        tocar(inst, archivo)
        escribir(repo, "Core/A/B.cs", "a\nb\nc\nprimera\nsegunda\n")
        correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        assert numstat_de(estado_escrito(inst)) == [("Core/A/B.cs", 2, 0, "foto")], numstat_de(estado_escrito(inst))


@contextlib.contextmanager
def config_de_git(base, autocrlf):
    archivo = escribir(base, "gitconfig-%s" % autocrlf, "[core]\n\tautocrlf = %s\n" % autocrlf)
    previo = {k: os.environ.get(k) for k in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL")}
    os.environ.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(archivo))
    try:
        yield
    finally:
        for k, v in previo.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_s9_lf_a_crlf_no_infla_ni_dispara_sin_foto():
    for autocrlf in ("false", "true"):
        with temporal() as base:
            repo, archivo, inst = escenario(base, nuevo_texto="l1\nl2\nl3\nl4\n")
            t = transcript(base, [("Edit", {"file_path": str(archivo)})])
            tocar(inst, archivo)
            escribir(repo, "Core/A/B.cs", "l1\nl2\nCAMBIO REAL\nl4\n")
            archivo.write_bytes(archivo.read_bytes().replace(b"\n", b"\r\n"))
            with config_de_git(base, autocrlf):
                correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
            assert numstat_de(estado_escrito(inst)) == [("Core/A/B.cs", 1, 1, "foto")], (autocrlf, numstat_de(estado_escrito(inst)))


def _hooks_del_plugin():
    datos = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for evento_, grupos in datos["hooks"].items():
        for grupo in grupos:
            for h in grupo["hooks"]:
                yield evento_, grupo.get("matcher") or "", h


def test_s21_hooks_json_cablea_el_guard_y_la_compuerta():
    guard = [(e, m, h) for e, m, h in _hooks_del_plugin() if h["args"][0] == "${CLAUDE_PLUGIN_ROOT}/scripts/writer_guard.py"]
    assert len(guard) == 1 and guard[0][0] == "PreToolUse", guard
    assert set(guard[0][1].split("|")) == {"Bash", "PowerShell", "Edit", "Write"} and guard[0][2]["timeout"] == 10, guard
    stop = [(e, m, h) for e, m, h in _hooks_del_plugin() if h["args"][0] == "${CLAUDE_PLUGIN_ROOT}/scripts/writer_stop.py"]
    assert len(stop) == 1 and stop[0][0] == "SubagentStop", stop
    evento_, matcher, h = stop[0]
    assert h["type"] == "command" and h["command"] == "python3" and "onFailure" not in h, h
    assert (h["timeout"], plazo_de(h["args"][1:])) == (60, 50), h
    assert plazo_de(h["args"][1:]) <= h["timeout"] - 2, h


def test_el_matcher_de_subagent_stop_es_la_regex_de_los_writers():
    stop = [m for e, m, h in _hooks_del_plugin() if h["args"][0] == "${CLAUDE_PLUGIN_ROOT}/scripts/writer_stop.py"]
    assert stop == ["^%s$" % convencion.WRITER_RE.pattern], stop
    nombres = ("writer-sql", "writer-web", "writer-a-b", "writer-9", "writer-x-", "writer-", "writer-Web", "Writer-web",
               "xwriter-web", "writer--x", "writer-web ", "revisor-web", "odd-ws:writer-web", "writer_web", "Explore")
    for nombre in nombres:
        assert (re.search(stop[0], nombre) is not None) == convencion.es_writer(nombre), nombre


def test_b_las_fotos_se_borran_al_dejar_cerrar_y_se_conservan_al_bloquear():
    with temporal() as base:
        repo, archivo, inst = escenario(base, nuevo_texto="a\nb\nc\n")
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        tocar(inst, archivo)
        escribir(repo, "Core/A/B.cs", "a\nb\nc\nlimpio\n")
        carpeta = carpeta_de_fotos(inst)
        c, o, e = correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        assert bloqueo(o) is not None and carpeta.is_dir(), "si bloquea, el writer sigue y la carpeta de fotos queda"
        c, o, e = correr(evento(t, resultado("ok", arbol="sin cambios"), activo=True), inst)
        assert o == "" and not carpeta.exists(), "con stop_hook_active deja cerrar y borra las fotos: %r" % o
        assert numstat_de(estado_escrito(inst)) == [("Core/A/B.cs", 1, 0, "foto")], numstat_de(estado_escrito(inst))
    with temporal() as base:
        repo, archivo, inst = escenario(base, nuevo_texto="a\nb\nc\n")
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        tocar(inst, archivo)
        escribir(repo, "Core/A/B.cs", "a\nb\nc\nlimpio\n")
        carpeta = carpeta_de_fotos(inst)
        assert correr(evento(t, resultado("ok")), inst) == SILENCIO
        assert not carpeta.exists(), "al dejar cerrar se borran las fotos de ese agente"
        assert numstat_de(estado_escrito(inst)) == [("Core/A/B.cs", 1, 0, "foto")], "el sidecar se queda, con su numstat"


def _bash(comando, herramienta="Bash"):
    return (herramienta, {"command": comando})


def test_s14_lo_escrito_por_bash_va_al_sidecar_como_informacion():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        sal = (base / "salida.txt").as_posix()
        otro = (base / "otro.txt").as_posix()
        solo_edit = transcript(base, [("Edit", {"file_path": str(archivo)})], nombre="a.jsonl")
        con_bash = transcript(base, [("Edit", {"file_path": str(archivo)}), _bash("sed -i s/a/b/ " + sal), _bash("cat " + otro),
                                     _bash("Set-Content " + otro + " x", "PowerShell"), _bash("grep -r x ."), ("Read", {"file_path": "x"})], nombre="b.jsonl")
        r1 = correr(evento(solo_edit, resultado("ok"), sesion="s1"), inst)
        r2 = correr(evento(con_bash, resultado("ok"), sesion="s2"), inst)
        e1, e2 = estado_escrito(inst, "s1"), estado_escrito(inst, "s2")
        assert e1["escritos_por_bash"] == [], e1["escritos_por_bash"]
        assert e2["escritos_por_bash"] == [sal, otro], e2["escritos_por_bash"]
        assert str(archivo) not in e2["escritos_por_bash"]
        assert r1 == r2, (r1, r2)
        for campo in ("numstat", "archivos", "bloqueos", "avisos", "formato_ok", "formato_errores", "resultado"):
            assert e1[campo] == e2[campo], campo
        assert e2["errores_internos"] == [], e2["errores_internos"]


def test_s14_un_cat_no_aparece_y_lo_repetido_no_se_duplica():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        sal = (base / "salida.txt").as_posix()
        t = transcript(base, [_bash("cat " + sal), _bash("echo a > " + sal), _bash("echo b >> " + sal)])
        correr(evento(t, resultado("ok", arbol="sin cambios")), inst)
        assert estado_escrito(inst)["escritos_por_bash"] == [sal], estado_escrito(inst)["escritos_por_bash"]


def test_s14_un_parser_roto_falla_abierto_y_no_cambia_la_decision():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        sal = (base / "salida.txt").as_posix()
        t = transcript(base, [("Edit", {"file_path": str(archivo)}), _bash("sed -i s/a/b/ " + sal)])
        normal = correr(evento(t, resultado("ok"), sesion="s1"), inst)
        guardia = W._guardia()
        original = guardia.destinos
        try:
            guardia.destinos = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("parser roto"))
            roto = correr(evento(t, resultado("ok"), sesion="s2"), inst)
        finally:
            guardia.destinos = original
        assert roto == normal and bloqueo(roto[1]) is not None, "bloquea igual con el parser roto"
        e = estado_escrito(inst, "s2")
        assert e["escritos_por_bash"] == [] and any("parser roto" in x for x in e["errores_internos"]), e
        assert e["numstat"] == estado_escrito(inst, "s1")["numstat"]
        original_guardia = W._guardia
        try:
            W._guardia = lambda: (_ for _ in ()).throw(ImportError("no carga"))
            sin_carga = correr(evento(t, resultado("ok"), sesion="s3"), inst)
        finally:
            W._guardia = original_guardia
        assert bloqueo(sin_carga[1]) is not None, "si el guard no carga, tampoco cambia el bloqueo"
        e3 = estado_escrito(inst, "s3")
        assert e3["escritos_por_bash"] == [] and any("no carga" in x for x in e3["errores_internos"]), e3
        assert numstat_de(e3) == [("Core/A/B.cs", 2, 1, "HEAD")], numstat_de(e3)


def test_s14_transcript_ilegible_o_sin_bash_da_vacio():
    with temporal() as base:
        assert escritos(base / "no" / "existe.jsonl") == [] and escritos(None) == []
        t = transcript(base, [("Read", {"file_path": "x"}), ("Bash", {"command": 5}), ("Bash", {})])
        assert escritos(t) == []


def test_u6d_lo_escrito_por_bash_se_lee_con_el_escape_de_su_herramienta():
    with temporal() as base:
        unida = (base / "dos palabras" / "x.txt").as_posix()
        barra = "cp a.txt " + unida.replace(" ", "\\ ")
        grave = "Copy-Item a.txt " + unida.replace(" ", "` ")
        fallos = []
        for k, (uso, une) in enumerate(((_bash(barra), True), (_bash(barra, "PowerShell"), False),
                                         (_bash(grave, "PowerShell"), True), (_bash(grave), False))):
            vistos = escritos(transcript(base, [uso], nombre="u%d.jsonl" % k))
            if (unida in vistos) != une:
                fallos.append("%s en %s: %r" % (uso[1]["command"], uso[0], vistos))
        assert not fallos, "\n".join(fallos)


def test_p3_sin_instancia_o_con_la_config_rota_calla():
    with temporal() as base:
        repo, archivo, _ = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        suelta = base / "suelta"
        suelta.mkdir()
        assert correr(evento(t, "Listo."), suelta) == SILENCIO, "sin instancia"
        assert not (suelta / ".claude").exists() and not (base / ".claude").exists()
        rota = base / "rota"
        escribir(rota, "workspace.config.json", "{no es json")
        assert correr(evento(t, "Listo."), rota) == SILENCIO, "con la config rota"
        escribir(rota, "workspace.config.json", json.dumps({"schema_version": 99, "repos": {}, "layers": {}}))
        assert correr(evento(t, "Listo."), rota) == SILENCIO, "con una version que no entiende"
        assert not (rota / ".claude").exists()


def test_p5_el_sidecar_va_al_estado_de_los_writers_de_la_instancia():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        sub = inst / "tickets" / "T-1"
        sub.mkdir(parents=True)
        assert bloqueo(correr(evento(t, "Listo."), sub)[1]) is not None, "la raiz se busca subiendo desde el inicio de la sesion"
        assert (inst / convencion.ESTADO_WRITERS / "sesion1" / "a1b2.json").is_file()
        assert not (sub / ".claude").exists()


def _tres_archivos(base, modulo):
    repo = repo_web(base, {"Core/A.cs": "a\n", "Core/B.cs": "b\n", "Core/C.cs": "c\n"})
    archivos = [escribir(repo, "Core/%s.cs" % n, "%s\nnuevo\n" % n.lower()) for n in "ABC"]
    inst = instancia(base, modulo)
    return archivos, inst, transcript(base, [("Edit", {"file_path": str(a)}) for a in archivos])


def test_r4_una_verificacion_que_agota_el_plazo_no_tumba_la_compuerta():
    with temporal() as base:
        archivos, inst, t = _tres_archivos(base, STUB_LENTO)
        antes = time.monotonic()
        c, o, e = correr(evento(t, "Listo."), inst, plazo=3)
        duracion = time.monotonic() - antes
        assert duracion < 3 + 2, "la compuerta responde dentro del plazo mas el margen de P6: %.2f s" % duracion
        assert c == 0 and e == b"" and bloqueo(o) is not None, (c, o, e)
        est = estado_escrito(inst)
        assert sorted(n["relativa"] for n in est["numstat"]) == ["Core/A.cs", "Core/B.cs", "Core/C.cs"], est["numstat"]
        sin_tiempo = [x for x in est["errores_internos"] if "TimeoutExpired" in x]
        assert len(sin_tiempo) == 2 and any("B.cs" in x for x in sin_tiempo) and any("C.cs" in x for x in sin_tiempo), est["errores_internos"]


def test_r4_main_lee_el_plazo_y_responde_antes_del_timeout():
    with temporal() as base:
        archivos, inst, t = _tres_archivos(base, STUB_LENTO)
        antes = time.monotonic()
        r = hook(json.dumps(evento(t, "Listo.")).encode("utf-8"), inst, ("--plazo", "3"))
        duracion = time.monotonic() - antes
        assert duracion < 3 + 2, "con --plazo 3 y un timeout de 5, Claude Code no descartaria la salida: %.2f s" % duracion
        assert r.returncode == 0 and r.stderr == b"" and bloqueo(r.stdout.decode("ascii")) is not None, r


def test_r4_las_lineas_reales_respetan_el_plazo():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        llamadas = []
        original = W.subprocess.run

        def espia(*a, **k):
            llamadas.append(k.get("timeout"))
            return original(*a, **k)

        W.subprocess.run = espia
        try:
            assert W.lineas_reales([archivo], None, time.monotonic() - 1) == []
            assert llamadas == [], "sin tiempo no lanza git: %r" % llamadas
            datos = W.lineas_reales([archivo], None, time.monotonic() + 2)
            assert [(d["agregadas"], d["quitadas"]) for d in datos] == [(2, 1)], datos
            assert llamadas and all(0 < t <= 2 for t in llamadas), llamadas
            del llamadas[:]
            W.lineas_reales([archivo])
            assert llamadas and all(t == W._verificar_capa().TIMEOUT_GIT for t in llamadas), llamadas
        finally:
            W.subprocess.run = original


def test_r4_los_chequeos_reciben_el_limite_de_la_compuerta():
    with temporal() as base:
        repo, archivo, inst = escenario(base, modulo='def verificar(ctx):\n    return [{"id": "T-09", "modo": "aviso", "severidad": "", "linea": None, "fragmento": None, "mensaje": "L=%r" % ctx.get("limite")}]\n')
        t = transcript(base, [("Edit", {"file_path": str(archivo)})])
        antes = time.monotonic()
        correr(evento(t, resultado("ok")), inst, plazo=20)
        aviso = estado_escrito(inst)["avisos"][0]["mensaje"]
        limite = float(aviso.split("L=", 1)[1])
        assert 19 <= limite - antes <= 20.5, limite - antes
        assert W._verificar_capa()._LIMITE is None, "la compuerta no deja el limite colgado en el dispatcher"


@contextlib.contextmanager
def posix():
    from odd_ws.hosts import codex
    previo = codex.SISTEMA
    codex.SISTEMA = "posix"
    try:
        yield
    finally:
        codex.SISTEMA = previo


def parche(*lineas):
    return "\n".join(("*** Begin Patch",) + lineas + ("*** End Patch",)) + "\n"


def pre_de_codex(inst, herramienta, entrada, cwd, sesion="sesion1", agente="a1b2"):
    e = {"hook_event_name": "PreToolUse", "tool_name": herramienta, "session_id": sesion, "agent_id": agente,
         "agent_type": "writer-web", "cwd": str(cwd), "tool_input": {"command": entrada}}
    return W._guardia().correr(e, raiz=str(inst), host="codex")


def escenario_codex(base):
    repo, archivo, inst = escenario(base, nuevo_texto="a\nb\nc\n")
    nuevo = repo / "Core" / "A" / "Otro.cs"
    texto = parche("*** Update File: Core/A/B.cs", "@@", "+y = MALO BLOQ;", "*** Add File: Core/A/Otro.cs", "+uno")
    assert pre_de_codex(inst, "apply_patch", texto, repo) == SILENCIO
    sal = (base / "salida.txt").as_posix()
    assert pre_de_codex(inst, "Bash", "echo a > " + sal, base) == SILENCIO
    assert "git commit" in (negado_en_codex(pre_de_codex(inst, "Bash", "git commit -m x", repo)) or "")
    escribir(repo, "Core/A/B.cs", "a\nb\nc\ny = MALO BLOQ;\n")
    escribir(repo, "Core/A/Otro.cs", "uno\n")
    return repo, archivo, nuevo, inst, sal


def test_codex_la_compuerta_lee_la_bitacora_y_no_el_transcript():
    with temporal() as base, posix():
        repo, archivo, nuevo, inst, sal = escenario_codex(base)
        t = transcript(base, [("Edit", {"file_path": str(base / "ajeno.cs")}), _bash("echo z > " + (base / "z.txt").as_posix())])
        c, o, e = correr(evento(t, resultado("ok")), inst, host="codex")
        razon = bloqueo(o) or ""
        assert c == 0 and e == b"" and "T-02" in razon and "Core/A/B.cs" in razon, (c, o, e)
        est = estado_escrito(inst)
        assert est["archivos"] == [str(archivo), str(nuevo)], est["archivos"]
        assert numstat_de(est) == [("Core/A/B.cs", 1, 0, "foto"), ("Core/A/Otro.cs", 1, 0, "nuevo")], numstat_de(est)
        assert est["escritos_por_bash"] == [sal], "el git commit bloqueado no está: %r" % est["escritos_por_bash"]
        assert est["errores_internos"] == [], est["errores_internos"]
        assert (carpeta_de_fotos(inst) / convencion.BITACORA).is_file(), "al bloquear, la bitácora queda para el reintento"
        c, o, e = correr(evento(t, resultado("ok"), activo=True), inst, host="codex")
        assert (c, o, e) == SILENCIO and not carpeta_de_fotos(inst).exists(), "al dejar cerrar se va con las fotos"


def test_codex_la_compuerta_exige_limites_igual_que_en_claude_code():
    with temporal() as base, posix():
        repo, archivo, nuevo, inst, sal = escenario_codex(base)
        t = transcript(base, [("Edit", {"file_path": str(base / "ajeno.cs")})])
        razon = bloqueo(correr(evento(t, resultado("ok", limites=None)), inst, host="codex")[1]) or ""
        assert "falta `limites:`" in razon and "\nlimites:\n" in razon, razon
        est = estado_escrito(inst)
        assert any("limites" in e for e in est["formato_errores"]) and est["resultado"]["limites"] == [], est
        assert correr(evento(t, resultado("ok", limites=None), activo=True), inst, host="codex") == SILENCIO


def test_codex_sin_hallazgos_de_capa_solo_falta_limites_y_completo_cierra_a_la_primera():
    with temporal() as base, posix():
        repo, archivo, nuevo, inst, sal = escenario_codex(base)
        escribir(repo, "Core/A/B.cs", "a\nb\nc\nlimpio\n")
        t = transcript(base, [("Edit", {"file_path": str(base / "ajeno.cs")})])
        razon = bloqueo(correr(evento(t, resultado("ok", limites=None)), inst, host="codex")[1]) or ""
        assert "falta `limites:`" in razon and "Chequeos de capa" not in razon, razon
        assert estado_escrito(inst)["formato_errores"] == [e for e in W.parsear_resultado(resultado("ok", limites=None))[1]]
        assert correr(evento(t, resultado("ok")), inst, host="codex") == SILENCIO, "con limites cierra a la primera"
        assert estado_escrito(inst)["resultado"]["limites"] == ["no corrió contra la base real, solo contra los datos de prueba"]


def test_codex_sin_poder_leer_la_bitacora_decide_como_un_transcript_ilegible_y_lo_dice():
    perdido = Path("no") / "existe.jsonl"
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        referencia = [bloqueo(correr(evento(base / perdido, "Listo."), inst)[1]) is not None,
                      correr(evento(base / perdido, resultado("ok")), inst)]
        assert referencia == [True, SILENCIO], "Claude Code con el transcript ilegible: manda el formato y nada más"
    for dano, falta in (("borrada", "la bitácora no está"), ("vacia", "la bitácora está vacía"),
                        ("ilegible", "no se pudo leer la bitácora")):
        with temporal() as base, posix():
            repo, archivo, nuevo, inst, sal = escenario_codex(base)
            bitacora = carpeta_de_fotos(inst) / convencion.BITACORA
            bitacora.unlink()
            if dano == "vacia":
                bitacora.write_bytes(b"")
            elif dano == "ilegible":
                bitacora.mkdir()
            c, o, e = correr(evento(base / perdido, "Listo."), inst, host="codex")
            assert bloqueo(o) is not None, "%s: el formato sigue mandando, la compuerta no se abre" % dano
            est = estado_escrito(inst)
            assert est["archivos"] == [str(nuevo)], "%s: el archivo nuevo sale de su marca: %r" % (dano, est["archivos"])
            internos = est["errores_internos"]
            assert any(x.startswith("archivos_tocados: " + falta) for x in internos), (dano, internos)
            assert "archivos_tocados: 1 archivos con foto no están en la bitácora y la compuerta no los puede medir" in internos, internos
            assert est["escritos_por_bash"] == [], est["escritos_por_bash"]
            assert correr(evento(base / perdido, resultado("ok")), inst, host="codex") == SILENCIO, dano


def test_codex_una_linea_rota_no_abre_la_compuerta():
    with temporal() as base, posix():
        repo, archivo, nuevo, inst, sal = escenario_codex(base)
        bitacora = carpeta_de_fotos(inst) / convencion.BITACORA
        sin_utf8 = json.dumps({"tipo": "edicion", "rutas": [str(repo / "Core" / "A" / "Z\ud800.cs")]}).encode("ascii")
        bitacora.write_bytes(b'{"tipo": "edicion", "rut\n' + sin_utf8 + b"\n" + bitacora.read_bytes() + b"\x00basura\n")
        c, o, e = correr(evento(base / "no.jsonl", resultado("ok")), inst, host="codex")
        assert "Core/A/B.cs" in (bloqueo(o) or ""), "el bloqueo de capa sigue: %r" % o
        est = estado_escrito(inst)
        assert est["archivos"] == [str(archivo), str(nuevo)] and est["escritos_por_bash"] == [sal], est
        assert est["errores_internos"] == ["archivos_tocados: la bitácora tiene 3 líneas rotas"], est["errores_internos"]


def test_codex_una_ruta_sin_utf8_en_el_parche_no_tapa_las_demas():
    with temporal() as base, posix():
        repo, archivo, inst = escenario(base)
        nuevo = repo / "Core" / "A" / "N2.cs"
        texto = parche("*** Add File: Core/A/N2.cs", "+y = MALO BLOQ;", "*** Add File: Core/A/Z\ud800.cs", "+z")
        assert pre_de_codex(inst, "apply_patch", texto, repo) == SILENCIO
        escribir(repo, "Core/A/N2.cs", "y = MALO BLOQ;\n")
        c, o, e = correr(evento(base / "no.jsonl", resultado("ok")), inst, host="codex")
        assert c == 0 and e == b"" and "Core/A/N2.cs" in (bloqueo(o) or ""), (c, o, e)
        assert estado_escrito(inst)["archivos"] == [str(nuevo)], estado_escrito(inst)["archivos"]


def test_main_lee_host_como_los_guards():
    with temporal() as base, posix():
        repo, archivo, nuevo, inst, sal = escenario_codex(base)
        entrada = json.dumps(evento(base / "no" / "existe.jsonl", resultado("ok"))).encode("utf-8")
        for args in (("--plazo", "50", "--host", "otro"), ("--plazo", "50", "--host"), ("--host=", "--plazo", "50")):
            r = hook(entrada, inst, args)
            assert (r.returncode, r.stdout, r.stderr) == (0, b"", b"") and estado_escrito(inst) is None, (args, r)
        for args in (("--plazo", "50", "--host", "codex"), ("--host=codex", "--plazo", "50")):
            r = hook(entrada, inst, args)
            assert r.returncode == 0 and r.stderr == b"" and "Core/A/B.cs" in (bloqueo(r.stdout.decode("ascii")) or ""), (args, r)
            assert estado_escrito(inst)["archivos"] == [str(archivo), str(nuevo)], args
        for args in (("--plazo", "50", "--host", "claude-code"), ("--plazo", "50")):
            r = hook(entrada, inst, args)
            assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), (args, r)
            assert estado_escrito(inst)["archivos"] == [], "Claude Code lee su transcript, que no está: %r" % (args,)


def test_claude_code_no_lee_la_bitacora():
    with temporal() as base:
        repo, archivo, inst = escenario(base)
        t = transcript(base, [("Read", {"file_path": str(archivo)})])
        for host in ({}, {"host": "claude-code"}):
            carpeta = carpeta_de_fotos(inst)
            carpeta.mkdir(parents=True, exist_ok=True)
            comun.anotar_en_bitacora(str(carpeta), {"tipo": "edicion", "rutas": [str(archivo)]})
            comun.anotar_en_bitacora(str(carpeta), {"tipo": "shell", "comando": "echo a > x.txt", "dialecto": "posix"})
            assert correr(evento(t, resultado("ok", arbol="sin cambios")), inst, **host) == SILENCIO, host
            est = estado_escrito(inst)
            assert (est["archivos"], est["escritos_por_bash"], est["errores_internos"]) == ([], [], []), (host, est)


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
