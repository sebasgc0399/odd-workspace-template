---
name: abrir
description: Abre un ticket de la instancia a partir de un pedido. Usar al empezar un ticket nuevo, para crear su carpeta desde la plantilla, llenar objetivo, criterios de aceptación y alcance, marcar las preguntas por fijar con el líder, mapear los docs de dominio que toca y traer los candidatos a graduar de los tickets hermanos. Solo lo invoca el usuario.
disable-model-invocation: true
---

# /odd-ws:abrir

Ritual de apertura de un ticket: que el trabajo arranque con el alcance entendido y no con el código. Corre desde la raíz de la instancia (o desde dentro de la carpeta de un ticket). En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts`, `<id>` es el id del pedido en el tracker, o el consecutivo de la instancia si no hay tracker, y `<ticket>` es la carpeta del ticket. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

## Reglas duras

1. **Nada se escribe antes del sí.** La carpeta se crea con el sí del paso 2, y el contenido del ticket se escribe con el sí del paso 8. Mostrar primero, escribir después.
2. **Nada se asume.** Si algo del pedido no está claro, queda como pregunta en el ticket. En particular, todo «X o Y» del pedido es una pregunta por fijar con el líder antes de codear, no una elección tuya.
3. **Los repos del equipo no se tocan.** Esta skill no corre `git` sobre ellos: los comandos que pide (el worktree, un `fetch`) los corre el usuario. La única lectura es la de `ticket.py --cobertura` (paso 8), que lista lo versionado sin cambiar nada. Lo único que escribe es, en la instancia, la carpeta del ticket, el `.code-workspace` si le suma el worktree, y el commit de eso (paso 8). La excepción es un repo con `"own": true` en `workspace.config.json`, que es del usuario: ahí la skill corre ella misma el `fetch` y crea el worktree (paso 6). Ni ahí commitea ni hace push.
4. **No hay contrato con el tracker.** Si esta sesión tiene una herramienta (MCP) del tracker del usuario, se usa para leer el pedido; si no, el usuario lo pega.
5. **Cuando el glob de un id encuentra más de una carpeta, las listás y preguntás.** Nunca elegís una vos. Con ids que llevan guion, la carpeta de `AB-CD-x` también aparece en el glob del id `AB`.

## 1. El pedido

- Si la sesión tiene una herramienta del tracker del usuario, usala para leer el work item (título, descripción, criterios, enlaces). Mostrá lo que leíste.
- Si no la tiene, pedile al usuario que pegue el pedido y su id. No inventes ni completes datos que no vengan en él.
- **Si el usuario no usa un tracker**, no le pidas el id: proponé el siguiente con `python3 "<S>/ticket.py" --siguiente`, que busca en `tickets/` (archivados incluidos) el número más alto del prefijo de `tickets.prefix` y sale con `siguiente: <id>`. Si sale con 1 porque la config no fija el prefijo, proponé uno corto y pasáselo (`ticket.py --siguiente <prefijo>`); para no volver a preguntarlo, sugerí fijarlo en `workspace.config.json` como `"tickets": {"prefix": "<prefijo>"}`.
- Anotá el enlace o la referencia del pedido: va al ticket como `Fuente:`.

## 2. El id, el slug y la carpeta

1. **Buscá si el id ya tiene carpeta.** El glob es recursivo, porque un ticket archivado puede estar en una subcarpeta, y la herramienta Glob lista archivos, no carpetas: usá `tickets/**/<id>-*/CLAUDE.md`.
   - **Ninguna:** seguí.
   - **Una:** el ticket ya existe. Mostrá la ruta y preguntá si querés retomarlo; esta skill no vuelve a llenar un ticket que ya tiene contenido. Si lo retoma, marcalo como el ticket activo: `python3 "<S>/ticket.py" --activar <id>`.
   - **Más de una:** listalas todas y preguntá cuál es. No elijas.
2. **Proponé el slug:** kebab-case, en minúsculas, derivado del título (por ejemplo, `lector-de-codigo`). Los ids válidos llevan letras, números, guion y guion bajo.
3. **Ensayo:** no escribe nada. Mostrá su salida tal cual.

   ```bash
   python3 "<S>/ticket.py" <id> <slug> --ensayo
   ```

   Lista lo que crearía (`crearía …`), el resumen (`ensayo: N se crearían, M ya existen, no se escribió nada`) y, al final, la línea `ticket: <ruta>`. Si dice `0 se crearían`, la carpeta ya está completa: pasá al caso «Una» de arriba. Si por stderr sale un aviso de que la plantilla no tiene `tickets/_plantilla/.claude/settings.json` (una instancia generada antes de que el ticket llevara su `settings.json`), una sesión abierta dentro del ticket no cargaría el plugin: completá la instancia con `/odd-ws:bootstrap` y volvé a correr `ticket.py` (en el ensayo y, después, en la corrida real).
4. **Pedí el sí** a la carpeta y su nombre. Con el sí, el mismo comando sin `--ensayo`:

   ```bash
   python3 "<S>/ticket.py" <id> <slug>
   ```

   Copia la plantilla entera sin pisar nada y termina con `ticket: <ruta>`: esa es la carpeta del ticket de ahora en adelante.
5. **Los códigos de salida:**
   - **0:** hecho.
   - **1:** el pedido no se puede cumplir, y el mensaje dice por qué. Un id con otra carpeta (nombra las que ya existen, archivadas incluidas): preguntale al usuario si es el mismo ticket o si el id está mal. Un id o un slug inválido: corregilo y volvé a mostrar el ensayo. Una plantilla ausente (`falta tickets/_plantilla/CLAUDE.md`): la instancia está incompleta, mandá al usuario a `/odd-ws:bootstrap`.
   - **2:** error de uso o de entorno. Sin instancia (`no hay workspace.config.json …`) o con la config rota: mandá al usuario a `/odd-ws:doctor`, que dice qué falta. Con un uso mal formado, corregí el comando.

## 3. Llenar el ticket

Con la carpeta creada, leé `<ticket>/CLAUDE.md` y armá el borrador de estas secciones **sin escribirlo todavía** (se escribe en el paso 8):

- **Cabecera:** el título (`# <id> — <título corto>`), `Estado: nuevo` y `Conocimiento: pendiente`.
- **Objetivo:** una frase, qué resuelve y para quién, más la línea `Fuente: <enlace o referencia del pedido>`.
- **Criterios de aceptación:** una casilla `- [ ]` por criterio, con las palabras del pedido. Si el pedido no trae criterios, no los inventes: dejá la pregunta.
- **Alcance y no-goals:** qué incluye y qué queda fuera. Un no-goal que se justifique con un conteo («N consumidores») lleva el comando y su salida, y eso lo corre el usuario si toca los repos del equipo.
- **Los «X o Y».** Recorré el pedido buscando alternativas («X **o** Y», «A / B», «según el caso»). Cada una va a una línea de Alcance:
  - `- **Por fijar con el líder (antes de codear):** <la alternativa tal cual viene en el pedido>`

  Mostrale al usuario cuántas encontraste. Ninguna se resuelve por tu cuenta ni se cuenta como incluida o excluida hasta que el líder la fije.

## 4. Los docs de dominio, por el índice

No leas todos los docs. Mapealos por el índice:

1. Leé la sección `knowledge` de `workspace.config.json`: `docs` es la carpeta de los docs de dominio y `index` es el índice (por defecto, el `CLAUDE.md` raíz).
2. Si no hay `knowledge.docs`, la instancia no declara docs de dominio: decilo y seguí.
3. Si lo hay, listá la carpeta con Glob (`<docs>/*.md`), leé el índice y elegí por su descripción los docs que este ticket toca. Abrí un doc solo si el índice no alcanza para decidir.
4. Mostrá la lista: `<doc> — <por qué lo toca>`. Un doc que el índice no enlaza se avisa, pero no se descarta.

La lista va en «Contexto técnico» del ticket: `Docs de dominio: <doc> — <razón>, …`.

## 5. Candidatos de los tickets hermanos

Los candidatos a graduar de otros tickets pueden aplicar a este antes de que alguien los gradúe.

1. Buscá la sección en todos los tickets. El glob es recursivo y la plantilla y el ticket nuevo no cuentan:

   `Grep`, patrón `^## Candidatos a graduar`, path `tickets`, glob `**/CLAUDE.md`, con `-A 12`.

2. Ignorá el `_plantilla`, este ticket y la línea de ejemplo (`- <hallazgo general> → <doc destino o la raíz>`). Si la sección de un ticket sigue después de las 12 líneas, leé ese `CLAUDE.md`.
3. De los candidatos que quedan, elegí los que tocan este ticket (el mismo tema, los mismos docs, la misma capa) y mostralos con su ticket de origen.
4. Van a «Contexto técnico»: `Candidatos de tickets hermanos: <hallazgo> (<id del ticket>) — <por qué aplica>`. **No** van a la sección «Candidatos a graduar» de este ticket: siguen siendo del ticket que los anotó, y copiarlos acá rompería la regla de que `graduado` exige esa sección vacía.

## 6. El worktree

Preguntale al usuario si el trabajo va en un **worktree** o en el **árbol principal** de cada repo que toca. Los comandos sobre los repos del equipo los corre él, no esta skill. Dale el comando exacto:

- **Worktree** (el árbol principal queda como está):

  ```bash
  git -C <repo> worktree add --no-track <ruta del worktree> -b <rama> <base>
  ```

- **Árbol principal** (cambia la rama del árbol del usuario, por eso se confirma):

  ```bash
  git -C <repo> switch --no-track -c <rama> <base>
  ```

La ruta de `<repo>` sale de `workspace.local.json` (`repos.<repo>.path`). Proponé la rama (por ejemplo, `feat/<id>-<slug>`), y preguntá por la `<base>`: la rama de integración del repo. Si el `origin` puede estar atrasado, proponé el `git fetch` de ese repo, que corre el usuario porque habla con el remoto. Si la rama ya existe, el comando falla y no pisa nada: se elige otro nombre o se retoma esa rama.

**En un repo con `"own": true`**, si el usuario eligió un worktree, no le pases los comandos: corré vos `git -C <repo> fetch` y después el `worktree add`, y mostrá lo que salió. Si eligió el árbol principal, pasale el `switch` como en cualquier repo, y que lo corra él: cambiar la rama de su árbol puede pisar trabajo sin commitear. Esta regla es de la skill: el guard de comandos solo protege los repos con `agent_readonly`, y un repo `own` no puede llevarlo. Si un comando falla, mostrá el error y no lo reintentes con otra forma.

**Si la raíz tiene un `.code-workspace`** (el usuario trabaja desde VS Code), sumá el worktree como carpeta, después de la raíz, con Edit y sin tocar el resto, y avisá que VS Code lo toma al recargar la ventana. Así la sesión de la raíz puede editarlo sin pedir permiso.

La respuesta va a «Contexto técnico», en `Worktree y rama:`: la ruta y la rama, o «árbol principal» y la rama.

## 7. El Paso 0 de diseño

Recordalo y dejalo escrito en el ticket **antes de cualquier código**: para cada dato nuevo, el **hermano vigente** (qué existente ya resuelve algo igual) y su **consumidor** (quién lo lee en este flujo). Si todavía no se sabe, la línea queda como:

`Paso 0 de diseño: pendiente: hermano vigente y consumidor de cada dato nuevo, antes de escribir código.`

No lo llenes con suposiciones: se completa cuando se exploran los repos, y el revisor de diseño lo usa como entrada.

## 8. Mostrar, escribir y cerrar

1. **Mostrá todo lo que se va a escribir**, junto, antes de tocar el archivo: la cabecera, el Objetivo, los criterios, el Alcance con sus preguntas por fijar, y el Contexto técnico con los repos y capas afectados (si el pedido los dice; si no, quedan como pregunta), los docs de dominio, los candidatos hermanos, el worktree y el Paso 0. Marcá lo que quedó pendiente.
   - **La cobertura de capas.** Corré `python3 "<S>/ticket.py" --cobertura`, que hace la misma cuenta que el ítem `capas-cobertura` del doctor sobre toda la instancia, porque todavía no hay diff. Si sale `aviso capas-cobertura: …`, mostralo tal cual, con su línea `cómo:`, junto a las capas afectadas: un cambio del ticket en esos archivos lleva `/odd-ws:revisar` a modo `completo`. Si sale `capas-cobertura: todo lo versionado …`, no hace falta decir nada.
   - **Si el ticket es grande** (no cabe en una sesión, espera algo externo o trae entregas separadas), sumá sus `## Specs`, con cada S# citando el pedido tal cual, y sus `## Tareas`. Con gentle-ai, ese ticket es el documento de ODD: no se crea `odd/tasks/`, y el espejo en engram va en `odd/<id>/tasks`.
   - **Si es chico**, decí que vas a quitar esas dos secciones.
2. **Pedí el sí.** Sin sí, no se escribe nada. Si el usuario corrige algo, ajustá y volvé a mostrar.
3. **Con el sí**, editá `<ticket>/CLAUDE.md` con Edit, sección por sección, sin tocar las demás (Seguimientos, Decisiones, Gotchas, Candidatos a graduar y Cierre quedan como los trae la plantilla). En un ticket chico, quitá `## Specs` y `## Tareas`; `## Seguimientos` queda, porque ahí van los hallazgos que una revisión derivó y los pendientes, también en un ticket chico. La primera entrada de la bitácora lleva el pedido tal cual, porque la bitácora hace de Log: `<fecha> — el pedido, tal cual: «<…>»; abierto desde <fuente>; preguntas por fijar: <n>`.
4. **Commiteá el ticket en la raíz de la instancia**, sin volver a preguntar: el sí del paso 2 ya lo cubre, y en la instancia el agente commitea sin pedir aprobación. Solo si `workspace.config.json` dice `"ask_before_commit": true`, pedí el sí antes. Así el ticket tiene historia desde el primer día, y el commit de `cerrar` no se lleva todo de una vez: en un ticket real, el cierre barrió 151 archivos. `git add` explícito, nunca `-A`: la carpeta del ticket y, si este `abrir` le sumó el worktree, el `.code-workspace`. Nunca hagas push.

   ```bash
   git add -- ':/<ticket>' [':/<archivo>.code-workspace']
   git commit -m "chore(<id>): abre el ticket"
   ```

   Si el pre-commit de la instancia falla, mostrá su salida: no lo saltees con `--no-verify`.
5. **Decí qué quedó escrito** y qué sigue:
   - las dos formas de trabajar el ticket, con las rutas reales:
     - **desde su carpeta**, con `claude --add-dir <ruta>` por cada repo o worktree de «Worktree y rama». Sin eso, Claude Code pide permiso para leer o editar fuera de la carpeta del ticket;
     - **desde la raíz**, que es lo cómodo en VS Code: `ticket.py` ya lo dejó como ticket activo, así que un resumen de su `CLAUDE.md` (objetivo, specs, tareas, seguimientos y la bitácora reciente) llega al arrancar y después de cada `/compact`;
   - las preguntas por fijar con el líder, que van primero;
   - el Paso 0, antes de cualquier código;
   - `/odd-ws:revisar` antes de cada commit, y antes de mostrarle el cambio a un líder. Si `--cobertura` avisó extensiones sin capa, repetí el aviso: un cambio en esos archivos sube la revisión a `completo` hasta que su capa se declare;
   - `/odd-ws:cerrar` al terminar, para graduar lo aprendido.

## Scripts

| Script | Para qué | Salidas |
|---|---|---|
| `ticket.py` | crea `tickets/<id>-<slug>/` desde la plantilla sin pisar nada; `--ensayo` solo muestra | 0 ok · 1 pedido rechazado (conflicto, id o slug inválido, plantilla ausente) · 2 error de uso o de entorno |
| `ticket.py --activar <id>` | marca como activo el ticket de ese id, que la sesión de la raíz recibe al arrancar y tras cada `/compact`; crear un ticket ya lo marca | 0 `ticket activo: <carpeta>` · 1 sin carpeta, con varias o id inválido · 2 error de uso o de entorno |
| `ticket.py --desactivar <id>` | quita la marca si es de ese ticket | 0 `sin ticket activo` o `ticket activo: <carpeta> (no es el <id>)` · 2 error de uso o de entorno |
| `ticket.py --siguiente [<prefijo>]` | propone el siguiente id consecutivo, con el prefijo de `tickets.prefix` o el que se le pasa; no escribe nada | 0 `siguiente: <id>` · 1 sin prefijo o prefijo inválido · 2 error de uso, sin instancia o config rota |
| `ticket.py --cobertura` | repite el aviso `capas-cobertura` del doctor: cuenta por extensión lo versionado en los repos que ninguna capa clasifica, sin los docs; solo lee | 0 `aviso capas-cobertura: …` y su `cómo:`, o `capas-cobertura: todo lo versionado en los repos tiene capa o es doc` · 2 error de uso, sin instancia o config rota |
| `ticket.py --enlaces <id \| ruta a un .md> [--copiar]` | lista los enlaces del `CLAUDE.md` del ticket, o de cualquier `.md`, con su ruta absoluta y si es archivo o carpeta; los rotos y los de esquema van aparte. `--copiar` manda además las rutas al portapapeles. Solo lee y no abre nada: si el usuario quiere abrir uno, en la terminal de VS Code una ruta absoluta se abre con Ctrl+clic | 0 `enlaces de <documento>: <n>` y la lista, aunque haya rotos (sin portapapeles avisa por stderr y la lista sale igual) · 1 id sin carpeta, con varias o sin `CLAUDE.md`, una ruta que no es un `.md` o `--raiz` con una ruta · 2 error de uso, o con un id, sin instancia o config rota |
