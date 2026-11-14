# Changelog

Las notas de cada entrega de `odd-ws`. Cada versión es una sección `## <versión>`, y su contenido es el cuerpo del release que publica `.github/workflows/release.yml` cuando llega la etiqueta `odd-ws--v<versión>`. El pre-push no deja entregar una versión sin su sección.

## Sin publicar

**Soporte para gentle-shell (Pi).** Una instancia puede trabajarse también desde gentle-shell, que es Pi con subagentes. Los guards, el primer toque, las reglas de las capas y la compuerta de los writers corren con los mismos scripts. Todavía no corrió dentro de un Pi real: la prueba de humo llega con la entrega.

### Lo que cambia para ti

- **`hosts` acepta `pi`.** Con `pi` declarado, la instalación genera `.pi/agents/*.md` a partir de los mismos agentes, y el doctor revisa Pi. Sin `pi`, nada cambia en Claude Code ni en Codex.
- **El paquete de Pi se instala desde git o desde un clon:** `gentle-shell install git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v<versión>` o `gentle-shell install <ruta del clon>`. No está en npm. El README explica el home aislado de gentle-shell y `--link`.
- **Abre gentle-shell en la raíz de la instancia y dale confianza con `/trust`.** gentle-shell solo lee los agentes de `<cwd>/.pi/agents`, y sin confianza no llegan las skills de la instancia. Las del plugin se invocan con `/skill:<nombre>`, por ejemplo `/skill:doctor`.
- **Preguntar necesita pantalla.** Con pantalla, un comando dudoso pide tu confirmación; sin ella, se bloquea con el motivo.
- **Los writers necesitan gentle-shell.** Con Pi a secas no hay subagentes, y el doctor lo avisa. La tarea de un writer no puede empezar con `/`: Pi la expandiría, y el writer correría sin guards.
- **`/skill:doctor` en Pi revisa** la versión de Pi (1.5.0 o más), gentle-shell, que el paquete cargue el shim, la confianza del proyecto y los `.pi/agents`. `--arreglar pi-agentes` los genera o los pone al día.
- **Las skills en Pi:** sus comandos usan `${CLAUDE_PLUGIN_ROOT}`, que Pi no define, así que la extensión la define al cargarse, con la carpeta del plugin, si no estaba.

### Detalle técnico

- **`odd_ws/hosts/pi.py`:** el adaptador de Pi, con su manifiesto de capacidades. Sin pantalla, preguntar se degrada a bloquear. P3, P5 a P7 y P10 son `degradado`; P1, P2, P4, P8 y P9, `soportado`.
- **`plugin/shim/`:** una extensión TypeScript sin dependencias ni build. Lanza los scripts de Python sin shell, les pone un timeout y falla cerrada en pre. `nucleo.ts` es neutral, para que lo reuse otro host. Los hooks están en `hooks/hooks.pi.json`, con su test de paridad contra `hooks.json`.
- **El writer en gentle-shell:** el padre marca la tarea de `subagent_run` con el nombre del writer, y el hijo corre `writer_stop` en `agent_before_settle`, con la bitácora de `writer_guard`.
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
