---
name: revisar
description: Revisar un cambio de un ticket con los revisores de la instancia (el de diseño y el de cada capa tocada). Usar antes del commit de un cambio, o antes de mostrárselo a un líder. Hace el triaje, anuncia el modo y su costo, espera el sí, lanza las corridas, consolida los reportes y deja un recibo atado al diff.
---

# /odd-ws:revisar

Orquesta la revisión de un cambio con los agentes de `.claude/agents/`: `revisor-diseno` (entre capas) y el `revisor-<capa>` de cada capa que toca el cambio. Los revisores solo leen: **el orquestador arma la entrada, lanza las corridas, rescata los reportes, los consolida y escribe el recibo.** Ningún revisor edita código ni commitea, y esta skill tampoco: ni `git add` ni `git commit`.

En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts` y `<ticket>` es la carpeta del ticket. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

## Qué se sabe de estos revisores

- **Hay varianza.** Dos corridas del mismo revisor sobre el mismo código pueden opinar distinto sobre la misma pieza.
- **Varias corridas no suman aciertos sobre la mejor.** Sirven para protegerse de la corrida mala y para **mostrar los conflictos**: una corrida dice X y otra lo contrario. Un conflicto no se resuelve votando: es una señal de que la decisión es de dominio, y la toma el líder o se revisa a mano.

## Reglas duras

1. **Nunca se lanza una revisión sin el sí del usuario**, aunque el modelo haya invocado la skill por su cuenta. La revisión cuesta corridas; el sí va después de anunciar el modo y su costo (paso 2). Hay dos excepciones, y en las dos el modo se anuncia igual:
   - el modo `0`, que cuesta cero corridas, corre sin pedir el sí;
   - el rechequeo que anunció, con su costo, el mensaje del lote de corrección: aprobar ese lote aprueba también el rechequeo (sección 9).
2. **Nunca dos revisiones a la vez.** Las corridas de una revisión se lanzan juntas; la siguiente revisión espera a que esta termine.
3. **No hay bucle automático de corrección.** El usuario decide qué corrige, y una revisión se cierra con una corrección y un rechequeo (sección 9). Cualquier otra revisión después de corregir es un pedido nuevo y vuelve a pedir el sí.
4. **Solo git de lectura en los repos del equipo.** No se cambia de rama, no se toca el índice (un archivo sin trackear entra al diff con `--no-index`, nunca con `git add -N`) y no se plantan archivos en esos repos: todo lo que escribe esta skill va dentro de la carpeta del ticket.
5. **Todas las corridas de una revisión usan el mismo modelo.** No pases `model` a ninguna o pasale el mismo alias a todas, y no fijes IDs de modelo.
6. **Esta skill no congela nada.** Si el usuario quiere que la revisión quede como caso del modo sombra, mandalo a `/odd-ws:eval-reviewers`.

## 1. Las entradas

- **El ticket.** Su carpeta es `tickets/<id>-<slug>/`. Si el usuario solo dio el id, buscala con el glob recursivo `tickets/**/<id>-*/CLAUDE.md` (la herramienta Glob lista archivos, no carpetas): un ticket archivado puede estar en una subcarpeta. Si el glob encuentra más de una carpeta, listalas y preguntale al usuario cuál es; nunca elijas una por tu cuenta, porque con ids que llevan guion la carpeta de un ticket puede coincidir también con el glob de otro id.
- **Los repos tocados**, con su rama o worktree:
  - la ruta de cada repo sale de `workspace.local.json` (`repos.<repo>.path`);
  - el worktree y la rama del ticket están en su `CLAUDE.md`, en «Worktree y rama». Si el ticket trabaja en un worktree, ese es el `--repo`, no el árbol principal;
  - si no está claro qué repos toca el cambio, preguntá.
- **La base** de cada repo es la misma que usan el triaje y el recibo, y sale en este orden:
  1. la explícita, si pasás `--repo <ruta>#<base>`;
  2. con `--ticket`, el commit más nuevo que sellaron los recibos del ticket (`recibo.py --sellar`, después del commit de una unidad revisada), si es ancestro de `HEAD` y más nuevo que el merge-base con `origin/HEAD`;
  3. si no, el merge-base con `origin/HEAD`.

  Así una unidad ya revisada y commiteada no se vuelve a revisar. Los scripts no hacen `git fetch`: si el `origin/HEAD` local puede estar atrasado, proponé el `git fetch` de ese repo y corrélo solo con el sí del usuario, porque habla con el remoto. Si un repo no tiene `origin/HEAD`, los scripts salen con 2 y piden `git remote set-head origin -a` o la base explícita con `--repo <ruta>#<base>`. Un repo sin ningún remoto, con la base explícita, cuenta sus consumidores en esa base; con remoto y sin `origin/HEAD`, la señal de consumidores queda inválida.
- **Los archivos del ticket.** El triaje lista todo lo que cambió contra la base. Si entre esos archivos hay algunos que no son del ticket (por ejemplo, archivos del ambiente local que están modificados a propósito), separalos con el usuario: no entran a la entrada ni al recibo.

## 2. El triaje y el sí

1. Corré el triaje, que solo lee:

   ```bash
   python3 "<S>/triaje.py" --ticket "<ticket>" --repo <repo o worktree>[#<base>] [--repo …] [--taller <archivo del taller del ticket>] [--clon <repo>] [--raiz <raíz de la instancia>] [--json]
   ```

   - Se corre desde la carpeta de la instancia o con `--raiz`. Con `--json` salen los hashes completos de la base, que se usan en el recibo.
   - Pasá siempre `--ticket`: un `--repo` sin `#<base>` parte del último commit sellado del ticket. La línea `repo … (base …, <origen>)` dice de dónde salió (`sellada en revision/…`, `merge-base con origin/HEAD` o `explícita`), y en `--json` van `base_origen` y `base_recibo`. Mostrala junto al modo.
   - Si el ticket tiene una unidad revisada que el usuario ya commiteó y nadie selló, sellala antes del triaje (ver «Después de la revisión»). Si `--sellar` sale con 1, seguí: el triaje usa el sello anterior o el merge-base.
   - Sale con 0, o con 2 si falta un `--repo` o un `--taller`, o si hay un error de uso o de entorno (por ejemplo, un repo sin `origin/HEAD`): mostrá el mensaje tal cual y corregilo.
2. **El modo lo propone el triaje y no se elige a ojo.** Las señales solo escalan:

   | Modo | Sale cuando |
   |---|---|
   | `sin-cambios` | no hay cambios contra la base: no hay nada que revisar, se avisa y se termina |
   | `0` | solo docs o notas del taller: lectura estructural, sin revisores |
   | `rapido` | todas las señales en negativo y el instrumento verificado |
   | `completo` | cualquier señal positiva o inválida |

   Un falso positivo solo cuesta una revisión de más; un falso negativo cuesta un hallazgo que llega al líder. Ante la duda, subí. No bajes el modo por tu cuenta.
3. **Preguntá si el cambio va a un líder antes del commit.** El triaje no lo puede detectar: lo declara en «el triaje NO detecta». Si va a un líder, el modo es `completo` aunque todo haya salido en negativo.
4. Si el triaje nombra archivos «fuera de la unidad» (generados sin trackear, como `__pycache__/` o `*.pyc`), no entran a la revisión ni al recibo; decíselo al usuario en una línea, porque puede borrarlos o ignorarlos en su repo. Mostrá también la lista «el triaje NO detecta» y aplicá tu criterio a lo que toque este cambio (consumidores fuera de los repos declarados, la forma de un resultado que consume otra capa, constantes compartidas).
5. **Anunciá, antes de lanzar nada:**
   - el modo y las señales que lo decidieron (o «va a un líder»);
   - las capas tocadas, que salen de la columna `[capa]` del triaje. Un archivo `sin capa` no tiene revisor de capa: lo lee el de diseño, y se avisa;
   - el costo, en corridas, sin inventar cifras: `modo 0` son 0 corridas; `rapido` son `1 + <capas tocadas>`; `completo` son `3 + <capas tocadas>`. Cada una cuesta lo que una corrida de revisor sobre este diff.
6. **Esperá el sí del usuario.** Sin sí explícito, no se lanza ni se escribe nada. Las dos excepciones de la regla 1:
   - **modo `0`:** no hay nada que lanzar. Anunciá el modo y los archivos que vas a leer, y seguí con la sección 5 sin esperar;
   - **un rechequeo** que el usuario aprobó junto con su lote de corrección: seguí sin volver a pedirlo.

## 3. La entrada de los revisores

**La carpeta de la revisión** es `<ticket>/revision/<fecha>-<modo>/`, con la fecha de hoy (`AAAA-MM-DD`) fijada para toda la revisión. **Si ya existe** (otra ronda del mismo día y modo, por ejemplo el rechequeo después de una corrección), no la pises ni la muevas: esta ronda va en `<fecha>-<modo>-2`, o en el siguiente número libre, y en todo lo que sigue `<fecha>-<modo>` quiere decir esa carpeta con su número. El recibo de esa ronda se escribe con `--ronda <n>`.

Con el sí, creá `<ticket>/revision/<fecha>-<modo>/entrada/` y guardá ahí un diff por repo, `<repo>.diff`, solo con los archivos del ticket:

```bash
git -C <repo> diff --no-color <base> -- <archivo> [<archivo>…] > "<entrada>/<repo>.diff"
git -C <repo> diff --no-color --no-index -- /dev/null <archivo nuevo sin trackear> >> "<entrada>/<repo>.diff"
```

- La primera línea cubre los archivos trackeados (commiteados o no); la segunda se repite por cada archivo nuevo sin trackear y sale con 1, que es lo normal en `--no-index`.
- `<base>` es la base completa del triaje.
- Si el diff sale vacío, pará: algo de la lista no cuadra.

## 4. Las corridas

Cada corrida es un `Agent` en segundo plano (`run_in_background`), todas en el **mismo mensaje**. Si el agente no existe (por ejemplo, `revisor-diseno` en una instancia que se generó antes de que el plugin lo trajera), no lo reemplaces con otro: decile al usuario que complete la instancia con `/odd-ws:bootstrap`, y que si el agente es nuevo en esta sesión hace falta reabrirla.

| Modo | Corridas |
|---|---|
| `0` | ninguna: lectura estructural (paso 5) |
| `rapido` | `revisor-diseno` ×1, más `revisor-<capa>` ×1 por cada capa tocada |
| `completo` | `revisor-diseno` ×3, con los archivos en un orden distinto en cada corrida (con un solo archivo el orden es el mismo y las 3 son muestras independientes: no lo anuncies como «en otro orden»), más `revisor-<capa>` ×1 por cada capa tocada |

**Un rechequeo** (sección 9) corre `revisor-diseno` ×1 más `revisor-<capa>` ×1 por cada capa de los rechequeados, también en modo `completo`: sin orden barajado ni frecuencias.

**Orden barajado (modo `completo`).** La primera corrida de diseño recibe los archivos en el orden del triaje; la segunda, en el orden inverso; la tercera, en un orden barajado. El orden va escrito en el prompt como lectura sugerida.

**La forma del prompt:**

```
Revisá <el diseño | el código de la capa <capa>> del ticket <id> (<título>) antes del commit.

Entrada:
- Diff de <repo>: <ruta de <repo>.diff> (base <commit>, rama <rama>). El código completo está en <ruta del repo o worktree>: leé ahí el código, sus hermanos y sus consumidores.
- (una línea por cada repo tocado)
- Carpeta del ticket: <ruta>. Leé su CLAUDE.md del disco, aunque ya tengas uno cargado: el que cargaste al arrancar puede ser anterior al Paso 0. No leas su carpeta revision/: trae reportes de otras revisiones.
- <solo capa> Archivos de tu capa: <lista>.
- <solo diseño, modo completo> Orden de lectura sugerido: <lista>.

Entregá el reporte con tu contrato.
```

- Anotá la tabla `nombre de corrida → agentId`, con nombres `<revisor>-r<i>` (`revisor-diseno-r1`, `revisor-capa-a-r1`…). Los `agentId` los devuelve cada lanzamiento.
- **No leas reportes parciales:** esperá a que terminen todas. Nunca lances otra revisión mientras tanto.

## 5. El modo 0

No hay corridas, así que no se pide el sí: se anuncia el modo y se sigue. Leé vos los archivos de docs o notas cambiados y revisá su estructura: encabezados, enlaces y rutas que citan, que lo que afirman exista, y que no queden restos de borrador. Mostrá el resultado, escribí el recibo (paso 8) con `--modo 0`, sin `--reviewer`, y dejá la lectura en `--verificacion "lectura estructural: <resultado>"`.

## 6. El rescate

Cuando terminan todas las corridas:

```bash
python3 "<S>/rescatar.py" --sesion "<carpeta subagents de esta sesión>" --destino "<ticket>/revision/<fecha>-<modo>/corridas" --corrida <nombre>=<agentId> --corrida …
```

- `--sesion` es la carpeta `subagents` de esta sesión, bajo `~/.claude/projects/<proyecto>/<sesión>/`. También acepta la carpeta de la sesión que la contiene. Si no la encontrás, buscala con Glob: `~/.claude/projects/*/*/subagents/agent-<agentId>.jsonl`.
- Por cada corrida escribe `<nombre>.md` (el reporte), `.prompt.txt`, `.lecturas.json` y, si hubo comandos, `.comandos.json`. El reporte sale del `SubagentHandback` o, si no hubo, del último texto.
- Sale con 0 si todas están bien, con 1 si alguna corrida no dejó reporte (`FAIL … sin SubagentHandback` o `no existe agent-…`) y con 2 por error de uso.
- **Una corrida cortada se informa y no se reintenta en silencio.** Decile al usuario cuál falló y preguntá: relanzar solo esa o seguir sin ella. Si se sigue sin ella, la frecuencia se cuenta sobre las corridas que sí hay (k/2) y se dice.
- Una herramienta «NO auditada» en la salida (`Bash`, `PowerShell`) en un revisor que solo debería leer se informa: no es una corrida limpia.

## 7. La consolidación

La hace el orquestador, en prosa, leyendo los reportes de `corridas/`.

- **Modo `rapido`, y todo rechequeo:** junta los reportes de diseño y de capa. Cada hallazgo, una vez, con su ubicación y su regla.
- **Modo `completo`:**
  - **Hallazgos con su frecuencia** entre las tres corridas de diseño (3/3, 2/3, 1/3), unidos por ubicación y regla. Los que salieron 1/3 van marcados **«a confirmar»**.
  - **Conflictos:** la misma pieza con veredictos opuestos entre corridas (por ejemplo, «quitar» contra «consumido»). Van en su propia sección, **«Decide el líder o revisa a mano»**, con la evidencia de cada lado y **sin votar**.
- **En los dos modos:**
  - **La severidad de diseño y la de capa van separadas.** Cada hallazgo conserva la del revisor que lo dijo (`CRITICAL`, `WARNING`, `SUGGESTION`); no se promedian ni se unifican.
  - **Lo derivado:** lo que diseño pasó a un revisor de capa y lo que ese revisor devolvió. Una derivación que nadie toma (diseño se la pasa a la capa y la capa se la devuelve) se marca **«sin dueño»** y se la lleva el usuario.
  - **Preguntas para el líder**, aparte: las que cualquier corrida dejó como pregunta, no como hallazgo.
  - Lo que ya estaba antes del cambio y los límites que declaró cada revisor van aparte; un límite declarado no es un hallazgo.
- Guardá la consolidación en `<ticket>/revision/<fecha>-<modo>/consolidado.md`.

## 8. Presentar y dejar el recibo

1. **Presentá** la consolidación al usuario. Él decide qué corrige. No corrijas por tu cuenta ni lances otra revisión: la corrección y su rechequeo siguen la sección 9.
2. **Escribí el recibo** al cerrar la revisión. Lleva la lista **explícita** de los archivos revisados por repo, nunca el working tree entero: `--archivo` es obligatorio y, con más de un `--repo`, cada uno es una ruta absoluta.

   ```bash
   python3 "<S>/recibo.py" --write --ticket "<ticket>" --repo <repo>#<base> [--repo …] --archivo <ruta absoluta> [--archivo …] --modo <0|rapido|completo> --fecha <AAAA-MM-DD> [--ronda <n>] --reviewer <agente> [--reviewer …] --verificacion "<comando>: <resultado>" [--verificacion …] --estado <limpio|con-hallazgos|pendiente> [--derivado "<hallazgo>=<destino>" …]
   ```

   - `--fecha` es la misma de la carpeta de la revisión: sin ella toma el día de hoy, y puede no coincidir.
   - `--derivado` anota un hallazgo que no se corrige en esta unidad y va a otra tarea, otro ticket o el backlog (sección 9). Es repetible, y el destino es lo que va después del último `=`. Uno sin `=`, o con un lado vacío, es un error de uso.
   - `--ronda <n>` va solo desde la segunda ronda del mismo día y modo, con el número de su carpeta. `--check` toma la ronda más alta, o la de `--recibo`.
   - `<base>` es la base completa del triaje, para que el recibo cubra el mismo diff que se revisó.
   - Los `--reviewer` son los agentes que corrieron (cada nombre una vez). `--estado` es `limpio` si no hubo hallazgos, `pendiente` si los hubo y el usuario todavía no los resolvió, o `con-hallazgos` si los hubo y ya los resolvió (corregidos, o descartados con su motivo). Cuando el usuario resuelve los de un recibo `pendiente`, volvé a escribirlo con `con-hallazgos` y los mismos argumentos; si era un rechequeo, también con su `--previo`, porque sin él el recibo pierde lo heredado y después no se puede sellar. `--verificacion` anota lo que se corrió de verdad y su resultado.
   - Escribe `revision/<fecha>-<modo>[-<n>]/recibo.json`, con una entrada por repo (base, hash del diff por archivo, archivos, modo, revisores, verificación y estado). Sale con 0, o con 2 si falta el ticket, un repo, un `--archivo` o el `--modo`.
   - Si el recibo ya existía, se pisa entero: pasá todos los `--repo` en una sola llamada.
3. **Antes de decir «listo» o «listo para commit», corré `--check`:**

   ```bash
   python3 "<S>/recibo.py" --check "<ticket>/revision/<fecha>-<modo>"
   ```

   - Pasá la carpeta de esta revisión. Si pasás la del ticket, toma el recibo más reciente, y a igual fecha el de modo `completo`, que puede no ser el de esta revisión; en ese caso filtrá con `--modo <m>` o apuntá con `--recibo <ruta>`.
   - **Exit 0:** el recibo vale, no cambió un byte de lo revisado.
   - **Exit 1:** cambió el diff revisado y el recibo no vale. Re-revisá **la divergencia** que nombra (repo y archivos) con un rechequeo (sección 9), que pide su sí salvo que el usuario lo haya aprobado con su lote de corrección. Un recibo viejo no autoriza nada.
   - **Exit 2:** error de uso o de entorno (no hay recibo, el repo ya no existe, `--modo` contradice al recibo). Mostrá el mensaje y no digas «listo».
4. **Qué decir.** Con exit 0, el estado del recibo y lo pendiente del usuario. Con 1 o 2, nunca «listo para commit».

## 9. El cierre: una corrección y un rechequeo

Una revisión se cierra así, para que corregir no se vuelva un bucle ni cueste una revisión entera por vuelta. En un ticket real, la re-revisión después de una corrección volvió a revisar la unidad entera, al mismo costo que la primera, y no se podía sellar una parcial; los hallazgos que quedaron para después terminaron dentro de la tabla de Tareas, y la rompieron.

1. **Una sola corrección.** Con la consolidación, el usuario elige qué se corrige, y eso es un lote. El mensaje que propone el lote anuncia también el rechequeo y su costo en corridas (abajo): si el usuario aprueba el lote, aprueba el rechequeo.
2. **Un rechequeo** cuando termina el lote. Verifica los hallazgos anteriores y revisa solo lo que cambió desde la ronda anterior:
   - **Qué entra.** Los rechequeados son los archivos que nombra `recibo.py --check "<carpeta de la ronda anterior>"` cuando sale con 1 (los que cambiaron), más los que el triaje lista y el recibo anterior no tiene (los que sumó la corrección, como un test nuevo). Si `--check` sale con 0 y la corrección no sumó archivos, no hay nada que rechequear. Un archivo sumado nunca se salta: sin su rechequeo queda sin revisar y `--sellar` rechaza el commit que lo trae.
   - **La base** es la del recibo anterior, y el triaje con `--ticket` da esa misma mientras la unidad no se selle. **El modo** es el de la ronda anterior, y la carpeta es la ronda siguiente (`<fecha>-<modo>-<n>`). Si el triaje de ahora da otra base o propone un modo más alto, no es un rechequeo: es una revisión nueva de la unidad entera, que pide su sí.
   - **Las corridas** son una de `revisor-diseno` más una por cada capa de los archivos rechequeados, `1 + <capas>`, tanto en `rapido` como en `completo`, sobre un diff que trae solo esos archivos. En modo `0` son cero. El rechequeo verifica una corrección acotada y no repite las tres corridas de `completo`: en un ticket real, dos rechequeos de una corrida, con los hallazgos anteriores en el prompt, cerraron bien. Si los rechequeados tocan una capa que el mensaje del lote no anunció, el costo cambió: anunciá el nuevo y pedí el sí.
   - **La entrada** es el diff de los rechequeados contra la base (paso 3). El prompt suma los hallazgos de la ronda anterior, con su ubicación, su regla y su severidad, copiados del `consolidado.md`, y pide decir de cada uno si quedó resuelto. La regla de no leer `revision/` sigue.
   - **El recibo** hereda lo que no cambió:

     ```bash
     python3 "<S>/recibo.py" --write --ticket "<ticket>" --repo <repo>#<base> [--repo …] --archivo <rechequeado> [--archivo …] --previo "<ticket>/revision/<carpeta de la ronda anterior>" --modo <modo> --fecha <AAAA-MM-DD> --ronda <n> --reviewer <agente> [--reviewer …] --verificacion "<comando>: <resultado>" [--verificacion …] --estado <limpio|con-hallazgos|pendiente> [--derivado "<hallazgo>=<destino>" …]
     ```

     - `--archivo` lista solo lo rechequeado, y el recibo cubre la unidad entera: lo rechequeado, con su hash de ahora, y cada archivo del recibo anterior que no se pasó, que tiene que estar igual que entonces. Un repo del recibo anterior sin nada rechequeado no se pasa: se hereda entero. Un `--repo` sin `#<base>` toma la base del recibo anterior.
     - Un archivo nuevo de la unidad que la corrección quitó se pasa con `--archivo`: queda en `retirados`, fuera del recibo.
     - **Exit 1**, sin escribir nada: un archivo del recibo anterior cambió y no está en `--archivo` (rechequealo), o la base no es la del recibo anterior.
     - **Exit 2:** `--previo` no es un recibo de este ticket, o el rechequeo no queda después de él: tiene que ir en la misma fecha y modo con una `--ronda` más alta, o en una fecha posterior.
     - Con eso, `--check` y `--sellar` valen para la unidad entera.
3. **Lo que trae el rechequeo:**
   - un hallazgo `CRITICAL`, nuevo o uno anterior que sigue abierto, se corrige en esta unidad, como un lote nuevo con su rechequeo, y los dos siguen esta misma regla;
   - un hallazgo que no es `CRITICAL`, nuevo o uno anterior que sigue abierto, **se deriva**: no se corrige en esta unidad, sino que va a otra tarea, otro ticket o el backlog. Anotalo en el recibo con `--derivado "<hallazgo>=<destino>"` y en `## Seguimientos` del ticket, una línea por hallazgo (`<fecha>: <qué> → <destino>`), nunca en la tabla de Tareas;
   - con eso la revisión queda cerrada: el recibo del rechequeo es el de la unidad, y después del commit se sella.

## Después de la revisión

- El commit es del usuario. Esta skill no commitea nada, y en los repos del equipo nunca se commitea sin una autorización puntual.
- **Después del commit de una unidad revisada, sellá su recibo**, antes de cualquier otro commit, y mostrá su línea:

  ```bash
  python3 "<S>/recibo.py" --sellar "<ticket>/revision/<carpeta de la unidad>"
  ```

  - Por qué: anota en el recibo el commit que guarda lo revisado, y el triaje de la unidad siguiente parte de ese commit en vez del merge-base. Sin sello, vuelve a contar lo ya revisado (en un ticket real, 83 archivos en vez de los 21 de la unidad nueva).
  - Pasá la carpeta del recibo de la unidad: la de su última ronda, la del rechequeo si lo hubo. Con la carpeta del ticket toma el recibo más nuevo por fecha, modo y ronda, que puede no ser el de esta unidad (por ejemplo, una unidad en modo `0` revisada el mismo día después de una en `rapido`). Sellar de nuevo sin mover `HEAD` no cambia nada.
  - **Exit 0:** `recibo sellado: <recibo> (<commit> en <n> repo(s))`.
  - **Exit 1:** no sella y no toca el recibo: cambió el diff revisado, hay archivos revisados sin commitear («commitea primero lo revisado»), o `HEAD` trae cambios fuera de lo revisado (por ejemplo, un commit de otra unidad). Mostrá el motivo; no lo fuerces, porque un sello sobre lo no revisado lo dejaría fuera del triaje siguiente.
  - **Exit 2:** error de uso o de entorno. Mostrá el mensaje.
- Si el modo fue `completo` y el cambio va a un líder, y el usuario quiere dejar la revisión como caso del modo sombra, `/odd-ws:eval-reviewers`. Ahí se congela, se puntúa y se ratifica; esta skill no toca ninguna de esas etapas.

## Scripts

| Script | Para qué | Salidas |
|---|---|---|
| `triaje.py` | propone el modo con las señales del diff | 0 ok · 2 error de uso o de entorno |
| `rescatar.py` | reporte, prompt y lecturas de cada corrida desde el `.jsonl` del subagente | 0 ok · 1 corrida sin reporte · 2 error |
| `recibo.py` | `--write` escribe el recibo, y con `--previo` el de un rechequeo, que hereda lo que no cambió; `--check` lo compara con el diff actual; `--sellar` anota el commit que guarda lo revisado | 0 escrito, vale o sellado · 1 el diff cambió, no se puede sellar o el rechequeo no puede heredar · 2 error de uso o de entorno |
