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
