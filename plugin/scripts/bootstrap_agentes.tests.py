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
import tomllib
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import plantilla_writer  # noqa: E402
import verificar_capa  # noqa: E402
from odd_ws import capas  # noqa: E402

HOOKS_CODEX = AQUI.parent / "hooks" / "hooks.codex.json"
GOLDEN_DEL_REVISOR = {
    "sql": "069e1b2fd987dd14473bd1025f6d294e829d4f3bdf8d720455bc999e2d379319",
    "web": "8887ea14bcbaf7a2dec5be9f694fe32d0ba9f21be4d7ba69fa60b339d9033ba7",
    "movil": "679c52af770cc47fd770ee5bce7b80f1a1613c7ac58974f44ffd4cb972e01de0",
}
GOLDEN_DEL_REVISOR_DE_DISENO = "3fbcd9c42c77035b069dd112c707748c7c3ab43792afc7f14e7353d49de3aeac"
FRASES_DE_CLAUDE_CODE = ("Edit o Write", "con Read", "Read, Glob o Grep", "Tus herramientas son Read", "transcript",
                         "Tu contexto trae precargada", "el Glob o el Grep", "ya están en tu contexto", "por Bash",
                         ". Bash te sirve")
HOY = datetime.date(2026, 10, 30)
CAPAS = ("sql", "web", "movil")
PROHIBIDAS = re.compile(r"(?:paths|disable-model-invocation|hooks|model)\s*:")
HUELLAS_DEL_REVISOR = {1: "ab73f19f2dae734c3fae2bb0d1d5a1904c89cfed513d9f7344819ed120c9e0dc"}
HUELLAS_DEL_REVISOR_DE_DISENO = {1: "3fbcd9c42c77035b069dd112c707748c7c3ab43792afc7f14e7353d49de3aeac"}
GOLDEN_DEL_WRITER = {
    "sql": "918331c4d350d9d9b8c24e301affe9afa3421b0ed1f39b77dcb9c675c6c1cef0",
    "web": "fa3d48f5304aa4691a8083ac42c6d243ff05b1e11479566ead8daa7f2bb5e3f7",
    "movil": "42d7e5e214e6bc77ce0c1a6c96dac2041d65d641894ac9c37c41cfa337f688c5",
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


def codex():
    return importlib.import_module("odd_ws.hosts.codex")


def con_hosts(hosts, *nombres):
    spec = spec_de(*nombres)
    spec["config"]["hosts"] = hosts
    return spec


def agentes_de(nombres):
    return [n for capa in nombres for n in ("writer-%s" % capa, "revisor-%s" % capa)] + ["revisor-diseno"]


def contenidos(acciones):
    return {accion[0]: accion[1] for accion in acciones}


def tomls(*nombres, hosts=("codex",)):
    generados = contenidos(a().generar(con_hosts(list(hosts), *nombres), HOY))
    return generados, {nombre: generados[capas.agente_codex(nombre)] for nombre in agentes_de(nombres)}


def instrucciones(texto):
    return tomllib.loads(texto)["developer_instructions"]


def test_sin_hosts_y_con_claude_code_sale_byte_a_byte_lo_de_antes():
    sin = a().generar(spec_de(*CAPAS), HOY)
    assert a().generar(con_hosts(["claude-code"], *CAPAS), HOY) == sin
    assert not [ruta for ruta, _ in sin if ruta.startswith(capas.CODEX + "/") or ruta.endswith(".toml")], sin
    generados = dict(sin)
    for capa in CAPAS:
        assert sha(generados[capas.writer(capa)]) == GOLDEN_DEL_WRITER[capa], capa
        assert sha(generados[capas.revisor(capa)]) == GOLDEN_DEL_REVISOR[capa], capa
    assert sha(generados[capas.REVISOR_DISENO]) == GOLDEN_DEL_REVISOR_DE_DISENO


def test_con_codex_salen_el_toml_de_cada_agente_y_su_config_detras_de_lo_de_siempre():
    sin = a().generar(spec_de(*CAPAS), HOY)
    for hosts in (["codex"], ["claude-code", "codex"], ["codex", "claude-code"]):
        con = a().generar(con_hosts(hosts, *CAPAS), HOY)
        assert con[:len(sin)] == sin, hosts
        esperadas = [capas.agente_codex(nombre) for nombre in agentes_de(CAPAS)] + [capas.CODEX_CONFIG]
        assert [accion[0] for accion in con[len(sin):]] == esperadas, (hosts, con[len(sin):])


def test_cada_toml_declara_que_deriva_del_md_de_su_agente_y_la_config_de_codex_no():
    bootstrap = importlib.import_module("bootstrap")
    extra = a().generar(con_hosts(["codex"], *CAPAS), HOY)[len(a().generar(spec_de(*CAPAS), HOY)):]
    for accion in extra[:-1]:
        assert isinstance(accion, bootstrap.AccionDerivada), accion[0]
        assert accion.fuente == capas.agente(accion.ruta.rsplit("/", 1)[1][:-len(".toml")]), (accion.ruta, accion.fuente)
        assert accion.arreglo == codex().ID_AGENTES == "codex-agentes", (accion.ruta, accion.arreglo)
    assert extra[-1] == (capas.CODEX_CONFIG, codex().CONFIG_DEL_PROYECTO) and not isinstance(extra[-1], bootstrap.AccionDerivada)


def test_sin_codex_declarado_no_sale_nada_de_codex_ni_un_agents_md():
    for spec in (spec_de("sql"), con_hosts(["claude-code"], "sql")):
        rutas = [accion[0] for accion in a().generar(spec, HOY)]
        assert not [r for r in rutas if r.startswith(capas.CODEX) or r.endswith(".toml") or r.upper().endswith("AGENTS.MD")], rutas
    rutas = [accion[0] for accion in a().generar(con_hosts(["codex"], "sql"), HOY)]
    assert not [r for r in rutas if r.upper().endswith("AGENTS.MD")], rutas


def test_el_toml_es_valido_y_solo_trae_name_description_y_developer_instructions():
    generados, por_agente = tomls(*CAPAS)
    for nombre, texto in por_agente.items():
        datos = tomllib.loads(texto)
        assert set(datos) == {"name", "description", "developer_instructions"}, (nombre, set(datos))
        assert all(isinstance(valor, str) and valor.strip() for valor in datos.values()), nombre
        md = plantilla_writer.agente(generados[capas.agente(nombre)])
        assert datos["name"] == nombre == md.nombre and datos["description"] == md.descripcion, nombre
        for linea in texto.split("\n"):
            assert not re.match(r"\s*(sandbox_mode|shell_tool|model)\s*=", linea), (nombre, linea)
        assert texto.endswith("\n") and "\r" not in texto and not texto.startswith("\ufeff"), nombre


def test_los_writers_de_codex_cumplen_el_matcher_de_su_compuerta():
    datos = json.loads(HOOKS_CODEX.read_text(encoding="utf-8"))
    matcher = next(grupo["matcher"] for grupo in datos["hooks"]["SubagentStop"])
    _, por_agente = tomls(*CAPAS)
    for capa in CAPAS:
        assert re.search(matcher, tomllib.loads(por_agente["writer-%s" % capa])["name"]), (capa, matcher)
    for nombre in ("revisor-sql", "revisor-diseno"):
        assert not re.search(matcher, tomllib.loads(por_agente[nombre])["name"]), nombre


def test_el_toml_lleva_su_version_y_su_huella_en_un_comentario_y_no_como_clave():
    _, por_agente = tomls("sql")
    revisor, diseno = (plantilla_writer.version(plantilla_writer.leer_plantilla(ruta))
                       for ruta in (a().PLANTILLA_REVISOR, a().PLANTILLA_REVISOR_DISENO))
    versiones = {"writer-sql": plantilla_writer.version(), "revisor-sql": revisor, "revisor-diseno": diseno}
    assert set(por_agente) == set(versiones), sorted(por_agente)
    for nombre, texto in por_agente.items():
        cabecera = [linea for linea in texto.split("\n") if linea.startswith("#")]
        assert "# odd-ws-plantilla: %d" % versiones[nombre] in cabecera, (nombre, cabecera)
        huella = re.fullmatch(r"# odd-ws-hash: ([0-9a-f]{64})", next(l for l in cabecera if l.startswith("# odd-ws-hash:")))
        assert huella and huella.group(1) == codex().huella(texto), (nombre, cabecera)
        assert not [clave for clave in tomllib.loads(texto) if "odd" in clave], nombre
        assert codex().huella(texto.replace(huella.group(1), "0" * 64)) == huella.group(1), nombre
        assert codex().huella(texto.replace("Arranque", "Arranco", 1)) != huella.group(1), nombre


def test_las_instrucciones_de_codex_traen_las_herramientas_y_las_skills_del_frontmatter():
    _, por_agente = tomls("sql")
    writer, revisor, diseno = (instrucciones(por_agente[n]) for n in ("writer-sql", "revisor-sql", "revisor-diseno"))
    assert "Read, Glob, Grep, Edit, Write, Bash" in writer
    for texto in (writer, revisor):
        assert capas.skill_de("criterios") in texto and capas.skill("sql") in texto
    assert "Read, Glob, Grep." in revisor and "Read, Glob, Grep." in diseno
    assert capas.skill_de("criterios") in diseno and "capa-" not in diseno


def test_las_instrucciones_de_codex_describen_su_realidad_y_no_la_de_claude_code():
    _, por_agente = tomls(*CAPAS)
    for nombre, texto in por_agente.items():
        cuerpo = instrucciones(texto)
        for frase in FRASES_DE_CLAUDE_CODE:
            assert frase not in cuerpo, (nombre, frase)
        for marca in ("{{", "<!-- instancia:", "<!-- /instancia:", "Lo genera odd-ws desde su plantilla"):
            assert marca not in cuerpo, (nombre, marca)
        for frase in ("herramienta de shell (en Windows corre PowerShell)", "apply_patch", "no viene", "precargada"):
            assert frase in cuerpo, (nombre, frase)
        sin_cabecera = cuerpo.split("**Arranque, antes que nada.**", 1)[1]
        assert "Bash" not in sin_cabecera, (nombre, [l for l in sin_cabecera.split("\n") if "Bash" in l])
    writer = instrucciones(por_agente["writer-sql"])
    assert "de la bitácora" in writer and "## Resultado" in writer


def test_la_config_de_codex_es_el_fallback_a_claude_md():
    generados, _ = tomls("sql")
    assert generados[capas.CODEX_CONFIG] == 'project_doc_fallback_filenames = ["CLAUDE.md"]\n'
    assert tomllib.loads(generados[capas.CODEX_CONFIG]) == {"project_doc_fallback_filenames": ["CLAUDE.md"]}


def test_el_toml_deriva_del_md_con_los_bloques_y_la_description_de_la_instancia():
    rara = "Mía: ''' y \"\"\" con C:\\x\\y, ñ y # no es comentario"
    propia = "Identidad '''propia''' con \"\"\"comillas\"\"\", una \\ barra al final\\\n\tcon tab y \x7f.\n"
    claude = plantilla_writer.generar("sql")
    propio = re.sub(r"(?m)^description:.*$", lambda _m: "description: " + json.dumps(rara, ensure_ascii=False), claude, count=1)
    propio = re.sub(r"(<!-- instancia:identidad -->\n).*?(<!-- /instancia:identidad -->)", lambda m: m.group(1) + propia + m.group(2),
                    propio, count=1, flags=re.S)
    archivos = contenidos(codex().archivos([plantilla_writer.agente(plantilla_writer.generar("sql", propio, host="codex"))]))
    datos = tomllib.loads(archivos[capas.agente_codex("writer-sql")])
    assert datos["description"] == rara, datos["description"]
    assert propia.rstrip("\n") in datos["developer_instructions"], datos["developer_instructions"]


def test_armar_da_lo_mismo_que_el_generador_de_cada_agente_y_los_nombres_salen_en_el_orden_del_bootstrap():
    assert a().nombres_de_agentes(CAPAS) == agentes_de(CAPAS)
    assert a().nombres_de_agentes(("sql", "C_Sharp", 3)) == ["writer-sql", "revisor-sql", "revisor-diseno"]
    assert a().nombres_de_agentes(()) == [] and a().nombres_de_agentes(("C_Sharp",)) == []
    propio = re.sub(r"(?m)^description:.*$", 'description: "Mía"', plantilla_writer.generar("sql"), count=1)
    for host in ("claude-code", "codex"):
        assert a().armar("writer-sql", propio, host) == plantilla_writer.generar("sql", propio, host=host)
        assert a().armar("revisor-web", None, host) == a().generar_revisor("web", host=host)
        assert a().armar("revisor-diseno", None, host) == a().generar_revisor_diseno(host=host)
    for malo in ("otro", "writer-", "revisor-C_Sharp", None):
        try:
            a().armar(malo)
        except ValueError:
            continue
        raise AssertionError("armó %r" % (malo,))


def test_generar_con_codex_es_pura_y_determinista():
    spec = con_hosts(["claude-code", "codex"], "sql", "web")
    copia = json.loads(json.dumps(spec))
    primero = a().generar(spec, HOY)
    assert a().generar(spec, HOY) == primero and spec == copia
    assert len(primero) == 8 + 5 + 1, [accion[0] for accion in primero]


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
