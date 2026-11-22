---
name: cerrar
description: Cierra un ticket graduando lo aprendido, o con memorias gradúa las reglas de las memorias del proyecto. Solo lo invoca el usuario.
disable-model-invocation: true
---

# /odd-ws:cerrar

Ritual de cierre de un ticket: que lo aprendido no quede atrapado en su carpeta. Corre desde la raíz de la instancia (o desde dentro de la carpeta del ticket). En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts`, `<ticket>` es la carpeta del ticket y `<capa>` es una capa declarada en `workspace.config.json` con `rule_prefix`. En Windows con Codex, los comandos van con `python` en lugar de `python3`. El detalle está en `references/`, junto a este archivo: se lee solo cuando un paso lo pide, y ahí `<S>` quiere decir lo mismo.

**Con el argumento `memorias`** (`/odd-ws:cerrar memorias`; en Codex, `$cerrar memorias`) no se cierra ningún ticket: lee `references/memorias.md` y sigue su «Modo memorias», no los pasos 1 a 10.

**Perfil `controles`.** Antes de nada, lee `workspace.config.json` en la raíz de la instancia: si dice `"profile": "controles"` y no vino el argumento `memorias`, el cierre de un ticket no aplica, porque esa instancia no tiene tickets. Dilo en una línea, recuerda que `/odd-ws:cerrar memorias` sí corre ahí, porque es por donde nacen sus reglas, y detente. Con `memorias`, sigue el «Modo memorias» como en cualquier instancia.

## Reglas duras

1. **Nada se escribe antes del sí** a la propuesta del paso 4. Mostrar primero, escribir después.
2. **Se gradúa solo a lo que ya existe:** los docs de `knowledge.docs`, el `CLAUDE.md` raíz, la matriz (`.claude/reglas/matriz.csv`) y `.claude/reglas/evidencia.md`. No crees destinos nuevos por tu cuenta. Engram, si esta sesión lo tiene, es opcional: guarda lo relevante, pero nunca reemplaza a ninguno de los destinos de arriba.
3. **Los repos del equipo son de solo lectura** para esta skill: ni `git add` ni `git commit` ahí. El único commit es el de la raíz de la instancia (paso 9).
4. **`Estado` y `Conocimiento` son dos relojes distintos.** Esta skill mueve el de `Conocimiento`; `Estado` solo cambia si la entrega cambió de verdad.
5. **Un bug posterior no desgradúa nada:** si demuestra que un doc decía algo falso, se corrige el doc.

## 1. Leer el ticket

- La carpeta se encuentra con el glob recursivo `tickets/**/<id>-*` (un ticket archivado puede estar en una subcarpeta); como Glob lista archivos, no carpetas, usa `tickets/**/<id>-*/CLAUDE.md`. Si encuentra más de una carpeta, lístalas y pregunta cuál es; nunca elijas tú, porque con ids que llevan guion el glob de un id puede traer otro ticket.
- Lee su `CLAUDE.md`: Decisiones, Gotchas, **Candidatos a graduar** y Bitácora. Si falta marcar algún criterio de aceptación, dilo antes de seguir.
- **Comprueba cada `Fuente:` externa** (una transcripción, un documento, una ruta fuera de la instancia): si ya no resuelve, se corrige o se anota **antes** de promover, porque lo destilado no vale si su fuente dejó de ser localizable.
- **Revisa sus enlaces** con `python3 "<S>/ticket.py" --enlaces <id>` (con varias carpetas, la ruta del `CLAUDE.md` elegido). Si están todos bien, no digas nada. Los rotos y los que llevan una ruta de la máquina (`C:\…`, `/home/…`, `~/…`), que se rompen en el clon de otra persona, van a la propuesta del paso 4 con su arreglo (un enlace relativo a la carpeta del ticket, o sacarlo si ya no sirve), y se escriben con su sí, nunca antes.

## 2. Triaje de cada aprendizaje

Por cada decisión, gotcha, hallazgo y candidato del ticket, decide a dónde va:

| Lo aprendido | Destino |
|---|---|
| Aplica solo a este ticket | **Se queda** en su carpeta. No se promueve. |
| Conocimiento de dominio (cómo funciona algo del proyecto) | El doc de `knowledge.docs` que corresponde: lista su carpeta y mira qué dice de cada doc el índice de `knowledge.index` (por defecto, el `CLAUDE.md` raíz), como en `/odd-ws:abrir`. |
| Metodología o convención de trabajo | El `CLAUDE.md` raíz, en su sección. Se mantiene corto (lo mide `conocimiento.py`): si crece, el detalle va a un doc y la raíz solo lo indexa. |
| **Criterio de revisión** o convención de una capa | Una **fila de la matriz**, más la regla escrita en su destino (paso 5). |
| Una medición (cuánto tarda, cuánto pesa, cuántos consumidores) | Una **fila de la matriz** con `destino` `evidencia`, y su ID una sola vez en `.claude/reglas/evidencia.md`, con su fuente (paso 5). |
| Un pendiente que este ticket resolvió | Se cierra con su evidencia donde viva ese pendiente. |

**Cada aprendizaje se clasifica además como de dominio o de motor.** De dominio es lo del proyecto; **de motor**, lo que habla del propio plugin `odd-ws` (un script, una skill o la plantilla), que no se gradúa a ningún destino de la instancia: se anota en la última entrada de la bitácora como `→ motor: <hallazgo>`, sin buzón, y queda para quien mantiene el plugin.

Los ítems de la **sección «Candidatos a graduar»** ya vienen marcados como generales y con su destino: promuévelos ahí o descártalos con razón. Al graduar, la sección **queda vacía**, para que la apertura de un ticket hermano no vuelva a ver lo ya promovido.

## 3. El modo sombra va primero

Si el ticket tiene un caso congelado del modo sombra (`<ticket>/revision/<fecha>-sombra/`) sin puntuar ni ratificar, frena aquí, antes de proponer nada, y manda al usuario a puntuarlo con `/odd-ws:eval-reviewers`: **primero se puntúa y después se gradúa**, porque graduar antes la regla que ese caso mide vuelve inútil la medición. Los criterios de ese ticket se gradúan cuando termine.

## 4. La propuesta y el sí

Muestra, **antes de escribir nada**, todo lo que este cierre va a escribir, ya con el modo sombra resuelto:

1. **Los aprendizajes:** una tabla con una fila por aprendizaje: qué es, dominio o motor, destino y el texto o la fila exacta que vas a escribir. Una fila de la matriz va con todos sus campos y, si es un chequeo que tiene que bloquear, con su `sembrado`; si el ticket anota que una regla bloqueó algo correcto, va su disputa. Una medición también es una fila, con `destino` `evidencia`. Antes de armarlas, lee `references/matriz.md`.
2. **Los dos relojes** (paso 6): el valor y la fecha exactos de `Conocimiento`, y `Estado`, sin cambio o con su valor nuevo y por qué.
3. **La entrada de la bitácora** (paso 6), con su texto y la foto de la entrega por repo, que miras antes con git de solo lectura.
4. **Los enlaces que se arreglan** (paso 1): el de hoy y el que lo reemplaza, o que se saca. Se escriben en el paso 6, con los relojes.
5. **El commit de cierre** (paso 9): los archivos del `git add` y el mensaje, marcando los que ya venían modificados: entran enteros, con los cambios que no son de este cierre.

Después pide un sí explícito: sin sí, no se escribe nada. Si el usuario corrige una línea, ajusta la propuesta y vuelve a mostrarla.

## 5. Promover (con el sí)

Escribe lo aprobado en su destino, uno por uno:

- **Un doc de dominio o el `CLAUDE.md` raíz:** edita la sección que corresponde. Si el doc es nuevo, tiene que quedar enlazado desde el índice. Si cambia una cifra o un dato que ya vivía en otro doc, busca sus copias antes de seguir.
- **Una fila de la matriz**, con el script que la agrega con su ID, su regla en su destino, su evidencia en `.claude/reglas/evidencia.md` y, si bloquea, su calibración: todo como dice `references/matriz.md`. Una regla sin evidencia no entra a la matriz.

**Después de cada fila nueva, la matriz tiene que dar 0 fallas** para su capa:

```bash
python3 "<S>/matriz.py" --destinos --capa <capa>
python3 "<S>/matriz.py" --severidad --capa <capa>
```

Salen con 0 si todo cuadra, con 1 si hay `FALLA` o `ESQUEMA` (muestra el mensaje y corrige la fila o la regla) y con 2 por un error de entorno (por ejemplo, una capa sin `rule_prefix`). Un `PENDIENTE` significa que el destino todavía no existe: no es una falla, pero tampoco una regla escrita.

## 6. Los dos relojes

En el `CLAUDE.md` del ticket, lo que mostró la propuesta:

- **`Conocimiento`:** `graduado (AAAA-MM-DD)`, o `descartado (AAAA-MM-DD, motivo)` si el ciclo se cierra sin cosechar nada (un ticket reasignado, por ejemplo). Con `graduado`, **«Candidatos a graduar» tiene que quedar vacía**: `graduado` es un recibo, no una declaración, y ningún script lo chequea: lo miras tú antes de escribir la fecha.
- **`Estado` no se toca** salvo que la entrega haya cambiado de verdad: el conocimiento gradúa cuando está verificado y es general, no cuando el código sale, así que un ticket puede quedar `en revisión` y `graduado`.
- **Una última entrada de la bitácora** con lo que se graduó y a dónde, lo pendiente, lo de motor como `→ motor: <hallazgo>` y **la foto de la entrega, por repo:** la rama con su hash, o qué falta subir y de quién (también en la `Nota de estado`), con git de solo lectura: `git -C <repo> log -1 --format=%h <rama>` y, si está pusheada, `git -C <repo> branch -r --contains <hash>`. Si el `origin` puede estar atrasado, propón el `git fetch` de ese repo y córrelo solo con el sí del usuario, porque habla con el remoto; sin fetch ni forma de comprobarlo, se anota **«no verificado»**. Es una foto: informa, no condiciona el `graduado`.

## 7. Desarmar el worktree

Si el ticket usó un worktree («Worktree y rama»), lee «El worktree» en `references/entrega.md` antes de tocarlo: en un repo con `"own": true` lo desarmas tú, con dos comprobaciones, y en uno del equipo lo desarma el usuario. **La rama no se borra.**

## 8. El conocimiento

Después de editar los docs, corre `python3 "<S>/conocimiento.py"`, el nivel 1 de `/odd-ws:conocimiento` (el índice, los links, las anclas y el tope de líneas). Sale con 0 si está sano, con 1 si hay algún `FAIL` (corrígelo antes del commit), con 3 si solo hay deuda y con 2 por un error de entorno. El aviso «todo commiteado» es esperado aquí: el commit de cierre lo resuelve.

## 9. El commit de cierre

Un solo commit, **en la raíz de la instancia y nunca en los repos del equipo**, con el cierre y lo promovido, para que los docs no queden rezagados del ticket que los cambió.

1. **Muestra el estado antes de commitear:** `git -c status.relativePaths=false status --short`.
2. **`git add` explícito, nunca `-A`**, que barre la instancia entera con los tickets de otros y los cambios ajenos: solo lo que **este cierre** tocó, anclado a la raíz con `:/`, que vale desde cualquier profundidad: `git add -- ':/<ruta>' ':/<ruta>' …`.
3. **Lo ajeno se saca del índice** con `git reset -q -- ':/<ruta>'`, y se avisa: lo stageado que el cierre no tocó (un ticket de otro, un archivo del ambiente local). Un archivo que ya venía modificado entra entero solo si estuvo en la propuesta, para que el sí lo cubra; si aparece recién aquí, sácalo y avísalo.
4. Muestra el `status` otra vez, con lo stageado a la izquierda, y **commitea sin volver a preguntar**: el sí del paso 4 ya cubrió el commit, y en la raíz de la instancia el agente commitea sin pedir aprobación; solo con `"ask_before_commit": true` en `workspace.config.json`, pide el sí antes. Nunca hagas push. Un mensaje convencional: `git commit -m "chore(<id>): cierre e hidratación"`. Si el pre-commit de la instancia falla, muestra su salida y no lo saltees con `--no-verify`.
5. **Si la entrega ya está** (`Estado` en `listo`), sácale la marca de ticket activo, que solo se quita si es la suya: `python3 "<S>/ticket.py" --desactivar <id>`. Si no, la marca se queda hasta «La entrega después del cierre».

## 10. Las memorias sin triar

Un aviso de una línea, que no tría ni frena el cierre: corre `python3 "<S>/memorias.py" --json --memorias "<dir>"` como en M1 del modo memorias, sin abrir su reference, con la memoria persistente que la sesión ya conoce (si no la conoces, sin la opción; en Codex, `--host codex` en su lugar), y otra vez por cada repo de `workspace.config.json`, con `--repo <repo>`. Cuenta las memorias en `nueva` y `cambiada` y avisa «N memorias sin triar (<origen>): `/odd-ws:cerrar memorias`», con el `cobertura.origen` del JSON (`pasada` o `derivada`); por ejemplo, «0 memorias sin triar (derivada): `/odd-ws:cerrar memorias`». Si el script sale con 2, o la cobertura sale `no disponible` (Codex), dilo en esa línea, con el motivo, y sigue.

## Qué decir al final

El resumen del cierre: lo graduado y a dónde, lo que se quedó en el ticket, lo de motor, los dos relojes, el hash del commit, el aviso de las memorias y lo que le toca al usuario: desarmar un worktree que no desarmaste, y el `fetch` si quedó «no verificado».

## La entrega después del cierre

Un ticket puede cerrarse `en revisión` y entregarse después. Cuando la entrega queda hecha (el usuario lo dice, o la hiciste tú en un repo propio con su sí), no se vuelve a correr el cierre: sigue los pasos de `references/entrega.md`.
