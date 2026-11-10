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
- **S8. Los hosts se declaran (L17).** `workspace.config.json` lleva una clave opcional `hosts`, por ejemplo `["claude-code", "codex"]`. Sin la clave, el workspace es solo Claude Code, y las instancias que ya existen no cambian. La instalación genera los archivos de un host, y el doctor lo revisa, solo si está declarado.

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
| F0b | S3, S4 | Manifiesto de capacidades y su test de paridad, con Claude Code como primer host. Suma un test que falla si un núcleo emite una decisión que el host no puede expresar, que hoy calla (aviso 6 de L9) | inline | hecho (`6db4105`, L10) |
| F0c | S2, S6 | Se juntó con F1 (L11): la generación por host se diseña con Codex como segundo caso real | — | fusionada en F1 |
| F1a | S2–S4 | Adaptador de protocolo de Codex (`odd_ws/hosts/codex.py`) y elección del adaptador con `--host` en los tres guards (aviso 3 de L9). Detalle:<br>• `apply_patch` es edición, con las rutas del parche (`Add`, `Update`, `Delete` y `Move to`) resueltas contra el `cwd`<br>• `Bash` es shell, con dialecto según la plataforma: PowerShell en Windows<br>• `Preguntar` se degrada a bloqueo con la instrucción de pedirle al usuario que lo corra (S4)<br>• `DEGRADACIONES` en el manifiesto<br>• los guards procesan todas las rutas de un evento | delegado: un writer, por el respaldo de contexto; después, un verificador (ítem 2) | hecho (`f8a9b88`) |
| F1b | S2, S4 | `writer_stop` en Codex. `writer_guard` anota en `.claude/estado` las rutas y los comandos de cada writer, y el adaptador de Codex lee esa bitácora en vez del transcript (la alternativa neutral de S2). Claude Code sigue con su transcript. Hasta F1b, P5 de Codex queda `no disponible` | delegado: un writer, por el respaldo de contexto; después, un verificador (ítem 2: `writer_guard` y `writer_stop`) | hecho (`c3736ff`, L14) |
| F1c | S2–S4 | Empaquetado y bloqueo por JSON (L15). Detalle:<br>• `.codex-plugin/plugin.json` con la misma versión que `.claude-plugin`, `"hooks": "./hooks/hooks.codex.json"`, sin `skills` (Codex descubre `skills/`) y sin `plugin.json` en la raíz<br>• `hooks/hooks.codex.json`: comandos como string, `python "${PLUGIN_ROOT}/scripts/<x>.py" --plazo N --host codex`, con matchers `apply_patch` y `Bash`, sin `Read` ni `PowerShell`<br>• `writer_stop` se registra con `--host codex`, y `writer_guard` va en `apply_patch` y en `Bash`, porque sin él la compuerta no ve nada (L14)<br>• el adaptador de Codex bloquea por JSON y exit 0, nunca con exit 2<br>• un test de paridad entre los dos `hooks*.json` | delegado: un writer, por el respaldo de contexto; después, un verificador (ítem 2: el bloqueo de los guards en Codex) | hecho (`167132d`, L16) |
| F1d1 | S2, S5, S6, S8 | Generación (la ex F0c), solo para los hosts declarados en `hosts` (S8, L17). Detalle:<br>• `hosts` en `workspace.config.json`, validado contra el registro<br>• un puerto de generación por adaptador<br>• marcadores por host en las plantillas, que en Claude Code valen el texto de hoy<br>• `.codex/agents/*.toml` derivados del `.md`<br>• `.codex/config.toml` con `project_doc_fallback_filenames = ["CLAUDE.md"]`, sin ningún `AGENTS.md`<br><br>Claude Code genera lo mismo, byte a byte | delegado: un writer, por el respaldo de contexto; después, un verificador (ítem 5: el bootstrap es el instalador de la instancia) | hecho (`932d733`, L19) |
| F1d2 | S2–S4, S8 | Doctor por host (L17):<br>• Codex: la versión, el plugin instalado y la confianza de los hooks y del proyecto<br>• `codex-agentes` (L18): cada TOML se compara con el que sale del `.md` actual. Si falta, se genera; si está atrasado y su huella coincide, da `FALTA` y `--arreglar` lo re-deriva; si fue editado a mano, da `AVISO` sin pisarlo y pide editar el `.md`. Se compara contra la derivación completa y no contra `# odd-ws-plantilla: N`, que no sube cuando cambian los textos de Codex (A5 del verificador de F1d1)<br>• `hooks-host` en todos los hosts: ningún hook con un `--host` desconocido o vacío (A5 de L14, A2 de L16)<br>• `claude` no es `FALTA` si la instancia no lo declara<br>• el bootstrap ya promete «lo deriva de ahí el doctor (doctor --arreglar)»: F1d2 la cumple, e idealmente suma el id del arreglo a esa línea (A6 de L19) | delegado: un writer, por el respaldo de contexto; después, un verificador (ítem 5) | hecho (`39f46e4`, L20) |
| F1f | S4, S5 | Lo que encontró el humo (L23):<br>• A: en Codex, el primer toque no se saltea por las skills del frontmatter, porque Codex no las precarga<br>• D: documentar la config de Codex que necesita un writer en Windows<br>• B pasó a X7 (L25) | inline; después, un verificador (ítem 2: `verificar_capa`) | hecho (`d205677`, L26) |
| F1e | S1 | Prueba de humo en el Codex local (0.144 sirve para los hooks), con un `CODEX_HOME` aparte (L21), y entrega `0.3.0` | inline; el usuario hace el login y la confianza en `/hooks` | hecho (L22–L24 y L27) |
| M1 | S4 | Un CI que corra todas las suites en Windows, Linux y macOS (L30). Hoy las suites solo corren en el pre-commit de una máquina Windows, y el único workflow es `release.yml` | inline | hecho (L34) |
| M2 | S4 | Un arranque de Python portable. Los 13 hooks llaman a `python`, que no existe en una Mac típica, y entonces el hook no arranca y los guards fallan abiertos. En Codex: `command` con `python3` y `commandWindows` con `python`. En Claude Code: por investigar (L30) | delegado: un writer, por el respaldo de contexto; después, un verificador (ítems 2, 3 y 5) | hecho (L34) |
| M3 | S4, S5 | Todas las suites en verde en Linux y macOS (L32). Separar los tests que asumen Windows de los bugs del producto fuera de Windows; primero `guard_comandos`, por ser un guard. Fijar `windows-2022` si `windows-latest` sigue sin crear el job (L35: ya lo crea) | delegado: M3a, M3b y M3c en paralelo (Writer trigger a); el padre, `writer_guard.tests` y `verificar_capa.tests`. M3c `1cfd042`, M3b `04d0674` y M3a `0a1af09`; entrega `0.3.1` en `906864b`; M3a y M3b con verificador independiente y rechequeo cerrado (L39-L42) | hecho (CI verde, L43) |
| F2 | S2–S4, S7 | gentle-shell sobre Pi: al arrancar, investigar sus hooks y sus subagentes. El mismo adaptador TS cubre Pi | por decidir | pendiente |
| F3 | S2–S4, S7 | OpenCode V2: shim TS → Python y la compuerta sobre `experimental.idle`. Reusa el shim de F2 si encaja | por decidir | pendiente |
| F4 | S2–S4, S7 | Gemini CLI: writer `no disponible`, o el rodeo de `complete_task` (sin probar) | por decidir | pendiente |
| F5 | S2–S4, S7 | Copilot CLI: verificar antes los nombres de las tools y el payload de cada evento | por decidir | pendiente |
| X1 | — | Fuera del alcance: `MultiEdit` no está en ningún matcher de `hooks.json`, aunque `writer_guard.py:27` y `writer_stop.py:16` la tratan como escritura (L2) | inline, aparte | pendiente |
| X2 | — | Fuera del alcance, ya estaba en `6db4105`: en el dialecto PowerShell, ``g`it push --force origin main`` pasa por `guard_comandos`, en Claude Code y en Codex (aviso 5 de L13) | inline, aparte | pendiente |
| X3 | — | Fuera del alcance: con la config rota, `SessionStart` con `fork` no avisa (`ORIGENES_DEL_AVISO` de `verificar_capa.py`); conviene tratarlo como `resume` (aviso 3 de L13) | inline, aparte | pendiente |
| X4 | — | Fuera del alcance, ya estaba en `f8a9b88`: en Claude Code, un transcript ilegible, o con una ruta con un surrogate suelto, da «nada tocado» sin dejar falta (A9 de L14). S5 no dejaba cambiarlo en F1b | inline, aparte | pendiente |
| X5 | — | Fuera del alcance: un writer puede borrar su propia bitácora, o su transcript en Claude Code, con una llamada permitida, y la compuerta calla (paridad con la base); y un enlace duro plantado en lugar de la bitácora hace que el hook anote en otro archivo. Propuesta: proteger `.claude/estado/writers` de los writers en `writer_guard`, y un `lstat` antes del append (A1 y A2 de L14) | inline, aparte | pendiente |
| X7 | — | Hallazgo B de la prueba de humo (L24): con Codex 0.167 en Windows y `[windows] sandbox = "unelevated"`, `writer_stop` mide 0/0 las líneas de un writer. La foto es correcta, y el mismo código fuera de Codex da 1/1, así que el entorno de los hooks hace que `git diff --no-index` no vea la diferencia. Para cerrarlo: instrumentar el hook en una instancia de prueba y ver qué devuelve `git` ahí. Afecta solo la medición de líneas, no los bloqueos | inline, aparte | pendiente |
| X6 | — | Fuera del alcance, ya estaba en la base: un borrado no suma líneas, porque `lineas_reales` salta lo que no existe aunque la `.foto` tenga el contenido previo. En Codex se alcanza con `*** Delete File:` (A6 de L14) | inline, aparte | pendiente |
| X8 | — | Una clave de `[projects]` de Codex escrita a mano con un alias de la raíz del repo da un AVISO falso en `codex-proyecto`, que falla cerrado. Se arregla en `hosts/codex.py` `_proyecto` (L36) | inline, aparte | pendiente |
| X9 | — | Ya estaba en la base de Windows: con Git Bash, `rm -rf <scratch>/.\./.\./fuera` pasa la capa 1, porque bash lee `\` como escape. S5 congeló Windows en M3; en POSIX ya falla cerrado (L40) | inline, aparte; cambia la salida en Windows | pendiente |
| X10 | — | Ya estaba en la base: tres escapes del scratch de `writer_guard`: `.\.`, `enlace/..` y `Join-Path` con `..` (L40) | inline, aparte; ítem 2 | pendiente |
| X11 | — | Ya estaba en la base: `rutas.ubicar` colapsa `..` como texto, así que en POSIX la capa 2 y `writer_guard` no ven un `enlace/..` (`git -C /tmp/l/.. push`). Propuesta: que en POSIX lo resuelva `canonica` (L40, N1 de L42) | inline, aparte; ítems 2 y 3 | pendiente |
| X12 | — | Fuera de dominio hoy: en PowerShell sobre POSIX, `Remove-Item <scratch>/dentro/../../x`, con un enlace interno, podría salir del scratch si pwsh resuelve `..` como texto (L42) | cuando un host dé PowerShell en POSIX | pendiente |

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
- **L11 (2026-11-07), F0c.** F0b quedó en `6db4105`.
  - **La propuesta:** juntar F0c con F1, para no adivinar la interfaz de generación teniendo un solo host. Codex trae el segundo caso real: agentes TOML, `AGENTS.md` y el trust de hooks.
  - **El usuario:** «tomare tu recomendacion».
- **L12 (2026-11-07), investigación puntual de Codex para F1.** Se leyó el código de los tags 0.144.0 y 0.167.0.
  - **Hooks de un plugin de Claude.** Codex carga `.claude-plugin/plugin.json` y `hooks/hooks.json`, pero **ignora `args` en silencio**: el handler solo tiene `command`, `commandWindows`, `timeout` y `statusMessage`. El padre lo verificó en `protocol/src/hooks.rs`.
    - Hoy, la 0.2.2 instalada en Codex corre `python` sin script, y los guards quedan muertos (fallan abiertos).
    - `.codex-plugin/plugin.json` gana sobre `.claude-plugin`, y su `hooks` reemplaza a `hooks/hooks.json`.
    - `${CLAUDE_PLUGIN_ROOT}` se reemplaza como texto.
    - Los matchers son por igualdad, o regex si traen otros caracteres. `Edit` y `Write` son alias de `apply_patch`. `PowerShell` y `Read` nunca disparan.
    - El timeout va en segundos.
  - **Detectar el host:** lo fiable es `--host codex` en los comandos de Codex. El entorno se hereda y es frágil.
  - **Herramientas y payloads:**
    - `apply_patch` trae el parche entero en `tool_input.command`, con la gramática `*** Add/Update/Delete File:` y `*** Move to:`. Las rutas relativas se resuelven contra el `cwd`.
    - La shell es siempre `Bash`, con `command` como string; en Windows corre PowerShell.
    - No hay herramienta de lectura.
  - **SubagentStop:** trae los mismos campos que Claude Code, y `agent_type` es el `name` del TOML. Bloquear y seguir funciona igual.
  - **Lo que falla abierto:** `ask`, los timeouts y los errores. Los plugins no pueden traer `.rules`.
  - **Confianza:**
    - es por handler y se guarda en `~/.codex/config.toml` (`[hooks.state]`, `trusted_hash`);
    - en 0.167 el hash cubre todo el plugin, así que cada actualización pide `/hooks` de nuevo;
    - un hook sin confianza no corre;
    - la config del proyecto no puede pre-confiar.
  - **Agentes:** van en `.codex/agents/*.toml` (`name`, `description`, `developer_instructions` y claves de config). No hay lista de herramientas ni skills precargadas.
  - **Instrucciones:** `AGENTS.md` o los nombres de `project_doc_fallback_filenames`, desde la raíz hasta el `cwd`, con un tope de 32 KiB, sin imports y sin carga diferida.
  - **Skills:** `disable-model-invocation` no se respeta. El equivalente es `agents/openai.yaml`, con `allow_implicit_invocation: false`.
  - **0.144 frente a 0.167:** el contrato de hooks es el mismo. La 0.144 no tiene el hash por contenido ni `fork`.
  - **Decisiones técnicas del padre:**
    - F1 se parte en F1a a F1e.
    - **Archivos tocados en Codex:** el transcript de Codex tiene otro formato, así que se usa una bitácora neutral que escribe `writer_guard` (F1b).
    - **Preguntar:** se degrada a bloqueo dentro del `responder` de Codex.
    - **Instrucciones:** `CLAUDE.md` sigue siendo la fuente y Codex lo lee por fallback; un `AGENTS.md` taparía el `CLAUDE.md` de su carpeta.
- **L13 (2026-11-07), F1a.** Quedó en `f8a9b88`.
  - **Ruta:** un writer delegado, por el respaldo de contexto, y después un verificador independiente, por el ítem 2 (los guards).
  - **El writer:** el adaptador de Codex, `odd_ws/hosts/base.py`, `--host` en los tres guards con falla cerrada, varias rutas por evento (`por_ruta` y `combinar`) y `DEGRADACIONES` con la regla de implicación del manifiesto. RED observado en los tests nuevos y 9 de 10 mutantes muertos; el que sobrevivió era equivalente, y se quitó el chequeo redundante.
  - **El verificador:** S3 cumplido; S2 parcial y S4 en riesgo por dos fallas abiertas nuevas, las dos solo en Codex:
    - **B1:** una ruta que lanzaba una excepción silenciaba el bloqueo de las demás (`por_ruta` no aislaba).
    - **B2:** `--host=codex` caía en silencio a `claude-code`, y el `ask` de `guard_comandos` falla abierto en Codex.
  - **La corrección (una tanda, inline):** `_aislada` en `por_ruta` (con 2 rutas o más, una ruta que revienta cuenta como `Permitir`), `host_de` reconoce `--host=<v>` (vacío falla cerrado), y el parser de `apply_patch` conserva el espacio de más tras la marca, como Codex (aviso 1). RED de los 7 tests nuevos y GREEN después. El recheck, acotado a B1 y B2, los dio cerrados, y ninguna sonda que antes pasaba falla.
  - **Medición:** diferencial solo de Claude Code contra `6db4105`, sin flag, con `--host claude-code` y con `--host=claude-code`: 3713 de 3713 payloads sin estado y 1628 de 1628 pasos con estado idénticos, también en los archivos. Sondas Codex: 166 de 167; la que falla es X2, que ya venía de la base.
  - **Avisos que quedan:** 2, un host desconocido solo reconoce `PreToolUse` como pre (fuera de dominio hoy); 3, X3; 4, `writer_stop` ignora `--host` (va en F1c); 5, X2; 6, una ruta escrita como absoluta y como relativa entra dos veces.
- **L14 (2026-11-08), F1b.**
  - **Ruta:** un writer delegado, por el respaldo de contexto, y después un verificador independiente, por el ítem 2 (`writer_guard` y `writer_stop`).
  - **El writer:**
    - **Puerto por adaptador:** `BITACORA`, `archivos_del_writer(evento, fotos)`, `comandos_del_writer(evento, fotos)` y `hosts.necesita_bitacora`.
    - **Bitácora neutral:** está en `odd_ws/comun.py` y escribe en `<agente>.fotos/bitacora.jsonl`, un registro JSON en ASCII por línea con `O_APPEND`.
    - **Cuándo anota `writer_guard`:** en pre y solo si el host la necesita. Las ediciones van siempre; los comandos, solo si el guard no los bloquea.
    - **`writer_stop`:** lee `--host`.
    - **P5 de Codex:** pasa a `soportado`.
    - **Pruebas:** RED observado en 6 suites y 12 de 12 mutantes muertos.
  - **Decisión del orquestador:** una bitácora ausente, ilegible, vacía o con líneas rotas decide como Claude Code con un transcript ilegible. La falta queda en `errores_internos` y no cuenta como etapa rota. S4 no cubre este caso, y una etapa rota termina en `Permitir`, así que abriría la compuerta.
  - **El verificador:** S2, S3 y S5 cumplidos; S4 parcial por un blocker.
    - **B1:** una línea con un surrogate suelto en una ruta reventaba `clave_foto`. La etapa se rompía y la compuerta dejaba cerrar sin medir nada, con las fotos borradas.
  - **La corrección (una tanda, inline):** `_cadena_valida` rechaza la ruta o el comando que no se codifica en UTF-8, y esa línea cuenta como rota. RED de 4 tests y GREEN después. El rechequeo, limitado a B1, lo dio cerrado: con esa línea, la compuerta decide igual que con la bitácora sana.
  - **Medición del verificador:**
    - **Diferencial de Claude Code contra `f8a9b88`, sin flag, con `--host claude-code` y con `--host=claude-code`:** 1558 de 1558 payloads sin estado y 762 de 762 pasos con estado idénticos, también en los archivos. Ningún `bitacora.jsonl` en Claude Code.
    - **Paridad Codex contra Claude Code:** la misma decisión en los 10 casos comparables.
    - **Suites:** 41 de 41.
  - **Avisos que quedan:**
    - A1 y A2 van a X5; A5, al doctor de F1d; A6, a X6; A9, a X4.
    - **A3:** un comando que frena `guard_comandos` y no `writer_guard` queda anotado. Es solo información y está documentado.
    - **A4:** en Windows, el append no es atómico entre procesos. Dos procesos escribiendo seguido perdieron el 7,5 % de los registros; con hooks reales, 0 de 240. Lo mitiga el control cruzado de las fotos.
    - **A7:** una ruta relativa en una bitácora alterada se resuelve contra el cwd y entra dos veces.
    - **A8:** un id de sesión `NUL` en Windows no escribe nada. Ya venía de la base, y Codex da UUID.
- **L15 (2026-11-08), investigación puntual para F1c.** F1b quedó en `c3736ff`. Se leyó el código de Codex en los tags 0.144.0 y 0.167.0.
  - **Cómo corre un hook:** pasa por el shell del turno, sin login: `$SHELL -c` en Unix y PowerShell en Windows (`pwsh`, o si no `powershell.exe`, con `-NoProfile -Command`). `commandWindows` reemplaza a `command` en Windows. `${PLUGIN_ROOT}` y `${CLAUDE_PLUGIN_ROOT}` se reemplazan como texto y sin comillas, así que la ruta va entre comillas en el propio comando, y el comando no puede empezar con un token entre comillas (PowerShell lo toma como expresión). El timeout está en segundos; sin él, 600.
  - **El hallazgo que cambia F1a:** con `-Command`, PowerShell convierte en 1 cualquier exit distinto de 0 o 1. El padre lo comprobó en esta máquina: `powershell.exe -NoProfile -Command 'python -c "import sys; sys.exit(2)"'` sale con 1, y con `; exit $LASTEXITCODE` sale con 2. En Windows, el exit 2 del adaptador de Codex llegaba como 1, un error que no bloquea: los guards fallaban abiertos (S4).
  - **Bloquear por JSON con exit 0** funciona en las dos versiones, y el padre lo verificó en sus tests (`hooks/src/events/pre_tool_use.rs`, `post_tool_use.rs`):
    - PreToolUse: `hookSpecificOutput.permissionDecision: "deny"` con `permissionDecisionReason`.
    - PostToolUse: `{"decision": "block", "reason": …}`.
  - **El manifiesto:** ningún campo de `.codex-plugin/plugin.json` es obligatorio, y los desconocidos se ignoran.
    - `version`, si viene, es un string no vacío.
    - `hooks` acepta una ruta que empiece con `./`.
    - Sin `skills`, Codex descubre `skills/`.
    - Con `.codex-plugin`, Codex ignora entero `.claude-plugin`.
    - En 0.167, un `plugin.json` en la raíz con `$schema` de agent-plugins gana sobre los dos y apaga los hooks.
  - **El archivo de hooks** tiene `deny_unknown_fields`: arriba solo admite `description` y `hooks`.
  - **Matchers:** `SessionStart` admite `startup|resume|clear|compact`, y `fork` desde 0.167. `apply_patch` sirve literal. `SubagentStop` compara contra el `agent_role`.
  - **Confianza:** en 0.167 el hash incluye el contenido del bundle, así que cualquier cambio en un script pide confiar de nuevo. La clave incluye la ruta del archivo de hooks.
  - **Decisiones técnicas del padre:**
    - El adaptador de Codex bloquea por JSON y exit 0 en todas las plataformas, con un solo camino de código.
    - `command` usa `python`, como `hooks.json` de Claude Code, sin `commandWindows`.
    - El matcher de `SessionStart` es el mismo de Claude Code; `fork` sigue en X3.
- **L16 (2026-11-08), F1c.**
  - **Ruta:** un writer delegado, por el respaldo de contexto, y después un verificador independiente, por los ítems 2 y 5.
  - **El writer:**
    - El adaptador de Codex bloquea por JSON y exit 0: `deny` en pre y `decision: block` en post.
    - `hooks.codex.json` y `.codex-plugin/plugin.json`.
    - El test de paridad entre los dos `hooks*.json`, en `capacidades.tests.py`, con la misma versión en los dos manifiestos. Los tests de degradación comparan la forma de la salida y no el exit code.
    - Una prueba de punta a punta por `powershell.exe -NoProfile -Command`, con un espacio en la ruta.
    - Pasaron 40 de 41 suites y murieron 7 de 7 mutantes.
    - `tools/entrega.py` no sube versiones, así que no cambió.
  - **El padre:**
    - Sumó `odd_ws/hosts/base.tests.py` a la superficie: también esperaba exit 2 de Codex. Se aplicó el diff del writer, probado en RED y en GREEN.
    - Aplicó la misma limpieza de surrogates a `Contexto` y a `Seguir` (`_limpio`), con RED observado: serde_json rechaza un surrogate suelto escapado y la decisión se perdía.
  - **El verificador:** S2, S3, S4 y S5 cumplen, sin blockers.
    - **Contra el parser real:** copió `output_parser.rs` y `schema.rs` de los dos tags y los compiló con serde_json. Las 25 salidas de punta a punta dan el mismo veredicto en 0.144 y en 0.167, y las 104 salidas con motivos raros son válidas.
    - **El instrumento sabe decir que sí:** en la base, los mismos 11 bloqueos salían con exit 1 por PowerShell, es decir, abiertos.
    - **Mutantes y suites:** murieron 17 de 17 mutantes del empaquetado y 7 de 7 del adaptador. Pasaron 41 de 41 suites (1636 pruebas).
    - **Claude Code:** `claude plugin validate` da lo mismo en la base y en el candidato.
  - **Avisos que quedan:**
    - **A1:** una ruta del plugin con `$` se rompe dentro de las comillas dobles. Es fuera de dominio y quedó escrito en `diseno.md`.
    - **A2:** un `--host` desconocido sale con exit 2 y no bloquea en Codex; va al doctor de F1d.
    - **A3:** el test de paridad fija `displayName` como literal y no lo compara con `.claude-plugin`.
    - **A5:** un motivo vacío Codex lo toma como inválido, pero ningún núcleo lo construye.
    - **A6:** PowerShell suma unos 0,33 s por hook.
- **L17 (2026-11-08), el mapa de F1d y la decisión del usuario.** F1c quedó en `167132d`. Un explorador mapeó el bootstrap, el doctor y el esquema de Codex en 0.144 y 0.167.
  - **El bootstrap solo crea.** Lo que ya existe no se pisa, y cada plantilla de agente lleva una huella (`odd-ws-hash`). Una plantilla se actualiza por `doctor --arreglar`.
  - **La config de la instancia:** `config_loader` ignora las claves de primer nivel que no conoce. La `config` de la spec tiene que ser idéntica a la de una instancia que ya existe.
  - **El doctor** devuelve un `Resultado` por chequeo. Hoy, sin `claude`, da `FALTA`.
  - **El TOML de un agente de Codex:**
    - claves `name`, `description` y `developer_instructions`, las tres obligatorias y no vacías, con `deny_unknown_fields`;
    - el nombre sale de `name` y llega a los hooks como `agent_type`;
    - en 0.167 solo se aplican las instrucciones, el modelo y el apagado de algunas features, y `sandbox_mode` se ignora;
    - no hay lista blanca de herramientas ni skills precargadas.
  - **`.codex/config.toml` y `.codex/agents`** solo cargan si la raíz del repo tiene confianza en `[projects]`. `project_doc_fallback_filenames` sí vale en la config del proyecto.
  - **La confianza de un hook** se guarda bajo `[hooks.state."<plugin>@<marketplace>:<archivo>:<evento>:<grupo>:<handler>"]`. Su hash en 0.167 incluye el contenido del bundle, así que recalcularlo es frágil.
  - **La pregunta al usuario:** ¿cuándo genera la instalación los archivos de Codex: siempre, si se declara en la config, o si detecta Codex en la máquina?
    - **Respuesta:** «Declarado en config (Recomendado)». De ahí sale S8.
  - **Decisiones técnicas del padre:**
    - F1d se parte en F1d1 (generación) y F1d2 (doctor). F1d2 depende de la clave `hosts` de F1d1, así que van una después de la otra.
    - `hosts` es una lista no vacía, sin repetidos, de nombres del registro (`hosts.NOMBRES`).
    - El TOML se deriva del `.md`:
      - la versión y la huella van en un comentario TOML;
      - los bloques de la instancia y la description viven solo en el `.md`;
      - las diferencias de texto entre hosts entran por marcadores en las plantillas, que en Claude Code valen el texto de hoy, así que la huella no cambia.
    - Sin `sandbox_mode` ni `shell_tool = false`: la restricción va por texto y P7 queda degradado.
    - Una instancia que ya existe suma Codex agregando `"codex"` a `hosts` y corriendo `doctor --arreglar` (F1d2).
- **L18 (2026-11-08), los TOML de Codex atrasados respecto del `.md`.**
  - **El problema:** el writer de F1d1 avisó (A1) que en una instancia que ya existe, si se agrega `codex` y se corre el bootstrap, los TOML salen de la plantilla, sin los bloques ni la `description` del `.md`. El bootstrap solo crea y no lee el disco.
  - **La propuesta:** lo resuelve el doctor de F1d2 con el chequeo `codex-agentes`, como cualquier otro TOML que se atrasa cuando cambia su `.md`. La regla es la misma que el doctor ya usa con los writers: re-deriva el atrasado, avisa del editado a mano y genera el que falta. Se descartó que el bootstrap lea los `.md` existentes, porque va contra su diseño y solo cubre este caso.
  - **El usuario:** «tomare tu recomendacion».
- **L19 (2026-11-08), F1d1.**
  - **Ruta:** un writer delegado, por el respaldo de contexto, y después un verificador independiente, por el ítem 5 (el bootstrap es el instalador) y el 6.
  - **El writer:**
    - **`hosts`:** `config_loader.hosts_de` y `hosts` la validan, con `["claude-code"]` por defecto. `cargar` no la mira, así que una clave rota no cambia los hooks. El bootstrap la valida.
    - **El puerto de generación:** `TEXTOS` y `archivos(agentes)` en cada adaptador.
    - **Las plantillas:** 11 marcadores `{{host:x}}`. Con los textos de Claude Code dan las plantillas de antes, byte a byte.
    - **Los TOML de Codex:** se derivan del `.md` armado. Llevan solo `name`, `description` y `developer_instructions`, en strings básicos escapados, con la versión y la huella en comentarios.
    - **`.codex/config.toml`:** sale con el fallback a `CLAUDE.md`.
    - **Pruebas:** pasaron 41 de 41 suites, murieron 8 de 8 mutantes, y el diferencial de S5 dio 100 de 100 iguales.
  - **El verificador:** S2, S5 y S8 cumplen; S6 quedó parcial por un blocker.
    - **S5, sin diferencias en ninguna comparación:** bootstrap 124, generadores 1071, doctor 324 y hooks 690.
    - **Los TOML contra Codex:** un modelo compilado del parser de roles de Codex los acepta, incluidos 153 con textos raros.
    - **B1:** en una instancia que ya existe, sumar `codex` y correr el bootstrap escribía cada TOML desde la plantilla, sin la `description` ni los bloques del `.md`, y con una cabecera que decía, en falso, que salía del `.md`.
  - **La corrección (una tanda, del writer):**
    - **B1:** `AccionDerivada(ruta, contenido, fuente)`. El plan la marca `lo_deriva_el_doctor` cuando la fuente ya existía, con el mismo `lexists` de `ya_existe` y sin leerla. Esas acciones no se escriben, y el informe dice que las deriva el doctor (coherente con L18).
    - **A2:** los textos de Codex ya no nombran `Bash`. El modelo ve la shell como `exec_command`; `Bash` es solo el nombre en los hooks.
    - **A4:** `hosts` salió de `bootstrap.ejemplo.json`.
    - **Docs:** `diseno.md` dice que `.claude/` sale siempre, porque es la fuente y para Codex es inerte.
  - **El rechequeo,** limitado a B1: cerrado. El diferencial de S5 sigue en 0, y `ticket.py`, que comparte el plan, da 24 de 24 iguales a la base.
  - **Avisos que quedan:**
    - **A6:** hoy el doctor todavía no cumple la línea «lo deriva el doctor»; va en F1d2.
    - **A7:** `isinstance(AccionDerivada)` depende de que `bootstrap.py` se registre en `sys.modules` como `bootstrap`. Hoy no hay ningún punto de entrada distinto.
- **L20 (2026-11-08), F1d2.** F1d1 quedó en `932d733`. En el primer intento de commit, el barrido del pre-commit frenó un prefijo del dominio en un test. Se reemplazó por un texto neutro, y desde entonces cada brief de writer avisa que el repo es público.
  - **Ruta:** un writer delegado, por el respaldo de contexto, y después un verificador independiente, por el ítem 5 (`--arreglar` escribe en `.codex/` de la instancia) y el 6.
  - **El writer:**
    - **Puerto del doctor por adaptador:** `version`, `chequeos(ctx, raiz, nucleo, cli)` y `hooks_registrados`, y `doctor.NUCLEO` les pasa los helpers.
    - **Hosts declarados:** solo esos se revisan. Un `hosts` inválido da un único ítem en FALTA.
    - **Codex:** `codex`, `codex-plugin`, `codex-hooks`, `codex-proyecto`, `codex-config` y `codex-agentes`, este último con la regla de L18 y comparando contra la derivación completa.
    - **`hooks-host`:** corre solo si se declara algún host además de `claude-code`, por S5. En Claude Code ese error no puede pasar, porque sus hooks no llevan `--host`.
    - **Bootstrap:** la línea dice «(doctor --arreglar codex-agentes)», por el campo `arreglo`.
  - **Decisiones técnicas del padre:**
    - **CLI ausente con varios hosts declarados (S6, instancia compartida):** el CLI que falta da AVISO si hay otro declarado instalado, y FALTA si no hay ninguno.
    - **Lo que depende del CLI ausente:** con `CLI_DE_OTRO_HOST`, `marketplace` y `agentes-skills` dan NO APLICA.
    - **Un solo host declarado:** no cambia nada.
  - **El verificador:** S3, S4, S5, S6 y S8 cumplen; S2 parcial por un blocker.
    - **Medición:** doctor 513 de 513 iguales a la base, bootstrap y `ticket.py` 36 de 36, de punta a punta OK, y 16 de 16 mutantes muertos.
    - **B1:** `codex-proyecto` comparaba las claves de `[projects]` con `normcase` y `realpath`, y daba OK con barras normales o con barra final, que Codex no reconoce. Codex compara texto: en Windows ignora solo las mayúsculas ASCII.
  - **La corrección (una tanda, del writer):**
    - **B1:** calca la regla de Codex (ruta canónica y ruta tal cual, solo mayúsculas ASCII, gana la menor), y la ayuda da la tabla `[projects.'<ruta>']` lista para pegar.
    - **Avisos que entraron:**
      - A4: un TOML de solo lectura ya no da traceback;
      - A7: sin `tomllib` (Python 3.10) hay una falta clara;
      - A1: `hooks-host` lee también `CODEX_HOME/hooks.json` y `.codex/hooks.json`;
      - A2: el alias `command_windows`, y las barras se pasan a `/` antes de `shlex`;
      - A9: los mensajes.
  - **El rechequeo:** B1 y los avisos, cerrados; el doctor sigue en 513 de 513.
  - **Avisos que quedan:**
    - **A3:** en un worktree enlazado, `codex-proyecto` da un AVISO de más cuando la confianza está en el checkout principal. Falla del lado seguro.
    - **A5:** `.codex` como archivo da un mensaje confuso. Es fuera de dominio.
    - **A6:** `enabled = "false"` como string y `[plugins._default]` en 0.167. Fuera de dominio.
    - **A8:** `codex-hooks` lee el `hooks.codex.json` del plugin que corre el doctor, no el del caché de Codex.
    - **A10:** el CRLF del working copy lo normaliza git con `eol=lf`.
- **L21 (2026-11-09), arranque de F1e.** F1d2 quedó en `39f46e4`.
  - **El usuario:** «Si arranquemos».
  - **La pregunta:** dónde se instala el plugin de esta rama para la prueba.
  - **Su respuesta:** «Codex aparte (Recomendado)». La prueba usa un `CODEX_HOME` en el scratch, con el repo como marketplace local, y no toca `~/.codex` ni la 0.2.2 instalada.
  - **Lo que hace el usuario:** el `codex login` en esa carpeta y la confianza de los 6 hooks en `/hooks`.
  - **La entrega de `0.3.0`** (versión, tag y push) se confirma aparte, después de la prueba.
- **L22 (2026-11-09), prueba de humo en Codex 0.144 (Windows).** El `CODEX_HOME` aparte quedó en `D:\dev-cache\codex-prueba-odd-ws`, porque dentro del temp del sistema Codex no crea sus binarios auxiliares. El plugin se instaló desde el repo como marketplace local, y el workspace de prueba salió del bootstrap con `["claude-code","codex"]`. El usuario hizo el login y confió los hooks en `/hooks`.
  - **Doctor:** 0 FALTA, y los 7 ítems de Codex en OK. `codex-hooks` confirma, contra el Codex real, la clave de confianza que calcula el doctor.
  - **Humo 1, `git push --force`:** bloqueado por `guard_comandos` con un `deny` por JSON a través de PowerShell («Command blocked by PreToolUse hook: guard-comandos bloqueó el comando…»).
  - **Humo 2, primer toque con `apply_patch` en la capa:** bloqueado con los no negociables, y el archivo quedó intacto. Los hooks corren también dentro de un subagente.
  - **Humo 3, un writer por rol:** no se pudo, por límites de Codex 0.144 y no de odd-ws.
    - **El rol:** en v2 (el modelo por defecto, `gpt-5.6-terra`), `[features.multi_agent_v2] hide_spawn_agent_metadata` vale `true` y oculta `agent_type`. Ponerlo en `false` hace que la API rechace el pedido: «Function 'collaboration.spawn_agent' is reserved for use by this model and must match the configured schema». Además, `fork_turns` omitido vale `all`, y en 0.144 eso rechaza `agent_type`.
    - **Con `gpt-5.6-luna` (v1):** el modelo pasa `agent_type = 'writer-capa-a'`, pero Codex falla con «spawn_agent could not resolve the child model for service tier validation».
    - **El sandbox:** en Windows, Codex baja `workspace-write` a solo lectura si falta `[windows] sandbox = "unelevated"` (o `"elevated"`). Con eso, más `sandbox_mode = "workspace-write"` y `writable_roots` absolutos en el `.codex/config.toml` del proyecto, la sesión queda en `workspace-write`.
    - **Las rutas relativas** en la config del proyecto se resuelven contra `.codex/`.
    - **Herencia:** el subagente hereda el sandbox del padre y el rol no lo cambia, ni en 0.144 ni en 0.167.
  - **Lo que dice el código de 0.167:** con roles definidos por el usuario, `spawn_agent` v2 expone `agent_type` (`expose_agent_type = !agent_roles.is_empty()`), y el fork completo acepta el rol. Así que los writers por rol probablemente funcionen en 0.167. Falta probarlo.
- **L23 (2026-11-09), humo 3 con Codex 0.167 (npx), desde la TUI del usuario.**
  - **El usuario:** sobre cómo seguir, eligió «0.167 con npx (Recomendado)». Después, como `codex exec` se colgaba con el sandbox `unelevated`, eligió «Desde tu Codex abierto (Recomendado)».
  - **Lo que pasó:**
    - **El rol:** el writer se lanzó con `agent_type: "writer-capa-a"`, aun con `fork_turns: "all"`.
    - **El formato:** devolvió `## Resultado` con el formato de la plantilla.
    - **El cambio:** `a.ext` quedó en `valor = 2`.
    - **La compuerta:** `writer_stop` corrió en `SubagentStop`. Sacó el archivo de la bitácora, dio `formato_ok` y dejó cerrar.
    - **Las instrucciones:** el fallback a `CLAUDE.md` funciona, porque Codex lo inyecta como «AGENTS.md instructions».
    - **Los hooks:** el log de Codex (`logs_2.sqlite`) muestra que los de pre del `apply_patch` terminaron antes de aplicar el parche, y el de post después.
  - **Hallazgo A:** el primer toque no frenó al writer de Codex. `verificar_capa._precarga` lo saltea cuando el `.md` del agente precarga la skill de la capa. Eso vale en Claude Code, pero Codex no precarga skills (P7 degradado). El writer leyó el `SKILL.md` solo porque sus instrucciones se lo piden, y nada lo obliga.
  - **Hallazgo B:** `writer_stop` midió `a.ext` con 0 agregadas y 0 quitadas, sobre la base de su `.foto`, aunque cambió una línea. Con el mismo `git diff --no-index --numstat --ignore-cr-at-eol` fuera de Codex da 1 y 1, así que la foto ya tenía el contenido nuevo. Falta la causa; la foto se borró cuando la compuerta dejó cerrar.
  - **Hallazgo C (de Codex):** con `codex exec` (sin pantalla) y `[windows] sandbox = "unelevated"`, la 0.167 se cuelga en el primer comando de shell. En la TUI, los comandos tardan unos 30 s.
  - **Hallazgo D (de generación):** para que un writer de Codex escriba en Windows hace falta, en la config de Codex, `sandbox_mode = "workspace-write"`, `[windows] sandbox` y `writable_roots` absolutos con los repos de las capas. Las rutas son de cada máquina, y la decisión toca el aislamiento del usuario.
- **L24 (2026-11-09), F1f en curso.**
  - **A, resuelto inline:**
    - **El cambio:** `PRECARGA_SKILLS` en cada adaptador (`True` en Claude Code, `False` en Codex). `verificar_capa.decidir` recibe el host y `_precarga` lo consulta.
    - **La prueba:** RED del test `test_codex_no_precarga_skills_y_el_writer_tiene_su_primer_toque` y GREEN después. Las suites `verificar_capa` 70/70, `codex` 40/40, `claude_code` 24/24 y `capacidades` 20/20 pasan, y `diseno.md` quedó actualizado.
    - **Riesgo:** ítem 2, porque cambia un guard.
  - **En Codex 0.167, el pre se respeta en modo código:** la TUI del usuario bloqueó un `apply_patch` del agente principal por primer toque, y el archivo quedó intacto.
  - **B, acotado:** un vigilante copió `.claude/estado/writers` cada 0,2 s durante una segunda corrida del writer (`valor = 2` a `valor = 3`).
    - **La foto estaba bien:** `writer_guard` la sacó con `valor = 2\r\n` antes del parche, y la bitácora tenía la ruta.
    - **El hook midió mal:** `writer_stop` volvió a medir 0/0. Con el mismo código del caché del plugin y la misma foto, fuera de Codex, `lineas_reales` da 1/1, y `git diff --no-index` da rc 1 con «1 1».
    - **Conclusión:** la diferencia está en el entorno con el que Codex corre los hooks: probablemente el sandbox `unelevated` o variables del entorno. La causa exacta sigue abierta.
- **L25 (2026-11-09), decisión sobre B.** La pregunta: si seguir con B ahora o registrarlo y cerrar A. El usuario: «Registrar y cerrar A (Recomendado)». B pasa a X7. F1f cierra A y D, con su verificador.
- **L26 (2026-11-09), F1f.**
  - **El verificador:** sin blockers, con S4 (A), S5 y D cumplidos.
    - **Claude Code:** 4510 de 4510 pasos con estado iguales a `39f46e4`, sin flag, con `--host claude-code` y con `--host=claude-code`. Por el CLI real, 700 de 700.
    - **Codex:** un oráculo cruzado, el candidato con precarga contra la base sin precarga, da 3060 de 3060 iguales. El post no cambia.
    - **Estado global:** `_HOST` se restaura en todos los casos (25 de 25).
    - **Mutantes:** murieron los tres pedidos.
    - **Suites:** 41 de 41.
  - **Avisos aplicados:**
    - A1: la redacción de X7 en `diseno.md`;
    - A2: un test de paridad que exige `PRECARGA_SKILLS` en cada adaptador.
  - **Avisos que quedan:**
    - A3: restaurar `_HOST` en el `finally` es defensivo;
    - A4: la marca de la sesión principal es compartida, igual que en la base.
- **L27 (2026-11-09), entrega `0.3.0`.** F1f quedó en `d205677`.
  - **El usuario:** sobre la `0.3.0` (subir la versión, etiquetar y el push), respondió «Si autorizo».
  - **El commit de la entrega:**
    - `0.3.0` en `.claude-plugin/plugin.json` y en `.codex-plugin/plugin.json`;
    - la sección `## 0.3.0` en `CHANGELOG.md`;
    - en el README, el paso de la entrega nombra los dos manifiestos.
  - **El resto,** como en la `0.2.2`:
    - etiqueta con `claude plugin tag ./plugin`;
    - push de `main` y la etiqueta juntos (`git push origin <sha>:refs/heads/main refs/tags/odd-ws--v0.3.0`), que avanza `main` sin merge desde `4b423c6`;
    - el release lo publica `release.yml`.
- **L28 (2026-11-09), el README para Codex.** La entrega quedó en `9590e57`, con push de `main` y la etiqueta `odd-ws--v0.3.0`. El release lo publicó el CI.
  - **El usuario,** probando en su Codex, avisó que `/odd-ws:` no muestra nada. En Codex las skills se invocan con `$` o con `/skills` (`chat_composer.rs` de 0.167), y con `$` aparecen las siete. El usuario: «falta actualizar el readme tambien».
  - **El README:**
    - **Descripción y versión:** dice «para Claude Code y Codex CLI» y la versión `0.3.0`.
    - **Sección nueva «Usarlo desde Codex»:** declarar `hosts`; instalar con `codex plugin marketplace add` y `codex plugin add`; confiar la carpeta y los hooks; invocar las skills con `$`. También, que los writers necesitan 0.167 o más y, en Windows, la config del sandbox.
    - **Requisitos:** suma Codex CLI.
    - **Actualizar el plugin:** suma los comandos de Codex.
- **L29 (2026-11-09), historial reescrito con el email personal.** El README quedó en `main` (`f7b7630`, que ahora es `9245d36`).
  - **Por qué:** GitHub no contaba los commits en el gráfico del usuario, porque los 107 estaban firmados con el email del trabajo, que viene del `~/.gitconfig` global. Además, ese email quedaba a la vista en el historial público.
  - **La decisión:** el usuario: «me gustaria rescribir el historial para que queden a mi nombre». Para el push forzado eligió «Sí, forzar el push».
  - **Qué se hizo:**
    - respaldo previo en `D:\Project\odd-workspace-template-respaldo-20261109.bundle`;
    - `git config --local user.email` con el email personal;
    - `git filter-branch --env-filter` sobre todas las ramas y etiquetas, y las 4 etiquetas anotadas rehechas con el mismo mensaje y la misma fecha.
  - **Verificado:** 214 de 214 campos de autor y de commit, y las 4 etiquetas, con el email personal; los 107 commits; los 14 árboles idénticos a los de antes.
  - **El push:** `main` y las 4 etiquetas con `--force-with-lease`. Las otras 5 ramas ya no existían en GitHub. Los releases `0.3.0` y `0.2.2` siguen en pie.
  - **Incidente:** el primer push forzado subió el `main` local, que había quedado en `4b423c6` reescrito (`0ddf1a4`). Se corrigió en el acto, con un fast-forward a `9245d36`.
  - **Hashes de este documento,** viejo → nuevo:

    | Viejo | Nuevo |
    |---|---|
    | `4b423c6` | `0ddf1a4` |
    | `5bb9c3e` | `f6d13dc` |
    | `dcad0d9` | `78345f2` |
    | `6db4105` | `1f12bb9` |
    | `f8a9b88` | `1417ebf` |
    | `c3736ff` | `f1809b5` |
    | `167132d` | `ca43398` |
    | `932d733` | `858ca5a` |
    | `39f46e4` | `f85a96d` |
    | `d205677` | `37d2a1a` |
    | `9590e57` | `c6a799b` |
    | `f7b7630` | `9245d36` |
- **L30 (2026-11-09), macOS y Linux antes de Pi.** El commit de la tabla de hashes quedó en `5d4f764`, sin push.
  - **La pregunta del usuario:** «si alguien en mac quiere usar este plugin no le va funcionar bien?».
  - **La evidencia:**
    - los 13 hooks (7 en `hooks.json` y 6 en `hooks.codex.json`) llaman a `python`;
    - macOS no lo trae desde la 12.3, y Homebrew y python.org instalan `python3`;
    - las suites nunca corrieron fuera de Windows: el único workflow es `release.yml`;
    - no hay WSL en esta máquina.
  - **La propuesta:** primero un CI en las tres plataformas, después el arranque portable.
  - **El usuario:** a «¿Lo meto como próxima tarea, antes de Pi?», respondió «Si me parece bien».
- **L31 (2026-11-09), la investigación de M2 y la decisión.** El usuario pidió «Investiga bien, antes de que tomemos una decision para estar seguros».
  - **Claude Code** (según `hooks.md`):
    - Con `args`, ejecuta el binario sin shell. Sin `args`, usa `sh -c`, o Git Bash en Windows.
    - No hay campo de comando por sistema operativo.
    - `onFailure: "block"`, desde la v2.1.295, cuenta como falla un hook que no arranca, un exit distinto de 0 y 2, un timeout o un JSON inválido. Hace lo mismo que un exit 2 y no tiene efecto en `Stop`/`SubagentStop`.
    - Un plugin de prueba con `onFailure` valida en la 2.1.284 y en la actual: la versión vieja no lo rechaza.
  - **Python:**
    - **Versión:** los hooks y sus imports necesitan 3.7 (análisis estático con `ast` y `tokenize`); los tests, 3.12 (`shutil.rmtree(onexc=)` y `os.path.isjunction`).
    - **Mac y Linux:** `python3` existe siempre; en Mac, el de las Command Line Tools es 3.9.6. `python` falta en macOS, en Ubuntu y en Debian de fábrica, y en el runner `macos-latest`.
    - **Windows:** traen `python3` el Python install manager, la Store y scoop. El instalador clásico (obsoleto desde 3.14, sin publicar desde 3.16), winget y choco no lo traen, y ahí `python3` cae en el alias de la Store, que falla con argumentos.
    - **El costo:** medido en esta máquina, un lanzador `sh` le suma unos 330 ms a cada hook en Windows (388 contra 58 ms).
  - **Las opciones** que se le presentaron:
    - A: exec `python3` más `onFailure: "block"`;
    - B: lanzador `sh`;
    - C: `python` como hoy.
  - **El usuario:** «Si vamos con A».
- **L32 (2026-11-09), el primer CI en tres plataformas.**
  - **El usuario:** «si te doy autorizacion» (el push de una rama para el CI y la `0.3.1`).
  - **La rama `ci/pruebas`:** un worktree aparte desde `5d4f764`, con solo el workflow, empujado a GitHub (`cf3b2f5`, y `0aa6ca3` con anotaciones por suite).
  - **Resultado:**
    - **Windows:** GitHub no creó el job ninguna de las dos veces; la primera, con «Internal server error».
    - **Ubuntu:** 7 suites en rojo.
    - **macOS:** 10 suites en rojo.
    - **Hay dos tipos:** tests que asumen Windows (mayúsculas en rutas, `/var` → `/private/var`, el bit de ejecución de los hooks, `GREP_OPTIONS`) y posibles bugs reales (`guard_comandos` con 18/19 decisiones distintas, `/usr/bin/timeout` en `afirmaciones` en macOS, y otros sin causa).
  - **`gh`:** el usuario instaló GitHub CLI e inició sesión, así que los logs se leen con `gh run view --log-failed`.
- **L33 (2026-11-09), triaje de M3.** Lo hizo un explorador sobre `ci/pruebas` (`0aa6ca3`) y los logs de `gh`.
  - **El conteo real:** 6 suites en Ubuntu y 11 en macOS; a `ticket` no la anotó porque GitHub guarda como mucho 10 errores por step.
  - **Lo que es solo del test (T):**
    - fixtures de `guard_comandos` hechas para Windows (`TEMP=C:\…`, `\\?\`, `C:/`), y la ruta `//mp/…` que la mutila el test (L713);
    - `shutil.copyfile`, que pierde el bit de ejecución (en `pre-commit.tests` y en `bootstrap.tests`);
    - `os.rmdir` sobre un symlink en `ticket.tests`;
    - `/var` → `/private/var` en `recibo.tests` y en `doctor` `codex_proyecto`;
    - `GREP_OPTIONS`, que el GNU grep actual ignora.
  - **Lo que es del producto (P), de mayor a menor riesgo:**
    - **P1:** `guard_comandos` capa 2 **falla abierta en macOS**. `rutas.caso` y `config_loader.canonica` no pliegan mayúsculas en darwin, y APFS no las distingue: un push o un commit sobre un repo `agent_readonly`, escrito con otras mayúsculas, pasa. Toca `canonica`, que es compartido (ítem 3).
    - **P2:** `auditar_lecturas` no ve una lectura prohibida si la ruta pasa por un symlink (`/var` → `/private/var`): compara texto.
    - **P3:** `afirmaciones` y `conocimiento` fijan `/usr/bin/timeout`, que en macOS no existe. Todo da ERROR, y los filtros BSD pueden diferir.
    - **P4:** la excepción del scratch de la capa 1 de `guard_comandos` no funciona en POSIX: `_bajo_scratch` solo acepta `X:/` o `/x/`. Falla cerrada, más un borde improbable de falla abierta con `/c/…` resuelto contra el cwd.
    - **P5:** el doctor da FALTA en `plugin_root` en macOS cuando apunta al mismo plugin; se arregla con `samefile`.
    - **P6:** fuera de Windows, `scriptdom.ps1` sale con 4 en vez de 3 (`Join-Path 'C:\…'`).
  - **Windows:** sin pista. La primera corrida tuvo un solo job y la segunda, dos.
- **L34 (2026-11-09), M1 y M2 cerrados.**
  - **M1:** `.github/workflows/pruebas.yml` corre todas las suites con Python 3.12 en Ubuntu, Windows y macOS, sin `fail-fast`. Cada suite en rojo deja una anotación con sus primeras fallas, y GitHub guarda como mucho 10 por step.
  - **M2, el writer:**
    - **Claude Code:** `hooks.json` con `python3` en exec form, y `onFailure: "block"` en los 5 hooks de pre y post.
    - **Codex:** `hooks.codex.json` con `python3` y `commandWindows` con `python`.
    - **El doctor:** revisa que el binario corra un Python 3.7 o más y da un AVISO con Claude Code entre la 2.1.284 y la 2.1.294.
    - **Hooks de git:** `.githooks/python.sh` sondea `python3`, `python` y `py`, y la plantilla del pre-commit lleva el mismo texto.
    - **Pruebas:** 24 mutantes muertos.
  - **El padre:** cambió `writer_stop.tests.py:693` a `python3` y sin `onFailure`.
  - **El verificador:** S5 cumple, y S4 quedó parcial por un blocker.
    - **B1:** el ítem `python` del doctor revisaba solo `python3`, pero Codex lanza `python` en Windows.
    - **La corrección:** cada adaptador declara `PYTHON` y `PYTHON_EN_WINDOWS`. En Windows, el doctor revisa el binario de cada host declarado. A1: `hooks-host` cuenta handlers, con los comandos entre paréntesis.
    - **El rechequeo:** B1 y A1 cerrados, con una matriz de 40 casos.
  - **Pruebas:** 41 de 41 suites, con 1758 pruebas.
  - **Avisos que quedan:**
    - **A3:** la sonda solo silencia stderr.
    - **A5:** la sonda elige el primer intérprete que arranca, sin mirar la versión.
    - **A7:** `which` acepta los shims `.bat`; ahora eso falla cerrado.
    - **A8:** las instancias existentes conservan el pre-commit viejo, que llama a `python`.
    - **Las skills y el README:** unas 25 líneas todavía dicen `python` a secas (pasan a M3).
- **Siguiente paso:** M3 en unidades: guard (P1, P4), afirmaciones (P3), el resto (P2, P5, P6 y los T), las skills y el README con `python3`, y `windows-2022` en el CI. Después, la `0.3.1` y F2.
- **L35 (2026-11-09), el CI sobre `f287253` y el arranque de M3.**
  - **El push:** `feat/multi-host` quedó en `origin`, con upstream `origin/feat/multi-host`. Corrida `42697491803`.
  - **Windows:** GitHub creó el job esta vez, así que no hace falta fijar `windows-2022`.
  - **Suites en rojo:** 4 en Windows, 5 en Ubuntu y 11 en macOS.
  - **Lo nuevo de Windows, que el triaje no vio:**
    - **Python 3.12 en el CI contra 3.14 local:** antes de la 3.13, `time.monotonic()` en Windows salta de a 15,6 ms. Con `plazo=1e-9` el plazo nunca vence. Es del test: pasa a `plazo=-1`, un plazo ya vencido. `writer_guard.tests` lo arregla el padre, y `guard_comandos.tests` se suma a M3a. RED emulado con un reloj constante.
    - **Ruta 8.3 del temporal (`RUNNER~1`):** `realpath` la expande. Afecta a `recibo.tests` y al test `codex_proyecto` del doctor, y se suma a M3c.
  - **Lo nuevo de macOS:** `verificar_capa.tests` `test_no_escribe_nada_en_disco` ve un `maintenance.lock`: el `commit` del fixture dispara el mantenimiento automático de git en segundo plano. El helper `git` del test pasa `-c maintenance.auto=false`. Sin RED local: lo prueba el CI.
  - **Las unidades:** M3a, M3b y M3c corren en paralelo, como writers acotados con superficies disjuntas.
- **L36 (2026-11-09), M3b y M3c de vuelta.**
  - **M3b, las afirmaciones:**
    - **P3:** el `timeout` externo va solo en Windows, donde es el de Git for Windows. Fuera de Windows, el plazo exacto lo pone Python: `start_new_session` y, al vencer, `killpg` del grupo.
    - **Lo descartado:**
      - Buscar `timeout` o `gtimeout` en el PATH: rompe la regla de no confiar en el PATH, y en una Mac limpia igual falta.
      - Prescindir del `timeout` también en Windows: medido, `taskkill /T` deja vivo un descendiente MSYS.
    - **`GREP_OPTIONS`:** el test usa `/usr/bin/env` como instrumento.
    - **Además, `uniq`:** el de macOS no permuta (`getopt_long` con `+`) y escribe en el segundo operando. Arreglar P3 volvía alcanzable ese agujero, así que ahora se cuentan los operandos como GNU y como macOS. Sobre 2 380 formas, 532 pasan a rechazarse y ninguna se acepta de más.
    - **Pruebas:** 6 mutantes muertos. `afirmaciones` 106/106 y `conocimiento` 112/112. El padre corrió la suite tres veces más, todas 106/106; antes había dado una vez 105/106, con los otros writers cargando la máquina.
    - **Risk:** ítems 2, 4 y 6. Lleva verificador independiente, que está corriendo.
  - **M3c, el resto:**
    - **P2:** `auditar_lecturas` pasa por `canonica` las rutas de esta máquina.
    - **P5:** el `plugin-root` del doctor usa `canonica`, y si no alcanza, `samefile`.
    - **P6:** `scriptdom.ps1` busca la DLL en `C:\Program Files` solo en Windows, y si no, sale con 3.
    - **Los T:** el 8.3 y `/private/var` en `recibo.tests` (`realpath` de `mkdtemp`); `ticket.tests` usa `unlink`; `bootstrap.tests` hace `chmod 0o755`.
    - **El doctor contra Codex:** es del test. Codex escribe la clave canónica de `[projects]`.
    - **Los textos:** 27 líneas pasan a `python3`, con una oración por skill para Codex en Windows.
    - **Pruebas:** 8 suites en verde, con TEMP normal y con TEMP 8.3. El padre repitió el doctor: 131/131.
    - **Risk:** none.
  - **Avisos nuevos:**
    - **X8:** una clave de `[projects]` escrita a mano con un alias de la raíz del repo da un AVISO falso, que falla cerrado. Arreglarlo es tocar `hosts/codex.py` `_proyecto`.
    - **A2:** `instancia-hooks` del doctor compara con `canonica`, así que en macOS depende de lo que haga M3a con las mayúsculas.
    - **Previo:** `grep -r` sin operando lee el working tree.
- **L37 (2026-11-09), M3a de vuelta.**
  - **P1:**
    - **Cómo:** `rutas.plegar` pasa a minúsculas y NFC solo en darwin, después de `realpath`, en `canonica` y en la cola inexistente de `Protegidos._canonica`. `caso` no cambia.
    - **Por qué plegar siempre y no sondear el volumen:** sondear cuesta llamadas dentro del plazo, falla con los montajes y no se puede probar desde Windows.
    - **El costo:** en un APFS sensible a mayúsculas, los guards quedan más estrictos.
    - **Consumidores de `canonica`:** 9, contados con `git grep`, y ninguno se afloja en APFS normal.
    - **`comun._misma_carpeta`:** usa `canonica`.
  - **P4:**
    - **El scratch por OS:** `comun.carpeta_scratch` da `<TEMP>\claude` en Windows, `<TMPDIR|/tmp>/claude-<uid>` en Linux y `/tmp/claude-<uid>` en macOS. Sale de la doc de `CLAUDE_CODE_TMPDIR`.
    - **`_bajo_scratch`:** fuera de Windows solo acepta `/…`, lo que cierra el borde de `/c/…`.
  - **Una falla abierta más:** en POSIX, `git -C //<repo> push` pasaba, porque `//` se trataba como UNC en todos los OS. Ahora es solo de Windows. El test la escondía al mutilar la ruta.
  - **Pruebas:**
    - **S5:** diferencial en Windows contra `f287253` sobre 415 casos, idéntico.
    - **Suites:** rutas 11, config_loader 83, guard_comandos 49 y comun 62, más 21 consumidoras en verde. El padre repitió guard_comandos: 49/49.
  - **Risk:** ítems 2, 3 y 6.
  - **Pendiente, en curso:** el scratch de `writer_guard` todavía es `<temporal>/claude` en POSIX. Se le devolvió a M3a.
  - **Avisos nuevos:**
    - `CLAUDE_CODE_TMPDIR` no se honra; con la variable puesta, la excepción del scratch falla cerrada.
    - `comun.temporal` en POSIX lee solo `TMPDIR`.
    - `clave_foto` no pliega en macOS: sobrecuenta, que es el lado estricto.
- **L38 (2026-11-09), M3c commiteado (`1cfd042`) y empujado.**
  - **El CI** (corrida `42707595845`) solo deja en rojo las suites de las unidades sin commitear:
    - macOS: `afirmaciones`, `guard_comandos` y `conocimiento`;
    - Ubuntu: `afirmaciones` y `guard_comandos`;
    - Windows: `guard_comandos` y `writer_guard` (el `plazo=-1` va con M3a).
  - **En verde en los tres OS:** las 8 suites de M3c y `verificar_capa`.
  - **Pendiente:** M3a y M3b esperan a su verificador independiente.
- **L39 (2026-11-09), el verificador de M3b: S4 parcial, S5 cumple.**
  - **B1 (blocker):** `uniq -i-ignore-cas - escrito.txt` pasa la lista blanca y escribe en el repo medido.
    - El getopt_long BSD lee un `-` en medio de un grupo corto como el comienzo de una opción larga. Lo hacen macOS y también el `uniq.exe` de Git for Windows, que usa el getopt de Cygwin.
    - En Windows ya estaba en la base. En macOS lo vuelve alcanzable M3b.
  - **A1:** `sort -u-t=DIR` crea temporales en DIR. Es la misma causa y se cierra con el mismo arreglo.
  - **A2 (S5):** en Windows, `--claims` cambia en 4 formas de `uniq` (`uniq - -c`, `uniq alfa.txt -c`, `uniq -c alfa.txt -u` y `uniq alfa.txt --`), que pasan a FAIL del lint. Es la regla nueva de M3b, **aceptada por el padre**: en macOS esas formas escriben.
  - **A3:** el 105/106 era un glob `afirmaciones-*.sh` sobre el temporal compartido, que choca con otros procesos que corren afirmaciones. No es de tiempo.
  - **A5:** el camino POSIX con `killpg` está bien, leído en el código.
  - **La corrección:** una tanda para B1, A1 y A3, más las sondas como tests de regresión, devuelta al writer de M3b. Después, un rechequeo limitado a B1.
- **L40 (2026-11-09), el verificador de M3a: S4 parcial, S5 cumple.**
  - **Lo que cumple:**
    - **S5:** en Windows, 46 468 filas idénticas a la base, y el arranque en frío también es igual.
    - **P1:** cumple en la capa 2 y en `writer_guard`.
    - **`//` en POSIX:** cumple.
    - **Consumidores de `canonica`:** 9 módulos, más `auditar_lecturas` de M3c, y ninguno se afloja en APFS normal.
  - **B1 (blocker):** en POSIX, un enlace dentro del scratch más `..` (`rm -rf <scratch>/enlace/../x`) borra fuera. El guard colapsa `..` como texto antes del `realpath`. En la base POSIX bloqueaba.
  - **B2 (blocker):** en POSIX, `rm -rf <scratch>/.\./.\./fuera` pasa, porque bash lee `\` como escape y el guard como separador. En la base POSIX bloqueaba.
  - **Seguimientos (advisories):**
    - **X9:** B2 ya estaba en la base de Windows con Git Bash. S5 congela Windows, así que queda para después.
    - **X10:** tres escapes del scratch de `writer_guard`, ya en la base: `.\.`, `enlace/..` y `Join-Path` con `..`.
    - **X11:** la capa 2 en POSIX colapsa `..` como texto en `ubicar` (`git -C /tmp/l/.. push`). Ya estaba en la base.
    - **A4 y A5:** en un APFS sensible a mayúsculas, el plegado afloja el scratch, y `lower()` no es el case folding de APFS. Ambos, fuera de dominio.
  - **La corrección:** una tanda para B1 y B2, más 5 tests de regresión, devuelta al writer de M3a. Después, un rechequeo limitado a B1 y B2.
- **L41 (2026-11-09), la corrección de M3b y su rechequeo.**
  - **La regla nueva:** `_guion_en_grupo_corto` rechaza, en `sort` y `uniq`, un `-` dentro de un grupo de opciones cortas antes del primer carácter que lleva argumento.
  - **A3:** los tests del guion temporal fijan `tempfile.tempdir` a una carpeta propia.
  - **Pruebas del writer:** 3 mutantes muertos; `afirmaciones` 109/109 y `conocimiento` 112/112. El padre repitió `afirmaciones`: 109/109.
  - **El rechequeo (limitado a B1 y A1): cerrados.**
    - En el port del getopt de Apple, las formas que escriben bajan de 286 a 0.
    - Con el `uniq.exe` real, 0 de 1476 formas aceptadas escriben.
    - De punta a punta, no se escribe ningún archivo.
    - La regla no acepta nada que la base rechazara.
    - Siguen valiendo `sort -t-` y `uniq -f-1`.
  - **`Doc/diseno.md`:** el padre integró las notas de M3b: el plazo por OS, `uniq` contado de dos maneras, el `-` en un grupo corto, el test de `GREP_OPTIONS` y lo que no ve.
  - **Commit:** M3b quedó en `04d0674`.
- **L42 (2026-11-10), la corrección de M3a.**
  - **B1:** fuera de Windows, `_bajo_scratch` le pasa los `..` a `canonica`, y `realpath` los resuelve después de los enlaces.
  - **B2:** en Bash, en POSIX, una pieza con `\` no cuenta como scratch. `\` separa solo en el dialecto PowerShell y en sus cmdlets.
  - **Tests de regresión:** los 5 que pidió el verificador. El del enlace real de B1 solo corre en el CI de POSIX.
  - **Pruebas:** en Windows, diferencial idéntico a `f287253`. guard_comandos 51/51, writer_guard 112/112, comun 62/62, rutas 11/11 y config_loader 83/83. El padre repitió guard_comandos: 51/51.
  - **N1, que trae el writer:** `rutas.ubicar` colapsa `..` como texto, así que en POSIX la capa 2 y `writer_guard` siguen ciegos al `enlace/..`. Es el A2 y A3 del verificador, previo a M3: el padre lo deja como seguimiento X10 y X11, sin otra tanda.
  - **El rechequeo, limitado a B1 y B2: cerrados.**
    - **Cómo se midió:** POSIX emulado, con `os.path = posixpath` y `lstat`/`readlink` falsos, para que `realpath` resuelva `..` de forma física. Sobre la primera versión de M3a, 28 de esas sondas fallaban.
    - **Bloquean:** enlaces anidados y relativos, `..` en el medio, varias piezas, `.\.` y `\` en otras posiciones.
    - **PowerShell:** `\` sigue separando.
    - **Windows:** el diferencial da 46 468 filas idénticas.
    - **X12 (advisory, fuera de dominio):** en PowerShell sobre POSIX, `Remove-Item <scratch>/dentro/../../x`, con un enlace interno, podría salir del scratch si pwsh resuelve `..` como texto. Hoy ningún host da una herramienta PowerShell en POSIX.
- **L43 (2026-11-10), M3 cerrado y la entrega `0.3.1`.**
  - **Commits:** M3a quedó en `0a1af09`.
  - **El CI:** la corrida `42821303293` sobre `0a1af09` da todas las suites en verde en Ubuntu, Windows y macOS. S4 y S5 quedan cumplidos.
  - **La `0.3.1`** (autorizada en L32):
    - los dos manifiestos y el README pasan a `0.3.1`;
    - el CHANGELOG lleva el efecto de bloqueo en Windows con el instalador clásico y el pre-commit de las instancias existentes (A8);
    - etiqueta `odd-ws--v0.3.1`, y `main` avanza por fast-forward hasta el commit de la entrega.
  - **Siguiente paso:** F2, gentle-shell (Pi). Los seguimientos X1-X12 quedan abiertos.
  - **`Doc/diseno.md`:** el padre integró las notas de M3a: el scratch por OS en los dos guards, `..` y `\` en POSIX, el plegado en macOS y `//`.
