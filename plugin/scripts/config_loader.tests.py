import importlib
import json
import os
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
