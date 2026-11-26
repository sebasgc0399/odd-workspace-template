import sys

sys.dont_write_bytecode = True

import json
import os
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin" / "scripts"))

import config_loader
from odd_ws import plantillas_instancia

PATRON_ETIQUETA = "odd-ws--v*"
PREFIJO_ETIQUETA = "odd-ws--v"
PLUGIN_JSON = "plugin/" + plantillas_instancia.MANIFIESTO
CARPETA = "plugin/" + plantillas_instancia.CARPETA
TABLA = "plugin/" + plantillas_instancia.TABLA
HISTORIAL = "plugin/" + plantillas_instancia.HISTORIAL
USO = f"uso: huellas.py   (escribe {TABLA} desde las etiquetas {PATRON_ETIQUETA} y las plantillas del árbol de trabajo)"


class NoSePuede(Exception):
    pass


def _git(raiz, *args, entrada=None):
    return subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, input=entrada,
                          **({} if entrada is not None else {"stdin": subprocess.DEVNULL}))


def _error_de(resultado):
    return resultado.stderr.decode("utf-8", "replace").strip() or f"salió con {resultado.returncode}"


def etiquetas(raiz, ref):
    resultado = _git(raiz, "tag", "--merged", ref, "--list", PATRON_ETIQUETA)
    if resultado.returncode != 0:
        raise NoSePuede(f"git no pudo listar las etiquetas {PATRON_ETIQUETA} de {ref}: " + _error_de(resultado))
    nombres = [linea.strip() for linea in resultado.stdout.decode("utf-8", "replace").splitlines()]
    validas = [n for n in nombres if config_loader.VERSION_DEL_PLUGIN_RE.fullmatch(n[len(PREFIJO_ETIQUETA):])]
    return sorted(validas, key=lambda nombre: plantillas_instancia.orden(nombre[len(PREFIJO_ETIQUETA):]))


def leer_en_lote(raiz, objetos):
    if not objetos:
        return {}
    resultado = _git(raiz, "cat-file", "--batch", entrada="".join(objeto + "\n" for objeto in objetos).encode("utf-8"))
    if resultado.returncode != 0:
        raise NoSePuede("git no pudo leer las plantillas de las etiquetas: " + _error_de(resultado))
    salida, posicion, leidos = resultado.stdout, 0, {}
    for objeto in objetos:
        fin = salida.index(b"\n", posicion)
        cabecera = salida[posicion:fin].decode("utf-8", "replace").rsplit(" ", 2)
        posicion = fin + 1
        if len(cabecera) != 3 or not cabecera[2].isdigit():
            leidos[objeto] = None
            continue
        largo = int(cabecera[2])
        leidos[objeto] = salida[posicion:posicion + largo] if cabecera[1] == "blob" else None
        posicion += largo + 1
    return leidos


def version_de(contenido, donde):
    if contenido is None:
        raise NoSePuede(f"{PLUGIN_JSON} no existe {donde}")
    try:
        datos = json.loads(contenido.decode("utf-8-sig"))
    except ValueError as error:
        raise NoSePuede(f"{PLUGIN_JSON} {donde} no es un JSON legible: {error}")
    version = datos.get("version") if isinstance(datos, dict) else None
    if not isinstance(version, str) or not config_loader.VERSION_DEL_PLUGIN_RE.fullmatch(version):
        raise NoSePuede(f"{PLUGIN_JSON} {donde} no tiene un «version» válido (X.Y.Z): {version!r}")
    return version


def _del_arbol(raiz, relativa):
    try:
        return (Path(raiz) / relativa).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise NoSePuede(f"no se puede leer {relativa}: {error}")


def etiquetas_que_faltan(raiz, tabla, propias):
    resultado = _git(raiz, "tag", "--list", PATRON_ETIQUETA)
    if resultado.returncode != 0:
        raise NoSePuede(f"git no pudo listar las etiquetas {PATRON_ETIQUETA}: " + _error_de(resultado))
    locales = {linea.strip() for linea in resultado.stdout.decode("utf-8", "replace").splitlines()}
    por_plantilla = tabla.values() if isinstance(tabla, dict) else ()
    versiones = {v for por_version in por_plantilla if isinstance(por_version, dict) for v in por_version}
    faltan = [v for v in versiones - set(propias) if PREFIJO_ETIQUETA + v not in locales]
    return [PREFIJO_ETIQUETA + v for v in sorted(faltan, key=plantillas_instancia.orden)]


def faltan_las_etiquetas(faltan):
    return f"faltan las etiquetas locales {', '.join(faltan)}: corre `git fetch --tags`"


def _tabla_commiteada(raiz):
    leidos = leer_en_lote(raiz, [f"HEAD:{TABLA}", f"HEAD:{PLUGIN_JSON}"])
    try:
        tabla = json.loads(leidos[f"HEAD:{TABLA}"].decode("utf-8-sig")) if leidos[f"HEAD:{TABLA}"] is not None else {}
    except ValueError:
        return {}, None
    try:
        version = version_de(leidos[f"HEAD:{PLUGIN_JSON}"], "en HEAD")
    except NoSePuede:
        version = None
    return tabla, version


def generar(raiz, ref=None):
    return generar_con_textos(raiz, ref)[0]


def generar_con_textos(raiz, ref=None):
    nombres = etiquetas(raiz, ref or "HEAD")
    objetos = [f"refs/tags/{nombre}:{CARPETA}/{plantilla}" for nombre in nombres for plantilla in plantillas_instancia.PLANTILLAS]
    if ref is not None:
        objetos += [f"{ref}:{PLUGIN_JSON}"] + [f"{ref}:{CARPETA}/{plantilla}" for plantilla in plantillas_instancia.PLANTILLAS]
    leidos = leer_en_lote(raiz, objetos)
    if ref is None:
        version = version_de(_del_arbol(raiz, PLUGIN_JSON), "del árbol de trabajo")
        actuales = {p: _del_arbol(raiz, f"{CARPETA}/{p}") for p in plantillas_instancia.PLANTILLAS}
    else:
        version = version_de(leidos[f"{ref}:{PLUGIN_JSON}"], f"en {ref[:7]}")
        actuales = {p: leidos[f"{ref}:{CARPETA}/{p}"] for p in plantillas_instancia.PLANTILLAS}
    tabla = {plantilla: {} for plantilla in plantillas_instancia.PLANTILLAS}
    textos = {}

    def anotar(plantilla, version_de_la_huella, contenido):
        huella = plantillas_instancia.huella_de_la_plantilla(plantilla, contenido)
        tabla[plantilla][version_de_la_huella] = huella
        textos[huella] = plantillas_instancia.texto_de_la_huella(plantilla, contenido)

    for nombre in nombres:
        for plantilla in plantillas_instancia.PLANTILLAS:
            contenido = leidos[f"refs/tags/{nombre}:{CARPETA}/{plantilla}"]
            if contenido is not None:
                anotar(plantilla, nombre[len(PREFIJO_ETIQUETA):], contenido)
    if PREFIJO_ETIQUETA + version not in nombres:
        for plantilla, contenido in actuales.items():
            if contenido is not None:
                anotar(plantilla, version, contenido)
    ordenada = {plantilla: dict(sorted(versiones.items(), key=lambda par: plantillas_instancia.orden(par[0])))
                for plantilla, versiones in tabla.items()}
    return ordenada, textos, version


def escribir_historial(raiz, textos):
    carpeta = Path(raiz) / HISTORIAL
    escritos = 0
    for huella, texto in sorted(textos.items()):
        ruta = carpeta / huella[len(plantillas_instancia.PREFIJO_DE_LA_HUELLA):]
        try:
            if ruta.is_file() and ruta.read_bytes() == texto:
                continue
            carpeta.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(texto)
        except OSError as error:
            raise NoSePuede(f"no se puede escribir {HISTORIAL}/{ruta.name}: {error}")
        escritos += 1
    return escritos


def serializar(tabla):
    return json.dumps(tabla, indent=2, ensure_ascii=False) + "\n"


def raiz_del_repo():
    resultado = _git(os.getcwd(), "rev-parse", "--show-toplevel")
    if resultado.returncode != 0:
        raise NoSePuede("huellas.py corre dentro del repo del plugin: " + _error_de(resultado))
    return Path(resultado.stdout.decode("utf-8").strip())


def main(argv):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if argv:
        print(USO, file=sys.stderr)
        return 2
    try:
        raiz = raiz_del_repo()
        tabla, textos, version = generar_con_textos(raiz)
        commiteada, la_de_head = _tabla_commiteada(raiz)
        faltan = etiquetas_que_faltan(raiz, commiteada, {version, la_de_head})
        if faltan:
            raise NoSePuede(faltan_las_etiquetas(faltan))
        escritos = escribir_historial(raiz, textos)
    except NoSePuede as error:
        print(f"huellas.py: {error}", file=sys.stderr)
        return 2
    (raiz / TABLA).write_bytes(serializar(tabla).encode("utf-8"))
    versiones = sorted({v for por_version in tabla.values() for v in por_version}, key=plantillas_instancia.orden)
    cuantas = sum(len(por_version) for por_version in tabla.values())
    rango = f", de la {versiones[0]} a la {versiones[-1]}" if versiones else ""
    print(f"{TABLA}: {cuantas} huellas de {len(versiones)} versiones{rango}")
    if escritos:
        print(f"{HISTORIAL}: 1 texto escrito; commitéalo con la tabla" if escritos == 1
              else f"{HISTORIAL}: {escritos} textos escritos; commitéalos con la tabla")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
