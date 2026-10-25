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
