# Lo que sale de la máquina: nada secreto ni personal sale sin que lo veas, y queda escrito qué hace odd-ws con la red (R20)

Objetivo: que el commit frene los archivos secretos (I93), que nada personal ni una clave privada salga sin un chequeo (I94), que un `SECURITY.md` diga qué sale de la máquina y una prueba lo mantenga honesto (I97), y cerrar lo que la auditoría de la `0.14.0` a la `0.16.0` dejó de seguridad, más la escritura atómica de `tapar.py` y la verificación con Code Mode.
Rama: `feat/lo-que-sale-de-la-maquina`, en `D:/Project/odd-ws-wt/salida`. Está apilada sobre la R19 en curso (`b4f8a16`): lo que la R19 sume después se integra hacia acá con un merge. Entrega: un commit por unidad. Sale en la `0.18.0`, sin publicar: publicar lleva el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py`, `python plugin/plantillas/pre-commit.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites, con el `GIT_INDEX_FILE` del commit en el entorno.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap. Lo marcado como **decisión de diseño** lo decidió el orquestador con la autonomía del loop (L1), y queda a ratificar por el autor.

- **S1** (I93, los archivos secretos). «El commit frena los archivos secretos: un `.env`, una clave (`*.pem`, `*.key`, `id_rsa`, `id_ed25519`) o un `credentials*.json` stageado no entra, salvo sus variantes de ejemplo (`.example`, `.sample`, `.template`).»
  - **Decisión de diseño:**
    - **Dónde.** La plantilla `plugin/plantillas/pre-commit` de la instancia deja de llamar directo a `reglas.py --test`: llama a un punto de entrada nuevo del plugin, `pre_commit.py`, que corre el chequeo de los archivos secretos y después las pruebas de las reglas, como hoy. Así la plantilla cambia una sola vez, y los chequeos que vengan después salen con el plugin, sin tocarla de nuevo.
    - **El chequeo.** Mira los nombres stageados (`git diff --cached --name-only -z`, con el entorno limpio). Frena con el nombre del archivo y cómo sacarlo del stage (`git restore --staged <ruta>`). Las variantes de ejemplo pasan.
    - **Lo que cuesta.** Cambiar la plantilla suma su huella de la `0.18.0` a `huellas.json`, una viñeta «En la `0.18.0`» en `Doc/actualizar.md`, y el aviso de plantillas en cada instancia, que se arregla con `--arreglar plantillas` si la copia está sin tocar.
    - La plantilla sigue en ASCII y con LF, con el sondeo de `python.sh` intacto (`pre-commit.tests.py`).
- **S2** (I94, lo personal y las claves privadas). «Antes de que algo salga de la máquina, un chequeo busca rutas personales (`/home/<usuario>/`, `/Users/<usuario>/`, `C:\Users\<usuario>\`) y claves privadas: en el pre-push y al exportar un paquete de reglas.»
  - **Decisión de diseño:**
    - **Las instancias no tienen pre-push** (el bootstrap instala solo el pre-commit). Sumar una plantilla de pre-push toca el bootstrap, el doctor y las huellas, y en una instancia, que suele ser personal, una ruta propia no es una fuga. Por eso el chequeo va donde algo sí sale de la máquina:
      - **al exportar un paquete de reglas:** un subcomando nuevo de `paquetes.py` revisa la carpeta de un paquete antes de publicarlo, con rutas personales, claves privadas (`secretos.BLOQUE_RE`) y una `fuente` local guardada como ruta absoluta; «Publicar un paquete» en `Doc/capas-y-reglas.md` suma ese paso;
      - **en el pre-commit de la instancia** (el punto de entrada de S1), una clave privada pegada en un archivo stageado frena, porque una clave no tiene variante legítima. Una ruta personal solo avisa, sin frenar.
    - **El pre-push con plantilla queda fuera,** como seguimiento si alguien lo pide.
    - Un marcador como `<usuario>` no cuenta como ruta personal.
- **S3** (I97, `SECURITY.md`). «Un `SECURITY.md` con tres cosas: cómo reportar una vulnerabilidad en privado, el modelo de amenaza que ya está escrito y un inventario de todo lo que puede salir de tu máquina. Una prueba lo mantiene honesto.»
  - **Decisión de diseño:**
    - El modelo de amenaza se resume y enlaza a `Doc/diseno.md`, que sigue siendo la fuente.
    - **El inventario** es una tabla con cada llamada que puede salir a la red:
      - `git ls-remote` y `git clone` de `paquetes.py`;
      - `claude plugin marketplace add` del doctor;
      - el `fetch` de la auditoría de ramas de la R19;
      - los CLI de terceros que el doctor solo consulta.
    - **La prueba** junta, con el AST de Python (así no cuenta comentarios), los strings de los módulos del plugin y de `tools/` que nombran un verbo de red (`fetch`, `push`, `pull`, `ls-remote`, `clone`, `marketplace`, `curl`, `http://`, `https://`, imports de `socket`, `http` o `requests`).
      - Cada archivo con uno tiene que estar en el inventario, o en una lista de excepciones con su porqué: los guards, que esos verbos los leen y no los corren.
      - Un archivo nuevo que salga a la red sin entrar al inventario hace fallar la prueba.
- **S4** (la verificación con Code Mode). Del plan aprobado: «Code Mode de Claude Code (experimental): se verifica que los guards siguen disparando dentro de los scripts, y se documenta.»
  - **Decisión de diseño.**
    - La documentación de Claude Code dice que, dentro de un script de Code Mode, cada llamada dispara `PreToolUse` con su nombre de siempre. Los comandos de un script corren en Git Bash, y uno compuesto llega unido, como `cd 'app' && git push`.
    - Se prueban, con payloads de esas formas, los guards de comandos y de writers (un comando compuesto, una edición). La forma de PowerShell de un script llega como `Bash`.
    - El plazo de los hooks (8 s con un timeout de 10) ya termina antes de que Code Mode rechace por tiempo.
    - `Doc/hooks.md` lo dice, y la corrida real con Code Mode prendido queda como un paso manual para el autor, porque no anda en el panel de VS Code.
- **S5** (la escritura atómica de `tapar.py`). El autor: «Sí, mueve tapar.py atómico a la 0.18.0».
  - **Decisión de diseño.** Un módulo hoja nuevo, `odd_ws/archivos.py`, con `reemplazar(ruta, contenido)`: escribe a un temporal en la misma carpeta y hace `os.replace`, y limpia el temporal si algo falla. Lo usan `tapar.py`, y en lugar de sus copias privadas `fallas._reemplazar` y `entregas._reemplazar`. Una falla a mitad deja el archivo original intacto y sin `.tmp`.
- **S6** (los seguimientos de seguridad de la auditoría). Del plan: «`config_loader.clasificar` deja de lanzar cuando una ruta está dentro de la instancia pero `relpath` no la alcanza; un aviso del inicio de sesión que falla ya no se lleva puestos a los demás; una falla del sub-chequeo del porqué queda en el rastro de fallas de la `0.14.0`.»
  - **Decisión de diseño:**
    - `_relativa` que lanza `ValueError` dentro de `clasificar` se toma como «no clasifica».
    - `plantillas_instancia.aviso_de_inicio` va en su propio `try`, que anota la falla con `fallas.anotar` (la A7 de la `0.14.0`).
    - `comun._aislada` acepta un `al_fallar` opcional, y `verificar_capa` lo usa para anotar sus fallas. Ningún veredicto cambia.
- **S7** (la versión). Se actualizan:
  - el CHANGELOG de la `0.18.0`;
  - `Doc/actualizar.md`, por la plantilla del pre-commit;
  - la versión en los dos `plugin.json` y en `package.json`, el README y `Doc/`;
  - `tools/huellas.py`.

  Después, un verificador independiente. Publicar lleva el ok del autor.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento y su espejo en engram | inline | hecha | |
| T1 | S1, S2 (pre-commit) | El punto de entrada del pre-commit, los archivos secretos y las claves pegadas | un writer, en paralelo con T2 (motivo: dos unidades independientes con superficies disjuntas, de varios minutos cada una) | hecha (L3) | `a1b9349` |
| T2 | S5, S6 | `odd_ws/archivos.py`, `tapar.py` atómico y los seguimientos de la auditoría | un writer, en paralelo con T1 | hecha (L4) | `a1df267` |
| T3 | S2 (paquetes), S3, S4 | El chequeo de un paquete antes de publicarlo, `SECURITY.md` con su prueba, y la verificación con Code Mode | un writer, después de T1 y T2 (motivo: el respaldo de contexto del orquestador) | hecha (L6) | `9733db4` |
| T4 | S7 | El CHANGELOG, la versión y el verificador | docs inline; verificador delegado | versión lista (L7); verificador: el bloqueante de S3 corregido (L8); con el ok del autor para publicar | `7823093` y el cierre |

## Log

- **L1** (2026-11-25) El autor:
  - aprobó el plan de la R20 a la R22: «Sí, va ese orden»;
  - movió `tapar.py` atómico a esta versión: «Sí, mueve tapar.py atómico a la 0.18.0»;
  - dejó el loop a criterio del orquestador: «Vale, te dejare trabajando en loop termina con las publicacion y las version tu te organizas trabaja como te deje ayer».
- **L2** (2026-11-25) El mapa del explorador, sobre `225113f`.
  - **S1.** Hoy nada mira los nombres de los archivos stageados. `guard_comandos` solo pide autorización para `add` y `commit`, y `secretos` tapa texto, no archivos. El patrón para leer lo stageado es el de `tools/barrido.py:127-141` y `marcadores.py:97-163`; `tools/` no viaja con el plugin, así que se calca.
  - **S2.**
    - Las instancias no tienen pre-push.
    - `paquetes.py` no tiene exportación: publicar un paquete es una etiqueta y un push a mano (`Doc/capas-y-reglas.md:161-166`).
    - Una `fuente` local se guarda como ruta absoluta en el lock (`paquetes.py:88-96`).
    - Unas 95 rutas sintéticas de usuarios en las pruebas obligan a excluir los `*.tests.py` si el chequeo corre sobre el repo de odd-ws.
  - **S3.**
    - No hay `SECURITY.md`; el modelo de amenaza está en `Doc/diseno.md:558`.
    - Lo que sale a la red:
      - `paquetes.py:106` (`ls-remote`) y `:128` (`clone`);
      - el doctor con `claude plugin marketplace add` (`hosts/claude_code.py:231`, `doctor.py:975`);
      - el `fetch` de la auditoría de ramas de la R19;
      - los CLI de terceros que el doctor consulta.
    - No hay imports de `http`, `socket` ni `requests`.
    - Los verbos llegan por envoltorios (`_git(...)`) y tuplas (`*FETCH`). Por eso la prueba busca strings y no solo llamadas.
  - **S4.** Todos los hooks de herramientas tienen `onFailure: block`, y ningún matcher cubre MultiEdit. `guard_comandos.tests.py:1581-1583` y `capacidades.tests.py` fijan el cableado.
  - **S5.** `tapar.py:81-88` trunca en el lugar. `fallas._reemplazar` y `entregas._reemplazar` son copias privadas iguales, y uno compartido tiene que vivir en un módulo hoja, porque `comun` importa `fallas`.
  - **S6.** El mapa trae los llamadores de `clasificar`, la línea de la A7 (`verificar_capa.py:699`), los usos de `_aislada` y las pruebas de cada uno.
  - **Las trampas:**
    - los núcleos de `cerrar` (10 bytes libres) y de `revisar` (96) no admiten texto;
    - la plantilla va en ASCII y con LF;
    - todo texto en español va en tú;
    - el barrido de la lista negra.
  - **El tamaño estimado:**
    - S1: 300 a 400 líneas;
    - S2: unas 200, con el pre-push fuera;
    - S3: unas 250;
    - S4: chica;
    - S5 y S6: unas 100.
- **L3** (2026-11-25) T1, un writer, desde `b4f8a16`. Lo cortaron el reinicio de la sesión y el límite de 5 horas, y se lo retomó con su contexto. Cubrió S1 y la parte de S2 que va en el pre-commit.
  - **Lo nuevo:**
    - la plantilla `pre-commit` corre `pre_commit.py --raiz <instancia>` (sigue en ASCII y con LF, con el sondeo intacto);
    - `pre_commit.py` y su prueba;
    - en `secretos.py`, dos detectores públicos que T3 reusa: `claves_privadas` y `rutas_personales`;
    - `Doc/actualizar.md` y `Doc/uso.md`.
  - **El orden:** lee lo stageado con una sola llamada y los contenidos con un solo `cat-file --batch`. Frena los nombres de secretos y una clave pegada, avisa de las rutas personales y, si nada frena, corre `reglas.py --test` con el mismo código de salida.
  - **Decisiones del writer que se aceptan:**
    - **No usa `comun.entorno_git()` para leer lo stageado.** Dentro del hook, el `GIT_INDEX_FILE` es el índice del commit (`.git/index.lock` en `commit -a`, `next-index-*.lock` en `commit -- <ruta>`), y sin él un `commit -a` dejaría pasar un `.env` modificado. Usa el entorno del hook con `--no-optional-locks`, como `marcadores.py`.
    - **Frena también `.env.*`.** Una variante de ejemplo es un nombre con un segmento `example`, `sample` o `template`, sin distinguir mayúsculas.
    - **Falla cerrado:** si git no puede leer lo stageado, el commit para.
    - **La plantilla busca `pre_commit.py`** para decidir si encontró el plugin. Un `plugin_root` anterior a la `0.18.0` recibe el arreglo guiado.
      - Seguimiento: el ítem `plugin-root` del doctor y `seguir_al_vigente` todavía juzgan por `reglas.py`.
    - **Lo que no frena:** borrar un `.env` del repo, ni `id_rsa.pub`, ni un ejemplo de clave con `<PRIVATE_KEY>` o `...`.
    - **Las rutas personales:** las carpetas `Shared`, `Public` y `Default` no cuentan, y un usuario de Windows con espacio no se detecta.
  - **Las pruebas,** cada regla vista en RED y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `pre-commit.tests.py` 22/22, `pre_commit.tests.py` 12/12 y `secretos` 15/15;
    - `registro` 7/7, `bootstrap` 212/212 y `doctor` 245/245.
    - Un mutante que saca el `GIT_INDEX_FILE` heredado lo atrapan dos pruebas.
  - **La diferencial contra `b4f8a16`,** con la plantilla y el plugin viejos contra los nuevos, da el mismo código, la misma cantidad de commits y la misma salida de las reglas (verde, rojo y sin config).
  - **Risk: ítem 2.** Es un guard nuevo que frena commits en el pre-commit de cada instancia y falla cerrado. El cambio de plantilla toca además el ítem 3, que fue pedido.
  - **Scratch del writer**, en `%TEMP%`: `tmp.CRQTJNKuqV`, `tmp.Oi3TRGBUTV`, `tmp.fhTS1w97mK` y `tmp.H9Z5HX87YC`. Va a la limpieza del autor.
- **L4** (2026-11-25) T2, un writer, desde `b4f8a16`. Lo cortaron el reinicio de la sesión y el límite de 5 horas, y se lo retomó con su contexto. Cubrió S5 y S6.
  - **S5:**
    - el módulo hoja `odd_ws/archivos.py`, con `reemplazar` (un temporal hermano y `os.replace`);
    - lo usan `tapar.py` y `fallas`, en lugar de su `_reemplazar` privado;
    - `entregas._reemplazar` se migra después del merge de la R19.
  - **S6:**
    - `clasificar` devuelve `None` si `relpath` lanza;
    - la A7: `verificar_capa._plantillas_cambiadas` atrapa la excepción del aviso de plantillas y la anota;
    - la W2: `_aislada` y `por_ruta` aceptan un `al_fallar` opcional, que `verificar_capa` usa para anotar sus fallas.
  - **Decisiones del writer que se aceptan:**
    - `por_ruta` también lleva `al_fallar`, porque si no, la falla de un archivo de un parche de varios callaba;
    - `reemplazar` sigue los enlaces simbólicos, para no dejar el secreto en el destino real;
    - un `al_fallar` que lanza se traga;
    - el temporal se limpia con un `chmod` antes, porque en Windows `copymode` le copia el solo lectura.
  - **Un cambio de comportamiento que no se pidió, a ratificar:** en POSIX, `tapar.py` ahora reemplaza un archivo de solo lectura en una carpeta con escritura; antes salía con 2. En Windows sigue saliendo con 2 y deja el archivo intacto. Se acepta, porque el objetivo es tapar el secreto.
  - **Las pruebas,** cada regla vista en RED y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `archivos` 8/8, `tapar` 11/11, `fallas` 3/3, `config_loader` 123/123, `verificar_capa` 160/160 y `comun` 65/65;
    - los llamadores de `clasificar` en verde;
    - `doctor` 245/245 y `writer_stop` 61/61. Este último falló una vez con tres suites a la vez y pasa solo: era carga.
    - Tres mutantes, todos atrapados.
  - **La diferencial contra `b4f8a16`:** 16 casos sin diferencias, entre el inicio de sesión en los tres hosts y `tapar.py`.
  - **Los docs:** el orquestador integró el texto de T2 en `Doc/diseno.md`. El writer editó `Doc/hooks.md` y `references/recibo.md`.
  - **Risk: ítem 3.** `_aislada`, `por_ruta` y `clasificar` se comparten con otros hooks. Sus valores por defecto conservan el comportamiento de antes, y lo fijan las pruebas de cada llamador.
  - **Scratch del writer:** en el scratchpad de la sesión, `mut-6bZN`, `verif-yp2c` y los `dif-*`; además, `%TEMP%\tmpveiuqpfw`. Va a la limpieza del autor.
- **L5** (2026-11-26) La R19 y el cierre de S5.
  - **La R19 entró con un merge limpio** (`487dc62`, desde `ab6248e`, la versión `0.17.0`). Así T3 ve el `fetch` de la auditoría de ramas para el inventario de red.
  - **S5 queda completo.** `entregas._reemplazar`, la última copia privada, se cambió por `archivos.reemplazar` (`f530976`): la prueba nueva se vio en RED y después en GREEN, `entregas` 11/11 y 14/14, y `archivos` 8/8.
  - **Sigue T3:** el chequeo de un paquete, `SECURITY.md` con su prueba, y Code Mode. Un writer.
  - **Lo que cambia T3:** el verificador de la R19 encontró que el `fetch` de la auditoría podía escribir refs fuera de `origin`. Se corrige en la R19 (`--refmap=`) y llega acá con el próximo merge, antes del verificador de esta versión.
- **L6** (2026-11-26) T3, un writer, desde `f530976`. Lo cortó el límite de 5 horas y se lo retomó con su contexto. Cubrió la parte de S2 de los paquetes, S3 y S4.
  - **S2:** `paquetes.py revisar <carpeta>`, de solo lectura y sin instancia.
    - Mira solo los archivos de la lista blanca del importador.
    - Busca rutas personales y claves pegadas con los detectores de `secretos`, una `fuente` local absoluta y los enlaces.
    - Sale con 0, 1 o 2, y nunca muestra la clave.
    - «Publicar un paquete» suma el paso.
  - **S3:**
    - `SECURITY.md`, en español: el reporte privado de GitHub, el resumen del modelo de amenaza y el inventario de lo que sale de la máquina;
    - `tools/inventario_de_red.tests.py`, que lee con el AST los strings de los `.py` de `plugin/` y `tools/` y exige que cada archivo con un verbo de red entero, una URL o un import de red esté en el inventario o en `EXCEPCIONES` (solo los dos guards).
  - **S4:** pruebas de payloads de Code Mode en `guard_comandos` y `writer_guard`. **No hay bug de seguridad:**
    - el compuesto `cd '…' && git push` se pregunta, y el forzado se bloquea;
    - las escrituras de un writer detrás de un `cd` se bloquean;
    - la forma de PowerShell que llega como `Bash` se lee como POSIX.
    - La documentación de Code Mode no dice «Git Bash» literalmente, así que `Doc/hooks.md` tampoco lo dice.
  - **Decisiones del writer que se aceptan:**
    - una `fuente` local es un valor dentro de los archivos del paquete, no el lock de la instancia: el lock no se puede arreglar antes de empujar la etiqueta;
    - un enlace en el paquete es un hallazgo;
    - la prueba cuenta solo verbos enteros, para no llenar las excepciones con prosa;
    - `SECURITY.md` lista también las consultas de versión que corre el doctor.
  - **Las pruebas,** cada regla vista en RED (con un mutante por regla en el chequeo de paquetes, y una sonda que planta una llamada de red sin inventario) y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `paquetes` 23/23 y 23/23;
    - `inventario_de_red` 4/4;
    - `registro` 7/7;
    - `guard_comandos` 85/85;
    - `writer_guard` 128/128.
  - **La diferencial contra `f530976`:** 14 pasos de `paquetes`. Solo cambia la línea de uso de argparse, que ahora nombra `revisar`.
  - **Lo que queda para el autor:**
    - habilitar el reporte privado de vulnerabilidades en la config del repo;
    - hacer la corrida real con Code Mode en una terminal.
  - **Seguimientos:**
    - la skill `/odd-ws:paquetes` no nombra `revisar`;
    - `revisar` no mira el resto del repo del paquete, como un README.
  - **Risk: ítem 5.** La prueba del inventario pasa a ser una compuerta del pre-commit y del CI.
  - **Scratch del writer:** `%TEMP%\tmp.5EsAOKrLE9` y la carpeta `t3\` del scratchpad de la sesión. Va a la limpieza del autor.
- **L7** (2026-11-26) La corrección de la R19 y la versión.
  - **La corrección de la R19** (`f10fecf`: el `fetch` de la auditoría con `--refmap=` y sin askpass) entró con un merge limpio (`020f986`). El inventario de red no cambia, porque `FETCH` sigue diciendo `fetch`.
  - **T4, la versión, inline.**
    - La `0.18.0` quedó en los dos `plugin.json`, el `package.json`, el README, `Doc/actualizar.md:28` y `Doc/uso.md:66`.
    - El CHANGELOG suma su sección. Esta versión cambia una plantilla, el `pre-commit`, y `Doc/actualizar.md` ya trae su viñeta «En la `0.18.0`» (de T1).
    - **`tools/huellas.py`** dio 122 huellas de 28 versiones, hasta la `0.18.0`.
      - La `0.17.0` no tiene etiqueta, así que no entra a la tabla.
      - Al publicar, primero se etiqueta la `0.17.0` y después se regenera, que es la A6 que cierra la R21.
    - En el roadmap, R20 queda «lista, sin publicar», con I93, I94 e I97 «lista (`0.18.0`, sin publicar)».
  - **Falta el verificador independiente,** por los ítems 2 (el pre-commit que frena y el `writer_guard` de Code Mode), 3 (`clasificar`, `_aislada` y la plantilla) y 5 (la compuerta del inventario). Publicar lleva el ok del autor.
- **L8** (2026-11-26) El verificador independiente, sobre `020f986` y `7823093` contra `f10fecf`.
  - **Veredicto:** S1, S2, S4, S5, S6 y S7 PASS. S3 FAIL por un bloqueante de documentación.
  - **B1.** `SECURITY.md` decía «Los hooks no salen a la red». En un clon parcial (`--filter=blob:none`), el `git blame` del porqué baja de `origin` los blobs que faltan, y el inventario no lo nombraba. El comportamiento ya estaba en la base; lo nuevo era la frase falsa.
  - **La corrección:**
    - `SECURITY.md` dice que los hooks no lanzan nada que salga a la red, con la salvedad del clon parcial, que es de git;
    - el inventario suma una fila para esa bajada, con `GIT_NO_LAZY_FETCH=1` como la forma de apagarla;
    - «Lo que la prueba no ve» nombra las brechas que encontró el verificador: verbos fuera de la lista, `import urllib` seguido de `urllib.request`, una llamada nueva en un archivo que ya está en la tabla, y la bajada de git.
  - **La recomprobación, en el orquestador:** el texto dice lo que hace el código, y `inventario_de_red` (4/4) y `registro` (7/7) dan verde.
  - **Queda para que decida el autor:** que los hooks apaguen esa bajada con `GIT_NO_LAZY_FETCH=1`, como ya hace `afirmaciones.py`. En un clon parcial, el porqué y los chequeos dirían entonces «no se pudo chequear».
  - **Advertencias, como seguimientos:**
    - el inventario mira archivo por archivo;
    - el detector de claves no ve un PEM partido en strings, ni un UTF-16 sin BOM;
    - `tapar.py` en POSIX: un archivo en una carpeta sin escritura ya no se tapa, y `os.replace` corta los enlaces duros. Lo dice `Doc/diseno.md`;
    - una copia de emergencia vieja del plugin con la plantilla nueva frena los commits;
    - nombres de secretos fuera de la lista: `*.env`, `id_ecdsa`, `*.p12` y `.npmrc`.
  - **Lo que probó y pasa:**
    - 28 nombres en el pre-commit;
    - los flujos `commit -a`, `commit -- <ruta>`, `-i` y `--amend`;
    - un commit rechazado deja el repo igual;
    - falla cerrado;
    - las salidas son iguales a la base en los hooks de los tres hosts, en `tapar.py` y en `paquetes.py`;
    - la actualización de la 0.17 a la 0.18;
    - la A7 y `clasificar`;
    - la compuerta del inventario;
    - los compuestos de Code Mode;
    - siete mutantes.
    - Las suites dan 71/71, también con un `GIT_INDEX_FILE` ajeno.
  - **Los pasos del autor, hechos:**
    - habilitó el reporte privado de vulnerabilidades (Settings, Advanced Security);
    - la corrida real de Code Mode pasó con `--permission-mode manual`: en un solo script, odd-ws bloqueó un `cd … && git push --force` y un `git reset --hard`, y el `git log` corrió.
    - En el modo automático, el clasificador de Claude Code rechazó el script entero antes que los hooks.
    - `Doc/hooks.md` lo dice.
  - **El cierre para publicar:**
    - la `0.17.0` ya se publicó, y su etiqueta está en esta rama;
    - `huellas.py` dio 127 huellas de 29 versiones;
    - el roadmap da por hechas R19 y R20.
  - **El autor dio el ok para publicar cada versión apenas esté lista:** «La idea es ya tienes mis Ok, para empezar a publicar, para que vayamos avanzando».
  - **Scratch del verificador:** `%TEMP%\tmp.nrzWUtSSDs`. Va a la limpieza del autor.
