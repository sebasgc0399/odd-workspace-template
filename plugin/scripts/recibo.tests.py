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
    raiz = Path(tempfile.mkdtemp(prefix="recibo-test-"))
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
