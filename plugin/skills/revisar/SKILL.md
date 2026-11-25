---
name: revisar
description: Revisar un cambio de un ticket con los revisores de la instancia, antes del commit o antes de mostrárselo a un líder. Hace el triaje y deja un recibo atado al diff.
---

# /odd-ws:revisar

Orquesta la revisión de un cambio con los agentes de `.claude/agents/`: `revisor-diseno` (entre capas) y el `revisor-<capa>` de cada capa que toca el cambio. Los revisores solo leen: **el orquestador arma la entrada, lanza las corridas, rescata los reportes, los consolida y escribe el recibo.** Ningún revisor edita código ni commitea, y esta skill tampoco: ni `git add` ni `git commit`.

En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts` y `<ticket>` es la carpeta del ticket. En Windows con Codex, los comandos van con `python` en lugar de `python3`. El detalle está en `references/`, junto a este archivo: se lee solo cuando un paso lo pide, y ahí `<S>` quiere decir lo mismo.

**Perfil `controles`.** Antes de nada, lee `workspace.config.json` en la raíz de la instancia: si dice `"profile": "controles"`, esta skill no aplica, porque esa instancia no tiene revisores ni recibos y la revisión es la de la herramienta del usuario (por ejemplo, el RDD de gentle-ai). Dilo en una línea y detente, sin correr nada.

## Reglas duras

1. **Nunca se lanza una revisión sin el sí del usuario**, aunque el modelo haya invocado la skill por su cuenta: el sí va después de anunciar el modo y su costo (paso 2). Sin sí corren solo el modo `0`, que cuesta cero corridas, y el rechequeo aprobado con su lote (sección 9), y los dos anuncian su modo igual.
2. **Nunca dos revisiones a la vez.** Las corridas de una revisión se lanzan juntas; la siguiente revisión espera a que esta termine.
3. **No hay bucle automático de corrección.** El usuario decide qué corrige, y una revisión se cierra con una corrección y un rechequeo (sección 9). Cualquier otra revisión después de corregir es un pedido nuevo y vuelve a pedir el sí.
4. **Solo git de lectura en los repos del equipo:** ni cambiar de rama, ni tocar el índice (un archivo sin trackear entra al diff con `--no-index`, nunca con `git add -N`), ni plantar archivos. Todo lo que escribe esta skill va en la carpeta del ticket.
5. **Todas las corridas de una revisión usan el mismo modelo:** no pases `model` a ninguna o pásale el mismo alias a todas, y no fijes IDs de modelo.
6. **Esta skill no congela nada:** si el usuario quiere dejar la revisión como caso del modo sombra (por ejemplo, un `completo` que va a un líder), es de `/odd-ws:eval-reviewers`, que lo congela, lo puntúa y lo ratifica.

## 1. Las entradas

- **El ticket** es `tickets/<id>-<slug>/`. Con solo el id, búscalo con Glob (lista archivos, no carpetas), recursivo porque un ticket archivado puede estar en una subcarpeta: `tickets/**/<id>-*/CLAUDE.md`. Si sale más de una carpeta, lístalas y pregunta cuál; nunca elijas tú, porque con ids que llevan guion el glob de un id puede traer otro ticket.
- **Los repos tocados** salen de `workspace.local.json` (`repos.<repo>.path`), y su worktree y rama, del `CLAUDE.md` del ticket («Worktree y rama»): si hay worktree, ese es el `--repo`, no el árbol principal. Si no está claro qué repos toca el cambio, pregunta.
- **La base** la eligen el triaje y el recibo con la misma regla: la explícita (`--repo <ruta>#<base>`), si no el último sello de los recibos del ticket, y si no el merge-base con `origin/HEAD`. Los scripts no hacen `git fetch`: si el `origin/HEAD` local puede estar atrasado, propón el `git fetch` de ese repo y córrelo solo con el sí del usuario.
- **Los archivos que no son del ticket** (por ejemplo, los del ambiente local, modificados a propósito) se separan con el usuario: no entran a la entrada ni al recibo.

## 2. El triaje y el sí

1. Corre el triaje, que solo lee, desde la carpeta de la instancia o con `--raiz`:

   ```bash
   python3 "<S>/triaje.py" --ticket "<ticket>" --repo <repo o worktree>[#<base>] [--repo …] [--taller <archivo del taller del ticket>] [--clon <repo>] [--raiz <raíz de la instancia>] [--json]
   ```

   Pasa siempre `--ticket`, y muestra junto al modo la línea `repo … (base …, <origen>)`, que dice de dónde salió la base. Si una unidad revisada ya está commiteada y sin sellar, séllala antes (ver «Después de la revisión»); si `--sellar` sale con 1, sigue. Si el triaje sale con 2, muestra el mensaje tal cual y corrígelo.
2. **El modo lo propone el triaje y no se elige a ojo.** Las señales solo escalan, y ante la duda se sube, porque un falso negativo es un hallazgo que llega al líder:

   | Modo | Sale cuando |
   |---|---|
   | `sin-cambios` | no hay nada que revisar: se avisa y se termina |
   | `0` | solo docs o notas del taller: lectura estructural, sin revisores |
   | `rapido` | todas las señales en negativo y el instrumento verificado |
   | `completo` | cualquier señal positiva o inválida |

   **Nunca bajes el modo por tu cuenta.**
3. **Pregunta si el cambio va a un líder antes del commit**, que el triaje no lo puede detectar: si va, el modo es `completo` aunque todo haya salido en negativo.
4. Los archivos «fuera de la unidad» (generados sin trackear, como `__pycache__/` o `*.pyc`) no entran a la revisión ni al recibo: díselo al usuario en una línea, porque puede borrarlos o ignorarlos. Muestra la lista «el triaje NO detecta» y aplica tu criterio (consumidores fuera de los repos declarados, la forma de un resultado que consume otra capa, constantes compartidas).
5. **Anuncia, antes de lanzar nada,** el modo y las señales que lo decidieron (o «va a un líder»), las capas tocadas, de la columna `[capa]` (un archivo `sin capa` lo lee el de diseño, y se avisa), y el costo en corridas, sin inventar cifras: `0` son 0; `rapido`, `1 + <capas tocadas>`; `completo`, `3 + <capas tocadas>`. Salvo en modo `0`, cita tal cual la línea de `python3 "<S>/rescatar.py" --ultimo-costo "<ticket>"`, sin multiplicarla ni ajustarla a este diff; si sale con 1, anuncia solo las corridas.
6. **Espera el sí explícito del usuario:** sin él no se lanza ni se escribe nada, salvo en modo `0` (sección 5) o en un rechequeo aprobado con su lote de corrección. Si el triaje termina con «corregir antes de lanzar», propón corregir primero; lanzar sin corregir pide un sí aparte: lee `references/chequeos.md`.

**La bajada**, de `completo` a `rapido`, la pide el usuario con su motivo, y su pedido es el sí de `rapido`; nunca si el cambio va a un líder (si no lo respondió, pregúntaselo antes). Si el modo es `completo` y no va a un líder, lee «La bajada» en `references/recibo.md` antes de anunciar: cuándo cabe ofrecerla, en una línea y sin recomendarla.

## 3. La entrada de los revisores

**La carpeta de la revisión** es `<ticket>/revision/<fecha>-<modo>/`, con la fecha de hoy (`AAAA-MM-DD`) fijada para toda la revisión. Si ya existe (otra ronda del mismo día y modo), no la pises ni la muevas: esta ronda va en `<fecha>-<modo>-2`, o en el siguiente número libre, que de aquí en adelante es `<fecha>-<modo>`, y su recibo lleva `--ronda <n>`. Con el sí, guarda en su `entrada/` un diff por repo, `<repo>.diff`, solo con los archivos del ticket, y el triaje:

```bash
git -C <repo> diff --no-color <base> -- <archivo> [<archivo>…] > "<entrada>/<repo>.diff"
git -C <repo> diff --no-color --no-index -- /dev/null <archivo nuevo sin trackear> >> "<entrada>/<repo>.diff"
python3 "<S>/triaje.py" <los argumentos del paso 2> --json > "<entrada>/triaje.json"
```

La primera línea cubre los archivos trackeados (commiteados o no); la segunda va por cada archivo nuevo sin trackear y sale con 1, que es lo normal. `<base>` es la base completa del triaje. Si el diff sale vacío, detente: algo de la lista no cuadra. `triaje.json` y `recibo.json` no se editan a mano: si algo no cuadra, se vuelve a correr el script.

## 4. Las corridas

Cada corrida es un `Agent` en segundo plano (`run_in_background`), todas en el **mismo mensaje**; en Pi (gentle-shell), antes de lanzar, lee «Pi» en `references/hosts.md`.

Son las del costo anunciado: `revisor-diseno` ×1 en `rapido` y ×3 en `completo`, más `revisor-<capa>` ×1 por cada capa tocada.

**El prompt** de cada corrida sale de la plantilla de `references/prompt.md`, con el orden de lectura de cada corrida de diseño: léela antes de lanzar. Lleva copiadas las decisiones del ticket y pide el ID de la regla, pero nunca un ID de ejemplo, porque el revisor lo copiaría.

Anota la tabla `nombre de corrida → agentId` (en Pi, `task_id`), con nombres `<revisor>-r<i>` (`revisor-diseno-r1`, `revisor-capa-a-r1`…). **No leas reportes parciales:** espera a que terminen todas.

**Un lanzamiento que el host rechaza por su límite de concurrencia no es una corrida cortada.** En Codex dice «agent thread limit reached». Ante ese rechazo, espera a que termine una corrida en marcha, ciérrala (en Codex, `close_agent` libera su lugar), relanza la rechazada y dile al usuario que la revisión va por tandas. La regla es la misma en todos los hosts, y sus límites están en `references/hosts.md`.

## 5. El modo 0

Sin corridas ni sí: anuncia el modo y los archivos que vas a leer, y lee tú los docs o notas cambiados. Revisa su estructura: encabezados, enlaces y rutas que citan, que lo que afirman exista, y que no queden restos de borrador. Muestra el resultado y escribe el recibo (paso 8) con `--modo 0`, sin `--reviewer`, y `--verificacion "lectura estructural: <resultado>"`.

## 6. El rescate

Cuando terminan todas las corridas:

```bash
python3 "<S>/rescatar.py" --sesion "<carpeta subagents de esta sesión>" --destino "<ticket>/revision/<fecha>-<modo>/corridas" --corrida <nombre>=<agentId> --corrida … --costo
```

`--sesion` es `~/.claude/projects/<proyecto>/<sesión>/subagents` (si no la encuentras, lee `references/rescate.md`). **En Pi**, antes de rescatar, lee «Pi» en `references/hosts.md`:

```bash
python3 "<S>/rescatar.py" --host pi --destino "<ticket>/revision/<fecha>-<modo>/corridas" --corrida <nombre>=<task_id> --corrida … --costo
```

- Deja cada reporte en `corridas/<nombre>.md` y, con `--costo`, `corridas/costo.json`, el que lee `--ultimo-costo`. Si avisa que le falta algo, lee `references/rescate.md`.
- Sale con 0, con 1 si alguna corrida no dejó reporte (`FAIL …`) o con 2 por error de uso. **Una corrida cortada se informa y no se reintenta en silencio:** dile al usuario cuál falló y pregunta si se relanza solo esa o se sigue sin ella; si se sigue, la frecuencia es sobre las que sí hay (k/2), y se dice. Un rechazo por el límite de concurrencia no es una corrida cortada (paso 4).
- Una herramienta «NO auditada» (`Bash`, `PowerShell`) en un revisor que solo debería leer se informa: no es una corrida limpia.

## 7. La consolidación

La hace el orquestador, en prosa, con los reportes de `corridas/`, en `consolidado.md` de la carpeta de la revisión. La regla de un hallazgo es la que citó el revisor: con ID, la regla es su ID; con `sin ID`, lo que viola.

- **El rendimiento** va en la primera línea de `consolidado.md`, siempre con esta forma:

  ```
  Rendimiento: <n> hallazgos · acuerdo 3/3 <a>, 2/3 <b>, 1/3 <c> · CRITICAL <x>, WARNING <y>, SUGGESTION <z> · destino: pendiente
  ```

  `<n>` cuenta cada hallazgo una vez, de diseño y de capa, sin los conflictos ni lo que va aparte. El acuerdo va solo en `completo`, con los hallazgos de diseño por su frecuencia; en `rapido` y en un rechequeo, la línea no lo trae. El destino queda `pendiente` hasta el recibo.
- **En `rapido` y en todo rechequeo**, cada hallazgo va una vez, con su ubicación y su regla.
- **En `completo`**, los de diseño van con su frecuencia entre las tres corridas (3/3, 2/3, 1/3), unidos por ubicación y regla (con ID, la regla es su ID), y los de 1/3, marcados **«a confirmar»**. Hay varianza, y varias corridas no suman aciertos: protegen de la corrida mala y muestran los **conflictos**, la misma pieza con veredictos opuestos («quitar» contra «consumido»), que van en **«Decide el líder o revisa a mano»**, con la evidencia de cada lado y **sin votar**, porque la decisión es de dominio.
- La severidad de diseño y la de capa van separadas: cada hallazgo, con la de su revisor, sin promediar. Lo que diseño derivó a una capa y lo que esa capa devolvió va aparte, y lo que nadie toma se marca **«sin dueño»** y se lo lleva el usuario.
- No son hallazgos, y van aparte: las preguntas para el líder, lo que ya estaba antes del cambio, los límites que declaró cada revisor y lo que reabre una decisión del ticket sin ser `CRITICAL` (con la decisión que contradice, y fuera del lote de corrección). Un `CRITICAL` que la contradice sí es un hallazgo, y nombra la decisión.

## 8. Presentar y dejar el recibo

1. **Presenta** la consolidación: el usuario decide qué corrige. No corrijas ni lances otra revisión por tu cuenta (sección 9).
2. **Escribe el recibo** al cerrar la revisión, con los archivos revisados **explícitos**, nunca el working tree entero: `--archivo` es obligatorio y, con más de un `--repo`, va con ruta absoluta.

   ```bash
   python3 "<S>/recibo.py" --write --ticket "<ticket>" --repo <repo>#<base> [--repo …] --archivo <ruta absoluta> [--archivo …] --modo <0|rapido|completo> --fecha <AAAA-MM-DD> [--ronda <n>] --reviewer <agente> [--reviewer …] --verificacion "<comando>: <resultado>" [--verificacion …] --estado <limpio|con-hallazgos|pendiente> [--derivado "<hallazgo>=<destino>" …] [--bajada "<motivo>" --va-a-lider no]
   ```

   **Antes de usar `--bajada`, `--derivado` o `--ronda`, de reescribir un recibo, o si `recibo.py` sale con 1 o 2, lee `references/recibo.md`.** `<base>` es la base completa del triaje; `--fecha`, la de la carpeta (sin ella, la de hoy); `--reviewer`, los agentes que corrieron, y `--verificacion`, lo que se corrió de verdad. `--estado` es `limpio` sin hallazgos, `pendiente` si el usuario todavía no los resolvió y `con-hallazgos` si ya los corrigió o los descartó con su motivo; un `pendiente` resuelto sin tocar lo revisado se reescribe con `con-hallazgos`, y si se tocó, es un rechequeo (sección 9).

   **Completa el destino** en la línea de rendimiento de `consolidado.md` cuando el recibo queda `con-hallazgos` o `limpio`: `destino: corregidos <c>, derivados <d>, descartados <e>`. En un rechequeo, también el de la ronda anterior, donde lo que el rechequeo vio resuelto cuenta como corregido.

   Tapa los secretos con `tapar.py`: lee «Los secretos» en `references/recibo.md`.
3. **Antes de decir «listo» o «listo para commit», corre `--check`** con la carpeta de esta revisión:

   ```bash
   python3 "<S>/recibo.py" --check "<ticket>/revision/<fecha>-<modo>"
   ```

   Con 0, el recibo vale: di su estado y lo pendiente (un `pendiente` no se sella hasta reescribirlo con `con-hallazgos` o `limpio`). Con 1 y `NO vale … cambio el diff revisado`, la divergencia que nombra va a un rechequeo (sección 9), que pide su sí salvo que viniera aprobado con su lote: un recibo viejo no autoriza nada. Con 1 y `NO vale para el commit`, el índice no es lo revisado: sigue lo que propone el mensaje. Con 1 o 2, nunca «listo para commit».

## 9. El cierre: una corrección y un rechequeo

1. **Una sola corrección**, para que corregir no sea un bucle: el usuario elige de la consolidación qué se corrige, y eso es un lote. El mensaje que lo propone anuncia también el rechequeo y su costo, `1 + <capas>` corridas (una de `revisor-diseno` y una por capa rechequeada, también en `completo`; cero en modo `0`), con el último costo medido: aprobar el lote aprueba el rechequeo.
2. **Un rechequeo** cuando termina el lote: verifica los hallazgos anteriores y revisa solo lo que cambió. **Antes de armarlo, lee `references/rechequeo.md`.** Si el triaje de ahora da otra base o un modo más alto, es una revisión nueva de la unidad entera, que pide su sí; si los rechequeados tocan una capa que el lote no anunció, anuncia el costo nuevo y pide el sí. El prompt suma los hallazgos de la ronda anterior (ubicación, regla y severidad, del `consolidado.md`) y pide decir de cada uno si quedó resuelto.
3. **Lo que trae el rechequeo:** un `CRITICAL`, nuevo o anterior que sigue abierto, se corrige en esta unidad, como un lote nuevo con su rechequeo y esta misma regla. Lo que no es `CRITICAL` **se deriva** a otra tarea, otro ticket o el backlog: en el recibo con `--derivado "<hallazgo>=<destino>"` y en `## Seguimientos` del ticket, una línea por hallazgo (`<fecha>: <qué> → <destino>`), nunca en la tabla de Tareas. Con eso la revisión queda cerrada: el recibo del rechequeo es el de la unidad.

## Después de la revisión

El commit es del usuario, y en los repos del equipo, solo con una autorización puntual. **Después del commit de una unidad revisada, y antes de cualquier otro, sella su recibo** con la carpeta de su última ronda (la del rechequeo, si lo hubo), y muestra su línea:

```bash
python3 "<S>/recibo.py" --sellar "<ticket>/revision/<carpeta de la unidad>"
```

Con 1 no sella: muestra el motivo y no lo fuerces, porque un sello sobre lo no revisado lo sacaría del triaje siguiente. Con `pendiente`, reescríbelo con `con-hallazgos` o `limpio` y sella; con otro motivo, lee `references/recibo.md`. Con 2, muestra el mensaje.
