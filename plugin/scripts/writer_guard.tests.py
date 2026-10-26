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
_RUTA = AQUI / "writer_guard.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
NT = os.name == "nt"

import config_loader  # noqa: E402
from odd_ws import capas as convencion  # noqa: E402


def _cargar():
    spec = importlib.util.spec_from_file_location("writer_guard", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


G = _cargar() if _RUTA.exists() else None


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def _borrar(carpeta):
    shutil.rmtree(carpeta, onexc=_quitar)
    if Path(carpeta).exists():
        SOBRANTES.append(str(carpeta))


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno_sin_git())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def fw(p):
    return str(p).replace("\\", "/")


def bw(p):
    return str(p).replace("/", "\\")


def gb(p):
    s = fw(p)
    return "/" + s[0].lower() + s[2:] if re.match(r"[A-Za-z]:/", s) else s


BASE = Path(tempfile.mkdtemp(prefix="guarda-test-"))
EQUIPO = BASE / "equipo"
DB, WEB, MOVIL = EQUIPO / "db", EQUIPO / "web", EQUIPO / "movil"
WT = EQUIPO / "worktrees" / "movil--x"
INST = BASE / "inst"
TMPD = BASE / "tmp"
SCRATCH_BASE = TMPD / "claude"
TALLER_DIR = INST / "tickets" / "T-123-x" / "SQL"

CONFIG = {
    "schema_version": 1,
    "repos": {"db": {}, "web": {}, "movil": {}},
    "layers": {
        "sql": {"extensions": [".sql"], "repos": ["db"], "workshop": ["tickets/**/T-[0-9]*/SQL/esq.*.sql"]},
        "web": {"extensions": [".cs"], "repos": ["web"]},
        "movil": {"extensions": [".java", ".xml"], "repos": ["movil"], "match": ["**/*.java", "**/res/**/*.xml"]},
    },
}


def _armar():
    for repo in (DB, WEB, MOVIL):
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
    (MOVIL / "README.md").write_text("x\n", encoding="utf-8")
    git(MOVIL, "add", "-A")
    git(MOVIL, "commit", "-q", "-m", "base")
    git(MOVIL, "worktree", "add", "-q", "-b", "x", str(WT))
    TALLER_DIR.mkdir(parents=True)
    TMPD.mkdir()
    (INST / "workspace.config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    local = {"repos": {"db": {"path": str(DB)}, "web": {"path": str(WEB)}, "movil": {"path": str(MOVIL)}}}
    (INST / "workspace.local.json").write_text(json.dumps(local), encoding="utf-8")


_armar()

ENTORNO = {"TEMP": str(TMPD), "TMP": str(TMPD), "TMPDIR": str(TMPD), "HOME": str(BASE), "USERPROFILE": str(BASE),
           "REPOS": str(EQUIPO), "PWD": str(DB)}
ZONAS = G.Zonas(config_loader.cargar(INST), ENTORNO) if G else None

JAVA = fw(MOVIL / "app/src/main/java/com/x/A.java")
JAVA_W = bw(JAVA)
CS = fw(WEB / "Core/A/B.cs")
SQL = fw(DB / "Current/esq.Proc_X.sql")
TALLER = fw(TALLER_DIR / "esq.Proc_A.sql")
TALLER_W = bw(TALLER)
SCRATCH = bw(SCRATCH_BASE / "c--x/sesion/scratchpad/u1/salida.txt")
SCRATCH_FW = fw(SCRATCH)
REPO_CWD = bw(DB)


def esperar(fallos, cond, msg):
    if not cond:
        fallos.append("  " + msg)


def tabla(casos, debe_bloquear, cwd=None, zonas=None):
    fallos = []
    for comando in casos:
        motivo = G.analizar(comando, cwd, ZONAS if zonas is None else zonas)
        donde = " (cwd %s)" % cwd if cwd else ""
        if debe_bloquear:
            esperar(fallos, bool(motivo), "deberia bloquear y paso%s: %s" % (donde, comando))
        else:
            esperar(fallos, motivo is None, "deberia pasar y bloqueo (%s)%s: %s" % (motivo, donde, comando))
    return fallos


def con_cwd(casos, cwd, debe_bloquear):
    return tabla(casos, debe_bloquear, cwd)


def comprobar(*listas):
    fallos = [f for lista in listas for f in lista]
    assert not fallos, "\n" + "\n".join(fallos)


GIT_BLOQUEA = [
    "git add .", "git add -A", "git commit -m x", "git commit --amend --no-edit", "git push",
    "git push -u origin rama-x", "git checkout rama", "git checkout -- f.cs", "git switch -c nueva",
    "git stash", "git stash pop", "git stash push -m x", "git restore f.cs", "git restore --staged f.cs",
    "git reset --hard", "git reset HEAD~1", "git rebase master", "git merge rama", "git cherry-pick abc123",
    "git clean -fd", "git rm f.cs", "git mv a.cs b.cs", "git worktree add ../x rama", "git worktree remove ../x",
    "git pull", "git revert abc", "git apply parche.diff", "git am parche.mbox",
]


def test_git_de_escritura_bloquea():
    comprobar(tabla(GIT_BLOQUEA, True))


def test_git_de_escritura_con_opciones_globales():
    comprobar(tabla([
        "git -C " + fw(MOVIL) + " commit -m y", "git -C C:\\x\\y add -A", "git -c user.name=a commit -m y",
        "git -c user.name=a -c user.email=b commit -m y", "git --no-pager -C d push", "git --git-dir=.git --work-tree=. add .",
        "git --git-dir .git add .", "git -C d -c k=v checkout x", "/usr/bin/git commit -m x", "git.exe commit -m x",
        '"C:\\Program Files\\Git\\cmd\\git.exe" commit -m x', '& "C:\\Program Files\\Git\\cmd\\git.exe" push',
    ], True))


def test_git_de_escritura_encadenado():
    comprobar(tabla([
        "cd X && git commit -m y", "echo a; git push", "git status || git add .", "git diff | git apply",
        "git status\ngit commit -m x", "cd C:/x; git add .; git commit -m y", "echo ok & git push",
        "(git add .) && echo listo", "true && { git commit -m x; }", "FOO=1 git commit -m x", "env GIT_X=1 git commit -m x",
        "time git commit -m x", "xargs git add", "ls | xargs -n1 git add", "nohup git push",
    ], True))


def test_git_de_escritura_desde_otro_shell_o_sustitucion():
    comprobar(tabla([
        'bash -c "git commit -m x"', "bash -lc 'git push'", 'sh -c "cd x && git add ."',
        'powershell -Command "git push"', "powershell.exe -NoProfile -Command git commit -m x", "pwsh -c 'git add .'",
        "cmd /c git commit -m x", 'cmd.exe /c "git push"', "echo $(git commit -m x)", "echo `git add .`",
        'bash -c "echo \\"a\\"; git push"',
    ], True))


GIT_PASA = [
    "git status", "git status -s", "git diff", "git diff --stat HEAD", "git diff --no-index a b", "git log", "git log --oneline -5",
    "git log --grep commit", "git log --grep=push -n 3", "git log --author add", "git show HEAD:f.cs", "git grep push",
    "git grep -n commit -- '*.cs'", "git fetch origin", "git fetch --all --prune", "git rev-parse HEAD",
    "git rev-parse --show-toplevel", "git -C " + fw(DB) + " status", "git -c core.quotepath=off diff",
    "git stash list", "git stash show -p", "git worktree list", "git branch -a", "git ls-files", "git ls-tree -r origin/master",
    "git cat-file -p HEAD:f", "git blame f.cs", "git merge-base HEAD origin/master", "git config user.name",
    "git diff --numstat HEAD -- f.cs", "git remote -v", "git describe --tags", "git show-ref",
]


def test_git_de_lectura_pasa():
    comprobar(tabla(GIT_PASA, False))


def test_los_enganosos_no_son_git_de_escritura():
    comprobar(tabla([
        'grep -r "push" .', "grep -rn commit src", "rg checkout", 'echo "git commit"', "echo 'git push -u origin x'",
        "cat notas.md | grep 'git add'", "python tools/commit-helper.py", "dotnet test Tests.csproj --filter commit",
        'git log --format=%s | grep "restore"', "ls commit", "type push.txt", "findstr /s reset *.md",
    ], False))


SHELL_BLOQUEA = [
    "echo x > " + JAVA, "echo x >> " + CS, "echo x > " + JAVA_W, "echo x 1> " + SQL, "echo x >" + CS, "echo x &> " + SQL,
    'echo x > "' + fw(DB) + '/Current/a b.sql"', "echo x > " + gb(CS), "echo x > " + bw(DB) + "\\notas.txt",
    "echo x > " + TALLER, "echo x >> " + TALLER_W, "echo x > " + gb(TALLER),
    "cat a | tee " + CS, "cat a | tee -a " + JAVA_W, 'echo x | tee "' + bw(DB) + '\\a b.txt"',
    "sed -i 's/a/b/' " + CS, "sed -i.bak s/a/b/ " + JAVA, "sed -ni 's/a/b/p' " + SQL, "sed --in-place s/a/b/ " + CS,
    "Set-Content -Path " + JAVA_W + " -Value a", "Set-Content " + TALLER_W + " a", "Add-Content " + JAVA_W + " a",
    '"x" | Out-File ' + JAVA_W, "Out-File -FilePath " + CS + " -InputObject x", "Clear-Content " + JAVA_W,
    "cp scratch.txt " + CS, "cp -r a/ " + gb(DB) + "/a", "copy a.txt " + JAVA_W, "Copy-Item a.txt " + JAVA_W,
    "Copy-Item -Path a.txt -Destination " + CS, "mv a.txt " + CS, "mv " + CS + " /tmp/a.cs", "Move-Item a.txt " + JAVA_W,
    "Move-Item " + JAVA_W + " x.java", "rm " + CS, "rm -rf " + fw(DB) + "/Current", "del " + JAVA_W,
    "Remove-Item -Recurse -Force " + JAVA_W, "New-Item -ItemType File -Path " + JAVA_W, "ni " + CS, "touch " + CS,
    "Rename-Item " + JAVA_W + " B.java", "cd " + fw(MOVIL) + " && echo x > app/A.java",
    "cd " + bw(MOVIL) + "; Set-Content app\\A.java x", "Set-Location " + fw(DB) + "; rm Current/x.sql",
    'bash -c "echo x > ' + CS + '"', 'powershell -Command "Set-Content ' + JAVA_W + ' x"', "echo $(echo x > " + CS + ")",
    "echo ok && echo x > " + CS, "echo ok; sed -i s/a/b/ " + JAVA,
] + (["echo x > " + bw(DB).lower() + "\\notas.txt", "echo x > " + fw(DB).upper() + "/notas.txt"] if NT else [])


def test_escritura_por_shell_a_capa_o_repos_declarados_bloquea():
    comprobar(tabla(SHELL_BLOQUEA, True))


SHELL_PASA = [
    "cp " + CS + " scratch/B.cs", "Copy-Item " + JAVA_W + " " + SCRATCH, "copy " + SQL + " " + SCRATCH,
    "echo x > " + SCRATCH, "echo x >> " + SCRATCH_FW, "echo x > " + gb(SCRATCH_BASE / "c--x/s/a.txt"),
    "echo x > /dev/null", "echo x > NUL", "ls 2>&1", "ls > salida.txt", "ls | tee salida.txt", "sed -i s/a/b/ salida.txt",
    "sed -i s/a/b/ " + fw(BASE / "home/scratch/f.txt"), "sed -n 1,5p " + SQL, "sed s/a/b/ " + CS, "cat " + CS, "type " + JAVA_W,
    "Get-Content " + JAVA_W, "Get-Content " + JAVA_W + " | Select-Object -First 5", "Select-String -Path " + CS + " -Pattern x",
    "Get-ChildItem " + bw(EQUIPO), "ls " + fw(DB), "rm scratch.txt", "rm " + SCRATCH,
    "Remove-Item " + SCRATCH, "mv a.txt b.txt", "Set-Content salida.txt x", "Out-File -FilePath " + SCRATCH,
    "New-Item -ItemType File -Path " + SCRATCH, "echo 'a > b'", 'grep -n ">" ' + CS, 'echo "x > ' + CS + '"',
    "mkdir -p " + SCRATCH.replace("salida.txt", "d"), "cd " + fw(INST) + " && echo x > notas.txt",
    "cd " + fw(INST / "tickets/T-123-x") + "; Set-Content README.txt x",
]


def test_escritura_por_shell_que_pasa():
    comprobar(tabla(SHELL_PASA, False))


BUILDS_PASA = [
    "python plugin/scripts/normalizar_sql.py --fix " + SQL, "python normalizar_sql.py --fix " + TALLER,
    "python plugin/scripts/normalizar_sql.py --check " + SQL, r".\gradlew.bat :core:test",
    "./gradlew :app:assembleDebug", r"$env:JAVA_HOME='C:\jbr'; .\gradlew.bat :core:test", "dotnet test Tests/Tests.csproj",
    "dotnet build App.sln -c Release", "dotnet restore", "python plugin/scripts/writer_guard.tests.py",
    "python plugin/scripts/verificar_capa.tests.py", "python x.tests.py > " + SCRATCH,
    "python plugin/scripts/doctor.py", "msbuild X.sln", "mvn -q test",
]


def test_builds_tests_y_normalizador_pasan():
    comprobar(tabla(BUILDS_PASA, False))


def evento_bash(comando, **extra):
    e = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "s1", "cwd": str(INST),
         "agent_type": "writer-sql", "tool_input": {"command": comando}}
    e.update(extra)
    return e


def correr(e, raiz=INST, **extra):
    return G.correr(e, raiz=str(raiz), **extra)


def test_bloqueo_exit_2_stderr_en_bytes_utf8_y_stdout_vacio():
    fallos = []
    c, o, e = correr(evento_bash("cd X && git commit -m y"))
    esperar(fallos, c == 2 and o == "" and isinstance(e, bytes), "bloquea con exit 2: %r %r %r" % (c, o, e))
    texto = e.decode("utf-8") if isinstance(e, bytes) else ""
    esperar(fallos, "git commit" in texto, "dice que bloqueo: %r" % texto)
    esperar(fallos, "Edit" in texto and "Write" in texto, "dice que use Edit o Write: %r" % texto)
    esperar(fallos, any(ord(ch) > 127 for ch in texto), "lleva tildes enteras (utf-8): %r" % texto)
    c, o, e = correr(evento_bash("echo x > " + CS))
    esperar(fallos, c == 2 and CS in e.decode("utf-8"), "la escritura por shell nombra la ruta: %r %r" % (c, e))
    comprobar(fallos)


def test_lo_que_pasa_sale_en_silencio():
    fallos = []
    for comando in ("git status", 'grep -r "push" .', "dotnet test X.csproj"):
        esperar(fallos, correr(evento_bash(comando)) == (0, "", b""), "%s sale en silencio" % comando)
    comprobar(fallos)


def test_otras_herramientas_y_eventos_sin_comando_callan():
    fallos = []
    sin_comando = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "agent_type": "writer-sql", "tool_input": {}}
    casos = [
        dict(evento_bash("git commit"), tool_name="Edit"),
        dict(evento_bash("git commit"), tool_name="Read"),
        sin_comando,
        dict(sin_comando, tool_input={"command": 7}),
        {k: v for k, v in sin_comando.items() if k != "tool_input"},
        dict(evento_bash("git commit"), hook_event_name="PostToolUse"),
        [], "no es json", None, 5,
    ]
    for caso in casos:
        esperar(fallos, correr(caso) == (0, "", b""), "%r sale en silencio" % (caso,))
    esperar(fallos, correr(json.dumps(evento_bash("git push")).encode("utf-8"))[0] == 2, "acepta el evento como bytes JSON")
    esperar(fallos, correr(dict(evento_bash("git push"), tool_name="PowerShell"))[0] == 2, "PowerShell tambien se guarda")
    sin_evento = {k: v for k, v in evento_bash("git push").items() if k != "hook_event_name"}
    esperar(fallos, correr(sin_evento)[0] == 2, "sin hook_event_name cuenta como PreToolUse")
    comprobar(fallos)


def test_falla_abierto_ante_error_interno():
    fallos = []
    original = G.analizar
    try:
        def roto(*a, **k):
            raise RuntimeError("boom")

        def sale(*a, **k):
            raise SystemExit(3)
        for falla in (roto, sale):
            G.analizar = falla
            esperar(fallos, correr(evento_bash("git commit")) == (0, "", b""), "%s: exit 0 en silencio" % falla.__name__)
    finally:
        G.analizar = original
    esperar(fallos, correr(evento_bash("git commit"))[0] == 2, "restaurado, vuelve a bloquear")
    patologico = "(" * 5000 + "git commit" + ")" * 5000 + " $(" * 300
    esperar(fallos, correr(evento_bash(patologico))[0] in (0, 2), "un comando patologico no lanza")
    esperar(fallos, correr(evento_bash("echo 'sin cerrar"))[0] == 0, "comillas sin cerrar no lanza")
    comprobar(fallos)


def _arbol(carpeta):
    return sorted((fw(p), p.stat().st_mtime_ns) for p in Path(carpeta).rglob("*") if ".git" not in p.parts)


def test_no_lanza_subprocess_ni_escribe_en_disco():
    fallos = []
    original = subprocess.run
    llamadas = []
    antes = _arbol(BASE)
    subprocess.run = lambda *a, **k: llamadas.append(a)
    try:
        correr(evento_bash("git commit -m x"))
        correr(evento_bash("echo x > " + CS))
        correr(evento_bash("find " + fw(TALLER_DIR) + " -name '*.sql' | xargs sed -i s/a/b/"))
        correr(evento_bash("git status"))
    finally:
        subprocess.run = original
    esperar(fallos, llamadas == [], "analiza el texto, sin subprocess: %r" % llamadas)
    esperar(fallos, _arbol(BASE) == antes, "no escribe en disco")
    comprobar(fallos)


def _hook(evento, *args, entorno=None):
    env = dict(_entorno_sin_git(), CLAUDE_PROJECT_DIR=str(INST)) if entorno is None else entorno
    datos = evento if isinstance(evento, bytes) else json.dumps(evento).encode("utf-8")
    return subprocess.run([sys.executable, str(_RUTA), *args], input=datos, capture_output=True, env=env, timeout=60)


def test_main_como_hook_real():
    fallos = []
    r = _hook(evento_bash("git -C d commit -m x"), "--plazo", "8")
    esperar(fallos, r.returncode == 2 and r.stdout == b"", "bloquea: %r %r" % (r.returncode, r.stdout))
    esperar(fallos, "git commit" in r.stderr.decode("utf-8", errors="replace"), "stderr utf-8 legible: %r" % r.stderr)
    for args in ((), ("--plazo",), ("--plazo", "x"), ("--plazo", "0")):
        esperar(fallos, _hook(evento_bash("git push"), *args).returncode == 2, "bloquea con los argumentos %r" % (args,))
    r = _hook(evento_bash("git status"))
    esperar(fallos, (r.returncode, r.stdout, r.stderr) == (0, b"", b""), "lo que pasa: exit 0 y nada: %r" % ((r.returncode, r.stdout, r.stderr),))
    r = _hook(b"\xff\xfe no es json writer-sql")
    esperar(fallos, (r.returncode, r.stdout, r.stderr) == (0, b"", b""), "stdin basura falla abierto")
    esperar(fallos, _hook(b"").returncode == 0, "stdin vacio falla abierto")
    env = dict(_entorno_sin_git(), PYTHONIOENCODING="cp1252", CLAUDE_PROJECT_DIR=str(INST))
    env.pop("PYTHONPATH", None)
    r = _hook(evento_bash("git push"), entorno=env)
    esperar(fallos, r.returncode == 2 and "índice".encode("utf-8") in r.stderr, "UTF-8 aun con consola cp1252: %r" % r.stderr)
    comprobar(fallos)


AJENOS = ("Explore", "revisor-sql", "general-purpose", "", None, 7, ["writer-sql"], "writer-", "writer-SQL", "Writer-sql",
          "odd-ws:writer-sql", "xwriter-sql", "writer-sql ", "writer-sql:x", "writer--x", "writer-_x")
WRITERS = ("writer-sql", "writer-web", "writer-movil", "writer-otra", "writer-a1-b2", "writer-9")


def test_s19_solo_actua_dentro_de_un_writer():
    fallos = []
    base = evento_bash("git commit -m x")
    sin = {k: v for k, v in base.items() if k != "agent_type"}
    esperar(fallos, correr(sin) == (0, "", b""), "sin agent_type (sesion principal) calla")
    for ajeno in AJENOS:
        esperar(fallos, correr(dict(base, agent_type=ajeno)) == (0, "", b""), "agent_type %r calla" % (ajeno,))
    for writer in WRITERS:
        esperar(fallos, correr(dict(base, agent_type=writer))[0] == 2, "%s sigue bloqueando" % writer)
        esperar(fallos, correr(dict(base, agent_type=writer, tool_name="PowerShell"))[0] == 2, "%s con PowerShell" % writer)
    comprobar(fallos)


def test_el_reconocimiento_es_la_convencion_de_capas():
    for writer in WRITERS:
        assert convencion.es_writer(writer), writer
    for ajeno in AJENOS:
        assert not convencion.es_writer(ajeno), ajeno
    for capa in CONFIG["layers"]:
        assert convencion.es_writer(Path(convencion.writer(capa)).stem), capa
    assert convencion.WRITER_RE.pattern.startswith(G.PREFILTRO.decode("ascii")), (convencion.WRITER_RE.pattern, G.PREFILTRO)


@contextlib.contextmanager
def instancia_temporal():
    d = Path(tempfile.mkdtemp(prefix="guarda-inst-"))
    try:
        config = {"schema_version": 1, "repos": {}, "layers": {"sql": {"extensions": [".sql"]}}}
        (d / "workspace.config.json").write_text(json.dumps(config), encoding="utf-8")
        yield d
    finally:
        _borrar(d)


def test_s19_un_ajeno_no_toma_foto():
    fallos = []
    with instancia_temporal() as raiz:
        archivo = raiz / "A.sql"
        archivo.write_text("x", encoding="utf-8")
        e = evento_escritura(archivo)
        for caso in (dict(e, agent_type="Explore"), {k: v for k, v in e.items() if k != "agent_type"}):
            esperar(fallos, correr(caso, raiz) == (0, "", b""), "calla")
        esperar(fallos, not (raiz / ".claude").exists(), "no toca disco con un agente ajeno o sin agent_type")
        correr(e, raiz)
        esperar(fallos, (raiz / ".claude").exists(), "con un writer si toma la foto")
    comprobar(fallos)


def _mediana(args, entrada, n=15):
    tiempos = []
    for _ in range(n):
        t0 = time.perf_counter()
        subprocess.run(args, input=entrada, capture_output=True)
        tiempos.append(time.perf_counter() - t0)
    return sorted(tiempos)[n // 2]


def test_s19_main_como_hook_real_sin_writer_es_noop_y_barato():
    fallos = []
    sin = {k: v for k, v in evento_bash("git commit -m x").items() if k != "agent_type"}
    assert G.PREFILTRO not in json.dumps(sin).encode("utf-8"), "la prueba necesita un evento sin el prefijo"
    for e in (sin, dict(sin, agent_type="Explore"), dict(sin, agent_type="revisor-sql")):
        r = _hook(e)
        esperar(fallos, (r.returncode, r.stdout, r.stderr) == (0, b"", b""), "no-op con %r: %r" % (e.get("agent_type"), r))
    esperar(fallos, _hook(dict(sin, agent_type="writer-web")).returncode == 2, "con un writer bloquea")
    pelado = _mediana([sys.executable, "-c", "pass"], b"")
    noop = _mediana([sys.executable, str(_RUTA)], json.dumps(sin).encode("utf-8"))
    print("      latencia no-op: %.1f ms; python pelado: %.1f ms" % (noop * 1000, pelado * 1000))
    esperar(fallos, noop < pelado * 1.5 + 0.015, "el no-op queda cerca del arranque pelado: %.1f ms contra %.1f ms" % (noop * 1000, pelado * 1000))
    comprobar(fallos)


def test_un_comando_de_la_sesion_principal_que_nombra_un_writer_calla():
    sin = {k: v for k, v in evento_bash("cat .claude/agents/writer-sql.md && git commit -m x").items() if k != "agent_type"}
    r = _hook(sin)
    assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r


def test_sin_instancia_o_con_la_config_rota_calla():
    d = Path(tempfile.mkdtemp(prefix="guarda-sin-"))
    try:
        archivo = d / "A.sql"
        archivo.write_text("x", encoding="utf-8")
        assert correr(evento_bash("git commit -m x", cwd=str(d)), d) == (0, "", b"")
        assert correr(evento_escritura(archivo), d) == (0, "", b"")
        assert not (d / ".claude").exists()
        (d / "workspace.config.json").write_text("{ roto", encoding="utf-8")
        assert correr(evento_bash("git commit -m x", cwd=str(d)), d) == (0, "", b"")
        assert correr(evento_escritura(archivo), d) == (0, "", b"")
        assert not (d / ".claude").exists()
        r = _hook(evento_bash("git push", cwd=str(d)), entorno=dict(_entorno_sin_git(), CLAUDE_PROJECT_DIR=str(d)))
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r
    finally:
        _borrar(d)


def test_e2_el_scratchpad_se_decide_con_la_ruta_normalizada():
    base = fw(SCRATCH_BASE)
    bloquea = [
        "echo x > " + base + "/../../equipo/db/x",
        "echo x > " + bw(base) + "\\..\\..\\equipo\\db\\x",
        "echo x > " + gb(base) + "/../../equipo/db/x.sql",
        "echo x > " + base + "/c--x/s/scratchpad/../../../../../inst/tickets/T-123-x/SQL/esq.Proc_A.sql",
        "cp a.txt " + base + "/../../equipo/movil/app/src/main/java/com/x/A.java",
        "Set-Content " + bw(base) + "\\..\\..\\equipo\\db\\x -Value a",
    ]
    pasa = [
        "echo x > " + base + "/c--x/s/scratchpad/u1/../u2/salida.txt",
        "echo x > " + SCRATCH,
        "echo x > " + base + "/c--x/s/scratchpad/./u1//salida.txt",
        "cp " + CS + " " + base + "/c--x/s/scratchpad/a/../B.cs",
    ]
    comprobar(tabla(bloquea, True), tabla(pasa, False))


def test_s10_alias_de_git_que_esconde_una_escritura():
    comprobar(tabla([
        "git -c alias.ci=commit ci -m x", "git -c alias.p=push p", "git -c alias.a=add a .", "git -c alias.CI=commit ci -m x",
        'git -c "alias.go=commit -v" go', 'git -c alias.x="!git push" x', "git -c alias.x=!git\\ add x",
        "git -c alias.a=commit -c alias.b=a b", "cd X && git -C d -c alias.ci=commit ci",
    ], True), tabla([
        "git -c alias.st=status st", "git -c alias.l=log l --oneline", 'git -c alias.x="!git status" x',
        "git -c alias.ci=commit status", "git -c core.quotepath=off diff",
    ], False))


def test_s10_xargs_analiza_el_comando_que_ejecuta():
    comprobar(tabla([
        "ls | xargs -I {} git commit -m {}", "xargs -n 1 -P 4 git add", "xargs -0 -n1 git push", "find . | xargs -I{} git rm {}",
        "ls | xargs -I {} cp {} " + CS, "xargs -0 sed -i s/a/b/ " + CS, "xargs -a lista.txt -d '\\n' git checkout",
        "ls | xargs sh -c 'git commit -m x'",
    ], True), tabla([
        "xargs grep push", "ls | xargs -I {} cp {} scratch/", "xargs -n1 git log", "xargs -P 4 -I {} git show {}",
        "git ls-files | xargs -n 1 grep commit", "xargs -I {} sed -i s/a/b/ {}",
    ], False))


def test_s10_perl_en_sitio():
    comprobar(tabla([
        "perl -pi -e 's/a/b/' " + CS, "perl -pi.bak -e 's/a/b/' " + JAVA_W, "perl -i -pe 's/a/b/' " + SQL, "perl -i.orig -ne print " + TALLER_W,
        "perl -pie 's/a/b/' " + CS, "cat x | perl -pi -e 's/a/b/' " + gb(DB) + "/a.sql",
    ], True), tabla([
        "perl -ne 'print if /x/' " + CS, "perl -pe 's/a/b/' " + CS, "perl -pi -e 's/a/b/' salida.txt",
        "perl -pi -e 's/a/b/' " + SCRATCH, "perl -e 'print 1'", "perl -wle 'print 1' " + CS,
        "perl -Mstrict -ne 'print' " + CS, "perl -mlib -ne 'print' " + CS,
        "perl -MList::Util=sum -ne 'print' " + CS, "perl -Ilib -ne 'print' " + CS,
    ], False), tabla(["perl -Mstrict -pi -e 's/a/b/' " + CS], True))


def test_s10_python_c():
    comprobar(tabla([
        "python -c \"open('" + fw(DB) + "/x.sql','w').write('x')\"",
        "python3 -c \"from pathlib import Path; Path(r'" + bw(DB).replace("\\", "\\\\") + "\\\\x.sql').write_text('x')\"",
        "python -c \"import shutil; shutil.copy('a.txt','" + fw(MOVIL) + "/A.java')\"",
        "python -c \"open('" + TALLER + "','a').write('x')\"",
        "python -c \"import os; os.remove('" + fw(DB) + "/x.sql')\"",
        "python -c \"import subprocess; subprocess.run(['git','commit','-m','x'])\"",
        "python -c \"import os; os.system('git push')\"", "py -c \"import subprocess; subprocess.check_call(['git', 'add', '.'])\"",
        "cd X && python -c \"import subprocess; subprocess.run('git reset --hard', shell=True)\"",
    ], True), tabla([
        "python -c \"print(1+1)\"", "python -c \"import json; print(open('" + fw(DB) + "/x.json').read())\"",
        "python -c \"open('salida.txt','w').write('x')\"", "python -c \"open('" + SCRATCH_FW + "','w').write('x')\"",
        "python -c \"import subprocess; subprocess.run(['git','status'])\"", "python -c \"import subprocess; subprocess.run(['dotnet','test'])\"",
        "python plugin/scripts/writer_guard.tests.py", "python -c \"print('git commit')\"",
    ], False))


def test_s21_python_por_heredoc():
    fallos = tabla([
        "cd " + gb(WT) + " && python3 - <<'EOF'\np='app/src/main/java/A.java'\n"
        "s=open(p,encoding='utf-8',newline='').read()\nopen(p,'w',encoding='utf-8',newline='').write(s)\nEOF",
        "cd " + gb(WT) + " && python3 - <<'EOF'\np='app/src/main/res/values/strings.xml'\n"
        "b=open(p,'rb').read()\nopen(p,'wb').write(b)\nEOF",
        "python - <<EOF\nopen('" + SQL + "','w').write('x')\nEOF",
        "python3 <<'PY'\nimport shutil\nshutil.copy('a.txt','" + CS + "')\nPY",
        "python3 -I - << 'EOF'\nfrom pathlib import Path\nPath(r'" + JAVA_W + "').write_text('x')\nEOF",
        "py - <<-EOF\n\topen('" + TALLER + "','a').write('x')\n\tEOF",
        "python3 - <<\"EOF\"\nimport subprocess\nsubprocess.run(['git','commit','-m','x'])\nEOF",
        "python3 -X utf8 - <<'EOF'\nopen('" + SQL + "','w').write('x')\nEOF",
        "python -W ignore - <<'EOF'\nopen('" + SQL + "','w').write('x')\nEOF",
        "python3 - arg1 <<'EOF'\nopen('" + SQL + "','w').write('x')\nEOF",
        "python3 - <<'END-PY'\nopen('" + SQL + "','w').write('x')\nEND-PY",
        "python3 - <<END.PY\nopen('" + SQL + "','w').write('x')\nEND.PY",
    ], True)
    fallos += tabla([
        "python3 - <<'EOF'\nprint(open('" + SQL + "').read())\nEOF",
        "python3 - <<'EOF'\nopen('salida.txt','w').write('x')\nEOF",
        "python3 - <<'EOF'\nopen('" + SCRATCH_FW + "','w').write('x')\nEOF",
        "python3 script.py <<'EOF'\nopen('" + SQL + "','w').write('x')\nEOF",
        "python3 -c \"print(1)\" <<'EOF'\nopen('" + SQL + "','w').write('x')\nEOF",
        "cat <<'EOF'\nopen('" + SQL + "','w').write('x')\nEOF",
    ], False)
    d = G.destinos("python3 - <<'EOF'\nopen('" + SQL + "','w').write('x')\nEOF")
    esperar(fallos, any(x.lower() == SQL.lower() for x in d), "destinos no recoge la ruta del heredoc: %r" % d)
    comprobar(fallos)


def test_s10_clr_file():
    comprobar(tabla([
        "[IO.File]::WriteAllText('" + bw(DB) + "\\x.sql','x')", "[System.IO.File]::WriteAllText(\"" + JAVA_W + "\", \"x\")",
        "[IO.File]::AppendAllText('" + CS + "','x')", "[IO.File]::WriteAllLines('" + TALLER_W + "', $l)", "[IO.File]::Delete('" + JAVA_W + "')",
        "[IO.File]::Copy('a.txt','" + CS + "')", "[IO.File]::Move('a.txt', '" + JAVA_W + "', $true)",
        'powershell -Command "[IO.File]::WriteAllText(\'' + CS + '\',\'x\')"', "$x = 1; [io.file]::writealltext('" + SQL + "','x')",
    ], True), tabla([
        "[IO.File]::WriteAllText('salida.txt','x')", "[IO.File]::WriteAllText('" + SCRATCH + "','x')", "[IO.File]::ReadAllText('" + CS + "')",
        "[IO.File]::Copy('" + CS + "','scratch.txt')", "[IO.File]::WriteAllText($ruta,'x')", "[IO.File]::Exists('" + CS + "')",
    ], False))


def test_s10_robocopy_y_xcopy_miran_el_segundo_posicional():
    carpeta_cs = CS.rsplit("/", 1)[0]
    comprobar(tabla([
        "robocopy scratch " + bw(MOVIL) + " /E", "robocopy scratch " + fw(TALLER_DIR) + " /MIR",
        "robocopy.exe a " + JAVA_W + " x.java /Y", "robocopy /E a " + gb(DB), "xcopy /Y a.txt " + bw(DB) + "\\",
        "robocopy a " + carpeta_cs + " B.cs /R:1 /W:1",
    ], True), tabla([
        "robocopy " + bw(DB) + " scratch /E", "robocopy " + carpeta_cs + " " + SCRATCH + " /MIR", "robocopy a b /E",
        "xcopy " + bw(DB) + "\\x.sql scratch\\ /Y", "robocopy /?",
    ], False))


def _ms_por_comando(comandos, cwd=None):
    G.analizar(comandos[0], cwd, ZONAS)
    t0 = time.perf_counter()
    for c in comandos:
        G.analizar(c, cwd, ZONAS)
    return (time.perf_counter() - t0) * 1000 / len(comandos)


def test_s10_la_latencia_no_empeora():
    ms = _ms_por_comando(GIT_BLOQUEA + GIT_PASA + SHELL_BLOQUEA + SHELL_PASA)
    assert ms < 5, "analizar tarda %.2f ms por comando" % ms


def test_s13_git_config_alias_y_config_env():
    comprobar(tabla([
        "git config alias.ci commit", "git config --global alias.p push", "git config alias.x '!git add .'",
        "git config alias.CI commit", "git config --add alias.ci commit", "git config alias.ci commit && git ci -m x",
        "git --config-env=alias.ci=CI ci -m x", "git --config-env alias.ci=CI ci -m x", "cd X && git --config-env=alias.a=A a .",
    ], True), tabla([
        "git config alias.st status", "git config alias.l 'log --oneline'", "git config --get alias.ci", "git config alias.ci",
        "git config user.name x", "git config --list", "git --config-env=core.pager=P status", "git --config-env=alias.st=S log",
        "git config alias.x '!git status'",
    ], False))


def test_s13_git_update_index_y_branch_borrar():
    comprobar(tabla([
        "git update-index --assume-unchanged x", "git update-index --skip-worktree f.cs", "git -C d update-index --refresh",
        "git branch -D x", "git branch -d x", "git branch --delete x", "git branch -dr o/x", "git -C d branch -D x",
        "git branch -fD x", "cd X && git branch --delete --force x",
    ], True), tabla([
        "git branch", "git branch -a", "git branch -vv", "git branch --show-current", "git branch --list 'f*'",
        "git branch --contains abc", "git branch --sort=-committerdate", "git branch -r", "git diff --name-only",
    ], False))


def test_s13_xargs_y_find_exec_sobre_zona_protegida():
    comprobar(tabla([
        "find " + gb(DB) + " -name '*.sql' | xargs sed -i 's/a/b/'", "find " + gb(DB) + " -name '*.bak' | xargs rm",
        "find " + fw(DB) + " -name '*.bak' -exec rm {} \\;", "find " + fw(DB) + " -name '*.sql' -exec sed -i s/a/b/ {} +",
        "find " + gb(DB) + " -name x -delete", "cd " + gb(DB) + " && ls | xargs rm",
        "find " + fw(TALLER_DIR) + " -name '*.sql' | xargs sed -i s/a/b/", "find " + fw(DB) + " -name '*.sql' -exec git add {} \\;",
        "find " + gb(DB) + " -name '*.sql' | xargs -I {} cp a.sql {}",
    ], True), tabla([
        "ls | xargs rm", "find . -name x -exec rm {} \\;", "find " + gb(DB) + " -name '*.sql' | xargs grep -l x",
        "find " + fw(DB) + " -name '*.sql' -exec grep -l x {} +", "find " + fw(DB) + " -name x -print",
        "find " + fw(DB) + " -name '*.sql' | xargs -I {} cp {} " + SCRATCH_FW,
        "find " + SCRATCH_FW + " -name '*.tmp' -exec rm {} +", "find " + SCRATCH_FW + " -name '*.tmp' -delete",
        "find " + fw(DB) + " -name '*.sql' | head", "ls | xargs -I {} sed -i s/a/b/ {}",
    ], False), con_cwd([
        "ls | xargs rm", "git ls-files | xargs sed -i s/a/b/", "find . -name '*.bak' -exec rm {} \\;",
        "find . -name '*.sql' -exec sed -i s/a/b/ {} +", "find . -name '*.bak' -delete",
    ], REPO_CWD, True), con_cwd(["ls | xargs rm", "find . -name '*.bak' -exec rm {} \\;", "git ls-files | xargs grep x"], bw(INST), False),
        con_cwd(["ls | xargs grep x", "find . -name '*.sql' -exec grep -l x {} +", "find . -name x -print"], REPO_CWD, False))


def test_s13_perl_0pi_y_python_Ic():
    comprobar(tabla([
        "perl -0pi -e 's/a/b/s' " + CS, "perl -0777pi -e 's/a/b/' " + CS, "perl -0777 -pi -e 's/a/b/' " + CS, "perl -0pi.bak -e 's/a/b/' " + SQL,
        "python -Ic \"open('" + SQL + "','w').write('a')\"", "python -Bc \"open('" + SQL + "','w').write('a')\"",
        "python -sIc \"import os; os.remove('" + CS + "')\"", "py -Ic \"import subprocess; subprocess.run(['git','add','.'])\"",
    ], True), tabla([
        "perl -0ne 'print' " + CS, "perl -0777 -ne 'print' " + CS, "perl -0pe 's/a/b/' " + CS, "perl -0pi -e 's/a/b/' salida.txt",
        "python -Ic \"print(1)\"", "python -Ic \"open('salida.txt','w').write('a')\"", "python -Bc \"print(open('" + SQL + "').read())\"",
    ], False))


def test_s13_clr_file_con_destino_no_resoluble():
    comprobar(tabla([
        "[IO.File]::WriteAllText((Join-Path '" + bw(DB) + "' 'x.sql'), 'x')",
        "[IO.File]::WriteAllText((Join-Path '" + bw(TALLER_DIR) + "' 'esq.Proc_A.sql'), 'x')",
        "[IO.File]::WriteAllText(\"" + bw(DB) + "\\$n.sql\", 'x')", "[IO.File]::AppendAllText(\"" + bw(TALLER_DIR) + "\\esq.$n.sql\", 'x')",
        "[IO.File]::Copy('a.txt', (Join-Path '" + bw(DB) + "' 'x.sql'))", "[IO.File]::WriteAllText(('" + bw(DB) + "\\' + $n), 'x')",
    ], True), tabla([
        "[IO.File]::WriteAllText($ruta,'x')", "[IO.File]::WriteAllText((Join-Path $env:TEMP 'x.txt'), 'x')", "[IO.File]::WriteAllText(\"$PWD\\x.sql\", 'x')",
        "[IO.File]::ReadAllText((Join-Path '" + bw(DB) + "' 'x.sql'))", "[IO.File]::WriteAllText((Join-Path '" + SCRATCH + "' 'x.txt'), 'x')",
    ], False), con_cwd([
        "[IO.File]::WriteAllText($ruta,'x')", "[IO.File]::WriteAllText(\"$PWD\\x.sql\", 'x')", "[IO.File]::WriteAllText((Join-Path $PWD 'x.sql'), 'x')",
        "[IO.File]::WriteAllText((Join-Path (Get-Location) 'x.sql'), 'x')", "[IO.File]::Delete($f)", "[IO.File]::Copy('a.txt', $destino)",
    ], REPO_CWD, True), tabla([
        "$p = '" + bw(DB) + "\\esq\\x.sql'; [IO.File]::WriteAllText($p, 'x')",
        "$p = \"" + TALLER_W + "\"; [IO.File]::Delete($p)",
    ], True), tabla(["$p = 'salida.txt'; [IO.File]::WriteAllText($p, 'x')", "$p = '" + SCRATCH + "'; [IO.File]::WriteAllText($p, 'x')"], False),
        con_cwd(["$p = '" + SCRATCH + "'; [IO.File]::WriteAllText($p, 'x')"], REPO_CWD, False),
        con_cwd(["[IO.File]::WriteAllText($ruta,'x')", "[IO.File]::WriteAllText(\"$PWD\\x.sql\", 'x')", "[IO.File]::Copy($origen, 'salida.txt')"], bw(INST), False),
        con_cwd(["[IO.File]::ReadAllText($ruta)", "[IO.File]::Exists($ruta)", "[IO.File]::Copy($origen, '" + SCRATCH + "')"], REPO_CWD, False))


def test_s13_iex_invoke_expression_y_start_process():
    comprobar(tabla([
        "iex 'git commit -m x'", 'Invoke-Expression "git push"', "iex \"Set-Content " + TALLER_W + " x\"", "Invoke-Expression 'git add .'",
        "Start-Process git -ArgumentList 'commit','-m','x'", "Start-Process -FilePath git -ArgumentList 'add .'",
        "Start-Process powershell -ArgumentList '-Command','git push'", "Start-Process -FilePath git -ArgumentList 'push' -Wait -NoNewWindow",
        "saps git -ArgumentList 'reset','--hard'", "iex \"[IO.File]::WriteAllText('" + CS + "','x')\"", "Start-Process git -WorkingDirectory C:\\x -ArgumentList 'checkout','y'",
    ], True), tabla([
        "iex 'git status'", "Invoke-Expression 'Get-ChildItem'", "Start-Process notepad", "Start-Process git -ArgumentList 'log','-1'",
        "Start-Process dotnet -ArgumentList 'test' -Wait", "Start-Process -FilePath git -ArgumentList 'status'", "iex $comando", "Start-Process $exe",
    ], False))


def test_s13_el_scratchpad_exige_que_la_ruta_empiece_por_el_scratch_real():
    comprobar(tabla([
        "echo x > " + fw(DB) + "/tmp/claude/x.sql", "Set-Content " + bw(DB) + "\\tmp\\claude\\x.sql x",
        "cp a.txt " + fw(MOVIL) + "/tmp/claude/A.java",
        "echo x > " + gb(DB) + "/tmp/claude/x.sql", "echo x > " + fw(SCRATCH_BASE) + "X/../../equipo/db/x",
    ], True), tabla([
        "echo x > " + SCRATCH, "echo x > " + SCRATCH_FW, "Set-Content " + SCRATCH + " x", "cp " + CS + " " + SCRATCH,
        "echo x > " + fw(BASE / "otro/tmp/claude/c--x/s/x.txt"), "echo x > " + gb(BASE / "otro/tmp/claude/c--x/s/x.txt"),
    ], False))


def test_s13_la_latencia_con_las_variantes_no_empeora():
    comandos = GIT_BLOQUEA + GIT_PASA + SHELL_BLOQUEA + SHELL_PASA + [
        "git config alias.ci commit", "find " + gb(DB) + " -name '*.sql' | xargs sed -i s/a/b/", "iex 'git status'",
        "[IO.File]::WriteAllText($ruta,'x')", "Start-Process git -ArgumentList 'log','-1'", "git branch -D x", "python -Ic \"print(1)\"",
    ]
    ms = _ms_por_comando(comandos, REPO_CWD)
    assert ms < 5, "analizar tarda %.2f ms por comando" % ms


def test_s13_destinos_recoge_lo_que_el_comando_escribe_con_el_mismo_parser():
    fallos = []
    d = G.destinos("sed -i s/a/b/ " + SCRATCH_FW)
    esperar(fallos, any(x.lower() == SCRATCH_FW.lower() for x in d), "sed -i del scratch no aparece: %r" % d)
    esperar(fallos, not any("s/a/b" in x for x in d), "el script de sed aparece como destino: %r" % d)
    esperar(fallos, G.destinos("cat " + SCRATCH_FW) == [], "cat no escribe")
    esperar(fallos, G.destinos("git commit -m x && echo y > " + SCRATCH_FW)[-1:] == [SCRATCH_FW], "tras un git de escritura sigue recogiendo")
    esperar(fallos, any(x.endswith("a.txt") for x in G.destinos("cd C:/x && tee a.txt")), "tee con cd")
    esperar(fallos, G.destinos("echo y > " + SCRATCH_FW) == [SCRATCH_FW], "redireccion")
    esperar(fallos, G.destinos("") == [] and G.destinos(None) == [], "vacio o None")
    antes = G.analizar("git commit -m x", None, ZONAS)
    G.destinos("git commit -m x")
    esperar(fallos, G.analizar("git commit -m x", None, ZONAS) == antes and G.analizar("cat x", None, ZONAS) is None, "destinos deja estado colgado")
    esperar(fallos, G.analizar("echo x > " + CS, None, ZONAS) is not None, "analizar sigue protegiendo tras destinos")
    comprobar(fallos)


def test_destinos_tras_un_cd_conserva_la_forma_del_origen():
    esperado = "c:/x/a.txt" if NT else "C:/x/a.txt"
    assert G.destinos("cd C:/X && tee a.txt" if NT else "cd C:/x && tee a.txt") == [esperado]


def test_una_ruta_que_no_se_resuelve_no_usa_el_cwd_del_proceso():
    previo = os.getcwd()
    os.chdir(DB)
    try:
        unidad = fw(DB)[:2] if NT else ""
        relativas_a_la_unidad = [unidad, unidad + "x.sql", unidad + "$f", unidad + "Current/x.sql", unidad + "/../x.sql",
                                 unidad + "/../../Current/x.sql"] if NT else []
        comprobar(tabla(["echo x > %x", "echo x > %x/y.sql", "echo x > $", "Set-Content %x x", "echo x > %x/../" + fw(DB) + "/x.sql"], False),
                  tabla(["echo x > " + r for r in relativas_a_la_unidad], False),
                  tabla(["echo x > x.sql"], False), con_cwd(["echo x > x.sql"], REPO_CWD, True))
        comprobar(tabla(["cd " + unidad + " && echo x > x.sql", "cd " + unidad + "/.. && echo x > x.sql"] if NT else [], False),
                  tabla(["cd " + unidad + "/ && echo x > " + fw(DB)[3:] + "/x.sql"] if NT else [], True))
    finally:
        os.chdir(previo)


def test_una_ruta_sin_unidad_toma_la_unidad_del_cwd_del_shell():
    if not NT:
        return
    sin_unidad = fw(DB)[2:]
    otra = "Z:/otra" if fw(DB)[0].upper() != "Z" else "Y:/otra"
    previo = os.getcwd()
    os.chdir(DB)
    try:
        comprobar(tabla(["echo x > " + sin_unidad + "/x.sql", "Set-Content " + bw(sin_unidad) + "\\x.sql x",
                         "cd " + bw(sin_unidad) + " && echo x > y.txt"], False),
                  con_cwd(["echo x > " + sin_unidad + "/x.sql", "cd " + bw(sin_unidad) + "; Set-Content y.txt x"], otra, False),
                  con_cwd(["echo x > " + sin_unidad + "/x.sql", "Set-Content " + bw(sin_unidad) + "\\x.sql x",
                           "cd " + bw(sin_unidad) + "; Set-Content y.txt x"], fw(DB)[:2] + "/", True),
                  con_cwd(["echo x > /dev/null", "echo x > //srv/sh/x.sql"], REPO_CWD, False))
    finally:
        os.chdir(previo)


def test_un_ancestro_de_un_repo_es_zona():
    comprobar(tabla([
        "rm -rf " + fw(EQUIPO), "Remove-Item -Recurse -Force " + bw(EQUIPO), "cd " + fw(DB) + " && rm -rf ..",
        "mv " + fw(EQUIPO) + " " + fw(BASE / "otro"), "rm -rf " + fw(BASE), "rm -rf " + fw(EQUIPO / "worktrees"),
        "find " + fw(EQUIPO) + " -name x -delete", "cd " + fw(EQUIPO) + " && ls | xargs rm", "cp a.txt " + fw(BASE) + "/",
        "rd /s /q " + bw(EQUIPO), "echo x > " + fw(DB)[:3] + "$f" if NT else "echo x > /$f",
    ] + (["rm -rf " + fw(DB)[:3], "Remove-Item -Recurse " + bw(DB)[:3]] if NT else ["rm -rf /"]), True), tabla([
        "rm -rf " + fw(BASE / "copia"), "rm -rf " + fw(INST / "tickets"), "ls " + fw(EQUIPO), "echo x > " + fw(EQUIPO) + "/notas.txt",
        "find " + fw(EQUIPO) + " -name '*.sql' | xargs grep x", "rm -rf " + fw(EQUIPO / "worktrees/web--y"),
    ], False))


def test_un_comodin_corta_la_ruta_y_la_carpeta_conocida_decide():
    comprobar(tabla([
        "rm -rf " + fw(EQUIPO) + "/*", "rm -rf " + fw(BASE) + "/eq*", "Remove-Item " + bw(EQUIPO) + "\\*\\*.sql",
        "cd " + fw(EQUIPO) + " && rm -rf *", "rm -rf " + fw(DB) + "/*.sql", "rm " + fw(TALLER_DIR) + "/esq.*.sql",
        "rm " + fw(INST / "tickets") + "/T-1*/SQL/esq.a.sql", "rm -rf " + fw(EQUIPO) + "/[dw]*", "rm -rf " + fw(EQUIPO) + "/d?",
        "rm -rf " + fw(EQUIPO) + "/[dw]b",
    ], True), tabla([
        "rm -rf " + fw(BASE / "copia") + "/*", "rm " + fw(INST / "tickets") + "/*.tmp", "rm -rf *", "cd " + fw(INST) + " && rm -rf *.log",
        "ls " + fw(EQUIPO) + "/*", "rm " + fw(SCRATCH_BASE) + "/*",
    ], False))


def test_la_carpeta_de_un_cd_con_variable_decide_sola():
    comprobar(tabla(["cd $REPOS/db && echo x > notas.txt", "cd ${REPOS}/web; Set-Content B.cs x", "cd ~/equipo/db && rm x.sql"], True),
              tabla(["cd $NOEXISTE && echo x > notas.txt"], False))


def test_fuera_de_la_instancia_ningun_glob_del_taller_cuenta():
    config = config_loader.cargar(INST)
    config["layers"]["sql"] = dict(config["layers"]["sql"], workshop=["**/SQL/*.sql"])
    otra = G.Zonas(config, ENTORNO)
    afuera = BASE / "afuera" / "SQL"
    comprobar(tabla(["find " + fw(TALLER_DIR) + " | xargs rm", "find " + fw(INST / "x/SQL") + " | xargs rm"], True, None, otra),
              tabla(["find " + fw(afuera) + " | xargs rm", "echo x > " + fw(afuera / "a.sql")], False, None, otra))


def test_la_foto_no_se_pisa_aunque_otro_proceso_la_escriba_en_el_medio():
    with instancia_temporal() as raiz:
        archivo = raiz / "A.sql"
        archivo.write_bytes(b"original\n")
        correr(evento_escritura(archivo), raiz)
        archivo.write_bytes(b"cambiado\n")
        original = G.os.path.exists
        G.os.path.exists = lambda p: False
        try:
            G.tomar_foto(evento_escritura(archivo), str(raiz))
        finally:
            G.os.path.exists = original
        foto = Path(G.carpeta_fotos(str(raiz), "s1", "a1")) / (G.clave_foto(archivo) + ".foto")
        assert foto.read_bytes() == b"original\n"


def test_el_scratch_gana_aunque_caiga_dentro_de_una_zona():
    adentro = G.Zonas(config_loader.cargar(INST), dict(ENTORNO, TEMP=str(DB / "tmp"), TMP=str(DB / "tmp"), TMPDIR=str(DB / "tmp")))
    comprobar(tabla(["echo x > " + fw(DB / "tmp/claude/s/x.sql"), "rm -rf " + fw(DB / "tmp/claude/s")], False, None, adentro),
              tabla(["echo x > " + fw(DB / "x.sql"), "echo x > " + fw(DB / "tmp/claude/../x.sql")], True, None, adentro))


def test_destinos_no_inventa_rutas_de_capa():
    assert G.destinos("robocopy a " + fw(DB / "sub") + " /E") == [fw(DB / "sub")]
    assert G.destinos("xcopy /Y a.txt " + fw(DB / "sub")) == [fw(DB / "sub")]


def test_zonas_por_contencion_y_no_por_nombre():
    comprobar(tabla([
        "echo x > " + fw(DB) + "/notas.txt", "echo x > " + fw(WEB) + "/appsettings.json", "rm " + fw(MOVIL) + "/build.gradle",
    ], True), tabla([
        "echo x > " + fw(BASE / "copia/equipo/db/x.sql"), "echo x > " + fw(EQUIPO) + "/notas.txt",
        "echo x > " + fw(INST) + "/x.sql", "echo x > " + fw(INST / "tickets/T-123-x/SQL/otro.sql"),
    ], False))


def test_un_worktree_registrado_es_zona_y_uno_sin_registrar_no():
    suelto = EQUIPO / "worktrees" / "web--y"
    suelto.mkdir(parents=True, exist_ok=True)
    comprobar(tabla([
        "echo x > " + fw(WT) + "/notas.txt", "echo x > " + fw(WT) + "/app/src/main/java/A.java", "cd " + gb(WT) + " && rm README.md",
    ], True), tabla(["echo x > " + fw(suelto) + "/B.cs", "cd " + fw(suelto) + " && rm B.cs"], False))


def test_una_junction_o_un_enlace_hacia_un_repo_es_zona():
    enlace = BASE / "atajo"
    if NT:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(DB)], capture_output=True)
        assert r.returncode == 0, r
    else:
        os.symlink(DB, enlace)
    try:
        comprobar(tabla(["echo x > " + fw(enlace) + "/x.sql", "echo x > " + fw(enlace) + "/notas.txt", "cd " + fw(enlace) + " && ls | xargs rm"], True))
    finally:
        os.rmdir(enlace) if NT else os.unlink(enlace)


def test_las_variables_se_expanden_con_el_entorno():
    comprobar(tabla([
        "echo x > $REPOS/db/x.sql", "echo x > ${REPOS}/db/notas.txt", "Set-Content $env:REPOS\\db\\x.sql x", "echo x > %REPOS%\\db\\x.sql",
        "echo x > ~/equipo/db/x.sql", "Set-Content ~\\equipo\\web\\B.cs x", "cd $REPOS/db && ls | xargs rm",
        "echo x > $HOME/inst/tickets/T-123-x/SQL/esq.Proc_A.sql",
    ], True), tabla([
        "echo x > $NOEXISTE/db/x.sql", "echo x > %NOEXISTE%\\db\\x.sql", "echo x > ~otro/equipo/db/x.sql", "echo x > ${NOEXISTE}",
        "echo x > $REPOS/../copia/db/x.sql", "cd $NOEXISTE && ls | xargs rm",
    ], False))


def test_una_variable_desconocida_corta_la_ruta_en_la_parte_conocida():
    comprobar(tabla([
        "echo x > " + fw(DB) + "/$f", "echo x > " + fw(DB) + "/sub/${f}.sql", "echo x > " + fw(TALLER_DIR) + "/$f",
        "Set-Content " + bw(DB) + "\\%F% x", "echo x > $REPOS/db/$f",
    ], True), tabla([
        "echo x > " + fw(INST) + "/$f", "echo x > " + fw(INST / "tickets") + "/$f", "echo x > $f", "echo x > $NOEXISTE/db/$f",
        "echo x > " + fw(BASE / "copia") + "/$f",
    ], False))


def test_pwd_es_la_carpeta_del_shell_y_no_la_del_hook():
    comprobar(tabla(["echo x > $PWD/x.txt", "echo x > ${PWD}/x.sql"], False),
              con_cwd(["echo x > $PWD/x.txt", "echo x > ${PWD}/x.sql"], REPO_CWD, True),
              tabla(["cd " + fw(INST) + " && echo x > $PWD/x.txt"], False),
              tabla(["cd " + fw(DB) + " && echo x > $PWD/x.txt"], True))


def test_el_scratch_sale_del_entorno():
    duda = "[IO.File]::WriteAllText((Join-Path '" + bw(SCRATCH_BASE / "c--x") + "' $n), 'x')"
    sin_temporal = {k: v for k, v in ENTORNO.items() if k not in ("TEMP", "TMP", "TMPDIR")}
    otra = G.Zonas(config_loader.cargar(INST), sin_temporal)
    comprobar(con_cwd([duda], REPO_CWD, False), tabla([duda], True, REPO_CWD, otra))
    if NT:
        assert G.Zonas(config_loader.cargar(INST), dict(ENTORNO, TMP=str(BASE / "otro"))).es_scratch(SCRATCH_FW)
        assert not G.Zonas(config_loader.cargar(INST), dict(ENTORNO, TEMP=str(BASE / "otro"))).es_scratch(SCRATCH_FW)
        assert G.Zonas(config_loader.cargar(INST), dict(sin_temporal, SYSTEMROOT=str(BASE))).es_scratch(fw(BASE / "temp/claude/x"))
    else:
        assert G.Zonas(config_loader.cargar(INST), sin_temporal).es_scratch("/tmp/claude/x")
    assert not ZONAS.es_scratch(fw(SCRATCH_BASE) + "X/y") and not ZONAS.es_scratch(None)


def test_la_carpeta_padre_del_taller_es_zona():
    config = config_loader.cargar(INST)
    config["layers"]["notas"] = {"extensions": [".md"], "workshop": ["notas/**"]}
    otra = G.Zonas(config, ENTORNO)
    comprobar(tabla(["find " + fw(TALLER_DIR) + " | xargs rm", "robocopy a " + fw(TALLER_DIR) + " /E"], True),
              tabla(["find " + fw(INST / "tickets") + " | xargs rm", "find " + fw(INST / "tickets/T-123-x") + " | xargs rm",
                     "find " + fw(INST) + " | xargs rm"], False),
              tabla(["find " + fw(INST / "notas") + " | xargs rm", "find " + fw(INST / "notas/a/b") + " | xargs rm"], True, None, otra),
              tabla(["find " + fw(INST / "notas") + " | xargs rm"], False))


def test_un_plazo_vencido_calla():
    assert correr(evento_bash("echo x > " + CS), plazo=1e-9) == (0, "", b"")
    assert correr(evento_bash("git commit -m x"), plazo=1e-9) == (0, "", b"")
    assert G.analizar("echo x > " + CS, None, ZONAS), "el limite de una corrida no queda para la siguiente"
    assert correr(evento_bash("echo x > " + CS), plazo=8)[0] == 2


def _hooks_del_plugin():
    datos = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for evento_, grupos in datos["hooks"].items():
        for grupo in grupos:
            for h in grupo["hooks"]:
                yield evento_, grupo.get("matcher") or "", h


def test_esta_cableado_en_pre_tool_use_con_8_s():
    from odd_ws.comun import plazo_de
    cableados = [(e, m, h) for e, m, h in _hooks_del_plugin() if h["args"][0] == "${CLAUDE_PLUGIN_ROOT}/scripts/writer_guard.py"]
    assert len(cableados) == 1, cableados
    evento_, matcher, h = cableados[0]
    assert evento_ == "PreToolUse" and set(matcher.split("|")) >= {"Bash", "PowerShell", "Edit", "Write"}, (evento_, matcher)
    assert (h["timeout"], plazo_de(h["args"][1:])) == (10, 8), h


def evento_escritura(ruta, herramienta="Edit", sesion="s1", agente="a1", **extra):
    e = {"hook_event_name": "PreToolUse", "tool_name": herramienta, "session_id": sesion, "agent_id": agente,
         "agent_type": "writer-sql", "cwd": str(INST), "tool_input": {"file_path": str(ruta)}}
    e.update(extra)
    return e


def fotos_de(raiz, sesion="s1", agente="a1"):
    carpeta = Path(G.carpeta_fotos(str(raiz), sesion, agente))
    return sorted(p.name for p in carpeta.iterdir()) if carpeta.is_dir() else []


def test_s9_el_primer_toque_guarda_la_foto_y_nunca_bloquea():
    with instancia_temporal() as raiz:
        archivo = raiz / "taller" / "A.sql"
        archivo.parent.mkdir()
        archivo.write_bytes(b"linea 1\r\nlinea 2\r\n")
        for herramienta in ("Edit", "Write", "MultiEdit"):
            r = correr(evento_escritura(archivo, herramienta), raiz)
            assert r == (0, "", b""), (herramienta, r)
        carpeta = Path(G.carpeta_fotos(str(raiz), "s1", "a1"))
        assert fotos_de(raiz) == [G.clave_foto(archivo) + ".foto"], fotos_de(raiz)
        assert (carpeta / (G.clave_foto(archivo) + ".foto")).read_bytes() == b"linea 1\r\nlinea 2\r\n"
        assert carpeta.parent.name == "s1" and carpeta.name == "a1.fotos", carpeta
        assert fw(carpeta.parent.parent) == fw(raiz / convencion.ESTADO_WRITERS), carpeta


def test_s9_la_segunda_foto_no_pisa_la_primera_y_la_ruta_se_normaliza():
    with instancia_temporal() as raiz:
        archivo = raiz / "A.sql"
        archivo.write_bytes(b"original\n")
        correr(evento_escritura(archivo), raiz)
        archivo.write_bytes(b"cambiado por el writer\n")
        correr(evento_escritura(archivo, "Write"), raiz)
        correr(evento_escritura(fw(archivo)), raiz)
        correr(evento_escritura(str(archivo).upper() if NT else archivo), raiz)
        assert len(fotos_de(raiz)) == 1, fotos_de(raiz)
        foto = Path(G.carpeta_fotos(str(raiz), "s1", "a1")) / (G.clave_foto(archivo) + ".foto")
        assert foto.is_file() and foto.read_bytes() == b"original\n"
        correr(evento_escritura(archivo, agente="a2"), raiz)
        assert fotos_de(raiz, agente="a2") == [G.clave_foto(archivo) + ".foto"]


def test_s9_un_archivo_que_no_existia_deja_la_marca_nuevo_explicita():
    with instancia_temporal() as raiz:
        nuevo = raiz / "Nuevo.sql"
        correr(evento_escritura(nuevo, "Write"), raiz)
        nuevo.write_bytes(b"x\n")
        correr(evento_escritura(nuevo, "Edit"), raiz)
        assert fotos_de(raiz) == [G.clave_foto(nuevo) + ".nuevo"], fotos_de(raiz)


def test_s9_una_ruta_relativa_se_resuelve_contra_el_cwd_del_evento():
    with instancia_temporal() as raiz:
        archivo = raiz / "sub" / "A.sql"
        archivo.parent.mkdir()
        archivo.write_bytes(b"x\n")
        correr(evento_escritura("A.sql", cwd=str(archivo.parent)), raiz)
        assert fotos_de(raiz) == [G.clave_foto(archivo) + ".foto"], fotos_de(raiz)


def test_s9_sin_agent_id_o_con_ids_raros_no_toca_disco():
    with instancia_temporal() as raiz:
        archivo = raiz / "A.sql"
        archivo.write_bytes(b"x\n")
        sin_agente = evento_escritura(archivo)
        del sin_agente["agent_id"]
        casos = [sin_agente, evento_escritura(archivo, agente="../x"), evento_escritura(archivo, sesion="a/b"),
                 evento_escritura(archivo, agente=7), dict(evento_escritura(archivo), tool_input={}),
                 dict(evento_escritura(archivo), tool_input=None), evento_escritura(archivo, hook_event_name="PostToolUse"),
                 evento_escritura(archivo, agente="odd-ws:a1")]
        for e in casos:
            assert correr(e, raiz) == (0, "", b""), e
        assert not (raiz / ".claude").exists()


def test_s9_falla_abierto_si_la_foto_no_se_puede_escribir():
    with instancia_temporal() as raiz:
        archivo = raiz / "A.sql"
        archivo.write_bytes(b"x\n")
        (raiz / ".claude").mkdir()
        tapon = raiz / ".claude" / "estado"
        tapon.write_text("no soy una carpeta", encoding="utf-8")
        assert correr(evento_escritura(archivo), raiz) == (0, "", b"")
        assert tapon.read_text(encoding="utf-8") == "no soy una carpeta"
        tapon.unlink()
        original = G.tomar_foto
        try:
            def roto(*a, **k):
                raise RuntimeError("boom")
            G.tomar_foto = roto
            assert correr(evento_escritura(archivo), raiz) == (0, "", b"")
            G.tomar_foto = lambda *a, **k: (_ for _ in ()).throw(SystemExit(3))
            assert correr(evento_escritura(archivo), raiz) == (0, "", b"")
        finally:
            G.tomar_foto = original
        assert correr(evento_escritura(archivo, agente="a9", tool_input=None), raiz) == (0, "", b"")


def test_s9_main_como_hook_real_con_edit():
    archivo = BASE / "fuera" / "A.sql"
    archivo.parent.mkdir(exist_ok=True)
    archivo.write_bytes(b"x\n")
    real = Path(G.carpeta_fotos(str(INST), "sreal", "reala1"))
    try:
        r = _hook(evento_escritura(archivo, agente="reala1", sesion="sreal"), "--plazo", "8")
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r
        assert real.is_dir() and (real / (G.clave_foto(archivo) + ".foto")).read_bytes() == b"x\n", "la foto cae bajo el estado de la instancia"
    finally:
        shutil.rmtree(real.parent, ignore_errors=True)


def test_b_una_sesion_nueva_poda_las_viejas_y_deja_la_actual():
    with instancia_temporal() as raiz:
        writers = raiz / convencion.ESTADO_WRITERS
        vieja, reciente = writers / "sesion-vieja", writers / "sesion-reciente"
        for d in (vieja, reciente):
            (d / "a1.fotos").mkdir(parents=True)
            (d / "a1.json").write_text("{}", encoding="utf-8")
        hace = time.time() - (G._verificar_capa().DIAS_PODA + 5) * 86400
        os.utime(vieja, (hace, hace))
        archivo = raiz / "A.sql"
        archivo.write_bytes(b"x\n")
        correr(evento_escritura(archivo, sesion="sesion-nueva"), raiz)
        assert not vieja.exists(), "la sesion vieja se poda"
        assert reciente.is_dir() and (reciente / "a1.json").is_file(), "la reciente queda"
        assert fotos_de(raiz, sesion="sesion-nueva") == [G.clave_foto(archivo) + ".foto"]
        os.utime(writers / "sesion-nueva", (hace, hace))
        correr(evento_escritura(raiz / "B.sql", sesion="sesion-nueva", agente="a2"), raiz)
        assert (writers / "sesion-nueva").is_dir(), "la sesion actual nunca se poda, aunque su mtime sea viejo"


def test_b_la_poda_falla_abierto():
    with instancia_temporal() as raiz:
        vieja = raiz / convencion.ESTADO_WRITERS / "sesion-vieja"
        vieja.mkdir(parents=True)
        hace = time.time() - 4000 * 86400
        os.utime(vieja, (hace, hace))
        archivo = raiz / "A.sql"
        archivo.write_bytes(b"x\n")
        original = G._verificar_capa
        try:
            def roto():
                raise RuntimeError("no carga")
            G._verificar_capa = roto
            r = correr(evento_escritura(archivo, sesion="sesion-nueva"), raiz)
        finally:
            G._verificar_capa = original
        assert r == (0, "", b""), r
        assert vieja.exists(), "sin poda no se borra nada"
        assert fotos_de(raiz, sesion="sesion-nueva") == [G.clave_foto(archivo) + ".foto"]


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    pruebas = [(nombre, funcion) for nombre, funcion in globals().items() if nombre.startswith("test_") and callable(funcion)]
    fallas = 0
    try:
        if re.search(r"\s", str(BASE)):
            print("ERROR la carpeta temporal tiene espacios (%s): correr con TMP, TEMP y TMPDIR sin espacios" % BASE)
            return 1
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
    finally:
        _borrar(BASE)
    if SOBRANTES:
        fallas += 1
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
