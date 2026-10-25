# /doctor: el chequeo de la máquina (Capa 0)

Objetivo: que una máquina nueva (o esta) diga en una tabla qué le falta para trabajar con la plantilla, con el arreglo de cada ítem, y que el riesgo B2b (un clon sin `core.hooksPath`) deje de depender de la memoria. Rama: `feat/doctor`, desde `feat/fundacion`. Runner: Python sin pytest, `doctor.tests.py` junto al script.
Espejo en Engram: `odd/doctor/tasks`.

## Specs

- **S1** — Alcance aprobado (L1): «Un script `plugin/scripts/doctor.py` con sus tests escritos primero y una skill `/odd-ws:doctor` que lo corre y explica el resultado.» «Por defecto solo lee: muestra una tabla OK / FALTA / AVISO con el comando que arreglaría cada ítem, pero no arregla nada. Para arreglar algo hay que pedirlo ítem por ítem: `--arreglar <id>`.»
- **S2** — Chequeos de la v1, ajustados por la evidencia de L2 (los ítems y su estado si fallan):
  - `repo-hooks` — en un clon de este repo, `core.hooksPath` = `.githooks`. FALTA si no. Arreglo automático: `git config core.hooksPath .githooks`.
  - `lista-negra` — en un clon de este repo, `tools/barrido.py --autoprueba` sale 0. FALTA si no (la lista se crea a mano: no hay arreglo automático).
  - `python` — `python` corre; AVISO si el que resuelve el PATH tarda más de 100 ms que el intérprete real (el alias de la Store). Arreglo manual: desactivar el alias de ejecución de `python.exe`, o poner `%LOCALAPPDATA%\Python\bin` antes de `WindowsApps` en el PATH.
  - `git-credenciales` — `credential.helper` configurado en algún nivel. FALTA si no.
  - `claude` — Claude Code ≥ 2.1.284 (la versión del spike S1). FALTA si es menor; AVISO si la versión no se puede leer.
  - `marketplace` — `odd-workspace-template` en `~/.claude/plugins/known_marketplaces.json`. FALTA si no. Arreglo automático: `claude plugin marketplace add https://github.com/sebasgc0399/odd-workspace-template.git`.
  - `gentle-ai` — ≥ 4.2.0. FALTA si falta o es menor.
  - `rdd` — `gentle-ai review mode status` en `off`. AVISO si está encendido (D3). Arreglo automático **solo con `--arreglar rdd`**: `gentle-ai review mode disable --scope global`.
  - `telemetria` — `gentle-ai telemetry status` en `disabled` (decisión del 2026-09-29). AVISO si no.
  - `engram` — ≥ 3.5.0. FALTA si falta o es menor.
  - `jq` — presente. FALTA si no.
- **S3** — Seguridad: el doctor solo invoca comandos de lectura conocidos. **Nunca** pasa `--help` ni invoca `upgrade` de gentle-ai (`gentle-ai upgrade --help` ejecuta el upgrade). Una prueba lo verifica.
- **S4** — Salida: tabla con id, estado, detalle y arreglo; código 0 sin FALTA, 1 con alguna FALTA (los AVISO no fallan). `--arreglar <id>`: corre el arreglo automático de ese ítem y vuelve a chequearlo; si el ítem no tiene arreglo automático, muestra la ayuda y sale con 2; un id desconocido sale con 2.

## Tasks

| ID | Specs | Ruta | Estado | Evidencia |
|---|---|---|---|---|
| T1 | S2, S3, S4 | inline, test primero | **hecho** | L3 |
| T2 | S1 (la skill) | inline | **hecho** | L3 |
| T3 | README y `Doc/diseno.md` | inline | **hecho** | L4 |

## Log

- **L1 (2026-10-24, Sebastián):** «Si arranca» — a la propuesta de alcance de T6 (fundación, L17).
- **L2 (2026-10-24): exploración.** Salidas reales: `claude --version` → `2.1.284 (Claude Code)`; `gentle-ai version` → `gentle-ai 4.2.0`; `gentle-ai review mode status` → `receipt-driven development: off (decided by global)`; `gentle-ai telemetry status` → `telemetry: disabled (source: GENTLE_AI_TELEMETRY)`; `engram version` → `engram 3.5.1`; `jq --version` → `jq-1.8.2`; `credential.helper` = `manager` a nivel sistema; `known_marketplaces.json` es un objeto con una clave por marketplace. **Ajustes al alcance propuesto:** (a) `diff.autoRefreshIndex` **sale**: el motor del proyecto de origen lo fija por proceso con `GIT_CONFIG_COUNT` en un solo lugar, no en la configuración de git; es un mecanismo del motor (viaja en T7), y exigirlo global duplicaría el mecanismo y cambiaría git en todos los repos. (b) `core.longpaths` **sale**: lo propuse sin un incidente que lo justifique (principio 2). (c) `telemetria` **entra**: una línea de lectura que verifica una decisión ya tomada. **Python medido por ruta explícita** (mediana de 9): el que resuelve el PATH (`WindowsApps\python.exe`) 214 ms; `%LOCALAPPDATA%\Python\bin\python.exe` (atajo del instalador, en el PATH pero después del alias) 50 ms; el intérprete real 49 ms. Trampa de medición: lanzar `python` **desde Python** no pasa por el alias (Windows busca primero en la carpeta del proceso padre), así que el doctor tiene que medir la ruta que da `shutil.which("python")`, no el nombre. `gentle-ai review mode disable --scope global` verificado en la fuente de gentle-ai 4.2.0 (`internal/cli/review_mode.go:61`: `--scope` vale `global` por defecto), sin correr `--help`.
- **L3 (2026-10-24): T1 y T2 hechos.** RED: 0/24 (`ModuleNotFoundError`). GREEN tras corregir el **doble de pruebas**, no el doctor: una clave corta de la prueba (`("jq",)`, «no instalado») no tapaba la clave larga del default (`("jq", "--version")`); ahora la tapa → 24/24. Mutación: si el doctor le pide `gentle-ai upgrade --help`, la prueba de seguridad se pone roja. **Corrida real** desde el clon: 0 FALTA, 1 AVISO (Python: el del PATH 204 ms, el real 51 ms), código 0. **B2b de punta a punta:** un clon nuevo nace con `core.hooksPath` vacío → `repo-hooks` FALTA, código 1 → `--arreglar repo-hooks` lo configura y vuelve a chequear → OK; el clon de prueba vivía en el scratchpad y se borró. Skill `plugin/skills/doctor/SKILL.md`: corre el script con `${CLAUDE_PLUGIN_ROOT}`, ofrece arreglos de a uno con autorización por ítem, `rdd` solo si el usuario pide apagarlo, nunca `--help` ni `upgrade` a gentle-ai, nunca mostrar la lista negra. `claude plugin validate` pasó en el plugin y en el marketplace. Entorno: el guard de comandos de la máquina exige que un `rm -rf` lleve la ruta literal del scratchpad, no una variable. Commit `784ba3f`.
- **L4 (2026-10-24): T3 hecho.** README: la puesta en marcha arranca por el doctor y su `--arreglar repo-hooks`. `Doc/diseno.md` §6: el alcance real de la v1 y lo que quedó afuera, con su razón; §8: el riesgo residual B2b lo cubre `repo-hooks`, verificado con un clon nuevo. La feature queda cerrada en la rama `feat/doctor`, sin push. Commit `7779594`.
- **L5 (2026-10-24, Sebastián):** «Si autorizo» — a subir los 4 commits. `main` local se adelantó a `47f88c3` (verificado como avance directo con `merge-base --is-ancestor`) y `git push origin main`: el `pre-push` corrió (autoprueba y barrido limpio) y `origin/main` pasó de `6c29dcb` a `47f88c3`. El guard de comandos de la máquina bloqueó el primer intento porque leyó el `-f` de `git branch -f` y el `git push` del mismo comando como un `push --force`; se separó en dos llamadas.
