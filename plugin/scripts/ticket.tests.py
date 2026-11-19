import ast
import contextlib
import importlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPT = AQUI / "ticket.py"
sys.path.insert(0, str(AQUI))
VARIABLES_DE_GIT_AISLADAS = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM")


def _cargar(nombre):
    especificacion = importlib.util.spec_from_file_location(nombre, AQUI / (nombre + ".tests.py"))
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


motor = _cargar("bootstrap")
arbol, crear_enlace, hay_repo_arriba = motor.arbol, motor.crear_enlace, motor.hay_repo_arriba

CLAUDE_MD = "# plantilla personalizada\r\ncon CRLF y ñ\r\n".encode("utf-8")
SETTINGS = b'{"enabledPlugins": {"otro@sitio": true}}'
GUIA = b"\x00guia binaria\xff\r\n"
USO = ("uso: ticket.py <id> <slug> [--raiz <carpeta>] [--ensayo]\n"
       "     ticket.py --siguiente [<prefijo>] [--raiz <carpeta>]\n"
       "     ticket.py --activar <id> [--raiz <carpeta>]\n"
       "     ticket.py --desactivar <id> [--raiz <carpeta>]\n"
       "     ticket.py --cobertura [--raiz <carpeta>]\n"
       "     ticket.py --enlaces <id> [--raiz <carpeta>] [--copiar]\n"
       "     ticket.py --enlaces <ruta a un .md> [--copiar]\n")
PLANTILLA = {
    "tickets/_plantilla/CLAUDE.md": CLAUDE_MD,
    "tickets/_plantilla/.claude/settings.json": SETTINGS,
    "tickets/_plantilla/notas/guia.md": GUIA,
}
CREADOS = {
    "CLAUDE.md": CLAUDE_MD,
    ".claude/settings.json": SETTINGS,
    "notas/guia.md": GUIA,
}


def t():
    return importlib.import_module("ticket")


class Escenario:
    def __init__(self, plantilla=True):
        self.plantilla = plantilla

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix="ticket-ñ-"))
        self.repo = self.base / "repo-a"
        self.repo.mkdir()
        self.raiz = self.base / "instancia"
        self.raiz.mkdir()
        config = {"schema_version": 1, "repos": {"repo-a": {}}, "layers": {"capa-a": {"extensions": [".ext"], "repos": ["repo-a"]}}}
        (self.raiz / "workspace.config.json").write_bytes((json.dumps(config, indent=2) + "\n").encode("utf-8"))
        (self.raiz / "workspace.local.json").write_bytes((json.dumps({"repos": {"repo-a": {"path": str(self.repo)}}}) + "\n").encode("utf-8"))
        if self.plantilla:
            self.escribir(PLANTILLA)
        self.git_global = self.base / "gitconfig-global"
        self.git_sistema = self.base / "gitconfig-sistema"
        self.git_global.write_bytes(b"")
        self.git_sistema.write_bytes(b"")
        self.entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k not in ("CLAUDE_PROJECT_DIR", "PYTHONIOENCODING", "PYTHONUTF8")}
        self.entorno.update(GIT_CONFIG_GLOBAL=str(self.git_global), GIT_CONFIG_SYSTEM=str(self.git_sistema), GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
        return self

    def escribir(self, archivos, raiz=None):
        for ruta, datos in archivos.items():
            destino = (raiz or self.raiz) / ruta
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(datos)

    def correr(self, *argv, cwd=None, entorno=None):
        resultado = subprocess.run(
            [sys.executable, "-W", "error", str(SCRIPT), *argv],
            cwd=cwd or self.base, capture_output=True, env={**self.entorno, **(entorno or {})}, timeout=120,
        )
        return (
            resultado.returncode,
            resultado.stdout.decode("utf-8").replace("\r\n", "\n"),
            resultado.stderr.decode("utf-8").replace("\r\n", "\n"),
        )

    def __exit__(self, *_):
        for ruta in sorted(self.base.rglob("*"), reverse=True):
            if ruta.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(ruta)):
                os.rmdir(ruta) if os.name == "nt" and ruta.is_dir() else os.unlink(ruta)
        shutil.rmtree(self.base, onexc=lambda f, r, _e: (os.chmod(r, 0o700), f(r)))


def carpeta(e, nombre="12-mi-ticket"):
    return e.raiz / "tickets" / nombre


def lineas_creadas(nombre="12-mi-ticket", verbo="creado", archivos=None):
    return [f"{verbo} tickets/{nombre}/{ruta}" for ruta in sorted(archivos or CREADOS)]


def rechazado(e, codigo_esperado, fragmento, *argv, **extra):
    antes = arbol(e.base)
    codigo, salida, errores = e.correr(*argv, **extra)
    assert codigo == codigo_esperado, (argv, codigo, salida, errores)
    assert fragmento in errores, (argv, errores)
    assert salida == "", (argv, salida)
    assert arbol(e.base) == antes, (argv, "se escribió algo")
    return errores


def test_crea_el_ticket_copiando_toda_la_plantilla_byte_a_byte():
    with Escenario() as e:
        antes = arbol(e.base)
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz))
        assert codigo == 0 and errores == "", (codigo, errores)
        destino = carpeta(e)
        assert salida == "\n".join([
            *lineas_creadas(),
            "resumen: 3 creados, 0 ya existían",
            f"ticket: {(e.raiz / 'tickets' / '12-mi-ticket').as_posix()}",
        ]) + "\n", salida
        for ruta, datos in CREADOS.items():
            assert (destino / ruta).read_bytes() == datos, ruta
        despues = arbol(e.base)
        nuevas = {k for k in despues if k not in antes}
        assert nuevas == {"instancia/tickets/12-mi-ticket"} | {f"instancia/tickets/12-mi-ticket/{r}" for r in CREADOS} | {
            "instancia/tickets/12-mi-ticket/.claude", "instancia/tickets/12-mi-ticket/notas",
            "instancia/.claude", "instancia/.claude/estado", "instancia/.claude/estado/ticket-activo"}, nuevas
        assert despues["instancia/.claude/estado/ticket-activo"] == b"tickets/12-mi-ticket\n"
        assert all(despues[k] == v for k, v in antes.items()), "cambió algo que ya existía"
        assert not (e.raiz / ".git").exists() and not list(destino.rglob("*.tmp"))


def test_sin_raiz_toma_la_instancia_de_la_sesion():
    with Escenario() as e:
        sesion = e.raiz / "tickets" / "10-otro" / "sub"
        sesion.mkdir(parents=True)
        codigo, salida, errores = e.correr("12", "mi-ticket", cwd=sesion)
        assert codigo == 0 and errores == "", (codigo, errores)
        assert lineas_creadas()[0] in salida.splitlines()
        assert (carpeta(e) / "CLAUDE.md").read_bytes() == CLAUDE_MD
        fuera = e.base / "fuera"
        fuera.mkdir()
        codigo, salida, errores = e.correr("13", "otro", cwd=fuera, entorno={"CLAUDE_PROJECT_DIR": str(e.raiz)})
        assert codigo == 0 and errores == "", (codigo, errores)
        assert (carpeta(e, "13-otro") / ".claude" / "settings.json").read_bytes() == SETTINGS


def test_sin_instancia_en_la_sesion_sale_con_dos_y_no_escribe():
    with Escenario() as e:
        fuera = e.base / "fuera"
        fuera.mkdir()
        errores = rechazado(e, 2, "workspace.config.json", "12", "mi-ticket", cwd=fuera)
        assert errores.startswith("ticket: ") and errores.endswith("\n") and errores.count("\n") == 1, errores


def test_con_raiz_la_carpeta_debe_tener_la_config_y_no_la_busca_arriba():
    with Escenario() as e:
        sub = e.raiz / "tickets"
        rechazado(e, 2, "workspace.config.json", "12", "mi-ticket", "--raiz", str(sub))
        rechazado(e, 2, "workspace.config.json", "12", "mi-ticket", "--raiz", str(e.base / "no-existe"))


def test_una_config_rota_sale_con_dos_y_no_escribe():
    with Escenario() as e:
        (e.raiz / "workspace.config.json").write_bytes(b"{no es json")
        errores = rechazado(e, 2, "workspace.config.json", "12", "mi-ticket", "--raiz", str(e.raiz))
        assert errores.startswith("ticket: ") and "rota" in errores, errores


def test_no_pisa_lo_que_existe_y_completa_lo_que_falta():
    with Escenario() as e:
        propio = b"# lo que el usuario ya escribio\n"
        e.escribir({"tickets/12-mi-ticket/CLAUDE.md": propio})
        destino = carpeta(e)
        antes = (destino / "CLAUDE.md").stat().st_mtime_ns
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz))
        assert codigo == 0 and errores == "", (codigo, errores)
        lineas = salida.splitlines()
        assert "ya existía tickets/12-mi-ticket/CLAUDE.md" in lineas
        assert "creado tickets/12-mi-ticket/.claude/settings.json" in lineas and "creado tickets/12-mi-ticket/notas/guia.md" in lineas
        assert "resumen: 2 creados, 1 ya existían" in lineas
        assert (destino / "CLAUDE.md").read_bytes() == propio and (destino / "CLAUDE.md").stat().st_mtime_ns == antes
        assert (destino / ".claude" / "settings.json").read_bytes() == SETTINGS and (destino / "notas" / "guia.md").read_bytes() == GUIA


def test_volver_a_correr_no_cambia_nada_y_lo_dice():
    with Escenario() as e:
        assert e.correr("12", "mi-ticket", "--raiz", str(e.raiz))[0] == 0
        antes = arbol(e.base)
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz))
        assert codigo == 0 and errores == "", (codigo, errores)
        assert arbol(e.base) == antes
        assert salida.splitlines()[:-1] == [*lineas_creadas(verbo="ya existía"), "resumen: 0 creados, 3 ya existían"], salida
        assert not any(l.startswith("creado ") for l in salida.splitlines())


def test_un_id_es_una_sola_carpeta_en_cualquier_parte_de_tickets():
    with Escenario() as e:
        conflictos = [
            "tickets/12-otro-slug",
            "tickets/archivo/2024/12-viejo",
            "tickets/12-mi-ticket-2",
            "tickets/12-OTRO",
            "tickets/22-x/12-anidado",
        ]
        for ruta in conflictos:
            (e.raiz / ruta).mkdir(parents=True)
            errores = rechazado(e, 1, ruta, "12", "mi-ticket", "--raiz", str(e.raiz))
            assert errores.startswith("ticket: ") and "12" in errores, errores
            shutil.rmtree(e.raiz / ruta)
            for padre in (e.raiz / ruta).parents:
                if padre.name in ("archivo", "2024", "22-x") and not any(padre.iterdir()):
                    padre.rmdir()


def test_el_id_se_compara_sin_distinguir_mayusculas():
    with Escenario() as e:
        (e.raiz / "tickets" / "AB-viejo").mkdir()
        errores = rechazado(e, 1, "tickets/AB-viejo", "ab", "mi-ticket", "--raiz", str(e.raiz))
        assert errores.startswith("ticket: "), errores
        rechazado(e, 1, "tickets/AB-viejo", "Ab", "mi-ticket", "--raiz", str(e.raiz))


def test_varias_carpetas_en_conflicto_se_nombran_todas():
    with Escenario() as e:
        (e.raiz / "tickets" / "12-uno").mkdir()
        (e.raiz / "tickets" / "archivo" / "12-dos").mkdir(parents=True)
        errores = rechazado(e, 1, "tickets/12-uno", "12", "mi-ticket", "--raiz", str(e.raiz))
        assert "tickets/archivo/12-dos" in errores, errores


def test_lo_que_no_es_del_mismo_id_ni_la_plantilla_no_es_conflicto():
    with Escenario() as e:
        for ruta in ("tickets/1-otro", "tickets/123-otro", "tickets/012-otro", "tickets/_plantilla/12-ejemplo", "tickets/x12-otro", "tickets/12"):
            (e.raiz / ruta).mkdir(parents=True)
        (e.raiz / "tickets" / "12-es-un-archivo.md").write_bytes(b"x")
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz))
        assert codigo == 0 and errores == "", (codigo, errores)
        assert (carpeta(e) / "CLAUDE.md").read_bytes() == CLAUDE_MD
        assert not (e.raiz / "tickets" / "_plantilla" / "12-ejemplo" / "CLAUDE.md").exists()


def test_las_carpetas_vacias_de_la_plantilla_no_se_copian_y_la_plantilla_no_cambia():
    with Escenario() as e:
        (e.raiz / "tickets" / "_plantilla" / "vacia").mkdir()
        assert e.correr("12", "mi-ticket", "--raiz", str(e.raiz))[0] == 0
        assert not (carpeta(e) / "vacia").exists()
        assert arbol(e.raiz / "tickets" / "_plantilla") == {**{r.split("tickets/_plantilla/", 1)[1]: d for r, d in PLANTILLA.items()}, ".claude": None, "notas": None, "vacia": None}


def test_sin_plantilla_se_rechaza_y_manda_a_correr_el_bootstrap():
    with Escenario(plantilla=False) as e:
        errores = rechazado(e, 1, "/odd-ws:bootstrap", "12", "mi-ticket", "--raiz", str(e.raiz))
        assert "tickets/_plantilla/CLAUDE.md" in errores, errores
    with Escenario(plantilla=False) as e:
        e.escribir({"tickets/_plantilla/.claude/settings.json": SETTINGS})
        errores = rechazado(e, 1, "/odd-ws:bootstrap", "12", "mi-ticket", "--raiz", str(e.raiz))
        assert not carpeta(e).exists()


def test_una_plantilla_sin_settings_avisa_por_stderr_y_no_cambia_ni_la_salida_ni_el_codigo():
    aviso = "ticket: aviso: la plantilla no tiene tickets/_plantilla/.claude/settings.json, así que una sesión abierta dentro del ticket no carga el plugin: completá la instancia con /odd-ws:bootstrap y volvé a correr ticket.py"
    with Escenario() as e:
        (e.raiz / "tickets" / "_plantilla" / ".claude" / "settings.json").unlink()
        completos = {r: d for r, d in CREADOS.items() if r != ".claude/settings.json"}
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz))
        assert codigo == 0, (codigo, errores)
        assert errores == aviso + "\n", errores
        assert salida == "\n".join([
            *lineas_creadas(archivos=completos),
            "resumen: 2 creados, 0 ya existían",
            f"ticket: {(e.raiz / 'tickets' / '12-mi-ticket').as_posix()}",
        ]) + "\n", salida
        codigo, salida, errores = e.correr("13", "otro", "--raiz", str(e.raiz), "--ensayo")
        assert codigo == 0 and errores == aviso + "\n" and salida.startswith("crearía tickets/13-otro/"), (codigo, salida, errores)


def test_una_plantilla_completa_no_avisa_nada():
    with Escenario() as e:
        for extra in ((), ("--ensayo",)):
            codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz), *extra)
            assert codigo == 0 and errores == "", (extra, codigo, errores)


def test_un_id_o_un_slug_invalido_se_rechaza_con_uno_sin_escribir():
    with Escenario() as e:
        for id in ("a/b", "a b", "ñ", "x" * 129, "..", "a.b", "a\\b", ""):
            errores = rechazado(e, 1, "id", id, "mi-ticket", "--raiz", str(e.raiz))
            assert errores.startswith("ticket: ") and repr(id) in errores, (id, errores)
        for slug in ("Mi-Ticket", "mi_ticket", "-a", "a-", "a--b", "a b", "ñ", "a/b", "..", "a.b", ""):
            errores = rechazado(e, 1, "slug", "12", slug, "--raiz", str(e.raiz))
            assert errores.startswith("ticket: ") and repr(slug) in errores, (slug, errores)


def test_los_ids_y_slugs_validos_en_el_borde_se_aceptan():
    with Escenario() as e:
        for id, slug in (("A_b-9", "a"), ("x" * 128, "a1-b2-c3"), ("-", "a")):
            codigo, salida, errores = e.correr(id, slug, "--raiz", str(e.raiz))
            assert codigo == 0 and errores == "", (id, slug, codigo, errores)
            assert (carpeta(e, f"{id}-{slug}") / "CLAUDE.md").read_bytes() == CLAUDE_MD


def test_los_argumentos_mal_formados_dan_la_linea_de_uso_y_dos():
    with Escenario() as e:
        casos = [
            [], ["12"], ["12", "a", "b"], ["12", "a", "--raiz"], ["12", "a", "--raiz", ""], ["12", "a", "--raiz", "--ensayo"],
            ["12", "a", "--ensayo", "--ensayo"], ["12", "a", "--raiz", "x", "--raiz", "y"], ["12", "a", "--otra"], ["--ensayo"],
            ["--siguiente", "a", "b"], ["--siguiente", "--ensayo"], ["--siguiente", "--siguiente"], ["--siguiente", "a", "--raiz"],
            ["--activar"], ["--activar", "12", "13"], ["--activar", "12", "--ensayo"], ["--activar", "12", "--siguiente"],
            ["--desactivar"], ["--desactivar", "12", "13"], ["12", "a", "--activar"],
            ["--cobertura", "12"], ["--cobertura", "--ensayo"], ["--cobertura", "--siguiente"], ["--cobertura", "--cobertura"],
            ["12", "a", "--cobertura"],
        ]
        for argv in casos:
            rechazado(e, 2, USO.strip(), *argv)
            assert e.correr(*argv)[2] == USO, argv


def test_el_ensayo_muestra_el_plan_y_no_escribe_nada():
    with Escenario() as e:
        antes = arbol(e.base)
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz), "--ensayo")
        assert codigo == 0 and errores == "", (codigo, errores)
        assert arbol(e.base) == antes
        assert salida == "\n".join([
            *lineas_creadas(verbo="crearía"),
            "ensayo: 3 se crearían, 0 ya existen, no se escribió nada",
            f"ticket: {(e.raiz / 'tickets' / '12-mi-ticket').as_posix()}",
        ]) + "\n", salida
        e.escribir({"tickets/12-mi-ticket/CLAUDE.md": b"x"})
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz), "--ensayo")
        assert codigo == 0 and "ya existe tickets/12-mi-ticket/CLAUDE.md" in salida.splitlines()
        assert "ensayo: 2 se crearían, 1 ya existen, no se escribió nada" in salida.splitlines()


def test_el_ensayo_tambien_rechaza_los_conflictos_y_la_plantilla_ausente():
    with Escenario() as e:
        (e.raiz / "tickets" / "12-otro").mkdir()
        rechazado(e, 1, "tickets/12-otro", "12", "mi-ticket", "--raiz", str(e.raiz), "--ensayo")
    with Escenario(plantilla=False) as e:
        rechazado(e, 1, "/odd-ws:bootstrap", "12", "mi-ticket", "--raiz", str(e.raiz), "--ensayo")


def test_la_salida_va_en_utf8_aunque_la_consola_no_lo_sea():
    with Escenario() as e:
        codigo, salida, errores = e.correr("12", "mi-ticket", "--raiz", str(e.raiz), entorno={"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"})
        assert codigo == 0 and errores == "", (codigo, errores)
        assert "ticket-ñ-" in salida and "ñ" in salida.splitlines()[-1], salida
        assert salida.splitlines()[-2] == "resumen: 3 creados, 0 ya existían"


def test_un_ticket_que_es_un_enlace_hacia_fuera_se_rechaza():
    with Escenario() as e:
        fuera = e.base / "fuera"
        fuera.mkdir()
        (e.raiz / "tickets").mkdir(exist_ok=True)
        if not crear_enlace(carpeta(e), fuera):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        errores = rechazado(e, 1, "sale de la raíz", "12", "mi-ticket", "--raiz", str(e.raiz))
        assert list(fuera.iterdir()) == []


def test_una_plantilla_con_un_enlace_hacia_fuera_se_rechaza_sin_copiar_nada():
    with Escenario() as e:
        fuera = e.base / "fuera"
        fuera.mkdir()
        (fuera / "secreto.txt").write_bytes(b"no se copia")
        if not crear_enlace(e.raiz / "tickets" / "_plantilla" / "enlace", fuera):
            print("      (sin permiso para crear enlaces: prueba omitida)")
            return
        errores = rechazado(e, 1, "enlace", "12", "mi-ticket", "--raiz", str(e.raiz))
        assert not carpeta(e).exists()


def test_una_ruta_del_ticket_que_es_un_archivo_se_rechaza_sin_escribir():
    with Escenario() as e:
        e.escribir({"tickets/12-mi-ticket": b"soy un archivo"})
        errores = rechazado(e, 1, "no es una carpeta", "12", "mi-ticket", "--raiz", str(e.raiz))
        assert errores.startswith("ticket: "), errores


def test_el_codigo_no_trae_rutas_de_la_instancia_a_mano():
    textos = [n.value for n in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for literal in ("_plantilla", ".claude", "settings.json", "workspace.config", "tickets", "CLAUDE.md"):
        assert not [t for t in textos if literal in t], literal


def test_las_funciones_publicas_describen_conflictos_y_plantilla():
    with Escenario() as e:
        assert t().carpeta_del_ticket("12", "mi-ticket") == "tickets/12-mi-ticket"
        assert t().conflictos(e.raiz, "12", "mi-ticket") == []
        (e.raiz / "tickets" / "archivo" / "12-viejo").mkdir(parents=True)
        (e.raiz / "tickets" / "12-b").mkdir()
        assert t().conflictos(e.raiz, "12", "mi-ticket") == ["tickets/12-b", "tickets/archivo/12-viejo"]
        assert t().conflictos(e.raiz, "12", "b") == ["tickets/archivo/12-viejo"]
        assert t().archivos_de_la_plantilla(e.raiz) == [(ruta, CREADOS[ruta]) for ruta in sorted(CREADOS)]


def test_principal_en_el_mismo_proceso_devuelve_los_mismos_codigos():
    with Escenario() as e:
        def correr(*argv):
            salida, errores = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
                codigo = t().principal(list(argv))
            return codigo, salida.getvalue(), errores.getvalue()

        assert correr("12", "mi-ticket", "--raiz", str(e.raiz), "--ensayo")[0] == 0
        assert not carpeta(e).exists()
        assert correr("12", "mi-ticket", "--raiz", str(e.raiz))[0] == 0 and carpeta(e).is_dir()
        assert correr("12", "otro-slug", "--raiz", str(e.raiz))[0] == 1
        assert correr("12")[0:2] == (2, "") and correr("12")[2] == USO
        assert correr("Z", "A", "--raiz", str(e.raiz))[0] == 1


def test_el_settings_del_ticket_generado_por_el_bootstrap_es_el_de_la_raiz():
    caja_modulo = _cargar("bootstrap_e2e")
    if hay_repo_arriba(tempfile.gettempdir()):
        print("      (el temporal está dentro de un repo: prueba omitida)")
        return
    caja = caja_modulo.Caja()
    codigo, _, errores = caja.cli(caja.spec())
    assert codigo == 0, errores
    entorno = {k: v for k, v in caja.entorno.items()}
    resultado = subprocess.run([sys.executable, "-W", "error", str(SCRIPT), "12", "mi-ticket"], cwd=caja.raiz, capture_output=True, env=entorno, timeout=120)
    assert resultado.returncode == 0 and resultado.stderr == b"", resultado.stderr
    destino = caja.raiz / "tickets" / "12-mi-ticket"
    assert (destino / ".claude" / "settings.json").read_bytes() == (caja.raiz / ".claude" / "settings.json").read_bytes()
    assert (destino / "CLAUDE.md").read_bytes() == (caja.raiz / "tickets" / "_plantilla" / "CLAUDE.md").read_bytes()
    assert sorted(p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file()) == [".claude/settings.json", "CLAUDE.md"]
    assert caja.global_.read_bytes() == b"" and caja.sistema.read_bytes() == b""


def con_prefijo(e, prefijo):
    ruta = e.raiz / "workspace.config.json"
    config = json.loads(ruta.read_text(encoding="utf-8"))
    config["tickets"] = {"prefix": prefijo}
    ruta.write_bytes((json.dumps(config, indent=2) + "\n").encode("utf-8"))


def test_siguiente_sin_tickets_es_el_uno_con_el_prefijo_de_la_config_y_no_escribe():
    with Escenario() as e:
        con_prefijo(e, "SM")
        antes = arbol(e.base)
        assert e.correr("--siguiente", "--raiz", str(e.raiz)) == (0, "siguiente: SM-1\n", "")
        assert arbol(e.base) == antes


def test_siguiente_cuenta_los_archivados_y_los_anidados_y_no_reusa_un_numero():
    with Escenario() as e:
        con_prefijo(e, "SM")
        for ruta in ("tickets/SM-1-uno", "tickets/archivo/2025/SM-7-viejo", "tickets/sm-3-minusculas", "tickets/SM-2-x/SM-9-anidado",
                     "tickets/OTRO-40-ajeno", "tickets/SMX-50-parecido", "tickets/SM-abc-sin-numero", "tickets/_plantilla/SM-99-ejemplo"):
            (e.raiz / ruta).mkdir(parents=True)
        (e.raiz / "tickets" / "SM-80-es-un-archivo.md").write_bytes(b"x")
        assert e.correr("--siguiente", "--raiz", str(e.raiz)) == (0, "siguiente: SM-10\n", "")


def test_siguiente_con_un_prefijo_explicito_no_necesita_la_config():
    with Escenario() as e:
        (e.raiz / "tickets" / "T-4-algo").mkdir(parents=True)
        assert e.correr("--siguiente", "T", "--raiz", str(e.raiz)) == (0, "siguiente: T-5\n", "")


def test_siguiente_sin_prefijo_en_la_config_ni_en_el_comando_se_rechaza_con_uno():
    with Escenario() as e:
        rechazado(e, 1, "tickets.prefix", "--siguiente", "--raiz", str(e.raiz))


def test_siguiente_con_un_prefijo_invalido_se_rechaza_con_uno():
    with Escenario() as e:
        for malo in ("S-M", "9A", "x" * 33):
            rechazado(e, 1, "prefijo", "--siguiente", malo, "--raiz", str(e.raiz))


def activo(e):
    ruta = e.raiz / ".claude" / "estado" / "ticket-activo"
    return ruta.read_text(encoding="utf-8") if ruta.is_file() else None


def test_crear_un_ticket_lo_deja_como_activo_y_el_ensayo_no():
    with Escenario() as e:
        assert e.correr("12", "mi-ticket", "--raiz", str(e.raiz), "--ensayo")[0] == 0
        assert activo(e) is None
        assert e.correr("12", "mi-ticket", "--raiz", str(e.raiz))[0] == 0
        assert activo(e) == "tickets/12-mi-ticket\n"
        assert e.correr("13", "otro", "--raiz", str(e.raiz))[0] == 0
        assert activo(e) == "tickets/13-otro\n"


def test_activar_cambia_el_ticket_activo_a_uno_que_ya_existe_tambien_archivado():
    with Escenario() as e:
        for id, slug in (("12", "uno"), ("13", "dos")):
            assert e.correr(id, slug, "--raiz", str(e.raiz))[0] == 0
        assert e.correr("--activar", "12", "--raiz", str(e.raiz)) == (0, "ticket activo: tickets/12-uno\n", "")
        assert activo(e) == "tickets/12-uno\n"
        (e.raiz / "tickets" / "archivo" / "14-viejo").mkdir(parents=True)
        assert e.correr("--activar", "14", "--raiz", str(e.raiz)) == (0, "ticket activo: tickets/archivo/14-viejo\n", "")
        assert activo(e) == "tickets/archivo/14-viejo\n"


def test_activar_sin_carpeta_o_con_varias_se_rechaza_con_uno_y_no_cambia_nada():
    with Escenario() as e:
        assert e.correr("12", "uno", "--raiz", str(e.raiz))[0] == 0
        rechazado(e, 1, "99", "--activar", "99", "--raiz", str(e.raiz))
        (e.raiz / "tickets" / "12-otra").mkdir()
        errores = rechazado(e, 1, "tickets/12-otra", "--activar", "12", "--raiz", str(e.raiz))
        assert "tickets/12-uno" in errores, errores
        rechazado(e, 1, "no es válido", "--activar", "1 2", "--raiz", str(e.raiz))
        assert activo(e) == "tickets/12-uno\n"


def test_desactivar_quita_la_marca_solo_si_es_de_ese_ticket():
    with Escenario() as e:
        for id, slug in (("12", "uno"), ("13", "dos")):
            assert e.correr(id, slug, "--raiz", str(e.raiz))[0] == 0
        assert e.correr("--desactivar", "12", "--raiz", str(e.raiz)) == (0, "ticket activo: tickets/13-dos (no es el 12)\n", "")
        assert activo(e) == "tickets/13-dos\n"
        assert e.correr("--desactivar", "13", "--raiz", str(e.raiz)) == (0, "sin ticket activo\n", "")
        assert activo(e) is None
        assert e.correr("--desactivar", "13", "--raiz", str(e.raiz)) == (0, "sin ticket activo\n", "")


def test_siguiente_con_los_tickets_de_la_config_rotos_sale_con_dos():
    with Escenario() as e:
        con_prefijo(e, "S-M")
        rechazado(e, 2, "tickets.prefix", "--siguiente", "--raiz", str(e.raiz))


def versionar(e, archivos):
    e.escribir(archivos, raiz=e.repo)
    for argv in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *argv], cwd=e.repo, env=e.entorno, check=True, capture_output=True)


def test_cobertura_avisa_las_extensiones_versionadas_sin_capa_de_la_instancia_y_no_escribe():
    import config_loader
    with Escenario() as e:
        versionar(e, {"a.ext": b"x", "sub/b.EXT": b"x", "scripts/x.mjs": b"x", "scripts/y.mjs": b"x", "Makefile": b"x", "README.md": b"x"})
        e.escribir({"sin-versionar.py": b"x"}, raiz=e.repo)
        antes = arbol(e.base)
        assert e.correr("--cobertura", "--raiz", str(e.raiz)) == (
            0,
            "aviso capas-cobertura: extensiones versionadas sin capa: .mjs (2), (sin extensión) (1)\n"
            "  cómo: " + config_loader.AYUDA_COBERTURA + "\n",
            "",
        )
        assert arbol(e.base) == antes
        assert e.correr("--cobertura", cwd=e.raiz / "tickets") == e.correr("--cobertura", "--raiz", str(e.raiz))


def test_cobertura_sin_extensiones_sin_capa_lo_dice_con_cero():
    with Escenario() as e:
        versionar(e, {"a.ext": b"x", "README.md": b"x"})
        assert e.correr("--cobertura", "--raiz", str(e.raiz)) == (0, "capas-cobertura: todo lo versionado en los repos tiene capa o es doc\n", "")


def test_cobertura_sin_instancia_o_con_la_config_rota_sale_con_dos():
    with Escenario() as e:
        rechazado(e, 2, "no hay workspace.config.json", "--cobertura", "--raiz", str(e.base))
        (e.raiz / "workspace.config.json").write_bytes(b"{roto")
        rechazado(e, 2, "está rota", "--cobertura", "--raiz", str(e.raiz))


DOC_CON_ENLACES = (
    "# 12\n\n"
    "[Guía](notas/guia.md) y [sección](notas/guia.md#uso)\n"
    "[notas](notas/) [el repo](../../../repo-a)\n"
    "[con espacios](<carpeta con espacios/año.txt>) [ñandú](ñandú.md)\n"
    "[lo que falta](falta.md) [carpeta que falta](no-hay/)\n"
    "[web](https://example.org/a#b) [correo](mailto:a@b.c) [arriba](#objetivo)\n"
)


def absoluta(ruta):
    return Path(os.path.abspath(ruta)).as_posix()


def ticket_con_enlaces(e):
    e.escribir({
        "tickets/12-mi-ticket/CLAUDE.md": DOC_CON_ENLACES.encode("utf-8"),
        "tickets/12-mi-ticket/notas/guia.md": b"# guia\n",
        "tickets/12-mi-ticket/carpeta con espacios/año.txt": b"x",
        "tickets/12-mi-ticket/ñandú.md": b"x",
    })
    d = absoluta(carpeta(e))
    rutas = [f"{d}/notas/guia.md", f"{d}/notas/guia.md", f"{d}/notas", absoluta(e.repo),
             f"{d}/carpeta con espacios/año.txt", f"{d}/ñandú.md", f"{d}/falta.md", f"{d}/no-hay"]
    listado = (
        f"enlaces de {d}/CLAUDE.md: 10\n"
        f"  archivo  Guía -> {rutas[0]}\n"
        f"  archivo  sección -> {rutas[1]}\n"
        f"  carpeta  notas -> {rutas[2]}\n"
        f"  carpeta  el repo -> {rutas[3]}\n"
        f"  archivo  con espacios -> {rutas[4]}\n"
        f"  archivo  ñandú -> {rutas[5]}\n"
        "rotos: 2\n"
        f"  no existe  lo que falta -> {rutas[6]}\n"
        f"  no existe  carpeta que falta -> {rutas[7]}\n"
        "con esquema, sin verificar: 2\n"
        "  web -> https://example.org/a#b\n"
        "  correo -> mailto:a@b.c\n"
    )
    return listado, rutas


def test_enlaces_de_un_ticket_por_id_los_lista_con_su_ruta_su_tipo_y_los_rotos_aparte_sin_escribir():
    with Escenario() as e:
        listado, _ = ticket_con_enlaces(e)
        antes = arbol(e.base)
        assert e.correr("--enlaces", "12", "--raiz", str(e.raiz)) == (0, listado, "")
        assert e.correr("--enlaces", "12", cwd=e.raiz / "tickets") == (0, listado, "")
        assert arbol(e.base) == antes


def test_enlaces_de_cualquier_md_por_ruta_no_necesita_instancia():
    with Escenario() as e:
        e.escribir({"odd/tasks/feature.md": b"[repo](../../repo-a) [nada](nada.txt)\n"}, raiz=e.base)
        documento = absoluta(e.base / "odd" / "tasks" / "feature.md")
        listado = (f"enlaces de {documento}: 2\n  carpeta  repo -> {absoluta(e.repo)}\n"
                   f"rotos: 1\n  no existe  nada -> {absoluta(e.base / 'odd' / 'tasks' / 'nada.txt')}\n")
        antes = arbol(e.base)
        assert e.correr("--enlaces", "odd/tasks/feature.md", cwd=e.base) == (0, listado, "")
        assert e.correr("--enlaces", documento, cwd=e.repo) == (0, listado, "")
        assert arbol(e.base) == antes


def test_enlaces_de_un_documento_sin_enlaces_dice_cero():
    with Escenario() as e:
        e.escribir({"vacio.md": b"# sin enlaces\n[arriba](#sin-enlaces)\n"}, raiz=e.base)
        assert e.correr("--enlaces", "vacio.md", cwd=e.base) == (0, f"enlaces de {absoluta(e.base / 'vacio.md')}: 0\n", "")


def test_enlaces_de_un_id_o_una_ruta_que_no_sirven_se_rechaza_sin_escribir():
    with Escenario() as e:
        rechazado(e, 1, "el id 99 no tiene carpeta en tickets/", "--enlaces", "99", "--raiz", str(e.raiz))
        (e.raiz / "tickets" / "12-sin-documento").mkdir(parents=True)
        rechazado(e, 1, "tickets/12-sin-documento no tiene CLAUDE.md", "--enlaces", "12", "--raiz", str(e.raiz))
        (e.raiz / "tickets" / "12-otra").mkdir()
        rechazado(e, 1, "tickets/12-otra", "--enlaces", "12", "--raiz", str(e.raiz))
        e.escribir({"notas.txt": b"[a](b.md)\n", "doc.md": b"[a](b.md)\n"}, raiz=e.base)
        for objetivo in ("notas.txt", "nada.md", str(e.raiz)):
            rechazado(e, 1, "no es un .md", "--enlaces", objetivo, cwd=e.base)
        rechazado(e, 1, "--raiz", "--enlaces", "doc.md", "--raiz", str(e.raiz), cwd=e.base)
        rechazado(e, 2, "no hay workspace.config.json", "--enlaces", "12", cwd=e.base)


def portapapeles_falso(e):
    carpeta_bin = e.base / "bin-falso"
    carpeta_bin.mkdir()
    falso = carpeta_bin / "falso.py"
    falso.write_text("import os, sys\nopen(os.environ['COPIADO_POR_EL_FALSO'], 'wb').write(sys.stdin.buffer.read())\n", encoding="utf-8")
    if os.name == "nt":
        (carpeta_bin / "powershell.cmd").write_text(f'@"{sys.executable}" "%~dp0falso.py" %*\r\n', encoding="ascii")
    else:
        for nombre in ("pbcopy", "wl-copy"):
            (carpeta_bin / nombre).write_text(f'#!/bin/sh\nexec "{sys.executable}" "{falso}" "$@"\n', encoding="utf-8")
            (carpeta_bin / nombre).chmod(0o755)
    copiado = e.base / "copiado.bin"
    return {"PATH": str(carpeta_bin), "COPIADO_POR_EL_FALSO": str(copiado)}, copiado


def test_copiar_manda_las_rutas_absolutas_al_portapapeles_y_lista_igual():
    with Escenario() as e:
        listado, rutas = ticket_con_enlaces(e)
        entorno, copiado = portapapeles_falso(e)
        codigo, salida, errores = e.correr("--enlaces", "12", "--copiar", "--raiz", str(e.raiz), entorno=entorno)
        assert (codigo, salida, errores) == (0, listado + "portapapeles: 8 rutas copiadas\n", ""), (codigo, salida, errores)
        assert copiado.read_bytes() == os.linesep.join(rutas).encode("utf-8"), copiado.read_bytes()


def test_copiar_sin_rutas_no_toca_el_portapapeles():
    with Escenario() as e:
        e.escribir({"web.md": b"[web](https://example.org)\n"}, raiz=e.base)
        entorno, copiado = portapapeles_falso(e)
        codigo, salida, errores = e.correr("--copiar", "--enlaces", "web.md", cwd=e.base, entorno=entorno)
        assert (codigo, errores) == (0, ""), (codigo, errores)
        assert salida.endswith("  web -> https://example.org\nportapapeles: no hay rutas que copiar\n"), salida
        assert not copiado.exists()


def test_copiar_sin_herramienta_de_portapapeles_avisa_y_lista_igual():
    with Escenario() as e:
        listado, _ = ticket_con_enlaces(e)
        vacio = e.base / "path-vacio"
        vacio.mkdir()
        codigo, salida, errores = e.correr("--enlaces", "12", "--copiar", "--raiz", str(e.raiz), entorno={"PATH": str(vacio)})
        assert (codigo, salida) == (0, listado), (codigo, salida, errores)
        assert errores.startswith("ticket: aviso: no hay herramienta de portapapeles (busqué ") and errores.endswith(
            "): la lista sale solo por pantalla\n"), errores


def test_copiar_fuera_de_enlaces_y_enlaces_mal_formado_son_error_de_uso():
    with Escenario() as e:
        for argv in (("--copiar",), ("--siguiente", "T", "--copiar"), ("12", "x", "--copiar"), ("--enlaces",),
                     ("--enlaces", "12", "--ensayo"), ("--enlaces", "12", "13"), ("--enlaces", "12", "--copiar", "--copiar")):
            assert e.correr(*argv, "--raiz", str(e.raiz)) == (2, "", USO), argv
        assert e.correr("--siguiente", "T", "--raiz", str(e.raiz)) == (0, "siguiente: T-1\n", "")


def main():
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    if hay_repo_arriba(tempfile.gettempdir()):
        print("el directorio temporal está dentro de un repo: el aislamiento de las pruebas no vale")
        return 1
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
