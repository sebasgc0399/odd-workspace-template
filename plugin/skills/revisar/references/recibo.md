# El recibo: la base, la bajada, cada opción y sus salidas

Detalle de `recibo.py` para `/odd-ws:revisar`. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`, y las secciones y los pasos que se citan son los del `SKILL.md`.

## La base

La base de cada repo es la misma que usan el triaje y el recibo, y sale en este orden:

1. la explícita, si pasas `--repo <ruta>#<base>`;
2. con `--ticket`, el commit más nuevo que sellaron los recibos del ticket (`recibo.py --sellar`, después del commit de una unidad revisada), si es ancestro de `HEAD` y más nuevo que el merge-base con `origin/HEAD`;
3. si no, el merge-base con `origin/HEAD`.

Así una unidad ya revisada y commiteada no se vuelve a revisar. Los scripts no hacen `git fetch`: si el `origin/HEAD` local puede estar atrasado, propón el `git fetch` de ese repo y córrelo solo con el sí del usuario, porque habla con el remoto. El triaje lista todo lo que cambió contra la base.

- En el triaje, un `--repo` sin `#<base>` parte del último commit sellado del ticket. La línea `repo … (base …, <origen>)` dice de dónde salió (`sellada en revision/…`, `merge-base con origin/HEAD` o `explícita`), y en `--json` van `base_origen` y `base_recibo`. Con `--json` salen los hashes completos de la base, que se usan en el recibo.
- El triaje sale con 0, o con 2 si falta un `--repo` o un `--taller`, o si hay un error de uso o de entorno (por ejemplo, un repo sin `origin/HEAD`). Si el `--sellar` previo al triaje sale con 1, el triaje usa el sello anterior o el merge-base.
- Si un repo no tiene `origin/HEAD`, los scripts salen con 2 y piden `git remote set-head origin -a` o la base explícita con `--repo <ruta>#<base>`. Un repo sin ningún remoto, con la base explícita, cuenta sus consumidores en esa base; con remoto y sin `origin/HEAD`, la señal de consumidores queda inválida.
- En el recibo, `<base>` es la base completa del triaje, para que el recibo cubra el mismo diff que se revisó. Un `--repo` sin `#<base>` toma la misma que el triaje con `--ticket`, con la misma función: la explícita, el sello vivo más nuevo del ticket o el merge-base. Al reescribir un recibo, toma la que ese recibo guarda.

## El triaje de la entrada

`entrada/triaje.json` trae la huella del diff de cada repo y de cada archivo, la misma que guarda el recibo, y con ella `recibo.py` sabe si el diff cambió después del triaje. `triaje.json` y `recibo.json` no se editan a mano: los escriben los scripts, y `recibo.py` valida el triaje entero (las seis señales, y que el modo sea el que dan sus señales y sus archivos). Si algo no cuadra, se vuelve a correr el script.

## La bajada

Un falso positivo solo cuesta una revisión de más; un falso negativo cuesta un hallazgo que llega al líder. Ante la duda, sube. **Nunca bajes el modo por tu cuenta:** la bajada de un escalón la pide el usuario, con su motivo (paso 6). El triaje no puede detectar si el cambio va a un líder: lo declara en «el triaje NO detecta». Si va a un líder, el modo es `completo` aunque todo haya salido en negativo.

- **Cuándo cabe ofrecerla:** si el modo es `completo`, el usuario dijo que el cambio no va a un líder (paso 3) y todas las positivas son límites del instrumento, di en una línea que puede bajarlo un escalón, a `rapido`, si deja el motivo. Un límite del instrumento es una señal `invalida`, o la de `capas` cuando en `--json` `sin_capa.unico_motivo_de_capas` es `true`; cualquier otra `positiva` es un riesgo real. No la recomiendes: decide el usuario.
- **Si el usuario baja el modo**, su pedido es el sí de `rapido`, con su motivo. Es un escalón, de `completo` a `rapido`: nunca a `0` si hay código, nunca si el cambio va a un líder y nunca si el triaje vio un riesgo real. Si pide bajar sin haber respondido lo del líder, pregúntaselo antes. La carpeta va con el modo bajado (`<fecha>-rapido`), su `entrada/triaje.json` es el que propuso `completo`, y el recibo lleva `--bajada` (paso 8).
- **En el recibo**, `--bajada "<motivo>" --va-a-lider no` va solo cuando el usuario bajó el modo (sección 2, paso 6), con su motivo y su respuesta sobre el líder. `recibo.py` lo valida contra `entrada/triaje.json` de la carpeta de la revisión: el triaje tiene que proponer `completo`, `--modo` tiene que ser `rapido` y no puede haber un riesgo real. Ese triaje tiene que ser de este diff: cada repo y cada archivo del recibo tienen que estar en el triaje, con la misma base y la misma huella, así que un archivo editado después del triaje lo deja viejo. El triaje puede haber visto más que el recibo, como los archivos del ambiente local que separaste en la sección 1: eso no rechaza, y `recibo.py` los nombra en un aviso. Si alguno es del ticket, revísalo y súmalo con `--archivo`. Si `recibo.py` dice que `no es de este diff`, vuelve a correr el triaje con `--json` y los mismos argumentos que el recibo, guárdalo en `entrada/triaje.json` y mira de nuevo su modo, porque la edición pudo traer un riesgo real. Guarda en el recibo `bajada` con `de`, `a`, `motivo` y `va_a_lider`. Cualquier otro par de modos, un motivo vacío, `--va-a-lider si` o sin `--bajada`, un triaje que falta, no se lee o no trae su huella, o un riesgo real es un error de uso: sale con 2 sin escribir nada.

## `--write`

- `--fecha` es la misma de la carpeta de la revisión: sin ella toma el día de hoy, y puede no coincidir.
- **El modo no baja sin `--bajada`.** Si la carpeta de la revisión tiene `entrada/triaje.json`, `--modo` es igual o más alto que el que propuso, y el triaje tiene que leerse y ser válido aunque no vaya `--bajada`. Salvo con `--modo completo`, que no tiene piso que violar, ese triaje también tiene que ser de este diff, igual que con la bajada: un triaje viejo en `rapido` no habilita `rapido` después de una edición que pudo sumar riesgo. Con `--previo`, `--modo` también es igual o más alto que el del recibo anterior. Un modo más bajo es un error de uso: sale con 2 sin escribir nada.
- `--derivado` anota un hallazgo que no se corrige en esta unidad y va a otra tarea, otro ticket o el backlog (sección 9). Es repetible, y el destino es lo que va después del último `=`. Uno sin `=`, o con un lado vacío, es un error de uso.
- `--ronda <n>` va solo desde la segunda ronda del mismo día y modo, con el número de su carpeta. `--check` toma la ronda más alta, o la de `--recibo`.
- Los `--reviewer` son los agentes que corrieron (cada nombre una vez). `--estado` es `limpio` si no hubo hallazgos, `pendiente` si los hubo y el usuario todavía no los resolvió, o `con-hallazgos` si los hubo y ya los resolvió (corregidos, o descartados con su motivo). Cuando el usuario resuelve los de un recibo `pendiente` sin tocar lo revisado (los descarta o los deriva), vuelve a escribirlo con `con-hallazgos` y los mismos argumentos; si era un rechequeo, también con su `--previo`. Si resolverlos cambió lo revisado, no se reescribe: es un rechequeo (sección 9). `--verificacion` anota lo que se corrió de verdad y su resultado.
- **El destino** de la línea de rendimiento se completa también al reescribir uno `pendiente`. Los derivados son los que van con `--derivado`, y los descartados, los que el usuario descartó con su motivo. Con `pendiente`, el destino sigue `pendiente`.
- Escribe `revision/<fecha>-<modo>[-<n>]/recibo.json`, con una entrada por repo (base, hash del diff por archivo, archivos, modo, revisores, verificación y estado). Sale con 0, con 1 si ese recibo ya existe con otro diff, o con 2 si falta el ticket, un repo, un `--archivo` o el `--modo`.
- **Si el recibo ya existe**, `recibo.py` compara el diff de esta llamada (repos, bases, archivos y el hash de cada uno) con el que guarda. Si es el mismo, cambia el estado y conserva el sello y lo demás: lo que la llamada nombra (`--reviewer`, `--verificacion`, `--derivado`, `--bajada`) reemplaza lo guardado, y lo que no nombra queda. Si es otro (un archivo cambió, sobra o falta, o falta un repo), sale con 1 sin escribir y nombra cada diferencia: lo que cambió va en un rechequeo con `--previo` en la ronda siguiente (sección 9); si es el mismo diff, repite los mismos `--repo`, `--archivo` y `--previo`.

## Los secretos

Con corridas (`rapido` o `completo`), cuando `consolidado.md` ya tiene su destino y antes del `--check`, tapa los secretos de la entrada y de la consolidación, que quedan en la instancia:

```bash
python3 "<S>/tapar.py" "<ticket>/revision/<fecha>-<modo>/entrada/*.diff" "<ticket>/revision/<fecha>-<modo>/consolidado.md"
```

- Reescribe cada archivo en el lugar, con su codificación y sus fines de línea, y dice cuántos secretos tapó en cada uno. Cada secreto queda como un marcador con su tipo, como `<GITHUB_TOKEN>`. Correrlo de nuevo no cambia nada.
- Tapa solo formatos concretos: claves de AWS, tokens de GitHub, Slack, Google, OpenAI, Anthropic y Stripe, y bloques de clave privada. No busca «etiqueta: valor»: en una prueba real solo dio falsos positivos (`dark:`, `sm:`, `mailto:`).
- El comodín va entre comillas, porque `tapar.py` lo expande él mismo, también en PowerShell y en cmd.
- Se tapa después del rescate y nunca antes de lanzar: los revisores ven los diffs crudos, porque un secreto en el código es un hallazgo `CRITICAL`. Los reportes de `corridas/` ya salen tapados del rescate, y el recibo tapa su texto libre (`--verificacion`, `--derivado` y `--bajada`).
- No invalida el recibo, que guarda la huella del diff de los repos y no la de `entrada/`; `triaje.json` no se toca, y sus `chequeos` ya salen tapados del triaje.
- Sale con 0; con 2, sin escribir nada, si un archivo no existe, es una carpeta, el comodín no encuentra nada o un archivo no se puede leer. Si falla la escritura de un archivo, sale con 2: los anteriores ya quedaron tapados y el que falló queda como estaba, sin temporales. Muestra el mensaje y no digas «listo».

## `--check`

- Pasa la carpeta de esta revisión. Si pasas la del ticket, toma el recibo más reciente, y a igual fecha el de modo `completo`, que puede no ser el de esta revisión; en ese caso filtra con `--modo <m>` o apunta con `--recibo <ruta>`.
- La segunda línea dice el estado, el modo y la bajada del recibo: `estado: <estado>; modo: <modo>; bajada: no`, o `bajada: de completo a rapido (<motivo>)`.
- **Lo que entraría al commit.** `--check` le aplica al índice el criterio de `--sellar`: lo revisado no puede estar stageado en otra versión, y el índice no puede traer, contra la base, archivos fuera del recibo (lo ya commiteado desde la base también cuenta). Los cambios del working tree fuera del recibo que no están en el índice salen como aviso por stderr: no entran al commit salvo que los stagees. Un recibo ya sellado no mira el índice, porque su commit ya pasó.
- **Exit 0:** el recibo vale: no cambió un byte de lo revisado y el índice no trae otra cosa.
- **Exit 1, `NO vale … cambio el diff revisado`:** cambió el diff revisado y el recibo no vale. Re-revisa **la divergencia** que nombra (repo y archivos) con un rechequeo (sección 9), que pide su sí salvo que el usuario lo haya aprobado con su lote de corrección. Un recibo viejo no autoriza nada.
- **Exit 1, `NO vale para el commit`:** lo revisado no cambió, pero el índice no es lo revisado. Lo stageado en otra versión se stagea tal cual; lo que no es de esta unidad se saca del índice; lo que sí es, o ya está commiteado desde la base, se rechequea con `--previo`, como propone el mensaje.
- **Exit 2:** error de uso o de entorno (no hay recibo, el repo ya no existe, `--modo` contradice al recibo). Muestra el mensaje y no digas «listo».

## `--sellar`

- Por qué: anota en el recibo el commit que guarda lo revisado, y el triaje de la unidad siguiente parte de ese commit en vez del merge-base. Sin sello, vuelve a contar lo ya revisado (en un ticket real, 83 archivos en vez de los 21 de la unidad nueva).
- Pasa la carpeta del recibo de la unidad: la de su última ronda, la del rechequeo si lo hubo. Con la carpeta del ticket toma el recibo más nuevo por fecha, modo y ronda, que puede no ser el de esta unidad (por ejemplo, una unidad en modo `0` revisada el mismo día después de una en `rapido`). Sellar de nuevo sin mover `HEAD` no cambia nada.
- **Exit 0:** `recibo sellado: <recibo> (<commit> en <n> repo(s))`.
- **Exit 1:** no sella y no toca el recibo: cambió el diff revisado, hay archivos revisados sin commitear («commitea primero lo revisado»), `HEAD` trae cambios fuera de lo revisado (por ejemplo, un commit de otra unidad), o el recibo está `pendiente`. Muestra el motivo; no lo fuerces, porque un sello sobre lo no revisado lo dejaría fuera del triaje siguiente. Con cambios fuera de lo revisado, el mensaje propone el rechequeo con `--previo` de este recibo y esos archivos en `--archivo`: su recibo cubre la unidad entera, y ese sí se sella. Con `pendiente`, reescríbelo con `con-hallazgos` o `limpio` (paso 2 de la sección 8) y sella.
- **Exit 2:** error de uso o de entorno. Muestra el mensaje.

## Los scripts

| Script | Para qué | Salidas |
|---|---|---|
| `triaje.py` | propone el modo con las señales del diff | 0 ok · 2 error de uso o de entorno |
| `rescatar.py` | reporte, prompt, lecturas y costo de cada corrida desde el `.jsonl` del subagente o, con `--host pi`, desde la tarea que guarda gentle-shell; `--costo` escribe el `costo.json` de la revisión y `--ultimo-costo` imprime el último costo medido | 0 ok · 1 corrida sin reporte, o ningún costo medido con `--ultimo-costo` · 2 error |
| `recibo.py` | `--write` escribe el recibo, con `--previo` el de un rechequeo, que hereda lo que no cambió, y con `--bajada` la bajada de un escalón que pidió el usuario; `--check` lo compara con el diff actual y con lo que entraría al commit; `--sellar` anota el commit que guarda lo revisado | 0 escrito, vale o sellado · 1 el diff cambió, el índice no es lo revisado, el recibo ya existe con otro diff, no se puede sellar o el rechequeo no puede heredar · 2 error de uso o de entorno |
| `tapar.py` | tapa en el lugar los secretos de `entrada/*.diff` y `consolidado.md` antes del `--check` | 0 ok · 2 error de uso o de lectura, sin escribir nada, o de escritura, con los archivos anteriores ya tapados |
