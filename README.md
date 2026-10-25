# odd-workspace-template

Marketplace personal de Claude Code con el plugin `odd-ws`: el motor de una metodología de trabajo con agentes donde lo aprendido se vuelve mecanismo verificable (*Mecanismo > Memoria*).

**Estado:** fundación. Hay esqueleto y barrido de confidencialidad; el motor todavía no está extraído.

## Estructura

| Ruta | Qué es |
|---|---|
| `.claude-plugin/marketplace.json` | El catálogo: un solo plugin, `odd-ws` |
| `plugin/` | El plugin (`plugin.json`; después `hooks/`, `scripts/`, `skills/`) |
| `tools/barrido.py` | Barrido de confidencialidad que corre en cada commit |
| `.githooks/pre-commit` | Autoprueba del barrido, barrido de lo stageado y suites `*.tests.py` |

## Puesta en marcha en una máquina

1. `git config core.hooksPath .githooks`
2. Crear la lista negra en `~/.odd-ws/denylist.txt` (o apuntar `ODD_WS_DENYLIST` a otra ruta). Va **fuera** del repo. Sin ella, el barrido bloquea todos los commits: falla cerrado.
3. `python tools/barrido.tests.py`

## Instalar el plugin

```text
/plugin marketplace add sebasgc0399/odd-workspace-template
/plugin install odd-ws@odd-workspace-template
```
