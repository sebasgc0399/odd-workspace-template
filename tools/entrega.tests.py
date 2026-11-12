import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "entrega.py"
BARRIDO = AQUI / "barrido.py"
NOTAS = AQUI / "notas.py"
HOOKS = AQUI.parent / ".githooks"
CEROS = "0" * 40
PLUGIN_JSON = "plugin/.claude-plugin/plugin.json"
LISTA_DE_PRUEBA = "# lista sintetica\n\nAcmeCorp\n"


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def plugin_json(version):
    return json.dumps({"name": "odd-ws", "version": version}) + "\n"


def notas_de(*versiones):
    return "# Changelog\n" + "".join(f"\n## {version}\n\n- cambios de la {version}\n" for version in versiones)


WORKFLOW = ".github/workflows/release.yml"
CON_WORKFLOW = {WORKFLOW: "name: release\n"}


def a_etiqueta(version, objeto, remoto=CEROS):
    return f"refs/tags/odd-ws--v{version} {objeto} refs/tags/odd-ws--v{version} {remoto}"


class Escenario:
    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="entrega-"))
        for nombre in ("gitconfig-global", "gitconfig-sistema"):
            (self.dir / nombre).write_text("", encoding="utf-8")
        self.lista = self.dir / "denylist.txt"
        self.lista.write_text(LISTA_DE_PRUEBA, encoding="utf-8")
        self.env = {clave: valor for clave, valor in os.environ.items() if not clave.startswith("GIT_")}
        self.env.update(
            GIT_CONFIG_GLOBAL=str(self.dir / "gitconfig-global"),
            GIT_CONFIG_SYSTEM=str(self.dir / "gitconfig-sistema"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="prueba",
            GIT_AUTHOR_EMAIL="prueba@example.com",
            GIT_COMMITTER_NAME="prueba",
            GIT_COMMITTER_EMAIL="prueba@example.com",
            ODD_WS_DENYLIST=str(self.lista),
        )
        self.obra = self.dir / "obra"
        self.obra.mkdir()
        self.git("init", "-q", "-b", "main")
        return self

    def __exit__(self, *_):
        shutil.rmtree(self.dir, onexc=_forzar_borrado)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.obra, env=self.env, capture_output=True, check=True)

    def git_salida(self, *args):
        return self.git(*args).stdout.decode("utf-8").strip()

    def commit(self, archivos, mensaje="cambio"):
        for ruta, contenido in archivos.items():
            destino = self.obra / ruta
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(contenido, encoding="utf-8")
            self.git("add", ruta)
        self.git("commit", "-q", "--no-verify", "-m", mensaje)
        return self.git_salida("rev-parse", "HEAD")

    def etiquetar(self, version, sha=None):
        self.git("tag", "-a", f"odd-ws--v{version}", "-m", f"entrega {version}", *([sha] if sha else []))

    def entrega_inicial(self, version="0.1.0"):
        sha = self.commit({PLUGIN_JSON: plugin_json(version), "plugin/skills/uno.md": "uno\n", "README.md": "base\n"}, "base")
        self.etiquetar(version)
        return sha

    def correr(self, lineas, cwd=None):
        entrada = "".join(f"{linea}\n" for linea in lineas).encode("utf-8")
        resultado = subprocess.run([sys.executable, str(SCRIPT)], cwd=cwd or self.obra, env=self.env, capture_output=True, input=entrada)
        salida = resultado.stdout.decode("utf-8", "replace").splitlines()
        return resultado.returncode, "".join(f"{linea}\n" for linea in salida), resultado.stderr.decode("utf-8", "replace")


def a_main(sha, remoto=CEROS):
    return f"refs/heads/main {sha} refs/heads/main {remoto}"


def asegurar(resultado, esperado_codigo, esperado_salida, *en_el_error):
    codigo, salida, error = resultado
    assert codigo == esperado_codigo, (codigo, salida, error)
    assert salida == esperado_salida, (salida, error)
    for fragmento in en_el_error:
        assert fragmento in error, (fragmento, error)
    if not en_el_error:
        assert error == "", error


def test_un_push_a_otra_rama_con_cambios_en_plugin_pasa_sin_decir_nada():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"plugin/skills/uno.md": "dos\n"})
        asegurar(e.correr([f"refs/heads/feature {sha} refs/heads/feature {CEROS}"]), 0, "")


def test_un_push_de_una_etiqueta_pasa_sin_decir_nada():
    with Escenario() as e:
        sha = e.entrega_inicial()
        asegurar(e.correr([f"refs/tags/odd-ws--v0.1.0 {sha} refs/tags/odd-ws--v0.1.0 {CEROS}"]), 0, "")


def test_el_borrado_de_main_se_ignora():
    with Escenario() as e:
        sha = e.entrega_inicial()
        asegurar(e.correr([f"(delete) {CEROS} refs/heads/main {sha}"]), 0, "")


def test_main_con_cambios_solo_fuera_de_plugin_desde_la_etiqueta_pasa():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"README.md": "otro\n", "tools/x.py": "x\n"})
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_main_con_cambios_en_plugin_sin_subir_la_version_bloquea():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"plugin/skills/uno.md": "dos\n"})
        asegurar(
            e.correr([a_main(sha)]), 1, "",
            "ENTREGA BLOQUEADA", "cambia plugin/ desde odd-ws--v0.1.0", f"{sha[:7]} no tiene la etiqueta odd-ws--v0.1.0",
            "la versión sigue en 0.1.0", "Subí «version» en plugin/.claude-plugin/plugin.json", "claude plugin tag ./plugin", "junto con la rama",
        )


def test_version_subida_sin_etiqueta_bloquea():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n"})
        resultado = e.correr([a_main(sha)])
        asegurar(resultado, 1, "", "ENTREGA BLOQUEADA", "desde odd-ws--v0.1.0", f"{sha[:7]} no tiene la etiqueta odd-ws--v0.2.0")
        assert "la versión sigue" not in resultado[2], resultado


def test_etiqueta_de_la_version_en_otro_commit_bloquea():
    with Escenario() as e:
        e.entrega_inicial()
        e.git("checkout", "-q", "-b", "lateral")
        ajeno = e.commit({PLUGIN_JSON: plugin_json("0.2.0")})
        e.etiquetar("0.2.0")
        e.git("checkout", "-q", "main")
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "tres\n"})
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "desde odd-ws--v0.1.0", f"la etiqueta odd-ws--v0.2.0 apunta a {ajeno[:7]} y no a {sha[:7]}")


def test_version_subida_y_etiqueta_en_el_commit_pasa():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", "CHANGELOG.md": notas_de("0.2.0", "0.1.0")})
        e.etiquetar("0.2.0")
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_una_entrega_sin_changelog_bloquea_y_dice_que_escribir():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", **CON_WORKFLOW})
        e.etiquetar("0.2.0")
        asegurar(
            e.correr([a_main(sha)]), 1, "",
            "ENTREGA BLOQUEADA", "entrega odd-ws--v0.2.0", f"CHANGELOG.md en {sha[:7]} no tiene notas para 0.2.0",
            "«## 0.2.0»", ".github/workflows/release.yml",
        )


def test_una_entrega_con_changelog_sin_la_seccion_de_su_version_o_vacia_bloquea():
    with Escenario() as e:
        e.entrega_inicial()
        for changelog in (notas_de("0.1.0"), "# Changelog\n\n## 0.2.0\n\n## 0.1.0\n\n- algo\n"):
            sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": changelog, "CHANGELOG.md": changelog, **CON_WORKFLOW})
            e.etiquetar("0.2.0")
            asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "no tiene notas para 0.2.0")
            e.git("tag", "-d", "odd-ws--v0.2.0")


def test_una_seccion_sin_publicar_no_cuenta_como_las_notas_de_una_version():
    with Escenario() as e:
        e.entrega_inicial()
        sin_publicar = "# Changelog\n\n## Sin publicar\n\n- lo que viene\n\n## 0.1.0\n\n- algo\n"
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", "CHANGELOG.md": sin_publicar, **CON_WORKFLOW})
        e.etiquetar("0.2.0")
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "no tiene notas para 0.2.0")
        e.git("tag", "-d", "odd-ws--v0.2.0")
        con_version = sin_publicar.replace("## 0.1.0", "## 0.2.0\n\n- cambios de la 0.2.0\n\n## 0.1.0")
        sha = e.commit({"CHANGELOG.md": con_version})
        e.etiquetar("0.2.0")
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_una_entrega_de_un_commit_sin_el_workflow_no_pide_notas():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n"})
        e.etiquetar("0.2.0")
        asegurar(e.correr([a_main(sha), a_etiqueta("0.2.0", e.git_salida("rev-parse", "odd-ws--v0.2.0"))]), 0, "entrega limpia\n")


def test_una_etiqueta_empujada_detras_de_main_tambien_exige_sus_notas():
    with Escenario() as e:
        e.entrega_inicial()
        e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", **CON_WORKFLOW})
        e.etiquetar("0.2.0")
        punta = e.commit({"README.md": "otro\n"})
        objeto = e.git_salida("rev-parse", "odd-ws--v0.2.0")
        asegurar(e.correr([a_main(punta), a_etiqueta("0.2.0", objeto)]), 1, "", "ENTREGA BLOQUEADA", "entrega odd-ws--v0.2.0", "no tiene notas para 0.2.0")
        asegurar(e.correr([a_etiqueta("0.2.0", objeto)]), 1, "", "ENTREGA BLOQUEADA", "no tiene notas para 0.2.0")


def test_una_etiqueta_empujada_con_sus_notas_pasa_y_una_ajena_a_su_version_bloquea():
    with Escenario() as e:
        e.entrega_inicial()
        e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", "CHANGELOG.md": notas_de("0.2.0"), **CON_WORKFLOW})
        e.etiquetar("0.2.0")
        e.etiquetar("0.9.0")
        asegurar(e.correr([a_etiqueta("0.2.0", e.git_salida("rev-parse", "odd-ws--v0.2.0"))]), 0, "entrega limpia\n")
        asegurar(
            e.correr([a_etiqueta("0.9.0", e.git_salida("rev-parse", "odd-ws--v0.9.0"))]), 1, "",
            "ENTREGA BLOQUEADA", "odd-ws--v0.9.0", "dice 0.2.0", "debería ser odd-ws--v0.2.0",
        )


def test_el_borrado_de_una_etiqueta_se_ignora():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", **CON_WORKFLOW})
        e.etiquetar("0.2.0")
        asegurar(e.correr([f"(delete) {CEROS} refs/tags/odd-ws--v0.2.0 {sha}"]), 0, "")


def test_un_push_a_main_que_no_entrega_no_pide_notas():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"README.md": "otro\n", "CHANGELOG.md": "# Changelog\n"})
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_sin_ninguna_etiqueta_y_con_plugin_bloquea_y_pasa_al_etiquetar():
    with Escenario() as e:
        sha = e.commit({PLUGIN_JSON: plugin_json("0.1.0"), "CHANGELOG.md": notas_de("0.1.0")})
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "desde el inicio", f"{sha[:7]} no tiene la etiqueta odd-ws--v0.1.0")
        e.etiquetar("0.1.0")
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_una_etiqueta_ajena_no_cuenta_como_entrega():
    with Escenario() as e:
        sha = e.commit({PLUGIN_JSON: plugin_json("0.1.0")})
        e.git("tag", "-a", "v9.9.9", "-m", "ajena")
        asegurar(e.correr([a_main(sha)]), 1, "", "desde el inicio")


def test_una_etiqueta_a_mano_con_otro_nombre_que_la_version_bloquea_y_dice_como_arreglarlo():
    with Escenario() as e:
        e.entrega_inicial("0.3.0")
        sha = e.commit({"plugin/x.txt": "x\n"})
        for nombre in ("0.4.0", "9.9.9"):
            e.etiquetar(nombre)
            asegurar(
                e.correr([a_main(sha)]), 1, "",
                "ENTREGA BLOQUEADA", f"odd-ws--v{nombre}", "dice 0.3.0", "debería ser odd-ws--v0.3.0", "claude plugin tag ./plugin", "Subí «version»",
            )
            e.git("tag", "-d", f"odd-ws--v{nombre}")


def test_el_hook_frena_el_push_a_main_con_una_etiqueta_a_mano_que_no_es_la_version():
    with Escenario() as e:
        repo = RepoConHook(e)
        e.entrega_inicial("0.3.0")
        e.commit({"plugin/x.txt": "x\n"})
        e.etiquetar("0.4.0")
        codigo, salida = repo.empujar("main", "refs/tags/odd-ws--v0.4.0")
        assert codigo != 0, salida
        assert "ENTREGA BLOQUEADA" in salida and "odd-ws--v0.4.0" in salida, salida
        assert repo.en_el_remoto("refs/heads/main") is None


def test_una_etiqueta_a_mano_vieja_con_nombre_distinto_de_su_version_bloquea_aunque_no_haya_cambios_despues():
    with Escenario() as e:
        e.commit({PLUGIN_JSON: plugin_json("0.3.0"), "plugin/skills/uno.md": "uno\n"}, "base")
        e.etiquetar("0.5.0")
        sha = e.commit({"README.md": "otro\n"})
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "odd-ws--v0.5.0", "dice 0.3.0", "debería ser odd-ws--v0.3.0")


def test_con_varias_lineas_basta_una_de_main_que_falle_para_bloquear():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"plugin/skills/uno.md": "dos\n"})
        lineas = [f"refs/heads/feature {sha} refs/heads/feature {CEROS}", a_main(sha), f"refs/tags/x {sha} refs/tags/x {CEROS}"]
        asegurar(e.correr(lineas), 1, "", "ENTREGA BLOQUEADA", f"{sha[:7]} no tiene la etiqueta")


def test_con_varias_lineas_todas_en_regla_pasan():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"plugin/skills/uno.md": "dos\n", PLUGIN_JSON: plugin_json("0.2.0"), "CHANGELOG.md": notas_de("0.2.0")})
        e.etiquetar("0.2.0")
        lineas = [f"refs/heads/feature {sha} refs/heads/feature {CEROS}", a_main(sha)]
        asegurar(e.correr(lineas), 0, "entrega limpia\n")


def test_plugin_json_ilegible_bloquea_y_dice_por_que():
    with Escenario() as e:
        e.entrega_inicial()
        casos = [
            ("{no es json", "no es un JSON legible"),
            ('{"name": "odd-ws"}', "no tiene un «version» válido"),
            ('{"version": 2}', "no tiene un «version» válido"),
            ('{"version": "dos"}', "no tiene un «version» válido"),
            ('["version"]', "no tiene un «version» válido"),
        ]
        for contenido, motivo in casos:
            sha = e.commit({PLUGIN_JSON: contenido, "plugin/skills/uno.md": contenido})
            asegurar(e.correr([a_main(sha)]), 2, "", "ENTREGA BLOQUEADA", motivo)


def test_sin_plugin_json_en_el_commit_bloquea_y_dice_por_que():
    with Escenario() as e:
        e.entrega_inicial()
        e.git("rm", "-q", PLUGIN_JSON)
        e.git("commit", "-q", "--no-verify", "-m", "sin json")
        sha = e.git_salida("rev-parse", "HEAD")
        asegurar(e.correr([a_main(sha)]), 2, "", "ENTREGA BLOQUEADA", f"no pudo leer {PLUGIN_JSON}")


def test_una_linea_mal_formada_bloquea():
    with Escenario() as e:
        sha = e.entrega_inicial()
        for linea in ("refs/heads/main", f"refs/heads/main {sha} refs/heads/main", f"refs/heads/main sin-sha refs/heads/main {CEROS}", f"refs/heads/main {sha} refs/heads/main {CEROS} extra"):
            asegurar(e.correr([linea]), 2, "", "ENTREGA BLOQUEADA", "línea ilegible")


def test_un_error_de_git_en_un_push_a_main_bloquea_y_lo_dice():
    with Escenario() as e:
        e.entrega_inicial()
        desconocido = "1234567890abcdef1234567890abcdef12345678"
        asegurar(e.correr([a_main(desconocido)]), 2, "", "ENTREGA BLOQUEADA", "git no pudo")
        fuera = e.dir / "fuera"
        fuera.mkdir()
        e.env["GIT_CEILING_DIRECTORIES"] = str(e.dir)
        asegurar(e.correr([a_main(desconocido)], cwd=fuera), 2, "", "ENTREGA BLOQUEADA", "repositorio git")


def test_un_argumento_de_mas_es_un_error_de_uso():
    with Escenario() as e:
        resultado = subprocess.run([sys.executable, str(SCRIPT), "--x"], cwd=e.obra, env=e.env, capture_output=True)
        assert resultado.returncode == 2, resultado
        assert resultado.stdout == b"" and b"uso:" in resultado.stderr, resultado


class RepoConHook:
    def __init__(self, e):
        self.e = e
        self.remoto = e.dir / "remoto.git"
        e.git("init", "-q", "--bare", "-b", "main", str(self.remoto), cwd=e.dir)
        (e.obra / "tools").mkdir()
        shutil.copy(BARRIDO, e.obra / "tools" / "barrido.py")
        shutil.copy(SCRIPT, e.obra / "tools" / "entrega.py")
        shutil.copy(NOTAS, e.obra / "tools" / "notas.py")
        shutil.copytree(HOOKS, e.obra / ".githooks")
        e.git("config", "core.hooksPath", ".githooks")

    def empujar(self, *refspecs):
        resultado = subprocess.run(["git", "push", "-q", str(self.remoto), *refspecs], cwd=self.e.obra, env=self.e.env, capture_output=True)
        return resultado.returncode, resultado.stdout.decode("utf-8", "replace") + resultado.stderr.decode("utf-8", "replace")

    def en_el_remoto(self, ref):
        resultado = subprocess.run(["git", "rev-parse", "--verify", "-q", ref], cwd=self.remoto, env=self.e.env, capture_output=True)
        return resultado.stdout.decode().strip() if resultado.returncode == 0 else None


def test_el_hook_sigue_frenando_contenido_con_la_lista_negra_y_deja_pasar_lo_limpio():
    with Escenario() as e:
        repo = RepoConHook(e)
        limpio = e.commit({"README.md": "limpio\n"}, "base")
        codigo, salida = repo.empujar("HEAD:refs/heads/feature")
        assert codigo == 0, salida
        assert repo.en_el_remoto("refs/heads/feature") == limpio
        e.commit({"nota.md": "menciona AcmeCorp\n"}, "nota")
        codigo, salida = repo.empujar("HEAD:refs/heads/feature")
        assert codigo != 0, salida
        assert "nota.md" in salida and "AcmeCorp" in salida and "BARRIDO" in salida, salida
        assert repo.en_el_remoto("refs/heads/feature") == limpio


def test_el_hook_frena_el_push_a_main_con_plugin_sin_etiqueta_y_lo_deja_pasar_con_ella():
    with Escenario() as e:
        repo = RepoConHook(e)
        sha = e.commit({PLUGIN_JSON: plugin_json("0.1.0"), "CHANGELOG.md": notas_de("0.1.0")}, "base")
        codigo, salida = repo.empujar("main")
        assert codigo != 0, salida
        assert "ENTREGA BLOQUEADA" in salida and "odd-ws--v0.1.0" in salida, salida
        assert repo.en_el_remoto("refs/heads/main") is None
        e.etiquetar("0.1.0")
        codigo, salida = repo.empujar("main", "refs/tags/odd-ws--v0.1.0")
        assert codigo == 0, salida
        assert repo.en_el_remoto("refs/heads/main") == sha
        assert repo.en_el_remoto("refs/tags/odd-ws--v0.1.0^{commit}") == sha


def test_el_hook_corre_el_barrido_antes_que_la_entrega():
    with Escenario() as e:
        repo = RepoConHook(e)
        e.commit({PLUGIN_JSON: plugin_json("0.1.0"), "nota.md": "menciona AcmeCorp\n"}, "base")
        codigo, salida = repo.empujar("main")
        assert codigo != 0, salida
        assert "BARRIDO" in salida and "ENTREGA BLOQUEADA" not in salida, salida


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
