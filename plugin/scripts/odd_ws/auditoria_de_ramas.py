import sys

sys.dont_write_bytecode = True

import os
import subprocess
import tempfile
import time
from collections import namedtuple

from odd_ws import capas, entregas
from odd_ws.comun import entorno_git

PLAZO_POR_REPO = 60
TOPE_DEL_MOTIVO = 200
RAMAS = entregas.RAMAS
ORIGEN = entregas.ORIGEN
REMOTAS = "refs/remotes/"
CABEZA_DEL_ORIGEN = ORIGEN + "HEAD"
PRINCIPALES = ("main", "master")
FORMATO = "--format=%(refname)%00%(objectname)%00%(symref)"
FETCH = ("-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "fetch.writeCommitGraph=false", "fetch", "--quiet", "--no-tags",
         "--no-prune", "--no-recurse-submodules", "--no-write-fetch-head", "--refmap=", "origin", "+%s*:%s*" % (RAMAS, ORIGEN))
SIN_PROMPTS = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_ASKPASS": ""}
DIFF = ("--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--src-prefix=a/", "--dst-prefix=b/")

SIN_COMMITEAR = "sin_commitear"
ILEGIBLE = "ilegible"
NUNCA = "nunca_empujada"
SIN_EMPUJAR = "sin_empujar"
NO_LLEGO = "no_llego"
SIN_PRINCIPAL = "sin_principal"
SIN_COMPARAR = "sin_comparar"
LLEGO = "llego"
PENDIENTE = "pendiente"
SIN_JUZGAR = "sin_juzgar"
EN_ROJO = "repo_en_rojo"
SIN_TIEMPO = "sin_tiempo"

NO_TERMINO = "no terminó a tiempo"
SALIO_CON = "git salió con %d"
TEXTO_LLEGO = "llegó a %s"
TEXTO_NUNCA = "nunca se empujó"
TEXTO_SIN_COMMITEAR = "cambios sin commitear"
TEXTO_SIN_EMPUJAR = ("1 commit sin empujar", "%d commits sin empujar", "commits sin empujar")
TEXTO_NO_LLEGO = ("1 commit que no llegó a %s", "%d commits que no llegaron a %s")
TEXTO_SIN_PRINCIPAL = "no tiene con qué compararse: el repo no tiene origin/HEAD, origin/main ni origin/master"
TEXTO_SIN_COMPARAR = "no se pudo comparar con %s"
TEXTO_EN_ROJO = "queda sin juzgar, porque el fetch del repo falló"
TEXTO_SIN_TIEMPO = "queda sin juzgar, porque no alcanzó el tiempo"
LINEA = "%s: en %s, %s."
RAMA = "la rama %s %s"
EN_ROJO_LINEA = ("En rojo: %s, porque el fetch falló (%s). Sus ramas no se juzgan con refs viejas: arregla el acceso a su remoto y "
                 "vuelve a auditar.")
SIN_REVISAR_LINEA = "Tickets sin revisar, porque no alcanzó el tiempo: %s."
NADA = "Resumen: ningún ticket nombra una rama de los repos, así que no hay nada que auditar."
TODO = "Resumen: todo llegó (%s de %s)."
NO_TODO = "Resumen: no todo llegó: %s, de %s en %s."
NO_TODO_SIN_RAMAS = "Resumen: no todo llegó: %s."

Cabeza = namedtuple("Cabeza", "cherry squash")
Datos = namedtuple("Datos", "sin_commitear origen sin_empujar principal cabezas")
Falta = namedtuple("Falta", "tipo commits")
Estado = namedtuple("Estado", "llego faltas")
Refs = namedtuple("Refs", "ramas origen cabeza")
RepoAuditado = namedtuple("RepoAuditado", "repo rojo motivo")
RamaAuditada = namedtuple("RamaAuditada", "ticket repo rama carpeta principal estado motivo")
Auditoria = namedtuple("Auditoria", "repos ramas sin_ramas sin_revisar")


def _fuera_de_la_principal(datos):
    if datos.principal is None or any(cabeza.cherry is None for cabeza in datos.cabezas):
        return None
    return len({linea.split()[-1] for cabeza in datos.cabezas if not cabeza.squash for linea in cabeza.cherry if linea.startswith("+")})


def clasificar_rama(datos):
    faltas = []
    if datos.sin_commitear is None:
        faltas.append(Falta(ILEGIBLE, None))
    elif datos.sin_commitear:
        faltas.append(Falta(SIN_COMMITEAR, None))
    fuera = _fuera_de_la_principal(datos)
    if fuera != 0:
        if not datos.origen:
            faltas.append(Falta(NUNCA, None))
        elif datos.sin_empujar != 0:
            faltas.append(Falta(SIN_EMPUJAR, datos.sin_empujar))
        if datos.principal is None:
            faltas.append(Falta(SIN_PRINCIPAL, None))
        elif fuera is None:
            faltas.append(Falta(SIN_COMPARAR, None))
        else:
            faltas.append(Falta(NO_LLEGO, fuera))
    return Estado(not faltas, tuple(faltas))


def principal_de(origen, cabeza):
    apuntada = cabeza[len(ORIGEN):] if cabeza and cabeza.startswith(ORIGEN) else None
    for nombre in ([apuntada] if apuntada else []) + list(PRINCIPALES):
        if nombre in origen:
            return ORIGEN[len(REMOTAS):] + nombre
    return None


def _y(partes):
    return partes[0] if len(partes) == 1 else "%s y %s" % (", ".join(partes[:-1]), partes[-1])


def _commits(cuantos, textos):
    if cuantos is None:
        return textos[-1]
    return textos[0] if cuantos == 1 else textos[1] % cuantos


def texto(estado, principal):
    if estado.llego:
        return TEXTO_LLEGO % principal
    tipos = {falta.tipo: falta.commits for falta in estado.faltas}
    partes = [TEXTO_NUNCA] if NUNCA in tipos else []
    tiene = [TEXTO_SIN_COMMITEAR] if SIN_COMMITEAR in tipos else []
    if SIN_EMPUJAR in tipos:
        tiene.append(_commits(tipos[SIN_EMPUJAR], TEXTO_SIN_EMPUJAR))
    if NO_LLEGO in tipos:
        cuantos = tipos[NO_LLEGO]
        tiene.append(TEXTO_NO_LLEGO[0] % principal if cuantos == 1 else TEXTO_NO_LLEGO[1] % (cuantos, principal))
    if tiene:
        partes.append("tiene " + _y(tiene))
    if ILEGIBLE in tipos:
        partes.append(entregas.ILEGIBLE)
    if SIN_PRINCIPAL in tipos:
        partes.append(TEXTO_SIN_PRINCIPAL)
    if SIN_COMPARAR in tipos:
        partes.append(TEXTO_SIN_COMPARAR % principal)
    return " y ".join(partes)


def archivados(raiz):
    base = os.path.join(str(raiz), capas.TICKETS)
    excluidas = set(entregas.activos(raiz)) | {os.path.basename(capas.TICKET_PLANTILLA_DIR)}
    hallados = []
    for actual, carpetas, archivos in os.walk(base):
        relativa = os.path.relpath(actual, base)
        if relativa == os.curdir:
            carpetas[:] = sorted(carpeta for carpeta in carpetas if carpeta not in excluidas)
        elif capas.INDICE in archivos:
            hallados.append(relativa.replace(os.sep, "/"))
            carpetas[:] = []
        else:
            carpetas.sort()
    return sorted(hallados)


def _hasta():
    return time.monotonic() + PLAZO_POR_REPO


def _git(arbol, limite, *args, entrada=None):
    restante = limite - time.monotonic()
    if restante <= 0:
        raise subprocess.TimeoutExpired(["git", *args], 0)
    flujo = {"input": entrada} if entrada is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run(["git", "-C", str(arbol), *args], capture_output=True, timeout=restante, env=entorno_git(), **flujo)


def _fetch(ruta):
    restante = _hasta() - time.monotonic()
    if restante <= 0:
        return True, NO_TERMINO
    entorno = entorno_git()
    entorno.update(SIN_PROMPTS)
    with tempfile.TemporaryFile() as errores:
        try:
            r = subprocess.run(["git", "-C", str(ruta), *FETCH], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errores,
                               timeout=restante, env=entorno)
        except subprocess.TimeoutExpired:
            return True, NO_TERMINO
        if r.returncode == 0:
            return False, None
        errores.seek(0)
        lineas = [linea.strip() for linea in errores.read().decode("utf-8", errors="replace").splitlines() if linea.strip()]
    return True, (lineas[0] if lineas else SALIO_CON % r.returncode)[:TOPE_DEL_MOTIVO]


def _refs(ruta, limite):
    r = _git(ruta, limite, "for-each-ref", FORMATO, RAMAS, ORIGEN)
    ramas, origen, cabeza = {}, {}, None
    if r.returncode == 0:
        for linea in r.stdout.decode("utf-8", errors="replace").split("\n"):
            partes = linea.split("\0")
            if len(partes) != 3:
                continue
            nombre, sha, simbolica = partes
            if nombre == CABEZA_DEL_ORIGEN:
                cabeza = simbolica or None
            elif nombre.startswith(RAMAS):
                ramas[nombre[len(RAMAS):]] = sha
            elif nombre.startswith(ORIGEN):
                origen[nombre[len(ORIGEN):]] = sha
    return Refs(ramas, origen, cabeza)


def _sin_commitear(carpeta, limite):
    if carpeta is None or not os.path.isdir(carpeta):
        return False
    r = _git(carpeta, limite, "status", "--porcelain=v2", "-z", "-uall")
    return bool(r.stdout) if r.returncode == 0 else None


def _divergencia(ruta, remota, local, limite):
    r = _git(ruta, limite, "rev-list", "--left-right", "--count", "%s...%s" % (remota, local))
    partes = r.stdout.decode("ascii", errors="replace").split()
    if r.returncode != 0 or len(partes) != 2 or not all(parte.isdigit() for parte in partes):
        return None, None
    return int(partes[0]), int(partes[1])


def _parches(ruta, limite, diff):
    r = _git(ruta, limite, "patch-id", "--stable", entrada=diff)
    if r.returncode != 0:
        return frozenset()
    return frozenset(linea.split()[0] for linea in r.stdout.decode("ascii", errors="replace").splitlines() if linea.split())


def _squash(ruta, principal, cabeza, limite, cache):
    r = _git(ruta, limite, "merge-base", principal, cabeza)
    base = r.stdout.decode("ascii", errors="replace").strip()
    if r.returncode != 0 or not base:
        return False
    diff = _git(ruta, limite, "diff", *DIFF, base, cabeza)
    if diff.returncode != 0:
        return False
    if not diff.stdout.strip():
        return True
    if (base, principal) not in cache:
        log = _git(ruta, limite, "log", "-p", "--no-merges", "--no-show-signature", *DIFF, "--format=commit %H", "%s..%s" % (base, principal))
        cache[(base, principal)] = _parches(ruta, limite, log.stdout) if log.returncode == 0 else frozenset()
    return bool(_parches(ruta, limite, diff.stdout) & cache[(base, principal)])


def _cabeza(ruta, principal, cabeza, limite, cache):
    r = _git(ruta, limite, "cherry", principal, cabeza)
    if r.returncode != 0:
        return Cabeza(None, False)
    lineas = tuple(linea.strip() for linea in r.stdout.decode("ascii", errors="replace").splitlines() if linea.strip())
    return Cabeza(lineas, any(linea.startswith("+") for linea in lineas) and _squash(ruta, principal, cabeza, limite, cache))


def _datos(ruta, entrega, refs, principal, limite, cache):
    local, remota = RAMAS + entrega.rama, ORIGEN + entrega.rama
    origen = entrega.rama in refs.origen
    sin_empujar, cabezas = 0, [local]
    if origen and refs.origen[entrega.rama] != refs.ramas.get(entrega.rama):
        solo_en_origen, sin_empujar = _divergencia(ruta, remota, local, limite)
        if solo_en_origen != 0:
            cabezas.append(remota)
    comparadas = () if principal is None else tuple(_cabeza(ruta, REMOTAS + principal, cabeza, limite, cache) for cabeza in cabezas)
    return Datos(_sin_commitear(entrega.carpeta, limite), origen, sin_empujar, principal, comparadas)


def _sin_juzgar(ticket, entrega, motivo):
    return RamaAuditada(ticket, entrega.repo, entrega.rama, entrega.carpeta, None, None, motivo)


def _juzgar(ruta, pendientes):
    limite, cache, por_rama, juzgadas = _hasta(), {}, {}, []
    try:
        refs = _refs(ruta, limite)
        principal = principal_de(refs.origen, refs.cabeza)
        for orden, ticket, entrega in pendientes:
            if entrega.rama not in por_rama:
                por_rama[entrega.rama] = clasificar_rama(_datos(ruta, entrega, refs, principal, limite, cache))
            juzgadas.append((orden, RamaAuditada(ticket, entrega.repo, entrega.rama, entrega.carpeta, principal, por_rama[entrega.rama], None)))
    except subprocess.TimeoutExpired:
        juzgadas += [(orden, _sin_juzgar(ticket, entrega, SIN_TIEMPO)) for orden, ticket, entrega in pendientes[len(juzgadas):]]
    return juzgadas


def auditar(config, tickets):
    repos = [RepoAuditado(repo, *_fetch(config["repos"][repo]["path"])) for repo in sorted(config["repos"])]
    rojos = {repo.repo for repo in repos if repo.rojo}
    resueltas = []
    try:
        for ticket, halladas in entregas.entregas_de(config, tickets, _hasta()):
            resueltas.append((ticket, halladas))
    except subprocess.TimeoutExpired:
        pass
    por_repo = {}
    for orden, (ticket, halladas) in enumerate(resueltas):
        for entrega in halladas:
            por_repo.setdefault(entrega.repo, []).append((orden, ticket, entrega))
    ramas = []
    for repo, pendientes in sorted(por_repo.items()):
        if repo in rojos:
            ramas += [(orden, _sin_juzgar(ticket, entrega, EN_ROJO)) for orden, ticket, entrega in pendientes]
        else:
            ramas += _juzgar(config["repos"][repo]["path"], pendientes)
    ramas.sort(key=lambda par: (par[0], par[1].repo, par[1].rama))
    return Auditoria(repos, [rama for _, rama in ramas], [ticket for ticket, halladas in resueltas if not halladas],
                     list(tickets[len(resueltas):]))


def estado_de(rama):
    if rama.motivo:
        return SIN_JUZGAR
    return LLEGO if rama.estado.llego else PENDIENTE


def texto_de(rama):
    if rama.motivo == EN_ROJO:
        return TEXTO_EN_ROJO
    if rama.motivo == SIN_TIEMPO:
        return TEXTO_SIN_TIEMPO
    return texto(rama.estado, rama.principal)


def todo_llego(auditoria):
    return (not auditoria.sin_revisar and not any(repo.rojo for repo in auditoria.repos)
            and all(estado_de(rama) == LLEGO for rama in auditoria.ramas))


def _cuantos(cuantos, singular, plural):
    if not cuantos:
        return ""
    return "1 %s" % singular if cuantos == 1 else "%d %s" % (cuantos, plural)


def resumen(auditoria):
    estados = [estado_de(rama) for rama in auditoria.ramas]
    total = (_cuantos(len(estados), "rama", "ramas"), _cuantos(len({rama.ticket for rama in auditoria.ramas}), "ticket", "tickets"))
    if todo_llego(auditoria):
        return TODO % total if estados else NADA
    partes = [parte for parte in (_cuantos(estados.count(PENDIENTE), "rama pendiente", "ramas pendientes"),
                                  _cuantos(estados.count(SIN_JUZGAR), "rama sin juzgar", "ramas sin juzgar"),
                                  _cuantos(sum(1 for repo in auditoria.repos if repo.rojo), "repo en rojo", "repos en rojo"),
                                  _cuantos(len(auditoria.sin_revisar), "ticket sin revisar", "tickets sin revisar")) if parte]
    return NO_TODO % ((_y(partes),) + total) if estados else NO_TODO_SIN_RAMAS % _y(partes)


def lineas(auditoria):
    grupos = []
    for rama in auditoria.ramas:
        if grupos and grupos[-1][0] == (rama.ticket, rama.repo):
            grupos[-1][1].append(rama)
        else:
            grupos.append(((rama.ticket, rama.repo), [rama]))
    salida = [LINEA % (ticket, repo, "; ".join(RAMA % (rama.rama, texto_de(rama)) for rama in ramas)) for (ticket, repo), ramas in grupos]
    salida += [EN_ROJO_LINEA % (repo.repo, repo.motivo) for repo in auditoria.repos if repo.rojo]
    if auditoria.sin_revisar:
        salida.append(SIN_REVISAR_LINEA % ", ".join(auditoria.sin_revisar))
    return salida + [resumen(auditoria)]


def a_json(auditoria):
    return {
        "todo_llego": todo_llego(auditoria),
        "repos": [{"repo": repo.repo, "rojo": repo.rojo, "motivo": repo.motivo} for repo in auditoria.repos],
        "ramas": [{"ticket": rama.ticket, "repo": rama.repo, "rama": rama.rama,
                   "carpeta": os.path.normpath(rama.carpeta) if rama.carpeta else None, "principal": rama.principal,
                   "estado": estado_de(rama), "motivo": rama.motivo,
                   "faltas": [{"tipo": falta.tipo, "commits": falta.commits} for falta in (rama.estado.faltas if rama.estado else ())],
                   "texto": texto_de(rama)} for rama in auditoria.ramas],
        "tickets_sin_ramas": list(auditoria.sin_ramas),
        "tickets_sin_revisar": list(auditoria.sin_revisar),
    }
