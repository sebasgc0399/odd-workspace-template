import os
import shutil
import stat


def _borrar(ruta):
    try:
        os.remove(ruta)
    except FileNotFoundError:
        pass
    except OSError:
        try:
            os.chmod(ruta, stat.S_IREAD | stat.S_IWRITE)
            os.remove(ruta)
        except OSError:
            pass


def reemplazar(ruta, contenido):
    destino = os.path.realpath(os.fspath(ruta))
    temporal = "%s.%d.tmp" % (destino, os.getpid())
    try:
        with open(temporal, "wb") as archivo:
            archivo.write(contenido)
        try:
            shutil.copymode(destino, temporal)
        except FileNotFoundError:
            pass
        os.replace(temporal, destino)
    except BaseException:
        _borrar(temporal)
        raise
