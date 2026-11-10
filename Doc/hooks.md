# Hooks

Corren solos, sin que los invoques. Cuando uno frena algo, el mensaje dice por qué. Por ejemplo, si el agente intenta `git push --force origin main`, recibe esto:

```text
guard-comandos bloqueó el comando: git push --force (si de verdad hace falta forzar, usa --force-with-lease). Si la operación es deliberada, que la corra el usuario a mano.
```

## Cuándo corre cada uno

| Cuándo | Qué hace |
|---|---|
| Al abrir o retomar una sesión | Valida la config de la instancia y avisa si está rota. Tras `/compact` o `/clear`, reinicia las marcas de primer toque. |
| Al leer por primera vez un archivo de una capa | Inyecta sus no-negociables como contexto. |
| Antes de editar un archivo de una capa | Si los no-negociables no se cargaron, bloquea la primera edición y los inyecta. El reintento pasa. |
| Después de editar | Corre las reglas de la capa (`.claude/reglas/verificar_<capa>.py`): un `bloqueo` frena y un `aviso` llega como contexto. |
| Antes de un comando de shell | `guard_comandos.py` bloquea force push, `reset --hard`, `clean -f` y borrados recursivos fuera del scratch. En un repo con `agent_readonly: true`, pregunta antes de cualquier git que no sea de lectura. |
| Dentro de un `writer-<capa>` | `writer_guard.py` bloquea el git de escritura y las escrituras por shell sobre los repos y el taller de la capa, y guarda una foto de cada archivo en su primer toque. |
| Al terminar un `writer-<capa>` | `writer_stop.py` compara las líneas reales contra la foto, corre los chequeos de la capa y exige el bloque `## Resultado`. Bloquea una sola vez. |

Las reglas que corren después de editar son las de tu instancia: ver [Capas y reglas propias](capas-y-reglas.md).

## Si Python no arranca

Los hooks los lanza `python3`. Si no arranca, en Claude Code 2.1.295 o más la herramienta queda bloqueada con el error; con una versión anterior, y siempre en Codex, la herramienta pasa sin el chequeo. En ese caso, la defensa es el ítem `python` de `/odd-ws:doctor`, que revisa el intérprete que lanza cada CLI declarado.

## En Codex

- **Lo que en Claude Code pregunta, en Codex se bloquea,** porque Codex no puede pedir confirmación desde un hook. El motivo llega con una línea más: «Codex no puede pedir confirmación desde un hook, así que este comando queda bloqueado: si hace falta, pídele al usuario que lo corra él.»
- **Codex no tiene herramienta de lectura,** así que el hook de la primera lectura no corre ahí: los no-negociables llegan con el bloqueo de la primera edición.
- **Cada hook necesita tu confianza** en `/hooks`. Sin ella, Codex no lo corre.
- **En la prueba de humo,** el bloqueo del force push llegó así: «Command blocked by PreToolUse hook: guard-comandos bloqueó el comando…».

El porqué de cada hook, con su especificación, está en [`Doc/diseno.md`](diseno.md).
