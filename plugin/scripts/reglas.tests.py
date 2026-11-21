import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_RUTA = AQUI / "reglas.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []


def _cargar():
    spec = importlib.util.spec_from_file_location("reglas", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None

CAPAS_CONFIG = {"sql": {"extensions": [".sql"]}, "docs": {"extensions": [".md"]}}
MODULO_RUTA = ".claude/reglas/verificar_sql.py"
SUITE_RUTA = ".claude/reglas/verificar_sql.tests.py"
TRAZA = ".claude/reglas/traza.jsonl"

MODULO = r'''import collections
import json
from pathlib import Path

from odd_ws import tsql

Regla = collections.namedtuple("Regla", "id funcion")
TRAZA = Path(__file__).with_name("traza.jsonl")


def _anotar(evento):
    with open(TRAZA, "a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def _mal(ctx):
    limpias = tsql.depurar(ctx["texto"]).split("\n")
    return [(n, t.strip()) for n, t in ctx["agregadas"] if "MAL" in limpias[n - 1]]


def _vacio(ctx):
    return [] if ctx["texto"].strip() else [(None, None)]


REGLAS = [Regla("SQL-01", _mal), Regla("SQL-02", _vacio), Regla("SQL-03", lambda ctx: [])]


def precalcular(ctxs):
    _anotar({"evento": "precalcular", "relativas": [c["relativa"] for c in ctxs]})
    if any("PRECALC" in c["texto"] for c in ctxs):
        raise ValueError("precalcular explota")


def verificar(ctx):
    _anotar({"evento": "verificar", "ctx": {k: (v.hex() if isinstance(v, bytes) else v) for k, v in ctx.items()}})
    if "BOOM" in ctx["texto"]:
        raise ValueError("explota")
    if "BASURA" in ctx["texto"]:
        return ["no soy un hallazgo"]
    if "SINMENSAJE" in ctx["texto"]:
        return [{"id": "SQL-01", "modo": "aviso"}]
    res = []
    for regla in REGLAS:
        for linea, fragmento in regla.funcion(ctx):
            res.append({"id": regla.id, "modo": "aviso", "severidad": "", "linea": linea, "fragmento": fragmento, "mensaje": "m"})
    if "LENTO" in ctx["texto"]:
        res.append({"id": "SQL-AST", "modo": "aviso", "severidad": "", "linea": None, "fragmento": None, "mensaje": "sin tiempo"})
    return res
'''

SUITE = r'''import importlib.util
import sys
from pathlib import Path

from odd_ws import tsql

spec = importlib.util.spec_from_file_location("verificar_sql", Path(__file__).with_name("verificar_sql.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

if __name__ == "__main__":
    print("suite %s argv=%d %s %s mañana" % (__name__, len(sys.argv), tsql.depurar("a -- b").strip(), M.REGLAS[0].id))
    sys.exit(CODIGO)
'''


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    raiz = Path(tempfile.mkdtemp(prefix="reglas-test-"))
    try:
        yield raiz
    finally:
        shutil.rmtree(raiz, onexc=_quitar)
        if raiz.exists():
            SOBRANTES.append(str(raiz))


def escribir(raiz, archivos):
    for ruta, texto in archivos.items():
        p = Path(raiz) / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)


def instancia(raiz, modulo=MODULO, suite=None, capas=None):
    archivos = {"workspace.config.json": json.dumps({"schema_version": 1, "repos": {}, "layers": capas or CAPAS_CONFIG})}
    if modulo is not None:
        archivos[MODULO_RUTA] = modulo
    if suite is not None:
        archivos[SUITE_RUTA] = suite
    escribir(raiz, archivos)


def correr(argv):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = M.main(argv)
    return codigo, salida.getvalue(), error.getvalue()


def calibrar(raiz, *extra):
    return correr(["--calibrar", "sql", str(Path(raiz) / "db"), "--raiz", str(raiz), *extra])


def traza(raiz):
    ruta = Path(raiz) / TRAZA
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []


def instantanea(carpeta):
    return sorted((str(p.relative_to(carpeta)), p.read_bytes()) for p in Path(carpeta).rglob("*") if p.is_file())


def test_calibrar_una_linea_por_regla_en_el_orden_de_REGLAS_con_el_formato_del_origen():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {
            "db/a.sql": "SELECT 1\r\nSELECT MAL\r\n-- MAL en un comentario\r\n",
            "db/sub/b.SQL": "SELECT MAL\n",
            "db/notas.md": "MAL\n",
            "db/.git/c.sql": "SELECT MAL\n",
            "db/node_modules/d.sql": "SELECT MAL\n",
        })
        antes = instantanea(Path(raiz) / "db")
        codigo, out, err = calibrar(raiz)
        assert codigo == 0 and err == "", (codigo, err)
        assert out.splitlines() == ["SQL-01 archivos=2 aciertos=2", "SQL-02 archivos=0 aciertos=0",
                                    "SQL-03 archivos=0 aciertos=0"], out
        assert instantanea(Path(raiz) / "db") == antes


def test_calibrar_recorre_en_orden_aunque_el_sistema_de_archivos_no_lo_de():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/%s.sql" % n: "SELECT MAL\n" for n in ("a", "b", "c", "s1/x", "s2/y")})
        real = os.walk

        def al_reves(carpeta, *args, **kwargs):
            for actual, subcarpetas, archivos in real(carpeta, *args, **kwargs):
                subcarpetas.reverse()
                archivos.reverse()
                yield actual, subcarpetas, archivos

        M.os.walk = al_reves
        try:
            codigo, out, err = calibrar(raiz, "--detalle")
        finally:
            M.os.walk = real
        assert codigo == 0, (codigo, err)
        detalle = [l for l in out.splitlines() if l.startswith("  ")]
        assert detalle == ["  %s.sql:1 SELECT MAL" % n for n in ("a", "b", "c", "s1/x", "s2/y")], detalle


def test_calibrar_detalle_maximo_20_por_regla_justo_debajo_de_su_linea():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/f%02d.sql" % i: "SELECT 1\r\nSELECT MAL  \r\n" for i in range(25)})
        codigo, out, err = calibrar(raiz, "--detalle")
        ls = out.splitlines()
        assert codigo == 0, (codigo, err)
        i = ls.index("SQL-01 archivos=25 aciertos=25")
        assert ls[i + 1:i + 21] == ["  f%02d.sql:2 SELECT MAL" % n for n in range(20)], ls[i + 1:i + 21]
        assert ls[i + 21] == "SQL-02 archivos=0 aciertos=0", ls[i + 21]
        assert ls[-1] == "SQL-03 archivos=0 aciertos=0", ls


def test_calibrar_detalle_de_un_hallazgo_sin_linea_ni_fragmento():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/vacio.sql": b"", "db/a.sql": "SELECT 1\n"})
        codigo, out, err = calibrar(raiz, "--detalle")
        assert codigo == 0, (codigo, err)
        ls = out.splitlines()
        assert ls == ["SQL-01 archivos=0 aciertos=0", "SQL-02 archivos=1 aciertos=1", "  vacio.sql:0",
                      "SQL-03 archivos=0 aciertos=0"], ls


def test_calibrar_llama_a_precalcular_una_vez_con_todos_los_ctx_antes_de_verificar():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/b.sql": "SELECT 2\n", "db/a.sql": "SELECT 1\n", "db/sub/c.sql": "SELECT 3\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 0, (codigo, err)
        eventos = traza(raiz)
        assert [e["evento"] for e in eventos] == ["precalcular", "verificar", "verificar", "verificar"], eventos
        assert eventos[0]["relativas"] == ["a.sql", "b.sql", "sub/c.sql"], eventos[0]
        assert [e["ctx"]["relativa"] for e in eventos[1:]] == ["a.sql", "b.sql", "sub/c.sql"]


def test_calibrar_sin_precalcular_igual_verifica_cada_archivo():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO.replace("def precalcular(", "def _precalcular("))
        escribir(raiz, {"db/a.sql": "SELECT MAL\n", "db/b.sql": "SELECT 1\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 0 and err == "", (codigo, err)
        assert [e["evento"] for e in traza(raiz)] == ["verificar", "verificar"]
        assert out.splitlines()[0] == "SQL-01 archivos=1 aciertos=1", out


def test_calibrar_el_ctx_cumple_el_contrato_de_los_modulos():
    with temporal() as raiz:
        instancia(raiz)
        crudo = b"\xef\xbb\xbfSELECT 1\r\nSELECT 2\r\n"
        escribir(raiz, {"db/x/a.sql": crudo, "db/vacio.sql": b""})
        codigo, out, err = calibrar(raiz)
        assert codigo == 0, (codigo, err)
        ctxs = {e["ctx"]["relativa"]: e["ctx"] for e in traza(raiz) if e["evento"] == "verificar"}
        assert set(ctxs) == {"x/a.sql", "vacio.sql"}, set(ctxs)
        ctx = ctxs["x/a.sql"]
        claves = {"ruta", "relativa", "relativa_repo", "origen", "capa", "bytes", "texto", "es_nuevo", "agregadas", "hunks", "limite"}
        assert set(ctx) == claves, set(ctx) ^ claves
        assert os.path.isabs(ctx["ruta"]) and os.path.samefile(ctx["ruta"], Path(raiz) / "db" / "x" / "a.sql"), ctx["ruta"]
        assert ctx["relativa_repo"] == "x/a.sql" and ctx["origen"] == "repo" and ctx["capa"] == "sql"
        assert bytes.fromhex(ctx["bytes"]) == crudo
        assert ctx["texto"] == "SELECT 1\r\nSELECT 2\r\n", repr(ctx["texto"])
        assert ctx["es_nuevo"] is True and ctx["limite"] is None
        assert ctx["agregadas"] == [[1, "SELECT 1"], [2, "SELECT 2"]], ctx["agregadas"]
        assert ctx["hunks"] == [{"agregadas": [[1, "SELECT 1"], [2, "SELECT 2"]], "quitadas": []}], ctx["hunks"]
        assert ctxs["vacio.sql"]["agregadas"] == [] and ctxs["vacio.sql"]["hunks"] == []


def test_calibrar_sin_REGLAS_lista_solo_los_vistos_y_avisa_que_los_ceros_no_aparecen():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO.replace("REGLAS", "_TODAS"))
        escribir(raiz, {"db/a.sql": "SELECT MAL\n", "db/b.sql": "SELECT 1\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 0, (codigo, err)
        assert out.splitlines() == ["SQL-01 archivos=1 aciertos=1"], out
        assert "REGLAS" in err and "0 aciertos" in err, err


def test_calibrar_un_id_que_no_esta_en_REGLAS_va_despues_de_ellas():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/a.sql": "SELECT LENTO\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 0 and err == "", (codigo, err)
        assert out.splitlines() == ["SQL-01 archivos=0 aciertos=0", "SQL-02 archivos=0 aciertos=0",
                                    "SQL-03 archivos=0 aciertos=0", "SQL-AST archivos=1 aciertos=1"], out


def test_calibrar_un_modulo_que_revienta_o_devuelve_basura_sale_1_y_cuenta_el_resto():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/a.sql": "SELECT MAL\n", "db/b.sql": "BOOM\n", "db/c.sql": "BASURA\n", "db/d.sql": "SINMENSAJE\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 1, (codigo, err)
        assert out.splitlines()[0] == "SQL-01 archivos=1 aciertos=1", out
        errores = err.splitlines()
        for nombre, motivo in (("b.sql", "explota"), ("c.sql", "no soy un hallazgo"), ("d.sql", "SQL-01")):
            assert any(nombre in l and motivo in l for l in errores), (nombre, errores)


def test_calibrar_un_precalcular_que_revienta_se_reporta_y_igual_verifica():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/a.sql": "SELECT MAL PRECALC\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 1, (codigo, err)
        assert "precalcular" in err and "precalcular explota" in err, err
        assert out.splitlines()[0] == "SQL-01 archivos=1 aciertos=1", out


def test_calibrar_un_modulo_que_no_carga_o_con_REGLAS_mal_formadas_sale_1():
    with temporal() as raiz:
        instancia(raiz, modulo="def roto(:\n")
        escribir(raiz, {"db/a.sql": "SELECT 1\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 1 and out == "" and "verificar_sql.py" in err, (codigo, out, err)
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO.replace("REGLAS", "_TODAS") + "\nREGLAS = ['x']\n")
        escribir(raiz, {"db/a.sql": "SELECT MAL\n"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 1 and "REGLAS" in err, (codigo, err)
        assert out.splitlines() == ["SQL-01 archivos=1 aciertos=1"], out


def test_errores_de_uso_dan_exit_2_sin_nada_en_stdout():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
        carpeta = Path(raiz) / "db"
        carpeta.mkdir()
        r = str(raiz)
        casos = [
            ([], "sin argumentos"),
            (["--calibrar", "sql"], "--calibrar sin carpeta"),
            (["--calibrar", "sql", str(Path(raiz) / "no-existe"), "--raiz", r], "carpeta inexistente"),
            (["--detalle"], "--detalle solo"),
            (["--test", "sql", "--detalle", "--raiz", r], "--detalle con --test"),
            (["--test", "sql", "--calibrar", "sql", str(carpeta)], "los dos modos"),
            (["--otra"], "opcion desconocida"),
            (["--test", "nada", "--raiz", r], "capa no declarada"),
            (["--calibrar", "docs", str(carpeta), "--raiz", r], "capa sin modulo"),
            (["--test", "docs", "--raiz", r], "capa sin suite"),
        ]
        for argv, que in casos:
            codigo, out, err = correr(argv)
            assert codigo == 2 and out == "" and err, (que, codigo, out, err)
    with temporal() as raiz:
        codigo, out, err = correr(["--test", "sql", "--raiz", str(raiz)])
        assert codigo == 2 and out == "" and "workspace.config.json" in err, ("sin instancia", codigo, err)
        escribir(raiz, {"workspace.config.json": "{no es json"})
        codigo, out, err = correr(["--test", "sql", "--raiz", str(raiz)])
        assert codigo == 2 and out == "" and "workspace.config.json" in err, ("config rota", codigo, err)


def test_test_corre_la_suite_de_la_instancia_como_main_y_devuelve_su_codigo():
    for esperado in (0, 3):
        with temporal() as raiz:
            instancia(raiz, suite=SUITE.replace("CODIGO", str(esperado)))
            previo = list(sys.argv)
            codigo, out, err = correr(["--test", "sql", "--raiz", str(raiz)])
            assert codigo == esperado, (esperado, codigo, err)
            assert "suite __main__ argv=1 a SQL-01 mañana" in out, out
            assert sys.argv == previo, sys.argv


def test_test_sin_capa_corre_la_suite_de_cada_capa_que_tiene_una():
    capas = {"sql": {"extensions": [".sql"]}, "docs": {"extensions": [".md"]}, "web": {"extensions": [".cs"]}}
    for codigo_web, esperado in ((0, 0), (3, 1)):
        with temporal() as raiz:
            instancia(raiz, suite=SUITE.replace("CODIGO", "0"), capas=capas)
            escribir(raiz, {".claude/reglas/verificar_web.tests.py": "import sys\nprint('suite web')\nsys.exit(%d)\n" % codigo_web})
            codigo, out, err = correr(["--test", "--raiz", str(raiz)])
            assert codigo == esperado, (codigo_web, codigo, out, err)
            ls = out.splitlines()
            assert ls.index("== sql: .claude/reglas/verificar_sql.tests.py") < ls.index("== web: .claude/reglas/verificar_web.tests.py"), ls
            assert ls.index("suite web") > ls.index("== web: .claude/reglas/verificar_web.tests.py"), ls
            assert "sin suite: docs" in ls, ls
            assert ls[-1] == ("suites en rojo: web" if codigo_web else "suites: 2, todas en verde"), ls[-1]


def test_test_sin_capa_y_sin_ninguna_suite_sale_0_y_lo_dice():
    with temporal() as raiz:
        instancia(raiz)
        codigo, out, err = correr(["--test", "--raiz", str(raiz)])
        assert codigo == 0 and out.splitlines() == ["sin suite: sql, docs", "ninguna capa tiene suite"], (codigo, out, err)


def test_test_una_suite_que_revienta_o_sale_con_un_mensaje_sale_1():
    for suite, rastro in (("raise RuntimeError('suite rota')\n", "suite rota"),
                          ("import sys\nsys.exit('mensaje de falla')\n", "mensaje de falla")):
        with temporal() as raiz:
            instancia(raiz, suite=suite)
            codigo, out, err = correr(["--test", "sql", "--raiz", str(raiz)])
            assert codigo == 1 and rastro in err, (suite, codigo, err)


def test_la_raiz_por_defecto_es_la_de_la_sesion():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
        ticket = Path(raiz) / "tickets" / "T-1"
        ticket.mkdir(parents=True)
        previo = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(ticket)
        try:
            codigo, out, err = correr(["--test", "sql"])
        finally:
            if previo is None:
                del os.environ["CLAUDE_PROJECT_DIR"]
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = previo
        assert codigo == 0 and "suite __main__" in out, (codigo, out, err)


def test_como_proceso_la_instancia_importa_odd_ws_sin_pythonpath_y_sale_en_utf8_con_consola_cp1252():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
        escribir(raiz, {"db/a.sql": "SELECT MAL ñ\r\n"})
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONPATH")}
        env["PYTHONIOENCODING"] = "cp1252"
        prueba = subprocess.run([sys.executable, str(_RUTA), "--test", "sql", "--raiz", str(raiz)],
                                capture_output=True, env=env, cwd=str(raiz))
        assert prueba.returncode == 0 and b"Traceback" not in prueba.stderr, prueba.stderr
        assert "suite __main__ argv=1 a SQL-01 mañana" in prueba.stdout.decode("utf-8"), prueba.stdout
        cal = subprocess.run([sys.executable, str(_RUTA), "--calibrar", "sql", str(Path(raiz) / "db"), "--detalle",
                              "--raiz", str(raiz)], capture_output=True, env=env, cwd=str(raiz))
        assert cal.returncode == 0 and b"Traceback" not in cal.stderr, cal.stderr
        assert "  a.sql:1 SELECT MAL ñ" in cal.stdout.decode("utf-8").splitlines(), cal.stdout


def test_la_ayuda_documenta_los_dos_modos():
    codigo, out, err = correr(["--help"])
    assert codigo == 0, (codigo, err)
    for opcion in ("--test", "--calibrar", "--detalle", "--raiz"):
        assert opcion in out, opcion


SUITE_DE_PAQUETE = r'''import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("verificar_del_paquete", Path(__file__).with_name("verificar.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

if __name__ == "__main__":
    print("suite del paquete %s argv=%d" % (M.NOMBRE, len(sys.argv)))
    sys.exit(CODIGO)
'''


def paquete(raiz, nombre, capa, prefijo, codigo=0, con_suite=True):
    carpeta = ".claude/reglas/paquetes/%s/" % nombre
    archivos = {carpeta + "verificar.py": "NOMBRE = %r\ndef verificar(ctx):\n    return []\n" % nombre}
    if con_suite:
        archivos[carpeta + "verificar.tests.py"] = SUITE_DE_PAQUETE.replace("CODIGO", str(codigo))
    escribir(raiz, archivos)
    lock = Path(raiz) / ".claude" / "reglas" / "paquetes.json"
    datos = json.loads(lock.read_text(encoding="utf-8")) if lock.is_file() else {"version": 1, "paquetes": {}}
    datos["paquetes"][nombre] = {"capa": capa, "prefijo": prefijo, "fuente": "https://example.com/%s.git" % nombre,
                                 "etiqueta": "v1.0.0", "commit": "b" * 40, "huella": "sha256:" + "0" * 64}
    escribir(raiz, {".claude/reglas/paquetes.json": json.dumps(datos)})


def test_test_sin_capa_corre_tambien_la_suite_de_cada_paquete_tras_la_de_su_capa():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
        paquete(raiz, "zeta", "sql", "ZET")
        paquete(raiz, "alfa", "sql", "ALF", codigo=3)
        paquete(raiz, "de-docs", "docs", "DOC")
        paquete(raiz, "sin-suite", "sql", "SIN", con_suite=False)
        paquete(raiz, "de-otra-capa", "rust", "RUS")
        codigo, out, err = correr(["--test", "--raiz", str(raiz)])
        ls = out.splitlines()
        assert codigo == 1, (codigo, out, err)
        assert ls[0] == "sin suite: sql/sin-suite, docs", ls
        cabeceras = [l for l in ls if l.startswith("== ")]
        assert cabeceras == ["== sql: .claude/reglas/verificar_sql.tests.py",
                             "== sql/alfa: .claude/reglas/paquetes/alfa/verificar.tests.py",
                             "== sql/zeta: .claude/reglas/paquetes/zeta/verificar.tests.py",
                             "== docs/de-docs: .claude/reglas/paquetes/de-docs/verificar.tests.py"], cabeceras
        assert ls.index("suite del paquete alfa argv=1") == ls.index(cabeceras[1]) + 1, ls
        assert "suite del paquete zeta argv=1" in ls and "suite del paquete de-docs argv=1" in ls, ls
        assert not any("de-otra-capa" in l for l in ls), "un paquete de una capa no declarada no corre"
        assert ls[-1] == "suites en rojo: sql/alfa", ls[-1]


def test_test_sin_capa_con_los_paquetes_en_verde_los_cuenta():
    with temporal() as raiz:
        instancia(raiz)
        paquete(raiz, "alfa", "sql", "ALF")
        codigo, out, err = correr(["--test", "--raiz", str(raiz)])
        ls = out.splitlines()
        assert codigo == 0 and ls[0] == "sin suite: sql, docs" and ls[-1] == "suites: 1, todas en verde", (codigo, ls, err)


def test_test_de_una_capa_con_paquetes_corre_la_suya_y_las_de_sus_paquetes():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
        paquete(raiz, "alfa", "sql", "ALF")
        paquete(raiz, "de-docs", "docs", "DOC", codigo=3)
        codigo, out, err = correr(["--test", "sql", "--raiz", str(raiz)])
        ls = out.splitlines()
        assert codigo == 0, (codigo, out, err)
        assert [l for l in ls if l.startswith("== ")] == ["== sql: .claude/reglas/verificar_sql.tests.py",
                                                         "== sql/alfa: .claude/reglas/paquetes/alfa/verificar.tests.py"], ls
        assert ls[-1] == "suites: 2, todas en verde", ls
        paquete(raiz, "alfa", "sql", "ALF", codigo=5)
        codigo, out, _ = correr(["--test", "sql", "--raiz", str(raiz)])
        assert codigo == 1 and out.splitlines()[-1] == "suites en rojo: sql/alfa", (codigo, out)
    with temporal() as raiz:
        instancia(raiz)
        paquete(raiz, "alfa", "sql", "ALF")
        codigo, out, err = correr(["--test", "sql", "--raiz", str(raiz)])
        ls = out.splitlines()
        assert codigo == 0 and ls[0] == "sin suite: sql" and ls[-1] == "suites: 1, todas en verde", (codigo, ls, err)


def test_test_con_el_lock_roto_es_error_de_entorno():
    for lock in ("{roto", json.dumps({"version": 9, "paquetes": {}})):
        with temporal() as raiz:
            instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
            escribir(raiz, {".claude/reglas/paquetes.json": lock})
            for argv in (["--test", "--raiz", str(raiz)], ["--test", "sql", "--raiz", str(raiz)]):
                codigo, out, err = correr(argv)
                assert codigo == 2 and out == "" and err.startswith("reglas: .claude/reglas/paquetes.json roto: "), (argv, codigo, out, err)


def test_test_sin_paquetes_de_la_capa_sale_con_el_codigo_de_su_suite_como_siempre():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "3"))
        paquete(raiz, "de-docs", "docs", "DOC")
        codigo, out, err = correr(["--test", "sql", "--raiz", str(raiz)])
        assert codigo == 3 and out.splitlines() == ["suite __main__ argv=1 a SQL-01 mañana"], (codigo, out, err)
        codigo, out, err = correr(["--test", "docs", "--raiz", str(raiz)])
        assert codigo == 0 and out.splitlines()[-1] == "suites: 1, todas en verde", (codigo, out, err)


def test_test_con_un_paquete_que_usa_el_prefijo_de_una_capa_es_error_de_entorno():
    capas = {"sql": {"extensions": [".sql"], "rule_prefix": "SQL"}, "docs": {"extensions": [".md"]}}
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"), capas=capas)
        paquete(raiz, "alfa", "docs", "SQL")
        for argv in (["--test"], ["--test", "sql"], ["--test", "docs"]):
            codigo, out, err = correr(argv + ["--raiz", str(raiz)])
            assert (codigo, out, err) == (2, "", "reglas: .claude/reglas/paquetes.json roto: alfa: el prefijo SQL ya lo usa "
                                                 "layers.sql.rule_prefix\n"), (argv, codigo, out, err)


def test_test_cada_suite_de_paquete_corre_aparte_y_un_os_exit_no_corta_las_demas():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
        paquete(raiz, "a-sale", "sql", "ASA")
        escribir(raiz, {".claude/reglas/paquetes/a-sale/verificar.tests.py": "import os\nprint('se va', flush=True)\nos._exit(0)\n"})
        paquete(raiz, "b-roja", "sql", "BRO", codigo=3)
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONUTF8")}
        r = subprocess.run([sys.executable, str(_RUTA), "--test", "--raiz", str(raiz)], capture_output=True, env=env, cwd=str(raiz),
                           timeout=120)
        ls = r.stdout.decode("utf-8").splitlines()
        assert r.returncode == 1, (r.returncode, ls, r.stderr)
        assert ls.index("se va") == ls.index("== sql/a-sale: .claude/reglas/paquetes/a-sale/verificar.tests.py") + 1, ls
        assert ls.index("suite del paquete b-roja argv=1") == ls.index("== sql/b-roja: .claude/reglas/paquetes/b-roja/verificar.tests.py") + 1, ls
        assert ls[-1] == "suites en rojo: sql/b-roja", ls


def test_test_una_suite_de_paquete_que_se_cuelga_o_revienta_queda_en_rojo_y_las_otras_corren():
    with temporal() as raiz:
        instancia(raiz)
        paquete(raiz, "colgada", "sql", "COL")
        paquete(raiz, "rota", "sql", "ROT")
        paquete(raiz, "verde", "sql", "VER")
        escribir(raiz, {".claude/reglas/paquetes/colgada/verificar.tests.py": "import time\ntime.sleep(10)\n",
                        ".claude/reglas/paquetes/rota/verificar.tests.py": "raise RuntimeError('suite rota')\n"})
        previo = getattr(M, "TOPE_DE_UNA_SUITE_DE_PAQUETE", None)
        M.TOPE_DE_UNA_SUITE_DE_PAQUETE = 2
        try:
            codigo, out, err = correr(["--test", "--raiz", str(raiz)])
        finally:
            M.TOPE_DE_UNA_SUITE_DE_PAQUETE = previo
        ls = out.splitlines()
        assert codigo == 1 and ls[-1] == "suites en rojo: sql/colgada, sql/rota", (codigo, out, err)
        assert "suite del paquete verde argv=1" in ls, ls
        assert "RuntimeError: suite rota" in err, err
        assert "reglas: la suite .claude/reglas/paquetes/colgada/verificar.tests.py no termino en 2 s" in err.splitlines(), err


def test_test_no_corre_la_suite_de_un_paquete_enlazado_fuera_de_su_carpeta():
    with temporal() as raiz:
        instancia(raiz)
        paquete(raiz, "alfa", "sql", "ALF")
        carpeta = Path(raiz) / ".claude" / "reglas" / "paquetes" / "alfa"
        real = Path(raiz) / "alfa-real"
        shutil.move(str(carpeta), str(real))
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(real), str(carpeta))
        else:
            os.symlink(str(real), str(carpeta), target_is_directory=True)
        codigo, out, err = correr(["--test", "--raiz", str(raiz)])
        assert codigo == 1 and out.splitlines()[-1] == "suites en rojo: sql/alfa", (codigo, out, err)
        assert "suite del paquete alfa argv=1" not in out, out
        assert "reglas: .claude/reglas/paquetes/alfa: enlace o fuera de su carpeta, no se corre" in err.splitlines(), err


def test_calibrar_no_mira_el_lock():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {"db/a.sql": "SELECT 1\n", ".claude/reglas/paquetes.json": "{roto"})
        codigo, out, err = calibrar(raiz)
        assert codigo == 0 and "SQL-01 archivos=0 aciertos=0" in out.splitlines(), (codigo, out, err)


REGISTRO = ".claude/registro/calibracion.json"
MODULO_CON_SEMBRADO = ('import collections\r\n'
                       '\r\n'
                       'Regla = collections.namedtuple("Regla", "id sembrado")\r\n'
                       'REGLAS = [Regla("SQL-01", "SELECT MAL;"), Regla("SQL-02", "SELECT NADIE_LO_VE;"), Regla("SQL-03", None)]\r\n'
                       '\r\n'
                       '\r\n'
                       'def verificar(ctx):\r\n'
                       '    if "BOOM" in ctx["texto"]:\r\n'
                       '        raise ValueError("explota")\r\n'
                       '    res = []\r\n'
                       '    for n, t in ctx["agregadas"]:\r\n'
                       '        if "MAL" in t:\r\n'
                       '            res.append({"id": "SQL-01", "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": "MAL", "mensaje": "m"})\r\n'
                       '        if "OJO" in t:\r\n'
                       '            res.append({"id": "SQL-03", "modo": "aviso", "severidad": "", "linea": n, "fragmento": None, "mensaje": "m"})\r\n'
                       '    return res\r\n')


def huella_de(texto):
    import hashlib
    return "sha256:" + hashlib.sha256(texto.encode("utf-8").replace(b"\r\n", b"\n")).hexdigest()


def registro(raiz):
    return json.loads((Path(raiz) / REGISTRO).read_text(encoding="utf-8"))


@contextlib.contextmanager
def git_aislado(base):
    vacio = Path(base) / "gitconfig-vacio"
    vacio.write_text("", encoding="utf-8")
    aislado = {"GIT_CONFIG_GLOBAL": str(vacio), "GIT_CONFIG_SYSTEM": str(vacio), "GIT_CONFIG_NOSYSTEM": "1"}
    previo = {clave: os.environ.get(clave) for clave in aislado}
    os.environ.update(aislado)
    try:
        yield
    finally:
        for clave, valor in previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor


def git_de_prueba(repo, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args], cwd=str(repo),
                       capture_output=True, text=True, encoding="utf-8", env=M.entorno_git())
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def test_git_de_prueba_no_escribe_en_el_repo_del_hook_que_corre_la_suite():
    with temporal() as raiz, git_aislado(raiz):
        afuera, prueba = raiz / "afuera", raiz / "prueba"
        for repo in (afuera, prueba):
            repo.mkdir()
        git_de_prueba(afuera, "init", "-q")
        escribir(afuera, {"x.txt": "x\n"})
        git_de_prueba(afuera, "add", "-A")
        git_de_prueba(afuera, "commit", "-q", "-m", "afuera")
        del_hook = {"GIT_DIR": str(afuera / ".git"), "GIT_INDEX_FILE": str(afuera / ".git" / "index"), "GIT_WORK_TREE": str(afuera)}
        previo = {clave: os.environ.get(clave) for clave in del_hook}
        os.environ.update(del_hook)
        try:
            git_de_prueba(prueba, "init", "-q")
            escribir(prueba, {"y.txt": "y\n"})
            git_de_prueba(prueba, "add", "-A")
            git_de_prueba(prueba, "commit", "-q", "-m", "base")
        finally:
            for clave, valor in previo.items():
                if valor is None:
                    os.environ.pop(clave, None)
                else:
                    os.environ[clave] = valor
        assert git_de_prueba(afuera, "log", "--format=%s") == "afuera", "un commit de fixture cayó en el repo del hook"
        assert git_de_prueba(prueba, "log", "--format=%s") == "base"


def test_guardar_escribe_la_calibracion_de_cada_regla_con_su_forma():
    import datetime
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        escribir(raiz, {"db/a.sql": "SELECT 1\n", "db/sub/b.sql": "SELECT MAL\nSELECT MAL\n", "db/c.sql": "-- OJO\n"})
        antes = datetime.date.today().isoformat()
        codigo, out, err = calibrar(raiz, "--guardar")
        despues = datetime.date.today().isoformat()
        assert codigo == 0, (codigo, out, err)
        assert out.splitlines() == ["SQL-01 archivos=1 aciertos=2", "SQL-02 archivos=0 aciertos=0", "SQL-03 archivos=1 aciertos=1",
                                    "calibracion guardada en %s" % REGISTRO,
                                    "SQL-01 solo avisa: 2 aciertos en bloqueo en el corpus",
                                    "SQL-02 solo avisa: no atrapa su sembrado",
                                    "SQL-03 solo avisa: sin sembrado"], out
        assert err.splitlines() == ["reglas: aviso, %s no esta en ningun repo declarado: el corpus queda registrado solo por "
                                    "su nombre (db)" % (Path(raiz) / "db")], err
        datos = registro(raiz)
        assert datos["version"] == 1 and list(datos["capas"]) == ["sql"], datos
        reglas = datos["capas"]["sql"]
        assert list(reglas) == ["SQL-01", "SQL-02", "SQL-03"], reglas
        comun = {"huella": huella_de(MODULO_CON_SEMBRADO), "archivos_del_corpus": 3, "corpus": {"repo": None, "commit": None, "ruta": "db"}}
        esperado = {"SQL-01": dict(comun, atrapa_su_sembrado=True, aciertos=2, aciertos_en_bloqueo=2),
                    "SQL-02": dict(comun, atrapa_su_sembrado=False, aciertos=0, aciertos_en_bloqueo=0),
                    "SQL-03": dict(comun, atrapa_su_sembrado=False, aciertos=1, aciertos_en_bloqueo=0)}
        for id_, datos_de_la_regla in esperado.items():
            assert {k: v for k, v in reglas[id_].items() if k != "fecha"} == datos_de_la_regla, (id_, reglas[id_])
            assert reglas[id_]["fecha"] in (antes, despues), reglas[id_]
        assert str(raiz) not in (Path(raiz) / REGISTRO).read_text(encoding="utf-8"), "nunca una ruta absoluta"


def test_guardar_con_corpus_limpio_o_vacio_deja_bloquear_a_la_regla_que_atrapa_su_sembrado():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        (Path(raiz) / "db").mkdir()
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0, (codigo, out, err)
        assert "SQL-01 puede bloquear" in out.splitlines(), out
        regla = registro(raiz)["capas"]["sql"]["SQL-01"]
        assert regla["archivos_del_corpus"] == 0 and regla["atrapa_su_sembrado"] is True and regla["aciertos_en_bloqueo"] == 0, regla


def test_guardar_con_un_repo_declarado_guarda_repo_commit_y_ruta_relativa():
    with temporal() as raiz, git_aislado(raiz):
        repo = Path(raiz) / "equipo" / "db"
        escribir(repo, {"src/sp/a.sql": "SELECT 1\n", "README.md": "x\n"})
        git_de_prueba(repo, "init", "-q")
        git_de_prueba(repo, "add", "-A")
        git_de_prueba(repo, "commit", "-q", "-m", "base")
        cabeza = git_de_prueba(repo, "rev-parse", "HEAD")
        escribir(raiz, {"workspace.config.json": json.dumps({"schema_version": 1, "repos": {"db": {}},
                                                             "layers": {"sql": {"extensions": [".sql"], "repos": ["db"]}}}),
                        "workspace.local.json": json.dumps({"repos": {"db": {"path": str(repo)}}}), MODULO_RUTA: MODULO_CON_SEMBRADO})
        for carpeta, ruta in ((repo / "src" / "sp", "src/sp"), (repo, ".")):
            codigo, out, err = correr(["--calibrar", "sql", str(carpeta), "--raiz", str(raiz), "--guardar"])
            assert codigo == 0 and err == "", (carpeta, codigo, out, err)
            assert registro(raiz)["capas"]["sql"]["SQL-01"]["corpus"] == {"repo": "db", "commit": cabeza, "ruta": ruta}, registro(raiz)


def test_guardar_no_escribe_si_hubo_errores_y_sale_1():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        escribir(raiz, {"db/a.sql": "SELECT 1\n", "db/b.sql": "BOOM\n"})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 1 and not (Path(raiz) / ".claude" / "registro").exists(), (codigo, out, err)
        assert "explota" in err and "no se guarda la calibracion" in err, err
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO.replace('"SELECT MAL;"', '"BOOM"'))
        escribir(raiz, {"db/a.sql": "SELECT 1\n"})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 1 and not (Path(raiz) / ".claude" / "registro").exists(), (codigo, out, err)
        assert "sembrado de SQL-01" in err and "explota" in err, err


def test_guardar_no_escribe_sin_REGLAS_y_sale_2():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO.replace("REGLAS = ", "_TODAS = "))
        escribir(raiz, {"db/a.sql": "SELECT MAL\n"})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 2 and not (Path(raiz) / ".claude" / "registro").exists(), (codigo, out, err)
        assert out.splitlines() == ["SQL-01 archivos=1 aciertos=1"], out
        assert "no declara REGLAS: no se guarda la calibracion" in err, err


def test_guardar_conserva_las_otras_capas_y_reemplaza_entera_la_suya():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        (Path(raiz) / "db").mkdir()
        vieja = {"huella": "sha256:" + "c" * 64, "atrapa_su_sembrado": True, "aciertos": 0, "aciertos_en_bloqueo": 0,
                 "archivos_del_corpus": 9, "corpus": {"repo": None, "commit": None, "ruta": "docs"}, "fecha": "2026-01-02"}
        escribir(raiz, {REGISTRO: json.dumps({"version": 1, "capas": {"docs": {"DOC-01": vieja}, "sql": {"SQL-99": vieja}}})})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0, (codigo, out, err)
        capas = registro(raiz)["capas"]
        assert capas["docs"] == {"DOC-01": vieja} and sorted(capas["sql"]) == ["SQL-01", "SQL-02", "SQL-03"], capas


def test_guardar_con_el_registro_roto_no_escribe_y_sale_2():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        (Path(raiz) / "db").mkdir()
        escribir(raiz, {REGISTRO: "{roto"})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 2 and out == "" and REGISTRO in err, (codigo, out, err)
        assert (Path(raiz) / REGISTRO).read_text(encoding="utf-8") == "{roto"


def test_guardar_sin_calibrar_es_un_error_de_uso():
    with temporal() as raiz:
        instancia(raiz, suite=SUITE.replace("CODIGO", "0"))
        for argv in (["--guardar"], ["--test", "sql", "--guardar", "--raiz", str(raiz)]):
            codigo, out, err = correr(argv)
            assert codigo == 2 and out == "" and "--guardar" in err, (argv, codigo, out, err)


def test_sin_guardar_la_calibracion_no_cambia_ni_escribe_nada():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        escribir(raiz, {"db/a.sql": "SELECT MAL\n", "db/b.sql": "-- OJO\n"})
        codigo, out, err = calibrar(raiz, "--detalle")
        assert (codigo, out, err) == (0, "SQL-01 archivos=1 aciertos=1\n  a.sql:1 MAL\nSQL-02 archivos=0 aciertos=0\n"
                                         "SQL-03 archivos=1 aciertos=1\n  b.sql:1\n", ""), (codigo, out, err)
        assert not (Path(raiz) / ".claude" / "registro").exists()


def test_la_ayuda_documenta_guardar():
    codigo, out, err = correr(["--help"])
    assert codigo == 0 and "--guardar" in out and "calibracion.json" in out, (codigo, out)


MODULO_DE_PAQUETE = ('import types\n'
                     '\n'
                     'REGLA = types.SimpleNamespace(id="%(id)s", sembrado=%(sembrado)r)\n'
                     'REGLAS = (REGLA,)\n'
                     '\n'
                     '\n'
                     'def verificar(ctx):\n'
                     '    return [{"id": REGLA.id, "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": "MALO", "mensaje": "m"}\n'
                     '            for n, t in ctx["agregadas"] if "MALO" in t]\n')


def paquete_con_reglas(raiz, nombre, capa, prefijo, modulo=None, sembrado="SELECT MALO;"):
    carpeta = ".claude/reglas/paquetes/%s/" % nombre
    escribir(raiz, {carpeta + "verificar.py": modulo or MODULO_DE_PAQUETE % {"id": prefijo + "-01", "sembrado": sembrado},
                    carpeta + "odd-ws-paquete.json": json.dumps({"formato": 1, "nombre": nombre, "prefijo": prefijo, "odd_ws_api": 1,
                                                                 "descripcion": ""})})
    lock = Path(raiz) / ".claude" / "reglas" / "paquetes.json"
    datos = json.loads(lock.read_text(encoding="utf-8")) if lock.is_file() else {"version": 1, "paquetes": {}}
    huella = M.paquetes.huella(str(Path(raiz) / carpeta))
    datos["paquetes"][nombre] = {"capa": capa, "prefijo": prefijo, "fuente": "https://example.com/%s.git" % nombre,
                                 "etiqueta": "v1.0.0", "commit": "b" * 40, "huella": huella}
    escribir(raiz, {".claude/reglas/paquetes.json": json.dumps(datos)})
    return huella


def test_guardar_calibra_tambien_los_paquetes_de_la_capa_aparte_de_la_capa():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        escribir(raiz, {"db/a.sql": "SELECT 1\n", "db/b.sql": "SELECT MAL\nSELECT MALO\n"})
        huella = paquete_con_reglas(raiz, "zeta", "sql", "ZET", sembrado="SELECT NADA;")
        paquete_con_reglas(raiz, "alfa", "sql", "ALF")
        paquete_con_reglas(raiz, "de-docs", "docs", "DOC")
        codigo, out, err = calibrar(raiz, "--guardar", "--detalle")
        assert codigo == 0, (codigo, out, err)
        assert out.splitlines() == ["SQL-01 archivos=1 aciertos=2", "  b.sql:1 MAL", "  b.sql:2 MAL", "SQL-02 archivos=0 aciertos=0",
                                    "SQL-03 archivos=0 aciertos=0",
                                    "== sql/alfa: .claude/reglas/paquetes/alfa/verificar.py", "ALF-01 archivos=1 aciertos=1", "  b.sql:2 MALO",
                                    "== sql/zeta: .claude/reglas/paquetes/zeta/verificar.py", "ZET-01 archivos=1 aciertos=1", "  b.sql:2 MALO",
                                    "calibracion guardada en %s" % REGISTRO,
                                    "SQL-01 solo avisa: 2 aciertos en bloqueo en el corpus",
                                    "SQL-02 solo avisa: no atrapa su sembrado",
                                    "SQL-03 solo avisa: sin sembrado",
                                    "ALF-01 solo avisa: 1 aciertos en bloqueo en el corpus",
                                    "ZET-01 solo avisa: no atrapa su sembrado"], out
        datos = registro(raiz)
        assert list(datos) == ["version", "capas", "paquetes"] and list(datos["capas"]) == ["sql"], datos
        assert list(datos["paquetes"]) == ["sql"] and list(datos["paquetes"]["sql"]) == ["alfa", "zeta"], "solo los de la capa"
        zeta = datos["paquetes"]["sql"]["zeta"]["ZET-01"]
        capa = datos["capas"]["sql"]["SQL-01"]
        assert zeta["huella"] == huella != capa["huella"], "la huella de un paquete es la de su lock"
        assert (zeta["corpus"], zeta["archivos_del_corpus"], zeta["fecha"]) == (capa["corpus"], 2, capa["fecha"]), zeta
        assert (zeta["atrapa_su_sembrado"], zeta["aciertos"], zeta["aciertos_en_bloqueo"]) == (False, 1, 1), zeta
        assert datos["paquetes"]["sql"]["alfa"]["ALF-01"]["atrapa_su_sembrado"] is True


def test_guardar_con_un_corpus_limpio_deja_bloquear_al_paquete_que_atrapa_su_sembrado():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        (Path(raiz) / "db").mkdir()
        paquete_con_reglas(raiz, "alfa", "sql", "ALF")
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0 and out.splitlines()[-1] == "ALF-01 puede bloquear", (codigo, out, err)


def test_guardar_de_una_capa_sin_modulo_propio_calibra_solo_sus_paquetes():
    with temporal() as raiz:
        instancia(raiz, modulo=None)
        (Path(raiz) / "db").mkdir()
        vieja = {"huella": "sha256:" + "c" * 64, "atrapa_su_sembrado": True, "aciertos": 0, "aciertos_en_bloqueo": 0,
                 "archivos_del_corpus": 9, "corpus": {"repo": None, "commit": None, "ruta": "db"}, "fecha": "2026-01-02"}
        escribir(raiz, {REGISTRO: json.dumps({"version": 1, "capas": {"sql": {"SQL-01": vieja}, "docs": {"DOC-01": vieja}}})})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert (codigo, out) == (2, ""), "sin módulo ni paquetes sigue siendo un error de entorno: %r" % ((codigo, out, err),)
        assert err == "reglas: la capa sql no tiene modulo: no existe .claude/reglas/verificar_sql.py\n", err
        paquete_con_reglas(raiz, "alfa", "sql", "ALF")
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0, (codigo, out, err)
        assert out.splitlines() == ["== sql/alfa: .claude/reglas/paquetes/alfa/verificar.py", "ALF-01 archivos=0 aciertos=0",
                                    "calibracion guardada en %s" % REGISTRO, "ALF-01 puede bloquear"], out
        datos = registro(raiz)
        assert datos["capas"] == {"docs": {"DOC-01": vieja}}, "la capa sin módulo no deja reglas propias calibradas"
        assert list(datos["paquetes"]["sql"]) == ["alfa"], datos
        codigo, out, err = calibrar(raiz)
        assert (codigo, out) == (2, "") and "no tiene modulo" in err, "sin --guardar, --calibrar no cambia"


def test_guardar_no_escribe_si_un_paquete_no_coincide_con_su_lock_o_revienta():
    rotos = {
        "editado": None,
        "revienta": "REGLAS = ()\ndef verificar(ctx):\n    raise ValueError('explota el paquete')\n",
        "sale": "import sys\nREGLAS = ()\ndef verificar(ctx):\n    sys.exit(3)\n",
        "no-carga": "def verificar(ctx) roto\n",
        "ajeno": "REGLAS = ()\ndef verificar(ctx):\n    return [{'id': 'SQL-01', 'modo': 'bloqueo', 'mensaje': 'm'}]\n",
    }
    for nombre, modulo in rotos.items():
        with temporal() as raiz:
            instancia(raiz, modulo=MODULO_CON_SEMBRADO)
            escribir(raiz, {"db/a.sql": "SELECT 1\n"})
            paquete_con_reglas(raiz, nombre, "sql", "ROT", modulo=modulo)
            if modulo is None:
                escribir(raiz, {".claude/reglas/paquetes/editado/verificar.py": MODULO_DE_PAQUETE % {"id": "ROT-01", "sembrado": "x"}})
            codigo, out, err = calibrar(raiz, "--guardar")
            assert codigo == 1 and not (Path(raiz) / ".claude" / "registro").exists(), (nombre, codigo, out, err)
            assert "paquete %s" % nombre in err and "no se guarda la calibracion" in err, (nombre, err)
            assert modulo is not None or "reglas: paquete editado: no coincide con la huella de su lock" in err, err


def test_guardar_con_el_lock_roto_es_error_de_entorno_y_sin_guardar_lo_ignora():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        (Path(raiz) / "db").mkdir()
        escribir(raiz, {".claude/reglas/paquetes.json": "{roto"})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 2 and out == "" and err.startswith("reglas: .claude/reglas/paquetes.json roto: "), (codigo, out, err)
        assert not (Path(raiz) / ".claude" / "registro").exists()
        assert calibrar(raiz)[0] == 0


def test_calibrar_sin_guardar_no_corre_los_paquetes():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        escribir(raiz, {"db/a.sql": "SELECT MALO\n"})
        sin_paquetes = calibrar(raiz, "--detalle")
        paquete_con_reglas(raiz, "alfa", "sql", "ALF", modulo="raise SystemExit(9)\n")
        assert calibrar(raiz, "--detalle") == sin_paquetes == (0, "SQL-01 archivos=1 aciertos=1\n  a.sql:1 MAL\nSQL-02 archivos=0 aciertos=0\n"
                                                               "SQL-03 archivos=0 aciertos=0\n", ""), sin_paquetes
        assert not (Path(raiz) / ".claude" / "registro").exists()


def test_guardar_un_paquete_sin_REGLAS_no_se_calibra_y_lo_dice():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        escribir(raiz, {"db/a.sql": "SELECT MALO\n"})
        paquete_con_reglas(raiz, "alfa", "sql", "ALF", modulo=(MODULO_DE_PAQUETE % {"id": "ALF-01", "sembrado": "x"}).replace("REGLAS = (REGLA,)", "_TODAS = (REGLA,)"))
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0, (codigo, out, err)
        assert "ALF-01 archivos=1 aciertos=1" in out.splitlines() and not any(l.startswith("ALF-01 ") and "avisa" in l for l in out.splitlines()), out
        assert "reglas: el paquete alfa no declara REGLAS: no se calibra, y sus reglas solo avisan" in err.splitlines(), err
        assert "paquetes" not in registro(raiz), registro(raiz)


def test_guardar_dice_que_una_regla_disputada_solo_avisa_y_no_toca_la_disputa():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        (Path(raiz) / "db").mkdir()
        paquete_con_reglas(raiz, "alfa", "sql", "ALF")
        disputa = "Abre: Ana\nBloqueo: ALF-01 en a.sql\nPor qué: falso positivo\n"
        escribir(raiz, {".claude/registro/disputas/ALF-01.md": disputa, ".claude/registro/disputas/SQL-01.md": disputa})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0, (codigo, out, err)
        ls = out.splitlines()
        assert "SQL-01 solo avisa: disputada (.claude/registro/disputas/SQL-01.md)" in ls, ls
        assert ls[-1] == "ALF-01 solo avisa: disputada (.claude/registro/disputas/ALF-01.md)", ls
        assert sorted(os.listdir(Path(raiz) / ".claude" / "registro" / "disputas")) == ["ALF-01.md", "SQL-01.md"]
        assert registro(raiz)["paquetes"]["sql"]["alfa"]["ALF-01"]["atrapa_su_sembrado"] is True, "la calibración se guarda igual"
        shutil.rmtree(Path(raiz) / ".claude" / "registro" / "disputas")
        escribir(raiz, {".claude/registro/disputas": "no soy una carpeta"})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0 and out.splitlines()[-1] == "ALF-01 solo avisa: .claude/registro/disputas no se puede leer", (codigo, out, err)


MODULO_CON_RUTAS = ('import types\n'
                    '\n'
                    'MIGRACION = types.SimpleNamespace(id="SQL-01", sembrado=%(migracion)r)\n'
                    'VISTA = types.SimpleNamespace(id="SQL-02", sembrado=%(vista)r)\n'
                    'REGLAS = (MIGRACION, VISTA)\n'
                    '\n'
                    '\n'
                    'def verificar(ctx):\n'
                    '    res = []\n'
                    '    for n, t in ctx["agregadas"]:\n'
                    '        if "DROP" in t and ctx["relativa"].startswith("Migrations/") and ctx["relativa"].endswith(".sql"):\n'
                    '            res.append({"id": MIGRACION.id, "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "m"})\n'
                    '        if "MALO" in t and ctx["relativa"].endswith(".vista"):\n'
                    '            res.append({"id": VISTA.id, "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "m"})\n'
                    '    return res\n')
CAPAS_CON_DOS_EXTENSIONES = {"sql": {"extensions": [".sql", ".vista"]}}
SEMBRADOS_CON_RUTA = {"migracion": {"ruta": "Migrations/0001_alta.sql", "texto": "DROP TABLE t;\n"},
                      "vista": {"ruta": "Views/lista.vista", "texto": "<p>MALO</p>\n"}}


def test_guardar_una_regla_con_alcance_por_ruta_o_por_extension_atrapa_su_sembrado_con_ruta():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_RUTAS % {"migracion": "DROP TABLE t;", "vista": "<p>MALO</p>"}, capas=CAPAS_CON_DOS_EXTENSIONES)
        (Path(raiz) / "db").mkdir()
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0 and out.splitlines()[-2:] == ["SQL-01 solo avisa: no atrapa su sembrado",
                                                         "SQL-02 solo avisa: no atrapa su sembrado"], (codigo, out, err)
        instancia(raiz, modulo=MODULO_CON_RUTAS % SEMBRADOS_CON_RUTA, capas=CAPAS_CON_DOS_EXTENSIONES)
        escribir(raiz, {"db/Migrations/0002.sql": "SELECT 1;\n", "db/Views/b.vista": "<p>bien</p>\n", "db/a.sql": "DROP TABLE x;\n"})
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0 and out.splitlines() == ["SQL-01 archivos=0 aciertos=0", "SQL-02 archivos=0 aciertos=0",
                                                    "calibracion guardada en %s" % REGISTRO,
                                                    "SQL-01 puede bloquear", "SQL-02 puede bloquear"], (codigo, out, err)
        reglas = registro(raiz)["capas"]["sql"]
        assert reglas["SQL-01"]["atrapa_su_sembrado"] is True and reglas["SQL-02"]["atrapa_su_sembrado"] is True, reglas
        assert reglas["SQL-01"]["archivos_del_corpus"] == 3, reglas


def test_guardar_el_sembrado_con_ruta_le_llega_al_modulo_como_un_archivo_nuevo_del_repo_con_esa_ruta():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO.replace('REGLAS = [Regla("SQL-01", _mal)',
                                              'REGLAS = [Regla("SQL-01", _mal, {"ruta": "Migrations/0001.sql", "texto": "SELECT MAL\\n"})'
                                              ).replace('"id funcion"', '"id funcion sembrado", defaults=(None,)'))
        (Path(raiz) / "db").mkdir()
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0 and "SQL-01 puede bloquear" in out.splitlines(), (codigo, out, err)
        ctx = [e["ctx"] for e in traza(raiz) if e["evento"] == "verificar"][-1]
        assert ctx["ruta"] == os.path.join(os.path.abspath(Path(raiz) / "db"), "Migrations", "0001.sql"), ctx["ruta"]
        assert {k: ctx[k] for k in ("relativa", "relativa_repo", "origen", "capa", "texto", "es_nuevo", "agregadas", "limite")} == {
            "relativa": "Migrations/0001.sql", "relativa_repo": "Migrations/0001.sql", "origen": "repo", "capa": "sql",
            "texto": "SELECT MAL\n", "es_nuevo": True, "agregadas": [[1, "SELECT MAL"]], "limite": None}, ctx


def test_guardar_un_sembrado_de_texto_llega_igual_que_antes():
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO.replace('REGLAS = [Regla("SQL-01", _mal)', 'REGLAS = [Regla("SQL-01", _mal, "SELECT MAL")'
                                              ).replace('"id funcion"', '"id funcion sembrado", defaults=(None,)'))
        (Path(raiz) / "db").mkdir()
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 0 and "SQL-01 puede bloquear" in out.splitlines(), (codigo, out, err)
        ctx = [e["ctx"] for e in traza(raiz) if e["evento"] == "verificar"][-1]
        assert ctx["ruta"] == os.path.join(os.path.abspath(Path(raiz) / "db"), "sembrado.sql"), ctx["ruta"]
        assert (ctx["relativa"], ctx["relativa_repo"], ctx["origen"], ctx["bytes"]) == ("sembrado.sql", "sembrado.sql", "repo",
                                                                                         b"SELECT MAL".hex()), ctx


def test_guardar_un_sembrado_con_ruta_invalido_es_lo_mismo_que_no_tenerlo():
    invalidos = ({"ruta": "/Migrations/a.sql", "texto": "DROP TABLE t;"}, {"ruta": "../a.sql", "texto": "DROP TABLE t;"},
                 {"ruta": "Migrations/a.sql", "texto": ""}, {"ruta": "", "texto": "DROP TABLE t;"}, {"texto": "DROP TABLE t;"},
                 {"ruta": "Migrations/a.sql", "texto": 3})
    for sembrado in invalidos:
        with temporal() as raiz:
            instancia(raiz, modulo=MODULO_CON_RUTAS % dict(SEMBRADOS_CON_RUTA, migracion=sembrado), capas=CAPAS_CON_DOS_EXTENSIONES)
            (Path(raiz) / "db").mkdir()
            codigo, out, err = calibrar(raiz, "--guardar")
            assert codigo == 0 and out.splitlines()[-2:] == ["SQL-01 solo avisa: sin sembrado", "SQL-02 puede bloquear"], (sembrado, codigo, out, err)
            assert registro(raiz)["capas"]["sql"]["SQL-01"]["atrapa_su_sembrado"] is False, sembrado


PLANTILLA_DE_LA_SUITE = AQUI.parent / "plantillas" / "reglas" / "verificar.tests.py"


def test_la_suite_de_la_plantilla_acepta_los_dos_sembrados_y_comprueba_que_la_regla_los_atrapa():
    casos = {
        "los dos atrapan": ({"migracion": "DROP en Migrations", "vista": SEMBRADOS_CON_RUTA["vista"]}, 0, None),
        "solo rutas": (SEMBRADOS_CON_RUTA, 0, None),
        "texto que no atrapa": ({"migracion": "DROP TABLE t;", "vista": SEMBRADOS_CON_RUTA["vista"]}, 1, "SQL-01 no atrapa su sembrado"),
        "ruta que no atrapa": ({"migracion": {"ruta": "Otros/0001.sql", "texto": "DROP TABLE t;"}, "vista": SEMBRADOS_CON_RUTA["vista"]}, 1,
                               "SQL-01 no atrapa su sembrado"),
        "ruta absoluta": ({"migracion": {"ruta": "/Migrations/0001.sql", "texto": "DROP TABLE t;"}, "vista": SEMBRADOS_CON_RUTA["vista"]}, 1,
                          "la ruta del sembrado de SQL-01"),
        "texto vacio": ({"migracion": {"ruta": "Migrations/0001.sql", "texto": " "}, "vista": SEMBRADOS_CON_RUTA["vista"]}, 1,
                        "el texto del sembrado de SQL-01"),
        "clave de mas": ({"migracion": dict(SEMBRADOS_CON_RUTA["migracion"], otra=1), "vista": SEMBRADOS_CON_RUTA["vista"]}, 1,
                         "el sembrado de SQL-01 lleva solo ruta y texto"),
    }
    suite = PLANTILLA_DE_LA_SUITE.read_text(encoding="utf-8")
    for que, (sembrados, esperado, motivo) in casos.items():
        with temporal() as raiz:
            alcance = 'ctx["relativa"].startswith("Migrations/") and ctx["relativa"].endswith(".sql")'
            modulo = MODULO_CON_RUTAS.replace(alcance, '(%s or "Migrations" in t)' % alcance) % sembrados
            instancia(raiz, modulo=modulo, suite=suite, capas=CAPAS_CON_DOS_EXTENSIONES)
            prueba = subprocess.run([sys.executable, str(_RUTA), "--test", "sql", "--raiz", str(raiz)], capture_output=True, cwd=str(raiz))
            codigo, out, err = prueba.returncode, prueba.stdout.decode("utf-8"), prueba.stderr.decode("utf-8")
            assert codigo == esperado and "Traceback" not in err, (que, codigo, out, err)
            fallas = [l for l in out.splitlines() if l.startswith(("FALLA", "ERROR"))]
            if motivo is None:
                assert not fallas and out.splitlines()[-1].endswith("pruebas en verde"), (que, out)
            else:
                assert len(fallas) == 1 and fallas[0].startswith("FALLA test_cada_sembrado_") and motivo in fallas[0], (que, out)


def test_guardar_un_paquete_cuyo_REGLAS_sale_con_SystemExit_es_un_error_y_no_corta_el_script():
    modulo = ('import sys\n'
              'class _Reglas:\n'
              '    def __iter__(self):\n'
              '        sys.exit(3)\n'
              'REGLAS = _Reglas()\n'
              'def verificar(ctx):\n'
              '    return []\n')
    with temporal() as raiz:
        instancia(raiz, modulo=MODULO_CON_SEMBRADO)
        (Path(raiz) / "db").mkdir()
        paquete_con_reglas(raiz, "alfa", "sql", "ALF", modulo=modulo)
        codigo, out, err = calibrar(raiz, "--guardar")
        assert codigo == 1 and not (Path(raiz) / ".claude" / "registro").exists(), (codigo, out, err)
        assert "reglas: paquete alfa: REGLAS: SystemExit: 3" in err.splitlines() and "no se guarda la calibracion" in err, err


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
