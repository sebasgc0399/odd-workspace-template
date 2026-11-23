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
  - La página se lee de la rama local `gh-pages` o, si no existe, de `origin/gh-pages`. Si no hay ninguna de las dos, se salta solo la parte de la página, con un aviso: el README y los docs se siguen revisando (L6).
  - Por eso la página de una versión se commitea antes de empujar `main`. `CONTRIBUTING.md` («Una entrega») suma ese paso y el de la «Versión actual» del README.
- **S8** (nada se rompe). Fuera de lo que piden S1 a S7, los scripts conservan su comportamiento. Las instancias que ya existen no tienen que editar nada. El CHANGELOG lleva la `0.13.3`.
- **S9** (la prueba). Un verificador independiente revisa la feature entera al final, con foco en S1, S2 y S7, que tocan el guard y el pre-push.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento, su espejo en engram y el enlace en R14 | inline | hecha | (con T2) |
| T1 | S1, S2 | El guard: el push forzado y el comando literal en cada bloqueo | delegada: writer A en `D:/Project/odd-ws-wt/huecos-guard`, en paralelo con T5 (dos unidades independientes de más de 100 líneas, con superficies disjuntas) | hecha (L5) | `d9331d8` |
| T2 | S3 | El fragmento en los hallazgos de la capa | inline (unidad chica) | hecha (L4) | `9f61655` |
| T3 | S4, S5 | La leyenda de `tipo` y las plantillas por versión | inline (docs) | hecha (L7) | |
| T4 | S6 | La instalación a la vista y con la versión puesta; la página, en la rama local `gh-pages` | inline (docs) | hecha (L7) | página: `83b55b8` (local) |
| T5 | S7 | El chequeo de la página y el README en el pre-push | delegada: writer B en `D:/Project/odd-ws-wt/huecos-pagina`, en paralelo con T1 | hecha (L6) | `6a40970` |
| T6 | S8, S9 | El CHANGELOG, el verificador independiente y la versión | docs inline; verificador delegado; publicar, con el ok del autor (L8) | hecha (L9) | `release/0.13.3` |

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
- **L5** (2026-11-22) T1, del writer A en `feat/huecos-guard`:
  - **S1:**
    - El predicado `_opcion_forzada` lo usan las dos pasadas y reconoce `--force`, `--force-with-lease` (con o sin valor), `--force-if-includes` y `--mirror`, también abreviadas, como las acepta git (`--forc`, `--mirr`). `-f`, `-uf` y el refspec con `+` siguen el parseo de antes.
    - El lease ya no apaga la pasada gruesa, y las dos pasadas dan el mismo motivo, `PUSH_FORZADO`, con la forma segura para el usuario. `--no-force-with-lease` solo pasa.
    - Sale el código del lease que cubría una ref (`LEASE_REF`, `REFS`, `HEADS` y `_sin_prefijo`).
  - **S2:** cada bloqueo y cada pregunta de `guard_comandos` (también las de plazo vencido o error interno), y el bloqueo de `writer_guard`, termina con la línea `Comando: «<literal>»`, cortada a 300 caracteres con «…». `_cita` está duplicada a propósito en los dos guards: un import que falle al armar un bloqueo lo volvería un permitir.
  - **Tests que cambian a propósito:**
    - En `CASOS`, 7 casos: 5 pasan de permitir a bloquear y 2 (el repo protegido y `--mirror`) de preguntar a bloquear.
    - 4 bordes de lease, y la sonda de :1330.
    - Los tests de :1676 y :1707.
    - Los motivos y prefijos de :1119, :1611 y :1615, que ahora dicen «git push forzado».
    - `pi.tests.py:1291` y `pi.test.ts:285`.
  - **Verification del writer:** `guard_comandos` 82/82, `writer_guard` 124/124 en una corrida, `codex` 46/46, `pi` 70/70 y `pi.test.ts` 74/74.
  - **Diferencial** sobre 137 filas en tres hosts: 44 iguales (todas permitidas), 27 que solo suman la cita, 24 con el motivo nuevo y la cita, 36 de permitir a bloquear, 6 de preguntar a bloquear y 0 otras diferencias.
  - **Chequeo del orquestador:** `guard_comandos.tests.py` 82/82. Pasan `--follow-tags`, `--message x && git push`, `-u origin feat/x` y `--no-force-with-lease`. Bloquean `--forc`, `+main` y `--force-with-lease=main:abc123`.
  - **Decisión de diseño ratificada:** cuenta como forzado todo prefijo de una opción forzada. Git acepta los prefijos únicos (`--force-w`, `--force-i`, `--mi`, `--mirr`). Los ambiguos (`--forc`, `--for`, `--fo`, `--f`) git los rechaza: bloquearlos no hace daño (corregido en L8). El costo son unos pocos falsos positivos en la pasada gruesa, como un `--mirror` de otro programa en un comando que también nombra git y push. Esa pasada ya bloqueaba un `--force` en cualquier lugar.
  - **Seguimientos** (estaban en la base, no los amplía esta feature): una opción o un refspec forzado entre comillas (`git push "--force" origin main`) pasa la capa 1, porque el texto entre comillas se lee como dato.
  - **El mensaje literal, para la página:** «guard-comandos bloqueó el comando: git push forzado (no lo corras tú: un lease sin `ref:sha` lo satisface cualquier `fetch`; para forzar con seguridad, el usuario mira `git log <remoto>/<rama>` y corre `git push --force-with-lease=<rama>:<sha que esperas> <remoto> <rama>`). Si la operación es deliberada, que la corra el usuario a mano.», más la línea `Comando: «git push --force origin main»`.
  - **Docs:** `README.md`, `Doc/hooks.md`, `Doc/diseno.md` y `Doc/equipo.md`. No cambia ninguna plantilla.
- **L6** (2026-11-22) T5, del writer B en `feat/huecos-pagina`:
  - **El chequeo** vive en `tools/entrega.py` y corre después de todos los chequeos de antes, sobre cada línea del push. Así un fallo de S7 no tapa uno viejo: la primera versión tapaba las notas de una etiqueta empujada detrás de `main`.
    - Cuando falla, lista todo lo que difiere con su `ruta:línea` y su arreglo, y dice de qué rama leyó la página.
    - Reusa la lectura con `git show`, que salió a `leer`, `texto_en` y `commit_de`.
  - **Decisión de diseño ratificada:** sin rama de la página se salta solo la parte de la página, con una línea `aviso:`. El README y los docs se siguen revisando.
  - **Lo que T4 tiene que respetar:**
    - la tabla de requisitos va bajo el primer `## ` del README que contiene «Instalación»;
    - en la página, bajo el primer `<h2>` con `id="instalar"` o con «instal» en el texto;
    - la página lleva una línea «Versión actual:»;
    - todo número X.Y.Z del pie es la versión.
  - **Tests:** 6 reglas con RED observado sobre el `entrega.py` sin cambios, más el caso en que todo coincide y 4 de preservación. Los tests que ya existían solo cambian sus fixtures, que ahora traen el README, los docs y la página al día. `entrega` 42/42, `barrido` 37/37 y `notas` 11/11.
  - **Diferencial** contra `9444075`: 14 escenarios iguales en stdout, stderr y código de salida. Solo cambian el README con otra versión, que ahora frena, y el aviso sin rama de la página.
  - **Lo que marca hoy sobre `9444075`** (es el trabajo de T4):
    - los `odd-ws--v<versión>` de `README.md:150`, `Doc/uso.md:66`, `Doc/actualizar.md:28` y la página (:235);
    - la fila de Pi, con otro texto en el README (:98) y en la página (:199);
    - la fila de gentle-shell (`README.md:99`), que falta en la página.
  - **Chequeo del orquestador:** `entrega.tests.py` 42/42.
  - **Seguimientos:**
    - los mensajes viejos de `entrega.py` usan voseo («Subí», «etiquetá»), en una herramienta del repo y no del producto;
    - re-empujar una etiqueta vieja se compara con la página de hoy;
    - `Doc/diseno.md` («La entrega en el pre-push», :1262-1273) no describe S7: se completa en T6.
  - **Risk:** item 5. Va en su commit.
- **L7** (2026-11-22) T3 y T4, inline:
  - **S4:**
    - En `cerrar/references/matriz.md`, la columna `tipo` dice qué es cada código y pide proponerlo y confirmarlo con el usuario. La fila vecina queda como ayuda si hay duda.
    - `Doc/capas-y-reglas.md` («La matriz») trae la misma leyenda.
  - **S5:** `Doc/actualizar.md` lista por versión lo que se copia a mano:
    - la `0.2.2`, la sección «Si también usas gentle-ai»;
    - la `0.3.1`, el `pre-commit` con `python3`;
    - la `0.7.0`, la línea de `paquetes`;
    - la `0.9.0`, que ya estaba;
    - la `0.10.0`, la línea de `enlaces`;
    - la `0.12.0`, la prueba `verificar_<capa>.tests.py` y `CLAUDE.controles.md`, nueva y sin nada que copiar.

    La primera etiqueta de cada commit sale de `git tag --contains <commit> --sort=v:refname`. El orden por defecto es alfabético y pone la `0.10.0` antes que la `0.2.2`.
    - **Decisión de diseño:** la sección cubre lo que el bootstrap no pisa y se copia a mano. Los writers ya tienen la suya (regenerar). El cambio de la `0.3.0` a las plantillas de writers y revisores, la generación por host, no se copia a mano.
    - En la `0.13.3` no cambia ninguna plantilla.
  - **S6, el README:**
    - Bajo la «Versión actual», la línea «**Instalar:**» lleva a cada CLI y al video.
    - «Por dónde empezar» enlaza Codex y gentle-shell.
    - Los tres `<details>` de «Instalación» pasan a `###`, así que se ven sin abrir nada y tienen ancla.
    - El bloque de Pi trae `npm i -g gentle-pi` y el comando con `0.13.2`, listos para copiar. La ruta del clon queda en una línea aparte.
  - **S6, los docs:** `Doc/uso.md` y `Doc/actualizar.md` llevan el número en lugar de `<versión>` y de `<versión nueva>`.
  - **S6, la página** (`83b55b8`, commit local en `gh-pages`, sin publicar):
    - los desplegables de Codex y gentle-shell, abiertos;
    - el comando con el número y `npm i -g gentle-pi`;
    - la tabla de requisitos igual a la del README, con la fila de Pi corregida y la de gentle-shell nueva;
    - el mensaje nuevo del guard (S1 y S2).
  - **Doc/diseno.md:** «La entrega en el pre-push» describe el chequeo de S7.
  - **Los números:** quedan en `0.13.2`, la versión del `plugin.json` de hoy, para que cada commit sea coherente. La entrega de T6 los sube a `0.13.3` junto con la página.
- **L8** (2026-11-22) La integración y el verificador independiente:
  - **La integración:** las ramas de los writers entraron con `--no-ff` (`7f0fea7` y `86404e4`), sin conflictos. Sobre `86404e4` con la página local `83b55b8`, `desfases_de_la_entrega` da `None`.
  - **El autor:** «ok autorizo publicacion» (2026-11-22), mientras corría el verificador. Un «ok» suelto anterior no se tomó como autorización.
  - **El veredicto, sin bloqueantes:**
    - S1 a S7 dan PASS. S8 queda PARCIAL solo por el CHANGELOG de la `0.13.3`, que es de T6.
    - El diferencial del guard, sobre 402 filas (67 comandos, tres hosts, con y sin repo protegido): 92 iguales, 70 que solo suman la cita, 143 con el motivo nuevo, 75 de permitir a bloquear y 22 de preguntar a bloquear, todas de un push forzado. Ninguna otra diferencia.
    - S7: todos los escenarios. Los chequeos de antes dan la misma salida, byte a byte, que la base.
    - S8, las suites sobre el árbol integrado: las 52 de Python con exit 0 (2679 pruebas) y node 97/97.
  - **Avisos atendidos:**
    - L5 decía que git acepta `--forc`: git 2.51 lo rechaza por ambiguo. L5 está corregido, y el bloqueo se mantiene.
    - `Doc/diseno.md` decía que la cita es siempre la última línea. En Codex y Pi la sigue la nota del host.
  - **Las sondas, como tests de regresión:**
    - `PUSHES_FORZADOS` suma `--force-w`, un `+main` después de `--recurse-submodules check`, `cmd /c … --mirror` y `(git push --mirror)`.
    - Sus tests suman el `Invoke-Expression` de PowerShell, y fijan que un `wget --mirror` en un comando con push bloquea, que es la decisión de L5.
    - Pasan `git push origin HEAD:+main` y `git push -of origin main`.
    - En la capa, un `fragmento` que es una lista no se cita.
    - La página local que manda sobre un `origin/gh-pages` viejo ya la cubría `test_sin_rama_local_la_pagina_se_lee_de_origin_y_la_local_manda_si_existe`.
    - Resultado: `guard_comandos` 82/82 y `verificar_capa` 131/131.
  - **Seguimientos** (ya estaban en la base o son de diseño, no bloquean):
    - el forzado por config (`git -c remote.origin.mirror=true push`, `-c remote.origin.push=+…`, `-c alias.p='push --force'`) y el forzado entre comillas;
    - S7 revisa toda aparición de `odd-ws--v…`, no solo las de un comando, así que un enlace a una etiqueta vieja frenaría la entrega;
    - re-empujar una etiqueta vieja se compara con la página de hoy;
    - la página no tiene un acceso por CLI cerca del principio, solo el botón «Instalar».
- **L9** (2026-11-22) La versión `0.13.3`, en `release/0.13.3` desde `origin/main`:
  - La rama entró con `--no-ff`. Subieron a `0.13.3` las tres versiones, la «Versión actual» del README y el comando de gentle-shell del README, `Doc/uso.md` y `Doc/actualizar.md`.
  - Se sumó la sección del CHANGELOG, y en el roadmap R14 y sus ideas quedaron hechas.
  - La página de la versión quedó commiteada en la `gh-pages` local (`8a86aa1`) antes de empujar `main`, como pide S7.
  - Publicar lo autorizó el autor (L8).
