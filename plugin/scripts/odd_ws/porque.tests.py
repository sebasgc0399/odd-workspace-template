import sys

sys.dont_write_bytecode = True

import contextlib
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
    return importlib.import_module("odd_ws.porque")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def carpeta():
    ruta = Path(os.path.realpath(tempfile.mkdtemp(prefix="porque-test-")))
    try:
        yield ruta
    finally:
        shutil.rmtree(ruta, onexc=_quitar)
        if ruta.exists():
            SOBRANTES.append(str(ruta))


@contextlib.contextmanager
def sin_subprocess():
    llamadas = []
    original = subprocess.run

    def prohibido(*args, **kwargs):
        llamadas.append(args)
        raise AssertionError("se lanzó un subprocess")

    subprocess.run = prohibido
    try:
        yield llamadas
    finally:
        subprocess.run = original


def test_el_fragmento_se_ubica_por_contenido_en_todas_sus_apariciones():
    texto = "uno\ndos\ntres\ndos\ncuatro\n"
    assert m().rangos_del_texto(texto, "dos") == [(2, 2), (4, 4)]
    assert m().rangos_del_texto(texto, "dos\ntres\n") == [(2, 3)], "el salto final no suma la línea siguiente"
    assert m().rangos_del_texto(texto.replace("\n", "\r\n"), "uno\r\ndos") == [(1, 2)], "CRLF en los dos lados"
    assert m().rangos_del_texto(texto.replace("\n", "\r\n"), "tres\ndos") == [(3, 4)], "CRLF en el archivo y LF en el fragmento"
    assert m().rangos_del_texto(texto, None) == [(1, 5)], "None es el archivo entero"
    assert m().rangos_del_texto("", None) == [] and m().rangos_del_texto(texto, " \n ") == [] and m().rangos_del_texto(texto, "cinco") == []


def test_las_lineas_de_una_desviacion_se_ubican_sin_mirar_la_sangria_ni_los_bordes_en_blanco():
    texto = "a\n    IF @x = 1\n        RETURN\nb\nIF @x = 1\nRETURN\n"
    assert m().rangos_de_las_lineas(texto, ["", "IF @x = 1", "  RETURN", ""]) == [(2, 3), (5, 6)]
    assert m().rangos_de_las_lineas(texto, ["IF @x = 2"]) == [] and m().rangos_de_las_lineas(texto, ["", " "]) == []


def test_los_rangos_se_tocan_se_unen_y_tienen_tope():
    assert m().se_tocan((5, 6), (6, 9)) and m().se_tocan((5, 6), (1, 5)) and not m().se_tocan((5, 6), (7, 8))
    assert m().unir([(8, 9), (1, 3), (4, 5), (2, 2)]) == [(1, 5), (8, 9)]
    assert m().con_tope([(1, 300), (400, 600), (700, 701)]) == [(1, 300), (400, 499)]
    assert m().TOPE_DE_LINEAS == 400


def test_la_primera_linea_del_cuerpo_salta_el_asunto_y_los_trailers():
    porque = m().primera_linea_del_cuerpo
    assert porque("asunto\n") is None and porque("") is None and porque(None) is None
    assert porque("asunto\n\nel porqué\notra\n\nCo-Authored-By: X <x@x>\nSigned-off-by: Y <y@y>\n") == "el porqué otra"
    assert porque("asunto\n\nCo-Authored-By: X <x@x>\n") is None, "un cuerpo de solo trailers no es un porqué"
    assert porque("asunto\nsigue el asunto\n\n  el   porqué  \n") == "el porqué"
    assert porque("asunto\n\nNota: va así por la DIAN\n\nmás texto\n") == "Nota: va así por la DIAN", "un trailer solo cuenta al final"
    assert porque("asunto\r\n\r\nen CRLF\r\n") == "en CRLF"
    largo = porque("asunto\n\n" + "x" * 300 + "\n")
    assert len(largo) == m().LARGO_DEL_PORQUE and largo.endswith("…"), largo


def test_el_porque_es_el_primer_parrafo_en_una_linea_o_su_primera_vineta():
    porque = m().primera_linea_del_cuerpo
    assert porque("asunto\n\nla línea envuelta sigue\nen la de abajo\n\notro párrafo\n") == "la línea envuelta sigue en la de abajo"
    assert porque("asunto\n\n- la primera viñeta sigue\n  en la de abajo\n- la segunda no\n") == "la primera viñeta sigue en la de abajo"
    assert porque("asunto\n\n* con asterisco\n* otra\n") == "con asterisco"
    palabras = " ".join("pa%03d" % n for n in range(50))
    assert porque("asunto\n\n" + palabras + "\n") == " ".join("pa%03d" % n for n in range(33)) + "…", "corta en un borde de palabra"


def test_solo_los_trailers_conocidos_del_ultimo_parrafo_salen_del_porque():
    porque = m().primera_linea_del_cuerpo
    assert porque("asunto\n\nMotivo: la DIAN rechaza X\n") == "Motivo: la DIAN rechaza X", "una clave desconocida es cuerpo"
    assert porque("asunto\n\nMotivo: la DIAN\nco-authored-by: Y <y@y>\nCHANGE-ID: I12\n") == "Motivo: la DIAN", "sin mayúsculas"
    for clave in ("Co-Authored-By", "Signed-off-by", "Reviewed-by", "Acked-by", "Tested-by", "Reported-by", "Suggested-by", "Helped-by", "Cc",
                  "Change-Id"):
        assert porque("asunto\n\n%s: X <x@x>\n" % clave) is None, clave
    assert porque("asunto\n\nSigned-off-by: X <x@x>\n\nel porqué\n") == "Signed-off-by: X <x@x>", "solo en el último párrafo"
    assert porque("asunto\n\nel porqué\n\nCo-Authored-By: X\n  <x@x>\n") == "el porqué", "con su línea de continuación"


def test_la_fecha_es_la_del_autor_en_su_zona():
    momento = 1775104200
    assert m().fecha(momento, "-0500") == "2026-04-01" and m().fecha(momento, "+0000") == "2026-04-02"
    assert m().fecha(momento, "raro") == "2026-04-02"


def test_el_blame_porcelain_da_cada_commit_una_vez_con_su_fecha_y_sin_el_commit_cero():
    a, b, cero = "a" * 40, "b" * 40, "0" * 40
    salida = ("%s 1 1 2\nauthor X\nauthor-time 100\nauthor-tz +0100\nsummary s\nfilename f\n\tuno\n"
              "%s 2 2\n\tdos\n"
              "%s 3 3 1\nauthor-time 200\nauthor-tz -0300\nboundary\nfilename f\n\ttres\n"
              "%s 4 4 1\nauthor-time 300\nfilename f\n\tcuatro\n" % (a, a, b, cero))
    commits = m()._commits_del_blame(salida)
    assert [h for h, _ in commits] == [a, b], commits
    assert commits[0][1]["author-time"] == "100" and commits[1][1]["author-tz"] == "-0300", commits


def test_la_ruta_relativa_al_arbol_y_afuera_none():
    with carpeta() as base:
        (base / "repo" / "src").mkdir(parents=True)
        assert m().relativa(base / "repo" / "src" / "a.sql", base / "repo") == "src/a.sql"
        assert m().relativa(base / "otro" / "a.sql", base / "repo") is None
        assert m().relativa(base / "repo", base / "repo") is None


def test_la_pausa_sin_desviaciones_no_corre_git():
    with carpeta() as base:
        (base / "workspace.config.json").write_text('{"schema_version": 1, "repos": {"db": {}}, "layers": {}}', encoding="utf-8")
        archivo = base / "db" / "a.sql"
        archivo.parent.mkdir()
        archivo.write_text("uno\n", encoding="utf-8")
        with sin_subprocess() as llamadas:
            assert m().pausa(base, "db", base / "db", archivo, ["uno"], m().hasta(5)) is None
        assert llamadas == []


def test_fuera_de_un_repo_git_el_contexto_dice_que_no_se_pudo_chequear():
    with carpeta() as base:
        archivo = base / "a.sql"
        archivo.write_text("uno\n", encoding="utf-8")
        previo = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = str(base.parent)
        try:
            texto = m().contexto(base, archivo, ["uno"], m().hasta(5))
        finally:
            if previo is None:
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            else:
                os.environ["GIT_CEILING_DIRECTORIES"] = previo
        assert texto is not None and m().NO_SE_PUDO in texto and "a.sql" in texto, texto
        assert m().contexto(base, base / "no-existe.sql", ["uno"], m().hasta(5)) is None, "un archivo que no existe calla"
        vencido = m().contexto(base, archivo, ["uno"], m().hasta(-1))
        assert vencido is not None and m().NO_SE_PUDO in vencido and "a tiempo" in vencido, vencido


@contextlib.contextmanager
def git_aislado(base):
    claves = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")
    previo = {clave: os.environ.get(clave) for clave in claves}
    os.environ.update(GIT_CONFIG_GLOBAL=str(base / "global"), GIT_CONFIG_SYSTEM=str(base / "sistema"), GIT_CONFIG_NOSYSTEM="1")
    try:
        yield
    finally:
        for clave, valor in previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor


def _git_de_prueba(repo, *args, entrada=None):
    entorno = {clave: valor for clave, valor in os.environ.items() if not clave.startswith("GIT_") or clave.startswith("GIT_CONFIG_")}
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false",
                        *args], cwd=str(repo), input=entrada, capture_output=True, env=entorno)
    assert r.returncode == 0, r.stderr


def test_una_ruta_que_ya_no_existe_trae_el_porque_de_head_y_una_carpeta_calla():
    with carpeta() as base, git_aislado(base):
        repo = base / "repo"
        (repo / "src").mkdir(parents=True)
        _git_de_prueba(repo, "init", "-q")
        (repo / "src" / "a.sql").write_text("uno\ndos\n", encoding="utf-8")
        _git_de_prueba(repo, "add", "-A")
        _git_de_prueba(repo, "commit", "-q", "-F", "-", entrada="asunto\n\nEl porqué de uno.\n".encode("utf-8"))
        (repo / "src" / "a.sql").unlink()
        texto = m().contexto(repo, repo / "src" / "a.sql", ["uno"], m().hasta(5))
        assert texto is not None and texto.startswith(m().ENCABEZADO % "src/a.sql" + "\n"), texto
        assert texto.endswith(": El porqué de uno.") and texto.count("\n") == 1, texto
        assert m().contexto(repo, repo / "src" / "nunca.sql", ["uno"], m().hasta(5)) is None, "lo que no existe ni está en HEAD calla"
        (repo / "src" / "carpeta.sql").mkdir()
        with sin_subprocess() as llamadas:
            assert m().contexto(repo, repo / "src" / "carpeta.sql", ["uno"], m().hasta(5)) is None, "una carpeta calla"
            assert m().contexto(repo, repo / "src" / "a.sql", [None], m().hasta(5)) is None, "un archivo entero que ya no existe calla"
        assert llamadas == []


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
    if SOBRANTES:
        print("quedaron carpetas temporales: %s" % ", ".join(SOBRANTES))
        fallas += 1
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
