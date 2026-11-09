---
name: bootstrap
description: Genera una instancia de la plantilla ODD con una entrevista, o completa una que ya existe sin pisar nada (config, writers, revisores, skills de capa, reglas vacías, CLAUDE.md, plantilla de ticket, pre-commit, settings.json, git init y core.hooksPath). Usar cuando el usuario pide arrancar una instancia nueva o completar la que tiene.
disable-model-invocation: true
---

# /odd-ws:bootstrap

La entrevista arma una spec en JSON y se la pasa a un script determinista, `bootstrap.py`, que genera la instancia. El script **nunca pisa un archivo que ya existe**: lo deja como está y lo dice en su salida.

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
   python "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap.py" --spec "<ruta de la spec>" --raiz "<raíz>" --ensayo
   ```

2. Mostrá el plan tal cual sale: `crearía …`, `ya existe …` y lo que haría git.
3. Pedí un sí explícito.
4. Con el sí, corré lo mismo sin `--ensayo`.

Cómo leer la salida:

- **Sale con 2:** mostrá el error tal cual.
  - Si el error es de la spec, corregí la spec y volvé al ensayo.
  - Si es de una config que ya existía, el arreglo es del usuario: decile qué falta.
- **`no se tocó` en una línea de git** (hooks propios, un worktree enlazado, un `core.hooksPath` con otro valor): explicá en una línea qué significa. No lo cambies por tu cuenta.
- **`al commitear, marcalo ejecutable: git add --chmod=+x …`**, **`falta en .gitignore: …`** y **`no se pudo borrar …`:** pasáselas al usuario. La última va antes de su primer commit.
- **`no se creó … ya existía, así que lo deriva de ahí el doctor`** (o `no se crearía …` en el ensayo): el TOML de Codex de un agente que ya tenía su `.md`. No es un error: lo genera el doctor del paso 5, desde ese `.md`, con su arreglo.

## 5. El doctor

Al final, corré el doctor y presentalo como dice `/odd-ws:doctor`, con los arreglos de a uno y solo con un sí:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
```

## Reglas

- No edites a mano lo que generó el script ni un archivo que ya existía. Si algo no te cierra, decíselo al usuario.
- El primer commit es del usuario: no hagas `git add` ni `git commit`.
- `git init` y `core.hooksPath` los decide el script. No los corras por tu cuenta.
