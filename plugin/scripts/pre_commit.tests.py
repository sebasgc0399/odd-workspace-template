import sys

sys.dont_write_bytecode = True

import codecs
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PRE_COMMIT = AQUI / "pre_commit.py"
REGLAS = AQUI / "reglas.py"
SUITE = "import sys\nprint('suite sql corrio')\nsys.exit(%d)\n"
CUERPO = "MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gunVTLw7onLRnrq0/IzW7yWR7Qk"
SECRETOS = (".env", "config/.env", ".env.local", ".ENV", "deploy/server.pem", "tls.key", "id_rsa", ".ssh/id_ed25519",
            "credentials.json", "gcp/credentials-prod.json", "Credentials.JSON")
EJEMPLOS = (".env.example", ".env.sample", ".env.template", "config/.ENV.Example", "credentials.example.json",
            "certs/server.sample.pem", "id_rsa.pub")
MARCADORES = ("/home/<usuario>/x", "/Users/$USER/x", "C:\\Users\\%USERNAME%\\x", "/home/{user}/x", "/Users/Shared/x",
              "C:\\Users\\Public\\x", "/api/home/ana/x")
SOBRANTES = []


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def clave_privada(fin="\n"):
    cuerpo = [(CUERPO * 2)[i * 7:i * 7 + 64] for i in range(4)]
    return fin.join(["-----BEGIN RSA PRIVATE KEY-----", *cuerpo, "-----END RSA PRIVATE KEY-----"]) + fin


class Repo:
    def __init__(self, suite=0, config=True):
        self.suite = suite
        self.config = config

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="pre-commit-py-test-"))
        try:
            return self._armar()
        except BaseException:
            self.__exit__()
            raise

    def _armar(self):
        for nombre in ("gitconfig-global", "gitconfig-sistema"):
            (self.base / nombre).write_bytes(b"")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=str(self.base / "gitconfig-global"),
                        GIT_CONFIG_SYSTEM=str(self.base / "gitconfig-sistema"), GIT_CONFIG_NOSYSTEM="1")
        self.raiz = self.base / "instancia"
        self.raiz.mkdir()
        self.git("init", "-q")
        for clave, valor in (("user.name", "prueba"), ("user.email", "prueba@example.com"), ("core.autocrlf", "false")):
            self.git("config", clave, valor)
        if self.config:
            (self.raiz / "workspace.config.json").write_text(
                json.dumps({"schema_version": 1, "layers": {"sql": {"extensions": [".sql"]}}}), encoding="utf-8")
            suites = self.raiz / ".claude" / "reglas"
            suites.mkdir(parents=True)
            (suites / "verificar_sql.tests.py").write_text(SUITE % self.suite, encoding="utf-8")
        return self

    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.raiz, capture_output=True, env=self.env)
        assert r.returncode == 0, (args, r.stderr.decode("utf-8", "replace"))
        return r

    def poner(self, relativa, contenido):
        ruta = self.raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido if isinstance(contenido, bytes) else contenido.encode("utf-8"))

    def stagear(self, relativa, contenido="x\n"):
        self.poner(relativa, contenido)
        self.git("add", "--", relativa)

    def stageados(self):
        return self.git("diff", "--cached", "--name-only").stdout.decode("utf-8").split()

    def correr(self, script=PRE_COMMIT, *args, extra=None):
        r = subprocess.run([sys.executable, str(script), *args, "--raiz", str(self.raiz)], cwd=self.raiz,
                           capture_output=True, env={**self.env, **(extra or {})})
        return tuple([r.returncode] + [crudo.decode("utf-8", "replace").replace("\r\n", "\n") for crudo in (r.stdout, r.stderr)])

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def test_cada_nombre_de_secreto_stageado_frena_nombra_el_archivo_y_como_sacarlo_del_stage():
    with Repo() as r:
        for nombre in SECRETOS:
            r.stagear(nombre, "TOKEN=abc\n")
            codigo, salida, errores = r.correr()
            assert codigo == 1, (nombre, codigo, salida, errores)
            assert "commit frenado" in errores and f"  {nombre}: " in errores, (nombre, errores)
            assert f"git restore --staged {nombre}\n" in errores and ".example, .sample o .template" in errores, (nombre, errores)
            assert "== sql" not in salida and r.stageados() == [nombre], (nombre, salida, r.stageados())
            r.git("rm", "-q", "--cached", "--", nombre)
            (r.raiz / nombre).unlink()


def test_las_variantes_de_ejemplo_y_la_clave_publica_pasan_y_las_reglas_corren():
    with Repo() as r:
        for nombre in EJEMPLOS:
            r.stagear(nombre, "TOKEN=<tu-token>\n")
        codigo, salida, errores = r.correr()
        assert codigo == 0 and "commit frenado" not in errores, (salida, errores)
        assert "suite sql corrio" in salida and "suites: 1, todas en verde" in salida, salida


def test_varios_archivos_salen_todos_y_una_ruta_con_espacios_va_entre_comillas():
    with Repo() as r:
        r.stagear("mi carpeta/.env")
        codigo, _, errores = r.correr()
        assert codigo == 1 and "Sácalo del stage" in errores and "git restore --staged 'mi carpeta/.env'\n" in errores, errores
        r.stagear("id_rsa")
        codigo, _, errores = r.correr()
        assert codigo == 1 and "Sácalos del stage" in errores, errores
        assert "git restore --staged 'mi carpeta/.env'\n" in errores and "git restore --staged id_rsa\n" in errores, errores


def test_borrar_un_env_del_repo_no_frena():
    with Repo() as r:
        r.stagear(".env", "A=1\n")
        r.git("commit", "-q", "-m", "base")
        r.git("rm", "-q", "--cached", "--", ".env")
        codigo, salida, errores = r.correr()
        assert codigo == 0 and "commit frenado" not in errores and "suite sql corrio" in salida, (salida, errores)


def test_una_clave_privada_pegada_en_un_archivo_stageado_frena():
    for fin in ("\n", "\r\n"):
        with Repo() as r:
            r.stagear("notas/servidor.md", "# Acceso" + fin + "Pega esto:" + fin + clave_privada(fin) + "fin" + fin)
            codigo, salida, errores = r.correr()
            assert codigo == 1 and "commit frenado" in errores, (fin, salida, errores)
            assert "  notas/servidor.md: tiene una clave privada pegada" in errores, errores
            assert "git restore --staged notas/servidor.md\n" in errores and "bórrala del archivo" in errores, errores
            assert ".example, .sample o .template" not in errores and "== sql" not in salida, (salida, errores)


def test_una_clave_de_ejemplo_sin_cuerpo_de_clave_no_frena():
    ejemplos = ("-----BEGIN PRIVATE KEY-----\n<PRIVATE_KEY>\n-----END PRIVATE KEY-----\n"
                "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----\n"
                "El bloque empieza con -----BEGIN PRIVATE KEY----- y termina con -----END PRIVATE KEY-----.\n")
    with Repo() as r:
        r.stagear("doc/claves.md", ejemplos)
        codigo, salida, errores = r.correr()
        assert codigo == 0 and "commit frenado" not in errores and "suite sql corrio" in salida, (salida, errores)


def test_una_ruta_personal_avisa_con_archivo_y_linea_sin_frenar():
    texto = ("Instalado en /home/ana/proyecto\n"
             "copia de /Users/beto/Desktop/x.txt\n"
             "ruta C:\\Users\\u\\AppData\\y y otra vez /home/ana/proyecto\n"
             '{"plugin_root": "C:\\\\Users\\\\ana\\\\odd-ws"}\n')
    with Repo() as r:
        r.stagear("notas.md", texto)
        codigo, salida, errores = r.correr()
        assert codigo == 0 and "commit frenado" not in errores and "suite sql corrio" in salida, (salida, errores)
        assert "aviso" in errores and "no frena el commit" in errores and "<usuario>" in errores, errores
        for linea in ("  notas.md:1: /home/ana/", "  notas.md:2: /Users/beto/", "  notas.md:3: C:\\Users\\u\\",
                      "  notas.md:4: C:\\\\Users\\\\ana\\\\"):
            assert linea + "\n" in errores, (linea, errores)
        assert errores.count("/home/ana/") == 1, errores
        assert r.stageados() == ["notas.md"]


def test_los_marcadores_y_las_carpetas_comunes_no_cuentan_como_ruta_personal():
    with Repo() as r:
        r.stagear("guia.md", "\n".join(MARCADORES) + "\n")
        codigo, salida, errores = r.correr()
        assert codigo == 0 and "rutas personales" not in errores and "suite sql corrio" in salida, (salida, errores)


def test_un_archivo_utf16_con_bom_tambien_se_revisa():
    with Repo() as r:
        r.stagear("datos.sql", codecs.BOM_UTF16_LE + "-- de C:\\Users\\ana\\Desktop\n".encode("utf-16-le"))
        codigo, _, errores = r.correr()
        assert codigo == 0 and "  datos.sql:1: C:\\Users\\ana\\\n" in errores, errores


def test_las_pruebas_de_las_reglas_corren_despues_con_el_mismo_resultado_que_reglas_test():
    for suite, config, esperado in ((0, True, 0), (1, True, 1), (0, False, 2)):
        with Repo(suite=suite, config=config) as r:
            r.stagear("a.txt", "cambio\n")
            propio = r.correr()
            directo = r.correr(REGLAS, "--test")
            assert propio == directo and propio[0] == esperado, (suite, config, propio, directo)


def test_si_git_no_puede_leer_lo_stageado_frena_y_lo_dice():
    with Repo() as r:
        roto = r.base / "indice-roto"
        roto.write_bytes(b"esto no es un indice de git")
        codigo, salida, errores = r.correr(extra={"GIT_INDEX_FILE": str(roto)})
        assert codigo == 1 and "no se pudo revisar lo stageado" in errores and "== sql" not in salida, (salida, errores)
        assert "Traceback" not in errores, errores


def test_sin_raiz_sale_con_el_uso():
    r = subprocess.run([sys.executable, str(PRE_COMMIT)], capture_output=True)
    assert r.returncode == 2 and b"--raiz" in r.stderr, r


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
