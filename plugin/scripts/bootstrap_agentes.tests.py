import datetime
import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import plantilla_writer  # noqa: E402
import verificar_capa  # noqa: E402
from odd_ws import capas  # noqa: E402

HOY = datetime.date(2026, 10, 30)
CAPAS = ("sql", "web", "movil")
PROHIBIDAS = re.compile(r"(?:paths|disable-model-invocation|hooks|model)\s*:")
HUELLAS_DEL_REVISOR = {1: "ab73f19f2dae734c3fae2bb0d1d5a1904c89cfed513d9f7344819ed120c9e0dc"}
HUELLAS_DEL_REVISOR_DE_DISENO = {1: "3fbcd9c42c77035b069dd112c707748c7c3ab43792afc7f14e7353d49de3aeac"}
GOLDEN_DEL_WRITER = {
    "sql": "1b99b17a282494b2c83d33bb697c24e88b1c39142eac6bdfea03f408edb1cab4",
    "web": "3bd61a704704a1ba8340969fcb8b191f469c32f5469c83fb34597c32c76fe086",
    "movil": "20774e6229f1458f6257bcc76ab33f0c7cdf93e6d4a90e5580e062c5579f3b0f",
}


def a():
    return importlib.import_module("bootstrap_agentes")


def _forzar_borrado(funcion, ruta, _error):
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


class Temporal:
    def __enter__(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="bootstrap-agentes-"))
        return self

    def __exit__(self, *_):
        shutil.rmtree(self.raiz, onexc=_forzar_borrado)


def spec_de(*nombres):
    return {"spec_version": 1, "config": {"schema_version": 1, "layers": {n: {"extensions": [".x"]} for n in nombres}}}


def archivos(*nombres, hoy=HOY):
    resultado = a().generar(spec_de(*nombres), hoy)
    rutas = [ruta for ruta, _ in resultado]
    assert len(rutas) == len(set(rutas)), rutas
    return dict(resultado)


def frontmatter(texto):
    return texto.split("\n---\n", 1)[0].splitlines()


def sha(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def doctor_tests():
    if "doctor_tests" not in sys.modules:
        especificacion = importlib.util.spec_from_file_location("doctor_tests", AQUI / "doctor.tests.py")
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        sys.modules["doctor_tests"] = modulo
    return sys.modules["doctor_tests"]


def volcar(raiz, generados):
    for ruta, texto in generados.items():
        destino = Path(raiz) / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(texto.encode("utf-8"))


def test_no_suma_claves_a_la_spec():
    assert a().CLAVES == ()


def test_por_capa_salen_el_writer_el_revisor_y_la_skill_y_criterios_una_sola_vez():
    generados = archivos(*CAPAS)
    esperadas = {capas.CRITERIOS_SKILL, capas.REVISOR_DISENO}
    for capa in CAPAS:
        esperadas |= {capas.writer(capa), capas.revisor(capa), capas.skill(capa)}
    assert set(generados) == esperadas, sorted(set(generados) ^ esperadas)
    assert len(generados) == 3 * len(CAPAS) + 2
    assert [ruta for ruta, _ in a().generar(spec_de(*CAPAS), HOY)].count(capas.CRITERIOS_SKILL) == 1
    assert [ruta for ruta, _ in a().generar(spec_de(*CAPAS), HOY)].count(capas.REVISOR_DISENO) == 1


def test_las_rutas_son_las_de_capas_y_van_en_orden_de_la_config():
    resultado = a().generar(spec_de("web", "sql"), HOY)
    assert [ruta for ruta, _ in resultado][:3] == [capas.writer("web"), capas.revisor("web"), capas.skill("web")]
    assert [ruta for ruta, _ in resultado][3:6] == [capas.writer("sql"), capas.revisor("sql"), capas.skill("sql")]
    assert resultado[-1][0] == capas.CRITERIOS_SKILL
    for ruta, texto in resultado:
        assert isinstance(ruta, str) and isinstance(texto, str)


def test_una_capa_que_no_cumple_writer_re_no_genera_nada_y_las_demas_siguen():
    for invalida in ("SQL", "c_sharp", "-web", "", "a/b", "con espacio"):
        generados = archivos(invalida, "sql")
        assert set(generados) == {capas.writer("sql"), capas.revisor("sql"), capas.skill("sql"), capas.CRITERIOS_SKILL, capas.REVISOR_DISENO}, (invalida, sorted(generados))
    solo_invalidas = archivos("SQL", "c_sharp")
    assert set(solo_invalidas) == {capas.CRITERIOS_SKILL}, sorted(solo_invalidas)


def test_una_config_sin_capas_utiles_no_rompe_la_generacion():
    for spec in ({"spec_version": 1}, {"spec_version": 1, "config": {}}, {"spec_version": 1, "config": {"layers": []}},
                 {"spec_version": 1, "config": {"layers": None}}, {"spec_version": 1, "config": {"layers": ["sql"]}},
                 {"spec_version": 1, "config": {"layers": "sql"}}, {"spec_version": 1, "config": []}, []):
        assert [ruta for ruta, _ in a().generar(spec, HOY)] == [capas.CRITERIOS_SKILL], spec


def test_el_writer_es_el_de_plantilla_writer_sin_cambios():
    generados = archivos(*CAPAS)
    for capa in CAPAS:
        texto = generados[capas.writer(capa)]
        assert texto == plantilla_writer.generar(capa), capa
        assert sha(texto) == GOLDEN_DEL_WRITER[capa], capa


def test_centinela_con_la_fecha_inyectada_una_sola_vez_y_suelto():
    generados = archivos("sql", hoy=HOY)
    for nombre, ruta in (("capa-sql", capas.skill("sql")), ("criterios", capas.CRITERIOS_SKILL)):
        lineas = generados[ruta].split("\n")
        assert [l for l in lineas if l.startswith("CENTINELA")] == ["CENTINELA %s 2026-10-30" % nombre], (nombre, lineas[:12])
    otra = archivos("sql", hoy=datetime.date(2027, 1, 2))
    assert "CENTINELA capa-sql 2027-01-02\n" in otra[capas.skill("sql")]
    assert "CENTINELA criterios 2027-01-02\n" in otra[capas.CRITERIOS_SKILL]
    por_texto = a().generar(spec_de("sql"), "2028-03-04")
    assert "CENTINELA criterios 2028-03-04\n" in dict(por_texto)[capas.CRITERIOS_SKILL]
    con_hora = a().generar(spec_de("sql"), datetime.datetime(2029, 5, 6, 23, 59, 58))
    assert "CENTINELA capa-sql 2029-05-06\n" in dict(con_hora)[capas.skill("sql")]


def test_sin_fecha_inyectada_el_centinela_lleva_la_de_hoy():
    antes = datetime.date.today().isoformat()
    texto = dict(a().generar(spec_de("sql")))[capas.CRITERIOS_SKILL]
    despues = datetime.date.today().isoformat()
    assert re.search(r"(?m)^CENTINELA criterios (%s|%s)$" % (antes, despues), texto), texto[:200]


def test_una_fecha_que_no_es_iso_se_rechaza():
    for hoy in ("30/10/2026", "2026-13-01", "ayer", 20261030, "2026-10-30\nCENTINELA x 1"):
        try:
            a().generar(spec_de("sql"), hoy)
        except ValueError:
            continue
        raise AssertionError("aceptó la fecha %r" % (hoy,))


def test_la_skill_de_la_capa_tiene_su_frontmatter_y_el_bloque_no_negociables_bien_formado():
    generados = archivos(*CAPAS)
    for capa in CAPAS:
        texto = generados[capas.skill(capa)]
        cabecera = frontmatter(texto)
        assert cabecera[0] == "---" and "name: capa-%s" % capa in cabecera and "user-invocable: false" in cabecera, cabecera
        assert any(re.fullmatch(r'description: ".+"', l) for l in cabecera), cabecera
        dentro, _, estado = capas.partir_bloque(texto.splitlines())
        assert estado == "ok" and "\n".join(dentro).strip(), (capa, estado)
        assert texto.count(capas.MARCA_ABRE) == 1 and texto.count(capas.MARCA_CIERRA) == 1
        assert texto.index(capas.MARCA_ABRE) < texto.index(capas.MARCA_CIERRA)


def test_el_hook_de_la_capa_lee_el_bloque_de_lo_generado():
    generados = archivos("sql")
    with Temporal() as t:
        volcar(t.raiz, generados)
        leido = verificar_capa.no_negociables("sql", str(t.raiz))
        assert leido and "sql" in leido, leido
        assert verificar_capa.no_negociables("web", str(t.raiz)) is None


def test_la_skill_de_la_capa_guia_lo_que_va_abajo_sin_reglas_inventadas():
    texto = archivos("sql")[capas.skill("sql")]
    despues = texto.split(capas.MARCA_CIERRA, 1)[1]
    assert "onvenciones" in despues and "olde" in despues, despues
    assert "{{" not in texto and "}}" not in texto


def test_criterios_trae_los_criterios_transversales_genericos():
    texto = archivos("sql")[capas.CRITERIOS_SKILL]
    cabecera = frontmatter(texto)
    assert "name: criterios" in cabecera and any(l.startswith("description: ") for l in cabecera), cabecera
    for pedida in ("Paso 0", "hermano", "consumidor", "alcance", "ruta:línea", "CRITICAL", "WARNING", "SUGGESTION"):
        assert pedida.lower() in texto.lower(), pedida
    assert capas.MARCA_ABRE not in texto
    assert len(texto.splitlines()) < 120, len(texto.splitlines())


def test_ninguna_skill_ni_agente_generado_lleva_paths_disable_hooks_ni_model():
    generados = archivos(*CAPAS)
    assert len(generados) == 11, sorted(generados)
    for ruta, texto in generados.items():
        for linea in frontmatter(texto)[1:]:
            assert not PROHIBIDAS.match(linea), (ruta, linea)


def test_el_revisor_es_de_solo_lectura_y_precarga_criterios_y_su_capa():
    generados = archivos(*CAPAS)
    for capa in CAPAS:
        texto = generados[capas.revisor(capa)]
        cabecera = frontmatter(texto)
        assert cabecera[0] == "---" and "name: revisor-%s" % capa in cabecera, cabecera
        assert "tools: Read, Glob, Grep" in cabecera, cabecera
        assert verificar_capa.skills_del_frontmatter(texto) == ["criterios", "capa-%s" % capa]
        descripcion = next(l for l in cabecera if l.startswith("description:"))
        assert re.fullmatch(r'description: "((?:[^"\\]|\\.)*)"', descripcion), descripcion
        assert capa in json.loads(descripcion.split(":", 1)[1].strip())


def test_el_revisor_devuelve_hallazgos_con_severidad_y_evidencia():
    texto = archivos("sql")[capas.revisor("sql")]
    for pedida in ("CRITICAL", "WARNING", "SUGGESTION", "ruta:línea", "CENTINELA criterios", "CENTINELA capa-sql"):
        assert pedida in texto, pedida
    herramientas = next(l for l in frontmatter(texto) if l.startswith("tools:"))
    assert not {"Edit", "Write", "Bash", "PowerShell", "NotebookEdit"} & set(re.findall(r"\w+", herramientas.split(":", 1)[1])), herramientas
    assert "{{" not in texto


def test_el_revisor_trae_su_version_y_su_huella_y_regenerarlo_no_cambia_nada():
    for capa in CAPAS:
        texto = archivos(*CAPAS)[capas.revisor(capa)]
        cabecera = frontmatter(texto)
        version = plantilla_writer.version(plantilla_writer.leer_plantilla(a().PLANTILLA_REVISOR))
        assert isinstance(version, int) and version >= 1
        assert "odd-ws-plantilla: %d" % version in cabecera, cabecera
        assert "odd-ws-hash: %s" % plantilla_writer.huella(texto) in cabecera, cabecera
        assert a().generar_revisor(capa, texto) == texto, capa
        assert a().generar_revisor(capa) == texto, capa


def test_regenerar_el_revisor_conserva_lo_de_la_instancia_y_pone_lo_que_falta():
    base = a().generar_revisor("sql")
    propio = re.sub(r"(<!-- instancia:identidad -->\n).*?(<!-- /instancia:identidad -->)",
                    lambda m: m.group(1) + "Soy el revisor propio.\n" + m.group(2), base, count=1, flags=re.S)
    propio = re.sub(r"(?m)^description:.*$", 'description: "Mía: # propia"', propio, count=1)
    regenerado = a().generar_revisor("sql", propio)
    assert "Soy el revisor propio.\n<!-- /instancia:identidad -->" in regenerado
    assert 'description: "Mía: # propia"' in regenerado
    assert a().generar_revisor("sql", regenerado) == regenerado
    assert plantilla_writer.huella(propio) == plantilla_writer.huella(base)
    roto = base.replace("<!-- /instancia:identidad -->\n", "", 1)
    try:
        a().generar_revisor("sql", roto)
    except ValueError:
        pass
    else:
        raise AssertionError("regeneró sobre bloques mal formados")


def test_el_revisor_rechaza_una_capa_invalida():
    for capa in ("SQL", "c_sharp", "-web", "", "a/b", None):
        try:
            a().generar_revisor(capa)
        except ValueError:
            continue
        raise AssertionError("generó revisor-%r" % (capa,))


def test_cambiar_el_revisor_obliga_a_subir_su_version():
    version = plantilla_writer.version(plantilla_writer.leer_plantilla(a().PLANTILLA_REVISOR))
    huella = sha(a().generar_revisor("x"))
    if version not in HUELLAS_DEL_REVISOR:
        raise AssertionError("anotá %d: %r en HUELLAS_DEL_REVISOR" % (version, huella))
    assert HUELLAS_DEL_REVISOR[version] == huella, (
        "lo generado cambió: subí odd-ws-plantilla en plugin/plantillas/revisor.md y anotá %d: %r en HUELLAS_DEL_REVISOR" % (version + 1, huella))


def test_el_revisor_de_diseno_sale_una_sola_vez_por_instancia_aunque_haya_varias_capas():
    for nombres in (("sql",), CAPAS, ("web", "sql", "movil", "otra")):
        rutas = [ruta for ruta, _ in a().generar(spec_de(*nombres), HOY)]
        assert rutas.count(capas.REVISOR_DISENO) == 1, (nombres, rutas)
    assert capas.REVISOR_DISENO == capas.agente("revisor-diseno")


def test_sin_capas_validas_no_sale_el_revisor_de_diseno():
    for spec in ({"spec_version": 1}, {"spec_version": 1, "config": {}}, {"spec_version": 1, "config": {"layers": {}}},
                 {"spec_version": 1, "config": {"layers": ["sql"]}}, {"spec_version": 1, "config": {"layers": None}}, spec_de("SQL", "c_sharp", "", "a/b")):
        rutas = [ruta for ruta, _ in a().generar(spec, HOY)]
        assert capas.REVISOR_DISENO not in rutas, (spec, rutas)
        assert rutas == [capas.CRITERIOS_SKILL], (spec, rutas)


def test_el_revisor_de_diseno_es_el_de_su_plantilla_y_sale_antes_de_criterios():
    resultado = a().generar(spec_de(*CAPAS), HOY)
    rutas = [ruta for ruta, _ in resultado]
    assert rutas[-2:] == [capas.REVISOR_DISENO, capas.CRITERIOS_SKILL], rutas
    assert dict(resultado)[capas.REVISOR_DISENO] == a().generar_revisor_diseno()


def test_el_revisor_de_diseno_es_de_solo_lectura_y_precarga_criterios():
    texto = archivos(*CAPAS)[capas.REVISOR_DISENO]
    cabecera = frontmatter(texto)
    assert cabecera[0] == "---" and "name: revisor-diseno" in cabecera, cabecera
    assert "tools: Read, Glob, Grep" in cabecera, cabecera
    assert verificar_capa.skills_del_frontmatter(texto) == ["criterios"]
    herramientas = next(l for l in cabecera if l.startswith("tools:"))
    assert not {"Edit", "Write", "Bash", "PowerShell", "NotebookEdit"} & set(re.findall(r"\w+", herramientas.split(":", 1)[1])), herramientas
    descripcion = next(l for l in cabecera if l.startswith("description:"))
    assert re.fullmatch(r'description: "((?:[^"\\]|\\.)*)"', descripcion), descripcion
    assert "{{" not in texto and "}}" not in texto


def test_el_revisor_de_diseno_revisa_hermano_consumidor_errores_y_tamano_con_el_contrato_comun():
    texto = archivos("sql")[capas.REVISOR_DISENO]
    for pedida in ("CENTINELA criterios", "hermano vigente", "consumidor", "definitivo", "commit", "aborta o sigue", "Tamaño relativo",
                   "CRITICAL", "WARNING", "SUGGESTION", "ruta:línea", "Solo lees", "Alcance y límites", "workspace.config.json"):
        assert pedida in texto, pedida


def test_el_revisor_de_diseno_trae_su_version_y_su_huella_y_regenerarlo_no_cambia_nada():
    texto = archivos(*CAPAS)[capas.REVISOR_DISENO]
    cabecera = frontmatter(texto)
    version = plantilla_writer.version(plantilla_writer.leer_plantilla(a().PLANTILLA_REVISOR_DISENO))
    assert isinstance(version, int) and version >= 1
    assert "odd-ws-plantilla: %d" % version in cabecera, cabecera
    assert "odd-ws-hash: %s" % plantilla_writer.huella(texto) in cabecera, cabecera
    assert re.fullmatch(r"[0-9a-f]{64}", plantilla_writer.huella(texto))
    assert a().generar_revisor_diseno(texto) == texto
    assert a().generar_revisor_diseno() == texto
    revisor = archivos("sql")[capas.revisor("sql")]
    assert [l.split(":")[0] for l in frontmatter(revisor) if l.startswith("odd-ws-")] == [l.split(":")[0] for l in cabecera if l.startswith("odd-ws-")]


def test_regenerar_el_revisor_de_diseno_conserva_los_bloques_de_la_instancia():
    base = a().generar_revisor_diseno()
    nombres = re.findall(r"<!-- instancia:([a-z][a-z0-9-]*) -->", base)
    assert "identidad" in nombres and "foco" in nombres, nombres
    propio = re.sub(r"(<!-- instancia:identidad -->\n).*?(<!-- /instancia:identidad -->)",
                    lambda m: m.group(1) + "Soy el revisor de diseño propio.\n" + m.group(2), base, count=1, flags=re.S)
    propio = propio.replace("<!-- instancia:foco -->\n", "<!-- instancia:foco -->\nMira primero los contratos entre capas.\n", 1)
    propio = re.sub(r"(?m)^description:.*$", 'description: "Mía: # propia"', propio, count=1)
    regenerado = a().generar_revisor_diseno(propio)
    assert "Soy el revisor de diseño propio.\n<!-- /instancia:identidad -->" in regenerado
    assert "<!-- instancia:foco -->\nMira primero los contratos entre capas.\n<!-- /instancia:foco -->" in regenerado
    assert 'description: "Mía: # propia"' in regenerado
    assert a().generar_revisor_diseno(regenerado) == regenerado
    assert plantilla_writer.huella(propio) == plantilla_writer.huella(base)
    roto = base.replace("<!-- /instancia:foco -->\n", "", 1)
    try:
        a().generar_revisor_diseno(roto)
    except ValueError:
        pass
    else:
        raise AssertionError("regeneró sobre bloques mal formados")


def test_cambiar_el_revisor_de_diseno_obliga_a_subir_su_version():
    version = plantilla_writer.version(plantilla_writer.leer_plantilla(a().PLANTILLA_REVISOR_DISENO))
    huella = sha(a().generar_revisor_diseno())
    if version not in HUELLAS_DEL_REVISOR_DE_DISENO:
        raise AssertionError("anotá %d: %r en HUELLAS_DEL_REVISOR_DE_DISENO" % (version, huella))
    assert HUELLAS_DEL_REVISOR_DE_DISENO[version] == huella, (
        "lo generado cambió: subí odd-ws-plantilla en plugin/plantillas/revisor-diseno.md y anotá %d: %r en HUELLAS_DEL_REVISOR_DE_DISENO" % (version + 1, huella))


def test_todo_sale_en_lf_sin_bom_con_salto_final_y_sin_marcas_sin_resolver():
    generados = archivos(*CAPAS)
    assert len(generados) == 11, sorted(generados)
    for ruta, texto in generados.items():
        crudo = texto.encode("utf-8")
        assert not crudo.startswith(b"\xef\xbb\xbf") and b"\r" not in crudo, ruta
        assert texto.endswith("\n") and not texto.endswith("\n\n"), ruta
        assert "{{" not in texto and "}}" not in texto, (ruta, re.findall(r"\{\{\w+\}\}", texto))
        assert "﻿" not in texto and "\x00" not in texto, ruta


def test_generar_es_pura_y_determinista_y_no_toca_la_spec():
    spec = spec_de("sql", "web")
    copia = json.loads(json.dumps(spec))
    primero = a().generar(spec, HOY)
    assert len(primero) == 8, primero
    assert a().generar(spec, HOY) == primero
    assert spec == copia


def test_el_doctor_da_ok_sobre_lo_generado():
    modulo = doctor_tests()
    with modulo.Escenario() as e:
        raiz = e.instancia(capas=("sql", "web"))
        volcar(raiz, archivos("sql", "web"))
        resultados = modulo.por_id(modulo.Falso(e.base, cwd=raiz))
        for id in ("writer-sql", "writer-web", "agentes-skills", "agentes-hooks"):
            assert resultados[id].estado == "OK", resultados[id]
        assert "9 skills precargadas" in resultados["agentes-skills"].detalle, resultados["agentes-skills"].detalle


def test_control_positivo_el_doctor_si_marca_lo_que_no_debe_pasar():
    modulo = doctor_tests()
    for ruta, cambio, esperado in (
        (capas.skill("sql"), lambda t: t.replace("user-invocable: false\n", "user-invocable: false\npaths: **/*.x\n", 1), "FALTA"),
        (capas.CRITERIOS_SKILL, lambda t: t.replace("CENTINELA criterios", "CENTINELA otro", 1), "AVISO"),
    ):
        with modulo.Escenario() as e:
            raiz = e.instancia(capas=("sql",))
            generados = dict(a().generar(spec_de("sql"), HOY))
            assert cambio(generados[ruta]) != generados[ruta], ruta
            generados[ruta] = cambio(generados[ruta])
            volcar(raiz, generados)
            assert modulo.por_id(modulo.Falso(e.base, cwd=raiz))["agentes-skills"].estado == esperado, ruta


def test_el_writer_generado_pasa_la_revision_del_doctor_y_el_revisor_conserva_su_huella():
    with Temporal() as t:
        volcar(t.raiz, archivos("sql"))
        assert plantilla_writer.revisar(t.raiz, "sql").codigo == "ok"
        texto = (t.raiz / capas.revisor("sql")).read_text(encoding="utf-8")
        assert plantilla_writer.huella(texto) in texto


def test_el_motor_de_bootstrap_acepta_el_generador():
    bootstrap = importlib.import_module("bootstrap")
    previos = list(bootstrap.GENERADORES)
    try:
        bootstrap.registrar_generador("agentes", a().generar, a().CLAVES)
        spec = spec_de("sql")
        spec["config"]["layers"]["sql"]["extensions"] = [".sql"]
        spec["local"] = {}
        with Temporal() as t:
            plan = bootstrap.planificar(spec, t.raiz)
            rutas = {accion.ruta: accion.modo for accion in plan}
            assert capas.writer("sql") in rutas and capas.CRITERIOS_SKILL in rutas and capas.skill("sql") in rutas
            resultados = bootstrap.aplicar(plan, t.raiz)
            assert all(r.estado == bootstrap.CREADO for r in resultados), resultados
            (t.raiz / capas.skill("sql")).write_text("mío\n", encoding="utf-8")
            otra = bootstrap.aplicar(bootstrap.planificar(spec, t.raiz), t.raiz)
            assert all(r.estado == bootstrap.YA_EXISTIA for r in otra), otra
            assert (t.raiz / capas.skill("sql")).read_text(encoding="utf-8") == "mío\n"
    finally:
        bootstrap.GENERADORES[:] = previos


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
