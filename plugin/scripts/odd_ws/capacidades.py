from odd_ws.eventos import Bloquear, Contexto, Permitir, Preguntar, Seguir

SOPORTADO = "soportado"
DEGRADADO = "degradado"
NO_DISPONIBLE = "no disponible"
ESTADOS = (SOPORTADO, DEGRADADO, NO_DISPONIBLE)

PRE = "pre"
POST = "post"
INICIO = "inicio"
FIN_SUBAGENTE = "fin_subagente"
INICIO_TURNO = "inicio_turno"
FIN_TURNO = "fin_turno"
PUNTOS_DE_EVENTO = (PRE, POST, INICIO, FIN_SUBAGENTE, INICIO_TURNO, FIN_TURNO)

CAPACIDADES = {
    "P1": "contexto al iniciar la sesión",
    "P2": "bloquear una edición antes de que pase",
    "P3": "guard de shell que bloquea o pregunta",
    "P4": "bloquear o dar contexto después de una edición o una lectura",
    "P5": "compuerta de fin de subagente",
    "P6": "identidad del agente en los hooks",
    "P7": "subagentes propios",
    "P8": "skills del plugin",
    "P9": "distribución del plugin",
    "P10": "instrucciones por carpeta",
    "P11": "compuerta de fin de turno del principal",
    "P12": "inicio de turno",
}

REQUISITOS = {
    "P1": ((INICIO, Contexto),),
    "P2": ((PRE, Bloquear),),
    "P3": ((PRE, Bloquear), (PRE, Preguntar)),
    "P4": ((POST, Bloquear), (POST, Contexto)),
    "P5": ((FIN_SUBAGENTE, Seguir),),
    "P11": ((FIN_TURNO, Seguir),),
    "P12": ((INICIO_TURNO, Permitir),),
}
