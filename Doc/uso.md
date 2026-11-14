# Usar odd-ws

Esta guía es para quien ya instaló el plugin y lo usa en su proyecto: los conceptos, lo que necesita la máquina, el ciclo de un ticket y qué hace cada skill. La instalación en tres pasos está en el [README](../README.md#instalación).

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

Dos cosas a tener en cuenta:

- **Sin gentle-shell no hay writers con compuerta.** Pi a secas corre los guards y el primer toque, pero no tiene subagentes.
- **La tarea de un writer no puede empezar con `/`.** Pi la expandiría como comando y el writer perdería su marca, así que odd-ws bloquea el lanzamiento. Nombra la skill o la plantilla dentro del texto.

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
| `/odd-ws:cerrar` | Al terminar un ticket, o con `memorias` para graduar las memorias del proyecto | La instancia: su raíz o el ticket | Solo tú |
| `/odd-ws:conocimiento` | Para revisar la salud de los docs del proyecto | La raíz de la instancia | Solo tú |
| `/odd-ws:eval-reviewers` | Para medir un revisor contra la revisión real de un líder | La instancia | Tú o Claude |

En Codex, cada skill se invoca con `$` (por ejemplo `$doctor`) o desde `/skills`; ver [Usarlo desde Codex](#usarlo-desde-codex).

«Solo tú» quiere decir que Claude no la dispara por su cuenta: la escribes tú en el chat. Todas las skills que escriben algo te muestran antes lo que van a hacer y esperan tu sí.

### `/odd-ws:bootstrap`

- **Entrevista,** de a una pregunta: el nombre del proyecto, los repos con su ruta absoluta y las capas, cada una con sus extensiones, sus repos y su prefijo de reglas. `diseno` es un nombre reservado.
- **Ensayo primero.** Arma una spec JSON (ejemplo: `plugin/plantillas/bootstrap.ejemplo.json`), corre `bootstrap.py --ensayo` y te muestra el plan. Solo con tu sí escribe.
- **Nunca pisa un archivo.** En una instancia que ya existe, completa lo que falta a partir de su `workspace.config.json`, que no cambia.
- **Los CLI de la instancia.** La clave `hosts` de `workspace.config.json` dice en qué CLI se trabaja: `"hosts": ["claude-code", "codex"]`. Es opcional, y sin ella la instancia es solo de Claude Code. Con `codex`, el bootstrap también genera `.codex/`. El bootstrap la pregunta solo si mencionas otro CLI.
- **Termina con el doctor.** No hace `git add` ni `commit`: el primer commit es tuyo.

Lo que deja en la instancia está en [Qué genera el bootstrap](#qué-genera-el-bootstrap).

### `/odd-ws:doctor`

- Muestra una tabla OK / FALTA / AVISO / NO APLICA, con el arreglo de cada ítem. Sale con 0 si no hay ninguna FALTA y con 1 si hay alguna.
- Arregla de a un ítem, solo con tu sí (`doctor.py --arreglar <id>`).
- Revisa cada CLI solo si la instancia lo declara en `hosts` (sin la clave, Claude Code). Con `codex` suma la versión de Codex (0.144 o más), el plugin instalado y habilitado, la confianza de los hooks y del proyecto, `.codex/config.toml` y que cada `.codex/agents/<agente>.toml` sea el que sale de su `.md` (`codex-agentes`), además de `hooks-host`, que ningún hook lleve un `--host` desconocido, vacío o de otro host. No escribe en la carpeta de Codex, y no verifica que el hash de la confianza siga fresco.
- **Sumar Codex a una instancia que ya existe:** agrega `"codex"` a `hosts` y corre `doctor.py --arreglar codex-config` y `doctor.py --arreglar codex-agentes`. Los TOML salen de los `.md` de `.claude/agents`, con su `description` y sus bloques; uno editado a mano queda en AVISO y no se pisa.
- Sin el plugin instalado, se corre desde un clon: `python3 plugin/scripts/doctor.py`.

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
- **Las memorias sin triar.** Cierra con una línea: «N memorias sin triar: `/odd-ws:cerrar memorias`». No las tría ni frena el cierre.

#### El modo `memorias`

`/odd-ws:cerrar memorias` (en Codex, `$cerrar memorias`) no cierra ningún ticket: gradúa a la matriz las reglas que ya están en las memorias del proyecto. Reusa la propuesta con tu sí, la fila de la matriz con sus chequeos y el commit; salta lo que es de un ticket (los relojes, la bitácora, el modo sombra y el worktree). El porqué está en [Memorias](diseno.md#memorias-memoriaspy-y-cerrar-memorias), dentro de `Doc/diseno.md`.

- **Las fuentes.** La memoria en archivos de Claude Code, que lee `memorias.py`, y engram, si tu sesión lo tiene. Si `memorias.py` no encuentra el directorio, el modo te dice qué ruta probó y se detiene: nunca te dice «no hay memorias».
- **Qué te propone.** De las memorias `feedback` (y las `project`, si las pides), las que están `nueva` o `cambiada` y suenan a regla. Por cada una ves su slug, la fila exacta de la matriz, con `memoria:<slug>` como origen, y el texto que va a su destino. Las `user` y las `reference` nunca entran.
- **La privacidad.** La fila, el destino y la evidencia parafrasean la regla: no copian la memoria ni nombran personas, y la propuesta te muestra los tres antes de escribirlos. El slug va en el origen, así que si el nombre del archivo no debe salir de tu máquina, renómbralo antes o déjalo como visto. La matriz viaja en el repo de tu instancia y ahí no corre ningún barrido: lo que apruebas es lo que queda escrito.
- **engram.** Solo con `scope: project` y `limit: 20` por consulta. Su cobertura sale como parcial, con cuántas consultas llegaron al tope de 20. El origen es `memoria:engram-<id>`. Lo de engram no entra al registro local, así que puede volver a salir; lo que ya graduaste se reconoce por su fila.
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
| `.claude/settings.json` | El `enabledPlugins` de la raíz |
| `.gitignore`, `git init` y `core.hooksPath` | Para que el pre-commit corra desde el primer commit |
| `.codex/` | Solo si `hosts` declara `codex`: un `agents/<agente>.toml` por agente, derivado de su `.md` en `.claude/agents` (que es donde se edita), y `config.toml` para que Codex lea los `CLAUDE.md`. Codex los carga solo si el proyecto tiene su confianza. En una instancia que ya existía, el TOML de un agente que ya tenía su `.md` no lo crea el bootstrap: lo genera el doctor (`--arreglar codex-agentes`) |

No los genera: la carpeta de docs de `knowledge`, el estado de ejecución (`.claude/estado/`, ignorado por git) ni las carpetas `revision/` de cada ticket.

Las reglas de cada capa se escriben después, en la instancia: ver [Capas y reglas propias](capas-y-reglas.md).
