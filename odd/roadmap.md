# Roadmap de odd-ws

Lo que viene después de cada entrega, en orden. Es una cola viva: un ítem que espera algo externo no frena a los demás, y una idea nueva pasa primero por una bandeja antes de entrar a la cola. El detalle de cada ítem vive en su documento de `odd/tasks/`; acá van solo el orden y el estado.

Actualizado: 2026-11-17, con la `0.8.0`, las ideas I1 a I16 y R4 en curso.

## Cómo se mueve

1. **Se toma el primer ítem de «La cola».** Un ítem a medias no se interrumpe por otro.
2. **Si el ítem espera algo** (una respuesta, otro cambio), se revisa su condición al llegar a él. Si no se cumple, pasa a «Esperando» con la fecha del chequeo y se toma el siguiente.
3. **Al empezar cada ítem, se revisan los de «Esperando».** El que se destraba vuelve al frente de la cola.
4. **Las ideas entran a «Ideas»**, sean del autor, de un video o de otro proyecto, con su fuente y lo que se recicla. Se revisan al cerrar cada ítem: se descartan con el porqué, se estudian con un alcance acotado o pasan a la cola. **El lugar en la cola lo decide el autor.**
5. **Un seguimiento** va con el ítem que toque su mismo código, o pasa a la cola si el autor lo pide.
6. **Al cerrar un ítem**, pasa a «Hecho» con su commit. Cuándo sale una versión lo decide el autor.

## La cola

| # | Qué | Detalle | Estado |
|---|---|---|---|
| R4 | La experiencia de uso, vista en un ciclo real que va de la instalación al cierre de un ticket: el bootstrap en una sola propuesta (I8), el hook en LF (I9), la autoridad según de quién es el repo (I10), el siguiente paso al cerrar el bootstrap (I11), el id del ticket sin tracker (I12), la sesión del ticket en VS Code (I7), el ticket activo que vuelve solo (I13), las memorias de los repos (I14), el ticket como documento de ODD (I15) y el arranque en frío de las reglas (I16). Se siguen sumando hallazgos en el trayecto, y sale como `0.9.0`. | [experiencia-de-uso](tasks/experiencia-de-uso.md); [Ideas](#ideas), I7 a I16 | en curso |
| R2 | En Pi, el doctor da un OK falso en cinco casos forzados, y una carpeta `.git` inválida confunde la raíz de la instancia. Además, dos tests de plazo fallan a veces en el CI. | [multi-host](tasks/multi-host.md), X14 a X16 | en cola |
| R3 | Soporte para OpenCode (F3), Gemini CLI (F4) y Copilot CLI (F5), a partir del estudio de align-cli guardado en engram (`odd-ws/estudio-align-cli`). | [multi-host](tasks/multi-host.md), F3 a F5 | en cola |

## Esperando

| Qué | Espera | Último chequeo |
|---|---|---|
| El lector del `ratchet-handoff/v1` de `gentle-contribution-skills` | Que Denver2828 responda sobre `source_id` en el issue #1 de `Denver2828/gentle-contribution-skills` ([graduar-memorias](tasks/graduar-memorias.md), X7) | 2026-11-16: abierto; el último comentario es nuestro, del 2026-11-15 |
| `writer.md` usa «límites» para tres cosas: renombrar `## Tus límites` | El próximo cambio de la plantilla del writer, porque cambiarla sube a v3 y obliga a regenerar los writers de cada instancia ([limites-en-el-cierre](tasks/limites-en-el-cierre.md), F3) | 2026-11-16: ningún ítem de la cola cambia `writer.md` |

## Ideas

Cada idea lleva su fuente (del autor, un video o un proyecto, con su enlace), la idea en una línea, lo que se recicla y su estado: nueva, estudiando, en la cola (con su `R#`) o descartada (con el porqué).

| # | Fecha | Fuente | La idea | Qué se recicla | Estado |
|---|---|---|---|---|---|
| I1 | 2026-11-17 | [Libro de Gentleman](https://the-amazing-gentleman-programming-book.vercel.app/en), cap. 21, y el [video de RDD](https://www.youtube.com/watch?v=t_HEm1om2Ek) | El commit vuelve a comprobar el recibo: si lo que va al commit no es lo que se revisó, se pregunta. | El recibo atado al contenido y la compuerta que lo vuelve a derivar al entregar. `recibo.py` ya guarda el hash del diff revisado, y `guard_comandos` ve el `git commit` y compararía, sin poner hooks en los repos de código. | nueva |
| I2 | 2026-11-17 | [Libro de Gentleman](https://the-amazing-gentleman-programming-book.vercel.app/en), cap. 21 | Que la falla de un hook quede a la vista: se anota en `.claude/estado` y el doctor o la sesión siguiente la muestra. | «Una falla de la infraestructura nunca se vuelve una respuesta». Hoy `revisar_turno` y `verificar_capa` fallan abiertos sin dejar rastro. | nueva |
| I3 | 2026-11-17 | [Libro de Gentleman](https://the-amazing-gentleman-programming-book.vercel.app/en), cap. 21 | Un test por cada cosa que la revisión no ve. | Los contratos honestos fijados con tests de alcance: cada punto de «No ve» de la capa por shell tendría un test que confirma que no lo ve, para que cerrar un hueco sea un cambio a propósito. | nueva |
| I4 | 2026-11-17 | [Video de RDD](https://www.youtube.com/watch?v=t_HEm1om2Ek) | Un banco reproducible de flujos adversariales por CLI. | El banco de más de 60 flujos de RDD, clasificados en in-band, out-of-band y callejón sin salida: vuelve automática la prueba de humo manual de los tres CLI. | nueva |
| I5 | 2026-11-17 | [Video de RDD](https://www.youtube.com/watch?v=t_HEm1om2Ek) | Un interruptor por hook en `workspace.config.json`. | El kill switch de RDD: apagar `revisar_turno`, que suma unos 400 ms por prompt, sin desinstalar el plugin. | nueva |
| I6 | 2026-11-17 | [Libro de Gentleman](https://the-amazing-gentleman-programming-book.vercel.app/en), cap. 20 | Clasificar las memorias en hechos, decisiones y comportamientos. | La regla del capítulo, en la que los hechos van a la búsqueda, las decisiones a la memoria y los comportamientos a las skills, aplicada en `cerrar memorias` para elegir el destino de cada una. | nueva |
| I7 | 2026-11-17 | Del autor, al abrir una instancia desde la extensión de VS Code | En VS Code, la sesión de un ticket se abre con la carpeta del ticket como directorio principal. | Claude Code lee el `.claude/settings.json` compartido solo del directorio principal, y la extensión toma como principal la primera carpeta del `.code-workspace`: no está documentado, pero `/status` lo mostró el 2026-11-17. odd-ws solo documenta `claude --add-dir`. Primer paso: probar si `/cd <ticket>` recarga el plugin; si no lo hace, `abrir` genera un `.code-workspace` por ticket, con el ticket primero y los repos después. Otra opción, más simple: trabajar desde la raíz de la instancia, que ya carga el plugin, con `abrir` agregando el worktree al `.code-workspace` y el ticket activo inyectado por I13. | en la cola (R4) |
| I8 | 2026-11-17 | Del autor, al correr `/odd-ws:bootstrap` en una instancia nueva | El bootstrap en una sola parada: una propuesta completa junto con el ensayo, y un sí la aplica. | Hoy la entrevista hace una pregunta por paso, y en una instancia nueva fueron seis paradas, todas con «sí». Se recicla: `bootstrap.py --proponer`, que lee el `.code-workspace`, cuenta las extensiones con `git ls-files` y propone `knowledge.docs` si el repo tiene una carpeta de docs; el criterio de capas en la skill, una por tecnología y con su costo real según `revisar`; y un resumen agrupado del ensayo. | en la cola (R4) |
| I9 | 2026-11-17 | Del autor, en el primer commit de una instancia nueva | El bootstrap crea un `.gitattributes` que deja `.githooks/*` en LF, y el doctor lo revisa en las instancias que ya existen. | Git para Windows trae `core.autocrlf=true`: al volver a clonar la instancia, el `pre-commit` quedaría en CRLF y `sh` falla. El repo de odd-ws ya se protege con `* text=auto eol=lf`, pero la instancia no. | en la cola (R4) |
| I10 | 2026-11-17 | Del autor, en el bootstrap y al abrir el primer ticket | La autoridad depende de quién es el repo: en la instancia, y en un repo de código marcado como propio, el agente commitea y crea el worktree sin pedir cada paso. Un interruptor en `workspace.config.json` vuelve a pedir aprobación. | Hoy el bootstrap prohíbe el primer commit («El primer commit es del usuario»), mientras `cerrar` ya commitea en la instancia, y `abrir` trata todo repo como del equipo y le pasa los comandos del worktree al usuario. Límites: `git add` solo por ruta explícita, nunca push, y en los repos del equipo solo lectura. Con el bootstrap commiteando desaparecen el chmod y el `git add` archivo por archivo. | en la cola (R4) |
| I11 | 2026-11-17 | Del autor, al terminar el bootstrap | El bootstrap cierra con el siguiente paso concreto: abrir el primer ticket con `/odd-ws:abrir`. | Arrancar con la matriz vacía es lo normal, porque las reglas nacen al cerrar tickets. Sin ese paso, el agente improvisó «cargá las reglas» a mano. Se mencionan los atajos `/odd-ws:cerrar memorias` y `/odd-ws:paquetes`. | en la cola (R4) |
| I12 | 2026-11-17 | Del autor, al abrir el primer ticket sin tracker | Sin tracker, `abrir` propone el siguiente id consecutivo con un prefijo fijado en el bootstrap (`T-1`, `T-2`…). | `abrir` da por hecho que el id sale de un tracker, y quien trabaja solo tuvo que inventar la convención en ese momento. | en la cola (R4) |
| I13 | 2026-11-17 | Del autor, al trabajar un ticket desde la sesión de la raíz | El ticket activo vuelve solo: `abrir` lo anota en `.claude/estado/` y, si la sesión corre en la raíz, el hook de inicio inyecta su `CLAUDE.md` al arrancar y después de cada `/compact`. | Desde la raíz, Claude Code carga el `CLAUDE.md` del ticket solo cuando lee un archivo de su carpeta, y no lo vuelve a cargar después de un `/compact`. El hook de inicio ya corre en `startup`, `resume`, `compact` y `clear` y puede agregar contexto (P1), pero hoy solo lo usa `verificar_capa`. El `settings.json` del ticket solo lleva `enabledPlugins`, igual que el de la raíz, así que los hooks y las skills ya funcionan desde ahí. | en la cola (R4) |
| I14 | 2026-11-17 | Del autor, al guardar memorias desde la instancia | `cerrar memorias` también lee las memorias de los repos de la config, y el bootstrap lo deja configurado. | engram y la memoria en archivos de Claude Code separan las memorias por proyecto: las sesiones del repo guardan bajo el proyecto del repo, y las de la instancia bajo el de la instancia. Hoy `cerrar memorias` lee solo las de la instancia (`memorias.py` y el paso M2 de `cerrar`), así que la historia que ya tenía el repo no llega a la matriz. | en la cola (R4) |
| I15 | 2026-11-17 | Del autor, al cruzar el ODD de gentle-ai con el ticket | Una plantilla del ticket compatible con ODD: `## Specs` y `## Tareas` opcionales para las tareas grandes, la Bitácora como Log con el pedido textual en L1 y la clave del espejo en engram. La regla «el ticket es el documento de la feature» sube de lugar en el `CLAUDE.md`, o la recuerda `abrir`. | El agente planteó «el ticket o `odd/tasks/<feature>.md`» como un conflicto abierto y propuso escribir la regla, que ya estaba en la línea 115 de 139 del `CLAUDE.md` de la instancia. La plantilla del ticket no tiene dónde guardar los S#, los T# ni el commit de cada tarea. | en la cola (R4) |
| I16 | 2026-11-17 | Del autor, al ver los revisores de capa vacíos el primer día | El arranque en frío de las reglas: sembrar las capas con lo que el repo ya sabe (su `CLAUDE.md`, sus gotchas, sus docs), junto con las memorias de I14. | El primer día la skill de cada capa y la matriz están vacías, así que los revisores de capa no tienen contra qué medir aunque el repo ya tenga reglas escritas. Hoy `paquetes` copia paquetes aparte y `cerrar memorias` solo gradúa memorias. | en la cola (R4) |

## Seguimientos

Anotados en el documento de cada feature, sin lugar en la cola:

| Documento | Seguimientos |
|---|---|
| [endurecer-guards](tasks/endurecer-guards.md) | Y1 a Y5 e Y7 a Y10 |
| [graduar-memorias](tasks/graduar-memorias.md) | X1 a X6 |
| [multi-host](tasks/multi-host.md) | X1, X3 a X8, X12 y X13 |
| [paquetes-de-reglas](tasks/paquetes-de-reglas.md) | A4 a A8, los avisos del verificador de T1 |
| [uso-en-equipo](tasks/uso-en-equipo.md) | F1 y F2 |
| [capa-por-shell](tasks/capa-por-shell.md) | F1, la caché de bytecode de los hooks; los avisos A1 a A6 del verificador de la parte B (L20) |

## Hecho

| Versión | Qué |
|---|---|
| `0.8.0` | Las reglas de la capa corren aunque el agente escriba por la shell: el guard frena la escritura de capa por la shell (R1) y el fin del turno revisa lo que cambió (R1b) ([capa-por-shell](tasks/capa-por-shell.md)) |
| `0.7.0` | Paquetes de reglas importables desde git ([paquetes-de-reglas](tasks/paquetes-de-reglas.md)) y la guía de uso en equipo ([uso-en-equipo](tasks/uso-en-equipo.md)) |
