# Hooks

Corren solos, sin que los invoques. Cuando uno frena algo, el mensaje dice por qué. Por ejemplo, si el agente intenta `git push --force origin main`, recibe esto:

```text
guard-comandos bloqueó el comando: git push --force (si de verdad hace falta forzar, usa --force-with-lease). Si la operación es deliberada, que la corra el usuario a mano.
```

## Cuándo corre cada uno

| Cuándo | Qué hace |
|---|---|
| Al abrir o retomar una sesión | Valida la config de la instancia y avisa si está rota. Tras `/compact` o `/clear`, reinicia las marcas de primer toque. |
| Al empezar el turno | `revisar_turno.py` saca una foto de los archivos de capa que ya están modificados, para saber después qué cambió durante el turno. Corre solo en el agente principal: un subagente no saca foto. |
| Al leer por primera vez un archivo de una capa | Inyecta sus no-negociables como contexto. |
| Antes de editar un archivo de una capa | Si los no-negociables no se cargaron, bloquea la primera edición y los inyecta. El reintento pasa. |
| Después de editar | Corre las reglas de la capa (`.claude/reglas/verificar_<capa>.py`): un `bloqueo` frena y un `aviso` llega como contexto. |
| Antes de un comando de shell | `guard_comandos.py` bloquea force push, `reset --hard`, `clean -f`, borrados recursivos fuera del scratch y el parche de Codex aplicado por la shell (`--codex-run-as-apply-patch`), que escribe archivos sin pasar por los chequeos de capa. Fuera de un writer, bloquea también una escritura por shell que deja contenido nuevo en un archivo de capa, y manda a la herramienta de edición para que corran el primer toque y las reglas. En un repo con `agent_readonly: true`, pregunta antes de cualquier git que no sea de lectura. |
| Dentro de un `writer-<capa>` | `writer_guard.py` bloquea el git de escritura y las escrituras por shell sobre los repos y el taller de la capa, y guarda una foto de cada archivo en su primer toque. |
| Al terminar un `writer-<capa>` | `writer_stop.py` compara las líneas reales contra la foto, corre los chequeos de la capa y exige el bloque `## Resultado`. Bloquea una sola vez. |
| Al terminar el turno | `revisar_turno.py` corre las reglas de la capa sobre los archivos de capa que cambiaron durante el turno, sin importar cómo se escribieron: con la herramienta de edición, por la shell, con un script o con git. Mira solo las líneas nuevas del turno. Si hay un `bloqueo`, el agente sigue una vez más para corregirlo, y los avisos llegan en el mismo mensaje. No distingue quién escribió el cambio: si el usuario editó un archivo de capa durante el turno, el agente igual recibe esa vuelta, con el pedido de avisarle al usuario y no tocarlo. Si el hook falla, el turno cierra igual, sin revisión. |

Las reglas que corren después de editar son las de tu instancia: ver [Capas y reglas propias](capas-y-reglas.md).

## Qué frenan y qué no

Los guards frenan los errores y los atajos del agente, también cuando escribe el comando dentro de un shell (`bash -c '…'`, `powershell -Command "…"`, `iex '…'`) o llama a git por su ruta completa. No frenan a un agente que intenta esquivarlos a propósito, por ejemplo partiendo una palabra con comillas (`gi''t`). Para eso está el sandbox del sistema, no un hook. La lista de formas conocidas que quedan fuera está en [`Doc/diseno.md`](diseno.md#guard-de-comandos-guard_comandospy-l48-l49-l52-l53).

## Si Python no arranca

Una capa sin no-negociables no tiene primer toque: si el bloque `<!-- no-negociables -->` de su skill está vacío, o conserva el texto que trae la plantilla de la capa, la lectura no inyecta nada y la primera edición no se bloquea.

Los hooks los lanza `python3`. Si no arranca, en Claude Code 2.1.295 o más la herramienta queda bloqueada con el error; con una versión anterior, y siempre en Codex, la herramienta pasa sin el chequeo. En ese caso, la defensa es el ítem `python` de `/odd-ws:doctor`, que revisa el intérprete que lanza cada CLI declarado.

## Apagar un hook

Un plugin no puede quitar un hook en un solo proyecto, así que se apaga desde la config: la clave opcional `disabled_hooks` de `workspace.config.json` lista los hooks que no corren en esta instancia, en Claude Code, Codex y Pi por igual.

```json
"disabled_hooks": ["revisar_turno"]
```

- **Los nombres** son los de los cinco scripts: `verificar_capa`, `guard_comandos`, `revisar_turno`, `writer_guard` y `writer_stop`. Un hook apagado deja pasar todo y no escribe nada: `revisar_turno` no saca su foto, `verificar_capa` no marca el primer toque y `writer_guard` no guarda las fotos del writer.
- **Cada nombre apaga solo su hook.** Con `verificar_capa` apagado, las reglas de la capa siguen corriendo al terminar el turno (`revisar_turno`) y al cerrar un writer (`writer_stop`).
- **Un valor inválido no apaga ninguno:** si no es una lista, o si un nombre no es de los cinco o se repite, los cinco siguen prendidos. El ítem `config` de `/odd-ws:doctor` lo marca como FALTA y el bootstrap rechaza esa config.
- **El doctor avisa** en el ítem `hooks-apagados` mientras haya alguno apagado, con su nombre. Para prenderlo, sácalo de la lista.
- **Apagar `guard_comandos` es el riesgo mayor:** nada frena un force push, un `reset --hard`, un `clean -f`, un borrado recursivo fuera del scratch ni la escritura por shell de un archivo de capa, y el git de escritura en un repo con `agent_readonly: true` ya no pregunta. Apágalo solo si otra herramienta cumple ese papel, por ejemplo el sandbox de tu CLI.
- **El perfil `controles` no apaga ninguno.** Una instancia con `"profile": "controles"` corre los mismos cinco hooks, que no dependen de tickets, recibos ni de `/odd-ws:revisar`. Como no tiene writers, `writer_guard` y `writer_stop` quedan dormidos; ver [el perfil `controles`](uso.md#el-perfil-controles).

## En Codex

- **Lo que en Claude Code pregunta, en Codex se bloquea,** porque Codex no puede pedir confirmación desde un hook. El motivo llega con una línea más: «Codex no puede pedir confirmación desde un hook, así que este comando queda bloqueado: si hace falta, pídele al usuario que lo corra él.»
- **Codex no tiene herramienta de lectura,** así que el hook de la primera lectura no corre ahí: los no-negociables llegan con el bloqueo de la primera edición.
- **Cada hook necesita tu confianza** en `/hooks`. Sin ella, Codex no lo corre.
- **En la prueba de humo,** el bloqueo del force push llegó así: «Command blocked by PreToolUse hook: guard-comandos bloqueó el comando…».

El porqué de cada hook, con su especificación, está en [`Doc/diseno.md`](diseno.md).
