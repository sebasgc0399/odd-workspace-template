import sys

sys.dont_write_bytecode = True

import codecs
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
SCRIPT = AQUI / "tapar.py"
RECIBO = AQUI / "recibo.py"
SKILL_REVISAR = AQUI.parent / "skills" / "revisar" / "SKILL.md"
REFERENCIA_RE = re.compile(r"references/([\w.-]+\.md)")
sys.path.insert(0, str(AQUI))
SOBRANTES = []

GITHUB = "gh" + "p_" + ("aB3dE5fG7h" * 4)[:36]
AWS = "AK" + "IA" + "Z7Q4X2W9R5T8Y3U6"
CLAVE = "-----BEGIN RSA PRIVATE KEY-----\n+MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgO\n+EePzNm0tRgeLezV6ffAt0gunVTLw7onLRnrq0/I\n+-----END RSA PRIVATE KEY-----"


def m():
    return importlib.import_module("tapar")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Temporal:
    def __enter__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="tapar-test-")))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def correr(argv):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            codigo = m().main([str(a) for a in argv])
        except SystemExit as exc:
            codigo = exc.code
    return codigo, salida.getvalue(), error.getvalue()


def escribir(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos.encode("utf-8") if isinstance(datos, str) else datos)
    return ruta


def linea(ruta, cuantos):
    return "%s: %d secreto(s) tapado(s)\n" % (Path(ruta).as_posix(), cuantos)


def envejecer(ruta):
    os.utime(ruta, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    return os.stat(ruta).st_mtime_ns


def test_tapa_en_el_lugar_cuenta_por_archivo_y_no_reescribe_el_que_no_tiene():
    with Temporal() as base:
        sucio = escribir(base / "entrada" / "repo.diff", "+token = '%s'\n+clave = %s\n contexto\n" % (GITHUB, AWS))
        limpio = escribir(base / "consolidado.md", "Rendimiento: 0 hallazgos\n\nclass=\"dark:bg-gray-800 sm:p-4\" mailto:x@y.com\n")
        antes, mtime = limpio.read_bytes(), envejecer(limpio)
        codigo, salida, error = correr([sucio, limpio])
        assert (codigo, error) == (0, ""), (codigo, error)
        assert salida == linea(sucio, 2) + linea(limpio, 0), salida
        assert sucio.read_bytes() == b"+token = '<GITHUB_TOKEN>'\n+clave = <AWS_ACCESS_KEY_ID>\n contexto\n", sucio.read_bytes()
        assert limpio.read_bytes() == antes and os.stat(limpio).st_mtime_ns == mtime
        assert correr([sucio]) == (0, linea(sucio, 0), "")


def test_conserva_la_codificacion_y_los_fines_de_linea():
    texto = "+línea con tildes\n+token %s\n" % GITHUB
    tapado = "+línea con tildes\n+token <GITHUB_TOKEN>\n"
    crlf = lambda t: t.replace("\n", "\r\n")
    casos = {
        "utf-8 con LF": (texto.encode("utf-8"), tapado.encode("utf-8")),
        "utf-8 con BOM y CRLF": (codecs.BOM_UTF8 + crlf(texto).encode("utf-8"), codecs.BOM_UTF8 + crlf(tapado).encode("utf-8")),
        "utf-16 LE con BOM y CRLF (la redireccion de PowerShell 5.1)": (
            codecs.BOM_UTF16_LE + crlf(texto).encode("utf-16-le"), codecs.BOM_UTF16_LE + crlf(tapado).encode("utf-16-le")),
        "utf-16 BE con BOM": (codecs.BOM_UTF16_BE + texto.encode("utf-16-be"), codecs.BOM_UTF16_BE + tapado.encode("utf-16-be")),
        "bytes que no son utf-8": (b"+ma\xf1ana\r\n+token " + GITHUB.encode() + b"\xff\n", b"+ma\xf1ana\r\n+token <GITHUB_TOKEN>\xff\n"),
    }
    with Temporal() as base:
        for nombre, (crudo, esperado) in casos.items():
            ruta = escribir(base / "a.diff", crudo)
            codigo, salida, error = correr([ruta])
            assert (codigo, salida, error) == (0, linea(ruta, 1), ""), (nombre, codigo, salida, error)
            assert ruta.read_bytes() == esperado, (nombre, ruta.read_bytes())


def test_un_error_de_uso_o_de_lectura_sale_con_2_sin_escribir_nada():
    with Temporal() as base:
        sucio = escribir(base / "a.diff", "+token %s\n" % GITHUB)
        antes = sucio.read_bytes()
        roto = escribir(base / "roto.diff", codecs.BOM_UTF16_LE + b"a\x00b")
        (base / "carpeta").mkdir()
        casos = (
            ([sucio, base / "no-hay.diff"], "no existe %s" % (base / "no-hay.diff").as_posix()),
            ([sucio, base / "carpeta"], "%s es una carpeta" % (base / "carpeta").as_posix()),
            ([sucio, base / "nada" / "*.diff"], "ningun archivo coincide con %s" % (base / "nada" / "*.diff").as_posix()),
            ([sucio, roto], "%s no se puede leer como utf-16-le" % roto.as_posix()),
        )
        for argv, motivo in casos:
            codigo, salida, error = correr(argv)
            assert codigo == 2 and salida == "", (argv, codigo, salida)
            assert error.startswith("tapar: " + motivo) and error.endswith("; no se escribio nada\n"), (motivo, error)
            assert sucio.read_bytes() == antes, argv
        codigo, salida, _ = correr([])
        assert codigo == 2 and salida == "", codigo


def test_un_error_interno_al_tapar_sale_con_2_sin_escribir_nada():
    secretos = m().secretos
    originales = secretos.PATRONES
    with Temporal() as base:
        sucio = escribir(base / "a.diff", "+token %s\n" % GITHUB)
        antes = sucio.read_bytes()
        try:
            secretos.PATRONES = (("ROTO", object()),)
            codigo, salida, error = correr([sucio])
        finally:
            secretos.PATRONES = originales
        assert codigo == 2 and salida == "", (codigo, salida)
        assert error.startswith("tapar: error interno al tapar %s (" % sucio.as_posix()), error
        assert error.endswith("; no se escribio nada\n"), error
        assert sucio.read_bytes() == antes


def test_los_comodines_se_expanden_aunque_el_shell_no_lo_haga_y_un_archivo_repetido_va_una_vez():
    with Temporal() as base:
        x = escribir(base / "entrada" / "x.diff", "+%s\n" % AWS)
        y = escribir(base / "entrada" / "y.diff", "+nada\n")
        z = escribir(base / "entrada" / "triaje.json", '{"detalle": "%s"}' % AWS)
        codigo, salida, error = correr([base / "entrada" / "*.diff", x])
        assert (codigo, error) == (0, ""), (codigo, error)
        assert salida == linea(x, 1) + linea(y, 0), salida
        assert AWS in z.read_text(encoding="utf-8")


def test_el_diff_tapado_conserva_las_lineas_que_cuenta_el_rescate():
    rescatar = importlib.import_module("rescatar")
    diff = ("diff --git a/k.pem b/k.pem\nnew file mode 100644\n--- /dev/null\n+++ b/k.pem\n@@ -0,0 +1,5 @@\n+"
            + CLAVE + "\n+token = %s\n" % GITHUB)
    with Temporal() as base:
        ruta = escribir(base / "repo.diff", diff)
        assert correr([ruta]) == (0, linea(ruta, 2), "")
        tapado = ruta.read_text(encoding="utf-8")
    assert "MIIE" not in tapado and GITHUB not in tapado, tapado
    assert rescatar.lineas_del_diff(tapado) == rescatar.lineas_del_diff(diff) == 5
    assert [l[:1] for l in tapado.split("\n")] == [l[:1] for l in diff.split("\n")], tapado


def _entorno_git(base):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for nombre in ("gitconfig-global", "gitconfig-sistema"):
        (base / nombre).write_bytes(b"")
    entorno.update(GIT_CONFIG_GLOBAL=str(base / "gitconfig-global"), GIT_CONFIG_SYSTEM=str(base / "gitconfig-sistema"),
                   GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(base), PYTHONIOENCODING="utf-8")
    return entorno


def _git(entorno, repo, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "core.autocrlf=false", "-C", str(repo), *args], capture_output=True, env=entorno)
    assert r.returncode in (0, 1), (args, r.stderr)
    return r.stdout


def _script(entorno, script, *args):
    r = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, env=entorno)
    return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n"), r.stderr.decode("utf-8").replace("\r\n", "\n")


def _triaje(recibo, repo, base, archivos):
    huella = recibo.calcular(str(repo), base, archivos)
    senales = {s: {"nivel": "negativa", "detalle": []} for s in recibo.SENALES}
    return {"modo": "rapido", "motivos": [], "senales": senales, "taller": [],
            "repos": [{"ruta": repo.as_posix(), "base": base, "sha256": huella["sha256"],
                       "sha256_por_archivo": huella["sha256_por_archivo"],
                       "archivos": [{"ruta": a, "estado": "M", "capa": "py", "origen": "repo"} for a in huella["archivos"]]}]}


def test_el_recibo_sigue_valiendo_despues_de_tapar_la_carpeta_de_la_revision():
    recibo = importlib.import_module("recibo")
    with Temporal() as base:
        entorno = _entorno_git(base)
        repo = base / "repo"
        escribir(repo / "config.py", "A = 1\n")
        _git(entorno, base, "init", "-q", str(repo))
        _git(entorno, repo, "add", "-A")
        _git(entorno, repo, "commit", "-q", "-m", "inicial")
        inicial = _git(entorno, repo, "rev-parse", "HEAD").decode().strip()
        _git(entorno, repo, "update-ref", "refs/remotes/origin/main", inicial)
        _git(entorno, repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        escribir(repo / "config.py", "A = 1\nTOKEN = '%s'\nAWS = '%s'\n" % (GITHUB, AWS))
        escribir(repo / "nuevo.py", "CLAVE = '%s'\n" % AWS)
        ticket = base / "tickets" / "T-1-secretos"
        carpeta = ticket / "revision" / "2026-11-24-rapido"
        entrada = carpeta / "entrada"
        diff = (_git(entorno, repo, "diff", "--no-color", inicial, "--", "config.py")
                + _git(entorno, repo, "diff", "--no-color", "--no-index", "--", "/dev/null", "nuevo.py"))
        escribir(entrada / "repo.diff", diff)
        escribir(entrada / "triaje.json", json.dumps(_triaje(recibo, repo, inicial, ["config.py", "nuevo.py"]), indent=2))
        escribir(carpeta / "consolidado.md", "Rendimiento: 1 hallazgos · CRITICAL 1 · destino: pendiente\n\n"
                                             "- [CRITICAL] sin ID config.py:2 — un token en el código (`%s`)\n" % GITHUB)
        triaje_antes = (entrada / "triaje.json").read_bytes()
        escritura = ["--write", "--ticket", ticket, "--repo", "%s#%s" % (repo, inicial), "--archivo", "config.py",
                     "--archivo", "nuevo.py", "--modo", "rapido", "--fecha", "2026-11-24", "--reviewer", "revisor-diseno"]
        codigo, salida, error = _script(entorno, RECIBO, *escritura, "--estado", "pendiente")
        assert codigo == 0 and error == "", (codigo, salida, error)

        codigo, salida, error = _script(entorno, SCRIPT, entrada / "*.diff", carpeta / "consolidado.md")
        assert (codigo, error) == (0, ""), (codigo, salida, error)
        assert salida == linea(entrada / "repo.diff", 3) + linea(carpeta / "consolidado.md", 1), salida
        for tapado in (entrada / "repo.diff", carpeta / "consolidado.md"):
            texto = tapado.read_text(encoding="utf-8")
            assert GITHUB not in texto and AWS not in texto and "<GITHUB_TOKEN>" in texto, (tapado, texto)
        assert (entrada / "triaje.json").read_bytes() == triaje_antes

        codigo, salida, error = _script(entorno, RECIBO, "--check", carpeta)
        assert codigo == 0 and salida.startswith("recibo vale: 1 repo(s), 2 archivo(s)"), (codigo, salida, error)
        codigo, salida, error = _script(entorno, RECIBO, *escritura, "--estado", "con-hallazgos")
        assert codigo == 0 and error == "", (codigo, salida, error)
        _git(entorno, repo, "add", "config.py", "nuevo.py")
        _git(entorno, repo, "commit", "-q", "-m", "unidad")
        head = _git(entorno, repo, "rev-parse", "HEAD").decode().strip()
        codigo, salida, error = _script(entorno, RECIBO, "--sellar", carpeta)
        assert codigo == 0 and salida.startswith("recibo sellado:"), (codigo, salida, error)
        guardado = json.loads((carpeta / "recibo.json").read_text(encoding="utf-8"))
        assert guardado["repos"][0]["sellado"] == head and guardado["repos"][0]["estado"] == "con-hallazgos", guardado
        sello = recibo.sello_mas_nuevo(str(ticket), str(repo))
        assert sello is not None and sello[0] == head and sello[2] == "revision/2026-11-24-rapido", sello


def _seccion_8(nucleo):
    return nucleo[nucleo.index("## 8."):nucleo.index("## 9.")]


def test_la_skill_revisar_tapa_la_entrada_y_la_consolidacion_antes_del_check():
    paso_8 = _seccion_8(SKILL_REVISAR.read_text(encoding="utf-8"))
    assert "tapar.py" in paso_8 and paso_8.index("tapar.py") < paso_8.index('recibo.py" --check'), paso_8
    referencias = sorted(set(REFERENCIA_RE.findall(paso_8)))
    textos = [(SKILL_REVISAR.parent / "references" / nombre).read_text(encoding="utf-8") for nombre in referencias]
    comandos = [l for t in textos for l in t.split("\n") if 'python3 "<S>/tapar.py"' in l]
    assert len(comandos) == 1, comandos
    assert "/entrada/*.diff" in comandos[0] and "/consolidado.md" in comandos[0], comandos[0]


def test_la_cli_como_proceso_sale_con_su_codigo_y_escribe_utf8_aunque_la_consola_no_lo_sea():
    with Temporal() as base:
        ruta = escribir(base / "mañana.diff", "+%s\n" % GITHUB)
        entorno = dict(os.environ, PYTHONIOENCODING="cp1252")
        r = subprocess.run([sys.executable, str(SCRIPT), str(ruta)], capture_output=True, env=entorno)
        assert r.returncode == 0 and r.stdout.decode("utf-8").replace("\r\n", "\n") == linea(ruta, 1), (r.returncode, r.stdout)
        r = subprocess.run([sys.executable, str(SCRIPT), str(base / "no-hay.diff")], capture_output=True, env=entorno)
        assert r.returncode == 2 and b"no-hay.diff" in r.stderr, (r.returncode, r.stderr)
        r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, env=entorno)
        assert r.returncode == 2, r.returncode
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, env=entorno)
        assert r.returncode == 0 and b"comodines" in r.stdout, r.stdout


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
