import sys

sys.dont_write_bytecode = True

import ast
import builtins
import contextlib
import errno
import importlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
EN_WINDOWS = os.name == "nt"
SOBRANTES = []


def m():
    return importlib.import_module("odd_ws.archivos")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Temporal:
    def __enter__(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="archivos-test-")))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def nombres(carpeta):
    return sorted(p.name for p in Path(carpeta).iterdir())


@contextlib.contextmanager
def reemplazo_que_falla():
    modulo = m()
    original = modulo.os.replace

    def falla(*_a, **_k):
        raise OSError(errno.EACCES, "Permission denied")

    modulo.os.replace = falla
    try:
        yield
    finally:
        modulo.os.replace = original


@contextlib.contextmanager
def escritura_que_falla():
    original = builtins.open

    class Lleno:
        def __init__(self, real):
            self.real = real

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.real.close()

        def write(self, datos):
            self.real.write(datos[: len(datos) // 2])
            raise OSError(errno.ENOSPC, "No space left on device")

    def abrir(ruta, modo="r", *a, **k):
        archivo = original(ruta, modo, *a, **k)
        return Lleno(archivo) if modo == "wb" else archivo

    builtins.open = abrir
    try:
        yield
    finally:
        builtins.open = original


def test_reemplaza_el_contenido_crea_el_que_no_existe_y_no_deja_temporales():
    with Temporal() as base:
        existente = base / "a.txt"
        existente.write_bytes(b"viejo\r\n")
        m().reemplazar(existente, b"nuevo\n")
        m().reemplazar(str(base / "b.bin"), b"\x00\xff")
        assert existente.read_bytes() == b"nuevo\n"
        assert (base / "b.bin").read_bytes() == b"\x00\xff"
        assert nombres(base) == ["a.txt", "b.bin"], nombres(base)


def test_si_falla_el_reemplazo_el_original_queda_y_no_queda_el_temporal():
    with Temporal() as base:
        ruta = base / "a.txt"
        ruta.write_bytes(b"original\n")
        with reemplazo_que_falla():
            try:
                m().reemplazar(ruta, b"nuevo\n")
            except OSError as error:
                assert error.errno == errno.EACCES, error
            else:
                raise AssertionError("la falla del reemplazo tiene que llegar a quien llama")
        assert ruta.read_bytes() == b"original\n"
        assert nombres(base) == ["a.txt"], nombres(base)


def test_si_falla_la_escritura_el_original_queda_y_no_queda_el_temporal():
    with Temporal() as base:
        ruta = base / "a.txt"
        ruta.write_bytes(b"original\n")
        with escritura_que_falla():
            try:
                m().reemplazar(ruta, b"nuevo contenido\n")
            except OSError as error:
                assert error.errno == errno.ENOSPC, error
            else:
                raise AssertionError("la falla de la escritura tiene que llegar a quien llama")
        assert ruta.read_bytes() == b"original\n"
        assert nombres(base) == ["a.txt"], nombres(base)


def test_una_falla_que_no_es_de_disco_tambien_limpia_el_temporal_y_llega_a_quien_llama():
    with Temporal() as base:
        ruta = base / "a.txt"
        ruta.write_bytes(b"original\n")
        try:
            m().reemplazar(ruta, "texto, no bytes")
        except TypeError:
            pass
        else:
            raise AssertionError("un contenido que no son bytes tiene que fallar")
        assert ruta.read_bytes() == b"original\n"
        assert nombres(base) == ["a.txt"], nombres(base)


def test_conserva_los_permisos_del_destino():
    with Temporal() as base:
        ruta = base / "script.sh"
        ruta.write_bytes(b"#!/bin/sh\n")
        if EN_WINDOWS:
            antes = stat.S_IMODE(os.stat(ruta).st_mode)
            m().reemplazar(ruta, b"#!/bin/sh\necho 1\n")
            assert stat.S_IMODE(os.stat(ruta).st_mode) == antes
        else:
            os.chmod(ruta, 0o750)
            m().reemplazar(ruta, b"#!/bin/sh\necho 1\n")
            assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o750, oct(os.stat(ruta).st_mode)
        assert ruta.read_bytes() == b"#!/bin/sh\necho 1\n"


def test_en_windows_un_destino_de_solo_lectura_falla_sin_tocarlo_ni_dejar_el_temporal():
    if not EN_WINDOWS:
        return
    with Temporal() as base:
        ruta = base / "a.txt"
        ruta.write_bytes(b"original\n")
        os.chmod(ruta, stat.S_IREAD)
        try:
            m().reemplazar(ruta, b"nuevo\n")
        except PermissionError:
            pass
        else:
            raise AssertionError("un archivo de solo lectura no se reemplaza en Windows")
        finally:
            os.chmod(ruta, stat.S_IREAD | stat.S_IWRITE)
        assert ruta.read_bytes() == b"original\n"
        assert nombres(base) == ["a.txt"], nombres(base)


def test_un_enlace_simbolico_se_sigue_y_se_reemplaza_su_destino():
    with Temporal() as base:
        destino = base / "real" / "a.txt"
        destino.parent.mkdir()
        destino.write_bytes(b"original\n")
        enlace = base / "enlace.txt"
        try:
            os.symlink(destino, enlace)
        except (OSError, NotImplementedError):
            return
        m().reemplazar(enlace, b"nuevo\n")
        assert enlace.is_symlink(), "el enlace sigue siendo un enlace"
        assert destino.read_bytes() == b"nuevo\n"
        assert nombres(base) == ["enlace.txt", "real"] and nombres(destino.parent) == ["a.txt"]


def test_es_un_modulo_hoja_que_no_importa_nada_de_odd_ws():
    arbol = ast.parse((AQUI / "archivos.py").read_text(encoding="utf-8"))
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            importados.add(nodo.module or "")
    assert not any(nombre == "odd_ws" or nombre.startswith("odd_ws.") or nombre == "" for nombre in importados), importados


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
