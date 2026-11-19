import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CLI = AQUI / "marcadores.py"
APERTURA = "<" * 7
SEPARADOR = "=" * 7
CIERRE = ">" * 7
CONFLICTO = f"antes\n{APERTURA} HEAD\nlo nuestro\n{SEPARADOR}\nlo de ellos\n{CIERRE} otra\ndespues\n"
SOBRANTES = []


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Repo:
    def __init__(self, crear=True):
        self.crear = crear

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="marcadores-test-"))
        for nombre in ("gitconfig-global", "gitconfig-sistema"):
            (self.base / nombre).write_bytes(b"")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=str(self.base / "gitconfig-global"),
                        GIT_CONFIG_SYSTEM=str(self.base / "gitconfig-sistema"), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CEILING_DIRECTORIES=str(self.base), GIT_AUTHOR_NAME="prueba",
                        GIT_AUTHOR_EMAIL="prueba@example.com", GIT_COMMITTER_NAME="prueba",
                        GIT_COMMITTER_EMAIL="prueba@example.com")
        self.raiz = self.base / "repo"
        self.raiz.mkdir()
        if self.crear:
            for args in (("init", "-q", "-b", "main"), ("config", "core.autocrlf", "false")):
                self.git(*args)
        return self

    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.raiz, capture_output=True, env=self.env)
        assert r.returncode == 0, (args, r.stderr.decode("utf-8", "replace"))
        return r.stdout.decode("utf-8", "replace")

    def escribir(self, ruta, contenido):
        destino = self.raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido if isinstance(contenido, bytes) else contenido.encode("utf-8"))

    def stagear(self, ruta, contenido):
        self.escribir(ruta, contenido)
        self.git("add", "--", ruta)

    def stagear_solo_en_el_indice(self, ruta, contenido):
        blob = self.base / "blob"
        blob.write_bytes(contenido.encode("utf-8"))
        self.git("config", "core.protectNTFS", "false")
        self.git("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (self.git("hash-object", "-w", str(blob)).strip(), ruta))

    def commitear(self, mensaje="prueba"):
        self.git("commit", "-q", "--allow-empty", "-m", mensaje)

    def revisar(self, env=None):
        r = subprocess.run([sys.executable, str(CLI)], cwd=self.raiz, capture_output=True, env=env or self.env, timeout=120)
        return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def test_los_dos_marcadores_en_un_archivo_frenan_y_nombran_archivo_y_linea():
    with Repo() as repo:
        repo.stagear("docs/guia.md", CONFLICTO)
        repo.stagear("limpio.md", "nada raro\n")
        codigo, salida, errores = repo.revisar()
        assert codigo == 1, (codigo, salida, errores)
        assert f"docs/guia.md:2: {APERTURA} HEAD" in errores, errores
        assert f"docs/guia.md:6: {CIERRE} otra" in errores, errores
        assert "limpio.md" not in errores and salida == "", (salida, errores)
        assert "git add" in errores and "conflict-marker-size" in errores and ".gitattributes" in errores, errores


def test_un_separador_suelto_es_un_subrayado_de_markdown_y_pasa():
    with Repo() as repo:
        repo.stagear("titulo.md", f"Titulo\n{SEPARADOR}\n\ntexto\n")
        assert repo.revisar() == (0, "", "")


def test_un_solo_tipo_de_marcador_por_archivo_pasa_aunque_el_otro_este_en_otro_archivo():
    with Repo() as repo:
        repo.stagear("apertura.md", f"{APERTURA} HEAD\nlo nuestro\n{SEPARADOR}\nlo de ellos\n")
        repo.stagear("cierre.md", f"lo de ellos\n{CIERRE} otra\n")
        assert repo.revisar() == (0, "", "")


def test_los_errores_de_espacios_nunca_frenan():
    with Repo() as repo:
        repo.stagear(".gitattributes", "estricto.txt whitespace=trailing-space,space-before-tab,tab-in-indent\n")
        repo.stagear("espacios.txt", "fin con espacios   \n \tespacio antes del tab\ncon CR\r\n\n\n")
        repo.stagear("estricto.txt", "\tsangria con tab\nfin con espacios   \n\n")
        assert repo.revisar() == (0, "", "")


def test_conflict_marker_size_saca_del_chequeo_las_lineas_de_siete_y_vigila_las_de_su_tamano():
    with Repo() as repo:
        repo.stagear(".gitattributes", "ejemplos/*.md conflict-marker-size=32\n")
        repo.stagear("ejemplos/conflicto.md", CONFLICTO)
        assert repo.revisar() == (0, "", "")
        largo = CONFLICTO.replace(APERTURA, "<" * 32).replace(CIERRE, ">" * 32).replace(SEPARADOR, "=" * 32)
        repo.stagear("ejemplos/largo.md", largo)
        codigo, _, errores = repo.revisar()
        assert codigo == 1 and "ejemplos/largo.md:2:" in errores and "ejemplos/conflicto.md" not in errores, errores


def test_los_marcadores_que_ya_estaban_en_head_y_no_se_tocan_pasan():
    with Repo() as repo:
        repo.stagear("viejo.md", CONFLICTO)
        repo.commitear()
        repo.stagear("viejo.md", CONFLICTO + "una linea nueva\n")
        repo.stagear("otro.md", "otro archivo\n")
        assert repo.revisar() == (0, "", "")


def test_solo_cuenta_lo_stageado_y_no_el_arbol_de_trabajo():
    with Repo() as repo:
        repo.stagear("a.md", "limpio\n")
        repo.escribir("a.md", CONFLICTO)
        assert repo.revisar() == (0, "", "")


def test_si_git_falla_por_no_ser_un_repo_deja_pasar_con_un_aviso():
    with Repo(crear=False) as repo:
        codigo, salida, errores = repo.revisar()
        assert (codigo, salida) == (0, ""), (codigo, salida, errores)
        assert "no se pudo revisar" in errores and "sin este chequeo" in errores, errores


def test_si_git_no_esta_en_el_path_deja_pasar_con_un_aviso():
    with Repo() as repo:
        repo.stagear("a.md", CONFLICTO)
        vacia = repo.base / "path-vacio"
        vacia.mkdir()
        codigo, salida, errores = repo.revisar({**repo.env, "PATH": str(vacia)})
        assert (codigo, salida) == (0, ""), (codigo, salida, errores)
        assert "no se pudo revisar" in errores, errores


def test_un_archivo_binario_pasa_aunque_traiga_los_dos_marcadores():
    with Repo() as repo:
        repo.stagear("datos.bin", CONFLICTO.encode("utf-8") + b"\0\x01\x02\n")
        assert repo.revisar() == (0, "", "")


def test_un_nombre_con_espacios_dos_puntos_y_acentos_se_nombra_tal_cual():
    with Repo() as repo:
        nombre = "carpeta con espacio/3:año.md" if os.name != "nt" else "carpeta con espacio/3 año.md"
        repo.stagear(nombre, CONFLICTO)
        codigo, _, errores = repo.revisar()
        assert codigo == 1 and f"{nombre}:2: {APERTURA} HEAD" in errores and f"{nombre}:6:" in errores, errores


def _ejemplo_de_exclusion(errores):
    return errores.split("por ejemplo: ", 1)[1].rstrip("\r\n")


def test_el_ejemplo_de_exclusion_de_una_ruta_simple_sigue_sin_comillas():
    with Repo() as repo:
        repo.stagear("docs/guia.md", CONFLICTO)
        assert _ejemplo_de_exclusion(repo.revisar()[2]) == "docs/guia.md conflict-marker-size=32"


def test_el_ejemplo_de_exclusion_es_un_patron_valido_para_cualquier_ruta():
    casos = (("dir con espacio/café ñandú.txt", '"dir con espacio/café ñandú.txt" conflict-marker-size=32', None),
             ("#nota.md", None, None), ("!importante.md", None, None), ("[ab].md", None, "a.md"), ("a?.md", None, "ab.md"),
             ("a*b.md", None, "axb.md"), ('com"illa.md', None, None), ("barra\\invertida.md", None, None),
             ("con\ttab.md", None, None))
    for ruta, esperado, vecino in casos:
        with Repo() as repo:
            for archivo in filter(None, (ruta, vecino)):
                repo.stagear_solo_en_el_indice(archivo, CONFLICTO)
            codigo, _, errores = repo.revisar()
            assert codigo == 1 and f"{ruta}:2:" in errores, (ruta, codigo, errores)
            ejemplo = _ejemplo_de_exclusion(errores)
            assert esperado is None or ejemplo == esperado, (ruta, ejemplo)
            repo.stagear(".gitattributes", ejemplo + "\n")
            if vecino is None:
                assert repo.revisar() == (0, "", ""), (ruta, ejemplo, repo.revisar())
            else:
                codigo, _, errores = repo.revisar()
                assert codigo == 1 and f"{vecino}:2:" in errores and f"{ruta}:" not in errores, (ruta, ejemplo, errores)


def test_en_un_merge_lo_que_trae_el_otro_lado_cuenta_como_agregado():
    with Repo() as repo:
        repo.stagear("base.md", "base\n")
        repo.commitear("base")
        repo.git("checkout", "-q", "-b", "otra")
        repo.stagear("del-otro-lado.md", CONFLICTO)
        repo.commitear("trae marcadores")
        repo.git("checkout", "-q", "main")
        repo.stagear("propio.md", "propio\n")
        repo.commitear("propio")
        repo.git("merge", "--no-commit", "--no-ff", "-q", "otra")
        codigo, _, errores = repo.revisar()
        assert codigo == 1 and "del-otro-lado.md:2:" in errores, errores


def test_un_commit_a_revisa_el_indice_temporal_que_arma_git():
    with Repo() as repo:
        repo.stagear("a.md", "limpio\n")
        repo.commitear("base")
        ganchos = repo.raiz / "ganchos"
        ganchos.mkdir()
        hook = ganchos / "pre-commit"
        hook.write_bytes(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{CLI.as_posix()}"\n'.encode("utf-8"))
        hook.chmod(0o755)
        repo.git("config", "core.hooksPath", "ganchos")
        repo.escribir("a.md", CONFLICTO)
        r = subprocess.run(["git", "commit", "-q", "-a", "-m", "con marcadores"], cwd=repo.raiz, capture_output=True,
                           env=repo.env, timeout=120)
        errores = r.stderr.decode("utf-8", "replace")
        assert r.returncode != 0 and "a.md:2:" in errores, (r.returncode, errores)
        assert repo.git("rev-list", "--count", "HEAD").strip() == "1"


def test_el_cli_rechaza_argumentos():
    with Repo() as repo:
        r = subprocess.run([sys.executable, str(CLI), "--algo"], cwd=repo.raiz, capture_output=True, env=repo.env, timeout=60)
        assert r.returncode == 2 and "uso: marcadores.py" in r.stderr.decode("utf-8", "replace"), r.stderr


def test_ninguna_linea_del_codigo_ni_de_las_pruebas_empieza_con_un_marcador():
    for archivo in (CLI, Path(__file__)):
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            assert not linea.startswith((APERTURA, CIERRE)), (archivo.name, numero)


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
        print("quedaron carpetas temporales: " + ", ".join(SOBRANTES))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
