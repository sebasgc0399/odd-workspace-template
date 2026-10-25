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


HOOKS = AQUI.parent / ".githooks"
CEROS = "0" * 40


def correr(args, cwd, lista, entrada=None):
    resultado = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, env=entorno_sin_git(lista), capture_output=True, input=entrada)
    salida = resultado.stdout.decode("utf-8", "replace") + resultado.stderr.decode("utf-8", "replace")
    return resultado.returncode, salida


def git(cwd, *args, entrada=None):
    return subprocess.run(["git", "-c", "user.name=prueba", "-c", "user.email=prueba@local", *args], cwd=cwd, env=entorno_sin_git(), capture_output=True, check=True, input=entrada)


def git_salida(cwd, *args):
    return git(cwd, *args).stdout.decode("utf-8").strip()


def commit_sin_hooks(cwd, archivo, contenido, mensaje):
    (cwd / archivo).write_text(contenido, encoding="utf-8")
    git(cwd, "add", archivo)
    git(cwd, "commit", "-q", "--no-verify", "-m", mensaje)
    return git_salida(cwd, "rev-parse", "HEAD")


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


def test_lee_cp1252_con_tildes():
    with Escenario() as e:
        (e.obra / "acta.txt").write_bytes("Reunión con Pérez".encode("cp1252"))
        codigo, salida = correr(["--paths", "acta.txt"], e.obra, e.lista)
        assert codigo == 1, salida


def test_termino_de_varias_palabras_partido_por_salto_de_linea():
    with Escenario() as e:
        (e.obra / "nota.md").write_text("primera linea\nlo dijo la Acme Corp\nInterna en la reunion\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "nota.md"], e.obra, e.lista)
        assert codigo == 1, salida
        assert "nota.md:2" in salida, salida


def test_una_palabra_no_se_arma_con_el_final_de_la_linea_anterior():
    with Escenario() as e:
        (e.obra / "nota.md").write_text("termina en Acme\nCorp no es una palabra\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "nota.md"], e.obra, e.lista)
        assert codigo == 0, salida


def test_ruta_windows_escapada_en_json_y_con_barras_normales():
    with Escenario(lista="c:\\acme\n") as e:
        (e.obra / "a.json").write_text('{"c": "C:\\\\ACME\\\\x"}\n', encoding="utf-8")
        (e.obra / "b.md").write_text("ver C:/Acme/x\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "a.json", "b.md"], e.obra, e.lista)
        assert codigo == 1, salida
        assert "a.json:1" in salida and "b.md:1" in salida, salida


def test_ignora_caracteres_de_formato_dentro_del_termino():
    with Escenario() as e:
        (e.obra / "a.txt").write_text("hola Acme\u200bCorp y Acme\u00adCorp y Acme\ufeffCorp\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "a.txt"], e.obra, e.lista)
        assert codigo == 1, salida
        assert salida.count("a.txt:1") == 1, salida


def test_lista_en_cp1252_se_lee():
    with Escenario(lista=None) as e:
        e.lista.write_bytes("Pérez\n".encode("cp1252"))
        (e.obra / "a.txt").write_text("habló Pérez\n", encoding="utf-8")
        codigo, salida = correr(["--paths", "a.txt"], e.obra, e.lista)
        assert codigo == 1, salida


def test_lista_con_caracteres_ilegibles_falla_cerrado():
    with Escenario(lista=None) as e:
        e.lista.write_bytes(b"Acme\x81Corp\n")
        codigo, salida = correr(["--autoprueba"], e.obra, e.lista)
        assert codigo == 2, salida
        assert "ilegibles" in salida, salida


def test_autoprueba_prueba_todos_los_terminos_y_dice_que_lista_uso():
    with Escenario() as e:
        codigo, salida = correr(["--autoprueba"], e.obra, e.lista)
        assert codigo == 0, salida
        assert "3 términos" in salida and str(e.lista) in salida, salida


def test_mensaje_de_commit_con_termino_bloquea():
    with Escenario() as e:
        (e.obra / "MSG").write_text("fix: portado desde AcmeCorp\n", encoding="utf-8")
        codigo, salida = correr(["--mensaje", "MSG"], e.obra, e.lista)
        assert codigo == 1, salida
        assert "mensaje" in salida, salida


def test_mensaje_de_commit_ignora_los_comentarios_de_git():
    with Escenario() as e:
        (e.obra / "MSG").write_text("fix: limpio\n# notas-acmecorp.txt modificado\n", encoding="utf-8")
        codigo, salida = correr(["--mensaje", "MSG"], e.obra, e.lista)
        assert codigo == 0, salida


def test_pre_push_bloquea_un_commit_que_salto_el_pre_commit():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        sha = commit_sin_hooks(e.obra, "leak.txt", "menciona AcmeCorp\n", "chore: limpio")
        codigo, salida = correr(["--pre-push"], e.obra, e.lista, entrada=f"refs/heads/main {sha} refs/heads/main {CEROS}\n".encode())
        assert codigo == 1, salida
        assert "leak.txt" in salida, salida


def test_pre_push_bloquea_un_termino_en_el_mensaje():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        sha = commit_sin_hooks(e.obra, "a.txt", "limpio\n", "fix: portado de Pérez")
        codigo, salida = correr(["--pre-push"], e.obra, e.lista, entrada=f"refs/heads/main {sha} refs/heads/main {CEROS}\n".encode())
        assert codigo == 1, salida
        assert "mensaje" in salida, salida


def test_pre_push_solo_barre_lo_que_el_remoto_no_tiene():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        viejo = commit_sin_hooks(e.obra, "viejo.txt", "menciona AcmeCorp\n", "base")
        nuevo = commit_sin_hooks(e.obra, "nuevo.txt", "limpio\n", "feat: limpio")
        codigo, salida = correr(["--pre-push"], e.obra, e.lista, entrada=f"refs/heads/main {nuevo} refs/heads/main {viejo}\n".encode())
        assert codigo == 0, salida


def test_pre_push_ignora_el_borrado_de_una_rama():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        sha = commit_sin_hooks(e.obra, "leak.txt", "menciona AcmeCorp\n", "base")
        codigo, salida = correr(["--pre-push"], e.obra, e.lista, entrada=f"(delete) {CEROS} refs/heads/vieja {sha}\n".encode())
        assert codigo == 0, salida


def test_git_push_real_no_deja_pasar_el_commit():
    with Escenario() as e:
        remoto = e.dir / "remoto.git"
        git(e.dir, "init", "-q", "--bare", str(remoto))
        git(e.obra, "init", "-q")
        (e.obra / "tools").mkdir()
        shutil.copy(SCRIPT, e.obra / "tools" / "barrido.py")
        shutil.copytree(HOOKS, e.obra / ".githooks")
        git(e.obra, "config", "core.hooksPath", ".githooks")
        commit_sin_hooks(e.obra, "leak.txt", "menciona AcmeCorp\n", "chore: rebase sin pre-commit")
        empuje = subprocess.run(["git", "push", "-q", str(remoto), "HEAD:refs/heads/x"], cwd=e.obra, env=entorno_sin_git(e.lista), capture_output=True)
        assert empuje.returncode != 0, empuje.stderr.decode("utf-8", "replace")
        en_remoto = subprocess.run(["git", "rev-parse", "--verify", "-q", "refs/heads/x"], cwd=remoto, env=entorno_sin_git(), capture_output=True)
        assert en_remoto.returncode != 0, "el commit llegó al remoto"


def test_staged_barre_un_cambio_de_tipo_a_symlink():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        commit_sin_hooks(e.obra, "lnk", "archivo comun\n", "base")
        blob = git(e.obra, "hash-object", "-w", "--stdin", entrada=b"C:/AcmeCorp/destino").stdout.decode().strip()
        git(e.obra, "update-index", "--cacheinfo", f"120000,{blob},lnk")
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 1, salida


def test_staged_un_submodulo_no_bloquea():
    with Escenario() as e:
        git(e.obra, "init", "-q")
        commit_sin_hooks(e.obra, "a.txt", "limpio\n", "base")
        ajeno = "1234567890abcdef1234567890abcdef12345678"
        git(e.obra, "update-index", "--add", "--cacheinfo", f"160000,{ajeno},vendored")
        codigo, salida = correr(["--staged"], e.obra, e.lista)
        assert codigo == 0, salida


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
