# I21: la perilla `mold_source`

Borrador de estudio para decidir con el autor. No cambia código: prepara la conversación.
Fuente: la idea I21 (`odd/roadmap.md:56`) y la decisión D2 (`Doc/diseno.md:989-995`). Base: odd-ws `0.9.0`.

## 1. El problema

D2 dice que lo único que cambia entre un proyecto estricto, uno legacy y uno nuevo es de dónde sale el
molde, con una perilla por capa: `repo` (todo hermano vigente es molde, salvo `no_molde`) o `propio`
(ningún hermano es molde, salvo `molde`; el resto es solo contrato). Un proyecto nuevo es `propio` sin
corpus (`Doc/diseno.md:991-993`).

Hoy la perilla se valida y no hace nada:

- `config_loader` la valida en `defaults` y en cada capa (`plugin/scripts/config_loader.py:15`, `:64-67`, `:207`, `:357-360`).
- `molde_de` existe (`config_loader.py:373-374`), pero solo la llaman los tests (`config_loader.tests.py:161-168`).
- El bootstrap la propone y promete un efecto: «`repo` quiere decir que los revisores comparan cada cambio contra el código que ya está en el repo» (`plugin/skills/bootstrap/SKILL.md:47`).
- La generación de agentes y skills no recibe la config, solo la capa, la fecha y el host (`plugin/scripts/bootstrap_agentes.py:44-46`, `:87-97`; `plugin/scripts/plantilla_writer.py:116-120`): con `repo` o con `propio` salen los mismos bytes.
- Las listas `molde` y `no_molde` quedaron fuera desde el bootstrap (`odd/tasks/bootstrap.md:18`, `:64`).

### Lo que vive hoy un proyecto nuevo, paso a paso

| Paso | Qué pasa | Dónde falla |
|---|---|---|
| Bootstrap | Propone `repo`. Si eliges `propio`, nada cambia. La matriz vacía «es lo normal» (`bootstrap/SKILL.md:119`), y la siembra de I16 solo aplica si el repo ya tiene reglas escritas (`:121`). | Un repo nuevo no tiene reglas que sembrar: arranca sin nada. |
| Abrir | El Paso 0 pide el hermano vigente de cada pieza (`plugin/skills/abrir/SKILL.md:114-116`, `plugin/plantillas/ticket.md:37`). Sin código, queda «sin hermano» con la búsqueda que lo probó (`plugin/plantillas/criterios.md:17-18`). | Nada dice de dónde sale la forma entonces. La regla solo sabe «lo nuevo calca las convenciones de sus hermanos» (`plugin/plantillas/CLAUDE.md:41-42`). |
| Writer | «Abre el molde que nombra la skill de la capa» (`plugin/plantillas/writer.md:45`). La sección `## Moldes` es el relleno de la plantilla (`plugin/plantillas/capa.md:27-30`). | El writer escribe con lo que el modelo trae por defecto, y «las divergencias con el molde» (`writer.md:56`) no tienen contra qué medirse. |
| Triaje | Sin remoto no hay `origin/HEAD` y hace falta la base explícita (`plugin/skills/revisar/SKILL.md:40`). Fuera de T-SQL, la señal de consumidores es inválida (`plugin/scripts/triaje.py:27`, `:417-420`) y el modo sale `completo` (`triaje.py:511-513`). | Es caro, pero no depende del molde: depende del lenguaje. |
| `revisor-diseno` | Pide al menos dos candidatos a hermano (`plugin/plantillas/revisor-diseno.md:62-65`). Con tres archivos, elige hermanos débiles o declara que no hay. | «Tamaño relativo al hermano» (`:131-134`) vuelve hallazgo toda lógica sin equivalente y sin razón escrita: un falso positivo por pieza. «La buena práctica genérica no le gana al hermano» (`:141`) queda sin ancla. |
| `revisor-<capa>` | Aplica la skill de la capa y `criterios` (`plugin/plantillas/revisor.md:33-34`). | Con la skill vacía, solo quedan los criterios transversales. |
| Ticket 2 | Lo que escribió el writer del ticket 1 ya es el hermano vigente, y «gana el hermano» (`revisor-diseno.md:73-74`). | **El molde por accidente:** lo primero que escribió un writer sin molde pasa a ser el canon, sin que nadie lo eligiera. |

El fallo de fondo es el último. Con `repo` es la semántica de D2; con `propio`, D2 lo evitaría, porque el
hermano sería solo contrato (`Doc/diseno.md:992`), pero nadie lee la perilla. El caso legacy es el espejo:
con un hermano malo, «gana el hermano» defiende copiar lo que no se quiere (`odd/roadmap.md:56`).

### Son dos problemas, no uno

- **No hay hermano.** Pasa en un proyecto nuevo, pero también en cualquier proyecto cuando nace una pieza de
  un tipo que no existía. Las plantillas no tienen respaldo para ese caso, con cualquier valor de la perilla.
- **Hay hermano, pero no es molde.** Es el caso legacy, y es para lo que existe la perilla.

Quitar o mantener la perilla no resuelve el primero. Cualquier opción de la sección 4 lo necesita.

## 2. Los tres tipos de proyecto

| | Estricto (equipo con convenciones) | Legacy (código que no se quiere copiar) | Nuevo (sin corpus) |
|---|---|---|---|
| Valor en D2 | `repo` | `propio` con lista `molde` | `propio` sin corpus |
| De dónde sale la forma | El hermano vigente | Los moldes que la instancia nombra | Las convenciones escritas de la capa, y después los moldes que una persona promueve |
| Writer | Calca al hermano, como hoy | Lee al hermano solo como contrato (firma, datos, errores que otros consumen) y calca el molde nombrado | Sin hermano, sigue `## Convenciones`; si está vacía, lo declara en `limites:` |
| Revisores | «Gana el hermano» (`revisor-diseno.md:73-74`) | Copiar un patrón de `no_molde` es hallazgo; divergir del hermano no lo es, salvo en el contrato | Sin tabla de tamaño relativo; juzga contra la skill de la capa y avisa cuando una pieza se vuelve molde sin que nadie la eligiera |
| Reglas | Se siembran del repo (I16) y se gradúan | La matriz describe las convenciones destino, no las del código | Cambian rápido: ver sección 5 |
| Triaje | Cuenta consumidores (`triaje.py:410-460`) | Igual: el contrato pesa más que nunca | Objetos nuevos sin consumidores previos (`triaje.py:437-439`); el molde no cambia nada aquí |

El triaje queda igual en los tres: D2 dice que la perilla no decide qué bloquea (`Doc/diseno.md:994`).

## 3. Dónde tendría que leerse `mold_source`

| # | Punto | Archivo y línea | Qué cambiaría |
|---|---|---|---|
| 1 | Brief de `revisar` | `plugin/skills/revisar/SKILL.md:110` | Una línea «Molde de `<capa>`: `repo` o `propio`», sacada de `molde_de` (`config_loader.py:373`). Es el único punto de lectura en tiempo de ejecución que no toca la huella de las plantillas. |
| 2 | Brief del writer | `plugin/plantillas/CLAUDE.md:44-46` | La misma línea, junto al Paso 0. |
| 3 | Writer, al explorar y al cerrar | `plugin/plantillas/writer.md:45`, `:56` | Con `propio`, el hermano es contrato y el molde es el de la skill. |
| 4 | Revisor de capa | `plugin/plantillas/revisor.md:33-34` | Lo mismo, del lado del revisor. |
| 5 | `revisor-diseno`, paso 2 y tamaño | `revisor-diseno.md:58-74`, `:131-134`, `:141-152` | Qué hacer sin hermano y con un hermano que no es molde. Es un solo agente para todas las capas (`bootstrap_agentes.py:53-55`): el valor por capa no se puede fijar en su texto y tiene que llegar en el brief. |
| 6 | Paso 0 | `criterios.md:17-18`, `CLAUDE.md:40-43`, `abrir/SKILL.md:114-116`, `ticket.md:37` | «Sin hermano» deja de ser un callejón: dice de dónde sale la forma. |
| 7 | Moldes de la instancia | `capa.md:27-30` | El hogar natural de las listas `molde` y `no_molde` de D2. |
| 8 | Promover un molde | `plugin/skills/cerrar/SKILL.md:68` | El destino `skill` ya escribe en la skill de la capa: falta decir que un molde se gradúa por ahí. |
| 9 | Generación y regeneración | `bootstrap_agentes.py:87-97`, `plantilla_writer.py:207-208`, `plugin/scripts/doctor.py:392-396` | Solo si el texto de los agentes dependiera de la perilla: hoy el generador no recibe la config, y el doctor marcaría `atrasado` al cambiarla. |
| 10 | Bootstrap | `bootstrap/SKILL.md:47` | Decir lo que la perilla hace de verdad. |
| 11 | Doctor | (nuevo) | Un AVISO si una capa `propio` no tiene moldes ni convenciones. |
| | **No:** el triaje | `Doc/diseno.md:994` | La perilla habla de forma; el triaje, de riesgo. |

## 4. Opciones

**Lo que necesitan todas:** un respaldo «sin hermano» en `criterios`, en el writer y en los dos revisores.
Sin hermano, la forma se juzga contra `## Convenciones` de la capa; la tabla de tamaño relativo no aplica;
y si la skill está vacía, se declara como límite, no como hallazgo.

### A. Quitar la perilla

- **Qué es:** borrar `MOLDES`, `_molde`, `molde_de` y sus tests (`config_loader.py:15`, `:64-67`, `:373-374`; `config_loader.tests.py:153-168`), la línea del bootstrap (`SKILL.md:47`, `:65`) y reescribir D2.
- **Cuesta:** bajo. Una config vieja con la clave sigue cargando, porque la raíz de la config no rechaza claves desconocidas (solo `knowledge` es estricta, `config_loader.py:237-239`).
- **Protege:** la honestidad. Hoy el bootstrap promete un efecto que no existe.
- **Arriesga:** el caso legacy pierde su palanca, y D2 se abandona sin haberla probado. El proyecto nuevo sigue igual: A no toca el molde por accidente.

### B. `propio` cambia los prompts

- **Qué es:** con `propio`, writer y revisores leen al hermano solo como contrato; la forma sale de las convenciones escritas o, si no hay, de los primeros commits.
- **Dos cableados:** B1 genera una variante de cada plantilla según la perilla; B2 deja un párrafo fijo que define los dos valores, y la perilla llega en el brief (puntos 1 y 2).
- **Cuesta:** B1, medio-alto: dos variantes por plantilla, la config hasta el generador y el doctor, y todas las instancias ven sus agentes `atrasado` (`plantilla_writer.py:207-208`). B2, medio-bajo.
- **Protege:** el legacy deja de copiar lo malo.
- **Arriesga:** «los primeros commits» como fuente es el molde por accidente con otro nombre, y choca con D6: el sistema no se certifica con sus propios resultados (`Doc/diseno.md:999`). Con la skill vacía, `propio` deja al writer de un proyecto nuevo sin ninguna fuente.

### C. El molde sale de la instancia

- **Qué es:** las listas de D2 viven como contenido de la skill de la capa: `## Moldes` (ya existe) y una sección `## No molde`. Con `propio`, solo lo listado es molde; con `repo`, todo hermano salvo lo de `## No molde`. Promover un archivo a molde es graduarlo con `cerrar`, destino `skill`, con su fila y su origen. El doctor avisa si una capa `propio` no tiene moldes ni convenciones, o si un molde listado ya no existe.
- **Cuesta:** medio: la plantilla `capa.md`, un párrafo en tres plantillas, la línea del brief (B2), un ítem del doctor, docs y sus tests.
- **Protege:** los dos casos. En legacy, lo listado como `no_molde` no se copia; en un proyecto nuevo, nada es molde hasta que una persona lo promueve. Es un artefacto verificable, no algo que el modelo recuerda (`Doc/diseno.md:11`).
- **Arriesga:** el día 1 de un proyecto nuevo sigue vacío, así que hace falta un primer ticket de molde, como la siembra de I16 (`Doc/diseno.md:759`). La lista se desactualiza si nadie la cuida (sección 5).

| Opción | Cuesta | Resuelve «sin hermano» | Resuelve legacy | Evita el molde por accidente | Riesgo principal |
|---|---|---|---|---|---|
| A | Bajo | Solo con la base común | No | No | Abandonar D2 sin probarla |
| B1 | Medio-alto | Solo con la base común | Sí | No | Migración de huellas; autocertificación |
| B2 | Medio-bajo | Solo con la base común | Sí | No | Autocertificación |
| C con B2 | Medio | Sí | Sí | Sí | Día 1 vacío; listas que envejecen |

## 5. El vínculo con I22

I22 propone que `cerrar` busque qué regla reemplaza a cuál y que el doctor recalibre contra el código
actual, marcando las reglas que saltan sobre código ya aceptado (`odd/roadmap.md:57`).

- **La perilla decide quién gana cuando el código y la regla discrepan.** Con `repo`, gana el hermano (`revisor-diseno.md:73-74`); con `propio`, la instancia (`Doc/diseno.md:992`). El estudio de I22 (`reglas-que-cambian.md`, pregunta 5) propone que gane la regla y deja la decisión para I21: son la misma pregunta.
- **I22 tiene que leer la perilla.** Con `repo`, una regla que salta sobre código aceptado es sospechosa. Con `propio`, esos aciertos son deuda de migración: se listan, no retiran la regla. Sin esa lectura, la recalibración retiraría justo las convenciones nuevas de un proyecto que cambia rápido.
- **La calibración de D2 también.** Una regla bloquea solo si da 0 aciertos en el corpus (`Doc/diseno.md:994`). En un proyecto nuevo el corpus es mínimo y todo pasa; tras un cambio de convención, el código viejo da aciertos y la regla nueva ya no puede bloquear. Con `propio`, el corpus que calibra deberían ser los moldes, no todo el código.
- **Los moldes también se reemplazan.** Con C, un molde es contenido graduado con su fila, así que «reemplazada por X» de I22 vale igual para un molde. Conviene diseñar el reemplazo una sola vez.
- **El campo `fuente: equipo | propia`** por fila, diferido hasta su primer caso (`Doc/diseno.md:1084`), es el primo por fila de la perilla: decidirlos juntos.

Orden: I21 primero, porque fija quién gana; I22 después, leyendo la perilla.

## 6. Recomendación y orden

C, cableada como B2, con la base común antes. No A: quitar la perilla deja la promesa honesta, pero el
proyecto nuevo sigue fallando igual, porque las plantillas asumen un hermano con cualquier valor.

1. **Medir sin código.** Dos repos sintéticos, como los fixtures previstos (`Doc/diseno.md:1082`): uno vacío y uno con un hermano malo sembrado. Un ticket en cada uno con las plantillas de hoy: `/odd-ws:revisar`, y el caso congelado en modo sombra con `/odd-ws:eval-reviewers` (`plugin/skills/revisar/SKILL.md:26`). Así ves cómo se comporta tu proyecto nuevo antes de cambiar nada, y quedan los casos para medir después.
2. **La base común:** el respaldo «sin hermano» en `criterios`, el writer y los dos revisores, para cualquier valor.
3. **Textos honestos:** `bootstrap/SKILL.md:47` y D2 dicen lo que la perilla hace.
4. **C:** `## No molde` en `capa.md`, la línea del brief desde `molde_de`, el párrafo fijo en las plantillas, el destino `skill` para los moldes en `cerrar` y el AVISO del doctor.
5. **Medir otra vez** con los mismos dos repos y comparar.
6. **I22**, leyendo la perilla.

## 7. Preguntas para el autor

1. **¿La perilla sigue por capa o pasa a ser global?** Propuesta: por capa, como D2. El caso real es mixto (una capa nueva sobre un backend legacy), y con el brief el costo es el mismo.
2. **¿Quién promueve un archivo a molde?** Propuesta: solo una persona, en `cerrar` y con su fila. Nunca un writer ni un revisor, por D6.
3. **¿Qué propone el bootstrap en un repo casi vacío?** Propuesta: `propio`, más un primer ticket «el molde de `<capa>`» que escriba tres a cinco convenciones, como la siembra de I16, sin forzarlo.
4. **¿Medimos antes de decidir, o eliges ya?** Propuesta: medir (paso 1). No toca código, responde tu duda de cómo se comporta un proyecto nuevo y deja los casos para comparar.
