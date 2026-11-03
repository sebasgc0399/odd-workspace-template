import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
SCRIPT = AQUI / "bootstrap.py"
EJEMPLO = AQUI.parent / "plantillas" / "bootstrap.ejemplo.json"

_especificacion = importlib.util.spec_from_file_location("bootstrap_pruebas_del_motor", AQUI / "bootstrap.tests.py")
motor = importlib.util.module_from_spec(_especificacion)
_especificacion.loader.exec_module(motor)
Escenario, arbol, git_aislado, hay_repo_arriba = motor.Escenario, motor.arbol, motor.git_aislado, motor.hay_repo_arriba


def b():
    return importlib.import_module("bootstrap")


def capas():
    return importlib.import_module("odd_ws.capas")


def sin_repo(e):
    if hay_repo_arriba(e.base):
        print("      (el temporal está dentro de un repo: prueba omitida)")
        return False
    return True


def spec_completa(e):
    spec = e.spec()
    spec["config"]["layers"] = {"capa-a": {"extensions": [".ext"], "repos": ["repo-a"], "rule_prefix": "CA"}}
    spec["proyecto"] = {"nombre": "Proyecto Sintetico"}
    return spec


def cli(e, spec, raiz, *extra):
    ruta = e.archivo_spec(spec)
    entorno = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(e.git_global),
        "GIT_CONFIG_SYSTEM": str(e.git_sistema),
        "GIT_CONFIG_NOSYSTEM": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    resultado = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "--spec", str(ruta), "--raiz", str(raiz), *extra], capture_output=True, env=entorno, timeout=300)
    return (
        resultado.returncode,
        resultado.stdout.decode("utf-8").replace("\r\n", "\n"),
        resultado.stderr.decode("utf-8").replace("\r\n", "\n"),
    )


def archivos_esperados():
    c = capas()
    return [
        "workspace.config.json", "workspace.local.json", ".gitignore",
        c.writer("capa-a"), c.revisor("capa-a"), c.skill("capa-a"), c.REVISOR_DISENO, c.CRITERIOS_SKILL,
        c.MATRIZ, c.EVIDENCIA, c.chequeo("capa-a"), c.prueba("capa-a"),
        c.INDICE, c.TICKET_PLANTILLA,
        ".githooks/pre-commit", ".claude/settings.json",
    ]


def sin_git(vista):
    return {k: v for k, v in vista.items() if k != ".git" and not k.startswith(".git/") and not k.startswith(".git\\")}


def test_una_spec_completa_crea_los_archivos_de_los_cinco_generadores_y_configura_git():
    with Escenario() as e:
        if not sin_repo(e):
            return
        codigo, salida, errores = cli(e, spec_completa(e), e.raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        lineas = salida.splitlines()
        for ruta in archivos_esperados():
            assert (e.raiz / ruta).is_file(), ruta
            assert f"creado {ruta}" in lineas, (ruta, lineas)
        assert "git init: repo creado" in lineas, lineas
        assert "core.hooksPath = .githooks: configurado (--local)" in lineas, lineas
        assert (e.raiz / ".git").is_dir()
        assert git_aislado("config", "--local", "--get", "core.hooksPath", cwd=e.raiz)[1] == ".githooks"
        nombres = {p.name for p in e.raiz.rglob("*") if ".git" not in p.relative_to(e.raiz).parts[:1]}
        assert not nombres & {"init", "hooks_path"}, nombres
        assert not any(l.startswith("creado init") or "hooks_path" in l for l in lineas), lineas
        assert lineas[-1] == f"resumen: {len(archivos_esperados())} creados, 0 ya existían", lineas[-1]


def test_los_archivos_salen_en_el_orden_de_los_generadores():
    with Escenario() as e:
        if not sin_repo(e):
            return
        _, salida, _ = cli(e, spec_completa(e), e.raiz)
        lineas = salida.splitlines()
        c = capas()
        orden = ["workspace.config.json", c.writer("capa-a"), c.MATRIZ, c.INDICE, ".githooks/pre-commit"]
        posiciones = [lineas.index(f"creado {ruta}") for ruta in orden]
        assert posiciones == sorted(posiciones), (orden, posiciones)
        assert lineas.index("git init: repo creado") > lineas.index("creado .claude/settings.json")


def test_el_ensayo_muestra_el_plan_completo_y_no_escribe_nada():
    with Escenario() as e:
        if not sin_repo(e):
            return
        spec = spec_completa(e)
        e.archivo_spec(spec)
        antes = arbol(e.base)
        codigo, salida, errores = cli(e, spec, e.raiz, "--ensayo")
        assert codigo == 0 and errores == "", (codigo, errores)
        assert arbol(e.base) == antes and not e.raiz.exists()
        lineas = salida.splitlines()
        for ruta in archivos_esperados():
            assert f"crearía {ruta}" in lineas, (ruta, lineas)
        assert "git init: se haría (la raíz no está en ningún repo)" in lineas
        assert "core.hooksPath = .githooks: se configuraría (--local)" in lineas
        assert lineas[-1] == f"ensayo: {len(archivos_esperados())} se crearían, 0 ya existen, no se escribió nada", lineas[-1]
        assert not any("hooks_path" in l or l.startswith("crearía init") for l in lineas)


def test_una_segunda_corrida_da_todo_ya_existia_y_no_cambia_nada_en_disco():
    with Escenario() as e:
        if not sin_repo(e):
            return
        spec = spec_completa(e)
        assert cli(e, spec, e.raiz)[0] == 0
        antes = sin_git(arbol(e.raiz))
        config_antes = (e.raiz / ".git" / "config").read_bytes()
        codigo, salida, errores = cli(e, spec, e.raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        assert sin_git(arbol(e.raiz)) == antes
        assert (e.raiz / ".git" / "config").read_bytes() == config_antes
        lineas = salida.splitlines()
        for ruta in archivos_esperados():
            assert f"ya existía {ruta}" in lineas, (ruta, lineas)
        assert not any(l.startswith("creado ") for l in lineas)
        assert "git init: no hace falta, la raíz ya es un repo git" in lineas
        assert "core.hooksPath = .githooks: ya estaba" in lineas
        assert lineas[-1] == f"resumen: 0 creados, {len(archivos_esperados())} ya existían"


def test_una_spec_sin_proyecto_sale_dos_con_el_mensaje_de_los_textos():
    with Escenario() as e:
        spec = spec_completa(e)
        del spec["proyecto"]
        codigo, salida, errores = cli(e, spec, e.raiz)
        assert codigo == 2 and salida == "", (codigo, salida, errores)
        assert errores == 'error: proyecto es obligatorio y debe ser un objeto: {"nombre": "<texto>"}\n', errores
        assert "error interno" not in errores
        assert not e.raiz.exists()


def test_una_capa_sin_rule_prefix_sale_dos_con_el_mensaje_de_las_reglas():
    with Escenario() as e:
        spec = spec_completa(e)
        del spec["config"]["layers"]["capa-a"]["rule_prefix"]
        codigo, salida, errores = cli(e, spec, e.raiz)
        assert codigo == 2 and salida == "", (codigo, salida, errores)
        assert errores == (
            "error: layers.capa-a.rule_prefix falta: la entrevista lo deriva de la capa y lo confirma, "
            "y sin él la capa no tiene matriz de reglas\n"
        ), errores
        assert not e.raiz.exists()


def instancia_a_medias(e, spec_en_disco):
    raiz = e.crear_raiz()
    (raiz / "workspace.config.json").write_bytes((json.dumps(spec_en_disco["config"], indent=2) + "\n").encode("utf-8"))
    (raiz / "workspace.local.json").write_bytes((json.dumps(spec_en_disco["local"], indent=2) + "\n").encode("utf-8"))
    return raiz


def mensaje_de_config_distinta(raiz):
    return (
        f"error: la config de la spec no es la de {raiz}/workspace.config.json, que ya existe: el bootstrap no la reescribe, "
        "así que la spec tiene que traerla tal cual (o cambiala a mano antes)\n"
    )


def test_un_rule_prefix_que_solo_trae_la_spec_se_rechaza_en_vez_de_ignorarse():
    with Escenario() as e:
        if not sin_repo(e):
            return
        en_disco = spec_completa(e)
        del en_disco["config"]["layers"]["capa-a"]["rule_prefix"]
        raiz = instancia_a_medias(e, en_disco)
        spec = spec_completa(e)
        e.archivo_spec(spec)
        antes = arbol(e.base)
        for extra in ([], ["--ensayo"]):
            codigo, salida, errores = cli(e, spec, raiz, *extra)
            assert codigo == 2 and salida == "", (codigo, salida, errores)
            assert errores == mensaje_de_config_distinta(raiz), errores
        assert arbol(e.base) == antes


def test_la_comparacion_con_lo_existente_va_antes_de_los_validar_de_los_generadores():
    with Escenario() as e:
        if not sin_repo(e):
            return
        raiz = instancia_a_medias(e, spec_completa(e))
        sin_prefijo = spec_completa(e)
        del sin_prefijo["config"]["layers"]["capa-a"]["rule_prefix"]
        codigo, salida, errores = cli(e, sin_prefijo, raiz)
        assert codigo == 2 and errores == mensaje_de_config_distinta(raiz), errores
        sin_proyecto = spec_completa(e)
        del sin_proyecto["proyecto"]
        sin_proyecto["config"]["nota"] = 1
        codigo, salida, errores = cli(e, sin_proyecto, raiz)
        assert codigo == 2 and errores == mensaje_de_config_distinta(raiz), errores


def test_una_instancia_con_la_config_igual_sigue_aceptandose_por_la_cli():
    with Escenario() as e:
        if not sin_repo(e):
            return
        raiz = instancia_a_medias(e, spec_completa(e))
        codigo, salida, errores = cli(e, spec_completa(e), raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        lineas = salida.splitlines()
        assert "ya existía workspace.config.json" in lineas and "ya existía workspace.local.json" in lineas
        assert "creado .claude/reglas/matriz.csv" in lineas


def test_una_clave_que_nadie_registra_sigue_rechazandose():
    with Escenario() as e:
        spec = spec_completa(e)
        spec["otra"] = 1
        codigo, salida, errores = cli(e, spec, e.raiz)
        assert codigo == 2 and "otra no es una clave conocida" in errores and "proyecto" in errores, errores
        assert not e.raiz.exists()


def test_el_ejemplo_es_una_spec_completa_para_la_cli():
    with Escenario() as e:
        if not sin_repo(e):
            return
        spec = json.loads(EJEMPLO.read_text(encoding="utf-8"))
        assert set(spec) == {"spec_version", "config", "local", "proyecto"}
        for repo in spec["local"]["repos"].values():
            repo["path"] = str(e.repo)
        codigo, salida, errores = cli(e, spec, e.raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        assert (e.raiz / ".githooks" / "pre-commit").is_file() and (e.raiz / ".git").is_dir()
        for capa, datos in spec["config"]["layers"].items():
            assert "rule_prefix" in datos
            assert (e.raiz / capas().writer(capa)).is_file() and (e.raiz / capas().chequeo(capa)).is_file()


def test_registrar_estandar_suma_los_cuatro_generadores_detras_de_config_con_sus_claves():
    copia = list(b().GENERADORES)
    try:
        assert [g.nombre for g in b().GENERADORES] == ["config"]
        b().registrar_estandar()
        asignados = b().GENERADORES
        assert [g.nombre for g in asignados] == ["config", "agentes", "reglas", "textos", "instalacion"]
        por_nombre = {g.nombre: g for g in asignados}
        assert por_nombre["textos"].claves == ("proyecto",)
        assert por_nombre["agentes"].claves == por_nombre["reglas"].claves == por_nombre["instalacion"].claves == ()
        reglas, textos = importlib.import_module("bootstrap_reglas"), importlib.import_module("bootstrap_textos")
        assert por_nombre["reglas"].validar is reglas.validar and por_nombre["textos"].validar is textos.validar
        assert por_nombre["agentes"].validar is None and por_nombre["instalacion"].validar is None
        for nombre in ("agentes", "reglas", "textos", "instalacion"):
            assert por_nombre[nombre].funcion is importlib.import_module("bootstrap_" + nombre).generar
        assert b().claves_conocidas() == ("spec_version", "config", "local", "proyecto")
    finally:
        b().GENERADORES[:] = copia


def test_registrar_estandar_dos_veces_falla_en_voz_alta_y_no_duplica_nada():
    copia = list(b().GENERADORES)
    try:
        b().registrar_estandar()
        registrados = [g.nombre for g in b().GENERADORES]
        try:
            b().registrar_estandar()
        except ValueError as error:
            assert "agentes" in str(error) and "ya está registrado" in str(error), str(error)
        else:
            raise AssertionError("no falló")
        assert [g.nombre for g in b().GENERADORES] == registrados
    finally:
        b().GENERADORES[:] = copia


def test_al_importar_el_modulo_solo_se_registra_config():
    codigo = "import bootstrap; print(','.join(g.nombre for g in bootstrap.GENERADORES))"
    resultado = subprocess.run([sys.executable, "-W", "error", "-c", codigo], capture_output=True, cwd=AQUI, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=120)
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.decode("utf-8").strip() == "config"


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
