# Lo que cambia según el host

Detalle de las secciones 4 y 6 del `SKILL.md` de `/odd-ws:revisar` para Pi y para Codex. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`. En Claude Code no cambia nada.

## Pi

**Las corridas.** En Pi (gentle-shell), cada corrida es un `subagent_run` con `mode: "background"`, uno por corrida y todos en el mismo mensaje, y cada lanzamiento devuelve su `task_id` («as task <id>»). Cuando una corrida termina, gentle-shell te entrega una copia de su reporte que puede venir cortada (a 16 KB por defecto): no la uses, porque el reporte entero sale del rescate (paso 6). Los `agentId` los devuelve cada lanzamiento; en Pi, la tabla lleva el `task_id`.

**El rescate.** En Pi, el rescate lee la tarea que gentle-shell guarda por corrida, con el reporte entero, y escribe los mismos archivos. Es el comando de la sección 6 con `--host pi` y `--corrida <nombre>=<task_id>`, sin `--sesion`:

- La tarea es `<agentHome>/gentle-agents/tasks/<task_id>.json`, y `agentHome` es `GENTLE_PI_AGENT_HOME`, si no `PI_CODING_AGENT_DIR`, si no `~/.pi/agent`. gentle-shell define las dos variables en su sesión, así que corré el rescate desde ahí; `--sesion <carpeta>` las reemplaza con la carpeta de tareas o con el `agentHome`. Fuera de una sesión de gentle-shell, su home por defecto es `~/.gentle-shell/agent`: pasá `--sesion ~/.gentle-shell/agent`.
- Las lecturas son `read`, `grep` y `find`; cualquier otra herramienta sale como «NO auditada». En `costo.json`, `orquestador` queda en `null` con un aviso, porque solo se mide en Claude Code.
- Una tarea que no terminó en `completed` es una corrida cortada: `FAIL … tarea <task_id> en estado <estado>, sin reporte`. Si el estado es `running` y la corrida ya avisó que terminó, gentle-shell todavía no guardó la tarea: volvé a rescatar esa corrida un momento después antes de darla por cortada.
- **Si el rescate de una corrida falla** (`FAIL … no existe <task_id>.json`, `no es una tarea de gentle-shell`, o la carpeta de tareas no existe), pedí su reporte con `subagent_result` y su `task_id`, que lo devuelve entero, y guardalo en `corridas/<nombre>.md`. Decile al usuario que esa corrida salió de `subagent_result`, sin lecturas ni costo.

## Codex

**El límite de concurrencia.** Codex responde «agent thread limit reached» cuando se pasa de `agents.max_threads`, que Gentle AI pone en 4, o, en V2, de `max_concurrent_threads_per_session - 1`, que es 3, y un `completo` con 2 capas o más lanza 5 corridas o más. Ante ese rechazo, esperá a que termine una corrida en marcha, cerrala (en Codex, `close_agent` libera su lugar), relanzá la rechazada y decile al usuario que la revisión va por tandas. La regla es la misma en todos los hosts.
