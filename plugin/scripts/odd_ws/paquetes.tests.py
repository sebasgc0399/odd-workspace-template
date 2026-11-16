import hashlib
import importlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
SOBRANTES = []


def m():
    return importlib.import_module("odd_ws.paquetes")


def _forzar_borrado(funcion, ruta, _error):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        funcion(ruta)
    except Exception:
        pass


class Temporal:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="paquetes-"))
        return self.base

    def __exit__(self, *_):
        shutil.rmtree(self.base, onerror=_forzar_borrado)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


CAPAS = {"go": {"extensions": [".go"], "rule_prefix": "GO"}, "sql": {"extensions": [".sql"], "rule_prefix": "SQL"},
         "docs": {"extensions": [".md"]}}
COMMIT = "a" * 40
ARCHIVOS = {
    "verificar.py": "def verificar(ctx):\n    return []\n",
    "verificar.tests.py": "print('suite')\n",
    "matriz.csv": "id,origen,tipo,destino,severidad,numeros,resumen,motivo\n",
    "no-negociables.md": "- **GOB-01** no ignorar el error\n",
    "evidencia.md": "# Evidencia\n",
}


def manifiesto(nombre="go-basico", prefijo="GOB", api=1, **extra):
    datos = {"formato": 1, "nombre": nombre, "prefijo": prefijo, "odd_ws_api": api, "descripcion": "reglas de ejemplo"}
    datos.update(extra)
    return datos


def poner_paquete(raiz, nombre="go-basico", prefijo="GOB", api=1, archivos=None, datos=None):
    carpeta = Path(raiz) / ".claude" / "reglas" / "paquetes" / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    for archivo, texto in {**ARCHIVOS, **(archivos or {})}.items():
        if texto is None:
            continue
        (carpeta / archivo).write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)
    contenido = manifiesto(nombre, prefijo, api) if datos is None else datos
    (carpeta / "odd-ws-paquete.json").write_text(json.dumps(contenido), encoding="utf-8")
    return carpeta


def entrada(raiz, nombre="go-basico", capa="go", prefijo="GOB", huella=None):
    carpeta = Path(raiz) / ".claude" / "reglas" / "paquetes" / nombre
    return {"capa": capa, "prefijo": prefijo, "fuente": "https://example.com/reglas-go.git", "etiqueta": "v1.0.0",
            "commit": COMMIT, "huella": huella or m().huella(str(carpeta))}


def poner_lock(raiz, paquetes, version=1):
    ruta = Path(raiz) / ".claude" / "reglas" / "paquetes.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = paquetes if isinstance(paquetes, str) else json.dumps({"version": version, "paquetes": paquetes})
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def instancia_con(base, *paquetes):
    lock = {}
    for nombre, capa, prefijo in paquetes:
        poner_paquete(base, nombre, prefijo)
        lock[nombre] = entrada(base, nombre, capa, prefijo)
    poner_lock(base, lock)
    return lock


def huella_de_la_especificacion(archivos):
    h = hashlib.sha256()
    for nombre in sorted(archivos):
        contenido = archivos[nombre].replace(b"\r\n", b"\n")
        h.update(nombre.encode("utf-8") + b"\0" + str(len(contenido)).encode("ascii") + b"\0" + contenido)
    return "sha256:" + h.hexdigest()


def test_las_rutas_y_los_archivos_del_paquete():
    assert m().LOCK == ".claude/reglas/paquetes.json"
    assert m().carpeta("go-basico") == ".claude/reglas/paquetes/go-basico"
    assert m().MANIFIESTO == "odd-ws-paquete.json"
    assert m().OBLIGATORIOS == ("odd-ws-paquete.json", "verificar.py", "verificar.tests.py", "matriz.csv", "no-negociables.md",
                                "evidencia.md")
    assert m().LISTA_BLANCA == m().OBLIGATORIOS + ("LICENSE",)


def test_no_es_parte_de_la_api_publica():
    assert "paquetes" not in importlib.import_module("odd_ws").PUBLICO


def test_sin_lock_no_hay_paquetes_ni_activos():
    with Temporal() as base:
        assert m().leer_lock(str(base)) is None
        assert m().activos(str(base), "go", CAPAS) == []


def test_el_lock_valido_se_lee_y_cada_capa_da_sus_paquetes_por_nombre():
    with Temporal() as base:
        instancia_con(base, ("zeta", "go", "ZET"), ("alfa", "go", "ALF"), ("tsql-base", "sql", "TSB"))
        lock = m().leer_lock(str(base))
        assert sorted(lock) == ["alfa", "tsql-base", "zeta"], lock
        alfa = lock["alfa"]
        assert (alfa.nombre, alfa.capa, alfa.prefijo, alfa.etiqueta, alfa.commit) == ("alfa", "go", "ALF", "v1.0.0", COMMIT), alfa
        assert alfa.fuente == "https://example.com/reglas-go.git" and alfa.huella.startswith("sha256:"), alfa
        assert [p.nombre for p in m().de_la_capa(lock, "go")] == ["alfa", "zeta"]
        assert [p.nombre for p in m().de_la_capa(lock, "sql")] == ["tsql-base"]
        assert m().de_la_capa(lock, "docs") == []


def test_un_lock_vacio_es_valido():
    with Temporal() as base:
        poner_lock(base, {})
        assert m().leer_lock(str(base)) == {}


def _lock_con(**cambios):
    entrada_ = {"capa": "go", "prefijo": "GOB", "fuente": "https://example.com/r.git", "etiqueta": "v1", "commit": COMMIT,
                "huella": "sha256:" + "0" * 64}
    entrada_.update(cambios)
    return {"version": 1, "paquetes": {"go-basico": {k: v for k, v in entrada_.items() if v is not None}}}


def test_un_lock_roto_dice_por_que():
    casos = [
        ("{no es json", "JSON"),
        ("[]", "objeto"),
        (json.dumps({"version": 2, "paquetes": {}}), "version 2"),
        (json.dumps({"version": True, "paquetes": {}}), "version True"),
        (json.dumps({"paquetes": {}}), "version None"),
        (json.dumps({"version": 1}), "paquetes"),
        (json.dumps({"version": 1, "paquetes": []}), "paquetes"),
        (json.dumps({"version": 1, "paquetes": {}, "otra": 1}), "otra"),
        (json.dumps({"version": 1, "paquetes": {"Go_Basico": _lock_con()["paquetes"]["go-basico"]}}), "Go_Basico"),
        (json.dumps({"version": 1, "paquetes": {"go-basico": "no"}}), "go-basico"),
        (json.dumps(_lock_con(capa=None)), "capa"),
        (json.dumps(_lock_con(capa="")), "capa"),
        (json.dumps(_lock_con(prefijo="gob")), "prefijo"),
        (json.dumps(_lock_con(fuente=3)), "fuente"),
        (json.dumps(_lock_con(etiqueta="")), "etiqueta"),
        (json.dumps(_lock_con(commit="abc")), "commit"),
        (json.dumps(_lock_con(commit="A" * 40)), "commit"),
        (json.dumps(_lock_con(huella="md5:" + "0" * 32)), "huella"),
        (json.dumps(_lock_con(extra="x")), "extra"),
    ]
    with Temporal() as base:
        for texto, rastro in casos:
            poner_lock(base, texto)
            try:
                m().leer_lock(str(base))
            except m().LockRoto as error:
                assert rastro in str(error), (texto, str(error))
            else:
                raise AssertionError("no lo rechazó: %s" % texto)


def test_dos_paquetes_con_el_mismo_prefijo_rompen_el_lock():
    with Temporal() as base:
        a, b = _lock_con()["paquetes"]["go-basico"], dict(_lock_con()["paquetes"]["go-basico"])
        poner_lock(base, {"go-basico": a, "go-extra": b})
        try:
            m().leer_lock(str(base))
        except m().LockRoto as error:
            assert "GOB" in str(error) and "go-basico" in str(error) and "go-extra" in str(error), str(error)
        else:
            raise AssertionError("dos paquetes con el prefijo GOB")


def test_un_lock_que_no_se_puede_leer_es_lock_roto():
    with Temporal() as base:
        (base / ".claude" / "reglas" / "paquetes.json").mkdir(parents=True)
        try:
            m().leer_lock(str(base))
        except m().LockRoto:
            pass
        else:
            raise AssertionError("una carpeta en lugar del lock")
        shutil.rmtree(base / ".claude" / "reglas" / "paquetes.json")
        poner_lock(base, "")
        (base / ".claude" / "reglas" / "paquetes.json").write_bytes(b'{"version": 1, "paquetes": {}}\xff')
        try:
            m().leer_lock(str(base))
        except m().LockRoto:
            pass
        else:
            raise AssertionError("un lock que no es UTF-8")


def test_validar_lock_sirve_para_un_lock_en_memoria():
    paquetes = m().validar_lock(_lock_con())
    assert list(paquetes) == ["go-basico"] and paquetes["go-basico"].prefijo == "GOB", paquetes


def test_el_manifiesto_valido_pasa_y_cualquier_desvio_se_rechaza_con_su_clave():
    assert m().validar_manifiesto(manifiesto()) == manifiesto()
    casos = [
        ([], "objeto"),
        (manifiesto(formato=2), "formato"),
        (manifiesto(formato=True), "formato"),
        (manifiesto(nombre="Go"), "nombre"),
        (manifiesto(nombre="-go"), "nombre"),
        (manifiesto(nombre=""), "nombre"),
        (manifiesto(prefijo="1GO"), "prefijo"),
        (manifiesto(prefijo=""), "prefijo"),
        (manifiesto(api=0), "odd_ws_api"),
        (manifiesto(api=True), "odd_ws_api"),
        (manifiesto(api="1"), "odd_ws_api"),
        (manifiesto(descripcion=None), "descripcion"),
        (manifiesto(dependencias=[]), "dependencias"),
        ({k: v for k, v in manifiesto().items() if k != "descripcion"}, "descripcion"),
    ]
    for datos, rastro in casos:
        try:
            m().validar_manifiesto(datos)
        except m().ManifiestoInvalido as error:
            assert rastro in str(error), (datos, str(error))
        else:
            raise AssertionError("no lo rechazó: %r" % (datos,))


def test_leer_manifiesto_de_una_carpeta():
    with Temporal() as base:
        carpeta = poner_paquete(base)
        assert m().leer_manifiesto(str(carpeta)) == manifiesto()
        (carpeta / "odd-ws-paquete.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(manifiesto()).encode("utf-8"))
        assert m().leer_manifiesto(str(carpeta)) == manifiesto(), "con BOM"
        for crudo in (b"{roto", b"\xff\xfe"):
            (carpeta / "odd-ws-paquete.json").write_bytes(crudo)
            try:
                m().leer_manifiesto(str(carpeta))
            except m().ManifiestoInvalido as error:
                assert "odd-ws-paquete.json" in str(error), str(error)
            else:
                raise AssertionError(crudo)
        os.remove(carpeta / "odd-ws-paquete.json")
        try:
            m().leer_manifiesto(str(carpeta))
        except m().ManifiestoInvalido as error:
            assert "odd-ws-paquete.json" in str(error), str(error)
        else:
            raise AssertionError("sin manifiesto")


def test_la_huella_cumple_la_especificacion_y_no_depende_del_fin_de_linea():
    with Temporal() as base:
        carpeta = poner_paquete(base)
        presentes = {p.name: p.read_bytes() for p in carpeta.iterdir()}
        esperada = huella_de_la_especificacion(presentes)
        assert m().huella(str(carpeta)) == esperada
        for nombre, contenido in presentes.items():
            (carpeta / nombre).write_bytes(contenido.replace(b"\n", b"\r\n"))
        assert m().huella(str(carpeta)) == esperada, "un checkout con autocrlf da la misma huella"


def test_la_huella_cuenta_solo_la_lista_blanca_y_cambia_con_una_edicion():
    with Temporal() as base:
        carpeta = poner_paquete(base)
        antes = m().huella(str(carpeta))
        (carpeta / "extra.py").write_text("x = 1\n", encoding="utf-8")
        (carpeta / "sub").mkdir()
        (carpeta / "sub" / "verificar.py").write_text("x = 2\n", encoding="utf-8")
        assert m().huella(str(carpeta)) == antes, "lo que no es de la lista blanca no cuenta"
        (carpeta / "LICENSE").write_text("MIT\n", encoding="utf-8")
        con_licencia = m().huella(str(carpeta))
        assert con_licencia != antes, "LICENSE es de la lista blanca"
        (carpeta / "verificar.py").write_text("def verificar(ctx):\n    return [] \n", encoding="utf-8")
        assert m().huella(str(carpeta)) != con_licencia, "una edición cambia la huella"
        os.remove(carpeta / "verificar.py")
        assert m().huella(str(carpeta)) not in (antes, con_licencia), "un archivo que falta cambia la huella"


def test_los_activos_de_una_capa_saltean_lo_que_no_se_puede_cargar():
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"), ("otro", "go", "OTR"), ("de-sql", "sql", "DSQ"))
        assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno", "otro"]
        poner_paquete(base, "otro", "OTR", api=2)
        assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"], "un odd_ws_api mayor no se carga"
        poner_paquete(base, "otro", "OTR", datos=manifiesto("otro-nombre", "OTR"))
        assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"], "el nombre del manifiesto no es el del lock"
        poner_paquete(base, "otro", "OTR", datos=manifiesto("otro", "XYZ"))
        assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"], "el prefijo del manifiesto no es el del lock"
        poner_paquete(base, "otro", "OTR", datos={"formato": 1})
        assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"], "manifiesto inválido"
        shutil.rmtree(base / ".claude" / "reglas" / "paquetes" / "otro")
        assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"], "sin carpeta"
        lock["bueno"]["prefijo"] = "SQL"
        poner_paquete(base, "bueno", "SQL")
        poner_lock(base, lock)
        assert m().activos(str(base), "go", CAPAS) == [], "el prefijo de una capa no lo puede usar un paquete"
        (base / "x").mkdir()
        assert [p.nombre for p in m().activos(str(base), "sql", CAPAS)] == ["de-sql"]


def test_los_activos_no_miran_la_huella():
    with Temporal() as base:
        instancia_con(base, ("bueno", "go", "BUE"))
        (base / ".claude" / "reglas" / "paquetes" / "bueno" / "verificar.py").write_text("editado = 1\n", encoding="utf-8")
        assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"]


def test_los_activos_con_el_lock_roto_lanzan_lock_roto():
    with Temporal() as base:
        poner_lock(base, "{roto")
        try:
            m().activos(str(base), "go", CAPAS)
        except m().LockRoto:
            pass
        else:
            raise AssertionError("lock roto")


def test_el_id_de_un_hallazgo_de_paquete_lleva_su_prefijo():
    assert m().id_del_paquete("GOB", "GOB-01") and m().id_del_paquete("GOB", "GOB-123")
    for malo in ("GOB-1", "GO-01", "GOBX-01", "gob-01", "GOB-01x", "GOB01", "", None, 3):
        assert not m().id_del_paquete("GOB", malo), malo


def test_los_problemas_de_una_instancia_sana_son_ninguno():
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"), ("de-sql", "sql", "DSQ"))
        assert m().problemas(str(base), m().validar_lock({"version": 1, "paquetes": lock}), CAPAS) == []


def _problemas(base, lock):
    return m().problemas(str(base), m().validar_lock({"version": 1, "paquetes": lock}), CAPAS)


def test_cada_problema_de_un_paquete_se_nombra():
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        lock["bueno"]["capa"] = "rust"
        assert _problemas(base, lock) == ["bueno: la capa rust no está declarada en workspace.config.json"]
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        shutil.rmtree(base / ".claude" / "reglas" / "paquetes" / "bueno")
        assert _problemas(base, lock) == ["bueno: falta la carpeta .claude/reglas/paquetes/bueno"]
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        carpeta = base / ".claude" / "reglas" / "paquetes" / "bueno"
        os.remove(carpeta / "verificar.tests.py")
        os.remove(carpeta / "evidencia.md")
        lock["bueno"]["huella"] = m().huella(str(carpeta))
        assert _problemas(base, lock) == ["bueno: faltan verificar.tests.py, evidencia.md en .claude/reglas/paquetes/bueno"]
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        (base / ".claude" / "reglas" / "paquetes" / "bueno" / "verificar.py").write_text("editado = 1\n", encoding="utf-8")
        problemas = _problemas(base, lock)
        assert len(problemas) == 1 and problemas[0].startswith("bueno: la huella no coincide con el lock"), problemas
        assert "/odd-ws:paquetes" not in problemas[0], "el cómo va en la ayuda del doctor, no en el detalle"
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "GO"))
        assert _problemas(base, lock) == ["bueno: el prefijo GO ya lo usa layers.go.rule_prefix"]
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        poner_paquete(base, "bueno", "BUE", api=2)
        lock["bueno"]["huella"] = m().huella(str(base / ".claude" / "reglas" / "paquetes" / "bueno"))
        assert _problemas(base, lock) == ["bueno: pide odd_ws_api 2 y este plugin da 1, así que no se carga"], _problemas(base, lock)
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        poner_paquete(base, "bueno", "BUE", datos=manifiesto("malo", "MAL"))
        lock["bueno"]["huella"] = m().huella(str(base / ".claude" / "reglas" / "paquetes" / "bueno"))
        assert _problemas(base, lock) == ["bueno: el manifiesto dice nombre malo y el lock bueno",
                                          "bueno: el manifiesto dice prefijo MAL y el lock BUE"], _problemas(base, lock)
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        poner_paquete(base, "bueno", "BUE", datos={"formato": 1})
        lock["bueno"]["huella"] = m().huella(str(base / ".claude" / "reglas" / "paquetes" / "bueno"))
        problemas = _problemas(base, lock)
        assert len(problemas) == 1 and problemas[0].startswith("bueno: odd-ws-paquete.json no es válido"), problemas


def _enlazar(destino, enlace, carpeta=False):
    try:
        os.symlink(str(destino), str(enlace), target_is_directory=carpeta)
        return True
    except OSError:
        if carpeta and os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(destino), str(enlace))
            return True
        return False


def _junction(destino, enlace):
    if os.name != "nt":
        return _enlazar(destino, enlace, carpeta=True)
    import _winapi
    _winapi.CreateJunction(str(destino), str(enlace))
    return True


def test_un_paquete_con_enlaces_o_fuera_de_su_carpeta_no_se_carga_y_se_nombra():
    probados = []
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"), ("otro", "go", "OTR"))
        afuera = base / "afuera.py"
        afuera.write_text("def verificar(ctx):\n    return []\n", encoding="utf-8")
        modulo = base / ".claude" / "reglas" / "paquetes" / "otro" / "verificar.py"
        os.remove(modulo)
        if _enlazar(afuera, modulo):
            probados.append("archivo")
            assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"], "un verificar.py enlazado no se carga"
            assert ("otro: enlace o fuera de .claude/reglas/paquetes/otro, así que no se carga: "
                    ".claude/reglas/paquetes/otro/verificar.py") in _problemas(base, lock), _problemas(base, lock)
    for crear in (_enlazar, _junction):
        with Temporal() as base:
            lock = instancia_con(base, ("bueno", "go", "BUE"), ("otro", "go", "OTR"))
            carpeta = base / ".claude" / "reglas" / "paquetes" / "otro"
            real = base / "real-otro"
            shutil.move(str(carpeta), str(real))
            if crear(real, carpeta, True) if crear is _enlazar else crear(real, carpeta):
                probados.append(crear.__name__)
                assert [p.nombre for p in m().activos(str(base), "go", CAPAS)] == ["bueno"], crear.__name__
                assert ("otro: enlace o fuera de .claude/reglas/paquetes/otro, así que no se carga: "
                        ".claude/reglas/paquetes/otro") in _problemas(base, lock), (crear.__name__, _problemas(base, lock))
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        todos = base / ".claude" / "reglas" / "paquetes"
        real = base / "otro-lugar"
        shutil.move(str(todos), str(real))
        _junction(real, todos)
        assert m().activos(str(base), "go", CAPAS) == [], "la carpeta de los paquetes enlazada saca todo de su lugar"
        assert ("bueno: enlace o fuera de .claude/reglas/paquetes/bueno, así que no se carga: "
                ".claude/reglas/paquetes/bueno") in _problemas(base, lock), _problemas(base, lock)
    with Temporal() as base:
        lock = instancia_con(base, ("bueno", "go", "BUE"))
        assert m().enlaces(str(base), "bueno") == [] and _problemas(base, lock) == [], "sin enlaces no hay nada que decir"
    assert "_junction" in probados, probados


def _entrada_de(nombre, capa, prefijo, etiqueta, commit, huella):
    return m().Paquete(nombre, capa, prefijo, "https://example.com/%s.git" % nombre, etiqueta, commit, huella)


def test_escribir_lock_es_determinista_valida_antes_y_borra_el_lock_vacio():
    zeta = _entrada_de("zeta", "go", "ZET", "v1", "a" * 40, "sha256:" + "1" * 64)
    alfa = _entrada_de("alfa", "sql", "ALF", "v2.0", "b" * 40, "sha256:" + "2" * 64)
    with Temporal() as base:
        m().escribir_lock(str(base), {"zeta": zeta, "alfa": alfa})
        ruta = base / ".claude" / "reglas" / "paquetes.json"
        esperado = {"version": 1, "paquetes": {
            "alfa": {"capa": "sql", "prefijo": "ALF", "fuente": "https://example.com/alfa.git", "etiqueta": "v2.0", "commit": "b" * 40,
                     "huella": "sha256:" + "2" * 64},
            "zeta": {"capa": "go", "prefijo": "ZET", "fuente": "https://example.com/zeta.git", "etiqueta": "v1", "commit": "a" * 40,
                     "huella": "sha256:" + "1" * 64}}}
        assert ruta.read_bytes() == (json.dumps(esperado, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), ruta.read_bytes()
        assert m().datos_del_lock({"zeta": zeta, "alfa": alfa}) == esperado
        assert m().leer_lock(str(base)) == {"alfa": alfa, "zeta": zeta}
        antes = ruta.read_bytes()
        for malo in ({"zeta": zeta._replace(commit="no")}, {"zeta": zeta, "alfa": alfa._replace(prefijo="ZET")}):
            try:
                m().escribir_lock(str(base), malo)
            except m().LockRoto:
                pass
            else:
                raise AssertionError("escribió un lock inválido: %r" % (malo,))
            assert ruta.read_bytes() == antes, "un lock inválido no toca el que había"
        m().escribir_lock(str(base), {})
        assert not ruta.exists() and m().leer_lock(str(base)) is None, "sin paquetes, sin lock"
        m().escribir_lock(str(base), {})
        assert sorted(p.name for p in ruta.parent.iterdir()) == [], "no deja temporales"


def test_presentes_y_enlaces_en_una_carpeta_suelta():
    with Temporal() as base:
        carpeta = poner_paquete(base)
        (carpeta / "extra.py").write_text("x = 1\n", encoding="utf-8")
        (carpeta / "LICENSE").mkdir()
        assert m().presentes(str(carpeta)) == ["evidencia.md", "matriz.csv", "no-negociables.md", "odd-ws-paquete.json", "verificar.py",
                                               "verificar.tests.py"], m().presentes(str(carpeta))
        assert m().enlaces_en(str(carpeta)) == []
        afuera = base / "afuera.py"
        afuera.write_text("x = 2\n", encoding="utf-8")
        os.remove(carpeta / "verificar.py")
        if _enlazar(afuera, carpeta / "verificar.py"):
            assert m().enlaces_en(str(carpeta)) == ["verificar.py"], m().enlaces_en(str(carpeta))
            assert "verificar.py" not in m().presentes(str(carpeta)), "un enlace no es un archivo del paquete"


def test_destino_enlazado_mira_la_carpeta_mas_honda_que_existe():
    with Temporal() as base:
        assert m().destino_enlazado(str(base), "alfa") is None, "sin .claude todavía no hay nada que mirar"
        (base / ".claude" / "reglas" / "paquetes").mkdir(parents=True)
        assert m().destino_enlazado(str(base), "alfa") is None
        poner_paquete(base, "alfa")
        assert m().destino_enlazado(str(base), "alfa") is None
    with Temporal() as base:
        real = base / "afuera"
        real.mkdir()
        (base / ".claude" / "reglas").mkdir(parents=True)
        _junction(real, base / ".claude" / "reglas" / "paquetes")
        assert m().destino_enlazado(str(base), "alfa") == ".claude/reglas/paquetes"
        (real / "alfa").mkdir()
        assert m().destino_enlazado(str(base), "alfa") == ".claude/reglas/paquetes/alfa", "su carpeta sale por el enlace de arriba"
    with Temporal() as base:
        poner_paquete(base, "alfa")
        real = base / "alfa-real"
        shutil.move(str(base / ".claude" / "reglas" / "paquetes" / "alfa"), str(real))
        _junction(real, base / ".claude" / "reglas" / "paquetes" / "alfa")
        assert m().destino_enlazado(str(base), "alfa") == ".claude/reglas/paquetes/alfa"


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
