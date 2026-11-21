# Actualizar el plugin

La versión está fijada en `plugin.json` y la actualización automática viene apagada, así que se actualiza a mano, entre tickets. Qué trae cada versión está en el [CHANGELOG](../CHANGELOG.md).

## En Claude Code

```text
claude plugin marketplace update odd-workspace-template
claude plugin update odd-ws@odd-workspace-template
```

Después, `/plugin` dentro de una sesión debe mostrar la versión nueva, con la pestaña de errores vacía. Los dos comandos van juntos: sin el primero, el clon local del marketplace no ve la versión nueva, y la instancia sigue en la anterior sin avisar. En una instancia real pasó eso: corrió la `0.7.0` con la `0.8.0` ya publicada.

## En Codex

```text
codex plugin marketplace upgrade odd-workspace-template
codex plugin add odd-ws@odd-workspace-template
```

Después, abre `codex` y vuelve a confiar los hooks en `/hooks`. `/odd-ws:doctor` (en Codex, `$doctor`) avisa si a alguno le falta la confianza.

## En gentle-shell (Pi)

Instalado por git, Pi fija la etiqueta de la versión, y `pi update` no la mueve. Para pasar a otra versión, vuelve a instalar con la etiqueta nueva:

```text
gentle-shell install git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v<versión nueva>
```

Usa `gentle-shell --link install …` si trabajas con el home de `~/.pi/agent`. Reinstalar reemplaza la entrada y pone el clon en la etiqueta nueva. Si lo instalaste desde un clon tuyo, actualiza el clon y corre `/reload` en gentle-shell.

## Después de actualizar: las plantillas de la instancia

El bootstrap no pisa el `CLAUDE.md` de la raíz ni la plantilla de los tickets (`tickets/_plantilla/CLAUDE.md`) si ya existen, porque son tuyos y los vas ajustando. Cuando una versión cambia esas plantillas, el CHANGELOG lo dice, y lo nuevo se copia a mano desde [`plugin/plantillas/`](../plugin/plantillas/) de esa versión. Los tickets que ya existen no hace falta tocarlos.

En la `0.9.0`:

- **El `CLAUDE.md` de la raíz**, desde `plugin/plantillas/CLAUDE.md`:
  - en «Cómo se carga el contexto», los párrafos sobre trabajar desde la raíz (el ticket activo llega como resumen) y sobre el idioma de la conversación;
  - en «Ciclo de un ticket», el paso 3: con gentle-ai, el documento de ODD es el `CLAUDE.md` del ticket;
  - en «Repos del equipo», la autoridad de commit en la instancia y los repos con `"own": true`;
  - en «Si también usas gentle-ai», el primer ajuste: el trabajo de un ticket se anota en su carpeta;
  - en «Skills del plugin», el párrafo de los rituales.
- **La plantilla de los tickets**, desde `plugin/plantillas/ticket.md`: las secciones `## Specs`, `## Tareas` y `## Seguimientos`, y la nota de la Bitácora.

## Después de actualizar: regenerar los writers

Corre `/odd-ws:doctor` (en Codex, `$doctor`). Si una versión cambia la plantilla de los writers, cada `writer-<capa>` sale en AVISO, con el motivo «está en la plantilla v1 y el plugin trae la v2» (o las versiones que toquen). Aplica su arreglo, `--arreglar writer-<capa>`. Si usas Codex, `codex-agentes` sale en FALTA porque sus TOML quedaron atrás: aplica también `--arreglar codex-agentes`. Si usas gentle-shell, lo mismo con `pi-agentes`: aplica `--arreglar pi-agentes`. Regenerar conserva la `description` y los bloques `<!-- instancia:... -->` de cada writer.

Mientras un writer siga en la plantilla vieja, la compuerta de cierre le pide lo que la plantilla nueva agrega. Por ejemplo, desde la plantilla 2 un writer de la plantilla 1 cierra sin `limites:`, se come el único bloqueo de la compuerta y pasa en el segundo cierre. No se traba, pero cada cierre gasta ese aviso hasta que lo regeneres.

## Después de actualizar: calibrar las reglas que bloquean

Desde la versión que trae `reglas.py --calibrar … --guardar` (el CHANGELOG lo dice), una regla de capa bloquea solo si está calibrada: ver [Cuándo bloquea una regla](capas-y-reglas.md#cuándo-bloquea-una-regla). Es un corte duro: al actualizar, todo `bloqueo` de los módulos de tu instancia llega como aviso, con el motivo `sin calibrar` y el comando a correr, hasta que lo calibres. Para que una regla vuelva a bloquear:

1. **Suma su `sembrado`.** En `.claude/reglas/verificar_<capa>.py`, el objeto de la regla en `REGLAS` lleva un atributo `sembrado`: un texto con el defecto que la regla tiene que atrapar. Si el módulo no declara `REGLAS`, declárala; sin ella no se puede calibrar.
2. **Calibra la capa.** Corre, con una carpeta de código real de la capa (o una vacía, si todavía no hay código):

   ```text
   python3 "<plugin_root>/scripts/reglas.py" --calibrar <capa> <carpeta> --guardar
   ```

   La salida dice qué regla puede bloquear y por qué no las demás: sin sembrado, no atrapa su sembrado o tiene aciertos en bloqueo en el corpus.
3. **Commitea `.claude/registro/`**, junto con el módulo si le sumaste `sembrado`.

Cada cambio posterior del módulo deja vieja la calibración de su capa, así que se repiten los pasos 2 y 3. Los paquetes de reglas siguen bloqueando como antes, sin calibrar. La prueba de la suite que comprueba los `sembrado` llega solo a las instancias nuevas: en una que ya existe, cópiala de `plugin/plantillas/reglas/verificar.tests.py`.
