# Compatibilidad con el stack de Gentle 4.8 (R6)

Objetivo: que `revisar` funcione completo en Pi y en Codex con las versiones nuevas de Gentle Shell y Gentle AI, y sumar lo que esas versiones enseñan y odd-ws puede usar en los tres hosts. Sale en la próxima versión, junto con R5, cuando el autor lo decida.
Rama: `feat/compat-gentle`, desde `8a4b44d` (R5 hasta T2); T2 y T3 se hacen después de juntar `feat/costo-de-revisar` con T3 de R5, porque tocan los mismos archivos. Entrega: una rama con un commit por unidad; el push a main y la etiqueta, solo con autorización.
Pruebas: `python3 plugin/scripts/<script>.tests.py`, todas con el bucle de `CONTRIBUTING.md`, y `node --test plugin/shim/*.test.ts`.

## Specs

Cada spec cita al autor tal cual. El diseño de cada una es la fila del plan que el autor aprobó (L3), y sale de la evaluación de L2.

- **S1. El alcance.** «Me gustaria que investigues sobre esto, a ver si puede a ver algo a reciclar o extrapolar que podamos utilizar e implementar o ideas», «si, arregla lo de Pi y anota el resto(Pero tambien antes, evalua todo esto nuevos riesgos de compatibilidad y ideas para reciclar de manera riguroso 1 por 1, analizalo si lo tomamos tal cual o se puede hacer mejor la implementacion de cada punto, ya que estamos en un punto de zona solidad en proyecto lo ideal es pulir y refactirizar y mejorar con bastante calidad)» y «Si apruebo el plan».
- **S2. Rescatar en Pi (punto 1).** `rescatar.py --host pi` lee el archivo que Gentle Shell guarda por tarea (`<agentHome>/gentle-agents/tasks/<task_id>.json`), con el reporte entero, los tokens y las herramientas usadas, y escribe lo mismo que en Claude Code. Si no está, se recurre a `subagent_result` y se avisa. Quedan descartados renombrar los revisores a `review-*` y subir `report_max_bytes` desde el doctor (L2).
- **S3. El límite de hilos de Codex (punto 2).** En `revisar`, un lanzamiento que el host rechaza por su límite de concurrencia no cuenta como corrida cortada. Se espera a una corrida que esté en marcha, se cierra la que termina, se relanza la rechazada y se avisa que la revisión va por tandas. La regla es la misma para todos los hosts.
- **S4. Los marcadores de conflicto (punto 4).** El pre-commit propio de odd-ws rechaza un commit que agrega `<<<<<<<` y `>>>>>>>` en un mismo archivo. Usa `git diff --cached --check` filtrado a esos dos marcadores, porque un `=======` suelto es un subrayado de Markdown. Respeta `conflict-marker-size` de `.gitattributes`, y si git falla deja pasar el commit.
- **S5. Los overlays de herramientas en Pi (punto 5).** La documentación y el texto de `pi-agentes` dicen que el doctor no ve los overlays de Gentle Shell (#3223), que pueden cambiar las herramientas de un agente al cargarlo.
- El punto 3, el costo del orquestador y el aviso de corridas en serie, va en R5 como T5 ([costo-de-revisar](costo-de-revisar.md)).

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T0 | S1 | Este documento, y las ideas I48 a I54 en el roadmap | inline | hecho | este commit |
| T1 | S4 | El chequeo de marcadores en `.githooks/pre-commit`, con su helper y sus tests | delegada: no comparte archivos con R5. Risk: item 5, porque es la compuerta de commit del repo; lleva verificador | hecho; verificador: PASS (L4) | `a179a8e` |
| T2 | S2, S5 | `rescatar.py --host pi`, su helper en `hosts/pi.py`, los pasos 4 y 6 de `revisar` y los docs | delegada, después de T3 de R5. Risk: item 6, porque el archivo de tarea es interno de Gentle; lleva una prueba real en Pi | hecho; verificador: PASS (L4). Falta la prueba en vivo (F9) | `b4a5eb9` |
| T3 | S3 | La regla del límite de concurrencia en `revisar` | con T2: los mismos pasos de la skill. Risk: none | hecho (L4) | `11bdb89` |
| F1 | S4 | Seguimiento: el ejemplo de exclusión del mensaje de bloqueo no sirve para una ruta con espacios; en `.gitattributes` va entre comillas, con escapes de C (L4) | aparte | anotado | |
| F2 | S4 | Seguimiento: `git rebase --continue` no corre el pre-commit, ni antes ni ahora, así que un conflicto que quedó con marcadores entra. Se documenta en §8 (L4) | aparte | anotado | |
| F3 | S2 | Seguimiento: `auditar_lecturas.py` solo clasifica `Read`, `Grep` y `Glob`, así que una corrida de Pi sale limpia aunque lea una ruta prohibida. Va antes de que `eval-reviewers` soporte Pi (L4) | aparte | anotado | |
| F4 | S2 | Seguimiento: una corrida de Pi sin `task.usage` cuenta como medida. Además, `--sesion` con una carpeta sin `gentle-agents/tasks` sale con 1, y el doc dice 2 (L4) | aparte | anotado | |
| F5 | S5 | Seguimiento: la línea de `pi-agentes` que muestra el doctor no dice lo de los overlays: solo lo dicen la nota del manifiesto y los docs (L4) | aparte | anotado | |
| F6 | S2 | Seguimiento: los límites de gentle-shell que los docs no nombran (L4): <ul><li>la historia se poda a 200 tareas;</li><li>`usage` suma solo las primeras 128 respuestas;</li><li>el guardado final es asíncrono, así que un rescate que llega antes ve `running`;</li><li>un reporte cortado por `stopReason: length` queda `completed`, y en Claude Code pasa lo mismo.</li></ul> | aparte | anotado | |
| F7 | S2 | Seguimiento: fuera de una sesión de gentle-shell, la regla cae en `~/.pi/agent`, pero el hogar aislado por defecto es `~/.gentle-shell/agent`. Dentro de la sesión, el lanzador fija las dos variables (L4) | aparte | anotado | |
| F9 | S2 | La prueba en vivo: en esta máquina no hay archivos de tarea de Pi, así que falta una revisión real en gentle-shell con `--host pi`. La corre el autor | con el autor | pendiente | |

## Log

- **L1** (2026-11-18) Los pedidos del autor, tal cual, son los de S1. Antes de eso, él pegó el anuncio de la versión (Gentle Shell v4.8.0, Gentle AI v4.5.0 y Engram v3.7.2) y el del benchmark de Gentle.
- **L2** (2026-11-18) La evaluación, hecha por dos analistas sobre `8a4b44d` y los PR públicos de Gentle.
  - **El tope de reportes (#3115) es real.** De 28 reportes de diseño reales, 26 pasan los 16 KB, y el corte se come las tablas de evidencia y las derivaciones. Pero el problema de fondo es otro: en Pi nunca hubo rescate, porque `rescatar.py` solo lee los transcripts de Claude Code.
  - **Los overlays (#3223)** cambian las herramientas de un agente por su nombre al cargarlo, y `pi-agentes` no los ve.
  - **Codex (#6121)** no toca la confianza. Codex rechaza los lanzamientos que pasan `max_threads`, que es 4, o su límite de V2, que es 3, y un `completo` con 2 capas o más lanza 5 corridas o más.
  - **Ideas adoptadas:** medir al orquestador (T5 de R5), y los marcadores de conflicto en el pre-commit propio en vez de en el guard.
  - **Ideas que pasan al roadmap:** I48 a I54.
  - **Descartes:**
    - el permiso de push recordado: pedirlo cada vez es la protección;
    - la admisión de writers en lote, porque un hook de Claude Code no ve las otras llamadas del mismo mensaje;
    - el banco sintético para decidir O6, porque exagera los aciertos: las formas de revisión hallaron 4 de 4 defectos sembrados y como mucho 2 de 6 reales.
- **L3** (2026-11-18) El autor aprobó el plan: «Si apruebo el plan». Siguiente paso: T1 en paralelo con R5; T2 y T3 cuando cierre T3 de R5.
- **L4** (2026-11-19) T1, T2 y T3 hechos, con verificadores independientes. El límite de 5 horas de uso cortó a dos agentes a mitad de camino, y se retomaron desde donde estaban con el sí del autor («si, retomalos ahora»).
  - **T1 (`a179a8e`).**
    - **Qué hace:** `odd_ws/marcadores.py`, llamado desde `.githooks/pre-commit`, bloquea solo cuando un mismo archivo agrega `<` y `>` de conflicto.
    - **Supuestos de diseño:**
      - Las fallas de git dejan pasar el commit.
      - En un merge, solo cuenta el primer padre.
    - **Superficie extra:** el autor autorizó el stub en `corredores.test.ts` («Si, autoriza ese archivo»).
    - **Verificador: PASS.** Corrió 61 escenarios, con 122 commits reales entre el hook viejo y el nuevo:
      - los 34 bloqueos traen los dos marcadores en un archivo, y en todos HEAD y el índice quedan como estaban;
      - los 27 que pasan dan la misma salida que antes.
    - **Avisos:** F1 y F2.
  - **T2 (`b4a5eb9`).**
    - **Qué hace:** `rescatar.py --host pi` lee `<agentHome>/gentle-agents/tasks/<id>.json` y devuelve el mismo dict que en Claude Code. De la tarea salen `turnos`, `inicio`, `fin`, `salida` y las dos cachés; las de contexto quedan en null.
    - **Verificador: PASS.** Confirmó el formato contra el código de gentle-shell, en main y en v4.8.0: estados, `thread.items`, `dropped`, ids y la regla del agentHome. Corrió 60 sondas de Pi, y Claude Code dio idéntico en 34 de 34 casos.
    - **Sin prueba real:** en esta máquina no hay archivos de tarea de Pi, así que el formato quedó fijado por fixtures armados desde el código. La prueba en vivo es F9.
    - **Avisos:** F3 a F7.
  - **T3 (`11bdb89`).** Una corrida que el host rechaza por concurrencia no cuenta como cortada: se espera a otra, se cierra con `close_agent` en Codex, se relanza y se avisa que va por tandas. Está fijado por un test con control por mutación.
  - R6 queda lista para salir con la próxima versión. Antes falta F9, que corre el autor.
