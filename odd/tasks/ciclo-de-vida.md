# T9: las skills de ciclo de vida (apertura, cierre y `/odd-ws:revisar`)

Objetivo: que el ciclo de un ticket de la instancia (abrir, revisar antes del commit y cerrar) tenga sus skills en el plugin `odd-ws`, sobre las piezas que ya existen (triaje, recibo, rescate, revisores por capa, matriz). Rama: `feat/ciclo-de-vida`, creada desde `main` (`8b497d3`). Entrega: como la T8, un commit por unidad, push solo con autorización y fast-forward de `main` al cerrar. Runner: Python sin pytest, `<nombre>.tests.py` junto a cada script. Espejo en Engram: `odd/ciclo-de-vida/tasks`.

## Specs

- **S1. Alcance aprobado (L2).** Unidades:
  - **S0, spike:** abrir Claude Code dentro de un ticket de la instancia de prueba y ver si aparecen las skills `/odd-ws:*`. Si no aparecen, los settings no se heredan y cada ticket necesita su `settings.json`.
  - **R2:** la plantilla `revisor-diseno` y su generador en `/bootstrap`. Revisa entre capas: el hermano vigente y el consumidor de cada dato.
  - **R1:** la skill `/odd-ws:revisar`. Sigue este orden: triaje, anuncio del modo y su costo, el sí, las corridas, el rescate, la consolidación y el recibo. Corre `--check` antes de cualquier «listo» y pregunta si el cambio va a un líder.
  - **A2:** el script `ticket.py`, que crea `tickets/<id>-<slug>/` desde la plantilla sin pisar nada y reusa el motor de `/bootstrap`.
  - **A1:** la skill de apertura: alcance y no-goals, avisos de los «X o Y», docs de dominio por índice y candidatos de los tickets hermanos.
  - **C1:** la skill de cierre: triaje de aprendizajes, fila de la matriz con origen, los dos relojes, mostrar antes de escribir y un commit con `git add` explícito, con el sí del usuario.
  - **T1:** los textos. `CLAUDE.md` y `ticket.md` apuntan a las skills nuevas.
- **S2. Decisiones técnicas del padre, aprobadas con el alcance (L2).**
  - **Tracker sin contrato:** si la sesión tiene una herramienta (MCP) del tracker del usuario, la apertura la usa; si no, el usuario pega el pedido.
  - **El cierre gradúa solo a lo que ya existe:** `knowledge.docs`, el `CLAUDE.md` raíz, la matriz y `evidencia.md`. Engram es opcional.
  - **La consolidación la hace el orquestador en prosa,** con la frecuencia k/3, el 1/3 como «a confirmar» y los conflictos sin votar.
- **S3. Fuera de la T9 (L2):**
  - el chequeo mecánico de «graduado ⇒ candidatos vacíos»;
  - el buzón de `.claude/registro/`;
  - el `.code-workspace` generado.
- **S4. Reglas transversales de la T7 y la T8, que siguen vigentes.**
  - Test primero y datos sintéticos: ningún literal del dominio del origen entra al repo, y el barrido lo bloquea. El origen se lee para entender la mecánica y nunca se copia.
  - Diferencial y mutaciones con control positivo. Toda prueba o mutante que corra git aísla `GIT_CONFIG_GLOBAL` y `GIT_CONFIG_SYSTEM` en archivos propios, con `GIT_CONFIG_NOSYSTEM=1`.
  - Las rutas de la instancia salen de `odd_ws/capas.py` (R-8) y la raíz, de `config_loader` (R-1). La salida va en UTF-8 y los archivos generados, en LF sin BOM (R-5).
- **S5. Decisiones técnicas del padre para las skills (L3).**
  - **El modo sombra** sigue siendo de `/odd-ws:eval-reviewers` (`revision/<fecha>-sombra/`). `/revisar` no congela nada: si el usuario quiere sombra, lo manda ahí.
  - **El modelo:** todas las corridas de una revisión usan el mismo modelo, sin IDs fijos en la skill.
  - **La invocación:** el modelo puede invocar `/revisar` antes de un commit, pero la skill siempre pide el sí por el costo. La apertura y el cierre los invoca solo el usuario.
  - **El worktree:** la apertura pregunta si va en un worktree o en el árbol principal y da el comando; los comandos en los repos del equipo los corre el usuario.
  - **El commit de cierre:** lo propone la skill, con `git status` mostrado antes y `git add` explícito, y lo hace solo con el sí.

## Tasks

| ID | S# | Qué | Ruta | Riesgo | Estado |
|---|---|---|---|---|---|
| S0 | S1 | Spike: ¿una sesión abierta dentro de un ticket carga el plugin de la raíz? | el usuario, a mano (2 minutos), con control positivo en la raíz | ninguno | pendiente |
| R2 | S1, S4 | Plantilla `revisor-diseno` y su generador en `bootstrap_agentes.py` | delegado (writer, en paralelo con R1, por el respaldo de contexto del padre; L3) | ninguno: suma un archivo generado | hecho (L5) |
| R1 | S1, S2, S5 | Skill `/odd-ws:revisar` | delegado (writer, en paralelo con R2; L3) | **6**, porque ninguna prueba atrapa la prosa. Verificador: cada comando de la skill contra la CLI real, y una corrida a mano en la instancia de prueba | hecho (L4); verificación al final de la feature (L5) |
| A2 | S1, S4 | `ticket.py`: crear el ticket desde la plantilla sin pisar nada | después de S0 | ninguno: reusa el motor que no pisa | pendiente |
| A1 | S1, S2, S5 | Skill de apertura | después de A2 | **6**, como R1 | pendiente |
| C1 | S1, S2, S5 | Skill de cierre (`/odd-ws:cerrar`) | delegado (writer, adelantado porque no depende de S0; L6) | **6**, como R1 | hecho (L7); verificación al final de la feature |
| T1 | S1 | Textos: `CLAUDE.md`, `ticket.md` y la prueba de `bootstrap_textos` | al final | ninguno | pendiente |

## Log

- **L1 (2026-11-03): el pedido del usuario, verbatim:** «Pasame el comando y sigamos con T9».
  - Contexto: la T8 se cerró y entregó en `main` (`8b497d3`). La T9 la fijó la S2 de `odd/tasks/bootstrap.md`: «Las skills de ciclo de vida (apertura, cierre y `/odd-ws:revisar`) van a una T9».
- **L2 (2026-11-03): exploración y alcance aprobado.**
  - **El explorador, de solo lectura,** mapeó las tres skills del origen y lo que ya ofrece el plugin:
    - Ya existen `triaje.py`, `recibo.py` (con `--ticket`), `rescatar.py`, `revisor-<capa>`, la plantilla del ticket con los dos relojes, la matriz con `matriz.py --destinos | --severidad` y `knowledge.docs`.
    - Faltan el revisor de diseño y el consolidador.
    - El triaje declara «antes de mostrarle a un líder» como algo que no puede detectar.
    - El riesgo sin verificar: los settings podrían no heredarse dentro de un ticket.
  - **El padre propuso** las unidades de S1, las decisiones de S2 y lo de S3.
  - **El usuario respondió, verbatim:** «Si vamos asi».
- **L3 (2026-11-03): decisiones técnicas del padre para las skills y las rutas.**
  - Las de S5.
  - **Las rutas:** R1 y R2 son unidades independientes, con superficies disjuntas. Van a dos writers en paralelo, por el respaldo de contexto del padre.
  - **El nombre que comparten:** el agente `revisor-diseno`, en `.claude/agents/revisor-diseno.md`.
  - A2 espera el resultado de S0, porque de ahí sale si el ticket lleva su propio `settings.json`.
- **L4 (2026-11-03): R1 hecho por el writer (Sonnet).**
  - `plugin/skills/revisar/SKILL.md`, de 177 líneas:
    - reglas duras: el sí siempre, nunca dos revisiones, sin bucle, solo git de lectura en los repos del equipo, el mismo modelo y no congela nada;
    - el triaje con la pregunta por el líder;
    - la entrada, con `--no-index` para lo nuevo;
    - las corridas por modo, con el orden barajado;
    - el modo 0;
    - el rescate;
    - la consolidación;
    - el recibo con `--check` sobre la carpeta de la revisión.
  - **Cada comando de la skill se corrió una vez sobre una instancia sintética, con git aislado:**
    - el triaje: modos `completo` y `0`, `--json` con la base completa y los errores de uso y de entorno;
    - el `git diff`, incluido el `--no-index`;
    - `recibo.py --write` y `--check`: exit 0, 1 después de cambiar un archivo, 0 al restaurarlo, y 2 sin recibo o sin `--archivo`;
    - el modo 0 sin revisores;
    - `rescatar.py` con una corrida cortada (exit 1) y con todas buenas (exit 0).
  - **Observaciones sobre los scripts, sin defecto:**
    - `recibo.py --check` sobre la carpeta del ticket toma el recibo más reciente, y a igual fecha el `completo`. Por eso la skill chequea la carpeta de la revisión.
    - El triaje no falla con un repo fuera de la config.
    - El triaje lista todo lo cambiado, así que la skill separa con el usuario lo que no es del ticket.
  - **Sin verificar en esta máquina:** la ruta real de la carpeta `subagents` contra un `.jsonl` de Claude Code. La cubre la corrida a mano del final.
  - **Corrección del padre:** el writer mandaba hacer `git fetch` sin más. Ahora la skill lo propone y lo corre solo con el sí del usuario, porque habla con el remoto.
  - **Inconsistencia conocida:** la skill está en «tú» neutro y las demás skills del plugin, en voseo. Se unifica en T1.
- **L5 (2026-11-03): R2 hecho por el writer (Sonnet), y el commit conjunto de R1 y R2.**
  - **La plantilla `plantillas/revisor-diseno.md`**, genérica:
    - el arranque con `CENTINELA criterios`;
    - los límites (solo lee, cada repo en su rama);
    - la entrada: todos los diffs, la rama o el worktree y la carpeta del ticket;
    - cuatro pasos con tabla: el mapa del cambio, el hermano vigente, el consumidor de cada dato con control positivo en los negativos, y los errores, los efectos hacia otro sistema con las tres preguntas, el ciclo de vida y el tamaño;
    - los sesgos;
    - el reporte con el contrato común.
  - **El generador:** `generar_revisor_diseno(actual=None)` en `bootstrap_agentes`, una vez por instancia, solo con capas válidas y antes de `criterios`. La constante es `capas.REVISOR_DISENO`.
  - **ROJO:** 22 de 34 caían por la regla. **VERDE:**
    - `bootstrap_agentes` 34/34 y `plantilla_writer` 24/24;
    - `bootstrap` 146/146, `bootstrap_cli` 14/14 y `bootstrap_e2e` 10/10, que ahora cuentan 16 archivos;
    - `doctor` 76/76 y `capas` 12/12.
  - **Mutantes:** 10 de 10 muertos. **Config real:** sin cambios.
  - **Desvío del writer:** la constante de `capas` se escribió antes de su prueba.
  - **Decisión del padre:** una capa llamada `diseno` choca con este revisor, y el plan sale con «ruta repetida». Hoy es un fallo explícito, así que queda como nombre reservado, documentado en `diseno.md` y en la entrevista de `/odd-ws:bootstrap`, sin código nuevo.
  - **El commit:** R1 y R2 van en un solo commit. Están acoplados (`/revisar` usa `revisor-diseno`) y sus docs comparten `diseno.md`.
  - **Commit:** `2c46547`.
- **L6 (2026-11-03): nombres y orden.**
  - **Nombres (decisión técnica del padre):** las skills son `abrir` y `cerrar` (`/odd-ws:abrir` y `/odd-ws:cerrar`), como los pasos 1 y 7 del ciclo en la plantilla de `CLAUDE.md`, y verbos como `revisar`.
  - **Registro:** el voseo de `doctor` y de `bootstrap`. `revisar` se pasa a voseo en T1.
  - **C1 se adelanta:** no depende de S0, así que se delegó a un writer (Sonnet) mientras el usuario corre el spike. A2 y A1 siguen esperando a S0.
- **L7 (2026-11-03): C1 hecho por el writer (Sonnet).**
  - `plugin/skills/cerrar/SKILL.md`, de 160 líneas, en voseo, con `disable-model-invocation`. Tiene reglas duras y 9 pasos:
    1. leer el ticket y sus `Fuente:`;
    2. el triaje, con la clasificación dominio o motor;
    3. la propuesta y el sí;
    4. el modo sombra primero;
    5. promover, con la fila de la matriz y su validación;
    6. los dos relojes y la foto de la entrega;
    7. el worktree;
    8. `conocimiento.py`;
    9. el commit de cierre.
  - **Cada comando se corrió sobre una instancia sintética, con git aislado:**
    - el glob del ticket, que encuentra también el archivado;
    - el script de agregar fila, que dio `EJ-01` y después `EJ-02`, en LF y sin BOM;
    - `matriz.py --destinos` y `--severidad`, con su control positivo: exit 1 con la regla sin escribir o sin severidad, y 0 al corregirla;
    - `conocimiento.py`: 1 con un link roto y 3 con solo deuda;
    - `git status`, y `git add` y `git reset` anclados con `:/` desde dentro del ticket;
    - el commit, que corrió el pre-commit;
    - la foto de la entrega y el worktree.
  - **El hallazgo del writer:** la herramienta Glob lista archivos, no carpetas, así que el glob del ticket termina en `/CLAUDE.md`. El padre lo propagó a `/odd-ws:revisar`.
  - **Decisiones del writer:**
    - `→ motor` va en la última entrada de la bitácora;
    - el `tipo` de la matriz se copia de una fila vecina o se confirma con el usuario;
    - el script de agregar fila va dentro de la skill. Pasarlo a un `matriz.py --agregar` probado queda como sugerencia, fuera de la T9.
  - **Corrección del padre:** el registro estaba mezclado. Cuatro verbos en «tú» pasaron a voseo.
  - **Verificación (decisión del padre):** R1, A1 y C1 son prosa, de riesgo 6. Van con un solo verificador independiente al final de la feature, más una corrida a mano del ciclo completo (apertura → revisar → cierre) en la instancia de prueba, en lugar de un verificador por skill.
