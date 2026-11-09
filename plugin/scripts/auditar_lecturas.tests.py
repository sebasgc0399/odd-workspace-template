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
SCRIPT = AQUI / "auditar_lecturas.py"
RESCATAR = AQUI / "rescatar.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []

CWD = "C:\\inst"
SECRETO = "C:\\inst\\secreto"
VERDAD = "C:\\inst\\casos\\uno\\revision\\verdad.md"
DIFFS = ["C:\\inst\\casos\\uno\\revision\\a.diff", "C:\\inst\\casos\\uno\\revision\\b.diff"]
CARPETA_CASO = "C:\\inst\\casos\\uno"


def m():
    return importlib.import_module("auditar_lecturas")


def capas():
    return importlib.import_module("odd_ws.capas")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Temporal:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="auditar-test-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def reglas(prohibidas=(), permitidas=()):
    return m().armar_reglas(list(prohibidas), list(permitidas), CWD)


def niveles(informe):
    return [h["nivel"] for h in informe["hallazgos"]]


def auditar(lecturas, rs, ceguera=False):
    return m().auditar(lecturas, rs, CWD, ceguera)


def lectura(herramienta, **entrada):
    return {"tool": herramienta, "input": entrada}


def escribir_json(ruta, datos):
    Path(ruta).write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def lecturas_json(base, nombre, lecturas, agente="ag", **extra):
    return escribir_json(base / nombre, {"agente": agente, "meta": {}, "lecturas": lecturas, **extra})


def jsonl(base, nombre, lineas):
    ruta = base / nombre
    ruta.write_bytes(("\n".join(l if isinstance(l, str) else json.dumps(l) for l in lineas) + "\n").encode("utf-8"))
    return ruta


def asistente(*bloques):
    return {"type": "assistant", "message": {"content": list(bloques)}}


def uso(nombre, entrada):
    return {"type": "tool_use", "name": nombre, "input": entrada}


def enlazar(enlace, destino):
    try:
        os.symlink(destino, enlace, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        return subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], capture_output=True).returncode == 0
    return False


def desenlazar(enlace):
    if os.path.lexists(enlace):
        (os.rmdir if os.name == "nt" else os.unlink)(enlace)


def instancia(base):
    base.mkdir(parents=True, exist_ok=True)
    (base / "workspace.config.json").write_text(json.dumps({"schema_version": 1, "repos": {}}), encoding="utf-8")
    return base


def entorno(**sobre):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.update(sobre)
    return env


def cli(*args, cwd=None, env=None):
    r = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), *map(str, args)], capture_output=True, cwd=cwd, env=env or entorno())
    return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n"), r.stderr.decode("utf-8").replace("\r\n", "\n")


def test_normalizar_ruta_windows_y_msys():
    esperado = "c:/inst/docs/x.md"
    for crudo in ("C:\\inst\\docs\\x.md", "c:/INST/docs/x.md", "C:/inst/docs/x.md/", "c:\\inst\\docs\\.\\a\\..\\x.md", "/c/inst/docs/x.md",
                  "\\\\?\\C:\\inst\\docs\\x.md"):
        assert m().normalizar_ruta(crudo, CWD) == esperado, (crudo, m().normalizar_ruta(crudo, CWD))
    assert m().normalizar_ruta("docs\\x.md", CWD) == esperado


def test_una_ruta_que_pasa_por_un_enlace_se_compara_por_la_carpeta_real():
    with Temporal() as base:
        real, enlace = base / "real", base / "enlace"
        (real / "secreto" / "abierto").mkdir(parents=True)
        if not enlazar(enlace, real):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        try:
            for regla, otra in ((enlace, real), (real, enlace)):
                rs = m().armar_reglas([str(regla / "secreto")], [str(regla / "secreto" / "abierto")], str(base))
                inf = m().auditar([lectura("Read", file_path=str(otra / "secreto" / "x.md")),
                                   lectura("Grep", pattern="x", path=str(otra / "secreto")),
                                   lectura("Glob", pattern="*.md", path=str(otra)),
                                   lectura("Read", file_path=str(otra / "secreto" / "abierto" / "a.md"))], rs, str(base))
                assert niveles(inf) == ["contaminado", "exposicion", "exposicion"], (regla, inf["hallazgos"])
                assert [h["indice"] for h in inf["hallazgos"]] == [0, 1, 2], (regla, inf["hallazgos"])
        finally:
            desenlazar(enlace)


def test_cli_lee_por_el_enlace_lo_que_la_regla_prohibe_por_la_ruta_real():
    with Temporal() as base:
        real, enlace = base / "real", base / "enlace"
        raiz = instancia(real / "inst")
        (raiz / "sub").mkdir()
        if not enlazar(enlace, real):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        try:
            f = lecturas_json(base, "a.lecturas.json", [lectura("Read", file_path="secreto\\y.md"), lectura("Grep", pattern="x")])
            codigo, salida, error = cli(f, "--prohibida", str(raiz / "secreto"), "--json", cwd=enlace / "inst" / "sub")
            assert codigo == 1 and error == "", (codigo, salida, error)
            h = json.loads(salida)["archivos"][0]["hallazgos"]
            assert [(x["indice"], x["nivel"]) for x in h] == [(0, "contaminado"), (1, "exposicion")], h
        finally:
            desenlazar(enlace)


def test_es_bajo_exige_limite_de_segmento():
    assert m().es_bajo("c:/inst/a/x.md", "c:/inst/a")
    assert m().es_bajo("c:/inst/a", "c:/inst/a")
    assert not m().es_bajo("c:/inst/aa/x.md", "c:/inst/a")


def test_read_prohibido_es_contaminado_con_su_hallazgo_completo():
    inf = auditar([lectura("Read", file_path=VERDAD)], reglas([VERDAD]))
    assert inf["total"] == 1 and inf["estado"] == "contaminado", inf
    assert inf["hallazgos"] == [{
        "indice": 0, "tool": "Read", "entrada": {"file_path": VERDAD}, "tipo": "lectura_prohibida", "nivel": "contaminado",
        "alcance": VERDAD, "reglas": [VERDAD], "motivo": "Read de un archivo bajo una ruta prohibida"}], inf["hallazgos"]


def test_read_bajo_carpeta_prohibida_y_relativo_son_contaminado():
    rs = reglas([SECRETO])
    assert niveles(auditar([lectura("Read", file_path="c:/INST/secreto/tareas/x.md")], rs)) == ["contaminado"]
    assert niveles(auditar([lectura("Read", file_path="secreto\\tareas\\x.md")], rs)) == ["contaminado"]
    assert niveles(auditar([lectura("Read", path=SECRETO + "\\y.md")], rs)) == ["contaminado"]


def test_read_permitido_dentro_de_prohibido_gana_la_mas_especifica():
    rs = reglas([CARPETA_CASO], DIFFS)
    inf = auditar([lectura("Read", file_path=DIFFS[1]), lectura("Read", file_path=CARPETA_CASO + "\\notas.md")], rs)
    assert niveles(inf) == ["contaminado"] and inf["hallazgos"][0]["indice"] == 1, inf["hallazgos"]


def test_si_la_misma_ruta_es_prohibida_y_permitida_gana_la_prohibida():
    for orden in (([SECRETO], [SECRETO]), ([SECRETO], [SECRETO.upper()])):
        assert niveles(auditar([lectura("Read", file_path=SECRETO + "\\x.md")], reglas(*orden))) == ["contaminado"], orden
    assert niveles(auditar([lectura("Grep", pattern="x", path=SECRETO)], reglas([SECRETO], [SECRETO]))) == ["exposicion"]


def test_read_ajeno_hermano_o_sin_ruta_no_se_marca():
    rs = reglas([SECRETO])
    inf = auditar([lectura("Read", file_path="C:\\inst\\secretos\\a.md"), lectura("Read", file_path="C:\\inst\\docs\\g.md"),
                   lectura("Read"), {"tool": "Read"}, {"tool": "Bash", "input": {"command": "ls"}}, {"input": {}}], rs)
    assert inf == {"total": 6, "estado": "limpio", "hallazgos": []}, inf


def test_grep_sobre_ancestro_es_exposicion_y_el_glob_de_exclusion_no_exime():
    inf = auditar([lectura("Grep", pattern="x", path=CARPETA_CASO, glob="!revision/**")], reglas([VERDAD]))
    assert inf["estado"] == "exposicion", inf
    assert inf["hallazgos"] == [{
        "indice": 0, "tool": "Grep", "entrada": {"path": CARPETA_CASO, "pattern": "x", "glob": "!revision/**"},
        "tipo": "busqueda_alcance_prohibido", "revela": "contenido", "nivel": "exposicion", "alcance": CARPETA_CASO, "reglas": [VERDAD],
        "motivo": "el alcance de la busqueda contiene o esta dentro de una ruta prohibida"}], inf["hallazgos"]


def test_grep_sin_path_usa_el_cwd_recibido():
    inf = auditar([lectura("Grep", pattern="x", type="md")], reglas([SECRETO]))
    assert niveles(inf) == ["exposicion"] and inf["hallazgos"][0]["alcance"] == "(cwd C:\\inst)", inf["hallazgos"]
    assert niveles(m().auditar([lectura("Grep", pattern="x")], reglas([SECRETO]), "C:\\otra", False)) == []


def test_grep_o_glob_dentro_de_la_prohibida_es_exposicion():
    inf = auditar([lectura("Grep", pattern="x", path=SECRETO + "\\tareas"), lectura("Glob", pattern="*.md", path=SECRETO)], reglas([SECRETO]))
    assert niveles(inf) == ["exposicion", "exposicion"]


def test_grep_dentro_de_permitida_o_en_zona_ajena_no_se_marca():
    inf = auditar([lectura("Grep", pattern="x", path="C:\\tmp\\run1\\copia"), lectura("Grep", pattern="x", path="C:\\inst\\docs"),
                   lectura("Grep", pattern="x", path="C:\\inst\\secretos")], reglas([SECRETO, "C:\\tmp"], ["C:\\tmp\\run1"]))
    assert inf["hallazgos"] == [], inf["hallazgos"]


def test_glob_con_patron_absoluto_usa_su_prefijo_literal():
    inf = auditar([lectura("Glob", pattern="C:/inst/secreto/**/*.md"), lectura("Glob", pattern="C:/inst/docs/*.md")], reglas([SECRETO]))
    assert niveles(inf) == ["exposicion"] and inf["hallazgos"][0]["indice"] == 0, inf["hallazgos"]


def test_glob_relativo_suma_su_prefijo_al_path_y_revela_nombres():
    inf = auditar([lectura("Glob", pattern="casos/uno/*", path=CWD), lectura("Glob", pattern="secreto/**/*.md", path=CWD),
                   lectura("Glob", pattern="*.md", path=CWD)], reglas([SECRETO]))
    assert [h["indice"] for h in inf["hallazgos"]] == [1, 2], inf["hallazgos"]
    assert {h["revela"] for h in inf["hallazgos"]} == {"nombres"}
    assert auditar([lectura("Grep", pattern="x", path=CWD)], reglas([SECRETO]))["hallazgos"][0]["revela"] == "contenido"
    for patron, esperado in (("C:/inst/secreto/**/*.md", "C:/inst/secreto"), ("casos/x/*", "casos/x"), ("**/*", ""), ("*.sql", ""),
                             ("C:/*.sql", "C:/"), ("/c/inst/*", "/c/inst"), ("a/b.sql", "a/b.sql"), ("/*.md", "/"), ("a{b,c}/x", "")):
        assert m()._prefijo_literal(patron) == esperado, (patron, m()._prefijo_literal(patron))


def test_ceguera_fisica_baja_a_info_solo_lo_que_estaba_oculto():
    busqueda = [lectura("Grep", pattern="x", path=CARPETA_CASO)]
    assert niveles(auditar(busqueda, reglas([VERDAD]), True)) == ["info"]
    assert auditar(busqueda, reglas([VERDAD]), True)["estado"] == "limpio"
    assert niveles(auditar(busqueda, reglas([CARPETA_CASO]), True)) == ["exposicion"], "la carpeta viva no se movio del disco"
    assert niveles(auditar(busqueda, reglas([VERDAD]), False)) == ["exposicion"]
    assert niveles(auditar([lectura("Read", file_path=VERDAD)], reglas([VERDAD]), True)) == ["contaminado"], "un Read nunca baja"
    mixta = auditar(busqueda, reglas([VERDAD, SECRETO + "\\x"]), True)
    assert niveles(mixta) == ["info"], "la segunda regla no esta bajo el alcance: no cuenta"
    dos = auditar([lectura("Grep", pattern="x", path=CWD)], reglas([VERDAD, SECRETO]), True)
    assert niveles(dos) == ["exposicion"], "si alguna regla pegada no estaba oculta, no baja"


def test_la_carpeta_de_la_verdad_sale_de_la_convencion():
    original = capas().CARPETA_VERDAD
    try:
        capas().CARPETA_VERDAD = "veredicto"
        assert m()._es_fisica("c:/inst/caso/veredicto/a.md") and not m()._es_fisica("c:/inst/caso/revision/a.md")
        assert niveles(auditar([lectura("Grep", pattern="x", path=CWD)], reglas(["C:\\inst\\caso\\veredicto\\a.md"]), True)) == ["info"]
    finally:
        capas().CARPETA_VERDAD = original
    assert m()._es_fisica("c:/inst/caso/revision/a.md") and not m()._es_fisica("c:/inst/caso/revisiones/a.md")


def test_leer_lecturas_json_trae_no_auditadas_y_jsonl_las_cuenta():
    with Temporal() as base:
        a = lecturas_json(base, "a.lecturas.json", [lectura("Read", file_path="x")], agente="ag1", no_auditadas={"Bash": 2})
        sin = escribir_json(base / "b.lecturas.json", {"lecturas": []})
        j = jsonl(base, "agent-ag2.jsonl", [
            {"type": "user", "message": {"content": "prompt"}},
            asistente(uso("Read", {"file_path": "x"}), uso("Bash", {"command": "ls"}), uso("Grep", {"pattern": "p"}),
                      uso("SubagentHandback", {"message": "r"}), uso("Bash", {"command": "pwd"})), ""])
        assert m().leer_lecturas(a) == {"agente": "ag1", "meta": {}, "lecturas": [lectura("Read", file_path="x")],
                                        "no_auditadas": {"Bash": 2}, "salteadas": 0}
        assert m().leer_lecturas(sin) == {"agente": None, "meta": {}, "lecturas": [], "no_auditadas": {}, "salteadas": 0}
        d = m().leer_lecturas(j)
        assert d == {"agente": "ag2", "meta": {}, "lecturas": [lectura("Read", file_path="x"), lectura("Grep", pattern="p")],
                     "no_auditadas": {"Bash": 2}, "salteadas": 0}, d
        assert m().leer_lecturas(jsonl(base, "otro.jsonl", [asistente(uso("Read", {"file_path": "y"}))]))["agente"] == "otro"
        try:
            m().leer_lecturas(escribir_json(base / "malo.json", {"x": 1}))
        except ValueError as exc:
            assert "no tiene la clave 'lecturas'" in str(exc), exc
        else:
            raise AssertionError("un .json sin lecturas debe fallar")


def test_leer_lecturas_jsonl_tolera_la_linea_a_medio_escribir_y_la_cuenta():
    with Temporal() as base:
        j = jsonl(base, "agent-x.jsonl", [asistente(uso("Read", {"file_path": "a"})), '{"type": "assistant", "message": {"content": [{"type": "tool_u',
                                          asistente(uso("Glob", {"pattern": "*"}), uso("Bash", {"command": "ls"})), '{"type": "assis'])
        d = m().leer_lecturas(j)
        assert [x["tool"] for x in d["lecturas"]] == ["Read", "Glob"] and d["no_auditadas"] == {"Bash": 1} and d["salteadas"] == 2, d


def test_leer_lecturas_jsonl_inexistente_falla_con_oserror():
    with Temporal() as base:
        try:
            m().leer_lecturas(base / "agent-no.jsonl")
        except OSError:
            pass
        else:
            raise AssertionError("un jsonl que no abre debe fallar con OSError")


def test_rutas_de_manifest_sustituye_scratch():
    with Temporal() as base:
        manifest = escribir_json(base / "m.json", {"prohibidas": [SECRETO], "permitidas": ["{scratch}", "{scratch}\\sub", "C:\\x\\a.diff"]})
        assert m().rutas_de_manifest(manifest, "C:\\run1") == ([SECRETO], ["C:\\run1", "C:\\run1\\sub", "C:\\x\\a.diff"])
        assert m().rutas_de_manifest(manifest, None) == ([SECRETO], ["C:\\x\\a.diff"])
        assert m().rutas_de_manifest(escribir_json(base / "v.json", {}), None) == ([], [])


def test_rutas_ocultas_del_scratch_y_de_movidos_json():
    with Temporal() as base:
        scratch = base / "run1"
        scratch.mkdir()
        s = str(scratch)
        assert m().rutas_ocultas(scratch) == [s + ".oculto", s + "\\oculto"]
        assert m().rutas_ocultas(s + "\\") == [s + ".oculto", s + "\\oculto"]
        escribir_json(scratch / "movidos.json", {"oculto_raiz": "D:\\guardado"})
        assert m().rutas_ocultas(scratch) == ["D:\\guardado"]
        escribir_json(scratch / "movidos.json", {"otra": 1})
        assert m().rutas_ocultas(scratch) == [s + ".oculto", s + "\\oculto"]
        (scratch / "movidos.json").write_text("{roto", encoding="utf-8")
        assert m().rutas_ocultas(scratch) == [s + ".oculto", s + "\\oculto"]
        escribir_json(scratch / "movidos.json", {"oculto_raiz": s + ".oculto"})
        rs = m().armar_reglas(m().rutas_ocultas(scratch), [s], CWD)
        inf = m().auditar([lectura("Grep", pattern="x", path=str(scratch.parent)), lectura("Grep", pattern="x", path=s + "\\copia"),
                           lectura("Grep", pattern="x", path=s)], rs, CWD, True)
        assert niveles(inf) == ["exposicion"] and inf["hallazgos"][0]["indice"] == 0, inf["hallazgos"]


def test_la_carpeta_oculta_sale_de_la_convencion():
    original = capas().CARPETA_OCULTA
    try:
        capas().CARPETA_OCULTA = "guardado"
        assert m().rutas_ocultas("C:\\run1") == ["C:\\run1.guardado", "C:\\run1\\guardado"]
    finally:
        capas().CARPETA_OCULTA = original
    assert m().rutas_ocultas("C:\\run1") == ["C:\\run1.oculto", "C:\\run1\\oculto"]


def test_cli_codigos_de_salida_0_1_2():
    with Temporal() as base:
        manifest = escribir_json(base / "m.json", {"prohibidas": [SECRETO], "permitidas": []})
        limpio = lecturas_json(base, "limpio.lecturas.json", [lectura("Read", file_path="C:\\inst\\CLAUDE.md")])
        sucio = lecturas_json(base, "sucio.lecturas.json", [lectura("Read", file_path=SECRETO + "\\x.md")], agente="b")
        assert cli(limpio, "--manifest", manifest, "--cwd", CWD)[0] == 0
        assert cli(limpio, sucio, "--manifest", manifest, "--cwd", CWD)[0] == 1
        assert cli(sucio, "--prohibida", SECRETO, "--cwd", CWD)[0] == 1
        assert cli(sucio, "--prohibida", SECRETO, "--permitida", SECRETO + "\\x.md", "--cwd", CWD)[0] == 0
        codigo, salida, error = cli(base / "no-existe.json", "--manifest", manifest, "--cwd", CWD)
        assert codigo == 2 and salida.startswith("auditar_lecturas: no pude leer ") and "no-existe.json" in salida, (codigo, salida)
        codigo, salida, error = cli(limpio, "--manifest", base / "no-hay.json", "--cwd", CWD)
        assert codigo == 2 and salida.startswith("auditar_lecturas: no pude leer el manifest ("), (codigo, salida)
        codigo, salida, error = cli(limpio, "--cwd", CWD)
        assert (codigo, salida) == (2, "auditar_lecturas: no hay rutas prohibidas (usa --manifest o --prohibida)\n"), (codigo, salida)
        codigo, salida, error = cli(escribir_json(base / "x.json", {"nada": 1}), "--prohibida", SECRETO, "--cwd", CWD)
        assert codigo == 2 and "no tiene la clave 'lecturas'" in salida, (codigo, salida)
        codigo, salida, error = cli("--prohibida", SECRETO)
        assert codigo == 2 and salida == "" and "required" in error, (codigo, salida, error)


def test_cli_resumen_legible_exacto():
    with Temporal() as base:
        sucio = lecturas_json(base, "sucio.lecturas.json", [lectura("Read", file_path=SECRETO + "\\x.md"), lectura("Grep", pattern="x", path=CWD)],
                              agente="b", no_auditadas={"Bash": 2, "PowerShell": 1})
        codigo, salida, error = cli(sucio, "--prohibida", SECRETO, "--cwd", CWD)
        assert codigo == 1 and error == "", (codigo, error)
        assert salida.splitlines() == [
            "auditar_lecturas: 1 archivo(s); 1 regla(s) prohibida(s), 0 permitida(s); ceguera fisica: no",
            "",
            "[CONTAMINADO] %s  (agente b, 2 lecturas auditadas)" % sucio,
            "   aviso: herramientas NO auditadas: Bash x2, PowerShell x1",
            "   #0 Read   CONTAMINADO %s\\x.md" % SECRETO,
            "        regla: %s" % SECRETO,
            "   #1 Grep   EXPOSICION  C:\\inst  [revela contenido]",
            "        regla: %s" % SECRETO,
            "",
            "RESUMEN: 0 limpio(s), 0 con exposicion posible, 1 contaminado(s)",
            "Recordatorio: EXPOSICION es «pudo ver», no «vio» -- se resuelve leyendo el reporte (¿cito algo",
            "de esa ruta?). CONTAMINADO descarta la corrida de la medicion salvo prueba en contrario."], salida.splitlines()


def test_cli_info_se_oculta_salvo_con_v():
    with Temporal() as base:
        f = lecturas_json(base, "a.lecturas.json", [lectura("Grep", pattern="x", path=CARPETA_CASO)])
        codigo, salida, _ = cli(f, "--prohibida", VERDAD, "--ceguera-fisica", "--cwd", CWD)
        assert codigo == 0 and "(1 hallazgo(s) en INFO por ceguera fisica; --v los lista)" in salida and "#0" not in salida, salida
        assert "ceguera fisica: si" in salida
        codigo, salida, _ = cli(f, "--prohibida", VERDAD, "--ceguera-fisica", "--v", "--cwd", CWD)
        assert codigo == 0 and "   #0 Grep   INFO        %s  [revela contenido]" % CARPETA_CASO in salida and "--v los lista" not in salida, salida


def test_cli_json_y_salida_escriben_el_mismo_informe_y_solo_con_salida():
    with Temporal() as base:
        manifest = escribir_json(base / "m.json", {"prohibidas": [SECRETO], "permitidas": ["{scratch}"]})
        f = lecturas_json(base, "a.lecturas.json", [lectura("Read", file_path=SECRETO + "\\x.md")], agente="a", no_auditadas={"Bash": 1})
        informe = base / "informe.json"
        codigo, salida, _ = cli(f, "--manifest", manifest, "--scratch", base / "run", "--cwd", CWD, "--json", "--salida", informe)
        assert codigo == 1
        impreso = json.loads(salida)
        assert impreso == json.loads(informe.read_text(encoding="utf-8")), "stdout y --salida llevan el mismo informe"
        crudo = informe.read_bytes()
        assert b"\r\n" not in crudo and b"\n" in crudo and not crudo.startswith(b"\xef\xbb\xbf"), crudo[:80]
        assert list(impreso) == ["ceguera_fisica", "cwd", "reglas", "archivos", "resumen"], list(impreso)
        assert impreso["cwd"] == CWD and impreso["ceguera_fisica"] is False
        assert impreso["resumen"] == {"limpio": 0, "exposicion": 0, "contaminado": 1}
        scratch = str(base / "run")
        assert impreso["reglas"] == {"prohibidas": [SECRETO, scratch + ".oculto", scratch + "\\oculto"], "permitidas": [scratch]}, impreso["reglas"]
        a = impreso["archivos"][0]
        assert a["fuente"] == str(f) and a["agente"] == "a" and a["no_auditadas"] == {"Bash": 1} and a["estado"] == "contaminado", a
        assert list(a) == ["total", "estado", "hallazgos", "fuente", "agente", "no_auditadas"], list(a)
        sin_salida = base / "no-debe-existir.json"
        cli(f, "--prohibida", SECRETO, "--cwd", CWD, "--json")
        assert not sin_salida.exists() and sorted(p.name for p in base.iterdir()) == ["a.lecturas.json", "informe.json", "m.json"]


def test_cli_la_busqueda_sin_path_audita_contra_la_raiz_de_la_instancia():
    with Temporal() as base:
        raiz = instancia(base / "inst")
        (raiz / "sub" / "hondo").mkdir(parents=True)
        f = lecturas_json(base, "a.lecturas.json", [lectura("Grep", pattern="x"), lectura("Read", file_path="secreto\\y.md")])
        secreto = str(raiz / "secreto")
        codigo, salida, error = cli(f, "--prohibida", secreto, "--json", cwd=raiz / "sub" / "hondo")
        assert codigo == 1 and error == "", (codigo, error)
        informe = json.loads(salida)
        assert os.path.samefile(informe["cwd"], raiz), informe["cwd"]
        h = informe["archivos"][0]["hallazgos"]
        assert [(x["indice"], x["nivel"]) for x in h] == [(0, "exposicion"), (1, "contaminado")], h
        assert h[0]["alcance"] == "(cwd %s)" % informe["cwd"], h[0]


def test_cli_la_raiz_sale_del_entorno_de_la_sesion_antes_que_del_cwd():
    with Temporal() as base:
        raiz = instancia(base / "inst")
        f = lecturas_json(base, "a.lecturas.json", [lectura("Grep", pattern="x")])
        codigo, salida, _ = cli(f, "--prohibida", str(raiz / "secreto"), "--json", cwd=base, env=entorno(CLAUDE_PROJECT_DIR=str(raiz)))
        assert codigo == 1 and json.loads(salida)["cwd"] == os.path.abspath(raiz), (codigo, salida)


def test_cli_sin_raiz_ni_cwd_falla_con_2_y_con_cwd_no_la_necesita():
    with Temporal() as base:
        f = lecturas_json(base, "a.lecturas.json", [lectura("Grep", pattern="x")])
        codigo, salida, error = cli(f, "--prohibida", "C:\\inst\\secreto", cwd=base)
        assert (codigo, salida, error) == (2, "auditar_lecturas: no hay workspace.config.json en la carpeta de la sesion ni en sus padres (pasa --cwd)\n", ""), (codigo, salida, error)
        codigo, salida, error = cli(f, "--prohibida", "C:\\inst\\secreto", "--cwd", CWD, "--json", cwd=base)
        assert codigo == 1 and json.loads(salida)["cwd"] == CWD
        raiz = instancia(base / "inst")
        codigo, salida, _ = cli(f, "--prohibida", "C:\\inst\\secreto", "--cwd", CWD, "--json", cwd=raiz)
        assert json.loads(salida)["cwd"] == CWD, "--cwd explicito gana sobre la raiz de la instancia"


def test_cli_audita_un_jsonl_sintetico_con_el_caso_de_filtracion_por_glob():
    with Temporal() as base:
        j = jsonl(base, "agent-abc.jsonl", [
            {"type": "user", "message": {"content": "revisa"}},
            asistente(uso("Grep", {"pattern": "x", "path": CARPETA_CASO, "glob": "!revision/**"}),
                      uso("Read", {"file_path": "C:\\inst\\casos\\uno\\cambio.diff"}), uso("Bash", {"command": "ls"})),
            asistente(uso("SubagentHandback", {"message": "listo"}))])
        manifest = escribir_json(base / "m.json", {"prohibidas": [VERDAD], "permitidas": DIFFS})
        codigo, salida, _ = cli(j, "--manifest", manifest, "--cwd", CWD, "--json")
        a = json.loads(salida)["archivos"][0]
        assert codigo == 1 and a["estado"] == "exposicion" and a["agente"] == "abc" and a["no_auditadas"] == {"Bash": 1}, (codigo, a)
        marcadas = [h for h in a["hallazgos"] if h["tool"] == "Grep" and h["entrada"].get("glob") == "!revision/**"]
        assert len(marcadas) == 1 and marcadas[0]["nivel"] == "exposicion" and not any(h["nivel"] == "contaminado" for h in a["hallazgos"]), a
        codigo, salida, _ = cli(j, "--manifest", manifest, "--cwd", CWD, "--ceguera-fisica", "--json")
        a = json.loads(salida)["archivos"][0]
        assert codigo == 0 and a["estado"] == "limpio" and [h["nivel"] for h in a["hallazgos"]] == ["info"], (codigo, a)


def test_cli_tolera_la_linea_rota_de_un_jsonl_y_la_avisa_por_stderr():
    with Temporal() as base:
        j = jsonl(base, "agent-abc.jsonl", [asistente(uso("Read", {"file_path": SECRETO + "\\x.md"})), '{"type": "assistant", "mess'])
        codigo, salida, error = cli(j, "--prohibida", SECRETO, "--cwd", CWD, "--json")
        assert codigo == 1 and json.loads(salida)["archivos"][0]["estado"] == "contaminado", (codigo, salida)
        assert error == "aviso %s: 1 linea(s) no se pudieron leer y se saltearon\n" % j, repr(error)
        limpio = jsonl(base, "agent-ok.jsonl", [asistente(uso("Read", {"file_path": "C:\\inst\\a.md"}))])
        assert cli(limpio, "--prohibida", SECRETO, "--cwd", CWD)[2] == ""


def test_lo_que_rescatar_guarda_llega_al_informe_de_auditar():
    with Temporal() as base:
        sub = base / "subagents"
        sub.mkdir()
        lineas = [{"type": "user", "message": {"content": "p"}},
                  asistente(uso("Read", {"file_path": "C:\\inst\\a.md"}), uso("Bash", {"command": "ls"}), uso("Bash", {"command": "pwd"})),
                  asistente(uso("SubagentHandback", {"message": "r"}))]
        (sub / "agent-z.jsonl").write_bytes(("\n".join(json.dumps(l) for l in lineas) + "\n").encode("utf-8"))
        r = subprocess.run([sys.executable, "-W", "error", str(RESCATAR), "--sesion", str(sub), "--destino", str(base / "c"), "--corrida", "c1=z"],
                           capture_output=True)
        assert r.returncode == 0, r
        codigo, salida, _ = cli(base / "c" / "c1.lecturas.json", "--prohibida", SECRETO, "--cwd", CWD, "--json")
        assert codigo == 0 and json.loads(salida)["archivos"][0]["no_auditadas"] == {"Bash": 2}, (codigo, salida)


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
