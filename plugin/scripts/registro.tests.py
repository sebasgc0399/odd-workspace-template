import re
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent

VOSEO = frozenset("""
abrís aplicás autenticás borrás buscás cambiás conocés consultás corrés creés decidís decís dejás desarmás
elegís empezás encontrás entendés escribís esperás hacés juzgás leés listás llegás mirás mostrás necesitás
pasás pedís pensás podés ponés preferís preguntás querés recordás registrás repetís sabés salís seguís sos
tenés usás venís volvés vos

aceptá activá actualizá agregá ajustá andá anotá anunciá apagá aplicá apuntá armá arreglá avisá borrá buscá
calculá cambiá cerrá chequeá citá commiteá compará completá comprobá confiá configurá confirmá contá copiá
creá dejá desactivá desarmá descartá detectá editá empezá entrá entregá esperá explicá filtrá fijá frená
generá guardá ignorá importá instalá integrá intentá juzgá listá llamá mandá mapeá marcá mirá mostrá
nombrá pará pasá preguntá presentá priorizá probá quitá rechequeá recomendá recordá reiniciá reinstalá
relanzá renombrá reportá revisá sacá sellá sumá terminá tomá usá verificá

corré devolvé hacé leé ofrecé poné prendé promové proponé respondé recorré tené traé volvé

abrí corregí decí decidí elegí escribí omití pedí preferí reescribí repetí salí seguí subí sugerí vení

acordate actualizalo abrila abrilo anotalo apagala arreglalo asegurate avisale avisalo borrala borralo
buscala buscalas buscalo cambiala cambialo cerrala cerralo commitealo commitealos comprobalo confirmalo
correla correlo corregilo decile decilo decime dejala dejalo desarmalo descartalos escribila escribilo
fijalo fijate generalo guardala guardalo hacelo instalalo listalas listalos llamalo mapealos marcalo
mostrala mostrale mostralo mostralos olvidate omitilo pasale pasalo pedile pedilo ponela ponelo
preguntale promovelos rechequealo rechequealos recordale recordalo reescribilo reimportalo reinstalalo
reportalo revisala revisalo sacala sacale sacalo sellala sumala sumalas sumalo sumalos leela leelo leelos usala
usalo usalos

decíselo decíselos dejáselo mostráselo pasáselo pasáselos preguntáselo repetíselo corréla corrélo corrélos

abri cerra conta corregi deci decidi devolve elegi escribi mostra omiti pedi proba promove recorda reescribi repeti
sali segui subi sugeri tene veni volve decis podes queres tenes
""".split())

EXCEPCIONES = frozenset("""
esté estés caché cachés arnés revés así sé busqué encontré cambié aísla leí conté porqué
está estás será acá allá aquí ahí allí más demás además qué también después detrás atrás través inglés país sí café
""".split())

PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
ESCAPE = re.compile(r"\\[nrt]")
AGUDA_CON_TILDE = re.compile(r"[áéí]s?$")
CON_TILDE = re.compile(r"[áéíóú]")
CLITICOS = ("los", "las", "lo", "la", "le", "me", "nos")
IMPERATIVOS = frozenset(forma for forma in VOSEO if forma[-1] in "áéí")
TILDE = str.maketrans("aei", "áéí")


def _por_su_terminacion(forma):
    if len(forma) > 2 and AGUDA_CON_TILDE.search(forma):
        return True
    if CON_TILDE.search(forma):
        return False
    for clitico in CLITICOS:
        base = forma[:-len(clitico)]
        if forma.endswith(clitico) and base and base[-1] in "aei":
            return base[:-1] + base[-1].translate(TILDE) in IMPERATIVOS
    return False


def formas_de_voseo(texto):
    hallados = []
    for numero, linea in enumerate(unicodedata.normalize("NFC", texto).splitlines(), 1):
        for palabra in PALABRA.findall(ESCAPE.sub(" ", linea)):
            forma = palabra.lower()
            if forma not in EXCEPCIONES and (forma in VOSEO or _por_su_terminacion(forma)):
                hallados.append((numero, palabra))
    return hallados


def _es_test(ruta):
    return ruta.name.endswith(".tests.py") or ruta.name.endswith(".test.ts")


def _archivos(carpeta, patron):
    return [r for r in carpeta.glob(patron) if r.is_file() and "__pycache__" not in r.parts and not _es_test(r)]


def archivos_del_producto(raiz=RAIZ):
    plugin = raiz / "plugin"
    publicadas = plugin / "plantillas" / "historial"
    plantillas = [r for r in _archivos(plugin / "plantillas", "**/*") if publicadas not in r.parents]
    archivos = (_archivos(plugin / "skills", "**/*") + _archivos(plugin / "scripts", "**/*.py")
                + _archivos(plugin / "shim", "**/*.ts") + plantillas
                + _archivos(raiz / "Doc", "*.md") + [raiz / "README.md", raiz / "SECURITY.md"])
    return sorted(set(archivos))


def hallazgos(raiz=RAIZ):
    salida = []
    for ruta in archivos_del_producto(raiz):
        for numero, forma in formas_de_voseo(ruta.read_text(encoding="utf-8")):
            salida.append(f"{ruta.relative_to(raiz).as_posix()}:{numero}: «{forma}»")
    return salida


def test_detecta_el_voseo_sembrado():
    texto = ("Corré el doctor y mostrá lo que dice.\n"
             "Si querés, decile que lo revise; commitealo vos.\n"
             "print(\"\\nPreguntáselo antes\")\n")
    assert formas_de_voseo(texto) == [(1, "Corré"), (1, "mostrá"), (2, "querés"), (2, "decile"), (2, "commitealo"),
                                      (2, "vos"), (3, "Preguntáselo")], formas_de_voseo(texto)


def test_no_da_falsos_positivos_con_las_excepciones_ni_con_el_tuteo():
    texto = ("Que esté listo aunque no estés; el caché y los cachés, el arnés, al revés, así lo sé.\n"
             "Busqué, encontré y cambié la regla; aísla el repo. La leí del disco y conté en la base, sin porqué.\n"
             "Déjalo, Avísalo y Pídele el sí. Corre el doctor, muestra lo que dice, si quieres dile que lo revise.\n"
             "Si no sabes cuál es, pregunta; si tienes dudas, sigue y vuelve después.\n"
             "Más allá del tomate, la escala y el intervalo.\n")
    assert formas_de_voseo(texto) == [], formas_de_voseo(texto)


def test_detecta_por_su_terminacion_el_voseo_que_no_esta_en_la_lista():
    texto = ("Si agregás una capa, llevá el cambio y tomalo de ahí.\n"
             "Copialo cuando terminés, elegilo y llamame.\n"
             "Ejecutá el doctor y cargá la config.\n")
    assert formas_de_voseo(texto) == [(1, "agregás"), (1, "llevá"), (1, "tomalo"), (2, "Copialo"), (2, "terminés"), (2, "elegilo"),
                                      (2, "llamame"), (3, "Ejecutá"), (3, "cargá")], formas_de_voseo(texto)


def test_la_terminacion_respeta_las_excepciones_y_no_confunde_sustantivos_ni_el_tuteo():
    texto = ("Ya está: será así, acá y allá, aquí, ahí y allí; más, qué, también, después, además, a través y en inglés.\n"
             "El país, el sí, que esté, el caché, el arnés, al revés, lo sé: busqué, encontré y cambié la escala.\n"
             "Los demás, detrás y atrás; si estás, el café, la leí y la conté. ¿Por qué? Sin porqué.\n"
             "El modelo, el intervalo, el estilo, la centinela; instala, imprime, compila y revela. Tómalo, cópialo, elígelo, "
             "llámame y dale.\n"
             "l[ií]mites, el tomate y los criterios generales.\n")
    assert formas_de_voseo(texto) == [], formas_de_voseo(texto)


def test_las_excepciones_no_estan_en_la_lista():
    assert not VOSEO & EXCEPCIONES, sorted(VOSEO & EXCEPCIONES)


def test_el_barrido_alcanza_el_texto_del_producto_y_no_los_tests():
    relativas = {r.relative_to(RAIZ).as_posix() for r in archivos_del_producto()}
    for esperada in ("plugin/skills/abrir/SKILL.md", "plugin/skills/revisar/references/prompt.md", "plugin/scripts/doctor.py",
                     "plugin/scripts/odd_ws/hosts/pi.py", "plugin/shim/pi.ts", "plugin/plantillas/CLAUDE.md",
                     "plugin/plantillas/pre-commit", "Doc/diseno.md", "README.md", "SECURITY.md"):
        assert esperada in relativas, esperada
    assert not [r for r in relativas if r.endswith(".tests.py") or r.endswith(".test.ts")], relativas


def test_el_barrido_no_alcanza_el_historial_de_las_plantillas_porque_son_textos_publicados():
    raiz = Path(tempfile.mkdtemp(prefix="registro-"))
    try:
        for relativa in ("plugin/plantillas/CLAUDE.md", "plugin/plantillas/historial/" + "a" * 64):
            (raiz / relativa).parent.mkdir(parents=True, exist_ok=True)
            (raiz / relativa).write_text("Corré el doctor.\n", encoding="utf-8")
        relativas = {r.relative_to(raiz).as_posix() for r in archivos_del_producto(raiz)}
        assert "plugin/plantillas/CLAUDE.md" in relativas, "control positivo"
        assert not [r for r in relativas if r.startswith("plugin/plantillas/historial/")], relativas
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def test_el_texto_del_producto_esta_en_tuteo():
    encontrados = hallazgos()
    assert not encontrados, f"{len(encontrados)} formas de voseo (pásalas a tuteo):\n" + "\n".join(encontrados)


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
