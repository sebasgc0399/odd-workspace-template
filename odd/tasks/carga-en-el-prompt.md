# La carga de odd-ws en el prompt (R11, I65)

Objetivo: bajar lo que odd-ws suma al prompt del modelo, después de que un usuario de la comunidad con 5 agentes en gentle-shell reportó un pico de consumo. Que no sume nada fuera de una instancia ni en los subagentes, y que las skills largas tengan un núcleo corto con el detalle en archivos que se leen solo cuando hacen falta.
Rama: `feat/carga-en-el-prompt`, en `D:/Project/odd-ws-wt/r11`, desde la `0.12.0` (`43ccca7`). Entrega: una unidad por commit; el push y la publicación, solo con autorización del autor. Sale en la `0.12.1`.
Pruebas: `python plugin/scripts/<script>.tests.py` (en Linux y macOS, `python3`) y `node --test plugin/shim/*.test.ts`.

## Specs

El origen es la promesa del autor a ese usuario, tal cual (L1): «Para la 0.12.1 voy a hacer que odd-ws no sume nada fuera de una instancia ni en los subagentes, y a dejar las skills con un núcleo corto y el detalle en archivos que se leen solo cuando hacen falta.» El mapa del explorador está en L2.

- **S1** (los subagentes, en Pi). En un hijo de gentle-shell (`GENTLE_PI_AGENTS_CHILD=1`), odd-ws no suma nada al system prompt:
  - `session_start` y `session_compact` no lanzan Python ni agregan contexto: ni el resumen del ticket activo ni el aviso de config rota;
  - no se publica `.claude/skills` de la instancia;
  - las skills de odd-ws, las del plugin y las de la instancia, se sacan del catálogo del hijo filtrando `event.systemPromptOptions.skills` por su `filePath` en `before_agent_start`, sin tocar las de otros paquetes.

  Los guards siguen igual en el hijo: los bloqueos de `tool_call`, el primer toque y las reglas en `tool_result`, y la compuerta del writer. Es la paridad con Claude Code, donde el SessionStart no llega a los subagentes.
- **S2** (fuera de una instancia, en Pi). En el agente principal, si desde `ctx.cwd` no hay raíz de instancia, las skills del plugin se sacan del catálogo con el mismo filtro. `/skill:<nombre>` sigue andando, porque `pi.skills` se queda en el `package.json` (así `/skill:bootstrap` crea una instancia y `/skill:doctor` revisa la máquina). Dentro de una instancia el catálogo queda como hoy.
- **S3** (`revisar` con un núcleo corto). El `SKILL.md` de `revisar` baja a menos de unos 5.000 tokens (Claude Code solo vuelve a adjuntar los primeros 5.000 de una skill después de una compactación, y hoy `revisar` ronda los 10.000 y pierde sus secciones del recibo y del rechequeo).
  - **El núcleo** conserva la guarda de `controles`, las reglas duras, los pasos y los comandos.
  - **El detalle** pasa a `references/` (por ejemplo `recibo.md`, `rechequeo.md` y `rescate-pi.md`), detrás de compuertas explícitas en el núcleo («antes de usar `--previo` o `--bajada`, leé `references/recibo.md`»).
  - **Lo que ningún script valida** se queda en el núcleo, salvo el prompt de los revisores, que se usa solo al lanzar las corridas y el núcleo lo pide en ese paso con una compuerta sin condiciones (L4).
  - **Las rutas en las references** usan el marcador `<S>` que define el núcleo, nunca `${CLAUDE_PLUGIN_ROOT}`, porque Claude Code solo lo reemplaza en el `SKILL.md`.
  - **Los tests** que leen el texto de la skill leen el núcleo y las references juntos.
- **S4** (`cerrar` con un núcleo corto). Lo mismo para `cerrar`, con un núcleo de unos 12 KB y el detalle en `references/` (por ejemplo `matriz.md`, `memorias.md` y `entrega.md`).
- **S5** (las descripciones). Las de las skills listadas, con el caso de uso primero y unos 150 caracteres. Las de las que solo invoca el usuario, unos 110. Sin perder las palabras con que hoy se disparan las listadas.
- **S6** (nada se rompe). Las instancias que ya existen no tienen que editar nada. En Claude Code y Codex solo cambia el texto de las skills. El mecanismo de Pi es el filtro del catálogo, y `pi.skills` no se quita.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T1 | S1, S2 | Los hijos limpios y el catálogo solo dentro de una instancia, en el shim de Pi | delegada a un writer, en paralelo con T2 (superficies disjuntas) | hecha (L3) | `2b19450` |
| T2 | S3 | `revisar` con un núcleo corto y sus references | delegada a un writer, en paralelo con T1 | hecha (L4) | `f93167a` |
| T3 | S4 | `cerrar` con un núcleo corto y sus references | delegada, después de T2, con el mismo patrón | hecha (L6) | `26624db` |
| T4 | S5 | Las descripciones de las 9 skills | inline, al final, porque toca los frontmatter de T2 y T3 | hecha (L7, L8) | `95d361e` |
| T5 | todas | El verificador independiente de la feature, los docs y el cierre | inline | hecha: verificador PASS después de un lote de corrección (L8, L9) | `f3abf6f` |

## Log

- **L1** (2026-11-21) El autor, tal cual:
  - sobre el reporte del usuario: «hagamoslo en una 0.12.1 y lo miramos con mas calma»;
  - en el mensaje que le mandó a ese usuario: «Para la 0.12.1 voy a hacer que odd-ws no sume nada fuera de una instancia ni en los subagentes, y a dejar las skills con un núcleo corto y el detalle en archivos que se leen solo cuando hacen falta.»;
  - al salir: «Voy a salira almorzar, ya tienes mi aprobacion para publicar y trabaja para la proxima version».
- **L2** (2026-11-21) El mapa del explorador, de solo lectura, sobre la `0.12.0`, verificado en el código instalado de gentle-shell 4.8.0 y Pi 1.5.2:
  - **Lo que necesita cada uno:**
    - los hijos de odd-ws no necesitan ninguna skill del plugin ni el resumen del ticket: el writer lee `criterios` y `capa-<capa>` por su ruta, y los revisores leen el `CLAUDE.md` del ticket del disco;
    - `doctor` y `enlaces` los invoca el modelo a propósito, y `bootstrap` y `doctor` hacen falta fuera de una instancia.
  - **Cómo se filtra en Pi:** `skillPaths` acepta carpetas sueltas, y una carpeta con `SKILL.md` no se recorre, así que `references/` no se carga como skill. `before_agent_start` expone `systemPromptOptions.skills` mutable: gentle-shell lo vacía en sus agentes genéricos, y odd-ws puede filtrar las suyas.
  - **Tests atados al texto:** `recibo.tests.py`, `rescatar.tests.py`, `memorias.tests.py`, `config_loader.tests.py` (la guarda), `hosts/pi.tests.py` (P8, P9 y `disable-model-invocation`), `capacidades.tests.py:547` (el bloque `pi` del `package.json`) y `pi.test.ts:244,1618`.
  - **Decisiones:**
    - Tomadas por la promesa del autor: los hijos sin nada de odd-ws, el catálogo solo dentro de una instancia y el núcleo corto.
    - Defaults técnicos: filtrar el catálogo sin quitar `pi.skills`, registrar los 7 eventos también en el hijo, y usar `<S>` en las references, abiertas por compuertas.
    - **Para el autor:** qué skills pasan a ser solo del usuario. El explorador recomendaba `eval-reviewers` sí y `doctor` no. Decidido en L5: ninguna cambia.
    - El tope de 12.000 caracteres del resumen en el agente principal no se baja en esta versión.
- **L3** (2026-11-21) T1, escrita por un writer en `r11`. Son unas 286 líneas, 148 de tests.
  - **El shim:** `pi.ts` suma `cwdDe`, `carpetasDeOddWs` y `sinLasSkillsDeOddWs`, que filtran `event.systemPromptOptions.skills` en `before_agent_start`. En el hijo, `iniciar` no hace nada y `resources_discover` no publica. Se siguen registrando los 7 eventos.
  - **La comparación de rutas** usa los helpers del shim (`resolve`, `canonica`, `dentro` y `comparable`), con la ruta escrita y la real: sobrevive a junctions, mayúsculas y barras en Windows.
  - **Las suites:** el shim 74/74, `nucleo.test.ts` 15/15, `hosts/pi.tests.py` 70/70 y `odd_ws/capacidades.tests.py` 37/37. Rojo observado en cada regla, y un mutante sin la comparación por ruta real hace fallar su test.
  - **El diferencial**, con las suites viejas contra el shim nuevo, da 2 diferencias, las dos pedidas por S1:
    - `pi.test.ts:1618`: el hijo ya no publica las skills de la instancia;
    - `pi.test.ts:806`: el `session_compact` del hijo ya no genera texto de inicio. El padre aceptó ajustar este test, que el brief no nombraba.
  - **`/skill:<nombre>`** se comprobó leyendo el código de Pi 1.5.2, no en vivo. Pi le pasa a cada handler una copia del catálogo, y `/skill:` busca en `resourceLoader.getSkills()`, que el filtro no toca.
  - **Decisiones del writer, que el padre acepta:**
    - un padre con un `ctx.cwd` ilegible conserva el catálogo;
    - el límite conocido: si otra extensión ya devolvió un `systemPrompt`, Pi lo manda tal cual. Es el mismo límite que tiene gentle-shell, y está documentado.
  - **Scratch, a borrar a mano:** `%TEMP%	mp.tJ7dGKOGQ5`.
- **L4** (2026-11-21) T2, escrita por un writer en `r11`.
  - **Los tamaños:** `revisar/SKILL.md` bajó de 39.200 a 17.344 bytes, unos 4.690 tokens, con cinco references: `recibo.md` (12.355 bytes), `rechequeo.md` (5.342), `rescate.md` (2.870), `hosts.md` (2.757) y `prompt.md` (2.567).
  - **Las compuertas:** se abren con un evento que se ve (estar en Pi, un host que rechaza un lanzamiento, un rechequeo, `--bajada`, o `recibo.py` que sale con 1 o 2). Las rutas de las references usan `<S>`.
  - **Lo que no cambió:** el frontmatter, la guarda de `controles` y los números de sección.
  - **El prompt de los revisores** pasó a `references/prompt.md`, aunque S3 pedía dejar en el núcleo lo que ningún script valida. Solo ese texto ya pasaba de 17 KB. El padre lo aceptó, porque el prompt se usa solo al lanzar las corridas y el núcleo lo pide en ese paso sin condiciones. Aflojar el tope a 18,4 KB lo dejaba pegado a los 5.000 tokens de la compactación. Se reescribió S3 para decirlo.
  - **«Nada se perdió»:** de 275 oraciones, 165 están textuales y 110 se condensaron. Cada una tiene un ancla en el archivo que ahora la lleva, y un script comprobó que el ancla existe: 0 sin mapear. Las 22 líneas de código y las 18 frases entre comillas están todas.
  - **Los tests:** `recibo.tests.py` y `rescatar.tests.py` leen el núcleo y sus references con un helper. Se sumaron dos tests: uno fija el tamaño del núcleo (17 KB) y el otro, que el núcleo nombre exactamente las references que existen y que ninguna use `${CLAUDE_PLUGIN_ROOT}`. Rojo observado con el archivo viejo.
  - **Las suites:** `recibo` 115/115, `rescatar` 61/61 y `config_loader` 105/105. El señuelo quedó intacto.
  - **Los márgenes:** el núcleo queda 64 bytes por debajo del tope, y la descripción más corta de T4 lo agranda. Falta una línea sobre `references/` en `Doc/diseno.md`, para T5.
  - **Scratch, a borrar a mano:** `%TEMP%	mp.PUBwn4xeKh` y `scratchpad	2` de esta sesión.
- **L5** (2026-11-21) La decisión del autor sobre qué skills pasan a ser solo del usuario. Tal cual: «Si dejemoslo como esta, en ves de ganar, lo complicamos».
  - **Lo que se comparó:** el ahorro, entre 60 y 120 tokens por agente y por llamada, y menos con las descripciones de T4, contra tres costos:
    - `cerrar` le pide al agente puntuar con `eval-reviewers` un caso del modo sombra antes de graduar (`cerrar/SKILL.md:49`), y `revisar` le delega congelar un caso que va a un líder (`revisar/SKILL.md:21`); con la skill solo del usuario, el agente tendría que frenar y pedírsela;
    - en las instancias que ya existen, el `CLAUDE.md` la lista como una skill más y no como ritual (línea 148 de la plantilla), así que el agente la ofrecería y no podría correrla: la vuelta perdida de la I39;
    - en Codex no cambia nada.
  - **`doctor`** tampoco cambia: lo piden el hook y el bootstrap.
  - **T4** solo acorta las descripciones, sin cambiar quién puede invocar cada skill.
- **L6** (2026-11-21) T3, escrita por un writer en `r11`.
  - **Los tamaños:** `cerrar/SKILL.md` bajó de 32.442 a 13.061 bytes, unos 3.530 tokens, con tres references: `memorias.md` (12.003 bytes, el modo memorias completo y con sus títulos), `matriz.md` (5.909) y `entrega.md` (2.494).
  - **El núcleo** conserva el frontmatter, la guarda de `controles`, las reglas duras 1 a 5 y los pasos 1 a 10. El paso 5 queda en los destinos y los dos `matriz.py`.
  - **Las compuertas:** se abren con un evento que se ve: el argumento `memorias`, una fila de la matriz o una regla que bloqueó algo correcto, un ticket que usó worktree, y la entrega.
  - **Una compuerta más que pidió el writer:** una disputa puede aparecer sin una fila nueva de la matriz.
  - **«Nada se perdió»:** las 37 líneas de código, los 176 spans y las 15 frases entre comillas están todas. De 229 oraciones, 171 están textuales y 58 se condensaron, cada una con su ancla. El control positivo falla si se borra una regla.
  - **Los tests:** `memorias.tests.py` lee el núcleo y las references con un helper, y fija el núcleo en 13 KB. Rojo observado con el archivo viejo.
  - **Las suites:** `memorias` 42/42, `config_loader` 105/105, `matriz` 60/60, `conocimiento` 113/113 y `hosts/pi` 70/70. El señuelo quedó intacto.
  - **S4 pedía unos 12 KB** y el núcleo quedó en 12,75 KiB, muy por debajo de los 5.000 tokens. El padre lo aceptó.
  - **Scratch, a borrar a mano:** `%TEMP%	mp.0gfodm0b7I` y `scratchpad	3` de esta sesión.
- **L7** (2026-11-21) T4, escrita por el padre. Las nueve descripciones, con el caso de uso primero y sin cambiar quién puede invocar cada skill (L5).
  - **Las que el modelo ve:** `revisar` pasa de 309 a 164 caracteres, `enlaces` de 286 a 153, `doctor` de 289 a 156 y `eval-reviewers` de 291 a 151. Entre las cuatro, de 1.175 a 624.
  - **Las del usuario:** quedan entre 112 y 130 caracteres.
  - **Lo que se conserva:** las palabras que disparan las listadas (`revisar`: «antes del commit», «líder», «recibo»; `doctor`: «hook», «entorno»). Ninguna lleva dos puntos, que en el frontmatter YAML rompen el valor.
- **L8** (2026-11-21) El verificador independiente de la feature (`43ccca7..95d361e`) y su lote de corrección. El autor ya dio el ok para publicar la `0.12.1`.
  - **El veredicto:** PASS en S1, S2, S3, S5 y S6, y FAIL en S4.
    - En Pi, el hijo no suma nada en ningún inicio y conserva todos los guards; el agente principal fuera de una instancia saca solo las skills del plugin, y `/skill:` sigue resolviendo.
    - Todas las suites dieron verde, también con `GIT_DIR` apuntando a un señuelo.
  - **El bloqueante:** la tabla del paso 2 de `cerrar` mandaba una medición directo a `evidencia.md`. La regla de que una medición es una fila de la matriz con su ID había quedado solo en `references/matriz.md`, cuya compuerta se abría con una fila o una disputa. El modelo habría escrito la medición sin fila, sin ID y sin `matriz.py`.
  - **El arreglo:** la fila de la tabla dice «una fila de la matriz con `destino` `evidencia`» y su entrada en `evidencia.md`, y el paso 4.1 nombra la medición junto a la compuerta. Un test de regresión en `memorias.tests.py` lo fija; dio rojo contra el núcleo commiteado y verde con el arreglo.
  - **Los avisos de significado, también corregidos:**
    - la regla 6 de `revisar` vuelve a cubrir cualquier revisión que el usuario quiera como caso del modo sombra;
    - el modo 0 vuelve a anunciar los archivos que va a leer;
    - la línea del acuerdo vuelve a decir que en `rapido` y en un rechequeo no lo trae.
  - **Los disparadores secundarios recuperados en las descripciones:** `doctor` con «Capa 0», «portátil» y «después de clonar la plantilla»; `eval-reviewers` con «comparar dos versiones de su prompt»; `enlaces` con «rutas de la máquina». Quedan en 179 a 199 caracteres, por encima de los 150 de S5, porque que se disparen cuando corresponde pesa más.
  - **Los núcleos:** `revisar` 17.331 bytes (tope 17.408) y `cerrar` 12.970 (tope 13.312).
  - **Los docs:** `Doc/diseno.md` describe las references de `revisar` y `cerrar`.
  - **Scratch del verificador, a borrar a mano:** `%TEMP%	mp.ZFERijv3X2`.
- **L9** (2026-11-21) El rechequeo y la entrega.
  - **El rechequeo** del verificador, limitado al bloqueante y a los avisos sobre `f3abf6f`, dio PASS en todo:
    - leyendo solo el núcleo, una medición lleva a una fila con `destino` `evidencia` y abre `references/matriz.md`;
    - los tres matices de `revisar` volvieron con su significado de base;
    - las descripciones parsean y recuperaron sus disparadores.
  - **Las suites del rechequeo:** `memorias` 43/43, `recibo` 115/115 y `pi.tests` 70/70.
  - **La entrega:** el autor dio el ok para publicar la `0.12.1`.
