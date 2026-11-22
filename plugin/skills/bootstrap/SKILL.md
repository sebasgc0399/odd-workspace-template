---
name: bootstrap
description: Genera una instancia de la plantilla ODD, o completa la que ya existe sin pisar nada. Solo lo invoca el usuario.
disable-model-invocation: true
---

# /odd-ws:bootstrap

Arma una spec en JSON y se la pasa a un script determinista, `bootstrap.py`, que genera la instancia. El script **nunca pisa un archivo que ya existe**: lo deja como está y lo dice en su salida. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

**Una sola parada.** Detectá todo lo que se puede detectar, armá la propuesta completa, corré el ensayo y mostrá las dos cosas juntas, con **una sola pregunta**: si se aplica así o qué cambia. Preguntá aparte solo lo que no se puede inferir, como la ruta de un repo que no aparece por ningún lado, y si la instancia va en la raíz de un repo de código (paso 2).

## 1. La raíz

- La raíz es la carpeta de la sesión, salvo que esa carpeta esté dentro de una instancia: entonces es la raíz de esa instancia (el script hace lo mismo cuando no recibe `--raiz`). No la preguntes aparte: va en la propuesta. La excepción es la raíz de un repo de código, que se pregunta siempre (paso 2).
- **Si la raíz ya tiene `workspace.config.json`, es completar una instancia.**
  - Leé `workspace.config.json` y `workspace.local.json`.
  - La spec lleva esa config **tal cual**, y como `local` lo que diga `workspace.local.json`, sin `plugin_root`.
  - Proponé solo lo que no está en la config: el nombre del proyecto.
  - No la cambies para que la spec pase. La config es del usuario y el script no la reescribe.
- **Pasar de `controles` a completo.** Si la config ya no tiene `profile` y el `CLAUDE.md` raíz es el reducido (tiene la línea `<!-- odd-ws:perfil controles -->`), el usuario está pasando a completo. Antes del ensayo, decile que lo borre si no lo editó: el script no lo reemplaza, y sin borrarlo la instancia queda con el reducido y el doctor lo avisa. Si lo editó, que lo borre igual y pase sus cambios al completo después. El resto (writers, revisores, criterios y la plantilla del ticket) lo completa el script sin pisar nada.
- **Bajar de completo a `controles` no se soporta** en esta versión: si la config de una instancia completa pasa a `"profile": "controles"`, el script no borra nada, y los writers, los revisores, los tickets y el `CLAUDE.md` completo quedan.

## 2. Detectar (instancia nueva)

Corré la detección, que no escribe nada y sale en JSON:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap.py" --proponer --raiz "<raíz>"
```

- **`repo_de_codigo`:** `true` si la raíz es la raíz de un repo git con archivos versionados y sin `workspace.config.json`. Ahí la instancia quedaría en el git de ese repo: el primer commit iría a su rama y el hook a su config. **Preguntá siempre, aparte y antes de la propuesta**, y recomendá una carpeta aparte, al lado del repo (por ejemplo `../<repo>-odd`), con el repo como repo de la instancia.
  - Si elige la carpeta aparte, esa es la raíz: volvé a correr la detección con `--raiz` en esa carpeta, y al terminar decile que abra `claude` ahí.
  - Solo si te dice que la quiere en el repo, pasá `--confirmar-repo` al ensayo y a la aplicación. Sin la bandera, el script sale con 2 sin escribir nada: nunca la pases sin ese sí.
- **`proyecto`:** el nombre de la carpeta raíz, que es tu propuesta para `proyecto.nombre`.
- **`repos`:** los repos git que lista algún `.code-workspace` de la raíz, con un nombre corto, su ruta y las extensiones de sus archivos versionados, de la más usada a la menos.
- **`mismo_lenguaje`:** los grupos de extensiones de esos repos que son de un mismo lenguaje, como `[".ts", ".mjs"]`. Son lo único que se ofrece sumar a una capa (paso 3).
- **`avisos`:** una carpeta del workspace que no es repo, un workspace que no se pudo leer. Pasáselos al usuario.
- **Sin `repos`** (no hay `.code-workspace`, o no lista repos), preguntá aparte qué repos de código trabaja y en qué ruta. Comprobá que cada ruta exista: si no, el script rechaza la spec.

Para entender el stack, mirá solo los manifiestos de la raíz de cada repo (por ejemplo `package.json`, `Cargo.toml`, `pyproject.toml` o un `.csproj`), sin recorrer el repo entero.

## 3. La propuesta y el ensayo

La respuesta va en este orden, para que en una terminal de unas 24 filas lo que el usuario decide quede a la vista junto a la pregunta, sin subir:

1. lo detectado, en una tabla, con la explicación de cada término;
2. el ensayo, agrupado, con aparte las líneas que piden atención (ver «El ensayo»);
3. el bloque «Lo que decides», con el perfil, los tickets y `own` (ver «Lo que decides»);
4. la única pregunta, justo debajo, y nada más después.

Lo detectado va en una tabla. Cada término que aparezca lleva su explicación en una línea:

- **El nombre del proyecto** (`proyecto.nombre`).
- **Los repos:** su nombre corto, que es la clave en `config.repos`, y su ruta, que va a `local.repos.<repo>.path`.
- **Las capas.** El criterio es **una capa por tecnología**, es decir, por un juego de extensiones con convenciones propias: la config separa capas por extensión, no por carpeta ni por plataforma. Lo que genera una herramienta (por ejemplo, el proyecto nativo que arma un framework móvil) no lleva capa. **Los scripts del mismo lenguaje van en la misma capa:** en un proyecto TypeScript, `.js`, `.mjs` y `.cjs` van en la capa `ts`. Todo archivo que no sea doc (`.md`, `.txt` o `.rst`) y que ninguna capa cubra lleva el triaje de `/odd-ws:revisar` a modo `completo`, así que en la propuesta nombrá las extensiones de `--proponer` que quedan sin capa y por qué. **A una capa solo se le ofrece sumar extensiones de su mismo lenguaje:** las del grupo de `mismo_lenguaje` que comparte alguna de sus extensiones. Ninguna otra se ofrece para esa capa: un `.json` o un `.yml` en un repo TypeScript queda sin capa, y es esperado. Lo que cuesta una capa, dicho tal cual: mantener su writer, su revisor, su skill y su regla, y una corrida de revisor más **solo cuando un cambio toca esa capa** (`/odd-ws:revisar` corre el revisor de cada capa tocada). Por cada capa:
  - el nombre, en minúsculas y con guiones. `diseno` está reservado para el revisor de diseño;
  - las extensiones, como `.sql`, y los repos que la usan;
  - el `rule_prefix`: el prefijo de los ids de las reglas de esa capa en la matriz (`TS-01`, `TS-02`…). Sale del nombre, en mayúsculas y dígitos, empezando por letra: `sql` da `SQL`, `capa-web` da `CW`. Tiene que ser único entre las capas.
- **El molde** (`defaults.mold_source`): `repo` quiere decir que los revisores comparan cada cambio contra el código que ya está en el repo; `propio`, que la instancia va a tener sus propios moldes. Proponé `repo`.
- **Los commits.** En la instancia, el agente commitea sin pedir aprobación: el primer commit lo hace este script, y los siguientes, las skills. Con `"ask_before_commit": true`, pide el sí antes de cada uno. Proponé dejarlo sin la clave.

`knowledge` y `hosts` son opcionales: sumalas solo si el usuario las menciona. `hosts` dice en qué CLI se trabaja la instancia (sin ella, solo Claude Code); el plugin conoce `claude-code`, `codex` y `pi`, y va dentro de `config`, como `"hosts": ["claude-code", "codex"]`.

Con la propuesta, escribí la spec y corré el ensayo **en el mismo turno**, antes de preguntar nada.

### La spec

Escribila con la herramienta Write, en UTF-8 y **fuera de la instancia**, para que no termine en un commit: en el scratch de la sesión o en una carpeta bajo `%TEMP%\claude` (en macOS, `/tmp/claude-<uid>`; en Linux, `claude-<uid>` dentro del temp del sistema). No en la raíz del temp del sistema: ahí el guard de comandos no deja borrar con `rm -rf`, y la limpieza le queda al usuario.

```json
{
  "spec_version": 1,
  "proyecto": {"nombre": "<nombre>"},
  "config": {
    "schema_version": 1,
    "defaults": {"mold_source": "repo"},
    "repos": {"<repo>": {}},
    "layers": {"<capa>": {"extensions": [".<ext>"], "repos": ["<repo>"], "rule_prefix": "<PREFIJO>"}}
  },
  "local": {"repos": {"<repo>": {"path": "<ruta absoluta>"}}}
}
```

Nunca pongas `plugin_root` en `local`: lo anota el script cuando crea `workspace.local.json`.

### El ensayo

No escribe nada:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap.py" --spec "<ruta de la spec>" --raiz "<raíz>" --ensayo --commitear
```

En la raíz de un repo de código, y solo si el usuario la eligió (paso 2), el ensayo y la aplicación llevan además `--confirmar-repo`.

Mostralo **agrupado**, no línea por línea:

- por capa: su writer, su revisor, su skill, su regla y la prueba de la regla;
- lo común: la config, `.gitignore`, `.gitattributes`, el `CLAUDE.md`, la plantilla del ticket, el revisor de diseño, los criterios, la matriz, la evidencia, los `settings.json` y el `pre-commit`. En `controles` no salen los writers, los revisores, el revisor de diseño, los criterios ni la plantilla del ticket, ni sus derivados de Codex y Pi, y el `CLAUDE.md` es el reducido;
- git: `git init`, `core.hooksPath` y el primer commit;
- **aparte y tal cual**, las líneas que piden atención: `ya existe …`, `falta en .gitignore: …`, `no se tocó …`, `commit: no se hizo; …`, `no entraría al commit …` y `no se crearía …`.

### Lo que decides

Va al final de la respuesta, después del ensayo: un bloque corto con lo que el usuario decide, una fila por decisión, en este orden, cada una con tu propuesta y una explicación corta.

- **El perfil** (`profile`): `completo` es la plantilla entera, con tickets, writers, revisores y recibos; `controles` trae solo los guards, las reglas por capa y el doctor, para quien ya tiene su propia orquestación o revisión (por ejemplo, gentle-ai con su RDD). Proponé `completo`, y pasá a `controles` si el usuario dice que ya tiene su propia orquestación o revisión. En `completo` la spec no lleva la clave; en `controles` va dentro de `config` como `"profile": "controles"`, una capa cuesta solo su skill y su regla, y la fila de los tickets no va.
- **Los tickets.** Si el usuario no usa un tracker (Jira, Azure Boards, GitHub Issues, Linear…), proponé un prefijo corto (por ejemplo, las iniciales del proyecto) en `"tickets": {"prefix": "T"}`: empieza por letra y sigue con letras, números o guion bajo, hasta 32. Con él, `/odd-ws:abrir` propone el siguiente id (`T-1`, `T-2`…) solo. Si usa un tracker, la spec no lleva `tickets`: el id de cada ticket es el de su tracker.
- **Los repos propios** (`own`): propón cada repo como del equipo. Un repo con `"own": true` es del usuario, y con él `/odd-ws:abrir` corre el `fetch` y crea el worktree del ticket sin pasarle los comandos. No va junto con `agent_readonly`.

Muéstralo así, con los valores de tu propuesta en lugar de los `<…>`:

```text
**Lo que decides**

- **Perfil:** `<perfil>`. Si ya usas tu propia orquestación o revisión (por ejemplo, gentle-ai), `controles`; si no, `completo`.
- **Tickets:** prefijo `<P>` (`<P>-1`, `<P>-2`…), o el id de tu tracker si usas uno (Jira, Azure Boards, GitHub Issues, Linear).
- **Repos tuyos** (`own`): <ninguno, o cuáles>. En uno tuyo, `/odd-ws:abrir` hace el `fetch` y crea el worktree del ticket por ti.

¿Lo aplico así, o quieres cambiar algo? Si dices que sí, también hago el primer commit.
```

Justo debajo del bloque va **la única pregunta**, y nada más después: las filas no se preguntan una por una ni con un menú aparte, porque el usuario cambia lo que quiera en su respuesta. Al completar una instancia (paso 1), su config ya fija estas tres cosas: el bloque no va, y la pregunta sigue al ensayo.

Si el usuario corrige algo, ajustá la spec, volvé a correr el ensayo y mostrá solo lo que cambió.

## 4. La aplicación

Con el sí, corré lo mismo sin `--ensayo` (con `--commitear`).

Cómo leer la salida:

- **Sale con 2:** mostrá el error tal cual.
  - Si el error es de la spec, corregí la spec y volvé al ensayo.
  - Si es de una config que ya existía, el arreglo es del usuario: decile qué falta.
  - Si dice que la raíz es la raíz de un repo de código, hacé la pregunta del paso 2 antes de seguir.
- **`no se tocó` en una línea de git** (hooks propios, un worktree enlazado, un `core.hooksPath` con otro valor): explicá en una línea qué significa. No lo cambies por tu cuenta.
- **La línea `commit:`.** `commit: <hash> con N archivos (el hook, ejecutable)` es el primer commit hecho: los archivos que el script creó, sin lo ignorado, nunca `workspace.local.json` (tiene las rutas de la máquina) y nunca un push. Si termina en `; entraron también los que ya existían: …`, sumó lo que ya estaba sin trackear y es de la instancia: el `.claude/settings.json` igual al que escribe el script (el que deja `claude plugin install --scope project`) y el `.code-workspace` de la raíz con rutas relativas. Si dice `commit: no se hizo; …` (la config pide aprobar cada commit, hay cambios stageados ajenos, la raíz está dentro de otro repo) o `commit: falló (…)`, pasale la línea al usuario tal cual: trae lo que tiene que hacer, con el `chmod` del hook.
- **`no entró al commit …`:** un `.claude/settings.json` con otro contenido, o un `.code-workspace` con alguna ruta absoluta o que no se pudo leer. Quedan sin trackear: pasale la línea al usuario tal cual, que trae el motivo, y no los commitees vos.
- **`falta en .gitignore: …`** y **`no se pudo borrar …`:** pasáselas al usuario. La última va antes de commitear.
- **`no se creó … ya existía, así que lo deriva de ahí el doctor`**: el agente de otro CLI que ya tenía su `.md`. No es un error: lo genera el doctor del paso 5, desde ese `.md`, con su arreglo.

## 5. El doctor

Corré el doctor y presentalo como dice `/odd-ws:doctor`, con los arreglos de a uno y solo con un sí:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
```

En `capas-cobertura` vale la regla del paso 3: solo ofrecé sumar a una capa las extensiones de su grupo de `mismo_lenguaje`, y las demás quedan con el aviso.

## 6. El siguiente paso

Cerrá con lo que sigue, en pocas líneas:

- **Abrir el primer ticket** con `/odd-ws:abrir`, con un cambio real y chico.
- **Que la matriz esté vacía es lo normal.** Las reglas nacen al cerrar tickets: `/odd-ws:cerrar` gradúa lo aprendido. No las cargues a mano ahora.
- **Dos atajos:** `/odd-ws:cerrar memorias` pasa a la matriz las reglas que ya están en las memorias del proyecto (las de la instancia y las de cada repo), y `/odd-ws:paquetes` trae las reglas de una capa desde otro repo git.
- **Si el repo ya tiene reglas escritas** (su `CLAUDE.md`, una carpeta de gotchas, sus docs o sus propios agentes), proponé que el primer ticket sea **sembrarlas**: abrir un ticket «sembrar las reglas de <capa>», leer esas fuentes y anotar en la bitácora cada regla con su archivo y el commit del repo, para graduarlas al cerrarlo con `/odd-ws:cerrar`. La matriz cita la bitácora del ticket, porque un archivo de un repo de código no se puede citar directo como origen.
- **En `controles`, lo de los tickets no aplica:** no hay `/odd-ws:abrir` ni cierre de tickets. Las reglas nacen con `/odd-ws:cerrar memorias` y `/odd-ws:paquetes`, y la revisión sigue siendo la de la herramienta del usuario (el doctor avisa si su RDD está apagado).

## Reglas

- No edites a mano lo que generó el script ni un archivo que ya existía. Si algo no te cierra, decíselo al usuario.
- El primer commit lo hace el script con `--commitear`, no vos: no corras `git add` ni `git commit` por tu cuenta. Con `"ask_before_commit": true` en la config, el script no commitea y el commit es del usuario.
- `git init` y `core.hooksPath` los decide el script. No los corras por tu cuenta.
- `--confirmar-repo` va solo con el sí del usuario a usar la raíz de su repo de código como instancia (paso 2), nunca para que el script deje de salir con 2.
