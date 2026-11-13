# odd-workspace-template

**Que tu agente no vuelva a cometer el mismo error.** `odd-ws` es un plugin para Claude Code y Codex CLI que convierte lo que aprendes en un proyecto en chequeos que corren solos, en vez de notas que el agente tiene que recordar.

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

- **El CI** (`.github/workflows/pruebas.yml`) corre todas las suites en Ubuntu, Windows y macOS. No instala ningún CLI. En Linux y macOS nadie lo probó a mano todavía.
- **Codex en Windows:** los writers necesitan `[windows] sandbox` en la config de Codex. Con el sandbox `unelevated`, la medición de líneas del writer da 0/0 (pendiente X7). Afecta solo esa medición, no los bloqueos.
- **Si Python no arranca:** con Claude Code 2.1.295 o más, la herramienta se bloquea con el error. Con una versión anterior, y siempre en Codex, la herramienta pasa sin el chequeo.

## Instalación

### Antes de instalar

| Herramienta | Versión |
|---|---|
| Python, invocable como `python3` | 3.7 o más. El doctor pide 3.11 o más para leer la config de Codex |
| Git | En Windows, Git for Windows |
| Claude Code | 2.1.284 o más; se recomienda 2.1.295 o más |
| Codex CLI, si lo usas | 0.144 o más; 0.167 o más para los writers |

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
