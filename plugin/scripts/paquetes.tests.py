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
_RUTA = AQUI / "paquetes.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
AISLAMIENTO = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM", "CENTINELA_DE_LA_PRUEBA")
LOCK = ".claude/reglas/paquetes.json"
CARPETA = ".claude/reglas/paquetes/alfa"


def _cargar():
    spec = importlib.util.spec_from_file_location("paquetes_cli", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None
B = importlib.import_module("odd_ws.paquetes")


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


def _entorno():
    return {k: v for k, v in os.environ.items() if (not k.startswith("GIT_") or k in AISLAMIENTO) and k != "CLAUDE_PROJECT_DIR"}


def git(cwd, *args, entrada=None):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
                        "-c", "core.autocrlf=false", "-c", "init.defaultBranch=main", *args],
                       cwd=str(cwd), capture_output=True, input=entrada, env=_entorno())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr.decode("utf-8", "replace")))
    return r.stdout.decode("utf-8").strip()


VERIFICAR = '''import os
import types
with open(os.environ.get("CENTINELA_DE_LA_PRUEBA", os.devnull), "a") as f:
    f.write("verificar\\n")

REGLA = types.SimpleNamespace(id="ALF-01", sembrado="SELECT MALO;")
REGLAS = (REGLA,)


def verificar(ctx):
    return [{"id": REGLA.id, "modo": "bloqueo", "severidad": "", "linea": n, "fragmento": None, "mensaje": "MENSAJE"}
            for n, t in ctx["agregadas"] if "MALO" in t]
'''
SUITE = '''import os
with open(os.environ.get("CENTINELA_DE_LA_PRUEBA", os.devnull), "a") as f:
    f.write("suite\\n")
print("suite del paquete")
'''


def manifiesto(nombre="alfa", prefijo="ALF", **extra):
    return json.dumps({"formato": 1, "nombre": nombre, "prefijo": prefijo, "odd_ws_api": 1, "descripcion": "reglas de ejemplo", **extra})


def archivos(mensaje, nombre="alfa", prefijo="ALF", **extra):
    return {"odd-ws-paquete.json": manifiesto(nombre, prefijo, **extra), "verificar.py": VERIFICAR.replace("MENSAJE", mensaje),
            "verificar.tests.py": SUITE, "matriz.csv": "id,origen,tipo,destino,severidad,numeros,resumen,motivo\nALF-01,memoria:x,CE,chequeo,,,r,m\n",
            "no-negociables.md": "- **ALF-01** no escribir MALO\n", "evidencia.md": "# Evidencia\n"}


def escribir(carpeta, contenido):
    for rel, texto in contenido.items():
        p = Path(carpeta) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))


def commit(repo, contenido, mensaje, quitar=()):
    for rel in quitar:
        os.remove(Path(repo) / rel)
    escribir(repo, contenido)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", mensaje)
    return git(repo, "rev-parse", "HEAD")


def armar_repo(base):
    trabajo = base / "trabajo"
    trabajo.mkdir()
    git(trabajo, "init", "-q")
    ids = {"v1": commit(trabajo, {**archivos("regla v1"), "extra.py": "x = 1\n", "sub/otro.py": "y = 2\n"}, "v1")}
    git(trabajo, "tag", "v1")
    ids["v2"] = commit(trabajo, {**archivos("regla v2"), "LICENSE": "MIT\n"}, "v2")
    git(trabajo, "tag", "-a", "v2", "-m", "version 2")
    git(trabajo, "branch", "v9")
    git(trabajo, "checkout", "-q", "-b", "otros")
    for etiqueta, contenido, quitar in (("roto", archivos("roto", formato=2), ()),
                                        ("api-nueva", archivos("api", odd_ws_api=2), ()),
                                        ("incompleto", archivos("incompleto"), ("evidencia.md",)),
                                        ("beta-choca", archivos("beta", nombre="beta"), ()),
                                        ("gamma-capa", archivos("gamma", nombre="gamma", prefijo="SQL"), ()),
                                        ("delta", archivos("delta", nombre="delta", prefijo="DEL"), ())):
        ids[etiqueta] = commit(trabajo, {k: v for k, v in contenido.items() if k not in quitar}, etiqueta, quitar)
        git(trabajo, "tag", etiqueta)
        if quitar:
            escribir(trabajo, {r: archivos("x")[r] for r in quitar})
    escribir(trabajo, archivos("enlace"))
    git(trabajo, "add", "-A")
    blob = git(trabajo, "hash-object", "-w", "--stdin", entrada=b"../afuera.py")
    git(trabajo, "update-index", "--cacheinfo", "120000,%s,verificar.py" % blob)
    git(trabajo, "commit", "-q", "-m", "enlace")
    git(trabajo, "tag", "enlace")
    ids["enlace"] = git(trabajo, "rev-parse", "HEAD")
    git(base, "clone", "-q", "--bare", str(trabajo), "paquete.git")
    return str(base / "paquete.git"), ids


def armar_instancia(base):
    db = base / "db"
    db.mkdir()
    git(db, "init", "-q")
    escribir(db, {"src/Base.sql": "SELECT 1\n"})
    git(db, "add", "-A")
    git(db, "commit", "-q", "-m", "base")
    raiz = base / "inst"
    config = {"schema_version": 1, "repos": {"db": {}},
              "layers": {"sql": {"extensions": [".sql"], "repos": ["db"], "rule_prefix": "SQL"},
                         "web": {"extensions": [".cs"], "rule_prefix": "WEB"}, "docs": {"extensions": [".md"]}}}
    escribir(raiz, {"workspace.config.json": json.dumps(config), "workspace.local.json": json.dumps({"repos": {"db": {"path": str(db)}}})})
    return raiz, db


class Mundo:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="paquetes-cli-"))
        self.previo = {k: os.environ.get(k) for k in AISLAMIENTO}
        self.centinela = self.base / "centinela.txt"
        os.environ.update(GIT_CONFIG_GLOBAL=str(self.base / "gitglobal"), GIT_CONFIG_SYSTEM=str(self.base / "gitsistema"),
                          GIT_CONFIG_NOSYSTEM="1", CENTINELA_DE_LA_PRUEBA=str(self.centinela))
        self.tmp = self.base / "tmp"
        self.tmp.mkdir()
        self.fuente, self.ids = armar_repo(self.base)
        self.raiz, self.db = armar_instancia(self.base)
        return self

    def __exit__(self, *_):
        for clave, valor in self.previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(self.base, onexc=_quitar)
        if self.base.exists():
            SOBRANTES.append(str(self.base))

    def correr(self, *argv, raiz=True, cwd=None, **env):
        entorno = dict(_entorno(), TEMP=str(self.tmp), TMP=str(self.tmp), TMPDIR=str(self.tmp), PYTHONIOENCODING="utf-8", **env)
        r = subprocess.run([sys.executable, str(_RUTA), *argv, *(["--raiz", str(self.raiz)] if raiz else [])], capture_output=True,
                           env=entorno, timeout=180, cwd=str(cwd or self.base))
        return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n"), r.stderr.decode("utf-8").replace("\r\n", "\n")

    def en_proceso(self, *argv):
        salida, error = io.StringIO(), io.StringIO()
        previo, tempfile.tempdir = tempfile.tempdir, str(self.tmp)
        try:
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
                codigo = M.main([*argv, "--raiz", str(self.raiz)])
        finally:
            tempfile.tempdir = previo
        return codigo, salida.getvalue(), error.getvalue()

    def importar(self, etiqueta="v1", capa="sql", *extra):
        return self.correr("importar", self.fuente, "--etiqueta", etiqueta, "--capa", capa, *extra)

    def foto(self):
        carpeta = self.raiz / ".claude"
        return sorted((str(p.relative_to(self.raiz)).replace("\\", "/"), p.read_bytes()) for p in carpeta.rglob("*") if p.is_file()) \
            if carpeta.exists() else []

    def sin_rastros(self):
        assert list(self.tmp.iterdir()) == [], "la carpeta temporal del clon se borra: %r" % list(self.tmp.iterdir())
        assert not self.centinela.exists(), "ningún comando corre código del paquete: %r" % self.centinela.read_text()


AVISO_LOCAL = ("paquetes: aviso: la fuente es una ruta local (%s): el lock solo sirve en esta máquina; para un equipo, importá desde "
               "una URL\n")


def test_importar_en_ensayo_muestra_el_plan_y_no_escribe_nada():
    with Mundo() as w:
        codigo, out, err = w.importar("v1", "sql", "--ensayo")
        assert (codigo, err) == (0, AVISO_LOCAL % w.fuente), (codigo, out, err)
        ls = out.splitlines()
        assert ls[0] == "ensayo: no se escribe nada", ls
        assert "paquete: alfa (prefijo ALF, capa sql)" in ls and "fuente: %s" % w.fuente in ls, ls
        assert "etiqueta: v1 (commit %s)" % w.ids["v1"] in ls, ls
        assert "  verificar.py (%d bytes)" % len(VERIFICAR.replace("MENSAJE", "regla v1").encode("utf-8")) in ls, ls
        assert not any("extra.py" in l or "otro.py" in l for l in ls), "lo que no es de la lista blanca no entra en el plan"
        entrada = json.loads(ls[ls.index("entrada del lock:") + 1])
        assert list(entrada) == ["alfa"] and entrada["alfa"]["commit"] == w.ids["v1"] and entrada["alfa"]["etiqueta"] == "v1", entrada
        assert w.foto() == [], "el ensayo no escribe nada"
        w.sin_rastros()


def test_importar_copia_solo_la_lista_blanca_y_escribe_el_lock():
    with Mundo() as w:
        codigo, out, err = w.importar()
        assert (codigo, err) == (0, AVISO_LOCAL % w.fuente), (codigo, out, err)
        carpeta = w.raiz / CARPETA
        assert sorted(p.name for p in carpeta.iterdir()) == ["evidencia.md", "matriz.csv", "no-negociables.md", "odd-ws-paquete.json",
                                                              "verificar.py", "verificar.tests.py"], list(carpeta.iterdir())
        assert (carpeta / "verificar.py").read_text(encoding="utf-8") == VERIFICAR.replace("MENSAJE", "regla v1")
        lock = B.leer_lock(str(w.raiz))
        assert lock == {"alfa": B.Paquete("alfa", "sql", "ALF", w.fuente, "v1", w.ids["v1"], B.huella(str(carpeta)))}, lock
        assert (w.raiz / LOCK).read_bytes() == (json.dumps(B.datos_del_lock(lock), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        ls = out.splitlines()
        assert ls[0] == "importado: alfa (prefijo ALF, capa sql), etiqueta v1 (commit %s), en %s" % (w.ids["v1"][:12], CARPETA), ls
        assert any(l.startswith("Antes de commitear, revisá en el diff") for l in ls), ls
        w.sin_rastros()
        codigo, out, err = w.correr("importar", w.fuente, "--etiqueta", "delta", "--capa", "web")
        assert codigo == 0 and sorted(B.leer_lock(str(w.raiz))) == ["alfa", "delta"], (codigo, out, err)
        assert B.leer_lock(str(w.raiz))["alfa"] == lock["alfa"], "las demás entradas quedan como estaban"


def test_importado_el_doctor_da_ok_y_el_hook_aplica_su_regla():
    with Mundo() as w:
        assert w.importar()[0] == 0
        env = dict(_entorno(), CLAUDE_PROJECT_DIR=str(w.raiz), PYTHONIOENCODING="utf-8")
        doctor = subprocess.run([sys.executable, str(AQUI / "doctor.py")], capture_output=True, env=env, cwd=str(w.raiz), timeout=300)
        filas = [l for l in doctor.stdout.decode("utf-8").splitlines() if l.startswith("paquetes ")]
        assert len(filas) == 1 and filas[0].split()[1] == "OK", filas
        calibrar = [sys.executable, str(AQUI / "reglas.py"), "--calibrar", "sql", str(w.db / "src"), "--guardar"]
        calibrada = subprocess.run(calibrar, capture_output=True, env=env, cwd=str(w.raiz), timeout=120)
        assert calibrada.returncode == 0 and calibrada.stdout.decode("utf-8").splitlines()[-1] == "ALF-01 puede bloquear", calibrada
        escribir(w.db, {"src/Nuevo.sql": "SELECT MALO\n"})
        evento = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "session_id": "s1", "tool_input": {"file_path": str(w.db / "src" / "Nuevo.sql")}}
        hook = subprocess.run([sys.executable, str(AQUI / "verificar_capa.py"), "--plazo", "20"], input=json.dumps(evento).encode("utf-8"),
                              capture_output=True, env=env, timeout=120)
        assert hook.returncode == 2 and "[ALF-01] linea 1: regla v1" in hook.stderr.decode("utf-8"), hook
        assert w.correr("actualizar", "alfa", "--etiqueta", "v2")[0] == 0
        hook = subprocess.run([sys.executable, str(AQUI / "verificar_capa.py"), "--plazo", "20"], input=json.dumps(evento).encode("utf-8"),
                              capture_output=True, env=env, timeout=120)
        contexto = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"] if hook.returncode == 0 else hook
        assert "[ALF-01] linea 1: regla v2 (aviso: calibración vieja; para que bloquee, correr `reglas.py --calibrar sql " in contexto, \
            "otra etiqueta es otra huella en el lock: hay que recalibrar (%r)" % (contexto,)


def test_importar_rechaza_lo_que_no_es_una_etiqueta():
    with Mundo() as w:
        for etiqueta in ("nada", "v9", w.ids["v1"], "main"):
            codigo, out, err = w.importar(etiqueta)
            assert codigo == 1 and out == "" and err == "paquetes: la etiqueta %s no existe en %s\n" % (etiqueta, w.fuente), (etiqueta, codigo, out, err)
        assert w.foto() == []
        w.sin_rastros()


def test_importar_rechaza_un_paquete_invalido_sin_escribir_nada():
    casos = {"roto": "odd-ws-paquete.json no es válido: formato 2",
             "api-nueva": "pide odd_ws_api 2 y este plugin da 1",
             "incompleto": "falta evidencia.md",
             "enlace": "verificar.py es un enlace"}
    with Mundo() as w:
        for etiqueta, rastro in casos.items():
            codigo, out, err = w.importar(etiqueta)
            assert codigo == 1 and out == "" and err.startswith("paquetes: ") and rastro in err, (etiqueta, codigo, out, err)
        assert w.foto() == []
        w.sin_rastros()


def test_importar_rechaza_el_nombre_repetido_los_prefijos_que_chocan_y_la_capa_que_no_sirve():
    with Mundo() as w:
        assert w.importar()[0] == 0
        antes = w.foto()
        casos = [
            (("v2", "sql"), "paquetes: alfa ya está en %s: para cambiar su etiqueta, actualizar\n" % LOCK),
            (("beta-choca", "sql"), "paquetes: el prefijo ALF lo usan alfa y beta: cada paquete lleva el suyo\n"),
            (("gamma-capa", "web"), "paquetes: gamma: el prefijo SQL ya lo usa layers.sql.rule_prefix\n"),
            (("delta", "rust"), "paquetes: la capa rust no está declarada en workspace.config.json (capas: sql, web, docs)\n"),
            (("delta", "docs"), "paquetes: la capa docs no tiene rule_prefix en workspace.config.json: sin prefijo no tiene matriz, "
                                "y matriz.py no podría validar la del paquete\n"),
        ]
        for (etiqueta, capa), esperado in casos:
            codigo, out, err = w.importar(etiqueta, capa)
            assert (codigo, out, err) == (1, "", esperado), (etiqueta, codigo, out, err)
        assert w.foto() == antes
        escribir(w.raiz, {".claude/reglas/paquetes/delta/nota.txt": "a mano\n"})
        codigo, out, err = w.importar("delta", "web")
        assert (codigo, out, err) == (1, "", "paquetes: ya existe .claude/reglas/paquetes/delta y no está en el lock: sacala o elegí otro paquete\n"), (codigo, out, err)
        w.sin_rastros()


def test_actualizar_de_v1_a_v2_cambia_commit_etiqueta_y_huella_y_dice_que_cambio():
    with Mundo() as w:
        assert w.importar()[0] == 0
        antes = w.foto()
        codigo, out, err = w.correr("actualizar", "alfa", "--etiqueta", "v2", "--ensayo")
        assert (codigo, err) == (0, "") and out.splitlines()[0] == "ensayo: no se escribe nada", (codigo, out, err)
        assert "  cambia verificar.py" in out.splitlines() and "  nuevo LICENSE" in out.splitlines(), out
        assert w.foto() == antes, "el ensayo no escribe nada"
        codigo, out, err = w.correr("actualizar", "alfa", "--etiqueta", "v2")
        assert (codigo, err) == (0, ""), (codigo, out, err)
        ls = out.splitlines()
        assert ls[0] == "actualizado: alfa, etiqueta v1 -> v2 (commit %s -> %s)" % (w.ids["v1"][:12], w.ids["v2"][:12]), ls
        assert ls[1:3] == ["  nuevo LICENSE", "  cambia verificar.py"], ls
        assert any(l.startswith("Antes de commitear, revisá en el diff") for l in ls), ls
        carpeta = w.raiz / CARPETA
        lock = B.leer_lock(str(w.raiz))["alfa"]
        assert (lock.etiqueta, lock.commit, lock.huella) == ("v2", w.ids["v2"], B.huella(str(carpeta))), lock
        assert (carpeta / "LICENSE").read_text(encoding="utf-8") == "MIT\n" and "regla v2" in (carpeta / "verificar.py").read_text(encoding="utf-8")
        assert sorted(p.name for p in carpeta.parent.iterdir()) == ["alfa"], "no quedan carpetas a medio cambiar"
        codigo, out, err = w.correr("actualizar", "alfa", "--etiqueta", "v2")
        assert codigo == 0 and out.splitlines()[1] == "  sin cambios en los archivos", out
        w.sin_rastros()


def test_un_actualizar_que_falla_deja_el_paquete_como_estaba():
    with Mundo() as w:
        assert w.importar()[0] == 0
        antes = w.foto()
        for etiqueta, codigo_esperado, rastro in (("roto", 1, "formato 2"), ("nada", 1, "no existe"),
                                                  ("beta-choca", 1, "el manifiesto dice nombre beta y el lock alfa")):
            codigo, out, err = w.correr("actualizar", "alfa", "--etiqueta", etiqueta)
            assert codigo == codigo_esperado and out == "" and rastro in err, (etiqueta, codigo, out, err)
            assert w.foto() == antes, etiqueta
        codigo, out, err = w.correr("actualizar", "beta", "--etiqueta", "v2")
        assert (codigo, out, err) == (1, "", "paquetes: beta no está en %s\n" % LOCK), (codigo, out, err)
        original = M.paquetes.escribir_lock

        def falla(*_a, **_k):
            raise OSError("disco lleno")

        M.paquetes.escribir_lock = falla
        try:
            codigo, out, err = w.en_proceso("actualizar", "alfa", "--etiqueta", "v2")
        finally:
            M.paquetes.escribir_lock = original
        assert codigo == 2 and "disco lleno" in err, (codigo, out, err)
        assert w.foto() == antes, "la carpeta vuelve a la versión anterior si el lock no se pudo escribir"
        assert sorted(p.name for p in (w.raiz / CARPETA).parent.iterdir()) == ["alfa"], list((w.raiz / CARPETA).parent.iterdir())
        w.sin_rastros()


def test_quitar_borra_la_carpeta_la_entrada_y_el_lock_vacio():
    with Mundo() as w:
        assert w.importar()[0] == 0
        assert w.correr("importar", w.fuente, "--etiqueta", "delta", "--capa", "web")[0] == 0
        codigo, out, err = w.correr("quitar", "alfa")
        assert (codigo, err) == (0, "") and out == "quitado: alfa (%s y su entrada en el lock)\n" % CARPETA, (codigo, out, err)
        assert not (w.raiz / CARPETA).exists() and list(B.leer_lock(str(w.raiz))) == ["delta"]
        codigo, out, err = w.correr("quitar", "delta")
        assert codigo == 0 and out.splitlines() == ["quitado: delta (.claude/reglas/paquetes/delta y su entrada en el lock)",
                                                    "el lock quedó vacío: se borró %s" % LOCK], out
        assert not (w.raiz / LOCK).exists() and B.leer_lock(str(w.raiz)) is None
        codigo, out, err = w.correr("quitar", "delta")
        assert (codigo, out, err) == (1, "", "paquetes: delta no está en %s\n" % LOCK), (codigo, out, err)
        w.sin_rastros()


def test_listar_muestra_cada_paquete_y_si_su_huella_coincide():
    with Mundo() as w:
        codigo, out, err = w.correr("listar")
        assert (codigo, out, err) == (0, "no hay paquetes: no existe %s\n" % LOCK, ""), (codigo, out, err)
        assert w.importar()[0] == 0
        assert w.correr("importar", w.fuente, "--etiqueta", "delta", "--capa", "web")[0] == 0
        escribir(w.raiz, {".claude/reglas/paquetes/delta/verificar.py": "editado = 1\n"})
        codigo, out, err = w.correr("listar")
        assert (codigo, err) == (0, ""), (codigo, out, err)
        assert out.splitlines() == [
            "alfa  capa sql  prefijo ALF  etiqueta v1  commit %s  huella al día" % w.ids["v1"][:12],
            "delta  capa web  prefijo DEL  etiqueta delta  commit %s  huella no coincide" % w.ids["delta"][:12],
        ], out
        shutil.rmtree(w.raiz / ".claude" / "reglas" / "paquetes" / "delta")
        assert w.correr("listar")[1].splitlines()[1].endswith("huella sin carpeta")
        w.sin_rastros()


def test_errores_de_entorno_salen_con_2():
    with Mundo() as w:
        codigo, out, err = w.correr("importar", str(w.base / "no-existe.git"), "--etiqueta", "v1", "--capa", "sql")
        assert codigo == 2 and out == "" and err.startswith("paquetes: git ls-remote no pudo leer "), (codigo, out, err)
        codigo, out, err = w.correr("importar", w.fuente, "--etiqueta", "v1", "--capa", "sql", PATH="")
        assert (codigo, out) == (2, "") and err == "paquetes: git no está instalado o no está en el PATH\n", (codigo, out, err)
        escribir(w.raiz, {LOCK: "{roto"})
        for argv in (("importar", w.fuente, "--etiqueta", "v1", "--capa", "sql"), ("actualizar", "alfa", "--etiqueta", "v1"),
                     ("quitar", "alfa"), ("listar",)):
            codigo, out, err = w.correr(*argv)
            assert codigo == 2 and out == "" and err.startswith("paquetes: %s roto: " % LOCK), (argv, codigo, out, err)
        os.remove(w.raiz / LOCK)
        os.remove(w.raiz / "workspace.config.json")
        codigo, out, err = w.correr("listar")
        assert codigo == 2 and "workspace.config.json" in err, (codigo, out, err)
        codigo, out, err = w.correr("listar", raiz=False)
        assert codigo == 2 and "workspace.config.json" in err, (codigo, out, err)
        w.sin_rastros()


def test_una_fuente_local_se_guarda_absoluta_y_avisa_que_solo_sirve_en_esta_maquina():
    with Mundo() as w:
        codigo, out, err = w.correr("importar", "paquete.git", "--etiqueta", "v1", "--capa", "sql", cwd=w.base)
        guardada = B.leer_lock(str(w.raiz))["alfa"].fuente
        assert (codigo, err) == (0, AVISO_LOCAL % guardada), (codigo, out, err)
        assert os.path.isabs(guardada) and guardada == os.path.normpath(guardada), guardada
        assert os.path.samefile(guardada, w.base / "paquete.git"), "la ruta guardada es la del repo, aunque el sistema la escriba con un enlace resuelto (/var y /private/var en macOS)"
        codigo, out, err = w.correr("actualizar", "alfa", "--etiqueta", "v2", cwd=w.raiz)
        assert (codigo, err) == (0, "") and B.leer_lock(str(w.raiz))["alfa"].etiqueta == "v2", (codigo, out, err)
        w.sin_rastros()


def _junction(destino, enlace):
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(destino), str(enlace))
    else:
        os.symlink(str(destino), str(enlace), target_is_directory=True)


def test_no_escribe_a_traves_de_un_enlace_y_deja_todo_como_estaba():
    with Mundo() as w:
        afuera = w.base / "afuera"
        afuera.mkdir()
        (w.raiz / ".claude" / "reglas").mkdir(parents=True)
        _junction(afuera, w.raiz / ".claude" / "reglas" / "paquetes")
        for extra in ((), ("--ensayo",)):
            codigo, out, err = w.importar("v1", "sql", *extra)
            assert (codigo, out, err) == (1, "", "paquetes: .claude/reglas/paquetes es un enlace o apunta fuera de la instancia: el "
                                                 "paquete no se escribe ahí\n"), (extra, codigo, out, err)
        assert list(afuera.iterdir()) == [] and not (w.raiz / LOCK).exists()
        w.sin_rastros()
    with Mundo() as w:
        assert w.importar()[0] == 0
        real = w.base / "alfa-real"
        shutil.move(str(w.raiz / CARPETA), str(real))
        _junction(real, w.raiz / CARPETA)
        lock = (w.raiz / LOCK).read_bytes()
        afuera = sorted((p.name, p.read_bytes()) for p in real.iterdir())
        codigo, out, err = w.correr("actualizar", "alfa", "--etiqueta", "v2")
        assert (codigo, out, err) == (1, "", "paquetes: %s es un enlace o apunta fuera de la instancia: el paquete no se escribe ahí\n"
                                      % CARPETA), (codigo, out, err)
        assert (w.raiz / LOCK).read_bytes() == lock and sorted((p.name, p.read_bytes()) for p in real.iterdir()) == afuera
        w.sin_rastros()


def test_una_fuente_con_credenciales_se_rechaza_sin_mostrarlas():
    mensaje = ("paquetes: la fuente trae usuario o contraseña en la URL y quedaría en el lock, que se commitea: configurá las "
               "credenciales en git (un credential helper o ssh) y pasá la URL sin ellas\n")
    with Mundo() as w:
        for fuente in ("https://usuario:SECRETO123@example.invalid/org/reglas.git", "https://SECRETO123@example.invalid/r.git",
                       "ssh://git:SECRETO123@example.invalid/r.git", "ssh://git@example.invalid/r.git"):
            codigo, out, err = w.correr("importar", fuente, "--etiqueta", "v1", "--capa", "sql")
            assert (codigo, out, err) == (1, "", mensaje), (fuente, codigo, out, err)
        assert w.foto() == []
        w.sin_rastros()


def test_los_protocolos_que_no_son_de_la_lista_fallan_rapido():
    with Mundo() as w:
        previo, M.PLAZO_DE_GIT = M.PLAZO_DE_GIT, 8
        try:
            for fuente in ("fd::0", "ext::git --version", "nadie::x"):
                inicio = time.monotonic()
                codigo, out, err = w.en_proceso("importar", fuente, "--etiqueta", "v1", "--capa", "sql")
                duracion = time.monotonic() - inicio
                assert codigo == 2 and out == "" and err.startswith("paquetes: git ls-remote no pudo leer "), (fuente, codigo, out, err)
                assert duracion < 5, (fuente, duracion)
        finally:
            M.PLAZO_DE_GIT = previo
        assert w.foto() == []
        w.sin_rastros()


def test_git_corre_sin_preguntar_y_solo_con_los_protocolos_de_la_lista():
    with Mundo() as w:
        llamadas, original = [], M.subprocess.run

        def espia(args, **kw):
            llamadas.append((list(args), dict(kw.get("env") or {})))
            return original(args, **kw)

        M.subprocess.run = espia
        try:
            codigo, out, err = w.en_proceso("importar", w.fuente, "--etiqueta", "v1", "--capa", "sql", "--ensayo")
        finally:
            M.subprocess.run = original
        assert codigo == 0 and len(llamadas) >= 3, (codigo, out, err, llamadas)
        for args, env in llamadas:
            assert args[0] == "git", args
            for valor in ("protocol.allow=never", "protocol.file.allow=always", "protocol.https.allow=always", "protocol.ssh.allow=always",
                          "protocol.git.allow=always", "protocol.ext.allow=never"):
                assert valor in args and args[args.index(valor) - 1] == "-c", (valor, args)
            assert (env.get("GIT_PROTOCOL_FROM_USER"), env.get("GCM_INTERACTIVE"), env.get("GIT_TERMINAL_PROMPT")) == ("0", "never", "0"), env
        w.sin_rastros()


def test_uso_y_ayuda():
    with Mundo() as w:
        for argv in ((), ("otro",), ("importar", w.fuente), ("importar", w.fuente, "--etiqueta", "v1"), ("actualizar", "alfa"),
                     ("quitar",)):
            codigo, out, err = w.correr(*argv)
            assert codigo == 2 and out == "" and err, (argv, codigo, out, err)
        codigo, out, err = w.correr("--help", raiz=False)
        assert codigo == 0 and all(c in out for c in ("importar", "actualizar", "quitar", "listar")), out
        codigo, out, err = w.correr("importar", "--help", raiz=False)
        assert codigo == 0 and "--ensayo" in out and "--etiqueta" in out and "--capa" in out, out


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
