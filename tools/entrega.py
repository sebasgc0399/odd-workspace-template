import fnmatch
import html
import json
import os
import re
import subprocess
import sys

import notas

CEROS = "0" * 40
REF_MAIN = "refs/heads/main"
REF_ETIQUETAS = "refs/tags/"
PATRON_ETIQUETA = "odd-ws--v*"
PREFIJO_ETIQUETA = "odd-ws--v"
PLUGIN_JSON = "plugin/.claude-plugin/plugin.json"
WORKFLOW = ".github/workflows/release.yml"
SHA = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
USO = "uso: entrega.py   (lee de stdin las líneas del pre-push)"
README = "README.md"
DOCS_CON_COMANDOS = ("Doc/uso.md", "Doc/actualizar.md")
PAGINA = "index.html"
RAMAS_DE_LA_PAGINA = (("refs/heads/gh-pages", "gh-pages"), ("refs/remotes/origin/gh-pages", "origin/gh-pages"))
SIN_PAGINA = (
    "aviso: no hay rama gh-pages, ni local ni en origin, así que no se revisa la página. "
    "Si entregas una versión, commitea su página en gh-pages antes de empujar main"
)
SECCION_DEL_README = "Instalación"
SECCION_DE_LA_PAGINA = "Instalar"
COMANDO = re.compile(r"odd-ws--v(<[^<>\n]*>|[^\s<>\"'`()\[\]{}|*,;]*)")
VERSION_ACTUAL = re.compile(r"Versión actual:\s*(\S*)")
NUMERO_DE_VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]*[0-9A-Za-z])?")
ENLACE_MD = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
NEGRITA_MD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
SEPARADOR_MD = re.compile(r":?-+:?")
ETIQUETA_HTML = re.compile(r"<[^>]*>")
H2_HTML = re.compile(r"<h2\b([^>]*)>(.*?)</h2>", re.S | re.I)
ID_INSTALAR = re.compile(r"\bid=[\"']instalar[\"']", re.I)
TABLA_HTML = re.compile(r"<table\b.*?</table>", re.S | re.I)
FILA_HTML = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
CELDA_HTML = re.compile(r"<t([hd])\b[^>]*>(.*?)</t\1>", re.S | re.I)
PIE_HTML = re.compile(r"<footer\b.*?</footer>", re.S | re.I)


class NoSePuedeVerificar(Exception):
    pass


def git(raiz, *args):
    return subprocess.run(["git", "-C", raiz, *args], capture_output=True)


def error_de(resultado):
    return resultado.stderr.decode("utf-8", "replace").strip() or f"salió con {resultado.returncode}"


def raiz_del_repo():
    resultado = subprocess.run(["git", "-C", os.getcwd(), "rev-parse", "--show-toplevel"], capture_output=True)
    if resultado.returncode != 0:
        raise NoSePuedeVerificar("este chequeo necesita correr dentro de un repositorio git: " + error_de(resultado))
    return resultado.stdout.decode("utf-8").strip()


def ultima_etiqueta(raiz, sha):
    resultado = git(raiz, "describe", "--tags", "--match", PATRON_ETIQUETA, "--abbrev=0", sha)
    if resultado.returncode == 0:
        return resultado.stdout.decode("utf-8").strip()
    alcanzables = git(raiz, "tag", "--merged", sha, "--list", PATRON_ETIQUETA)
    if alcanzables.returncode == 0 and not alcanzables.stdout.strip():
        return None
    raise NoSePuedeVerificar(f"git no pudo buscar la última etiqueta {PATRON_ETIQUETA} desde {sha[:7]}: " + error_de(resultado))


def plugin_cambio(raiz, etiqueta, sha):
    resultado = git(raiz, "diff", "--quiet", f"refs/tags/{etiqueta}", sha, "--", "plugin/")
    if resultado.returncode in (0, 1):
        return resultado.returncode == 1
    raise NoSePuedeVerificar(f"git no pudo comparar plugin/ entre {etiqueta} y {sha[:7]}: " + error_de(resultado))


def leer(raiz, sha, ruta):
    resultado = git(raiz, "show", f"{sha}:{ruta}")
    if resultado.returncode != 0:
        raise NoSePuedeVerificar(f"git no pudo leer {ruta} en {sha[:7]}: " + error_de(resultado))
    return resultado.stdout


def version_del_plugin(raiz, sha):
    contenido = leer(raiz, sha, PLUGIN_JSON)
    try:
        datos = json.loads(contenido.decode("utf-8-sig"))
    except ValueError as error:
        raise NoSePuedeVerificar(f"{PLUGIN_JSON} en {sha[:7]} no es un JSON legible: {error}")
    version = datos.get("version") if isinstance(datos, dict) else None
    if not isinstance(version, str) or not VERSION.match(version):
        raise NoSePuedeVerificar(f"{PLUGIN_JSON} en {sha[:7]} no tiene un «version» válido (X.Y.Z): {version!r}")
    return version


def commit_de(raiz, ref, nombre):
    resultado = git(raiz, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
    if resultado.returncode == 0:
        return resultado.stdout.decode("utf-8").strip()
    if resultado.returncode == 1 and not resultado.stderr.strip():
        return None
    raise NoSePuedeVerificar(f"git no pudo resolver {nombre}: " + error_de(resultado))


def commit_de_la_etiqueta(raiz, etiqueta):
    return commit_de(raiz, f"refs/tags/{etiqueta}", f"la etiqueta {etiqueta}")


def no_es_entrega(cual, commit, version):
    return (
        f"{cual} no es una entrega: el plugin.json de su commit {commit[:7]} dice {version} "
        f"y su nombre debería ser {PREFIJO_ETIQUETA}{version}. "
        f"Subí «version» en {PLUGIN_JSON} y etiquetá con «claude plugin tag ./plugin», que crea el nombre que corresponde"
    )


def etiqueta_ajena_a_su_version(raiz, etiqueta):
    commit = commit_de_la_etiqueta(raiz, etiqueta)
    if commit is None:
        raise NoSePuedeVerificar(f"git no pudo resolver la etiqueta {etiqueta}")
    version = version_del_plugin(raiz, commit)
    if etiqueta == PREFIJO_ETIQUETA + version:
        return None
    return no_es_entrega(f"la última etiqueta, {etiqueta},", commit, version)


def commit_del_objeto(raiz, objeto):
    resultado = git(raiz, "rev-parse", "--verify", "-q", f"{objeto}^{{commit}}")
    if resultado.returncode != 0:
        raise NoSePuedeVerificar(f"git no pudo resolver el commit de {objeto[:7]}: " + error_de(resultado))
    return resultado.stdout.decode("utf-8").strip()


def existe_en(raiz, sha, ruta):
    listado = git(raiz, "ls-tree", "--name-only", sha, "--", ruta)
    if listado.returncode != 0:
        raise NoSePuedeVerificar(f"git no pudo listar {ruta} en {sha[:7]}: " + error_de(listado))
    return bool(listado.stdout.strip())


def texto_en(raiz, sha, ruta):
    if not existe_en(raiz, sha, ruta):
        return ""
    return leer(raiz, sha, ruta).decode("utf-8-sig", "replace")


def faltan_las_notas(raiz, sha, version):
    if not existe_en(raiz, sha, WORKFLOW):
        return None
    texto = texto_en(raiz, sha, notas.CHANGELOG)
    if notas.seccion(texto, version) is not None:
        return None
    return (
        f"el push entrega {PREFIJO_ETIQUETA}{version}, pero {notas.CHANGELOG} en {sha[:7]} no tiene notas para {version}. "
        f"Escribí la sección «## {version}» en {notas.CHANGELOG}: es el cuerpo del release que publica {WORKFLOW}"
    )


def revisar_etiqueta_empujada(raiz, etiqueta, commit):
    version = version_del_plugin(raiz, commit)
    if etiqueta != PREFIJO_ETIQUETA + version:
        return no_es_entrega(f"la etiqueta {etiqueta}", commit, version)
    return faltan_las_notas(raiz, commit, version)


def revisar_push_a_main(raiz, sha):
    ultima = ultima_etiqueta(raiz, sha)
    if ultima is not None:
        ajena = etiqueta_ajena_a_su_version(raiz, ultima)
        if ajena:
            return ajena
        if not plugin_cambio(raiz, ultima, sha):
            if commit_de_la_etiqueta(raiz, ultima) == sha:
                return faltan_las_notas(raiz, sha, version_del_plugin(raiz, sha))
            return None
    version = version_del_plugin(raiz, sha)
    etiqueta = PREFIJO_ETIQUETA + version
    apunta_a = commit_de_la_etiqueta(raiz, etiqueta)
    if apunta_a == sha:
        return faltan_las_notas(raiz, sha, version)
    desde = ultima if ultima is not None else "el inicio"
    if etiqueta == ultima:
        faltante = f"{sha[:7]} no tiene la etiqueta {etiqueta}: la versión sigue en {version}, la de la última etiqueta"
    elif apunta_a is None:
        faltante = f"{sha[:7]} no tiene la etiqueta {etiqueta}"
    else:
        faltante = f"la etiqueta {etiqueta} apunta a {apunta_a[:7]} y no a {sha[:7]}"
    return (
        f"el push a main cambia plugin/ desde {desde} y {faltante}. "
        f"Subí «version» en {PLUGIN_JSON}, etiquetá con «claude plugin tag ./plugin» y empujá la etiqueta junto con la rama"
    )


def la_pagina(raiz):
    for ref, nombre in RAMAS_DE_LA_PAGINA:
        commit = commit_de(raiz, ref, f"la rama {nombre}")
        if commit is not None:
            resultado = git(raiz, "show", f"{commit}:{PAGINA}")
            if resultado.returncode != 0:
                raise NoSePuedeVerificar(f"git no pudo leer {PAGINA} de la rama {nombre}: " + error_de(resultado))
            return nombre, resultado.stdout.decode("utf-8-sig", "replace")
    return None


def plano_md(texto):
    texto = ENLACE_MD.sub(r"\1", texto)
    texto = NEGRITA_MD.sub(lambda negrita: negrita.group(1) if negrita.group(1) is not None else negrita.group(2), texto)
    return " ".join(texto.replace("`", "").split())


def plano_html(texto):
    return " ".join(html.unescape(ETIQUETA_HTML.sub("", texto)).split())


def version_actual_desfasada(texto, plano, donde, version, arreglo):
    halladas = [
        (numero, encontrada.group(1).rstrip(".,;:"))
        for numero, renglon in enumerate(texto.splitlines(), 1)
        for encontrada in VERSION_ACTUAL.finditer(plano(renglon))
    ]
    if not halladas:
        return [f"{donde} no tiene la línea «Versión actual»: escríbela con {version}"]
    return [f"{donde}:{numero} dice «Versión actual: {dicha}»: {arreglo}" for numero, dicha in halladas if dicha != version]


def pie_desfasado(texto, donde, version):
    pie = PIE_HTML.search(texto)
    if pie is None:
        return []
    primera = texto.count("\n", 0, pie.start()) + 1
    return [
        f"{donde}:{primera + desplazamiento} dice {numero} en el pie: sube la versión del pie a {version}"
        for desplazamiento, renglon in enumerate(pie.group(0).splitlines())
        for numero in NUMERO_DE_VERSION.findall(plano_html(renglon))
        if numero != version
    ]


def comandos_desfasados(texto, donde, version, preparar=str):
    problemas = []
    for numero, renglon in enumerate(texto.splitlines(), 1):
        for encontrado in COMANDO.finditer(preparar(renglon)):
            dicho = encontrado.group(1)
            if not dicho.startswith("<"):
                dicho = dicho.rstrip(".:")
            if dicho != version:
                problemas.append(f"{donde}:{numero} tiene {PREFIJO_ETIQUETA}{dicho}: cámbialo por {PREFIJO_ETIQUETA}{version}")
    return problemas


def tabla_del_readme(texto):
    filas, dentro, en_bloque = [], False, False
    for numero, renglon in enumerate(texto.splitlines(), 1):
        if renglon.lstrip().startswith(("```", "~~~")):
            en_bloque = not en_bloque
        elif en_bloque:
            continue
        elif renglon.startswith("## "):
            if dentro:
                break
            dentro = SECCION_DEL_README.lower() in renglon.lower()
        elif dentro and renglon.lstrip().startswith("|"):
            celdas = [plano_md(celda) for celda in renglon.strip().strip("|").split("|")]
            if not all(SEPARADOR_MD.fullmatch(celda) for celda in celdas):
                filas.append((numero, celdas))
        elif filas:
            break
    return filas


def tabla_de_la_pagina(texto):
    titulos = list(H2_HTML.finditer(texto))
    indice = next(
        (i for i, titulo in enumerate(titulos) if ID_INSTALAR.search(titulo.group(1)) or "instal" in plano_html(titulo.group(2)).lower()),
        None,
    )
    if indice is None:
        return []
    fin = titulos[indice + 1].start() if indice + 1 < len(titulos) else len(texto)
    tabla = TABLA_HTML.search(texto, titulos[indice].end(), fin)
    if tabla is None:
        return []
    return [
        (texto.count("\n", 0, fila.start()) + 1, [plano_html(celda.group(2)) for celda in CELDA_HTML.finditer(fila.group(1))])
        for fila in FILA_HTML.finditer(texto, tabla.start(), tabla.end())
    ]


def requisitos_distintos(readme, pagina, donde):
    del_readme, de_la_pagina = tabla_del_readme(readme), tabla_de_la_pagina(pagina)
    if not del_readme:
        return [f"{README} no tiene la tabla de requisitos en su sección «{SECCION_DEL_README}»: ponla, igual a la de la página"]
    if not de_la_pagina:
        return [f"{donde} no tiene la tabla de requisitos en su sección «{SECCION_DE_LA_PAGINA}»: ponla, igual a la del README"]
    columnas = del_readme[0][1]
    problemas = []
    for indice in range(max(len(del_readme), len(de_la_pagina))):
        fila = "el encabezado de la tabla de requisitos" if indice == 0 else f"la fila {indice} de la tabla de requisitos"
        if indice >= len(de_la_pagina):
            numero, celdas = del_readme[indice]
            problemas.append(f"{fila} («{celdas[0] if celdas else ''}», {README}:{numero}) no está en la página: súmala a la página o sácala del README")
            continue
        if indice >= len(del_readme):
            numero, celdas = de_la_pagina[indice]
            problemas.append(f"{fila} («{celdas[0] if celdas else ''}», {donde}:{numero}) no está en el README: súmala al README o sácala de la página")
            continue
        (en_readme, de_readme), (en_pagina, de_pagina) = del_readme[indice], de_la_pagina[indice]
        for columna in range(max(len(de_readme), len(de_pagina))):
            dice_readme = de_readme[columna] if columna < len(de_readme) else ""
            dice_pagina = de_pagina[columna] if columna < len(de_pagina) else ""
            if dice_readme != dice_pagina:
                nombre = columnas[columna] if columna < len(columnas) else str(columna + 1)
                problemas.append(
                    f"{fila} («{de_readme[0] if de_readme else ''}»), columna «{nombre}», dice «{dice_readme}» en {README}:{en_readme} "
                    f"y «{dice_pagina}» en {donde}:{en_pagina}: iguala esa celda en los dos"
                )
    return problemas


def desfases_de_la_entrega(raiz, sha, pagina):
    version = version_del_plugin(raiz, sha)
    readme = texto_en(raiz, sha, README)
    problemas = version_actual_desfasada(readme, plano_md, README, version, f"sube la «Versión actual» del README a {version}")
    problemas += comandos_desfasados(readme, README, version)
    for ruta in DOCS_CON_COMANDOS:
        problemas += comandos_desfasados(texto_en(raiz, sha, ruta), ruta, version)
    de_la_pagina = []
    if pagina is not None:
        nombre, texto = pagina
        donde = f"{nombre}:{PAGINA}"
        de_la_pagina = version_actual_desfasada(texto, plano_html, donde, version, f"sube la versión de la página a {version}")
        de_la_pagina += pie_desfasado(texto, donde, version)
        de_la_pagina += comandos_desfasados(texto, donde, version, html.unescape)
        de_la_pagina += requisitos_distintos(readme, texto, donde)
    if not problemas and not de_la_pagina:
        return None
    lineas = [f"la página y el README no coinciden con {PLUGIN_JSON} de {sha[:7]}, que dice {version}:"]
    lineas += [f"  - {problema}" for problema in problemas + de_la_pagina]
    if de_la_pagina:
        lineas.append(f"La página se lee de {nombre}: commitea la página de la versión en la rama gh-pages antes de empujar main")
    return "\n".join(lineas)


def revisar(entrada):
    raiz = None
    revisadas = 0
    commits = []
    for linea in entrada.splitlines():
        if not linea.strip():
            continue
        partes = linea.split()
        if len(partes) != 4 or not SHA.match(partes[1]) or not SHA.match(partes[3]):
            raise NoSePuedeVerificar(f"línea ilegible en la entrada del pre-push: {linea!r}")
        es_etiqueta = fnmatch.fnmatchcase(partes[2], REF_ETIQUETAS + PATRON_ETIQUETA)
        if partes[2] != REF_MAIN and not es_etiqueta or partes[1] == CEROS:
            continue
        if raiz is None:
            raiz = raiz_del_repo()
        if es_etiqueta:
            commit = commit_del_objeto(raiz, partes[1])
            if not existe_en(raiz, commit, WORKFLOW):
                continue
            revisadas += 1
            problema = revisar_etiqueta_empujada(raiz, partes[2][len(REF_ETIQUETAS):], commit)
        else:
            commit = partes[1]
            revisadas += 1
            problema = revisar_push_a_main(raiz, commit)
        if problema:
            return revisadas, problema, []
        commits.append(commit)
    if not commits:
        return revisadas, None, []
    pagina = la_pagina(raiz)
    avisos = [SIN_PAGINA] if pagina is None else []
    for commit in dict.fromkeys(commits):
        problema = desfases_de_la_entrega(raiz, commit, pagina)
        if problema:
            return revisadas, problema, avisos
    return revisadas, None, avisos


def main(argv):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if argv:
        print(USO, file=sys.stderr)
        return 2
    try:
        revisadas, problema, avisos = revisar(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except NoSePuedeVerificar as error:
        print(f"ENTREGA BLOQUEADA: {error}. Sin verificar la entrega no se empuja a main.", file=sys.stderr)
        return 2
    for aviso in avisos:
        print(f"{aviso}.", file=sys.stderr)
    if problema:
        print(f"ENTREGA BLOQUEADA: {problema}.", file=sys.stderr)
        return 1
    if revisadas:
        print("entrega limpia")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
