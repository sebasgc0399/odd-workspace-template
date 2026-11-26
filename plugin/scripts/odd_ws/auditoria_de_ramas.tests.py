import sys

sys.dont_write_bytecode = True

import importlib
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
SOBRANTES = []


def m():
    return importlib.import_module("odd_ws.auditoria_de_ramas")


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
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="auditoria-lib-")))
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


def _cabeza(*lineas, squash=False):
    return m().Cabeza(tuple(lineas), squash)


def _datos(sin_commitear=False, origen=True, sin_empujar=0, principal="origin/main", cabezas=None):
    return m().Datos(sin_commitear, origen, sin_empujar, principal, (_cabeza(),) if cabezas is None else cabezas)


def llego():
    return m().Estado(True, ())


def faltas(*pares):
    return m().Estado(False, tuple(m().Falta(tipo, commits) for tipo, commits in pares))


def clasificar(datos):
    with SinGit() as guardia:
        estado = m().clasificar_rama(datos)
    assert not guardia.llamadas
    return estado


def test_una_rama_con_todo_en_la_principal_y_sin_cambios_llego():
    assert clasificar(_datos()) == llego(), "cherry vacío: la principal ya contiene la rama, como después de un merge"
    assert clasificar(_datos(cabezas=(_cabeza("- a", "- b"),))) == llego(), "cada commit tiene su parche en la principal"
    assert clasificar(_datos(origen=False)) == llego(), "sin origin/<rama>, pero con todo en la principal (un merge local ya empujado)"
    assert clasificar(_datos(sin_empujar=3)) == llego(), "commits que no están en origin/<rama> pero sí en la principal"


def test_los_cambios_sin_commitear_son_pendientes_aunque_todo_haya_llegado():
    m_ = m()
    assert clasificar(_datos(sin_commitear=True)) == faltas((m_.SIN_COMMITEAR, None))
    assert clasificar(_datos(sin_commitear=None)) == faltas((m_.ILEGIBLE, None)), "un status que falla no cuenta como limpio"


def test_los_commits_sin_empujar_que_no_estan_en_la_principal_son_pendientes():
    m_ = m()
    assert clasificar(_datos(sin_empujar=2, cabezas=(_cabeza("+ a", "+ b"),))) == faltas((m_.SIN_EMPUJAR, 2), (m_.NO_LLEGO, 2))
    assert clasificar(_datos(sin_empujar=None, cabezas=(_cabeza("+ a"),))) == faltas((m_.SIN_EMPUJAR, None), (m_.NO_LLEGO, 1)), \
        "sin poder contarlos, igual son pendientes"


def test_una_rama_que_nunca_se_empujo_con_trabajo_fuera_de_la_principal_es_pendiente():
    m_ = m()
    assert clasificar(_datos(origen=False, cabezas=(_cabeza("+ a"),))) == faltas((m_.NUNCA, None), (m_.NO_LLEGO, 1))


def test_el_trabajo_empujado_que_no_esta_en_la_principal_no_llego():
    assert clasificar(_datos(cabezas=(_cabeza("+ a", "+ b"),))) == faltas((m().NO_LLEGO, 2))


def test_un_squash_no_se_confunde_con_trabajo_perdido():
    assert clasificar(_datos(cabezas=(_cabeza("- a"),))) == llego(), "el squash de un commit: git cherry lo marca con -"
    assert clasificar(_datos(cabezas=(_cabeza("+ a", "+ b", squash=True),))) == llego(), \
        "el squash de varios commits: el parche de toda la rama está en la principal"


def test_el_caso_sembrado_los_commits_nuevos_despues_de_que_lo_anterior_llego_no_llegaron_aunque_esten_empujados():
    # «un push a una rama cuyo PR ya se mergeó sale bien, no corre CI y el commit nunca llega a la rama principal»
    m_ = m()
    assert clasificar(_datos(cabezas=(_cabeza("+ c"),))) == faltas((m_.NO_LLEGO, 1)), "después de un merge"
    assert clasificar(_datos(cabezas=(_cabeza("- a", "+ c"),))) == faltas((m_.NO_LLEGO, 1)), "después del squash de un commit"
    assert clasificar(_datos(cabezas=(_cabeza("+ a", "+ b", "+ c"),))) == faltas((m_.NO_LLEGO, 3)), "después del squash de varios"
    assert clasificar(_datos(cabezas=(_cabeza(), _cabeza("+ c")))) == faltas((m_.NO_LLEGO, 1)), \
        "empujado desde otra máquina: la rama local está atrás y origin/<rama> tiene el commit"


def test_las_cabezas_local_y_de_origin_cuentan_cada_commit_una_vez():
    m_ = m()
    assert clasificar(_datos(cabezas=(_cabeza("+ a", "+ b"), _cabeza("+ a", "+ c")))) == faltas((m_.NO_LLEGO, 3))
    assert clasificar(_datos(cabezas=(_cabeza("+ a", squash=True), _cabeza("+ a", "+ c")))) == faltas((m_.NO_LLEGO, 2)), \
        "una cabeza que llegó por squash no tapa a la otra"


def test_sin_principal_o_sin_cherry_no_se_puede_decir_que_llego():
    m_ = m()
    assert clasificar(_datos(principal=None, cabezas=())) == faltas((m_.SIN_PRINCIPAL, None))
    assert clasificar(_datos(principal=None, origen=False, cabezas=())) == faltas((m_.NUNCA, None), (m_.SIN_PRINCIPAL, None))
    assert clasificar(_datos(sin_commitear=True, sin_empujar=1, principal=None, cabezas=())) == faltas(
        (m_.SIN_COMMITEAR, None), (m_.SIN_EMPUJAR, 1), (m_.SIN_PRINCIPAL, None))
    assert clasificar(_datos(cabezas=(m_.Cabeza(None, False),))) == faltas((m_.SIN_COMPARAR, None)), "un cherry que falla"


def test_la_principal_es_la_de_origin_head_y_si_no_hay_main_o_master():
    p = m().principal_de
    assert p({"develop": "1", "main": "2"}, "refs/remotes/origin/develop") == "origin/develop"
    assert p({"main": "2", "master": "3"}, None) == "origin/main"
    assert p({"master": "3"}, None) == "origin/master"
    assert p({"main": "2"}, "refs/remotes/origin/borrada") == "origin/main", "un origin/HEAD que apunta a una rama que no está"
    assert p({"feat/x": "1"}, None) is None


def test_el_texto_de_cada_estado():
    m_, t = m(), m().texto
    assert t(llego(), "origin/main") == "llegó a origin/main"
    assert t(faltas((m_.NUNCA, None), (m_.NO_LLEGO, 1)), "origin/main") == "nunca se empujó y tiene 1 commit que no llegó a origin/main"
    assert t(faltas((m_.SIN_COMMITEAR, None), (m_.SIN_EMPUJAR, 2), (m_.NO_LLEGO, 3)), "origin/main") == (
        "tiene cambios sin commitear, 2 commits sin empujar y 3 commits que no llegaron a origin/main")
    assert t(faltas((m_.SIN_EMPUJAR, None), (m_.NO_LLEGO, 1)), "origin/trunk") == (
        "tiene commits sin empujar y 1 commit que no llegó a origin/trunk")
    assert t(faltas((m_.SIN_EMPUJAR, 1), (m_.SIN_PRINCIPAL, None)), None) == (
        "tiene 1 commit sin empujar y no tiene con qué compararse: el repo no tiene origin/HEAD, origin/main ni origin/master")
    assert t(faltas((m_.ILEGIBLE, None), (m_.SIN_COMPARAR, None)), "origin/main") == (
        "su carpeta no se pudo leer con git status y no se pudo comparar con origin/main")


def test_un_ticket_sin_revisar_o_un_repo_en_rojo_no_dejan_decir_que_todo_llego():
    m_ = m()
    sano = m_.RepoAuditado("web", False, None)
    llegada = m_.RamaAuditada("T-1-a", "web", "feat/T-1", None, "origin/main", llego(), None)
    assert m_.todo_llego(m_.Auditoria([sano], [llegada], [], [])), "control: todo llegó"
    assert m_.resumen(m_.Auditoria([sano], [llegada], [], [])) == "Resumen: todo llegó (1 rama de 1 ticket)."
    sin_revisar = m_.Auditoria([sano], [llegada], [], ["T-2-b", "T-3-c"])
    assert not m_.todo_llego(sin_revisar)
    assert m_.resumen(sin_revisar) == "Resumen: no todo llegó: 2 tickets sin revisar, de 1 rama en 1 ticket.", m_.resumen(sin_revisar)
    rojo = m_.Auditoria([sano, m_.RepoAuditado("db", True, "x")], [], [], [])
    assert not m_.todo_llego(rojo) and m_.resumen(rojo) == "Resumen: no todo llegó: 1 repo en rojo.", m_.resumen(rojo)
    assert m_.resumen(m_.Auditoria([sano], [], ["T-4-d"], [])) == m_.NADA


def test_los_archivados_son_los_tickets_mas_hondos_de_tickets_sin_la_plantilla_ni_lo_que_cuelga_de_un_ticket():
    with Carpeta() as raiz:
        for rel in ("tickets/T-1-a/CLAUDE.md", "tickets/T-1-a/sub/CLAUDE.md", "tickets/_plantilla/CLAUDE.md", "tickets/_plantilla/x/CLAUDE.md",
                    "tickets/archivo/T-3-c/CLAUDE.md", "tickets/archivo/T-3-c/notas/CLAUDE.md", "tickets/archivo/2025/T-2-b/CLAUDE.md",
                    "tickets/archivo/2025/notas.md", "otra/T-5-e/CLAUDE.md"):
            escribir(raiz, rel, "x\n")
        assert m().archivados(str(raiz)) == ["archivo/2025/T-2-b", "archivo/T-3-c"], m().archivados(str(raiz))
    with Carpeta() as raiz:
        assert m().archivados(str(raiz)) == [], "sin tickets/"


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
