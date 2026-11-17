---
name: bootstrap
description: Genera una instancia de la plantilla ODD con una entrevista, o completa una que ya existe sin pisar nada (config, writers, revisores, skills de capa, reglas vacías, CLAUDE.md, plantilla de ticket, pre-commit, settings.json, git init y core.hooksPath). Usar cuando el usuario pide arrancar una instancia nueva o completar la que tiene.
disable-model-invocation: true
---

# /odd-ws:bootstrap

La entrevista arma una spec en JSON y se la pasa a un script determinista, `bootstrap.py`, que genera la instancia. El script **nunca pisa un archivo que ya existe**: lo deja como está y lo dice en su salida. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

## 1. La raíz

- La raíz es la carpeta de la sesión, salvo que esa carpeta esté dentro de una instancia: entonces es la raíz de esa instancia (el script hace lo mismo cuando no recibe `--raiz`). Decile al usuario qué carpeta vas a usar y confirmala antes de seguir.
- **Si la raíz ya tiene `workspace.config.json`, es completar una instancia.**
  - Leé `workspace.config.json` y `workspace.local.json`.
  - La spec lleva esa config **tal cual**, y como `local` lo que diga `workspace.local.json`, sin `plugin_root`.
  - Preguntá solo lo que no está en la config: el nombre del proyecto.
  - No la cambies para que la spec pase. La config es del usuario y el script no la reescribe.

## 2. La entrevista (instancia nueva)

Una pregunta por vez, cada una con tu propuesta. Esperá la respuesta antes de la siguiente.

1. **El nombre del proyecto** (`proyecto.nombre`). Proponé el nombre de la carpeta raíz.
2. **Los repos.** Por cada repo hacen falta dos datos:
   - un nombre corto, que es la clave en `config.repos`;
   - su ruta absoluta en esta máquina, que va a `local.repos.<repo>.path`.

   Antes de seguir, comprobá que la ruta exista: si no, el script rechaza la spec.
3. **Las capas.** Por cada capa:
   - el nombre, en minúsculas y con guiones. `diseno` está reservado para el revisor de diseño;
   - las extensiones, como `.sql`;
   - los repos que la usan;
   - el `rule_prefix`. Derivalo del nombre (mayúsculas y dígitos, empezando por letra) y confirmalo con el usuario: `sql` da `SQL`, `capa-web` da `CW`. Tiene que ser único entre las capas.
4. **De dónde salen los moldes** (`defaults.mold_source`). Proponé `repo`: el molde es el código vigente del repo. La otra opción es `propio`, si la instancia va a tener moldes propios.

La sección `knowledge` es opcional. Preguntala solo si el usuario la menciona.

La clave `hosts` también es opcional: dice en qué CLI se trabaja la instancia. Sin ella, la instancia es solo de Claude Code. Preguntala solo si el usuario menciona otro CLI. Hoy el plugin conoce `claude-code` y `codex`, y va dentro de `config`, como `"hosts": ["claude-code", "codex"]`: una lista sin repetidos. Con `codex`, el script también genera `.codex/agents/` y `.codex/config.toml`.

La clave `tickets` también es opcional: el prefijo de los ids de los tickets cuando el usuario no usa un tracker. Preguntá si usa uno. Si no, proponé un prefijo corto (por ejemplo, las iniciales del proyecto) y ponelo dentro de `config`, como `"tickets": {"prefix": "T"}`: empieza por letra y sigue con letras, números o guion bajo, hasta 32. Con ella, `/odd-ws:abrir` propone el siguiente id (`T-1`, `T-2`…) sin preguntarlo.

Dos claves más, opcionales, sobre qué hace el agente sin preguntar:

- **`ask_before_commit`:** en la instancia, el agente commitea sin pedir aprobación (el primer commit del bootstrap, y los de las skills). Con `"ask_before_commit": true`, pide el sí antes de cada uno. Preguntala solo si el usuario quiere aprobar cada commit.
- **`own` de cada repo:** `"repos": {"<repo>": {"own": true}}` marca un repo como del usuario, que nadie más trabaja. Preguntá si cada repo es suyo o del equipo. No va junto con `agent_readonly`.

## 3. La spec

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

## 4. Ensayo, sí y aplicación

1. Corré el ensayo, que no escribe nada:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap.py" --spec "<ruta de la spec>" --raiz "<raíz>" --ensayo --commitear
   ```

2. Mostrá el plan tal cual sale: `crearía …`, `ya existe …`, lo que haría git y la línea `commit:`.
3. Pedí un sí explícito. Ese sí cubre también el primer commit.
4. Con el sí, corré lo mismo sin `--ensayo` (con `--commitear`).

Cómo leer la salida:

- **Sale con 2:** mostrá el error tal cual.
  - Si el error es de la spec, corregí la spec y volvé al ensayo.
  - Si es de una config que ya existía, el arreglo es del usuario: decile qué falta.
- **`no se tocó` en una línea de git** (hooks propios, un worktree enlazado, un `core.hooksPath` con otro valor): explicá en una línea qué significa. No lo cambies por tu cuenta.
- **La línea `commit:`.** `commit: <hash> con N archivos (el hook, ejecutable)` es el primer commit hecho: solo los archivos que el script creó, sin lo ignorado, y nunca un push. Si dice `commit: no se hizo; …` (la config pide aprobar cada commit, hay cambios stageados ajenos, la raíz está dentro de otro repo) o `commit: falló (…)`, pasale la línea al usuario tal cual: trae lo que tiene que hacer, con el `chmod` del hook.
- **`falta en .gitignore: …`** y **`no se pudo borrar …`:** pasáselas al usuario. La última va antes de commitear.
- **`no se creó … ya existía, así que lo deriva de ahí el doctor`** (o `no se crearía …` en el ensayo): el TOML de Codex de un agente que ya tenía su `.md`. No es un error: lo genera el doctor del paso 5, desde ese `.md`, con su arreglo.

## 5. El doctor

Al final, corré el doctor y presentalo como dice `/odd-ws:doctor`, con los arreglos de a uno y solo con un sí:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
```

## Reglas

- No edites a mano lo que generó el script ni un archivo que ya existía. Si algo no te cierra, decíselo al usuario.
- El primer commit lo hace el script con `--commitear`, no vos: no corras `git add` ni `git commit` por tu cuenta. Con `"ask_before_commit": true` en la config, el script no commitea y el commit es del usuario.
- `git init` y `core.hooksPath` los decide el script. No los corras por tu cuenta.
