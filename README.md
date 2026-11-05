# odd-workspace-template

Marketplace de Claude Code con un solo plugin, **`odd-ws`**. El plugin convierte la carpeta de un proyecto en una **instancia**: un espacio de trabajo con agentes donde cada ticket tiene su carpeta y los hooks chequean cada edición contra las reglas de su capa. Los cambios grandes los escriben agentes con compuerta, y los revisores dejan un recibo atado al diff. Lo aprendido en un ticket sube a reglas y docs verificables. El principio es *Mecanismo > Memoria*: lo que se aprende se vuelve un chequeo, no un recordatorio.

**Versión actual:** `0.2.1`. Quedan en espera, hasta que haya un consumidor real, las bibliotecas de reglas para C# y Java, el fixture ciego de `eval-reviewers` y el juicio de las afirmaciones SQL.

| Si quieres… | Ve a |
|---|---|
| Usar el plugin en tu proyecto | [Camino rápido](#camino-rápido) |
| Saber qué hace cada comando | [Skills](#skills) |
| Entender por qué Claude frenó una edición o un comando | [Hooks](#hooks) |
| Escribir reglas para tu stack | [Capas y reglas propias](#capas-y-reglas-propias) |
| Modificar la plantilla misma | [Contribuir a la plantilla](#contribuir-a-la-plantilla) |

## Conceptos

| Término | Qué es |
|---|---|
| Instancia | La carpeta de tu proyecto con la metodología montada: `workspace.config.json`, su `CLAUDE.md`, sus agentes y sus reglas. La genera `/odd-ws:bootstrap`. |
| Ticket | Una carpeta por pedido, en `tickets/<id>-<slug>/`. Su `CLAUDE.md` guarda el objetivo, los criterios de aceptación, el alcance, el Paso 0 y la bitácora. |
| Repo de código | Donde vive el código. La instancia no lo contiene: lo referencia por su ruta en `workspace.local.json`. |
| Capa | Un tipo de código con convenciones propias (por ejemplo `sql` o `web`): sus extensiones, sus repos y su prefijo de reglas. |
| Paso 0 | Antes de escribir código: para cada pieza nueva, cuál es su hermano vigente (lo que ya resuelve algo parecido) y quién consume cada dato. |
| Writer | El agente `writer-<capa>`, que escribe los cambios grandes de una capa con archivos autorizados y una compuerta al terminar. |
| Revisores | Los agentes `revisor-<capa>` y `revisor-diseno`, que leen el diff antes del commit. |
| Recibo | `recibo.json`: ata la revisión al diff exacto que se revisó. Si el diff cambia, el recibo deja de valer. |
| No-negociables | Las reglas de una capa que Claude tiene que tener cargadas antes de su primera edición en esa capa (el «primer toque»). |
| Matriz de reglas | `.claude/reglas/matriz.csv`: cada convención aprendida, con su origen y su destino (un chequeo, una skill, un revisor…). |
| Graduar | Subir lo aprendido en un ticket a la capa durable: los docs del proyecto, el `CLAUDE.md` de la raíz o la matriz. Lo hace `/odd-ws:cerrar`. |

## Camino rápido

1. **Revisa los [requisitos de la máquina](#requisitos-de-la-máquina).**
2. **Registra el marketplace e instala el plugin** desde la carpeta del proyecto (puede estar vacía):

   ```text
   claude plugin marketplace add sebasgc0399/odd-workspace-template
   claude plugin install odd-ws@odd-workspace-template --scope project
   ```

3. **Abre `claude` en esa carpeta y corre `/odd-ws:bootstrap`.** Te entrevista (proyecto, repos y capas), te muestra el plan y solo escribe después de tu sí.
4. **Corre `/odd-ws:doctor`** y arregla lo que marque FALTA.
5. **Abre tu primer ticket** con `/odd-ws:abrir`.

Tres reglas de la instalación:

- **`--scope project` es obligatorio.** Sin él, `claude plugin install` instala a nivel usuario, y los hooks del plugin correrían en todos tus proyectos (P2 de `Doc/diseno.md`). En `/plugin install`, dentro de una sesión, elige la opción de instalar para todos los colaboradores del repositorio.
- **Cada ticket lleva su propio `.claude/settings.json`,** porque Claude Code lee ese archivo solo de la carpeta donde arranca la sesión. El bootstrap pone el `enabledPlugins` en la raíz y en la plantilla, y `/odd-ws:abrir` lo copia a cada ticket.
- **La sesión de un ticket se abre desde su carpeta, con cada repo de código agregado:** `claude --add-dir <ruta>`, una vez por cada repo o worktree de «Worktree y rama» en el `CLAUDE.md` del ticket. Sin eso, Claude Code pide permiso para leer o editar fuera de la carpeta del ticket.

### Requisitos de la máquina

Se desarrolla y se prueba en Windows.

| Herramienta | Para qué | ¿Obligatoria? |
|---|---|---|
| Claude Code ≥ 2.1.284 | El plugin, sus skills y sus hooks | Sí |
| Python 3, invocable como `python` | Todos los hooks y scripts del plugin | Sí |
| Git | Los repos y los worktrees. En Windows, Git for Windows: su `sh` corre los hooks de git | Sí |
| Un `credential.helper` de git | Empujar a GitHub (en Windows, Git Credential Manager) | Solo para empujar |
| PowerShell | El análisis AST de la biblioteca T-SQL (ScriptDom). Sin él, esos chequeos no encuentran nada | Solo con una capa SQL |
| gentle-ai ≥ 4.2.0, engram ≥ 3.5.0 y jq | El entorno del mantenedor. Ningún script del plugin los invoca | No |

> **El doctor y las herramientas opcionales.** Hoy `/odd-ws:doctor` marca FALTA si no encuentra gentle-ai, engram, jq o un `credential.helper`, y sale con código 1. Si no los usas, esas filas quedan en FALTA y el resto funciona igual. Si tienes gentle-ai, el doctor también pide que su revisión nativa (`rdd`) esté apagada: la instancia trae revisores propios.

## El ciclo de un ticket

1. **Abrir** con `/odd-ws:abrir`: crea la carpeta del ticket desde la plantilla y llena el objetivo, los criterios de aceptación y el alcance.
2. **Entender antes de codear.** Si el pedido trae un «X **o** Y», fija con quien lo pide qué casos entran.
3. **Planear con ODD:** Explorar → Implementar → Revisar, anunciando la etapa.
4. **Paso 0 de diseño,** escrito en el ticket antes del código.
5. **Escribir.** Un ajuste mínimo se hace en la sesión; algo más grande en una capa va al agente `writer-<capa>`.
6. **Revisar antes del commit** con `/odd-ws:revisar`.
7. **Cerrar** con `/odd-ws:cerrar`: gradúa lo aprendido y deja el commit de cierre.

Ejemplo de la sesión de un ticket que toca un repo:

```text
cd tickets/T-123-mi-cambio
claude --add-dir D:/code/mi-repo
```

## Skills

| Comando | Cuándo | Dónde | Quién la dispara |
|---|---|---|---|
| `/odd-ws:bootstrap` | Para crear una instancia o completar una que ya existe | La carpeta del proyecto | Solo tú |
| `/odd-ws:doctor` | Al estrenar máquina, después de clonar o cuando un hook no corre | Un clon de la plantilla o una instancia | Tú o Claude |
| `/odd-ws:abrir` | Al empezar un ticket | La instancia: su raíz o un ticket | Solo tú |
| `/odd-ws:revisar` | Antes de cada commit, o antes de mostrarle un cambio a un líder | La carpeta del ticket | Tú o Claude, siempre con tu sí |
| `/odd-ws:cerrar` | Al terminar un ticket | La instancia: su raíz o el ticket | Solo tú |
| `/odd-ws:conocimiento` | Para revisar la salud de los docs del proyecto | La raíz de la instancia | Solo tú |
| `/odd-ws:eval-reviewers` | Para medir un revisor contra la revisión real de un líder | La instancia | Tú o Claude |

«Solo tú» quiere decir que Claude no la dispara por su cuenta: la escribes tú en el chat. Todas las skills que escriben algo te muestran antes lo que van a hacer y esperan tu sí.

### `/odd-ws:bootstrap`

- **Entrevista,** de a una pregunta: el nombre del proyecto, los repos con su ruta absoluta y las capas, cada una con sus extensiones, sus repos y su prefijo de reglas. `diseno` es un nombre reservado.
- **Ensayo primero.** Arma una spec JSON (ejemplo: `plugin/plantillas/bootstrap.ejemplo.json`), corre `bootstrap.py --ensayo` y te muestra el plan. Solo con tu sí escribe.
- **Nunca pisa un archivo.** En una instancia que ya existe, completa lo que falta a partir de su `workspace.config.json`, que no cambia.
- **Termina con el doctor.** No hace `git add` ni `commit`: el primer commit es tuyo.

### `/odd-ws:doctor`

- Muestra una tabla OK / FALTA / AVISO / NO APLICA, con el arreglo de cada ítem. Sale con 0 si no hay ninguna FALTA y con 1 si hay alguna.
- Arregla de a un ítem, solo con tu sí (`doctor.py --arreglar <id>`).
- Sin el plugin instalado, se corre desde un clon: `python plugin/scripts/doctor.py`.

### `/odd-ws:abrir`

- **Le pasas el pedido:** el ítem del tracker (si Claude tiene una herramienta MCP para leerlo) o el texto pegado.
- **La carpeta.** Propone el id y el slug, y con tu sí crea la carpeta desde la plantilla (`ticket.py`, con ensayo antes).
- **El `CLAUDE.md` del ticket.** Lo llena con el objetivo, los criterios, el alcance, las preguntas por fijar con el líder, los docs de dominio que toca y los candidatos a graduar de tickets hermanos. Te lo muestra antes de escribirlo.
- **El worktree o la rama.** Te sugiere el comando, con `--no-track`, y lo corres tú.
- **Al final** te dice cómo abrir la sesión del ticket con `--add-dir`.

### `/odd-ws:revisar`

- **El triaje.** Corre `triaje.py` sobre el diff contra la base, que es el merge-base con `origin/HEAD` o la que le pases con `--repo RUTA#BASE`. Propone un modo:
  - `sin-cambios`: no hay nada que revisar;
  - `0`: solo docs o notas, con lectura estructural y sin revisores;
  - `rapido`: todas las señales en negativo;
  - `completo`: alguna señal positiva, o un cambio que va a un líder.
- **El costo.** Anuncia cuántas corridas cuesta y espera tu sí. En `completo`, `revisor-diseno` corre 3 veces, más el `revisor-<capa>` de cada capa tocada.
- **Lo que deja** en `tickets/<id>-<slug>/revision/<fecha>-<modo>/`: los diffs de entrada, los reportes, `consolidado.md` y `recibo.json`.
- **No commitea.**

### `/odd-ws:cerrar`

- **El triaje de los aprendizajes.** Lee el ticket y decide qué pasa con cada aprendizaje: lo general sube a los docs de dominio, al `CLAUDE.md` de la raíz o a una fila de la matriz; lo de un solo ticket se queda en su carpeta.
- **Antes de escribir** te muestra la propuesta completa y espera tu sí.
- **El modo sombra.** Si hay un caso sin puntuar, frena y te manda primero a `/odd-ws:eval-reviewers`.
- **Al final** te guía para desarmar el worktree y deja el commit de cierre (`chore(<id>): cierre e hidratación`), con un segundo sí.

### `/odd-ws:conocimiento`

- **Solo lee.** Su salida es un triaje para ti: no edita docs por su cuenta.
- **Necesita la sección `knowledge`** de `workspace.config.json`, que dice dónde viven los docs y su índice. El bootstrap solo la pregunta si la mencionas.
- **Tiene tres niveles,** que no se suman en un mismo conteo:

  | Nivel | Comando | Qué da |
  |---|---|---|
  | 1, mecánico | `conocimiento.py` | **Hallazgos:** links y anclas rotos, docs sin indexar, el índice pasado de su tope, la frescura y las cifras en los headings |
  | 2, afirmaciones | `conocimiento.py --claims` | **Veredictos** sobre las afirmaciones verificables contra el código de los repos |
  | 3, cruce | `conocimiento.py --cruce` | **Candidatos,** no hallazgos: entidades repetidas en muchos docs y cifras del mismo sustantivo que difieren |

### `/odd-ws:eval-reviewers`

- **A ciegas.** Mide un revisor contra la revisión real de un líder: rescata los reportes, audita qué leyó cada corrida y las puntúa, con una ratificación a ciegas.
- **Antes de correr** te muestra cuántas corridas son y su costo, y espera tu sí. El fixture ciego hoy se arma a mano.
- **El modo sombra.** Antes de la revisión real de un líder, congela las corridas en `revision/<fecha>-sombra/` y las commitea, para compararlas después.

## Hooks

Corren solos, sin que los invoques. Cuando uno frena algo, el mensaje dice por qué.

| Cuándo | Qué hace |
|---|---|
| Al abrir o retomar una sesión | Valida la config de la instancia y avisa si está rota. Tras `/compact` o `/clear`, reinicia las marcas de primer toque. |
| Al leer por primera vez un archivo de una capa | Inyecta sus no-negociables como contexto. |
| Antes de editar un archivo de una capa | Si los no-negociables no se cargaron, bloquea la primera edición y los inyecta. El reintento pasa. |
| Después de editar | Corre las reglas de la capa (`.claude/reglas/verificar_<capa>.py`): un `bloqueo` frena y un `aviso` llega como contexto. |
| Antes de un comando de shell | `guard_comandos.py` bloquea force push, `reset --hard`, `clean -f` y borrados recursivos fuera del scratch. En un repo con `agent_readonly: true`, pregunta antes de cualquier git que no sea de lectura. |
| Dentro de un `writer-<capa>` | `writer_guard.py` bloquea el git de escritura y las escrituras por shell sobre los repos y el taller de la capa, y guarda una foto de cada archivo en su primer toque. |
| Al terminar un `writer-<capa>` | `writer_stop.py` compara las líneas reales contra la foto, corre los chequeos de la capa y exige el bloque `## Resultado`. Bloquea una sola vez. |

## Qué genera el bootstrap

| Ruta en la instancia | Para qué |
|---|---|
| `workspace.config.json` | La config versionada: los repos (con `agent_readonly` opcional), las capas y, opcional, `knowledge` |
| `workspace.local.json` | Lo de tu máquina: la ruta de cada repo y `plugin_root`. Va en `.gitignore` |
| `CLAUDE.md` | El índice y la metodología de la instancia |
| `tickets/_plantilla/` | La plantilla de cada ticket, con su `.claude/settings.json` |
| `.claude/agents/` | `writer-<capa>.md`, `revisor-<capa>.md` y `revisor-diseno.md` |
| `.claude/skills/` | `capa-<capa>/SKILL.md` (las convenciones de cada capa) y `criterios/SKILL.md` |
| `.claude/reglas/` | `matriz.csv` (solo el encabezado), `evidencia.md`, `verificar_<capa>.py` (vacío) y `verificar_<capa>.tests.py` |
| `.githooks/pre-commit` | Corre las pruebas de las reglas de cada capa (`reglas.py --test`) |
| `.claude/settings.json` | El `enabledPlugins` de la raíz |
| `.gitignore`, `git init` y `core.hooksPath` | Para que el pre-commit corra desde el primer commit |

No los genera: la carpeta de docs de `knowledge`, el estado de ejecución (`.claude/estado/`, ignorado por git) ni las carpetas `revision/` de cada ticket.

## Capas y reglas propias

La plantilla trae una sola biblioteca de reglas, la de T-SQL (`odd_ws.tsql`). Para cualquier otro stack, las reglas de cada capa se escriben en la instancia.

- **El módulo.** Cada capa tiene su `.claude/reglas/verificar_<capa>.py`. El bootstrap lo deja vacío: `REGLAS = ()` y `verificar(ctx)` devuelve `[]`. Su `verificar_<capa>.tests.py` valida el contrato.
- **El contrato.** `verificar(ctx)` recibe el archivo editado (`ruta`, `texto`, `agregadas`, `hunks`, `es_nuevo`, entre otros). Devuelve una lista de hallazgos `{id, modo, severidad, linea, fragmento, mensaje}`, con `modo` en `bloqueo` o `aviso`. El detalle está en `Doc/diseno.md`.
- **Correrlas sin Claude.** `reglas.py` está en `scripts/` del plugin; su ruta queda en `plugin_root` de `workspace.local.json`.

  ```text
  python "<plugin_root>/scripts/reglas.py" --test [CAPA]
  python "<plugin_root>/scripts/reglas.py" --calibrar CAPA CARPETA [--detalle]
  ```

  `--test` corre las pruebas de las reglas. `--calibrar` pasa las reglas sobre una carpeta de código real y cuenta cuántas veces salta cada una. Las dos aceptan `--raiz <instancia>`.
- **La matriz.** Cada convención nueva entra como una fila de `.claude/reglas/matriz.csv`, con su id `<prefijo>-NN`, su origen, su tipo, su destino y su severidad. `/odd-ws:cerrar` la agrega por ti.
- **Agregar una capa a una instancia que ya existe.** Suma la capa a `workspace.config.json` y la ruta de sus repos a `workspace.local.json`, a mano. Después vuelve a correr `/odd-ws:bootstrap`: genera lo que falta de la capa nueva sin tocar lo que ya existe.

## Actualizar el plugin

La versión está fijada en `plugin.json` y la actualización automática viene apagada, así que se actualiza a mano, entre tickets:

```text
claude plugin marketplace update odd-workspace-template
claude plugin update odd-ws@odd-workspace-template
```

Después, `/plugin` dentro de una sesión debe mostrar la versión nueva, con la pestaña de errores vacía.

## Contribuir a la plantilla

### Puesta en marcha del clon

1. Clona el repo (si no eres colaborador, trabaja en un fork y propón el cambio con un pull request) y, desde el clon, corre `python plugin/scripts/doctor.py`. Muestra qué falta, con el arreglo de cada ítem.
2. `python plugin/scripts/doctor.py --arreglar repo-hooks` (o `git config core.hooksPath .githooks`). **Obligatorio:** git no instala hooks solo, y un clon sin este paso no corre ningún barrido.
3. Crea la lista negra en `~/.odd-ws/denylist.txt` (o apunta `ODD_WS_DENYLIST` a otra ruta). Va **fuera** del repo y no viaja con él. Sin ella, el barrido bloquea todos los commits: falla cerrado.
4. Vuelve a correr el doctor hasta que solo queden en FALTA las [herramientas opcionales](#requisitos-de-la-máquina).

### Los hooks del repo

| Hook | Qué corre |
|---|---|
| `.githooks/pre-commit` | La autoprueba del barrido, el barrido de lo stageado y todas las suites `*.tests.py` (unos 4 minutos) |
| `.githooks/commit-msg` | El barrido del mensaje del commit |
| `.githooks/pre-push` | El barrido de todo lo que se empuja (contenido, rutas y mensajes) y después el chequeo de la entrega (`tools/entrega.py`) |

### Las pruebas

No hay pytest: cada `*.tests.py` es un script que se corre solo.

```text
python plugin/scripts/<script>.tests.py
for suite in $(git ls-files -- '*.tests.py'); do python "$suite"; done
```

### Una entrega

1. Sube `version` en `plugin/.claude-plugin/plugin.json` y commitea.
2. Etiqueta con `claude plugin tag ./plugin --dry-run` y después sin `--dry-run`. Crea `odd-ws--v<versión>` y exige el árbol limpio.
3. Empuja `main` y la etiqueta juntas:

   ```text
   git push origin <sha>:refs/heads/main refs/tags/odd-ws--v<versión>
   ```

   El pre-push frena un push a `main` que cambie `plugin/` si el commit no lleva la etiqueta de la versión de su `plugin.json`.

### Dónde está el porqué

| Doc | Qué tiene |
|---|---|
| `Doc/diseno.md` | Todas las decisiones de diseño y la especificación de cada script |
| `odd/tasks/<feature>.md` | La bitácora de cada feature: los requisitos, las tareas con su commit y el log de decisiones |

### Estructura del repo

| Ruta | Qué es |
|---|---|
| `.claude-plugin/marketplace.json` | El catálogo: un solo plugin, `odd-ws` |
| `plugin/.claude-plugin/plugin.json` | El nombre y la versión del plugin |
| `plugin/skills/` | Las 7 skills |
| `plugin/hooks/hooks.json` | Los hooks del plugin |
| `plugin/scripts/` | Los scripts de las skills y los hooks, cada uno con su `*.tests.py`. `odd_ws/` es la biblioteca que importan los hooks y las reglas de la instancia |
| `plugin/plantillas/` | Lo que el bootstrap copia a la instancia: `CLAUDE.md`, `ticket.md`, `capa.md`, `criterios.md`, `revisor.md`, `revisor-diseno.md`, `writer.md`, `reglas/`, `pre-commit` y `bootstrap.ejemplo.json` |
| `tools/` | `barrido.py` (el barrido de confidencialidad) y `entrega.py` (el chequeo de la entrega). Son del repo, no viajan con el plugin |
| `.githooks/` | Los hooks de git del repo |

## Licencia

[MIT](LICENSE).
