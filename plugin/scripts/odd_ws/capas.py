import os
import re

MARCA_ABRE = "<!-- no-negociables -->"
MARCA_CIERRA = "<!-- /no-negociables -->"

REGLAS = ".claude/reglas"
MATRIZ = REGLAS + "/matriz.csv"
EVIDENCIA = REGLAS + "/evidencia.md"
SENALES = REGLAS + "/senales.py"
PAQUETES_LOCK = REGLAS + "/paquetes.json"
PAQUETES = REGLAS + "/paquetes"
REGISTRO = ".claude/registro"
CALIBRACION = REGISTRO + "/calibracion.json"
CRITERIOS_SKILL = ".claude/skills/criterios/SKILL.md"
CRITERIOS_REFS = ".claude/skills/criterios/references/"
AGENTES = ".claude/agents"
REVISOR_DISENO = AGENTES + "/revisor-diseno.md"
CODEX = ".codex"
CODEX_AGENTES = CODEX + "/agents"
CODEX_CONFIG = CODEX + "/config.toml"
PI = ".pi"
PI_AGENTES = PI + "/agents"
PRIMER_TOQUE = ".claude/estado/primer-toque"
ESTADO_WRITERS = ".claude/estado/writers"
BITACORA = "bitacora.jsonl"
WRITER_RE = re.compile(r"writer-[a-z0-9][a-z0-9-]*")
CARPETA_VERDAD = "revision"
CARPETA_OCULTA = "oculto"
ESTADO = ".claude/estado"
TICKET_ACTIVO = ESTADO + "/ticket-activo"
FALLAS_DE_HOOKS = ESTADO + "/fallas-de-hooks.jsonl"
FALLAS_VISTAS = ESTADO + "/fallas-de-hooks.vista"
GITIGNORE = ".gitignore"
TICKETS = "tickets"
INDICE = "CLAUDE.md"
TICKET_PLANTILLA_DIR = TICKETS + "/_plantilla"
TICKET_PLANTILLA = TICKET_PLANTILLA_DIR + "/CLAUDE.md"
TICKET_SETTINGS = TICKET_PLANTILLA_DIR + "/.claude/settings.json"


def es_writer(nombre):
    return isinstance(nombre, str) and WRITER_RE.fullmatch(nombre) is not None


def chequeo(capa):
    return "%s/verificar_%s.py" % (REGLAS, capa)


def prueba(capa):
    return "%s/verificar_%s.tests.py" % (REGLAS, capa)


def paquete(nombre):
    return "%s/%s" % (PAQUETES, nombre)


def skill(capa):
    return skill_de("capa-%s" % capa)


def skill_de(nombre):
    return ".claude/skills/%s/SKILL.md" % nombre


def revisor(capa):
    return agente("revisor-%s" % capa)


def writer(capa):
    return agente("writer-%s" % capa)


def agente(nombre):
    return "%s/%s.md" % (AGENTES, nombre)


def agente_codex(nombre):
    return "%s/%s.toml" % (CODEX_AGENTES, nombre)


def agente_pi(nombre):
    return "%s/%s.md" % (PI_AGENTES, nombre)


def partir_bloque(lineas):
    dentro, fuera = [], []
    en_bloque, cerrados, buffer = False, 0, []
    for l in lineas:
        marca = l.strip()
        if not en_bloque and marca == MARCA_ABRE:
            en_bloque, buffer = True, []
        elif en_bloque and marca == MARCA_CIERRA:
            dentro += buffer + [""]
            fuera.append("")
            en_bloque, cerrados = False, cerrados + 1
        elif en_bloque:
            buffer.append(l)
        else:
            fuera.append(l)
    if en_bloque:
        return dentro, fuera, "abierto"
    return dentro, fuera, "ok" if cerrados else "ausente"


PLANTILLA_CAPA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              "plantillas", "capa.md")


def sin_espacios(texto):
    return " ".join(texto.split())


def relleno_de_la_plantilla(capa):
    try:
        with open(PLANTILLA_CAPA, encoding="utf-8-sig") as f:
            lineas = f.read().replace("{{capa}}", capa).splitlines()
    except OSError:
        return None
    dentro, _, estado = partir_bloque(lineas)
    return sin_espacios("\n".join(dentro)) if estado == "ok" else None
