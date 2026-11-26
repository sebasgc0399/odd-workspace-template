import sys

sys.dont_write_bytecode = True

import importlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
SOBRANTES = []


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
