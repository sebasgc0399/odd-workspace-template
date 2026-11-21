# Las reglas empiezan observando (I64)

Objetivo: que una regla por capa bloquee solo después de calibrarse, y que una disputada vuelva a aviso, como prometen D2 y D6.3 del diseño. No aplica al guard de comandos destructivos.
Rama: `feat/reglas-observan`, en `D:/Project/odd-ws-wt/i64`, desde la `0.11.0`. Entrega: tres unidades con un commit cada una (T1 el modo efectivo y la calibración de la capa, T2 las disputas, T3 los paquetes); el push y la publicación, solo con autorización del autor. Sale en una versión menor.
Pruebas: `python plugin/scripts/<script>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`.

## Specs

Origen: la I64 del roadmap, tal cual: «Las reglas por capa empiezan observando: una regla bloquea solo después de calibrarse, y una disputada vuelve a aviso.» Y el diseño, tal cual: D2, «Qué bloquea lo decide la calibración: una regla bloquea solo si atrapa su defecto sembrado **y** da 0 aciertos en el corpus.»; D6.3, «Las **disputas** de bloqueos quedan en `.claude/registro/`; una regla disputada vuelve a `aviso` hasta que se arregle su chequeo.» El autor aprobó el diseño que se le mostró, con el corte duro (L1).

- **S1** (cuándo bloquea). Un hallazgo bloquea solo si se cumplen las cinco condiciones:
  1. el módulo pide `bloqueo`, que pasa a ser un techo: la calibración permite bloquear, pero no obliga, así que una regla de estilo puede avisar para siempre;
  2. la regla declara su defecto sembrado;
  3. la calibración guardada atrapó ese defecto y dio 0 aciertos que piden bloqueo en el corpus;
  4. el módulo no cambió desde la calibración;
  5. no hay una disputa abierta para su ID.

  Si falta alguna, el hallazgo llega como `aviso`, con el motivo (`sin calibrar`, `calibración vieja` o `disputada`) y el comando a correr. El modo efectivo se calcula al correr, en un solo punto (`verificar_capa._verificar_archivo`), así que vale para PostToolUse, `writer_stop` y `revisar_turno` en los tres hosts, sin tocar los adaptadores ni el shim. No aplica a `guard_comandos.py`.
- **S2** (el defecto sembrado). Un atributo opcional `sembrado` en cada objeto de `REGLAS`: un texto que la regla tiene que atrapar. Una regla sin `sembrado`, o un módulo sin `REGLAS`, no puede bloquear.
- **S3** (la calibración). `reglas.py --calibrar <capa> <carpeta> --guardar` escribe `.claude/registro/calibracion.json`, versionado. Por regla guarda la huella del módulo, si atrapó su sembrado, los aciertos, los archivos del corpus, el corpus (`repo`, `commit` y `ruta`, nunca una ruta absoluta) y la fecha. Sin `--guardar`, la salida de `--calibrar` no cambia ni un byte. `--guardar` no escribe si hubo errores (exit 1) o si el módulo no declara `REGLAS` (exit 2). Un corpus vacío se permite, con `archivos_del_corpus: 0` a la vista: un proyecto `propio` sin corpus también puede bloquear.
- **S4** (la huella). Es el sha256 del módulo, con CRLF pasado a LF, como `odd_ws.paquetes.huella`. Cualquier cambio en el archivo del módulo invalida su calibración (estricto); para un paquete, la huella de su lock.
- **S5** (las disputas). Un archivo `.claude/registro/disputas/<ID>.md` por disputa abierta, con quién la abre, qué bloqueo y por qué. Mientras exista, la regla avisa. Se cierra borrando el archivo, en el commit que arregla el chequeo; como la huella cambia, la regla también pide recalibrar. La escribe el usuario, o el agente con su sí: ningún script disputa solo (D6).
- **S6** (los paquetes). Los paquetes de reglas entran igual, con la huella de su lock: `--guardar` corre también los paquetes de la capa.
- **S7** (el registro roto). Con `calibracion.json` ilegible o con otra forma, ninguna regla bloquea, y el aviso lo dice.
- **S8** (el corte duro). Al actualizar, todo bloqueo de una capa o de un paquete pasa a aviso hasta calibrar. El CHANGELOG y `Doc/actualizar.md` dan el paso a paso: sumar `sembrado` a cada regla que deba bloquear, correr `reglas.py --calibrar <capa> <carpeta> --guardar` y commitear `.claude/registro/`. El paso 5 de la skill `cerrar`, que gradúa una regla a chequeo, pide su sembrado y su calibración.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T1 | S1, S2, S3, S4, S7, S8 | El modo efectivo y la calibración de la capa: `odd_ws/calibracion.py`, `reglas.py --guardar`, `verificar_capa`, `writer_stop`, la plantilla de la suite de reglas y los docs | delegada a un writer, en paralelo con la I62 en otro worktree. Risk: item 2 (los guards dejan de bloquear hasta calibrar) y item 6 (si la huella falla en silencio, ningún test lo vería en una instancia real); lleva verificador, al final de la feature (L3) | hecha (L3, L4) | `bf6cc5b` |
| T2 | S5 | Las disputas en `.claude/registro/disputas/` | delegada junto con T3, en un writer y un commit (L5) | hecha (L5) | `ebe8bf6` |
| T3 | S6 | Los paquetes con la huella de su lock | delegada junto con T2 (L5) | hecha (L5) | `ebe8bf6` |
| T4 | todas | El verificador independiente de la feature y el cierre | inline | verificador: un bloqueante y cuatro avisos, corregidos en un lote (L6); falta el rechequeo | |

## Log

- **L1** (2026-11-20) El autor aprobó el diseño que se le mostró (las cinco condiciones, el modo como techo, la calibración en `.claude/registro/calibracion.json`, las disputas como archivos, los paquetes y el corte duro) con estas palabras, tal cual: «Vale, no hay problema de momento solo son si mucho 3 o 4 personas probando que saben que es un proyecto nuevo asi que hagamos los ajustes necesarios para que quede bien para cuando haya mas usuarios».
- **L2** (2026-11-20) El mapa del explorador, de solo lectura, sobre la `0.10.1`.
  - Hoy el modo lo pone cada hallazgo del módulo de la instancia. Ni `matriz.csv` ni el lock de los paquetes lo guardan.
  - Deciden bloquear `verificar_capa._salida` (`:196-205`), `writer_stop._chequear` y `revisar_turno._chequear`, y los tres pasan por `verificar_capa.verificar_archivo`.
  - `reglas.py --calibrar` (`:99-136`) solo cuenta aciertos, no persiste nada e ignora los paquetes. No existe el concepto de defecto sembrado, y ningún script lee ni escribe `.claude/registro/`.
  - Detalle visto: `_salida` lee `h["modo"]` sin `.get`, y un hallazgo sin `modo` da `KeyError`, con el hook en silencio. Se cubre en T1, porque ese punto pasa a calcular el modo efectivo.
  - Decisiones tomadas con las recomendadas: invalidación estricta por la huella del módulo (P4), cierre explícito de una disputa (P5), corpus vacío permitido (P6) y versión menor (P7).
  - Riesgos anotados:
    - editar el módulo degrada todas las reglas de la capa;
    - la huella no ve los helpers que importa el módulo;
    - la plantilla de la suite no llega a las instancias que ya existen.
- **L3** (2026-11-20) T1, escrita por un writer en `i64`. Son unas 1.290 líneas, la mayoría tests y docs (el estimado era 450), más el parche del padre al shim.
  - **El modo efectivo:**
    - `odd_ws/calibracion.py` es nuevo. `_verificar_archivo` termina en `calibracion.aplicar(grupos, raiz, repos)`, y `_salida`, `writer_stop` y `revisar_turno` solo leen el `modo` resultante.
    - El motivo viaja en la clave `aviso_por`, que se le quita al módulo para que no pueda falsearlo.
    - Un hallazgo sin `modo` pasa a aviso con el motivo `modo inválido`, en vez de callar el hook.
  - **`--guardar`** escribe `calibracion.json` de forma atómica y reemplaza solo la capa que calibra. Con el registro roto sale con 2.
  - **Decisiones del writer, que el padre acepta:**
    - Un motivo más, `no pasó la calibración`, para una regla calibrada que no atrapó su sembrado o tuvo aciertos.
    - Dos contadores, `aciertos` y `aciertos_en_bloqueo`; decide el segundo.
    - El `sembrado` también se chequea al correr el hook, así que un registro editado a mano no hace bloquear a una regla sin sembrado.
    - El comando del aviso va sin la ruta del plugin.
  - **Los puntos de extensión:** un grupo de un paquete lleva `fuente=None` y conserva su modo hasta T3, y T2 suma `disputas` al `Registro` y un chequeo en `_motivo`.
  - **Las suites:** `calibracion` 18/18, `reglas` 40/40, `verificar_capa` 114/114, `writer_stop` 58/58, `revisar_turno` 31/31, `pi.tests` 68/68 y `capas` 16/16. Rojo observado en cada regla. El padre repitió `calibracion`: 18/18.
  - **El shim:** `plugin/shim/pi.test.ts` quedaba fuera de la superficie, y daba 64/68 porque su fixture esperaba que una regla sin calibrar bloqueara. El padre aplicó el parche que el writer probó en un scratch, `REGLAS` con `sembrado` y la calibración del fixture, y quedó 68/68.
  - **El diferencial contra `2ef0c3b`** dio iguales `--calibrar` sin `--guardar`, los errores de uso y los avisos en los tres hosts. Distinto, como se pidió: un `bloqueo` sin calibrar llega como aviso, un hallazgo sin `modo` avisa en vez de callar, y la ayuda suma `[--guardar]`.
  - **El verificador:** para cuidar tokens, uno solo al final de la feature, que cubra T1 (la de alto riesgo) junto con T2 y T3.
  - **Scratch del writer, a borrar a mano:** `%TEMP%	mp.eGB2BNP0t7`.
- **L4** (2026-11-20) Un incidente en el primer intento de commitear T1.
  - **Qué pasó:** el pre-commit exporta `GIT_DIR` y `GIT_INDEX_FILE`, y el helper nuevo `git_de_prueba` de `reglas.tests.py` corría git heredándolas. El `git init/add/commit -m base` de una fixture cayó en la rama real (el commit basura `830d0fa`) y reemplazó el índice. El working tree quedó intacto, y la suite salió en rojo.
  - **La recuperación, sin destruir nada:** `git update-ref` de la rama de `830d0fa` a `2ef0c3b`, verificando el valor viejo, y `git read-tree HEAD` para rearmar el índice sin tocar archivos.
  - **El arreglo:** `git_de_prueba` pasa `env=M.entorno_git()`, como el código de producción (`reglas.py:110`). Un test de regresión pone `GIT_DIR`, `GIT_INDEX_FILE` y `GIT_WORK_TREE` apuntando a un repo de afuera y comprueba que el commit de la fixture no cae ahí. Rojo antes del arreglo, verde después.
  - **La comprobación:** `reglas` dio 41/41 con el entorno del hook. Las demás suites de T1 (`verificar_capa`, `writer_stop`, `revisar_turno`, `calibracion`, `capas` y `pi.tests`) dieron verde con `GIT_DIR` apuntando a un repo señuelo, que quedó intacto.
  - **La lección:** todo helper de test que corre git usa `entorno_git()`, porque las suites corren dentro del pre-commit. Se le avisó al writer de T2 de la I62.
- **L5** (2026-11-20) T2 y T3 juntas, porque son chicas y tocan los mismos archivos: un writer y un solo commit. Son unas +700/−117, con unas 215/−63 de código.
  - **Las disputas (S5):** `Registro` suma `disputas` y `disputas_ilegibles`. `disputas(raiz)` lista los `.md` de `.claude/registro/disputas/` sin leerlos ni escribir nada, y compara los ID sin distinguir mayúsculas. `_motivo` chequea primero si la carpeta se puede leer y después si la regla está disputada.
  - **Los paquetes (S6):** `Fuente` suma `paquete`, y `fuente_del_paquete` usa la huella del lock de `odd_ws.paquetes`. `calibracion.json` suma un `paquetes` opcional, que se escribe solo si no está vacío, así que un registro solo de capas queda igual que en T1. `--guardar` calibra también los paquetes activos de la capa, y sin `--guardar` la salida no cambia.
  - **Decisiones del writer, que el padre acepta:**
    - Un hallazgo sin fuente cae en aviso `sin calibrar`, en lugar de conservar su modo. Cierra un bypass, y el test de T1 que decía lo contrario se reescribió.
    - Una capa con paquetes y sin módulo propio se puede calibrar.
    - `--guardar` sale con 2 si el lock está roto o hay prefijos que chocan.
    - Un paquete cuya carpeta no coincide con su lock es error.
    - Un paquete sin `REGLAS` se saltea con aviso.
    - Un `sys.exit` dentro de un paquete se informa como error.
    - Los avisos de un paquete dicen que se arregla en su repo, con una etiqueta nueva.
    - La línea del veredicto dice si la regla quedó disputada.
  - **Las suites:** `calibracion` 29/29, `reglas` 49/49, `verificar_capa` 119/119, `odd_ws/paquetes` 23/23, `paquetes` 17/17, `writer_stop` 58/58, `revisar_turno` 31/31, `pi.tests` 68/68 y el shim 68/68. Rojo observado en cada regla.
  - **El señuelo:** las nueve suites dieron verde con `GIT_DIR`, `GIT_INDEX_FILE` y `GIT_WORK_TREE` apuntando a un repo de prueba, que quedó intacto. La rama siguió en `bf6cc5b`.
  - **El diferencial contra `bf6cc5b`:** distinto solo en lo pedido. Un paquete en bloqueo sin calibrar ahora avisa, y una disputa abierta avisa.
  - **Un defecto de T1 que reportó el writer, y que el padre arregló:** un hallazgo en bloqueo con un `id` que no es texto (una lista) tiraba `TypeError` en `_motivo`. `verificar_capa.correr` se tragaba la excepción y el archivo entero quedaba en silencio, cuando en la `0.11.0` ese hallazgo bloqueaba. Ahora cae en aviso con el motivo `id inválido`, como un `modo` inválido. Rojo observado con la misma `TypeError`; después, `calibracion` 30/30 y `verificar_capa` 119/119.
  - **Pendiente para la entrega:** el CHANGELOG, con el corte duro que ahora cubre también los paquetes, las disputas y las capas que solo tienen paquetes.
  - **Scratch del writer, a borrar a mano:** `%TEMP%	mp.lgf63efl8F`.
- **L6** (2026-11-21) El verificador independiente de la feature (`2ef0c3b..ebe8bf6`) y su lote de corrección.
  - **El veredicto:** PASS de S1 a S7; S8 parcial porque falta el CHANGELOG, que va con la entrega.
  - **El bloqueante:** una regla filtrada por ruta (por ejemplo, solo `Migrations/`) o por una extensión que no es la primera de la capa nunca podía atrapar su sembrado, porque `reglas._atrapa` lo pasaba como un archivo `sembrado<primera extensión>` en la raíz. Quedaba para siempre en «no pasó la calibración», con un mensaje que engaña. En la `0.11.0` esas reglas bloqueaban. Lo vio en una instancia de prueba real.
  - **La decisión del padre:** el `sembrado` puede ser un texto, como antes, o un dict `{"ruta", "texto"}`, que se pasa como un archivo en esa ruta relativa. Cubre los filtros por carpeta, por extensión y por nombre de archivo. Probar cada extensión no resolvía las rutas.
  - **Los avisos que callaban el hook donde antes bloqueaba,** corregidos en el mismo lote:
    - un `calibracion.json` muy anidado tiraba `RecursionError` en `cargar`;
    - un `REGLAS` que tira `SystemExit` caía en `sembrados`, y en un paquete también callaba a la capa. El writer encontró y cerró el mismo hueco en `reglas._calibrar_paquete`.
  - **Los docs:** el motivo `id inválido` en las listas, la salvedad de los hooks de cierre en `Doc/actualizar.md`, y la forma con dict en `Doc/capas-y-reglas.md`, `Doc/actualizar.md`, `Doc/diseno.md` y la skill `cerrar`.
  - **Las suites del lote:** `calibracion` 33/33, `reglas` 55/55, `verificar_capa` 123/123, `odd_ws/paquetes` 23/23, `paquetes` 17/17, `writer_stop` 58/58, `revisar_turno` 31/31, `bootstrap_reglas` 22/22 y el shim 68/68. Rojo observado en cada punto. El padre repitió `calibracion`.
  - **El señuelo y el diferencial:** el señuelo quedó intacto, y el diferencial contra `ebe8bf6`, en 34 casos, solo cambia en lo pedido.
  - **Seguimientos, sin cambio en esta versión:**
    - un dict de sembrado inválido da el mismo motivo que no declararlo;
    - no se valida que la extensión de `ruta` sea de la capa;
    - un objeto hostil dentro de un hallazgo todavía puede callar el hook. Ya pasaba en la `0.11.0`;
    - los hooks de cierre no muestran un hallazgo bajado a aviso: está documentado;
    - el comando sugerido puede apuntar al checkout principal cuando el corpus está en un worktree.
  - **Scratch, a borrar a mano:** del verificador, `%TEMP%	mp.rVy72n5d6i` (con un worktree enlazado de prueba adentro); del writer del lote, `%TEMP%	mp.WJLEKeuCgL`.
