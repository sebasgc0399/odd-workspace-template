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
GH_PAGES = "refs/heads/gh-pages"
ORIGIN_GH_PAGES = "refs/remotes/origin/gh-pages"
FILAS_MD = [
    "Python, invocable como `python3` | 3.7 o más",
    "**Git** | En Windows, [Git for Windows](https://gitforwindows.org)",
    "Pi, si lo usas | 1.5.0 o más; Node & npm",
]
FILAS_HTML = [
    "<td>Python, invocable como <code>python3</code></td><td>3.7 o más</td>",
    '<td><b>Git</b></td><td>En Windows, <a href="https://gitforwindows.org">Git for Windows</a></td>',
    "<td>Pi, si lo usas</td><td>1.5.0 o más; Node &amp; npm</td>",
]
SIN_PAGINA = "aviso: no hay rama gh-pages, ni local ni en origin, así que no se revisa la página"


def a_etiqueta(version, objeto, remoto=CEROS):
    return f"refs/tags/odd-ws--v{version} {objeto} refs/tags/odd-ws--v{version} {remoto}"


def readme_de(version, actual=None, comando=None, filas=FILAS_MD, sin_actual=False):
    presentacion = "" if sin_actual else f"**Versión actual:** `{actual or version}` ([qué cambió en cada versión](CHANGELOG.md)).\n\n"
    return (
        "# odd-ws\n\n" + presentacion
        + "## Cómo funciona\n\n| Paso | Qué |\n|---|---|\n| uno | algo |\n\n"
        "## Instalación\n\n| Herramienta | Versión |\n|---|---|\n" + "".join(f"| {fila} |\n" for fila in filas)
        + f"\n```text\ngentle-shell install git:github.com/x/y@odd-ws--v{comando or version}\n```\n\n"
        "## Dónde funciona\n\n| CLI | Windows |\n|---|---|\n| Claude Code | sí |\n"
    )


def uso_de(comando):
    return f"# Uso\n\n- **Instalar:** `gentle-shell install git:github.com/x/y@odd-ws--v{comando}`, o la ruta de un clon tuyo.\n"


def actualizar_de(comando):
    return f"# Actualizar\n\n```text\ngentle-shell install git:github.com/x/y@odd-ws--v{comando}\n```\n"


def docs_al_dia(version):
    return {"README.md": readme_de(version), "Doc/uso.md": uso_de(version), "Doc/actualizar.md": actualizar_de(version)}


def pagina_de(version, actual=None, pie=None, comando=None, filas=FILAS_HTML, sin_actual=False):
    encabezado = "" if sin_actual else f'  <p class="version">Versión actual: <b>{actual or version}</b> · <a href="x">qué cambió</a></p>\n'
    return (
        '<!doctype html>\n<html lang="es">\n<body>\n<header>\n' + encabezado + "</header>\n<main>\n"
        "  <h2>Qué trae</h2>\n  <table>\n    <tr><th>Comando</th><th>Para qué</th></tr>\n  </table>\n"
        '  <h2 id="instalar">Instalar</h2>\n  <table>\n    <thead><tr><th>Herramienta</th><th>Versión</th></tr></thead>\n    <tbody>\n'
        + "".join(f"      <tr>{fila}</tr>\n" for fila in filas)
        + "    </tbody>\n  </table>\n"
        f"  <pre><code>gentle-shell install git:github.com/x/y@odd-ws--v{comando or version}</code></pre>\n"
        '  <h2>Novedades</h2>\n  <p class="novedad"><b>0.0.9.</b> Lo de antes.</p>\n'
        f'</main>\n<footer>\n  <p>odd-ws {pie or version} · <a href="https://github.com/x/y">github.com/x/y</a> · Licencia MIT</p>\n</footer>\n</body>\n</html>\n'
    )


def linea(texto, fragmento):
    return next(numero for numero, renglon in enumerate(texto.splitlines(), 1) if fragmento in renglon)


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

    def git(self, *args, cwd=None, entrada=None):
        return subprocess.run(["git", *args], cwd=cwd or self.obra, env=self.env, capture_output=True, check=True, input=entrada)

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
        sha = self.commit({PLUGIN_JSON: plugin_json(version), "plugin/skills/uno.md": "uno\n", **docs_al_dia(version)}, "base")
        self.etiquetar(version)
        self.pagina(pagina_de(version))
        return sha

    def pagina(self, contenido, ref=GH_PAGES):
        blob = self.git("hash-object", "-w", "--stdin", entrada=contenido.encode("utf-8")).stdout.decode().strip()
        arbol = self.git("mktree", entrada=f"100644 blob {blob}\tindex.html\n".encode()).stdout.decode().strip()
        self.git("update-ref", ref, self.git("commit-tree", arbol, "-m", "pagina").stdout.decode().strip())

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
        sha = e.commit({"Doc/otro.md": "otro\n", "tools/x.py": "x\n"})
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
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", "CHANGELOG.md": notas_de("0.2.0", "0.1.0"), **docs_al_dia("0.2.0")})
        e.etiquetar("0.2.0")
        e.pagina(pagina_de("0.2.0"))
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
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", "CHANGELOG.md": sin_publicar, **CON_WORKFLOW, **docs_al_dia("0.2.0")})
        e.etiquetar("0.2.0")
        e.pagina(pagina_de("0.2.0"))
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "no tiene notas para 0.2.0")
        e.git("tag", "-d", "odd-ws--v0.2.0")
        con_version = sin_publicar.replace("## 0.1.0", "## 0.2.0\n\n- cambios de la 0.2.0\n\n## 0.1.0")
        sha = e.commit({"CHANGELOG.md": con_version})
        e.etiquetar("0.2.0")
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_una_entrega_de_un_commit_sin_el_workflow_no_pide_notas():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", **docs_al_dia("0.2.0")})
        e.etiquetar("0.2.0")
        e.pagina(pagina_de("0.2.0"))
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
        e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", "CHANGELOG.md": notas_de("0.2.0"), **CON_WORKFLOW, **docs_al_dia("0.2.0")})
        e.etiquetar("0.2.0")
        e.etiquetar("0.9.0")
        e.pagina(pagina_de("0.2.0"))
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
        sha = e.commit({"Doc/otro.md": "otro\n", "CHANGELOG.md": "# Changelog\n"})
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_sin_ninguna_etiqueta_y_con_plugin_bloquea_y_pasa_al_etiquetar():
    with Escenario() as e:
        sha = e.commit({PLUGIN_JSON: plugin_json("0.1.0"), "CHANGELOG.md": notas_de("0.1.0"), **docs_al_dia("0.1.0")})
        e.pagina(pagina_de("0.1.0"))
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
        sha = e.commit({"plugin/skills/uno.md": "dos\n", PLUGIN_JSON: plugin_json("0.2.0"), "CHANGELOG.md": notas_de("0.2.0"), **docs_al_dia("0.2.0")})
        e.etiquetar("0.2.0")
        e.pagina(pagina_de("0.2.0"))
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


def sin_chequeo_de_pagina(resultado):
    for marca in ("la página y el README", "gh-pages", "aviso:"):
        assert marca not in resultado[2], (marca, resultado)


def test_el_readme_con_otra_version_actual_o_sin_ella_bloquea_y_dice_como_arreglarlo():
    with Escenario() as e:
        e.entrega_inicial("0.2.0")
        viejo = readme_de("0.2.0", actual="0.1.0")
        sha = e.commit({"README.md": viejo})
        resultado = e.correr([a_main(sha)])
        asegurar(
            resultado, 1, "",
            "ENTREGA BLOQUEADA", f"la página y el README no coinciden con {PLUGIN_JSON} de {sha[:7]}, que dice 0.2.0",
            f"README.md:{linea(viejo, 'Versión actual')} dice «Versión actual: 0.1.0»: sube la «Versión actual» del README a 0.2.0",
        )
        assert "gh-pages" not in resultado[2], resultado
        sha = e.commit({"README.md": readme_de("0.2.0", sin_actual=True)})
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "README.md no tiene la línea «Versión actual»: escríbela con 0.2.0")


def test_la_pagina_con_otra_version_bloquea_en_main_y_en_la_etiqueta_y_las_novedades_viejas_no_cuentan():
    with Escenario() as e:
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "CHANGELOG.md": notas_de("0.2.0"), **CON_WORKFLOW, **docs_al_dia("0.2.0")})
        e.etiquetar("0.2.0")
        objeto = e.git_salida("rev-parse", "odd-ws--v0.2.0")
        actual_vieja = pagina_de("0.2.0", actual="0.1.0")
        pie_viejo = pagina_de("0.2.0", pie="0.1.0")
        casos = [
            (actual_vieja, f"gh-pages:index.html:{linea(actual_vieja, 'Versión actual')} dice «Versión actual: 0.1.0»: sube la versión de la página a 0.2.0"),
            (pie_viejo, f"gh-pages:index.html:{linea(pie_viejo, 'odd-ws 0.1.0')} dice 0.1.0 en el pie: sube la versión del pie a 0.2.0"),
            (pagina_de("0.2.0", sin_actual=True), "gh-pages:index.html no tiene la línea «Versión actual»: escríbela con 0.2.0"),
        ]
        for pagina, motivo in casos:
            e.pagina(pagina)
            for lineas in ([a_main(sha)], [a_etiqueta("0.2.0", objeto)]):
                asegurar(
                    e.correr(lineas), 1, "",
                    "ENTREGA BLOQUEADA", motivo, "La página se lee de gh-pages: commitea la página de la versión en la rama gh-pages antes de empujar main",
                )
        e.pagina(pagina_de("0.2.0"))
        asegurar(e.correr([a_main(sha), a_etiqueta("0.2.0", objeto)]), 0, "entrega limpia\n")


def test_un_comando_sin_el_numero_de_la_version_bloquea_en_el_readme_los_docs_y_la_pagina():
    with Escenario() as e:
        e.entrega_inicial("0.2.0")
        readme, uso, actualizar = readme_de("0.2.0", comando="<versión>"), uso_de("<versión>"), actualizar_de("<versión nueva>")
        sha = e.commit({"README.md": readme, "Doc/uso.md": uso, "Doc/actualizar.md": actualizar})
        pagina = pagina_de("0.2.0", comando="&lt;versión&gt;")
        e.pagina(pagina)
        asegurar(
            e.correr([a_main(sha)]), 1, "",
            "ENTREGA BLOQUEADA",
            f"README.md:{linea(readme, 'odd-ws--v')} tiene odd-ws--v<versión>: cámbialo por odd-ws--v0.2.0",
            f"Doc/uso.md:{linea(uso, 'odd-ws--v')} tiene odd-ws--v<versión>: cámbialo por odd-ws--v0.2.0",
            f"Doc/actualizar.md:{linea(actualizar, 'odd-ws--v')} tiene odd-ws--v<versión nueva>: cámbialo por odd-ws--v0.2.0",
            f"gh-pages:index.html:{linea(pagina, 'odd-ws--v')} tiene odd-ws--v<versión>: cámbialo por odd-ws--v0.2.0",
        )
        sha = e.commit({**docs_al_dia("0.2.0"), "Doc/uso.md": uso_de("0.1.0")})
        e.pagina(pagina_de("0.2.0"))
        resultado = e.correr([a_main(sha)])
        asegurar(resultado, 1, "", "ENTREGA BLOQUEADA", f"Doc/uso.md:{linea(uso_de('0.1.0'), 'odd-ws--v')} tiene odd-ws--v0.1.0: cámbialo por odd-ws--v0.2.0")
        assert "README.md:" not in resultado[2] and "Doc/actualizar.md" not in resultado[2] and "gh-pages" not in resultado[2], resultado


def test_la_tabla_de_requisitos_distinta_entre_el_readme_y_la_pagina_bloquea_y_dice_que_fila_o_celda_difiere():
    with Escenario() as e:
        sha = e.entrega_inicial("0.2.0")
        readme = readme_de("0.2.0")
        otra_celda = pagina_de("0.2.0", filas=FILAS_HTML[:2] + ["<td>Pi, si lo usas</td><td>1.5.0 o más. Para los writers, gentle-shell</td>"])
        una_menos = pagina_de("0.2.0", filas=FILAS_HTML[:2])
        una_mas = pagina_de("0.2.0", filas=FILAS_HTML + ["<td>gentle-shell</td><td>El de <code>npm i -g gentle-pi</code></td>"])
        casos = [
            (otra_celda, (
                f"la fila 3 de la tabla de requisitos («Pi, si lo usas»), columna «Versión», dice «1.5.0 o más; Node & npm» en README.md:{linea(readme, 'Pi, si lo usas')} "
                f"y «1.5.0 o más. Para los writers, gentle-shell» en gh-pages:index.html:{linea(otra_celda, 'Pi, si lo usas')}"
            )),
            (una_menos, f"la fila 3 de la tabla de requisitos («Pi, si lo usas», README.md:{linea(readme, 'Pi, si lo usas')}) no está en la página"),
            (una_mas, f"la fila 4 de la tabla de requisitos («gentle-shell», gh-pages:index.html:{linea(una_mas, '<td>gentle-shell')}) no está en el README"),
        ]
        for pagina, motivo in casos:
            e.pagina(pagina)
            asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", motivo, "La página se lee de gh-pages")
        e.pagina(pagina_de("0.2.0").replace('<h2 id="instalar">Instalar</h2>', "<h2>👉 Instalación</h2>"))
        sha = e.commit({"README.md": readme.replace("## Instalación", "## 👉 Instalación 👈")})
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")
        sha = e.commit({"README.md": readme.replace("## Instalación", "## Instalar")})
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", "README.md no tiene la tabla de requisitos en su sección «Instalación»")


def test_sin_rama_de_la_pagina_avisa_en_una_linea_y_no_frena_pero_revisa_el_readme():
    with Escenario() as e:
        sha = e.entrega_inicial("0.2.0")
        e.git("update-ref", "-d", GH_PAGES)
        resultado = e.correr([a_main(sha)])
        asegurar(resultado, 0, "entrega limpia\n", SIN_PAGINA)
        assert resultado[2].startswith(SIN_PAGINA) and resultado[2].count("\n") == 1, resultado
        viejo = readme_de("0.2.0", actual="0.1.0")
        sha = e.commit({"README.md": viejo})
        asegurar(e.correr([a_main(sha)]), 1, "", SIN_PAGINA, f"README.md:{linea(viejo, 'Versión actual')} dice «Versión actual: 0.1.0»")


def test_sin_rama_local_la_pagina_se_lee_de_origin_y_la_local_manda_si_existe():
    with Escenario() as e:
        sha = e.entrega_inicial("0.2.0")
        e.git("update-ref", "-d", GH_PAGES)
        vieja = pagina_de("0.2.0", actual="0.1.0")
        e.pagina(vieja, ORIGIN_GH_PAGES)
        asegurar(
            e.correr([a_main(sha)]), 1, "",
            "ENTREGA BLOQUEADA", f"origin/gh-pages:index.html:{linea(vieja, 'Versión actual')} dice «Versión actual: 0.1.0»", "La página se lee de origin/gh-pages",
        )
        e.pagina(pagina_de("0.2.0"))
        asegurar(e.correr([a_main(sha)]), 0, "entrega limpia\n")


def test_con_el_readme_los_docs_y_la_pagina_al_dia_la_entrega_pasa_en_main_y_en_la_etiqueta():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", "CHANGELOG.md": notas_de("0.2.0"), **CON_WORKFLOW, **docs_al_dia("0.2.0")})
        e.etiquetar("0.2.0")
        e.pagina(pagina_de("0.2.0"))
        asegurar(e.correr([a_main(sha), a_etiqueta("0.2.0", e.git_salida("rev-parse", "odd-ws--v0.2.0"))]), 0, "entrega limpia\n")


HUELLAS = AQUI / "huellas.py"
TABLA_DE_HUELLAS = "plugin/plantillas/huellas.json"


def generar_huellas(e):
    resultado = subprocess.run([sys.executable, str(HUELLAS)], cwd=e.obra, env=e.env, capture_output=True)
    assert resultado.returncode == 0, resultado
    return (e.obra / TABLA_DE_HUELLAS).read_text(encoding="utf-8")


def entrega_con(e, version, archivos):
    sha = e.commit({PLUGIN_JSON: plugin_json(version), "CHANGELOG.md": notas_de(version), **CON_WORKFLOW, **archivos, **docs_al_dia(version)})
    e.etiquetar(version)
    e.pagina(pagina_de(version))
    return sha


def test_la_tabla_de_huellas_desfasada_o_que_falta_bloquea_en_main_y_en_la_etiqueta_y_al_dia_pasa():
    with Escenario() as e:
        e.entrega_inicial()
        plantillas = {"plugin/plantillas/CLAUDE.md": "# {{nombre}}\n`{{tickets}}/`\n", "plugin/plantillas/pre-commit": "#!/bin/sh\n"}
        sha = entrega_con(e, "0.2.0", plantillas)
        for lineas in ([a_main(sha)], [a_etiqueta("0.2.0", e.git_salida("rev-parse", "odd-ws--v0.2.0"))]):
            asegurar(e.correr(lineas), 1, "", "ENTREGA BLOQUEADA", f"{TABLA_DE_HUELLAS} en {sha[:7]} no está al día", "python tools/huellas.py")
        (e.obra / PLUGIN_JSON).write_text(plugin_json("0.3.0"), encoding="utf-8")
        tabla = generar_huellas(e)
        sha = entrega_con(e, "0.3.0", {TABLA_DE_HUELLAS: tabla})
        asegurar(e.correr([a_main(sha), a_etiqueta("0.3.0", e.git_salida("rev-parse", "odd-ws--v0.3.0"))]), 0, "entrega limpia\n")
        sha = entrega_con(e, "0.4.0", {"plugin/plantillas/pre-commit": "#!/bin/sh\necho 4\n"})
        asegurar(e.correr([a_main(sha)]), 1, "", "ENTREGA BLOQUEADA", f"{TABLA_DE_HUELLAS} en {sha[:7]} no está al día")


def test_con_la_pagina_y_el_readme_desfasados_una_etiqueta_ajena_a_su_version_sigue_frenando_con_su_mensaje():
    with Escenario() as e:
        e.entrega_inicial("0.3.0")
        sha = e.commit({"plugin/x.txt": "x\n", **docs_al_dia("9.9.9")})
        e.pagina(pagina_de("9.9.9"))
        e.etiquetar("0.4.0")
        resultado = e.correr([a_main(sha)])
        asegurar(resultado, 1, "", "ENTREGA BLOQUEADA", "odd-ws--v0.4.0", "dice 0.3.0", "debería ser odd-ws--v0.3.0", "claude plugin tag ./plugin")
        sin_chequeo_de_pagina(resultado)


def test_con_la_pagina_y_el_readme_desfasados_una_entrega_sin_notas_sigue_frenando_con_su_mensaje():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({PLUGIN_JSON: plugin_json("0.2.0"), "plugin/skills/uno.md": "dos\n", **CON_WORKFLOW, **docs_al_dia("9.9.9")})
        e.etiquetar("0.2.0")
        e.pagina(pagina_de("9.9.9"))
        for lineas in ([a_main(sha)], [a_etiqueta("0.2.0", e.git_salida("rev-parse", "odd-ws--v0.2.0"))]):
            resultado = e.correr(lineas)
            asegurar(resultado, 1, "", "ENTREGA BLOQUEADA", f"CHANGELOG.md en {sha[:7]} no tiene notas para 0.2.0", "«## 0.2.0»")
            sin_chequeo_de_pagina(resultado)


def test_sin_pagina_y_con_el_readme_desfasado_un_cambio_de_plugin_sin_etiqueta_sigue_frenando_con_su_mensaje():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"plugin/skills/uno.md": "dos\n", **docs_al_dia("9.9.9")})
        e.git("update-ref", "-d", GH_PAGES)
        resultado = e.correr([a_main(sha)])
        asegurar(resultado, 1, "", "ENTREGA BLOQUEADA", f"{sha[:7]} no tiene la etiqueta odd-ws--v0.1.0", "Subí «version»", "junto con la rama")
        sin_chequeo_de_pagina(resultado)


def test_sin_pagina_y_con_el_readme_desfasado_un_push_a_otra_rama_sigue_sin_revisarse():
    with Escenario() as e:
        e.entrega_inicial()
        sha = e.commit({"plugin/skills/uno.md": "dos\n", **docs_al_dia("9.9.9")})
        e.git("update-ref", "-d", GH_PAGES)
        asegurar(e.correr([f"refs/heads/feature {sha} refs/heads/feature {CEROS}"]), 0, "")


class RepoConHook:
    def __init__(self, e):
        self.e = e
        self.remoto = e.dir / "remoto.git"
        e.git("init", "-q", "--bare", "-b", "main", str(self.remoto), cwd=e.dir)
        (e.obra / "tools").mkdir()
        shutil.copy(BARRIDO, e.obra / "tools" / "barrido.py")
        shutil.copy(SCRIPT, e.obra / "tools" / "entrega.py")
        shutil.copy(NOTAS, e.obra / "tools" / "notas.py")
        shutil.copy(AQUI / "huellas.py", e.obra / "tools" / "huellas.py")
        shutil.copytree(AQUI.parent / "plugin" / "scripts", e.obra / "plugin" / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__", "*.tests.py"))
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
        sha = e.commit({PLUGIN_JSON: plugin_json("0.1.0"), "CHANGELOG.md": notas_de("0.1.0"), **docs_al_dia("0.1.0")}, "base")
        e.pagina(pagina_de("0.1.0"))
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
