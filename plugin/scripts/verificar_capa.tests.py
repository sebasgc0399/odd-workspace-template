import contextlib
import importlib.util
import io
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
_RUTA = AQUI / "verificar_capa.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []


def _cargar():
    spec = importlib.util.spec_from_file_location("verificar_capa", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


AISLAMIENTO_GIT = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in AISLAMIENTO_GIT}


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "core.autocrlf=false", "-c", "maintenance.auto=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno_sin_git())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def escribir(raiz, rel, texto):
    p = Path(raiz) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)
    return p


def commitear(repo, mensaje="c"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", mensaje)


STUB_CTX = '''import json
def verificar(ctx):
    info = {k: ctx[k] for k in ("relativa", "relativa_repo", "origen", "capa", "es_nuevo", "agregadas", "hunks")}
    info["texto_igual_a_bytes"] = ctx["texto"] == ctx["bytes"].decode("utf-8-sig")
    info["ruta_existe"] = __import__("os").path.exists(ctx["ruta"])
    return [{"id": "T-01", "modo": "aviso", "severidad": "", "linea": None, "fragmento": None,
             "mensaje": "CTX " + json.dumps(info)}]
'''

STUB_MALO = '''import types
REGLAS = (types.SimpleNamespace(id="T-02", sembrado="x = MALO BLOQ;"),)
def verificar(ctx):
    out = []
    for n, t in ctx["agregadas"]:
        if "MALO" in t:
            out.append({"id": "T-02", "modo": "bloqueo" if "BLOQ" in t else "aviso", "severidad": "CRITICAL",
                        "linea": n, "fragmento": "MALO", "mensaje": "est\\u00e1 mal \\u2192 as\\u00ed, molde: x/y.cs"})
    return out
'''

STUB_SIN_SEVERIDAD = '''def verificar(ctx):
    return [{"id": "T-03", "modo": "aviso", "severidad": "", "linea": 1, "fragmento": None, "mensaje": "uno"},
            {"id": "T-04", "modo": "aviso", "severidad": "", "linea": None, "fragmento": None, "mensaje": "dos"}]
'''

STUB_ALCANCE = '''import types
REGLAS = (types.SimpleNamespace(id="T-05", sembrado="XX"),)
def verificar(ctx):
    if (ctx["relativa_repo"] or "").startswith("src/legado/"):
        return []
    return [{"id": "T-05", "modo": "bloqueo", "severidad": "CRITICAL", "linea": n, "fragmento": "XX", "mensaje": "XX fuera del legado"}
            for n, t in ctx["agregadas"] if "XX" in t]
'''

STUB_IMPORTA_LA_BIBLIOTECA = '''import types
from odd_ws.comun import lineas
REGLAS = (types.SimpleNamespace(id="T-06", sembrado="MALO"),)
def verificar(ctx):
    return [{"id": "T-06", "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "lineas de la biblioteca: \\u00f1 %d" % len(lineas(ctx["texto"]))}
            for n, t in ctx["agregadas"] if "MALO" in t]
'''

PROC = "CREATE PROC Proc_A\nAS\nBEGIN\n\tSELECT 1;\nEND\n"


class Mundo:
    def __init__(self, base_sql=True, db=None, repos="repos"):
        self.base_sql = base_sql
        self.db_archivos = db
        self.repos = repos

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="verificar-capa-test-"))
        self.raiz = self.base / "inst"
        self.raiz.mkdir()
        git(self.raiz, "init", "-q")
        escribir(self.raiz, "README.md", "x\n")
        commitear(self.raiz, "base")
        self.web = self.base / self.repos / "web"
        self.web.mkdir(parents=True)
        git(self.web, "init", "-q")
        self.db = self.base / self.repos / "db"
        self.db.mkdir(parents=True)
        git(self.db, "init", "-q")
        if self.db_archivos is not None:
            for rel, texto in self.db_archivos.items():
                escribir(self.db, rel, texto)
            commitear(self.db, "base")
            git(self.db, "update-ref", "refs/remotes/origin/main", "HEAD")
            git(self.db, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        sql = {"extensions": [".sql"], "repos": ["db"], "workshop": ["tickets/**/T-[0-9]*/SQL/esq.*.sql"]}
        if self.base_sql:
            sql["workshop_baseline"] = {"repo": "db", "under": "src", "strip_prefix": "esq."}
        config = {"schema_version": 1, "repos": {"web": {}, "db": {}},
                  "layers": {"web": {"extensions": [".cs"], "repos": ["web"]}, "sql": sql}}
        escribir(self.raiz, "workspace.config.json", json.dumps(config))
        escribir(self.raiz, "workspace.local.json", json.dumps({"repos": {"web": {"path": str(self.web)}, "db": {"path": str(self.db)}}}))
        return self

    def modulo(self, capa, fuente):
        escribir(self.raiz, ".claude/reglas/verificar_%s.py" % capa, fuente)

    def calibrar(self, capa, carpeta=None):
        import reglas
        carpeta = Path(carpeta) if carpeta is not None else self.base / "corpus-vacio"
        carpeta.mkdir(parents=True, exist_ok=True)
        salida, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = reglas.main(["--calibrar", capa, str(carpeta), "--guardar", "--raiz", str(self.raiz)])
        assert codigo == 0, (codigo, salida.getvalue(), error.getvalue())
        return salida.getvalue()

    def config(self):
        import config_loader
        return config_loader.cargar(self.raiz)

    def correr(self, e, plazo=25):
        return M.correr(e, raiz=self.raiz, plazo=plazo)

    def taller(self, nombre, texto, commit=False):
        p = escribir(self.raiz, "tickets/T-1-x/SQL/" + nombre, texto)
        if commit:
            commitear(self.raiz, "linea base")
        return p

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def evento(ruta, herramienta="Edit", nombre="PostToolUse", **extra):
    e = {"hook_event_name": nombre, "tool_name": herramienta, "session_id": "s1", "tool_input": {"file_path": str(ruta)}}
    e.update(extra)
    return e


def ctx_de(salida):
    d = json.loads(salida)
    linea = [l for l in d["hookSpecificOutput"]["additionalContext"].split("\n") if "CTX " in l][0]
    return json.loads(linea.split("CTX ", 1)[1])


def reportado(mundo, ruta):
    mundo.modulo("web", STUB_CTX)
    mundo.modulo("sql", STUB_CTX)
    codigo, out, err = mundo.correr(evento(ruta))
    assert codigo == 0 and out, (codigo, out, err)
    return ctx_de(out)


class SinSubprocess:
    def __enter__(self):
        self.original = M.subprocess.run
        self.llamadas = []

        def prohibido(*a, **k):
            self.llamadas.append(a)
            raise AssertionError("se lanzo un subprocess")

        M.subprocess.run = prohibido
        return self

    def __exit__(self, *_):
        M.subprocess.run = self.original


@contextlib.contextmanager
def subprocess_falso(funcion):
    original = M.subprocess.run
    M.subprocess.run = funcion
    try:
        yield
    finally:
        M.subprocess.run = original


def test_fuera_de_las_capas_sale_sin_lanzar_subprocess():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.modulo("sql", STUB_MALO)
        rutas = [w.raiz / "README.md", w.raiz / "tickets" / "T-1" / "SQL" / "otro.Proc.sql", w.base / "otro" / "A.cs",
                 w.web / "build.gradle", w.raiz / "tickets" / "T-1" / "SQL" / "sub" / "esq.A.sql"]
        with SinSubprocess() as guardia:
            for ruta in rutas:
                for herr in ("Edit", "Write"):
                    assert w.correr(evento(ruta, herr)) == (0, "", b""), (herr, ruta)
        assert not guardia.llamadas, guardia.llamadas


def test_otros_eventos_y_herramientas_salen_en_silencio():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        assert w.correr(evento(ruta))[0] == 2, "control positivo: el caso base bloquea"
        assert w.correr(evento(ruta, "Write"))[0] == 2
        for e in (evento(ruta, "Read"), evento(ruta, "Bash"), evento(ruta, "MultiEdit"), evento(ruta, nombre="PreToolUse"),
                  evento(ruta, nombre="SessionStart"), evento(ruta, nombre="SubagentStop"), {"tool_name": "Edit"}, {}):
            assert w.correr(e) == (0, "", b""), e


def test_falla_abierta_ante_cualquier_error_interno():
    with Mundo() as w:
        escribir(w.web, "Core/A.cs", "int a;\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        assert w.correr(evento(ruta)) == (0, "", b""), "sin modulo de la capa"
        for fuente in ("def verificar(ctx):\n    raise RuntimeError('boom')\n", "def verificar(ctx) syntax error\n",
                       "def verificar(ctx):\n    return 42\n", "import sys\ndef verificar(ctx):\n    sys.exit(3)\n",
                       "def verificar(ctx):\n    return [{'id': 'X'}]\n", "VERIFICAR = 1\n"):
            w.modulo("web", fuente)
            assert w.correr(evento(ruta)) == (0, "", b""), fuente
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        assert w.correr(evento(w.web / "no-existe" / "A.cs")) == (0, "", b""), "archivo inexistente"
        assert M.correr("esto no es json {", raiz=w.raiz) == (0, "", b"")
        assert w.correr({"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": None}) == (0, "", b"")
        assert w.correr({"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": 3}}) == (0, "", b"")

        def sin_git(*a, **k):
            raise FileNotFoundError("git")

        def lento(*a, **k):
            raise subprocess.TimeoutExpired("git", 5)

        for falso in (sin_git, lento):
            with subprocess_falso(falso):
                assert w.correr(evento(ruta)) == (0, "", b""), falso.__name__
        assert w.correr(evento(ruta))[0] == 2, "control: sin las fallas, bloquea"


def test_un_hallazgo_invalido_calla_el_archivo_entero():
    valido = '{"id": "T-02", "modo": "bloqueo", "severidad": "", "linea": None, "fragmento": None, "mensaje": "valido"}'
    for extra in ("", ', {"id": "T-02", "modo": "bloqueo"}', ', {"modo": "bloqueo", "mensaje": "sin id"}', ', "no soy un hallazgo"',
                  ', {"id": "T-02", "modo": "bloqueo", "severidad": "", "linea": None, "fragmento": None, "mensaje": ""}',
                  ', {"id": "", "modo": "bloqueo", "severidad": "", "linea": None, "fragmento": None, "mensaje": "sin id"}'):
        with Mundo() as w:
            w.modulo("web", "import types\nREGLAS = (types.SimpleNamespace(id='T-02', sembrado='x'),)\n"
                            "def verificar(ctx):\n    return [%s%s]\n" % (valido, extra))
            if not extra:
                w.calibrar("web")
            ruta = escribir(w.web, "Core/A.cs", "int a;\n")
            codigo, out, err = w.correr(evento(ruta))
            if extra:
                assert (codigo, out, err) == (0, "", b""), extra
            else:
                assert codigo == 2 and b"valido" in err, "control: solo el valido bloquea"


def test_sin_instancia_o_con_config_rota_calla():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        assert w.correr(evento(ruta))[0] == 2, "control"
        escribir(w.raiz, "workspace.config.json", "{rota")
        assert w.correr(evento(ruta)) == (0, "", b""), "config rota: los hooks no bloquean"
        os.remove(w.raiz / "workspace.config.json")
        assert w.correr(evento(ruta)) == (0, "", b""), "sin instancia"


def test_main_lee_stdin_y_falla_abierto():
    with Mundo() as w:
        env = dict(_entorno_sin_git(), CLAUDE_PROJECT_DIR=str(w.raiz))
        for entrada in ("", "no es json", "[]", "null"):
            r = subprocess.run([sys.executable, str(_RUTA), "--plazo", "25"], input=entrada.encode("utf-8"),
                               capture_output=True, timeout=60, env=env)
            assert r.returncode == 0 and r.stdout == b"" and r.stderr == b"", (entrada, r)


def test_ctx_archivo_sin_trackear_es_nuevo_con_todo_agregado():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "int a;\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/Foo/Nuevo.cs", "uno\r\ndos\r\ntres\r\n")
        c = reportado(w, ruta)
        assert c["es_nuevo"] is True, c
        assert (c["relativa"], c["relativa_repo"], c["capa"], c["origen"]) == ("Core/Foo/Nuevo.cs", "Core/Foo/Nuevo.cs", "web", "repo"), c
        assert c["agregadas"] == [[1, "uno"], [2, "dos"], [3, "tres"]], c["agregadas"]
        assert c["hunks"] == [{"agregadas": [[1, "uno"], [2, "dos"], [3, "tres"]], "quitadas": []}], c["hunks"]
        assert c["texto_igual_a_bytes"] and c["ruta_existe"], c


def test_ctx_archivo_en_el_indice_pero_no_en_head_es_nuevo():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "int a;\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/Staged.cs", "x\ny\n")
        git(w.web, "add", "Core/Staged.cs")
        c = reportado(w, ruta)
        assert c["es_nuevo"] is True and len(c["agregadas"]) == 2, c


def test_ctx_repo_sin_commits_todo_es_nuevo():
    with Mundo() as w:
        ruta = escribir(w.web, "Core/Base.cs", "int a;\n")
        c = reportado(w, ruta)
        assert c["es_nuevo"] is True and c["agregadas"] == [[1, "int a;"]], c


def test_ctx_archivo_modificado_solo_trae_el_diff():
    with Mundo() as w:
        escribir(w.web, "Core/A.cs", "uno\ndos\ntres\ncuatro\ncinco\nseis\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "uno\nDOS nuevo\ntres\ncuatro\ncinco\nseis\nsiete\nocho\n")
        c = reportado(w, ruta)
        assert c["es_nuevo"] is False
        assert c["agregadas"] == [[2, "DOS nuevo"], [7, "siete"], [8, "ocho"]], c["agregadas"]
        assert c["hunks"] == [{"agregadas": [[2, "DOS nuevo"]], "quitadas": ["dos"]},
                              {"agregadas": [[7, "siete"], [8, "ocho"]], "quitadas": []}], c["hunks"]


def test_ctx_archivo_sin_cambios_no_tiene_agregadas():
    with Mundo() as w:
        ruta = escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        c = reportado(w, ruta)
        assert c["es_nuevo"] is False and c["agregadas"] == [] and c["hunks"] == [], c


def test_ctx_taller_sin_linea_base_configurada_es_nuevo_y_relativa_es_el_nombre():
    with Mundo(base_sql=False) as w:
        ruta = w.taller("esq.Proc_A.sql", "SELECT 1\r\n")
        c = reportado(w, ruta)
        assert (c["relativa"], c["relativa_repo"], c["origen"], c["capa"]) == ("esq.Proc_A.sql", None, "taller", "sql"), c
        assert c["es_nuevo"] is True and c["agregadas"] == [[1, "SELECT 1"]], c


def test_ctx_worktree_del_repo_es_el_repo_con_la_relativa_del_worktree():
    with Mundo() as w:
        escribir(w.web, "Core/A.cs", "x\n")
        commitear(w.web)
        arbol = w.base / "worktrees" / "web--rama"
        git(w.web, "worktree", "add", "-q", "-b", "rama", str(arbol))
        ruta = escribir(arbol, "Core/B.cs", "y\n")
        c = reportado(w, ruta)
        assert (c["capa"], c["origen"], c["relativa"]) == ("web", "repo", "Core/B.cs"), c


def test_filtro_descarta_lo_que_ya_estaba_en_una_linea_quitada_del_mismo_hunk():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        escribir(w.web, "Core/A.cs", "int a; // MALO viejo\nint b;\nint c;\nint d;\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "int a = 2; // MALO viejo\nint b;\nint c;\nint d; // MALO nuevo\nint e; // MALO otro\n")
        codigo, out, err = w.correr(evento(ruta))
        contexto = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        assert codigo == 0 and err == b""
        assert "linea 1 en «MALO»:" not in contexto, contexto
        assert "linea 4 en «MALO»:" in contexto and "linea 5 en «MALO»:" in contexto, contexto
        assert "tiene 2 aviso(s)" in contexto, contexto


def test_filtro_no_toca_archivos_nuevos_ni_hallazgos_sin_fragmento():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "x\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/N.cs", "a // MALO\nb // MALO\n")
        w.modulo("web", STUB_MALO)
        assert "tiene 2 aviso(s)" in w.correr(evento(ruta))[1]
        w.modulo("web", STUB_SIN_SEVERIDAD)
        assert "tiene 2 aviso(s)" in w.correr(evento(ruta))[1]


def _hall(id_, linea, fragmento):
    return {"id": id_, "modo": "aviso", "severidad": "", "linea": linea, "fragmento": fragmento, "mensaje": "m"}


def _hunk(agregadas, quitadas):
    return {"agregadas": [(n, "x") for n in agregadas], "quitadas": list(quitadas)}


def test_filtro_por_conteo_cada_quitada_cancela_a_lo_sumo_un_hallazgo():
    quitada = "error(217) vieja"
    for etiqueta, id_, quitadas, lineas, esperado in (
        ("1 quitado y 2 agregados", "R-27", [quitada], [1, 2], 1),
        ("1 quitado y 1 agregado", "R-27", [quitada], [1], 0),
        ("0 quitados", "R-27", [], [1, 2], 2),
        ("2 quitados y 1 agregado", "R-27", [quitada, quitada], [1], 0),
        ("2 quitados y 2 agregados", "R-27", [quitada, quitada], [1, 2], 0),
        ("otra regla: 1 quitado y 2 agregados", "W-10", [quitada], [1, 2], 1),
        ("otra regla: 1 quitado y 1 agregado", "W-10", [quitada], [1], 0),
    ):
        hallazgos = [_hall(id_, n, "217") for n in lineas]
        assert len(M.filtrar_preexistentes(hallazgos, [_hunk(lineas, quitadas)])) == esperado, etiqueta
    hallazgos = [_hall("R-27", 1, "217"), _hall("R-27", 2, "217")]
    assert [h["linea"] for h in M.filtrar_preexistentes(hallazgos, [_hunk([1, 2], ["217"])])] == [2]
    resultado = M.filtrar_preexistentes([_hall("R-27", 1, "217"), _hall("R-27", 5, "217")], [_hunk([1], ["217"]), _hunk([5], [])])
    assert [h["linea"] for h in resultado] == [5], resultado


def test_filtro_extremo_a_extremo_una_quitada_cancela_uno_de_dos():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        escribir(w.web, "Core/A.cs", "int a; // MALO viejo\nint b;\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "int a; // MALO nuevo\nint z; // MALO otro\nint b;\n")
        contexto = json.loads(w.correr(evento(ruta))[1])["hookSpecificOutput"]["additionalContext"]
        assert "tiene 1 aviso(s)" in contexto and "linea 2 en «MALO»:" in contexto and "linea 1 en «MALO»:" not in contexto, contexto


def test_salida_con_bloqueo_exit_2_stderr_en_bytes_utf8():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "x\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/N.cs", "a // MALO\nb // MALO BLOQ\nc\n")
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        codigo, out, err = w.correr(evento(ruta))
        assert codigo == 2 and out == "" and isinstance(err, bytes)
        lineas = err.decode("utf-8").rstrip("\n").split("\n")
        assert lineas[0] == "verificar-capa: Core/N.cs tiene 2 problema(s): corregir y reintentar.", lineas[0]
        assert lineas[1] == "[T-02 CRITICAL] linea 2 en «MALO»: está mal → así, molde: x/y.cs", lineas[1]
        assert lineas[2] == "[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs", lineas[2]
        assert len(lineas) == 3, lineas


def test_la_cita_del_fragmento_va_en_una_linea_y_corta_lo_largo():
    assert M.cita_del_fragmento({"fragmento": None}) == ""
    assert M.cita_del_fragmento({}) == ""
    assert M.cita_del_fragmento({"fragmento": "  \n "}) == ""
    assert M.cita_del_fragmento({"fragmento": 7}) == ""
    assert M.cita_del_fragmento({"fragmento": ["a"]}) == ""
    assert M.cita_del_fragmento({"fragmento": "a\n   b"}) == " en «a b»"
    largo = "x" * (M.LARGO_DE_LA_CITA + 5)
    assert M.cita_del_fragmento({"fragmento": largo}) == " en «%s…»" % ("x" * (M.LARGO_DE_LA_CITA - 1))
    assert M.cita_del_fragmento({"fragmento": "y" * M.LARGO_DE_LA_CITA}) == " en «%s»" % ("y" * M.LARGO_DE_LA_CITA)


def test_un_hallazgo_de_archivo_con_fragmento_lo_cita():
    with Mundo() as w:
        ruta = escribir(w.web, "Core/N.cs", "a\n")
        w.modulo("web", 'def verificar(ctx):\n    return [{"id": "T-12", "modo": "aviso", "severidad": "", "linea": None, '
                        '"fragmento": "namespace Viejo", "mensaje": "todo el archivo"}]\n')
        codigo, out, err = w.correr(evento(ruta))
        assert codigo == 0 and err == b"" and contexto(out).split("\n")[1:] == ["[T-12] archivo en «namespace Viejo»: todo el archivo"], \
            (codigo, out, err)


def contexto_de(salida):
    codigo, out, err = salida
    assert codigo == 0 and err == b"" and out, salida
    return json.loads(out)["hookSpecificOutput"]["additionalContext"].split("\n")


REGLAS_PY = str(AQUI / "reglas.py")


CORREGIR = "corregir los hallazgos y después correr %s"


def interprete():
    from odd_ws import calibracion
    return calibracion.interprete()


def comando(carpeta, capa="web"):
    return '`%s "%s" --calibrar %s "%s" --guardar`' % (interprete(), REGLAS_PY, capa, carpeta)


def sin_calibrar(w):
    return " (aviso: sin calibrar; para que bloquee, %s)" % CORREGIR % comando(w.web)


def test_un_bloqueo_sin_calibrar_llega_como_aviso_con_el_motivo_y_el_comando():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        ruta = escribir(w.web, "Core/N.cs", "a // MALO\nb // MALO BLOQ\n")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[0] == ("verificar-capa (aviso): Core/N.cs tiene 2 aviso(s); el cambio ya quedó escrito: "
                             "corregirlo si es propio (no hace falta reintentar)."), lineas[0]
        assert lineas[1:] == ["[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs",
                              "[T-02 CRITICAL] linea 2 en «MALO»: está mal → así, molde: x/y.cs" + sin_calibrar(w)], lineas


def test_el_comando_del_aviso_se_corre_tal_cual_desde_la_raiz_con_espacios_en_las_rutas():
    with Mundo(repos="mis repos") as w:
        plugin = w.base / "mi plugin"
        shutil.copytree(PLUGIN, plugin, ignore=shutil.ignore_patterns("__pycache__", "*.tests.py"))
        hook = [sys.executable, str(plugin / "scripts" / "verificar_capa.py"), "--plazo", "25"]
        env = dict(_entorno_sin_git(), CLAUDE_PROJECT_DIR=str(w.raiz), PYTHONIOENCODING="utf-8")
        w.modulo("web", STUB_MALO)
        escribir(w.web, "Core/Base.cs", "a\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        e = json.dumps(evento(ruta)).encode("utf-8")
        aviso = subprocess.run(hook, input=e, capture_output=True, env=env, timeout=120)
        assert aviso.returncode == 0 and aviso.stderr == b"", aviso
        texto = json.loads(aviso.stdout)["hookSpecificOutput"]["additionalContext"]
        copiado = re.search(r"correr `([^`]+)`", texto).group(1)
        partes = re.fullmatch(r'(\S+) "([^"]+)" --calibrar web "([^"]+)" --guardar', copiado)
        assert partes and partes.group(1) == interprete(), copiado
        assert os.path.realpath(partes.group(2)) == os.path.realpath(plugin / "scripts" / "reglas.py"), copiado
        assert os.path.realpath(partes.group(3)) == os.path.realpath(w.web), copiado
        escribir(w.web, "Core/N.cs", "b\n")
        en_la_terminal = {k: v for k, v in env.items() if k != "CLAUDE_PROJECT_DIR"}
        corrido = subprocess.run(copiado, shell=True, cwd=str(w.raiz), capture_output=True, env=en_la_terminal, timeout=120)
        salida = corrido.stdout.decode("utf-8")
        assert corrido.returncode == 0 and salida.splitlines()[-1] == "T-02 puede bloquear", (copiado, corrido)
        assert json.loads((w.raiz / ".claude/registro/calibracion.json").read_text(encoding="utf-8"))["capas"]["web"]["T-02"]["corpus"]["repo"] == "web"
        escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        bloqueo = subprocess.run(hook, input=e, capture_output=True, env=env, timeout=120)
        assert bloqueo.returncode == 2 and "[T-02 CRITICAL] linea 1 en «MALO»:" in bloqueo.stderr.decode("utf-8"), bloqueo


def test_calibrado_con_reglas_py_bloquea_y_si_el_modulo_cambia_avisa_que_la_calibracion_es_vieja():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        corpus = w.web / "Core"
        salida = w.calibrar("web", corpus)
        assert "T-02 puede bloquear" in salida.splitlines(), salida
        ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        assert w.correr(evento(ruta))[0] == 2, "calibrada, bloquea"
        w.modulo("web", STUB_MALO.replace("\n", "\r\n"))
        assert w.correr(evento(ruta))[0] == 2, "el fin de línea no invalida la calibración"
        w.modulo("web", STUB_MALO + "\n")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1] == ("[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs (aviso: calibración vieja; para que bloquee, "
                             "%s)" % CORREGIR % comando(corpus)), lineas


def test_una_regla_sin_sembrado_o_un_modulo_sin_REGLAS_no_bloquea_aunque_el_registro_diga_que_si():
    sin_sembrado = STUB_MALO.replace('sembrado="x = MALO BLOQ;"', 'otro="x"')
    sin_reglas = STUB_MALO.replace("REGLAS = ", "_TODAS = ")
    for fuente in (sin_sembrado, sin_reglas):
        with Mundo() as w:
            w.modulo("web", fuente)
            huella = "sha256:" + __import__("hashlib").sha256(fuente.encode("utf-8")).hexdigest()
            regla = {"huella": huella, "atrapa_su_sembrado": True, "aciertos": 0, "aciertos_en_bloqueo": 0, "archivos_del_corpus": 0,
                     "corpus": {"repo": None, "commit": None, "ruta": "x"}, "fecha": "2026-11-20"}
            escribir(w.raiz, ".claude/registro/calibracion.json", json.dumps({"version": 1, "capas": {"web": {"T-02": regla}}}))
            ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
            lineas = contexto_de(w.correr(evento(ruta)))
            assert lineas[1].endswith(" (aviso: sin calibrar; para que bloquee, declarar su `sembrado` en REGLAS, %s)"
                                      % CORREGIR % comando(w.web)), lineas


def test_el_registro_roto_no_deja_bloquear_y_el_aviso_lo_dice():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        assert w.correr(evento(ruta))[0] == 2, "control: calibrada, bloquea"
        escribir(w.raiz, ".claude/registro/calibracion.json", "{roto")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1].endswith(" (aviso: registro de calibración roto; para que bloquee, arreglar o borrar "
                                  ".claude/registro/calibracion.json, %s)" % CORREGIR % comando(w.web)), lineas


def test_un_registro_anidado_sin_fondo_no_calla_el_hook_y_avisa_que_esta_roto():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        assert w.correr(evento(ruta))[0] == 2, "control: calibrada, bloquea"
        escribir(w.raiz, ".claude/registro/calibracion.json", '{"version": 1, "capas": %s}' % ("[" * 100000 + "]" * 100000))
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1].endswith(" (aviso: registro de calibración roto; para que bloquee, arreglar o borrar "
                                  ".claude/registro/calibracion.json, %s)" % CORREGIR % comando(w.web)), lineas


STUB_CON_RUTAS = '''import types
MIGRACION = types.SimpleNamespace(id="T-10", sembrado=%(migracion)r)
VISTA = types.SimpleNamespace(id="T-11", sembrado=%(vista)r)
REGLAS = (MIGRACION, VISTA)
def verificar(ctx):
    out = []
    for n, t in ctx["agregadas"]:
        if "MALO" in t and ctx["relativa"].startswith("Migrations/") and ctx["relativa"].endswith(".cs"):
            out.append({"id": MIGRACION.id, "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "migracion"})
        if "MALO" in t and ctx["relativa"].endswith(".cshtml"):
            out.append({"id": VISTA.id, "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "vista"})
    return out
'''


def test_una_regla_con_alcance_por_ruta_o_por_extension_calibrada_con_un_sembrado_con_ruta_bloquea():
    with Mundo() as w:
        config = json.loads((w.raiz / "workspace.config.json").read_text(encoding="utf-8"))
        config["layers"]["web"]["extensions"] = [".cs", ".cshtml"]
        escribir(w.raiz, "workspace.config.json", json.dumps(config))
        migracion = escribir(w.web, "Migrations/0002_baja.cs", "x = MALO;\n")
        vista = escribir(w.web, "Views/lista.cshtml", "<p>MALO</p>\n")
        fuera = escribir(w.web, "Core/N.cs", "x = MALO;\n")
        w.modulo("web", STUB_CON_RUTAS % {"migracion": "x = MALO;", "vista": "<p>MALO</p>"})
        salida = w.calibrar("web")
        assert {"T-10 solo avisa: no atrapa su sembrado", "T-11 solo avisa: no atrapa su sembrado"} <= set(salida.splitlines()), salida
        assert "no pasó la calibración; no atrapa su sembrado" in contexto_de(w.correr(evento(migracion)))[1]
        w.modulo("web", STUB_CON_RUTAS % {"migracion": {"ruta": "Migrations/0001_alta.cs", "texto": "x = MALO;"},
                                          "vista": {"ruta": "Views/alta.cshtml", "texto": "<p>MALO</p>"}})
        salida = w.calibrar("web")
        assert {"T-10 puede bloquear", "T-11 puede bloquear"} <= set(salida.splitlines()), salida
        codigo, _, err = w.correr(evento(migracion))
        assert codigo == 2 and problemas_de(err)[1:] == ["[T-10] linea 1: migracion"], (codigo, err)
        codigo, _, err = w.correr(evento(vista))
        assert codigo == 2 and problemas_de(err)[1:] == ["[T-11] linea 1: vista"], (codigo, err)
        assert w.correr(evento(fuera)) == (0, "", b""), "fuera de su alcance, la regla no ve nada"


REGLAS_QUE_SALEN = '''import sys
class _Reglas:
    def __iter__(self):
        sys.exit(3)
REGLAS = _Reglas()
def verificar(ctx):
    return [{"id": "%(id)s", "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "sale"}
            for n, t in ctx["agregadas"] if "MALO" in t]
'''


def test_un_REGLAS_que_sale_con_SystemExit_al_leerse_avisa_en_vez_de_callar_el_hook():
    with Mundo() as w:
        w.modulo("web", REGLAS_QUE_SALEN % {"id": "T-08"})
        ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1:] == ["[T-08] linea 1: sale (aviso: sin calibrar; para que bloquee, declarar su `sembrado` en REGLAS, "
                              "%s)" % CORREGIR % comando(w.web)], lineas


def test_un_paquete_cuyo_REGLAS_sale_con_SystemExit_avisa_y_no_calla_a_la_capa():
    with git_aislado(), Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        poner_paquete(w, "sale", "SAL", REGLAS_QUE_SALEN % {"id": "SAL-01"})
        codigo, out, err = w.correr(evento(archivo_con_malo(w)))
        assert codigo == 2 and out == "", (codigo, out, err)
        assert problemas_de(err)[1:] == ["[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs",
                                         "[SAL-01] linea 1: sale (aviso: sin calibrar; para que bloquee, declarar su `sembrado` en "
                                         "REGLAS (en el repo del paquete sale, con una etiqueta nueva), "
                                         "%s)" % CORREGIR % comando(w.web)], problemas_de(err)


def test_un_hallazgo_sin_modo_no_calla_el_hook_y_llega_como_aviso_con_el_motivo():
    with Mundo() as w:
        w.modulo("web", 'def verificar(ctx):\n    return [{"id": "T-09", "linea": 1, "mensaje": "sin modo"}]\n')
        ruta = escribir(w.web, "Core/N.cs", "b\n")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1:] == ["[T-09] linea 1: sin modo (aviso: modo inválido; el módulo tiene que devolver modo aviso o bloqueo)"], lineas


DISPUTA = "Abre: Ana, con el sí del usuario\nBloqueo: %s en Core/N.cs\nPor qué: falso positivo en un comentario\n"


def disputada(w, id_):
    return (" (aviso: disputada; se cierra borrando .claude/registro/disputas/%s.md en el commit que arregla el chequeo, "
            "y después correr %s)" % (id_, comando(w.web)))


def test_una_disputa_abierta_vuelve_a_aviso_y_borrarla_vuelve_a_bloquear():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        assert w.correr(evento(ruta))[0] == 2, "control: calibrada, bloquea"
        disputa = escribir(w.raiz, ".claude/registro/disputas/T-02.md", DISPUTA % "T-02")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1:] == ["[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs" + disputada(w, "T-02")], lineas
        disputa.unlink()
        assert w.correr(evento(ruta))[0] == 2, "cerrada la disputa, vuelve a bloquear"


def test_una_carpeta_de_disputas_ilegible_no_deja_bloquear_y_lo_dice():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/N.cs", "b // MALO BLOQ\n")
        escribir(w.raiz, ".claude/registro/disputas", "no soy una carpeta")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1].endswith(" (aviso: disputas ilegibles; para que bloquee, .claude/registro/disputas tiene que ser una carpeta "
                                  "legible, con un <ID>.md por disputa abierta)"), lineas


def test_salida_solo_avisos_exit_0_con_additional_context():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "x\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/N.cs", "a\n")
        w.modulo("web", STUB_SIN_SEVERIDAD)
        codigo, out, err = w.correr(evento(ruta))
        datos = json.loads(out)["hookSpecificOutput"]
        assert codigo == 0 and err == b"" and datos["hookEventName"] == "PostToolUse"
        lineas = datos["additionalContext"].split("\n")
        assert lineas[0] == ("verificar-capa (aviso): Core/N.cs tiene 2 aviso(s); el cambio ya quedó escrito: "
                             "corregirlo si es propio (no hace falta reintentar)."), lineas[0]
        assert lineas[1:] == ["[T-03] linea 1: uno", "[T-04] archivo: dos"], lineas


def test_salida_sin_hallazgos_nada():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "x\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/N.cs", "limpio\n")
        w.modulo("web", STUB_MALO)
        assert w.correr(evento(ruta)) == (0, "", b"")


def test_main_como_hook_real_con_un_modulo_que_importa_la_biblioteca():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "x\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/N.cs", "a\nb MALO\n")
        w.modulo("web", STUB_IMPORTA_LA_BIBLIOTECA)
        w.calibrar("web")
        env = {k: v for k, v in _entorno_sin_git().items() if k not in ("PYTHONPATH", "PYTHONUTF8")}
        env.update(CLAUDE_PROJECT_DIR=str(w.raiz / "tickets"), PYTHONIOENCODING="cp1252")
        (w.raiz / "tickets").mkdir(exist_ok=True)
        entrada = json.dumps(evento(ruta)).encode("utf-8")
        r = subprocess.run([sys.executable, str(_RUTA), "--plazo", "25"], input=entrada, capture_output=True,
                           timeout=60, env=env, cwd=str(w.base))
        assert r.returncode == 2 and r.stdout == b"", (r.returncode, r.stdout, r.stderr)
        assert "[T-06] linea 2: lineas de la biblioteca: ñ 2".encode("utf-8") in r.stderr, r.stderr


def foto(raiz):
    return sorted((str(p.relative_to(raiz)), p.stat().st_size, p.stat().st_mtime_ns) for p in Path(raiz).rglob("*") if p.is_file())


def test_git_corre_con_timeout_corto_y_sin_variables_de_repo():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "uno\ndos MALO\n")
        trampa = w.base / "trampa"
        trampa.mkdir()
        git(trampa, "init", "-q")
        previo = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_INDEX_FILE")}
        os.environ["GIT_DIR"] = str(trampa / ".git")
        os.environ["GIT_INDEX_FILE"] = str(w.base / "indice-del-commit")
        llamadas = []
        original = M.subprocess.run

        def espia(*a, **k):
            llamadas.append((a, k))
            return original(*a, **k)

        try:
            with subprocess_falso(espia):
                codigo, out, err = w.correr(evento(ruta))
        finally:
            for k, v in previo.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        assert llamadas
        for a, k in llamadas:
            assert 0 < (k.get("timeout") or 0) <= M.TIMEOUT_GIT, k.get("timeout")
            env = k.get("env")
            assert env is not None and not any(v in env for v in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")), a[0][:5]
        assert codigo == 0 and "linea 2 en «MALO»:" in contexto(out), (codigo, err)
        assert not (w.base / "indice-del-commit").exists()
        assert git(trampa, "rev-list", "--all") == ""


def test_no_escribe_nada_en_disco():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.modulo("sql", STUB_MALO)
        escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        a = escribir(w.web, "Core/A.cs", "uno\ndos MALO\n")
        n = escribir(w.web, "Core/N.cs", "nuevo MALO BLOQ\n")
        t = w.taller("esq.Proc_A.sql", "MALO\n")
        antes = foto(w.base)
        for ruta in (a, n, t):
            w.correr(evento(ruta))
        assert foto(w.base) == antes, set(foto(w.base)) ^ set(antes)


def test_git_diff_no_reescribe_la_cache_de_stat_del_indice():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        ruta = escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        git(w.web, "update-index", "--refresh")
        time.sleep(1.2)
        os.utime(ruta, None)
        indice = w.web / ".git" / "index"
        antes = indice.read_bytes()
        assert w.correr(evento(ruta))[0] == 0
        assert indice.read_bytes() == antes


def test_linea_base_copia_sin_trackear_se_compara_con_su_original():
    with Mundo(db={"src/legado/Proc_A.sql": PROC}) as w:
        copia = PROC.replace("\n", "\r\n").replace("\tSELECT 1;\r\n", "\tSELECT 1;\r\n\tSELECT 2;\r\n")
        ruta = w.taller("esq.Proc_A.sql", copia)
        c = reportado(w, ruta)
        assert c["es_nuevo"] is False, c
        assert c["relativa_repo"] == "src/legado/Proc_A.sql", c
        assert c["relativa"] == "esq.Proc_A.sql", c
        assert c["agregadas"] == [[5, "\tSELECT 2;"]], c["agregadas"]


def test_linea_base_el_prefijo_y_el_nombre_no_distinguen_mayusculas():
    with Mundo(db={"src/legado/PROC_A.sql": PROC}) as w:
        ruta = w.taller("ESQ.proc_a.sql", PROC)
        c = reportado(w, ruta)
        assert c["relativa_repo"] == "src/legado/PROC_A.sql" and c["agregadas"] == [], c


def test_linea_base_ausente_ambigua_o_sin_rama_es_nuevo():
    casos = [
        ("sin original", {"src/otro/Proc_B.sql": PROC}),
        ("dos candidatos", {"src/a/Proc_A.sql": PROC, "src/b/Proc_A.sql": PROC}),
        ("fuera de under", {"otra/Proc_A.sql": PROC}),
    ]
    for etiqueta, archivos in casos:
        with Mundo(db=archivos) as w:
            c = reportado(w, w.taller("esq.Proc_A.sql", "SELECT 1\r\n"))
            assert c["es_nuevo"] is True and c["relativa_repo"] is None and c["agregadas"] == [[1, "SELECT 1"]], (etiqueta, c)
    with Mundo(db={"src/legado/Proc_A.sql": PROC}) as w:
        git(w.db, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        c = reportado(w, w.taller("esq.Proc_A.sql", PROC))
        assert c["es_nuevo"] is True and c["relativa_repo"] is None, ("sin origin/HEAD", c)
    with Mundo() as w:
        c = reportado(w, w.taller("esq.Proc_A.sql", PROC))
        assert c["es_nuevo"] is True and c["relativa_repo"] is None, ("repo sin commits", c)


def test_linea_base_sin_strip_prefix_ni_under():
    with Mundo(db={"src/legado/esq.Proc_A.sql": PROC}) as w:
        config = json.loads((w.raiz / "workspace.config.json").read_text(encoding="utf-8"))
        config["layers"]["sql"]["workshop_baseline"] = {"repo": "db"}
        escribir(w.raiz, "workspace.config.json", json.dumps(config))
        c = reportado(w, w.taller("esq.Proc_A.sql", PROC))
        assert c["relativa_repo"] == "src/legado/esq.Proc_A.sql" and c["es_nuevo"] is False, c


def test_linea_base_trackeado_diff_contra_head_de_la_instancia_y_relativa_repo():
    with Mundo(db={"src/legado/Proc_A.sql": PROC}) as w:
        base = PROC.replace("\n", "\r\n")
        ruta = w.taller("esq.Proc_A.sql", base, commit=True)
        escribir(ruta.parent, ruta.name, base.replace("SELECT 1", "SELECT 3"))
        c = reportado(w, ruta)
        assert c["es_nuevo"] is False and [n for n, _ in c["agregadas"]] == [4], c
        assert c["relativa_repo"] == "src/legado/Proc_A.sql", c


def test_linea_base_permite_las_reglas_con_alcance_por_carpeta():
    with Mundo(db={"src/legado/Proc_A.sql": PROC, "src/nuevo/Proc_B.sql": PROC.replace("Proc_A", "Proc_B")}) as w:
        w.modulo("sql", STUB_ALCANCE)
        w.calibrar("sql")
        legado =w.taller("esq.Proc_A.sql", PROC.replace("\tSELECT 1;\n", "\tSELECT 1;\n\tXX;\n"))
        nuevo = w.taller("esq.Proc_B.sql", PROC.replace("Proc_A", "Proc_B").replace("\tSELECT 1;\n", "\tSELECT 1;\n\tXX;\n"))
        assert w.correr(evento(legado, "Write")) == (0, "", b"")
        codigo, _, err = w.correr(evento(nuevo, "Write"))
        assert codigo == 2 and "[T-05 CRITICAL] linea 5 en «XX»:".encode("utf-8") in err, (codigo, err)


def test_repo_relativa_repo_es_la_relativa():
    with Mundo() as w:
        escribir(w.web, "Core/A.cs", "x\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "y\n")
        c = reportado(w, ruta)
        assert c["relativa"] == c["relativa_repo"] == "Core/A.cs", c


def test_verificar_archivo_devuelve_hallazgos_ya_filtrados():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        escribir(w.web, "Core/A/B.cs", "uno\nx = MALO;\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A/B.cs", "uno\nx = MALO;\ny = MALO BLOQ;\n")
        config = w.config()
        r = M.verificar_archivo(ruta, config)
        assert r is not None and r[0] == "Core/A/B.cs", r
        assert [h["id"] for h in r[1]] == ["T-02"] and r[1][0]["modo"] == "bloqueo" and r[1][0]["linea"] == 3, r
        escribir(w.web, "Core/A/B.cs", "uno\nx = MALO; // y\n")
        assert M.verificar_archivo(ruta, config)[1] == []
        assert M.verificar_archivo(w.base / "otro" / "C.txt", config) is None
        assert M.verificar_archivo(w.web / "Core" / "A" / "NoExiste.cs", config) is None
        os.remove(w.raiz / ".claude" / "reglas" / "verificar_web.py")
        assert M.verificar_archivo(ruta, config) is None


def test_verificar_archivo_contra_otro_commit_ve_lo_commiteado_despues():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        escribir(w.web, "Core/A/B.cs", "uno\nx = MALO BLOQ;\n")
        commitear(w.web)
        viejo = git(w.web, "rev-parse", "HEAD")
        ruta = escribir(w.web, "Core/A/B.cs", "uno\nx = MALO BLOQ;\ny = MALO BLOQ;\n")
        nuevo = escribir(w.web, "Core/A/N.cs", "z = MALO BLOQ;\n")
        commitear(w.web, "despues")
        escribir(w.web, "Core/A/B.cs", "uno\nx = MALO BLOQ;\ny = MALO BLOQ;\nlimpia\n")
        config = w.config()
        assert M.verificar_archivo(ruta, config)[1] == [], "contra HEAD, lo commiteado ya no es nuevo"
        assert M.verificar_archivo(ruta, config, contra=None) == M.verificar_archivo(ruta, config)
        assert [h["linea"] for h in M.verificar_archivo(ruta, config, contra=viejo)[1]] == [3]
        w.modulo("web", STUB_CTX)
        c = json.loads(M.verificar_archivo(nuevo, config, contra=viejo)[1][0]["mensaje"].split("CTX ", 1)[1])
        assert c["es_nuevo"] is True and c["agregadas"] == [[1, "z = MALO BLOQ;"]], c


def test_post_tool_use_usa_la_funcion_publica_sin_cambiar_la_salida():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        escribir(w.web, "Core/A/B.cs", "uno\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A/B.cs", "uno\ny = MALO BLOQ;\n")
        c, o, e = w.correr(evento(ruta))
        assert c == 2 and o == "" and e.decode("utf-8").startswith("verificar-capa: Core/A/B.cs tiene 1 problema(s)"), (c, o, e)


def test_plazo_por_argumento():
    assert M.plazo_de([]) == 8
    assert M.plazo_de(["--plazo", "25"]) == 25
    assert M.plazo_de(["--plazo", "2.5"]) == 2.5
    for malo in (["--plazo"], ["--plazo", "x"], ["--plazo", "0"], ["--plazo", "-3"], ["--plazo", "nan"], ["--plazo", "inf"]):
        assert M.plazo_de(malo) == 8, malo


def _hooks_del_plugin():
    datos = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for evento_, grupos in datos["hooks"].items():
        for grupo in grupos:
            for h in grupo["hooks"]:
                yield evento_, grupo.get("matcher") or "", h


def test_cada_hook_del_plugin_tiene_plazo_menor_que_su_timeout():
    vistos = 0
    for evento_, matcher, h in _hooks_del_plugin():
        vistos += 1
        assert h.get("type") == "command" and isinstance(h.get("args"), list), h
        timeout = h.get("timeout")
        assert isinstance(timeout, (int, float)) and timeout > 0, h
        args = h["args"]
        plazo = M.plazo_de(args[1:])
        assert 0 < plazo <= timeout - 2, (evento_, matcher, plazo, timeout)
        script = args[0].replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
        assert args[0].startswith("${CLAUDE_PLUGIN_ROOT}/") and Path(script).is_file(), args[0]
    assert vistos >= 1


def test_el_dispatcher_esta_cableado_en_post_tool_use_edit_y_write_con_25_s():
    cableados = [(e, m, h) for e, m, h in _hooks_del_plugin() if h["args"][0].endswith("/scripts/verificar_capa.py")]
    post = [(m, h) for e, m, h in cableados if e == "PostToolUse" and "Edit" in m.split("|")]
    assert len(post) == 1, cableados
    matcher, h = post[0]
    assert set(matcher.split("|")) >= {"Edit", "Write"}, matcher
    assert 20 <= M.plazo_de(h["args"][1:]) <= 25 and h["timeout"] == 30, h


def test_el_dispatcher_le_pasa_al_modulo_el_deadline_y_a_git_lo_que_queda():
    stub = 'def verificar(ctx):\n    return [{"id": "T-09", "modo": "aviso", "severidad": "", "linea": None, "fragmento": None, "mensaje": "L=%r" % ctx.get("limite")}]\n'
    with Mundo() as w:
        w.modulo("web", stub)
        escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "uno\ndos\n")
        timeouts = []
        original = M.subprocess.run

        def espia(*a, **k):
            timeouts.append(k.get("timeout"))
            return original(*a, **k)

        antes = time.monotonic()
        with subprocess_falso(espia):
            codigo, out, err = w.correr(evento(ruta), plazo=25)
        limite = float(json.loads(out)["hookSpecificOutput"]["additionalContext"].split("L=", 1)[1].split()[0])
        assert 20 <= limite - antes <= 25.5, limite - antes
        assert timeouts and all(0 < t <= M.TIMEOUT_GIT for t in timeouts), timeouts
        w.correr(evento(ruta, nombre="PreToolUse"))
        assert M._LIMITE is None


def test_verificar_archivo_recibe_el_limite_explicito_y_no_lo_deja_colgado():
    stub = 'def verificar(ctx):\n    return [{"id": "T-09", "modo": "aviso", "severidad": "", "linea": None, "fragmento": None, "mensaje": "L=%r" % ctx.get("limite")}]\n'
    with Mundo() as w:
        w.modulo("web", stub)
        escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "uno\ndos\n")
        config = w.config()
        timeouts = []
        original = M.subprocess.run

        def espia(*a, **k):
            timeouts.append(k.get("timeout"))
            return original(*a, **k)

        limite = time.monotonic() + 3
        with subprocess_falso(espia):
            r = M.verificar_archivo(ruta, config, limite)
        assert r[1][0]["mensaje"] == "L=%r" % limite, r
        assert timeouts and all(0 < t <= 3 for t in timeouts), timeouts
        assert M._LIMITE is None
        assert M.verificar_archivo(ruta, config)[1][0]["mensaje"] == "L=None"
        try:
            M.verificar_archivo(ruta, config, time.monotonic() - 1)
            assert False, "sin tiempo no llega al modulo"
        except subprocess.TimeoutExpired:
            pass
        assert M._LIMITE is None


ARBOL_VACIO = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
CONFIG_GIT_RARA = ("[diff]\n\tnoprefix = true\n\tmnemonicPrefix = true\n\tsubmodule = log\n[core]\n\tquotepath = true\n"
                   "[diff \"mayus\"]\n\ttextconv = tr a-z A-Z <\n")


def _con_config_rara():
    with open(os.environ["GIT_CONFIG_GLOBAL"], "w", encoding="utf-8") as f:
        f.write(CONFIG_GIT_RARA)


def _contar_git():
    lanzados, original = [], M.subprocess.run

    def espia(*a, **k):
        lanzados.append(a)
        return original(*a, **k)

    return lanzados, subprocess_falso(espia)


def test_armar_ctx_con_lo_que_ya_sabe_el_triaje_no_lanza_git_y_arma_el_mismo_contexto():
    with git_aislado(), Mundo() as w:
        _con_config_rara()
        escribir(w.web, ".gitattributes", "Core/Mayus.cs diff=mayus\n")
        escribir(w.web, "Core/M.cs", "uno\ndos\ntres\n")
        escribir(w.web, "Core/Mayus.cs", "uno\n")
        commitear(w.web)
        base = git(w.web, "rev-parse", "HEAD")
        casos = [(escribir(w.web, "Core/M.cs", "uno\nDOS\ntres\ncuatro\n"), "Core/M.cs", False),
                 (escribir(w.web, "Core/Mayus.cs", "uno\ndos\n"), "Core/Mayus.cs", False),
                 (escribir(w.web, "Core/A.cs", "nuevo\n"), "Core/A.cs", True),
                 (escribir(w.web, "Core/S.cs", "suelto\n"), "Core/S.cs", True)]
        git(w.web, "add", "--", "Core/A.cs")
        config, raiz = w.config(), git(w.web, "rev-parse", "--show-toplevel")
        diffs = M.diffs_por_archivo(raiz, base)
        assert sorted(diffs) == ["Core/M.cs", "Core/Mayus.cs"], diffs
        for ruta, rel, es_nuevo in casos:
            esperado = M.armar_ctx(ruta, "web", "repo", config, contra=base)
            previo = {"raiz": raiz, "rel_git": rel, "es_nuevo": es_nuevo, "texto_diff": None if es_nuevo else diffs[rel]}
            with SinSubprocess():
                obtenido = M.armar_ctx(ruta, "web", "repo", config, contra=base, previo=previo)
            assert obtenido == esperado and esperado["es_nuevo"] is es_nuevo, (rel, obtenido, esperado)
            if rel == "Core/M.cs":
                assert esperado["agregadas"] == [(2, "DOS"), (4, "cuatro")], esperado
            if rel == "Core/Mayus.cs":
                assert esperado["agregadas"] == [(2, "DOS")], "control positivo: el textconv del hook: %s" % esperado
        w.modulo("web", STUB_MALO)
        ruta = escribir(w.web, "Core/M.cs", "uno\nx = MALO BLOQ;\n")
        previo = {"raiz": raiz, "rel_git": "Core/M.cs", "es_nuevo": False, "texto_diff": M.diffs_por_archivo(raiz, base)["Core/M.cs"]}
        esperado = M.verificar_archivo(ruta, config, contra=base)
        with SinSubprocess():
            assert M.verificar_archivo(ruta, config, contra=base, previo=previo) == esperado
        assert [h["linea"] for h in esperado[1]] == [2], esperado


def test_armar_ctx_no_usa_lo_previo_de_otro_archivo_ni_en_el_taller():
    with git_aislado(), Mundo(db={"src/ventas/Proc_A.sql": PROC}) as w:
        config = w.config()
        escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "uno\ndos\n")
        falso = {"raiz": git(w.web, "rev-parse", "--show-toplevel"), "rel_git": "Core/Otro.cs", "es_nuevo": False,
                 "texto_diff": "@@ -1 +1 @@\n+falso\n"}
        esperado = M.armar_ctx(ruta, "web", "repo", config)
        lanzados, espia = _contar_git()
        with espia:
            assert M.armar_ctx(ruta, "web", "repo", config, previo=falso) == esperado
        assert lanzados and esperado["agregadas"] == [(2, "dos")], (lanzados, esperado)
        taller = w.taller("esq.Proc_A.sql", PROC.replace("SELECT 1;", "SELECT 2;"))
        falso = {"raiz": git(w.raiz, "rev-parse", "--show-toplevel"), "rel_git": "tickets/T-1-x/SQL/esq.Proc_A.sql",
                 "es_nuevo": False, "texto_diff": "@@ -1 +1 @@\n+falso\n"}
        esperado = M.armar_ctx(taller, "sql", "taller", config, contra=ARBOL_VACIO)
        assert M.armar_ctx(taller, "sql", "taller", config, contra=ARBOL_VACIO, previo=falso) == esperado
        assert esperado["es_nuevo"] is False and esperado["agregadas"] == [(4, "\tSELECT 2;")], esperado


def test_los_diffs_por_archivo_son_los_de_cada_archivo_con_cualquier_config_de_git():
    with git_aislado(), Mundo() as w:
        _con_config_rara()
        raro = "Core/con espacio b/año [v2].cs"
        escribir(w.web, ".gitattributes", "Core/Mayus.cs diff=mayus\n")
        for rel, texto in (("Core/Uno.cs", "uno\ndos\n"), (raro, "a\n"), ("Core/Mayus.cs", "uno\n"), ("Core/Bin.cs", b"\x00uno\x00"),
                           ("Core/Borrado.cs", "x\n")):
            escribir(w.web, rel, texto)
        commitear(w.web)
        base = git(w.web, "rev-parse", "HEAD")
        for rel, texto in (("Core/Uno.cs", "UNO\ndos\ntres\n"), (raro, "a\nb\n"), ("Core/Mayus.cs", "uno\ndos\n"),
                           ("Core/Bin.cs", b"\x00dos\x00"), ("Core/Nuevo.cs", "n\n"), ("Core/Suelto.cs", "s\n")):
            escribir(w.web, rel, texto)
        git(w.web, "add", "--", "Core/Nuevo.cs")
        os.remove(w.web / "Core" / "Borrado.cs")
        diffs = M.diffs_por_archivo(str(w.web), base)
        modificados = ["Core/Bin.cs", "Core/Mayus.cs", "Core/Uno.cs", raro]
        assert sorted(diffs) == sorted(modificados), diffs
        for rel in modificados:
            uno = git(w.web, "diff", "-U0", "--no-color", "--no-ext-diff", base, "--", rel)
            assert M._hunks_del_diff(diffs[rel]) == M._hunks_del_diff(uno), (rel, diffs[rel], uno)
        assert M._hunks_del_diff(diffs[raro])[0]["agregadas"] == [(2, "b")], diffs[raro]
        assert "Binary files" in diffs["Core/Bin.cs"] and M._hunks_del_diff(diffs["Core/Mayus.cs"])[0]["agregadas"] == [(2, "DOS")]
        assert M.diffs_por_archivo(str(w.web), "no-existe") is None


def test_partir_el_diff_lee_las_rutas_con_comillas_y_rechaza_lo_que_no_entiende():
    crudo = (b'diff --git "a/x\\"y\\t\\303\\261.cs" "b/x\\"y\\t\\303\\261.cs"\n@@ -1 +1 @@\n-a\n+b\n'
             b"diff --git a/d b/e b/d b/e\nBinary files a/d b/e and b/d b/e differ\n")
    partes = M.partir_el_diff(crudo)
    assert partes == {'x"y\tñ.cs': crudo[:crudo.index(b"diff --git a/d")], "d b/e": crudo[crudo.index(b"diff --git a/d"):]}, partes
    assert M.partir_el_diff(b"") == {}
    for malo in (b"Submodule x 1..2:\n", b"diff --git a/x b/y\n", b'diff --git "a/x\\', b"diff --git a/x b/x\ndiff --git c/z d/z\n"):
        assert M.partir_el_diff(malo) is None, malo


def test_sin_tiempo_para_git_falla_abierto_sin_colgarse():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "uno\ndos MALO\n")
        assert w.correr(evento(ruta), plazo=-1) == (0, "", b"")
        assert w.correr(evento(ruta), plazo=25)[0] == 0 and "linea 2 en «MALO»:" in contexto(w.correr(evento(ruta), plazo=25)[1])


def test_la_raiz_sale_de_la_sesion_si_no_se_pasa():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/A.cs", "x MALO BLOQ\n")
        ticket = w.raiz / "tickets" / "T-1"
        ticket.mkdir(parents=True)
        previo = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(ticket)
        try:
            assert M.correr(evento(ruta), plazo=25)[0] == 2
        finally:
            if previo is None:
                del os.environ["CLAUDE_PROJECT_DIR"]
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = previo
        e = evento(ruta, cwd=str(ticket))
        assert M.correr(e, plazo=25)[0] == 2


REGLA = "- **%s-01** Abrir el molde antes de escribir → así, con 16 y 151."


def skill(capa, cuerpo=None):
    if cuerpo is None:
        cuerpo = "<!-- no-negociables -->\n%s\n<!-- /no-negociables -->\n" % (REGLA % capa.upper())
    return "---\nname: capa-%s\nuser-invocable: false\n---\nCENTINELA capa-%s 2026-10-25\n\n%s\nFUERA DEL BLOQUE\n" % (capa, capa, cuerpo)


class Toque(Mundo):
    def __init__(self, capas=("web", "sql"), writers=()):
        super().__init__()
        self.capas = capas
        self.writers = writers

    def __enter__(self):
        super().__enter__()
        for capa in self.capas:
            escribir(self.raiz, ".claude/skills/capa-%s/SKILL.md" % capa, skill(capa))
        for capa in self.writers:
            escribir(self.raiz, ".claude/agents/writer-%s.md" % capa, "---\nname: writer-%s\n---\n" % capa)
        self.sql = str(self.db / "src" / "Proc_X.sql")
        self.sql2 = str(self.db / "src" / "Proc_Y.sql")
        self.cs = str(self.web / "Core" / "A" / "B.cs")
        self.taller_sql = str(self.raiz / "tickets" / "T-1-x" / "SQL" / "esq.Proc_A.sql")
        return self

    def marcas(self):
        base = self.raiz / ".claude" / "estado" / "primer-toque"
        if not base.is_dir():
            return []
        return sorted(str(p.relative_to(base)).replace("\\", "/") for p in base.rglob("*") if p.is_file())

    def agente(self, nombre, frontmatter):
        escribir(self.raiz, ".claude/agents/%s.md" % nombre, frontmatter)


def leer(ruta, sesion="s1", agente=None):
    e = evento(ruta, "Read", session_id=sesion)
    if agente:
        e.update(agent_id=agente, agent_type="Explore")
    return e


def a_escribir(ruta, herramienta="Write", sesion="s1", agente=None):
    e = evento(ruta, herramienta, nombre="PreToolUse", session_id=sesion)
    if agente:
        e.update(agent_id=agente, agent_type="general-purpose")
    return e


def inicio(source, sesion="s1"):
    return {"hook_event_name": "SessionStart", "source": source, "session_id": sesion}


def contexto(out):
    try:
        datos = json.loads(out)
    except ValueError:
        return None
    hso = (datos or {}).get("hookSpecificOutput") or {}
    return hso.get("additionalContext") if hso.get("hookEventName") == "PostToolUse" else None


def test_primer_read_inyecta_una_vez_por_sesion_agente_y_capa():
    with Toque() as w:
        codigo, out, err = w.correr(leer(w.sql))
        texto = contexto(out)
        assert codigo == 0 and err == b"" and texto is not None, (codigo, out, err)
        assert (REGLA % "SQL") in texto and "FUERA DEL BLOQUE" not in texto and "CENTINELA" not in texto, texto
        assert ".claude/skills/capa-sql/SKILL.md" in texto, texto
        assert w.marcas() == ["s1/principal.sql"], w.marcas()
        assert w.correr(leer(w.sql)) == (0, "", b"")
        assert w.correr(leer(w.sql2)) == (0, "", b""), "otro archivo de la misma capa calla"
        assert (REGLA % "WEB") in contexto(w.correr(leer(w.cs))[1])
        assert (REGLA % "SQL") in contexto(w.correr(leer(w.sql, agente="a1b2"))[1]), "un subagente recibe su propia inyeccion"
        assert contexto(w.correr(leer(w.sql, sesion="s2"))[1]) is not None
        assert w.marcas() == ["s1/a1b2.sql", "s1/principal.sql", "s1/principal.web", "s2/principal.sql"], w.marcas()


def test_el_relleno_de_la_plantilla_no_cuenta_como_no_negociables():
    plantilla = (PLUGIN / "plantillas" / "capa.md").read_text(encoding="utf-8")
    generada = plantilla.replace("{{capa}}", "sql").replace("{{fecha}}", "2026-11-15")
    with Toque(capas=("sql",)) as w:
        for texto in (generada, generada.replace("\n", "\r\n")):
            escribir(w.raiz, ".claude/skills/capa-sql/SKILL.md", texto)
            assert w.correr(leer(w.sql)) == (0, "", b""), "un read no inyecta el relleno"
            assert w.correr(a_escribir(w.sql)) == (0, "", b""), "el primer edit no se bloquea por el relleno"
            assert w.correr(a_escribir(w.sql, "Edit")) == (0, "", b"")
            assert w.marcas() == [], w.marcas()
        con_regla = generada.replace("<!-- /no-negociables -->", "- NN-SQL-REAL nunca borrar la tabla de auditoria\n<!-- /no-negociables -->")
        escribir(w.raiz, ".claude/skills/capa-sql/SKILL.md", con_regla)
        texto = contexto(w.correr(leer(w.sql))[1])
        assert texto is not None and "NN-SQL-REAL" in texto, "un bloque que suma una regla al relleno sí se inyecta"
        assert w.marcas() == ["s1/principal.sql"], w.marcas()


def test_primer_toque_sin_subprocess_y_calla_fuera_de_las_capas():
    with Toque() as w:
        with SinSubprocess() as guardia:
            for i, (ruta, prefijo) in enumerate([(w.sql, "SQL"), (w.taller_sql, "SQL"), (w.cs, "WEB")]):
                assert (REGLA % prefijo) in contexto(w.correr(leer(ruta, sesion="r%d" % i))[1]), ruta
                codigo, out, err = w.correr(a_escribir(ruta, sesion="w%d" % i))
                assert codigo == 2 and (REGLA % prefijo).encode("utf-8") in err, (ruta, err)
            antes = w.marcas()
            for ruta in (str(w.raiz / "README.md"), str(w.raiz / "tickets" / "T-1-x" / "SQL" / "otro.Proc_A.sql"),
                         str(w.base / "otro" / "A.cs"), str(w.web / "build.gradle")):
                for e in (leer(ruta, sesion="z"), a_escribir(ruta, sesion="z"), a_escribir(ruta, "Edit", sesion="z")):
                    assert w.correr(e) == (0, "", b""), (e["hook_event_name"], ruta)
            assert w.marcas() == antes
        assert not guardia.llamadas, guardia.llamadas


def test_write_sin_inyeccion_previa_bloquea_una_sola_vez_en_bytes_utf8():
    with Toque() as w:
        codigo, out, err = w.correr(a_escribir(w.sql))
        assert codigo == 2 and out == "", (codigo, out)
        assert (REGLA % "SQL").encode("utf-8") in err, err
        assert b"reintent" in err and b"FUERA DEL BLOQUE" not in err, err
        assert w.marcas() == ["s1/principal.sql"], w.marcas()
        assert w.correr(a_escribir(w.sql)) == (0, "", b""), "el reintento pasa"
        assert w.correr(a_escribir(w.sql, "Edit")) == (0, "", b"")
        assert w.correr(leer(w.sql)) == (0, "", b"")
        w.correr(leer(w.cs))
        assert w.correr(a_escribir(w.cs, "Edit")) == (0, "", b"")
        codigo, _, err = w.correr(a_escribir(w.sql, "Edit", agente="a1"))
        assert codigo == 2 and (REGLA % "SQL").encode("utf-8") in err, err
        for herr in ("Bash", "Read", "MultiEdit", "NotebookEdit"):
            assert w.correr(a_escribir(w.sql, herr, sesion="s9")) == (0, "", b""), herr
        assert not any(m.startswith("s9/") for m in w.marcas()), w.marcas()


def test_un_agent_id_que_no_es_texto_no_cuenta_como_principal():
    with Toque() as w:
        for raro in (5, True, ["a1"], {"a": 1}):
            assert w.correr(dict(leer(w.sql), agent_id=raro)) == (0, "", b""), raro
        assert w.marcas() == [], w.marcas()
        for i, vacio in enumerate(("", None, 0)):
            assert contexto(w.correr(dict(leer(w.sql, sesion="v%d" % i), agent_id=vacio))[1]) is not None, vacio
        assert w.marcas() == ["v0/principal.sql", "v1/principal.sql", "v2/principal.sql"], w.marcas()


def test_sin_hook_event_name_calla_aunque_el_cambio_bloquee():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        assert w.correr(evento(ruta))[0] == 2, "control positivo: con PostToolUse bloquea"
        sin = {k: v for k, v in evento(ruta).items() if k != "hook_event_name"}
        assert w.correr(sin) == (0, "", b"")
        assert w.correr(json.dumps(sin).encode("utf-8")) == (0, "", b"")
    with Toque() as w:
        sin = {k: v for k, v in a_escribir(w.sql).items() if k != "hook_event_name"}
        assert w.correr(sin) == (0, "", b"") and w.marcas() == [], "a diferencia de los guards, no cuenta como PreToolUse"
        assert w.correr(a_escribir(w.sql))[0] == 2, "control positivo: con PreToolUse bloquea"


def test_compact_y_clear_resetean_solo_la_sesion_principal():
    with Toque() as w:
        for source in ("compact", "clear"):
            for e in (leer(w.sql), leer(w.cs), leer(w.sql, agente="a1"), leer(w.sql, sesion="s2")):
                w.correr(e)
            assert w.correr(inicio(source)) == (0, "", b""), source
            assert w.marcas() == ["s1/a1.sql", "s2/principal.sql"], (source, w.marcas())
            assert contexto(w.correr(leer(w.sql))[1]) is not None, source
        for source in ("startup", "resume", None):
            antes = w.marcas()
            assert w.correr(inicio(source)) == (0, "", b"") and w.marcas() == antes, source
        assert w.correr(inicio("compact", sesion="../s2")) == (0, "", b"") and "s2/principal.sql" in w.marcas()


def aviso_de(out):
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart", hso
    return hso["additionalContext"]


def entorno_de_sesion(raiz):
    return dict(_entorno_sin_git(), CLAUDE_PROJECT_DIR=str(raiz))


def test_inicio_con_la_config_rota_avisa_en_startup_y_resume_con_un_aviso_corto():
    with Mundo() as w:
        casos = {"{rota": "workspace.config.json", '{"schema_version": 9, "layers": {}}': "schema_version"}
        for contenido, rastro in casos.items():
            escribir(w.raiz, "workspace.config.json", contenido)
            for source in ("startup", "resume"):
                codigo, out, err = w.correr(inicio(source))
                texto = aviso_de(out)
                assert codigo == 0 and err == b"", (source, codigo, err)
                assert "/odd-ws:doctor" in texto and rastro in texto, (source, texto)
                assert "\n" not in texto and len(texto) <= 400, (source, len(texto), texto)
        sin_sesion = {"hook_event_name": "SessionStart", "source": "startup"}
        assert "/odd-ws:doctor" in aviso_de(w.correr(sin_sesion)[1]), "el aviso no depende del session_id"


def test_inicio_con_la_ruta_local_de_un_repo_que_falta_o_no_existe_avisa():
    with Mundo() as w:
        escribir(w.raiz, "workspace.local.json", json.dumps({"repos": {"web": {"path": str(w.web)}}}))
        for source in ("startup", "resume"):
            texto = aviso_de(w.correr(inicio(source))[1])
            assert "db" in texto and "workspace.local.json" in texto and "/odd-ws:doctor" in texto, texto
        ausente = str(w.base / "no-existe")
        escribir(w.raiz, "workspace.local.json", json.dumps({"repos": {"web": {"path": str(w.web)}, "db": {"path": ausente}}}))
        assert ausente in aviso_de(w.correr(inicio("startup"))[1])
        os.remove(w.raiz / "workspace.local.json")
        assert "falta la ruta" in aviso_de(w.correr(inicio("resume"))[1])


def test_el_aviso_queda_en_una_linea_y_corto_aunque_el_motivo_sea_largo_y_traiga_saltos():
    with Mundo() as w:
        larga = "x\n" + "y" * 600
        escribir(w.raiz, "workspace.local.json", json.dumps({"repos": {"web": {"path": str(w.web)}, "db": {"path": larga}}}))
        texto = aviso_de(w.correr(inicio("startup"))[1])
        assert "\n" not in texto and len(texto) <= 400 and "yyyy" in texto and "/odd-ws:doctor" in texto, (len(texto), texto)


def test_inicio_con_la_config_sana_calla_en_startup_y_resume_y_no_deja_marcas():
    with Toque() as w:
        for source in ("startup", "resume"):
            assert w.correr(inicio(source)) == (0, "", b""), source
        assert w.marcas() == []
        escribir(w.raiz, "workspace.config.json", "{rota")
        assert w.correr(inicio("startup"))[1], "control positivo: rota avisa"


def inicio_en(source, cwd, sesion="s1"):
    return {"hook_event_name": "SessionStart", "source": source, "session_id": sesion, "cwd": str(cwd)}


def marcar_activo(raiz, relativa):
    escribir(raiz, ".claude/estado/ticket-activo", relativa + "\n")


TICKET_ACTIVO = "# T-7 — algo\n\n## Objetivo\n\nhacer algo concreto\n"


def test_inicio_en_la_raiz_inyecta_el_ticket_activo_en_cada_origen():
    with Toque() as w:
        escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", TICKET_ACTIVO)
        marcar_activo(w.raiz, "tickets/T-7-algo")
        for source in ("startup", "resume", "compact", "clear"):
            codigo, out, err = w.correr(inicio_en(source, w.raiz))
            assert codigo == 0 and err == b"", (source, codigo, err)
            texto = aviso_de(out)
            assert "tickets/T-7-algo" in texto and "## Objetivo" in texto and "hacer algo concreto" in texto, (source, texto)
        assert w.marcas() == []


def test_inicio_fuera_de_la_raiz_sin_cwd_o_sin_ticket_activo_valido_calla():
    with Toque() as w:
        escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", TICKET_ACTIVO)
        assert w.correr(inicio_en("startup", w.raiz)) == (0, "", b""), "sin marca"
        marcar_activo(w.raiz, "tickets/T-7-algo")
        assert w.correr(inicio_en("startup", w.raiz / "tickets" / "T-7-algo")) == (0, "", b""), "dentro del ticket ya carga solo"
        assert w.correr(inicio("startup")) == (0, "", b""), "sin cwd"
        for malo in ("tickets/T-9-no-existe", "../afuera", "tickets/../../afuera", "/abs", "workspace.config.json", "tickets", ""):
            marcar_activo(w.raiz, malo)
            assert w.correr(inicio_en("startup", w.raiz)) == (0, "", b""), malo
        marcar_activo(w.raiz, "tickets/T-7-algo")
        assert "hacer algo concreto" in aviso_de(w.correr(inicio_en("startup", w.raiz))[1]), "control positivo"


@contextlib.contextmanager
def plugin_actualizado(raiz):
    base = Path(tempfile.mkdtemp(prefix="odd-plugin-actualizado-"))
    vieja, vigente = (base / "odd-ws" / "0.13.1", base / "odd-ws" / "0.13.2")
    for carpeta in (vieja, vigente):
        (carpeta / "scripts").mkdir(parents=True)
        (carpeta / "scripts" / "reglas.py").write_text("", encoding="utf-8")
    local = Path(raiz) / "workspace.local.json"
    datos = json.loads(local.read_text(encoding="utf-8"))
    local.write_text(json.dumps({**datos, "plugin_root": str(vieja)}), encoding="utf-8")
    original = M.raiz_del_plugin.vigente
    M.raiz_del_plugin.vigente = lambda: vigente
    try:
        yield local, datos, vieja, vigente
    finally:
        M.raiz_del_plugin.vigente = original
        shutil.rmtree(base, ignore_errors=True)


def test_al_iniciar_la_sesion_plugin_root_sigue_a_la_version_vigente_y_lo_dice():
    with Toque() as w, plugin_actualizado(w.raiz) as (local, datos, vieja, vigente):
        codigo, out, err = w.correr(inicio_en("startup", w.raiz))
        assert codigo == 0 and err == b"", (codigo, err)
        texto = aviso_de(out)
        assert "0.13.1" in texto and "0.13.2" in texto and "pre-commit" in texto, texto
        assert json.loads(local.read_text(encoding="utf-8")) == {**datos, "plugin_root": str(vigente)}
        assert w.correr(inicio_en("startup", w.raiz)) == (0, "", b""), "la segunda sesión ya no cambia nada"


def test_al_iniciar_la_sesion_el_aviso_de_plugin_root_va_junto_al_ticket_activo():
    with Toque() as w, plugin_actualizado(w.raiz) as (local, datos, vieja, vigente):
        escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", TICKET_ACTIVO)
        marcar_activo(w.raiz, "tickets/T-7-algo")
        texto = aviso_de(w.correr(inicio_en("resume", w.raiz))[1])
        assert "0.13.2" in texto and "hacer algo concreto" in texto, texto
        assert texto.index("0.13.2") < texto.index("hacer algo concreto"), texto


PLANTILLAS_DEL_SALTO = {"CLAUDE.md": ("# {{nombre}} — guía de trabajo\n\nRaíz de **{{nombre}}**, con `{{tickets}}/`.\n",) * 2,
                        "ticket.md": ("# ticket\n",) * 2, "pre-commit": ("#!/bin/sh\necho 1\n", "#!/bin/sh\necho 2\n"),
                        "reglas/verificar.tests.py": ("print(1)\n", "print(2)\n")}


def huella_del_salto(texto):
    import hashlib
    return "sha256:" + hashlib.sha256(texto.replace("{{tickets}}", "tickets").encode("utf-8")).hexdigest()


def con_plantillas_del_salto(raiz, vigente, copiadas):
    escribir(vigente, ".claude-plugin/plugin.json", json.dumps({"name": "odd-ws", "version": "0.13.2"}))
    for plantilla, (vieja, nueva) in PLANTILLAS_DEL_SALTO.items():
        escribir(vigente, "plantillas/" + plantilla, nueva)
    escribir(vigente, "plantillas/huellas.json", json.dumps({p: {"0.13.1": huella_del_salto(v), "0.13.2": huella_del_salto(n)}
                                                             for p, (v, n) in PLANTILLAS_DEL_SALTO.items()}))
    config = json.loads((Path(raiz) / "workspace.config.json").read_text(encoding="utf-8"))
    escribir(raiz, "workspace.config.json", json.dumps({**config, "plantillas": "0.13.1"}))
    cual = 0 if copiadas == "viejas" else 1
    escribir(raiz, "CLAUDE.md", PLANTILLAS_DEL_SALTO["CLAUDE.md"][cual].replace("{{tickets}}", "tickets").replace("{{nombre}}", "Toque"))
    escribir(raiz, "tickets/_plantilla/CLAUDE.md", PLANTILLAS_DEL_SALTO["ticket.md"][cual])
    escribir(raiz, ".githooks/pre-commit", PLANTILLAS_DEL_SALTO["pre-commit"][cual])
    for capa in config["layers"]:
        escribir(raiz, ".claude/reglas/verificar_%s.tests.py" % capa, PLANTILLAS_DEL_SALTO["reglas/verificar.tests.py"][cual])
    return sorted(config["layers"])


def test_tras_el_salto_de_version_el_inicio_nombra_las_plantillas_copiadas_que_cambiaron_y_manda_al_doctor():
    with Toque() as w, plugin_actualizado(w.raiz) as (local, datos, vieja, vigente):
        capas = con_plantillas_del_salto(w.raiz, vigente, "viejas")
        escribir(w.raiz, ".claude/reglas/verificar_%s.tests.py" % capas[0], "editada a mano\n")
        texto = aviso_de(w.correr(inicio_en("startup", w.raiz))[1])
        linea = next(l for l in texto.split("\n\n") if "cambiaron plantillas" in l)
        cambiaron = [".githooks/pre-commit"] + [".claude/reglas/verificar_%s.tests.py" % capa for capa in capas]
        assert all(ruta in linea for ruta in cambiaron) and "CLAUDE.md" not in linea, linea
        assert "\n" not in linea and "/odd-ws:doctor" in linea and "ítem plantillas" in linea and "0.13.2" in linea, linea
        assert texto.index("apuntaba a la versión 0.13.1") < texto.index(linea), texto
        assert w.correr(inicio_en("startup", w.raiz)) == (0, "", b""), "sin salto no lo repite, aunque las copias sigan viejas"


def test_tras_el_salto_de_version_con_las_copias_al_dia_el_inicio_no_suma_la_linea_de_plantillas():
    with Toque() as w, plugin_actualizado(w.raiz) as (local, datos, vieja, vigente):
        con_plantillas_del_salto(w.raiz, vigente, "nuevas")
        texto = aviso_de(w.correr(inicio_en("startup", w.raiz))[1])
        assert "0.13.2" in texto and "plantillas" not in texto, texto


def test_con_verificar_capa_apagado_plugin_root_no_cambia():
    with Toque() as w, plugin_actualizado(w.raiz) as (local, datos, vieja, vigente):
        config = json.loads((w.raiz / "workspace.config.json").read_text(encoding="utf-8"))
        escribir(w.raiz, "workspace.config.json", json.dumps({**config, "disabled_hooks": ["verificar_capa"]}))
        antes = local.read_bytes()
        assert w.correr(inicio_en("startup", w.raiz)) == (0, "", b"")
        assert local.read_bytes() == antes


def test_el_ticket_activo_largo_se_recorta_y_dice_donde_sigue():
    with Toque() as w:
        escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", "# T-7\n" + "linea larga del ticket\n" * 2000)
        marcar_activo(w.raiz, "tickets/T-7-algo")
        texto = aviso_de(w.correr(inicio_en("startup", w.raiz))[1])
        assert len(texto) <= M.TOPE_DEL_TICKET + 500, len(texto)
        assert texto.rstrip().endswith("tickets/T-7-algo/CLAUDE.md"), texto[-200:]


def ticket_largo(seguimientos=True):
    relleno = "".join("- detalle del contexto técnico %03d, que ocupa lugar y no va al resumen\n" % i for i in range(150))
    tareas = "".join("| T%02d | S1 | tarea %02d del ticket | en la sesión | hecho | `abc%04d` |\n" % (i, i, i) for i in range(1, 30))
    bitacora = "".join("- 2026-11-%02d — ENTRADA-%02d\n  - detalle-%02d\n" % (i, i, i) for i in range(1, 9))
    return ("# T-7 — algo largo\n\n"
            "> **Contexto y metodología:** ver `../../CLAUDE.md` (la raíz de la instancia).\n"
            "> Un ticket se abre con `/odd-ws:abrir`.\n\n"
            "- **Estado:** en progreso\n- **Conocimiento:** pendiente\n\n"
            "> **Los dos campos miden relojes distintos, a propósito.** CITA-DEL-MOLDE\n\n"
            "## Objetivo\n\nOBJETIVO-DEL-TICKET\n\n"
            "## Criterios de aceptación\n\n- [ ] CUERPO-CRITERIOS\n\n"
            "## Alcance y no-goals\n\n- **Incluye:** CUERPO-ALCANCE\n\n"
            "## Contexto técnico\n\n" + relleno + "\n"
            "## Specs\n\n- S1: «SPEC-UNO»\n- S2: «SPEC-DOS»\n\n"
            "## Tareas\n\n| ID | Specs | Qué | Ruta | Estado | Commit |\n|---|---|---|---|---|---|\n" + tareas +
            "| T30 | S2 | FILA-FINAL | con un writer | pendiente | |\n\n" +
            ("## Seguimientos\n\n- SEGUIMIENTO-UNO → T31\n\n" if seguimientos else "") +
            "## Decisiones\n\n- CUERPO-DECISIONES\n\n"
            "## Gotchas\n\n- CUERPO-GOTCHAS\n\n"
            "## Bitácora\n\nHace de Log de ODD: INTRO-BITACORA\n\n" + bitacora +
            "- 2026-11-09 — ENTRADA-09\n  - detalle-09\n    - sub-detalle-09\n\n"
            "## Candidatos a graduar\n\n- CUERPO-CANDIDATOS\n\n"
            "## Cierre\n\nCUERPO-CIERRE\n")


def resumen_del_ticket(w, texto):
    escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", texto)
    marcar_activo(w.raiz, "tickets/T-7-algo")
    codigo, out, err = w.correr(inicio_en("startup", w.raiz))
    assert codigo == 0 and err == b"", (codigo, err)
    return aviso_de(out)


def test_el_ticket_activo_largo_inyecta_un_resumen_con_las_tareas_enteras_y_la_bitacora_reciente():
    with Toque() as w:
        ticket = ticket_largo()
        assert len(ticket) > M.TOPE_DEL_TICKET and ticket.index("## Tareas") > 10000, (len(ticket), ticket.index("## Tareas"))
        texto = resumen_del_ticket(w, ticket)
        for presente in ("# T-7 — algo largo", "- **Estado:** en progreso", "- **Conocimiento:** pendiente", "## Objetivo",
                         "OBJETIVO-DEL-TICKET", "## Specs", "SPEC-UNO", "SPEC-DOS", "## Tareas", "| ID | Specs |", "FILA-FINAL",
                         "## Seguimientos", "SEGUIMIENTO-UNO", "## Bitácora", "Las últimas 5 de 9 entradas.", "sub-detalle-09"):
            assert presente in texto, (presente, texto)
        for i in range(1, 30):
            assert "| T%02d | S1 | tarea %02d del ticket |" % (i, i) in texto, (i, texto)
        for i in range(5, 10):
            assert "ENTRADA-%02d" % i in texto and "  - detalle-%02d" % i in texto, (i, texto)
        for ausente in ["ENTRADA-%02d" % i for i in range(1, 5)] + ["detalle-%02d" % i for i in range(1, 5)] + [
                "CITA-DEL-MOLDE", "Contexto y metodología", "CUERPO-CRITERIOS", "CUERPO-ALCANCE", "detalle del contexto técnico",
                "CUERPO-DECISIONES", "CUERPO-GOTCHAS", "INTRO-BITACORA", "CUERPO-CANDIDATOS", "CUERPO-CIERRE", "## Decisiones",
                "## Gotchas", "## Candidatos a graduar", "[...] el resto sigue en"]:
            assert ausente not in texto, (ausente, texto)
        orden = [texto.index(marca) for marca in ("# T-7 — algo largo", "OBJETIVO-DEL-TICKET", "SPEC-UNO", "| T01 |", "FILA-FINAL",
                                                  "SEGUIMIENTO-UNO", "ENTRADA-05", "ENTRADA-09")]
        assert orden == sorted(orden), orden
        cierre = texto.rstrip().rsplit("\n", 1)[1]
        assert cierre.endswith("tickets/T-7-algo/CLAUDE.md"), cierre
        for parte in ("alcance", "criterios", "decisiones", "gotchas", "candidatos", "archivo completo"):
            assert parte in cierre, (parte, cierre)
        assert len(texto) <= M.TOPE_DEL_TICKET, len(texto)


def test_el_resumen_sin_seguimientos_no_los_pide():
    with Toque() as w:
        texto = resumen_del_ticket(w, ticket_largo(seguimientos=False))
        assert "Seguimientos" not in texto and "SEGUIMIENTO-UNO" not in texto, texto
        assert "FILA-FINAL" in texto and "ENTRADA-09" in texto and texto.index("FILA-FINAL") < texto.index("## Bitácora"), texto
        assert texto.rstrip().endswith("tickets/T-7-algo/CLAUDE.md"), texto[-200:]


def test_un_ticket_sin_secciones_inyecta_su_cabecera_sin_las_citas_del_molde():
    with Toque() as w:
        texto = resumen_del_ticket(w, "# T-7 — algo\n\n> cita del molde\n> otra cita\n\nSolo texto suelto del ticket.\n\n\n\nY otra línea.\n")
        assert "# T-7 — algo\n\nSolo texto suelto del ticket.\n\nY otra línea." in texto, texto
        assert "cita del molde" not in texto and "otra cita" not in texto, texto
        assert texto.rstrip().endswith("tickets/T-7-algo/CLAUDE.md") and "[...]" not in texto, texto


def test_las_secciones_del_resumen_se_reconocen_por_su_titulo_exacto():
    with Toque() as w:
        texto = resumen_del_ticket(w, "# T-7\n\n## Objetivo   \n\nOBJ-CON-ESPACIOS\n\n## Objetivos\n\nCUERPO-OBJETIVOS\n\n"
                                      "## Tareas viejas\n\nCUERPO-TAREAS-VIEJAS\n\n## Tareas \n\nTAREAS-CON-ESPACIO\n\n"
                                      "## Notas\n\n### Specs\n\nCUERPO-SUBSECCION\n\n##Specs\n\nSIN-ESPACIO\n\n"
                                      "## Bitácora\n\n- E-UNO\n\n- E-DOS\n  sigue E-DOS\n")
        for presente in ("## Objetivo\n\nOBJ-CON-ESPACIOS", "## Tareas\n\nTAREAS-CON-ESPACIO", "- E-UNO", "- E-DOS\n  sigue E-DOS"):
            assert presente in texto, (presente, texto)
        for ausente in ("CUERPO-OBJETIVOS", "CUERPO-TAREAS-VIEJAS", "Tareas viejas", "CUERPO-SUBSECCION", "SIN-ESPACIO", "Las últimas"):
            assert ausente not in texto, (ausente, texto)


def test_un_titulo_dentro_de_un_bloque_de_codigo_no_corta_la_seccion():
    with Toque() as w:
        texto = resumen_del_ticket(w, "# T-7\n\n## Specs\n\n- S1: «el pedido»\n\n```markdown\n## Decisiones\nDENTRO-DEL-BLOQUE\n```\n\n"
                                      "FIN-DE-SPECS\n\n## Decisiones\n\nCUERPO-DECISIONES\n")
        assert "DENTRO-DEL-BLOQUE" in texto and "FIN-DE-SPECS" in texto and "CUERPO-DECISIONES" not in texto, texto


def test_un_resumen_que_pasa_el_tope_se_recorta_y_dice_donde_sigue():
    with Toque() as w:
        filas = "".join("| T%03d | S1 | una tarea con bastante texto para ocupar lugar | en la sesión | hecho | |\n" % i for i in range(300))
        texto = resumen_del_ticket(w, "# T-7\n\n## Objetivo\n\nOBJETIVO-DEL-TICKET\n\n## Tareas\n\n" + filas +
                                      "\n## Bitácora\n\n- ENTRADA-FINAL\n")
        assert "OBJETIVO-DEL-TICKET" in texto and "ENTRADA-FINAL" not in texto, texto[-300:]
        assert len(texto) <= M.TOPE_DEL_TICKET + 500, len(texto)
        assert texto.rstrip().endswith("[...] el resto sigue en tickets/T-7-algo/CLAUDE.md"), texto[-200:]


ENCABEZADO_DEL_RESUMEN = ("odd-ws: el ticket activo de esta instancia es tickets/T-7-algo. La sesión corre en la raíz, así que Claude Code no "
                          "carga su CLAUDE.md solo; este es su resumen, de tickets/T-7-algo/CLAUDE.md:\n\n")
CIERRE_DEL_TICKET = ("El resto (alcance, criterios de aceptación, contexto técnico, decisiones, gotchas y candidatos) está en el archivo "
                     "completo: tickets/T-7-algo/CLAUDE.md")
ENLACES_A_DEPURAR = "Enlaces del ticket rotos o no portables (una ruta de la máquina se rompe en el clon de otra persona):\n"
LISTA_DE_ENLACES = "La lista completa sale con `ticket.py --enlaces tickets/T-7-algo/CLAUDE.md`."
FILAS_LARGAS = "".join("| T%03d | S1 | una tarea con bastante texto para ocupar lugar | en la sesión | hecho | |\n" % i for i in range(300))
MARCA_UNC = "servidor-que-no-se-toca"


def enlaces_a_depurar(*lineas):
    return "\n\n" + ENLACES_A_DEPURAR + "".join(linea + "\n" for linea in lineas) + LISTA_DE_ENLACES


def test_un_ticket_con_enlaces_sanos_inyecta_el_mismo_resumen_que_antes():
    with Toque() as w:
        for rel in ("notas/guía.md", "con espacios/a.md", "i.png"):
            escribir(w.raiz, "tickets/T-7-algo/" + rel, "x\n")
        objetivo = "Ver [la guía](notas/guía.md#uso), [notas](notas/), [la web](https://x.org/a#b), [arriba](#objetivo) y ![img](i.png)."
        texto = resumen_del_ticket(w, "# T-7 — algo\n\n## Objetivo\n\n%s\n\n## Decisiones\n\n- [espacios](<con espacios/a.md>)\n" % objetivo)
        assert texto == "%s# T-7 — algo\n\n## Objetivo\n\n%s\n\n%s" % (ENCABEZADO_DEL_RESUMEN, objetivo, CIERRE_DEL_TICKET), texto


def test_un_ticket_largo_con_enlaces_sanos_se_recorta_como_antes():
    with Toque() as w:
        escribir(w.raiz, "tickets/T-7-algo/actas/acta.md", "x\n")
        texto = resumen_del_ticket(w, "# T-7\n\n## Objetivo\n\nVer [el acta](actas/acta.md).\n\n## Tareas\n\n" + FILAS_LARGAS +
                                      "\n## Bitácora\n\n- ENTRADA-FINAL\n")
        assert texto.endswith("\n\n[...] el resto sigue en tickets/T-7-algo/CLAUDE.md"), texto[-300:]
        assert "Enlaces del ticket" not in texto and "ENTRADA-FINAL" not in texto, texto[-300:]
        assert len(texto) <= M.TOPE_DEL_TICKET + 500, len(texto)


def test_el_resumen_termina_con_los_enlaces_rotos_del_ticket():
    with Toque() as w:
        escribir(w.raiz, "tickets/T-7-algo/notas/guía.md", "x\n")
        texto = resumen_del_ticket(w, "# T-7\n\n## Objetivo\n\nVer [la guía](notas/guía.md).\n\n## Decisiones\n\n"
                                      "- [el diseño](diseño.md#parte), [web](https://x.org/nada) y [la carpeta](<sin carpeta/>)\n")
        assert texto.endswith(CIERRE_DEL_TICKET + enlaces_a_depurar("- no existe: el diseño -> diseño.md",
                                                                     "- no existe: la carpeta -> sin carpeta/")), texto[-500:]
        assert "la guía ->" not in texto and "web ->" not in texto, texto[-500:]


def test_el_resumen_marca_las_rutas_de_la_maquina_aunque_existan():
    with Toque() as w:
        real = (w.raiz / "README.md").as_posix()
        texto = resumen_del_ticket(w, "# T-7\n\n## Notas\n\n[existe](<%s>) [unidad](C:\\Users\\yo\\d.md) [raíz](/home/yo/x.md) "
                                      "[casa](~/x.md)\n" % real)
        assert texto.endswith(CIERRE_DEL_TICKET + enlaces_a_depurar(
            "- ruta de la máquina: existe -> " + real, "- ruta de la máquina: unidad -> C:\\Users\\yo\\d.md",
            "- ruta de la máquina: raíz -> /home/yo/x.md", "- ruta de la máquina: casa -> ~/x.md")), texto[-500:]


def test_el_resumen_trata_como_relativo_un_destino_con_virgulilla_sin_barra():
    with Toque() as w:
        escribir(w.raiz, "tickets/T-7-algo/~notas.md", "x\n")
        texto = resumen_del_ticket(w, "# T-7\n\n## Notas\n\n[nota](~notas.md) [falta](~falta.md) [casa](~/x.md) [sola](~)\n")
        assert texto.endswith(CIERRE_DEL_TICKET + enlaces_a_depurar(
            "- no existe: falta -> ~falta.md", "- ruta de la máquina: casa -> ~/x.md", "- ruta de la máquina: sola -> ~")), texto[-500:]
        assert "nota ->" not in texto, texto[-500:]


def test_el_resumen_lista_rotos_y_rutas_de_la_maquina_en_el_orden_del_ticket():
    with Toque() as w:
        texto = resumen_del_ticket(w, "# T-7\n\n## Objetivo\n\n[falta](nada.md)\n\n## Gotchas\n\n- [unidad](D:/x.md)\n- [otra](otra/nada/)\n")
        assert texto.endswith(CIERRE_DEL_TICKET + enlaces_a_depurar(
            "- no existe: falta -> nada.md", "- ruta de la máquina: unidad -> D:/x.md", "- no existe: otra -> otra/nada/")), texto[-500:]


def test_los_enlaces_a_depurar_se_cortan_en_pocas_lineas():
    with Toque() as w:
        largo = "x" * 300
        rotos = "".join("- [f%d](falta-%d.md)\n" % (i, i) for i in range(1, 8))
        texto = resumen_del_ticket(w, "# T-7\n\n## Bitácora\n\n- [%s](<%s.md>)\n%s" % (largo, largo, rotos))
        recortado = "x" * 120 + "..."
        assert texto.endswith(CIERRE_DEL_TICKET + enlaces_a_depurar(
            "- no existe: %s -> %s" % (recortado, recortado), "- no existe: f1 -> falta-1.md", "- no existe: f2 -> falta-2.md",
            "- no existe: f3 -> falta-3.md", "- no existe: f4 -> falta-4.md", "- y 3 más")), texto[-800:]


def test_los_enlaces_a_depurar_sobreviven_al_recorte_del_resumen():
    with Toque() as w:
        texto = resumen_del_ticket(w, "# T-7\n\n## Objetivo\n\nOBJETIVO-DEL-TICKET\n\n## Tareas\n\n" + FILAS_LARGAS +
                                      "\n## Bitácora\n\n- ENTRADA-FINAL con [el acta](actas/2026-11-01.md)\n")
        assert "ENTRADA-FINAL" not in texto, texto[-500:]
        assert texto.endswith("\n\n[...] el resto sigue en tickets/T-7-algo/CLAUDE.md" +
                              enlaces_a_depurar("- no existe: el acta -> actas/2026-11-01.md")), texto[-500:]
        assert len(texto) <= M.TOPE_DEL_TICKET + 1000, len(texto)


@contextlib.contextmanager
def sin_tocar(marca):
    tocados = []
    objetivos = [(os, "stat"), (os, "lstat"), (os, "scandir"), (os, "listdir"), (os.path, "exists"), (os.path, "lexists"),
                 (os.path, "isdir"), (os.path, "isfile"), (os.path, "realpath"), (Path, "exists"), (Path, "is_dir"),
                 (Path, "is_file"), (Path, "resolve"), (Path, "stat")]
    originales = [(dueno, nombre, getattr(dueno, nombre)) for dueno, nombre in objetivos]

    def envolver(nombre, original):
        def envuelta(*args, **kwargs):
            if any(marca in str(arg) for arg in args):
                tocados.append((nombre, str(args[0])))
                raise OSError("tocó " + marca)
            return original(*args, **kwargs)
        return envuelta

    for dueno, nombre, original in originales:
        setattr(dueno, nombre, envolver(nombre, original))
    try:
        yield tocados
    finally:
        for dueno, nombre, original in originales:
            setattr(dueno, nombre, original)


def test_una_ruta_unc_se_marca_sin_tocar_el_disco_ni_la_red():
    from odd_ws import enlaces
    with Toque() as w:
        unc = "\\\\%s\\recurso\\x.md" % MARCA_UNC
        unc_con_barras = "//%s/recurso/y.md" % MARCA_UNC
        ticket = "# T-7\n\n## Notas\n\n[unc](%s) [unc2](%s)\n" % (unc, unc_con_barras)
        with sin_tocar(MARCA_UNC) as tocados:
            texto = resumen_del_ticket(w, ticket)
            del_hook = list(tocados)
            list(enlaces.enlaces(ticket, w.raiz / "tickets" / "T-7-algo"))
        assert del_hook == [], del_hook
        assert tocados, "control positivo: enlaces() sí toca esas rutas, y el instrumento lo ve"
        assert texto.endswith(CIERRE_DEL_TICKET + enlaces_a_depurar(
            "- ruta de la máquina: unc -> " + unc, "- ruta de la máquina: unc2 -> " + unc_con_barras)), texto[-500:]


def test_si_revisar_los_enlaces_falla_el_resumen_sale_igual_que_antes():
    with Toque() as w:
        original = M.enlaces.revisar

        def rota(*_):
            yield M.enlaces.Revisado("falta", "nada.md", M.enlaces.NO_EXISTE)
            raise RuntimeError("rota")

        M.enlaces.revisar = rota
        try:
            texto = resumen_del_ticket(w, "# T-7 — algo\n\n## Objetivo\n\n[falta](nada.md)\n")
        finally:
            M.enlaces.revisar = original
        assert texto == "%s# T-7 — algo\n\n## Objetivo\n\n[falta](nada.md)\n\n%s" % (ENCABEZADO_DEL_RESUMEN, CIERRE_DEL_TICKET), texto


def test_sin_plazo_los_enlaces_dejan_de_revisarse_y_el_resumen_sale():
    with Toque() as w:
        escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", "# T-7\n\n## Objetivo\n\n[a](falta-a.md) [b](falta-b.md) [c](C:/x.md)\n")
        marcar_activo(w.raiz, "tickets/T-7-algo")
        codigo, out, err = w.correr(inicio_en("startup", w.raiz), plazo=-1)
        assert codigo == 0 and err == b"", (codigo, err)
        texto = aviso_de(out)
        assert texto.endswith(CIERRE_DEL_TICKET + enlaces_a_depurar("- no existe: a -> falta-a.md")), texto[-500:]


ENCABEZADO_DE_ENTREGAS = "odd-ws: hay trabajo de los tickets que todavía no llegó a origin (mirado con las refs locales, sin fetch):\n"
CIERRE_DE_ENTREGAS = ("\nCuéntaselo al usuario. Si ya llegó por otro camino o no va a subirse, con su sí corre "
                      "`entregas.py --confirmar <ticket>`: ese ticket calla hasta que cambien sus ramas o sus archivos.")
T7_SIN_EMPUJAR = "- T-7-algo: en web, la rama feat/T-7 nunca se empujó."


def entregas_pendientes(*lineas):
    return ENCABEZADO_DE_ENTREGAS + "\n".join(lineas) + CIERRE_DE_ENTREGAS


def con_origin(repo):
    escribir(repo, "base.txt", "base\n")
    commitear(repo, "base")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def ticket_con_rama(raiz, nombre, worktree_y_rama):
    escribir(raiz, "tickets/%s/CLAUDE.md" % nombre, "# %s\n\n## Objetivo\n\nhacer algo concreto\n\n## Contexto técnico\n\n"
             "- Worktree y rama: %s\n" % (nombre, worktree_y_rama))


def confirmar_entrega(raiz, ticket):
    import entregas
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return entregas.main(["--raiz", str(raiz), "--confirmar", ticket])


def test_inicio_avisa_de_cada_ticket_con_la_entrega_pendiente_en_startup_resume_y_fork():
    with git_aislado(), Toque() as w:
        con_origin(w.web)
        git(w.web, "branch", "feat/T-7")
        ticket_con_rama(w.raiz, "T-7-algo", "árbol principal, rama `feat/T-7`")
        for source in ("startup", "resume", "fork"):
            codigo, out, err = w.correr(inicio(source))
            assert codigo == 0 and err == b"", (source, codigo, err)
            assert aviso_de(out) == entregas_pendientes(T7_SIN_EMPUJAR), (source, aviso_de(out))
        with SinSubprocess() as guardia:
            for source in ("compact", "clear", None, "otro"):
                assert w.correr(inicio(source)) == (0, "", b""), source
        assert not guardia.llamadas, "en compact y clear no corre git"


def test_inicio_sin_entregas_pendientes_calla_del_todo_y_con_el_ticket_activo_inyecta_lo_mismo_que_antes():
    with git_aislado(), Toque() as w:
        con_origin(w.web)
        git(w.web, "branch", "feat/T-7")
        carpeta = w.base / "wt" / "web-T-7"
        git(w.web, "worktree", "add", "-q", str(carpeta), "feat/T-7")
        git(w.web, "update-ref", "refs/remotes/origin/feat/T-7", "refs/heads/feat/T-7")
        ticket_con_rama(w.raiz, "T-7-algo", "`%s`, rama `feat/T-7`" % carpeta)
        for source in ("startup", "resume", "fork"):
            assert w.correr(inicio(source)) == (0, "", b""), source
        marcar_activo(w.raiz, "tickets/T-7-algo")
        texto = aviso_de(w.correr(inicio_en("startup", w.raiz))[1])
        assert texto == "%s# T-7-algo\n\n## Objetivo\n\nhacer algo concreto\n\n%s" % (ENCABEZADO_DEL_RESUMEN, CIERRE_DEL_TICKET), texto
        escribir(carpeta, "nuevo.txt", "x\n")
        texto = aviso_de(w.correr(inicio_en("startup", w.raiz))[1])
        assert texto.startswith(entregas_pendientes("- T-7-algo: en web, la rama feat/T-7 tiene cambios sin commitear.") + "\n\n"
                                + ENCABEZADO_DEL_RESUMEN), texto


def test_inicio_un_ticket_confirmado_calla_hasta_que_cambia_su_huella():
    with git_aislado(), Toque() as w:
        con_origin(w.web)
        git(w.web, "branch", "feat/T-7")
        ticket_con_rama(w.raiz, "T-7-algo", "`feat/T-7`")
        git(w.web, "branch", "feat/T-8")
        ticket_con_rama(w.raiz, "T-8-otro", "`feat/T-8`")
        t8 = "- T-8-otro: en web, la rama feat/T-8 nunca se empujó."
        assert aviso_de(w.correr(inicio("startup"))[1]) == entregas_pendientes(T7_SIN_EMPUJAR, t8)
        assert confirmar_entrega(w.raiz, "T-7-algo") == 0
        assert aviso_de(w.correr(inicio("startup"))[1]) == entregas_pendientes(t8)
        assert confirmar_entrega(w.raiz, "T-8-otro") == 0
        assert w.correr(inicio("startup")) == (0, "", b""), "todo confirmado calla"
        git(w.web, "checkout", "-q", "feat/T-7")
        escribir(w.web, "base.txt", "otro\n")
        commitear(w.web, "nuevo")
        assert aviso_de(w.correr(inicio("startup"))[1]) == entregas_pendientes(T7_SIN_EMPUJAR), "la rama cambió"


def test_inicio_el_aviso_de_entregas_va_despues_de_las_fallas_anotadas_y_antes_del_ticket_activo():
    with git_aislado(), Toque() as w:
        con_origin(w.web)
        git(w.web, "branch", "feat/T-7")
        ticket_con_rama(w.raiz, "T-7-algo", "`feat/T-7`")
        marcar_activo(w.raiz, "tickets/T-7-algo")
        M.fallas.anotar("guard_comandos", {"hook_event_name": "PreToolUse"}, RuntimeError("rota"), str(w.raiz))
        texto = aviso_de(w.correr(inicio_en("startup", w.raiz))[1])
        fallas, entregas, ticket = texto.split("\n\n", 2)
        assert "desde el último aviso hubo 1 falla" in fallas, fallas
        assert entregas == entregas_pendientes(T7_SIN_EMPUJAR), entregas
        assert ticket.startswith(ENCABEZADO_DEL_RESUMEN) and ticket.endswith(CIERRE_DEL_TICKET), ticket


def test_inicio_con_mas_de_20_tickets_revisa_los_20_primeros_y_dice_en_una_linea_cuantos_quedaron():
    with git_aislado(), Toque() as w:
        con_origin(w.web)
        for n in range(1, 23):
            git(w.web, "branch", "feat/T-%d" % n)
            ticket_con_rama(w.raiz, "T-%02d-x" % n, "`feat/T-%d`" % n)
        texto = aviso_de(w.correr(inicio("startup"))[1])
        lineas = ["- T-%02d-x: en web, la rama feat/T-%d nunca se empujó." % (n, n) for n in range(1, 21)]
        quedaron = ("\nodd-ws: quedaron 2 tickets sin revisar (el inicio revisa hasta 20), así que no cuentan como limpios: "
                    "`entregas.py` los revisa todos.")
        assert texto == entregas_pendientes(*lineas) + quedaron, texto


def test_inicio_sin_plazo_lo_dice_en_una_linea_solo_si_habia_algo_que_chequear():
    with git_aislado(), Toque() as w:
        con_origin(w.web)
        ticket_con_rama(w.raiz, "T-7-algo", "árbol principal")
        assert w.correr(inicio("startup"), plazo=-1) == (0, "", b""), "nada que chequear"
        ticket_con_rama(w.raiz, "T-8-otro", "`feat/T-8`")
        texto = aviso_de(w.correr(inicio("startup"), plazo=-1)[1])
        assert texto == ("odd-ws: quedó 1 ticket sin revisar (no alcanzó el tiempo), así que no cuenta como limpio: "
                         "`entregas.py` los revisa todos."), texto


def test_inicio_una_falla_del_aviso_de_entregas_no_calla_el_resto_del_inicio():
    with git_aislado(), Toque() as w:
        con_origin(w.web)
        git(w.web, "branch", "feat/T-7")
        ticket_con_rama(w.raiz, "T-7-algo", "`feat/T-7`")
        marcar_activo(w.raiz, "tickets/T-7-algo")
        original = M.entregas.aviso_de_inicio

        def rota(*_a, **_k):
            raise RuntimeError("rota")

        M.entregas.aviso_de_inicio = rota
        try:
            codigo, out, err = w.correr(inicio_en("startup", w.raiz))
        finally:
            M.entregas.aviso_de_inicio = original
        assert codigo == 0 and err == b"", (codigo, err)
        assert aviso_de(out) == "%s# T-7-algo\n\n## Objetivo\n\nhacer algo concreto\n\n%s" % (ENCABEZADO_DEL_RESUMEN, CIERRE_DEL_TICKET)


def test_inicio_con_la_config_rota_en_compact_clear_u_otro_origen_sigue_callando():
    with Mundo() as w:
        escribir(w.raiz, "workspace.config.json", "{rota")
        assert w.correr(inicio("startup"))[1], "control positivo"
        for source in ("compact", "clear", None, "otro", ""):
            assert w.correr(inicio(source)) == (0, "", b""), source
        for e in (evento(w.raiz / "a.cs", "Read"), evento(w.raiz / "a.cs", nombre="PreToolUse"), evento(w.raiz / "a.cs", nombre="SubagentStop"),
                  evento(w.raiz / "a.cs", nombre="PreToolUse", source="startup"), evento(w.raiz / "a.cs", nombre="PostToolUse", source="resume")):
            assert w.correr(e) == (0, "", b""), e


def test_inicio_con_la_config_rota_en_fork_avisa_como_en_resume():
    with Mundo() as w:
        escribir(w.raiz, "workspace.config.json", "{rota")
        resume = w.correr(inicio("resume"))
        assert w.correr(inicio("fork")) == resume and "/odd-ws:doctor" in aviso_de(resume[1]), resume
        codigo, out, err = M.correr(inicio("fork"), raiz=w.raiz, host="codex")
        assert (codigo, err) == (0, b"") and "/odd-ws:doctor" in aviso_de(out), (codigo, out, err)
        for source in ("startup", "resume"):
            assert "/odd-ws:doctor" in aviso_de(w.correr(inicio(source))[1]), source
        for source in ("compact", "clear", None, "otro", "", "Fork"):
            assert w.correr(inicio(source)) == (0, "", b""), source


def test_inicio_sin_instancia_calla_en_todos_los_origenes():
    with Mundo() as w:
        assert w.correr(inicio("startup"))[0] == 0
        os.remove(w.raiz / "workspace.config.json")
        for source in ("startup", "resume", "compact", "clear", None):
            assert w.correr(inicio(source)) == (0, "", b""), source


def test_main_en_startup_avisa_por_stdout_con_la_config_rota_y_calla_sin_instancia():
    with Mundo() as w:
        entrada = json.dumps(inicio("startup")).encode("utf-8")
        sana = subprocess.run([sys.executable, str(_RUTA), "--plazo", "8"], input=entrada, capture_output=True, timeout=60,
                              env=entorno_de_sesion(w.raiz))
        assert (sana.returncode, sana.stdout, sana.stderr) == (0, b"", b""), sana
        escribir(w.raiz, "workspace.config.json", "{rota")
        rota = subprocess.run([sys.executable, str(_RUTA), "--plazo", "8"], input=entrada, capture_output=True, timeout=60,
                              env=entorno_de_sesion(w.raiz))
        assert rota.returncode == 0 and rota.stderr == b"", rota
        assert "/odd-ws:doctor" in aviso_de(rota.stdout.decode("utf-8"))
        vacia = w.base / "vacia"
        vacia.mkdir()
        sin = subprocess.run([sys.executable, str(_RUTA), "--plazo", "8"], input=entrada, capture_output=True, timeout=60,
                             env=entorno_de_sesion(vacia))
        assert (sin.returncode, sin.stdout, sin.stderr) == (0, b"", b""), sin


def test_sin_skill_sin_bloque_o_sin_marca_falla_abierto_y_nunca_bloquea():
    casos = {
        "sin skill": None,
        "sin bloque": skill("sql", cuerpo="solo texto\n"),
        "bloque abierto": skill("sql", cuerpo="<!-- no-negociables -->\n- regla\n"),
        "bloque vacio": skill("sql", cuerpo="<!-- no-negociables -->\n\n<!-- /no-negociables -->\n"),
    }
    for nombre, texto in casos.items():
        with Toque(capas=()) as w:
            if texto is not None:
                escribir(w.raiz, ".claude/skills/capa-sql/SKILL.md", texto)
            for e in (leer(w.sql), a_escribir(w.sql), a_escribir(w.sql, "Edit")):
                assert w.correr(e) == (0, "", b""), (nombre, e["hook_event_name"])
            assert w.marcas() == [], nombre
    with Toque() as w:
        escribir(w.raiz, ".claude/estado/primer-toque", "un archivo donde va la carpeta de marcas")
        for e in (leer(w.sql), a_escribir(w.sql), a_escribir(w.sql)):
            assert w.correr(e) == (0, "", b""), e["hook_event_name"]


def test_ids_invalidos_o_ausentes_callan():
    with Toque() as w:
        malos = [leer(w.sql, sesion=s) for s in ("", "../fuera", "a/b", "a b", None, 7)]
        sin_sesion = leer(w.sql)
        sin_sesion.pop("session_id")
        malos.append(sin_sesion)
        malos += [leer(w.sql, agente=a) for a in ("../x", "a\\b", "x" * 200, "odd-ws:writer")]
        malos += [a_escribir(w.sql, sesion="../fuera"), a_escribir(w.sql, agente="../x")]
        for e in malos:
            assert w.correr(e) == (0, "", b""), (e.get("session_id"), e.get("agent_id"))
        assert w.marcas() == [] and not (w.raiz / ".claude" / "estado" / "fuera").exists(), w.marcas()


def test_enrutamiento_solo_si_existe_el_writer_de_la_capa():
    with Toque(writers=("sql",)) as w:
        texto_sql = contexto(w.correr(leer(w.sql))[1])
        texto_web = contexto(w.correr(leer(w.cs))[1])
        assert "writer-sql" in texto_sql, texto_sql
        assert "writer" not in texto_web, texto_web
        codigo, _, err = w.correr(a_escribir(w.sql, sesion="s2"))
        assert codigo == 2 and b"writer-sql" in err, err


def test_poda_las_sesiones_de_mas_de_7_dias_al_abrir_una_nueva():
    with Toque() as w:
        base = w.raiz / ".claude" / "estado" / "primer-toque"
        ahora = time.time()
        for nombre, dias in (("vieja", 8), ("reciente", 1)):
            marca = escribir(base, "%s/principal.sql" % nombre, "")
            os.utime(marca.parent, (ahora - dias * 86400, ahora - dias * 86400))
        escribir(base, "suelto.txt", "")
        w.correr(leer(w.cs, sesion="reciente"))
        assert "vieja/principal.sql" in w.marcas(), w.marcas()
        w.correr(leer(w.sql, sesion="nueva"))
        assert w.marcas() == ["nueva/principal.sql", "reciente/principal.sql", "reciente/principal.web", "suelto.txt"], w.marcas()


def test_main_real_primer_toque_read_y_write_bajo_la_raiz_de_la_instancia():
    with Toque() as w:
        env = {k: v for k, v in _entorno_sin_git().items() if k not in ("PYTHONPATH", "PYTHONUTF8")}
        env.update(CLAUDE_PROJECT_DIR=str(w.raiz), PYTHONIOENCODING="cp1252")

        def real(e):
            return subprocess.run([sys.executable, str(_RUTA), "--plazo", "8"], input=json.dumps(e).encode("utf-8"),
                                  capture_output=True, timeout=60, env=env, cwd=str(w.base))

        r = real(leer(w.cs))
        texto = contexto(r.stdout.decode("utf-8", errors="replace"))
        assert r.returncode == 0 and r.stderr == b"" and texto and (REGLA % "WEB") in texto, r
        r = real(a_escribir(w.sql))
        assert r.returncode == 2 and r.stdout == b"" and (REGLA % "SQL").encode("utf-8") in r.stderr, r
        assert w.marcas() == ["s1/principal.sql", "s1/principal.web"], w.marcas()


def test_agente_con_la_skill_precargada_no_repite_el_primer_toque():
    with Toque() as w:
        w.agente("writer-sql", "---\nname: writer-sql\nskills:\n  - criterios\n  - capa-sql\n---\ncuerpo\n")
        w.agente("en-linea", "---\nname: en-linea\nskills: [criterios, capa-sql]\n---\n")
        for tipo, aid in (("writer-sql", "a1"), ("en-linea", "a2")):
            for herr in ("Read", "Write", "Edit"):
                e = leer(w.sql, agente=aid) if herr == "Read" else a_escribir(w.sql, herr, agente=aid)
                e["agent_type"] = tipo
                assert w.correr(e) == (0, "", b""), (tipo, herr)
        assert w.marcas() == [], w.marcas()
        e = leer(w.cs, agente="a1")
        e["agent_type"] = "writer-sql"
        c, o, _ = w.correr(e)
        assert c == 0 and contexto(o) is not None, "otra capa que no precarga si inyecta"
        assert contexto(w.correr(leer(w.sql))[1]) is not None, "la sesion principal inyecta"


def test_agente_sin_la_skill_o_con_frontmatter_ilegible_inyecta_igual():
    with Toque() as w:
        w.agente("otra-capa", "---\nname: otra-capa\nskills:\n  - capa-web\n---\n")
        w.agente("casi", "---\nname: casi\nskills:\n  - capa-sql-extra\n---\n")
        w.agente("roto", "---\nname: roto\nskills:\n  - capa-sql\n")
        w.agente("sin-skills", "---\nname: sin-skills\ntools: Read\n---\n")
        w.agente("en-el-cuerpo", "---\nname: en-el-cuerpo\n---\nskills:\n  - capa-sql\n")
        (w.raiz / ".claude" / "agents" / "carpeta.md").mkdir(parents=True)
        casos = [("otra-capa", "a1"), ("casi", "a2"), ("roto", "a3"), ("sin-skills", "a4"), ("en-el-cuerpo", "a5"),
                 ("carpeta", "a6"), ("no-existe", "a7"), ("odd-ws:writer-sql", "a8"), ("../x", "a9"), ("", "a10"), (None, "a11")]
        for tipo, aid in casos:
            e = leer(w.sql, agente=aid)
            if tipo is None:
                del e["agent_type"]
            else:
                e["agent_type"] = tipo
            c, o, _ = w.correr(e)
            assert c == 0 and contexto(o) is not None, tipo
        e = a_escribir(w.sql, "Write", agente="b1")
        e["agent_type"] = "roto"
        c, _, err = w.correr(e)
        assert c == 2 and "capa-sql" in err.decode("utf-8"), c


def test_skills_del_frontmatter_formas_de_yaml_validas():
    f = M.skills_del_frontmatter
    casos = [
        ("lista de bloque sin sangria", "---\nname: x\nskills:\n- criterios\n- capa-sql\n---\n", ["criterios", "capa-sql"]),
        ("sin sangria y la clave siguiente la corta", "---\nskills:\n- a\ntools:\n- Read\n---\n", ["a"]),
        ("comentario tras la clave", "---\nskills: # las de la capa\n  - capa-sql\n---\n", ["capa-sql"]),
        ("comentario tras un item", "---\nskills:\n  - criterios # base\n  - capa-sql # capa\n---\n", ["criterios", "capa-sql"]),
        ("comentario tras la lista en linea", "---\nskills: [a, b] # c\n---\n", ["a", "b"]),
        ("item entre comillas con comentario", "---\nskills:\n  - 'capa-sql'  # c\n---\n", ["capa-sql"]),
        ("linea de comentario y linea en blanco dentro", "---\nskills:\n  # nota\n  - a\n\n  - b\n---\n", ["a", "b"]),
        ("lista en linea", "---\nskills: [criterios, \"capa-sql\"]\n---\n", ["criterios", "capa-sql"]),
        ("lista de bloque con sangria", "---\nskills:\n  - criterios\n  - capa-sql\ntools: Read\n---\n", ["criterios", "capa-sql"]),
        ("sin skills", "---\nname: x\ntools: Read\n---\n", []),
        ("sin cerrar", "---\nskills:\n  - a\n", None),
        ("sin frontmatter", "skills:\n  - a\n", None),
        ("el cuerpo no cuenta", "---\nname: x\n---\nskills:\n- a\n", []),
        ("con BOM", "﻿---\nskills: [a]\n---\n", ["a"]),
    ]
    for etiqueta, texto, esperado in casos:
        assert f(texto) == esperado, (etiqueta, f(texto))


def test_cada_evento_del_primer_toque_esta_cableado():
    cableados = {}
    for e, m, h in _hooks_del_plugin():
        if h["args"][0].endswith("/scripts/verificar_capa.py"):
            for parte in m.split("|"):
                cableados[(e, parte)] = (h["timeout"], M.plazo_de(h["args"][1:]))
    for clave in (("PostToolUse", "Edit"), ("PostToolUse", "Write"), ("PostToolUse", "Read"), ("PreToolUse", "Edit"),
                  ("PreToolUse", "Write"), ("SessionStart", "compact"), ("SessionStart", "clear"), ("SessionStart", "startup"),
                  ("SessionStart", "resume")):
        assert clave in cableados, (clave, cableados)
    for clave in (("PostToolUse", "Read"), ("PreToolUse", "Edit"), ("PreToolUse", "Write"), ("SessionStart", "compact"),
                  ("SessionStart", "clear"), ("SessionStart", "startup"), ("SessionStart", "resume")):
        assert cableados[clave] == (10, 8), (clave, cableados[clave])
    assert {p for (e, p) in cableados if e == "SessionStart"} == {"startup", "resume", "compact", "clear"}


@contextlib.contextmanager
def git_aislado():
    carpeta = Path(tempfile.mkdtemp(prefix="verificar-capa-git-"))
    previo = {k: os.environ.get(k) for k in AISLAMIENTO_GIT}
    os.environ.update(GIT_CONFIG_GLOBAL=str(carpeta / "global"), GIT_CONFIG_SYSTEM=str(carpeta / "sistema"),
                      GIT_CONFIG_NOSYSTEM="1")
    try:
        yield
    finally:
        for clave, valor in previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(carpeta, onexc=_quitar)
        if carpeta.exists():
            SOBRANTES.append(str(carpeta))


def parche_codex(*lineas):
    return "\n".join(("*** Begin Patch",) + lineas + ("*** End Patch",)) + "\n"


def codex(texto, nombre="PreToolUse", cwd=None, **extra):
    e = {"hook_event_name": nombre, "tool_name": "apply_patch", "tool_input": {"command": texto}, "session_id": "s1",
         "turn_id": "t1"}
    if cwd is not None:
        e["cwd"] = str(cwd)
    e.update(extra)
    return e


def _json_de_codex(salida):
    codigo, texto, error = salida
    if isinstance(texto, bytes):
        texto = texto.decode("ascii")
    if (codigo, error) != (0, b"") or not texto:
        return None
    try:
        datos = json.loads(texto)
    except ValueError:
        return None
    return datos if isinstance(datos, dict) else None


def negado_en_codex(salida):
    datos = _json_de_codex(salida) or {}
    decision = datos.get("hookSpecificOutput")
    if not isinstance(decision, dict) or (decision.get("hookEventName"), decision.get("permissionDecision")) != ("PreToolUse", "deny"):
        return None
    return decision.get("permissionDecisionReason")


def bloqueado_en_codex(salida):
    datos = _json_de_codex(salida) or {}
    return datos.get("reason") if set(datos) == {"decision", "reason"} and datos["decision"] == "block" else None


def test_codex_no_precarga_skills_y_el_writer_tiene_su_primer_toque():
    with git_aislado(), Toque() as w:
        w.agente("writer-sql", "---\nname: writer-sql\nskills:\n  - criterios\n  - capa-sql\n---\ncuerpo\n")
        texto = parche_codex("*** Update File: %s" % w.sql, "@@", "-a", "+b")
        e = codex(texto, agent_type="writer-sql", agent_id="a1")
        motivo = negado_en_codex(M.correr(e, raiz=w.raiz, plazo=25, host="codex"))
        assert motivo is not None and motivo.startswith("primer toque (capa-sql)"), motivo
        assert w.marcas() == ["s1/a1.sql"], w.marcas()
        assert M.correr(e, raiz=w.raiz, plazo=25, host="codex") == (0, "", b""), "el reintento pasa"
        claude = a_escribir(w.sql, "Edit", agente="a2")
        claude["agent_type"] = "writer-sql"
        assert w.correr(claude) == (0, "", b""), "en Claude Code la skill precargada sigue salteando el primer toque"
        assert w.marcas() == ["s1/a1.sql"], w.marcas()


def test_codex_un_parche_de_dos_capas_bloquea_una_vez_con_los_dos_primeros_toques():
    with git_aislado(), Toque() as w:
        texto = parche_codex("*** Update File: %s" % w.sql, "@@", "-a", "+b", "*** Add File: %s" % w.cs, "+int a;",
                             "*** Delete File: %s" % w.sql2)
        salida = M.correr(codex(texto), raiz=w.raiz, plazo=25, host="codex")
        motivo = negado_en_codex(salida)
        assert motivo is not None, "en Codex se bloquea por JSON con exit 0: %r" % (salida,)
        assert motivo.index(REGLA % "SQL") < motivo.index(REGLA % "WEB"), motivo
        assert motivo.count("primer toque (capa-") == 2 and "\n\nprimer toque (capa-web)" in motivo, motivo
        assert motivo.startswith("primer toque (capa-sql): este apply_patch no se aplicó."), motivo
        assert w.marcas() == ["s1/principal.sql", "s1/principal.web"], "el tercer archivo es de una capa ya marcada"
        assert M.correr(codex(texto), raiz=w.raiz, plazo=25, host="codex") == (0, "", b""), "el reintento pasa"


def test_codex_post_combina_los_hallazgos_de_cada_archivo_y_salta_los_que_ya_no_estan():
    with git_aislado(), Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        escribir(w.web, "Core/A.cs", "a = MALO BLOQ;\n")
        escribir(w.web, "Core/B.cs", "b = MALO;\n")
        escribir(w.web, "Core/C.cs", "c = MALO;\n")
        texto = parche_codex("*** Update File: Core/B.cs", "@@", "+b = MALO;", "*** Delete File: Core/Borrado.cs",
                             "*** Update File: Core/Viejo.cs", "*** Move to: Core/A.cs", "@@", "+a = MALO BLOQ;")
        salida = M.correr(codex(texto, "PostToolUse", cwd=w.web), raiz=w.raiz, plazo=25, host="codex")
        motivo = bloqueado_en_codex(salida)
        assert motivo is not None, "en Codex post bloquea con decision block y exit 0: %r" % (salida,)
        assert motivo.startswith("verificar-capa (aviso): Core/B.cs tiene 1 aviso(s)"), motivo
        assert "\n\nverificar-capa: Core/A.cs tiene 1 problema(s): corregir y reintentar." in motivo, motivo
        assert "Borrado" not in motivo and "Viejo" not in motivo, motivo
        avisos = parche_codex("*** Update File: Core/B.cs", "*** Delete File: Core/Borrado.cs", "*** Add File: Core/C.cs")
        codigo, out, err = M.correr(codex(avisos, "PostToolUse", cwd=w.web), raiz=w.raiz, plazo=25, host="codex")
        texto_ = contexto(out)
        assert (codigo, err) == (0, b"") and texto_ is not None, (codigo, out, err)
        assert texto_.startswith("verificar-capa (aviso): Core/B.cs") and "\n\nverificar-capa (aviso): Core/C.cs" in texto_, texto_
        solo_borrado = parche_codex("*** Delete File: Core/Borrado.cs")
        assert M.correr(codex(solo_borrado, "PostToolUse", cwd=w.web), raiz=w.raiz, plazo=25, host="codex") == (0, "", b"")


def test_codex_un_archivo_que_revienta_no_silencia_el_bloqueo_de_los_otros():
    with git_aislado(), Mundo(db={"src/Proc_X.sql": "select 0;\n"}) as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        w.modulo("sql", "raise RuntimeError('roto')\n")
        escribir(w.web, "Core/A.cs", "a = MALO BLOQ;\n")
        escribir(w.db, "src/Proc_X.sql", "select 1;\n")
        cs = ("*** Update File: Core/A.cs", "@@", "+a = MALO BLOQ;")
        sql = ("*** Update File: ../db/src/Proc_X.sql", "@@", "-select 0;", "+select 1;")
        for lineas in (cs + sql, sql + cs):
            salida = M.correr(codex(parche_codex(*lineas), "PostToolUse", cwd=w.web), raiz=w.raiz, plazo=25, host="codex")
            assert "Core/A.cs tiene 1 problema(s)" in (bloqueado_en_codex(salida) or ""), (lineas, salida)


def test_codex_una_capa_que_revienta_en_el_primer_toque_no_silencia_la_otra():
    with git_aislado(), Toque() as w:
        (w.raiz / ".claude" / "skills" / "capa-web" / "SKILL.md").write_bytes(b"\xff\xfe\xff no es utf-8\n")
        sql = ("*** Update File: %s" % w.sql, "@@", "-a", "+b")
        cs = ("*** Add File: %s" % w.cs, "+int a;")
        for sesion, lineas in (("s1", sql + cs), ("s2", cs + sql)):
            salida = M.correr(codex(parche_codex(*lineas), session_id=sesion), raiz=w.raiz, plazo=25, host="codex")
            assert (REGLA % "SQL") in (negado_en_codex(salida) or ""), (sesion, salida)


def test_codex_inicio_con_fork_y_con_la_config_rota():
    with git_aislado(), Toque() as w:
        w.correr(leer(w.sql))
        assert w.marcas() == ["s1/principal.sql"]
        assert M.correr(inicio("fork"), raiz=w.raiz, host="codex") == (0, "", b"")
        assert w.marcas() == ["s1/principal.sql"], "fork no reinicia el primer toque"
        assert M.correr(inicio("compact"), raiz=w.raiz, host="codex") == (0, "", b"") and w.marcas() == []
        escribir(w.raiz, "workspace.config.json", "{rota")
        codigo, out, err = M.correr(inicio("startup"), raiz=w.raiz, host="codex")
        assert (codigo, err) == (0, b"") and "/odd-ws:doctor" in aviso_de(out), (codigo, out, err)


def test_un_host_desconocido_bloquea_en_pre_sin_correr_el_nucleo_y_calla_en_lo_demas():
    with git_aislado(), Toque() as w:
        for host in ("otro", "", None, "Codex"):
            codigo, out, err = M.correr(a_escribir(w.sql), raiz=w.raiz, plazo=25, host=host)
            assert codigo == 2 and out == "" and err.startswith(b"odd-ws: host desconocido"), (host, codigo, err)
        for e in (leer(w.sql), inicio("startup"), inicio("compact"), evento(w.sql)):
            assert M.correr(e, raiz=w.raiz, plazo=25, host="otro") == (0, "", b""), e
        assert w.marcas() == [], "con un host desconocido el núcleo no corre"
        assert M.correr(a_escribir(w.sql), raiz=w.raiz, plazo=25)[0] == 2 and w.marcas() == ["s1/principal.sql"], "sin host, Claude Code"


def test_main_elige_el_host_con_el_argumento():
    with git_aislado(), Toque() as w:
        env = dict(_entorno_sin_git(), CLAUDE_PROJECT_DIR=str(w.raiz))

        def hook(payload, *args):
            return subprocess.run([sys.executable, str(_RUTA), "--plazo", "8", *args], input=json.dumps(payload).encode("utf-8"),
                                  capture_output=True, timeout=60, env=env)

        r = hook(a_escribir(w.sql), "--host", "gemini")
        assert r.returncode == 2 and r.stdout == b"" and r.stderr.startswith(b"odd-ws: host desconocido") and b"'gemini'" in r.stderr, r
        r = hook(a_escribir(w.sql), "--host")
        assert r.returncode == 2 and b"sin valor" in r.stderr, r
        assert hook(inicio("startup"), "--host", "gemini").returncode == 0 and w.marcas() == []
        r = hook(codex(parche_codex("*** Update File: %s" % w.sql, " x")), "--host", "codex")
        assert (REGLA % "SQL") in (negado_en_codex((r.returncode, r.stdout, r.stderr)) or ""), r
        r = hook(codex(parche_codex("*** Update File: %s" % w.cs, " x"), session_id="s2"))
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), "sin --host es Claude Code, y apply_patch no es suyo"
        r = hook(a_escribir(w.cs, sesion="s3"))
        assert r.returncode == 2 and (REGLA % "WEB").encode("utf-8") in r.stderr, r
        r = hook(codex(parche_codex("*** Update File: %s" % w.sql, " x"), session_id="s4"), "--host=codex")
        assert (REGLA % "SQL") in (negado_en_codex((r.returncode, r.stdout, r.stderr)) or ""), "--host=codex es Codex: %r" % r
        r = hook(a_escribir(w.sql, sesion="s5"), "--host=gemini")
        assert r.returncode == 2 and r.stderr.startswith(b"odd-ws: host desconocido") and b"'gemini'" in r.stderr, r


HUELLA_CUALQUIERA = "sha256:" + "0" * 64
PAQUETE_MALO = '''import types
REGLA = types.SimpleNamespace(id="%(prefijo)s-01", sembrado="x = MALO;")
REGLAS = (REGLA,)
def verificar(ctx):
    return [{"id": REGLA.id, "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None,
             "mensaje": "regla del paquete %(nombre)s en " + __name__}
            for n, t in ctx["agregadas"] if "MALO" in t]
'''


def poner_paquete(w, nombre, prefijo, fuente=None, capa="web", no_negociables="", api=1, manifiesto=None, huella=None):
    from odd_ws import paquetes
    carpeta = ".claude/reglas/paquetes/%s/" % nombre
    escribir(w.raiz, carpeta + "verificar.py", PAQUETE_MALO % {"prefijo": prefijo, "nombre": nombre} if fuente is None else fuente)
    escribir(w.raiz, carpeta + "no-negociables.md", no_negociables)
    datos = manifiesto or {"formato": 1, "nombre": nombre, "prefijo": prefijo, "odd_ws_api": api, "descripcion": "de prueba"}
    escribir(w.raiz, carpeta + "odd-ws-paquete.json", json.dumps(datos))
    lock = w.raiz / ".claude" / "reglas" / "paquetes.json"
    contenido = json.loads(lock.read_text(encoding="utf-8")) if lock.is_file() else {"version": 1, "paquetes": {}}
    contenido["paquetes"][nombre] = {"capa": capa, "prefijo": prefijo, "fuente": "https://example.com/%s.git" % nombre,
                                     "etiqueta": "v1.0.0", "commit": "a" * 40, "huella": huella or paquetes.huella(w.raiz / carpeta)}
    escribir(w.raiz, ".claude/reglas/paquetes.json", json.dumps(contenido))


def problemas_de(err):
    return err.decode("utf-8").rstrip("\n").split("\n")


def archivo_con_malo(w, texto="a // MALO BLOQ\n"):
    escribir(w.web, "Core/Base.cs", "x\n")
    commitear(w.web)
    return escribir(w.web, "Core/N.cs", texto)


def test_paquetes_una_regla_sin_calibrar_solo_avisa_y_calibrada_bloquea():
    with git_aislado(), Mundo() as w:
        poner_paquete(w, "alfa", "ALF")
        ruta = archivo_con_malo(w)
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1:] == ["[ALF-01] linea 1: regla del paquete alfa en verificar_capa_paquete_alfa" + sin_calibrar(w)], lineas
        salida = w.calibrar("web")
        assert "ALF-01 puede bloquear" in salida.splitlines(), salida
        codigo, _, err = w.correr(evento(ruta))
        assert codigo == 2 and problemas_de(err)[1:] == ["[ALF-01] linea 1: regla del paquete alfa en verificar_capa_paquete_alfa"], err


def test_paquetes_un_lock_con_otra_huella_deja_vieja_su_calibracion():
    with git_aislado(), Mundo() as w:
        poner_paquete(w, "alfa", "ALF")
        w.calibrar("web")
        ruta = archivo_con_malo(w)
        assert w.correr(evento(ruta))[0] == 2, "control: calibrado, bloquea"
        poner_paquete(w, "alfa", "ALF", no_negociables="- **ALF-01** de la etiqueta nueva.\n")
        lineas = contexto_de(w.correr(evento(ruta)))
        assert lineas[1].endswith(" (aviso: calibración vieja; para que bloquee, %s)" % CORREGIR % comando(w.web)), lineas


def test_paquetes_una_disputa_vale_tambien_para_una_regla_de_paquete():
    with git_aislado(), Mundo() as w:
        poner_paquete(w, "alfa", "ALF")
        w.calibrar("web")
        escribir(w.raiz, ".claude/registro/disputas/ALF-01.md", DISPUTA % "ALF-01")
        lineas = contexto_de(w.correr(evento(archivo_con_malo(w))))
        assert lineas[1:] == ["[ALF-01] linea 1: regla del paquete alfa en verificar_capa_paquete_alfa" + disputada(w, "ALF-01")], lineas


def test_paquetes_sus_hallazgos_se_suman_a_los_de_la_capa_en_orden_de_nombre():
    with git_aislado(), Mundo() as w:
        w.modulo("web", STUB_MALO)
        poner_paquete(w, "zeta", "ZET")
        poner_paquete(w, "alfa-uno", "ALF")
        poner_paquete(w, "de-sql", "DSQ", capa="sql")
        w.calibrar("web")
        codigo, out, err = w.correr(evento(archivo_con_malo(w)))
        assert codigo == 2 and out == "", (codigo, out, err)
        assert problemas_de(err) == ["verificar-capa: Core/N.cs tiene 3 problema(s): corregir y reintentar.",
                                     "[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs",
                                     "[ALF-01] linea 1: regla del paquete alfa-uno en verificar_capa_paquete_alfa_uno",
                                     "[ZET-01] linea 1: regla del paquete zeta en verificar_capa_paquete_zeta"], problemas_de(err)


def test_paquetes_corren_aunque_la_capa_no_tenga_modulo_propio():
    with git_aislado(), Mundo() as w:
        poner_paquete(w, "alfa", "ALF")
        w.calibrar("web")
        codigo, _, err = w.correr(evento(archivo_con_malo(w)))
        assert codigo == 2 and problemas_de(err)[1:] == ["[ALF-01] linea 1: regla del paquete alfa en verificar_capa_paquete_alfa"], err


def test_paquetes_uno_roto_no_calla_la_capa_ni_a_los_otros():
    rotos = {
        "excepcion": "def verificar(ctx):\n    raise RuntimeError('boom')\n",
        "invalido": "def verificar(ctx):\n    return [{'id': 'INV-01'}]\n",
        "mezcla": "def verificar(ctx):\n    return [{'id': 'MEZ-01', 'modo': 'bloqueo', 'mensaje': 'valido'}, {'modo': 'bloqueo'}]\n",
        "fuera-de-prefijo": "def verificar(ctx):\n    return [{'id': 'T-02', 'modo': 'bloqueo', 'mensaje': 'ajeno'}]\n",
        "salida": "import sys\ndef verificar(ctx):\n    sys.exit(3)\n",
        "sintaxis": "def verificar(ctx) syntax error\n",
        "tipo": "def verificar(ctx):\n    return 42\n",
        "muta-el-ctx": "def verificar(ctx):\n    ctx['agregadas'].clear()\n    ctx['hunks'].clear()\n    return []\n",
    }
    with git_aislado(), Mundo() as w:
        w.modulo("web", STUB_MALO)
        poner_paquete(w, "sano", "ZZZ")
        w.calibrar("web")
        prefijos = {"excepcion": "EXC", "invalido": "INV", "mezcla": "MEZ", "fuera-de-prefijo": "FUE", "salida": "SAL",
                    "sintaxis": "SIN", "tipo": "TIP", "muta-el-ctx": "MUT"}
        for nombre, fuente in rotos.items():
            poner_paquete(w, nombre, prefijos[nombre], fuente)
        poner_paquete(w, "pide-mas-api", "API", api=2)
        codigo, out, err = w.correr(evento(archivo_con_malo(w)))
        assert codigo == 2 and problemas_de(err)[1:] == ["[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs",
                                                         "[ZZZ-01] linea 1: regla del paquete sano en verificar_capa_paquete_sano"], err


def test_paquetes_un_modulo_de_la_capa_roto_no_calla_a_los_paquetes():
    for fuente in ("def verificar(ctx):\n    raise RuntimeError('boom')\n", "def verificar(ctx):\n    return [{'id': 'X'}]\n",
                   "import sys\ndef verificar(ctx):\n    sys.exit(3)\n"):
        with git_aislado(), Mundo() as w:
            poner_paquete(w, "alfa", "ALF")
            w.calibrar("web")
            w.modulo("web", fuente)
            codigo, _, err = w.correr(evento(archivo_con_malo(w)))
            assert codigo == 2 and problemas_de(err)[1:] == ["[ALF-01] linea 1: regla del paquete alfa en verificar_capa_paquete_alfa"], (fuente, err)


def test_paquetes_la_compuerta_del_writer_sigue_viendo_el_error_del_modulo_de_la_capa():
    spec = importlib.util.spec_from_file_location("writer_stop", AQUI / "writer_stop.py")
    writer_stop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer_stop)
    with git_aislado(), Mundo() as w:
        poner_paquete(w, "alfa", "ALF")
        w.calibrar("web")
        w.modulo("web", "def verificar(ctx):\n    raise RuntimeError('boom')\n")
        ruta = archivo_con_malo(w)
        try:
            M.verificar_archivo(ruta, w.config())
        except RuntimeError as error:
            assert str(error) == "boom"
        else:
            raise AssertionError("con un paquete instalado, quien llama a verificar_archivo sigue viendo el error de la capa")
        bloqueos, avisos, internos = writer_stop._chequear([str(ruta)], w.config(), None)
        assert (bloqueos, avisos) == ([], []) and len(internos) == 1 and "boom" in internos[0], (bloqueos, avisos, internos)
        codigo, _, err = w.correr(evento(ruta))
        assert codigo == 2 and "ALF-01" in err.decode("utf-8"), "el hook aísla la capa y los hallazgos del paquete salen igual"


def test_paquetes_con_el_lock_roto_se_ignoran_y_la_capa_sigue_verificando():
    for lock in ("{roto", json.dumps({"version": 2, "paquetes": {}}), json.dumps({"version": 1, "paquetes": {"Mal": {}}})):
        with git_aislado(), Mundo() as w:
            w.modulo("web", STUB_MALO)
            w.calibrar("web")
            poner_paquete(w, "alfa", "ALF")
            escribir(w.raiz, ".claude/reglas/paquetes.json", lock)
            codigo, _, err = w.correr(evento(archivo_con_malo(w)))
            assert codigo == 2 and problemas_de(err)[1:] == ["[T-02 CRITICAL] linea 1 en «MALO»: está mal → así, molde: x/y.cs"], (lock, err)


def test_paquetes_el_hook_no_mira_la_huella():
    with git_aislado(), Mundo() as w:
        poner_paquete(w, "alfa", "ALF", huella=HUELLA_CUALQUIERA)
        lineas = contexto_de(w.correr(evento(archivo_con_malo(w))))
        assert lineas[1:] == ["[ALF-01] linea 1: regla del paquete alfa en verificar_capa_paquete_alfa" + sin_calibrar(w)], \
            "el lock tiene una huella cualquiera y el paquete corre igual, sin calibrar: %r" % lineas


def test_paquetes_con_el_prefijo_de_una_capa_no_corren():
    with git_aislado(), Mundo() as w:
        config = json.loads((w.raiz / "workspace.config.json").read_text(encoding="utf-8"))
        config["layers"]["sql"]["rule_prefix"] = "ALF"
        escribir(w.raiz, "workspace.config.json", json.dumps(config))
        poner_paquete(w, "beta", "BET")
        w.calibrar("web")
        poner_paquete(w, "alfa", "ALF")
        codigo, _, err = w.correr(evento(archivo_con_malo(w)))
        assert codigo == 2 and problemas_de(err)[1:] == ["[BET-01] linea 1: regla del paquete beta en verificar_capa_paquete_beta"], err


LENTO = '''import time
def verificar(ctx):
    time.sleep(max(0.0, ctx["limite"] - time.monotonic()) + 0.05)
    return [{"id": "%s", "modo": "aviso", "severidad": "", "linea": None, "fragmento": None, "mensaje": "lento"}]
'''


def test_paquetes_respetan_el_plazo_y_no_corren_si_ya_vencio():
    with git_aislado(), Mundo() as w:
        w.modulo("web", LENTO % "T-07")
        poner_paquete(w, "alfa", "ALF")
        antes = time.monotonic()
        codigo, out, err = w.correr(evento(archivo_con_malo(w)), plazo=2)
        assert time.monotonic() - antes < 2 + 2, time.monotonic() - antes
        assert codigo == 0 and err == b"" and contexto(out).split("\n")[1:] == ["[T-07] archivo: lento"], (codigo, out, err)
    with git_aislado(), Mundo() as w:
        poner_paquete(w, "a-lento", "ALE", LENTO % "ALE-01")
        poner_paquete(w, "b-rapido", "BRA")
        codigo, out, err = w.correr(evento(archivo_con_malo(w)), plazo=2)
        assert codigo == 0 and err == b"" and contexto(out).split("\n")[1:] == ["[ALE-01] archivo: lento"], (codigo, out, err)


def test_sin_lock_un_modulo_de_la_capa_que_revienta_sigue_subiendo_a_quien_llama():
    with git_aislado(), Mundo() as w:
        w.modulo("web", "def verificar(ctx):\n    raise RuntimeError('boom')\n")
        ruta = archivo_con_malo(w)
        try:
            M.verificar_archivo(ruta, w.config())
        except RuntimeError as error:
            assert str(error) == "boom"
        else:
            raise AssertionError("sin paquetes, la compuerta del writer sigue viendo el error del módulo")
        w.modulo("web", "def verificar(ctx):\n    return [{'id': 'X'}]\n")
        assert M.verificar_archivo(ruta, w.config()) is None
        assert w.correr(evento(ruta)) == (0, "", b"")
        escribir(w.raiz, ".claude/reglas/paquetes.json", json.dumps({"version": 1, "paquetes": {}}))
        assert M.verificar_archivo(ruta, w.config()) is None, "un lock sin paquetes de la capa es lo mismo que no tenerlo"


REGLA_DE_PAQUETE = "- **%s-01** Regla del paquete %s."


def texto_de_paquete(nombre, prefijo):
    return "Del paquete %s (fuente: .claude/reglas/paquetes/%s/no-negociables.md):\n%s" % (nombre, nombre, REGLA_DE_PAQUETE % (prefijo, nombre))


def test_paquetes_el_primer_toque_suma_sus_no_negociables_tras_el_bloque_de_la_capa():
    with git_aislado(), Toque() as w:
        poner_paquete(w, "zeta", "ZET", capa="sql", no_negociables="﻿" + REGLA_DE_PAQUETE % ("ZET", "zeta") + "\r\n\r\n")
        poner_paquete(w, "alfa", "ALF", capa="sql", no_negociables=REGLA_DE_PAQUETE % ("ALF", "alfa") + "\n")
        poner_paquete(w, "vacio", "VAC", capa="sql", no_negociables="  \n\n")
        poner_paquete(w, "nuevo", "NUE", capa="sql", no_negociables=REGLA_DE_PAQUETE % ("NUE", "nuevo"), api=2)
        poner_paquete(w, "de-web", "DWE", capa="web", no_negociables=REGLA_DE_PAQUETE % ("DWE", "de-web"))
        texto = contexto(w.correr(leer(w.sql))[1])
        partes = texto.split("\n", 1)
        assert partes[0].startswith("primer toque (capa-sql):"), partes[0]
        assert partes[1] == "\n\n".join([REGLA % "SQL", texto_de_paquete("alfa", "ALF"), texto_de_paquete("zeta", "ZET")]), partes[1]
        codigo, _, err = w.correr(a_escribir(w.sql, sesion="s2"))
        assert codigo == 2 and texto_de_paquete("alfa", "ALF").encode("utf-8") in err, err
        assert texto_de_paquete("de-web", "DWE") in contexto(w.correr(leer(w.cs))[1])


def test_paquetes_traen_sus_no_negociables_aunque_la_capa_tenga_solo_el_relleno_o_ninguno():
    plantilla = (PLUGIN / "plantillas" / "capa.md").read_text(encoding="utf-8")
    generada = plantilla.replace("{{capa}}", "sql").replace("{{fecha}}", "2026-11-16")
    for skill_sql in (generada, None):
        with git_aislado(), Toque(capas=("web",)) as w:
            if skill_sql is not None:
                escribir(w.raiz, ".claude/skills/capa-sql/SKILL.md", skill_sql)
            poner_paquete(w, "alfa", "ALF", capa="sql", no_negociables=REGLA_DE_PAQUETE % ("ALF", "alfa"))
            texto = contexto(w.correr(leer(w.sql))[1])
            assert texto is not None and texto.split("\n", 1)[1] == texto_de_paquete("alfa", "ALF"), texto
            assert w.marcas() == ["s1/principal.sql"], w.marcas()
            poner_paquete(w, "alfa", "ALF", capa="sql", no_negociables="")
            assert w.correr(leer(w.sql, sesion="s2")) == (0, "", b""), "un no-negociables.md vacío no suma nada"
            assert w.correr(a_escribir(w.sql, sesion="s3")) == (0, "", b"")


def test_paquetes_con_el_lock_roto_el_primer_toque_trae_solo_la_capa():
    with git_aislado(), Toque() as w:
        poner_paquete(w, "alfa", "ALF", capa="sql", no_negociables=REGLA_DE_PAQUETE % ("ALF", "alfa"))
        escribir(w.raiz, ".claude/reglas/paquetes.json", "{roto")
        texto = contexto(w.correr(leer(w.sql))[1])
        assert texto.split("\n", 1)[1] == REGLA % "SQL", texto


def test_paquetes_un_agente_con_la_skill_precargada_recibe_solo_los_de_los_paquetes():
    with git_aislado(), Toque() as w:
        w.agente("writer-sql", "---\nname: writer-sql\nskills:\n  - capa-sql\n---\n")
        e = leer(w.sql, agente="a1")
        e["agent_type"] = "writer-sql"
        assert w.correr(e) == (0, "", b""), "sin paquetes, como siempre: la skill ya trae el bloque"
        poner_paquete(w, "alfa", "ALF", capa="sql", no_negociables=REGLA_DE_PAQUETE % ("ALF", "alfa"))
        texto = contexto(w.correr(e)[1])
        delegar = "Para más que un ajuste mínimo, delegar en `writer-sql`."
        assert texto is not None and texto.split("\n", 1)[1] == texto_de_paquete("alfa", "ALF") + "\n" + delegar, texto
        assert w.correr(e) == (0, "", b""), "una vez por sesión y agente"
        assert w.marcas() == ["s1/a1.sql"], w.marcas()


def test_sin_lock_el_primer_toque_no_cambia():
    with git_aislado(), Toque() as w:
        texto = contexto(w.correr(leer(w.sql))[1])
        assert texto.split("\n", 1)[1] == REGLA % "SQL", texto
        assert M.no_negociables("sql", str(w.raiz)) == REGLA % "SQL"


def test_paquetes_una_skill_de_la_capa_ilegible_no_calla_los_de_los_paquetes():
    with git_aislado(), Toque() as w:
        (w.raiz / ".claude" / "skills" / "capa-sql" / "SKILL.md").write_bytes(b"\xff\xfe\xff no es utf-8\n")
        assert w.correr(leer(w.sql)) == (0, "", b"") and w.marcas() == [], "sin paquetes, como siempre"
        try:
            M.no_negociables("sql", str(w.raiz))
        except UnicodeDecodeError:
            pass
        else:
            raise AssertionError("sin paquetes, el error de la skill sigue subiendo")
        poner_paquete(w, "alfa", "ALF", capa="sql", no_negociables=REGLA_DE_PAQUETE % ("ALF", "alfa"))
        texto = contexto(w.correr(leer(w.sql, sesion="s2"))[1])
        assert texto is not None and texto.split("\n", 1)[1] == texto_de_paquete("alfa", "ALF"), texto


def apagar(raiz, valor):
    ruta = Path(raiz) / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["disabled_hooks"] = valor
    ruta.write_text(json.dumps(config), encoding="utf-8")


def test_apagado_en_disabled_hooks_deja_pasar_todo_sin_marcas_ni_avisos():
    with git_aislado(), Toque() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        malo = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        assert w.correr(evento(malo))[0] == 2, "control: la regla de la capa bloquea"
        assert w.correr(a_escribir(w.sql, sesion="c1"))[0] == 2, "control: el primer toque bloquea"
        marcar_activo(w.raiz, "tickets/T-7-algo")
        escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", TICKET_ACTIVO)
        assert w.correr(inicio_en("startup", w.raiz))[1], "control: el inicio inyecta el ticket activo"
        texto = parche_codex("*** Update File: %s" % w.sql, "@@", "-a", "+b")
        assert negado_en_codex(M.correr(codex(texto, agent_id="a8"), raiz=w.raiz, plazo=25, host="codex")), "control en Codex"
        antes = w.marcas()
        apagar(w.raiz, ["verificar_capa"])
        assert w.correr(evento(malo)) == (0, "", b"")
        assert w.correr(a_escribir(w.sql, sesion="s7")) == (0, "", b"")
        assert w.correr(leer(w.sql, sesion="s8")) == (0, "", b"")
        assert w.correr(inicio_en("startup", w.raiz)) == (0, "", b"")
        assert M.correr(codex(texto, agent_id="a9"), raiz=w.raiz, plazo=25, host="codex") == (0, "", b"")
        assert w.marcas() == antes, w.marcas()
        os.remove(w.raiz / "workspace.local.json")
        assert w.correr(inicio("startup")) == (0, "", b""), "apagado tampoco avisa de la config rota"


def test_disabled_hooks_invalido_o_con_otros_hooks_no_apaga_verificar_capa():
    otros = ["guard_comandos", "revisar_turno", "writer_guard", "writer_stop"]
    with git_aislado(), Toque() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        malo = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        for i, valor in enumerate((otros, "verificar_capa", ["verificar_capa", "verificar_capa"], ["verificar-capa"], [None],
                                   {"verificar_capa": True})):
            apagar(w.raiz, valor)
            assert w.correr(evento(malo))[0] == 2, valor
            codigo, _, err = w.correr(a_escribir(w.sql, sesion="v%d" % i))
            assert codigo == 2 and (REGLA % "SQL").encode("utf-8") in err, (valor, err)


FALLAS = ".claude/estado/fallas-de-hooks.jsonl"


@contextlib.contextmanager
def decidir_que_falla(error):
    original = M.decidir

    def falla(*_args, **_kwargs):
        raise error

    M.decidir = falla
    try:
        yield
    finally:
        M.decidir = original


def fallas_anotadas(raiz):
    ruta = Path(raiz) / FALLAS
    return [json.loads(linea) for linea in ruta.read_bytes().splitlines()] if ruta.exists() else []


def test_una_falla_que_se_traga_correr_queda_anotada_sin_el_payload():
    with Toque() as w:
        secreto = "nombre-que-no-se-anota"
        with decidir_que_falla(RuntimeError("se rompió\n  " + "x" * 400)):
            assert w.correr(evento(w.db / "src" / (secreto + ".sql"))) == (0, "", b"")
        assert secreto.encode("utf-8") not in (w.raiz / FALLAS).read_bytes()
        [anotada] = fallas_anotadas(w.raiz)
        assert set(anotada) == {"id", "momento", "hook", "evento", "tipo", "mensaje"}, anotada
        assert (anotada["hook"], anotada["evento"], anotada["tipo"]) == ("verificar_capa", "PostToolUse", "RuntimeError"), anotada
        assert anotada["mensaje"].startswith("se rompió xxx") and anotada["mensaje"].endswith("...") and len(anotada["mensaje"]) == 203, anotada
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", anotada["momento"]), anotada


def test_el_inicio_muestra_una_sola_vez_las_fallas_anotadas_desde_el_ultimo_aviso():
    with Toque() as w:
        with decidir_que_falla(RuntimeError("la primera")):
            w.correr(leer(w.sql))
        texto = aviso_de(w.correr(inicio("startup"))[1])
        assert "verificar_capa (PostToolUse): RuntimeError: la primera" in texto and "/odd-ws:doctor" in texto, texto
        assert w.correr(inicio("resume")) == (0, "", b""), "ya se mostró"
        with decidir_que_falla(ValueError("la segunda")):
            w.correr(a_escribir(w.sql))
        texto = aviso_de(w.correr(inicio("compact"))[1])
        assert "PreToolUse): ValueError: la segunda" in texto and "la primera" not in texto, texto
        assert w.correr(inicio("clear")) == (0, "", b""), "ya se mostró"
        assert [a["mensaje"] for a in fallas_anotadas(w.raiz)] == ["la primera", "la segunda"], "mostrarlas no las borra"


def test_las_fallas_anotadas_tienen_tope_y_quedan_las_ultimas():
    from odd_ws import fallas
    with Toque() as w:
        for numero in range(fallas.TOPE + 5):
            with decidir_que_falla(RuntimeError("falla %d" % numero)):
                w.correr(evento(w.sql))
        assert [a["mensaje"] for a in fallas_anotadas(w.raiz)] == ["falla %d" % n for n in range(5, fallas.TOPE + 5)]


PORQUE_DE_LA_DIAN = "La DIAN rechaza tres decimales, así que se redondea"


def commitear_con_fecha(repo, mensaje, fecha):
    git(repo, "add", "-A")
    entorno = dict(_entorno_sin_git(), GIT_AUTHOR_DATE=fecha, GIT_COMMITTER_DATE=fecha)
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false",
                        "commit", "-q", "-F", "-"], cwd=str(repo), input=mensaje.encode("utf-8"), capture_output=True, env=entorno)
    if r.returncode != 0:
        raise RuntimeError("git commit fallo: %s" % r.stderr)
    return git(repo, "rev-parse", "HEAD")


class Porque(Mundo):
    def __init__(self, modo=None):
        super().__init__(db={"src/base.sql": "x\n"})
        self.modo = modo

    def __enter__(self):
        super().__enter__()
        if self.modo is not None:
            ruta = self.raiz / "workspace.config.json"
            config = json.loads(ruta.read_text(encoding="utf-8"))
            config["porque_al_editar"] = self.modo
            escribir(self.raiz, "workspace.config.json", json.dumps(config))
        self.ventas = self.db / "src" / "ventas.sql"
        self.hashes = {}
        lineas = ["linea %02d" % n for n in range(1, 21)]
        self.hashes["A"] = self.version(lineas, "base de ventas\n\nLa base que copia el SP de la central.\n", "2026-01-10T10:00:00+00:00")
        lineas[4:6] = ["redondeo 05", "redondeo 06"]
        self.hashes["B"] = self.version(lineas, "redondeo\n\nSe redondea a dos decimales porque la DIAN rechaza tres.\n\n"
                                                "Co-Authored-By: Otra <otra@x>\n", "2026-02-15T10:00:00+00:00")
        lineas[9] = "trailers 10"
        self.hashes["C"] = self.version(lineas, "solo trailers\n\nCo-Authored-By: Y <y@y>\nSigned-off-by: Z <z@z>\n",
                                        "2026-03-20T10:00:00+00:00")
        lineas[11] = "tope 12"
        self.hashes["D"] = self.version(lineas, "tope\n\nEl tope de 400 lo fija la norma de ventas.\nSegunda linea del cuerpo.\n",
                                        "2026-04-01T23:30:00-05:00")
        lineas[15] = "sin cuerpo 16"
        self.hashes["E"] = self.version(lineas, "solo el asunto\n", "2026-05-01T10:00:00+00:00")
        self.lineas = lineas
        return self

    def version(self, lineas, mensaje, fecha):
        escribir(self.db, "src/ventas.sql", "\n".join(lineas) + "\n")
        return commitear_con_fecha(self.db, mensaje, fecha)

    def desviacion(self, ini, fin, ruta="src/ventas.sql", hash_=None):
        hash_ = hash_ or self.hashes["B"][:7]
        fila = 'D-01,db:%s@%s:%d-%d,Redondeo a dos decimales,"%s",2026-02-15\n' % (ruta, hash_, ini, fin, PORQUE_DE_LA_DIAN)
        escribir(self.raiz, ".claude/reglas/desviaciones.csv", "id,ubicacion,resumen,porque,fecha\n" + fila)

    def linea(self, letra, cuerpo, fecha):
        return "%s %s: %s" % (fecha, self.hashes[letra][:7], cuerpo)


def editar(ruta, viejo, nombre="PostToolUse", **extra):
    e = evento(ruta, "Edit", nombre=nombre, **extra)
    e["tool_input"] = dict(e["tool_input"], old_string=viejo, new_string="NUEVO")
    return e


def preguntado(salida):
    codigo, out, err = salida
    if codigo != 0 or err != b"" or not out:
        return None
    decision = json.loads(out).get("hookSpecificOutput") or {}
    if (decision.get("hookEventName"), decision.get("permissionDecision")) != ("PreToolUse", "ask"):
        return None
    return decision.get("permissionDecisionReason")


@contextlib.contextmanager
def que_falle(modulo, nombre):
    original = getattr(modulo, nombre)

    def falla(*_args, **_kwargs):
        raise RuntimeError("el porqué se rompió")

    setattr(modulo, nombre, falla)
    try:
        yield
    finally:
        setattr(modulo, nombre, original)


def test_porque_la_pausa_pregunta_si_la_edicion_toca_una_desviacion_y_calla_si_no():
    with Porque() as w:
        w.desviacion(5, 6)
        motivo = preguntado(w.correr(editar(w.ventas, "linea 04\nredondeo 05\n", nombre="PreToolUse")))
        assert motivo is not None, motivo
        for pedazo in ("D-01", PORQUE_DE_LA_DIAN, "2026-02-15", "Redondeo a dos decimales", "src/ventas.sql", "5-6"):
            assert pedazo in motivo, (pedazo, motivo)
        assert w.correr(editar(w.ventas, "linea 08\nlinea 09", nombre="PreToolUse")) == (0, "", b""), "no toca la desviación"
        assert w.correr(editar(w.ventas, "no está en el archivo", nombre="PreToolUse")) == (0, "", b"")
        assert preguntado(w.correr(evento(w.ventas, "Write", nombre="PreToolUse"))) is not None, "un Write pisa el archivo entero"
        actual = w.ventas.read_text(encoding="utf-8")
        escribir(w.db, "src/ventas.sql", "nueva 1\nnueva 2\n" + actual)
        motivo = preguntado(w.correr(editar(w.ventas, "redondeo 06", nombre="PreToolUse")))
        assert motivo is not None and "7-8" in motivo, "la desviación se ubica por contenido, no por número de línea: %s" % motivo
        escribir(w.db, "src/ventas.sql", actual.replace("redondeo 05\nredondeo 06\n", "cinco\nseis\n"))
        assert w.correr(editar(w.ventas, "linea 04\ncinco", nombre="PreToolUse")) == (0, "", b""), "la desviación ya no está"
        w.desviacion(3, 4, hash_=w.hashes["A"][:7])
        multi = dict(editar(w.ventas, "linea 04", nombre="PreToolUse"), tool_name="MultiEdit")
        assert preguntado(w.correr(dict(multi, tool_name="Edit"))) is not None, "control: con Edit pregunta"
        assert w.correr(multi) == (0, "", b""), "MultiEdit sigue afuera"


def test_porque_sin_desviaciones_del_archivo_el_pre_no_corre_git():
    with Porque() as w:
        with SinSubprocess() as guardia:
            for e in (editar(w.ventas, "redondeo 05", nombre="PreToolUse"), evento(w.ventas, "Write", nombre="PreToolUse")):
                assert w.correr(e) == (0, "", b""), "sin desviaciones.csv"
            w.desviacion(5, 6, ruta="src/otro.sql")
            for e in (editar(w.ventas, "redondeo 05", nombre="PreToolUse"), evento(w.ventas, "Write", nombre="PreToolUse")):
                assert w.correr(e) == (0, "", b""), "con desviaciones de otro archivo"
            w.desviacion(5, 6)
            fuera = escribir(w.raiz, "notas/ventas.sql", "redondeo 05\n")
            assert w.correr(editar(fuera, "redondeo 05", nombre="PreToolUse")) == (0, "", b""), "un archivo fuera de los repos"
            assert w.correr(evento(w.db / "src" / "nuevo.sql", "Write", nombre="PreToolUse")) == (0, "", b""), "un archivo nuevo"
        assert not guardia.llamadas, guardia.llamadas


def test_porque_despues_de_editar_trae_fecha_hash_y_primera_linea_del_cuerpo_sin_trailers_y_hasta_dos():
    with Porque() as w:
        viejo = "\n".join(w.lineas[3:13])
        escribir(w.db, "src/ventas.sql", w.ventas.read_text(encoding="utf-8").replace(viejo, "NUEVO"))
        texto = contexto(w.correr(editar(w.ventas, viejo))[1])
        assert texto is not None, texto
        lineas = texto.split("\n")
        assert "src/ventas.sql" in lineas[0], lineas
        assert lineas[1:] == [w.linea("D", "El tope de 400 lo fija la norma de ventas. Segunda linea del cuerpo.", "2026-04-01"),
                              w.linea("B", "Se redondea a dos decimales porque la DIAN rechaza tres.", "2026-02-15")], lineas
        for afuera in ("Co-Authored-By", "Signed-off-by", "solo trailers", "redondeo\n"):
            assert afuera not in texto, (afuera, texto)
        texto = contexto(w.correr(editar(w.ventas, "linea 02"))[1])
        assert texto.split("\n")[1:] == [w.linea("A", "La base que copia el SP de la central.", "2026-01-10")], texto
        texto = contexto(w.correr(evento(w.ventas, "Write"))[1])
        assert texto.split("\n")[1:] == [w.linea("D", "El tope de 400 lo fija la norma de ventas. Segunda linea del cuerpo.", "2026-04-01"),
                                         w.linea("B", "Se redondea a dos decimales porque la DIAN rechaza tres.", "2026-02-15")], texto


def test_porque_un_commit_sin_cuerpo_o_con_solo_trailers_calla():
    with Porque() as w:
        for viejo in ("trailers 10", "sin cuerpo 16", "esto no está en HEAD"):
            assert w.correr(editar(w.ventas, viejo)) == (0, "", b""), viejo


def test_porque_un_timeout_o_un_error_de_git_dice_que_no_se_pudo_chequear():
    real = subprocess.run

    def lento(args, *a, **k):
        if "blame" in args:
            raise subprocess.TimeoutExpired(args, 1.5)
        return real(args, *a, **k)

    def roto(args, *a, **k):
        if "blame" in args:
            return subprocess.CompletedProcess(args, 128, b"", b"fatal: roto")
        return real(args, *a, **k)

    def sin_git(*_a, **_k):
        raise FileNotFoundError("git")

    with Porque() as w:
        for falso in (lento, roto, sin_git):
            with subprocess_falso(falso):
                texto = contexto(w.correr(editar(w.ventas, "redondeo 05"))[1])
            assert texto is not None and "no se pudo chequear el porqué de estas líneas" in texto, (falso.__name__, texto)
        texto = contexto(w.correr(editar(w.ventas, "redondeo 05"), plazo=0.000001)[1])
        assert texto is not None and "no se pudo chequear el porqué de estas líneas" in texto, "sin plazo: %s" % texto


def test_porque_un_archivo_sin_trackear_no_tiene_historia_y_uno_nuevo_calla():
    with Porque() as w:
        suelto = escribir(w.db, "src/suelto.sql", "uno\ndos\n")
        texto = contexto(w.correr(editar(suelto, "uno"))[1])
        assert texto is not None and "sin historia" in texto and "src/suelto.sql" in texto, texto
        assert "no se pudo chequear" not in texto, texto
        assert w.correr(evento(suelto, "Write")) == (0, "", b""), "un Write que crea el archivo calla"
        assert w.correr(evento(w.db / "src" / "no-existe.sql", "Write")) == (0, "", b"")
        assert w.correr(editar(w.db / "src" / "no-existe.sql", "uno")) == (0, "", b"")
    with Mundo() as w:
        sin_commits = escribir(w.db, "src/a.sql", "uno\n")
        assert "sin historia" in contexto(w.correr(editar(sin_commits, "uno"))[1]), "un repo sin commits tampoco tiene historia"


def test_porque_al_editar_prende_la_pausa_y_el_contexto_por_separado():
    for modo, pausa, con_contexto in ((None, True, True), ("todo", True, True), ("indice", True, False), ("apagado", False, False),
                                      ("off", True, True)):
        with Porque(modo) as w:
            w.desviacion(5, 6)
            pre = w.correr(editar(w.ventas, "redondeo 05", nombre="PreToolUse"))
            assert (preguntado(pre) is not None) == pausa and (pausa or pre == (0, "", b"")), (modo, pre)
            post = w.correr(editar(w.ventas, "redondeo 05"))
            assert (contexto(post[1]) is not None) == con_contexto and (con_contexto or post == (0, "", b"")), (modo, post)
            if modo == "apagado":
                with SinSubprocess() as guardia:
                    w.correr(editar(w.ventas, "redondeo 05", nombre="PreToolUse"))
                    w.correr(editar(w.ventas, "redondeo 05"))
                assert not guardia.llamadas, guardia.llamadas


def test_porque_una_falla_del_subchequeo_no_borra_el_primer_toque_ni_los_hallazgos():
    with Toque() as w:
        escribir(w.db, "src/Proc_X.sql", "a\n")
        esperado = w.correr(editar(w.sql, "a", nombre="PreToolUse", session_id="s1"))
        assert esperado[0] == 2 and b"primer toque (capa-sql)" in esperado[2], esperado
        with que_falle(M.porque, "pausa"):
            assert w.correr(editar(w.sql, "a", nombre="PreToolUse", session_id="s2")) == esperado
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        esperado = w.correr(evento(ruta))
        assert esperado[0] == 2 and "sin historia".encode("utf-8") not in esperado[2], esperado
        with que_falle(M.porque, "contexto"):
            assert w.correr(editar(ruta, "int a;")) == esperado
        codigo, _, err = w.correr(editar(ruta, "int a;"))
        assert codigo == 2 and err.startswith(esperado[2].rstrip(b"\n")) and b"sin historia" in err, err


def anotada_de(raiz):
    [anotada] = fallas_anotadas(raiz)
    return anotada["hook"], anotada["evento"], anotada["tipo"], anotada["mensaje"]


def test_porque_una_falla_del_subchequeo_queda_anotada_y_el_veredicto_no_cambia():
    with git_aislado(), Toque() as w:
        escribir(w.db, "src/Proc_X.sql", "a\n")
        esperado = w.correr(editar(w.sql, "a", nombre="PreToolUse", session_id="s1"))
        assert esperado[0] == 2 and fallas_anotadas(w.raiz) == [], esperado
        with que_falle(M.porque, "pausa"):
            assert w.correr(editar(w.sql, "a", nombre="PreToolUse", session_id="s2")) == esperado
        assert anotada_de(w.raiz) == ("verificar_capa", "PreToolUse", "RuntimeError", "el porqué se rompió")
    with git_aislado(), Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        ruta = escribir(w.web, "Core/A.cs", "int a; // MALO BLOQ\n")
        esperado = w.correr(evento(ruta))
        with que_falle(M.porque, "contexto"):
            assert w.correr(editar(ruta, "int a;")) == esperado
        assert anotada_de(w.raiz) == ("verificar_capa", "PostToolUse", "RuntimeError", "el porqué se rompió")


def test_codex_un_archivo_del_parche_que_revienta_queda_anotado_y_los_otros_deciden_igual():
    with git_aislado(), Mundo() as w:
        w.modulo("web", STUB_MALO)
        w.calibrar("web")
        escribir(w.web, "Core/A.cs", "a = MALO BLOQ;\n")
        escribir(w.web, "Core/B.cs", "b = 1;\n")
        texto = parche_codex("*** Update File: Core/B.cs", "@@", "+b = 1;", "*** Update File: Core/A.cs", "@@", "+a = MALO BLOQ;")
        esperado = M.correr(codex(texto, "PostToolUse", cwd=w.web), raiz=w.raiz, plazo=25, host="codex")
        assert "Core/A.cs tiene 1 problema(s)" in (bloqueado_en_codex(esperado) or ""), esperado
        original = M._verificar_ruta

        def revienta_en_b(una, config):
            if una.rutas[0].endswith("B.cs"):
                raise RuntimeError("B se rompió")
            return original(una, config)

        M._verificar_ruta = revienta_en_b
        try:
            assert M.correr(codex(texto, "PostToolUse", cwd=w.web), raiz=w.raiz, plazo=25, host="codex") == esperado
        finally:
            M._verificar_ruta = original
        assert anotada_de(w.raiz) == ("verificar_capa", "PostToolUse", "RuntimeError", "B se rompió")


def test_inicio_una_falla_del_aviso_de_plantillas_queda_anotada_y_los_demas_avisos_salen_en_orden():
    with git_aislado(), Toque() as w, plugin_actualizado(w.raiz) as (local, datos, vieja, vigente):
        con_plantillas_del_salto(w.raiz, vigente, "viejas")
        escribir(w.raiz, "tickets/T-7-algo/CLAUDE.md", TICKET_ACTIVO)
        marcar_activo(w.raiz, "tickets/T-7-algo")
        original = M.plantillas_instancia.aviso_de_inicio

        def rota(*_a, **_k):
            raise RuntimeError("las plantillas se rompieron")

        M.plantillas_instancia.aviso_de_inicio = rota
        try:
            codigo, out, err = w.correr(inicio_en("startup", w.raiz))
        finally:
            M.plantillas_instancia.aviso_de_inicio = original
        assert codigo == 0 and err == b"", (codigo, err)
        texto = aviso_de(out)
        anotada = "- %s verificar_capa (SessionStart): RuntimeError: las plantillas se rompieron" % fallas_anotadas(w.raiz)[0]["momento"]
        partes = ["apuntaba a la versión 0.13.1", "desde el último aviso hubo 1 falla", anotada, ENCABEZADO_DEL_RESUMEN]
        posiciones = [texto.find(parte) for parte in partes]
        assert -1 not in posiciones and posiciones == sorted(posiciones), (posiciones, texto)
        assert "cambiaron plantillas" not in texto and texto.endswith(CIERRE_DEL_TICKET), texto
        assert anotada_de(w.raiz) == ("verificar_capa", "SessionStart", "RuntimeError", "las plantillas se rompieron")


def test_porque_en_codex_la_pausa_bloquea_con_el_texto_de_una_edicion_y_el_contexto_llega_en_post():
    from odd_ws.hosts import codex as adaptador
    with git_aislado(), Porque() as w:
        w.desviacion(5, 6)
        texto = parche_codex("*** Update File: %s" % w.ventas, "@@", " linea 04", "-redondeo 05", "+cinco")
        motivo = negado_en_codex(M.correr(codex(texto), raiz=w.raiz, plazo=25, host="codex"))
        assert motivo is not None and "D-01" in motivo and PORQUE_DE_LA_DIAN in motivo, motivo
        assert motivo.endswith(adaptador.SIN_CONFIRMACION_DE_EDICION) and "comando" not in motivo, motivo
        lejos = parche_codex("*** Update File: %s" % w.ventas, "@@", "-linea 08", "+ocho")
        assert M.correr(codex(lejos), raiz=w.raiz, plazo=25, host="codex") == (0, "", b"")
        salida = M.correr(codex(texto, nombre="PostToolUse"), raiz=w.raiz, plazo=25, host="codex")
        texto_post = (_json_de_codex(salida) or {}).get("hookSpecificOutput", {}).get("additionalContext")
        assert texto_post is not None and w.linea("B", "Se redondea a dos decimales porque la DIAN rechaza tres.", "2026-02-15") in texto_post, salida


def pi_evento(tipo, herramienta, entrada, cwd, pantalla=False):
    return {"type": tipo, "toolName": herramienta, "input": entrada, "ctx": {"cwd": str(cwd), "sessionId": "s1", "hasUI": pantalla,
                                                                              "mode": "tui"},
            "oddWs": {"agent": None, "agentId": None, "lastAssistantMessage": "", "continued": False}}


def test_porque_en_pi_la_pausa_pregunta_con_pantalla_y_sin_ella_bloquea_con_el_texto_de_una_edicion():
    from odd_ws.hosts import pi as adaptador
    with git_aislado(), Porque() as w:
        w.desviacion(5, 6)
        entrada = {"path": str(w.ventas), "edits": [{"oldText": "redondeo 05", "newText": "cinco"}]}
        for pantalla, accion in ((True, "preguntar"), (False, "bloquear")):
            codigo, salida, error = M.correr(pi_evento("tool_call", "edit", entrada, w.raiz, pantalla), raiz=w.raiz, plazo=25, host="pi")
            datos = json.loads(salida)
            assert (codigo, error, datos["accion"]) == (0, b"", accion) and PORQUE_DE_LA_DIAN in datos["texto"], (pantalla, salida)
            assert pantalla or datos["texto"].endswith(adaptador.SIN_PANTALLA_DE_EDICION), datos
        sin_texto = {"path": str(w.ventas), "edits": [{"newText": "cinco"}]}
        assert M.correr(pi_evento("tool_call", "edit", sin_texto, w.raiz), raiz=w.raiz, plazo=25, host="pi") == (0, "", b"")
        codigo, salida, _ = M.correr(pi_evento("tool_result", "edit", entrada, w.raiz), raiz=w.raiz, plazo=25, host="pi")
        datos = json.loads(salida)
        assert datos["accion"] == "contexto" and "2026-02-15" in datos["texto"], datos


SP_CON_DOS_CATCH = """CREATE PROCEDURE ventas.registrar_venta
AS
BEGIN
    BEGIN TRY
        EXEC ventas.encolar_envio @Id
    END TRY
    BEGIN CATCH
    END CATCH

    BEGIN TRY
        UPDATE dbo.Venta SET Estado = 2 WHERE Id = @Id
    END TRY
    BEGIN CATCH
    END CATCH
END
"""
PRIMER_CATCH = "        EXEC ventas.encolar_envio @Id\n    END TRY\n    BEGIN CATCH\n    END CATCH"
SEGUNDO_CATCH = "        UPDATE dbo.Venta SET Estado = 2 WHERE Id = @Id\n    END TRY\n    BEGIN CATCH\n    END CATCH"


def parche_del_catch(ruta, catch):
    lineas = catch.split("\n")
    return parche_codex("*** Update File: %s" % ruta, "@@", *(" " + linea for linea in lineas[:-1]), "+        THROW;", " " + lineas[-1])


def test_porque_la_pausa_mira_solo_la_copia_de_la_desviacion_y_no_las_iguales():
    with git_aislado(), Porque() as w:
        sp = escribir(w.db, "src/sp.sql", SP_CON_DOS_CATCH)
        hash_ = commitear_con_fecha(w.db, "sp\n\nEl encolado a SAP no aborta la venta.\n", "2026-06-01T10:00:00+00:00")
        w.desviacion(6, 8, ruta="src/sp.sql", hash_=hash_[:7])
        for arriba, hoy in ((0, "6-8"), (2, "8-10")):
            escribir(w.db, "src/sp.sql", "-- arriba\n" * arriba + SP_CON_DOS_CATCH)
            assert w.correr(editar(sp, SEGUNDO_CATCH, nombre="PreToolUse")) == (0, "", b""), (arriba, "Claude Code: la otra copia no pausa")
            otra = M.correr(codex(parche_del_catch(sp, SEGUNDO_CATCH)), raiz=w.raiz, plazo=25, host="codex")
            assert otra == (0, "", b""), (arriba, "Codex: la otra copia no bloquea", otra)
            motivo = preguntado(w.correr(editar(sp, PRIMER_CATCH, nombre="PreToolUse")))
            assert motivo is not None and "hoy en las líneas %s (" % hoy in motivo, (arriba, motivo)
            motivo = negado_en_codex(M.correr(codex(parche_del_catch(sp, PRIMER_CATCH)), raiz=w.raiz, plazo=25, host="codex"))
            assert motivo is not None and "hoy en las líneas %s (" % hoy in motivo, (arriba, motivo)


def test_porque_la_pausa_de_una_desviacion_de_una_linea_no_alcanza_a_sus_copias():
    lineas = ["-- linea %02d" % n for n in range(1, 36)]
    lineas[19:21] = ["    SELECT 1", "END"]
    lineas[29:31] = ["    SELECT 2", "END"]
    with Porque() as w:
        sp = escribir(w.db, "src/dos.sql", "\n".join(lineas) + "\n")
        hash_ = commitear_con_fecha(w.db, "dos\n\nEl primer END cierra el SP viejo.\n", "2026-06-01T10:00:00+00:00")
        w.desviacion(21, 21, ruta="src/dos.sql", hash_=hash_[:7])
        assert w.correr(editar(sp, "    SELECT 2\nEND", nombre="PreToolUse")) == (0, "", b""), "el END de la línea 31 no es la desviación"
        motivo = preguntado(w.correr(editar(sp, "    SELECT 1\nEND", nombre="PreToolUse")))
        assert motivo is not None and "hoy en las líneas 21-21 (" in motivo, motivo


def test_porque_el_blame_ignora_los_espacios_y_no_busca_copias_entre_archivos():
    real, llamadas = subprocess.run, []

    def anotado(args, *a, **k):
        if "blame" in args:
            llamadas.append(list(args))
        return real(args, *a, **k)

    with Porque() as w:
        with subprocess_falso(anotado):
            texto = contexto(w.correr(editar(w.ventas, "redondeo 05"))[1])
        assert texto is not None and len(llamadas) == 1, (texto, llamadas)
        blame = llamadas[0][llamadas[0].index("blame"):]
        assert "-w" in blame and not any(a.startswith("-C") or a.startswith("-M") for a in blame), blame


def test_porque_el_porque_es_el_primer_parrafo_o_su_primera_vineta_en_una_linea_y_sin_los_trailers_conocidos():
    palabras = ["pa%03d" % n for n in range(50)]
    largo = "\n".join(" ".join(palabras[n:n + 10]) for n in range(0, 50, 10))
    commits = (
        ("uno", "envuelto\n\n- Después de editar, el hook muestra la fecha y una línea del cuerpo de\n  cada commit que escribió esas líneas.\n"
                "- La segunda viñeta no entra.\n\nCo-Authored-By: Y <y@y>\n",
         "Después de editar, el hook muestra la fecha y una línea del cuerpo de cada commit que escribió esas líneas."),
        ("dos", "motivo\n\nMotivo: la DIAN rechaza X\n", "Motivo: la DIAN rechaza X"),
        ("tres", "largo\n\n" + largo + "\n\nEl segundo párrafo no entra.\n\nreviewed-by: Z <z@z>\nSigned-off-by: Q <q@q>\n",
         " ".join(palabras[:33]) + "…"),
        ("cuatro", "mezcla\n\nNota: va así por la DIAN\nco-authored-by: Y <y@y>\n", "Nota: va así por la DIAN"),
    )
    with Porque() as w:
        archivo, hashes = w.db / "src" / "motivo.sql", []
        for n, (_, mensaje, _) in enumerate(commits, 1):
            escribir(w.db, "src/motivo.sql", "".join(linea + "\n" for linea, _, _ in commits[:n]))
            hashes.append(commitear_con_fecha(w.db, mensaje, "2026-06-0%dT10:00:00+00:00" % n))
        for n, ((viejo, _, porque), hash_) in enumerate(zip(commits, hashes), 1):
            texto = contexto(w.correr(editar(archivo, viejo))[1])
            assert texto is not None and texto.split("\n")[1:] == ["2026-06-0%d %s: %s" % (n, hash_[:7], porque)], (viejo, texto)
            assert "no entra" not in texto and "-by" not in texto.lower(), texto


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
