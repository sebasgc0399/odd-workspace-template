# El costo de revisar (R5)

Objetivo: que una revisión cueste lo que vale. Se mide su costo y su rendimiento, el usuario puede bajar un escalón dejando el motivo, y se avisa cuando el `completo` sale de un archivo sin capa. Sale en la próxima versión, cuando el autor lo decida.
Rama: `feat/costo-de-revisar`, desde `docs/idea-i46` (sobre la `0.9.1`). Entrega: una rama con un commit por unidad; el push a main y la etiqueta, solo con autorización. Se estiman unas 650 líneas, en cuatro commits.
Pruebas: `python3 plugin/scripts/<script>.tests.py`, todas con el bucle de `CONTRIBUTING.md`, y `node --test plugin/shim/*.test.ts`.

## Specs

Cada spec cita al autor tal cual. Las decisiones son las filas del cuadro que el autor aprobó, armado sobre la sección 7 del [estudio](../estudios/costo-de-revisar.md); lo que no sale de una cita va marcado como supuesto.

- **S1. El alcance.** «Vale retomemos los pendientes que sigue?», «Hazme las 5 preguntas en un cuadro con una recomendacion» y «si apruebo». Entran las cinco decisiones del estudio.
- **S2. Medir el costo (I28, pregunta 1).** Fila aprobada: «Además de tokens y minutos, ¿I28 mide el rendimiento de cada hallazgo: en cuántas corridas salió, su severidad y qué pasó con él?», con la recomendación «**Sí**, y que guarde también el ID de la regla que rompe (I46).» El costo es el de la sección 5 del estudio:
  - por corrida: `turnos`, `contexto_inicial`, `contexto_final`, `salida`, `cache_escrita`, `cache_leida`, `inicio`, `fin` y `pausa_mayor`, contados una vez por id de mensaje;
  - por revisión: un `costo.json` con el modo, los motivos del triaje, las corridas y las líneas del diff;
  - el anuncio cita el último costo medido del ticket, o de la instancia si el ticket no tiene; sin ninguno, anuncia corridas como hoy.
- **S3. El rendimiento (pregunta 1).** La misma fila. Una línea fija en `consolidado.md` cuenta los hallazgos por acuerdo (3/3, 2/3 y 1/3, que solo existen en `completo`) y por severidad. Al escribir el recibo, la completa con el destino de cada uno: corregido, derivado o descartado.
- **S4. El ID de la regla (pregunta 1, el requisito de I46).** La misma fila. Cada hallazgo cita el ID de la regla de la matriz que rompe, o dice que no viene de una regla con ID. Supuesto: va en el prompt que arma `revisar` y no en las plantillas de los revisores. Un cambio en la plantilla no llega a los revisores de Claude Code ya generados, y deja en FALTA los de Codex y Pi (L3).
- **S5. Bajar un escalón (O3, pregunta 2).** Fila aprobada: «Un escalón, de `completo` a `rapido`, con el motivo escrito en el recibo. Nunca a `0` si hay código, nunca si el cambio va a un líder y nunca si el triaje vio un riesgo real.» Supuestos:
  - la bajada la pide el usuario, nunca el agente;
  - un rechequeo después de una bajada se mide contra el modo bajado.
- **S6. I34 e I44 (pregunta 3).** Fila aprobada: «**Sí a las dos.** I34 queda cubierta por la bajada con motivo. I44 cambia de enfoque: en vez de marcar los consumidores como «no detectable», se buscan los nombres que el archivo exporta.» I44, que es O5 en el estudio, espera a S8. O2 y O4 no se hacen.
- **S7. El aviso de «sin capa» (pregunta 4).** Fila aprobada: «**Una falla del instrumento.** Se arregla declarando la capa». Sobre la corrección de esa fila (L2), el autor respondió «si». Por ahora entra solo el aviso de `capas-cobertura`:
  - el triaje lo repite cada vez que «sin capa» está entre los motivos;
  - `abrir` lo repite cuando la instancia tiene extensiones versionadas sin capa;
  - el triaje distingue «sin capa» de una positiva real con una clave propia.

  Las 2 corridas llegan cuando se decida O6.
- **S8. Cuándo se decide O6 (pregunta 5).** Fila aprobada: «**10 revisiones `completo` con el mismo modelo, o el próximo ticket entero**, lo que llegue primero.» Con esos datos se deciden O6 y O5; R5 no trae código para eso.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T0 | S1, S6, S8 | Las decisiones en el estudio y el roadmap, I46 anotada, y este documento | inline | hecho | este commit |
| T1 | S2 | El costo por corrida en `rescatar.py`, con su lector en `odd_ws/transcripcion.py`; el `costo.json` opcional, el triaje guardado en la revisión y el anuncio con el último costo | delegada: corre en paralelo con T2, con superficies disjuntas | pendiente | |
| T2 | S7 | La clave de «sin capa» en el triaje, y el aviso de `capas-cobertura` compartido en `odd_ws/`, que repiten el triaje y `abrir` | delegada: corre en paralelo con T1 | pendiente | |
| T3 | S5, S6 | La bajada de un escalón en `recibo.py` y en `revisar`, con el rechequeo medido contra el modo bajado; cierra I34 | inline. Risk: item 2, porque el recibo es la compuerta de la revisión; lleva verificador | pendiente | |
| T4 | S3, S4 | La línea de rendimiento y el ID de la regla, en el prompt y en la consolidación de `revisar` | inline | pendiente | |

## Log

- **L1** (2026-11-18) El pedido del autor, tal cual: «Vale retomemos los pendientes que sigue?». Después, «Hazme las 5 preguntas en un cuadro con una recomendacion» y «si apruebo».
- **L2** (2026-11-18) Una corrección al cuadro: la fila 4 decía «mientras tanto pide 2 corridas en vez de 3», pero el estudio ata las 2 corridas a O6, y O6 espera a S8. Pregunté si seguía el estudio: por ahora solo el aviso, que salta cada vez que «sin capa» está entre los motivos. El autor respondió «si».
- **L3** (2026-11-18) El mapa del explorador, solo lectura:
  - **Hallazgos y consolidación.** Ningún script lee las líneas de hallazgo. `consolidado.md` y las frecuencias 3/3, 2/3 y 1/3 las escribe el agente en prosa (`revisar/SKILL.md:147-159`).
  - **«Sin capa».** La señal `capas` lo marca `positiva`, el mismo nivel que «más de una capa» (`triaje.py:576-580`). Solo se distinguen por el texto.
  - **Plantillas de revisores.** El doctor revisa la versión de las plantillas de los writers, no la de los revisores (`doctor.py:379-417`), y el bootstrap no sobreescribe lo que ya existe. Solo los agentes derivados de Codex y Pi siguen un cambio de la plantilla.
  - **Recibo.** `recibo.py` guarda `modo` por repo y no tiene campo para un motivo. Tampoco puede importar `triaje`, porque `triaje.py:14` importa `recibo`.
  - **Rescate.** `rescatar.py` no lee `usage`, `message.id` ni `timestamp`, y sus tests fijan las claves y las líneas exactas de lo que escribe. Además, lo comparte con `eval-reviewers`, así que el `costo.json` va opcional.
  - **Rechequeo.** La regla del rechequeo (`revisar/SKILL.md:196`) haría de cada rechequeo posterior a una bajada una revisión completa.
- **L4** (2026-11-18) Plan. T1 y T2 son unidades independientes con superficies disjuntas, así que corren en paralelo con dos writers en este worktree; los commits los hace el orquestador. T3 depende de la clave de T2 y del triaje guardado de T1. T4 es texto de `revisar`. Siguiente paso: lanzar T1 y T2.
