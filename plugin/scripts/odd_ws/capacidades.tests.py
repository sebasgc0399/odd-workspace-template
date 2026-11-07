import ast
import importlib
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SCRIPTS = AQUI.parent
sys.path.insert(0, str(SCRIPTS))
SILENCIO = (0, "", b"")
HOOKS = ("verificar_capa", "writer_guard", "writer_stop", "guard_comandos")
DECISIONES_DE_HOOK = ("Bloquear", "Preguntar", "Contexto", "Seguir")


def cap():
    return importlib.import_module("odd_ws.capacidades")


def ev():
    return importlib.import_module("odd_ws.eventos")


def adaptadores():
    registro = importlib.import_module("odd_ws.hosts")
    return [(nombre, importlib.import_module("odd_ws.hosts." + nombre)) for nombre in registro.ADAPTADORES]


def hooks():
    return [(nombre, importlib.import_module(nombre)) for nombre in HOOKS]


def eventos_por_punto():
    C, E = cap(), ev()
    return {
        C.PRE: E.Herramienta(fase="pre", tipo="shell", herramienta="Bash", comando="ls"),
        C.POST: E.Herramienta(fase="post", tipo="edicion", herramienta="Edit", rutas=("/w/a.txt",)),
        C.INICIO: E.InicioSesion(origen="startup"),
        C.FIN_SUBAGENTE: E.FinSubagente(agente="writer-x"),
    }


def decisiones():
    E = ev()
    return (E.Bloquear("x"), E.Preguntar("x"), E.Contexto("x"), E.Seguir("x"))


def test_hay_al_menos_un_adaptador_y_es_el_de_claude_code():
    assert [nombre for nombre, _ in adaptadores()][:1] == ["claude_code"]


def test_los_puntos_de_evento_son_los_cuatro_del_modelo():
    C = cap()
    assert C.PUNTOS_DE_EVENTO == (C.PRE, C.POST, C.INICIO, C.FIN_SUBAGENTE)
    assert set(eventos_por_punto()) == set(C.PUNTOS_DE_EVENTO)


def test_cada_adaptador_responde_justo_lo_que_declara_expresable():
    C, E = cap(), ev()
    for nombre, adaptador in adaptadores():
        assert set(adaptador.EXPRESABLES) <= set(C.PUNTOS_DE_EVENTO), nombre
        for punto, evento in eventos_por_punto().items():
            assert adaptador.responder(evento, E.Permitir()) == SILENCIO, (nombre, punto)
            for decision in decisiones():
                expresable = type(decision) in adaptador.EXPRESABLES.get(punto, ())
                salida = adaptador.responder(evento, decision)
                assert (salida != SILENCIO) == expresable, (
                    "%s: %s en %s %s, pero EXPRESABLES dice %s"
                    % (nombre, type(decision).__name__, punto, "responde" if salida != SILENCIO else "calla", expresable))


def test_cada_hook_emite_solo_lo_que_cada_adaptador_puede_expresar():
    for hook, modulo in hooks():
        for nombre, adaptador in adaptadores():
            for punto, tipos in modulo.EMITE.items():
                for tipo in tipos:
                    assert tipo in adaptador.EXPRESABLES.get(punto, ()), (
                        "%s emite %s en %s y el host %s no lo puede expresar: hay que degradarlo en su adaptador, "
                        "que falle cerrado, y declararlo en su MANIFIESTO" % (hook, tipo.__name__, punto, nombre))


def test_emite_usa_puntos_y_decisiones_del_modelo():
    C, E = cap(), ev()
    validas = {getattr(E, nombre) for nombre in DECISIONES_DE_HOOK}
    for hook, modulo in hooks():
        assert modulo.EMITE, hook
        assert set(modulo.EMITE) <= set(C.PUNTOS_DE_EVENTO), hook
        for tipos in modulo.EMITE.values():
            assert tipos and set(tipos) <= validas, hook


def test_emite_nombra_cada_tipo_de_decision_que_el_hook_construye():
    for hook, modulo in hooks():
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
        construidas = {nodo.func.id for nodo in ast.walk(arbol)
                       if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id in DECISIONES_DE_HOOK}
        declaradas = {tipo.__name__ for tipos in modulo.EMITE.values() for tipo in tipos}
        assert construidas == declaradas, "%s construye %s y EMITE declara %s" % (hook, sorted(construidas), sorted(declaradas))


def test_el_manifiesto_de_cada_adaptador_declara_los_diez_puntos():
    C = cap()
    assert list(C.CAPACIDADES) == ["P%d" % n for n in range(1, 11)]
    for nombre, adaptador in adaptadores():
        assert list(adaptador.MANIFIESTO) == list(C.CAPACIDADES), nombre
        for clave, (estado, nota) in adaptador.MANIFIESTO.items():
            assert estado in C.ESTADOS, (nombre, clave, estado)
            assert isinstance(nota, str), (nombre, clave)
            if estado != C.SOPORTADO:
                assert nota.strip(), "%s: %s es %s y no escribe su fallback" % (nombre, clave, estado)


def test_el_manifiesto_coincide_con_lo_que_el_adaptador_expresa():
    C = cap()
    assert set(C.REQUISITOS) <= set(C.CAPACIDADES)
    for nombre, adaptador in adaptadores():
        for clave, requisitos in C.REQUISITOS.items():
            cumple = all(tipo in adaptador.EXPRESABLES.get(punto, ()) for punto, tipo in requisitos)
            estado = adaptador.MANIFIESTO[clave][0]
            assert (estado == C.SOPORTADO) == cumple, (
                "%s: %s está declarado %s, pero el adaptador %s expresa lo que pide" % (nombre, clave, estado, "sí" if cumple else "no"))


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
