import sys

sys.dont_write_bytecode = True

import importlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
SOBRANTES = []

import config_loader


def m():
    return importlib.import_module("odd_ws.entregas")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def escribir(raiz, rel, texto):
    p = Path(raiz) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texto.encode("utf-8"))
    return p


class Carpeta:
    def __enter__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="entregas-lib-")))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


class SinGit:
    def __enter__(self):
        self.original, self.llamadas = subprocess.run, []

        def prohibido(*args, **kwargs):
            self.llamadas.append(args)
            raise AssertionError("no tenía que correr git: %r" % (args,))

        subprocess.run = prohibido
        return self

    def __exit__(self, *_):
        subprocess.run = self.original


TICKET = """# T-7 — algo

## Contexto técnico

- Repos y capas afectados: `web`
- **Worktree y rama:** `C:/wt/web-T-7` con `feat/T-7`
  - db: árbol principal, rama `feat/T-7-db` y otra vez `feat/T-7`

  - `feat/T-7-tras-un-blanco`
- Dependencias o bloqueos: `feat/fuera`

## Specs

- Worktree y rama: `feat/T-7-segunda`
"""


def test_los_fragmentos_salen_de_la_linea_de_worktree_y_rama_y_de_sus_vinetas_en_orden_y_sin_repetir():
    assert m().fragmentos(TICKET) == ["C:/wt/web-T-7", "feat/T-7", "feat/T-7-db", "feat/T-7-tras-un-blanco", "feat/T-7-segunda"]
    assert m().fragmentos(TICKET.replace("\n", "\r\n")) == m().fragmentos(TICKET), "con CRLF da lo mismo"
    plantilla = "- Worktree y rama: <ruta del worktree y rama, o «árbol principal»>\n- Paso 0: `x`\n"
    assert m().fragmentos(plantilla) == [], "el molde de la plantilla no trae fragmentos"
    assert m().fragmentos("Worktree y rama: `feat/T-7`\n") == [], "sin viñeta no es la línea del ticket"
    assert m().fragmentos("* worktree y rama: `feat/a` y ` feat/b `\n") == ["feat/a", "feat/b"], "otra viñeta, otras mayúsculas y espacios"
    assert m().fragmentos("") == []


def test_los_tickets_activos_son_los_hijos_directos_de_tickets_con_su_claude_md_sin_la_plantilla():
    with Carpeta() as raiz:
        for rel in ("tickets/T-2-b/CLAUDE.md", "tickets/T-1-a/CLAUDE.md", "tickets/_plantilla/CLAUDE.md", "tickets/archivo/T-3-c/CLAUDE.md",
                    "tickets/T-4-sin/notas.md", "otra/T-5-e/CLAUDE.md"):
            escribir(raiz, rel, "x\n")
        assert m().activos(str(raiz)) == ["T-1-a", "T-2-b"]
    with Carpeta() as raiz:
        assert m().activos(str(raiz)) == [], "sin tickets/"


def _config(raiz, repos=("web",)):
    return {"raiz": str(raiz), "repos": {nombre: {"path": str(Path(raiz) / nombre), "worktrees": []} for nombre in repos}, "layers": {}}


def test_sin_tiempo_no_corre_git_y_cuenta_solo_los_tickets_con_algo_que_chequear():
    with Carpeta() as raiz:
        escribir(raiz, "tickets/T-1-a/CLAUDE.md", "- Worktree y rama: `feat/T-1`\n")
        escribir(raiz, "tickets/T-2-b/CLAUDE.md", "- Worktree y rama: árbol principal\n")
        escribir(raiz, "tickets/T-3-c/CLAUDE.md", "- Worktree y rama: `feat/T-3`\n")
        with SinGit() as guardia:
            revision = m().revisar(_config(raiz), time.monotonic() - 1)
            assert revision == m().Revision([], 2, 0), revision
            assert m().revisar(_config(raiz, repos=()), time.monotonic() - 1) == m().Revision([], 0, 0), "sin repos no hay nada reconocible"
            os.remove(raiz / "tickets" / "T-1-a" / "CLAUDE.md")
            os.remove(raiz / "tickets" / "T-3-c" / "CLAUDE.md")
            assert m().revisar(_config(raiz), time.monotonic() - 1) == m().Revision([], 0, 0), "nada que chequear"
        assert not guardia.llamadas


def test_el_tope_deja_fuera_los_tickets_que_siguen_en_orden_y_los_cuenta():
    with Carpeta() as raiz:
        for n in range(1, 26):
            escribir(raiz, "tickets/T-%02d-x/CLAUDE.md" % n, "- Worktree y rama: `feat/T-%d`\n" % n)
        with SinGit():
            assert m().revisar(_config(raiz), time.monotonic() - 1, tope=20) == m().Revision([], 20, 5)
            assert m().revisar(_config(raiz), time.monotonic() - 1) == m().Revision([], 25, 0), "sin tope cuenta todos"


def test_entregas_de_da_las_ramas_de_cada_ticket_en_su_orden_y_lee_git_recien_cuando_hace_falta():
    with Carpeta() as raiz:
        escribir(raiz, "tickets/T-1-a/CLAUDE.md", "- Worktree y rama: `feat/T-1`\n")
        escribir(raiz, "tickets/archivo/T-2-b/CLAUDE.md", "- Worktree y rama: `feat/T-2`\n")
        escribir(raiz, "tickets/T-3-c/CLAUDE.md", "- Worktree y rama: árbol principal\n")
        tickets = ["T-1-a", "archivo/T-2-b", "T-3-c", "T-9-no-existe"]
        with SinGit() as guardia:
            assert list(m().entregas_de(_config(raiz, repos=()), tickets, time.monotonic() - 1)) == [(t, []) for t in tickets], \
                "sin repos no hay ramas, y no corre git"
            pendientes = m().entregas_de(_config(raiz), ["T-3-c", "T-1-a"], time.monotonic() - 1)
            assert next(pendientes) == ("T-3-c", []), "un ticket sin fragmentos no lee las refs"
            try:
                next(pendientes)
                raise AssertionError("sin tiempo, el ticket con una rama tenía que cortar")
            except subprocess.TimeoutExpired:
                pass
        assert not guardia.llamadas


CABEZA, ATRAS = "a" * 40, "b" * 40
SUCIO = b"? nuevo.txt\0"
RANGO = "refs/remotes/origin/%s..refs/heads/%s"


def _clave(lectura):
    return config_loader.canonica(str(lectura)) if isinstance(lectura, Path) else lectura


class GitFalso:
    def __init__(self, ramas, sucias=(), demora=0.0, lentas=(), rotas=()):
        self.ramas, self.demora = ramas, demora
        self.sucias = {_clave(c) for c in sucias}
        self.lentas, self.rotas = {_clave(c) for c in lentas}, {_clave(c) for c in rotas}
        self.llamadas, self.en_curso, self.maximo = [], 0, 0
        self.candado = threading.Lock()

    def __enter__(self):
        self.original = m()._git
        m()._git = self
        return self

    def __exit__(self, *_):
        m()._git = self.original

    def cuantas(self, comando):
        return sum(1 for hecho, _ in self.llamadas if hecho == comando)

    def _refs(self, repo):
        lineas = []
        for rama, carpeta, origen in self.ramas.get(repo, ()):
            lineas.append("refs/heads/%s\0%s\0%s" % (rama, CABEZA, carpeta or ""))
            if origen:
                lineas.append("refs/remotes/origin/%s\0%s\0" % (rama, origen))
        return subprocess.CompletedProcess(["git"], 0, "\n".join(lineas).encode("utf-8"), b"")

    def __call__(self, arbol, limite, *args):
        restante = limite - time.monotonic()
        if restante <= 0:
            raise subprocess.TimeoutExpired(["git", *args], 0)
        if args[0] == "for-each-ref":
            return self._refs(os.path.basename(str(arbol)))
        clave = config_loader.canonica(str(arbol)) if args[0] == "status" else args[-1]
        with self.candado:
            self.llamadas.append((args[0], clave))
            self.en_curso += 1
            self.maximo = max(self.maximo, self.en_curso)
        try:
            if clave in self.lentas:
                time.sleep(restante)
                raise subprocess.TimeoutExpired(["git", *args], restante)
            time.sleep(self.demora)
            if clave in self.rotas:
                raise OSError("no se pudo lanzar git")
        finally:
            with self.candado:
                self.en_curso -= 1
        salida = (SUCIO if clave in self.sucias else b"") if args[0] == "status" else b"2\n"
        return subprocess.CompletedProcess(["git", *args], 0, salida, b"")


def _tickets_con_worktree(raiz, cuantos):
    carpetas = {}
    for n in range(1, cuantos + 1):
        carpetas[n] = raiz / "wt" / ("T-%d" % n)
        carpetas[n].mkdir(parents=True)
        escribir(raiz, "tickets/T-%d-x/CLAUDE.md" % n, "- Worktree y rama: `feat/T-%d`\n" % n)
    return carpetas


def _lineas(revision):
    return [m().linea(ticket, pendiente) for ticket, pendiente in revision.pendientes]


def test_los_status_y_los_rev_list_corren_en_paralelo_con_un_tope_de_hilos_y_alcanzan_un_plazo_que_en_serie_no():
    with Carpeta() as raiz:
        carpetas = _tickets_con_worktree(raiz, 8)
        ramas = {"web": [("feat/T-%d" % n, str(c), CABEZA if n <= 4 else ATRAS) for n, c in carpetas.items()]}
        with GitFalso(ramas, sucias=[carpetas[n] for n in range(1, 5)], demora=0.3) as falso:
            revision = m().revisar(_config(raiz), time.monotonic() + 2.0)
        esperadas = (["T-%d-x: en web, la rama feat/T-%d tiene cambios sin commitear." % (n, n) for n in range(1, 5)]
                     + ["T-%d-x: en web, la rama feat/T-%d tiene 2 commits sin empujar." % (n, n) for n in range(5, 9)])
        assert _lineas(revision) == esperadas and revision[1:] == (0, 0), "12 lecturas de 0,3 s en serie no caben en 2 s: %r" % (revision,)
        assert (falso.cuantas("status"), falso.cuantas("rev-list")) == (8, 4), falso.llamadas
        assert falso.maximo == m().HILOS == 4, "a lo sumo 4 a la vez, y las 4 a la vez: %d" % falso.maximo


def test_cada_carpeta_se_consulta_una_sola_vez_aunque_la_nombren_varios_tickets_o_con_otra_grafia():
    with Carpeta() as raiz:
        carpeta = raiz / "wt" / "T-1"
        carpeta.mkdir(parents=True)
        otra_grafia = os.path.join(str(carpeta.parent), ".", carpeta.name) + os.sep
        ramas = {"web": [("feat/T-1", str(carpeta), CABEZA)], "db": [("feat/T-2", otra_grafia, CABEZA)]}
        escribir(raiz, "tickets/T-1-a/CLAUDE.md", "- Worktree y rama: `feat/T-1`\n")
        escribir(raiz, "tickets/T-2-b/CLAUDE.md", "- Worktree y rama: `feat/T-2`\n")
        escribir(raiz, "tickets/T-3-c/CLAUDE.md", "- Worktree y rama: `feat/T-1`\n")
        with GitFalso(ramas, sucias=[carpeta]) as falso:
            revision = m().revisar(_config(raiz, repos=("db", "web")), time.monotonic() + 30)
        assert _lineas(revision) == ["T-1-a: en web, la rama feat/T-1 tiene cambios sin commitear.",
                                     "T-2-b: en db, la rama feat/T-2 tiene cambios sin commitear.",
                                     "T-3-c: en web, la rama feat/T-1 tiene cambios sin commitear."], revision
        assert falso.llamadas == [("status", _clave(carpeta))], falso.llamadas


def test_si_el_plazo_vence_dentro_del_pool_el_ticket_que_no_alcanzo_y_los_que_siguen_quedan_sin_revisar_como_antes():
    with Carpeta() as raiz:
        carpetas = _tickets_con_worktree(raiz, 3)
        ramas = {"web": [("feat/T-%d" % n, str(c), CABEZA) for n, c in carpetas.items()]}
        with GitFalso(ramas, sucias=carpetas.values()):
            assert m().confirmar(_config(raiz), "T-1-x", time.monotonic() + 30, "2026-11-25T10:00:00") == ("T-1-x", True)
        quedaron = ("odd-ws: quedaron 2 tickets sin revisar (no alcanzó el tiempo), así que no cuentan como limpios: "
                    "`entregas.py` los revisa todos.")
        with GitFalso(ramas, sucias=carpetas.values(), lentas=[carpetas[2]]):
            inicio = time.monotonic()
            texto = m().aviso_de_inicio(_config(raiz), inicio + 1.0)
            demoro = time.monotonic() - inicio
        assert texto == quedaron, "el confirmado de antes calla y el lento corta: %r" % texto
        assert demoro < 2.0, "el pool no espera más que el plazo: %.2f s" % demoro
        os.remove(raiz / ".claude" / "estado" / "entregas.json")
        with GitFalso(ramas, sucias=carpetas.values(), lentas=[carpetas[2]]):
            texto = m().aviso_de_inicio(_config(raiz), time.monotonic() + 1.0)
        assert texto == "\n".join([m().ENCABEZADO, "- T-1-x: en web, la rama feat/T-1 tiene cambios sin commitear.", m().CIERRE, quedaron]), \
            "el T-3 ya leído no cuenta como limpio: %r" % texto


def test_una_excepcion_en_un_hilo_deja_esa_lectura_como_ilegible_y_no_pierde_las_demas():
    with Carpeta() as raiz:
        carpetas = _tickets_con_worktree(raiz, 4)
        ramas = {"web": [("feat/T-%d" % n, str(c), ATRAS if n == 4 else CABEZA) for n, c in carpetas.items()]}
        rotas = [carpetas[2], RANGO % ("feat/T-4", "feat/T-4")]
        with GitFalso(ramas, sucias=[carpetas[1], carpetas[3]], rotas=rotas):
            revision = m().revisar(_config(raiz), time.monotonic() + 30)
            try:
                m().confirmar(_config(raiz), "T-2-x", time.monotonic() + 30, "2026-11-25T10:00:00")
                raise AssertionError("sin pool, la excepción de git sigue subiendo y no confirma nada")
            except OSError:
                pass
        assert _lineas(revision) == ["T-1-x: en web, la rama feat/T-1 tiene cambios sin commitear.",
                                     "T-2-x: en web, la rama feat/T-2 su carpeta no se pudo leer con git status.",
                                     "T-3-x: en web, la rama feat/T-3 tiene cambios sin commitear.",
                                     "T-4-x: en web, la rama feat/T-4 tiene commits sin empujar."] and revision[1:] == (0, 0), revision
        assert not (raiz / ".claude" / "estado" / "entregas.json").exists()


def test_las_confirmadas_se_leen_solo_con_la_forma_que_se_escribe():
    with Carpeta() as raiz:
        ruta = raiz / ".claude" / "estado" / "entregas.json"
        assert m().confirmadas(str(raiz)) == {}, "sin archivo"
        buena = {"version": 1, "confirmadas": {"T-1-a": {"huella": "a" * 64, "fecha": "2026-11-25T10:00:00"}, "T-2-b": {"huella": 5}}}
        escribir(raiz, ".claude/estado/entregas.json", json.dumps(buena))
        assert m().confirmadas(str(raiz)) == {"T-1-a": "a" * 64}, m().confirmadas(str(raiz))
        for rota in ("{roto", "[]", json.dumps({"version": 2, "confirmadas": buena["confirmadas"]}), json.dumps({"version": 1})):
            ruta.write_text(rota, encoding="utf-8")
            assert m().confirmadas(str(raiz)) == {}, rota


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
