# El rescate: qué escribe y qué se mide

Detalle de la sección 6 del `SKILL.md` de `/odd-ws:revisar`. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`.

## Lo que escribe

- `--sesion` es la carpeta `subagents` de esta sesión, bajo `~/.claude/projects/<proyecto>/<sesión>/`. También acepta la carpeta de la sesión que la contiene. Si no la encuentras, búscala con Glob: `~/.claude/projects/*/*/subagents/agent-<agentId>.jsonl`.
- Por cada corrida escribe `<nombre>.md` (el reporte), `.prompt.txt`, `.lecturas.json`, con el costo de la corrida en `costo`, y, si hubo comandos, `.comandos.json`. Si la devolución es una línea `VEREDICTO:` (I35), el reporte es el texto que el revisor escribió justo antes de devolverla, y en Pi, el texto del hilo después de su última herramienta. Si no, el reporte sale del `SubagentHandback` o, si no hubo, del último texto.
- Con `--costo` escribe también `corridas/costo.json`: el modo, los motivos de `entrada/triaje.json`, cada corrida con su costo (también la cortada, que se pagó igual), las líneas de los diffs de `entrada/`, el costo de esta sesión desde el último `triaje.py` antes de lanzar las corridas (`orquestador`, leído de `<sesión>.jsonl`, junto a la carpeta de la sesión) y si las corridas corrieron en serie (`en_serie`). Es lo que lee `--ultimo-costo` en el anuncio (paso 2). Un rescate posterior en la misma carpeta, por ejemplo el de una corrida relanzada, suma sus corridas sin pisar las anteriores. Si falta `triaje.json` o los diffs, lo avisa y deja ese campo en `null`; si no encuentra el tramo de esta sesión, deja `orquestador` en `null`, también con aviso, y no es una falla del rescate. `--costo` va solo con el `--destino` de una revisión (`<ticket>/revision/<fecha>-<modo>[-<n>]/corridas`); con otro sale con 2 sin escribir nada.
- `triaje.json` es el triaje del paso 2 con `--json`, con los mismos argumentos. De ahí saca el rescate los motivos del modo para el costo de la revisión.
- Sale con 0 si todas están bien, con 1 si alguna corrida no dejó reporte (`FAIL … sin SubagentHandback`, `FAIL … devolvio solo el veredicto` o `no existe agent-…`) y con 2 por error de uso.
- Un lanzamiento que el host rechazó por su límite de concurrencia no es una corrida cortada: se relanzó por tandas (paso 4) y se rescata con las demás.

## Lo que se mide

- **El último costo medido** se anuncia, salvo en modo `0`, porque las corridas no dicen cuánto cuesta cada una. `python3 "<S>/rescatar.py" --ultimo-costo "<ticket>"` imprime una línea que se cita tal cual: es el `costo.json` más nuevo del ticket o, si el ticket no tiene, el de la instancia (las carpetas `-sombra` no cuentan). Es una referencia, no una estimación: no la multipliques ni la ajustes a este diff. Si sale con 1, no hay ningún costo medido: anuncia solo las corridas. Cada corrida cuesta lo que una corrida de revisor sobre este diff.
- **El rendimiento** de la primera línea de `consolidado.md` es lo que mide qué rinde cada corrida: con esos datos se decide si un `completo` puede bajar a 2 corridas de diseño.
