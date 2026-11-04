# {{nombre}} — guía de trabajo

Raíz de la instancia de trabajo de **{{nombre}}**. El motor (hooks, writers, revisión, doctor) lo trae el
plugin `odd-ws`; aquí viven la metodología y las reglas propias del proyecto. **La raíz orquesta; el
trabajo real de cada ticket vive en su carpeta bajo `{{tickets}}/`.**

Este archivo es la memoria de trabajo: se carga siempre, así que se mantiene corto (menos de 200 líneas,
lo mide `/odd-ws:conocimiento`). El detalle estable va a los docs del proyecto y esto solo los indexa.

## Cómo se carga el contexto

Los `CLAUDE.md` se apilan (se concatenan), no se sobreescriben. Regla práctica: si vas a trabajar UN
ticket, ábrelo por dentro (su carpeta en `{{tickets}}/`): cargan la raíz **y** el ticket, y ambos se
reinyectan tras `/compact`. Abrir la raíz sirve para orquestar o mirar varios tickets: el contexto de uno
solo entra al leer un archivo de su carpeta, y tras `/compact` no vuelve hasta tocarlo de nuevo.

## Ciclo de un ticket

1. **Abrir** con `/odd-ws:abrir`: crea `{{tickets}}/<id>-<slug>/` desde la plantilla
   (`{{tickets}}/_plantilla/CLAUDE.md`) y llena estado, objetivo, criterios de aceptación y alcance. Un
   ticket es una carpeta.
2. **Entender, antes de codear.** Criterios de aceptación, alcance y no-goals escritos en el ticket. Si
   el pedido trae un «X **o** Y», pina con quien lo pide qué casos entran desde el arranque.
3. **Planear con ODD.** Explorar → Implementar → Revisar, anunciando la etapa en una línea. La exploración
   se delega cuando es grande por volumen de lectura. Un recurso compartido o un cambio que cruza capas se
   acuerda con su dueño ANTES de implementar.
4. **Paso 0 de diseño, antes de escribir código.** Para cada dato o pieza nueva, anota en el ticket cuál
   es el hermano vigente (lo que ya resuelve algo parecido) y quién consume el dato. Lo nuevo calca las
   convenciones de sus hermanos; lo existente que difiere no se toca de paso. Las reglas de cada capa
   están en las skills `criterios` y `capa-<capa>`.
5. **Escribir.** Un ajuste mínimo se hace en la sesión. Más que eso en una capa ⇒ el agente
   `writer-<capa>` (`.claude/agents/`), con el brief completo: archivos autorizados, Paso 0 y comandos de
   verificación.
6. **Revisar antes del commit** con `/odd-ws:revisar`: el agente `revisor-<capa>` de cada capa tocada y
   `revisor-diseno` (el diseño entre capas, siempre) leen el diff. Lo que se aplica a un ambiente
   compartido o se muestra a un líder queda ese mismo día en la rama del ticket.
7. **Cerrar** con `/odd-ws:cerrar`. Triaje de aprendizajes: lo verificado y general sube a la capa durable
   (los docs del proyecto o este archivo); lo de un solo ticket se queda en su carpeta. Los
   candidatos a graduar se anotan en el ticket apenas aparecen, no al final.

## Repos del equipo (leer sin pisar el working tree)

El código vive en los repos declarados en `workspace.config.json`; sus rutas en esta máquina, en
`workspace.local.json` (ignorado por git).

- **Autoridad de commit, asimétrica a propósito.** Un «commitea» abierto da libertad en esta raíz
  (repo propio, reversible). **Nunca se extiende a los repos del equipo:** ahí cada commit y cada push se
  autorizan puntualmente, aunque se haya dicho antes en la sesión. El default es que los commitea el
  usuario a mano. El merge a la rama principal lo autoriza un líder.
- **`push` siempre con destino explícito** (`git push -u origin <rama-del-ticket>`, nunca a secas).
  Verificar la rama no alcanza: hay que verificar el upstream.
- **`git fetch` antes de afirmar nada sobre el código** del repo.
- **Nunca cambiar de rama en el working tree del usuario.** Una segunda rama viva va en un **worktree**.
- **Un negativo de búsqueda u observación no es evidencia hasta probar que el instrumento sabe decir que
  sí.** Ejemplos: `Grep` solo alcanza las carpetas del workspace, mientras que `git grep` desde la
  terminal llega al repo completo; un archivo en otra codificación devuelve cero coincidencias; un
  instrumento mudo por diseño (un log que no escribe) no dice «no pasó».
- **No plantar `.claude/` ni tooling propio** en los repos del equipo sin que lo decidan ellos.

## Profundidad de investigación (perilla del usuario)

Si una pregunta exige investigar código y es **no trivial** (varios archivos, cruza repos o toca una zona
de baja confianza), ofrece el fork ANTES de arrancar: **¿rápida o profunda?** Si es trivial, responde
directo. **Rápida (default):** la pregunta es la prioridad; corrige los docs solo si algo los contradice,
y nunca en silencio. **Profunda:** prioriza la verificación (segunda fuente, revisión adversarial),
confirma o corrige los docs y responde a la vez, acotada al alcance de la pregunta. El usuario fuerza el
modo con `profunda` o `rápida`.

## Calidad: quien desarrolla también prueba

Tu análisis es la red: nadie atrapa después lo que aquí se deja pasar. **Calidad de pruebas > cantidad**
(datos reales, no suposiciones) y **la mejor opción, no la primera que funciona**: evalúa los tradeoffs y
revisa tu propio diseño cuando la evidencia lo cuestiona.

Un **efecto hacia otro sistema** (encolar un trabajo, notificar a un tercero, llamar a una API externa) se
decide con tres preguntas ANTES de escribirlo:

1. ¿El estado ya es **definitivo**?
2. ¿El efecto queda antes o después del `COMMIT`?
3. Si el efecto falla, ¿aborta o sigue?

Se miden en registros que pueden divergir entre los dos sistemas, no en «el mensaje se envió».

## Alcance mínimo: el encargo es el encargo

En los repos del equipo, **antes de editar un archivo compartido cuenta sus consumidores con `git grep`,
citando el comando y su salida.** Dos o más consumidores ⇒ el cambio va por **configuración** (valores,
constantes), nunca por estructura; uno solo ⇒ libertad. Los identificadores no se renombran de paso: son
contrato. Esto no contradice «la mejor opción»: es la mejor opción **dentro del encargo**. Si la solución
correcta lo excede, se dice y se hace igual lo pedido: ampliar el alcance lo decide quien lo encargó. Un
diff que crece de 2 a 12 archivos es señal de parar, no de avanzar.

## Dónde vive el conocimiento

El conocimiento sube cuando demuestra ser general: **sesión → ticket → docs del proyecto o este
archivo.** ¿Solo un ticket? Se queda en su carpeta. ¿Todo el proyecto? Los docs de dominio van a la
carpeta que declara `knowledge.docs` en `workspace.config.json`, y la metodología, aquí. Una regla de
una capa se gana con origen y evidencia: entra como fila a `.claude/reglas/matriz.csv`, con su
evidencia en `.claude/reglas/evidencia.md`. Si este archivo crece, el detalle se mueve a los docs y
queda el índice.

## Tickets

- Carpeta de cada ticket: `{{tickets}}/<id>-<slug>`; uno = una carpeta, y su `CLAUDE.md` parte de la
  plantilla.
- ⚠️ **Todo glob sobre los tickets se escribe recursivo**, `{{tickets}}/**/<id>-*`, nunca
  `{{tickets}}/<id>-*`: asumir hijo directo deja ciego justo al trabajo archivado en subcarpetas.
- Estado y conocimiento miden relojes distintos: `Estado` es la entrega; `Conocimiento` es si lo
  aprendido ya subió a la capa durable.

## Skills del plugin

- `/odd-ws:doctor` — chequeo de la máquina y de la instancia (OK / FALTA / AVISO); arregla de a un ítem,
  con autorización.
- `/odd-ws:conocimiento` — salud del conocimiento: índice, docs, links y anclas, cifras que se
  contradicen.
- `/odd-ws:eval-reviewers` — mide un revisor contra la revisión real de un líder, a ciegas y repetible.
- `/odd-ws:bootstrap` — genera o completa esta instancia desde una entrevista, sin pisar nada.
- `/odd-ws:abrir` — abre un ticket: carpeta desde la plantilla, alcance y no-goals, y los docs de dominio
  que toca.
- `/odd-ws:revisar` — revisión antes del commit: triaje, revisores por capa y recibo atado al diff.
- `/odd-ws:cerrar` — cierra un ticket: triaje de aprendizajes, graduación y commit de cierre.
