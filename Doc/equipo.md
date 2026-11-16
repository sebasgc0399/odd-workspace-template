# Trabajar en equipo

Una instancia se comparte como cualquier repo: las convenciones viajan con ella, se revisan en un pull request y llegan a cada dev con `git pull`. No hace falta un servidor. Lo que es de cada máquina (las rutas, la instalación del plugin, el estado de las sesiones) queda fuera del repo.

Esta guía es para un equipo que ya tiene su instancia. Para crearla, empieza por la [instalación](../README.md#instalación).

## Qué viaja y qué no

| Viaja en el repo de la instancia | Queda en cada máquina |
|---|---|
| `workspace.config.json`: los repos, las capas y los CLI | `workspace.local.json`: la ruta de cada repo y `plugin_root`. El bootstrap lo pone en `.gitignore` |
| `.claude/reglas/`: `matriz.csv`, `evidencia.md` y `verificar_<capa>.py` con su prueba, y los paquetes de reglas con su lock (`paquetes/` y `paquetes.json`) | `.claude/estado/`: el estado de las sesiones, también en `.gitignore` |
| `.claude/skills/` (`capa-<capa>` y `criterios`) y `.claude/agents/` | `core.hooksPath`: es config de git, y `git clone` no la copia |
| `.githooks/pre-commit` | La instalación del plugin: Claude Code la registra para la carpeta donde la hiciste |
| `.claude/settings.json`, con el plugin habilitado | Las memorias de cada uno, y el registro de las que ya viste en `/odd-ws:cerrar memorias` |
| `CLAUDE.md` y `tickets/` | |

## Al clonar la instancia

Cada dev hace esto una vez por clon:

1. **Instala el plugin en tu clon.** El plugin ya viene habilitado en `.claude/settings.json`, pero la instalación es de cada máquina y de cada carpeta. Desde la raíz del clon:

   ```text
   claude plugin marketplace add sebasgc0399/odd-workspace-template
   claude plugin install odd-ws@odd-workspace-template --scope project
   ```

   No cambia ningún archivo del repo: `git status` sigue limpio.
2. **Abre `claude` en la raíz y corre `/odd-ws:doctor`.** En un clon recién hecho marca tres FALTA:

   | Ítem | Qué falta | Cómo se arregla |
   |---|---|---|
   | `plugin-root` | `workspace.local.json` no existe, así que el pre-commit no encuentra el plugin | `--arreglar plugin-root`: crea el archivo con la ruta del plugin |
   | `config` | La ruta de cada repo en tu máquina | A mano, en `workspace.local.json` (abajo) |
   | `instancia-hooks` | `core.hooksPath`: sin él, en tu clon no corre el pre-commit | `--arreglar instancia-hooks` |

   El doctor arregla de a un ítem, con tu sí.
3. **Agrega tus rutas.** Por cada repo de `workspace.config.json`, su carpeta en tu máquina, con ruta absoluta:

   ```json
   {
     "plugin_root": "<la que escribió el doctor>",
     "repos": {
       "app": { "path": "D:/code/app" }
     }
   }
   ```

4. **Corre el doctor otra vez** hasta que no quede ninguna FALTA. `git status` tiene que seguir limpio: `workspace.local.json` está en `.gitignore`.

## Graduar una regla

Gradúa quien cierra el ticket, con `/odd-ws:cerrar`, o quien corre `/odd-ws:cerrar memorias`. La skill escribe la fila de la matriz, la regla en su destino y su evidencia, y deja un commit en la rama en la que estás. No empuja: el push y el pull request son tuyos.

**Gradúa desde un `main` al día.** El ID de la regla nueva es el siguiente libre de la matriz de tu rama. Si dos devs gradúan a la vez, los dos sacan el mismo ID, y el segundo pull request choca en `matriz.csv`, en `.claude/skills/capa-<capa>/SKILL.md` y en `evidencia.md`.

**Si choca, no unas las dos filas.** Quedarían dos reglas con el mismo ID, y el pre-commit no lo frena. Rehaz la graduación sobre el `main` nuevo:

1. Trae `main` (`git fetch origin`).
2. Deja tu rama sin el commit de la graduación. Si la rama solo tenía ese commit: `git reset --hard origin/main`.
3. Vuelve a correr `/odd-ws:cerrar`. Calcula el siguiente ID libre con la matriz de `main`.
4. Empuja la rama otra vez (`git push --force-with-lease origin <tu rama>`).

## Revisar la matriz en un pull request

El pre-commit de la instancia corre las pruebas de las reglas de cada capa (`reglas.py --test`), pero no valida la matriz: una fila con un ID repetido pasa en verde. La matriz la revisa quien revisa el pull request.

En la rama del pull request, por cada capa que toca:

```text
python3 "<plugin_root>/scripts/matriz.py" --destinos --capa <capa>
python3 "<plugin_root>/scripts/matriz.py" --severidad --capa <capa>
```

`<plugin_root>` es el de tu `workspace.local.json`. Los dos tienen que salir con 0, con `esquema=0 fallas=0` en su línea `RESUMEN`. Con dos filas `SQ-01`, por ejemplo, `--destinos` sale con 1:

```text
ESQUEMA fila 3: id duplicado 'SQ-01' (ya en fila 2)
FALLA SQ-01: aparece 2 veces en .claude/skills/capa-sql/SKILL.md (dentro del bloque no-negociables) (debe ser exactamente 1)
```

Además de los dos comandos:

- [ ] La regla dice lo que el equipo quiere exigir, y su destino es el que corresponde (un chequeo, los no-negociables, el revisor…).
- [ ] La fila, la regla y la evidencia no copian nada que no deba quedar en el repo. En la instancia no corre ningún barrido de confidencialidad: lo que se aprueba es lo que queda escrito.

**Después del merge,** cada dev recibe las reglas con `git pull`: la primera edición en una capa le entrega sus no-negociables, con las reglas nuevas.

## Paquetes de reglas

Un [paquete de reglas](capas-y-reglas.md#paquetes-de-reglas) viaja en el repo como las demás reglas: su carpeta en `.claude/reglas/paquetes/` y el lock, `.claude/reglas/paquetes.json`.

- **Lo importa uno,** con `/odd-ws:paquetes`, y lo sube en un pull request. El pull request muestra el código copiado y el lock con la etiqueta y el commit.
- **Quien revisa lee el código del paquete,** sobre todo `verificar.py` y su suite: corren en los hooks y en el pre-commit de cada dev. Esa lectura es la barrera.
- **Los demás lo reciben con `git pull`.** No lo importan de nuevo ni necesitan acceso al repo del paquete. En cada clon, `/odd-ws:doctor` compara la huella de lo copiado con la del lock.
- **La fuente, una URL.** Una ruta local se guarda absoluta y solo existe en la máquina de quien importó: en otro clon, `actualizar` no la encuentra. Para un repo privado, quien actualiza se autentica antes con git.
- **Nadie edita lo copiado.** Un cambio va al repo del paquete, con una etiqueta nueva, y entra con `actualizar` en otro pull request.

## Con engram

engram es la memoria del agente, y con su sincronización el equipo puede compartir esas memorias. odd-ws no sincroniza nada. El reparto es este:

1. **engram comparte las memorias** del proyecto entre los devs.
2. **`/odd-ws:cerrar memorias` gradúa** a la matriz las que suenan a regla, con tu sí.
3. **Las reglas viajan por git,** con el pull request y la revisión de arriba.

Dos cosas que importan en equipo:

- **El proyecto es el mismo en todos los clones.** engram lo saca del remoto de git, no del nombre de la carpeta, así que dos clones con carpetas distintas consultan el mismo proyecto.
- **El origen de la fila es el `sync_id` de la memoria** (`memoria:engram-obs-…`), que es el mismo en todas las máquinas. El número de la memoria (`#12`) no: es de cada máquina, y la misma memoria tiene otro en la de un compañero. Una fila escrita antes con el número solo se reconoce como graduada en la máquina que la escribió.

Esto se probó compartiendo las memorias con `engram sync` entre dos almacenes. engram cloud no se probó.
