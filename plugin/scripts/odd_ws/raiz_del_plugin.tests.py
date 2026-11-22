import importlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

LOCAL = "workspace.local.json"


def m():
    return importlib.import_module("odd_ws.raiz_del_plugin")


class Cache:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="odd-raiz-del-plugin-"))
        self.versiones = self.base / "cache" / "odd-workspace-template" / "odd-ws"
        self.raiz = self.base / "instancia"
        self.raiz.mkdir()
        return self

    def version(self, nombre, con_reglas=True):
        carpeta = self.versiones / nombre
        (carpeta / "scripts").mkdir(parents=True, exist_ok=True)
        if con_reglas:
            (carpeta / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        return carpeta

    def anotar(self, datos):
        (self.raiz / LOCAL).write_text(json.dumps(datos), encoding="utf-8")

    def leido(self):
        return json.loads((self.raiz / LOCAL).read_text(encoding="utf-8"))

    def bytes(self):
        return (self.raiz / LOCAL).read_bytes()

    def __exit__(self, *_):
        shutil.rmtree(self.base, ignore_errors=True)


REPOS = {"mi-proyecto": {"path": "C:/repos/mi-proyecto"}}


def test_una_version_vieja_del_mismo_plugin_pasa_a_la_vigente_y_conserva_las_otras_claves():
    with Cache() as c:
        vieja, vigente = c.version("0.13.1"), c.version("0.13.2")
        c.anotar({"repos": REPOS, "plugin_root": str(vieja)})
        aviso = m().seguir_al_vigente(c.raiz, vigente)
        assert aviso and "0.13.1" in aviso and "0.13.2" in aviso and "pre-commit" in aviso, aviso
        assert c.leido() == {"repos": REPOS, "plugin_root": str(vigente)}, c.leido()
        assert m().seguir_al_vigente(c.raiz, vigente) is None, "una segunda sesión ya no cambia nada"


def test_una_version_borrada_o_a_medio_barrer_del_mismo_plugin_tambien_pasa_a_la_vigente():
    for vieja_con_reglas in (None, False):
        with Cache() as c:
            vigente = c.version("0.13.2")
            vieja = c.version("0.12.1", con_reglas=False) if vieja_con_reglas is False else c.versiones / "0.12.1"
            c.anotar({"plugin_root": str(vieja)})
            aviso = m().seguir_al_vigente(c.raiz, vigente)
            assert aviso and "0.12.1" in aviso and "0.13.2" in aviso, (vieja_con_reglas, aviso)
            assert c.leido() == {"plugin_root": str(vigente)}, c.leido()


def test_un_numero_de_version_con_sufijo_cuenta_como_version():
    with Cache() as c:
        vieja, vigente = c.version("0.13.2-rc.1"), c.version("0.13.2")
        c.anotar({"plugin_root": str(vieja)})
        assert m().seguir_al_vigente(c.raiz, vigente), c.leido()
        assert c.leido() == {"plugin_root": str(vigente)}, c.leido()


def test_fuera_de_la_regla_no_toca_el_archivo():
    with Cache() as c:
        vieja, vigente = c.version("0.13.1"), c.version("0.13.2")
        clon = c.base / "clon" / "plugin"
        (clon / "scripts").mkdir(parents=True)
        (clon / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        otro_cache = c.base / "otro-cache" / "odd-ws" / "0.13.1"
        (otro_cache / "scripts").mkdir(parents=True)
        (otro_cache / "scripts" / "reglas.py").write_text("", encoding="utf-8")
        casos = (
            ("ya es la vigente", {"plugin_root": str(vigente)}, vigente),
            ("sin anotar", {"repos": REPOS}, vigente),
            ("vacío", {"plugin_root": ""}, vigente),
            ("no es texto", {"plugin_root": 7}, vigente),
            ("anotado a mano en un clon", {"plugin_root": str(clon)}, vigente),
            ("de otro caché", {"plugin_root": str(otro_cache)}, vigente),
            ("la sesión corre desde un clon", {"plugin_root": str(vieja)}, clon),
            ("la vigente no tiene reglas.py", {"plugin_root": str(vieja)}, c.version("0.13.3", con_reglas=False)),
        )
        for nombre, datos, plugin in casos:
            c.anotar(datos)
            antes = c.bytes()
            assert m().seguir_al_vigente(c.raiz, plugin) is None, nombre
            assert c.bytes() == antes, nombre
        for nombre, crudo in (("no es JSON", b"{roto"), ("no es un objeto", b"[1, 2]")):
            (c.raiz / LOCAL).write_bytes(crudo)
            assert m().seguir_al_vigente(c.raiz, vigente) is None, nombre
            assert c.bytes() == crudo, nombre
        (c.raiz / LOCAL).unlink()
        assert m().seguir_al_vigente(c.raiz, vigente) is None, "sin workspace.local.json"
        assert not (c.raiz / LOCAL).exists(), "no lo crea"


def test_con_la_copia_de_emergencia_no_toca_nada():
    with Cache() as c:
        vieja, vigente = c.version("0.13.1"), c.version("0.13.2")
        emergencia = c.raiz / ".claude" / "plugin" / "scripts"
        emergencia.mkdir(parents=True)
        (emergencia / "reglas.py").write_text("", encoding="utf-8")
        c.anotar({"plugin_root": str(vieja)})
        antes = c.bytes()
        assert m().seguir_al_vigente(c.raiz, vigente) is None
        assert c.bytes() == antes
        (emergencia / "reglas.py").unlink()
        assert m().seguir_al_vigente(c.raiz, vigente), "control positivo: sin la copia, sí"


def test_la_vigente_por_defecto_es_la_carpeta_del_plugin_que_corre():
    assert m().vigente() == AQUI.parent.parent, m().vigente()
    assert (m().vigente() / "scripts" / "reglas.py").is_file()


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
