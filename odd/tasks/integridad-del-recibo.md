# La integridad del recibo (issue #1 y auditoría)

Objetivo: que el recibo registre solo lo que de verdad se revisó, con el modo que el triaje del diff actual respalda. Parte del issue #1 de Denver y de una auditoría de dos lentes, una sobre cómo se ata el triaje al diff y otra sobre quién consume el recibo. Sale en la próxima versión, cuando el autor lo decida.
Rama: `fix/integridad-del-recibo` (T1, en `D:/Project/odd-ws-wt/t`) y `fix/recibo-garantias` (T2, en `D:/Project/odd-ws-wt/t2`), las dos desde main (`0.10.1`, `a94b46a`); T2 se mergea en la primera. Entrega: un commit por unidad; el push a main y la etiqueta, solo con autorización. Se estiman unas 900 líneas, en dos unidades y un cierre.
Pruebas: `python3 plugin/scripts/<script>.tests.py` (en Windows, `python`), todas con el bucle de `CONTRIBUTING.md`, y `node --test plugin/shim/*.test.ts`.

## Specs

Los hallazgos de la auditoría entran por L1 («hacemos varios arreglos y/o mejoras»). Cada spec cita su origen: el issue, el hallazgo del auditor del vínculo (A#) o el del auditor de los consumidores (B#).

- **S1** (issue #1, y F6 de `costo-de-revisar`). El resultado esperado del issue, tal cual: «Detectar que el contenido cambio y pedir un triaje nuevo antes de escribir el recibo. Al repetir el triaje sobre esta edicion, la señal de efecto exige mantener la revision completa.» Y su prueba: «Para el test mantendria fijos el repo, la base y la lista de archivos. Antes de la segunda edicion, la bajada deberia aceptarse. Despues, el mismo triaje deberia rechazarse sin escribir un recibo nuevo.» El triaje guarda la huella de su diff por repo y por archivo, calculada con la misma función que el recibo (`recibo.calcular`); al autorizar o heredar una bajada, y al leer el piso del modo de S3, el recibo exige que cada archivo que cubre esté en el triaje con la misma huella y la misma base; si no, rechaza sin escribir. El triaje puede haber visto más archivos o repos que el recibo, por ejemplo los del ambiente local que no se commitean (F4, L5): esos salen en un aviso y no rechazan. Un triaje sin huella se rechaza igual, pidiendo correrlo de nuevo.
- **S2** (A5, B6). El triaje guardado se valida entero: trae las seis señales de `SENALES`, su modo es el que el triaje sacaría de esas señales y `sin_capa.unico_motivo_de_capas` se recalcula desde los archivos en lugar de creerle al JSON. La skill `revisar` dice que `triaje.json` y `recibo.json` no se editan a mano.
- **S3** (A2, B5, F2 de `costo-de-revisar`). El modo no baja sin `--bajada`. Con un triaje guardado, que se lee atado al diff como en S1 (F3, L5), `--modo` es igual o más alto que el que propuso el triaje, salvo con `--bajada` (un escalón, de `completo` a `rapido`). En un rechequeo, `--modo` es igual o más alto que el del recibo previo, o que el `a` de su bajada si la hereda; con una fecha posterior también. Un modo más bajo es error de uso y no escribe.
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
| T1 | S1, S2, S3, S4 | El triaje que respalda el modo: la huella en `triaje.py`, la validación entera y el modo en `recibo.py`, la contraparte del taller por `--repo` | delegada en paralelo con T2, en su worktree. Risk: item 2, porque el recibo es la compuerta de la revisión; lleva verificador | hecha (L4, L5) | `46884df` |
| T2 | S5, S6, S7, S8, S9, S10 | Lo que el recibo garantiza: la reescritura, `--check`, `--sellar`, la base con el sello, las rutas literales y las mayúsculas | delegada en paralelo con T1, en su worktree. Risk: item 2, la misma compuerta; lleva verificador | hecha (L4, L5) | `76f710f` |
| T3 | todas | El merge de T2 en la rama, F3 y F4, la suite completa, el verificador independiente de la feature, y F2, F5 y F6 cerrados en `costo-de-revisar` | inline. Risk: item 2, la misma compuerta | merge, F3, F4 y F5 commiteados (L6); el verificador encontró B1 a B3, corregidos en un lote (L7); falta su rechequeo | `0d01eac`, `db0cea8` |
| F1 | — | Anotado (A7, inferido): `--clon` con un subconjunto, `--raiz` u un `origin_head` viejo mueven la señal de consumidores, y el recibo no lo ata | aparte | anotado | |
| F2 | — | Anotado (B8, inferido): la bajada heredada arrastra `va_a_lider: false`. No se cambia: la regla de mostrar a un líder se aplica al mostrar, y exigirlo en cada rechequeo agrega fricción sin evidencia de un caso real | aparte | anotado | |
| F3 | S1, S3 | Hueco que reportó T1: sin `--bajada`, el triaje guardado pone el piso del modo pero no se ata al diff, así que un triaje viejo en `rapido` habilita `--modo rapido` después de una edición que suma riesgo. Se cierra comparando la huella también al leer el piso (L5) | en T3, inline | decidido | |
| F4 | S1 | Decisión que reportó T1: la lista de archivos se comparaba por igualdad estricta, así que una revisión que deja afuera archivos del ambiente local nunca podía bajar. El autor aprobó aceptar un recibo que cubre parte de los archivos del triaje (L5) | en T3, inline | hecho | `db0cea8` |
| F5 | S3 | Seguimiento (aviso 1 del verificador, L7): el piso de S3 solo existe si el triaje está en la carpeta del modo elegido. Un `--modo` más bajo escribe en otra carpeta, sin `entrada/triaje.json`, y ahí no hay piso. La skill guarda el triaje en la carpeta del modo de la revisión, así que pasa fuera de su flujo; la base no tenía ningún piso | aparte | anotado | |
| F6 | — | Seguimiento (aviso 2): el triaje en texto también calcula la huella, unos 3 git más por archivo, aunque el texto no la muestra | aparte | anotado | |
| F7 | S6 | Seguimiento (aviso 4): el aviso de `--check` nombra los generados (`__pycache__/*.pyc`) que el triaje deja fuera de la unidad | aparte | anotado | |

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
- **L5** (2026-11-20) F3 y F4 decididos. T1 y T2 se commitean en sus ramas.
  - **F3**, decidido por el padre porque solo hay una dirección segura: cuando hay triaje guardado, el piso del modo se lee con `leer_triaje_del_diff`, igual que la bajada. Hoy `_no_baja_del_triaje` (`recibo.py:417-424` de T1) lo lee sin atarlo al diff.
  - **F4**, el autor, tal cual: «Vale me parece una buena solucion igualmente analiza bien si esa es la mejor solucion». Se acepta un recibo cuyos archivos son parte de los del triaje. Se comparan la base y la huella de cada archivo del recibo, y no la huella total del repo. Un archivo o un repo del recibo que el triaje no vio se sigue rechazando.
  - **Por qué es seguro:** las seis señales solo pueden subir con más archivos (`modo_de_las_senales`, `sin_capa_es_el_unico_motivo`), así que un triaje que vio más nunca es más permisivo. Lo no revisado no entra al commit, porque `--check` (S6) rechaza un archivo del índice que está fuera del recibo.
  - **Alternativas descartadas:**
    - Que el triaje reciba `--archivo`: el usuario elegiría lo que ve el triaje.
    - Una lista de exclusiones en la config: una clave nueva, para cubrir solo lo anotado.
    - Mantener la igualdad estricta: obliga a guardar el ambiente local con stash, o a pagar `completo`.
    - Correr el triaje dentro del recibo: ya descartado en L3.
  - **Dos agregados del padre:**
    - Un aviso con los archivos y los repos del triaje que el recibo no cubre. Conserva el «te olvidaste un archivo» que daba la igualdad estricta.
    - Un repo que está en el triaje y falta en el recibo se trata como sus archivos: sale en el aviso.
  - **Dependencia:** F4 es condición de F3. Con la igualdad estricta, atar el piso al diff haría fallar todo `--write` con el ambiente local sucio.
- **L6** (2026-11-20) T3, el merge y los arreglos de F3, F4 y F5.
  - **Commits:** T1 quedó en `46884df` y T2 en `76f710f`, cada uno con el pre-commit completo en verde.
  - **El merge** de `fix/recibo-garantias` tuvo dos conflictos y los dos eran de suma. En `Doc/diseno.md` va la «Recolección» de T1 con la «base sellada» de T2. En el test `check_y_sellar…bajado` va el `guardar_triaje` de T1 con el `--estado limpio` de T2. Las costuras de `armar_rechequeo` y `recolectar_repo` se mezclaron solas y quedaron bien. Sobre el merge, `recibo` dio 108/108 y `triaje` 99/99.
  - **F4:**
    - `_huella_distinta` ya no rechaza los archivos del triaje que el recibo no trae, y `leer_triaje_del_diff` tampoco rechaza los repos del triaje que el recibo no trae.
    - Los dos salen en un aviso por stderr, impreso después de validar el triaje.
    - La huella total del repo se compara solo cuando el triaje y el recibo traen los mismos archivos.
  - **F3:** `_no_baja_del_triaje` lee el triaje con `leer_triaje_del_diff`. Con `--modo completo` solo lo valida, sin atarlo, porque no hay piso que violar, y atarlo pediría correr el triaje después de cada corrección. Es decisión del padre.
  - **F5:** el rechazo nombra cada repo del recibo con su base (`--repo <ruta>#<base>`), los heredados también.
  - **Tests:**
    - Rojo observado antes del cambio en los dos de F4 y en el de F3. El de F5 se escribió junto con el cambio, y su rojo se comprobó después contra el `recibo.py` de HEAD, en una copia aparte.
    - Salen dos casos que fijaban la igualdad estricta: «el triaje trae un archivo que el recibo no», en S1, y «el triaje trae un repo de mas».
    - Otros dos tests fijaban el hueco de F3 y se ajustan:
      - En S2, el caso «rapido sin archivos» pasa a `--modo completo`, que valida sin atar al diff.
      - En «sin bajada… mismos bytes», los casos «sin huella» y «propone 0 con solo `c.txt`» pasan a los que no escriben, y «con huella» sigue escribiendo los mismos bytes.
    - Con todo, `recibo` da 112/112. El primer intento de commitear el merge falló porque el pre-commit corre sobre el working tree y encontró esos dos tests. El merge entró después como `0d01eac`, solo con su resolución.
    - Se actualizan la skill `revisar` (paso 8), `Doc/uso.md` y `Doc/diseno.md`.
  - **`costo-de-revisar`:** F2, F5 y F6 cerrados, con su L10.
- **L7** (2026-11-20) El verificador independiente de toda la feature (`a94b46a..db0cea8`), y un lote de corrección.
  - **Lo que pasó:** S1 a S10, F3, F4 y F5 dieron PASS, con el flujo real (`triaje.py --json` y después `recibo.py --write`) en S1, F3, F4, F5 y S8. El chequeo diferencial fueron 24 casos, todos iguales salvo lo pedido, y todo rechazo dejó el ticket idéntico byte a byte. Las suites, sobre su copia: `recibo` 112/112, `triaje` 99/99 y `doctor` 203/203.
  - **Bloqueantes.** Los dos los causa la rama y los dos fallan cerrado:
    - **B1:** `triaje.py` salía con 2 con un submódulo borrado. Calculaba la huella de todos los cambios sin `permitir_ausentes`, y el commit del gitlink no está en los objetos del repo.
    - **B2:** un repo anidado sin trackear, o un submódulo con el puntero cambiado, aparece en `archivos` pero queda fuera de la huella. Por eso `sorted(huella) != vistos` rechazaba la bajada para siempre.
  - **El lote:**
    - En el triaje, `calcular(…, permitir_ausentes=True)`: el gitlink borrado entra como ausente.
    - En `_huella_distinta`, la huella tiene que cubrir solo archivos que el triaje lista, y no toda la lista. No se pierde seguridad: cada archivo del recibo sigue necesitando su huella igual, y una carpeta no puede estar en un recibo porque `diff_de_ruta` la rechaza.
  - **B3, del aviso 6.** Reescribir un recibo bajado sin repetir `--bajada` salía con 2 por el piso de S3. Contradecía S5 («conserva `sellado` y lo demás») y el paso 8 de la skill («lo que no nombra queda»). Ahora la reescritura hereda la bajada guardada como un rechequeo: vale mientras el triaje sea de este diff y no vea un riesgo real.
  - **Tests de regresión:** el submódulo borrado y el repo anidado, de punta a punta con el triaje real en `triaje.tests.py`, y la reescritura de un recibo bajado en `recibo.tests.py`. Rojo observado en los tres antes del arreglo. Después: `recibo` 112/112 y `triaje` 101/101; la de la reescritura se sumó después, en verde.
  - **Avisos sin cambio:**
    - El 3 queda como está: el aviso de F4 antes de un rechazo por riesgo real dice de qué archivo puede venir ese riesgo.
    - El 5 es por diseño: los JSON no se editan a mano, y la huella se compara archivo por archivo.
    - El 7 lo cubren ahora los tests de punta a punta.
    - Los avisos 1, 2 y 4 quedan como F5, F6 y F7.
  - **Scratch del verificador, a borrar a mano:** `%TEMP%\tmp.OgkSwA9P1q`.
