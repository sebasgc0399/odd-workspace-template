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
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
EJEMPLO = AQUI.parent / "plantillas" / "bootstrap.ejemplo.json"
GITIGNORE_ESPERADO = "workspace.local.json\n.claude/estado/\n"


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
            "workspace.local.json": esperado_json(spec["local"]),
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
        previos = {
            "workspace.config.json": b"\xef\xbb\xbf{ \"otro\": 1 }\r\n\r\n",
            "workspace.local.json": b"\x00\x01 no es json \xff",
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
        (raiz / "workspace.config.json").write_bytes(b"{}")
        codigo, salida, errores = correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz)])
        assert codigo == 0 and errores == ""
        assert (raiz / "workspace.config.json").read_bytes() == b"{}"
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
