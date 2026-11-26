import importlib
import json
import os
import re
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


VEREDICTO = "VEREDICTO: 0 CRITICAL, 1 WARNING, 0 SUGGESTION"


def test_extraer_con_veredicto_el_reporte_es_el_texto_previo_a_la_devolucion():
    reporte = "## Hallazgos\n[WARNING] sin ID a.sql:3 — x — y"
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [
            usuario("p"), asistente({"type": "text", "text": "voy a leer"}, uso("Read", {"file_path": "x"})),
            asistente({"type": "text", "text": reporte}, uso("SubagentHandback", {"message": VEREDICTO}))]))
    assert r["reporte"] == reporte and r["origen"] == "texto_previo" and r["veredicto"] == VEREDICTO, r


def test_extraer_solo_el_veredicto_no_da_reporte():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [
            usuario("p"), asistente({"type": "text", "text": "voy a leer"}, uso("Read", {"file_path": "x"})),
            asistente(uso("SubagentHandback", {"message": VEREDICTO}))]))
    assert r["reporte"] is None and r["origen"] == "solo_veredicto" and r["veredicto"] == VEREDICTO, r


def test_extraer_una_devolucion_sin_veredicto_sigue_siendo_el_reporte_aunque_haya_texto_antes():
    with Temporal() as base:
        r = m().extraer_corrida(agente(base, "a", [
            usuario("p"), asistente({"type": "text", "text": "te lo entrego"}, uso("SubagentHandback", {"message": "## Reporte\nentero"}))]))
    assert r["reporte"] == "## Reporte\nentero" and r["origen"] == "handback" and r["veredicto"] is None, r


def test_rescatar_solo_el_veredicto_falla_en_voz_alta_y_no_escribe():
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "abc", [usuario("p"), asistente(uso("Read", {"file_path": "x"})), asistente(uso("SubagentHandback", {"message": VEREDICTO}))])
        codigo, out, err = cli("--sesion", sub, "--destino", dest, "--corrida", "c1=abc")
        assert codigo == 1 and "FAIL c1: el revisor devolvio solo el veredicto" in out and not dest.exists(), (codigo, out, err)


FORMAS_DE_ANTES = (VEREDICTO, "**VEREDICTO:** 0 CRITICAL, 1 WARNING, 0 SUGGESTION",
                   "`VEREDICTO: 0 CRITICAL, 1 WARNING, 0 SUGGESTION`", "Veredicto: 0 CRITICAL, 1 WARNING, 0 SUGGESTION",
                   "0 CRITICAL, 1 WARNING, 0 SUGGESTION", "**VEREDICTO:**\n0 CRITICAL, 1 WARNING, 0 SUGGESTION")
FORMAS_QUE_SE_ESCAPABAN = ("Veredicto final: 0 CRITICAL, 1 WARNING, 0 SUGGESTION", "**Veredicto final:** 0 CRITICAL, 1 WARNING, 0 SUGGESTION",
                           "✅ VEREDICTO: 0 CRITICAL, 1 WARNING, 0 SUGGESTION", "Verdict: 0 critical, 1 warning, 0 suggestion",
                           "\U0001f7e1 **Verdict:** 0 CRITICAL, 1 WARNING, 0 SUGGESTION",
                           "Cierro con 0 CRITICAL, 1 WARNING, 0 SUGGESTION en total.", "Veredicto final:\n0 CRITICAL, 1 WARNING, 0 SUGGESTION",
                           "Verdict: no findings", "✅ Veredicto final: sin hallazgos")
FORMAS_DEL_VEREDICTO = FORMAS_DE_ANTES + FORMAS_QUE_SE_ESCAPABAN


def test_rescatar_reconoce_el_veredicto_en_negrita_entre_comillas_en_minusculas_o_por_sus_cuentas():
    reporte = "## Hallazgos\n[WARNING] sin ID a.sql:3 — x — y"
    for forma in FORMAS_DEL_VEREDICTO:
        with Temporal() as base:
            sub = base / "subagents"
            r = m().extraer_corrida(agente(sub, "abc", [
                usuario("p"), asistente({"type": "text", "text": reporte}, uso("SubagentHandback", {"message": forma}))]))
            assert (r["reporte"], r["origen"], r["veredicto"]) == (reporte, "texto_previo", forma), (forma, r)
            r = m().extraer_corrida(agente(sub, "def", [
                usuario("p"), asistente(uso("Read", {"file_path": "x"})), asistente(uso("SubagentHandback", {"message": forma}))]))
            assert (r["reporte"], r["origen"]) == (None, "solo_veredicto"), (forma, r)
            codigo, out, err = cli("--sesion", sub, "--destino", base / "corridas", "--corrida", "c1=abc")
            assert codigo == 0 and (base / "corridas" / "c1.md").read_text(encoding="utf-8") == reporte, (forma, codigo, out, err)
            codigo, out, err = cli("--sesion", sub, "--destino", base / "solo", "--corrida", "c2=def")
            assert codigo == 1 and "FAIL c2: el revisor devolvio solo el veredicto" in out, (forma, codigo, out, err)
            assert not (base / "solo").exists(), forma


def test_pi_reconoce_el_veredicto_en_negrita_entre_comillas_en_minusculas_o_por_sus_cuentas():
    reporte = "## Hallazgos\nninguno"
    for forma in FORMAS_DEL_VEREDICTO:
        con_reporte = tarea_pi(resultado=forma, items=hilo_pi() + [{"kind": "text", "text": reporte}, {"kind": "text", "text": forma}])
        r = m()._corrida_de_tarea(con_reporte["task"], con_reporte["thread"])
        assert (r["reporte"], r["origen"], r["veredicto"]) == (reporte, "texto_previo", forma), (forma, r)
        solo = tarea_pi(id_="t2", resultado=forma)
        r = m()._corrida_de_tarea(solo["task"], solo["thread"])
        assert (r["reporte"], r["origen"]) == (None, "solo_veredicto"), (forma, r)
        with Temporal() as base:
            guardar_tarea(base / "agente", con_reporte)
            guardar_tarea(base / "agente", solo)
            codigo, out, err = cli_pi(base, "--destino", base / "corridas", "--corrida", "c1=t1")
            assert codigo == 0 and (base / "corridas" / "c1.md").read_text(encoding="utf-8") == reporte, (forma, codigo, out, err)
            codigo, out, err = cli_pi(base, "--destino", base / "solo", "--corrida", "c2=t2")
            assert codigo == 1 and "FAIL c2: el revisor devolvio solo el veredicto" in out, (forma, codigo, out, err)
            assert not (base / "solo").exists(), forma


def test_una_devolucion_que_no_es_solo_el_veredicto_sigue_siendo_el_reporte():
    for devolucion in (VEREDICTO + "\n## Hallazgos\n[WARNING] sin ID a.sql:3", "**Veredicto:** 1 WARNING\n## Hallazgos\n- a.sql:3",
                       "El veredicto: revisa a.sql antes del commit", "Sin hallazgos.",
                       "Veredicto final: 0 CRITICAL, 1 WARNING, 0 SUGGESTION\n## Hallazgos\n[WARNING] sin ID a.sql:3",
                       "✅ Verdict: 0 critical, 1 warning, 0 suggestion\n- a.sql:3", "El veredicto final: revisa a.sql antes del commit",
                       "## Hallazgos\n- a.sql:3 deja 0 critical, 1 warning, 0 suggestion"):
        with Temporal() as base:
            r = m().extraer_corrida(agente(base, "a", [
                usuario("p"), asistente({"type": "text", "text": "previo"}, uso("SubagentHandback", {"message": devolucion}))]))
        assert (r["reporte"], r["origen"], r["veredicto"]) == (devolucion, "handback", None), (devolucion, r)
        datos = tarea_pi(resultado=devolucion, items=hilo_pi() + [{"kind": "text", "text": "previo"}])
        r = m()._corrida_de_tarea(datos["task"], datos["thread"])
        assert (r["reporte"], r["origen"], r["veredicto"]) == (devolucion, "resultado", None), (devolucion, r)


GITHUB = "gh" + "p_" + ("aB3dE5fG7h" * 4)[:36]
AWS = "AK" + "IA" + "Z7Q4X2W9R5T8Y3U6"


def test_rescatar_tapa_los_secretos_de_lo_que_guarda_y_los_json_siguen_validos():
    reporte = "## Hallazgos\n[CRITICAL] sin ID a.py:1 — un token en el código: `%s`" % GITHUB
    with Temporal() as base:
        sub, dest = base / "subagents", base / "corridas"
        agente(sub, "abc", [
            usuario("Revisa el cambio; la clave de prueba es " + AWS),
            asistente(uso("Grep", {"pattern": GITHUB, "path": "C:\\x"}),
                      uso("Bash", {"command": "curl -H 'Authorization: token %s' x" % GITHUB}, "b1")),
            resultado_de("b1", "AWS=" + AWS),
            asistente({"type": "text", "text": reporte}, uso("SubagentHandback", {"message": VEREDICTO}))])
        res = m().rescatar(sub, dest, {"c1": "abc"})
        tapado = reporte.replace(GITHUB, "<GITHUB_TOKEN>")
        assert res == [{"corrida": "c1", "agente": "abc", "estado": "ok", "comandos": 1, "caracteres": len(tapado), "lecturas": 1,
                        "agentType": "revisor-x", "model": "opus", "no_auditadas": {"Bash": 1}, "salteadas": 0, "tapados": 5}], res
        for escrito in sorted(dest.iterdir()):
            texto = escrito.read_text(encoding="utf-8")
            assert GITHUB not in texto and AWS not in texto, (escrito.name, texto)
        assert (dest / "c1.md").read_text(encoding="utf-8") == tapado
        assert (dest / "c1.prompt.txt").read_text(encoding="utf-8") == "Revisa el cambio; la clave de prueba es <AWS_ACCESS_KEY_ID>"
        assert leer_json(dest / "c1.lecturas.json")["lecturas"] == [{"tool": "Grep", "input": {"pattern": "<GITHUB_TOKEN>", "path": "C:\\x"}}]
        comando = leer_json(dest / "c1.comandos.json")["comandos"][0]
        assert comando == {"tool": "Bash", "comando": "curl -H 'Authorization: token <GITHUB_TOKEN>' x", "exit": 0, "error": None,
                           "salida": "AWS=<AWS_ACCESS_KEY_ID>"}, comando
        shutil.rmtree(dest)
        codigo, out, err = cli("--sesion", sub, "--destino", dest, "--corrida", "c1=abc")
        assert codigo == 0 and err == "", (codigo, err)
        assert out == ("ok   c1: %d car., 1 lecturas, revisor-x/opus  (herramientas NO auditadas: Bash x1)  (comandos Bash/PowerShell: "
                       "1 en c1.comandos.json)  (5 secreto(s) tapado(s) antes de guardar)\n" % len(tapado)), out
        carpeta = guardar_tarea(base / "agente", tarea_pi(resultado="Reporte de Pi con " + AWS))
        res = m().rescatar_pi(carpeta, base / "pi", {"c2": "t1"})
        assert res[0]["estado"] == "ok" and res[0]["tapados"] == 1, res
        assert (base / "pi" / "c2.md").read_text(encoding="utf-8") == "Reporte de Pi con <AWS_ACCESS_KEY_ID>"


def test_pi_con_veredicto_el_reporte_es_el_texto_despues_de_la_ultima_herramienta():
    reporte = "## Hallazgos\nninguno"
    items = hilo_pi() + [{"kind": "text", "text": reporte}, {"kind": "text", "text": VEREDICTO}]
    datos = tarea_pi(resultado=VEREDICTO, items=items)
    r = m()._corrida_de_tarea(datos["task"], datos["thread"])
    assert r["reporte"] == reporte and r["origen"] == "texto_previo" and r["veredicto"] == VEREDICTO, r


def test_pi_solo_el_veredicto_no_da_reporte():
    datos = tarea_pi(resultado=VEREDICTO)
    r = m()._corrida_de_tarea(datos["task"], datos["thread"])
    assert r["reporte"] is None and r["origen"] == "solo_veredicto", r


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


def test_sin_host_el_rescate_de_claude_code_no_cambia():
    with Temporal() as base:
        vistos = []
        for nombre, extra in (("sin", ()), ("con", ("--host", "claude-code"))):
            raiz = base / nombre
            rev = revision(raiz)
            sub = sesion_con_principal(raiz, principal())
            agente(sub, "a3", con_comandos())
            codigo, salida, error = cli(*extra, "--sesion", sub, "--destino", rev / "corridas", "--corrida", "c1=a1",
                                        "--corrida", "c3=agent-a3", "--corrida", "c4=nada", "--costo")
            archivos = {p.name: p.read_bytes() for p in sorted((rev / "corridas").iterdir())}
            vistos.append((codigo, salida.replace(str(raiz), "<raiz>"), error.replace(str(raiz), "<raiz>"), archivos))
        assert vistos[0] == vistos[1], vistos
        codigo, salida, error, archivos = vistos[0]
        assert (codigo, error) == (1, ""), (codigo, error)
        assert salida.splitlines() == [
            "ok   c1: 1 car., 1 lecturas, revisor-x/opus",
            "ok   c3: 1 car., 0 lecturas, revisor-x/opus  (herramientas NO auditadas: Bash x2, PowerShell x1)  (comandos Bash/PowerShell: 3 en c3.comandos.json)",
            "FAIL c4: no existe agent-nada.jsonl en %s" % Path("<raiz>", "proyecto", "sesion-1", "subagents"),
            "costo: 2 corrida(s) en %s (1 sin datos de uso)" % Path("<raiz>", "inst", "tickets", "T1-a", "revision",
                                                                   "2026-11-18-completo", "corridas", "costo.json")], salida
        assert sorted(archivos) == ["c1.lecturas.json", "c1.md", "c1.prompt.txt", "c3.comandos.json", "c3.lecturas.json", "c3.md",
                                    "c3.prompt.txt", "costo.json"], sorted(archivos)


MODELO_PI = "proveedor/modelo-x"
PROMPT_PI = "Revisá el diseño del ticket T1 antes del commit."
INICIO_PI, FIN_PI = 1794996000250, 1794996270007
USO_PI = {"input": 900, "output": 1200, "cacheRead": 50000, "cacheWrite": 8000, "reasoning": 300}
COSTO_PI = {"turnos": 3, "contexto_inicial": None, "contexto_final": None, "salida": 1200, "cache_escrita": 8000,
            "cache_leida": 50000, "inicio": "2026-11-18T10:00:00.250Z", "fin": "2026-11-18T10:04:30.007Z", "pausa_mayor": None,
            "tokens_total": 60100, "costo_usd": 0.42}
SIN_ORQUESTADOR_PI = "aviso costo: el costo del orquestador solo se mide en Claude Code; orquestador queda en null\n"
AUSENTE = object()


def herramienta_pi(nombre, args, salida="", error=False, corriendo=False, llamada=None):
    return {"kind": "tool", "callId": llamada or "c-" + nombre, "name": nombre, "args": args, "output": salida,
            "running": corriendo, "isError": error}


def hilo_pi():
    return [{"kind": "text", "text": "voy a leer"}, herramienta_pi("read", {"path": "C:\\x\\a.sql"}, "contenido"),
            {"kind": "thinking", "text": "pienso"}, herramienta_pi("grep", {"pattern": "foo", "path": "C:\\x"}),
            herramienta_pi("find", {"pattern": "**/*.sql"}), {"kind": "note", "text": "retrying (1/3)"}]


def tarea_pi(id_="t1", status="completed", resultado="Reporte de Pi.", items=None, dropped=0, uso=USO_PI, inicio=INICIO_PI,
             fin=FIN_PI, agente_="revisor-diseno", **cambios):
    tarea = {"id": id_, "agent": agente_, "mode": "background", "prompt": PROMPT_PI, "label": "Revisá el diseño",
             "cwd": "C:\\inst", "parentSessionId": "s1", "status": status, "createdAt": INICIO_PI - 50, "startedAt": inicio,
             "endedAt": fin, "model": MODELO_PI, "thinking": None, "sessionPath": None, "error": None, "result": resultado,
             "lastStep": "responded", "lastActivityAt": FIN_PI, "turns": 3, "toolCalls": 3, "tokens": 60100, "cost": 0.42}
    if uso is not None:
        tarea["usage"] = uso
    for clave, valor in cambios.items():
        if valor is AUSENTE:
            tarea.pop(clave, None)
        else:
            tarea[clave] = valor
    return {"task": tarea, "thread": {"items": hilo_pi() if items is None else items, "dropped": dropped, "version": 9,
                                      "limits": {"maxItems": 400, "maxOutputChars": 16000}}}


def guardar_tarea(home, datos):
    carpeta = home / "gentle-agents" / "tasks"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / ("%s.json" % datos["task"]["id"])).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return carpeta


def cli_pi(base, *args, entorno=None):
    env = {k: v for k, v in os.environ.items() if k not in ("GENTLE_PI_AGENT_HOME", "PI_CODING_AGENT_DIR")}
    env.update({"HOME": str(base / "casa"), "USERPROFILE": str(base / "casa")})
    env.update(entorno if entorno is not None else {"GENTLE_PI_AGENT_HOME": str(base / "agente")})
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--host", "pi", *map(str, args)], capture_output=True, env=env)
    return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n"), r.stderr.decode("utf-8").replace("\r\n", "\n")


def test_pi_un_reporte_de_30_kb_llega_entero_con_su_prompt_y_sus_lecturas():
    with Temporal() as base:
        reporte = "".join("[WARNING] sin ID a.sql:%d — revisión número %d\n" % (i, i) for i in range(700))
        assert len(reporte.encode("utf-8")) > 30000, len(reporte.encode("utf-8"))
        guardar_tarea(base / "agente", tarea_pi(resultado=reporte))
        codigo, salida, error = cli_pi(base, "--destino", base / "d", "--corrida", "revisor-diseno-r1=t1")
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert salida == "ok   revisor-diseno-r1: %d car., 3 lecturas, revisor-diseno/%s\n" % (len(reporte), MODELO_PI), repr(salida)
        assert (base / "d" / "revisor-diseno-r1.md").read_bytes() == reporte.encode("utf-8")
        assert (base / "d" / "revisor-diseno-r1.prompt.txt").read_text(encoding="utf-8") == PROMPT_PI
        lecturas = leer_json(base / "d" / "revisor-diseno-r1.lecturas.json")
        assert list(lecturas) == ["agente", "meta", "lecturas", "no_auditadas", "costo"], list(lecturas)
        assert (lecturas["agente"], lecturas["meta"]) == ("t1", {"agentType": "revisor-diseno", "model": MODELO_PI}), lecturas
        assert lecturas["lecturas"] == [{"tool": "read", "input": {"path": "C:\\x\\a.sql"}},
                                        {"tool": "grep", "input": {"pattern": "foo", "path": "C:\\x"}},
                                        {"tool": "find", "input": {"pattern": "**/*.sql"}}], lecturas["lecturas"]
        assert lecturas["no_auditadas"] == {} and lecturas["costo"] == COSTO_PI, lecturas
        assert sorted(p.name for p in (base / "d").iterdir()) == [
            "revisor-diseno-r1.lecturas.json", "revisor-diseno-r1.md", "revisor-diseno-r1.prompt.txt"]


def test_pi_una_tarea_que_no_termino_bien_da_sin_reporte_y_no_escribe_nada():
    with Temporal() as base:
        casos = (("failed", None), ("cancelled", None), ("timed_out", None), ("running", None), ("queued", None),
                 ("completed", None), ("completed", ""), ("failed", "texto parcial"))
        for i, (status, resultado) in enumerate(casos):
            guardar_tarea(base / "agente", tarea_pi(id_="t%d" % i, status=status, resultado=resultado))
            codigo, salida, error = cli_pi(base, "--destino", base / "d", "--corrida", "c=t%d" % i)
            assert (codigo, error) == (1, ""), (status, codigo, error)
            assert salida == ("FAIL c: tarea t%d en estado %s, sin reporte (corrida cortada), 3 lecturas, no se escribio nada\n"
                              % (i, status)), repr(salida)
        assert not (base / "d").exists()


def test_pi_las_herramientas_que_no_son_lecturas_van_a_no_auditadas_y_los_comandos_se_guardan():
    with Temporal() as base:
        items = hilo_pi() + [herramienta_pi("edit", {"path": "a.sql", "edits": []}),
                             herramienta_pi("bash", {"command": "ls"}, "a.sql\n"),
                             herramienta_pi("bash", {"command": "git status"}, "fatal: no es un repo", error=True, llamada="c2"),
                             herramienta_pi("powershell", {"command": "sleep 9"}, corriendo=True), herramienta_pi("ls", {"path": "."})]
        guardar_tarea(base / "agente", tarea_pi(items=items))
        codigo, salida, error = cli_pi(base, "--destino", base / "d", "--corrida", "c1=t1")
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert salida == ("ok   c1: 14 car., 3 lecturas, revisor-diseno/%s  (herramientas NO auditadas: bash x2, edit x1, ls x1, "
                          "powershell x1)  (comandos Bash/PowerShell: 3 en c1.comandos.json)\n" % MODELO_PI), repr(salida)
        assert leer_json(base / "d" / "c1.lecturas.json")["no_auditadas"] == {"edit": 1, "bash": 2, "powershell": 1, "ls": 1}
        assert leer_json(base / "d" / "c1.comandos.json") == {"agente": "t1", "meta": {"agentType": "revisor-diseno", "model": MODELO_PI},
                                                             "comandos": [
            {"tool": "bash", "comando": "ls", "exit": 0, "error": None, "salida": "a.sql\n"},
            {"tool": "bash", "comando": "git status", "exit": 1, "error": "fatal: no es un repo", "salida": "fatal: no es un repo"},
            {"tool": "powershell", "comando": "sleep 9", "exit": None, "error": None, "salida": None}]}


def test_pi_un_hilo_con_elementos_descartados_da_un_aviso():
    with Temporal() as base:
        guardar_tarea(base / "agente", tarea_pi(dropped=7))
        guardar_tarea(base / "agente", tarea_pi(id_="t2", status="failed", resultado=None, dropped=1))
        guardar_tarea(base / "agente", tarea_pi(id_="t3"))
        codigo, salida, error = cli_pi(base, "--destino", base / "d", "--corrida", "c1=t1", "--corrida", "c2=t2", "--corrida", "c3=t3")
        assert codigo == 1 and salida.startswith("ok   c1: 14 car., 3 lecturas"), (codigo, salida)
        aviso = ("aviso %s: gentle-shell descarto %d elemento(s) del hilo de la tarea %s (dropped): las lecturas y las "
                 "herramientas pueden estar incompletas")
        assert error.splitlines() == [aviso % ("c1", 7, "t1"), aviso % ("c2", 1, "t2")], error


def test_pi_el_home_de_los_agentes_sigue_la_precedencia_del_entorno_y_sesion_lo_reemplaza():
    with Temporal() as base:
        for carpeta in ("g", "p", "casa/.pi/agent", "casa/otro"):
            guardar_tarea(base / carpeta, tarea_pi(resultado="desde " + carpeta))
        casos = (({"GENTLE_PI_AGENT_HOME": str(base / "g"), "PI_CODING_AGENT_DIR": str(base / "p")}, "g"),
                 ({"GENTLE_PI_AGENT_HOME": "", "PI_CODING_AGENT_DIR": str(base / "p")}, "p"),
                 ({"PI_CODING_AGENT_DIR": "~/otro"}, "casa/otro"),
                 ({}, "casa/.pi/agent"))
        for i, (entorno, carpeta) in enumerate(casos):
            destino = base / ("d%d" % i)
            codigo, salida, error = cli_pi(base, "--destino", destino, "--corrida", "c=t1", entorno=entorno)
            assert (codigo, error) == (0, ""), (entorno, codigo, salida, error)
            assert (destino / "c.md").read_text(encoding="utf-8") == "desde " + carpeta, (entorno, carpeta)
        for i, sesion in enumerate((base / "p", base / "p" / "gentle-agents" / "tasks")):
            destino = base / ("s%d" % i)
            assert cli_pi(base, "--sesion", sesion, "--destino", destino, "--corrida", "c=t1")[0] == 0, sesion
            assert (destino / "c.md").read_text(encoding="utf-8") == "desde p", sesion


def test_pi_una_tarea_que_no_existe_o_no_se_lee_es_un_fail_y_sin_carpeta_o_con_un_id_raro_sale_con_2():
    with Temporal() as base:
        tareas = guardar_tarea(base / "agente", tarea_pi())
        (tareas / "roto.json").write_text("{roto", encoding="utf-8")
        (tareas / "ajeno.json").write_text(json.dumps({"task": {"id": 1}}), encoding="utf-8")
        codigo, salida, error = cli_pi(base, "--destino", base / "d", "--corrida", "c1=t1", "--corrida", "c2=nada",
                                       "--corrida", "c3=roto", "--corrida", "c4=ajeno")
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        assert salida.splitlines() == [
            "ok   c1: 14 car., 3 lecturas, revisor-diseno/%s" % MODELO_PI,
            "FAIL c2: no existe nada.json en %s" % tareas,
            "FAIL c3: roto.json no es una tarea de gentle-shell que se pueda leer, no se escribio nada",
            "FAIL c4: ajeno.json no es una tarea de gentle-shell que se pueda leer, no se escribio nada"], salida
        assert sorted(p.name for p in (base / "d").iterdir()) == ["c1.lecturas.json", "c1.md", "c1.prompt.txt"]
        vacio = base / "vacio"
        assert cli_pi(base, "--destino", base / "d2", "--corrida", "c=t1", entorno={"GENTLE_PI_AGENT_HOME": str(vacio)}) == (
            2, "rescatar: no existe la carpeta de tareas de gentle-shell %s\n" % (vacio / "gentle-agents" / "tasks"), "")
        for corrida in ("c=../t1", "c=t1.json", "c=a b", "c=", "sin-igual"):
            assert cli_pi(base, "--destino", base / "d3", "--corrida", corrida) == (
                2, "rescatar: --corrida espera <nombre>=<task_id>, recibio %r\n" % corrida, ""), corrida
        assert not (base / "d2").exists() and not (base / "d3").exists()
        codigo, salida, error = cli_pi(base)
        assert (codigo, salida) == (2, "") and error.splitlines()[-1] == (
            "rescatar.py: error: the following arguments are required: --destino, --corrida"), error


def test_pi_costo_escribe_el_costo_de_la_revision_sin_orquestador_y_el_anuncio_no_inventa_lo_que_falta():
    with Temporal() as base:
        rev = revision(base)
        guardar_tarea(base / "agente", tarea_pi())
        guardar_tarea(base / "agente", tarea_pi(id_="t2", agente_="revisor-capa-a", uso=None, inicio=1794996300000, fin=1794996360999))
        codigo, salida, error = cli_pi(base, "--destino", rev / "corridas", "--corrida", "c1=t1", "--corrida", "c2=t2", "--costo")
        assert (codigo, error) == (0, SIN_ORQUESTADOR_PI), (codigo, salida, error)
        assert salida.splitlines()[-1] == "costo: 2 corrida(s) en %s" % (rev / "corridas" / "costo.json"), salida
        segunda = dict(COSTO_PI, salida=None, cache_escrita=None, cache_leida=None, inicio="2026-11-18T10:05:00.000Z",
                       fin="2026-11-18T10:06:00.999Z")
        assert leer_json(rev / "corridas" / "costo.json") == {"modo": "completo", "motivos": TRIAJE["motivos"], "corridas": [
            {"corrida": "c1", "agente": "t1", "estado": "ok", "agentType": "revisor-diseno", "model": MODELO_PI, "costo": COSTO_PI},
            {"corrida": "c2", "agente": "t2", "estado": "ok", "agentType": "revisor-capa-a", "model": MODELO_PI, "costo": segunda}],
            "lineas_diff": 4, "orquestador": None, "en_serie": True}
        assert leer_json(rev / "corridas" / "c1.lecturas.json")["costo"] == COSTO_PI
        assert cli("--ultimo-costo", base / "inst" / "tickets" / "T1-a") == (0, (
            "último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, 2 corrida(s), 4 líneas "
            "de diff; por corrida, en promedio: 3 turnos, contexto final sin medir, salida 1 200, caché escrita 8 000 y caché "
            "leída 50 000 tokens; las corridas corrieron en serie\n"), "")


TICKET_T1 = ("inst", "tickets", "T1-a")
INICIO_T2, FIN_T2 = 1794996300000, 1794996360999


def test_pi_una_tarea_real_sin_usage_guarda_sus_totales_cuenta_como_medida_y_el_anuncio_los_cita():
    with Temporal() as base:
        rev = revision(base)
        guardar_tarea(base / "agente", tarea_pi(uso=None, tokens=7196, cost=0.0142, turns=4, toolCalls=5))
        guardar_tarea(base / "agente", tarea_pi(id_="t2", uso=None, usage=None, tokens=2804, cost=0.0058, turns=2, toolCalls=1,
                                                inicio=INICIO_T2, fin=FIN_T2))
        codigo, salida, error = cli_pi(base, "--destino", rev / "corridas", "--corrida", "c1=t1", "--corrida", "c2=t2", "--costo")
        assert (codigo, error) == (0, SIN_ORQUESTADOR_PI), (codigo, salida, error)
        assert salida.splitlines()[-1] == "costo: 2 corrida(s) en %s" % (rev / "corridas" / "costo.json"), salida
        totales = dict(COSTO_PI, turnos=4, salida=None, cache_escrita=None, cache_leida=None, tokens_total=7196, costo_usd=0.0142)
        assert list(totales)[-2:] == ["tokens_total", "costo_usd"]
        assert leer_json(rev / "corridas" / "c1.lecturas.json")["costo"] == totales
        assert [c["costo"] for c in leer_json(rev / "corridas" / "costo.json")["corridas"]] == [totales, dict(
            totales, turnos=2, inicio="2026-11-18T10:05:00.000Z", fin="2026-11-18T10:06:00.999Z", tokens_total=2804, costo_usd=0.0058)]
        assert cli("--ultimo-costo", base.joinpath(*TICKET_T1)) == (0, (
            "último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, 2 corrida(s), 4 líneas "
            "de diff; por corrida, en promedio: 3 turnos, 5 000 tokens en total y 0,0100 USD; las corridas corrieron en serie\n"), "")


def test_pi_una_tarea_sin_usage_tokens_ni_costo_cuenta_sin_datos_de_uso():
    with Temporal() as base:
        rev = revision(base)
        guardar_tarea(base / "agente", tarea_pi())
        guardar_tarea(base / "agente", tarea_pi(id_="t2", uso=None, tokens=AUSENTE, cost=AUSENTE, inicio=INICIO_T2, fin=FIN_T2))
        codigo, salida, error = cli_pi(base, "--destino", rev / "corridas", "--corrida", "c1=t1", "--corrida", "c2=t2", "--costo")
        assert (codigo, error) == (0, SIN_ORQUESTADOR_PI), (codigo, salida, error)
        assert salida.splitlines()[-1] == "costo: 2 corrida(s) en %s (1 sin datos de uso)" % (rev / "corridas" / "costo.json"), salida
        assert leer_json(rev / "corridas" / "costo.json")["corridas"][1]["costo"] == dict(
            COSTO_PI, salida=None, cache_escrita=None, cache_leida=None, tokens_total=None, costo_usd=None,
            inicio="2026-11-18T10:05:00.000Z", fin="2026-11-18T10:06:00.999Z")
        assert cli("--ultimo-costo", base.joinpath(*TICKET_T1)) == (0, (
            "último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, 1 de 2 corrida(s) con "
            "datos de uso, 4 líneas de diff; por corrida, en promedio: 3 turnos, contexto final sin medir, salida 1 200, caché "
            "escrita 8 000 y caché leída 50 000 tokens; las corridas corrieron en serie\n"), "")


def test_pi_el_anuncio_no_le_pone_tokens_a_un_campo_sin_medir():
    with Temporal() as base:
        rev = revision(base)
        guardar_tarea(base / "agente", tarea_pi(uso={"output": 1200, "cacheWrite": 8000}))
        assert cli_pi(base, "--destino", rev / "corridas", "--corrida", "c1=t1", "--costo")[0] == 0
        assert cli("--ultimo-costo", base.joinpath(*TICKET_T1)) == (0, (
            "último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, 1 corrida(s), 4 líneas "
            "de diff; por corrida, en promedio: 3 turnos, contexto final sin medir, salida 1 200, caché escrita 8 000 tokens y "
            "caché leída sin medir\n"), "")


def test_pi_sesion_con_una_carpeta_sin_la_de_tareas_sale_con_2_sin_escribir_nada():
    with Temporal() as base:
        guardar_tarea(base / "agente", tarea_pi())
        for sesion in (base / "vacia", base / "otra" / "tasks"):
            sesion.mkdir(parents=True)
            assert cli_pi(base, "--sesion", sesion, "--destino", base / "d", "--corrida", "c=t1") == (
                2, "rescatar: no existe la carpeta de tareas de gentle-shell %s\n" % (sesion / "gentle-agents" / "tasks"), ""), sesion
        assert not (base / "d").exists()


HILO_CODEX = "01a218ab-7693-7ba0-a3cc-8e22dfc00781"
PADRE_CODEX = "01a218ab-3f79-7c11-b26b-6252fa646d66"
TURNO_CODEX = "01a218ab-7770-7fc0-86ee-382e6c538347"
MODELO_CODEX = "gpt-6-luna"
POWERSHELL_CODEX = "C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
INST_CODEX = "file:///C:/inst"
REPO_CODEX = "file:///C:/repo-a"
LEER_SKILLS = "Get-Content -Raw .claude/skills/criterios/SKILL.md; Get-Content -Raw tickets/T1-prueba/CLAUDE.md"
LEER_REPO = 'Get-Content src/a.ext; rg -n "\\b(total|promedio)\\b" src'
REPORTE_CODEX = "Sin hallazgos.\n\n**Alcance y límites:** revisé el diff de `src/a.ext`, el archivo completo y el ticket."
FINAL_CODEX = REPORTE_CODEX + "\n\nVEREDICTO: 0 CRITICAL, 0 WARNING, 0 SUGGESTION"
SIN_PROMPT_CODEX = "  (sin .prompt.txt: en Codex el prompt viaja cifrado y lo guarda el orquestador antes de lanzar)"
COSTO_CODEX = {"turnos": 3, "contexto_inicial": 21198, "contexto_final": 29649, "salida": 440, "cache_escrita": 0, "cache_leida": 50176,
               "inicio": "2026-11-26T16:23:40.000Z", "fin": "2026-11-26T16:23:52.000Z", "pausa_mayor": 1.0, "tokens_total": 73749,
               "costo_usd": None}


def meta_codex(rol="revisor-capa-a", subagente=True):
    carga = {"session_id": PADRE_CODEX, "id": HILO_CODEX, "timestamp": "2026-11-26T16:23:40.111Z", "cwd": "C:\\inst",
             "originator": "codex_exec", "cli_version": "0.171.0-alpha.13.2", "model_provider": "openai"}
    if subagente:
        lanzado_ = {"parent_thread_id": PADRE_CODEX, "depth": 1, "agent_path": "/root/revisor_capa_a", "agent_nickname": "Harvey",
                    "agent_role": rol}
        carga.update({"parent_thread_id": PADRE_CODEX, "source": {"subagent": {"thread_spawn": lanzado_}}, "thread_source": "subagent",
                      "agent_nickname": "Harvey", "agent_role": rol, "agent_path": "/root/revisor_capa_a"})
    else:
        carga.update({"id": PADRE_CODEX, "source": "exec"})
    return ("session_meta", carga)


def item_codex(item):
    return ("event_msg", {"type": "item_completed", "thread_id": HILO_CODEX, "turn_id": TURNO_CODEX, "item": item})


def mensaje_codex(texto, fase="commentary"):
    return item_codex({"type": "AgentMessage", "id": "msg_" + str(len(texto)), "content": [{"type": "Text", "text": texto}], "phase": fase})


def comando_codex(cmd, salida="", codigo=0, cwd=INST_CODEX):
    return item_codex({"type": "CommandExecution", "id": "exec-" + str(len(cmd)), "process_id": "76147",
                       "command": [POWERSHELL_CODEX, "-Command", cmd], "cwd": cwd, "parsed_cmd": [{"type": "unknown", "cmd": cmd}],
                       "source": "unified_exec_startup", "status": "completed" if codigo == 0 else "failed", "aggregated_output": salida,
                       "exit_code": codigo, "duration": {"secs": 0, "nanos": 446673000}})


def uso_codex(respuesta, entrada, cacheada, salida):
    return ("token_usage_record", {"thread_id": HILO_CODEX, "turn_id": TURNO_CODEX, "session_id": PADRE_CODEX, "response_id": respuesta,
                                   "usage": {"input_tokens": entrada, "cached_input_tokens": cacheada, "cache_write_input_tokens": 0,
                                             "output_tokens": salida, "reasoning_output_tokens": 0, "total_tokens": entrada + salida}})


def items_codex(final=FINAL_CODEX):
    return [mensaje_codex("Voy a leer las skills y el ticket."), uso_codex("resp_1", 21198, 0, 182),
            comando_codex(LEER_SKILLS, "CENTINELA criterios"), uso_codex("resp_2", 22462, 20992, 108),
            comando_codex(LEER_REPO, "Get-Content : No se encuentra la ruta de acceso", 1, REPO_CODEX), uso_codex("resp_3", 29649, 29184, 150),
            *([mensaje_codex(final, "final_answer")] if final is not None else []),
            ("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 73309, "output_tokens": 440}}})]


def rollout_codex(final=FINAL_CODEX, items=None, meta=None, fin=True):
    lineas = [meta or meta_codex(),
              ("event_msg", {"type": "task_started", "turn_id": TURNO_CODEX, "started_at": 1795710220, "model_context_window": 258400}),
              ("response_item", {"type": "agent_message", "author": "/root", "recipient": "/root/revisor_capa_a", "content": [
                  {"type": "input_text", "text": "Message Type: NEW_TASK\nTask name: /root/revisor_capa_a\nSender: /root\nPayload:\n"},
                  {"type": "encrypted_content", "encrypted_content": "gAAAAA-cifrado-por-codex"}]}),
              ("turn_context", {"turn_id": TURNO_CODEX, "cwd": "C:\\inst", "model": MODELO_CODEX, "effort": "low",
                                "sandbox_policy": {"type": "read-only"}})]
    lineas += items_codex(final) if items is None else items
    if fin:
        lineas.append(("event_msg", {"type": "task_complete", "turn_id": TURNO_CODEX, "last_agent_message": final,
                                     "started_at": 1795710220, "completed_at": 1795710271, "duration_ms": 51745}))
    return lineas


def guardar_rollout(home, lineas, hilo=HILO_CODEX, dia=("2026", "11", "26"), hora="11-23-40"):
    carpeta = home.joinpath("sessions", *dia)
    carpeta.mkdir(parents=True, exist_ok=True)
    acumulado, texto = {}, []
    for i, linea in enumerate(lineas):
        if isinstance(linea, str):
            texto.append(linea)
            continue
        tipo, carga = linea[0], dict(linea[1])
        if tipo == "token_usage_record":
            for clave, valor in carga["usage"].items():
                acumulado[clave] = acumulado.get(clave, 0) + valor
            carga.update({"turn_token_usage": dict(acumulado), "thread_token_usage": dict(acumulado)})
        texto.append(json.dumps({"timestamp": "2026-11-26T16:%02d:%02d.000Z" % (23 + (40 + i) // 60, (40 + i) % 60), "ordinal": i,
                                 "type": tipo, "payload": carga}, ensure_ascii=False))
    ruta = carpeta / ("rollout-%s-%s-%sT%s-%s.jsonl" % (dia[0], dia[1], dia[2], hora, hilo))
    ruta.write_bytes(("\n".join(texto) + "\n").encode("utf-8"))
    return ruta


def cli_codex(base, *args, entorno=None):
    env = {k: v for k, v in os.environ.items() if k != "CODEX_HOME"}
    env.update({"HOME": str(base / "casa"), "USERPROFILE": str(base / "casa")})
    env.update(entorno if entorno is not None else {"CODEX_HOME": str(base / "codex")})
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--host", "codex", *map(str, args)], capture_output=True, env=env)
    return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n"), r.stderr.decode("utf-8").replace("\r\n", "\n")


LECTURAS_CODEX = [{"tool": "CommandExecution", "input": {"command": [POWERSHELL_CODEX, "-Command", LEER_SKILLS], "cwd": INST_CODEX}, "exit": 0},
                  {"tool": "CommandExecution", "input": {"command": [POWERSHELL_CODEX, "-Command", LEER_REPO], "cwd": REPO_CODEX}, "exit": 1}]


def test_codex_rescata_el_reporte_sin_el_veredicto_las_lecturas_y_el_costo_y_no_escribe_el_prompt():
    with Temporal() as base:
        guardar_rollout(base / "codex", rollout_codex())
        codigo, salida, error = cli_codex(base, "--destino", base / "d", "--corrida", "revisor-capa-a-r1=" + HILO_CODEX)
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert salida == "ok   revisor-capa-a-r1: %d car., 2 lecturas, revisor-capa-a/%s%s\n" % (
            len(REPORTE_CODEX), MODELO_CODEX, SIN_PROMPT_CODEX), repr(salida)
        assert (base / "d" / "revisor-capa-a-r1.md").read_bytes() == REPORTE_CODEX.encode("utf-8")
        assert sorted(p.name for p in (base / "d").iterdir()) == ["revisor-capa-a-r1.lecturas.json", "revisor-capa-a-r1.md"]
        lecturas = leer_json(base / "d" / "revisor-capa-a-r1.lecturas.json")
        assert list(lecturas) == ["agente", "meta", "lecturas", "no_auditadas", "costo"], list(lecturas)
        assert (lecturas["agente"], lecturas["meta"]) == (HILO_CODEX, {"agentType": "revisor-capa-a", "model": MODELO_CODEX}), lecturas
        assert lecturas["lecturas"] == LECTURAS_CODEX, lecturas["lecturas"]
        assert lecturas["no_auditadas"] == {} and lecturas["costo"] == COSTO_CODEX, lecturas
        (base / "o").mkdir()
        (base / "o" / "c1.prompt.txt").write_bytes("El prompt que guardó el orquestador.\n".encode("utf-8"))
        assert cli_codex(base, "--destino", base / "o", "--corrida", "c1=" + HILO_CODEX)[0] == 0
        assert (base / "o" / "c1.prompt.txt").read_bytes() == "El prompt que guardó el orquestador.\n".encode("utf-8")
        r = m().extraer_corrida_codex(next((base / "codex" / "sessions").glob("*/*/*/rollout-*.jsonl")))
        assert (r["prompt"], r["reporte"], r["veredicto"], r["rol"]) == (
            None, REPORTE_CODEX, "VEREDICTO: 0 CRITICAL, 0 WARNING, 0 SUGGESTION", "revisor-capa-a"), r


def test_codex_tapa_los_secretos_del_prompt_que_guardo_el_orquestador_y_no_toca_uno_limpio():
    with Temporal() as base:
        guardar_rollout(base / "codex", rollout_codex())
        (base / "d").mkdir()
        sucio = "Revisa el diff; la clave de prueba es %s.\n" % AWS
        limpio = "Revisa el diff, sin secretos.\r\n".encode("utf-8")
        (base / "d" / "c1.prompt.txt").write_bytes(sucio.encode("utf-8"))
        (base / "d" / "c2.prompt.txt").write_bytes(limpio)
        codigo, salida, error = cli_codex(base, "--destino", base / "d", "--corrida", "c1=" + HILO_CODEX, "--corrida", "c2=" + HILO_CODEX,
                                          "--corrida", "c3=" + HILO_CODEX)
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        ok = "ok   %s: %d car., 2 lecturas, revisor-capa-a/%s%s%s"
        assert salida.splitlines() == [
            ok % ("c1", len(REPORTE_CODEX), MODELO_CODEX, "  (1 secreto(s) tapado(s) antes de guardar)", SIN_PROMPT_CODEX),
            ok % ("c2", len(REPORTE_CODEX), MODELO_CODEX, "", SIN_PROMPT_CODEX),
            ok % ("c3", len(REPORTE_CODEX), MODELO_CODEX, "", SIN_PROMPT_CODEX)], salida
        assert (base / "d" / "c1.prompt.txt").read_bytes() == sucio.replace(AWS, "<AWS_ACCESS_KEY_ID>").encode("utf-8")
        assert (base / "d" / "c2.prompt.txt").read_bytes() == limpio
        assert not (base / "d" / "c3.prompt.txt").exists()


def test_codex_costo_cuenta_la_cache_leida_dentro_de_la_entrada_y_deja_al_orquestador_en_null():
    with Temporal() as base:
        rev = revision(base)
        guardar_rollout(base / "codex", rollout_codex())
        codigo, salida, error = cli_codex(base, "--destino", rev / "corridas", "--corrida", "c1=" + HILO_CODEX, "--costo")
        assert (codigo, error) == (0, SIN_ORQUESTADOR_PI), (codigo, salida, error)
        assert salida.splitlines()[-1] == "costo: 1 corrida(s) en %s" % (rev / "corridas" / "costo.json"), salida
        assert leer_json(rev / "corridas" / "costo.json") == {"modo": "completo", "motivos": TRIAJE["motivos"], "corridas": [
            {"corrida": "c1", "agente": HILO_CODEX, "estado": "ok", "agentType": "revisor-capa-a", "model": MODELO_CODEX,
             "costo": COSTO_CODEX}], "lineas_diff": 4, "orquestador": None, "en_serie": None}
        assert cli("--ultimo-costo", base.joinpath(*TICKET_T1)) == (0, (
            "último costo medido, del ticket: tickets/T1-a/revision/2026-11-18-completo: modo completo, 1 corrida(s), 4 líneas "
            "de diff; por corrida, en promedio: 3 turnos, contexto final 29 649, salida 440, caché escrita 0 y caché leída "
            "50 176 tokens\n"), "")


def test_codex_un_hilo_que_no_es_de_un_revisor_falla_y_no_escribe_nada():
    with Temporal() as base:
        guardar_rollout(base / "codex", rollout_codex())
        guardar_rollout(base / "codex", rollout_codex(meta=meta_codex("writer-capa-a")), hilo="hilo-del-writer")
        guardar_rollout(base / "codex", rollout_codex(meta=meta_codex(subagente=False)), hilo="hilo-con-historia")
        guardar_rollout(base / "codex", rollout_codex(meta=meta_codex(None)), hilo="hilo-sin-rol")
        codigo, salida, error = cli_codex(base, "--destino", base / "d", "--corrida", "c1=" + HILO_CODEX, "--corrida", "c2=hilo-del-writer",
                                          "--corrida", "c3=hilo-con-historia", "--corrida", "c4=hilo-sin-rol")
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        lanzar = 'lanza cada revisor con su agent_type y fork_turns "none"'
        assert salida.splitlines()[1:] == [
            "FAIL c2: el hilo hilo-del-writer es de writer-capa-a, no de un revisor, no se escribio nada: %s" % lanzar,
            "FAIL c3: el hilo hilo-con-historia es de un agente sin agent_role, no de un revisor, no se escribio nada: %s" % lanzar,
            "FAIL c4: el hilo hilo-sin-rol es de un agente sin agent_role, no de un revisor, no se escribio nada: %s" % lanzar], salida
        assert sorted(p.name for p in (base / "d").iterdir()) == ["c1.lecturas.json", "c1.md"]


def test_codex_una_corrida_cortada_o_que_solo_devolvio_el_veredicto_falla_y_el_reporte_puede_ir_antes_del_veredicto():
    with Temporal() as base:
        solo = "VEREDICTO: 0 CRITICAL, 1 WARNING, 0 SUGGESTION"
        guardar_rollout(base / "codex", rollout_codex(fin=False), hilo="cortado")
        guardar_rollout(base / "codex", rollout_codex(final=None), hilo="sin-mensaje")
        guardar_rollout(base / "codex", rollout_codex(final=solo), hilo="solo")
        previo = items_codex(solo)
        previo.insert(-2, mensaje_codex("## Hallazgos\n[WARNING] sin ID a.ext:7 — divide por cero — valida la lista vacía"))
        guardar_rollout(base / "codex", rollout_codex(final=solo, items=previo), hilo="previo")
        codigo, salida, error = cli_codex(base, "--destino", base / "d", "--corrida", "c1=cortado", "--corrida", "c2=sin-mensaje",
                                          "--corrida", "c3=solo", "--corrida", "c4=previo")
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        assert salida.splitlines() == [
            "FAIL c1: hilo cortado sin task_complete con su mensaje final (corrida cortada), 2 lecturas, no se escribio nada",
            "FAIL c2: hilo sin-mensaje sin task_complete con su mensaje final (corrida cortada), 2 lecturas, no se escribio nada",
            "FAIL c3: el revisor devolvio solo el veredicto y su reporte no quedo como texto antes de la devolucion, 2 lecturas, "
            "no se escribio nada",
            "ok   c4: 79 car., 2 lecturas, revisor-capa-a/%s%s" % (MODELO_CODEX, SIN_PROMPT_CODEX)], salida
        assert (base / "d" / "c4.md").read_text(encoding="utf-8") == (
            "## Hallazgos\n[WARNING] sin ID a.ext:7 — divide por cero — valida la lista vacía"), salida
        assert sorted(p.name for p in (base / "d").iterdir()) == ["c4.lecturas.json", "c4.md"]


def test_codex_reconoce_las_formas_del_veredicto_al_final_del_reporte_y_un_reporte_sin_veredicto_queda_entero():
    reporte = "## Hallazgos\n[WARNING] sin ID a.ext:3 — x — y"
    with Temporal() as base:
        for i, forma in enumerate(FORMAS_DEL_VEREDICTO):
            ruta = guardar_rollout(base / "codex", rollout_codex(final="%s\n\n%s\n" % (reporte, forma)), hilo="f%d" % i)
            r = m().extraer_corrida_codex(ruta)
            assert (r["reporte"], r["veredicto"]) == (reporte, forma.strip()), (forma, r)
            r = m().extraer_corrida_codex(guardar_rollout(base / "codex", rollout_codex(final=forma), hilo="s%d" % i))
            assert (r["reporte"], r["origen"]) == (None, "solo_veredicto"), (forma, r)
        for devolucion in (VEREDICTO + "\n## Hallazgos\n[WARNING] sin ID a.sql:3", "Sin hallazgos.", "El veredicto final: revisa a.sql"):
            r = m().extraer_corrida_codex(guardar_rollout(base / "codex", rollout_codex(final=devolucion), hilo="g"))
            assert (r["reporte"], r["veredicto"]) == (devolucion, None), (devolucion, r)


def test_codex_lo_que_no_es_un_comando_ni_un_mensaje_sale_como_no_auditado():
    with Temporal() as base:
        items = items_codex()
        items[1:1] = [item_codex({"type": "Reasoning", "id": "rs_1", "summary": []}),
                      item_codex({"type": "FileChange", "id": "fc_1", "changes": [], "status": "completed"}), item_codex({"id": "sin-tipo"})]
        guardar_rollout(base / "codex", rollout_codex(items=items))
        codigo, salida, error = cli_codex(base, "--destino", base / "d", "--corrida", "c1=" + HILO_CODEX)
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert salida == "ok   c1: %d car., 2 lecturas, revisor-capa-a/%s  (herramientas NO auditadas: FileChange x1, sin tipo x1)%s\n" % (
            len(REPORTE_CODEX), MODELO_CODEX, SIN_PROMPT_CODEX), repr(salida)
        assert leer_json(base / "d" / "c1.lecturas.json")["no_auditadas"] == {"FileChange": 1, "sin tipo": 1}


def test_codex_busca_el_hilo_en_el_codex_home_y_sesion_lo_reemplaza():
    with Temporal() as base:
        guardar_rollout(base / "codex", rollout_codex(final="desde codex\n\n" + VEREDICTO))
        guardar_rollout(base / "casa" / ".codex", rollout_codex(final="desde casa\n\n" + VEREDICTO), dia=("2026", "11", "27"), hora="00-05-01")
        guardar_rollout(base / "otro", rollout_codex(final="desde otro\n\n" + VEREDICTO))
        casos = (({"CODEX_HOME": str(base / "codex")}, "desde codex"), ({}, "desde casa"), ({"CODEX_HOME": ""}, "desde casa"))
        for i, (entorno, esperado) in enumerate(casos):
            destino = base / ("d%d" % i)
            codigo, salida, error = cli_codex(base, "--destino", destino, "--corrida", "c=" + HILO_CODEX, entorno=entorno)
            assert (codigo, error) == (0, ""), (entorno, codigo, salida, error)
            assert (destino / "c.md").read_text(encoding="utf-8") == esperado, entorno
        for i, sesion in enumerate((base / "otro", base / "otro" / "sessions")):
            destino = base / ("s%d" % i)
            assert cli_codex(base, "--sesion", sesion, "--destino", destino, "--corrida", "c=" + HILO_CODEX)[0] == 0, sesion
            assert (destino / "c.md").read_text(encoding="utf-8") == "desde otro", sesion


def test_codex_un_hilo_que_no_existe_o_no_se_lee_es_un_fail_y_sin_carpeta_o_con_un_id_raro_sale_con_2():
    with Temporal() as base:
        guardar_rollout(base / "codex", rollout_codex())
        guardar_rollout(base / "codex", ["{roto", json.dumps({"type": "event_msg", "payload": {}})], hilo="roto")
        guardar_rollout(base / "codex", [], hilo="vacio")
        sesiones = base / "codex" / "sessions"
        codigo, salida, error = cli_codex(base, "--destino", base / "d", "--corrida", "c1=" + HILO_CODEX, "--corrida", "c2=nada",
                                          "--corrida", "c3=roto", "--corrida", "c4=vacio")
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        assert salida.splitlines()[1:] == [
            "FAIL c2: no existe rollout-*-nada.jsonl en %s" % sesiones,
            "FAIL c3: rollout-*-roto.jsonl no es un rollout de Codex que se pueda leer, no se escribio nada",
            "FAIL c4: rollout-*-vacio.jsonl no es un rollout de Codex que se pueda leer, no se escribio nada"], salida
        vacio = base / "vacio"
        assert cli_codex(base, "--destino", base / "d2", "--corrida", "c=" + HILO_CODEX, entorno={"CODEX_HOME": str(vacio)}) == (
            2, "rescatar: no existe la carpeta de sesiones de Codex %s\n" % (vacio / "sessions"), "")
        for corrida in ("c=../x", "c=*", "c=a?b", "c=[0-9]", "c=", "sin-igual"):
            assert cli_codex(base, "--destino", base / "d3", "--corrida", corrida) == (
                2, "rescatar: --corrida espera <nombre>=<thread_id>, recibio %r\n" % corrida, ""), corrida
        assert not (base / "d2").exists() and not (base / "d3").exists()
        codigo, salida, error = cli_codex(base)
        assert (codigo, salida) == (2, "") and error.splitlines()[-1] == (
            "rescatar.py: error: the following arguments are required: --destino, --corrida"), error


def test_codex_tolera_la_linea_rota_y_la_avisa_por_stderr():
    with Temporal() as base:
        lineas = rollout_codex()
        lineas.insert(5, '{"timestamp": "2026-11-26T16:23:45.000Z", "type": "event_m')
        guardar_rollout(base / "codex", lineas)
        codigo, salida, error = cli_codex(base, "--destino", base / "d", "--corrida", "c1=" + HILO_CODEX)
        assert codigo == 0 and salida.startswith("ok   c1: %d car., 2 lecturas" % len(REPORTE_CODEX)), (codigo, salida)
        assert error == "aviso c1: 1 linea(s) de rollout-*-%s.jsonl no se pudieron leer y se saltearon\n" % HILO_CODEX, repr(error)


def test_codex_no_cambia_lo_que_escriben_claude_code_y_pi():
    with Temporal() as base:
        agente(base / "subagents", "abc", tipica())
        codigo, salida, error = cli("--sesion", base / "subagents", "--destino", base / "cc", "--corrida", "c1=abc")
        assert (codigo, salida, error) == (0, "ok   c1: 32 car., 3 lecturas, revisor-x/opus  (herramientas NO auditadas: Bash x1)  "
                                              "(comandos Bash/PowerShell: 1 en c1.comandos.json)\n", ""), (codigo, salida, error)
        assert sorted(p.name for p in (base / "cc").iterdir()) == ["c1.comandos.json", "c1.lecturas.json", "c1.md", "c1.prompt.txt"]
        assert (base / "cc" / "c1.prompt.txt").read_text(encoding="utf-8") == "Revisa el cambio antes del commit."
        guardar_tarea(base / "agente", tarea_pi())
        codigo, salida, error = cli_pi(base, "--destino", base / "pi", "--corrida", "c1=t1")
        assert (codigo, salida, error) == (0, "ok   c1: 14 car., 3 lecturas, revisor-diseno/%s\n" % MODELO_PI, ""), (codigo, salida, error)
        assert (base / "pi" / "c1.prompt.txt").read_text(encoding="utf-8") == PROMPT_PI


OPCION_RE = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
SKILL_REVISAR = AQUI.parent / "skills" / "revisar" / "SKILL.md"
REFERENCIA_RE = re.compile(r"references/([\w.-]+\.md)")


def texto_de_revisar():
    nucleo = SKILL_REVISAR.read_text(encoding="utf-8")
    referencias = [(SKILL_REVISAR.parent / "references" / nombre).read_text(encoding="utf-8")
                   for nombre in sorted(set(REFERENCIA_RE.findall(nucleo)))]
    return "\n\n".join([nucleo, *referencias])


def test_los_rescates_que_da_la_skill_revisar_usan_opciones_que_existen_y_traen_el_de_pi_y_el_de_codex():
    texto = texto_de_revisar()
    lineas = [l.split("rescatar.py", 1)[1] for l in texto.split("\n") if "rescatar.py\"" in l and "--destino" in l]
    assert len(lineas) == 3, lineas
    opciones = {o for accion in m()._parser()._actions for o in accion.option_strings}
    for linea in lineas:
        assert set(OPCION_RE.findall(linea)) <= opciones, (linea, set(OPCION_RE.findall(linea)) - opciones)
    assert any("--host pi" in l and "--sesion" not in l and "<task_id>" in l for l in lineas), lineas
    assert any("--host" not in l and "--sesion" in l and "<agentId>" in l for l in lineas), lineas
    assert any("--host codex" in l and "--sesion" not in l and "<thread_id>" in l for l in lineas), lineas
    for frase in ("subagent_run", "background", "task_id", "subagent_result", "16 KB", 'fork_turns: "none"', "agent_type", "CODEX_HOME",
                  ".prompt.txt", "I35"):
        assert frase in texto, frase


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
