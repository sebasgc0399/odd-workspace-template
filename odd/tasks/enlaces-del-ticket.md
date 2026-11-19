# Los enlaces del ticket (I61, `0.10.0`)

Objetivo: que los enlaces de un ticket, o de cualquier documento `.md`, se puedan revisar y depurar desde cualquier cliente: con su ruta absoluta para abrirlos o copiarlos, y sabiendo cuáles están rotos.
Rama: `feat/enlaces-del-ticket`, desde `de07bf8`. Entrega: un commit con la unidad, que incluye este documento; el push a main y la etiqueta, solo con autorización.
Pruebas: `python3 plugin/scripts/<script>.tests.py`, todas con el bucle de `CONTRIBUTING.md`.

## Specs

- **S1. El pedido.** Es de un usuario de la comunidad (_00_), en el hilo de la `0.9.0`: «lo que igual se podria mejorar es si se abrieran los enlaces que aparecen en las ODDs, aunque como, por lo menos en las que tengo ahora, son variados, lo mismo enlace a carpeta que a .md,... igual es un poco farragoso, pero si nos los abre por lo menos que si los copia al portapapeles o preguntara, eso ayudaría mucho a revisarlas/depurarlas». El autor, sobre la propuesta: «Metamosla en esta version».
- **S2. Listar los enlaces.** `ticket.py --enlaces <id | ruta a un .md>` lista los enlaces del documento:
  - del `CLAUDE.md` del ticket si recibe un id, o del `.md` que se le pase;
  - cada uno con su texto, su ruta absoluta resuelta contra la carpeta del documento, su tipo (archivo o carpeta) y si el destino existe;
  - los rotos, marcados aparte;
  - sin escribir nada.

  Aceptar cualquier `.md` cubre también los documentos de ODD de gentle-ai (`odd/tasks/*.md`), porque el pedido no dice cuáles usa.
- **S3. Copiarlos.** Con `--copiar`, la misma lista de rutas absolutas va al portapapeles. Si no hay herramienta de portapapeles, avisa y la lista sale igual por pantalla.
- **S4. Una sola regla de enlace válido.** Se reutiliza el criterio de `conocimiento.py` (`LINK_MD_RE`, `_resolver`, `_existe` y `ESQUEMA_RE`), extendido a carpetas y a archivos que no son `.md`. No se escribe una segunda regla. Los enlaces con esquema (`https:`, `mailto:`) se listan aparte, sin verificarlos.
- **S5. Supuesto: no se abren solos.** Abrir un enlace depende del sistema y del cliente, y lanzar programas desde el agente es un efecto que habría que pedir cada vez. En la terminal de VS Code, una ruta absoluta se abre con Ctrl+clic, y en cualquier otra se puede copiar. S8 lo reemplaza: se abren, pero solo el que el usuario elige.
- **S6. Una solución por escenario.** El autor: «Pero en si si tu dices en la practica se le pide a claude en la sesion, pero analiza bien, como experiencia de usuario cual seria la mejor solucion?», «Pero tenemos que pensar una o varias soluciones para diferentes escenarios, para mejorar la experiencia del usuario» y, sobre el diseño de L3, «Si». La evidencia es una captura de _00_ trabajando en Gentle Companion, la interfaz web de Gentle Shell en `127.0.0.1`, en lo que parece Linux: ahí no hay Ctrl+clic, y un chat en el navegador no puede abrir un archivo local.
- **S7. Depurar sin pedirlo.**
  - Los enlaces rotos de un ticket aparecen solos en el resumen del ticket activo, al arrancar la sesión y después de cada `/compact`, y al cerrar el ticket con `/odd-ws:cerrar`. Si todos están bien, no se dice nada.
  - Un enlace con una ruta de la máquina (`C:\…`, `/home/…`, `~/…`) se marca como **no portable**, porque se rompe en el clon de otra persona.
- **S8. Navegar según el escenario.** `ticket.py --enlaces` numera los enlaces que existen, y `--abrir <n>` abre el que el usuario eligió. El agente pregunta cuál antes de abrir.
  - **En un escritorio local** (Windows, macOS, o Linux con `DISPLAY` o `WAYLAND_DISPLAY` y sin `SSH_CONNECTION`), abre con el abridor del sistema: `explorer`, `open` o `xdg-open`.
  - **En WSL** (`WSL_DISTRO_NAME`), abre en Windows con `explorer.exe` y la ruta pasada por `wslpath -w`.
  - **En una sesión remota o sin pantalla** (SSH, un contenedor, un servidor), no abre, porque se abriría en otra máquina: muestra la ruta y dice por qué no abrió.
  - **En un editor** (VS Code, GitHub, Obsidian), los enlaces relativos al documento ya se abren con un clic, y de eso se encarga S7.
- **S9. Supuesto: abrir no ejecuta.**
  - Solo se abre un número de la lista: una ruta local que existe, pasada como argumento y nunca por una shell.
  - Una carpeta se abre en el gestor de archivos.
  - Un archivo de texto, de datos o de imagen se abre con su programa.
  - Cualquier otro archivo, como un `.exe`, un `.bat`, un `.sh` o un `.command`, no se lanza: se muestra en su carpeta, porque abrirlo lo ejecutaría.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T1 | S1 a S5 | `ticket.py --enlaces` y `--copiar`, sobre el criterio compartido con `conocimiento.py`, con sus tests y sus docs | delegada, en un carril propio. Risk: none, porque solo lee y el portapapeles se toca a pedido | hecho (L2) | `8315dc9` |
| T2 | S8, S9 | La lista numerada, `--abrir <n>` con el abridor de cada escenario, y la skill `abrir` que pregunta antes | delegada, en paralelo con T3 por el contexto del orquestador. Risk: item 2, porque lanza un programa del sistema; lleva verificador | hecho; verificador: sin bloqueantes, y sus avisos corregidos en C1 (L5) | `b72ae44` |
| T3 | S7 | Los rotos y los no portables en el resumen del ticket activo y en `cerrar` | delegada, en paralelo con T2, con superficies disjuntas. Risk: none | hecho (L4) | `b72ae44` |
| T4 | S7, S8 | La costura: la lista de `--enlaces` marca los no portables de T3, y los docs de las dos | inline, al final. Risk: item 2, porque el portapapeles buscaba su herramienta en la carpeta actual | hecho (L4) | `b72ae44` |
| C1 | S8, S9 | Corrección de los avisos del verificador: la coma en Windows y WSL, `/select,` en dos argumentos, un número enorme, `~` sin barra, y la skill `enlaces`, que el agente puede usar por su cuenta (L5) | delegada. Risk: item 2 | hecho; rechequeo en curso | este commit |

## Log

- **L1** (2026-11-19) El pedido de _00_ y la decisión del autor, tal cual, están en S1. Antes de decidir, se verificó qué hay hoy: `conocimiento.py:191-199` detecta enlaces rotos, pero solo en los docs de conocimiento y solo a `.md`.
- **L2** (2026-11-19) T1 hecho en `8315dc9`.
  - **Qué hace.** `ticket.py --enlaces <id | ruta>` lista los enlaces con su texto, su ruta absoluta y su tipo; los rotos y los enlaces con esquema salen aparte. `--copiar` manda las rutas al portapapeles y, sin herramienta, avisa y las muestra igual.
  - **Una sola regla.** La regla de enlace válido pasó de `conocimiento.py` a `odd_ws/enlaces.py`, y `conocimiento.py` la importa con su salida sin cambios.
  - **Pruebas.** El pre-commit corrió todas las suites en verde.
  - Queda esperar la respuesta de _00_ sobre si esto es lo que pedía.
- **L3** (2026-11-19) El autor cuestionó la experiencia: «pedírselo a Claude» obliga a saber que existe y muestra la lista lejos de donde se lee. Después mostró a _00_ trabajando en Gentle Companion. El análisis separa dos trabajos:
  - **depurar**, que no depende del entorno y va sin pedirlo (S7);
  - **navegar**, que depende de dónde está la persona (S8): escritorio local, WSL, remoto o un editor.

  El autor aprobó ese diseño para la `0.10.0` con un «Si». S9 es un supuesto de seguridad del orquestador: abrir no puede ejecutar un archivo.
- **L4** (2026-11-19) T2, T3 y T4 hechos. Dos writers trabajaron en paralelo en el mismo árbol, con superficies disjuntas, y el orquestador hizo la costura y los docs. Las sesiones se cortaron una vez a mitad de los docs, sin perder nada del árbol.
  - **T2.** `odd_ws/abridor.py` decide el escenario con el entorno y la plataforma inyectados, y `ticket.py` numera la lista y suma `--abrir <n>`. La skill `abrir` pregunta antes de abrir.
    - **Decisiones del writer:**
      - `SSH_CONNECTION` cuenta como remoto en cualquier sistema.
      - En macOS, una carpeta con extensión (un `.app`) se muestra con `open -R`.
      - El abridor se busca solo en las entradas absolutas del `PATH`.
      - El plazo es de 15 s.
      - El código de `explorer` no cuenta.
    - **Pruebas.** RED: 17 pruebas en ERROR sin el módulo, y 14 de 56 en `ticket.tests.py`. GREEN: 17/17 y 56/56. Los cinco mutantes cayeron, y el diferencial contra `7ea37f6` solo cambia la numeración pedida.
  - **T3.** `enlaces.es_ruta_de_la_maquina` y `enlaces.revisar`. `verificar_capa.py` agrega al resumen del ticket activo hasta 5 enlaces rotos o con una ruta de la máquina, después del recorte, sin tocar el disco para una ruta de la máquina y con el plazo del hook. `cerrar` los revisa en su paso 1.
    - **Pruebas.** RED: 4/6 y 99/107. GREEN: 6/6 y 107/107. El diferencial de SessionStart dio 48/48 iguales en los tres hosts y los cuatro orígenes, con un control positivo que sí cambia.
  - **T4.**
    - **La costura.** La lista marca `(ruta de la máquina)` en los sanos y en los rotos.
    - **Un defecto de T1 que encontró el writer de T2.** `--copiar` buscaba su herramienta con `shutil.which`, que en Windows mira primero la carpeta actual, salvo que esté definida `NoDefaultCurrentDirectoryInExePath`. El entorno de Claude Code la define, así que el riesgo no se veía. Ahora busca con `abridor.buscar`.
    - **Pruebas.** Las dos dieron RED. El de la herramienta plantada, solo después de quitar esa variable: el falso copió las 8 rutas. Después, GREEN: `ticket.tests.py` 58/58, `abridor` 17/17, `enlaces` 6/6, `verificar_capa` 107/107 y `conocimiento` 113/113.
  - **Avisos del writer de T3, sin acción en esta tanda:**
    - un `file:///C:/…` se ignora como esquema;
    - un `/docs/x.md` se marca como ruta de la máquina, aunque en GitHub es relativo a la raíz del repo;
    - los enlaces dentro de bloques de código también cuentan, como en `--enlaces`.
- **L5** (2026-11-19) El verificador independiente de `b72ae44` contra `7ea37f6`: sin bloqueantes.
  - **Veredictos:**
    - S7 PASS: 8 tickets, 4 orígenes y 3 hosts; con enlaces sanos, idéntico byte a byte. 10 hosts UNC en 0.31 s, contra 1.27 s de un solo `stat` de control.
    - S8 PASS.
    - S9 PASS en lo reproducible: 54 destinos en 4 escenarios, con symlinks, junctions, doble extensión y mayúsculas.
    - El arreglo de `--copiar` PASS: el defecto se reproduce en la base sin `NoDefaultCurrentDirectoryInExePath`, y no en el candidato.
  - **Los avisos que se corrigieron en C1, porque la versión tiene que salir bien:**
    1. una ruta con coma en Windows y WSL, que `explorer` separa;
    2. `/select,` con espacios;
    3. **el agente no veía el procedimiento:** vivía en `abrir`, que es solo del usuario, y por eso nace la skill `enlaces`, que el modelo puede invocar;
    4. un número de más de 4300 cifras;
    5. `~notas.md` marcado como ruta de la máquina;
    6. una frase del diseño que prometía de más.
  - **Avisos sin acción, fuera de dominio o informativos:** un flujo alternativo de NTFS (`f.bat:.md`), un `xdg-open` que bloquea y se informa como no abierto, y metadatos del sistema que la extensión no ve.
  - **C1, por un writer.** Cada ítem dio RED antes y GREEN después: `abridor` 19/19, `ticket` 61/61, `enlaces` 7/7, `verificar_capa` 108/108, `bootstrap_textos` 29/29, `pi` 68/68, `doctor` 202/202 y `conocimiento` 113/113.
    - **Diferencial contra `b72ae44`.** Solo cambian:
      - los destinos con `~` sin barra;
      - el argv de `/select,`;
      - la ruta con coma.
    - **Las skills, donde se enumeran.** Suma `enlaces` en la plantilla del `CLAUDE.md`, en `Doc/uso.md` y en `bootstrap_textos.tests.py`. P8 de Pi ahora cuenta nueve skills y nombra `paquetes`, que le faltaba.
