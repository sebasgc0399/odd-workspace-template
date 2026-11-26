import sys

sys.dont_write_bytecode = True

import contextlib
import hashlib
import http.server
import importlib
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "auditar_ramas.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
AISLAMIENTO_GIT = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
REPOS = ("web", "db")
PLANTILLA = []
NADA = "Resumen: ningún ticket nombra una rama de los repos, así que no hay nada que auditar.\n"


def m():
    return importlib.import_module("auditar_ramas")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in AISLAMIENTO_GIT}


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false",
                        "-c", "init.defaultBranch=main", "-c", "maintenance.auto=false", "-c", "gc.auto=0", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno_sin_git())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def escribir(raiz, rel, texto):
    p = Path(raiz) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texto.encode("utf-8"))
    return p


def commitear(carpeta, rel=None, texto=None):
    escribir(carpeta, rel or ("%s.txt" % os.urandom(4).hex()), texto if texto is not None else "%s\n" % os.urandom(4).hex())
    git(carpeta, "add", "-A")
    git(carpeta, "commit", "-q", "-m", "c")
    return git(carpeta, "rev-parse", "HEAD")


def ticket_con(worktree_y_rama):
    return ("# T — algo\n\n## Objetivo\n\nalgo\n\n## Contexto técnico\n\n- Repos y capas afectados: web\n"
            "- Worktree y rama: %s\n- Dependencias o bloqueos: `feat/fuera` no cuenta acá\n" % worktree_y_rama)


def _plantilla():
    if not PLANTILLA:
        base = Path(os.path.realpath(tempfile.mkdtemp(prefix="auditar-ramas-plantilla-")))
        semilla = base / "semilla"
        git(base, "init", "-q", str(semilla))
        commitear(semilla, "a.txt", "base\n")
        for nombre in REPOS:
            remoto = base / "remotos" / ("%s.git" % nombre)
            git(base, "init", "-q", "--bare", str(remoto))
            git(semilla, "push", "-q", str(remoto), "main")
            git(base, "clone", "-q", str(remoto), str(base / "repos" / nombre))
            git(base / "repos" / nombre, "remote", "set-url", "origin", remoto.as_posix())
        PLANTILLA.append(base)
    return PLANTILLA[0]


class Instancia:
    def __init__(self, config=None):
        self.config_cruda = config

    def __enter__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="auditar-ramas-")))
        try:
            return self._armar()
        except BaseException:
            self.__exit__()
            raise

    def _armar(self):
        self.raiz = self.base / "inst"
        (self.raiz / "tickets").mkdir(parents=True)
        self.repos, self.remotos, self.otras = {}, {}, {}
        plantilla = _plantilla()
        for carpeta in ("remotos", "repos"):
            shutil.copytree(str(plantilla / carpeta), str(self.base / carpeta))
        for nombre in REPOS:
            self.repos[nombre], self.remotos[nombre] = self.base / "repos" / nombre, self.base / "remotos" / ("%s.git" % nombre)
            config = self.repos[nombre] / ".git" / "config"
            texto = config.read_text(encoding="utf-8")
            config.write_text(texto.replace(plantilla.as_posix(), self.base.as_posix()), encoding="utf-8")
            assert git(self.repos[nombre], "remote", "get-url", "origin") == self.remotos[nombre].as_posix(), "la copia apunta a su remoto"
        config = {"schema_version": 1, "repos": {"web": {}, "db": {}}, "layers": {"web": {"extensions": [".cs"], "repos": ["web"]}}}
        escribir(self.raiz, "workspace.config.json", self.config_cruda if self.config_cruda is not None else json.dumps(config))
        escribir(self.raiz, "workspace.local.json", json.dumps({"repos": {n: {"path": str(r)} for n, r in self.repos.items()}}))
        return self

    def ticket(self, nombre, worktree_y_rama, carpeta="tickets"):
        escribir(self.raiz, "%s/%s/CLAUDE.md" % (carpeta, nombre), ticket_con(worktree_y_rama))

    def rama(self, repo, nombre, worktree=False):
        git(self.repos[repo], "branch", nombre, "main")
        if not worktree:
            return None
        carpeta = self.base / "wt" / ("%s-%s" % (repo, nombre.replace("/", "-")))
        git(self.repos[repo], "worktree", "add", "-q", str(carpeta), nombre)
        return carpeta

    def empujar(self, repo, rama):
        git(self.repos[repo], "push", "-q", "origin", rama)

    def otra(self, repo):
        if repo not in self.otras:
            carpeta = self.base / "otras" / repo
            git(self.base, "clone", "-q", str(self.remotos[repo]), str(carpeta))
            self.otras[repo] = carpeta
        git(self.otras[repo], "fetch", "-q", "origin")
        return self.otras[repo]

    def mergear(self, repo, rama, modo="merge"):
        otra = self.otra(repo)
        git(otra, "checkout", "-q", "-B", "main", "origin/main")
        if modo == "merge":
            git(otra, "merge", "-q", "--no-ff", "-m", "merge", "origin/" + rama)
        else:
            git(otra, "merge", "-q", "--squash", "origin/" + rama)
            git(otra, "commit", "-q", "-m", "squash")
        git(otra, "push", "-q", "origin", "main")

    def commit_en_otra(self, repo, rama):
        otra = self.otra(repo)
        git(otra, "checkout", "-q", "-B", rama, "origin/" + rama)
        sha = commitear(otra)
        git(otra, "push", "-q", "origin", rama)
        return sha

    def correr(self, *argv):
        return correr(["--raiz", self.raiz, *argv])

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def correr(argv, cwd=None):
    salida, error = io.StringIO(), io.StringIO()
    previo, previa = os.getcwd(), os.environ.pop("CLAUDE_PROJECT_DIR", None)
    try:
        if cwd is not None:
            os.chdir(cwd)
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = m().main([str(a) for a in argv])
    finally:
        os.chdir(previo)
        if previa is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = previa
    return codigo, salida.getvalue(), error.getvalue()


def test_sin_tickets_no_hay_nada_que_auditar_y_sale_con_0():
    with Instancia() as w:
        assert w.correr() == (0, NADA, "")
        w.ticket("T-2-sin-rama", "<ruta del worktree y rama, o «árbol principal»>")
        assert w.correr() == (0, NADA, ""), "un ticket sin nada reconocible no tiene nada que auditar"
        assert correr([], cwd=w.raiz / "tickets") == (0, NADA, ""), "sin --raiz, la instancia sale de la carpeta de la sesión"


def test_lo_que_llego_a_la_principal_sale_con_0_y_el_fetch_trae_el_merge_hecho_en_otra_maquina():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        git(w.repos["web"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["web"])
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "árbol principal, rama `feat/T-7`")
        w.mergear("web", "feat/T-7")
        assert w.correr() == (0, "T-7-algo: en web, la rama feat/T-7 llegó a origin/main.\n"
                                 "Resumen: todo llegó (1 rama de 1 ticket).\n", ""), "sin el fetch, la rama no estaría en origin/main"


def test_una_linea_por_ticket_y_repo_y_las_ramas_del_mismo_repo_van_juntas():
    with Instancia() as w:
        carpeta = w.rama("web", "feat/T-7-web", worktree=True)
        w.rama("web", "feat/T-7-otra")
        w.rama("db", "feat/T-7")
        w.ticket("T-7-algo", "\n  - web: `%s` y `feat/T-7-otra`\n  - db: árbol principal, `feat/T-7`" % carpeta)
        assert w.correr() == (0, "T-7-algo: en db, la rama feat/T-7 llegó a origin/main.\n"
                                 "T-7-algo: en web, la rama feat/T-7-otra llegó a origin/main; la rama feat/T-7-web llegó a origin/main.\n"
                                 "Resumen: todo llegó (3 ramas de 1 ticket).\n", ""), "ramas recién abiertas, sin nada propio"


def test_los_cambios_sin_commitear_y_los_commits_sin_empujar_son_pendientes_y_salen_con_1():
    with Instancia() as w:
        carpeta = w.rama("web", "feat/T-7", worktree=True)
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "`%s`" % carpeta)
        escribir(carpeta, "nuevo.txt", "sin agregar\n")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene cambios sin commitear.\n"
                                 "Resumen: no todo llegó: 1 rama pendiente, de 1 rama en 1 ticket.\n", "")
        os.remove(carpeta / "nuevo.txt")
        commitear(carpeta)
        commitear(carpeta)
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene 2 commits sin empujar y 2 commits que no llegaron a "
                                 "origin/main.\nResumen: no todo llegó: 1 rama pendiente, de 1 rama en 1 ticket.\n", "")


def test_una_rama_que_nunca_se_empujo_es_pendiente_solo_si_tiene_trabajo_fuera_de_la_principal():
    with Instancia() as w:
        w.rama("db", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        assert w.correr()[0] == 0, "recién abierta: no tiene nada propio que perder"
        git(w.repos["db"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["db"])
        assert w.correr() == (1, "T-7-algo: en db, la rama feat/T-7 nunca se empujó y tiene 1 commit que no llegó a origin/main.\n"
                                 "Resumen: no todo llegó: 1 rama pendiente, de 1 rama en 1 ticket.\n", "")
        git(w.repos["db"], "checkout", "-q", "main")
        git(w.repos["db"], "merge", "-q", "--ff-only", "feat/T-7")
        git(w.repos["db"], "push", "-q", "origin", "main")
        assert w.correr()[0] == 0, "mergeada a mano en main y main empujada: llegó aunque la rama nunca se empujó"


def test_el_trabajo_empujado_que_no_llego_a_la_principal_es_pendiente():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        git(w.repos["web"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["web"])
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene 1 commit que no llegó a origin/main.\n"
                                 "Resumen: no todo llegó: 1 rama pendiente, de 1 rama en 1 ticket.\n", "")


def test_un_squash_de_uno_o_de_varios_commits_cuenta_como_llegado():
    with Instancia() as w:
        for rama, commits in (("feat/T-1", 1), ("feat/T-2", 3)):
            w.rama("web", rama)
            git(w.repos["web"], "checkout", "-q", rama)
            for _ in range(commits):
                commitear(w.repos["web"])
            w.empujar("web", rama)
            w.mergear("web", rama, modo="squash")
        w.rama("web", "feat/T-3")
        git(w.repos["web"], "checkout", "-q", "feat/T-3")
        commitear(w.repos["web"], "c.txt", "se va\n")
        git(w.repos["web"], "revert", "--no-edit", "HEAD")
        w.empujar("web", "feat/T-3")
        git(w.repos["web"], "checkout", "-q", "main")
        w.ticket("T-1-uno", "`feat/T-1`")
        w.ticket("T-2-varios", "`feat/T-2`")
        w.ticket("T-3-neto", "`feat/T-3`")
        assert w.correr() == (0, "T-1-uno: en web, la rama feat/T-1 llegó a origin/main.\n"
                                 "T-2-varios: en web, la rama feat/T-2 llegó a origin/main.\n"
                                 "T-3-neto: en web, la rama feat/T-3 llegó a origin/main.\n"
                                 "Resumen: todo llegó (3 ramas de 3 tickets).\n", ""), "una rama cuyo diff entero es vacío no cambia nada"


def test_el_caso_sembrado_un_push_despues_del_merge_del_pr_no_llego_aunque_este_empujado():
    # «un push a una rama cuyo PR ya se mergeó sale bien, no corre CI y el commit nunca llega a la rama principal»
    with Instancia() as w:
        for rama, modo in (("feat/T-1", "merge"), ("feat/T-2", "squash")):
            w.rama("web", rama)
            git(w.repos["web"], "checkout", "-q", rama)
            commitear(w.repos["web"])
            commitear(w.repos["web"])
            w.empujar("web", rama)
            w.mergear("web", rama, modo=modo)
            commitear(w.repos["web"])
            w.empujar("web", rama)
        w.ticket("T-1-merge", "`feat/T-1`")
        w.ticket("T-2-squash", "`feat/T-2`")
        codigo, salida, error = w.correr()
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        assert salida.startswith("T-1-merge: en web, la rama feat/T-1 tiene 1 commit que no llegó a origin/main.\n"
                                 "T-2-squash: en web, la rama feat/T-2 tiene 3 commits que no llegaron a origin/main.\n"), salida


def test_el_caso_sembrado_con_el_push_desde_otra_maquina_lo_trae_el_fetch():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        git(w.repos["web"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["web"])
        w.empujar("web", "feat/T-7")
        w.mergear("web", "feat/T-7")
        git(w.repos["web"], "fetch", "-q", "origin")
        w.ticket("T-7-algo", "`feat/T-7`")
        assert w.correr()[0] == 0, "antes del push nuevo, todo llegó"
        w.commit_en_otra("web", "feat/T-7")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene 1 commit que no llegó a origin/main.\n"
                                 "Resumen: no todo llegó: 1 rama pendiente, de 1 rama en 1 ticket.\n", "")


def test_un_repo_cuyo_fetch_falla_sale_en_rojo_y_sus_ramas_no_se_juzgan_con_refs_viejas():
    with Instancia() as w:
        w.rama("db", "feat/T-7")
        w.rama("web", "feat/T-8")
        w.ticket("T-7-algo", "`feat/T-7`")
        w.ticket("T-8-otro", "`feat/T-8`")
        assert w.correr()[0] == 0, "control: con el fetch bien, las dos llegaron"
        git(w.repos["db"], "remote", "set-url", "origin", str(w.base / "remotos" / "no-existe.git"))
        codigo, salida, error = w.correr()
        lineas = salida.split("\n")
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        assert lineas[0] == "T-7-algo: en db, la rama feat/T-7 queda sin juzgar, porque el fetch del repo falló.", salida
        assert lineas[1] == "T-8-otro: en web, la rama feat/T-8 llegó a origin/main.", salida
        assert lineas[2].startswith("En rojo: db, porque el fetch falló (") and lineas[2].endswith(
            "). Sus ramas no se juzgan con refs viejas: arregla el acceso a su remoto y vuelve a auditar."), salida
        assert lineas[3:] == ["Resumen: no todo llegó: 1 rama sin juzgar y 1 repo en rojo, de 2 ramas en 2 tickets.", ""], salida
        os.remove(w.raiz / "tickets" / "T-7-algo" / "CLAUDE.md")
        codigo, salida, error = w.correr()
        assert codigo == 1 and "En rojo: db" in salida, "un repo en rojo sin ramas de tickets igual sale con 1"


def test_un_fetch_que_no_termina_a_tiempo_es_rojo_y_los_tickets_que_no_se_revisaron_lo_dicen():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        original = m().auditoria_de_ramas.PLAZO_POR_REPO
        m().auditoria_de_ramas.PLAZO_POR_REPO = -1
        try:
            codigo, salida, error = w.correr()
        finally:
            m().auditoria_de_ramas.PLAZO_POR_REPO = original
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        assert "Tickets sin revisar, porque no alcanzó el tiempo: T-7-algo." in salida, salida
        assert "En rojo: db, porque el fetch falló (no terminó a tiempo)" in salida and "En rojo: web" in salida, salida


def test_archivados_suma_los_tickets_archivados():
    with Instancia() as w:
        w.rama("web", "feat/T-1")
        git(w.repos["web"], "checkout", "-q", "feat/T-1")
        commitear(w.repos["web"])
        git(w.repos["web"], "checkout", "-q", "main")
        w.ticket("T-1-viejo", "`feat/T-1`", carpeta="tickets/archivo/2025")
        w.ticket("_plantilla", "`feat/T-1`")
        assert w.correr() == (0, NADA, ""), "sin --archivados, un ticket archivado no cuenta"
        assert w.correr("--archivados") == (1, "archivo/2025/T-1-viejo: en web, la rama feat/T-1 nunca se empujó y tiene 1 commit que "
                                               "no llegó a origin/main.\nResumen: no todo llegó: 1 rama pendiente, de 1 rama en 1 ticket.\n",
                                            "")


def test_json_da_cada_rama_con_su_estado_y_sus_faltas():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        git(w.repos["web"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["web"])
        w.empujar("web", "feat/T-7")
        commitear(w.repos["web"])
        w.rama("db", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        w.ticket("T-8-nada", "árbol principal")
        git(w.repos["db"], "remote", "set-url", "origin", str(w.base / "remotos" / "no-existe.git"))
        codigo, salida, error = w.correr("--json")
        assert (codigo, error) == (1, ""), (codigo, salida, error)
        datos = json.loads(salida)
        assert set(datos) == {"todo_llego", "repos", "ramas", "tickets_sin_ramas", "tickets_sin_revisar"}, datos
        assert datos["todo_llego"] is False and datos["tickets_sin_ramas"] == ["T-8-nada"] and datos["tickets_sin_revisar"] == []
        assert [r["repo"] for r in datos["repos"]] == ["db", "web"] and [r["rojo"] for r in datos["repos"]] == [True, False], datos["repos"]
        assert datos["repos"][0]["motivo"] and datos["repos"][1]["motivo"] is None, datos["repos"]
        db, web = datos["ramas"]
        assert db == {"ticket": "T-7-algo", "repo": "db", "rama": "feat/T-7", "carpeta": None, "principal": None, "estado": "sin_juzgar",
                      "motivo": "repo_en_rojo", "faltas": [], "texto": "queda sin juzgar, porque el fetch del repo falló"}, db
        assert web["estado"] == "pendiente" and web["motivo"] is None and web["principal"] == "origin/main", web
        assert web["faltas"] == [{"tipo": "sin_empujar", "commits": 1}, {"tipo": "no_llego", "commits": 2}], web
        assert Path(web["carpeta"]) == w.repos["web"] and web["texto"].startswith("tiene 1 commit sin empujar"), web


def test_errores_de_uso_o_de_entorno_salen_con_2():
    with Instancia() as w:
        for argv in (["--no-existe"], ["--json", "sobra"], ["--archi"]):
            codigo, salida, error = w.correr(*argv)
            assert codigo == 2 and salida == "" and error, (argv, codigo, salida, error)
        codigo, salida, error = correr(["--raiz", w.raiz / "tickets"])
        assert codigo == 2 and salida == "" and "workspace.config.json" in error, (codigo, salida, error)
        codigo, salida, error = correr([], cwd=w.base)
        assert codigo == 2 and salida == "" and "--raiz" in error, (codigo, salida, error)
    with Instancia(config="{ rota") as w:
        codigo, salida, error = w.correr()
        assert codigo == 2 and salida == "" and "la config está rota" in error, (codigo, salida, error)


def _foto(arbol):
    fotos = {}
    for actual, carpetas, archivos in os.walk(str(arbol)):
        carpetas[:] = sorted(c for c in carpetas if c != ".git")
        for nombre in sorted(archivos):
            ruta = os.path.join(actual, nombre)
            if nombre != ".git":
                fotos[os.path.relpath(ruta, str(arbol))] = hashlib.sha256(Path(ruta).read_bytes()).hexdigest()
    return fotos


def _estado_del_repo(repo, arboles):
    gitdir = Path(repo) / ".git"
    archivos = {}
    for nombre in ("index", "HEAD", "config", "FETCH_HEAD", "ORIG_HEAD", "logs/HEAD"):
        ruta = gitdir / nombre
        archivos[nombre] = hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else None
    for indice in sorted((gitdir / "worktrees").glob("*/index")):
        archivos[str(indice.relative_to(gitdir))] = hashlib.sha256(indice.read_bytes()).hexdigest()
    refs = [linea for linea in git(repo, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
            if not linea.startswith("refs/remotes/origin/")]
    return {"refs": refs, "archivos": archivos, "arboles": [_foto(a) for a in arboles]}


def test_no_escribe_nada_salvo_las_refs_de_origin_aunque_el_remoto_tenga_otros_mapeos_configurados():
    with Instancia() as w:
        carpeta = w.rama("web", "feat/T-7", worktree=True)
        commitear(carpeta)
        escribir(carpeta, "a.txt", "editado y sin commitear\n")
        escribir(carpeta, "nuevo.txt", "sin agregar\n")
        git(w.repos["web"], "tag", "v1")
        git(w.repos["web"], "config", "--replace-all", "remote.origin.fetch", "+refs/heads/*:refs/remotes/espejo/*")
        git(w.repos["web"], "config", "--add", "remote.origin.fetch", "+refs/heads/feat/*:refs/heads/copia/feat/*")
        git(w.repos["web"], "branch", "copia/feat/x", "main")
        w.ticket("T-7-algo", "`%s`" % carpeta)
        w.commit_en_otra("web", "main")
        git(w.otra("web"), "push", "-q", "origin", "main:refs/heads/feat/x")
        antes = _estado_del_repo(w.repos["web"], [w.repos["web"], carpeta])
        remotas = git(w.repos["web"], "for-each-ref", "refs/remotes/origin/")
        assert w.correr()[0] == 1
        despues = _estado_del_repo(w.repos["web"], [w.repos["web"], carpeta])
        assert despues["refs"] == antes["refs"], "solo cambian las refs de origin: %s" % sorted(set(despues["refs"]) ^ set(antes["refs"]))
        assert despues == antes
        assert git(w.repos["web"], "for-each-ref", "refs/remotes/origin/") != remotas, "control: el fetch sí movió origin/main"


class ServidorQuePideCredencial:
    def __enter__(self):
        class Pide(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="odd"')
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_):
                pass

        self.servidor = http.server.HTTPServer(("127.0.0.1", 0), Pide)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d/db.git" % self.servidor.server_port

    def __exit__(self, *_):
        self.servidor.shutdown()
        self.servidor.server_close()


def test_un_remoto_que_pide_credencial_sale_en_rojo_enseguida_sin_llamar_al_askpass_del_entorno():
    with Instancia() as w, ServidorQuePideCredencial() as url:
        marca = w.base / "askpass-llamado"
        askpass = escribir(w.base, "askpass.sh", "#!/bin/sh\necho llamado >> '%s'\nsleep 12\n" % marca.as_posix())
        os.chmod(str(askpass), 0o755)
        git(w.repos["db"], "remote", "set-url", "origin", url)
        previo = {k: os.environ.get(k) for k in ("GIT_ASKPASS", "NO_PROXY", "no_proxy")}
        os.environ.update(GIT_ASKPASS=askpass.as_posix(), NO_PROXY="127.0.0.1", no_proxy="127.0.0.1")
        plazo = m().auditoria_de_ramas.PLAZO_POR_REPO
        m().auditoria_de_ramas.PLAZO_POR_REPO = 10
        try:
            codigo, salida, error = w.correr()
        finally:
            m().auditoria_de_ramas.PLAZO_POR_REPO = plazo
            for clave, valor in previo.items():
                if valor is None:
                    os.environ.pop(clave, None)
                else:
                    os.environ[clave] = valor
        assert (codigo, error) == (1, "") and "En rojo: db, porque el fetch falló (" in salida, (codigo, salida, error)
        assert "no terminó a tiempo" not in salida, "git falla solo, sin esperar al plazo: %s" % salida
        assert not marca.exists(), "el askpass del entorno no se llama"


def test_la_cli_como_proceso_sale_con_su_codigo_y_escribe_utf8_aunque_la_consola_no_lo_sea():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        git(w.repos["web"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["web"])
        w.ticket("T-7-algo", "`feat/T-7`")
        entorno = {k: v for k, v in _entorno_sin_git().items() if k != "CLAUDE_PROJECT_DIR"}
        entorno["PYTHONIOENCODING"] = "cp1252"
        r = subprocess.run([sys.executable, str(SCRIPT), "--raiz", str(w.raiz)], capture_output=True, env=entorno)
        assert r.returncode == 1, (r.returncode, r.stderr)
        assert r.stdout.decode("utf-8").replace("\r\n", "\n").startswith(
            "T-7-algo: en web, la rama feat/T-7 nunca se empujó y tiene 1 commit que no llegó a origin/main.\n"), r.stdout
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, env=entorno)
        assert r.returncode == 0 and all(o in r.stdout for o in (b"--archivados", b"--json", b"--raiz")), (r.returncode, r.stdout)


@contextlib.contextmanager
def git_aislado():
    carpeta = Path(tempfile.mkdtemp(prefix="auditar-ramas-git-"))
    (carpeta / "global").write_bytes(b"")
    (carpeta / "sistema").write_bytes(b"")
    previo = {k: os.environ.get(k) for k in AISLAMIENTO_GIT}
    os.environ.update(GIT_CONFIG_GLOBAL=str(carpeta / "global"), GIT_CONFIG_SYSTEM=str(carpeta / "sistema"), GIT_CONFIG_NOSYSTEM="1")
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


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    pruebas = [(nombre, funcion) for nombre, funcion in globals().items() if nombre.startswith("test_") and callable(funcion)]
    fallas = 0
    with git_aislado():
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
        for plantilla in PLANTILLA:
            shutil.rmtree(plantilla, onexc=_quitar)
            if plantilla.exists():
                SOBRANTES.append(str(plantilla))
    if SOBRANTES:
        fallas += 1
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
