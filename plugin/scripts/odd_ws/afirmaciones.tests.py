import contextlib
import importlib
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
sys.path.insert(0, str(AQUI.parent))

CONTEO = r"git ls-tree -r {ref} --name-only | grep -c '\.txt$'"
P = "git ls-tree -r origin/HEAD --name-only | "


def m():
    return importlib.import_module("odd_ws.afirmaciones")


def _quitar(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


@contextlib.contextmanager
def temporal():
    base = Path(tempfile.mkdtemp(prefix="afirmaciones-"))
    try:
        yield base
    finally:
        shutil.rmtree(base, onexc=_quitar)


@contextlib.contextmanager
def entorno(**variables):
    previo = dict(os.environ)
    os.environ.update(variables)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previo)


def git(cwd, *args, entrada=None):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "core.autocrlf=false", "-C", str(cwd), *args],
                       capture_output=True, env=env, timeout=60, input=None if entrada is None else entrada.encode("utf-8"))
    if r.returncode != 0:
        raise RuntimeError("git %s falló: %s" % (" ".join(args), r.stderr.decode("utf-8", errors="replace")))
    return r.stdout.decode("utf-8", errors="replace").strip()


def escribir(raiz, archivos):
    for rel, texto in archivos.items():
        p = Path(raiz) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))


def commitear(repo, archivos, mensaje="c"):
    escribir(repo, archivos)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", mensaje)


def repo_fixture(base):
    repo = base / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commitear(repo, {"alfa.txt": "UNO\nDOS\nTRES\n"}, "uno")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    commitear(repo, {"beta.txt": "x\n"}, "dos")
    return repo


def af(comando=None, expected=1, **extra):
    datos = {"id": "a1", "tipo": "contrato", "naturaleza": "invariante", "claim": "texto", "doc": "docs/a.md",
             "ejecutor": "repo", "repo": "principal", "expected": expected, "expected_verificado": "2026-01-01",
             "notas": ""}
    if comando is not None:
        datos["comando"] = comando
    datos.update(extra)
    return datos


def archivo(claims=(), **extra):
    lista = list(claims) if isinstance(claims, (list, tuple)) else claims
    datos = {"version": 1, "reglas": {}, "claims": lista, "rechazados": [], "cobertura_triada": []}
    datos.update(extra)
    return datos


def sin_cambios(repo, antes):
    return sorted(p.name for p in repo.iterdir()) == antes


def listar(repo):
    return sorted(p.name for p in repo.iterdir())


def hallazgos(datos, **kw):
    return m().lint(datos, **kw)


def con_texto(lista, *partes):
    return [h for h in lista if all(p in h.texto for p in partes)]


def duplicados_json(texto):
    with temporal() as tmp:
        ruta = tmp / "a.json"
        ruta.write_text(texto, encoding="utf-8")
        try:
            m().cargar(ruta)
        except ValueError as exc:
            return str(exc)
    return None


def test_cargar_lee_las_cinco_claves():
    datos = archivo([af(CONTEO)], reglas={"r1": "texto"}, rechazados=[{"id": "x9", "motivo": "m"}],
                    cobertura_triada=[{"doc": "a.md", "cifras": ["3"], "fecha": "2026-01-01"}])
    with temporal() as tmp:
        ruta = tmp / "afirmaciones.json"
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        leido = m().cargar(ruta)
        assert leido == datos
        assert list(leido) == list(datos) and list(leido["claims"][0]) == list(datos["claims"][0]), "se perdió el orden"
        assert sorted(leido) == ["claims", "cobertura_triada", "rechazados", "reglas", "version"]
        assert leido["claims"][0]["repo"] == "principal"
        assert m().cargar(str(ruta)) == datos


def test_cargar_acepta_bom_y_crlf():
    with temporal() as tmp:
        ruta = tmp / "a.json"
        ruta.write_bytes(b"\xef\xbb\xbf" + json.dumps(archivo(), indent=2).replace("\n", "\r\n").encode("utf-8"))
        assert m().cargar(ruta) == archivo()


def test_cargar_rechaza_clave_duplicada_en_la_raiz():
    msg = duplicados_json('{"version": 1, "claims": [], "claims": [{"id": "z"}]}')
    assert msg is not None, "una clave repetida se quedaba con la última sin avisar"
    assert "claims" in msg and "duplicad" in msg, msg


def test_cargar_rechaza_clave_duplicada_dentro_de_una_afirmacion():
    msg = duplicados_json('{"version": 1, "claims": [{"id": "a1", "expected": 3, "expected": 4}]}')
    assert msg is not None, "el expected repetido hacía que la afirmación midiera otra cosa y diera verde"
    assert "expected" in msg and "duplicad" in msg, msg


def test_cargar_rechaza_clave_duplicada_en_reglas_anidadas():
    msg = duplicados_json('{"version": 1, "reglas": {"a": {"x": 1, "x": 2}}, "claims": []}')
    assert msg is not None and "x" in msg


def test_cargar_json_sin_duplicados_si_carga():
    assert duplicados_json('{"version": 1, "claims": [{"id": "a1", "expected": 3}], "otra": {"id": "a1"}}') is None


def test_cargar_rechaza_lo_que_no_es_objeto_o_no_es_json():
    with temporal() as tmp:
        ruta = tmp / "a.json"
        for contenido, dice in (("[]", "objeto"), ('"x"', "objeto"), ("{", "JSON"), ("", "JSON"), ("{'a': 1}", "JSON")):
            ruta.write_text(contenido, encoding="utf-8")
            try:
                m().cargar(ruta)
            except ValueError as exc:
                assert dice in str(exc), "%r: %s" % (contenido, exc)
                assert str(ruta) in str(exc), "el mensaje no nombra el archivo"
            else:
                raise AssertionError("%r se cargó" % contenido)
        try:
            m().cargar(tmp / "no-existe.json")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("un archivo ausente tiene que levantar FileNotFoundError")


SEGUROS = [
    r"git ls-tree -r origin/HEAD --name-only | grep -cE '^src/[^/]+\.txt$'",
    "git show origin/HEAD:alfa.txt | grep -c '<resumen>'",
    "git ls-tree -r origin/HEAD --name-only | grep -E 'a->b' | wc -l",
    "git ls-tree -r origin/HEAD --name-only | grep -c '$(no-se-expande)'",
    "git show origin/HEAD:alfa.txt | grep -c '#region'",
    'git ls-tree -r origin/HEAD --name-only | grep -c "a>b"',
    "git ls-tree -r origin/HEAD | wc -l && git ls-tree -r origin/HEAD | wc -l",
    "git ls-tree -r origin/HEAD | wc -l; git ls-tree -r origin/HEAD | wc -l",
    "git ls-tree -r origin/HEAD | wc -l\ngit ls-tree -r origin/HEAD | wc -l",
    'git ls-tree -r origin/HEAD | grep -c "a;b"',
    P + "grep -oE 'src/[^/]+/' | sort -u | wc -l",
    P + "sort -to -k2", P + "sort -k2,2n -t , | uniq -c", P + "uniq -f 1 -", P + "uniq -cf 1",
    P + "cut -d/ -f3- | sort -u", P + "head -1 | tail -1 | tr a b",
    P + "sort -t T -k2", P + "sort -tT", P + "sort -S 1K -u",
    "git grep -c x origin/HEAD", "git log -1 --format=%cs origin/HEAD", "git grep -lE 'x' origin/HEAD -- '*.txt'",
    "git rev-parse origin/HEAD", "git cat-file -p origin/HEAD:alfa.txt | wc -l",
    "git diff-tree --no-commit-id --name-only -r origin/HEAD | wc -l",
    "git log -1 -p --no-textconv --no-ext-diff origin/HEAD | wc -l",
    "git show --no-textconv origin/HEAD:alfa.txt | wc -l",
    "git ls-tree -r origin/HEAD \\\n  --name-only | wc -l",
]


def test_comando_seguro_acepta_lo_legitimo():
    for cmd in SEGUROS:
        ok, motivo = m().comando_seguro(cmd)
        assert (ok, motivo) == (True, None), "%r se rechazó: %s" % (cmd, motivo)


def test_comando_seguro_solo_verbos_de_lectura_de_git():
    for verbo in ("ls-tree", "show", "log", "cat-file", "rev-parse", "diff-tree", "grep"):
        ok, motivo = m().comando_seguro("git %s x | wc -l" % verbo)
        assert ok, "git %s es de lectura y se rechazó (%s)" % (verbo, motivo)
    for cmd in ("git checkout main", "git commit -m x", "git push", "git fetch", "git config a b", "git branch x",
                "git diff", "git ls-files", "git reset --hard", "git clean -fd", "git stash", "git add .",
                "git rm x", "git mv a b", "git apply x", "git am x", "git gc", "git update-ref a b",
                "git -C x ls-tree y", "git --no-pager log", "git -c core.pager=x log", "git",
                "git ls-tree x && git checkout y", "git ls-tree x ; git push", "git ls-tree x\ngit commit -m z"):
        ok, motivo = m().comando_seguro(cmd)
        assert not ok, "%r pasó la lista blanca" % cmd
        assert "git" in motivo, motivo
    ok, motivo = m().comando_seguro("git checkout main")
    assert motivo == "verbo git no permitido: git checkout", motivo


def test_comando_seguro_solo_los_ocho_filtros():
    for filtro in ("grep -c x", "wc -l", "sort -u", "uniq -c", "head -1", "tail -1", "cut -c1", "tr a b"):
        ok, motivo = m().comando_seguro(P + filtro)
        assert ok, "%s es un filtro permitido y se rechazó (%s)" % (filtro, motivo)
    for cmd in ("rm x", "find . -name x", "sed -n p", "xargs rm", "tee z", "cat f", "awk 1", "curl x", "bash -c x",
                "sh -c x", "python -c 1", "echo x", "env x", "command git log", "touch x", "mkdir y", "mv a b",
                "cp a b", "dd if=a of=b", "perl -e 1", "git/../bin/sh", "/usr/bin/git ls-tree x", "FOO=1 git ls-tree x"):
        ok, motivo = m().comando_seguro(P + cmd)
        assert not ok, "%r pasó la lista blanca como filtro" % cmd
        assert motivo.startswith("comando no permitido: "), (cmd, motivo)
    assert m().comando_seguro(P + "rm x")[1] == "comando no permitido: rm"


def test_comando_seguro_cada_tramo_se_valida():
    ok, motivo = m().comando_seguro("git ls-tree origin/HEAD && rm -rf y")
    assert (ok, motivo) == (False, "comando no permitido: rm"), motivo
    for cmd in ("git ls-tree x ; rm y", "git ls-tree x\nrm y", "git ls-tree x | rm y", "git ls-tree x | grep a | tee z"):
        ok, motivo = m().comando_seguro(cmd)
        assert not ok and motivo.startswith("comando no permitido"), (cmd, motivo)


METACARACTERES = [
    ("git ls-tree -r origin/HEAD 2>/dev/null | wc -l", "redirecci"),
    ("git show origin/HEAD:$(touch x) | wc -l", "expansi"),
    ('git show "origin/HEAD:$(touch x)" | wc -l', "expansi"),
    ("git show origin/HEAD:${HOME} | wc -l", "expansi"),
    ("git show origin/HEAD:`touch x` | wc -l", "sustituci"),
    ("git log -1 origin/HEAD >x.txt", "redirecci"),
    ("git log -1 origin/HEAD >>x.txt", "redirecci"),
    ("git log -1 origin/HEAD > x.txt", "redirecci"),
    ("grep -c x < f", "redirecci"),
    ("git ls-tree -r origin/HEAD &touch x", "background"),
    ("git ls-tree -r origin/HEAD & touch x", "background"),
    ("git ls-tree -r origin/HEAD &> x", "redirecci"),
    ("git ls-tree -r origin/HEAD | wc -l &", "background"),
    ("grep -c x <(touch y)", "redirecci"),
    ("git show origin/HEAD:a | grep -c x #", "comentario"),
    ("git ls-tree -r origin/HEAD \\' >x", "barra invertida"),
    (r"git show origin/HEAD:a | grep -c $'\'' >x '\'", "expansi"),
    (r"git show origin/HEAD:a | grep -c $'\'' $(touch y) '\'", "expansi"),
    (r"git show origin/HEAD:a | grep -c $'\'' | tee z '\'", "expansi"),
    ("git show origin/HEAD:a | grep -c $'\\'' \nmkdir y\n '", "expansi"),
    (r"git show origin/HEAD:a | grep -c \' | tee z", "barra invertida"),
    (r'git show origin/HEAD:a | grep -c "a\" " | tee z ""', "barra invertida"),
    ("git show origin/HEAD:a | grep -c x #'\nmkdir y\n#'", "comentario"),
    ('git show origin/HEAD:a | grep -c "a$(touch y)"', "expansi"),
    ('git show origin/HEAD:a | grep -c "a`touch y`"', "sustituci"),
    ("git show origin/HEAD:a | grep -c '' \"$HOME\"", "expansi"),
]


def test_comando_seguro_metacaracteres_fuera_de_comillas():
    for cmd, dice in METACARACTERES:
        ok, motivo = m().comando_seguro(cmd)
        assert not ok, "%r pasó la lista blanca y escribe o ejecuta" % cmd
        assert dice in motivo, (cmd, motivo)


def test_comando_seguro_lo_inerte_entre_comillas_simples_pasa():
    for cmd in ("git show origin/HEAD:a | grep -c '<resumen>'", "git show origin/HEAD:a | grep -c 'a>b&c|d'",
                "git show origin/HEAD:a | grep -c '$HOME`x`\\'", "git show origin/HEAD:a | grep -c '#x'",
                'git show origin/HEAD:a | grep -c "a>b <c & d"', 'git show origin/HEAD:a | grep -c "#x"'):
        ok, motivo = m().comando_seguro(cmd)
        assert ok, "%r es inerte y se rechazó (%s)" % (cmd, motivo)


def test_comando_seguro_motivos_de_forma():
    assert m().comando_seguro("") == (False, "comando vacío")
    assert m().comando_seguro("   \n ") == (False, "comando vacío")
    assert m().comando_seguro(";") == (False, "comando vacío")
    assert m().comando_seguro("git ls-tree x |") == (False, "tramo vacío")
    assert m().comando_seguro("| wc -l") == (False, "tramo vacío")
    ok, motivo = m().comando_seguro("git show 'x | wc -l")
    assert not ok and motivo.startswith("comando mal formado"), motivo
    ok, motivo = m().comando_seguro("git ls-tree x || wc -l")
    assert not ok and "vacío" in motivo, motivo


FLAGS_QUE_ESCRIBEN = [
    "sort -o x", "sort -uo x", "sort x -o y", "sort --output=x", "sort --outp=x", "sort --o=x",
    "sort -S 1 --compress-program=touch", "sort --compress=touch", "sort -u --output x",
    "uniq - x", "uniq -c a b", "uniq -f 1 a b", "uniq a b",
]
FLAGS_DE_GIT = [
    "git log -1 --output=x origin/HEAD", "git diff-tree --output=x origin/HEAD", "git log -1 --ou=x origin/HEAD",
    "git log --ext-diff -1 origin/HEAD", "git log --ext -1 origin/HEAD", "git show --ext-diff origin/HEAD",
    "git grep --open-files-in-pager=touch x origin/HEAD", "git grep --open=touch x origin/HEAD",
    "git grep -Otouch x origin/HEAD", "git grep -iOtouch x origin/HEAD",
]


def test_comando_seguro_flags_que_escriben_o_ejecutan():
    for cmd in FLAGS_QUE_ESCRIBEN:
        ok, motivo = m().comando_seguro(P + cmd)
        assert not ok, "%r pasó la lista blanca" % cmd
        assert "escribe" in motivo or "ejecuta" in motivo, (cmd, motivo)
    for cmd in FLAGS_DE_GIT:
        ok, motivo = m().comando_seguro(cmd)
        assert not ok, "%r pasó la lista blanca" % cmd
        assert "escribe" in motivo or "ejecuta" in motivo or "pager" in motivo, (cmd, motivo)
    assert m().comando_seguro(P + "sort -o x")[1] == "sort -o escribe un archivo (-o)"
    assert m().comando_seguro(P + "uniq a b")[1] == "uniq con dos operandos escribe el segundo (b)"


def test_comando_seguro_endurecimiento_sort_temporales():
    for cmd in ("sort -T x", "sort -T/x", "sort -uT x", "sort -T x -u", "sort -S 1K -T x", "sort --temporary-directory=x",
                "sort --temporary-directory x", "sort --temp=x", "sort --tem x", "sort -k2 -T x", "sort -ruT x"):
        ok, motivo = m().comando_seguro(P + cmd)
        assert not ok, "%r pasó: sort -T escribe archivos temporales donde le digan" % cmd
        assert "sort" in motivo and "temporal" in motivo, (cmd, motivo)
    for cmd in ("sort -tT", "sort -t T", "sort -k2,2 -t T", "sort -S 1K", "sort -u", "sort -k1T"):
        ok, motivo = m().comando_seguro(P + cmd)
        assert ok, "%r no escribe y se rechazó (%s)" % (cmd, motivo)


def test_comando_seguro_endurecimiento_drivers_de_la_config_del_repo():
    for cmd in ("git log -p --textconv origin/HEAD", "git show --textconv origin/HEAD:alfa.txt",
                "git cat-file --textconv origin/HEAD:alfa.txt", "git grep --textconv x origin/HEAD",
                "git show --textc origin/HEAD:alfa.txt", "git show --text origin/HEAD:alfa.txt",
                "git log --no-textconv --textconv -1 origin/HEAD", "git diff-tree -p --textconv origin/HEAD",
                "git cat-file --filters origin/HEAD:alfa.txt", "git cat-file --filt origin/HEAD:alfa.txt",
                "git cat-file --fil origin/HEAD:alfa.txt",
                "git grep --no-index x", "git grep --no-i x", "git grep -c --no-index x -- /",
                "git log -1 --show-signature origin/HEAD", "git show --show-signature origin/HEAD",
                "git log --show-s origin/HEAD", "git log -1 --format=%G? origin/HEAD",
                "git log -1 --pretty=format:%GG origin/HEAD", "git show -s --format='%GK' origin/HEAD",
                "git log -1 --format='%H %GS' origin/HEAD"):
        ok, motivo = m().comando_seguro(cmd)
        assert not ok, "%r pasó la lista blanca y ejecuta un driver de la config del repo o lee el disco" % cmd
        assert "git" in motivo and ("ejecuta" in motivo or "escribe" in motivo), (cmd, motivo)
    for cmd in ("git show --no-textconv origin/HEAD", "git log -1 -p --no-ext-diff origin/HEAD",
                "git grep -c -e filters origin/HEAD", "git grep -c --files-with-matches x origin/HEAD",
                "git log --first-parent -1 origin/HEAD", "git cat-file -p origin/HEAD:alfa.txt",
                "git log -1 --format=%gd origin/HEAD", "git log --show-notes -1 origin/HEAD",
                "git log -1 --grep=firma origin/HEAD"):
        ok, motivo = m().comando_seguro(cmd)
        assert ok, "%r es de lectura y se rechazó (%s)" % (cmd, motivo)


def test_comando_seguro_el_primer_tramo_tiene_que_ser_git():
    for cmd in ("grep -c x alfa.txt", "wc -l alfa.txt", "sort alfa.txt", "head -1 alfa.txt", "tr a b", "cut -c1 f",
                "git ls-tree x | wc -l && grep -c y f", "git ls-tree x\nwc -l f", "git ls-tree x ; sort f"):
        ok, motivo = m().comando_seguro(cmd)
        assert not ok, "%r pasó: un filtro al comienzo lee archivos del disco y no el árbol medido" % cmd
        assert "git" in motivo and "primer" in motivo, (cmd, motivo)
    assert m().comando_seguro("rm x")[1] == "comando no permitido: rm"
    for cmd in ("git ls-tree x | wc -l", "git ls-tree x | wc -l && git ls-tree y | grep -c a"):
        assert m().comando_seguro(cmd) == (True, None)


def test_comando_sustituido_pone_el_ref():
    c = af("git show {ref}:a | grep -c {ref}", ref="origin/main")
    assert m().comando_sustituido(c) == "git show origin/main:a | grep -c origin/main"
    assert m().comando_sustituido(af("git ls-tree {ref}")) == "git ls-tree origin/HEAD"
    assert m().comando_sustituido(af("git ls-tree {ref}", ref=None)) == "git ls-tree origin/HEAD"
    assert m().comando_sustituido(af("git ls-tree HEAD")) == "git ls-tree HEAD"
    assert m().comando_sustituido(af(None)) == ""
    assert m().comando_sustituido({"comando": None}) == ""


def test_correr_mide_el_ref_y_no_el_working_tree():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        v = m().correr(af(CONTEO, 1), repo)
        assert tuple(v) == ("OK", "1"), "sin ref tiene que medir origin/HEAD (1 archivo), no el working tree (2): %s" % (v,)
        v = m().correr(af(CONTEO, 2, ref="HEAD"), repo)
        assert tuple(v) == ("OK", "2"), v
        v = m().correr(af(CONTEO, 1, ref="origin/main"), repo)
        assert tuple(v) == ("OK", "1"), v
        v = m().correr(af(CONTEO, 2), repo)
        assert tuple(v) == ("DRIFT", "esperado ['2'], obtenido ['1']"), v
        assert isinstance(v, tuple) and v.estado == "DRIFT"


def test_correr_el_repo_es_una_clave_y_la_ruta_la_pone_quien_llama():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        otro = tmp / "otro"
        otro.mkdir()
        git(otro, "init", "-q", "-b", "main")
        commitear(otro, {"x.txt": "1\n", "y.txt": "1\n", "z.txt": "1\n"})
        git(otro, "update-ref", "refs/remotes/origin/HEAD", "HEAD")
        for repo_campo in ("principal", "no/es/una/ruta", str(otro), ""):
            v = m().correr(af(CONTEO, 1, repo=repo_campo), repo)
            assert tuple(v) == ("OK", "1"), "el campo repo=%r se interpretó como ruta: %s" % (repo_campo, v)
        assert tuple(m().correr(af(CONTEO, 3), otro)) == ("OK", "3")


def test_correr_valida_el_repo_antes_de_medir():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        v = m().correr(af(CONTEO, 0), tmp / "no-existe")
        assert v.estado == "ERROR" and v.detalle.startswith("repo inexistente"), v
        sin_git = tmp / "sin-git"
        sin_git.mkdir()
        v = m().correr(af(CONTEO, 0), sin_git)
        assert v.estado == "ERROR" and "falta .git" in v.detalle, v
        v = m().correr(af(CONTEO, 0, ref="no-existe"), repo)
        assert v.estado == "ERROR" and "no-existe" in v.detalle and "no resuelve a un commit" in v.detalle, v
        v = m().correr(af("git ls-tree -r {ref} --name-only | grep -c x", 0, ref="no-existe"), repo)
        assert v.estado == "ERROR", "un ref con typo daba verde en los invariantes que esperan 0: %s" % (v,)


def test_correr_ref_invalido_no_llega_a_git_ni_al_shell():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        antes = listar(repo)
        for ref in ("--output=escrito", "-x", "a;touch escrito", "a b", "a\nb", "$(touch escrito)", "", 5, ["x"], "a|b",
                    "a'b", "..", "a>b"):
            v = m().correr(af(CONTEO, 1, ref=ref), repo)
            assert v.estado == "ERROR" and "ref" in v.detalle, (ref, v)
        assert listar(repo) == antes, "un ref hostil escribió en el repo"
        for ref in ("origin/HEAD", "origin/main", "HEAD", "main", "HEAD~1", "main^", "v1.0", "refs/remotes/origin/main"):
            assert m().ref_valido(ref), ref
        assert m().ref_de(af(CONTEO)) == "origin/HEAD"
        assert m().ref_de(af(CONTEO, ref=None)) == "origin/HEAD"
        assert m().ref_de(af(CONTEO, ref="main")) == "main"


def test_correr_stderr_es_error_y_no_un_valor():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        v = m().correr(af("git show {ref}:no-existe.txt | grep -c x", 0), repo)
        assert v.estado == "ERROR" and v.detalle.startswith("stderr: "), v
        v = m().correr(af(r"git ls-tree -r {ref} --name-only | grep -c '['", 0), repo)
        assert v.estado == "ERROR" and v.detalle.startswith("stderr: "), "un regex inválido daba 0: %s" % (v,)


def test_correr_sin_salida_es_error_y_cero_legitimo_es_ok():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        v = m().correr(af("git ls-tree -r {ref} --name-only | grep nada-de-esto", 0), repo)
        assert v.estado == "ERROR" and v.detalle.startswith("sin salida: "), v
        assert "grep nada-de-esto" in v.detalle
        v = m().correr(af("git ls-tree -r {ref} --name-only | grep -c nada-de-esto", 0), repo)
        assert tuple(v) == ("OK", "0"), v


def test_correr_cada_comando_es_un_valor():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        esperado = {"total": 1, "txt": 1}
        base = "git ls-tree -r {ref} --name-only | wc -l"
        for union in (" && ", " ; ", "\n"):
            v = m().correr(af(base + union + CONTEO, esperado), repo)
            assert tuple(v) == ("OK", "1, 1"), (union, v)
        v = m().correr(af(base + " && " + CONTEO, 1), repo)
        assert v.estado == "ERROR" and "produjo 2 valor(es) y 'expected' declara 1" in v.detalle, v
        v = m().correr(af(base + " \\\n  && " + CONTEO, esperado), repo)
        assert tuple(v) == ("OK", "1, 1"), "la continuación de línea cortó el comando: %s" % (v,)
        v = m().correr(af(base + " ; git ls-tree -r {ref} --name-only | grep -c nada", {"a": 1, "b": 0}), repo)
        assert tuple(v) == ("OK", "1, 0"), v


def test_correr_el_valor_es_la_ultima_linea_de_cada_comando():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        v = m().correr(af("git ls-tree -r {ref} --name-only", "beta.txt", ref="HEAD"), repo)
        assert tuple(v) == ("OK", "beta.txt"), v
        v = m().correr(af("git ls-tree -r {ref} --name-only | wc -l ; git ls-tree -r {ref} --name-only", {"n": 2, "u": "beta.txt"},
                          ref="HEAD"), repo)
        assert tuple(v) == ("OK", "2, beta.txt"), v


def test_correr_usa_la_naturaleza_para_juzgar():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        v = m().correr(af(CONTEO, 0, naturaleza="inventario"), repo)
        assert v.estado == "CRECIO", v
        v = m().correr(af(CONTEO, 3, naturaleza="inventario"), repo)
        assert v.estado == "DRIFT" and v.detalle.startswith("BAJO "), v


def test_correr_no_ejecuta_lo_rechazado_ni_toca_el_repo():
    comandos = [
        "git ls-tree -r {ref} --name-only | wc -l ; touch escrito",
        "git ls-tree -r {ref} --name-only | wc -l > escrito",
        "git ls-tree -r {ref} --name-only | wc -l >> escrito",
        "git ls-tree -r {ref} --name-only | wc -l && mkdir escrito",
        "git ls-tree -r {ref} --name-only | tee escrito",
        "git ls-tree -r {ref} --name-only | sort -o escrito",
        "git ls-tree -r {ref} --name-only | sort -T escrito",
        "git ls-tree -r {ref} --name-only | sort --temporary-directory=escrito",
        "git ls-tree -r {ref} --name-only | uniq - escrito",
        "git log -1 --output=escrito {ref}",
        "git diff-tree --output=escrito {ref}",
        "git ls-tree -r {ref} --name-only | wc -l $(touch escrito)",
        "git ls-tree -r {ref} --name-only | wc -l `touch escrito`",
        "git ls-tree -r {ref} --name-only | wc -l &touch escrito",
        "git ls-tree -r {ref} --name-only | wc -l #'\ntouch escrito\n#'",
        "git checkout -b escrito",
        "git tag escrito {ref}",
        "git ls-tree -r {ref} --name-only | xargs touch",
    ]
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        antes = listar(repo)
        ramas = git(repo, "branch", "--list")
        for cmd in comandos:
            v = m().correr(af(cmd, 0), repo)
            assert v.estado == "ERROR", "%r -> %s" % (cmd, tuple(v))
        assert listar(repo) == antes, "el claim escribió en el repo: %s" % sorted(set(listar(repo)) - set(antes))
        assert git(repo, "branch", "--list") == ramas
        assert git(repo, "tag", "--list") == ""


def test_correr_solo_corre_afirmaciones_de_repo_completas():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        v = m().correr(af(CONTEO, 1, ejecutor="sql"), repo)
        assert v.estado == "ERROR" and "repo" in v.detalle, v
        v = m().correr(af(CONTEO, 1, ejecutor="otro"), repo)
        assert v.estado == "ERROR", v
        v = m().correr({"id": "x", "comando": CONTEO}, repo)
        assert v.estado == "ERROR", v
        c = af(CONTEO)
        del c["expected"]
        v = m().correr(c, repo)
        assert v.estado == "ERROR" and "expected" in v.detalle, v
        v = m().correr(af(None, 1), repo)
        assert v.estado == "ERROR" and "vacío" in v.detalle, v
        v = m().correr(af("", 1), repo)
        assert v.estado == "ERROR" and "vacío" in v.detalle, v


def test_correr_el_stdin_va_cerrado():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        t0 = time.time()
        v = m().correr(af("git cat-file --batch-check | wc -l", 0), repo, plazo=5)
        assert tuple(v) == ("OK", "0"), v
        assert time.time() - t0 < 5, "esperó el stdin heredado"


def test_correr_un_plazo_invalido_vale_el_de_por_defecto():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        for plazo in (0, -5, float("nan"), float("inf"), True, "5", None):
            v = m().correr(af(CONTEO, 1), repo, plazo=plazo)
            assert tuple(v) == ("OK", "1"), (plazo, tuple(v))


def test_correr_el_plazo_de_respaldo_corta_aunque_falle_el_timeout_del_shell():
    modulo = m()
    previo = (modulo.GUION_DEL_PLAZO, modulo.MARGEN_DEL_PLAZO)
    modulo.GUION_DEL_PLAZO = "sleep 20"
    modulo.MARGEN_DEL_PLAZO = 1
    try:
        with temporal() as tmp:
            repo = repo_fixture(tmp)
            t0 = time.time()
            v = modulo.correr(af(CONTEO, 1), repo, plazo=1)
            assert v.estado == "ERROR" and v.detalle.startswith("plazo de 1 s agotado: "), v
            assert time.time() - t0 < 12, "el respaldo no cortó a tiempo"
    finally:
        modulo.GUION_DEL_PLAZO, modulo.MARGEN_DEL_PLAZO = previo


def test_correr_el_plazo_corta_un_comando_colgado():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        t0 = time.time()
        v = m().correr(af("git ls-tree -r {ref} --name-only | tail -f alfa.txt", 1), repo, plazo=2)
        assert v.estado == "ERROR" and v.detalle.startswith("plazo de 2 s agotado: "), v
        assert time.time() - t0 < 9, "el plazo no mató al proceso hijo"


def test_bash_ejecutable_es_el_de_git_y_no_el_lanzador_de_wsl():
    ruta = m().bash_ejecutable()
    assert ruta is not None and Path(ruta).is_file(), ruta
    assert "system32" not in ruta.lower()
    r = subprocess.run([ruta, "-c", "echo hola"], capture_output=True, timeout=60)
    assert r.stdout.strip() == b"hola"


def test_entorno_de_corrida_quita_el_arranque_de_bash():
    base = {"PATH": "/x", "HOME": "/h", "BASH_ENV": "a", "ENV": "b", "SHELLOPTS": "xtrace", "BASHOPTS": "x",
            "BASH_XTRACEFD": "2", "POSIXLY_CORRECT": "1", "GREP_OPTIONS": "-v", "BASH_FUNC_grep%%": "() { x; }",
            "bash_func_sort%%": "() { x; }", "bash_env": "c", "Shellopts": "d"}
    env = m().entorno_de_corrida(base)
    assert env["PATH"] == "/x" and env["HOME"] == "/h", "no se debe perder el resto del entorno"
    for k in env:
        assert k.upper() not in ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "BASH_XTRACEFD", "POSIXLY_CORRECT",
                                 "GREP_OPTIONS"), k
        assert not k.upper().startswith("BASH_FUNC_"), k
    assert "ENV" not in env and "BASH_ENV" not in env


def test_entorno_de_corrida_la_config_de_git_es_solo_la_de_entorno_git():
    comun = importlib.import_module("odd_ws.comun")
    base = {"GIT_CONFIG_COUNT": "3", "GIT_CONFIG_KEY_0": "core.pager", "GIT_CONFIG_VALUE_0": "x",
            "GIT_CONFIG_KEY_1": "diff.ev.textconv", "GIT_CONFIG_VALUE_1": "x",
            "GIT_CONFIG_KEY_2": "core.fsmonitor", "GIT_CONFIG_VALUE_2": "x", "GIT_CONFIG_PARAMETERS": "'a.b=c'",
            "GIT_DIR": "/x", "GIT_TRACE": "1", "GIT_TRACE_PACKET": "1", "GIT_EXTERNAL_DIFF": "x", "GIT_PAGER": "x",
            "GIT_CONFIG_GLOBAL": "/x", "GIT_CONFIG_SYSTEM": "/x", "GIT_CONFIG_NOSYSTEM": "0", "git_ssh": "x",
            "GIT_SSH_COMMAND": "x", "PATH": "/p"}
    env = m().entorno_de_corrida(base)
    propias = comun.entorno_git({})
    git_ = {k: v for k, v in env.items() if k.upper().startswith("GIT_")}
    assert git_ == {k: v for k, v in propias.items() if k.upper().startswith("GIT_")}, git_
    assert git_ == {"GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "diff.autoRefreshIndex",
                    "GIT_CONFIG_VALUE_0": "false"}, "la config inyectada por entorno_git cambió: revisar si abre un hueco"
    assert env["PATH"] == "/p"


def test_entorno_de_corrida_usa_os_environ_por_defecto():
    with entorno(BASH_ENV="x", GIT_DIR="y", MARCA_PROPIA="z"):
        env = m().entorno_de_corrida()
    assert "BASH_ENV" not in env and "GIT_DIR" not in env and env["MARCA_PROPIA"] == "z"


def test_correr_ignora_el_entorno_que_altera_bash_y_git():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        otro = tmp / "otro"
        otro.mkdir()
        git(otro, "init", "-q", "-b", "main")
        commitear(otro, {"x.txt": "1\n", "y.txt": "1\n"})
        arranque = tmp / "arranque.sh"
        arranque.write_text("echo ruido-de-arranque >&2\n", encoding="utf-8", newline="\n")
        casos = [
            ("SHELLOPTS", "xtrace", "bash traza cada comando en stderr"),
            ("GIT_TRACE", "1", "git traza en stderr"),
            ("GIT_DIR", str(otro / ".git"), "git -C lee OTRO repo, donde el ref no existe"),
            ("GREP_OPTIONS", "-v", "grep aplica opciones heredadas"),
            ("BASH_ENV", arranque.as_posix(), "bash -c lee el script de arranque"),
            ("GIT_CONFIG_COUNT", "2", "el segundo par de config inyectada no existe: git muere"),
        ]
        bash = m().bash_ejecutable()
        for var, valor, porque in casos:
            with entorno(**{var: valor}):
                v = m().correr(af(CONTEO, 1), repo)
                assert tuple(v) == ("OK", "1"), "con %s un claim sano dio %s (%s)" % (var, tuple(v), porque)
                r = subprocess.run([bash, "-c", CONTEO.replace("{ref}", "origin/HEAD")], capture_output=True, text=True,
                                   cwd=str(repo), timeout=60, env=dict(os.environ))
                assert (r.stdout.strip(), r.stderr.strip()) != ("1", ""), \
                    "%s no cambió nada sin limpiar el entorno: el caso no demuestra nada (%s)" % (var, porque)


def repo_con_drivers(base):
    repo = base / "drivers"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commitear(repo, {"datos.dat": "crudo\n", ".gitattributes": "*.dat diff=ev filter=ev\n"}, "uno")
    commitear(repo, {"datos.dat": "crudo2\n"}, "dos")
    marca = base / "marca"
    script = base / "driver.py"
    script.write_text("import sys\nopen(sys.argv[1], 'a').write('x')\nprint('convertido')\n", encoding="utf-8", newline="\n")
    comando = "'%s' '%s' '%s'" % (Path(sys.executable).as_posix(), script.as_posix(), marca.as_posix())
    git(repo, "config", "diff.ev.textconv", comando)
    git(repo, "config", "filter.ev.smudge", comando)
    git(repo, "config", "diff.ev.command", comando)
    return repo, marca


def test_correr_no_ejecuta_el_textconv_de_la_config_del_repo():
    with temporal() as tmp:
        repo, marca = repo_con_drivers(tmp)
        git(repo, "show", "HEAD")
        assert marca.exists(), "el instrumento no sabe decir que sí: git show no ejecutó el textconv de la config"
        marca.unlink()
        git(repo, "log", "-1", "-p")
        assert marca.exists(), "git log -p no ejecutó el textconv"
        marca.unlink()
        for cmd, esperado in (("git show {ref} | grep -c crudo", 2),
                              ("git log -1 -p {ref} | grep -c crudo", 2),
                              ("git diff-tree -p {ref} | grep -c crudo", 2),
                              ("git show {ref} | grep -c convertido", 0),
                              ("git log -1 -p {ref} | grep -c convertido", 0)):
            v = m().correr(af(cmd, esperado, ref="HEAD"), repo)
            assert tuple(v) == ("OK", str(esperado)), "%s -> %s" % (cmd, tuple(v))
            assert not marca.exists(), "%s ejecutó el textconv de la config del repo medido" % cmd


def test_correr_no_deja_que_el_claim_reactive_los_drivers():
    with temporal() as tmp:
        repo, marca = repo_con_drivers(tmp)
        for cmd in ("git show --textconv {ref}:datos.dat", "git log -1 -p --textconv {ref}",
                    "git cat-file --textconv {ref}:datos.dat", "git cat-file --filters {ref}:datos.dat",
                    "git show --ext-diff {ref}", "git log -1 -p --ext-diff {ref}", "git show --textconv --no-textconv {ref}:datos.dat"):
            v = m().correr(af(cmd, 1, ref="HEAD"), repo)
            assert v.estado == "ERROR", "%s -> %s" % (cmd, tuple(v))
            assert not marca.exists(), "%s ejecutó un driver de la config del repo medido" % cmd


def repo_con_firma(base):
    repo, marca = repo_con_drivers(base)
    arbol = git(repo, "rev-parse", "HEAD^{tree}")
    padre = git(repo, "rev-parse", "HEAD")
    objeto = ("tree %s\nparent %s\nauthor t <t@t> 1700000000 +0000\ncommitter t <t@t> 1700000000 +0000\n"
              "gpgsig -----BEGIN PGP SIGNATURE-----\n \n abc\n -----END PGP SIGNATURE-----\n\nfirmado\n") % (arbol, padre)
    firmado = git(repo, "hash-object", "-t", "commit", "-w", "--stdin", entrada=objeto)
    git(repo, "update-ref", "refs/heads/firmada", firmado)
    programa = base / "firma"
    programa.write_text("#!/bin/sh\necho x >> '%s'\nexit 1\n" % marca.as_posix(), encoding="utf-8", newline="\n")
    programa.chmod(0o755)
    git(repo, "config", "gpg.program", programa.as_posix())
    git(repo, "config", "log.showSignature", "true")
    return repo, marca


def test_correr_no_ejecuta_el_programa_de_firmas_de_la_config_del_repo():
    with temporal() as tmp:
        repo, marca = repo_con_firma(tmp)
        git(repo, "log", "-1", "firmada")
        assert marca.exists(), "el instrumento no sabe decir que sí: log.showSignature no ejecutó gpg.program"
        marca.unlink()
        git(repo, "log", "-1", "--format=%G?", "firmada")
        assert marca.exists(), "el instrumento no sabe decir que sí: %G? no ejecutó gpg.program"
        marca.unlink()
        for cmd in ("git log -1 {ref} | grep -c firmado", "git show -s {ref} | grep -c firmado"):
            v = m().correr(af(cmd, 1, ref="firmada"), repo)
            assert tuple(v) == ("OK", "1"), "%s -> %s" % (cmd, tuple(v))
            assert not marca.exists(), "%s ejecutó el programa de firmas de la config del repo medido" % cmd
        for cmd in ("git log -1 --format=%G? {ref}", "git log -1 --show-signature {ref}",
                    "git show -s --pretty=format:%GG {ref}"):
            v = m().correr(af(cmd, 1, ref="firmada"), repo)
            assert v.estado == "ERROR", "%s -> %s" % (cmd, tuple(v))
            assert not marca.exists(), "%s ejecutó el programa de firmas de la config del repo medido" % cmd


def test_correr_la_config_inyectada_de_afuera_no_ejecuta_nada():
    with temporal() as tmp:
        repo, marca = repo_con_drivers(tmp)
        script = tmp / "driver.py"
        comando = "'%s' '%s' '%s'" % (Path(sys.executable).as_posix(), script.as_posix(), marca.as_posix())
        with entorno(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="core.pager", GIT_CONFIG_VALUE_0=comando,
                     GIT_CONFIG_KEY_1="diff.ev.textconv", GIT_CONFIG_VALUE_1=comando,
                     GIT_EXTERNAL_DIFF=comando, GIT_PAGER=comando):
            v = m().correr(af("git show {ref} | grep -c crudo", 2, ref="HEAD"), repo)
        assert tuple(v) == ("OK", "2"), v
        assert not marca.exists()


def test_correr_el_working_tree_no_se_lee():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        (repo / "alfa.txt").write_text("UNO\nDOS\nTRES\nSUELTO\n", encoding="utf-8", newline="\n")
        for cmd in ("grep -c SUELTO alfa.txt", "wc -l alfa.txt", "git grep --no-index -c SUELTO"):
            v = m().correr(af(cmd, 1), repo)
            assert v.estado == "ERROR", "%s midió el working tree: %s" % (cmd, tuple(v))
        v = m().correr(af("git show {ref}:alfa.txt | grep -c SUELTO", 0), repo)
        assert tuple(v) == ("OK", "0"), v


def test_juzgar_ok_cuando_es_igual():
    j = m().juzgar
    assert tuple(j(af(expected=3), ["3"])) == ("OK", "3")
    assert tuple(j(af(expected="abc"), ["abc"])) == ("OK", "abc")
    assert tuple(j(af(expected={"a": 1, "b": 2}), ["1", "2"])) == ("OK", "1, 2")
    assert tuple(j(af(expected=0, naturaleza="inventario"), ["0"])) == ("OK", "0")
    assert j(af(expected=3), ["3"]).estado == "OK"


def test_juzgar_drift_en_un_invariante_que_cambia():
    j = m().juzgar
    assert tuple(j(af(expected=3), ["4"])) == ("DRIFT", "esperado ['3'], obtenido ['4']")
    assert tuple(j(af(expected=3), ["2"])) == ("DRIFT", "esperado ['3'], obtenido ['2']")
    assert tuple(j(af(expected={"a": 1, "b": 2}), ["1", "3"]))[0] == "DRIFT"
    assert j(af(expected=3, naturaleza="desconocida"), ["4"]).estado == "DRIFT"
    assert j(af(expected=3, naturaleza=None), ["4"]).estado == "DRIFT"


def test_juzgar_crecio_solo_en_un_inventario_que_sube():
    j = m().juzgar
    assert tuple(j(af(expected=3, naturaleza="inventario"), ["5"])) == ("CRECIO", "+2 (linea base 3 -> 5)")
    v = j(af(expected={"a": 1, "b": 2}, naturaleza="inventario"), ["1", "5"])
    assert tuple(v) == ("CRECIO", "=, +3 (linea base 1, 2 -> 1, 5)"), v
    assert j(af(expected=3, naturaleza="invariante"), ["5"]).estado == "DRIFT"


def test_juzgar_un_inventario_que_baja_es_drift():
    j = m().juzgar
    assert tuple(j(af(expected=3, naturaleza="inventario"), ["1"])) == ("DRIFT", "BAJO -2 (linea base 3 -> 1)")
    v = j(af(expected={"a": 1, "b": 2}, naturaleza="inventario"), ["9", "1"])
    assert v.estado == "DRIFT" and v.detalle.startswith("BAJO "), v


def test_juzgar_inventario_no_numerico_no_inventa_un_delta():
    j = m().juzgar
    v = j(af(expected="abc", naturaleza="inventario"), ["abd"])
    assert tuple(v) == ("DRIFT", "valor no numerico: esperado ['abc'], obtenido ['abd']"), v
    v = j(af(expected=3, naturaleza="inventario"), ["tres"])
    assert v.estado == "DRIFT" and "no numerico" in v.detalle, v


def test_juzgar_error_si_no_mide_lo_que_declara():
    j = m().juzgar
    assert tuple(j(af(expected=3), ["3", "4"])) == ("ERROR", "el comando produjo 2 valor(es) y 'expected' declara 1")
    assert tuple(j(af(expected={"a": 1, "b": 2}), ["1"])) == ("ERROR", "el comando produjo 1 valor(es) y 'expected' declara 2")
    assert j(af(expected=3), []).estado == "ERROR"
    sin = af()
    del sin["expected"]
    v = j(sin, ["3"])
    assert v.estado == "ERROR" and "expected" in v.detalle, v


def limpio():
    return archivo([af(CONTEO, 1, id="a1"), af("git show {ref}:alfa.txt | wc -l", 3, id="a2", ref="origin/main")])


def test_lint_un_archivo_sano_no_tiene_hallazgos():
    assert hallazgos(limpio()) == []
    assert hallazgos(limpio(), repos_conocidos={"principal"}) == []
    sql = af(None, 1, id="s1", ejecutor="sql", query="SELECT 1 AS uno", repo=None)
    del sql["repo"]
    assert hallazgos(archivo([sql])) == [], "el ejecutor sql se reconoce y no se juzga acá"


def test_lint_version():
    for datos in (archivo(version=2), archivo(version="1"), archivo(version=None), archivo(version=True),
                  archivo(version=1.0)):
        h = hallazgos(datos)
        assert [(x.sev, x.claim) for x in con_texto(h, "version")] == [("FAIL", None)], h
    d = archivo()
    del d["version"]
    assert [x.sev for x in con_texto(hallazgos(d), "version")] == ["FAIL"]


def test_lint_clave_desconocida_del_archivo_es_aviso():
    h = hallazgos(archivo(claim=[]))
    assert [(x.sev, x.claim) for x in con_texto(h, "claim")] == [("warn", None)], h
    assert "'claim'" in h[0].texto


def test_lint_claims_tiene_que_ser_una_lista():
    for valor in ({"a1": {}}, "x", None, 5):
        h = hallazgos(archivo(claims=valor))
        assert [x.sev for x in con_texto(h, "claims")] == ["FAIL"], (valor, h)
    d = archivo()
    del d["claims"]
    assert [x.sev for x in con_texto(hallazgos(d), "claims")] == ["FAIL"]


def test_lint_cada_afirmacion_es_un_objeto_con_id():
    h = hallazgos(archivo(["texto", af(CONTEO, id="a1")]))
    assert [(x.sev, x.claim) for x in con_texto(h, "objeto")] == [("FAIL", 0)], h
    sin_id = af(CONTEO)
    del sin_id["id"]
    h = hallazgos(archivo([sin_id]))
    assert [(x.sev, x.claim) for x in con_texto(h, "sin id")] == [("FAIL", 0)], h
    h = hallazgos(archivo([af(CONTEO, id=5), af(CONTEO, id="")]))
    assert [(x.sev, x.claim) for x in con_texto(h, "sin id")] == [("FAIL", 0), ("FAIL", 1)], h


def test_lint_id_repetido_es_fail():
    h = hallazgos(archivo([af(CONTEO, id="a1"), af(CONTEO, id="a2"), af(CONTEO, id="a1"), af(CONTEO, id="a1")]))
    r = con_texto(h, "id repetido")
    assert [(x.sev, x.claim) for x in r] == [("FAIL", None)], h
    assert r[0].texto.startswith("a1: ") and "3 afirmaciones" in r[0].texto, r[0].texto
    assert r[0].arreglo


def test_lint_dos_ids_iguales_ya_son_repetidos():
    h = hallazgos(archivo([af(CONTEO, id="a1"), af(CONTEO, id="a1"), af(CONTEO, id="a2")]))
    r = con_texto(h, "id repetido")
    assert [x.sev for x in r] == ["FAIL"] and "2 afirmaciones" in r[0].texto, h


def test_lint_id_en_afirmaciones_y_en_rechazados_es_fail():
    h = hallazgos(archivo([af(CONTEO, id="a1")], rechazados=[{"id": "a1", "motivo": "m"}, {"id": "x9"}, "suelto", 4]))
    r = con_texto(h, "rechazados")
    assert [(x.sev, x.claim) for x in r] == [("FAIL", None)], h
    assert r[0].texto.startswith("a1: ")
    assert hallazgos(archivo([af(CONTEO, id="a1")], rechazados=[{"id": "x9"}])) == []
    assert hallazgos(archivo([af(CONTEO, id="a1")], rechazados=None)) == []


def test_lint_tipo_fuera_de_la_lista_es_aviso():
    h = hallazgos(archivo([af(CONTEO, tipo="volumen")]))
    assert [(x.sev, x.claim) for x in con_texto(h, "tipo 'volumen'")] == [("warn", 0)], h
    for tipo in ("estructura", "contrato"):
        assert hallazgos(archivo([af(CONTEO, tipo=tipo)])) == []
    assert [x.sev for x in con_texto(hallazgos(archivo([af(CONTEO, tipo=None)])), "tipo")] == ["warn"]


def test_lint_naturaleza_es_obligatoria_y_cerrada():
    for valor in ("otra", None, ""):
        h = hallazgos(archivo([af(CONTEO, naturaleza=valor)]))
        assert [(x.sev, x.claim) for x in con_texto(h, "naturaleza")] == [("FAIL", 0)], (valor, h)
    for valor in ("invariante", "inventario"):
        assert hallazgos(archivo([af(CONTEO, naturaleza=valor)])) == []


def test_lint_sin_expected_es_fail():
    c = af(CONTEO)
    del c["expected"]
    h = hallazgos(archivo([c]))
    assert [(x.sev, x.claim) for x in con_texto(h, "expected")] == [("FAIL", 0)], h
    assert hallazgos(archivo([af(CONTEO, expected=0)])) == [], "un expected 0 es un valor"
    assert hallazgos(archivo([af(CONTEO, expected=None)])) == [], "un expected presente, aunque sea null, no es ausente"


def test_lint_ejecutor_desconocido_es_aviso():
    for valor in ("otro", None, ""):
        h = hallazgos(archivo([af(CONTEO, ejecutor=valor)]))
        assert [(x.sev, x.claim) for x in con_texto(h, "ejecutor")] == [("warn", 0)], (valor, h)
        assert "sql" in h[0].arreglo and "repo" in h[0].arreglo


def test_lint_afirmacion_de_repo_sin_repo_es_fail():
    for valor in (None, "", 5):
        h = hallazgos(archivo([af(CONTEO, repo=valor)]))
        assert [(x.sev, x.claim) for x in con_texto(h, "sin 'repo'")] == [("FAIL", 0)], (valor, h)
    c = af(CONTEO)
    del c["repo"]
    assert [x.sev for x in con_texto(hallazgos(archivo([c])), "sin 'repo'")] == ["FAIL"]


def test_lint_el_repo_tiene_que_ser_una_clave_de_la_config():
    h = hallazgos(archivo([af(CONTEO, repo="otro")]), repos_conocidos={"principal", "web"})
    r = con_texto(h, "otro")
    assert [(x.sev, x.claim) for x in r] == [("FAIL", 0)], h
    assert "principal" in r[0].arreglo and "web" in r[0].arreglo
    assert hallazgos(archivo([af(CONTEO, repo="otro")])) == [], "sin la lista de claves no se puede juzgar"
    assert hallazgos(archivo([af(CONTEO, repo="otro")]), repos_conocidos=["otro"]) == []
    h = hallazgos(archivo([af(CONTEO, repo="C:/ruta/absoluta")]), repos_conocidos={"principal"})
    assert [x.sev for x in con_texto(h, "C:/ruta/absoluta")] == ["FAIL"]


def test_lint_el_ref_es_opcional_pero_si_esta_tiene_que_ser_valido():
    assert hallazgos(archivo([af(CONTEO)])) == []
    assert hallazgos(archivo([af(CONTEO, ref=None)])) == []
    for ref in ("", "-x", "a;b", "a b", 5, "$(x)"):
        h = hallazgos(archivo([af(CONTEO, ref=ref)]))
        assert [(x.sev, x.claim) for x in con_texto(h, "ref")] == [("FAIL", 0)], (ref, h)


def test_lint_tramo_git_sin_ref_es_fail():
    for cmd in ("git grep -L x -- '*.cfg' | wc -l", "git ls-tree -r origin/main | wc -l", "git show HEAD:a | wc -l",
                "git log -1 --format=%cs | wc -l", "git cat-file -p x | wc -l", "git diff-tree -r x | wc -l",
                CONTEO + " && git ls-tree -r x | wc -l"):
        h = hallazgos(archivo([af(cmd)]))
        r = con_texto(h, "tramo git sin {ref}")
        assert [(x.sev, x.claim) for x in r] == [("FAIL", 0)], (cmd, h)
        assert r[0].arreglo
    h = hallazgos(archivo([af("git rev-parse HEAD | wc -l")]))
    assert con_texto(h, "tramo git sin {ref}") == [], "rev-parse no lee un árbol"
    assert con_texto(hallazgos(archivo([af("git ls-tree -r {ref} | wc -l")])), "sin {ref}") == []


def test_lint_comando_no_ejecutable_es_fail():
    for cmd, dice in (("git checkout {ref}", "verbo git"), ("rm -rf {ref}", "no permitido"),
                      (CONTEO + " > x", "redirecci"), ("", "vacío"), ("git ls-tree {ref} | sort -T x", "temporal"),
                      ("git show --textconv {ref}:a", "ejecuta"), ("grep -c x f", "primer")):
        h = hallazgos(archivo([af(cmd)]))
        r = con_texto(h, "comando no ejecutable")
        assert [(x.sev, x.claim) for x in r] == [("FAIL", 0)], (cmd, h)
        assert dice in r[0].texto, (cmd, r[0].texto)
    h = hallazgos(archivo([af(None)]))
    assert [x.sev for x in con_texto(h, "comando no ejecutable")] == ["FAIL"]
    h = hallazgos(archivo([af("git ls-tree {ref}x | wc -l ; touch y")]))
    assert con_texto(h, "touch"), h


def test_lint_juzga_el_comando_ya_sustituido():
    h = hallazgos(archivo([af("git ls-tree -r {ref} | wc -l", ref="a;touch y")]))
    assert con_texto(h, "ref") and con_texto(h, "comando no ejecutable"), h


def test_lint_el_indice_es_el_de_la_posicion():
    h = hallazgos(archivo([af(CONTEO, id="a1"), af("git checkout {ref}", id="a2"), af(CONTEO, id="a3", naturaleza="x")]))
    assert sorted((x.claim, x.sev) for x in h) == [(1, "FAIL"), (2, "FAIL")], h


def test_lint_no_ejecuta_ni_imprime_nada():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        salida, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(error):
            m().lint(limpio())
            m().comando_seguro("git checkout x")
            m().correr(af(CONTEO, 1), repo)
            m().juzgar(af(expected=1), ["2"])
            m().fetch_viejo(repo)
        assert salida.getvalue() == "" and error.getvalue() == ""


def fetch_head_de(repo):
    ruta = Path(git(repo, "rev-parse", "--git-path", "FETCH_HEAD"))
    return ruta if ruta.is_absolute() else repo / ruta


def test_fetch_viejo_sin_fetch_head_es_aviso():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        assert m().antiguedad_fetch(repo) is None
        h = m().fetch_viejo(repo, nombre="principal")
        assert h.sev == "warn" and h.claim is None
        assert "principal" in h.texto and "FETCH_HEAD" in h.texto and "fetch" in h.arreglo
        sin_git = tmp / "sin-git"
        sin_git.mkdir()
        assert m().antiguedad_fetch(sin_git) is None
        assert m().fetch_viejo(sin_git).sev == "warn"


def test_fetch_viejo_por_antiguedad():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        fh = fetch_head_de(repo)
        fh.write_text("x\n", encoding="utf-8")
        for dias, sev in ((0, "info"), (6, "info"), (7, "info"), (8, "warn"), (40, "warn")):
            t = time.time() - dias * 86400 - 60
            os.utime(fh, (t, t))
            assert m().antiguedad_fetch(repo) == dias, dias
            h = m().fetch_viejo(repo)
            assert h.sev == sev, (dias, h)
            assert ("%d" % dias) in h.texto, h
        t = time.time() - 8 * 86400 - 60
        os.utime(fh, (t, t))
        assert m().fetch_viejo(repo, dias=30).sev == "info"
        assert m().fetch_viejo(repo, dias=7).sev == "warn"
        assert m().fetch_viejo(repo, dias=7).arreglo
        assert m().fetch_viejo(repo, nombre="web").texto.startswith("web: ")
        assert m().fetch_viejo(repo).texto.startswith(str(repo))


def test_fetch_viejo_en_un_worktree_mira_el_fetch_head_que_git_indica():
    with temporal() as tmp:
        repo = repo_fixture(tmp)
        arbol = tmp / "arbol"
        git(repo, "worktree", "add", "-q", "-b", "otra", str(arbol))
        fh = fetch_head_de(arbol)
        assert not (arbol / ".git").is_dir()
        fh.write_text("x\n", encoding="utf-8")
        t = time.time() - 3 * 86400 - 60
        os.utime(fh, (t, t))
        assert m().antiguedad_fetch(arbol) == 3


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
