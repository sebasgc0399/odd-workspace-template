import contextlib
import importlib.util
import json
import os
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

STUB_MALO = '''def verificar(ctx):
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

STUB_ALCANCE = '''def verificar(ctx):
    if (ctx["relativa_repo"] or "").startswith("src/legado/"):
        return []
    return [{"id": "T-05", "modo": "bloqueo", "severidad": "CRITICAL", "linea": n, "fragmento": "XX", "mensaje": "XX fuera del legado"}
            for n, t in ctx["agregadas"] if "XX" in t]
'''

STUB_IMPORTA_LA_BIBLIOTECA = '''from odd_ws.comun import lineas
def verificar(ctx):
    return [{"id": "T-06", "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "lineas de la biblioteca: \\u00f1 %d" % len(lineas(ctx["texto"]))}
            for n, t in ctx["agregadas"] if "MALO" in t]
'''

PROC = "CREATE PROC Proc_A\nAS\nBEGIN\n\tSELECT 1;\nEND\n"


class Mundo:
    def __init__(self, base_sql=True, db=None):
        self.base_sql = base_sql
        self.db_archivos = db

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="verificar-capa-test-"))
        self.raiz = self.base / "inst"
        self.raiz.mkdir()
        git(self.raiz, "init", "-q")
        escribir(self.raiz, "README.md", "x\n")
        commitear(self.raiz, "base")
        self.web = self.base / "repos" / "web"
        self.web.mkdir(parents=True)
        git(self.web, "init", "-q")
        self.db = self.base / "repos" / "db"
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


def test_sin_instancia_o_con_config_rota_calla():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
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
        assert "linea 1:" not in contexto, contexto
        assert "linea 4:" in contexto and "linea 5:" in contexto, contexto
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
        assert "tiene 1 aviso(s)" in contexto and "linea 2:" in contexto and "linea 1:" not in contexto, contexto


def test_salida_con_bloqueo_exit_2_stderr_en_bytes_utf8():
    with Mundo() as w:
        escribir(w.web, "Core/Base.cs", "x\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/N.cs", "a // MALO\nb // MALO BLOQ\nc\n")
        w.modulo("web", STUB_MALO)
        codigo, out, err = w.correr(evento(ruta))
        assert codigo == 2 and out == "" and isinstance(err, bytes)
        lineas = err.decode("utf-8").rstrip("\n").split("\n")
        assert lineas[0] == "verificar-capa: Core/N.cs tiene 2 problema(s): corregir y reintentar.", lineas[0]
        assert lineas[1] == "[T-02 CRITICAL] linea 2: está mal → así, molde: x/y.cs", lineas[1]
        assert lineas[2] == "[T-02 CRITICAL] linea 1: está mal → así, molde: x/y.cs", lineas[2]
        assert len(lineas) == 3, lineas


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
        assert codigo == 0 and "linea 2:" in out, (codigo, err)
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
        legado = w.taller("esq.Proc_A.sql", PROC.replace("\tSELECT 1;\n", "\tSELECT 1;\n\tXX;\n"))
        nuevo = w.taller("esq.Proc_B.sql", PROC.replace("Proc_A", "Proc_B").replace("\tSELECT 1;\n", "\tSELECT 1;\n\tXX;\n"))
        assert w.correr(evento(legado, "Write")) == (0, "", b"")
        codigo, _, err = w.correr(evento(nuevo, "Write"))
        assert codigo == 2 and b"[T-05 CRITICAL] linea 5:" in err, (codigo, err)


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


def test_post_tool_use_usa_la_funcion_publica_sin_cambiar_la_salida():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
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


def test_sin_tiempo_para_git_falla_abierto_sin_colgarse():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
        escribir(w.web, "Core/A.cs", "uno\n")
        commitear(w.web)
        ruta = escribir(w.web, "Core/A.cs", "uno\ndos MALO\n")
        assert w.correr(evento(ruta), plazo=-1) == (0, "", b"")
        assert w.correr(evento(ruta), plazo=25)[0] == 0 and "linea 2:" in w.correr(evento(ruta), plazo=25)[1]


def test_la_raiz_sale_de_la_sesion_si_no_se_pasa():
    with Mundo() as w:
        w.modulo("web", STUB_MALO)
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
                  ("PreToolUse", "Write"), ("SessionStart", "compact"), ("SessionStart", "clear")):
        assert clave in cableados, (clave, cableados)
    for clave in (("PostToolUse", "Read"), ("PreToolUse", "Edit"), ("PreToolUse", "Write"), ("SessionStart", "compact")):
        assert cableados[clave] == (10, 8), (clave, cableados[clave])
    assert ("SessionStart", "startup") not in cableados and ("SessionStart", "resume") not in cableados


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
