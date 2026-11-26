# Lo que cambia según el host

Detalle de las secciones 4 y 6 del `SKILL.md` de `/odd-ws:revisar` para Pi y para Codex. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`. En Claude Code no cambia nada.

## Pi

**Las corridas.** En Pi (gentle-shell), cada corrida es un `subagent_run` con `mode: "background"`, uno por corrida y todos en el mismo mensaje, y cada lanzamiento devuelve su `task_id` («as task <id>»). Cuando una corrida termina, gentle-shell te entrega una copia de su reporte que puede venir cortada (a 16 KB por defecto): no la uses, porque el reporte entero sale del rescate (paso 6). Los `agentId` los devuelve cada lanzamiento; en Pi, la tabla lleva el `task_id`.

**El rescate.** En Pi, el rescate lee la tarea que gentle-shell guarda por corrida, con el reporte entero, y escribe los mismos archivos. Es el comando de la sección 6 con `--host pi` y `--corrida <nombre>=<task_id>`, sin `--sesion`:

- La tarea es `<agentHome>/gentle-agents/tasks/<task_id>.json`, y `agentHome` es `GENTLE_PI_AGENT_HOME`, si no `PI_CODING_AGENT_DIR`, si no `~/.pi/agent`. gentle-shell define las dos variables en su sesión, así que corre el rescate desde ahí; `--sesion <carpeta>` las reemplaza con la carpeta de tareas o con el `agentHome`. Fuera de una sesión de gentle-shell, su home por defecto es `~/.gentle-shell/agent`: pasa `--sesion ~/.gentle-shell/agent`.
- Las lecturas son `read`, `grep` y `find`; cualquier otra herramienta sale como «NO auditada». En `costo.json`, `orquestador` queda en `null` con un aviso, porque solo se mide en Claude Code.
- Una tarea que no terminó en `completed` es una corrida cortada: `FAIL … tarea <task_id> en estado <estado>, sin reporte`. Si el estado es `running` y la corrida ya avisó que terminó, gentle-shell todavía no guardó la tarea: vuelve a rescatar esa corrida un momento después antes de darla por cortada.
- **Si el rescate de una corrida falla** (`FAIL … no existe <task_id>.json`, `no es una tarea de gentle-shell`, o la carpeta de tareas no existe), pide su reporte con `subagent_result` y su `task_id`, que lo devuelve entero, y guárdalo en `corridas/<nombre>.md`. Dile al usuario que esa corrida salió de `subagent_result`, sin lecturas ni costo.

## Codex

**Las corridas.** En Codex, cada corrida es un `spawn_agent` con `agent_type` igual al nombre del revisor (`revisor-diseno`, `revisor-<capa>`), un `task_name` único por ticket, corrida y ronda (en minúsculas, con `_` en lugar de `-`, como `t1_a_revisor_diseno_r1_ronda1`) y `fork_turns: "none"`: con `"all"`, el revisor hereda tu historia y deja de revisar a ciegas. El prompt viaja cifrado y el rescate no lo puede reconstruir, así que, antes de lanzar, guarda el de cada corrida en `corridas/<nombre>.prompt.txt`.

**El `thread_id`.** `spawn_agent` devuelve solo el `task_name`. El hilo de cada revisor queda en `<CODEX_HOME>/sessions/<año>/<mes>/<día>/rollout-<fecha>T<hora>-<thread_id>.jsonl` (`CODEX_HOME` es `~/.codex` por defecto, y la fecha va en hora local), y su **primera línea**, el `session_meta` del revisor, lleva `"agent_path":"/root/<task_name>"`. Mira solo esa primera línea de cada rollout de la carpeta de hoy (por ejemplo, con `Get-Content -TotalCount 1` o `head -n 1`), no el archivo entero: tu propio rollout también nombra ese `agent_path` más abajo. Con el ticket y la ronda en el `task_name`, otra revisión o una segunda ronda del mismo día no encuentra el hilo de la primera; si aun así encuentras más de uno, no elijas: pregúntale al usuario. Toma el `thread_id` entero del final del nombre del archivo: son cinco grupos hexadecimales de 8, 4, 4, 4 y 12 caracteres, y uno parcial es un error de uso. En Codex, la tabla lleva el `thread_id`.

**Un límite (I35).** En Codex, el reporte y el veredicto llegan en un solo mensaje, y tú recibes la devolución entera, no solo el veredicto: el ahorro de I35 no se cumple. Igual, los hallazgos se leen del `<nombre>.md` rescatado.

**El rescate.** Es el comando de la sección 6 con `--host codex` y `--corrida <nombre>=<thread_id>`, sin `--sesion`:

```bash
python3 "<S>/rescatar.py" --host codex --destino "<ticket>/revision/<fecha>-<modo>/corridas" --corrida <nombre>=<thread_id> --corrida … --costo
```

- Lee el rollout del revisor en `CODEX_HOME`; `--sesion <carpeta>` lo reemplaza con otro `CODEX_HOME` o con su carpeta `sessions`. Comprueba que su `agent_role` sea el de un revisor: si no, `FAIL … no de un revisor`, porque el hilo es otro o el revisor se lanzó sin `agent_type` o con `fork_turns: "all"`.
- El reporte es el mensaje final del revisor (el de `task_complete`) sin su última línea, la del veredicto; si el mensaje es solo el veredicto, es el texto que escribió después de su último comando. No escribe `.prompt.txt`: el que guardaste antes de lanzar queda como está, salvo sus secretos, que tapa como en los otros hosts, y la línea `ok` los cuenta.
- Las lecturas son los comandos del shell (`CommandExecution`), con el comando, la carpeta y el código de salida, porque Codex lee con el shell. `auditar_lecturas.py` no los sabe auditar y los cuenta como «NO auditados»: una corrida sin ninguna lectura auditada sale `SIN AUDITAR`, con código 1, porque no está probado que no haya leído una ruta prohibida. Lo que no es un comando ni un mensaje, como una edición, sale como herramienta «NO auditada».
- En `costo.json`, la caché leída de Codex ya está dentro de la entrada: `contexto_final` es la entrada de la última llamada, sin sumarle la caché, y `orquestador` queda en `null`, con un aviso.
- Sin `task_complete` con su mensaje final, es una corrida cortada: `FAIL … sin task_complete`. **Si el rescate de una corrida falla**, su reporte entero ya llegó en la devolución: guárdalo en `corridas/<nombre>.md` sin la línea del veredicto y dile al usuario que esa corrida salió de la devolución, sin lecturas ni costo.

**El límite de concurrencia.** Codex responde «agent thread limit reached» cuando se pasa de `agents.max_threads`, que Gentle AI pone en 4, o, en V2, de `max_concurrent_threads_per_session - 1`, que es 3, y un `completo` con 2 capas o más lanza 5 corridas o más. Ante ese rechazo, espera a que termine una corrida en marcha, ciérrala (en Codex, `close_agent` libera su lugar), relanza la rechazada y dile al usuario que la revisión va por tandas. La regla es la misma en todos los hosts.
