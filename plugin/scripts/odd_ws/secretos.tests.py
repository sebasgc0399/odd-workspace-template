import sys

sys.dont_write_bytecode = True

import importlib
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

ALFANUMERICOS = "aB3dE5fG7hJ9kL2mN4pQ6rS8tU0vW1xY"
MAYUSCULAS = "Z7Q4X2W9R5T8Y3U6"


def m():
    return importlib.import_module("odd_ws.secretos")


def cuerpo(n, alfabeto=ALFANUMERICOS):
    return (alfabeto * (n // len(alfabeto) + 1))[:n]


def falsos():
    return {
        "AWS_ACCESS_KEY_ID": ["AK" + "IA" + cuerpo(16, MAYUSCULAS)],
        "GITHUB_TOKEN": ["gh" + p + "_" + cuerpo(36) for p in "pousr"]
                        + ["github" + "_pat_" + cuerpo(22) + "_" + cuerpo(59)],
        "SLACK_TOKEN": ["xo" + "xb-" + "17653672481-19874698323-" + cuerpo(24),
                        "xo" + "xp-" + "4815162342-4815162342-4815162342-" + cuerpo(32, "0123456789abcdef")],
        "GOOGLE_API_KEY": ["AI" + "za" + "Sy" + cuerpo(29) + "-_x9"],
        "OPENAI_API_KEY": ["sk" + "-" + cuerpo(20) + "T3BlbkFJ" + cuerpo(20),
                           "sk" + "-proj-" + cuerpo(74) + "_" + cuerpo(48) + "-" + cuerpo(30)],
        "ANTHROPIC_API_KEY": ["sk" + "-ant-api03-" + cuerpo(93) + "-" + "AA"],
        "STRIPE_KEY": ["sk" + "_live_" + cuerpo(24), "rk" + "_live_" + cuerpo(99)],
    }


BASE64 = ("MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gunVTLw7onLRnrq0/IzW7yWR7QkrmBL7jTKEn5u"
          "+qKhbwKfBstIs+bMY2Zkp18gnTxKLxoS2tFczGkPLPgizskuemMghRniWaoLcyehkd3qqGElvW/VDL5AaWTg0nLVkjRo9z+40RQ")


def clave_privada(tipo="RSA ", lineas=4, prefijo="", fin="\n"):
    inicio, cierre = "-----BEGIN %sPRIVATE KEY-----" % tipo, "-----END %sPRIVATE KEY-----" % tipo
    cuerpo_ = [BASE64[i * 7:i * 7 + 64] for i in range(lineas)]
    return fin.join(prefijo + linea for linea in [inicio, *cuerpo_, cierre]) + fin


NEGATIVOS = {
    "tailwind": '<div class="dark:bg-gray-800 sm:p-4 md:hover:text-white">',
    "mailto": '<a href="mailto:x@y.com">escríbenos</a>',
    "hash de git": "commit 9412353a1c7e0b2d4f6a8c0e2b4d6f8a0c2e4b6d",
    "sk- con una palabra corta": "pip install sk-learn y el atajo sk-ant y sk-proj",
    "sha256": "sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "uuid": "id 123e4567-e89b-12d3-a456-426614174000",
    "prosa": "Guarda el token en el gestor y nunca pegues la password ni la clave en el chat.",
    "nombres de variables": "OPENAI_API_KEY=${OPENAI_API_KEY} GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}",
    "un bloque de clave sin fin": "-----BEGIN PRIVATE KEY-----\nsolo el encabezado, sin su cierre\n",
    "el regex de un patron": r"AKIA[0-9A-Z]{16} y gh[pousr]_[A-Za-z0-9]{36}",
}


def test_cada_control_positivo_se_tapa_con_su_marcador_y_cuenta_uno():
    for nombre, tokens in falsos().items():
        for token in tokens:
            texto = "antes %s despues\n" % token
            tapado, cuantos = m().tapar(texto)
            assert tapado == "antes <%s> despues\n" % nombre, (nombre, token, tapado)
            assert cuantos == 1, (nombre, token, cuantos)


def test_los_controles_negativos_vuelven_identicos_y_con_cero():
    for nombre, texto in NEGATIVOS.items():
        tapado, cuantos = m().tapar(texto)
        assert tapado == texto and cuantos == 0, (nombre, tapado, cuantos)
    juntos = "\n".join(NEGATIVOS.values())
    assert m().tapar(juntos) == (juntos, 0)


def test_un_texto_sin_secretos_es_el_mismo_objeto_de_texto():
    texto = "linea 1\r\nlínea 2 con tildes\n\tfin"
    tapado, cuantos = m().tapar(texto)
    assert tapado == texto and cuantos == 0
    assert m().tapar("") == ("", 0)


def test_los_secretos_pegados_a_otras_letras_no_cuentan_salvo_que_el_formato_lo_permita():
    aws = falsos()["AWS_ACCESS_KEY_ID"][0]
    for texto in ("X" + aws, aws + "Z", "ghp_" + cuerpo(30), "sk-" + cuerpo(39), "xoxb-tokens-de-ejemplo-sin-numeros",
                  "AIza" + cuerpo(30), "sk_test_" + cuerpo(24), "sk_live_corta"):
        assert m().tapar(texto) == (texto, 0), texto
    assert m().tapar("clave=" + aws + ";") == ("clave=<AWS_ACCESS_KEY_ID>;", 1)
    assert m().tapar('"' + falsos()["GITHUB_TOKEN"][0] + '"') == ('"<GITHUB_TOKEN>"', 1)


def test_anthropic_no_se_confunde_con_openai():
    token = falsos()["ANTHROPIC_API_KEY"][0]
    assert m().tapar("export ANTHROPIC_API_KEY=" + token) == ("export ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY>", 1)


def test_cuenta_cada_secreto_de_un_texto_con_varios():
    todos = [t for tokens in falsos().values() for t in tokens]
    texto = "\n".join("linea %d: %s" % (i, t) for i, t in enumerate(todos)) + "\n" + clave_privada()
    tapado, cuantos = m().tapar(texto)
    assert cuantos == len(todos) + 1, cuantos
    for token in todos:
        assert token not in tapado, token
    assert "PRIVATE KEY-----" in tapado and "MIIE" not in tapado, tapado


def test_tapar_dos_veces_no_cambia_nada_la_segunda():
    texto = "a %s b\n%s" % (falsos()["STRIPE_KEY"][0], clave_privada("EC "))
    una, cuantos = m().tapar(texto)
    assert cuantos == 2
    assert m().tapar(una) == (una, 0)


def test_la_clave_privada_conserva_sus_lineas_y_el_prefijo_de_cada_una():
    for tipo in ("", "RSA ", "EC ", "OPENSSH ", "ENCRYPTED "):
        for prefijo, fin in (("", "\n"), ("+", "\n"), ("+", "\r\n"), ("> ", "\n"), ("    ", "\r\n")):
            texto = "antes" + fin + clave_privada(tipo, 4, prefijo, fin) + "despues" + fin
            tapado, cuantos = m().tapar(texto)
            assert cuantos == 1, (tipo, prefijo, cuantos)
            lineas, originales = tapado.split(fin), texto.split(fin)
            assert len(lineas) == len(originales), (tipo, prefijo, tapado)
            assert lineas[1] == prefijo + "-----BEGIN %sPRIVATE KEY-----" % tipo, lineas[1]
            assert lineas[2:6] == [prefijo + "<PRIVATE_KEY>"] * 4, (tipo, prefijo, lineas)
            assert lineas[6] == prefijo + "-----END %sPRIVATE KEY-----" % tipo, lineas[6]
            assert "\r\n" not in tapado.replace(fin, "") and lineas[0] == "antes" and lineas[7] == "despues", tapado


def test_una_clave_privada_en_una_sola_linea_se_tapa_entre_sus_encabezados():
    texto = 'KEY = "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\\n-----END PRIVATE KEY-----\\n"'
    assert m().tapar(texto) == ('KEY = "-----BEGIN PRIVATE KEY-----<PRIVATE_KEY>-----END PRIVATE KEY-----\\n"', 1)
    pgp = "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nlQOYBF\n-----END PGP PRIVATE KEY BLOCK-----\n"
    assert m().tapar(pgp) == ("-----BEGIN PGP PRIVATE KEY BLOCK-----\n\n<PRIVATE_KEY>\n-----END PGP PRIVATE KEY BLOCK-----\n", 1)


def test_tapar_nunca_lanza_y_ante_un_error_devuelve_el_texto_igual():
    for raro in (None, b"AKIA" + MAYUSCULAS.encode(), 12, ["x"]):
        assert m().tapar(raro) == (raro, 0), raro
    modulo = m()
    originales = modulo.PATRONES
    texto = "antes %s despues" % falsos()["AWS_ACCESS_KEY_ID"][0]
    try:
        modulo.PATRONES = (("ROTO", object()),)
        assert modulo.tapar(texto) == (texto, 0)
        tapado, cuantos, error = modulo.intentar_tapar(texto)
        assert (tapado, cuantos) == (texto, 0) and isinstance(error, Exception), (tapado, cuantos, error)
        assert modulo.tapar_valores({"a": texto}) == ({"a": texto}, 0)
    finally:
        modulo.PATRONES = originales
    assert modulo.intentar_tapar(texto) == ("antes <AWS_ACCESS_KEY_ID> despues", 1, None)


def test_tapar_valores_recorre_dicts_y_listas_sin_tocar_las_claves_ni_lo_que_no_es_texto():
    token = falsos()["GITHUB_TOKEN"][1]
    datos = {"agente": "abc", "meta": {"model": "opus", "n": 3}, token: "la clave queda",
             "lecturas": [{"tool": "Grep", "input": {"pattern": token, "head_limit": 5, "multiline": False}}, None, 1.5],
             "comandos": ({"comando": "echo " + token, "exit": 0},)}
    copia = json.loads(json.dumps(datos))
    tapados, cuantos = m().tapar_valores(datos)
    assert cuantos == 2, cuantos
    assert tapados[token] == "la clave queda" and tapados["meta"] == {"model": "opus", "n": 3}
    assert tapados["lecturas"] == [{"tool": "Grep", "input": {"pattern": "<GITHUB_TOKEN>", "head_limit": 5, "multiline": False}},
                                   None, 1.5], tapados["lecturas"]
    assert tapados["comandos"] == ({"comando": "echo <GITHUB_TOKEN>", "exit": 0},), tapados["comandos"]
    assert json.loads(json.dumps(datos)) == copia, "no muta lo que recibe"
    json.loads(json.dumps(tapados, ensure_ascii=False))
    assert m().tapar_valores(copia["meta"]) == (copia["meta"], 0)


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
