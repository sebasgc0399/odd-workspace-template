# Changelog

Las notas de cada entrega de `odd-ws`. Cada versión es una sección `## <versión>`, y su contenido es el cuerpo del release que publica `.github/workflows/release.yml` cuando llega la etiqueta `odd-ws--v<versión>`. El pre-push no deja entregar una versión sin su sección.

## 0.16.0

**El porqué antes de editar: el agente ve por qué existen las líneas que toca, y lo que un ticket quita no vuelve sin que alguien lo decida.**

### Lo que cambia para ti

- **Después de editar, el agente ve el porqué de las líneas que reemplazó.** Lee la fecha y una línea del commit que las escribió, sacadas del `git blame`, sin modelo. Así puede reconsiderar la edición antes de seguir. Si el blame falla, lo dice; nunca lo da por limpio.
- **Antes de editar, si la edición toca una desviación conocida de la instancia, te pregunta.** En Codex, y en Pi sin pantalla, la frena.
- **Lo que un ticket quita vuelve como regla.** Al cerrar, si el ticket borró un archivo o sacó una dependencia de su manifiesto, `/odd-ws:cerrar` te pregunta si puede volver. Si no puede, te propone la regla que lo frena, con la línea que lo volvería a agregar como caso sembrado.
- **Lo ajustas con `"porque_al_editar"`** en `workspace.config.json`: `"todo"` (por defecto), `"indice"` (solo la pregunta de las desviaciones) o `"apagado"`.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md). Esta versión no cambia ninguna plantilla de la instancia.

### Detalle técnico

- **El porqué (I90):**
  - `odd_ws/porque.py` reúne el blame y la ubicación por contenido.
  - El evento `Herramienta` suma `reemplazos`, el texto que se reemplaza, que llenan los tres hosts.
  - En el `PreToolUse`, `verificar_capa` pregunta solo ante una desviación, y no corre git si el archivo no tiene ninguna.
  - En el `PostToolUse`, suma el contexto del blame en `HEAD`, con su propio plazo de 1,5 s y el entorno limpio.
  - El sub-chequeo va aislado, así que una falla suya nunca borra el bloqueo del primer toque.
- **Lo que se quita (I91):**
  - `quitado.py`, de solo lectura, lista los archivos borrados (con `--find-renames`) y las dependencias que salieron de `package.json`, `requirements*.txt`, `pyproject.toml`, `go.mod`, `*.csproj`, `build.gradle(.kts)` y `Cargo.toml`.
  - `cerrar` lo corre en su triaje.
  - La foto de la entrega pasó a `references/entrega.md`.

## 0.15.0

**Revisar gasta menos: lo determinista se encuentra antes de lanzar a los revisores, sus reportes ya no llenan tu contexto, lo que ya se aprobó como desviación no se vuelve a plantear y lo que se guarda sale con los secretos tapados.**

### Lo que cambia para ti

- **El triaje corre los chequeos de cada capa sobre el diff antes de lanzar a los revisores.** También busca marcadores de conflicto, incluso en lo que no trackeaste. Si algo falla, te propone corregirlo antes de gastar tokens, y lanzar igual pide un sí aparte. Lo que decidas no corregir entra al prompt de los revisores como «ya detectado», para que no lo repitan.
- **Los reportes de los revisores ya no entran enteros a tu contexto.** Cada revisor deja su reporte en su último bloque de texto y devuelve una sola línea, `VEREDICTO: <n> CRITICAL, <n> WARNING, <n> SUGGESTION`. `rescatar.py` guarda el reporte entero, y si un revisor devuelve solo el veredicto, el rescate falla en voz alta.
- **Las desviaciones conocidas de toda la instancia.** El código que parece un error y es a propósito se anota una vez en `.claude/reglas/desviaciones.csv`, con su porqué, y `revisar` no lo vuelve a plantear en ningún ticket. `/odd-ws:cerrar` te ofrece graduar ahí una desviación aprobada, y el doctor avisa si una fila está mal formada.
- **Los secretos se tapan antes de guardar.** Un token o una clave con formato conocido (AWS, GitHub, Slack, Google, OpenAI, Anthropic, Stripe o una clave privada) queda como un marcador como `<GITHUB_TOKEN>` en los reportes rescatados, en el recibo y en los diffs y la consolidación de cada ronda. Los revisores siguen viendo el código crudo.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md). Esta versión no cambia ninguna plantilla de la instancia.

### Detalle técnico

- **Los chequeos (I47):**
  - `triaje.py` corre `verificar_capa.verificar_archivo(..., contra=<base>)` en cada archivo activo con capa, y `marcadores.marcadores_contra` en el diff.
  - El resultado va a la clave `chequeos` de `triaje.json` y a la última línea del texto.
  - Un chequeo que falla por dentro sale como «no se pudo chequear», nunca como limpio.
  - El git de los marcadores corre con el entorno limpio, así que no depende del índice de un hook.
- **El veredicto (I35):** la regla va en `references/prompt.md`. `rescatar.extraer_corrida` toma el texto del mismo mensaje antes del `SubagentHandback`; en Pi, el texto del hilo después de la última herramienta. Una devolución sin `VEREDICTO:` sigue siendo el reporte, como antes.
- **Las desviaciones (I92):** `odd_ws/desviaciones.py` valida cada fila, y `ubicacion` reusa el formato `ruta@hash:ini-fin` de la matriz. `desviaciones.py` las imprime para el prompt, y el doctor suma el ítem `desviaciones`.
- **Los secretos (I86):** `odd_ws/secretos.py` usa solo patrones concretos, ninguno genérico de `etiqueta:valor`. Lo aplican `rescatar._guardar` y `recibo._guardar`, y `tapar.py` antes del `--check` de cada ronda. El recibo sigue valiendo, porque hashea el `git diff` vivo.

## 0.14.0

**Lo que pasaba en silencio ahora se ve: un hook que falló, los hooks de un repo que no corren desde la instancia y las plantillas que quedaron viejas después de actualizar.**

### Lo que cambia para ti

- **Cuando un hook falla por dentro, ya no pasa callado.** Sigue dejando pasar lo que le tocaba revisar, como antes, pero la falla queda anotada. La sesión siguiente te la muestra una vez, y `/odd-ws:doctor` la lista en el ítem `hooks-fallas` hasta que la vacíes con `--arreglar hooks-fallas`.
- **El doctor y `/odd-ws:abrir` avisan cuando un repo de tu config trae hooks propios** en su `.claude/settings.json` o `.claude/settings.local.json`. Esos hooks, como un guard o un formateador, corren solo si la sesión arranca en el repo, no desde la instancia. Es el ítem `hooks-de-repos`, y solo aparece si tu instancia usa Claude Code.
- **Las extensiones sin capa a propósito ya no avisan para siempre.** Imágenes, recursos o archivos de build se reconocen una vez en la clave `"sin_capa"` de `workspace.config.json`. El `cómo:` del aviso te da la línea exacta, para que saques las que sí son código.
- **El doctor te dice qué plantillas de tu instancia quedaron viejas.** El ítem `plantillas` compara tu `CLAUDE.md`, la plantilla de los tickets, el `pre-commit` y la prueba de tus reglas con las de cada versión publicada. El aviso te dice cuáles no tocaste y cuáles editaste. Fusiona a mano las editadas y después corre `--arreglar plantillas`: reemplaza las que no tocaste y anota la versión, y desde ahí el ítem sale OK, así que no lo corras antes de fusionar. La primera sesión después de actualizar ya te nombra las que cambiaron.
- **Dos arreglos en las plantillas.** El `CLAUDE.md` de la instancia ya no se contradice sobre lo que vuelve después de un `/compact`. Correr a mano la prueba de tus reglas ya no deja `__pycache__`.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md). Esta versión cambia dos plantillas, y el doctor te dice cuáles tienes que copiar.

### Detalle técnico

- **La falla de un hook (I2):**
  - `odd_ws/fallas.py` anota en `.claude/estado/fallas-de-hooks.jsonl` cada excepción que se tragaban `correr()` de los cinco hooks y `comun.correr_hook`. Guarda el hook, el evento, la fecha y el tipo y mensaje del error, este cortado a 200 caracteres, nunca el payload.
  - El registro tiene un tope de 20 entradas. Ningún guard cambia su veredicto.
  - `verificar_capa._session_start` muestra las nuevas una sola vez.
- **Los hooks de un repo (I36):** `config_loader.hooks_de_los_repos` lo usan el doctor y `ticket.py --cobertura`. Cuenta un objeto `hooks` no vacío.
- **`sin_capa` (I87):**
  - Es una clave opcional validada como las demás.
  - Las extensiones que lista pasan a las esperadas en el doctor, en `--cobertura` y en el triaje.
  - `Cobertura` suma su `ayuda`, para que el doctor y `ticket.py` digan lo mismo.
- **Las plantillas viejas (I85):**
  - La clave `"plantillas"` la escribe el bootstrap.
  - `plugin/plantillas/huellas.json` guarda la huella de cada plantilla copiada en cada versión publicada. La genera `tools/huellas.py` desde las etiquetas, y el pre-push de `tools/entrega.py` exige que esté al día en un push a `main` o a una etiqueta.
  - El `CLAUDE.md` raíz se compara con el nombre del proyecto devuelto a su marcador. Si eso no calza, la copia cuenta como editada y nunca se reemplaza.
- **Los defectos (I88, I89):** `verificar.tests.py` y `pre-commit.tests.py` ponen `sys.dont_write_bytecode`, y la línea 14 del `CLAUDE.md` de la instancia ya no contradice al párrafo del ticket activo.

## 0.13.3

**El agente ya no puede forzar un push de ninguna forma, y cada bloqueo muestra el comando que frenó. La instalación se ve de un vistazo, con la versión puesta.**

### Lo que cambia para ti

- **El agente ya no puede forzar un push de ninguna forma.** Hasta ahora `git push --force-with-lease` pasaba, y el guard hasta lo recomendaba, pero un lease sin `ref:sha` lo satisface cualquier `fetch`. Ahora bloquean siempre `--force`, `-f`, `--force-with-lease` en cualquier forma, `--force-if-includes`, `--mirror` y un refspec con `+`, también abreviados y también en un repo protegido. El mensaje te da la forma segura para correrlo tú: mira `git log <remoto>/<rama>` y corre `git push --force-with-lease=<rama>:<sha que esperas> <remoto> <rama>`.
- **Cada bloqueo y cada pregunta de un comando muestran el comando tal cual**, en la línea `Comando: «…»`. Uno de más de 300 caracteres se corta con «…».
- **Un hallazgo de la capa cita el fragmento que lo disparó** cuando la regla lo trae: `[T-02 CRITICAL] linea 4 en «MALO»: …`.
- **La instalación se ve sin abrir nada.** En el README, una línea «Instalar» lleva a cada CLI y al video, y la instalación de Claude Code, Codex y gentle-shell ya no está en desplegables. El comando de gentle-shell lleva el número de la versión, listo para copiar y pegar, también en la página y en `Doc/`.
- **La columna `tipo` de la matriz dice qué es cada código** (`CE`, `CC`, `PR`, `CR`, `MT` y `META`), en `/odd-ws:cerrar` y en `Doc/capas-y-reglas.md`.
- **`Doc/actualizar.md` lista por versión lo que se copia a mano de las plantillas.** Si tu instancia es de una versión vieja, ahí ves qué le falta a tu `CLAUDE.md`, a tu `pre-commit` o a la prueba de tus reglas. Esta versión no cambia ninguna plantilla.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **El push forzado (I49):** el predicado `_opcion_forzada` reconoce toda opción forzada y sus prefijos. Lo usan las dos pasadas de `guard_comandos`, que ahora dan el mismo motivo. Sale el código del lease que cubría una ref.
- **El comando literal y el fragmento (el M3 de Maik):**
  - En `guard_comandos`, citan el comando `_mensaje`, `_preguntar` y `_mensaje_de_capa`, también en las preguntas por plazo vencido o por error interno.
  - En `writer_guard`, lo cita su `_mensaje`. En Codex y Pi, la nota del host va después de la cita.
  - El fragmento lo citan `verificar_capa._formatear` y `writer_stop._describir`, que también usa `revisar_turno`.
- **El chequeo de la entrega (I70):** en un push a `main` o a una etiqueta, `tools/entrega.py` compara con el `plugin.json` del commit:
  - la «Versión actual» del README;
  - la versión de la página;
  - cada `odd-ws--v…` del README, de `Doc/uso.md`, de `Doc/actualizar.md` y de la página;
  - la tabla de requisitos del README con la de la página.

  La página se lee de la rama local `gh-pages`, así que se commitea antes de empujar `main`; `CONTRIBUTING.md` suma esos pasos. Es una herramienta del repo: no cambia el plugin.
- **Cómo se validó:**
  - Un verificador independiente corrió 67 comandos de push en los tres CLI, con y sin repo protegido, contra la `0.13.2`. Las únicas diferencias son los push forzados que ahora bloquean y la cita del comando.
  - Probó el chequeo de la entrega en un repo de prueba con todos sus casos, y los chequeos de antes dieron la misma salida, byte a byte.
  - Las 52 suites de Python y las de node pasaron sobre el árbol integrado, y sus sondas quedaron como tests.
- Las decisiones están en `odd/tasks/huecos-chicos.md`.

## 0.13.2

**Actualizar el plugin ya no deja el doctor en FALTA, y la primera corrida del bootstrap y del doctor sale completa, en español y sin palabras internas.**

### Lo que cambia para ti

- **Después de actualizar, `plugin-root` se pone al día solo.** La ruta del plugin lleva la versión, así que hasta ahora cada actualización dejaba `plugin-root` en FALTA en cada instancia, y había que correr `--arreglar plugin-root` en todas; mientras tanto, el pre-commit corría las reglas de la versión vieja. Ahora la primera sesión que abres en la instancia anota en `workspace.local.json` la versión de esa sesión, y se lo dice al agente al arrancar. Vale desde esta misma actualización: la primera sesión con la `0.13.2` ya lo hace. Solo cambia una ruta que apunta a otra versión del mismo plugin: una carpeta con nombre de versión junto a la de la sesión, como las del caché. Una que anotaste a mano en otro lado, por ejemplo en un clon, queda como está. Con el hook `verificar_capa` apagado, el arreglo del doctor sigue ahí.
- **En «Lo detectado», la fila del repo sale completa siempre:** su «Qué significa» lleva el nombre del repo (`local.repos.mi-proyecto.path`). En la `0.13.1`, a veces quedaba `<repo>` sin llenar.
- **El título de cada comando que corren el bootstrap y el doctor va en español.** En la `0.13.1`, a veces salía en inglés.
- **La descripción del doctor en el autocompletado dice qué hace:** «Revisa tu máquina y esta instancia, dice qué falta y cómo arreglarlo», sin «(Capa 0)».
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **`plugin-root` (I75):** el `SessionStart` de `verificar_capa` llama a `odd_ws/raiz_del_plugin.seguir_al_vigente`, en Claude Code, Codex y Pi. Anota la carpeta del plugin de la sesión solo si no hay copia de emergencia, la anotada y la vigente tienen nombre de versión y la misma carpeta madre, son distintas y la vigente tiene `scripts/reglas.py`. Usa la misma escritura que `--arreglar plugin-root`, que pasó a ese módulo junto con `misma_carpeta` y `COPIA_DE_EMERGENCIA`. El pre-commit de la instancia y el ítem `plugin-root` del doctor no cambian.
- **Los skills:** la regla de la tabla del paso 3 del bootstrap dice que el `<repo>` de «Qué significa» se llena; el bootstrap y el doctor piden en español la descripción de cada comando; la descripción del doctor cambió; y el bootstrap escribe la spec con la herramienta de archivos, nunca con un heredoc ni con `echo`, porque en una corrida de prueba las barras invertidas de una ruta de Windows rompieron el JSON. Los tests de `bootstrap.tests.py` fijan las cuatro cosas.
- **Cómo se validó:** un verificador independiente simuló una actualización con dos versiones del plugin en un caché de prueba, con la versión vieja en disco y borrada: el hook anotó la nueva, el doctor dio `plugin-root` OK y el commit corrió las reglas de la versión nueva. Los casos fuera de la regla dejaron el archivo idéntico, y con la versión ya al día la salida del hook es la misma que en la `0.13.1`. Cuatro corridas reales del bootstrap con el plugin de la rama salieron con la fila del repo llena, todos los títulos de los comandos en español y el doctor en `0 FALTA, 0 AVISO`.
- Las decisiones están en `odd/tasks/pulido-instalacion.md`.

## 0.13.1

**El bootstrap muestra lo mismo en cada corrida y vuelve a proponer tus repos como del equipo.**

### Lo que cambia para ti

- **La pregunta en la raíz de un repo de código sale siempre igual, y en español.** El encabezado es «Ubicación», la pregunta termina en «¿Dónde la creo?» y las opciones son «Carpeta aparte (recomendado)» y «Dentro del repo». La carpeta aparte que propone es `<raíz>-ws`, al lado del repo.
- **La parte de arriba de la propuesta también es fija:** la misma línea de apertura, la tabla «Lo detectado» con sus filas en el mismo orden, el ensayo y, si hay, «Lo que pide atención» justo antes de «Lo que decides». Después del sí, la respuesta empieza directo con «La aplicación». En la `0.13.0` esa parte la redactaba el modelo y cambiaba de una corrida a otra.
- **Corrige una regresión de la `0.13.0`: el bootstrap proponía tu repo como propio (`own`).** Ahora, como antes, cada repo se propone del equipo, y la fila «Repos tuyos» lo dice: si uno es tuyo, lo dices en tu respuesta. Si creaste una instancia con la `0.13.0`, mira `workspace.config.json`: si un repo tiene `"own": true` y no es tuyo, quítalo y commitea el cambio.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **El skill del bootstrap** escribe literales, en bloques `text` que el modelo pega como texto normal, la pregunta de la raíz (paso 2), la apertura, «Lo detectado», el ensayo y «Lo que pide atención» (paso 3), con `<…>` solo donde va lo variable. La fila de `own` dice «ninguno, todos del equipo» y la regla prohíbe inferirlo de que el repo sea local, no tenga remoto o lo haya creado el usuario. Los tests de `bootstrap.tests.py` fijan las tres cosas.
- **Por qué pasó:** en la `0.13.0` la fila decía `<ninguno, o cuáles>`, un hueco con el beneficio a la vista, lejos de la regla; el modelo lo llenó con el único repo en tres corridas de tres. Un `<…>` con una alternativa invita a llenarlo: un valor por defecto va literal.
- **Cómo se validó:** antes de publicar, tres corridas reales del bootstrap con el plugin de la rama salieron con la misma estructura y `"mi-proyecto": {}` en el commit, y la pregunta de la raíz salió literal.
- Las decisiones están en `odd/tasks/primera-impresion.md`.

## 0.13.0

**La propuesta del bootstrap deja a la vista lo que decides, el doctor se lee de un vistazo y una instancia nueva sale sin avisos por sus archivos de datos y configuración, el aviso de calibrar trae un comando que se corre tal cual, y todo el texto de odd-ws pasa a tuteo neutro.**

### Lo que cambia para ti

- **En el bootstrap, lo que decides queda a la vista.** La propuesta sigue siendo una sola parada, en este orden: lo detectado, el ensayo y, al final, el bloque «Lo que decides», con el perfil primero, después los tickets (un prefijo o el id de tu tracker) y tus repos (`own`), y la única pregunta justo debajo. En una terminal de unas 24 filas lo ves sin subir. El perfil se explica en una línea: si ya usas tu propia orquestación o revisión (por ejemplo, gentle-ai), `controles`; si no, `completo`.
- **Una instancia nueva no avisa por sus archivos de datos y configuración.** En el ítem `capas-cobertura` del doctor, los `.json`, `.jsonc`, `.yml`, `.yaml`, `.toml`, `.lock`, `.ini` y los archivos sin extensión (`.gitignore`, `Dockerfile`…) son esperados: la fila sale OK y los nombra con su conteo, con la nota de que un cambio en ellos lleva `/odd-ws:revisar` a modo `completo`. Una extensión de otro tipo, como un `.mjs` en un repo sin capa `js`, sigue dando AVISO, que ahora lista solo esas. `/odd-ws:abrir` hace la misma separación. El triaje de `/odd-ws:revisar` sigue contando igual: un cambio en un `.json` lo sigue llevando a `completo`. La ayuda de `capas-cobertura` (su línea `cómo:`) cambió solo su redacción.
- **El aviso de calibrar trae un comando que se corre tal cual.** Una regla sin calibrar avisa con el Python de tu máquina (`python` o `python3`, el que esté en el PATH), la ruta absoluta del `reglas.py` del plugin entre comillas, la capa y la carpeta real: la de una regla de la capa ya calibrada o, si no hay ninguna, la del primer repo de la capa. Primero corrige lo que la regla marcó, como dice el aviso: calibrar con el defecto todavía en el archivo lo cuenta como un acierto, y la regla sigue sin bloquear. Después, copia el comando y córrelo desde la raíz de la instancia, en Windows (cmd o PowerShell), Linux o macOS, aunque las rutas tengan espacios. Solo si no hay ninguna de las dos carpetas queda `<carpeta>`, para que pongas una.
- **El doctor se lee de un vistazo.** Su salida va en tres grupos, cada uno con su encabezado: «La plantilla (solo en un clon de odd-workspace-template):», «Tu máquina:» y «Esta instancia:». La línea de resumen (`0 FALTA, 1 AVISO`) sigue al final, que es lo que se ve sin subir. Los ítems y `--arreglar` no cambian.
- **`plugin-root` ya no muestra tu usuario.** En OK, la ruta del plugin sale desde tu home (`~` y el resto). Una FALTA y su arreglo la siguen mostrando entera, porque se copian, y `workspace.local.json` sigue guardando la ruta absoluta.
- **El doctor y el bootstrap responden siempre con la misma forma.** `/odd-ws:doctor` muestra su salida entera y tal cual en un bloque de código, con un comentario de una línea por cada FALTA y cada AVISO, o `Todo en orden: nada falta y no hay avisos.` si no hay ninguno. El bootstrap muestra igual la aplicación y el doctor, y cierra con «Lo que sigue», un texto fijo para cada perfil.
- **Todo el texto de odd-ws pasa a tuteo neutro:** las skills, los mensajes de los scripts y de los hooks, y la documentación. Las plantillas ya lo estaban.
- **En tu instancia no editas nada a mano.** La config y lo que generó el bootstrap no cambian. Después de actualizar, corre `/odd-ws:doctor` (en Codex, `$doctor`): la ruta del plugin lleva la versión, así que `plugin-root` puede salir en FALTA con la de la versión anterior, y su arreglo, `--arreglar plugin-root`, anota la nueva en `workspace.local.json`.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **La propuesta.** El paso 3 de `skills/bootstrap` abre con el orden de la respuesta y trae el bloque «Lo que decides» literal, en un bloque `text` que leen los tests de `bootstrap.tests.py`. El perfil, los tickets y `own` salieron de la tabla de lo detectado. Al completar una instancia, el bloque no va.
- **El comando de calibrar.** `calibracion.REGLAS_PY` sale de `__file__`. `calibracion.aplicar` y `modo_efectivo` suman un parámetro opcional `capas`, que `verificar_capa` llena con `config["layers"]`, para tomar el `path` del primer repo de la capa cuando ninguna regla está calibrada. Toda ruta va entre comillas dobles, y una barra invertida final se dobla, porque sin doblar `"C:\"` rompe cmd y Git Bash. El Python lo elige `calibracion.interprete()`: por su nombre, el primero que esté en el PATH (`python` y `python3` en Windows, `python3` en Linux y macOS), porque una ruta entre comillas al principio de la línea no la corre PowerShell; sin ninguno, `sys.executable` entre comillas, y sin él, `python3`. Así el comando no pide un `python3` que no existe en un Windows con solo `python.exe`, donde los hooks de Codex y Pi corren `python`. El aviso pide corregir los hallazgos antes de calibrar, porque el corpus de `--calibrar` incluye los archivos sin commitear; con aciertos en bloqueo, pide corregirlos o, si son falsos positivos, arreglar la regla. Un test de punta a punta copia el plugin a una ruta con espacios, corre el comando del aviso tal cual por el shell y comprueba que calibra y que después el hook bloquea. Quedan dos límites: el nombre de la capa va sin comillas, y una ruta UNC con espacios sigue fallando en Git Bash.
- **La cobertura.** `config_loader.cobertura_de_los_repos(config, versionados, controles=False)` devuelve `None` o `Cobertura(aviso, detalle)`, en lugar del texto del aviso, y los esperados están en `config_loader.ESPERADOS_SIN_CAPA`. La usan el doctor y `ticket.py --cobertura`, con el mismo detalle y la misma ayuda, también en `controles`. El triaje sigue contando por su cuenta, igual que antes; de `AYUDA_COBERTURA`, que comparte, cambió solo la redacción («si no, el aviso queda», porque «es esperado» chocaba con el sentido nuevo de los esperados).
- **El doctor.** `doctor.agrupar` arma los grupos al imprimir, con `DE_LA_PLANTILLA` y `DE_LA_MAQUINA`, y lo que no está en ninguno va a la instancia. `diagnosticar`, el orden de sus ids y las firmas de `chequear_*` no cambian. Un test descubre las filas de máquina de cada host por su interfaz pública (`chequeos` con el CLI de otro host) y falla si alguna no está en `DE_LA_MAQUINA`. La ruta de `plugin-root` la arma `doctor.desde_el_home`.
- **Las respuestas fijas.** `skills/doctor` trae la forma de su respuesta («Cómo presentarlo»), y `skills/bootstrap` muestra la aplicación tal cual en el paso 4, el doctor como su skill en el paso 5 y un cierre fijo por perfil en el paso 6. Los tests de `bootstrap.tests.py` fijan las tres cosas.
- **El tuteo.** `plugin/scripts/registro.tests.py` busca formas de voseo en las skills, los scripts, el shim, las plantillas, `Doc/*.md` y el `README.md`, con una lista de formas, una regla por terminación (las palabras agudas con tilde en `-á`, `-é` o `-í`, con o sin `s`, y los imperativos de la lista con un clítico sin tilde, como `tomalo`) y una lista de excepciones (`está`, `después`, `así`…), y falla si aparece alguna: un cambio futuro escrito en voseo se detecta solo. Los tests que leen frases de las skills pasaron al texto nuevo. Quedan fuera `odd/` y las secciones viejas del `CHANGELOG`.
- Las decisiones están en `odd/tasks/primera-impresion.md`.

## 0.12.1

**odd-ws le suma menos al prompt: nada en los subagentes de gentle-shell ni fuera de una instancia, y `revisar` y `cerrar` con un núcleo corto que sobrevive a la compactación.**

### Lo que cambia para ti

- **En gentle-shell, los subagentes no reciben nada de odd-ws:** ni el resumen del ticket activo, ni el aviso de config rota, ni las skills de odd-ws en su catálogo. Los guards siguen funcionando igual en ellos. Es lo mismo que ya pasaba en Claude Code, donde el inicio de la sesión no llega a los subagentes.
- **Fuera de una instancia, en Pi, las skills de odd-ws no se listan.** Igual las puedes correr con `/skill:<nombre>`, por ejemplo `/skill:bootstrap` para crear una instancia.
- **`revisar` y `cerrar` tienen un núcleo corto,** de unos 4.700 y 3.500 tokens, y el detalle en archivos que se leen solo en el paso que los necesita. En Claude Code, después de una compactación solo vuelven los primeros 5.000 tokens de cada skill: con la skill entera, `revisar` perdía el recibo y el rechequeo. Ninguna regla cambió; solo dónde está.
- **Las descripciones de las skills tienen la mitad de largo,** con el caso de uso primero. Ninguna cambia quién la puede invocar.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **El shim de Pi** filtra `event.systemPromptOptions.skills` en `before_agent_start`: en un hijo (`GENTLE_PI_AGENTS_CHILD=1`) saca las skills del plugin y las de la instancia, y en el agente principal fuera de una instancia saca las del plugin. Compara la ruta escrita y la real, así que sobrevive a junctions, mayúsculas y barras. `pi.skills` se queda en el `package.json`, así que `/skill:<nombre>` sigue resolviendo. En el hijo, `session_start` y `session_compact` no lanzan Python, y `resources_discover` no publica nada.
- **Las references** viven en `skills/revisar/references/` y `skills/cerrar/references/`, se abren con compuertas explícitas en el núcleo y usan el marcador `<S>`, porque `${CLAUDE_PLUGIN_ROOT}` solo se reemplaza dentro del `SKILL.md`. Un chequeo mecánico comparó cada oración del archivo viejo con el núcleo y sus references. Los tests leen las dos partes y fijan el tamaño de cada núcleo.
- Las decisiones están en `odd/tasks/carga-en-el-prompt.md`.

## 0.12.0

**Puedes instalar solo los controles de odd-ws junto a otra orquestación, apagar un hook puntual, y las reglas por capa bloquean solo después de calibrarse.**

### Lo que cambia para ti

- **Corte duro: las reglas por capa no bloquean hasta calibrarlas.** Al actualizar, todo bloqueo de una capa o de un paquete pasa a aviso, con el motivo y el comando a correr. Para que una regla vuelva a bloquear, declara su `sembrado` en `REGLAS`, corre `reglas.py --calibrar <capa> <carpeta> --guardar` y commitea `.claude/registro/`. El paso a paso está en [Doc/actualizar.md](Doc/actualizar.md).
- **Una regla bloquea solo si** su módulo lo pide, atrapa su defecto sembrado, da 0 aciertos en el código existente y no cambió desde la calibración. Cualquier cambio en el módulo pide calibrar de nuevo, y un fin de línea distinto no.
- **El sembrado puede llevar ruta.** Además de un texto, puede ser `{"ruta": "Migrations/0001_alta.sql", "texto": "..."}`, así una regla que solo mira una carpeta, una extensión que no es la primera de la capa o el nombre del archivo también se calibra.
- **Las disputas.** Si un bloqueo está mal, crea `.claude/registro/disputas/<ID>.md` con quién la abre, qué bloqueo y por qué. La regla vuelve a avisar hasta que se arregle su chequeo y se borre el archivo. Ningún script abre una disputa solo.
- **Los paquetes de reglas** se calibran igual, contra la huella de su lock, y `--guardar` los calibra junto con la capa.
- **Instalar solo los controles.** Con `"profile": "controles"` en la config (el bootstrap te lo pregunta), la instancia trae los guards, las reglas por capa y el doctor, sin tickets, revisiones ni writers. El `CLAUDE.md` sale corto, para no chocar con la orquestación de gentle-ai, y el doctor no te propone apagar el RDD, porque ahí la revisión es la tuya. Para pasar a completo, quita la clave y corre `/odd-ws:bootstrap`.
- **Apagar un hook.** `"disabled_hooks"` en la config apaga los hooks que nombres: `verificar_capa`, `guard_comandos`, `revisar_turno`, `writer_guard` o `writer_stop`. El doctor te avisa cuáles están apagados, y el riesgo si uno es `guard_comandos`. Un valor inválido no apaga nada.
- Actualiza con los comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **El modo efectivo** se calcula en un solo punto, `odd_ws/calibracion.py`, al final de `verificar_capa._verificar_archivo`; `writer_stop` y `revisar_turno` leen el resultado. El motivo de un aviso viaja en `aviso_por`, que el módulo no puede falsear. Un hallazgo sin `modo`, con un `id` que no es texto o sin fuente avisa con su motivo en vez de bloquear o de callar el hook.
- **La calibración** vive en `.claude/registro/calibracion.json`, versionado: por regla, la huella del módulo (sha256 con CRLF pasado a LF), si atrapó su sembrado, los aciertos, los que piden bloqueo, el corpus (repo, commit y ruta relativa) y la fecha. Los paquetes van en `paquetes`, aparte de las capas. Sin `--guardar`, la salida de `--calibrar` no cambia.
- **El perfil** se lee con un solo helper de `config_loader`, y cada generador filtra adentro de su `generar`. La plantilla reducida es `plugin/plantillas/CLAUDE.controles.md`, con una marca que el doctor usa en el ítem `perfil`.
- **`disabled_hooks`** se chequea en la decisión de cada hook, con `config_loader.hook_apagado`, en Claude Code, Codex y Pi. Un hook apagado deja pasar todo sin tocar el disco. El doctor suma el ítem `hooks-apagados`.
- **Los helpers de las pruebas que corren git** limpian el entorno, porque las suites corren dentro del pre-commit, que exporta `GIT_DIR`.
- Las decisiones de cada parte están en `odd/tasks/solo-controles.md` y `odd/tasks/reglas-observan.md`.

## 0.11.0

**El recibo registra solo lo que de verdad se revisó, con el modo que respalda el triaje de tu diff actual (issue #1), y el doctor apaga el RDD de gentle-ai solo en el clon de la instancia.**

### Lo que cambia para ti

- **Una bajada ya no vale con un triaje viejo.** Si editas algo después del triaje, el recibo te pide correrlo de nuevo antes de bajar a `rapido`, porque la edición pudo traer un riesgo real. Es el caso del issue #1.
- **El modo no baja sin `--bajada`.** Con un triaje guardado, el recibo no acepta un `--modo` más bajo que el que propuso, y en un rechequeo tampoco uno más bajo que el de la ronda anterior. Salvo en `completo`, ese triaje también tiene que ser el de tu diff actual.
- **Los archivos del ambiente local ya no impiden bajar.** El triaje ve todo el diff y el recibo cubre solo lo que revisaste: lo que el triaje vio y el recibo no cubre sale en un aviso, por si alguno era del ticket.
- **Reescribir un recibo con otro diff ya no pasa en silencio:** sale con 1 y te manda al rechequeo con `--previo`. Con el mismo diff conserva el sello y la bajada.
- **`--check` mira lo que entraría al commit,** el índice, y te dice el estado, el modo y la bajada del recibo. **`--sellar` no sella un recibo `pendiente`.**
- **`recibo.py --write --ticket` parte de la misma base que el triaje:** la del último sello del ticket.
- **El doctor apaga el RDD nativo solo en el clon de la instancia** (`--scope clone`), no en toda la máquina. Fuera de una instancia el ítem no aplica, porque ahí el RDD de gentle-ai es tu revisión.
- **El bootstrap da ejemplos de tracker** (Jira, Azure Boards, GitHub Issues, Linear) cuando te pregunta si usas uno.
- **Si tienes una revisión a medias** con un `triaje.json` de antes de esta versión, vuelve a correr el triaje: sin la huella del diff, la bajada y el piso del modo lo rechazan.
- Actualiza con los dos comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **La huella del triaje.** `triaje.py --json` suma a cada repo `sha256` y `sha256_por_archivo`, calculados con `recibo.calcular`. El recibo exige que cada archivo que cubre esté en el triaje con la misma base y la misma huella; los archivos o repos que el triaje vio de más solo salen en el aviso. Las carpetas (submódulos, repos anidados) quedan fuera de la huella, y un submódulo borrado entra como ausente.
- **El triaje se valida entero:** las seis señales, un modo que sea el que dan sus señales y sus archivos, y `sin_capa.unico_motivo_de_capas` recalculado desde los archivos. Las funciones compartidas viven en `recibo.py`.
- **Un archivo del taller triado por el `--repo` de la instancia** conserva su contraparte de la línea base, como con `--taller`.
- **Las rutas van a git como literales** (`--literal-pathspecs`, sin las variables `GIT_*_PATHSPECS`), y en Windows una ruta con otras mayúsculas se canoniza a la del repo antes de hashearla.
- **El rechazo de un triaje de otro diff** nombra cada repo del recibo con su base (`--repo <ruta>#<base>`), también los que un rechequeo hereda enteros.
- **El doctor:** `--arreglar rdd` corre `gentle-ai review mode disable --scope clone --cwd <repo>`. En una instancia fuera de git no hay arreglo automático, porque gentle-ai lo apaga por clon.
- La auditoría y sus decisiones están en `odd/tasks/integridad-del-recibo.md`.

## 0.10.1

**Un parche de pruebas: los tests de los enlaces pasan también en macOS. No cambia nada para ti.**

### Lo que cambia para ti

- **Nada.** El plugin hace lo mismo que en la `0.10.0`. Si ya la tienes, no hace falta actualizar; si actualizas, usa los dos comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **`ticket.tests.py`** resuelve con `realpath` la carpeta temporal de sus pruebas, como ya hacía `abridor.tests.py`. En macOS, el temporal `/var/folders/...` es un enlace a `/private/var/...`. Las rutas que calcula `ticket.py` desde la carpeta actual, o con `realpath` al abrir, salen como `/private/var`, y siete pruebas de los enlaces las esperaban como `/var`. Fallaban solo en el CI de macOS, después de publicar la `0.10.0`.

## 0.10.0

**La instalación sale limpia, `revisar` mide y explica lo que cuesta, Pi y Codex funcionan completos con Gentle 4.8, y los enlaces de un ticket se depuran y se abren desde cualquier cliente.**

### Lo que cambia para ti

- **El primer commit trae lo que es de la instancia.** Si `claude plugin install --scope project` ya escribió `.claude/settings.json` con lo mismo que escribiría el bootstrap, entra al primer commit. Antes quedaba afuera, y un clon del equipo no habilitaba el plugin. El `.code-workspace` de la raíz también entra si sus carpetas usan rutas relativas. Lo que no entra, el bootstrap te lo dice con su motivo.
- **`workspace.local.json` nunca entra a un commit,** aunque tu `.gitignore` no lo excluya, porque tiene las rutas de tu máquina.
- **En la raíz de un repo de código, el bootstrap pregunta antes.** Ahí la instancia quedaría en el git de ese repo, con el hook y el primer commit en su rama. Por eso te recomienda una carpeta aparte, y solo sigue ahí con tu sí. Esto corrige lo que decía la `0.9.1`: la instancia pierde su git solo en una subcarpeta de un repo, no en su raíz.
- **La propuesta de capas solo te ofrece sumar extensiones del mismo lenguaje**, como un `.js` a una capa `ts`, y no un `.json`.
- **Si `claude plugin marketplace add` falla** con «its source doesn't match its extraKnownMarketplaces entry», el marketplace ya está registrado: sigue con `plugin install`.
- **Cada revisión mide lo que cuesta.** Registra los turnos, el contexto, la salida y la caché de cada corrida, y en Claude Code también lo que le costó a la sesión principal. El anuncio de la siguiente revisión cita el último costo medido, y avisa si las corridas corrieron en serie. El consolidado cuenta los hallazgos por acuerdo y por severidad, y cada hallazgo cita el ID de la regla que rompe.
- **Puedes bajar un escalón, de `completo` a `rapido`,** cuando el triaje lo propuso solo por límites del instrumento (una señal inválida o un archivo sin capa) y el cambio no va a un líder. Lo decides tú, con un motivo que queda en el recibo. Nunca se baja si el triaje vio un riesgo real, y el recibo comprueba que el triaje sea del mismo diff.
- **«Sin capa» se explica.** El triaje y `/odd-ws:abrir` te dicen qué extensiones versionadas no tienen capa y que se arregla declarándola.
- **En Pi, `revisar` rescata los reportes enteros.** gentle-shell 4.8 corta a 16 KB la copia que le entrega al agente, y la mayoría de los reportes de diseño pasan ese tope. Ahora se leen de la tarea que guarda gentle-shell, con sus lecturas auditadas y su costo. Fuera de una sesión de gentle-shell, el rescate se corre con `--sesion ~/.gentle-shell/agent`.
- **En Codex, una revisión grande ya no se corta por el límite de hilos.** Una corrida que Codex rechaza por su límite de concurrencia se relanza cuando termina otra, y te avisa que la revisión va por tandas.
- **Los enlaces de un ticket se revisan y se abren desde cualquier cliente.**
  - `ticket.py --enlaces <id>` lista los enlaces del ticket, o de cualquier `.md`, numerados, con su ruta absoluta y los rotos aparte.
  - Pídele al agente que abra uno, o usa `/odd-ws:enlaces`, una skill nueva que el agente también puede usar por su cuenta. Te pregunta cuál y lo abre en tu escritorio, en Windows, macOS, Linux con escritorio o WSL. En una sesión remota no abre, y te dice por qué.
  - Un script o un ejecutable nunca se lanza: se muestra en su carpeta.
  - Con `--copiar`, las rutas van al portapapeles.
- **Los enlaces rotos aparecen solos.** Si el ticket activo tiene enlaces rotos, o con una ruta de tu máquina que se rompe en el clon de otra persona, el resumen del ticket te los muestra al arrancar la sesión. `/odd-ws:cerrar` los revisa antes de cerrar.
- **No tienes que regenerar nada.** Actualiza el plugin con los dos comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **El bootstrap (R7).**
  - **`--commitear`.** Suma lo que ya existía sin trackear ni ignorar:
    - `.claude/settings.json`, comparado como JSON canónico;
    - cada `*.code-workspace` de la raíz sin carpetas de la máquina: letra de unidad, `/`, `\`, UNC o `uri`.

    `workspace.local.json` nunca entra. Lo que queda afuera sale en una línea `no entró al commit <ruta>: <motivo>`.
  - **Los ignorados.** Se leen con `git check-ignore -z --stdin`: sin `-z`, git cita los nombres no ASCII, y un `.code-workspace` ignorado con un nombre como `facturación` hacía fallar el primer commit.
  - **`es_repo_de_codigo`.** Es una raíz que es el toplevel de su repo, con archivos en `HEAD` y sin `workspace.config.json`. Ahí el script sale con 2 sin escribir nada, también en el ensayo, salvo con `--confirmar-repo`. `--proponer` suma `repo_de_codigo` y `mismo_lenguaje`, con una sola familia: TypeScript con JavaScript.
- **El costo de revisar (R5).**
  - **`rescatar.py`.** Mide cada corrida desde su transcript (`odd_ws/transcripcion.py`), contando cada mensaje una vez por id. `--costo` escribe `corridas/costo.json`, con el modo, los motivos del triaje, las corridas, las líneas del diff, el `orquestador` y `en_serie`. `--ultimo-costo <ticket>` da la línea del anuncio.
  - **`recibo.py --bajada "<motivo>" --va-a-lider no`.** Baja solo de `completo` a `rapido`, contra el `entrada/triaje.json` de la revisión. Ese triaje tiene que ser del mismo diff: los mismos repos, con la misma base. El rechequeo hereda la bajada mientras siga en ese modo.
  - **El triaje.** Suma la clave `sin_capa` (`archivos`, `unico_motivo_de_capas` y `aviso`). El aviso de `capas-cobertura` vive en `config_loader`, y lo repiten el triaje y `abrir`.
- **Gentle 4.8 (R6).**
  - **`rescatar.py --host pi`.** Lee `<agentHome>/gentle-agents/tasks/<task_id>.json`, y `agentHome` es `GENTLE_PI_AGENT_HOME`, si no `PI_CODING_AGENT_DIR`, si no `~/.pi/agent`. Devuelve lo mismo que en Claude Code, más `tokens_total` y `costo_usd`, porque la tarea real no trae `usage`. Si una tarea falta, la skill recurre a `subagent_result`. La prueba en vivo en gentle-shell coincidió con el formato.
  - **`auditar_lecturas.py`.** Clasifica las lecturas de Pi (`read`, `grep` y `find`) como las de Claude Code.
  - **La línea `pi-agentes` del doctor.** Dice que no ve los overlays de herramientas de gentle-shell (#3223).
  - **El pre-commit del repo.** Frena un commit que agrega `<<<<<<<` y `>>>>>>>` en un mismo archivo (`odd_ws/marcadores.py`), y respeta `conflict-marker-size`. `git rebase --continue` no corre el pre-commit: `CONTRIBUTING.md` pide `git commit` en la parada.
- **Los enlaces (I61).**
  - **La regla.** La de enlace válido pasa a `odd_ws/enlaces.py` y la comparten `conocimiento.py`, `ticket.py` y el resumen del ticket activo.
  - **`--abrir <n>`** usa `odd_ws/abridor.py`, que decide con el entorno:
    - con `SSH_CONNECTION` o sin pantalla no abre, y sale con 1;
    - el abridor y la herramienta del portapapeles se buscan solo en las entradas absolutas del `PATH`, porque en Windows `shutil.which` mira primero la carpeta actual.
  - **La decisión de abrir.**
    - Usa la ruta real, y solo una lista de documentos, datos e imágenes se abre con su programa.
    - En Windows y WSL, una ruta con coma no se abre ni se muestra, porque `explorer` separa los argumentos por comas.
    - El código de salida de `explorer` no cuenta, porque suele ser 1 aunque haya abierto.
  - **La skill `enlaces`.** El procedimiento vive en `/odd-ws:enlaces`, sin `disable-model-invocation`, para que el agente lo encuentre cuando el usuario pide abrir o revisar enlaces. `abrir` crea tickets y sigue siendo solo del usuario.
  - **El resumen del ticket activo.** Marca las rutas de la máquina sin tocar el disco, porque una ruta UNC puede bloquear el hook.
- **Seguimientos de versiones anteriores.**
  - En Pi, una sesión bifurcada (`fork`) avisa de una config rota, como `resume`.
  - El ítem `codex-proyecto` del doctor acepta la clave del repo escrita con un alias.
  - El shim cuenta un `commondir` solo si su carpeta tiene `objects` y `refs`, como git.
  - En el modo memorias de `cerrar`, la corrección que pide `matriz.py` se muestra antes del sí, y el id se calcula igual que el script que lo asigna.
- **Las verificaciones.**
  - Cada cambio de riesgo tuvo un verificador independiente sobre copias aisladas: el bootstrap, la bajada y su cruce con el triaje, el rescate de Pi, el pre-commit y la apertura de enlaces.
  - Dos bloqueantes se corrigieron con su rechequeo: el `.code-workspace` no ASCII, y el `commondir` del shim.

## 0.9.1

**Un parche: el doctor de Pi deja de dar OK falsos, un writer de gentle-shell ya no corre sin guards en el repo de arriba, y la documentación dice dónde va la instancia.**

### Lo que cambia para ti

- **La instancia va en una carpeta aparte.** El README y la guía de uso ahora lo dicen claro: la instancia es una carpeta propia, con su propio git, al lado de tus repos de código. Apunta a tus repos por su ruta, sin tocarlos. Si la creas dentro de un repo de código, pierde su git: el bootstrap no le hace `git init`, ni configura el hook, ni hace el primer commit.
- **En gentle-shell (Pi), un writer ya no corre sin guards en el repo de arriba.** Si la instancia estaba dentro de otro repo y tenía una carpeta `.git` vacía o rota, el shim la tomaba como raíz git, mientras gentle-shell corría al writer en el repo de arriba. Ahora el shim mira el `.git` como lo hace git, y lo frena.
- **El doctor de Pi dice la verdad.** Antes daba OK en cinco casos en que Pi no cargaba el shim: tres enlaces o junctions que duplican el plugin, un `NaN` en el `settings.json` y un filtro escrito como `file://`. Ahora da el veredicto real. Además te avisa si la instancia está en una subcarpeta de su repo, donde gentle-shell no tiene writers.
- **No tienes que regenerar nada.** Actualiza el plugin con los dos comandos de [Doc/actualizar.md](Doc/actualizar.md).

### Detalle técnico

- **`hosts/pi.py`:**
  - La deduplicación de paquetes y la clave `extensions` de nivel superior usan la ruta real, como `getResourcePathKey` en Pi. En `toResolvedPaths`, Pi ordena por precedencia y descarta los duplicados, así que la primera copia gana aunque esté deshabilitada.
  - El `settings.json` se lee con `parse_constant`, que rechaza `NaN`, `Infinity` y `-Infinity` como `JSON.parse`.
  - Un patrón `file://` se normaliza a su ruta.
  - Con `git rev-parse --show-toplevel`, el ítem de gentle-shell da AVISO cuando la instancia está en una subcarpeta de su repo.
  - Los helpers que `pi.py` importaba de `codex.py` pasan a `hosts/base.py`, sin cambio de comportamiento.
- **`shim/pi.ts`:** `esCarpetaDeGit` cuenta una carpeta `.git` cuando se cumplen dos cosas:
  - `HEAD` es un archivo o un enlace, visto con `lstat`;
  - y hay un `commondir`, o bien `objects` y `refs`: carpetas en POSIX y de cualquier tipo en Windows, como acepta git for Windows.
  - Un `.git` que es archivo sigue igual.
  - **Quedan dos límites:** un `HEAD` cuyo contenido git rechaza, y un `commondir` que apunta a una carpeta que no existe (X18).
- **Los dos tests de plazo** (`test_correr_el_plazo_corta_un_comando_que_no_alcanza_a_terminar` y `test_un_git_que_pasa_el_plazo_se_informa_y_la_salida_sigue_en_cero`) corren un comando que duerme 30 s contra un plazo de 0.5 s. El corte ya no depende del tiempo.
- **Las verificaciones:**
  - El cambio del shim tuvo un verificador independiente, una tanda de corrección y un rechequeo ([multi-host](odd/tasks/multi-host.md), L60).
  - El doctor dio la misma salida que en la `0.9.0` en los casos de antes.
  - El CI pasó en Windows, Ubuntu y macOS.
- **Los estudios:** `odd/estudios/` trae cinco borradores para decidir: el costo de revisar, la calidad de los revisores, las reglas que cambian, `mold_source` y mudar la instancia a otra máquina.

## 0.9.0

**El primer uso pide menos pasos a mano, y revisar cuesta menos.** Todo sale de usar odd-ws en un ciclo real, de la instalación al cierre de un ticket.

### Lo que cambia para ti

- **El bootstrap, en una parada.**
  - Detecta tus repos y sus extensiones, y te muestra una sola propuesta, con cada término explicado. Un sí la aplica.
  - Deja el hook en LF con un `.gitattributes`, y hace el primer commit con el hook ejecutable, también en Windows.
  - Cierra con el siguiente paso: abrir tu primer ticket, o sembrar las reglas que tu repo ya tiene.
- **Los commits en la instancia.**
  - El agente commitea en la raíz de la instancia sin pedirte permiso cada vez, con `git add` por ruta y nunca push. Eso cubre el primer commit del bootstrap, el del ticket al abrirlo, el del cierre y el de la entrega.
  - Si prefieres aprobarlos, pon `"ask_before_commit": true` en `workspace.config.json`.
  - En los repos del equipo no cambia nada: cada commit se autoriza puntualmente.
- **Tus repos.** Un repo con `"own": true` es tuyo. Ahí `abrir` crea el worktree del ticket, y `cerrar` lo desarma si está limpio y su rama ya está en `origin`.
- **Los tickets.**
  - Sin tracker, `abrir` te propone el siguiente id (`T-1`, `T-2`…).
  - El ticket es el documento de trabajo. Uno grande suma `## Specs` y `## Tareas`, y todos tienen `## Seguimientos` para lo que queda para después.
  - Puedes trabajar desde la raíz, que es lo cómodo en VS Code. El ticket activo te llega como resumen al arrancar y después de cada `/compact`.
  - La conversación sigue en tu idioma después de compactar.
  - Los rituales (`abrir`, `cerrar`, `bootstrap`…) los escribes tú, y el agente te deja la línea exacta en vez de ofrecerte lanzarlos.
- **Revisar.**
  - Las rondas se numeran y nunca pisan una revisión anterior.
  - Cada unidad se revisa desde el commit sellado de la anterior, así que no se vuelve a revisar lo ya revisado.
  - Después de una corrección, el rechequeo mira solo lo que cambió o se sumó: una corrida de diseño más una por capa, también en `completo`. Su recibo cubre la unidad entera y se puede sellar.
  - Lo que el rechequeo encuentra y no es `CRITICAL` se deriva a `## Seguimientos`.
  - Te pide menos síes. El modo `0` corre sin preguntar, y aprobar una corrección aprueba su rechequeo.
  - Los revisores reciben las decisiones del ticket y no te las vuelven a discutir.
  - Los archivos que Python genera sin trackear (`__pycache__/`, `*.pyc`) ya no suben el modo.
- **Cerrar.** Si la entrega llega después del cierre, `cerrar` deja el ticket en `listo` sin repetir el cierre.
- **Las memorias.** `cerrar memorias` también lee las memorias que guardaste trabajando dentro de tus repos.
- **El doctor.** Te avisa de las extensiones de código que ninguna capa cubre, porque llevan la revisión a `completo`, y revisa que el hook esté en LF.

### Qué hacer en tu instancia

1. **Actualiza el plugin con los dos comandos** de [Doc/actualizar.md](Doc/actualizar.md). Sin `marketplace update`, te quedas en la versión anterior sin aviso.
2. **Copia lo nuevo de las plantillas** a tu `CLAUDE.md` y a `tickets/_plantilla/CLAUDE.md`, porque el bootstrap no las pisa. La lista está en [Doc/actualizar.md](Doc/actualizar.md#después-de-actualizar-las-plantillas-de-la-instancia).
3. **Corre `/odd-ws:doctor`.** Te avisa si al hook le falta el `.gitattributes` y qué extensiones no tienen capa.

### Detalle técnico

- **`bootstrap.py`:**
  - `--proponer` lee el `.code-workspace` y cuenta las extensiones con `git ls-files`.
  - `--commitear` hace el primer commit, con `git add --chmod=+x` para el hook.
  - El `.gitattributes` lleva `.githooks/* text eol=lf`, y el doctor revisa la línea en `instancia-eol`.
- **`config_loader.py`** valida tres claves opcionales: `tickets.prefix`, `ask_before_commit` y `repos.<r>.own`. `own` no puede ir junto con `agent_readonly`.
- **`ticket.py`:**
  - `--siguiente` da el siguiente id, contando también los tickets archivados.
  - `--activar` y `--desactivar` mueven la marca `.claude/estado/ticket-activo`.
- **`verificar_capa.py`:**
  - En la raíz, `SessionStart` inyecta un resumen del ticket activo: la cabecera sin las citas del molde, Objetivo, Specs, Tareas, Seguimientos y las últimas 5 entradas de la Bitácora.
  - Corre en `startup`, `resume`, `compact` y `clear`, en los tres CLI.
  - El tope de 12000 caracteres queda solo como red.
- **`recibo.py`:**
  - `--ronda` escribe en `revision/<fecha>-<modo>-<n>/`.
  - `--sellar` anota el commit que guarda lo revisado.
  - `--previo` escribe el recibo de un rechequeo, con `rechequeados`, `heredados` y `retirados`, desde la base del recibo previo.
  - `--derivado HALLAZGO=DESTINO` anota lo que se deriva.
  - Sin las opciones nuevas, la salida y los bytes del recibo son los de antes, según un diferencial contra la `0.8.0`.
- **`triaje.py`:**
  - La base de `--ticket` sale, en este orden, de la explícita, del sello más nuevo (si es ancestro de `HEAD` y más nuevo que el merge-base) o del merge-base.
  - Los archivos generados sin trackear salen en `generados`, fuera de la unidad.
- **`memorias.py --repo`** lee las memorias del proyecto de cada repo de la config.
- **El doctor** suma `capas-cobertura`.
- **Las skills:**
  - `revisar` suma la sección 9 (una corrección y un rechequeo) y las decisiones en el prompt.
  - `abrir` commitea el ticket.
  - `cerrar` suma la entrega después del cierre y el worktree de un repo propio.
- **Las verificaciones:**
  - Dos cambios tuvieron verificador independiente ([experiencia-de-uso](odd/tasks/experiencia-de-uso.md)):
    - los commits del bootstrap y de `cerrar`, con tres bloqueos corregidos y rechequeados;
    - la base sellada junto con el rechequeo, con un bloqueo de texto corregido y rechequeado (L40).
  - El CI pasó en Windows, Ubuntu y macOS.

## 0.8.0

**Las reglas de la capa corren aunque el agente escriba por la shell.**

### Lo que cambia para ti

- **El guard de comandos frena la escritura de un archivo de capa por la shell.** Funciona en los tres CLI, fuera de un writer. Si un comando deja contenido nuevo en un archivo de capa, se bloquea antes de correr: una redirección, `Set-Content`, `Out-File`, `cp`, `sed -i`, `python -c`… El mensaje manda a la herramienta de edición, para que el contenido pase por el primer toque y las reglas.
  - Siguen pasando borrar, vaciar y sacar un archivo de la capa.
  - Para renombrar un archivo que ya está en git, usa `git mv`.
- **Al terminar cada turno, se revisa lo que cambió.** Los archivos de capa que cambiaron durante el turno del agente principal pasan por las reglas, sin importar cómo se escribieron: con un script, con git o con una ruta en una variable.
  - Solo cuentan las líneas nuevas del turno, y también entra lo que se commiteó en el turno.
  - Con un bloqueo, el agente sigue una vez para corregirlo.
  - La revisión no sabe quién escribió el cambio. Si editas un archivo de capa mientras el agente trabaja, el agente recibe la vuelta con el pedido de avisarte y no tocarlo.
- **En Codex, confía los dos hooks nuevos.** Al abrir Codex, `/hooks` pide confiar `UserPromptSubmit` y `Stop` de odd-ws. Sin eso, la revisión del fin del turno no corre. El ítem `codex-hooks` del doctor lo avisa.
- **Cada mensaje cuesta un poco más.**
  - El inicio y el fin del turno lanzan un proceso de Python cada uno: unos 400 ms con dos repos, y unos 200 ms fuera de una instancia.
  - Cada comando de shell suma unos 30 ms en el guard.
- **No tienes que regenerar nada.** Los hooks vienen con el plugin.

### Detalle técnico

- **`writer_guard.escrituras()`** usa el mismo parser que `destinos()`, que no cambia, y devuelve solo los destinos que reciben contenido.
  - En PowerShell lee `-Path`, `-LiteralPath`, `-FilePath`, `-PSPath` o `-LP`, y en `New-Item` también `-Name`.
  - En Python toma el destino de cada llamada que escribe.
  - `guard_comandos` la combina con `config_loader.clasificar`, después de la capa 1 y antes de la capa 2. Un diferencial de 8556 casos contra la 0.7.0 no dio regresiones.
- **`revisar_turno.py`** es el hook nuevo de inicio y fin de turno: eventos `InicioTurno` y `FinTurno`, y capacidades P11 (`degradado`: si el hook falla, el turno cierra igual) y P12 (`soportado`).
  - La foto vive en `.claude/estado/turnos/<sesión>/` y sale de `git status --porcelain=v2 --branch`, que da también el HEAD de cada repo.
  - Si el HEAD avanzó durante el turno, lo commiteado se mide contra el commit viejo con `verificar_archivo(contra=...)`, un parámetro opcional que por defecto es `HEAD`.
- **Por host:**
  - **Claude Code:** `UserPromptSubmit` y `Stop`, con `decision: block`.
  - **Codex:** los mismos eventos, por JSON con exit 0. Un `UserPromptSubmit` de un subagente no saca foto.
  - **Pi:** `before_agent_start` y `agent_before_settle` del padre. Cada grupo de `hooks.pi.json` nombra su agente (`writer` o `principal`), y el shim los compara exactos.
- **Un writer en curso** queda fuera de la revisión solo si el host avisa que hay trabajo en segundo plano (`background_tasks` de Claude Code). Esos archivos los revisa `writer_stop`.
- **El doctor** cuenta los hooks nuevos, pide la confianza de los dos handlers en Codex y, en Pi, revisa la cobertura por agente.
- **Lo que no se ve:** lo que el guard y la revisión no alcanzan está en el «No ve» de `Doc/diseno.md`.
- **Las verificaciones:** las dos partes tuvieron un verificador independiente y una prueba de humo en vivo en los tres CLI (`odd/tasks/capa-por-shell.md`, L12-L14 y L20-L23).

## 0.7.0

**Paquetes de reglas importables desde git, y una guía para trabajar en equipo.**

### Lo que cambia para ti

- **Paquetes de reglas.** Con `/odd-ws:paquetes` importas a una capa de tu instancia las reglas de un repo git, fijadas a una etiqueta. Se copian a `.claude/reglas/paquetes/<nombre>/`, y un lock guarda la fuente, la etiqueta y su commit. Sus reglas corren junto a las tuyas, el primer toque muestra sus no-negociables y el pre-commit corre su suite. Importar nunca ejecuta código del paquete: lo lees en el diff antes de commitear. Cómo se escribe y se publica uno está en `Doc/capas-y-reglas.md`.
- **El doctor suma el ítem `paquetes`.** Sin paquetes sale NO APLICA y nada más cambia. Con paquetes revisa el lock, que nadie haya editado a mano lo copiado, los prefijos y los enlaces.
- **Una guía para compartir una instancia en equipo,** en `Doc/equipo.md`: qué viaja en el repo, qué hace cada dev al clonar, cómo se gradúa y se revisa la matriz en un pull request, y cómo encaja engram.
- **`/odd-ws:cerrar memorias` reconoce lo que ya graduó un compañero.** El origen de una memoria de engram es ahora su `sync_id`, que es el mismo en todas las máquinas. Las filas anteriores, con el número de la memoria, se siguen reconociendo en la máquina que las escribió.
- **No tienes que regenerar nada.** Si quieres la skill nueva en la lista de skills del `CLAUDE.md` de tu instancia, agrégala a mano: el bootstrap no pisa un archivo que ya existe.

### Detalle técnico

- `odd_ws/paquetes.py` (interno, fuera de `PUBLICO`) lee y valida el lock `.claude/reglas/paquetes.json` y el manifiesto `odd-ws-paquete.json`, calcula la huella (sha256 de la lista blanca, con CRLF normalizado) y detecta enlaces, junctions y choques de prefijo.
- `verificar_capa` corre cada paquete de la capa aislado: uno roto no calla a la capa ni a otro paquete. Solo el hook aísla también el módulo de la capa (`verificar_archivo(aislar_la_capa=True)`); la compuerta del writer sigue viendo su excepción. El primer toque suma el `no-negociables.md` de cada paquete, por nombre.
- `reglas.py --test` corre la suite de cada paquete en su propio proceso (`python -I`, tope de 300 s). `matriz.py` valida la matriz de cada paquete contra sus archivos (`chequeo`, `pasiva`, `evidencia` y `descarte`). Un lock roto, o un prefijo de paquete igual al de una capa, sale con 2.
- `paquetes.py` (`importar`, `actualizar`, `quitar` y `listar`, con `--ensayo`) resuelve la etiqueta con `ls-remote --tags`, clona solo esa etiqueta fuera de la instancia y exige que `HEAD` sea su commit. Rechaza enlaces y submódulos en la etiqueta, una URL con credenciales y un destino enlazado. Git corre sin prompts (`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) y solo con los protocolos file, https, ssh y git. Una fuente local se guarda absoluta, con un aviso.
- En `/odd-ws:cerrar memorias`, el origen de engram es `memoria:engram-<sync_id>`, con el id numérico como respaldo, y el chequeo de reconocimiento acepta los dos.
- Sin lock, la salida de cada comando es la misma que en la 0.6.2, salvo la fila nueva del doctor (diferencial de 57 escenarios).

## 0.6.2

**Un hueco del guard en Codex y una compuerta del writer que lee mejor el cierre.**

### Lo que cambia para ti

- **El guard de comandos bloquea el parche de Codex aplicado por la shell.** En Codex, cuando la herramienta de edición fallaba, un agente podía escribir un archivo con `codex.exe --codex-run-as-apply-patch`, y los chequeos de capa no corrían. Ahora ese comando se bloquea en los tres CLI, con un mensaje que pide usar la herramienta de edición.
- **La compuerta del writer lee mejor el cierre.** Reconoce los campos escritos con tilde o mayúscula (`límites:`, `Verificación:`). Una línea de la lista que empieza con el nombre de otro campo ya no lo pisa. Y en `limites`, ni `n/a`, ni `nada`, ni `none`, ni `no aplica` valen como límite, igual que `ninguno`. No tienes que regenerar los writers.

### Detalle técnico

- `guard_comandos` (capa 1) bloquea `--codex-run-as-apply-patch` cuando va como argumento, también dentro de `bash -c` y `powershell -Command`. Nombrado dentro de comillas, por ejemplo en un mensaje de commit, no bloquea.
- `writer_stop.parsear_resultado` normaliza el mensaje a NFC y compara los nombres de campo sin tildes y en minúscula. Dentro de `verificacion` o `limites`, una viñeta con el nombre de un campo ya visto queda como entrada. `NINGUNO_RE` suma `ningún límite`, `nada`, `n/a`, `none`, `no aplica` y `sin límites`, solo como frase completa (seguimientos F1, F2 y F4 de `odd/tasks/limites-en-el-cierre.md`).
- La nota P9 del manifiesto de Pi (`odd_ws/hosts/pi.py`) registra que la instalación desde la fuente git se probó a mano con la 0.6.1, y que el ítem `pi-plugin` del doctor dio OK.
- La nota P5 registra que la acción `seguir` de la compuerta se probó en vivo con la 0.6.1: frenó una vez a un writer que cerró sin el bloque de resultado, y el writer volvió a cerrar con el bloque completo.

## 0.6.1

**Dos correcciones del primer toque,** encontradas al grabar odd-ws en gentle-shell.

### Lo que cambia para ti

- **Una capa recién generada ya no recibe el texto de ejemplo como reglas.** Mientras no escribas los no-negociables de una capa, la primera lectura no inyecta nada y la primera edición pasa. Antes, el texto de ejemplo de la plantilla llegaba como si fueran reglas y bloqueaba la primera edición. No tienes que hacer nada en tu instancia.
- **En gentle-shell, lo que odd-ws suma a un resultado ya no se confunde con el resultado.** Los no-negociables y los motivos de un bloqueo llegan después de la línea «[odd-ws] Lo que sigue no es parte del resultado de la herramienta: lo agrega odd-ws.». Antes llegaban pegados al final del archivo leído, y un modelo los tomó como parte del archivo.

### Detalle técnico

- `verificar_capa.no_negociables` compara el bloque, sin contar espacios ni saltos de línea, con el de `plugin/plantillas/capa.md` renderizado para la capa (`odd_ws/capas.relleno_de_la_plantilla`). Si coinciden, la capa no tiene no-negociables. La plantilla tuvo un solo texto desde que existe, así que la comparación cubre toda instancia generada.
- En el shim de Pi, `conTexto` antepone una línea en blanco y la marca al texto que agrega, sea contexto, bloqueo o falla. Los proveedores de `pi-ai` juntan los bloques de texto de un resultado con un salto de línea, así que sin la marca el texto quedaba pegado al resultado.

## 0.6.0

**Soporte para gentle-shell (Pi).** Una instancia puede trabajarse también desde gentle-shell, que es Pi con subagentes. Los guards, el primer toque, las reglas de las capas y la compuerta de los writers corren con los mismos scripts. Se probó a mano en Windows, con gentle-shell 4.8.0 y Pi 1.5.2.

### Lo que cambia para ti

- **`hosts` acepta `pi`.** Con `pi` declarado, la instalación genera `.pi/agents/*.md` a partir de los mismos agentes, y el doctor revisa Pi. Sin `pi`, nada cambia en Claude Code ni en Codex.
- **El paquete de Pi se instala desde git o desde un clon:** `gentle-shell install git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v<versión>` o `gentle-shell install <ruta del clon>`. No está en npm. El README explica el home aislado de gentle-shell y `--link`.
- **Abre gentle-shell en la raíz de la instancia y dale confianza con `/trust`.** gentle-shell solo lee los agentes de `<cwd>/.pi/agents`, y sin confianza no llegan las skills de la instancia. Las del plugin se invocan con `/skill:<nombre>`, por ejemplo `/skill:doctor`.
- **Preguntar necesita pantalla.** Con pantalla, un comando dudoso pide tu confirmación; sin ella, se bloquea con el motivo.
- **Los writers necesitan gentle-shell.** Con Pi a secas no hay subagentes, y el doctor lo avisa. La tarea de un writer no puede empezar con `/`: Pi la expandiría, y el writer correría sin guards.
- **El writer corre en la raíz de la instancia.** odd-ws bloquea su lanzamiento si gentle-shell lo correría afuera o en otra instancia: con un `repository_root` o un `workspace_root` fuera de la instancia, con un worktree dentro de ella que trae su propia config, o sin ellos si la instancia está en una subcarpeta de su repo git. Relánzalo sin esos campos: el writer edita tus repos por su ruta absoluta. En gentle-shell, la instancia tiene que ser la raíz de su repo git, o no estar en ninguno.
- **Los guards de comandos cubren las tres herramientas de shell de gentle-shell:** `bash`, `bash_background` y `monitor`, además de `powershell`. Las dos nuevas corren un comando en segundo plano con el mismo bash que `bash`, y antes pasaban sin guard.
- **`/skill:doctor` en Pi revisa** la versión de Pi (1.5.0 o más), gentle-shell, que el paquete cargue el shim, la confianza del proyecto y los `.pi/agents`. `--arreglar pi-agentes` los genera o los pone al día.
- **Las skills en Pi:** sus comandos usan `${CLAUDE_PLUGIN_ROOT}`, que Pi no define, así que la extensión la define al cargarse, con la carpeta del plugin, si no estaba.

### Detalle técnico

- **`odd_ws/hosts/pi.py`:** el adaptador de Pi, con su manifiesto de capacidades. Sin pantalla, preguntar se degrada a bloquear. P3, P5 a P7 y P10 son `degradado`; P1, P2, P4, P8 y P9, `soportado`.
- **`plugin/shim/`:** una extensión TypeScript sin dependencias ni build. Lanza los scripts de Python sin shell, les pone un timeout y falla cerrada en pre. `nucleo.ts` es neutral, para que lo reuse otro host. Los hooks están en `hooks/hooks.pi.json`, con su test de paridad contra `hooks.json`.
- **El writer en gentle-shell:** el padre marca la tarea de `subagent_run` con el nombre del writer, y el hijo corre `writer_stop` en `agent_before_settle`, con la bitácora de `writer_guard`. Antes de marcarla, el padre calcula el `cwd` que le daría gentle-shell al hijo y bloquea si la instancia que encontrarían sus guards no es la del padre.
- **`bash_background` y `monitor`:** `pi.py` las lee como shell POSIX, `hooks.pi.json` les corre `writer_guard` y `guard_comandos`, y el doctor exige esa cobertura.
- **`package.json` en la raíz del repo:** es el paquete de Pi. Va en la raíz porque Pi instala un repo git entero y no admite un paquete en una subcarpeta. Es privado y no tiene dependencias ni scripts. Su versión sube con los dos `plugin.json`: lo exige un test.
- **El doctor de Pi:** los ítems `pi`, `gentle-shell`, `pi-plugin`, `pi-confianza` y `pi-agentes`; `hooks-host` revisa también la forma de `hooks.pi.json`. `pi-plugin` calca la resolución de paquetes de Pi y no cuenta una fuente `npm:`.
- **El pre-commit y el CI** corren también las suites `*.test.ts` del shim, con Node 22.18 o más (el CI usa 24).

## 0.5.0

**El cierre del writer dice también qué no demuestra lo que corrió.** La idea viene del video «Un test en verde puede estar mal», de RefactorIA Devs, con su cadena afirmación → prueba → resultado → límite, que compartió Denver2828. odd-ws ya exigía el resultado (`verificacion:`); ahora exige también el límite.

### Lo que cambia para ti

- **El bloque `## Resultado` del writer suma `limites:`**, con al menos una línea por cada cosa que su verificación no demuestra: un caso que ningún test cubre, otro sistema operativo, una integración que no corrió, los datos reales. Una suite verde demuestra los casos que ejecuta. Nada más. `ninguno` no vale.
- **Después de actualizar, corre `/odd-ws:doctor`** (en Codex, `$doctor`) y regenera los writers que siguen en la plantilla anterior: `--arreglar writer-<capa>` y, si usas Codex, después `--arreglar codex-agentes`. Un writer que quede en la plantilla anterior cierra sin `limites:`, se come el único bloqueo de la compuerta y pasa en el segundo cierre, hasta que lo regeneres. Los pasos están en `Doc/actualizar.md`.

### Detalle técnico

- **`writer_stop.py`:** `limites` entra en `CAMPOS` y en la `PLANTILLA`, se lee como lista igual que `verificacion` (también en la misma línea) y no valida si falta, si está vacío, si conserva el placeholder o si solo dice `ninguno` o `ninguna`. Queda en el sidecar del writer, en `resultado.limites`. En Codex vale lo mismo: la compuerta lee el último mensaje igual y la bitácora no cambia.
- **La plantilla del writer pasa a la v2** (`odd-ws-plantilla: 2`), con su huella nueva y los snapshots por capa actualizados. Los revisores siguen en la v1. Los TOML de Codex se derivan del `.md`, así que llevan la v2 al regenerarse.

## 0.4.1

**Los guards ven más formas de escribir el mismo comando.** Un force push o un borrado que el agente escribe dentro de un shell, con la ruta completa de git o con un escape de PowerShell ya no pasa sin el chequeo. No tienes que cambiar nada en tu instancia.

### Lo que cambia para ti

- **El guard de comandos bloquea también lo que el agente le pasa a un shell:** `bash -c '…'`, `sh -c`, `powershell -Command "…"`, `pwsh -c`, `cmd /c "…"`, `eval '…'`, `iex '…'` e `Invoke-Expression`, también detrás de `sudo`, `docker run` o `xargs`. Lo mismo con git llamado por su ruta: `& "C:\Program Files\Git\cmd\git.exe" push --force`. Un texto que solo menciona el comando sigue pasando: un mensaje de commit, un `echo` o el argumento de un script.
- **Lo que puede empezar a bloquear:** un borrado fuera del scratch dentro de un contenedor (`docker exec app sh -c 'rm -rf /app/tmp'`) bloquea igual que si se escribiera directo. Si es deliberado, córrelo tú a mano.
- **En PowerShell,** un backtick dentro de una palabra (``g`it push --force``) ya no esconde el comando, en Claude Code y en Codex.
- **Dentro de un `writer-<capa>`,** una escritura que sale del scratch hacia un repo bloquea como cualquier escritura sobre el repo, también cuando sale por `.\.`, por un enlace seguido de `..` o con `Join-Path` y `[IO.Path]::Combine`.
- **En Linux y macOS,** un `..` después de un enlace se resuelve donde apunta el enlace, como lo hace el sistema, al decidir qué repo toca un comando.
- **Qué frenan y qué no:** la guía de hooks (`Doc/hooks.md`) dice ahora que los guards frenan los errores y los atajos del agente, no a un agente que intenta esquivarlos a propósito.

### Detalle técnico

- **`guard_comandos.py`, capa 1:** lee el primer argumento que un shell recibe como comando (después de `-c`, `-Command` o `/c`, o el de `eval`, `iex` y `wsl`), hasta dos niveles, sin los cuerpos de heredoc que no recibe un shell. Una ruta entre comillas que termina en `git` o `git.exe`, en la posición del comando, cuenta como `git` en una pasada aparte que solo suma bloqueos.
- **`guard_comandos.py`, escapes:** en el dialecto PowerShell, una segunda pasada sobre el texto sin backticks, que respeta las comillas simples y los here-strings. En Bash, una pieza con `\` fuera de comillas no cuenta como scratch, en ningún sistema.
- **`writer_guard.py`:** lee una pieza de Bash con `\` como separador y como escape (con un tope, y falla cerrada al pasarlo), decide `Join-Path` y `[IO.Path]::Combine` con la ruta resultante, y sigue el `cd` de Bash como lógico (salvo con `cd -P`, `set -P` o `set -o physical`), con todas las carpetas posibles cuando no se puede saber cuál es.
- **`odd_ws/rutas.py`:** en POSIX, `ubicar` deja los `..` para `realpath`. En Windows el `..` sigue siendo texto, que es lo que hace Win32. La capa 2 pregunta si una mención toca un repo marcado con la lectura física o con la lógica.
- **Fuera de alcance, documentado en `Doc/diseno.md`:** una palabra partida con comillas o escapes, un comando en una variable de PowerShell, `Start-Process`, los decodificadores, `-EncodedCommand`, un texto que llega a un shell por una tubería y las sustituciones entre comillas dobles.

## 0.4.0

**Graduar las memorias del proyecto.** `/odd-ws:cerrar` puede sacar candidatos de las memorias del proyecto, además de los del ticket. La idea de usar las memorias como fuente de candidatos viene de las skills de observaciones de Denver2828 ([gentle-contribution-skills](https://github.com/Denver2828/gentle-contribution-skills)).

### Lo que cambia para ti

- **`/odd-ws:cerrar memorias`** gradúa a la matriz las reglas que ya están en la memoria en archivos de Claude Code y, si la tienes, en engram. Te muestra la fila, la regla y la evidencia exactas antes de escribirlas, sin copiar la memoria ni nombrar personas, y lo que no apruebas no te lo vuelve a proponer mientras el `modified` de la memoria no cambie.
- **El cierre de un ticket** termina con una línea: cuántas memorias quedan sin triar.
- **En Codex,** la memoria en archivos de Claude Code no está disponible: el modo sigue con engram, si está.

### Detalle técnico

- **`memorias.py`** lista las memorias `feedback` (y las `project` con `--con-project`) con su estado: `graduada`, `ilegible`, `cambiada`, `descartada`, `vista` o `nueva`. Si no encuentra el directorio de memoria, sale con 2 y nombra la ruta que probó.
- **El registro local** de lo visto y lo descartado vive fuera del repo, en `~/.odd-ws/memorias/<proyecto>.json`, y lo escribe `--registrar` después del sí.
- **engram** lo consulta la skill, con `scope: project` y `limit: 20`, y declara su cobertura como parcial. Su origen en la matriz es `memoria:engram-<id>`.

## 0.3.1

**Soporte para macOS y Linux.** Hasta esta versión, los hooks llamaban a `python`, que macOS, Ubuntu y Debian no traen de fábrica: ahí no arrancaban, y los guards dejaban pasar sin el chequeo. Por ahora lo prueba el CI; nadie lo probó a mano todavía.

### Lo que cambia para ti

- **macOS y Linux:** los hooks arrancan con `python3`, el único que traen de fábrica macOS, Ubuntu y Debian. Los guards cierran además formas de esquivarlos propias de esos sistemas (el detalle, abajo).
- **Si Python no arranca, Claude Code bloquea.** Con Claude Code 2.1.295 o más, la herramienta se bloquea con el error en vez de pasar sin el chequeo.
- **Windows con el instalador clásico de python.org, winget o choco:** no crean `python3`, así que en Claude Code las herramientas quedan bloqueadas hasta que lo instales con el Python install manager o la Microsoft Store. `/odd-ws:doctor` te dice qué falta y cómo arreglarlo.
- **`/odd-ws:conocimiento --claims` funciona en macOS,** y rechaza formas de `uniq` y `sort` que escribían archivos, también en Windows.
- **`/odd-ws:doctor` en macOS** ya no marca FALTA en `plugin-root` cuando la ruta apunta al mismo plugin escrito de otra forma.
- **Si tu instancia ya existe y usas macOS, Ubuntu o Debian:** su `.githooks/pre-commit` sigue llamando a `python`. Copia encima el de `plugin/plantillas/pre-commit`, que prueba `python3`, `python` y `py`.

### Detalle técnico

- **El arranque de los hooks:**
  - En Claude Code 2.1.295 o más, los hooks de pre y post van con `onFailure: "block"`.
  - Codex lanza `python3`, y `python` en Windows.
  - `/odd-ws:doctor` revisa el intérprete que lanza cada host declarado y da el arreglo.
- **Los guards en macOS y Linux:**
  - En macOS, un push o un commit sobre un repo protegido escrito con otras mayúsculas o en otra forma Unicode ya no pasa.
  - La excepción del scratch reconoce el de Claude Code en cada sistema: `/tmp/claude-<uid>` en macOS y `<TMPDIR>/claude-<uid>` en Linux. Un borrado ya no se escapa del scratch por un enlace seguido de `..` ni por `.\.`.
  - `git -C //<repo>` ya no esquiva la capa 2.
- **`/odd-ws:conocimiento --claims`:** en macOS, las afirmaciones corren sin `/usr/bin/timeout`. La lista blanca cierra formas de `uniq` y `sort` que, con el getopt de BSD (también el de Git for Windows), escribían archivos.
- **`auditar_lecturas`** ve una lectura prohibida aunque la ruta pase por un enlace.
- **El doctor:** `plugin-root` compara la forma canónica y, si no alcanza, `samefile`.
- **Fuera de Windows:** `scriptdom.ps1` ya no busca la DLL en `C:\Program Files`. Sin `-Dll`, sale con 3 (falta la DLL) en vez de un error.

## 0.3.0

- **Soporte para Codex CLI.** El plugin trae su manifiesto para Codex (`.codex-plugin/plugin.json`) y sus hooks (`hooks/hooks.codex.json`). Los hooks corren con `--host codex` y bloquean por JSON, también en Windows. En Codex, cada hook necesita tu confianza en `/hooks`, y en la 0.167 la vuelve a pedir con cada actualización del plugin.
- **`hosts` en `workspace.config.json`.** Declara los CLI del workspace, por ejemplo `["claude-code", "codex"]`. Sin la clave, el workspace es solo de Claude Code y nada cambia. Con `codex`, la instalación genera `.codex/agents/*.toml` a partir de los mismos agentes, y `.codex/config.toml` para que Codex lea los `CLAUDE.md`.
- **`/odd-ws:doctor` por host.** Con Codex declarado, revisa:
  - la versión, el plugin y la confianza de los hooks y del proyecto;
  - `.codex/config.toml` y los agentes TOML: `--arreglar codex-config` y `--arreglar codex-agentes` los generan o los ponen al día a partir del `.md`.

  `hooks-host` avisa si un hook tiene el `--host` mal puesto.
- **Writers en Codex.**
  - **La compuerta de cierre:** también funciona en Codex. Los archivos y comandos del writer salen de una bitácora que anota `writer_guard`.
  - **El primer toque:** frena también a sus writers.
  - **Codex 0.167 o más:** hace falta para lanzar un writer por su rol.
  - **En Windows:** un writer que escribe en los repos de las capas necesita `[windows] sandbox` y esos repos como `writable_roots` en la config de Codex. Ver `Doc/diseno.md`.
  - **Pendiente conocido:** con el sandbox `unelevated`, la medición de líneas reales del writer da 0/0.
- Para leer la config de Codex, el doctor necesita Python 3.11 o más.

## 0.2.2

- `/odd-ws:doctor` marca gentle-ai, engram, jq y el `credential.helper` de git como **AVISO opcional**, no como FALTA: el plugin no los necesita.
- La plantilla del `CLAUDE.md` de la instancia explica qué ajusta del ODD de gentle-ai si también lo usas.

## 0.2.1

- El triaje cuenta los consumidores en la base explícita de un repo sin remoto (`--repo RUTA#BASE`).
- `/odd-ws:abrir` crea la rama con `--no-track`, y `/odd-ws:revisar` ya no anuncia «otro orden» cuando el cambio tiene un solo archivo.

## 0.2.0

- Las skills del ciclo de un ticket: `/odd-ws:abrir`, `/odd-ws:revisar` y `/odd-ws:cerrar`.
- Los revisores leen el `CLAUDE.md` del ticket desde el disco, el recibo distingue `limpio`, `pendiente` y `con-hallazgos`, y `/odd-ws:cerrar` no repite el id de una regla.
