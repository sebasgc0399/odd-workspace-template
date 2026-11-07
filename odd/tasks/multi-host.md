# Multi-host: odd-ws en varios CLI de agentes

Objetivo: que odd-ws corra en otros CLI además de Claude Code, con un núcleo común y un adaptador por CLI, agregando un CLI por entrega. Rama: `feat/multi-host`, a crear desde `main` (`4b423c6`) al arrancar F0a. Entrega: `ask-on-risk`, un commit por unidad, push solo con autorización, y cada F# cierra con su versión. Runner: Python sin pytest, `<nombre>.tests.py` junto a cada script. Espejo en Engram: `odd/multi-host/tasks`.

## Specs

- **S1. El pedido (L1).** «lo vamos agregando 1 por 1, pero toca plantearlo bien para que soporte varios»: un CLI por entrega, sobre una base común que se diseña primero.
- **S2. Puertos y adaptadores.**
  - **Núcleo.** Es la lógica que ya no depende del host, cerca del 87 % de `plugin/scripts` (L2). Se le suma un modelo de eventos neutral:
    - herramienta: fase pre o post; tipo edición, lectura o shell; rutas (una o varias); comando; dialecto de shell; agente con nombre o principal; sesión; cwd;
    - inicio de sesión: su origen;
    - fin de subagente: agente, mensaje final y si ya se reintentó.

    Las decisiones también son neutrales: permitir, bloquear(motivo), preguntar(motivo), contexto(texto) y seguir(motivo).
  - **Adaptador de protocolo por host.** Traduce el payload al evento y la decisión al protocolo del host (exit code, JSON):
    - los hosts con hooks de comando (Claude Code, Codex, Copilot CLI, Gemini CLI) se adaptan en Python;
    - los hosts con plugins en TS (OpenCode) usan un shim delgado que llama al mismo punto de entrada de Python.
  - **Adaptador de generación por host.** Cubre lo que escribe el bootstrap (archivo de instrucciones, agentes, skills, habilitación del plugin), el doctor y el layout de la instancia, que hoy está centralizado en `odd_ws/capas.py`.
  - **A decidir en F0a:** `writer_stop` saca del transcript los archivos que tocó el writer (L2). La alternativa neutral es derivarlos de la foto previa que ya toma `writer_guard` y no leer transcripts.
- **S3. Manifiesto de capacidades por host (L4, lección de gentle-ai).** Cada host declara P1–P10 (ver la matriz) como `soportado`, `degradado` (con el fallback escrito) o `no disponible`, y un test cruza el manifiesto con lo que el adaptador dice soportar. Lo que falta se declara; nunca se simula. `eval-reviewers` y `rescatar` arrancan como «solo Claude Code»: leen el JSONL de sus transcripts.
- **S4. La degradación falla cerrada.**
  - Si un host no puede preguntar, el guard bloquea con el motivo en vez de dejar pasar. El caso real: en Codex 0.167, un hook que devuelve `ask` falla y la herramienta corre igual (L3).
  - Si un host no tiene compuerta de fin de subagente o no da la identidad del agente, el writer queda `no disponible` en ese host y el doctor lo dice.
- **S5. Cero cambio en Claude Code.** F0 se valida con un diferencial contra `main` en cada hook: la misma entrada da la misma salida y el mismo exit code. Riesgo: ítem 2 (los guards) e ítem 3 (`hooks.json` y lo que genera el bootstrap), así que F0a lleva un verificador independiente.
- **S6. D1, resuelta (L7): varios CLI a la vez en un mismo workspace.**
  - `.claude/` sigue siendo la única fuente de verdad: reglas, criterios, estado y tickets. No se migra nada en las instancias que ya existen.
  - Cada host recibe solo sus archivos delgados generados, por ejemplo los agentes TOML de Codex.
  - El archivo de instrucciones (`CLAUDE.md` o `AGENTS.md`) se decide en F1, sin duplicar contenido.
- **S7. El orden de los CLI, del usuario (L6).** «Prioridad Codex, Gentle-Shell o si hay mas de la comunidad y luego OpenCode, luyego Gemini y de ultimo Copilot».

### Matriz de capacidades (2026-11-07)

| Capacidad | Claude Code | Codex 0.167 | Copilot CLI | Gemini CLI 0.67 | OpenCode V2 2.2.6 |
|---|---|---|---|---|---|
| P1 contexto al iniciar | sí | sí (`source` incluye `compact`) | sí | parcial: no hay `compact` | parcial: no distingue el origen |
| P2 bloquear una edición | sí | sí, parseando las rutas de `apply_patch` | sí, parseando `apply_patch` | sí | sí |
| P3 guard de shell que pregunta | sí | bloquea; preguntar no (`ask` falla abierto) | bloquea; `ask` interactivo, a verificar | bloquea; `ask` no documentado, hay política TOML | sí (`permission.evaluate`) |
| P4 post-edición y lecturas | sí | edición sí; lecturas no (no hay tool de lectura) | sí | sí | da contexto, no bloquea |
| P5 compuerta de fin de subagente | sí | sí | sí, con un tope de 8 bloqueos | no | parcial: solo `experimental.idle` |
| P6 identidad del agente en los hooks | sí | sí (`agent_id`, `agent_type`) | sí; el payload por evento, a verificar | no | sí |
| P7 subagentes propios | sí | parcial: TOML sin lista de tools, y el plugin no los trae | a verificar | parcial (`.gemini/agents`) | parcial: el plugin no los trae |
| P8 skills del plugin | sí | sí (SKILL.md) | a verificar | sí, sin namespace | parcial: por código |
| P9 distribución | sí | sí, lee `.claude-plugin` | sí, lee `.claude-plugin` | sí (`gemini-extension.json`) | parcial: npm, sin raíz del plugin |
| P10 instrucciones por carpeta | sí (CLAUDE.md apilado) | parcial: AGENTS.md, al arrancar | a verificar | sí (GEMINI.md, carga JIT) | sí (AGENTS.md, carga diferida) |

gentle-shell todavía no está investigado. Corre sobre Pi y se instala con `npm i -g gentle-pi` (L6). De Pi se sabe esto:
- `tool_call` bloquea con `{block, reason}` y puede preguntar con `ctx.ui.confirm`;
- después de la herramienta corre `tool_result`;
- no trae subagentes nativos, y gentle-shell los agrega (a verificar en F2).

## Tasks

| ID | Specs | Qué | Ruta | Estado |
|---|---|---|---|---|
| F0a | S2, S5 | Modelo de eventos y decisiones en el núcleo, y el adaptador de Claude Code, sin cambio de comportamiento (diferencial) | delegado: un writer, por el respaldo de contexto de una sesión larga (L8); después, un verificador independiente (S5) | hecho (`dcad0d9`, L9) |
| F0b | S3, S4 | Manifiesto de capacidades y su test de paridad, con Claude Code como primer host. Suma un test que falla si un núcleo emite una decisión que el host no puede expresar, que hoy calla (aviso 6 de L9) | inline | hecho (L10); commit en curso |
| F0c | S2, S6 | Generación por host: bootstrap y doctor parametrizados, con `.claude/` como fuente de verdad | inline | pendiente |
| F1 | S2–S4 | Codex: adaptador, manifiesto, `ask` → bloqueo, rutas de `apply_patch`, agentes TOML y el trust de hooks en el doctor. Además: inyectar el adaptador según el host y sacar del núcleo los nombres de Claude Code (`MultiEdit`, `PowerShell`), que son los avisos 3 y 4 de L9 | por decidir | pendiente |
| F2 | S2–S4, S7 | gentle-shell sobre Pi: al arrancar, investigar sus hooks y sus subagentes. El mismo adaptador TS cubre Pi | por decidir | pendiente |
| F3 | S2–S4, S7 | OpenCode V2: shim TS → Python y la compuerta sobre `experimental.idle`. Reusa el shim de F2 si encaja | por decidir | pendiente |
| F4 | S2–S4, S7 | Gemini CLI: writer `no disponible`, o el rodeo de `complete_task` (sin probar) | por decidir | pendiente |
| F5 | S2–S4, S7 | Copilot CLI: verificar antes los nombres de las tools y el payload de cada evento | por decidir | pendiente |
| X1 | — | Fuera del alcance: `MultiEdit` no está en ningún matcher de `hooks.json`, aunque `writer_guard.py:27` y `writer_stop.py:16` la tratan como escritura (L2) | inline, aparte | pendiente |

## Log

- **L1 (2026-11-07), el pedido:** «Me interesa, que lo ampliemos, deberiamos investigar hacer una plan y roadmap, y lo vamos agregando 1 por 1, pero toca plantearlo bien para que soporte varios». Origen: en el foro de la comunidad de Gentleman Programming, dos personas preguntaron si funciona fuera de Claude Code.
- **L2, el mapa interno.** De unas 10.100 líneas de `plugin/scripts` sin tests, el pegamento suma unas 1.300 (≈13 %): los envoltorios de los 4 hooks, la mayor parte de `doctor.py`, `rescatar.py`, `bootstrap_agentes`, `bootstrap_instalacion`, `transcripcion` y `capas.py`.
  - **La identidad del writer** sale solo de `agent_type`/`agent_id` en el payload (`writer_guard.py:1117`, `verificar_capa.py:249`).
  - **`writer_stop`** lee `agent_transcript_path` y `last_assistant_message` (`writer_stop.py:300-324`).
  - **Lo más difícil de portar:**
    - la compuerta del writer;
    - la semántica de salida: exit 2 con reintento, `additionalContext` y `ask`;
    - una sola `file_path` por llamada;
    - los transcripts JSONL;
    - el modelo de agentes y de contexto.
  - **`MultiEdit`:** queda fuera de los matchers. Verificado con grep (X1).
- **L3, Codex y OpenCode.**
  - **Codex `rust-v0.167.0` (2026-11-06):**
    - tiene `SessionStart`, `PreToolUse`/`PostToolUse` y `SubagentStop`, con matcher por `agent_type`;
    - da `agent_id`/`agent_type` dentro de los subagentes;
    - lee `.claude-plugin` y expone `PLUGIN_ROOT` y `CLAUDE_PLUGIN_ROOT`;
    - `ask` falla abierto, y preguntar solo se puede con `.rules` (experimental);
    - no hay tool de lectura;
    - los hooks necesitan una revisión de trust en `/hooks`.
  - **OpenCode:** conviven V2 `v2.2.6` (la línea a apuntar) y V1 `v1.19.5` (todavía «Latest» en npm), con plugins incompatibles entre sí. V2:
    - tiene plugins en TS/Promise, sin hooks de comando;
    - `permission.evaluate` puede preguntar;
    - la compuerta de subagente solo existe por `experimental.idle`;
    - un plugin no puede traer agentes;
    - no hay variable de entorno con la raíz del plugin.
  - **Fuentes:** https://learn.chatgpt.com/docs/hooks, https://github.com/openai/codex/releases/tag/rust-v0.167.0, https://opencode.ai/v2/docs/build/plugins/server y https://github.com/anomalyco/opencode/releases.
- **L4, Gemini CLI, gentle-ai y otros CLI.**
  - **Gemini CLI v0.67.0 (2026-11-04):**
    - `BeforeTool`/`AfterTool` cubren P2 a P4;
    - no hay evento de subagente: `hooks migrate --from-claude` mapea `SubagentStop` a `AfterAgent`, que es otra semántica;
    - la entrada de los hooks no trae identidad (issue #25033, abierto);
    - los hooks de herramienta sí corren dentro de los subagentes, sin identidad.
  - **gentle-ai v4.3.1 soporta 18 runtimes**, y su diseño es el modelo a calcar:
    - una interfaz `Adapter` por runtime (`internal/agents/<agente>/adapter.go`);
    - un manifiesto de capacidades cruzado por test contra los `Supports*()` de cada adapter (`internal/agents/capabilitymanifest/`);
    - degradación tipada (`unavailable` nunca se vuelve PASS);
    - renders por host con tests de paridad.

    Instala hooks solo en Claude Code y Codex.
  - **Copilot CLI:**
    - lee `.claude-plugin/plugin.json`;
    - tiene `subagentStop` que bloquea y obliga a seguir;
    - da `agentId`/`agentType` dentro de los subagentes;
    - `sessionStart` acepta `additionalContext`, y `postToolUse` también;
    - sus tools son `bash`, `view`, `apply_patch`, `glob`, `rg` y `task`.

    Lo confirmé con un segundo lector (L5).
  - **Estándares compartidos:** Agent Skills (SKILL.md) lo adoptaron casi todos; AGENTS.md también; Agent Plugins 1.0 cubre `plugin.json`, `skills/` y `mcp.json`, pero no los hooks.
  - **Fuentes:** https://github.com/google-gemini/gemini-cli/blob/v0.67.0/docs/hooks/reference.md, https://github.com/Gentleman-Programming/gentle-ai, https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-hooks-reference, https://agents.md/ y https://github.com/agentplugins/agent-plugins-spec.
- **L5, verificación de Copilot CLI.**
  - Se confirmaron, citando la página: `subagentStop` «can block and force continuation»; los campos de identidad dentro de los subagentes; la lectura de `.claude-plugin`; y `additionalContext` en `sessionStart`.
  - Quedan sin verificar:
    - `ask` en modo interactivo;
    - el payload de `preToolUse` con la identidad;
    - si los hooks de comando fallan cerrados (eso sale de un resumen, no de una cita).
- **L6 (2026-11-07), el orden de los CLI.**
  - **En el foro aclararon** que «agente» quiere decir el CLI, y pusieron gentle-shell y Codex como ejemplos.
  - **El usuario:** «tambien deberiamos pensar en integrar tamen Gentle-shell los CLI que usan esta comunidad, Prioridad Codex, Gentle-Shell o si hay mas de la comunidad y luego OpenCode, luyego Gemini y de ultimo Copilot».
  - **Las tareas se reordenaron:** F1 Codex, F2 gentle-shell, F3 OpenCode, F4 Gemini, F5 Copilot.
  - **gentle-shell** es un agente de código sobre Pi, de Gentleman Programming. Se instala con `npm i -g gentle-pi`; el repo y el paquete siguen llamándose gentle-pi mientras dura la migración del nombre. Fuentes: https://github.com/Gentleman-Programming/gentle-shell/wiki y https://cdn.jsdelivr.net/npm/gentle-pi@4.5.1/README.md.
- **L7 (2026-11-07), D1.**
  - **La propuesta:** varios CLI a la vez, con `.claude/` como fuente de verdad y sin migrar instancias.
  - **El porqué:** Codex y Copilot leen `.claude-plugin`, OpenCode lee `.claude/skills` y las rutas ya están centralizadas en `capas.py`. Cambiar después un layout ya persistido es el cambio más caro.
  - **El usuario:** «Vale me parece bien».
- **L8 (2026-11-07), el arranque de F0a.**
  - La rama `feat/multi-host` sale de `main` (`4b423c6`). El plan es el commit `5bb9c3e`.
  - **Decisión técnica del padre sobre S2:** en F0a, `writer_stop` sigue leyendo el transcript (cero cambio), pero esa lectura pasa a vivir en el adaptador de Claude Code. La alternativa de la foto previa se decide en F1, cuando un host la necesite.
  - **La ruta:** un writer, por el respaldo de contexto. La sesión ya es larga.
- **L9 (2026-11-07), F0a escrito y verificado.**
  - **El writer.** Agregó `odd_ws/eventos.py`, `odd_ws/hosts/claude_code.py` (`leer`, `responder`, `atender`, más el transcript) y un `decidir(evento, …)` en cada uno de los cuatro hooks. No tocó `hooks.json`.
    - RED: 0/7 y 0/18 (`ModuleNotFoundError`). GREEN: 7/7 y 18/18.
    - Su diferencial contra `main` dio 255/255 idénticos. Con 5 mutaciones lo marcó 30 veces, así que el instrumento sabe decir que sí. De ahí salieron 3 regresiones nuevas.
  - **El verificador independiente.** Usó su propio corpus de unas 3.400 entradas: 2669/2669 sin estado, 626/626 con estado y 140/140 de dialecto, todas idénticas. Ningún bloqueante; S2 y S5 cumplen. De sus avisos:
    - 1 y 2: un bloqueo con un surrogate suelto en el texto callaba. En guard_comandos el cambio lo había introducido (antes preguntaba); en writer_guard ya venía de la base. Se corrigió en el adaptador con `encode("utf-8", "replace")`, que falla cerrado (S4), con un test que dio RED antes del arreglo.
    - 5: `Doc/diseno.md` decía que el adaptador solo normaliza `rutas` y `comando`; ya está corregido.
    - 3 y 4: el núcleo importa el adaptador fijo y todavía nombra `MultiEdit` y `PowerShell`. Van a F1.
    - 6: una combinación sin protocolo calla. Va a F0b.
  - **El padre.** Volvió a correr 2 suites (18/18 y 44/44), con el mismo resultado que reportó el writer.
  - `review assess` dio `unassessable` por los archivos sin trackear. El riesgo se nombró igual (ítem 2) y el verificador corrió.
  - **Sobrantes fuera del scratch** que tiene que borrar el usuario: `%TEMP%\guarda-test-6n4pk2w3` y `%TEMP%\guarda-test-ac0fg8x0`.
- **L10 (2026-11-07), F0b inline.** F0a quedó en `dcad0d9`.
  - **Qué se hizo:**
    - `odd_ws/capacidades.py`: los estados, los cuatro puntos de evento, P1 a P10 y los `REQUISITOS` de P1 a P5;
    - `odd_ws/hosts/__init__.py`: el registro `ADAPTADORES`;
    - en el adaptador de Claude Code: `EXPRESABLES` y `MANIFIESTO`, todo soportado y con su mecanismo;
    - un `EMITE` en cada hook.

    No cambia nada en tiempo de ejecución.
  - **Tests:** RED 0/8 (`ModuleNotFoundError`, `AttributeError`), GREEN 8/8.
  - **Control positivo con mutantes en memoria:**
    - sacar `Preguntar` de `pre` en el adaptador lo atrapan 3 tests;
    - declarar en `writer_guard` un tipo que no construye lo atrapa el chequeo `ast`.

    Mover una decisión de punto no lo atrapa nadie: es el límite que quedó escrito en `Doc/diseno.md`.
  - **Decisión técnica del padre:** la degradación (`Preguntar` → `Bloquear` en un host que no puede preguntar) se implementa en el `responder` de ese adaptador, en F1. No va en `atender`, para no tocar el camino de los guards de Claude Code.
  - **Risk: none.** Son datos y tests; el comportamiento de los hooks no cambia.
- **Siguiente paso:** el commit de F0b; después, F0c.
