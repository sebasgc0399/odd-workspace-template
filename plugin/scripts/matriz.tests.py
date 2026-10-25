import contextlib
import csv
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
_RUTA = AQUI / "matriz.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []


def _cargar():
    spec = importlib.util.spec_from_file_location("matriz", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None

ENC = ["id", "origen", "tipo", "destino", "severidad", "numeros", "resumen", "motivo"]
PREFIJOS = {"SQL": "sql", "WEB": "web", "MOV": "movil"}
CAPAS_CONFIG = {"sql": {"extensions": [".sql"], "rule_prefix": "SQL"},
                "web": {"extensions": [".cs"], "rule_prefix": "WEB"},
                "movil": {"extensions": [".java"], "rule_prefix": "MOV"},
                "docs": {"extensions": [".md"]}}

P_SQL = ".claude/skills/capa-sql/SKILL.md"
H_SQL = ".claude/reglas/verificar_sql.py"
A_SQL = ".claude/agents/revisor-sql.md"
CRIT = ".claude/skills/criterios/SKILL.md"
CREF = ".claude/skills/criterios/references/sql.md"
EVID = ".claude/reglas/evidencia.md"
MATRIZ_DEFECTO = ".claude/reglas/matriz.csv"

SKILL_OK = ("# capa-sql\n\nSQL-02: regla fuera del bloque\n\n<!-- no-negociables -->\n"
            "SQL-01: dentro del bloque\n<!-- /no-negociables -->\n")


def fila(id_="SQL-01", origen="a.md@abc1234:1-2", tipo="CE", destino="descarte",
         severidad="", numeros="", resumen="regla", motivo="porque"):
    return [id_, origen, tipo, destino, severidad, numeros, resumen, motivo]


def csv_texto(filas, encabezado=ENC):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(encabezado)
    for f in filas:
        w.writerow(f)
    return buf.getvalue()


def cargar(filas, encabezado=ENC, prefijos=PREFIJOS):
    return M.cargar_matriz(csv_texto(filas, encabezado), prefijos)


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    raiz = Path(tempfile.mkdtemp(prefix="matriz-test-"))
    try:
        yield raiz
    finally:
        shutil.rmtree(raiz, onexc=_quitar)
        if raiz.exists():
            SOBRANTES.append(str(raiz))


def escribir(raiz, archivos):
    for ruta, texto in archivos.items():
        p = Path(raiz) / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)


def instancia(raiz, capas=None, repos=None):
    config = {"schema_version": 1, "repos": repos or {}, "layers": capas or CAPAS_CONFIG}
    escribir(raiz, {"workspace.config.json": json.dumps(config, ensure_ascii=False)})
    return Path(raiz)


def escribir_matriz(raiz, filas, nombre="matriz.csv", encabezado=ENC):
    p = Path(raiz) / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(csv_texto(filas, encabezado).encode("utf-8"))
    return str(p)


def correr(argv):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = M.main(argv)
    return codigo, salida.getvalue(), error.getvalue()


def lineas(salida):
    return [l for l in salida.splitlines() if l.strip()]


def fila_valida(id_, destino, **kw):
    filas, errores = cargar([fila(id_, destino=destino, **kw)])
    assert not errores, errores
    return filas[0]


def filas_validas(*specs):
    filas, errores = cargar([fila(i, destino=d, **kw) for i, d, kw in specs])
    assert not errores, errores
    return filas


def test_esquema_matriz_valida():
    filas, errores = cargar([
        fila("SQL-01", "a/b.md@abc1234:1-1;c.md@0881eb4:3-9;memoria:mi_slug", "CE", "chequeo", "CRITICAL", "16;151"),
        fila("WEB-02", "x.md@abc1234:2-5", "META", "evidencia"),
        fila("MOV-100", "x.md@abc1234:2-5", "PR", "reviewer-PR", "WARNING"),
    ])
    assert not errores, errores
    assert [f["id"] for f in filas] == ["SQL-01", "WEB-02", "MOV-100"]
    assert [f["capa"] for f in filas] == ["sql", "web", "movil"]


def test_esquema_el_mapeo_de_prefijos_sale_de_quien_llama():
    filas, errores = cargar([fila("BD-01")], prefijos={"BD": "sql"})
    assert not errores and filas[0]["capa"] == "sql", errores
    filas, errores = cargar([fila("SQL-01")], prefijos={"BD": "sql"})
    assert not filas and errores and "id" in errores[0][1] and "BD" in errores[0][1], errores


def test_esquema_sin_prefijos_toda_fila_es_invalida():
    filas, errores = cargar([fila("SQL-01")], prefijos={})
    assert not filas and len(errores) == 1 and errores[0][0] == 2 and "id" in errores[0][1], errores


def test_esquema_encabezado_exacto():
    malos = [
        ["id", "origen", "tipo", "destino", "severidad", "numeros", "resumen"],
        ["ID", "origen", "tipo", "destino", "severidad", "numeros", "resumen", "motivo"],
        ["origen", "id", "tipo", "destino", "severidad", "numeros", "resumen", "motivo"],
        ENC + ["extra"],
    ]
    for enc in malos:
        filas, errores = cargar([fila()], enc)
        assert not filas, enc
        assert errores and errores[0][0] == 1, (enc, errores)
    filas, errores = M.cargar_matriz("﻿" + csv_texto([fila()]), PREFIJOS)
    assert errores and errores[0][0] == 1 and "BOM" in errores[0][1], errores
    filas, errores = M.cargar_matriz("", PREFIJOS)
    assert errores and errores[0][0] == 1, errores


def test_esquema_id_formato():
    for malo in ["sql-01", "SQL-1", "SQL01", "XX-01", "SQL-01x", "SQL-0a", "xSQL-01", "SQL-", " SQL-01", ""]:
        filas, errores = cargar([fila(malo)])
        assert not filas and errores and errores[0][0] == 2 and "id" in errores[0][1], (malo, errores)
    for bueno in ["SQL-01", "WEB-99", "MOV-100", "SQL-0001"]:
        filas, errores = cargar([fila(bueno)])
        assert not errores and len(filas) == 1, (bueno, errores)


def test_esquema_id_unico():
    filas, errores = cargar([fila("SQL-01"), fila("WEB-01"), fila("SQL-01")])
    assert len(errores) == 1 and errores[0][0] == 4 and "duplicado" in errores[0][1] and "2" in errores[0][1], errores
    assert [f["id"] for f in filas] == ["SQL-01", "WEB-01"]


def test_esquema_tipo():
    for t in ["CE", "CC", "PR", "CR", "MT", "META"]:
        assert not cargar([fila(tipo=t)])[1], t
    for t in ["", "ce", "XX", "META "]:
        filas, errores = cargar([fila(tipo=t)])
        assert not filas and errores and "tipo" in errores[0][1], (t, errores)


def test_esquema_destino():
    for d in ["chequeo", "pasiva", "skill", "reviewer-PR", "criterios", "evidencia", "descarte"]:
        assert not cargar([fila(destino=d)])[1], d
    for d in ["", "Chequeo", "reviewer", "otro", "criterios-pos"]:
        filas, errores = cargar([fila(destino=d)])
        assert not filas and errores and "destino" in errores[0][1], (d, errores)


def test_esquema_severidad():
    for s in ["CRITICAL", "WARNING", "SUGGESTION", ""]:
        assert not cargar([fila(severidad=s)])[1], s
    for s in ["critical", "HIGH", "WARNING "]:
        filas, errores = cargar([fila(severidad=s)])
        assert not filas and errores and "severidad" in errores[0][1], (s, errores)


def test_esquema_resumen_y_motivo_obligatorios():
    filas, errores = cargar([fila(resumen="")])
    assert not filas and errores and "resumen" in errores[0][1], errores
    filas, errores = cargar([fila(motivo="   ")])
    assert not filas and errores and "motivo" in errores[0][1], errores
    filas, errores = cargar([fila(resumen="", motivo="")])
    assert len(errores) == 2, errores


def test_esquema_origen_formatos():
    buenos = ["a.md@abc1234:1-1", "dir/sub/a.md@abc1234:10-20", "a.md@abc1234:3-9", "a.md@" + "f" * 40 + ":1-2",
              "memoria:mi_slug-2", "a.md@abc1234:1-2;b.md@0881eb4:5-5;memoria:otra", "memoria:señal"]
    for o in buenos:
        assert not cargar([fila(origen=o)])[1], o
    malos = ["", "a.md", "a.md@abc1234:5-3", "a.md@abc1234:0-3", "a.md@abc1234:1", "a.md@abc1234:x-y",
             "a.md@abc12:1-2", "a.md@XYZ1234:1-2", "dir\\a.md@abc1234:1-2", "/abs/a.md@abc1234:1-2",
             "memoria:", "memoria:a/b", "a.md@abc1234:1-2;", "a.md@abc1234:1-2;;b.md@abc1234:1-2",
             "a.md@abc1234:1-2 b.md@abc1234:3-4", "../a.md@abc1234:1-2"]
    for o in malos:
        filas, errores = cargar([fila(origen=o)])
        assert not filas and errores and "origen" in errores[0][1], (o, errores)


def test_esquema_origen_sin_hash():
    for o, pieza in (("a.md:1-2", "a.md:1-2"), ("memoria:x;dir/a.md:3-9", "dir/a.md:3-9"),
                     ("a.md@abc1234:1-2;b.md:5-5", "b.md:5-5")):
        filas, errores = cargar([fila(origen=o)])
        assert not filas and len(errores) == 1 and errores[0][0] == 2, (o, errores)
        assert "origen" in errores[0][1] and pieza in errores[0][1] and "@hash" in errores[0][1], (o, errores)
    filas, errores = cargar([fila(origen="memoria:solo")])
    assert not errores and len(filas) == 1, errores
    o = M.parsear_origen("a.md:1-2")
    assert (o["tipo"], o["hash"]) == ("rango", None), o


def test_esquema_numeros():
    for n in ["", "16", "16;151", "0.5;3"]:
        assert not cargar([fila(numeros=n)])[1], n
    for n in ["16;", ";16", "16;;151"]:
        filas, errores = cargar([fila(numeros=n)])
        assert not filas and errores and "numeros" in errores[0][1], (n, errores)
    filas, errores = cargar([fila(numeros="16;151")])
    assert filas[0]["numeros"] == ["16", "151"]


def test_esquema_fila_con_columnas_de_menos_y_numeracion():
    texto = csv_texto([fila("SQL-01")]) + "SQL-02,a.md:1-2,CE\n\n" + ",".join(fila("WEB-01")) + "\n"
    filas, errores = M.cargar_matriz(texto, PREFIJOS)
    assert [f["id"] for f in filas] == ["SQL-01", "WEB-01"]
    assert len(errores) == 1 and errores[0][0] == 3 and "columnas" in errores[0][1], errores


def test_esquema_csv_con_comillas_y_saltos():
    f = fila("SQL-01", resumen='dice "no hacer X", y luego\nsigue', motivo="a,b")
    filas, errores = cargar([f, fila("WEB-01")])
    assert not errores and len(filas) == 2, errores
    assert filas[0]["resumen"] == f[6] and filas[0]["motivo"] == "a,b"


def test_parsear_origen():
    o = M.parsear_origen("dir/a.md:3-9")
    assert (o["tipo"], o["ruta"], o["hash"], o["ini"], o["fin"]) == ("rango", "dir/a.md", None, 3, 9)
    o = M.parsear_origen("a.md@0881eb4:5-5")
    assert (o["tipo"], o["ruta"], o["hash"], o["ini"], o["fin"]) == ("rango", "a.md", "0881eb4", 5, 5)
    o = M.parsear_origen("memoria:mi_slug")
    assert (o["tipo"], o["slug"]) == ("memoria", "mi_slug")
    try:
        M.parsear_origen("a.md:5-3")
    except ValueError:
        pass
    else:
        raise AssertionError("ini > fin deberia levantar ValueError")


def test_id_entero():
    casos = [
        ("SQL-01", "regla SQL-01", 1),
        ("SQL-01", "SQL-01", 1),
        ("SQL-01", "(SQL-01), y mas", 1),
        ("SQL-01", "SQL-010 es otra regla", 0),
        ("SQL-01", "XSQL-01 tampoco", 0),
        ("SQL-01", "SQL-01a tampoco", 0),
        ("SQL-01", "SQL-01 y SQL-01 otra vez", 2),
        ("SQL-01", "SQL-010 SQL-01", 1),
        ("SQL-10", "SQL-1 SQL-100", 0),
    ]
    for id_, texto, esperado in casos:
        assert M.contar_id(id_, texto) == esperado, (id_, texto)


def test_numero_entero():
    casos = [
        ("16", "usa 16 aqui", True),
        ("16", "error(..., 16, 1)", True),
        ("16", "el 160 no", False),
        ("16", "el 116 no", False),
        ("16", "el 0.16 no", False),
        ("16", "el 16.5 no", False),
        ("16", "termina en 16.", True),
        ("16", "(16)", True),
        ("151", "16 y 151", True),
        ("151", "1510", False),
        ("0.5", "valor 0.5 ok", True),
    ]
    for num, texto, esperado in casos:
        assert M.numero_en_texto(num, texto) == esperado, (num, texto)


def test_partir_bloque_es_el_de_la_convencion():
    from odd_ws import capas
    assert M.partir_bloque is capas.partir_bloque


def test_segmento():
    ids = {"SQL-01", "SQL-02"}
    ls = ["intro", "SQL-01: regla", "detalle", "mas detalle", "", "suelto", "SQL-02: otra", "x"]
    assert M.segmentos("SQL-01", ls, ids) == ["SQL-01: regla\ndetalle\nmas detalle"]
    assert M.segmentos("SQL-02", ls, ids) == ["SQL-02: otra\nx"]
    ls = ["SQL-01: regla", "detalle", "SQL-02: otra", "tail"]
    assert M.segmentos("SQL-01", ls, ids) == ["SQL-01: regla\ndetalle"]
    ls = ["SQL-01: regla y ademas SQL-02", "detalle"]
    assert M.segmentos("SQL-01", ls, ids) == ["SQL-01: regla y ademas SQL-02\ndetalle"]
    ls = ["SQL-01: a", "SQL-010 no es de la matriz", "SQL-01: b", ""]
    assert M.segmentos("SQL-01", ls, ids) == ["SQL-01: a\nSQL-010 no es de la matriz\nSQL-01: b", "SQL-01: b"]
    assert M.segmentos("SQL-01", ["nada"], ids) == []


def test_destinos_una_vez_ok_por_destino():
    filas = filas_validas(
        ("SQL-01", "pasiva", {}), ("SQL-02", "skill", {}), ("SQL-03", "chequeo", {}),
        ("SQL-04", "reviewer-PR", {}), ("SQL-05", "criterios", {}), ("SQL-06", "evidencia", {}))
    archivos = {P_SQL: SKILL_OK, H_SQL: "# SQL-03 aqui\n", A_SQL: "SQL-04\n", CRIT: "texto\n", CREF: "SQL-05\n", EVID: "SQL-06\n"}
    assert M.verificar_destinos(filas, "sql", archivos) == ([], [])


def test_destinos_ausente_y_repetido():
    filas = filas_validas(("SQL-01", "chequeo", {}), ("SQL-02", "chequeo", {}))
    fallas, pendientes = M.verificar_destinos(filas, "sql", {H_SQL: "SQL-02\notra vez SQL-02\n"})
    assert len(fallas) == 2, fallas
    assert fallas[0].startswith("FALLA SQL-01: no aparece en " + H_SQL), fallas[0]
    assert fallas[1].startswith("FALLA SQL-02: aparece 2 veces en " + H_SQL), fallas[1]
    assert not pendientes


def test_destinos_id_entero_no_matchea_prefijo_ni_sufijo():
    filas = filas_validas(("SQL-01", "chequeo", {}))
    for texto in ["SQL-010\n", "XSQL-01\n", "SQL-01x\n"]:
        fallas, _ = M.verificar_destinos(filas, "sql", {H_SQL: texto})
        assert len(fallas) == 1 and "no aparece" in fallas[0], (texto, fallas)
    assert M.verificar_destinos(filas, "sql", {H_SQL: "SQL-010 y SQL-01\n"})[0] == []


def test_destinos_pasiva_dentro_skill_fuera():
    texto = "SQL-01 fuera\n<!-- no-negociables -->\nSQL-02 dentro\n<!-- /no-negociables -->\n"
    filas = filas_validas(("SQL-01", "pasiva", {}), ("SQL-02", "skill", {}))
    fallas, pendientes = M.verificar_destinos(filas, "sql", {P_SQL: texto})
    assert len(fallas) == 2, fallas
    assert fallas[0].startswith("FALLA SQL-01:") and "no aparece" in fallas[0] and "bloque" in fallas[0], fallas[0]
    assert fallas[1].startswith("FALLA SQL-02:") and "no aparece" in fallas[1], fallas[1]
    assert not pendientes


def test_destinos_pasiva_sin_bloque_es_falla_no_pendiente():
    filas = filas_validas(("SQL-01", "pasiva", {}), ("SQL-02", "skill", {}))
    fallas, pendientes = M.verificar_destinos(filas, "sql", {P_SQL: "SQL-01\nSQL-02\n"})
    assert len(fallas) == 1 and fallas[0].startswith("FALLA SQL-01:") and "no tiene el bloque" in fallas[0], fallas
    assert not pendientes
    fallas, _ = M.verificar_destinos(filas[:1], "sql", {P_SQL: "SQL-01\n<!-- no-negociables -->\n"})
    assert len(fallas) == 1 and "no se cierra" in fallas[0], fallas


def test_destinos_criterios_suma_skill_y_references():
    filas = filas_validas(("SQL-01", "criterios", {}))
    fallas, _ = M.verificar_destinos(filas, "sql", {CRIT: "SQL-01\n", CREF: "SQL-01\n"})
    assert len(fallas) == 1 and "aparece 2 veces" in fallas[0], fallas
    fallas, _ = M.verificar_destinos(filas, "sql", {CRIT: "x\n", ".claude/skills/criterios/references/otra.md": "SQL-01\n"})
    assert not fallas, fallas
    assert M.verificar_destinos(filas, "sql", {".claude/skills/criterios/references/x.md": "SQL-01\n"}) == ([], [])
    fallas, _ = M.verificar_destinos(filas, "sql", {CRIT: "x\n", ".claude/skills/criterios/references/sub/y.md": "SQL-01\n"})
    assert len(fallas) == 1 and "no aparece" in fallas[0], "una subcarpeta de references no cuenta: %r" % fallas


def test_destinos_pendiente_si_el_archivo_no_existe():
    filas = filas_validas(
        ("SQL-01", "pasiva", {}), ("SQL-02", "skill", {}), ("SQL-03", "chequeo", {}),
        ("SQL-04", "reviewer-PR", {}), ("SQL-05", "criterios", {}), ("SQL-06", "evidencia", {}))
    fallas, pendientes = M.verificar_destinos(filas, "sql", {})
    assert not fallas
    assert pendientes == [
        "PENDIENTE SQL-01: " + P_SQL + " no existe todavia",
        "PENDIENTE SQL-02: " + P_SQL + " no existe todavia",
        "PENDIENTE SQL-03: " + H_SQL + " no existe todavia",
        "PENDIENTE SQL-04: " + A_SQL + " no existe todavia",
        "PENDIENTE SQL-05: " + CRIT + " no existe todavia",
        "PENDIENTE SQL-06: " + EVID + " no existe todavia",
    ], pendientes


def test_destinos_solo_filas_de_la_capa():
    filas, _ = cargar([fila("SQL-01", destino="chequeo"), fila("WEB-01", destino="chequeo"), fila("MOV-01", destino="chequeo")])
    assert M.verificar_destinos(filas, "web", {}) == ([], ["PENDIENTE WEB-01: .claude/reglas/verificar_web.py no existe todavia"])


def test_destinos_descarte():
    filas = filas_validas(("SQL-01", "descarte", {}))
    assert M.verificar_destinos(filas, "sql", {}) == ([], [])
    sano = {P_SQL: "otra cosa\n", H_SQL: "x\n", A_SQL: "y\n", CRIT: "z\n", CREF: "w\n", EVID: "v\n"}
    assert M.verificar_destinos(filas, "sql", sano)[0] == []
    for ruta in [P_SQL, H_SQL, A_SQL, CRIT, CREF, EVID]:
        malo = dict(sano)
        malo[ruta] = "SQL-01 colado\n"
        fallas, _ = M.verificar_destinos(filas, "sql", malo)
        assert len(fallas) == 1 and fallas[0].startswith("FALLA SQL-01: descarte aparece en " + ruta), (ruta, fallas)
    malo = dict(sano)
    malo[".claude/skills/capa-web/SKILL.md"] = "SQL-01\n"
    assert M.verificar_destinos(filas, "sql", malo)[0] == [], "un archivo de OTRA capa no cuenta"
    malo = dict(sano)
    malo[P_SQL] = "SQL-010\nXSQL-01\n"
    assert M.verificar_destinos(filas, "sql", malo)[0] == []


def test_severidad_ok_y_faltantes():
    filas = filas_validas(("SQL-01", "chequeo", {"severidad": "CRITICAL", "numeros": "16;151"}))
    assert M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 error 16 / 151 [CRITICAL]\n"}) == ([], [])
    fallas, _ = M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 error 16 / 151\n"})
    assert len(fallas) == 1 and "severidad CRITICAL" in fallas[0] and "numero" not in fallas[0], fallas
    fallas, _ = M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 CRITICAL 16\n"})
    assert len(fallas) == 1 and "numero 151" in fallas[0] and "severidad" not in fallas[0], fallas
    fallas, _ = M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 aqui\n"})
    assert len(fallas) == 1 and fallas[0].startswith("FALLA SQL-01:"), fallas
    assert "severidad CRITICAL" in fallas[0] and "numero 16" in fallas[0] and "numero 151" in fallas[0], fallas
    fallas, _ = M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 CRITICAL 160 y 1510\n"})
    assert len(fallas) == 1 and "numero 16" in fallas[0] and "numero 151" in fallas[0], fallas
    fallas, _ = M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 NONCRITICAL 16 151\n"})
    assert len(fallas) == 1 and "severidad CRITICAL" in fallas[0], fallas


def test_severidad_limites_del_segmento():
    filas = filas_validas(("SQL-01", "chequeo", {"severidad": "WARNING", "numeros": "7"}), ("SQL-02", "chequeo", {}))
    assert len(M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 regla\n\nWARNING 7\n"})[0]) == 1
    assert len(M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 regla\nSQL-02 otra\nWARNING 7\n"})[0]) == 1
    assert M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 regla\ncontinua\nWARNING 7\n\nSQL-02\n"})[0] == []
    assert M.verificar_severidad(filas, "sql", {H_SQL: "SQL-02 aparte\nSQL-01 regla WARNING 7"})[0] == []
    assert len(M.verificar_severidad(filas, "sql", {H_SQL: "WARNING 7\nSQL-01 regla\n"})[0]) == 1


def test_severidad_varias_apariciones_alcanza_una():
    filas = filas_validas(("SQL-01", "chequeo", {"severidad": "WARNING", "numeros": "7"}))
    assert M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 primera sin nada\n\nSQL-01 segunda WARNING 7\n"})[0] == []
    fallas, _ = M.verificar_severidad(filas, "sql", {H_SQL: "SQL-01 a\n\nSQL-01 b WARNING\n\nSQL-01 c 7\n"})
    assert len(fallas) == 1, "ningun segmento cumple por si solo: %r" % fallas


def test_severidad_pendiente_ausente_y_filas_omitidas():
    filas = filas_validas(
        ("SQL-01", "chequeo", {"severidad": "CRITICAL"}),
        ("SQL-02", "descarte", {"severidad": "CRITICAL", "numeros": "9"}),
        ("SQL-03", "chequeo", {}),
        ("SQL-04", "reviewer-PR", {"numeros": "5"}))
    assert M.verificar_severidad(filas, "sql", {}) == ([], [
        "PENDIENTE SQL-01: " + H_SQL + " no existe todavia",
        "PENDIENTE SQL-04: " + A_SQL + " no existe todavia"])
    fallas, pendientes = M.verificar_severidad(filas, "sql", {H_SQL: "otra cosa\n", A_SQL: "SQL-04 5\n"})
    assert not pendientes and len(fallas) == 1 and fallas[0].startswith("FALLA SQL-01: no aparece en " + H_SQL), fallas


def test_severidad_pasiva_skill_y_criterios():
    filas = filas_validas(("SQL-01", "pasiva", {"severidad": "CRITICAL"}),
                          ("SQL-02", "skill", {"severidad": "WARNING"}),
                          ("SQL-03", "criterios", {"numeros": "151"}))
    texto = "SQL-02 WARNING fuera\n\n<!-- no-negociables -->\nSQL-01 CRITICAL dentro\n<!-- /no-negociables -->\n"
    assert M.verificar_severidad(filas, "sql", {P_SQL: texto, CREF: "SQL-03 usa 151\n", CRIT: "x\n"}) == ([], [])
    fallas, _ = M.verificar_severidad(filas[:2], "sql", {P_SQL: "SQL-01 CRITICAL\nSQL-02 WARNING\n"})
    assert len(fallas) == 1 and fallas[0].startswith("FALLA SQL-01:") and "no tiene el bloque" in fallas[0], fallas
    texto = "<!-- no-negociables -->\nSQL-01 CRITICAL\n<!-- /no-negociables -->\nSQL-02 sin severidad\n"
    fallas, _ = M.verificar_severidad(filas[:2], "sql", {P_SQL: texto})
    assert len(fallas) == 1 and fallas[0].startswith("FALLA SQL-02:"), fallas


def test_cargar_archivos_lee_los_destinos_de_las_capas_dadas():
    with temporal() as raiz:
        escribir(raiz, {P_SQL: "a\n", H_SQL: "b\n", A_SQL: "c\n", CRIT: "d\n", CREF: "e\n", EVID: "f\n",
                        ".claude/skills/criterios/references/sub/g.md": "g\n", ".claude/skills/capa-web/SKILL.md": "h\n",
                        ".claude/skills/capa-movil/SKILL.md": "i\n"})
        archivos = M.cargar_archivos(raiz, ["sql", "web"])
        assert set(archivos) == {P_SQL, H_SQL, A_SQL, CRIT, CREF, EVID, ".claude/skills/capa-web/SKILL.md"}, sorted(archivos)
        assert archivos[CREF] == "e\n"


def args(modo, capa, raiz, matriz=None):
    a = [modo, "--capa", capa, "--raiz", str(raiz)]
    return a + (["--matriz", str(matriz)] if matriz else [])


def test_cli_esquema_invalido_en_los_dos_modos():
    with temporal() as raiz:
        instancia(raiz)
        matriz = escribir_matriz(raiz, [fila("SQL-01"), fila("sql-02"), fila("WEB-01", tipo="XX")])
        for modo in ("--destinos", "--severidad"):
            codigo, out, err = correr(args(modo, "sql", raiz, matriz))
            esq = [l for l in lineas(out) if l.startswith("ESQUEMA")]
            assert codigo == 1, (modo, codigo, err)
            assert len(esq) == 2 and esq[0].startswith("ESQUEMA fila 3:") and esq[1].startswith("ESQUEMA fila 4:"), (modo, esq)
            assert "esquema=2" in lineas(out)[-1], lineas(out)[-1]


def test_cli_encabezado_invalido_corta():
    with temporal() as raiz:
        instancia(raiz)
        matriz = escribir_matriz(raiz, [fila("SQL-01", destino="chequeo")], encabezado=ENC[:-1])
        codigo, out, _ = correr(args("--destinos", "sql", raiz, matriz))
        esq = [l for l in lineas(out) if l.startswith("ESQUEMA")]
        assert codigo == 1 and len(esq) == 1 and esq[0].startswith("ESQUEMA fila 1:"), out
        assert not any(l.startswith(("FALLA", "PENDIENTE")) for l in lineas(out)), out


def test_cli_esquema_invalido_sigue_con_filas_validas():
    with temporal() as raiz:
        instancia(raiz)
        matriz = escribir_matriz(raiz, [fila("SQL-01", destino="chequeo"), fila("xx-9")])
        codigo, out, _ = correr(args("--destinos", "sql", raiz, matriz))
        ls = lineas(out)
        assert codigo == 1 and sum(l.startswith("ESQUEMA") for l in ls) == 1, out
        assert "PENDIENTE SQL-01: " + H_SQL + " no existe todavia" in ls, out


def test_cli_matriz_no_utf8_es_esquema_invalido():
    with temporal() as raiz:
        instancia(raiz)
        matriz = Path(raiz) / "matriz.csv"
        matriz.write_bytes(csv_texto([fila()]).encode("utf-8") + b"\xff\n")
        codigo, out, _ = correr(args("--destinos", "sql", raiz, matriz))
        assert codigo == 1 and lineas(out)[0].startswith("ESQUEMA fila 1:") and "UTF-8" in lineas(out)[0], out


def test_cli_matriz_inexistente_es_error_de_entorno():
    with temporal() as raiz:
        instancia(raiz)
        codigo, out, err = correr(args("--destinos", "sql", raiz, Path(raiz) / "no-esta.csv"))
        assert codigo == 2 and "no-esta.csv" in err and not lineas(out), (codigo, out, err)


def test_cli_no_necesita_git():
    with temporal() as raiz:
        instancia(raiz)
        matriz = escribir_matriz(raiz, [fila("SQL-01", destino="chequeo")])
        for modo in ("--destinos", "--severidad"):
            codigo, out, err = correr(args(modo, "sql", raiz, matriz))
            assert codigo == 0, (modo, codigo, out, err)


def test_cli_no_necesita_las_rutas_de_la_maquina():
    with temporal() as raiz:
        instancia(raiz, repos={"db": {}})
        matriz = escribir_matriz(raiz, [fila("SQL-01", destino="chequeo")])
        codigo, out, err = correr(args("--destinos", "sql", raiz, matriz))
        assert codigo == 0, (codigo, out, err)


def test_cli_uso():
    with temporal() as raiz:
        instancia(raiz)
        matriz = escribir_matriz(raiz, [fila()])
        casos = [
            ([], "sin modo"),
            (["--matriz", matriz, "--raiz", str(raiz)], "sin modo, solo opciones"),
            (["--destinos", "--matriz", matriz, "--raiz", str(raiz)], "destinos sin --capa"),
            (["--severidad", "--matriz", matriz, "--raiz", str(raiz)], "severidad sin --capa"),
            (args("--destinos", "otra", raiz, matriz), "capa no declarada"),
            (args("--destinos", "docs", raiz, matriz), "capa sin rule_prefix"),
            (["--destinos", "--severidad", "--capa", "sql", "--matriz", matriz, "--raiz", str(raiz)], "dos modos"),
            (["--cobertura", "--matriz", matriz, "--raiz", str(raiz)], "--cobertura no se porta"),
            (["--no-existe"], "opcion desconocida"),
        ]
        for argv, que in casos:
            codigo, out, err = correr(argv)
            assert codigo == 2, (que, codigo)
            assert not lineas(out), (que, out)
            assert err.strip(), que
        codigo, _, err = correr(args("--destinos", "otra", raiz, matriz))
        assert "otra" in err and "sql" in err, err
        codigo, _, err = correr(args("--destinos", "docs", raiz, matriz))
        assert "docs" in err and "rule_prefix" in err, err


def test_cli_sin_instancia_es_error_de_entorno():
    with temporal() as raiz:
        matriz = escribir_matriz(raiz, [fila()])
        codigo, out, err = correr(args("--destinos", "sql", raiz, matriz))
        assert codigo == 2 and "workspace.config.json" in err and not lineas(out), (codigo, out, err)


def test_cli_config_rota_es_error_de_entorno():
    with temporal() as raiz:
        escribir(raiz, {"workspace.config.json": "{no es json"})
        matriz = escribir_matriz(raiz, [fila()])
        codigo, out, err = correr(args("--destinos", "sql", raiz, matriz))
        assert codigo == 2 and "workspace.config.json" in err and not lineas(out), (codigo, out, err)


def test_cli_defaults_raiz_desde_la_sesion_y_matriz_de_la_convencion():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {H_SQL: "SQL-01\n"})
        escribir_matriz(raiz, [fila("SQL-01", destino="chequeo")], nombre=MATRIZ_DEFECTO)
        ticket = Path(raiz) / "tickets" / "T-1"
        ticket.mkdir(parents=True)
        previo = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(ticket)
        try:
            codigo, out, err = correr(["--destinos", "--capa", "sql"])
        finally:
            if previo is None:
                del os.environ["CLAUDE_PROJECT_DIR"]
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = previo
        assert codigo == 0 and "filas=1" in lineas(out)[-1] and "fallas=0" in lineas(out)[-1], (codigo, out, err)
    with temporal() as raiz:
        instancia(raiz)
        codigo, out, err = correr(["--destinos", "--capa", "sql", "--raiz", str(raiz)])
        assert codigo == 2 and "matriz.csv" in err, (codigo, out, err)


def test_cli_destinos_pendiente_contra_falla():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {CRIT: "criterios\n", A_SQL: "SQL-04 esta\n"})
        matriz = escribir_matriz(raiz, [
            fila("SQL-01", destino="pasiva"), fila("SQL-02", destino="criterios"), fila("SQL-03", destino="chequeo"),
            fila("SQL-04", destino="reviewer-PR"), fila("WEB-01", destino="criterios")])
        codigo, out, _ = correr(args("--destinos", "sql", raiz, matriz))
    ls = lineas(out)
    for e in ["FALLA SQL-02: no aparece en " + CRIT, "PENDIENTE SQL-01: " + P_SQL + " no existe todavia",
              "PENDIENTE SQL-03: " + H_SQL + " no existe todavia"]:
        assert any(l.startswith(e) for l in ls), (e, ls)
    assert not any("SQL-04" in l or "WEB-01" in l for l in ls[:-1]), ls
    assert codigo == 1
    assert ls[-1].startswith("RESUMEN") and "fallas=1" in ls[-1] and "pendientes=2" in ls[-1] and "filas=4" in ls[-1], ls[-1]


def test_cli_destinos_solo_pendientes_sale_0():
    with temporal() as raiz:
        instancia(raiz)
        matriz = escribir_matriz(raiz, [fila("SQL-01", destino="pasiva"), fila("SQL-02", destino="descarte")])
        codigo, out, _ = correr(args("--destinos", "sql", raiz, matriz))
    ls = lineas(out)
    assert codigo == 0
    assert ls[0] == "PENDIENTE SQL-01: " + P_SQL + " no existe todavia" and len(ls) == 2, ls
    assert "pendientes=1" in ls[-1] and "fallas=0" in ls[-1], ls[-1]


def test_cli_destinos_ok():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {P_SQL: SKILL_OK})
        matriz = escribir_matriz(raiz, [fila("SQL-01", destino="pasiva"), fila("SQL-02", destino="skill")])
        codigo, out, _ = correr(args("--destinos", "sql", raiz, matriz))
    ls = lineas(out)
    assert codigo == 0 and len(ls) == 1 and "fallas=0" in ls[0] and "pendientes=0" in ls[0], (codigo, ls)


def test_cli_severidad():
    with temporal() as raiz:
        instancia(raiz)
        escribir(raiz, {H_SQL: "SQL-01 CRITICAL 16\n\nSQL-02 solo CRITICAL\n"})
        matriz = escribir_matriz(raiz, [
            fila("SQL-01", destino="chequeo", severidad="CRITICAL", numeros="16"),
            fila("SQL-02", destino="chequeo", severidad="CRITICAL", numeros="151"),
            fila("SQL-03", destino="pasiva", severidad="WARNING"),
            fila("WEB-01", destino="chequeo", severidad="WARNING")])
        codigo, out, _ = correr(args("--severidad", "sql", raiz, matriz))
    ls = lineas(out)
    assert codigo == 1
    fs = [l for l in ls if l.startswith("FALLA")]
    assert len(fs) == 1 and fs[0].startswith("FALLA SQL-02:") and "numero 151" in fs[0], fs
    assert "PENDIENTE SQL-03: " + P_SQL + " no existe todavia" in ls, ls
    assert "fallas=1" in ls[-1] and "pendientes=1" in ls[-1] and "filas=3" in ls[-1], ls[-1]


def test_cli_utf8_en_consola_cp1252():
    with temporal() as raiz:
        instancia(raiz, capas={"diseño": {"extensions": [".md"], "rule_prefix": "DIS"}})
        matriz = escribir_matriz(raiz, [fila("DIS-01", destino="pasiva")])
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONPATH")}
        env["PYTHONIOENCODING"] = "cp1252"
        r = subprocess.run([sys.executable, str(_RUTA), "--destinos", "--capa", "diseño", "--matriz", matriz,
                            "--raiz", str(raiz)], capture_output=True, env=env, cwd=str(raiz))
    assert r.returncode == 0, r.stderr
    texto = r.stdout.decode("utf-8")
    assert "PENDIENTE DIS-01: .claude/skills/capa-diseño/SKILL.md no existe todavia" in texto, texto
    assert b"Traceback" not in r.stderr


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
