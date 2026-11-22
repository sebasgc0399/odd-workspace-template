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
REGLAS_PY = str(AQUI.parent / "reglas.py")
CORREGIR = "corregir los hallazgos y después correr %s"


def m():
    return importlib.import_module("odd_ws.calibracion")


def comando(carpeta="<carpeta>", capa="sql"):
    return '`%s "%s" --calibrar %s %s --guardar`' % (m().interprete(), REGLAS_PY, capa, carpeta)


def entre_comillas(*partes):
    return '"%s"' % os.path.join(*partes)


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


def efectivo(h, registro, f=None, repos=None, capas=None):
    return m().modo_efectivo(h, fuente() if f is None else f, registro, repos or {}, capas)


def registro_con(capas):
    return m().Registro(capas, None)


def test_un_bloqueo_con_un_id_que_no_es_texto_avisa_con_su_motivo_y_no_calla_el_hook():
    registro = registro_con({"sql": {"SQL-01": entrada()}})
    sin_id = {k: v for k, v in hallazgo().items() if k != "id"}
    for nombre, h in (("id lista", hallazgo(id_=["SQL-01"])), ("id numero", hallazgo(id_=7)), ("id vacio", hallazgo(id_="")),
                      ("sin id", sin_id)):
        resultado = efectivo(h, registro)
        assert resultado["modo"] == "aviso" and resultado[m().CLAVE]["motivo"] == m().ID_INVALIDO, (nombre, resultado)


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
        assert m().sufijo(resultado) == " (aviso: sin calibrar; para que bloquee, %s)" % CORREGIR % comando(), m().sufijo(resultado)


def test_el_comando_corre_el_reglas_py_del_plugin_con_su_ruta_absoluta_entre_comillas():
    assert m().REGLAS_PY == REGLAS_PY, (m().REGLAS_PY, REGLAS_PY)
    assert os.path.isabs(REGLAS_PY) and os.path.isfile(REGLAS_PY), REGLAS_PY
    resultado = efectivo(hallazgo(), registro_con({}))
    assert m().sufijo(resultado).endswith('correr `%s "%s" --calibrar sql <carpeta> --guardar`)' % (m().interprete(), REGLAS_PY)),         m().sufijo(resultado)


@contextlib.contextmanager
def solo_en_el_path(*nombres, ejecutable=None):
    with temporal() as carpeta:
        for nombre in nombres:
            ruta = carpeta / (nombre + (".exe" if os.name == "nt" else ""))
            ruta.write_bytes(b"")
            os.chmod(ruta, 0o755)
        path, actual = os.environ.get("PATH"), sys.executable
        os.environ["PATH"] = str(carpeta)
        if ejecutable is not None:
            sys.executable = ejecutable
        try:
            yield
        finally:
            sys.executable = actual
            if path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = path


def interprete_del_aviso():
    sufijo = m().sufijo(efectivo(hallazgo(), registro_con({})))
    fin = ' "%s" --calibrar sql <carpeta> --guardar`)' % REGLAS_PY
    assert sufijo.endswith(fin), sufijo
    return sufijo[sufijo.rindex("`", 0, len(sufijo) - len(fin)) + 1:len(sufijo) - len(fin)]


def test_el_comando_llama_por_su_nombre_al_python_del_path_para_correr_en_cualquier_terminal():
    if os.name == "nt":
        casos = ((("python",), "python"), (("python", "python3"), "python"), (("python3",), "python3"))
    else:
        casos = ((("python3",), "python3"), (("python", "python3"), "python3"))
    for nombres, esperado in casos:
        with solo_en_el_path(*nombres):
            assert interprete_del_aviso() == esperado, (nombres, interprete_del_aviso())


def test_sin_python_en_el_path_el_comando_usa_el_interprete_actual_entre_comillas_o_python3():
    con_espacios = os.path.join(os.sep, "mis pythons", "python.exe")
    for ejecutable, esperado in ((con_espacios, '"%s"' % con_espacios), ("", "python3")):
        with solo_en_el_path(ejecutable=ejecutable):
            assert interprete_del_aviso() == esperado, (ejecutable, interprete_del_aviso())
    if os.name != "nt":
        with solo_en_el_path("python"):
            assert interprete_del_aviso() == '"%s"' % sys.executable, "en Linux y macOS, python puede ser Python 2"


def test_el_aviso_pide_corregir_los_hallazgos_antes_de_calibrar():
    antes = "corregir los hallazgos y después correr `"
    casos = {
        "sin calibrar": efectivo(hallazgo(), registro_con({})),
        "calibración vieja": efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada()}}), fuente(huella=OTRA_HUELLA)),
        "sin sembrado": efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada()}}), fuente(sembrados={})),
        "registro roto": efectivo(hallazgo(), m().Registro({}, "roto")),
    }
    for que, resultado in casos.items():
        assert antes in m().sufijo(resultado), (que, m().sufijo(resultado))
    con_aciertos = m().sufijo(efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada(aciertos=1, en_bloqueo=1)}})))
    assert ("1 aciertos en bloqueo en el corpus: para que bloquee, corregir esos hallazgos, o arreglar la regla si son falsos "
            "positivos, y después correr `") in con_aciertos, con_aciertos


def test_un_modulo_que_cambio_da_calibracion_vieja_con_la_carpeta_del_corpus():
    repos = {"db": {"path": os.path.join(os.sep, "equipo", "db")}}
    resultado = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada()}}), fuente(huella=OTRA_HUELLA), repos)
    assert resultado["modo"] == "aviso"
    assert m().sufijo(resultado) == (" (aviso: calibración vieja; para que bloquee, %s)"
                                     % CORREGIR % comando(entre_comillas(repos["db"]["path"], "src", "sp"))), m().sufijo(resultado)


def test_las_rutas_del_comando_van_entre_comillas_aunque_tengan_espacios():
    repos = {"db": {"path": os.path.join(os.sep, "mis repos", "db")}}
    vieja = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada()}}), fuente(huella=OTRA_HUELLA), repos)
    assert m().sufijo(vieja).endswith(comando(entre_comillas(repos["db"]["path"], "src", "sp")) + ")"), m().sufijo(vieja)
    del_config = efectivo(hallazgo(), registro_con({}), repos=repos, capas={"sql": {"extensions": [".sql"], "repos": ["db"]}})
    assert m().sufijo(del_config).endswith(comando(entre_comillas(repos["db"]["path"])) + ")"), m().sufijo(del_config)


def test_una_carpeta_que_termina_en_barra_invertida_la_dobla_para_no_escapar_la_comilla():
    capas = {"sql": {"extensions": [".sql"], "repos": ["db"]}}
    resultado = efectivo(hallazgo(), registro_con({}), repos={"db": {"path": "D:\\"}}, capas=capas)
    assert m().sufijo(resultado).endswith(comando('"D:\\\\"') + ")"), m().sufijo(resultado)


def test_sin_regla_calibrada_la_carpeta_sale_del_primer_repo_de_la_capa():
    repos = {"db": {"path": os.path.join(os.sep, "equipo", "db")}, "app": {"path": os.path.join(os.sep, "equipo", "app")}}
    capas = {"sql": {"extensions": [".sql"], "repos": ["app", "db"]}, "web": {"extensions": [".cs"], "repos": ["db"]}}
    sin_registro = efectivo(hallazgo(), registro_con({}), repos=repos, capas=capas)
    assert m().sufijo(sin_registro) == (" (aviso: sin calibrar; para que bloquee, %s)"
                                        % CORREGIR % comando(entre_comillas(repos["app"]["path"]))), m().sufijo(sin_registro)
    suelta = entrada(corpus={"repo": None, "commit": None, "ruta": "corpus"})
    sin_repo = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": suelta}}), fuente(huella=OTRA_HUELLA), repos, capas)
    assert m().sufijo(sin_repo).endswith(comando(entre_comillas(repos["app"]["path"])) + ")"), m().sufijo(sin_repo)
    calibrada = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": entrada()}}), fuente(huella=OTRA_HUELLA), repos, capas)
    assert m().sufijo(calibrada).endswith(comando(entre_comillas(repos["db"]["path"], "src", "sp")) + ")"), \
        "una regla calibrada de la capa gana sobre la config: %s" % m().sufijo(calibrada)


def test_sin_regla_calibrada_ni_repo_de_la_capa_queda_carpeta():
    repos = {"db": {"path": os.path.join(os.sep, "equipo", "db")}}
    suelta = entrada(corpus={"repo": None, "commit": None, "ruta": "corpus"})
    for capas in ({}, {"sql": {"extensions": [".sql"]}}, {"sql": {"extensions": [".sql"], "repos": []}},
                  {"web": {"extensions": [".cs"], "repos": ["db"]}}):
        for registro in (registro_con({}), registro_con({"sql": {"SQL-01": suelta}})):
            resultado = efectivo(hallazgo(), registro, fuente(huella=OTRA_HUELLA), repos, capas)
            assert m().sufijo(resultado).endswith(comando() + ")"), (capas, m().sufijo(resultado))


def test_una_regla_sin_sembrado_o_un_modulo_sin_reglas_no_bloquea():
    registro = registro_con({"sql": {"SQL-01": entrada()}})
    for sembrados in ({}, {"SQL-01": None}, {"SQL-02": "SELECT MAL"}):
        resultado = efectivo(hallazgo(), registro, fuente(sembrados=sembrados))
        assert resultado["modo"] == "aviso", (sembrados, resultado)
        assert m().sufijo(resultado) == (" (aviso: sin calibrar; para que bloquee, declarar su `sembrado` en REGLAS, %s)"
                                         % CORREGIR % comando()), m().sufijo(resultado)


def test_los_sembrados_salen_de_REGLAS_y_sin_REGLAS_no_hay_ninguno():
    Regla = lambda **kw: types.SimpleNamespace(**kw)
    modulo = types.SimpleNamespace(REGLAS=(Regla(id="A-01", sembrado="x"), Regla(id="A-02"), Regla(id="A-03", sembrado="  "),
                                           Regla(id="A-04", sembrado=3), Regla(sembrado="sin id")))
    assert m().sembrados(modulo) == {"A-01": "x", "A-02": None, "A-03": None, "A-04": None}
    assert m().sembrados(types.SimpleNamespace()) == {}
    assert m().sembrados(types.SimpleNamespace(REGLAS=42)) == {}
    assert m().sembrados(types.SimpleNamespace(REGLAS=None)) == {}


def test_un_sembrado_puede_ser_una_ruta_relativa_con_su_texto():
    Regla = lambda **kw: types.SimpleNamespace(**kw)
    declarado = {"ruta": "Migrations/0001_alta.sql", "texto": "DROP TABLE t;"}
    modulo = types.SimpleNamespace(REGLAS=(Regla(id="A-01", sembrado="x"), Regla(id="A-02", sembrado=declarado),
                                           Regla(id="A-03", sembrado={"ruta": "vista.cshtml", "texto": "MALO"})))
    encontrados = m().sembrados(modulo)
    assert encontrados == {"A-01": "x", "A-02": declarado, "A-03": {"ruta": "vista.cshtml", "texto": "MALO"}}, encontrados
    assert encontrados["A-02"] is not declarado, "una copia: el módulo no la cambia después"
    registro = registro_con({"sql": {"SQL-01": entrada()}})
    resultado = efectivo(hallazgo(), registro, fuente(sembrados={"SQL-01": declarado}))
    assert resultado["modo"] == "bloqueo" and m().sufijo(resultado) == "", resultado


SEMBRADOS_INVALIDOS = {
    "sin ruta": {"texto": "x"},
    "sin texto": {"ruta": "a.sql"},
    "vacío": {},
    "ruta vacía": {"ruta": "", "texto": "x"},
    "ruta en blanco": {"ruta": "  ", "texto": "x"},
    "texto vacío": {"ruta": "a.sql", "texto": ""},
    "texto en blanco": {"ruta": "a.sql", "texto": " \n"},
    "ruta absoluta": {"ruta": "/Migrations/a.sql", "texto": "x"},
    "ruta con unidad": {"ruta": "C:/Migrations/a.sql", "texto": "x"},
    "ruta con barra invertida": {"ruta": "Migrations\\a.sql", "texto": "x"},
    "ruta que sube": {"ruta": "../a.sql", "texto": "x"},
    "ruta que sube adentro": {"ruta": "Migrations/../a.sql", "texto": "x"},
    "ruta con punto": {"ruta": "./a.sql", "texto": "x"},
    "ruta que termina en barra": {"ruta": "Migrations/", "texto": "x"},
    "ruta con barras dobles": {"ruta": "Migrations//a.sql", "texto": "x"},
    "ruta que no es texto": {"ruta": ["Migrations", "a.sql"], "texto": "x"},
    "texto que no es texto": {"ruta": "a.sql", "texto": b"x"},
    "clave de más": {"ruta": "a.sql", "texto": "x", "extension": ".sql"},
}


def test_un_sembrado_con_ruta_invalido_es_lo_mismo_que_no_tenerlo():
    Regla = lambda **kw: types.SimpleNamespace(**kw)
    registro = registro_con({"sql": {"SQL-01": entrada()}})
    sin_sembrado = efectivo(hallazgo(), registro, fuente(sembrados={"SQL-01": None}))
    for que, sembrado in SEMBRADOS_INVALIDOS.items():
        modulo = types.SimpleNamespace(REGLAS=(Regla(id="SQL-01", sembrado=sembrado), Regla(id="SQL-02", sembrado="y")))
        encontrados = m().sembrados(modulo)
        assert encontrados == {"SQL-01": None, "SQL-02": "y"}, (que, encontrados)
        resultado = efectivo(hallazgo(), registro, m().Fuente("sql", HUELLA, encontrados))
        assert resultado == sin_sembrado and resultado["modo"] == "aviso", (que, resultado)


def test_un_REGLAS_que_sale_con_SystemExit_al_leerse_deja_sin_sembrados_y_no_corta_al_que_llama():
    class SaleAlRecorrer:
        def __iter__(self):
            raise SystemExit(3)

    class SaleAlLeerElSembrado:
        id = "A-01"

        @property
        def sembrado(self):
            raise SystemExit("chau")

    for reglas in (SaleAlRecorrer(), (SaleAlLeerElSembrado(),)):
        assert m().sembrados(types.SimpleNamespace(REGLAS=reglas)) == {}, reglas
    f = m().fuente_del_paquete(Paquete(), types.SimpleNamespace(REGLAS=SaleAlRecorrer()))
    assert f == m().Fuente("sql", HUELLA, {}, "alfa"), f
    resultado = m().modo_efectivo(hallazgo(id_="ALF-01"), f, m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada()}}}), {})
    assert resultado["modo"] == "aviso" and "sin calibrar" in m().sufijo(resultado), resultado


def test_una_calibracion_que_no_atrapa_su_sembrado_o_con_aciertos_en_bloqueo_no_bloquea():
    for datos, detalle in ((entrada(atrapa=False), "no atrapa su sembrado: para que bloquee, arreglar la regla y correr"),
                           (entrada(aciertos=4, en_bloqueo=2), "2 aciertos en bloqueo en el corpus: para que bloquee, corregir esos "
                            "hallazgos, o arreglar la regla si son falsos positivos, y después correr")):
        resultado = efectivo(hallazgo(), registro_con({"sql": {"SQL-01": datos}}))
        assert resultado["modo"] == "aviso", resultado
        assert m().sufijo(resultado) == " (aviso: no pasó la calibración; %s %s)" % (detalle, comando()), m().sufijo(resultado)
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


def test_sin_fuente_un_bloqueo_no_bloquea():
    for registro in (registro_con({"sql": {"SQL-01": entrada()}}), m().Registro({}, "roto")):
        resultado = m().modo_efectivo(hallazgo(), None, registro, {})
        assert resultado["modo"] == "aviso", resultado
        assert m().sufijo(resultado) == " (aviso: sin calibrar; no viene de un módulo de capa ni de un paquete)", resultado
    h = hallazgo(modo="aviso")
    assert m().modo_efectivo(h, None, registro_con({}), {}) is h


DISPUTADA = (" (aviso: disputada; se cierra borrando .claude/registro/disputas/%s.md en el commit que arregla el chequeo, "
             "y después correr " + comando().replace("%", "%%") + ")")


def test_una_disputa_abierta_vuelve_a_aviso_una_regla_calibrada_y_dice_como_cerrarla():
    calibrada = registro_con({"sql": {"SQL-01": entrada()}})
    disputada = m().Registro(calibrada.capas, None, disputas=frozenset({"SQL-01"}))
    resultado = efectivo(hallazgo(), disputada)
    assert resultado["modo"] == "aviso" and m().sufijo(resultado) == DISPUTADA % "SQL-01", m().sufijo(resultado)
    otra = efectivo(hallazgo(), m().Registro(calibrada.capas, None, disputas=frozenset({"SQL-02"})))
    assert otra["modo"] == "bloqueo" and m().sufijo(otra) == "", "la disputa es de su ID y de ningún otro"
    sin_calibrar = efectivo(hallazgo(), m().Registro({}, None, disputas=frozenset({"SQL-01"})))
    assert m().sufijo(sin_calibrar) == DISPUTADA % "SQL-01", "la disputa es lo primero que se dice: es la decisión del usuario"


def test_un_id_que_no_es_texto_no_rompe_el_chequeo_de_disputas():
    for id_ in (5, ("SQL", 1)):
        resultado = efectivo(hallazgo(id_=id_), m().Registro({"sql": {}}, None, disputas=frozenset({"5"})))
        assert resultado["modo"] == "aviso", resultado


def test_las_disputas_se_leen_de_la_carpeta_y_borrar_el_archivo_la_cierra():
    with temporal() as raiz:
        m().escribir(raiz, {"sql": {"SQL-01": entrada()}})
        carpeta = raiz / ".claude" / "registro" / "disputas"
        carpeta.mkdir()
        (carpeta / "SQL-01.md").write_text("Abre: Ana\nBloqueo: SQL-01 en a.sql\nPor qué: falso positivo\n", encoding="utf-8")
        (carpeta / "sql-02.md").write_text("", encoding="utf-8")
        (carpeta / "SQL-03.txt").write_text("", encoding="utf-8")
        (carpeta / ".gitkeep").write_text("", encoding="utf-8")
        assert m().DISPUTAS == ".claude/registro/disputas"
        assert m().disputas(raiz) == frozenset({"SQL-01", "SQL-02"}), m().disputas(raiz)
        f = fuente(sembrados={"SQL-01": "x", "SQL-02": "y", "SQL-03": "z"})
        resultado = m().aplicar([(f, [hallazgo(), hallazgo(id_="SQL-02"), hallazgo(id_="SQL-03")])], str(raiz), {})
        assert [h["modo"] for h in resultado] == ["aviso", "aviso", "aviso"], resultado
        assert m().sufijo(resultado[0]) == DISPUTADA % "SQL-01" and m().sufijo(resultado[1]) == DISPUTADA % "SQL-02", resultado
        assert "sin calibrar" in m().sufijo(resultado[2]), "un archivo que no es .md no es una disputa"
        (carpeta / "SQL-01.md").unlink()
        resultado = m().aplicar([(f, [hallazgo()])], str(raiz), {})
        assert resultado[0]["modo"] == "bloqueo" and m().sufijo(resultado[0]) == "", resultado
        assert sorted(os.listdir(carpeta)) == [".gitkeep", "SQL-03.txt", "sql-02.md"], "ningún script escribe ni borra una disputa"


def test_una_carpeta_de_disputas_ilegible_deja_todo_en_aviso_y_lo_dice():
    with temporal() as raiz:
        m().escribir(raiz, {"sql": {"SQL-01": entrada()}})
        (raiz / ".claude" / "registro" / "disputas").write_text("no soy una carpeta", encoding="utf-8")
        registro = m().registro(raiz)
        assert registro.disputas_ilegibles and registro.capas, registro
        resultado = m().aplicar([(fuente(), [hallazgo()])], str(raiz), {})
        assert resultado[0]["modo"] == "aviso", resultado
        assert m().sufijo(resultado[0]) == (" (aviso: disputas ilegibles; para que bloquee, .claude/registro/disputas tiene que ser una "
                                            "carpeta legible, con un <ID>.md por disputa abierta)"), m().sufijo(resultado[0])
    with temporal() as raiz:
        assert m().disputas(raiz) == frozenset() and m().registro(raiz) == m().Registro({}, None), "sin carpeta no hay disputas"


class Paquete:
    def __init__(self, nombre="alfa", capa="sql", huella=HUELLA):
        self.nombre, self.capa, self.huella = nombre, capa, huella


def fuente_de_paquete(huella=HUELLA, sembrados=None, nombre="alfa"):
    modulo = types.SimpleNamespace(REGLAS=[types.SimpleNamespace(id=id_, sembrado=s)
                                           for id_, s in ({"ALF-01": "MALO"} if sembrados is None else sembrados).items()])
    return m().fuente_del_paquete(Paquete(nombre, "sql", huella), modulo)


def test_la_fuente_de_un_paquete_lleva_la_huella_de_su_lock_y_su_nombre():
    f = fuente_de_paquete()
    assert f == m().Fuente("sql", HUELLA, {"ALF-01": "MALO"}, "alfa"), f
    assert m().fuente_del_paquete(Paquete(), None) == m().Fuente("sql", HUELLA, {}, "alfa")
    assert m().Fuente("sql", HUELLA, {}).paquete is None, "la fuente de una capa no tiene paquete"


def test_una_regla_de_paquete_sin_calibrar_solo_avisa_y_calibrada_bloquea():
    del_paquete = hallazgo(id_="ALF-01")
    capa_calibrada = m().Registro({"sql": {"ALF-01": entrada()}}, None)
    resultado = m().modo_efectivo(del_paquete, fuente_de_paquete(), capa_calibrada, {})
    assert resultado["modo"] == "aviso", "la entrada de una capa no vale para un paquete: %r" % resultado
    assert m().sufijo(resultado) == " (aviso: sin calibrar; para que bloquee, %s)" % CORREGIR % comando(), resultado
    calibrado = m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada()}}})
    resultado = m().modo_efectivo(del_paquete, fuente_de_paquete(), calibrado, {})
    assert resultado is del_paquete and resultado["modo"] == "bloqueo", resultado
    otro_paquete = m().modo_efectivo(del_paquete, fuente_de_paquete(nombre="beta"), calibrado, {})
    assert otro_paquete["modo"] == "aviso", "la entrada de un paquete no vale para otro"
    en_otra_capa = m().Registro({}, None, {"web": {"alfa": {"ALF-01": entrada()}}})
    assert m().modo_efectivo(del_paquete, fuente_de_paquete(), en_otra_capa, {})["modo"] == "aviso", "ni en otra capa"


def test_un_lock_con_otra_huella_deja_vieja_la_calibracion_del_paquete():
    calibrado = m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada()}}})
    resultado = m().modo_efectivo(hallazgo(id_="ALF-01"), fuente_de_paquete(huella=OTRA_HUELLA), calibrado, {})
    assert resultado["modo"] == "aviso", resultado
    assert m().sufijo(resultado) == " (aviso: calibración vieja; para que bloquee, %s)" % CORREGIR % comando(), m().sufijo(resultado)


def test_un_paquete_sin_sembrado_o_que_no_pasa_lo_arregla_su_repo():
    calibrado = m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada()}}})
    resultado = m().modo_efectivo(hallazgo(id_="ALF-01"), fuente_de_paquete(sembrados={"ALF-01": None}), calibrado, {})
    assert m().sufijo(resultado) == (" (aviso: sin calibrar; para que bloquee, declarar su `sembrado` en REGLAS (en el repo del "
                                     "paquete alfa, con una etiqueta nueva), %s)" % CORREGIR % comando()), resultado
    no_paso = m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada(atrapa=False)}}})
    resultado = m().modo_efectivo(hallazgo(id_="ALF-01"), fuente_de_paquete(), no_paso, {})
    assert m().sufijo(resultado) == (" (aviso: no pasó la calibración; no atrapa su sembrado: para que bloquee, arreglar la regla (en el "
                                     "repo del paquete alfa, con una etiqueta nueva) y correr %s)" % comando()), resultado


def test_la_carpeta_del_comando_de_un_paquete_sale_de_su_corpus_o_del_de_su_capa():
    repos = {"db": {"path": os.path.join(os.sep, "equipo", "db")}}
    carpeta = comando(entre_comillas(repos["db"]["path"], "src", "sp"))
    del_paquete = m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada()}}})
    vieja = m().modo_efectivo(hallazgo(id_="ALF-01"), fuente_de_paquete(huella=OTRA_HUELLA), del_paquete, repos)
    assert m().sufijo(vieja).endswith(carpeta + ")"), m().sufijo(vieja)
    solo_la_capa = m().Registro({"sql": {"SQL-01": entrada()}}, None)
    sin_calibrar = m().modo_efectivo(hallazgo(id_="ALF-01"), fuente_de_paquete(), solo_la_capa, repos)
    assert m().sufijo(sin_calibrar).endswith(carpeta + ")"), m().sufijo(sin_calibrar)


def test_la_carpeta_de_un_paquete_sin_corpus_sale_del_primer_repo_de_su_capa():
    repos = {"db": {"path": os.path.join(os.sep, "equipo", "db")}}
    capas = {"sql": {"extensions": [".sql"], "repos": ["db"]}}
    for registro in (m().Registro({}, None), m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada(corpus=dict(CORPUS, repo=None))}}})):
        resultado = m().modo_efectivo(hallazgo(id_="ALF-01"), fuente_de_paquete(huella=OTRA_HUELLA), registro, repos, capas)
        assert resultado["modo"] == "aviso" and m().sufijo(resultado).endswith(comando(entre_comillas(repos["db"]["path"])) + ")"), \
            (registro, m().sufijo(resultado))


def test_una_disputa_vale_tambien_para_una_regla_de_paquete():
    calibrado = m().Registro({}, None, {"sql": {"alfa": {"ALF-01": entrada()}}}, frozenset({"ALF-01"}))
    resultado = m().modo_efectivo(hallazgo(id_="ALF-01"), fuente_de_paquete(), calibrado, {})
    assert resultado["modo"] == "aviso" and m().sufijo(resultado) == DISPUTADA % "ALF-01", m().sufijo(resultado)


def test_un_modulo_no_puede_fingir_el_motivo():
    falso = {"motivo": "inventado", "accion": "nada"}
    h = hallazgo(modo="aviso", **{m().CLAVE: falso})
    assert m().sufijo(m().modo_efectivo(h, fuente(), registro_con({}), {})) == ""
    calibrado = m().modo_efectivo(hallazgo(**{m().CLAVE: falso}), fuente(), registro_con({"sql": {"SQL-01": entrada()}}), {})
    assert calibrado["modo"] == "bloqueo" and m().sufijo(calibrado) == "", calibrado


def test_el_registro_ausente_es_vacio_y_no_esta_roto():
    with temporal() as raiz:
        assert m().cargar(raiz) == m().Calibradas({}, {})
        assert m().registro(raiz) == m().Registro({}, None)


def test_escribir_y_leer_ida_y_vuelta_ordenado_en_lf_sin_bom():
    with temporal() as raiz:
        capas = {"web": {"WEB-02": entrada(), "WEB-01": entrada(atrapa=False)}, "sql": {"SQL-01": entrada(archivos=0)}}
        m().escribir(raiz, capas)
        crudo = (raiz / m().RUTA).read_bytes()
        assert not crudo.startswith(b"\xef\xbb\xbf") and b"\r\n" not in crudo and crudo.endswith(b"}\n"), crudo[:40]
        datos = json.loads(crudo.decode("utf-8"))
        assert datos["version"] == m().VERSION == 1
        assert list(datos) == ["version", "capas"], "sin paquetes calibrados, el registro no nombra los paquetes"
        assert list(datos["capas"]) == ["sql", "web"] and list(datos["capas"]["web"]) == ["WEB-01", "WEB-02"], datos
        assert m().cargar(raiz) == m().Calibradas(capas, {})
        assert sorted(os.listdir(raiz / ".claude" / "registro")) == ["calibracion.json"], "no deja el temporal"


def test_los_paquetes_van_aparte_de_las_capas_por_capa_y_por_nombre():
    with temporal() as raiz:
        capas = {"sql": {"SQL-01": entrada()}}
        de_paquetes = {"sql": {"zeta": {"ZET-01": entrada()}, "alfa": {"ALF-02": entrada(), "ALF-01": entrada(atrapa=False)}},
                       "web": {}}
        m().escribir(raiz, capas, de_paquetes)
        datos = json.loads((raiz / m().RUTA).read_text(encoding="utf-8"))
        assert list(datos) == ["version", "capas", "paquetes"], datos
        assert list(datos["paquetes"]) == ["sql"], "una capa sin paquetes calibrados no aparece"
        assert list(datos["paquetes"]["sql"]) == ["alfa", "zeta"] and list(datos["paquetes"]["sql"]["alfa"]) == ["ALF-01", "ALF-02"], datos
        assert m().cargar(raiz) == m().Calibradas(capas, {"sql": de_paquetes["sql"]})
        assert m().registro(raiz).paquetes == {"sql": de_paquetes["sql"]}
        m().escribir(raiz, capas, {"sql": {}})
        assert "paquetes" not in json.loads((raiz / m().RUTA).read_text(encoding="utf-8"))


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
        "paquetes no es objeto": json.dumps({"version": 1, "capas": {}, "paquetes": []}),
        "capa de paquetes no es objeto": json.dumps({"version": 1, "capas": {}, "paquetes": {"sql": []}}),
        "nombre de paquete invalido": json.dumps({"version": 1, "capas": {}, "paquetes": {"sql": {"Alfa": {}}}}),
        "paquete no es objeto": json.dumps({"version": 1, "capas": {}, "paquetes": {"sql": {"alfa": 3}}}),
        "regla de paquete mal formada": json.dumps({"version": 1, "capas": {}, "paquetes": {"sql": {"alfa": {"ALF-01": dict(buena, huella="x")}}}}),
        "anidado sin fondo": '{"version": 1, "capas": %s}' % ("[" * 100000 + "]" * 100000),
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
            assert registro.capas == {} and registro.paquetes == {} and registro.roto, (que, registro)
            resultado = efectivo(hallazgo(), registro)
            assert resultado["modo"] == "aviso", (que, resultado)
            assert m().sufijo(resultado) == (" (aviso: registro de calibración roto; para que bloquee, arreglar o borrar "
                                             ".claude/registro/calibracion.json, %s)" % CORREGIR % comando()), (que, m().sufijo(resultado))


def test_un_registro_con_bom_se_lee():
    with temporal() as raiz:
        (raiz / ".claude" / "registro").mkdir(parents=True)
        datos = {"version": 1, "capas": {"sql": {"SQL-01": entrada()}}}
        (raiz / m().RUTA).write_bytes(b"\xef\xbb\xbf" + json.dumps(datos).encode("utf-8"))
        assert m().cargar(raiz) == m().Calibradas(datos["capas"], {})


def test_aplicar_calcula_cada_grupo_con_su_fuente_y_lee_el_registro_de_la_raiz():
    with temporal() as raiz:
        m().escribir(raiz, {"sql": {"SQL-01": entrada()}}, {"sql": {"alfa": {"ALF-01": entrada()}}})
        calibrado, otro, del_paquete, sin_calibrar = hallazgo(), hallazgo(id_="SQL-02"), hallazgo(id_="ALF-01"), hallazgo(id_="BET-01")
        resultado = m().aplicar([(fuente(sembrados={"SQL-01": "x", "SQL-02": "y"}), [calibrado, otro]),
                                 (fuente_de_paquete(), [del_paquete]),
                                 (fuente_de_paquete(nombre="beta", sembrados={"BET-01": "x"}), [sin_calibrar])], str(raiz), {})
        assert [(h["id"], h["modo"]) for h in resultado] == [("SQL-01", "bloqueo"), ("SQL-02", "aviso"), ("ALF-01", "bloqueo"),
                                                             ("BET-01", "aviso")], resultado
        assert "sin calibrar" in m().sufijo(resultado[1]) and "sin calibrar" in m().sufijo(resultado[3]), resultado


def test_aplicar_lleva_las_capas_de_la_config_hasta_el_comando():
    repos = {"db": {"path": os.path.join(os.sep, "equipo", "db")}}
    with temporal() as raiz:
        resultado = m().aplicar([(fuente(), [hallazgo()]), (fuente_de_paquete(), [hallazgo(id_="ALF-01")])], str(raiz), repos,
                                {"sql": {"extensions": [".sql"], "repos": ["db"]}})
    assert [h["modo"] for h in resultado] == ["aviso", "aviso"], resultado
    for h in resultado:
        assert m().sufijo(h).endswith(comando(entre_comillas(repos["db"]["path"])) + ")"), m().sufijo(h)


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
