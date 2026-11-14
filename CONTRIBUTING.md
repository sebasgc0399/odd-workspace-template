# Contribuir a la plantilla

Esta guía es para quien modifica la plantilla misma. Si quieres usar el plugin en tu proyecto, empieza por el [README](README.md).

## Puesta en marcha del clon

1. Clona el repo (si no eres colaborador, trabaja en un fork y propón el cambio con un pull request) y, desde el clon, corre `python3 plugin/scripts/doctor.py`. Muestra qué falta, con el arreglo de cada ítem.
2. `python3 plugin/scripts/doctor.py --arreglar repo-hooks` (o `git config core.hooksPath .githooks`). **Obligatorio:** git no instala hooks solo, y un clon sin este paso no corre ningún barrido.
3. Crea la lista negra en `~/.odd-ws/denylist.txt` (o apunta `ODD_WS_DENYLIST` a otra ruta). Va **fuera** del repo y no viaja con él. Sin ella, el barrido bloquea todos los commits: falla cerrado.
4. Vuelve a correr el doctor hasta que no quede ninguna FALTA.

## Los hooks del repo

| Hook | Qué corre |
|---|---|
| `.githooks/pre-commit` | La autoprueba del barrido, el barrido de lo stageado y todas las suites `*.tests.py` (unos 4 minutos) |
| `.githooks/commit-msg` | El barrido del mensaje del commit |
| `.githooks/pre-push` | El barrido de todo lo que se empuja (contenido, rutas y mensajes) y después el chequeo de la entrega (`tools/entrega.py`): la etiqueta de la versión y sus notas en `CHANGELOG.md` |

Los tres corren Python con el primero que arranca de `python3`, `python` y `py` (`.githooks/python.sh`); si no arranca ninguno, frenan con el motivo.

## Las pruebas

No hay pytest: cada `*.tests.py` es un script que se corre solo. `.github/workflows/pruebas.yml` corre todas las suites en Ubuntu, Windows y macOS con Python 3.12, porque los tests piden 3.12 (`shutil.rmtree(onexc=)` y `os.path.isjunction`).

```text
python3 plugin/scripts/<script>.tests.py
for suite in $(git ls-files -- '*.tests.py'); do python3 "$suite"; done
```

## Una entrega

1. Sube `version` en `plugin/.claude-plugin/plugin.json`, en `plugin/.codex-plugin/plugin.json` y en el `package.json` de la raíz (las tres tienen que coincidir: lo exige un test), escribe sus notas en una sección `## <versión>` de `CHANGELOG.md` y commitea las dos cosas juntas.
2. Etiqueta con `claude plugin tag ./plugin --dry-run` y después sin `--dry-run`. Crea `odd-ws--v<versión>` y exige el árbol limpio.
3. Empuja `main` y la etiqueta juntas:

   ```text
   git push origin <sha>:refs/heads/main refs/tags/odd-ws--v<versión>
   ```

   El pre-push frena un push a `main` que cambie `plugin/` si el commit no lleva la etiqueta de la versión de su `plugin.json`. También frena cualquier etiqueta `odd-ws--v*` empujada cuyo commit no tenga sus notas en `CHANGELOG.md`.
4. **El release se publica solo.** Al llegar la etiqueta, `.github/workflows/release.yml` comprueba que coincida con `plugin.json` y publica el release en GitHub con la sección del CHANGELOG como cuerpo. Si el release ya existe, no lo toca.

### Cómo se escriben las notas

La sección `## <versión>` es lo que lee la comunidad en el release, así que va en dos partes:

- **Arriba, `### Lo que cambia para ti`:** qué nota distinto quien usa el plugin, en qué CLI o sistema, y si tiene que hacer algo en su instancia. Sin nombres de scripts internos ni detalles de implementación.
- **Abajo, `### Detalle técnico`:** los scripts, las causas y los casos borde, para quien mantiene el plugin.
- **Dentro de la sección, solo encabezados `###`.** `tools/notas.py` toma todo lo que hay hasta el siguiente `## `, así que un `##` la cortaría. Pruébalo antes de etiquetar: `python3 tools/notas.py <versión>` imprime el cuerpo que va a publicar el release.

## Dónde está el porqué

| Doc | Qué tiene |
|---|---|
| [`Doc/diseno.md`](Doc/diseno.md) | Todas las decisiones de diseño y la especificación de cada script |
| `odd/tasks/<feature>.md` | La bitácora de cada feature: los requisitos, las tareas con su commit y el log de decisiones |

## Estructura del repo

| Ruta | Qué es |
|---|---|
| `.claude-plugin/marketplace.json` | El catálogo: un solo plugin, `odd-ws` |
| `plugin/.claude-plugin/plugin.json` | El nombre y la versión del plugin |
| `plugin/skills/` | Las 7 skills |
| `plugin/hooks/hooks.json` | Los hooks del plugin |
| `plugin/scripts/` | Los scripts de las skills y los hooks, cada uno con su `*.tests.py`. `odd_ws/` es la biblioteca que importan los hooks y las reglas de la instancia |
| `plugin/plantillas/` | Lo que el bootstrap copia a la instancia: `CLAUDE.md`, `ticket.md`, `capa.md`, `criterios.md`, `revisor.md`, `revisor-diseno.md`, `writer.md`, `reglas/`, `pre-commit` y `bootstrap.ejemplo.json` |
| `tools/` | `barrido.py` (el barrido de confidencialidad), `entrega.py` (el chequeo de la entrega) y `notas.py` (saca del CHANGELOG las notas de una versión). Son del repo, no viajan con el plugin |
| `.githooks/` | Los hooks de git del repo |
| `.github/workflows/release.yml` | Publica el release de cada etiqueta `odd-ws--v*` |
| `CHANGELOG.md` | Las notas de cada versión, una sección `## <versión>` por entrega |
| `README.md` y `Doc/` | La portada y la referencia de uso: `uso.md`, `hooks.md`, `capas-y-reglas.md` y `actualizar.md`. `diseno.md` guarda el porqué |
