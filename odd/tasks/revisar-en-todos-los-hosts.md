# Revisar en todos los hosts: el rescate de los revisores en Codex, los textos de Codex y Pi que engañan y las formas de veredicto que se escapan (R22)

Objetivo: que `/odd-ws:revisar` rescate y mida a los revisores en Codex como ya lo hace en Claude Code y en Pi (I53), que los textos de Codex y Pi digan lo que pasa, y que las formas de veredicto que todavía pasan como reporte se reconozcan.
Rama: `feat/revisar-en-todos-los-hosts`, en `D:/Project/odd-ws-wt/hosts`, apilada sobre la punta de la R21 (la `0.19.0`). Entrega: un commit por unidad. Sale en la `0.20.0`; el autor dio el ok para publicarla apenas esté lista (L1).
Pruebas: `python plugin/scripts/<script>.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites, con el `GIT_INDEX_FILE` del commit en el entorno.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap. Lo marcado como **decisión de diseño** lo decidió el orquestador con la autonomía del loop (L1), y queda a ratificar por el autor.

- **S1** (I53, el rescate en Codex). «Rescatar los reportes de los revisores en Codex.» Del roadmap: «`rescatar.py` solo lee los transcripts de Claude Code; R6 suma Pi, y Codex queda con el mismo hueco.»
  - **Decisión de diseño** (sobre la corrida real de L2):
    - `rescatar.py --host codex --corrida <nombre>=<thread_id>` busca el rollout del revisor en `sessions/*/*/*/rollout-*-<thread_id>.jsonl` del `CODEX_HOME` (por defecto `~/.codex`). Las carpetas y el nombre van en hora local, por eso el glob.
    - Comprueba que `session_meta.source.subagent.thread_spawn.agent_role` sea un revisor de la instancia.
    - **El reporte** es `last_agent_message` del último `task_complete`, sin la línea del veredicto, con la regla de Pi.
    - **Las lecturas** salen de los `item_completed` de tipo `CommandExecution` (el comando, la carpeta y el código de salida). Codex no tiene una herramienta de lectura: lee con el shell.
    - **El costo** suma los `token_usage_record`. En Codex, la caché leída es parte de la entrada, no un número aparte.
    - **El prompt** viaja cifrado en el rollout, así que el rescate no lo puede reconstruir. En Codex, el orquestador guarda el `.prompt.txt` antes de lanzar al revisor.
    - **El revisor se lanza a ciegas,** con `fork_turns: "none"`: con `"all"` hereda la historia del orquestador. `references/hosts.md` lo dice.
    - **Un límite que se documenta:** en Codex, el orquestador recibe el reporte entero, no solo el veredicto (I35).
    - El fixture de las pruebas es la corrida real de L2, limpia de rutas personales.
- **S2** (los textos que engañan). Del roadmap: «los textos de Codex y Pi que hoy engañan (el primer toque con la pausa, el rechazo en Pi y el move con edición en Codex)».
  - **Decisión de diseño** (el mapa de L2):
    - **(a) El primer toque con la pausa.** Cuando el primer toque bloquea y la pausa pregunta, el encabezado no dice «(el reintento pasa)», porque no pasa. Se conserva el prefijo que fija la prueba de hoy. Una prueba combinada en los tres hosts.
    - **(b) El rechazo en Pi.** El texto dice «este comando» también cuando lo que se frena es una edición. Para una edición o una escritura, dice «esta edición». Las pruebas de bash quedan iguales, byte a byte.
    - **(c) El move con edición en Codex.** `porque.contexto` devuelve nada cuando el origen no es un archivo, y el porqué se calla. Solo se calla cuando la ruta existe y no es un archivo.
- **S3** (las formas de veredicto). Del roadmap: «las formas de veredicto que todavía pasan como reporte (`Veredicto final:`, un emoji delante, `Verdict:`)».
  - **Decisión de diseño.** Una línea con las cuentas, `\d+ critical, \d+ warning, \d+ suggestion` en cualquier lugar y sin importar mayúsculas, cuenta como veredicto, y `VEREDICTO_RE` acepta `Veredicto final:` y `Verdict:` con un carácter que no es letra delante. Un reporte de varias líneas sigue siendo reporte.
- **S4** (la versión). Se actualizan el CHANGELOG de la `0.20.0`, la versión en los dos `plugin.json`, en `package.json`, el README y `Doc/`, y `huellas.json`. Después, un verificador independiente.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento y su espejo en engram | inline | hecha | |
| T1 | S1, S3 | El rescate en Codex y las formas de veredicto, los dos en `rescatar.py` | un writer, en paralelo con T2 (motivo: dos unidades con superficies disjuntas, de varios minutos cada una) | hecha (L4) | `103eec9` |
| T2 | S2 | Los tres textos que engañan | un writer, en paralelo con T1 | hecha (L3) | |
| T3 | S4 | El CHANGELOG, la versión y el verificador | docs inline; verificador delegado | pendiente | |

## Log

- **L1** (2026-11-26) El autor:
  - aprobó el plan de la R20 a la R22: «Sí, va ese orden»;
  - dejó el loop a criterio del orquestador: «Vale, te dejare trabajando en loop termina con las publicacion y las version tu te organizas trabaja como te deje ayer»;
  - dio el ok para publicar cada versión apenas esté lista: «La idea es ya tienes mis Ok, para empezar a publicar, para que vayamos avanzando».
- **L2** (2026-11-26) La corrida real de Codex, que pide el plan antes de S1. El autor la autorizó: «Si te autorizo que hagas lo necesito».
  - Una sola corrida de `codex exec`, de las dos permitidas, con el `codex.exe` 0.171 de la extensión de VS Code: el 0.144 del PATH esconde `agent_type`. Unos 242 mil tokens de entrada; la cuota del mes pasó del 43 % al 44 %.
  - Lo que mostró (engram `odd/revisar-en-todos-los-hosts/spike-codex`):
    - el prompt del revisor viaja cifrado, en el rollout del revisor y en el `spawn_agent` del orquestador;
    - el reporte y su veredicto llegan en un solo mensaje, y el orquestador lo recibe entero;
    - las lecturas son comandos del shell (`Get-Content`, `rg`, `Select-String`, `git grep`);
    - no corrió ningún `SubagentStop` para el revisor: el plugin lo registra solo para los writers;
    - con esfuerzo bajo, el revisor no vio una división por cero, así que las pruebas con hallazgos usan un reporte sintético.
  - El fixture limpio pasa `barrido.py --paths`. **Scratch:** `%TEMP%\tmp.GX7j5LH9JY`. Va a la limpieza del autor.
  - El mapa del explorador, sobre `7823093`, está en engram `odd/revisar-en-todos-los-hosts/mapa`.
- **L3** (2026-11-26) T2, un writer, desde `e2b6fec`, en paralelo con T1. Cubrió S2 (a), (b) y (c).
  - **(a)** Si alguna pausa pregunta, en la misma ruta o en otra del mismo parche de Codex, el encabezado del primer toque cierra con «(el reintento se frena en la pausa de abajo)» y no con «(el reintento pasa)». El prefijo y el orden de los textos no cambian.
  - **(b)** En Pi, el rechazo y la falla al pedir la confirmación de un `edit` o un `write` dicen «esta edición queda bloqueada». Con cualquier otra herramienta, el texto de antes, byte a byte.
  - **(c)** `porque.contexto` busca en `HEAD` el origen de un `Move to` con texto reemplazado, y calla si no está ahí.
  - **Las pruebas,** cada regla vista en RED y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `verificar_capa` 171/171, `codex` 48/48, `pi` 71/71 y `claude_code` 42/42;
    - `porque` 12/12 y `registro` 8/8;
    - con node, `pi.test.ts` 75, `corredores.test.ts` 8 y `nucleo.test.ts` 15, sin fallas.
    - Seis mutantes, atrapados.
  - **La diferencial contra `e2b6fec`:** de 28 escenarios en los tres hosts y el shim de Pi, 18 son idénticos. Los 10 que cambian son los tres casos buscados.
  - **Decisiones del writer que se aceptan:**
    - el encabezado cambia también cuando la pausa está en otro archivo del mismo parche de Codex;
    - el mismo final en los tres hosts;
    - en Codex, y en Pi sin pantalla, el bloque combinado todavía no trae la línea de «no se puede pedir la confirmación»: el agente la recibe en el reintento;
    - un origen sin trackear calla, sin «sin historia».
  - **El orquestador integró el texto de T2 en `Doc/diseno.md`.**
  - **Risk: ítem 3.** Los mensajes del hook y `porque.contexto` los comparten los tres hosts. La diferencial muestra cambios solo en los tres casos buscados. Lo cubre el verificador de T3.
  - **Scratch del writer:** `%TEMP%\tmp.g5uLRYZisd`, y 136 carpetas `%TEMP%\verificar-capa-test-*` de una corrida de las suites cortada a la mitad. Van a la limpieza del autor.
- **L4** (2026-11-26) T1, un writer, desde `e2b6fec`, en paralelo con T2. Cubrió S1 y S3.
  - **S1:** `rescatar.py --host codex --corrida <nombre>=<thread_id> [--sesion <CODEX_HOME>]`.
    - Busca el rollout con el glob y exige un `agent_role` de la forma `revisor-<...>`: si no, `FAIL … no de un revisor` y no escribe nada.
    - Escribe el reporte sin el veredicto, las lecturas de los `CommandExecution` y el costo (`transcripcion.costo_codex`, con la caché dentro de la entrada).
    - No escribe el `.prompt.txt`: lo guarda el orquestador antes de lanzar. Si ese prompt trae secretos, el rescate los tapa como en los otros hosts; sin secretos no lo toca.
    - `auditar_lecturas.py` pasa a `no_auditadas` lo que no sabe mirar, como un comando de shell. Antes, una corrida de Codex salía limpia sin que se mirara nada.
    - `references/hosts.md` dice cómo lanzar al revisor en Codex (`fork_turns: "none"`, un `task_name` por corrida, el prompt guardado antes) y cómo encontrar su `thread_id`.
  - **S3:** una devolución de una línea cuenta como veredicto si empieza con `VEREDICTO:`, `Veredicto final:` o `Verdict:`, con un carácter que no es letra delante, o si trae las cuentas en cualquier lugar.
  - **Las pruebas,** cada regla vista en RED y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `rescatar` 82/82, `transcripcion` 23/23 y `auditar_lecturas` 37/37;
    - `puntuar` 40/40, `registro` 8/8, `memorias` 43/43, `recibo` 120/120 y `tapar` 11/11.
    - Ocho mutantes, atrapados.
    - Una prueba sobre el rollout real de L2, en el scratch, dio los mismos totales que el rollout.
  - **La diferencial contra `e2b6fec`:** los 19 casos de Claude Code y Pi salen idénticos, byte a byte. Lo que cambia son las formas nuevas de S3 y el texto de uso.
  - **Decisiones del writer que se aceptan:**
    - el orquestador no ve el `thread_id`, porque `spawn_agent` devuelve solo el `task_name`: `hosts.md` dice cómo buscarlo por el `agent_path`;
    - una lectura de Codex lleva además la clave `exit`;
    - el costo de Codex usa las claves de Pi, con `costo_usd` en `null`;
    - con varios rollouts para un id, toma el último por nombre;
    - el fixture de las pruebas es mínimo y va en la prueba, con la forma real: el rollout de 98 KB no entra al plugin.
  - **Una corrección del orquestador, antes del commit:** el prompt que guarda el orquestador en Codex no pasaba por `secretos.tapar`, como sí pasa en los otros hosts. El writer lo sumó, con su prueba y su mutante.
  - **El orquestador integró el texto de T1 en `Doc/diseno.md`.**
  - **Risk: ítem 3.** Cambian la CLI de `rescatar.py` (un host nuevo), qué cuenta como veredicto en todos los hosts y lo que `auditar_lecturas.py` cuenta como auditado. Lo cubre el verificador de T3.
  - **Scratch del writer:** `%TEMP%\tmp.0QtEBnarWg`. Va a la limpieza del autor.
