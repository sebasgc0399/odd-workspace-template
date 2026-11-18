import contextlib
import hashlib
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


def _entorno_sin_git():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


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


def test_pisar_un_recibo_avisa_los_repos_que_la_llamada_nueva_no_trae():
    with temporal() as t:
        r1, _ = repo_con_principal(t, ARCHIVOS, "uno")
        r2, _ = repo_con_principal(t, ARCHIVOS, "dos")
        ticket = Path(t) / "T-14-w"
        ticket.mkdir()
        comun = ["--fecha", "2026-10-21", "--modo", "rapido"]
        assert correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], comun))[0] == 0
        codigo, salida, error = correr(args_write(ticket, [r1], [r1 / "a.sql"], comun))
        assert codigo == 0, error
        assert str(r2).replace("\\", "/") in error.replace("\\", "/") and str(r1).replace("\\", "/") not in error.replace("\\", "/"), error
        datos = json.loads((ticket / "revision" / "2026-10-21-rapido" / "recibo.json").read_text(encoding="utf-8"))
        assert [r["ruta"] for r in datos["repos"]] == [str(r1).replace("\\", "/")], "pisa entero, sin merge"
        codigo, _, error = correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], comun))
        assert codigo == 0 and error == "", "ampliar no avisa"
        codigo, _, error = correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], ["--fecha", "2026-10-22", "--modo", "rapido"]))
        assert codigo == 0 and error == "", "una carpeta nueva no avisa"


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
        repo, ticket, recibo = preparar_recibo(t)
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
        repo, ticket, recibo = preparar_recibo(t)
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
        repo, ticket, recibo = preparar_recibo(t)
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
        repo, ticket, recibo = preparar_recibo(t)
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
        assert correr(args_write(ticket, [r1, r2], [r1 / "a.sql", r2 / "b.cs"], ["--fecha", "2026-10-21"]))[0] == 0
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
        codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "a.sql"], primera, ["--ronda", "3"]))
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
        codigo, salida, error = correr(rechequeo(ticket, [repo], [repo / "prueba_a.sql"], primera))
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
            (args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-21", "--modo", "rapido", "--previo", str(primera)]), "--ronda"),
            (args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-20", "--modo", "completo", "--previo", str(primera)]), "--ronda"),
        ]
        for argv, esperado in malos:
            codigo, salida, error = correr(argv)
            assert codigo == 2 and salida == "" and esperado in error, (argv, codigo, salida, error)
        assert (primera / "recibo.json").read_bytes() == crudo
        assert sorted(p.name for p in (ticket / "revision").iterdir()) == antes
        codigo, _, error = correr(args_write(ticket, [repo], [repo / "a.sql"], ["--fecha", "2026-10-22", "--modo", "rapido", "--previo", str(primera)]))
        assert codigo == 0, "una fecha posterior queda despues del previo aunque el modo sea otro: %s" % error


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
