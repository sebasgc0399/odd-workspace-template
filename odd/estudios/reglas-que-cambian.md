# I22: las reglas que cambian

> Borrador de estudio para que el autor decida. No trae cambios de código. Base: odd-ws 0.9.0 (`0400cf8`).
> La idea está en `odd/roadmap.md:56`.

Lo planteaste así: «hoy dicen algo y entra en el chequeo pero meses despues lo cambian [...] pueden
superponer los chequeos». Y pediste analizarlo con rigor antes de implementar nada.

## 1. El problema

Una convención entra a la matriz como una fila con su ID, y su texto vive en un destino: el módulo de
chequeo, la skill de la capa, el revisor, `criterios` o la evidencia (`plugin/skills/cerrar/SKILL.md:64-68`).
Meses después el equipo cambia la convención. Si nadie retira la fila, los chequeos siguen exigiendo la
forma vieja. Si se gradúa la nueva sin tocar la vieja, las dos conviven.

Los dos escenarios usan una capa con prefijo `EJ`.

### Escenario A: un refactor reemplaza la convención

`EJ-03` (destino `chequeo`, modo bloqueo) exige la forma A. El equipo pasa a la forma B y migra parte del código.

| Pieza | Qué hace hoy | Cita |
|---|---|---|
| Hook en cada Edit o Write | Mira solo las líneas agregadas. Si el chequeo detecta la forma B (o la falta de A), toda línea nueva o editada en B salta con `EJ-03`. | `plugin/scripts/verificar_capa.py:143-148`, `Doc/diseno.md:39` |
| Primer toque | Si la regla es `pasiva`, se la recuerda al agente la primera vez que toca la capa. | `Doc/diseno.md:40` |
| Paso 0 | El writer calca el hermano vigente. Tras un refactor a medias, ese hermano puede estar en A o en B. | `plugin/plantillas/criterios.md:17-18` |
| Revisor | Aplica la skill de la capa al diff y marca la forma B. | `plugin/plantillas/revisor.md:33-34` |
| `cerrar` | Gradúa `EJ-09` («usa B») sin buscar reglas parecidas. Las dos quedan vivas. | `plugin/skills/cerrar/SKILL.md:64-70` |
| `matriz.py` | Pasa: solo exige que cada ID aparezca una vez en su destino. No compara reglas entre sí. | `plugin/scripts/matriz.py:226-255` |
| Calibración | `EJ-03` tendría aciertos en código nuevo, pero nadie la corre: el pre-commit solo corre `--test`, y ni el hook ni el doctor leen la matriz (`grep -c matriz` da 0 en los dos). | `plugin/plantillas/pre-commit:30` |

Resultado: con `EJ-03` y `EJ-09` vivas, cada línea nueva falla una de las dos.

### Escenario B: el refactor se revierte

Alguien retira `EJ-03` a mano, porque `cerrar` solo agrega filas al final y no tiene un paso para retirar
una (`plugin/skills/cerrar/SKILL.md:72`). Cambia su destino a `descarte` y borra su texto de todos los
destinos, evidencia incluida: el chequeo exige que un descarte no aparezca en ninguno
(`plugin/scripts/matriz.py:232-235`, `plugin/skills/cerrar/SKILL.md:102`). Meses después, el equipo vuelve a A.

| Pieza | Qué hace hoy | Cita |
|---|---|---|
| `EJ-09` | Salta sobre la forma A, que vuelve a ser la correcta. | como en A |
| Volver a A | Nace `EJ-12`: el script de `cerrar` da el máximo más uno y no recicla IDs. | `plugin/skills/cerrar/SKILL.md:82-95` |
| El porqué de A | Ya no está en `evidencia.md`, porque el descarte lo obligó a salir. Queda solo en la historia de git. | `plugin/scripts/matriz.py:232-235` |
| Editar `EJ-09` en su lugar | Nada lo impide, pero su `origen@hash` sigue citando la decisión de B. | `plugin/scripts/matriz.py:114-116` |

### Lo que muestra el proyecto de origen

La matriz del proyecto del que salió el motor (fuera de este repo, `Doc/diseno.md:3`) tiene 256 filas,
escritas en unas tres semanas. Medido sobre su historia de git:

- 10 filas son `descarte`, y todas nacieron así al graduar: duplicaban otra regla o el código las
  contradecía. Una de C# se descartó porque 141 de 174 archivos de su tipo hacían lo contrario.
- 7 filas se editaron en su lugar, y ninguna cambió de destino. En una, la revisión de un líder cambió la
  convención: la fila conservó su ID y su `origen@hash`, que ya no respalda el texto nuevo.
- 23 filas son `chequeo`. Otras 201 viven en prosa (skill, pasiva, revisor y criterios).

Todavía no hubo una regla vigente retirada meses después: la matriz es muy joven. El caso chico ya
existe: una convención cambió y la fila se editó sin dejar rastro.

## 2. Qué hay hoy

| Pieza | Qué ofrece | Qué le falta | Cita |
|---|---|---|---|
| Destino `descarte` | Retira una regla, y `matriz.py` comprueba que su ID no quede en ningún destino. | No dice qué la reemplaza. Borra su evidencia. `cerrar` no tiene un paso para retirar una fila existente. | `matriz.py:20`, `:232-235`; `cerrar/SKILL.md:64-111` |
| `origen` con `@hash` | Fija la fuente a un commit de la instancia; un rango sin hash es error. | El hash solo se valida al leer y nada lo compara después. Apunta a la bitácora del ticket, no al código ni al repo del equipo. | `matriz.py:69-81`, `:114-116`; `cerrar/SKILL.md:66`; `Doc/diseno.md:759` |
| `origen` `memoria:<slug>` | Marca `graduada` a la memoria citada. | `graduada` le gana a `cambiada`: una memoria que cambia después de graduar no vuelve a salir. Lo graduado no se registra. | `memorias.py:30`, `:279-284`; `Doc/diseno.md:971` |
| `motivo` | Texto libre, obligatorio. | Ningún script lo lee. | `matriz.py:130-131` |
| `reglas.py --calibrar` | Cuenta aciertos por regla sobre una carpeta, con cada archivo como nuevo. D2: una regla bloquea solo con 0 aciertos en el corpus. | Mide solo `chequeo`. Cuenta igual el código viejo y el nuevo. Se corre a mano, y nada une el conteo con el modo. | `reglas.py:75-85`, `:99-136`; `Doc/diseno.md:47`, `:994` |
| Solo líneas agregadas | El hook no ve el código que no se tocó, y descarta un hallazgo que ya estaba en la línea quitada del mismo hunk. | Nada: esto ya protege el código viejo. | `verificar_capa.py:143-148`, `:161-180` |
| Revisor | Deja aparte lo que ya estaba antes del cambio. | Sus hallazgos citan `ruta:línea`, no el ID de la regla: no se puede contar qué regla se disputa. | `plantillas/revisor.md:25-26`, `:35` |
| Disputas (D6) | Diseñadas: una regla disputada vuelve a aviso. | El buzón `.claude/registro/` no está implementado. | `Doc/diseno.md:1003`, `:961` |
| Paquetes | Fijados a una etiqueta, con su propio `descarte` y un prefijo que no choca. | Nada compara una regla de paquete con una de la instancia. | `Doc/capas-y-reglas.md:47`, `:85`, `:99` |

## 3. Las preguntas de fondo

### Quién decide que una regla está vieja

D6 dice que el sistema no se reescribe con sus propios resultados: las entradas vienen de afuera
(`Doc/diseno.md:999`). Un script puede señalar una regla sospechosa. Retirarla lo decide el usuario, como
cualquier graduación, con su sí (`plugin/skills/cerrar/SKILL.md:48-57`). El lugar natural es `cerrar`, que
solo invoca el usuario (`Doc/diseno.md:42`).

### Cómo se detecta que el origen quedó viejo

El hash del origen es procedencia, no un sensor. Fija la decisión del ticket que hizo nacer la regla, y esa
bitácora casi no cambia después del cierre (`plugin/skills/cerrar/SKILL.md:66`). Lo que cambia cuando el
equipo cambia de convención es el código y, a veces, el `CLAUDE.md` del repo, y ninguno de los dos puede
ser origen (`Doc/diseno.md:759`). Además, un ticket archivado cambia de carpeta
(`plugin/skills/cerrar/SKILL.md:23`): que la ruta no exista en HEAD no dice que la regla esté vieja. El
origen se comprueba con `git cat-file -e <hash>:<ruta>`.

Las señales que sí dicen algo:

1. **Una memoria cambiada después de graduar:** su `modified` es posterior al commit que agregó la fila.
   La fecha del commit sale de git, sin guardar nada nuevo.
2. **Una fila editada en su lugar sin un origen nuevo:** el caso real de arriba. Sale de `git log -p` sobre la matriz.
3. **Una regla de `chequeo` con aciertos en código reciente:** si el equipo escribe B desde hace meses,
   `EJ-03` salta sobre lo que el equipo ya aceptó.
4. **Un hallazgo que el líder disputa:** solo sirve si el hallazgo cita el ID de la regla.

Ninguna dice quién tiene razón. Un acierto en código reciente puede ser una regla vieja o un defecto que pasó.

### Cómo se nota que dos reglas se contradicen

En prosa, solo leyendo. En `chequeo`, una calibración lo insinúa: si dos reglas se contradicen, casi todo
archivo de la capa dispara una de las dos. El mejor momento es al graduar: la regla nueva está escrita, el
usuario está presente y la capa tiene pocas filas que comparar (entre 67 y 95 por capa en el proyecto de origen).

### Qué pasa con el código escrito bajo la regla vieja

Ya está protegido. La plantilla dice que «lo existente que difiere no se toca de paso»
(`plugin/plantillas/CLAUDE.md:42`), el hook solo mira líneas agregadas (`verificar_capa.py:143-148`) y el
revisor deja aparte lo que ya estaba (`plugin/plantillas/revisor.md:25-26`). Migrar ese código es un
ticket propio, y ampliar el alcance lo decide quien lo encargó (`plugin/plantillas/CLAUDE.md:105-106`).

El riesgo real está en el Paso 0. Tras un refactor a medias, la mayoría de los hermanos sigue en la forma
vieja, y «lo nuevo calca su forma» (`plugin/plantillas/criterios.md:17-18`). Nada dice quién gana entre una
regla vigente y el hermano que la contradice. Es la pieza que I21 resuelve con la lista `no_molde`
(`Doc/diseno.md:991`, `odd/roadmap.md:56`).

## 4. Opciones

| # | Opción | Qué cambia | Costo | Protege | Riesgo |
|---|---|---|---|---|---|
| O1 | Buscar al graduar y enlazar en el `motivo` | `cerrar` muestra las filas vivas de la capa y de `criterios`, y pregunta si la nueva reemplaza a alguna. La vieja pasa a `descarte` con «reemplazada por EJ-09» en su `motivo`, en el mismo commit. Un cambio de sentido no se edita: nace otra fila. El enlace solo puede vivir en la matriz, porque el texto de `EJ-09` no puede nombrar a un descarte (`matriz.py:232-235`). | Bajo: texto de la skill, sin esquema nuevo. | El escenario A, en el momento en que más se sabe. Deja rastro del reemplazo. | Depende de que el agente vea la relación. Una regla transversal tiene una fila por capa (`cerrar/SKILL.md:70`): hay que retirarlas todas. |
| O2 | Validar el enlace en `matriz.py` | Un `descarte` con «reemplazada por X» exige que X exista y sea de la misma capa. Una cadena que vuelve a una regla parecida marca una reversión. | Bajo: un chequeo más sobre `motivo`. Las versiones anteriores lo ignoran. | Que el enlace no apunte a la nada. Hace visible el escenario B. | Vuelve sintaxis un texto libre. Enlazar con un paquete pide su matriz, que ya se carga (`matriz.py:339-349`). |
| O3 | Columnas nuevas: `reemplaza`, o vigencia por fecha o versión | El encabezado pasa de 8 a 9 o 10 columnas. | Alto: `matriz.py` rechaza otro encabezado (`:152-154`) y los paquetes usan las mismas columnas (`capas-y-reglas.md:33`). P4 sube la mayor cuando se rompe la config, el contrato de módulos o la API (`Doc/diseno.md:30`); la matriz no está en la lista, pero romperla rompe cada instancia y cada paquete. | Un ciclo de vida explícito y consultable. | Una fecha de fin no se conoce de antemano, y vencer sin decidir es desviarse en silencio. El hook no lee la matriz: la vigencia tendría que vivir igual en el código del módulo. |
| O4 | Detectar el origen que cambió | `memorias.py` avisa «graduada y cambiada» si la memoria es posterior al commit de su fila. Un chequeo avisa de una fila editada sin origen nuevo. | Bajo a medio. engram no da fechas (`Doc/diseno.md:970`): ahí queda parcial. | Las reglas nacidas de una memoria (`cerrar memorias`) y el caso real de la fila editada. | Cubre poco del escenario A, porque el código no es origen. Un aviso que se repite cansa si no se puede marcar visto. |
| O5 | Recalibrar con tiempo | `reglas.py --calibrar` suma `--desde <commit>` y cuenta solo las líneas agregadas desde ahí. Una regla con aciertos en código reciente sale como «posiblemente vieja». A mano o en un ritual, no en cada `doctor`. | Medio: leer `git log` o `blame` por repo. | Las reglas de `chequeo`, con datos del código que el equipo acepta hoy. Une la calibración con D2. | Solo cubre `chequeo` (23 de 256 en el origen). Un acierto puede ser un defecto real. En un corpus grande tarda, y por eso no va en el doctor por defecto. |
| O6 | Ritual periódico | Una lista por capa: la edad de cada regla, las señales de O4 y O5 y, si los hallazgos citaran el ID, cuántas veces se disputó. El usuario decide mantener o retirar. | Bajo en código, alto en atención. | Las reglas en prosa, que ningún script mide. | Sin señales es releer 250 filas, y se vuelve ceremonia. |
| O7 | Acotar una regla a código posterior a un commit | La fila o el módulo llevan un `desde`; antes de ese commit la regla no aplica. | Medio, y pide esquema (O3) o lógica en cada módulo. | Que la regla nueva no salte sobre código viejo. | Repite lo que ya hacen las líneas agregadas y `filtrar_preexistentes`. Su parte útil es la de calibrar, que ya está en O5. |

La idea tal como quedó en el roadmap (`odd/roadmap.md:57`) es O1 más el doctor recalibrando. O1 se
sostiene. El doctor no es buen lugar: no lee la matriz, calibrar todo el corpus mezcla el código viejo con
el nuevo y solo mide `chequeo`. O5, con `--desde`, da la misma señal sin esa mezcla.

## 5. Recomendación

Atacar el cambio cuando nace, con lo que ya existe, y medir el código solo cuando haya un caso real. O1 y
O2 primero, O4 para las memorias, y O5 cuando llegue el primer refactor que lo pida. O3 y O7 quedan
descartadas por ahora, como el campo `fuente`, que espera su primer caso (`Doc/diseno.md:1084`).

Orden de pasos:

1. **La regla de la fila.** Un cambio de sentido no se edita en su lugar: nace una fila nueva, y la vieja
   pasa a `descarte` con «reemplazada por <ID>». En su lugar solo se corrige una errata. Va en `cerrar` y en
   `Doc/capas-y-reglas.md`.
2. **O1 en `cerrar`.** La propuesta del paso 4 suma, por cada fila nueva, las filas vivas de su capa y de
   `criterios` que parecen relacionadas, con la pregunta «¿reemplaza a alguna?». El mismo sí cubre las dos filas.
3. **O2 en `matriz.py`**, con su test.
4. **La evidencia de una regla retirada.** Decidir si se conserva bajo un encabezado de retiradas en
   `evidencia.md`, lo que pide eximir ese archivo del chequeo de `matriz.py:232-235`. Sin eso, una reversión
   pierde el porqué de la regla original.
5. **O4 para memorias.** El aviso «graduada y cambiada» en `memorias.py` y en la línea de `cerrar` que
   cuenta las memorias sin triar.
6. **Con un caso real:** O5 (`--desde`), y que los hallazgos de los revisores citen el ID de la regla. Esto
   último puede ir con I17, que ya trata la calidad de la revisión (`odd/roadmap.md:51`), y es el requisito de I46, las
   métricas de fricción por regla.

Mientras el paso 1 no exista, el caso real del proyecto de origen (una fila editada en su lugar) puede
repetirse en cualquier instancia.

## 6. Preguntas para el autor

1. **¿Quién retira una regla?** Propuesta: solo el usuario, con su sí en `cerrar` o en el ritual. Los
   scripts solo señalan (D6).
2. **¿Se puede editar una fila en su lugar?** Propuesta: solo por una errata. Un cambio de sentido es una
   fila nueva más el `descarte` de la vieja.
3. **¿Dónde vive el enlace de reemplazo?** Propuesta: en el `motivo` de la fila retirada, validado por
   `matriz.py`, sin columna nueva hasta que una versión mayor lo justifique.
4. **Si el equipo revierte, ¿se reactiva el ID viejo o nace otro?** Propuesta: nace otro, que reemplaza a
   la intermedia y cita a la vieja en su `motivo`. Los IDs no se reciclan, y la evidencia retirada se
   conserva bajo «Retiradas».
5. **Si una regla vigente y el hermano vigente se contradicen, ¿cuál gana?** Propuesta: la regla. El hermano
   que la contradice deja de ser molde y se anota en el Paso 0. Se decide junto con I21.
6. **¿El doctor avisa cuando una capa crece demasiado?** Propuesta: sí, con un aviso y no una falla, cuando
   una capa pasa de cierto número de reglas vivas en la matriz; el umbral se fija con la primera capa real
   que lo roce. Viene de una revisión externa del 2026-11-18: la carga ya es por capa, porque solo el revisor
   y el writer de una capa tocada leen su skill, pero nada le pone tope a una capa.
