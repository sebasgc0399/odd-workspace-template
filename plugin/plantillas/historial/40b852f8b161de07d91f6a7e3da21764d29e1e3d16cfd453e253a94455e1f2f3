# {{nombre}} — guía de trabajo

<!-- odd-ws:perfil controles -->

Raíz de la instancia de **{{nombre}}**, con el perfil `controles` de `odd-ws` (`"profile": "controles"` en
`workspace.config.json`). El plugin pone los controles: los guards, las reglas de cada capa y el doctor. El
método, la delegación y la revisión son los de tu herramienta (por ejemplo, gentle-ai): odd-ws no los
reemplaza ni trae los suyos.

## Qué controla esta instancia

- **Los comandos peligrosos** (`guard_comandos`): bloquea un force push, un `reset --hard`, un `clean -f` y
  los borrados recursivos fuera del scratch. En un repo con `"agent_readonly": true`, pregunta antes de
  cualquier git que no sea de lectura.
- **Las ediciones en una capa** (`verificar_capa`): si los no-negociables de la skill `capa-<capa>` no se
  cargaron, la primera edición se bloquea y los recibe; después de cada edición corren las reglas de la capa
  (`.claude/reglas/verificar_<capa>.py`).
- **El fin del turno** (`revisar_turno`): las reglas corren sobre los archivos de capa que cambiaron en el
  turno, aunque se hayan escrito por la terminal o con un script.
- **El commit de la instancia** (`.githooks/pre-commit`): corre las pruebas de las reglas de cada capa.
- **La instalación** (`/odd-ws:doctor`): los hooks, la config, los CLI declarados y las extensiones de tus
  repos que ninguna capa cubre.

Un hook se apaga por instancia con `"disabled_hooks"` en `workspace.config.json`, y el doctor lo avisa.

## Cómo nacen las reglas

Una regla de capa se gana con origen y evidencia: entra como fila a `.claude/reglas/matriz.csv`, con su
evidencia en `.claude/reglas/evidencia.md`, y se cumple en su chequeo (`verificar_<capa>.py`) o en los
no-negociables de `capa-<capa>`. Aquí no hay tickets que cerrar, así que nacen por dos caminos:

- **`/odd-ws:cerrar memorias`** lee las memorias del proyecto (las de la instancia y las de cada repo) y
  propone cuáles graduar a la matriz.
- **`/odd-ws:paquetes`** trae las reglas de una capa desde otro repo git, fijadas a una etiqueta.

## Lo que no aplica

`/odd-ws:abrir`, `/odd-ws:cerrar` en su modo normal, `/odd-ws:revisar` y `/odd-ws:eval-reviewers` no aplican
en este perfil: son de los tickets, los writers, los revisores y los recibos del perfil `completo`, que esta
instancia no tiene. Si se invocan, lo dicen y no corren. **La revisión es la de tu herramienta**, por ejemplo
el RDD de gentle-ai: `/odd-ws:doctor` avisa si está apagado, porque la instancia quedaría sin revisión.

## Pasar a completo

Quita `"profile": "controles"` de `workspace.config.json` y corre `/odd-ws:bootstrap`, que completa lo que
falta sin pisar nada. Antes, borra este archivo si no lo editaste: el bootstrap no lo reemplaza, y el doctor
avisa mientras siga aquí con el perfil `completo`.
