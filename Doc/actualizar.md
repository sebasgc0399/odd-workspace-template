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

Instalado por git, Pi fija la etiqueta de la versión, y `pi update` no la mueve. Para pasar a la versión actual, vuelve a instalar con su etiqueta:

```text
gentle-shell install git:github.com/sebasgc0399/odd-workspace-template@odd-ws--v0.17.0
```

Usa `gentle-shell --link install …` si trabajas con el home de `~/.pi/agent`. Reinstalar reemplaza la entrada y pone el clon en la etiqueta nueva. Si lo instalaste desde un clon tuyo, actualiza el clon y corre `/reload` en gentle-shell.

## Después de actualizar: el doctor

Corre `/odd-ws:doctor` (en Codex, `$doctor`). La ruta del plugin lleva la versión, y la primera sesión que abres en la instancia la pone al día sola: si `plugin_root` en `workspace.local.json` apunta a otra versión del mismo plugin (una carpeta con nombre de versión junto a la de esa sesión, como las del caché, que guarda una carpeta por versión), el hook de inicio de sesión anota la de esa sesión y se lo dice al agente en el contexto de la sesión. Así el pre-commit de la instancia corre las reglas de la versión vigente, y `plugin-root` sale OK. Si sale en FALTA igual (por ejemplo, con el hook `verificar_capa` apagado en `disabled_hooks`, o con una ruta anotada a mano fuera del caché), aplica su arreglo, `--arreglar plugin-root`, que anota la nueva.

## Después de actualizar: las plantillas de la instancia

El bootstrap no pisa el `CLAUDE.md` de la raíz, la plantilla de los tickets (`tickets/_plantilla/CLAUDE.md`), el `.githooks/pre-commit` ni la prueba de las reglas de cada capa si ya existen, porque son tuyos o ya están commiteados en la instancia. Los tickets que ya existen no hace falta tocarlos.

El ítem `plantillas` de `/odd-ws:doctor` te dice cuáles cambiaron desde la versión con que quedaron tus copias, anotada en `"plantillas"` de `workspace.config.json`:

- **Sin tocar: se reemplaza.** La copia es igual a la plantilla de alguna versión publicada, así que no tiene nada tuyo. `--arreglar plantillas` la reemplaza por la de esta versión, con el nombre de tu proyecto en el `CLAUDE.md`.
- **Editada: fusiónala a mano.** La copia tiene cambios tuyos, y el doctor no la toca. Lleva a mano lo nuevo de [`plugin/plantillas/`](../plugin/plantillas/), con la lista de abajo.
- **Primero las editadas, después el arreglo.** `--arreglar plantillas` reemplaza las sin tocar y anota la versión nueva en `"plantillas"`; desde ahí el ítem sale OK. Después, commitea las copias.
- **Sin la clave** (una instancia creada antes de la 0.14.0), el doctor dice «sin versión anotada» y deduce la versión de las copias sin tocar.
- **La primera sesión después de actualizar** ya te nombra las copias que cambiaron y te manda al doctor, si el plugin vive en una carpeta con su versión, como el caché de Claude Code o de Codex. Si la ruta no cambia con la versión, como en Pi instalado por git, ese aviso no sale: el doctor te avisa igual.

Abajo está cada cambio, por versión, para fusionar las editadas: el doctor te dice desde qué versión leer. Copia lo de esa versión y lo de las que siguen.

En la `0.2.2`:

- **El `CLAUDE.md` de la raíz**, desde `plugin/plantillas/CLAUDE.md`: la sección «Si también usas gentle-ai», entera.

En la `0.3.1`:

- **El `.githooks/pre-commit`**: cópialo encima desde `plugin/plantillas/pre-commit`. El nuevo prueba `python3`, `python` y `py`, así que también corre en macOS, Ubuntu y Debian, que no traen `python`.

En la `0.7.0`:

- **El `CLAUDE.md` de la raíz**: en «Skills del plugin», la línea de `/odd-ws:paquetes`.

En la `0.9.0`:

- **El `CLAUDE.md` de la raíz**, desde `plugin/plantillas/CLAUDE.md`:
  - en «Cómo se carga el contexto», los párrafos sobre trabajar desde la raíz (el ticket activo llega como resumen) y sobre el idioma de la conversación;
  - en «Ciclo de un ticket», el paso 3: con gentle-ai, el documento de ODD es el `CLAUDE.md` del ticket;
  - en «Repos del equipo», la autoridad de commit en la instancia y los repos con `"own": true`;
  - en «Si también usas gentle-ai», el primer ajuste: el trabajo de un ticket se anota en su carpeta;
  - en «Skills del plugin», el párrafo de los rituales.
- **La plantilla de los tickets**, desde `plugin/plantillas/ticket.md`: las secciones `## Specs`, `## Tareas` y `## Seguimientos`, y la nota de la Bitácora.

En la `0.10.0`:

- **El `CLAUDE.md` de la raíz**: en «Skills del plugin», la línea de `/odd-ws:enlaces`.

En la `0.12.0`:

- **La prueba de las reglas de cada capa**, `.claude/reglas/verificar_<capa>.tests.py`: cópiala encima desde `plugin/plantillas/reglas/verificar.tests.py`. Comprueba los `sembrado` de las reglas que bloquean (ver [calibrar las reglas que bloquean](#después-de-actualizar-calibrar-las-reglas-que-bloquean)).
- **`CLAUDE.controles.md`** es nueva, y la usa solo una instancia creada con el perfil `controles`: en una instancia que ya existe no hay nada que copiar.

En la `0.14.0`:

- **El `CLAUDE.md` de la raíz**: en «Cómo se carga el contexto», la frase sobre abrir la raíz. Ahora dice que tras `/compact` el `CLAUDE.md` de un ticket no vuelve entero, y que del ticket activo vuelve un resumen. Antes se contradecía con el párrafo del ticket activo.
- **La prueba de las reglas de cada capa**: cópiala encima desde `plugin/plantillas/reglas/verificar.tests.py`. Ahora apaga el bytecode, así que correrla a mano ya no deja `.claude/reglas/__pycache__/`.
- **La clave `"plantillas"`**: no la escribas a mano. La anota `--arreglar plantillas`, que corres después de fusionar las copias editadas: el arreglo no sabe si ya las fusionaste, y desde ahí el ítem sale OK.

En la `0.18.0`:

- **El `.githooks/pre-commit`**: cópialo encima desde `plugin/plantillas/pre-commit`. Si lo editaste, cambia `reglas.py` por `pre_commit.py` en la línea que comprueba que encontró el plugin (`[ ! -f "$plugin/scripts/reglas.py" ]`), y deja la última así: `exec "$python" "$plugin/scripts/pre_commit.py" --raiz "$raiz"`. El nuevo frena un `.env` (o un `.env.*`), una clave (`*.pem`, `*.key`, `id_rsa`, `id_ed25519`) o un `credentials*.json` stageado, salvo sus variantes `.example`, `.sample` y `.template`, y un archivo con una clave privada pegada; avisa, sin frenar, de las rutas personales (`/home/<usuario>/`, `/Users/<usuario>/`, `C:\Users\<usuario>\`). Después corre las pruebas de las reglas, como antes. Hasta que lo actualices, tu copia corre solo las pruebas.

## Después de actualizar: regenerar los writers

Corre `/odd-ws:doctor` (en Codex, `$doctor`). Si una versión cambia la plantilla de los writers, cada `writer-<capa>` sale en AVISO, con el motivo «está en la plantilla v1 y el plugin trae la v2» (o las versiones que toquen). Aplica su arreglo, `--arreglar writer-<capa>`. Si usas Codex, `codex-agentes` sale en FALTA porque sus TOML quedaron atrás: aplica también `--arreglar codex-agentes`. Si usas gentle-shell, lo mismo con `pi-agentes`: aplica `--arreglar pi-agentes`. Regenerar conserva la `description` y los bloques `<!-- instancia:... -->` de cada writer.

Mientras un writer siga en la plantilla vieja, la compuerta de cierre le pide lo que la plantilla nueva agrega. Por ejemplo, desde la plantilla 2 un writer de la plantilla 1 cierra sin `limites:`, se come el único bloqueo de la compuerta y pasa en el segundo cierre. No se traba, pero cada cierre gasta ese aviso hasta que lo regeneres.

## Después de actualizar: calibrar las reglas que bloquean

Desde la versión que trae `reglas.py --calibrar … --guardar` (el CHANGELOG lo dice), una regla bloquea solo si está calibrada: ver [Cuándo bloquea una regla](capas-y-reglas.md#cuándo-bloquea-una-regla). Es un corte duro, para los módulos de tus capas y para los paquetes de reglas: al actualizar, todo `bloqueo` llega como aviso, con el motivo `sin calibrar` y el comando a correr, hasta que lo calibres. Ese aviso lo muestra el hook de después de editar. Los hooks de cierre (`writer_stop` y `revisar_turno`) solo muestran los hallazgos junto con un bloqueo, así que un bloqueo que pasó a aviso no les da ninguna señal hasta que la regla se calibre (ver [Hooks](hooks.md#cuándo-corre-cada-uno)). Para que una regla vuelva a bloquear:

1. **Suma su `sembrado`.** En `.claude/reglas/verificar_<capa>.py`, el objeto de la regla en `REGLAS` lleva un atributo `sembrado`: un texto con el defecto que la regla tiene que atrapar. Si la regla mira la ruta del archivo o una extensión que no es la primera de la capa, el `sembrado` lleva también la ruta, relativa al repo y con `/`, porque un texto solo le llega como `sembrado<primera extensión>` en la raíz:

   ```python
   types.SimpleNamespace(id="EJ-02", sembrado={"ruta": "Migrations/0001_alta.sql", "texto": "DROP TABLE t;"})
   ```

   Un `sembrado` con otra forma es lo mismo que no tenerlo (ver [Las dos formas del `sembrado`](capas-y-reglas.md#cuándo-bloquea-una-regla)). Si el módulo no declara `REGLAS`, declárala; sin ella no se puede calibrar. Una regla de un paquete no se edita en la instancia: su `sembrado` lo declara el autor del paquete, en su repo, con una etiqueta nueva que traes con `/odd-ws:paquetes` (`actualizar`).
2. **Calibra la capa.** Corre, con una carpeta de código real de la capa (o una vacía, si todavía no hay código):

   ```text
   python3 "<plugin_root>/scripts/reglas.py" --calibrar <capa> <carpeta> --guardar
   ```

   El aviso de la regla trae este mismo comando, con el Python de tu máquina, la ruta del plugin y la carpeta ya puestas (la de una regla de la capa que ya se calibró o, si no hay ninguna, la del primer repo de la capa): cópialo y córrelo tal cual desde la raíz de la instancia, después de corregir lo que la regla marca en esa carpeta, porque la calibración cuenta también los archivos sin commitear. Calibra también los paquetes de la capa, cada uno con la huella de su lock; una capa que solo tiene paquetes también se calibra así. La salida dice qué regla puede bloquear y por qué no las demás: sin sembrado, no atrapa su sembrado, tiene aciertos en bloqueo en el corpus o está disputada.
3. **Commitea `.claude/registro/`**, junto con el módulo si le sumaste `sembrado`.

Cada cambio posterior del módulo deja vieja la calibración de su capa, y `actualizar` un paquete a otra etiqueta deja vieja la del paquete, así que se repiten los pasos 2 y 3. Si una regla calibrada bloquea algo que está bien, ábrele una disputa (`.claude/registro/disputas/<ID>.md`, ver [Las disputas](capas-y-reglas.md#las-disputas)): vuelve a avisar hasta que se arregle su chequeo. La prueba de la suite que comprueba los `sembrado` llega solo a las instancias nuevas: en una que ya existe, cópiala de `plugin/plantillas/reglas/verificar.tests.py`.
