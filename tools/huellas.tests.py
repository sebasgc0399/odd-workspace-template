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
        assert salida.strip() == f"{TABLA}: 5 huellas de 2 versiones, de la 0.2.0 a la 0.10.0", salida


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


def test_sin_poder_leer_la_version_del_plugin_sale_con_error_y_no_escribe():
    with Repo() as r:
        historia(r)
        r.poner({PLUGIN_JSON: "{roto"})
        codigo, salida, error = r.correr()
        assert codigo == 2 and "plugin.json" in error and salida == "", (codigo, salida, error)
        assert not (r.obra / TABLA).exists()


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
