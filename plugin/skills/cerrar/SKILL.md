---
name: cerrar
description: Cierra un ticket de la instancia, graduando lo aprendido. Usar al terminar un ticket, para triar sus aprendizajes, subir lo general a los docs de dominio, a la raíz o a la matriz de reglas, actualizar los dos relojes del ticket y dejar el commit de cierre. Solo lo invoca el usuario.
disable-model-invocation: true
---

# /odd-ws:cerrar

Ritual de cierre de un ticket: que lo aprendido no quede atrapado en su carpeta. Corre desde la raíz de la instancia (o desde dentro de la carpeta del ticket). En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts`, `<ticket>` es la carpeta del ticket y `<capa>` es una capa declarada en `workspace.config.json` con `rule_prefix`.

## Reglas duras

1. **Nada se escribe antes del sí** a la propuesta del paso 4. Mostrar primero, escribir después.
2. **Se gradúa solo a lo que ya existe:** los docs de `knowledge.docs`, el `CLAUDE.md` raíz, la matriz (`.claude/reglas/matriz.csv`) y `.claude/reglas/evidencia.md`. No crees destinos nuevos por tu cuenta. Engram, si esta sesión lo tiene, es opcional: guardá lo relevante, pero nunca reemplaza a ninguno de los destinos de arriba.
3. **Los repos del equipo son de solo lectura** para esta skill: ni `git add` ni `git commit` ahí. El único commit es el de la raíz de la instancia (paso 9).
4. **`Estado` y `Conocimiento` son dos relojes distintos.** Esta skill mueve el de `Conocimiento`; `Estado` solo cambia si la entrega cambió de verdad.
5. **Un bug posterior no desgradúa nada:** si demuestra que un doc decía algo falso, se corrige el doc.

## 1. Leer el ticket

- La carpeta se encuentra con el glob recursivo `tickets/**/<id>-*`: un ticket archivado puede estar en una subcarpeta. La herramienta Glob lista archivos, no carpetas: usá `tickets/**/<id>-*/CLAUDE.md`. Si el glob encuentra más de una carpeta, listalas y preguntale al usuario cuál es; nunca elijas una por tu cuenta, porque con ids que llevan guion la carpeta de un ticket puede coincidir también con el glob de otro id.
- Leé su `CLAUDE.md`: Decisiones, Gotchas, **Candidatos a graduar** y Bitácora. Confirmá que los criterios de aceptación están marcados; si falta alguno, decilo antes de seguir.
- **Comprobá cada `Fuente:` externa** (una transcripción, un documento, una ruta fuera de la instancia): tiene que seguir resolviendo. Si una ruta ya no existe, se corrige o se anota **antes** de promover: lo destilado no vale si su fuente dejó de ser localizable.

## 2. Triaje de cada aprendizaje

Por cada decisión, gotcha, hallazgo y candidato del ticket, decidí a dónde va:

| Lo aprendido | Destino |
|---|---|
| Aplica solo a este ticket | **Se queda** en su carpeta. No se promueve. |
| Conocimiento de dominio (cómo funciona algo del proyecto) | El doc de `knowledge.docs` que corresponde. Para elegirlo, listá la carpeta de `knowledge.docs` y mirá qué dice de cada doc el índice de `knowledge.index` (por defecto, el `CLAUDE.md` raíz), como en `/odd-ws:abrir`. |
| Metodología o convención de trabajo | El `CLAUDE.md` raíz, en la sección que corresponda. Se mantiene corto (lo mide `conocimiento.py`): si crece, el detalle va a un doc y la raíz solo lo indexa. |
| **Criterio de revisión** o convención de una capa | Una **fila de la matriz**, más la regla escrita en su destino (paso 5). |
| Una medición (cuánto tarda, cuánto pesa, cuántos consumidores) | `.claude/reglas/evidencia.md`. |
| Un pendiente que este ticket resolvió | Se cierra con su evidencia donde viva ese pendiente. |

**Cada aprendizaje se clasifica además como de dominio o de motor.** De dominio es lo del proyecto; **de motor** es lo que habla del propio plugin `odd-ws` (un script, una skill o la plantilla). Lo de motor no se gradúa a ningún destino de la instancia: se anota en la última entrada de la bitácora como `→ motor: <hallazgo>`, sin buzón, y queda para quien mantiene el plugin.

Si hay una **sección «Candidatos a graduar»** con ítems, cada uno ya viene marcado como general y con su destino: promovelo ahí o descartalo con razón. Al graduar, la sección **queda vacía**, para que la apertura de un ticket hermano no vuelva a ver lo ya promovido.

## 3. El modo sombra va primero

Si el ticket tiene un caso congelado del modo sombra (`<ticket>/revision/<fecha>-sombra/`) que todavía no se puntuó ni se ratificó, **primero se puntúa y después se gradúa**, con `/odd-ws:eval-reviewers`. La regla nueva es justo la respuesta que ese caso mide: graduarla antes vuelve inútil la medición. Si hay uno pendiente, frená acá, antes de proponer nada, y mandá al usuario a puntuarlo; los criterios de ese ticket se gradúan cuando termine.

## 4. La propuesta y el sí

Mostrá, **antes de escribir nada**, todo lo que este cierre va a escribir, ya con el modo sombra resuelto (paso 3):

1. **Los aprendizajes:** una tabla con una fila por aprendizaje: qué es, dominio o motor, destino y el texto o la fila exacta que vas a escribir. Para cada fila de la matriz mostrá todos sus campos (paso 5).
2. **Los dos relojes** del `CLAUDE.md` del ticket (paso 6): el valor y la fecha exactos de `Conocimiento`, y `Estado`, sin cambio o con su valor nuevo y por qué.
3. **La entrada de la bitácora** (paso 6), con su texto: lo graduado y a dónde, lo pendiente, lo de motor y la foto de la entrega por repo, que mirás antes con git de solo lectura.
4. **El commit de cierre** (paso 9): los archivos que irían al `git add` y el mensaje.

Después pedí un sí explícito. Sin sí, no se escribe nada. Si el usuario corrige un destino o cualquier otra línea, ajustá la propuesta y volvé a mostrarla.

## 5. Promover (con el sí)

Escribí lo aprobado en su destino, uno por uno:

- **Un doc de dominio o el `CLAUDE.md` raíz:** editá la sección que corresponde. Si el doc es nuevo, tiene que quedar enlazado desde el índice. Si cambia una cifra o un dato que ya vivía en otro doc, buscá sus copias antes de seguir.
- **Una fila de la matriz.** Las columnas, en este orden, son `id, origen, tipo, destino, severidad, numeros, resumen, motivo`:
  - `id`: el siguiente libre de la capa, `<rule_prefix>-NN` (por ejemplo `EJ-01`, `EJ-02`). El script de abajo lo calcula con la matriz y con los ids que ya usa `.claude/reglas/verificar_<capa>.py`, porque una instancia puede traer reglas propias sin fila en la matriz.
  - `origen`: fijado a un commit que ya existe, `<ruta>@<hash>:<ini>-<fin>` (el rango es de líneas, base 1), normalmente la decisión del ticket o su bitácora. **Si la fuente todavía no está commiteada, hay que commitearla antes** (con el sí del usuario): comprobalo con `git status --short -- <ruta>`, que tiene que salir vacío, y sacá el hash con `git log -1 --format=%h -- <ruta>`. Una memoria va como `memoria:<slug>` y no lleva hash.
  - `tipo`: uno de `CE`, `CC`, `PR`, `CR`, `MT`, `META`. La plantilla no los define: copiá el de una fila vecina de la matriz con el mismo destino, y si la matriz está vacía proponé uno y confirmalo con el usuario.
  - `destino`: **uno solo**: `chequeo`, `pasiva`, `skill`, `reviewer-PR`, `criterios`, `evidencia` o `descarte`. Son archivos de la instancia: `chequeo` es `.claude/reglas/verificar_<capa>.py`; `pasiva` es el bloque `no-negociables` de `.claude/skills/capa-<capa>/SKILL.md`; `skill` es ese mismo archivo, fuera del bloque; `reviewer-PR` es `.claude/agents/revisor-<capa>.md`; `criterios` es `.claude/skills/criterios/SKILL.md` (o su `references/`); `evidencia` es `.claude/reglas/evidencia.md`.
  - `severidad`: `CRITICAL`, `WARNING`, `SUGGESTION` o vacía. `numeros`: cifras que la regla tiene que citar, separadas por `;`, o vacío. `resumen` y `motivo`: texto, no pueden quedar vacíos.
  - Una regla transversal lleva una fila por cada capa a la que aplica, y se deja escrito por qué no a las otras.

  Se agrega **al final**, con el módulo `csv` de Python (para que el resto del archivo quede byte a byte), con LF y sin BOM. Guardá este script con la herramienta Write en un archivo fuera de la instancia, completá los campos y corrélo desde la raíz de la instancia:

  ```python
  import csv, re

  RUTA = ".claude/reglas/matriz.csv"
  REGLAS = ".claude/reglas/verificar_<capa>.py"
  PREFIJO = "<rule_prefix>"
  FILA = ["", "<ruta>@<hash>:<ini>-<fin>", "<tipo>", "<destino>", "<severidad>", "<numeros>", "<resumen>", "<motivo>"]

  ID = re.escape(PREFIJO) + r"-([0-9]{2,})"
  ultimo = 0
  with open(RUTA, encoding="utf-8", newline="") as f:
      for reg in csv.reader(f):
          m = re.fullmatch(ID, reg[0]) if reg else None
          if m:
              ultimo = max(ultimo, int(m.group(1)))
  try:
      with open(REGLAS, encoding="utf-8", errors="replace") as f:
          for m in re.finditer(r"\b" + ID + r"\b", f.read()):
              ultimo = max(ultimo, int(m.group(1)))
  except FileNotFoundError:
      pass
  FILA[0] = "%s-%02d" % (PREFIJO, ultimo + 1)
  with open(RUTA, "a", encoding="utf-8", newline="") as f:
      csv.writer(f, lineterminator="\n").writerow(FILA)
  print(FILA[0])
  ```

  Imprime el ID asignado. Después escribí la regla **en su destino, con ese ID**, en una línea o párrafo que además contenga la severidad y los números de la fila (el chequeo busca el ID y su segmento, hasta la línea en blanco siguiente).
- **Evidencia.** Una medición es una fila con `destino` `evidencia`: su ID tiene que aparecer **una sola vez** en `.claude/reglas/evidencia.md`, con su fuente (por ejemplo, bajo un encabezado con el ID). La evidencia de una regla que va a otro destino también se anota ahí citando su ID, salvo que la fila sea `descarte`: el chequeo exige que un descarte no aparezca en ningún destino. Una regla sin evidencia no entra a la matriz.

**Después de cada fila nueva, la matriz tiene que dar 0 fallas** para su capa:

```bash
python "<S>/matriz.py" --destinos --capa <capa>
python "<S>/matriz.py" --severidad --capa <capa>
```

Salen con 0 si todo cuadra, con 1 si hay `FALLA` o `ESQUEMA` (muestra el mensaje y corregí la fila o la regla) y con 2 por un error de entorno (por ejemplo, una capa sin `rule_prefix`). Un `PENDIENTE` significa que el destino todavía no existe: no es una falla, pero tampoco una regla escrita.

## 6. Los dos relojes

En el `CLAUDE.md` del ticket, lo que mostró la propuesta (paso 4):

- **`Conocimiento`:** `graduado (AAAA-MM-DD)`, o `descartado (AAAA-MM-DD, motivo)` si el ciclo se cierra sin cosechar nada (un ticket reasignado, por ejemplo). Con `graduado`, **«Candidatos a graduar» tiene que quedar vacía**: `graduado` es un recibo, no una declaración. Esta skill no lo chequea con ningún script: lo pide, y lo mirás vos antes de escribir la fecha.
- **`Estado` no se toca**, salvo que la entrega haya cambiado de verdad. El conocimiento gradúa cuando está verificado y es general, no cuando el código sale: un ticket puede quedar `en revisión` y `graduado`, y eso es correcto.
- **Una última entrada de la bitácora** con:
  - qué se graduó y a dónde, y qué queda pendiente;
  - lo de motor, como `→ motor: <hallazgo>`;
  - **la foto de la entrega, por repo:** la rama con su hash, o qué falta subir y de quién; si falta algo, también va a la `Nota de estado`. Se mira con git de solo lectura (`git -C <repo> log -1 --format=%h <rama>`; si la rama está pusheada, `git -C <repo> branch -r --contains <hash>`). Si el `origin` puede estar atrasado, proponé el `git fetch` de ese repo y corrélo solo con el sí del usuario, porque habla con el remoto. Sin fetch ni forma de comprobarlo, se anota **«no verificado»**. Es una foto: informa, no condiciona el `graduado`.

## 7. Desarmar el worktree

Mirá «Worktree y rama» del ticket. Si usó un worktree, **recordale al usuario que lo desarme a mano**, porque los comandos en los repos del equipo los corre él:

```bash
git -C <repo> worktree remove <ruta del worktree>
git -C <repo> worktree prune
```

**La rama no se borra** en este paso: su merge lo autoriza un líder, no el cierre.

## 8. El conocimiento

Después de editar los docs, corré el nivel 1 de `/odd-ws:conocimiento`, que revisa el índice, los links, las anclas y el tope de líneas:

```bash
python "<S>/conocimiento.py"
```

Sale con 0 si está sano, con 1 si hay algún `FAIL` (corregilo antes del commit), con 3 si solo hay deuda y con 2 por un error de entorno. El aviso «todo commiteado» es esperado en este punto: el commit de cierre lo resuelve.

## 9. El commit de cierre

Un solo commit, **en la raíz de la instancia y nunca en los repos del equipo**, con el cierre del ticket y lo que se promovió, para que los docs no queden rezagados del ticket que los cambió.

1. **Mostrá el estado antes de commitear:**

   ```bash
   git -c status.relativePaths=false status --short
   ```

2. **`git add` explícito, nunca `-A`**: barre la instancia entera, con los tickets de otros y los cambios ajenos. Las rutas se anclan a la raíz con `:/`, desde cualquier profundidad, y van solo los archivos que **este cierre** tocó:

   ```bash
   git add -- ':/<ruta>' ':/<ruta>' …
   ```

3. **Lo ajeno se saca del índice** y se avisa: lo que aparezca stageado que el cierre no tocó (un ticket de otro, un archivo del ambiente local). Si un archivo ya venía modificado antes del cierre, entra entero: avisalo.

   ```bash
   git reset -q -- ':/<ruta>'
   ```

4. Mostrá el `status` otra vez, con lo stageado a la izquierda, y **pedí el sí para el commit**. Con el sí, un mensaje convencional:

   ```bash
   git commit -m "chore(<id>): cierre e hidratación"
   ```

   Si el pre-commit de la instancia falla, mostrá su salida: no lo saltees con `--no-verify`.

## Qué decir al final

El resumen del cierre: qué se graduó y a dónde, qué se quedó en el ticket, lo de motor anotado, el estado de los dos relojes, el hash del commit y lo que le toca al usuario (desarmar el worktree, el `fetch` si quedó «no verificado»).
