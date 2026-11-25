import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_RUTA = AQUI / "quitado.py"
sys.path.insert(0, str(AQUI))
SOBRANTES = []
SKILL_CERRAR = AQUI.parent / "skills" / "cerrar" / "SKILL.md"
REFERENCIA = SKILL_CERRAR.parent / "references" / "quitado.md"
SHA_RE = re.compile(r"[0-9a-f]{40}")
CLAVES_DEL_REPO = {"ruta", "base", "base_origen", "vacio", "archivos", "dependencias", "avisos"}
CLAVES_DE_LA_DEPENDENCIA = {"manifiesto", "nombre", "linea"}


def _cargar():
    spec = importlib.util.spec_from_file_location("quitado", _RUTA)
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
    raiz = Path(os.path.realpath(tempfile.mkdtemp(prefix="quitado-test-")))
    try:
        (raiz / "gitconfig-global").write_bytes(b"")
        (raiz / "gitconfig-system").write_bytes(b"")
        yield raiz
    finally:
        shutil.rmtree(raiz, onexc=_quitar)
        if raiz.exists():
            SOBRANTES.append(str(raiz))


def _config_aislada(raiz):
    return {"GIT_CONFIG_GLOBAL": str(raiz / "gitconfig-global"), "GIT_CONFIG_SYSTEM": str(raiz / "gitconfig-system"),
            "GIT_CONFIG_NOSYSTEM": "1"}


def git(raiz, cwd, *args):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    entorno.update(_config_aislada(raiz))
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "core.autocrlf=false", "-c", "init.defaultBranch=main", *args],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=entorno)
    if r.returncode != 0:
        raise RuntimeError("git %s fallo: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def escribir(repo, archivos):
    for rel, texto in archivos.items():
        p = Path(repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8") if isinstance(texto, str) else texto)


def commitear(raiz, repo, archivos=None, borrar=(), mensaje="c"):
    escribir(repo, archivos or {})
    for rel in borrar:
        (Path(repo) / rel).unlink()
    git(raiz, repo, "add", "-A")
    git(raiz, repo, "commit", "-q", "-m", mensaje)
    return git(raiz, repo, "rev-parse", "HEAD")


def repo_con_base(raiz, archivos, nombre="app"):
    repo = raiz / nombre
    repo.mkdir()
    git(raiz, repo, "init", "-q")
    base = commitear(raiz, repo, archivos, mensaje="base")
    git(raiz, repo, "update-ref", "refs/remotes/origin/main", base)
    git(raiz, repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(raiz, repo, "checkout", "-q", "-b", "ticket")
    return repo, base


def correr(raiz, *argv, entorno=None):
    env = dict(os.environ)
    env.update(_config_aislada(raiz))
    env.update(entorno or {})
    r = subprocess.run([sys.executable, str(_RUTA), *argv], capture_output=True, text=True, encoding="utf-8", env=env)
    return r.returncode, r.stdout, r.stderr


def json_de(raiz, *argv, entorno=None):
    codigo, salida, error = correr(raiz, *argv, "--json", entorno=entorno)
    assert codigo == 0, (codigo, salida, error)
    return json.loads(salida)


def unico(datos):
    assert len(datos["repos"]) == 1, datos
    return datos["repos"][0]


def dependencias(repo):
    return sorted((d["manifiesto"], d["nombre"], d["linea"]) for d in repo["dependencias"])


# ---------------------------------------------------------------- los archivos

def test_un_archivo_borrado_sale_en_la_lista():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"a.txt": "a\n", "src/b.txt": "b\n"})
        commitear(raiz, repo, borrar=["src/b.txt"])
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["archivos"] == ["src/b.txt"] and r["dependencias"] == [] and r["vacio"] is False, r
        codigo, salida, error = correr(raiz, "--repo", str(repo))
        assert codigo == 0 and error == "" and "  archivo src/b.txt\n" in salida, (codigo, salida, error)


def test_un_borrado_sin_commitear_tambien_cuenta():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"a.txt": "a\n", "b.txt": "b\n"})
        (repo / "b.txt").unlink()
        assert unico(json_de(raiz, "--repo", str(repo)))["archivos"] == ["b.txt"]


def test_un_renombre_no_es_un_borrado():
    texto = "".join("linea %d del modulo\n" % n for n in range(40))
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"viejo.py": texto, "otro.txt": "x\n"})
        git(raiz, repo, "mv", "viejo.py", "nuevo.py")
        commitear(raiz, repo, {"nuevo.py": texto + "una linea mas\n"})
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["archivos"] == [] and r["vacio"] is False, r
        codigo, salida, _ = correr(raiz, "--repo", str(repo))
        assert codigo == 0 and "nada quitado" in salida, salida


def test_un_manifiesto_borrado_sale_como_archivo_sin_sus_dependencias():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"web/package.json": '{"dependencies": {"lodash": "^4"}}\n'})
        commitear(raiz, repo, borrar=["web/package.json"], archivos={"x.txt": "x\n"})
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["archivos"] == ["web/package.json"] and r["dependencias"] == [], r


# ---------------------------------------------------------------- las dependencias, una por manifiesto

PACKAGE_BASE = """{
  "name": "app",
  "dependencies": {
    "lodash": "^4.17.21",
    "react": "^17.0.2"
  },
  "devDependencies": {
    "jest": "^29.0.0"
  }
}
"""
PACKAGE_ACTUAL = """{
  "name": "app",
  "dependencies": {
    "react": "^18.2.0"
  },
  "devDependencies": {}
}
"""

PYPROJECT_BASE = """[project]
name = "app"
dependencies = [
    "httpx>=0.27",
    "rich==13.7.0",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
"""
PYPROJECT_ACTUAL = """[project]
name = "app"
dependencies = [
    "httpx>=0.28",
]
"""

GO_BASE = """module example.com/app

go 1.22

require github.com/single/mod v1.0.0

require (
\tgithub.com/pkg/errors v0.9.1
\tgolang.org/x/text v0.14.0 // indirect
)
"""
GO_ACTUAL = """module example.com/app

go 1.22

require (
\tgolang.org/x/text v0.15.0 // indirect
)
"""

CSPROJ_BASE = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
    <PackageReference Version="7.0.0" Include="Serilog" />
    <PackageReference Include="Dapper">
      <Version>2.0.0</Version>
    </PackageReference>
  </ItemGroup>
</Project>
"""
CSPROJ_ACTUAL = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Version="8.0.0" Include="Serilog" />
  </ItemGroup>
</Project>
"""

GRADLE_BASE = """dependencies {
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'
    testImplementation "junit:junit:4.13.2"
    implementation group: 'com.google.code.gson', name: 'gson', version: '2.10'
    api libs.okhttp
}
"""
GRADLE_ACTUAL = """dependencies {
    implementation 'com.squareup.retrofit2:retrofit:2.11.0'
}
"""

KTS_BASE = """dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    androidTestImplementation("androidx.test:runner:1.5.2")
}
"""
KTS_ACTUAL = """dependencies {
    androidTestImplementation("androidx.test:runner:1.6.0")
}
"""

CARGO_BASE = """[package]
name = "app"

[dependencies]
serde = { version = "1.0", features = ["derive"] }
anyhow = "1.0"

[dependencies.tokio]
version = "1"

[dev-dependencies]
proptest = "1.4"
"""
CARGO_ACTUAL = """[package]
name = "app"

[dependencies]
serde = { version = "1.1", features = ["derive"] }
"""

MANIFIESTOS = {
    "package": ({"web/package.json": PACKAGE_BASE}, {"web/package.json": PACKAGE_ACTUAL},
                [("web/package.json", "jest", '"jest": "^29.0.0"'), ("web/package.json", "lodash", '"lodash": "^4.17.21",')]),
    "requirements": ({"requirements.txt": "requests==2.31.0\nDjango>=4.2  # web\n-r base.txt\n", "requirements-dev.txt": "pytest==8.0\n"},
                     {"requirements.txt": "requests==2.32.0\n-r base.txt\n", "requirements-dev.txt": "# nada\n"},
                     [("requirements-dev.txt", "pytest", "pytest==8.0"), ("requirements.txt", "Django", "Django>=4.2  # web")]),
    "pyproject": ({"pyproject.toml": PYPROJECT_BASE}, {"pyproject.toml": PYPROJECT_ACTUAL},
                  [("pyproject.toml", "pytest", 'dev = ["pytest>=8"]'), ("pyproject.toml", "rich", '"rich==13.7.0",')]),
    "go": ({"go.mod": GO_BASE}, {"go.mod": GO_ACTUAL},
           [("go.mod", "github.com/pkg/errors", "github.com/pkg/errors v0.9.1"),
            ("go.mod", "github.com/single/mod", "require github.com/single/mod v1.0.0")]),
    "csproj": ({"src/Api/Api.csproj": CSPROJ_BASE}, {"src/Api/Api.csproj": CSPROJ_ACTUAL},
               [("src/Api/Api.csproj", "Dapper", '<PackageReference Include="Dapper">'),
                ("src/Api/Api.csproj", "Newtonsoft.Json", '<PackageReference Include="Newtonsoft.Json" Version="13.0.1" />')]),
    "gradle": ({"app/build.gradle": GRADLE_BASE}, {"app/build.gradle": GRADLE_ACTUAL},
               [("app/build.gradle", "com.google.code.gson:gson", "implementation group: 'com.google.code.gson', name: 'gson', version: '2.10'"),
                ("app/build.gradle", "junit:junit", 'testImplementation "junit:junit:4.13.2"'),
                ("app/build.gradle", "libs.okhttp", "api libs.okhttp")]),
    "kts": ({"build.gradle.kts": KTS_BASE}, {"build.gradle.kts": KTS_ACTUAL},
            [("build.gradle.kts", "androidx.core:core-ktx", 'implementation("androidx.core:core-ktx:1.12.0")')]),
    "cargo": ({"Cargo.toml": CARGO_BASE}, {"Cargo.toml": CARGO_ACTUAL},
              [("Cargo.toml", "anyhow", 'anyhow = "1.0"'), ("Cargo.toml", "proptest", 'proptest = "1.4"'),
               ("Cargo.toml", "tokio", "[dependencies.tokio]")]),
}


PACKAGE_PARECIDO_BASE = """{
  "name": "app",
  "scripts": {
    "dependencies": "npm ls --all",
    "lodash": "node scripts/lodash.js"
  },
  "overrides": {
    "react": "17.0.2"
  },
  "dependencies": {
    "lodash-es": "^4.17.21",
    "lodash": "^4.17.21",
    "react": "^17.0.2"
  }
}
"""
PACKAGE_PARECIDO_ACTUAL = PACKAGE_PARECIDO_BASE.replace('    "lodash": "^4.17.21",\n', "").replace(',\n    "react": "^17.0.2"', "")

PYPROJECT_PARECIDO_BASE = """[project]
name = "pytest-timer"
description = 'a rich client'
dependencies = [
    "colorama",
    "rich",
]

[project.optional-dependencies]
dev = [
    "pytest-cov",
    "pytest",
]
"""
PYPROJECT_PARECIDO_ACTUAL = """[project]
name = "pytest-timer"
description = 'a rich client'
dependencies = ["colorama"]
"""

CSPROJ_PARECIDO_BASE = """<Project Sdk="Microsoft.NET.Sdk">
  <!-- <PackageReference Include="Dapper" Version="1.0.0" /> -->
  <ItemGroup>
    <PackageReference Include="Dapper.Contrib" Version="2.0.0" />
    <PackageReference Include="Dapper" Version="2.0.0" />
  </ItemGroup>
</Project>
"""
CSPROJ_PARECIDO_ACTUAL = CSPROJ_PARECIDO_BASE.replace('    <PackageReference Include="Dapper" Version="2.0.0" />\n', "")

CARGO_PARECIDO_BASE = """[package]
name = "app"

[features]
serde = ["dep:serde"]

[dependencies]
serde_json = "1"
serde = { version = "1", optional = true }
anyhow.workspace = true
"""
CARGO_PARECIDO_ACTUAL = """[package]
name = "app"

[dependencies]
serde_json = "1"
"""

PARECIDOS = {
    "package": ({"package.json": PACKAGE_PARECIDO_BASE}, {"package.json": PACKAGE_PARECIDO_ACTUAL},
                [("package.json", "lodash", '"lodash": "^4.17.21",'), ("package.json", "react", '"react": "^17.0.2"')]),
    "requirements": ({"requirements.txt": "pytest-timer==1.0\n# pytest va en dev\npytest==8.0\n"}, {"requirements.txt": "pytest-timer==1.0\n"},
                     [("requirements.txt", "pytest", "pytest==8.0")]),
    "pyproject": ({"pyproject.toml": PYPROJECT_PARECIDO_BASE}, {"pyproject.toml": PYPROJECT_PARECIDO_ACTUAL},
                  [("pyproject.toml", "pytest", '"pytest",'), ("pyproject.toml", "pytest-cov", '"pytest-cov",'),
                   ("pyproject.toml", "rich", '"rich",')]),
    "go": ({"go.mod": "module example.com/app\n\nrequire (\n\tgithub.com/pkg/errors/v2 v2.0.0\n\t// github.com/pkg/errors v0.8.0\n"
                      "\tgithub.com/pkg/errors v0.9.1\n)\n\nreplace github.com/pkg/errors => ../errors\n"},
           {"go.mod": "module example.com/app\n\nrequire (\n\tgithub.com/pkg/errors/v2 v2.0.0\n)\n"},
           [("go.mod", "github.com/pkg/errors", "github.com/pkg/errors v0.9.1")]),
    "csproj": ({"Api.csproj": CSPROJ_PARECIDO_BASE}, {"Api.csproj": CSPROJ_PARECIDO_ACTUAL},
               [("Api.csproj", "Dapper", '<PackageReference Include="Dapper" Version="2.0.0" />')]),
    "gradle": ({"build.gradle": "dependencies {\n    // implementation 'com.squareup.retrofit2:retrofit:2.8.0'\n"
                                "    implementation 'com.squareup.retrofit2:retrofit-mock:2.9.0'\n"
                                "    implementation 'com.squareup.retrofit2:retrofit:2.9.0'\n}\n"},
               {"build.gradle": "dependencies {\n    implementation 'com.squareup.retrofit2:retrofit-mock:2.9.0'\n}\n"},
               [("build.gradle", "com.squareup.retrofit2:retrofit", "implementation 'com.squareup.retrofit2:retrofit:2.9.0'")]),
    "cargo": ({"Cargo.toml": CARGO_PARECIDO_BASE}, {"Cargo.toml": CARGO_PARECIDO_ACTUAL},
              [("Cargo.toml", "anyhow", "anyhow.workspace = true"), ("Cargo.toml", "serde", 'serde = { version = "1", optional = true }')]),
}


def _probar_manifiesto(clave, casos=MANIFIESTOS):
    base, actual, esperadas = casos[clave]
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, base)
        commitear(raiz, repo, actual)
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["avisos"] == [] and r["archivos"] == [], r
        assert dependencias(r) == esperadas, dependencias(r)
        codigo, salida, _ = correr(raiz, "--repo", str(repo))
        assert codigo == 0, salida
        for manifiesto, nombre, linea in esperadas:
            assert "  dependencia %s (%s): %s\n" % (nombre, manifiesto, linea) in salida, (nombre, salida)


def test_package_json_lista_lo_que_salio_de_dependencies_y_devdependencies():
    _probar_manifiesto("package")


def test_requirements_lista_lo_que_salio_de_cada_requirements_txt():
    _probar_manifiesto("requirements")


def test_pyproject_lista_lo_que_salio_de_dependencies_y_optional_dependencies():
    _probar_manifiesto("pyproject")


def test_go_mod_lista_lo_que_salio_de_sus_require():
    _probar_manifiesto("go")


def test_csproj_lista_el_packagereference_que_salio():
    _probar_manifiesto("csproj")


def test_build_gradle_lista_la_dependencia_que_salio():
    _probar_manifiesto("gradle")


def test_build_gradle_kts_lista_la_dependencia_que_salio():
    _probar_manifiesto("kts")


def test_cargo_toml_lista_lo_que_salio_de_dependencies_y_dev_dependencies():
    _probar_manifiesto("cargo")


def test_package_json_la_linea_es_la_de_su_seccion_aunque_el_nombre_aparezca_antes_en_scripts_u_overrides():
    _probar_manifiesto("package", PARECIDOS)


def test_requirements_la_linea_es_la_del_nombre_exacto_y_no_la_de_uno_parecido():
    _probar_manifiesto("requirements", PARECIDOS)


def test_pyproject_la_linea_es_la_del_arreglo_de_dependencias_y_no_la_del_nombre_o_la_descripcion():
    _probar_manifiesto("pyproject", PARECIDOS)


def test_go_mod_la_linea_es_la_del_require_y_no_la_de_un_comentario_un_replace_o_una_v2():
    _probar_manifiesto("go", PARECIDOS)


def test_csproj_la_linea_es_la_del_packagereference_y_no_la_de_un_comentario_o_uno_parecido():
    _probar_manifiesto("csproj", PARECIDOS)


def test_build_gradle_la_linea_es_la_de_la_declaracion_y_no_la_de_un_comentario_o_un_artefacto_parecido():
    _probar_manifiesto("gradle", PARECIDOS)


def test_cargo_toml_la_linea_es_la_de_su_tabla_y_no_la_de_features():
    _probar_manifiesto("cargo", PARECIDOS)


def test_una_subida_de_version_o_un_cambio_de_seccion_no_es_una_baja():
    base = {ruta: texto for b, _, _ in MANIFIESTOS.values() for ruta, texto in b.items()}
    subidas = {
        "web/package.json": PACKAGE_BASE.replace("^4.17.21", "^4.18.0").replace('"react": "^17.0.2"', '"react": "^18.2.0"')
                            .replace('"devDependencies": {\n    "jest"', '"devDependencies": {\n    "react-dom": "^18",\n    "jest"'),
        "requirements.txt": "requests==2.32.0\ndjango>=5.0  # web\n-r base.txt\n",
        "requirements-dev.txt": "pytest==8.1\n",
        "pyproject.toml": PYPROJECT_BASE.replace("0.27", "0.28").replace("13.7.0", "13.8.0").replace(">=8", ">=8.1"),
        "go.mod": GO_BASE.replace("v1.0.0", "v1.1.0").replace("v0.9.1", "v0.9.2"),
        "src/Api/Api.csproj": CSPROJ_BASE.replace("13.0.1", "13.0.3").replace("2.0.0", "2.1.0"),
        "app/build.gradle": GRADLE_BASE.replace("4.13.2", "4.13.3").replace("2.10", "2.11"),
        "build.gradle.kts": KTS_BASE.replace("1.12.0", "1.13.0"),
        "Cargo.toml": CARGO_BASE.replace('"1.4"', '"1.5"').replace('anyhow = "1.0"', 'anyhow = "1.1"'),
    }
    movida = PACKAGE_BASE.replace('    "lodash": "^4.17.21",\n', "").replace('"jest": "^29.0.0"', '"jest": "^29.0.0",\n    "lodash": "^4.17.21"')
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, base)
        commitear(raiz, repo, subidas)
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["dependencias"] == [] and r["archivos"] == [] and r["avisos"] == [], r
        commitear(raiz, repo, {"web/package.json": movida})
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["dependencias"] == [], r


def test_un_manifiesto_que_no_se_puede_leer_da_un_aviso_y_no_silencio():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"package.json": PACKAGE_BASE})
        commitear(raiz, repo, {"package.json": PACKAGE_BASE[:40]})
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["dependencias"] == [] and len(r["avisos"]) == 1 and r["avisos"][0].startswith("package.json: no se pudo leer"), r
        codigo, salida, _ = correr(raiz, "--repo", str(repo))
        assert codigo == 0 and "  aviso package.json: no se pudo leer" in salida, salida


# ---------------------------------------------------------------- la base

def test_un_diff_vacio_lo_dice_y_pide_la_base():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"a.txt": "a\n", "b.txt": "b\n"})
        punta = commitear(raiz, repo, borrar=["b.txt"])
        git(raiz, repo, "update-ref", "refs/remotes/origin/main", punta)
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["vacio"] is True and r["archivos"] == [] and r["base"] == punta, r
        codigo, salida, error = correr(raiz, "--repo", str(repo))
        assert codigo == 0 and error == "", (codigo, error)
        lineas = [l for l in salida.splitlines() if "vacío" in l]
        assert len(lineas) == 1 and "--repo RUTA#BASE" in lineas[0], salida


def test_un_archivo_tocado_sin_cambios_no_esconde_el_diff_vacio():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"a.txt": "a\n", "b.txt": "b\n"})
        punta = commitear(raiz, repo, borrar=["b.txt"])
        git(raiz, repo, "update-ref", "refs/remotes/origin/main", punta)
        os.utime(repo / "a.txt", (2000000000, 2000000000))
        r = unico(json_de(raiz, "--repo", str(repo)))
        assert r["vacio"] is True and r["archivos"] == [] and r["dependencias"] == [], r


def test_repo_con_base_explicita_usa_esa_base():
    with temporal() as raiz:
        repo, base = repo_con_base(raiz, {"a.txt": "a\n", "b.txt": "b\n"})
        punta = commitear(raiz, repo, borrar=["b.txt"])
        git(raiz, repo, "update-ref", "refs/remotes/origin/main", punta)
        r = unico(json_de(raiz, "--repo", "%s#%s" % (repo, base[:12])))
        assert r["archivos"] == ["b.txt"] and r["base"] == base and r["base_origen"] == "explicita" and r["vacio"] is False, r
        codigo, salida, _ = correr(raiz, "--repo", "%s#%s" % (repo, base[:12]))
        assert codigo == 0 and "explícita" in salida and "vacío" not in salida, salida


def test_la_forma_del_json():
    with temporal() as raiz:
        repo, base = repo_con_base(raiz, {"package.json": PACKAGE_BASE, "b.txt": "b\n"})
        otro, _ = repo_con_base(raiz, {"a.txt": "a\n"}, nombre="otro")
        commitear(raiz, repo, {"package.json": PACKAGE_ACTUAL}, borrar=["b.txt"])
        datos = json_de(raiz, "--repo", str(repo), "--repo", str(otro / "."))
        assert set(datos) == {"repos"} and len(datos["repos"]) == 2, datos
        primero, segundo = datos["repos"]
        for r in (primero, segundo):
            assert set(r) == CLAVES_DEL_REPO, sorted(r)
            assert SHA_RE.fullmatch(r["base"]) and r["base_origen"] == "merge-base", r
            assert isinstance(r["vacio"], bool) and isinstance(r["archivos"], list) and isinstance(r["avisos"], list), r
        assert primero["ruta"] == repo.as_posix() and segundo["ruta"] == otro.as_posix(), (primero["ruta"], segundo["ruta"])
        assert primero["base"] == base and primero["archivos"] == ["b.txt"], primero
        assert all(set(d) == CLAVES_DE_LA_DEPENDENCIA for d in primero["dependencias"]) and len(primero["dependencias"]) == 2, primero
        assert segundo["vacio"] is True and segundo["archivos"] == segundo["dependencias"] == segundo["avisos"] == [], segundo


# ---------------------------------------------------------------- los errores y el entorno

def test_un_repo_malo_sale_con_dos():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"a.txt": "a\n"})
        (raiz / "suelta").mkdir()
        sin_origin = raiz / "sin-origin"
        sin_origin.mkdir()
        git(raiz, sin_origin, "init", "-q")
        commitear(raiz, sin_origin, {"a.txt": "a\n"})
        casos = [
            (("--repo", str(raiz / "no-existe")), "no existe"),
            (("--repo", str(raiz / "suelta")), "no es un repo git"),
            (("--repo", "%s#no-hay-tal-base" % repo), "no-hay-tal-base"),
            (("--repo", str(sin_origin)), "--repo RUTA#BASE"),
            ((), "--repo"),
            (("--repo", str(repo), "--otra"), "--otra"),
        ]
        for argv, texto in casos:
            codigo, salida, error = correr(raiz, *argv)
            assert codigo == 2 and salida == "" and texto in error, (argv, codigo, salida, error)


def test_no_escribe_nada_y_no_lo_mueve_el_entorno_de_git_ajeno():
    with temporal() as raiz:
        repo, _ = repo_con_base(raiz, {"a.txt": "a\n", "b.txt": "b\n", "c.txt": "c\n"})
        commitear(raiz, repo, borrar=["b.txt"])
        (repo / "c.txt").unlink()
        estado = git(raiz, repo, "status", "--porcelain")
        indice = (repo / ".git" / "index").read_bytes()
        refs = git(raiz, repo, "for-each-ref")
        limpio = unico(json_de(raiz, "--repo", str(repo)))
        ajeno = {"GIT_INDEX_FILE": str(raiz / "no-existe" / "index"), "GIT_DIR": str(raiz / "no-existe" / ".git"),
                 "GIT_WORK_TREE": str(raiz)}
        sucio = unico(json_de(raiz, "--repo", str(repo), entorno=ajeno))
        assert limpio == sucio and limpio["archivos"] == ["b.txt", "c.txt"], (limpio, sucio)
        assert git(raiz, repo, "status", "--porcelain") == estado and (repo / ".git" / "index").read_bytes() == indice
        assert git(raiz, repo, "for-each-ref") == refs
        assert not (raiz / "no-existe").exists()


# ---------------------------------------------------------------- lo que dice cerrar

MARCADOR_RE = re.compile(r"<[^<>]+>")
OPCION_RE = re.compile(r"(?<![\w-])--[a-z][a-z-]*")


def comandos_de_quitado(texto):
    comandos = []
    for linea in texto.split("\n"):
        for m in re.finditer(r'quitado\.py"((?:[ \t]+[^\s`]+)*)', linea):
            comandos.append(shlex.split(MARCADOR_RE.sub("x", m.group(1))))
    return comandos


def problemas_de_los_comandos(texto):
    parser = M.construir_parser()
    opciones = {opcion for accion in parser._actions for opcion in accion.option_strings}
    comandos = comandos_de_quitado(texto)
    problemas = [] if comandos else ["no hay ningún comando de quitado.py"]
    for argv in comandos:
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(argv)
        except SystemExit:
            problemas.append("el parser de quitado.py rechaza %s" % argv)
    for argv in comandos:
        problemas += ["%s nombra %s, que quitado.py no tiene" % (argv, t) for t in argv if OPCION_RE.fullmatch(t) and t not in opciones]
    return problemas


def test_cerrar_lo_corre_con_opciones_que_el_parser_acepta():
    nucleo = SKILL_CERRAR.read_text(encoding="utf-8")
    referencia = REFERENCIA.read_text(encoding="utf-8")
    assert "references/quitado.md" in nucleo and comandos_de_quitado(nucleo), "el núcleo de cerrar no corre quitado.py ni abre su reference"
    texto = nucleo + "\n" + referencia
    assert problemas_de_los_comandos(texto) == [], problemas_de_los_comandos(texto)
    mutado = texto.replace('quitado.py" --repo', 'quitado.py" --repos', 1)
    assert mutado != texto and problemas_de_los_comandos(mutado), "control positivo: una opción que no existe se detecta"


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
