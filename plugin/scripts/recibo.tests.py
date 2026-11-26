import contextlib
import hashlib
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
_RUTA = AQUI / "recibo.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []


def _cargar():
    spec = importlib.util.spec_from_file_location("recibo", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


M = _cargar() if _RUTA.exists() else None


def _quitar(func, ruta, _exc):
    try:
        os.chmod(ruta, stat.S_IWRITE)
        func(ruta)
    except Exception:
        pass


@contextlib.contextmanager
def temporal():
    raiz = Path(os.path.realpath(tempfile.mkdtemp(prefix="recibo-test-")))
    try:
        yield raiz
    finally:
        shutil.rmtree(raiz, onexc=_quitar)
        if raiz.exists():
            SOBRANTES.append(str(raiz))


AISLAMIENTO_GIT = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in AISLAMIENTO_GIT}


@contextlib.contextmanager
def git_aislado(config=""):
    carpeta = Path(os.path.realpath(tempfile.mkdtemp(prefix="recibo-git-")))
    (carpeta / "global").write_text(config, encoding="utf-8")
    (carpeta / "sistema").write_text("", encoding="utf-8")
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
        shutil.rmtree(carpeta, onexc=_quitar)
        if carpeta.exists():
            SOBRANTES.append(str(carpeta))


def _git(cwd, *args):
    r = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
         "-c", "core.autocrlf=false", *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=_entorno_sin_git())
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def escribir(raiz, archivos):
    for ruta, texto in archivos.items():
        p = Path(raiz) / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)


def commitear(repo, archivos, mensaje="c"):
    escribir(repo, archivos)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", mensaje)
    return _git(repo, "rev-parse", "HEAD")


def repo_con_principal(raiz, archivos, nombre="repo", rama="main"):
    repo = Path(raiz) / nombre
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    base = commitear(repo, archivos, "inicial")
    _git(repo, "update-ref", "refs/remotes/origin/%s" % rama, base)
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/%s" % rama)
    return repo, base


def indice(repo):
    return _git(repo, "ls-files", "--stage")


def correr(argv):
    salida, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
        try:
            codigo = M.main(argv)
        except SystemExit as exc:
            codigo = exc.code if isinstance(exc.code, int) else 2
    return codigo, salida.getvalue(), error.getvalue()


ARCHIVOS = {"a.sql": "linea 1\nlinea 2\nlinea 3\n", "b.cs": "class B {}\n", "c.txt": "ajeno\n"}


def calc(repo, base, rutas):
    return M.calcular(str(repo), base, rutas)


def test_hash_dos_corridas_iguales():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n", "nuevo.sql": "nuevo\n"})
        r1 = calc(repo, base, ["a.sql", "nuevo.sql"])
        r2 = calc(repo, base, ["nuevo.sql", "a.sql"])
        assert r1["sha256"] == r2["sha256"], (r1, r2)
        assert len(r1["sha256"]) == 64
        assert r1["archivos"] == ["a.sql", "nuevo.sql"]
        assert r1["base"] == base


def test_hash_cambiar_un_byte_lo_cambia():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n"})
        antes = calc(repo, base, ["a.sql"])
        escribir(repo, {"a.sql": "linea 1\nCAMBIp\nlinea 3\n"})
        despues = calc(repo, base, ["a.sql"])
        assert antes["sha256"] != despues["sha256"]
        assert antes["sha256_por_archivo"]["a.sql"] != despues["sha256_por_archivo"]["a.sql"]


def test_hash_archivo_fuera_de_la_lista_no_lo_cambia():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n"})
        antes = calc(repo, base, ["a.sql"])
        escribir(repo, {"c.txt": "ajeno tocado\n", "ambiente.config": "ip=1.2.3.4\n"})
        despues = calc(repo, base, ["a.sql"])
        assert antes["sha256"] == despues["sha256"]
        assert despues["archivos"] == ["a.sql"]


def test_hash_cubre_archivo_nuevo_sin_trackear():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"nuevo.sql": "uno\n"})
        r1 = calc(repo, base, ["nuevo.sql"])
        escribir(repo, {"nuevo.sql": "uno\ndos\n"})
        r2 = calc(repo, base, ["nuevo.sql"])
        assert r1["sha256"] != r2["sha256"]
        vacio = hashlib.sha256(b"").hexdigest()
        assert r1["sha256"] != vacio
        assert r1["sha256_por_archivo"]["nuevo.sql"] != vacio


def test_hash_no_toca_el_indice():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n", "nuevo.sql": "nuevo\n"})
        antes = indice(repo)
        calc(repo, base, ["a.sql", "nuevo.sql", "b.cs"])
        assert indice(repo) == antes
        assert "nuevo.sql" not in indice(repo)
        assert "intent-to-add" not in _git(repo, "status", "--porcelain=v1", "--ignored").lower()


def test_hash_archivo_borrado_del_working_tree_cuenta():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        (repo / "b.cs").unlink()
        r = calc(repo, base, ["b.cs"])
        assert r["sha256_por_archivo"]["b.cs"] != hashlib.sha256(b"").hexdigest()


def test_hash_cubre_cambios_commiteados_y_sin_commitear():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        commitear(repo, {"a.sql": "linea 1\nCOMMITEADO\nlinea 3\n"})
        r1 = calc(repo, base, ["a.sql"])
        escribir(repo, {"a.sql": "linea 1\nCOMMITEADO\nSUCIO\n"})
        r2 = calc(repo, base, ["a.sql"])
        assert r1["sha256"] != hashlib.sha256(b"").hexdigest()
        assert r1["sha256"] != r2["sha256"]


def test_hash_no_reescribe_la_cache_de_stat_del_indice():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        _git(repo, "update-index", "--refresh")
        time.sleep(1.2)
        os.utime(repo / "a.sql", None)
        idx = repo / ".git" / "index"
        antes = idx.read_bytes()
        r = calc(repo, base, ["a.sql", "b.cs"])
        assert idx.read_bytes() == antes, "el .git/index cambio con un archivo stat-sucio"
        assert r["sha256_por_archivo"]["a.sql"] == hashlib.sha256(b"").hexdigest()


def test_hash_inmune_a_la_config_del_usuario_y_al_entorno():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "línea ñ\nCAMBIO\n", "nuevo.sql": "ñ\n"})
        limpio = calc(repo, base, ["a.sql", "nuevo.sql"])["sha256"]
        _git(repo, "config", "diff.noprefix", "true")
        _git(repo, "config", "diff.mnemonicPrefix", "true")
        _git(repo, "config", "diff.renames", "copies")
        _git(repo, "config", "diff.algorithm", "patience")
        _git(repo, "config", "core.quotepath", "true")
        _git(repo, "config", "diff.external", "false")
        previo = dict(os.environ)
        os.environ["GIT_INDEX_FILE"] = str(Path(t) / "no-existe-indice")
        os.environ["GIT_DIR"] = str(Path(t) / "no-existe-dir")
        os.environ["GIT_EXTERNAL_DIFF"] = "false"
        os.environ["GIT_DIFF_OPTS"] = "-u0"
        try:
            sucio = calc(repo, base, ["a.sql", "nuevo.sql"])["sha256"]
        finally:
            os.environ.clear()
            os.environ.update(previo)
        assert limpio == sucio


def test_hash_ruta_con_acentos_y_espacios():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"carpeta con espacio/ñandú.sql": "x\n"})
        r = calc(repo, base, ["carpeta con espacio/ñandú.sql"])
        assert r["archivos"] == ["carpeta con espacio/ñandú.sql"]
        assert r["sha256_por_archivo"]["carpeta con espacio/ñandú.sql"] != hashlib.sha256(b"").hexdigest()


def test_calcular_ruta_inexistente_es_error_de_uso():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        try:
            calc(repo, base, ["no-existe.sql"])
        except M.ErrorUso as exc:
            assert "no-existe.sql" in str(exc)
        else:
            raise AssertionError("debia lanzar ErrorUso")


def test_calcular_carpeta_es_error_de_uso():
    with temporal() as t:
        repo, base = repo_con_principal(t, {"d/a.sql": "x\n"})
        try:
            calc(repo, base, ["d"])
        except M.ErrorUso as exc:
            assert "carpeta" in str(exc)
        else:
            raise AssertionError("debia lanzar ErrorUso")


def test_calcular_ruta_fuera_del_repo_es_error_de_uso():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        try:
            calc(repo, base, ["../otro.sql"])
        except M.ErrorUso:
            pass
        else:
            raise AssertionError("debia lanzar ErrorUso")


def test_base_por_defecto_es_el_merge_base_con_la_rama_por_defecto_del_remoto():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        commitear(repo, {"a.sql": "rama\n"})
        assert M.resolver_base(str(repo)) == base
        _git(repo, "checkout", "-q", "--detach", base)
        principal2 = commitear(repo, {"z.sql": "la principal avanza\n"})
        _git(repo, "update-ref", "refs/remotes/origin/main", principal2)
        _git(repo, "checkout", "-q", "-")
        assert M.resolver_base(str(repo)) == base, "merge-base, no la punta de la rama por defecto"


def test_base_por_defecto_sigue_a_origin_head_aunque_la_rama_se_llame_master():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS, rama="master")
        commitear(repo, {"a.sql": "rama\n"})
        otra = commitear(repo, {"a.sql": "otra\n"})
        _git(repo, "update-ref", "refs/remotes/origin/main", otra)
        assert M.resolver_base(str(repo)) == base


def test_base_sin_origin_head_es_error_de_entorno_con_el_arreglo():
    with temporal() as t:
        repo = Path(t) / "r"
        repo.mkdir()
        _git(repo, "init", "-q")
        base = commitear(repo, ARCHIVOS)
        _git(repo, "update-ref", "refs/remotes/origin/main", base)
        try:
            M.resolver_base(str(repo))
        except M.ErrorEntorno as exc:
            assert "origin/HEAD" in str(exc)
            assert "git remote set-head origin -a" in str(exc)
            assert "#BASE" in str(exc)
        else:
            raise AssertionError("debia lanzar ErrorEntorno")


def test_base_con_origin_head_hacia_una_rama_inexistente_es_error_de_entorno():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/no-existe")
        try:
            M.resolver_base(str(repo))
        except M.ErrorEntorno as exc:
            assert "origin/no-existe" in str(exc)
        else:
            raise AssertionError("debia lanzar ErrorEntorno")


def args_write(ticket, repos, archivos, extra=()):
    a = ["--write", "--ticket", str(ticket)]
    if "--modo" not in extra:
        a += ["--modo", "rapido"]
    for r in repos:
        a += ["--repo", str(r)]
    for f in archivos:
        a += ["--archivo", str(f)]
    return a + list(extra)


def test_write_crea_recibo_en_revision_fecha_con_los_campos():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n", "nuevo.sql": "n\n"})
        ticket = Path(t) / "T-1-x"
        ticket.mkdir()
        antes = indice(repo)
        codigo, salida, error = correr(args_write(
            ticket, [repo], [repo / "a.sql", repo / "nuevo.sql"],
            ["--fecha", "2026-10-21", "--modo", "completo", "--reviewer", "reviewer-diseno",
             "--reviewer", "reviewer-sql", "--verificacion", "python x.tests.py: 12/12",
             "--estado", "limpio"]))
        assert codigo == 0, (salida, error)
        archivo = ticket / "revision" / "2026-10-21-completo" / "recibo.json"
        assert archivo.is_file()
        assert str(archivo).replace("\\", "/") in salida.replace("\\", "/")
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        assert datos["version"] == 1 and datos["fecha"] == "2026-10-21"
        assert datos["ticket"] == "T-1-x" and "pbi" not in datos
        assert len(datos["repos"]) == 1
        r = datos["repos"][0]
        assert r["ruta"] == str(repo).replace("\\", "/")
        assert r["base"] == base
        assert r["archivos"] == ["a.sql", "nuevo.sql"]
        assert r["sha256"] == calc(repo, base, ["a.sql", "nuevo.sql"])["sha256"]
        assert r["modo"] == "completo"
        assert r["reviewers"] == ["reviewer-diseno", "reviewer-sql"]
        assert r["verificacion"] == ["python x.tests.py: 12/12"]
        assert r["estado"] == "limpio"
        assert indice(repo) == antes


def test_write_el_recibo_es_utf8_sin_bom_con_lf():
    with temporal() as t:
        repo, pbi, recibo = preparar_recibo(t, ["--verificacion", "ñandú → ok"])
        crudo = recibo.read_bytes()
        assert not crudo.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" not in crudo and crudo.endswith(b"}\n")
        assert "ñandú → ok".encode("utf-8") in crudo


def test_write_dos_repos_una_entrada_por_repo_en_el_mismo_archivo():
    with temporal() as t:
        r1, _ = repo_con_principal(t, ARCHIVOS, "uno")
        r2, _ = repo_con_principal(t, ARCHIVOS, "dos")
        escribir(r1, {"a.sql": "x\n"})
        escribir(r2, {"b.cs": "class B { int x; }\n"})
        ticket = Path(t) / "T-2-y"
        ticket.mkdir()
        codigo, salida, error = correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"],
                                                   ["--fecha", "2026-10-21"]))
        assert codigo == 0, (salida, error)
        datos = json.loads((ticket / "revision" / "2026-10-21-rapido" / "recibo.json").read_text(encoding="utf-8"))
        assert [r["ruta"] for r in datos["repos"]] == [str(r1).replace("\\", "/"), str(r2).replace("\\", "/")]
        assert datos["repos"][0]["archivos"] == ["a.sql"] and datos["repos"][1]["archivos"] == ["b.cs"]
        assert datos["repos"][0]["estado"] == "pendiente"
        assert datos["repos"][0]["modo"] == "rapido"


def test_write_repo_con_base_explicita():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        medio = commitear(repo, {"a.sql": "medio\n"})
        escribir(repo, {"a.sql": "final\n"})
        ticket = Path(t) / "T-3-z"
        ticket.mkdir()
        codigo, _, error = correr(args_write(ticket, ["%s#%s" % (repo, medio)], [repo / "a.sql"],
                                              ["--fecha", "2026-10-21"]))
        assert codigo == 0, error
        datos = json.loads((ticket / "revision" / "2026-10-21-rapido" / "recibo.json").read_text(encoding="utf-8"))
        assert datos["repos"][0]["base"] == medio
        assert datos["repos"][0]["sha256"] == calc(repo, medio, ["a.sql"])["sha256"]


def test_write_base_explicita_no_necesita_origin_head():
    with temporal() as t:
        repo = Path(t) / "r"
        repo.mkdir()
        _git(repo, "init", "-q")
        base = commitear(repo, ARCHIVOS)
        escribir(repo, {"a.sql": "cambio\n"})
        ticket = Path(t) / "T-4-b"
        ticket.mkdir()
        codigo, _, error = correr(args_write(ticket, ["%s#%s" % (repo, base)], [repo / "a.sql"], ["--fecha", "2026-10-21"]))
        assert codigo == 0, error


def test_write_archivo_relativo_con_varios_repos_es_error_de_uso():
    with temporal() as t:
        r1, _ = repo_con_principal(t, ARCHIVOS, "uno")
        r2, _ = repo_con_principal(t, ARCHIVOS, "dos")
        ticket = Path(t) / "T-4-w"
        ticket.mkdir()
        codigo, _, error = correr(args_write(ticket, [r1, r2], ["a.sql"]))
        assert codigo == 2 and "a.sql" in error
        assert not (ticket / "revision").exists()


def test_write_archivo_que_no_es_de_ningun_repo_es_error_de_uso():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-5-v"
        ticket.mkdir()
        ajeno = Path(t) / "suelto.sql"
        ajeno.write_text("x", encoding="utf-8")
        codigo, _, error = correr(args_write(ticket, [repo], [ajeno]))
        assert codigo == 2 and "suelto.sql" in error
        assert not (ticket / "revision").exists()


def test_write_sin_archivos_es_error_de_uso():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-6-u"
        ticket.mkdir()
        codigo, _, error = correr(args_write(ticket, [repo], []))
        assert codigo == 2 and error


def test_write_un_repo_sin_archivos_es_error_de_uso():
    with temporal() as t:
        r1, _ = repo_con_principal(t, ARCHIVOS, "uno")
        r2, _ = repo_con_principal(t, ARCHIVOS, "dos")
        ticket = Path(t) / "T-7-t"
        ticket.mkdir()
        codigo, _, error = correr(args_write(ticket, [r1, r2], [r1 / "a.sql"]))
        assert codigo == 2 and "dos" in error


def test_write_carpeta_del_ticket_inexistente_es_error_de_uso():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        codigo, _, error = correr(args_write(Path(t) / "no-existe", [repo], [repo / "a.sql"]))
        assert codigo == 2 and error


def test_write_modo_invalido_es_error_de_uso():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-8-s"
        ticket.mkdir()
        codigo, _, _ = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--modo", "express"]))
        assert codigo == 2


def test_write_sin_ticket_es_error_de_uso():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        codigo, salida, error = correr(["--write", "--modo", "rapido", "--repo", str(repo), "--archivo", str(repo / "a.sql")])
        assert codigo == 2 and salida == "" and "--ticket" in error, error


def test_fecha_solo_acepta_aaaa_mm_dd_valido():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-11-f"
        ticket.mkdir()
        for mala in ("../", "..\\x", "..", "2026-10-21/../x", "2026-13-01", "2026-02-30", "26-10-21", "20261021",
                     "2026-10-21 ", "", "hoy", "2026-10-21-rapido", "/tmp"):
            antes = sorted(str(p) for p in Path(t).rglob("*"))
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", mala]))
            assert codigo not in (0, None), (mala, salida, error)
            assert error, mala
            assert sorted(str(p) for p in Path(t).rglob("*")) == antes, "escribio algo con --fecha %r" % mala
        assert not (ticket / "revision").exists()
        codigo, _, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-02-28"]))
        assert codigo == 0, error
        assert (ticket / "revision" / "2026-02-28-rapido" / "recibo.json").is_file()


def test_write_exige_el_modo_y_lo_pone_en_la_carpeta():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-12-m"
        ticket.mkdir()
        base = ["--write", "--ticket", str(ticket), "--repo", str(repo), "--archivo", str(repo / "a.sql"), "--fecha", "2026-10-21"]
        codigo, _, error = correr(base)
        assert codigo == 2 and "modo" in error, (codigo, error)
        assert not (ticket / "revision").exists()
        for invalido in ("express", "1"):
            assert correr(base + ["--modo", invalido])[0] not in (0, None)
        assert not (ticket / "revision").exists()
        assert correr(base + ["--modo", "completo"])[0] == 0
        assert (ticket / "revision" / "2026-10-21-completo" / "recibo.json").is_file()
        assert not (ticket / "revision" / "2026-10-21").exists()


def test_check_del_ticket_toma_el_mas_reciente_entre_los_modos():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        viejo = json.loads(recibo.read_text(encoding="utf-8"))
        viejo["repos"][0]["sha256"] = "0" * 64
        completo = ticket / "revision" / "2026-10-22-completo"
        completo.mkdir()
        (completo / "recibo.json").write_text(json.dumps(viejo), encoding="utf-8")
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert codigo == 1 and "2026-10-22-completo" in salida.replace("\\", "/")
        codigo, salida, _ = correr(["--check", str(ticket), "--modo", "rapido"])
        assert codigo == 0 and "2026-10-21-rapido" in salida.replace("\\", "/")
        codigo, _, error = correr(["--check", str(ticket), "--modo", "completo"])
        assert codigo == 1
        misma_fecha = ticket / "revision" / "2026-10-22-rapido"
        misma_fecha.mkdir()
        (misma_fecha / "recibo.json").write_text(recibo.read_text(encoding="utf-8"), encoding="utf-8")
        assert correr(["--check", str(ticket)])[0] == 1, "a igual fecha gana completo"
        codigo, salida, _ = correr(["--check", str(ticket), "--recibo", str(recibo)])
        assert codigo == 0 and "2026-10-21-rapido" in salida.replace("\\", "/"), "--recibo chequea uno puntual"
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert "2026-10-22-completo" in salida.replace("\\", "/"), "imprime el recibo que chequeo"


def test_check_del_ticket_ignora_carpetas_que_no_son_fecha_modo():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        ajena = ticket / "revision" / "2026-10-30"
        ajena.mkdir()
        (ajena / "recibo.json").write_text(recibo.read_text(encoding="utf-8").replace("2026-10-21", "2026-10-30"), encoding="utf-8")
        otra = ticket / "revision" / "zzzz-rapido"
        otra.mkdir()
        (otra / "recibo.json").write_text("{}", encoding="utf-8")
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert codigo == 0 and "2026-10-21-rapido" in salida.replace("\\", "/"), salida


def test_modo_0_se_escribe_y_se_encuentra():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-13-z"
        ticket.mkdir()
        base = ["--write", "--ticket", str(ticket), "--repo", str(repo), "--archivo", str(repo / "a.sql"), "--fecha", "2026-10-21"]
        codigo, _, error = correr(base + ["--modo", "0"])
        assert codigo == 0, error
        recibo = ticket / "revision" / "2026-10-21-0" / "recibo.json"
        assert recibo.is_file()
        assert json.loads(recibo.read_text(encoding="utf-8"))["repos"][0]["modo"] == "0"
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert codigo == 0 and "2026-10-21-0" in salida.replace("\\", "/"), salida
        codigo, salida, _ = correr(["--check", str(ticket), "--modo", "0"])
        assert codigo == 0
        assert correr(["--check", str(ticket), "--modo", "rapido"])[0] == 2
        assert correr(base + ["--modo", "completo"])[0] == 0
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert "2026-10-21-completo" in salida.replace("\\", "/"), "a igual fecha gana completo sobre 0"


def test_write_sin_origin_head_es_error_de_entorno():
    with temporal() as t:
        repo = Path(t) / "r"
        repo.mkdir()
        _git(repo, "init", "-q")
        commitear(repo, ARCHIVOS)
        ticket = Path(t) / "T-9-r"
        ticket.mkdir()
        codigo, _, error = correr(args_write(ticket, [repo], [repo / "a.sql"]))
        assert codigo == 2 and "origin/HEAD" in error
        assert not (ticket / "revision").exists()


def preparar_recibo(t, extra=()):
    repo, _ = repo_con_principal(t, ARCHIVOS)
    escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n", "nuevo.sql": "n\n"})
    ticket = Path(t) / "T-10-q"
    ticket.mkdir()
    codigo, _, error = correr(args_write(ticket, [repo], [repo / "a.sql", repo / "nuevo.sql"],
                                          ["--fecha", "2026-10-21", *extra]))
    assert codigo == 0, error
    return repo, ticket, ticket / "revision" / "2026-10-21-rapido" / "recibo.json"


def test_check_vale_si_nada_cambio():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        antes = indice(repo)
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0, (salida, error)
        assert "vale" in salida.lower()
        assert indice(repo) == antes


def test_check_no_depende_de_origin_head():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        _git(repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0, (salida, error)


def test_check_un_byte_cambiado_no_vale_y_nombra_repo_y_archivo():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        escribir(repo, {"nuevo.sql": "m\n"})
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 1, (salida, error)
        texto = (salida + error).replace("\\", "/")
        assert str(repo).replace("\\", "/") in texto
        assert "nuevo.sql" in texto
        assert "a.sql" not in texto.replace("nuevo.sql", "")


def test_check_archivo_fuera_de_la_lista_no_invalida():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        escribir(repo, {"c.txt": "ajeno tocado\n", "ambiente.config": "ip=1\n"})
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0, (salida, error)


def test_check_acepta_la_carpeta_del_ticket_y_la_de_la_revision():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        assert correr(["--check", str(ticket)])[0] == 0
        assert correr(["--check", str(recibo.parent)])[0] == 0


def test_check_de_la_carpeta_del_ticket_toma_la_revision_mas_reciente():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        viejo = json.loads(recibo.read_text(encoding="utf-8"))
        viejo["repos"][0]["sha256"] = "0" * 64
        carpeta = ticket / "revision" / "2026-10-01-completo"
        carpeta.mkdir()
        (carpeta / "recibo.json").write_text(json.dumps(viejo), encoding="utf-8")
        assert correr(["--check", str(ticket)])[0] == 0
        assert correr(["--check", str(carpeta / "recibo.json")])[0] == 1


def test_check_con_recibo_de_otro_modo_es_error_de_uso():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        codigo, salida, error = correr(["--check", str(ticket), "--recibo", str(recibo), "--modo", "completo"])
        assert codigo == 2 and salida == "", (codigo, salida, error)
        assert "completo" in error and "rapido" in error, error
        codigo, salida, error = correr(["--check", str(ticket), "--recibo", str(recibo), "--modo", "rapido"])
        assert codigo == 0, (salida, error)


def test_check_de_carpeta_rapido_con_modo_completo_es_error_de_uso():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        codigo, salida, error = correr(["--check", str(recibo.parent), "--modo", "completo"])
        assert codigo == 2 and salida == "", (codigo, salida, error)
        assert "completo" in error and "rapido" in error, error
        assert correr(["--check", str(recibo.parent), "--modo", "rapido"])[0] == 0


def test_write_con_recibo_es_error_de_uso():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n"})
        ticket = Path(t) / "T-10-q"
        ticket.mkdir()
        extra = ["--fecha", "2026-10-21", "--recibo", str(Path(t) / "otro.json")]
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], extra))
        assert codigo == 2 and salida == "", (codigo, salida, error)
        assert "--recibo" in error, error
        assert not (ticket / "revision").exists()


def test_carpeta_vieja_sin_modo_se_ignora_pero_avisa_en_stderr():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        vieja = ticket / "revision" / "2026-10-30"
        vieja.mkdir()
        (vieja / "recibo.json").write_text(recibo.read_text(encoding="utf-8"), encoding="utf-8")
        codigo, salida, error = correr(["--check", str(ticket)])
        assert codigo == 0 and "2026-10-21-rapido" in salida.replace("\\", "/"), (salida, error)
        assert "2026-10-30" in error.replace("\\", "/") and "recibo.json" in error, error
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0 and error == "", error


def test_sin_carpetas_viejas_no_avisa():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        codigo, salida, error = correr(["--check", str(ticket)])
        assert codigo == 0 and error == "", (salida, error)


def test_check_recibo_inexistente_es_error_de_uso():
    with temporal() as t:
        codigo, _, error = correr(["--check", str(Path(t) / "nada" / "recibo.json")])
        assert codigo == 2 and error


def test_check_recibo_corrupto_es_error_de_uso():
    with temporal() as t:
        archivo = Path(t) / "recibo.json"
        archivo.write_text("{no es json", encoding="utf-8")
        codigo, _, error = correr(["--check", str(archivo)])
        assert codigo == 2 and error


def test_check_recibo_de_otra_version_es_error_de_uso():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        datos = json.loads(recibo.read_text(encoding="utf-8"))
        datos["version"] = 2
        recibo.write_text(json.dumps(datos), encoding="utf-8")
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 2 and "version" in error, error


def test_check_repo_que_ya_no_existe_es_error_de_entorno():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        shutil.rmtree(repo, onexc=_quitar)
        codigo, _, error = correr(["--check", str(recibo)])
        assert codigo == 2 and error


def test_check_base_que_ya_no_existe_es_error_de_entorno():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        datos = json.loads(recibo.read_text(encoding="utf-8"))
        datos["repos"][0]["base"] = "f" * 40
        recibo.write_text(json.dumps(datos), encoding="utf-8")
        codigo, _, error = correr(["--check", str(recibo)])
        assert codigo == 2 and error


def test_check_archivo_borrado_despues_del_recibo_no_vale():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        (repo / "nuevo.sql").unlink()
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 1 and "nuevo.sql" in (salida + error)


def test_check_con_el_entorno_git_contaminado_sigue_valiendo():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        previo = dict(os.environ)
        os.environ["GIT_INDEX_FILE"] = str(Path(t) / "no-existe-indice")
        try:
            codigo, salida, error = correr(["--check", str(recibo)])
        finally:
            os.environ.clear()
            os.environ.update(previo)
        assert codigo == 0, (salida, error)


def test_cli_como_proceso_utf8_y_codigos():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        env = dict(_entorno_sin_git(), PYTHONIOENCODING="cp1252")
        env.pop("PYTHONPATH", None)
        r = subprocess.run([sys.executable, str(_RUTA), "--check", str(recibo)], capture_output=True, env=env, cwd=str(t))
        assert r.returncode == 0, r.stderr
        escribir(repo, {"nuevo.sql": "ñ cambiado\n"})
        r = subprocess.run([sys.executable, str(_RUTA), "--check", str(recibo)], capture_output=True, env=env, cwd=str(t))
        assert r.returncode == 1
        r.stdout.decode("utf-8")
        r.stderr.decode("utf-8")
        r = subprocess.run([sys.executable, str(_RUTA), "--check", str(Path(t) / "ñandú")], capture_output=True, env=env, cwd=str(t))
        assert r.returncode == 2
        assert "ñandú".encode("utf-8") in r.stderr, r.stderr


def base_de_ronda(ticket, repo):
    return ["--write", "--ticket", str(ticket), "--repo", str(repo), "--archivo", str(repo / "a.sql"), "--fecha", "2026-10-21",
            "--modo", "completo"]


def test_write_con_ronda_va_a_su_carpeta_y_no_pisa_la_primera():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-14-r"
        ticket.mkdir()
        assert correr(base_de_ronda(ticket, repo) + ["--estado", "con-hallazgos"])[0] == 0
        primera = ticket / "revision" / "2026-10-21-completo" / "recibo.json"
        antes = primera.read_bytes()
        codigo, salida, error = correr(base_de_ronda(ticket, repo) + ["--ronda", "2", "--estado", "limpio"])
        assert codigo == 0, error
        segunda = ticket / "revision" / "2026-10-21-completo-2" / "recibo.json"
        assert segunda.is_file() and primera.read_bytes() == antes
        assert "2026-10-21-completo-2" in salida.replace("\\", "/"), salida
        assert json.loads(segunda.read_text(encoding="utf-8"))["repos"][0]["estado"] == "limpio"
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert codigo == 0 and "2026-10-21-completo-2" in salida.replace("\\", "/"), "la ronda más alta es la más reciente"
        codigo, salida, _ = correr(["--check", str(ticket), "--modo", "completo"])
        assert codigo == 0 and "2026-10-21-completo-2" in salida.replace("\\", "/"), salida
        assert correr(["--check", str(ticket), "--modo", "rapido", "--recibo", str(segunda)])[0] == 2, "la carpeta con ronda dice su modo"
        diez = ticket / "revision" / "2026-10-21-completo-10"
        diez.mkdir()
        (diez / "recibo.json").write_bytes(segunda.read_bytes())
        assert "2026-10-21-completo-10" in correr(["--check", str(ticket)])[1].replace("\\", "/"), "la ronda se compara como número"


def test_write_con_ronda_uno_es_la_carpeta_de_siempre():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-15-r"
        ticket.mkdir()
        assert correr(base_de_ronda(ticket, repo) + ["--ronda", "1"])[0] == 0
        assert (ticket / "revision" / "2026-10-21-completo" / "recibo.json").is_file()
        assert not (ticket / "revision" / "2026-10-21-completo-1").exists()


def test_ronda_invalida_o_con_check_es_error_de_uso():
    with temporal() as t:
        repo, _ = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-16-r"
        ticket.mkdir()
        for malo in ("0", "-1", "x", "1.5", "02"):
            codigo, _, error = correr(base_de_ronda(ticket, repo) + ["--ronda", malo])
            assert codigo == 2, (malo, error)
        assert not (ticket / "revision").exists()
        assert correr(["--check", str(ticket), "--ronda", "2"])[0] == 2


def test_sellar_despues_del_commit_anota_el_head_y_el_recibo_sigue_valiendo():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t, ["--estado", "limpio"])
        antes = json.loads(recibo.read_text(encoding="utf-8"))
        head = commitear(repo, {})
        indice_antes = indice(repo)
        codigo, salida, error = correr(["--sellar", str(recibo)])
        assert codigo == 0 and error == "", (salida, error)
        assert salida == "recibo sellado: %s (%s en 1 repo(s))\n" % (str(recibo).replace("\\", "/"), head[:10]), salida
        crudo = recibo.read_bytes()
        esperado = dict(antes, repos=[dict(antes["repos"][0], sellado=head)])
        assert crudo == (json.dumps(esperado, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), crudo
        assert indice(repo) == indice_antes
        codigo, salida, _ = correr(["--check", str(recibo)])
        assert codigo == 0 and "vale" in salida, salida
        assert correr(["--sellar", str(recibo)])[0] == 0
        assert recibo.read_bytes() == crudo, "sellar de nuevo sin mover HEAD no cambia nada"


def test_sellar_con_lo_revisado_sin_commitear_no_toca_el_recibo():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t, ["--estado", "limpio"])
        crudo = recibo.read_bytes()
        codigo, salida, error = correr(["--sellar", str(recibo)])
        assert codigo == 1 and error == "", (codigo, salida, error)
        assert "commitea primero lo revisado" in salida and "a.sql" in salida and "nuevo.sql" in salida, salida
        assert recibo.read_bytes() == crudo
        _git(repo, "add", "a.sql")
        _git(repo, "commit", "-q", "-m", "solo a")
        codigo, salida, _ = correr(["--sellar", str(recibo)])
        assert codigo == 1 and "nuevo.sql" in salida and "a.sql" not in salida.replace("nuevo.sql", ""), salida
        escribir(repo, {".git/info/exclude": "nuevo.sql\n"})
        codigo, salida, _ = correr(["--sellar", str(recibo)])
        assert codigo == 1 and "nuevo.sql" in salida, "ignorado por git no es commiteado: %s" % salida
        escribir(repo, {".git/info/exclude": ""})
        _git(repo, "add", "nuevo.sql")
        codigo, salida, _ = correr(["--sellar", str(recibo)])
        assert codigo == 1 and "nuevo.sql" in salida, "stageado no es commiteado: %s" % salida
        assert recibo.read_bytes() == crudo
        _git(repo, "commit", "-q", "-m", "nuevo")
        assert correr(["--sellar", str(recibo)])[0] == 0


def test_sellar_con_el_diff_divergido_no_toca_el_recibo():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        commitear(repo, {})
        escribir(repo, {"nuevo.sql": "m\n"})
        crudo = recibo.read_bytes()
        codigo, salida, error = correr(["--sellar", str(recibo)])
        assert codigo == 1 and error == "", (codigo, salida, error)
        assert "cambio el diff revisado" in salida and "nuevo.sql" in salida and "a.sql" not in salida.replace("nuevo.sql", ""), salida
        assert recibo.read_bytes() == crudo
        commitear(repo, {})
        codigo, salida, _ = correr(["--sellar", str(recibo)])
        assert codigo == 1 and "cambio el diff revisado" in salida, "commitear lo que divergio no lo vuelve revisado: %s" % salida
        assert recibo.read_bytes() == crudo


def test_sellar_con_un_commit_fuera_de_lo_revisado_no_toca_el_recibo():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t, ["--estado", "limpio"])
        commitear(repo, {})
        commitear(repo, {"c.txt": "ajeno sin revisar\n"})
        crudo = recibo.read_bytes()
        codigo, salida, error = correr(["--sellar", str(recibo)])
        assert codigo == 1 and error == "", (codigo, salida, error)
        assert "HEAD trae cambios fuera de lo revisado" in salida and "c.txt" in salida, salida
        assert "a.sql" not in salida.replace("nuevo.sql", "").split("\n", 1)[1], salida
        assert recibo.read_bytes() == crudo
        commitear(repo, {"c.txt": ARCHIVOS["c.txt"]})
        assert correr(["--sellar", str(recibo)])[0] == 0, "un cambio que se deshace no queda fuera de lo revisado"


def test_sellar_la_carpeta_del_ticket_sella_el_recibo_mas_reciente():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t, ["--estado", "limpio"])
        segunda = ticket / "revision" / "2026-10-21-rapido-2" / "recibo.json"
        segunda.parent.mkdir()
        segunda.write_bytes(recibo.read_bytes())
        primera = recibo.read_bytes()
        head = commitear(repo, {})
        codigo, salida, error = correr(["--sellar", str(ticket)])
        assert codigo == 0, (salida, error)
        assert "2026-10-21-rapido-2/recibo.json" in salida.replace("\\", "/"), salida
        assert recibo.read_bytes() == primera, "solo sella el mas reciente"
        assert json.loads(segunda.read_text(encoding="utf-8"))["repos"][0]["sellado"] == head
        codigo, salida, _ = correr(["--sellar", str(recibo.parent)])
        assert codigo == 0 and "2026-10-21-rapido/recibo.json" in salida.replace("\\", "/"), salida
        assert json.loads(recibo.read_text(encoding="utf-8"))["repos"][0]["sellado"] == head


def test_sellar_dos_repos_es_todo_o_nada_y_cada_uno_con_su_head():
    with temporal() as t:
        r1, _ = repo_con_principal(t, ARCHIVOS, "uno")
        r2, _ = repo_con_principal(t, ARCHIVOS, "dos")
        escribir(r1, {"a.sql": "x\n"})
        escribir(r2, {"b.cs": "class B { int x; }\n"})
        ticket = Path(t) / "T-17-s"
        ticket.mkdir()
        assert correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], ["--fecha", "2026-10-21", "--estado", "limpio"]))[0] == 0
        recibo = ticket / "revision" / "2026-10-21-rapido" / "recibo.json"
        crudo = recibo.read_bytes()
        h1 = commitear(r1, {})
        codigo, salida, _ = correr(["--sellar", str(ticket)])
        assert codigo == 1 and "b.cs" in salida and str(r2).replace("\\", "/") in salida.replace("\\", "/"), salida
        assert recibo.read_bytes() == crudo, "si un repo no se puede sellar, no se sella ninguno"
        h2 = commitear(r2, {})
        codigo, salida, error = correr(["--sellar", str(ticket)])
        assert codigo == 0, (salida, error)
        assert "(%s, %s en 2 repo(s))" % (h1[:10], h2[:10]) in salida, salida
        assert [r["sellado"] for r in json.loads(recibo.read_text(encoding="utf-8"))["repos"]] == [h1, h2]


def test_sellar_con_opciones_que_no_son_suyas_es_error_de_uso():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        commitear(repo, {})
        crudo = recibo.read_bytes()
        for extra in (["--ticket", str(ticket)], ["--repo", str(repo)], ["--archivo", "a.sql"], ["--modo", "rapido"],
                      ["--recibo", str(recibo)], ["--reviewer", "r"], ["--verificacion", "v: ok"], ["--estado", "limpio"],
                      ["--fecha", "2026-10-21"], ["--ronda", "2"]):
            codigo, salida, error = correr(["--sellar", str(recibo)] + extra)
            assert codigo == 2 and salida == "" and extra[0] in error, (extra, codigo, salida, error)
        for otra in (["--check", str(recibo)], ["--write"]):
            codigo, salida, _ = correr(["--sellar", str(recibo)] + otra)
            assert codigo == 2 and salida == "", (otra, codigo, salida)
        assert recibo.read_bytes() == crudo
        codigo, salida, error = correr(["--sellar", str(Path(t) / "no-existe")])
        assert codigo == 2 and salida == "" and "no-existe" in error, error


UNIDAD = {"a.sql": "linea 1\nREVISADO\nlinea 3\n", "b.cs": "class B { int r; }\n", "nuevo.sql": "nuevo\n"}


def primera_ronda(t, nombre="T-20-u"):
    repo, base = repo_con_principal(t, ARCHIVOS)
    escribir(repo, UNIDAD)
    ticket = Path(t) / nombre
    ticket.mkdir()
    codigo, _, error = correr(args_write(ticket, [repo], [repo / a for a in sorted(UNIDAD)],
                                          ["--fecha", "2026-10-21", "--modo", "completo", "--estado", "pendiente"]))
    assert codigo == 0, error
    return repo, base, ticket, ticket / "revision" / "2026-10-21-completo"


def rechequeo(ticket, repos, archivos, previo, extra=()):
    return args_write(ticket, repos, archivos, ["--fecha", "2026-10-21", "--modo", "completo", "--ronda", "2",
                                                "--previo", str(previo), *extra])


def test_rechequeo_cubre_la_union_y_hereda_lo_que_no_cambio():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        crudo_primera = (primera / "recibo.json").read_bytes()
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        assert correr(["--check", str(primera)])[0] == 1
        segunda = ticket / "revision" / "2026-10-21-completo-2" / "recibo.json"
        hechos = []
        for previo in (primera, primera / "recibo.json", ticket):
            codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "a.sql"], previo, ["--estado", "limpio"]))
            assert codigo == 0 and error == "", (previo, salida, error)
            assert salida == "recibo escrito: %s (1 repo(s), 3 archivo(s); 1 rechequeado(s) y 2 heredado(s) de revision/2026-10-21-completo)\n" % (
                str(segunda).replace("\\", "/")), salida
            hechos.append(segunda.read_bytes())
            segunda.unlink()
        assert hechos[0] == hechos[1] == hechos[2], "las tres formas de --previo dan el mismo recibo"
        segunda.write_bytes(hechos[0])
        assert (primera / "recibo.json").read_bytes() == crudo_primera, "el recibo previo no se toca"
        datos = json.loads(hechos[0].decode("utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "previo", "repos"], list(datos)
        assert datos["previo"] == "revision/2026-10-21-completo"
        r = datos["repos"][0]
        union = calc(repo, base, sorted(UNIDAD))
        assert r["base"] == base and r["archivos"] == ["a.sql", "b.cs", "nuevo.sql"], r
        assert r["sha256"] == union["sha256"] and r["sha256_por_archivo"] == union["sha256_por_archivo"], r
        assert r["rechequeados"] == ["a.sql"] and r["heredados"] == ["b.cs", "nuevo.sql"] and r["retirados"] == [], r
        assert r["estado"] == "limpio" and r["modo"] == "completo"
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert codigo == 0 and "2026-10-21-completo-2" in salida.replace("\\", "/") and "3 archivo(s)" in salida, salida


def test_rechequeo_con_un_archivo_que_cambio_sin_rechequear_no_escribe_nada():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n", "b.cs": "class B { int otro; }\n"})
        antes = sorted(p.name for p in (ticket / "revision").iterdir())
        codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "a.sql"], primera))
        assert codigo == 1 and error == "", (codigo, salida, error)
        texto = salida.replace("\\", "/")
        assert "recibo NO se escribe" in texto and str(repo).replace("\\", "/") in texto and "b.cs" in texto, texto
        assert "a.sql" not in texto.split("\n", 1)[1] and "nuevo.sql" not in texto, texto
        assert sorted(p.name for p in (ticket / "revision").iterdir()) == antes
        escribir(repo, {"nuevo.sql": "nuevo cambiado\n"})
        codigo, salida, _ = correr(rechequeo(ticket, [repo], [repo / "a.sql"], primera))
        assert codigo == 1 and "b.cs, nuevo.sql" in salida, salida
        codigo, _, error = correr(rechequeo(ticket, [repo], [repo / "a.sql", repo / "b.cs", repo / "nuevo.sql"], primera))
        assert codigo == 0, error


def test_rechequeo_con_otra_base_no_escribe_nada_y_sin_base_toma_la_del_previo():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        otra = commitear(repo, {})
        _git(repo, "update-ref", "refs/remotes/origin/main", otra)
        assert M.resolver_base(str(repo)) == otra, "el merge-base de ahora ya no es la base del previo"
        codigo, salida, error = correr(rechequeo(ticket, ["%s#%s" % (repo, otra)], [repo / "a.sql"], primera))
        assert codigo == 1 and error == "", (codigo, salida, error)
        assert "recibo NO se escribe" in salida and otra in salida and base in salida, salida
        assert not (ticket / "revision" / "2026-10-21-completo-2").exists()
        codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "a.sql"], primera))
        assert codigo == 0, (salida, error)
        datos = json.loads((ticket / "revision" / "2026-10-21-completo-2" / "recibo.json").read_text(encoding="utf-8"))
        assert datos["repos"][0]["base"] == base
        assert correr(rechequeo(ticket, ["%s#%s" % (repo, base[:12])], [repo / "a.sql"], primera))[0] == 0


def test_rechequeo_se_puede_sellar_con_la_unidad_entera_y_uno_parcial_no():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        assert correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--modo", "completo", "--ronda", "2"]))[0] == 0
        head = commitear(repo, {})
        codigo, salida, _ = correr(["--sellar", str(ticket)])
        assert codigo == 1 and "fuera de lo revisado" in salida and "b.cs" in salida, "un recibo parcial no se sella: %s" % salida
        codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "a.sql"], primera, ["--ronda", "3", "--estado", "limpio"]))
        assert codigo == 0, (salida, error)
        tercera = ticket / "revision" / "2026-10-21-completo-3" / "recibo.json"
        codigo, salida, error = correr(["--sellar", str(ticket)])
        assert codigo == 0, (salida, error)
        assert "2026-10-21-completo-3/recibo.json" in salida.replace("\\", "/"), salida
        assert json.loads(tercera.read_text(encoding="utf-8"))["repos"][0]["sellado"] == head
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert codigo == 0 and "2026-10-21-completo-3" in salida.replace("\\", "/"), salida


def test_rechequeo_de_un_archivo_que_solo_sumo_la_correccion_deja_sellar_la_unidad():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        escribir(repo, {"prueba_a.sql": "prueba\n"})
        codigo, salida, _ = correr(["--check", str(primera)])
        assert codigo == 0, "la correccion no toco nada revisado: %s" % salida
        head = commitear(repo, {})
        codigo, salida, _ = correr(["--sellar", str(primera)])
        assert codigo == 1 and "fuera de lo revisado" in salida and "prueba_a.sql" in salida, (
            "sin rechequeo, el archivo sumado deja la unidad sin sellar: %s" % salida)
        codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "prueba_a.sql"], primera, ["--estado", "limpio"]))
        assert codigo == 0 and "1 rechequeado(s) y 3 heredado(s)" in salida, (salida, error)
        segunda = ticket / "revision" / "2026-10-21-completo-2"
        codigo, salida, error = correr(["--sellar", str(segunda)])
        assert codigo == 0, (salida, error)
        r = json.loads((segunda / "recibo.json").read_text(encoding="utf-8"))["repos"][0]
        assert r["rechequeados"] == ["prueba_a.sql"] and r["heredados"] == ["a.sql", "b.cs", "nuevo.sql"], r
        assert r["sellado"] == head, r


def test_rechequeo_hereda_el_repo_que_no_se_paso_y_suma_uno_nuevo_al_final():
    with temporal() as t:
        r1, b1 = repo_con_principal(t, ARCHIVOS, "uno")
        r2, b2 = repo_con_principal(t, ARCHIVOS, "dos")
        r3, b3 = repo_con_principal(t, ARCHIVOS, "tres")
        escribir(r1, {"a.sql": "x\n"})
        escribir(r2, {"b.cs": "class B { int x; }\n"})
        ticket = Path(t) / "T-21-u"
        ticket.mkdir()
        assert correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], ["--fecha", "2026-10-21", "--modo", "completo"]))[0] == 0
        primera = ticket / "revision" / "2026-10-21-completo"
        escribir(r1, {"a.sql": "y\n"})
        escribir(r3, {"c.txt": "tocado\n"})
        codigo, salida, error = correr(rechequeo(ticket, [r1, r3], [r1 / "a.sql", r3 / "c.txt"], primera))
        assert codigo == 0, (salida, error)
        datos = json.loads((ticket / "revision" / "2026-10-21-completo-2" / "recibo.json").read_text(encoding="utf-8"))
        rutas = [r["ruta"] for r in datos["repos"]]
        assert rutas == [str(r).replace("\\", "/") for r in (r1, r2, r3)], rutas
        uno, dos, tres = datos["repos"]
        assert uno["rechequeados"] == ["a.sql"] and uno["heredados"] == [] and uno["base"] == b1
        assert dos["rechequeados"] == [] and dos["heredados"] == ["b.cs"] and dos["archivos"] == ["b.cs"] and dos["base"] == b2
        assert dos["sha256"] == calc(r2, b2, ["b.cs"])["sha256"]
        assert tres["rechequeados"] == ["c.txt"] and tres["heredados"] == [] and tres["base"] == b3
        assert correr(["--check", str(ticket)])[0] == 0
        escribir(r2, {"b.cs": "class B { int z; }\n"})
        codigo, salida, _ = correr(rechequeo(ticket, [r1], [r1 / "a.sql"], primera))
        assert codigo == 1 and "b.cs" in salida and str(r2).replace("\\", "/") in salida.replace("\\", "/"), salida


def test_rechequeo_retira_el_archivo_nuevo_que_la_correccion_quito():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        (repo / "nuevo.sql").unlink()
        codigo, salida, _ = correr(rechequeo(ticket, [repo], [repo / "a.sql"], primera))
        assert codigo == 1 and "nuevo.sql" in salida, "quitarlo es un cambio: %s" % salida
        codigo, salida, error = correr(rechequeo(ticket, [repo], ["nuevo.sql"], primera))
        assert codigo == 0, (salida, error)
        assert "0 rechequeado(s) y 2 heredado(s)" in salida and "1 retirado(s)" in salida, salida
        r = json.loads((ticket / "revision" / "2026-10-21-completo-2" / "recibo.json").read_text(encoding="utf-8"))["repos"][0]
        assert r["archivos"] == ["a.sql", "b.cs"] and r["retirados"] == ["nuevo.sql"] and r["rechequeados"] == [], r
        assert correr(["--check", str(ticket)])[0] == 0
        codigo, _, error = correr(rechequeo(ticket, [repo], ["nuevo.sql", "otro-que-no-existe.sql"], primera, ["--ronda", "3"]))
        assert codigo == 2 and "otro-que-no-existe.sql" in error, error


def test_rechequeo_con_un_previo_que_no_sirve_es_error_de_uso():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        _, _, ajeno, primera_ajena = primera_ronda(Path(t) / "otro", "T-22-ajeno")
        crudo = (primera / "recibo.json").read_bytes()
        antes = sorted(p.name for p in (ticket / "revision").iterdir())
        malos = [
            (rechequeo(ticket, [repo], [repo / "a.sql"], Path(t) / "no-existe"), "no-existe"),
            (rechequeo(ticket, [repo], [repo / "a.sql"], primera_ajena), "este ticket"),
            (args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--modo", "completo", "--previo", str(primera)]), "--ronda"),
            (args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--modo", "rapido", "--previo", str(primera)]),
             "--modo rapido es mas bajo que el completo del recibo previo"),
            (args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-20", "--modo", "completo", "--previo", str(primera)]), "--ronda"),
        ]
        for argv, esperado in malos:
            codigo, salida, error = correr(argv)
            assert codigo == 2 and salida == "" and esperado in error, (argv, codigo, salida, error)
        assert (primera / "recibo.json").read_bytes() == crudo
        assert sorted(p.name for p in (ticket / "revision").iterdir()) == antes
        codigo, _, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-22", "--modo", "completo", "--previo", str(primera)]))
        assert codigo == 0, "una fecha posterior queda despues del previo, con un modo que no baja: %s" % error


def test_derivado_se_guarda_en_el_recibo_y_uno_mal_formado_es_error_de_uso():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], [
            "--fecha", "2026-10-22", "--derivado", "x = y en a.sql:2=T14", "--derivado", " sin dueño en b.cs = backlog "]))
        assert codigo == 0, (salida, error)
        assert salida.endswith("(1 repo(s), 1 archivo(s); 2 derivado(s))\n"), salida
        datos = json.loads((ticket / "revision" / "2026-10-22-rapido" / "recibo.json").read_text(encoding="utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "repos", "derivados"], list(datos)
        assert datos["derivados"] == [{"hallazgo": "x = y en a.sql:2", "destino": "T14"},
                                      {"hallazgo": "sin dueño en b.cs", "destino": "backlog"}], datos["derivados"]
        for malo in ("sin-igual", "=T14", "hallazgo=", " = ", "hallazgo=   "):
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-23", "--derivado", malo]))
            assert codigo == 2 and salida == "" and "--derivado" in error, (malo, codigo, error)
        assert not (ticket / "revision" / "2026-10-23-rapido").exists()
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "a.sql"], primera, ["--derivado", "nuevo WARNING=SM-3"]))
        assert codigo == 0 and salida.endswith("de revision/2026-10-21-completo; 1 derivado(s))\n"), (salida, error)
        datos = json.loads((ticket / "revision" / "2026-10-21-completo-2" / "recibo.json").read_text(encoding="utf-8"))
        assert datos["derivados"] == [{"hallazgo": "nuevo WARNING", "destino": "SM-3"}]


def test_sin_previo_ni_derivado_el_recibo_trae_los_campos_de_siempre():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        datos = json.loads(recibo.read_text(encoding="utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "repos"], list(datos)
        assert list(datos["repos"][0]) == ["ruta", "base", "archivos", "sha256", "sha256_por_archivo", "modo", "reviewers",
                                           "verificacion", "estado"], list(datos["repos"][0])


def test_previo_y_derivado_con_check_o_sellar_son_error_de_uso():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        commitear(repo, {})
        crudo = recibo.read_bytes()
        for modo in (["--check", str(recibo)], ["--sellar", str(recibo)]):
            for extra in (["--previo", str(recibo)], ["--derivado", "h=T1"]):
                codigo, salida, error = correr(modo + extra)
                assert codigo == 2 and salida == "" and extra[0] in error, (modo, extra, codigo, salida, error)
        assert recibo.read_bytes() == crudo


# ---------------------------------------------------------------- lo que el recibo garantiza (S5 a S10 de integridad-del-recibo)

def reescritura(ticket, repo, archivos, extra=()):
    return args_write(ticket, [repo], archivos, ["--fecha", "2026-10-21", "--modo", "completo", "--reviewer", "revisor-diseno", *extra])


def bytes_del_indice(repo):
    return (Path(repo) / ".git" / "index").read_bytes()


def test_reescribir_un_recibo_con_otro_diff_no_escribe_y_manda_al_rechequeo():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nREVISADO\nlinea 3\n"})
        ticket = Path(t) / "T-40-r"
        ticket.mkdir()
        assert correr(reescritura(ticket, repo, [repo / "a.sql"], ["--estado", "pendiente"]))[0] == 0
        carpeta = (ticket / "revision" / "2026-10-21-completo").as_posix()
        antes = bytes_de(ticket)
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO SIN RECHEQUEO\nlinea 3\n"})
        codigo, salida, error = correr(reescritura(ticket, repo, [repo / "a.sql"], ["--estado", "con-hallazgos"]))
        assert codigo == 1 and error == "", (codigo, salida, error)
        texto = salida.replace("\\", "/")
        assert texto.startswith("recibo NO se escribe (%s/recibo.json): ya existe" % carpeta), texto
        assert "  repo %s: cambiaron a.sql\n" % Path(repo).as_posix() in texto, texto
        assert "--previo %s" % carpeta in texto and "--ronda 2" in texto, texto
        assert bytes_de(ticket) == antes, "no absorbe la correccion sin rechequeo"
        escribir(repo, {"a.sql": "linea 1\nREVISADO\nlinea 3\n"})
        codigo, salida, error = correr(reescritura(ticket, repo, [repo / "a.sql", repo / "b.cs"], ["--estado", "con-hallazgos"]))
        assert codigo == 1 and "no estan en el recibo: b.cs" in salida, (codigo, salida, error)
        codigo, salida, error = correr(reescritura(ticket, "%s#%s" % (repo, commitear(repo, {"c.txt": "x\n"})), [repo / "a.sql"],
                                                   ["--estado", "con-hallazgos"]))
        assert codigo == 1 and "base " in salida and base in salida, (codigo, salida, error)
        assert bytes_de(ticket) == antes
        codigo, salida, error = correr(reescritura(ticket, repo, [repo / "a.sql"], ["--estado", "con-hallazgos"]))
        assert codigo == 0 and error == "", (salida, error)
        assert json.loads((ticket / "revision" / "2026-10-21-completo" / "recibo.json").read_text(encoding="utf-8"))["repos"][0]["estado"] == "con-hallazgos"


def test_pisar_un_recibo_con_menos_repos_no_escribe_y_nombra_el_que_falta():
    with temporal() as t:
        r1, _ = repo_con_principal(t, ARCHIVOS, "uno")
        r2, _ = repo_con_principal(t, ARCHIVOS, "dos")
        ticket = Path(t) / "T-14-w"
        ticket.mkdir()
        comun = ["--fecha", "2026-10-21", "--modo", "rapido"]
        assert correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], comun))[0] == 0
        recibo = ticket / "revision" / "2026-10-21-rapido" / "recibo.json"
        crudo = recibo.read_bytes()
        codigo, salida, error = correr(args_write(ticket, [r1], [r1 / "a.sql"], comun))
        assert codigo == 1 and error == "", (codigo, salida, error)
        texto = salida.replace("\\", "/")
        assert "  repo %s: esta llamada no trae este repo\n" % Path(r2).as_posix() in texto and Path(r1).as_posix() not in texto, texto
        assert recibo.read_bytes() == crudo, "no pisa entero"
        codigo, _, error = correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], comun))
        assert codigo == 0 and error == "" and recibo.read_bytes() == crudo, "la misma llamada reescribe los mismos bytes"
        codigo, _, error = correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], ["--fecha", "2026-10-22", "--modo", "rapido"]))
        assert codigo == 0 and error == "", "una carpeta nueva no avisa"


def test_reescribir_con_el_mismo_diff_cambia_el_estado_y_conserva_el_sello_y_lo_demas():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nREVISADO\nlinea 3\n"})
        ticket = Path(t) / "T-41-s"
        ticket.mkdir()
        assert correr(reescritura(ticket, repo, [repo / "a.sql"], ["--estado", "con-hallazgos", "--derivado", "h=T9",
                                                                    "--verificacion", "v: ok"]))[0] == 0
        recibo = ticket / "revision" / "2026-10-21-completo" / "recibo.json"
        head = commitear(repo, {})
        assert correr(["--sellar", str(recibo)])[0] == 0
        sellado = json.loads(recibo.read_text(encoding="utf-8"))
        codigo, salida, error = correr(reescritura(ticket, repo, [repo / "a.sql"], ["--estado", "limpio"]))
        assert codigo == 0 and error == "", (salida, error)
        assert salida == "recibo escrito: %s (1 repo(s), 1 archivo(s); 1 derivado(s))\n" % recibo.as_posix(), salida
        datos = json.loads(recibo.read_text(encoding="utf-8"))
        assert datos == dict(sellado, repos=[dict(sellado["repos"][0], estado="limpio")]), datos
        assert list(datos) == list(sellado) and list(datos["repos"][0]) == list(sellado["repos"][0])
        assert datos["repos"][0]["sellado"] == head and datos["repos"][0]["base"] == base, "sin #BASE toma la base del recibo, no su sello"
        codigo, _, error = correr(reescritura(ticket, repo, [repo / "a.sql"], ["--estado", "limpio", "--verificacion", "otra: ok",
                                                                               "--derivado", "h2=T10", "--reviewer", "revisor-sql"]))
        assert codigo == 0, error
        r = json.loads(recibo.read_text(encoding="utf-8"))
        assert r["derivados"] == [{"hallazgo": "h2", "destino": "T10"}] and list(r) == list(sellado), r
        assert r["repos"][0]["verificacion"] == ["otra: ok"] and r["repos"][0]["reviewers"] == ["revisor-diseno", "revisor-sql"], r
        assert r["repos"][0]["sellado"] == head, "lo que la llamada nombra se actualiza, el sello se conserva"


def test_reescribir_un_rechequeo_sin_su_previo_no_escribe_y_con_su_previo_conserva_lo_heredado():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        argv = rechequeo(ticket, [repo], [repo / "a.sql"], primera, ["--estado", "pendiente"])
        assert correr(argv)[0] == 0
        segunda = ticket / "revision" / "2026-10-21-completo-2" / "recibo.json"
        crudo = segunda.read_bytes()
        sin_previo = args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--modo", "completo", "--ronda", "2",
                                                                  "--estado", "con-hallazgos"])
        codigo, salida, error = correr(sin_previo)
        assert codigo == 1 and "faltan en esta llamada: b.cs, nuevo.sql" in salida and "--previo" in salida, (codigo, salida, error)
        assert segunda.read_bytes() == crudo, "sin --previo no pierde lo heredado"
        codigo, salida, error = correr([a if a != "pendiente" else "con-hallazgos" for a in argv])
        assert codigo == 0 and error == "", (salida, error)
        assert "1 rechequeado(s) y 2 heredado(s) de revision/2026-10-21-completo" in salida, salida
        datos = json.loads(segunda.read_text(encoding="utf-8"))
        r = datos["repos"][0]
        assert datos["previo"] == "revision/2026-10-21-completo" and r["heredados"] == ["b.cs", "nuevo.sql"], datos
        previo = json.loads(crudo.decode("utf-8"))
        assert datos == dict(previo, repos=[dict(previo["repos"][0], estado="con-hallazgos")]), datos


def test_check_con_otra_version_de_lo_revisado_en_el_indice_no_vale():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        revisado = (repo / "a.sql").read_bytes()
        escribir(repo, {"a.sql": "linea 1\nOTRA VERSION\nlinea 3\n"})
        _git(repo, "add", "a.sql")
        escribir(repo, {"a.sql": revisado})
        indice_antes = bytes_del_indice(repo)
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 1 and error == "", (codigo, salida, error)
        texto = salida.replace("\\", "/")
        assert texto.startswith("recibo NO vale para el commit (%s): el indice no es lo revisado\n" % recibo.as_posix()), texto
        assert "  repo %s: otra version en el indice: a.sql\n" % Path(repo).as_posix() in texto and "nuevo.sql" not in texto, texto
        assert "git add" in texto, texto
        assert bytes_del_indice(repo) == indice_antes, "--check no escribe el indice"
        _git(repo, "add", "a.sql", "nuevo.sql")
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0 and error == "" and salida.startswith("recibo vale:"), (salida, error)


def test_check_con_archivos_fuera_del_recibo_en_el_indice_no_vale_y_los_del_working_tree_avisan():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        escribir(repo, {"c.txt": "ajeno tocado\n", "ambiente.config": "ip=1\n"})
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0 and salida.startswith("recibo vale:"), (salida, error)
        avisa = error.replace("\\", "/")
        assert avisa.startswith("recibo: aviso,") and "%s: ambiente.config, c.txt" % Path(repo).as_posix() in avisa, avisa
        assert "a.sql" not in avisa and "nuevo.sql" not in avisa, avisa
        _git(repo, "add", "c.txt")
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 1, (salida, error)
        assert "  repo %s: fuera de lo revisado en el indice: c.txt\n" % Path(repo).as_posix() in salida.replace("\\", "/"), salida
        assert "--previo" in salida and "ambiente.config" in error and "c.txt" not in error, (salida, error)
        _git(repo, "commit", "-q", "-m", "ajeno")
        codigo, salida, _ = correr(["--check", str(recibo)])
        assert codigo == 1 and "fuera de lo revisado en el indice: c.txt" in salida, "lo commiteado desde la base tambien entra al sello: %s" % salida
        escribir(repo, {"c.txt": ARCHIVOS["c.txt"]})
        _git(repo, "add", "c.txt")
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0 and "c.txt" not in error, "un cambio que se deshace no queda fuera de lo revisado: %s" % salida


def test_check_de_un_recibo_sellado_no_mira_el_indice():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t, ["--estado", "limpio"])
        commitear(repo, {})
        assert correr(["--sellar", str(recibo)])[0] == 0
        escribir(repo, {"c.txt": "otra unidad\n", "suelto.txt": "x\n"})
        _git(repo, "add", "c.txt")
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0 and error == "", "el criterio del commit es de antes del commit: %s %s" % (salida, error)


def test_sellar_con_cambios_fuera_de_lo_revisado_propone_el_rechequeo_con_previo_y_ese_sella():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t, ["--estado", "limpio"])
        escribir(repo, {"c.txt": "lo sumo la unidad\n"})
        head = commitear(repo, {})
        codigo, salida, error = correr(["--sellar", str(recibo)])
        assert codigo == 1 and "HEAD trae cambios fuera de lo revisado" in salida and "c.txt" in salida, (salida, error)
        texto = salida.replace("\\", "/")
        assert "--previo %s" % recibo.parent.as_posix() in texto and "revision nueva" not in texto, texto
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "c.txt"], ["--fecha", "2026-10-21", "--ronda", "2", "--previo",
                                                                                   str(recibo.parent), "--estado", "limpio"]))
        assert codigo == 0, (salida, error)
        segunda = ticket / "revision" / "2026-10-21-rapido-2"
        codigo, salida, error = correr(["--sellar", str(segunda)])
        assert codigo == 0, (salida, error)
        assert json.loads((segunda / "recibo.json").read_text(encoding="utf-8"))["repos"][0]["sellado"] == head


def test_check_imprime_el_estado_el_modo_y_la_bajada():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0 and error == "", (salida, error)
        assert salida == "recibo vale: 1 repo(s), 2 archivo(s) (%s)\n  estado: pendiente; modo: rapido; bajada: no\n" % recibo.as_posix(), salida
        datos = json.loads(recibo.read_text(encoding="utf-8"))
        datos["bajada"] = {"de": "completo", "a": "rapido", "motivo": "solo c.txt sin capa", "va_a_lider": False}
        recibo.write_text(json.dumps(datos), encoding="utf-8")
        codigo, salida, _ = correr(["--check", str(ticket)])
        assert codigo == 0 and "\n  estado: pendiente; modo: rapido; bajada: de completo a rapido (solo c.txt sin capa)\n" in salida, salida
        escribir(repo, {"nuevo.sql": "m\n"})
        codigo, salida, _ = correr(["--check", str(recibo)])
        assert codigo == 1 and "\n  estado: pendiente; modo: rapido; bajada: de completo a rapido" in salida, salida


def test_sellar_se_niega_con_un_recibo_pendiente_y_sella_al_reescribirlo_con_el_mismo_diff():
    with temporal() as t:
        repo, ticket, recibo = preparar_recibo(t)
        head = commitear(repo, {})
        crudo = recibo.read_bytes()
        codigo, salida, error = correr(["--sellar", str(recibo)])
        assert codigo == 1 and error == "", (codigo, salida, error)
        assert salida.startswith("recibo NO se sella (%s): el recibo esta pendiente\n" % recibo.as_posix()), salida
        assert "--estado con-hallazgos" in salida, salida
        assert recibo.read_bytes() == crudo
        codigo, _, error = correr(args_write(ticket, [repo], [repo / "a.sql", repo / "nuevo.sql"], ["--fecha", "2026-10-21",
                                                                                                    "--estado", "con-hallazgos"]))
        assert codigo == 0, error
        codigo, salida, error = correr(["--sellar", str(recibo)])
        assert codigo == 0, (salida, error)
        assert json.loads(recibo.read_text(encoding="utf-8"))["repos"][0]["sellado"] == head


def test_write_con_ticket_parte_del_sello_vivo_mas_nuevo_como_el_triaje():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        ticket = Path(t) / "T-50-u"
        ticket.mkdir()
        escribir(repo, {"a.sql": "linea 1\nUNIDAD 1\nlinea 3\n"})
        assert correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--estado", "limpio"]))[0] == 0
        sello = commitear(repo, {})
        assert correr(["--sellar", str(ticket)])[0] == 0
        escribir(repo, {"b.cs": "class B { int unidad2; }\n"})
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "b.cs"], ["--fecha", "2026-10-22", "--estado", "limpio"]))
        assert codigo == 0 and error == "", (salida, error)
        segunda = ticket / "revision" / "2026-10-22-rapido"
        r = json.loads((segunda / "recibo.json").read_text(encoding="utf-8"))["repos"][0]
        assert r["base"] == sello and r["sha256"] == calc(repo, sello, ["b.cs"])["sha256"], (r["base"], sello, base)
        assert M.elegir_base(str(repo), None, str(ticket)) == (sello, "sellada", "revision/2026-10-21-rapido")
        head = commitear(repo, {})
        codigo, salida, error = correr(["--sellar", str(segunda)])
        assert codigo == 0, "la unidad 2 se sella sin la unidad 1: %s" % salida
        assert correr(args_write(ticket, ["%s#%s" % (repo, base)], [repo / "b.cs"], ["--fecha", "2026-10-23"]))[0] == 0
        r = json.loads((ticket / "revision" / "2026-10-23-rapido" / "recibo.json").read_text(encoding="utf-8"))["repos"][0]
        assert r["base"] == base, "la base explicita gana al sello"
        assert correr(args_write(ticket, [repo], [repo / "b.cs"], ["--fecha", "2026-10-24"]))[0] == 0
        r = json.loads((ticket / "revision" / "2026-10-24-rapido" / "recibo.json").read_text(encoding="utf-8"))["repos"][0]
        assert r["base"] == head, "el sello mas nuevo gana"


def test_una_ruta_con_corchetes_va_a_git_como_literal():
    with temporal() as t:
        repo, base = repo_con_principal(t, {"pages/i.tsx": "export const i = 1\n", "app/[slug]/page.tsx": "uno\n",
                                            "app/s/page.tsx": "s\n"})
        escribir(repo, {"pages/[id].tsx": "export default function P() { return 1 }\n", "app/[slug]/page.tsx": "uno cambiado\n"})
        ticket = Path(t) / "T-60-c"
        ticket.mkdir()
        codigo, salida, error = correr(args_write(ticket, [repo], ["pages/[id].tsx", "app/[slug]/page.tsx"], ["--fecha", "2026-10-21"]))
        assert codigo == 0, (salida, error)
        recibo = ticket / "revision" / "2026-10-21-rapido" / "recibo.json"
        r = json.loads(recibo.read_text(encoding="utf-8"))["repos"][0]
        assert r["sha256_por_archivo"]["pages/[id].tsx"] != hashlib.sha256(b"").hexdigest(), "un archivo nuevo no se hashea vacio"
        escribir(repo, {"app/s/page.tsx": "s cambiado\n", "pages/i.tsx": "export const i = 2\n"})
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0, "un archivo que el corchete emparejaba no es de la unidad: %s" % salida
        previo = dict(os.environ)
        os.environ.update(GIT_GLOB_PATHSPECS="1", GIT_ICASE_PATHSPECS="1")
        try:
            codigo, salida, error = correr(["--check", str(recibo)])
        finally:
            os.environ.clear()
            os.environ.update(previo)
        assert codigo == 0, "el entorno del usuario no cambia los pathspecs: %s %s" % (salida, error)
        escribir(repo, {"pages/[id].tsx": "export default function P() { return EXFILTRA() }\n"})
        codigo, salida, _ = correr(["--check", str(recibo)])
        assert codigo == 1 and "pages/[id].tsx" in salida and "app/[slug]/page.tsx" not in salida, salida


def _sin_distinguir_mayusculas(carpeta):
    prueba = Path(carpeta) / "Mayusculas.txt"
    prueba.write_text("x", encoding="utf-8")
    try:
        return (Path(carpeta) / "mAYUSCULAS.TXT").exists()
    finally:
        prueba.unlink()


def test_una_ruta_relativa_con_otras_mayusculas_se_canoniza_a_la_del_repo():
    with temporal() as t:
        if not _sin_distinguir_mayusculas(t):
            print("salta test_una_ruta_relativa_con_otras_mayusculas_se_canoniza_a_la_del_repo: el sistema de archivos de %s "
                  "distingue mayusculas, y el caso solo existe donde no las distingue (Windows, macOS)" % t)
            return
        repo, base = repo_con_principal(t, {"src/foo.sql": "a\nb\nc\n"})
        escribir(repo, {"src/foo.sql": "a\nX\nc\n"})
        ticket = Path(t) / "T-70-m"
        ticket.mkdir()
        codigo, salida, error = correr(args_write(ticket, [repo], ["SRC/FOO.SQL"], ["--fecha", "2026-10-21", "--estado", "limpio"]))
        assert codigo == 0, (salida, error)
        r = json.loads((ticket / "revision" / "2026-10-21-rapido" / "recibo.json").read_text(encoding="utf-8"))["repos"][0]
        assert r["archivos"] == ["src/foo.sql"] and r["sha256"] == calc(repo, base, ["src/foo.sql"])["sha256"], r
        commitear(repo, {})
        codigo, salida, error = correr(["--sellar", str(ticket)])
        assert codigo == 0, (salida, error)


def test_write_check_y_sellar_de_una_unidad_limpia_salen_como_antes():
    with temporal() as t:
        repo, base = repo_con_principal(t, ARCHIVOS)
        escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n", "nuevo.sql": "n\n"})
        ticket = Path(t) / "T-80-a"
        ticket.mkdir()
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql", repo / "nuevo.sql"], ["--fecha", "2026-10-21",
                                                                                                     "--estado", "limpio"]))
        recibo = ticket / "revision" / "2026-10-21-rapido" / "recibo.json"
        assert codigo == 0 and error == "" and salida == "recibo escrito: %s (1 repo(s), 2 archivo(s))\n" % recibo.as_posix(), (salida, error)
        datos = json.loads(recibo.read_text(encoding="utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "repos"] and datos["repos"][0]["base"] == base, datos
        codigo, salida, error = correr(["--check", str(ticket)])
        assert codigo == 0 and error == "", (salida, error)
        assert salida.split("\n")[0] == "recibo vale: 1 repo(s), 2 archivo(s) (%s)" % recibo.as_posix(), salida
        head = commitear(repo, {})
        codigo, salida, error = correr(["--sellar", str(ticket)])
        assert codigo == 0 and error == "", (salida, error)
        assert salida == "recibo sellado: %s (%s en 1 repo(s))\n" % (recibo.as_posix(), head[:10]), salida
        assert json.loads(recibo.read_text(encoding="utf-8")) == dict(datos, repos=[dict(datos["repos"][0], sellado=head)])


CONFIG_GIT_RARA = ("[diff]\n\tnoprefix = true\n\tmnemonicPrefix = true\n\tsubmodule = log\n\talgorithm = patience\n\tcontext = 7\n"
                   "\tinterHunkContext = 5\n\trenames = copies\n[core]\n\tquotepath = true\n\tabbrev = 12\n[color]\n\tui = always\n"
                   "[diff \"mayus\"]\n\ttextconv = tr a-z A-Z <\n")
GLOB = "x/[ab].sql"
NFD = "x/an\u0303o nfd.sql"
BINARIO = b"\x00\x01binario\x00"
RUTAS_MIXTAS = ["x/a.sql", GLOB, "x/año.sql", NFD, "con espacio/b c.sql", "bin.dat", "borrado.sql", "quitado.sql", "viejo.sql",
                "nuevo.sql", "carpeta", "igual.sql", "conflicto.sql", "agregado.sql", "suelto.sql", "era_submodulo", "submodulo_nuevo",
                "mayus.cs"]


def repo_mixto(t):
    repo = Path(t) / "mixto"
    repo.mkdir()
    _git(repo, "init", "-q")
    escribir(repo, {"x/a.sql": "a 1\na 2\na 3\n", GLOB: "g 1\ng 2\n", "x/año.sql": "ñ 1\n", NFD: "n 1\n", "con espacio/b c.sql": "e 1\n",
                    "bin.dat": BINARIO, "borrado.sql": "d\n", "quitado.sql": "q\n", "viejo.sql": "v\n", "carpeta/dentro.sql": "c\n",
                    "igual.sql": "igual\n", "conflicto.sql": "c\n", ".gitattributes": "mayus.cs diff=mayus\n", "mayus.cs": "uno\n"})
    _git(repo, "add", "-A")
    _git(repo, "update-index", "--add", "--cacheinfo", "160000,%s,era_submodulo" % ("e" * 40))
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    escribir(repo, {"x/a.sql": "a 1\nA 2\na 3\n", GLOB: "g 1\nG 2\n", "x/año.sql": "ñ 1\nÑ 2\n", NFD: "n 1\nN 2\n", "con espacio/b c.sql": "e 1\nE 2\n",
                    "bin.dat": BINARIO + b"\x02", "agregado.sql": "nuevo\n", "suelto.sql": "suelto\n", "mayus.cs": "uno\ndos\n"})
    _git(repo, "--literal-pathspecs", "add", "--", "agregado.sql")
    os.remove(repo / "borrado.sql")
    _git(repo, "--literal-pathspecs", "rm", "-q", "--", "quitado.sql")
    _git(repo, "--literal-pathspecs", "mv", "viejo.sql", "nuevo.sql")
    shutil.rmtree(repo / "carpeta")
    escribir(repo, {"carpeta": "ahora un archivo\n"})
    _git(repo, "--literal-pathspecs", "rm", "-q", "--cached", "--", "era_submodulo")
    escribir(repo, {"era_submodulo": "ahora un archivo\n"})
    _git(repo, "--literal-pathspecs", "add", "--", "era_submodulo")
    _git(repo, "update-index", "--add", "--cacheinfo", "160000,%s,submodulo_nuevo" % base)
    return repo, base


def con_un_conflicto(repo, rel):
    viejo = _git(repo, "rev-parse", "HEAD:" + rel)
    escribir(repo, {rel: "conflicto\n"})
    nuevo = _git(repo, "hash-object", "-w", "--", rel)
    _git(repo, "update-index", "--force-remove", "--", rel)
    subprocess.run(["git", "update-index", "--index-info"], cwd=str(repo), capture_output=True, check=True, env=_entorno_sin_git(),
                   input="".join("100644 %s %d\t%s\n" % (o, n, rel) for n, o in ((1, viejo), (2, nuevo), (3, viejo))).encode("utf-8"))
    assert "%s 2\t%s" % (nuevo, rel) in indice(repo), indice(repo)


def huella_archivo_por_archivo(repo, base, rutas, permitir_ausentes=False):
    raiz = M.raiz_del_repo(str(repo))
    archivos = sorted({M.normalizar(raiz, r) for r in rutas})
    por_archivo, total = {}, hashlib.sha256()
    for rel in archivos:
        diff = M.diff_de_ruta(raiz, base, rel, permitir_ausentes)
        if diff is None:
            por_archivo[rel] = M.AUSENTE
            total.update(b"<ausente>\0" + rel.encode("utf-8"))
        else:
            por_archivo[rel] = hashlib.sha256(diff).hexdigest()
            total.update(diff)
    return {"base": base, "archivos": archivos, "sha256": total.hexdigest(), "sha256_por_archivo": por_archivo}


def git_lanzados(funcion):
    lanzados, original = [], M.subprocess.run

    def espia(args, *a, **k):
        lanzados.append(list(args))
        return original(args, *a, **k)

    M.subprocess.run = espia
    try:
        resultado = funcion()
    finally:
        M.subprocess.run = original
    return resultado, lanzados


def test_la_huella_lanza_los_mismos_git_con_dos_archivos_que_con_ocho():
    cuentas = []
    for n in (2, 8):
        with git_aislado(), temporal() as t:
            archivos = {"m%d.sql" % i: "uno\n" for i in range(n)}
            repo, base = repo_con_principal(t, archivos)
            escribir(repo, {rel: "uno\ndos\n" for rel in archivos})
            huella, lanzados = git_lanzados(lambda: calc(repo, base, list(archivos)))
            assert huella == huella_archivo_por_archivo(repo, base, list(archivos)), huella
            cuentas.append(len(lanzados))
    assert cuentas[0] == cuentas[1] <= 5, "la huella lanza un git por archivo: %s" % cuentas


def test_la_huella_por_lotes_es_la_de_archivo_por_archivo_en_un_repo_mixto():
    for config in ("", CONFIG_GIT_RARA):
        with git_aislado(config), temporal() as t:
            repo, base = repo_mixto(t)
            con_un_conflicto(repo, "conflicto.sql")
            raiz = M.raiz_del_repo(str(repo))
            rutas = RUTAS_MIXTAS + ["nunca.sql"]
            esperada, por_archivo = git_lanzados(lambda: huella_archivo_por_archivo(repo, base, rutas, permitir_ausentes=True))
            huella, por_lotes = git_lanzados(lambda: M.calcular(str(repo), base, rutas, permitir_ausentes=True))
            assert huella == esperada, (config, huella, esperada)
            assert huella["sha256_por_archivo"]["nunca.sql"] == M.AUSENTE, huella
            assert len(por_lotes) < len(por_archivo) / 3, (len(por_lotes), len(por_archivo))
            assert b"G 2" in M.diff_de_ruta(raiz, base, GLOB) and b"A 2" not in M.diff_de_ruta(raiz, base, GLOB)
            if config:
                assert b"Submodule era_submodulo" in M.diff_de_ruta(raiz, base, "era_submodulo"), "control positivo: diff.submodule=log"


def test_un_recibo_con_la_huella_archivo_por_archivo_sigue_valiendo_y_nombra_solo_lo_que_cambio():
    with git_aislado(CONFIG_GIT_RARA), temporal() as t:
        repo, base = repo_mixto(t)
        viejo = huella_archivo_por_archivo(repo, base, RUTAS_MIXTAS)
        ticket = Path(t) / "T-90-h"
        recibo = ticket / "revision" / "2026-10-21-rapido" / "recibo.json"
        recibo.parent.mkdir(parents=True)
        entrada = {"ruta": M.raiz_del_repo(str(repo)), "base": base, "archivos": viejo["archivos"], "sha256": viejo["sha256"],
                   "sha256_por_archivo": viejo["sha256_por_archivo"], "modo": "rapido", "reviewers": [], "verificacion": [], "estado": "limpio"}
        recibo.write_text(json.dumps({"version": 1, "fecha": "2026-10-21", "ticket": ticket.name, "repos": [entrada]}), encoding="utf-8")
        codigo, salida, error = correr(["--check", str(recibo)])
        assert codigo == 0 and salida.split("\n")[0] == "recibo vale: 1 repo(s), %d archivo(s) (%s)" % (len(RUTAS_MIXTAS), recibo.as_posix()), (salida, error)
        escribir(repo, {"x/a.sql": "a 1\nA 2\nOTRA\n"})
        codigo, salida, _ = correr(["--check", str(recibo)])
        assert codigo == 1 and "  repo %s: divergen x/a.sql\n" % entrada["ruta"] in salida, salida


def test_sellar_mira_cada_ruta_como_literal_con_la_huella_por_lotes():
    with git_aislado(), temporal() as t:
        repo, base = repo_con_principal(t, {"x/a.sql": "a\n", GLOB: "g\n"})
        escribir(repo, {"x/a.sql": "a\nA\n", GLOB: "g\nG\n"})
        ticket = Path(t) / "T-91-s"
        ticket.mkdir()
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "x" / "a.sql", repo / "x" / "[ab].sql"],
                                                  ["--fecha", "2026-10-21", "--estado", "limpio"]))
        assert codigo == 0, (salida, error)
        _git(repo, "--literal-pathspecs", "add", "--", "x/a.sql")
        _git(repo, "commit", "-q", "-m", "solo a")
        codigo, salida, _ = correr(["--sellar", str(ticket)])
        raiz = M.raiz_del_repo(str(repo))
        assert codigo == 1 and salida.split("\n")[:2] == [
            "recibo NO se sella (%s): hay archivos revisados sin commitear" % (ticket / "revision" / "2026-10-21-rapido" / "recibo.json").as_posix(),
            "  repo %s: %s" % (raiz, GLOB)], salida
        head = commitear(repo, {})
        codigo, salida, _ = correr(["--sellar", str(ticket)])
        assert codigo == 0 and "(%s en 1 repo(s))" % head[:10] in salida, salida


SKILL_REVISAR =AQUI.parent / "skills" / "revisar" / "SKILL.md"
REFERENCIAS_DE_REVISAR = SKILL_REVISAR.parent / "references"
REFERENCIA_RE = re.compile(r"references/([\w.-]+\.md)")
NUCLEO_MAXIMO = 17 * 1024
ID_LITERAL_RE = re.compile(r"\b[A-Z][A-Z0-9]*-[0-9]{2,}\b")
FORMATO_CON_ID = "[SEVERIDAD] <ID de la regla | sin ID> ruta:línea — qué viola — cómo debe quedar"
RENDIMIENTO = ("Rendimiento: <n> hallazgos · acuerdo 3/3 <a>, 2/3 <b>, 1/3 <c> · "
               "CRITICAL <x>, WARNING <y>, SUGGESTION <z> · destino: pendiente")
DESTINO = "destino: corregidos <c>, derivados <d>, descartados <e>"


def seccion_de(texto, titulo):
    nivel = len(titulo) - len(titulo.lstrip("#"))
    partes, dentro, en_bloque = [], False, False
    for linea in texto.split("\n"):
        if linea.lstrip().startswith("```"):
            en_bloque = not en_bloque
        elif not en_bloque and linea.startswith("#"):
            if dentro and len(linea) - len(linea.lstrip("#")) <= nivel:
                break
            dentro = dentro or linea.startswith(titulo)
        if dentro:
            partes.append(linea)
    assert partes, "la skill no tiene la sección %r" % titulo
    return "\n".join(partes)


def texto_de_revisar(titulo=None):
    nucleo = SKILL_REVISAR.read_text(encoding="utf-8")
    parte = nucleo if titulo is None else seccion_de(nucleo, titulo)
    referencias = [(REFERENCIAS_DE_REVISAR / nombre).read_text(encoding="utf-8")
                   for nombre in sorted(set(REFERENCIA_RE.findall(parte)))]
    return "\n\n".join([parte, *referencias])


def bloques_de_codigo(texto):
    bloques, actual = [], None
    for linea in texto.split("\n"):
        if linea.lstrip().startswith("```"):
            if actual is None:
                actual = []
            else:
                bloques.append("\n".join(actual))
                actual = None
        elif actual is not None:
            actual.append(linea.strip())
    return bloques


def test_s3_el_nucleo_de_revisar_cabe_en_lo_que_claude_code_vuelve_a_adjuntar_tras_compactar():
    tamano = len(SKILL_REVISAR.read_bytes())
    assert tamano < NUCLEO_MAXIMO, "el SKILL.md de revisar pesa %d bytes, %d o más: el detalle va a references/" % (
        tamano, NUCLEO_MAXIMO)


def test_s3_cada_reference_de_revisar_existe_la_nombra_el_nucleo_y_usa_el_marcador_de_los_scripts():
    assert REFERENCIA_RE.findall("lee `references/a-b.md` y references/c.md") == ["a-b.md", "c.md"], "control positivo"
    nombradas = set(REFERENCIA_RE.findall(SKILL_REVISAR.read_text(encoding="utf-8")))
    archivos = {r.name for r in REFERENCIAS_DE_REVISAR.glob("*.md")} if REFERENCIAS_DE_REVISAR.is_dir() else set()
    assert nombradas, "el núcleo de revisar no nombra ninguna reference"
    assert nombradas == archivos, "nombradas sin archivo: %s; archivos que el núcleo no nombra: %s" % (
        sorted(nombradas - archivos), sorted(archivos - nombradas))
    for nombre in sorted(archivos):
        texto = (REFERENCIAS_DE_REVISAR / nombre).read_text(encoding="utf-8")
        assert "${CLAUDE_PLUGIN_ROOT}" not in texto, "%s usa ${CLAUDE_PLUGIN_ROOT}, que solo se reemplaza en el SKILL.md" % nombre
        comandos = [linea for linea in texto.split("\n") if re.search(r"python3? \"", linea)]
        assert all('"<S>/' in linea for linea in comandos), (nombre, comandos)


def test_el_prompt_de_revisar_pide_el_id_de_la_regla_sin_un_id_literal():
    prompts = [b for b in bloques_de_codigo(texto_de_revisar("## 4.")) if b.startswith("Revisa ")]
    assert len(prompts) == 1, prompts
    prompt = prompts[0]
    assert FORMATO_CON_ID in prompt and "sin ID" in prompt, prompt
    literal = ID_LITERAL_RE.search(prompt)
    assert literal is None, "el prompt nombra un ID literal: %s" % (literal and literal.group(0))
    assert ID_LITERAL_RE.search(prompt.replace("<ID de la regla | sin ID>", "SQL-01")), "control positivo: un ID literal se detecta"
    consolidacion = texto_de_revisar("## 7.")
    assert "unidos por ubicación y regla" in consolidacion and "con ID, la regla es su ID" in consolidacion, consolidacion


def test_la_consolidacion_abre_con_el_rendimiento_y_el_recibo_completa_su_destino():
    consolidacion = texto_de_revisar("## 7.")
    assert RENDIMIENTO in bloques_de_codigo(consolidacion), bloques_de_codigo(consolidacion)
    assert "solo en `completo`" in consolidacion and "primera línea de `consolidado.md`" in consolidacion, consolidacion
    recibo = texto_de_revisar("## 8.")
    assert DESTINO in recibo and "`con-hallazgos` o `limpio`" in recibo, recibo


OPCION_RE = re.compile(r"(?<![\w-])--[a-z][a-z-]*")


def opciones_de_recibo_en(texto):
    nombradas = set()
    for bloque in bloques_de_codigo(texto):
        for linea in bloque.split("\n"):
            if "recibo.py" in linea:
                nombradas |= set(OPCION_RE.findall(linea.split("recibo.py", 1)[1]))
    return nombradas


def test_las_opciones_de_recibo_que_da_la_skill_revisar_existen_y_traen_la_bajada():
    texto = texto_de_revisar()
    opciones = {o for accion in M._parser()._actions for o in accion.option_strings}
    nombradas = opciones_de_recibo_en(texto)
    assert nombradas <= opciones, "la skill da opciones que recibo.py no tiene: %s" % sorted(nombradas - opciones)
    paso_8 = opciones_de_recibo_en(texto_de_revisar("## 8."))
    assert {"--write", "--check", "--bajada", "--va-a-lider"} <= paso_8, sorted(paso_8)
    mutada = opciones_de_recibo_en(texto.replace("--va-a-lider", "--va-al-lider", 1))
    assert mutada - opciones == {"--va-al-lider"}, "control positivo: una opción que no existe se detecta"


LIMITE_DE_CONCURRENCIA = ("**Un lanzamiento que el host rechaza por su límite de concurrencia no es una corrida cortada.**",
                          "«agent thread limit reached»", "`agents.max_threads`", "`max_concurrent_threads_per_session - 1`",
                          "5 corridas o más", "en todos los hosts")
PASOS_DE_LA_TANDA = ("espera a que termine una corrida en marcha", "ciérrala", "`close_agent`", "relanza la rechazada",
                     "la revisión va por tandas")


def test_revisar_relanza_por_tandas_lo_que_el_host_rechaza_por_su_limite_de_concurrencia():
    corridas, rescate = texto_de_revisar("## 4."), texto_de_revisar("## 6.")
    for frase in LIMITE_DE_CONCURRENCIA + PASOS_DE_LA_TANDA:
        assert frase in corridas, (frase, corridas)
    posiciones = [corridas.index(paso) for paso in PASOS_DE_LA_TANDA]
    assert posiciones == sorted(posiciones), "los pasos de la tanda van en orden: %s" % posiciones
    assert "límite de concurrencia" in rescate and "no es una corrida cortada" in rescate, rescate


SENALES_DEL_TRIAJE = ("efecto", "consumidores", "dinero", "migracion", "contrato", "capas")
CLAVES_DEL_REPO = ["ruta", "base", "archivos", "sha256", "sha256_por_archivo", "modo", "reviewers", "verificacion", "estado"]


def triaje_con(modo="completo", positivas=("capas",), invalidas=("consumidores",), sin_capa=True, unico=True):
    senales = {s: {"nivel": "positiva" if s in positivas else "invalida" if s in invalidas else "negativa", "detalle": []}
               for s in SENALES_DEL_TRIAJE}
    motivos = ["señal %s: %s" % (s, senales[s]["nivel"]) for s in SENALES_DEL_TRIAJE if senales[s]["nivel"] != "negativa"]
    aviso = {"id": "capas-cobertura", "detalle": "extensiones sin capa en el cambio: .txt (1)", "ayuda": "declara la capa"}
    return {"senales": senales, "modo": modo, "motivos": motivos,
            "sin_capa": {"archivos": ["c.txt"], "unico_motivo_de_capas": unico, "aviso": aviso} if sin_capa else None}


def repo_del_triaje(repo, base, archivos=None, capas=None):
    entrada = {"ruta": Path(repo).as_posix(), "base": base, "archivos": []}
    if archivos is None:
        return entrada
    huella = M.calcular(str(repo), base, archivos)
    entrada["archivos"] = [{"ruta": a, "estado": "M", "capa": (capas or {}).get(a), "origen": "repo"} for a in huella["archivos"]]
    entrada.update(sha256=huella["sha256"], sha256_por_archivo=huella["sha256_por_archivo"])
    return entrada


def guardar_triaje(carpeta, datos, codificacion="utf-8", repos=None):
    entrada = Path(carpeta) / "entrada"
    entrada.mkdir(parents=True, exist_ok=True)
    if repos is not None and isinstance(datos, dict):
        datos = {"repos": [repo_del_triaje(*r) for r in repos], **datos}
    texto = datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False, indent=2)
    (entrada / "triaje.json").write_bytes(texto.encode(codificacion))


def bajar(motivo="solo c.txt sin capa", lider="no"):
    return ["--bajada", motivo, "--va-a-lider", lider]


def unidad_bajada(t, nombre="T-30-b"):
    repo, base = repo_con_principal(t, ARCHIVOS)
    escribir(repo, {"a.sql": "linea 1\nCAMBIO\nlinea 3\n", "c.txt": "ajeno cambiado\n"})
    ticket = Path(t) / nombre
    ticket.mkdir()
    return repo, base, ticket, ticket / "revision" / "2026-10-21-rapido"


def recibos_de(ticket):
    revision = Path(ticket) / "revision"
    return sorted(p.relative_to(revision).as_posix() for p in revision.rglob("recibo.json")) if revision.is_dir() else []


def bytes_de(ticket):
    revision = Path(ticket) / "revision"
    return {p.relative_to(revision).as_posix(): p.read_bytes() for p in revision.rglob("*") if p.is_file()} if revision.is_dir() else {}


# ---------------------------------------------------------------- el triaje que respalda el modo (integridad del recibo, S1 a S3)

LIMPIO = dict(positivas=(), invalidas=(), sin_capa=False)


def vaciar_revision(ticket):
    for vieja in (Path(ticket) / "revision").glob("*") if (Path(ticket) / "revision").is_dir() else []:
        shutil.rmtree(vieja, onexc=_quitar)


def test_s1_la_bajada_compara_los_archivos_y_la_huella_del_triaje_y_si_difieren_no_escribe_nada():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        r = Path(repo).as_posix()
        dos = ["a.sql", "c.txt"]
        casos = [
            ("el recibo trae un archivo que el triaje no", ["a.sql"], dos, "%s: el triaje no trae c.txt" % r),
            ("el triaje no trae la huella", None, dos, "%s: el triaje no trae la huella del diff" % r),
        ]
        for nombre, del_triaje, del_recibo, esperado in casos:
            vaciar_revision(ticket)
            guardar_triaje(carpeta, triaje_con(), repos=[(repo, base) if del_triaje is None else (repo, base, del_triaje)])
            antes = bytes_de(ticket)
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / a for a in del_recibo], ["--fecha", "2026-10-21", *bajar()]))
            assert codigo == 2 and salida == "" and "no es de este diff" in error and "corre el triaje de nuevo" in error, (nombre, codigo, salida, error)
            assert esperado in error.replace("\\", "/"), (nombre, esperado, error)
            assert error.replace("\\", "/").endswith("con un --repo por cada repo del recibo: --repo %s#%s\n" % (r, base)), (nombre, error)
            assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, (nombre, recibos_de(ticket))
        vaciar_revision(ticket)
        guardar_triaje(carpeta, triaje_con(), repos=[(repo, base, dos)])
        argv = args_write(ticket, [repo], [repo / a for a in dos], ["--fecha", "2026-10-21", *bajar()])
        codigo, salida, error = correr(argv)
        assert codigo == 0 and salida.endswith("; bajado de completo a rapido)\n"), "antes de la edicion, la bajada vale: %s" % error
        (carpeta / "recibo.json").unlink()
        escribir(repo, {"a.sql": "linea 1\nOTRA EDICION\nlinea 3\n"})
        antes = bytes_de(ticket)
        codigo, salida, error = correr(argv)
        assert codigo == 2 and salida == "" and "%s: a.sql cambio despues del triaje" % r in error.replace("\\", "/"), (codigo, salida, error)
        assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, recibos_de(ticket)


def test_s1_un_rechequeo_que_hereda_la_bajada_con_un_triaje_anterior_a_la_ultima_edicion_no_escribe_nada():
    with temporal() as t:
        repo, base, ticket, primera = unidad_bajada(t)
        dos = ["a.sql", "c.txt"]
        guardar_triaje(primera, triaje_con(), repos=[(repo, base, dos)])
        assert correr(args_write(ticket, [repo], [repo / a for a in dos], ["--fecha", "2026-10-21", "--estado", "pendiente", *bajar()]))[0] == 0
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        segunda = ticket / "revision" / "2026-10-21-rapido-2"
        guardar_triaje(segunda, triaje_con(), repos=[(repo, base, dos)])
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO OTRA VEZ\nlinea 3\n"})
        argv = args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--ronda", "2", "--previo", str(primera)])
        antes = bytes_de(ticket)
        codigo, salida, error = correr(argv)
        assert codigo == 2 and salida == "" and "a.sql cambio despues del triaje" in error, (codigo, salida, error)
        assert recibos_de(ticket) == ["2026-10-21-rapido/recibo.json"] and bytes_de(ticket) == antes, recibos_de(ticket)
        guardar_triaje(segunda, triaje_con(), repos=[(repo, base, dos)])
        codigo, salida, error = correr(argv)
        assert codigo == 0 and salida.endswith("; bajado de completo a rapido)\n"), (salida, error)


def aviso_de_lo_no_cubierto(carpeta, *partes):
    return ("recibo: aviso, el triaje de %s vio cambios que el recibo no cubre: %s; si son de esta unidad, se revisan y van con --archivo\n"
            % ((Path(carpeta) / "entrada" / "triaje.json").as_posix(), "; ".join(partes)))


def test_f4_la_bajada_vale_si_el_recibo_cubre_parte_de_lo_que_vio_el_triaje_y_avisa_lo_que_no_cubre():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        otro, base_otro = repo_con_principal(t, {"x.cs": "class X {}\n"}, nombre="otro")
        escribir(otro, {"x.cs": "class X { int y; }\n"})
        r, o = Path(repo).as_posix(), Path(otro).as_posix()
        guardar_triaje(carpeta, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"]), (otro, base_otro, ["x.cs"])])
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", *bajar()]))
        assert codigo == 0 and salida.endswith("; bajado de completo a rapido)\n"), (codigo, salida, error)
        assert error.replace("\\", "/") == aviso_de_lo_no_cubierto(carpeta, "%s: c.txt" % r, "%s (todo el repo): x.cs" % o), error
        recibo = json.loads((carpeta / "recibo.json").read_text(encoding="utf-8"))
        assert [(e["ruta"], e["archivos"]) for e in recibo["repos"]] == [(r, ["a.sql"])], recibo["repos"]
        assert recibo["bajada"]["de"] == "completo" and recibo["bajada"]["a"] == "rapido", recibo


def test_f4_sin_bajada_un_triaje_que_vio_mas_archivos_deja_escribir_el_modo_que_propuso_y_avisa():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        guardar_triaje(carpeta, triaje_con(modo="rapido", **LIMPIO), repos=[(repo, base, ["a.sql", "c.txt"])])
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--modo", "rapido"]))
        assert codigo == 0 and "bajado" not in salida, (codigo, salida, error)
        assert error.replace("\\", "/") == aviso_de_lo_no_cubierto(carpeta, "%s: c.txt" % Path(repo).as_posix()), error
        assert recibos_de(ticket) == ["2026-10-21-rapido/recibo.json"], recibos_de(ticket)


def test_reescribir_un_recibo_bajado_sin_repetir_la_bajada_la_conserva_y_con_otro_triaje_no_escribe():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        archivos = [repo / "a.sql", repo / "c.txt"]
        guardar_triaje(carpeta, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        assert correr(args_write(ticket, [repo], archivos, ["--fecha", "2026-10-21", "--estado", "pendiente", *bajar()]))[0] == 0
        antes = json.loads((carpeta / "recibo.json").read_text(encoding="utf-8"))
        codigo, salida, error = correr(args_write(ticket, [repo], archivos, ["--fecha", "2026-10-21", "--estado", "con-hallazgos"]))
        assert codigo == 0 and error == "" and salida.endswith("; bajado de completo a rapido)\n"), (codigo, salida, error)
        despues = json.loads((carpeta / "recibo.json").read_text(encoding="utf-8"))
        assert despues["bajada"] == antes["bajada"] and [e["estado"] for e in despues["repos"]] == ["con-hallazgos"], despues
        guardar_triaje(carpeta, triaje_con(positivas=("efecto", "capas")), repos=[(repo, base, ["a.sql", "c.txt"])])
        crudo = (carpeta / "recibo.json").read_bytes()
        codigo, salida, error = correr(args_write(ticket, [repo], archivos, ["--fecha", "2026-10-21", "--estado", "limpio"]))
        assert codigo == 2 and salida == "" and "riesgo real" in error, (codigo, salida, error)
        assert (carpeta / "recibo.json").read_bytes() == crudo


def test_f3_sin_bajada_un_triaje_anterior_a_la_ultima_edicion_no_deja_escribir_rapido_y_completo_si():
    with temporal() as t:
        repo, base, ticket, _ = unidad_bajada(t)
        dos = ["a.sql", "c.txt"]
        revision = ticket / "revision"
        for modo in ("rapido", "completo"):
            guardar_triaje(revision / ("2026-10-21-" + modo), triaje_con(modo="rapido", **LIMPIO), repos=[(repo, base, dos)])
        escribir(repo, {"a.sql": "linea 1\nOTRA EDICION\nlinea 3\n"})
        antes = bytes_de(ticket)
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / a for a in dos], ["--fecha", "2026-10-21", "--modo", "rapido"]))
        assert codigo == 2 and salida == "" and "corre el triaje de nuevo" in error, (codigo, salida, error)
        assert "%s: a.sql cambio despues del triaje" % Path(repo).as_posix() in error.replace("\\", "/"), error
        assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, recibos_de(ticket)
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / a for a in dos], ["--fecha", "2026-10-21", "--modo", "completo"]))
        assert codigo == 0 and error == "", "con --modo completo no hay piso que violar: %s" % error
        assert recibos_de(ticket) == ["2026-10-21-completo/recibo.json"], recibos_de(ticket)


def test_s2_el_triaje_guardado_trae_las_seis_senales_y_el_modo_que_dan_sus_senales_y_archivos():
    with temporal() as t:
        repo, base, ticket, _ = unidad_bajada(t)
        cinco, siete = triaje_con(), triaje_con()
        del cinco["senales"]["efecto"]
        siete["senales"]["otra"] = {"nivel": "negativa", "detalle": []}
        taller = {"ruta": Path(t, "T-30-b", "SQL", "esq.Proc.sql").as_posix(), "capa": "sql", "origen": "taller", "contraparte": None}
        rapido, cero, completo = (["--fecha", "2026-10-21", "--modo", m] for m in ("rapido", "0", "completo"))
        casos = [
            ("le falta una senal", cinco, ["a.sql", "c.txt"], [*rapido, *bajar()], "las seis senales"),
            ("le sobra una senal", siete, ["a.sql", "c.txt"], [*rapido, *bajar()], "las seis senales"),
            ("completo con todas en negativo", triaje_con(**LIMPIO), ["a.sql", "c.txt"], [*rapido, *bajar()],
             "propone completo, y sus senales y archivos dan rapido"),
            ("rapido con una invalida, sin --bajada", triaje_con(modo="rapido"), ["a.sql", "c.txt"], rapido,
             "propone rapido, y sus senales y archivos dan completo"),
            ("0 con un archivo que no es doc", triaje_con(modo="0", **LIMPIO), ["a.sql", "c.txt"], cero,
             "propone 0, y sus senales y archivos dan rapido"),
            ("rapido sin archivos, con --modo completo, que valida sin atar al diff", triaje_con(modo="rapido", **LIMPIO), [], completo,
             "propone rapido, y sus senales y archivos dan sin-cambios"),
            ("rapido con solo docs", triaje_con(modo="rapido", **LIMPIO), ["c.txt"], rapido, "propone rapido, y sus senales y archivos dan 0"),
            ("un archivo del triaje sin ruta", dict(triaje_con(**LIMPIO, modo="rapido"), taller=[{"capa": "sql"}]), ["a.sql"], rapido,
             "repos y taller"),
        ]
        for nombre, triaje, archivos, extra, esperado in casos:
            vaciar_revision(ticket)
            guardar_triaje(ticket / "revision" / ("2026-10-21-" + extra[3]), triaje, repos=[(repo, base, archivos)])
            antes = bytes_de(ticket)
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / a for a in archivos or ["a.sql"]], extra))
            assert codigo == 2 and salida == "" and "triaje con forma invalida" in error and esperado in error, (nombre, codigo, salida, error)
            assert "entrada/triaje.json" in error.replace("\\", "/"), (nombre, error)
            assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, (nombre, recibos_de(ticket))
        vaciar_revision(ticket)
        con_taller = dict(triaje_con(modo="rapido", **LIMPIO), taller=[taller])
        guardar_triaje(ticket / "revision" / "2026-10-21-rapido", con_taller, repos=[(repo, base, ["c.txt"])])
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "c.txt"], rapido))
        assert codigo == 0 and error == "", "un archivo del taller que no es doc da rapido, como en el triaje: %s" % error


def test_s2_la_bajada_recalcula_si_sin_capa_es_el_unico_motivo_de_capas_desde_los_archivos():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        escribir(repo, {"b.cs": "class B { int x; }\n", "Makefile": "todo:\n"})
        tres = ["Makefile", "a.sql", "b.cs"]
        argv = args_write(ticket, [repo], [repo / a for a in tres], ["--fecha", "2026-10-21", *bajar()])
        casos = [
            ("dos capas y un sin capa, aunque el json diga unico", triaje_con(unico=True), tres, {"a.sql": "sql", "b.cs": "cs"}),
            ("un doc sin capa no es un archivo sin capa", triaje_con(unico=True), ["a.sql", "c.txt"], {"a.sql": "sql"}),
        ]
        for nombre, triaje, archivos, capas in casos:
            vaciar_revision(ticket)
            guardar_triaje(carpeta, triaje, repos=[(repo, base, archivos, capas)])
            antes = bytes_de(ticket)
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / a for a in archivos], ["--fecha", "2026-10-21", *bajar()]))
            assert codigo == 2 and salida == "" and "senal capas: positiva" in error, (nombre, codigo, salida, error)
            assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, (nombre, recibos_de(ticket))
        vaciar_revision(ticket)
        guardar_triaje(carpeta, triaje_con(unico=False), repos=[(repo, base, tres, {"a.sql": "sql", "b.cs": "sql"})])
        codigo, salida, error = correr(argv)
        assert codigo == 0 and salida.endswith("; bajado de completo a rapido)\n"), "una capa y un sin capa, aunque el json diga que no: %s" % error


def test_s2_la_skill_revisar_dice_que_el_triaje_y_el_recibo_no_se_editan_a_mano():
    entrada = texto_de_revisar("## 3.")
    assert "`triaje.json` y `recibo.json` no se editan a mano" in entrada, entrada


def test_s3_sin_bajada_el_modo_no_baja_del_que_propuso_el_triaje_guardado():
    with temporal() as t:
        repo, base, ticket, _ = unidad_bajada(t)
        dos = ["a.sql", "c.txt"]
        casos = [
            ("completo", triaje_con(), "rapido", 2),
            ("completo", triaje_con(), "0", 2),
            ("rapido", triaje_con(modo="rapido", **LIMPIO), "0", 2),
            ("completo", triaje_con(), "completo", 0),
            ("rapido", triaje_con(modo="rapido", **LIMPIO), "rapido", 0),
            ("rapido", triaje_con(modo="rapido", **LIMPIO), "completo", 0),
        ]
        for propuesto, triaje, modo, sale in casos:
            vaciar_revision(ticket)
            guardar_triaje(ticket / "revision" / ("2026-10-21-" + modo), triaje, repos=[(repo, base, dos)])
            antes = bytes_de(ticket)
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / a for a in dos], ["--fecha", "2026-10-21", "--modo", modo]))
            if sale == 2:
                assert codigo == 2 and salida == "" and "--modo %s es mas bajo que el %s que propuso el triaje" % (modo, propuesto) in error, \
                    (propuesto, modo, codigo, salida, error)
                assert "--bajada" in error and recibos_de(ticket) == [] and bytes_de(ticket) == antes, (propuesto, modo, recibos_de(ticket))
            else:
                assert codigo == 0 and error == "" and "bajado" not in salida, (propuesto, modo, salida, error)
                assert recibos_de(ticket) == ["2026-10-21-%s/recibo.json" % modo], recibos_de(ticket)


def test_s3_un_rechequeo_no_baja_del_modo_del_recibo_previo_ni_con_una_fecha_posterior():
    with temporal() as t:
        repo, base, ticket, primera = primera_ronda(t)
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})

        def de_nuevo(fecha, modo, *extra):
            return args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", fecha, "--modo", modo, "--previo", str(primera), *extra])

        for fecha, modo, extra in (("2026-10-21", "rapido", ["--ronda", "2"]), ("2026-10-22", "rapido", []), ("2026-10-22", "0", [])):
            antes = bytes_de(ticket)
            codigo, salida, error = correr(de_nuevo(fecha, modo, *extra))
            assert codigo == 2 and salida == "", (fecha, modo, codigo, salida, error)
            assert "--modo %s es mas bajo que el completo del recibo previo revision/2026-10-21-completo" % modo in error, (fecha, modo, error)
            assert recibos_de(ticket) == ["2026-10-21-completo/recibo.json"] and bytes_de(ticket) == antes, (fecha, modo, recibos_de(ticket))
        codigo, salida, error = correr(de_nuevo("2026-10-22", "completo"))
        assert codigo == 0 and error == "", (salida, error)
        assert recibos_de(ticket) == ["2026-10-21-completo/recibo.json", "2026-10-22-completo/recibo.json"], recibos_de(ticket)


def test_s3_un_rechequeo_despues_de_una_bajada_no_baja_a_0():
    with temporal() as t:
        repo, base, ticket, primera = unidad_bajada(t)
        dos = ["a.sql", "c.txt"]
        guardar_triaje(primera, triaje_con(), repos=[(repo, base, dos)])
        assert correr(args_write(ticket, [repo], [repo / a for a in dos], ["--fecha", "2026-10-21", "--estado", "pendiente", *bajar()]))[0] == 0
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        for fecha, extra in (("2026-10-21", ["--ronda", "2"]), ("2026-10-22", [])):
            antes = bytes_de(ticket)
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"],
                                                      ["--fecha", fecha, "--modo", "0", "--previo", str(primera), *extra]))
            assert codigo == 2 and salida == "", (fecha, codigo, salida, error)
            assert "--modo 0 es mas bajo que el rapido del recibo previo revision/2026-10-21-rapido" in error, (fecha, error)
            assert recibos_de(ticket) == ["2026-10-21-rapido/recibo.json"] and bytes_de(ticket) == antes, (fecha, recibos_de(ticket))


# ---------------------------------------------------------------- la bajada de un escalón (I34)

def test_bajada_de_completo_a_rapido_guarda_el_motivo_y_la_respuesta_del_lider():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        guardar_triaje(carpeta, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"], [
            "--fecha", "2026-10-21", "--derivado", "h en a.sql:2=T9", *bajar("  solo c.txt, sin capa: config de la instancia  ")]))
        assert codigo == 0 and error == "", (salida, error)
        assert salida.endswith("(1 repo(s), 2 archivo(s); 1 derivado(s); bajado de completo a rapido)\n"), salida
        datos = json.loads((carpeta / "recibo.json").read_text(encoding="utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "repos", "derivados", "bajada"], list(datos)
        assert datos["bajada"] == {"de": "completo", "a": "rapido", "motivo": "solo c.txt, sin capa: config de la instancia",
                                   "va_a_lider": False}, datos["bajada"]
        assert list(datos["repos"][0]) == CLAVES_DEL_REPO and datos["repos"][0]["modo"] == "rapido", datos["repos"][0]
        assert datos["repos"][0]["sha256"] == calc(repo, base, ["a.sql", "c.txt"])["sha256"]
        (carpeta / "recibo.json").unlink()
        guardar_triaje(carpeta, triaje_con(positivas=(), invalidas=("consumidores", "efecto"), sin_capa=False), "utf-16",
                       repos=[(repo, base, ["a.sql"])])
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", *bajar("solo inválidas")]))
        assert codigo == 0 and salida.endswith("(1 repo(s), 1 archivo(s); bajado de completo a rapido)\n"), (salida, error)
        datos = json.loads((carpeta / "recibo.json").read_text(encoding="utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "repos", "bajada"] and datos["bajada"]["motivo"] == "solo inválidas", datos


GITHUB = "gh" + "p_" + ("aB3dE5fG7h" * 4)[:36]
AWS = "AK" + "IA" + "Z7Q4X2W9R5T8Y3U6"


def test_el_recibo_guarda_tapados_los_secretos_del_texto_libre_y_sigue_valiendo():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        guardar_triaje(carpeta, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"], [
            "--fecha", "2026-10-21", "--verificacion", "curl -H 'Authorization: token %s' x: 200" % GITHUB,
            "--derivado", "clave %s en a.sql:2=T9" % AWS, *bajar("solo c.txt sin capa; la clave era " + AWS)]))
        assert codigo == 0 and error == "", (salida, error)
        assert salida.endswith("(1 repo(s), 2 archivo(s); 1 derivado(s); bajado de completo a rapido; 3 secreto(s) tapado(s))\n"), salida
        crudo = (carpeta / "recibo.json").read_text(encoding="utf-8")
        assert GITHUB not in crudo and AWS not in crudo, crudo
        datos = json.loads(crudo)
        assert datos["repos"][0]["verificacion"] == ["curl -H 'Authorization: token <GITHUB_TOKEN>' x: 200"], datos["repos"][0]
        assert datos["derivados"] == [{"hallazgo": "clave <AWS_ACCESS_KEY_ID> en a.sql:2", "destino": "T9"}], datos["derivados"]
        assert datos["bajada"] == {"de": "completo", "a": "rapido", "motivo": "solo c.txt sin capa; la clave era <AWS_ACCESS_KEY_ID>",
                                   "va_a_lider": False}, datos["bajada"]
        assert datos["repos"][0]["sha256"] == calc(repo, base, ["a.sql", "c.txt"])["sha256"]
        assert correr(["--check", str(carpeta)])[0] == 0
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"], [
            "--fecha", "2026-10-21", "--estado", "con-hallazgos"]))
        assert codigo == 0 and salida.endswith("bajado de completo a rapido)\n"), (salida, error)
        assert json.loads((carpeta / "recibo.json").read_text(encoding="utf-8"))["bajada"] == datos["bajada"]


def test_una_bajada_que_no_vale_es_error_de_uso_y_no_escribe_nada():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        rapido, completo, cero = (["--fecha", "2026-10-21", "--modo", m] for m in ("rapido", "completo", "0"))
        limpio = dict(positivas=(), invalidas=(), sin_capa=False)
        casos = [
            ("rapido a rapido", triaje_con(modo="rapido", **limpio), rapido, bajar(), "escalon"),
            ("completo a completo", triaje_con(), completo, bajar(), "escalon"),
            ("completo a 0", triaje_con(), cero, bajar(), "escalon"),
            ("0 a 0", triaje_con(modo="0", **limpio), cero, bajar(), "escalon", (["c.txt"], None)),
            ("efecto positiva", triaje_con(positivas=("efecto", "capas")), rapido, bajar(), "efecto"),
            ("consumidores positiva", triaje_con(positivas=("consumidores",), invalidas=(), sin_capa=False), rapido, bajar(), "consumidores"),
            ("mas de una capa", triaje_con(sin_capa=False), rapido, bajar(), "capas", (["a.sql"], {"a.sql": "sql"})),
            ("sin --va-a-lider", triaje_con(), rapido, ["--bajada", "motivo"], "--va-a-lider"),
            ("va a un lider", triaje_con(), rapido, bajar(lider="si"), "lider"),
            ("--va-a-lider sin --bajada", triaje_con(), rapido, ["--va-a-lider", "no"], "--va-a-lider"),
            ("motivo vacio", triaje_con(), rapido, bajar(motivo=""), "--bajada"),
            ("motivo en blanco", triaje_con(), rapido, bajar(motivo="   "), "--bajada"),
            ("lider invalido", triaje_con(), rapido, bajar(lider="tal vez"), "--va-a-lider"),
            ("sin triaje", None, rapido, bajar(), "entrada/triaje.json"),
            ("triaje roto", "{roto", rapido, bajar(), "entrada/triaje.json"),
            ("triaje sin senales", {"modo": "completo"}, rapido, bajar(), "entrada/triaje.json"),
            ("triaje que es una lista", "[]", rapido, bajar(), "entrada/triaje.json"),
            ("nivel desconocido", {"modo": "completo", "senales": {"capas": {"nivel": "alta"}}}, rapido, bajar(), "entrada/triaje.json"),
        ]
        for nombre, triaje, modo, extra, esperado, *resto in casos:
            archivos, capas = resto[0] if resto else (["a.sql"], None)
            for vieja in (ticket / "revision").glob("*") if (ticket / "revision").is_dir() else []:
                shutil.rmtree(vieja, onexc=_quitar)
            if triaje is not None:
                guardar_triaje(ticket / "revision" / ("2026-10-21-" + modo[-1]), triaje, repos=[(repo, base, archivos, capas)])
            antes = bytes_de(ticket)
            codigo, salida, error = correr(args_write(ticket, [repo], [repo / a for a in archivos], [*modo, *extra]))
            assert codigo == 2 and salida == "" and esperado in error.replace("\\", "/"), (nombre, codigo, salida, error)
            assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, (nombre, recibos_de(ticket))
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21"]))
        assert codigo == 2 and salida == "" and "entrada/triaje.json" in error.replace("\\", "/"), \
            "sin --bajada, el triaje guardado tambien se valida: %s" % error
        assert recibos_de(ticket) == [], recibos_de(ticket)


def test_sin_bajada_un_triaje_del_diff_que_no_propone_mas_deja_los_mismos_bytes_y_uno_mas_alto_roto_o_de_otro_diff_no_escribe():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        argv = args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"], ["--fecha", "2026-10-21", "--estado", "limpio"])
        codigo, salida_sin, _ = correr(argv)
        assert codigo == 0
        sin_triaje = (carpeta / "recibo.json").read_bytes()
        limpio = triaje_con(modo="rapido", positivas=(), invalidas=(), sin_capa=False)
        sin_huella = repo_del_triaje(repo, base, ["a.sql", "c.txt"])
        del sin_huella["sha256"], sin_huella["sha256_por_archivo"]
        guardar_triaje(carpeta, {**limpio, "repos": [repo_del_triaje(repo, base, ["a.sql", "c.txt"])]})
        codigo, salida, error = correr(argv)
        assert codigo == 0 and error == "" and salida == salida_sin, (salida, error)
        assert (carpeta / "recibo.json").read_bytes() == sin_triaje
        de_otro_diff = (({**limpio, "repos": [sin_huella]}, "el triaje no trae la huella del diff"),
                        ({**triaje_con(modo="0", positivas=(), invalidas=(), sin_capa=False), "repos": [repo_del_triaje(repo, base, ["c.txt"])]},
                         "el triaje no trae a.sql"))
        for triaje, esperado in ((triaje_con(), "--modo rapido es mas bajo que el completo que propuso el triaje"), ("{roto", "triaje ilegible"),
                                 *de_otro_diff):
            guardar_triaje(carpeta, triaje, repos=[(repo, base, ["a.sql", "c.txt"])])
            (carpeta / "recibo.json").unlink()
            antes = bytes_de(ticket)
            codigo, salida, error = correr(argv)
            assert codigo == 2 and salida == "" and esperado in error, (codigo, salida, error)
            assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, recibos_de(ticket)
            (carpeta / "recibo.json").write_bytes(sin_triaje)


def test_check_y_sellar_valen_con_un_recibo_bajado_y_la_bajada_no_es_suya():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        guardar_triaje(carpeta, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        assert correr(args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"], ["--fecha", "2026-10-21", "--estado", "limpio", *bajar()]))[0] == 0
        recibo = carpeta / "recibo.json"
        codigo, salida, error = correr(["--check", str(carpeta)])
        assert codigo == 0 and error == "", (salida, error)
        assert salida == ("recibo vale: 1 repo(s), 2 archivo(s) (%s)\n  estado: limpio; modo: rapido; bajada: de completo a rapido "
                          "(solo c.txt sin capa)\n" % str(recibo).replace("\\", "/")), salida
        assert correr(["--check", str(ticket), "--modo", "rapido"])[0] == 0
        assert correr(["--check", str(ticket), "--modo", "completo"])[0] == 2, "el recibo es de rapido aunque el triaje propuso completo"
        crudo = recibo.read_bytes()
        for modo in (["--check", str(carpeta)], ["--sellar", str(carpeta)]):
            for extra in (["--bajada", "motivo"], ["--va-a-lider", "no"]):
                codigo, salida, error = correr(modo + extra)
                assert codigo == 2 and salida == "" and extra[0] in error, (modo, extra, codigo, salida, error)
        assert recibo.read_bytes() == crudo
        _git(repo, "add", "a.sql", "c.txt")
        _git(repo, "commit", "-q", "-m", "unidad")
        head = _git(repo, "rev-parse", "HEAD")
        codigo, salida, error = correr(["--sellar", str(carpeta)])
        assert codigo == 0, (salida, error)
        datos = json.loads(recibo.read_text(encoding="utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "repos", "bajada"] and datos["repos"][0]["sellado"] == head, datos
        assert datos["bajada"] == json.loads(crudo.decode("utf-8"))["bajada"]
        assert correr(["--check", str(carpeta)])[0] == 0


def test_un_rechequeo_despues_de_una_bajada_la_hereda_y_un_riesgo_real_nuevo_no_baja():
    with temporal() as t:
        repo, base, ticket, primera = unidad_bajada(t)
        guardar_triaje(primera, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        assert correr(args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"],
                                 ["--fecha", "2026-10-21", "--estado", "pendiente", *bajar("c.txt sin capa")]))[0] == 0
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        segunda = ticket / "revision" / "2026-10-21-rapido-2"
        argv = args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--ronda", "2", "--previo", str(primera)])
        codigo, salida, error = correr(argv)
        assert codigo == 2 and salida == "" and "entrada/triaje.json" in error.replace("\\", "/"), (codigo, salida, error)
        assert recibos_de(ticket) == ["2026-10-21-rapido/recibo.json"], recibos_de(ticket)
        guardar_triaje(segunda, triaje_con(positivas=("migracion", "capas")), repos=[(repo, base, ["a.sql", "c.txt"])])
        codigo, salida, error = correr(argv)
        assert codigo == 2 and salida == "" and "migracion" in error, (codigo, salida, error)
        assert recibos_de(ticket) == ["2026-10-21-rapido/recibo.json"], recibos_de(ticket)
        guardar_triaje(segunda, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        codigo, salida, error = correr(argv + ["--estado", "limpio"])
        assert codigo == 0 and error == "", (salida, error)
        assert salida.endswith("; 1 rechequeado(s) y 1 heredado(s) de revision/2026-10-21-rapido; bajado de completo a rapido)\n"), salida
        datos = json.loads((segunda / "recibo.json").read_text(encoding="utf-8"))
        assert list(datos) == ["version", "fecha", "ticket", "previo", "repos", "bajada"], list(datos)
        assert datos["bajada"] == {"de": "completo", "a": "rapido", "motivo": "c.txt sin capa", "va_a_lider": False}, datos["bajada"]
        assert correr(["--check", str(ticket)])[0] == 0
        tercera = ticket / "revision" / "2026-10-21-rapido-3"
        guardar_triaje(tercera, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        codigo, salida, error = correr(argv + ["--ronda", "3", *bajar("otro motivo")])
        assert codigo == 0, (salida, error)
        assert json.loads((tercera / "recibo.json").read_text(encoding="utf-8"))["bajada"]["motivo"] == "otro motivo"
        codigo, salida, error = correr(args_write(ticket, [repo], [repo / "a.sql"],
                                                  ["--fecha", "2026-10-22", "--modo", "completo", "--previo", str(primera)]))
        assert codigo == 0 and "bajado" not in salida, (salida, error)
        datos = json.loads((ticket / "revision" / "2026-10-22-completo" / "recibo.json").read_text(encoding="utf-8"))
        assert "bajada" not in datos, "un rechequeo en completo no está bajado"


def otro_repo(t):
    otro, base_otro = repo_con_principal(t, dict(ARCHIVOS, **{"d.txt": "solo del otro repo\n"}), nombre="otro")
    escribir(otro, {"b.cs": "class B { decimal Precio; }\n"})
    return otro, base_otro


def test_una_bajada_con_el_triaje_de_otro_diff_sale_con_2_y_no_escribe_nada():
    with temporal() as t:
        repo, base, ticket, carpeta = unidad_bajada(t)
        otro, base_otro = otro_repo(t)
        uno = args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"], ["--fecha", "2026-10-21", *bajar()])
        dos = args_write(ticket, [repo, otro], [repo / "a.sql", otro / "b.cs"], ["--fecha", "2026-10-21", *bajar()])
        casos = [
            ("el triaje es de otro repo", uno, [(otro, base_otro)], "%s no esta en el triaje" % Path(repo).as_posix()),
            ("el mismo repo con otra base", uno, [(repo, base_otro)],
             "%s tiene base %s en el triaje y %s en el recibo" % (Path(repo).as_posix(), base_otro, base)),
            ("el triaje no trae repos", uno, None, "%s no esta en el triaje" % Path(repo).as_posix()),
            ("al triaje le falta un repo del recibo", dos, [(repo, base)], "%s no esta en el triaje" % Path(otro).as_posix()),
        ]
        for nombre, argv, repos, esperado in casos:
            for vieja in (ticket / "revision").glob("*") if (ticket / "revision").is_dir() else []:
                shutil.rmtree(vieja, onexc=_quitar)
            guardar_triaje(carpeta, triaje_con(), repos=repos)
            antes = bytes_de(ticket)
            codigo, salida, error = correr(argv)
            assert codigo == 2 and salida == "" and "no es de este diff" in error, (nombre, codigo, salida, error)
            assert esperado in error.replace("\\", "/"), (nombre, esperado, error)
            assert recibos_de(ticket) == [] and bytes_de(ticket) == antes, (nombre, recibos_de(ticket))
        guardar_triaje(carpeta, triaje_con(), repos=[(otro, base_otro, ["b.cs"]), (repo, base, ["a.sql"])])
        codigo, salida, error = correr(dos)
        assert codigo == 0 and error == "" and salida.endswith("(2 repo(s), 2 archivo(s); bajado de completo a rapido)\n"), (salida, error)


def test_un_rechequeo_que_hereda_la_bajada_con_el_triaje_de_otro_diff_sale_con_2_y_no_escribe_nada():
    with temporal() as t:
        repo, base, ticket, primera = unidad_bajada(t)
        otro, base_otro = otro_repo(t)
        guardar_triaje(primera, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        assert correr(args_write(ticket, [repo], [repo / "a.sql", repo / "c.txt"],
                                 ["--fecha", "2026-10-21", "--estado", "pendiente", *bajar()]))[0] == 0
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        segunda = ticket / "revision" / "2026-10-21-rapido-2"
        argv = args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--ronda", "2", "--previo", str(primera)])
        for repos in ([(otro, base_otro)], [(repo, base_otro)], None):
            guardar_triaje(segunda, triaje_con(), repos=repos)
            antes = bytes_de(ticket)
            codigo, salida, error = correr(argv)
            assert codigo == 2 and salida == "" and "no es de este diff" in error, (repos, codigo, salida, error)
            assert recibos_de(ticket) == ["2026-10-21-rapido/recibo.json"] and bytes_de(ticket) == antes, (repos, recibos_de(ticket))
        guardar_triaje(segunda, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        codigo, salida, error = correr(argv)
        assert codigo == 0 and salida.endswith("; bajado de completo a rapido)\n"), (salida, error)


def test_f5_el_rechazo_de_un_rechequeo_con_un_repo_heredado_entero_nombra_todos_los_repos_del_recibo():
    with temporal() as t:
        repo, base, ticket, primera = unidad_bajada(t)
        otro, base_otro = otro_repo(t)
        de_la_unidad = [(repo, base, ["a.sql", "c.txt"]), (otro, base_otro, ["b.cs"])]
        guardar_triaje(primera, triaje_con(), repos=de_la_unidad)
        assert correr(args_write(ticket, [repo, otro], [repo / "a.sql", repo / "c.txt", otro / "b.cs"],
                                 ["--fecha", "2026-10-21", "--estado", "pendiente", *bajar()]))[0] == 0
        escribir(repo, {"a.sql": "linea 1\nCORREGIDO\nlinea 3\n"})
        segunda = ticket / "revision" / "2026-10-21-rapido-2"
        argv = args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--ronda", "2", "--previo", str(primera)])
        guardar_triaje(segunda, triaje_con(), repos=[(repo, base, ["a.sql", "c.txt"])])
        antes = bytes_de(ticket)
        codigo, salida, error = correr(argv)
        r, o = Path(repo).as_posix(), Path(otro).as_posix()
        assert codigo == 2 and salida == "" and "%s no esta en el triaje" % o in error.replace("\\", "/"), (codigo, salida, error)
        assert error.replace("\\", "/").endswith("con un --repo por cada repo del recibo: --repo %s#%s --repo %s#%s\n"
                                                 % (r, base, o, base_otro)), error
        assert recibos_de(ticket) == ["2026-10-21-rapido/recibo.json"] and bytes_de(ticket) == antes, recibos_de(ticket)
        guardar_triaje(segunda, triaje_con(), repos=de_la_unidad)
        codigo, salida, error = correr(argv)
        assert codigo == 0 and error == "" and salida.endswith("; bajado de completo a rapido)\n"), (salida, error)


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
