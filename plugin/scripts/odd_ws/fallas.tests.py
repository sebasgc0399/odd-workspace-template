import sys

sys.dont_write_bytecode = True

import contextlib
import errno
import importlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
SOBRANTES = []
FALLAS = (".claude", "estado", "fallas-de-hooks.jsonl")
VISTA = (".claude", "estado", "fallas-de-hooks.vista")


def m():
    return importlib.import_module("odd_ws.fallas")


def archivos():
    return importlib.import_module("odd_ws.archivos")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Instancia:
    def __enter__(self):
        self.raiz = Path(os.path.realpath(tempfile.mkdtemp(prefix="fallas-test-")))
        (self.raiz / "workspace.config.json").write_text("{}", encoding="utf-8")
        return self

    def anotar(self, mensaje, evento="PostToolUse"):
        m().anotar("verificar_capa", {"hook_event_name": evento}, RuntimeError(mensaje), str(self.raiz))

    def mensajes(self):
        return [entrada["mensaje"] for entrada in m().leer(str(self.raiz))]

    def estado(self):
        return sorted(p.name for p in (self.raiz / ".claude" / "estado").iterdir())

    def __exit__(self, *_):
        shutil.rmtree(self.raiz, onexc=_quitar)
        if self.raiz.exists():
            SOBRANTES.append(str(self.raiz))


@contextlib.contextmanager
def espia():
    modulo = archivos()
    original = modulo.reemplazar
    llamadas = []

    def reemplazar(ruta, contenido):
        llamadas.append(Path(ruta).parts[-3:])
        return original(ruta, contenido)

    modulo.reemplazar = reemplazar
    try:
        yield llamadas
    finally:
        modulo.reemplazar = original


@contextlib.contextmanager
def reemplazo_que_falla():
    modulo = archivos()
    original = modulo.os.replace

    def falla(*_a, **_k):
        raise OSError(errno.EACCES, "Permission denied")

    modulo.os.replace = falla
    try:
        yield
    finally:
        modulo.os.replace = original


def test_el_recorte_del_tope_y_la_vista_se_escriben_con_archivos_reemplazar():
    assert not hasattr(m(), "_reemplazar"), "la copia privada se fue: la escritura atómica vive en odd_ws.archivos"
    with Instancia() as i:
        with espia() as llamadas:
            for numero in range(m().TOPE + 1):
                i.anotar("falla %d" % numero)
            assert llamadas == [FALLAS], llamadas
            assert m().aviso_de_inicio(str(i.raiz)) is not None
            assert llamadas == [FALLAS, VISTA], llamadas


def test_anotar_guarda_las_ultimas_del_tope_y_el_aviso_sale_una_vez_sin_dejar_temporales():
    with Instancia() as i:
        for numero in range(m().TOPE + 5):
            i.anotar("falla %d" % numero)
        assert i.mensajes() == ["falla %d" % n for n in range(5, m().TOPE + 5)], i.mensajes()
        texto = m().aviso_de_inicio(str(i.raiz))
        assert "hubo %d fallas" % m().TOPE in texto and "falla %d" % (m().TOPE + 4) in texto, texto
        assert m().aviso_de_inicio(str(i.raiz)) is None, "ya se mostró"
        vista = (i.raiz.joinpath(*VISTA)).read_bytes()
        assert vista == m().leer(str(i.raiz))[-1]["id"].encode("ascii"), vista
        assert i.estado() == ["fallas-de-hooks.jsonl", "fallas-de-hooks.vista"], i.estado()


def test_si_el_recorte_falla_anotar_no_lanza_y_el_registro_queda_entero_sin_temporales():
    with Instancia() as i:
        for numero in range(m().TOPE):
            i.anotar("falla %d" % numero)
        with reemplazo_que_falla():
            i.anotar("la que sobra")
            assert m().aviso_de_inicio(str(i.raiz)) is not None, "sin poder guardar la vista, el aviso igual sale"
        assert i.mensajes() == ["falla %d" % n for n in range(m().TOPE)] + ["la que sobra"], i.mensajes()
        assert i.estado() == ["fallas-de-hooks.jsonl"], i.estado()


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
