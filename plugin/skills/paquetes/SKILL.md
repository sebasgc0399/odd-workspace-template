---
name: paquetes
description: Importa, actualiza, quita o lista paquetes de reglas de una capa traídos de un repo git por etiqueta. Solo lo invoca el usuario.
disable-model-invocation: true
---

# /odd-ws:paquetes

Un paquete trae las reglas de una capa desde otro repo git: su `verificar.py`, su suite, su matriz, sus no-negociables y su evidencia. `paquetes.py` lo fija a una etiqueta, lo copia a la instancia y escribe el lock; tú corres el script, muestras lo que dice y esperas el sí. Cómo se escribe un paquete y qué revisa el doctor está en la sección «Paquetes de reglas» de `Doc/capas-y-reglas.md`, en el repo del plugin.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/paquetes.py" <comando> ...
```

En Windows con Codex, los comandos van con `python` en lugar de `python3`. En Codex la skill es `$paquetes`, y en Pi, `/skill:paquetes`. Todo pasa en la raíz de la instancia: los repos del equipo no se tocan.

## Reglas

- **Nunca ejecutes código del paquete:** ni lo importes ni corras su `verificar.py` o su suite por tu cuenta. Su suite corre solo en el pre-commit de la instancia o en `reglas.py --test`, cuando el usuario lo aprueba. Calibrarlo (`reglas.py --calibrar … --guardar`) también corre su código: solo después de que el usuario leyó lo copiado y con su sí.
- **Un bloqueo del paquete empieza avisando.** Una regla del paquete bloquea solo si declara su `sembrado` en `REGLAS` y la instancia la calibró con la huella actual del lock. Importar o actualizar no la calibra: `actualizar` deja vieja la calibración que había. Si el usuario es el autor del paquete, recuérdale que cada regla que tiene que bloquear declara su `sembrado` (sección «Paquetes de reglas» de `Doc/capas-y-reglas.md`).
- **No edites lo copiado.** Ni `.claude/reglas/paquetes/<nombre>/` ni `.claude/reglas/paquetes.json` se tocan a mano: el doctor lo marca por la huella. Un arreglo va al repo del paquete, con una etiqueta nueva, y se trae con `actualizar`.
- **Cada escritura, con su sí:** `importar`, `actualizar` y `quitar`. El commit, con un segundo sí aparte.
- **La fuente.** Prefiere una URL https o ssh (también la forma `git@host:repo`). Una ruta local se guarda absoluta y solo sirve en esta máquina: el script lo avisa, y tú se lo repites. Una URL con usuario o contraseña se rechaza, porque iría al lock que se commitea: las credenciales van en git. `http://` sin TLS tampoco vale.
- **Un repo privado:** el usuario se autentica antes con git (un credential helper o ssh). El script nunca pide credenciales ni abre una ventana para hacerlo.

## Importar

1. Pregunta de a uno, cada uno con tu propuesta:
   - la **fuente**, la URL del repo del paquete;
   - la **etiqueta**, un tag del repo. Una rama o un hash no valen;
   - la **capa**, declarada en `workspace.config.json` y con `rule_prefix`. Si no sabes cuáles hay, lee `workspace.config.json`.
2. Corre el ensayo, que no escribe nada:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/paquetes.py" importar "<fuente>" --etiqueta <etiqueta> --capa <capa> --ensayo
   ```

3. Muestra el plan tal cual sale: el paquete con su prefijo y su capa, la fuente, la etiqueta con su commit, los archivos con su tamaño y la entrada del lock.
4. Pide un sí explícito. Con el sí, corre lo mismo sin `--ensayo`.
5. Sigue con «Después de importar o actualizar».

## Actualizar

1. Pregunta el paquete (si no lo sabes, corre `listar`) y la etiqueta nueva.
2. Corre el ensayo y muestra la salida tal cual: la etiqueta y el commit de antes y de después, y por archivo `nuevo`, `cambia` o `sale`.

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/paquetes.py" actualizar <nombre> --etiqueta <etiqueta> --ensayo
   ```

3. Con un sí explícito, corre lo mismo sin `--ensayo` y sigue con «Después de importar o actualizar».

`actualizar` a la misma etiqueta es el arreglo cuando el doctor dice que la huella no coincide: vuelve a copiar lo de esa etiqueta.

## Después de importar o actualizar

1. **Pídele que lea el código copiado antes del commit,** sobre todo `verificar.py` y `verificar.tests.py`: corren en los hooks de esta instancia en cada edición de la capa, y en el pre-commit. El lock fija el commit, pero lo que corre lo revisa él.
2. **Ofrece calibrar la capa,** después de que lo leyó y solo con su sí, con una carpeta de código real de la capa (o una vacía, si todavía no hay código):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reglas.py" --calibrar <capa> <carpeta> --guardar
   ```

   Muestra la línea de cada regla del paquete: `puede bloquear`, o `solo avisa:` con el porqué. Calibra también el módulo de la capa y sus otros paquetes, porque reemplaza la calibración de la capa entera. Sin calibrar, los bloqueos del paquete llegan como aviso. Si sale con 1 porque la carpeta del paquete no coincide con su lock, el arreglo es `actualizar` a la misma etiqueta.
3. Muestra:

   ```bash
   git status --short
   git diff --stat
   ```

   Los archivos de un paquete recién importado son nuevos: salen en `git status` y no en `git diff --stat`, que solo muestra lo que ya estaba commiteado (el lock, si había otro paquete).
4. Ofrece el commit con las rutas exactas y un mensaje convencional, y córrelo **solo con un segundo sí:**

   ```bash
   git add -- ':/.claude/reglas/paquetes/<nombre>' ':/.claude/reglas/paquetes.json'
   git commit -m "chore(reglas): importa el paquete <nombre> en <etiqueta>"
   ```

   Si calibraste en el paso 2, suma `':/.claude/registro/calibracion.json'` al `git add`.

   Para `actualizar`, el mensaje es `chore(reglas): lleva el paquete <nombre> a <etiqueta>`. El pre-commit corre `reglas.py --test`, que también corre la suite del paquete, en su propio proceso. Si queda en rojo, el commit no pasa: muestra la salida y no lo saltees con `--no-verify`.

## Quitar

1. Confirma el nombre con `listar`.
2. Di qué va a borrar: `.claude/reglas/paquetes/<nombre>` y su entrada del lock, o el lock entero si era el último paquete. Pide un sí explícito.
3. Corre `quitar <nombre>` y muestra `git status --short`. Ofrece el commit con las mismas rutas del paso de arriba y `chore(reglas): quita el paquete <nombre>`, también con un segundo sí.

## Listar

`listar` muestra cada paquete con su capa, su prefijo, su etiqueta, los primeros 12 caracteres del commit y si su huella está al día, no coincide o le falta la carpeta. No escribe nada, así que córrelo sin preguntar. Si una huella no coincide, alguien editó lo copiado: propón `actualizar` a la misma etiqueta, con su ensayo y su sí.

## Cómo leer la salida

- **Sale con 0:** anduvo. Muestra la salida tal cual. `paquetes: aviso: la fuente es una ruta local…` no es un error: repíteselo al usuario.
- **Sale con 1:** el script rechazó el pedido y no escribió nada. Puede ser una etiqueta que no existe, un paquete inválido (el manifiesto, un archivo que falta, un enlace o un `odd_ws_api` mayor que el del plugin), un nombre que ya está en el lock, un prefijo que choca con una capa o con otro paquete, una capa sin `rule_prefix`, una URL con credenciales o una carpeta de destino enlazada. Muestra el mensaje tal cual y di qué decisión le toca al usuario: otra etiqueta, actualizar el plugin, otra capa o corregir el paquete en su repo. No lo resuelvas editando archivos.
- **Sale con 2:** el entorno. Puede ser que no haya git, que falte red o acceso al repo, un protocolo que no vale (`http://`, `ext::`), o un lock o una config rota. Muestra el mensaje. Para un repo privado, recuérdale autenticarse con git; para un lock roto, `/odd-ws:doctor` dice qué tiene.
- Después de importar, actualizar o quitar, el ítem `paquetes` de `/odd-ws:doctor` confirma que el lock y las carpetas están en orden.
