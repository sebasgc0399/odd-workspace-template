import contextlib
import hashlib
import importlib
import json
import os
import shutil
import stat
import sys
import tempfile
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
SOBRANTES = []

HUELLA = "sha256:" + "a" * 64
OTRA_HUELLA = "sha256:" + "b" * 64
CORPUS = {"repo": "db", "commit": "0" * 40, "ruta": "src/sp"}


def m():
    return importlib.import_module("odd_ws.calibracion")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    raiz = Path(tempfile.mkdtemp(prefix="calibracion-test-"))
    try:
        yield raiz
    finally:
        shutil.rmtree(raiz, onexc=_quitar)
        if raiz.exists():
            SOBRANTES.append(str(raiz))


def entrada(huella=HUELLA, atrapa=True, aciertos=0, en_bloqueo=0, archivos=3, corpus=CORPUS, fecha="2026-11-20"):
    return {"huella": huella, "atrapa_su_sembrado": atrapa, "aciertos": aciertos, "aciertos_en_bloqueo": en_bloqueo,
            "archivos_del_corpus": archivos, "corpus": dict(corpus), "fecha": fecha}


def hallazgo(id_="SQL-01", modo="bloqueo", **extra):
    h = {"id": id_, "modo": modo, "severidad": "", "linea": 3, "fragmento": None, "mensaje": "mal"}
    h.update(extra)
    return h


def fuente(huella=HUELLA, sembrados=None, capa="sql"):
    return m().Fuente(capa, huella, {"SQL-01": "SELECT MAL"} if sembrados is None else sembrados)


def efectivo(h, registro, f=None, repos=None):
    return m().modo_efectivo(h, fuente() if f is None else f, registro, repos or {})


def registro_con(capas):
    return m().Registro(capas, None)


def test_la_ruta_del_registro_es_relativa_y_versionable():
    assert m().RUTA == ".claude/registro/calibracion.json"
    assert not m().RUTA.startswith("/") and "\\" not in m().RUTA and ":" not in m().RUTA


def test_la_huella_es_el_sha256_del_modulo_con_crlf_pasado_a_lf():
    lf, crlf = b"REGLAS = ()\ndef verificar(ctx):\n    return []\n", b"REGLAS = ()\r\ndef verificar(ctx):\r\n    return []\r\n"
    assert m().huella(lf) == "sha256:" + hashlib.sha256(lf).hexdigest()
    assert m().huella(crlf) == m().huella(lf), "el fin de línea no invalida la calibración"
    assert m().huella(lf + b" ") != m().huella(lf), "cualquier otro cambio sí"
    with temporal() as raiz:
        (raiz / "verificar_sql.py").write_bytes(crlf)
        assert m().huella_del_archivo(raiz / "verificar_sql.py") == m().huella(lf)


def test_un_bloqueo_calibrado_bloquea_tal_cual():
    h = hallazgo()
    resultado = efectivo(h, registro_con({"sql": {"SQL-01": entrada()}}))
    assert resultado == h and resultado["modo"] == "bloqueo" and m().sufijo(resultado) == "", resultado


def test_sin_registro_un_bloqueo_llega_como_aviso_sin_calibrar_con_el_comando():
    for registro in (registro_con({}), registro_con({"sql": {}}), registro_con({"web": {"SQL-01": entrada()}})):
        resultado = efectivo(hallazgo(), registro)
        assert resultado["modo"] == "aviso", resultado
        assert m().sufijo(resultado) == (" (aviso: sin calibrar; para que bloquee, correr "
                                         "`reglas.py --calibrar sql <carpeta> --guardar`)"), m().sufijo(resultado)


def test_un_modulo_que_cambio_da_calibracion_vieja_con_la_carpeta_del_corpus():
    repos = {"db": {"path": os.path.join(os.sep, "equipo", "db")}}
    resultado = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada()}}), fuente(huella=OTRA_HUELLA), repos)
    carpeta = os.path.join(repos["db"]["path"], "src", "sp")
    assert resultado["modo"] == "aviso"
    assert m().sufijo(resultado) == (" (aviso: calibración vieja; para que bloquee, correr "
                                     "`reglas.py --calibrar sql %s --guardar`)" % carpeta), m().sufijo(resultado)


def test_la_carpeta_del_comando_va_entre_comillas_con_espacios_y_sin_repo_conocido_queda_por_nombre():
    repos = {"db": {"path": os.path.join(os.sep, "mis repos", "db")}}
    vieja = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada()}}), fuente(huella=OTRA_HUELLA), repos)
    assert '--calibrar sql "%s" --guardar' % os.path.join(repos["db"]["path"], "src", "sp") in m().sufijo(vieja), m().sufijo(vieja)
    suelta = entrada(corpus={"repo": None, "commit": None, "ruta": "corpus"})
    sin_repo = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": suelta}}), fuente(huella=OTRA_HUELLA), repos)
    assert "--calibrar sql <carpeta> --guardar" in m().sufijo(sin_repo), m().sufijo(sin_repo)


def test_una_regla_sin_sembrado_o_un_modulo_sin_reglas_no_bloquea():
    registro = registro_con({"sql": {"SQL-01": entrada()}})
    for sembrados in ({}, {"SQL-01": None}, {"SQL-02": "SELECT MAL"}):
        resultado = efectivo(hallazgo(), registro, fuente(sembrados=sembrados))
        assert resultado["modo"] == "aviso", (sembrados, resultado)
        assert m().sufijo(resultado) == (" (aviso: sin calibrar; para que bloquee, declarar su `sembrado` en REGLAS y correr "
                                         "`reglas.py --calibrar sql <carpeta> --guardar`)"), m().sufijo(resultado)


def test_los_sembrados_salen_de_REGLAS_y_sin_REGLAS_no_hay_ninguno():
    Regla = lambda **kw: types.SimpleNamespace(**kw)
    modulo = types.SimpleNamespace(REGLAS=(Regla(id="A-01", sembrado="x"), Regla(id="A-02"), Regla(id="A-03", sembrado="  "),
                                           Regla(id="A-04", sembrado=3), Regla(sembrado="sin id")))
    assert m().sembrados(modulo) == {"A-01": "x", "A-02": None, "A-03": None, "A-04": None}
    assert m().sembrados(types.SimpleNamespace()) == {}
    assert m().sembrados(types.SimpleNamespace(REGLAS=42)) == {}
    assert m().sembrados(types.SimpleNamespace(REGLAS=None)) == {}


def test_una_calibracion_que_no_atrapa_su_sembrado_o_con_aciertos_en_bloqueo_no_bloquea():
    for datos, detalle in ((entrada(atrapa=False), "no atrapa su sembrado"),
                           (entrada(aciertos=4, en_bloqueo=2), "2 aciertos en bloqueo en el corpus")):
        resultado = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": datos}}))
        assert resultado["modo"] == "aviso", resultado
        assert m().sufijo(resultado) == (" (aviso: no pasó la calibración; %s: para que bloquee, arreglar la regla y correr "
                                         "`reglas.py --calibrar sql <carpeta> --guardar`)" % detalle), m().sufijo(resultado)
    con_avisos = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada(aciertos=5, en_bloqueo=0)}}))
    assert con_avisos["modo"] == "bloqueo", "los aciertos en aviso no le quitan el bloqueo"


def test_un_aviso_pedido_queda_igual_sin_mirar_el_registro():
    h = hallazgo(modo="aviso")
    for registro in (registro_con({}), m().Registro({}, "no se puede leer")):
        resultado = efectivo(h, registro)
        assert resultado is h and m().sufijo(resultado) == "", resultado


def test_un_hallazgo_sin_modo_o_con_otro_llega_como_aviso_con_el_motivo():
    registro = registro_con({"sql": {"SQL-01": entrada()}})
    for h in ({"id": "SQL-01", "mensaje": "mal"}, hallazgo(modo="Bloqueo"), hallazgo(modo=None), hallazgo(modo=["bloqueo"])):
        resultado = efectivo(h, registro)
        assert resultado["modo"] == "aviso", resultado
        assert m().sufijo(resultado) == " (aviso: modo inválido; el módulo tiene que devolver modo aviso o bloqueo)", resultado
        sin_fuente = m().modo_efectivo(h, None, registro, {})
        assert sin_fuente["modo"] == "aviso" and m().sufijo(sin_fuente) == m().sufijo(resultado), sin_fuente


def test_sin_fuente_el_modo_pedido_se_respeta_como_hasta_ahora():
    h = hallazgo()
    assert m().modo_efectivo(h, None, registro_con({}), {}) is h
    assert m().modo_efectivo(h, None, m().Registro({}, "roto"), {}) is h


def test_un_modulo_no_puede_fingir_el_motivo():
    falso = {"motivo": "inventado", "accion": "nada"}
    h = hallazgo(modo="aviso", **{m().CLAVE: falso})
    assert m().sufijo(m().modo_efectivo(h, fuente(), registro_con({}), {})) == ""
    calibrado = m().modo_efectivo(hallazgo(**{m().CLAVE: falso}), fuente(), registro_con({"sql": {"SQL-01": entrada()}}), {})
    assert calibrado["modo"] == "bloqueo" and m().sufijo(calibrado) == "", calibrado


def test_el_registro_ausente_es_vacio_y_no_esta_roto():
    with temporal() as raiz:
        assert m().cargar(raiz) == {}
        assert m().registro(raiz) == m().Registro({}, None)


def test_escribir_y_leer_ida_y_vuelta_ordenado_en_lf_sin_bom():
    with temporal() as raiz:
        capas = {"web": {"WEB-02": entrada(), "WEB-01": entrada(atrapa=False)}, "sql": {"SQL-01": entrada(archivos=0)}}
        m().escribir(raiz, capas)
        crudo = (raiz / m().RUTA).read_bytes()
        assert not crudo.startswith(b"\xef\xbb\xbf") and b"\r\n" not in crudo and crudo.endswith(b"}\n"), crudo[:40]
        datos = json.loads(crudo.decode("utf-8"))
        assert datos["version"] == m().VERSION == 1
        assert list(datos["capas"]) == ["sql", "web"] and list(datos["capas"]["web"]) == ["WEB-01", "WEB-02"], datos
        assert m().cargar(raiz) == capas
        assert sorted(os.listdir(raiz / ".claude" / "registro")) == ["calibracion.json"], "no deja el temporal"


def test_el_registro_roto_o_con_otra_forma_no_deja_bloquear_y_lo_dice():
    buena = entrada()
    rotos = {
        "no es json": "{roto",
        "no es un objeto": "[]",
        "otra version": json.dumps({"version": 2, "capas": {}}),
        "version booleana": json.dumps({"version": True, "capas": {}}),
        "clave desconocida": json.dumps({"version": 1, "capas": {}, "otra": 1}),
        "capas no es objeto": json.dumps({"version": 1, "capas": []}),
        "regla no es objeto": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": 3}}}),
        "falta una clave": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": {k: v for k, v in buena.items() if k != "huella"}}}}),
        "clave de mas": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, extra=1)}}}),
        "huella mal formada": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, huella="sha1:x")}}}),
        "atrapa no booleano": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, atrapa_su_sembrado="si")}}}),
        "aciertos negativos": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, aciertos=-1)}}}),
        "archivos booleanos": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, archivos_del_corpus=True)}}}),
        "ruta absoluta": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, corpus=dict(CORPUS, ruta="/abs"))}}}),
        "ruta de windows": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, corpus=dict(CORPUS, ruta="C:\\db"))}}}),
        "corpus sin commit": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, corpus={"repo": "db", "ruta": "x"})}}}),
        "fecha mal formada": json.dumps({"version": 1, "capas": {"sql": {"SQL-01": dict(buena, fecha="ayer")}}}),
    }
    for que, texto in rotos.items():
        with temporal() as raiz:
            (raiz / ".claude" / "registro").mkdir(parents=True)
            (raiz / m().RUTA).write_text(texto, encoding="utf-8")
            try:
                m().cargar(raiz)
            except m().RegistroRoto:
                pass
            else:
                raise AssertionError("cargar acepta un registro con %s" % que)
            registro = m().registro(raiz)
            assert registro.capas == {} and registro.roto, (que, registro)
            resultado = efectivo(hallazgo(), registro)
            assert resultado["modo"] == "aviso", (que, resultado)
            assert m().sufijo(resultado) == (" (aviso: registro de calibración roto; para que bloquee, arreglar o borrar "
                                             ".claude/registro/calibracion.json y correr "
                                             "`reglas.py --calibrar sql <carpeta> --guardar`)"), (que, m().sufijo(resultado))


def test_un_registro_con_bom_se_lee():
    with temporal() as raiz:
        (raiz / ".claude" / "registro").mkdir(parents=True)
        datos = {"version": 1, "capas": {"sql": {"SQL-01": entrada()}}}
        (raiz / m().RUTA).write_bytes(b"\xef\xbb\xbf" + json.dumps(datos).encode("utf-8"))
        assert m().cargar(raiz) == datos["capas"]


def test_aplicar_calcula_cada_grupo_con_su_fuente_y_lee_el_registro_de_la_raiz():
    with temporal() as raiz:
        m().escribir(raiz, {"sql": {"SQL-01": entrada()}})
        calibrado, otro, del_paquete = hallazgo(), hallazgo(id_="SQL-02"), hallazgo(id_="PAQ-01")
        resultado = m().aplicar([(fuente(sembrados={"SQL-01": "x", "SQL-02": "y"}), [calibrado, otro]), (None, [del_paquete])],
                                str(raiz), {})
        assert [(h["id"], h["modo"]) for h in resultado] == [("SQL-01", "bloqueo"), ("SQL-02", "aviso"), ("PAQ-01", "bloqueo")], resultado
        assert "sin calibrar" in m().sufijo(resultado[1]), resultado[1]


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
