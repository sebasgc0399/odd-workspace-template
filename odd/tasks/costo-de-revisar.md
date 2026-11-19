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
- **S9. El costo del orquestador y las corridas en serie (el punto 3 del plan de R6).** El autor: «Si apruebo el plan» ([compat-gentle](compat-gentle.md), L3). `costo.json` suma el costo del orquestador entre el triaje y el rescate, leído del transcript de la sesión principal con el mismo lector de T1. Suma también `contexto_final − contexto_inicial`, que es lo que la revisión le deja al resto de la sesión. Además avisa si las corridas que se lanzaron juntas corrieron en serie, porque sus intervalos no se solapan. Solo en Claude Code, como T1. Supuesto: sin ese tramo del transcript, el campo queda en `null` con un aviso.
- **S8. Cuándo se decide O6 (pregunta 5).** Fila aprobada: «**10 revisiones `completo` con el mismo modelo, o el próximo ticket entero**, lo que llegue primero.» Con esos datos se deciden O6 y O5; R5 no trae código para eso.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T0 | S1, S6, S8 | Las decisiones en el estudio y el roadmap, I46 anotada, y este documento | inline | hecho | este commit |
| T1 | S2 | El costo por corrida en `rescatar.py`, con su lector en `odd_ws/transcripcion.py`; el `costo.json` opcional, el triaje guardado en la revisión y el anuncio con el último costo | delegada: corre en paralelo con T2, con superficies disjuntas | hecho (L5) | `9a03892` |
| T2 | S7 | La clave de «sin capa» en el triaje, y el aviso de `capas-cobertura` compartido en `config_loader`, que repiten el triaje y `abrir` | delegada: corre en paralelo con T1 | hecho (L5) | `e2ffcff` |
| T3 | S5, S6 | La bajada de un escalón en `recibo.py` y en `revisar`, con el rechequeo medido contra el modo bajado; cierra I34 | delegada con T4. Risk: item 2, porque el recibo es la compuerta de la revisión; lleva verificador | hecho; verificador: PASS (L7) | `a7ac88d` |
| T4 | S3, S4 | La línea de rendimiento y el ID de la regla, en el prompt y en la consolidación de `revisar` | delegada con T3, por el contexto del orquestador | hecho (L6) | `2c3689f` |
| T5 | S9 | El costo del orquestador y el aviso de corridas en serie en `costo.json` | delegada, por el contexto del orquestador. Risk: none | hecho (L7) | `f30405a` |
| F1 | S5 | Seguimiento: `recibo.py` confía en el `triaje.json` de la carpeta. Se blinda comparando sus repos y su base con los del recibo (L7) | en `fix/seguimientos-0-10`. Risk: item 2, porque es una compuerta del recibo; lleva verificador | hecho; verificador: PASS (L9) | `357a059` |
| F2 | S5 | Seguimiento, ya estaba antes de T3: un recibo `rapido` sin `--bajada`, sobre un triaje que propuso `completo`, no se detecta (L7) | aparte | anotado | |
| F3 | S9 | Seguimiento: un rescate posterior desde otra sesión pisa con `null` un `orquestador` que estaba bien; además, `costo.json` no guarda el modo que propuso el triaje (L7) | aparte | anotado | |
| F4 | — | Seguimiento cosmético: `triaje.tests.py` perdió un espacio (`PRUEBAS =[`) | con F1 | hecho; verificador: PASS (L9) | `357a059` |
| F5 | S5 | Seguimiento (aviso 1 del verificador de F1): el arreglo que sugiere el rechazo, «guardalo con triaje.py --json con los mismos --repo y la misma base que el recibo», lleva otra vez al mismo rechazo en dos flujos documentados: un rechequeo con un repo heredado entero, cuyo triaje tiene que traer todos los repos de la unidad, y un recibo sin `#BASE` después de una unidad sellada, donde lo que se corrige es la base del recibo. Los dos fallan cerrado (L9) | aparte | anotado | |
| F6 | S5 | Seguimiento (aviso 2): el cruce compara repos y base, no archivos, así que un triaje guardado antes de sumar un archivo al mismo diff sigue habilitando la bajada. Ya pasaba antes de F1; se cerraría exigiendo que los `--archivo` de cada repo estén en sus `repos[].archivos` (L9) | aparte | anotado | |

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
- **L5** (2026-11-18) T1 y T2 hechos, cada uno con RED antes de GREEN, la suite completa en verde y un diferencial contra `f6afa50`. El orquestador revisó cada diff contra sus superficies, volvió a correr `rescatar.tests.py` (41/41) y vio que `rescatar.py -h` sigue andando.
  - **T1 (`9a03892`).** El costo de cada corrida va en `costo` de su `.lecturas.json`; con un transcript viejo, sin `usage`, queda en `null`. `--costo` escribe `corridas/costo.json` solo con el destino de una revisión, así que `eval-reviewers` no cambia. `--ultimo-costo` busca en el ticket y después en la instancia. El diferencial dio igual salvo la línea `usage:` de argparse, que ahora muestra las dos formas.
    - Queda abierto: `costo.json` no guarda el modo que propuso el triaje, que importa después de una bajada (T3); el anuncio cita tokens y no minutos; `CARPETA_RE` y `MODOS` están copiados de `recibo.py`, con un test que los mantiene iguales.
  - **T2 (`e2ffcff`).** La clave `sin_capa` vale `null` o `{archivos, unico_motivo_de_capas, aviso}`. Una positiva real es una señal `positiva` que no sea la de `capas` con `unico_motivo_de_capas`. La cuenta compartida quedó en `config_loader` y no en `odd_ws/`, por el ciclo de importación `config_loader` → `odd_ws.hosts` → `odd_ws.comun` → `odd_ws.capas`. La salida del doctor es idéntica byte a byte.
  - Risk: none en los dos. Suman una clave opcional y opciones nuevas, que pidió la spec, y la salida existente quedó fijada por tests y por el diferencial.
- **L6** (2026-11-18) T4 y T3 hechos por un writer, con RED antes de GREEN, las 46 suites en verde y un diferencial contra `8a4b44d`: los 8 recibos dieron idénticos byte a byte, y lo único que cambió fue la línea `usage:` de argparse.
  - **T4 (`2c3689f`).**
    - El prompt pide `[SEVERIDAD] <ID de la regla | sin ID> ruta:línea — …`, sin un ID literal, y las plantillas de los revisores no cambian.
    - `consolidado.md` abre con `Rendimiento: <n> hallazgos · acuerdo 3/3 <a>, 2/3 <b>, 1/3 <c> · CRITICAL <x>, WARNING <y>, SUGGESTION <z> · destino: pendiente`, y el destino se completa al escribir el recibo.
  - **T3 (`a7ac88d`).**
    - La bajada se pide con `--modo rapido --bajada "<motivo>" --va-a-lider no`, y `recibo.py` la valida contra `entrada/triaje.json`.
    - El recibo guarda `"bajada": {"de": "completo", "a": "rapido", "motivo": …, "va_a_lider": false}`.
    - El rechequeo hereda la bajada mientras siga en `rapido`, y una positiva real nueva lo convierte en una revisión nueva.
    - **Diseño de «va a un líder».** Ningún script puede saberlo, así que `--bajada` exige `--va-a-lider` explícito y rechaza `si`.
    - **Queda abierto:**
      - un recibo `rapido` sin `--bajada`, cuando el triaje propuso `completo`, no se detecta, porque sin la opción los recibos no cambian;
      - `recibo.py` confía en el `triaje.json` de la carpeta y no comprueba que sea de este diff.
  - Con T3 se cierra I34. Siguiente paso: el verificador de T3 y, en paralelo, T5.
- **L7** (2026-11-18) Las verificaciones de T3 y T5.
  - **El verificador independiente de T3: PASS, sin bloqueantes.** Probó lo siguiente, siempre sobre una copia aparte:
    - 8 escenarios con triajes reales de `triaje.py --json`. La bajada se permite en tres: un archivo sin capa, un archivo sin capa más una capa, y `consumidores` inválida. Se rechaza en los otros cinco: dos capas, dos capas más un archivo sin capa, `dinero`, `efecto`, y `efecto` más un archivo sin capa.
    - 40 casos borde, con los hashes de la instancia sin cambios después de cada rechazo.
    - El sello y el `--check` de un recibo bajado, y 24 chequeos de rechequeo.
    - Un diferencial de 17 secuencias contra `2c3689f`: los recibos dieron idénticos, salvo la línea `usage:`.

    Los avisos se convirtieron en F1, F2 y F4, y el verificador confirmó que F2 ya pasaba antes de T3. Por su lado, el orquestador volvió a correr `recibo.tests.py` y dio 84/84.
  - **T5 (`f30405a`).** `costo.json` suma `orquestador`, que son los campos de `costo()` más `contexto_dejado`, y `en_serie`.
    - **El tramo** sale del transcript principal, `<proyecto>/<sesión>.jsonl`. Va desde el último `triaje.py` anterior al primer lanzamiento de las corridas hasta el `recibo.py --write` de la ronda, o hasta el final del archivo.
    - **El anuncio** de `--ultimo-costo` solo agrega «las corridas corrieron en serie» cuando es cierto.
    - **Prueba en vivo.** Corrió sobre sesiones reales, en solo lectura: en una revisión, el orquestador hizo 29 turnos y le dejó 64 263 tokens de contexto al resto de la sesión.
    - **Diferencial contra `a7ac88d`.** Las claves anteriores y los demás archivos quedaron idénticos.
    - **Verificación del orquestador.** Volvió a correr `rescatar.tests.py` y dio 48/48.
    - **Riesgo.** El writer marcó el ítem 3, pero solo suma claves opcionales, así que el orquestador lo clasificó `Risk: none`.
  - R5 queda lista, de T0 a T5, para salir con la próxima versión. Las decisiones de O6 y O5 (S8) esperan las revisiones medidas.
- **L8** (2026-11-19) F1 y F4, en `fix/seguimientos-0-10`.
  - **F1.** Antes de leer el triaje para una bajada, o para heredarla en un rechequeo, `recibo.py` comprueba que sus `repos` sean los del recibo, con la misma `base` cada uno. Si falta un repo, sobra uno o cambia una base, sale con 2 sin escribir nada y nombra cada diferencia. Lo fijan dos tests nuevos, con cinco casos de bajada y tres de rechequeo; los tests de bajada que ya existían guardan ahora el triaje con sus repos.
  - **F4.** Vuelve el espacio de `PRUEBAS = [`.
  - F2 y F3 siguen anotados.
- **L9** (2026-11-19) El verificador independiente de F1 y F4 (`357a059` contra `0b2ff56`): PASS, sin bloqueantes.
  - **Suites.** Desde una copia de `357a059`, `recibo.tests.py` dio 87/87 y `triaje.tests.py` 95/95. Los dos tests nuevos fallan contra el `recibo.py` de la base, así que fijan el defecto.
  - **El flujo real.** 23 casos con `triaje.py --json` y el recibo con los mismos repos dan idéntico en la base y en el candidato. Incluyen dos repos en otro orden, la base como sha corto o `origin/main`, y la misma carpeta escrita de varias maneras: mayúsculas, `\` o `/`, barra final, junction, ruta relativa y nombre corto 8.3.
  - **Los desajustes.** Los 10 casos salen con 2, sin recibo y con el ticket idéntico byte a byte, y el mensaje nombra cada diferencia. La base escribía el recibo.
  - **Lo que no cambia.** Sin bajada pasada ni heredada, 44 casos de `--write`, `--check` y `--sellar` dan idénticos.
  - **Los `repos` malformados.** Las 24 variantes fallan cerrado con 2, sin error interno.
  - **Avisos.** El 1 y el 2 quedan como F5 y F6. El 3 (un repo repetido gana la última entrada) y el 4 (la grafía UNC de una carpeta local se rechaza, cerrado) son entrada fuera de dominio. El 5 dice que, con dos errores a la vez, el mensaje que sale primero cambió.
