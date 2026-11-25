# Que se vea lo que hoy pasa callado: la falla de un hook, los hooks de un repo, las plantillas viejas, las extensiones sin capa a propósito y dos defectos de plantilla (R15)

Objetivo: que el doctor y el inicio de sesión muestren lo que hoy pasa en silencio (I2, I36, I85 e I87) y cerrar dos defectos de las plantillas de la instancia (I88 e I89).
Rama: `feat/fallas-calladas`, en `D:/Project/odd-ws-wt/fallas`, desde `origin/main` (`0b44438`). Los writers trabajan en sus propios worktrees desde `origin/main` y el orquestador integra sus ramas con `--no-ff`. Entrega: un commit por unidad. Sale en la `0.14.0`, con el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap.
- Lo marcado como **decisión de diseño** no lo pidió el autor con esas palabras: es cómo se cumple su pedido.
- Lo marcado como **supuesto** está por confirmar.

- **S1** (I2, la falla de un hook). «Que la falla de un hook quede a la vista: se anota en `.claude/estado` y el doctor o la sesión siguiente la muestra.» El porqué, del roadmap: «Una falla de la infraestructura nunca se vuelve una respuesta».
  - **Decisión de diseño:** los hooks siguen fallando abiertos, y ningún guard cambia su veredicto. Lo nuevo es el rastro.
    - Cada excepción que hoy se tragan `correr()` de cada hook y `comun.correr_hook` se anota en un archivo de `.claude/estado/`: el hook, el evento, la fecha y el tipo y mensaje de la excepción. Nunca el payload del evento. El archivo tiene un tope de entradas.
    - La sesión siguiente la muestra una vez, por `verificar_capa._session_start`.
    - El doctor suma un ítem con las últimas fallas, en AVISO, y `--arreglar` lo vacía.
  - **Supuesto:** las capturas silenciosas internas, como `revisar_turno.py:223,306`, `writer_guard.py:1406,1455,1479` y `writer_stop.py:171,223,277,293`, son degradaciones previstas y no se anotan. Solo se anota lo que llega al `except` de `correr()` o de `correr_hook`.
- **S2** (I36, los hooks propios de un repo). «`abrir` y el doctor avisan cuando un repo trae hooks propios en su `.claude/settings.json`, porque no corren si la sesión arranca en la instancia.» El porqué: «El guard y el formateador del repo no corrieron en toda una sesión desde la raíz».
  - **Decisión de diseño:**
    - Una sola función compartida, como en I67, lista los repos de la config cuyo `.claude/settings.json` o `.claude/settings.local.json` declaran `hooks`.
    - `ticket.py --cobertura`, el paso 8 de `abrir`, imprime un `aviso` con su `cómo:`: esos hooks corren solo si la sesión arranca en el repo.
    - El doctor suma un ítem en AVISO.
    - Un archivo que no se puede leer, o que no trae `hooks`, no avisa.
- **S3** (I87, sin capa a propósito). «Las extensiones que van sin capa a propósito, como imágenes, recursos o archivos de build, se reconocen una vez y el AVISO de `capas-cobertura` se apaga.»
  - **Decisión de diseño:**
    - Una clave opcional `sin_capa` en `workspace.config.json`: una lista de extensiones con su punto.
    - Se valida con el par `sin_capa_de(config)` / `sin_capa(raiz)`, como `hooks_apagados`, y se registra en `bootstrap._cargar_en_temporal` y en `doctor.chequear_config`.
    - Las extensiones listadas pasan a las esperadas, que salen en OK con su nota, en el doctor, en `ticket.py --cobertura` y en el triaje.
    - El `cómo:` del AVISO muestra la línea exacta de la clave con las extensiones del aviso, para que el usuario saque las que sí son código. No hay `--arreglar`, porque reconocer todo de una vez taparía código sin capa.
- **S4** (I85, las plantillas viejas). «El doctor avisa cuando una plantilla copiada a la instancia quedó en una versión vieja, y la primera sesión después de actualizar dice qué copiar.» Las plantillas copiadas son el `CLAUDE.md` raíz, `tickets/_plantilla/CLAUDE.md`, `.githooks/pre-commit` y `.claude/reglas/verificar_<capa>.tests.py`.
  - **Diseño aprobado por el autor (opción A, L5):**
    - La instancia anota con qué versión del plugin quedaron sus plantillas.
    - El plugin trae, como datos bajo `plugin/`, la huella de cada plantilla en cada versión publicada, generada al publicar. El plugin instalado no tiene etiquetas de git.
    - El doctor avisa qué plantillas cambiaron desde la versión anotada.
    - `--arreglar` reemplaza las copias sin tocar, que son las que coinciden con la huella de alguna versión. Después de que el usuario fusiona las editadas, anota la versión nueva.
    - La primera sesión después de actualizar dice qué copiar.
  - **Decisión de diseño:** el `CLAUDE.md` raíz se compara ya renderizado con los valores de la instancia (`{{nombre}}` y `{{tickets}}`).
- **S5** (I88, el `__pycache__`). «Correr las pruebas de reglas copiadas a la instancia no deja `__pycache__`.»
  - `verificar.tests.py` y `pre-commit.tests.py` ponen `sys.dont_write_bytecode = True` antes de cargar nada.
  - `verificar.py` no lo necesita, porque lo carga su prueba con el flag ya puesto.
  - Una prueba corre la plantilla copiada en un temporal y comprueba que no queda `__pycache__`.
- **S6** (I89, el `/compact`). «El `CLAUDE.md` de la instancia dice una sola cosa sobre lo que vuelve después de un `/compact`.»
  - Lo correcto, del roadmap: «el `CLAUDE.md` del ticket no vuelve entero, pero el ticket activo vuelve como resumen (I13)».
  - Lleva su entrada en `Doc/actualizar.md`.
- **S7** (la versión). Se actualizan:
  - el CHANGELOG de la `0.14.0`;
  - `Doc/actualizar.md`, con las plantillas que cambian en la `0.14.0`;
  - la versión en `plugin/.claude-plugin/plugin.json`, `plugin/.codex-plugin/plugin.json`, `package.json`, el README, `Doc/` y la página.

  Después, un verificador independiente revisa toda la feature. Publicar lleva el ok del autor.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento, su espejo en engram y la cola del roadmap con el orden nuevo | inline | hecha | (con T1) |
| T1 | S5, S6 | El `__pycache__` y el `/compact` | inline (unidad chica) | hecha (L3) | `47ab32b` |
| T2 | S1 | La falla de un hook a la vista | delegada: writer A en `D:/Project/odd-ws-wt/fallas-hooks`, en paralelo con T3 (motivo: el respaldo de contexto del orquestador y dos unidades independientes de más de 100 líneas; comparten `doctor.py`, `doctor.tests.py` y el SKILL del doctor, que integra el orquestador) | hecha (L7) | `b0e7093`, integrada en `ffce153` |
| T3 | S2, S3 | Los hooks de un repo y las extensiones sin capa | delegada: writer B en `D:/Project/odd-ws-wt/fallas-cobertura`, en paralelo con T2 | hecha (L6) | `b9f00f6`, integrada en `fd94d72` |
| T4 | S4 | Las plantillas viejas | delegada: un solo writer en `D:/Project/odd-ws-wt/fallas-plantillas`, desde `ffce153` (motivo: el respaldo de contexto del orquestador) | hecha (L9) | `4b39845`, integrada en `649cd7f` |
| T5 | S7 | El CHANGELOG, la versión, el verificador independiente y publicar con el ok del autor | docs inline; verificador delegado | versión lista (L10); verificador hecho y su bloqueante corregido (L11); `main` integrado y la A1 arreglada (L12); auditada y publicada como `0.14.0` (L13, L14) | `9412353` y la corrección |

## Log

- **L1** (2026-11-24) El autor, tal cual, en orden:
  - «Debemos retomar y empezar con lo nuestro reorganizar que ideas van a salair y que versiones como para volver a organizar y deberiamos empezar».
  - A la propuesta, aceptó este orden:
    - `0.14.0`: I2, I36, I85, I87, I88 e I89.
    - `0.15.0`: I47, I35, I92 e I86.
    - `0.16.0`: I90 e I91.
    - `0.17.0`: I83 e I84.
    - Los estudios de I80 con I63 y de I78 con I79 van en paralelo.

    Su respuesta: «Si, va ese orden, arranca con la 0.14.0».
- **L2** (2026-11-24) El mapa del explorador:
  - El plugin instalado no trae etiquetas ni historia de git: la fuente del marketplace es `./plugin`. Las huellas por versión tienen que viajar como datos bajo `plugin/`, generadas al publicar.
  - Una cabecera en `verificar*.py` choca con `bootstrap_reglas.tests.py:158-162`, que prohíbe comentarios.
  - La I85 queda pendiente de una pregunta al autor sobre su diseño.
- **L3** (2026-11-24) T1, hecha inline.
  - **S5:**
    - RED con `test_correr_a_mano_la_suite_copiada_de_la_plantilla_no_deja_pycache` (`reglas.tests.py`). Dejaba `verificar_sql.cpython-314.pyc`.
    - GREEN con `sys.dont_write_bytecode = True` al principio de `verificar.tests.py`, igual que en los scripts del plugin.
    - `pre-commit.tests.py` lleva el mismo flag por consistencia. No hay RED posible ahí, porque no carga ningún módulo local.
  - **S6:**
    - RED con `test_la_raiz_dice_una_sola_cosa_sobre_lo_que_vuelve_tras_compactar` (`bootstrap_textos.tests.py`).
    - GREEN con la línea 14-16 de `plantillas/CLAUDE.md`: «tras `/compact` no vuelve entero: del ticket activo vuelve un resumen».
  - **Suites:** `reglas` 56/56, `bootstrap_reglas` 22/22, `pre-commit.tests` 16/16, `bootstrap_textos` 34/34, `bootstrap` 208/208.
  - La entrada de `Doc/actualizar.md` para la `0.14.0` va con T5.
- **L4** (2026-11-24) El autor, tal cual: «Como yo te dejare trabajando en loop todo el dia, por si llegas el limite deberias poder seguir trabajando apenas se renicie el limite de 5h».
  - Queda un cron de la sesión que retoma desde este documento cada 30 minutos.
  - Fuera de su alcance quedan el push a `main`, la etiqueta y la publicación.
  - **Sobre S4:** se le preguntó al autor por el diseño de la I85. Si no responde, se sigue con la opción recomendada, marcada como «a ratificar»:
    - la instancia anota con qué versión quedaron sus plantillas;
    - el plugin trae las huellas por versión;
    - `--arreglar` reemplaza las copias sin tocar y, después de fusionar las editadas, anota la versión nueva.
- **L5** (2026-11-24) El autor aprobó la opción A para S4: «Vale me parece bien».
  - Después dejó el resto de la jornada a criterio del orquestador: «Apartir de ahora te dejo a tu criterio, probablemente antes de sacar la version enviare un auditor, asi que tu sigue trabajando el resto de versiones solo dejalas listas que mañana miramos en que quedamos ya te dejo libremente espero que nada que interrumpa».
  - Y pidió, solo para este loop: «intenta trabajar con menos agentes paso a paso solo lo necesario». Desde ahí va un agente por vez y nunca en paralelo.
- **L6** (2026-11-24) T3, el writer B. Cubrió S2 y S3.
  - **Suites:** `config_loader` 116/116, `ticket` 68/68, `doctor` 233/233, `bootstrap` 209/209, `triaje` 103/103.
  - **Diferencial contra `0b44438`:** solo cambian la fila nueva del doctor, el aviso nuevo, el `cómo:` de la cobertura y el efecto de `sin_capa`.
  - **Decisiones del writer que se aceptan:**
    - `Cobertura` suma el campo `ayuda`, que arma `ayuda_de_cobertura`, para que el doctor y `ticket.py` digan lo mismo.
    - El `cómo:` de la cobertura cambia en todo AVISO, porque «si no, el aviso queda» ya no era cierto.
    - En el triaje no cambian ni la lista ni el modo, y `sin_capa.aviso` puede ser `null` cuando la clave cubre todo.
    - Las extensiones se comparan sin distinguir mayúsculas.
    - Para S2, «trae hooks» es un objeto `hooks` no vacío, y solo se lee la ruta principal de cada repo.
  - **El orquestador, inline:**
    - `hooks-de-repos` no aplica en una instancia que no declara Claude Code, porque los hooks de `.claude/settings.json` solo corren ahí. Es `config_loader.declara_claude_code`, y `ticket.py --cobertura` tampoco avisa en ese caso. RED con dos pruebas nuevas, después GREEN: `ticket` 69/69 y `doctor` 234/234.
    - `skills/bootstrap/SKILL.md` ya no dice que las demás extensiones «quedan con el aviso»: también se reconocen en `sin_capa`.
  - **Risk: item 3 (contratos).** Cambian la tupla `Cobertura`, el texto del `cómo:` y el `null` de `sin_capa.aviso` en el JSON del triaje. Son contratos internos del plugin; el verificador los revisa.
  - **Scratch del writer:** `%TEMP%\tmp.w631YHxaIh` y `%TEMP%\tmp.WyA413be6K`. El guard no deja borrarlos, así que van a la limpieza del autor.
- **L7** (2026-11-24) T2, el writer A. Cubrió S1.
  - **Lo nuevo:** `odd_ws/fallas.py` es el módulo compartido. Lo usan los cinco hooks, `correr_hook` (con el argumento opcional `hook`) y el doctor.
    - El rastro va en `.claude/estado/fallas-de-hooks.jsonl`, con los campos `{id, momento, hook, evento, tipo, mensaje}`.
    - El mensaje va en una sola línea, cortado a 200 caracteres. El evento se guarda solo si es un nombre válido.
    - El tope es de 20 entradas, reescritas con `os.replace`.
    - `fallas-de-hooks.vista` guarda el último que mostró el inicio de sesión.
    - SessionStart muestra las nuevas una sola vez, con las 5 más recientes y la cuenta de las demás, entre el aviso de I75 y el ticket activo.
    - El doctor suma el ítem `hooks-fallas`, después de `perfil`. Sale OK sin fallas y AVISO con la cuenta y las 3 más recientes. `--arreglar` borra los dos archivos. Si no se puede leer, es AVISO sin arreglo.
  - **Para el verificador:**
    - Un payload que no es JSON también llega al `except` de `correr()`, así que ahora deja rastro. Por eso cambió la aserción de `writer_stop.tests.py::test_otros_eventos_y_basura_callan`.
    - El mensaje de una excepción puede llevar hasta 200 caracteres de la entrada, como el texto de un `int()`. Queda solo en `.claude/estado/`, que la instancia ignora.
    - Si dos fallas llegan durante la reescritura del tope, se puede perder una. Está anotado en `Doc/diseno.md`.
  - **Suites:** `comun` 63/63, `verificar_capa` 134/134, `revisar_turno` 34/34, `writer_guard` 125/125, `guard_comandos` 83/83, `writer_stop` 61/61, `doctor` 230/230, `capacidades` 37/37, y las otras 44 suites más el shim (97/97) en verde.
  - **Diferencial contra `0b44438`:**
    - En el doctor, la única línea nueva es `hooks-fallas OK`.
    - En los guards, 15 payloads por `guard_comandos` y `writer_guard` dieron el mismo código, stdout y stderr en los 30 casos.
  - **Risk: item 2 (guards).** Toca el camino de error de los guards. Los veredictos no cambian (diferencial y pruebas por guard), y lo revisa el verificador independiente de la feature.
  - **Scratch del writer:** `%TEMP%\tmp.Mz99acoG1o`. Va a la limpieza del autor.
- **L8** (2026-11-24) La integración.
  - T3 entró sin conflictos en `fd94d72`.
  - T2 entró en `ffce153`, con conflictos en `doctor.py`, `doctor.tests.py`, `skills/doctor/SKILL.md`, `Doc/diseno.md` y `Doc/uso.md`. Se resolvieron conservando los dos ítems nuevos en este orden: `perfil`, `hooks-de-repos`, `hooks-fallas`.
  - Antes del merge, en la punta: `doctor` 235/235, `ticket` 69/69, `config_loader` 116/116 y `verificar_capa` 134/134. El pre-commit del merge corrió todas las suites y pasó, y ese fue el chequeo de costura.
  - **T4 (S4, diseño A)** lo hace un solo writer en `D:/Project/odd-ws-wt/fallas-plantillas`, desde `ffce153`. Decisiones de diseño del orquestador para ese writer:
    - **La clave `plantillas`.** Es una clave opcional de `workspace.config.json` con la versión del plugin a la que se sincronizaron las plantillas, y la escribe el bootstrap. Una instancia sin la clave es «sin versión anotada»: la versión se infiere de las copias sin tocar.
    - **La tabla de huellas.** `plugin/plantillas/huellas.json` guarda la huella de cada plantilla copiada en cada versión publicada, más la del árbol actual bajo la versión de `plugin.json`. La genera `tools/huellas.py` desde las etiquetas `odd-ws--v*`.
      - El pre-push de `tools/entrega.py` comprueba que esté al día en un push a `main` o a una etiqueta, igual que el chequeo de la página de la R14 (S7).
      - No hay una prueba que trabe los commits intermedios.
    - **El `CLAUDE.md` raíz.** Antes de calcular su huella se des-renderiza: los valores de `{{nombre}}` y `{{tickets}}` de la instancia vuelven a sus marcadores.
      - Si la des-renderización falla, la copia cuenta como editada. Es el lado seguro: nunca reemplaza algo que el usuario tocó.
      - El perfil controles usa `CLAUDE.controles.md`.
    - **El ítem `plantillas` del doctor.**
      - OK si la versión anotada es la actual, o si ninguna plantilla cambió desde la anotada.
      - AVISO si cambió alguna. Lista cada copia como «sin tocar, se reemplaza» o «editada, fusiónala a mano» (con las versiones para leer `Doc/actualizar.md`).
      - `--arreglar plantillas` reemplaza las copias sin tocar y anota la versión actual. El `cómo:` dice que las editadas se fusionan antes de correrlo.
    - **El inicio de sesión.** Después de un salto de versión (I75), nombra las plantillas que cambiaron y manda a `/odd-ws:doctor`.
- **L9** (2026-11-25) T4, el writer C. Cubrió S4 con el diseño de L8 y estas decisiones propias, que se aceptan:
  - **`{{tickets}}` se renderiza del lado de la plantilla.** La palabra «tickets» aparece también en el texto, así que no se puede revertir en la copia. `{{nombre}}` sale de la primera línea de la copia. Si no calza, la copia cuenta como editada.
  - **Las copias se comparan contra la plantilla actual, calculada en vivo.** Una tabla atrasada entre versiones nunca traba nada. Una versión etiquetada conserva la huella de su etiqueta, y el árbol actual va solo bajo una versión de `plugin.json` que todavía no tiene etiqueta.
  - **La tabla.** `tools/huellas.py` lee las etiquetas con `git tag --merged` y `git cat-file --batch`. La tabla trae 102 huellas, de la `0.2.0` a la `0.13.3`, y regenerarla da los mismos bytes.
  - **Sin la clave.** La versión se infiere de forma conservadora, como la más vieja que comparten las copias sin tocar, y el ítem sale en AVISO. Con la clave y todo ya al día, sale en AVISO «falta anotar la versión», y el arreglo solo la anota.
  - **El arreglo.** `--arreglar` cambia solo la línea de la clave en `workspace.config.json` y conserva el BOM, el CRLF y la sangría. Un symlink cuenta como editado, y una copia que falta se salta.
  - **Las pruebas del hook.** `RepoConHook` en `entrega.tests.py` ahora copia también `huellas.py` y `plugin/scripts`. Esa suite pasó de 1m45s a 2m03s.
  - **Suites.** `plantillas_instancia` 6/6, `doctor` 241/241, `config_loader` 117/117, `bootstrap` 211/211, `verificar_capa` 136/136, `tools/huellas` 3/3, `tools/entrega` 43/43, y las 54 suites más el shim en verde.
  - **Diferencial contra `ffce153`.** Solo cambian la fila nueva `plantillas` y la línea nueva del inicio de sesión después de un salto.
  - **Risk.**
    - Item 3: el bootstrap escribe una clave nueva, y el doctor escribe `workspace.config.json` con `--arreglar`.
    - Item 5: el pre-push de la entrega gana un chequeo que bloquea.

    Los dos van al verificador de T5.
  - **Para T5.** Después de subir a la `0.14.0`, correr `python tools/huellas.py` y commitear la tabla, o el pre-push bloquea.
  - **Scratch del writer.** El guard no deja borrarlo, así que va a la limpieza del autor:
    - `%TEMP%\tmp.EdC1ixQMTE`
    - `%TEMP%\tmp.lw2gH4w7ZZ`
    - `%TEMP%\pi_respaldo.py`
    - `%TEMP%\suite-actual.log`
- **L10** (2026-11-25) T5, la versión.
  - T4 entró sin conflictos en `649cd7f`. Su pre-commit corrió sobre ese mismo árbol.
  - La versión `0.14.0` quedó en:
    - los dos `plugin.json` y el `package.json`;
    - la «Versión actual» y el comando de gentle-shell del README;
    - `Doc/actualizar.md:28` y `Doc/uso.md:66`.
  - `Doc/actualizar.md` suma «En la `0.14.0`»: la frase del `/compact` en el `CLAUDE.md` (I89), la prueba de las reglas sin bytecode (I88) y la clave `"plantillas"`, que la anota el doctor.
  - El CHANGELOG suma la sección `0.14.0`.
  - `tools/huellas.py` regeneró la tabla: 107 huellas de 25 versiones, de la `0.2.0` a la `0.14.0`.
  - En el roadmap, R15 queda «lista, sin publicar», y sus seis ideas quedan «lista (`0.14.0`, sin publicar)».
  - La página (`gh-pages`) se actualiza al publicar, igual que en la R14, porque es otra rama.
  - Falta el verificador independiente de toda la feature (Risk items 2, 3 y 5) y, después, el ok del autor y su auditor para publicar.
- **L11** (2026-11-25) El verificador independiente, sobre `9412353` contra `0b44438`.
  - **S1 a S6: PASS.**
    - Los 370 casos de `guard_comandos` y 332 payloads de `writer_guard` dieron, corriendo el hook real en la base y en la punta, el mismo código, stdout y stderr: 0 diferencias.
    - Las excepciones forzadas en los cinco hooks dieron `(0, b'', b'')` en las dos versiones, y anotar nunca lanzó.
    - `--arreglar plantillas` sobre una instancia de la base la dejó byte a byte igual a un bootstrap nuevo.
    - Ningún consumidor de los contratos que cambiaron se rompe.
    - `tabla_desfasada` solo bloquea una tabla de verdad atrasada.
    - Suites: las 54 de Python y el shim (97/97) en verde.
  - **S7: FAIL por un bloqueante, B1, solo de docs.**
    - El CHANGELOG decía que `--arreglar plantillas` «te deja la lista de las que tienes que fusionar a mano», y `Doc/actualizar.md`, que la clave se anota «cuando ya no queda ninguna copia por fusionar».
    - El código hace lo que aprobó el autor con el diseño A: reemplaza las copias sin tocar y anota la versión. Por eso hay que fusionar antes.
  - **La corrección, un solo lote:**
    - B1: los dos textos dicen ahora que se fusiona primero y se arregla después.
    - A2: `Doc/hooks.md` ya no dice que nunca se anota el comando, porque el mensaje del error puede traer un pedazo de la entrada.
    - La recomprobación de B1, inline: el CHANGELOG, `Doc/actualizar.md`, `Doc/uso.md`, el SKILL del doctor y `Doc/diseno.md` dicen lo mismo que el código.
  - **Advertencias que quedan para el autor y su auditor** (seguimientos, no arreglados en este lote):
    - **A1 (ya estaba en la base, ahora se ve).** `writer_guard` lanza un `ValueError` interno con `echo x > NUL`, tanto en Bash como en PowerShell, y falla abierto igual que en la base. Desde esta versión cada comando así anota una falla, y la sesión siguiente avisa. En Windows eso es ruido. Arreglarlo toca un guard (item 2), así que se deja para que lo decida el autor antes de publicar.
    - **A3.** Un `CLAUDE.md` sin tocar sale como «editada» si el nombre del proyecto aparece también en el texto de la plantilla (por ejemplo «Claude» o «repos»), porque `plantillas_instancia.py:127` reemplaza todas las apariciones. Se equivoca hacia el lado seguro.
    - **A4.** Con `sin_capa` inválido (`config` en FALTA), `--arreglar plantillas` igual reescribe las plantillas y la config, y deja la clave inválida.
    - **A5.** El bootstrap pisa en silencio un `config.plantillas` explícito del spec.
    - **A6.** El pre-push compara contra las etiquetas locales: un clon sin alguna etiqueta queda bloqueado, y correr ahí `huellas.py` borraría entradas.
    - **A7.** `aviso_de_inicio` de las plantillas no está dentro de un `try` en `_session_start`. Si lanzara, se perderían el aviso de versión y el resumen del ticket. El verificador no encontró un disparador realista.
    - **A8.** La redacción de una instancia sin copias, y el tope de 20 en la cuenta del inicio.
  - **El scratch del verificador va a la limpieza del autor:** `%TEMP%\tmp.hgPegvIkB7`.
- **L12** (2026-11-25) Antes de publicar: el merge de `main`, la decisión de la A1 y la auditoría.
  - **El autor:**
    - dejó la R19 en pausa y pidió auditar las tres versiones listas: «Dejalo que termine su T1, vale hagamos esos 4 pasos y si hagamoslo de la siguiente manera, acabo de crear una sesion nueva para que hables con el le das el prompt para que el sea el auditor mejor que este separado con su contexto y trabajando en conjunto»;
    - decidió la A1: «Arréglala ahora en la 0.14.0»;
    - autorizó publicar: «Por tiene tienes el OK, para publicar las versiones cuando ya lo esten».
  - **El merge de `main`** (`907f430`) trae solo el roadmap, con I93 a I97. El choque de la tabla se resolvió con las filas de esta rama más las cinco nuevas, y la fecha y la cuenta de ideas de `main`. Contra `f915b0b`, el diff es igual al que trae `main`.
  - **La A1, arreglada.**
    - **La causa.** `rutas.ubicar` vuelve absoluto el `NUL` relativo (`C:/<cwd>/NUL`), así que ya no calza con `NULOS`. `realpath` lo lleva a `\\.\nul`, y `config_loader.clasificar` termina en un `relpath` entre montajes distintos, que lanza `ValueError`.
    - **El arreglo.** `_es_nulo` acepta `NULOS` como antes y, solo en Windows, una ruta cuyo último tramo es `nul` o `nul:`. En Windows, `<carpeta>/NUL` es el dispositivo nulo y no puede existir como archivo. En Linux y macOS, `NUL` sigue siendo un archivo común y el guard lo sigue mirando. Se usa en los tres lugares que miraban `NULOS`.
    - **RED y GREEN.** La prueba nueva cubre `> NUL`, `> nul`, `2> NUL`, `> NUL:` y `> /dev/null` en Bash, y `> NUL` y `2> nul` en PowerShell. Pide que cada uno pase con `(0, "", b"")` sin anotar ninguna falla. RED: anotaban `ValueError: path is on mount '\\.\nul', start on mount 'c:'`. GREEN: `writer_guard.tests.py` en 126/126.
    - **Risk: ítem 2.** Toca un guard. El veredicto de estos comandos no cambia, porque ya pasaban por fallar abierto; lo recomprueba el auditor.
  - **La auditoría** la hace una sesión aparte, de a una versión. Sus hallazgos y su corrección se anotan acá.
- **L13** (2026-11-25) La auditoría de publicación, sobre `f915b0b`: **PUBLICABLE CON NOTAS**, sin bloqueantes causados por la versión.
  - **La A1 era un bypass, no solo ruido.** Ya estaba en la base.
    - Con `2>nul`, todo `decidir` se caía y el guard dejaba pasar.
    - Con un writer, `git commit -m x 2>nul`, `git push 2>NUL` y `git -C <repo> reset --hard 2>nul` salían con 0 en Bash y en PowerShell.
    - `guard_comandos` no tenía el problema.
  - **El primer arreglo** (`be2bfeb`, en L12) miraba el último tramo `nul`. El auditor barrió los destinos en Windows 11:
    - se caían `NUL`, `nul:`, `x\nul` y, en Bash, `\\.\nul`;
    - `CON`, `PRN`, `AUX`, `COM1` y `nul.txt` no se caen en Windows 11, pero en Windows Server, que corre el CI y se comporta como Windows 10, `GetFullPathNameW` también los vuelve `\\.\…`.
  - **El arreglo final.** `_es_dispositivo` sigue aceptando `NULOS`, y en Windows también toda ruta cuya `abspath` empieza con `\\.\`, que es justo el caso que hacía caer el `relpath`. Así cubre Windows 10 y 11 sin listar nombres. Se usa en los mismos tres lugares.
  - **La prueba del bypass:** con un writer, `git commit -m x` con `2>nul`, `2>NUL`, `>nul 2>&1` y `2> NUL:`, y `git push 2>NUL`, en Bash y en PowerShell, bloquean sin anotar fallas.
    - En la base dio RED en 10 de 12.
    - Con el arreglo, `writer_guard.tests.py` da 127/127, también con un `GIT_INDEX_FILE` ajeno.
    - Las pruebas usan solo formas de `NUL`, que son dispositivo en los dos Windows, como sugirió el auditor.
  - **`config_loader.clasificar`** sigue lanzando si `_dentro` y `relpath` no coinciden. El auditor no encontró otro camino que le llegue con un dispositivo. Queda como seguimiento (ítem 3), por ser una función compartida.
  - **W1, en el mismo lote.** El CHANGELOG, `Doc/actualizar.md` y `Doc/uso.md` decían que la primera sesión después de actualizar nombra las copias que cambiaron. Eso pasa solo si el plugin vive en una carpeta con su versión; en Pi instalado por git, avisa el doctor. Ahora lo dicen.
  - **Seguimientos:**
    - W2: el doctor nombra la 0.12.0 en una instancia de la 0.13.3 sin clave.
    - W3: rutas locales en los documentos de `odd/tasks/`.
    - A3 a A8, con la nota del auditor sobre la A7: un `try` alrededor de `aviso_de_inicio` es barato.
  - **Risk: ítem 2.** Toca un guard. La recomprobación de la A1 y la W1 la hace el auditor.
- **L14** (2026-11-25) La recomprobación y la publicación.
  - **El auditor recomprobó `5ad9149`:**
    - A1 PASS:
      - 28 destinos de `git commit -m x 2><destino>` bloquean en Bash y en PowerShell sin anotar fallas;
      - los comandos inocentes con `nul` pasan sin anotar;
      - el diferencial de `guard_comandos` contra `f915b0b` (758 corridas) solo cambia una falsa alarma: `echo x > x\nul` desde un repo protegido ya no pregunta.
    - W1 PASS.
    - Veredicto: **PUBLICABLE CON NOTAS.**
  - **El CI** de la rama dio verde en Windows, Ubuntu y macOS (run `45696650498`).
  - **Publicada como `0.14.0`:**
    - `main` avanzó de `5c3de25` a `5ad9149`, con la etiqueta `odd-ws--v0.14.0`;
    - `release.yml` creó el release;
    - la página dice la `0.14.0` desde `8cb1a37`.
