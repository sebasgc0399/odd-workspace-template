MARCA_ABRE = "<!-- no-negociables -->"
MARCA_CIERRA = "<!-- /no-negociables -->"

REGLAS = ".claude/reglas"
MATRIZ = REGLAS + "/matriz.csv"
EVIDENCIA = REGLAS + "/evidencia.md"
CRITERIOS_SKILL = ".claude/skills/criterios/SKILL.md"
CRITERIOS_REFS = ".claude/skills/criterios/references/"
PRIMER_TOQUE = ".claude/estado/primer-toque"


def chequeo(capa):
    return "%s/verificar_%s.py" % (REGLAS, capa)


def prueba(capa):
    return "%s/verificar_%s.tests.py" % (REGLAS, capa)


def skill(capa):
    return ".claude/skills/capa-%s/SKILL.md" % capa


def revisor(capa):
    return ".claude/agents/revisor-%s.md" % capa


def writer(capa):
    return agente("writer-%s" % capa)


def agente(nombre):
    return ".claude/agents/%s.md" % nombre


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
