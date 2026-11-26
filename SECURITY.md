# Seguridad

odd-ws corre en tu máquina: hooks que leen lo que el agente va a hacer, scripts que corres tú y skills que guían al agente. Acá está cómo reportar una falla de seguridad, qué protege odd-ws y qué no, y todo lo que puede salir de tu máquina.

## Reportar una vulnerabilidad

No abras un issue público ni un pull request con el detalle. Repórtala en privado con la función de GitHub: en la pestaña **Security** del repo, **Report a vulnerability** ([el formulario](https://github.com/sebasgc0399/odd-workspace-template/security/advisories/new)). Solo la ven los mantenedores, y la conversación y el arreglo siguen ahí hasta que se publican.

Incluye:

- la versión de odd-ws (la de `plugin/.claude-plugin/plugin.json`) y el CLI donde corre (Claude Code, Codex o Pi), con su versión;
- el sistema operativo;
- los pasos para reproducirla y qué esperabas que pasara.

No pegues secretos reales, rutas con tu usuario ni código de tu empresa: un ejemplo mínimo alcanza. Si el formulario no aparece, abre un issue que diga solo que tienes un reporte de seguridad, sin detalles, y el mantenedor te abre un canal privado.

Los arreglos salen en la versión siguiente: actualiza a la última etiqueta `odd-ws--v*`.

## El modelo de amenaza

La fuente es [`Doc/diseno.md`](Doc/diseno.md#guard-de-comandos-guard_comandospy-l48-l49-l52-l53). En resumen:

- **Los guards frenan los errores y los atajos del agente, no a un agente que los esquiva a propósito.** Bloquean un push forzado, un `reset --hard`, un `clean -f`, un borrado recursivo fuera del scratch y la escritura por shell en un archivo de capa, y preguntan antes de un git de escritura en un repo de solo lectura, también dentro de un `bash -c` o con la ruta completa de git. Pero leen texto, y el shell es un lenguaje completo: una palabra partida con comillas (`gi''t`) pasa. Contra eso protege el sandbox de tu CLI, no un hook.
- **Un hook que falla por dentro deja pasar,** y la falla queda anotada (ver [Si un hook falla](Doc/hooks.md#si-un-hook-falla)). Si Python no arranca, depende del CLI (ver [Si Python no arranca](Doc/hooks.md#si-python-no-arranca)).
- **Un paquete de reglas es código que corre en tus hooks, con tus permisos.** No hay contenedor: el lock fija el commit, la huella detecta una edición local y el código se lee en el diff antes del commit (ver [El modelo de seguridad](Doc/capas-y-reglas.md#el-modelo-de-seguridad)).
- **Los secretos.** odd-ws tapa las claves conocidas en el texto que guarda en la instancia. El pre-commit de la instancia frena un archivo de secretos (`.env`, una clave, un `credentials*.json`) y una clave privada pegada. `paquetes.py revisar` busca rutas personales, claves privadas y fuentes locales antes de que publiques un paquete.
- **El texto que llega al agente es un dato, no una orden.** El porqué que sale de `git blame` y el `no-negociables.md` de un paquete entran al contexto del agente: en un repo o un paquete que no es de confianza, léelos como pistas.
- **odd-ws no tiene telemetría.**

## Lo que sale de tu máquina

odd-ws no importa módulos de red de Python (`socket`, `http`, `requests`, `urllib.request`). Lo único que puede salir a la red son los programas que lanza, y a cada uno lo lanza un comando que corres tú. Los hooks no salen a la red: el aviso de lo que quedó sin subir mira las refs locales, sin `fetch`.

| Qué corre | Cuándo | Adónde va | Dónde está |
|---|---|---|---|
| `git ls-remote --tags` | `paquetes.py importar` y `actualizar` (`/odd-ws:paquetes`) | La fuente del paquete que le das: https, ssh, `git://` o una ruta local | `plugin/scripts/paquetes.py`, en `resolver_etiqueta` |
| `git clone --depth 1` de esa etiqueta | Lo mismo, después del `ls-remote` | La misma fuente | `plugin/scripts/paquetes.py`, en `clon` |
| `git fetch origin` de las ramas, sin etiquetas | `auditar_ramas.py`, antes de publicar (la entrega de `/odd-ws:cerrar`) | El `origin` de cada repo de tu config | `plugin/scripts/odd_ws/auditoria_de_ramas.py`, en `_fetch` |
| `claude plugin marketplace add` | `/odd-ws:doctor --arreglar marketplace`, solo si lo pides | GitHub, al repo de odd-ws | `plugin/scripts/odd_ws/hosts/claude_code.py` lo arma y `plugin/scripts/doctor.py` lo corre |
| `gentle-ai review mode disable --scope clone` | `/odd-ws:doctor --arreglar rdd`, solo si lo pides | Lo que haga gentle-ai | `plugin/scripts/doctor.py` |
| Consultas a otros CLI: `gentle-ai review mode status`, `gentle-ai telemetry status`, `gentle-ai version`, `engram version`, `jq --version`, `claude --version`, `codex --version`, `pi --version` y `gentle-shell --version` | Cada `/odd-ws:doctor` | odd-ws no les pide red; si un CLI sale a la red por su cuenta, eso es de ese CLI | `plugin/scripts/doctor.py`, `plugin/scripts/odd_ws/hosts/claude_code.py`, `plugin/scripts/odd_ws/hosts/codex.py` y `plugin/scripts/odd_ws/hosts/pi.py` |
| `gh release create` | Solo en el CI de este repo, al empujar una etiqueta `odd-ws--v*` | GitHub | `.github/workflows/release.yml`, nunca en tu máquina |

- **Lo que corre el agente no es de esta lista.** Un `git push` que le pides, o un `git fetch` que sugiere una skill, lo corre el agente con la herramienta de shell de tu CLI: pasa por sus permisos y por los guards, y ningún script de odd-ws lo lanza por su cuenta.
- **Cómo se mantiene al día.** `tools/inventario_de_red.tests.py`, que corre en el pre-commit de este repo, lee con el AST de Python el código de `plugin/` y de `tools/` (sin las pruebas). Junta los textos que son un verbo de red (`fetch`, `push`, `pull`, `ls-remote`, `clone`, `marketplace`, `curl`, `wget`, `gh`), los que traen `http://` o `https://` y los imports de red. Cada archivo con uno tiene que estar en esta tabla, o en las excepciones de la prueba con su porqué: los guards, que leen esos verbos para frenarlos y no los corren. Un archivo nuevo que sale a la red sin entrar acá la pone en rojo.
- **Lo que la prueba no ve:** un verbo dentro de un texto más largo, como `"git fetch origin"` en un solo string, y un módulo que se importa por su nombre en un texto (`importlib.import_module("socket")`). odd-ws lanza sus programas con la lista de argumentos, sin `shell=True`.
