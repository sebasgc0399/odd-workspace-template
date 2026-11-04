# <id> — <título corto>

> **Contexto y metodología:** ver `../../CLAUDE.md` (la raíz de la instancia).
> Si abriste este ticket suelto y la raíz no cargó, léela desde esa ruta.
> Un ticket se abre con `/odd-ws:abrir`.

- **Estado:** nuevo | en progreso | en revisión | listo | standby | sin desarrollo
- **Conocimiento:** pendiente | graduado (YYYY-MM-DD) | descartado (YYYY-MM-DD, motivo)
- **Nota de estado:** <opcional: qué falta o quién lo bloquea, en una línea>

> **Los dos campos miden relojes distintos, a propósito.** `Estado` es la ENTREGA del ticket.
> `Conocimiento` es si lo aprendido acá ya subió a los docs del proyecto o a la raíz. Un ticket puede
> estar `graduado` sin haberse entregado: el conocimiento gradúa cuando está **verificado y es
> general**, no cuando el código sale. `descartado` es el tercer desenlace, para cuando el ciclo se
> cierra SIN cosechar nada (un ticket reasignado, por ejemplo). `graduado` y `descartado` exigen la
> sección «Candidatos a graduar» vacía: declararlo y dejar la lista llena es la misma fuga, con permiso.

## Objetivo

<Una frase: qué resuelve este ticket y para quién.>

## Criterios de aceptación

- [ ] <criterio 1>
- [ ] <criterio 2>

## Alcance y no-goals

- **Incluye:** <lo que sí entra>
- **NO incluye (no-goals):** <lo que explícitamente queda fuera; si lo justifica un conteo («N consumidores»), con el comando y su salida>

## Contexto técnico

- Repos y capas afectados: <…>
- Worktree y rama: <ruta del worktree y rama, o «árbol principal»>
- Dependencias o bloqueos: <…>
- Paso 0 de diseño: <hermano vigente y consumidor de cada dato nuevo, antes de escribir código>

## Decisiones

- <fecha> — <decisión tomada> — <por qué>

## Gotchas

- <edge case o cosa no obvia descubierta durante el trabajo>

## Bitácora

- <fecha> — <qué se hizo, qué sigue>

## Candidatos a graduar

Conocimiento de este ticket que probablemente es GENERAL (aplica a todo el proyecto, no solo a este
ticket) y debería subir a los docs del proyecto o a la raíz. Anótalo apenas aparece: el cierre lo
gradúa, y un ticket hermano lo ve antes. Si algo es claramente general y urgente, se puede graduar
a mitad de camino sin esperar el cierre.

- <hallazgo general> → <doc destino o la raíz>

## Cierre

Al terminar el ticket, `/odd-ws:cerrar`: triaje de los aprendizajes, graduación de los candidatos a la
capa durable (docs del proyecto o raíz) y commit de cierre. Después, `Estado` y `Conocimiento` se
actualizan.
