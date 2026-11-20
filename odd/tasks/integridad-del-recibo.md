# La integridad del recibo (issue #1 y auditoría)

Objetivo: que el recibo registre solo lo que de verdad se revisó, con el modo que el triaje del diff actual respalda. Parte del issue #1 de Denver y de una auditoría de dos lentes, una sobre cómo se ata el triaje al diff y otra sobre quién consume el recibo. Sale en la próxima versión, cuando el autor lo decida.
Rama: `fix/integridad-del-recibo` (T1, en `D:/Project/odd-ws-wt/t`) y `fix/recibo-garantias` (T2, en `D:/Project/odd-ws-wt/t2`), las dos desde main (`0.10.1`, `a94b46a`); T2 se mergea en la primera. Entrega: un commit por unidad; el push a main y la etiqueta, solo con autorización. Se estiman unas 900 líneas, en dos unidades y un cierre.
Pruebas: `python3 plugin/scripts/<script>.tests.py` (en Windows, `python`), todas con el bucle de `CONTRIBUTING.md`, y `node --test plugin/shim/*.test.ts`.

## Specs

Los hallazgos de la auditoría entran por L1 («hacemos varios arreglos y/o mejoras»). Cada spec cita su origen: el issue, el hallazgo del auditor del vínculo (A#) o el del auditor de los consumidores (B#).

- **S1** (issue #1, y F6 de `costo-de-revisar`). El resultado esperado del issue, tal cual: «Detectar que el contenido cambio y pedir un triaje nuevo antes de escribir el recibo. Al repetir el triaje sobre esta edicion, la señal de efecto exige mantener la revision completa.» Y su prueba: «Para el test mantendria fijos el repo, la base y la lista de archivos. Antes de la segunda edicion, la bajada deberia aceptarse. Despues, el mismo triaje deberia rechazarse sin escribir un recibo nuevo.» El triaje guarda la huella de su diff por repo y por archivo, calculada con la misma función que el recibo (`recibo.calcular`); al autorizar o heredar una bajada, el recibo compara la lista de archivos y las huellas, y si difieren rechaza sin escribir. Un triaje sin huella se rechaza igual, pidiendo correrlo de nuevo.
- **S2** (A5, B6). El triaje guardado se valida entero: trae las seis señales de `SENALES`, su modo es el que el triaje sacaría de esas señales y `sin_capa.unico_motivo_de_capas` se recalcula desde los archivos en lugar de creerle al JSON. La skill `revisar` dice que `triaje.json` y `recibo.json` no se editan a mano.
- **S3** (A2, B5, F2 de `costo-de-revisar`). El modo no baja sin `--bajada`. Con un triaje guardado, `--modo` es igual o más alto que el que propuso el triaje, salvo con `--bajada` (un escalón, de `completo` a `rapido`). En un rechequeo, `--modo` es igual o más alto que el del recibo previo, o que el `a` de su bajada si la hereda; con una fecha posterior también. Un modo más bajo es error de uso y no escribe.
- **S4** (A3). Un archivo del taller triado por `--repo <instancia>` conserva su contraparte de la línea base: salen las mismas señales que con `--taller`.
- **S5** (A1, B1, B2). `--write` sobre un recibo que ya existe: si las huellas del diff actual difieren de las guardadas, rechaza sin escribir y manda al rechequeo con `--previo`; si son iguales, cambia el estado y conserva `sellado` y lo demás.
- **S6** (B3). Antes del commit, `--check` aplica el criterio de `--sellar` a lo que entraría al commit: falla si el índice trae otra versión de un archivo revisado, o si hay archivos en el índice fuera del recibo con las mismas exclusiones que `fuera_de_lo_revisado`; los cambios del working tree fuera del recibo que no están en el índice salen como aviso. El mensaje de `--sellar` cuando hay cambios fuera de lo revisado propone el rechequeo con `--previo`.
- **S7** (A8, B7). `--check` imprime el estado, el modo y la bajada del recibo, y `--sellar` se niega con un recibo `pendiente`.
- **S8** (B4, F5 de `costo-de-revisar`). `--write --ticket` elige la base igual que el triaje (la explícita, el sello vivo más nuevo del ticket, el merge-base), con la misma función.
- **S9** (A4). Las rutas van a git como literales (la opción global `--literal-pathspecs` en la configuración fija, y sin `GIT_GLOB_PATHSPECS`, `GIT_ICASE_PATHSPECS` ni `GIT_NOGLOB_PATHSPECS` en el entorno), así que un nombre con corchetes no empareja otros archivos. Corregida en L4: `core.literalPathspecs` no es una clave de git.
- **S10** (A6). Una ruta relativa con otras mayúsculas en Windows se canoniza a la que tiene el repo antes de hashearla.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T1 | S1, S2, S3, S4 | El triaje que respalda el modo: la huella en `triaje.py`, la validación entera y el modo en `recibo.py`, la contraparte del taller por `--repo` | delegada en paralelo con T2, en su worktree. Risk: item 2, porque el recibo es la compuerta de la revisión; lleva verificador | escrita y en verde, sin commitear en `t` (L4) | |
| T2 | S5, S6, S7, S8, S9, S10 | Lo que el recibo garantiza: la reescritura, `--check`, `--sellar`, la base con el sello, las rutas literales y las mayúsculas | delegada en paralelo con T1, en su worktree. Risk: item 2, la misma compuerta; lleva verificador | escrita y en verde, sin commitear en `t2` (L4) | |
| T3 | todas | El merge de T2 en la rama, la suite completa, el verificador independiente de la feature, y F2, F5 y F6 cerrados en `costo-de-revisar` | inline | pendiente | |
| F1 | — | Anotado (A7, inferido): `--clon` con un subconjunto, `--raiz` u un `origin_head` viejo mueven la señal de consumidores, y el recibo no lo ata | aparte | anotado | |
| F2 | — | Anotado (B8, inferido): la bajada heredada arrastra `va_a_lider: false`. No se cambia: la regla de mostrar a un líder se aplica al mostrar, y exigirlo en cada rechequeo agrega fricción sin evidencia de un caso real | aparte | anotado | |
| F3 | S1, S3 | Hueco que reportó T1: sin `--bajada`, el triaje guardado pone el piso del modo pero no se ata al diff, así que un triaje viejo en `rapido` habilita `--modo rapido` después de una edición que suma riesgo. Se cerraría comparando la huella también al leer el piso | a decidir en T3 | abierto | |
| F4 | S1 | Decisión abierta que reportó T1: la lista de archivos se compara por igualdad estricta, así que una revisión que deja afuera archivos del ambiente local nunca puede bajar. Falla hacia lo seguro (queda en `completo`); aceptar un subconjunto puede tapar un riesgo | preguntar al autor | abierto | |

## Log

- **L1** (2026-11-20) El pedido del autor, tal cual, después del análisis del issue #1: «Si, arreglalo pero aprovechemos esta issues, para hacer una auditoria al respecto, sobre este tema, a ver si encontramos mas cosas y hacemos varios arreglos y/o mejoras».
- **L2** (2026-11-20) Auditoría de solo lectura con dos lentes, en paralelo. El auditor del vínculo reportó 8 hallazgos (A1 a A8) y el de los consumidores 8 (B1 a B8); se solapan en la reescritura del recibo (A1, B1, B2), el modo sin bajada (A2, B5), la validación del triaje (A5, B6) y `--sellar` con `pendiente` (A8, B7). Spot check del padre: `resolver_base` (`recibo.py:91-101`) no mira los sellos, como dice B4. Cierran F2, F5 y F6 de `costo-de-revisar`. Scratch de los auditores, a borrar a mano: `%TEMP%\tmp.gDSOQvERGb` y `%TEMP%\tmp.BZ4wBw9nSe`.
- **L3** (2026-11-20) Diseño: se sigue la corrección del issue (la huella en el triaje) y no volver a correr el triaje dentro del recibo. La huella detecta el triaje viejo con un solo paso más para el usuario y no acopla el tiempo del triaje a cada `--write`. `triaje.py` ya importa `recibo`, así que la huella sale de `recibo.calcular` sin un módulo nuevo.
- **L4** (2026-11-20, 09:25) Los dos writers terminaron, y sus cambios quedaron sin commitear en sus worktrees. La sesión se cortó a las 9:30 por pedido del autor.
  - **T1** (`t`, +495/−86). Cubre S1 a S4.
    - Lo compartido entre los dos scripts vive en `recibo.py`: `SENALES`, `es_doc`, `modo_de_las_senales` y `sin_capa_es_el_unico_motivo`. Para eso, `recibo.py` ahora importa `config_loader`.
    - El escenario exacto del issue sale con 2 y no escribe.
    - Suites: `recibo` 95/95, `triaje` 98/98, `doctor` 203/203 y `rescatar` 61/61.
    - Chequeo diferencial: 72 de 73 salidas iguales. La única distinta es la ayuda, que se cambió a propósito.
    - Abrió F3 y F4.
  - **T2** (`t2`, +638/−116). Cubre S5 a S10.
    - S9 se corrigió: queda `--literal-pathspecs`.
    - La reescritura con el mismo diff conserva lo que la llamada no nombra y hereda la base del recibo.
    - Siete tests existentes ahora escriben con `--estado limpio`, por S7.
    - Suites: `recibo` 100/100 (el padre lo volvió a correr: 100/100), `triaje` 96/96 y `doctor` 203/203.
    - Chequeo diferencial: 12 iguales y 3 con las diferencias pedidas.
  - **Costuras para el merge de T3:**
    - Una línea de `armar_rechequeo` (T2, `elegir_base`) junto al piso del modo de T1.
    - Una línea de `recolectar_repo` (T2, `recibo.elegir_base`) junto a la contraparte del taller de T1.
    - Los tests de bajada que tocaron las dos unidades: T2 sumó un `unlink` y `--estado limpio`, y T1 cambió `guardar_triaje`.
    - Las secciones 3, 8 y 9 de la skill `revisar`, y `Doc/uso.md` y `Doc/diseno.md`.
  - **Scratch, a borrar a mano:** `%TEMP%\tmp.RQjplZBWDk` (T1) y `%TEMP%\tmp.p5jFDIJ7xQ` (T2). También dos logs sueltos de T2, que el guard no dejó borrar: `C:\Program Files\Git\triaje-1.log` y `C:\Program Files\Git\doctor-1.log`.
  - **Próximo paso (T3):**
    1. Commitear T1 en `t` y T2 en `t2`.
    2. Mergear `fix/recibo-garantias` en `fix/integridad-del-recibo` y resolver las costuras.
    3. Decidir F3 y preguntar F4.
    4. Correr la suite completa.
    5. Pasar el verificador independiente de toda la feature.
    6. Cerrar F2, F5 y F6 en `costo-de-revisar`.
