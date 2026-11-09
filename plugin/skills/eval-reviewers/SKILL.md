---
name: eval-reviewers
description: Medir los revisores de la instancia (los agentes de .claude/agents que revisan un cambio) contra la revisión real de un líder, a ciegas y de forma repetible. Usar cuando el usuario pide medir un revisor, comparar dos versiones de su prompt o correr el modo sombra antes de una revisión real.
---

# /odd-ws:eval-reviewers

Mide a los revisores LLM de la instancia contra la revisión real de un líder, sin que vean la respuesta y de forma repetible. Los scripts los corre el orquestador, nunca el revisor. En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts`. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

## Reglas duras

1. **La ceguera tiene que ser física.** Pedir «no leas X» no alcanza: un `Grep` con exclusiones sobre la carpeta del ticket puede devolver la verdad de terreno. Mientras corren los revisores, la verdad de terreno (la carpeta `revision/` del ticket) tiene que estar fuera del alcance de sus herramientas. Hoy eso se hace a mano, porque el armado automático del fixture está en espera.
2. **Los repos se leen de una copia en el commit base**, nunca del clon vivo, que puede estar en la rama con el código ya corregido. El clon vivo va entre las rutas prohibidas.
3. **Auditar siempre** con `auditar_lecturas.py`, que mira la huella real de `Read`, `Grep` y `Glob`. El autorreporte del revisor no cuenta.
4. **Corridas por fase, nunca todas juntas.** Antes de lanzar, dar el pronóstico (`N corridas × el costo de una corrida`) y esperar el sí del usuario.
5. **Mismo número de corridas y misma agregación en los dos brazos** de una comparación. Una corrida suelta es anécdota.
6. **No ajustar prompts mirando el caso sombra.** Si la aceptación no se cumple, se reporta tal cual.

## Protocolo

1. **Elegir y pronosticar.** Definir el fixture, los revisores, `N` corridas por revisor y la etiqueta de cada brazo (`v1`, `v2`…). Dar el costo estimado y esperar el sí.
2. **Armar el fixture, a mano.**
   - Crear un scratch nuevo con la entrada (los diffs y las copias de los repos en el commit base) y un prompt por corrida.
   - Sacar la verdad de terreno del alcance de los revisores, a una carpeta **hermana** del scratch (`<scratch>.oculto`), nunca hija.
   - Escribir un `manifest.json` con `prohibidas` y `permitidas`: rutas absolutas, donde `{scratch}` es el scratch de la corrida.
3. **Lanzar los revisores en paralelo.**
   - Un `Agent` por prompt, en segundo plano y todos en el mismo mensaje.
   - Anotar la tabla `nombre de corrida → agentId`, con nombres `<fecha>-<versión>-<revisor>-r<i>`.
   - No leer reportes parciales.
4. **Rescatar** cuando terminan todos:

   ```bash
   python3 "<S>/rescatar.py" --sesion "<~/.claude/projects/<proyecto>/<sesión>/subagents>" --destino "<scratch>/corridas" --corrida <nombre>=<agentId> --corrida …
   ```

   - Un revisor cortado no deja reporte: sale como `FAIL` (exit 1) y se informa; no se reintenta en silencio.
   - Un `Bash` o un `PowerShell` aparece entre las herramientas no auditadas, y sus comandos quedan en `<nombre>.comandos.json`.
5. **Devolver la verdad de terreno a su lugar**, aunque falte puntuar, y mover las corridas a `revision/<fixture>/corridas/` del ticket.
6. **Auditar las lecturas** de cada corrida:

   ```bash
   python3 "<S>/auditar_lecturas.py" <corridas>/*.lecturas.json --manifest <manifest.json> --scratch <scratch> [--ceguera-fisica]
   ```

   - **CONTAMINADO** (un `Read` bajo una ruta prohibida): la corrida no cuenta, salvo que se demuestre que ese archivo no traía la verdad de terreno. Se puntúa `contaminado`.
   - **EXPOSICIÓN** (un `Grep` o un `Glob` cuyo alcance toca una ruta prohibida): significa «pudo ver», no «vio». Se resuelve leyendo el reporte. Un `Glob` solo revela nombres.
   - **`--ceguera-fisica`** baja a info solo lo que estaba fuera del disco (las rutas que pasan por una carpeta `revision`). Usalo solo si la verdad de terreno estuvo de verdad fuera del disco.
7. **Puntuar.** Un veredicto por celda (corrida × observación), con la cita del reporte, en `puntajes.json`. La escala es fija:

   | Veredicto | Significa |
   |---|---|
   | `ok` | el mismo problema y la misma dirección que el líder |
   | `parcial` | el mismo objeto, con otra solución o cobertura incompleta |
   | `reves` | toca el tema y recomienda lo contrario |
   | `elogio` | marca como correcto lo que el líder objetó, o lo justifica |
   | `derivado` | lo anota para otro revisor, sin dirección |
   | `contaminado` | vio la verdad de terreno (lo dice la auditoría); no cuenta |
   | `-` | no lo toca |

   **El puntaje del orquestador solo no alcanza:** lo repite un juez independiente, a ciegas.
   - Los reportes van a una carpeta con nombres neutros (`reporte-A.md`…), en orden barajado; el mapa letra → corrida, fuera de esa carpeta.
   - El juez cita literal en 30 palabras o menos; ante la duda, elige el nivel que afirma menos.
   - Llena un campo de disputas, verificadas en el código.
   - El orquestador adjudica cada diferencia con la cita y el código.
   - Una observación cuya verdad de terreno el código refuta va a `disputadas`, con la evidencia, y sale del conteo.
8. **Ratificación a ciegas.** Primero, la tabla:

   ```bash
   python3 "<S>/puntuar.py" puntajes.json --plantilla-ratificacion tabla.md --clave clave.json
   ```

   Entregá **solo** `tabla.md`; `clave.json` no se muestra. Se responde en la última columna, con `sí` o `no → <veredicto>`. Después:

   ```bash
   python3 "<S>/puntuar.py" puntajes.json --aplicar-ratificacion tabla.md clave.json --ratificado-por "<quién>"
   ```

   - Si quedan filas sin responder, sale con 1 y no escribe nada.
   - Si el usuario delega la ratificación en el juez, `--ratificado-por` lo dice así, nunca con el nombre del usuario.
   - Las citas no deben dejar ver la versión: el script quita los nombres de corrida, pero no puede adivinar otras pistas.
9. **Agregar y comparar:**

   ```bash
   python3 "<S>/puntuar.py" puntajes.json --brazo v1=<corrida>,<corrida> --brazo v2=<corrida>,<corrida>
   ```

   - Por corrida y por brazo, da `ok`, `parcial`, contra (`reves` + `elogio`) y el puntaje (`ok + 0,5 × parcial`).
   - Por brazo suma la media, la unión (el mejor veredicto por observación), las estables, el k/N y los conflictos: «decide el líder o revisá a mano».
   - Con dos brazos, también la tabla pareada.

## Modo sombra (la aceptación de un cambio de revisor)

1. **Antes de mostrarle el código al líder:**
   - correr las dos versiones con la misma agregación;
   - congelar los reportes, los prompts y la huella de cada revisor (`git hash-object` del agente y de cada `SKILL.md` que precarga) en `revision/<fecha>-sombra/`;
   - commitear **antes** de la revisión.
2. **Después de la revisión:** armar la verdad de terreno con lo que dijo el líder, puntuar, ratificar y armar la tabla pareada.
3. **Aceptación:**
   - la versión nueva suma más aciertos ratificados;
   - `reves` y `elogio` no aumentan;
   - los falsos positivos siguen en 0.

## Scripts

| Script | Para qué | Salidas |
|---|---|---|
| `rescatar.py` | reporte, prompt, lecturas y comandos desde el `.jsonl` del subagente | 0 ok · 1 corrida sin reporte · 2 error |
| `auditar_lecturas.py` | cruza `Read`, `Grep` y `Glob` con las rutas prohibidas | 0 limpio · 1 exposición o contaminado · 2 error |
| `puntuar.py` | puntaje, brazos, tabla pareada y ratificación | 0 ok · 1 filas pendientes · 2 error |
