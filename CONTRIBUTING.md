# Contribuir a la plantilla

Esta guía es para quien modifica la plantilla misma. Si quieres usar el plugin en tu proyecto, empieza por el [README](README.md).

## Puesta en marcha del clon

Necesitas Python 3.12 o más, porque las suites lo piden, y Node 22.18 o más (el CI usa 24) para las suites del shim de Pi, que el pre-commit también corre.

1. Clona el repo (si no eres colaborador, trabaja en un fork y propón el cambio con un pull request) y, desde el clon, corre `python3 plugin/scripts/doctor.py`. Muestra qué falta, con el arreglo de cada ítem.
2. `python3 plugin/scripts/doctor.py --arreglar repo-hooks` (o `git config core.hooksPath .githooks`). **Obligatorio:** git no instala hooks solo, y un clon sin este paso no corre ningún barrido.
3. Crea la lista negra en `~/.odd-ws/denylist.txt` (o apunta `ODD_WS_DENYLIST` a otra ruta). Va **fuera** del repo y no viaja con él. Sin ella, el barrido bloquea todos los commits: falla cerrado.
4. Vuelve a correr el doctor hasta que no quede ninguna FALTA.

## Los hooks del repo

| Hook | Qué corre |
|---|---|
| `.githooks/pre-commit` | La autoprueba del barrido, el barrido de lo stageado, el chequeo de marcadores de conflicto, todas las suites `*.tests.py` y las `*.test.ts` del shim de Pi. En Windows tarda unos 20 minutos, y un pre-commit corriendo a la vez que otro puede hacer fallar las pruebas de latencia |
| `.githooks/commit-msg` | El barrido del mensaje del commit |
| `.githooks/pre-push` | El barrido de todo lo que se empuja (contenido, rutas y mensajes) y después el chequeo de la entrega (`tools/entrega.py`): la etiqueta de la versión, sus notas en `CHANGELOG.md`, que el README y la página digan esa versión y los mismos requisitos, y que la tabla de huellas de las plantillas esté al día |

Los tres corren Python con el primero que arranca de `python3`, `python` y `py` (`.githooks/python.sh`); si no arranca ninguno, frenan con el motivo.

El chequeo de marcadores (`plugin/scripts/odd_ws/marcadores.py`) frena el commit si un mismo archivo agrega una línea de apertura (`<<<<<<<`) y una de cierre (`>>>>>>>`) de un conflicto, y nombra cada archivo y línea. Un `=======` suelto pasa, porque es un subrayado de Markdown, y los errores de espacios nunca frenan. Si un archivo trae esas líneas a propósito, sácalo del chequeo en `.gitattributes` con un tamaño de marcador que no use (`<ruta> conflict-marker-size=32`). Si git falla, avisa y deja pasar el commit. `git rebase --continue` no corre el pre-commit, así que al resolver un conflicto en un rebase, corre `git commit` antes de seguir: así el chequeo pasa por lo que resolviste. El detalle, con el caso del merge, está en `Doc/diseno.md` (§8).

## Las pruebas

No hay pytest: cada `*.tests.py` es un script que se corre solo. Las suites del shim de Pi son `*.test.ts` y corren con `node --test`, sin flags. `.github/workflows/pruebas.yml` corre todas en Ubuntu, Windows y macOS, con Python 3.12 (los tests usan `shutil.rmtree(onexc=)` y `os.path.isjunction`) y Node 24.

```text
python3 plugin/scripts/<script>.tests.py
for suite in $(git ls-files -- '*.tests.py'); do python3 "$suite"; done
node --test plugin/shim/*.test.ts
```

## Una entrega

1. Sube `version` en `plugin/.claude-plugin/plugin.json`, en `plugin/.codex-plugin/plugin.json` y en el `package.json` de la raíz (las tres tienen que coincidir: lo exige un test), escribe sus notas en una sección `## <versión>` de `CHANGELOG.md` y commitea las dos cosas juntas.
   - En el mismo commit, después de subir la versión, corre `python3 tools/huellas.py`: reescribe `plugin/plantillas/huellas.json` con la huella de cada plantilla que el bootstrap copia a la instancia, en cada etiqueta publicada y en la versión nueva. El doctor de una instancia la usa para saber qué copias quedaron viejas.
2. En el mismo commit, sube la «Versión actual» del README y la versión de los comandos de instalación: cada `odd-ws--v` del README, de `Doc/uso.md` y de `Doc/actualizar.md` lleva el número de la versión nueva.
3. Commitea la página de la versión en la rama `gh-pages` **antes de empujar `main`**: su «Versión actual», el pie, el comando de instalación y la tabla de requisitos, que tiene que ser igual a la de «Instalación» en el README.
4. Etiqueta con `claude plugin tag ./plugin --dry-run` y después sin `--dry-run`. Crea `odd-ws--v<versión>` y exige el árbol limpio.
5. Empuja `main` y la etiqueta juntas:

   ```text
   git push origin <sha>:refs/heads/main refs/tags/odd-ws--v<versión>
   ```

   El pre-push frena un push a `main` que cambie `plugin/` si el commit no lleva la etiqueta de la versión de su `plugin.json`. También frena cualquier etiqueta `odd-ws--v*` empujada cuyo commit no tenga sus notas en `CHANGELOG.md`, cualquier push a `main` o a una etiqueta cuyo README o página no cumplan los pasos 2 y 3 con la versión de su `plugin.json`, y uno cuya tabla de huellas no sea la que sale de `tools/huellas.py` (el paso 1). La página la lee de tu rama local `gh-pages` o, si no la tienes, de `origin/gh-pages`; sin ninguna de las dos, avisa y deja pasar.
6. Empuja la página después:

   ```text
   git push origin gh-pages
   ```

   El chequeo de la entrega no revisa el push de `gh-pages`: por eso la página se revisa en el push de `main`, antes de que salga.
7. **El release se publica solo.** Al llegar la etiqueta, `.github/workflows/release.yml` comprueba que coincida con `plugin.json` y publica el release en GitHub con la sección del CHANGELOG como cuerpo. Si el release ya existe, no lo toca.

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
| `odd/roadmap.md` | Lo que viene: la cola, lo que espera, las ideas con su fuente y lo hecho por versión |

## Estructura del repo

| Ruta | Qué es |
|---|---|
| `.claude-plugin/marketplace.json` | El catálogo: un solo plugin, `odd-ws` |
| `plugin/.claude-plugin/plugin.json` | El nombre y la versión del plugin. `plugin/.codex-plugin/plugin.json` es el de Codex, con la misma versión |
| `package.json` | El paquete de Pi, que gentle-shell instala desde git: apunta al shim y a las skills, y lleva la misma versión |
| `plugin/skills/` | Las 9 skills |
| `plugin/hooks/` | Los hooks del plugin en cada CLI: `hooks.json` (Claude Code), `hooks.codex.json` y `hooks.pi.json` |
| `plugin/shim/` | El shim de Pi en TypeScript (`pi.ts` y `nucleo.ts`), que lleva los eventos de Pi a los hooks de Python, con sus `*.test.ts` |
| `plugin/scripts/` | Los scripts de las skills y los hooks, cada uno con su `*.tests.py`. `odd_ws/` es la biblioteca que importan los hooks y las reglas de la instancia |
| `plugin/plantillas/` | Lo que el bootstrap copia a la instancia: `CLAUDE.md` (o `CLAUDE.controles.md` con el perfil `controles`), `ticket.md`, `capa.md`, `criterios.md`, `revisor.md`, `revisor-diseno.md`, `writer.md`, `reglas/`, `pre-commit` y `bootstrap.ejemplo.json`, más `huellas.json`, la tabla de huellas que genera `tools/huellas.py` |
| `tools/` | `barrido.py` (el barrido de confidencialidad), `entrega.py` (el chequeo de la entrega), `notas.py` (saca del CHANGELOG las notas de una versión) y `huellas.py` (escribe `plugin/plantillas/huellas.json`, la huella de cada plantilla copiada en cada versión). Son del repo, no viajan con el plugin |
| `.githooks/` | Los hooks de git del repo |
| `.github/workflows/release.yml` | Publica el release de cada etiqueta `odd-ws--v*` |
| `CHANGELOG.md` | Las notas de cada versión, una sección `## <versión>` por entrega |
| `README.md` y `Doc/` | La portada y la referencia de uso: `uso.md`, `equipo.md`, `hooks.md`, `capas-y-reglas.md` y `actualizar.md`. `diseno.md` guarda el porqué |
| `Doc/img/` | Las imágenes del README y de las redes: el banner (`odd-ws-banner.png`, con su fuente `banner.html` y el comando para renderizarlo), el GIF del ciclo y la tarjeta, que también es la imagen social del repo |
| `odd/` | La bitácora del proyecto: `roadmap.md`, `tasks/` (una por feature) y `estudios/` |
| La rama `gh-pages` | La página del proyecto: un `index.html` estático, con sus fuentes y su favicon en `assets/`. Se commitea antes de empujar `main` (ver «Una entrega») |
