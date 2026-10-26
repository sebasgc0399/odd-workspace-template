import contextlib
import copy
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent
sys.path.insert(0, str(SCRIPTS))
SOBRANTES = []


class Saltar(Exception):
    pass


def m():
    return importlib.import_module("odd_ws.tsql")


def _forzar_borrado(funcion, ruta, _error):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        funcion(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    base = Path(tempfile.mkdtemp(prefix="tsql-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, onerror=_forzar_borrado)
        if base.exists():
            SOBRANTES.append(str(base))


def crlf(texto):
    return texto.replace("\r\n", "\n").replace("\n", "\r\n")


PROCEDIMIENTO = """CREATE OR ALTER PROCEDURE [esq].[Proc_A]
\t@Id INT = NULL
AS
BEGIN
\tSET NOCOUNT ON
\tBEGIN TRY
\t\tSELECT 1
\tEND TRY
\tBEGIN CATCH
\t\tRAISERROR('fallo', 16, 1)
\tEND CATCH
END
"""


def ctx_de(raiz, nombre, texto, agregadas=None, limite=None, datos=None):
    ruta = Path(raiz) / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    crudo = datos if datos is not None else crlf(texto).encode("utf-8")
    ruta.write_bytes(crudo)
    decodificado = crudo.decode("utf-8", errors="replace")
    if decodificado.startswith("﻿"):
        decodificado = decodificado[1:]
    partes = [t.rstrip("\r") for t in decodificado.split("\n")]
    if partes and partes[-1] == "":
        partes.pop()
    todas = [(i + 1, t) for i, t in enumerate(partes)]
    elegidas = todas if agregadas is None else [(n, partes[n - 1]) for n in agregadas]
    return {"ruta": str(ruta), "bytes": crudo, "texto": decodificado, "agregadas": elegidas, "limite": limite}


def entrada(ruta, **extra):
    base = {"ruta": ruta, "errores": [], "comentarios": [], "dinamico": []}
    base.update(extra)
    return base


class Espia:
    def __init__(self, entradas=None, codigo=0, ok=True, excepcion=None, sin_salida=False, crudo=None):
        self.entradas = entradas or {}
        self.codigo = codigo
        self.ok = ok
        self.excepcion = excepcion
        self.sin_salida = sin_salida
        self.crudo = crudo
        self.llamadas = []

    def __call__(self, argumentos, **kwargs):
        lista = Path(argumentos[argumentos.index("-Lista") + 1])
        salida = Path(argumentos[argumentos.index("-Salida") + 1])
        rutas = lista.read_bytes().decode("utf-8").split("\n")
        self.llamadas.append({"rutas": rutas, "timeout": kwargs.get("timeout"), "env": kwargs.get("env"),
                              "tmp": lista.parent, "argumentos": list(argumentos)})
        if self.excepcion is not None:
            raise self.excepcion
        if not self.sin_salida:
            if self.crudo is not None:
                salida.write_bytes(self.crudo)
            else:
                archivos = []
                for ruta in rutas:
                    if ruta in self.entradas:
                        if self.entradas[ruta] is not None:
                            archivos.append(self.entradas[ruta])
                    else:
                        archivos.append(entrada(ruta))
                salida.write_bytes(json.dumps({"ok": self.ok, "dll": "x", "archivos": archivos}).encode("utf-8"))
        return subprocess.CompletedProcess(argumentos, self.codigo, b"", b"")


@contextlib.contextmanager
def helper_falso(espia):
    modulo = m()
    previo_run, previo_which = modulo.subprocess.run, modulo.shutil.which
    modulo.subprocess.run = espia
    modulo.shutil.which = lambda nombre: "powershell.exe"
    modulo.limpiar_cache()
    try:
        yield espia
    finally:
        modulo.subprocess.run = previo_run
        modulo.shutil.which = previo_which
        modulo.limpiar_cache()


@contextlib.contextmanager
def analisis_falso(analisis, motivo=None):
    modulo = m()
    previo = modulo.analizar
    modulo.analizar = lambda ctx: (analisis, motivo)
    try:
        yield
    finally:
        modulo.analizar = previo


_REAL = {}


def helper_real():
    ok, motivo = _scriptdom_tests().disponible()
    if not ok:
        raise Saltar(motivo)


def test_depurar_pasa_los_comentarios_a_espacios_y_conserva_largo_y_saltos():
    texto = "SELECT 1 -- nota 'x'\r\nSELECT 2 /* a\r\nb */ SELECT 3\r\n"
    esperado = ("SELECT 1 " + " " * len("-- nota 'x'") + "\r\nSELECT 2 " + " " * len("/* a") + "\r\n"
                + " " * len("b */") + " SELECT 3\r\n")
    resultado = m().depurar(texto)
    assert resultado == esperado, repr(resultado)
    assert len(resultado) == len(texto)
    assert [i for i, c in enumerate(resultado) if c == "\n"] == [i for i, c in enumerate(texto) if c == "\n"]


def test_depurar_comentarios_de_bloque_anidados_se_blanquean_enteros():
    texto = "a /* x /* y */ z */ b"
    resultado = m().depurar(texto)
    assert len(resultado) == len(texto)
    assert resultado.split() == ["a", "b"], repr(resultado)
    assert resultado.startswith("a ") and resultado.endswith(" b")


def test_depurar_no_toca_un_guion_doble_dentro_de_un_literal_si_no_se_piden_literales():
    texto = "SELECT '-- no /* soy' + 'it''s' -- si\n"
    resultado = m().depurar(texto)
    assert resultado == "SELECT '-- no /* soy' + 'it''s' " + " " * len("-- si") + "\n", repr(resultado)


def test_depurar_con_literales_blanquea_su_contenido_y_conserva_las_comillas():
    texto = "SELECT '-- no /* soy' + 'it''s' -- si\r\nSELECT 'a\r\nb'\r\n"
    resultado = m().depurar(texto, literales=True)
    esperado = ("SELECT '" + " " * len("-- no /* soy") + "' + '" + " " * 5 + "' " + " " * len("-- si")
                + "\r\nSELECT '" + " " + "\r\n" + " " + "'\r\n")
    assert resultado == esperado, repr(resultado)
    assert len(resultado) == len(texto)


def test_depurar_literal_sin_cerrar_llega_al_final_sin_perder_saltos():
    texto = "SELECT 'abc -- x\nSELECT 2"
    assert m().depurar(texto) == texto
    resultado = m().depurar(texto, literales=True)
    assert resultado == "SELECT '" + " " * len("abc -- x") + "\n" + " " * len("SELECT 2"), repr(resultado)


def test_depurar_comentario_de_bloque_sin_cerrar_llega_al_final_sin_perder_saltos():
    texto = "SELECT 1 /* abc\r\nxyz"
    resultado = m().depurar(texto)
    assert resultado == "SELECT 1 " + " " * len("/* abc") + "\r\n" + " " * 3, repr(resultado)


def test_depurar_texto_sin_comentarios_ni_literales_queda_igual():
    assert m().depurar(PROCEDIMIENTO) == PROCEDIMIENTO
    assert m().depurar("") == ""
    assert m().depurar("", literales=True) == ""


def test_linea_de_cuenta_los_saltos_hasta_la_posicion():
    texto = "a\nb\r\nc"
    assert m().linea_de(texto, 0) == 1
    assert m().linea_de(texto, texto.index("b")) == 2
    assert m().linea_de(texto, texto.index("c")) == 3
    assert m().linea_de(texto, len(texto)) == 3
    assert m().linea_de(texto, texto.index("\n")) == 1


def test_bloques_catch_devuelve_posiciones_y_lineas_del_bloque():
    s = m().depurar(crlf(PROCEDIMIENTO))
    ini = s.index("BEGIN CATCH")
    fin = s.index("END CATCH") + len("END CATCH")
    assert m().bloques_catch(s) == [(ini, fin, 9, 11)]


def test_bloques_catch_anidados_salen_ordenados_por_inicio():
    s = "BEGIN CATCH\nBEGIN CATCH\nEND CATCH\nEND CATCH"
    externo = (0, len(s), 1, 4)
    interno = (s.index("BEGIN CATCH", 1), s.index("END CATCH") + len("END CATCH"), 2, 3)
    assert m().bloques_catch(s) == [externo, interno]


def test_bloques_catch_sin_cerrar_llega_al_final():
    s = "SELECT 1\nBEGIN CATCH\nSELECT 2\nSELECT 3"
    assert m().bloques_catch(s) == [(s.index("BEGIN"), len(s), 2, 4)]


def test_bloques_catch_acepta_espacios_y_minusculas_e_ignora_un_cierre_suelto():
    s = "end catch\nbegin   catch\nend\tcatch"
    assert m().bloques_catch(s) == [(s.index("begin"), len(s), 2, 3)]
    assert m().bloques_catch("SELECT 1") == []
    assert m().bloques_catch("") == []


def test_bloques_catch_de_un_texto_depurado_ignora_los_comentarios():
    s = m().depurar("-- BEGIN CATCH\nSELECT 1\n/* BEGIN CATCH */\n")
    assert m().bloques_catch(s) == []


def _args(texto, tras):
    return m().argumentos(texto, texto.index(tras) + len(tras))


def test_argumentos_separa_a_profundidad_cero_y_respeta_parentesis_anidados():
    texto = "EXEC Proc_X @a, @b = 2, f(1, g(2, 3)), 'z'\nSELECT 1"
    assert _args(texto, "Proc_X") == ["@a", "@b = 2", "f(1, g(2, 3))", "'z'"]


def test_argumentos_termina_en_punto_y_coma_a_profundidad_cero():
    assert _args("EXEC Proc_X @a, @b; SELECT 1, 2", "Proc_X") == ["@a", "@b"]
    assert _args("EXEC Proc_X f(1;2), @b; SELECT 1, 2", "Proc_X") == ["f(1;2)", "@b"]


def test_argumentos_termina_en_la_palabra_que_abre_una_sentencia_al_inicio_de_linea():
    for palabra in ("END", "SET", "IF", "DECLARE", "RAISERROR", "THROW", "SELECT", "INSERT", "UPDATE", "EXEC",
                    "EXECUTE", "RETURN", "WHILE", "BEGIN", "select"):
        texto = "EXEC Proc_X @a,\n@b\n\t  %s algo, mas\n" % palabra
        assert _args(texto, "Proc_X") == ["@a", "@b"], palabra


def test_argumentos_no_termina_en_una_palabra_a_mitad_de_linea_ni_dentro_de_parentesis():
    assert _args("EXEC Proc_X @a, SELECT, @b", "Proc_X") == ["@a", "SELECT", "@b"]
    assert _args("EXEC Proc_X f(\nSELECT 1), @b", "Proc_X") == ["f(\nSELECT 1)", "@b"]
    assert _args("EXEC Proc_X @a,\nSELECTOR, @b", "Proc_X") == ["@a", "SELECTOR", "@b"]


def test_argumentos_sin_argumentos_devuelve_lista_vacia_y_una_coma_final_deja_un_vacio():
    assert _args("EXEC Proc_X\nSELECT 1", "Proc_X") == []
    assert _args("EXEC Proc_X ;", "Proc_X") == []
    assert _args("EXEC Proc_X @a,", "Proc_X") == ["@a", ""]
    assert _args("EXEC Proc_X   ", "Proc_X") == []


def test_analizar_devuelve_el_analisis_y_motivo_none():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        ctx = ctx_de(raiz, "a.sql", "SELECT 1\n")
        extra = {"comentarios": [{"linea": 1, "linea_fin": 1, "texto": "-- x"}]}
        espia.entradas[ctx["ruta"]] = entrada(ctx["ruta"], **extra)
        analisis, motivo = m().analizar(ctx)
        assert motivo is None
        assert analisis == entrada(ctx["ruta"], **extra)
        assert len(espia.llamadas) == 1
        argumentos = espia.llamadas[0]["argumentos"]
        assert argumentos[0] == "powershell.exe" and "-NoProfile" in argumentos
        assert argumentos[argumentos.index("-File") + 1] == str(m().RUTA_HELPER)
        assert espia.llamadas[0]["rutas"] == [ctx["ruta"]]


def test_analizar_conserva_los_errores_de_parseo_del_archivo():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        ctx = ctx_de(raiz, "roto.sql", "SELEC FROM\n")
        espia.entradas[ctx["ruta"]] = entrada(ctx["ruta"], errores=[{"linea": 1, "mensaje": "mal"}])
        analisis, motivo = m().analizar(ctx)
        assert motivo is None and analisis["errores"] == [{"linea": 1, "mensaje": "mal"}]


def test_analizar_cachea_por_ruta_y_huella_del_contenido():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        ctx = ctx_de(raiz, "a.sql", "SELECT 1\n")
        primero = m().analizar(ctx)
        segundo = m().analizar(dict(ctx))
        assert primero == segundo and len(espia.llamadas) == 1
        otro = ctx_de(raiz, "a.sql", "SELECT 2\n")
        m().analizar(otro)
        assert len(espia.llamadas) == 2
        gemelo = ctx_de(raiz, "b.sql", "SELECT 2\n")
        m().analizar(gemelo)
        assert len(espia.llamadas) == 3
        m().analizar(gemelo)
        m().analizar(otro)
        assert len(espia.llamadas) == 3


def test_analizar_no_muta_el_ctx_en_ningun_resultado():
    with temporal() as raiz:
        casos = {
            "analisis": Espia(),
            "sin_tiempo": Espia(excepcion=subprocess.TimeoutExpired("x", 1)),
            "sin_helper": Espia(codigo=1, sin_salida=True),
        }
        for nombre, espia in casos.items():
            with helper_falso(espia):
                ctx = ctx_de(raiz, nombre + ".sql", "SELECT 1\n", limite=time.monotonic() + 30)
                antes = copy.deepcopy(ctx)
                m().analizar(ctx)
                assert ctx == antes and set(ctx) == set(antes), nombre
        with helper_falso(Espia()):
            ctx = ctx_de(raiz, "vencido.sql", "SELECT 1\n", limite=time.monotonic() - 1)
            antes = copy.deepcopy(ctx)
            assert m().analizar(ctx) == (None, "sin_tiempo")
            assert ctx == antes and "ast_sin_tiempo" not in ctx


def test_analizar_con_el_limite_vencido_es_sin_tiempo_y_no_lanza_el_helper():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        for restante in (-1, 0.2):
            ctx = ctx_de(raiz, "a.sql", "SELECT 1\n", limite=time.monotonic() + restante)
            assert m().analizar(ctx) == (None, "sin_tiempo"), restante
        assert espia.llamadas == []


def test_analizar_con_el_limite_vencido_no_cachea_el_sin_tiempo_ni_deja_un_estado_pegado():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        vencido = ctx_de(raiz, "a.sql", "SELECT 1\n", limite=time.monotonic() - 1)
        assert m().analizar(vencido) == (None, "sin_tiempo")
        holgado = dict(vencido, limite=time.monotonic() + 30)
        analisis, motivo = m().analizar(holgado)
        assert motivo is None and analisis["ruta"] == vencido["ruta"]
        assert len(espia.llamadas) == 1
        otro = ctx_de(raiz, "b.sql", "SELECT 2\n")
        assert m().analizar(otro)[1] is None


def test_analizar_el_timeout_del_helper_es_lo_que_queda_del_limite_con_su_tope_como_maximo():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        for nombre, limite in (("a.sql", None), ("b.sql", time.monotonic() + 10), ("c.sql", time.monotonic() + 500)):
            m().analizar(ctx_de(raiz, nombre, "SELECT 1\n", limite=limite))
        tiempos = [llamada["timeout"] for llamada in espia.llamadas]
        assert tiempos[0] == m().TOPE_HELPER == 20
        assert 0 < tiempos[1] <= 10
        assert 15 < tiempos[2] <= 20


def test_analizar_el_timeout_del_helper_es_sin_tiempo_y_no_lo_marca_como_roto():
    with temporal() as raiz:
        ctx = ctx_de(raiz, "a.sql", "SELECT 1\n")
        with helper_falso(Espia(excepcion=subprocess.TimeoutExpired("x", 1))) as espia:
            assert m().analizar(ctx) == (None, "sin_tiempo")
            assert espia.llamadas[0]["tmp"].exists() is False
            nuevo = Espia()
            m().subprocess.run = nuevo
            otro = ctx_de(raiz, "b.sql", "SELECT 2\n")
            analisis, motivo = m().analizar(otro)
            assert motivo is None and analisis["ruta"] == otro["ruta"] and len(nuevo.llamadas) == 1


def test_analizar_un_helper_vencido_no_se_relanza_para_el_mismo_contenido():
    with temporal() as raiz, helper_falso(Espia(excepcion=subprocess.TimeoutExpired("x", 1))) as espia:
        for restante in (10, 500):
            ctx = ctx_de(raiz, "r%d.sql" % restante, "SELECT %d\n" % restante, limite=time.monotonic() + restante)
            assert m().analizar(ctx) == (None, "sin_tiempo"), restante
            assert m().analizar(dict(ctx)) == (None, "sin_tiempo"), restante
            assert m().analizar(dict(ctx, limite=None)) == (None, "sin_tiempo"), restante
        assert len(espia.llamadas) == 2, len(espia.llamadas)


def test_analizar_con_el_helper_ausente_es_sin_helper():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        previo = m().RUTA_HELPER
        m().RUTA_HELPER = Path(raiz) / "no-existe" / "scriptdom.ps1"
        try:
            assert m().analizar(ctx_de(raiz, "a.sql", "SELECT 1\n")) == (None, "sin_helper")
        finally:
            m().RUTA_HELPER = previo
        assert espia.llamadas == []


def test_analizar_sin_powershell_es_sin_helper():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        m().shutil.which = lambda nombre: None
        assert m().analizar(ctx_de(raiz, "a.sql", "SELECT 1\n")) == (None, "sin_helper")
        assert espia.llamadas == []


def test_analizar_una_falla_del_helper_lo_marca_roto_para_el_resto_del_proceso():
    fallas = {
        "codigo distinto de cero": Espia(codigo=3, sin_salida=True),
        "sin archivo de salida": Espia(sin_salida=True),
        "ok falso": Espia(ok=False),
        "json invalido": Espia(crudo=b"no es json"),
        "oserror": Espia(excepcion=OSError("no arranca")),
    }
    with temporal() as raiz:
        for nombre, falla in fallas.items():
            with helper_falso(falla):
                assert m().analizar(ctx_de(raiz, "a.sql", "SELECT 1\n")) == (None, "sin_helper"), nombre
                sano = Espia()
                m().subprocess.run = sano
                assert m().analizar(ctx_de(raiz, "b.sql", "SELECT 2\n")) == (None, "sin_helper"), nombre
                assert sano.llamadas == [], nombre
                m().limpiar_cache()
                assert m().analizar(ctx_de(raiz, "b.sql", "SELECT 2\n"))[1] is None, nombre
                assert len(sano.llamadas) == 1, nombre


def test_analizar_una_entrada_con_error_es_sin_helper_pero_no_rompe_a_las_demas():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        malo = ctx_de(raiz, "malo.sql", "SELECT 1\n")
        bueno = ctx_de(raiz, "bueno.sql", "SELECT 2\n")
        espia.entradas[malo["ruta"]] = {"ruta": malo["ruta"], "error": "no se pudo leer"}
        assert m().analizar(malo) == (None, "sin_helper")
        assert m().analizar(malo) == (None, "sin_helper")
        assert len(espia.llamadas) == 1
        assert m().analizar(bueno)[1] is None
        assert len(espia.llamadas) == 2


def test_analizar_un_archivo_que_el_helper_no_devuelve_es_sin_helper():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        ctx = ctx_de(raiz, "a.sql", "SELECT 1\n")
        espia.entradas[ctx["ruta"]] = None
        assert m().analizar(ctx) == (None, "sin_helper")


def test_analizar_el_entorno_del_helper_no_hereda_las_variables_de_un_hook_de_git():
    previo = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")}
    os.environ.update({"GIT_DIR": "x", "GIT_INDEX_FILE": "y", "GIT_WORK_TREE": "z"})
    try:
        with temporal() as raiz, helper_falso(Espia()) as espia:
            m().analizar(ctx_de(raiz, "a.sql", "SELECT 1\n"))
            env = espia.llamadas[0]["env"]
    finally:
        for clave, valor in previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
    assert not any(k in env for k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"))
    assert "PATH" in env or "Path" in env
    assert env["GIT_OPTIONAL_LOCKS"] == "0"


def test_analizar_borra_los_temporales_del_helper():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        privado = Path(raiz) / "tmp"
        privado.mkdir()
        previo = tempfile.tempdir
        tempfile.tempdir = str(privado)
        try:
            m().analizar(ctx_de(raiz, "a.sql", "SELECT 1\n"))
        finally:
            tempfile.tempdir = previo
        usado = espia.llamadas[0]["tmp"]
        assert usado.parent == privado and usado.name.startswith("tsql-scriptdom-"), usado
        assert list(privado.iterdir()) == []


def test_el_helper_vive_junto_al_modulo():
    assert m().RUTA_HELPER == Path(m().__file__).resolve().with_name("scriptdom.ps1")
    assert m().RUTA_HELPER.exists()


def test_precalcular_hace_una_sola_invocacion_para_los_pendientes_y_llena_el_cache():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        ctxs = [ctx_de(raiz, "%s.sql" % n, "SELECT %d\n" % i) for i, n in enumerate("abc")]
        m().analizar(ctxs[1])
        assert len(espia.llamadas) == 1
        assert m().precalcular(ctxs) is None
        assert len(espia.llamadas) == 2
        assert espia.llamadas[1]["rutas"] == [ctxs[0]["ruta"], ctxs[2]["ruta"]]
        assert espia.llamadas[1]["timeout"] == min(900, 30 + 2 * 2)
        for ctx in ctxs:
            analisis, motivo = m().analizar(ctx)
            assert motivo is None and analisis["ruta"] == ctx["ruta"]
        assert len(espia.llamadas) == 2
        m().precalcular(ctxs)
        m().precalcular([])
        assert len(espia.llamadas) == 2


def test_precalcular_no_repite_una_ruta_y_acota_el_timeout():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        ctx = ctx_de(raiz, "a.sql", "SELECT 1\n")
        m().precalcular([ctx, dict(ctx)])
        assert espia.llamadas[0]["rutas"] == [ctx["ruta"]]
        muchos = [ctx_de(raiz, "m%d.sql" % i, "SELECT %d\n" % i) for i in range(500)]
        m().precalcular(muchos)
        assert espia.llamadas[1]["timeout"] == 900


def test_precalcular_con_una_falla_no_cachea_nada_y_deja_al_helper_roto():
    with temporal() as raiz, helper_falso(Espia(codigo=1, sin_salida=True)) as espia:
        ctxs = [ctx_de(raiz, "a.sql", "SELECT 1\n"), ctx_de(raiz, "b.sql", "SELECT 2\n")]
        m().precalcular(ctxs)
        assert len(espia.llamadas) == 1
        assert m().analizar(ctxs[0]) == (None, "sin_helper")
        assert len(espia.llamadas) == 1


def test_precalcular_vencido_deja_sin_tiempo_a_su_lote_sin_contaminar_a_otro_archivo():
    with temporal() as raiz:
        ctxs = [ctx_de(raiz, "a.sql", "SELECT 1\n"), ctx_de(raiz, "b.sql", "SELECT 2\n")]
        with helper_falso(Espia(excepcion=subprocess.TimeoutExpired("x", 1))):
            m().precalcular(ctxs)
            sano = Espia()
            m().subprocess.run = sano
            for ctx in ctxs:
                assert m().analizar(dict(ctx, limite=None)) == (None, "sin_tiempo"), ctx["ruta"]
            assert sano.llamadas == []
            otro = ctx_de(raiz, "c.sql", "SELECT 3\n")
            analisis, motivo = m().analizar(otro)
            assert motivo is None and analisis["ruta"] == otro["ruta"]
            assert len(sano.llamadas) == 1


def test_precalcular_guarda_tambien_la_entrada_con_error_como_sin_helper():
    with temporal() as raiz, helper_falso(Espia()) as espia:
        malo = ctx_de(raiz, "malo.sql", "SELECT 1\n")
        bueno = ctx_de(raiz, "bueno.sql", "SELECT 2\n")
        espia.entradas[malo["ruta"]] = {"ruta": malo["ruta"], "error": "x"}
        m().precalcular([malo, bueno])
        assert m().analizar(malo) == (None, "sin_helper")
        assert m().analizar(bueno)[1] is None
        assert len(espia.llamadas) == 1


def test_sql_dinamico_devuelve_las_marcas_que_caen_en_lineas_agregadas_con_su_texto_recortado():
    marcas = [{"linea": 6, "tipo": "exec", "texto": "EXEC('a' + @x)"},
              {"linea": 7, "tipo": "sp_executesql", "texto": "EXEC sp_executesql @sql"}]
    analisis = entrada("x", dinamico=marcas)
    with temporal() as raiz, analisis_falso(analisis):
        ctx = ctx_de(raiz, "a.sql", PROCEDIMIENTO)
        assert m().sql_dinamico(ctx) == [(6, "BEGIN TRY"), (7, "SELECT 1")]
        solo = ctx_de(raiz, "a.sql", PROCEDIMIENTO, agregadas=[7])
        assert m().sql_dinamico(solo) == [(7, "SELECT 1")]
        ninguna = ctx_de(raiz, "a.sql", PROCEDIMIENTO, agregadas=[2])
        assert m().sql_dinamico(ninguna) == []
        fuera = dict(ctx, agregadas=[(99, "x")])
        assert m().sql_dinamico(dict(fuera, texto=ctx["texto"])) == []


def test_sql_dinamico_ignora_marcas_de_lineas_inexistentes_y_sin_linea():
    marcas = [{"linea": 0, "texto": "x"}, {"linea": 500, "texto": "x"}, {"texto": "x"}, {"linea": None}]
    with temporal() as raiz, analisis_falso(entrada("x", dinamico=marcas)):
        ctx = ctx_de(raiz, "a.sql", PROCEDIMIENTO)
        ctx["agregadas"] = ctx["agregadas"] + [(0, ""), (500, "")]
        assert m().sql_dinamico(ctx) == []


def test_sql_dinamico_sin_analisis_o_sin_marcas_devuelve_lista_vacia():
    with temporal() as raiz:
        ctx = ctx_de(raiz, "a.sql", PROCEDIMIENTO)
        for analisis, motivo in ((None, "sin_helper"), (None, "sin_tiempo"), (entrada("x"), None)):
            with analisis_falso(analisis, motivo):
                assert m().sql_dinamico(ctx) == []


def test_comentarios_agregados_usa_el_texto_del_comentario_si_es_de_una_linea():
    comentarios = [{"linea": 5, "linea_fin": 5, "texto": "  -- nota  "}, {"linea": 7, "texto": "-- sin fin"}]
    with temporal() as raiz, analisis_falso(entrada("x", comentarios=comentarios)):
        ctx = ctx_de(raiz, "a.sql", PROCEDIMIENTO)
        assert m().comentarios_agregados(ctx) == [(5, "-- nota"), (7, "-- sin fin")]
        solo = ctx_de(raiz, "a.sql", PROCEDIMIENTO, agregadas=[7])
        assert m().comentarios_agregados(solo) == [(7, "-- sin fin")]
        assert m().comentarios_agregados(ctx_de(raiz, "a.sql", PROCEDIMIENTO, agregadas=[1])) == []


def test_comentarios_agregados_de_bloque_marca_la_primera_linea_agregada_con_su_texto_de_linea():
    comentarios = [{"linea": 4, "linea_fin": 8, "texto": "/* a\r\n b\r\n c */"}]
    with temporal() as raiz, analisis_falso(entrada("x", comentarios=comentarios)):
        ctx = ctx_de(raiz, "a.sql", PROCEDIMIENTO)
        assert m().comentarios_agregados(ctx) == [(4, "BEGIN")]
        medio = ctx_de(raiz, "a.sql", PROCEDIMIENTO, agregadas=[6, 7])
        assert m().comentarios_agregados(medio) == [(6, "BEGIN TRY")]
        sin_linea = dict(ctx, agregadas=[(4, "x")], texto="una sola")
        assert m().comentarios_agregados(sin_linea) == [(4, "/* a")]


def test_comentarios_agregados_no_filtra_por_origen_la_politica_es_de_la_instancia():
    comentarios = [{"linea": 5, "linea_fin": 5, "texto": "-- nota"}]
    with temporal() as raiz, analisis_falso(entrada("x", comentarios=comentarios)):
        for origen in ("repo", "taller", "otro"):
            ctx = dict(ctx_de(raiz, "a.sql", PROCEDIMIENTO), origen=origen)
            assert m().comentarios_agregados(ctx) == [(5, "-- nota")], origen


def test_comentarios_agregados_sin_analisis_o_sin_comentarios_devuelve_lista_vacia():
    with temporal() as raiz:
        ctx = ctx_de(raiz, "a.sql", PROCEDIMIENTO)
        for analisis, motivo in ((None, "sin_helper"), (None, "sin_tiempo"), (entrada("x"), None)):
            with analisis_falso(analisis, motivo):
                assert m().comentarios_agregados(ctx) == []


def test_problemas_de_bytes_un_archivo_limpio_no_tiene_problemas():
    ok = crlf(PROCEDIMIENTO).encode("utf-8")
    assert m().problemas_de_bytes(ok) == []
    assert m().problemas_de_bytes(b"") == []
    assert m().problemas_de_bytes(crlf("SELECT 'estación'\n").encode("utf-8")) == []
    assert m().problemas_de_bytes(PROCEDIMIENTO.encode("utf-8"), fin="lf") == []


def test_problemas_de_bytes_detecta_el_bom_por_defecto():
    ok = crlf(PROCEDIMIENTO).encode("utf-8")
    assert m().problemas_de_bytes(b"\xef\xbb\xbf" + ok) == ["tiene BOM"]


def test_problemas_de_bytes_detecta_finales_de_linea_que_no_son_crlf():
    ok = crlf(PROCEDIMIENTO).encode("utf-8")
    esperado = ["tiene finales de línea que no son CRLF"]
    assert m().problemas_de_bytes(ok.replace(b"\r\n", b"\n")) == esperado
    assert m().problemas_de_bytes(ok.replace(b"\r\n", b"\n", 1)) == esperado
    assert m().problemas_de_bytes(ok.replace(b"\r\n", b"\r", 1)) == esperado
    assert m().problemas_de_bytes(ok.replace(b"\r\n", b"\r")) == esperado


def test_problemas_de_bytes_detecta_bytes_que_no_son_utf8():
    ok = crlf("SELECT 'estacion'\n").encode("utf-8")
    assert m().problemas_de_bytes(ok.replace(b"estacion", b"estaci\xf3n")) == ["no es UTF-8 válido"]


def test_problemas_de_bytes_junta_todos_los_problemas_en_orden():
    datos = b"\xef\xbb\xbfSELECT '\xf3'\nSELECT 2\r\n"
    assert m().problemas_de_bytes(datos) == ["tiene BOM", "tiene finales de línea que no son CRLF", "no es UTF-8 válido"]


def test_problemas_de_bytes_con_fin_lf_rechaza_crlf_y_cr_y_acepta_lf():
    assert m().problemas_de_bytes(b"SELECT 1\nSELECT 2\n", fin="lf") == []
    esperado = ["tiene finales de línea que no son LF"]
    assert m().problemas_de_bytes(b"SELECT 1\r\nSELECT 2\n", fin="lf") == esperado
    assert m().problemas_de_bytes(b"SELECT 1\rSELECT 2\n", fin="lf") == esperado
    assert m().problemas_de_bytes(b"SELECT 1\r\n", fin="lf") == esperado
    assert m().problemas_de_bytes(b"SELECT 1\n", fin="crlf") == ["tiene finales de línea que no son CRLF"]


def test_problemas_de_bytes_con_bom_verdadero_lo_exige():
    ok = crlf(PROCEDIMIENTO).encode("utf-8")
    assert m().problemas_de_bytes(b"\xef\xbb\xbf" + ok, bom=True) == []
    assert m().problemas_de_bytes(ok, bom=True) == ["no tiene BOM"]
    assert m().problemas_de_bytes(b"", bom=True) == ["no tiene BOM"]


def test_problemas_de_bytes_rechaza_un_fin_desconocido():
    for fin in ("cr", "CRLF", "", None):
        try:
            m().problemas_de_bytes(b"SELECT 1\r\n", fin=fin)
        except ValueError:
            continue
        raise AssertionError("debio rechazar fin=%r" % (fin,))


def test_la_superficie_de_tsql_es_la_declarada():
    paquete = importlib.import_module("odd_ws")
    esperado = ("analizar", "argumentos", "bloques_catch", "comentarios_agregados", "depurar", "linea_de",
                "precalcular", "problemas_de_bytes", "sql_dinamico")
    assert paquete.PUBLICO["tsql"] == esperado
    for nombre in esperado:
        assert callable(getattr(m(), nombre)), nombre


ALFA = ("CREATE PROCEDURE esq.Proc_Alfa\n    @Id INT,\n    @Nombre VARCHAR(50) = NULL\nAS\nBEGIN\n"
        "    SELECT 1\nEND\n")


def test_tipos_de_dinero_detecta_los_tipos_de_tsql_sin_distinguir_mayusculas():
    for linea in ("@Importe DECIMAL(18,2)", "campo money NOT NULL", "CAST(x AS numeric(10,2))", "@Cuota smallmoney"):
        assert m().TIPOS_DINERO.search(linea), linea


def test_tipos_de_dinero_no_detecta_otros_tipos_ni_palabras_que_los_contienen():
    for linea in ("@Id INT", "SELECT Nombre FROM esq.Tabla", "varchar(50)", "@Decimales INT", "moneda BIT"):
        assert not m().TIPOS_DINERO.search(linea), linea


def test_es_migracion_por_ddl_de_tabla_columna_indice_o_renombre():
    for agregadas in ("ALTER TABLE esq.Turno ADD Nuevo INT", "CREATE TABLE esq.Nueva (Id INT)", "DROP TABLE esq.Vieja",
                      "    ADD COLUMN y INT", "    DROP COLUMN y", "EXEC sp_rename 'a', 'b'",
                      "CREATE INDEX ix ON esq.T (Id)", "create unique nonclustered index ix on esq.T (Id)"):
        assert m().es_migracion(agregadas, "CREATE PROCEDURE p AS SELECT 1"), agregadas


def test_es_migracion_no_cuenta_tablas_temporales_ni_variables_de_tabla():
    cuerpo = "CREATE PROCEDURE p AS SELECT 1"
    for agregadas in ("CREATE TABLE #tmp (Id INT)", "DECLARE @t TABLE (Id INT)", "SELECT 1"):
        assert not m().es_migracion(agregadas, cuerpo), agregadas


def test_es_migracion_un_script_de_datos_sin_objeto_si_y_dentro_de_un_objeto_no():
    for agregadas in ("INSERT INTO esq.Tipo VALUES (1)", "UPDATE esq.Tipo SET A = 1", "DELETE FROM esq.Tipo",
                      "MERGE esq.Tipo AS t USING x ON 1 = 1"):
        assert m().es_migracion(agregadas, agregadas), agregadas
        assert not m().es_migracion(agregadas, "CREATE PROCEDURE esq.P AS\n" + agregadas), agregadas
    assert m().es_migracion("INSERT INTO esq.Tipo VALUES (1)", ""), "sin texto actual, decide por lo agregado"
    assert not m().es_migracion("CREATE PROCEDURE esq.P AS\nINSERT INTO esq.Tipo VALUES (1)", "")


def test_parametros_de_sp_nombres_tal_cual_y_tipos_normalizados():
    assert m().parametros_de_sp(ALFA) == {
        "proc_alfa": ("Proc_Alfa", {"@id": ("@Id", "int"), "@nombre": ("@Nombre", "varchar(50)=null")})}
    con_parentesis = "CREATE OR ALTER PROC [esq].[Proc_B] (@A INT OUTPUT, @B DECIMAL(18, 2) = 0) WITH RECOMPILE AS SELECT 1"
    assert m().parametros_de_sp(con_parentesis) == {
        "proc_b": ("Proc_B", {"@a": ("@A", "int out"), "@b": ("@B", "decimal(18,2)=0")})}
    ejecutar = "ALTER PROCEDURE esq.Proc_C @X INT WITH EXECUTE AS OWNER AS SELECT 1"
    assert m().parametros_de_sp(ejecutar) == {"proc_c": ("Proc_C", {"@x": ("@X", "int")})}
    coma = "CREATE PROCEDURE esq.Proc_D @L VARCHAR(9) = 'a,b', @M INT AS SELECT 1"
    assert m().parametros_de_sp(coma) == {"proc_d": ("Proc_D", {"@l": ("@L", "varchar(9)='a,b'"), "@m": ("@M", "int")})}
    con_as = "CREATE PROCEDURE esq.Proc_E\n    @Id AS INT\nAS\nSELECT 1\n"
    assert m().parametros_de_sp(con_as) == {"proc_e": ("Proc_E", {"@id": ("@Id", "as int")})}, "la línea AS cierra la firma"


def test_cambios_de_contrato_de_un_sp_parametro_agregado_quitado_tipo_default_y_salida():
    cambios = {
        "agregado": (ALFA.replace("@Id INT,", "@Id INT,\n    @Extra INT,"), "firma Proc_Alfa: +@Extra int"),
        "quitado": (ALFA.replace("    @Id INT,\n", ""), "firma Proc_Alfa: -@Id int"),
        "tipo": (ALFA.replace("@Id INT", "@Id BIGINT"), "firma Proc_Alfa: ~@Id: int -> bigint"),
        "default": (ALFA.replace("= NULL", "= 'x'"), "firma Proc_Alfa: ~@Nombre: varchar(50)=null -> varchar(50)='x'"),
        "salida": (ALFA.replace("@Id INT", "@Id INT OUTPUT"), "firma Proc_Alfa: ~@Id: int -> int out"),
    }
    for nombre, (nuevo, esperado) in cambios.items():
        assert m().cambios_de_contrato(ALFA, nuevo) == [esperado], (nombre, m().cambios_de_contrato(ALFA, nuevo))


def test_cambios_de_contrato_ignora_el_cuerpo_los_espacios_y_las_mayusculas():
    assert m().cambios_de_contrato(ALFA, ALFA.replace("SELECT 1", "SELECT 2")) == []
    assert m().cambios_de_contrato(ALFA, ALFA.replace("    @Id INT,", "@Id   int ,")) == []
    assert m().cambios_de_contrato(ALFA, crlf(ALFA)) == []


def test_cambios_de_contrato_un_sp_quitado_del_archivo_o_el_archivo_borrado():
    otro = "CREATE PROCEDURE esq.Proc_Otro\nAS\nSELECT 2\n"
    assert m().cambios_de_contrato(ALFA + otro, ALFA) == ["eliminado el SP Proc_Otro: su contrato desaparece"]
    assert m().cambios_de_contrato(ALFA + otro, None) == [
        "eliminado el SP Proc_Alfa: su contrato desaparece", "eliminado el SP Proc_Otro: su contrato desaparece"]


def test_cambios_de_contrato_de_un_archivo_nuevo_no_hay():
    assert m().cambios_de_contrato(None, ALFA) == []


def test_cambios_de_contrato_paths_y_alias_del_json_de_un_sp():
    entrada = "CREATE PROCEDURE esq.Proc_J\n    @Json NVARCHAR(MAX)\nAS\nBEGIN\n    SELECT * FROM OPENJSON(@Json) WITH (Id INT '$.id')\nEND\n"
    assert m().cambios_de_contrato(entrada, entrada.replace("'$.id'", "'$.venta.id'")) == [
        "JSON del SP: +path:$.venta.id; -path:$.id"]
    salida = "CREATE PROCEDURE esq.Proc_K\nAS\nBEGIN\n    SELECT Id AS idVenta FROM x FOR JSON PATH\nEND\n"
    assert m().cambios_de_contrato(salida, salida.replace("idVenta", "idNuevo")) == [
        "JSON del SP: +alias:idNuevo; -alias:idVenta"]
    assert m().cambios_de_contrato(salida, salida.replace("FROM x", "FROM y")) == []
    assert m().json_de_sp(ALFA) == set(), "sin FOR JSON ni OPENJSON no hay contrato de JSON"
    assert m().json_de_sp("SELECT '$.x' AS a") == set(), "un path suelto sin FOR JSON ni OPENJSON no cuenta"


def test_cambios_de_contrato_del_json_ignoran_alias_sin_for_json_reservadas_corchetes_y_comentarios():
    entrada = "CREATE PROCEDURE esq.Proc_J\nAS\nBEGIN\n    SELECT * FROM OPENJSON(@J) WITH (Id INT '$.id') AS j\nEND\n"
    assert m().cambios_de_contrato(entrada, entrada.replace("AS j", "AS k")) == [], "sin FOR JSON un alias no es contrato"
    salida = "CREATE PROCEDURE esq.Proc_K\nAS\nBEGIN\n    SELECT Id AS idVenta FROM x FOR JSON PATH\nEND\n"
    assert m().cambios_de_contrato(salida, salida.replace("AS\nBEGIN", "AS\nSET NOCOUNT ON;\nBEGIN")) == []
    assert m().cambios_de_contrato(salida, salida.replace("AS idVenta", "AS [idVenta]")) == []
    assert m().cambios_de_contrato(salida, salida.replace("FOR JSON PATH", "FOR JSON PATH -- AS aliasViejo")) == []


def test_un_guion_doble_dentro_de_un_literal_no_corta_la_firma():
    base = "CREATE PROCEDURE esq.Proc_S\n    @Sep VARCHAR(5) = '--', @A INT\nAS\nSELECT 1\n"
    nuevo = base.replace("@A INT", "@A INT, @B INT")
    assert m().cambios_de_contrato(base, nuevo) == ["firma Proc_S: +@B int"]


def test_un_encabezado_comentado_no_crea_un_sp_ni_un_objeto_fantasma():
    texto = "-- CREATE PROCEDURE esq.Proc_Viejo @Z INT AS\n/* ALTER VIEW esq.Vista_Vieja AS */\n" + ALFA
    assert list(m().parametros_de_sp(texto)) == ["proc_alfa"]
    assert [o["nombre"] for o in m().objetos(texto, None)] == ["Proc_Alfa"]


def test_objetos_juntan_lo_actual_y_la_base_y_marcan_lo_nuevo():
    base = ALFA + "CREATE VIEW esq.Vista_A AS SELECT 1\n"
    actual = ALFA + "CREATE FUNCTION [esq].[Fn_B] () RETURNS INT AS BEGIN RETURN 1 END\n"
    objetos = m().objetos(actual, base)
    assert [(o["nombre"], o["nuevo"]) for o in objetos] == [("Fn_B", True), ("Proc_Alfa", False), ("Vista_A", False)]
    assert all(o["ref"] == o["nombre"] for o in objetos)
    assert [(o["nombre"], o["nuevo"]) for o in m().objetos(None, base)] == [("Proc_Alfa", False), ("Vista_A", False)]
    assert m().objetos("SELECT 1", None) == []
    minusculas = ALFA.replace("Proc_Alfa", "proc_alfa")
    assert [(o["nombre"], o["nuevo"]) for o in m().objetos(ALFA, minusculas)] == [("Proc_Alfa", False), ("proc_alfa", False)]


def test_objetos_la_ere_de_definicion_la_entiende_git_grep_y_no_confunde_llamadas_ni_prefijos():
    with temporal() as raiz:
        archivos = {
            "def.sql": "create  or alter procedure [esq] . [Proc_Alfa]\n@Id INT AS SELECT 1\n",
            "def2.sql": "CREATE PROC Proc_Alfa AS SELECT 1\n",
            "llama.sql": "EXEC esq.Proc_Alfa @Id = 1\n",
            "prefijo.sql": "CREATE PROCEDURE esq.Proc_AlfaB AS SELECT 1\n",
            "trigger.sql": "CREATE TRIGGER esq.Proc_Alfa_T ON t AFTER INSERT AS SELECT 1\n",
        }
        for nombre, texto in archivos.items():
            (raiz / nombre).write_bytes(texto.encode("utf-8"))
        objeto = m().objetos(ALFA, None)[0]
        assert objeto["fijo"] is True and objeto["ci"] is True
        r = subprocess.run(["git", "grep", "--no-index", "-l", "-I", "-i", "-E", "-e", objeto["ere_def"], "--", "."],
                           cwd=str(raiz), capture_output=True,
                           env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
        assert r.returncode == 0, r.stderr
        assert sorted(r.stdout.decode("utf-8").split()) == ["def.sql", "def2.sql"], r.stdout


SQL_REAL = (
    "DECLARE @t VARCHAR(20) = '-- no soy comentario'\r\n"
    "SELECT 1 -- si soy\r\n"
    "DECLARE @q VARCHAR(50) = 'x'\r\n"
    "EXEC('SELECT ' + @q)\r\n"
    "EXEC sp_executesql N'SELECT 1'\r\n"
    "/* bloque\r\ndos */\r\n"
)


def _scriptdom_tests():
    if "modulo" not in _REAL:
        from odd_ws.comun import cargar_por_ruta
        _REAL["modulo"] = cargar_por_ruta(AQUI / "scriptdom.tests.py", "scriptdom_tests")
    return _REAL["modulo"]


def test_las_pruebas_reales_no_se_saltan_si_el_helper_falla_con_scriptdom_disponible():
    ok, motivo = _scriptdom_tests().disponible()
    if not ok:
        raise Saltar(motivo)
    previo = m().RUTA_HELPER
    with temporal() as raiz:
        roto = Path(raiz) / "scriptdom.ps1"
        roto.write_bytes(b"param($Lista, $Salida, $Dll)\r\n[IO.File]::WriteAllText($Salida, 'no es json')\r\nexit 0\r\n")
        m().RUTA_HELPER = roto
        try:
            helper_real()
        except Saltar as exc:
            raise AssertionError("un helper roto salto las pruebas reales: %s" % exc)
        finally:
            m().RUTA_HELPER = previo
            m().limpiar_cache()


def test_real_distingue_un_comentario_de_un_guion_doble_dentro_de_un_literal():
    helper_real()
    with temporal() as raiz:
        ctx = ctx_de(raiz, "a.sql", SQL_REAL)
        m().limpiar_cache()
        analisis, motivo = m().analizar(ctx)
        assert motivo is None and analisis["errores"] == []
        assert [(c["linea"], c["linea_fin"]) for c in analisis["comentarios"]] == [(2, 2), (6, 7)]
        assert m().comentarios_agregados(ctx) == [(2, "-- si soy"), (6, "/* bloque")]
        assert "no soy" not in json.dumps(analisis["comentarios"])
        solo = ctx_de(raiz, "a.sql", SQL_REAL, agregadas=[7])
        assert m().comentarios_agregados(solo) == [(7, "dos */")]
    m().limpiar_cache()


def test_real_marca_el_sql_dinamico_concatenado_y_no_el_estatico():
    helper_real()
    with temporal() as raiz:
        ctx = ctx_de(raiz, "a.sql", SQL_REAL)
        m().limpiar_cache()
        assert m().sql_dinamico(ctx) == [(4, "EXEC('SELECT ' + @q)")]
        assert m().sql_dinamico(ctx_de(raiz, "a.sql", SQL_REAL, agregadas=[2, 5])) == []
        limpio = ctx_de(raiz, "limpio.sql", PROCEDIMIENTO)
        assert m().sql_dinamico(limpio) == [] and m().comentarios_agregados(limpio) == []
    m().limpiar_cache()


def test_real_un_archivo_que_no_parsea_trae_errores_y_ninguna_marca_dinamica():
    helper_real()
    with temporal() as raiz:
        ctx = ctx_de(raiz, "roto.sql", "SELECT 1 -- antes\nSELEC FROM WHERE ((\nEXEC('a' + @b)\n")
        m().limpiar_cache()
        analisis, motivo = m().analizar(ctx)
        assert motivo is None and analisis["errores"] and analisis["dinamico"] == []
        assert any(e["linea"] == 2 for e in analisis["errores"])
        assert m().comentarios_agregados(ctx) == [(1, "-- antes")]
    m().limpiar_cache()


def test_real_precalcular_lanza_el_helper_una_sola_vez_para_varios_archivos():
    helper_real()
    with temporal() as raiz:
        ctxs = [ctx_de(raiz, "%s.sql" % n, SQL_REAL.replace("si soy", n)) for n in ("a", "b", "c")]
        m().limpiar_cache()
        real = subprocess.run
        lanzamientos = []

        def contar(*args, **kwargs):
            lanzamientos.append(args[0])
            return real(*args, **kwargs)

        m().subprocess.run = contar
        try:
            m().precalcular(ctxs)
            assert len(lanzamientos) == 1
            for n, ctx in zip("abc", ctxs):
                assert m().comentarios_agregados(ctx)[0] == (2, "-- " + n)
            assert len(lanzamientos) == 1
        finally:
            m().subprocess.run = real
    m().limpiar_cache()


def test_real_con_el_limite_vencido_no_lanza_el_helper():
    helper_real()
    with temporal() as raiz:
        ctx = ctx_de(raiz, "a.sql", SQL_REAL, limite=time.monotonic() - 1)
        m().limpiar_cache()
        assert m().analizar(ctx) == (None, "sin_tiempo")
        assert m().sql_dinamico(ctx) == [] and m().comentarios_agregados(ctx) == []
        sano = dict(ctx, limite=None)
        assert m().analizar(sano)[1] is None
    m().limpiar_cache()


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
