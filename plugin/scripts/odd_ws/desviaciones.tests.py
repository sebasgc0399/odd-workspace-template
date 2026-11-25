import sys

sys.dont_write_bytecode = True

import codecs
import importlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

ENCABEZADO = "id,ubicacion,resumen,porque,fecha\n"
HASH = "abc1234"
REPO = "db:src/ventas.sql@%s:10-14" % HASH
SOBRANTES = []


def m():
    return importlib.import_module("odd_ws.desviaciones")


def config_loader():
    return importlib.import_module("config_loader")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


class Instancia:
    def __init__(self, repos=("db", "app"), csv=None, config=None):
        self.repos, self.csv, self.config = repos, csv, config

    def __enter__(self):
        self.raiz = Path(os.path.realpath(tempfile.mkdtemp(prefix="desviaciones-test-")))
        config = self.config if self.config is not None else json.dumps(
            {"schema_version": 1, "repos": {r: {} for r in self.repos}, "layers": {"sql": {"extensions": [".sql"], "repos": ["db"]}}})
        (self.raiz / "workspace.config.json").write_text(config, encoding="utf-8")
        if self.csv is not None:
            ruta = self.raiz / ".claude" / "reglas" / "desviaciones.csv"
            ruta.parent.mkdir(parents=True)
            ruta.write_bytes(self.csv if isinstance(self.csv, bytes) else self.csv.encode("utf-8"))
        return self.raiz

    def __exit__(self, *_):
        shutil.rmtree(self.raiz, onexc=_quitar)
        if self.raiz.exists():
            SOBRANTES.append(str(self.raiz))


def cargar(csv, **kwargs):
    with Instancia(csv=csv, **kwargs) as raiz:
        return m().cargar(raiz)


def solo_problemas(csv, **kwargs):
    filas, problemas = cargar(csv, **kwargs)
    return problemas


def test_sin_el_archivo_no_hay_filas_ni_problemas_y_no_lee_la_config():
    assert cargar(None) == ([], [])
    assert cargar(None, config="{ rota") == ([], []), "sin el archivo, la config rota no importa"
    assert m().ARCHIVO == ".claude/reglas/desviaciones.csv"


def test_las_filas_validas_de_las_dos_formas_de_ubicacion_salen_con_su_linea_y_sus_partes():
    texto = (ENCABEZADO
             + "catch-silencioso,%s,El CATCH no relanza el error,Lo pide el contrato con el POS,2026-11-25\n" % REPO
             + "\n"
             + 'typo-congelado,docs/glosario.md,"Dice ""Reponse"", con el error",Otro sistema consume ese nombre,2026-01-02\n')
    filas, problemas = cargar(texto)
    assert problemas == [], problemas
    assert [f["linea"] for f in filas] == [2, 4], filas
    primera, segunda = filas
    assert {k: primera[k] for k in ("id", "ubicacion", "resumen", "porque", "fecha")} == {
        "id": "catch-silencioso", "ubicacion": REPO, "resumen": "El CATCH no relanza el error",
        "porque": "Lo pide el contrato con el POS", "fecha": "2026-11-25"}, primera
    assert (primera["repo"], primera["ruta"], primera["hash"], primera["ini"], primera["fin"]) == ("db", "src/ventas.sql", HASH, 10, 14), primera
    assert (segunda["repo"], segunda["ruta"], segunda["hash"], segunda["ini"], segunda["fin"]) == (None, "docs/glosario.md", None, None, None)
    assert segunda["resumen"] == 'Dice "Reponse", con el error', segunda


def test_se_lee_con_bom_y_con_crlf():
    texto = (ENCABEZADO + "a,%s,r,p,2026-11-25\n" % REPO).replace("\n", "\r\n")
    filas, problemas = cargar(codecs.BOM_UTF8 + texto.encode("utf-8"))
    assert problemas == [] and [f["id"] for f in filas] == ["a"], (filas, problemas)


def test_un_encabezado_distinto_es_un_problema_en_su_linea_y_ninguna_fila_vale():
    for texto in ("id,ubicacion,resumen,motivo,fecha\na,%s,r,p,2026-11-25\n" % REPO, "\n\nid,ubicacion\n"):
        filas, problemas = cargar(texto)
        assert filas == [] and len(problemas) == 1, (texto, filas, problemas)
        linea, mensaje = problemas[0]
        assert linea == texto.count("\n", 0, texto.index("id")) + 1 and "id,ubicacion,resumen,porque,fecha" in mensaje, problemas
    filas, problemas = cargar("")
    assert filas == [] and problemas == [(1, "falta el encabezado id,ubicacion,resumen,porque,fecha")], problemas


def test_un_campo_que_falta_o_vacio_es_un_problema_de_su_fila():
    texto = (ENCABEZADO + "a,%s,r,p,2026-11-25\n" % REPO + "b,%s,r\n" % REPO + "c,%s, ,p,2026-11-25\n" % REPO
             + "d,%s,r,p,2026-11-25,sobra\n" % REPO)
    filas, problemas = cargar(texto)
    assert [f["id"] for f in filas] == ["a"], filas
    assert problemas == [(3, "falta porque, fecha"), (4, "falta resumen"), (5, "tiene 6 campos y el encabezado 5")], problemas


def test_una_ubicacion_mal_formada_es_un_problema_de_su_fila():
    malas = ["db:src/a.sql:1-2", "db:src/a.sql@%s" % HASH, "db:src/a.sql@%s:5-2" % HASH, "db:/abs/a.sql@%s:1-2" % HASH,
             ":src/a.sql@%s:1-2" % HASH, "db:memoria:1-2", "/abs/a.md", "../fuera.md", "docs/../../fuera.md", "con espacio.md",
             "C:\\docs\\a.md", "docs\\a.md", "a@b.md"]
    texto = ENCABEZADO + "".join('m%d,"%s",r,p,2026-11-25\n' % (i, u) for i, u in enumerate(malas))
    filas, problemas = cargar(texto)
    assert filas == [], filas
    assert [n for n, _ in problemas] == list(range(2, 2 + len(malas))), problemas
    for (n, mensaje), ubicacion in zip(problemas, malas):
        assert mensaje.startswith("ubicacion '%s'" % ubicacion), (n, mensaje)
    assert "sin @hash" in problemas[0][1] and "1-based" in problemas[2][1] and "relativa" in problemas[3][1], problemas
    assert "relativa" in problemas[6][1] and "relativa" in problemas[7][1], problemas


def test_un_repo_que_no_esta_en_la_config_es_un_problema_de_su_fila():
    texto = ENCABEZADO + "a,web:src/a.ts@%s:1-2,r,p,2026-11-25\n" % HASH
    assert solo_problemas(texto) == [(2, "el repo 'web' no está en workspace.config.json (repos: app, db)")]
    assert solo_problemas(texto, repos=()) == [(2, "el repo 'web' no está en workspace.config.json (no declara repos)")]


def test_una_fecha_mal_formada_es_un_problema_de_su_fila():
    malas = ["2026-13-01", "2026-02-30", "25/11/2026", "2026-1-5", "20261125", "hoy"]
    texto = ENCABEZADO + "".join("f%d,%s,r,p,%s\n" % (i, REPO, f) for i, f in enumerate(malas))
    problemas = solo_problemas(texto)
    assert problemas == [(i + 2, "fecha '%s' no es AAAA-MM-DD" % f) for i, f in enumerate(malas)], problemas


def test_un_id_repetido_es_un_problema_de_la_fila_que_lo_repite():
    texto = ENCABEZADO + "a,%s,r,p,2026-11-25\n" % REPO + "b,docs/x.md,r,p,2026-11-25\n" + "a,docs/y.md,r,p,2026-11-25\n"
    filas, problemas = cargar(texto)
    assert [f["id"] for f in filas] == ["a", "b"], filas
    assert problemas == [(4, "id 'a' repetido (ya en la línea 2)")], problemas


def test_una_fila_con_varios_defectos_es_un_solo_problema():
    texto = ENCABEZADO + "a,%s,r,p,2026-11-25\n" % REPO + "a,web:x.ts@%s:1-2,,p,ayer\n" % HASH
    assert solo_problemas(texto) == [(3, "falta resumen; id 'a' repetido (ya en la línea 2); el repo 'web' no está en "
                                         "workspace.config.json (repos: app, db); fecha 'ayer' no es AAAA-MM-DD")]


def test_un_archivo_ilegible_es_un_problema_y_no_hace_fallar():
    filas, problemas = cargar(b"\xff\xfe" + ENCABEZADO.encode("utf-16-le"))
    assert filas == [] and len(problemas) == 1 and problemas[0][0] == 1 and "UTF-8" in problemas[0][1], problemas
    with Instancia() as raiz:
        (raiz / ".claude" / "reglas" / "desviaciones.csv").mkdir(parents=True)
        filas, problemas = m().cargar(raiz)
        assert filas == [] and len(problemas) == 1 and "no se puede leer" in problemas[0][1], problemas


def test_con_el_archivo_y_la_config_rota_levanta_config_rota():
    for config in ("{ rota", json.dumps({"schema_version": 1, "repos": ["db"]}), json.dumps({"schema_version": 9})):
        with Instancia(csv=ENCABEZADO, config=config) as raiz:
            try:
                m().cargar(raiz)
            except config_loader().ConfigRota:
                continue
            raise AssertionError("no levantó ConfigRota con %s" % config)


def test_la_linea_para_el_prompt_y_el_texto_del_problema():
    texto = ENCABEZADO + 'a,%s,"El CATCH\nno relanza",Lo pide   el contrato,2026-11-25\n' % REPO
    filas, problemas = cargar(texto)
    assert problemas == [], problemas
    assert m().linea(filas[0]) == "a %s — El CATCH no relanza: Lo pide el contrato" % REPO, m().linea(filas[0])
    assert m().texto_del_problema((3, "falta porque")) == ".claude/reglas/desviaciones.csv:3: falta porque"


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
    if SOBRANTES:
        print("quedaron carpetas temporales: %s" % ", ".join(SOBRANTES))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
