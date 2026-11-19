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
SCRIPT = AQUI / "rescatar.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []

META = {"agentType": "revisor-x", "model": "opus"}


def m():
    return importlib.import_module("rescatar")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Temporal:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="rescatar-test-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def usuario(texto):
    return {"type": "user", "message": {"role": "user", "content": texto}}


def asistente(*bloques):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(bloques)}}


def uso(nombre, entrada, id_=None):
    return {"type": "tool_use", "id": id_ or "t_" + nombre, "name": nombre, "input": entrada}


def resultado_de(id_, contenido, error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": id_, "content": contenido, "is_error": error}]}}


def agente(carpeta, id_, lineas, meta=META):
    carpeta.mkdir(parents=True, exist_ok=True)
    texto = "\n".join(l if isinstance(l, str) else json.dumps(l, ensure_ascii=False) for l in lineas) + "\n"
    (carpeta / ("agent-%s.jsonl" % id_)).write_bytes(texto.encode("utf-8"))
    if meta is not None:
        (carpeta / ("agent-%s.meta.json" % id_)).write_text(json.dumps(meta), encoding="utf-8")
    return carpeta / ("agent-%s.jsonl" % id_)


def tipica(reporte="Reporte con tildes: revisión ok."):
    return [
        usuario("Revisa el cambio antes del commit."),
        asistente({"type": "text", "text": "voy a leer"}, uso("Read", {"file_path": "C:\\x\\a.sql"}), uso("Bash", {"command": "ls"})),
        "",
        asistente(uso("Grep", {"pattern": "foo", "path": "C:\\x"}), uso("Glob", {"pattern": "**/*.sql"})),
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}},
        asistente(uso("SubagentHandback", {"message": reporte})),
    ]


def con_comandos():
    return [
        usuario("p"),
        asistente(uso("Bash", {"command": "python x.tests.py"}, "b1")),
        resultado_de("b1", "12/12"),
        asistente(uso("PowerShell", {"command": "git status"}, "b2")),
        resultado_de("b2", [{"type": "text", "text": "Exit code 128\nfatal: no es un repo"}], True),
        asistente(uso("Bash", {"command": "sleep 9"}, "b3")),
        asistente(uso("SubagentHandback", {"message": "r"})),
    ]


def cli(*args):
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), *map(str, args)], capture_output=True)
    return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n"), r.stderr.decode("utf-8").replace("\r\n", "\n")


def leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def test_extraer_prompt_reporte_y_lecturas():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base / "s", "abc", tipica()))
    assert r["prompt"] == "Revisa el cambio antes del commit.", r["prompt"]
    assert r["reporte"] == "Reporte con tildes: revisión ok." and r["origen"] == "handback", r
    assert [x["tool"] for x in r["lecturas"]] == ["Read", "Grep", "Glob"]
    assert r["lecturas"][0] == {"tool": "Read", "input": {"file_path": "C:\\x\\a.sql"}}
    assert r["no_auditadas"] == {"Bash": 1}, r["no_auditadas"]
    assert r["salteadas"] == 0, r["salteadas"]


def test_extraer_reporte_de_claves_alternativas():
    for clave in ("result", "report", "message"):
        with Temporal() as base:
            r = m().extraer_corrida(agente(base, "a", [usuario("p"), asistente(uso("SubagentHandback", {clave: "R-" + clave}))]))
        assert r["reporte"] == "R-" + clave, (clave, r["reporte"])
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [usuario("p"), asistente(uso("SubagentHandback", {"otra": "x"}))]))
    assert json.loads(r["reporte"]) == {"otra": "x"}, r["reporte"]


def test_extraer_el_ultimo_handback_gana():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [usuario("p"), asistente(uso("SubagentHandback", {"message": "primero"})),
                                                  asistente(uso("SubagentHandback", {"message": "segundo"}))]))
    assert r["reporte"] == "segundo", r["reporte"]


def test_extraer_prompt_como_lista_de_bloques():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [{"type": "user", "message": {"content": [
            {"type": "text", "text": "uno"}, {"type": "text", "text": "dos"}]}}, asistente(uso("SubagentHandback", {"message": "r"}))]))
    assert r["prompt"] == "uno\ndos", r["prompt"]


def test_extraer_el_texto_posterior_al_handback_no_lo_pisa():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [usuario("p"), asistente(uso("SubagentHandback", {"message": "el reporte"})),
                                                  asistente({"type": "text", "text": "listo, ya entregue"})]))
    assert r["reporte"] == "el reporte" and r["origen"] == "handback", r


def test_extraer_sin_handback_da_reporte_none():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [usuario("p"), asistente(uso("Read", {"file_path": "x"}))]))
    assert r["reporte"] is None and r["origen"] is None, r


def test_extraer_sin_handback_toma_el_texto_final():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [
            usuario("p"), asistente({"type": "text", "text": "voy a leer"}, uso("Read", {"file_path": "x"})),
            asistente({"type": "text", "text": "## Hallazgos"}), asistente({"type": "text", "text": "## Veredicto"})]))
    assert r["reporte"] == "## Hallazgos\n\n## Veredicto" and r["origen"] == "texto_final", r


def test_extraer_comandos_con_exit_y_error():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", con_comandos()))
    c = r["comandos"]
    assert [x["comando"] for x in c] == ["python x.tests.py", "git status", "sleep 9"], c
    assert [x["tool"] for x in c] == ["Bash", "PowerShell", "Bash"]
    assert (c[0]["exit"], c[0]["error"], c[0]["salida"]) == (0, None, "12/12"), c[0]
    assert c[1]["exit"] == 128 and "no es un repo" in c[1]["error"], c[1]
    assert (c[2]["exit"], c[2]["error"], c[2]["salida"]) == (None, None, None), c[2]
    assert r["no_auditadas"] == {"Bash": 2, "PowerShell": 1}, r["no_auditadas"]


def test_extraer_el_codigo_de_salida_sale_del_texto_del_resultado():
    with Temporal() as base:
        lineas = [usuario("p"), asistente(uso("Bash", {"command": "a"}, "b1")), resultado_de("b1", "Exit code -1\nfalla", True),
                  asistente(uso("Bash", {"command": "b"}, "b2")), resultado_de("b2", "sin codigo", True),
                  asistente(uso("Bash", {"command": "c"}, "b3")), resultado_de("b3", "x" * 5000),
                  asistente(uso("SubagentHandback", {"message": "r"}))]
        c = m().extraer_corrida(agente(base, "a", lineas))["comandos"]
    assert [x["exit"] for x in c] == [-1, 1, 0], c
    assert len(c[2]["salida"]) == m().MAX_SALIDA == 2000


def test_extraer_saltea_la_linea_a_medio_escribir_y_la_cuenta():
    with Temporal() as base:
        lineas = tipica()
        lineas.insert(3, '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Re')
        lineas.append('{"type": "assistant", "mes')
        r = m().extraer_corrida(agente(base, "a", lineas))
    assert r["reporte"] == "Reporte con tildes: revisión ok." and len(r["lecturas"]) == 3, r
    assert r["salteadas"] == 2, r["salteadas"]


def test_rescatar_escribe_los_archivos_y_las_lecturas_traen_no_auditadas():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "abc", tipica())
        res = m().rescatar(sub, dest, {"c1": "abc"})
        assert res == [{"corrida": "c1", "agente": "abc", "estado": "ok", "comandos": 1, "caracteres": 32, "lecturas": 3,
                        "agentType": "revisor-x", "model": "opus", "no_auditadas": {"Bash": 1}, "salteadas": 0}], res
        assert sorted(p.name for p in dest.iterdir()) == ["c1.comandos.json", "c1.lecturas.json", "c1.md", "c1.prompt.txt"]
        assert (dest / "c1.md").read_bytes().decode("utf-8") == "Reporte con tildes: revisión ok."
        assert (dest / "c1.prompt.txt").read_text(encoding="utf-8") == "Revisa el cambio antes del commit."
        lecturas = leer_json(dest / "c1.lecturas.json")
        assert list(lecturas) == ["agente", "meta", "lecturas", "no_auditadas", "costo"], list(lecturas)
        assert lecturas["agente"] == "abc" and lecturas["meta"] == META and lecturas["no_auditadas"] == {"Bash": 1}
        assert lecturas["lecturas"][0] == {"tool": "Read", "input": {"file_path": "C:\\x\\a.sql"}}


def test_los_archivos_que_escribe_van_en_lf_sin_bom():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "abc", tipica("Línea 1\nLínea 2\n"))
        agente(sub, "cmd", con_comandos())
        m().rescatar(sub, dest, {"c1": "abc", "c2": "cmd"})
        for escrito in sorted(dest.iterdir()):
            crudo = escrito.read_bytes()
            assert b"\r\n" not in crudo and not crudo.startswith(b"\xef\xbb\xbf"), (escrito.name, crudo[:80])
        assert b"\n" in (dest / "c1.md").read_bytes() and b"\n" in (dest / "c1.lecturas.json").read_bytes()
        assert b"\n" in (dest / "c2.comandos.json").read_bytes()


def test_las_lecturas_sin_herramientas_ajenas_traen_no_auditadas_vacio():
    with Temporal() as base:
        agente(base / "s", "a", [usuario("p"), asistente(uso("Read", {"file_path": "x"})), asistente(uso("SubagentHandback", {"message": "r"}))])
        m().rescatar(base / "s", base / "d", {"c": "a"})
        assert leer_json(base / "d" / "c.lecturas.json")["no_auditadas"] == {}


def test_rescatar_comandos_json_solo_si_hubo_comandos():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "a", con_comandos())
        agente(sub, "b", [usuario("p"), asistente(uso("Read", {"file_path": "x"})), asistente(uso("SubagentHandback", {"message": "r"}))])
        res = m().rescatar(sub, dest, {"con": "a", "sin": "b"})
        assert res[0]["comandos"] == 3 and res[1]["comandos"] == 0
        datos = leer_json(dest / "con.comandos.json")
        assert list(datos) == ["agente", "meta", "comandos"] and datos["agente"] == "a" and len(datos["comandos"]) == 3, datos
        assert not (dest / "sin.comandos.json").exists()
        assert sorted(p.name for p in dest.glob("sin.*")) == ["sin.lecturas.json", "sin.md", "sin.prompt.txt"]


def test_rescatar_sin_meta_usa_un_meta_vacio():
    with Temporal() as base:
        agente(base / "s", "a", tipica(), meta=None)
        res = m().rescatar(base / "s", base / "d", {"c": "a"})
        assert res[0]["agentType"] is None and res[0]["model"] is None, res
        assert leer_json(base / "d" / "c.lecturas.json")["meta"] == {}


def test_rescatar_sin_reporte_no_escribe_y_agente_inexistente():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "abc", [usuario("p"), asistente(uso("Read", {"file_path": "x"}))])
        res = m().rescatar(sub, dest, {"c1": "abc", "c2": "noexiste"})
        assert res == [{"corrida": "c1", "agente": "abc", "estado": "sin_reporte", "lecturas": 1, "salteadas": 0},
                       {"corrida": "c2", "agente": "noexiste", "estado": "no_encontrado"}], res
        assert not dest.exists()


def test_resolver_dir_subagents_acepta_la_sesion_o_la_propia_carpeta():
    with Temporal() as base:
        (base / "subagents").mkdir()
        assert m().resolver_dir_subagents(base) == base / "subagents"
        assert m().resolver_dir_subagents(base / "subagents") == base / "subagents"


def test_las_constantes_de_claude_code_tienen_nombre():
    assert m().HANDBACK == "SubagentHandback"
    assert m().CODIGO_DE_SALIDA_RE.match("Exit code 12\nx").group(1) == "12"
    assert m().SHELL == ("Bash", "PowerShell")


def test_cli_ok_escribe_y_cuenta_en_el_stdout():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "abc", tipica())
        codigo, salida, error = cli("--sesion", sub, "--destino", dest, "--corrida", "c1=agent-abc")
        assert codigo == 0 and error == "", (codigo, error)
        assert salida == "ok   c1: 32 car., 3 lecturas, revisor-x/opus  (herramientas NO auditadas: Bash x1)  (comandos Bash/PowerShell: 1 en c1.comandos.json)\n", repr(salida)
        assert sorted(p.name for p in dest.iterdir()) == ["c1.comandos.json", "c1.lecturas.json", "c1.md", "c1.prompt.txt"]
        assert leer_json(dest / "c1.lecturas.json")["no_auditadas"] == {"Bash": 1}


def test_cli_acepta_la_carpeta_de_la_sesion_y_nombra_los_comandos():
    with Temporal() as base:
        agente(base / "sesion" / "subagents", "a", con_comandos())
        codigo, salida, error = cli("--sesion", base / "sesion", "--destino", base / "d", "--corrida", "con=a")
        assert codigo == 0 and error == "", (codigo, error)
        assert salida == "ok   con: 1 car., 0 lecturas, revisor-x/opus  (herramientas NO auditadas: Bash x2, PowerShell x1)  (comandos Bash/PowerShell: 3 en con.comandos.json)\n", repr(salida)


def test_cli_salida_1_si_alguna_corrida_falla_y_no_escribe_la_que_falla():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "abc", tipica())
        agente(sub, "def", [usuario("p")])
        codigo, salida, error = cli("--sesion", sub, "--destino", dest, "--corrida", "c1=abc", "--corrida", "c2=def", "--corrida", "c3=nada")
        assert codigo == 1 and error == "", (codigo, error)
        assert salida.splitlines() == [
            "ok   c1: 32 car., 3 lecturas, revisor-x/opus  (herramientas NO auditadas: Bash x1)  (comandos Bash/PowerShell: 1 en c1.comandos.json)",
            "FAIL c2: sin SubagentHandback (corrida cortada), 0 lecturas, no se escribio nada",
            "FAIL c3: no existe agent-nada.jsonl en %s" % sub], salida
        assert sorted(p.name for p in dest.iterdir()) == ["c1.comandos.json", "c1.lecturas.json", "c1.md", "c1.prompt.txt"]


def test_cli_salida_2_por_uso_incorrecto():
    with Temporal() as base:
        sub = base / "subagents"
        agente(sub, "abc", tipica())
        for corrida in ("sin-igual", "=x", "x="):
            codigo, salida, error = cli("--sesion", sub, "--destino", base / "d", "--corrida", corrida)
            assert (codigo, salida) == (2, "rescatar: --corrida espera <nombre>=<agentId>, recibio %r\n" % corrida), (corrida, codigo, salida)
        codigo, salida, error = cli("--sesion", base / "nada", "--destino", base / "d", "--corrida", "c=abc")
        assert (codigo, salida) == (2, "rescatar: no existe la carpeta de subagentes %s\n" % (base / "nada")), (codigo, salida)
        codigo, salida, error = cli("--destino", base / "d")
        assert codigo == 2 and salida == "" and "required" in error, (codigo, salida, error)
        assert not (base / "d").exists()


def test_cli_salida_2_ante_un_error_interno_con_el_mensaje_en_stderr():
    with Temporal() as base:
        sub = base / "subagents"
        agente(sub, "abc", tipica())
        (sub / "agent-abc.meta.json").write_text("{no es json", encoding="utf-8")
        codigo, salida, error = cli("--sesion", sub, "--destino", base / "d", "--corrida", "c=abc")
        assert codigo == 2 and salida == "" and error.startswith("rescatar: error interno ("), (codigo, salida, error)


def test_cli_tolera_la_linea_rota_y_la_avisa_por_stderr():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        lineas = tipica()
        lineas.insert(3, '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Re')
        agente(sub, "abc", lineas)
        codigo, salida, error = cli("--sesion", sub, "--destino", dest, "--corrida", "c1=abc")
        assert codigo == 0, (codigo, salida, error)
        assert salida == "ok   c1: 32 car., 3 lecturas, revisor-x/opus  (herramientas NO auditadas: Bash x1)  (comandos Bash/PowerShell: 1 en c1.comandos.json)\n", repr(salida)
        assert error == "aviso c1: 1 linea(s) de agent-abc.jsonl no se pudieron leer y se saltearon\n", repr(error)
        assert (dest / "c1.md").read_text(encoding="utf-8") == "Reporte con tildes: revisión ok."
        assert len(leer_json(dest / "c1.lecturas.json")["lecturas"]) == 3


def test_cli_avisa_la_linea_rota_tambien_en_la_corrida_sin_reporte():
    with Temporal() as base:
        sub = base / "subagents"
        agente(sub, "abc", [usuario("p"), '{"type": "assi'])
        codigo, salida, error = cli("--sesion", sub, "--destino", base / "d", "--corrida", "c1=abc")
        assert codigo == 1 and salida.startswith("FAIL c1: sin SubagentHandback"), (codigo, salida)
        assert error == "aviso c1: 1 linea(s) de agent-abc.jsonl no se pudieron leer y se saltearon\n", repr(error)
        assert not (base / "d").exists()


def test_cli_sin_linea_rota_no_escribe_nada_en_stderr():
    with Temporal() as base:
        sub = base / "subagents"
        agente(sub, "abc", tipica())
        assert cli("--sesion", sub, "--destino", base / "d", "--corrida", "c=abc")[2] == ""


def tokens(entrada, escrita, leida, salida):
    return {"input_tokens": entrada, "cache_creation_input_tokens": escrita, "cache_read_input_tokens": leida,
            "output_tokens": salida}


def con_uso(id_, usado, ts, *bloques):
    registro = asistente(*bloques)
    registro["message"].update({"id": id_, "usage": usado})
    registro["timestamp"] = ts
    return registro


def medida(reporte="r", handback=True, hora="10"):
    lineas = [
        dict(usuario("Revisa."), timestamp="2026-11-18T%s:00:00.000Z" % hora),
        con_uso("m1", tokens(3, 40000, 0, 100), "2026-11-18T%s:00:05.000Z" % hora, {"type": "text", "text": "leo"}),
        con_uso("m1", tokens(3, 40000, 0, 100), "2026-11-18T%s:00:05.100Z" % hora, uso("Read", {"file_path": "x"})),
        dict(resultado_de("t_Read", "x"), timestamp="2026-11-18T%s:00:06.000Z" % hora),
        con_uso("m2", tokens(2, 5000, 40000, 300), "2026-11-18T%s:02:06.000Z" % hora,
                uso("SubagentHandback", {"message": reporte}) if handback else {"type": "text", "text": ""}),
    ]
    return lineas


COSTO_MEDIDA = {"turnos": 2, "contexto_inicial": 40003, "contexto_final": 45002, "salida": 400, "cache_escrita": 45000,
                "cache_leida": 40000, "inicio": "2026-11-18T10:00:00.000Z", "fin": "2026-11-18T10:02:06.000Z",
                "pausa_mayor": 120.0}
TRIAJE = {"modo": "completo", "motivos": ["señal capas: positiva", "señal consumidores: invalida"], "senales": {}}
DIFF = ("diff --git a/x.sql b/x.sql\n--- a/x.sql\n+++ b/x.sql\n@@ -1,4 +1,4 @@\n contexto\n-viejo\n+nuevo\n"
        "--- comentario quitado\n+++ linea agregada\n\\ No newline at end of file\n")
DIFF_NUEVO = "diff --git a/dev/null b/n.txt\nnew file mode 100644\n--- /dev/null\n+++ b/n.txt\n@@ -0,0 +1,2 @@\n+a\n+b\n"


def revision(base, carpeta="2026-11-18-completo", triaje=TRIAJE, diffs=None):
    rev = base / "inst" / "tickets" / "T1-a" / "revision" / carpeta
    (rev / "entrada").mkdir(parents=True)
    if triaje is not None:
        (rev / "entrada" / "triaje.json").write_text(json.dumps(triaje, ensure_ascii=False), encoding="utf-8")
    for nombre, crudo in (diffs if diffs is not None else {"repo-a.diff": DIFF.encode("utf-8")}).items():
        (rev / "entrada" / nombre).write_bytes(crudo)
    return rev


def test_las_lecturas_guardan_el_costo_de_la_corrida_contado_una_vez_por_mensaje():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "a1", medida())
        codigo, salida, error = cli("--sesion", sub, "--destino", dest, "--corrida", "c1=a1")
        assert (codigo, salida, error) == (0, "ok   c1: 1 car., 1 lecturas, revisor-x/opus\n", ""), (codigo, salida, error)
        lecturas = leer_json(dest / "c1.lecturas.json")
        assert list(lecturas) == ["agente", "meta", "lecturas", "no_auditadas", "costo"], list(lecturas)
        assert lecturas["costo"] == COSTO_MEDIDA, lecturas["costo"]
        assert lecturas["lecturas"] == [{"tool": "Read", "input": {"file_path": "x"}}] and lecturas["no_auditadas"] == {}
        assert sorted(p.name for p in dest.iterdir()) == ["c1.lecturas.json", "c1.md", "c1.prompt.txt"]


def test_las_lecturas_de_una_transcripcion_sin_uso_guardan_el_costo_en_null():
    with Temporal() as base:
        agente(base / "s", "a", tipica())
        codigo, salida, _ = cli("--sesion", base / "s", "--destino", base / "d", "--corrida", "c=a")
        assert codigo == 0 and salida.startswith("ok   c: 32 car., 3 lecturas"), (codigo, salida)
        lecturas = leer_json(base / "d" / "c.lecturas.json")
        assert lecturas["costo"] is None and lecturas["meta"] == META and len(lecturas["lecturas"]) == 3, lecturas


def test_sin_costo_no_escribe_costo_json_aunque_el_destino_sea_una_revision():
    with Temporal() as base:
        rev = revision(base)
        agente(base / "s", "a1", medida())
        codigo, salida, error = cli("--sesion", base / "s", "--destino", rev / "corridas", "--corrida", "c1=a1")
        assert (codigo, salida, error) == (0, "ok   c1: 1 car., 1 lecturas, revisor-x/opus\n", ""), (codigo, salida, error)
        assert sorted(p.name for p in (rev / "corridas").iterdir()) == ["c1.lecturas.json", "c1.md", "c1.prompt.txt"]


def test_cli_costo_escribe_el_costo_de_la_revision():
    with Temporal() as base:
        rev = revision(base)
        agente(base / "s", "a1", medida())
        agente(base / "s", "a2", tipica(), meta={"agentType": "revisor-capa-a", "model": "sonnet"})
        codigo, salida, error = cli("--sesion", base / "s", "--destino", rev / "corridas", "--corrida", "c1=a1",
                                    "--corrida", "c2=agent-a2", "--costo")
        assert codigo == 0 and error == SIN_PRINCIPAL % (base / "s.jsonl"), (codigo, error)
        assert salida.splitlines() == [
            "ok   c1: 1 car., 1 lecturas, revisor-x/opus",
            "ok   c2: 32 car., 3 lecturas, revisor-capa-a/sonnet  (herramientas NO auditadas: Bash x1)  (comandos Bash/PowerShell: 1 en c2.comandos.json)",
            "costo: 2 corrida(s) en %s (1 sin datos de uso)" % (rev / "corridas" / "costo.json")], salida
        crudo = (rev / "corridas" / "costo.json").read_bytes()
        assert b"\r\n" not in crudo and not crudo.startswith(b"\xef\xbb\xbf"), crudo[:80]
        costo = json.loads(crudo.decode("utf-8"))
        assert costo == {"modo": "completo", "motivos": TRIAJE["motivos"], "corridas": [
            {"corrida": "c1", "agente": "a1", "estado": "ok", "agentType": "revisor-x", "model": "opus", "costo": COSTO_MEDIDA},
            {"corrida": "c2", "agente": "a2", "estado": "ok", "agentType": "revisor-capa-a", "model": "sonnet", "costo": None}],
            "lineas_diff": 4, "orquestador": None, "en_serie": None}, costo
        assert list(costo) == ["modo", "motivos", "corridas", "lineas_diff", "orquestador", "en_serie"], list(costo)


def test_cli_costo_cuenta_las_lineas_agregadas_y_quitadas_de_todos_los_diffs():
    with Temporal() as base:
        utf16 = "﻿diff --git a/u.txt b/u.txt\n--- a/u.txt\n+++ b/u.txt\n@@ -1 +1 @@\n-x\n+y\n".encode("utf-16-le")
        rev = revision(base, carpeta="2026-11-18-rapido-2", diffs={
            "repo-a.diff": DIFF.encode("utf-8"), "repo-b.diff": DIFF_NUEVO.encode("utf-8"), "repo-c.diff": utf16,
            "binario.diff": b"diff --git a/i.png b/i.png\nBinary files a/i.png and b/i.png differ\n", "notas.txt": b"+no\n"})
        agente(base / "s", "a1", medida())
        codigo, _, error = cli("--sesion", base / "s", "--destino", rev / "corridas", "--corrida", "c1=a1", "--costo")
        assert (codigo, error) == (0, SIN_PRINCIPAL % (base / "s.jsonl")), (codigo, error)
        costo = leer_json(rev / "corridas" / "costo.json")
        assert (costo["modo"], costo["lineas_diff"]) == ("rapido", 8), costo


def test_cli_costo_suma_la_corrida_cortada_y_junta_los_rescates_por_agente():
    with Temporal() as base:
        rev = revision(base)
        sub, dest = base / "s", rev / "corridas"
        agente(sub, "a1", medida())
        agente(sub, "a2", medida(handback=False))
        codigo, salida, error = cli("--sesion", sub, "--destino", dest, "--corrida", "c1=a1", "--corrida", "c2=a2", "--costo")
        assert codigo == 1 and error == SIN_PRINCIPAL % (base / "s.jsonl"), (codigo, error)
        assert salida.splitlines()[1:] == ["FAIL c2: sin SubagentHandback (corrida cortada), 1 lecturas, no se escribio nada",
                                           "costo: 2 corrida(s) en %s" % (dest / "costo.json")], salida
        assert [(c["corrida"], c["agente"], c["estado"], c["costo"]) for c in leer_json(dest / "costo.json")["corridas"]] == [
            ("c1", "a1", "ok", COSTO_MEDIDA), ("c2", "a2", "sin_reporte", COSTO_MEDIDA)]
        assert not (dest / "c2.md").exists() and not (dest / "c2.lecturas.json").exists()
        agente(sub, "a3", medida())
        assert cli("--sesion", sub, "--destino", dest, "--corrida", "c2=a3", "--costo")[0] == 0
        assert cli("--sesion", sub, "--destino", dest, "--corrida", "c1=a1", "--corrida", "c9=nada", "--costo")[0] == 1
        assert [(c["corrida"], c["agente"], c["estado"]) for c in leer_json(dest / "costo.json")["corridas"]] == [
            ("c1", "a1", "ok"), ("c2", "a2", "sin_reporte"), ("c2", "a3", "ok")]


def test_cli_costo_sin_triaje_ni_diff_deja_null_y_lo_avisa():
    with Temporal() as base:
        rev = revision(base, triaje=None, diffs={})
        agente(base / "s", "a1", medida())
        codigo, _, error = cli("--sesion", base / "s", "--destino", rev / "corridas", "--corrida", "c1=a1", "--costo")
        assert codigo == 0, (codigo, error)
        assert error.splitlines() == [
            "aviso costo: no hay motivos en %s; quedan en null" % (rev / "entrada" / "triaje.json"),
            "aviso costo: no hay diffs en %s; lineas_diff queda en null" % (rev / "entrada"),
            (SIN_PRINCIPAL % (base / "s.jsonl")).rstrip("\n")], error
        costo = leer_json(rev / "corridas" / "costo.json")
        assert (costo["motivos"], costo["lineas_diff"], len(costo["corridas"])) == (None, None, 1), costo
        for roto, previo in (("{no es json", "{roto"), (json.dumps({"modo": "rapido"}), json.dumps({"corridas": [{"agente": ["x"]}]})),
                             (json.dumps({"motivos": "texto"}), json.dumps([1]))):
            (rev / "entrada" / "triaje.json").write_text(roto, encoding="utf-8")
            (rev / "corridas" / "costo.json").write_text(previo, encoding="utf-8")
            codigo, _, error = cli("--sesion", base / "s", "--destino", rev / "corridas", "--corrida", "c1=a1", "--costo")
            assert codigo == 0 and error.splitlines()[0] == (
                "aviso costo: %s no se pudo leer; se reescribe con las corridas de este rescate" % (rev / "corridas" / "costo.json")), error
            assert "aviso costo: no hay motivos en" in error, error
            assert leer_json(rev / "corridas" / "costo.json")["motivos"] is None


def test_cli_costo_rechaza_un_destino_que_no_es_una_revision():
    with Temporal() as base:
        agente(base / "s", "a1", medida())
        sombra = base / "inst" / "tickets" / "T1-a" / "revision" / "2026-11-18-sombra" / "corridas"
        for dest in (base / "scratch" / "corridas", sombra, base / "scratch" / "2026-11-18-completo" / "corridas",
                     base / "inst" / "tickets" / "T1-a" / "revision" / "2026-11-18-completo-1" / "corridas"):
            codigo, salida, error = cli("--sesion", base / "s", "--destino", dest, "--corrida", "c1=a1", "--costo")
            assert (codigo, salida, error) == (2, "rescatar: --costo espera --destino <ticket>/revision/<fecha>-<modo>[-<n>]/corridas, recibio %s\n" % dest, ""), (codigo, salida, error)
            assert not dest.exists()


def test_carpeta_de_revision_y_modos_son_los_de_recibo():
    recibo = importlib.import_module("recibo")
    assert m().CARPETA_RE.pattern == recibo.CARPETA_RE.pattern
    assert m().MODOS == recibo.MODOS


def escribir_costo(base, ticket, carpeta, corridas, lineas=40, modo=None, crudo=None):
    ruta = base / "inst" / "tickets" / ticket / "revision" / carpeta / "corridas" / "costo.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {"modo": modo or carpeta.split("-")[3], "motivos": [], "corridas": [
        {"corrida": "c%d" % i, "agente": "a%d" % i, "estado": "ok", "agentType": "x", "model": "opus", "costo": c}
        for i, c in enumerate(corridas)], "lineas_diff": lineas}
    ruta.write_text(crudo if crudo is not None else json.dumps(datos), encoding="utf-8")
    return ruta


def medido(fin, turnos=2, final=45002, salida=400, escrita=45000, leida=40000):
    return {"turnos": turnos, "contexto_inicial": 40003, "contexto_final": final, "salida": salida, "cache_escrita": escrita,
            "cache_leida": leida, "inicio": "2026-11-18T08:00:00.000Z", "fin": fin, "pausa_mayor": 1.0}


def test_cli_ultimo_costo_cita_la_revision_mas_nueva_del_ticket():
    with Temporal() as base:
        ticket = base / "inst" / "tickets" / "T1-a"
        escribir_costo(base, "T1-a", "2026-11-17-completo", [medido("2026-11-17T23:00:00.000Z")])
        escribir_costo(base, "T1-a", "2026-11-18-completo", [medido("2026-11-18T08:30:00.000Z")])
        escribir_costo(base, "T1-a", "2026-11-18-rapido", [
            medido("2026-11-18T09:00:00.000Z"), None,
            medido("2026-11-18T09:01:00.000Z", turnos=4, final=55000, salida=600, escrita=15000, leida=160000)])
        escribir_costo(base, "T1-a", "2026-11-19-sombra", [medido("2026-11-19T09:00:00.000Z")], modo="completo")
        escribir_costo(base, "T1-a", "2026-11-20-completo", [None, None])
        roto = escribir_costo(base, "T1-a", "2026-11-21-rapido", [], crudo="{roto")
        escribir_costo(base, "T2-b", "2026-11-22-completo", [medido("2026-11-22T09:00:00.000Z")])
        codigo, salida, error = cli("--ultimo-costo", ticket)
        assert codigo == 0, (codigo, salida, error)
        assert salida == ("último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-rapido: modo rapido, "
                          "2 de 3 corrida(s) con datos de uso, 40 líneas de diff; por corrida, en promedio: 3 turnos, "
                          "contexto final 50 001, salida 500, caché escrita 30 000 y caché leída 100 000 tokens\n"), repr(salida)
        assert error == "aviso costo: se ignora %s (no es un costo.json legible)\n" % roto, repr(error)


def test_cli_ultimo_costo_sin_costo_en_el_ticket_cita_el_de_la_instancia():
    with Temporal() as base:
        ticket = base / "inst" / "tickets" / "T3-c"
        (ticket / "revision" / "2026-11-23-completo" / "corridas").mkdir(parents=True)
        escribir_costo(base, "archivo/T1-a", "2026-11-17-completo", [medido("2026-11-17T09:00:00.000Z")], lineas=None)
        escribir_costo(base, "T2-b", "2026-11-16-completo", [medido("2026-11-16T09:00:00.000Z")])
        codigo, salida, error = cli("--ultimo-costo", ticket)
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert salida == ("último costo medido, de la instancia (el ticket no tiene): tickets/archivo/T1-a/revision/"
                          "2026-11-17-completo: modo completo, 1 corrida(s), líneas de diff sin medir; por corrida, en "
                          "promedio: 2 turnos, contexto final 45 002, salida 400, caché escrita 45 000 y caché leída 40 000 tokens\n"), repr(salida)


def test_cli_ultimo_costo_sin_ninguno_sale_con_1():
    with Temporal() as base:
        ticket = base / "inst" / "tickets" / "T1-a"
        ticket.mkdir(parents=True)
        escribir_costo(base, "T2-b", "2026-11-19-sombra", [medido("2026-11-19T09:00:00.000Z")], modo="completo")
        assert cli("--ultimo-costo", ticket) == (1, "sin costo medido en el ticket ni en la instancia\n", "")
        suelto = base / "suelto" / "T9-z"
        suelto.mkdir(parents=True)
        assert cli("--ultimo-costo", suelto) == (1, "sin costo medido en el ticket ni en la instancia\n", "")


def test_cli_ultimo_costo_lee_lo_que_escribe_el_rescate():
    with Temporal() as base:
        rev = revision(base)
        agente(base / "s", "a1", medida())
        assert cli("--sesion", base / "s", "--destino", rev / "corridas", "--corrida", "c1=a1", "--costo")[0] == 0
        codigo, salida, error = cli("--ultimo-costo", base / "inst" / "tickets" / "T1-a")
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert salida.startswith("último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, "
                                 "1 corrida(s), 4 líneas de diff; por corrida, en promedio: 2 turnos, contexto final 45 002,"), salida


def test_cli_ultimo_costo_es_un_uso_aparte():
    with Temporal() as base:
        ticket = base / "inst" / "tickets" / "T1-a"
        ticket.mkdir(parents=True)
        for extra in (("--sesion", base), ("--destino", base / "d"), ("--corrida", "c=a"), ("--costo",)):
            assert cli("--ultimo-costo", ticket, *extra) == (
                2, "rescatar: --ultimo-costo no se combina con --sesion, --destino, --corrida ni --costo\n", ""), extra
        assert cli("--ultimo-costo", base / "nada") == (2, "rescatar: no existe la carpeta del ticket %s\n" % (base / "nada"), "")
        assert not (base / "d").exists()


def lanzado(id_, agente_, ts):
    return {"type": "user", "timestamp": ts, "toolUseResult": {"agentId": agente_, "status": "async_launched"},
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": id_, "content": [
                {"type": "text", "text": "Async agent launched successfully.\nagentId: %s" % agente_}]}]}}


def bash(id_, comando):
    return uso("Bash", {"command": comando}, id_)


TRIAJE_DEL_ANUNCIO = 'python3 "/plugin/scripts/triaje.py" --ticket "T1-a" --repo "/repo#main"'
TRIAJE_DE_LA_ENTRADA = TRIAJE_DEL_ANUNCIO + ' --json > "/inst/tickets/T1-a/revision/2026-11-18-completo/entrada/triaje.json"'
RECIBO = 'python3 "/plugin/scripts/recibo.py" --write --ticket "T1-a" --repo "/repo#main" --modo completo'


def principal(agentes=("a1", "a2"), triajes=(TRIAJE_DEL_ANUNCIO, TRIAJE_DE_LA_ENTRADA), recibo=False):
    lineas = [
        dict(usuario("Revisa el cambio."), timestamp="2026-11-18T09:50:00.000Z"),
        con_uso("p0", tokens(5, 2000, 10000, 40), "2026-11-18T09:50:05.000Z", uso("Agent", {"prompt": "otra"}, "l0")),
        lanzado("l0", "viejo", "2026-11-18T09:50:06.000Z"),
    ]
    for i, comando in enumerate(triajes):
        lineas += [con_uso("p1-%d" % i, tokens(5, 1000, 12000, 60), "2026-11-18T09:5%d:00.000Z" % (5 + i),
                           {"type": "text", "text": "triaje"}),
                   con_uso("p1-%d" % i, tokens(4, 3000, 13000, 80), "2026-11-18T09:5%d:00.100Z" % (5 + i), bash("x%d" % i, comando)),
                   dict(resultado_de("x%d" % i, "modo completo"), timestamp="2026-11-18T09:5%d:01.000Z" % (5 + i))]
    lineas += [con_uso("p3", tokens(3, 2500, 16000, 900), "2026-11-18T10:00:00.000Z", uso("Agent", {"prompt": "r1"}, "l1")),
               con_uso("p3", tokens(3, 2500, 16000, 900), "2026-11-18T10:00:00.100Z", uso("Agent", {"prompt": "r2"}, "l2"))]
    lineas += [lanzado("l%d" % (i + 1), a, "2026-11-18T10:00:0%d.500Z" % (i + 1)) for i, a in enumerate(agentes)]
    lineas += [con_uso("p4", tokens(2, 1500, 18500, 30), "2026-11-18T10:03:00.000Z", bash("x9", TRIAJE_DEL_ANUNCIO)),
               dict(resultado_de("x9", "modo completo"), timestamp="2026-11-18T10:03:01.000Z"),
               con_uso("p5", tokens(2, 600, 20000, 120), "2026-11-18T10:05:00.000Z", bash("r1", "python3 rescatar.py --costo"))]
    if recibo:
        lineas += [dict(resultado_de("r1", "ok"), timestamp="2026-11-18T10:05:02.000Z"),
                   con_uso("p6", tokens(2, 400, 20600, 200), "2026-11-18T10:20:00.000Z", bash("w1", RECIBO)),
                   dict(resultado_de("w1", "escrito"), timestamp="2026-11-18T10:20:01.000Z"),
                   con_uso("p7", tokens(2, 300, 21000, 70), "2026-11-18T10:30:00.000Z", {"type": "text", "text": "listo"})]
    return lineas


ORQUESTADOR = {"turnos": 4, "contexto_inicial": 16004, "contexto_final": 20602, "salida": 1130, "cache_escrita": 7600,
               "cache_leida": 67500, "inicio": "2026-11-18T09:56:00.100Z", "fin": "2026-11-18T10:05:00.000Z",
               "pausa_mayor": 239.0, "contexto_dejado": 4598}
SIN_PRINCIPAL = "aviso costo: no hay transcript de la sesion principal en %s; orquestador queda en null\n"


def sesion_con_principal(base, lineas, corridas=(("a1", "10"), ("a2", "10"))):
    sub = base / "proyecto" / "sesion-1" / "subagents"
    for agente_, hora in corridas:
        agente(sub, agente_, medida(hora=hora))
    if lineas is not None:
        (base / "proyecto" / "sesion-1.jsonl").write_bytes(
            ("\n".join(json.dumps(l, ensure_ascii=False) for l in lineas) + "\n").encode("utf-8"))
    return sub


def rescate_con_costo(base, sesion, rev, *corridas):
    return cli("--sesion", sesion, "--destino", rev / "corridas", *[x for c in corridas for x in ("--corrida", c)], "--costo")


def test_cli_costo_mide_al_orquestador_desde_el_ultimo_triaje_y_una_vez_por_mensaje():
    with Temporal() as base:
        rev = revision(base)
        sub = sesion_con_principal(base, principal())
        for sesion in (sub, sub.parent):
            codigo, salida, error = rescate_con_costo(base, sesion, rev, "c1=a1", "c2=a2")
            assert (codigo, error) == (0, ""), (codigo, salida, error)
            assert salida.splitlines()[-1] == "costo: 2 corrida(s) en %s" % (rev / "corridas" / "costo.json"), salida
            costo = leer_json(rev / "corridas" / "costo.json")
            assert list(costo) == ["modo", "motivos", "corridas", "lineas_diff", "orquestador", "en_serie"], list(costo)
            assert costo["orquestador"] == ORQUESTADOR, costo["orquestador"]
            assert list(costo["orquestador"]) == list(ORQUESTADOR), list(costo["orquestador"])


def test_cli_costo_corta_el_tramo_del_orquestador_en_el_recibo_de_la_ronda():
    with Temporal() as base:
        rev = revision(base)
        sub = sesion_con_principal(base, principal(recibo=True))
        codigo, salida, error = rescate_con_costo(base, sub, rev, "c1=a1", "c2=a2")
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert leer_json(rev / "corridas" / "costo.json")["orquestador"] == dict(
            ORQUESTADOR, turnos=5, contexto_final=21002, salida=1330, cache_escrita=8000, cache_leida=88100,
            fin="2026-11-18T10:20:00.000Z", pausa_mayor=898.0, contexto_dejado=4998)


def test_cli_costo_sin_transcript_principal_deja_al_orquestador_en_null_y_lo_avisa():
    with Temporal() as base:
        rev = revision(base)
        sub = sesion_con_principal(base, None)
        codigo, salida, error = rescate_con_costo(base, sub, rev, "c1=a1", "c2=a2")
        assert codigo == 0, (codigo, salida, error)
        assert error == SIN_PRINCIPAL % (base / "proyecto" / "sesion-1.jsonl"), repr(error)
        assert leer_json(rev / "corridas" / "costo.json")["orquestador"] is None


def test_cli_costo_sin_ancla_deja_al_orquestador_en_null_y_lo_avisa():
    with Temporal() as base:
        principal_ = base / "proyecto" / "sesion-1.jsonl"
        casos = ((principal(triajes=()), "no hay un triaje.py antes del primer lanzamiento de las corridas en %s" % principal_),
                 (principal(agentes=("otro", "otro2")), "no se encontro el lanzamiento de ninguna corrida en %s" % principal_),
                 ([usuario("p"), asistente({"type": "text", "text": "sin uso"})],
                  "no se encontro el lanzamiento de ninguna corrida en %s" % principal_),
                 ([dict(l, message={k: v for k, v in l["message"].items() if k != "usage"}) for l in principal()],
                  "el tramo de %s no tiene datos de uso" % principal_))
        for i, (lineas, aviso) in enumerate(casos):
            rev = revision(base, carpeta="2026-11-1%d-completo" % i)
            sub = sesion_con_principal(base, lineas)
            codigo, salida, error = rescate_con_costo(base, sub, rev, "c1=a1", "c2=a2")
            assert codigo == 0, (codigo, salida, error)
            assert error == "aviso costo: %s; orquestador queda en null\n" % aviso, (i, error)
            assert leer_json(rev / "corridas" / "costo.json")["orquestador"] is None


def test_cli_costo_dice_si_las_corridas_de_la_ronda_corrieron_en_serie():
    with Temporal() as base:
        casos = (((("a1", "10"), ("a2", "10")), ("c1=a1", "c2=a2"), False),
                 ((("a1", "10"), ("a2", "11")), ("c1=a1", "c2=a2"), True),
                 ((("a1", "10"),), ("c1=a1",), None))
        for i, (corridas, argumentos, esperado) in enumerate(casos):
            rev = revision(base, carpeta="2026-11-1%d-completo" % i)
            sub = sesion_con_principal(base / str(i), principal(), corridas=corridas)
            assert rescate_con_costo(base, sub, rev, *argumentos)[0] == 0
            assert leer_json(rev / "corridas" / "costo.json")["en_serie"] is esperado, (i, esperado)
        rev = revision(base, carpeta="2026-11-18-rapido")
        sub = sesion_con_principal(base / "3", principal(), corridas=(("a1", "10"), ("a2", "11")))
        agente(sub, "a3", tipica())
        assert rescate_con_costo(base, sub, rev, "c1=a1", "c2=a2", "c3=a3")[0] == 0
        assert leer_json(rev / "corridas" / "costo.json")["en_serie"] is None, "una corrida sin tiempos no deja afirmar la serie"
        agente(sub, "a4", medida(hora="10"))
        assert rescate_con_costo(base, sub, rev, "c4=a4")[0] == 0
        assert leer_json(rev / "corridas" / "costo.json")["en_serie"] is False, "la ronda junta los rescates de la carpeta"


def test_cli_ultimo_costo_menciona_la_serie_solo_si_es_cierta():
    with Temporal() as base:
        ticket = base / "inst" / "tickets" / "T1-a"
        linea = ("último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, 1 corrida(s), "
                 "40 líneas de diff; por corrida, en promedio: 2 turnos, contexto final 45 002, salida 400, caché escrita "
                 "45 000 y caché leída 40 000 tokens")
        ruta = escribir_costo(base, "T1-a", "2026-11-18-completo", [medido("2026-11-18T08:30:00.000Z")])
        for en_serie, sufijo in ((True, "; las corridas corrieron en serie"), (False, ""), (None, ""), ("si", "")):
            datos = leer_json(ruta)
            datos["en_serie"] = en_serie
            ruta.write_text(json.dumps(datos), encoding="utf-8")
            assert cli("--ultimo-costo", ticket) == (0, linea + sufijo + "\n", ""), en_serie


def test_cli_costo_sin_datos_nuevos_conserva_las_claves_y_el_anuncio():
    with Temporal() as base:
        rev = revision(base)
        agente(base / "s", "a1", medida())
        codigo, salida, error = cli("--sesion", base / "s", "--destino", rev / "corridas", "--corrida", "c1=a1", "--costo")
        assert (codigo, salida) == (0, "ok   c1: 1 car., 1 lecturas, revisor-x/opus\ncosto: 1 corrida(s) en %s\n" % (
            rev / "corridas" / "costo.json")), (codigo, salida)
        assert error == SIN_PRINCIPAL % (base / "s.jsonl"), repr(error)
        costo = leer_json(rev / "corridas" / "costo.json")
        assert costo == {"modo": "completo", "motivos": TRIAJE["motivos"], "corridas": [
            {"corrida": "c1", "agente": "a1", "estado": "ok", "agentType": "revisor-x", "model": "opus", "costo": COSTO_MEDIDA}],
            "lineas_diff": 4, "orquestador": None, "en_serie": None}, costo
        assert leer_json(rev / "corridas" / "c1.lecturas.json")["costo"] == COSTO_MEDIDA
        assert cli("--ultimo-costo", base / "inst" / "tickets" / "T1-a") == (0, (
            "último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, 1 corrida(s), "
            "4 líneas de diff; por corrida, en promedio: 2 turnos, contexto final 45 002, salida 400, caché escrita "
            "45 000 y caché leída 40 000 tokens\n"), "")


def test_cli_sin_sesion_ni_corrida_conserva_el_error_de_los_obligatorios():
    with Temporal() as base:
        codigo, salida, error = cli("--destino", base / "d")
        assert (codigo, salida) == (2, ""), (codigo, salida)
        assert error.splitlines()[-1] == "rescatar.py: error: the following arguments are required: --sesion, --corrida", error
        codigo, salida, error = cli()
        assert error.splitlines()[-1] == "rescatar.py: error: the following arguments are required: --sesion, --destino, --corrida", error


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
