---
name: revisar
description: Revisar un cambio de un ticket con los revisores de la instancia (el de diseño y el de cada capa tocada). Usar antes del commit de un cambio, o antes de mostrárselo a un líder. Hace el triaje, anuncia el modo y su costo, espera el sí, lanza las corridas, consolida los reportes y deja un recibo atado al diff.
---

# /odd-ws:revisar

Orquesta la revisión de un cambio con los agentes de `.claude/agents/`: `revisor-diseno` (entre capas) y el `revisor-<capa>` de cada capa que toca el cambio. Los revisores solo leen: **el orquestador arma la entrada, lanza las corridas, rescata los reportes, los consolida y escribe el recibo.** Ningún revisor edita código ni commitea, y esta skill tampoco: ni `git add` ni `git commit`.

En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts` y `<ticket>` es la carpeta del ticket.

## Qué se sabe de estos revisores

- **Hay varianza.** Dos corridas del mismo revisor sobre el mismo código pueden opinar distinto sobre la misma pieza.
- **Varias corridas no suman aciertos sobre la mejor.** Sirven para protegerse de la corrida mala y para **mostrar los conflictos**: una corrida dice X y otra lo contrario. Un conflicto no se resuelve votando: es una señal de que la decisión es de dominio, y la toma el líder o se revisa a mano.

## Reglas duras

1. **Nunca se lanza una revisión sin el sí del usuario**, aunque el modelo haya invocado la skill por su cuenta. La revisión cuesta corridas; el sí va después de anunciar el modo y su costo (paso 2).
2. **Nunca dos revisiones a la vez.** Las corridas de una revisión se lanzan juntas; la siguiente revisión espera a que esta termine.
3. **No hay bucle automático de corrección.** El usuario decide qué corrige. Después de corregir, una revisión nueva es un pedido nuevo y vuelve a pedir el sí.
4. **Solo git de lectura en los repos del equipo.** No se cambia de rama, no se toca el índice (un archivo sin trackear entra al diff con `--no-index`, nunca con `git add -N`) y no se plantan archivos en esos repos: todo lo que escribe esta skill va dentro de la carpeta del ticket.
5. **Todas las corridas de una revisión usan el mismo modelo.** No pases `model` a ninguna o pásale el mismo alias a todas, y no fijes IDs de modelo.
6. **Esta skill no congela nada.** Si el usuario quiere que la revisión quede como caso del modo sombra, mándalo a `/odd-ws:eval-reviewers`.

## 1. Las entradas

- **El ticket.** Su carpeta es `tickets/<id>-<slug>/`. Si el usuario solo dio el id, búscala con el glob recursivo `tickets/**/<id>-*`: un ticket archivado puede estar en una subcarpeta.
- **Los repos tocados**, con su rama o worktree:
  - la ruta de cada repo sale de `workspace.local.json` (`repos.<repo>.path`);
  - el worktree y la rama del ticket están en su `CLAUDE.md`, en «Worktree y rama». Si el ticket trabaja en un worktree, ese es el `--repo`, no el árbol principal;
  - si no está claro qué repos toca el cambio, pregunta.
- **La base** de cada repo es el merge-base con `origin/HEAD`, y es la misma que usan el triaje y el recibo. Los scripts no hacen `git fetch`: si el `origin/HEAD` local puede estar atrasado, propón el `git fetch` de ese repo y córrelo solo con el sí del usuario, porque habla con el remoto. Si un repo no tiene `origin/HEAD`, los scripts salen con 2 y piden `git remote set-head origin -a` o la base explícita con `--repo <ruta>#<base>`.
- **Los archivos del ticket.** El triaje lista todo lo que cambió contra la base. Si entre esos archivos hay algunos que no son del ticket (por ejemplo, archivos del ambiente local que están modificados a propósito), sepáralos con el usuario: no entran a la entrada ni al recibo.

## 2. El triaje y el sí

1. Corre el triaje, que solo lee:

   ```bash
   python "<S>/triaje.py" --repo <repo o worktree>[#<base>] [--repo …] [--taller <archivo del taller del ticket>] [--clon <repo>] [--raiz <raíz de la instancia>] [--json]
   ```

   - Se corre desde la carpeta de la instancia o con `--raiz`. Con `--json` salen los hashes completos de la base, que se usan en el recibo.
   - Sale con 0, o con 2 si falta un `--repo` o un `--taller`, o si hay un error de uso o de entorno (por ejemplo, un repo sin `origin/HEAD`): muestra el mensaje tal cual y corrígelo.
2. **El modo lo propone el triaje y no se elige a ojo.** Las señales solo escalan:

   | Modo | Sale cuando |
   |---|---|
   | `sin-cambios` | no hay cambios contra la base: no hay nada que revisar, se avisa y se termina |
   | `0` | solo docs o notas del taller: lectura estructural, sin revisores |
   | `rapido` | todas las señales en negativo y el instrumento verificado |
   | `completo` | cualquier señal positiva o inválida |

   Un falso positivo solo cuesta una revisión de más; un falso negativo cuesta un hallazgo que llega al líder. Ante la duda, sube. No bajes el modo por tu cuenta.
3. **Pregunta si el cambio va a un líder antes del commit.** El triaje no lo puede detectar: lo declara en «el triaje NO detecta». Si va a un líder, el modo es `completo` aunque todo haya salido en negativo.
4. Muestra también la lista «el triaje NO detecta» y aplica tu criterio a lo que toque este cambio (consumidores fuera de los repos declarados, la forma de un resultado que consume otra capa, constantes compartidas).
5. **Anuncia, antes de lanzar nada:**
   - el modo y las señales que lo decidieron (o «va a un líder»);
   - las capas tocadas, que salen de la columna `[capa]` del triaje. Un archivo `sin capa` no tiene revisor de capa: lo lee el de diseño, y se avisa;
   - el costo, en corridas, sin inventar cifras: `modo 0` son 0 corridas; `rapido` son `1 + <capas tocadas>`; `completo` son `3 + <capas tocadas>`. Cada una cuesta lo que una corrida de revisor sobre este diff.
6. **Espera el sí del usuario.** Sin sí explícito, no se lanza ni se escribe nada.

## 3. La entrada de los revisores

Con el sí, y con la fecha de hoy (`AAAA-MM-DD`) fijada para toda la revisión, crea `<ticket>/revision/<fecha>-<modo>/entrada/` y guarda ahí un diff por repo, `<repo>.diff`, solo con los archivos del ticket:

```bash
git -C <repo> diff --no-color <base> -- <archivo> [<archivo>…] > "<entrada>/<repo>.diff"
git -C <repo> diff --no-color --no-index -- /dev/null <archivo nuevo sin trackear> >> "<entrada>/<repo>.diff"
```

- La primera línea cubre los archivos trackeados (commiteados o no); la segunda se repite por cada archivo nuevo sin trackear y sale con 1, que es lo normal en `--no-index`.
- `<base>` es la base completa del triaje.
- Si el diff sale vacío, para: algo de la lista no cuadra.

## 4. Las corridas

Cada corrida es un `Agent` en segundo plano (`run_in_background`), todas en el **mismo mensaje**. Si el agente no existe (por ejemplo, `revisor-diseno` en una instancia que se generó antes de que el plugin lo trajera), no lo reemplaces con otro: dile al usuario que complete la instancia con `/odd-ws:bootstrap`, y que si el agente es nuevo en esta sesión hace falta reabrirla.

| Modo | Corridas |
|---|---|
| `0` | ninguna: lectura estructural (paso 5) |
| `rapido` | `revisor-diseno` ×1, más `revisor-<capa>` ×1 por cada capa tocada |
| `completo` | `revisor-diseno` ×3, con los archivos en un orden distinto en cada corrida, más `revisor-<capa>` ×1 por cada capa tocada |

**Orden barajado (modo `completo`).** La primera corrida de diseño recibe los archivos en el orden del triaje; la segunda, en el orden inverso; la tercera, en un orden barajado. El orden va escrito en el prompt como lectura sugerida.

**La forma del prompt:**

```
Revisa <el diseño | el código de la capa <capa>> del ticket <id> (<título>) antes del commit.

Entrada:
- Diff de <repo>: <ruta de <repo>.diff> (base <commit>, rama <rama>). El código completo está en <ruta del repo o worktree>: lee ahí el código, sus hermanos y sus consumidores.
- (una línea por cada repo tocado)
- Carpeta del ticket: <ruta>. No leas su carpeta revision/: trae reportes de otras revisiones.
- <solo capa> Archivos de tu capa: <lista>.
- <solo diseño, modo completo> Orden de lectura sugerido: <lista>.

Entrega el reporte con tu contrato.
```

- Anota la tabla `nombre de corrida → agentId`, con nombres `<revisor>-r<i>` (`revisor-diseno-r1`, `revisor-capa-a-r1`…). Los `agentId` los devuelve cada lanzamiento.
- **No leas reportes parciales:** espera a que terminen todas. Nunca lances otra revisión mientras tanto.

## 5. El modo 0

No hay corridas. Lee tú los archivos de docs o notas cambiados y revisa su estructura: encabezados, enlaces y rutas que citan, que lo que afirman exista, y que no queden restos de borrador. Muestra el resultado, escribe el recibo (paso 8) con `--modo 0`, sin `--reviewer`, y deja la lectura en `--verificacion "lectura estructural: <resultado>"`.

## 6. El rescate

Cuando terminan todas las corridas:

```bash
python "<S>/rescatar.py" --sesion "<carpeta subagents de esta sesión>" --destino "<ticket>/revision/<fecha>-<modo>/corridas" --corrida <nombre>=<agentId> --corrida …
```

- `--sesion` es la carpeta `subagents` de esta sesión, bajo `~/.claude/projects/<proyecto>/<sesión>/`. También acepta la carpeta de la sesión que la contiene. Si no la encuentras, búscala con Glob: `~/.claude/projects/*/*/subagents/agent-<agentId>.jsonl`.
- Por cada corrida escribe `<nombre>.md` (el reporte), `.prompt.txt`, `.lecturas.json` y, si hubo comandos, `.comandos.json`. El reporte sale del `SubagentHandback` o, si no hubo, del último texto.
- Sale con 0 si todas están bien, con 1 si alguna corrida no dejó reporte (`FAIL … sin SubagentHandback` o `no existe agent-…`) y con 2 por error de uso.
- **Una corrida cortada se informa y no se reintenta en silencio.** Dile al usuario cuál falló y pregunta: relanzar solo esa o seguir sin ella. Si se sigue sin ella, la frecuencia se cuenta sobre las corridas que sí hay (k/2) y se dice.
- Una herramienta «NO auditada» en la salida (`Bash`, `PowerShell`) en un revisor que solo debería leer se informa: no es una corrida limpia.

## 7. La consolidación

La hace el orquestador, en prosa, leyendo los reportes de `corridas/`.

- **Modo `rapido`:** junta los reportes de diseño y de capa. Cada hallazgo, una vez, con su ubicación y su regla.
- **Modo `completo`:**
  - **Hallazgos con su frecuencia** entre las tres corridas de diseño (3/3, 2/3, 1/3), unidos por ubicación y regla. Los que salieron 1/3 van marcados **«a confirmar»**.
  - **Conflictos:** la misma pieza con veredictos opuestos entre corridas (por ejemplo, «quitar» contra «consumido»). Van en su propia sección, **«Decide el líder o revisa a mano»**, con la evidencia de cada lado y **sin votar**.
- **En los dos modos:**
  - **La severidad de diseño y la de capa van separadas.** Cada hallazgo conserva la del revisor que lo dijo (`CRITICAL`, `WARNING`, `SUGGESTION`); no se promedian ni se unifican.
  - **Lo derivado:** lo que diseño pasó a un revisor de capa y lo que ese revisor devolvió. Una derivación que nadie toma (diseño se la pasa a la capa y la capa se la devuelve) se marca **«sin dueño»** y se la lleva el usuario.
  - **Preguntas para el líder**, aparte: las que cualquier corrida dejó como pregunta, no como hallazgo.
  - Lo que ya estaba antes del cambio y los límites que declaró cada revisor van aparte; un límite declarado no es un hallazgo.
- Guarda la consolidación en `<ticket>/revision/<fecha>-<modo>/consolidado.md`.

## 8. Presentar y dejar el recibo

1. **Presenta** la consolidación al usuario. Él decide qué corrige. No corrijas por tu cuenta ni lances otra revisión.
2. **Escribe el recibo** al cerrar la revisión. Lleva la lista **explícita** de los archivos revisados por repo, nunca el working tree entero: `--archivo` es obligatorio y, con más de un `--repo`, cada uno es una ruta absoluta.

   ```bash
   python "<S>/recibo.py" --write --ticket "<ticket>" --repo <repo>#<base> [--repo …] --archivo <ruta absoluta> [--archivo …] --modo <0|rapido|completo> --fecha <AAAA-MM-DD> --reviewer <agente> [--reviewer …] --verificacion "<comando>: <resultado>" [--verificacion …] --estado <limpio|con-hallazgos|pendiente>
   ```

   - `--fecha` es la misma de la carpeta de la revisión: sin ella toma el día de hoy, y puede no coincidir.
   - `<base>` es la base completa del triaje, para que el recibo cubra el mismo diff que se revisó.
   - Los `--reviewer` son los agentes que corrieron (cada nombre una vez). `--estado` es `limpio` sin hallazgos, `con-hallazgos` con hallazgos, o `pendiente` si el usuario todavía no los resolvió. `--verificacion` anota lo que se corrió de verdad y su resultado.
   - Escribe `revision/<fecha>-<modo>/recibo.json`, con una entrada por repo (base, hash del diff por archivo, archivos, modo, revisores, verificación y estado). Sale con 0, o con 2 si falta el ticket, un repo, un `--archivo` o el `--modo`.
   - Si el recibo ya existía, se pisa entero: pasa todos los `--repo` en una sola llamada.
3. **Antes de decir «listo» o «listo para commit», corre `--check`:**

   ```bash
   python "<S>/recibo.py" --check "<ticket>/revision/<fecha>-<modo>"
   ```

   - Pasa la carpeta de esta revisión. Si pasas la del ticket, toma el recibo más reciente, y a igual fecha el de modo `completo`, que puede no ser el de esta revisión; en ese caso filtra con `--modo <m>` o apunta con `--recibo <ruta>`.
   - **Exit 0:** el recibo vale, no cambió un byte de lo revisado.
   - **Exit 1:** cambió el diff revisado y el recibo no vale. Re-revisa **la divergencia** que nombra (repo y archivos), como un pedido nuevo que pide su sí. Un recibo viejo no autoriza nada.
   - **Exit 2:** error de uso o de entorno (no hay recibo, el repo ya no existe, `--modo` contradice al recibo). Muestra el mensaje y no digas «listo».
4. **Qué decir.** Con exit 0, el estado del recibo y lo pendiente del usuario. Con 1 o 2, nunca «listo para commit».

## Después de la revisión

- El commit es del usuario. Esta skill no commitea nada, y en los repos del equipo nunca se commitea sin una autorización puntual.
- Si el modo fue `completo` y el cambio va a un líder, y el usuario quiere dejar la revisión como caso del modo sombra, `/odd-ws:eval-reviewers`. Ahí se congela, se puntúa y se ratifica; esta skill no toca ninguna de esas etapas.

## Scripts

| Script | Para qué | Salidas |
|---|---|---|
| `triaje.py` | propone el modo con las señales del diff | 0 ok · 2 error de uso o de entorno |
| `rescatar.py` | reporte, prompt y lecturas de cada corrida desde el `.jsonl` del subagente | 0 ok · 1 corrida sin reporte · 2 error |
| `recibo.py` | `--write` escribe el recibo; `--check` lo compara con el diff actual | 0 escrito o vale · 1 el diff cambió · 2 error de uso o de entorno |
