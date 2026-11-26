import sys

sys.dont_write_bytecode = True

import importlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "fusionar_plantillas.py"
sys.path.insert(0, str(AQUI))

NOMBRE = "Mi proyecto"
INDICE_01 = "# {{nombre}} — guía\n\nTickets en `{{tickets}}/`.\n\n## Reglas\n\n- uno\n- dos\n\n## Notas\n\nUna nota.\n\n## Fin\n\nCierre.\n"
INDICE_02 = INDICE_01.replace("- dos\n", "- dos, de **{{nombre}}**\n").replace("Cierre.\n", "Cierre nuevo.\n")
PRE_01 = "#!/bin/sh\nset -e\necho uno\necho medio\necho fin\nexit 0\n"
PRE_02 = PRE_01.replace("set -e\n", "set -eu\n")
TICKET = "# ticket\n\n## Specs\n"
PRUEBA = "print('prueba')\n"
POR_VERSION = {"0.1.0": {"CLAUDE.md": INDICE_01, "ticket.md": TICKET, "pre-commit": PRE_01, "reglas/verificar.tests.py": PRUEBA},
               "0.2.0": {"CLAUDE.md": INDICE_02, "ticket.md": TICKET, "pre-commit": PRE_02, "reglas/verificar.tests.py": PRUEBA}}


def m():
    return importlib.import_module("odd_ws.plantillas_instancia")


def _quitar(func, ruta, _exc):
    os.chmod(ruta, stat.S_IWRITE)
    func(ruta)


def escribir(base, relativa, contenido):
    ruta = base / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido.encode("utf-8") if isinstance(contenido, str) else contenido)
    return ruta


def renderizada(texto, nombre=NOMBRE):
    return texto.replace("{{tickets}}", "tickets").replace("{{nombre}}", nombre)


class Escenario:
    def __init__(self, anotada="0.1.0", copias=None):
        self.anotada, self.copias = anotada, copias or {}

    def __enter__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="fusionar-")))
        for nombre in ("gitconfig-global", "gitconfig-sistema"):
            (self.base / nombre).write_text("", encoding="utf-8")
        self.env = {clave: valor for clave, valor in os.environ.items() if not clave.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=str(self.base / "gitconfig-global"), GIT_CONFIG_SYSTEM=str(self.base / "gitconfig-sistema"),
                        GIT_CONFIG_NOSYSTEM="1")
        self.plugin = self.base / "plugin"
        escribir(self.plugin, ".claude-plugin/plugin.json", json.dumps({"name": "odd-ws", "version": "0.2.0"}))
        tabla = {}
        for version, textos in POR_VERSION.items():
            for plantilla, texto in textos.items():
                forma = m().texto_de_la_huella(plantilla, texto.encode("utf-8"))
                huella = m().huella(forma)
                tabla.setdefault(plantilla, {})[version] = huella
                escribir(self.plugin, "plantillas/historial/" + huella[len("sha256:"):], forma)
                if version == "0.2.0":
                    escribir(self.plugin, "plantillas/" + plantilla, texto)
        escribir(self.plugin, "plantillas/huellas.json", json.dumps(tabla))
        self.raiz = self.base / "instancia"
        config = {"schema_version": 1, "layers": {"sql": {"extensions": [".sql"]}}}
        if self.anotada is not None:
            config["plantillas"] = self.anotada
        escribir(self.raiz, "workspace.config.json", json.dumps(config))
        copias = {"CLAUDE.md": renderizada(INDICE_01), "tickets/_plantilla/CLAUDE.md": TICKET, ".githooks/pre-commit": PRE_01,
                  ".claude/reglas/verificar_sql.tests.py": PRUEBA}
        for ruta, contenido in {**copias, **self.copias}.items():
            escribir(self.raiz, ruta, contenido)
        return self

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)

    def correr(self, *args):
        resultado = subprocess.run([sys.executable, str(SCRIPT), *args, "--raiz", str(self.raiz), "--plugin", str(self.plugin)],
                                   cwd=self.base, env=self.env, capture_output=True)
        return (resultado.returncode, resultado.stdout.decode("utf-8").replace("\r\n", "\n"),
                resultado.stderr.decode("utf-8").replace("\r\n", "\n"))

    def leer(self, ruta):
        return (self.raiz / ruta).read_bytes()


def test_diff_muestra_lo_que_cambio_la_plantilla_desde_la_version_de_la_copia_con_el_nombre_de_la_copia_y_no_escribe():
    editada = renderizada(INDICE_01).replace("Tickets en `tickets/`.", "Tickets en `tickets/`, y los míos.")
    with Escenario(copias={"CLAUDE.md": editada}) as e:
        codigo, salida, error = e.correr("--diff", "CLAUDE.md")
        assert codigo == 0 and error == "", (codigo, salida, error)
        assert salida == ("--- CLAUDE.md en la 0.1.0\n"
                          "+++ CLAUDE.md en la 0.2.0\n"
                          "@@ -5,7 +5,7 @@\n"
                          " ## Reglas\n"
                          " \n"
                          " - uno\n"
                          "-- dos\n"
                          "+- dos, de **Mi proyecto**\n"
                          " \n"
                          " ## Notas\n"
                          " \n"
                          "@@ -13,4 +13,4 @@\n"
                          " \n"
                          " ## Fin\n"
                          " \n"
                          "-Cierre.\n"
                          "+Cierre nuevo.\n"), salida
        assert e.leer("CLAUDE.md") == editada.encode("utf-8"), "--diff es de solo lectura"
    with Escenario(anotada=None) as e:
        codigo, salida, error = e.correr("--diff", ".githooks/pre-commit")
        assert codigo == 0 and salida.splitlines()[:2] == ["--- .githooks/pre-commit en la 0.1.0", "+++ .githooks/pre-commit en la 0.2.0"], salida
        assert "-set -e\n+set -eu\n" in salida, "una copia sin tocar parte de su propia versión"
        codigo, salida, error = e.correr("--diff", "./tickets/_plantilla/CLAUDE.md")
        assert (codigo, salida) == (0, "tickets/_plantilla/CLAUDE.md ya está al día con la plantilla de la 0.2.0, la del plugin: "
                                       "no hay nada que fusionar\n"), (codigo, salida, error)


def test_fusionar_sin_conflictos_muestra_el_texto_fusionado_y_sin_escribir_no_toca_la_copia():
    editada = renderizada(INDICE_01).replace("Tickets en `tickets/`.", "Tickets en `tickets/`, y los míos.")
    with Escenario(copias={"CLAUDE.md": editada}) as e:
        codigo, salida, error = e.correr("--fusionar", "CLAUDE.md")
        assert codigo == 0 and error == "", (codigo, salida, error)
        assert salida == renderizada(INDICE_02).replace("Tickets en `tickets/`.", "Tickets en `tickets/`, y los míos."), salida
        assert e.leer("CLAUDE.md") == editada.encode("utf-8")


def test_fusionar_con_escribir_reemplaza_la_copia_entera_y_conserva_su_modo():
    editada = PRE_01.replace("echo fin\n", "echo fin propio\n")
    with Escenario() as e:
        ruta = escribir(e.raiz, ".githooks/pre-commit", b"\xef\xbb\xbf" + editada.replace("\n", "\r\n").encode("utf-8"))
        if os.name != "nt":
            os.chmod(ruta, 0o755)
        codigo, salida, error = e.correr("--fusionar", ".githooks/pre-commit", "--escribir")
        assert codigo == 0 and error == "", (codigo, salida, error)
        assert salida == (".githooks/pre-commit: fusionada con la plantilla de la 0.2.0. Revisa el cambio con git diff y "
                          "commitéala.\n"), salida
        assert e.leer(".githooks/pre-commit") == PRE_02.replace("echo fin\n", "echo fin propio\n").encode("utf-8")
        assert sorted(p.name for p in ruta.parent.iterdir()) == ["pre-commit"], "sin temporales"
        if os.name != "nt":
            assert os.stat(ruta).st_mode & 0o777 == 0o755
        codigo, salida, error = e.correr("--fusionar", ".githooks/pre-commit", "--escribir")
        assert (codigo, salida) == (0, ".githooks/pre-commit ya tiene los cambios de la plantilla de la 0.2.0: "
                                       "no hay nada que escribir\n"), (codigo, salida, error)


def test_fusionar_con_conflictos_muestra_solo_los_bloques_sale_con_cuantos_son_y_no_escribe_nada():
    editada = renderizada(INDICE_01).replace("- dos\n", "- dos mío\n").replace("Cierre.\n", "Cierre mío.\n")
    for argumentos in ((), ("--escribir",)):
        with Escenario(copias={"CLAUDE.md": editada}) as e:
            codigo, salida, error = e.correr("--fusionar", "CLAUDE.md", *argumentos)
            assert codigo == 2 and error == "", (codigo, salida, error)
            assert salida == ("CLAUDE.md: 2 conflictos entre tu copia y la plantilla de la 0.2.0, desde la de la 0.1.0. "
                              "No se escribió nada: resuélvelos en la copia.\n"
                              "\n"
                              "<<<<<<< tu copia\n"
                              "- dos mío\n"
                              "=======\n"
                              "- dos, de **Mi proyecto**\n"
                              ">>>>>>> plantilla de la 0.2.0\n"
                              "\n"
                              "<<<<<<< tu copia\n"
                              "Cierre mío.\n"
                              "=======\n"
                              "Cierre nuevo.\n"
                              ">>>>>>> plantilla de la 0.2.0\n"), salida
            assert e.leer("CLAUDE.md") == editada.encode("utf-8"), argumentos
            assert sorted(p.name for p in e.raiz.iterdir()) == [".claude", ".githooks", "CLAUDE.md", "tickets", "workspace.config.json"]


def test_lo_que_no_se_puede_fusionar_sale_con_255_y_dice_por_que():
    with Escenario() as e:
        codigo, salida, error = e.correr("--diff", "README.md")
        assert codigo == 255 and salida == "" and "README.md no es una copia de una plantilla del plugin" in error, (codigo, error)
        assert "CLAUDE.md, tickets/_plantilla/CLAUDE.md, .githooks/pre-commit, .claude/reglas/verificar_sql.tests.py" in error, error
        codigo, salida, error = e.correr("--diff", "CLAUDE.md", "--escribir")
        assert codigo == 255 and "--escribir va con --fusionar" in error, (codigo, error)
        tabla = json.loads((e.plugin / "plantillas" / "huellas.json").read_text(encoding="utf-8"))
        (e.plugin / "plantillas" / "historial" / tabla["pre-commit"]["0.1.0"][len("sha256:"):]).unlink()
        escribir(e.raiz, ".githooks/pre-commit", PRE_01.replace("echo fin\n", "echo fin propio\n"))
        codigo, salida, error = e.correr("--fusionar", ".githooks/pre-commit")
        assert codigo == 255 and "el plugin no trae el texto de la plantilla pre-commit de la 0.1.0" in error, (codigo, error)
        assert "Reinstala el plugin" in error, error
    propias = {"CLAUDE.md": "# otra cosa\n", "tickets/_plantilla/CLAUDE.md": "propio\n", ".githooks/pre-commit": "propio\n",
               ".claude/reglas/verificar_sql.tests.py": "propio\n"}
    with Escenario(anotada=None, copias=propias) as e:
        codigo, salida, error = e.correr("--fusionar", "CLAUDE.md")
        assert codigo == 255 and "no se sabe de qué versión del plugin es CLAUDE.md" in error, (codigo, error)


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
