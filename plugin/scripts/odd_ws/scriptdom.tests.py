import contextlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PS1 = Path(__file__).resolve().parent / "scriptdom.ps1"
SOBRANTES = []


class Saltar(Exception):
    pass


def _quitar(funcion, ruta, _error):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        funcion(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    raiz = Path(tempfile.mkdtemp(prefix="scriptdom-test-"))
    try:
        yield raiz
    finally:
        shutil.rmtree(raiz, onerror=_quitar)
        if raiz.exists():
            SOBRANTES.append(str(raiz))


def powershell():
    for nombre in ("powershell.exe", "powershell"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


def correr(raiz, nombres_y_datos, extra=(), lista_texto=None):
    rutas = []
    for nombre, datos in nombres_y_datos:
        p = Path(raiz) / nombre
        p.write_bytes(datos)
        rutas.append(str(p))
    lista = Path(raiz) / "lista.txt"
    lista.write_bytes((lista_texto if lista_texto is not None else "\n".join(rutas) + "\n").encode("utf-8"))
    salida = Path(raiz) / "salida.json"
    r = subprocess.run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
                        "-Lista", str(lista), "-Salida", str(salida), *extra],
                       capture_output=True, timeout=90)
    crudo = salida.read_bytes() if salida.exists() else None
    try:
        datos = json.loads(crudo.decode("utf-8")) if crudo else None
    except ValueError:
        datos = None
    return r.returncode, datos, crudo, r.stderr.decode("utf-8", errors="replace")


CASOS = [
    ("comentarios.sql", ("SELECT '-- no soy comentario' -- si soy\r\n"
                         "SELECT 2 /* uno\r\ndos */ SELECT 3\r\n"
                         "-- mañana\r\n").encode("utf-8")),
    ("dinamico.sql", ("DECLARE @a VARCHAR(50) = 'x', @sql VARCHAR(MAX)\r\n"
                      "EXEC('SELECT ' + @a)\r\n"
                      "SET @sql = 'SELECT ' + @a\r\n"
                      "EXEC (@sql)\r\n"
                      "EXEC sp_executesql @sql\r\n"
                      "EXEC('SELECT 1')\r\n"
                      "EXEC sp_executesql N'SELECT 1'\r\n"
                      "SET @a = 'fijo'\r\n"
                      "EXEC esq.Proc_B @a\r\n").encode("utf-8")),
    ("estatico.sql", ("DECLARE @s VARCHAR(MAX) = 'SELECT 1'\r\n"
                      "EXEC (@s)\r\n"
                      "EXEC sp_executesql @s\r\n"
                      "EXEC sp_executesql N'SELECT 1'\r\n").encode("utf-8")),
    ("roto.sql", b"SELECT 1 -- comentario antes\r\nSELEC FROM WHERE ((\r\n"),
    ("limpio.sql", b"SELECT 1\r\n"),
]

_CACHE = {}


NOMBRE_DLL = "Microsoft.SqlServer.TransactSql.ScriptDom.dll"


def dll_en_la_maquina():
    candidatas = [Path(r"C:\Program Files\Microsoft SQL Server Management Studio 22\Release\Common7\IDE\Extensions\Application") / NOMBRE_DLL]
    for base in (r"C:\Program Files\Microsoft Visual Studio", r"C:\Program Files (x86)\Microsoft Visual Studio"):
        for version in ("18", "2022"):
            candidatas += Path(base, version).glob("*/Common7/IDE/Extensions/Microsoft/SQLCommon/" + NOMBRE_DLL)
    return [str(c) for c in candidatas if c.is_file()]


def disponible():
    if "disponible" not in _CACHE:
        if not PS1.exists():
            _CACHE["disponible"] = (True, "")
        elif powershell() is None:
            _CACHE["disponible"] = (False, "no hay powershell en el PATH")
        else:
            with temporal() as raiz:
                codigo = correr(raiz, [("a.sql", b"SELECT 1\r\n")])[0]
            if codigo == 3 and not dll_en_la_maquina():
                _CACHE["disponible"] = (False, "no se encontro %s" % NOMBRE_DLL)
            else:
                _CACHE["disponible"] = (True, "")
    return _CACHE["disponible"]


def requiere_helper():
    ok, motivo = disponible()
    if not ok:
        raise Saltar(motivo)


def corrida():
    if "r" not in _CACHE:
        with temporal() as raiz:
            codigo, datos, crudo, err = correr(raiz, CASOS)
            nombres = [Path(a["ruta"]).name for a in datos["archivos"]] if datos and datos.get("archivos") else []
            _CACHE["r"] = (codigo, datos, crudo, err, nombres)
    return _CACHE["r"]


def archivo(nombre):
    datos, nombres = corrida()[1], corrida()[4]
    for a in datos["archivos"]:
        if Path(a["ruta"]).name == nombre:
            return a
    raise AssertionError("el JSON no trae %s: %r" % (nombre, nombres))


def test_una_invocacion_devuelve_todos_los_archivos_en_orden():
    requiere_helper()
    codigo, datos, crudo, err, nombres = corrida()
    assert codigo == 0, "exit 0 esperado, fue %r: %r" % (codigo, err)
    assert datos is not None and datos.get("ok") is True
    assert nombres == [n for n, _ in CASOS], nombres
    assert isinstance(datos.get("dll"), str) and datos["dll"].lower().endswith("scriptdom.dll"), datos.get("dll")


def test_el_json_es_utf8_sin_bom():
    requiere_helper()
    crudo = corrida()[2]
    assert crudo is not None and not crudo.startswith(b"\xef\xbb\xbf")
    assert "mañana".encode("utf-8") in crudo, "las tildes viajan en UTF-8 crudo, no escapadas ni en cp1252"


def test_comentario_dentro_de_literal_no_es_comentario_y_fuera_si():
    requiere_helper()
    a = archivo("comentarios.sql")
    coms = a["comentarios"]
    por_linea = {c["linea"]: c for c in coms}
    assert len(coms) == 3, coms
    assert 1 in por_linea and por_linea[1]["texto"].strip() == "-- si soy", por_linea.get(1)
    assert "no soy" not in json.dumps(coms)
    assert 2 in por_linea and por_linea[2]["linea_fin"] == 3, por_linea.get(2)
    assert 4 in por_linea and por_linea[4]["texto"].strip() == "-- mañana", por_linea.get(4)
    assert a["errores"] == [], a["errores"]


def test_sql_dinamico_concatenado_se_marca_con_su_linea():
    requiere_helper()
    a = archivo("dinamico.sql")
    assert sorted(d["linea"] for d in a["dinamico"]) == [2, 4, 5], a["dinamico"]
    tipos = {d["linea"]: d["tipo"] for d in a["dinamico"]}
    assert tipos.get(2) == "exec" and tipos.get(4) == "exec" and tipos.get(5) == "sp_executesql", tipos
    assert all(d.get("texto") for d in a["dinamico"])


def test_sql_dinamico_que_no_se_concatena_no_se_marca():
    requiere_helper()
    assert archivo("estatico.sql")["dinamico"] == [], archivo("estatico.sql")["dinamico"]
    assert archivo("limpio.sql")["dinamico"] == [] and archivo("limpio.sql")["comentarios"] == []


def test_archivo_que_no_parsea_trae_errores_con_linea_y_conserva_los_comentarios():
    requiere_helper()
    a = archivo("roto.sql")
    assert len(a["errores"]) >= 1, a["errores"]
    assert all(isinstance(e["linea"], int) and e["mensaje"] for e in a["errores"]), a["errores"]
    assert any(e["linea"] == 2 for e in a["errores"]), a["errores"]
    assert [c["linea"] for c in a["comentarios"]] == [1], a["comentarios"]
    assert archivo("limpio.sql")["errores"] == []


def test_bom_utf8_en_el_archivo_no_se_confunde_con_codigo():
    requiere_helper()
    with temporal() as raiz:
        codigo, datos, crudo, err = correr(raiz, [("bom.sql", b"\xef\xbb\xbfSELECT 1 -- n\r\n")])
        assert codigo == 0 and datos["archivos"][0]["errores"] == [], (codigo, datos)
        assert [c["linea"] for c in datos["archivos"][0]["comentarios"]] == [1]


def test_sin_dll_sale_distinto_de_cero_con_json_de_error():
    requiere_helper()
    with temporal() as raiz:
        codigo, datos, crudo, err = correr(raiz, [("a.sql", b"SELECT 1\r\n")],
                                           extra=("-Dll", str(Path(raiz) / "no-existe.dll")))
        assert codigo == 3, "exit 3 esperado cuando no hay DLL, fue %r" % codigo
        assert datos is not None and datos.get("ok") is False and datos.get("error") == "sin_dll", datos
        assert datos.get("detalle"), "con el detalle de lo que se busco"


def test_lista_inexistente_es_error_de_uso():
    requiere_helper()
    with temporal() as raiz:
        salida = Path(raiz) / "salida.json"
        r = subprocess.run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1),
                            "-Lista", str(Path(raiz) / "no-hay.txt"), "-Salida", str(salida)],
                           capture_output=True, timeout=90)
        assert r.returncode == 2, "exit 2 esperado, fue %r" % r.returncode
        datos = json.loads(salida.read_bytes().decode("utf-8")) if salida.exists() else None
        assert datos is not None and datos.get("ok") is False, datos
        assert datos.get("error") == "lista_inexistente", datos


def test_archivo_ilegible_de_la_lista_no_tumba_a_los_demas():
    requiere_helper()
    with temporal() as raiz:
        ruta_ok = str(Path(raiz) / "ok.sql")
        falta = str(Path(raiz) / "falta.sql")
        codigo, datos, crudo, err = correr(raiz, [("ok.sql", b"SELECT 1 -- x\r\n")],
                                           lista_texto="%s\n%s\n" % (falta, ruta_ok))
        assert codigo == 0, (codigo, err)
        por = {Path(a["ruta"]).name: a for a in datos["archivos"]}
        assert "error" in por.get("falta.sql", {}), por.get("falta.sql")
        assert len(por.get("ok.sql", {}).get("comentarios", [])) == 1


def test_el_helper_existe_junto_a_la_biblioteca():
    assert PS1.exists(), PS1
    assert PS1.parent.name == "odd_ws"


def _helper_falso(raiz, cuerpo):
    ruta = Path(raiz) / "falso.ps1"
    ruta.write_bytes(("param($Lista, $Salida, $Dll)\r\n" + cuerpo + "\r\n").encode("utf-8"))
    return ruta


@contextlib.contextmanager
def con_helper(ps1, dlls=None):
    global PS1
    previo_ps1, previo_dlls = PS1, globals().get("dll_en_la_maquina")
    PS1 = ps1
    if dlls is not None:
        globals()["dll_en_la_maquina"] = lambda: dlls
    _CACHE.clear()
    try:
        yield
    finally:
        PS1 = previo_ps1
        if previo_dlls is None:
            globals().pop("dll_en_la_maquina", None)
        else:
            globals()["dll_en_la_maquina"] = previo_dlls
        _CACHE.clear()


def test_un_helper_que_escribe_basura_no_se_toma_como_scriptdom_ausente():
    if powershell() is None:
        raise Saltar("no hay powershell en el PATH")
    with temporal() as raiz:
        with con_helper(_helper_falso(raiz, "[IO.File]::WriteAllText($Salida, 'no es json')\r\nexit 0")):
            assert disponible() == (True, ""), disponible()


def test_un_sin_dll_con_la_dll_en_la_maquina_no_salta_la_suite():
    if powershell() is None:
        raise Saltar("no hay powershell en el PATH")
    cuerpo = "[IO.File]::WriteAllText($Salida, '{\"ok\":false,\"error\":\"sin_dll\",\"detalle\":\"x\"}')\r\nexit 3"
    with temporal() as raiz:
        with con_helper(_helper_falso(raiz, cuerpo), dlls=["C:/x/Microsoft.SqlServer.TransactSql.ScriptDom.dll"]):
            assert disponible() == (True, ""), disponible()


def test_sin_dll_en_la_maquina_la_suite_se_salta():
    if powershell() is None:
        raise Saltar("no hay powershell en el PATH")
    cuerpo = "[IO.File]::WriteAllText($Salida, '{\"ok\":false,\"error\":\"sin_dll\",\"detalle\":\"x\"}')\r\nexit 3"
    with temporal() as raiz:
        with con_helper(_helper_falso(raiz, cuerpo), dlls=[]):
            ok, motivo = disponible()
            assert ok is False and "ScriptDom" in motivo, (ok, motivo)


def _literal(texto):
    return "'%s'" % str(texto).replace("'", "''")


def correr_fuera_de_windows(raiz, extra=()):
    lista, salida = Path(raiz) / "lista.txt", Path(raiz) / "salida.json"
    (Path(raiz) / "a.sql").write_bytes(b"SELECT 1\r\n")
    lista.write_bytes((str(Path(raiz) / "a.sql") + "\n").encode("utf-8"))
    argumentos = ["-Lista", str(lista), "-Salida", str(salida), *extra]
    if os.name == "nt":
        orden = "$IsWindows = $false; & %s %s; exit $LASTEXITCODE" % (
            _literal(PS1), " ".join(a if a.startswith("-") else _literal(a) for a in argumentos))
        comando = [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", orden]
    else:
        comando = [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1), *argumentos]
    r = subprocess.run(comando, capture_output=True, timeout=90)
    datos = json.loads(salida.read_bytes().decode("utf-8")) if salida.exists() else None
    return r.returncode, datos, r.stderr.decode("utf-8", errors="replace")


def test_fuera_de_windows_no_busca_en_las_rutas_de_windows_y_sale_con_3():
    if powershell() is None:
        raise Saltar("no hay powershell en el PATH")
    with temporal() as raiz:
        codigo, datos, err = correr_fuera_de_windows(raiz)
        assert codigo == 3, "exit 3 esperado fuera de Windows sin -Dll, fue %r: %r %r" % (codigo, datos, err)
        assert datos.get("ok") is False and datos.get("error") == "sin_dll", datos
        assert "Program Files" not in datos["detalle"] and "-Dll" in datos["detalle"], datos
        dll = str(Path(raiz) / "no-existe.dll")
        codigo, datos, err = correr_fuera_de_windows(raiz, ("-Dll", dll))
        assert codigo == 3 and datos.get("error") == "sin_dll" and dll in datos["detalle"], (codigo, datos, err)


def test_la_dll_que_usa_el_helper_esta_entre_las_que_ve_la_suite():
    requiere_helper()
    usada = corrida()[1]["dll"]
    vistas = [os.path.normcase(os.path.abspath(d)) for d in dll_en_la_maquina()]
    assert os.path.normcase(os.path.abspath(usada)) in vistas, (usada, vistas)


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    pruebas = [(nombre, funcion) for nombre, funcion in globals().items() if nombre.startswith("test_") and callable(funcion)]
    fallas = 0
    saltadas = 0
    for nombre, prueba in pruebas:
        try:
            prueba()
            print(f"ok    {nombre}")
        except Saltar as motivo:
            saltadas += 1
            print(f"skip  {nombre}: {motivo}")
        except AssertionError as error:
            fallas += 1
            print(f"FALLA {nombre}: {error}")
        except Exception as error:
            fallas += 1
            print(f"ERROR {nombre}: {type(error).__name__}: {error}")
    if SOBRANTES:
        fallas += 1
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
    extra = f" ({saltadas} saltadas)" if saltadas else ""
    print(f"{len(pruebas) - fallas - saltadas}/{len(pruebas)} pruebas en verde{extra}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
