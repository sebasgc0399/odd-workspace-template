import dataclasses
import importlib
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))


def m():
    return importlib.import_module("odd_ws.eventos")


def herramienta(**sobre):
    campos = {"fase": "pre", "tipo": "shell", "herramienta": "x", "rutas": (), "comando": "ls", "dialecto": "posix",
              "agente": None, "id_agente": None, "sesion": "s1", "cwd": "/w"}
    campos.update(sobre)
    return m().Herramienta(**campos)


def test_vocabularios_cerrados():
    assert m().FASES == ("pre", "post")
    assert m().TIPOS == ("edicion", "lectura", "shell", "otra")
    assert m().DIALECTOS == ("posix", "powershell")
    assert (m().POSIX, m().POWERSHELL) == ("posix", "powershell")


def test_herramienta_lleva_sus_campos_con_nombre():
    e = herramienta(rutas=("/w/a.txt", "/w/b.txt"), agente="writer-x", id_agente="a1")
    assert [c.name for c in dataclasses.fields(e)] == ["fase", "tipo", "herramienta", "rutas", "comando", "dialecto",
                                                       "agente", "id_agente", "sesion", "cwd"]
    assert e.rutas == ("/w/a.txt", "/w/b.txt") and e.agente == "writer-x" and e.id_agente == "a1"
    minima = m().Herramienta(fase="post", tipo="otra")
    assert (minima.herramienta, minima.rutas, minima.comando, minima.dialecto, minima.agente, minima.id_agente,
            minima.sesion, minima.cwd) == (None, (), None, None, None, None, None, None)


def test_herramienta_rechaza_lo_que_no_esta_en_el_vocabulario():
    for sobre in ({"fase": "PreToolUse"}, {"fase": None}, {"tipo": "Edit"}, {"tipo": None}, {"dialecto": "Bash"},
                  {"dialecto": "PowerShell"}, {"rutas": ["/w/a.txt"]}, {"rutas": "/w/a.txt"}, {"rutas": None}):
        try:
            herramienta(**sobre)
        except ValueError:
            continue
        raise AssertionError("acepto %r" % (sobre,))
    for dialecto in (None, "posix", "powershell"):
        assert herramienta(dialecto=dialecto).dialecto == dialecto


def test_inicio_y_fin_llevan_sus_campos():
    i = m().InicioSesion(origen="compact", sesion="s1", cwd="/w")
    assert [c.name for c in dataclasses.fields(i)] == ["origen", "sesion", "cwd"]
    assert (i.origen, i.sesion, i.cwd) == ("compact", "s1", "/w")
    f = m().FinSubagente(agente="writer-x", id_agente="a1", sesion="s1", cwd="/w", transcript="/t.jsonl",
                         ultimo_mensaje="listo", ya_reintentado=True)
    assert [c.name for c in dataclasses.fields(f)] == ["agente", "id_agente", "sesion", "cwd", "transcript",
                                                       "ultimo_mensaje", "ya_reintentado"]
    assert f.ya_reintentado is True and f.transcript == "/t.jsonl"
    vacio = m().FinSubagente()
    assert (vacio.agente, vacio.transcript, vacio.ultimo_mensaje, vacio.ya_reintentado) == (None, None, None, False)


def test_las_decisiones_llevan_su_motivo_o_su_texto():
    assert m().Permitir() == m().Permitir()
    assert m().Bloquear("no").motivo == "no"
    assert m().Preguntar("¿sí?").motivo == "¿sí?"
    assert m().Contexto("dato").texto == "dato"
    assert m().Seguir("falta").motivo == "falta"
    assert m().Bloquear("x") != m().Preguntar("x") and m().Seguir("x") != m().Bloquear("x")


def test_todo_es_inmutable():
    casos = [(herramienta(), "fase"), (m().InicioSesion(), "origen"), (m().FinSubagente(), "agente"),
             (m().Bloquear("x"), "motivo"), (m().Preguntar("x"), "motivo"), (m().Contexto("x"), "texto"),
             (m().Seguir("x"), "motivo")]
    for objeto, campo in casos:
        try:
            setattr(objeto, campo, "otro")
        except dataclasses.FrozenInstanceError:
            continue
        raise AssertionError("%s se dejo cambiar" % type(objeto).__name__)


def test_el_nucleo_no_habla_el_idioma_de_ningun_host():
    texto = (AQUI / "eventos.py").read_text(encoding="utf-8")
    for palabra in ("hook_event_name", "tool_name", "tool_input", "PreToolUse", "PostToolUse", "SessionStart",
                    "SubagentStop", "Bash", "PowerShell", "Edit", "Write", "Read", "agent_type", "Claude"):
        assert palabra not in texto, palabra


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
