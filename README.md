# odd-workspace-template

Marketplace personal de Claude Code con el plugin `odd-ws`: el motor de una metodología de trabajo con agentes donde lo aprendido se vuelve mecanismo verificable (*Mecanismo > Memoria*).

**Estado:** motor extraído (T7 cerrada; las bibliotecas C# y Java, el fixture ciego de `eval-reviewers` y el juicio SQL quedan en espera de un consumidor real). T8 cerrada: `/odd-ws:bootstrap` genera una instancia desde cero, o completa una existente sin pisar nada. Siguen las skills de ciclo de vida (T9). Hay esqueleto, barrido de confidencialidad y `/odd-ws:doctor` (la máquina y, en una instancia, sus writers y sus agentes); del motor ya están el recibo atado al diff, el validador de la matriz de reglas, el dispatcher de capas (chequeos en cada `Edit` y `Write`), la biblioteca T-SQL, las corridas sueltas de los módulos de capa (`reglas.py`), el guard de los writers (`writer_guard.py`: sin git de escritura ni escritura por shell sobre los repos y el taller) y su compuerta de cierre (`writer_stop.py`: líneas reales contra la foto del primer toque, chequeos de capa y el bloque `## Resultado`), la plantilla de los writers, el triaje (`triaje.py`: las señales de riesgo sobre el diff antes de elegir la revisión, con el conteo de consumidores y su control positivo) y la Capa 1 del guard de comandos (`guard_comandos.py`: force push, `reset --hard`, `clean -f` y borrados recursivos fuera del scratch). También está la medición de revisores (`/odd-ws:eval-reviewers`): rescatar los reportes, auditar qué leyeron y puntuarlos, con ratificación a ciegas. Y el doctor de conocimiento (`/odd-ws:conocimiento`): links, anclas, índice, frescura y cifras que se contradicen entre los docs de la instancia, más afirmaciones verificables contra el código de sus repos.

## Estructura

| Ruta | Qué es |
|---|---|
| `.claude-plugin/marketplace.json` | El catálogo: un solo plugin, `odd-ws` |
| `plugin/` | El plugin: `plugin.json`, `scripts/` (`config_loader.py`, `doctor.py`, `recibo.py`, `matriz.py`, `verificar_capa.py`, `reglas.py`, `normalizar_sql.py`, `writer_guard.py`, `writer_stop.py`, `plantilla_writer.py`, `triaje.py`, `guard_comandos.py`, `rescatar.py`, `auditar_lecturas.py`, `puntuar.py`, `conocimiento.py`, `bootstrap.py` con sus generadores (`bootstrap_agentes.py`, `bootstrap_reglas.py`, `bootstrap_textos.py` y `bootstrap_instalacion.py`) y el paquete `odd_ws`, la biblioteca que importan los hooks y la instancia), `hooks/hooks.json`, `skills/doctor`, `skills/eval-reviewers`, `skills/conocimiento`, `skills/bootstrap`, `skills/revisar` y `plantillas/` (`pre-commit`, el pre-commit de una instancia, y `writer.md`, la plantilla de los writers de la instancia) |
| `tools/barrido.py` | Barrido de confidencialidad |
| `.githooks/pre-commit` | Autoprueba del barrido, barrido de lo stageado y suites `*.tests.py` |
| `.githooks/commit-msg` | Barrido del mensaje del commit |
| `.githooks/pre-push` | Barrido de todo lo que se empuja: contenido, rutas y mensajes. Cubre los commits que saltan el pre-commit (`rebase --continue`, `git am`) |

## Puesta en marcha en una máquina

1. Desde el clon: `python plugin/scripts/doctor.py`. Muestra qué falta, con el arreglo de cada ítem.
2. `python plugin/scripts/doctor.py --arreglar repo-hooks` (o `git config core.hooksPath .githooks`). **Obligatorio:** git no instala hooks solo, y un clon sin este paso no corre ningún barrido.
3. Crear la lista negra en `~/.odd-ws/denylist.txt` (o apuntar `ODD_WS_DENYLIST` a otra ruta). Va **fuera** del repo. Sin ella, el barrido bloquea todos los commits: falla cerrado.
4. Volver a correr el doctor hasta que no quede ninguna FALTA. Con el plugin instalado, lo mismo se pide con `/odd-ws:doctor`.

## Instalar el plugin

```text
/plugin marketplace add sebasgc0399/odd-workspace-template
/plugin install odd-ws@odd-workspace-template
```
