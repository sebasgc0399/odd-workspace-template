import sys

sys.dont_write_bytecode = True

import hashlib
import json
import os
import re
import stat
import subprocess
import time
from collections import namedtuple

import config_loader
from odd_ws import capas
from odd_ws.comun import entorno_git

PLAZO_DEL_INICIO = 4
PLAZO_DEL_CLI = 60
TOPE_DEL_INICIO = 20
HILOS = 4
TOPE_BYTES = 2000000
VERSION = 1
CAMPO = "worktree y rama"
FRAGMENTO = re.compile(r"`([^`\n]+)`")
VINETA = re.compile(r"([ \t]*)[-*+][ \t]+(.*)")
RAMAS = "refs/heads/"
ORIGEN = "refs/remotes/origin/"
FORMATO = "--format=%(refname)%00%(objectname)%00%(worktreepath)"
CAMPOS_ANTES_DE_LA_RUTA = {b"1": 8, b"2": 9, b"u": 10, b"?": 1}
RENOMBRE = b"2"
NADA = "nada pendiente"
ENCABEZADO = "odd-ws: hay trabajo de los tickets que todavía no llegó a origin (mirado con las refs locales, sin fetch):"
CIERRE = ("Cuéntaselo al usuario. Si ya llegó por otro camino o no va a subirse, con su sí corre `entregas.py --confirmar <ticket>`: "
          "ese ticket calla hasta que cambien sus ramas o sus archivos.")
NUNCA = "nunca se empujó"
SIN_COMMITEAR = "cambios sin commitear"
SIN_EMPUJAR = "%d commits sin empujar"
UN_COMMIT_SIN_EMPUJAR = "1 commit sin empujar"
COMMITS_SIN_CONTAR = "commits sin empujar"
ILEGIBLE = "su carpeta no se pudo leer con git status"
SIN_TIEMPO = "no alcanzó el tiempo"
FUERA_DEL_TOPE = "el inicio revisa hasta %d"
QUEDO = "quedó 1 ticket sin revisar (%s), así que no cuenta como limpio"
QUEDARON = "quedaron %d tickets sin revisar (%s), así que no cuentan como limpios"
AL_INICIO = "odd-ws: %s: `entregas.py` los revisa todos."

Entrega = namedtuple("Entrega", "repo rama carpeta")
Revision = namedtuple("Revision", "pendientes sin_tiempo fuera_del_tope")
Refs = namedtuple("Refs", "ramas origen")


class Rechazo(Exception):
    pass


def _git(arbol, limite, *args):
    restante = limite - time.monotonic()
    if restante <= 0:
        raise subprocess.TimeoutExpired(["git", *args], 0)
    return subprocess.run(["git", "-C", str(arbol), *args], capture_output=True, timeout=restante, env=entorno_git())


def _a_tiempo(limite):
    if time.monotonic() >= limite:
        raise subprocess.TimeoutExpired(["entregas"], 0)


def activos(raiz):
    carpeta = os.path.join(str(raiz), capas.TICKETS)
    plantilla = os.path.basename(capas.TICKET_PLANTILLA_DIR)
    try:
        nombres = sorted(os.listdir(carpeta))
    except OSError:
        return []
    return [nombre for nombre in nombres if nombre != plantilla and os.path.isfile(os.path.join(carpeta, nombre, capas.INDICE))]


def _es_el_campo(contenido):
    return contenido.replace("*", "").replace("_", "").lstrip().casefold().startswith(CAMPO)


def fragmentos(texto):
    hallados, sangria = [], None
    for linea in texto.splitlines():
        vineta = VINETA.fullmatch(linea)
        if sangria is not None and linea.strip():
            propia = len(linea) - len(linea.lstrip(" \t"))
            if propia <= sangria:
                sangria = None
        if sangria is None and vineta and _es_el_campo(vineta.group(2)):
            sangria = len(vineta.group(1))
        if sangria is None:
            continue
        for fragmento in FRAGMENTO.findall(linea):
            fragmento = fragmento.strip()
            if fragmento and fragmento not in hallados:
                hallados.append(fragmento)
    return hallados


def _texto_del_ticket(raiz, ticket):
    try:
        with open(os.path.join(str(raiz), capas.TICKETS, ticket, capas.INDICE), encoding="utf-8", errors="replace") as archivo:
            return archivo.read()
    except OSError:
        return ""


def _ruta_de_las_confirmadas(raiz):
    return os.path.join(str(raiz), *capas.ENTREGAS.split("/"))


def confirmadas(raiz):
    try:
        with open(_ruta_de_las_confirmadas(raiz), encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict) or datos.get("version") != VERSION or not isinstance(datos.get("confirmadas"), dict):
        return {}
    return {ticket: entrada["huella"] for ticket, entrada in datos["confirmadas"].items()
            if isinstance(entrada, dict) and isinstance(entrada.get("huella"), str)}


def _reemplazar(ruta, contenido):
    temporal = "%s.%d.tmp" % (ruta, os.getpid())
    try:
        with open(temporal, "wb") as archivo:
            archivo.write(contenido)
        os.replace(temporal, ruta)
    except OSError:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise


def _guardar(raiz, ticket, huella, fecha):
    try:
        with open(_ruta_de_las_confirmadas(raiz), encoding="utf-8") as archivo:
            previas = json.load(archivo)["confirmadas"]
    except (OSError, ValueError, KeyError, TypeError):
        previas = {}
    vigentes = set(activos(raiz))
    nuevas = {nombre: entrada for nombre, entrada in (previas.items() if isinstance(previas, dict) else ())
              if nombre in vigentes and nombre != ticket and isinstance(entrada, dict)}
    nuevas[ticket] = {"huella": huella, "fecha": fecha}
    ruta = _ruta_de_las_confirmadas(raiz)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    texto = json.dumps({"version": VERSION, "confirmadas": nuevas}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _reemplazar(ruta, texto.encode("utf-8"))


def _carpeta(fragmento):
    if fragmento.startswith(("\\\\", "//")):
        return None
    ruta = os.path.expanduser(fragmento)
    return ruta if os.path.isabs(ruta) and os.path.isdir(ruta) else None


def _rutas(salida):
    campos, rutas, i = salida.split(b"\0"), [], 0
    while i < len(campos):
        registro = campos[i]
        i += 1
        antes = CAMPOS_ANTES_DE_LA_RUTA.get(registro[:1])
        if antes is None:
            continue
        if registro[:1] == RENOMBRE:
            i += 1
        trozos = registro.split(b" ", antes)
        if len(trozos) > antes and trozos[antes]:
            rutas.append(trozos[antes])
    return rutas


def _contenido(ruta):
    try:
        datos = os.stat(ruta)
    except OSError:
        return b"ausente"
    if stat.S_ISDIR(datos.st_mode):
        return b"carpeta"
    if datos.st_size > TOPE_BYTES:
        return ("%d:%d" % (datos.st_size, datos.st_mtime_ns)).encode("ascii")
    suma = hashlib.sha256()
    try:
        with open(ruta, "rb") as archivo:
            suma.update(archivo.read())
    except OSError:
        return b"ilegible"
    return suma.hexdigest().encode("ascii")


class _Revisor:
    def __init__(self, config, limite):
        self.config, self.limite = config, limite
        self.refs, self.estados, self.adelante, self.resueltas, self.lecturas = {}, {}, {}, {}, {}

    def _ruta(self, repo):
        return self.config["repos"][repo]["path"]

    def refs_de(self, repo):
        if repo not in self.refs:
            self.refs[repo] = self._leer_refs(repo)
        return self.refs[repo]

    def _leer_refs(self, repo):
        r = _git(self._ruta(repo), self.limite, "for-each-ref", FORMATO, RAMAS, ORIGEN)
        ramas, origen = {}, {}
        if r.returncode != 0:
            return Refs(ramas, origen)
        for linea in r.stdout.decode("utf-8", errors="replace").split("\n"):
            partes = linea.split("\0")
            if len(partes) != 3:
                continue
            nombre, cabeza, carpeta = partes
            if nombre.startswith(RAMAS):
                ramas[nombre[len(RAMAS):]] = (cabeza, carpeta or None)
            elif nombre.startswith(ORIGEN) and nombre != ORIGEN + "HEAD":
                origen[nombre[len(ORIGEN):]] = cabeza
        return Refs(ramas, origen)

    def _rama_en(self, repo, arbol):
        buscada = config_loader.canonica(arbol)
        for rama, (_, carpeta) in sorted(self.refs_de(repo).ramas.items()):
            if carpeta and config_loader.canonica(carpeta) == buscada:
                return rama
        return None

    def entregas(self, fragmentos_):
        halladas = {}
        for fragmento in fragmentos_:
            carpeta = _carpeta(fragmento)
            dueno = config_loader.repo_de(carpeta, self.config) if carpeta else None
            if dueno is not None:
                rama = self._rama_en(dueno.repo, dueno.arbol)
                if rama is not None:
                    halladas[(dueno.repo, rama)] = Entrega(dueno.repo, rama, self.refs_de(dueno.repo).ramas[rama][1])
                continue
            for repo in sorted(self.config["repos"]):
                ramas = self.refs_de(repo).ramas
                if fragmento in ramas:
                    halladas[(repo, fragmento)] = Entrega(repo, fragmento, ramas[fragmento][1])
        return [halladas[clave] for clave in sorted(halladas)]

    def resueltas_de(self, fragmentos_):
        clave = tuple(fragmentos_)
        if clave not in self.resueltas:
            self.resueltas[clave] = self.entregas(fragmentos_)
        return self.resueltas[clave]

    def _leida(self, clave, leer, *args):
        lectura = self.lecturas.pop(clave, None)
        if lectura is None:
            return leer(*args)
        try:
            return lectura.result()
        except subprocess.TimeoutExpired:
            raise
        except Exception:
            return None

    def _leer_estado(self, carpeta):
        r = _git(carpeta, self.limite, "status", "--porcelain=v2", "-z", "-uall")
        return r.stdout if r.returncode == 0 else None

    def estado(self, carpeta):
        clave = config_loader.canonica(carpeta)
        if clave not in self.estados:
            self.estados[clave] = self._leida(clave, self._leer_estado, carpeta)
        return self.estados[clave]

    def _contar(self, repo, rama):
        r = _git(self._ruta(repo), self.limite, "rev-list", "--count", "%s%s..%s%s" % (ORIGEN, rama, RAMAS, rama))
        texto = r.stdout.decode("ascii", errors="replace").strip()
        return int(texto) if r.returncode == 0 and texto.isdigit() else None

    def sin_empujar(self, repo, rama):
        clave = (repo, rama)
        if clave not in self.adelante:
            self.adelante[clave] = self._leida(clave, self._contar, repo, rama)
        return self.adelante[clave]

    def _con_carpeta(self, entrega):
        return entrega.carpeta is not None and os.path.isdir(entrega.carpeta)

    def _adelantada(self, entrega):
        refs = self.refs_de(entrega.repo)
        origen = refs.origen.get(entrega.rama)
        return origen is not None and origen != refs.ramas[entrega.rama][0]

    def precargar(self, pool, fragmentos_por_ticket):
        for fragmentos_ in fragmentos_por_ticket:
            for entrega in self.resueltas_de(fragmentos_):
                if self._con_carpeta(entrega):
                    clave = config_loader.canonica(entrega.carpeta)
                    if clave not in self.estados and clave not in self.lecturas:
                        self.lecturas[clave] = pool.submit(self._leer_estado, entrega.carpeta)
                clave = (entrega.repo, entrega.rama)
                if self._adelantada(entrega) and clave not in self.adelante and clave not in self.lecturas:
                    self.lecturas[clave] = pool.submit(self._contar, entrega.repo, entrega.rama)

    def _estado_de(self, entrega):
        if not self._con_carpeta(entrega):
            return b""
        return self.estado(entrega.carpeta)

    def faltas(self, entrega):
        origen = self.refs_de(entrega.repo).origen.get(entrega.rama)
        estado = self._estado_de(entrega)
        tiene = []
        if estado:
            tiene.append(SIN_COMMITEAR)
        if self._adelantada(entrega):
            adelante = self.sin_empujar(entrega.repo, entrega.rama)
            if adelante is None:
                tiene.append(COMMITS_SIN_CONTAR)
            elif adelante:
                tiene.append(UN_COMMIT_SIN_EMPUJAR if adelante == 1 else SIN_EMPUJAR % adelante)
        partes = [NUNCA] if origen is None else []
        if tiene:
            partes.append("tiene " + " y ".join(tiene))
        if estado is None:
            partes.append(ILEGIBLE)
        return " y ".join(partes)

    def _huella_de_la_carpeta(self, entrega):
        estado = self._estado_de(entrega)
        if not estado:
            return None if estado is None else ""
        suma = hashlib.sha256(estado)
        for ruta in _rutas(estado):
            _a_tiempo(self.limite)
            suma.update(b"\0" + ruta + b"\0" + _contenido(os.path.join(entrega.carpeta, os.fsdecode(ruta))))
        return suma.hexdigest()

    def huella(self, entregas_):
        datos = []
        for entrega in entregas_:
            refs = self.refs_de(entrega.repo)
            datos.append([entrega.repo, entrega.rama, refs.ramas[entrega.rama][0], refs.origen.get(entrega.rama), entrega.carpeta,
                          self._huella_de_la_carpeta(entrega)])
        return hashlib.sha256(json.dumps(datos, ensure_ascii=True).encode("ascii")).hexdigest()

    def ticket(self, fragmentos_, confirmada):
        entregas_ = self.resueltas_de(fragmentos_)
        pendientes = [(entrega, faltas) for entrega in entregas_ for faltas in [self.faltas(entrega)] if faltas]
        if not pendientes or (confirmada is not None and confirmada == self.huella(entregas_)):
            return None
        return pendientes


def entregas_de(config, tickets, limite):
    revisor = _Revisor(config, limite)
    for ticket in tickets:
        yield ticket, revisor.entregas(fragmentos(_texto_del_ticket(config["raiz"], ticket)))


def _con_algo_que_chequear(config):
    if not config["repos"]:
        return []
    return [(ticket, hallados) for ticket in activos(config["raiz"]) for hallados in [fragmentos(_texto_del_ticket(config["raiz"], ticket))]
            if hallados]


def revisar(config, limite, tope=None):
    tickets = _con_algo_que_chequear(config)
    fuera = max(0, len(tickets) - tope) if tope is not None else 0
    tickets = tickets[:len(tickets) - fuera]
    if not tickets:
        return Revision([], 0, fuera)
    from concurrent.futures import ThreadPoolExecutor

    revisor, previas, pendientes = _Revisor(config, limite), confirmadas(config["raiz"]), []
    with ThreadPoolExecutor(max_workers=HILOS) as pool:
        try:
            revisor.precargar(pool, [hallados for _, hallados in tickets])
        except subprocess.TimeoutExpired:
            pass
        for posicion, (ticket, hallados) in enumerate(tickets):
            try:
                _a_tiempo(limite)
                pendiente = revisor.ticket(hallados, previas.get(ticket))
            except subprocess.TimeoutExpired:
                return Revision(pendientes, len(tickets) - posicion, fuera)
            if pendiente:
                pendientes.append((ticket, pendiente))
    return Revision(pendientes, 0, fuera)


def linea(ticket, pendiente):
    return "%s: %s." % (ticket, "; ".join("en %s, la rama %s %s" % (entrega.repo, entrega.rama, faltas) for entrega, faltas in pendiente))


def sin_revisar(revision, tope=TOPE_DEL_INICIO):
    motivos = ([SIN_TIEMPO] if revision.sin_tiempo else []) + ([FUERA_DEL_TOPE % tope] if revision.fuera_del_tope else [])
    cuantos = revision.sin_tiempo + revision.fuera_del_tope
    if not cuantos:
        return None
    motivo = " y ".join(motivos)
    return QUEDO % motivo if cuantos == 1 else QUEDARON % (cuantos, motivo)


def aviso_de_inicio(config, limite):
    revision = revisar(config, limite, TOPE_DEL_INICIO)
    lineas = []
    if revision.pendientes:
        lineas += [ENCABEZADO] + ["- " + linea(ticket, pendiente) for ticket, pendiente in revision.pendientes] + [CIERRE]
    quedaron = sin_revisar(revision)
    if quedaron:
        lineas.append(AL_INICIO % quedaron)
    return "\n".join(lineas) or None


def elegir(nombre, tickets):
    exactos = [ticket for ticket in tickets if ticket == nombre] or [ticket for ticket in tickets if ticket.casefold() == nombre.casefold()]
    if len(exactos) == 1:
        return exactos[0]
    por_id = exactos or [ticket for ticket in tickets if ticket.casefold().startswith(nombre.casefold() + "-")]
    if len(por_id) == 1:
        return por_id[0]
    if por_id:
        raise Rechazo("«%s» nombra a %d tickets (%s): usa el nombre de su carpeta" % (nombre, len(por_id), ", ".join(por_id)))
    raise Rechazo("no hay un ticket activo «%s» en %s/ (un ticket archivado no cuenta)" % (nombre, capas.TICKETS))


def confirmar(config, nombre, limite, fecha):
    raiz = config["raiz"]
    ticket = elegir(nombre, activos(raiz))
    revisor = _Revisor(config, limite)
    entregas_ = revisor.entregas(fragmentos(_texto_del_ticket(raiz, ticket))) if config["repos"] else []
    if not any(revisor.faltas(entrega) for entrega in entregas_):
        return ticket, False
    _guardar(raiz, ticket, revisor.huella(entregas_), fecha)
    return ticket, True
