# odd-workspace-template

Marketplace personal de Claude Code con el plugin `odd-ws`: el motor de una metodología de trabajo con agentes donde lo aprendido se vuelve mecanismo verificable (*Mecanismo > Memoria*).

**Estado:** extrayendo el motor (T7). Hay esqueleto, barrido de confidencialidad y `/odd-ws:doctor`; del motor ya están el recibo atado al diff, el validador de la matriz de reglas, el dispatcher de capas (chequeos en cada `Edit` y `Write`), la biblioteca T-SQL y las corridas sueltas de los módulos de capa (`reglas.py`).

## Estructura

| Ruta | Qué es |
|---|---|
| `.claude-plugin/marketplace.json` | El catálogo: un solo plugin, `odd-ws` |
| `plugin/` | El plugin: `plugin.json`, `scripts/` (`config_loader.py`, `doctor.py`, `recibo.py`, `matriz.py`, `verificar_capa.py`, `reglas.py`, `normalizar_sql.py` y el paquete `odd_ws`, la biblioteca que importan los hooks y la instancia), `hooks/hooks.json`, `skills/doctor` y `plantillas/pre-commit` (el pre-commit de una instancia) |
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
