from dataclasses import dataclass

POSIX = "posix"
POWERSHELL = "powershell"
FASES = ("pre", "post")
TIPOS = ("edicion", "lectura", "shell", "otra")
DIALECTOS = (POSIX, POWERSHELL)


@dataclass(frozen=True)
class Herramienta:
    fase: str
    tipo: str
    herramienta: object = None
    rutas: tuple = ()
    comando: object = None
    dialecto: object = None
    agente: object = None
    id_agente: object = None
    sesion: object = None
    cwd: object = None

    def __post_init__(self):
        if self.fase not in FASES:
            raise ValueError("fase desconocida: %r" % (self.fase,))
        if self.tipo not in TIPOS:
            raise ValueError("tipo desconocido: %r" % (self.tipo,))
        if self.dialecto is not None and self.dialecto not in DIALECTOS:
            raise ValueError("dialecto desconocido: %r" % (self.dialecto,))
        if not isinstance(self.rutas, tuple):
            raise ValueError("rutas tiene que ser una tupla, no %r" % (self.rutas,))


@dataclass(frozen=True)
class InicioSesion:
    origen: object = None
    sesion: object = None
    cwd: object = None


@dataclass(frozen=True)
class FinSubagente:
    agente: object = None
    id_agente: object = None
    sesion: object = None
    cwd: object = None
    transcript: object = None
    ultimo_mensaje: object = None
    ya_reintentado: bool = False


@dataclass(frozen=True)
class Permitir:
    pass


@dataclass(frozen=True)
class Bloquear:
    motivo: str


@dataclass(frozen=True)
class Preguntar:
    motivo: str


@dataclass(frozen=True)
class Contexto:
    texto: str


@dataclass(frozen=True)
class Seguir:
    motivo: str
