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
| M1 | S1, S6 | Correcciones de la corrida manual: F1, F3, F4 y F5 | inline (texto y un script chico, sin razón de writer) | **6**: prosa de skills que ninguna prueba atrapa, salvo la fijación de F1 y la prueba del script de F4 | hecho (L16) |
| V1 | S1, S6 | La entrega `0.2.0` y su etiqueta | inline, después del verificador y la corrida manual | **5**: toca la entrega. Commit propio | hecho: `a41e026`, etiqueta y push (L17) |
| H1 | S1, S6 | Prueba de humo por el camino real | el usuario, después del push autorizado | ninguno | hecho (L18) |
| M2 | S1, S6 | F6: el triaje cuenta consumidores en la base explícita de un repo sin remoto | inline | **3**: cambia la salida del triaje que consume `revisar`. Commit propio | hecho (L20) |
| M3 | S1, S6 | F2 y `--no-track` en el árbol principal de `abrir` | inline | **6**: prosa | hecho (L21) |
| V2 | S1, S6 | La entrega `0.2.1` y su etiqueta | inline | **5**: toca la entrega. Commit propio | pendiente |

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
  - **Commit:** `9996ef1`.
- **L13 (2026-11-04): el verificador independiente de la feature, sobre `9996ef1` contra `8b497d3`.**
  - **En verde:**
    - las 34 suites;
    - cada comando de las tres skills, contra las CLIs reales y sobre una instancia sintética;
    - `ticket.py`: cada rechazo deja el árbol idéntico byte a byte;
    - el diferencial del bootstrap: en `ad9e063` → `ec318f3` y en `8b497d3` → `9996ef1`, la única diferencia es lo pedido;
    - el diferencial del pre-push en un push a una rama de feature, que da salida idéntica;
    - la config real de git, que sigue limpia.
    - También cerró el pendiente de L4: el layout real de las transcripciones de los subagentes es el que espera `rescatar.py`.
  - **Bloqueante B1 (P1, S6 no cumplido):** el pre-push acepta cualquier etiqueta `odd-ws--v*` en el commit empujado, aunque su nombre no sea la versión de su `plugin.json`. Con `git tag odd-ws--v0.4.0` a mano y la versión en `0.3.0`, el push a `main` pasa con «entrega limpia».
  - **Un punto de la spec que `cerrar` incumple (S1, C1, «mostrar antes de escribir»):** los relojes y la bitácora se escriben sin mostrarse, y el chequeo del modo sombra corre después del sí.
  - **Avisos que entran en la misma tanda de corrección, porque son baratos:**
    - `cerrar` §2 apunta a una sección «Dominio» que no se genera; la del índice es «Dónde vive el conocimiento»;
    - `ticket.py` no avisa cuando la plantilla no trae `.claude/settings.json` (una instancia anterior a T9);
    - el paso 6 de la plantilla de `CLAUDE.md` no nombra a `revisor-diseno`;
    - el `worktree add` de `abrir` sin `--no-track`.
  - **Avisos que quedan registrados, sin corregir:**
    - la etiqueta solo se exige en local;
    - mover a mano una etiqueta existente pasa;
    - un mensaje elige «la versión sigue en V» cuando también aplica «apunta a otro commit»;
    - `ticket.py` repite la capitalización que se pidió;
    - `CEROS` y el glob con ids con guion (L9, L10).
  - **Declaración del verificador:** en un primer `git push` sintético, antes de exportar `ODD_WS_DENYLIST`, el barrido leyó la lista negra real una vez. Solo imprimió la cantidad de términos y el contenido barrido era sintético. Los pushes que siguieron usaron la lista sintética.
  - **La corrección:** un writer (Sonnet), en una sola tanda, con un solo rechequeo limitado a B1 y a `cerrar`.
- **L14 (2026-11-04): la corrección y el rechequeo.**
  - **B1:** la etiqueta más cercana cuenta como entrega solo si su nombre es `odd-ws--v<versión del plugin.json de su commit>`; si no, frena con exit 1 y dice el nombre que esperaba. `entrega.tests.py` pasa 23/23.
    - **RED:** 20/23. Las tres nuevas daban «entrega limpia»; una de ellas hace un `git push` real.
    - **`diseno.md` §8**, del padre.
    - **Commit:** `f143a17`.
  - **`cerrar`:** el chequeo del modo sombra pasa a §3, antes de proponer nada. La propuesta (§4) muestra antes del sí:
    - la tabla de aprendizajes;
    - los dos relojes, con sus valores exactos;
    - la entrada de bitácora completa, con la foto de la entrega;
    - el commit de cierre.
    - **El índice, corregido por el padre:** el writer apuntó a «Dónde vive el conocimiento», pero esa sección no lista los docs. Ahora `cerrar` lista la carpeta de `knowledge.docs` y lee el índice de `knowledge.index`, igual que `/odd-ws:abrir`.
  - **`ticket.py`:** avisa por stderr si la plantilla no trae su `settings.json`; stdout y el código de salida no cambian. `ticket.tests.py` pasa 28/28. `abrir` dice qué hacer con ese aviso y suma `--no-track` al worktree. El paso 6 de la plantilla nombra a `revisor-diseno`, con su fijación en `bootstrap_textos` (21/21).
  - **Rechequeo del verificador, limitado a los dos puntos: los dos están corregidos.**
    - B1, con pushes reales a un remoto sintético: las dos etiquetas a mano frenan y `main` del remoto no cambia. Los casos que pasaban siguen pasando.
    - `cerrar`: se cumple «mostrar antes de escribir».
    - La lista negra sintética se exportó antes del primer push, y la config real de git sigue limpia.
  - **Quedan registrados, sin corregir:** `switch -c` con una base remota también la sigue como upstream (aviso del writer), y los avisos que ya listaba L13.
- **L15 (2026-11-04): la corrida manual del ciclo, hecha por el usuario con `--plugin-dir` en la instancia de prueba.**
  - **El recorrido completo funcionó:**
    - `/odd-ws:bootstrap` completó la instancia: 2 archivos creados, 15 que ya existían, y el doctor con 0 FALTA. Commit `528c5c0` en la instancia.
    - `/odd-ws:abrir` T-200: hizo el ensayo antes de crear (con el `settings.json` de la plantilla), dejó la «o» por fijar con el líder y el Paso 0 como pendiente.
    - El cambio en el repo sintético `db`: commit del usuario `96ffb2f`, en la rama del ticket.
    - `/odd-ws:revisar` en modo completo, con 4 corridas. El contrato del resultado (`INSERT … EXEC`, un consumidor sin nombre) lo marcaron `revisor-sql` (WARNING) y diseño (1/3), aunque la sesión había anotado `Risk: none`. El recibo quedó `pendiente` y, cuando el líder respondió, `con-hallazgos`; `--check` dio 0.
    - `/odd-ws:cerrar` mostró todo antes del sí. Hizo dos commits: `dfea5b9`, la fuente de las filas, y `941a6c1`, el cierre. Graduó SQL-01..03 a `capa-sql` con su evidencia. El Conocimiento quedó `graduado` y el Estado `en revisión`.
  - **Hallazgos (la sesión del ticket anotó 6 en su bitácora, marcados `→ motor:`; se suman los del padre):**
    - **F1:** la sesión del ticket no tiene los repos de código como carpetas de trabajo, y nada le dice al usuario que use `--add-dir`.
    - **F2:** con un solo archivo, las 3 corridas de diseño leen en el mismo orden. No se corrige: siguen siendo muestras independientes, y la r2 encontró una SUGGESTION que la r1 y la r3 solo anotaron como límite. El padre lo había llamado «costo para nada», y la corrida lo desmiente.
    - **F3:** los revisores reciben el `CLAUDE.md` del ticket tal como estaba al arrancar la sesión, sin el Paso 0 escrito después. 3 de 4 lo notaron y releyeron el del disco.
    - **F4:** el script de ids de `cerrar` mira solo la matriz. Una instancia que trae un `verificar_<capa>.py` con ids propios, como la de aceptación de P1(a), choca en la fila 9 con SQL-09.
    - **F5:** `revisar` no dice qué estado lleva el recibo cuando hubo hallazgos y ya se resolvieron.
    - **F6 (aviso):** sin remoto, el triaje siempre manda al modo completo, y la salida `--clon` tampoco sirve. Un repo del equipo siempre tiene `origin`.
    - **Solo registrados:** la sesión escribió primero un Estado inválido («en curso») y lo corrigió sola. El molde del origen en SQL-82 y la exigencia de CRLF vienen de la copia de aceptación de la instancia, no de la plantilla (`git grep` en la plantilla: nada). El aviso LF→CRLF al commitear repite la sugerencia ya anotada de un `.gitattributes` generado.
  - **Evidencia para H1:** en la sesión del ticket, `/plugin` mostró `odd-ws @ odd-workspace-template (project)` con el error «not cached at …/odd-ws/0.1.0». O sea, la sesión abierta dentro del ticket **leyó el `settings.json` del ticket**. El error es esperable: el plugin no está instalado para la instancia y el marketplace sigue en una versión vieja. Se resuelve en H1 con `marketplace update` y `install --scope project`. No hay que «resolverlo» desde `/plugin`, porque instalaría la versión vieja.
- **L16 (2026-11-04): la corrección de la corrida manual (M1), inline.**
  - **F1:** la plantilla de `CLAUDE.md` («Cómo se carga el contexto»), el paso 8 de `abrir` y el README dicen cómo abrir la sesión del ticket: `claude --add-dir <ruta>` por cada repo o worktree de «Worktree y rama». `bootstrap_textos` lo fija: RED 21/22, GREEN 22/22. Se descartó generar un `settings.local.json` por ticket con `additionalDirectories`, porque es más maquinaria y la ruta del worktree recién se conoce en `abrir`.
  - **F3:** en el prompt de `revisar`, los revisores leen el `CLAUDE.md` del ticket del disco, aunque ya tengan uno cargado.
  - **F4:** el script de ids de `cerrar` toma el mayor entre la matriz y los ids de `.claude/reglas/verificar_<capa>.py`, y si ese archivo no existe sigue igual. La prueba extrae el bloque de la skill y lo corre sobre una copia de la instancia:
    - el script nuevo da `SQL-83` con el archivo de reglas y `SQL-04` sin él;
    - el viejo de `HEAD` da `SQL-04` con el archivo de reglas, o sea que reproduce el choque;
    - en los tres casos la matriz queda intacta más una línea.
  - **F5:** `revisar` define los tres estados del recibo y dice que, cuando se resuelven los hallazgos de un `pendiente`, el recibo se vuelve a escribir con `con-hallazgos`.
  - **F2 y F6:** sin cambios, por lo que dice L15.
  - **Commit:** `27330d2`. El pre-commit pasó y la config real de git sigue limpia.
- **L17 (2026-11-04): la entrega `0.2.0` (V1).**
  - **Versión:** `plugin.json` pasa de `0.1.0` a `0.2.0`. La mayor sigue en 0, como exige `comun.tests.py` (API 1). El marketplace no declara versión propia, así que manda `plugin.json`. No había ninguna etiqueta `odd-ws--v*` antes.
  - **Etiqueta:** la etiqueta anotada `odd-ws--v0.2.0`, creada con `claude plugin tag ./plugin` sobre el commit de esta entrada, primero con `--dry-run`.
  - **El push** de la rama, `main` y la etiqueta va junto, con autorización del usuario, porque el pre-push exige la etiqueta en el sha de `main`. Después, H1.
  - **Resultado (autorizado por el usuario):**
    - commit `a41e026`; `claude plugin tag` creó `odd-ws--v0.2.0`, que apunta a `a41e026`;
    - `git fetch`: `origin/main` seguía en `8b497d3`, ancestro de `HEAD`, y el remoto no tenía etiquetas;
    - `git push -u origin feat/ciclo-de-vida`: barrido limpio;
    - `git push origin a41e026:refs/heads/main refs/tags/odd-ws--v0.2.0`: barrido limpio y «entrega limpia», `8b497d3..a41e026`;
    - el `main` local se adelantó con `update-ref`, chequeando el valor viejo;
    - `ls-remote`: `main` y la etiqueta despelada en `a41e026`;
    - la config real de git sigue limpia.
    - Este cierre del documento queda sin commitear hasta H1.
- **L18 (2026-11-04): H1, la prueba de humo por el camino real. Pasó. La T9 queda cerrada.**
  - **Instalación:** el usuario corrió, desde la raíz de la instancia, `claude plugin marketplace update odd-workspace-template` y `claude plugin install odd-ws@odd-workspace-template --scope project`.
  - **Sesión abierta dentro de `tickets/T-200-getitems-stock-o-fecha-alta`, sin `--plugin-dir`:**
    - `/plugin` muestra `ODD Workspace` en el scope **Project**, desde `odd-workspace-template`, con 7 skills;
    - el marketplace figura actualizado el 4/11/2026, con 1 plugin instalado, y la pestaña Errors quedó vacía;
    - `/odd-ws:` lista las skills (el usuario confirmó las 7).
  - **S0, confirmado en la máquina:** una sesión abierta dentro de un ticket carga el plugin a través del `settings.json` del propio ticket. Ese archivo lo copia `ticket.py` desde la plantilla.
- **L19 (2026-11-04): la cola de la T9, aprobada por el usuario («Si»).** Son F6, F2 y `--no-track` en el árbol principal de `abrir`, más la entrega `0.2.1`. Los avisos de L13 quedan sin tocar.
  - **`.gitattributes`, descartado con evidencia:** `autocrlf=true` viene de la config del sistema de Git for Windows, o sea que es el default.
    - Un clon con esa config deja el `pre-commit` en CRLF (`w/crlf`), pero el `sh` de Git for Windows lo corre igual: llega a la misma rama y da el mismo mensaje que el control en LF. La prueba usó la config aislada.
    - El doctor tampoco se confunde, porque `plantilla_writer.revisar` normaliza el CRLF.
    - Solo serviría para sacar el aviso LF→CRLF, y un archivo generado más en cada instancia no se justifica por eso.
- **L20 (2026-11-04): F6 (M2).**
  - **El cambio:** `triaje.py` cuenta los consumidores en la base explícita (`--repo RUTA#BASE`) de un repo **sin ningún remoto**. El repo se identifica por su `--git-common-dir`, así que también vale desde un worktree.
    - La salida lo dice: «<repo>: sin remoto, conté en la base <hash>».
    - Un repo con remoto pero sin `origin/HEAD` sigue invalidando, porque una base vieja perdería consumidores nuevos de la rama de integración.
    - El mensaje del inválido ahora dice «si no tiene remoto, pasa su base con --repo RUTA#BASE».
  - **Pruebas:**
    - RED 75/78 y GREEN 78/78, con 3 pruebas nuevas, más una aserción en la prueba existente del repo sin `origin/HEAD`.
    - La prueba del repo con remoto ya pasaba antes del cambio: fija el comportamiento previo.
    - 3 mutantes, los tres muertos: sin la condición de no tener remoto, sin que la base habilite el conteo y sin la línea de dónde se contó.
  - **El diferencial** contra el `triaje.py` de `HEAD`, con la config aislada:
    - el caso de la corrida (sin remoto, base `a5d79a8`) pasa de `COMPLETO`, con consumidores inválidos, a `RAPIDO`;
    - sin remoto y sin base, con remoto y base por defecto, y con remoto y base explícita, la salida es idéntica byte a byte.
  - **Docs:** `diseno.md` (Consumidores) y `revisar` (La base).
  - **Commit:** `70c20dc`.
- **L21 (2026-11-04): F2 y `--no-track` (M3).**
  - **F2:** la tabla de modos de `revisar` dice que, con un solo archivo, las 3 corridas de diseño leen en el mismo orden y son muestras independientes, y que no se anuncian como «en otro orden». El costo no baja.
  - **`--no-track`:** el comando del árbol principal en `abrir` pasa a `git -C <repo> switch --no-track -c <rama> <base>`, y `diseno.md` §Abrir nombra los dos comandos con `--no-track`.
    - Lo verifiqué en un clon scratch, con la config aislada: sin la opción, la rama nueva queda con upstream `origin/feat/T-200-…`; con ella, sin upstream.
