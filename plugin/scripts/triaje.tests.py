import atexit
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_RUTA = AQUI / "triaje.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []


def _cargar():
    spec = importlib.util.spec_from_file_location("triaje", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None

ALFA = ("CREATE PROCEDURE esq.Proc_Alfa\n    @Id INT,\n    @Nombre VARCHAR(50) = NULL\nAS\nBEGIN\n"
        "    SELECT 1\nEND\n")
BETA = "CREATE PROCEDURE esq.Proc_Beta\nAS\nBEGIN\n    EXEC esq.Proc_Alfa @Id = 1\nEND\n"
GAMMA = "CREATE PROCEDURE esq.Proc_Gamma\nAS\nBEGIN\n    SELECT 2\nEND\n"
SERVICIO = "class Servicio { }\n"
EFECTO = "EXEC esq.proc_encolar @Tipo = 2"

SQL_ALFA = "src/ventas/Proc_Alfa.sql"
SQL_BETA = "src/ventas/Proc_Beta.sql"
SQL_GAMMA = "src/ventas/Proc_Gamma.sql"
CS_SVC = "Data/Servicio.cs"

DOC_SISTEMAS = "# Sistemas\n\nLa cola sale por proc_encolar hacia terceros.\n\nEl correo usa SmtpClient.\n"
MARCADOR_COLA = {"id": "cola", "patron": r"\bproc_encolar\b", "ejemplo": EFECTO, "fuente": "docs/sistemas.md:3",
                 "ancla": "proc_encolar", "descripcion": "cola de trabajos hacia terceros"}
MARCADOR_CORREO = {"id": "correo", "patron": r"SmtpClient", "ejemplo": "var c = new SmtpClient(host);",
                   "fuente": "docs/sistemas.md:5", "ancla": "SmtpClient", "descripcion": "correo saliente"}
NOMBRES = ("valor", "total", "tarifa", "cobro", "propina")


def senales(marcadores=(MARCADOR_COLA, MARCADOR_CORREO), nombres=NOMBRES, extra=""):
    return "MARCADORES = %r\nDINERO_NOMBRES = %r\n%s" % (list(marcadores), nombres, extra)


# ---------------------------------------------------------------- temporales y git

def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "core.autocrlf=false", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno_sin_git())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def escribir(raiz, archivos):
    for rel, texto in archivos.items():
        p = Path(raiz) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)


def commitear(repo, archivos, mensaje="c"):
    escribir(repo, archivos)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", mensaje)
    return git(repo, "rev-parse", "HEAD")


def publicar(repo, ref="HEAD"):
    git(repo, "update-ref", "refs/remotes/origin/main", ref)


def repo_en(ruta, archivos):
    ruta.mkdir(parents=True)
    git(ruta, "init", "-q")
    commitear(ruta, archivos, "inicial")
    publicar(ruta)
    git(ruta, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    return ruta


_PLANTILLA = []


def _borrar(ruta):
    if ruta.exists():
        shutil.rmtree(ruta, onexc=_quitar)
    if ruta.exists():
        SOBRANTES.append(str(ruta))


def _plantilla():
    if not _PLANTILLA:
        base = Path(tempfile.mkdtemp(prefix="triaje-plantilla-"))
        atexit.register(_borrar, base)
        repo_en(base / "db", {SQL_ALFA: ALFA, SQL_BETA: BETA, SQL_GAMMA: GAMMA, "README.md": "# db\n"})
        repo_en(base / "web", {CS_SVC: SERVICIO})
        _PLANTILLA.append(base)
    return _PLANTILLA[0]


def copiar_repo(nombre, destino):
    shutil.copytree(_plantilla() / nombre, destino)
    git(destino, "update-index", "-q", "--refresh")
    return destino


class Mundo:
    def __init__(self, modulo=None, linea_base=True):
        self.modulo = senales() if modulo is None else modulo
        self.linea_base = linea_base

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="triaje-test-"))
        self.raiz = self.base / "inst"
        escribir(self.raiz, {"docs/sistemas.md": DOC_SISTEMAS})
        if self.modulo is not False:
            escribir(self.raiz, {".claude/reglas/senales.py": self.modulo})
        self.db = copiar_repo("db", self.base / "repos" / "db")
        self.web = copiar_repo("web", self.base / "repos" / "web")
        sql = {"extensions": [".sql"], "repos": ["db"], "workshop": ["tickets/**/T-[0-9]*/SQL/esq.*.sql"]}
        if self.linea_base:
            sql["workshop_baseline"] = {"repo": "db", "under": "src", "strip_prefix": "esq."}
        config = {"schema_version": 1, "repos": {"db": {}, "web": {}},
                  "layers": {"sql": sql, "web": {"extensions": [".cs"], "repos": ["web"]}}}
        escribir(self.raiz, {"workspace.config.json": json.dumps(config),
                             "workspace.local.json": json.dumps({"repos": {"db": {"path": str(self.db)}, "web": {"path": str(self.web)}}})})
        return self

    def analizar(self, repos=None, taller=()):
        repos = [(str(r), None) for r in (repos if repos is not None else [self.db])]
        return M.analizar(repos, taller=[str(t) for t in taller], raiz=str(self.raiz))

    def taller(self, nombre, texto):
        rel = "tickets/T-1-x/SQL/" + nombre
        escribir(self.raiz, {rel: texto})
        return self.raiz / rel

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))


def nivel(r, id_):
    return r["senales"][id_]["nivel"]


def detalle(r, id_):
    return " | ".join(r["senales"][id_]["detalle"])


def solo_escala_consumidores(r):
    assert r["modo"] == "completo" and r["motivos"] == ["señal consumidores: invalida"], (r["motivos"], r["senales"])


def indice(repo):
    return git(repo, "ls-files", "--stage")


def correr(argv):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            codigo = M.main(argv)
        except SystemExit as exc:
            codigo = exc.code if isinstance(exc.code, int) else 2
    return codigo, salida.getvalue(), error.getvalue()


# ---------------------------------------------------------------- modos

def test_modo_cero_solo_docs():
    with Mundo() as w:
        escribir(w.db, {"README.md": "# db\nnota nueva\n", "notas/nota.txt": "x\n"})
        r = w.analizar()
        assert r["modo"] == "0", r
        assert any("docs" in m for m in r["motivos"])
        assert all(nivel(r, i) == "negativa" for i in M.SENALES)


def test_sin_cambios():
    with Mundo() as w:
        r = w.analizar()
        assert r["modo"] == "sin-cambios" and r["repos"][0]["archivos"] == []


def test_todas_las_senales_en_negativo_salvo_consumidores_que_llega_en_u7c():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        for id_ in ("efecto", "dinero", "migracion", "contrato", "capas"):
            assert nivel(r, id_) == "negativa", (id_, r["senales"][id_])
        solo_escala_consumidores(r)
        assert r["no_detectable"], "tiene que declarar lo que no detecta"


# ---------------------------------------------------------------- efecto hacia otro sistema

def test_efecto_end_to_end_escala_y_cita_la_fuente():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", EFECTO)})
        r = w.analizar()
        assert nivel(r, "efecto") == "positiva" and r["modo"] == "completo"
        assert "señal efecto: positiva" in r["motivos"]
        assert "cola (docs/sistemas.md:3) cola de trabajos hacia terceros" in detalle(r, "efecto"), detalle(r, "efecto")


def test_efecto_quitado_escala():
    with Mundo() as w:
        commitear(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", EFECTO)})
        publicar(w.db)
        escribir(w.db, {SQL_ALFA: ALFA})
        r = w.analizar()
        assert nivel(r, "efecto") == "positiva", r["senales"]["efecto"]
        assert "cola" in detalle(r, "efecto") and "solo en la base" in detalle(r, "efecto")


def test_efecto_movido_de_lugar_escala():
    antes = ALFA.replace("    SELECT 1\n", "    SELECT 1\n    " + EFECTO + "\n")
    despues = ALFA.replace("    SELECT 1\n", "    " + EFECTO + "\n    SELECT 1\n")
    with Mundo() as w:
        commitear(w.db, {SQL_ALFA: antes})
        publicar(w.db)
        escribir(w.db, {SQL_ALFA: despues})
        assert nivel(w.analizar(), "efecto") == "positiva"


def test_efecto_en_contexto_sin_tocar_de_un_archivo_tocado_escala():
    con_efecto = ALFA.replace("    SELECT 1\n", "    SELECT 1\n    " + EFECTO + "\n")
    with Mundo() as w:
        commitear(w.db, {SQL_ALFA: con_efecto})
        publicar(w.db)
        escribir(w.db, {SQL_ALFA: con_efecto.replace("VARCHAR(50)", "VARCHAR(80)")})
        r = w.analizar()
        assert nivel(r, "efecto") == "positiva"
        assert "solo en la base" not in detalle(r, "efecto"), "sigue en lo actual: no es un efecto quitado"


def test_efecto_en_cualquier_lenguaje_y_un_marcador_por_id():
    with Mundo() as w:
        escribir(w.web, {CS_SVC: "class Servicio {\n    void A() { new SmtpClient(h); }\n    void B() { new SmtpClient(i); }\n}\n"})
        r = w.analizar(repos=[w.web])
        assert nivel(r, "efecto") == "positiva"
        assert detalle(r, "efecto").count("correo (") == 1, detalle(r, "efecto")


def test_efecto_ni_en_la_base_ni_en_lo_actual_es_negativa():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 2")})
        r = w.analizar()
        assert nivel(r, "efecto") == "negativa", r["senales"]["efecto"]
        assert "sin marcadores de efecto" in detalle(r, "efecto")


def test_efecto_sin_modulo_de_la_instancia_es_negativa_y_lo_declara():
    with Mundo(modulo=False) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", EFECTO)})
        r = w.analizar()
        assert nivel(r, "efecto") == "negativa" and nivel(r, "dinero") == "negativa", r["senales"]
        assert "0 marcadores" in detalle(r, "efecto")
        assert any("marcadores de la instancia" in n for n in r["no_detectable"]), r["no_detectable"]


# ---------------------------------------------------------------- el módulo de la instancia

def _efecto_invalido(modulo, texto_esperado):
    with Mundo(modulo=modulo) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        assert nivel(r, "efecto") == "invalida", r["senales"]["efecto"]
        assert r["modo"] == "completo" and "señal efecto: invalida" in r["motivos"]
        assert texto_esperado in detalle(r, "efecto"), detalle(r, "efecto")
        return r


def test_modulo_un_ejemplo_que_su_patron_no_detecta_invalida_el_efecto():
    _efecto_invalido(senales([dict(MARCADOR_COLA, ejemplo="EXEC esq.otra_cosa")]), "cola: su patrón no detecta su ejemplo")


def test_modulo_el_ancla_fuera_de_la_linea_fuente_invalida_el_efecto():
    _efecto_invalido(senales([dict(MARCADOR_COLA, fuente="docs/sistemas.md:5")]), "cola: la línea docs/sistemas.md:5 no contiene «proc_encolar»")


def test_modulo_una_fuente_que_no_existe_o_sin_esa_linea_invalida_el_efecto():
    _efecto_invalido(senales([dict(MARCADOR_COLA, fuente="docs/otro.md:3")]), "cola: no existe docs/otro.md")
    _efecto_invalido(senales([dict(MARCADOR_COLA, fuente="docs/sistemas.md:99")]), "cola: docs/sistemas.md no tiene la línea 99")


def test_modulo_una_fuente_mal_formada_o_fuera_de_la_instancia_invalida_el_efecto():
    for fuente in ("docs/sistemas.md", "docs/sistemas.md:0", "docs/sistemas.md:x", "../afuera.md:1", "/docs/sistemas.md:3"):
        _efecto_invalido(senales([dict(MARCADOR_COLA, fuente=fuente)]), "cola: la fuente %r" % fuente)


def test_modulo_un_id_repetido_un_patron_roto_o_un_campo_faltante_invalida_el_efecto():
    _efecto_invalido(senales([MARCADOR_COLA, dict(MARCADOR_CORREO, id="cola")]), "cola: id repetido")
    _efecto_invalido(senales([dict(MARCADOR_COLA, patron="(sin cerrar")]), "cola: el patrón no compila")
    sin_ancla = {k: v for k, v in MARCADOR_COLA.items() if k != "ancla"}
    _efecto_invalido(senales([sin_ancla]), "marcador 1: faltan campos o no son texto: ancla")
    _efecto_invalido(senales([dict(MARCADOR_COLA, descripcion=3)]), "marcador 1: faltan campos o no son texto: descripcion")
    _efecto_invalido("MARCADORES = 'x'\n", "MARCADORES debe ser una lista")


def test_modulo_que_no_carga_invalida_efecto_y_dinero():
    r = _efecto_invalido("raise ValueError('roto adrede')\n", "el módulo no carga (ValueError: roto adrede)")
    assert nivel(r, "dinero") == "invalida", r["senales"]["dinero"]


def test_modulo_con_nombres_de_dinero_que_no_son_palabras_invalida_el_dinero():
    for nombres in ("valor", ("valor", ""), ("valor", 3)):
        r = _efecto_invalido(senales(nombres=nombres), "DINERO_NOMBRES debe ser una lista de palabras")
        assert nivel(r, "dinero") == "invalida"


def test_modulo_con_cota_o_no_detectable_mal_formados_invalida():
    _efecto_invalido(senales(extra="COTA = 3\n"), "COTA debe ser un texto")
    _efecto_invalido(senales(extra="NO_DETECTABLE = 'x'\n"), "NO_DETECTABLE debe ser una lista de textos")


def test_modulo_valido_no_dispara_con_lineas_sin_marcadores_y_suma_su_no_detectable_y_su_cota():
    extra = "COTA = 'sin mirar el sistema viejo'\nNO_DETECTABLE = ['efectos por colas del sistema viejo']\n"
    with Mundo(modulo=senales(extra=extra)) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "UPDATE esq.Turno SET Estado = 2")})
        r = w.analizar()
        assert nivel(r, "efecto") == "negativa", r["senales"]["efecto"]
        assert "efectos por colas del sistema viejo" in r["no_detectable"]
        assert any("sin mirar el sistema viejo" in n for n in r["no_detectable"]), r["no_detectable"]


# ---------------------------------------------------------------- índice y archivos solo con stat sucio

def test_un_archivo_solo_con_stat_sucio_no_cuenta_y_el_indice_queda_intacto():
    with Mundo() as w:
        git(w.db, "update-index", "--refresh")
        time.sleep(1.2)
        os.utime(w.db / SQL_BETA, None)
        idx = w.db / ".git" / "index"
        antes = idx.read_bytes()
        r = w.analizar()
        assert idx.read_bytes() == antes, "el .git/index cambio"
        assert r["repos"][0]["archivos"] == [] and r["modo"] == "sin-cambios", r["repos"][0]["archivos"]
    with Mundo() as w:
        git(w.db, "update-index", "--refresh")
        time.sleep(1.2)
        os.utime(w.db / SQL_BETA, None)
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 2")})
        idx = w.db / ".git" / "index"
        antes = idx.read_bytes()
        r = w.analizar()
        assert idx.read_bytes() == antes
        assert [a["ruta"] for a in r["repos"][0]["archivos"]] == [SQL_ALFA], r["repos"][0]["archivos"]


# ---------------------------------------------------------------- dinero

def test_dinero_por_nombre_de_la_instancia_en_cualquier_lenguaje():
    for linea in ("@Valor INT", "SELECT Total FROM x", "int TarifaId;", "var cobro = 1;", "int cobroMensual;"):
        with Mundo() as w:
            escribir(w.web, {CS_SVC: "class Servicio {\n    %s\n}\n" % linea})
            r = w.analizar(repos=[w.web])
            assert nivel(r, "dinero") == "positiva", (linea, r["senales"]["dinero"])


def test_dinero_por_tipo_donde_hay_biblioteca():
    with Mundo(modulo=False) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("@Id INT,", "@Id INT,\n    @Importe DECIMAL(18,2),")})
        r = w.analizar()
        assert nivel(r, "dinero") == "positiva", r["senales"]["dinero"]
        assert "«DECIMAL»" in detalle(r, "dinero")


def test_dinero_negativo():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT Nombre FROM esq.Estacion WHERE Id = @Id")})
        r = w.analizar()
        assert nivel(r, "dinero") == "negativa", r["senales"]["dinero"]
        assert "sin hallazgos en las líneas agregadas ni quitadas" in detalle(r, "dinero")


def test_dinero_end_to_end_en_lineas_agregadas_con_tope_de_cinco():
    with Mundo() as w:
        nuevos = "".join("    @Valor%d INT,\n" % i for i in range(7))
        escribir(w.db, {SQL_ALFA: ALFA.replace("    @Id INT,\n", "    @Id INT,\n" + nuevos)})
        r = w.analizar()
        assert nivel(r, "dinero") == "positiva" and r["modo"] == "completo"
        assert "«Valor0»" in detalle(r, "dinero") and "(+2 más)" in detalle(r, "dinero"), detalle(r, "dinero")
        assert "«Valor5»" not in detalle(r, "dinero"), "muestra cinco y cuenta el resto"


def test_dinero_en_lineas_quitadas_escala():
    with Mundo() as w:
        commitear(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SET @Total = @Total + @Propina;")})
        publicar(w.db)
        escribir(w.db, {SQL_ALFA: ALFA})
        r = w.analizar()
        assert nivel(r, "dinero") == "positiva", r["senales"]["dinero"]
        assert "Total" in detalle(r, "dinero")


def test_dinero_sin_dinero_ni_agregado_ni_quitado_es_negativa():
    with Mundo() as w:
        commitear(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 7")})
        publicar(w.db)
        escribir(w.db, {SQL_ALFA: ALFA})
        assert nivel(w.analizar(), "dinero") == "negativa"


# ---------------------------------------------------------------- migration o seed

def test_migracion_por_ruta_en_cualquier_lenguaje():
    for ruta in ("db/Seeds/SeedX.sql", "SQL/0.SeedTipo.sql", "Data/Migrations/2026_Add.cs", "src/Migration/uno.sql",
                 "scripts/migracion/dos.sql"):
        assert M.es_migracion_por_ruta(ruta), ruta
    assert not M.es_migracion_por_ruta("src/ventas/Proc_X.sql")


def test_migracion_end_to_end_por_ruta_y_por_ddl():
    with Mundo() as w:
        escribir(w.db, {"src/Seeds/SeedNuevo.sql": "INSERT INTO esq.TipoX VALUES (1)\n"})
        r = w.analizar()
        assert nivel(r, "migracion") == "positiva" and r["modo"] == "completo"
    with Mundo() as w:
        escribir(w.db, {"src/tablas/Turno.sql": "ALTER TABLE esq.Turno ADD Nuevo INT\n"})
        assert nivel(w.analizar(), "migracion") == "positiva"
    with Mundo() as w:
        escribir(w.web, {CS_SVC: "class Servicio { string s = \"ALTER TABLE esq.Turno ADD X INT\"; }\n"})
        assert nivel(w.analizar(repos=[w.web]), "migracion") == "negativa", "el DDL es de la biblioteca T-SQL"


def test_migracion_un_archivo_borrado_no_es_migracion():
    with Mundo() as w:
        commitear(w.db, {"src/Seeds/SeedViejo.sql": "INSERT INTO esq.TipoX VALUES (1)\n"})
        publicar(w.db)
        (w.db / "src/Seeds/SeedViejo.sql").unlink()
        assert nivel(w.analizar(), "migracion") == "negativa"


# ---------------------------------------------------------------- contrato entre capas

def test_contrato_sp_end_to_end_y_negativo():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("@Id INT,", "@Id INT,\n    @Extra INT,")})
        r = w.analizar()
        assert nivel(r, "contrato") == "positiva" and r["modo"] == "completo"
        assert "%s: firma Proc_Alfa: +@Extra int" % SQL_ALFA in detalle(r, "contrato"), detalle(r, "contrato")
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 2")})
        assert nivel(w.analizar(), "contrato") == "negativa"


def test_contrato_sp_borrado_es_contrato_removido():
    with Mundo() as w:
        (w.db / SQL_BETA).unlink()
        r = w.analizar()
        assert nivel(r, "contrato") == "positiva"
        assert "eliminado el SP Proc_Beta" in detalle(r, "contrato")


def test_contrato_archivo_nuevo_no_es_cambio_de_contrato():
    with Mundo() as w:
        escribir(w.db, {"src/ventas/Proc_Nuevo.sql": "CREATE PROCEDURE esq.Proc_Nuevo @A INT\nAS\nSELECT 1\n"})
        assert nivel(w.analizar(), "contrato") == "negativa"


# ---------------------------------------------------------------- capas

def test_multi_capa_escala():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        escribir(w.web, {CS_SVC: "class Servicio { int y; }\n"})
        r = w.analizar(repos=[w.db, w.web])
        assert nivel(r, "capas") == "positiva" and r["modo"] == "completo"
        assert "más de una capa: sql, web" in detalle(r, "capas")


def test_archivo_sin_capa_reconocida_escala():
    with Mundo() as w:
        escribir(w.web, {"appsettings.json": "{}\n"})
        r = w.analizar(repos=[w.web])
        assert nivel(r, "capas") == "positiva" and r["modo"] == "completo"
        assert "appsettings.json" in detalle(r, "capas")


def test_capas_usa_la_clasificacion_del_config():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        archivo = r["repos"][0]["archivos"][0]
        assert archivo == {"ruta": SQL_ALFA, "estado": "M", "capa": "sql", "origen": "repo"}, archivo
        assert "una sola capa: sql" in detalle(r, "capas")


def test_un_repo_fuera_del_config_no_tiene_capa():
    with Mundo() as w:
        otro = repo_en(w.base / "repos" / "otro", {"x.sql": GAMMA})
        escribir(otro, {"x.sql": GAMMA.replace("SELECT 2", "SELECT 3")})
        r = w.analizar(repos=[otro])
        assert r["repos"][0]["archivos"][0]["capa"] is None and nivel(r, "capas") == "positiva"


# ---------------------------------------------------------------- entrada: sin trackear, índice, base

def test_incluye_archivos_sin_trackear_sin_tocar_el_indice():
    with Mundo() as w:
        escribir(w.db, {"src/ventas/Proc_Nuevo.sql": "CREATE PROCEDURE esq.Proc_Nuevo\nAS\nBEGIN\n    " + EFECTO + "\nEND\n"})
        antes = indice(w.db)
        r = w.analizar()
        assert indice(w.db) == antes
        assert [(a["ruta"], a["estado"]) for a in r["repos"][0]["archivos"]] == [("src/ventas/Proc_Nuevo.sql", "?")]
        assert nivel(r, "efecto") == "positiva"


def test_base_por_defecto_es_el_merge_base_con_la_rama_de_origin_head():
    with Mundo() as w:
        base = git(w.db, "rev-parse", "HEAD")
        commitear(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        git(w.db, "checkout", "-q", "--detach", base)
        main2 = commitear(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", EFECTO)})
        publicar(w.db, main2)
        git(w.db, "checkout", "-q", "-")
        r = w.analizar()
        assert r["repos"][0]["base"] == base
        assert [a["ruta"] for a in r["repos"][0]["archivos"]] == [SQL_ALFA]
        assert nivel(r, "efecto") == "negativa"


def test_sin_origin_head_es_error_de_entorno_con_el_arreglo():
    with Mundo() as w:
        git(w.db, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        codigo, _, error = correr(["--repo", str(w.db), "--raiz", str(w.raiz)])
        assert codigo == 2 and "set-head" in error, error


def test_base_explicita_por_repo():
    with Mundo() as w:
        medio = commitear(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 4")})
        r = M.analizar([(str(w.db), medio)], taller=[], raiz=str(w.raiz))
        assert r["repos"][0]["base"] == medio
        assert [a["ruta"] for a in r["repos"][0]["archivos"]] == [SQL_ALFA]


def test_no_hace_fetch():
    fuente = _RUTA.read_text(encoding="utf-8")
    assert not re.search(r"""["']fetch["']""", fuente)
    assert "add -N" not in fuente and '"-N"' not in fuente


def test_lee_utf16_con_bom():
    with Mundo() as w:
        escribir(w.db, {"src/ventas/Proc_U16.sql": ("CREATE PROCEDURE esq.Proc_U16 AS\n" + EFECTO + "\n").encode("utf-16")})
        assert nivel(w.analizar(), "efecto") == "positiva"


def test_un_utf16_trackeado_que_git_ve_binario_se_compara_linea_a_linea():
    with Mundo(modulo=senales(marcadores=())) as w:
        commitear(w.db, {"src/ventas/Proc_U16.sql": "CREATE PROCEDURE esq.Proc_U16 @A INT AS\nSELECT 1\n".encode("utf-16")})
        publicar(w.db)
        escribir(w.db, {"src/ventas/Proc_U16.sql": "CREATE PROCEDURE esq.Proc_U16 @A INT, @Total INT AS\nSELECT 1\n".encode("utf-16")})
        r = w.analizar()
        assert nivel(r, "dinero") == "positiva" and "«Total»" in detalle(r, "dinero"), r["senales"]["dinero"]
        assert "firma Proc_U16: +@Total int" in detalle(r, "contrato"), detalle(r, "contrato")


def test_un_archivo_demasiado_grande_invalida_las_senales_del_texto():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        previo = M.TOPE_BYTES
        M.TOPE_BYTES = 10
        try:
            r = w.analizar()
        finally:
            M.TOPE_BYTES = previo
        for id_ in ("efecto", "dinero", "migracion", "contrato"):
            assert nivel(r, id_) == "invalida", (id_, r["senales"][id_])
            assert "demasiado grande" in detalle(r, id_)


# ---------------------------------------------------------------- taller

def test_taller_se_compara_con_la_contraparte_de_la_linea_base():
    with Mundo() as w:
        ruta = w.taller("esq.Proc_Alfa.sql", ALFA.replace("@Id INT,", "@Id INT,\n    @Extra INT,"))
        r = w.analizar(repos=[], taller=[ruta])
        t = r["taller"][0]
        assert t["capa"] == "sql" and t["origen"] == "taller", t
        assert t["contraparte"] == "%s:%s" % (Path(w.db).as_posix(), SQL_ALFA), t
        assert nivel(r, "contrato") == "positiva" and "@Extra" in detalle(r, "contrato")


def test_taller_con_dinero_solo_en_la_contraparte_lo_cuenta_como_quitado():
    with Mundo() as w:
        commitear(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SET @Total = @Total + @Propina;")})
        publicar(w.db)
        ruta = w.taller("esq.Proc_Alfa.sql", ALFA)
        r = w.analizar(repos=[], taller=[ruta])
        assert nivel(r, "dinero") == "positiva" and "Total" in detalle(r, "dinero"), r["senales"]["dinero"]


def test_taller_lee_las_senales_sobre_todo_su_contenido():
    with Mundo() as w:
        ruta = w.taller("esq.Proc_Alfa.sql", ALFA.replace("SELECT 1", EFECTO))
        assert nivel(w.analizar(repos=[], taller=[ruta]), "efecto") == "positiva"


def test_taller_igual_a_su_contraparte_no_tiene_contrato_ni_dinero():
    with Mundo() as w:
        ruta = w.taller("esq.Proc_Alfa.sql", ALFA)
        r = w.analizar(repos=[], taller=[ruta])
        assert nivel(r, "contrato") == "negativa" and nivel(r, "dinero") == "negativa", r["senales"]
        solo_escala_consumidores(r)


def test_taller_sin_linea_base_configurada_es_nuevo_sin_contraparte():
    with Mundo(linea_base=False) as w:
        ruta = w.taller("esq.Proc_Alfa.sql", ALFA.replace("@Id INT,", "@Id INT,\n    @Extra INT,"))
        r = w.analizar(repos=[], taller=[ruta])
        assert r["taller"][0]["contraparte"] is None and nivel(r, "contrato") == "negativa"


def test_taller_de_notas_es_modo_cero():
    with Mundo() as w:
        nota = w.raiz / "tickets" / "T-1-x" / "notas.md"
        escribir(w.raiz, {"tickets/T-1-x/notas.md": "# nota\n"})
        assert w.analizar(repos=[], taller=[nota])["modo"] == "0"


def test_taller_que_no_existe_es_error_de_entorno():
    with Mundo() as w:
        codigo, _, error = correr(["--taller", str(w.raiz / "no-existe.sql"), "--raiz", str(w.raiz)])
        assert codigo == 2 and "no existe" in error, error


# ---------------------------------------------------------------- salida y CLI

def test_cli_json_y_texto():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        args = ["--repo", str(w.db), "--raiz", str(w.raiz)]
        codigo, salida, error = correr(args + ["--json"])
        assert codigo == 0, error
        datos = json.loads(salida)
        assert datos["modo"] == "completo" and datos["repos"][0]["archivos"][0]["ruta"] == SQL_ALFA
        codigo, salida, error = correr(args)
        assert codigo == 0, error
        assert "modo: COMPLETO" in salida and "[invalida] consumidores" in salida and SQL_ALFA in salida, salida
        assert "no detecta" in salida.lower()
        assert "  - consumidores fuera de los repos declarados" in salida, salida


def test_cli_repo_inexistente_es_error_de_entorno():
    with Mundo() as w:
        codigo, _, error = correr(["--repo", str(w.base / "no-existe"), "--raiz", str(w.raiz)])
        assert codigo == 2 and error


def test_cli_sin_entrada_es_error_de_uso():
    codigo, _, error = correr([])
    assert codigo == 2 and "--repo" in error


def test_cli_sin_instancia_o_con_config_rota_es_error_de_entorno():
    with Mundo() as w:
        vacia = w.base / "vacia"
        vacia.mkdir()
        codigo, _, error = correr(["--repo", str(w.db), "--raiz", str(vacia)])
        assert codigo == 2 and "workspace.config.json" in error, error
        escribir(w.raiz, {"workspace.config.json": "{roto"})
        codigo, _, error = correr(["--repo", str(w.db), "--raiz", str(w.raiz)])
        assert codigo == 2 and "workspace.config.json" in error, error


def test_cli_como_proceso_utf8_y_raiz_de_la_sesion():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        env = {k: v for k, v in _entorno_sin_git().items() if k != "PYTHONPATH"}
        env.update(PYTHONIOENCODING="cp1252", CLAUDE_PROJECT_DIR=str(w.raiz))
        r = subprocess.run([sys.executable, str(_RUTA), "--repo", str(w.db), "--json"], capture_output=True, env=env,
                           cwd=str(w.base))
        assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
        datos = json.loads(r.stdout.decode("utf-8"))
        assert datos["motivos"] == ["señal consumidores: invalida"] and datos["raiz"] == str(w.raiz)


PRUEBAS = [(n[len("test_"):], f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]


def main():
    fallas = 0
    for nombre, prueba in PRUEBAS:
        try:
            prueba()
            print("ok    %s" % nombre)
        except Exception as exc:
            fallas += 1
            print("FALLA %s: %s: %s" % (nombre, type(exc).__name__, exc))
    for plantilla in _PLANTILLA:
        _borrar(plantilla)
    if SOBRANTES:
        print("TEMPORALES SIN BORRAR: %s" % ", ".join(SOBRANTES))
        fallas += 1
    print("%d/%d" % (len(PRUEBAS) - fallas, len(PRUEBAS)))
    return 1 if fallas else 0


if __name__ == "__main__":
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
