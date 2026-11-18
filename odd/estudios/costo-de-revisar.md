# Estudio: el costo de `/odd-ws:revisar` (I28, I34, I44)

Borrador para que el autor decida. No cambia código. Base: `main` en `0400cf8` (odd-ws 0.9.0), 2026-11-18.

Cómo leer las citas: `triaje.py`, `rescatar.py` y `recibo.py` están en `plugin/scripts/`; `SKILL.md` es `plugin/skills/revisar/SKILL.md`; `L#` es una entrada del Log de `odd/tasks/experiencia-de-uso.md`. «Medido» quiere decir sacado de la transcripción de SM-1 y de sus subagentes (el método está al final).

## 1. El problema

- Una corrida de `revisor-diseno` cuesta entre 115k y 256k tokens y entre 4 y 13 minutos activos (L35 da 155k a 254k para la primera mitad del ticket; medido en las 35 corridas).
- `completo` son 3 corridas de diseño más una por capa (`SKILL.md:70`). En SM-1, 11 de las 13 revisiones con revisores fueron `completo`, y las 35 corridas sumaron 6.48M tokens.
- Un cambio de 6 líneas en un `.yml` de CI costó cerca de 1M tokens (L42, G2).
- Un arreglo de 3 líneas en un test forzó `completo` y agotó el límite de 5 horas: la sesión quedó parada 87 minutos (L44, H6).
- Duele porque el costo no sigue al tamaño del cambio: cada corrida tiene un piso, y el modo lo multiplica por 3.

## 2. De dónde sale el costo

### 2.1 Dónde van los tokens de una corrida

Medido en las 35 corridas de `revisor-diseno` de SM-1. Ninguna corrida fue de capa: todos los archivos salieron `[sin capa]`.

| Parte | Cuánto |
|---|---|
| Antes de leer nada (sistema, herramientas, agente, `CLAUDE.md` cargados) | 38k a 43k tokens de contexto en el primer turno |
| Leer el diff | 25% del texto que devuelven las herramientas |
| Buscar hermanos y consumidores (`Grep`, `Glob`) | 24% |
| Leer código (hermanos y consumidores) | 23% |
| Leer docs y `CLAUDE.md` | 16% |
| Leer el `CLAUDE.md` del ticket (lo pide el prompt, `SKILL.md:112`) | 11% |
| Escribir: razonamiento y reporte | mediana de 55.7k tokens de salida; el reporte, mediana de 20.7k caracteres |
| Releer el contexto en cada turno | mediana de 32 turnos y 3.8M tokens leídos de caché por corrida |
| El reporte en el orquestador | entra entero: 14k a 27k caracteres cada uno, unos 85k tokens en cinco horas (`odd/roadmap.md:70`, I35) |

**El piso.** Las corridas con el diff más chico (692 a 864 caracteres) costaron entre 115k y 151k tokens; las del diff más grande, entre 241k y 256k (medido). Una corrida sobre un diff mínimo cuesta casi la mitad que la más cara del ticket. Por eso el cambio de 6 líneas de CI fueron un `completo` de 415k, un rechequeo de 117k y, después de la corrección, otro `completo` de 472k (con 4 docs sumados): 1.00M (medido, L42).

**Qué número es «tokens».** El que Claude Code informa por corrida (`subagent_tokens`, el de L35) es el contexto final más la última salida: en la primera corrida de diseño de SM-1, 228 237 = 215 820 de contexto final + 12 417 de la última salida (medido). No cuenta lo que se relee en cada turno ni toda la salida. A precio de lista de API (Opus 5.5: entrada 4, escritura de caché unos 5, lectura de caché 0.20 y salida 20 USD por millón), las 35 corridas suman unos 96 USD, con este reparto: 31% escribir el contexto, 31% releerlo, 38% salida (medido). El precio sirve solo como unidad común: el plan no publica cómo pesa cada parte en su límite. La consecuencia: el número que hoy se ve es un tercio del costo, y una corrida con menos turnos es más barata aunque termine con el mismo contexto.

### 2.2 Por qué un cambio que no es SQL cae en `completo`

El camino de `triaje.py` para un `.mjs` modificado, con una capa declarada para él:

1. No es doc (`DOC_EXT` son `.md`, `.txt` y `.rst`, `triaje.py:23`), así que entra a `activos` (`triaje.py:499`).
2. `_lenguaje` lo busca en `LENGUAJES = {".sql": tsql}` y devuelve `None` (`triaje.py:27`, `triaje.py:96-97`).
3. `contrato` y los tipos de `dinero` no tienen biblioteca: quedan en negativa (`triaje.py:541`, `triaje.py:549-556`, `triaje.py:566-568`), y la salida lo declara entre lo que no detecta (`triaje.py:41`).
4. `consumidores`, en cambio, queda **inválida**: «sin biblioteca de señales para .mjs, el conteo no vale» (`triaje.py:417-420`).
5. Una señal que no es negativa da `completo` (`triaje.py:511-513`), y `completo` son `3 + <capas>` corridas (`SKILL.md:70`, `SKILL.md:98`).

Hoy solo `.sql` tiene biblioteca (`Doc/diseno.md:597`), así que en un repo JS, TS o Python todo cambio de código va a `completo` (`odd/roadmap.md:79`, I44).

**Lo que mostró SM-1: escalaban dos señales, no una.** El triaje del `.yml` de CI dio `consumidores` inválida **y** `capas` positiva, por «archivo(s) sin capa reconocida (no se puede triar)» (`triaje.py:578-580`). Lo mismo cada triaje `completo` que quedó en la transcripción, el del test incluido (medido). Arreglar solo `consumidores` (I44) o solo los de configuración (I34) no habría bajado el modo de ninguna revisión de SM-1: hace falta además que esos archivos tengan capa. El doctor ya lo avisa con `capas-cobertura` (`Doc/uso.md:130`, `Doc/diseno.md:1019`), pero declarar la capa suma la corrida de su revisor.

## 3. La red de seguridad que no se puede perder

En palabras del código:

- «**Un negativo no es evidencia** hasta probar que el instrumento sabe decir que sí. Toda regla que bloquea tiene un control positivo.» (`Doc/diseno.md:14`)
- «Las señales **solo escalan**: cada una sale positiva, negativa o inválida (el instrumento no pudo medir), y «rápido» sale únicamente con todas en negativo.» (`Doc/diseno.md:589`)
- «Un falso positivo solo cuesta una revisión de más; un falso negativo cuesta un hallazgo que llega al líder. Ante la duda, subí. No bajes el modo por tu cuenta.» (`SKILL.md:64`)
- Varias corridas «sirven para protegerse de la corrida mala y para **mostrar los conflictos**» (`SKILL.md:15`).

| Regla que escala | Qué protege | Qué se colaría si se afloja |
|---|---|---|
| `consumidores` inválida sin biblioteca (`triaje.py:417-420`) | el invariante: un objeto con 2 o más consumidores no cambia de forma sin que se note (`triaje.py:21`, `Doc/diseno.md:596`) | una función exportada de JS que pasa de devolver texto a devolver un objeto, usada por tres scripts; un `conftest.py` o un `test-utils` que usan veinte tests |
| control positivo: sin la definición del objeto no hay conteo (`triaje.py:450-454`) | que un grep mudo no pase por «cero consumidores» | un nombre que el extractor no reconoce y da cero |
| más de 20 objetos, o un repo sin `origin/HEAD` (`triaje.py:428-433`) | que un conteo parcial no pase por completo | un cambio grande contado a medias |
| `capas`: más de una capa (`triaje.py:576-577`) | el contrato entre capas | un campo nuevo en un SP que la capa de arriba lee mal |
| `capas`: archivo sin capa (`triaje.py:578-580`) | que lo que ningún revisor de capa lee no pase con una sola mirada (`SKILL.md:69`) | un `package.json` que cambia `exports` o una dependencia; un `.yml` de CI que quita un job o le pone `continue-on-error` |
| el cambio va a un líder (`SKILL.md:65`) | lo que el triaje no ve del contexto | un cambio que el líder revisa con otro criterio |
| tres corridas de diseño en `completo` (`Doc/diseno.md:908`) | la varianza entre corridas (`SKILL.md:14-15`) | un hallazgo que solo vio una corrida |

**Lo que compran las tres corridas.** En los 7 consolidados de `completo` de SM-1 que traen la frecuencia por hallazgo, hubo 61 hallazgos: 28 en 3/3, 17 en 2/3 y 16 en 1/3. De los 24 `WARNING`, 4 fueron 1/3 y 6 fueron 2/3. No hubo `CRITICAL` entre los contados (medido). Si de las tres corridas se toma una al azar, se pierden en promedio 16 × 2/3 + 17 × 1/3 = 16.3 hallazgos (27%) y 4.7 `WARNING` (19%). Si se toman dos, solo se pierde un 1/3 cuando las dos elegidas son las que no lo vieron: 16 × 1/3 = 5.3 hallazgos (9%) y 1.3 `WARNING` (6%). Además, la consolidación por frecuencia sacó a la luz una regresión real (L35). La muestra es chica y sin `CRITICAL`, y no ve lo que ninguna de las tres encontró.

## 4. Opciones

### O1. Medir el costo real (I28)

- **Qué cambia:** `rescatar.py` lee el `usage` de cada mensaje del `.jsonl` (hoy `extraer_corrida` solo lee los bloques, `rescatar.py:55-103`) y lo guarda con cada corrida; el anuncio del paso 2.5 cita la última medida junto a las corridas (`SKILL.md:70`). El detalle, en la sección 5.
- **Ahorro:** ninguno directo. Es lo que deja estimar el de las demás.
- **Riesgo:** el formato de la transcripción no es una API estable (`Doc/diseno.md:607`); un host sin esa transcripción no da el dato.
- **Cómo se detecta la falla:** una corrida sin `usage` sale «sin medida», y el anuncio vuelve a corridas sin cifras, como hoy.
- **Tamaño:** chico. Unas 50 líneas en `rescatar.py`, sus tests y dos párrafos de la skill.

### O2. Los de configuración pesan como `rapido` (I34, primera forma)

- **Qué cambia:** `.yml`, `.json` y `.toml` no invalidan `consumidores` ni cuentan como «sin capa»; sí siguen mirando `efecto`, `dinero` y `migracion`.
- **Ahorro:** en el caso de CI, 415k + 117k + 472k = 1.00M pasa a 415k / 3 + 117k + 472k / 3 = 412k: 591k menos (59%). En SM-1 entero, el 9%.
- **Riesgo:** justo esos archivos deciden qué se verifica y qué se publica: `package.json` (`exports`, dependencias, `scripts`), los workflows de CI, `tsconfig.json`. Una clave de un JSON que el código lee por texto ya figura entre lo que no se detecta (`triaje.py:38`).
- **Cómo se detecta la falla:** un CI roto después del merge, o un hallazgo en ese archivo que la revisión siguiente marca como «ya estaba antes del cambio» (`SKILL.md:157`).
- **Tamaño:** chico. Unas 20 líneas en `triaje.py` y sus tests.

### O3. El usuario baja el modo y el motivo queda en el recibo (I34, segunda forma)

- **Qué cambia:** el triaje sigue proponiendo lo mismo. El usuario puede bajar un escalón (`completo` a `rapido`) con un motivo; `recibo.py --write` guarda el modo propuesto y el motivo junto al modo de verdad (`recibo.py:17`, `recibo.py:506`). El agente sigue sin poder bajarlo por su cuenta (`SKILL.md:64`).
- **Ahorro:** el de O2 o el de O4 en los casos que el usuario elige: 591k en el de CI, 246k en el del test (368k a 123k, 67% menos).
- **Riesgo:** que bajar se vuelva un reflejo. Con límites: nunca a `0` con código, nunca si va a un líder, nunca con una positiva de verdad (`efecto`, `dinero`, `migracion`, `contrato`, `consumidores` con 2 o más, más de una capa).
- **Cómo se detecta la falla:** el recibo dice qué unidades se revisaron por debajo de lo propuesto, y se pueden cruzar con los hallazgos «ya estaba antes del cambio» de la unidad siguiente.
- **Tamaño:** chico. Dos opciones nuevas y su validación en `recibo.py`, un campo opcional en el recibo, tests y el texto de la skill.

### O4. Sin biblioteca, los consumidores van a «no detectable» (I44, primera forma)

- **Qué cambia:** `triaje.py:417-420` deja la señal en negativa para ese archivo y suma el motivo a lo que no detecta, como ya hacen `contrato` y `dinero` (`triaje.py:41`).
- **Ahorro:** alto donde se aplica: todo cambio de código de una sola capa en un lenguaje sin biblioteca pasa de 3 corridas a 1 (67% menos por revisión). En SM-1, cero, porque `capas` también escalaba (sección 2.2).
- **Riesgo:** contradice el principio 4 (`Doc/diseno.md:14`): un negativo sin instrumento. El primer caso de la tabla de la sección 3 pasa con una sola corrida, que según SM-1 pierde uno de cada cuatro hallazgos.
- **Cómo se detecta la falla:** no se detecta en el momento; solo como escape, después.
- **Tamaño:** muy chico. Unas 5 líneas y sus tests.

### O5. Contar los nombres exportados, y los tests sin consumidores (I44, segunda forma)

- **Qué cambia:** una biblioteca chica por lenguaje (JS/TS, Python) que extrae los nombres exportados y los cuenta con el mismo `git grep` y el mismo control positivo que T-SQL (`triaje.py:436-459`). Un archivo de test por ruta (`*.test.*`, `test_*.py`, `*_test.*`) no tiene consumidores, salvo los que comparten fixtures (`conftest.py`, `*test-utils*`, `fixtures/`).
- **Ahorro:** el de O4 cuando el conteo da menos de 2 y nada más escala; en el del test, 246k (67%).
- **Riesgo:** no ve los re-exports, el `export default` consumido con otro nombre ni el acceso dinámico; hay que declararlo entre lo que no detecta. El control positivo atrapa una definición que no aparece, no un nombre que nunca se extrajo.
- **Cómo se detecta la falla:** el control positivo deja la señal inválida, como hoy; lo que no ve, solo como escape.
- **Tamaño:** mediano a grande, por lenguaje. `tsql.py` tiene 394 líneas, aunque gran parte es propia de T-SQL.

### O6. Una inválida pide 2 corridas; una positiva, 3 (opción nueva)

- **Qué cambia:** el triaje separa lo que escala por un límite del instrumento (inválida, archivo sin capa) de lo que escala por un riesgo visto (una positiva, más de una capa, el líder). Lo primero da `completo` con 2 corridas de diseño, y el prompt nombra lo que el triaje no pudo medir para que el revisor lo cuente a mano. Sin modo nuevo: el recibo ya guarda el modo y los revisores, y la consolidación sobre k/2 ya existe para una corrida cortada (`SKILL.md:142`).
- **Ahorro:** un tercio de cada revisión que escala solo por el instrumento. En SM-1 fueron las 11: 6.24M pasan a 4.16M, 2.08M menos (32% del ticket).
- **Riesgo:** con la muestra de SM-1, 2 corridas pierden el 9% de los hallazgos y el 6% de los `WARNING` que vieron 3 (sección 3); 1 corrida pierde el 27% y el 19%.
- **Cómo se detecta la falla:** la frecuencia 1/2 marca lo «a confirmar», igual que 1/3; si esos hallazgos terminan aceptados seguido, falta la tercera.
- **Tamaño:** mediano. Una clave en la salida del triaje, el texto de las secciones 2, 4 y 7 de la skill, y tests.

### O7. Bajar el piso de cada corrida (opción nueva)

- **Qué cambia:** el revisor recibe el resumen del ticket (el de T14, L38) y la ruta del archivo entero, en vez de leerlo todo. Aparte, con I35, el reporte deja de entrar entero al orquestador.
- **Ahorro:** bajo. El ticket es el 11% del texto leído; del orden del 5% de cada corrida, más lo que deja de releerse. I35 ahorra en el orquestador, no en la corrida.
- **Riesgo:** que el revisor no lea el Paso 0 o una decisión; por eso el prompt pide leer el `CLAUDE.md` del disco (`SKILL.md:112`).
- **Cómo se detecta la falla:** un hallazgo que reabre una decisión del ticket (`SKILL.md:158`).
- **Tamaño:** chico, solo texto del prompt.

### Resumen

| Opción | Ahorro | Seguridad que conserva | Tamaño |
|---|---|---|---|
| O1 Medir (I28) | ninguno directo | toda | chico |
| O2 Configuración a `rapido` (I34) | medio en esos casos (59% en el de CI) | media | chico |
| O3 El usuario baja con motivo (I34) | el que el usuario elige | alta: el default no cambia y queda escrito | chico |
| O4 «No detectable» (I44) | alto donde aplica, cero en SM-1 | baja: rompe el principio 4 | muy chico |
| O5 Nombres exportados y tests (I44) | medio a alto | media a alta: mantiene el control positivo | mediano a grande |
| O6 Inválida pide 2 corridas | medio: un tercio (32% de SM-1) | media a alta | mediano |
| O7 Bajar el piso | bajo | alta | chico |

## 5. Lo que se mide primero

I28 es la medición. Sin ella, las cifras de este estudio salen de un solo ticket.

**Qué registrar por corrida**, desde el `.jsonl` del subagente (cada mensaje trae `usage`; Claude Code repite el mismo mensaje en varias líneas, así que se cuenta una vez por id):

| Campo | Para qué |
|---|---|
| `turnos` | explica las relecturas |
| `contexto_inicial`, `contexto_final` | el piso, y el número que hoy ve el usuario |
| `salida`, `cache_escrita`, `cache_leida` | el costo que el número de hoy no muestra |
| `inicio`, `fin`, `pausa_mayor` | separa el trabajo de una espera por límite: en el test de SM-1, 92 minutos de reloj y unos 5 activos (medido) |

**Dónde:** en `corridas/<nombre>.lecturas.json`, que ya guarda el `meta` de la corrida (`rescatar.py:122-134`), y un `corridas/costo.json` por revisión con el modo, los motivos del triaje, las corridas y las líneas del diff. El anuncio lee el `costo.json` más nuevo del ticket, o de la instancia si el ticket no tiene; sin ninguno, anuncia corridas como hoy.

**El rendimiento, además del costo:** por revisión, cuántos hallazgos salieron 3/3, 2/3 y 1/3, con su severidad y su destino (corregido, derivado o descartado). Puede ser una línea fija en `consolidado.md`; el recibo ya guarda `estado` y `derivados`.

**Lo que espera esos datos:**

- O6 espera la tasa de hallazgos 1/3 que se aceptan, sobre todo los `WARNING` y `CRITICAL`.
- O2, O4 y O5 esperan qué parte de los `completo` escala solo por el instrumento (inválida o sin capa) y qué rinden esos frente a los que escalan por una positiva.
- O7 espera el reparto de cada corrida: contexto inicial, lectura del ticket y turnos.
- O1 y O3 no esperan nada.

## 6. Recomendación

1. **O1 (I28), con el rendimiento.** Es chico y es la base de todo lo demás.
2. **O3.** Da alivio ya sin tocar el default: el caso de CI y el del test se bajan con un motivo escrito, y cada bajada queda como evidencia.
3. **Las capas que faltan.** Que `abrir` y el triaje repitan el aviso de `capas-cobertura` cuando el único motivo es «sin capa». Es configuración, no aflojar el motor.
4. **Con unas 10 revisiones `completo` medidas, decidir O6**, y O5 para el lenguaje que más se revisa en la instancia.
5. **No hacer O2 ni O4.** O2 abarata justo los archivos que deciden qué se verifica y qué se publica, y O3 cubre el caso de CI. O4 rompe el principio 4, y O5 logra lo mismo con control positivo.

El tradeoff, sin vueltas: cada corrida de diseño que se quita ahorra un tercio del costo de esa revisión y, con lo que mostró SM-1, pierde cerca de 1 de cada 11 hallazgos si quedan 2, o 1 de cada 4 si queda 1. Los datos de SM-1 no traen un `CRITICAL`, así que no dicen qué pasa con lo más grave.

## 7. Preguntas para el autor

1. **¿I28 mide también el rendimiento (frecuencia, severidad y destino de cada hallazgo), no solo tokens y minutos?** Propuesta: sí; sin eso, O6 se decide a ciegas.
2. **¿El usuario puede bajar el modo (O3), y hasta dónde?** Propuesta: un escalón, de `completo` a `rapido`, con motivo en el recibo; nunca a `0` con código, nunca si va a un líder y nunca con una positiva de verdad.
3. **¿I34 se cierra con O3, e I44 se rehace como O5 en vez de «no detectable»?** Propuesta: sí, por la tabla de la sección 3 y el principio 4.
4. **¿«Sin capa» es un límite del instrumento (como una inválida) o un riesgo visto?** Propuesta: un límite; se arregla declarando la capa y, con O6, pide 2 corridas y no 3.
5. **¿Cuántas revisiones medidas antes de decidir O6?** Propuesta: 10 `completo` con el mismo modelo, o el próximo ticket entero, lo que llegue primero.

## Cómo se midió

- **Costo:** las 35 corridas de `revisor-diseno` de la sesión de SM-1 (`agent-<id>.jsonl` y su `.meta.json`). Por mensaje del asistente, contado una vez por id: `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` y `output_tokens`. Los tokens y minutos por corrida son los del aviso de fin de cada subagente en la transcripción principal (`subagent_tokens`, `duration_ms`).
- **Lecturas:** el texto de cada resultado de herramienta, por herramienta y por tipo de ruta (el diff de `entrada/`, el ticket, docs y `CLAUDE.md`, código). Es una partición aproximada: en las unidades que cambiaban docs, leer el cambio y leer docs se mezclan.
- **Modos:** las salidas del triaje en la transcripción principal. SM-1 corría la `0.7.0` (L42); las líneas citadas de `triaje.py` dan lo mismo en la `0.9.0` para estas señales.
- **Frecuencias:** las tablas de hallazgos de 7 de los 14 consolidados del ticket, los que traen la frecuencia por hallazgo.
- **La 0.9.0 ya ahorra una parte:** un rechequeo ahora es de 1 corrida (L43, T17). Las tres rondas de corrección de SM-1 que corrieron con 3 (2.04M) habrían costado unos 0.68M, si cada una calificaba como rechequeo.
