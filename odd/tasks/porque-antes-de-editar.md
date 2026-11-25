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
    - **Después de editar, en el `PostToolUse` de `Edit|Write`, el porqué como contexto.** Se ubica el texto reemplazado en la versión de `HEAD` del archivo, se corre `git blame` de ese rango en `HEAD`, y entran como contexto hasta 2 líneas `<fecha> <hash corto>: <primera línea del cuerpo>`, sin trailers.
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
| T1 | S1 | El blame antes de editar | un explorador y después un solo writer (motivo: el respaldo de contexto del orquestador) | hecha (L4) | |
| T2 | S2 | Lo que se quita vuelve como regla | un solo writer, después de T1 | pendiente | |
| T3 | S3 | El CHANGELOG, la versión, el verificador y publicar con el ok del autor | docs inline; verificador delegado | pendiente | |

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
