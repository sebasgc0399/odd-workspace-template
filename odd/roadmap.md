# Roadmap de odd-ws

Lo que viene después de cada entrega, en orden. Es una cola viva: un ítem que espera algo externo no frena a los demás, y una idea nueva pasa primero por una bandeja antes de entrar a la cola. El detalle de cada ítem vive en su documento de `odd/tasks/`; acá van solo el orden y el estado.

Actualizado: 2026-11-16, después de la `0.7.0`.

## Cómo se mueve

1. **Se toma el primer ítem de «La cola».** Un ítem a medias no se interrumpe por otro.
2. **Si el ítem espera algo** (una respuesta, otro cambio), se revisa su condición al llegar a él. Si no se cumple, pasa a «Esperando» con la fecha del chequeo y se toma el siguiente.
3. **Al empezar cada ítem, se revisan los de «Esperando».** El que se destraba vuelve al frente de la cola.
4. **Las ideas entran a «Ideas»**, sean del autor, de un video o de otro proyecto, con su fuente y lo que se recicla. Se revisan al cerrar cada ítem: se descartan con el porqué, se estudian con un alcance acotado o pasan a la cola. **El lugar en la cola lo decide el autor.**
5. **Un seguimiento** va con el ítem que toque su mismo código, o pasa a la cola si el autor lo pide.
6. **Al cerrar un ítem**, pasa a «Hecho» con su commit. Cuándo sale una versión lo decide el autor.

## La cola

| # | Qué | Detalle | Estado |
|---|---|---|---|
| R1 | Escribir un archivo de capa por la shell, fuera de un writer, se salta el chequeo de capa en cualquier CLI. Dentro de un writer ya lo frena `writer_guard`. Primera capa: bloquear el comando antes de que corra. | [capa-por-shell](tasks/capa-por-shell.md), parte A | en curso |
| R1b | Segunda capa de R1: al final del turno, los archivos de capa que cambiaron pasan por las reglas, sin importar cómo se escribieron. Es a R1 lo que `writer_stop` es a `writer_guard`. | [capa-por-shell](tasks/capa-por-shell.md), parte B | en cola |
| R2 | En Pi, el doctor da un OK falso en cinco casos forzados, y una carpeta `.git` inválida confunde la raíz de la instancia. Además, dos tests de plazo fallan a veces en el CI. | [multi-host](tasks/multi-host.md), X14 a X16 | en cola |
| R3 | Soporte para OpenCode (F3), Gemini CLI (F4) y Copilot CLI (F5), a partir del estudio de align-cli guardado en engram (`odd-ws/estudio-align-cli`). | [multi-host](tasks/multi-host.md), F3 a F5 | en cola |

## Esperando

| Qué | Espera | Último chequeo |
|---|---|---|
| El lector del `ratchet-handoff/v1` de `gentle-contribution-skills` | Que Denver2828 responda sobre `source_id` en el issue #1 de `Denver2828/gentle-contribution-skills` ([graduar-memorias](tasks/graduar-memorias.md), X7) | 2026-11-16: abierto; el último comentario es nuestro, del 2026-11-15 |
| `writer.md` usa «límites» para tres cosas: renombrar `## Tus límites` | El próximo cambio de la plantilla del writer, porque cambiarla sube a v3 y obliga a regenerar los writers de cada instancia ([limites-en-el-cierre](tasks/limites-en-el-cierre.md), F3) | 2026-11-16: ningún ítem de la cola cambia `writer.md` |

## Ideas

Cada idea lleva su fuente (del autor, un video o un proyecto, con su enlace), la idea en una línea, lo que se recicla y su estado: nueva, estudiando, en la cola (con su `R#`) o descartada (con el porqué).

| # | Fecha | Fuente | La idea | Qué se recicla | Estado |
|---|---|---|---|---|---|

Todavía no hay ninguna.

## Seguimientos

Anotados en el documento de cada feature, sin lugar en la cola:

| Documento | Seguimientos |
|---|---|
| [endurecer-guards](tasks/endurecer-guards.md) | Y1 a Y5 e Y7 a Y10 |
| [graduar-memorias](tasks/graduar-memorias.md) | X1 a X6 |
| [multi-host](tasks/multi-host.md) | X1, X3 a X8, X12 y X13 |
| [paquetes-de-reglas](tasks/paquetes-de-reglas.md) | A4 a A8, los avisos del verificador de T1 |
| [uso-en-equipo](tasks/uso-en-equipo.md) | F1 y F2 |
| [capa-por-shell](tasks/capa-por-shell.md) | F1, la caché de bytecode de los hooks |

## Hecho

| Versión | Qué |
|---|---|
| `0.7.0` | Paquetes de reglas importables desde git ([paquetes-de-reglas](tasks/paquetes-de-reglas.md)) y la guía de uso en equipo ([uso-en-equipo](tasks/uso-en-equipo.md)) |
