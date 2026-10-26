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
| P3 | Raíz de la instancia: subir desde `CLAUDE_PROJECT_DIR` hasta el primer `workspace.config.json`; rutas de la máquina en `workspace.local.json` (ignorado por git); clasificar el archivo editado con rutas canónicas `normcase(realpath(…))`; los globs del taller (`workshop`) y del filtro por repo (`match`) son por segmentos (`**` cruza carpetas; `*` no) y los worktrees de cada repo salen del registro de git, no de la config; **configuración rota ≠ ausente** (ausente: no-op en silencio; rota: los hooks no bloquean, pero `SessionStart` lo dice fuerte); `schema_version` en el config | El archivo editado suele estar fuera del árbol; una carpeta puede llegar con dos nombres (junctions, `c:` vs `C:`); un no-op silencioso por una configuración rota es un instrumento mudo |
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
- **Zona:** un archivo dentro de un repo declarado o de uno de sus worktrees, con cualquier extensión, o un archivo que `clasificar` asigna a una capa (el taller). Es contención canónica, no nombre: cuentan las junctions y las mayúsculas. Una carpeta es zona si está dentro de un repo, o si coincide con la carpeta padre de un glob de `workshop` (con `**` al final, también lo que está debajo).
- **Variables:** `~`, `$VAR`, `${VAR}`, `$env:VAR` y `%VAR%` se expanden con el entorno del hook; `$PWD` es la carpeta del shell que sigue el parser (`cd`), no la del hook. Una variable desconocida corta la ruta en la última carpeta conocida, y esa carpeta decide como zona; si no queda ninguna, la ruta no cuenta. Una ruta que no queda absoluta después de normalizarla (relativa sin `cd` conocido, relativa a la unidad como `C:x`, o con `..` que se come la unidad) no se resuelve: nunca cae en el cwd del proceso del hook. En Windows, una ruta con una sola barra inicial (`\repo\x`) toma la unidad del cwd que sigue el parser; sin cwd conocido, no se resuelve.
- **Scratch:** `<temporales>/claude/`, con la carpeta de `os.tmpdir()` de Node (`TEMP`, `TMP` o `%SystemRoot%\temp` en Windows; `TMPDIR` o `/tmp` en el resto). Le gana a una zona.
- **Foto del primer toque** (`Edit`/`Write`, nunca bloquea): el contenido previo de cada archivo, una vez por agente, en `.claude/estado/writers/<sesión>/<agente>.fotos/` (`capas.ESTADO_WRITERS`, P5), o la marca `.nuevo` si no existía. Con una sesión nueva se podan las de más de 7 días. La compuerta de cierre cuenta las líneas reales contra esa foto.
- `destinos(comando, cwd)` da los destinos de escritura que ve el mismo parser, sin decidir: la compuerta los deja en su sidecar.
- Falla abierta siempre; `--plazo` (8 s, timeout 10) es el límite del análisis, y al vencer calla.

### Biblioteca T-SQL (`odd_ws.tsql`)

Primitivas para el módulo de una capa SQL; la superficie la fija `odd_ws.PUBLICO["tsql"]`.

- **Texto:** `depurar(texto, literales=False)` pasa los comentarios (y, con `literales`, el contenido de los literales) a espacios, con el mismo largo y los mismos saltos de línea; `linea_de(texto, pos)`; `bloques_catch(depurado)` da `[(ini, fin, linea_ini, linea_fin)]` (un bloque sin cerrar llega hasta el final); `argumentos(texto, inicio)` da los argumentos a profundidad 0 de la sentencia que sigue.
- **AST:** `analizar(ctx)` corre ScriptDom (`scriptdom.ps1`, PowerShell) y devuelve `(análisis, motivo)`, sin escribir en el `ctx`. `motivo` es `None`, `sin_helper` (no hay PowerShell o DLL, el helper falló y queda roto para el resto del proceso, o no pudo leer ese archivo) o `sin_tiempo` (no queda el mínimo antes de `limite`, o el helper venció). El resultado se cachea por ruta y contenido, **también el vencimiento**: otra regla que pide el mismo archivo no relanza el helper, porque el plazo del hook alcanza para un solo intento. Un `limite` ya vencido no se cachea. `precalcular(ctxs)` analiza un lote en una sola invocación; si vence, todo el lote queda en `sin_tiempo`.
- **Chequeos genéricos:** `sql_dinamico(ctx)` (EXEC de una cadena armada con `+`, o `sp_executesql` con la sentencia concatenada) y `comentarios_agregados(ctx)` dan `[(línea, fragmento)]` sobre las líneas agregadas; sin análisis devuelven `[]`, y la instancia decide si avisa según el `motivo`. Dónde aplican es política de la instancia. `problemas_de_bytes(datos, bom=False, fin="crlf")` da la lista de problemas de BOM, fin de línea y UTF-8.
- **Normalizador** (CLI, fuera de la API): `normalizar_sql.py --check | --fix ARCHIVO... [--tabs] [--fin crlf|lf]`.

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

- **Capa 0, `/odd-ws:doctor`** (`plugin/scripts/doctor.py`): solo lee por defecto y arregla de a un ítem con `--arreglar <id>`. La v1 revisa los hooks y la lista negra del clon (cierra el riesgo B2b), Python por comportamiento y por latencia (S1.6), las credenciales de git, Claude Code ≥ 2.1.284, el marketplace, gentle-ai ≥ 4.2.0 con su RDD y su telemetría, engram ≥ 3.5.0 y `jq`. Quedaron afuera: `diff.autoRefreshIndex`, que el motor fija por proceso y viaja con él; `core.longpaths`, sin incidente que lo justifique; y MCPs, secretos, proxy corporativo, perfil de modelos y exportación de memoria, que entran cuando un caso real los pida.
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
