import os
import shutil
import subprocess
from pathlib import Path

PLAZO = 15
ABRIBLES = frozenset((".md", ".markdown", ".txt", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonc", ".yml", ".yaml", ".toml",
                      ".ini", ".cfg", ".xml", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))
WINDOWS, MACOS, WSL, LINUX, REMOTO, SIN_PANTALLA = "windows", "macos", "wsl", "linux", "remoto", "sin pantalla"
ABRIDORES = {WINDOWS: "explorer", MACOS: "open", WSL: "explorer.exe", LINUX: "xdg-open"}
CON_EXPLORER = (WINDOWS, WSL)
NO_ABRE = {
    REMOTO: "la sesión es remota (SSH_CONNECTION), así que se abriría en otra máquina",
    SIN_PANTALLA: "no hay pantalla (ni DISPLAY ni WAYLAND_DISPLAY), así que no hay dónde abrirlo",
}
ABRE_UNA_CARPETA = "abierto en el gestor de archivos"
ABRE_UN_ARCHIVO = "abierto con su programa"
MUESTRA = "mostrado en su carpeta sin abrirlo, porque abrirlo podría ejecutarlo"
SEPARA_EN_LAS_COMAS = "separa las rutas en las comas y podría abrir otra cosa: ábrela a mano"


class NoAbrio(Exception):
    pass


def escenario(entorno, plataforma):
    if entorno.get("SSH_CONNECTION"):
        return REMOTO
    if plataforma == "win32":
        return WINDOWS
    if plataforma == "darwin":
        return MACOS
    if entorno.get("WSL_DISTRO_NAME"):
        return WSL
    if entorno.get("DISPLAY") or entorno.get("WAYLAND_DISPLAY"):
        return LINUX
    return SIN_PANTALLA


def se_abre(real, lugar):
    if os.path.isdir(real):
        return not (lugar == MACOS and Path(real).suffix)
    return Path(real).suffix.lower() in ABRIBLES


def buscar(nombre, entorno):
    for carpeta in (entorno.get("PATH") or "").split(os.pathsep):
        if carpeta and os.path.isabs(carpeta):
            encontrado = shutil.which(os.path.join(carpeta, nombre))
            if encontrado:
                return encontrado
    return None


def _correr(nombre, argv, plazo, **salidas):
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, timeout=plazo, start_new_session=True, **salidas)
    except subprocess.TimeoutExpired:
        raise NoAbrio(f"{nombre} no respondió en {plazo} s")
    except OSError as error:
        raise NoAbrio(f"{nombre} no arrancó ({error})")


def _programa(nombre, entorno):
    programa = buscar(nombre, entorno)
    if programa is None:
        raise NoAbrio(f"no encontré {nombre} en el PATH")
    return programa


def _ruta_de_windows(real, entorno, plazo):
    resultado = _correr("wslpath", [_programa("wslpath", entorno), "-w", real], plazo, capture_output=True)
    convertida = resultado.stdout.decode("utf-8", "replace").rstrip("\r\n")
    if resultado.returncode != 0 or not convertida:
        raise NoAbrio(f"wslpath no convirtió la ruta (salida {resultado.returncode})")
    return convertida


def _orden(lugar, programa, destino, abre):
    nombre = ABRIDORES[lugar]
    if abre:
        return [programa, destino], nombre
    if lugar in CON_EXPLORER:
        return [programa, "/select,", destino], f"{nombre} /select"
    if lugar == MACOS:
        return [programa, "-R", destino], f"{nombre} -R"
    return [programa, os.path.dirname(destino)], f"{nombre} sobre su carpeta"


def _abrir(real, entorno, plataforma, plazo):
    lugar = escenario(entorno, plataforma)
    if lugar in NO_ABRE:
        raise NoAbrio(NO_ABRE[lugar])
    if lugar in CON_EXPLORER and "," in real:
        raise NoAbrio(f"{ABRIDORES[lugar]} {SEPARA_EN_LAS_COMAS}")
    programa = _programa(ABRIDORES[lugar], entorno)
    abre = se_abre(real, lugar)
    destino = _ruta_de_windows(real, entorno, plazo) if lugar == WSL else real
    argv, como = _orden(lugar, programa, destino, abre)
    resultado = _correr(ABRIDORES[lugar], argv, plazo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if lugar not in CON_EXPLORER and resultado.returncode != 0:
        raise NoAbrio(f"{ABRIDORES[lugar]} falló (salida {resultado.returncode})")
    que = MUESTRA if not abre else ABRE_UNA_CARPETA if os.path.isdir(real) else ABRE_UN_ARCHIVO
    return f"{que}: {Path(real).as_posix()} ({como})"


def abrir(ruta, entorno, plataforma, plazo=PLAZO):
    try:
        try:
            real = os.path.realpath(ruta, strict=True)
        except (OSError, ValueError):
            raise NoAbrio("ya no existe")
        if not (os.path.isdir(real) or os.path.isfile(real)):
            raise NoAbrio("no es un archivo ni una carpeta")
        return True, _abrir(real, entorno, plataforma, plazo)
    except NoAbrio as motivo:
        return False, f"no se abrió {ruta}: {motivo}"
