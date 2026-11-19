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
| T1 | S4 | El chequeo de marcadores en `.githooks/pre-commit`, con su helper y sus tests | delegada: no comparte archivos con R5. Risk: item 5, porque es la compuerta de commit del repo; lleva verificador | pendiente | |
| T2 | S2, S5 | `rescatar.py --host pi`, su helper en `hosts/pi.py`, los pasos 4 y 6 de `revisar` y los docs | delegada, después de T3 de R5. Risk: item 6, porque el archivo de tarea es interno de Gentle; lleva una prueba real en Pi | pendiente | |
| T3 | S3 | La regla del límite de concurrencia en `revisar` | con T2: los mismos pasos de la skill | pendiente | |

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
