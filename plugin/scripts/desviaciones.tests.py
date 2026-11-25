import sys

sys.dont_write_bytecode = True

import contextlib
import importlib
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "desviaciones.py"
sys.path.insert(0, str(AQUI))

ENCABEZADO = "id,ubicacion,resumen,porque,fecha\n"
REPO = "db:src/ventas.sql@abc1234:10-14"
CATCH = "catch-silencioso,%s,El CATCH no relanza el error,Lo pide el contrato con el POS,2026-11-25\n" % REPO
GLOSARIO = "typo-congelado,docs/glosario.md,Dice Reponse,Otro sistema consume ese nombre,2026-01-02\n"
LINEA_CATCH = "catch-silencioso %s — El CATCH no relanza el error: Lo pide el contrato con el POS" % REPO
LINEA_GLOSARIO = "typo-congelado docs/glosario.md — Dice Reponse: Otro sistema consume ese nombre"
SOBRANTES = []


def m():
    return importlib.import_module("desviaciones")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Instancia:
    def __init__(self, csv=None, config=None):
        self.csv, self.config = csv, config

    def __enter__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="desviaciones-cli-")))
        raiz = self.base / "instancia"
        (raiz / "tickets").mkdir(parents=True)
        config = self.config if self.config is not None else json.dumps({"schema_version": 1, "repos": {"db": {}}, "layers": {}})
        (raiz / "workspace.config.json").write_text(config, encoding="utf-8")
        if self.csv is not None:
            ruta = raiz / ".claude" / "reglas" / "desviaciones.csv"
            ruta.parent.mkdir(parents=True)
            ruta.write_text(self.csv, encoding="utf-8")
        return raiz

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def correr(argv, cwd=None):
    salida, error = io.StringIO(), io.StringIO()
    previo, previa = os.getcwd(), os.environ.pop("CLAUDE_PROJECT_DIR", None)
    try:
        if cwd is not None:
            os.chdir(cwd)
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            codigo = m().main([str(a) for a in argv])
    finally:
        os.chdir(previo)
        if previa is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = previa
    return codigo, salida.getvalue(), error.getvalue()


def test_sin_el_archivo_imprime_ninguna_y_sale_con_0():
    with Instancia() as raiz:
        assert correr(["--raiz", raiz]) == (0, "ninguna\n", "")
        assert correr([], cwd=raiz / "tickets") == (0, "ninguna\n", ""), "sin --raiz, la instancia sale de la carpeta de la sesión"
    with Instancia(csv=ENCABEZADO) as raiz:
        assert correr(["--raiz", raiz]) == (0, "ninguna\n", ""), "solo el encabezado"


def test_imprime_una_linea_por_desviacion_valida_y_sale_con_0():
    with Instancia(csv=ENCABEZADO + CATCH + GLOSARIO) as raiz:
        assert correr(["--raiz", raiz]) == (0, LINEA_CATCH + "\n" + LINEA_GLOSARIO + "\n", "")


def test_con_una_fila_mal_formada_imprime_las_validas_lista_los_problemas_y_sale_con_1():
    with Instancia(csv=ENCABEZADO + CATCH + "roto,web:a.ts@abc1234:1-2,r,p,2026-11-25\n" + GLOSARIO + "sin-fecha,docs/a.md,r,p\n") as raiz:
        codigo, salida, error = correr(["--raiz", raiz])
        assert codigo == 1 and salida == LINEA_CATCH + "\n" + LINEA_GLOSARIO + "\n", (codigo, salida)
        assert error.splitlines() == [
            "desviaciones: .claude/reglas/desviaciones.csv:3: el repo 'web' no está en workspace.config.json (repos: db)",
            "desviaciones: .claude/reglas/desviaciones.csv:5: falta fecha"], error
    with Instancia(csv="id,ubicacion\n" + CATCH) as raiz:
        codigo, salida, error = correr(["--raiz", raiz])
        assert (codigo, salida) == (1, "ninguna\n") and "desviaciones.csv:1: el encabezado no es" in error, (codigo, salida, error)


def test_un_error_de_uso_o_de_entorno_sale_con_2_sin_imprimir_desviaciones():
    with Instancia(csv=ENCABEZADO + CATCH) as raiz:
        codigo, salida, error = correr(["--no-existe"])
        assert codigo == 2 and salida == "" and "--no-existe" in error, (codigo, salida, error)
        codigo, salida, error = correr(["--raiz", raiz / "tickets"])
        assert codigo == 2 and salida == "" and "workspace.config.json" in error, (codigo, salida, error)
        codigo, salida, error = correr([], cwd=raiz.parent)
        assert codigo == 2 and salida == "" and "--raiz" in error, (codigo, salida, error)
    with Instancia(csv=ENCABEZADO + CATCH, config="{ rota") as raiz:
        codigo, salida, error = correr(["--raiz", raiz])
        assert codigo == 2 and salida == "" and "la config está rota" in error, (codigo, salida, error)


def test_la_cli_como_proceso_sale_con_su_codigo_y_escribe_utf8_aunque_la_consola_no_lo_sea():
    with Instancia(csv=ENCABEZADO + CATCH + "ñandú,docs/a.md,r,p\n") as raiz:
        entorno = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        entorno["PYTHONIOENCODING"] = "cp1252"
        r = subprocess.run([sys.executable, str(SCRIPT), "--raiz", str(raiz)], capture_output=True, env=entorno)
        assert r.returncode == 1, (r.returncode, r.stderr)
        assert r.stdout.decode("utf-8").replace("\r\n", "\n") == LINEA_CATCH + "\n", r.stdout
        assert "desviaciones.csv:3: falta fecha" in r.stderr.decode("utf-8"), r.stderr
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, env=entorno)
        assert r.returncode == 0 and b"--raiz" in r.stdout, (r.returncode, r.stdout)


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
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
