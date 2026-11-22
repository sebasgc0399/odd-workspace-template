# Los huecos chicos: el push forzado, los bloqueos con su comando, la leyenda de `tipo`, las plantillas por versión, la instalación a la vista y la página al día (R14)

Objetivo: cerrar cinco huecos chicos que salieron del uso real, del Discord y del plan de la serie de videos: I49 (con el M3 de Maik), I76, I77, I82 e I70.
Rama: `feat/huecos-chicos`, en `D:/Project/odd-ws-wt/huecos`, desde `origin/main` (`9444075`). Los writers trabajan en sus propios worktrees desde `origin/main` y el orquestador integra sus ramas. Entrega: un commit por unidad, con I49 y el chequeo de I70 en commits propios; sale en la `0.13.3`, con el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap. Lo marcado como **decisión de diseño** no lo pidió el autor con esas palabras: es cómo se cumple su pedido. Lo marcado como **supuesto** está por confirmar.

- **S1** (I49, el push forzado). «El guard bloquea toda variante forzada de `git push`, también `--force-with-lease`, `--force-if-includes` y el `+refspec`, y le sugiere al usuario la forma segura para correrla a mano.» El porqué, del roadmap: «un lease sin `ref:sha` lo satisface cualquier `fetch`».
  - **Decisión de diseño:** cuentan como forzados `--force`, `-f` (también dentro de un bloque corto, como `-uf`), `--force-with-lease` en cualquier forma (sin valor, `=<ref>` o `=<ref>:<sha>`), `--force-if-includes` y un refspec con `+`. Se bloquean siempre, sin pregunta, también en un repo protegido.
  - **Supuesto:** `--mirror` también se bloquea, porque git fuerza las refs que actualiza. La idea no lo nombra.
  - **La forma segura:** el mensaje le dice al agente que no lo corra, y le da al usuario el comando para correrlo a mano: `git push --force-with-lease=<rama>:<sha que esperas> <remoto> <rama>`, después de mirar `git log <remoto>/<rama>`.
  - Los docs que hoy recomiendan el lease al agente cambian. `Doc/equipo.md`, que le indica el comando al usuario, pasa a la forma segura.
- **S2** (el M3 de Maik en el guard). «todo bloqueo cita el comando literal». Cada bloqueo y cada pregunta de `guard_comandos` muestra el comando tal cual lo mandó el agente: en Codex y Pi una pregunta se vuelve bloqueo. También el bloqueo de un comando de `writer_guard` (`writer_guard.py:1389`), el otro guard que bloquea comandos.
  - **Supuesto:** un comando de más de 300 caracteres se corta con «…», para que un heredoc no tape el motivo.
- **S3** (el M3 de Maik en la capa). «y `verificar_capa` el fragmento que disparó la regla». Cada hallazgo muestra su `fragmento` cuando la regla lo trae, en los dos sitios que formatean hallazgos: `verificar_capa._formatear` y `writer_stop._describir`, que también usa `revisar_turno`. Sin `fragmento`, el hallazgo se ve como hoy.
- **S4** (I76). «Los códigos de la columna `tipo` de la matriz (`CE`, `CC`, `PR`, `CR`, `MT`, `META`) dicen qué significan en algún lado.»
  - **Decisión de diseño:** la leyenda va en `plugin/skills/cerrar/references/matriz.md`, donde hoy dice «La plantilla no los define», y en `Doc/capas-y-reglas.md`, junto al ejemplo que usa `CE`.
  - Los significados salen de la metodología de origen del autor: CE, convención de escritura; CC, convención con caso; PR, procedimiento de revisión; CR, contexto de repos; MT, matiz transversal. **Supuesto:** META son los metadatos del agente, como su frontmatter; en el origen, META marca esas líneas.
- **S5** (I77). «`Doc/actualizar.md` lista cada cambio de plantilla por versión.»
  - La sección «Después de actualizar: las plantillas de la instancia» suma las versiones que faltan (L2) y, si esta feature cambia una plantilla, la `0.13.3`.
  - **Decisión de diseño:** el CHANGELOG ya publicado no se reescribe.
- **S6** (I82). «La instalación se ve sin abrir nada, con el método de cada CLI listo para copiar y pegar, y el comando de gentle-shell lleva el número de la versión.» El pedido de _00_: «Sebas, la instalacion es complicadeta de encontrar, (y si puede ser deja puesta la versión, que sea cortar y pegar)», y «pon un 👉 INSTALL👈 y el/los metodo/s de install».
  - **Decisión de diseño:** en el README y en la página, «Instalación» deja de tener desplegables cerrados, y cerca del principio hay un acceso a la instalación de cada CLI.
  - `odd-ws--v<versión>` pasa al número de la versión en el README, la página, `Doc/uso.md` y `Doc/actualizar.md`.
- **S7** (I70). «Un chequeo que haga fallar el pre-push si la página y el README no coinciden en la versión y en los requisitos.»
  - **Decisión de diseño (L3):** corre con `tools/entrega.py`, en un push a `main` o a una etiqueta `odd-ws--v*`. Compara contra la versión del `plugin.json` del commit empujado:
    - la «Versión actual» del README;
    - la versión de la página;
    - cada `odd-ws--v<X.Y.Z>` de un comando en el README, la página, `Doc/uso.md` y `Doc/actualizar.md` (S6).
  - Además, la tabla de requisitos del README tiene que ser igual a la de la página.
  - La página se lee de la rama local `gh-pages` o, si no existe, de `origin/gh-pages`. Si no hay ninguna de las dos, el chequeo avisa y deja pasar.
  - Por eso la página de una versión se commitea antes de empujar `main`. `CONTRIBUTING.md` («Una entrega») suma ese paso y el de la «Versión actual» del README.
- **S8** (nada se rompe). Fuera de lo que piden S1 a S7, los scripts conservan su comportamiento. Las instancias que ya existen no tienen que editar nada. El CHANGELOG lleva la `0.13.3`.
- **S9** (la prueba). Un verificador independiente revisa la feature entera al final, con foco en S1, S2 y S7, que tocan el guard y el pre-push.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento, su espejo en engram y el enlace en R14 | inline | hecha | (con T2) |
| T1 | S1, S2 | El guard: el push forzado y el comando literal en cada bloqueo | delegada: writer A en `D:/Project/odd-ws-wt/huecos-guard`, en paralelo con T5 (dos unidades independientes de más de 100 líneas, con superficies disjuntas) | pendiente | |
| T2 | S3 | El fragmento en los hallazgos de la capa | inline (unidad chica) | hecha (L4) | |
| T3 | S4, S5 | La leyenda de `tipo` y las plantillas por versión | inline (docs) | pendiente | |
| T4 | S6 | La instalación a la vista y con la versión puesta; la página, en la rama local `gh-pages` | inline (docs) | pendiente | |
| T5 | S7 | El chequeo de la página y el README en el pre-push | delegada: writer B en `D:/Project/odd-ws-wt/huecos-pagina`, en paralelo con T1 | pendiente | |
| T6 | S8, S9 | El CHANGELOG, el verificador independiente y la versión | docs inline; verificador delegado; publicar, con el ok del autor | pendiente | |

## Log

- **L1** (2026-11-22) El autor, tal cual, en orden:
  - «Bueno ahora que cosas tenemos pendientes en el roadmap».
  - «Vale me parece bien organicemos para que trabajemos y saber que versiones se vienen».
  - A la propuesta de R14 (`0.13.3`: I49, I77, I76 e I70), R15 y R16: «Me parece bien».
  - A «¿Lo sumo a R14 como I82?»: «Si».
  - «Vale arranquemos».
- **L2** (2026-11-22) La evidencia de partida, del mapa de un explorador de solo lectura sobre `9444075`:
  - **S1:**
    - El guard tiene dos pasadas. La gruesa (`guard_comandos.py:585-588`) se apaga si `--force-with-lease` aparece en cualquier parte del texto y lo recomienda (:588).
    - La fina (`_push` y `_push_forzado`, :270-329) deja pasar el push entero con un lease sin valor, incluso con `+rama` (:316-317; test :232).
    - `--force-if-includes` y `--mirror` no se tratan.
    - Los tests que fijan el lease que pasa: :1676, :1707 y :1330, el repo protegido. El mensaje literal de un bloqueo se cita en `README.md:64-67`, `Doc/hooks.md:3-6` y la página (:121-122).
  - **S2:** ningún mensaje cita el comando literal, aunque `decidir` lo tiene (:1117).
    - Los bloqueos salen de `_mensaje` (:1078) y de `_mensaje_de_capa` (:1086), y las preguntas de `_pregunta` (:846).
    - En Codex y Pi, una pregunta se vuelve bloqueo (`codex.py:228`, `pi.py:392`).
  - **S3:** el contrato del hallazgo ya trae `fragmento` (`Doc/capas-y-reglas.md:6`), pero es opcional (`verificar_capa.py:210-211`). Lo formatean `verificar_capa._formatear` (:190-195) y `writer_stop._describir` (:209-214).
  - **S4:** `matriz.py:19` solo valida los códigos, y `cerrar/references/matriz.md:11` dice que la plantilla no los define. Los códigos entraron en `5e10ac2`, portados de la metodología de origen.
  - **S5:** la sección de `Doc/actualizar.md` (:37-49) solo cubre la `0.9.0`. Faltan estos cambios de plantilla:
    - `0.2.2` (`9d288e3`): el `CLAUDE.md` suma «Si también usas gentle-ai».
    - `0.3.1` (`f287253`): el `pre-commit` con `python3`.
    - `0.7.0` (`6dae9a9`): la línea de `/odd-ws:paquetes`.
    - `0.10.0` (`5a45aeb`): la línea de `/odd-ws:enlaces`, que tampoco está en el CHANGELOG.
    - `0.12.0` (`b192aa5` y `bf6cc5b`): `CLAUDE.controles.md`, nuevo, y `reglas/verificar.tests.py`.
  - **S6 y S7:**
    - En el README, Claude Code está en un `<details open>` (:103-120), y Codex (:122-139) y Pi (:141-160) en desplegables cerrados.
    - `<versión>` en comandos: `README.md:150`, `pages/index.html:235`, `Doc/uso.md:66` y `Doc/actualizar.md:28`.
    - Los requisitos ya están desfasados: el README tiene 6 filas (:92-99) y la página 5 (:191-200), con otro texto en la fila de Pi.
    - El pre-push (`.githooks/pre-push`) corre `barrido.py` y `tools/entrega.py`. `entrega.py` solo revisa los push a `main` y a etiquetas (:176-177) y lee archivos con `git show <sha>:<ruta>` (:58-69).
    - `git show origin/gh-pages:index.html` funciona desde `rel`. El worktree de la página no tiene `.githooks`, así que un push desde ahí no corre ningún chequeo.
    - `CONTRIBUTING.md:33-45` no nombra la «Versión actual» del README ni la página. Ningún chequeo compara el README ni la página con `plugin.json`: el único es `capacidades.tests.py:541-543`, con `package.json` y los dos `plugin.json`.
- **L3** (2026-11-22) Las decisiones de diseño:
  - **S7:** el chequeo va en un push a `main` porque el push de la página no pasa por ningún hook (L2). Compara contra la página local porque, al soltar una versión, la página nueva está commiteada pero todavía no publicada. Sin rama de la página deja pasar con un aviso: es el caso de un clon de un colaborador, al que la página no le toca.
  - **Risk:** T1, item 2 (el guard). T5, item 5 (el pre-push del repo, parte de la entrega). Cada uno va en su commit, y el verificador independiente de S9 cubre los dos.
- **L4** (2026-11-22) T2, inline:
  - **El cambio:** `verificar_capa.cita_del_fragmento(h)` da ` en «<fragmento>»` (los espacios y saltos se juntan en uno, y se corta a 120 caracteres con «…»), o nada sin `fragmento`. `_formatear` y `writer_stop._describir` lo ponen después de la línea: `[T-02 CRITICAL] linea 4 en «MALO»: está mal → así`. `Doc/diseno.md` («Hallazgo») lo documenta.
  - **RED:** los dos tests nuevos (`test_la_cita_del_fragmento_va_en_una_linea_y_corta_lo_largo` y `test_un_hallazgo_de_archivo_con_fragmento_lo_cita`) y la aserción exacta de `test_salida_con_bloqueo_exit_2_stderr_en_bytes_utf8`: 128/131.
  - **GREEN:** `verificar_capa` 131/131, `writer_stop` 60/60, `revisar_turno` 33/33 y `paquetes` 17/17. Las aserciones que fijaban el formato viejo con un fragmento (`MALO` o `XX`) pasan al nuevo. Las negativas («`linea 1:` no está») también, para que no pasen solas. Las de hallazgos sin fragmento (T-03, T-06, T-08, ALF-01, entre otras) quedan igual y siguen en verde.
  - **Diferencial** contra `9444075`, en un scratch fuera del worktree: sin fragmento, o con uno vacío o `None`, la salida es idéntica en los dos formateadores; con fragmento solo se suma la cita.
  - **Risk:** none (cambia un mensaje que lee el agente; ningún contrato lo parsea, y los tests que lo fijaban se actualizaron).
