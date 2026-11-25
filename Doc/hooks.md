# Hooks

Corren solos, sin que los invoques. Cuando uno frena algo, el mensaje dice por qué, y el de un comando cita el comando tal cual lo mandó el agente (uno de más de 300 caracteres se corta con «…»). Por ejemplo, si el agente intenta `git push --force origin main`, recibe esto:

```text
guard-comandos bloqueó el comando: git push forzado (no lo corras tú: un lease sin `ref:sha` lo satisface cualquier `fetch`; para forzar con seguridad, el usuario mira `git log <remoto>/<rama>` y corre `git push --force-with-lease=<rama>:<sha que esperas> <remoto> <rama>`). Si la operación es deliberada, que la corra el usuario a mano.
Comando: «git push --force origin main»
```

## Cuándo corre cada uno

| Cuándo | Qué hace |
|---|---|
| Al abrir o retomar una sesión | Valida la config de la instancia y avisa si está rota. Avisa una vez de los hooks que fallaron desde el último aviso (ver [Si un hook falla](#si-un-hook-falla)). Tras `/compact` o `/clear`, reinicia las marcas de primer toque. |
| Al empezar el turno | `revisar_turno.py` saca una foto de los archivos de capa que ya están modificados, para saber después qué cambió durante el turno. Corre solo en el agente principal: un subagente no saca foto. |
| Al leer por primera vez un archivo de una capa | Inyecta sus no-negociables como contexto. |
| Antes de editar un archivo de una capa | Si los no-negociables no se cargaron, bloquea la primera edición y los inyecta. El reintento pasa. |
| Antes de editar un archivo de un repo | Si la edición toca las líneas de una desviación conocida, pregunta antes de seguir, con la desviación, su porqué y su fecha (ver [El porqué antes de editar](#el-porqué-antes-de-editar)). |
| Después de editar | Corre las reglas de la capa (`.claude/reglas/verificar_<capa>.py`) y las de sus paquetes: un `bloqueo` de una regla calibrada frena, y lo demás llega como contexto. Un `bloqueo` de una regla sin calibrar, con la calibración vieja o con una disputa abierta, llega como aviso, con el motivo y lo que hay que hacer (ver [Cuándo bloquea una regla](capas-y-reglas.md#cuándo-bloquea-una-regla)). En un archivo de un repo, suma como contexto el porqué de las líneas reemplazadas, sacado de `git blame`. |
| Antes de un comando de shell | `guard_comandos.py` bloquea todo push forzado (también con `--force-with-lease`, `--force-if-includes`, `--mirror` o un refspec `+`), `reset --hard`, `clean -f`, borrados recursivos fuera del scratch y el parche de Codex aplicado por la shell (`--codex-run-as-apply-patch`), que escribe archivos sin pasar por los chequeos de capa. Fuera de un writer, bloquea también una escritura por shell que deja contenido nuevo en un archivo de capa, y manda a la herramienta de edición para que corran el primer toque y las reglas. En un repo con `agent_readonly: true`, pregunta antes de cualquier git que no sea de lectura. |
| Dentro de un `writer-<capa>` | `writer_guard.py` bloquea el git de escritura y las escrituras por shell sobre los repos y el taller de la capa, y guarda una foto de cada archivo en su primer toque. |
| Al terminar un `writer-<capa>` | `writer_stop.py` compara las líneas reales contra la foto, corre los chequeos de la capa y exige el bloque `## Resultado`. Bloquea una sola vez; un chequeo de capa frena solo si su regla está calibrada. |
| Al terminar el turno | `revisar_turno.py` corre las reglas de la capa sobre los archivos de capa que cambiaron durante el turno, sin importar cómo se escribieron: con la herramienta de edición, por la shell, con un script o con git. Mira solo las líneas nuevas del turno. Si hay un `bloqueo` de una regla calibrada, el agente sigue una vez más para corregirlo, y los avisos llegan en el mismo mensaje. No distingue quién escribió el cambio: si el usuario editó un archivo de capa durante el turno, el agente igual recibe esa vuelta, con el pedido de avisarle al usuario y no tocarlo. Si el hook falla, el turno cierra igual, sin revisión. |

Las reglas que corren después de editar son las de tu instancia: ver [Capas y reglas propias](capas-y-reglas.md).

## Qué frenan y qué no

Los guards frenan los errores y los atajos del agente, también cuando escribe el comando dentro de un shell (`bash -c '…'`, `powershell -Command "…"`, `iex '…'`) o llama a git por su ruta completa. No frenan a un agente que intenta esquivarlos a propósito, por ejemplo partiendo una palabra con comillas (`gi''t`). Para eso está el sandbox del sistema, no un hook. La lista de formas conocidas que quedan fuera está en [`Doc/diseno.md`](diseno.md#guard-de-comandos-guard_comandospy-l48-l49-l52-l53).

## El porqué antes de editar

Cuando el agente reemplaza líneas de un archivo de un repo de la config, `verificar_capa` le muestra por qué están así, sacado de la historia de git y sin modelo. Corre con `Edit` y `Write` (no con `MultiEdit`), tenga el archivo capa o no.

- **Antes de editar, una pausa solo para las desviaciones conocidas.** Si lo que se reemplaza se superpone con las líneas de una fila de `.claude/reglas/desviaciones.csv` (el código que parece un error y es a propósito, que gradúa `/odd-ws:cerrar`), el hook pregunta antes de seguir, con la desviación, su porqué y su fecha. Las líneas se buscan por contenido, así que la pausa sigue a la desviación aunque se haya movido; si ya no están en el archivo, no pausa. Sin desviaciones de ese archivo, la pausa no corre git.
- **Después de editar, el porqué como contexto.** El hook busca en `HEAD` el texto que se reemplazó, corre `git blame` de esas líneas y le pasa al agente hasta dos commits, del más nuevo al más viejo, en una línea cada uno: la fecha, el hash corto y la primera línea del cuerpo del commit, sin los trailers como `Co-Authored-By:`. Por ejemplo:

  ```text
  porqué de lo que reemplazaste en src/ventas.sql (git blame en HEAD, de lo más nuevo a lo más viejo; si un porqué choca con tu cambio, reconsidéralo):
  2026-02-15 3f2a9c1: Se redondea a dos decimales porque la DIAN rechaza tres.
  ```

  El agente lo lee justo después de editar y puede reconsiderar el cambio.
  - **Calla** si ningún commit de esas líneas tiene cuerpo, si el texto todavía no tiene commit o si el archivo es nuevo.
  - **«sin historia»** sale al editar un archivo que existe pero no está en `HEAD`, como uno sin trackear. Un `Write` que pisa un archivo sin trackear calla, porque después de escribir no se distingue de uno nuevo.
  - **«no se pudo chequear el porqué de estas líneas»** sale si git falla o tarda más de 1,5 s, nunca como silencio. Ese plazo es aparte y no alarga el del hook.
- **Una falla de este chequeo no cambia lo demás:** el bloqueo del primer toque y los hallazgos de la capa salen igual.
- **El blame no ve el código borrado:** lo que ya no está en el archivo no tiene líneas que mirar.

### La clave `porque_al_editar`

En `workspace.config.json`, opcional:

```json
"porque_al_editar": "indice"
```

- **`"todo"`**, por defecto: la pausa y el contexto.
- **`"indice"`**: solo la pausa de las desviaciones.
- **`"apagado"`**: ni la pausa ni el contexto.

Un valor que no sea uno de los tres lo rechaza el bootstrap, el doctor lo marca como FALTA en el ítem `config`, y mientras tanto el hook se comporta como con `"todo"`.

### En cada CLI

- **Claude Code** pregunta. Lo reemplazado es el `old_string` de un `Edit`, o el archivo entero en un `Write`.
- **Codex** no puede preguntar desde un hook, así que la pausa bloquea, con la línea «Codex no puede pedir confirmación desde un hook, así que esta edición queda bloqueada: si hace falta, pídele al usuario que la haga él.» Lo reemplazado son las líneas quitadas y de contexto de cada hunk del parche; un archivo que se agrega o se borra no trae nada.
- **Pi** pregunta si la sesión tiene pantalla, y si no, bloquea con la línea «Esta sesión de Pi no tiene pantalla para pedir confirmación, así que esta edición queda bloqueada: si hace falta, pídele al usuario que la haga él.» Lo reemplazado es el `oldText` de cada edición de `edits`, o el archivo entero en un `write`. Un `edit` sin `oldText` no trae nada que mirar: ni pausa ni contexto.

## Si Python no arranca

Una capa sin no-negociables no tiene primer toque: si el bloque `<!-- no-negociables -->` de su skill está vacío, o conserva el texto que trae la plantilla de la capa, la lectura no inyecta nada y la primera edición no se bloquea.

En Claude Code, los hooks los lanza `python3`; en Windows, los de Codex y Pi los lanza `python`. Si no arranca, en Claude Code 2.1.295 o más y en Pi la herramienta queda bloqueada con el error; con una versión anterior de Claude Code, y siempre en Codex, la herramienta pasa sin el chequeo. En ese caso, la defensa es el ítem `python` de `/odd-ws:doctor`, que revisa el intérprete que lanza cada CLI declarado.

## Si un hook falla

Un hook que arranca pero falla por dentro, con un error que no esperaba, no frena nada: deja pasar lo que le tocaba revisar, como siempre. Lo que cambia es que la falla deja rastro:

- **Queda anotada** en `.claude/estado/fallas-de-hooks.jsonl`, en la raíz de la instancia: el hook, el evento, la fecha, y el tipo y el mensaje del error, recortado a 200 caracteres. No se anota el payload del evento, aunque el mensaje del error sí puede traer un pedazo de la entrada, como una ruta o el destino de una redirección, recortado a esos 200 caracteres. Se guardan las últimas 20.
- **La sesión siguiente la muestra una vez.** Al abrir, retomar, compactar o limpiar la sesión, el agente recibe las fallas que todavía no vio, para que te las cuente.
- **El doctor la muestra** en el ítem `hooks-fallas`, en AVISO, con las tres más recientes, hasta que vacíes el registro con `--arreglar hooks-fallas`.

Lo que el hook ya resuelve por su cuenta no se anota: una regla de capa que se cae en el fin del turno, una etapa de la compuerta del writer (esa queda en el estado del writer) o una foto que no se pudo guardar.

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

- **Lo que en Claude Code pregunta, en Codex se bloquea,** porque Codex no puede pedir confirmación desde un hook. El motivo llega con una línea más: «Codex no puede pedir confirmación desde un hook, así que este comando queda bloqueado: si hace falta, pídele al usuario que lo corra él.» En una edición, como la pausa de una desviación conocida, la línea habla de la edición (ver [En cada CLI](#en-cada-cli)).
- **Codex no tiene herramienta de lectura,** así que el hook de la primera lectura no corre ahí: los no-negociables llegan con el bloqueo de la primera edición.
- **Cada hook necesita tu confianza** en `/hooks`. Sin ella, Codex no lo corre.
- **En la prueba de humo,** el bloqueo del force push llegó así: «Command blocked by PreToolUse hook: guard-comandos bloqueó el comando…».

## En Pi

- **Lo que suma el inicio llega solo al agente principal.** En un subagente de gentle-shell, el hook de inicio no corre: ni el aviso de config rota ni el resumen del ticket activo llegan a su prompt, como en Claude Code, donde ese hook no llega a los subagentes. Los demás hooks corren igual en el subagente: los bloqueos antes de una herramienta, el primer toque, las reglas después de editar y la compuerta del writer.
- **Las skills de odd-ws se listan en el prompt solo dentro de una instancia.** Fuera de una instancia, el agente principal no ve las del plugin, y un subagente de gentle-shell no ve ni las del plugin ni las de la instancia. Siguen cargadas: `/skill:<nombre>` las abre desde cualquier carpeta, así que `/skill:bootstrap` crea una instancia y `/skill:doctor` revisa la máquina.

El porqué de cada hook, con su especificación, está en [`Doc/diseno.md`](diseno.md).
