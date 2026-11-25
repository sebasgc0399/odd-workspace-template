import contextlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
EN_WINDOWS = os.name == "nt"


def m():
    return importlib.import_module("config_loader")


def config_valida():
    return {
        "schema_version": 1,
        "defaults": {"mold_source": "repo"},
        "repos": {"db": {}},
        "layers": {"sql": {"extensions": [".sql"], "repos": ["db"], "workshop": ["tickets/**/*.sql"]}},
    }


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Instancia:
    def __init__(self, config=None, local=None):
        self.config = config_valida() if config is None else config
        self.local = local

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="config-"))
        self.repo = self.base / "repos" / "DB"
        self.repo.mkdir(parents=True)
        self.raiz = self.base / "instancia"
        self.ticket = self.raiz / "tickets" / "T-1"
        self.ticket.mkdir(parents=True)
        if self.config is not False:
            texto = self.config if isinstance(self.config, str) else json.dumps(self.config)
            (self.raiz / "workspace.config.json").write_text(texto, encoding="utf-8")
        local = {"repos": {"db": {"path": str(self.repo)}}} if self.local is None else self.local
        if local is not False:
            texto = local if isinstance(local, str) else json.dumps(local)
            (self.raiz / "workspace.local.json").write_text(texto, encoding="utf-8")
        self.junctions = []
        return self

    def junction(self, nombre, destino):
        enlace = self.base / nombre
        subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], capture_output=True, check=True)
        self.junctions.append(enlace)
        return enlace

    def __exit__(self, *_):
        for enlace in self.junctions:
            os.rmdir(enlace)
        shutil.rmtree(self.base, onexc=_forzar_borrado)


def mismo(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def test_inicio_usa_claude_project_dir_y_si_falta_cwd():
    assert m().inicio_de_sesion({"CLAUDE_PROJECT_DIR": "X"}, "Y") == "X"
    assert m().inicio_de_sesion({}, "Y") == "Y"
    assert m().inicio_de_sesion({"CLAUDE_PROJECT_DIR": ""}, "Y") == "Y"


def test_encuentra_la_raiz_desde_una_carpeta_de_ticket():
    with Instancia() as i:
        assert mismo(m().encontrar_raiz(i.ticket), i.raiz)


def test_la_instancia_mas_cercana_gana():
    with Instancia() as i:
        (i.ticket / "workspace.config.json").write_text(json.dumps(config_valida()), encoding="utf-8")
        assert mismo(m().encontrar_raiz(i.ticket), i.ticket)


def test_sin_config_es_ausente():
    with Instancia(config=False) as i:
        e = m().estado(i.ticket)
        assert e.tipo == "ausente" and e.raiz is None, e


def test_config_valida_carga():
    with Instancia() as i:
        e = m().estado(i.ticket)
        assert e.tipo == "ok", e
        assert mismo(e.raiz, i.raiz), e
        assert mismo(e.config["repos"]["db"]["path"], i.repo), e


def test_json_invalido_es_rota_y_conserva_la_raiz():
    with Instancia(config="{ no es json") as i:
        e = m().estado(i.ticket)
        assert e.tipo == "rota", e
        assert "workspace.config.json" in e.razon, e
        assert mismo(e.raiz, i.raiz), e


def test_sin_schema_version_es_rota():
    config = config_valida()
    del config["schema_version"]
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "schema_version" in e.razon, e


def test_schema_version_desconocida_es_rota():
    config = config_valida()
    config["schema_version"] = 2
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "schema_version" in e.razon, e


def test_schema_version_booleana_es_rota():
    config = config_valida()
    config["schema_version"] = True
    with Instancia(config=config) as i:
        assert m().estado(i.raiz).tipo == "rota"


def test_local_invalido_es_rota():
    with Instancia(local="[roto") as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "workspace.local.json" in e.razon, e


def test_falta_la_ruta_del_repo_es_rota():
    with Instancia(local=False) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "workspace.local.json" in e.razon and "db" in e.razon, e


def test_ruta_del_repo_inexistente_es_rota():
    with Instancia(local={"repos": {"db": {"path": "Z:/no/existe/nunca"}}}) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "no existe" in e.razon, e


def test_mold_source_invalido_es_rota():
    config = config_valida()
    config["defaults"]["mold_source"] = "boy_scout"
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "mold_source" in e.razon, e


def test_mold_source_por_defecto_es_repo_y_la_capa_lo_puede_cambiar():
    config = config_valida()
    del config["defaults"]
    config["layers"]["ts"] = {"extensions": [".ts"], "mold_source": "propio"}
    with Instancia(config=config) as i:
        cargada = m().cargar(i.raiz)
        assert m().molde_de(cargada, "sql") == "repo"
        assert m().molde_de(cargada, "ts") == "propio"


def test_capa_con_repo_no_declarado_es_rota():
    config = config_valida()
    config["layers"]["sql"]["repos"] = ["fantasma"]
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "fantasma" in e.razon, e


def test_extension_sin_punto_es_rota():
    config = config_valida()
    config["layers"]["sql"]["extensions"] = ["sql"]
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "extensions" in e.razon, e


def test_rule_prefix_valido_se_conserva():
    config = config_valida()
    config["layers"]["sql"]["rule_prefix"] = "SQL"
    config["layers"]["web"] = {"extensions": [".cs"], "rule_prefix": "W2"}
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "ok", e
        assert e.config["layers"]["sql"]["rule_prefix"] == "SQL"
        assert e.config["layers"]["web"]["rule_prefix"] == "W2"


def test_rule_prefix_invalido_es_rota():
    for malo in ("sql", "1A", "", "S-Q", "SQL ", 3, None, ["SQL"]):
        config = config_valida()
        config["layers"]["sql"]["rule_prefix"] = malo
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "rota" and "rule_prefix" in e.razon, (malo, e)


def test_rule_prefix_repetido_es_rota():
    config = config_valida()
    config["layers"]["sql"]["rule_prefix"] = "SQL"
    config["layers"]["otra"] = {"extensions": [".txt"], "rule_prefix": "SQL"}
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "rule_prefix" in e.razon and "otra" in e.razon, e


def test_agent_readonly_booleano_se_conserva():
    for valor in (True, False):
        config = config_valida()
        config["repos"]["db"] = {"agent_readonly": valor}
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "ok" and e.config["repos"]["db"]["agent_readonly"] is valor, (valor, e)
    with Instancia() as i:
        assert "agent_readonly" not in m().estado(i.raiz).config["repos"]["db"]


def test_agent_readonly_que_no_es_booleano_es_rota():
    for malo in ("true", 1, 0, None, [], {}):
        config = config_valida()
        config["repos"]["db"] = {"agent_readonly": malo}
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "rota" and "repos.db.agent_readonly" in e.razon, (malo, e)
            try:
                m().capas(i.raiz)
            except m().ConfigRota as error:
                assert "agent_readonly" in str(error), error
            else:
                raise AssertionError(f"capas() debia dar rota con {malo!r}")


def test_repos_que_no_es_un_objeto_es_rota_tambien_en_capas():
    config = config_valida()
    config["repos"] = ["db"]
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "repos" in e.razon, e
        try:
            m().capas(i.raiz)
        except m().ConfigRota as error:
            assert "repos" in str(error), error
        else:
            raise AssertionError("capas() debia dar rota con repos como lista")


def test_capas_no_necesita_las_rutas_de_la_maquina():
    config = config_valida()
    config["layers"]["sql"]["rule_prefix"] = "SQL"
    with Instancia(config=config, local=False) as i:
        assert m().estado(i.raiz).tipo == "rota", "control: sin workspace.local.json, cargar() la da por rota"
        capas = m().capas(i.raiz)
        assert capas["sql"]["rule_prefix"] == "SQL"
    with Instancia(config=config, local={"repos": {"db": {"path": "C:/no/existe"}}}) as i:
        assert m().capas(i.raiz)["sql"]["extensions"] == [".sql"]


def test_capas_valida_el_resto_del_esquema():
    casos = []
    config = config_valida()
    config["schema_version"] = 2
    casos.append((config, "schema_version"))
    config = config_valida()
    config["layers"]["sql"]["repos"] = ["fantasma"]
    casos.append((config, "fantasma"))
    config = config_valida()
    config["layers"]["sql"]["rule_prefix"] = "sql"
    casos.append((config, "rule_prefix"))
    for config, palabra in casos:
        with Instancia(config=config, local=False) as i:
            try:
                m().capas(i.raiz)
            except m().ConfigRota as error:
                assert palabra in str(error), (palabra, error)
            else:
                raise AssertionError(f"debia ser rota por {palabra}")


def test_glob_el_asterisco_no_cruza_carpetas():
    c = m().coincide
    assert c("a/x.sql", "a/*.sql")
    assert not c("a/b/x.sql", "a/*.sql")
    assert not c("a/x.sql", "*.sql")
    assert c("x.sql", "*.sql")
    assert not c("a/x.sql", "a?x.sql")


def test_glob_doble_asterisco_es_cero_o_mas_carpetas():
    c = m().coincide
    for ruta in ("x.sql", "a/x.sql", "a/b/c/x.sql"):
        assert c(ruta, "**/x.sql"), ruta
    for ruta in ("a/x.sql", "a/b/x.sql", "a/b/c/d.txt"):
        assert c(ruta, "a/**"), ruta
    assert c("a/x/b", "a/**/b") and c("a/b", "a/**/b") and c("a/x/y/b", "a/**/b")
    assert not c("ab", "a/**/b") and not c("xa/b", "a/**/b")


def test_glob_clases_signos_y_mayusculas():
    c = m().coincide
    assert c("T-12", "T-[0-9]*") and not c("T-x1", "T-[0-9]*")
    assert c("b", "[!a]") and not c("a", "[!a]")
    assert c("a.b", "a?b") and not c("a/b", "a?b")
    assert c("Tickets/T-1/SQL/X.SQL", "tickets/t-1/sql/x.sql")
    assert c("a+b(1).sql", "a+b(1).sql") and not c("aab(1).sql", "a+b(1).sql")
    assert not c("a.sql", "a.sqlx") and not c("a.sqlx", "a.sql")


def test_taller_con_la_carpeta_sql_como_hija_directa_del_ticket():
    config = config_valida()
    config["layers"]["sql"]["workshop"] = ["tickets/**/T-[0-9]*/SQL/esq.*.sql"]
    with Instancia(config=config) as i:
        cargada = m().cargar(i.raiz)
        for ruta in ("tickets/T-1-x/SQL/esq.uno.sql", "tickets/Publicados/v1/T-22/SQL/esq.dos.sql"):
            assert m().clasificar(i.raiz / ruta, cargada) == ("sql", "taller"), ruta
        for ruta in ("tickets/T-1/SQL/sub/esq.uno.sql", "tickets/T-1/otra/SQL/esq.uno.sql",
                     "tickets/T-1/SQL/otro.uno.sql", "tickets/T-x/SQL/esq.uno.sql", "T-1/SQL/esq.uno.sql"):
            assert m().clasificar(i.raiz / ruta, cargada) is None, ruta


def capa_movil():
    config = config_valida()
    config["repos"]["app"] = {}
    config["layers"]["movil"] = {"extensions": [".java", ".xml"], "repos": ["app"], "match": ["**/*.java", "**/res/**/*.xml"]}
    return config


def test_match_restringe_los_archivos_del_repo_que_reclama_la_capa():
    with Instancia(config=capa_movil(), local=False) as i:
        app = i.base / "repos" / "App"
        app.mkdir(parents=True)
        (i.raiz / "workspace.local.json").write_text(json.dumps({"repos": {"db": {"path": str(i.repo)}, "app": {"path": str(app)}}}), encoding="utf-8")
        cargada = m().cargar(i.raiz)
        for ruta in ("src/main/res/values/a.xml", "res/a.xml", "src/A.java", "A.java"):
            assert m().clasificar(app / ruta, cargada) == ("movil", "app"), ruta
        for ruta in ("build.xml", "src/resources/a.xml", "fres/a.xml"):
            assert m().clasificar(app / ruta, cargada) is None, ruta


def test_sin_match_la_capa_reclama_toda_su_extension():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.repo / "a" / "b" / "Uno.sql", cargada) == ("sql", "db")


def test_extensiones_sin_capa_cuenta_lo_que_no_clasifica_y_saltea_los_docs():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        rutas = [i.repo / r for r in ("a.sql", "sub/b.SQL", "x.mjs", "sub/y.MJS", "Makefile", "README.md", "notas.TXT", "guia.rst",
                                      "package.json")]
        rutas.append(i.ticket / "suelto.sql")
        assert m().extensiones_sin_capa(rutas, cargada) == {".mjs": 2, "(sin extensión)": 1, ".json": 1}
        assert m().extensiones_sin_capa([i.repo / "a.sql", i.repo / "README.md"], cargada) == {}
        assert m().EXTENSIONES_DE_DOCS == (".md", ".txt", ".rst")


def test_lista_de_extensiones_va_de_la_mas_frecuente_y_corta_en_el_tope():
    assert m().lista_de_extensiones({".json": 1, ".mjs": 2, "(sin extensión)": 1}) == ".mjs (2), (sin extensión) (1), .json (1)"
    diez = {".e%d" % n: 1 for n in range(10)}
    assert m().lista_de_extensiones(diez) == ", ".join(".e%d (1)" % n for n in range(8)) + " y 2 más"
    assert m().lista_de_extensiones({".e%d" % n: 1 for n in range(8)}).endswith(".e7 (1)")


def test_cobertura_de_los_repos_lee_lo_versionado_de_cada_repo():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        pedidos = []

        def versionados(ruta):
            pedidos.append(ruta)
            return ["a.sql", "x.mjs", "y.mjs", "Makefile", "README.md"]

        assert m().cobertura_de_los_repos(cargada, versionados)[:2] == (True, "extensiones versionadas sin capa: .mjs (2)")
        assert pedidos == [str(i.repo)], pedidos
        assert m().cobertura_de_los_repos(cargada, lambda ruta: ["a.sql", "README.md"]) is None
        assert m().cobertura_de_los_repos(cargada, lambda ruta: None) is None, "un repo que git no pudo listar no cuenta"


def test_cobertura_con_solo_esperados_no_avisa_y_los_nombra_con_su_conteo():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        versionados = ["a.sql", "package.json", "tsconfig.json", ".gitignore", "README.md"]
        assert m().cobertura_de_los_repos(cargada, lambda ruta: versionados)[:2] == (
            False, "sin capa y esperados: .json (2), (sin extensión) (1); un cambio en ellos lleva /odd-ws:revisar a modo completo")


def test_cobertura_con_una_no_esperada_avisa_y_lista_solo_las_no_esperadas():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        versionados = ["a.sql", "x.mjs", "sub/y.mjs", "build.sh", "package.json", "ci.yml", "Dockerfile"]
        assert m().cobertura_de_los_repos(cargada, lambda ruta: versionados)[:2] == (
            True, "extensiones versionadas sin capa: .mjs (2), .sh (1)")


def test_los_datos_la_configuracion_y_los_archivos_sin_extension_son_esperados():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        datos = ["a.json", "b.JSONC", "c.yml", "d.yaml", "e.toml", "yarn.lock", "f.ini"]
        sin_extension = [".gitignore", ".gitattributes", "Dockerfile", "Makefile", "sub/LICENSE"]
        for versionados in (datos, sin_extension):
            cobertura = m().cobertura_de_los_repos(cargada, lambda ruta: versionados)
            assert cobertura is not None and cobertura.aviso is False, (versionados, cobertura)
        assert m().cobertura_de_los_repos(cargada, lambda ruta: sin_extension).detalle.startswith(
            "sin capa y esperados: (sin extensión) (5); ")


def test_en_controles_la_nota_de_los_esperados_no_habla_de_revisar():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        cobertura = m().cobertura_de_los_repos(cargada, lambda ruta: ["package.json", "Makefile"], controles=True)
        assert cobertura[:2] == (False, "sin capa y esperados: (sin extensión) (1), .json (1); ninguna regla de capa los chequea"), cobertura
        assert m().cobertura_de_los_repos(cargada, lambda ruta: ["x.mjs", "package.json"], controles=True)[:2] == (
            True, "extensiones versionadas sin capa: .mjs (1)")


def test_sin_capa_sin_la_clave_es_una_lista_vacia_y_la_cobertura_sale_como_antes():
    assert m().sin_capa_de({}) == []
    with Instancia() as i:
        assert m().sin_capa(i.raiz) == []
        cargada = m().cargar(i.raiz)
        assert "sin_capa" not in cargada, cargada
        versionados = ["a.sql", "i.png", "x.mjs", "package.json"]
        assert m().cobertura_de_los_repos(cargada, lambda ruta: versionados) == m().cobertura_de_los_repos(
            cargada, lambda ruta: versionados, sin_capa=m().sin_capa(i.raiz))


def test_sin_capa_pasa_sus_extensiones_a_las_esperadas_sin_distinguir_mayusculas():
    for valor in ([".png", ".XML"], [".PNG", ".xml"]):
        assert m().sin_capa_de({"sin_capa": list(valor)}) == valor, valor
        with Instancia(config=con_clave("sin_capa", list(valor))) as i:
            assert m().sin_capa(i.raiz) == valor, valor
            cargada = m().cargar(i.raiz)
            reconocidas = m().sin_capa(i.raiz)
            solo_reconocidas = ["a.sql", "res/i.png", "res/j.png", "res/k.xml", "package.json"]
            assert m().cobertura_de_los_repos(cargada, lambda ruta: solo_reconocidas, sin_capa=reconocidas) == (
                False, "sin capa y esperados: .png (2), .json (1), .xml (1); un cambio en ellos lleva /odd-ws:revisar a modo completo", "")
            cobertura = m().cobertura_de_los_repos(cargada, lambda ruta: solo_reconocidas + ["x.mjs"], sin_capa=reconocidas)
            assert cobertura[:2] == (True, "extensiones versionadas sin capa: .mjs (1)"), cobertura


def test_sin_capa_invalido_es_rota_y_cargar_no_lo_mira():
    malos = (".png", None, 3, True, {".png": True}, [1], [None], ["png"], ["."], [""], [[".png"]], [".png", 2])
    for malo in malos:
        try:
            m().sin_capa_de({"sin_capa": malo})
        except m().ConfigRota as error:
            assert str(error).startswith("sin_capa debe ser una lista de extensiones con punto"), (malo, str(error))
        else:
            raise AssertionError(f"sin_capa_de() debe lanzar ConfigRota para {malo!r}")
        with Instancia(config=con_clave("sin_capa", malo)) as i:
            assert m().estado(i.raiz).tipo == "ok", malo
            try:
                m().sin_capa(i.raiz)
            except m().ConfigRota:
                pass
            else:
                raise AssertionError(f"sin_capa() debe lanzar ConfigRota para {malo!r}")
    assert m().sin_capa_de({"sin_capa": []}) == []


def test_plantillas_es_la_version_anotada_y_un_valor_invalido_es_rota_sin_que_cargar_lo_mire():
    assert m().plantillas_de({}) is None
    for valor in ("0.14.0", "1.2.3", "0.14.0-rc.1"):
        assert m().plantillas_de({"plantillas": valor}) == valor, valor
        with Instancia(config=con_clave("plantillas", valor)) as i:
            assert m().plantillas(i.raiz) == valor, valor
    for malo in ("", "0.14", "v0.14.0", " 0.14.0", "0.14.0 ", "latest", None, 14, True, ["0.14.0"], {"version": "0.14.0"}):
        try:
            m().plantillas_de({"plantillas": malo})
        except m().ConfigRota as error:
            assert str(error).startswith("plantillas debe ser la versión del plugin"), (malo, str(error))
        else:
            raise AssertionError(f"plantillas_de() debe lanzar ConfigRota para {malo!r}")
        with Instancia(config=con_clave("plantillas", malo)) as i:
            assert m().estado(i.raiz).tipo == "ok", malo
            try:
                m().plantillas(i.raiz)
            except m().ConfigRota:
                pass
            else:
                raise AssertionError(f"plantillas() debe lanzar ConfigRota para {malo!r}")


def test_el_como_de_la_cobertura_trae_la_linea_de_sin_capa_con_todas_las_extensiones_del_aviso():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        versionados = ["a.sql", "x.mjs", "y.mjs", "i.png", "package.json"] + ["otros/a%d.e%d" % (n, n) for n in range(8)]
        cobertura = m().cobertura_de_los_repos(cargada, lambda ruta: versionados)
        assert cobertura.aviso is True and cobertura.detalle.endswith(" y 2 más"), cobertura
        todas = [".mjs"] + [".e%d" % n for n in range(8)] + [".png"]
        assert cobertura.ayuda == m().ayuda_de_cobertura({".mjs": 2, ".png": 1, **{".e%d" % n: 1 for n in range(8)}}), cobertura.ayuda
        assert cobertura.ayuda.startswith(m().AYUDA_COBERTURA.split("; si no,")[0] + ". "), cobertura.ayuda
        assert cobertura.ayuda.endswith(' "sin_capa": ' + json.dumps(todas)), cobertura.ayuda
        assert "sin capa a propósito" in cobertura.ayuda and "sin las extensiones que sí son código" in cobertura.ayuda, cobertura.ayuda
        previas = m().cobertura_de_los_repos(cargada, lambda ruta: versionados, sin_capa=[".gradle", ".PNG"])
        assert previas.ayuda.endswith(' "sin_capa": ' + json.dumps([".gradle", ".PNG"] + todas[:-1])), previas.ayuda
        controles = m().cobertura_de_los_repos(cargada, lambda ruta: versionados, controles=True)
        assert controles.ayuda.startswith(m().AYUDA_COBERTURA_CONTROLES.split("; si no,")[0] + ". "), controles.ayuda
        assert controles.ayuda.endswith(' "sin_capa": ' + json.dumps(todas)), controles.ayuda
    assert m().ayuda_de_cobertura({"(sin extensión)": 2}) == m().AYUDA_COBERTURA
    assert m().ayuda_de_cobertura({"(sin extensión)": 2}, controles=True) == m().AYUDA_COBERTURA_CONTROLES


def config_con_dos_repos():
    config = config_valida()
    config["repos"] = {"db": {}, "web": {}}
    return config


def poner_settings_de_repo(repo, nombre, contenido):
    ruta = Path(repo) / ".claude" / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido if isinstance(contenido, bytes) else json.dumps(contenido).encode("utf-8"))


def test_hooks_de_los_repos_nombra_cada_repo_de_la_config_con_hooks_y_sus_archivos():
    hooks = {"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "prettier"}]}]}}
    with Instancia() as i:
        web = i.base / "repos" / "web"
        web.mkdir()
        (i.raiz / "workspace.config.json").write_text(json.dumps(config_con_dos_repos()), encoding="utf-8")
        (i.raiz / "workspace.local.json").write_text(json.dumps({"repos": {"db": {"path": str(i.repo)}, "web": {"path": str(web)}}}),
                                                     encoding="utf-8")
        assert m().hooks_de_los_repos(m().cargar(i.raiz)) is None
        poner_settings_de_repo(web, "settings.json", hooks)
        poner_settings_de_repo(web, "settings.local.json", hooks)
        poner_settings_de_repo(i.repo, "settings.local.json", hooks)
        assert m().hooks_de_los_repos(m().cargar(i.raiz)) == (
            "repos con hooks propios: db (.claude/settings.local.json), web (.claude/settings.json, .claude/settings.local.json)")
        afuera = i.base / "repos" / "afuera"
        poner_settings_de_repo(afuera, "settings.json", hooks)
        poner_settings_de_repo(i.raiz, "settings.json", hooks)
        assert "afuera" not in m().hooks_de_los_repos(m().cargar(i.raiz)), "solo cuentan los repos de la config"
        assert m().ID_HOOKS_DE_REPOS == "hooks-de-repos"
        assert "corren solo si la sesión arranca en el repo" in m().AYUDA_HOOKS_DE_REPOS, m().AYUDA_HOOKS_DE_REPOS


def test_hooks_de_los_repos_calla_con_un_settings_ilegible_o_sin_hooks():
    for contenido in (b"{roto", b"\xff\xfe\x00no es utf-8", b"[]", b'"hooks"', {"permissions": {"allow": ["Bash"]}}, {"hooks": {}},
                      {"hooks": []}, {"hooks": None}):
        with Instancia() as i:
            poner_settings_de_repo(i.repo, "settings.json", contenido)
            poner_settings_de_repo(i.repo, "settings.local.json", contenido)
            assert m().hooks_de_los_repos(m().cargar(i.raiz)) is None, contenido
    with Instancia() as i:
        (i.repo / ".claude" / "settings.json").mkdir(parents=True)
        assert m().hooks_de_los_repos(m().cargar(i.raiz)) is None, "una carpeta en lugar del archivo no se puede leer"


def test_el_triaje_sigue_contando_los_esperados_y_con_la_misma_ayuda():
    assert m().lista_de_extensiones(m().contar_extensiones(["appsettings.json", "Makefile", "x.mjs"])) == (
        "(sin extensión) (1), .json (1), .mjs (1)")
    assert m().ID_COBERTURA == "capas-cobertura"
    assert m().AYUDA_COBERTURA == (
        "Un cambio en esos archivos lleva el triaje de /odd-ws:revisar a modo completo, porque no puede clasificarlos. Si son del "
        "mismo lenguaje que una capa (por ejemplo, .mjs o .js en una capa ts), súmalos a sus extensions en workspace.config.json; "
        "si no, el aviso queda.")


def test_la_ayuda_de_la_cobertura_dice_que_sube_a_completo_y_como_se_arregla():
    assert "/odd-ws:revisar a modo completo" in m().AYUDA_COBERTURA and "extensions" in m().AYUDA_COBERTURA
    assert m().NOMBRE in m().AYUDA_COBERTURA


def test_match_invalido_es_rota():
    for malo in ("**/*.java", [], [""], [3], None):
        config = config_valida()
        config["layers"]["sql"]["match"] = malo
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "rota" and "match" in e.razon, (malo, e)


def test_workshop_invalido_es_rota():
    for malo in ("tickets/**", [""], [3]):
        config = config_valida()
        config["layers"]["sql"]["workshop"] = malo
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "rota" and "workshop" in e.razon, (malo, e)


def test_workshop_vacio_o_nulo_sigue_siendo_valido_y_no_reclama_nada():
    for vacio in ([], None):
        config = config_valida()
        config["layers"]["sql"]["workshop"] = vacio
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "ok", (vacio, e)
            assert m().clasificar(i.ticket / "a.sql", e.config) is None, vacio
            assert m().capas(i.raiz)["sql"]["workshop"] == vacio


def test_glob_mal_formado_deja_la_config_rota_en_vez_de_romper():
    for campo in ("workshop", "match"):
        for malo in ("tickets/[z-a]*/x.sql", "a[9-0]"):
            config = config_valida()
            config["layers"]["sql"][campo] = [malo]
            with Instancia(config=config) as i:
                e = m().estado(i.raiz)
                assert e.tipo == "rota" and campo in e.razon and malo in e.razon, (campo, malo, e)


def test_glob_la_clase_negada_con_circunflejo_tampoco_cruza_carpetas():
    c = m().coincide
    assert not c("x/y", "x[^a]y") and not c("x/y", "x[!a]y")
    assert c("xby", "x[^a]y") and not c("xay", "x[^a]y")


def test_glob_corchete_de_cierre_al_principio_de_la_clase_es_literal():
    c = m().coincide
    assert c("]", "[]]") and c("a]", "a[]x]") and not c("b", "[]]")
    assert c("a", "[!]]") and not c("]", "[!]]") and not c("/", "[!]]")
    assert c("x[^]y", "x[^]y") and c("x[!]y", "x[!]y") and c("a[b", "a[b"), "un corchete sin cerrar es literal"


def test_glob_caracteres_especiales_dentro_de_la_clase_son_literales():
    import warnings
    c = m().coincide
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert c("a[b", "a[[]b") and c("a&b", "a[&]b") and c("a~b", "a[~]b") and c("a|b", "a[|]b")
        assert c("a\\b", "a[\\]b") and not c("axb", "a[[]b")


def _git(repo, *args):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                          capture_output=True, check=True, env=entorno)


def repo_con_commit(repo):
    _git(repo, "init", "-q")
    (repo / "base.sql").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")


def test_un_worktree_del_repo_cuenta_como_el_repo():
    for extra in ([], ["--relative-paths"]):
        with Instancia() as i:
            repo_con_commit(i.repo)
            arbol = i.base / "worktrees" / "db--rama"
            _git(i.repo, "worktree", "add", "-q", *extra, "-b", "rama", str(arbol))
            cargada = m().cargar(i.raiz)
            assert m().clasificar(arbol / "sp" / "Uno.sql", cargada) == ("sql", "db"), extra
            assert m().clasificar(i.base / "worktrees" / "otro" / "Uno.sql", cargada) is None, extra


def test_control_sin_registro_de_git_el_worktree_no_se_reconoce():
    with Instancia() as i:
        repo_con_commit(i.repo)
        arbol = i.base / "worktrees" / "db--rama"
        _git(i.repo, "worktree", "add", "-q", "-b", "rama", str(arbol))
        shutil.rmtree(i.repo / ".git" / "worktrees", onexc=_forzar_borrado)
        cargada = m().cargar(i.raiz)
        assert m().clasificar(arbol / "sp" / "Uno.sql", cargada) is None


def test_worktree_borrado_o_registro_ilegible_no_rompe_la_carga():
    with Instancia() as i:
        repo_con_commit(i.repo)
        arbol = i.base / "worktrees" / "db--rama"
        _git(i.repo, "worktree", "add", "-q", "-b", "rama", str(arbol))
        shutil.rmtree(arbol, onexc=_forzar_borrado)
        roto = i.repo / ".git" / "worktrees" / "roto"
        roto.mkdir()
        (roto / "gitdir").write_bytes(b"\xff\xfe\x00")
        vacio = i.repo / ".git" / "worktrees" / "vacio"
        vacio.mkdir()
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.repo / "Uno.sql", cargada) == ("sql", "db")


def test_un_repo_sin_git_no_rompe_la_carga():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.repo / "Uno.sql", cargada) == ("sql", "db")


def test_worktree_dentro_de_la_carpeta_del_repo_aplica_match_desde_su_propia_raiz():
    config = config_valida()
    config["layers"]["sql"]["match"] = ["res/**/*.sql"]
    with Instancia(config=config) as i:
        repo_con_commit(i.repo)
        arbol = i.repo / ".worktrees" / "w1"
        _git(i.repo, "worktree", "add", "-q", "-b", "w1", str(arbol))
        cargada = m().cargar(i.raiz)
        assert m().clasificar(arbol / "res" / "a.sql", cargada) == ("sql", "db")
        assert m().clasificar(i.repo / "res" / "a.sql", cargada) == ("sql", "db")
        assert m().clasificar(arbol / "otra" / "a.sql", cargada) is None


def test_sin_capas_es_rota():
    config = config_valida()
    config["layers"] = {}
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "layers" in e.razon, e


def test_workshop_baseline_valido_se_conserva():
    for base in ({"repo": "db"}, {"repo": "db", "under": "src/sp", "strip_prefix": "esq."}):
        config = config_valida()
        config["layers"]["sql"]["workshop_baseline"] = base
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "ok", (base, e)
            assert e.config["layers"]["sql"]["workshop_baseline"] == base


def test_workshop_baseline_invalido_es_rota():
    malos = ["db", None, {}, {"repo": "fantasma"}, {"repo": 3}, {"repo": "db", "otro": 1},
             {"repo": "db", "under": ""}, {"repo": "db", "under": "/abs"}, {"repo": "db", "under": "a/../b"},
             {"repo": "db", "under": "a\\b"}, {"repo": "db", "under": "C:/x"}, {"repo": "db", "strip_prefix": 3},
             {"repo": "db", "strip_prefix": ""}]
    for malo in malos:
        config = config_valida()
        config["layers"]["sql"]["workshop_baseline"] = malo
        with Instancia(config=config) as i:
            e = m().estado(i.raiz)
            assert e.tipo == "rota" and "workshop_baseline" in e.razon, (malo, e)


def test_clasifica_un_archivo_de_un_repo():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.repo / "sp" / "Uno.sql", cargada) == ("sql", "db")


def test_clasifica_un_archivo_del_taller():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.ticket / "SQL" / "dos.sql", cargada) == ("sql", "taller")


def test_un_archivo_de_afuera_no_se_clasifica():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.base / "otro" / "tres.sql", cargada) is None


def test_una_extension_sin_capa_no_se_clasifica():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.repo / "notas.txt", cargada) is None


def test_repo_de_dice_el_repo_y_su_arbol_aunque_el_archivo_no_tenga_capa():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        for ruta in (i.repo / "notas.txt", i.repo / "sp" / "Uno.sql", i.repo / "build.gradle"):
            dueno = m().repo_de(ruta, cargada)
            assert dueno is not None and dueno.repo == "db" and mismo(dueno.arbol, i.repo), (ruta, dueno)
        for ruta in (i.ticket / "SQL" / "dos.sql", i.base / "otro" / "tres.sql", i.raiz / "CLAUDE.md"):
            assert m().repo_de(ruta, cargada) is None, ruta


def test_repo_de_un_worktree_es_su_repo_con_el_arbol_del_worktree():
    with Instancia() as i:
        repo_con_commit(i.repo)
        arbol = i.base / "worktrees" / "db--rama"
        _git(i.repo, "worktree", "add", "-q", "-b", "rama", str(arbol))
        cargada = m().cargar(i.raiz)
        dueno = m().repo_de(arbol / "sp" / "notas.txt", cargada)
        assert dueno is not None and dueno.repo == "db" and mismo(dueno.arbol, arbol), dueno
        assert mismo(m().repo_de(i.repo / "notas.txt", cargada).arbol, i.repo)


def test_clasifica_con_la_letra_del_disco_en_otra_caja():
    if not EN_WINDOWS:
        return
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        ruta = str(i.repo / "sp" / "Uno.sql")
        otra_caja = (ruta[0].lower() if ruta[0].isupper() else ruta[0].upper()) + ruta[1:]
        assert m().clasificar(otra_caja, cargada) == ("sql", "db")


def test_clasifica_a_traves_de_una_junction():
    if not EN_WINDOWS:
        return
    with Instancia() as i:
        atajo = i.junction("atajo", i.repo)
        cargada = m().cargar(i.raiz)
        assert m().clasificar(atajo / "sp" / "Uno.sql", cargada) == ("sql", "db")


def test_el_repo_declarado_por_junction_reconoce_la_ruta_real():
    if not EN_WINDOWS:
        return
    with Instancia(local=False) as i:
        atajo = i.junction("atajo", i.repo)
        (i.raiz / "workspace.local.json").write_text(json.dumps({"repos": {"db": {"path": str(atajo)}}}), encoding="utf-8")
        cargada = m().cargar(i.raiz)
        assert m().clasificar(i.repo / "sp" / "Uno.sql", cargada) == ("sql", "db")


@contextlib.contextmanager
def plataforma(nombre):
    rutas = importlib.import_module("odd_ws.rutas")
    previa = rutas.PLATAFORMA
    rutas.PLATAFORMA = nombre
    try:
        yield
    finally:
        rutas.PLATAFORMA = previa


def test_en_macos_la_forma_canonica_pliega_mayusculas_y_nfd_como_apfs():
    with Instancia() as i:
        carpeta = i.base / "Año"
        carpeta.mkdir()
        real = str(carpeta / "x.sql")
        variantes = (real.upper(), real.replace("ñ", "n\u0303"))
        with plataforma("darwin"):
            for variante in variantes:
                assert m().canonica(variante) == m().canonica(real), variante
            cargada = m().cargar(i.raiz)
            assert m().clasificar(str(i.repo / "sp" / "Uno.sql").upper(), cargada) == ("sql", "db")
        with plataforma("linux"):
            assert m().canonica(variantes[1]) != m().canonica(real), "fuera de macOS, la forma NFD es otro nombre"


KNOWLEDGE_POR_DEFECTO = {"docs": None, "index": "CLAUDE.md", "index_max_lines": 200, "scan": [], "quantities": [], "claims": None}


def con_knowledge(valor):
    config = config_valida()
    config["knowledge"] = valor
    return config


def test_cargar_sigue_igual_que_antes_y_no_conoce_la_seccion_knowledge():
    with Instancia() as i:
        cargada = m().cargar(i.raiz)
        esperada = {
            "raiz": str(i.raiz),
            "schema_version": 1,
            "defaults": {"mold_source": "repo"},
            "repos": {"db": {"path": str(i.repo), "worktrees": []}},
            "layers": config_valida()["layers"],
        }
        assert cargada == esperada, cargada
        assert m().capas(i.raiz) == config_valida()["layers"]
        e = m().estado(i.raiz)
        assert e.tipo == "ok" and e.config == esperada, e


def test_cargar_ignora_la_seccion_knowledge_valida_o_invalida_y_solo_conocimiento_la_juzga():
    invalidas = ([], "docs", {"docz": "docs"}, {"index_max_lines": 0}, {"docs": 3}, {"scan": ["a[9-0]"]})
    validas = ({}, {"docs": "docs", "quantities": ["tablas"]})
    for valor in (*invalidas, *validas):
        with Instancia(config=con_knowledge(valor)) as i:
            con_seccion = m().cargar(i.raiz)
            estado = m().estado(i.raiz)
            assert m().capas(i.raiz) == config_valida()["layers"], valor
            (i.raiz / "workspace.config.json").write_text(json.dumps(config_valida()), encoding="utf-8")
            sin_seccion = m().cargar(i.raiz)
            assert "knowledge" not in con_seccion, (valor, con_seccion)
            assert con_seccion == sin_seccion, (valor, con_seccion, sin_seccion)
            assert estado.tipo == "ok" and estado.config == sin_seccion, (valor, estado)
    for valor in invalidas:
        with Instancia(config=con_knowledge(valor)) as i:
            try:
                m().conocimiento(i.raiz)
            except m().ConfigRota as error:
                assert "knowledge" in str(error), (valor, error)
            else:
                raise AssertionError(f"conocimiento() debe lanzar ConfigRota para {valor!r}")


def test_knowledge_vacio_da_los_valores_por_defecto():
    with Instancia(config=con_knowledge({})) as i:
        assert m().conocimiento(i.raiz) == KNOWLEDGE_POR_DEFECTO


def test_knowledge_completo_se_devuelve_tal_cual():
    completo = {
        "docs": "docs",
        "index": "README.md",
        "index_max_lines": 50,
        "scan": ["notas/**/*.md", "otro.md"],
        "quantities": ["tablas", "módulos"],
        "claims": "docs/afirmaciones.json",
    }
    with Instancia(config=con_knowledge(dict(completo))) as i:
        assert m().conocimiento(i.raiz) == completo


def test_knowledge_claims_por_defecto_cuelga_de_docs():
    for docs, claims in (("docs", "docs/_claims.json"), ("docs/", "docs/_claims.json"), ("a/b", "a/b/_claims.json"), (".", "_claims.json")):
        with Instancia(config=con_knowledge({"docs": docs})) as i:
            conocimiento = m().conocimiento(i.raiz)
            assert conocimiento["claims"] == claims, (docs, conocimiento)
            assert conocimiento["docs"] == os.path.normpath(docs).replace("\\", "/"), (docs, conocimiento)


def test_knowledge_sin_docs_no_inventa_el_archivo_de_afirmaciones():
    with Instancia(config=con_knowledge({"index": "LEEME.md"})) as i:
        assert m().conocimiento(i.raiz)["claims"] is None


def test_conocimiento_se_lee_sin_exigir_las_rutas_locales_de_los_repos():
    with Instancia(config=con_knowledge({"docs": "docs"}), local=False) as i:
        assert m().estado(i.raiz).tipo == "rota"
        assert m().conocimiento(i.raiz) == {**KNOWLEDGE_POR_DEFECTO, "docs": "docs", "claims": "docs/_claims.json"}


def test_conocimiento_sin_la_seccion_da_los_valores_por_defecto_y_valida_la_version():
    with Instancia() as i:
        assert m().conocimiento(i.raiz) == KNOWLEDGE_POR_DEFECTO
    config = config_valida()
    config["schema_version"] = 2
    with Instancia(config=config) as i:
        try:
            m().conocimiento(i.raiz)
        except m().ConfigRota as error:
            assert "schema_version" in str(error), error
        else:
            raise AssertionError("una schema_version desconocida debe lanzar ConfigRota")


def _rota_por_knowledge(valor, esperado):
    with Instancia(config=con_knowledge(valor)) as i:
        assert m().estado(i.raiz).tipo == "ok", valor
        try:
            m().conocimiento(i.raiz)
        except m().ConfigRota as error:
            assert "knowledge" in str(error) and all(t in str(error) for t in esperado), (valor, str(error))
        else:
            raise AssertionError(f"conocimiento() debe lanzar ConfigRota para {valor!r}")


def test_knowledge_que_no_es_un_objeto_es_rota():
    for malo in ([], "docs", 3, None, True):
        _rota_por_knowledge(malo, ["objeto"])


def test_knowledge_con_una_clave_desconocida_es_rota():
    _rota_por_knowledge({"docz": "docs"}, ["docz"])
    _rota_por_knowledge({"docs": "docs", "Docs": "x"}, ["Docs"])


def test_knowledge_rutas_invalidas_son_rota():
    malas = (3, True, None, ["x"], {}, "", "/abs", "C:/x", "C:\\x", "a\\b", "../fuera", "a/../b", "..")
    for campo in ("docs", "index", "claims"):
        for malo in malas:
            _rota_por_knowledge({campo: malo}, [f"knowledge.{campo}"])


def test_knowledge_rutas_relativas_validas_se_aceptan_y_se_normalizan():
    with Instancia(config=con_knowledge({"docs": "./docs//sub/", "index": "./LEEME.md", "claims": "x/./c.json"})) as i:
        conocimiento = m().conocimiento(i.raiz)
        assert conocimiento["docs"] == "docs/sub", conocimiento
        assert conocimiento["index"] == "LEEME.md", conocimiento
        assert conocimiento["claims"] == "x/c.json", conocimiento


def test_knowledge_tope_del_indice_invalido_es_rota():
    for malo in (0, -1, 1.5, "200", True, False, None, [200]):
        _rota_por_knowledge({"index_max_lines": malo}, ["knowledge.index_max_lines"])


def test_knowledge_tope_del_indice_valido():
    for valido in (1, 200, 5000):
        with Instancia(config=con_knowledge({"index_max_lines": valido})) as i:
            assert m().conocimiento(i.raiz)["index_max_lines"] == valido


def test_knowledge_scan_invalido_es_rota():
    for malo in ("docs/*.md", [""], [3], [None], None, {}, ["ok", ""]):
        _rota_por_knowledge({"scan": malo}, ["knowledge.scan"])


def test_knowledge_scan_con_un_glob_mal_formado_es_rota_y_nombra_el_glob():
    for malo in ("notas/[z-a]*.md", "a[9-0]"):
        _rota_por_knowledge({"scan": ["ok/*.md", malo]}, ["knowledge.scan", malo])


def test_knowledge_scan_vacio_es_valido():
    with Instancia(config=con_knowledge({"scan": []})) as i:
        assert m().conocimiento(i.raiz)["scan"] == []


def test_knowledge_vocabulario_de_cifras_invalido_es_rota():
    for malo in ("tablas", [""], [3], [None], None, {}, [" tablas"], ["tablas "], ["ok", " "]):
        _rota_por_knowledge({"quantities": malo}, ["knowledge.quantities"])


def test_knowledge_vocabulario_de_cifras_valido_conserva_el_orden_y_los_acentos():
    with Instancia(config=con_knowledge({"quantities": ["módulos", "tablas", "work items"]})) as i:
        assert m().conocimiento(i.raiz)["quantities"] == ["módulos", "tablas", "work items"]


def test_knowledge_roto_no_cambia_el_error_de_las_otras_secciones():
    config = con_knowledge({"docs": 3})
    config["layers"]["sql"]["extensions"] = ["sql"]
    with Instancia(config=config) as i:
        e = m().estado(i.raiz)
        assert e.tipo == "rota" and "extensions" in e.razon and "knowledge" not in e.razon, e


def test_knowledge_no_devuelve_las_listas_de_la_config_original():
    config = con_knowledge({"scan": ["a/*.md"], "quantities": ["tablas"]})
    resultado = m()._conocimiento(config)
    resultado["scan"].append("b")
    resultado["quantities"].append("c")
    assert config["knowledge"] == {"scan": ["a/*.md"], "quantities": ["tablas"]}, config


def con_hosts(valor):
    config = config_valida()
    config["hosts"] = valor
    return config


def _rota_por_hosts(valor, esperado):
    with Instancia(config=con_hosts(valor)) as i:
        assert m().estado(i.raiz).tipo == "ok", valor
        try:
            m().hosts(i.raiz)
        except m().ConfigRota as error:
            assert str(error).startswith("hosts") and all(t in str(error) for t in esperado), (valor, str(error))
        else:
            raise AssertionError(f"hosts() debe lanzar ConfigRota para {valor!r}")
    try:
        m().hosts_de({"hosts": valor})
    except m().ConfigRota:
        return
    raise AssertionError(f"hosts_de() debe lanzar ConfigRota para {valor!r}")


def test_sin_hosts_la_instancia_es_solo_de_claude_code():
    with Instancia() as i:
        assert m().hosts(i.raiz) == ["claude-code"]
    assert m().hosts_de({}) == ["claude-code"]
    assert m().HOSTS_POR_DEFECTO == ("claude-code",)


def test_hosts_validos_se_devuelven_en_su_orden():
    for valor in (["claude-code"], ["codex"], ["claude-code", "codex"], ["codex", "claude-code"], ["pi"], ["pi", "claude-code"],
                  ["claude-code", "codex", "pi"]):
        with Instancia(config=con_hosts(list(valor))) as i:
            assert m().hosts(i.raiz) == valor, valor


def test_los_hosts_validos_son_los_del_registro():
    registro = importlib.import_module("odd_ws.hosts")
    assert list(registro.NOMBRES) == ["claude-code", "codex", "pi"]
    for nombre in registro.NOMBRES:
        assert m().hosts_de({"hosts": [nombre]}) == [nombre], nombre
    assert m().hosts_de({"hosts": list(registro.NOMBRES)}) == list(registro.NOMBRES)


def test_hosts_que_no_es_una_lista_no_vacia_de_textos_es_rota():
    for malo in ("codex", {"codex": True}, None, 3, True, [], [1], [None], [["codex"]], ["codex", 2]):
        _rota_por_hosts(malo, ["lista no vacía", "claude-code, codex, pi"])


def test_un_host_desconocido_es_rota_y_nombra_los_validos():
    for malo in (["claude"], ["Codex"], ["gemini"], [""], ["claude-code", "opencode"], [" codex"], ["codex "], ["Pi"],
                 ["gentle-shell"], ["pi", "gentle-pi"]):
        desconocido = next(h for h in malo if h not in ("claude-code", "codex", "pi"))
        _rota_por_hosts(malo, [repr(desconocido), "no es un host conocido", "claude-code, codex, pi"])


def test_un_host_repetido_es_rota():
    for malo, repetido in ((["codex", "codex"], "codex"), (["claude-code", "codex", "claude-code"], "claude-code")):
        _rota_por_hosts(malo, [repr(repetido), "repetido"])


def test_cargar_ignora_hosts_valido_o_invalido_y_solo_hosts_lo_juzga():
    for valor in ("codex", [], ["codex", "codex"], ["gemini"], ["codex"], ["claude-code", "codex"]):
        with Instancia(config=con_hosts(valor)) as i:
            con_clave = m().cargar(i.raiz)
            estado = m().estado(i.raiz)
            assert m().capas(i.raiz) == config_valida()["layers"], valor
            assert m().conocimiento(i.raiz) == KNOWLEDGE_POR_DEFECTO, valor
            (i.raiz / "workspace.config.json").write_text(json.dumps(config_valida()), encoding="utf-8")
            sin_clave = m().cargar(i.raiz)
            assert "hosts" not in con_clave and con_clave == sin_clave, (valor, con_clave)
            assert estado.tipo == "ok" and estado.config == sin_clave, (valor, estado)


def test_hosts_valida_la_version_y_no_exige_las_rutas_locales():
    config = con_hosts(["codex"])
    with Instancia(config=config, local=False) as i:
        assert m().estado(i.raiz).tipo == "rota"
        assert m().hosts(i.raiz) == ["codex"]
    config["schema_version"] = 2
    with Instancia(config=config) as i:
        try:
            m().hosts(i.raiz)
        except m().ConfigRota as error:
            assert "schema_version" in str(error), error
        else:
            raise AssertionError("una schema_version desconocida debe lanzar ConfigRota")


def test_hosts_no_devuelve_la_lista_de_la_config_original():
    config = con_hosts(["codex"])
    resultado = m().hosts_de(config)
    resultado.append("x")
    assert config["hosts"] == ["codex"], config
    por_defecto = m().hosts_de({})
    por_defecto.append("x")
    assert m().hosts_de({}) == ["claude-code"]


def con_tickets(valor):
    config = config_valida()
    config["tickets"] = valor
    return config


def test_sin_tickets_no_hay_prefijo():
    with Instancia() as i:
        assert m().prefijo_de_tickets(i.raiz) is None
    assert m().tickets_de({}) is None


def test_un_prefijo_de_tickets_valido_se_devuelve_tal_cual():
    for prefijo in ("T", "SM", "sm", "Ab_9", "x" * 32):
        with Instancia(config=con_tickets({"prefix": prefijo})) as i:
            assert m().prefijo_de_tickets(i.raiz) == prefijo, prefijo


def test_tickets_mal_formado_es_rota_y_cargar_no_lo_ve():
    for malo in ("SM", None, [], {}, {"prefix": ""}, {"prefix": 3}, {"prefix": "S-M"}, {"prefix": "9A"}, {"prefix": "_A"},
                 {"prefix": "x" * 33}, {"prefix": "SM", "otra": 1}, {"prefix": "S M"}, {"prefix": "SÑ"}):
        with Instancia(config=con_tickets(malo)) as i:
            assert m().estado(i.raiz).tipo == "ok", malo
            try:
                m().prefijo_de_tickets(i.raiz)
            except m().ConfigRota as error:
                assert str(error).startswith("tickets"), (malo, str(error))
            else:
                raise AssertionError(f"prefijo_de_tickets() debe lanzar ConfigRota para {malo!r}")


def con_clave(clave, valor):
    config = config_valida()
    config[clave] = valor
    return config


def test_sin_ask_before_commit_el_agente_commitea_sin_preguntar():
    with Instancia() as i:
        assert m().pide_aprobar_commits(i.raiz) is False
    assert m().aprobacion_de_commits({}) is False


def test_ask_before_commit_booleano_se_devuelve_tal_cual():
    for valor in (True, False):
        with Instancia(config=con_clave("ask_before_commit", valor)) as i:
            assert m().pide_aprobar_commits(i.raiz) is valor, valor


def test_ask_before_commit_que_no_es_booleano_es_rota_y_cargar_no_lo_ve():
    for malo in ("true", 1, 0, None, [], {}):
        with Instancia(config=con_clave("ask_before_commit", malo)) as i:
            assert m().estado(i.raiz).tipo == "ok", malo
            try:
                m().pide_aprobar_commits(i.raiz)
            except m().ConfigRota as error:
                assert str(error).startswith("ask_before_commit"), (malo, str(error))
            else:
                raise AssertionError(f"pide_aprobar_commits() debe lanzar ConfigRota para {malo!r}")


def test_los_repos_propios_son_los_marcados_con_own_en_su_orden():
    config = config_valida()
    config["repos"] = {"db": {"own": True}, "web": {}, "app": {"own": False}, "api": {"own": True, "agent_readonly": False}}
    assert m().propios_de(config) == ["db", "api"]
    assert m().propios_de(config_valida()) == []
    assert m().propios_de({}) == []


def test_own_que_no_es_booleano_o_con_agent_readonly_es_rota_y_cargar_no_lo_ve():
    for valores, fragmento in (({"own": "si"}, "repos.db.own debe ser true o false"), ({"own": 1}, "repos.db.own debe ser true o false"),
                               ({"own": True, "agent_readonly": True}, "repos.db no puede ser own y agent_readonly")):
        config = config_valida()
        config["repos"] = {"db": valores}
        try:
            m().propios_de(config)
        except m().ConfigRota as error:
            assert fragmento in str(error), (valores, str(error))
        else:
            raise AssertionError(f"propios_de() debe lanzar ConfigRota para {valores!r}")
        with Instancia(config=config) as i:
            assert m().estado(i.raiz).tipo == "ok", valores
            try:
                m().repos_propios(i.raiz)
            except m().ConfigRota:
                pass
            else:
                raise AssertionError(f"repos_propios() debe lanzar ConfigRota para {valores!r}")


CINCO_HOOKS = ["verificar_capa", "guard_comandos", "revisar_turno", "writer_guard", "writer_stop"]


def test_los_hooks_que_se_pueden_apagar_son_los_cinco_scripts_registrados_en_los_tres_hosts():
    assert list(m().HOOKS) == CINCO_HOOKS, m().HOOKS
    for archivo in ("hooks.json", "hooks.codex.json", "hooks.pi.json"):
        texto = (AQUI.parent / "hooks" / archivo).read_text(encoding="utf-8")
        registrados = {Path(nombre).stem for nombre in re.findall(r"[a-z_]+\.py", texto)}
        assert registrados == set(CINCO_HOOKS), (archivo, registrados)


def test_sin_disabled_hooks_no_se_apaga_ninguno():
    assert m().hooks_apagados_de({}) == []
    with Instancia() as i:
        assert m().hooks_apagados(i.raiz) == []
        assert not [nombre for nombre in CINCO_HOOKS if m().hook_apagado(i.raiz, nombre)]


def test_disabled_hooks_valido_apaga_solo_los_que_nombra_en_su_orden():
    for valor in ([], ["guard_comandos"], ["writer_stop", "verificar_capa"], list(CINCO_HOOKS), list(reversed(CINCO_HOOKS))):
        assert m().hooks_apagados_de({"disabled_hooks": list(valor)}) == valor, valor
        with Instancia(config=con_clave("disabled_hooks", list(valor))) as i:
            assert m().hooks_apagados(i.raiz) == valor, valor
            apagados = [nombre for nombre in CINCO_HOOKS if m().hook_apagado(i.raiz, nombre)]
            assert apagados == [nombre for nombre in CINCO_HOOKS if nombre in valor], (valor, apagados)


def test_disabled_hooks_invalido_es_rota_y_no_apaga_ninguno():
    malos = ("guard_comandos", None, 3, True, {"guard_comandos": True}, [1], [None], [["guard_comandos"]], ["guard-comandos"],
             ["guard_comandos.py"], ["Guard_comandos"], [" guard_comandos"], ["recibo"], ["guard_comandos", "guard_comandos"],
             ["guard_comandos", 2])
    for malo in malos:
        try:
            m().hooks_apagados_de({"disabled_hooks": malo})
        except m().ConfigRota as error:
            assert str(error).startswith("disabled_hooks"), (malo, str(error))
        else:
            raise AssertionError(f"hooks_apagados_de() debe lanzar ConfigRota para {malo!r}")
        with Instancia(config=con_clave("disabled_hooks", malo)) as i:
            assert m().estado(i.raiz).tipo == "ok", malo
            try:
                m().hooks_apagados(i.raiz)
            except m().ConfigRota:
                pass
            else:
                raise AssertionError(f"hooks_apagados() debe lanzar ConfigRota para {malo!r}")
            assert not [nombre for nombre in CINCO_HOOKS if m().hook_apagado(i.raiz, nombre)], malo


def test_cargar_ignora_disabled_hooks_y_hook_apagado_lee_solo_la_clave_y_la_version():
    with Instancia(config=con_clave("disabled_hooks", ["guard_comandos"])) as i:
        cargada = m().cargar(i.raiz)
        (i.raiz / "workspace.config.json").write_text(json.dumps(config_valida()), encoding="utf-8")
        assert "disabled_hooks" not in cargada and cargada == m().cargar(i.raiz), cargada
    with Instancia(config=con_clave("disabled_hooks", ["guard_comandos"]), local=False) as i:
        assert m().estado(i.raiz).tipo == "rota"
        assert m().hook_apagado(i.raiz, "guard_comandos") is True
    config = con_clave("disabled_hooks", ["guard_comandos"])
    config["schema_version"] = 2
    with Instancia(config=config) as i:
        assert m().hook_apagado(i.raiz, "guard_comandos") is False
    with Instancia(config='{"schema_version": 1, "disabled_hooks": ["guard_comandos"]') as i:
        assert m().hook_apagado(i.raiz, "guard_comandos") is False
    with Instancia(config=False) as i:
        assert m().hook_apagado(i.raiz, "guard_comandos") is False


def test_sin_profile_el_perfil_es_completo():
    assert (m().COMPLETO, m().CONTROLES, m().CLAVE_DE_PERFIL) == ("completo", "controles", "profile")
    assert m().perfil_de({}) == "completo"
    with Instancia() as i:
        assert m().perfil(i.raiz) == "completo"
        assert m().es_controles(i.raiz) is False


def test_profile_valido_se_devuelve_tal_cual():
    for valor in ("completo", "controles"):
        assert m().perfil_de({"profile": valor}) == valor
        with Instancia(config=con_clave("profile", valor)) as i:
            assert m().perfil(i.raiz) == valor
            assert m().es_controles(i.raiz) is (valor == "controles"), valor


def test_profile_invalido_es_rota_y_no_es_controles():
    for malo in ("Controles", "control", " controles", "", None, 1, True, ["controles"], {"controles": True}):
        try:
            m().perfil_de({"profile": malo})
        except m().ConfigRota as error:
            assert str(error).startswith("profile") and "completo" in str(error) and "controles" in str(error), (malo, str(error))
        else:
            raise AssertionError(f"perfil_de() debe lanzar ConfigRota para {malo!r}")
        with Instancia(config=con_clave("profile", malo)) as i:
            assert m().estado(i.raiz).tipo == "ok", malo
            try:
                m().perfil(i.raiz)
            except m().ConfigRota:
                pass
            else:
                raise AssertionError(f"perfil() debe lanzar ConfigRota para {malo!r}")
            assert m().es_controles(i.raiz) is False, malo


def test_porque_al_editar_sin_la_clave_es_todo_y_cada_valor_valido_sale_tal_cual():
    assert (m().CLAVE_DEL_PORQUE, m().MODOS_DEL_PORQUE) == ("porque_al_editar", ("todo", "indice", "apagado"))
    assert m().porque_al_editar_de({}) == "todo"
    with Instancia() as i:
        assert m().porque_al_editar(i.raiz) == "todo" and m().modo_del_porque(i.raiz) == "todo"
    for valor in ("todo", "indice", "apagado"):
        assert m().porque_al_editar_de({"porque_al_editar": valor}) == valor
        with Instancia(config=con_clave("porque_al_editar", valor)) as i:
            assert m().porque_al_editar(i.raiz) == valor and m().modo_del_porque(i.raiz) == valor, valor
            cargada = m().cargar(i.raiz)
            assert "porque_al_editar" not in cargada, cargada


def test_porque_al_editar_invalido_es_rota_y_el_hook_lo_lee_como_todo():
    for malo in ("Todo", "off", "índice", " todo", "", None, 1, True, ["todo"], {"todo": True}):
        try:
            m().porque_al_editar_de({"porque_al_editar": malo})
        except m().ConfigRota as error:
            assert str(error).startswith("porque_al_editar") and "todo | indice | apagado" in str(error), (malo, str(error))
        else:
            raise AssertionError(f"porque_al_editar_de() debe lanzar ConfigRota para {malo!r}")
        with Instancia(config=con_clave("porque_al_editar", malo)) as i:
            assert m().estado(i.raiz).tipo == "ok", malo
            try:
                m().porque_al_editar(i.raiz)
            except m().ConfigRota:
                pass
            else:
                raise AssertionError(f"porque_al_editar() debe lanzar ConfigRota para {malo!r}")
            assert m().modo_del_porque(i.raiz) == "todo", malo
    with Instancia(config='{"schema_version": 1, "porque_al_editar": "apagado"') as i:
        assert m().modo_del_porque(i.raiz) == "todo"
    assert m().modo_del_porque(None) == "todo"


def test_cargar_ignora_profile_y_es_controles_lee_solo_la_clave_y_la_version():
    with Instancia(config=con_clave("profile", "controles")) as i:
        cargada = m().cargar(i.raiz)
        (i.raiz / "workspace.config.json").write_text(json.dumps(config_valida()), encoding="utf-8")
        assert "profile" not in cargada and cargada == m().cargar(i.raiz), cargada
    with Instancia(config=con_clave("profile", "controles"), local=False) as i:
        assert m().estado(i.raiz).tipo == "rota"
        assert m().es_controles(i.raiz) is True
    config = con_clave("profile", "controles")
    config["schema_version"] = 2
    with Instancia(config=config) as i:
        assert m().es_controles(i.raiz) is False
    with Instancia(config='{"schema_version": 1, "profile": "controles"') as i:
        assert m().es_controles(i.raiz) is False
    with Instancia(config=False) as i:
        assert m().es_controles(i.raiz) is False
    assert m().es_controles(None) is False


SKILLS = AQUI.parent / "skills"
GUARDA_DE_CONTROLES = "**Perfil `controles`.**"


def test_las_skills_que_no_aplican_en_controles_lo_dicen_antes_de_su_primer_paso():
    clave = f'"{m().CLAVE_DE_PERFIL}": "{m().CONTROLES}"'
    for nombre in ("revisar", "abrir", "cerrar", "eval-reviewers"):
        lineas = (SKILLS / nombre / "SKILL.md").read_text(encoding="utf-8").split("\n")
        guardas = [n for n, linea in enumerate(lineas) if linea.startswith(GUARDA_DE_CONTROLES)]
        assert len(guardas) == 1, (nombre, guardas)
        guarda = lineas[guardas[0]]
        primera_seccion = next(n for n, linea in enumerate(lineas) if linea.startswith("## "))
        assert guardas[0] < primera_seccion, (nombre, guardas[0], primera_seccion)
        for pedazo in (clave, m().NOMBRE, "no aplica"):
            assert pedazo in guarda, (nombre, pedazo, guarda)
        assert "y detente," in guarda or "y detente." in guarda, (nombre, guarda)
    cerrar = next(linea for linea in (SKILLS / "cerrar" / "SKILL.md").read_text(encoding="utf-8").split("\n")
                  if linea.startswith(GUARDA_DE_CONTROLES))
    assert "memorias" in cerrar and "/odd-ws:cerrar memorias" in cerrar, cerrar
    for nombre in ("bootstrap", "doctor", "conocimiento", "enlaces", "paquetes"):
        texto = (SKILLS / nombre / "SKILL.md").read_text(encoding="utf-8")
        assert GUARDA_DE_CONTROLES not in texto, nombre


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
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
