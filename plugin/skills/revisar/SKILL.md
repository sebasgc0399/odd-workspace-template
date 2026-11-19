---
name: revisar
description: Revisar un cambio de un ticket con los revisores de la instancia (el de diseño y el de cada capa tocada). Usar antes del commit de un cambio, o antes de mostrárselo a un líder. Hace el triaje, anuncia el modo y su costo, espera el sí, lanza las corridas, consolida los reportes y deja un recibo atado al diff.
---

# /odd-ws:revisar

Orquesta la revisión de un cambio con los agentes de `.claude/agents/`: `revisor-diseno` (entre capas) y el `revisor-<capa>` de cada capa que toca el cambio. Los revisores solo leen: **el orquestador arma la entrada, lanza las corridas, rescata los reportes, los consolida y escribe el recibo.** Ningún revisor edita código ni commitea, y esta skill tampoco: ni `git add` ni `git commit`.

En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts` y `<ticket>` es la carpeta del ticket. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

## Qué se sabe de estos revisores

- **Hay varianza.** Dos corridas del mismo revisor sobre el mismo código pueden opinar distinto sobre la misma pieza.
- **Varias corridas no suman aciertos sobre la mejor.** Sirven para protegerse de la corrida mala y para **mostrar los conflictos**: una corrida dice X y otra lo contrario. Un conflicto no se resuelve votando: es una señal de que la decisión es de dominio, y la toma el líder o se revisa a mano.

## Reglas duras

1. **Nunca se lanza una revisión sin el sí del usuario**, aunque el modelo haya invocado la skill por su cuenta. La revisión cuesta corridas; el sí va después de anunciar el modo y su costo (paso 2). Hay dos excepciones, y en las dos el modo se anuncia igual:
   - el modo `0`, que cuesta cero corridas, corre sin pedir el sí;
   - el rechequeo que anunció, con su costo, el mensaje del lote de corrección: aprobar ese lote aprueba también el rechequeo (sección 9).
2. **Nunca dos revisiones a la vez.** Las corridas de una revisión se lanzan juntas; la siguiente revisión espera a que esta termine.
3. **No hay bucle automático de corrección.** El usuario decide qué corrige, y una revisión se cierra con una corrección y un rechequeo (sección 9). Cualquier otra revisión después de corregir es un pedido nuevo y vuelve a pedir el sí.
4. **Solo git de lectura en los repos del equipo.** No se cambia de rama, no se toca el índice (un archivo sin trackear entra al diff con `--no-index`, nunca con `git add -N`) y no se plantan archivos en esos repos: todo lo que escribe esta skill va dentro de la carpeta del ticket.
5. **Todas las corridas de una revisión usan el mismo modelo.** No pases `model` a ninguna o pasale el mismo alias a todas, y no fijes IDs de modelo.
6. **Esta skill no congela nada.** Si el usuario quiere que la revisión quede como caso del modo sombra, mandalo a `/odd-ws:eval-reviewers`.

## 1. Las entradas

- **El ticket.** Su carpeta es `tickets/<id>-<slug>/`. Si el usuario solo dio el id, buscala con el glob recursivo `tickets/**/<id>-*/CLAUDE.md` (la herramienta Glob lista archivos, no carpetas): un ticket archivado puede estar en una subcarpeta. Si el glob encuentra más de una carpeta, listalas y preguntale al usuario cuál es; nunca elijas una por tu cuenta, porque con ids que llevan guion la carpeta de un ticket puede coincidir también con el glob de otro id.
- **Los repos tocados**, con su rama o worktree:
  - la ruta de cada repo sale de `workspace.local.json` (`repos.<repo>.path`);
  - el worktree y la rama del ticket están en su `CLAUDE.md`, en «Worktree y rama». Si el ticket trabaja en un worktree, ese es el `--repo`, no el árbol principal;
  - si no está claro qué repos toca el cambio, preguntá.
- **La base** de cada repo es la misma que usan el triaje y el recibo, y sale en este orden:
  1. la explícita, si pasás `--repo <ruta>#<base>`;
  2. con `--ticket`, el commit más nuevo que sellaron los recibos del ticket (`recibo.py --sellar`, después del commit de una unidad revisada), si es ancestro de `HEAD` y más nuevo que el merge-base con `origin/HEAD`;
  3. si no, el merge-base con `origin/HEAD`.

  Así una unidad ya revisada y commiteada no se vuelve a revisar. Los scripts no hacen `git fetch`: si el `origin/HEAD` local puede estar atrasado, proponé el `git fetch` de ese repo y corrélo solo con el sí del usuario, porque habla con el remoto. Si un repo no tiene `origin/HEAD`, los scripts salen con 2 y piden `git remote set-head origin -a` o la base explícita con `--repo <ruta>#<base>`. Un repo sin ningún remoto, con la base explícita, cuenta sus consumidores en esa base; con remoto y sin `origin/HEAD`, la señal de consumidores queda inválida.
- **Los archivos del ticket.** El triaje lista todo lo que cambió contra la base. Si entre esos archivos hay algunos que no son del ticket (por ejemplo, archivos del ambiente local que están modificados a propósito), separalos con el usuario: no entran a la entrada ni al recibo.

## 2. El triaje y el sí

1. Corré el triaje, que solo lee:

   ```bash
   python3 "<S>/triaje.py" --ticket "<ticket>" --repo <repo o worktree>[#<base>] [--repo …] [--taller <archivo del taller del ticket>] [--clon <repo>] [--raiz <raíz de la instancia>] [--json]
   ```

   - Se corre desde la carpeta de la instancia o con `--raiz`. Con `--json` salen los hashes completos de la base, que se usan en el recibo.
   - Pasá siempre `--ticket`: un `--repo` sin `#<base>` parte del último commit sellado del ticket. La línea `repo … (base …, <origen>)` dice de dónde salió (`sellada en revision/…`, `merge-base con origin/HEAD` o `explícita`), y en `--json` van `base_origen` y `base_recibo`. Mostrala junto al modo.
   - Si el ticket tiene una unidad revisada que el usuario ya commiteó y nadie selló, sellala antes del triaje (ver «Después de la revisión»). Si `--sellar` sale con 1, seguí: el triaje usa el sello anterior o el merge-base.
   - Sale con 0, o con 2 si falta un `--repo` o un `--taller`, o si hay un error de uso o de entorno (por ejemplo, un repo sin `origin/HEAD`): mostrá el mensaje tal cual y corregilo.
2. **El modo lo propone el triaje y no se elige a ojo.** Las señales solo escalan:

   | Modo | Sale cuando |
   |---|---|
   | `sin-cambios` | no hay cambios contra la base: no hay nada que revisar, se avisa y se termina |
   | `0` | solo docs o notas del taller: lectura estructural, sin revisores |
   | `rapido` | todas las señales en negativo y el instrumento verificado |
   | `completo` | cualquier señal positiva o inválida |

   Un falso positivo solo cuesta una revisión de más; un falso negativo cuesta un hallazgo que llega al líder. Ante la duda, subí. **Nunca bajes el modo por tu cuenta:** la bajada de un escalón la pide el usuario, con su motivo (paso 6).
3. **Preguntá si el cambio va a un líder antes del commit.** El triaje no lo puede detectar: lo declara en «el triaje NO detecta». Si va a un líder, el modo es `completo` aunque todo haya salido en negativo.
4. Si el triaje nombra archivos «fuera de la unidad» (generados sin trackear, como `__pycache__/` o `*.pyc`), no entran a la revisión ni al recibo; decíselo al usuario en una línea, porque puede borrarlos o ignorarlos en su repo. Mostrá también la lista «el triaje NO detecta» y aplicá tu criterio a lo que toque este cambio (consumidores fuera de los repos declarados, la forma de un resultado que consume otra capa, constantes compartidas).
5. **Anunciá, antes de lanzar nada:**
   - el modo y las señales que lo decidieron (o «va a un líder»);
   - las capas tocadas, que salen de la columna `[capa]` del triaje. Un archivo `sin capa` no tiene revisor de capa: lo lee el de diseño, y se avisa;
   - el costo, en corridas, sin inventar cifras: `modo 0` son 0 corridas; `rapido` son `1 + <capas tocadas>`; `completo` son `3 + <capas tocadas>`. Cada una cuesta lo que una corrida de revisor sobre este diff.
   - salvo en modo `0`, el último costo medido, porque las corridas no dicen cuánto cuesta cada una. Corré `python3 "<S>/rescatar.py" --ultimo-costo "<ticket>"` y citá su línea tal cual: es el `costo.json` más nuevo del ticket o, si el ticket no tiene, el de la instancia (las carpetas `-sombra` no cuentan). Es una referencia, no una estimación: no la multipliques ni la ajustes a este diff. Si sale con 1, no hay ningún costo medido: anunciá solo las corridas.
   - **la bajada, solo cuando cabe:** si el modo es `completo`, el usuario dijo que el cambio no va a un líder (paso 3) y todas las positivas son límites del instrumento, decí en una línea que puede bajarlo un escalón, a `rapido`, si deja el motivo. Un límite del instrumento es una señal `invalida`, o la de `capas` cuando en `--json` `sin_capa.unico_motivo_de_capas` es `true`; cualquier otra `positiva` es un riesgo real. No la recomiendes: decide el usuario.
6. **Esperá el sí del usuario.** Sin sí explícito, no se lanza ni se escribe nada. Las dos excepciones de la regla 1:
   - **modo `0`:** no hay nada que lanzar. Anunciá el modo y los archivos que vas a leer, y seguí con la sección 5 sin esperar;
   - **un rechequeo** que el usuario aprobó junto con su lote de corrección: seguí sin volver a pedirlo.

   **Si el usuario baja el modo**, su pedido es el sí de `rapido`, con su motivo. Es un escalón, de `completo` a `rapido`: nunca a `0` si hay código, nunca si el cambio va a un líder y nunca si el triaje vio un riesgo real. Si pide bajar sin haber respondido lo del líder, preguntáselo antes. La carpeta va con el modo bajado (`<fecha>-rapido`), su `entrada/triaje.json` es el que propuso `completo`, y el recibo lleva `--bajada` (paso 8).

## 3. La entrada de los revisores

**La carpeta de la revisión** es `<ticket>/revision/<fecha>-<modo>/`, con la fecha de hoy (`AAAA-MM-DD`) fijada para toda la revisión. **Si ya existe** (otra ronda del mismo día y modo, por ejemplo el rechequeo después de una corrección), no la pises ni la muevas: esta ronda va en `<fecha>-<modo>-2`, o en el siguiente número libre, y en todo lo que sigue `<fecha>-<modo>` quiere decir esa carpeta con su número. El recibo de esa ronda se escribe con `--ronda <n>`.

Con el sí, creá `<ticket>/revision/<fecha>-<modo>/entrada/` y guardá ahí un diff por repo, `<repo>.diff`, solo con los archivos del ticket, y el triaje en `triaje.json`:

```bash
git -C <repo> diff --no-color <base> -- <archivo> [<archivo>…] > "<entrada>/<repo>.diff"
git -C <repo> diff --no-color --no-index -- /dev/null <archivo nuevo sin trackear> >> "<entrada>/<repo>.diff"
python3 "<S>/triaje.py" <los argumentos del paso 2> --json > "<entrada>/triaje.json"
```

- La primera línea cubre los archivos trackeados (commiteados o no); la segunda se repite por cada archivo nuevo sin trackear y sale con 1, que es lo normal en `--no-index`.
- `<base>` es la base completa del triaje.
- Si el diff sale vacío, pará: algo de la lista no cuadra.
- `triaje.json` es el triaje del paso 2 con `--json`, con los mismos argumentos. De ahí saca el rescate los motivos del modo para el costo de la revisión (paso 6).

## 4. Las corridas

Cada corrida es un `Agent` en segundo plano (`run_in_background`), todas en el **mismo mensaje**. **En Pi (gentle-shell)**, cada corrida es un `subagent_run` con `mode: "background"`, uno por corrida y todos en el mismo mensaje, y cada lanzamiento devuelve su `task_id` («as task <id>»). Cuando una corrida termina, gentle-shell te entrega una copia de su reporte que puede venir cortada (a 16 KB por defecto): no la uses, porque el reporte entero sale del rescate (paso 6). Si el agente no existe (por ejemplo, `revisor-diseno` en una instancia que se generó antes de que el plugin lo trajera), no lo reemplaces con otro: decile al usuario que complete la instancia con `/odd-ws:bootstrap`, y que si el agente es nuevo en esta sesión hace falta reabrirla.

| Modo | Corridas |
|---|---|
| `0` | ninguna: lectura estructural (paso 5) |
| `rapido` | `revisor-diseno` ×1, más `revisor-<capa>` ×1 por cada capa tocada |
| `completo` | `revisor-diseno` ×3, con los archivos en un orden distinto en cada corrida (con un solo archivo el orden es el mismo y las 3 son muestras independientes: no lo anuncies como «en otro orden»), más `revisor-<capa>` ×1 por cada capa tocada |

**Un rechequeo** (sección 9) corre `revisor-diseno` ×1 más `revisor-<capa>` ×1 por cada capa de los rechequeados, también en modo `completo`: sin orden barajado ni frecuencias.

**Orden barajado (modo `completo`).** La primera corrida de diseño recibe los archivos en el orden del triaje; la segunda, en el orden inverso; la tercera, en un orden barajado. El orden va escrito en el prompt como lectura sugerida.

**La forma del prompt:**

```
Revisá <el diseño | el código de la capa <capa>> del ticket <id> (<título>) antes del commit.

Entrada:
- Diff de <repo>: <ruta de <repo>.diff> (base <commit>, rama <rama>). El código completo está en <ruta del repo o worktree>: leé ahí el código, sus hermanos y sus consumidores.
- (una línea por cada repo tocado)
- Carpeta del ticket: <ruta>. Leé su CLAUDE.md del disco, aunque ya tengas uno cargado: el que cargaste al arrancar puede ser anterior al Paso 0. No leas su carpeta revision/: trae reportes de otras revisiones.
- <solo capa> Archivos de tu capa: <lista>.
- <solo diseño, modo completo> Orden de lectura sugerido: <lista>.

Ya decidido en el ticket (## Decisiones), no lo vuelvas a plantear como hallazgo; si un CRITICAL lo contradice, reportalo y nombrá la decisión:
- <una línea por decisión, copiada de ## Decisiones, o «ninguna»>

Entregá el reporte con tu contrato. En cada hallazgo, justo después de la severidad, citá el ID de la regla de la matriz que rompe, o `sin ID` si no viene de una regla con ID:
[SEVERIDAD] <ID de la regla | sin ID> ruta:línea — qué viola — cómo debe quedar
```

- **Las decisiones van copiadas en el prompt**, no solo en el `CLAUDE.md` del ticket: en un ticket real, tres corridas de un `completo` pidieron quitar algo que el usuario ya había aprobado.
- **El ID de la regla también va en el prompt**, y no en las plantillas de los revisores: un cambio de plantilla no llega a los revisores ya generados. `revisor-diseno` solo ve los IDs de `criterios`, así que `sin ID` es una respuesta normal. Nunca pongas un ID de ejemplo en el prompt: el revisor lo copiaría.

- Anotá la tabla `nombre de corrida → agentId`, con nombres `<revisor>-r<i>` (`revisor-diseno-r1`, `revisor-capa-a-r1`…). Los `agentId` los devuelve cada lanzamiento; en Pi, la tabla lleva el `task_id`.
- **No leas reportes parciales:** esperá a que terminen todas. Nunca lances otra revisión mientras tanto.
- **Un lanzamiento que el host rechaza por su límite de concurrencia no es una corrida cortada.** Codex responde «agent thread limit reached» cuando se pasa de `agents.max_threads`, que Gentle AI pone en 4, o, en V2, de `max_concurrent_threads_per_session - 1`, que es 3, y un `completo` con 2 capas o más lanza 5 corridas o más. Ante ese rechazo, esperá a que termine una corrida en marcha, cerrala (en Codex, `close_agent` libera su lugar), relanzá la rechazada y decile al usuario que la revisión va por tandas. La regla es la misma en todos los hosts.

## 5. El modo 0

No hay corridas, así que no se pide el sí: se anuncia el modo y se sigue. Leé vos los archivos de docs o notas cambiados y revisá su estructura: encabezados, enlaces y rutas que citan, que lo que afirman exista, y que no queden restos de borrador. Mostrá el resultado, escribí el recibo (paso 8) con `--modo 0`, sin `--reviewer`, y dejá la lectura en `--verificacion "lectura estructural: <resultado>"`.

## 6. El rescate

Cuando terminan todas las corridas:

```bash
python3 "<S>/rescatar.py" --sesion "<carpeta subagents de esta sesión>" --destino "<ticket>/revision/<fecha>-<modo>/corridas" --corrida <nombre>=<agentId> --corrida … --costo
```

- `--sesion` es la carpeta `subagents` de esta sesión, bajo `~/.claude/projects/<proyecto>/<sesión>/`. También acepta la carpeta de la sesión que la contiene. Si no la encontrás, buscala con Glob: `~/.claude/projects/*/*/subagents/agent-<agentId>.jsonl`.
- Por cada corrida escribe `<nombre>.md` (el reporte), `.prompt.txt`, `.lecturas.json`, con el costo de la corrida en `costo`, y, si hubo comandos, `.comandos.json`. El reporte sale del `SubagentHandback` o, si no hubo, del último texto.
- Con `--costo` escribe también `corridas/costo.json`: el modo, los motivos de `entrada/triaje.json`, cada corrida con su costo (también la cortada, que se pagó igual), las líneas de los diffs de `entrada/`, el costo de esta sesión desde el último `triaje.py` antes de lanzar las corridas (`orquestador`, leído de `<sesión>.jsonl`, junto a la carpeta de la sesión) y si las corridas corrieron en serie (`en_serie`). Es lo que lee `--ultimo-costo` en el anuncio (paso 2). Un rescate posterior en la misma carpeta, por ejemplo el de una corrida relanzada, suma sus corridas sin pisar las anteriores. Si falta `triaje.json` o los diffs, lo avisa y deja ese campo en `null`; si no encuentra el tramo de esta sesión, deja `orquestador` en `null`, también con aviso, y no es una falla del rescate. `--costo` va solo con el `--destino` de una revisión (`<ticket>/revision/<fecha>-<modo>[-<n>]/corridas`); con otro sale con 2 sin escribir nada.
- Sale con 0 si todas están bien, con 1 si alguna corrida no dejó reporte (`FAIL … sin SubagentHandback` o `no existe agent-…`) y con 2 por error de uso.
- **En Pi**, el rescate lee la tarea que gentle-shell guarda por corrida, con el reporte entero, y escribe los mismos archivos:

  ```bash
  python3 "<S>/rescatar.py" --host pi --destino "<ticket>/revision/<fecha>-<modo>/corridas" --corrida <nombre>=<task_id> --corrida … --costo
  ```

  - La tarea es `<agentHome>/gentle-agents/tasks/<task_id>.json`, y `agentHome` es `GENTLE_PI_AGENT_HOME`, si no `PI_CODING_AGENT_DIR`, si no `~/.pi/agent`. gentle-shell define las dos variables en su sesión, así que corré el rescate desde ahí; `--sesion <carpeta>` las reemplaza con la carpeta de tareas o con el `agentHome`. Fuera de una sesión de gentle-shell, su home por defecto es `~/.gentle-shell/agent`: pasá `--sesion ~/.gentle-shell/agent`.
  - Las lecturas son `read`, `grep` y `find`; cualquier otra herramienta sale como «NO auditada». En `costo.json`, `orquestador` queda en `null` con un aviso, porque solo se mide en Claude Code.
  - Una tarea que no terminó en `completed` es una corrida cortada: `FAIL … tarea <task_id> en estado <estado>, sin reporte`. Si el estado es `running` y la corrida ya avisó que terminó, gentle-shell todavía no guardó la tarea: volvé a rescatar esa corrida un momento después antes de darla por cortada.
  - **Si el rescate de una corrida falla** (`FAIL … no existe <task_id>.json`, `no es una tarea de gentle-shell`, o la carpeta de tareas no existe), pedí su reporte con `subagent_result` y su `task_id`, que lo devuelve entero, y guardalo en `corridas/<nombre>.md`. Decile al usuario que esa corrida salió de `subagent_result`, sin lecturas ni costo.
- **Una corrida cortada se informa y no se reintenta en silencio.** Decile al usuario cuál falló y preguntá: relanzar solo esa o seguir sin ella. Si se sigue sin ella, la frecuencia se cuenta sobre las corridas que sí hay (k/2) y se dice.
- Un lanzamiento que el host rechazó por su límite de concurrencia no es una corrida cortada: se relanzó por tandas (paso 4) y se rescata con las demás.
- Una herramienta «NO auditada» en la salida (`Bash`, `PowerShell`) en un revisor que solo debería leer se informa: no es una corrida limpia.

## 7. La consolidación

La hace el orquestador, en prosa, leyendo los reportes de `corridas/`. La regla de un hallazgo es la que citó el revisor: con ID, la regla es su ID; con `sin ID`, lo que viola.

- **El rendimiento** va en la primera línea de `consolidado.md`, siempre con esta forma:

  ```
  Rendimiento: <n> hallazgos · acuerdo 3/3 <a>, 2/3 <b>, 1/3 <c> · CRITICAL <x>, WARNING <y>, SUGGESTION <z> · destino: pendiente
  ```

  - `<n>` cuenta cada hallazgo de la consolidación una vez, de diseño y de capa. No cuenta los conflictos, las preguntas para el líder, los límites, lo que ya estaba antes del cambio ni lo que reabre una decisión sin ser `CRITICAL`.
  - El acuerdo va solo en `completo`, y cuenta los hallazgos de diseño por su frecuencia. En `rapido` y en un rechequeo, la línea no lo trae.
  - La severidad de cada hallazgo es la que le dio su revisor.
  - El destino queda `pendiente` hasta el recibo (paso 8).

  Es lo que mide qué rinde cada corrida: con esos datos se decide si un `completo` puede bajar a 2 corridas de diseño.
- **Modo `rapido`, y todo rechequeo:** junta los reportes de diseño y de capa. Cada hallazgo, una vez, con su ubicación y su regla.
- **Modo `completo`:**
  - **Hallazgos con su frecuencia** entre las tres corridas de diseño (3/3, 2/3, 1/3), unidos por ubicación y regla (con ID, la regla es su ID). Los que salieron 1/3 van marcados **«a confirmar»**.
  - **Conflictos:** la misma pieza con veredictos opuestos entre corridas (por ejemplo, «quitar» contra «consumido»). Van en su propia sección, **«Decide el líder o revisa a mano»**, con la evidencia de cada lado y **sin votar**.
- **En los dos modos:**
  - **La severidad de diseño y la de capa van separadas.** Cada hallazgo conserva la del revisor que lo dijo (`CRITICAL`, `WARNING`, `SUGGESTION`); no se promedian ni se unifican.
  - **Lo derivado:** lo que diseño pasó a un revisor de capa y lo que ese revisor devolvió. Una derivación que nadie toma (diseño se la pasa a la capa y la capa se la devuelve) se marca **«sin dueño»** y se la lleva el usuario.
  - **Preguntas para el líder**, aparte: las que cualquier corrida dejó como pregunta, no como hallazgo.
  - Lo que ya estaba antes del cambio y los límites que declaró cada revisor van aparte; un límite declarado no es un hallazgo.
  - **Lo que reabre una decisión del ticket** y no es `CRITICAL` tampoco es un hallazgo: va aparte, con la decisión que contradice, y no entra al lote de corrección. Un `CRITICAL` que la contradice sí es un hallazgo, y nombra la decisión.
- Guardá la consolidación en `<ticket>/revision/<fecha>-<modo>/consolidado.md`.

## 8. Presentar y dejar el recibo

1. **Presentá** la consolidación al usuario. Él decide qué corrige. No corrijas por tu cuenta ni lances otra revisión: la corrección y su rechequeo siguen la sección 9.
2. **Escribí el recibo** al cerrar la revisión. Lleva la lista **explícita** de los archivos revisados por repo, nunca el working tree entero: `--archivo` es obligatorio y, con más de un `--repo`, cada uno es una ruta absoluta.

   ```bash
   python3 "<S>/recibo.py" --write --ticket "<ticket>" --repo <repo>#<base> [--repo …] --archivo <ruta absoluta> [--archivo …] --modo <0|rapido|completo> --fecha <AAAA-MM-DD> [--ronda <n>] --reviewer <agente> [--reviewer …] --verificacion "<comando>: <resultado>" [--verificacion …] --estado <limpio|con-hallazgos|pendiente> [--derivado "<hallazgo>=<destino>" …] [--bajada "<motivo>" --va-a-lider no]
   ```

   - `--fecha` es la misma de la carpeta de la revisión: sin ella toma el día de hoy, y puede no coincidir.
   - `--bajada "<motivo>" --va-a-lider no` va solo cuando el usuario bajó el modo (sección 2, paso 6), con su motivo y su respuesta sobre el líder. `recibo.py` lo valida contra `entrada/triaje.json` de la carpeta de la revisión: el triaje tiene que proponer `completo`, `--modo` tiene que ser `rapido` y no puede haber un riesgo real. Ese triaje tiene que ser de este diff: los mismos repos que el recibo, con la misma base. Si `recibo.py` dice que `no es de este diff`, volvé a guardar el triaje con `--json` y los mismos argumentos que el recibo. Guarda en el recibo `bajada` con `de`, `a`, `motivo` y `va_a_lider`. Cualquier otro par de modos, un motivo vacío, `--va-a-lider si` o sin `--bajada`, un triaje que falta o no se lee, o un riesgo real es un error de uso: sale con 2 sin escribir nada.
   - `--derivado` anota un hallazgo que no se corrige en esta unidad y va a otra tarea, otro ticket o el backlog (sección 9). Es repetible, y el destino es lo que va después del último `=`. Uno sin `=`, o con un lado vacío, es un error de uso.
   - `--ronda <n>` va solo desde la segunda ronda del mismo día y modo, con el número de su carpeta. `--check` toma la ronda más alta, o la de `--recibo`.
   - `<base>` es la base completa del triaje, para que el recibo cubra el mismo diff que se revisó.
   - Los `--reviewer` son los agentes que corrieron (cada nombre una vez). `--estado` es `limpio` si no hubo hallazgos, `pendiente` si los hubo y el usuario todavía no los resolvió, o `con-hallazgos` si los hubo y ya los resolvió (corregidos, o descartados con su motivo). Cuando el usuario resuelve los de un recibo `pendiente`, volvé a escribirlo con `con-hallazgos` y los mismos argumentos; si era un rechequeo, también con su `--previo`, porque sin él el recibo pierde lo heredado y después no se puede sellar. `--verificacion` anota lo que se corrió de verdad y su resultado.
   - **Completá el destino** en la línea de rendimiento de `consolidado.md` cuando escribís el recibo con `con-hallazgos` o `limpio`, también al reescribir uno `pendiente`: `destino: corregidos <c>, derivados <d>, descartados <e>`. Los derivados son los que van con `--derivado`, y los descartados, los que el usuario descartó con su motivo. En un rechequeo, completá también el de la ronda anterior: lo que el rechequeo vio resuelto cuenta como corregido. Con `pendiente`, el destino sigue `pendiente`.
   - Escribe `revision/<fecha>-<modo>[-<n>]/recibo.json`, con una entrada por repo (base, hash del diff por archivo, archivos, modo, revisores, verificación y estado). Sale con 0, o con 2 si falta el ticket, un repo, un `--archivo` o el `--modo`.
   - Si el recibo ya existía, se pisa entero: pasá todos los `--repo` en una sola llamada.
3. **Antes de decir «listo» o «listo para commit», corré `--check`:**

   ```bash
   python3 "<S>/recibo.py" --check "<ticket>/revision/<fecha>-<modo>"
   ```

   - Pasá la carpeta de esta revisión. Si pasás la del ticket, toma el recibo más reciente, y a igual fecha el de modo `completo`, que puede no ser el de esta revisión; en ese caso filtrá con `--modo <m>` o apuntá con `--recibo <ruta>`.
   - **Exit 0:** el recibo vale, no cambió un byte de lo revisado.
   - **Exit 1:** cambió el diff revisado y el recibo no vale. Re-revisá **la divergencia** que nombra (repo y archivos) con un rechequeo (sección 9), que pide su sí salvo que el usuario lo haya aprobado con su lote de corrección. Un recibo viejo no autoriza nada.
   - **Exit 2:** error de uso o de entorno (no hay recibo, el repo ya no existe, `--modo` contradice al recibo). Mostrá el mensaje y no digas «listo».
4. **Qué decir.** Con exit 0, el estado del recibo y lo pendiente del usuario. Con 1 o 2, nunca «listo para commit».

## 9. El cierre: una corrección y un rechequeo

Una revisión se cierra así, para que corregir no se vuelva un bucle ni cueste una revisión entera por vuelta. En un ticket real, la re-revisión después de una corrección volvió a revisar la unidad entera, al mismo costo que la primera, y no se podía sellar una parcial; los hallazgos que quedaron para después terminaron dentro de la tabla de Tareas, y la rompieron.

1. **Una sola corrección.** Con la consolidación, el usuario elige qué se corrige, y eso es un lote. El mensaje que propone el lote anuncia también el rechequeo y su costo en corridas (abajo), con el último costo medido como en el paso 2: si el usuario aprueba el lote, aprueba el rechequeo.
2. **Un rechequeo** cuando termina el lote. Verifica los hallazgos anteriores y revisa solo lo que cambió desde la ronda anterior:
   - **Qué entra.** Los rechequeados son los archivos que nombra `recibo.py --check "<carpeta de la ronda anterior>"` cuando sale con 1 (los que cambiaron), más los que el triaje lista y el recibo anterior no tiene (los que sumó la corrección, como un test nuevo). Si `--check` sale con 0 y la corrección no sumó archivos, no hay nada que rechequear. Un archivo sumado nunca se salta: sin su rechequeo queda sin revisar y `--sellar` rechaza el commit que lo trae.
   - **La base** es la del recibo anterior, y el triaje con `--ticket` da esa misma mientras la unidad no se selle. **El modo** es el de la ronda anterior, y la carpeta es la ronda siguiente (`<fecha>-<modo>-<n>`). Si el triaje de ahora da otra base o propone un modo más alto, no es un rechequeo: es una revisión nueva de la unidad entera, que pide su sí.
   - **Después de una bajada** (el recibo anterior trae `bajada`), el rechequeo se mide contra el modo bajado: sigue en `rapido`, y que el triaje vuelva a proponer `completo` no es un modo más alto. Un riesgo real nuevo sí lo es, y la revisión nueva va en `completo`. El recibo del rechequeo hereda la bajada sin volver a pasarla, y `recibo.py` valida el `triaje.json` de la entrada de esta ronda: sin él, o con un riesgo real, sale con 2 sin escribir nada.
   - **Las corridas** son una de `revisor-diseno` más una por cada capa de los archivos rechequeados, `1 + <capas>`, tanto en `rapido` como en `completo`, sobre un diff que trae solo esos archivos. En modo `0` son cero. El rechequeo verifica una corrección acotada y no repite las tres corridas de `completo`: en un ticket real, dos rechequeos de una corrida, con los hallazgos anteriores en el prompt, cerraron bien. Si los rechequeados tocan una capa que el mensaje del lote no anunció, el costo cambió: anunciá el nuevo, con las corridas y el último costo medido, y pedí el sí.
   - **La entrada** es el diff de los rechequeados contra la base, con su `triaje.json` (paso 3). El prompt suma los hallazgos de la ronda anterior, con su ubicación, su regla y su severidad, copiados del `consolidado.md`, y pide decir de cada uno si quedó resuelto. La regla de no leer `revision/` sigue.
   - **El recibo** hereda lo que no cambió:

     ```bash
     python3 "<S>/recibo.py" --write --ticket "<ticket>" --repo <repo>#<base> [--repo …] --archivo <rechequeado> [--archivo …] --previo "<ticket>/revision/<carpeta de la ronda anterior>" --modo <modo> --fecha <AAAA-MM-DD> --ronda <n> --reviewer <agente> [--reviewer …] --verificacion "<comando>: <resultado>" [--verificacion …] --estado <limpio|con-hallazgos|pendiente> [--derivado "<hallazgo>=<destino>" …]
     ```

     - `--archivo` lista solo lo rechequeado, y el recibo cubre la unidad entera: lo rechequeado, con su hash de ahora, y cada archivo del recibo anterior que no se pasó, que tiene que estar igual que entonces. Un repo del recibo anterior sin nada rechequeado no se pasa: se hereda entero. Un `--repo` sin `#<base>` toma la base del recibo anterior.
     - Un archivo nuevo de la unidad que la corrección quitó se pasa con `--archivo`: queda en `retirados`, fuera del recibo.
     - **Exit 1**, sin escribir nada: un archivo del recibo anterior cambió y no está en `--archivo` (rechequealo), o la base no es la del recibo anterior.
     - **Exit 2:** `--previo` no es un recibo de este ticket, o el rechequeo no queda después de él: tiene que ir en la misma fecha y modo con una `--ronda` más alta, o en una fecha posterior.
     - Con eso, `--check` y `--sellar` valen para la unidad entera.
3. **Lo que trae el rechequeo:**
   - un hallazgo `CRITICAL`, nuevo o uno anterior que sigue abierto, se corrige en esta unidad, como un lote nuevo con su rechequeo, y los dos siguen esta misma regla;
   - un hallazgo que no es `CRITICAL`, nuevo o uno anterior que sigue abierto, **se deriva**: no se corrige en esta unidad, sino que va a otra tarea, otro ticket o el backlog. Anotalo en el recibo con `--derivado "<hallazgo>=<destino>"` y en `## Seguimientos` del ticket, una línea por hallazgo (`<fecha>: <qué> → <destino>`), nunca en la tabla de Tareas;
   - con eso la revisión queda cerrada: el recibo del rechequeo es el de la unidad, y después del commit se sella.

## Después de la revisión

- El commit es del usuario. Esta skill no commitea nada, y en los repos del equipo nunca se commitea sin una autorización puntual.
- **Después del commit de una unidad revisada, sellá su recibo**, antes de cualquier otro commit, y mostrá su línea:

  ```bash
  python3 "<S>/recibo.py" --sellar "<ticket>/revision/<carpeta de la unidad>"
  ```

  - Por qué: anota en el recibo el commit que guarda lo revisado, y el triaje de la unidad siguiente parte de ese commit en vez del merge-base. Sin sello, vuelve a contar lo ya revisado (en un ticket real, 83 archivos en vez de los 21 de la unidad nueva).
  - Pasá la carpeta del recibo de la unidad: la de su última ronda, la del rechequeo si lo hubo. Con la carpeta del ticket toma el recibo más nuevo por fecha, modo y ronda, que puede no ser el de esta unidad (por ejemplo, una unidad en modo `0` revisada el mismo día después de una en `rapido`). Sellar de nuevo sin mover `HEAD` no cambia nada.
  - **Exit 0:** `recibo sellado: <recibo> (<commit> en <n> repo(s))`.
  - **Exit 1:** no sella y no toca el recibo: cambió el diff revisado, hay archivos revisados sin commitear («commitea primero lo revisado»), o `HEAD` trae cambios fuera de lo revisado (por ejemplo, un commit de otra unidad). Mostrá el motivo; no lo fuerces, porque un sello sobre lo no revisado lo dejaría fuera del triaje siguiente.
  - **Exit 2:** error de uso o de entorno. Mostrá el mensaje.
- Si el modo fue `completo` y el cambio va a un líder, y el usuario quiere dejar la revisión como caso del modo sombra, `/odd-ws:eval-reviewers`. Ahí se congela, se puntúa y se ratifica; esta skill no toca ninguna de esas etapas.

## Scripts

| Script | Para qué | Salidas |
|---|---|---|
| `triaje.py` | propone el modo con las señales del diff | 0 ok · 2 error de uso o de entorno |
| `rescatar.py` | reporte, prompt, lecturas y costo de cada corrida desde el `.jsonl` del subagente o, con `--host pi`, desde la tarea que guarda gentle-shell; `--costo` escribe el `costo.json` de la revisión y `--ultimo-costo` imprime el último costo medido | 0 ok · 1 corrida sin reporte, o ningún costo medido con `--ultimo-costo` · 2 error |
| `recibo.py` | `--write` escribe el recibo, con `--previo` el de un rechequeo, que hereda lo que no cambió, y con `--bajada` la bajada de un escalón que pidió el usuario; `--check` lo compara con el diff actual; `--sellar` anota el commit que guarda lo revisado | 0 escrito, vale o sellado · 1 el diff cambió, no se puede sellar o el rechequeo no puede heredar · 2 error de uso o de entorno |
