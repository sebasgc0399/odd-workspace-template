# Usar odd-ws

Esta guía es para quien ya instaló el plugin y lo usa en su proyecto: los conceptos, lo que necesita la máquina, el ciclo de un ticket y qué hace cada skill. La instalación en tres pasos está en el [README](../README.md#instalación), y cómo comparte un equipo una instancia, en [Trabajar en equipo](equipo.md).

## Conceptos

| Término | Qué es |
|---|---|
| Instancia | Una carpeta aparte, al lado de tus repos de código, con la metodología montada: `workspace.config.json`, su `CLAUDE.md`, sus agentes y sus reglas, y su propio git. La genera `/odd-ws:bootstrap`. Si la creas dentro de un repo de código, pierde su git: el bootstrap no le hace `git init` ni configura el hook ni el primer commit. |
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

## Requisitos de la máquina

Se desarrolla en Windows, y las suites corren también en Linux y macOS (ver [Dónde funciona](../README.md#dónde-funciona)).

| Herramienta | Para qué | ¿Obligatoria? |
|---|---|---|
| Claude Code ≥ 2.1.284; se recomienda 2.1.295 o más | El plugin, sus skills y sus hooks. Desde la 2.1.295, un hook que no arranca bloquea la herramienta; antes la deja pasar | Sí, si la instancia declara `claude-code` |
| Codex CLI ≥ 0.144 (0.167 para los writers) | El plugin desde Codex | Solo si la instancia declara `codex` |
| Pi ≥ 1.5.0 | El plugin desde Pi; por debajo de 0.87.0 no hay compuerta para los writers | Solo si la instancia declara `pi` |
| gentle-shell (`npm i -g gentle-pi`) | Los subagentes de Pi: sin él, los writers no tienen compuerta | Solo para los writers en Pi |
| Python 3.7 o más, invocable como `python3` | Todos los hooks y scripts del plugin; el doctor necesita 3.11 o más para leer la config de Codex | Sí |
| Git | Los repos y los worktrees. En Windows, Git for Windows: su `sh` corre los hooks de git | Sí |
| Un `credential.helper` de git | Empujar a GitHub (en Windows, Git Credential Manager) | Solo para empujar |
| PowerShell | El análisis AST de la biblioteca T-SQL (ScriptDom). Sin él, esos chequeos no encuentran nada | Solo con una capa SQL |
| gentle-ai ≥ 4.2.0, engram ≥ 3.5.0 y jq | El entorno del mantenedor. Ningún script del plugin los invoca | No |

> **`python3` en Windows.** Lo crean el Python install manager de python.org y la Microsoft Store. El instalador clásico, winget y choco no lo crean, y entonces `python3` cae en el alias de la Store, que no corre: los hooks no arrancan. `/odd-ws:doctor` lo marca como FALTA en el ítem `python`, con el arreglo. En Windows, los hooks de Codex lanzan `python`, así que con `codex` declarado el doctor revisa también ese. Si en Windows usas solo Codex, los comandos de esta guía y de las skills van con `python` en lugar de `python3`.

> **El doctor y las herramientas opcionales.** Si no encuentra gentle-ai, engram, jq o un `credential.helper`, `/odd-ws:doctor` lo marca como AVISO con «opcional» en el detalle, y no falla por eso. Si tienes gentle-ai, el doctor también pide que su revisión nativa (`rdd`) esté apagada: la instancia trae revisores propios.

## Reglas de la instalación

- **`--scope project` es obligatorio.** Sin él, `claude plugin install` instala a nivel usuario, y los hooks del plugin correrían en todos tus proyectos (P2 de [`Doc/diseno.md`](diseno.md#4-diseño-del-plugin-p1p6)). En `/plugin install`, dentro de una sesión, elige la opción de instalar para todos los colaboradores del repositorio.
- **Cada ticket lleva su propio `.claude/settings.json`,** porque Claude Code lee ese archivo solo de la carpeta donde arranca la sesión. El bootstrap pone el `enabledPlugins` en la raíz y en la plantilla, y `/odd-ws:abrir` lo copia a cada ticket.
- **La sesión de un ticket se abre desde su carpeta, con cada repo de código agregado:** `claude --add-dir <ruta>`, una vez por cada repo o worktree de «Worktree y rama» en el `CLAUDE.md` del ticket. Sin eso, Claude Code pide permiso para leer o editar fuera de la carpeta del ticket.
- **O se trabaja desde la raíz**, que es lo cómodo en VS Code. La extensión usa la primera carpeta del `.code-workspace` como directorio principal y las demás como directorios adicionales, así que la raíz va primero y los repos o worktrees después. El ticket activo (el último que abriste, o el de `ticket.py --activar <id>`) llega como resumen al arrancar la sesión y después de cada `/compact`: objetivo, specs, tareas, seguimientos y las últimas entradas de la bitácora. Lo demás se lee en su `CLAUDE.md`.

## Usarlo desde Codex

La instancia sigue siendo la misma: `.claude/` es la fuente, y Codex recibe sus propios archivos generados. Una instancia puede trabajarse con los dos CLI a la vez.

- **Declarar Codex:** `"hosts": ["claude-code", "codex"]` en `workspace.config.json`. En una instancia nueva, el bootstrap te lo pregunta si mencionas Codex. En una que ya existe, agrega la clave y corre `/odd-ws:doctor` con `--arreglar codex-config` y `--arreglar codex-agentes`.
- **La confianza de los hooks:** abre `codex` en la raíz de la instancia, acepta confiar en la carpeta y confía los hooks de `odd-ws` cuando Codex muestre «Hooks need review», o desde `/hooks`. Codex no corre un hook sin confianza, y en la 0.167 la vuelve a pedir con cada actualización del plugin.
- **Las skills se invocan con `$`, no con `/`:** escribe `$` y elige, por ejemplo, `doctor (odd-ws)`, o explóralas con `/skills`. Lo que esta guía llama `/odd-ws:<skill>` es la forma de Claude Code.

Dos cosas a tener en cuenta:

- **Los writers necesitan Codex 0.167 o más.** En la 0.144 Codex no deja lanzar un subagente con su rol. Los guards y el primer toque funcionan desde la 0.144.
- **En Windows, un writer necesita poder escribir en los repos de tus capas.** Configura en Codex `sandbox_mode = "workspace-write"`, `[windows] sandbox = "unelevated"` y los repos como `writable_roots`, con su ruta absoluta. El detalle está en «Writers en Codex», dentro de [Empaquetado para Codex](diseno.md#empaquetado-para-codex-codex-pluginpluginjson-y-hookshookscodexjson-f1c) de `Doc/diseno.md`.

## Usarlo desde gentle-shell

gentle-shell es un agente de código sobre Pi que le suma subagentes. La instancia sigue siendo la misma: `.claude/` es la fuente, y Pi recibe sus propios archivos generados (`.pi/agents`).

- **Declarar Pi:** `"hosts": ["claude-code", "pi"]` en `workspace.config.json`. En una instancia que ya existe, agrega `"pi"` y corre `/odd-ws:doctor` con `--arreglar pi-agentes`.
- **Instalar:** `npm i -g gentle-pi`, y después `gentle-shell install git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v<versión>`, o la ruta de un clon tuyo. El paquete es la raíz del repositorio, no `plugin/`. Con la fuente git hace falta `npm` en el PATH. Por defecto, gentle-shell usa un home aislado (`~/.gentle-shell/agent`); con `gentle-shell --link install …` usa el de Pi (`~/.pi/agent`).
- **Abrir en la raíz de la instancia:** gentle-shell solo lee los agentes de `<carpeta donde lo abres>/.pi/agents`.
- **Confiar el proyecto (`/trust`):** sin confianza, Pi no carga las skills de la instancia ni los paquetes declarados en `.pi/settings.json`.
- **Las skills se invocan con `/skill:<nombre>`,** por ejemplo `/skill:doctor`. No tienen el prefijo `odd-ws:`.

A tener en cuenta:

- **Sin gentle-shell no hay writers con compuerta.** Pi a secas corre los guards y el primer toque, pero no tiene subagentes.
- **La tarea de un writer no puede empezar con `/`.** Pi la expandiría como comando y el writer perdería su marca, así que odd-ws bloquea el lanzamiento. Nombra la skill o la plantilla dentro del texto.
- **El writer corre en la raíz de la instancia.** Sus guards y su compuerta buscan la instancia desde la carpeta donde corre, así que odd-ws bloquea un writer que gentle-shell correría afuera o en otra instancia: con `repository_root` o `workspace_root` fuera de la instancia, o en un worktree dentro de ella que trae su propia config, o sin ellos si la instancia está en una subcarpeta de su repo git, porque gentle-shell lo correría en la raíz de ese repo. Relánzalo sin esos campos: el writer edita los archivos de tus repos por su ruta absoluta. En gentle-shell, la instancia tiene que ser la raíz de su repo git, o no estar en ninguno.
- **Los guards de comandos cubren las tres herramientas de shell de gentle-shell:** `bash`, `bash_background` y `monitor`, además de `powershell`. Las tres corren en el bash que tengas configurado en Pi (en Windows, Git Bash).
- **Los comandos de las skills usan `${CLAUDE_PLUGIN_ROOT}`, que Pi no define.** La extensión de odd-ws la define al cargarse, con la carpeta del plugin, si no estaba. Si algo la pisa, corre el doctor a mano desde la raíz de la instancia: `python3 <raíz del paquete>/plugin/scripts/doctor.py`. La raíz del paquete es tu clon o, con la fuente git, `~/.gentle-shell/agent/git/github.com/sebasgc0399/odd-workspace-template` (con `--link`, `~/.pi/agent/git/github.com/sebasgc0399/odd-workspace-template`).
- **Lo que odd-ws suma al resultado de una herramienta va después de una marca.** Pi junta en un solo texto todo el resultado, así que los no-negociables del primer toque y los motivos de un bloqueo llegan precedidos por la línea «[odd-ws] Lo que sigue no es parte del resultado de la herramienta: lo agrega odd-ws.».
- **`/skill:revisar` rescata los reportes enteros.** gentle-shell le entrega al agente una copia de cada reporte que puede venir cortada a 16 KB, así que la skill la ignora y los lee de la tarea que gentle-shell guarda en `<agentHome>/gentle-agents/tasks/<task_id>.json` (`rescatar.py --host pi`). Si una tarea no está, pide el reporte con `subagent_result` y te avisa. En Pi, el costo de la revisión no mide la sesión principal.
- **El doctor no ve los overlays de herramientas de gentle-shell.** Un overlay puede cambiar las herramientas de un agente al cargarlo, sin tocar su `.md`, así que `pi-agentes` puede salir OK aunque un revisor tenga una herramienta de más.

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
| `/odd-ws:bootstrap` | Para crear una instancia o completar una que ya existe | La carpeta de la instancia, aparte de tus repos | Solo tú |
| `/odd-ws:doctor` | Al estrenar máquina, después de clonar o cuando un hook no corre | Un clon de la plantilla o una instancia | Tú o Claude |
| `/odd-ws:abrir` | Al empezar un ticket | La instancia: su raíz o un ticket | Solo tú |
| `/odd-ws:revisar` | Antes de cada commit, o antes de mostrarle un cambio a un líder | La carpeta del ticket | Tú o Claude, con tu sí cuando cuesta corridas |
| `/odd-ws:cerrar` | Al terminar un ticket, o con `memorias` para graduar las memorias del proyecto | La instancia: su raíz o el ticket | Solo tú |
| `/odd-ws:conocimiento` | Para revisar la salud de los docs del proyecto | La raíz de la instancia | Solo tú |
| `/odd-ws:eval-reviewers` | Para medir un revisor contra la revisión real de un líder | La instancia | Tú o Claude |
| `/odd-ws:paquetes` | Para traer las reglas de una capa desde otro repo git, cambiarlas de etiqueta, sacarlas o verlas | La raíz de la instancia | Solo tú |

En Codex, cada skill se invoca con `$` (por ejemplo `$doctor`) o desde `/skills`; ver [Usarlo desde Codex](#usarlo-desde-codex).

«Solo tú» quiere decir que Claude no la dispara por su cuenta: la escribes tú en el chat. Todas las skills que escriben algo te muestran antes lo que van a hacer y esperan tu sí. Las únicas excepciones están en `/odd-ws:revisar`: el modo `0`, que no cuesta corridas; el rechequeo que aprobaste junto con su corrección; y el sello, que después de tu commit solo anota ese commit en el recibo.

### `/odd-ws:bootstrap`

- **Una sola parada.** Detecta los repos del `.code-workspace` de la carpeta y las extensiones de sus archivos (`bootstrap.py --proponer`), y te muestra la propuesta completa junto con el ensayo: el nombre del proyecto, los repos con su ruta, las capas (una por tecnología, con lo que cuesta cada una), el molde, el prefijo de los tickets y quién commitea, cada término explicado en una línea. Te hace una sola pregunta: si se aplica así o qué cambia. `diseno` es un nombre reservado.
- **Ensayo primero.** Arma una spec JSON (ejemplo: `plugin/plantillas/bootstrap.ejemplo.json`), corre `bootstrap.py --ensayo` y te muestra el plan agrupado por capa, con aparte las líneas que piden atención. Solo con tu sí escribe.
- **Nunca pisa un archivo.** En una instancia que ya existe, completa lo que falta a partir de su `workspace.config.json`, que no cambia.
- **Los CLI de la instancia.** La clave `hosts` de `workspace.config.json` dice en qué CLI se trabaja: `"hosts": ["claude-code", "codex"]`. Es opcional, y sin ella la instancia es solo de Claude Code. Con `codex`, el bootstrap también genera `.codex/`. El bootstrap la pregunta solo si mencionas otro CLI.
- **El prefijo de los tickets.** Si no usas un tracker, la clave `tickets` fija el prefijo de los ids: `"tickets": {"prefix": "T"}`. Con ella, `/odd-ws:abrir` propone el siguiente id (`T-1`, `T-2`…) sin preguntarte. El bootstrap te pregunta si usas un tracker.
- **Hace el primer commit.** Solo con los archivos que creó, con el hook ya marcado como ejecutable, y nunca hace push. Si prefieres aprobar cada commit, pon `"ask_before_commit": true` en `workspace.config.json`: entonces no commitea y te dice qué hacer.
- **Termina con el doctor y el siguiente paso:** abrir tu primer ticket con `/odd-ws:abrir`. La matriz arranca vacía y se llena al cerrar tickets; para no arrancar de cero, `/odd-ws:cerrar memorias` y `/odd-ws:paquetes`. Si tu repo ya tiene reglas escritas (su `CLAUDE.md`, sus gotchas, sus docs), te propone que el primer ticket sea sembrarlas: leerlas, anotarlas en la bitácora con su archivo y su commit, y graduarlas con `/odd-ws:cerrar`.

Lo que deja en la instancia está en [Qué genera el bootstrap](#qué-genera-el-bootstrap).

### `/odd-ws:doctor`

- Muestra una tabla OK / FALTA / AVISO / NO APLICA, con el arreglo de cada ítem. Sale con 0 si no hay ninguna FALTA y con 1 si hay alguna.
- Arregla de a un ítem, solo con tu sí (`doctor.py --arreglar <id>`).
- **Las extensiones sin capa (`capas-cobertura`).** Te avisa qué extensiones versionadas de tus repos no cubre ninguna capa, porque un cambio en esos archivos lleva el triaje de `/odd-ws:revisar` a modo `completo`. Si son del mismo lenguaje que una capa (`.mjs` en una capa `ts`), súmalas a sus `extensions`. El mismo aviso lo repiten el triaje, cada vez que un archivo sin capa está entre sus motivos, y `/odd-ws:abrir`, cuando la instancia tiene extensiones versionadas sin capa.
- Revisa cada CLI solo si la instancia lo declara en `hosts` (sin la clave, Claude Code). Con `codex` suma la versión de Codex (0.144 o más), el plugin instalado y habilitado, la confianza de los hooks y del proyecto, `.codex/config.toml` y que cada `.codex/agents/<agente>.toml` sea el que sale de su `.md` (`codex-agentes`), además de `hooks-host`, que ningún hook lleve un `--host` desconocido, vacío o de otro host. No escribe en la carpeta de Codex, y no verifica que el hash de la confianza siga fresco.
- **Sumar Codex a una instancia que ya existe:** agrega `"codex"` a `hosts` y corre `doctor.py --arreglar codex-config` y `doctor.py --arreglar codex-agentes`. Los TOML salen de los `.md` de `.claude/agents`, con su `description` y sus bloques; uno editado a mano queda en AVISO y no se pisa.
- Sin el plugin instalado, se corre desde un clon: `python3 plugin/scripts/doctor.py`.

### `/odd-ws:abrir`

- **Le pasas el pedido:** el ítem del tracker (si Claude tiene una herramienta MCP para leerlo) o el texto pegado.
- **La carpeta.** Propone el id y el slug, y con tu sí crea la carpeta desde la plantilla (`ticket.py`, con ensayo antes). Sin tracker, el id es el siguiente consecutivo del prefijo de `tickets` (`ticket.py --siguiente`), contando también los tickets archivados, así que nunca repite un número.
- **El `CLAUDE.md` del ticket.** Lo llena con el objetivo, los criterios, el alcance, las preguntas por fijar con el líder, los docs de dominio que toca y los candidatos a graduar de tickets hermanos. Te lo muestra antes de escribirlo.
- **Si el ticket es grande**, suma sus Specs (tu pedido tal cual, numerado) y sus Tareas. Si usas el ODD de gentle-ai, ese ticket es su documento de feature: no se crea otro en `odd/tasks/`.
- **El worktree o la rama.** Te sugiere el comando, con `--no-track`, y lo corres tú. En un repo marcado como tuyo (`"own": true` en `workspace.config.json`), corre él mismo el `fetch` y crea el worktree; no commitea ni hace push ahí.
- **El ticket activo.** El ticket que abre queda como activo, y si retomas uno, lo marca con `ticket.py --activar <id>`. Si trabajas desde la raíz, un resumen de su `CLAUDE.md` llega al arrancar y después de cada `/compact`. Si la raíz tiene un `.code-workspace`, le suma el worktree como carpeta.
- **Las extensiones sin capa.** Al mostrar el ticket corre `ticket.py --cobertura`, la misma cuenta del ítem `capas-cobertura` del doctor. Si tus repos tienen extensiones versionadas sin capa, te lo dice junto a las capas afectadas: un cambio en esos archivos lleva la revisión a `completo` hasta que declares su capa.
- **Los enlaces del ticket.** Para revisarlos o depurarlos, `ticket.py --enlaces <id>` lista los enlaces del `CLAUDE.md` del ticket, cada uno con su ruta absoluta y si es archivo o carpeta. Los rotos y los que llevan esquema (`https:`, `mailto:`) salen aparte. También sirve con la ruta de cualquier `.md`, por ejemplo un `odd/tasks/<feature>.md`. Con `--copiar`, las rutas van además al portapapeles; si no hay con qué copiar, te avisa y la lista sale igual. No abre nada: en la terminal de VS Code, una ruta absoluta se abre con Ctrl+clic.
- **El commit del ticket.** Con el ticket escrito, lo commitea en la instancia (`chore(<id>): abre el ticket`) sin volver a preguntar, salvo `"ask_before_commit": true`. Así el ticket tiene historia desde el primer día. Nunca hace push.
- **Al final** te dice las dos formas de trabajar el ticket: desde su carpeta con `--add-dir`, o desde la raíz.

### `/odd-ws:revisar`

- **El triaje.** Corre `triaje.py --ticket` sobre el diff contra la base. La base es, en este orden: la que le pases con `--repo RUTA#BASE`; el último commit sellado del ticket; o el merge-base con `origin/HEAD`. La salida dice cuál usó. Propone un modo:
  - `sin-cambios`: no hay nada que revisar;
  - `0`: solo docs o notas, con lectura estructural y sin revisores;
  - `rapido`: todas las señales en negativo;
  - `completo`: alguna señal positiva, o un cambio que va a un líder.
- **El costo.** Anuncia cuántas corridas cuesta y espera tu sí. En `completo`, `revisor-diseno` corre 3 veces, más el `revisor-<capa>` de cada capa tocada; en un rechequeo, una sola vez. El modo `0` no cuesta corridas: te dice el modo y corre sin esperar tu sí.
- **El último costo medido.** Junto a las corridas, te cita cuánto costó la última revisión medida del ticket, o de la instancia si el ticket todavía no tiene ninguna: por corrida, en promedio, los turnos, el contexto final, la salida y la caché escrita y leída. Lo cita tal cual, sin ajustarlo a tu diff, y si esas corridas corrieron en serie, una detrás de otra, te lo dice. Sin ninguna revisión medida, te anuncia solo las corridas. El porqué: el número de tokens que muestra Claude Code por corrida es su contexto final, cerca de un tercio de lo que cuesta.
- **Bajar un escalón.** Si el triaje propone `completo` solo por límites del instrumento (una señal inválida o un archivo sin capa) y el cambio no va a un líder, el anuncio te dice que puedes bajarlo a `rapido` si dejas el motivo. Lo decides tú: el agente nunca baja el modo por su cuenta. Nunca se baja a `0` si hay código, ni un cambio que va a un líder, ni uno donde el triaje vio un riesgo real. El recibo guarda el motivo y tu respuesta sobre el líder (`--bajada "<motivo>" --va-a-lider no`), y el rechequeo de esa unidad sigue en `rapido` mientras no aparezca un riesgo real nuevo.
- **El rendimiento.** Cada hallazgo cita el ID de la regla que rompe, o `sin ID`, y `consolidado.md` abre con una línea que los cuenta: cuántos salieron, por acuerdo entre las tres corridas de diseño (solo en `completo`) y por severidad. Al escribir el recibo, la skill completa su destino: cuántos se corrigieron, se derivaron o se descartaron.
- **Lo que deja** en `tickets/<id>-<slug>/revision/<fecha>-<modo>/`: los diffs y el triaje de entrada, los reportes, el costo de cada corrida y de la revisión (`corridas/costo.json`, que en Claude Code suma lo que gastó la sesión principal desde el triaje y lo que le dejó en el contexto; en gentle-shell, el costo de cada corrida trae los turnos, la salida, la caché y los tiempos, sin el contexto), `consolidado.md` y `recibo.json`. Una segunda ronda del mismo día y modo va en `<fecha>-<modo>-2`, sin pisar la primera.
- **El cierre: una corrección y un rechequeo.** Tú eliges qué se corrige, y eso va en un solo lote. El mensaje que lo propone te anuncia también el rechequeo y su costo, así que con un solo sí apruebas los dos. El rechequeo verifica los hallazgos anteriores y revisa solo los archivos que cambiaron desde la ronda anterior y los que sumó la corrección, con una corrida del revisor de diseño y una por cada capa, también en `completo`. Su recibo (`recibo.py --write --previo <ronda anterior>`) hereda los archivos que no cambiaron, así que cubre la unidad entera y se puede sellar. El porqué: en un ticket real, la re-revisión después de una corrección volvió a revisar toda la unidad, al mismo costo que la primera, y una re-revisión parcial no se podía sellar.
- **Lo que aparece en el rechequeo.** Un hallazgo `CRITICAL` se corrige en la unidad. Uno que no es `CRITICAL` se deriva: va a otra tarea, otro ticket o el backlog, queda anotado en el recibo (`--derivado "<hallazgo>=<destino>"`) y en la sección `## Seguimientos` del ticket, que va justo después de las Tareas y queda también en un ticket chico. Antes, lo que quedaba para después terminaba metido en la tabla de Tareas, y la rompía.
- **Lo ya decidido.** Cada corrida recibe las decisiones del ticket (`## Decisiones`) y no las vuelve a plantear. Lo que reabre una sin ser `CRITICAL` queda aparte, fuera del lote de corrección.
- **El sello.** Cuando commiteas una unidad revisada, la skill corre `recibo.py --sellar` sobre el recibo de esa unidad, que anota en el recibo el commit donde quedó lo revisado. Así la revisión de la unidad siguiente parte de ese commit y no vuelve a revisar lo que ya revisó: sin sello, en un ticket real el triaje contó 83 archivos en vez de los 21 de la unidad nueva. No sella si cambió lo revisado, si falta commitearlo o si `HEAD` ya trae otra cosa, como un commit de otra unidad; por eso conviene sellar justo después del commit.
- **No commitea.**

### `/odd-ws:cerrar`

- **El triaje de los aprendizajes.** Lee el ticket y decide qué pasa con cada aprendizaje: lo general sube a los docs de dominio, al `CLAUDE.md` de la raíz o a una fila de la matriz; lo de un solo ticket se queda en su carpeta.
- **Antes de escribir** te muestra la propuesta completa y espera tu sí.
- **El modo sombra.** Si hay un caso sin puntuar, frena y te manda primero a `/odd-ws:eval-reviewers`.
- **Al final** hace el commit de cierre (`chore(<id>): cierre e hidratación`) sin volver a preguntar, porque tu sí a la propuesta ya lo cubría. Con `"ask_before_commit": true` en la config, te pide un segundo sí antes del commit. Nunca hace push.
- **El worktree.** En un repo marcado como tuyo, lo desarma él si está limpio y su rama ya está en `origin`; si no, te dice qué falta. En un repo del equipo, te da los comandos para que lo desarmes tú.
- **La entrega después del cierre.** Si cerraste antes de entregar, cuando la entrega queda hecha no se vuelve a cerrar: pasa el ticket a `listo`, anota la entrega en la bitácora, commitea (`chore(<id>): entrega`) y quita la marca de ticket activo. Si la entrega cambió código después de la revisión, ese cambio pasa antes por `/odd-ws:revisar`.
- **Las memorias sin triar.** Cierra con una línea: «N memorias sin triar: `/odd-ws:cerrar memorias`». No las tría ni frena el cierre.

#### El modo `memorias`

`/odd-ws:cerrar memorias` (en Codex, `$cerrar memorias`) no cierra ningún ticket: gradúa a la matriz las reglas que ya están en las memorias del proyecto. Reusa la propuesta con tu sí, la fila de la matriz con sus chequeos y el commit; salta lo que es de un ticket (los relojes, la bitácora, el modo sombra y el worktree). El porqué está en [Memorias](diseno.md#memorias-memoriaspy-y-cerrar-memorias), dentro de `Doc/diseno.md`.

- **Las fuentes.** La memoria en archivos de Claude Code, que lee `memorias.py`, y engram, si tu sesión lo tiene. Si `memorias.py` no encuentra el directorio, el modo te dice qué ruta probó y se detiene: nunca te dice «no hay memorias».
- **Las memorias de tus repos.** Lo que guardaste trabajando dentro de un repo vive en el proyecto de ese repo, no en el de la instancia. El modo las lee también, repo por repo (`memorias.py --repo <nombre>` y su proyecto en engram), y lo que gradúa de ahí queda en la matriz con el origen `memoria:<repo>.<slug>`.
- **Qué te propone.** De las memorias `feedback` (y las `project`, si las pides), las que están `nueva` o `cambiada` y suenan a regla. Por cada una ves su slug, la fila exacta de la matriz, con `memoria:<slug>` como origen, y el texto que va a su destino. Las `user` y las `reference` nunca entran.
- **La privacidad.** La fila, el destino y la evidencia parafrasean la regla: no copian la memoria ni nombran personas, y la propuesta te muestra los tres antes de escribirlos. El slug va en el origen, así que si el nombre del archivo no debe salir de tu máquina, renómbralo antes o déjalo como visto. La matriz viaja en el repo de tu instancia y ahí no corre ningún barrido: lo que apruebas es lo que queda escrito.
- **engram.** Solo con `scope: project` y `limit: 20` por consulta. Su cobertura sale como parcial, con cuántas consultas llegaron al tope de 20. El origen es `memoria:engram-<sync_id>` (por ejemplo, `memoria:engram-obs-d2a572e53ec05212`): el `sync_id` es el mismo en todas las máquinas que comparten las memorias, y el `id` numérico no, así que solo se usa si la observación no trae `sync_id`. Lo de engram no entra al registro local, así que puede volver a salir; lo que ya graduaste se reconoce por su fila.
- **En Codex,** la memoria en archivos de Claude Code no aplica: el modo dice «no disponible» y sigue con engram, si está.
- **Lo que no apruebas** queda en el registro local como `vista`, y lo que descartas, como `descartada`. No vuelven a salir mientras su `modified` no cambie; si cambia, vuelven como `cambiada`. El script solo compara `modified`: una edición a mano que no lo actualiza no la hace volver.

#### `memorias.py` y el registro local

`memorias.py` lista las memorias con su estado. Del que más pesa al que menos: `graduada` (una fila de la matriz la cita), `ilegible`, `cambiada`, `descartada`, `vista` y `nueva`. Sale con 0, o con 2 y la ruta que probó.

| Opción | Qué hace |
|---|---|
| `--memorias DIR` | El directorio de memoria. Sin ella, lo deriva de `autoMemoryDirectory` en los settings, de `CLAUDE_CODE_PROJECT_DIR_NAME` (con `CLAUDE_CONFIG_DIR`) o de `<config>/projects/<proyecto>/memory`, con `<proyecto>` sacado de la raíz del repo git |
| `--raiz RAIZ` | La raíz de la instancia; por defecto, la de la sesión |
| `--host claude-code\|codex` | El CLI cuya memoria se lee. Con `codex` sale `no disponible` |
| `--con-project` | Suma las memorias `project` a las `feedback` |
| `--json` | El informe en JSON, que es el que lee la skill |
| `--registro ARCHIVO` | El registro local; por defecto, `~/.odd-ws/memorias/<proyecto>.json` |
| `--registrar SLUG... --como vista\|descartada` | Anota esas memorias en el registro y después lista. Es la única escritura del script |

El registro vive fuera del repo, en tu máquina, con una entrada por memoria bajo la clave `<slug>@<modified>`:

```json
{
  "version": 1,
  "memorias": {
    "pruebas-sin-red@2026-01-15": {"slug": "pruebas-sin-red", "modified": "2026-01-15", "estado": "vista", "fecha": "2026-01-20"}
  }
}
```

**Para olvidar una entrada,** bórrala a mano de `memorias`, y el archivo tiene que seguir siendo un JSON con esa forma: si no, `memorias.py` sale con 2 y no lo pisa. Borrar el archivo entero olvida todo. La entrada de una memoria que ya no existe sigue contando en la línea `REGISTRO` hasta que la borres.

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

### `/odd-ws:paquetes`

- **Trae reglas de otro repo git,** fijadas a una etiqueta: `importar`, `actualizar`, `quitar` y `listar`. Las copia a `.claude/reglas/paquetes/<nombre>/` y las fija en `.claude/reglas/paquetes.json`.
- **Ensayo primero.** Te muestra el plan (en `actualizar`, qué archivos cambian) y solo con tu sí escribe. Nunca ejecuta código del paquete.
- **Lee el código antes del commit.** Lo copiado corre en tus hooks. La skill te ofrece el commit con las rutas exactas, con un segundo sí, y el pre-commit corre la suite del paquete.
- **La fuente,** mejor una URL: una ruta local solo sirve en tu máquina. Un repo privado se autentica antes con git; una URL con credenciales se rechaza.

Cómo se escribe un paquete, qué revisa el doctor y por qué funciona así: [Paquetes de reglas](capas-y-reglas.md#paquetes-de-reglas).

## Qué genera el bootstrap

| Ruta en la instancia | Para qué |
|---|---|
| `workspace.config.json` | La config versionada: los repos (con `agent_readonly` opcional), las capas y, opcionales, `knowledge` y `hosts` |
| `workspace.local.json` | Lo de tu máquina: la ruta de cada repo y `plugin_root`. Va en `.gitignore` |
| `CLAUDE.md` | El índice y la metodología de la instancia |
| `tickets/_plantilla/` | La plantilla de cada ticket, con su `.claude/settings.json` |
| `.claude/agents/` | `writer-<capa>.md`, `revisor-<capa>.md` y `revisor-diseno.md` |
| `.claude/skills/` | `capa-<capa>/SKILL.md` (las convenciones de cada capa) y `criterios/SKILL.md` |
| `.claude/reglas/` | `matriz.csv` (solo el encabezado), `evidencia.md`, `verificar_<capa>.py` (vacío) y `verificar_<capa>.tests.py` |
| `.githooks/pre-commit` | Corre las pruebas de las reglas de cada capa (`reglas.py --test`) |
| `.gitattributes` | Deja `.githooks/*` en LF, aunque Git convierta los saltos de línea (en Windows, `core.autocrlf` viene activado) |
| `.claude/settings.json` | El `enabledPlugins` de la raíz |
| `.gitignore`, `git init` y `core.hooksPath` | Para que el pre-commit corra desde el primer commit |
| `.codex/` | Solo si `hosts` declara `codex`: un `agents/<agente>.toml` por agente, derivado de su `.md` en `.claude/agents` (que es donde se edita), y `config.toml` para que Codex lea los `CLAUDE.md`. Codex los carga solo si el proyecto tiene su confianza. En una instancia que ya existía, el TOML de un agente que ya tenía su `.md` no lo crea el bootstrap: lo genera el doctor (`--arreglar codex-agentes`) |

No los genera: la carpeta de docs de `knowledge`, el estado de ejecución (`.claude/estado/`, ignorado por git) ni las carpetas `revision/` de cada ticket.

Las reglas de cada capa se escriben después, en la instancia: ver [Capas y reglas propias](capas-y-reglas.md).
