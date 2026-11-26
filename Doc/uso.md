# Usar odd-ws

Esta guía es para quien ya instaló el plugin y lo usa en su proyecto: los conceptos, lo que necesita la máquina, el ciclo de un ticket y qué hace cada skill. La instalación de cada CLI está en el [README](../README.md#instalación), y cómo comparte un equipo una instancia, en [Trabajar en equipo](equipo.md).

## Conceptos

| Término | Qué es |
|---|---|
| Instancia | Una carpeta aparte, al lado de tus repos de código, con la metodología montada: `workspace.config.json`, su `CLAUDE.md`, sus agentes y sus reglas, y su propio git. La genera `/odd-ws:bootstrap`. Si la creas en una subcarpeta de un repo de código, pierde su git: el bootstrap no le hace `git init` ni configura el hook ni el primer commit. Si la creas en la raíz de un repo de código, el bootstrap te pregunta antes y te recomienda una carpeta aparte: solo con tu sí la instancia queda en el git de ese repo, con su hook y el primer commit en su rama. |
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
| gentle-ai ≥ 4.2.0, engram ≥ 3.5.0 y jq | El entorno del mantenedor. Ningún hook los necesita: el doctor los consulta y, con tu sí, apaga la revisión nativa de gentle-ai (`rdd`) en el clon | No |

> **`python3` en Windows.** Lo crean el Python install manager de python.org y la Microsoft Store. El instalador clásico, winget y choco no lo crean, y entonces `python3` cae en el alias de la Store, que no corre: los hooks no arrancan. `/odd-ws:doctor` lo marca como FALTA en el ítem `python`, con el arreglo. En Windows, los hooks de Codex y los de Pi lanzan `python`, así que con `codex` o `pi` declarado el doctor revisa también ese. Si en Windows usas solo Codex o Pi, los comandos de esta guía y de las skills van con `python` en lugar de `python3`.

> **El doctor y las herramientas opcionales.** Si no encuentra gentle-ai, engram, jq o un `credential.helper`, `/odd-ws:doctor` lo marca como AVISO con «opcional» en el detalle, y no falla por eso. Si tienes gentle-ai, en una instancia completa el doctor te propone apagar su revisión nativa (`rdd`) solo en el clon de la instancia, porque ahí la instancia trae revisores propios; lo aplica con tu sí (`--arreglar rdd`), nunca solo. En el perfil `controles` es al revés: la revisión de gentle-ai apagada sale como AVISO. Fuera de una instancia, el ítem no aplica.

## Reglas de la instalación

- **`--scope project` es obligatorio.** Sin él, `claude plugin install` instala a nivel usuario, y los hooks del plugin correrían en todos tus proyectos (P2 de [`Doc/diseno.md`](diseno.md#4-diseño-del-plugin-p1p6)). En `/plugin install`, dentro de una sesión, elige la opción de instalar para todos los colaboradores del repositorio.
- **Cada ticket lleva su propio `.claude/settings.json`,** porque Claude Code lee ese archivo solo de la carpeta donde arranca la sesión. El bootstrap pone el `enabledPlugins` en la raíz y en la plantilla, y `/odd-ws:abrir` lo copia a cada ticket.
- **La sesión de un ticket se abre desde su carpeta, con cada repo de código agregado:** `claude --add-dir <ruta>`, una vez por cada repo o worktree de «Worktree y rama» en el `CLAUDE.md` del ticket. Sin eso, Claude Code pide permiso para leer o editar fuera de la carpeta del ticket.
- **O se trabaja desde la raíz**, que es lo cómodo en VS Code. La extensión usa la primera carpeta del `.code-workspace` como directorio principal y las demás como directorios adicionales, así que la raíz va primero y los repos o worktrees después. Si sus carpetas usan rutas relativas, el bootstrap lo suma al primer commit y el equipo lo recibe al clonar; con alguna ruta absoluta queda sin trackear, porque solo vale en tu máquina. El ticket activo (el último que abriste, o el de `ticket.py --activar <id>`) llega como resumen al arrancar la sesión y después de cada `/compact`: objetivo, specs, tareas, seguimientos y las últimas entradas de la bitácora. Lo demás se lee en su `CLAUDE.md`.

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
- **Instalar:** `npm i -g gentle-pi`, y después `gentle-shell install git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v0.20.0` (la versión actual), o la ruta de un clon tuyo. El paquete es la raíz del repositorio, no `plugin/`. Con la fuente git hace falta `npm` en el PATH. Por defecto, gentle-shell usa un home aislado (`~/.gentle-shell/agent`); con `gentle-shell --link install …` usa el de Pi (`~/.pi/agent`).
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
- **El doctor no ve los overlays de herramientas de gentle-shell.** Un overlay puede cambiar las herramientas de un agente al cargarlo, sin tocar su `.md`, así que `pi-agentes` puede salir OK aunque un revisor tenga una herramienta de más. La línea de `pi-agentes` del doctor te lo recuerda.

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
| `/odd-ws:enlaces` | Para revisar, abrir, copiar o depurar los enlaces de un ticket o de cualquier `.md` | La instancia, o cualquier carpeta con la ruta de un `.md` | Tú o Claude |
| `/odd-ws:revisar` | Antes de cada commit, o antes de mostrarle un cambio a un líder | La carpeta del ticket | Tú o Claude, con tu sí cuando cuesta corridas |
| `/odd-ws:cerrar` | Al terminar un ticket, o con `memorias` para graduar las memorias del proyecto | La instancia: su raíz o el ticket | Solo tú |
| `/odd-ws:conocimiento` | Para revisar la salud de los docs del proyecto | La raíz de la instancia | Solo tú |
| `/odd-ws:eval-reviewers` | Para medir un revisor contra la revisión real de un líder | La instancia | Tú o Claude |
| `/odd-ws:paquetes` | Para traer las reglas de una capa desde otro repo git, cambiarlas de etiqueta, sacarlas o verlas | La raíz de la instancia | Solo tú |

En Codex, cada skill se invoca con `$` (por ejemplo `$doctor`) o desde `/skills`; ver [Usarlo desde Codex](#usarlo-desde-codex).

«Solo tú» quiere decir que Claude no la dispara por su cuenta: la escribes tú en el chat. Todas las skills que escriben algo te muestran antes lo que van a hacer y esperan tu sí. Las únicas excepciones están en `/odd-ws:revisar`: el modo `0`, que no cuesta corridas; el rechequeo que aprobaste junto con su corrección; y el sello, que después de tu commit solo anota ese commit en el recibo.

### `/odd-ws:bootstrap`

- **Una sola parada.** Detecta los repos del `.code-workspace` de la carpeta y las extensiones de sus archivos (`bootstrap.py --proponer`), y te muestra la propuesta completa en una sola respuesta, en este orden:
  1. una línea fija de apertura y «Lo detectado», una tabla con cada término explicado en una línea y siempre las mismas filas, en el mismo orden: el proyecto, cada repo con su ruta, cada capa (una por tecnología, con lo que cuesta), las extensiones sin capa, el molde y quién commitea;
  2. el ensayo y, si hay, «Lo que pide atención», con esas líneas tal cual;
  3. el bloque «Lo que decides», con una fila corta por decisión: el perfil, los tickets y tus repos (`own`). Cada repo se propone del equipo: `own` solo va si dices que un repo es tuyo;
  4. justo debajo, una sola pregunta: si se aplica así o qué cambia.

  Así, en una terminal de unas 24 filas, lo que decides queda a la vista junto a la pregunta, sin subir, y la respuesta tiene la misma forma en cada corrida. `diseno` es un nombre reservado. A una capa solo te ofrece sumarle extensiones de su mismo lenguaje: en un repo TypeScript, `.js` o `.mjs` a la capa `ts`, pero no un `.json`.
- **En la raíz de un repo de código pregunta antes.** Si la carpeta es la raíz de un repo con archivos versionados y sin `workspace.config.json`, la instancia quedaría en el git de ese repo, con el hook y el primer commit en su rama. Por eso te lo pregunta aparte, siempre con el mismo texto («Ubicación», «¿Dónde la creo?»), y te recomienda una carpeta al lado del repo, `<raíz>-ws`. Solo con tu sí sigue ahí (`--confirmar-repo`); sin él, el script sale con 2 sin escribir nada.
- **Ensayo primero.** Arma una spec JSON (ejemplo: `plugin/plantillas/bootstrap.ejemplo.json`), corre `bootstrap.py --ensayo` y te muestra el plan agrupado por capa, con aparte las líneas que piden atención. Solo con tu sí escribe.
- **Nunca pisa un archivo.** En una instancia que ya existe, completa lo que falta a partir de su `workspace.config.json`, que no cambia.
- **Los CLI de la instancia.** La clave `hosts` de `workspace.config.json` dice en qué CLI se trabaja: `"hosts": ["claude-code", "codex"]`. Es opcional, y sin ella la instancia es solo de Claude Code. Con `codex`, el bootstrap también genera `.codex/`. El bootstrap la pregunta solo si mencionas otro CLI.
- **El perfil.** Es la primera fila de «Lo que decides», con `completo` propuesto: la plantilla entera. Si le dices que ya tienes tu propia orquestación o revisión (por ejemplo, gentle-ai con su RDD), la pasa a `controles`, que trae solo los guards, las reglas por capa y el doctor. Ver [El perfil `controles`](#el-perfil-controles).
- **El prefijo de los tickets.** Si no usas un tracker (Jira, Azure Boards, GitHub Issues, Linear…), la clave `tickets` fija el prefijo de los ids: `"tickets": {"prefix": "T"}`. Con ella, `/odd-ws:abrir` propone el siguiente id (`T-1`, `T-2`…) sin preguntarte. La fila de los tickets de «Lo que decides» te propone un prefijo, o el id de tu tracker si usas uno. En `controles` esa fila no va.
- **Los repos tuyos.** La última fila de «Lo que decides» propone cada repo como del equipo. Si uno es tuyo, dilo en tu respuesta: con `"own": true`, `/odd-ws:abrir` hace el `fetch` y crea el worktree del ticket por ti.
- **Hace el primer commit.** Con los archivos que creó, con el hook ya marcado como ejecutable, y nunca hace push. `workspace.local.json` nunca entra, porque tiene las rutas de tu máquina. También suma lo que ya estaba sin trackear y es de la instancia: el `.claude/settings.json` igual al que escribe el bootstrap (el que deja `claude plugin install --scope project`) y el `.code-workspace` de la raíz con rutas relativas. Lo que no entra lo dice con su motivo (`no entró al commit …`), por ejemplo un `settings.json` con otro contenido o un `.code-workspace` con una ruta absoluta: si es tuyo, lo commiteas tú. Si prefieres aprobar cada commit, pon `"ask_before_commit": true` en `workspace.config.json`: entonces no commitea y te dice qué hacer.
- **Muestra la aplicación y el doctor tal cual.** Con tu sí, te muestra las líneas de la aplicación tal cual, menos las de cada archivo, y después la salida entera del doctor, como `/odd-ws:doctor`: en un bloque de código, con un comentario de una línea por cada FALTA y cada AVISO. No las resume con sus palabras, así que la respuesta sale igual de una corrida a otra.
- **Termina con «Lo que sigue»,** un texto fijo según el perfil. En `completo`: abrir tu primer ticket con `/odd-ws:abrir`. La matriz arranca vacía y se llena al cerrar tickets; para no arrancar de cero, `/odd-ws:cerrar memorias` y `/odd-ws:paquetes`. Si alguno de tus repos ya tiene reglas escritas (su `CLAUDE.md`, sus gotchas, sus docs), que el primer ticket sea sembrarlas: leerlas, anotarlas en la bitácora con su archivo y su commit, y graduarlas con `/odd-ws:cerrar`. En `controles` no hay tickets: la revisión sigue siendo la de tu herramienta, y las reglas nacen con `/odd-ws:cerrar memorias` y `/odd-ws:paquetes`.

Lo que deja en la instancia está en [Qué genera el bootstrap](#qué-genera-el-bootstrap).

### `/odd-ws:doctor`

- Muestra una tabla OK / FALTA / AVISO / NO APLICA, con el arreglo de cada ítem. Sale con 0 si no hay ninguna FALTA y con 1 si hay alguna.
- **La tabla va en tres grupos,** cada uno con su encabezado: «La plantilla (solo en un clon de odd-workspace-template):», «Tu máquina:» (Python, git, los CLI, gentle-ai con su `rdd` y su telemetría, engram, jq y `plugin-root`) y «Esta instancia:». Un grupo sin filas no sale. La línea de resumen (`0 FALTA, 1 AVISO`) va al final, que es lo que se ve sin subir.
- **La skill la muestra tal cual,** entera y en un bloque de código, y debajo comenta solo cada FALTA y cada AVISO, en una línea: qué rompe y qué hacer. Si no hay ninguno, en lugar de los comentarios va la línea `Todo en orden: nada falta y no hay avisos.`, tal cual.
- **`plugin-root` sin tu usuario.** En OK, la ruta del plugin sale desde tu home (`~` y el resto) si está bajo él; si no, entera. Una FALTA y su arreglo la muestran entera, porque se copian, y `workspace.local.json` sigue guardando la ruta absoluta, que es la que lee el pre-commit.
- Arregla de a un ítem, solo con tu sí (`doctor.py --arreglar <id>`).
- **Las extensiones sin capa (`capas-cobertura`).** Te avisa qué extensiones versionadas de tus repos no cubre ninguna capa, porque un cambio en esos archivos lleva el triaje de `/odd-ws:revisar` a modo `completo`. Si son del mismo lenguaje que una capa (`.mjs` en una capa `ts`), súmalas a sus `extensions`.
  - **Los datos y la configuración son esperados y no avisan:** `.json`, `.jsonc`, `.yml`, `.yaml`, `.toml`, `.lock`, `.ini` y los archivos sin extensión (`.gitignore`, `Dockerfile`…). Si solo quedan esos, el ítem sale OK y los nombra con su conteo, con la nota de que un cambio en ellos lleva `/odd-ws:revisar` a modo `completo` (en `controles`, que ninguna regla de capa los chequea). Si hay alguna otra, el AVISO lista solo las otras.
  - **Las que van sin capa a propósito** (imágenes, recursos, archivos de build) las reconoces una vez con la clave `"sin_capa"` de `workspace.config.json`, una lista de extensiones con su punto: `"sin_capa": [".png", ".xml", ".gradle"]`. Pasan a las esperadas y el AVISO se apaga. El `cómo:` del AVISO trae esa línea con todas sus extensiones: saca las que sí son código antes de pegarla, porque reconocer código lo dejaría sin capa y sin aviso. No hay `--arreglar`: la config es tuya. Un valor inválido sale como FALTA en el ítem `config`.
  - **El triaje sigue contando igual:** cada vez que un archivo sin capa está entre sus motivos, esperado o no, repite el aviso, salvo para las extensiones de `sin_capa`, que nombra en una línea sin aviso. El modo no cambia: un cambio en ellas sigue llevando la revisión a `completo`. `/odd-ws:abrir` hace la misma cuenta que el doctor.
- **Los hooks apagados (`hooks-apagados`).** Si la clave `disabled_hooks` de `workspace.config.json` apaga alguno de los cinco hooks (`"disabled_hooks": ["revisar_turno"]`), te avisa con su nombre, y con el riesgo si es `guard_comandos`. No tiene arreglo: para prenderlo, lo sacas de la lista. Un valor inválido no apaga ninguno y sale como FALTA en el ítem `config`. Cómo y cuándo apagar uno, en [Hooks](hooks.md#apagar-un-hook).
- **Los hooks de tus repos (`hooks-de-repos`).** Si un repo de la config trae hooks propios en su `.claude/settings.json` o `.claude/settings.local.json`, te avisa con el repo y el archivo: esos hooks, como un guard o un formateador, corren solo si la sesión arranca en el repo, y no en una sesión abierta en la instancia. No tiene arreglo, porque esos archivos son del repo. Un archivo que no se puede leer, o que no trae `hooks`, no avisa.
- **Los hooks que fallaron (`hooks-fallas`).** Un hook que falla por dentro deja pasar lo que le tocaba revisar, y la falla queda anotada en `.claude/estado/fallas-de-hooks.jsonl`. Mientras haya alguna, te avisa con cuántas son y las tres más recientes: la fecha, el hook, el evento y el error. `--arreglar hooks-fallas` vacía el registro cuando ya lo viste. Más en [Hooks](hooks.md#si-un-hook-falla).
- **Las plantillas viejas (`plantillas`).** El `CLAUDE.md` raíz, `tickets/_plantilla/CLAUDE.md`, `.githooks/pre-commit` y la prueba de las reglas de cada capa son copias de plantillas del plugin, y el bootstrap no las vuelve a pisar. La clave `"plantillas"` de `workspace.config.json` anota con qué versión del plugin quedaron (el bootstrap la escribe al crear la instancia). Si desde esa versión cambió alguna plantilla, te avisa con cada copia: «sin tocar: se reemplaza» o «editada: fusiónala a mano», y qué versiones leer en [Actualizar](actualizar.md#después-de-actualizar-las-plantillas-de-la-instancia). Fusiona las editadas primero: te muestra qué cambió la plantilla desde la versión de tu copia y te propone la fusión de 3 vías, que escribe solo con tu sí (`fusionar_plantillas.py`); si choca, te muestra los bloques en conflicto y no escribe nada. Después, `--arreglar plantillas` reemplaza las sin tocar y anota la versión. Con el ítem `config` en FALTA, sale NO APLICA y `--arreglar plantillas` no escribe nada. Sin la clave (una instancia anterior a la 0.14.0) dice «sin versión anotada» y deduce la versión de las copias sin tocar, o «de la X a la Y» si coinciden con más de una. Después de actualizar el plugin, si vive en una carpeta con su versión (el caché de Claude Code o de Codex), la primera sesión ya te nombra las copias que cambiaron; si no, como en Pi instalado por git, te lo dice el doctor.
- **Las desviaciones conocidas (`desviaciones`).** Revisa `.claude/reglas/desviaciones.csv`, la lista de código que parece un error y es a propósito, que gradúa `/odd-ws:cerrar`. Sin el archivo es OK: «sin desviaciones anotadas». Si una fila está mal formada, te avisa con su línea y qué le falta, y no tiene arreglo: el archivo es tuyo. Mientras tanto, `/odd-ws:revisar` les pasa a los revisores solo las filas sanas.
- **Lo que se carga entero (`carga-entera`).** El `CLAUDE.md` raíz, el de cada ticket activo y cada `SKILL.md` de `.claude/skills` se cargan enteros: el primero en cada sesión, el del ticket en cada sesión que trabaja en él y el de una skill cada vez que se usa. Te avisa cuando alguno pasa de su tope, en bytes y no en líneas: 16 KiB el `CLAUDE.md` raíz, 32 KiB el de un ticket, cuya bitácora crece, y 17 KiB un `SKILL.md`. Nombra cada archivo con su peso y su tope. No tiene arreglo: el detalle se mueve a lo que se lee a pedido, como los docs del índice, un archivo aparte para la bitácora vieja o el `references/` de la skill. Por ahora el tope no se configura. No repite el tope del índice de `/odd-ws:conocimiento` (`index_max_lines`), que cuenta líneas.
- **Con el perfil `controles`,** `writers` sale una sola vez, en NO APLICA, y `rdd` cambia de sentido: encendido es OK, porque es tu revisión, y apagado es AVISO. Si el `CLAUDE.md` raíz sigue siendo el reducido y la instancia ya no es `controles`, te avisa en el ítem `perfil`. Ver [El perfil `controles`](#el-perfil-controles).
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
- **Las extensiones sin capa.** Al mostrar el ticket corre `ticket.py --cobertura`, la misma cuenta del ítem `capas-cobertura` del doctor. Si tus repos tienen extensiones versionadas sin capa que no son datos ni configuración, te lo dice junto a las capas afectadas: un cambio en esos archivos lleva la revisión a `completo` hasta que declares su capa. Los esperados (`.json`, `.yml`, los archivos sin extensión…, y las extensiones que reconoces en `sin_capa`) no son un aviso: te los nombra en una línea solo si el ticket va a tocarlos, porque un cambio en ellos también lleva la revisión a `completo`.
- **Los hooks de tus repos.** La misma corrida te avisa si un repo trae hooks propios en su `.claude/settings.json`: corren solo si la sesión arranca en ese repo, así que desde la raíz de la instancia no van a correr.
- **Los enlaces del ticket.** Para revisarlos, abrirlos o copiarlos está `/odd-ws:enlaces`, que también usa Claude cuando se lo pides.
- **El commit del ticket.** Con el ticket escrito, lo commitea en la instancia (`chore(<id>): abre el ticket`) sin volver a preguntar, salvo `"ask_before_commit": true`. Así el ticket tiene historia desde el primer día. Nunca hace push.
- **Al final** te dice las dos formas de trabajar el ticket: desde su carpeta con `--add-dir`, o desde la raíz.

### `/odd-ws:enlaces`

- **La lista.** Corre `ticket.py --enlaces <id>`, que lista los enlaces del `CLAUDE.md` del ticket, cada uno con su ruta absoluta y si es archivo o carpeta. Los que existen salen numerados, y los rotos y los que llevan esquema (`https:`, `mailto:`) salen aparte. También sirve con la ruta de cualquier `.md`, por ejemplo un `odd/tasks/<feature>.md`, aunque no estés en una instancia.
- **Las rutas de la máquina.** Un enlace con una ruta de tu máquina (`C:\…`, `/home/…`, `~/…`, o `~` solo) lleva la marca `(ruta de la máquina)`, porque se rompe en el clon de otra persona. Un destino como `~notas.md`, que empieza con `~` sin una barra después, es relativo al documento y no lleva la marca.
- **Abrir uno.** Te muestra la lista, con los rotos y las rutas de la máquina aparte, te pregunta cuál y corre `--abrir <n>` con el número que elegiste; nunca abre uno por su cuenta. Una carpeta se abre en el gestor de archivos, y un documento, un dato o una imagen, con su programa. Cualquier otro archivo, como un script o un ejecutable, se muestra en su carpeta sin abrirlo. Funciona en Windows, macOS, Linux con escritorio y WSL.
- **Cuándo no abre.** En una sesión remota (SSH) o sin pantalla no abre nada: te dice por qué y te deja la ruta. En Windows y WSL tampoco abre una ruta con una coma, porque `explorer` separa las rutas en las comas y podría abrir otra cosa: te deja la ruta para que la abras a mano.
- **Copiarlos.** Con `--copiar`, las rutas van además al portapapeles; si no hay con qué copiar, te avisa y la lista sale igual.
- **Los rotos aparecen solos.** Si el `CLAUDE.md` del ticket activo tiene enlaces rotos o con una ruta de tu máquina, el resumen que llega al arrancar y después de cada `/compact` termina con una lista corta: hasta 5, cada uno con su texto, su destino y el motivo (`no existe` o `ruta de la máquina`), y el comando que da la lista completa. `/odd-ws:cerrar` también los revisa antes de cerrar y te propone cómo arreglarlos, sin tocar ninguno sin tu sí. Si todos están bien, no dice nada.
- **Quién la dispara.** Tú o Claude: si le pides abrir o revisar los enlaces de un ticket, la usa sin que escribas el comando. `/odd-ws:abrir`, que es solo tuya, manda acá para lo mismo.

### `/odd-ws:revisar`

- **El triaje.** Corre `triaje.py --ticket` sobre el diff contra la base. La base es, en este orden: la que le pases con `--repo RUTA#BASE`; el último commit sellado del ticket; o el merge-base con `origin/HEAD`. La salida dice cuál usó. Propone un modo:
  - `sin-cambios`: no hay nada que revisar;
  - `0`: solo docs o notas, con lectura estructural y sin revisores;
  - `rapido`: todas las señales en negativo;
  - `completo`: alguna señal positiva, o un cambio que va a un líder.
- **Los chequeos antes de lanzar.** El mismo triaje corre sobre el diff las reglas de cada capa tocada (los chequeos de la instancia y de sus paquetes, con la calibración, sin contar lo que ya estaba en la base) y busca marcadores de conflicto (`<<<<<<<` y `>>>>>>>` en un mismo archivo), también en los archivos sin trackear. Si encuentra algo, o un chequeo no pudo correr, termina con «corregir antes de lanzar»: la skill te propone corregirlo antes de gastar en revisores, y lanzar sin corregir pide tu sí aparte. Si lanzas igual, los revisores lo reciben como ya detectado y no lo repiten. Sin nada, es una sola línea al final. El modo no cambia, y el rechequeo vuelve a correr los chequeos.
- **El costo.** Anuncia cuántas corridas cuesta y espera tu sí. En `completo`, `revisor-diseno` corre 3 veces, más el `revisor-<capa>` de cada capa tocada; en un rechequeo, una sola vez. El modo `0` no cuesta corridas: te dice el modo y corre sin esperar tu sí.
- **El último costo medido.** Junto a las corridas, te cita cuánto costó la última revisión medida del ticket, o de la instancia si el ticket todavía no tiene ninguna: por corrida, en promedio, los turnos, el contexto final, la salida y la caché escrita y leída (en gentle-shell, si solo guardó los totales, los tokens totales y el costo en USD). Lo cita tal cual, sin ajustarlo a tu diff, y si esas corridas corrieron en serie, una detrás de otra, te lo dice. Sin ninguna revisión medida, te anuncia solo las corridas. El porqué: el número de tokens que muestra Claude Code por corrida es su contexto final, cerca de un tercio de lo que cuesta.
- **Bajar un escalón.** Si el triaje propone `completo` solo por límites del instrumento (una señal inválida o un archivo sin capa) y el cambio no va a un líder, el anuncio te dice que puedes bajarlo a `rapido` si dejas el motivo. Lo decides tú: el agente nunca baja el modo por su cuenta. Nunca se baja a `0` si hay código, ni un cambio que va a un líder, ni uno donde el triaje vio un riesgo real. El recibo guarda el motivo y tu respuesta sobre el líder (`--bajada "<motivo>" --va-a-lider no`), solo si el triaje guardado es el de ese mismo diff: cada archivo del recibo tiene que estar en el triaje, con la misma base y sin una edición posterior al triaje. Si editaste algo después, el recibo te pide correr el triaje de nuevo, porque la edición pudo traer un riesgo real. Si el triaje vio además archivos que no revisaste, como los del ambiente local que no se commitean, el recibo no se niega: te los nombra en un aviso. El rechequeo de esa unidad sigue en `rapido` mientras no aparezca un riesgo real nuevo. Fuera de esta bajada, el modo nunca queda por debajo del que propuso el triaje guardado, y un rechequeo nunca baja del modo de la ronda anterior. Salvo en `completo`, ese triaje también tiene que ser el de este diff.
- **El rendimiento.** Cada hallazgo cita el ID de la regla que rompe, o `sin ID`, y `consolidado.md` abre con una línea que los cuenta: cuántos salieron, por acuerdo entre las tres corridas de diseño (solo en `completo`) y por severidad. Al escribir el recibo, la skill completa su destino: cuántos se corrigieron, se derivaron o se descartaron.
- **Lo que deja** en `tickets/<id>-<slug>/revision/<fecha>-<modo>/`: los diffs y el triaje de entrada, los reportes, el costo de cada corrida y de la revisión (`corridas/costo.json`, que en Claude Code suma lo que gastó la sesión principal desde el triaje y lo que le dejó en el contexto; en gentle-shell, el costo de cada corrida trae los turnos, los tiempos, los tokens totales y el costo en USD, y la salida y la caché cuando gentle-shell las guarda, sin el contexto), `consolidado.md` y `recibo.json`. Una segunda ronda del mismo día y modo va en `<fecha>-<modo>-2`, sin pisar la primera.
- **Los secretos tapados.** Lo que deja en la instancia sale con los secretos tapados: tokens y claves con un formato concreto (AWS, GitHub, Slack, Google, OpenAI, Anthropic, Stripe y las claves privadas), cada uno con un marcador como `<GITHUB_TOKEN>`. El rescate tapa los reportes, el recibo tapa su texto libre, el triaje tapa los fragmentos que citan sus chequeos, y antes del `--check` la skill corre `tapar.py` sobre los diffs de entrada y `consolidado.md`. Los revisores ven los diffs sin tapar, porque un secreto en el código es un hallazgo `CRITICAL`, y el recibo sigue valiendo, porque guarda la huella del diff de los repos.
- **El cierre: una corrección y un rechequeo.** Tú eliges qué se corrige, y eso va en un solo lote. El mensaje que lo propone te anuncia también el rechequeo y su costo, así que con un solo sí apruebas los dos. El rechequeo verifica los hallazgos anteriores y revisa solo los archivos que cambiaron desde la ronda anterior y los que sumó la corrección, con una corrida del revisor de diseño y una por cada capa, también en `completo`. Su recibo (`recibo.py --write --previo <ronda anterior>`) hereda los archivos que no cambiaron, así que cubre la unidad entera y se puede sellar. El porqué: en un ticket real, la re-revisión después de una corrección volvió a revisar toda la unidad, al mismo costo que la primera, y una re-revisión parcial no se podía sellar.
- **Lo que aparece en el rechequeo.** Un hallazgo `CRITICAL` se corrige en la unidad. Uno que no es `CRITICAL` se deriva: va a otra tarea, otro ticket o el backlog, queda anotado en el recibo (`--derivado "<hallazgo>=<destino>"`) y en la sección `## Seguimientos` del ticket, que va justo después de las Tareas y queda también en un ticket chico. Antes, lo que quedaba para después terminaba metido en la tabla de Tareas, y la rompía.
- **Lo ya decidido.** Cada corrida recibe las decisiones del ticket (`## Decisiones`) y no las vuelve a plantear. Lo que reabre una sin ser `CRITICAL` queda aparte, fuera del lote de corrección.
- **Las desviaciones conocidas.** Cada corrida recibe también las desviaciones de la instancia, de `.claude/reglas/desviaciones.csv`: el código que parece un error y es a propósito, cada uno con su porqué. Valen para todos los tickets, así que ningún revisor las vuelve a plantear, y lo que reabre una sin ser `CRITICAL` queda aparte, como una decisión. La skill las saca con `desviaciones.py`; sin el archivo, la lista dice «ninguna». Si una fila está mal formada, te lo dice en una línea y la revisión sigue con las demás.
- **El recibo no se reescribe con otro diff.** Si vuelves a escribir el recibo de una revisión (por ejemplo, de `pendiente` a `con-hallazgos` después de descartar o derivar los hallazgos), solo cambia el estado cuando el diff es el mismo que se revisó, y conserva el sello y lo demás. Si lo revisado cambió, no escribe nada y te manda al rechequeo con `--previo`: un recibo nunca pasa a cubrir una corrección que nadie revisó.
- **Antes del commit.** `recibo.py --check` dice el estado, el modo y la bajada del recibo, y mira también lo que entraría al commit: falla si el índice trae otra versión de lo revisado o archivos fuera del recibo, y te avisa de los cambios fuera del recibo que no stageaste, porque no entran al commit. Es el mismo criterio con el que después se sella.
- **El sello.** Cuando commiteas una unidad revisada, la skill corre `recibo.py --sellar` sobre el recibo de esa unidad, que anota en el recibo el commit donde quedó lo revisado. Así la revisión de la unidad siguiente parte de ese commit y no vuelve a revisar lo que ya revisó: sin sello, en un ticket real el triaje contó 83 archivos en vez de los 21 de la unidad nueva. El recibo de la unidad siguiente parte del mismo commit, aunque no le pases la base. No sella un recibo `pendiente`, ni si cambió lo revisado, si falta commitearlo o si `HEAD` ya trae otra cosa, como un commit de otra unidad; por eso conviene sellar justo después del commit. Si `HEAD` trae archivos de esta unidad que el recibo no tiene, te propone rechequearlos con `--previo`, y ese recibo sí se sella.
- **No commitea.**

### `/odd-ws:cerrar`

- **El triaje de los aprendizajes.** Lee el ticket y decide qué pasa con cada aprendizaje: lo general sube a los docs de dominio, al `CLAUDE.md` de la raíz o a una fila de la matriz; lo de un solo ticket se queda en su carpeta.
- **Las desviaciones conocidas.** El código que parece un error y es a propósito, con su porqué verificado, se gradúa como una fila de `.claude/reglas/desviaciones.csv` (`id,ubicacion,resumen,porque,fecha`), que se crea con la primera. `ubicacion` es `<repo>:<ruta>@<hash>:<ini>-<fin>` para el código de un repo, o la ruta de un archivo de la instancia. Desde ahí, `/odd-ws:revisar` se la pasa a cada revisor como «no la reemitas», en cualquier ticket, y los hooks preguntan antes de una edición que toque sus líneas (ver [El porqué antes de editar](hooks.md#el-porqué-antes-de-editar)).
- **Lo que el ticket quitó.** Con `quitado.py`, lista los archivos que el diff del ticket borró (un renombre no cuenta) y las dependencias que salieron de un manifiesto: `package.json`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `*.csproj`, `build.gradle`, `build.gradle.kts` y `Cargo.toml`. Subir una versión no es quitarla. Por cada ítem te pregunta si puede volver, y lo que no, lo gradúa como un chequeo cuyo `sembrado` es la línea que lo vuelve a agregar, con tu porqué. Un patrón no lo detecta: lo nombras tú. Si el ticket ya se mergeó, el diff sale vacío y te pide la base con `--repo RUTA#BASE`. Sin nada quitado, no dice nada.
- **Antes de escribir** te muestra la propuesta completa y espera tu sí.
- **El modo sombra.** Si hay un caso sin puntuar, frena y te manda primero a `/odd-ws:eval-reviewers`.
- **Al final** hace el commit de cierre (`chore(<id>): cierre e hidratación`) sin volver a preguntar, porque tu sí a la propuesta ya lo cubría. Con `"ask_before_commit": true` en la config, te pide un segundo sí antes del commit. Nunca hace push.
- **El worktree.** En un repo marcado como tuyo, lo desarma él si está limpio y su rama ya está en `origin`; si no, te dice qué falta. En un repo del equipo, te da los comandos para que lo desarmes tú.
- **La entrega después del cierre.** Si cerraste antes de entregar, cuando la entrega queda hecha no se vuelve a cerrar: pasa el ticket a `listo`, anota la entrega en la bitácora, commitea (`chore(<id>): entrega`) y quita la marca de ticket activo. Si la entrega cambió código después de la revisión, ese cambio pasa antes por `/odd-ws:revisar`.
- **Lo que quedó sin subir vuelve solo.** Mientras un ticket activo tenga cambios sin commitear, commits sin empujar o una rama que nunca se empujó, cada sesión arranca diciéndolo, en una línea por ticket, y calla cuando no hay nada. `entregas.py` da la misma lista, y si la entrega llegó por otro camino, `entregas.py --confirmar <ticket>` lo calla hasta que sus ramas o sus archivos cambien (ver [Lo que quedó sin subir](hooks.md#lo-que-quedó-sin-subir)).
- **Antes de publicar, la auditoría de ramas.** `auditar_ramas.py` hace `fetch` de cada repo de la config, que solo actualiza sus refs de `origin`, y da una línea por ticket y repo: si cada rama llegó a la rama principal del repo (`origin/HEAD`, y si no hay, `origin/main` u `origin/master`) o qué le falta (cambios sin commitear, commits sin empujar, una rama que nunca se empujó o commits que no llegaron).
  - **Un squash cuenta como llegado,** porque compara los parches con `git cherry`. Un commit empujado a una rama cuyo PR ya se mergeó no cuenta: el push sale bien, pero ese commit nunca llega a la principal.
  - **Si el `fetch` de un repo falla,** ese repo sale en rojo y sus ramas quedan sin juzgar, en vez de juzgarlas con refs viejas. Si tu remoto pide una credencial, el repo también sale en rojo, enseguida y sin abrir ninguna ventana: haz un `git fetch` a mano una vez y vuelve a auditar.
  - **La salida.** Termina con un resumen, y sale con 0 si todo llegó y con 1 si algo falta o algún repo está en rojo. `--json` da lo mismo para un script, y `--archivados` suma los tickets archivados.
  - **Diagnostica y no opera:** no toca ramas, archivos ni el índice. `/odd-ws:cerrar` la nombra en su referencia de la entrega.
- **Las memorias sin triar.** Cierra con una línea: «N memorias sin triar: `/odd-ws:cerrar memorias`». No las tría ni frena el cierre.

#### El modo `memorias`

`/odd-ws:cerrar memorias` (en Codex, `$cerrar memorias`) no cierra ningún ticket: gradúa a la matriz las reglas que ya están en las memorias del proyecto. Reusa la propuesta con tu sí, la fila de la matriz con sus chequeos y el commit; salta lo que es de un ticket (los relojes, la bitácora, el modo sombra y el worktree). El porqué está en [Memorias](diseno.md#memorias-memoriaspy-y-cerrar-memorias), dentro de `Doc/diseno.md`.

- **Las fuentes.** La memoria en archivos de Claude Code, que lee `memorias.py`, y engram, si tu sesión lo tiene. Si `memorias.py` no encuentra el directorio, el modo te dice qué ruta probó y se detiene: nunca te dice «no hay memorias».
- **Las memorias de tus repos.** Lo que guardaste trabajando dentro de un repo vive en el proyecto de ese repo, no en el de la instancia. El modo las lee también, repo por repo (`memorias.py --repo <nombre>` y su proyecto en engram), y lo que gradúa de ahí queda en la matriz con el origen `memoria:<repo>.<slug>`.
- **Qué te propone.** De las memorias `feedback` (y las `project`, si las pides), las que están `nueva` o `cambiada` y suenan a regla. Por cada una ves su slug, la fila exacta de la matriz, con `memoria:<slug>` como origen, y el texto que va a su destino. Las `user` y las `reference` nunca entran.
- **La privacidad.** La fila, el destino y la evidencia parafrasean la regla: no copian la memoria ni nombran personas, y la propuesta te muestra los tres antes de escribirlos. Si un chequeo de la matriz pide corregir alguno, también te muestra la corrección y espera tu sí. El slug va en el origen, así que si el nombre del archivo no debe salir de tu máquina, renómbralo antes o déjalo como visto. La matriz viaja en el repo de tu instancia y ahí no corre ningún barrido: lo que apruebas es lo que queda escrito.
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
| `workspace.config.json` | La config versionada: los repos (con `agent_readonly` opcional), las capas y, opcionales, `knowledge` y `hosts`. Al final, `plantillas`: la versión del plugin con que se copiaron las plantillas, que lee el doctor. La anota el bootstrap al crear la instancia, y rechaza una spec que trae otra versión |
| `workspace.local.json` | Lo de tu máquina: la ruta de cada repo y `plugin_root`. Va en `.gitignore`, y el bootstrap nunca lo commitea, aunque el `.gitignore` no lo excluya |
| `CLAUDE.md` | El índice y la metodología de la instancia |
| `tickets/_plantilla/` | La plantilla de cada ticket, con su `.claude/settings.json` |
| `.claude/agents/` | `writer-<capa>.md`, `revisor-<capa>.md` y `revisor-diseno.md` |
| `.claude/skills/` | `capa-<capa>/SKILL.md` (las convenciones de cada capa) y `criterios/SKILL.md` |
| `.claude/reglas/` | `matriz.csv` (solo el encabezado), `evidencia.md`, `verificar_<capa>.py` (vacío) y `verificar_<capa>.tests.py` |
| `.githooks/pre-commit` | Llama a `pre_commit.py` del plugin: frena un archivo de secretos stageado (`.env`, una clave o un `credentials*.json`, salvo sus variantes de ejemplo) o una clave privada pegada, avisa de las rutas personales sin frenar y corre las pruebas de las reglas de cada capa (`reglas.py --test`) |
| `.gitattributes` | Deja `.githooks/*` en LF, aunque Git convierta los saltos de línea (en Windows, `core.autocrlf` viene activado) |
| `.claude/settings.json` | El `enabledPlugins` de la raíz |
| `.gitignore`, `git init` y `core.hooksPath` | Para que el pre-commit corra desde el primer commit |
| `.codex/` | Solo si `hosts` declara `codex`: un `agents/<agente>.toml` por agente, derivado de su `.md` en `.claude/agents` (que es donde se edita), y `config.toml` para que Codex lea los `CLAUDE.md`. Codex los carga solo si el proyecto tiene su confianza. En una instancia que ya existía, el TOML de un agente que ya tenía su `.md` no lo crea el bootstrap: lo genera el doctor (`--arreglar codex-agentes`) |

No los genera: la carpeta de docs de `knowledge`, el estado de ejecución (`.claude/estado/`, ignorado por git) ni las carpetas `revision/` de cada ticket.

Las reglas de cada capa se escriben después, en la instancia: ver [Capas y reglas propias](capas-y-reglas.md).

## El perfil `controles`

Si ya trabajas con gentle-ai completo, con su orquestación y su RDD, puedes instalar solo los controles de `odd-ws`: los guards, las reglas por capa y el doctor, sin `/odd-ws:revisar`, recibos, tickets ni writers. Se elige con una clave de `workspace.config.json`:

```json
"profile": "controles"
```

- **Lo que genera:** la config y `.gitignore`; la matriz, la evidencia y el chequeo y la prueba de cada capa; la skill `capa-<capa>` de cada capa, de donde los hooks leen los no-negociables; el pre-commit, `.gitattributes`, `.claude/settings.json`, `git init` y `core.hooksPath`; y `.codex/config.toml`, si declaras Codex. El `CLAUDE.md` es uno reducido, de unas 45 líneas.
- **Lo que no genera:** los writers, los revisores, `revisor-diseno` ni `criterios`, ni sus derivados de Codex y Pi, ni `tickets/_plantilla/`.
- **Los hooks son los mismos** y ninguno se apaga por el perfil (ver [Hooks](hooks.md#apagar-un-hook)).
- **Las skills que no aplican** (`/odd-ws:abrir`, `/odd-ws:cerrar` en su modo normal, `/odd-ws:revisar` y `/odd-ws:eval-reviewers`) lo dicen y no corren. Las reglas nacen con `/odd-ws:cerrar memorias`, que sí corre, y con `/odd-ws:paquetes`.
- **La revisión es la de tu herramienta.** El doctor no te propone apagar el RDD de gentle-ai: encendido es OK, y apagado es AVISO, porque la instancia queda sin revisión. `writers` sale en NO APLICA.
- **Sin la clave** el perfil es `completo`, y una instancia que ya existía no cambia. Un valor que no sea `completo` ni `controles` lo rechaza el bootstrap, y el doctor lo marca como FALTA en el ítem `config`.
- **Pasar a completo:** quita `"profile": "controles"`, borra el `CLAUDE.md` reducido si no lo editaste y corre `/odd-ws:bootstrap`, que completa lo que falta sin pisar nada. Si no lo borras, el bootstrap no lo reemplaza, y el doctor te avisa en el ítem `perfil`.
- **Bajar de completo a `controles` no se soporta** en esta versión: el bootstrap no borra nada, así que los writers, los revisores, los tickets y el `CLAUDE.md` completo quedan.
