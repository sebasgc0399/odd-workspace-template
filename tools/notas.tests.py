import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "notas.py"
WORKFLOW = AQUI.parent / ".github" / "workflows" / "release.yml"
sys.path.insert(0, str(AQUI))

CHANGELOG = """# Changelog

Texto de arriba que no es de ninguna versión.

## 0.2.10

- de la 0.2.10

## 0.2.1 (2026-11-04)

- primera línea
### Detalle
- segunda línea

## 0.2.0

## 0.1.0

- de la 0.1.0
"""


def notas():
    import notas as modulo
    return modulo


def correr(argv, cwd, changelog=None):
    if changelog is not None:
        (Path(cwd) / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    resultado = subprocess.run([sys.executable, str(SCRIPT), *argv], cwd=cwd, capture_output=True)
    return resultado.returncode, resultado.stdout.decode("utf-8").replace("\r\n", "\n"), resultado.stderr.decode("utf-8", "replace")


class Carpeta:
    def __enter__(self):
        self.ruta = tempfile.mkdtemp(prefix="notas-")
        return self.ruta

    def __exit__(self, *_):
        shutil.rmtree(self.ruta)


def test_la_seccion_trae_el_cuerpo_sin_su_encabezado_ni_la_seccion_siguiente():
    assert notas().seccion(CHANGELOG, "0.2.1") == "- primera línea\n### Detalle\n- segunda línea\n"


def test_el_encabezado_admite_texto_despues_de_la_version():
    assert notas().seccion("## 1.0.0 (2026-12-01)\n\n- algo\n", "1.0.0") == "- algo\n"


def test_una_version_no_se_confunde_con_otra_que_empieza_igual():
    assert notas().seccion(CHANGELOG, "0.2.10") == "- de la 0.2.10\n"
    assert notas().seccion("## 0.2.10\n\n- solo la 0.2.10\n", "0.2.1") is None


def test_la_ultima_seccion_llega_hasta_el_final():
    assert notas().seccion(CHANGELOG, "0.1.0") == "- de la 0.1.0\n"


def test_una_seccion_vacia_o_ausente_no_tiene_notas():
    assert notas().seccion(CHANGELOG, "0.2.0") is None
    assert notas().seccion(CHANGELOG, "9.9.9") is None
    assert notas().seccion("", "0.1.0") is None


def test_tolera_crlf():
    assert notas().seccion(CHANGELOG.replace("\n", "\r\n"), "0.1.0") == "- de la 0.1.0\n"


def test_la_cli_imprime_la_seccion_de_la_version():
    with Carpeta() as carpeta:
        codigo, salida, error = correr(["0.2.1"], carpeta, CHANGELOG)
        assert codigo == 0 and error == "", (codigo, error)
        assert salida == "- primera línea\n### Detalle\n- segunda línea\n", salida


def test_la_cli_sin_notas_para_la_version_sale_uno_y_dice_que_falta():
    with Carpeta() as carpeta:
        for version in ("0.2.0", "9.9.9"):
            codigo, salida, error = correr([version], carpeta, CHANGELOG)
            assert codigo == 1 and salida == "", (codigo, salida)
            assert "CHANGELOG.md" in error and f"«## {version}»" in error, error


def test_la_cli_sin_changelog_o_con_argumentos_de_mas_sale_dos():
    with Carpeta() as carpeta:
        codigo, _, error = correr(["0.1.0"], carpeta)
        assert codigo == 2 and "CHANGELOG.md" in error, (codigo, error)
        codigo, _, error = correr([], carpeta, CHANGELOG)
        assert codigo == 2 and "uso:" in error, (codigo, error)


def test_el_workflow_se_dispara_con_las_etiquetas_que_exige_la_entrega_y_publica_con_estas_notas():
    import entrega

    texto = WORKFLOW.read_text(encoding="utf-8")
    disparadores = re.findall(r'^\s*-\s*"([^"]+)"\s*$', texto.split("tags:")[1].split("permissions:")[0], re.M)
    assert disparadores == [entrega.PATRON_ETIQUETA], disparadores
    assert f'"${{ETIQUETA#{entrega.PREFIJO_ETIQUETA}}}"' in texto
    assert "tools/notas.py" in texto and "--notes-file" in texto and "--verify-tag" in texto
    assert entrega.PLUGIN_JSON in texto


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
