---
name: bootstrap
description: Genera una instancia de la plantilla ODD con una sola propuesta, o completa una que ya existe sin pisar nada (config, writers, revisores, skills de capa, reglas vacías, CLAUDE.md, plantilla de ticket, pre-commit, settings.json, git init, core.hooksPath y el primer commit). Usar cuando el usuario pide arrancar una instancia nueva o completar la que tiene.
disable-model-invocation: true
---

# /odd-ws:bootstrap

Arma una spec en JSON y se la pasa a un script determinista, `bootstrap.py`, que genera la instancia. El script **nunca pisa un archivo que ya existe**: lo deja como está y lo dice en su salida. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

**Una sola parada.** Detectá todo lo que se puede detectar, armá la propuesta completa, corré el ensayo y mostrá las dos cosas juntas, con **una sola pregunta**: si se aplica así o qué cambia. Preguntá aparte solo lo que no se puede inferir, como la ruta de un repo que no aparece por ningún lado.

## 1. La raíz

- La raíz es la carpeta de la sesión, salvo que esa carpeta esté dentro de una instancia: entonces es la raíz de esa instancia (el script hace lo mismo cuando no recibe `--raiz`). No la preguntes aparte: va en la propuesta.
- **Si la raíz ya tiene `workspace.config.json`, es completar una instancia.**
  - Leé `workspace.config.json` y `workspace.local.json`.
  - La spec lleva esa config **tal cual**, y como `local` lo que diga `workspace.local.json`, sin `plugin_root`.
  - Proponé solo lo que no está en la config: el nombre del proyecto.
  - No la cambies para que la spec pase. La config es del usuario y el script no la reescribe.

## 2. Detectar (instancia nueva)

Corré la detección, que no escribe nada y sale en JSON:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap.py" --proponer --raiz "<raíz>"
```

- **`proyecto`:** el nombre de la carpeta raíz, que es tu propuesta para `proyecto.nombre`.
- **`repos`:** los repos git que lista algún `.code-workspace` de la raíz, con un nombre corto, su ruta y las extensiones de sus archivos versionados, de la más usada a la menos.
- **`avisos`:** una carpeta del workspace que no es repo, un workspace que no se pudo leer. Pasáselos al usuario.
- **Sin `repos`** (no hay `.code-workspace`, o no lista repos), esa es la única pregunta aparte: qué repos de código trabaja y en qué ruta. Comprobá que cada ruta exista: si no, el script rechaza la spec.

Para entender el stack, mirá solo los manifiestos de la raíz de cada repo (por ejemplo `package.json`, `Cargo.toml`, `pyproject.toml` o un `.csproj`), sin recorrer el repo entero.

## 3. La propuesta y el ensayo

Armá la propuesta completa en una tabla. Cada término que aparezca lleva su explicación en una línea:

- **El nombre del proyecto** (`proyecto.nombre`).
- **Los repos:** su nombre corto, que es la clave en `config.repos`, y su ruta, que va a `local.repos.<repo>.path`. Proponé cada uno como del equipo y explicá `own` en una línea: un repo con `"own": true` es del usuario, y con él `/odd-ws:abrir` corre el `fetch` y crea el worktree del ticket sin pasarle los comandos. No va junto con `agent_readonly`.
- **Las capas.** El criterio es **una capa por tecnología**, es decir, por un juego de extensiones con convenciones propias: la config separa capas por extensión, no por carpeta ni por plataforma. Lo que genera una herramienta (por ejemplo, el proyecto nativo que arma un framework móvil) no lleva capa. Lo que cuesta una capa, dicho tal cual: mantener su writer, su revisor, su skill y su regla, y una corrida de revisor más **solo cuando un cambio toca esa capa** (`/odd-ws:revisar` corre el revisor de cada capa tocada). Por cada capa:
  - el nombre, en minúsculas y con guiones. `diseno` está reservado para el revisor de diseño;
  - las extensiones, como `.sql`, y los repos que la usan;
  - el `rule_prefix`: el prefijo de los ids de las reglas de esa capa en la matriz (`TS-01`, `TS-02`…). Sale del nombre, en mayúsculas y dígitos, empezando por letra: `sql` da `SQL`, `capa-web` da `CW`. Tiene que ser único entre las capas.
- **El molde** (`defaults.mold_source`): `repo` quiere decir que los revisores comparan cada cambio contra el código que ya está en el repo; `propio`, que la instancia va a tener sus propios moldes. Proponé `repo`.
- **Los tickets.** Si el usuario no usa un tracker, proponé un prefijo corto (por ejemplo, las iniciales del proyecto) en `"tickets": {"prefix": "T"}`: empieza por letra y sigue con letras, números o guion bajo, hasta 32. Con él, `/odd-ws:abrir` propone el siguiente id (`T-1`, `T-2`…) solo.
- **Los commits.** En la instancia, el agente commitea sin pedir aprobación: el primer commit lo hace este script, y los siguientes, las skills. Con `"ask_before_commit": true`, pide el sí antes de cada uno. Proponé dejarlo sin la clave.

`knowledge` y `hosts` son opcionales: sumalas solo si el usuario las menciona. `hosts` dice en qué CLI se trabaja la instancia (sin ella, solo Claude Code); el plugin conoce `claude-code`, `codex` y `pi`, y va dentro de `config`, como `"hosts": ["claude-code", "codex"]`.

Con la propuesta, escribí la spec y corré el ensayo **en el mismo turno**, antes de preguntar nada.

### La spec

Escribila con la herramienta Write, en UTF-8 y **fuera de la instancia** (en el scratch de la sesión o en el temp del sistema), para que no termine en un commit:

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

Mostralo **agrupado**, no línea por línea:

- por capa: su writer, su revisor, su skill, su regla y la prueba de la regla;
- lo común: la config, `.gitignore`, `.gitattributes`, el `CLAUDE.md`, la plantilla del ticket, el revisor de diseño, los criterios, la matriz, la evidencia, los `settings.json` y el `pre-commit`;
- git: `git init`, `core.hooksPath` y el primer commit;
- **aparte y tal cual**, las líneas que piden atención: `ya existe …`, `falta en .gitignore: …`, `no se tocó …`, `commit: no se hizo; …` y `no se crearía …`.

Después, **la única pregunta**: ¿se aplica así, o qué cambia? Ese sí cubre también el primer commit. Si el usuario corrige algo, ajustá la spec, volvé a correr el ensayo y mostrá solo lo que cambió.

## 4. La aplicación

Con el sí, corré lo mismo sin `--ensayo` (con `--commitear`).

Cómo leer la salida:

- **Sale con 2:** mostrá el error tal cual.
  - Si el error es de la spec, corregí la spec y volvé al ensayo.
  - Si es de una config que ya existía, el arreglo es del usuario: decile qué falta.
- **`no se tocó` en una línea de git** (hooks propios, un worktree enlazado, un `core.hooksPath` con otro valor): explicá en una línea qué significa. No lo cambies por tu cuenta.
- **La línea `commit:`.** `commit: <hash> con N archivos (el hook, ejecutable)` es el primer commit hecho: solo los archivos que el script creó, sin lo ignorado, y nunca un push. Si dice `commit: no se hizo; …` (la config pide aprobar cada commit, hay cambios stageados ajenos, la raíz está dentro de otro repo) o `commit: falló (…)`, pasale la línea al usuario tal cual: trae lo que tiene que hacer, con el `chmod` del hook.
- **`falta en .gitignore: …`** y **`no se pudo borrar …`:** pasáselas al usuario. La última va antes de commitear.
- **`no se creó … ya existía, así que lo deriva de ahí el doctor`**: el agente de otro CLI que ya tenía su `.md`. No es un error: lo genera el doctor del paso 5, desde ese `.md`, con su arreglo.

## 5. El doctor

Corré el doctor y presentalo como dice `/odd-ws:doctor`, con los arreglos de a uno y solo con un sí:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
```

## 6. El siguiente paso

Cerrá con lo que sigue, en pocas líneas:

- **Abrir el primer ticket** con `/odd-ws:abrir`, con un cambio real y chico.
- **Que la matriz esté vacía es lo normal.** Las reglas nacen al cerrar tickets: `/odd-ws:cerrar` gradúa lo aprendido. No las cargues a mano ahora.
- **Dos atajos:** `/odd-ws:cerrar memorias` pasa a la matriz las reglas que ya están en las memorias del proyecto (las de la instancia y las de cada repo), y `/odd-ws:paquetes` trae las reglas de una capa desde otro repo git.
- **Si el repo ya tiene reglas escritas** (su `CLAUDE.md`, una carpeta de gotchas, sus docs o sus propios agentes), proponé que el primer ticket sea **sembrarlas**: abrir un ticket «sembrar las reglas de <capa>», leer esas fuentes y anotar en la bitácora cada regla con su archivo y el commit del repo, para graduarlas al cerrarlo con `/odd-ws:cerrar`. La matriz cita la bitácora del ticket, porque un archivo de un repo de código no se puede citar directo como origen.

## Reglas

- No edites a mano lo que generó el script ni un archivo que ya existía. Si algo no te cierra, decíselo al usuario.
- El primer commit lo hace el script con `--commitear`, no vos: no corras `git add` ni `git commit` por tu cuenta. Con `"ask_before_commit": true` en la config, el script no commitea y el commit es del usuario.
- `git init` y `core.hooksPath` los decide el script. No los corras por tu cuenta.
