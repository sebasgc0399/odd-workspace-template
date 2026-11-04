import contextlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
PLANTILLA = AQUI.parent / "plantillas" / "pre-commit"

_especificacion = importlib.util.spec_from_file_location("bootstrap_pruebas_del_motor", AQUI / "bootstrap.tests.py")
motor = importlib.util.module_from_spec(_especificacion)
_especificacion.loader.exec_module(motor)
Escenario, arbol, foto, correr = motor.Escenario, motor.arbol, motor.foto, motor.correr
git_aislado, hay_repo_arriba = motor.git_aislado, motor.hay_repo_arriba


def b():
    return importlib.import_module("bootstrap")


def g():
    return importlib.import_module("bootstrap_instalacion")


def d():
    return importlib.import_module("doctor")


def c():
    return importlib.import_module("odd_ws.capas")


@contextlib.contextmanager
def instalacion_registrada():
    copia = list(b().GENERADORES)
    try:
        b().registrar_generador("instalacion", g().generar, claves=g().CLAVES)
        yield
    finally:
        b().GENERADORES[:] = copia


def generar_instancia(e, raiz, *extra):
    with instalacion_registrada():
        return correr(["--spec", str(e.archivo_spec()), "--raiz", str(raiz), *extra])


def sin_repo(e):
    if hay_repo_arriba(e.base):
        print("      (el temporal está dentro de un repo: prueba omitida)")
        return False
    return True


def test_no_suma_claves_a_la_spec():
    assert g().CLAVES == ()


def test_genera_el_pre_commit_de_la_plantilla_y_el_settings_del_plugin():
    with Escenario() as e:
        acciones = g().generar(e.spec())
        archivos = [a for a in acciones if isinstance(a, tuple) and not isinstance(a, b().AccionDeGit)]
        assert [a[0] for a in archivos] == [".githooks/pre-commit", ".claude/settings.json", "tickets/_plantilla/.claude/settings.json"]
        pre_commit, settings, _ = archivos
        assert pre_commit[1] == PLANTILLA.read_bytes() and pre_commit[2] == 0o755
        assert len(settings) == 2
        assert json.loads(settings[1].decode("utf-8")) == {"enabledPlugins": {d().CLAVE_PLUGIN: True}}
        assert settings[1] == b().serializar({"enabledPlugins": {d().CLAVE_PLUGIN: True}})
        assert d().CLAVE_PLUGIN == "odd-ws@odd-workspace-template"


def test_genera_el_settings_de_la_plantilla_del_ticket_igual_al_de_la_raiz():
    with Escenario() as e:
        acciones = g().generar(e.spec())
        porruta = {a[0]: a for a in acciones if isinstance(a, tuple) and not isinstance(a, b().AccionDeGit)}
        raiz, ticket = porruta[".claude/settings.json"], porruta[c().TICKET_SETTINGS]
        assert len(ticket) == 2 and ticket[1] == raiz[1]
        assert ticket[1] == b().serializar({"enabledPlugins": {d().CLAVE_PLUGIN: True}})
        assert ticket[1].endswith(b"}" + bytes([10])) and bytes([13]) not in ticket[1] and not ticket[1].startswith(bytes([0xEF, 0xBB, 0xBF]))
        assert c().TICKET_SETTINGS == "tickets/_plantilla/.claude/settings.json"


def test_pide_git_init_y_el_hookspath_en_ese_orden_y_despues_de_los_archivos():
    with Escenario() as e:
        acciones = g().generar(e.spec())
        git = [a for a in acciones if isinstance(a, b().AccionDeGit)]
        assert git == [b().AccionDeGit(b().GIT_INIT, None), b().AccionDeGit(b().GIT_HOOKS, d().HOOKS_PATH)]
        assert d().HOOKS_PATH == ".githooks"


def test_la_instancia_generada_trae_los_archivos_de_instalacion():
    with Escenario() as e:
        if not sin_repo(e):
            return
        codigo, salida, errores = generar_instancia(e, e.raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        assert (e.raiz / ".githooks" / "pre-commit").read_bytes() == PLANTILLA.read_bytes()
        assert b"\r" not in (e.raiz / ".githooks" / "pre-commit").read_bytes()
        assert json.loads((e.raiz / ".claude" / "settings.json").read_text(encoding="utf-8")) == {"enabledPlugins": {d().CLAVE_PLUGIN: True}}
        lineas = salida.splitlines()
        assert "creado .githooks/pre-commit" in lineas and "creado .claude/settings.json" in lineas
        assert f"creado {c().TICKET_SETTINGS}" in lineas
        assert (e.raiz / c().TICKET_SETTINGS).read_bytes() == (e.raiz / ".claude" / "settings.json").read_bytes()
        assert "git init: repo creado" in lineas and "core.hooksPath = .githooks: configurado (--local)" in lineas


def test_en_posix_el_pre_commit_queda_ejecutable():
    if os.name == "nt":
        print("      (Windows no tiene bit de ejecución: prueba omitida)")
        return
    with Escenario() as e:
        if not sin_repo(e):
            return
        assert generar_instancia(e, e.raiz)[0] == 0
        assert os.stat(e.raiz / ".githooks" / "pre-commit").st_mode & 0o777 == 0o755
        assert not os.access(e.raiz / ".claude" / "settings.json", os.X_OK)


def test_en_windows_el_informe_dice_como_marcarlo_ejecutable():
    with Escenario() as e:
        if not sin_repo(e):
            return
        anterior = b().EN_WINDOWS
        b().EN_WINDOWS = True
        try:
            codigo, salida, _ = generar_instancia(e, e.raiz)
        finally:
            b().EN_WINDOWS = anterior
        assert codigo == 0
        lineas = salida.splitlines()
        aviso = "al commitear, marcalo ejecutable: git add --chmod=+x .githooks/pre-commit"
        assert lineas[lineas.index("creado .githooks/pre-commit") + 1] == aviso
        assert aviso in lineas and sum("marcalo ejecutable" in l for l in lineas) == 1


def test_un_pre_commit_y_un_settings_existentes_no_se_tocan():
    with Escenario() as e:
        if not sin_repo(e):
            return
        raiz = e.crear_raiz()
        (raiz / ".githooks").mkdir()
        (raiz / ".claude").mkdir()
        previos = {".githooks/pre-commit": b"#!/bin/sh\r\nexit 0\r\n", ".claude/settings.json": b'{"permissions": {}}'}
        for nombre, datos in previos.items():
            (raiz / nombre).write_bytes(datos)
        antes = {nombre: (raiz / nombre).stat().st_mtime_ns for nombre in previos}
        codigo, salida, _ = generar_instancia(e, raiz)
        assert codigo == 0
        for nombre, datos in previos.items():
            assert (raiz / nombre).read_bytes() == datos
            assert (raiz / nombre).stat().st_mtime_ns == antes[nombre]
            assert f"ya existía {nombre}" in salida.splitlines()
        assert "marcalo ejecutable" not in salida


def test_completar_una_instancia_anterior_agrega_solo_el_settings_de_la_plantilla_del_ticket():
    with Escenario() as e:
        if not sin_repo(e):
            return
        assert generar_instancia(e, e.raiz)[0] == 0
        (e.raiz / c().TICKET_SETTINGS).unlink()
        antes = {k: v for k, v in arbol(e.raiz).items() if not k.startswith(".git") and k != c().TICKET_SETTINGS}
        codigo, salida, errores = generar_instancia(e, e.raiz)
        assert codigo == 0 and errores == "", (codigo, errores)
        lineas = salida.splitlines()
        assert [l for l in lineas if l.startswith("creado ")] == [f"creado {c().TICKET_SETTINGS}"]
        assert "ya existía .githooks/pre-commit" in lineas and "ya existía .claude/settings.json" in lineas
        assert {k: v for k, v in arbol(e.raiz).items() if not k.startswith(".git") and k != c().TICKET_SETTINGS} == antes
        assert (e.raiz / c().TICKET_SETTINGS).read_bytes() == (e.raiz / ".claude" / "settings.json").read_bytes()


def test_el_doctor_da_ok_sobre_una_instancia_generada():
    with Escenario() as e:
        if not sin_repo(e):
            return
        assert generar_instancia(e, e.raiz)[0] == 0
        doctor = d()

        class Contexto(doctor.Contexto):
            def ejecutar(self, args, cwd=None):
                entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in motor.VARIABLES_DE_GIT_AISLADAS}
                resultado = subprocess.run(args, cwd=cwd or self.cwd, capture_output=True, env=entorno, timeout=60)
                return resultado.returncode, resultado.stdout.decode("utf-8", "replace") + resultado.stderr.decode("utf-8", "replace")

        ctx = Contexto(cwd=e.raiz)
        ctx.entorno = {}
        resultados = {r.id: r for r in [doctor.chequear_plugin_root(ctx), *doctor.chequear_instancia(ctx)]}
        assert set(resultados) == {"plugin-root", "config", "instancia-hooks", "instancia-plugin"}, sorted(resultados)
        for id, r in resultados.items():
            assert r.estado == doctor.OK, (id, r.estado, r.detalle)


def test_volver_a_correr_no_cambia_nada_y_lo_dice():
    with Escenario() as e:
        if not sin_repo(e):
            return
        assert generar_instancia(e, e.raiz)[0] == 0
        antes = {k: v for k, v in foto(e.raiz).items() if not k.startswith(".git")}
        config_antes = (e.raiz / ".git" / "config").read_bytes()
        codigo, salida, _ = generar_instancia(e, e.raiz)
        assert codigo == 0
        assert {k: v for k, v in foto(e.raiz).items() if not k.startswith(".git")} == antes
        assert (e.raiz / ".git" / "config").read_bytes() == config_antes
        lineas = salida.splitlines()
        assert "ya existía .githooks/pre-commit" in lineas and "ya existía .claude/settings.json" in lineas
        assert "git init: no hace falta, la raíz ya es un repo git" in lineas
        assert "core.hooksPath = .githooks: ya estaba" in lineas
        assert not any(l.startswith("creado ") for l in lineas)


def test_el_ensayo_de_la_instalacion_no_escribe_ni_ejecuta_nada():
    with Escenario() as e:
        if not sin_repo(e):
            return
        e.archivo_spec()
        antes = arbol(e.base)
        codigo, salida, errores = generar_instancia(e, e.raiz, "--ensayo")
        assert codigo == 0 and errores == ""
        assert arbol(e.base) == antes and not e.raiz.exists()
        lineas = salida.splitlines()
        assert "crearía .githooks/pre-commit" in lineas and "crearía .claude/settings.json" in lineas
        assert "git init: se haría (la raíz no está en ningún repo)" in lineas
        assert "core.hooksPath = .githooks: se configuraría (--local)" in lineas


def test_la_instalacion_no_toca_la_config_global_de_git():
    with Escenario() as e:
        if not sin_repo(e):
            return
        e.git_global.write_bytes(b"[user]\n\tname = Otra Persona\n")
        antes = e.git_global.read_bytes()
        assert generar_instancia(e, e.raiz)[0] == 0
        assert e.git_global.read_bytes() == antes
        assert git_aislado("config", "--local", "--get", "core.hooksPath", cwd=e.raiz)[1] == ".githooks"


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
