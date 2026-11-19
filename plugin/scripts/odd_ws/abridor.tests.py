import ast
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.dont_write_bytecode = True
NT = os.name == "nt"
CONVERTIDA = "\\\\wsl.localhost\\Distro"
FALSO = (
    "import json, sys, time\n"
    "from pathlib import Path\n"
    "carpeta = Path(__file__).resolve().parent\n"
    "nombre, argumentos = sys.argv[1], sys.argv[2:]\n"
    "with open(carpeta / 'registro.jsonl', 'a', encoding='utf-8') as f:\n"
    "    f.write(json.dumps([nombre, argumentos]) + '\\n')\n"
    "conducta = json.loads((carpeta / 'conducta.json').read_text(encoding='utf-8')).get(nombre, {})\n"
    "if 'convertir' in conducta:\n"
    "    sys.stdout.reconfigure(encoding='utf-8')\n"
    "    sys.stdout.write(conducta['convertir'] + argumentos[-1].replace('/', '\\\\') + '\\n')\n"
    "time.sleep(conducta.get('espera', 0))\n"
    "sys.exit(conducta.get('salida', 0))\n"
)
ESCENARIOS = {
    "windows": ("win32", {}),
    "macos": ("darwin", {}),
    "linux": ("linux", {"DISPLAY": ":0"}),
    "wayland": ("linux", {"WAYLAND_DISPLAY": "wayland-0"}),
    "wsl": ("linux", {"WSL_DISTRO_NAME": "Distro", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}),
}
ABRIDOR = {"windows": "explorer", "macos": "open", "linux": "xdg-open", "wayland": "xdg-open", "wsl": "explorer.exe"}
REVELAR = {"windows": "explorer /select", "macos": "open -R", "linux": "xdg-open sobre su carpeta",
           "wayland": "xdg-open sobre su carpeta", "wsl": "explorer.exe /select"}
ABRE_UNA_CARPETA = "abierto en el gestor de archivos"
ABRE_UN_ARCHIVO = "abierto con su programa"
MUESTRA = "mostrado en su carpeta sin abrirlo, porque abrirlo podría ejecutarlo"
SEPARA_EN_LAS_COMAS = "separa las rutas en las comas y podría abrir otra cosa: abrila a mano"
EJECUTABLES = (".py", ".js", ".ps1", ".bat", ".cmd", ".exe", ".sh", ".command", ".lnk", ".url", ".desktop", ".app", ".html", "")
DOCUMENTOS = (".md", ".markdown", ".txt", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonc", ".yml", ".yaml", ".toml", ".ini",
              ".cfg", ".xml", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def m():
    return importlib.import_module("odd_ws.abridor")


class Caja:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="abridor-ñ-"))
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "falso.py").write_text(FALSO, encoding="utf-8")
        self.conducta({})
        self.docs = self.base / "docs con espacios"
        self.docs.mkdir()
        return self

    def __exit__(self, *_):
        shutil.rmtree(self.base)

    def falsos(self, *nombres):
        for nombre in nombres:
            if NT:
                (self.bin / f"{nombre}.cmd").write_text(f'@"{sys.executable}" "%~dp0falso.py" {nombre} %*\r\n', encoding="ascii")
            else:
                ruta = self.bin / nombre
                ruta.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{self.bin / "falso.py"}" {nombre} "$@"\n', encoding="utf-8")
                ruta.chmod(0o755)

    def conducta(self, valores):
        (self.bin / "conducta.json").write_text(json.dumps({"wslpath": {"convertir": CONVERTIDA}, **valores}), encoding="utf-8")

    def registro(self):
        ruta = self.bin / "registro.jsonl"
        if not ruta.is_file():
            return []
        return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]

    def limpiar_registro(self):
        (self.bin / "registro.jsonl").unlink(missing_ok=True)

    def archivo(self, nombre, carpeta=None):
        ruta = (carpeta or self.docs) / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"x")
        return ruta

    def abrir(self, ruta, escenario, plazo=None, **extra):
        plataforma, entorno = ESCENARIOS[escenario]
        argumentos = {} if plazo is None else {"plazo": plazo}
        return m().abrir(Path(ruta).as_posix(), {"PATH": str(self.bin), **entorno, **extra}, plataforma, **argumentos)


def real(ruta):
    return os.path.realpath(ruta)


def posix(ruta):
    return Path(real(ruta)).as_posix()


def esperado(escenario, ruta, abre):
    destino = real(ruta)
    llamadas = []
    if escenario == "wsl":
        llamadas.append(["wslpath", ["-w", destino]])
        destino = CONVERTIDA + destino.replace("/", "\\")
    if abre:
        argumentos = [destino]
    elif escenario in ("windows", "wsl"):
        argumentos = ["/select,", destino]
    elif escenario == "macos":
        argumentos = ["-R", destino]
    else:
        argumentos = [os.path.dirname(destino)]
    return llamadas + [[ABRIDOR[escenario], argumentos]]


def test_el_escenario_sale_del_entorno_y_la_plataforma():
    casos = [
        ("win32", {}, "windows"),
        ("darwin", {}, "macos"),
        ("linux", {"DISPLAY": ":0"}, "linux"),
        ("linux", {"WAYLAND_DISPLAY": "wayland-0"}, "linux"),
        ("freebsd14", {"DISPLAY": ":0"}, "linux"),
        ("linux", {"WSL_DISTRO_NAME": "Ubuntu"}, "wsl"),
        ("linux", {"WSL_DISTRO_NAME": "Ubuntu", "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}, "wsl"),
        ("linux", {"SSH_CONNECTION": "10.0.0.1 5000 10.0.0.2 22", "DISPLAY": "localhost:10.0"}, "remoto"),
        ("linux", {"SSH_CONNECTION": "10.0.0.1 5000 10.0.0.2 22", "WSL_DISTRO_NAME": "Ubuntu"}, "remoto"),
        ("win32", {"SSH_CONNECTION": "10.0.0.1 5000 10.0.0.2 22"}, "remoto"),
        ("darwin", {"SSH_CONNECTION": "10.0.0.1 5000 10.0.0.2 22"}, "remoto"),
        ("linux", {}, "sin pantalla"),
        ("linux", {"DISPLAY": "", "WAYLAND_DISPLAY": "", "SSH_CONNECTION": "", "WSL_DISTRO_NAME": ""}, "sin pantalla"),
        ("win32", {"SSH_CONNECTION": "", "DISPLAY": ""}, "windows"),
    ]
    for plataforma, entorno, escenario in casos:
        assert m().escenario(entorno, plataforma) == escenario, (plataforma, entorno, m().escenario(entorno, plataforma))


def test_una_carpeta_se_abre_en_el_gestor_de_archivos_en_cada_escenario():
    with Caja() as c:
        c.falsos("explorer", "open", "xdg-open", "explorer.exe", "wslpath")
        carpeta = c.docs / "notas ñ"
        carpeta.mkdir()
        for escenario in ESCENARIOS:
            c.limpiar_registro()
            resultado = c.abrir(carpeta, escenario)
            assert resultado == (True, f"{ABRE_UNA_CARPETA}: {posix(carpeta)} ({ABRIDOR[escenario]})"), (escenario, resultado)
            assert c.registro() == esperado(escenario, carpeta, True), (escenario, c.registro())


def test_un_documento_un_dato_o_una_imagen_se_abre_con_su_programa_en_cada_escenario():
    with Caja() as c:
        c.falsos("explorer", "open", "xdg-open", "explorer.exe", "wslpath")
        guia = c.archivo("guía.md")
        for escenario in ESCENARIOS:
            c.limpiar_registro()
            resultado = c.abrir(guia, escenario)
            assert resultado == (True, f"{ABRE_UN_ARCHIVO}: {posix(guia)} ({ABRIDOR[escenario]})"), (escenario, resultado)
            assert c.registro() == esperado(escenario, guia, True), (escenario, c.registro())


def test_un_script_o_un_ejecutable_se_muestra_en_su_carpeta_en_cada_escenario():
    with Caja() as c:
        c.falsos("explorer", "open", "xdg-open", "explorer.exe", "wslpath")
        script = c.archivo("correr.py")
        for escenario in ESCENARIOS:
            c.limpiar_registro()
            resultado = c.abrir(script, escenario)
            assert resultado == (True, f"{MUESTRA}: {posix(script)} ({REVELAR[escenario]})"), (escenario, resultado)
            assert c.registro() == esperado(escenario, script, False), (escenario, c.registro())


def test_solo_los_documentos_datos_e_imagenes_de_la_lista_se_abren():
    with Caja() as c:
        c.falsos("explorer")
        for i, extension in enumerate(DOCUMENTOS + (".MD", ".Pdf")):
            documento = c.archivo(f"doc{i}{extension}")
            c.limpiar_registro()
            assert c.abrir(documento, "windows") == (True, f"{ABRE_UN_ARCHIVO}: {posix(documento)} (explorer)"), extension
            assert c.registro() == [["explorer", [real(documento)]]], (extension, c.registro())
        for i, extension in enumerate(EJECUTABLES + (".PY", ".Exe")):
            ejecutable = c.archivo(f"ejecutable{i}{extension}")
            c.limpiar_registro()
            assert c.abrir(ejecutable, "windows") == (True, f"{MUESTRA}: {posix(ejecutable)} (explorer /select)"), extension
            assert c.registro() == [["explorer", ["/select,", real(ejecutable)]]], (extension, c.registro())


def test_un_enlace_simbolico_se_decide_por_su_destino_real():
    with Caja() as c:
        c.falsos("open")
        lanzar = c.archivo("lanzar.sh", c.base / "otra carpeta")
        documento = c.archivo("doc.md", c.base / "otra carpeta")
        disfrazado = c.docs / "nota.md"
        atajo = c.docs / "atajo.sh"
        try:
            os.symlink(lanzar, disfrazado)
            os.symlink(documento, atajo)
        except (OSError, NotImplementedError):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert c.abrir(disfrazado, "macos") == (True, f"{MUESTRA}: {posix(lanzar)} (open -R)")
        assert c.registro() == [["open", ["-R", real(lanzar)]]], c.registro()
        c.limpiar_registro()
        assert c.abrir(atajo, "macos") == (True, f"{ABRE_UN_ARCHIVO}: {posix(documento)} (open)")
        assert c.registro() == [["open", [real(documento)]]], c.registro()


def test_en_macos_una_carpeta_con_extension_se_muestra_porque_open_la_lanzaria():
    with Caja() as c:
        c.falsos("open", "explorer", "xdg-open")
        paquete = c.docs / "Herramienta.app"
        paquete.mkdir()
        assert c.abrir(paquete, "macos") == (True, f"{MUESTRA}: {posix(paquete)} (open -R)")
        assert c.registro() == [["open", ["-R", real(paquete)]]], c.registro()
        for escenario in ("windows", "linux"):
            c.limpiar_registro()
            assert c.abrir(paquete, escenario)[0] is True
            assert c.registro() == esperado(escenario, paquete, True), (escenario, c.registro())


def test_la_ruta_va_como_un_solo_argumento_y_nunca_por_una_shell():
    with Caja() as c:
        c.falsos("xdg-open", "explorer")
        raro = c.archivo("a; b $(eco) & `c` 'd'.md")
        for escenario in ("linux", "windows"):
            c.limpiar_registro()
            assert c.abrir(raro, escenario)[0] is True, escenario
            assert c.registro() == [[ABRIDOR[escenario], [real(raro)]]], (escenario, c.registro())


def test_en_windows_y_wsl_una_ruta_con_coma_no_se_abre_ni_se_muestra_y_en_los_demas_sigue_igual():
    with Caja() as c:
        c.falsos("explorer", "open", "xdg-open", "explorer.exe", "wslpath")
        carpeta = c.docs / "notas,viejas"
        carpeta.mkdir()
        for ruta in (c.archivo("q,evil.bat,y.md"), c.archivo("a,b.py"), c.archivo("guía.md", c.docs / "con,coma"), carpeta):
            for escenario in ("windows", "wsl"):
                c.limpiar_registro()
                motivo = f"{ABRIDOR[escenario]} {SEPARA_EN_LAS_COMAS}"
                assert c.abrir(ruta, escenario) == (False, f"no se abrió {ruta.as_posix()}: {motivo}"), (escenario, ruta)
                assert c.registro() == [], (escenario, ruta, c.registro())
            for escenario in ("macos", "linux", "wayland"):
                c.limpiar_registro()
                abre = ruta.suffix != ".py"
                que = ABRE_UNA_CARPETA if ruta.is_dir() else ABRE_UN_ARCHIVO if abre else MUESTRA
                como = ABRIDOR[escenario] if abre else REVELAR[escenario]
                assert c.abrir(ruta, escenario) == (True, f"{que}: {posix(ruta)} ({como})"), (escenario, ruta)
                assert c.registro() == esperado(escenario, ruta, abre), (escenario, ruta, c.registro())


def test_la_coma_se_mira_en_la_ruta_real_que_recibiria_explorer():
    with Caja() as c:
        c.falsos("explorer")
        con_coma = c.archivo("q,evil.bat,y.md", c.base / "otra carpeta")
        sin_coma = c.archivo("doc.md", c.base / "otra carpeta")
        atajo, nombre_con_coma = c.docs / "atajo.md", c.docs / "a,b.md"
        try:
            os.symlink(con_coma, atajo)
            os.symlink(sin_coma, nombre_con_coma)
        except (OSError, NotImplementedError):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert c.abrir(atajo, "windows") == (False, f"no se abrió {atajo.as_posix()}: explorer {SEPARA_EN_LAS_COMAS}")
        assert c.registro() == [], c.registro()
        assert c.abrir(nombre_con_coma, "windows") == (True, f"{ABRE_UN_ARCHIVO}: {posix(sin_coma)} (explorer)")
        assert c.registro() == [["explorer", [real(sin_coma)]]], c.registro()


def test_explorer_que_sale_con_uno_cuenta_como_abierto():
    with Caja() as c:
        c.falsos("explorer", "explorer.exe", "wslpath")
        c.conducta({"explorer": {"salida": 1}, "explorer.exe": {"salida": 1}})
        guia = c.archivo("guía.md")
        assert c.abrir(guia, "windows") == (True, f"{ABRE_UN_ARCHIVO}: {posix(guia)} (explorer)")
        assert c.abrir(guia, "wsl") == (True, f"{ABRE_UN_ARCHIVO}: {posix(guia)} (explorer.exe)")


def test_un_abridor_que_falla_no_cuenta_como_abierto():
    with Caja() as c:
        c.falsos("open", "xdg-open")
        c.conducta({"open": {"salida": 1}, "xdg-open": {"salida": 4}})
        guia = c.archivo("guía.md")
        ruta = Path(guia).as_posix()
        assert c.abrir(guia, "macos") == (False, f"no se abrió {ruta}: open falló (salida 1)")
        assert c.abrir(guia, "linux") == (False, f"no se abrió {ruta}: xdg-open falló (salida 4)")
        assert [nombre for nombre, _ in c.registro()] == ["open", "xdg-open"], c.registro()


def test_wslpath_que_falla_no_abre_nada():
    with Caja() as c:
        c.falsos("explorer.exe", "wslpath")
        c.conducta({"wslpath": {"salida": 1}})
        guia = c.archivo("guía.md")
        assert c.abrir(guia, "wsl") == (False, f"no se abrió {Path(guia).as_posix()}: wslpath no convirtió la ruta (salida 1)")
        assert [nombre for nombre, _ in c.registro()] == ["wslpath"], c.registro()


def test_sin_el_abridor_en_el_path_no_abre_y_nombra_lo_que_busco():
    with Caja() as c:
        guia = c.archivo("guía.md")
        ruta = Path(guia).as_posix()
        for escenario in ESCENARIOS:
            assert c.abrir(guia, escenario) == (False, f"no se abrió {ruta}: no encontré {ABRIDOR[escenario]} en el PATH"), escenario
        c.falsos("explorer.exe")
        assert c.abrir(guia, "wsl") == (False, f"no se abrió {ruta}: no encontré wslpath en el PATH")
        assert c.abrir(guia, "linux", PATH="") == (False, f"no se abrió {ruta}: no encontré xdg-open en el PATH")
        assert c.registro() == [], c.registro()


def test_una_sesion_remota_o_sin_pantalla_no_abre_y_dice_por_que():
    with Caja() as c:
        c.falsos("explorer", "open", "xdg-open", "explorer.exe", "wslpath")
        guia = c.archivo("guía.md")
        ruta = Path(guia).as_posix()
        remota = f"no se abrió {ruta}: la sesión es remota (SSH_CONNECTION), así que se abriría en otra máquina"
        for escenario in ESCENARIOS:
            assert c.abrir(guia, escenario, SSH_CONNECTION="10.0.0.1 5000 10.0.0.2 22") == (False, remota), escenario
        assert m().abrir(ruta, {"PATH": str(c.bin)}, "linux") == (
            False, f"no se abrió {ruta}: no hay pantalla (ni DISPLAY ni WAYLAND_DISPLAY), así que no hay dónde abrirlo")
        assert c.registro() == [], c.registro()


def test_un_abridor_que_no_responde_se_corta_y_no_cuenta_como_abierto():
    with Caja() as c:
        c.falsos("xdg-open")
        c.conducta({"xdg-open": {"espera": 3}})
        guia = c.archivo("guía.md")
        assert c.abrir(guia, "linux", plazo=0.5) == (False, f"no se abrió {Path(guia).as_posix()}: xdg-open no respondió en 0.5 s")


def test_lo_que_no_existe_o_no_es_archivo_ni_carpeta_no_se_abre():
    with Caja() as c:
        c.falsos("explorer", "open", "xdg-open")
        falta = Path(c.docs / "falta.md").as_posix()
        for escenario in ("windows", "macos", "linux"):
            assert c.abrir(falta, escenario) == (False, f"no se abrió {falta}: ya no existe"), escenario
        if hasattr(os, "mkfifo"):
            tubo = c.docs / "tubo.md"
            os.mkfifo(tubo)
            assert c.abrir(tubo, "linux") == (False, f"no se abrió {tubo.as_posix()}: no es un archivo ni una carpeta")
        assert c.registro() == [], c.registro()


def test_el_abridor_solo_se_busca_en_carpetas_absolutas_del_path_y_nunca_en_la_actual():
    with Caja() as c:
        c.falsos("explorer", "xdg-open")
        nombre = "explorer" if NT else "xdg-open"
        previa = os.getcwd()
        os.chdir(c.bin)
        try:
            for path in (".", os.pathsep.join((".", "")), "bin", str(c.base / "vacia")):
                assert m().buscar(nombre, {"PATH": path}) is None, path
            assert m().buscar(nombre, {}) is None
            encontrado = m().buscar(nombre, {"PATH": os.pathsep.join(("", "relativa", str(c.bin)))})
            assert encontrado is not None and os.path.isabs(encontrado) and Path(encontrado).parent == c.bin, encontrado
        finally:
            os.chdir(previa)


def test_el_modulo_solo_usa_la_biblioteca_estandar_y_no_importa_config_loader():
    arbol = ast.parse((AQUI / "abridor.py").read_text(encoding="utf-8"))
    importados = {alias.name for nodo in ast.walk(arbol) if isinstance(nodo, ast.Import) for alias in nodo.names}
    importados |= {nodo.module for nodo in ast.walk(arbol) if isinstance(nodo, ast.ImportFrom)}
    assert importados <= {"os", "sys", "subprocess", "shutil", "pathlib"}, importados


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
