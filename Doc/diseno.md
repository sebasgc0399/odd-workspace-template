# Diseño de odd-workspace-template

> Decisiones tomadas entre el 2026-10-22 y el 2026-10-24. El motor se extrae de un proyecto de trabajo anterior (el «proyecto de origen»). El cuaderno de diseño con la evidencia de ese proyecto vive **fuera** de este repo: aquí solo quedan las decisiones y su porqué, sin dominio de ningún empleador.

## 1. Objetivo

Llevar un motor de trabajo con agentes de un proyecto a otro. Al llegar a un equipo, a una empresa o a un proyecto propio, o al estrenar portátil, se instala, se le da el contexto del entorno nuevo, y en la primera semana el ambiente queda blindado: ciclo ODD, hooks deterministas por capa, primer toque, writers con compuerta y revisión con recibo atado al diff.

## 2. Principios

1. **Mecanismo > Memoria.** Lo aprendido se vuelve un artefacto verificable, no algo que el modelo tiene que recordar.
2. **Motor sin reglas.** El plugin trae mecanismos, no las reglas del proyecto de origen. Cada regla nació de un incidente, y una regla que viaja sin su incidente es culto al cargo. En un proyecto nuevo, cada regla se gana con origen y evidencia.
3. **Nada del dominio de un empleador entra al repo.** Lo garantiza un chequeo determinista (el barrido, §8), no el cuidado.
4. **Un negativo no es evidencia** hasta probar que el instrumento sabe decir que sí. Toda regla que bloquea tiene un control positivo.
5. **El contrato no se rompe nunca; el molde es configurable.**

## 3. Forma: plugin + instancia (D1)

- **Motor** = plugin privado de Claude Code (`odd-ws`), publicado como marketplace (`odd-workspace-template`).
- **Instancia** = los archivos de cada proyecto, generados por `/bootstrap`: `CLAUDE.md`, `workspace.config.json`, permisos, agentes y moldes de cada capa, matriz de reglas, dominio. El plugin no puede llevarlos: no carga `CLAUDE.md` y su `settings.json` solo aplica `agent` y `subagentStatusLine`.
- **Salida de emergencia:** si una empresa bloquea los marketplaces, se copia `plugin/` dentro del `.claude/` de la instancia y los hooks se cablean desde `settings.json`. Por eso los scripts no dependen de `CLAUDE_PLUGIN_ROOT` más allá del cableado.

## 4. Diseño del plugin (P1–P6)

| # | Decisión | Por qué |
|---|---|---|
| P1 | **Tres niveles:** motor (dispatcher de eventos, primer toque, deadline, filtro de preexistentes, writers, triaje, recibo) y **biblioteca por lenguaje** en el plugin; **reglas de dominio** en la instancia, cargadas por el contrato `verificar(ctx) -> [hallazgos]`. La instancia **importa** la biblioteca del plugin | Las reglas de dominio necesitan lógica (no caben en una fila de regex), y un arreglo en una primitiva se hace una sola vez. La biblioteca pasa a ser API pública: chica y versionada. **Cómo se importa (R-2):** paquete `odd_ws` en `plugin/scripts/`; el hook corre desde esa carpeta, así que `import odd_ws` funciona sin tocar `sys.path`, y los módulos de la instancia los carga el dispatcher, que ya tiene el paquete a mano (ningún archivo de la instancia busca el plugin). La versión de la API es `schema_version`; `odd_ws.PUBLICO` declara la superficie y una prueba la congela |
| P2 | Habilitado **por proyecto**, con scope **local** como respaldo dentro de repos de un equipo; **nunca a nivel usuario**. El marketplace sí se registra a nivel usuario (lo hace `/doctor`) | Los hooks de un plugin disparan en toda sesión donde está habilitado. A nivel usuario se pagaría su costo en cada Read/Edit/Write de todos los proyectos |
| P3 | Raíz de la instancia: subir desde `CLAUDE_PROJECT_DIR` hasta el primer `workspace.config.json`; rutas de la máquina en `workspace.local.json` (ignorado por git); clasificar el archivo editado con rutas canónicas `normcase(realpath(…))`; los globs del taller (`workshop`) y del filtro por repo (`match`) son por segmentos (`**` cruza carpetas; `*` no) y los worktrees de cada repo salen del registro de git, no de la config; **configuración rota ≠ ausente** (ausente: no-op en silencio; rota: los hooks no bloquean, pero `SessionStart` lo avisa al arrancar o retomar la sesión, con el motivo y que se corra `/odd-ws:doctor` (`startup|resume`, T8 B7); la excepción es la Capa 2 del guard de comandos, que con la config rota pregunta, L49); `schema_version` en el config | El archivo editado suele estar fuera del árbol; una carpeta puede llegar con dos nombres (junctions, `c:` vs `C:`); un no-op silencioso por una configuración rota es un instrumento mudo |
| P4 | **Semver único** en `plugin.json` (sube la mayor si se rompe el config, el contrato de módulos o la API de la biblioteca); `schema_version` = versión mayor; canales `odd-ws` (GitHub, rama `stable`) y desarrollo desde una ruta local, solo en un sandbox; release con tag `odd-ws--vX.Y.Z`; **sin auto-update en máquinas de trabajo** (se actualiza a mano entre tickets); una mayor solo después de migrar las instancias | Con P1(a), una versión nueva cambia los chequeos de todas las instancias. Un marketplace de ruta local carga el código en sitio en cada sesión |
| P5 | Estado **por tipo:** efímero de sesión en `.claude/estado/` de la raíz de la instancia (ignorado, poda a 7 días); **decisiones con autoridad** en `.claude/registro/` (versionado); evidencia (recibos) en la carpeta del ticket; en `CLAUDE_PLUGIN_DATA` solo lo reconstruible | Desinstalar el plugin borra `CLAUDE_PLUGIN_DATA`; una decisión con autoridad es evidencia, no estado |
| P6 | El **plazo** de cada hook viaja como argumento junto a su **timeout**, en la misma entrada de `hooks/hooks.json`, en forma exec; sin `--plazo`, 8 s; la suite valida plazo ≤ timeout − 2 s | Claude Code descarta toda la salida de un hook que llega a su timeout. La forma exec no depende del shell |

### Contrato de los módulos de capa (P1)

Cada capa con reglas de dominio tiene un módulo en la instancia, `.claude/reglas/verificar_<capa>.py`, con una función `verificar(ctx) -> [hallazgos]`. El dispatcher del plugin (`verificar_capa.py`) lo carga en cada `Edit` o `Write` sobre un archivo de esa capa. El módulo puede importar `odd_ws`.

- **`ctx`:** `ruta`, `relativa` (en el taller, el nombre del archivo), `relativa_repo` (en el taller, la ruta del original en el repo si hay línea base; si no, `None`), `origen` (`repo` | `taller`), `capa`, `bytes`, `texto`, `es_nuevo`, `agregadas` `[(n, texto)]`, `hunks` `[{agregadas, quitadas}]` y `limite` (deadline del reloj monotónico, o `None`).
- **Hallazgo:** `{id, modo (aviso | bloqueo), severidad, linea, fragmento, mensaje}`. Un hallazgo cuyo `fragmento` ya estaba en una línea quitada del mismo hunk se descarta. Si el módulo devuelve algo que no es un hallazgo válido, el archivo entero se calla: nunca se bloquea sin poder explicarlo.
- **Primer toque:** el primer `Read` de una capa en (sesión, agente) inyecta el bloque `<!-- no-negociables -->` de `.claude/skills/capa-<capa>/SKILL.md`; el primer `Edit`/`Write` sin esa inyección se bloquea una vez y el reintento pasa. `compact` y `clear` lo reinician para la sesión principal. Un agente que precarga `capa-<capa>` en su frontmatter no lo recibe.
- **Línea base del taller** (`layers.<capa>.workshop_baseline`, opcional): `{repo, under?, strip_prefix?}`. Una copia sin trackear se compara con el original de ese nombre en la rama de `origin/HEAD` del repo; con cero o con más de un candidato, no hay base.
- **Opcionales del módulo:** `REGLAS`, una secuencia de objetos con `.id` (la lista de lo que el módulo chequea), y `precalcular(ctxs)`, que recibe todos los `ctx` de una calibración antes de verificarlos (por ejemplo, para analizar el lote de una vez). La suite del módulo vive en `.claude/reglas/verificar_<capa>.tests.py`.
- **Corridas sueltas** (`plugin/scripts/reglas.py`, fuera de la sesión): `--test <capa>` corre la suite como `__main__` y sale con su código; `--test` sin capa corre la de cada capa que tenga una y sale con 1 si alguna queda en rojo. `--calibrar <capa> <carpeta> [--detalle]` pasa por `verificar(ctx)`, como archivos nuevos, todos los archivos de la capa bajo la carpeta (en orden, sin `.git` ni `node_modules`) y cuenta los aciertos por regla: `ID archivos=N aciertos=M` y, con `--detalle`, hasta 20 `<relativa>:<línea> <fragmento>` por regla. Con `REGLAS`, cada regla tiene su línea aunque tenga 0 aciertos, que es lo que decide si puede bloquear; sin `REGLAS`, solo aparecen los IDs vistos y se avisa. Un módulo que no carga, revienta o devuelve un hallazgo inválido se reporta y sale con 1; un error de uso o de entorno, con 2.
- **Pre-commit de la instancia** (plantilla `plugin/plantillas/pre-commit`, L17, L22): desde afuera de la sesión no hay `CLAUDE_PLUGIN_ROOT`, así que el plugin se busca primero en la copia de emergencia (`.claude/plugin/`) y después en `plugin_root` de `workspace.local.json`, que anota `/odd-ws:doctor --arreglar plugin-root` (ítem `plugin-root`: FALTA si falta, si la ruta ya no existe o si es otra copia del plugin). Bloquea con el arreglo exacto si python no corre o si no encuentra el plugin, y corre `reglas.py --test --raiz <instancia>`: la raíz va explícita porque un commit lanzado desde una sesión de otro proyecto trae su `CLAUDE_PROJECT_DIR`.

### Writers: el guard (`writer_guard.py`, L25–L28)

Los writers son agentes de la instancia (`.claude/agents/writer-<capa>.md`, D1). El guard corre en `PreToolUse` de `Bash`, `PowerShell`, `Edit` y `Write`, y solo actúa dentro de un writer.

- **Reconocimiento:** un `agent_type` que cumple completo `writer-[a-z0-9][a-z0-9-]*` (`capas.WRITER_RE`), sin mirar la lista de capas: un writer de una capa renombrada sigue guardado. Antes de importar nada, un prefiltro busca los bytes `writer-` en el stdin; sin ellos, sale en silencio y casi al costo de arrancar Python. Sin instancia, o con la config rota, calla (P3).
- **Qué bloquea** (exit 2, mensaje en bytes UTF-8): el git de escritura (también con `-C`, `-c`, alias, `--config-env`, comandos encadenados, shells anidados, `$(...)`, `iex` y `Start-Process`) y la escritura por shell sobre una zona (`>`, `tee`, `sed -i`, `perl -pi`, `Set-Content`, `cp`, `mv`, `rm`, `robocopy`, `python -c` y su heredoc, `[IO.File]::` y lo que `xargs` o `find -exec` ejecutan). Analiza el texto del comando, sin subprocesos.
- **Escapes** (L58, L64): el escape del shell antes de un blanco o de un salto de línea no corta la palabra, y antes de una comilla no la abre ni la cierra. Con `tool_name` `Bash` (o sin él) es la barra: `repo\ x`, `\⇥`, la continuación `\⏎` (también con CRLF), `\\` como barra literal, `\"` y `\'` como comillas literales y, entre comillas dobles, `\\` que vale `\`, `\"` que vale `"` y `\⏎` que desaparece. Con `PowerShell` es el backtick, y la barra no escapa nada (`"C:\dir\"` cierra en su última comilla): ``repo` x``, la continuación `` `⏎ ``, ``` `` ``` literal, y ``` `" ``` y ``` `' ``` como comillas literales, también ``` `" ``` entre comillas dobles; dentro de una palabra, `` `⏎ `` pega las dos partes (PowerShell deja un salto literal: se elige lo más estricto), y entre comillas dobles el acento grave antes de un blanco, de un salto o de otro acento grave vale ese carácter, también en el literal de `[IO.File]::` (L61); entre comillas simples queda literal (L66). El comando se analiza en dos pasadas: la primera sin leer ningún escape, como siempre (entre comillas dobles, `\"` vale `"` con cualquier herramienta), y, si el texto tiene un escape antes de un blanco, de un salto o de una comilla, la segunda leyendo en cada nivel el escape de su shell, con un solo cwd que sigue los `cd` (también los de `eval` e `iex`, que corren en el mismo shell). Gana la más estricta, así que los falsos positivos de la primera quedan, en la dirección segura (`echo \" ; echo " ; git commit"` bloquea, y el shell no corre git), y `destinos` da la unión, con la primera pasada primero. El costo es el de dos pasadas, no el de dos lecturas por nivel de anidamiento. En un shell anidado decide el que recibe el texto: `bash`, `sh`, `zsh`, `dash`, `ksh`, `eval` y el `!` de un alias de git leen con la barra; `powershell`, `pwsh` e `iex`, con el backtick; `cmd` y `Start-Process`, sin escape; `$( )` y los backticks heredan. No ve el `^` de `cmd` ni un escape antes de un carácter común (`g\it commit`, `` g`it commit ``; L65). Tampoco ve, previas:
  - `$'…'` con `\'` adentro (L69);
  - una sustitución con comillas anidadas dentro de comillas dobles (`echo "$(echo "it's")" ; git commit` pasa), ni el acento grave en esa misma posición (L72, L73);
  - las comillas internas que PowerShell 5.1 rompe al pasarle un argumento a un ejecutable nativo;
  - el comando que sale de la salida de una sustitución: `$(echo "git commit")` en posición de comando corre `git commit` (L75);
  - el pipe a un shell sin heredoc (`echo 'git commit' | bash`, `@'…'@ | iex`), que quedó fuera de U6f (L74, L81).
- **Envoltorios y bloques** (L67, L81–L83): el comando que decide es el que queda después de saltar lo que lo envuelve.
  - `timeout` salta sus opciones y la duración; `-s` y `-k` llevan valor, también `--signal` y `--kill-after` sin `=`.
  - `env` y `sudo` saltan las opciones que llevan valor:
    - en `env`, `-u` y `-C` (`--unset` y `--chdir`);
    - en `sudo`, `-a`, `-C`, `-c`, `-D`, `-g`, `-p`, `-R`, `-r`, `-T`, `-t`, `-U` y `-u`, y sus largas.
    - En un grupo de letras (`-nu root`), la primera que lleva valor se queda con el resto del grupo o, si es la última, con la palabra siguiente, como en `getopt`.
    - `env -S` no lleva valor acá, porque su valor es el comando: `env -S git commit -m y` bloquea.
  - **Bloques de PowerShell:** `%`, `?`, `.`, `ForEach-Object` (`foreach`), `Where-Object` (`where`), `Invoke-Command` (`icm`), `Start-Job` (`sajb`) y `Measure-Command` abren un bloque si, después de sus opciones, sigue un `{` suelto. Decide el primer comando de adentro. Sin `{`, el comando es el cmdlet: `% Remove-Item x` no escribe.
  - **Cierre del bloque:** en los niveles de PowerShell, el primer `}` suelto de profundidad 0 cierra los argumentos, así que `{ Copy-Item a.txt <zona> }` copia en la zona y no en `}`.
    - Las llaves de un `@{ … }`, o de un bloque pasado como argumento, se cuentan: `Set-Content -Value @{ a = 1 } -Path <zona>` sigue viendo la ruta (L83).
    - En Bash, `}` es un argumento.
  - **El `cd` que no mueve el cwd:**
    - Detrás de `sudo`, `env` o `timeout`, porque ejecutan un programa y `cd` es un builtin.
    - Dentro de un bloque de PowerShell, como antes de U6f. En PowerShell real, `%`, `Invoke-Command` y `Measure-Command` sí lo mueven (`Start-Job` no), pero `ForEach-Object { Push-Location …; …; Pop-Location }` lo devuelve, y el guard no sigue `Pop-Location`: seguir el `cd` dejaba pasar la escritura que venía después (L83).
  - **El pipe a un shell** se lee de dos formas, y gana la más estricta (L83):
    - **La regex de antes** (`HEREDOC_A_SHELL`): un `| shell` literal después del `<<`, en la misma línea física. Ve los compuestos (`{ cat <<'EOF'; } | bash`) y conserva sus falsos positivos: `||`, `;`, un comentario o una comilla.
    - **La tubería por segmento,** con el mismo `_comando`: el shell es el comando de su segmento, o de uno que le sigue en la misma tubería. Así cuentan `| sudo bash`, `| timeout 5 bash`, `|& bash`, `| (bash)` y `|\⏎bash`.
  - **No ve:**
    - la llave pegada (`%{git push}`, `{git`, `push}`), que aparece en 25 de 1 939 comandos reales, ninguno con una escritura;
    - el segundo bloque de `ForEach-Object -Begin { } -Process { }`;
    - `env -S 'git commit'`, con el comando entre comillas;
    - el cwd de `env -C` y de `sudo -D`, ni el cwd inicial de un job;
    - un `cd` que no es lo primero del bloque (`% { $a; cd x }`), ni `nice cd` ni `nohup cd`: mueven el cwd, como antes de U6f;
    - un compuesto entre el heredoc y un shell envuelto (`{ cat <<'EOF'; } | sudo bash`), ni el shell detrás de un compuesto o de una sustitución en el pipe (`| (cd . && bash)`, `| { cd .; bash; }`, `| $(which bash)`), que ya pasaban (L83);
    - una opción con valor antes del `{` (`% -ThrottleLimit 5 -Parallel { }`, `Invoke-Command -ComputerName . { }`, `Start-Job -Name x { }`);
    - las abreviaturas de las opciones largas (`timeout --sig KILL`, `sudo --us root`), ni `sudo -h host`.
- **Cuerpos** (L70–L74): el cuerpo de un heredoc de Bash y el de un here-string de PowerShell son texto, no comandos. Por eso un apóstrofo adentro no abre una comilla que se trague lo que sigue: `cat > f <<'EOF'⏎don't⏎EOF⏎git commit -m y` y `$m = @'⏎it's⏎'@⏎git commit -m y` bloquean.
  - **Cuándo corre:** los cuerpos los lee una tercera pasada, que corre si el texto tiene `<<` (no `<<<`) o un `@'` o `@"` al final de una línea. Lee los escapes como la segunda y, en cada nivel, entiende el cuerpo del shell de ese nivel.
  - **Heredoc, en los niveles de Bash:**
    - Si el delimitador va con `'`, `"` o `\`, el cuerpo es literal; si no, se analizan sus `$( )` y sus backticks.
    - Termina en la línea igual al delimitador, sin los tabs de `<<-` y con un `\r` final, que Git Bash acepta. Sin terminador, llega hasta el final.
    - Un `<<` dentro de un `(( ))` o un `$[ ]` sin cerrar es aritmética, no un heredoc.
      - Se cuentan fuera de comillas, con sus paréntesis y corchetes anidados (L77). `\$[` y `$$[` no abren aritmética.
      - Se cuentan por línea física, para que un error del contador no pase de su línea: `${x:-((}` o un `((` entre comillas anidadas (L72) cuentan (L78). Reinicia cualquier salto, también una continuación `\⏎`, un salto entre comillas o un cuerpo salteado, y un `))` cierra toda la aritmética, como el `rfind` por línea de U6g (L79).
      - Por eso un `<<` en la continuación de un `(( ))` de varias líneas se lee como heredoc, como antes de U6g. Lo mismo pasa con un `<<` que sigue a un `$(( ))` anidado dentro de un `(( ))` (`(( x = $((1)) << 2 ))`), porque ese `))` interno cierra todo (L80).
    - El `<<` corta la palabra que lo precede: `bash<<'EOF'` es `bash` con un heredoc, y `cat >x.sql<<'EOF'` escribe en `x.sql` (L77).
  - **Here-string, en los niveles de PowerShell:**
    - Abre con `@'` o `@"` seguido solo de blancos hasta el salto, y cierra con `'@` o `"@` en la columna 0.
    - Es una palabra, así que `iex @'…'@` lo analiza como código. En `@"…"@`, también sus `$( )`.
  - **El cuerpo que recibe un shell** (`bash <<'EOF'`, `cat <<'EOF' | bash`) sigue siendo código, como en el guard de comandos (`_base`, `HEREDOC_A_SHELL`).
    - Se analiza en un nivel aparte: si no es shell válido (`say "hi`), no ciega lo que sigue, y los otros cuerpos de la línea siguen siendo texto (L77).
    - Se analiza en su lugar, al pasar por su segmento: con el cwd que había en el heredoc, y sin que su `cd` cambie el del padre, que es otro proceso (L78).
    - Tiene su propio cupo (`MAX_SUBS`), así que no desplaza las sustituciones que vienen después (L78). Pasado ese cupo, y en el último nivel de anidamiento (`PROFUNDIDAD_MAX`), desde ese cuerpo el resto se lee en línea, como antes de U6g.
    - El pipe a un shell cuenta para los heredocs que están antes que él en la línea, o en su misma tubería (L82, L83).
  - **Costo:** lineal en la cantidad de `<<`, y el segmentador consulta el plazo en cada uno (L77).
    - El pipe a un shell se busca con la regex una vez por línea física (en U6g, eso bajó 10 000 `<<` con pipes de 41 s a 0,3 s), y la tubería se resuelve una vez por línea, recorriendo los segmentos de atrás hacia adelante (L82).
    - Previa: un `cd` relativo repetido dentro del shell del pipe (`(cat <<a | (cd x; bash)⏎git status⏎a⏎)` × 5000) tarda unos 7 s en `fa5562a` y después, cerca del plazo de 8 s (L83).
    - El comando de cada segmento se calcula una vez por línea: `x=1 ` o `sudo ` repetidos antes de miles de `<<` (L78).
  - **Solo suma bloqueos:** gana la pasada más estricta, y las dos primeras quedan como estaban, con sus falsos positivos (el cuerpo de un heredoc leído como comandos). `destinos` agrega al final lo que encuentra la tercera.
  - **No ve, previas:**
    - Dan falsos positivos, en la dirección segura (L76, A6, L83):
      - `HEREDOC_A_SHELL`, que toma como pipe un `|| bash` y también un `| bash` después de un `;`, de un comentario o dentro de una comilla;
      - un `\$(` en un cuerpo sin comillas;
      - la sintaxis de un shell leída en el otro.
    - En un heredoc sin comillas que va a un shell, el padre expande `$( )` aunque esté entre comillas simples: `bash <<EOF⏎echo '$(git push)'⏎EOF` (L78). También cuando el `| bash` es de otro heredoc de la misma línea, que se le atribuye a este (L79).
    - Un `$( )` se analiza con el cwd final de su nivel: `cd zona; y="$(echo x > f.sql)"; cd ..` (L78).
    - `git <<EOF commit -m y` y `bash<<<'git commit -m y'` (L78).
    - Los tres casos anteriores quedaron fuera de U6f (L81).
    - El `|` al final de la línea del heredoc: en `cat <<'EOF' |⏎…⏎EOF⏎bash`, el shell llega después del cuerpo (L82).
- **Zona:** un archivo dentro de un repo declarado o de uno de sus worktrees, con cualquier extensión, o un archivo que `clasificar` asigna a una capa (el taller). Es contención canónica, no nombre: cuentan las junctions y las mayúsculas. También es zona una ruta **ancestra** de un repo o de un worktree (L31): `rm -rf <padre de los repos>` bloquea, y escribir directo sobre una carpeta ancestra (`cp a.txt C:/`) también. Una carpeta es zona si está dentro de un repo o es ancestra de uno, o si coincide con la carpeta padre de un glob de `workshop` (con `**` al final, también lo que está debajo). Un comodín (`*`, `?`, `[`, las llaves `{a,b}` de bash, y el extglob `@(…)`, `+(…)` y `!(…)`, que el segmentador deja como un token terminado en `@`, `+` o `!`) corta la ruta en su primer segmento con comodín, y la carpeta conocida (o el cwd, si el comodín está en el primer segmento) decide como zona, además de la ruta literal.
- **Variables** (la resolución vive en `odd_ws.rutas`, interno, y la comparte el guard de comandos): `~`, `$VAR`, `${VAR}`, `$env:VAR` y `%VAR%` se expanden con el entorno del hook; `$PWD` es la carpeta del shell que sigue el parser (`cd`), no la del hook. Una variable desconocida corta la ruta en la última carpeta conocida, y esa carpeta decide como zona; si no queda ninguna, la ruta no cuenta. Una ruta que no queda absoluta después de normalizarla (relativa sin `cd` conocido, relativa a la unidad como `C:x`, o con `..` que se come la unidad) no se resuelve: nunca cae en el cwd del proceso del hook. En Windows, una ruta con una sola barra inicial (`\repo\x`) toma la unidad del cwd que sigue el parser; sin cwd conocido, no se resuelve.
- **Scratch:** `<temporales>/claude/`, con la carpeta de `os.tmpdir()` de Node (`TEMP`, `TMP` o `%SystemRoot%\temp` en Windows; `TMPDIR` o `/tmp` en el resto). Le gana a una zona.
- **Foto del primer toque** (`Edit`/`Write`, nunca bloquea): el contenido previo de cada archivo, una vez por agente, en `.claude/estado/writers/<sesión>/<agente>.fotos/` (`capas.ESTADO_WRITERS`, P5), o la marca `.nuevo` si no existía. Con una sesión nueva se podan las de más de 7 días. La compuerta de cierre cuenta las líneas reales contra esa foto.
- `destinos(comando, cwd, herramienta)` da los destinos de escritura que ve el mismo parser, sin decidir: la compuerta los deja en su sidecar, con la herramienta de cada `tool_use`.
- Falla abierta siempre; `--plazo` (8 s, timeout 10) es el límite del análisis, y al vencer calla.

### Writers: la compuerta de cierre (`writer_stop.py`, L25–L28, L35)

Corre en `SubagentStop` con el matcher `^writer-[a-z0-9][a-z0-9-]*$`, que es `capas.WRITER_RE` anclada (una prueba las ata), y solo actúa con un `agent_type` que la cumple completa. Sin instancia, o con la config rota, calla (P3). De un solo tiro, antes de dejar cerrar al writer:

- **Archivos tocados:** los `file_path` de los `tool_use` `Edit`, `Write` y `MultiEdit` del transcript del subagente, en orden y sin repetir (no del `git status`: el cwd del hook es el de la sesión).
- **Líneas reales:** contra la foto del primer toque que dejó el guard, con `git diff --no-index --numstat --ignore-cr-at-eol` (un cambio de LF a CRLF no infla); un archivo que no existía cuenta todo como agregado. Sin foto (lo escribió el shell, el guard no pudo guardarla, o pesa más de 8 MB) cae a `HEAD` y lo marca: «contra HEAD: sin foto». Solo lee: nunca toca el índice ni el árbol. Se miden **antes** que los chequeos: son unos pocos git por archivo, y un chequeo lento no las deja sin tiempo.
- **Chequeos de capa:** `verificar_archivo(ruta, config, limite)` del dispatcher sobre cada archivo; un hallazgo `bloqueo` bloquea y un `aviso` solo queda registrado. Un archivo cuyo chequeo revienta o se queda sin tiempo va a `errores_internos` y no tumba la compuerta.
- **Formato del cierre:** el último bloque `## Resultado` del último mensaje contra `PLANTILLA`, la constante de `writer_stop.py` que el generador de U6c inserta tal cual en la plantilla de writer. Los campos van en español: `estado` (ok, partial o blocked), `regla`, `intento`, `presupuesto`, `reales`, `arbol` y `verificacion`. Un `<placeholder>` sin completar no valida, y `arbol: sin cambios` con líneas reales medidas es incoherente.
- **Decisión:** con `stop_hook_active` en `false` y algo faltante, imprime `{"decision": "block", "reason": …}` (JSON en ASCII) con todo junto, las líneas reales y la plantilla: es el único aviso. Con `stop_hook_active` en `true`, o si se rompió una etapa entera, deja cerrar; al dejar cerrar borra las fotos del agente.
- **Sidecar**, siempre que los ids sean válidos: `.claude/estado/writers/<sesión>/<agente>.json` (`capas.ESTADO_WRITERS`, P5) con los archivos, el numstat, los bloqueos, los avisos, el formato, lo que declaró el writer, `errores_internos` y `escritos_por_bash` (los destinos de los `Bash` y `PowerShell` según `writer_guard.destinos`; es solo información y no cambia la decisión). Se escribe primero con lo que ya se sabe, por si algo revienta después.
- **Plazo (R-4):** `--plazo 50`, timeout 60. El límite llega a `verificar_archivo` (y por él al `ctx["limite"]` del módulo y a sus git) y a cada git de las líneas reales; al vencer, lo que falta se saltea y la decisión sale igual. Un módulo que ignora `ctx["limite"]` no se puede cortar desde adentro del proceso.

### Writers: la plantilla (`plantilla_writer.py`, L27, L36, L38)

Cada writer de la instancia, `.claude/agents/writer-<capa>.md`, sale de una plantilla única del plugin, `plugin/plantillas/writer.md`. La genera y regenera un solo generador (`plantilla_writer.generar`), y hoy lo llama `/odd-ws:doctor --arreglar writer-<capa>`; `/bootstrap` va a llamar al mismo.

- **Del plugin**, regenerado siempre: el frontmatter (`name`, `tools`, `skills: [criterios, capa-<capa>]` según R-8, `odd-ws-plantilla` y `odd-ws-hash`; sin `hooks` ni `model`) y el cuerpo genérico: el arranque, los límites del guard, el ciclo ODD, la única corrección y el cierre. El bloque `## Resultado` es la `PLANTILLA` de `writer_stop.py`, insertada al generar: la plantilla solo tiene el marcador `{{resultado}}`, nunca una copia.
- **De la instancia**: la `description`, en una sola línea (el generador la reescribe entre comillas dobles, así un `#` no se lee como comentario de YAML), y los bloques `<!-- instancia:identidad -->`, `<!-- instancia:limites -->` y `<!-- instancia:verificacion -->` (cada uno cerrado por `<!-- /instancia:<nombre> -->`). Regenerar los conserva; un bloque que el writer no tenía sale con el texto por defecto. Las convenciones del proyecto (sus IDs de reglas, el estilo del commit, `## Key Learnings`) van en `limites`.
- **Arranque:** las skills `criterios` y `capa-<capa>` llevan una línea suelta `CENTINELA <skill> <fecha>`. Si falta, el writer lee la skill del disco (desde la raíz de la instancia) y lo avisa en la primera línea de su último mensaje. Si tampoco está en el disco, cierra con `estado: blocked`.
- **Versión:** un entero, `odd-ws-plantilla: N`, en el frontmatter de la plantilla; el generador lo copia. Una prueba ata N al sha256 de la salida por defecto: cambiar la plantilla, la `PLANTILLA` o el generador sin subir N la pone en rojo. No sale de `plugin.json`, porque cada release marcaría atrasados todos los writers.
- **Huella:** `odd-ws-hash` es el sha256 de lo que es del plugin: sin BOM, con CRLF → LF (un checkout con `autocrlf` no es una edición), con los valores de `description` y del propio hash vacíos y con los bloques vacíos por dentro (las marcas cuentan).
- **Ítems del doctor**, uno por capa declarada (`writer-<capa>`): falta → AVISO, `--arreglar` lo crea; atrasado (la huella está intacta, pero regenerarlo lo cambiaría) → AVISO, `--arreglar` lo regenera; editado fuera de los bloques, escrito a mano (sin `odd-ws-plantilla` u `odd-ws-hash`), con bloques mal formados o ilegible → FALTA sin arreglo, y el generador nunca lo pisa; una capa cuyo nombre no cumple `capas.WRITER_RE` → AVISO sin arreglo (ni el guard ni la compuerta reconocerían ese writer). Sin instancia no hay ítems; con la config rota, un solo ítem `writers` en FALTA. El writer es opcional: el motor funciona sin él, y el primer toque solo sugiere delegar cuando existe.

### Guard de comandos (`guard_comandos.py`, L48, L49, L52, L53)

Corre en `PreToolUse` de `Bash` y `PowerShell` (`--plazo 8`, timeout 10) para la sesión principal y para todo subagente. Está reescrito en Python a partir del guard del proyecto de origen, que era de PowerShell (L48: medio segundo por comando, y su suite sumaba más de 3 minutos al pre-commit). Sin instancia, calla (P3).

- **Capa 1** (en cualquier repo; bloquea con exit 2 y el mensaje en bytes UTF-8): `git push --force` o `-f` (también dentro de un bloque como `-uf`, y aunque el mismo push lleve `--force-with-lease`), un refspec `+` sin un `--force-with-lease` sobre esa misma ref, `git reset --hard` y `git clean -f` (también abreviados: `--ha`, `--fo`), y los borrados recursivos fuera del scratch (`rm -r`, `Remove-Item -Recurse`, `rd /s`, también detrás de `xargs`, `eval`, `cmd /c`, `find -exec`, `ForEach-Object`, sustituciones y bloques). No lee la config: con la config rota sigue bloqueando (L49).
- **Texto, no ejecución:** se analiza el comando sin lo que va entre comillas, y el cuerpo de un heredoc es texto salvo que lo reciba un shell o un intérprete (`bash`, `sh`, `zsh`, `pwsh`, `powershell`, `python` o `node`). Un mensaje de commit que menciona `push --force` pasa.
- **Scratch:** `<temporales>/claude/`, con la carpeta de `os.tmpdir()` de Node (`comun.temporal`, la misma de `writer_guard`). Un borrado pasa solo si **todos** sus destinos son rutas absolutas literales estrictamente dentro del scratch, con los `..` resueltos y la ruta canónica (una junction hacia afuera bloquea). Una variable, una sustitución, una ruta relativa, una entrada por pipe o una comilla ambigua no se pueden probar, y bloquean. A diferencia del origen, solo vale el temporal del usuario actual, en su unidad.
- **Capa 2** (pregunta: `permissionDecision: ask` en un JSON limpio por stdout, exit 0): en un repo con `repos.<clave>.agent_readonly: true` en `workspace.config.json` (opt-in; un valor que no es booleano deja la config rota), git es de solo lectura por lista blanca: `status`, `log`, `diff`, `show`, `grep`, `ls-files`, `rev-parse`, `blame` y el resto de las lecturas, más `fetch` sin `<src>:<dst>`, `-u`, `-P`, `--prune-tags`, `--set-upstream` ni `--stdin`; `branch` y `tag` solo en sus formas de lista, `stash list|show`, `worktree list` y `worktree add` sin `-B`, `config` de lectura, `remote` solo o con `show` o `get-url`, y `reflog` y `notes` de lectura. Todo lo demás pregunta, con el motivo: también una opción que escribe o ejecuta (`--output`, `--ext-diff`, `--exec`, con sus prefijos), una opción global fuera de la lista (`-c`, `--config-env`, `--exec-path`), una variable `GIT_*` que equivale a `-c` o nombra un programa, comillas ambiguas, un comando en una variable o una sustitución y un alias hacia git. Lee dentro de `bash -c`, `eval`, `$( )`, el here-string que es argumento de un shell o de `iex` en el mismo segmento y un heredoc que recibe un shell. La Capa 1 va primero: un force push en un repo protegido bloquea igual.
- **Qué repo toca** (contención canónica, como `writer_guard`, no el nombre): una ruta toca un repo marcado si está dentro de él o de uno de sus worktrees (los del registro de git), o si lo contiene (L53). La ruta propia de la invocación (`-C`, que se encadena, `--git-dir`, `--work-tree`) decide sola si es absoluta; si no, decide el ambiente: el cwd del evento, solo si está dentro de un repo marcado, o una mención en cualquier parte del comando (el token, lo que sigue a cada `=` y a `-Opcion:`, cada pieza separada por coma, y el texto entre comillas leído como comandos; no un argumento entre comillas con espacios de un git, como un mensaje de commit, ni una barra que queda sola al quitar un cierre, como el `\;` de `find`). Variables, `~` y comodines se resuelven como en `writer_guard`, con `odd_ws.rutas`; una ruta relativa a la unidad (`C:x`) no es absoluta, y `\\?\C:\…` y `\\.\C:\…` valen como `C:\…`. Las variables `GIT_*` y las comillas ambiguas preguntan solo si el cwd o alguna mención tocan un repo marcado (la compuerta del origen); una ruta propia encadenada (`git -C <otra> -C ../repo commit`) decide aunque nada más la mencione. **Espacios escapados:** en `Bash`, una barra seguida de un espacio lo escapa (`con\ espacio`), así que se analizan las dos lecturas, unida y separada, y gana la más estricta; en `PowerShell`, donde la barra no escapa, solo la separada; dentro de comillas decide el shell que las recibe (`bash`, `sh`, `zsh`, `dash`, `wsl` y `eval` unen). Costo aceptado: un git de escritura en un comando que nombra una carpeta que contiene un repo marcado pregunta (`cd ~` con los repos bajo la carpeta del usuario, `git add .` desde una instancia que tiene los repos adentro). Lo que no ve: una ruta pegada en medio de un texto (`x/C:/repo`), un worktree o una junction creados en el mismo comando, un UNC (`\\localhost\C$\…`: no pasa por `realpath`), una URL `file:///…`, un `cd` sin argumento, `${env:VAR}`, `wsl … /mnt/c/…`, `FileSystem::…` y una ruta entre comillas con espacios que es argumento de un git (`-WorkingDirectory "…"`); tampoco lo ve el origen: `GIT_DIR` o `GIT_WORK_TREE` con un `-C` absoluto hacia otra carpeta, una variable asignada en el mismo comando como ruta de `-C`, `GIT_PAGER`, `Set-Item env:GIT_*`, `fetch --depth` y `@'…'@ | powershell -`.
- **Fallas:** sin repos marcados, una excepción o el plazo vencido callan (la Capa 1 falla abierta). Con algún repo marcado, preguntan con el motivo (R-5: un guard que lanza sale con 1, y eso es permitir); el plazo también corta el análisis de las menciones, que crece lineal con el comando (un script en línea de 1000 líneas tarda alrededor de un segundo). **Con la config rota, excepción a P3 (L49):** la Capa 1 sigue, y la Capa 2 pregunta ante todo git que no sea de lectura, en cualquier repo, con el error de la config en el motivo; una config que revienta al leerla cuenta como rota.

### Triaje (`triaje.py`, L43)

Antes de elegir la revisión, el triaje calcula sobre el diff las señales de riesgo y propone el modo. Las señales **solo escalan**: cada una sale positiva, negativa o inválida (el instrumento no pudo medir), y «rápido» sale únicamente con todas en negativo.

- **Uso:** `triaje.py --repo RUTA[#BASE] ... [--taller ARCHIVO ...] [--clon REPO ...] [--raiz INSTANCIA] [--json]`. La raíz por defecto es la de la sesión (P3). Sale con 0 cuando calcula (el modo va en la salida) y con 2 ante un error de uso o de entorno: sin instancia, config rota, repo inexistente, sin `origin/HEAD` o un archivo del taller que no existe.
- **Modos:** `sin-cambios`; `0` (solo docs: `.md`, `.txt`, `.rst`); `rapido`; `completo` (cualquier señal positiva o inválida).
- **Recolección:** el cambio es el working tree contra la base (por defecto, el merge-base con la rama de `origin/HEAD`, la regla del recibo, L5) más los archivos sin trackear. Nunca `fetch` ni `git add -N`, y el índice no se toca (`entorno_git`); un archivo con el stat sucio pero sin cambios se descarta. Un archivo del taller se lee entero como agregado, y su base es la contraparte de `workshop_baseline`. La capa sale de `config_loader.clasificar`. Lee UTF-16 con BOM; un archivo de más de 2 MB deja inválidas las señales del texto.
- **Señales:** `efecto` (los marcadores de la instancia, en el archivo entero, en la base y en lo actual: un efecto quitado o movido también escala); `dinero` (los nombres de la instancia y los tipos de la biblioteca de cada lenguaje, en las líneas agregadas y quitadas); `migracion` (seed o migration en la ruta, o el DDL y el DML de la biblioteca); `contrato` (la biblioteca de cada lenguaje: hoy, la firma y el JSON de los SP); `capas` (más de una capa, o un archivo sin capa); `consumidores` (abajo).
- **Consumidores** (el invariante): los objetos que define el cambio (hoy, los de T-SQL) se buscan con `git grep` en la rama de `origin/HEAD` de cada repo del config (o de los `--clon`), sin distinguir mayúsculas y por palabra entera; los commits locales sin publicar no cuentan. Es una **cota inferior** (`≥ N`, con la `COTA` de la instancia): lo que no está en esos repos no se ve. **Control positivo:** si no encuentra la definición del propio objeto, el conteo no vale y la señal queda inválida; lo mismo con un repo sin `origin/HEAD`, con más de 20 objetos, con un archivo demasiado grande o con un archivo cuyo lenguaje no tiene biblioteca. Un objeto nuevo no tiene consumidores previos, salvo en el taller sin contraparte, donde no hay cómo saberlo. Con 2 o más consumidores, la señal escala; una positiva nunca borra una inválida. La salida informa el hash de `origin/HEAD` de cada repo (el triaje no hace `fetch`).
- **Biblioteca por extensión:** `.sql` → `odd_ws.tsql`. Un lenguaje sin biblioteca no aporta tipos de dinero, DDL ni contrato, y la salida lo declara entre lo que el triaje no detecta.
- **Lo de la instancia**, en `.claude/reglas/senales.py` (opcional): `MARCADORES` (cada uno con `id`, `patron`, `ejemplo`, `fuente` y `ancla`, más su `descripcion`), `DINERO_NOMBRES` (palabras), `COTA` (texto) y `NO_DETECTABLE` (textos que se suman a la lista del motor). Al cargarlo, el motor valida cada marcador: `id` único, `patron` que compila, un `ejemplo` que su propio `patron` detecta y un `ancla` dentro de la línea `fuente` (`<ruta relativa a la raíz de la instancia>:<línea>`). Si un marcador no cumple, o el módulo no carga, `efecto` y `dinero` quedan inválidas y la salida dice por qué. Sin el módulo, `efecto` sale negativa con «0 marcadores en la instancia», y la salida lo declara entre lo que no detecta.

### Medir revisores (`rescatar.py`, `auditar_lecturas.py`, `puntuar.py`, L87)

Mide a los revisores de la instancia contra la revisión real de un líder (D6), con la skill `/odd-ws:eval-reviewers`, que lleva el protocolo y las reglas duras. El orquestador corre los scripts, nunca el revisor. Ningún script importa a otro: se pasan archivos JSON. El fixture ciego del origen (`preparar`, que saca la verdad de terreno del disco mientras corren los revisores) quedó en espera (U11c, riesgo 1), así que hoy el fixture se arma a mano.

- **Transcripciones (`odd_ws/transcripcion.py`):**
  - Es el lector único de los `.jsonl` de Claude Code, compartido con la compuerta de cierre (`writer_stop._usos`).
  - Saltea y cuenta la línea que no es JSON (la última, a medio escribir) o que no es un objeto, y reemplaza los bytes que no son UTF-8.
  - Le pone nombre a lo interno de Claude Code: la herramienta de handback y las de lectura. Ese formato no es una API estable; si cambia, se arregla en un solo lugar.
- **`rescatar.py --sesion <dir> --destino <dir> --corrida <nombre>=<agentId>…`:**
  - Lee `subagents/agent-<id>.jsonl` y su `.meta.json`.
  - Escribe, en LF:
    - `<nombre>.md`: el reporte del handback o, si no hay handback, el texto final;
    - `.prompt.txt`;
    - `.lecturas.json`, con `{agente, meta, lecturas, no_auditadas}`: los `Read`, `Grep` y `Glob`, y la cuenta de las demás herramientas;
    - `.comandos.json`, solo si hubo `Bash` o `PowerShell`, con el exit y la salida cortada a 2 000 caracteres.
  - Sale con 0; con 1 si alguna corrida no tiene reporte o no existe (esa corrida no escribe nada); y con 2 ante un error. Avisa por stderr las líneas salteadas.
- **`auditar_lecturas.py <lecturas.json | jsonl>… [--manifest] [--scratch] [--prohibida] [--permitida] [--ceguera-fisica] [--cwd] [--json] [--salida]`:**
  - Cruza cada `Read` con las rutas prohibidas (contaminado) y el alcance de cada `Grep` o `Glob` (exposición: «pudo ver», no «vio»).
  - Gana la regla más larga y, en empate, la prohibida.
  - Con `--scratch` también prohíbe la carpeta oculta, hermana del scratch (`capas.CARPETA_OCULTA`).
  - Con `--ceguera-fisica`, una exposición baja a info solo si todas sus reglas pasan por la carpeta de la verdad de terreno (`capas.CARPETA_VERDAD`). Un `Read` prohibido nunca baja.
  - Sin `--cwd`, las búsquedas parten de la raíz de la instancia (R-1). Sin raíz y sin `--cwd`, sale con 2.
  - Sale con 0 si está limpio, con 1 si hay exposición o contaminado, y con 2 ante un error.
- **`puntuar.py puntajes.json`**, con tres modos:
  - **Agregar:** `[--brazo <nombre>=<corrida>,…]…`.
    - El puntaje de una corrida es `ok + 0,5 × parcial`, y lo contrario, `reves + elogio`.
    - Por brazo da la media, la unión (el mejor veredicto por observación), las estables (ok en todas, con N ≥ 2), el k/N y los conflictos (una corrida acierta y otra va en contra).
    - Con dos brazos o más, da también la tabla pareada.
  - **Armar la ratificación:** `--plantilla-ratificacion <tabla.md|-> --clave <clave.json> [--semilla N]`. La tabla es ciega: sin nombres de corrida ni de versión, con las filas mezcladas.
  - **Aplicarla:** `--aplicar-ratificacion <tabla.md> <clave.json> --ratificado-por <quién> [--permitir-pendientes]`.
    - Reescribe `puntajes.json` con el sello y el detalle de los cambios.
    - Si quedan filas pendientes, sale con 1 y no escribe nada.
  - **La escala es fija:** `ok`, `parcial`, `reves`, `elogio`, `derivado`, `contaminado` y `-`. El campo `escala` del JSON solo se muestra.
  - **Disputadas:** las observaciones en `disputadas` (verdad de terreno que el código refuta) salen del conteo y de la tabla, pero quedan en el archivo.
  - **Salidas:** 0 ok, 1 filas pendientes y 2 error.
- **Diferencias con el origen:**
  - la línea rota se tolera, donde el origen salía con 2;
  - `.lecturas.json` guarda `no_auditadas`, que el origen perdía;
  - la raíz sale de la instancia;
  - los archivos van en LF.
  - `puntuar`:
    - no tiene ratificador por defecto: `--ratificado-por` es obligatorio (sale con 2) y los textos no nombran a nadie;
    - la ratificación conserva las celdas y las observaciones disputadas, que el origen perdía desde la primera.
- **No ve:**
  - junctions ni links, porque compara texto normalizado y no el disco;
  - lo que leyó un `Bash` o un `PowerShell`, que solo queda contado en `no_auditadas`;
  - que la clave de la ratificación sea de esos puntajes, ni que la ratificación se haya hecho a ciegas.

### Conocimiento (`conocimiento.py`, L90)

Diagnostica la salud del conocimiento de la instancia con la skill `/odd-ws:conocimiento`. Es de solo lectura, y su nombre es distinto del doctor de la máquina (R-7).

- **Config: sección opcional `knowledge`** en `workspace.config.json`.
  - La lee y la valida solo `config_loader.conocimiento(raiz)`. `cargar()` no la conoce: un error en la config de los documentos nunca deja la config «rota» para los guards.
  - Sus claves:
    - `docs`: la carpeta de los docs de dominio, sus `*.md` sin recursión;
    - `index`: el índice, por defecto `CLAUDE.md`;
    - `index_max_lines`: el tope del índice, por defecto 200;
    - `scan`: globs de `.md` extra para links y anclas, con la semántica de R-3;
    - `quantities`: los sustantivos de las cifras;
    - `claims`: el archivo de afirmaciones, por defecto `<docs>/_claims.json`.
  - Son rutas relativas con `/`. Una clave desconocida o un tipo inválido hacen que `conocimiento.py` salga con 2 y nombre la clave.
- **Nivel 1**, `conocimiento.py [--v]`. Los hallazgos son FAIL o warn, más una worklist que no cuenta como deuda. Sale con 0 si está sano, con 1 si hay algún FAIL, con 3 si solo hay deuda y con 2 ante un error.
  - **Docs indexados:** cada doc de `docs` aparece nombrado en el índice. Es un warn por doc.
  - **Links:** un link `.md` cuyo destino no existe es FAIL. Se revisan el índice, los docs y el `scan`, y se ignoran los esquemas (`https:` y `mailto:`).
  - **Anclas:** una `#ancla` que no existe en el destino es warn. Se compara contra el slug de GitHub y contra `<a id|name>`.
  - **Cifras en headings:** un heading con `<n> <sustantivo>` que tiene links entrantes es warn, porque el ancla cambia cuando cambia la cifra.
  - **Tope del índice:** pasar de `index_max_lines` es warn.
  - **Frescura:** el frontmatter `verificado:` (fecha ISO) y `volatilidad:` (alta 30 días, media 90, baja nunca) dan un warn cuando el doc está vencido.
  - **Sin commitear:** `git status --porcelain -uall`, acotado a los archivos de conocimiento, separa conflictos, borrados, modificados y nuevos.
  - **Sin `docs`**, los chequeos que la necesitan dan «no aplica», nunca un FAIL.
  - **Cobertura de afirmaciones** (U12b):
    - Busca los docs que afirman cifras del vocabulario sin una afirmación que los cite en su `doc`.
    - Resta las cifras declaradas en `cobertura_triada`, por aparición.
    - Es worklist (hasta 5 docs); una cifra nueva en un doc ya triado y los problemas de la triada son warn.
- **Nivel 2**, `--claims` (U12b, L92): **veredictos** sobre afirmaciones verificables del código, con el motor en `odd_ws/afirmaciones.py`.
  - **El archivo** es JSON (por defecto `<docs>/_claims.json`) y rechaza las claves duplicadas. Lleva `version: 1`, `claims`, `rechazados` y `cobertura_triada`.
    - Cada afirmación tiene `id`, `naturaleza` (invariante o inventario), `ejecutor` (`repo` o `sql`) y `expected`.
    - Las de `repo` suman `repo`, que es una **clave** de `repos` de la config; `ref`, por defecto `origin/HEAD`; y `comando`, con `{ref}`.
  - **Lista blanca:**
    - git solo con `ls-tree`, `show`, `log`, `cat-file`, `rev-parse`, `diff-tree` y `grep`, siempre como primer tramo de cada comando;
    - después, por `|`, solo los filtros `grep`, `wc`, `sort`, `uniq`, `head`, `tail`, `cut` y `tr`.
    - Fuera de comillas simples se rechazan `$`, el backtick y `\`.
    - Fuera de toda comilla se rechazan `#`, `<`, `>`, `&`, `{`, `}`, `*`, `?`, `[`, `]` y `~`. Por eso `{ref}~1` va entre comillas: `'{ref}~1'`.
    - El NUL se rechaza en cualquier parte.
    - Se rechazan los flags que escriben, leen el disco o ejecutan:
      - `sort -o` y `-T`;
      - `uniq` con dos operandos;
      - en git, `--output`, `-O`, `--ext-diff`, `--textconv`, `--filters`, `--no-index` y `--show-signature`, con las opciones largas comparadas por prefijo;
      - un formato que cumpla `%[-+ ]?G` (`afirmaciones.REGEX_DE_FIRMAS`).
    - El `ref` se valida con una regex, así que no puede ser una opción ni meter shell.
  - **Ejecución: un script de bash generado, con cada token citado (L93-L95):**
    - Cada comando se parte en tramos, y cada tramo en un argv con `shlex` en modo POSIX. Se valida ese argv.
    - El motor **genera** un script con `shlex.quote` en cada token de ese argv. Dentro de comillas simples, bash no expande nada, y entre procesos MSYS los argumentos pasan sin reinterpretarse: cada programa recibe exactamente lo validado.
    - **No se ejecuta sin shell.** Un filtro MSYS lanzado desde un proceso nativo reinterpreta su línea de comandos: expande llaves, globs y `~`, quita las `\` y toma la `'` como comilla (medido, L94).
    - El script va en un archivo temporal. Lo corre el `bash` real de Git for Windows (`usr\bin\bash.exe`, ubicado a partir de `git`, sin depender del PATH; `/bin/bash` en POSIX), que recibe **solo la ruta del archivo**, nunca el texto por `-c`. Después se borra.
    - El script entra al repo con `cd --`. El stdin del primer tramo es `/dev/null`, y cada tramo va con `/usr/bin/timeout -k 2 <plazo>`. Si algún tramo sale con 124 o 137 (lo mira con `PIPESTATUS`), el plazo se agotó.
    - git va por su ruta absoluta. Justo después del verbo se le insertan `--no-textconv`, `--no-ext-diff` y `--no-show-signature` en `show` y `log`, y las dos primeras en `diff-tree`.
    - Los filtros van por su ruta MSYS absoluta (`/usr/bin/<filtro>`), nunca por el PATH: en Windows, `sort` resolvería a otro programa.
    - **El respaldo en Python** mata el árbol (`taskkill /T /F` en Windows, `os.killpg` en POSIX) cuando pasan el plazo más 10 s. Lo hace con archivos temporales en lugar de pipes, y alcanza a los descendientes nativos de `git.exe`, que `timeout` no mata.
    - El `rev-parse --verify` previo y la antigüedad del fetch corren nativos, con la misma maquinaria de archivos y del árbol.
    - **La semántica es la de bash:** un diferencial **de ejecución** sobre 1 170 comandos aceptados da lo mismo que bash leyendo un script. El origen corría `bash -c "<texto>"` desde Python y sufría la misma reinterpretación: reducía `\\` a `\`.
    - El entorno parte de `comun.entorno_git` y quita `BASH_*`, `ENV`, `SHELLOPTS`, `GREP_OPTIONS`, `POSIXLY_CORRECT` y todo `GIT_*` ajeno.
    - Por `GIT_CONFIG_COUNT`, que gana a la config local del repo medido, fuerza:
      - `core.fsmonitor=false` y `log.showSignature=false`;
      - `gpg.program`, `gpg.openpgp.program`, `gpg.ssh.program` y `gpg.x509.program` apuntando a una ruta inexistente. Falla cerrado: la afirmación queda `err`.
    - Suma `GIT_NO_LAZY_FETCH=1`, porque en un clon parcial `git show` haría fetch por red y podría ejecutar un remoto `ext::`.
    - Cualquier stderr, una salida vacía o un plazo agotado es error. Un comando que no se puede lanzar es `err` de esa afirmación, y la corrida sigue.
  - **Veredictos:** `ok`, `+` (creció; solo los inventarios, y no es un hallazgo), `ROJO` (drift) y `err`.
    - Una afirmación con un FAIL del lint no se ejecuta.
    - Las SQL salen «sin juicio» (U12c, en espera), con la línea `TIER 2 ABIERTO`, y no cuentan en el código de salida.
    - Por cada repo usado se informa la antigüedad de su último fetch: el motor no hace fetch.
  - **Salidas:** 0 si está todo verde (crecidos y SQL abiertas incluidos); 1 si hay algún `ROJO`, algún `err`, un FAIL del lint o un archivo que no carga; 2 si la config está rota (por ejemplo, falta la ruta local de un repo).
  - **Diferencias con el origen:**
    - JSON en lugar de YAML;
    - `repo` como clave;
    - el `ref` validado;
    - una lista blanca **más estricta en todo**: sobre 215 107 comandos, el port no acepta ninguno que el origen rechace y rechaza 13 333 que el origen aceptaba;
    - un script con cada token citado, config forzada, sin fetch perezoso y un plazo que mata el árbol de procesos.
  - **No ve:**
    - un filtro que, fuera del primer tramo, lee un archivo como operando (solo lectura);
    - `git grep -f`;
    - otros ejecutables de la config local, más allá de los medidos y cerrados: `textconv`, `smudge`, `diff.external`, los cuatro programas de firma, `core.fsmonitor` y el fetch perezoso;
    - un nieto MSYS nacido por fork/exec bajo un `git.exe` nativo sobrevive al plazo: `timeout` mata solo al hijo directo. Desde un archivo de afirmaciones no se alcanza, porque haría falta un fetch perezoso y `GIT_NO_LAZY_FETCH` está forzado (L96);
    - una capa mal declarada en la config, que también da 2 en `--claims`.
- **Nivel 3**, `--cruce`: propone **candidatos**, no hallazgos, y sale siempre con 0. No usa git, red ni repos.
  - Busca entidades entre backticks que aparecen en 6 docs o más.
  - Busca cifras del mismo sustantivo (de `quantities`) que difieren entre docs, siempre con la frase que las rodea.
  - Lee primero los docs con `rol: resumen`.
- **Diferencias con el origen:**
  - la config reemplaza las constantes de rutas;
  - el vocabulario de cifras viene vacío por defecto;
  - el rol sale solo del frontmatter;
  - un link con esquema ya no es FAIL;
  - lo nuevo se lista archivo por archivo (`-uall`), no por carpeta;
  - fuera de un repo git, «sin commitear» da «no aplica».
- **No ve:**
  - links por referencia o entre `<…>`;
  - un `#ancla` dentro del mismo doc;
  - headings dentro de bloques de código, que cuentan como headings;
  - frontmatter YAML anidado, porque lo lee por líneas `clave: valor`;
  - subcarpetas de `docs`;
  - plurales del vocabulario de cifras.
- **No viajaron:** los chequeos de proceso del origen (compromisos, drenaje de preguntas, estado de los tickets y candidatos atrapados) y el rol de evidencia por nombre de doc.

### Bootstrap (`bootstrap.py`, T8)

Genera una instancia desde una spec, que arma la skill `/odd-ws:bootstrap` con una entrevista (B8). **Nunca pisa un archivo del usuario.**

- **La spec** es JSON: `{"spec_version": 1, "config": <workspace.config.json exacto>, "local": <workspace.local.json sin plugin_root>, …}`. Hay un ejemplo en `plugin/plantillas/bootstrap.ejemplo.json`.
  - No hay un segundo esquema: las capas, los repos y `knowledge` salen de `config`.
  - Cada generador registra las claves de nivel superior que suma. Una clave desconocida, otra versión o `local.plugin_root` (que anota el doctor) rechazan la spec.
- **Antes de escribir**, valida en una copia dentro de un temporal, con `config_loader.cargar` y `config_loader.conocimiento`, **la combinación final**: lo que ya está en la instancia, más lo que se crearía. Si da `ConfigRota`, no se escribe nada, ni siquiera la raíz.
  - En la spec, `NaN` e `Infinity` se rechazan, y las rutas de los repos en `local` tienen que ser absolutas.
- **La raíz:** sin `--raiz`, es la instancia que haya arriba del cwd (`config_loader.encontrar_raiz`) o, si no hay ninguna, el cwd. Así nunca se crea una instancia anidada.
  - Un `--raiz` dentro de otra instancia sale con 2.
  - También sale con 2 un `--raiz` con un componente que termina en punto o espacio, que Windows recortaría.
- **El plan** (`planificar`) junta las acciones `(ruta, contenido[, permisos])` y las `AccionDeGit` de los generadores registrados (`registrar_generador`), y marca cada archivo como `crear` o `ya_existe`. Los permisos son un entero entre 0 y `0o777`, y tienen que incluir la escritura del dueño (`0o200`): en Windows, sin ella, el `chmod` deja el archivo de solo lectura, el enlace duro comparte el atributo y el temporal ya no se puede borrar (L14, A-3). Antes de escribir nada, rechaza:
  - las rutas absolutas;
  - las que tienen `..`, `\` o `:`;
  - los segmentos vacíos o que terminan en punto o espacio;
  - las rutas repetidas;
  - un choque entre archivo y carpeta;
  - un ancestro que es archivo;
  - un enlace que sale de la raíz;
  - los nombres reservados de Windows (`CON`, `PRN`, `AUX`, `NUL`, `CONIN$`, `CONOUT$`, `COM1-9` y `LPT1-9`, con o sin extensión, también como carpeta) y los caracteres `<>:"|?*` y de control.
- **La aplicación** (`aplicar`) nunca escribe directo al destino (L5, T8):
  - Escribe el contenido completo en un temporal hermano oculto y lo publica con `os.link(temporal, destino)`. Un enlace duro no reemplaza nada: un archivo existente, un symlink roto o una carpeta en el destino nunca se siguen ni se pisan, y quedan como «ya existía». En Windows, `open(…, "xb")` sí seguiría un symlink roto.
  - El nombre del temporal nunca reutiliza algo que ya exista, ni siquiera un symlink roto. Prueba hasta 5 nombres y, si ninguno está libre, sale con 2.
  - Después borra siempre el temporal, así que una escritura que falla (por ejemplo, un disco lleno) no deja un archivo a medias.
  - Si el temporal no se puede borrar (por ejemplo, lo tiene abierto un antivirus), el informe dice `no se pudo borrar <temporal>: borralo a mano (es una copia de <destino>)`, y la salida sigue en 0. Es un enlace duro del archivo publicado, y el de `workspace.local.json` no lo cubre el `.gitignore`: hay que borrarlo antes de commitear.
  - Antes de crear carpetas, de escribir y de cada publicación, vuelve a revisar que ningún ancestro sea un enlace que salga de la raíz, y que la raíz resuelva igual que al planificar.
  - Con permisos, hace `chmod` sobre el temporal antes del `link`, así que el archivo nunca aparece sin ellos.
  - Nunca modifica, trunca ni borra un archivo.
  - **Límite:** en FAT o exFAT, sin enlaces duros, sale con 2 sin escribir nada, en lugar de degradar a una escritura insegura.
  - **No ve:** que otro proceso mueva afuera una carpeta del usuario, con el temporal adentro, y la reemplace por una junction justo antes del `link` (L10, R2). Es inherente a trabajar con rutas en lugar de handles, y exige un proceso que modifique la instancia a mitad de la corrida. Lo mismo vale para el `chmod`, que también va por ruta (L14, A-7).
- **Las acciones de git** (`AccionDeGit`, B5) son dos: `init` y `hooks_path`. Corren después de los archivos, y solo si no falló ninguno.
  - **Solo si hace falta:**
    - `git init` corre únicamente si la raíz no está en ningún repo. No se anida un repo.
    - `core.hooksPath` se configura solo si la raíz es el toplevel de su repo, porque un valor relativo se interpreta desde ahí, y si no tiene valor propio.
    - Un valor ajeno se informa (`core.hooksPath = <valor>: no se tocó; el pre-commit no va a correr`) y no se toca. También cuenta como propio un valor vacío (`= (vacío)`) o uno que llega por un `include.path`.
    - **Sin valor no siempre es «hace falta»** (L14, B-1). Configurarlo apagaría lo que corre hoy, así que tampoco se toca en dos casos:
      - si la carpeta de hooks que da `git rev-parse --git-path hooks` tiene algún archivo que no sea `.sample` (husky, pre-commit o lefthook): `core.hooksPath: no se tocó; hay hooks propios en <carpeta> (<nombres>), que dejarían de correr`. Esa carpeta es la efectiva, así que respeta también un `hooksPath` global;
      - si la raíz es un worktree enlazado (`--git-dir` distinto de `--git-common-dir`, comparados con `realpath`), porque ahí `--local` escribe la config compartida: `core.hooksPath: no se tocó; la raíz es un worktree enlazado y --local cambiaría la config de todos sus checkouts`.
    - La regla es una sola función pura, `odd_ws.comun.decidir_hooks(raiz, salida)`, que recibe la salida de `rev-parse --git-path hooks --git-dir --git-common-dir`. La usan bootstrap y el arreglo del doctor, y cada uno corre git con su propio ejecutor. Si git no da las tres rutas, o la carpeta no se puede leer, no se toca.
  - **Solo la config del repo:** los comandos son `git -C <raíz> …`, con `config --local` para escribir y `config --local --includes --get` para leer. Leer sin `--local` mezclaría el valor global y el del sistema. Nunca usa `--global` ni `--system`.
  - **Decide al aplicar:** vuelve a mirar el estado del repo justo antes de cada acción, sin copiar la decisión del plan, y antes de cada una compara la raíz real con la del plan.
  - Si `rev-parse` falla pero hay un `.git` en algún ancestro (por ejemplo, con «dubious ownership»), no hace `git init` ni toca el `hooksPath`.
  - **Salida 0 y aviso** si git no está, si falla un comando o si se pasa el plazo de 60 s. El informe lleva una línea por acción, antes del resumen.
- **El `.gitignore`** nunca se modifica.
  - Se lee tolerando el BOM. Una línea cuenta como presente si coincide, o si la cubre una carpeta ancestro (`.claude/` cubre `.claude/estado/`).
  - Igual que en git, una barra final solo cubre carpetas: `workspace.local.json/` no ignora el archivo. Esto se verificó contra `git check-ignore`.
  - Los globs no se interpretan, así que el informe puede marcar de más una línea que falta.
  - El informe dice `falta en .gitignore: <línea>` por cada línea que falta.
  - Si no se puede leer (por ejemplo, porque es una carpeta), el informe lo dice y lista qué revisar a mano.
- **La CLI:** `bootstrap.py --spec <ruta> [--raiz <carpeta>] [--ensayo]`.
  - `--ensayo` muestra el plan (`crearía …`, `ya existe …` y lo que haría git, como `git init: se haría (la raíz no está en ningún repo)`) sin escribir nada. Solo ejecuta git de lectura.
  - En Windows, debajo de un archivo creado con bit de ejecución, el informe agrega `al commitear, marcalo ejecutable: git add --chmod=+x <ruta>`, porque git ahí no registra el bit.
  - Sale con 0 aunque haya archivos que ya existían, y con 2 ante una spec, una config o un plan inválidos, un error de aplicación (con el informe parcial de lo creado) o un error interno.
- **Generadores.** Cada uno es un módulo con `CLAVES`, un `validar(spec)` opcional y `generar(spec)`, y B8 lo registra con `registrar_generador`.
  - **Config** (`bootstrap.py`): `workspace.config.json`, `workspace.local.json` y `.gitignore`, en UTF-8, LF y sin BOM. `workspace.local.json` se crea con el `plugin_root` del plugin que está corriendo; si ya existía, lo cubre `--arreglar plugin-root` del doctor.
  - **Instalación** (`bootstrap_instalacion.py`, sin claves): `.githooks/pre-commit` desde `plantillas/pre-commit`, con 0755; `.claude/settings.json` con `enabledPlugins`, y las acciones `git init` y `core.hooksPath = .githooks`. Lo generado pasa los ítems `plugin-root`, `instancia-hooks` e `instancia-plugin` del doctor.
  - **Agentes y skills** (`bootstrap_agentes.py`). Por cada capa con un nombre válido, genera:
    - `writer-<capa>`, con `plantilla_writer.generar`, cuya salida no cambió;
    - `revisor-<capa>`, desde `plantillas/revisor.md`, con el mismo mecanismo de versión, huella y bloques `<!-- instancia:... -->`, que ahora es `plantilla_writer.armar` y recibe la plantilla. El revisor es de solo lectura y reporta con severidad y `ruta:línea`;
    - `capa-<capa>`, con `CENTINELA` y el bloque no-negociables, sin `paths:` ni `disable-model-invocation`.

    Además genera, una sola vez, `criterios`: el Paso 0, el alcance mínimo, la evidencia y el contrato de reporte. Lo generado pasa los ítems `writer-<capa>` y `agentes-skills` del doctor.
  - **Reglas vacías** (`bootstrap_reglas.py`, principio 2).
    - Genera la matriz, solo con el encabezado de `matriz.ENCABEZADO`, y `evidencia.md`.
    - Por cada capa, un stub `verificar_<capa>.py` (`REGLAS = ()`, y `verificar(ctx)` devuelve `[]`) y su suite, que cumple el contrato P1 y pasa `reglas.py --test <capa>`.
    - `validar` exige el `rule_prefix` de cada capa.
  - **Textos** (`bootstrap_textos.py`, clave `proyecto.nombre`):
    - un `CLAUDE.md` liviano (116 líneas, por debajo del tope de 200), solo con metodología genérica: cómo se apilan los contextos, el ciclo del ticket, las reglas de los repos del equipo, la perilla de profundidad, las tres preguntas ante un efecto externo, el alcance mínimo, el conocimiento, los tickets y las skills del plugin;
    - la plantilla del ticket en `tickets/_plantilla/CLAUDE.md`, con los dos relojes (Estado y Conocimiento), alcance y no-goals, Paso 0, bitácora y candidatos a graduar. No lleva tracker.

### Biblioteca T-SQL (`odd_ws.tsql`)

Primitivas para el módulo de una capa SQL; la superficie la fija `odd_ws.PUBLICO["tsql"]`.

- **Texto:** `depurar(texto, literales=False)` pasa los comentarios (y, con `literales`, el contenido de los literales) a espacios, con el mismo largo y los mismos saltos de línea; `linea_de(texto, pos)`; `bloques_catch(depurado)` da `[(ini, fin, linea_ini, linea_fin)]` (un bloque sin cerrar llega hasta el final); `argumentos(texto, inicio)` da los argumentos a profundidad 0 de la sentencia que sigue.
- **AST:** `analizar(ctx)` corre ScriptDom (`scriptdom.ps1`, PowerShell) y devuelve `(análisis, motivo)`, sin escribir en el `ctx`. `motivo` es `None`, `sin_helper` (no hay PowerShell o DLL, el helper falló y queda roto para el resto del proceso, o no pudo leer ese archivo) o `sin_tiempo` (no queda el mínimo antes de `limite`, o el helper venció). El resultado se cachea por ruta y contenido, **también el vencimiento**: otra regla que pide el mismo archivo no relanza el helper, porque el plazo del hook alcanza para un solo intento. Un `limite` ya vencido no se cachea. `precalcular(ctxs)` analiza un lote en una sola invocación; si vence, todo el lote queda en `sin_tiempo`.
- **Chequeos genéricos:** `sql_dinamico(ctx)` (EXEC de una cadena armada con `+`, o `sp_executesql` con la sentencia concatenada) y `comentarios_agregados(ctx)` dan `[(línea, fragmento)]` sobre las líneas agregadas; sin análisis devuelven `[]`, y la instancia decide si avisa según el `motivo`. Dónde aplican es política de la instancia. `problemas_de_bytes(datos, bom=False, fin="crlf")` da la lista de problemas de BOM, fin de línea y UTF-8.
- **Normalizador** (CLI, fuera de la API): `normalizar_sql.py --check | --fix ARCHIVO... [--tabs] [--fin crlf|lf]`.
- **Señales del triaje** (internas, fuera de `PUBLICO`; su único consumidor es el triaje, L43): `TIPOS_DINERO`; `es_migracion(agregadas, actual)` (DDL de tablas, columnas, índices o `sp_rename`, o DML sin objeto, sobre el texto crudo de las líneas agregadas); `parametros_de_sp`, `json_de_sp` y `cambios_de_contrato(base, actual)` (firma de cada SP, paths y alias del JSON, y los SP que desaparecen); y `objetos(actual, base)`, con la ERE de definición que se le pasa a `git grep -E -i`. Las firmas, el JSON y los objetos se leen sobre `depurar`, así que un `--` dentro de un literal no corta la firma y un encabezado comentado no crea un objeto.

## 5. Gobernanza, RDD y mejora continua

**D2 — Gobernanza.** Lo único que cambia entre un proyecto estricto, uno legacy y uno nuevo es **de dónde sale el molde**. Una perilla por capa, `layers.<capa>.mold_source`:

- `repo`: todo hermano vigente es molde, salvo los de la lista `no_molde`.
- `propio`: ningún hermano es molde, salvo los de la lista `molde`; el resto se lee solo como contrato, y los moldes sintéticos viven en la instancia.
- `greenfield` no es un modo: es `propio` sin corpus.
- La perilla **no** decide qué bloquea. Qué bloquea lo decide la calibración: una regla bloquea solo si atrapa su defecto sembrado **y** da 0 aciertos en el corpus.
- Se descartó el nombre «boy scout»: invita a limpiar alrededor, lo contrario del alcance mínimo. Para un modelo, los nombres son instrucciones.

**D3 — RDD propio desde el día 1; el nativo de gentle-ai, apagado.** El reviewer nativo corre sin herramientas ni `CLAUDE.md`: no puede abrir el hermano vigente ni contar consumidores. El propio sí puede, desde el primer minuto. El triaje del día 1 usa **señales universales** (migraciones y datos, seguridad, contratos consumidos, concurrencia, entrega, recursos con 2+ consumidores, dinero, efectos hacia otros sistemas); las del dominio se agregan a medida que se ganan. `/doctor` informa que el RDD nativo viene encendido por defecto y propone apagarlo, pero nunca lo cambia solo.

**D6 — Mejora continua.** El sistema no se reescribe a partir de sus propios resultados, porque eso sería autocertificarse. Las entradas vienen de afuera: una observación propia o del líder, o un incidente. El circuito es el de cierre de ticket (candidatos a graduar → fila de la matriz con origen → validación → `eval-reviewers` contra revisiones reales), más tres piezas:

1. Al cerrar, cada aprendizaje se clasifica como **dominio** (va a la instancia) o **motor** (va al plugin, después del barrido).
2. Lo que aparece igual en **dos** instancias sube a los defaults del plugin, reescrito sin el vocabulario de ninguna empresa.
3. Las **disputas** de bloqueos quedan en `.claude/registro/`; una regla disputada vuelve a `aviso` hasta que se arregle su chequeo.

## 6. Fuera del plugin

- **Capa 0, `/odd-ws:doctor`** (`plugin/scripts/doctor.py`): solo lee por defecto y arregla de a un ítem con `--arreglar <id>`. La v1 revisa los hooks y la lista negra del clon (cierra el riesgo B2b), Python por comportamiento y por latencia (S1.6), las credenciales de git, Claude Code ≥ 2.1.284, el marketplace, gentle-ai ≥ 4.2.0 con su RDD y su telemetría, engram ≥ 3.5.0 y `jq`. En una instancia suma `plugin-root`, los tres ítems de la instancia (T8 B7), un `writer-<capa>` por capa y los dos ítems de sus agentes (U9, L85), detallados abajo. Quedaron afuera: `diff.autoRefreshIndex`, que el motor fija por proceso y viaja con él; `core.longpaths`, sin incidente que lo justifique; y MCPs, secretos, proxy corporativo, perfil de modelos y exportación de memoria, que entran cuando un caso real los pida.
  - **Ítems de la instancia (T8 B7):**
    - **`config`:** corre `config_loader.cargar(raiz)`. Si falla, es FALTA con el motivo, por ejemplo la ruta de un repo que falta en `workspace.local.json`, que antes dejaba los hooks mudos sin que el doctor lo viera.
    - **`instancia-hooks`:** `core.hooksPath` apunta a `.githooks` y existe `.githooks/pre-commit`. Sin valor, `--arreglar` lo configura, salvo que `decidir_hooks` diga que no (hooks propios o un worktree enlazado). En ese caso, el ítem queda en falta, sin arreglo y con el motivo.
      - Si no tiene valor, `--arreglar` lo configura.
      - Si tiene otro valor, es FALTA sin arreglo.
      - Si la raíz no es la raíz de un repo git, es NO APLICA.
    - **`instancia-plugin`:** `.claude/settings.json` habilita `odd-ws@odd-workspace-template` en `enabledPlugins`.
      - Si no, es AVISO, sin arreglo, porque `settings.json` es del usuario. Sale aunque el plugin esté habilitado a nivel de usuario.
      - Un JSON roto es FALTA.
  - **`agentes-skills`:** cada skill que un agente de `.claude/agents/*.md` precarga con `skills:` (leído con `verificar_capa.skills_del_frontmatter`) existe en la instancia o en `~/.claude/skills/`, y Claude Code la precarga de verdad. Una que falta, o que lleva `paths:` (spike (e) del origen, con control) o `disable-model-invocation: true` (documentado), se saltea en silencio: FALTA. Si a `criterios` o a `capa-<capa>` les falta su línea suelta `CENTINELA <skill>`, es AVISO: el writer la vuelve a leer del disco y lo avisa en cada corrida. Las skills de un plugin (`plugin:skill`) no se verifican. Sin arreglo automático.
  - **`agentes-hooks`:** un agente que declara `hooks:` en el frontmatter es AVISO. En un agente de proyecto, Claude Code los saltea en silencio mientras la carpeta no aceptó el diálogo de confianza, y siempre en una sesión `-p` (documentado). Van en el `settings.json` de la instancia, filtrando por `agent_type`. Sin arreglo automático.
  - **No ve:** una skill cuyo `name` difiere de su carpeta (sale como faltante), la precedencia entre una skill del usuario y otra del proyecto con el mismo nombre, y los agentes en subcarpetas de `.claude/agents/`. Del chequeo de salud del origen quedó solo esto: el resto era paridad de `settings.json` entre carpetas de ticket y cableado de hooks, que el plugin resuelve con su `hooks.json`.
- **Perfil de modelos:** `rol → (alias, effort)`, nunca IDs; umbral del modo ahorro; medición de costo real (los tokens que se reportan de un subagente son su contexto final, no su costo).
- **Memoria partida:** la de metodología y lo personal se puede exportar; la de dominio se queda con su proyecto.

## 7. Spike S1 (2026-10-24, Windows, Claude Code 2.1.284)

| Punto | Resultado |
|---|---|
| Hooks del plugin (`SessionStart`, `PreToolUse`, `PostToolUse`, `SubagentStop`) en forma exec con `${CLAUDE_PLUGIN_ROOT}`, en Python y en PowerShell 5.1 | ✅ |
| exit 2 bloquea, y el mensaje llega intacto en UTF-8 (tildes y eñes) | ✅ |
| Un matcher `^plugin:agente$` en `SubagentStop` atrapa solo a ese agente; `agent_type` trae el prefijo del plugin también en las herramientas del subagente | ✅ |
| Plugin habilitado por proyecto en `claude -p` y desde la extensión de VS Code, con la letra del disco en minúscula | ✅ |
| En VS Code, la confianza la da VS Code (se hereda a las subcarpetas); sin ella, la extensión no arranca: no existe el caso «agente sin hooks» | ✅ |
| `CLAUDE_PROJECT_DIR`: la carpeta de ticket si la sesión se abre ahí; la **primera** carpeta en un workspace multi-raíz | ✅ |
| Python: el alias de la Store arranca en 216 ms; el mismo intérprete llamado directo, en 51 ms | medido |
| Con `--plugin-dir`, `CLAUDE_PLUGIN_DATA` es otra carpeta que la del plugin instalado | ✅ |
| Instalación desde el repo privado de GitHub (S1.5), por HTTPS con Git Credential Manager y sin interacción | ✅ |
| Dos proyectos con versiones distintas en una misma máquina (S1.8) | pendiente; no bloquea (P4 asume el peor caso) |

## 8. Barrido de confidencialidad

`tools/barrido.py` corre en tres hooks:

| Hook | Qué barre |
|---|---|
| `pre-commit` | Lo stageado: el índice (no el árbol) y las rutas |
| `commit-msg` | El mensaje del commit |
| `pre-push` | Todo lo que se empuja: contenido, rutas y mensajes. Es la garantía real, porque `rebase --continue` y `git am` commitean sin pasar por el pre-commit |

Además:

- **Normaliza** mayúsculas, tildes, espacios, caracteres de formato (espacio de ancho cero, guion suave) y separadores (`\`, `\\` y `/` valen lo mismo).
- **Busca en el texto completo**, así que un término de varias palabras partido por un salto de línea también se encuentra.
- **Lee** UTF-8, UTF-16 con y sin BOM, y cp1252 (lo que escribe por defecto `Set-Content` en PowerShell 5.1).
- **Falla cerrado** si la lista negra falta, está vacía o tiene caracteres ilegibles.
- **`--autoprueba`** demuestra, antes de cada barrido, que **cada** término se detecta en UTF-8, UTF-16 y cp1252, y dice qué lista usó.

La lista negra vive fuera del repo, en `~/.odd-ws/denylist.txt` (o donde diga `ODD_WS_DENYLIST`).

**Riesgo residual:** un clon sin `core.hooksPath .githooks` no corre ningún hook, porque git no los instala solo. Lo cubre `/odd-ws:doctor` (ítem `repo-hooks`), verificado con un clon nuevo: lo marca FALTA y `--arreglar repo-hooks` lo configura. Un escaneo del lado del servidor obligaría a subir la lista negra, lo que contradice el principio 3.

## 9. Propuestas abiertas

- Los hooks bloquean solo lo determinista; lo que pide juicio va a los reviewers.
- Fixtures de la verificación E2E: mini-repos sintéticos generados por las suites (uno con deuda sembrada y otro limpio).
- El «listo en una semana» se mide en tickets con recibo, no en días: el día 1 da el escudo, la semana 1 es sombra, y la calibración pide tickets reales.
- Campo `fuente: equipo | propia` por fila de la matriz: cuando aparezca el primer caso.
