# Experiencia de uso (R4, `0.9.0`)

Objetivo: que el primer uso de odd-ws, de la instalación al cierre de un ticket, no pida pasos a mano ni preguntas que el agente puede resolver solo. Sale como `0.9.0`.
Rama: `feat/experiencia-de-uso`, desde `fix/capa-por-shell` (lleva la `0.8.0`, todavía sin publicar). Entrega: una rama con un commit por unidad; el push a main y la etiqueta, solo con autorización, según «Una entrega» de `CONTRIBUTING.md`.
Pruebas: `python3 plugin/scripts/<x>.tests.py`, todas con el bucle de `CONTRIBUTING.md`, y `node --test plugin/shim/*.test.ts`.

## Specs

Cada spec cita al autor tal cual. La definición de cada mejora es la fila de su idea en [roadmap](../roadmap.md#ideas), aprobada por el autor; lo que no sale de una cita va marcado como supuesto.

- **S1. El alcance de la versión.** «La verdad quiero que la proximo que vamos a trabajar sea esto este tipo de cosas que estamos observando de experiencia de usuario se podria decir, cuando terminemos de analizar todo el proceso intentamos abarcar todos estos puntos para la proxima version» y «cualquier cosa en el trayecto te voy informando mas si agregamos mas cosas a esta version». Alcance: las ideas I7 a I16 del roadmap; lo que se sume en el trayecto entra como un S# nuevo, con su cita.
- **S2. El hook en LF (I9).** Entra por S1. El bootstrap crea un `.gitattributes` con `.githooks/* text eol=lf`, y el doctor revisa que el hook de una instancia que ya existe esté cubierto. Criterio: en una instancia nueva, `git ls-files --eol .githooks/pre-commit` muestra `attr/text eol=lf`. Supuesto: si el `.gitattributes` ya existe y le falta la línea, se avisa como hoy se avisa lo que falta en `.gitignore`, sin reescribirlo.
- **S3. La autoridad según de quién es el repo (I10).** «Tengo una pregunta si los commits deberia hacerlo la IA, si es la instancia no deberia haber problemas de hacerlo solo sin autorizacion a menos que lo exija el usuario», «Si me parece bien que commitear sea lo normal» y, sobre el worktree de un repo propio, «Eso lo puedes hacer tu». En la instancia el agente commitea sin preguntar (el primer commit del bootstrap y el commit de `cerrar`), con `git add` solo por ruta explícita y nunca push. Un interruptor en `workspace.config.json` vuelve a pedir aprobación. En un repo de código marcado como propio, `abrir` crea el worktree él mismo. Los repos del equipo siguen de solo lectura. El primer commit del bootstrap marca el hook como ejecutable (`git add --chmod=+x .githooks/pre-commit`). Criterio: en una instancia nueva, `git ls-files -s .githooks/pre-commit` empieza con `100755`, también en Windows.
- **S4. El bootstrap en una parada (I8).** «Asi estoy implementando el odd-ws el bootstrap, pero estaba pensando que deberiamos mejorar la experiencia del usuario cuando use esta skill, para que lo analicemos como mejora» y «Si me parece bien». Una propuesta completa junto con el ensayo, y un sí la aplica. `bootstrap.py --proponer` lee el `.code-workspace`, cuenta las extensiones con `git ls-files` y propone `knowledge.docs` si el repo tiene una carpeta de docs. La skill trae el criterio de capas, una por tecnología y con su costo real según `revisar`, y el ensayo se muestra como un resumen agrupado. La propuesta explica en una línea cada término que muestra, como `rule_prefix` y el molde (`repo` o `propio`).
- **S5. El siguiente paso al cerrar el bootstrap (I11).** «Ejemplo aca no se que hacer». El bootstrap cierra con abrir el primer ticket con `/odd-ws:abrir`, y menciona los atajos `/odd-ws:cerrar memorias` y `/odd-ws:paquetes`.
- **S6. El id del ticket sin tracker (I12).** «Sí, usemos SM-1 y asi sucesivamente ya que no manejamos boards o metodologia scrum ya que es solo soy 1 solo desarrollador». Sin tracker, `abrir` propone el siguiente id consecutivo con un prefijo fijado en el bootstrap.
- **S7. La sesión del ticket (I7 e I13).** «Otra cosa yo puedo trabajar desde esa sesion, no estar obligado a entrar a esa ruta cierto» y «Eso no seria un area de mejora de nosotros tambien?». `abrir` anota el ticket activo en `.claude/estado/`, y el hook de inicio inyecta su `CLAUDE.md` cuando la sesión corre en la raíz, al arrancar y después de cada `/compact`, en los tres CLI. Si hay un `.code-workspace`, `abrir` le agrega el worktree. El cierre de `abrir` explica las dos formas de trabajar el ticket: desde su carpeta con `--add-dir`, o desde la raíz.
- **S8. Las memorias de los repos (I14).** Entra por S1. `cerrar memorias` también lee las memorias de los repos de la config, en archivos y en engram.
- **S9. El ticket como documento de ODD (I15).** «Encontre un problema que es muy cierto sobre ODD de gentle-ia y odd-ws» y «Vale me parece bien». La plantilla del ticket suma `## Specs` y `## Tareas` opcionales para las tareas grandes, la Bitácora hace de Log con el pedido textual en L1, y se fija la clave del espejo en engram. La regla «el ticket es el documento de la feature» sube de lugar en el `CLAUDE.md`, o la recuerda `abrir`.
- **S10. El arranque en frío de las reglas (I16).** Entra por S1. Supuesto: primero un estudio acotado decide cómo sembrar las capas con lo que el repo ya sabe (su `CLAUDE.md`, sus gotchas, sus docs), porque la idea todavía no tiene mecanismo; el estudio vuelve al autor antes de implementar.

## Tareas

Todas van inline: no hay unidades paralelas lanzadas juntas ni otra razón de writer. Si dos unidades independientes se lanzan en paralelo, se anota acá.

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T1 | S2 | `.gitattributes` del bootstrap y chequeo del doctor | inline | hecho | `b49732b` |
| T2 | S9 | Plantilla del ticket compatible con ODD | inline | hecho | `6d34d60` |
| T3 | S6 | Id consecutivo sin tracker | inline | hecho | el commit que suma L10 |
| T4 | S3 | Autoridad según de quién es el repo | inline | pendiente | |
| T5 | S4, S5 | Bootstrap en una parada y su cierre | inline | pendiente | |
| T6 | S7 | Ticket activo y sesión del ticket | inline | pendiente | |
| T7 | S8 | Memorias de los repos | inline | pendiente | |
| T8 | S10 | Estudio del arranque en frío | inline, solo lectura | pendiente | |
| T9 | S1 | Entrega de la `0.9.0` | inline | pendiente | |

## Log

- **L1 (2026-11-17), el pedido del autor:** «Entonces empezamos a trabajar para esta nueva version que ya tenemos con que trabajar mientras, organiza todo lo que haremos para esta nueva version e iniciamos y cualquier cosa en el trayecto te voy informando mas si agregamos mas cosas a esta version»
- **L2 (2026-11-17), de dónde sale:** de leer una sesión real en otra instancia: el bootstrap tomó 20 minutos, 9 de ellos en arreglar el primer commit, y la apertura del primer ticket mostró el resto. Las ideas I7 a I16 del roadmap guardan la evidencia de cada una.
- **L3 (2026-11-17), el mapa del código:** un explorador de solo lectura encontró cinco restricciones que mandan sobre las tareas:
  1. `bootstrap.informe()` lo comparten `bootstrap.py` y `ticket.py`, y varios tests fijan sus líneas exactas.
  2. El hook de inicio solo inyecta texto con la config rota, y un test fija que una config sana calla (`verificar_capa.tests.py`).
  3. `odd_ws.comun.id_valido` también valida los ids de sesión y de agente en los hooks, y es API pública: T3 no lo cambia.
  4. `config_loader.py` es el único esquema de la config. Valida `repos.<repo>.agent_readonly` y deja pasar las otras claves de cada repo.
  5. La plantilla del ticket y el `CLAUDE.md` tienen tests que fijan sus secciones y su largo (entre 60 y 200 líneas).
- **L4 (2026-11-17), la entrega:** el pronóstico es de unas 1500 a 2000 líneas, en commits de una unidad cada uno, en una sola rama, como la `0.8.0`.
- **L5 (2026-11-17), lo siguiente:** T1.
- **L6 (2026-11-17), T1 hecho.** El bootstrap genera `.gitattributes` con `.githooks/* text eol=lf`, junto al `pre-commit`, y el doctor suma `instancia-eol`. Ese chequeo pregunta a `git check-attr`, así que también reconoce una regla más amplia como `* text=auto eol=lf`. Si falta, da AVISO con un arreglo que agrega la línea sin tocar el resto.
  - Rojo: doctor 182/189, bootstrap_instalacion 11/13 y bootstrap_cli 14/19.
  - Verde: doctor 189/189, bootstrap_instalacion 13/13, bootstrap_cli 19/19, bootstrap 158/158 y bootstrap_e2e 14/14. El e2e comprueba con `git check-attr` que en una instancia nueva el hook queda con `text: set` y `eol: lf`.
  - Docs: `Doc/diseno.md`, `Doc/uso.md`, `Doc/equipo.md` y la skill del doctor.
  - Risk: none. Suma un archivo generado y un chequeo AVISO, y los e2e corren el `pre-commit` y el primer commit de una instancia nueva.
- **L7 (2026-11-17), lo siguiente:** T2.
- **L8 (2026-11-17), T2 hecho.** La plantilla del ticket suma `## Specs` y `## Tareas`, que solo se usan en un ticket grande; en uno chico, `abrir` las quita. La Bitácora hace de Log, con el pedido tal cual en su primera entrada. El `CLAUDE.md` de la instancia dice en el paso 3 del ciclo que, con gentle-ai, el ticket es el documento de ODD, en vez de decirlo recién en la línea 115, y fija el espejo en engram en `odd/<id>/tasks`.
  - Rojo: bootstrap_textos 21/25.
  - Verde: bootstrap_textos 25/25, ticket 28/28, bootstrap 158/158 y bootstrap_e2e 14/14.
  - Docs: `Doc/diseno.md` («Abrir» y el largo del `CLAUDE.md`), `Doc/uso.md` y la skill `abrir`.
  - Para T9: una instancia que ya existe conserva su plantilla vieja, porque el bootstrap no pisa archivos. El CHANGELOG tiene que decir cómo traer la nueva.
  - Risk: none. Suma secciones a dos plantillas y no cambia ninguna instancia existente.
- **L9 (2026-11-17), lo siguiente:** T3.
- **L10 (2026-11-17), T3 hecho.** `ticket.py --siguiente [<prefijo>]` propone el siguiente id consecutivo: cuenta los tickets archivados y los anidados, y no lee la plantilla. El prefijo sale del argumento o de la clave opcional `tickets` de la config (`"tickets": {"prefix": "T"}`). La valida `config_loader.prefijo_de_tickets` igual que `hosts`: `cargar` no la mira, el bootstrap la valida antes de escribir y el doctor la marca en `config`. El prefijo no lleva guion, para no chocar con el límite de los ids con guion.
  - Rojo: config_loader 83/86, ticket 26/34, bootstrap 158/159 y doctor 189/190.
  - Verde: config_loader 86/86, ticket 34/34, bootstrap 159/159, doctor 190/190, bootstrap_cli 19/19 y bootstrap_e2e 14/14.
  - Docs: `Doc/diseno.md` («Tickets»), `Doc/uso.md` y las skills `abrir` y `bootstrap`.
  - Risk: none. Suma un comando y una clave opcional. La línea de uso de `ticket.py` cambia porque suma el comando nuevo, y su test lo fija.
- **L11 (2026-11-17), dos precisiones a S3 y S4.** Las trajo otra sesión que leyó este documento, y el autor preguntó: «Que opinas de esta observacion si ya estaba abarcada». S4 suma que la propuesta explica sus términos (`rule_prefix` y el molde). S3 deja escrito como criterio que el primer commit marca el hook como ejecutable; ya estaba en la idea I10 del roadmap, pero no en el spec.
- **L12 (2026-11-17), lo siguiente:** T4.
