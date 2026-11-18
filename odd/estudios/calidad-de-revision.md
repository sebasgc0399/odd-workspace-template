# Estudio: la calidad de `/odd-ws:revisar` (I17)

Borrador para que el autor decida. No cambia código. Base: odd-ws 0.9.0, 2026-11-18. Va junto con el [estudio de costo](costo-de-revisar.md): calidad y costo son dos caras de la misma elección.

Cómo leer las citas: `revisar` es `plugin/skills/revisar/SKILL.md`; `eval` es `plugin/skills/eval-reviewers/SKILL.md`; las plantillas están en `plugin/plantillas/` y los scripts en `plugin/scripts/`; `diseno` es `Doc/diseno.md`; `exp` es `odd/tasks/experiencia-de-uso.md`; `roadmap` es `odd/roadmap.md`; `costo` es `odd/estudios/costo-de-revisar.md`. Lo de Claude Code sale de su [página de subagentes](https://code.claude.com/docs/en/sub-agents), y los precios, de la [tabla de precios de la API](https://platform.claude.com/docs/en/about-claude/pricing), las dos consultadas el 2026-11-18.

## 1. Qué es «calidad» acá

Un hallazgo vale si es **real** (el código le da la razón), **grave** (su consecuencia importa) y **accionable** (dice qué viola y cómo debe quedar). Lo demás es ruido: un falso positivo, una decisión ya tomada que vuelve, una nota de estilo que gasta la corrida de diseño.

| Dimensión | Cómo se mide hoy | Lo que falta |
|---|---|---|
| Real | en `eval`, un juez ciego verifica en el código y saca lo refutado a `disputadas` (eval:60-65) | en el día a día nadie anota el destino de cada hallazgo (costo:157) |
| Grave | `CRITICAL`, `WARNING`, `SUGGESTION` (revisor-diseno.md:164-166), separadas en la consolidación (revisar:154) | `puntuar.py` no pondera la severidad: puntaje = `ok` + 0,5 × `parcial` (puntuar.py:52-59) |
| Accionable | `ok` es el mismo problema y la misma dirección que el líder; `derivado` no tiene dirección (eval:50-58) | |
| Completa | media, unión, estables y k/N por brazo (eval:88) | solo hay verdad de terreno cuando hay un líder |
| Sin ruido | `reves` y `elogio` cuentan en contra (eval:54-55); la aceptación pide falsos positivos en 0 (eval:101) | la escala no tiene valor para un hallazgo fuera de la verdad de terreno (puntuar.py:11, 101-107): el falso positivo se cuenta a mano |
| Estable | frecuencia k/3 y conflictos sin votar (revisar:151-152) | |

Hay dos instrumentos. `eval-reviewers` mide aciertos contra un líder, pero no falsos positivos ni severidad. La consolidación y el recibo ven todo, pero no guardan el destino de cada hallazgo ni el modelo que revisó: el recibo anota solo los nombres de los revisores (recibo.py:196). El primer arreglo de calidad es el mismo que el de costo: medir (costo:142-157).

## 2. Las palancas

### 2.1 El modelo de los revisores

**Lo que hay hoy.**
- Las plantillas no llevan `model` (revisor-diseno.md:1-9, revisor.md:1-10): cada revisor hereda el modelo de la sesión.
- La regla 5 pide el mismo modelo en todas las corridas de una revisión: se puede pasar el mismo alias a todas, nunca un ID (revisar:25, diseno:908).
- El «perfil de modelos» (`rol → (alias, effort)` y el umbral del modo ahorro) quedó fuera del plugin (diseno:1005, 1024).

**Lo que admite Claude Code.** El frontmatter de un subagente acepta `model` con un alias (`sonnet`, `opus`, `haiku`, `fable`), un ID completo o `inherit`; sin él, corre en el modelo de quien lo lanza. Gana el `model` de la invocación (solo alias), después el del frontmatter, después `CLAUDE_CODE_SUBAGENT_MODEL` y al final el de la sesión. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` ignora los dos primeros. Un subagente en otro modelo no hereda el `effort` de la sesión: se fija con `effort`.

**¿Es viable la sesión en el modelo más capaz y los revisores en uno más barato?**
- **De mecánica, sí, hoy y sin código.** La regla 5 ya permite pasar `model: "sonnet"` a todas las corridas. `CLAUDE_CODE_SUBAGENT_MODEL` también sirve, pero cambia además a los writers.
- **Solo en Claude Code.** Codex no lleva `model` en su TOML (diseno:329) y Pi lo omite a propósito, porque un alias de Claude Code no es una referencia de Pi (diseno:344).
- **De calidad, no hay un solo dato.** Es justo lo que no se nota cuando falla: una revisión con menos hallazgos se ve igual que un cambio más limpio.

**Lo que se sabe para estimar.**
- **Precio.** Sonnet 5.5 cuesta la mitad que Opus 5.5 en cada columna: entrada 2 contra 4, lectura de caché 0,10 contra 0,20 y salida 10 contra 20 USD por millón. Las 35 corridas que el estudio de costo valuó en unos 96 USD (costo:35) serían unos 48 con los mismos tokens. Un modelo que hace más turnos se come parte de eso.
- **El revisor de diseño es el trabajo de más juicio del flujo:** elegir el hermano entre al menos dos candidatos y rastrear cada dato entre capas, con control positivo para cada negativo (revisor-diseno.md:62-64, 79-105). En los negativos («nadie lo lee»), un modelo que busca menos no debería sumar falsos positivos, porque sin control positivo un negativo pasa a ser un límite (revisor-diseno.md:101-102). Lo esperable es que falten hallazgos, que es el error caro (revisar:64).
- **El revisor de capa aplica reglas escritas en su skill** (revisor.md:30-36): es el candidato natural a un modelo más barato. En SM-1 no corrió ninguno (costo:19), así que tampoco hay dato.
- **La regla 5 es más estricta que lo que la frecuencia necesita.** La frecuencia solo se cuenta entre las corridas de diseño (revisar:151), y las de capa son una por capa (revisar:97-98). Bastaría «el mismo modelo entre las corridas de un mismo revisor».
- **Registro.** `rescatar.py` ya lee `model` del `.meta.json` de cada corrida y lo imprime (rescatar.py:141, 189-190); falta confirmar en una corrida real que Claude Code lo escribe. El recibo no lo guarda (recibo.py:196).
- **La alternativa sin cambiar de modelo:** el mismo modelo con menos `effort`, en la invocación o en el frontmatter.

Efecto esperado: la mitad del costo por corrida. Riesgo: perder hallazgos de consumidor y de hermano sin verlo. Costo de probarlo: un eval, sin tocar código.

### 2.2 Lentes en vez de muestras

Hoy `completo` corre `revisor-diseno` tres veces con el mismo prompt, y solo cambia el orden de lectura (revisar:98, 102). Los revisores de capa ya son una lente, una por capa.

Lo que dijo SM-1: de 61 hallazgos, 28 los vieron las tres corridas, 17 dos y 16 una (costo:70). Tres de cada cuatro los vio más de una corrida, y la tercera muestra suma en promedio solo el 9% (costo:70). Ese es el lugar donde una lente podría rendir más que otra muestra.

Candidatas, por lo que hoy no cubre nadie:
- **Las pruebas.** Ni `revisor-diseno.md`, ni `revisor.md`, ni `criterios.md` mencionan tests (una búsqueda de «test» y «prueba» no da nada). RDD lo cubre con su lente de confiabilidad (roadmap:52).
- **Lo que el triaje declara que no ve** (revisar:66), que el estudio de costo ya propone nombrar en el prompt (costo:116).
- **Un paso del propio revisor como foco,** por ejemplo el de consumidores, el que más lee (costo:25-26).

Lo que se pierde: una lente rompe la frecuencia. Lo que solo ella puede ver sale siempre 1/3, «a confirmar», y no hay dos miradas sobre la misma pieza para mostrar un conflicto (revisar:15, 152). Por eso no se reemplazan las tres: se canjea la tercera. La consolidación sería k/2 entre las dos muestras, con la lente en su propia sección; si coincide con una muestra, la confirma.

Riesgo: mantener cada lente como plantilla, con su versión, su huella y su derivación por host (revisor-diseno.md:7-10, diseno:327-346); o darle el foco por prompt, que choca con el contrato de las cuatro tablas (revisor-diseno.md:172). Costo: el de hoy si canjea; una corrida más si suma.

### 2.3 Un refutador de los hallazgos graves

Qué sería: después de consolidar, una corrida de solo lectura que recibe los `CRITICAL`, los `WARNING` y los «a confirmar», cada uno con su `ruta:línea`, e intenta refutarlos contra el código. Devuelve, por hallazgo, «sostiene», «refutado» (con la evidencia y su control positivo) o «no decidible». No borra nada: anota al lado, y el usuario decide (revisar:163). Como un conflicto no se resuelve votando (revisar:15), el refutador tampoco vota.

Evidencia: poca.
- En SM-1 no hubo `CRITICAL` entre los contados (costo:70): un refutador solo de `CRITICAL` no habría corrido nunca.
- Hubo 24 `WARNING` y 16 «a confirmar» (costo:70), pero nadie anotó cuántos terminaron descartados.
- El revisor ya se refuta a sí mismo en los negativos (revisor-diseno.md:101-102), y `eval` ya tiene la pieza: un juez que verifica en el código (eval:60-65).

Efecto esperado: menos tiempo del usuario confirmando a mano y menos falsos positivos graves. Riesgo: que refute algo verdadero, o que un «refutado» se lea como resuelto. Costo: una corrida, solo cuando hay graves, con una entrada angosta.

### 2.4 El prompt

Hoy lleva las decisiones del ticket (revisar:116-117), porque tres corridas pidieron quitar algo ya aprobado (exp:311, revisar:122). El rechequeo suma los hallazgos de la ronda anterior (revisar:198), y dos rechequeos así cerraron bien (revisar:197).

| Cambio | Efecto | Riesgo |
|---|---|---|
| Los hallazgos anteriores en una revisión nueva | menos repetición | ancla: las corridas dejan de ser independientes, y la ceguera de `eval` existe por eso (eval:12) |
| El hermano del Paso 0 como puntero | menos búsqueda, que es el 24% del texto leído (costo:25) | «un hermano mal elegido justifica cualquier cosa» (revisor-diseno.md:151): va como candidato, nunca como dado |
| Lo que el triaje no ve | foco donde el instrumento es ciego | ninguno nuevo; es O6 del estudio de costo (costo:116) |

Es la palanca más barata y la más fácil de sobreajustar: un prompt no se ajusta mirando el caso sombra (eval:17).

### 2.5 El número de corridas

Lo midió el estudio de costo: con 2 corridas de diseño se pierde el 9% de los hallazgos y el 6% de los `WARNING`; con 1, el 27% y el 19% (costo:70). Desde la calidad, la tercera muestra idéntica es la corrida que menos rinde, y por eso es la que se canjea por una lente o paga un refutador. Una cuarta corrida no se sostiene con estos datos.

## 3. Cómo decidir sin adivinar

El sistema no se reescribe a partir de sus propios resultados (diseno:999). La verdad de terreno viene de afuera: la revisión de un líder o la ratificación del autor (eval:66-80), nunca un juez modelo solo.

1. **La base medida.** Con I28: tokens, turnos, minutos, modelo y effort por corrida, y el destino de cada hallazgo (costo:146-157). El modelo no cambia mientras se juntan las revisiones de la base (costo:182).
2. **Los casos.** De 3 a 5 unidades pasadas con verdad de terreno. Primero las de un líder. Si no hay, una verdad adjudicada (la unión de los dos brazos, juzgada a ciegas y ratificada por el autor), que sirve para descartar una variante, no para aceptarla. Los repos en el commit base y la verdad de terreno fuera del disco (eval:12-13, 24).
3. **Un cambio por comparación,** con el mismo número de corridas y la misma agregación (eval:16). `v1` es lo de hoy; `v2`, la variante.
4. **El pronóstico y el sí.** Cada corrida cuesta entre 115k y 256k tokens (costo:9), en el número que hoy se ve, que es un tercio del costo (costo:35). 2 brazos × 3 corridas × 4 casos son 24 corridas, entre 2,8M y 6,1M. Se corre por fases (eval:15).
5. **Correr, rescatar y auditar** (eval:26-47), y confirmar en la salida de `rescatar.py` el modelo de cada corrida.
6. **Puntuar con el juez ciego y ratificar** (eval:48-80). A mano, lo que `puntuar.py` no cuenta: cada hallazgo fuera de la verdad de terreno, como real, falso o «reabre una decisión», y la severidad de cada `ok`.
7. **Comparar** con `puntuar.py --brazo` (eval:81-89).

Qué registrar por brazo: puntaje medio, unión, `contra`, estables, conflictos, falsos positivos, `ok` en `CRITICAL` y `WARNING`, y tokens y minutos por corrida.

**Umbrales propuestos, para ratificar:**

| Variante | Se acepta si | De dónde sale el umbral |
|---|---|---|
| Revisores en Sonnet | (a) no pierde ningún `ok` ratificado `CRITICAL` o `WARNING` que tenía la unión de `v1`; (b) su puntaje medio es al menos el 91% del de `v1`; (c) `contra` y falsos positivos no suben; (d) medido, cuesta menos que dos corridas de `v1` | Se compara con lo que ya se puede hacer sin cambiar de modelo: `v1` con 2 corridas pierde el 9% (costo:70) y cuesta dos tercios. Ese brazo sale gratis, con `--brazo v1x2=<r1>,<r2>` sobre las mismas corridas. Si Sonnet × 3 no le gana a Opus × 2, conviene O6 del estudio de costo |
| Una lente como tercera corrida | la unión suma al menos un `ok` ratificado `CRITICAL` o `WARNING` en el total de los casos, sin perder ninguno y sin subir `contra` | a igual costo, la lente tiene que traer algo que la muestra no trae |
| Refutador | de lo que refuta, la ratificación da por falso al menos 9 de cada 10, y no refuta ningún `CRITICAL` o `WARNING` ratificado | un refutador que se equivoca en lo grave es peor que no tenerlo |

Con 3 a 5 casos, una diferencia de uno o dos `ok` es ruido. Por eso la regla mira un solo lado (no ser peor en lo grave) y el empate queda con lo de hoy, como «ante la duda, subí» (revisar:64). Lo que se decide en una instancia es de esa instancia; sube a los defaults del plugin cuando se repite en dos (diseno:1002).

## 4. El vínculo con el costo

| Del estudio de costo | De este | Cómo se tocan |
|---|---|---|
| O1, medir con el rendimiento (costo:142-163) | el instrumento de calidad | se juntan: es el mismo dato, y este suma el modelo y el effort por corrida, y el modelo en el recibo |
| «10 `completo` con el mismo modelo» (costo:182) | cambiar el modelo | chocan en el tiempo: primero la base y después el eval; un cambio de modelo en medio la invalida |
| O6, 2 corridas cuando escala el instrumento (costo:114-120) | la lente como tercera corrida | chocan: con 2 corridas no queda una tercera que canjear. Se deciden juntas: dos muestras siempre, y la lente o el refutador como la corrida que O6 quita o no |
| O7, bajar el piso con el resumen del ticket (costo:122-128) | el prompt | se juntan: las decisiones ya van en el prompt (revisar:116), que es lo que O7 arriesgaba |
| no lista el modelo | el modelo | palanca nueva: la mitad del precio por corrida sin quitar corridas, que se mide igual que las demás |

Lo que no contradigo: el estudio de costo dice que las tres corridas protegen contra la varianza (costo:68). Canjear la tercera deja dos muestras, que alcanzan para la frecuencia y los conflictos. Bajar a una no lo propongo.

## 5. Recomendación

1. **I28 con el rendimiento,** más el modelo y el effort de cada corrida, y el modelo en el recibo. Es la base de todo, y ya lo recomienda el estudio de costo (costo:168).
2. **Congelar de 3 a 5 casos sombra,** con un líder o ratificados por el autor.
3. **El eval del modelo primero,** porque no toca código: Opus × 3, Opus × 2 (la submuestra) y Sonnet × 3, con el effort fijado en los dos modelos. Si Sonnet pasa en los revisores de capa y no en el de diseño, la regla 5 se afloja a «por revisor».
4. **El eval de la lente,** después de decidir O6.
5. **El refutador,** solo si el paso 1 muestra que se descartan `WARNING` o «a confirmar» seguido. Propuesta: uno de cada cinco.
6. **El prompt:** ni los hallazgos anteriores en una revisión nueva, ni el hermano como dado.

La respuesta corta a «¿revisores en un modelo más barato?»: viable de mecánica hoy, en Claude Code y sin código; de calidad, no se sabe, y es lo que menos se nota cuando falla. Mi hipótesis, para probar y no para aplicar: el revisor de diseño se queda con el modelo de la sesión, y los de capa son los candidatos.

## 6. Preguntas para el autor

1. **¿Hay revisiones de un líder para congelar de 3 a 5 casos, o se acepta una verdad adjudicada?** Propuesta: las del líder para aceptar una variante; la adjudicada solo para descartarla.
2. **¿La regla 5 pasa a «el mismo modelo entre las corridas de un mismo revisor»?** Propuesta: sí, después del eval, porque la frecuencia solo se cuenta entre las corridas de diseño.
3. **¿El modelo de los revisores entra a la config?** Propuesta: no en las plantillas. Si el eval lo aprueba, una clave opcional que el orquestador pasa como alias en cada invocación, solo en Claude Code, y que el recibo anota.
4. **¿La tercera corrida de diseño se canjea por una lente o un refutador, en vez de sumar una cuarta?** Propuesta: se canjea, y se decide junto con O6.
