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
        assert list(lecturas) == ["agente", "meta", "lecturas", "no_auditadas"], list(lecturas)
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
