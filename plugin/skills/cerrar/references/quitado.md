# Lo que el ticket quitó: si puede volver, y la regla que lo frena

Detalle del paso 2 del `SKILL.md` de `/odd-ws:cerrar`. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`, y los pasos que se citan son los del `SKILL.md`.

El porqué de las líneas que se editan sale de su blame, y el blame no ve el código borrado. Lo que un ticket quita (una dependencia, un archivo, un patrón) puede volver en el ticket siguiente sin que nadie lo decida. Al cerrar, cada cosa quitada se decide una vez: puede volver, o vuelve como regla.

## El script

```bash
python3 "<S>/quitado.py" --repo <ruta>
python3 "<S>/quitado.py" --repo <ruta>#<base>
```

- **`--repo`** se repite, uno por repo que tocó el ticket: la ruta de su worktree si lo usó (lo dice «Worktree y rama»), o la del repo, con la rama del ticket en la copia de trabajo. Cuenta lo commiteado y lo que todavía no, contra la base; un archivo sin trackear no cuenta.
- **La base** es el merge-base con la rama de `origin/HEAD`, o la que va después de `#`. No es la base sellada de una revisión, que escondería lo que el ticket quitó antes de esa revisión.
- **Lo que lista**, por repo:
  - los archivos borrados, sin los renombres: un archivo que se movió no se quitó;
  - las dependencias que estaban en la base de un manifiesto y ya no están: `package.json` (`dependencies` y `devDependencies`), `requirements*.txt`, `pyproject.toml` (`dependencies` y `optional-dependencies` de `[project]`), `go.mod` (sus `require`), `*.csproj` (`PackageReference`), `build.gradle` y `build.gradle.kts` (las declaraciones como `implementation`, `api` o `testImplementation`) y `Cargo.toml` (`[dependencies]` y `[dev-dependencies]`). Cada una sale con la línea que la declaraba en la base. Subir la versión, o pasarla de una sección a otra, no es quitarla. Un manifiesto borrado sale como archivo, sin sus dependencias;
  - un **aviso** por cada manifiesto que no pudo leer (un JSON roto, o un TOML con un Python anterior a la 3.11): ese manifiesto no se revisó, no está limpio.
- **Un diff vacío** sale en una línea. Si el ticket tocó ese repo y ya se mergeó, el merge-base es su propia punta: vuelve a correrlo con `#<base>`, la de antes del ticket (el padre de su primer commit, o la que anota su bitácora). Si no la sabes, pregúntala; no la adivines.
- **Sale con 0** si corrió, con ítems o sin ellos, y con 2 por un error de uso o de entorno (un repo o una base que no existen, un repo sin `origin/HEAD` y sin `#<base>`): muestra el mensaje y sigue el cierre sin este paso, diciéndolo.
- **Es de solo lectura:** no escribe, no stagea ni commitea nada, así que también vale en un repo del equipo.

## La pregunta

Muestra la lista **numerada**, con una sola numeración para todos los repos, y pregunta **una sola vez** cuáles no pueden volver: «números, o "ninguno"». Si de alguno no lo sabe, lo dice en la misma respuesta.

- **Los que no nombra pueden volver:** no pasa nada más. Si el porqué de alguno le sirve a otro ticket, va a la bitácora.
- **Los que nombra no pueden volver:** pide el porqué solo de esos, en una línea cada uno, con las palabras del usuario. Cada porqué se anota en las Decisiones del ticket y es el origen de su fila, que `references/matriz.md` pide commiteado antes.
- **Los que no sabe:** quedan como pendientes en la bitácora, sin regla.

**Un patrón no se detecta solo:** una llamada, un estilo o una forma de código que el ticket sacó. Pregunta también si el ticket quitó alguno que no debería volver; si el usuario nombra uno, sigue como con una dependencia, con el texto del patrón en lugar de la línea.

## La regla que lo frena

Lo que no puede volver entra a la propuesta del paso 4 como una fila de la matriz con `destino` `chequeo`, y su regla va en `.claude/reglas/verificar_<capa>.py`, por la graduación de siempre: las columnas, el script que agrega la fila, la evidencia y la calibración están en `references/matriz.md`. Lo propio de este caso:

- **La capa** es la que cubre el archivo, por su extensión o su ruta. Si ninguna lo cubre (un `package.json` en una instancia sin una capa con `.json`), el chequeo nunca lo vería: dilo, y propón la regla como `pasiva` o `criterios`, que leen quien escribe y quien revisa. Sumar la extensión a una capa cambia qué archivos ve esa capa entera, así que lo decide el usuario, a mano en `workspace.config.json`.
- **El `sembrado`** es lo que lo vuelve a agregar, con su ruta, porque la regla mira el archivo: para una dependencia, `{"ruta": "<manifiesto>", "texto": "<la línea que lista el script>"}`, por ejemplo `{"ruta": "package.json", "texto": "\"lodash\": \"^4.17.21\","}`; para un archivo, `{"ruta": "<el archivo quitado>", "texto": "<una línea suya en la base>"}`.
- **La regla** mira la ruta y lo agregado: para una dependencia, que `ctx["relativa"]` sea el manifiesto y que una línea de `ctx["agregadas"]` la nombre; para un archivo, `ctx["es_nuevo"]` con `ctx["relativa"]` igual al archivo quitado. Pide `bloqueo`, y su mensaje dice qué no vuelve y por qué.
- **El porqué** va en el `motivo` de la fila y en su evidencia de `.claude/reglas/evidencia.md`, con el commit que lo quitó.

Por ejemplo, para una dependencia. El ID va una sola vez, con la severidad en su mismo segmento, como piden los chequeos de `matriz.py`:

```python
import re
import types

SIN_LODASH = types.SimpleNamespace(id="EJ-07", severidad="WARNING", sembrado={"ruta": "package.json", "texto": "\"lodash\": \"^4.17.21\","})
REGLAS = (SIN_LODASH,)


def verificar(ctx):
    if ctx["relativa"] != "package.json":
        return []
    return [{"id": SIN_LODASH.id, "modo": "bloqueo", "severidad": SIN_LODASH.severidad, "linea": n, "fragmento": texto.strip(),
             "mensaje": "lodash se quitó a propósito: no vuelve sin decidirlo de nuevo"}
            for n, texto in ctx["agregadas"] if re.search(r'"lodash"\s*:', texto)]
```
