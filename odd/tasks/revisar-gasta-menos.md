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
| T2 | S4 | Los secretos tapados (toca `rescatar._guardar`, después de T1) | por definir | pendiente | |
| T3 | S1 | Los chequeos antes de los revisores | por definir | pendiente | |
| T4 | S3 | Las desviaciones conocidas | por definir | pendiente | |
| T5 | S5 | El CHANGELOG, la versión, el verificador y publicar con el ok del autor | docs inline; verificador delegado | pendiente | |

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
