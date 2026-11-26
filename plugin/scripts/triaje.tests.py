import atexit
import codecs
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
CS_CALLER = "Data/AlfaCaller.cs"
CALLER = "class AlfaCaller { string sp = \"esq.Proc_Alfa\"; }\n"

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


AISLAMIENTO_GIT = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in AISLAMIENTO_GIT}


@contextlib.contextmanager
def git_aislado(config=""):
    carpeta = Path(tempfile.mkdtemp(prefix="triaje-git-"))
    (carpeta / "global").write_text(config, encoding="utf-8")
    previo = {k: os.environ.get(k) for k in AISLAMIENTO_GIT}
    os.environ.update(GIT_CONFIG_GLOBAL=str(carpeta / "global"), GIT_CONFIG_SYSTEM=str(carpeta / "sistema"), GIT_CONFIG_NOSYSTEM="1")
    try:
        yield
    finally:
        for clave, valor in previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        _borrar(carpeta)


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
    def __init__(self, modulo=None, linea_base=True, consumidor_extra=False):
        self.modulo = senales() if modulo is None else modulo
        self.linea_base = linea_base
        self.consumidor_extra = consumidor_extra

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="triaje-test-"))
        self.raiz = self.base / "inst"
        escribir(self.raiz, {"docs/sistemas.md": DOC_SISTEMAS})
        if self.modulo is not False:
            escribir(self.raiz, {".claude/reglas/senales.py": self.modulo})
        self.db = copiar_repo("db", self.base / "repos" / "db")
        self.web = copiar_repo("web", self.base / "repos" / "web")
        if self.consumidor_extra:
            commitear(self.web, {CS_CALLER: CALLER})
            publicar(self.web)
        sql = {"extensions": [".sql"], "repos": ["db"], "workshop": ["tickets/**/T-[0-9]*/SQL/esq.*.sql"]}
        if self.linea_base:
            sql["workshop_baseline"] = {"repo": "db", "under": "src", "strip_prefix": "esq."}
        config = {"schema_version": 1, "repos": {"db": {}, "web": {}},
                  "layers": {"sql": sql, "web": {"extensions": [".cs"], "repos": ["web"]}}}
        escribir(self.raiz, {"workspace.config.json": json.dumps(config),
                             "workspace.local.json": json.dumps({"repos": {"db": {"path": str(self.db)}, "web": {"path": str(self.web)}}})})
        return self

    def analizar(self, repos=None, taller=(), clones=None):
        repos = [(str(r), None) for r in (repos if repos is not None else [self.db])]
        return M.analizar(repos, taller=[str(t) for t in taller], raiz=str(self.raiz),
                          clones=None if clones is None else [str(c) for c in clones])

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


def test_rapido_solo_con_todas_las_senales_en_negativo():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        assert r["modo"] == "rapido", (r["motivos"], r["senales"])
        for id_ in M.SENALES:
            assert nivel(r, id_) == "negativa", (id_, r["senales"][id_])
        assert r["motivos"] == ["todas las señales en negativo y el instrumento verificado"]
        assert r["no_detectable"], "tiene que declarar lo que no detecta"
        assert re.fullmatch(r"[0-9a-f]{40}", r["origin_head"][str(w.db)] or ""), r["origin_head"]
        assert "Proc_Alfa: ≥ 1, %s (Proc_Beta.sql)" % M.COTA in detalle(r, "consumidores"), detalle(r, "consumidores")


def test_rapido_exige_el_instrumento_verificado_las_senales_solo_escalan():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar(clones=[w.web])
        assert r["modo"] == "completo", "sin la definición no hay conteo válido: tiene que escalar"
        assert nivel(r, "consumidores") == "invalida" and r["motivos"] == ["señal consumidores: invalida"]
        assert "no encontré la definición" in detalle(r, "consumidores"), detalle(r, "consumidores")


# ---------------------------------------------------------------- recurso compartido

def test_consumidores_dos_o_mas_escala_con_cota_inferior():
    with Mundo(consumidor_extra=True) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        assert nivel(r, "consumidores") == "positiva" and r["modo"] == "completo"
        assert "Proc_Alfa: ≥ 2, %s (AlfaCaller.cs, Proc_Beta.sql)" % M.COTA in detalle(r, "consumidores"), detalle(r, "consumidores")


def test_consumidores_cuentan_entre_los_repos_y_excluyen_la_definicion():
    with Mundo(consumidor_extra=True) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        d = detalle(w.analizar(), "consumidores")
        assert "Proc_Beta.sql" in d and "AlfaCaller.cs" in d and "Proc_Alfa.sql" not in d, d


def test_consumidores_un_solo_consumidor_es_negativa():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        assert nivel(r, "consumidores") == "negativa" and "≥ 1, " in detalle(r, "consumidores")


def test_consumidores_se_cuentan_en_la_rama_de_origin_head_y_no_en_el_working_tree():
    with Mundo() as w:
        commitear(w.web, {CS_CALLER: CALLER})
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        d = detalle(w.analizar(), "consumidores")
        assert "≥ 1, " in d and "AlfaCaller.cs" not in d, "un commit local sin publicar no cuenta: %s" % d


def test_consumidores_un_objeto_invalido_no_lo_pisa_otro_positivo():
    with Mundo(consumidor_extra=True) as w:
        aaa = "src/ventas/Proc_Aaa.sql"
        base = commitear(w.db, {aaa: "CREATE PROCEDURE esq.Proc_Aaa AS SELECT 1\n"})
        escribir(w.db, {aaa: "CREATE PROCEDURE esq.Proc_Aaa AS SELECT 2\n", SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = M.analizar([(str(w.db), base)], taller=[], raiz=str(w.raiz))
        d = detalle(r, "consumidores")
        assert "Proc_Aaa: no encontré la definición" in d and "Proc_Alfa: ≥ 2, " in d, d
        assert nivel(r, "consumidores") == "invalida", "el positivo que viene después no borra el inválido"


def test_consumidores_sin_distinguir_mayusculas_y_por_palabra_entera():
    with Mundo() as w:
        commitear(w.web, {CS_CALLER: CALLER.replace("Proc_Alfa", "PROC_ALFA"), "Data/Otro.cs": "class Otro { string s = \"esq.Proc_AlfaB\"; }\n"})
        publicar(w.web)
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        d = detalle(w.analizar(), "consumidores")
        assert "≥ 2, " in d and "AlfaCaller.cs" in d and "Otro.cs" not in d, d


def test_consumidores_no_cuentan_archivos_binarios():
    with Mundo() as w:
        commitear(w.web, {"Data/blob.bin": b"\x00\x01esq.Proc_Alfa\x00\x02"})
        publicar(w.web)
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        d = detalle(w.analizar(), "consumidores")
        assert "≥ 1, " in d and "blob.bin" not in d, d


def test_consumidores_control_positivo_definicion_no_encontrada_invalida_el_conteo():
    with Mundo(consumidor_extra=True) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar(clones=[w.web])
        assert nivel(r, "consumidores") == "invalida" and r["modo"] == "completo"


def test_consumidores_objeto_nuevo_no_tiene_consumidores_previos():
    with Mundo() as w:
        escribir(w.db, {"src/ventas/Proc_Nuevo.sql": "CREATE PROCEDURE esq.Proc_Nuevo\nAS\nBEGIN\n    SELECT 1\nEND\n"})
        r = w.analizar()
        assert nivel(r, "consumidores") == "negativa" and r["modo"] == "rapido", r["senales"]["consumidores"]
        assert "Proc_Nuevo: objeto nuevo, sin consumidores previos" in detalle(r, "consumidores")


def test_consumidores_repo_sin_origin_head_invalida_y_lo_informa():
    with Mundo() as w:
        git(w.web, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        assert nivel(r, "consumidores") == "invalida", r["senales"]["consumidores"]
        assert "repo(s) sin origin/HEAD o inexistentes" in detalle(r, "consumidores") and str(w.web) in detalle(r, "consumidores")
        assert r["origin_head"][str(w.web)] is None and r["origin_head"][str(w.db)]
        assert "si no tiene remoto, pasa su base con --repo RUTA#BASE" in detalle(r, "consumidores")


def _sin_remoto(repo):
    git(repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")


def test_consumidores_repo_sin_remoto_cuenta_en_su_base_explicita():
    with Mundo() as w:
        _sin_remoto(w.db)
        base = git(w.db, "rev-parse", "HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = M.analizar([(str(w.db), base)], taller=[], raiz=str(w.raiz))
        d = detalle(r, "consumidores")
        assert nivel(r, "consumidores") == "negativa" and r["modo"] == "rapido", d
        assert "Proc_Alfa: ≥ 1, " in d and "%s: sin remoto, conté en la base %s" % (w.db, base[:10]) in d, d
        assert r["origin_head"][str(w.db)] is None


def test_consumidores_en_la_base_explicita_ven_sus_commits_y_no_el_working_tree():
    with Mundo() as w:
        _sin_remoto(w.db)
        base = commitear(w.db, {"src/ventas/Proc_Delta.sql": BETA.replace("Proc_Beta", "Proc_Delta")})
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3"),
                        "src/ventas/Proc_Eps.sql": BETA.replace("Proc_Beta", "Proc_Eps")})
        r = M.analizar([(str(w.db), base)], taller=[], raiz=str(w.raiz))
        d = detalle(r, "consumidores")
        assert nivel(r, "consumidores") == "positiva" and "Proc_Delta.sql" in d and "Proc_Eps.sql" not in d, d


def test_consumidores_repo_con_remoto_sin_origin_head_sigue_invalida_aunque_tenga_base():
    with Mundo() as w:
        _sin_remoto(w.db)
        git(w.db, "remote", "add", "origin", str(w.web))
        base = git(w.db, "rev-parse", "HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = M.analizar([(str(w.db), base)], taller=[], raiz=str(w.raiz))
        d = detalle(r, "consumidores")
        assert nivel(r, "consumidores") == "invalida" and "repo(s) sin origin/HEAD o inexistentes" in d and "conté en la base" not in d, d


def test_consumidores_origin_head_hacia_una_rama_que_no_existe_invalida():
    with Mundo() as w:
        git(w.web, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/no-existe")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        assert nivel(r, "consumidores") == "invalida" and r["origin_head"][str(w.web)] is None


def test_consumidores_un_lenguaje_sin_biblioteca_invalida_el_conteo():
    with Mundo() as w:
        escribir(w.web, {CS_SVC: "class Servicio { int y; }\n"})
        r = w.analizar(repos=[w.web])
        assert nivel(r, "consumidores") == "invalida" and r["modo"] == "completo"
        assert "Data/Servicio.cs: sin biblioteca de señales para .cs, el conteo no vale" in detalle(r, "consumidores"), detalle(r, "consumidores")


def test_consumidores_sin_objetos_que_contar_es_negativa():
    with Mundo() as w:
        escribir(w.db, {"src/datos/uno.sql": "SELECT 1\n"})
        r = w.analizar()
        assert nivel(r, "consumidores") == "negativa"
        assert "sin objetos con consumidores que contar" in detalle(r, "consumidores")


def test_consumidores_con_mas_de_veinte_objetos_el_conteo_seria_parcial():
    with Mundo() as w:
        muchos = "".join("CREATE PROCEDURE esq.Proc_N%d AS SELECT 1\nGO\n" % i for i in range(21))
        escribir(w.db, {"src/ventas/Muchos.sql": muchos})
        r = w.analizar()
        assert nivel(r, "consumidores") == "invalida", r["senales"]["consumidores"]
        assert "21 objetos (más de 20)" in detalle(r, "consumidores")


def test_consumidores_usan_la_cota_de_la_instancia():
    with Mundo(modulo=senales(extra="COTA = 'sin mirar el sistema viejo'\n")) as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        assert "Proc_Alfa: ≥ 1, sin mirar el sistema viejo (Proc_Beta.sql)" in detalle(w.analizar(), "consumidores")


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
        assert r["modo"] == "rapido", r["motivos"]


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
        assert r["modo"] == "rapido", r["motivos"]


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


def aviso_de_cobertura(detalle_, cuenta, sin_capa=()):
    import config_loader
    return {"id": "capas-cobertura", "detalle": detalle_, "ayuda": config_loader.ayuda_de_cobertura(cuenta, sin_capa)}


def test_sin_capa_tiene_clave_propia_cuando_es_el_unico_motivo_de_capas():
    with Mundo() as w:
        escribir(w.web, {"appsettings.json": "{}\n", "Makefile": "x\n", "Data/README.md": "nota\n"})
        r = w.analizar(repos=[w.web])
        assert r["modo"] == "completo" and r["motivos"] == ["señal consumidores: invalida", "señal capas: positiva"], r["motivos"]
        assert r["sin_capa"] == {"archivos": ["Makefile", "appsettings.json"], "unico_motivo_de_capas": True,
                                 "aviso": aviso_de_cobertura("extensiones sin capa en el cambio: (sin extensión) (1), .json (1)",
                                                           {"(sin extensión)": 1, ".json": 1})}, r["sin_capa"]


def test_sin_capa_junto_a_mas_de_una_capa_no_es_el_unico_motivo_y_sin_ella_la_clave_es_nula():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        escribir(w.web, {CS_SVC: "class Servicio { int y; }\n"})
        solo_capas = w.analizar(repos=[w.db, w.web])
        assert nivel(solo_capas, "capas") == "positiva" and solo_capas["sin_capa"] is None, solo_capas["sin_capa"]
        escribir(w.web, {"appsettings.json": "{}\n"})
        r = w.analizar(repos=[w.db, w.web])
        assert r["motivos"] == ["señal consumidores: invalida", "señal capas: positiva"], r["motivos"]
        assert r["sin_capa"] == {"archivos": ["appsettings.json"], "unico_motivo_de_capas": False,
                                 "aviso": aviso_de_cobertura("extensiones sin capa en el cambio: .json (1)", {".json": 1})}, r["sin_capa"]
    with Mundo() as w:
        assert w.analizar()["sin_capa"] is None, "sin cambios"
        escribir(w.db, {"README.md": "# db\nnota\n"})
        assert w.analizar()["sin_capa"] is None, "modo 0"
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        r = w.analizar()
        assert r["modo"] == "rapido" and r["sin_capa"] is None, r["sin_capa"]


def test_sin_capa_cuenta_los_archivos_del_taller():
    with Mundo() as w:
        nota = w.raiz / "tickets" / "T-1-x" / "SQL" / "carga.csv"
        escribir(w.raiz, {"tickets/T-1-x/SQL/carga.csv": "a;b\n"})
        r = w.analizar(repos=[], taller=[nota])
        assert r["sin_capa"]["archivos"] == ["carga.csv"] and r["sin_capa"]["unico_motivo_de_capas"] is True, r["sin_capa"]
        assert r["sin_capa"]["aviso"]["detalle"] == "extensiones sin capa en el cambio: .csv (1)", r["sin_capa"]


def test_el_aviso_de_cobertura_sale_en_el_texto_despues_de_los_motivos_y_en_el_json():
    import config_loader
    with Mundo() as w:
        escribir(w.web, {"appsettings.json": "{}\n"})
        args = ["--repo", str(w.web), "--raiz", str(w.raiz)]
        codigo, salida, error = correr(args)
        assert codigo == 0 and error == "", error
        assert salida.splitlines()[:6] == [
            "triaje — modo: COMPLETO",
            "  señal consumidores: invalida",
            "  señal capas: positiva",
            "aviso capas-cobertura: extensiones sin capa en el cambio: .json (1)",
            "  cómo: " + config_loader.ayuda_de_cobertura({".json": 1}),
            "instancia: %s" % w.raiz,
        ], salida
        assert salida.count("capas-cobertura") == 1, salida
        codigo, salida, error = correr(args + ["--json"])
        assert codigo == 0 and error == "", error
        datos = json.loads(salida)
        assert datos["sin_capa"]["aviso"] == aviso_de_cobertura("extensiones sin capa en el cambio: .json (1)", {".json": 1}), datos["sin_capa"]
        assert datos["modo"] == "completo" and datos["motivos"] == ["señal consumidores: invalida", "señal capas: positiva"]


def test_sin_archivos_sin_capa_el_texto_y_el_json_salen_como_antes():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        args = ["--repo", str(w.db), "--raiz", str(w.raiz)]
        codigo, salida, error = correr(args)
        assert codigo == 0 and error == "", error
        lineas_ = salida.splitlines()
        assert lineas_[:3] == ["triaje — modo: RAPIDO", "  todas las señales en negativo y el instrumento verificado",
                               "instancia: %s" % w.raiz], lineas_[:3]
        assert "capas-cobertura" not in salida and "cómo:" not in salida, salida
        codigo, salida, error = correr(args + ["--json"])
        datos = json.loads(salida)
        assert list(datos) == ["raiz", "origin_head", "repos", "taller", "senales", "modo", "motivos", "sin_capa", "no_detectable",
                               "chequeos"], list(datos)
        assert datos["sin_capa"] is None


def con_sin_capa(w, valor):
    ruta = w.raiz / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["sin_capa"] = valor
    ruta.write_text(json.dumps(config), encoding="utf-8")


def test_sin_capa_de_la_config_saca_sus_extensiones_del_aviso_y_salen_con_su_nota_sin_cambiar_el_modo():
    with Mundo() as w:
        escribir(w.web, {"res/logo.png": "x\n", "res/icono.PNG": "x\n"})
        sin_la_clave = w.analizar(repos=[w.web])
        assert sin_la_clave["sin_capa"]["aviso"]["detalle"] == "extensiones sin capa en el cambio: .png (2)", sin_la_clave["sin_capa"]
        con_sin_capa(w, [".png"])
        r = w.analizar(repos=[w.web])
        assert (r["modo"], r["motivos"], r["senales"], r["repos"]) == (
            sin_la_clave["modo"], sin_la_clave["motivos"], sin_la_clave["senales"], sin_la_clave["repos"]), r
        assert r["sin_capa"] == {"archivos": ["res/icono.PNG", "res/logo.png"], "unico_motivo_de_capas": True, "aviso": None}, r["sin_capa"]
        codigo, salida, error = correr(["--repo", str(w.web), "--raiz", str(w.raiz)])
        assert codigo == 0 and error == "", error
        assert salida.splitlines()[:5] == [
            "triaje — modo: COMPLETO",
            "  señal consumidores: invalida",
            "  señal capas: positiva",
            "capas-cobertura: sin capa y esperados en el cambio: .png (2); un cambio en ellos lleva /odd-ws:revisar a modo completo",
            "instancia: %s" % w.raiz,
        ], salida
        assert "aviso capas-cobertura" not in salida and "cómo:" not in salida, salida
        escribir(w.web, {"scripts/x.mjs": "x\n"})
        r = w.analizar(repos=[w.web])
        assert r["sin_capa"]["archivos"] == ["res/icono.PNG", "res/logo.png", "scripts/x.mjs"], r["sin_capa"]
        assert r["sin_capa"]["aviso"] == aviso_de_cobertura("extensiones sin capa en el cambio: .mjs (1)", {".mjs": 1}, [".png"]), r["sin_capa"]
        assert r["sin_capa"]["aviso"]["ayuda"].endswith('"sin_capa": [".png", ".mjs"]'), r["sin_capa"]["aviso"]["ayuda"]


def test_sin_capa_invalido_en_la_config_sale_con_dos_sin_triar():
    with Mundo() as w:
        escribir(w.web, {"res/logo.png": "x\n"})
        con_sin_capa(w, ["png"])
        codigo, salida, error = correr(["--repo", str(w.web), "--raiz", str(w.raiz)])
        assert (codigo, salida) == (2, ""), (codigo, salida)
        assert "está rota: sin_capa debe ser una lista de extensiones con punto" in error, error


# ---------------------------------------------------------------- entrada: sin trackear, índice, base

def test_incluye_archivos_sin_trackear_sin_tocar_el_indice():
    with Mundo() as w:
        escribir(w.db, {"src/ventas/Proc_Nuevo.sql": "CREATE PROCEDURE esq.Proc_Nuevo\nAS\nBEGIN\n    " + EFECTO + "\nEND\n"})
        antes = indice(w.db)
        r = w.analizar()
        assert indice(w.db) == antes
        assert [(a["ruta"], a["estado"]) for a in r["repos"][0]["archivos"]] == [("src/ventas/Proc_Nuevo.sql", "?")]
        assert nivel(r, "efecto") == "positiva"


def test_los_generados_sin_trackear_quedan_fuera_de_la_unidad_y_se_nombran_aparte():
    generados = {"tools/__pycache__/util.cpython-312.pyc": b"\x00\x01", "tools/viejo.PYC": b"\x00", "tools/opt.pyo": b"\x00"}
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        sin = w.analizar()
        assert "generados" not in sin["repos"][0], "sin generados, la salida es la de siempre"
        escribir(w.db, generados)
        con = w.analizar()
        repo = con["repos"][0]
        assert [a["ruta"] for a in repo["archivos"]] == [SQL_ALFA], repo
        assert repo["generados"] == sorted(generados), repo
        assert con["modo"] == sin["modo"] and con["senales"] == sin["senales"], "los generados no mueven el modo ni las señales"
        codigo, salida, error = correr(["--repo", str(w.db), "--raiz", str(w.raiz)])
        assert codigo == 0, error
        assert "fuera de la unidad: 3 archivo(s) generado(s) sin trackear: " + ", ".join(sorted(generados)) in salida, salida
        escribir(w.db, {"tools/__pycache__/nota.md": "no es bytecode\n"})
        repo = w.analizar()["repos"][0]
        assert "tools/__pycache__/nota.md" in repo["generados"], "todo lo que está bajo __pycache__ es generado"


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
        for id_ in ("efecto", "dinero", "migracion", "contrato", "consumidores"):
            assert nivel(r, id_) == "invalida", (id_, r["senales"][id_])
            assert "demasiado grande" in detalle(r, id_), (id_, detalle(r, id_))


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
        assert nivel(r, "consumidores") == "negativa" and r["modo"] == "rapido", r["senales"]["consumidores"]


def test_taller_sin_contraparte_no_puede_validar_la_definicion():
    with Mundo() as w:
        ruta = w.taller("esq.Proc_Inventada.sql", "CREATE PROCEDURE esq.Proc_Inventada\nAS\nBEGIN\n    SELECT 1\nEND\n")
        r = w.analizar(repos=[], taller=[ruta])
        assert nivel(r, "consumidores") == "invalida" and r["modo"] == "completo", r["senales"]["consumidores"]


def test_taller_con_contraparte_cuenta_en_los_repos_sin_la_definicion():
    with Mundo() as w:
        ruta = w.taller("esq.Proc_Alfa.sql", ALFA)
        d = detalle(w.analizar(repos=[], taller=[ruta]), "consumidores")
        assert "Proc_Alfa: ≥ 1, " in d and "Proc_Beta.sql" in d and "Proc_Alfa.sql" not in d, d


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
        hash_db = git(w.db, "rev-parse", "origin/main")
        assert datos["modo"] == "rapido" and datos["repos"][0]["archivos"][0]["ruta"] == SQL_ALFA
        assert datos["origin_head"][str(w.db)] == hash_db, datos["origin_head"]
        codigo, salida, error = correr(args)
        assert codigo == 0, error
        assert "modo: RAPIDO" in salida and "[negativa] consumidores" in salida and SQL_ALFA in salida, salida
        assert hash_db in salida and M.COTA in salida, salida
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
        assert datos["modo"] == "rapido" and datos["raiz"] == str(w.raiz), datos["motivos"]
        assert "≥ 1, " in " ".join(datos["senales"]["consumidores"]["detalle"])


def test_cli_clon_cambia_los_repos_donde_se_cuenta():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        codigo, salida, error = correr(["--repo", str(w.db), "--raiz", str(w.raiz), "--clon", str(w.web), "--json"])
        assert codigo == 0, error
        datos = json.loads(salida)
        assert datos["senales"]["consumidores"]["nivel"] == "invalida" and list(datos["origin_head"]) == [str(w.web)]


# ---------------------------------------------------------------- la base sellada de un ticket (I20)

TICKET = "tickets/T-1-x"
SQL_NUEVO = "src/ventas/Proc_Nuevo.sql"
NUEVO = GAMMA.replace("Proc_Gamma", "Proc_Nuevo")


def recibo_main(argv):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(salida):
        codigo = M.recibo.main(argv)
    assert codigo == 0, (argv, salida.getvalue())


def sellar(w, repo, rutas, fecha="2026-11-17", sellar_en=None, base=None):
    ticket = w.raiz / TICKET
    ticket.mkdir(parents=True, exist_ok=True)
    argv = ["--write", "--ticket", str(ticket), "--repo", "%s#%s" % (repo, base) if base else str(repo), "--modo", "rapido",
            "--fecha", fecha, "--estado", "limpio"]
    for rel in rutas:
        argv += ["--archivo", str(repo / rel)]
    recibo_main(argv)
    head = commitear(repo, {})
    recibo_main(["--sellar", str(sellar_en or ticket)])
    return ticket, head


def con_ticket(w, repos, ticket):
    return M.analizar([(str(r), b) for r, b in repos], taller=[], raiz=str(w.raiz), ticket=str(ticket))


def rutas(repo):
    return [a["ruta"] for a in repo["archivos"]]


def test_ticket_con_una_unidad_sellada_triaja_solo_la_unidad_nueva():
    with Mundo() as w:
        merge_base = git(w.db, "rev-parse", "HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3"), SQL_NUEVO: NUEVO})
        ticket, sello = sellar(w, w.db, [SQL_ALFA, SQL_NUEVO])
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        sin = w.analizar()
        assert sin["repos"][0]["base"] == merge_base and rutas(sin["repos"][0]) == [SQL_ALFA, SQL_GAMMA, SQL_NUEVO]
        assert "base_origen" not in sin["repos"][0] and "base_recibo" not in sin["repos"][0], sin["repos"][0]
        r = con_ticket(w, [(w.db, None)], ticket)
        repo = r["repos"][0]
        assert repo["base"] == sello and rutas(repo) == [SQL_GAMMA], repo
        assert repo["base_origen"] == "sellada" and repo["base_recibo"] == "revision/2026-11-17-rapido", repo
        assert list(repo) == ["ruta", "base", "base_origen", "base_recibo", "archivos", "sha256", "sha256_por_archivo"], list(repo)
        args = ["--repo", str(w.db), "--raiz", str(w.raiz), "--ticket", str(ticket)]
        codigo, salida, error = correr(args)
        assert codigo == 0 and error == "", error
        assert "repo %s (base %s, sellada en revision/2026-11-17-rapido): 1 archivo(s)" % (repo["ruta"], sello[:10]) in salida, salida
        codigo, salida, error = correr(args + ["--json"])
        assert codigo == 0, error
        assert json.loads(salida)["repos"][0] == repo
        codigo, salida, _ = correr(["--repo", str(w.db), "--raiz", str(w.raiz)])
        assert "repo %s (base %s): 3 archivo(s)" % (repo["ruta"], merge_base[:10]) in salida, salida


def test_ticket_la_base_explicita_gana_al_sello():
    with Mundo() as w:
        merge_base = git(w.db, "rev-parse", "HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        ticket, _ = sellar(w, w.db, [SQL_ALFA])
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        repo = con_ticket(w, [(w.db, merge_base)], ticket)["repos"][0]
        assert repo["base"] == merge_base and repo["base_origen"] == "explicita" and repo["base_recibo"] is None, repo
        assert rutas(repo) == [SQL_ALFA, SQL_GAMMA]
        codigo, salida, _ = correr(["--repo", "%s#%s" % (w.db, merge_base), "--raiz", str(w.raiz), "--ticket", str(ticket)])
        assert codigo == 0 and "(base %s, explícita): 2 archivo(s)" % merge_base[:10] in salida, salida


def test_ticket_un_sello_que_no_es_ancestro_de_head_o_que_no_existe_usa_el_merge_base():
    with Mundo() as w:
        merge_base = git(w.db, "rev-parse", "HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        ticket, sello = sellar(w, w.db, [SQL_ALFA])
        git(w.db, "checkout", "-q", "-b", "otra", merge_base)
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
        assert repo["base"] == merge_base and repo["base_origen"] == "merge-base" and repo["base_recibo"] is None, repo
        assert rutas(repo) == [SQL_GAMMA]
        codigo, salida, _ = correr(["--repo", str(w.db), "--raiz", str(w.raiz), "--ticket", str(ticket)])
        assert "(base %s, merge-base con origin/HEAD): 1 archivo(s)" % merge_base[:10] in salida, salida
        git(w.db, "checkout", "-q", "-")
        archivo = ticket / "revision" / "2026-11-17-rapido" / "recibo.json"
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        for falso in ("f" * 40, "HEAD", "--output=x", sello[:10], 7):
            datos["repos"][0]["sellado"] = falso
            archivo.write_text(json.dumps(datos), encoding="utf-8")
            repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
            assert repo["base"] == merge_base and repo["base_origen"] == "merge-base", (falso, repo)


def test_ticket_un_sello_ya_integrado_en_origin_head_usa_el_merge_base():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        ticket, _ = sellar(w, w.db, [SQL_ALFA])
        integrado = commitear(w.db, {SQL_NUEVO: NUEVO})
        publicar(w.db, integrado)
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
        assert repo["base"] == integrado and repo["base_origen"] == "merge-base" and rutas(repo) == [SQL_GAMMA], repo


def test_ticket_con_la_rama_de_origin_head_mezclada_despues_del_sello_usa_el_merge_base():
    with Mundo() as w:
        merge_base = git(w.db, "rev-parse", "HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        ticket, _ = sellar(w, w.db, [SQL_ALFA])
        git(w.db, "checkout", "-q", "--detach", merge_base)
        principal = commitear(w.db, {SQL_NUEVO: NUEVO})
        publicar(w.db, principal)
        git(w.db, "checkout", "-q", "-")
        git(w.db, "merge", "-q", "--no-edit", "origin/main")
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
        assert repo["base"] == principal and repo["base_origen"] == "merge-base", repo
        assert rutas(repo) == [SQL_ALFA, SQL_GAMMA], "lo que trajo origin/HEAD no entra al triaje: %s" % rutas(repo)


def test_ticket_con_varios_sellos_gana_el_commit_mas_nuevo_y_no_la_carpeta():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        ticket, primero = sellar(w, w.db, [SQL_ALFA], fecha="2026-11-18")
        escribir(w.db, {SQL_NUEVO: NUEVO})
        _, segundo = sellar(w, w.db, [SQL_NUEVO], fecha="2026-11-17", sellar_en=w.raiz / TICKET / "revision" / "2026-11-17-rapido",
                            base=primero)
        recibos = {p.parent.name: json.loads(p.read_text(encoding="utf-8"))["repos"][0]["sellado"]
                   for p in (w.raiz / TICKET / "revision").glob("*/recibo.json")}
        assert recibos == {"2026-11-18-rapido": primero, "2026-11-17-rapido": segundo}, recibos
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
        assert repo["base"] == segundo and repo["base_recibo"] == "revision/2026-11-17-rapido" and rutas(repo) == [SQL_GAMMA], repo


def test_ticket_el_sello_de_otro_repo_no_cuenta():
    with Mundo() as w:
        merge_base = git(w.db, "rev-parse", "HEAD")
        escribir(w.web, {CS_SVC: "class Servicio { int y; }\n"})
        ticket, sello = sellar(w, w.web, [CS_SVC])
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        db, web = con_ticket(w, [(w.db, None), (w.web, None)], ticket)["repos"]
        assert db["base"] == merge_base and db["base_origen"] == "merge-base" and rutas(db) == [SQL_ALFA], db
        assert web["base"] == sello and web["base_origen"] == "sellada" and rutas(web) == [], web


def test_ticket_sin_recibos_sellados_usa_el_merge_base_y_lo_dice():
    with Mundo() as w:
        merge_base = git(w.db, "rev-parse", "HEAD")
        ticket = w.raiz / TICKET
        ticket.mkdir(parents=True)
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
        assert repo["base"] == merge_base and repo["base_origen"] == "merge-base" and repo["base_recibo"] is None, repo
        recibo_main(["--write", "--ticket", str(ticket), "--repo", str(w.db), "--archivo", str(w.db / SQL_ALFA),
                     "--modo", "rapido", "--fecha", "2026-11-17"])
        commitear(w.db, {})
        escribir(w.raiz, {TICKET + "/revision/2026-11-18-rapido/recibo.json": "{roto"})
        repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
        assert repo["base"] == merge_base and repo["base_origen"] == "merge-base", "un recibo sin sellar o roto no mueve la base"


def test_ticket_con_sello_no_necesita_origin_head():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        ticket, sello = sellar(w, w.db, [SQL_ALFA])
        git(w.db, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        repo = con_ticket(w, [(w.db, None)], ticket)["repos"][0]
        assert repo["base"] == sello and repo["base_origen"] == "sellada" and rutas(repo) == [SQL_GAMMA], repo
        codigo, _, error = correr(["--repo", str(w.db), "--raiz", str(w.raiz)])
        assert codigo == 2 and "set-head" in error, "sin --ticket, sigue pidiendo origin/HEAD"


def test_ticket_que_no_existe_es_error_de_uso():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        codigo, salida, error = correr(["--repo", str(w.db), "--raiz", str(w.raiz), "--ticket", str(w.raiz / "tickets" / "no-existe")])
        assert codigo == 2 and salida == "" and "la carpeta del ticket no existe" in error and "no-existe" in error, (codigo, salida, error)


def test_ticket_triaje_y_recibo_eligen_la_base_con_la_misma_funcion():
    with Mundo() as w:
        merge_base = git(w.db, "rev-parse", "HEAD")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        ticket, sello = sellar(w, w.db, [SQL_ALFA])
        escribir(w.db, {SQL_GAMMA: GAMMA.replace("SELECT 2", "SELECT 4")})
        assert not any(hasattr(M, f) for f in ("elegir_base", "sello_mas_nuevo", "sellos_del_ticket", "_es_ancestro")), "viven en recibo"
        codigo, salida, error = correr(["--repo", str(w.db), "--raiz", str(w.raiz), "--ticket", str(ticket), "--json"])
        assert codigo == 0 and error == "", error
        repo = json.loads(salida)["repos"][0]
        assert (repo["base"], repo["base_origen"], repo["base_recibo"]) == (sello, "sellada", "revision/2026-11-17-rapido"), repo
        assert M.recibo.elegir_base(repo["ruta"], None, str(ticket)) == (sello, "sellada", "revision/2026-11-17-rapido")
        assert M.recibo.elegir_base(repo["ruta"], merge_base, str(ticket))[:2] == (merge_base, "explicita")
        recibo_main(["--write", "--ticket", str(ticket), "--repo", str(w.db), "--archivo", str(w.db / SQL_GAMMA), "--modo", "rapido",
                     "--fecha", "2026-11-18"])
        escrito = json.loads((ticket / "revision" / "2026-11-18-rapido" / "recibo.json").read_text(encoding="utf-8"))
        assert escrito["repos"][0]["base"] == repo["base"], "recibo.py --write --ticket parte de la misma base que el triaje"


# ---------------------------------------------------------------- la bajada de un escalón en recibo.py (I34)

def bajar_con_el_triaje_real(w, ticket, fecha, repos, archivos):
    argv = ["--raiz", str(w.raiz), "--ticket", str(ticket), "--json"]
    for repo in repos:
        argv += ["--repo", str(repo)]
    codigo, salida, error = correr(argv)
    assert codigo == 0 and json.loads(salida)["modo"] == "completo", (codigo, error)
    entrada = ticket / "revision" / ("%s-rapido" % fecha) / "entrada"
    entrada.mkdir(parents=True)
    (entrada / "triaje.json").write_text(salida, encoding="utf-8")
    argv = ["--write", "--ticket", str(ticket), "--modo", "rapido", "--fecha", fecha, "--bajada", "un json sin capa", "--va-a-lider", "no"]
    for repo in repos:
        argv += ["--repo", str(repo)]
    for archivo in archivos:
        argv += ["--archivo", str(archivo)]
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            codigo = M.recibo.main(argv)
        except SystemExit as exc:
            codigo = exc.code if isinstance(exc.code, int) else 2
    return codigo, salida.getvalue(), error.getvalue()


def test_la_bajada_de_recibo_lee_el_json_que_guarda_el_triaje():
    with Mundo() as w:
        ticket = w.raiz / TICKET
        ticket.mkdir(parents=True)
        escribir(w.web, {"appsettings.json": "{}\n"})
        codigo, salida, error = bajar_con_el_triaje_real(w, ticket, "2026-11-18", [w.web], [w.web / "appsettings.json"])
        assert codigo == 0 and "bajado de completo a rapido" in salida, (codigo, salida, error)
        recibo = json.loads((ticket / "revision" / "2026-11-18-rapido" / "recibo.json").read_text(encoding="utf-8"))
        assert recibo["bajada"] == {"de": "completo", "a": "rapido", "motivo": "un json sin capa", "va_a_lider": False}, recibo
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        escribir(w.web, {CS_SVC: "class Servicio { int y; }\n"})
        codigo, salida, error = bajar_con_el_triaje_real(w, ticket, "2026-11-19", [w.db, w.web],
                                                         [w.db / SQL_ALFA, w.web / CS_SVC, w.web / "appsettings.json"])
        assert codigo == 2 and salida == "" and "senal capas: positiva" in error, (codigo, salida, error)
        assert not (ticket / "revision" / "2026-11-19-rapido" / "recibo.json").exists()


# ---------------------------------------------------------------- la huella del triaje y el taller por el repo de la instancia (integridad del recibo)

def test_s1_el_json_del_triaje_lleva_la_huella_del_diff_de_cada_repo_con_la_funcion_del_recibo():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3"), "Makefile": "x\n", "tools/__pycache__/u.pyc": b"\x00"})
        (w.db / SQL_GAMMA).unlink()
        args = ["--repo", str(w.db), "--repo", str(w.web), "--raiz", str(w.raiz)]
        codigo, salida, error = correr(args + ["--json"])
        assert codigo == 0 and error == "", error
        db, web = json.loads(salida)["repos"]
        assert list(db) == ["ruta", "base", "archivos", "sha256", "sha256_por_archivo", "generados"], list(db)
        rutas_db = [a["ruta"] for a in db["archivos"]]
        assert rutas_db == ["Makefile", SQL_ALFA, SQL_GAMMA], rutas_db
        huella = M.recibo.calcular(db["ruta"], db["base"], rutas_db)
        assert (db["sha256"], db["sha256_por_archivo"]) == (huella["sha256"], huella["sha256_por_archivo"]), db
        assert web["archivos"] == [] and web["sha256_por_archivo"] == {} and web["sha256"] == M.recibo.calcular(web["ruta"], web["base"], [])["sha256"]
        codigo, texto, _ = correr(args)
        assert codigo == 0 and "sha256" not in texto, "el texto sale como antes"


def guardar_el_triaje(w, ticket, carpeta, repos):
    argv = ["--raiz", str(w.raiz), "--ticket", str(ticket), "--json"]
    for repo in repos:
        argv += ["--repo", str(repo)]
    codigo, salida, error = correr(argv)
    assert codigo == 0, error
    (carpeta / "entrada").mkdir(parents=True, exist_ok=True)
    (carpeta / "entrada" / "triaje.json").write_text(salida, encoding="utf-8")
    return json.loads(salida)


def recibo_con_salida(argv):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = M.recibo.main(argv)
    return codigo, salida.getvalue(), error.getvalue()


def test_s1_la_bajada_con_el_triaje_de_antes_de_la_ultima_edicion_sale_con_2_y_no_escribe_el_recibo():
    with Mundo() as w:
        ticket = w.raiz / TICKET
        ticket.mkdir(parents=True)
        carpeta = ticket / "revision" / "2026-11-20-rapido"
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3"), "Makefile": "x\n"})
        triaje = guardar_el_triaje(w, ticket, carpeta, [w.db])
        assert triaje["modo"] == "completo" and triaje["motivos"] == ["señal consumidores: invalida", "señal capas: positiva"], triaje["motivos"]
        assert triaje["sin_capa"]["unico_motivo_de_capas"] is True, triaje["sin_capa"]
        argv = ["--write", "--ticket", str(ticket), "--repo", str(w.db), "--archivo", str(w.db / SQL_ALFA), "--archivo", str(w.db / "Makefile"),
                "--modo", "rapido", "--fecha", "2026-11-20", "--bajada", "Makefile sin capa", "--va-a-lider", "no"]
        codigo, salida, error = recibo_con_salida(argv)
        assert codigo == 0 and salida.endswith("(1 repo(s), 2 archivo(s); bajado de completo a rapido)\n"), "antes de la edicion vale: %s" % error
        (carpeta / "recibo.json").unlink()
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", EFECTO)})
        codigo, salida, error = recibo_con_salida(argv)
        assert codigo == 2 and salida == "" and "no es de este diff" in error and "corre el triaje de nuevo" in error, (codigo, salida, error)
        assert "%s cambio despues del triaje" % SQL_ALFA in error, error
        assert not (carpeta / "recibo.json").exists(), "el triaje viejo no escribe el recibo"
        triaje = guardar_el_triaje(w, ticket, carpeta, [w.db])
        assert triaje["senales"]["efecto"]["nivel"] == "positiva", triaje["senales"]["efecto"]
        codigo, salida, error = recibo_con_salida(argv)
        assert codigo == 2 and salida == "" and "senal efecto: positiva" in error, "con el triaje de nuevo, el efecto exige completo: %s" % error
        assert not (carpeta / "recibo.json").exists()


def instancia_versionada(w):
    git(w.raiz, "init", "-q")
    return commitear(w.raiz, {})


def niveles(r):
    return {id_: nivel(r, id_) for id_ in M.SENALES}, r["modo"]


def test_s4_un_archivo_del_taller_por_el_repo_de_la_instancia_da_las_mismas_senales_que_con_taller():
    casos = [
        ("un parametro nuevo contra la contraparte", None, ALFA.replace("@Id INT,", "@Id INT,\n    @Extra INT,")),
        ("igual a su contraparte", None, ALFA),
        ("dinero solo en la contraparte", {SQL_ALFA: ALFA.replace("SELECT 1", "SET @Total = @Total + @Propina;")}, ALFA),
        ("sin contraparte", None, "CREATE PROCEDURE esq.Proc_Inventada\nAS\nBEGIN\n    SELECT 1\nEND\n"),
        ("un borrador ya versionado en la instancia", None, ALFA.replace("SELECT 1", EFECTO)),
    ]
    for nombre, en_db, texto in casos:
        with Mundo() as w:
            if en_db:
                commitear(w.db, en_db)
                publicar(w.db)
            archivo = "esq.Proc_Inventada.sql" if "Inventada" in texto else "esq.Proc_Alfa.sql"
            if nombre.startswith("un borrador"):
                w.taller(archivo, ALFA)
            base = instancia_versionada(w)
            ruta = w.taller(archivo, texto)
            por_taller = w.analizar(repos=[], taller=[ruta])
            por_repo = M.analizar([(str(w.raiz), base)], taller=[], raiz=str(w.raiz))
            assert niveles(por_repo) == niveles(por_taller), (nombre, niveles(por_repo), niveles(por_taller))
            rel = "tickets/T-1-x/SQL/" + archivo
            assert [(a["ruta"], a["capa"], a["origen"]) for a in por_repo["repos"][0]["archivos"]] == [(rel, "sql", "taller")], por_repo["repos"][0]
    with Mundo() as w:
        base = instancia_versionada(w)
        ruta = w.taller("esq.Proc_Alfa.sql", ALFA.replace("@Id INT,", "@Id INT,\n    @Extra INT,"))
        por_repo = M.analizar([(str(w.raiz), base)], taller=[], raiz=str(w.raiz))
        assert nivel(por_repo, "contrato") == "positiva" and "@Extra" in detalle(por_repo, "contrato"), por_repo["senales"]["contrato"]
        d = detalle(por_repo, "consumidores")
        assert "Proc_Alfa: ≥ 1, " in d and "Proc_Beta.sql" in d, "cuenta en los repos, sin tratarlo como objeto nuevo: %s" % d


def test_un_submodulo_borrado_no_tumba_el_triaje_y_la_bajada_vale_con_un_recibo_de_archivos():
    with Mundo() as w:
        ticket = w.raiz / TICKET
        ticket.mkdir(parents=True)
        git(w.web, "update-index", "--add", "--cacheinfo", "160000,%s,mods/s" % ("1" * 40))
        git(w.web, "commit", "-q", "-m", "submodulo")
        publicar(w.web)
        git(w.web, "rm", "--cached", "-q", "mods/s")
        escribir(w.web, {"appsettings.json": "{}\n"})
        codigo, salida, error = bajar_con_el_triaje_real(w, ticket, "2026-11-20", [w.web], [w.web / "appsettings.json"])
        assert codigo == 0 and "bajado de completo a rapido" in salida, (codigo, salida, error)
        assert "vio cambios que el recibo no cubre" in error and ": mods/s;" in error, error


def test_un_repo_anidado_sin_trackear_no_impide_la_bajada_con_un_recibo_de_archivos():
    with Mundo() as w:
        ticket = w.raiz / TICKET
        ticket.mkdir(parents=True)
        anidado = w.web / "vendor" / "lib"
        anidado.mkdir(parents=True)
        git(anidado, "init", "-q")
        escribir(anidado, {"lib.txt": "de otro repo\n"})
        escribir(w.web, {"appsettings.json": "{}\n"})
        codigo, salida, error = bajar_con_el_triaje_real(w, ticket, "2026-11-20", [w.web], [w.web / "appsettings.json"])
        assert codigo == 0 and "bajado de completo a rapido" in salida, (codigo, salida, error)
        assert "vio cambios que el recibo no cubre" in error and "vendor/lib/" in error, error


# ---------------------------------------------------------------- chequeos (I47)

CHEQUEO_MALO = '''import types
REGLAS = (types.SimpleNamespace(id="T-02", sembrado="x = MALO;"),)
def verificar(ctx):
    return [{"id": "T-02", "modo": "bloqueo", "severidad": "CRITICAL", "linea": n, "fragmento": "MALO",
             "mensaje": "MALO no va"} for n, t in ctx["agregadas"] if "MALO" in t]
'''
CONFLICTO = "antes\n%s HEAD\nlo nuestro\n%s\nlo de ellos\n%s otra\ndespues\n" % ("<" * 7, "=" * 7, ">" * 7)
TEXTO_MALO = "[T-02 CRITICAL] linea %d en «MALO»: MALO no va"
LIMPIO = "chequeos: sin hallazgos ni marcadores de conflicto (%d archivo(s) con chequeos de capa)"


def con_chequeo(w, capa, fuente=CHEQUEO_MALO, calibrar=True):
    escribir(w.raiz, {".claude/reglas/verificar_%s.py" % capa: fuente})
    if not calibrar:
        return
    import reglas
    corpus = w.base / "corpus-vacio"
    corpus.mkdir(exist_ok=True)
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = reglas.main(["--calibrar", capa, str(corpus), "--guardar", "--raiz", str(w.raiz)])
    assert codigo == 0, (codigo, salida.getvalue(), error.getvalue())


def poner_paquete(w, nombre, prefijo, fuente, capa):
    from odd_ws import paquetes
    carpeta = ".claude/reglas/paquetes/%s/" % nombre
    escribir(w.raiz, {carpeta + "verificar.py": fuente, carpeta + "no-negociables.md": "",
                      carpeta + "odd-ws-paquete.json": json.dumps({"formato": 1, "nombre": nombre, "prefijo": prefijo,
                                                                   "odd_ws_api": 1, "descripcion": "de prueba"})})
    lock = {"version": 1, "paquetes": {nombre: {"capa": capa, "prefijo": prefijo, "fuente": "https://example.com/%s.git" % nombre,
                                                "etiqueta": "v1.0.0", "commit": "a" * 40,
                                                "huella": paquetes.huella(w.raiz / carpeta)}}}
    escribir(w.raiz, {".claude/reglas/paquetes.json": json.dumps(lock)})


def triado(w, repos=None, taller=()):
    argv = ["--raiz", str(w.raiz)]
    for repo in (repos if repos is not None else [w.db]):
        argv += ["--repo", str(repo)]
    for archivo in taller:
        argv += ["--taller", str(archivo)]
    codigo, salida, error = correr(argv + ["--json"])
    assert codigo == 0 and error == "", (codigo, error)
    datos = json.loads(salida)
    codigo, texto, error = correr(argv)
    assert codigo == 0 and error == "", (codigo, error)
    return datos, texto


def en_el_repo(datos, ruta, i=0):
    return "%s/%s" % (Path(datos["repos"][i]["ruta"]).as_posix(), ruta)


def test_chequeos_una_regla_calibrada_rota_en_una_linea_cambiada_sale_en_chequeos_sin_cambiar_lo_demas():
    with Mundo() as w:
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 1 -- MALO")})
        sin_chequeo, texto_sin_chequeo = triado(w)
        con_chequeo(w, "sql")
        datos, texto = triado(w)
        ch = datos["chequeos"]
        assert ch["hallazgos"] == [{"repo": datos["repos"][0]["ruta"], "ruta": SQL_ALFA, "capa": "sql", "id": "T-02",
                                    "modo": "bloqueo", "severidad": "CRITICAL", "linea": 6, "mensaje": "MALO no va",
                                    "texto": TEXTO_MALO % 6}], ch
        assert ch["marcadores"] == [] and ch["sin_chequear"] == [] and ch["archivos"] == 1 and ch["corregir_antes_de_lanzar"] is True, ch
        assert "chequeos: 1 hallazgo(s) de capa: corregir antes de lanzar" in texto.splitlines(), texto
        assert "  %s [sql] %s" % (en_el_repo(datos, SQL_ALFA), TEXTO_MALO % 6) in texto.splitlines(), texto
        assert {k: v for k, v in datos.items() if k != "chequeos"} == {k: v for k, v in sin_chequeo.items() if k != "chequeos"}
        assert texto.split("\nchequeos: ")[0] == texto_sin_chequeo.split("\nchequeos: ")[0], "los chequeos solo suman"


def test_chequeos_una_violacion_que_ya_estaba_en_la_base_no_sale():
    with Mundo() as w:
        con_chequeo(w, "sql")
        viejo = ALFA.replace("SELECT 1", "SELECT 1 -- MALO")
        commitear(w.db, {SQL_ALFA: viejo})
        publicar(w.db)
        escribir(w.db, {SQL_ALFA: viejo.replace("VARCHAR(50)", "VARCHAR(80)")})
        datos, texto = triado(w)
        ch = datos["chequeos"]
        assert ch["hallazgos"] == [] and ch["archivos"] == 1 and ch["corregir_antes_de_lanzar"] is False, ch
        assert texto.splitlines()[-1] == LIMPIO % 1, texto
        escribir(w.db, {SQL_ALFA: viejo.replace("VARCHAR(50)", "VARCHAR(80) -- MALO")})
        ch = triado(w)[0]["chequeos"]
        assert [(h["ruta"], h["linea"]) for h in ch["hallazgos"]] == [(SQL_ALFA, 3)], "control positivo: solo la línea nueva: %s" % ch


def test_chequeos_un_archivo_sin_capa_no_se_chequea():
    with Mundo() as w:
        con_chequeo(w, "web")
        escribir(w.web, {"Data/Nuevo.cs": "class Nuevo { } // MALO\n", "scripts/malo.js": "// MALO\n"})
        datos, _ = triado(w, repos=[w.web])
        ch = datos["chequeos"]
        assert [h["ruta"] for h in ch["hallazgos"]] == ["Data/Nuevo.cs"] and ch["archivos"] == 1 and ch["sin_chequear"] == [], ch
        assert datos["sin_capa"]["archivos"] == ["scripts/malo.js"], datos["sin_capa"]


def test_chequeos_un_marcador_de_conflicto_en_un_archivo_modificado_sin_trackear_o_del_taller_se_encuentra():
    with Mundo() as w:
        escribir(w.db, {"README.md": CONFLICTO, "src/ventas/Nuevo.sql": CONFLICTO, "src/ventas/Medio.sql": "<" * 7 + " solo\n"})
        datos, texto = triado(w)
        ch = datos["chequeos"]
        repo = datos["repos"][0]["ruta"]
        assert [(m["repo"], m["ruta"], m["linea"], m["texto"]) for m in ch["marcadores"]] == [
            (repo, "README.md", 2, "<" * 7 + " HEAD"), (repo, "README.md", 6, ">" * 7 + " otra"),
            (repo, "src/ventas/Nuevo.sql", 2, "<" * 7 + " HEAD"), (repo, "src/ventas/Nuevo.sql", 6, ">" * 7 + " otra")], ch
        assert ch["corregir_antes_de_lanzar"] is True and ch["hallazgos"] == [] and ch["sin_chequear"] == [], ch
        assert "chequeos: 2 archivo(s) con marcadores de conflicto: corregir antes de lanzar" in texto.splitlines(), texto
        assert "  %s:2: marcador de conflicto «%s HEAD»" % (en_el_repo(datos, "README.md"), "<" * 7) in texto.splitlines(), texto
        ruta = w.taller("esq.Proc_Alfa.sql", CONFLICTO)
        ch = triado(w, repos=[], taller=[ruta])[0]["chequeos"]
        assert [(m["repo"], m["ruta"], m["linea"]) for m in ch["marcadores"]] == [(None, ruta.as_posix(), 2), (None, ruta.as_posix(), 6)], ch


def test_chequeos_los_marcadores_no_dependen_del_indice_de_git_del_entorno():
    with Mundo() as w:
        escribir(w.db, {"README.md": CONFLICTO})
        previo = os.environ.get("GIT_INDEX_FILE")
        os.environ["GIT_INDEX_FILE"] = os.path.join(tempfile.gettempdir(), "odd-ws-indice-ajeno-que-no-existe")
        try:
            datos = triado(w)[0]
        finally:
            if previo is None:
                os.environ.pop("GIT_INDEX_FILE", None)
            else:
                os.environ["GIT_INDEX_FILE"] = previo
        assert [(m["ruta"], m["linea"]) for m in datos["chequeos"]["marcadores"]] == [("README.md", 2), ("README.md", 6)], datos["chequeos"]


def test_chequeos_proponen_corregir_antes_de_lanzar_solo_si_algo_falla():
    with Mundo() as w:
        con_chequeo(w, "sql")
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3")})
        datos, texto = triado(w)
        assert datos["chequeos"] == {"archivos": 1, "hallazgos": [], "marcadores": [], "sin_chequear": [],
                                     "corregir_antes_de_lanzar": False}, datos["chequeos"]
        assert texto.splitlines()[-1] == LIMPIO % 1 and "corregir antes de lanzar" not in texto, texto
        escribir(w.db, {SQL_BETA: BETA + "-- MALO\n"})
        datos, texto = triado(w)
        assert datos["chequeos"]["corregir_antes_de_lanzar"] is True and "corregir antes de lanzar" in texto, texto
        escribir(w.db, {SQL_BETA: BETA, "src/ventas/Otro.sql": CONFLICTO})
        datos, texto = triado(w)
        assert datos["chequeos"]["corregir_antes_de_lanzar"] is True and "corregir antes de lanzar" in texto, texto


def test_chequeos_un_chequeo_que_falla_sale_como_no_se_pudo_chequear_y_nunca_como_limpio():
    casos = [
        ("el módulo lanza", "def verificar(ctx):\n    raise RuntimeError('boom')\n", None, "RuntimeError: boom"),
        ("el módulo devuelve un hallazgo mal formado", "def verificar(ctx):\n    return [{'id': 'X'}]\n", None, "mal formado"),
        ("un paquete lanza", None, "def verificar(ctx):\n    raise RuntimeError('boom del paquete')\n", "boom del paquete"),
        ("el archivo pasa del tope", CHEQUEO_MALO, None, "no se pudo armar su diff"),
    ]
    for nombre, modulo, paquete, motivo in casos:
        with Mundo() as w:
            if modulo is not None:
                con_chequeo(w, "sql", modulo, calibrar=False)
            if paquete is not None:
                poner_paquete(w, "roto", "ROT", paquete, "sql")
            escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 3 -- MALO")})
            previo = M.verificar_capa.TOPE_BYTES
            if motivo == "no se pudo armar su diff":
                M.verificar_capa.TOPE_BYTES = 10
            try:
                datos, texto = triado(w)
            finally:
                M.verificar_capa.TOPE_BYTES = previo
            ch = datos["chequeos"]
            assert [(s["repo"], s["ruta"], s["capa"]) for s in ch["sin_chequear"]] == [(datos["repos"][0]["ruta"], SQL_ALFA, "sql")], (nombre, ch)
            assert motivo in ch["sin_chequear"][0]["motivo"], (nombre, ch["sin_chequear"])
            assert ch["hallazgos"] == [] and ch["archivos"] == 0 and ch["corregir_antes_de_lanzar"] is True, (nombre, ch)
            assert "chequeos: 1 sin chequear: corregir antes de lanzar" in texto.splitlines(), (nombre, texto)
            assert "  %s [sql]: no se pudo chequear: %s" % (en_el_repo(datos, SQL_ALFA), ch["sin_chequear"][0]["motivo"]) in texto.splitlines(), (nombre, texto)
            assert "chequeos: sin hallazgos" not in texto, (nombre, texto)


def test_chequeos_tapan_el_secreto_que_cita_una_regla_en_el_json_y_en_el_texto():
    token = "gh" + "p_" + ("aB3dE5fG7h" * 4)[:36]
    with Mundo() as w:
        con_chequeo(w, "sql", CHEQUEO_MALO.replace('"fragmento": "MALO"', '"fragmento": t'))
        escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 1 -- MALO " + token)})
        datos, texto = triado(w)
        [hallazgo] = datos["chequeos"]["hallazgos"]
        citado = "[T-02 CRITICAL] linea 6 en «SELECT 1 -- MALO <GITHUB_TOKEN>»: MALO no va"
        assert hallazgo["texto"] == citado, hallazgo
        assert "  %s [sql] %s" % (en_el_repo(datos, SQL_ALFA), citado) in texto.splitlines(), texto
        assert token not in json.dumps(datos, ensure_ascii=False) and token not in texto, "el token sale sin tapar"


def test_chequeos_el_taller_se_mide_contra_su_contraparte_aunque_este_commiteado_en_la_instancia():
    with Mundo() as w:
        instancia_versionada(w)
        con_chequeo(w, "sql")
        viejo = ALFA.replace("@Id INT,", "@Id INT, -- MALO viejo")
        commitear(w.db, {SQL_ALFA: viejo})
        publicar(w.db)
        ruta = w.taller("esq.Proc_Alfa.sql", viejo.replace("SELECT 1", "SELECT 1 -- MALO"))
        commitear(w.raiz, {})
        datos, texto = triado(w, repos=[], taller=[ruta])
        ch = datos["chequeos"]
        assert [(h["repo"], h["ruta"], h["linea"]) for h in ch["hallazgos"]] == [(None, ruta.as_posix(), 6)], ch
        assert "  %s [sql] %s" % (ruta.as_posix(), TEXTO_MALO % 6) in texto.splitlines(), texto


def test_el_triaje_lanza_los_mismos_git_con_un_archivo_de_capa_por_estado_que_con_tres():
    cuentas = []
    for n in (1, 3):
        with git_aislado(), Mundo() as w:
            con_chequeo(w, "web", calibrar=False)
            commitear(w.web, {"Data/M%d.cs" % i: "class M%d { }\n" % i for i in range(n)})
            publicar(w.web)
            escribir(w.web, {"Data/M%d.cs" % i: "class M%d { } // MALO\n" % i for i in range(n)})
            escribir(w.web, {"Data/A%d.cs" % i: "class A%d { } // MALO\n" % i for i in range(n)})
            git(w.web, "add", "--", *("Data/A%d.cs" % i for i in range(n)))
            escribir(w.web, {"Data/S%d.cs" % i: "class S%d { } // MALO\n" % i for i in range(n)})
            config = M.config_loader.cargar(str(w.raiz))
            lanzados, original = [], M.subprocess.run

            def espia(args, *a, **k):
                lanzados.append(list(args))
                return original(args, *a, **k)

            M.subprocess.run = espia
            try:
                r = M.recolectar_repo(str(w.web), None, config)
                ch = M.chequear([r], [], config)
            finally:
                M.subprocess.run = original
            assert ch["archivos"] == 3 * n and len(ch["hallazgos"]) == 3 * n and ch["sin_chequear"] == [], ch
            assert sorted(c["estado"] for c in r["cambios"]) == sorted("AM?" * n), r["cambios"]
            cuentas.append(len([a for a in lanzados if "--check" not in a and "--name-only" not in a]))
    assert cuentas[0] == cuentas[1] <= 12, "el triaje lanza un git por archivo: %s" % cuentas


VARIADO_BINARIO = b"\x00\x01CREATE PROCEDURE esq.Proc_Datos\x00"
VARIADO_ANO = "src/ventas/Proc Año [v2].sql"
VARIADO_GLOB = "src/ventas/Proc Año 2.sql"


def mundo_variado(w):
    instancia_versionada(w)
    con_chequeo(w, "sql")
    con_chequeo(w, "web")
    taller_commiteado = w.taller("esq.Proc_Alfa.sql", ALFA)
    base_inst = commitear(w.raiz, {}, "taller")
    w.taller("esq.Proc_Alfa.sql", ALFA.replace("SELECT 1", "SELECT 1 -- MALO"))
    taller_suelto = w.taller("esq.Proc_Beta.sql", BETA + "-- MALO\n")
    commitear(w.db, {"src/ventas/Proc_Crlf.sql": GAMMA.replace("Gamma", "Crlf").replace("\n", "\r\n"), VARIADO_ANO: GAMMA.replace("Gamma", "Ano"),
                     VARIADO_GLOB: "-- glob\n", "src/ventas/Datos.sql": VARIADO_BINARIO, "src/ventas/Proc_Conflicto.sql": "antes\ndespues\n",
                     "src/ventas/Proc_U16.sql": codecs.BOM_UTF16_LE + GAMMA.replace("Gamma", "U16").encode("utf-16-le")})
    publicar(w.db)
    git(w.db, "mv", SQL_BETA, "src/ventas/Proc_BetaNuevo.sql")
    os.remove(w.db / SQL_GAMMA)
    escribir(w.db, {SQL_ALFA: ALFA.replace("SELECT 1", "SELECT 1 -- MALO"), "src/ventas/Proc_BetaNuevo.sql": BETA + "-- MALO\n",
                    "src/ventas/Proc_Crlf.sql": GAMMA.replace("Gamma", "Crlf").replace("SELECT 2", "SELECT 2 -- MALO").replace("\n", "\r\n"),
                    VARIADO_ANO: GAMMA.replace("Gamma", "Ano").replace("SELECT 2", "SELECT 2 -- MALO"), VARIADO_GLOB: "-- glob\n-- MALO\n",
                    "src/ventas/Datos.sql": VARIADO_BINARIO + b"MALO\x00", "src/ventas/Proc_Conflicto.sql": CONFLICTO,
                    "src/ventas/Proc_U16.sql": codecs.BOM_UTF16_LE + GAMMA.replace("Gamma", "U16").replace("SELECT 2", "SELECT 3").encode("utf-16-le"),
                    "src/ventas/Proc_Nuevo.sql": GAMMA.replace("Gamma", "Nuevo") + "-- MALO\n", "README.md": "# db\notra\n",
                    "src/ventas/Proc_Suelto.sql": GAMMA.replace("Gamma", "Suelto") + "-- MALO\n"})
    git(w.db, "add", "--", "src/ventas/Proc_Nuevo.sql")
    commitear(w.web, {".gitattributes": "Data/Mayus.cs diff=mayus\n", "Data/Mayus.cs": "class mayus { }\n"})
    publicar(w.web)
    escribir(w.web, {CS_SVC: "class Servicio { } // MALO\n", "Data/Mayus.cs": "class mayus { } // malo\n", "Data/Nuevo.cs": "class Nuevo { } // MALO\n"})
    return [w.db, w.web, "%s#%s" % (w.raiz, base_inst)], [taller_suelto, taller_commiteado]


def test_el_triaje_por_lotes_sale_igual_que_archivo_por_archivo():
    with git_aislado("[diff \"mayus\"]\n\ttextconv = tr a-z A-Z <\n[diff]\n\tnoprefix = true\n\tsubmodule = log\n"), Mundo() as w:
        repos, taller = mundo_variado(w)
        por_lotes = triado(w, repos=repos, taller=taller)
        originales = (M._diffs_del_repo, M._leer_en_lote, M._previos)
        M._diffs_del_repo, M._leer_en_lote, M._previos = (lambda *a: None), (lambda *a: None), (lambda *a: {})
        try:
            por_archivo = triado(w, repos=repos, taller=taller)
        finally:
            M._diffs_del_repo, M._leer_en_lote, M._previos = originales
        assert por_lotes == por_archivo, "los lotes cambian la salida"
        datos, texto = por_lotes
        estados = {(Path(r["ruta"]).name, a["ruta"]): a["estado"] for r in datos["repos"] for a in r["archivos"]}
        for clave, estado in (((w.db.name, SQL_ALFA), "M"), ((w.db.name, SQL_BETA), "D"), ((w.db.name, "src/ventas/Proc_BetaNuevo.sql"), "A"),
                              ((w.db.name, SQL_GAMMA), "D"), ((w.db.name, "src/ventas/Proc_Suelto.sql"), "?"), ((w.db.name, VARIADO_ANO), "M")):
            assert estados.get(clave) == estado, (clave, estados)
        hallazgos = {(Path(h["repo"]).name if h["repo"] else None, h["ruta"]) for h in datos["chequeos"]["hallazgos"]}
        for esperado in ((w.db.name, SQL_ALFA), (w.db.name, "src/ventas/Proc_BetaNuevo.sql"), (w.db.name, "src/ventas/Proc_Crlf.sql"),
                         (w.db.name, VARIADO_ANO), (w.db.name, "src/ventas/Proc_Nuevo.sql"), (w.db.name, "src/ventas/Proc_Suelto.sql"),
                         (w.web.name, CS_SVC), (w.web.name, "Data/Mayus.cs"), (w.web.name, "Data/Nuevo.cs"),
                         (None, taller[0].as_posix()), ("inst", "tickets/T-1-x/SQL/esq.Proc_Alfa.sql")):
            assert esperado in hallazgos, (esperado, hallazgos)
        assert {m["ruta"] for m in datos["chequeos"]["marcadores"]} == {"src/ventas/Proc_Conflicto.sql"}, datos["chequeos"]["marcadores"]
        consumidores = detalle(datos, "consumidores")
        assert "Proc_U16:" in consumidores and "Proc_U16: objeto nuevo" not in consumidores, "la base UTF-16 se lee: %s" % consumidores


PRUEBAS =[(n[len("test_"):], f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]


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
