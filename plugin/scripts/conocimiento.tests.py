import contextlib
import hashlib
import importlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "conocimiento.py"
sys.path.insert(0, str(AQUI))
sys.dont_write_bytecode = True

HOY = date(2026, 10, 30)


def m():
    return importlib.import_module("conocimiento")


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def escribir(raiz, archivos):
    for rel, contenido in archivos.items():
        ruta = Path(raiz) / rel
        if contenido is None:
            ruta.unlink()
            continue
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8", newline="\n")


def config_de(knowledge):
    config = {"schema_version": 1, "layers": {"x": {"extensions": [".x"]}}}
    if knowledge is not None:
        config["knowledge"] = knowledge
    return config


def git_en(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, timeout=60).stdout.strip()


class Arbol:
    def __init__(self, archivos=None, knowledge=None, git=False, subcarpeta=None, config=None):
        self.archivos = archivos or {}
        self.knowledge = knowledge
        self.git = git
        self.subcarpeta = subcarpeta
        self.config = config

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="conocimiento-"))
        self.previo = dict(os.environ)
        for clave in [c for c in os.environ if c.startswith("GIT_")]:
            del os.environ[clave]
        vacio = self.base / "gitconfig-vacio"
        vacio.write_text("", encoding="utf-8")
        os.environ.update({
            "GIT_CONFIG_GLOBAL": str(vacio), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": str(self.base),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        })
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.raiz = self.repo / self.subcarpeta if self.subcarpeta else self.repo
        self.raiz.mkdir(parents=True, exist_ok=True)
        datos = self.config if self.config is not None else config_de(self.knowledge)
        (self.raiz / "workspace.config.json").write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding="utf-8")
        escribir(self.raiz, self.archivos)
        if self.git:
            git_en(self.repo, "init", "-q", "-b", "main")
        return self

    def escribir(self, archivos):
        escribir(self.raiz, archivos)

    def commitear(self):
        git_en(self.repo, "add", "-A")
        git_en(self.repo, "commit", "-q", "-m", "base")

    def ctx(self, hoy=HOY):
        return m().contexto_de(self.raiz, hoy)

    def entorno(self):
        entorno = {c: v for c, v in os.environ.items() if c not in ("PYTHONIOENCODING", "PYTHONUTF8", "CLAUDE_PROJECT_DIR")}
        return entorno

    def cli(self, *args, cwd=None):
        completado = subprocess.run(
            [sys.executable, "-B", "-W", "error", str(SCRIPT), *args],
            cwd=cwd or self.raiz, capture_output=True, env=self.entorno(), timeout=120,
        )
        return completado.returncode, completado.stdout.decode("utf-8"), completado.stderr.decode("utf-8")

    def instantanea(self):
        resumen = {}
        for ruta in sorted(self.base.rglob("*")):
            if ".git" in ruta.relative_to(self.base).parts:
                continue
            resumen[ruta.relative_to(self.base).as_posix()] = hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.is_file() else "<dir>"
        return resumen

    def __exit__(self, *_):
        os.environ.clear()
        os.environ.update(self.previo)
        shutil.rmtree(self.base, onexc=_forzar_borrado)


def pares(hallazgos):
    return [(h.sev, h.texto) for h in hallazgos]


def correr_main(arbol, *args, entorno=None):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = m().main(list(args), entorno if entorno is not None else {}, str(arbol.raiz))
    return codigo, salida.getvalue(), error.getvalue()


def test_hallazgo_guarda_severidad_texto_y_arreglo():
    h = m().Hallazgo(m().WARN, "algo", "arreglo")
    assert (h.sev, h.texto, h.arreglo) == ("warn", "algo", "arreglo"), h
    assert m().Hallazgo(m().FAIL, "x").arreglo is None
    assert (m().FAIL, m().WARN, m().INFO, m().WORKLIST, m().NOAPLICA) == ("FAIL", "warn", "info", "worklist", "n/a")


def test_slug_estilo_github_sin_colapsar_espacios_y_con_acentos():
    casos = [
        ("Ejecución", "ejecución"),
        ("Jerarquía de configuración", "jerarquía-de-configuración"),
        ("El modelo: a = b, no c", "el-modelo-a--b-no-c"),
        ("ADR-003 — Título largo", "adr-003--título-largo"),
        ("2. Ciclo: `Alfa_Beta` + `Gamma`", "2-ciclo-alfa_beta--gamma"),
        ("Catálogo (orquestador `fn_uno`)", "catálogo-orquestador-fn_uno"),
        ("  Con bordes  ", "con-bordes"),
    ]
    for titulo, ancla in casos:
        assert m().slug(titulo) == ancla, (titulo, m().slug(titulo), ancla)


def test_frontmatter_lee_campos_y_descarta_comentarios():
    with Arbol() as a:
        a.escribir({
            "ok.md": "---\nrol: resumen\nverificado: 2026-10-01 # revisado a mano\n---\n# T\n",
            "sin.md": "# sin\n",
            "abierto.md": "---\nrol: resumen\n# nunca cierra\n",
            "bom.md": "﻿---\nrol: autoritativo\n---\n",
        })
        assert m().frontmatter(a.raiz / "ok.md") == {"rol": "resumen", "verificado": "2026-10-01"}
        assert m().frontmatter(a.raiz / "sin.md") is None
        assert m().frontmatter(a.raiz / "abierto.md") is None
        assert m().frontmatter(a.raiz / "bom.md") == {"rol": "autoritativo"}


def test_contexto_toma_la_config_y_sus_valores_por_defecto():
    with Arbol() as a:
        c = a.ctx()
        assert (c.docs, c.indice, c.tope, c.escaneo, c.cantidades, c.afirmaciones) == (None, "CLAUDE.md", 200, [], [], None), vars(c)
        assert Path(c.raiz) == a.raiz and c.hoy == HOY
    cfg = {"docs": "notas", "index": "LEEME.md", "index_max_lines": 7, "scan": ["x/*.md"], "quantities": ["tablas"], "claims": "notas/a.json"}
    with Arbol(knowledge=cfg) as a:
        c = a.ctx()
        assert (c.docs, c.indice, c.tope, c.escaneo, c.cantidades, c.afirmaciones) == ("notas", "LEEME.md", 7, ["x/*.md"], ["tablas"], "notas/a.json")


def test_indexados_un_doc_no_nombrado_en_el_indice_es_warn_con_arreglo():
    with Arbol({"CLAUDE.md": "- [a](docs/a.md) y la letra b suelta\n", "docs/a.md": "# A\n", "docs/b.md": "# B\n", "docs/README.md": "# r\n", "docs/sub/c.md": "# C\n"}, {"docs": "docs"}) as a:
        hs = m().chequear_indexados(a.ctx())
        assert pares(hs) == [("warn", "docs/b.md no está linkeado desde CLAUDE.md")], pares(hs)
        assert hs[0].arreglo == "agregarlo al índice (CLAUDE.md)", hs[0].arreglo


def test_indexados_respeta_el_indice_y_la_carpeta_de_la_config():
    archivos = {"LEEME.md": "ver a.md\n", "notas/dom/a.md": "# A\n", "notas/dom/b.md": "# B\n", "CLAUDE.md": "b.md\n"}
    with Arbol(archivos, {"docs": "notas/dom", "index": "LEEME.md"}) as a:
        hs = m().chequear_indexados(a.ctx())
        assert pares(hs) == [("warn", "notas/dom/b.md no está linkeado desde LEEME.md")], pares(hs)
        assert hs[0].arreglo == "agregarlo al índice (LEEME.md)"


def test_indexados_sin_el_indice_es_fail():
    with Arbol({"docs/a.md": "# A\n"}, {"docs": "docs"}) as a:
        assert pares(m().chequear_indexados(a.ctx())) == [("FAIL", "no existe CLAUDE.md en la raíz")]


def test_indexados_sin_docs_no_aplica_y_con_carpeta_inexistente_es_fail():
    with Arbol({"CLAUDE.md": "x\n"}) as a:
        assert pares(m().chequear_indexados(a.ctx())) == [("n/a", "sin knowledge.docs en la config")]
    with Arbol({"CLAUDE.md": "x\n"}, {"docs": "no-existe"}) as a:
        hs = m().chequear_indexados(a.ctx())
        assert pares(hs) == [("FAIL", "knowledge.docs 'no-existe' no es una carpeta")], pares(hs)
        assert hs[0].arreglo == "crear la carpeta o corregir knowledge.docs en workspace.config.json"


def test_links_rotos_son_fail_incluso_desde_archivos_extra_y_hondos():
    archivos = {
        "CLAUDE.md": "[a](docs/a.md) y [roto](docs/no-existe.md)\n",
        "docs/a.md": "[b](b.md) [b con ancla](b.md#x) [roto](nada.md) [con ancla](c.md#a) [web](https://example.org/x/y.md) [mail](mailto:a@b.md) [unidad](C:/no-existe/zz.md)\n",
        "docs/b.md": "# B\n",
        "notas/x.md": "[roto](../docs/fantasma.md)\n",
        "notas/hondo/uno/y.md": "[ok](../../../docs/a.md) [roto](../../../docs/tampoco.md)\n",
        "suelto.md": "[roto](nada.md)\n",
        "LEEME.md": "[ok](CLAUDE.md)\n",
        "lib/codigo.py": "# [roto](nada.md)\n",
    }
    with Arbol(archivos, {"docs": "docs", "scan": ["notas/**/*.md", "LEEME.md"]}) as a:
        hs = m().chequear_links(a.ctx())
    quiero = {
        "CLAUDE.md -> docs/no-existe.md",
        "docs/a.md -> nada.md",
        "docs/a.md -> c.md",
        "docs/a.md -> C:/no-existe/zz.md",
        "notas/x.md -> ../docs/fantasma.md",
        "notas/hondo/uno/y.md -> ../../../docs/tampoco.md",
    }
    assert {h.texto.replace(" (destino inexistente)", "") for h in hs} == quiero, pares(hs)
    assert len(hs) == 6 and all(h.sev == "FAIL" and h.texto.endswith("(destino inexistente)") for h in hs), pares(hs)
    assert all(h.arreglo == "corregir la ruta o crear el destino" for h in hs)


def test_links_solo_con_el_indice_cuando_no_hay_docs_ni_scan():
    with Arbol({"CLAUDE.md": "[roto](nada.md) [ok](otro.md)\n", "otro.md": "x\n"}) as a:
        assert pares(m().chequear_links(a.ctx())) == [("FAIL", "CLAUDE.md -> nada.md (destino inexistente)")]


def test_links_no_repite_un_archivo_que_entra_por_dos_caminos():
    with Arbol({"CLAUDE.md": "x\n", "docs/a.md": "[roto](nada.md)\n"}, {"docs": "docs", "scan": ["docs/*.md", "**/*.md"]}) as a:
        assert len(m().chequear_links(a.ctx())) == 1


def test_links_scan_ignora_git_y_node_modules():
    archivos = {"CLAUDE.md": "x\n", "node_modules/p/a.md": "[roto](nada.md)\n", ".git/b.md": "[roto](nada.md)\n", "ok/c.md": "[ok](../CLAUDE.md)\n"}
    with Arbol(archivos, {"scan": ["**/*.md"]}) as a:
        assert m().chequear_links(a.ctx()) == []


def test_links_scan_acepta_un_archivo_literal_y_una_carpeta_inexistente():
    with Arbol({"CLAUDE.md": "x\n", "uno.md": "[roto](nada.md)\n"}, {"scan": ["uno.md", "no/existe/*.md"]}) as a:
        assert pares(m().chequear_links(a.ctx())) == [("FAIL", "uno.md -> nada.md (destino inexistente)")]


def test_links_scan_no_distingue_mayusculas_como_el_resto_de_los_globs():
    if os.name != "nt":
        return
    with Arbol({"CLAUDE.md": "x\n", "Notas/Uno.MD": "[roto](nada.md)\n"}, {"scan": ["notas/*.md"]}) as a:
        assert len(m().chequear_links(a.ctx())) == 1


def test_anclas_rotas_son_warn_y_las_sanas_no():
    archivos = {
        "CLAUDE.md": "[b](docs/b.md#ejecución)\n",
        "docs/a.md": (
            "[ok](b.md#ejecución) [ok2](b.md#adr-003--título-largo) [mayus](b.md#Ejecución) [html](b.md#r-03) "
            "[html rota](b.md#r-99) [rota](b.md#no-existe) [archivo muerto](c.md#x) [mismo doc](#nada)\n"
        ),
        "docs/b.md": '# Ejecución\n\n## ADR-003 — Título largo\n\n<a id="r-03"></a>\n### R-03 · Decisión\n',
    }
    with Arbol(archivos, {"docs": "docs"}) as a:
        hs = m().chequear_anclas(a.ctx())
    assert sorted(h.texto for h in hs) == ["docs/a.md -> b.md#no-existe (sección inexistente)", "docs/a.md -> b.md#r-99 (sección inexistente)"], pares(hs)
    assert all(h.sev == "warn" and h.arreglo == "revisar el título de la sección destino" for h in hs)


def test_anclas_desde_el_indice_y_los_archivos_extra():
    archivos = {
        "CLAUDE.md": "[x](notas/n.md#no)\n",
        "notas/n.md": "# Sí\n[y](../CLAUDE.md#nada)\n",
    }
    with Arbol(archivos, {"scan": ["notas/*.md"]}) as a:
        hs = m().chequear_anclas(a.ctx())
    assert sorted(h.texto for h in hs) == ["CLAUDE.md -> notas/n.md#no (sección inexistente)", "notas/n.md -> ../CLAUDE.md#nada (sección inexistente)"], pares(hs)


def test_anclas_acepta_el_id_y_name_html_con_comillas_simples_y_dobles():
    archivos = {
        "CLAUDE.md": "[a](x.md#uno) [b](x.md#dos) [d](x.md#cuatro)\n",
        "x.md": "<a id='uno'></a> <a class=\"k\" name=\"dos\"></a>\n",
    }
    with Arbol(archivos) as a:
        hs = m().chequear_anclas(a.ctx())
    assert [h.texto for h in hs] == ["CLAUDE.md -> x.md#cuatro (sección inexistente)"], pares(hs)


def _arbol_de_cifras():
    return {
        "CLAUDE.md": "[m](docs/a.md#catálogo-de-25-módulos)\n",
        "AAA/z.md": "[m](../docs/a.md#catálogo-de-25-módulos)\n",
        "notas/r.md": "[m](../docs/a.md#Catálogo-de-25-módulos) y otra vez [m](../docs/a.md#catálogo-de-25-módulos)\n",
        "notas/hondo/p.md": "[c](../../docs/a.md#contrato-de-3-capas)\n",
        "docs/a.md": (
            "# Visión de 8 módulos\n\n## Catálogo de 25 módulos\n\n## Contrato de 3 capas\n\nVer [arriba](#contrato-de-3-capas).\n\n"
            "### 7 TABLAS sueltas\n\n## 2. Ciclo de vida\n\n## Frente 4\n\n##### 9 tablas en un nivel que no se mira\n"
        ),
    }


def test_cifras_en_headings_cuenta_links_entrantes_de_todas_partes():
    knowledge = {"docs": "docs", "scan": ["notas/**/*.md", "AAA/*.md"], "quantities": ["módulos", "tablas", "capas"]}
    with Arbol(_arbol_de_cifras(), knowledge) as a:
        hs = m().chequear_cifras_en_headings(a.ctx())
    avisos = {h.texto: h for h in hs if h.sev == "warn"}
    clave1 = "a.md: heading con cantidad '25 módulos' y 4 link(s) entrante(s) -- corregir la cifra rompe el ancla"
    clave2 = "a.md: heading con cantidad '3 capas' y 2 link(s) entrante(s) -- corregir la cifra rompe el ancla"
    assert set(avisos) == {clave1, clave2}, sorted(avisos)
    assert avisos[clave1].arreglo == "sacar la cifra del título y dejarla en el cuerpo (citada por AAA/z.md, CLAUDE.md, notas/r.md)", avisos[clave1].arreglo
    assert avisos[clave2].arreglo == "sacar la cifra del título y dejarla en el cuerpo (citada por docs/a.md, notas/hondo/p.md)", avisos[clave2].arreglo
    infos = [(h.sev, h.texto) for h in hs if h.sev == "info"]
    assert infos == [("info", "1 heading(s) con cantidad y CERO links entrantes -- gratis sacarles la cifra ahora")], infos
    assert len(hs) == 3


def test_cifras_en_headings_un_ordinal_o_un_vocabulario_ajeno_no_cuentan():
    archivos = {"docs/a.md": "# A\n\n## 2. Ciclo\n\n## Frente 4\n\n## 12 módulos\n"}
    with Arbol(archivos, {"docs": "docs", "quantities": ["tablas"]}) as a:
        assert m().chequear_cifras_en_headings(a.ctx()) == []
    with Arbol(archivos, {"docs": "docs", "quantities": ["módulos"]}) as a:
        assert pares(m().chequear_cifras_en_headings(a.ctx())) == [("info", "1 heading(s) con cantidad y CERO links entrantes -- gratis sacarles la cifra ahora")]


def test_cifras_en_headings_el_vocabulario_se_escapa_y_no_es_regex():
    with Arbol({"docs/a.md": "## 3 tabla.s\n\n## 4 tablaXs\n"}, {"docs": "docs", "quantities": ["tabla.s"]}) as a:
        hs = m().chequear_cifras_en_headings(a.ctx())
        assert [h.texto for h in hs] == ["1 heading(s) con cantidad y CERO links entrantes -- gratis sacarles la cifra ahora"], pares(hs)


def test_cifras_en_headings_no_aplica_sin_docs_o_sin_vocabulario():
    with Arbol({"CLAUDE.md": "x\n"}, {"quantities": ["tablas"]}) as a:
        assert pares(m().chequear_cifras_en_headings(a.ctx())) == [("n/a", "sin knowledge.docs en la config")]
    with Arbol({"docs/a.md": "## 3 tablas\n"}, {"docs": "docs"}) as a:
        assert pares(m().chequear_cifras_en_headings(a.ctx())) == [("n/a", "sin knowledge.quantities en la config")]
    with Arbol({}, {"docs": "docs", "quantities": ["tablas"]}) as a:
        hs = m().chequear_cifras_en_headings(a.ctx())
        assert pares(hs) == [("n/a", "knowledge.docs 'docs' no es una carpeta (lo reporta el chequeo de indexados)")], pares(hs)


def test_tope_del_indice_el_limite_no_es_exceso_y_uno_mas_si():
    with Arbol({"CLAUDE.md": "x\n" * 200}) as a:
        assert m().chequear_tope_del_indice(a.ctx()) == []
    with Arbol({"CLAUDE.md": "x\n" * 201}) as a:
        hs = m().chequear_tope_del_indice(a.ctx())
        assert pares(hs) == [("warn", "CLAUDE.md tiene 201 líneas (límite 200)")], pares(hs)
        assert hs[0].arreglo == "podar: mover el detalle estable a los docs y dejar solo el índice"


def test_tope_del_indice_usa_el_indice_y_el_tope_de_la_config():
    with Arbol({"LEEME.md": "x\n" * 6, "CLAUDE.md": "x\n" * 500}, {"index": "LEEME.md", "index_max_lines": 5}) as a:
        assert pares(m().chequear_tope_del_indice(a.ctx())) == [("warn", "LEEME.md tiene 6 líneas (límite 5)")]
    with Arbol({"LEEME.md": "x\n" * 5}, {"index": "LEEME.md", "index_max_lines": 5}) as a:
        assert m().chequear_tope_del_indice(a.ctx()) == []


def test_tope_del_indice_sin_indice_no_inventa_hallazgos():
    with Arbol({}) as a:
        assert m().chequear_tope_del_indice(a.ctx()) == []


def _fm(verificado, volatilidad="media", rol="resumen"):
    return f"---\nrol: {rol}\nverificado: {verificado}\nvolatilidad: {volatilidad}\n---\n# doc\n"


def _hace(dias):
    return (HOY - timedelta(days=dias)).isoformat()


def test_frescura_vence_segun_la_volatilidad_y_el_borde_no_vence():
    archivos = {
        "docs/sin-volatilidad.md": f"---\nrol: resumen\nverificado: {_hace(60)}\n---\n# doc\n",
        "docs/vencido-media.md": _fm(_hace(100)),
        "docs/borde-media.md": _fm(_hace(90)),
        "docs/vencido-alta.md": _fm(_hace(40), "alta"),
        "docs/borde-alta.md": _fm(_hace(30), "alta"),
        "docs/fresco.md": _fm(_hace(10)),
        "docs/fecha-mala.md": _fm("ayer"),
        "docs/baja.md": _fm("2000-01-01", "baja"),
        "docs/rara.md": _fm(_hace(91), "inventada"),
        "docs/con-comentario.md": f"---\nrol: autoritativo\nverificado: {_hace(5)} # revisado a mano\n---\n",
        "docs/sin-frontmatter.md": "# sin campos\n",
        "docs/sin-rol.md": "# no declara rol\n",
        "docs/rol-raro.md": _fm(_hace(5), rol="inventado"),
        "docs/README.md": "# no cuenta\n",
    }
    with Arbol(archivos, {"docs": "docs"}) as a:
        hs = m().chequear_frescura(a.ctx())
    avisos = sorted((h.texto, h.arreglo) for h in hs if h.sev == "warn")
    assert avisos == [
        ("fecha-mala.md: 'verificado: ayer' no es una fecha ISO", "usar formato YYYY-MM-DD"),
        ("rara.md sin verificar hace 91d (volatilidad inventada -> 90d)", "revisarlo contra el código y actualizar 'verificado:'"),
        ("vencido-alta.md sin verificar hace 40d (volatilidad alta -> 30d)", "revisarlo contra el código y actualizar 'verificado:'"),
        ("vencido-media.md sin verificar hace 100d (volatilidad media -> 90d)", "revisarlo contra el código y actualizar 'verificado:'"),
    ], avisos
    infos = [h.texto for h in hs if h.sev == "info"]
    assert infos == ["11/13 docs declaran 'verificado:' (opt-in) y 3 sin 'rol:' en el frontmatter"], infos
    assert len(hs) == 5


def test_frescura_no_pide_agregar_el_frontmatter_ni_usa_roles_por_nombre():
    archivos = {"docs/glosario.md": "# g\n", "docs/flujo-x.md": "# f\n", "CLAUDE.md": "# c\n"}
    with Arbol(archivos, {"docs": "docs"}) as a:
        hs = m().chequear_frescura(a.ctx())
    assert pares(hs) == [("info", "0/2 docs declaran 'verificado:' (opt-in) y 2 sin 'rol:' en el frontmatter")], pares(hs)
    assert all("agregar" not in (h.arreglo or "") for h in hs)


def test_frescura_usa_la_fecha_de_hoy_del_contexto():
    archivos = {"docs/a.md": _fm("2026-07-01")}
    with Arbol(archivos, {"docs": "docs"}) as a:
        assert [h for h in m().chequear_frescura(a.ctx(date(2026, 9, 28))) if h.sev == "warn"] == []
        avisos = [h.texto for h in m().chequear_frescura(a.ctx(date(2026, 9, 30))) if h.sev == "warn"]
        assert avisos == ["a.md sin verificar hace 91d (volatilidad media -> 90d)"], avisos


def test_frescura_no_aplica_sin_docs():
    with Arbol({"CLAUDE.md": "x\n"}) as a:
        assert pares(m().chequear_frescura(a.ctx())) == [("n/a", "sin knowledge.docs en la config")]


def _es_conocimiento(ruta):
    return ruta.endswith(".md") or ruta.endswith("_claims.json")


def test_agrupar_porcelain_clasifica_cada_estado_sin_perder_la_primera_linea():
    lineas = [
        " M docs/modificado-sin-stagear.md",
        "M  docs/modificado-stageado.md",
        "AM docs/nuevo-y-editado.md",
        "T  docs/cambio-de-tipo.md",
        "?? docs/nuevo.md",
        " D docs/borrado-sin-stagear.md",
        "D  docs/borrado-stageado.md",
        "UU docs/conflicto-uu.md",
        "AA docs/conflicto-aa.md",
        "DD docs/conflicto-dd.md",
        "DU docs/conflicto-du.md",
        "UD docs/conflicto-ud.md",
        "R  docs/viejo.md -> docs/renombrado.md",
        "C  docs/origen.md -> docs/copia.md",
        " M docs/imagen.png",
        "?? docs/_claims.json",
        " M otro/sin-md.txt",
    ]
    for giro in range(len(lineas)):
        orden = lineas[giro:] + lineas[:giro]
        g = m().agrupar_porcelain("\n".join(orden) + "\n", _es_conocimiento)
        assert sorted(g["modificados"]) == sorted([
            "docs/modificado-sin-stagear.md", "docs/modificado-stageado.md", "docs/nuevo-y-editado.md", "docs/cambio-de-tipo.md",
            "docs/viejo.md -> docs/renombrado.md", "docs/origen.md -> docs/copia.md",
        ]), (giro, g)
        assert sorted(g["nuevos"]) == ["docs/_claims.json", "docs/nuevo.md"], (giro, g)
        assert sorted(g["borrados"]) == ["docs/borrado-sin-stagear.md", "docs/borrado-stageado.md"], (giro, g)
        assert sorted(g["conflictos"]) == ["docs/conflicto-aa.md", "docs/conflicto-dd.md", "docs/conflicto-du.md", "docs/conflicto-ud.md", "docs/conflicto-uu.md"], (giro, g)


def test_agrupar_porcelain_quita_las_comillas_de_cada_ruta_y_el_prefijo_de_la_instancia():
    g = m().agrupar_porcelain('R  "docs/a b.md" -> "docs/c d.md"\n?? "docs/con espacio.md"\n', _es_conocimiento)
    assert g["modificados"] == ["docs/a b.md -> docs/c d.md"] and g["nuevos"] == ["docs/con espacio.md"], g
    entrada = "?? sub/docs/a.md\n?? otro/docs/b.md\nR  sub/x.md -> otro/y.md\n M sub/docs/c.md\n"
    g = m().agrupar_porcelain(entrada, _es_conocimiento, "sub/")
    assert g == {"conflictos": [], "borrados": [], "modificados": ["docs/c.md"], "nuevos": ["docs/a.md"]}, g


def test_agrupar_porcelain_ignora_lo_que_no_es_conocimiento_y_las_lineas_vacias():
    g = m().agrupar_porcelain("\n M a.txt\n\n?? b.png\n", _es_conocimiento)
    assert g == {"conflictos": [], "borrados": [], "modificados": [], "nuevos": []}, g


def test_sin_trackear_un_arbol_limpio_no_da_hallazgos():
    archivos = {"CLAUDE.md": "# c\n", "docs/a.md": "# A\n"}
    with Arbol(archivos, {"docs": "docs"}, git=True) as a:
        a.commitear()
        assert m().chequear_sin_trackear(a.ctx()) == []


def test_sin_trackear_ve_modificados_nuevos_borrados_y_renombrados_solo_del_conocimiento():
    archivos = {
        "CLAUDE.md": "# c\n", "docs/a.md": "# A\n", "docs/d.md": "# D\n", "docs/img.png": "x", "docs/_claims.json": "{}\n",
        "notas/b.md": "# B\n", "afuera/z.md": "# Z\n",
    }
    knowledge = {"docs": "docs", "scan": ["notas/**/*.md", "nuevas/**/*.md"]}
    with Arbol(archivos, knowledge, git=True) as a:
        a.commitear()
        a.escribir({
            "docs/a.md": "# A editado\n", "docs/img.png": "y", "docs/_claims.json": '{"a": 1}\n', "docs/nuevo.md": "# N\n", "docs/ñandú.md": "# Ñ\n",
            "docs/con espacio.md": "# E\n", "docs/sub/hondo.md": "# H\n", "docs/d.md": None, "nuevas/hondo/n.md": "# n\n",
            "afuera/z.md": "# Z editado\n", "afuera/nuevo.md": "# x\n",
        })
        git_en(a.repo, "mv", "notas/b.md", "notas/movido.md")
        hs = m().chequear_sin_trackear(a.ctx())
    textos = {h.texto.split(":")[0]: h for h in hs}
    assert all(h.sev == "warn" for h in hs), pares(hs)
    assert list(textos) == ["1 doc(s) BORRADOS sin commitear", "3 doc(s) MODIFICADOS sin commitear", "4 ruta(s) nuevas sin commitear"], pares(hs)
    assert hs[0].texto == "1 doc(s) BORRADOS sin commitear: docs/d.md"
    assert hs[1].texto == "3 doc(s) MODIFICADOS sin commitear: docs/_claims.json, docs/a.md, notas/b.md -> notas/movido.md", hs[1].texto
    assert hs[2].texto == "4 ruta(s) nuevas sin commitear: docs/con espacio.md, docs/nuevo.md, docs/ñandú.md, nuevas/hondo/n.md", hs[2].texto
    assert hs[0].arreglo == "si el borrado es a propósito, corregir los links que lo citaban y commitearlo; si no, recuperarlo"
    assert hs[1].arreglo == "un doc ya citado y editado a medias es el estado más riesgoso: commitear o revertir antes de seguir"
    assert hs[2].arreglo == "git add + commit, o borrarlas si eran temporales"


def test_sin_trackear_lista_los_cuatro_primeros_y_cuenta_el_resto():
    with Arbol({"CLAUDE.md": "# c\n"}, {"docs": "docs"}, git=True) as a:
        a.commitear()
        a.escribir({f"docs/n{i}.md": "x\n" for i in range(6)})
        hs = m().chequear_sin_trackear(a.ctx())
        assert [h.texto for h in hs] == ["6 ruta(s) nuevas sin commitear: docs/n0.md, docs/n1.md, docs/n2.md, docs/n3.md ..."], pares(hs)


def test_sin_trackear_los_conflictos_se_nombran_aparte():
    with Arbol({"CLAUDE.md": "# c\n", "docs/a.md": "uno\n"}, {"docs": "docs"}, git=True) as a:
        a.commitear()
        git_en(a.repo, "checkout", "-q", "-b", "otra")
        a.escribir({"docs/a.md": "dos\n"})
        git_en(a.repo, "commit", "-qam", "otra")
        git_en(a.repo, "checkout", "-q", "main")
        a.escribir({"docs/a.md": "tres\n"})
        git_en(a.repo, "commit", "-qam", "main")
        subprocess.run(["git", "-C", str(a.repo), "merge", "otra"], capture_output=True)
        hs = m().chequear_sin_trackear(a.ctx())
        assert pares(hs) == [("warn", "1 doc(s) EN CONFLICTO sin resolver: docs/a.md")], pares(hs)
        assert hs[0].arreglo == "resolverlo antes de seguir: el doc tiene los marcadores del merge y no se puede commitear hasta sacarlos"


def test_sin_trackear_una_instancia_dentro_de_un_repo_mayor_ve_solo_lo_suyo():
    archivos = {"CLAUDE.md": "# c\n", "docs/a.md": "# A\n"}
    with Arbol(archivos, {"docs": "docs"}, git=True, subcarpeta="instancia") as a:
        escribir(a.repo, {"fuera.md": "x\n"})
        a.commitear()
        a.escribir({"docs/a.md": "# editado\n", "docs/nuevo.md": "# n\n"})
        escribir(a.repo, {"fuera.md": "editado\n", "docs/a.md": "# otro docs en la raíz del repo\n"})
        hs = m().chequear_sin_trackear(a.ctx())
        assert [h.texto for h in hs] == ["1 doc(s) MODIFICADOS sin commitear: docs/a.md", "1 ruta(s) nuevas sin commitear: docs/nuevo.md"], pares(hs)


def test_sin_trackear_sin_repo_git_no_aplica():
    with Arbol({"CLAUDE.md": "# c\n"}, {"docs": "docs"}) as a:
        assert pares(m().chequear_sin_trackear(a.ctx())) == [("n/a", "la raíz no está dentro de un repo git")]


def test_sin_trackear_fuerza_el_idioma_de_git_para_reconocer_que_no_es_un_repo():
    with Arbol({"CLAUDE.md": "# c\n"}, {"docs": "docs"}) as a:
        entornos = []
        original = subprocess.run

        def falso(args, **kwargs):
            entornos.append(kwargs["env"])
            return subprocess.CompletedProcess(args, 128, b"", b"fatal: not a git repository")

        subprocess.run = falso
        try:
            hs = m().chequear_sin_trackear(a.ctx())
        finally:
            subprocess.run = original
        assert pares(hs) == [("n/a", "la raíz no está dentro de un repo git")], pares(hs)
        assert len(entornos) == 1 and entornos[0]["LC_ALL"] == "C", entornos


def test_sin_trackear_si_git_status_falla_es_un_error_interno():
    with Arbol({"CLAUDE.md": "# c\n"}, {"docs": "docs"}) as a:
        respuestas = [subprocess.CompletedProcess([], 0, b"", b""), subprocess.CompletedProcess([], 1, b"", b"fatal: index roto")]
        original = subprocess.run
        subprocess.run = lambda args, **kwargs: respuestas.pop(0)
        try:
            try:
                m().chequear_sin_trackear(a.ctx())
            except RuntimeError as error:
                assert "git status" in str(error) and "index roto" in str(error), error
            else:
                raise AssertionError("un git status fallido debe lanzar RuntimeError")
        finally:
            subprocess.run = original
        assert respuestas == []


def test_sin_trackear_un_fallo_de_git_distinto_de_no_ser_repo_es_error_interno():
    with Arbol({"CLAUDE.md": "# c\n"}, {"docs": "docs"}) as a:
        original = subprocess.run

        def falso(args, **kwargs):
            return subprocess.CompletedProcess(args, 128, b"", b"fatal: detected dubious ownership in repository")

        subprocess.run = falso
        try:
            try:
                m().chequear_sin_trackear(a.ctx())
            except RuntimeError as error:
                assert "dubious ownership" in str(error), error
            else:
                raise AssertionError("un fallo de git que no es 'no es un repo' debe lanzar RuntimeError")
        finally:
            subprocess.run = original


def test_sin_trackear_sin_docs_mira_solo_el_indice_y_las_afirmaciones():
    with Arbol({"CLAUDE.md": "# c\n", "otros/x.md": "x\n"}, git=True) as a:
        a.commitear()
        a.escribir({"CLAUDE.md": "# editado\n", "otros/x.md": "editado\n"})
        assert pares(m().chequear_sin_trackear(a.ctx())) == [("warn", "1 doc(s) MODIFICADOS sin commitear: CLAUDE.md")]


def test_sin_trackear_si_git_falla_es_un_error_interno_y_no_un_hallazgo():
    with Arbol({"CLAUDE.md": "# c\n"}, git=True) as a:
        original = subprocess.run

        def sin_git(*_args, **_kwargs):
            raise FileNotFoundError("git")

        subprocess.run = sin_git
        try:
            try:
                m().chequear_sin_trackear(a.ctx())
            except RuntimeError as error:
                assert "git" in str(error), error
            else:
                raise AssertionError("un git inexistente debe lanzar RuntimeError")
        finally:
            subprocess.run = original


def _arbol_de_cruce():
    archivos = {
        "CLAUDE.md": "---\nrol: resumen\n---\nEl motor tiene 10 módulos.\n",
        "docs/a.md": "---\nrol: autoritativo\n---\nEl motor tiene 12 módulos y 4 tablas.\n",
        "docs/b.md": 'Dice "antes eran 7 módulos" y hoy 12 módulos; hay 4 tablas.\n',
        "docs/solo.md": "Una sola capa con 3 capas y nada que comparar.\n",
        "docs/otra.md": "Hay 5 capas aquí.\n",
    }
    for i in range(1, 7):
        archivos[f"docs/e{i}.md"] = f"Usa `Entidad_Uno` y {'`Otra_Cosa` ' if i <= 5 else ''}`fn` y `X1`.\n"
    return archivos


def test_cifras_comparables_agrupa_por_sustantivo_y_solo_lo_que_difiere_entre_docs():
    with Arbol(_arbol_de_cruce(), {"docs": "docs", "quantities": ["módulos", "tablas", "capas"]}) as a:
        grupos = m().cifras_comparables(a.ctx())
        assert sorted(grupos) == ["capas", "módulos"], sorted(grupos)
        filas = sorted((Path(d).name, n, cifra) for d, n, cifra, _ in grupos["módulos"])
        assert filas == [("CLAUDE.md", 4, "10"), ("a.md", 4, "12"), ("b.md", 1, "12")], filas
        assert all("módulos" in f for *_, f in grupos["módulos"])
        capas = sorted((Path(d).name, cifra) for d, _, cifra, _ in grupos["capas"])
        assert capas == [("otra.md", "5"), ("solo.md", "3")], capas


def test_cifras_comparables_descarta_la_cifra_citada_entre_comillas_y_recorta_la_frase():
    larga = "x" * 200 + " 12 módulos " + "y" * 200 + "\n"
    justo = "j" * 140 + " 9 módulos"
    pasado = "h" * 141 + " 8 módulos"
    archivos = {"CLAUDE.md": larga, "docs/a.md": 'dice «antes 99 módulos» y hoy 3 módulos\n', "docs/b.md": justo + "\n", "docs/c.md": pasado + "\n"}
    with Arbol(archivos, {"docs": "docs", "quantities": ["módulos"]}) as a:
        filas = m().cifras_comparables(a.ctx())["módulos"]
        cifras = sorted(c for _, _, c, _ in filas)
        assert cifras == ["12", "3", "8", "9"], cifras
        frase = next(f for _, _, c, f in filas if c == "12")
        assert frase == "..." + "x" * 59 + " 12 módulos " + "y" * 79 + "...", frase
        corta = next(f for _, _, c, f in filas if c == "3")
        assert corta == "dice «antes 99 módulos» y hoy 3 módulos", corta
        assert len(justo) == 150 and next(f for _, _, c, f in filas if c == "9") == justo
        recortada = next(f for _, _, c, f in filas if c == "8")
        assert recortada == "..." + pasado[82:] + "...", recortada


def test_cifras_comparables_el_mas_cuenta_como_otra_cifra_y_no_distingue_mayusculas():
    with Arbol({"CLAUDE.md": "hay 10+ MÓDULOS\n", "docs/a.md": "hay 10 módulos\n"}, {"docs": "docs", "quantities": ["módulos"]}) as a:
        filas = m().cifras_comparables(a.ctx())["módulos"]
        assert sorted(c for _, _, c, _ in filas) == ["10", "10+"], filas


def test_superficie_de_cruce_pide_seis_docs_y_ordena_por_presencia():
    with Arbol(_arbol_de_cruce(), {"docs": "docs"}) as a:
        sup = m().superficie_de_cruce(a.ctx())
    assert [(e, len(d)) for e, d in sup] == [("Entidad_Uno", 6)], sup


def test_superficie_de_cruce_cuenta_el_indice_y_no_las_entidades_cortas():
    archivos = {"CLAUDE.md": "`Alfa_Uno` `ab`\n"}
    for i in range(5):
        archivos[f"docs/d{i}.md"] = "`Alfa_Uno` `ab` `Beta.Dos`\n"
    with Arbol(archivos, {"docs": "docs"}) as a:
        sup = m().superficie_de_cruce(a.ctx())
    assert [(e, sorted(d)) for e, d in sup] == [("Alfa_Uno", ["CLAUDE.md", "d0.md", "d1.md", "d2.md", "d3.md", "d4.md"])], sup


def test_cruce_imprime_prioridad_superficie_y_candidatos_con_su_marca_de_rol():
    with Arbol(_arbol_de_cruce(), {"docs": "docs", "quantities": ["módulos", "capas"]}) as a:
        codigo, salida, error = correr_main(a, "--cruce")
    assert (codigo, error) == (0, ""), (codigo, error)
    lineas = salida.splitlines()
    assert "[Prioridad de lectura]" in lineas
    assert "  Empezar por: CLAUDE.md" in lineas, lineas
    assert "  9 doc(s) sin 'rol:' declarado -- se leen al final, sin prioridad." in lineas, lineas
    assert "[Detector 1 - superficie de cruce (entidades en >=6 docs)]" in lineas
    assert any(l.startswith("  Entidad_Uno") and " 6 docs  " in l for l in lineas), lineas
    assert "[Detector 2 - cifras comparables (CANDIDATOS, no hallazgos)]" in lineas
    assert "  ~ módulos" in lineas and "  ~ capas" in lineas, lineas
    assert any(l.startswith("      (R) CLAUDE.md:4  [10]  ") for l in lineas), lineas
    assert any(l.startswith("      (A) a.md:4  [12]  ") for l in lineas), lineas
    assert any(l.startswith("      (?) b.md:1  [12]  ") for l in lineas), lineas
    assert any("Desempate" in l for l in lineas) and any("NUNCA" in l for l in lineas)


def test_cruce_sin_candidatos_lo_dice_y_sigue_en_cero():
    with Arbol({"CLAUDE.md": "nada\n", "docs/a.md": "nada\n"}, {"docs": "docs", "quantities": ["módulos"]}) as a:
        codigo, salida, _ = correr_main(a, "--cruce")
    assert codigo == 0 and "  (ninguna cifra del mismo sustantivo difiere entre docs)" in salida.splitlines(), salida
    assert "Desempate" not in salida


def test_cruce_sin_docs_no_aplica_y_sin_vocabulario_solo_corre_el_detector_uno():
    with Arbol({"CLAUDE.md": "x\n"}) as a:
        codigo, salida, error = correr_main(a, "--cruce")
        assert (codigo, error) == (0, "") and "no aplica: sin knowledge.docs en la config" in salida, (codigo, salida, error)
        assert "Detector" not in salida
    with Arbol(_arbol_de_cruce(), {"docs": "docs"}) as a:
        codigo, salida, _ = correr_main(a, "--cruce")
        assert codigo == 0
        lineas = salida.splitlines()
        assert any(l.startswith("  Entidad_Uno") for l in lineas), lineas
        assert "  no aplica: sin knowledge.quantities en la config" in lineas, lineas
        assert "  ~ módulos" not in lineas


def test_cruce_nunca_sale_con_deuda_aunque_haya_candidatos_y_un_error_interno_da_dos():
    with Arbol(_arbol_de_cruce(), {"docs": "docs", "quantities": ["módulos"]}) as a:
        assert correr_main(a, "--cruce")[0] == 0
        original = m().cifras_comparables

        def roto(_ctx):
            raise ValueError("boom")

        m().cifras_comparables = roto
        try:
            codigo, salida, error = correr_main(a, "--cruce")
        finally:
            m().cifras_comparables = original
        assert codigo == 2 and "error interno (boom)" in error, (codigo, error)


SANO = {"CLAUDE.md": "- [a](docs/a.md)\n", "docs/a.md": "# A\n"}


def test_cli_arbol_sano_sale_con_cero_y_el_informe_exacto():
    with Arbol(SANO, {"docs": "docs", "quantities": ["tablas"]}, git=True) as a:
        a.commitear()
        antes = a.instantanea()
        codigo, salida, error = a.cli()
        assert a.instantanea() == antes, "el doctor no debe escribir nada"
    salida = salida.replace("\r\n", "\n")
    assert (codigo, error) == (0, ""), (codigo, error)
    assert salida == (
        "\n[Índice y navegación]\n"
        "  ok   docs indexados en el índice\n"
        "  ok   links .md\n"
        "  ok   anclas de sección\n"
        "  ok   cifras en headings\n"
        "  ok   tope del índice\n"
        "\n[Frescura]\n"
        "  ok   verificación de docs -- 0/1 docs declaran 'verificado:' (opt-in) y 1 sin 'rol:' en el frontmatter\n"
        "\n[Higiene]\n"
        "  ok   todo commiteado\n"
        "\n"
        "DIAGNÓSTICO: sistema de conocimiento SANO.\n"
    ), salida


def test_cli_salida_en_utf8_aunque_la_consola_no_lo_sea():
    with Arbol(SANO, {"docs": "docs"}) as a:
        completado = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=a.raiz, capture_output=True, env={**a.entorno(), "PYTHONIOENCODING": "cp1252"}, timeout=120)
    assert completado.returncode == 0, completado.stderr
    assert "DIAGNÓSTICO".encode("utf-8") in completado.stdout and "Índice".encode("utf-8") in completado.stdout


def test_cli_una_falla_sale_con_uno_y_muestra_el_arreglo():
    with Arbol({"CLAUDE.md": "[roto](nada.md)\n- [a](docs/a.md)\n", "docs/a.md": "# A\n", "docs/b.md": "# B\n"}, {"docs": "docs"}) as a:
        codigo, salida, error = a.cli()
    assert (codigo, error) == (1, ""), (codigo, error)
    lineas = salida.splitlines()
    assert "  FAIL links .md (1)" in lineas, lineas
    assert "       - CLAUDE.md -> nada.md (destino inexistente)" in lineas
    assert "         -> corregir la ruta o crear el destino" in lineas
    assert "  warn docs indexados en el índice (1)" in lineas
    assert "       - docs/b.md no está linkeado desde CLAUDE.md" in lineas
    assert "DIAGNÓSTICO: 1 falla(s), 1 advertencia(s). Las FAIL rompen un mecanismo -- atenderlas primero." in lineas, lineas


def test_cli_solo_deuda_sale_con_tres():
    with Arbol({"CLAUDE.md": "- [a](docs/a.md)\n", "docs/a.md": "# A\n", "docs/b.md": "# B\n"}, {"docs": "docs"}) as a:
        codigo, salida, error = a.cli()
    assert (codigo, error) == (3, ""), (codigo, error)
    assert salida.splitlines()[-1] == "DIAGNÓSTICO: sin fallas, 1 advertencia(s) de deuda.", salida


def test_cli_cuenta_cada_hallazgo_y_acota_la_lista_salvo_con_v():
    archivos = {"CLAUDE.md": "indice\n", **{f"docs/d{i}.md": "x\n" for i in range(8)}}
    with Arbol(archivos, {"docs": "docs"}) as a:
        codigo, salida, _ = a.cli()
        assert codigo == 3
        lineas = salida.splitlines()
        assert "  warn docs indexados en el índice (8)" in lineas, lineas
        assert sum(1 for l in lineas if l.startswith("       - docs/d")) == 6, lineas
        assert "       (+2 más -- correr con --v)" in lineas
        assert lineas[-1] == "DIAGNÓSTICO: sin fallas, 8 advertencia(s) de deuda."
        for bandera in ("--v", "-v"):
            codigo, salida, _ = a.cli(bandera)
            lineas = salida.splitlines()
            assert codigo == 3 and sum(1 for l in lineas if l.startswith("       - docs/d")) == 8, (bandera, lineas)
            assert not any("más -- correr con --v" in l for l in lineas)


def test_cli_lo_que_no_aplica_se_dice_y_no_cuenta():
    with Arbol({"CLAUDE.md": "indice\n"}) as a:
        codigo, salida, error = a.cli()
    assert (codigo, error) == (0, ""), (codigo, error)
    lineas = salida.splitlines()
    assert "  n/a  docs indexados en el índice -- sin knowledge.docs en la config" in lineas, lineas
    assert "  n/a  cifras en headings -- sin knowledge.docs en la config" in lineas
    assert "  n/a  verificación de docs -- sin knowledge.docs en la config" in lineas
    assert "  n/a  todo commiteado -- la raíz no está dentro de un repo git" in lineas
    assert "  ok   links .md" in lineas and "  ok   tope del índice" in lineas
    assert lineas[-1] == "DIAGNÓSTICO: sistema de conocimiento SANO."


def test_cli_sin_instancia_sale_con_dos_y_un_mensaje_claro():
    base = Path(tempfile.mkdtemp(prefix="conocimiento-sin-"))
    try:
        entorno = {c: v for c, v in os.environ.items() if c != "CLAUDE_PROJECT_DIR"}
        completado = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=base, capture_output=True, env=entorno, timeout=120)
    finally:
        shutil.rmtree(base, onexc=_forzar_borrado)
    assert completado.returncode == 2, completado.returncode
    assert completado.stdout == b""
    mensaje = completado.stderr.decode("utf-8")
    assert mensaje.startswith("conocimiento: ") and "workspace.config.json" in mensaje, mensaje


def test_cli_usa_claude_project_dir_para_hallar_la_instancia():
    with Arbol(SANO, {"docs": "docs"}) as a:
        base = Path(tempfile.mkdtemp(prefix="conocimiento-lejos-"))
        try:
            entorno = {**a.entorno(), "CLAUDE_PROJECT_DIR": str(a.raiz)}
            completado = subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=base, capture_output=True, env=entorno, timeout=120)
        finally:
            shutil.rmtree(base, onexc=_forzar_borrado)
        assert completado.returncode == 0, completado.stderr
        assert "DIAGNÓSTICO".encode("utf-8") in completado.stdout


def test_cli_con_la_config_rota_sale_con_dos_y_nombra_la_clave():
    for knowledge, clave in (([], "knowledge debe ser un objeto"), ({"docs": 3}, "knowledge.docs"), ({"index_max_lines": 0}, "knowledge.index_max_lines"), ({"zzz": 1}, "knowledge.zzz")):
        with Arbol(SANO, knowledge) as a:
            codigo, salida, error = a.cli()
        assert (codigo, salida) == (2, ""), (knowledge, codigo, salida)
        assert error.startswith("conocimiento: ") and clave in error, error
    with Arbol(SANO, config="{ no es json") as a:
        codigo, salida, error = a.cli()
        assert (codigo, salida) == (2, "") and "workspace.config.json" in error, (codigo, salida, error)


def test_cli_un_argumento_desconocido_sale_con_dos():
    with Arbol(SANO, {"docs": "docs"}) as a:
        for args in (("--no-existe",), ("--c",), ("--cruce", "extra")):
            codigo, salida, error = a.cli(*args)
            assert codigo == 2 and salida == "" and error != "", (args, codigo, salida, error)


def test_main_un_error_interno_de_un_chequeo_sale_con_dos_sin_disfrazarlo_de_hallazgo():
    with Arbol(SANO, {"docs": "docs"}) as a:
        original = m().GRUPOS

        def roto(_ctx):
            raise ValueError("boom")

        m().GRUPOS = [("Grupo", [("roto", roto)])]
        try:
            codigo, salida, error = correr_main(a)
        finally:
            m().GRUPOS = original
        assert codigo == 2 and "error interno (boom)" in error, (codigo, salida, error)
        assert "DIAGNÓSTICO" not in salida


def _con_grupos(arbol, grupos, *args):
    original = m().GRUPOS
    m().GRUPOS = grupos
    try:
        return correr_main(arbol, *args)
    finally:
        m().GRUPOS = original


def test_main_la_worklist_no_es_deuda_y_el_exit_sigue_a_la_severidad():
    H = m().Hallazgo
    with Arbol(SANO, {"docs": "docs"}) as a:
        solo_lista = [("G", [("lista", lambda _c: [H("worklist", "a decidir 1", "cruzar"), H("worklist", "a decidir 2")])])]
        codigo, salida, _ = _con_grupos(a, solo_lista)
        lineas = salida.splitlines()
        assert codigo == 0, codigo
        assert "  worklist lista (2)" in lineas, lineas
        assert "       - a decidir 1" in lineas and "         -> cruzar" in lineas
        assert "DIAGNÓSTICO: sistema de conocimiento SANO." in lineas
        assert "WORKLIST: 2 item(s) para cruzar o decidir. No son deuda ni cuentan en el exit." in lineas
        mixto = [("G", [("mixto", lambda _c: [H("warn", "deuda"), H("worklist", "lista")])])]
        codigo, salida, _ = _con_grupos(a, mixto)
        lineas = salida.splitlines()
        assert codigo == 3, codigo
        assert "  warn mixto (2)" in lineas and "       - deuda" in lineas and "       - (worklist) lista" in lineas, lineas
        assert "DIAGNÓSTICO: sin fallas, 1 advertencia(s) de deuda." in lineas
        assert "WORKLIST: 1 item(s) para cruzar o decidir. No son deuda ni cuentan en el exit." in lineas
        con_fail = [("G", [("duro", lambda _c: [H("FAIL", "roto"), H("warn", "deuda"), H("info", "nota")])])]
        codigo, salida, _ = _con_grupos(a, con_fail)
        assert codigo == 1 and "       info: nota" in salida.splitlines(), salida
        assert "WORKLIST" not in salida


def test_main_una_info_sola_se_muestra_junto_al_ok_y_no_cuenta():
    H = m().Hallazgo
    with Arbol(SANO, {"docs": "docs"}) as a:
        codigo, salida, _ = _con_grupos(a, [("G", [("nota", lambda _c: [H("info", "dato 1"), H("info", "dato 2")])])])
        assert codigo == 0 and "  ok   nota -- dato 1" in salida.splitlines(), salida


def test_un_tier_nuevo_se_suma_con_una_funcion_y_una_entrada():
    H = m().Hallazgo
    with Arbol(SANO, {"docs": "docs"}) as a:
        visto = {}

        def modo_prueba(ctx, args):
            visto["ctx"] = ctx
            visto["args"] = (args.extra, args.ruta)
            print("modo de prueba")
            return 7

        def chequeo_nuevo(ctx):
            return [H("warn", "del chequeo nuevo", "arreglarlo")]

        grupos, modos = m().GRUPOS, m().MODOS
        m().MODOS = {**modos, "prueba": m().Modo(modo_prueba, (("--extra", {"action": "store_true"}), ("--ruta", {"metavar": "RUTA"})))}
        m().GRUPOS = [*grupos, ("Nuevo", [("chequeo nuevo", chequeo_nuevo)])]
        try:
            codigo, salida, error = correr_main(a, "--prueba", "--extra", "--ruta", "x.json")
            assert (codigo, salida, error) == (7, "modo de prueba\n", ""), (codigo, salida, error)
            assert visto["args"] == (True, "x.json") and visto["ctx"].docs == "docs"
            codigo, salida, _ = correr_main(a)
            assert codigo == 3 and "[Nuevo]" in salida and "  warn chequeo nuevo (1)" in salida.splitlines(), salida
            codigo, salida, error = correr_main(a, "--prueba", "--cruce")
            assert codigo == 2 and salida == "" and error != "", (codigo, salida, error)
        finally:
            m().GRUPOS, m().MODOS = grupos, modos


def test_el_registro_real_declara_los_grupos_y_el_modo_cruce():
    nombres = [g for g, _ in m().GRUPOS]
    assert nombres == ["Índice y navegación", "Frescura", "Higiene"], nombres
    etiquetas = [e for _, cs in m().GRUPOS for e, _ in cs]
    assert etiquetas == [
        "docs indexados en el índice", "links .md", "anclas de sección", "cifras en headings", "tope del índice",
        "verificación de docs", "todo commiteado",
    ], etiquetas
    assert list(m().MODOS) == ["cruce"], list(m().MODOS)


def test_la_fuente_esta_en_lf_sin_bom_y_con_salto_final():
    for ruta in (SCRIPT, Path(__file__)):
        crudo = ruta.read_bytes()
        assert b"\r" not in crudo and not crudo.startswith(b"\xef\xbb\xbf") and crudo.endswith(b"\n"), ruta.name


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
