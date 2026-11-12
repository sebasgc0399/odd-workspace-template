import contextlib
import importlib
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
NT = os.name == "nt"


def m():
    return importlib.import_module("odd_ws.rutas")


def entorno(**valores):
    return lambda nombre: valores.get(nombre)


def test_una_relativa_necesita_un_cwd_y_nunca_cae_en_el_del_proceso():
    assert m().ubicar("x/y.sql", None) is None
    assert m().ubicar("x/../y.sql", "C:/base") == m().caso("C:/base/y.sql")
    assert m().ubicar("x", "relativa") is None


def test_las_formas_relativas_a_la_unidad_no_se_resuelven():
    for ruta in ("C:", "C:x.sql", "C:/../x.sql"):
        assert m().ubicar(ruta, "D:/base") is None, ruta
    assert m().ubicar("C:/", None) == m().caso("C:/")


def test_git_bash_y_la_barra_sola_toman_la_unidad():
    assert m().ubicar("/c/repos/db", None) == m().caso("c:/repos/db")
    if NT:
        assert m().ubicar("/repos/db", "D:/x") == "d:/repos/db"
        assert m().ubicar("\\repos\\db", None) is None
        assert m().ubicar("//servidor/recurso", None) == "//servidor/recurso"


def test_expande_variables_del_entorno_y_pwd_del_cwd():
    variable = entorno(BASE="C:/repos", PWD="C:/del/entorno")
    assert m().expandir("$BASE/db", "C:/cwd", variable) == ("C:/repos/db", None)
    assert m().expandir("${BASE}/db", None, variable) == ("C:/repos/db", None)
    assert m().expandir("%BASE%/db", None, variable) == ("C:/repos/db", None)
    assert m().expandir("$PWD/x", "C:/cwd", variable) == ("C:/cwd/x", None)
    assert m().expandir("$env:PWD/x", "C:/cwd", variable) == ("C:/del/entorno/x", None)


def test_una_variable_desconocida_corta_en_la_ultima_carpeta_conocida():
    variable = entorno(BASE="C:/repos")
    assert m().expandir("$BASE/sub/$NO/x", None, variable) == (None, "C:/repos/sub/")
    assert m().expandir("$NO/x", None, variable) == (None, None)


def test_la_tilde_usa_home_o_userprofile():
    assert m().expandir("~/x", None, entorno(HOME="C:/Users/ana")) == ("C:/Users/ana/x", None)
    assert m().expandir("~/x", None, entorno(USERPROFILE="C:/Users/ana")) == ("C:/Users/ana/x", None)
    assert m().expandir("~beto/x", None, entorno(HOME="C:/Users/ana")) == (None, None)
    assert m().expandir("~/x", None, entorno()) == (None, None)


def test_resolver_expande_y_ubica():
    assert m().resolver(" $BASE/db/../web ", "C:/x", entorno(BASE="C:/repos")) == m().caso("C:/repos/web")
    assert m().resolver("$NO/db", "C:/x", entorno()) is None


def test_el_corte_por_comodin_deja_la_carpeta_anterior():
    assert m().antes_del_comodin("C:/repos/d*/x") == "C:/repos/"
    assert m().antes_del_comodin("C:/repos/{db,web}") == "C:/repos/"
    assert m().antes_del_comodin("*.sql") == ""
    assert m().antes_del_comodin("C:/repos/c++/x") is None
    assert m().antes_del_comodin("C:/repos/c++") == "C:/repos/"
    assert m().antes_del_comodin("C:/repos/db") is None


@contextlib.contextmanager
def plataforma(nombre):
    previa = m().PLATAFORMA
    m().PLATAFORMA = nombre
    try:
        yield
    finally:
        m().PLATAFORMA = previa


def test_en_macos_plegar_ignora_las_mayusculas_y_la_forma_unicode_como_apfs():
    nfd = "/Users/Ana/A\u0303n\u0303o"
    with plataforma("darwin"):
        assert m().plegar("/USERS/ana/ÃÑO") == m().plegar(nfd) == "/users/ana/ãño", m().plegar(nfd)


def test_en_windows_y_en_linux_plegar_deja_la_ruta_como_esta():
    for nombre in ("win32", "linux"):
        with plataforma(nombre):
            assert m().plegar("/Users/Ana/A\u0303n\u0303o") == "/Users/Ana/A\u0303n\u0303o", nombre


def test_en_posix_ubicar_deja_los_dos_puntos_para_que_los_resuelva_realpath():
    for nombre in ("linux", "darwin"):
        with plataforma(nombre):
            assert m().ubicar("l/../x", "/home/u/mi_repo") == m().caso("/home/u/mi_repo/l/../x"), nombre
            assert m().ubicar("./l//..", "/home/u/mi_repo") == m().caso("/home/u/mi_repo/./l//.."), nombre
            assert m().resolver(" $SUB/../x ", "/home/u/mi_repo", entorno(SUB="l")) == m().caso("/home/u/mi_repo/l/../x"), nombre
            if not NT:
                assert m().ubicar("/tmp/l/..", None) == "/tmp/l/..", nombre
                assert m().ubicar("/../x", None) == "/../x", nombre


def test_en_posix_una_ruta_sin_dos_puntos_se_normaliza_como_antes():
    for nombre in ("linux", "darwin"):
        with plataforma(nombre):
            assert m().ubicar("a//./b/", "/home/u/mi_repo") == m().caso("/home/u/mi_repo/a/b"), nombre
            assert m().ubicar("a..b/./x", "/home/u/mi_repo") == m().caso("/home/u/mi_repo/a..b/x"), nombre
            assert m().ubicar("x/../y.sql", "C:/Proyecto") == m().caso("C:/Proyecto/y.sql"), nombre
            assert m().ubicar("C:/../x.sql", "D:/base") is None, nombre


def test_la_lectura_logica_de_un_cd_quita_los_dos_puntos_como_texto_en_todas_las_plataformas():
    for nombre in ("linux", "darwin", "win32"):
        with plataforma(nombre):
            assert m().ubicar("l/..", "/home/u/ws", logica=True) == m().caso("/home/u/ws"), nombre
            assert m().ubicar("./l//../x", "/home/u/ws", logica=True) == m().caso("/home/u/ws/x"), nombre
            assert m().resolver(" $SUB/.. ", "/home/u/ws", entorno(SUB="lnk"), logica=True) == m().caso("/home/u/ws"), nombre
            assert m().ubicar("x/../y", "C:/Proyecto", logica=True) == m().caso("C:/Proyecto/y"), nombre
            assert m().ubicar("C:/../x", "D:/base", logica=True) is None, nombre
            assert m().ubicar("l/..", None, logica=True) is None, nombre


def test_en_windows_los_dos_puntos_se_colapsan_como_texto():
    with plataforma("win32"):
        assert m().ubicar("l/../x", "C:/Proyecto") == m().caso("C:/Proyecto/x")
        assert m().ubicar("l/..", "C:/Proyecto") == m().caso("C:/Proyecto")
        assert m().ubicar("l/../x", "/home/u/mi_repo") == m().caso("/home/u/mi_repo/x")


def test_la_plataforma_por_defecto_es_la_del_proceso():
    assert m().PLATAFORMA == sys.platform


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
    print(f"{len(pruebas) - fallas}/{len(pruebas)} pruebas en verde")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
