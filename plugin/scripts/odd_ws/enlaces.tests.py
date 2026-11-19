import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.dont_write_bytecode = True


def m():
    return importlib.import_module("odd_ws.enlaces")


class Carpeta:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="enlaces-ñ-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base)


def absoluta(ruta):
    return Path(os.path.abspath(ruta)).as_posix()


def test_un_enlace_a_md_sin_angulares_es_el_mismo_para_las_dos_reglas():
    muestras = ("[a](b.md)", "[a](b.md#x)", "[a](../c/d.md)", "[a](b.txt)", "[a](b.md.txt)", "[a](carpeta/)", "[a](#solo-ancla)",
                "[a](https://x.org/b.md)", "[a](b.md \"titulo\")", "![img](i.png)", "[a](C:/x/y.md)", "[](vacio.md)", "[a](ñ.md#sección)")
    for muestra in muestras:
        md = m().LINK_MD_RE.search(muestra)
        general = m().ENLACE_RE.search(muestra)
        crudo = general and (general.group(3) or "")
        destino, _, ancla = (crudo or "").partition("#")
        a_md = general is not None and destino.endswith(".md")
        assert (md is not None) == a_md, muestra
        if md:
            assert (md.group(1), md.group(2)) == (destino, "#" + ancla if ancla else None), muestra


def test_enlaces_resuelve_contra_la_carpeta_y_dice_el_tipo_o_que_falta():
    with Carpeta() as base:
        (base / "notas").mkdir()
        (base / "notas" / "guía.md").write_bytes(b"x")
        (base / "con espacios").mkdir()
        texto = ("[Guía](notas/guía.md#uso) [notas](notas/) [espacios](<con espacios>) [falta](nada.txt)\n"
                 "[web](https://x.org/a#b) [arriba](#titulo) [partido\n en dos](notas)\n")
        hallados = list(m().enlaces(texto, base))
        assert hallados == [
            ("Guía", "notas/guía.md", absoluta(base / "notas" / "guía.md"), "archivo"),
            ("notas", "notas/", absoluta(base / "notas"), "carpeta"),
            ("espacios", "con espacios", absoluta(base / "con espacios"), "carpeta"),
            ("falta", "nada.txt", absoluta(base / "nada.txt"), None),
            ("web", "https://x.org/a#b", None, None),
            ("partido en dos", "notas", absoluta(base / "notas"), "carpeta"),
        ], hallados


def test_existe_y_resolver_no_rompen_con_una_ruta_imposible():
    imposible = Path("a\0b")
    assert m().existe(imposible) is False
    assert isinstance(m().resolver(imposible), Path)
    hallados = list(m().enlaces("[x](a\0b.md)", Path(".")))
    assert [(e.texto, e.tipo) for e in hallados] == [("x", None)], hallados


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
