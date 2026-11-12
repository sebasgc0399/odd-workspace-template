import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
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
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = M.main(list(argv), entorno={} if entorno is None else entorno)
    return codigo, salida.getvalue(), error.getvalue()


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
        r = subprocess.run([sys.executable, str(_RUTA), "--raiz", str(raiz), "--memorias", str(carpeta)], capture_output=True,
                           env=entorno, cwd=str(base))
        assert r.returncode == 0 and b"Traceback" not in r.stderr, r.stderr
        assert "Señal de diseño" in r.stdout.decode("utf-8"), r.stdout


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
