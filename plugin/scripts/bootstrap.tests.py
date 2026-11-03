import contextlib
import importlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
EJEMPLO = AQUI.parent / "plantillas" / "bootstrap.ejemplo.json"
GITIGNORE_ESPERADO = "workspace.local.json\n.claude/estado/\n"
VARIABLES_DE_GIT_AISLADAS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def b():
    return importlib.import_module("bootstrap")


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Escenario:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="bootstrap-"))
        self.repo = self.base / "repo-a"
        self.repo.mkdir()
        self.raiz = self.base / "instancia"
        self.git_global = self.base / "gitconfig-aislado"
        self.git_global.write_bytes(b"")
        self.git_sistema = self.base / "gitconfig-sistema"
        self.git_sistema.write_bytes(b"")
        self.entorno_previo = {c: os.environ.get(c) for c in VARIABLES_DE_GIT_AISLADAS}
        os.environ["GIT_CONFIG_GLOBAL"] = str(self.git_global)
        os.environ["GIT_CONFIG_SYSTEM"] = str(self.git_sistema)
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        return self

    def crear_raiz(self):
        self.raiz.mkdir(exist_ok=True)
        return self.raiz

    def spec(self, **extra):
        return {
            "spec_version": 1,
            "config": {
                "schema_version": 1,
                "repos": {"repo-a": {}},
                "layers": {"capa-ñ": {"extensions": [".ext"], "repos": ["repo-a"]}},
            },
            "local": {"repos": {"repo-a": {"path": str(self.repo)}}},
            **extra,
        }

    def archivo_spec(self, spec=None, nombre="spec.json"):
        ruta = self.base / nombre
        ruta.write_text(json.dumps(self.spec() if spec is None else spec), encoding="utf-8")
        return ruta

    def __exit__(self, *_):
        for clave, valor in self.entorno_previo.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        shutil.rmtree(self.base, onexc=_forzar_borrado)


def arbol(raiz):
    raiz = Path(raiz)
    if not raiz.exists():
        return None
    vista = {}
    for ruta in sorted(raiz.rglob("*")):
        clave = ruta.relative_to(raiz).as_posix()
        vista[clave] = None if ruta.is_dir() else ruta.read_bytes()
    return vista


def correr(argv):
    salida, errores = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
        codigo = b().principal(argv)
    return codigo, salida.getvalue(), errores.getvalue()


def esperado_json(objeto):
    return (json.dumps(objeto, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def local_esperado(spec):
    return esperado_json({**spec["local"], "plugin_root": str(b().RAIZ_DEL_PLUGIN)})


@contextlib.contextmanager
def generadores_temporales(*altas):
    copia = list(b().GENERADORES)
    try:
        for alta in altas:
            b().registrar_generador(*alta[:2], **(alta[2] if len(alta) > 2 else {}))
        yield
    finally:
        b().GENERADORES[:] = copia


def generador_de(*acciones):
    return lambda spec: list(acciones)


def rechazada(e, spec, fragmento):
    raiz = e.crear_raiz()
    antes = arbol(raiz)
    codigo, salida, errores = correr(["--spec", str(e.archivo_spec(spec)), "--raiz", str(raiz)])
    assert codigo == 2, (codigo, salida, errores)
    assert fragmento in errores, errores
    assert salida == "", salida
    assert arbol(raiz) == antes == {}, arbol(raiz)


def test_spec_version_distinta_de_uno_se_rechaza():
    with Escenario() as e:
        for version in (2, 0, "1", True, None):
            rechazada(e, e.spec(spec_version=version), "spec_version")
        sin_version = e.spec()
        del sin_version["spec_version"]
        rechazada(e, sin_version, "spec_version")


def test_clave_desconocida_de_nivel_superior_se_rechaza():
    with Escenario() as e:
        rechazada(e, e.spec(extra=1), "extra")


def test_tipos_invalidos_se_rechazan():
    with Escenario() as e:
        rechazada(e, [], "objeto")
        rechazada(e, e.spec(config=[]), "config debe ser un objeto")
        rechazada(e, e.spec(local="x"), "local debe ser un objeto")
        sin_config = e.spec()
        del sin_config["config"]
        rechazada(e, sin_config, "config debe ser un objeto")
        con_plugin_root = e.spec(local={"repos": {"repo-a": {"path": str(e.repo)}}, "plugin_root": "x"})
        rechazada(e, con_plugin_root, "plugin_root")


def test_spec_con_bom_se_lee():
    with Escenario() as e:
        ruta = e.base / "con-bom.json"
        ruta.write_bytes(b"\xef\xbb\xbf" + json.dumps(e.spec()).encode("utf-8"))
        codigo, salida, errores = correr(["--spec", str(ruta), "--raiz", str(e.raiz)])
        assert codigo == 0 and errores == "", (salida, errores)
        assert (e.raiz / "workspace.config.json").is_file()


def test_spec_ilegible_o_ausente_sale_dos():
    with Escenario() as e:
        raiz = e.crear_raiz()
        ruta = e.base / "roto.json"
        ruta.write_bytes(b"{no es json")
        codigo, salida, errores = correr(["--spec", str(ruta), "--raiz", str(raiz)])
        assert codigo == 2 and "roto.json" in errores and salida == "", (codigo, salida, errores)
        codigo, salida, errores = correr(["--spec", str(e.base / "no-existe.json"), "--raiz", str(raiz)])
        assert codigo == 2 and "no-existe.json" in errores and salida == "", (codigo, salida, errores)
        assert arbol(raiz) == {}


def test_config_invalida_no_escribe_nada():
    with Escenario() as e:
        casos = []
        mala = e.spec()
        mala["config"]["schema_version"] = 9
        casos.append((mala, "schema_version"))
        sin_capas = e.spec()
        sin_capas["config"]["layers"] = {}
        casos.append((sin_capas, "layers"))
        sin_ruta = e.spec()
        sin_ruta["local"] = {}
        casos.append((sin_ruta, "falta la ruta del repo 'repo-a'"))
        ruta_falsa = e.spec()
        ruta_falsa["local"]["repos"]["repo-a"]["path"] = str(e.base / "no-existe")
        casos.append((ruta_falsa, "no existe"))
        conocimiento = e.spec()
        conocimiento["config"]["knowledge"] = {"inventada": 1}
        casos.append((conocimiento, "knowledge.inventada"))
        for spec, fragmento in casos:
            rechazada(e, spec, fragmento)
            assert "la config no es válida" in correr(["--spec", str(e.archivo_spec(spec)), "--raiz", str(e.raiz)])[2]


def test_config_invalida_no_crea_ni_la_raiz():
    with Escenario() as e:
        mala = e.spec()
        mala["config"]["schema_version"] = 9
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec(mala)), "--raiz", str(e.raiz)])
        assert codigo == 2 and "schema_version" in errores and salida == ""
        assert not e.raiz.exists()


def test_config_invalida_deja_intacta_una_instancia_con_contenido():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / "propio.txt").write_bytes(b"mio\r\n")
        (raiz / "workspace.config.json").write_bytes(b"\xef\xbb\xbf{}\r\n")
        antes = arbol(raiz)
        mala = e.spec()
        mala["config"]["layers"] = []
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec(mala)), "--raiz", str(raiz)])
        assert codigo == 2 and "layers" in errores and salida == ""
        assert arbol(raiz) == antes


def test_instancia_nueva_crea_los_tres_archivos():
    with Escenario() as e:
        spec = e.spec()
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec(spec)), "--raiz", str(e.raiz)])
        assert codigo == 0 and errores == "", (codigo, errores)
        assert arbol(e.raiz) == {
            "workspace.config.json": esperado_json(spec["config"]),
            "workspace.local.json": local_esperado(spec),
            ".gitignore": GITIGNORE_ESPERADO.encode("utf-8"),
        }
        lineas = salida.splitlines()
        assert lineas[:3] == ["creado workspace.config.json", "creado workspace.local.json", "creado .gitignore"], lineas
        assert len(lineas) == 4 and "3 creados" in lineas[3] and "0 ya existían" in lineas[3], lineas


def test_lo_generado_pasa_el_cargador():
    with Escenario() as e:
        assert correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])[0] == 0
        config_loader = importlib.import_module("config_loader")
        cargada = config_loader.cargar(e.raiz)
        assert list(cargada["layers"]) == ["capa-ñ"]
        assert cargada["repos"]["repo-a"]["path"] == str(e.repo)


def test_salida_en_lf_sin_bom_y_con_salto_final():
    with Escenario() as e:
        assert correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])[0] == 0
        for nombre in ("workspace.config.json", "workspace.local.json", ".gitignore"):
            datos = (e.raiz / nombre).read_bytes()
            assert not datos.startswith(b"\xef\xbb\xbf"), nombre
            assert b"\r" not in datos, nombre
            assert datos.endswith(b"\n") and not datos.endswith(b"\n\n"), nombre
        assert "capa-ñ".encode("utf-8") in (e.raiz / "workspace.config.json").read_bytes()
        assert b"\\u" not in (e.raiz / "workspace.config.json").read_bytes()
        assert (e.raiz / "workspace.config.json").read_bytes().startswith(b'{\n  "schema_version": 1')


def test_archivos_existentes_quedan_intactos_byte_a_byte():
    with Escenario() as e:
        raiz = e.crear_raiz()
        spec = e.spec()
        previos = {
            "workspace.config.json": b"\xef\xbb\xbf" + json.dumps(spec["config"], indent=4).replace("\n", "\r\n").encode("utf-8") + b"\r\n\r\n",
            "workspace.local.json": json.dumps(spec["local"]).encode("utf-8"),
            ".gitignore": b"# mio\r\n*.log\r\nworkspace.local.json\r\n",
        }
        for nombre, datos in previos.items():
            (raiz / nombre).write_bytes(datos)
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and errores == "", (codigo, errores)
        assert arbol(raiz) == previos
        lineas = salida.splitlines()
        for nombre in previos:
            assert "ya existía " + nombre in lineas, lineas
        assert not any(l.startswith("creado ") for l in lineas)
        assert "0 creados" in salida and "3 ya existían" in salida


def test_instancia_parcial_solo_completa_lo_que_falta():
    with Escenario() as e:
        raiz = e.crear_raiz()
        previo = json.dumps(e.spec()["config"]).encode("utf-8")
        (raiz / "workspace.config.json").write_bytes(previo)
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and errores == ""
        assert (raiz / "workspace.config.json").read_bytes() == previo
        assert "ya existía workspace.config.json" in salida
        assert "creado workspace.local.json" in salida and "creado .gitignore" in salida
        assert "2 creados" in salida and "1 ya existían" in salida


def test_gitignore_existente_informa_la_linea_que_falta_sin_tocarlo():
    with Escenario() as e:
        raiz = e.crear_raiz()
        original = b"workspace.local.json\n"
        (raiz / ".gitignore").write_bytes(original)
        codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0
        assert (raiz / ".gitignore").read_bytes() == original
        lineas = salida.splitlines()
        assert "ya existía .gitignore" in lineas
        assert "falta en .gitignore: .claude/estado/" in lineas
        assert "falta en .gitignore: workspace.local.json" not in salida
        assert lineas.index("falta en .gitignore: .claude/estado/") == lineas.index("ya existía .gitignore") + 1


def test_gitignore_existente_vacio_informa_las_dos_lineas():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b"")
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en .gitignore: workspace.local.json" in salida
        assert "falta en .gitignore: .claude/estado/" in salida
        assert (raiz / ".gitignore").read_bytes() == b""


def test_gitignore_equivalente_no_informa_faltas():
    with Escenario() as e:
        raiz = e.crear_raiz()
        original = b"/workspace.local.json\r\n.claude/estado  \r\n"
        (raiz / ".gitignore").write_bytes(original)
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en" not in salida, salida
        assert (raiz / ".gitignore").read_bytes() == original


def test_gitignore_con_lineas_comentadas_o_negadas_no_cuenta():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b"# workspace.local.json\n!.claude/estado/\n")
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en .gitignore: workspace.local.json" in salida
        assert "falta en .gitignore: .claude/estado/" in salida


def test_gitignore_completo_no_informa_faltas():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b"*.log\n" + GITIGNORE_ESPERADO.encode("utf-8"))
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en" not in salida


def test_plan_marca_crear_y_ya_existe():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / "workspace.local.json").write_bytes(b"x")
        plan = b().planificar(e.spec(), raiz)
        assert [(a.ruta, a.modo) for a in plan] == [
            ("workspace.config.json", "crear"),
            ("workspace.local.json", "ya_existe"),
            (".gitignore", "crear"),
        ]
        assert plan[0].contenido == esperado_json(e.spec()["config"])
        assert plan[2].contenido == GITIGNORE_ESPERADO.encode("utf-8")
        assert arbol(raiz) == {"workspace.local.json": b"x"}


def test_plan_sobre_raiz_inexistente_marca_todo_crear():
    with Escenario() as e:
        plan = b().planificar(e.spec(), e.raiz)
        assert {a.modo for a in plan} == {"crear"}
        assert not e.raiz.exists()


def test_una_raiz_que_es_un_archivo_se_rechaza_en_el_plan():
    with Escenario() as e:
        e.raiz.write_bytes(b"x")
        try:
            b().planificar(e.spec(), e.raiz)
        except b().ErrorDePlan as error:
            assert "carpeta" in str(error)
        else:
            raise AssertionError("se aceptó")


def test_un_directorio_con_el_nombre_cuenta_como_existente():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").mkdir()
        plan = b().planificar(e.spec(), raiz)
        assert dict((a.ruta, a.modo) for a in plan)[".gitignore"] == "ya_existe"
        resultados = b().aplicar(plan, raiz)
        assert (".gitignore", "ya_existia") in [(r.ruta, r.estado) for r in resultados]
        assert (raiz / ".gitignore").is_dir()


def test_aplicar_crea_solo_las_acciones_crear():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / "workspace.config.json").write_bytes(b"previo")
        plan = b().planificar(e.spec(), raiz)
        resultados = b().aplicar(plan, raiz)
        assert [(r.ruta, r.estado) for r in resultados] == [
            ("workspace.config.json", "ya_existia"),
            ("workspace.local.json", "creado"),
            (".gitignore", "creado"),
        ]
        assert (raiz / "workspace.config.json").read_bytes() == b"previo"


def test_aplicar_no_crea_lo_marcado_ya_existe_aunque_haya_desaparecido():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b"x")
        plan = b().planificar(e.spec(), raiz)
        (raiz / ".gitignore").unlink()
        resultados = b().aplicar(plan, raiz)
        assert not (raiz / ".gitignore").exists()
        assert (".gitignore", "ya_existia") in [(r.ruta, r.estado) for r in resultados]


def test_carrera_un_archivo_que_aparece_tras_el_plan_queda_intacto():
    with Escenario() as e:
        raiz = e.crear_raiz()
        plan = b().planificar(e.spec(), raiz)
        assert {a.modo for a in plan} == {"crear"}
        (raiz / "workspace.config.json").write_bytes(b"llego despues")
        (raiz / ".gitignore").write_bytes(b"solo-mio\n")
        resultados = b().aplicar(plan, raiz)
        assert [(r.ruta, r.estado) for r in resultados] == [
            ("workspace.config.json", "ya_existia"),
            ("workspace.local.json", "creado"),
            (".gitignore", "ya_existia"),
        ]
        assert (raiz / "workspace.config.json").read_bytes() == b"llego despues"
        assert (raiz / ".gitignore").read_bytes() == b"solo-mio\n"
        assert sorted(os.listdir(raiz)) == [".gitignore", "workspace.config.json", "workspace.local.json"]
        informe = "\n".join(b().informe(plan, resultados, raiz, ensayo=False))
        assert "ya existía workspace.config.json" in informe
        assert "falta en .gitignore: workspace.local.json" in informe


def test_aplicar_crea_las_carpetas_intermedias():
    with Escenario() as e:
        with generadores_temporales(("extra", generador_de(("a/b/c.txt", "hola\n")))):
            raiz = e.crear_raiz()
            plan = b().planificar(e.spec(), raiz)
            b().aplicar(plan, raiz)
        assert (raiz / "a" / "b" / "c.txt").read_bytes() == b"hola\n"


def test_aplicar_escribe_bytes_sin_traducir_saltos():
    with Escenario() as e:
        with generadores_temporales(("extra", generador_de(("t.txt", "uno\ndos\n"), ("u.bin", b"\x00\r\n\xff")))):
            raiz = e.crear_raiz()
            b().aplicar(b().planificar(e.spec(), raiz), raiz)
        assert (raiz / "t.txt").read_bytes() == b"uno\ndos\n"
        assert (raiz / "u.bin").read_bytes() == b"\x00\r\n\xff"


def test_aplicar_crea_la_raiz_si_falta():
    with Escenario() as e:
        codigo, _, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz / "anidada" / "mas")])
        assert codigo == 0
        assert (e.raiz / "anidada" / "mas" / "workspace.config.json").is_file()


def test_raiz_que_es_un_archivo_sale_dos():
    with Escenario() as e:
        e.raiz.write_bytes(b"soy un archivo")
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])
        assert codigo == 2 and errores != "" and "creado" not in salida
        assert e.raiz.read_bytes() == b"soy un archivo"


def test_rutas_invalidas_se_rechazan_y_no_se_escribe_nada():
    malas = ["/abs.txt", "\\abs.txt", "C:/abs.txt", "C:abs.txt", "../fuera.txt", "a/../b.txt", "a/..", "a\\b.txt", "", "a//b.txt", "./a.txt", "a/./b.txt", "a/", "a\x00b", "...", "a./b.txt", "a /b.txt", "b.txt ", "b.txt."]
    with Escenario() as e:
        raiz = e.crear_raiz()
        for ruta in malas:
            with generadores_temporales(("extra", generador_de((ruta, "x")))):
                try:
                    b().planificar(e.spec(), raiz)
                except b().ErrorDePlan as error:
                    assert str(error), ruta
                else:
                    raise AssertionError(f"se aceptó la ruta {ruta!r}")
        assert arbol(raiz) == {}


def test_rutas_repetidas_se_rechazan():
    with Escenario() as e:
        raiz = e.crear_raiz()
        for repetidas in ((("a.txt", "1"), ("a.txt", "2")), (("a.txt", "1"), ("A.TXT", "2")), (("workspace.config.json", "x"),)):
            with generadores_temporales(("extra", generador_de(*repetidas))):
                try:
                    b().planificar(e.spec(), raiz)
                except b().ErrorDePlan as error:
                    assert "repetida" in str(error) or "repite" in str(error), str(error)
                else:
                    raise AssertionError(f"se aceptaron {repetidas!r}")
        assert arbol(raiz) == {}


def test_un_archivo_y_una_carpeta_con_el_mismo_nombre_se_rechazan():
    with Escenario() as e:
        raiz = e.crear_raiz()
        with generadores_temporales(("extra", generador_de(("a", "x"), ("a/b.txt", "y")))):
            try:
                b().planificar(e.spec(), raiz)
            except b().ErrorDePlan as error:
                assert "carpeta" in str(error)
            else:
                raise AssertionError("se aceptó")


def test_accion_con_forma_invalida_se_rechaza():
    with Escenario() as e:
        raiz = e.crear_raiz()
        for accion in (("solo-ruta",), ("a.txt", 5), (5, "x"), ("a.txt", "x", "y")):
            with generadores_temporales(("extra", generador_de(accion))):
                try:
                    b().planificar(e.spec(), raiz)
                except b().ErrorDePlan:
                    pass
                else:
                    raise AssertionError(f"se aceptó {accion!r}")


def test_un_ancestro_que_es_archivo_se_rechaza_en_el_plan():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / "a").write_bytes(b"soy archivo")
        with generadores_temporales(("extra", generador_de(("a/b.txt", "x")))):
            try:
                b().planificar(e.spec(), raiz)
            except b().ErrorDePlan as error:
                assert "a" in str(error)
            else:
                raise AssertionError("se aceptó")
        assert arbol(raiz) == {"a": b"soy archivo"}


def test_un_error_a_mitad_de_la_aplicacion_informa_lo_creado():
    with Escenario() as e:
        raiz = e.crear_raiz()
        with generadores_temporales(("extra", generador_de(("d/x.txt", "x")))):
            plan = b().planificar(e.spec(), raiz)
        (raiz / "d").write_bytes(b"archivo en el lugar de la carpeta")
        try:
            b().aplicar(plan, raiz)
        except b().ErrorDeAplicacion as error:
            hechos = [(r.ruta, r.estado) for r in error.resultados]
            assert ("workspace.config.json", "creado") in hechos
            assert all(ruta != "d/x.txt" for ruta, _ in hechos)
        else:
            raise AssertionError("no falló")
        assert (raiz / "d").read_bytes() == b"archivo en el lugar de la carpeta"


def test_un_error_de_aplicacion_por_cli_sale_dos_e_informa_lo_creado():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / "d").mkdir()
        original = b().aplicar

        def con_carrera(plan, raiz_):
            shutil.rmtree(raiz_ / "d")
            (raiz_ / "d").write_bytes(b"x")
            return original(plan, raiz_)

        b().aplicar = con_carrera
        try:
            with generadores_temporales(("extra", generador_de(("d/x.txt", "x")))):
                codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            b().aplicar = original
        assert codigo == 2 and "d" in errores
        assert "creado workspace.config.json" in salida
        assert (raiz / "d").read_bytes() == b"x"


def crear_enlace(destino, origen):
    try:
        os.symlink(origen, destino, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        resultado = subprocess.run(["cmd", "/c", "mklink", "/J", str(destino), str(origen)], capture_output=True)
        return resultado.returncode == 0
    return False


def test_un_enlace_que_sale_de_la_raiz_se_rechaza():
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        if not crear_enlace(raiz / "salida", fuera):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        with generadores_temporales(("extra", generador_de(("salida/x.txt", "x")))):
            try:
                b().planificar(e.spec(), raiz)
            except b().ErrorDePlan as error:
                assert "salida" in str(error)
            else:
                raise AssertionError("se aceptó una ruta que sale de la raíz")
        assert list(fuera.iterdir()) == []


def test_ensayo_no_escribe_nada():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b"workspace.local.json\n")
        antes = arbol(raiz)
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz), "--ensayo"])
        assert codigo == 0 and errores == ""
        assert arbol(raiz) == antes
        lineas = salida.splitlines()
        assert "crearía workspace.config.json" in lineas and "crearía workspace.local.json" in lineas
        assert "ya existe .gitignore" in lineas
        assert "falta en .gitignore: .claude/estado/" in lineas
        assert "creado" not in salida
        assert "ensayo" in lineas[-1] and "2 se crearían" in lineas[-1] and "1 ya existen" in lineas[-1], lineas[-1]


def test_ensayo_no_crea_ni_la_raiz():
    with Escenario() as e:
        codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz), "--ensayo"])
        assert codigo == 0 and "crearía .gitignore" in salida
        assert not e.raiz.exists()


def test_ensayo_con_config_invalida_sale_dos():
    with Escenario() as e:
        mala = e.spec()
        mala["config"]["schema_version"] = 9
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec(mala)), "--raiz", str(e.raiz), "--ensayo"])
        assert codigo == 2 and "schema_version" in errores and salida == ""


def test_argumentos_invalidos_salen_dos_con_el_uso():
    with Escenario() as e:
        spec = str(e.archivo_spec())
        casos = [[], ["--raiz", str(e.raiz)], ["--spec"], ["--spec", spec, "--raiz"], ["--spec", spec, "--inventada"], ["--spec", spec, "--spec", spec], ["--spec", spec, "--ensayo", "--ensayo"], ["suelto"]]
        for argv in casos:
            codigo, salida, errores = correr(argv)
            assert codigo == 2, argv
            assert "uso: bootstrap.py" in errores and salida == "", (argv, errores)
        assert not e.raiz.exists()


def test_el_ejemplo_se_valida_y_se_genera():
    datos = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    assert datos["spec_version"] == 1
    assert set(datos) <= set(b().claves_conocidas())
    with Escenario() as e:
        for clave in datos["local"]["repos"]:
            datos["local"]["repos"][clave]["path"] = str(e.repo)
        spec = e.archivo_spec(datos, "ejemplo.json")
        codigo, salida, errores = correr(["--spec", str(spec), "--raiz", str(e.raiz), "--ensayo"])
        assert codigo == 0 and errores == "", (salida, errores)
        assert not e.raiz.exists()
        codigo, salida, errores = correr(["--spec", str(spec), "--raiz", str(e.raiz)])
        assert codigo == 0 and errores == "", (salida, errores)
        assert importlib.import_module("config_loader").cargar(e.raiz)["layers"]
        assert (e.raiz / ".gitignore").read_bytes() == GITIGNORE_ESPERADO.encode("utf-8")


def test_el_ejemplo_esta_en_lf_sin_bom_y_con_salto_final():
    datos = EJEMPLO.read_bytes()
    assert not datos.startswith(b"\xef\xbb\xbf") and b"\r" not in datos and datos.endswith(b"\n")


def test_un_generador_registrado_suma_su_clave_y_sus_archivos():
    with Escenario() as e:
        def generar(spec):
            return [("extra/" + nombre + ".txt", "x\n") for nombre in spec.get("otra", [])]

        alta = ("extra", generar, {"claves": ("otra",)})
        assert "otra" not in b().claves_conocidas()
        with generadores_temporales(alta):
            assert "otra" in b().claves_conocidas()
            assert {"spec_version", "config", "local"} <= set(b().claves_conocidas())
            spec = e.archivo_spec(e.spec(otra=["uno", "dos"]))
            codigo, salida, _ = correr(["--spec", str(spec), "--raiz", str(e.raiz)])
            assert codigo == 0, salida
            assert (e.raiz / "extra" / "uno.txt").is_file() and (e.raiz / "extra" / "dos.txt").is_file()
        assert "otra" not in b().claves_conocidas()


def test_un_generador_no_puede_repetir_nombre():
    with generadores_temporales(("extra", generador_de(), {"claves": ("otra",)})):
        try:
            b().registrar_generador("extra", generador_de())
        except ValueError:
            pass
        else:
            raise AssertionError("se aceptó un nombre repetido")


def test_el_validador_de_un_generador_rechaza_la_spec_sin_escribir():
    with Escenario() as e:
        def validar(spec):
            if not isinstance(spec.get("otra"), list):
                raise b().SpecInvalida("otra debe ser una lista")

        with generadores_temporales(("extra", generador_de(("extra.txt", "x")), {"claves": ("otra",), "validar": validar})):
            raiz = e.crear_raiz()
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec(e.spec(otra="no"))), "--raiz", str(raiz)])
            assert codigo == 2 and "otra debe ser una lista" in errores and salida == ""
            assert arbol(raiz) == {}


def test_un_error_interno_sale_dos_sin_escribir():
    with Escenario() as e:
        def explota(spec):
            raise RuntimeError("falla del generador")

        with generadores_temporales(("extra", explota)):
            raiz = e.crear_raiz()
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
            assert codigo == 2 and "error interno" in errores and "falla del generador" in errores and salida == ""
            assert arbol(raiz) == {}


def test_cli_real_exito_y_error_en_utf8():
    with Escenario() as e:
        script = str(AQUI / "bootstrap.py")
        spec = str(e.archivo_spec())
        ok = subprocess.run([sys.executable, "-W", "error", script, "--spec", spec, "--raiz", str(e.raiz)], capture_output=True)
        assert ok.returncode == 0 and ok.stderr == b"", ok.stderr
        assert "creado workspace.config.json".encode("utf-8") in ok.stdout
        repetida = subprocess.run([sys.executable, "-W", "error", script, "--spec", spec, "--raiz", str(e.raiz)], capture_output=True)
        assert repetida.returncode == 0 and "ya existía workspace.config.json".encode("utf-8") in repetida.stdout
        mala = e.spec()
        mala["config"]["schema_version"] = 9
        roja = subprocess.run([sys.executable, "-W", "error", script, "--spec", str(e.archivo_spec(mala, "mala.json")), "--raiz", str(e.base / "otra")], capture_output=True)
        assert roja.returncode == 2 and roja.stdout == b"" and "la config no es válida".encode("utf-8") in roja.stderr
        assert not (e.base / "otra").exists()


def test_cli_real_usa_el_cwd_sin_raiz():
    with Escenario() as e:
        e.crear_raiz()
        resultado = subprocess.run([sys.executable, "-W", "error", str(AQUI / "bootstrap.py"), "--spec", str(e.archivo_spec())], capture_output=True, cwd=e.raiz)
        assert resultado.returncode == 0, resultado.stderr
        assert (e.raiz / "workspace.config.json").is_file() and (e.raiz / ".gitignore").is_file()


def test_cli_real_con_bandera_desconocida_sale_dos():
    resultado = subprocess.run([sys.executable, "-W", "error", str(AQUI / "bootstrap.py"), "--nada"], capture_output=True)
    assert resultado.returncode == 2 and resultado.stdout == b"" and b"uso: bootstrap.py" in resultado.stderr


def foto(base):
    vista = {}
    for actual, carpetas, archivos in os.walk(base):
        for nombre in list(carpetas):
            ruta = os.path.join(actual, nombre)
            if os.path.islink(ruta) or (hasattr(os.path, "isjunction") and os.path.isjunction(ruta)):
                carpetas.remove(nombre)
                vista[os.path.relpath(ruta, base)] = ("enlace", os.readlink(ruta))
            else:
                vista[os.path.relpath(ruta, base)] = ("carpeta",)
        for nombre in archivos:
            ruta = os.path.join(actual, nombre)
            if os.path.islink(ruta):
                vista[os.path.relpath(ruta, base)] = ("enlace", os.readlink(ruta))
            else:
                estado = os.lstat(ruta)
                vista[os.path.relpath(ruta, base)] = ("archivo", Path(ruta).read_bytes(), estado.st_mtime_ns)
    return vista


def enlace_de_archivo(destino, origen):
    try:
        os.symlink(origen, destino)
        return True
    except (OSError, NotImplementedError):
        return False


def con_aplicar_previo(previo):
    original = b().aplicar

    def envoltura(plan, raiz):
        previo(raiz)
        return original(plan, raiz)

    b().aplicar = envoltura
    return original


def test_carrera_enlace_roto_que_aparece_no_se_sigue():
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        creado = {}

        def poner(r):
            creado["ok"] = enlace_de_archivo(Path(r) / "workspace.config.json", fuera / "por-la-carrera.json")

        original = con_aplicar_previo(poner)
        try:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            b().aplicar = original
        if not creado["ok"]:
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert list(fuera.iterdir()) == []
        assert codigo == 0 and "ya existía workspace.config.json" in salida, (salida, errores)
        assert sorted(os.listdir(raiz)) == [".gitignore", "workspace.config.json", "workspace.local.json"]


def test_carrera_enlace_en_un_ancestro_no_escribe_fuera():
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        with generadores_temporales(("extra", generador_de(("sub/deep/x.txt", "x")))):
            plan = b().planificar(e.spec(), raiz)
        if not crear_enlace(raiz / "sub", fuera):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        try:
            b().aplicar(plan, raiz)
        except b().ErrorDeAplicacion as error:
            assert "sub" in str(error)
        else:
            raise AssertionError("escribió a través del enlace")
        assert list(fuera.iterdir()) == []


def test_el_ancestro_se_revisa_otra_vez_tras_crear_las_carpetas():
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        with generadores_temporales(("extra", generador_de(("sub/x.txt", "x")))):
            plan = b().planificar(e.spec(), raiz)
        makedirs, abrir = os.makedirs, open
        escritos = []
        estado = {"enlace": None}

        def con_carrera(ruta, *a, **k):
            resultado = makedirs(ruta, *a, **k)
            if str(ruta).endswith("sub") and estado["enlace"] is None:
                os.rmdir(ruta)
                estado["enlace"] = crear_enlace(Path(ruta), fuera)
            return resultado

        def espia(ruta, modo="r", *a, **k):
            if modo == "xb":
                escritos.append(os.path.realpath(ruta))
            return abrir(ruta, modo, *a, **k)

        os.makedirs, b().open = con_carrera, espia
        try:
            try:
                b().aplicar(plan, raiz)
            except b().ErrorDeAplicacion as error:
                assert "sale de la raíz" in str(error), str(error)
            else:
                raise AssertionError("escribió a través del enlace")
        finally:
            os.makedirs = makedirs
            del b().open
        if not estado["enlace"]:
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert list(fuera.iterdir()) == []
        assert not any(os.path.normcase(ruta).startswith(os.path.normcase(os.path.realpath(fuera))) for ruta in escritos), escritos


def test_el_ancestro_se_revisa_otra_vez_antes_del_link():
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        with generadores_temporales(("extra", generador_de(("sub/x.txt", "x")))):
            plan = b().planificar(e.spec(), raiz)
        abrir = open
        estado = {"enlace": None}

        class Proxy:
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def write(self, datos):
                return self.f.write(datos)

            def __exit__(self, *a):
                self.f.close()
                if estado["enlace"] is None and "x.txt" in self.f.name:
                    os.rename(raiz / "sub", raiz / "sub_real")
                    estado["enlace"] = crear_enlace(raiz / "sub", fuera)

        def falso(ruta, modo="r", *a, **k):
            f = abrir(ruta, modo, *a, **k)
            return Proxy(f) if modo == "xb" else f

        b().open = falso
        try:
            try:
                b().aplicar(plan, raiz)
            except b().ErrorDeAplicacion as error:
                assert "sale de la raíz" in str(error), str(error)
            else:
                raise AssertionError("publicó a través del enlace")
        finally:
            del b().open
        if not estado["enlace"]:
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert list(fuera.iterdir()) == []


def test_carrera_la_raiz_pasa_a_ser_un_enlace():
    with Escenario() as e:
        fuera = e.base / "fuera"
        fuera.mkdir()
        plan = b().planificar(e.spec(), e.raiz)
        if not crear_enlace(e.raiz, fuera):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        try:
            b().aplicar(plan, e.raiz)
        except b().ErrorDeAplicacion as error:
            assert "raíz" in str(error)
        else:
            raise AssertionError("escribió a través de la raíz enlazada")
        assert list(fuera.iterdir()) == []


def test_enlace_roto_en_el_destino_no_se_sigue():
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        if not enlace_de_archivo(raiz / "workspace.config.json", fuera / "no-existe.json"):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 2 and salida == "" and "workspace.config.json" in errores, (salida, errores)
        assert list(fuera.iterdir()) == []
        assert os.listdir(raiz) == ["workspace.config.json"]


def test_carrera_carpeta_en_el_destino_no_pisa_nada():
    with Escenario() as e:
        raiz = e.crear_raiz()
        original = con_aplicar_previo(lambda r: (Path(r) / "workspace.config.json").mkdir())
        try:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            b().aplicar = original
        assert (raiz / "workspace.config.json").is_dir() and list((raiz / "workspace.config.json").iterdir()) == []
        assert codigo == 0 and "ya existía workspace.config.json" in salida, (salida, errores)
        assert sorted(os.listdir(raiz)) == [".gitignore", "workspace.config.json", "workspace.local.json"]


def test_escritura_que_falla_no_deja_un_archivo_a_medias():
    with Escenario() as e:
        abrir = open

        class Rota:
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

            def write(self, datos):
                self.f.write(datos[:7])
                raise OSError(28, "No space left on device")

        def falso(ruta, modo="r", *a, **k):
            f = abrir(ruta, modo, *a, **k)
            return Rota(f) if modo == "xb" and "workspace.local.json" in str(ruta) else f

        b().open = falso
        try:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])
        finally:
            del b().open
        assert codigo == 2 and "workspace.local.json" in errores
        assert "creado workspace.config.json" in salida
        assert sorted(os.listdir(e.raiz)) == ["workspace.config.json"]
        codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])
        assert codigo == 0 and "creado workspace.local.json" in salida and "ya existía workspace.config.json" in salida
        assert (e.raiz / "workspace.local.json").read_bytes() == local_esperado(e.spec())


def test_si_el_link_falla_no_queda_ni_destino_ni_temporal():
    with Escenario() as e:
        raiz = e.crear_raiz()
        original = os.link

        def sin_links(origen, destino, **k):
            raise OSError(95, "link no soportado")

        os.link = sin_links
        try:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            os.link = original
        assert codigo == 2 and "workspace.config.json" in errores and salida == ""
        assert os.listdir(raiz) == []


def test_publica_con_link_y_no_con_rename_ni_replace():
    with Escenario() as e:
        raiz = e.crear_raiz()
        llamadas = []
        link, rename, replace = os.link, os.rename, os.replace

        def espia(nombre, funcion):
            def envuelta(*a, **k):
                llamadas.append(nombre)
                return funcion(*a, **k)
            return envuelta

        def prohibida(*a, **k):
            raise AssertionError("publicó con rename/replace")

        os.link, os.rename, os.replace = espia("link", link), prohibida, prohibida
        try:
            codigo, _, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            os.link, os.rename, os.replace = link, rename, replace
        assert codigo == 0, errores
        assert llamadas == ["link"] * 3


def combinacion_rechazada(e, preparar, fragmento, extra=()):
    raiz = e.crear_raiz()
    preparar(raiz)
    spec = e.archivo_spec()
    antes = foto(e.base)
    codigo, salida, errores = correr(["--spec", str(spec), "--raiz", str(raiz), *extra])
    assert codigo == 2 and salida == "", (codigo, salida, errores)
    assert "la config no es válida" in errores and fragmento in errores, errores
    assert foto(e.base) == antes


def test_config_existente_incompatible_con_la_spec_sale_dos_sin_escribir():
    otra = {"schema_version": 1, "repos": {"otro": {}}, "layers": {"capa-b": {"extensions": [".b"], "repos": ["otro"]}}}
    with Escenario() as e:
        combinacion_rechazada(e, lambda raiz: (raiz / "workspace.config.json").write_bytes(json.dumps(otra).encode("utf-8")), "falta la ruta del repo 'otro'")
    with Escenario() as e:
        combinacion_rechazada(e, lambda raiz: (raiz / "workspace.config.json").write_bytes(json.dumps(otra).encode("utf-8")), "falta la ruta del repo 'otro'", ["--ensayo"])


def test_local_existente_sin_la_ruta_de_la_spec_sale_dos_sin_escribir():
    with Escenario() as e:
        combinacion_rechazada(e, lambda raiz: (raiz / "workspace.local.json").write_bytes(b"{}"), "falta la ruta del repo 'repo-a'")


def test_config_existente_ilegible_sale_dos_sin_escribir():
    with Escenario() as e:
        combinacion_rechazada(e, lambda raiz: (raiz / "workspace.config.json").write_bytes(b"\xff\x00 no es json"), "workspace.config.json")
    with Escenario() as e:
        combinacion_rechazada(e, lambda raiz: (raiz / "workspace.config.json").mkdir(), "workspace.config.json")


def test_config_existente_igual_a_la_spec_no_cambia_nada():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / "workspace.config.json").write_bytes(esperado_json(e.spec()["config"]))
        antes = foto(e.base)
        codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and "ya existía workspace.config.json" in salida
        assert {k: v for k, v in foto(e.base).items() if k.endswith("workspace.config.json")} == {k: v for k, v in antes.items() if k.endswith("workspace.config.json")}


def crear_instancia(e):
    assert correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])[0] == 0
    return e.raiz


def test_cli_real_sin_raiz_desde_una_subcarpeta_usa_la_instancia():
    with Escenario() as e:
        raiz = crear_instancia(e)
        sub = raiz / "tickets" / "T-1"
        sub.mkdir(parents=True)
        spec = e.archivo_spec()
        antes = foto(e.base)
        resultado = subprocess.run([sys.executable, "-W", "error", str(AQUI / "bootstrap.py"), "--spec", str(spec)], capture_output=True, cwd=sub, timeout=120)
        salida = resultado.stdout.decode("utf-8")
        assert resultado.returncode == 0, resultado.stderr
        assert "ya existía workspace.config.json" in salida and "creado" not in salida.replace("0 creados", "")
        assert foto(e.base) == antes
        assert not (sub / "workspace.config.json").exists()


def test_raiz_explicita_dentro_de_otra_instancia_sale_dos():
    with Escenario() as e:
        raiz = crear_instancia(e)
        spec = e.archivo_spec()
        antes = foto(e.base)
        for destino in (raiz / "anidada", raiz / "tickets" / "T-1" / "mas"):
            for extra in ([], ["--ensayo"]):
                codigo, salida, errores = correr(["--spec", str(spec), "--raiz", str(destino), *extra])
                assert codigo == 2 and salida == "", (codigo, salida)
                assert "dentro de la instancia" in errores, errores
        assert foto(e.base) == antes


def test_raiz_explicita_igual_a_la_instancia_se_acepta():
    with Escenario() as e:
        raiz = crear_instancia(e)
        codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and "3 ya existían" in salida


def test_gitignore_con_bom_se_lee_bien():
    with Escenario() as e:
        raiz = e.crear_raiz()
        original = b"\xef\xbb\xbf" + GITIGNORE_ESPERADO.encode("utf-8")
        (raiz / ".gitignore").write_bytes(original)
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en .gitignore" not in salida, salida
        assert (raiz / ".gitignore").read_bytes() == original


def test_gitignore_con_una_carpeta_que_cubre_la_linea_cuenta_como_presente():
    for patron in (b".claude/\n", b".claude\n", b"/.claude/\r\n"):
        with Escenario() as e:
            raiz = e.crear_raiz()
            (raiz / ".gitignore").write_bytes(patron + b"workspace.local.json\n")
            _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
            assert "falta en .gitignore" not in salida, (patron, salida)
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b".claude-otro/\nclaude/\n.clau/\nworkspace.local.json\n")
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en .gitignore: .claude/estado/" in salida


def test_gitignore_que_es_una_carpeta_se_dice_en_el_informe():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").mkdir()
        codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and "ya existía .gitignore" in salida
        assert "no se pudo leer .gitignore: es una carpeta" in salida, salida
        assert "workspace.local.json" in salida.split("revisá a mano que ignore:")[1], salida
        assert (raiz / ".gitignore").is_dir()


def test_nombres_reservados_y_caracteres_invalidos_se_rechazan_en_el_plan():
    malas = ["CON", "aux/x.txt", "nul.txt", "COM1", "CONOUT$", "conin$", "LPT9.log", "Con.tar.gz", "nul .txt", "x/PRN", "com¹", "lpt².txt",
             "a<b", "a>b", 'a"b', "a|b", "a?b", "a*b", "a\x01b", "a\x1fb", "a\tb"]
    with Escenario() as e:
        raiz = e.crear_raiz()
        for ruta in malas:
            with generadores_temporales(("extra", generador_de((ruta, "x")))):
                try:
                    b().planificar(e.spec(), raiz)
                except b().ErrorDePlan:
                    pass
                else:
                    raise AssertionError(f"se aceptó {ruta!r}")
        assert arbol(raiz) == {}


def test_nombres_parecidos_a_los_reservados_se_aceptan():
    buenas = ["console.txt", "auxiliar/x", "com10", "nulo", "lpt", "conin", "capa-con/x.md", "con-x", "a.b/c.d"]
    with Escenario() as e:
        raiz = e.crear_raiz()
        for ruta in buenas:
            with generadores_temporales(("extra", generador_de((ruta, "x")))):
                plan = b().planificar(e.spec(), raiz)
                assert ruta in [a.ruta for a in plan]


def test_nombre_reservado_por_cli_sale_dos_sin_crear_la_raiz():
    for ruta in ("CON", "aux/x.txt", "nul.txt", "COM1", "CONOUT$"):
        with Escenario() as e:
            with generadores_temporales(("extra", generador_de((ruta, "x")))):
                codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])
            assert codigo == 2 and salida == "" and "el plan no es válido" in errores, (ruta, errores)
            assert not e.raiz.exists(), ruta


def test_raiz_que_termina_en_punto_o_espacio_se_rechaza():
    with Escenario() as e:
        for texto in (str(e.raiz) + ".", str(e.raiz) + " ", str(e.base / "a.") + os.sep + "instancia", str(e.base / "a ") + os.sep + "instancia"):
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", texto])
            assert codigo == 2 and salida == "" and "punto o espacio" in errores, (texto, errores)
        assert sorted(os.listdir(e.base)) == ["gitconfig-aislado", "gitconfig-sistema", "repo-a", "spec.json"]


def test_raiz_con_punto_como_componente_se_acepta():
    with Escenario() as e:
        texto = str(e.base) + os.sep + "." + os.sep + "instancia"
        codigo, _, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", texto])
        assert codigo == 0, errores
        assert (e.raiz / "workspace.config.json").is_file()


def test_nan_o_infinito_en_la_spec_se_rechazan_sin_escribir():
    for valor in (float("nan"), float("inf"), float("-inf")):
        for donde in ("config", "local"):
            with Escenario() as e:
                spec = e.spec()
                spec[donde]["extra"] = {"x": valor}
                raiz = e.crear_raiz()
                codigo, salida, errores = correr(["--spec", str(e.archivo_spec(spec)), "--raiz", str(raiz)])
                assert codigo == 2 and salida == "" and "no se puede escribir como JSON" in errores, (valor, donde, errores)
                assert arbol(raiz) == {}


def test_rutas_de_repos_relativas_o_mal_formadas_invalidan_la_spec():
    with Escenario() as e:
        casos = [
            ("repo-a", "absoluta"), ("./repo-a", "absoluta"), ("..\\repo-a", "absoluta"), ("", "absoluta"), (5, "texto"), (None, "texto"), ({"x": 1}, "texto"),
        ]
        for ruta, fragmento in casos:
            spec = e.spec()
            spec["local"]["repos"]["repo-a"]["path"] = ruta
            rechazada(e, spec, fragmento)
        for local, fragmento in (({"repos": []}, "local.repos"), ({"repos": {"repo-a": 3}}, "local.repos.repo-a")):
            spec = e.spec()
            spec["local"] = local
            rechazada(e, spec, fragmento)


def test_la_raiz_pasa_a_ser_un_enlace_entre_dos_publicaciones():
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        (fuera / "centinela.txt").write_bytes(b"c")
        original = b()._publicar
        estado = {"llamadas": 0, "enlace": None}

        def publicar(*a, **k):
            if estado["llamadas"] == 1:
                os.rename(raiz, e.base / "instancia-movida")
                estado["enlace"] = crear_enlace(raiz, fuera)
            estado["llamadas"] += 1
            return original(*a, **k)

        b()._publicar = publicar
        try:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            b()._publicar = original
        if not estado["enlace"]:
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert codigo == 2 and "raíz" in errores, (codigo, errores)
        assert os.listdir(fuera) == ["centinela.txt"]
        assert "creado workspace.config.json" in salida


def correr_con_unlink_bloqueado(e, raiz, extra=()):
    unlink = os.unlink

    def sin_borrar(ruta, *a, **k):
        if str(ruta).endswith(".tmp"):
            raise PermissionError(13, "bloqueado por otro proceso")
        return unlink(ruta, *a, **k)

    os.unlink = sin_borrar
    try:
        return correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz), *extra])
    finally:
        os.unlink = unlink


def lineas_de_sobrante(lineas, nombre):
    patron = re.compile(r"no se pudo borrar \." + re.escape(nombre) + r"\.[0-9a-f]{32}\.tmp: borralo a mano \(es una copia de " + re.escape(nombre) + r"\)")
    return [l for l in lineas if patron.fullmatch(l)]


def test_un_temporal_que_no_se_puede_borrar_se_avisa_y_sale_cero():
    with Escenario() as e:
        raiz = e.crear_raiz()
        codigo, salida, errores = correr_con_unlink_bloqueado(e, raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        lineas = salida.splitlines()
        for nombre in ("workspace.config.json", "workspace.local.json", ".gitignore"):
            assert len(lineas_de_sobrante(lineas, nombre)) == 1, lineas
            assert (raiz / nombre).is_file()
        assert (raiz / "workspace.local.json").read_bytes() == local_esperado(e.spec())
        assert lineas[-1].startswith("resumen: 3 creados"), lineas
        assert len([n for n in os.listdir(raiz) if n.endswith(".tmp")]) == 3


def test_un_temporal_que_ya_no_esta_no_se_avisa():
    with Escenario() as e:
        raiz = e.crear_raiz()
        unlink = os.unlink

        def ya_borrado(ruta, *a, **k):
            if str(ruta).endswith(".tmp"):
                unlink(ruta, *a, **k)
                raise FileNotFoundError(2, "ya no estaba")
            return unlink(ruta, *a, **k)

        os.unlink = ya_borrado
        try:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            os.unlink = unlink
        assert codigo == 0 and errores == "" and "no se pudo borrar" not in salida, (salida, errores)
        assert sorted(os.listdir(raiz)) == [".gitignore", "workspace.config.json", "workspace.local.json"]


def test_un_temporal_trabado_por_otro_handle_se_avisa():
    if os.name != "nt":
        print("      (solo Windows: un archivo abierto no se puede borrar en POSIX)")
        return
    with Escenario() as e:
        raiz = e.crear_raiz()
        link, asas = os.link, []

        def link_trabado(origen, destino):
            asas.append(open(origen, "rb"))
            return link(origen, destino)

        os.link = link_trabado
        try:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            os.link = link
            for asa in asas:
                asa.close()
        assert codigo == 0 and errores == "", (codigo, errores)
        for nombre in ("workspace.config.json", "workspace.local.json", ".gitignore"):
            assert len(lineas_de_sobrante(salida.splitlines(), nombre)) == 1, salida


def test_un_temporal_que_no_se_borra_tras_un_error_tambien_se_avisa():
    with Escenario() as e:
        raiz = e.crear_raiz()
        link = os.link

        def sin_links(origen, destino, **k):
            raise OSError(95, "link no soportado")

        os.link = sin_links
        try:
            codigo, salida, errores = correr_con_unlink_bloqueado(e, raiz)
        finally:
            os.link = link
        assert codigo == 2 and "workspace.config.json" in errores
        assert len(lineas_de_sobrante(salida.splitlines(), "workspace.config.json")) == 1, salida


class Ns:
    def __init__(self, **k):
        self.__dict__.update(k)


@contextlib.contextmanager
def uuid_de(secuencia):
    real = b().uuid
    llamadas = []

    def uuid4():
        llamadas.append(1)
        return Ns(hex=next(secuencia))

    b().uuid = Ns(uuid4=uuid4)
    try:
        yield llamadas
    finally:
        b().uuid = real


def test_un_nombre_de_temporal_ocupado_no_se_usa():
    fijo = "0" * 32
    with Escenario() as e:
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        (raiz / f".workspace.config.json.{fijo}.tmp").write_bytes(b"del usuario")
        roto = raiz / f".workspace.local.json.{2:032x}.tmp"
        hay_enlace = enlace_de_archivo(roto, fuera / "por-el-temporal.json")
        if not hay_enlace:
            roto.write_bytes(b"del usuario 2")
        secuencia = iter([fijo, fijo, "1" * 32] + [f"{n:032x}" for n in range(2, 60)])
        with uuid_de(secuencia):
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and errores == "", (codigo, errores)
        assert (raiz / f".workspace.config.json.{fijo}.tmp").read_bytes() == b"del usuario"
        assert list(fuera.iterdir()) == []
        assert os.path.islink(roto) if hay_enlace else roto.read_bytes() == b"del usuario 2"
        assert (raiz / "workspace.config.json").read_bytes() == esperado_json(e.spec()["config"])
        assert (raiz / "workspace.local.json").read_bytes() == local_esperado(e.spec())
        assert sorted(n for n in os.listdir(raiz) if n.endswith(".tmp")) == sorted([f".workspace.config.json.{fijo}.tmp", roto.name])


def test_sin_nombre_libre_para_el_temporal_es_un_error():
    fijo = "0" * 32
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / f".workspace.config.json.{fijo}.tmp").write_bytes(b"del usuario")
        secuencia = iter([fijo] * 100)
        with uuid_de(secuencia) as llamadas:
            codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 2 and "nombre libre" in errores and "workspace.config.json" in errores, errores
        assert len(llamadas) == b().INTENTOS_DE_TEMPORAL
        assert sorted(os.listdir(raiz)) == [f".workspace.config.json.{fijo}.tmp"]
        assert (raiz / f".workspace.config.json.{fijo}.tmp").read_bytes() == b"del usuario"


def test_una_barra_final_en_gitignore_no_cubre_un_archivo():
    with Escenario() as e:
        raiz = e.crear_raiz()
        original = b"workspace.local.json/\n.claude/estado/\n"
        (raiz / ".gitignore").write_bytes(original)
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en .gitignore: workspace.local.json" in salida.splitlines(), salida
        assert "falta en .gitignore: .claude/estado/" not in salida
        assert (raiz / ".gitignore").read_bytes() == original


def test_una_carpeta_con_barra_final_cubre_su_contenido_y_su_propia_linea():
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b".claude/estado/\nworkspace.local.json\n")
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en" not in salida
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".gitignore").write_bytes(b"workspace.local.json/\n.claude/\n")
        _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert "falta en .gitignore: workspace.local.json" in salida.splitlines()
        assert "falta en .gitignore: .claude/estado/" not in salida


def entorno_git_aislado(base):
    vacio = base / "gitconfig-vacio"
    vacio.write_bytes(b"")
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    entorno.update(GIT_CONFIG_GLOBAL=str(vacio), GIT_CONFIG_NOSYSTEM="1")
    return entorno


def test_el_informe_del_gitignore_coincide_con_git_check_ignore():
    if shutil.which("git") is None:
        print("      (sin git: prueba omitida)")
        return
    casos = [
        b"workspace.local.json/\n.claude/estado/\n",
        b"workspace.local.json\n.claude/estado/\n",
        b"/workspace.local.json\n.claude/estado\n",
        b".claude/\nworkspace.local.json\n",
        b"workspace.local.json/\n.claude/\n",
    ]
    with Escenario() as e:
        entorno = entorno_git_aislado(e.base)
        for indice, contenido in enumerate(casos):
            repo = e.base / f"git-{indice}"
            (repo / ".claude" / "estado").mkdir(parents=True)
            (repo / "workspace.local.json").write_bytes(b"{}")
            (repo / ".claude" / "estado" / "x").write_bytes(b"x")
            (repo / ".gitignore").write_bytes(contenido)
            subprocess.run(["git", "init", "-q", str(repo)], check=True, env=entorno, capture_output=True, timeout=60)

            def ignorado(ruta):
                return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--no-index", ruta], env=entorno, capture_output=True, timeout=60).returncode == 0

            esperadas = set()
            if not ignorado("workspace.local.json"):
                esperadas.add("workspace.local.json")
            if not ignorado(".claude/estado/x"):
                esperadas.add(".claude/estado/")
            raiz = e.base / f"raiz-{indice}"
            raiz.mkdir()
            (raiz / ".gitignore").write_bytes(contenido)
            _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz), "--ensayo"])
            faltas = {l.split(": ", 1)[1] for l in salida.splitlines() if l.startswith("falta en .gitignore: ")}
            assert faltas == esperadas, (contenido, faltas, esperadas)


def test_plugin_root_se_escribe_al_crear_con_la_carpeta_del_plugin_que_corre():
    with Escenario() as e:
        assert b().RAIZ_DEL_PLUGIN == AQUI.parent
        assert correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])[0] == 0
        local = json.loads((e.raiz / "workspace.local.json").read_text(encoding="utf-8"))
        assert local["plugin_root"] == str(AQUI.parent)
        assert (Path(local["plugin_root"]) / "scripts" / "reglas.py").is_file()
        assert list(local) == ["repos", "plugin_root"]


def test_plugin_root_sale_de_la_constante_del_modulo():
    with Escenario() as e:
        anterior = b().RAIZ_DEL_PLUGIN
        b().RAIZ_DEL_PLUGIN = e.base / "otro-plugin"
        try:
            assert correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])[0] == 0
        finally:
            b().RAIZ_DEL_PLUGIN = anterior
        assert json.loads((e.raiz / "workspace.local.json").read_text(encoding="utf-8"))["plugin_root"] == str(e.base / "otro-plugin")


def test_plugin_root_no_se_anota_si_el_local_ya_existia():
    with Escenario() as e:
        raiz = e.crear_raiz()
        previo = json.dumps(e.spec()["local"]).encode("utf-8")
        (raiz / "workspace.local.json").write_bytes(previo)
        codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and "ya existía workspace.local.json" in salida
        assert (raiz / "workspace.local.json").read_bytes() == previo


def test_la_spec_sigue_rechazando_plugin_root_en_local():
    with Escenario() as e:
        spec = e.spec()
        spec["local"]["plugin_root"] = "x"
        rechazada(e, spec, "plugin_root")


def permisos_de(plan, ruta):
    return next(a.permisos for a in plan if a.ruta == ruta)


def test_una_accion_con_permisos_los_lleva_al_plan():
    with Escenario() as e:
        raiz = e.crear_raiz()
        with generadores_temporales(("extra", generador_de(("gancho", "#!/bin/sh\n", 0o755), ("normal.txt", "x")))):
            plan = b().planificar(e.spec(), raiz)
        assert permisos_de(plan, "gancho") == 0o755
        assert permisos_de(plan, "normal.txt") is None
        assert permisos_de(plan, "workspace.config.json") is None


def test_permisos_invalidos_se_rechazan_en_el_plan():
    with Escenario() as e:
        raiz = e.crear_raiz()
        for permisos in (True, "755", -1, 0o1000, 1.5, 0o7777):
            with generadores_temporales(("extra", generador_de(("g", "x", permisos)))):
                try:
                    b().planificar(e.spec(), raiz)
                except b().ErrorDePlan as error:
                    assert "permisos" in str(error)
                else:
                    raise AssertionError(f"se aceptó {permisos!r}")


def test_los_permisos_se_aplican_al_temporal_antes_del_link():
    with Escenario() as e:
        raiz = e.crear_raiz()
        eventos = []
        chmod, link = os.chmod, os.link

        def espia_chmod(ruta, modo, *a, **k):
            eventos.append(("chmod", os.path.basename(str(ruta)), modo))
            return chmod(ruta, modo, *a, **k)

        def espia_link(origen, destino, *a, **k):
            eventos.append(("link", os.path.basename(str(destino))))
            return link(origen, destino, *a, **k)

        os.chmod, os.link = espia_chmod, espia_link
        try:
            with generadores_temporales(("extra", generador_de(("gancho", "#!/bin/sh\n", 0o755)))):
                codigo, _, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            os.chmod, os.link = chmod, link
        assert codigo == 0, errores
        mios = [x for x in eventos if x[1] == "gancho" or x[1].startswith(".gancho.")]
        assert [x[0] for x in mios] == ["chmod", "link"], eventos
        assert mios[0][2] == 0o755
        assert not any(x[0] == "chmod" and not x[1].startswith(".gancho.") for x in eventos)


def test_en_posix_el_archivo_con_permisos_queda_ejecutable():
    if os.name == "nt":
        print("      (Windows no tiene bit de ejecución: prueba omitida)")
        return
    with Escenario() as e:
        raiz = e.crear_raiz()
        with generadores_temporales(("extra", generador_de(("gancho", "#!/bin/sh\n", 0o755), ("normal.txt", "x")))):
            assert correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])[0] == 0
        assert os.stat(raiz / "gancho").st_mode & 0o777 == 0o755
        assert not os.access(raiz / "normal.txt", os.X_OK)


def con_windows(valor):
    anterior = b().EN_WINDOWS
    b().EN_WINDOWS = valor
    return anterior


def test_en_windows_el_informe_dice_como_marcar_ejecutable():
    with Escenario() as e:
        raiz = e.crear_raiz()
        anterior = con_windows(True)
        try:
            with generadores_temporales(("extra", generador_de((".githooks/pre-commit", "x", 0o755), ("normal.txt", "x")))):
                codigo, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
                ensayo = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.base / "otra"), "--ensayo"])[1]
        finally:
            b().EN_WINDOWS = anterior
        assert codigo == 0
        lineas = salida.splitlines()
        indice = lineas.index("creado .githooks/pre-commit")
        assert lineas[indice + 1] == "al commitear, marcalo ejecutable: git add --chmod=+x .githooks/pre-commit", lineas
        assert sum("marcalo ejecutable" in l for l in lineas) == 1
        assert "al commitear, marcalo ejecutable: git add --chmod=+x .githooks/pre-commit" in ensayo.splitlines()


def test_fuera_de_windows_o_si_ya_existia_no_hay_aviso_de_ejecutable():
    with Escenario() as e:
        raiz = e.crear_raiz()
        anterior = con_windows(False)
        try:
            with generadores_temporales(("extra", generador_de((".githooks/pre-commit", "x", 0o755)))):
                _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            b().EN_WINDOWS = anterior
        assert "marcalo ejecutable" not in salida
    with Escenario() as e:
        raiz = e.crear_raiz()
        (raiz / ".githooks").mkdir()
        (raiz / ".githooks" / "pre-commit").write_bytes(b"mio")
        anterior = con_windows(True)
        try:
            with generadores_temporales(("extra", generador_de((".githooks/pre-commit", "x", 0o755)))):
                _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        finally:
            b().EN_WINDOWS = anterior
        assert "ya existía .githooks/pre-commit" in salida and "marcalo ejecutable" not in salida
        assert (raiz / ".githooks" / "pre-commit").read_bytes() == b"mio"


def pasos_de_git(*pasos):
    return lambda spec: [b().AccionDeGit(tipo, valor) for tipo, valor in pasos]


def instalacion_git():
    return pasos_de_git((b().GIT_INIT, None), (b().GIT_HOOKS, ".githooks"))


def git_aislado(*args, cwd):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in VARIABLES_DE_GIT_AISLADAS}
    resultado = subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=entorno, timeout=60)
    return resultado.returncode, resultado.stdout.decode("utf-8", "replace").strip(), resultado.stderr.decode("utf-8", "replace").strip()


def hay_repo_arriba(ruta):
    return any((p / ".git").exists() for p in (Path(ruta).resolve(), *Path(ruta).resolve().parents))


def correr_con_git(e, raiz, *extra, generadores=None):
    alta = ("instalacion", generadores or instalacion_git())
    with generadores_temporales(alta):
        return correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz), *extra])


def test_git_init_en_una_raiz_fuera_de_todo_repo():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        codigo, salida, errores = correr_con_git(e, e.raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        assert (e.raiz / ".git").is_dir()
        codigo, toplevel, _ = git_aislado("rev-parse", "--show-toplevel", cwd=e.raiz)
        assert codigo == 0 and os.path.normcase(os.path.realpath(toplevel)) == os.path.normcase(os.path.realpath(e.raiz))
        lineas = salida.splitlines()
        assert "git init: repo creado" in lineas, lineas
        assert lineas.index("git init: repo creado") > lineas.index("creado .gitignore")
        assert lineas[-1].startswith("resumen:")


def test_core_hookspath_se_configura_en_local_cuando_no_tiene_valor():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        codigo, salida, _ = correr_con_git(e, e.raiz)
        assert codigo == 0
        assert git_aislado("config", "--local", "--get", "core.hooksPath", cwd=e.raiz)[1] == ".githooks"
        assert "core.hooksPath = .githooks: configurado (--local)" in salida.splitlines()
        assert "hooksPath" not in e.git_global.read_text(encoding="utf-8")
        assert e.git_global.read_bytes() == b""


def test_nunca_se_toca_la_config_global_ni_la_del_sistema():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        e.git_global.write_bytes(b"[user]\n\tname = Otra Persona\n")
        antes = e.git_global.read_bytes()
        antes_listado = git_aislado("config", "--global", "--list", cwd=e.base)
        codigo, _, _ = correr_con_git(e, e.raiz)
        assert codigo == 0
        assert e.git_global.read_bytes() == antes
        assert git_aislado("config", "--global", "--list", cwd=e.base) == antes_listado
        assert git_aislado("config", "--local", "--get", "core.hooksPath", cwd=e.raiz)[1] == ".githooks"
        assert git_aislado("config", "--global", "--get", "core.hooksPath", cwd=e.base)[0] == 1
        assert git_aislado("config", "--system", "--get", "core.hooksPath", cwd=e.base)[0] == 1
        assert e.git_sistema.read_bytes() == b""


def test_un_hookspath_global_no_cuenta_como_valor_del_repo_y_no_se_toca():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        e.git_global.write_bytes(b"[core]\n\thooksPath = /global/hooks\n")
        antes = e.git_global.read_bytes()
        codigo, salida, _ = correr_con_git(e, e.raiz)
        assert codigo == 0
        assert e.git_global.read_bytes() == antes
        assert git_aislado("config", "--local", "--get", "core.hooksPath", cwd=e.raiz)[1] == ".githooks"
        assert "core.hooksPath = .githooks: configurado (--local)" in salida.splitlines()


def test_un_archivo_con_permisos_sin_bit_de_ejecucion_no_lleva_aviso():
    with Escenario() as e:
        anterior = con_windows(True)
        try:
            with generadores_temporales(("extra", generador_de(("datos.txt", "x", 0o644), ("script.sh", "x", 0o700)))):
                _, salida, _ = correr(["--spec", str(e.archivo_spec()), "--raiz", str(e.raiz)])
        finally:
            b().EN_WINDOWS = anterior
        assert "git add --chmod=+x script.sh" in salida
        assert "datos.txt" not in "".join(l for l in salida.splitlines() if "marcalo" in l)


def test_una_raiz_que_ya_es_un_repo_no_se_reinicia_y_conserva_su_hookspath_vacio():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        raiz = e.crear_raiz()
        assert git_aislado("init", "-q", cwd=raiz)[0] == 0
        (raiz / ".git" / "marca").write_bytes(b"no me toques")
        codigo, salida, _ = correr_con_git(e, raiz)
        assert codigo == 0
        assert (raiz / ".git" / "marca").read_bytes() == b"no me toques"
        lineas = salida.splitlines()
        assert "git init: no hace falta, la raíz ya es un repo git" in lineas, lineas
        assert "core.hooksPath = .githooks: configurado (--local)" in lineas


def test_hookspath_con_otro_valor_no_se_toca_y_se_informa():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        raiz = e.crear_raiz()
        git_aislado("init", "-q", cwd=raiz)
        git_aislado("config", "--local", "core.hooksPath", "otros-hooks", cwd=raiz)
        antes = (raiz / ".git" / "config").read_bytes()
        codigo, salida, _ = correr_con_git(e, raiz)
        assert codigo == 0
        assert (raiz / ".git" / "config").read_bytes() == antes
        assert "core.hooksPath = otros-hooks: no se tocó; el pre-commit no va a correr" in salida.splitlines()


def test_hookspath_que_ya_es_githooks_no_se_vuelve_a_escribir():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        raiz = e.crear_raiz()
        git_aislado("init", "-q", cwd=raiz)
        git_aislado("config", "--local", "core.hooksPath", ".githooks", cwd=raiz)
        antes = (raiz / ".git" / "config").read_bytes()
        _, salida, _ = correr_con_git(e, raiz)
        assert (raiz / ".git" / "config").read_bytes() == antes
        assert "core.hooksPath = .githooks: ya estaba" in salida.splitlines()


def test_una_raiz_dentro_de_otro_repo_no_anida_otro_ni_toca_su_config():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        externo = e.base / "externo"
        externo.mkdir()
        git_aislado("init", "-q", cwd=externo)
        antes = (externo / ".git" / "config").read_bytes()
        raiz = externo / "sub" / "instancia"
        codigo, salida, _ = correr_con_git(e, raiz)
        assert codigo == 0
        assert not (raiz / ".git").exists() and not (externo / "sub" / ".git").exists()
        assert (externo / ".git" / "config").read_bytes() == antes
        lineas = salida.splitlines()
        assert any(l.startswith("git init: no se hizo; la raíz está dentro del repo ") and "externo" in l for l in lineas), lineas
        assert any(l.startswith("core.hooksPath: no se tocó; la raíz está dentro del repo ") and l.endswith(", que no es la instancia") for l in lineas), lineas
        assert (raiz / "workspace.config.json").is_file()


def test_una_raiz_que_es_subcarpeta_de_un_repo_existente_tampoco_se_toca():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        externo = e.base / "externo"
        (externo / "sub").mkdir(parents=True)
        git_aislado("init", "-q", cwd=externo)
        antes = (externo / ".git" / "config").read_bytes()
        codigo, salida, _ = correr_con_git(e, externo / "sub")
        assert codigo == 0
        assert (externo / ".git" / "config").read_bytes() == antes
        assert not (externo / "sub" / ".git").exists()
        assert "core.hooksPath = .githooks: configurado (--local)" not in salida


def test_ensayo_no_ejecuta_nada_de_git_y_dice_que_haria():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        e.archivo_spec()
        antes = arbol(e.base)
        codigo, salida, errores = correr_con_git(e, e.raiz, "--ensayo")
        assert codigo == 0 and errores == ""
        assert not e.raiz.exists()
        assert arbol(e.base) == antes
        lineas = salida.splitlines()
        assert "git init: se haría (la raíz no está en ningún repo)" in lineas, lineas
        assert "core.hooksPath = .githooks: se configuraría (--local)" in lineas
        assert lineas[-1].startswith("ensayo:")


def test_ensayo_en_un_repo_existente_no_escribe_su_config():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        raiz = e.crear_raiz()
        git_aislado("init", "-q", cwd=raiz)
        e.archivo_spec()
        antes = arbol(e.base)
        codigo, salida, _ = correr_con_git(e, raiz, "--ensayo")
        assert codigo == 0 and arbol(e.base) == antes
        assert "core.hooksPath = .githooks: se configuraría (--local)" in salida.splitlines()
        assert "git init: no hace falta, la raíz ya es un repo git" in salida.splitlines()


def test_ensayo_dentro_de_otro_repo_dice_que_no_tocaria_nada():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        externo = e.base / "externo"
        externo.mkdir()
        git_aislado("init", "-q", cwd=externo)
        codigo, salida, _ = correr_con_git(e, externo / "nueva", "--ensayo")
        assert codigo == 0
        assert any(l.startswith("git init: no se hizo; la raíz está dentro del repo ") for l in salida.splitlines())
        assert not (externo / "nueva").exists()


def test_sin_git_instalado_los_archivos_salen_y_la_salida_es_cero():
    with Escenario() as e:
        vacio = e.base / "path-vacio"
        vacio.mkdir()
        spec = e.archivo_spec()
        programa = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "import bootstrap\n"
            "bootstrap.registrar_generador('instalacion', lambda spec: [bootstrap.AccionDeGit(bootstrap.GIT_INIT, None), bootstrap.AccionDeGit(bootstrap.GIT_HOOKS, '.githooks')])\n"
            "sys.exit(bootstrap.principal(['--spec', %r, '--raiz', %r]))\n"
        ) % (str(AQUI), str(spec), str(e.raiz))
        entorno = {**os.environ, "PATH": str(vacio)}
        resultado = subprocess.run([sys.executable, "-W", "error", "-c", programa], capture_output=True, env=entorno, timeout=120)
        salida = resultado.stdout.decode("utf-8")
        assert resultado.returncode == 0, resultado.stderr
        assert (e.raiz / "workspace.config.json").is_file()
        assert not (e.raiz / ".git").exists()
        lineas = salida.splitlines()
        assert "git init: no se hizo; git no está instalado" in lineas, lineas
        assert "core.hooksPath: no se tocó; git no está instalado" in lineas


def test_un_git_que_falla_se_informa_sin_cambiar_la_salida():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        original = b()._git

        def roto(argumentos):
            if "init" in argumentos:
                return 1, "", "fatal: no se puede crear el repo"
            return original(argumentos)

        b()._git = roto
        try:
            codigo, salida, _ = correr_con_git(e, e.raiz)
        finally:
            b()._git = original
        assert codigo == 0
        assert "git init: falló: fatal: no se puede crear el repo" in salida.splitlines()
        assert not (e.raiz / ".git").exists()
        assert (e.raiz / "workspace.config.json").is_file()


def test_el_estado_de_git_se_vuelve_a_mirar_al_aplicar_y_no_se_confia_en_el_plan():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        raiz = e.crear_raiz()
        with generadores_temporales(("instalacion", instalacion_git())):
            plan = b().planificar(e.spec(), raiz)
            assert [p.modo for p in plan.pasos_git] == ["hacer", "hacer"]
            git_aislado("init", "-q", cwd=raiz)
            git_aislado("config", "--local", "core.hooksPath", "otros-hooks", cwd=raiz)
            resultados = b().aplicar(plan, raiz)
        assert resultados.git == ["git init: no hace falta, la raíz ya es un repo git", "core.hooksPath = otros-hooks: no se tocó; el pre-commit no va a correr"]
        assert git_aislado("config", "--local", "--get", "core.hooksPath", cwd=raiz)[1] == "otros-hooks"


def test_si_git_desaparece_entre_la_consulta_y_la_escritura_se_informa_sin_romper():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        original = b()._git

        def desaparece(argumentos):
            if "init" in argumentos or "--get" not in argumentos and "config" in argumentos:
                return None
            return original(argumentos)

        b()._git = desaparece
        try:
            codigo, salida, errores = correr_con_git(e, e.raiz)
        finally:
            b()._git = original
        assert codigo == 0 and errores == "", (codigo, errores)
        lineas = salida.splitlines()
        assert "git init: no se hizo; git no está instalado" in lineas, lineas
        assert not (e.raiz / ".git").exists()


def test_si_no_se_puede_leer_el_hookspath_no_se_escribe():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        raiz = e.crear_raiz()
        git_aislado("init", "-q", cwd=raiz)
        antes = (raiz / ".git" / "config").read_bytes()
        original = b()._git

        def ilegible(argumentos):
            if "--get" in argumentos:
                return 128, "", "fatal: bad config line 1"
            return original(argumentos)

        b()._git = ilegible
        try:
            codigo, salida, _ = correr_con_git(e, raiz)
        finally:
            b()._git = original
        assert codigo == 0
        assert (raiz / ".git" / "config").read_bytes() == antes
        assert "core.hooksPath: no se tocó; no se pudo leer su valor (fatal: bad config line 1)" in salida.splitlines()


def test_si_git_no_puede_leer_un_repo_de_arriba_no_se_inicia_otro():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        externo = e.base / "externo"
        (externo / ".git").mkdir(parents=True)
        original = b()._git

        def ownership(argumentos):
            if "rev-parse" in argumentos:
                return 128, "", "fatal: detected dubious ownership in repository"
            return original(argumentos)

        b()._git = ownership
        try:
            codigo, salida, _ = correr_con_git(e, externo / "instancia")
        finally:
            b()._git = original
        assert codigo == 0
        assert not (externo / "instancia" / ".git").exists()
        lineas = salida.splitlines()
        assert any(l.startswith("git init: no se hizo; hay un repo git arriba de la raíz que git no pudo leer") for l in lineas), lineas
        assert "core.hooksPath: no se tocó; hay un repo git arriba de la raíz que git no pudo leer" in lineas, lineas


def test_los_comandos_de_git_son_solo_locales_y_con_la_raiz_como_directorio():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        original, llamadas = b()._git, []

        def espia(argumentos):
            llamadas.append(list(argumentos))
            return original(argumentos)

        b()._git = espia
        try:
            assert correr_con_git(e, e.raiz)[0] == 0
        finally:
            b()._git = original
        assert llamadas
        for llamada in llamadas:
            assert llamada[0] == "-C", llamada
            assert "--global" not in llamada and "--system" not in llamada, llamada
        escrituras = [l for l in llamadas if "config" in l and "--get" not in l]
        assert len(escrituras) == 1 and "--local" in escrituras[0] and escrituras[0][-2:] == ["core.hooksPath", ".githooks"], escrituras


def test_las_acciones_de_git_se_rechazan_si_son_invalidas():
    with Escenario() as e:
        raiz = e.crear_raiz()
        casos = [
            [b().AccionDeGit("clonar", None)],
            [b().AccionDeGit(b().GIT_HOOKS, "../fuera")],
            [b().AccionDeGit(b().GIT_HOOKS, "/abs")],
            [b().AccionDeGit(b().GIT_HOOKS, None)],
            [b().AccionDeGit(b().GIT_HOOKS, "--global")],
            [b().AccionDeGit(b().GIT_INIT, "--bare")],
            [b().AccionDeGit(b().GIT_INIT, None), b().AccionDeGit(b().GIT_INIT, None)],
        ]
        for acciones in casos:
            with generadores_temporales(("extra", generador_de(*acciones))):
                try:
                    b().planificar(e.spec(), raiz)
                except b().ErrorDePlan:
                    pass
                else:
                    raise AssertionError(f"se aceptó {acciones!r}")


def test_las_acciones_de_git_no_corren_si_fallaron_los_archivos():
    with Escenario() as e:
        raiz = e.crear_raiz()
        original, llamadas = b()._git, []
        b()._git = lambda argumentos: llamadas.append(list(argumentos)) or original(argumentos)
        try:
            with generadores_temporales(("a", generador_de(("d/x.txt", "x"))), ("b", instalacion_git())):
                plan = b().planificar(e.spec(), raiz)
                llamadas.clear()
                (raiz / "d").write_bytes(b"archivo en el lugar de la carpeta")
                try:
                    b().aplicar(plan, raiz)
                except b().ErrorDeAplicacion:
                    pass
                else:
                    raise AssertionError("no falló")
        finally:
            b()._git = original
        assert llamadas == []
        assert not (raiz / ".git").exists()


def test_las_acciones_de_git_respetan_la_raiz_real_del_plan():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        raiz = e.crear_raiz()
        fuera = e.base / "fuera"
        fuera.mkdir()
        original = b()._publicar
        estado = {"llamadas": 0, "enlace": None}

        def publicar(*a, **k):
            resultado = original(*a, **k)
            estado["llamadas"] += 1
            if estado["llamadas"] == 3:
                os.rename(raiz, e.base / "instancia-movida")
                estado["enlace"] = crear_enlace(raiz, fuera)
            return resultado

        b()._publicar = publicar
        try:
            codigo, salida, errores = correr_con_git(e, raiz)
        finally:
            b()._publicar = original
        if not estado["enlace"]:
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        assert codigo == 2 and "raíz" in errores, (codigo, errores)
        assert os.listdir(fuera) == []
        assert not (fuera / ".git").exists()


def test_el_informe_dice_en_cada_modo_lo_que_se_hizo_con_git_en_un_repo_propio():
    with Escenario() as e:
        if hay_repo_arriba(e.base):
            print("      (el temporal está dentro de un repo: prueba omitida)")
            return
        assert correr_con_git(e, e.raiz)[0] == 0
        codigo, salida, _ = correr_con_git(e, e.raiz)
        lineas = salida.splitlines()
        assert codigo == 0
        assert "git init: no hace falta, la raíz ya es un repo git" in lineas
        assert "core.hooksPath = .githooks: ya estaba" in lineas


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
