import sys

sys.dont_write_bytecode = True

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "huellas.py"
TABLA = "plugin/plantillas/huellas.json"
PLUGIN_JSON = "plugin/.claude-plugin/plugin.json"
INDICE = "# {{nombre}} — guía\n\nTickets en `{{tickets}}/`.\n"
PRE_COMMIT_VIEJO = "#!/bin/sh\necho viejo\n"


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def huella_de(texto):
    return "sha256:" + hashlib.sha256(texto.encode("utf-8")).hexdigest()


class Repo:
    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="huellas-"))
        for nombre in ("gitconfig-global", "gitconfig-sistema"):
            (self.dir / nombre).write_text("", encoding="utf-8")
        self.env = {clave: valor for clave, valor in os.environ.items() if not clave.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=str(self.dir / "gitconfig-global"), GIT_CONFIG_SYSTEM=str(self.dir / "gitconfig-sistema"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="prueba", GIT_AUTHOR_EMAIL="prueba@example.com",
                        GIT_COMMITTER_NAME="prueba", GIT_COMMITTER_EMAIL="prueba@example.com")
        self.obra = self.dir / "obra"
        self.obra.mkdir()
        self.git("init", "-q", "-b", "main")
        return self

    def __exit__(self, *_):
        shutil.rmtree(self.dir, onexc=_forzar_borrado)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.obra, env=self.env, capture_output=True, check=True)

    def poner(self, archivos):
        for ruta, contenido in archivos.items():
            destino = self.obra / ruta
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido.encode("utf-8") if isinstance(contenido, str) else contenido)

    def entrega(self, version, archivos):
        self.poner({PLUGIN_JSON: json.dumps({"name": "odd-ws", "version": version}) + "\n", **archivos})
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", f"entrega {version}")
        self.git("tag", "-a", f"odd-ws--v{version}", "-m", f"entrega {version}")

    def correr(self):
        resultado = subprocess.run([sys.executable, str(SCRIPT)], cwd=self.obra, env=self.env, capture_output=True)
        return resultado.returncode, resultado.stdout.decode("utf-8", "replace"), resultado.stderr.decode("utf-8", "replace")

    def tabla(self):
        return json.loads((self.obra / TABLA).read_text(encoding="utf-8"))


def historia(r):
    r.entrega("0.2.0", {"plugin/plantillas/CLAUDE.md": INDICE, "plugin/plantillas/pre-commit": PRE_COMMIT_VIEJO})
    r.entrega("0.10.0", {"plugin/plantillas/pre-commit": "#!/bin/sh\necho nuevo\n",
                         "plugin/plantillas/reglas/verificar.tests.py": "print('prueba')\n"})


def test_reproduce_la_huella_de_cada_plantilla_en_cada_etiqueta_publicada():
    with Repo() as r:
        historia(r)
        codigo, salida, error = r.correr()
        assert codigo == 0 and error == "", (codigo, salida, error)
        tabla = r.tabla()
        con_tickets = huella_de(INDICE.replace("{{tickets}}", "tickets"))
        assert tabla == {"CLAUDE.md": {"0.2.0": con_tickets, "0.10.0": con_tickets},
                         "CLAUDE.controles.md": {},
                         "ticket.md": {},
                         "pre-commit": {"0.2.0": huella_de(PRE_COMMIT_VIEJO), "0.10.0": huella_de("#!/bin/sh\necho nuevo\n")},
                         "reglas/verificar.tests.py": {"0.10.0": huella_de("print('prueba')\n")}}, tabla
        assert tabla["pre-commit"]["0.2.0"] == "sha256:" + hashlib.sha256(r.git("show", "odd-ws--v0.2.0:plugin/plantillas/pre-commit").stdout).hexdigest()
        assert list(tabla["pre-commit"]) == ["0.2.0", "0.10.0"], "por número de versión, no por texto"
        assert salida.splitlines() == [f"{TABLA}: 5 huellas de 2 versiones, de la 0.2.0 a la 0.10.0",
                                       "plugin/plantillas/historial: 4 textos escritos; commitéalos con la tabla"], salida


def test_la_version_sin_etiqueta_toma_las_plantillas_del_arbol_y_una_etiquetada_gana_al_arbol():
    with Repo() as r:
        historia(r)
        r.poner({PLUGIN_JSON: json.dumps({"name": "odd-ws", "version": "0.11.0"}),
                 "plugin/plantillas/pre-commit": PRE_COMMIT_VIEJO.replace("\n", "\r\n").encode("utf-8"),
                 "plugin/plantillas/ticket.md": "﻿ticket nuevo\n"})
        assert r.correr()[0] == 0
        tabla = r.tabla()
        assert tabla["pre-commit"]["0.11.0"] == huella_de(PRE_COMMIT_VIEJO), "sin CRLF"
        assert tabla["ticket.md"] == {"0.11.0": huella_de("ticket nuevo\n")}, "sin BOM y solo desde que existe"
        assert list(tabla["CLAUDE.md"]) == ["0.2.0", "0.10.0", "0.11.0"], tabla
        primera = (r.obra / TABLA).read_bytes()
        assert r.correr()[0] == 0 and (r.obra / TABLA).read_bytes() == primera, "dos corridas, los mismos bytes"
        assert primera.endswith(b"}\n") and b"\r\n" not in primera
        r.poner({PLUGIN_JSON: json.dumps({"name": "odd-ws", "version": "0.10.0"})})
        assert r.correr()[0] == 0
        assert r.tabla()["pre-commit"] == {"0.2.0": huella_de(PRE_COMMIT_VIEJO), "0.10.0": huella_de("#!/bin/sh\necho nuevo\n")}


HISTORIAL = "plugin/plantillas/historial"


def historial_de(r):
    carpeta = r.obra / HISTORIAL
    return {ruta.name: ruta.read_bytes() for ruta in carpeta.iterdir()} if carpeta.is_dir() else {}


def test_escribe_en_el_historial_el_texto_de_cada_huella_que_falta_con_su_huella_por_nombre_y_no_borra_nada():
    with Repo() as r:
        historia(r)
        r.poner({PLUGIN_JSON: json.dumps({"name": "odd-ws", "version": "0.11.0"}),
                 "plugin/plantillas/ticket.md": "﻿ticket\r\nnuevo\r\n"})
        huerfano = r.obra / HISTORIAL / ("0" * 64)
        r.poner({f"{HISTORIAL}/{'0' * 64}": "de otra versión\n"})
        codigo, salida, error = r.correr()
        assert codigo == 0 and error == "", (codigo, salida, error)
        tabla = r.tabla()
        huellas = {h for por_version in tabla.values() for h in por_version.values()}
        escritos = historial_de(r)
        assert set(escritos) == {h[len("sha256:"):] for h in huellas} | {huerfano.name}, sorted(escritos)
        for nombre, contenido in escritos.items():
            if nombre != huerfano.name:
                assert hashlib.sha256(contenido).hexdigest() == nombre, nombre
                assert b"\r" not in contenido and not contenido.startswith(b"\xef\xbb\xbf"), contenido
        assert escritos[tabla["CLAUDE.md"]["0.2.0"][len("sha256:"):]] == INDICE.replace("{{tickets}}", "tickets").encode("utf-8")
        assert escritos[tabla["ticket.md"]["0.11.0"][len("sha256:"):]] == b"ticket\nnuevo\n"
        assert huerfano.read_bytes() == "de otra versión\n".encode("utf-8"), "solo suma: nunca borra ni cambia otro texto"
        assert salida.splitlines() == [f"{TABLA}: 9 huellas de 3 versiones, de la 0.2.0 a la 0.11.0",
                                       f"{HISTORIAL}: 5 textos escritos; commitéalos con la tabla"], salida
        roto = r.obra / HISTORIAL / tabla["pre-commit"]["0.2.0"][len("sha256:"):]
        roto.write_bytes(b"#!/bin/sh\necho otro\n")
        antes = {nombre: (r.obra / HISTORIAL / nombre).stat().st_mtime_ns for nombre in escritos if nombre != roto.name}
        codigo, salida, error = r.correr()
        assert codigo == 0 and salida.splitlines()[1:] == [f"{HISTORIAL}: 1 texto escrito; commitéalo con la tabla"], (salida, error)
        assert roto.read_bytes() == PRE_COMMIT_VIEJO.encode("utf-8"), "un texto que no da su huella se vuelve a escribir"
        assert {n: (r.obra / HISTORIAL / n).stat().st_mtime_ns for n in antes} == antes, "los textos sanos no se tocan"
        codigo, salida, error = r.correr()
        assert codigo == 0 and len(salida.splitlines()) == 1, "sin textos nuevos, la salida de siempre"


def test_si_falta_la_etiqueta_local_de_una_version_de_la_tabla_commiteada_sale_con_2_y_no_toca_la_tabla():
    with Repo() as r:
        historia(r)
        r.poner({PLUGIN_JSON: json.dumps({"name": "odd-ws", "version": "0.11.0"})})
        assert r.correr()[0] == 0
        r.git("add", "-A")
        r.git("commit", "-q", "--no-verify", "-m", "tabla con la 0.11.0 sin publicar")
        r.poner({PLUGIN_JSON: json.dumps({"name": "odd-ws", "version": "0.12.0"})})
        assert r.correr()[0] == 0, "la versión sin etiqueta de la tabla commiteada no es una etiqueta que falte"
        assert "0.11.0" not in r.tabla()["CLAUDE.md"] and "0.12.0" in r.tabla()["CLAUDE.md"], r.tabla()
        r.git("checkout", "-q", "--", TABLA)
        r.git("tag", "-d", "odd-ws--v0.2.0")
        r.git("tag", "-d", "odd-ws--v0.10.0")
        antes = (r.obra / TABLA).read_bytes()
        codigo, salida, error = r.correr()
        assert codigo == 2 and salida == "", (codigo, salida, error)
        assert error.strip() == "huellas.py: faltan las etiquetas locales odd-ws--v0.2.0, odd-ws--v0.10.0: corre `git fetch --tags`", error
        assert (r.obra / TABLA).read_bytes() == antes, "no borra las entradas de las etiquetas que no ve"


def test_sin_poder_leer_la_version_del_plugin_sale_con_error_y_no_escribe():
    with Repo() as r:
        historia(r)
        r.poner({PLUGIN_JSON: "{roto"})
        codigo, salida, error = r.correr()
        assert codigo == 2 and "plugin.json" in error and salida == "", (codigo, salida, error)
        assert not (r.obra / TABLA).exists() and not (r.obra / HISTORIAL).exists()


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
