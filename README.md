# odd-workspace-template

**Que tu agente no vuelva a cometer el mismo error.** `odd-ws` es un plugin para Claude Code, Codex CLI y gentle-shell (Pi) que convierte lo que aprendes en un proyecto en chequeos que corren solos, en vez de notas que el agente tiene que recordar.

**Versión actual:** `0.5.0` ([qué cambió en cada versión](CHANGELOG.md)).

## El problema

Una convención que solo vive como texto depende de que el modelo la recuerde. `odd-ws` sigue el principio *Mecanismo > Memoria*: lo que se aprende se vuelve un chequeo, no un recordatorio.

Este repo es un marketplace con un solo plugin, `odd-ws`. El plugin convierte la carpeta de tu proyecto en una **instancia**, un espacio de trabajo con agentes:

- **Cada ticket tiene su carpeta,** con su objetivo, sus criterios de aceptación y su alcance.
- **Los hooks chequean cada edición** contra las reglas de su capa, y frenan los comandos peligrosos.
- **Los cambios grandes los escriben agentes con compuerta,** y los revisores dejan un recibo atado al diff.
- **Lo aprendido en un ticket sube** a reglas y docs verificables.

## Así se ve un bloqueo

Tu agente intenta `git push --force origin main`. El hook de comandos lo frena antes de que corra, y el agente recibe este mensaje:

```text
guard-comandos bloqueó el comando: git push --force (si de verdad hace falta forzar, usa --force-with-lease). Si la operación es deliberada, que la corra el usuario a mano.
```

Lo mismo vale para tu stack: si el agente no cargó los no-negociables de una capa, su primera edición ahí se bloquea y los recibe, y después de cada edición corren las reglas de la capa. El detalle está en [Hooks](Doc/hooks.md).

## Dónde funciona

| CLI | Windows | Linux | macOS |
|---|---|---|---|
| Claude Code | Uso diario del autor, y el CI | Solo el CI | Solo el CI |
| Codex CLI | Prueba de humo a mano con la 0.144 y la 0.167, y el CI | Solo el CI | Solo el CI |
| gentle-shell (Pi) | Solo el CI, con una Pi simulada | Solo el CI | Solo el CI |

- **El CI** (`.github/workflows/pruebas.yml`) corre todas las suites en Ubuntu, Windows y macOS. No instala ningún CLI. En Linux y macOS nadie lo probó a mano todavía.
- **Codex en Windows:** los writers necesitan `[windows] sandbox` en la config de Codex. Con el sandbox `unelevated`, la medición de líneas del writer da 0/0 (pendiente X7). Afecta solo esa medición, no los bloqueos.
- **gentle-shell:** todavía no corrió dentro de un Pi real. La prueba de humo llega con la próxima entrega.
- **Si Python no arranca:** con Claude Code 2.1.295 o más, y en Pi, la herramienta se bloquea con el error. Con una versión anterior de Claude Code, y siempre en Codex, la herramienta pasa sin el chequeo.

## Instalación

### Antes de instalar

| Herramienta | Versión |
|---|---|
| Python, invocable como `python3` | 3.7 o más. El doctor pide 3.11 o más para leer la config de Codex |
| Git | En Windows, Git for Windows |
| Claude Code | 2.1.284 o más; se recomienda 2.1.295 o más |
| Codex CLI, si lo usas | 0.144 o más; 0.167 o más para los writers |
| Pi, si lo usas | 1.5.0 o más. En Windows, sus hooks lanzan `python` |
| gentle-shell, para los writers en Pi | El de `npm i -g gentle-pi`. Sin él, Pi corre los guards, pero no los writers |

En Windows, `python3` lo crean el Python install manager de python.org y la Microsoft Store, no el instalador clásico. El detalle y las herramientas opcionales están en [Requisitos de la máquina](Doc/uso.md#requisitos-de-la-máquina).

### Con Claude Code

1. **Instala el plugin** desde la carpeta del proyecto (puede estar vacía). `--scope project` es obligatorio: sin él, los hooks correrían en todos tus proyectos.

   ```text
   claude plugin marketplace add sebasgc0399/odd-workspace-template
   claude plugin install odd-ws@odd-workspace-template --scope project
   ```

2. **Abre `claude` en esa carpeta y corre `/odd-ws:bootstrap`.** Te entrevista (proyecto, repos y capas), te muestra el plan y solo escribe después de tu sí.
3. **Corre `/odd-ws:doctor`,** arregla lo que marque FALTA y abre tu primer ticket con `/odd-ws:abrir`.

Antes de tu primer ticket, lee las [reglas de la instalación](Doc/uso.md#reglas-de-la-instalación): cada ticket lleva su `.claude/settings.json` y su sesión se abre con `--add-dir`.

### Con Codex CLI

Codex trabaja sobre la misma instancia: `.claude/` sigue siendo la fuente, y Codex recibe sus propios archivos generados. Una instancia puede usarse con los dos CLI a la vez.

1. **Declara Codex en la instancia:** `"hosts": ["claude-code", "codex"]` en `workspace.config.json`. En una instancia nueva, el bootstrap te lo pregunta si mencionas Codex.
2. **Instala el plugin en Codex:**

   ```text
   codex plugin marketplace add sebasgc0399/odd-workspace-template
   codex plugin add odd-ws@odd-workspace-template
   ```

3. **Abre `codex` en la raíz de la instancia,** acepta confiar en la carpeta y confía los hooks de `odd-ws` cuando Codex lo pida, o desde `/hooks`. Las skills se invocan con `$`, por ejemplo `$doctor`.

Para sumar Codex a una instancia que ya existe, o configurar los writers en Windows, ve a [Usarlo desde Codex](Doc/uso.md#usarlo-desde-codex).

### Con gentle-shell (Pi)

gentle-shell es Pi con subagentes, y trabaja sobre la misma instancia: `.claude/` sigue siendo la fuente, y Pi recibe sus agentes generados en `.pi/agents`.

1. **Declara Pi en la instancia:** `"hosts": ["claude-code", "pi"]` en `workspace.config.json`, o solo `["pi"]`. En una instancia que ya existe, los agentes de `.pi/agents` los genera el doctor en el paso 4.
2. **Instala gentle-shell y el paquete de `odd-ws`.** gentle-shell se instala con `npm i -g gentle-pi`. El paquete de `odd-ws` no está en npm: se instala desde git, con la etiqueta de la versión, o desde la raíz de un clon del repo.

   ```text
   gentle-shell install git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v<versión>
   gentle-shell install <ruta del clon>
   ```

   - **El home:** `gentle-shell install` instala en el home aislado de gentle-shell (`~/.gentle-shell/agent`), que no ve los paquetes de tu Pi. Si abres gentle-shell con `--link`, que usa `~/.pi/agent`, instala ahí: `gentle-shell --link install <fuente>`.
   - **La ruta es la raíz del clon, no `plugin/`:** ahí está el `package.json` del paquete. Va en la raíz porque Pi instala un repo git entero y no admite un paquete en una subcarpeta.
   - **Con la fuente git,** Pi corre `npm install` en su copia del repo, así que necesita `npm` en el `PATH`.
3. **Abre gentle-shell en la raíz de la instancia** y dale confianza al proyecto con `/trust`. gentle-shell solo lee los agentes de `<cwd>/.pi/agents`, y sin confianza no llegan las skills de la instancia.
4. **Corre `/skill:doctor`.** En Pi, las skills del plugin se invocan con `/skill:<nombre>`. El doctor revisa la versión de Pi, gentle-shell, el paquete del home activo, la confianza del proyecto y los agentes de `.pi/agents`; en una instancia que ya existía, aplica `--arreglar pi-agentes`.

Para actualizar, vuelve a instalar con la etiqueta nueva: Pi deja fija la etiqueta de una fuente git, y `pi update` no la mueve. Con un clon, actualiza el clon y corre `/reload`.

Ten en cuenta:

- **Sin gentle-shell no hay compuerta.** Con Pi a secas corren los guards, pero no hay subagentes: no hay writers ni su compuerta de cierre, y el doctor lo avisa.
- **La tarea de un writer no puede empezar con `/`.** Pi la expandiría como una skill o una plantilla, y el writer correría sin guards, así que el lanzamiento se bloquea. Nombra la skill en el texto de la tarea.
- **Los comandos de las skills usan `${CLAUDE_PLUGIN_ROOT}`, que Pi no define.** La extensión de odd-ws la define al cargarse, con la carpeta del plugin, si no estaba. Si algo la pisa, corre el doctor a mano desde la raíz de la instancia: `python3 <raíz del paquete>/plugin/scripts/doctor.py`. La raíz del paquete es tu clon o, con la fuente git, `~/.gentle-shell/agent/git/github.com/sebasgc0399/odd-workspace-template` (con `--link`, `~/.pi/agent/git/github.com/sebasgc0399/odd-workspace-template`).

## Documentación

| Si quieres… | Lee |
|---|---|
| Conocer los conceptos, el ciclo de un ticket y cada skill | [Doc/uso.md](Doc/uso.md) |
| Entender por qué el agente frenó una edición o un comando | [Doc/hooks.md](Doc/hooks.md) |
| Escribir reglas para tu stack | [Doc/capas-y-reglas.md](Doc/capas-y-reglas.md) |
| Actualizar el plugin | [Doc/actualizar.md](Doc/actualizar.md) |
| Saber qué cambió en cada versión | [CHANGELOG.md](CHANGELOG.md) |
| Modificar la plantilla misma | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Conocer el porqué de cada decisión | [Doc/diseno.md](Doc/diseno.md) |

## Licencia

[MIT](LICENSE).
