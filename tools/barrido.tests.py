import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "barrido.py"
LISTA_DE_PRUEBA = "# lista sintetica\n\nAcmeCorp\nPérez\nacme corp interna\n"


def entorno_sin_git(lista=None):
    env = {clave: valor for clave, valor in os.environ.items() if not clave.startswith("GIT_")}
    if lista is not None:
        env["ODD_WS_DENYLIST"] = str(lista)
    return env


def correr(args, cwd, lista):
    resultado = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, env=entorno_sin_git(lista), capture_output=True)
    salida = resultado.stdout.decode("utf-8", "replace") + resultado.stderr.decode("utf-8", "replace")
    return resultado.returncode, salida


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=prueba", "-c", "user.email=prueba@local", *args], cwd=cwd, env=entorno_sin_git(), capture_output=True, check=True)


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Escenario:
    def __init__(self, lista=LISTA_DE_PRUEBA):
        self.contenido_lista = lista

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="barrido-"))
        self.lista = self.dir / "denylist.txt"
        if self.contenido_lista is not None:
            self.lista.write_text(self.contenido_lista, encoding="utf-8")
        self.obra = self.dir / "obra"
        self.obra.mkdir()
        return self

    def __exit__(self, *_):
        shutil.rmtree(self.dir, onexc=_forzar_borrado)


def test_encuentra_termino_sin_importar_mayusculas_ni_tildes():
    with Escenario() as e:
        (e.obra / "nota.md").write_text("linea limpia\nhabla con PEREZ hoy\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "nota.md"], e.obra, e.lista)
        assert codigo == 1, salida
        assert "nota.md:2" in salida and "Pérez" in salida, salida


def test_contenido_limpio_sale_cero():
    with Escenario() as e:
        (e.obra / "nota.md").write_text("nada que ver aca\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "nota.md"], e.obra, e.lista)
        assert codigo == 0, salida


def test_termino_de_varias_palabras_en_un_subdirectorio():
    with Escenario() as e:
        profundo = e.obra / "a" / "b"
        profundo.mkdir(parents=True)
        (profundo / "x.txt").write_text("la Acme  Corp   Interna dijo algo\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "."], e.obra, e.lista)
        assert codigo == 1, salida
        assert "x.txt:1" in salida, salida


def test_encuentra_termino_en_el_nombre_del_archivo():
    with Escenario() as e:
        (e.obra / "notas-acmecorp.md").write_text("contenido limpio\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "notas-acmecorp.md"], e.obra, e.lista)
        assert codigo == 1, salida
        assert "(nombre)" in salida, salida


def test_lee_utf16_con_bom():
    with Escenario() as e:
        (e.obra / "sp.sql").write_bytes("SELECT 1 -- AcmeCorp\r\n".encode("utf-16"))
        codigo, salida = correr(["--paths", "sp.sql"], e.obra, e.lista)
        assert codigo == 1, salida


def test_lee_utf16_sin_bom():
    with Escenario() as e:
        (e.obra / "sp.sql").write_bytes("SELECT 1 -- AcmeCorp\r\n".encode("utf-16-le"))
        codigo, salida = correr(["--paths", "sp.sql"], e.obra, e.lista)
        assert codigo == 1, salida


def test_binario_no_rompe():
    with Escenario() as e:
        (e.obra / "basura.bin").write_bytes(bytes(range(256)) * 8)
        codigo, salida = correr(["--paths", "basura.bin"], e.obra, e.lista)
        assert codigo == 0, salida
        assert "Traceback" not in salida, salida


def test_sin_lista_falla_cerrado():
    with Escenario(lista=None) as e:
        (e.obra / "nota.md").write_text("limpio\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "nota.md"], e.obra, e.lista)
        assert codigo == 2, salida
        assert "lista negra" in salida, salida


def test_lista_solo_con_comentarios_falla_cerrado():
    with Escenario(lista="# nada\n\n   \n") as e:
        (e.obra / "nota.md").write_text("limpio\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "nota.md"], e.obra, e.lista)
        assert codigo == 2, salida
        assert "vacía" in salida, salida


def test_autoprueba_con_lista_valida():
    with Escenario() as e:
        codigo, salida = correr(["--autoprueba"], e.obra, e.lista)
        assert codigo == 0, salida
        assert "autoprueba ok" in salida, salida


def test_autoprueba_sin_lista_falla_cerrado():
    with Escenario(lista=None) as e:
        codigo, salida = correr(["--autoprueba"], e.obra, e.lista)
        assert codigo == 2, salida
        assert "lista negra" in salida, salida


def test_staged_lee_el_indice_y_no_el_arbol():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        archivo = e.obra / "a.txt"
        archivo.write_text("menciona AcmeCorp\n", encoding="utf-8")
        git(e.obra, "add", "a.txt")
        archivo.write_text("ya limpio en disco\n", encoding="utf-8")
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 1, salida
        assert "a.txt:1" in salida, salida


def test_staged_no_bloquea_lo_que_no_esta_stageado():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        archivo = e.obra / "a.txt"
        archivo.write_text("limpio\n", encoding="utf-8")
        git(e.obra, "add", "a.txt")
        archivo.write_text("ahora menciona AcmeCorp, sin stagear\n", encoding="utf-8")
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 0, salida


def test_staged_detecta_el_nombre_del_archivo():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        (e.obra / "notas-acmecorp.txt").write_text("limpio\n", encoding="utf-8")
        git(e.obra, "add", ".")
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 1, salida
        assert "(nombre)" in salida, salida


def test_staged_ignora_un_borrado():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        (e.obra / "viejo.txt").write_text("menciona AcmeCorp\n", encoding="utf-8")
        git(e.obra, "add", ".")
        git(e.obra, "commit", "-q", "--no-verify", "-m", "base")
        git(e.obra, "rm", "-q", "viejo.txt")
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 0, salida


def test_staged_sin_nada_stageado_sale_cero():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 0, salida


def test_staged_fuera_de_un_repo_falla_cerrado():
    with Escenario() as e:
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 2, salida
        assert "repositorio git" in salida, salida


def test_sin_argumentos_falla_cerrado():
    with Escenario() as e:
        codigo, salida = correr([], e.obra, e.lista)
        assert codigo == 2, salida
        assert "uso:" in salida, salida


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
