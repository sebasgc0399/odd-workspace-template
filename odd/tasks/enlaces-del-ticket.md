# Los enlaces del ticket (I61, `0.10.0`)

Objetivo: que los enlaces de un ticket, o de cualquier documento `.md`, se puedan revisar y depurar desde cualquier cliente: con su ruta absoluta para abrirlos o copiarlos, y sabiendo cuáles están rotos.
Rama: `feat/enlaces-del-ticket`, desde `de07bf8`. Entrega: un commit con la unidad, que incluye este documento; el push a main y la etiqueta, solo con autorización.
Pruebas: `python3 plugin/scripts/<script>.tests.py`, todas con el bucle de `CONTRIBUTING.md`.

## Specs

- **S1. El pedido.** Es de un usuario de la comunidad (_00_), en el hilo de la `0.9.0`: «lo que igual se podria mejorar es si se abrieran los enlaces que aparecen en las ODDs, aunque como, por lo menos en las que tengo ahora, son variados, lo mismo enlace a carpeta que a .md,... igual es un poco farragoso, pero si nos los abre por lo menos que si los copia al portapapeles o preguntara, eso ayudaría mucho a revisarlas/depurarlas». El autor, sobre la propuesta: «Metamosla en esta version».
- **S2. Listar los enlaces.** `ticket.py --enlaces <id | ruta a un .md>` lista los enlaces del documento:
  - del `CLAUDE.md` del ticket si recibe un id, o del `.md` que se le pase;
  - cada uno con su texto, su ruta absoluta resuelta contra la carpeta del documento, su tipo (archivo o carpeta) y si el destino existe;
  - los rotos, marcados aparte;
  - sin escribir nada.

  Aceptar cualquier `.md` cubre también los documentos de ODD de gentle-ai (`odd/tasks/*.md`), porque el pedido no dice cuáles usa.
- **S3. Copiarlos.** Con `--copiar`, la misma lista de rutas absolutas va al portapapeles. Si no hay herramienta de portapapeles, avisa y la lista sale igual por pantalla.
- **S4. Una sola regla de enlace válido.** Se reutiliza el criterio de `conocimiento.py` (`LINK_MD_RE`, `_resolver`, `_existe` y `ESQUEMA_RE`), extendido a carpetas y a archivos que no son `.md`. No se escribe una segunda regla. Los enlaces con esquema (`https:`, `mailto:`) se listan aparte, sin verificarlos.
- **S5. Supuesto: no se abren solos.** Abrir un enlace depende del sistema y del cliente, y lanzar programas desde el agente es un efecto que habría que pedir cada vez. En la terminal de VS Code, una ruta absoluta se abre con Ctrl+clic, y en cualquier otra se puede copiar.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T1 | S1 a S5 | `ticket.py --enlaces` y `--copiar`, sobre el criterio compartido con `conocimiento.py`, con sus tests y sus docs | delegada, en un carril propio. Risk: none, porque solo lee y el portapapeles se toca a pedido | pendiente | |

## Log

- **L1** (2026-11-19) El pedido de _00_ y la decisión del autor, tal cual, están en S1. Antes de decidir, se verificó qué hay hoy: `conocimiento.py:191-199` detecta enlaces rotos, pero solo en los docs de conocimiento y solo a `.md`.
