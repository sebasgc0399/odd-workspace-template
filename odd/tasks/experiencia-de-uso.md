# Experiencia de uso (R4, `0.9.0`)

Objetivo: que el primer uso de odd-ws, de la instalación al cierre de un ticket, no pida pasos a mano ni preguntas que el agente puede resolver solo. Sale como `0.9.0`.
Rama: `feat/experiencia-de-uso`, desde `fix/capa-por-shell` (lleva la `0.8.0`, todavía sin publicar). Entrega: una rama con un commit por unidad; el push a main y la etiqueta, solo con autorización, según «Una entrega» de `CONTRIBUTING.md`.
Pruebas: `python3 plugin/scripts/<x>.tests.py`, todas con el bucle de `CONTRIBUTING.md`, y `node --test plugin/shim/*.test.ts`.

## Specs

Cada spec cita al autor tal cual. La definición de cada mejora es la fila de su idea en [roadmap](../roadmap.md#ideas), aprobada por el autor; lo que no sale de una cita va marcado como supuesto.

- **S1. El alcance de la versión.** «La verdad quiero que la proximo que vamos a trabajar sea esto este tipo de cosas que estamos observando de experiencia de usuario se podria decir, cuando terminemos de analizar todo el proceso intentamos abarcar todos estos puntos para la proxima version» y «cualquier cosa en el trayecto te voy informando mas si agregamos mas cosas a esta version». Alcance: las ideas I7 a I16 del roadmap; lo que se sume en el trayecto entra como un S# nuevo, con su cita.
- **S2. El hook en LF (I9).** Entra por S1. El bootstrap crea un `.gitattributes` con `.githooks/* text eol=lf`, y el doctor revisa que el hook de una instancia que ya existe esté cubierto. Criterio: en una instancia nueva, `git ls-files --eol .githooks/pre-commit` muestra `attr/text eol=lf`. Supuesto: si el `.gitattributes` ya existe y le falta la línea, se avisa como hoy se avisa lo que falta en `.gitignore`, sin reescribirlo.
- **S3. La autoridad según de quién es el repo (I10).** «Tengo una pregunta si los commits deberia hacerlo la IA, si es la instancia no deberia haber problemas de hacerlo solo sin autorizacion a menos que lo exija el usuario», «Si me parece bien que commitear sea lo normal» y, sobre el worktree de un repo propio, «Eso lo puedes hacer tu». En la instancia el agente commitea sin preguntar (el primer commit del bootstrap y el commit de `cerrar`), con `git add` solo por ruta explícita y nunca push. Un interruptor en `workspace.config.json` vuelve a pedir aprobación. En un repo de código marcado como propio, `abrir` crea el worktree él mismo. Los repos del equipo siguen de solo lectura. El primer commit del bootstrap marca el hook como ejecutable (`git add --chmod=+x .githooks/pre-commit`). Criterio: en una instancia nueva, `git ls-files -s .githooks/pre-commit` empieza con `100755`, también en Windows.
- **S4. El bootstrap en una parada (I8).** «Asi estoy implementando el odd-ws el bootstrap, pero estaba pensando que deberiamos mejorar la experiencia del usuario cuando use esta skill, para que lo analicemos como mejora» y «Si me parece bien». Una propuesta completa junto con el ensayo, y un sí la aplica. `bootstrap.py --proponer` lee el `.code-workspace` y cuenta las extensiones con `git ls-files`. No propone `knowledge.docs`: esa ruta vive dentro de la instancia y no puede apuntar a un repo de código (L17). La skill trae el criterio de capas, una por tecnología y con su costo real según `revisar`, y el ensayo se muestra como un resumen agrupado. La propuesta explica en una línea cada término que muestra, como `rule_prefix` y el molde (`repo` o `propio`).
- **S5. El siguiente paso al cerrar el bootstrap (I11).** «Ejemplo aca no se que hacer». El bootstrap cierra con abrir el primer ticket con `/odd-ws:abrir`, y menciona los atajos `/odd-ws:cerrar memorias` y `/odd-ws:paquetes`.
- **S6. El id del ticket sin tracker (I12).** «Sí, usemos SM-1 y asi sucesivamente ya que no manejamos boards o metodologia scrum ya que es solo soy 1 solo desarrollador». Sin tracker, `abrir` propone el siguiente id consecutivo con un prefijo fijado en el bootstrap.
- **S7. La sesión del ticket (I7 e I13).** «Otra cosa yo puedo trabajar desde esa sesion, no estar obligado a entrar a esa ruta cierto» y «Eso no seria un area de mejora de nosotros tambien?». `abrir` anota el ticket activo en `.claude/estado/`, y el hook de inicio inyecta su `CLAUDE.md` cuando la sesión corre en la raíz, al arrancar y después de cada `/compact`, en los tres CLI. Si hay un `.code-workspace`, `abrir` le agrega el worktree. El cierre de `abrir` explica las dos formas de trabajar el ticket: desde su carpeta con `--add-dir`, o desde la raíz.
- **S8. Las memorias de los repos (I14).** Entra por S1. `cerrar memorias` también lee las memorias de los repos de la config, en archivos y en engram.
- **S9. El ticket como documento de ODD (I15).** «Encontre un problema que es muy cierto sobre ODD de gentle-ia y odd-ws» y «Vale me parece bien». La plantilla del ticket suma `## Specs` y `## Tareas` opcionales para las tareas grandes, la Bitácora hace de Log con el pedido textual en L1, y se fija la clave del espejo en engram. La regla «el ticket es el documento de la feature» sube de lugar en el `CLAUDE.md`, o la recuerda `abrir`.
- **S10. El arranque en frío de las reglas (I16).** Entra por S1. Supuesto: primero un estudio acotado decide cómo sembrar las capas con lo que el repo ya sabe (su `CLAUDE.md`, sus gotchas, sus docs), porque la idea todavía no tiene mecanismo; el estudio vuelve al autor antes de implementar. Resuelto con «si» a la opción C (L25): un ticket de siembra que sugiere el cierre del bootstrap, sin código nuevo.
- **S11. Las rondas de una revisión (I19).** «Si quieres observa como va actualmente a ver que mas observas» y, sobre las tres fricciones de `revisar`, «Me parece bien analizadas 3 fricciones se van agregar en esta version? esas 3?». Una segunda revisión del mismo día y modo no pisa la primera: va en `revision/<fecha>-<modo>-<n>/`, y `recibo.py` la reconoce como la más nueva.
- **S12. Las extensiones de código sin capa (I18).** Las mismas citas que S11. El bootstrap propone cubrir los scripts del mismo lenguaje (por ejemplo, `.mjs` en una capa `ts`), y el doctor avisa cuando un repo tiene extensiones de código que ninguna capa cubre, porque esos archivos llevan el triaje a modo `completo`.
- **S13. La base de la revisión de una unidad (I20).** Las mismas citas que S11. Cuando el ticket ya tiene un recibo válido, la base por defecto del triaje es el commit que ese recibo cubrió, y no el merge-base con `origin/HEAD`, para no volver a revisar unidades ya revisadas. Cambia qué se revisa por defecto: lleva verificador independiente.
- **S14. El rechequeo después de una corrección (I23).** «Cunato termines T12 analiza la sesion a ver que otras mejoras podemos encontrar» y, sobre la lista de lo encontrado, «Me parece bien». Una ronda de rechequeo revisa solo lo que cambió desde la ronda anterior, y su recibo hereda del recibo anterior válido los hashes de los archivos que no cambiaron (`recibo.py --write --previo <recibo>`), para que la unidad entera se pueda sellar. Hoy la re-revisión vuelve a revisar toda la unidad y cuesta lo mismo que la primera, y una re-revisión parcial no se puede sellar.
- **S15. Cómo se cierra una revisión (I24).** Las mismas citas que S14. `revisar` trae una regla de cierre: una sola corrección, después un rechequeo que verifica los hallazgos anteriores, y un hallazgo nuevo que no es CRITICAL se deriva a otra tarea en vez de corregirse en esa unidad. El recibo anota los hallazgos derivados con su destino (`--derivado <hallazgo>=<destino>`), y la plantilla del ticket suma `## Seguimientos`, para que lo derivado no rompa la tabla de Tareas.
- **S16. Menos síes en `revisar` (I25).** Las mismas citas que S14. El modo 0, que cuesta cero corridas, corre sin pedir el sí. Aprobar un lote de corrección cuyo mensaje anuncia el rechequeo y su costo aprueba también ese rechequeo.
- **S17. El resumen del ticket activo (I26).** Las mismas citas que S14. Lo que T6 inyecta deja de ser un recorte a 12000 caracteres, que en un ticket real de 30600 caracteres cortaba `## Tareas` a la mitad, y pasa a ser un resumen: la cabecera, el Objetivo, los S#, la tabla de Tareas entera, los Seguimientos y las últimas entradas de la Bitácora, con la ruta del archivo completo. Si aun así pasa el tope, se recorta con la línea de dónde sigue.
- **S18. Los scratch donde se pueden borrar (I27).** Las mismas citas que S14. Las skills y las plantillas que sugieren «el temp del sistema» para el scratch dicen `%TEMP%\claude` (o el scratch de la sesión), porque fuera de ahí el guard no deja borrar con `rm -rf` y la limpieza le queda al usuario.
- **S19. Los archivos generados sin trackear (I30).** «Pues si quieres revisa la sesion a ver que mas puedes observar como mejora» y, sobre la lista de lo encontrado (G1, G3, G5 y G7 a la versión, el resto como ideas), «Vale me parece bien». El triaje deja fuera de la unidad los archivos sin trackear que genera una herramienta (`__pycache__/`, `*.pyc`, `*.pyo`) y los nombra aparte, para que no vuelvan inválida la señal de consumidores ni lleven el modo a `completo`. Supuesto: la lista de patrones es fija; ampliarla por config queda fuera.
- **S20. El costo de un rechequeo (I31).** Las mismas citas que S19. Un rechequeo corre una corrida de `revisor-diseno` más la de cada capa de los rechequeados, tanto en `rapido` como en `completo`, y cero en modo 0. Corrige la regla de T13, que en `completo` pedía `3 + <capas>`.
- **S21. El idioma después de un `/compact` (I32).** Las mismas citas que S19. El `CLAUDE.md` de la instancia dice que la conversación sigue en el idioma en que escribe el usuario, también después de un `/compact` cuyo resumen quedó en otro idioma. Supuesto: una línea en la plantilla alcanza, porque ese `CLAUDE.md` se vuelve a cargar después de compactar.
- **S22. Lo ya decidido no se vuelve a plantear (I33).** Las mismas citas que S19. El prompt de cada corrida de `revisar` suma las decisiones del ticket (`## Decisiones`) como lo que no se vuelve a plantear. Supuesto: un hallazgo CRITICAL que contradice una decisión se reporta igual, nombrando la decisión.
- **S23. Los rituales los escribe el usuario (I39).** «Listo haz la ultima revision que ya hice el cierre del primer ticket» y, sobre la lista de lo encontrado (H1, H4, H5 y que `abrir` commitee el ticket a la versión, el resto como ideas), «Vale». El `CLAUDE.md` de la instancia dice que los rituales (`abrir`, `cerrar`, `bootstrap`, `conocimiento`, `paquetes`) los escribe el usuario: el agente no ofrece lanzarlos y termina con la línea exacta que hay que escribir.
- **S24. La entrega después del cierre (I40).** Las mismas citas que S23. `cerrar` suma qué hacer cuando la entrega llega después del cierre: `Estado` pasa a `listo`, se actualiza lo que el ticket dice de la entrega, se commitea en la instancia y se quita la marca de ticket activo.
- **S25. El worktree de un repo propio lo desarma el agente (I41).** Las mismas citas que S23. En un repo marcado como propio (`own`), `cerrar` desarma el worktree él mismo (`worktree remove` y `prune`) si está limpio y su rama ya está en `origin`; si no, lo dice y se lo deja al usuario. En los repos del equipo, sigue siendo del usuario.
- **S26. `abrir` commitea el ticket (I42).** Las mismas citas que S23. `abrir` commitea la carpeta del ticket nuevo en la instancia, con `git add` por ruta y sin push, salvo `"ask_before_commit": true`, para que el estado del ticket tenga historia desde el primer día y el commit de `cerrar` no se lleve todo de una vez.

## Tareas

Todas van inline: no hay unidades paralelas lanzadas juntas ni otra razón de writer. Si dos unidades independientes se lanzan en paralelo, se anota acá.

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T1 | S2 | `.gitattributes` del bootstrap y chequeo del doctor | inline | hecho | `b49732b` |
| T2 | S9 | Plantilla del ticket compatible con ODD | inline | hecho | `6d34d60` |
| T3 | S6 | Id consecutivo sin tracker | inline | hecho | `5185e0d` |
| T4a | S3 | Las claves `ask_before_commit` y `own`, y el primer commit del bootstrap con el hook ejecutable | inline | hecho | `9798504` |
| T4b | S3 | `cerrar` commitea sin preguntar, `abrir` crea el worktree en un repo propio, y el `CLAUDE.md` de la instancia lo dice | inline | hecho | `c82376e` |
| T5 | S4, S5 | Bootstrap en una parada y su cierre | inline | hecho | `fd45a3c` |
| T6 | S7 | Ticket activo y sesión del ticket | inline | hecho | `2dac068` |
| T7 | S8 | Memorias de los repos | inline | hecho | `19d0f21` |
| T8 | S10 | Estudio del arranque en frío, y la opción C en textos | inline | hecho | `69f0b2c` |
| T10 | S11 | Las rondas de una revisión | inline | hecho | `c5735a5` |
| T11 | S12 | Las extensiones de código sin capa | inline | hecho | `87c64b3` |
| T12 | S13 | La base de la revisión de una unidad | delegada a un writer (razón de contexto), con verificador | hecho y verificado (junto con T13, L40) | `3aaf174` |
| T13 | S14, S15, S16 | El rechequeo, el cierre de una revisión y menos síes | writer A, en paralelo con T14 (superficies disjuntas) | hecho y verificado (junto con T12, L40) | `478a3e7`, corrección en el commit que suma L40 |
| T14 | S17 | El resumen del ticket activo | writer B, en paralelo con T13 | hecho | `7974a62` |
| T15 | S18 | Los scratch donde se pueden borrar | inline | hecho | `7974a62` |
| T16 | S19 | Los archivos generados sin trackear quedan fuera del triaje | inline | hecho | `3e6c06d` |
| T17 | S20 | El costo de un rechequeo | inline | hecho | `6d7088c` |
| T18 | S21 | El idioma después de un `/compact` | inline | hecho | `895a7ed` |
| T19 | S22 | Lo ya decidido no se vuelve a plantear | inline | hecho | `d95e0e7` |
| T20 | S23 | Los rituales los escribe el usuario | inline | hecho | `481e02a` |
| T21 | S24 | La entrega después del cierre | inline | hecho | el commit que suma L45, junto con T22 |
| T22 | S25 | El worktree de un repo propio lo desarma el agente | inline | hecho | el commit que suma L45, junto con T21 |
| T23 | S26 | `abrir` commitea el ticket | inline | hecho | `78f8887` |
| T9 | S1 | Entrega de la `0.9.0` | inline | hecho | el commit que suma L46, con la etiqueta `odd-ws--v0.9.0` |
| F1 | — | Seguimiento: `test_correr_el_plazo_corta_un_comando_que_no_alcanza_a_terminar` (`afirmaciones.tests.py`) es inestable en macOS: con un plazo de 0.001 s, el comando a veces termina antes del corte (L41) | aparte | anotado | |

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
- **L13 (2026-11-17), T4a hecho.** T4 se parte en dos commits: T4a es el script y la config, y T4b son las skills y la plantilla.
  - `bootstrap.py --commitear` hace el primer commit (`chore: crea la instancia con odd-ws`) solo con lo que creó esa corrida, sin lo ignorado, con `git add --chmod=+x .githooks/pre-commit` y sin push.
  - No commitea, y lo dice, en cuatro casos: con `ask_before_commit: true`, dentro de otro repo, sin repo, o con cambios stageados ajenos.
  - Un commit que falla queda informado en `commit: falló (…)`, con exit 0, como los otros pasos de git. Con `--commitear` el informe ya no agrega el aviso del `chmod`, porque el commit lo marca.
  - Las claves `ask_before_commit` y `repos.<repo>.own` se validan como `hosts`: `cargar` no las mira, y el bootstrap y el doctor sí. `own` no va con `agent_readonly`.
  - Rojo: config_loader 86/91, bootstrap 158/167 y doctor 190/191.
  - Verde: config_loader 91/91, bootstrap 167/167, bootstrap_e2e 14/14, bootstrap_cli 19/19, bootstrap_instalacion 13/13, ticket 34/34 y doctor 191/191. El e2e comprueba en una instancia nueva el hook en `100755`, todo lo generado menos `workspace.local.json`, y el árbol limpio.
  - Una regresión atrapada por un test existente: el plazo de `_git` quedaba fijo en la firma, y el test que lo cambia en tiempo de ejecución falló. Ahora se lee en cada llamada.
  - Un error de proceso: edité tests de T4a mientras corría el pre-commit de T3. Lo arreglé devolviendo los archivos a su versión del índice con `git show`, y el commit de T3 salió limpio.
  - Risk: item 2. Cambia lo que el agente hace sin preguntar. Lleva verificador independiente, que corre después de T4b sobre T4 completo.
- **L14 (2026-11-17), lo siguiente:** T4b.
- **L15 (2026-11-17), T4b hecho.**
  - `cerrar` ya no pide un segundo sí antes del commit, porque el sí de la propuesta lo cubre. Vale para el commit de cierre y para el del modo `memorias`. Con `ask_before_commit: true` lo pide, y nunca hace push.
  - `abrir`, en un repo con `"own": true`, corre él mismo el `fetch` y el `worktree add`. Solo el worktree, porque el guard de comandos ya frena `switch` y `checkout` en el árbol del usuario. Ni ahí commitea ni hace push.
  - El `CLAUDE.md` de la instancia dice las dos cosas en «Autoridad de commit».
  - Rojo: bootstrap_textos 25/26.
  - Verde: bootstrap_textos 26/26 y bootstrap_e2e 14/14. El `CLAUDE.md` queda en 144 líneas.
  - Docs: `Doc/uso.md`, `Doc/diseno.md` y las skills `abrir`, `cerrar` y `bootstrap`.
  - Risk: item 2, igual que T4a. Sigue el verificador independiente sobre T4 completo, con `5185e0d` como base.
- **L16 (2026-11-17), lo siguiente:** el verificador de T4 y después T5.
- **L17 (2026-11-17), T5 hecho, y S4 sin `knowledge.docs`.**
  - **`bootstrap.py --proponer`** no escribe nada e imprime un JSON con:
    - el nombre de la carpeta raíz como proyecto;
    - los repos git de los `.code-workspace`, sin la raíz y sin repetir, cada uno con su nombre corto, su ruta y sus extensiones, de la más usada a la menos;
    - los avisos: un workspace que no es JSON y una carpeta que no existe o no es raíz de un repo.
  - **La skill del bootstrap se reescribió para una sola parada.** Detecta, arma la propuesta completa con cada término explicado en una línea (`own`, el criterio y el costo de las capas, `rule_prefix`, el molde, el prefijo de los tickets y quién commitea), corre el ensayo en el mismo turno y lo muestra agrupado, con las líneas de atención aparte. Hace una sola pregunta y cierra con el siguiente paso (S5).
  - **S4 pierde `knowledge.docs`.** `config_loader._ruta_de_conocimiento` solo acepta rutas relativas a la instancia, sin `..` ni `:`, así que no puede apuntar a la carpeta de docs de un repo de código. Lo propuse sin verificarlo; se le avisa al autor.
  - **El ensayo agrupado lo arma la skill y no el script.** La salida de `informe()` la fijan tests y la comparte `ticket.py`.
  - Rojo: bootstrap 167/173.
  - Verde: bootstrap 173/173, bootstrap_cli 19/19, bootstrap_e2e 14/14, ticket 34/34 y bootstrap_textos 26/26.
  - Docs: `Doc/uso.md`, `Doc/diseno.md` y el README.
  - Risk: none. Es un comando nuevo de solo lectura y texto de una skill; la línea de uso suma una forma, y su test la fija.
- **L18 (2026-11-17), lo siguiente:** el veredicto del verificador de T4 y después T6.
- **L19 (2026-11-17), el verificador de T4 y su lote de corrección.**
  - **Lo que da por cumplido de S3:**
    - el commit sin preguntar en la instancia, con el hook en `100755` y sin `workspace.local.json`;
    - nunca push;
    - el interruptor `ask_before_commit`;
    - los repos del equipo de solo lectura, con las decisiones del guard idénticas a la base en 11 comandos y 5 configs;
    - el diferencial sin `--commitear`, idéntico salvo la línea de uso.
  - **Tres blockers, corregidos en un solo lote:**
    - **B1.** Con `--commitear`, en Windows se perdía el aviso del `chmod` también cuando el commit no se hacía. Ahora el aviso solo se calla si el commit se hizo, o si el ensayo dice que se haría.
    - **B2.** En un clon de la instancia, el bootstrap solo recrea `workspace.local.json`, que git ignora, y daba un `commit: falló` falso. Ahora dice `commit: no hace falta; lo que se creó lo ignora git`.
    - **B3.** Una afirmación falsa mía: escribí que el guard frena `switch` en un repo `own`, pero el guard solo protege los repos con `agent_readonly`. La regla es de la skill, y `abrir` y `Doc/diseno.md` lo dicen así.
  - **Avisos corregidos en el mismo lote:**
    - A1: el `git add` va con `--literal-pathspecs`. `check-ignore` no lo acepta, y ya toma rutas literales.
    - A4: la fila del modo `memorias` en `cerrar`.
    - A5: lo que ya venía modificado se marca en la propuesta del paso 4, y si aparece recién en el paso 9 se saca del índice.
    - A6: en un repo `own`, si el usuario elige el árbol principal, el `switch` lo corre él.
  - **Quedan como seguimiento:**
    - A2: en un worktree enlazado, el commit corre sin el pre-commit.
    - A3: al reintentar después de un commit fallido, el mensaje habla de cambios ajenos que en realidad son los suyos.
    - A7: el plazo de 600 s del commit, si un `gpgsign` o un hook lento lo traban.
  - **Rojo:** bootstrap 174/177. **Verde:** bootstrap 177/177, bootstrap_e2e 14/14 y bootstrap_cli 19/19.
  - **El scratch del verificador** (`tmp.0edGdN41al` en el temp del sistema) lo borra el autor a mano.
- **L20 (2026-11-17), lo siguiente:** la re-verificación limitada a B1, B2 y B3, y después T6.
- **L21 (2026-11-17), T4 cerrado y T6 hecho.**
  - **La re-verificación de `8f908a4` da los tres blockers corregidos**, y el CI está en verde.
    - B1: el aviso del `chmod` sigue en los cinco casos sin commit y falta solo cuando el commit se hace.
    - B2: el clon dice `no hace falta`.
    - B3: los textos ya no afirman que el guard frena el `switch`.
    - Aviso nuevo, como seguimiento: el ensayo no aplica el filtro de `check-ignore`, así que en un clon dice `se haría` donde la corrida real dice `no hace falta`. Es inofensivo, porque ahí no se crea el hook.
    - El autor borra a mano su scratch: `tmp.HRwVyUeq7p` en el temp del sistema.
  - **T6:**
    - `ticket.py` marca como activo el ticket que crea (no en el ensayo) en `.claude/estado/ticket-activo`, con `--activar <id>` y `--desactivar <id>` para cambiarlo y quitarlo.
    - `verificar_capa` inyecta en `SessionStart` (`startup`, `resume`, `compact` y `clear`) el `CLAUDE.md` del ticket activo, solo si la sesión corre en la raíz, recortado a 12000 caracteres. Llega a los tres CLI por los adaptadores que ya existían.
    - `abrir` marca el ticket que se retoma, suma el worktree al `.code-workspace` si la raíz tiene uno, y cierra con las dos formas de trabajar el ticket. `cerrar` quita la marca.
    - La plantilla del `CLAUDE.md` explica cómo se trabaja desde la raíz.
  - Rojo: ticket 31/38 y verificar_capa 88/91.
  - Verde: ticket 38/38, verificar_capa 91/91, bootstrap_textos 26/26, bootstrap_e2e 14/14, y los adaptadores y las capacidades. El `CLAUDE.md` queda en 148 líneas.
  - Docs: `Doc/diseno.md` («Primer toque» y «Tickets»), `Doc/uso.md` y las skills `abrir` y `cerrar`.
  - Risk: none. La inyección solo lee un archivo de la instancia y la valida (bajo `tickets/`, sin `..`, con su `CLAUDE.md`); sin marca, el inicio sigue callado, como fija el test de la config sana.
- **L22 (2026-11-17), lo siguiente:** T7.
- **L23 (2026-11-17), T7 hecho.**
  - `memorias.py --repo <nombre>` lee la memoria del proyecto de un repo de la config.
    - Su carpeta sale de la ruta del repo, sin el `CLAUDE_CODE_PROJECT_DIR_NAME` de la sesión, que nombra a la instancia.
    - Usa el registro local del proyecto del repo.
    - Solo cuenta como `graduada` lo que la matriz cita como `memoria:<repo>.<slug>`. El validador de la matriz ya aceptaba el punto.
    - No va junto con `--memorias`.
  - `cerrar memorias` corre `memorias.py` por cada repo y repite `mem_current_project` en engram con la ruta de cada repo.
  - Un cuidado: sumar `"repo": null` a la cobertura de siempre rompía dos tests que fijan el JSON exacto. Por eso la clave aparece solo con `--repo`, y la salida de siempre no cambia.
  - Rojo: memorias 34/38. Verde: memorias 38/38 y matriz 60/60.
  - Docs: `Doc/diseno.md` («Memorias»), `Doc/uso.md` y la skill `cerrar`, con `<repo>` sumado a los sustitutos del test que valida sus comandos.
  - Risk: none. Es una opción nueva de solo lectura, y la salida sin ella es la misma.
- **L24 (2026-11-17), lo siguiente:** T8, el estudio del arranque en frío, que vuelve al autor antes de implementarse.
- **L25 (2026-11-17), T8: el estudio y la decisión.**
  - **La restricción.** El origen de una fila de la matriz es `<ruta>@<hash>:<ini>-<fin>`, relativo a la instancia (`matriz.parsear_origen`), y `RE_RANGO` no admite `:` en la ruta. Un archivo de un repo de código no se puede citar directo.
  - **Tres opciones:**
    - A, un modo `cerrar repo` con un origen nuevo `repo:<repo>/<ruta>@<hash>`: trazabilidad exacta, a un costo medio-alto;
    - B, copiar el fragmento a un doc de la instancia y citarlo: duplica texto que se desactualiza;
    - C, un ticket de siembra con el `cerrar` de siempre: cero código.
  - **El autor eligió C:** «si».
  - **Lo que se hizo:** el paso 6 de la skill del bootstrap propone, si el repo ya tiene reglas escritas, que el primer ticket sea sembrarlas. Lo dicen también `Doc/uso.md` y `Doc/diseno.md`.
  - Si sembrar resulta frecuente, A queda como idea, con datos reales.
  - Sin tests, porque son textos de una skill y docs: se revisaron leyéndolos.
  - Risk: none.
- **L26 (2026-11-17), lo siguiente:** T9, la entrega de la `0.9.0`.
- **L27 (2026-11-17), tres fricciones de `revisar` vistas en SM-1, que entran a la versión.**
  - **I18.** T7 y T7b dieron modo `completo`, con 3 corridas cada vez, por scripts `.mjs` y un `package.json` que ninguna capa cubre. El triaje cuenta «sin capa» como señal positiva, y sin biblioteca de señales no puede contar los consumidores.
  - **I19.** La segunda revisión del mismo día y modo iba a pisar la primera, y el agente movió la primera a mano a `ronda-1/`. Además de nombrar la carpeta, `recibo.py` la lee (`CARPETA_RE`).
  - **I20.** Con el merge-base con `origin/HEAD` como base, el triaje contó 83 archivos en vez de los 21 de la unidad, y el agente pasó la base a mano.
  - **Descartado:** el `__pycache__` que apareció era de una skill del repo (`gotchas-search/reindex.py`), no de odd-ws.
  - La entrega (T9) se corre al final, para seguir observando SM-1 hasta su `cerrar`.
- **L28 (2026-11-17), lo siguiente:** T10.
- **L29 (2026-11-17), T10 hecho.**
  - `recibo.py --write --ronda <n>` escribe en `revision/<fecha>-<modo>-<n>/`; la ronda 1 queda sin sufijo, como siempre.
  - `CARPETA_RE` acepta el sufijo desde el 2.
  - `--check` sobre el ticket elige por fecha, después por modo y después por ronda, esta última comparada como número: la 10 le gana a la 2.
  - `--ronda` con `--check` es un error de uso.
  - La skill `revisar` usa la siguiente carpeta libre en vez de pisar o mover la anterior.
  - Rojo: recibo 56/58. Verde: recibo 58/58 y triaje 78/78 (`triaje.py` importa `recibo`, pero no usa la carpeta).
  - Docs: `Doc/diseno.md`, `Doc/uso.md` y la skill `revisar`.
  - Risk: none. Es una opción nueva, y sin ella la carpeta y la elección del recibo son las de siempre.
- **L30 (2026-11-17), lo siguiente:** T11.
- **L31 (2026-11-17), T11 hecho, y dos ideas nuevas fuera de la versión.**
  - **El chequeo `capas-cobertura`.** El doctor lista las extensiones versionadas de los repos que ninguna capa cubre, con su cantidad, hasta 8. Es AVISO sin arreglo.
    - La capa la decide `config_loader.clasificar`, la misma función del triaje, así que el doctor y el triaje no pueden discrepar.
    - Los docs no cuentan. `EXTENSIONES_DE_DOCS` es igual a `triaje.DOC_EXT`, y un test lo fija.
  - **El criterio de capas del bootstrap** dice que los scripts del mismo lenguaje van en la misma capa (`.js`, `.mjs` y `.cjs` en una capa `ts`). También pide nombrar en la propuesta las extensiones que quedan sin capa.
  - Rojo: doctor 189/195. Verde: doctor 195/195, bootstrap_instalacion 13/13, bootstrap_e2e 14/14 y triaje 78/78.
  - Docs: `Doc/diseno.md`, `Doc/uso.md` y las skills `doctor` y `bootstrap`.
  - Risk: none. Es un chequeo AVISO nuevo, y el resto del doctor no cambia.
  - **Al roadmap, como ideas nuevas para analizar con rigor:**
    - I21 hace efectiva la perilla `mold_source`. Es la premisa de los tres tipos de proyecto: D2 la deja como una etiqueta que nada consume.
    - I22 trata las reglas que cambian con el tiempo: cuál reemplaza a cuál, y la recalibración contra el código actual.
- **L32 (2026-11-17), lo siguiente:** T12, con verificador.
- **L33 (2026-11-17), T12 hecho por un writer.** Se delegó por el respaldo de contexto: la conversación del parent ya venía muy cargada.
  - **`recibo.py --sellar <ruta>`** anota en cada entrada del recibo `"sellado": <HEAD>`. Antes comprueba tres cosas, y si alguna falla sale con 1 sin tocar el recibo:
    - el recibo sigue valiendo;
    - lo revisado está commiteado;
    - `HEAD` no trae cambios fuera de lo revisado desde la base del recibo.
  - **`triaje.py --ticket <carpeta>`** elige la base de cada `--repo` sin `#base` en este orden: la explícita; el sello más nuevo, si es ancestro de `HEAD` y más nuevo que el merge-base; si no, el merge-base. La salida dice el origen: `base_origen` y `base_recibo` en el JSON, y la línea `repo` en el texto. Sin `--ticket`, la salida no cambia.
  - **La skill `revisar`** pasa `--ticket` al triaje y sella después de cada commit de una unidad revisada, también uno viejo que nadie selló.
  - **Decisiones del writer más allá del brief, aceptadas:**
    - el tercer chequeo del sello, sin el cual sellar después del commit de otra unidad la escondería de la revisión siguiente;
    - que el sello sea más nuevo que el merge-base, para no meter en el diff cambios publicados por otros.
  - Rojo: recibo 58/64 y triaje 79/87. Verde: recibo 65/65 y triaje 88/88, confirmados por el parent; doctor 195/195, bootstrap_textos 26/26 y memorias 38/38.
  - Diferencial contra `87c64b3`: 15 de 15 casos iguales en stdout, stderr y exit code.
  - El writer deja su scratch para que lo borre el autor: `tmp.mbpQqFpjm7` en el temp del sistema.
  - Risk: item 3. Cambia qué se revisa por defecto cuando se pasa `--ticket`, que la skill pasa siempre. Lleva el verificador independiente.
- **L34 (2026-11-17), lo siguiente:** el verificador de T12, y el análisis de lo nuevo en la sesión de SM-1.
- **L35 (2026-11-17), lo nuevo de SM-1 entre las 17:20 y las 20:01.** Lo leyó un agente de solo lectura y verificó cada punto contra el código. Trajo siete fricciones.
  - **Entran a la versión, con «Me parece bien»:** F1 (S14), F2 (S15), F3 (S16), F6 (S17) y F7 (S18).
  - **Quedan como ideas aparte:**
    - F4, medir el costo real de una revisión: cada corrida de `revisor-diseno` gastó entre 155k y 254k tokens y entre 6 y 13 minutos;
    - F5, un writer genérico para lo que no tiene capa: los 8 writers de SM-1 fueron genéricos, así que la compuerta del writer nunca corrió.
  - **Lo que anduvo bien:**
    - `recibo --check` atrapó cada cambio posterior a una revisión;
    - el modo 0 costó cero corridas;
    - la consolidación por frecuencia sacó a la luz una regresión real;
    - `rescatar.py` recuperó cada corrida al primer intento;
    - el guard frenó el borrado de una carpeta con una junction que apuntaba a un `node_modules` real.
  - **Orden:** F1 cambia el diseño del sello de T12, así que el verificador independiente corre una sola vez sobre T12 y T13 juntos. T13 y T14 van con dos writers en paralelo, sobre superficies disjuntas. `Doc/diseno.md` es de T13, y el writer de T14 devuelve su texto para que lo inserte el parent.
- **L36 (2026-11-17), lo siguiente:** T13 y T14 en paralelo, T15 inline, el verificador de T12 y T13, y la entrega.
- **L37 (2026-11-17), T15 hecho.** La skill del bootstrap (la spec) y la de `eval-reviewers` (el fixture) dicen dónde va el scratch para que el guard deje borrarlo: el scratch de la sesión, o una carpeta bajo `%TEMP%\claude` en Windows, `/tmp/claude-<uid>` en macOS y `claude-<uid>` dentro del temp en Linux. Es lo que acepta `comun.carpeta_scratch`, que se verificó en el código antes de escribirlo. Son solo textos, sin tests, y se revisaron leyéndolos. Risk: none.
- **L38 (2026-11-17), T14 hecho por el writer B.** Los dos writers se cortaron por el límite de 5 horas y retomaron desde donde quedaron.
  - **`_ticket_activo` inyecta un resumen y ya no un recorte:**
    - la cabecera sin las citas del molde;
    - `## Objetivo`, `## Specs`, `## Tareas` (la tabla entera) y `## Seguimientos`, en el orden del ticket;
    - las últimas 5 entradas de la Bitácora, con una línea que dice cuántas había;
    - y la ruta del archivo completo, donde está lo demás.
  - **Más allá del brief, aceptado:**
    - un `## ` dentro de un bloque de código no corta la sección;
    - las secciones se reconocen por su título exacto.
  - Si el resumen pasa los 12000 caracteres, se recorta con la línea de dónde sigue.
  - En la plantilla del ticket, el resumen pasa de 3216 a 1015 caracteres.
  - Rojo: verificar_capa 92/97. Verde: verificar_capa 97/97, confirmado por el parent, y los adaptadores base 8/8, claude_code 41/41, codex 44/44 y pi 66/66.
  - **Docs:** el parent ajustó la plantilla del `CLAUDE.md`, que queda en 149 líneas. El texto de `Doc/diseno.md` que trajo B y la línea de `abrir` se aplican cuando termine T13, que es dueño de esos dos archivos.
  - El writer B deja su scratch `t14-tbuG` bajo `%TEMP%\claude`, donde el guard deja borrarlo.
  - Risk: none.
- **L39 (2026-11-17), T13 hecho por el writer A, en `478a3e7`.** Cubre S14, S15 y S16.
  - `recibo.py --write --previo <recibo anterior>` escribe el recibo del rechequeo: rechequea lo pasado con `--archivo`, hereda los demás archivos del recibo previo con su base y sus hashes, y anota `previo`, `rechequeados`, `heredados` y `retirados`. Sale con 1 sin escribir si un heredado cambió o la base no es la del previo, y con 2 si el previo no es de este ticket o el rechequeo no queda después de él.
  - `--derivado "<hallazgo>=<destino>"` anota en el recibo lo que se deriva, y la plantilla del ticket suma `## Seguimientos` después de las Tareas, también en un ticket chico.
  - `revisar` suma la sección 9 (una corrección y un rechequeo) y las dos excepciones del sí: el modo `0` y el rechequeo aprobado con su lote.
  - Rojo: recibo 67/75 y bootstrap_textos 25/27. Verde: recibo 75/75, bootstrap_textos 27/27, triaje 88/88, ticket 38/38, bootstrap_e2e 14/14 y verificar_capa 97/97, corridas por el parent antes del commit.
  - Diferencial contra `3aaf174` en 23 pasos: stdout, códigos de salida y bytes del recibo idénticos sin las opciones nuevas; solo cambia el banner de uso de argparse en stderr.
  - El parent aplicó el texto de B en `Doc/diseno.md`, y `Doc/uso.md` y `abrir` dicen que el ticket activo llega como resumen. Esos cambios van con T14, separados de T13 por hunk.
  - Risk: item 3 (cambia el contrato de `revisar` sobre cuándo se pide el sí y qué acepta `--sellar` como cubierto). Lo siguiente: el commit de T14 y T15, y un solo verificador independiente sobre T12 y T13 juntos.
- **L40 (2026-11-17), el verificador independiente de T12 y T13 juntos.** Probó, contra la base `87c64b3`, el ciclo entero en un repo de prueba con `origin`: revisión, corrección, rechequeo, sello y la base de la unidad siguiente.
  - S13 PASS, S15 PASS, S16 PASS. S14 FAIL solo por el texto de la skill; el código pasa entero.
  - Sin regresión: 22 casos de `recibo.py` y 9 de `--sellar` dan el mismo código de salida, stdout, stderr y bytes del recibo. Solo cambia el banner de uso de argparse.
  - **B1, el bloqueo:** la sección 9.2 de `revisar` decía «Si sale con 0, la corrección no tocó nada revisado y no hay rechequeo». Una corrección que solo suma un archivo (un test nuevo) lo dejaba sin revisar, y `--sellar` rechazaba el commit.
  - **La corrección, en una sola tanda:** un archivo sumado siempre se rechequea. También cinco avisos:
    - `--sellar` recibe la carpeta del recibo de la unidad, porque la del ticket puede tomar el de otra unidad (una en modo `0` revisada el mismo día después de una en `rapido`).
    - Reescribir un recibo de rechequeo repite su `--previo`.
    - Si el rechequeo suma una capa que el lote no anunció, vuelve a pedir el sí.
    - `Doc/uso.md` nombra el sello como la tercera escritura sin sí.
    - En el paso 6, «la sección 5».
  - Un sexto aviso, sobre valores fuera de dominio, queda como está.
  - El rechequeo del mismo verificador, limitado a B1 y los avisos: B1 FIXED, los cinco avisos FIXED, sin contradicciones con `recibo.py`.
  - El caso de B1 queda como test de regresión en `recibo.tests.py` (76/76).
  - Risk: item 3, ya verificado.
- **L41 (2026-11-18), el CI de `4cbb8cb` y el seguimiento F1.**
  - Primer intento: Windows y Ubuntu en verde. macOS falló en un solo test, `test_correr_el_plazo_corta_un_comando_que_no_alcanza_a_terminar` de `afirmaciones.tests.py`, con `Veredicto(estado='OK', detalle='1')`.
  - Esta rama no tocó esa suite, cuyo último cambio es `04d0674`.
  - El test le da al comando un plazo de 0.001 s y espera que se corte. En el runner arm64, el conteo alcanzó a terminar dentro del plazo: es una carrera de tiempos.
  - Con el job relanzado (`gh run rerun --failed`), los tres sistemas quedan en verde.
  - Lo pedido por el autor, tal cual: «vale», a anotarlo en el roadmap como seguimiento, fuera de la `0.9.0`. Queda como F1, y en el roadmap.
  - El arreglo de fondo es un comando más lento que el plazo de forma determinista, por ejemplo con un `sleep`, y no depender de 1 ms.
- **L42 (2026-11-18), lo nuevo de SM-1 entre las 20:01 y las 01:18 UTC.** El pedido del autor, tal cual: «Pues si quieres revisa la sesion a ver que mas puedes observar como mejora».
  - Lo leyó un agente de solo lectura y verificó cada punto contra la rama.
  - **La instancia corría la `0.7.0`**, no la `0.8.0`. El parent lo confirmó en `installed_plugins.json`: el clon local del marketplace nunca se actualizó. La entrega tiene que decir cómo se actualiza.
  - **Ocho fricciones nuevas:**
    - G1: un `.pyc` sin trackear forzó `completo` durante horas. El parent confirmó que `triaje.py` suma los archivos sin trackear (`ls-files --others`) y marca inválida la señal de un archivo sin lenguaje.
    - G2: un `.yml` de CI de 6 líneas costó cerca de 1M tokens en `completo`.
    - G3: la regla de T13 pide `3 + <capas>` en un rechequeo `completo`, mientras que en SM-1 dos rechequeos de una corrida cerraron bien.
    - G4: cada reporte de revisión entra entero al contexto del orquestador.
    - G5: el agente pasó a inglés después de un compact.
    - G6: los hooks propios del repo no corren desde la instancia.
    - G7: los revisores volvieron a plantear algo ya aprobado.
    - G8: un revisor del repo usó `gh` sin autorización, y `cerrar` no gradúa a un repo propio.
  - **El autor, tal cual, sobre G1, G3, G5 y G7 a la versión y el resto como ideas:** «Vale me parece bien».
  - Entran como S19 a S22 (T16 a T19). G2, G4, G6 y G8 quedan como I34 a I38 en el roadmap, y G2 se analiza junto con I28.
  - Lo siguiente: T16 a T19, inline y una por una, y después la entrega.
- **L43 (2026-11-18), T16 a T19 hechos, inline, un commit por tarea.**
  - **T16 (S19):** `triaje.py` deja fuera de la unidad los archivos sin trackear bajo `__pycache__/` o con extensión `.pyc` o `.pyo`. Los nombra en `generados`, una clave que solo aparece si hay alguno, y en una línea «fuera de la unidad». Ni las señales ni el modo cambian por ellos. Un archivo que la base tenía y ya no está trackeado sigue en la unidad.
    - Rojo: triaje 88/89. Verde: 89/89.
  - **T17 (S20):** un rechequeo corre `revisor-diseno` ×1 más una corrida por capa, también en `completo`, y se consolida como `rapido`. Es solo texto en `revisar`, `Doc/uso.md` y `Doc/diseno.md`, sin un test que pueda fallar antes; la lectura estructural la hizo el parent.
  - **T18 (S21):** la plantilla del `CLAUDE.md` de la instancia dice que la conversación sigue en el idioma del usuario después de un `/compact`. Queda en 152 líneas.
    - Rojo: bootstrap_textos 27/28. Verde: 28/28.
  - **T19 (S22):** el prompt de cada corrida copia las decisiones del ticket, y la consolidación deja aparte lo que reabre una decisión sin ser `CRITICAL`. Solo texto, como T17.
  - Suites antes de commitear: triaje 89/89, doctor 195/195, bootstrap_textos 28/28, bootstrap_e2e 14/14 y bootstrap 177/177.
  - `revisar/SKILL.md`, `Doc/uso.md` y `Doc/diseno.md` se separaron por hunk entre los cuatro commits.
  - Risk: none en las cuatro.
    - T16 cambia qué archivos entran a la unidad, como pidió el autor. La salida del triaje suma una clave opcional, y sin generados queda igual, como lo prueba el test.
    - T17 y T19 cambian el texto de `revisar`, también pedido por el autor.
    - Ninguna rompe algo que no se pidió, así que no hay verificador independiente.
- **L44 (2026-11-18), el cierre de SM-1, entre las 01:18 y las 04:08 UTC.** El pedido del autor, tal cual: «Listo haz la ultima revision que ya hice el cierre del primer ticket».
  - Lo leyó un agente de solo lectura. El parent verificó tres afirmaciones contra la rama:
    - solo `.sql` tiene biblioteca de señales, y sin ella la señal de consumidores queda inválida (`triaje.py`, `evaluar_consumidores`);
    - las cinco skills de ritual traen `disable-model-invocation: true`;
    - el paso 7 de `cerrar` le deja el worktree al usuario.
  - **Cómo terminó SM-1:** `listo` y `graduado`, con el commit de cierre `4352746` y el de la entrega `07aecb0`. El `cerrar` tardó unos 5.5 minutos, con una sola tabla de propuesta.
  - **Las fricciones:**
    - H1: el agente ofreció lanzar `/odd-ws:cerrar`, que solo el usuario puede escribir.
    - H2: un `CLAUDE.md` que ya venía modificado no salió en la propuesta. Ya lo cubre la `0.9.0`.
    - H3: la instancia no se commiteó en todo el ticket, y el cierre se llevó 151 archivos.
    - H4: la entrega falló después del cierre, y el estado y el segundo commit se improvisaron.
    - H5: el worktree de un repo propio le quedó al usuario.
    - H6: un arreglo de 3 líneas en un test forzó `completo` y agotó el límite de 5 horas.
    - Lo nuevo de G8: `cerrar` igual graduó a un doc del repo, en una rama sin mergear.
  - **El autor, tal cual, sobre H1, H4, H5 y que `abrir` commitee el ticket a la versión, el resto como ideas:** «Vale».
  - Entran como S23 a S26 (T20 a T23).
  - Quedan como ideas:
    - I43: commitear las rondas de `revisar`;
    - I44: el triaje de los lenguajes sin biblioteca, que se analiza con rigor junto con I28 e I34;
    - lo nuevo de G8, sumado a I38.
- **L45 (2026-11-18), T20 a T23 hechos, inline.**
  - **T20 (S23):** la plantilla del `CLAUDE.md` de la instancia dice, en «Skills del plugin», que los cinco rituales los escribe el usuario y que el agente termina con la línea exacta. Queda en 155 líneas.
    - Rojo: bootstrap_textos 28/29. Verde: 29/29.
  - **T21 (S24):** `cerrar` suma «La entrega después del cierre»:
    - comprobar la entrega con git de lectura;
    - un cambio de código posterior a la revisión pasa antes por `revisar`;
    - `listo`, con la foto nueva en la bitácora;
    - `chore(<id>): entrega`;
    - quitar la marca de ticket activo.
    - El paso 9.5 ya no es ambiguo: la marca se quita solo con `listo`.
  - **T22 (S25):** el paso 7 de `cerrar` desarma el worktree de un repo `own` si está limpio y su rama ya está en `origin`. En un repo del equipo, sigue siendo del usuario.
  - **T23 (S26):** el paso 8.4 de `abrir` commitea el ticket en la instancia (`chore(<id>): abre el ticket`), con la carpeta del ticket y, si le sumó el worktree, el `.code-workspace`. La regla 3 lo nombra.
  - T21 a T23 son solo texto en las skills y en `Doc/`, sin un test que pueda fallar antes. Ninguna suite lee esas skills, y la lectura estructural la hizo el parent.
  - T21 y T22 van en un solo commit, porque comparten hunks en `cerrar`, `Doc/uso.md` y `Doc/diseno.md`, y se citan entre sí.
  - Suites: bootstrap_textos 29/29, bootstrap_e2e 14/14, bootstrap 177/177 y ticket 38/38.
  - Risk: none. Son cambios pedidos por el autor. `abrir` suma un commit en la instancia, que S3 ya autoriza ahí, y el worktree solo se desarma en un repo propio, con las dos comprobaciones.
- **L46 (2026-11-18), T9: la entrega de la `0.9.0`.** El autor, tal cual: «autorizo».
  - El CI de `8c731a1`, el último commit de T20 a T23, pasó en los tres sistemas.
  - El CHANGELOG `## 0.9.0` trae «Lo que cambia para ti», «Qué hacer en tu instancia» y «Detalle técnico». `tools/notas.py 0.9.0` imprime el cuerpo sin cortes.
  - `plugin.json` (Claude Code y Codex), `package.json` y el README pasan a `0.9.0`.
  - `Doc/actualizar.md` suma dos cosas:
    - los dos comandos de Claude Code van juntos, porque sin `marketplace update` la instancia sigue en la versión anterior, como pasó en SM-1;
    - «Después de actualizar: las plantillas de la instancia», con lo que hay que copiar a mano, sacado del diff de `plugin/plantillas/` contra `odd-ws--v0.8.0`.
  - Roadmap:
    - R4 pasa a Hecho, y sus 26 ideas a «hecha (`0.9.0`)»;
    - R2 queda como lo siguiente, con F1 adentro;
    - R3 pasa a «Esperando», con la cita del autor: «Bueno lo de R3 se puede postergar hasta nuevo aviso, ya que no me han pedido soporte para OpenCode, Gemini CLI y Copilot CLI para que lo hagamos a demanda».
  - Pendiente después de publicar: medir cuánto tarda el bootstrap («de 20 minutos a X») en una instancia nueva.
