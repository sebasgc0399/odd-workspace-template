import sys

sys.dont_write_bytecode = True

import contextlib
import importlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "entregas.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
AISLAMIENTO_GIT = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
HUELLA_RE = re.compile(r"[0-9a-f]{64}")
NADA = "nada pendiente\n"


def m():
    return importlib.import_module("entregas")


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
                        "-c", "init.defaultBranch=main", "-c", "maintenance.auto=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno_sin_git())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def escribir(raiz, rel, texto):
    p = Path(raiz) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texto.encode("utf-8"))
    return p


def commitear(carpeta, rel="a.txt", texto=None):
    escribir(carpeta, rel, texto if texto is not None else "%s\n" % os.urandom(4).hex())
    git(carpeta, "add", "-A")
    git(carpeta, "commit", "-q", "-m", "c")
    return git(carpeta, "rev-parse", "HEAD")


def ticket_con(worktree_y_rama):
    return ("# T — algo\n\n## Objetivo\n\nalgo\n\n## Contexto técnico\n\n- Repos y capas afectados: web\n"
            "- Worktree y rama: %s\n- Dependencias o bloqueos: `feat/fuera` no cuenta acá\n" % worktree_y_rama)


class Instancia:
    def __init__(self, config=None):
        self.config_cruda = config

    def __enter__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="entregas-cli-")))
        self.raiz = self.base / "inst"
        (self.raiz / "tickets").mkdir(parents=True)
        self.repos = {}
        for nombre in ("web", "db"):
            repo = self.base / "repos" / nombre
            repo.mkdir(parents=True)
            git(repo, "init", "-q")
            commitear(repo)
            git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
            self.repos[nombre] = repo
        config = {"schema_version": 1, "repos": {"web": {}, "db": {}}, "layers": {"web": {"extensions": [".cs"], "repos": ["web"]}}}
        escribir(self.raiz, "workspace.config.json", self.config_cruda if self.config_cruda is not None else json.dumps(config))
        escribir(self.raiz, "workspace.local.json", json.dumps({"repos": {n: {"path": str(r)} for n, r in self.repos.items()}}))
        return self

    def ticket(self, nombre, worktree_y_rama, carpeta="tickets"):
        escribir(self.raiz, "%s/%s/CLAUDE.md" % (carpeta, nombre), ticket_con(worktree_y_rama))

    def rama(self, repo, nombre, worktree=False):
        git(self.repos[repo], "branch", nombre)
        if not worktree:
            return None
        carpeta = self.base / "wt" / ("%s-%s" % (repo, nombre.replace("/", "-")))
        git(self.repos[repo], "worktree", "add", "-q", str(carpeta), nombre)
        return carpeta

    def empujar(self, repo, rama):
        git(self.repos[repo], "update-ref", "refs/remotes/origin/" + rama, "refs/heads/" + rama)

    def correr(self, *argv):
        return correr(["--raiz", self.raiz, *argv])

    def confirmadas(self):
        ruta = self.raiz / ".claude" / "estado" / "entregas.json"
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None

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


def test_sin_tickets_o_con_todo_entregado_dice_nada_pendiente_y_sale_con_0():
    with Instancia() as w:
        assert w.correr() == (0, NADA, ""), "sin tickets"
        carpeta = w.rama("web", "feat/T-7", worktree=True)
        commitear(carpeta)
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "`%s`, rama `feat/T-7`" % carpeta)
        assert w.correr() == (0, NADA, ""), "rama empujada y carpeta limpia"
        assert correr([], cwd=w.raiz / "tickets") == (0, NADA, ""), "sin --raiz, la instancia sale de la carpeta de la sesión"
        assert w.confirmadas() is None, "listar no escribe nada"


def test_un_cambio_sin_commitear_en_la_carpeta_de_la_rama_es_una_entrega_pendiente():
    with Instancia() as w:
        carpeta = w.rama("web", "feat/T-7", worktree=True)
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "worktree en `%s`, rama `feat/T-7`" % carpeta)
        escribir(carpeta, "nuevo.txt", "sin agregar\n")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene cambios sin commitear.\n", "")
        os.remove(carpeta / "nuevo.txt")
        escribir(carpeta, "a.txt", "editado\n")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene cambios sin commitear.\n", ""), "un archivo trackeado editado"


def test_un_commit_que_no_esta_en_origin_de_la_rama_es_una_entrega_pendiente():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "árbol principal, rama `feat/T-7`")
        git(w.repos["web"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["web"])
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene 1 commit sin empujar.\n", "")
        commitear(w.repos["web"])
        escribir(w.repos["web"], "a.txt", "sin commitear\n")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene cambios sin commitear y 2 commits sin empujar.\n", "")
        git(w.repos["web"], "checkout", "-q", "--", "a.txt")
        w.empujar("web", "feat/T-7")
        assert w.correr() == (0, NADA, ""), "con origin al día calla"
        git(w.repos["web"], "update-ref", "refs/remotes/origin/feat/T-7", commitear(w.repos["web"]))
        git(w.repos["web"], "reset", "-q", "--hard", "HEAD~1")
        assert w.correr() == (0, NADA, ""), "una rama atrás de su origin no tiene nada sin empujar"


def test_una_rama_sin_origin_nunca_se_empujo_aunque_no_tenga_commits_propios():
    with Instancia() as w:
        carpeta = w.rama("db", "feat/T-7", worktree=True)
        w.ticket("T-7-algo", "`%s` (`feat/T-7`)" % carpeta)
        assert w.correr() == (1, "T-7-algo: en db, la rama feat/T-7 nunca se empujó.\n", "")
        escribir(carpeta, "b.txt", "x\n")
        assert w.correr() == (1, "T-7-algo: en db, la rama feat/T-7 nunca se empujó y tiene cambios sin commitear.\n", "")


def test_la_carpeta_de_un_repo_da_la_rama_de_su_head_y_cada_repo_va_en_la_misma_linea_del_ticket():
    with Instancia() as w:
        carpeta = w.rama("web", "feat/T-7-web", worktree=True)
        w.rama("db", "feat/T-7")
        w.ticket("T-7-algo", "\n  - web: `%s`\n  - db: árbol principal, `feat/T-7`" % carpeta)
        assert w.correr() == (1, "T-7-algo: en db, la rama feat/T-7 nunca se empujó; en web, la rama feat/T-7-web nunca se empujó.\n", "")
        git(carpeta, "checkout", "-q", "--detach")
        assert w.correr() == (1, "T-7-algo: en db, la rama feat/T-7 nunca se empujó.\n", ""), "una carpeta sin rama en HEAD no da nada"


def test_una_rama_que_existe_en_dos_repos_cuenta_en_los_dos():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.rama("db", "feat/T-7")
        w.empujar("db", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7` en web y db")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 nunca se empujó.\n", "")
        git(w.repos["db"], "checkout", "-q", "feat/T-7")
        commitear(w.repos["db"])
        assert w.correr() == (1, "T-7-algo: en db, la rama feat/T-7 tiene 1 commit sin empujar; "
                                 "en web, la rama feat/T-7 nunca se empujó.\n", "")


def test_un_ticket_archivado_la_plantilla_y_uno_sin_nada_reconocible_callan():
    with Instancia() as w:
        w.rama("web", "feat/T-1")
        w.rama("web", "feat/fuera")
        for carpeta in ("tickets/archivo", "tickets/archivo/2025"):
            w.ticket("T-1-viejo", "`feat/T-1`", carpeta=carpeta)
        w.ticket("_plantilla", "`feat/T-1`")
        w.ticket("T-2-sin-rama", "<ruta del worktree y rama, o «árbol principal»>")
        w.ticket("T-3-otra", "`feat/no-existe`, `%s`" % (w.base / "no-existe"))
        escribir(w.raiz, "tickets/T-4-sin-claude/notas.md", ticket_con("`feat/T-1`"))
        assert w.correr() == (0, NADA, "")
        w.ticket("T-1-vivo", "`feat/T-1`")
        assert w.correr() == (1, "T-1-vivo: en web, la rama feat/T-1 nunca se empujó.\n", ""), "control positivo"


def test_confirmar_guarda_la_huella_y_el_ticket_calla_hasta_que_cambian_sus_archivos_o_sus_ramas():
    with Instancia() as w:
        carpeta = w.rama("web", "feat/T-7", worktree=True)
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "`%s`, `feat/T-7`" % carpeta)
        escribir(carpeta, "a.txt", "editado\n")
        codigo, salida, error = w.correr("--confirmar", "T-7-algo")
        assert (codigo, error) == (0, "") and salida.startswith("T-7-algo: confirmado."), (codigo, salida, error)
        datos = w.confirmadas()
        assert set(datos) == {"version", "confirmadas"} and datos["version"] == 1 and list(datos["confirmadas"]) == ["T-7-algo"], datos
        entrada = datos["confirmadas"]["T-7-algo"]
        assert set(entrada) == {"huella", "fecha"} and HUELLA_RE.fullmatch(entrada["huella"]), entrada
        assert w.correr() == (0, NADA, ""), "confirmado calla"
        escribir(carpeta, "nueva/carpeta/x.txt", "uno\n")
        assert w.correr()[0] == 1, "un archivo nuevo"
        assert w.correr("--confirmar", "T-7-algo")[0] == 0 and w.correr() == (0, NADA, "")
        escribir(carpeta, "nueva/carpeta/x.txt", "dos\n")
        assert w.correr()[0] == 1, "un archivo sin trackear con otro contenido"
        os.remove(carpeta / "nueva" / "carpeta" / "x.txt")
        assert w.correr()[0] == 1, "un archivo que se borró"
        assert w.correr("--confirmar", "T-7-algo")[0] == 0 and w.correr() == (0, NADA, "")
        escribir(carpeta, "a.txt", "editado otra vez\n")
        assert w.correr() == (1, "T-7-algo: en web, la rama feat/T-7 tiene cambios sin commitear.\n", ""), "el mismo archivo con otro contenido"
        assert w.correr("--confirmar", "T-7")[0] == 0 and w.correr() == (0, NADA, ""), "se confirma también por el id"
        commitear(carpeta)
        escribir(carpeta, "a.txt", "editado otra vez\n")
        assert w.correr()[0] == 1, "un commit nuevo cambia la cabeza de la rama"
        w.correr("--confirmar", "T-7-algo")
        w.empujar("web", "feat/T-7")
        assert w.correr()[0] == 1, "un origin que se movió también cambia la huella"


def test_confirmar_un_ticket_sin_nada_pendiente_no_guarda_nada():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.empujar("web", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        codigo, salida, error = w.correr("--confirmar", "T-7-algo")
        assert (codigo, error) == (0, "") and salida.startswith("T-7-algo: no tiene nada pendiente"), (codigo, salida, error)
        assert w.confirmadas() is None


def test_confirmar_conserva_los_otros_tickets_activos_y_suelta_los_que_ya_no_lo_son():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.rama("web", "feat/T-8")
        w.ticket("T-7-algo", "`feat/T-7`")
        w.ticket("T-8-otro", "`feat/T-8`")
        assert w.correr("--confirmar", "T-7-algo")[0] == 0 and w.correr("--confirmar", "T-8-otro")[0] == 0
        assert sorted(w.confirmadas()["confirmadas"]) == ["T-7-algo", "T-8-otro"]
        (w.raiz / "tickets" / "archivo").mkdir()
        shutil.move(str(w.raiz / "tickets" / "T-7-algo"), str(w.raiz / "tickets" / "archivo" / "T-7-algo"))
        w.rama("web", "feat/T-9")
        w.ticket("T-9-mas", "`feat/T-9`")
        assert w.correr("--confirmar", "T-9-mas")[0] == 0
        assert sorted(w.confirmadas()["confirmadas"]) == ["T-8-otro", "T-9-mas"], w.confirmadas()


def test_un_entregas_json_roto_no_confirma_nada_y_confirmar_lo_rehace():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        pendiente = (1, "T-7-algo: en web, la rama feat/T-7 nunca se empujó.\n", "")
        for roto in ("{roto", "[]", json.dumps({"version": 9, "confirmadas": {}}), json.dumps({"version": 1, "confirmadas": {"T-7-algo": 5}})):
            escribir(w.raiz, ".claude/estado/entregas.json", roto)
            assert w.correr() == pendiente, roto
        assert w.correr("--confirmar", "T-7-algo")[0] == 0 and w.correr() == (0, NADA, "")


def test_errores_de_uso_o_de_entorno_salen_con_2():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        w.ticket("T-7-otro", "`feat/T-7`")
        for argv, rastro in ((["--no-existe"], "--no-existe"), (["--confirmar"], "--confirmar"),
                             (["--confirmar", "T-9"], "no hay un ticket activo"), (["--confirmar", "T-7"], "T-7-algo, T-7-otro")):
            codigo, salida, error = w.correr(*argv)
            assert codigo == 2 and salida == "" and rastro in error, (argv, codigo, salida, error)
        assert w.confirmadas() is None
        codigo, salida, error = correr(["--raiz", w.raiz / "tickets"])
        assert codigo == 2 and salida == "" and "workspace.config.json" in error, (codigo, salida, error)
        codigo, salida, error = correr([], cwd=w.base)
        assert codigo == 2 and salida == "" and "--raiz" in error, (codigo, salida, error)
    with Instancia(config="{ rota") as w:
        codigo, salida, error = w.correr()
        assert codigo == 2 and salida == "" and "la config está rota" in error, (codigo, salida, error)


def test_sin_tiempo_lo_dice_en_una_linea_no_cuenta_como_limpio_y_no_confirma():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        w.ticket("T-8-otro", "`feat/T-8`")
        w.ticket("T-9-nada", "sin ramas")
        original = m().entregas.PLAZO_DEL_CLI
        m().entregas.PLAZO_DEL_CLI = -1
        try:
            assert w.correr() == (1, "quedaron 2 tickets sin revisar (no alcanzó el tiempo), así que no cuentan como limpios.\n", "")
            codigo, salida, error = w.correr("--confirmar", "T-7-algo")
            assert codigo == 2 and salida == "" and "no alcanzó el tiempo" in error, (codigo, salida, error)
        finally:
            m().entregas.PLAZO_DEL_CLI = original
        assert w.confirmadas() is None


def test_la_cli_como_proceso_sale_con_su_codigo_y_escribe_utf8_aunque_la_consola_no_lo_sea():
    with Instancia() as w:
        w.rama("web", "feat/T-7")
        w.ticket("T-7-algo", "`feat/T-7`")
        entorno = {k: v for k, v in _entorno_sin_git().items() if k != "CLAUDE_PROJECT_DIR"}
        entorno["PYTHONIOENCODING"] = "cp1252"
        r = subprocess.run([sys.executable, str(SCRIPT), "--raiz", str(w.raiz)], capture_output=True, env=entorno)
        assert r.returncode == 1, (r.returncode, r.stderr)
        assert r.stdout.decode("utf-8").replace("\r\n", "\n") == "T-7-algo: en web, la rama feat/T-7 nunca se empujó.\n", r.stdout
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, env=entorno)
        assert r.returncode == 0 and b"--confirmar" in r.stdout and b"--raiz" in r.stdout, (r.returncode, r.stdout)


@contextlib.contextmanager
def git_aislado():
    carpeta = Path(tempfile.mkdtemp(prefix="entregas-cli-git-"))
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
    if SOBRANTES:
        fallas += 1
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
