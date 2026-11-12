import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_RUTA = AQUI / "memorias.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []


def _cargar():
    spec = importlib.util.spec_from_file_location("memorias", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None

ENC = ["id", "origen", "tipo", "destino", "severidad", "numeros", "resumen", "motivo"]
MATRIZ = ".claude/reglas/matriz.csv"
CAPAS = {"sql": {"extensions": [".sql"], "rule_prefix": "SQL"}, "docs": {"extensions": [".md"]}}
CASA_IMPOSIBLE = str(Path(__file__).resolve() / "casa")
FECHA_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SKILL_CERRAR = AQUI.parent / "skills" / "cerrar" / "SKILL.md"
MARCADOR_RE = re.compile(r"<[^<>\s]+>")
SUSTITUTOS = {"<dir>": "/home/u/memoria", "<slug>": "a"}
OPCION_RE = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
CODIGO_RE = re.compile(r"`([^`\n]+)`")
RUTA_JSON_RE = re.compile(r"([a-z_]+)\.([a-z_]+)")
EXTENSIONES = ("py", "md", "json", "csv")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    base = Path(os.path.realpath(tempfile.mkdtemp(prefix="memorias-test-")))
    try:
        yield base
    finally:
        shutil.rmtree(base, onexc=_quitar)
        if base.exists():
            SOBRANTES.append(str(base))


def escribir(ruta, contenido):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido.encode("utf-8") if isinstance(contenido, str) else contenido)
    return ruta


def fila(id_, origen):
    return [id_, origen, "CE", "descarte", "", "", "regla", "porque"]


def matriz_csv(filas, encabezado=ENC):
    buf = io.StringIO()
    escritor = csv.writer(buf, lineterminator="\n")
    escritor.writerow(encabezado)
    for registro in filas:
        escritor.writerow(registro)
    return buf.getvalue()


def instancia(base, filas=(), nombre="instancia"):
    raiz = Path(base) / nombre
    escribir(raiz / "workspace.config.json", json.dumps({"schema_version": 1, "repos": {}, "layers": CAPAS}))
    escribir(raiz / MATRIZ, matriz_csv(filas))
    return raiz


def memoria(tipo="feedback", nombre="Una regla", descripcion="Lo que se aprendió", anidado=True, modificada="2026-11-01T10:00:00Z"):
    lineas = ["---", "name: %s" % nombre, 'description: "%s"' % descripcion]
    if anidado:
        lineas += ["metadata:", "  type: %s" % tipo, "  modified: %s" % modificada]
    else:
        lineas += ["type: %s" % tipo, "modified: %s" % modificada]
    return "\n".join(lineas + ["---", "", "Cuerpo de la memoria.", ""])


def memorias(base, archivos, indice=None, nombre="memoria"):
    carpeta = Path(base) / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    for archivo, contenido in archivos.items():
        escribir(carpeta / archivo, contenido)
    if indice is None:
        indice = "\n".join("- [%s](%s) — algo" % (archivo[:-3], archivo) for archivo in sorted(archivos)) + "\n"
    if indice is not False:
        escribir(carpeta / "MEMORY.md", indice)
    return carpeta


def correr(*argv, entorno=None):
    entorno = dict({} if entorno is None else entorno)
    for clave in ("HOME", "USERPROFILE"):
        entorno.setdefault(clave, CASA_IMPOSIBLE)
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = M.main(list(argv), entorno=entorno)
    return codigo, salida.getvalue(), error.getvalue()


def con_registro(raiz, carpeta, registro, *argv):
    return correr("--raiz", str(raiz), "--memorias", str(carpeta), "--registro", str(registro), *argv)


def registrar(raiz, carpeta, registro, como, *slugs):
    return con_registro(raiz, carpeta, registro, "--registrar", *slugs, "--como", como)


def estados(raiz, carpeta, registro, *argv):
    codigo, salida, error = con_registro(raiz, carpeta, registro, "--json", *argv)
    assert codigo == 0, (codigo, salida, error)
    return {dato["slug"]: dato["estado"] for dato in json.loads(salida)["memorias"]}


def primeras_columnas(salida, desde, hasta):
    return [linea.split()[0] for linea in lineas(salida)[desde:hasta]]


def json_de(*argv, entorno=None):
    codigo, salida, error = correr(*argv, "--json", entorno=entorno)
    assert codigo == 0, (codigo, salida, error)
    return json.loads(salida)


def por_slug(datos):
    return {registro["slug"]: registro for registro in datos["memorias"]}


def lineas(texto):
    return [linea for linea in texto.splitlines() if linea.strip()]


def huella(*carpetas):
    hash_ = hashlib.sha256()
    for carpeta in carpetas:
        for actual, subcarpetas, archivos in os.walk(carpeta):
            subcarpetas.sort()
            for nombre in sorted(archivos) + ["<carpetas>"] + subcarpetas:
                hash_.update(os.path.relpath(os.path.join(actual, nombre), carpeta).encode("utf-8"))
            for nombre in sorted(archivos):
                hash_.update(Path(actual, nombre).read_bytes())
    return hash_.hexdigest()


def test_un_directorio_inexistente_sale_con_2_y_nombra_la_ruta_y_existente_da_su_cobertura():
    with temporal() as base:
        raiz = instancia(base)
        falta = base / "no-existe"
        codigo, salida, error = correr("--raiz", str(raiz), "--memorias", str(falta))
        assert codigo == 2 and str(falta) in error and salida == "", (codigo, salida, error)
        assert "candidat" not in error.lower() and "COBERTURA" not in error, "nunca dice 0 candidatos: %s" % error
        archivo = escribir(base / "un-archivo", "x")
        codigo, _, error = correr("--raiz", str(raiz), "--memorias", str(archivo))
        assert codigo == 2 and str(archivo) in error, (codigo, error)
        carpeta = memorias(base, {"a.md": memoria()}, nombre="no-existe")
        codigo, salida, error = correr("--raiz", str(raiz), "--memorias", str(carpeta))
        assert codigo == 0 and error == "", (codigo, error)
        assert lineas(salida)[-1] == "COBERTURA claude-code: completa (1, %s, pasada)" % carpeta, salida


def test_la_cobertura_dice_derivada_cuando_el_directorio_sale_de_claude_config_dir():
    with temporal() as base:
        raiz = instancia(base)
        (raiz / ".git").mkdir()
        config = base / "config"
        nombre = "".join(c if c.isascii() and c.isalnum() else "-" for c in str(raiz))
        carpeta = memorias(config / "projects" / nombre, {"a.md": memoria(), "b.md": memoria()}, nombre="memory")
        codigo, salida, error = correr("--raiz", str(raiz), entorno={"CLAUDE_CONFIG_DIR": str(config)})
        assert codigo == 0, (codigo, salida, error)
        assert lineas(salida)[-1] == "COBERTURA claude-code: completa (2, %s, derivada)" % carpeta, salida
        codigo, _, error = correr("--raiz", str(raiz), entorno={"CLAUDE_CONFIG_DIR": str(base / "otra-config")})
        assert codigo == 2 and str(base / "otra-config") in error and "--memorias" in error, (codigo, error)


def test_sin_instancia_sale_con_2():
    with temporal() as base:
        carpeta = memorias(base, {"a.md": memoria()})
        codigo, _, error = correr("--raiz", str(base), "--memorias", str(carpeta))
        assert codigo == 2 and "workspace.config.json" in error, (codigo, error)


def test_el_frontmatter_en_la_raiz_o_bajo_metadata_con_crlf_y_con_bom():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {
            "anidada.md": memoria(nombre="Anidada", descripcion="Con: dos puntos y \\\"comillas\\\""),
            "en-la-raiz.md": memoria(nombre="En la raíz", anidado=False, modificada="2026-10-01"),
            "crlf.md": memoria(nombre="Crlf").replace("\n", "\r\n"),
            "bom.md": b"\xef\xbb\xbf" + memoria(nombre="Bom").encode("utf-8"),
            "simple.md": "---\nname: 'Con '' simple'\ndescription: sin comillas # y un comentario\ntype: feedback\n---\n",
        })
        datos = por_slug(json_de("--raiz", str(raiz), "--memorias", str(carpeta)))
        assert set(datos) == {"anidada", "en-la-raiz", "crlf", "bom", "simple"}, datos
        assert datos["anidada"]["descripcion"] == 'Con: dos puntos y "comillas"', datos["anidada"]
        assert (datos["en-la-raiz"]["nombre"], datos["en-la-raiz"]["modificada"]) == ("En la raíz", "2026-10-01"), datos["en-la-raiz"]
        assert datos["simple"]["nombre"] == "Con ' simple" and datos["simple"]["descripcion"] == "sin comillas", datos["simple"]
        assert datos["simple"]["modificada"] is None, datos["simple"]
        for slug in datos:
            assert datos[slug]["estado"] == "nueva" and datos[slug]["tipo"] == "feedback" and datos[slug]["motivo"] is None, datos[slug]
        assert datos["crlf"]["nombre"] == "Crlf" and datos["bom"]["nombre"] == "Bom"


def test_un_frontmatter_ausente_o_roto_es_ilegible_sin_romper_el_script():
    with temporal() as base:
        raiz = instancia(base)
        rotos = {
            "sin-frontmatter.md": "Solo texto, sin frontmatter.\n",
            "sin-cierre.md": "---\nname: x\ndescription: y\ntype: feedback\n",
            "linea-rara.md": "---\nname: x\nesto no es clave\ndescription: y\ntype: feedback\n---\n",
            "comillas.md": '---\nname: "sin cerrar\ndescription: y\ntype: feedback\n---\n',
            "sin-tipo.md": "---\nname: x\ndescription: y\n---\n",
            "sangria-suelta.md": "---\nname: x\n  type: feedback\ndescription: y\n---\n",
            "no-utf8.md": b"---\nname: \xff\xfe\ndescription: y\ntype: feedback\n---\n",
            "vacio.md": "",
        }
        carpeta = memorias(base, dict(rotos, **{"buena.md": memoria()}))
        codigo, salida, error = correr("--raiz", str(raiz), "--memorias", str(carpeta), "--json")
        assert codigo == 0 and "Traceback" not in error, (codigo, error)
        datos = por_slug(json.loads(salida))
        for archivo in rotos:
            registro = datos[archivo[:-3]]
            assert registro["estado"] == "ilegible" and registro["tipo"] is None and registro["motivo"], registro
        assert datos["buena"]["estado"] == "nueva", datos["buena"]
        assert "sin-cierre" in correr("--raiz", str(raiz), "--memorias", str(carpeta))[1]
        escribir(carpeta / "sin-nombre.md", "---\ndescription: y\ntype: feedback\n---\n")
        escribir(carpeta / "user-incompleta.md", "---\nname: x\ntype: user\n---\n")
        datos = json_de("--raiz", str(raiz), "--memorias", str(carpeta))
        registro = por_slug(datos)["sin-nombre"]
        assert (registro["estado"], registro["tipo"], registro["motivo"]) == ("ilegible", "feedback", "al frontmatter le falta name"), registro
        assert "user-incompleta" not in por_slug(datos) and datos["excluidas"]["user"] == 1, "con el tipo leído, user nunca entra"


def test_graduada_si_el_slug_esta_en_un_origen_simple_o_de_varias_piezas():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:simple"),
                                fila("SQL-02", "docs/a.md@abc1234:1-2;memoria:en-piezas"),
                                fila("SQL-03", "memoria:simple;memoria:otra-cosa")])
        carpeta = memorias(base, {"simple.md": memoria(), "en-piezas.md": memoria(), "nueva.md": memoria(),
                                  "en-piezas-no.md": memoria()})
        datos = por_slug(json_de("--raiz", str(raiz), "--memorias", str(carpeta)))
        assert (datos["simple"]["estado"], datos["simple"]["filas"]) == ("graduada", ["SQL-01", "SQL-03"]), datos["simple"]
        assert (datos["en-piezas"]["estado"], datos["en-piezas"]["filas"]) == ("graduada", ["SQL-02"]), datos["en-piezas"]
        for slug in ("nueva", "en-piezas-no"):
            assert (datos[slug]["estado"], datos[slug]["filas"]) == ("nueva", []), datos[slug]
        salida = correr("--raiz", str(raiz), "--memorias", str(carpeta))[1]
        assert any(linea.startswith("graduada") and "simple" in linea and "SQL-01, SQL-03" in linea for linea in lineas(salida)), salida


def test_la_matriz_ilegible_sale_con_2_y_la_legible_no():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria()})
        assert correr("--raiz", str(raiz), "--memorias", str(carpeta))[0] == 0
        for contenido in (b"id,origen\xff\n", matriz_csv([], encabezado=ENC[:-1]).encode("utf-8"), b""):
            escribir(raiz / MATRIZ, contenido)
            codigo, salida, error = correr("--raiz", str(raiz), "--memorias", str(carpeta))
            assert codigo == 2 and "matriz" in error and str(raiz / MATRIZ) in error and salida == "", (contenido, codigo, error)
        (raiz / MATRIZ).unlink()
        codigo, _, error = correr("--raiz", str(raiz), "--memorias", str(carpeta))
        assert codigo == 2 and str(raiz / MATRIZ) in error, (codigo, error)


def test_una_fila_rota_de_la_matriz_es_aviso_y_no_cuenta_para_graduada():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:ok"), fila("ROTA", "memoria:rota")])
        carpeta = memorias(base, {"ok.md": memoria(), "rota.md": memoria()})
        datos = json_de("--raiz", str(raiz), "--memorias", str(carpeta))
        assert por_slug(datos)["ok"]["estado"] == "graduada" and por_slug(datos)["rota"]["estado"] == "nueva", datos
        assert any(aviso.startswith("matriz fila 3:") for aviso in datos["avisos"]), datos["avisos"]


def test_por_defecto_solo_feedback_project_con_opcion_y_user_y_reference_nunca():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"f.md": memoria("feedback"), "p.md": memoria("project"), "u.md": memoria("user"),
                                  "u2.md": memoria("user"), "r.md": memoria("reference"), "o.md": memoria("otra-cosa")})
        datos = json_de("--raiz", str(raiz), "--memorias", str(carpeta))
        assert set(por_slug(datos)) == {"f"} and datos["tipos"] == ["feedback"], datos
        assert datos["excluidas"] == {"project": 1, "user": 2, "reference": 1, "otros": 1}, datos["excluidas"]
        assert datos["cobertura"]["total"] == 6, datos["cobertura"]
        con_project = json_de("--raiz", str(raiz), "--memorias", str(carpeta), "--con-project")
        assert set(por_slug(con_project)) == {"f", "p"} and con_project["tipos"] == ["feedback", "project"], con_project
        assert con_project["excluidas"] == {"project": 0, "user": 2, "reference": 1, "otros": 1}, con_project["excluidas"]
        salida = correr("--raiz", str(raiz), "--memorias", str(carpeta))[1]
        assert "EXCLUIDAS project=1 user=2 reference=1 otros=1" in lineas(salida), salida


def test_huerfanas_y_links_rotos_del_indice_son_avisos():
    with temporal() as base:
        raiz = instancia(base)
        indice = "- [A](a.md)\n- [Rota](no-esta.md#ancla)\n- [Web](https://example.invalid/x.md)\n- [B](./b.md)\n"
        carpeta = memorias(base, {"a.md": memoria(), "b.md": memoria(), "huerfana.md": memoria()}, indice=indice)
        codigo, salida, error = correr("--raiz", str(raiz), "--memorias", str(carpeta))
        assert codigo == 0, (codigo, error)
        avisos = [linea for linea in lineas(salida) if linea.startswith("AVISO")]
        assert avisos == ["AVISO huérfana: huerfana.md no figura en MEMORY.md",
                          "AVISO link roto: MEMORY.md enlaza no-esta.md, que no existe"], avisos
        escribir(carpeta / "privada.md", memoria("user"))
        datos = json_de("--raiz", str(raiz), "--memorias", str(carpeta))
        assert not any("privada" in aviso for aviso in datos["avisos"]), datos["avisos"]
        assert "huérfanas entre las excluidas por tipo: 1, sin nombrarlas" in datos["avisos"], datos["avisos"]
        sin_indice = memorias(base, {"a.md": memoria()}, indice=False, nombre="sin-indice")
        datos = json_de("--raiz", str(raiz), "--memorias", str(sin_indice))
        assert datos["avisos"] == ["falta MEMORY.md en %s: no se revisan huérfanas ni links" % sin_indice], datos["avisos"]


def test_el_json_es_estable():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:b")])
        carpeta = memorias(base, {"c.md": memoria(), "b.md": memoria(), "a.md": "roto"})
        datos = json_de("--raiz", str(raiz), "--memorias", str(carpeta))
        assert list(datos) == ["host", "cobertura", "tipos", "memorias", "excluidas", "avisos"], list(datos)
        assert datos["cobertura"] == {"estado": "completa", "total": 3, "directorio": str(carpeta), "origen": "pasada",
                                      "fuente": "--memorias", "detalle": None}, datos["cobertura"]
        assert [registro["slug"] for registro in datos["memorias"]] == ["a", "b", "c"], datos["memorias"]
        claves = ["slug", "archivo", "nombre", "descripcion", "tipo", "modificada", "estado", "motivo", "filas"]
        assert all(list(registro) == claves for registro in datos["memorias"]), datos["memorias"]
        assert por_slug(datos)["c"] == {"slug": "c", "archivo": "c.md", "nombre": "Una regla", "descripcion": "Lo que se aprendió",
                                       "tipo": "feedback", "modificada": "2026-11-01T10:00:00Z", "estado": "nueva", "motivo": None,
                                       "filas": []}, por_slug(datos)["c"]
        assert json_de("--raiz", str(raiz), "--memorias", str(carpeta)) == datos


def test_no_cambia_ni_la_memoria_ni_la_instancia():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:a")])
        (raiz / ".git").mkdir()
        carpeta = memorias(base, {"a.md": memoria(), "b.md": "roto"}, indice="- [Rota](x.md)\n")
        antes = huella(carpeta, raiz)
        assert correr("--raiz", str(raiz), "--memorias", str(carpeta))[0] == 0
        assert correr("--raiz", str(raiz), "--memorias", str(carpeta), "--json", "--con-project")[0] == 0
        assert huella(carpeta, raiz) == antes


def test_en_codex_la_memoria_de_claude_code_no_esta_disponible():
    with temporal() as base:
        raiz = instancia(base)
        codigo, salida, error = correr("--raiz", str(raiz), "--host", "codex")
        assert codigo == 0 and error == "", (codigo, error)
        assert lineas(salida)[0].startswith("COBERTURA codex: no disponible (") and len(lineas(salida)) == 1, salida
        datos = json_de("--raiz", str(raiz), "--host", "codex")
        assert datos["cobertura"]["estado"] == "no disponible" and datos["memorias"] is None and datos["excluidas"] is None, datos
        carpeta = memorias(base, {"a.md": memoria()})
        codigo, _, error = correr("--raiz", str(raiz), "--host", "codex", "--memorias", str(carpeta))
        assert codigo == 2 and "--host claude-code" in error, (codigo, error)


def test_la_matriz_sigue_aceptando_memoria_sin_hash_sola_y_entre_piezas():
    import matriz

    filas, errores = matriz.cargar_matriz(matriz_csv([fila("SQL-01", "memoria:sola"),
                                                      fila("SQL-02", "docs/a.md@abc1234:1-2;memoria:entre-piezas")]), {"SQL": "sql"})
    assert errores == [], errores
    assert [[(o["tipo"], o.get("slug")) for o in f["origenes"]] for f in filas] == [
        [("memoria", "sola")], [("rango", None), ("memoria", "entre-piezas")]], filas


def test_cli_utf8_en_consola_cp1252():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"acento.md": memoria(descripcion="Señal de diseño")})
        entorno = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONPATH")}
        entorno["PYTHONIOENCODING"] = "cp1252"
        entorno["HOME"] = entorno["USERPROFILE"] = str(base / "casa")
        r = subprocess.run([sys.executable, str(_RUTA), "--raiz", str(raiz), "--memorias", str(carpeta)], capture_output=True,
                           env=entorno, cwd=str(base))
        assert r.returncode == 0 and b"Traceback" not in r.stderr, r.stderr
        assert "Señal de diseño" in r.stdout.decode("utf-8"), r.stdout


def test_sin_registro_la_tabla_el_json_y_los_codigos_de_salida_siguen_como_en_t1():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:c")])
        carpeta = memorias(base, {"a.md": memoria(), "b.md": "roto", "c.md": memoria(), "u.md": memoria("user")})
        codigo, salida, error = correr("--raiz", str(raiz), "--memorias", str(carpeta))
        assert (codigo, error) == (0, ""), (codigo, error)
        assert salida == "\n".join([
            "ESTADO    TIPO      MEMORIA  DESCRIPCION",
            "nueva     feedback  a        Lo que se aprendió",
            "ilegible  -         b        no empieza con un frontmatter (---)",
            "graduada  feedback  c        Lo que se aprendió [SQL-01]",
            "EXCLUIDAS project=0 user=1 reference=0 otros=0",
            "COBERTURA claude-code: completa (4, %s, pasada)" % carpeta]) + "\n", salida
        buena = {"archivo": None, "nombre": "Una regla", "descripcion": "Lo que se aprendió", "tipo": "feedback",
                 "modificada": "2026-11-01T10:00:00Z", "estado": "nueva", "motivo": None, "filas": []}
        assert json_de("--raiz", str(raiz), "--memorias", str(carpeta)) == {
            "host": "claude-code",
            "cobertura": {"estado": "completa", "total": 4, "directorio": str(carpeta), "origen": "pasada", "fuente": "--memorias",
                          "detalle": None},
            "tipos": ["feedback"],
            "memorias": [dict(buena, slug="a", archivo="a.md"),
                         {"slug": "b", "archivo": "b.md", "nombre": None, "descripcion": None, "tipo": None, "modificada": None,
                          "estado": "ilegible", "motivo": "no empieza con un frontmatter (---)", "filas": []},
                         dict(buena, slug="c", archivo="c.md", estado="graduada", filas=["SQL-01"])],
            "excluidas": {"project": 0, "user": 1, "reference": 0, "otros": 0},
            "avisos": []}
        falta = base / "falta"
        assert correr("--raiz", str(raiz), "--memorias", str(falta)) == (
            2, "", "memorias: el directorio de memoria %s no existe (pasado por --memorias)\n" % falta)
        assert correr("--raiz", str(raiz), "--memorias", str(carpeta), "--sin-esa-opcion")[0] == 2


def test_vista_y_descartada_salen_del_registro_con_el_mismo_modified():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria(), "b.md": memoria(), "c.md": memoria()})
        registro = base / "casa" / "registro.json"
        codigo, salida, error = registrar(raiz, carpeta, registro, "vista", "a")
        assert codigo == 0 and error == "", (codigo, salida, error)
        assert registrar(raiz, carpeta, registro, "descartada", "b")[0] == 0
        assert estados(raiz, carpeta, registro) == {"a": "vista", "b": "descartada", "c": "nueva"}
        salida = con_registro(raiz, carpeta, registro)[1]
        assert primeras_columnas(salida, 1, 4) == ["nueva", "vista", "descartada"], salida
        assert lineas(salida)[-2] == "REGISTRO %s (2)" % registro, salida
        assert registrar(raiz, carpeta, registro, "vista", "b")[0] == 0
        assert estados(raiz, carpeta, registro) == {"a": "vista", "b": "vista", "c": "nueva"}


def test_cambiada_cuando_el_modified_cambio_despues_de_verla_o_descartarla():
    with temporal() as base:
        raiz = instancia(base)
        sin_fecha = "---\nname: x\ndescription: y\ntype: feedback\n---\n"
        carpeta = memorias(base, {"a.md": memoria(), "b.md": memoria(), "sin-fecha.md": sin_fecha})
        registro = base / "registro.json"
        assert registrar(raiz, carpeta, registro, "vista", "a", "sin-fecha")[0] == 0
        assert registrar(raiz, carpeta, registro, "descartada", "b")[0] == 0
        assert estados(raiz, carpeta, registro) == {"a": "vista", "b": "descartada", "sin-fecha": "vista"}
        for archivo in ("a.md", "b.md", "sin-fecha.md"):
            escribir(carpeta / archivo, memoria(modificada="2026-11-05T09:00:00Z"))
        assert estados(raiz, carpeta, registro) == {"a": "cambiada", "b": "cambiada", "sin-fecha": "cambiada"}
        assert registrar(raiz, carpeta, registro, "vista", "a")[0] == 0
        assert estados(raiz, carpeta, registro)["a"] == "vista"
        claves = list(json.loads(registro.read_bytes())["memorias"])
        assert claves == ["a@2026-11-05T09:00:00Z", "b@2026-11-01T10:00:00Z", "sin-fecha@"], claves


def test_graduada_e_ilegible_ganan_al_registro_y_la_tabla_va_en_orden():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:g")])
        incompleta = "---\nname: x\nmetadata:\n  type: feedback\n  modified: 2026-11-01\n---\n"
        carpeta = memorias(base, {"g.md": memoria(), "i.md": incompleta, "n.md": memoria(), "c.md": memoria(), "v.md": memoria(),
                                  "d.md": memoria()})
        registro = base / "registro.json"
        assert registrar(raiz, carpeta, registro, "vista", "g", "i", "c", "v")[0] == 0
        assert registrar(raiz, carpeta, registro, "descartada", "d")[0] == 0
        escribir(carpeta / "c.md", memoria(modificada="2026-11-05"))
        assert estados(raiz, carpeta, registro) == {"g": "graduada", "i": "ilegible", "n": "nueva", "c": "cambiada", "v": "vista",
                                                     "d": "descartada"}
        salida = con_registro(raiz, carpeta, registro)[1]
        assert primeras_columnas(salida, 1, 7) == ["nueva", "cambiada", "ilegible", "vista", "descartada", "graduada"], salida
        escribir(carpeta / "g.md", memoria(modificada="2026-11-05"))
        escribir(carpeta / "i.md", incompleta.replace("2026-11-01", "2026-11-05"))
        resultado = estados(raiz, carpeta, registro)
        assert (resultado["g"], resultado["i"]) == ("graduada", "ilegible"), resultado
        assert M.PRECEDENCIA == ("graduada", "ilegible", "cambiada", "descartada", "vista", "nueva"), M.PRECEDENCIA


def test_un_registro_ausente_es_vacio_todo_sale_nueva_y_no_se_crea():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria(), "b.md": memoria()})
        registro = base / "no-esta" / "registro.json"
        codigo, salida, error = con_registro(raiz, carpeta, registro)
        assert codigo == 0 and error == "", (codigo, error)
        assert salida == correr("--raiz", str(raiz), "--memorias", str(carpeta))[1], salida
        assert not any(linea.startswith("REGISTRO") for linea in lineas(salida)), salida
        assert estados(raiz, carpeta, registro) == {"a": "nueva", "b": "nueva"}
        assert not (base / "no-esta").exists()


def test_un_registro_ilegible_sale_con_2_nombra_la_ruta_y_no_se_pisa():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria()})
        registro = base / "registro.json"
        entrada = {"slug": "a", "modified": "2026-11-01T10:00:00Z", "estado": "vista", "fecha": "2026-11-12"}
        clave = "a@2026-11-01T10:00:00Z"

        def forma(entradas, **extra):
            return json.dumps(dict({"version": 1, "memorias": entradas}, **extra))

        rotos = [b"", b"{roto", b"\xff\xfe{}", b"[]", forma({}, version=2), json.dumps({"version": 1}), forma([]),
                 forma({}, otra=1), forma({clave: dict(entrada, estado="otra")}), forma({"a@otra-fecha": entrada}),
                 forma({clave: dict(entrada, descripcion="x")}), forma({clave: dict(entrada, fecha=None)}),
                 forma({clave: entrada, "a@2026-10-01": dict(entrada, modified="2026-10-01")})]
        for crudo in rotos:
            crudo = crudo if isinstance(crudo, bytes) else crudo.encode("utf-8")
            escribir(registro, crudo)
            for argv in ((), ("--json",), ("--registrar", "a", "--como", "descartada")):
                codigo, salida, error = con_registro(raiz, carpeta, registro, *argv)
                assert codigo == 2 and str(registro) in error and salida == "", (crudo, argv, codigo, salida, error)
            assert registro.read_bytes() == crudo, crudo
        escribir(registro, b"\xef\xbb\xbf" + forma({clave: entrada}).encode("utf-8"))
        assert estados(raiz, carpeta, registro) == {"a": "vista"}, "control positivo: el mismo registro, bien formado, se lee"


def test_registrar_una_memoria_que_no_existe_sale_con_2_y_no_escribe():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria(), "b.md": memoria()})
        registro = base / "casa" / "registro.json"
        codigo, salida, error = registrar(raiz, carpeta, registro, "vista", "a", "no-esta")
        assert codigo == 2 and "no-esta" in error and str(carpeta) in error and salida == "", (codigo, salida, error)
        assert not (base / "casa").exists()
        assert registrar(raiz, carpeta, registro, "vista", "b")[0] == 0
        antes = registro.read_bytes()
        for slugs in (("a", "no-esta"), ("a.md",), ("MEMORY",), ("../a",)):
            codigo, salida, error = registrar(raiz, carpeta, registro, "descartada", *slugs)
            assert codigo == 2 and salida == "", (slugs, codigo, salida, error)
        assert registro.read_bytes() == antes and estados(raiz, carpeta, registro) == {"a": "nueva", "b": "vista"}


def test_registrar_dos_veces_da_los_mismos_bytes_en_utf8_sin_bom_y_con_lf():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"b.md": memoria(), "señal.md": memoria(modificada="2026-10-02"), "a.md": memoria()})
        registro = base / "casa" / "registro.json"
        assert registrar(raiz, carpeta, registro, "vista", "señal", "b")[0] == 0
        primero = registro.read_bytes()
        assert registrar(raiz, carpeta, registro, "vista", "b", "señal", "b")[0] == 0
        assert registro.read_bytes() == primero
        assert not primero.startswith(b"\xef\xbb\xbf") and b"\r" not in primero and primero.endswith(b"}\n"), primero
        assert "señal".encode("utf-8") in primero, primero
        datos = json.loads(primero.decode("utf-8"))
        fecha = datos["memorias"]["b@2026-11-01T10:00:00Z"]["fecha"]
        assert FECHA_RE.fullmatch(fecha), fecha
        assert datos == {"version": 1, "memorias": {
            "b@2026-11-01T10:00:00Z": {"slug": "b", "modified": "2026-11-01T10:00:00Z", "estado": "vista", "fecha": fecha},
            "señal@2026-10-02": {"slug": "señal", "modified": "2026-10-02", "estado": "vista", "fecha": fecha}}}, datos
        assert list(datos) == ["version", "memorias"] and list(datos["memorias"]) == ["b@2026-11-01T10:00:00Z", "señal@2026-10-02"]
        assert all(list(entrada) == ["slug", "modified", "estado", "fecha"] for entrada in datos["memorias"].values()), datos
        assert registrar(raiz, carpeta, registro, "descartada", "a")[0] == 0
        assert list(json.loads(registro.read_bytes())["memorias"])[0] == "a@2026-11-01T10:00:00Z"
        assert os.listdir(registro.parent) == ["registro.json"], os.listdir(registro.parent)
        antes, original = registro.read_bytes(), M.date

        class OtroDia:
            @staticmethod
            def today():
                return original(2099, 1, 2)

        M.date = OtroDia
        try:
            assert registrar(raiz, carpeta, registro, "descartada", "a")[0] == 0
            assert registro.read_bytes() == antes, "otro día, lo mismo: no cambia ni la fecha"
            assert registrar(raiz, carpeta, registro, "vista", "a")[0] == 0
        finally:
            M.date = original
        assert json.loads(registro.read_bytes())["memorias"]["a@2026-11-01T10:00:00Z"]["fecha"] == "2099-01-02"


def test_la_escritura_del_registro_es_atomica():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria()})
        registro = base / "casa" / "registro.json"
        assert registrar(raiz, carpeta, registro, "vista", "a")[0] == 0
        antes = registro.read_bytes()

        def falla(*_):
            raise OSError(13, "reemplazo simulado")

        original, M.os.replace = M.os.replace, falla
        try:
            codigo, salida, error = registrar(raiz, carpeta, registro, "descartada", "a")
        finally:
            M.os.replace = original
        assert codigo == 2 and str(registro) in error and "reemplazo simulado" in error and salida == "", (codigo, salida, error)
        assert registro.read_bytes() == antes and os.listdir(registro.parent) == ["registro.json"], os.listdir(registro.parent)
        archivo = escribir(base / "un-archivo", "x")
        codigo, salida, error = registrar(raiz, carpeta, archivo / "registro.json", "vista", "a")
        assert codigo == 2 and str(archivo) in error and salida == "", (codigo, salida, error)


def test_el_registro_no_guarda_ni_la_descripcion_ni_el_nombre_ni_el_cuerpo():
    with temporal() as base:
        raiz = instancia(base)
        contenido = memoria(nombre="Nombre inventado Qx", descripcion="Descripción inventada Qy").replace(
            "Cuerpo de la memoria.", "Cuerpo inventado Qz")
        carpeta = memorias(base, {"a.md": contenido})
        registro = base / "registro.json"
        assert registrar(raiz, carpeta, registro, "descartada", "a")[0] == 0
        texto = registro.read_bytes().decode("utf-8")
        for fragmento in ("Qx", "Qy", "Qz", "inventad", "feedback"):
            assert fragmento not in texto, (fragmento, texto)
        assert [list(entrada) for entrada in json.loads(texto)["memorias"].values()] == [["slug", "modified", "estado", "fecha"]], texto


def test_sin_registrar_no_escribe_ni_la_memoria_ni_la_instancia_ni_el_registro():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:a")])
        (raiz / ".git").mkdir()
        carpeta = memorias(base, {"a.md": memoria(), "b.md": memoria(), "c.md": "roto", "p.md": memoria("project")})
        registro = base / "casa" / "registro.json"
        assert registrar(raiz, carpeta, registro, "vista", "b")[0] == 0
        antes = huella(carpeta, raiz, registro.parent)
        for argv in ((), ("--json",), ("--con-project",), ("--json", "--con-project")):
            assert con_registro(raiz, carpeta, registro, *argv)[0] == 0
        assert huella(carpeta, raiz, registro.parent) == antes
        casa = base / "casa-vacia"
        entorno = {"HOME": str(casa), "USERPROFILE": str(casa)}
        assert correr("--raiz", str(raiz), "--memorias", str(carpeta), "--json", entorno=entorno)[0] == 0
        assert not casa.exists()


def test_el_registro_por_defecto_vive_en_la_casa_con_el_nombre_del_repo_de_la_instancia():
    with temporal() as base:
        raiz = instancia(base)
        (raiz / ".git").mkdir()
        carpeta = memorias(base, {"a.md": memoria()})
        casa = base / "casa"
        entorno = {"HOME": str(casa), "USERPROFILE": str(casa)}
        nombre = "".join(c if c.isascii() and c.isalnum() else "-" for c in str(raiz)) + ".json"
        codigo, salida, error = correr("--raiz", str(raiz), "--memorias", str(carpeta), "--registrar", "a", "--como", "vista",
                                       entorno=entorno)
        esperado = casa / ".odd-ws" / "memorias" / nombre
        assert codigo == 0 and esperado.is_file() and "REGISTRO %s (1)" % esperado in lineas(salida), (codigo, salida, error)
        assert os.listdir(esperado.parent) == [nombre], os.listdir(esperado.parent)
        subcarpeta = instancia(raiz, nombre="sub")
        datos = json_de("--raiz", str(subcarpeta), "--memorias", str(carpeta), entorno=entorno)
        assert por_slug(datos)["a"]["estado"] == "vista", "una instancia dentro del repo usa el registro del repo"


def test_registrar_y_como_van_juntos_y_codex_no_registra():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria()})
        registro = base / "registro.json"
        for argv in (("--como", "vista"), ("--registrar", "a"), ("--registrar", "a", "--como", "otra"),
                     ("--registrar", "--como", "vista")):
            codigo, salida, error = con_registro(raiz, carpeta, registro, *argv)
            assert codigo == 2 and salida == "", (argv, codigo, salida, error)
        assert not registro.exists()
        for argv in (("--registrar", "a", "--como", "vista"), ("--registro", str(registro))):
            codigo, salida, error = correr("--raiz", str(raiz), "--host", "codex", *argv)
            assert codigo == 2 and "--host claude-code" in error and salida == "", (argv, codigo, salida, error)
        assert not registro.exists()


def seccion_de(texto, titulo):
    nivel = len(titulo) - len(titulo.lstrip("#"))
    partes, dentro, en_bloque = [], False, False
    for linea in texto.split("\n"):
        if linea.lstrip().startswith("```"):
            en_bloque = not en_bloque
        elif not en_bloque and linea.startswith("#"):
            if dentro and len(linea) - len(linea.lstrip("#")) <= nivel:
                break
            dentro = dentro or linea.startswith(titulo)
        if dentro:
            partes.append(linea)
    assert partes, "la skill no tiene la sección %r" % titulo
    return "\n".join(partes)


def zona_de_memorias(texto):
    return seccion_de(texto, "## 10.") + "\n" + seccion_de(texto, "## Modo memorias")


def comandos_de_memorias(zona):
    comandos, en_bloque = [], False
    for linea in zona.split("\n"):
        if linea.lstrip().startswith("```"):
            en_bloque = not en_bloque
        elif en_bloque and "memorias.py" in linea:
            tokens = shlex.split(linea.strip())
            posicion = next(i for i, token in enumerate(tokens) if token.endswith("memorias.py"))
            comandos.append(tokens[posicion + 1:])
    return comandos


def problemas_de_los_comandos(texto):
    zona = zona_de_memorias(texto)
    parser = M.construir_parser()
    opciones = {opcion for accion in parser._actions for opcion in accion.option_strings}
    comandos = comandos_de_memorias(zona)
    problemas = [] if len(comandos) >= 3 else ["la skill da %d comandos de memorias.py, se esperaban M1 y los dos de M4" % len(comandos)]
    for argv in comandos:
        desconocidos = [token for token in argv if MARCADOR_RE.fullmatch(token) and token not in SUSTITUTOS]
        if desconocidos:
            problemas.append("marcador sin valor sintético %s en %s" % (desconocidos, argv))
            continue
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                args = parser.parse_args([SUSTITUTOS.get(token, token) for token in argv])
        except SystemExit:
            problemas.append("el parser de memorias.py rechaza %s" % argv)
            continue
        if (args.registrar is None) != (args.como is None):
            problemas.append("--registrar y --como no van juntos en %s" % argv)
    problemas += ["la skill nombra %s, que memorias.py no tiene" % opcion for opcion in sorted(set(OPCION_RE.findall(zona)) - opciones)]
    return problemas


def problemas_del_json(texto, datos, codex):
    zona = zona_de_memorias(texto)
    problemas, rutas = [], set()
    for token in CODIGO_RE.findall(zona):
        encontrada = RUTA_JSON_RE.fullmatch(token)
        if encontrada and encontrada.group(1) in datos and encontrada.group(2) not in EXTENSIONES:
            rutas.add(encontrada.groups())
    if not rutas:
        problemas.append("la skill no nombra ninguna clave anidada del JSON")
    for primera, segunda in sorted(rutas):
        if not any(isinstance(informe[primera], dict) and segunda in informe[primera] for informe in (datos, codex)):
            problemas.append("la skill nombra %s.%s, que el JSON no trae" % (primera, segunda))
    linea = next((linea for linea in zona.split("\n") if "**Cada memoria del JSON**" in linea), None)
    if linea is None:
        return problemas + ["la skill no dice qué trae cada memoria del JSON"]
    claves = set(datos["memorias"][0])
    nombradas = set(CODIGO_RE.findall(linea))
    if not nombradas & claves:
        problemas.append("la línea de cada memoria no nombra ninguna clave real")
    problemas += ["la línea de cada memoria nombra %s, que no es clave, estado ni sección del JSON" % token
                  for token in sorted(nombradas - claves - set(datos) - set(M.PRECEDENCIA))]
    return problemas


def test_los_comandos_de_memorias_py_que_da_la_skill_los_acepta_su_parser():
    texto = SKILL_CERRAR.read_text(encoding="utf-8")
    assert problemas_de_los_comandos(texto) == [], problemas_de_los_comandos(texto)
    mutada = texto.replace("--como vista", "--coma vista", 1)
    assert mutada != texto and problemas_de_los_comandos(mutada), "control positivo: una opción que no existe se detecta"


def test_las_claves_del_json_que_nombra_la_skill_existen_en_la_salida_real():
    texto = SKILL_CERRAR.read_text(encoding="utf-8")
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria()})
        datos = json_de("--raiz", str(raiz), "--memorias", str(carpeta))
        codex = json_de("--raiz", str(raiz), "--host", "codex")
    assert problemas_del_json(texto, datos, codex) == [], problemas_del_json(texto, datos, codex)
    mutada = texto.replace("`cobertura.origen`", "`cobertura.origin`", 1).replace("`tipo`, `descripcion`", "`tipo`, `descripción`", 1)
    assert mutada != texto and len(problemas_del_json(mutada, datos, codex)) == 2, "control positivo: dos claves que no existen se detectan"


def test_las_reglas_del_modo_y_la_propuesta_nombran_la_evidencia():
    texto = SKILL_CERRAR.read_text(encoding="utf-8")
    reglas = seccion_de(texto, "### Reglas duras del modo")
    numeradas = {linea.split(".", 1)[0]: linea for linea in reglas.split("\n") if re.match(r"\d+\. ", linea)}
    assert "evidencia" in numeradas.get("2", "") and "`descripcion`" in numeradas.get("2", ""), numeradas.get("2")
    assert "evidencia.md" in numeradas.get("4", ""), numeradas.get("4")
    assert "evidencia.md" in seccion_de(texto, "### M3."), "la propuesta muestra la entrada de evidencia.md"


def test_de_punta_a_punta_solo_un_origen_exacto_y_valido_gradua():
    with temporal() as base:
        raiz = instancia(base, [fila("SQL-01", "memoria:graduable"), fila("SQL-02", "memoria:engram-123"),
                                fila("SQL-03", "memoria:regla+rara")])
        carpeta = memorias(base, {"graduable.md": memoria(), "engram-12.md": memoria(), "regla+rara.md": memoria()})
        datos = json_de("--raiz", str(raiz), "--memorias", str(carpeta))
        resultado = {slug: (registro["estado"], registro["filas"]) for slug, registro in por_slug(datos).items()}
        assert resultado == {"graduable": ("graduada", ["SQL-01"]), "engram-12": ("nueva", []), "regla+rara": ("nueva", [])}, resultado
        assert len(datos["avisos"]) == 1 and datos["avisos"][0].startswith("matriz fila 4:"), datos["avisos"]
        assert "regla+rara" in datos["avisos"][0] and not any("engram" in aviso for aviso in datos["avisos"]), datos["avisos"]


def test_un_cuerpo_que_cambia_sin_tocar_modified_sigue_vista_porque_solo_se_compara_modified():
    with temporal() as base:
        raiz = instancia(base)
        carpeta = memorias(base, {"a.md": memoria()})
        registro = base / "registro.json"
        assert registrar(raiz, carpeta, registro, "vista", "a")[0] == 0
        escribir(carpeta / "a.md", memoria().replace("Cuerpo de la memoria.", "Otro cuerpo, con otra regla."))
        assert estados(raiz, carpeta, registro) == {"a": "vista"}, "el límite documentado: sin otro modified no vuelve"
        escribir(carpeta / "a.md", memoria(modificada="2026-11-20T08:00:00Z"))
        assert estados(raiz, carpeta, registro) == {"a": "cambiada"}


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
