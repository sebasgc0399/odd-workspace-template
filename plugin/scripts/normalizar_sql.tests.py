import contextlib
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_RUTA = AQUI / "normalizar_sql.py"
SOBRANTES = []


def _cargar():
    spec = importlib.util.spec_from_file_location("normalizar_sql", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None


def _quitar(funcion, ruta, _error):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        funcion(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    raiz = Path(tempfile.mkdtemp(prefix="normalizar-sql-test-"))
    try:
        yield raiz
    finally:
        shutil.rmtree(raiz, onerror=_quitar)
        if raiz.exists():
            SOBRANTES.append(str(raiz))


def correr(argv):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            codigo = M.main(argv)
        except SystemExit as exc:
            codigo = exc.code
    return codigo, salida.getvalue(), error.getvalue()


def escribir(raiz, nombre, datos):
    p = Path(raiz) / nombre
    p.write_bytes(datos)
    return str(p)


def _texto(proceso):
    return proceso.stdout.decode("utf-8").replace(os.linesep, "\n")


LIMPIO = b"SET ANSI_NULLS ON\r\nGO\r\nSELECT 1\r\n\tFROM\tx\r\n"
LIMPIO_LF = LIMPIO.replace(b"\r\n", b"\n")


def test_check_archivo_limpio():
    with temporal() as raiz:
        p = escribir(raiz, "limpio.sql", LIMPIO)
        codigo, out, err = correr(["--check", p])
        assert codigo == 0, codigo
        assert out == "", out
        assert err == "", err
        assert Path(p).read_bytes() == LIMPIO


def test_check_reporta_bom():
    with temporal() as raiz:
        datos = b"\xef\xbb\xbf" + LIMPIO
        p = escribir(raiz, "bom.sql", datos)
        codigo, out, err = correr(["--check", p])
        assert codigo == 1, codigo
        assert "bom.sql" in out and "BOM" in out, out
        assert "CRLF" not in out, out
        assert Path(p).read_bytes() == datos


def test_check_reporta_lf_con_su_linea():
    with temporal() as raiz:
        datos = b"SET ANSI_NULLS ON\r\nGO\nSELECT 1\r\n"
        p = escribir(raiz, "lf.sql", datos)
        codigo, out, err = correr(["--check", p])
        assert codigo == 1, codigo
        assert out == "%s: fin de linea que no es CRLF en 1 lineas (primera: 2)\n" % p, out
        assert Path(p).read_bytes() == datos


def test_check_reporta_cr_suelto():
    with temporal() as raiz:
        p = escribir(raiz, "cr.sql", b"SELECT 1\rSELECT 2\r\n")
        codigo, out, err = correr(["--check", p])
        assert codigo == 1, codigo
        assert "CRLF" in out, out


def test_check_reporta_no_utf8():
    with temporal() as raiz:
        datos = b"SELECT 'ma\xf1ana'\r\n"
        p = escribir(raiz, "latin1.sql", datos)
        codigo, out, err = correr(["--check", p])
        assert codigo == 1, codigo
        assert out == "%s: no es UTF-8 valido (byte 10)\n" % p, out
        assert Path(p).read_bytes() == datos


def test_check_acepta_utf8_con_tildes():
    with temporal() as raiz:
        p = escribir(raiz, "tildes.sql", "SELECT 'mañana'\r\n".encode("utf-8"))
        codigo, out, err = correr(["--check", p])
        assert codigo == 0 and out == "", (codigo, out)


def test_check_reporta_indentacion_con_espacios():
    with temporal() as raiz:
        datos = b"BEGIN\r\n    SELECT 1\r\n\tSELECT 2\r\nEND\r\n"
        p = escribir(raiz, "esp.sql", datos)
        codigo, out, err = correr(["--tabs", "--check", p])
        assert codigo == 1, codigo
        assert out == "%s: indentacion solo con espacios (ancho de tab 4) en 1 lineas (primera: 2)\n" % p, out


def test_check_no_reporta_mezcla_tab_mas_espacios_como_indentacion_de_espacios():
    with temporal() as raiz:
        p = escribir(raiz, "mezcla.sql", b"BEGIN\r\n\t  SELECT 1\r\nEND\r\n")
        codigo, out, err = correr(["--tabs", "--check", p])
        assert codigo == 0 and out == "", (codigo, out)


def test_check_ignora_espacios_dentro_de_literal_y_comentario_de_bloque():
    with temporal() as raiz:
        datos = b"SELECT 'a\r\n    b'\r\n/*\r\n    nota\r\n*/\r\n"
        p = escribir(raiz, "lit.sql", datos)
        codigo, out, err = correr(["--tabs", "--check", p])
        assert codigo == 0 and out == "", (codigo, out)


def test_check_varios_archivos_exit_1_si_alguno_falla():
    with temporal() as raiz:
        a = escribir(raiz, "a.sql", LIMPIO)
        b = escribir(raiz, "b.sql", b"SELECT 1\n")
        codigo, out, err = correr(["--check", a, b])
        assert codigo == 1, codigo
        assert "b.sql" in out and "a.sql" not in out, out


def test_check_archivo_inexistente_es_error_de_uso():
    with temporal() as raiz:
        codigo, out, err = correr(["--check", str(Path(raiz) / "no-existe.sql")])
        assert codigo == 2, codigo
        assert "no-existe.sql" in err and out == "", (out, err)


def test_fix_saca_bom_y_lleva_a_crlf():
    with temporal() as raiz:
        p = escribir(raiz, "x.sql", b"\xef\xbb\xbfSELECT 1\nSELECT 2\r\nSELECT 3\rSELECT 4")
        codigo, out, err = correr(["--fix", p])
        assert codigo == 0, (codigo, err)
        assert Path(p).read_bytes() == b"SELECT 1\r\nSELECT 2\r\nSELECT 3\r\nSELECT 4"
        assert out == "%s: corregido\n" % p, out
        c2, o2, e2 = correr(["--check", p])
        assert c2 == 0 and o2 == "", o2


def test_fix_no_toca_ningun_otro_byte():
    with temporal() as raiz:
        p = escribir(raiz, "y.sql", "SELECT 'mañana'  \n\t  x\t\n".encode("utf-8"))
        correr(["--fix", p])
        assert Path(p).read_bytes() == "SELECT 'mañana'  \r\n\t  x\t\r\n".encode("utf-8")


def test_fix_archivo_limpio_no_se_reescribe():
    with temporal() as raiz:
        p = escribir(raiz, "ok.sql", LIMPIO)
        antes = os.stat(p).st_mtime_ns
        codigo, out, err = correr(["--fix", p])
        assert codigo == 0 and out == "", (codigo, out)
        assert Path(p).read_bytes() == LIMPIO
        assert os.stat(p).st_mtime_ns == antes


def test_fix_se_niega_si_no_es_utf8():
    with temporal() as raiz:
        datos = b"SELECT 'ma\xf1ana'\nGO\n"
        p = escribir(raiz, "latin1.sql", datos)
        otro = escribir(raiz, "otro.sql", b"SELECT 1\n")
        codigo, out, err = correr(["--fix", p, otro])
        assert codigo == 1, codigo
        assert Path(p).read_bytes() == datos
        assert err == "%s: no es UTF-8 valido, no se escribe nada\n" % p, err
        assert Path(otro).read_bytes() == b"SELECT 1\r\n"


def test_fix_convierte_espacios_multiplo_de_cuatro_en_tabs():
    with temporal() as raiz:
        p = escribir(raiz, "e.sql", b"BEGIN\r\n    SELECT 1\r\n        FROM x\r\nEND\r\n")
        codigo, out, err = correr(["--tabs", "--fix", p])
        assert codigo == 0, (codigo, err)
        assert Path(p).read_bytes() == b"BEGIN\r\n\tSELECT 1\r\n\t\tFROM x\r\nEND\r\n"


def test_fix_deja_intactas_indentaciones_que_no_son_multiplo_de_cuatro():
    with temporal() as raiz:
        datos = b"BEGIN\r\n      SELECT 1\r\n   SELECT 2\r\nEND\r\n"
        p = escribir(raiz, "e6.sql", datos)
        correr(["--tabs", "--fix", p])
        assert Path(p).read_bytes() == datos
        c, o, e = correr(["--tabs", "--check", p])
        assert c == 1 and "espacios" in o, (c, o)


def test_fix_deja_intactas_las_mezclas_de_tab_y_espacios():
    with temporal() as raiz:
        datos = b"BEGIN\r\n\t    SELECT 1\r\n    \tSELECT 2\r\nEND\r\n"
        p = escribir(raiz, "mix.sql", datos)
        correr(["--tabs", "--fix", p])
        assert Path(p).read_bytes() == datos


def test_fix_no_reindenta_dentro_de_literales_ni_bloques_de_comentario():
    with temporal() as raiz:
        p = escribir(raiz, "lit.sql", b"SELECT 'a\r\n    b'\r\n/*\r\n    nota\r\n*/\r\n    SELECT 1\r\n")
        correr(["--tabs", "--fix", p])
        assert Path(p).read_bytes() == b"SELECT 'a\r\n    b'\r\n/*\r\n    nota\r\n*/\r\n\tSELECT 1\r\n"


def test_fix_es_idempotente():
    with temporal() as raiz:
        p = escribir(raiz, "i.sql", b"\xef\xbb\xbfBEGIN\n    SELECT 1\nEND\n")
        correr(["--tabs", "--fix", p])
        una = Path(p).read_bytes()
        correr(["--tabs", "--fix", p])
        assert Path(p).read_bytes() == una


def test_uso_sin_modo_o_sin_archivos_es_error():
    with temporal() as raiz:
        p = escribir(raiz, "a.sql", LIMPIO)
        for argv, que in (([], "sin argumentos"), (["--check"], "--check sin archivos"),
                          (["--fix"], "--fix sin archivos"), ([p], "archivo sin modo"),
                          (["--check", "--fix", p], "los dos modos")):
            codigo, out, err = correr(argv)
            assert codigo == 2, "%s: exit 2 esperado, fue %r" % (que, codigo)


def test_fix_por_defecto_no_reindenta():
    with temporal() as raiz:
        p = escribir(raiz, "d.sql", b"\xef\xbb\xbfBEGIN\n    SELECT 1\nEND\n")
        codigo, out, err = correr(["--fix", p])
        assert codigo == 0, (codigo, err)
        assert Path(p).read_bytes() == b"BEGIN\r\n    SELECT 1\r\nEND\r\n"


def test_check_por_defecto_no_reporta_indentacion():
    with temporal() as raiz:
        p = escribir(raiz, "c.sql", b"BEGIN\r\n    SELECT 1\r\nEND\r\n")
        codigo, out, err = correr(["--check", p])
        assert codigo == 0 and out == "", (codigo, out)


def test_fin_crlf_explicito_es_igual_al_valor_por_defecto():
    with temporal() as raiz:
        datos = b"\xef\xbb\xbfSELECT 1\nSELECT 2\r\nSELECT 3\rSELECT 4"
        por_defecto = escribir(raiz, "a.sql", datos)
        explicito = escribir(raiz, "b.sql", datos)
        r1 = correr(["--check", por_defecto])
        r2 = correr(["--fin", "crlf", "--check", explicito])
        assert r1[0] == r2[0] == 1
        assert r1[1].replace(por_defecto, "X") == r2[1].replace(explicito, "X")
        correr(["--fix", por_defecto])
        correr(["--fin", "crlf", "--fix", explicito])
        assert Path(por_defecto).read_bytes() == Path(explicito).read_bytes() == b"SELECT 1\r\nSELECT 2\r\nSELECT 3\r\nSELECT 4"


def test_fin_lf_check_reporta_crlf_y_cr_con_su_linea_y_acepta_lf():
    with temporal() as raiz:
        limpio = escribir(raiz, "limpio.sql", LIMPIO_LF)
        codigo, out, err = correr(["--fin", "lf", "--check", limpio])
        assert codigo == 0 and out == "" and err == "", (codigo, out, err)
        codigo, out, err = correr(["--check", limpio])
        assert codigo == 1 and "no es CRLF" in out, (codigo, out)
        mixto = escribir(raiz, "mixto.sql", b"SELECT 1\nSELECT 2\r\nSELECT 3\rSELECT 4\n")
        codigo, out, err = correr(["--fin", "lf", "--check", mixto])
        assert codigo == 1, codigo
        assert out == "%s: fin de linea que no es LF en 2 lineas (primera: 2)\n" % mixto, out
        assert "CRLF" not in out


def test_fin_lf_check_sigue_reportando_el_bom_y_los_bytes_que_no_son_utf8():
    with temporal() as raiz:
        bom = escribir(raiz, "bom.sql", b"\xef\xbb\xbf" + LIMPIO_LF)
        codigo, out, err = correr(["--fin", "lf", "--check", bom])
        assert codigo == 1 and out == "%s: tiene BOM\n" % bom, (codigo, out)
        malo = escribir(raiz, "malo.sql", b"SELECT 'ma\xf1ana'\n")
        codigo, out, err = correr(["--fin", "lf", "--check", malo])
        assert codigo == 1 and out == "%s: no es UTF-8 valido (byte 10)\n" % malo, (codigo, out)


def test_fin_lf_fix_saca_el_bom_y_lleva_a_lf_sin_tocar_otro_byte():
    with temporal() as raiz:
        datos = b"\xef\xbb\xbfSELECT 'ma\xc3\xb1ana'  \r\n\t  x\t\rSELECT 3\r\nSELECT 4"
        p = escribir(raiz, "x.sql", datos)
        codigo, out, err = correr(["--fin", "lf", "--fix", p])
        assert codigo == 0, (codigo, err)
        assert Path(p).read_bytes() == "SELECT 'mañana'  \n\t  x\t\nSELECT 3\nSELECT 4".encode("utf-8")
        assert out == "%s: corregido\n" % p, out
        assert correr(["--fin", "lf", "--check", p])[0] == 0


def test_fin_lf_fix_no_reescribe_un_archivo_limpio_y_es_idempotente():
    with temporal() as raiz:
        p = escribir(raiz, "ok.sql", LIMPIO_LF)
        antes = os.stat(p).st_mtime_ns
        codigo, out, err = correr(["--fin", "lf", "--fix", p])
        assert codigo == 0 and out == "", (codigo, out)
        assert os.stat(p).st_mtime_ns == antes and Path(p).read_bytes() == LIMPIO_LF
        sucio = escribir(raiz, "sucio.sql", LIMPIO)
        correr(["--fin", "lf", "--fix", sucio])
        una = Path(sucio).read_bytes()
        correr(["--fin", "lf", "--fix", sucio])
        assert una == LIMPIO_LF and Path(sucio).read_bytes() == una


def test_fin_lf_fix_se_niega_si_no_es_utf8():
    with temporal() as raiz:
        datos = b"SELECT 'ma\xf1ana'\r\nGO\r\n"
        p = escribir(raiz, "latin1.sql", datos)
        codigo, out, err = correr(["--fin", "lf", "--fix", p])
        assert codigo == 1, codigo
        assert Path(p).read_bytes() == datos
        assert err == "%s: no es UTF-8 valido, no se escribe nada\n" % p, err


def test_fin_lf_con_tabs_convierte_la_indentacion_y_los_finales():
    with temporal() as raiz:
        p = escribir(raiz, "e.sql", b"BEGIN\r\n    SELECT 1\r\n        FROM x\r\nEND\r\n")
        codigo, out, err = correr(["--fin", "lf", "--tabs", "--fix", p])
        assert codigo == 0, (codigo, err)
        assert Path(p).read_bytes() == b"BEGIN\n\tSELECT 1\n\t\tFROM x\nEND\n"
        codigo, out, err = correr(["--fin", "lf", "--tabs", "--check", p])
        assert codigo == 0 and out == "", (codigo, out)


def test_fin_desconocido_es_error_de_uso_y_no_escribe():
    with temporal() as raiz:
        p = escribir(raiz, "a.sql", b"SELECT 1\n")
        for valor in ("cr", "CRLF", ""):
            codigo, out, err = correr(["--fin", valor, "--fix", p])
            assert codigo == 2, (valor, codigo)
            assert Path(p).read_bytes() == b"SELECT 1\n"
        codigo, out, err = correr(["--fin"])
        assert codigo == 2, codigo


def test_la_ayuda_documenta_el_modo_y_el_fin_de_linea():
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            M.main(["--help"])
        except SystemExit as exc:
            codigo = exc.code
    ayuda = salida.getvalue()
    assert codigo == 0 and error.getvalue() == ""
    for opcion in ("--check", "--fix", "--tabs", "--fin"):
        assert opcion in ayuda, opcion
    assert "crlf" in ayuda and "lf" in ayuda


def test_la_cli_como_proceso_sale_con_su_codigo_y_escribe_utf8_aunque_la_consola_no_lo_sea():
    with temporal() as raiz:
        sucio = escribir(raiz, "mañana.sql", b"SELECT 1\n")
        limpio = escribir(raiz, "limpio.sql", LIMPIO)
        entorno = dict(os.environ, PYTHONIOENCODING="cp1252")
        r = subprocess.run([sys.executable, str(_RUTA), "--check", limpio, sucio], capture_output=True, env=entorno)
        assert r.returncode == 1, r.returncode
        assert _texto(r) == "%s: fin de linea que no es CRLF en 1 lineas (primera: 1)\n" % sucio, r.stdout
        r = subprocess.run([sys.executable, str(_RUTA), "--fix", sucio], capture_output=True, env=entorno)
        assert r.returncode == 0 and _texto(r) == "%s: corregido\n" % sucio, (r.returncode, r.stdout)
        r = subprocess.run([sys.executable, str(_RUTA), "--check", str(Path(raiz) / "no-hay.sql")], capture_output=True, env=entorno)
        assert r.returncode == 2 and b"no-hay.sql" in r.stderr, (r.returncode, r.stderr)
        r = subprocess.run([sys.executable, str(_RUTA)], capture_output=True, env=entorno)
        assert r.returncode == 2, r.returncode


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
