import copy
import csv
import importlib
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
PLANTILLAS = AQUI.parent / "plantillas" / "reglas"
ENCABEZADO_LITERAL = "id,origen,tipo,destino,severidad,numeros,resumen,motivo\n"
CAPAS = {"capa-a": "CAA", "capa-ñ": "CAN"}


def r():
    return importlib.import_module("bootstrap_reglas")


def b():
    return importlib.import_module("bootstrap")


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def spec_de(capas=None, taller=True):
    capas = CAPAS if capas is None else capas
    layers = {}
    for nombre, prefijo in capas.items():
        datos = {"extensions": [".ext"], "repos": ["repo-a"]}
        if taller:
            datos["workshop"] = ["taller/*.ext"]
        if prefijo is not None:
            datos["rule_prefix"] = prefijo
        layers[nombre] = datos
    return {"spec_version": 1, "config": {"schema_version": 1, "repos": {"repo-a": {}}, "layers": layers}}


class Escenario:
    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="breglas-"))
        self.repo = self.base / "repo-a"
        self.repo.mkdir()
        self.raiz = self.base / "instancia"
        return self

    def spec(self, capas=None):
        spec = spec_de(capas)
        spec["local"] = {"repos": {"repo-a": {"path": str(self.repo)}}}
        return spec

    def generar_instancia(self, capas=None):
        spec = self.spec(capas)
        copia = list(b().GENERADORES)
        try:
            propios = [g for g in copia if g.nombre == "config"]
            b().GENERADORES[:] = propios + [b().Generador("reglas", r().generar, r().CLAVES, r().validar)]
            self.raiz.mkdir(exist_ok=True)
            plan = b().planificar(spec, self.raiz)
            resultados = b().aplicar(plan, self.raiz)
        finally:
            b().GENERADORES[:] = copia
        assert all(x.estado == "creado" for x in resultados), resultados
        return spec

    def __exit__(self, *_):
        shutil.rmtree(self.base, onexc=_forzar_borrado)


def entorno_limpio():
    return {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE_"))}


def correr(args, cwd=None):
    resultado = subprocess.run([sys.executable, "-W", "error", *args], capture_output=True, cwd=cwd, env=entorno_limpio())
    return resultado.returncode, resultado.stdout.decode("utf-8"), resultado.stderr.decode("utf-8")


def git(carpeta, *args):
    return subprocess.run(["git", "-C", str(carpeta), *args], capture_output=True, env=entorno_limpio())


def test_las_claves_de_la_spec_son_ninguna():
    assert r().CLAVES == ()


def test_genera_los_archivos_unicos_y_los_de_cada_capa_en_orden():
    rutas = [ruta for ruta, _ in r().generar(spec_de())]
    assert rutas == [
        ".claude/reglas/matriz.csv",
        ".claude/reglas/evidencia.md",
        ".claude/reglas/verificar_capa-a.py",
        ".claude/reglas/verificar_capa-a.tests.py",
        ".claude/reglas/verificar_capa-ñ.py",
        ".claude/reglas/verificar_capa-ñ.tests.py",
    ]


def test_una_capa_mas_suma_exactamente_sus_dos_archivos():
    una = [ruta for ruta, _ in r().generar(spec_de({"capa-a": "CAA"}))]
    assert len(una) == 4 and len(set(una)) == 4
    assert [x for x in una if "capa-ñ" in x] == []


def test_la_matriz_solo_trae_el_encabezado_exacto():
    texto = dict(r().generar(spec_de()))[".claude/reglas/matriz.csv"]
    assert texto == ENCABEZADO_LITERAL
    matriz = importlib.import_module("matriz")
    assert next(csv.reader(io.StringIO(texto))) == matriz.ENCABEZADO
    assert len(texto.splitlines()) == 1


def test_evidencia_lleva_un_titulo_y_una_linea_que_explica():
    texto = dict(r().generar(spec_de()))[".claude/reglas/evidencia.md"]
    lineas = texto.splitlines()
    assert lineas[0].startswith("# ") and len(lineas[0]) > 3
    cuerpo = [l for l in lineas[1:] if l.strip()]
    assert len(cuerpo) >= 1 and all(len(l) > 20 for l in cuerpo[:1])
    assert "matriz" in texto


def test_todo_sale_en_utf8_con_lf_sin_bom_y_salto_final():
    for ruta, texto in r().generar(spec_de()):
        assert isinstance(texto, str), ruta
        crudo = texto.encode("utf-8")
        assert b"\r" not in crudo and not crudo.startswith(b"\xef\xbb\xbf"), ruta
        assert crudo.endswith(b"\n") and not crudo.endswith(b"\n\n"), ruta


def test_los_stubs_salen_de_las_plantillas_del_plugin():
    salida = dict(r().generar(spec_de({"capa-a": "CAA"})))
    assert salida[".claude/reglas/verificar_capa-a.py"] == (PLANTILLAS / "verificar.py").read_text(encoding="utf-8")
    assert salida[".claude/reglas/verificar_capa-a.tests.py"] == (PLANTILLAS / "verificar.tests.py").read_text(encoding="utf-8")


def test_las_plantillas_con_crlf_o_bom_salen_con_lf_sin_bom():
    with Escenario() as e:
        for nombre in ("verificar.py", "verificar.tests.py"):
            (e.base / nombre).write_bytes(b"\xef\xbb\xbfREGLAS = ()\r\nX = 1\r\n")
        anterior = r().PLANTILLAS
        r().PLANTILLAS = e.base
        try:
            salida = dict(r().generar(spec_de({"capa-a": "CAA"})))
        finally:
            r().PLANTILLAS = anterior
        assert salida[".claude/reglas/verificar_capa-a.py"] == "REGLAS = ()\nX = 1\n"
        assert salida[".claude/reglas/verificar_capa-a.tests.py"] == "REGLAS = ()\nX = 1\n"


def test_las_plantillas_son_lf_sin_bom_y_sin_comentarios():
    for nombre in ("verificar.py", "verificar.tests.py"):
        crudo = (PLANTILLAS / nombre).read_bytes()
        assert b"\r" not in crudo and not crudo.startswith(b"\xef\xbb\xbf") and crudo.endswith(b"\n"), nombre
        compile(crudo.decode("utf-8"), nombre, "exec")
        assert not any(l.lstrip().startswith("#") for l in crudo.decode("utf-8").splitlines()), nombre


def test_validar_acepta_capas_con_rule_prefix():
    assert r().validar(spec_de()) is None


def test_validar_exige_el_rule_prefix_de_cada_capa():
    for faltante in ("capa-a", "capa-ñ"):
        capas = {**CAPAS, faltante: None}
        try:
            r().validar(spec_de(capas))
        except b().SpecInvalida as error:
            mensaje = str(error)
            assert type(error) is b().SpecInvalida
            assert faltante in mensaje and "rule_prefix" in mensaje and "entrevista" in mensaje, mensaje
        else:
            assert False, "debía fallar sin rule_prefix en " + faltante


def test_validar_deja_a_la_config_juzgar_un_rule_prefix_presente_pero_invalido():
    for valor in ("", 0, None, "minus"):
        spec = spec_de({"capa-a": "CAA"})
        spec["config"]["layers"]["capa-a"]["rule_prefix"] = valor
        assert r().validar(spec) is None, valor


def test_validar_no_revienta_con_una_config_mal_formada():
    for config in ({}, {"layers": []}, {"layers": {"x": 3}}, {"layers": {"x": {"extensions": [".a"]}}}):
        spec = {"spec_version": 1, "config": config}
        try:
            r().validar(spec)
        except b().SpecInvalida as error:
            assert "x" in str(error) and "rule_prefix" in str(error), str(error)
        except Exception as error:
            assert False, f"{type(error).__name__}: {error}"
    assert r().validar({"spec_version": 1, "config": "no es un objeto"}) is None


def test_validar_no_modifica_la_spec():
    spec = spec_de()
    antes = copy.deepcopy(spec)
    r().validar(spec)
    r().generar(spec)
    assert spec == antes


def test_el_stub_cumple_el_contrato_p1_sin_ninguna_regla():
    with Escenario() as e:
        e.generar_instancia()
        for capa in CAPAS:
            modulo = importlib.util.spec_from_file_location("stub_" + capa, e.raiz / ".claude" / "reglas" / f"verificar_{capa}.py")
            m = importlib.util.module_from_spec(modulo)
            modulo.loader.exec_module(m)
            assert list(m.REGLAS) == []
            for texto in ("", "x\n", "línea ñ\notra\n"):
                ctx = {"ruta": "x", "relativa": "x.ext", "relativa_repo": None, "origen": "taller", "capa": capa, "bytes": texto.encode(),
                       "texto": texto, "es_nuevo": True, "agregadas": [], "hunks": [], "limite": None}
                assert m.verificar(ctx) == []


def test_reglas_py_test_sale_en_verde_sobre_la_instancia_generada():
    with Escenario() as e:
        e.generar_instancia()
        for capa in CAPAS:
            codigo, salida, errores = correr([str(AQUI / "reglas.py"), "--test", capa], cwd=e.raiz)
            assert codigo == 0 and errores == "", (capa, codigo, salida, errores)
        codigo, salida, errores = correr([str(AQUI / "reglas.py"), "--test"], cwd=e.raiz)
        assert codigo == 0 and errores == "" and salida.splitlines()[-1] == "suites: 2, todas en verde", (codigo, salida, errores)


def test_la_suite_del_stub_corre_sola_y_no_necesita_el_plugin():
    with Escenario() as e:
        e.generar_instancia()
        for capa in CAPAS:
            codigo, salida, errores = correr([str(e.raiz / ".claude" / "reglas" / f"verificar_{capa}.tests.py")], cwd=e.base)
            assert codigo == 0 and errores == "" and "en verde" in salida, (capa, salida, errores)


def test_la_suite_del_stub_se_pone_en_rojo_si_el_modulo_rompe_el_contrato():
    malos = {
        "devuelve_basura": "REGLAS = ()\n\n\ndef verificar(ctx):\n    return ['no soy un hallazgo']\n",
        "no_es_lista": "REGLAS = ()\n\n\ndef verificar(ctx):\n    return None\n",
        "revienta": "REGLAS = ()\n\n\ndef verificar(ctx):\n    raise ValueError('x')\n",
        "regla_sin_id": "REGLAS = (object(),)\n\n\ndef verificar(ctx):\n    return []\n",
        "ids_repetidos": "class R:\n    id = 'X-1'\n\n\nREGLAS = (R(), R())\n\n\ndef verificar(ctx):\n    return []\n",
        "modo_invalido": "REGLAS = ()\n\n\ndef verificar(ctx):\n    return [{'id': 'X-1', 'modo': 'otro', 'mensaje': 'm'}]\n",
        "sin_mensaje": "REGLAS = ()\n\n\ndef verificar(ctx):\n    return [{'id': 'X-1', 'modo': 'aviso'}]\n",
        "sin_verificar": "REGLAS = ()\n",
        "devuelve_tupla": "REGLAS = ()\n\n\ndef verificar(ctx):\n    return ()\n",
        "sin_id": "REGLAS = ()\n\n\ndef verificar(ctx):\n    return [{'modo': 'aviso', 'mensaje': 'm'}]\n",
        "id_fuera_de_reglas": "class R:\n    id = 'X-1'\n\n\nREGLAS = (R(),)\n\n\ndef verificar(ctx):\n    return [{'id': 'X-2', 'modo': 'aviso', 'mensaje': 'm'}]\n",
        "no_determinista": "VECES = []\n\n\nREGLAS = ()\n\n\ndef verificar(ctx):\n    VECES.append(1)\n    return [] if len(VECES) % 2 == 0 else [{'id': 'X-1', 'modo': 'aviso', 'mensaje': 'm'}]\n",
        "sin_reglas": "def verificar(ctx):\n    return []\n",
    }
    with Escenario() as e:
        e.generar_instancia({"capa-a": "CAA"})
        modulo = e.raiz / ".claude" / "reglas" / "verificar_capa-a.py"
        suite = e.raiz / ".claude" / "reglas" / "verificar_capa-a.tests.py"
        for nombre, texto in malos.items():
            modulo.write_text(texto, encoding="utf-8")
            codigo, salida, errores = correr([str(suite)], cwd=e.base)
            assert codigo != 0, (nombre, salida, errores)


def test_la_suite_del_stub_acepta_un_modulo_con_reglas_y_hallazgos_validos():
    bueno = (
        "class R:\n    id = 'CAA-01'\n\n\nREGLAS = (R(),)\n\n\n"
        "def verificar(ctx):\n    if 'MAL' in ctx['texto']:\n"
        "        return [{'id': 'CAA-01', 'modo': 'bloqueo', 'severidad': 'CRITICAL', 'linea': 1, 'fragmento': 'MAL', 'mensaje': 'no'}]\n"
        "    return []\n"
    )
    with Escenario() as e:
        e.generar_instancia({"capa-a": "CAA"})
        (e.raiz / ".claude" / "reglas" / "verificar_capa-a.py").write_text(bueno, encoding="utf-8")
        codigo, salida, errores = correr([str(e.raiz / ".claude" / "reglas" / "verificar_capa-a.tests.py")], cwd=e.base)
        assert codigo == 0, (salida, errores)


def test_verificar_archivo_no_da_hallazgos_ni_errores_y_si_sabe_decir_que_si():
    import config_loader
    import verificar_capa

    with Escenario() as e:
        e.generar_instancia({"capa-a": "CAA"})
        assert git(e.raiz, "init", "-q").returncode == 0
        archivo = e.raiz / "taller" / "uno.ext"
        archivo.parent.mkdir()
        archivo.write_text("contenido cualquiera\notra línea\n", encoding="utf-8")
        config = config_loader.cargar(e.raiz)
        assert verificar_capa.verificar_archivo(str(archivo), config) == ("uno.ext", [])
        modulo = e.raiz / ".claude" / "reglas" / "verificar_capa-a.py"
        modulo.write_text("REGLAS = ()\n\n\ndef verificar(ctx):\n    return [{'id': 'CAA-01', 'modo': 'aviso', 'mensaje': 'sí'}]\n", encoding="utf-8")
        resultado = verificar_capa.verificar_archivo(str(archivo), config)
        assert resultado is not None and [h["id"] for h in resultado[1]] == ["CAA-01"], resultado


def test_matriz_py_valida_la_matriz_vacia_y_rechaza_una_rota():
    with Escenario() as e:
        e.generar_instancia()
        for capa in CAPAS:
            for modo in ("--destinos", "--severidad"):
                codigo, salida, errores = correr([str(AQUI / "matriz.py"), modo, "--capa", capa, "--raiz", str(e.raiz)])
                assert codigo == 0 and errores == "", (capa, modo, codigo, salida, errores)
        (e.raiz / ".claude" / "reglas" / "matriz.csv").write_text("id,origen\n", encoding="utf-8")
        codigo, _, _ = correr([str(AQUI / "matriz.py"), "--destinos", "--capa", "capa-a", "--raiz", str(e.raiz)])
        assert codigo != 0


def test_la_instancia_generada_no_pisa_lo_que_ya_existe():
    with Escenario() as e:
        e.raiz.mkdir()
        existente = e.raiz / ".claude" / "reglas" / "matriz.csv"
        existente.parent.mkdir(parents=True)
        existente.write_bytes(b"lo mio\n")
        spec = e.spec({"capa-a": "CAA"})
        copia = list(b().GENERADORES)
        try:
            b().GENERADORES[:] = [g for g in copia if g.nombre == "config"] + [b().Generador("reglas", r().generar, r().CLAVES, r().validar)]
            plan = b().planificar(spec, e.raiz)
            resultados = b().aplicar(plan, e.raiz)
        finally:
            b().GENERADORES[:] = copia
        assert existente.read_bytes() == b"lo mio\n"
        assert {x.ruta: x.estado for x in resultados}[".claude/reglas/matriz.csv"] == "ya_existia"
        assert (e.raiz / ".claude" / "reglas" / "verificar_capa-a.py").is_file()


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
