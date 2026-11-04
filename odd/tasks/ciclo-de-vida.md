# T9: las skills de ciclo de vida (apertura, cierre y `/odd-ws:revisar`)

Objetivo: que el ciclo de un ticket de la instancia (abrir, revisar antes del commit y cerrar) tenga sus skills en el plugin `odd-ws`, sobre las piezas que ya existen (triaje, recibo, rescate, revisores por capa, matriz). Rama: `feat/ciclo-de-vida`, creada desde `main` (`8b497d3`). Entrega: como la T8, un commit por unidad, push solo con autorización y fast-forward de `main` al cerrar. Runner: Python sin pytest, `<nombre>.tests.py` junto a cada script. Espejo en Engram: `odd/ciclo-de-vida/tasks`.

## Specs

- **S1. Alcance aprobado (L2).** Unidades:
  - **S0, spike:** abrir Claude Code dentro de un ticket de la instancia de prueba y ver si aparecen las skills `/odd-ws:*`. Si no aparecen, los settings no se heredan y cada ticket necesita su `settings.json`. **Resuelto por la documentación (L8):** no se heredan, así que cada ticket lleva el suyo. La prueba en la máquina pasa a H1.
  - **R2:** la plantilla `revisor-diseno` y su generador en `/bootstrap`. Revisa entre capas: el hermano vigente y el consumidor de cada dato.
  - **R1:** la skill `/odd-ws:revisar`. Sigue este orden: triaje, anuncio del modo y su costo, el sí, las corridas, el rescate, la consolidación y el recibo. Corre `--check` antes de cualquier «listo» y pregunta si el cambio va a un líder.
  - **A2:** el script `ticket.py`, que crea `tickets/<id>-<slug>/` desde la plantilla sin pisar nada y reusa el motor de `/bootstrap`.
  - **A1:** la skill de apertura: alcance y no-goals, avisos de los «X o Y», docs de dominio por índice y candidatos de los tickets hermanos.
  - **C1:** la skill de cierre: triaje de aprendizajes, fila de la matriz con origen, los dos relojes, mostrar antes de escribir y un commit con `git add` explícito, con el sí del usuario.
  - **T1:** los textos. `CLAUDE.md` y `ticket.md` apuntan a las skills nuevas.
  - **P1 (L8):** «Chequeo en el pre-push: frena un push a main que cambia `plugin/` desde la última etiqueta sin subir la versión.»
  - **V1 (L8):** la entrega: `plugin.json` a `0.2.0`, la etiqueta con `claude plugin tag` y el push de la rama, de main y de la etiqueta, solo con la autorización del usuario.
  - **H1 (L8):** la prueba de humo después del push: actualizar el marketplace, abrir `claude` en un ticket sin `--plugin-dir` y ver `/odd-ws:`.
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
- **S6. El plan de la entrega, aprobado por el usuario (L8).**
  - **Se mantiene P4:** la versión fijada en `plugin.json` y la etiqueta `odd-ws--vX.Y.Z`. El canal es `main` y no una rama `stable`: `main` solo avanza al cerrar una feature, y cada cierre es una entrega. P1 lo hace cumplir.
  - **A2:** el bootstrap genera también `tickets/_plantilla/.claude/settings.json`, con el mismo `enabledPlugins` de la raíz, y `ticket.py` copia la plantilla entera sin pisar nada.
  - **T1** suma el README: la instalación con `--scope project`, porque `claude plugin install` instala a nivel usuario por defecto y eso va contra P2, y cómo actualizar. También corrige `Doc/diseno.md:503`: el ticket necesita su `enabledPlugins` aunque el plugin traiga sus hooks.
  - **La corrida manual del ciclo** va con `claude --plugin-dir <clon>/plugin`, abierta dentro de un ticket de la instancia de prueba. Antes, el repo `db` de esa instancia pasa a un repo sintético, para que la corrida no toque ningún repo del equipo.

## Tasks

| ID | S# | Qué | Ruta | Riesgo | Estado |
|---|---|---|---|---|---|
| S0 | S1 | Spike: ¿una sesión abierta dentro de un ticket carga el plugin de la raíz? | el usuario, a mano (2 minutos), con control positivo en la raíz | ninguno | hecho por la documentación (L8); la prueba en la máquina pasa a H1 |
| R2 | S1, S4 | Plantilla `revisor-diseno` y su generador en `bootstrap_agentes.py` | delegado (writer, en paralelo con R1, por el respaldo de contexto del padre; L3) | ninguno: suma un archivo generado | hecho (L5) |
| R1 | S1, S2, S5 | Skill `/odd-ws:revisar` | delegado (writer, en paralelo con R2; L3) | **6**, porque ninguna prueba atrapa la prosa. Verificador: cada comando de la skill contra la CLI real, y una corrida a mano en la instancia de prueba | hecho (L4); verificación al final de la feature (L5) |
| A2 | S1, S4, S6 | `ticket.py`: crear el ticket desde la plantilla sin pisar nada, y el `settings.json` de la plantilla | delegado (writer, en paralelo con P1; L8) | **3**: el writer refactorizó `bootstrap.planificar`, que usa `/bootstrap`. Entra al verificador del final | hecho (L10); verificación al final de la feature |
| P1 | S1, S4, S6 | Chequeo de la entrega en el pre-push | delegado (writer, en paralelo con A2; L8) | **5**: toca la entrega. Commit propio y entra al verificador del final | hecho (L9); verificación al final de la feature |
| A1 | S1, S2, S5 | Skill de apertura (`/odd-ws:abrir`) | delegado (writer, por el respaldo de contexto del padre, en paralelo con T1; L11) | **6**, como R1 | hecho (L11); verificación al final de la feature |
| C1 | S1, S2, S5 | Skill de cierre (`/odd-ws:cerrar`) | delegado (writer, adelantado porque no depende de S0; L6) | **6**, como R1 | hecho (L7); verificación al final de la feature |
| T1 | S1, S6 | Textos: `CLAUDE.md`, `ticket.md`, la prueba de `bootstrap_textos`, el README, P4 y `diseno.md:503` | delegado (writer, en paralelo con A1; L12); el README, el padre | ninguno | hecho (L12) |
| V1 | S1, S6 | La entrega `0.2.0` y su etiqueta | inline, después del verificador y la corrida manual | **5**: toca la entrega. Commit propio | pendiente |
| H1 | S1, S6 | Prueba de humo por el camino real | el usuario, después del push autorizado | ninguno | pendiente |

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
- **L8 (2026-11-04): S0, la versión del plugin y el plan de la entrega.**
  - **S0:** el control positivo falló: tampoco en la raíz aparecía `/odd-ws:` («No commands match "/odd-ws"»).
    - **Causa:** `plugin.json` fija `0.1.0` desde el esqueleto, y Claude Code nombra su copia y detecta las actualizaciones por esa versión. La copia `0.1.0` de la máquina es la del spike del 25/10: trae `scripts/` y ninguna skill.
    - **P4 nunca se ejecutó:** no hay etiquetas `odd-ws--v*` ni rama `stable`.
  - **El padre propuso sacar la versión, con un dato equivocado.** Dijo que nada la leía, y el usuario respondió «Si me parece bien». La búsqueda se había cortado a los 30 resultados: `comun.tests.py:296` ata la mayor a la API, y P4 decide la versión fijada. El padre lo corrigió antes de escribir nada.
  - **El usuario, verbatim:** «Vale, tomate tu tiempo e investiga y analiza bien que vamos hacer».
  - **La documentación oficial** (`code.claude.com/docs`; un agente la investigó y el padre verificó tres citas con `curl`):
    - `settings.json` se lee solo de la carpeta de arranque;
    - la confianza se guarda por la raíz del repo git;
    - los agentes y las skills de proyecto se buscan subiendo hasta la raíz del repo, y las del plugin no;
    - `claude plugin tag` crea `<name>--v<version>`;
    - `owner/repo#ref` fija un canal;
    - en un marketplace de terceros la actualización automática viene apagada;
    - `claude plugin install` instala a nivel usuario por defecto.
  - **El plan aprobado (S6).** El usuario, verbatim: «Si vamos con ese plan». Con eso aceptó `main` como canal y el chequeo P1.
  - **Rutas:** A2 y P1 son independientes y tocan archivos distintos, así que van con dos writers en paralelo. Los docs compartidos (`diseno.md`, `README.md` y este archivo) los edita el padre al final.
- **L9 (2026-11-04): P1 hecho por el writer (Sonnet).**
  - `tools/entrega.py` y `tools/entrega.tests.py`, más una línea al final de `.githooks/pre-push`. Las dos líneas del barrido siguen primero y sin cambios.
  - **Pruebas:** 20/20. Tres de ellas hacen un `git push` real a un remoto sintético con una copia del hook y una lista negra sintética. Fijan que el barrido sigue frenando y corre antes. La suite tarda unos 40 s en el pre-commit.
  - **RED:** 0/20 sin el script y 5/20 con un stub que sale 0.
  - **Mutantes:** 16 de 17 muertos. El vivo (sacar `|| exit 1` de la última línea del hook) es equivalente, porque el hook sale con el código de su último comando.
  - **Diferencial contra el hook de `c66cf0e`:** el push a una rama de feature da salida idéntica. El push a `main` con su etiqueta solo suma la línea pedida `entrega limpia`.
  - **Decisiones del writer:**
    - el bloqueo por regla sale con 1, y no poder verificar sale con 2, como el barrido;
    - una línea ilegible bloquea siempre;
    - si `describe` falla, confirma con `git tag --merged` en vez de leer el texto del error.
  - **Aviso del padre (fuera de alcance):** `CEROS` cubre solo SHA-1, así que en un repo SHA-256 el borrado de `main` se bloquearía.
  - La config real de git siguió limpia (`~/.gitconfig` igual; `core.hooksPath` sin valor en `--system` ni en `--global`).
  - **Docs del padre:**
    - la fila P4 de `diseno.md`: el canal es `main`, y el porqué de la versión fijada;
    - `diseno.md` §8: el chequeo;
    - el README: `tools/entrega.py` y el pre-push.
  - **Commit:** `ad9e063`.
- **L10 (2026-11-04): A2 hecho por el writer (Sonnet).**
  - **`ticket.py` y `ticket.tests.py` (26/26).**
    - Copia `tickets/_plantilla/` entera, con los bytes tal cual, usando el motor del bootstrap. Nada se pisa, y volver a correrlo completa lo que falta.
    - Rechaza un id con otra carpeta (las archivadas incluidas) y la plantilla ausente, que manda a `/odd-ws:bootstrap`. También lo que escape de la raíz o de la plantilla.
    - Una prueba recorre el AST y confirma que no hay rutas de la instancia escritas a mano (R-8).
  - **Bootstrap:** `bootstrap_instalacion` emite `tickets/_plantilla/.claude/settings.json` con los mismos bytes que el de la raíz.
    - `capas.TICKET_PLANTILLA_DIR` y `capas.TICKET_SETTINGS`.
    - `bootstrap.planificar_archivos`: para compartirlo, el writer extrajo `_revisar_raiz`, `_sumar_accion` y `_armar_plan` de `planificar`, con el mismo orden de revisiones.
  - **Pruebas:** `bootstrap.tests.py` 150/150 (146 previas), `bootstrap_instalacion` 13/13, `bootstrap_cli` 14/14, `bootstrap_e2e` 10/10, `capas` 13/13 y `doctor` 76/76. En `bootstrap_cli` y `bootstrap_e2e`, la lista fijada suma el archivo nuevo.
  - **Mutantes:** 25 de 25 muertos.
  - **Diferencial contra `c66cf0e`, con una spec sintética:** la única diferencia es el archivo nuevo (de 16 a 17), en la corrida real, en el ensayo y en la segunda corrida.
  - **Decisiones del padre sobre las preguntas del writer:**
    - **El límite de los ids con guion queda documentado** en `diseno.md`. Con ids que llevan guion, la carpeta de un ticket puede aparecer también en el glob de otro id. Por eso, cuando el glob encuentra más de una carpeta, las skills tienen que listarlas y preguntar. Eso lo suma T1 a `revisar` y `cerrar`, y A1 lo trae de entrada.
    - **`_dentro` y `_revisar_destino` siguen privados:** solo los usan scripts del plugin y no están en `odd_ws.PUBLICO`.
  - **La corrección de `diseno.md:503` pasó de T1 a A2,** porque es el mismo comportamiento.
  - **Docs del padre:**
    - `diseno.md`: la instalación, la sección «Tickets» y la línea 503;
    - el README: `ticket.py`.
  - **Commit:** `ec318f3`.
- **L11 (2026-11-04): A1 hecho por el writer (Sonnet).**
  - `plugin/skills/abrir/SKILL.md`, de 130 líneas, en voseo, con `disable-model-invocation` y 5 reglas duras. La última es la de las varias carpetas (L10). Tiene 8 pasos:
    1. el pedido, por la herramienta (MCP) del tracker o pegado;
    2. el id, el slug y la carpeta: primero el glob, después `ticket.py --ensayo`, el sí y la corrida;
    3. el borrador del ticket, donde cada «X o Y» queda «por fijar con el líder»;
    4. los docs de dominio por el índice de `knowledge`;
    5. los candidatos de los tickets hermanos;
    6. el worktree, con el comando exacto, que corre el usuario;
    7. el Paso 0;
    8. mostrar, escribir con el sí y los pasos que siguen.
  - **Cada comando se corrió sobre una instancia sintética hecha con el bootstrap real, con git aislado:**
    - `ticket.py`: el ensayo, la creación y el ensayo sobre un ticket existente;
    - el control positivo de cada salida: 1 por un conflicto de id, un id o slug inválido y la plantilla ausente; 2 sin instancia, con la config rota y con un uso mal formado;
    - la corrida desde dentro de un ticket;
    - el glob con varias carpetas (`AB-CD-dos` y `archivo/AB-uno`);
    - el Grep de candidatos;
    - `worktree add`, que con la rama existente sale con 255 sin pisarla, y `switch -c`.
  - **Decisiones del writer, aceptadas por el padre:**
    - Los candidatos de los hermanos y los docs de dominio van a «Contexto técnico» y no a «Candidatos a graduar», que tiene que quedar vacía al graduar.
    - Hay dos sí: uno para crear la carpeta y otro para escribir el contenido.
    - Si el ticket ya existe, la skill pregunta si se retoma.
    - La base del worktree se pregunta. El `git fetch` se propone y lo corre el usuario.
  - **Docs del writer:** `diseno.md`, con la sección «Abrir», y el README, con `skills/abrir`.
  - **Queda para la corrida manual:** la herramienta del tracker en una sesión real.
  - **Commit:** `0d98973`.
- **L12 (2026-11-04): T1 hecho por el writer (Sonnet) y el README por el padre.**
  - **`plantillas/CLAUDE.md`** (122 líneas): los pasos 1, 6 y 7 del ciclo y la lista de skills apuntan a `/odd-ws:abrir`, `/odd-ws:revisar` y `/odd-ws:cerrar`.
  - **`ticket.md`:** dice que el ticket se abre con `/odd-ws:abrir` y se cierra con `/odd-ws:cerrar`.
  - **`bootstrap_textos.tests.py`** (21/21) fija las dos cosas.
    - **RED:** la prueba vieja solo chequeaba presencia, así que primero se escribieron las fijaciones nuevas, que dieron 18/21 por la razón correcta.
    - Las que se rompieron al reescribir la plantilla se arreglaron en el texto, no en las pruebas.
  - **`revisar`** pasa a voseo. El word-diff muestra que solo cambió el registro, también dentro del bloque del prompt del revisor. Las negaciones («no pases») quedan como en `cerrar`.
  - **`revisar` y `cerrar`** suman la regla de las varias carpetas.
  - **El README, del padre:** la instalación con `--scope project` y cómo actualizar. Los comandos se verificaron con `--help`: `install` usa `user` por defecto y `update` detecta el alcance solo.
  - **Verificación:** `bootstrap_cli` 14/14, `bootstrap_e2e` 10/10 y `doctor` 76/76. La corrida completa del writer dio 23 suites en verde y ninguna en rojo.
