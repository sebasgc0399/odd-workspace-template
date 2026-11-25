# El porqué antes de editar: el blame de las líneas que se tocan y lo que se quita vuelve como regla (R18)

Objetivo: que el agente vea el porqué de las líneas que va a editar, sacado de la historia y sin modelo (I90), y que lo que un ticket quita no pueda volver sin que alguien lo decida (I91).
Rama: `feat/porque-antes-de-editar`, en `D:/Project/odd-ws-wt/porque`. Está apilada sobre la punta de R16 (`44fffdf`, la `0.15.0` sin publicar): si R15 o R16 cambian, se integran hacia acá con un merge. Va un agente por vez (L1). Entrega: un commit por unidad. Sale en la `0.16.0`, con el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites, con el `GIT_INDEX_FILE` del commit en el entorno.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap. Lo marcado como **decisión de diseño** lo decidió el orquestador con la autonomía que dio el autor para esta jornada (L1), y queda a ratificar por el autor y su auditor.

- **S1** (I90, el porqué antes de editar). «Antes de editar, el agente ve el porqué de las líneas que va a tocar: un `git blame` de esas líneas muestra el cuerpo del commit que las escribió, sin modelo ni índice.» Del roadmap, las cuatro reglas de los comentarios: «Un timeout o un error del blame sale como «no se pudo chequear», nunca como limpio, y un archivo nuevo o sin trackear sale como «sin historia»», «la pausa usa el `ask` que el guard ya devuelve», «Se muestra la fecha del commit y una sola línea de porqué, no el cuerpo entero», y «el blame no ve el código borrado, que lo cubre I91».
  - **Decisión de diseño (revisada en L3, después del mapa del explorador; reemplaza a la de abajo donde se contradicen):**
    - **Antes de editar, en el `PreToolUse` de `Edit|Write`, solo la pausa.** Si el rango a reemplazar se superpone con una desviación conocida (`desviaciones.csv`, ubicada por contenido desde `git show <hash>:<ruta>`), el hook devuelve `Preguntar` con la desviación, su porqué y su fecha.
      - Claude Code pregunta. En Pi pregunta si hay interfaz y bloquea si no. En Codex bloquea.
      - Si el archivo no tiene desviaciones, este paso no corre ningún git.
    - **Después de editar, en el `PostToolUse` de `Edit|Write`, el porqué como contexto.** Se ubica el texto reemplazado en la versión de `HEAD` del archivo, se corre `git blame -w` (sin `-C`, por L8) de ese rango en `HEAD`, y entran como contexto hasta 2 líneas `<fecha> <hash corto>: <primer párrafo del cuerpo en una línea>`, sin los trailers conocidos (L8).
      - El agente lo lee justo después de la edición y puede reconsiderarla. Es lo que align hace en los hosts que no tienen contexto antes de editar.
      - El contexto va en el post porque ningún host puede mostrar un `Contexto` en el pre: los tres declaran solo `Bloquear` y `Preguntar`.
    - **El evento.** `Herramienta` (`odd_ws/eventos.py`) suma el texto que se reemplaza:
      - Claude Code, el `old_string` del `Edit` o el archivo entero de un `Write` que pisa;
      - Codex, las líneas quitadas y de contexto del `apply_patch` de ese archivo;
      - Pi, el campo de su entrada si lo trae. Si no lo trae, sin texto, y entonces sin pausa ni contexto, y se documenta.
    - **Lo que no cambia.**
      - El sub-chequeo va aislado (`comun._aislada`) y se combina con `comun.combinar`, así que una falla suya nunca borra el bloqueo del primer toque.
      - El blame tiene su propio plazo (`_restante(1.5)`) y el entorno limpio.
      - Un timeout o un error sale como «no se pudo chequear», un archivo sin trackear como «sin historia», y un archivo nuevo calla.
    - **La perilla `porque_al_editar`:** `"todo"` (la pausa y el contexto), `"indice"` (solo la pausa) y `"apagado"`. Se valida como `perfil` en `config_loader.py`, y se registra en `bootstrap._cargar_en_temporal` y `doctor.chequear_config`.
  - **Decisión de diseño (primera versión, de L1):**
    - **Dónde corre.** En el hook `PreToolUse` de `Edit|Write` (`verificar_capa.py`), solo para archivos de un repo de la config.
      - En un `Edit`, el hook busca el texto a reemplazar en el archivo actual y saca su rango de líneas.
      - En un `Write` que pisa un archivo que ya existe, el rango es el archivo entero.
      - Hay un tope de 400 líneas.
    - **Qué corre.** `git blame -w -C --porcelain -L <ini>,<fin>` con un plazo de 1,5 s, y después la fecha y el cuerpo de cada commit. Todo git corre con el entorno limpio (`comun.entorno_git()`).
    - **Qué muestra, como contexto, sin frenar.** Por cada commit distinto, hasta 2, una línea: `<fecha> <hash corto>: <primera línea con texto del cuerpo>`, sin los trailers como `Co-Authored-By`. Un commit sin cuerpo no se muestra. Si no queda nada que mostrar, calla, como I83.
    - **Cuándo pausa.** Pausa con `ask` solo si el rango a reemplazar se superpone con las líneas de una desviación conocida de la instancia (`.claude/reglas/desviaciones.csv`, I92). El mensaje nombra la desviación, su porqué y su fecha. En Codex y Pi, donde una pregunta se vuelve bloqueo, lo frena.
      - Las líneas de la desviación se leen en su `<hash>` (`git show <hash>:<ruta>`, rango `<ini>-<fin>`) y se ubican por contenido en el archivo actual.
      - No se usa el commit del blame, porque el `@hash` de una desviación marca dónde estaban sus líneas y no siempre el commit que las escribió.
      - Si ya no se encuentran, la desviación no pausa, y el contexto lo dice en una línea.
    - **Las fallas.** Un timeout o un error del blame sale como «no se pudo chequear el porqué de estas líneas», nunca como silencio.
      - Un archivo que existe sin trackear sale como «sin historia».
      - Un archivo nuevo, que todavía no existe, calla.
      - Una falla interna del chequeo nunca cambia el veredicto del resto del hook.
    - **La perilla.** Una clave opcional, `porque_al_editar`, en `workspace.config.json`:
      - `"todo"`, por defecto: contexto y pausa;
      - `"indice"`: solo la pausa de las desviaciones;
      - `"apagado"`.
- **S2** (I91, lo que se quita vuelve como regla). «Lo que un ticket quita vuelve como regla: al cerrar, si el diff saca una dependencia, un archivo o un patrón, `cerrar` pregunta si puede volver, y si no puede, propone la regla que lo frena.»
  - **Decisión de diseño:**
    - Un script lista lo que el diff del ticket quitó, por repo y desde su base:
      - los archivos borrados;
      - las dependencias que salieron de un manifiesto conocido: `package.json` (`dependencies` y `devDependencies`), `requirements*.txt`, `pyproject.toml`, `go.mod`, `*.csproj` (`PackageReference`), `build.gradle` / `build.gradle.kts` y `Cargo.toml`.
    - **Supuesto:** «un patrón» genérico no se detecta solo. Lo nombra el usuario en la pregunta.
    - `cerrar` muestra esa lista en su triaje y pregunta, por cada ítem, si puede volver. Si no puede, propone una regla `chequeo` con su caso sembrado (la línea que lo vuelve a agregar), por la graduación de siempre (I22), y anota el porqué.
    - El núcleo de `cerrar` tiene 15 bytes libres (tope de 13.312 en `memorias.tests.py`). El paso va en una referencia, y si hace falta una línea en el núcleo, se libera moviendo texto a las referencias.
- **S3** (la versión). Se actualizan:
  - el CHANGELOG de la `0.16.0`;
  - `Doc/actualizar.md`, si cambia alguna plantilla;
  - la versión en los dos `plugin.json` y en `package.json`, el README y `Doc/`;
  - `tools/huellas.py`.

  Después, un verificador independiente. Publicar lleva el ok del autor y su auditor.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento y su espejo en engram | inline | hecha | |
| T1 | S1 | El blame antes de editar | un explorador y después un solo writer (motivo: el respaldo de contexto del orquestador) | hecha (L4) | `bfd7115` |
| T2 | S2 | Lo que se quita vuelve como regla | un solo writer, después de T1 (motivo: el respaldo de contexto del orquestador) | hecha (L5) | `e49fdbc` |
| T3 | S3 | El CHANGELOG, la versión, el verificador y publicar con el ok del autor | docs inline; verificador delegado | versión lista (L6); verificador: B1 y B2 corregidos y recomprobados (L7, L8); auditoría PUBLICABLE CON NOTAS, notas aplicadas (L9); con el ok del autor para publicar | `1419e9e`, y la corrección de L8 |

## Log

- **L1** (2026-11-24) El autor aceptó el orden de las versiones, con la `0.16.0` = I90 e I91: «Si, va ese orden, arranca con la 0.14.0».
  - Después dejó la jornada a criterio del orquestador: «Apartir de ahora te dejo a tu criterio, probablemente antes de sacar la version enviare un auditor, asi que tu sigue trabajando el resto de versiones solo dejalas listas que mañana miramos en que quedamos ya te dejo libremente espero que nada que interrumpa».
  - Y pidió, solo para este loop: «intenta trabajar con menos agentes paso a paso solo lo necesario».
- **L2** (2026-11-25) Lo que sale de R15 y R16 para esta feature:
  - `guard_comandos` ya devuelve `ask` (`guard_comandos.tests.py:1029`).
  - Las desviaciones de I92 ya traen su `ubicacion` con `@hash`, y ese es el índice de la pausa.
  - Todo git que mire un repo de la config tiene que usar el entorno limpio, porque el pre-commit corre las suites con `GIT_INDEX_FILE`.
  - El núcleo de `cerrar` está a 15 bytes de su tope.
- **L3** (2026-11-25) El mapa del explorador, sobre `44fffdf`. Dos hallazgos frenaban S1 tal como estaba en L1:
  - **El evento no trae el texto de la edición.** `Herramienta` (`eventos.py:10-31`) solo lleva rutas y comando. Claude Code lee `file_path` y `command`, Codex tira el texto del parche, y Pi lee solo `input.path`.
  - **Ningún host puede mostrar un `Contexto` en el `PreToolUse`.** `EXPRESABLES[PRE]` es `(Bloquear, Preguntar)` en los tres (`claude_code.py:23`, `codex.py:15`, `pi.py:20`), y `capacidades.tests.py` solo deja degradar a `Bloquear`.
  - **Más datos del mapa:**
    - `EMITE[PRE]` de `verificar_capa` tiene que sumar `Preguntar` (lo controla `capacidades.tests.py:124-130`).
    - `correr` convierte cualquier excepción en silencio: un sub-chequeo sin aislar borraría el bloqueo del primer toque.
    - `clasificar` devuelve `None` para un archivo de repo sin capa, así que hace falta separar la parte que dice a qué repo pertenece una ruta.
    - Dos pruebas de `verificar_capa.tests.py` (:229-235 y :245) suponen que el pre no corre git y que un archivo sin trackear calla.
  - **Para S2:**
    - El núcleo de `cerrar` tiene 14 bytes libres, con un tope estricto. Se puede mover a una referencia el detalle de la foto de la entrega, unos 650 bytes.
    - Ningún script calcula lo que quitó un ticket: el script nuevo reusa `recibo.elegir_base`, `recibo.git` y `triaje.recolectar_repo`.
    - Ojo con dos casos: `triaje` usa `--no-renames`, así que un renombre parece un borrado y hace falta `--find-renames`. Y después del merge del ticket, el merge-base es `HEAD`, así que el diff sale vacío.
  - **La decisión revisada de S1** (arriba) resuelve los dos frenos: la pausa queda en el pre, porque `Preguntar` sí se expresa ahí, y el contexto pasa al post. Así el pre no corre git en el caso común.
  - **El tamaño estimado:** S1, unas 550 a 700 líneas; S2, unas 450 a 600.
- **L4** (2026-11-25) T1, un writer, desde `bcd3524`, con la corrección de R16 ya integrada. Lo cortó el límite de 5 horas y se lo retomó con su contexto. Cubrió S1 con el diseño revisado de L3.
  - **Lo nuevo:**
    - `odd_ws/porque.py` reúne el blame, la ubicación por contenido y las desviaciones.
    - `Herramienta.reemplazos` lleva pares `(ruta, texto)`, donde `None` es el archivo entero. Los llenan los tres adaptadores:
      - Claude Code, el `old_string` del `Edit` y el archivo entero de un `Write`;
      - Codex, los hunks de su `apply_patch`, con `Move to` en la ruta de origen;
      - Pi, `edits[].oldText`, y su `write` cuenta como archivo entero.
    - `verificar_capa` suma la pausa en el pre y el contexto en el post, aislados y combinados con lo que ya devolvía.
    - La clave `porque_al_editar` se valida, la registran el bootstrap y el doctor, y un valor inválido el hook lo toma como `"todo"`.
    - Codex y Pi tienen su texto para una edición bloqueada.
  - **Decisiones del writer que se aceptan:**
    - Un `Write` sobre un archivo que no está en `HEAD` calla, y solo un `Edit` dice «sin historia», porque después de escribir no se distingue lo nuevo de lo sin trackear.
    - El texto reemplazado se ubica como subcadena exacta, con el CRLF normalizado. Las líneas de una desviación se ubican línea por línea, sin la sangría.
    - Los commits van del más nuevo al más viejo, con hashes de 7 caracteres y el cuerpo cortado a 200. Los trailers solo se sacan si son el último párrafo.
    - La pausa falla abierta: sin hash, con un error de git, con timeout o si la desviación ya no está, no pausa.
    - Si el primer toque y la pausa caen en la misma edición, salen en un solo `Bloquear` que lleva los dos textos.
  - **Las dos pruebas de L3** (`verificar_capa.tests.py:229-235` y `:245`) pasan sin cambios.
  - **Expectativas que cambiaron** porque los adaptadores ahora llenan `reemplazos`: las pruebas de `eventos`, `claude_code`, `codex` y `pi` que listan sus campos. Además, el texto de Pi sin pantalla para una edición dice ahora «esta edición queda bloqueada».
  - **Test-first, con salvedades:**
    - 8 de las 10 pruebas nuevas del hook se vieron en RED. Las otras 2 solo comprueban silencio y ya pasaban: protegen contra una regresión.
    - `eventos.py` se editó antes que su prueba, y `porque.tests.py` se escribió después del módulo.
  - **Suites, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:** `verificar_capa` 146, `porque` 9, `capacidades` 37, `claude_code` 42, `codex` 48, `pi` 71, `base` 9, `config_loader` 121, `bootstrap` 212, `doctor` 245, `eventos` 9, `registro` 7, `guard_comandos` 83, `writer_guard` 125, `writer_stop` 61, `revisar_turno` 34, `triaje` 111, `desviaciones` 13 y 5, `comun` 63, y el shim 97. Todo en verde.
  - **Diferencial contra `bcd3524`**, con 172 payloads de los tres hosts:
    - con `porque_al_editar: "apagado"` y sin desviaciones, 0 diferencias;
    - sin la clave, las 28 diferencias son todas del post, el contexto nuevo, y el pre no cambia.
  - **Seguimientos, fuera de lo que el writer podía tocar:**
    - En `plugin/shim/pi.ts`, cuando el usuario rechaza la pausa de una edición (o falla la confirmación), el mensaje todavía dice «este comando queda bloqueado». Arreglarlo pide elegir el texto según la herramienta, sin cambiar lo que hoy ven los comandos, y una prueba de punta a punta.
    - Las notas del `MANIFIESTO` de Codex y Pi (P2 y P3) no nombran la pausa de una edición.
  - **Risk: items 2 y 3.** Cambia el comportamiento de un hook que puede pausar o bloquear una edición, y el evento suma un campo. Lo revisa el verificador de la feature.
  - **Scratch del writer:** `%TEMP%\tmp.xj4DhJgKYg`. Va a la limpieza del autor.
- **L5** (2026-11-25) T2, un writer, desde `bfd7115`. Cubrió S2.
  - **`quitado.py`, de solo lectura,** lista por repo lo que el diff quitó desde la base:
    - los archivos borrados, con `--find-renames`, así que un renombre no cuenta;
    - las dependencias que salieron de `package.json`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `*.csproj`, `build.gradle(.kts)` y `Cargo.toml`, cada una con la línea que la declaraba en la base, que es el `sembrado` de su regla.
  - **Tiene `--json`.** Con el diff vacío lo dice y pide la base con `--repo RUTA#BASE`. Sale con 2 por un error de uso o de entorno.
  - **Reusa** `recibo.elegir_base` (sin ticket), `recibo.git`, `recibo._partir_repo` y `triaje.decodificar`.
  - **`cerrar`:** el paso 2 suma una línea que corre `quitado.py`, y el detalle va en la referencia nueva `references/quitado.md`: qué preguntar por cada ítem y cómo proponer la regla con su sembrado. Si nada se quitó, `cerrar` no dice nada.
  - **El núcleo de `cerrar`** pasa de 13.297 a 13.302 bytes, con un tope estricto de 13.312. La foto de la entrega del paso 6 (648 bytes) se movió a «La foto de la entrega» en `references/entrega.md`.
  - **Decisiones del writer que se aceptan:**
    - **La base.** Es la de `#` o el merge-base, y no la base sellada de una revisión: esa escondería lo que el ticket quitó antes.
    - **El diff.**
      - Compara la base con la copia de trabajo, como `triaje`.
      - Un `M` cuenta como cambio solo si su `diff -U0` tiene contenido, porque con `diff.autoRefreshIndex=false` un archivo con solo la fecha cambiada aparece como `M`.
    - **Las dependencias.**
      - Se comparan por nombre, sin la versión, y moverlas de sección no cuenta.
      - `requirements` y `pyproject` normalizan como PEP 503, y NuGet sin distinguir mayúsculas.
      - Gradle cubre la notación de mapa, los alias del catálogo y `platform(...)`.
    - **Los casos borde.** Un manifiesto borrado sale como archivo. Uno ilegible da un aviso, nunca silencio.
    - **Sin capa que vea el archivo** (por ejemplo, ninguna con `.json`), la referencia propone la regla como `pasiva` o `criterios`.
    - **La prueba de guarda.** Una prueba comprueba que cada comando de `quitado.py` del núcleo y de la referencia lo acepta su parser.
  - **Test-first:**
    - RED: 0/20 antes del script.
    - GREEN: `quitado` 21/21, `memorias` 43/43 (con el tamaño del núcleo), `registro` 7/7, `recibo` 116/116 y `triaje` 111/111. Todo también con un `GIT_INDEX_FILE` ajeno.
    - Mutaciones: 14, cada una atrapada por la prueba de su regla.
  - **El ejemplo de regla de la referencia** se calibró en una instancia de prueba: `EJ-07 puede bloquear`.
  - **Risk: ninguno** de los ítems 1 a 6. El script es nuevo y de solo lectura, y en `cerrar` cambia el texto y se mueve un párrafo.
  - **Scratch del writer:** `%TEMP%\tmp.ziox3RJBtD` y la copia de mutaciones en el scratchpad de la sesión. Van a la limpieza del autor.
- **L6** (2026-11-25) T3, la versión, inline.
  - La `0.16.0` quedó en:
    - los dos `plugin.json` y el `package.json`;
    - el README;
    - `Doc/actualizar.md:28` y `Doc/uso.md:66`.
  - El CHANGELOG suma su sección, con la clave `porque_al_editar`.
  - Esta versión no cambia ninguna plantilla de la instancia: `git diff 44fffdf..HEAD -- plugin/plantillas` sale vacío.
  - `tools/huellas.py` dio 107 huellas, hasta la `0.16.0`. Como en la R16, al publicar hay que regenerar la tabla después de etiquetar las versiones anteriores.
  - En el roadmap, R18 queda «lista, sin publicar», con I90 e I91 «lista (`0.16.0`, sin publicar)».
  - Falta el verificador independiente (Risk items 2 y 3, por I90) y, después, el ok del autor y su auditor.
- **L7** (2026-11-25) El verificador independiente, sobre `1419e9e` contra `0b7255f`.
  - **S3: PASS.**
  - **S1 y S2: FAIL, por un bloqueante cada uno.** El resto pasa:
    - con `"apagado"`, 41 payloads reales de los tres hosts dan una salida idéntica a la base;
    - el pre no corre git si el archivo no tiene desviaciones;
    - no se pierde ningún bloqueo del primer toque ni ningún hallazgo de capa;
    - cada pieza nueva va aislada;
    - la pausa se ve bien en los tres hosts y falla abierta;
    - `quitado.py` es de solo lectura, ignora los renombres y los cambios de versión, y cubre los 7 manifiestos;
    - suites: 60 de Python (2.845 pruebas) y el shim en verde, también con un `GIT_INDEX_FILE` ajeno.
  - **B1 (S1).** Una desviación pausa la edición de cualquier copia idéntica de sus líneas. Con dos bloques `BEGIN CATCH … END CATCH` iguales en un SP, editar el que no es desviación igual pregunta, y en Codex se bloquea.
  - **B2 (S2).** `quitado.py` busca la línea que declaraba una dependencia como subcadena en todo el archivo. Para `pytest` toma `name = "pytest-timer"`, y esa línea terminaría como el sembrado de la regla.
  - **Advertencias que entran en el mismo lote de corrección,** porque pesan en el uso real:
    - `git blame -C` tarda unas diez veces más que `-w` solo. En un repo de 2,6k commits, un `Write` de 400 líneas siempre se pasa del plazo de 1,5 s.
    - El porqué toma el primer renglón físico del cuerpo, que en un commit con las líneas envueltas queda cortado a mitad de frase.
    - Un cuerpo de una línea como `Motivo: …` se descarta como trailer.
  - **Advertencias que quedan para el autor y su auditor:**
    - En Codex, y en Pi sin pantalla, el primer toque combinado con la pausa dice que el reintento pasa, pero el reintento también se bloquea.
    - Un `porque_al_editar` inválido corre como `"todo"`, a propósito, y el doctor lo marca en FALTA.
    - `quitado` no ve `[tool.poetry.dependencies]`, y en Go toma un cambio de versión mayor de la ruta como una dependencia quitada.
    - Un `move` con edición en Codex calla en el post.
    - El texto de Pi al rechazar la pausa (L4).
  - **La latencia:**
    - El pre de un `Edit` sin desviaciones pasa de unos 0,30 s a unos 0,32 s.
    - El post pasa de 0,29 s a unos 0,72 s.
    - El blame en el proceso tarda de 0,2 a 0,8 s en odd-ws.
  - **La corrección** va en un solo lote, con un writer. Después se recomprueban solo B1 y B2.
  - **Scratch del verificador:** `%TEMP%\tmp.BOwGqKrCKf`. Va a la limpieza del autor.
- **L8** (2026-11-25) La corrección, un solo lote con un writer, y la recomprobación de B1 y B2.
  - **B1.** `porque.rango_de_la_desviacion` cuenta una sola copia de las líneas: la que sigue en `<ini>-<fin>` y, si se movió, la más cercana. Editar otra copia idéntica no pausa.
  - **B2.** `quitado.py` busca la línea que declaraba la dependencia por su nombre normalizado y entero, dentro de la sección que declara las dependencias de cada manifiesto, nunca como subcadena. En un `.csproj`, una referencia comentada ya no cuenta.
  - **Las advertencias del mismo lote:**
    - el blame va sin `-C`, con el porqué y las cifras en `Doc/diseno.md`;
    - el porqué es el primer párrafo del cuerpo en una línea, o su primera viñeta, cortado en una palabra pasados 200 caracteres;
    - solo salen los 10 trailers conocidos del último párrafo, así que `Motivo: …` se muestra.
  - **RED antes de cada arreglo, y GREEN.** Suites del writer, también con un `GIT_INDEX_FILE` ajeno:
    - `porque.tests.py` 11/11;
    - `verificar_capa.tests.py` 150/150;
    - `quitado.tests.py` 28/28;
    - `registro.tests.py` 7/7.
  - **La diferencial del verificador** (42 payloads por 3 casos del CSV):
    - con `"apagado"`, la salida es idéntica byte a byte;
    - en el modo por defecto, solo cambia lo esperado.
    - Un `Write` de 400 líneas en el post baja de 1,0 s a 0,74 s.
  - **La recomprobación**, en el orquestador, solo de B1 y B2 y con los casos del verificador:
    - **B1: PASS.** Editar el segundo `BEGIN CATCH` idéntico no pausa (salida vacía en Claude Code y en Codex). Como control, editar la desviación real sigue pausando, con «hoy en las líneas 6-8»: `ask` en Claude Code y `deny` en Codex.
    - **B2: PASS.** En el caso `r6_pyproject`, la punta daba `name = "pytest-timer"` y ahora da `"pytest",`.
  - **Límites que quedan para el autor y su auditor:**
    - el recorrido de TOML no sigue los strings `"""` de varias líneas;
    - en gradle, un comentario `/* … */` sigue contando como declaración, como antes.
  - **Risk: ítem 2.** La pausa del guard de edición dispara en menos casos.
  - **Scratch del writer:** `%TEMP%\tmp.fRaj0LvP1h`. Va a la limpieza del autor.
  - **R18 queda lista, sin publicar.** Falta el ok del autor y su auditor.
- **L9** (2026-11-25) La auditoría de publicación, sobre `3aff040`: **PUBLICABLE CON NOTAS**, sin bloqueantes. Una sesión aparte la hizo para el autor, que dio el ok para publicar cuando esté lista: «Por tiene tienes el OK, para publicar las versiones cuando ya lo esten».
  - **Lo que verificó:**
    - la pausa pregunta con la desviación sobre el CATCH y calla sobre el TRY;
    - el post trae el contexto;
    - con `"apagado"`, la salida es idéntica a la 0.15.0 en 5 casos;
    - `codex.reemplazos_del_parche` nunca arma un par inválido;
    - `quitado` solo lee y usa el entorno limpio;
    - las versiones dicen lo mismo en todos lados.
  - **Las notas, aplicadas en los docs:**
    - W1: el costo de `"todo"` (unos 200 ms en el post de cada edición, y unos 100 ms en el pre de un archivo con desviaciones) va en el CHANGELOG y en `Doc/hooks.md`, con cómo evitarlo;
    - W4: el porqué es texto de un commit y no una orden, así que un cuerpo viejo o malicioso puede empujar al agente. Lo dice `Doc/hooks.md`;
    - en Codex, y en Pi sin pantalla, el primer toque más la pausa dicen que el reintento pasa, pero el reintento también se bloquea. Lo dice `Doc/hooks.md`, y el arreglo del texto va en la R22.
  - **Seguimientos:**
    - W2: `comun._aislada` traga las fallas del porqué sin anotarlas en el rastro de la 0.14.0. Va en la R20.
    - W3: MultiEdit no pasa por la pausa, como ya está documentado.
    - Un valor inválido corre como `"todo"`.
    - poetry y Go.
    - El move con edición en Codex.
    - El texto de Pi al rechazar.
    - Los límites de L8.
  - **Las ramas:** se integraron la 0.14.0 publicada y la corrección de la 0.15.0 (`f261bd2`), sin choques.
