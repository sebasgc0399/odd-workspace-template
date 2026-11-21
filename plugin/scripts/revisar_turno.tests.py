import ast
import contextlib
import importlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_RUTA = AQUI / "revisar_turno.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
SILENCIO = (0, "", b"")
FRASE = "si este cambio no es tuyo, avísale al usuario y no lo toques"
AISLAMIENTO = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM", "CLAUDE_PROJECT_DIR")

from odd_ws import capas as convencion  # noqa: E402
from odd_ws import comun  # noqa: E402
from odd_ws.capacidades import FIN_TURNO  # noqa: E402
from odd_ws.eventos import FinTurno, InicioTurno, Permitir, Seguir  # noqa: E402


def _cargar():
    spec = importlib.util.spec_from_file_location("revisar_turno", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


R = _cargar() if _RUTA.exists() else None

STUB = '''import types
REGLAS = (types.SimpleNamespace(id="T-01", sembrado="x MALO BLOQ"),)
def verificar(ctx):
    salida = []
    for n, t in ctx["agregadas"]:
        if "MALO" in t:
            salida.append({"id": "T-01", "modo": "bloqueo" if "BLOQ" in t else "aviso", "severidad": "ALTA",
                           "linea": n, "fragmento": "MALO", "mensaje": "l\\u00ednea marcada"})
    return salida
'''
STUB_EXPLOTA = '''def verificar(ctx):
    raise SystemExit(7)
'''
STUB_LENTO = '''import time
def verificar(ctx):
    limite = ctx["limite"]
    time.sleep(5 if limite is None else max(0.0, limite - time.monotonic()))
    return []
'''


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    base = Path(tempfile.mkdtemp(prefix="revisar-turno-test-"))
    vacio = base / "gitconfig-vacio"
    vacio.write_bytes(b"")
    previo = {clave: os.environ.get(clave) for clave in AISLAMIENTO}
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    os.environ.update({"GIT_CONFIG_GLOBAL": str(vacio), "GIT_CONFIG_SYSTEM": str(vacio), "GIT_CONFIG_NOSYSTEM": "1"})
    try:
        yield base
    finally:
        for clave, valor in previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(base, onexc=_quitar)
        if base.exists():
            SOBRANTES.append(str(base))


def _entorno():
    return {k: v for k, v in os.environ.items() if k not in comun.VARIABLES_DE_REPO_GIT}


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "core.autocrlf=false", "-c", "init.defaultBranch=main", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout


def escribir(raiz, rel, texto):
    p = Path(raiz) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)
    return p


def agregar(ruta, texto):
    with open(ruta, "ab") as f:
        f.write(texto.encode("utf-8"))


BASE = {"db/a.sql": "uno\ndos\n", "db/b.sql": "tres\n", "README.md": "hola\n"}


def calibrar(inst, capa):
    import reglas
    corpus = Path(inst).parent / "corpus-vacio"
    corpus.mkdir(parents=True, exist_ok=True)
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        codigo = reglas.main(["--calibrar", capa, str(corpus), "--guardar", "--raiz", str(inst)])
    assert codigo == 0, (codigo, salida.getvalue(), error.getvalue())


def escenario(base, archivos=None, modulo=STUB, calibrada=True):
    repo = Path(base) / "equipo" / "app"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    for rel, texto in (BASE if archivos is None else archivos).items():
        escribir(repo, rel, texto)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    inst = Path(base) / "inst"
    config = {"schema_version": 1, "repos": {"app": {}},
              "layers": {"sql": {"extensions": [".sql"], "repos": ["app"], "workshop": ["taller/*.sql"]}}}
    escribir(inst, "workspace.config.json", json.dumps(config))
    escribir(inst, "workspace.local.json", json.dumps({"repos": {"app": {"path": str(repo)}}}))
    escribir(inst, ".gitignore", "workspace.local.json\n.claude/estado/\n")
    escribir(inst, convencion.chequeo("sql"), modulo)
    if calibrada and modulo is STUB:
        calibrar(inst, "sql")
    git(inst, "init", "-q")
    git(inst, "add", "-A")
    git(inst, "commit", "-q", "-m", "instancia")
    return repo, inst


def inicio(inst, sesion="s1", turno="t1", plazo=60, **extra):
    return R.decidir(InicioTurno(sesion=sesion, cwd=str(inst), turno=turno, **extra), raiz=str(inst), plazo=plazo)


def fin(inst, sesion="s1", plazo=60, host="claude-code", **extra):
    return R.decidir(FinTurno(sesion=sesion, cwd=str(inst), turno="t1", **extra), raiz=str(inst), plazo=plazo, host=host)


def turnos(inst):
    return Path(inst) / convencion.ESTADO / "turnos"


def foto(inst, sesion="s1"):
    return turnos(inst) / sesion


def manifiesto(inst, sesion="s1"):
    return json.loads((foto(inst, sesion) / "manifiesto.json").read_text(encoding="utf-8"))


def canonica(ruta):
    return os.path.normcase(os.path.realpath(str(ruta)))


def fotografiados(inst, sesion="s1"):
    return sorted(canonica(entrada["ruta"]) for entrada in manifiesto(inst, sesion)["archivos"])


def contenido_de_la_foto(inst, ruta, sesion="s1"):
    for entrada in manifiesto(inst, sesion)["archivos"]:
        if canonica(entrada["ruta"]) == canonica(ruta):
            return (foto(inst, sesion) / entrada["foto"]).read_bytes()
    return None


def motivo(decision):
    assert isinstance(decision, Seguir), decision
    return decision.motivo


def nombra(texto, ruta):
    return os.path.normcase(str(ruta)) in os.path.normcase(texto)


def test_el_inicio_de_un_subagente_no_saca_foto():
    with temporal() as base:
        repo, inst = escenario(base)
        escribir(repo, "db/a.sql", "uno\ndos\nsucio\n")
        for extra in ({"agente": "Explore"}, {"id_agente": "a1"}, {"agente": "writer-sql", "id_agente": "a2"}):
            assert inicio(inst, **extra) == Permitir(), extra
            assert not turnos(inst).exists(), extra
        assert inicio(inst) == Permitir()
        assert foto(inst).is_dir(), "el inicio del principal sí saca la foto"


def test_la_foto_guarda_solo_los_archivos_de_capa_sucios_con_su_contenido():
    with temporal() as base:
        repo, inst = escenario(base, {"db/a.sql": "uno\n", "db/b.sql": "dos\n", "b.sql": "raiz\n", "README.md": "hola\n"})
        arbol = base / "equipo" / "app-wt"
        git(repo, "worktree", "add", "-q", str(arbol), "-b", "otra")
        sucios = [escribir(repo, "db/a.sql", "uno\nsucio\n"), escribir(repo, "db/sub/n.sql", "nuevo\n"),
                  escribir(repo, "db/con espacio.sql", "espacio\n"), escribir(repo, "db/canción.sql", "tilde\n"),
                  escribir(arbol, "db/a.sql", "uno\nen el worktree\n")]
        git(repo, "mv", "db/b.sql", "db/r.sql")
        sucios.append(repo / "db" / "r.sql")
        escribir(repo, "README.md", "hola\ncambiado\n")
        assert inicio(inst) == Permitir()
        assert fotografiados(inst) == sorted(canonica(p) for p in sucios), fotografiados(inst)
        for ruta in sucios:
            assert contenido_de_la_foto(inst, ruta) == ruta.read_bytes(), ruta
        assert sorted(os.listdir(turnos(inst))) == ["s1"], "la foto se escribe de una vez, sin restos"
        assert manifiesto(inst)["turno"] == "t1"


def test_un_archivo_en_conflicto_entra_en_la_foto():
    with temporal() as base:
        repo, inst = escenario(base)
        git(repo, "checkout", "-q", "-b", "otra")
        agregar(repo / "db" / "a.sql", "otra\n")
        git(repo, "commit", "-qam", "otra")
        git(repo, "checkout", "-q", "main")
        agregar(repo / "db" / "a.sql", "main\n")
        git(repo, "commit", "-qam", "main")
        try:
            git(repo, "merge", "-q", "otra")
        except RuntimeError:
            pass
        assert git(repo, "status", "--porcelain").startswith("UU "), git(repo, "status", "--porcelain")
        assert inicio(inst) == Permitir()
        assert fotografiados(inst) == [canonica(repo / "db" / "a.sql")], fotografiados(inst)


def test_una_foto_pendiente_no_se_pisa():
    with temporal() as base:
        repo, inst = escenario(base)
        a = escribir(repo, "db/a.sql", "uno\ndos\nv1\n")
        assert inicio(inst, turno="t1") == Permitir()
        escribir(repo, "db/a.sql", "uno\ndos\nv2 MALO BLOQ\n")
        escribir(repo, "db/b.sql", "tres\notro\n")
        assert inicio(inst, turno="t2") == Permitir()
        assert manifiesto(inst)["turno"] == "t1"
        assert fotografiados(inst) == [canonica(a)], fotografiados(inst)
        assert contenido_de_la_foto(inst, a) == b"uno\ndos\nv1\n"
        texto = motivo(fin(inst))
        assert nombra(texto, a) and "línea 3" in texto, texto


def test_un_turno_sin_cambios_deja_pasar_y_borra_la_foto():
    with temporal() as base:
        repo, inst = escenario(base)
        a = escribir(repo, "db/a.sql", "uno\nviejo MALO BLOQ\ndos\n")
        verificar_capa = importlib.import_module("verificar_capa")
        import config_loader
        _, hallazgos = verificar_capa.verificar_archivo(str(a), config_loader.cargar(inst))
        assert [h["modo"] for h in hallazgos] == ["bloqueo"], "contra HEAD la línea sí bloquea: %r" % hallazgos
        assert inicio(inst) == Permitir()
        assert fin(inst) == Permitir()
        assert not foto(inst).exists()


def test_un_archivo_de_capa_escrito_por_cualquier_via_con_un_bloqueo_hace_seguir_y_lo_nombra():
    with temporal() as base:
        repo, inst = escenario(base)
        b = repo / "db" / "b.sql"
        agregar(b, "z MALO BLOQ\n")
        parche = base / "cambio.patch"
        parche.write_bytes(git(repo, "diff").encode("utf-8"))
        git(repo, "checkout", "--", "db/b.sql")
        assert inicio(inst) == Permitir()
        a = repo / "db" / "a.sql"
        agregar(a, "x MALO BLOQ\ny MALO\n")
        git(repo, "apply", str(parche))
        texto = motivo(fin(inst))
        assert nombra(texto, a) and nombra(texto, b), texto
        assert "[T-01 ALTA]" in texto and "línea 3: línea marcada" in texto and "línea 2: línea marcada" in texto, texto
        assert "Avisos" in texto and "línea 4: línea marcada" in texto, "los avisos van en el mismo mensaje: %s" % texto
        assert texto.index("Avisos") > texto.index("línea 2: línea marcada"), texto
        assert FRASE in texto, texto
        assert "Edit o Write" in texto, texto
        assert foto(inst).is_dir(), "con un bloqueo la foto queda para la continuación"
        assert "apply_patch" in motivo(fin(inst, host="codex"))


def test_un_bloqueo_sin_calibrar_no_hace_seguir_y_su_aviso_dice_por_que():
    with temporal() as base:
        repo, inst = escenario(base, calibrada=False)
        assert inicio(inst) == Permitir()
        a = repo / "db" / "a.sql"
        agregar(a, "x MALO BLOQ\n")
        assert fin(inst) == Permitir(), "sin calibrar, el bloqueo no hace seguir"
        import config_loader
        bloqueos, avisos = R._chequear([(str(a), None, None)], config_loader.cargar(inst), None)
        assert bloqueos == [] and len(avisos) == 1, (bloqueos, avisos)
        assert avisos[0].endswith("línea 3: línea marcada (aviso: sin calibrar; para que bloquee, correr "
                                  "`reglas.py --calibrar sql <carpeta> --guardar`)"), avisos


def fotos_del_writer(inst, sesion="s1", agente="writer-sql"):
    carpeta = Path(inst) / convencion.ESTADO_WRITERS / sesion / (agente + ".fotos")
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def marcar(carpeta, ruta, extension):
    (carpeta / (R.clave_foto(str(ruta)) + extension)).write_bytes(b"")


def test_un_archivo_con_un_writer_en_curso_queda_para_su_compuerta():
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        a, b = repo / "db" / "a.sql", repo / "db" / "b.sql"
        agregar(a, "x MALO BLOQ\n")
        agregar(b, "z MALO BLOQ\n")
        marcar(fotos_del_writer(inst), a, ".foto")
        texto = motivo(fin(inst, segundo_plano=True))
        assert nombra(texto, b) and not nombra(texto, a), texto
        marcar(fotos_del_writer(inst, sesion="s2"), b, ".foto")
        assert nombra(motivo(fin(inst, segundo_plano=True)), b), "la foto de un writer de otra sesión no saca el archivo"


def test_un_archivo_nuevo_de_un_writer_en_curso_queda_para_su_compuerta():
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        b = repo / "db" / "b.sql"
        agregar(b, "z MALO BLOQ\n")
        nuevo = escribir(repo, "db/n.sql", "x MALO BLOQ\n")
        marcar(fotos_del_writer(inst), nuevo, ".nuevo")
        texto = motivo(fin(inst, segundo_plano=True))
        assert nombra(texto, b) and not nombra(texto, nuevo), "writer_guard marca con .nuevo lo que el writer crea: %s" % texto


def test_la_foto_de_un_writer_solo_cuenta_si_el_host_avisa_trabajo_en_segundo_plano():
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        a = repo / "db" / "a.sql"
        agregar(a, "x MALO BLOQ\n")
        nuevo = escribir(repo, "db/n.sql", "y MALO BLOQ\n")
        fotos = fotos_del_writer(inst)
        marcar(fotos, a, ".foto")
        marcar(fotos, nuevo, ".nuevo")
        _, terminar, _ = _turno_por_host("claude-code", inst)
        texto = _motivo_de_la_salida("claude-code", R.correr(terminar, raiz=str(inst), plazo=60, host="claude-code"))
        assert nombra(texto, a) and nombra(texto, nuevo), "sin trabajo en segundo plano, un writer caído no esconde nada: %s" % texto
        assert foto(inst).is_dir()
        en_curso = dict(terminar, background_tasks=[{"id": "task-001", "type": "subagent", "status": "running",
                                                     "description": "writer", "agent_type": "writer-sql"}])
        assert R.correr(en_curso, raiz=str(inst), plazo=60, host="claude-code") == SILENCIO, (
            "con trabajo en segundo plano, los dos quedan para writer_stop")


def test_un_commit_durante_el_turno_no_saca_los_cambios_de_la_revision():
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        a = repo / "db" / "a.sql"
        agregar(a, "x MALO BLOQ\n")
        escribir(repo, "README.md", "hola\nz MALO BLOQ\n")
        git(repo, "commit", "-qam", "x")
        nuevo = escribir(repo, "db/n.sql", "n MALO BLOQ\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "y")
        assert git(repo, "status", "--porcelain") == ""
        texto = motivo(fin(inst))
        assert nombra(texto, a) and "línea 3" in texto, texto
        assert nombra(texto, nuevo) and "línea 1" in texto, texto
        assert "README" not in texto, texto


def test_lo_commiteado_en_el_turno_se_sigue_viendo_si_el_archivo_se_vuelve_a_editar():
    with temporal() as base:
        repo, inst = escenario(base)
        b = escribir(repo, "db/b.sql", "tres\nantes\n")
        assert inicio(inst) == Permitir()
        a = repo / "db" / "a.sql"
        agregar(a, "x MALO BLOQ\n")
        agregar(b, "y MALO BLOQ\n")
        git(repo, "commit", "-qam", "x")
        agregar(a, "limpia\n")
        agregar(b, "limpia\n")
        texto = motivo(fin(inst))
        assert nombra(texto, a) and nombra(texto, b), texto
        assert texto.count("línea 3") == 2 and "línea 4" not in texto, texto


def test_una_foto_sin_cabezas_de_la_version_anterior_se_revisa_como_antes():
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        datos = manifiesto(inst)
        assert "cabezas" in datos, datos
        del datos["cabezas"]
        (foto(inst) / "manifiesto.json").write_text(json.dumps(datos), encoding="utf-8")
        agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
        git(repo, "commit", "-qam", "x")
        b = repo / "db" / "b.sql"
        agregar(b, "y MALO BLOQ\n")
        texto = motivo(fin(inst))
        assert nombra(texto, b) and not nombra(texto, repo / "db" / "a.sql"), texto


def test_una_linea_mala_de_antes_del_turno_no_se_marca_despues_de_un_commit():
    with temporal() as base:
        repo, inst = escenario(base, {"db/a.sql": "uno\nviejo MALO BLOQ\n", "db/b.sql": "tres\n", "README.md": "hola\n"})
        b = escribir(repo, "db/b.sql", "tres\nsucia MALO BLOQ\n")
        escribir(repo, "db/c.sql", "c MALO BLOQ\n")
        assert inicio(inst) == Permitir()
        agregar(repo / "db" / "a.sql", "limpia\n")
        agregar(b, "limpia\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "x")
        assert fin(inst) == Permitir()
        assert not foto(inst).exists()


def test_un_checkout_a_otra_rama_durante_el_turno_no_marca_lo_que_ya_tenia_esa_rama():
    with temporal() as base:
        repo, inst = escenario(base)
        git(repo, "checkout", "-q", "-b", "otra")
        agregar(repo / "db" / "a.sql", "de otra MALO BLOQ\n")
        escribir(repo, "db/o.sql", "o MALO BLOQ\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "otra")
        git(repo, "checkout", "-q", "main")
        agregar(repo / "db" / "b.sql", "en main\n")
        git(repo, "commit", "-qam", "main")
        assert inicio(inst) == Permitir()
        git(repo, "checkout", "-q", "otra")
        assert fin(inst) == Permitir()
        assert not foto(inst).exists()


def test_una_linea_mala_que_ya_estaba_en_un_archivo_sucio_no_se_vuelve_a_marcar():
    with temporal() as base:
        repo, inst = escenario(base)
        a = escribir(repo, "db/a.sql", "uno\nviejo MALO BLOQ\ndos\n")
        assert inicio(inst) == Permitir()
        escribir(repo, "db/a.sql", "uno\nviejo cambiado MALO BLOQ\ndos\nlimpia\n")
        assert fin(inst) == Permitir()
        assert not foto(inst).exists()
        assert inicio(inst) == Permitir()
        agregar(a, "nueva MALO BLOQ\n")
        texto = motivo(fin(inst))
        assert nombra(texto, a) and "línea 5" in texto and "línea 2" not in texto, texto


def test_una_linea_mala_nueva_en_un_archivo_limpio_se_mide_contra_head():
    with temporal() as base:
        repo, inst = escenario(base, {"db/a.sql": "uno\nviejo MALO BLOQ\n", "README.md": "hola\n"})
        a = repo / "db" / "a.sql"
        assert inicio(inst) == Permitir()
        assert fotografiados(inst) == [], "un archivo limpio no entra en la foto"
        agregar(a, "nueva MALO BLOQ\n")
        texto = motivo(fin(inst))
        assert nombra(texto, a) and "línea 3" in texto and "línea 2" not in texto, texto


def test_continuado_deja_pasar_y_borra_la_foto():
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
        assert fin(inst, continuado=True) == Permitir()
        assert not foto(inst).exists()
        assert fin(inst) == Permitir(), "sin foto no hay otra vuelta"


def test_los_archivos_revertidos_o_borrados_se_ignoran():
    with temporal() as base:
        repo, inst = escenario(base)
        escribir(repo, "db/a.sql", "uno\ndos\nsucio\n")
        u = escribir(repo, "db/u.sql", "suelto\n")
        assert inicio(inst) == Permitir()
        git(repo, "checkout", "--", "db/a.sql")
        b = repo / "db" / "b.sql"
        agregar(b, "x MALO BLOQ\n")
        b.unlink()
        u.unlink()
        assert fin(inst) == Permitir()
        assert not foto(inst).exists()


def test_un_archivo_de_capa_nuevo_sin_trackear_se_revisa():
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        nuevo = escribir(repo, "db/carpeta/nueva/n.sql", "uno\nx MALO BLOQ\n")
        escribir(repo, "db/carpeta/nueva/notas.txt", "x MALO BLOQ\n")
        texto = motivo(fin(inst))
        assert nombra(texto, nuevo) and "línea 2" in texto and "notas.txt" not in texto, texto


def test_un_archivo_del_taller_en_la_raiz_de_la_instancia_se_revisa():
    with temporal() as base:
        repo, inst = escenario(base)
        viejo = escribir(inst, "taller/viejo.sql", "v MALO BLOQ\n")
        assert inicio(inst) == Permitir()
        assert fotografiados(inst) == [canonica(viejo)], fotografiados(inst)
        nuevo = escribir(inst, "taller/nuevo.sql", "n MALO BLOQ\n")
        texto = motivo(fin(inst))
        assert nombra(texto, nuevo) and not nombra(texto, viejo), texto


def test_un_error_interno_deja_pasar():
    with temporal() as base:
        repo, inst = escenario(base, modulo=STUB_EXPLOTA)
        assert inicio(inst) == Permitir()
        agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
        assert fin(inst) == Permitir(), "una capa que revienta no tumba el cierre"
        assert not foto(inst).exists()
    with temporal() as base:
        repo, inst = escenario(base)
        assert inicio(inst) == Permitir()
        (foto(inst) / "manifiesto.json").write_text("{roto", encoding="utf-8")
        agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
        assert fin(inst) == Permitir()
        assert not foto(inst).exists(), "una foto ilegible se descarta para no frenar los turnos siguientes"
        original = R.config_loader.estado
        try:
            R.config_loader.estado = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
            assert inicio(inst) == Permitir() and fin(inst) == Permitir()
        finally:
            R.config_loader.estado = original
        assert not foto(inst).exists()
        for caso in ({}, [], "no es json", None, 5, b"\xff", {"hook_event_name": "Stop", "session_id": "s1"}):
            assert R.correr(caso, raiz=str(inst)) == SILENCIO, caso


def test_sin_instancia_o_sin_foto_deja_pasar():
    with temporal() as base:
        vacia = base / "vacia"
        vacia.mkdir()
        assert R.decidir(InicioTurno(sesion="s1", cwd=str(vacia))) == Permitir()
        assert R.decidir(FinTurno(sesion="s1", cwd=str(vacia))) == Permitir()
        assert list(vacia.iterdir()) == []
        repo, inst = escenario(base)
        agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
        assert fin(inst) == Permitir(), "sin la foto del inicio no hay revisión"
        assert not turnos(inst).exists()


def test_una_sesion_invalida_no_escribe_nada():
    with temporal() as base:
        repo, inst = escenario(base)
        escribir(repo, "db/a.sql", "uno\ndos\nsucio\n")
        for sesion in (None, "", "../s1", "a/b", "s 1", 7):
            assert inicio(inst, sesion=sesion) == Permitir(), sesion
            assert fin(inst, sesion=sesion) == Permitir(), sesion
        assert not (Path(inst) / convencion.ESTADO).exists()


def test_el_plazo_agotado_no_deja_una_foto_a_medias_y_la_revision_lo_respeta():
    with temporal() as base:
        repo, inst = escenario(base)
        escribir(repo, "db/a.sql", "uno\ndos\nsucio\n")
        assert inicio(inst, plazo=1e-9) == Permitir()
        assert not turnos(inst).exists() or os.listdir(turnos(inst)) == [], "sin tiempo no se escribe una foto incompleta"
    with temporal() as base:
        repo, inst = escenario(base, modulo=STUB_LENTO)
        assert inicio(inst) == Permitir()
        for nombre in ("a", "b"):
            agregar(repo / "db" / ("%s.sql" % nombre), "x MALO BLOQ\n")
        antes = time.monotonic()
        assert fin(inst, plazo=2) == Permitir()
        duracion = time.monotonic() - antes
        assert duracion < 2 + 2, "la revisión responde dentro del plazo: %.2f s" % duracion
        assert not foto(inst).exists()


def test_una_foto_vieja_de_otra_sesion_se_poda():
    with temporal() as base:
        repo, inst = escenario(base)
        viejo, reciente = turnos(inst) / "vieja", turnos(inst) / "reciente"
        for carpeta in (viejo, reciente):
            carpeta.mkdir(parents=True)
        hace = time.time() - 8 * 86400
        os.utime(viejo, (hace, hace))
        assert inicio(inst) == Permitir()
        assert sorted(os.listdir(turnos(inst))) == ["reciente", "s1"], os.listdir(turnos(inst))


def test_la_foto_y_la_revision_no_tocan_el_indice():
    with temporal() as base:
        repo, inst = escenario(base)
        b = repo / "db" / "b.sql"
        hace = time.time() + 5
        os.utime(b, (hace, hace))
        indice = repo / ".git" / "index"
        antes = indice.read_bytes()
        assert inicio(inst) == Permitir()
        agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
        assert isinstance(fin(inst), Seguir)
        assert indice.read_bytes() == antes, "git status corre sin locks opcionales y no refresca el índice"


def test_emite_seguir_en_el_fin_de_turno_y_nada_mas():
    assert R.EMITE == {FIN_TURNO: (Seguir,)}
    arbol = ast.parse(_RUTA.read_text(encoding="utf-8"))
    construidas = {nodo.func.id for nodo in ast.walk(arbol) if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                   and nodo.func.id in ("Bloquear", "Preguntar", "Contexto", "Seguir")}
    assert construidas == {"Seguir"}, construidas


def _pi(tipo, inst, odd_ws=None):
    datos = {"type": tipo, "ctx": {"cwd": str(inst), "sessionId": "s1", "hasUI": False, "mode": "print"}}
    return datos if odd_ws is None else dict(datos, oddWs=odd_ws)


def _turno_por_host(host, inst):
    if host == "pi":
        return (_pi("before_agent_start", inst),
                _pi("agent_before_settle", inst, {"child": False, "lastAssistantMessage": "Listo.", "continued": False}),
                _pi("agent_before_settle", inst, {"child": False, "lastAssistantMessage": "Corregido.", "continued": True}))
    comun_ = {"session_id": "s1", "cwd": str(inst)}
    if host == "codex":
        comun_["turn_id"] = "t1"
    return (dict(comun_, hook_event_name="UserPromptSubmit", prompt="hola", prompt_id="p1"),
            dict(comun_, hook_event_name="Stop", stop_hook_active=False, last_assistant_message="Listo."),
            dict(comun_, hook_event_name="Stop", stop_hook_active=True, last_assistant_message="Corregido."))


def _motivo_de_la_salida(host, salida):
    codigo, texto, error = salida
    assert (codigo, error) == (0, b""), salida
    datos = json.loads(texto)
    if host == "pi":
        assert set(datos) == {"accion", "texto"} and datos["accion"] == "seguir", datos
        return datos["texto"]
    assert set(datos) == {"decision", "reason"} and datos["decision"] == "block", datos
    return datos["reason"]


def test_de_punta_a_punta_cada_host_saca_la_foto_al_empezar_y_hace_seguir_una_vez_al_terminar():
    for host, edicion in (("claude-code", "Edit o Write"), ("codex", "apply_patch"), ("pi", "`edit` o `write`")):
        with temporal() as base:
            repo, inst = escenario(base)
            empezar, terminar, continuacion = _turno_por_host(host, inst)
            assert R.correr(empezar, raiz=str(inst), plazo=60, host=host) == SILENCIO, host
            assert foto(inst).is_dir(), host
            a = repo / "db" / "a.sql"
            agregar(a, "x MALO BLOQ\n")
            texto = _motivo_de_la_salida(host, R.correr(terminar, raiz=str(inst), plazo=60, host=host))
            assert nombra(texto, a) and FRASE in texto and edicion in texto, (host, texto)
            assert foto(inst).is_dir(), host
            assert R.correr(continuacion, raiz=str(inst), plazo=60, host=host) == SILENCIO, host
            assert not foto(inst).exists(), "la continuación no revisa de nuevo y borra la foto: %s" % host


def test_de_punta_a_punta_un_subagente_no_saca_foto_y_su_cierre_no_toca_la_del_principal():
    with temporal() as base:
        repo, inst = escenario(base)
        agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
        subagente = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "turn_id": "t2", "cwd": str(inst), "prompt": "x",
                     "agent_id": "a1", "agent_type": "explorer"}
        assert R.correr(subagente, raiz=str(inst), plazo=60, host="codex") == SILENCIO
        assert not turnos(inst).exists(), "en Codex, UserPromptSubmit de un subagente no saca foto"
        hijo = _pi("before_agent_start", inst, {"agent": "writer-sql", "agentId": "hija"})
        assert R.correr(hijo, raiz=str(inst), plazo=60, host="pi") == SILENCIO
        assert not turnos(inst).exists(), "un hijo de gentle-shell no saca foto aunque lo mandaran"
        assert R.correr(_turno_por_host("pi", inst)[0], raiz=str(inst), plazo=60, host="pi") == SILENCIO
        assert foto(inst).is_dir()
        agregar(repo / "db" / "b.sql", "y MALO BLOQ\n")
        cierres = (("pi", _pi("agent_before_settle", inst, {"agent": "writer-sql", "agentId": "hija", "lastAssistantMessage": "x",
                                                            "continued": False})),
                   ("claude-code", {"hook_event_name": "SubagentStop", "session_id": "s1", "cwd": str(inst), "agent_type": "writer-sql",
                                    "agent_id": "a1", "stop_hook_active": False}),
                   ("codex", {"hook_event_name": "SubagentStop", "session_id": "s1", "turn_id": "t1", "cwd": str(inst),
                              "agent_type": "writer-sql", "agent_id": "a1", "stop_hook_active": False}))
        for host, cierre in cierres:
            assert R.correr(cierre, raiz=str(inst), plazo=60, host=host) == SILENCIO, host
            assert foto(inst).is_dir(), "el cierre de un writer es de writer_stop: %s" % host


def apagar(inst, valor):
    ruta = Path(inst) / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["disabled_hooks"] = valor
    ruta.write_text(json.dumps(config), encoding="utf-8")


def test_apagado_en_disabled_hooks_no_saca_foto_ni_hace_seguir_en_los_tres_hosts():
    for host in ("claude-code", "codex", "pi"):
        with temporal() as base:
            repo, inst = escenario(base)
            apagar(inst, ["revisar_turno"])
            empezar, terminar, _ = _turno_por_host(host, inst)
            escribir(repo, "db/a.sql", "uno\ndos\nsucio\n")
            assert R.correr(empezar, raiz=str(inst), plazo=60, host=host) == SILENCIO, host
            assert not turnos(inst).exists(), "apagado no escribe la carpeta de la foto: %s" % host
            agregar(repo / "db" / "b.sql", "x MALO BLOQ\n")
            assert R.correr(terminar, raiz=str(inst), plazo=60, host=host) == SILENCIO, host
            assert not turnos(inst).exists(), host
            apagar(inst, ["verificar_capa", "guard_comandos", "writer_guard", "writer_stop"])
            assert R.correr(empezar, raiz=str(inst), plazo=60, host=host) == SILENCIO and foto(inst).is_dir(), "control: %s" % host
            agregar(repo / "db" / "a.sql", "y MALO BLOQ\n")
            texto = _motivo_de_la_salida(host, R.correr(terminar, raiz=str(inst), plazo=60, host=host))
            assert nombra(texto, repo / "db" / "a.sql"), (host, texto)


def test_disabled_hooks_invalido_no_apaga_revisar_turno():
    for valor in ("revisar_turno", ["revisar-turno"], [None], ["revisar_turno", "revisar_turno"], {"revisar_turno": True}):
        with temporal() as base:
            repo, inst = escenario(base)
            apagar(inst, valor)
            assert inicio(inst) == Permitir() and foto(inst).is_dir(), valor
            agregar(repo / "db" / "a.sql", "x MALO BLOQ\n")
            assert nombra(motivo(fin(inst)), repo / "db" / "a.sql"), valor


def test_main_lee_stdin_y_falla_abierto():
    with temporal() as base:
        env = _entorno()
        for entrada in (b"\xff\xfe basura", b"", b"{}"):
            r = subprocess.run([sys.executable, str(_RUTA), "--plazo", "5"], input=entrada, capture_output=True, env=env,
                               cwd=str(base), timeout=120)
            assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), (entrada, r)


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
