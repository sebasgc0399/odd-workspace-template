import re
import sys

CHANGELOG = "CHANGELOG.md"
USO = "uso: notas.py <versión>   (imprime la sección «## <versión>» de CHANGELOG.md)"


def seccion(texto, version):
    encabezado = re.compile("## " + re.escape(version) + r"(\s.*)?")
    cuerpo, dentro = [], False
    for linea in texto.splitlines():
        if linea.startswith("## "):
            if dentro:
                break
            dentro = encabezado.fullmatch(linea.rstrip()) is not None
            continue
        if dentro:
            cuerpo.append(linea)
    while cuerpo and not cuerpo[0].strip():
        cuerpo.pop(0)
    while cuerpo and not cuerpo[-1].strip():
        cuerpo.pop()
    return "\n".join(cuerpo) + "\n" if cuerpo else None


def main(argv):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) != 1:
        print(USO, file=sys.stderr)
        return 2
    try:
        with open(CHANGELOG, encoding="utf-8-sig") as archivo:
            texto = archivo.read()
    except OSError as error:
        print(f"no se pudo leer {CHANGELOG}: {error}", file=sys.stderr)
        return 2
    notas = seccion(texto, argv[0])
    if notas is None:
        print(f"{CHANGELOG} no tiene notas para {argv[0]}: falta la sección «## {argv[0]}» o está vacía", file=sys.stderr)
        return 1
    sys.stdout.write(notas)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
