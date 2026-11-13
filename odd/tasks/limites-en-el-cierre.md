# El límite en el cierre del writer

Objetivo: sumar al bloque de cierre del writer el eslabón «límite» (qué no demuestra lo que corrió), antes de Pi, para que el adaptador de Pi se construya contra el contrato final. Rama: `feat/limites-en-el-cierre`, desde `main` (`347b83b`). Entrega: un commit por unidad en la rama; push y avance de `main` solo con autorización. Runner: Python sin pytest, `python <x>.tests.py`. Espejo en Engram: `odd/limites-en-el-cierre/tasks`.

## Specs

- **S1.** El bloque de cierre del writer suma `limites:`, con al menos una línea `- <qué no demuestra la verificación>`, en ok, partial y blocked, igual que `verificacion`. writer_stop.py lo valida y bloquea si falta, si está vacío o si solo dice `ninguno` o `ninguna`.
- **S2.** plugin/plantillas/writer.md documenta el campo con la frase «Una suite verde demuestra los casos que ejecuta. Nada más.», con ejemplos de límites: casos sin cubrir, otro OS, integraciones, datos reales.
- **S3.** `odd-ws-plantilla` pasa de 1 a 2 (writer.md:8), con su sha256 fijado (Doc/diseno.md:297). Tiene que andar en Claude Code y en Codex (writer_stop con la bitácora de F1b, y los TOML de codex-agentes).
- **S4.** CHANGELOG y Doc/actualizar.md: después de actualizar, correr /odd-ws:doctor para regenerar los writers. Un writer que quede en la plantilla 1 se come un bloqueo de la compuerta hasta que se regenere (doctor.py:339-343 lo marca «atrasado»). En el CHANGELOG, el crédito del video y de Denver2828.
- **Fuera de alcance (del pedido):** el «Reporte de Auditoría» completo del video, porque duplica presupuesto, reales y verificacion; la regla de «no pinear la versión degradada», porque ninguna compuerta puede verificarla; y Pi.
- **Riesgo:** ítem 3, porque cambia el contrato del bloque que consumen los writers de cada instancia.

## Tasks

| ID | Specs | Qué | Ruta | Estado |
|---|---|---|---|---|
| T1 | S1-S4 | `limites:` en `writer_stop.PLANTILLA` y su validación, la plantilla del writer en v2 con su huella, y la documentación (`writer.md`, `Doc/diseno.md`, `Doc/actualizar.md`, CHANGELOG) | inline: un cambio entendido, sin razón de writer (Writer trigger no aplica) | en curso |
| V | S1-S4 | Un verificador independiente sobre T1 | delegado (ítem 3: el contrato del bloque) | pendiente |

## Log

- **L1 (2026-11-13), el pedido.** Textual:
  > Lo siguiente es el campo `limites:` en el cierre del writer. Rama nueva desde main (347b83b).
  >
  > Contexto: Denver2828 compartió el video «Un test en verde puede estar mal» (RefactorIA Devs), con la cadena afirmación → prueba → resultado → límite. odd-ws ya cubre el resultado: writer_stop.py exige `verificacion:` con `- <comando>: <resultado observado>` (CAMPOS en writer_stop.py:22). Le falta el límite: decir qué NO demuestra lo que corrió. `partial` cubre «quedó sin verificar», pero no «verificado, aunque esto no lo cubre».
  >
  > (Siguen S1 a S4, el fuera de alcance y el riesgo, copiados arriba.) Decisión y evidencia en Engram, proyecto pos: tema odd-ws/limite-en-el-cierre-del-writer.
- **L2 (2026-11-13), lo verificado antes de escribir.** `CAMPOS` está en `writer_stop.py:22`; `odd-ws-plantilla: 1` en `writer.md:8`; la huella por versión, en `HUELLAS_POR_VERSION` de `plantilla_writer.tests.py:22` (la regla, en `Doc/diseno.md:302`); «atrasado» en `doctor.py:339-343` es AVISO con arreglo. El bloque tiene una sola fuente, `writer_stop.PLANTILLA`, que el generador inserta en `{{resultado}}`. Codex lee el último mensaje con el mismo `parsear_resultado`, y sus TOML se derivan del `.md` (`codex-agentes`), así que se regeneran después del writer. La rama se creó primero desde el `main` local, que seguía en `f012ca0` porque la release se empujó directo al remoto; se rehízo desde `347b83b` sin commits perdidos.
- **L3 (2026-11-13), T1 implementado.**
  - **RED:** con la `PLANTILLA` y el parser de `347b83b`, fallaban `sin limites` (no daba error), los límites en los tres estados (`KeyError: 'limites'`) y la plantilla sin `limites:`.
  - **`writer_stop.py`:** `limites` entra en `CAMPOS` y en la `PLANTILLA`; el parser lee `verificacion` y `limites` como listas con el mismo código (también el valor en la misma línea), y `limites` no valida si falta, está vacío, conserva el placeholder o solo dice `ninguno`/`ninguna` (con `` ` ``, `**` o punto). Una línea real junto a `ninguno` vale. Queda en el sidecar en `resultado.limites`.
  - **La plantilla v2:** `writer.md` documenta el campo con la frase de S2 y sus ejemplos, y avisa en *Revisando* que lo que no demuestra lo corrido va a `limites:`. `HUELLAS_POR_VERSION[2]` y los `GOLDEN_DEL_WRITER` de `plantilla_writer.tests.py` y `bootstrap_agentes.tests.py` se actualizaron: fijan la salida por capa y este cambio la mueve a propósito.
  - **Un supuesto latente en un test:** `test_el_toml_lleva_su_version_y_su_huella_en_un_comentario_y_no_como_clave` esperaba la versión del writer en los TOML de los revisores, porque todas las plantillas estaban en la v1. Ahora compara cada TOML con la versión de su propia plantilla (writer v2, revisores v1).
  - **S4 probado de punta a punta:** un cierre sin `limites:` se come el único bloqueo con solo ese error, y el segundo cierre pasa (Claude Code y Codex con su bitácora).
  - **Diferencial del parser contra `347b83b`:** 1604 mensajes (viñetas, valor en línea, varias `verificacion`, campos intercalados, colas con otros encabezados): sacando `limites` y su error, campos y errores dan idénticos.
  - **Suites:** `writer_stop` 53/53, `plantilla_writer` 31/31, `bootstrap_agentes` 47/47, `doctor` 131/131, `codex` 41/41 y `claude_code` 37/37. Enlaces de la doc: 0 rotos.
