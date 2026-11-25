# Revisar gasta menos: los chequeos antes de los revisores, el reporte fuera del contexto, las desviaciones conocidas y los secretos tapados (R16)

Objetivo: que `revisar` corra lo determinista antes de gastar en revisores (I47), que los reportes no inunden el contexto del orquestador (I35), que no se vuelvan a plantear las desviaciones conocidas de la instancia (I92) y que lo que se guarda salga con los secretos tapados (I86).
Rama: `feat/revisar-gasta-menos`, en `D:/Project/odd-ws-wt/revisar`. Está apilada sobre la punta de R15 (`9412353`, la `0.14.0` sin publicar): si R15 cambia, se integra hacia acá con un merge. Va un agente por vez (L1). Entrega: un commit por unidad. Sale en la `0.15.0`, con el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap.
- Lo marcado como **decisión de diseño** lo decidió el orquestador con la autonomía que dio el autor para esta jornada (L1). Queda a ratificar por el autor y su auditor.
- El mapa del código está en engram (`odd/r16/diseno`).

- **S1** (I47, los chequeos antes de los revisores). «`revisar` corre los chequeos deterministas de cada capa tocada sobre el diff antes de lanzar los revisores, y lo que falla se corrige antes de gastar tokens. En el mismo paso entran los marcadores de conflicto del diff (R6, L2).»
  - **Decisión de diseño:**
    - El triaje corre `verificar_capa.verificar_archivo(..., contra=<base>)` sobre cada archivo activo con capa. Es el mismo llamado que ya hace `revisar_turno.py:213-226`: aplica la calibración y deja pasar lo preexistente.
    - El resultado va a `triaje.json`, en una clave `chequeos`, y al texto de `formatear`.
    - Si algún chequeo falla, el triaje propone «corregir antes de lanzar», y lanzar igual pide un sí explícito del usuario.
    - Los hallazgos de los chequeos entran al prompt de los revisores como «ya detectado: no lo reemitas».
    - El rechequeo corre el triaje de nuevo, así que también los chequeos.
    - `odd_ws/marcadores.py` se generaliza para comparar la base contra el árbol de trabajo, incluidos los archivos sin trackear.
- **S2** (I35, el reporte fuera del contexto). «El revisor deja el reporte entero en su último bloque de texto y devuelve una sola línea de veredicto; `rescatar.py` lee el reporte de ese bloque.» El porqué: «Cada reporte, de 14k a 27k caracteres, entraba entero al contexto del orquestador».
  - **Decisión de diseño:**
    - La regla va en el prompt (`skills/revisar/references/prompt.md`) y no en una plantilla nueva del revisor. El doctor solo regenera writers, y un cambio de plantilla no llegaría a los revisores ya generados (`prompt.md:27`).
    - El revisor escribe el reporte entero como su último bloque de texto, y su devolución final es una sola línea de veredicto.
    - `rescatar.py` toma el bloque de texto inmediatamente anterior a la devolución. Si solo encuentra la línea de veredicto, falla en voz alta: nunca guarda el veredicto como si fuera el reporte.
    - En Pi lee los ítems de texto del hilo. Codex sigue sin rescate, como hoy.
  - **Seguimiento (fuera de alcance):** un ítem del doctor que regenere los agentes revisores, como ya hace con los writers.
- **S3** (I92, las desviaciones conocidas). «Una lista de desviaciones conocidas para toda la instancia: código que parece un error y es a propósito, cada uno con su porqué. `revisar` no las vuelve a plantear en ningún ticket, y la I90 las usa como índice.»
  - **Decisión de diseño:**
    - Es un archivo propio de la instancia, `.claude/reglas/desviaciones.csv`, con las columnas `id`, `ubicacion`, `resumen`, `porque` y `fecha`. No es un destino de la matriz, porque cada fila de la matriz va atada al prefijo de una capa y su ID tiene que aparecer una sola vez en su destino.
    - `ubicacion` es `<repo>:<ruta>@<hash>:<ini>-<fin>` para el código de un repo de la config, o `<ruta>` para un archivo de la instancia. Reusa `matriz.parsear_origen`, que es la clave que necesita el índice de I90.
    - El cargador devuelve una lista de problemas, y el doctor da AVISO si una fila está mal formada. Que el archivo falte no es un problema.
    - `revisar` pasa las filas a los revisores como «no las reemitas», igual que las decisiones del ticket (I33).
    - El skill `cerrar` ofrece graduar a ese archivo una desviación aprobada.
- **S4** (I86, los secretos tapados). «Antes de guardar texto en la instancia, odd-ws tapa los secretos que encuentre (tokens, claves) con un marcador.» Lo que enseñó la prueba de align-cli, del roadmap: «van patrones concretos y no el genérico […] y se revisan los diffs y los fragmentos de código».
  - **Decisión de diseño:**
    - Un módulo nuevo, `odd_ws/secretos.py`, con `tapar(texto) -> (texto, cuantos)`.
    - Usa solo patrones concretos, cada uno con su prueba de control positivo: AWS `AKIA…`, GitHub `ghp_`/`gho_`/`github_pat_`, Slack `xox…`, Google `AIza…`, bloques de clave privada, OpenAI `sk-…`, Anthropic `sk-ant-…` y Stripe `sk_live_…`. No hay ningún patrón genérico de «etiqueta:valor».
    - Tapa después del rescate y antes del commit: en `rescatar._guardar` y en `recibo._guardar`, y con un comando que `revisar` corre sobre `entrada/*.diff` y `consolidado.md` antes de sellar.
    - Los revisores siguen viendo los diffs crudos, porque un secreto en el código es en sí un hallazgo CRITICAL.
- **S5** (la versión). Se actualizan:
  - el CHANGELOG de la `0.15.0`;
  - `Doc/actualizar.md`, si cambia alguna plantilla;
  - la versión en los dos `plugin.json` y en `package.json`, el README y `Doc/`;
  - `tools/huellas.py`, que se corre después de subir la versión.
  
  Después, un verificador independiente. Publicar lleva el ok del autor y su auditor.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento y su espejo en engram | inline | hecha | |
| T1 | S2 | El reporte fuera del contexto | inline (unos 100 líneas, y el único lugar de agente lo ocupaba el verificador de R15) | hecha (L3) | (con T0) |
| T2 | S4 | Los secretos tapados (toca `rescatar._guardar`, después de T1) | delegada: un solo writer en este worktree (motivo: el respaldo de contexto del orquestador) | hecha (L4) | |
| T3 | S1 | Los chequeos antes de los revisores | delegada: un solo writer en este worktree (motivo: el respaldo de contexto del orquestador) | hecha (L5, L6) | `a70cd94` |
| T4 | S3 | Las desviaciones conocidas | delegada: un solo writer en este worktree (motivo: el respaldo de contexto del orquestador) | hecha (L7) | `b37a860` |
| T5 | S5 | El CHANGELOG, la versión, el verificador y publicar con el ok del autor | docs inline; verificador delegado | versión lista (L8); verificador hecho y sus dos bloqueantes corregidos (L9); sin publicar, espera al autor y su auditor | `44fffdf` y la corrección |

El orden sigue los archivos compartidos: `rescatar.py` lo tocan S2 y S4, y el skill `revisar` lo tocan las cuatro. Va de a una unidad, sin writers en paralelo (L1).

## Log

- **L1** (2026-11-24) El autor aceptó el orden de las versiones, con la `0.15.0` = I47, I35, I92 e I86: «Si, va ese orden, arranca con la 0.14.0».
  - Después dejó la jornada a criterio del orquestador: «Apartir de ahora te dejo a tu criterio, probablemente antes de sacar la version enviare un auditor, asi que tu sigue trabajando el resto de versiones solo dejalas listas que mañana miramos en que quedamos ya te dejo libremente espero que nada que interrumpa».
  - Y pidió, solo para este loop: «intenta trabajar con menos agentes paso a paso solo lo necesario».
- **L2** (2026-11-25) El explorador de la R16 mapeó el código en `0b44438` (engram `odd/r16/diseno`). Lo que más pesa para el diseño:
  - el doctor solo regenera writers;
  - `rescatar` toma el reporte de la devolución del subagente y descarta el texto anterior a cada `tool_use`;
  - `verificar_archivo` ya acepta `contra`;
  - la matriz ata cada fila a una capa;
  - no hay ningún tapado de secretos;
  - y la lista negra de `tools/barrido.py` no viaja con el plugin.
- **L3** (2026-11-25) T1, inline.
  - **Decisión de diseño:** el veredicto tiene una forma fija, `VEREDICTO: <n> CRITICAL, <n> WARNING, <n> SUGGESTION`, para distinguirlo de un reporte viejo que venga entero en la devolución.
    - **Claude Code:** si la devolución empieza con `VEREDICTO:` y es una sola línea, el reporte es el texto del mismo mensaje antes del `SubagentHandback`. Si no hay ese texto, la corrida es `solo_veredicto`: `FAIL … devolvio solo el veredicto`, sale con 1 y no escribe nada.
    - **Una devolución sin `VEREDICTO:`** sigue siendo el reporte, como antes, aunque haya texto antes. El texto posterior a la devolución tampoco la pisa.
    - **Pi:** si `task.result` es el veredicto, el reporte es el texto del hilo después de su último ítem `tool`.
    - El dict de la corrida suma `veredicto`.
  - **La regla va en `references/prompt.md`,** con su porqué. Se actualizaron también `references/rescate.md` y `Doc/diseno.md`. La consolidación (paso 7) ya leía los reportes de `corridas/`.
  - **RED:** 6 pruebas nuevas en `rescatar.tests.py`:
    - el texto previo con veredicto;
    - solo el veredicto;
    - una devolución sin veredicto con texto antes;
    - el CLI, que falla en voz alta;
    - en Pi, el texto después de la última herramienta;
    - en Pi, solo el veredicto.
  - **GREEN:** `rescatar` 67/67.
  - **Risk: item 3 (contratos).** Cambia el contrato entre el orquestador y los revisores: lo que devuelven y de dónde se rescata. Lo revisa el verificador de la R16.
- **L4** (2026-11-25) T2, un writer. Lo cortó el límite de 5 horas y se lo retomó con su contexto. Cubrió S4.
  - **`odd_ws/secretos.py`:**
    - `tapar` usa solo los patrones concretos de S4, y `intentar_tapar` devuelve además el error interno.
    - `tapar_valores` recorre dicts y listas y tapa solo los valores, nunca las claves.
    - Una clave privada conserva su BEGIN y su END y tapa cada línea del cuerpo con el prefijo que comparte con el BEGIN, como el `+` de un diff. Así el diff sigue siendo válido.
    - Slack exige un número después de `xox?-`, para no tocar la prosa.
  - **`tapar.py`:**
    - Expande los comodines él mismo, porque PowerShell y cmd no lo hacen.
    - No reescribe un archivo sin secretos y conserva la codificación.
    - Sale con 2 si falla, sin escribir.
  - **Dónde se aplica:**
    - `rescatar._guardar` tapa sus cuatro archivos, y los JSON siguen siendo válidos.
    - `recibo._guardar` tapa `--verificacion`, `--derivado` y `--bajada`.
    - El paso 8 del skill suma una línea que remite a «Los secretos» en `references/recibo.md`: `tapar.py` sobre `entrada/*.diff` y `consolidado.md`, antes del `--check`.
  - **El recibo sigue valiendo:** hashea el `git diff` vivo de cada repo, no `entrada/*.diff`. Una prueba corre el flujo real (`--write`, `tapar.py`, `--check`, `--sellar`), y no hubo que excluir ningún archivo.
  - **La salida:** sin secretos es igual byte a byte que antes (diferencial de 5 comandos y 15 archivos). Con secretos, la línea `ok` y la de `recibo escrito` dicen cuántos se taparon.
  - **Las pruebas:** los tokens falsos se arman concatenando, para que el código commiteado no traiga ningún token literal.
  - **Suites:** `secretos` 11/11, `tapar` 9/9, `rescatar` 68/68, `recibo` 116/116, `triaje` 103/103, y `registro`, `comun`, `paquetes`, `memorias`, `auditar_lecturas` y `puntuar` en verde. El barrido sobre lo tocado salió limpio.
  - **Para T3 y T4:** el núcleo de `skills/revisar/SKILL.md` pesa 17.381 bytes contra un tope de 17.408 (`NUCLEO_MAXIMO` en `recibo.tests.py`). Lo nuevo va a las referencias, o hay que liberar espacio en el núcleo.
  - **Risk: item 3.** Cambian los archivos guardados y el texto del recibo cuando hay un secreto. Lo revisa el verificador.
  - **Scratch del writer:** `%TEMP%\tapar-diferencial-2siIec`. Va a la limpieza del autor.
- **L5** (2026-11-25) T3, un writer, después de integrar la corrección de R15 (`7e180d8`). Cubrió S1.
  - **`triaje.json` suma la clave `chequeos`** con:
    - `archivos`;
    - `hallazgos` (repo, ruta, capa, id, modo, severidad, línea, mensaje, texto);
    - `marcadores`;
    - `sin_chequear` (con su motivo);
    - `corregir_antes_de_lanzar`.
  - **El texto del triaje suma una última línea.** Si todo está limpio dice «sin hallazgos ni marcadores de conflicto». Si no, «corregir antes de lanzar», con un renglón por cada cosa.
  - **El skill:** lanzar sin corregir pide un sí aparte, y el detalle está en la referencia nueva `references/chequeos.md`. `prompt.md` suma el bloque «ya detectado por los chequeos del triaje, no lo reemitas», y `rechequeo.md` dice que el rechequeo vuelve a correr los chequeos.
  - **`marcadores_contra(raiz, base)`** compara la base contra el árbol de trabajo, también lo no trackeado. El CLI de lo stageado corre los mismos comandos que antes.
  - **Decisiones del writer que se aceptan:**
    - Los archivos del taller se miden contra el árbol vacío, así que se comparan con su par o con el archivo entero.
    - El triaje llama a `verificar_archivo` sin `aislar_la_capa`, así que un módulo de capa que revienta sale como «no se pudo chequear», y eso también pide corregir antes de lanzar.
    - `verificar_archivo` suma el parámetro opcional `errores`. Sin él se comporta igual que antes.
    - Los marcadores se buscan en todos los archivos del diff, incluidos los docs.
    - El chequeo de marcadores no escribe `.git/index` (`--no-optional-locks -c diff.autoRefreshIndex=false`).
    - Con `--no-index`, un `error:` o un `fatal:` en stderr cuenta como falla.
    - Lo que se lanzó sin corregir entra a la consolidación bajo un título propio.
  - **El núcleo de `SKILL.md`** bajó de 17.381 a 17.337 bytes, contra un tope de 17.408 que no se tocó. Se sacaron dos frases que ya estaban en las referencias.
  - **Suites:** `triaje` 110/110, `marcadores` 22/22, `verificar_capa` 136/136, `recibo` 116/116 (con la prueba del tamaño del núcleo), `revisar_turno` 34/34, `registro` 7/7, `rescatar` 68/68, `tapar` 9/9.
  - **Diferencial contra `7e180d8`:**
    - En el triaje (texto y `--json`), el código y stderr son iguales. stdout cambia solo por la línea nueva y la clave `chequeos`.
    - El CLI de marcadores stageados da lo mismo que antes.
  - **El costo:** unas 4 o 5 llamadas a git por cada archivo con capa, más una por cada archivo no trackeado.
  - **Risk: item 3.** `triaje.json` gana una clave que leen `recibo` y `rescatar`, y el flujo de `revisar` gana un sí. Lo revisa el verificador.
  - **Scratch del writer:** varias carpetas `%TEMP%\r16-t3-*`, `%TEMP%\tmp.PXohDLO8kO`, `%TEMP%\triaje-plantilla-ng2lfqcr` y `%TEMP%\triaje-test-4b3wy2qv`. Van a la limpieza del autor.
- **L6** (2026-11-25) El primer commit de T3 lo frenó el pre-commit: «suite en rojo: plugin/scripts/triaje.tests.py». A mano daba 110/110.
  - **La causa:** durante un commit, git le exporta `GIT_INDEX_FILE` a los hooks, y `marcadores.git` no limpia el entorno. Eso es a propósito, porque el CLI de lo stageado necesita el índice del commit. Pero `marcadores_contra` mira otros repos y heredaba ese índice ajeno. Con él, el marcador de un archivo trackeado desaparecía en silencio y el triaje decía «limpio».
  - **El arreglo, inline:**
    - `git`, `_chequeo_del_diff`, `marcadores_nuevos`, `sin_trackear` y `marcadores_contra` aceptan un `entorno` opcional.
    - El triaje les pasa `recibo._entorno()`, el mismo entorno limpio que usa para el resto de su git.
    - Sin `entorno`, todo se comporta igual que antes, también el CLI de lo stageado.
  - **RED:** `test_chequeos_los_marcadores_no_dependen_del_indice_de_git_del_entorno`, con un `GIT_INDEX_FILE` ajeno en el entorno.
  - **GREEN, con el índice ajeno puesto:** `triaje` 111/111 y `marcadores` 22/22.
- **L7** (2026-11-25) T4, un writer. Cubrió S3.
  - **El cargador `odd_ws/desviaciones.py`** devuelve `(filas, problemas)`.
    - Sin archivo no lee la config. Con archivo y la config rota lanza `ConfigRota`, y el doctor da NO APLICA, como los demás ítems.
    - Cada fila mal formada es un problema, con su línea y todos sus defectos juntos.
    - `ubicacion` de repo exige `@hash` y se valida con `RE_RANGO` y `parsear_origen`. La ruta de la instancia rechaza `@`, `:`, `\`, espacios, una `/` inicial y `..`.
  - **El CLI `desviaciones.py`** imprime las filas válidas para el prompt (o `ninguna`). Sale con 1 si hay problemas, que van a stderr, y con 2 si hay un error de uso.
  - **El doctor** suma el ítem `desviaciones`, después de `plantillas`. Sale OK con la cuenta y AVISO, sin arreglo, con los problemas.
  - **`revisar`:**
    - `prompt.md` suma el bloque de desviaciones al lado del de las decisiones del ticket.
    - El núcleo suma una línea en la consolidación: lo que reabre una desviación sin ser CRITICAL va aparte.
    - Para pagar esos bytes se sacó del paso 4 el porqué del ID de ejemplo, que ya está en `prompt.md`. El núcleo baja de 17.337 a 17.312 bytes, con un tope de 17.408.
  - **`cerrar`:**
    - Suma una fila en el triaje del paso 2, una viñeta en el paso 5 y el archivo en la regla de destinos.
    - El detalle y un script para agregar filas van en la referencia nueva `references/desviaciones.md`. El paso 5 no la nombra por archivo, para que la prueba de IDs de `memorias.tests.py` no lea su `RUTA`.
    - El núcleo de `cerrar` sube de 12.943 a 13.297 bytes, con un tope de 13.312: quedan 15.
  - **Para el auditor:** el cargador usa tres funciones privadas de `config_loader` (`_leer_objeto`, `_version`, `_banderas`), porque `config_loader.py` estaba fuera de lo que el writer podía tocar. Lo limpio sería una función pública que lea las claves de los repos.
  - **Suites:**
    - `desviaciones` (módulo) 13/13, `desviaciones` (CLI) 5/5, `doctor` 244/244, `recibo` 116/116 (con el tamaño del núcleo), `registro` 7/7, `matriz` 60/60;
    - `memorias`, `rescatar`, `tapar`, `bootstrap`, `bootstrap_agentes`, `bootstrap_e2e`, `plantilla_writer`, `capas`, `tools/entrega` y `tools/huellas` en verde;
    - con un `GIT_INDEX_FILE` ajeno, las tres suites tocadas también en verde.
  - **Diferencial del doctor contra `a70cd94`:** la única fila nueva es `desviaciones OK sin desviaciones anotadas`.
  - **Risk: item 3.** El prompt de los revisores gana un bloque, el doctor un ítem, y cambian los núcleos de `revisar` y `cerrar`.
  - **Scratch del writer:** `%TEMP%\r16-t4-Futrpt`. Va a la limpieza del autor.
- **L8** (2026-11-25) T5, la versión, inline.
  - La `0.15.0` quedó en los dos `plugin.json`, el `package.json`, el README, `Doc/actualizar.md:28` y `Doc/uso.md:66`. El CHANGELOG suma su sección.
  - En el roadmap, R16 queda «lista, sin publicar», y sus cuatro ideas quedan «lista (`0.15.0`, sin publicar)».
  - Esta versión no cambia ninguna plantilla de la instancia: `git diff f915b0b..HEAD -- plugin/plantillas` sale vacío. Por eso `Doc/actualizar.md` no suma una entrada.
  - **La tabla de huellas.** `tools/huellas.py` dio 107 huellas, de la `0.2.0` a la `0.15.0`. Como la `0.14.0` todavía no tiene etiqueta, el árbol actual queda bajo la `0.15.0` y la `0.14.0` no aparece.
    - **Al publicar:** después de etiquetar la `0.14.0`, hay que regenerar la tabla en esta rama antes de empujar la `0.15.0`. El pre-push lo exige.
    - Una instancia que anotó «0.14.0» necesita esa entrada para saber que nada cambió desde ahí.
  - Falta el verificador independiente de toda la feature (Risk item 3), y después el ok del autor y su auditor.
- **L9** (2026-11-25) El verificador independiente, sobre `44fffdf` contra `f915b0b`. Lo cortó el límite de 5 horas y se lo retomó con su contexto.
  - **S1, S2, S3 y S5: PASS.**
    - Los diferenciales del triaje, del rescate (Claude Code y Pi, al estilo viejo) y del doctor solo cambian lo pedido.
    - Los marcadores son iguales con y sin `GIT_INDEX_FILE` o `GIT_DIR` ajenos.
    - El índice no se toca, y el CLI de lo stageado no cambia.
    - Suites: 61 de 61 archivos (2.792 pruebas) y el shim en verde, y las 8 suites del entorno del hook en verde con un índice ajeno.
  - **S4: FAIL, por dos bloqueantes en las claves privadas de `odd_ws/secretos.py`:**
    - **B1.** En el diff de una rotación de clave (BEGIN y END de contexto, cuerpo con `-` y `+`), las líneas del cuerpo perdían su prefijo de diff, y el parche quedaba corrupto.
    - **B2.** Dos menciones de los encabezados PEM a menos de 12.000 caracteres se tomaban como una clave, y se borraba lo de en medio: un hallazgo CRITICAL del reporte rescatado, o el código de quien firma XML.
  - **La corrección, un solo lote, inline:**
    - Un bloque se tapa solo si su cuerpo son líneas de armadura base64, encabezados PEM (`Proc-Type`, `DEK-Info`, `Version`, `Comment`, `Hash`), líneas vacías o separadores de diff (`@@`, `\ `).
    - Cada línea conserva su propio prefijo de diff (`+`, `-` o espacio) y su sangría.
    - Si un emparejamiento no valida, la búsqueda sigue desde el `BEGIN` siguiente, así que una clave real después de una mención en prosa igual se tapa.
    - El tope del cuerpo sube a 64.000 caracteres: era la advertencia 7, una clave PGP grande.
  - **RED**, con dos pruebas nuevas en `secretos.tests.py`: la rotación de clave en un diff, y los encabezados nombrados en prosa y en código, más la clave real después de la prosa.
  - **GREEN:** `secretos` 13/13 y `tapar` 9/9.
  - **La recomprobación de B1**, con un diff real de rotación de una clave RSA: las líneas `+/-` siguen siendo 16, y `git apply --numstat` da `8 8`, así que el parche sigue bien formado.
  - **Advertencias para el autor y su auditor** (no se arreglaron en este lote):
    1. Una devolución de una línea con otra forma, como `**VEREDICTO:**`, se guarda como el reporte, con salida 0. Ya pasaba en la base, pero I35 lo vuelve más probable.
    2. Si falla una escritura en un archivo posterior, `tapar.py` deja escritos los anteriores, y sale con 2.
    3. `triaje.json` no se tapa, a propósito, y ahora trae los mensajes de las reglas de la instancia.
    4. La `ubicacion` de una desviación no puede llevar una ruta con espacios, porque hereda `RE_RANGO`.
    5. El modo 0 no dice qué hacer con «corregir antes de lanzar».
    6. A los núcleos les queda poco margen: 96 bytes a `revisar` y 15 a `cerrar`.
    7. Una corrida `solo_veredicto` queda como `sin_reporte` en `costo.json`.
  - **El scratch del verificador y de la recomprobación va a la limpieza del autor:** `%TEMP%\r16-verif-24Toof` y `%TEMP%\r16-recheck-b1-faqsc8h2`.
