# El modo memorias

Detalle de `/odd-ws:cerrar memorias`. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`, y los pasos 1 a 10 que se citan son los del `SKILL.md`. La fila de la matriz se arma como en el paso 5, con `references/matriz.md`.

## Modo memorias

`/odd-ws:cerrar memorias` gradúa a la matriz las reglas que ya están en las memorias del proyecto. Tiene dos fuentes: la memoria en archivos de Claude Code, que lee `memorias.py`, y engram, opcional, que consultas tú. Las dos se miran para la instancia y para cada repo de la config, porque lo que se guardó trabajando dentro de un repo vive en el proyecto de ese repo.

### Qué reusa del cierre y qué salta

| Del cierre de un ticket | En este modo |
|---|---|
| Reglas duras 1 a 3 | Rigen igual: nada se escribe antes del sí, solo se gradúa a lo que ya existe y los repos del equipo son de solo lectura. |
| 1. Leer el ticket | Se salta: no hay ticket. |
| 2. Triaje | Se reusa la clasificación de dominio o de motor. El destino es siempre una fila de la matriz: es el único lugar que guarda el origen `memoria:<slug>`, y `memorias.py` marca `graduada` solo a la memoria que una fila cita. Lo que es de dominio o de metodología no tiene fila: va con las «sin fila» de la propuesta. Lo de motor no tiene bitácora donde anotarse: va al resumen final. |
| 3. El modo sombra | Se salta: es de un ticket. |
| 4. La propuesta y el sí | Se reusa, con la forma de M3: sin relojes ni bitácora. |
| 5. Promover | Se reusa: la fila con el script, la regla en su destino, la evidencia y los dos chequeos de `matriz.py`. |
| 6 y 7. Los relojes y el worktree | Se saltan: no hay ticket. |
| 8. El conocimiento | Se salta: este modo no edita los docs de `knowledge.docs`. |
| 9. El commit | Se reusa, sin un segundo sí salvo con `"ask_before_commit": true`, y con el mensaje de M5. |
| 10. Las memorias sin triar | Se salta: es este modo. |

### Reglas duras del modo

1. **Las memorias `user` no entran.** El script ya las excluye, junto con las `reference`. No las pidas ni abras sus archivos: lee solo los que lista el JSON.
2. **La fila, el destino y la evidencia parafrasean la regla.** Nunca copian texto literal de la memoria ni nombres de personas. La `descripcion` del JSON también es texto de la memoria: sirve para juzgar, pero no se copia al `resumen`, al `motivo` ni a la evidencia.
3. **El slug viaja en el `origen`.** Si el nombre del archivo trae el nombre de una persona o algo que no debe salir de la máquina, no la gradúes. Dilo en la propuesta, con dos salidas: que el usuario renombre la memoria (el archivo está fuera de la instancia, así que lo renombra él, con su link en `MEMORY.md`) y vuelva a correr el modo, o que quede como `vista`. Nunca inventes otro slug para el `origen`. Lo mismo si el slug tiene algo que no sea letra, dígito, `_`, `.` o `-`, porque `matriz.py` no lo acepta.
4. **La propuesta muestra exactamente lo que va a quedar escrito:** la fila con todos sus campos, el texto de la regla en su destino y la entrada de `evidencia.md`.
5. **Esta revisión es la única barrera.** La matriz viaja en el repo de la instancia, y ahí no corre ningún barrido de confidencialidad.
6. **En una instancia con `"profile": "controles"` no hay revisores ni `criterios`:** el destino de una fila es `chequeo`, `pasiva`, `skill`, `evidencia` o `descarte`, nunca `reviewer-PR` ni `criterios`.

### M1. Correr `memorias.py`

```bash
python3 "<S>/memorias.py" --json --memorias "<dir>"
```

- **`--memorias`** lleva la ruta de la memoria persistente que la sesión ya conoce (Claude Code la anuncia en el system prompt). Si no la conoces, saca la opción y el script la deriva: `cobertura.origen` sale `derivada`.
- **En Codex,** `--host codex` en lugar de `--memorias`. Sale con 0 y `cobertura.estado` `no disponible`: dilo en una línea («memoria en archivos: no disponible en Codex») y sigue con engram (M2).
- **Si sale con 2,** muestra el motivo, que va por stderr, y frena el modo. Nunca digas «no hay memorias»: el script no pudo mirar.
- **Por defecto entran solo las `feedback`.** Las `project` se cuentan en `excluidas.project`, y entran solo si el usuario las pide, con `--con-project`.
- **Los repos de la config también tienen memorias.** Lo que se guardó trabajando dentro de un repo vive en el proyecto de ese repo, no en el de la instancia. Corre también, por cada repo de `workspace.config.json`:

  ```bash
  python3 "<S>/memorias.py" --json --repo <repo>
  ```

  Su cobertura dice de qué repo son. Lo que gradúes de ahí lleva el origen `memoria:<repo>.<slug>`, para no chocar con una memoria de la instancia del mismo nombre, y si registras una como vista o descartada, va con el mismo `--repo`.
- **Cada memoria del JSON** trae `slug`, `tipo`, `descripcion`, `estado` y `filas` (los IDs de la matriz que la citan). Los candidatos salen de las `nueva` y las `cambiada`. Las `graduada`, `vista` y `descartada` no se vuelven a proponer, y una `ilegible` se nombra con su `motivo`, sin proponerla. Los `avisos` (huérfanas, links rotos, filas de la matriz con errores) se muestran tal cual.

### M2. engram, opcional

Lo consultas tú, no el script.

- **Busca las herramientas antes de darlas por ausentes.** En Claude Code, las `mem_*` pueden llegar diferidas: búscalas con ToolSearch (por ejemplo, `mem_search`). Solo si después de buscarlas no aparecen: «engram: no disponible», y sigue.
- **Primero, `mem_current_project`,** con la raíz de la instancia como `cwd` (o `directory`) si su schema lo acepta. Si la `path` que devuelve no es la de la instancia, o el proyecto sale ambiguo (con `available_projects` o con la fuente `ambiguous`) o vacío, dilo y omite engram. No adivines el proyecto.
- **Los repos de la config tienen su propio proyecto en engram.** Repite `mem_current_project` con la ruta de cada repo como `cwd`, con la misma regla: si la `path` que devuelve no es la del repo, o sale ambiguo o vacío, omítelo. Lo que se gradúe de ahí sigue con el origen `memoria:engram-<sync_id>`, porque el `sync_id` ya es único.
- **Después, `mem_search`** con ese `project`, `scope: "project"` y `limit: 20`. Nunca `scope: "personal"` ni `all_projects`. Haz una consulta por capa de la instancia y por tema (una convención, un error que se repitió). Para leer una observación entera, `mem_get_observation`.
- **Una observación que describe a una persona** (su perfil, su rol, sus preferencias) cuenta como `user` y no entra.
- **La cobertura es parcial, y se declara así:** «engram: parcial; N consultas, K llegaron al tope 20/20, puede haber más». Nunca «no hay más»: `mem_search` no tiene cursor.
- **El origen** de lo que se gradúa desde engram es `memoria:engram-<sync_id>`, con el `sync_id` que trae cada resultado de `mem_search` (por ejemplo, `memoria:engram-obs-d2a572e53ec05212`). No uses el `id` numérico: es de esta máquina, y en la de un compañero que comparte las memorias del equipo la misma observación tiene otro, así que ahí la fila no se reconocería. Si un resultado no trae `sync_id`, el origen es `memoria:engram-<id>`, y la propuesta avisa que esa fila solo se reconoce en esta máquina. Nunca otro `:` dentro del slug, porque la regex de `matriz.py` no lo admite.
- **Si ya está graduada,** alguna pieza de un `origen` de la matriz, partido por `;`, es exactamente `memoria:engram-<sync_id>` o, en una fila anterior a este formato, `memoria:engram-<id>`: no la propongas. Compara la pieza entera, nunca una subcadena (`memoria:engram-12` no es `memoria:engram-123`). Este comando imprime `True` si ya está:

  ```bash
  python3 -c "import csv, sys; filas = list(csv.reader(open('.claude/reglas/matriz.csv', encoding='utf-8', newline='')))[1:]; print(any(pieza in sys.argv[1:] for fila in filas if len(fila) > 1 for pieza in fila[1].split(';')))" "memoria:engram-<sync_id>" "memoria:engram-<id>"
  ```

  Una fila con el `id` numérico solo es segura en la máquina que la escribió: en otra, ese número puede ser otra observación.

- **El límite:** el registro local solo acepta slugs de archivos, así que lo de engram no se registra como `vista` ni `descartada`. Puede volver a proponerse en la próxima corrida; lo ya graduado se reconoce por su fila.

### M3. La propuesta y el sí

Juzga cuáles de los candidatos suenan a regla (un criterio de revisión o una convención de una capa) y con qué destino. Muestra, **antes de escribir nada**:

1. **La cobertura de cada fuente:** la línea de la memoria en archivos (`completa`, con cuántas, el directorio y si fue `pasada` o `derivada`, o `no disponible`) y la de engram.
2. **Los candidatos, uno por fila:** el slug (o `engram-<sync_id>`; sin `sync_id`, `engram-<id>`, con el aviso de que esa fila solo se reconoce en esta máquina); la fila exacta de la matriz con todos sus campos (el `id` que le va a tocar y `memoria:<slug>` como `origen`); el destino, con el texto exacto de la regla que va ahí; y la entrada de `.claude/reglas/evidencia.md`, con su texto exacto (salvo un `descarte`, que no lleva). Calcula ese `id` igual que el script del paso 5, sin escribir nada: el siguiente libre de `<rule_prefix>-NN` entre los de `.claude/reglas/matriz.csv` y los que ya usa `.claude/reglas/verificar_<capa>.py`, y para varios candidatos de la misma capa, los que siguen, en el orden en que se van a escribir.
3. **Las «sin fila»:** las `nueva` y `cambiada` que no suenan a regla, las de dominio o de metodología y las de motor, cada una con su slug y el porqué en pocas palabras.
4. **El registro local:** qué slugs quedan como `vista` (lo mostrado que no se aprueba, las «sin fila» incluidas) y cuáles como `descartada` (lo que el usuario descarta explícitamente). Avisa que lo que queda `vista` o `descartada` no vuelve a proponerse mientras el `modified` de su memoria no cambie.
5. **El commit** (M5): los archivos y el mensaje.

Después pide un sí explícito. Si el usuario aprueba solo algunos, descarta otros o corrige una fila, ajusta la propuesta y vuelve a mostrarla.

### M4. Con el sí

1. **Lo aprobado se escribe como en el paso 5:** la fila con su script, con `memoria:<slug>` como `origen` y sin hash; la regla en su destino, con su ID, su severidad y sus números; la evidencia en `.claude/reglas/evidencia.md`, la misma que mostró la propuesta, que cita el ID y dice que sale de la memoria `<slug>`, sin copiarla; y los dos chequeos de `matriz.py` por capa, con 0 fallas. Rigen las excepciones del paso 5: con destino `evidencia`, el ID aparece una sola vez en `evidencia.md`, y un `descarte` no lleva evidencia ni aparece en ningún destino. Si un chequeo de `matriz.py` pide corregir la fila, la regla o la evidencia, muestra la corrección tal como va a quedar escrita y pide el sí antes de escribirla.
2. **El registro, solo de slugs de archivos y con el mismo `--memorias` de M1:**

   ```bash
   python3 "<S>/memorias.py" --json --memorias "<dir>" --registrar <slug> <slug> --como vista
   python3 "<S>/memorias.py" --json --memorias "<dir>" --registrar <slug> --como descartada
   ```

   Lo graduado no se registra: la matriz manda. Si sale con 2, muestra el motivo; no se registró nada.
3. **La comprobación:** corre otra vez M1. Lo graduado tiene que salir `graduada`, con su ID en `filas`, y lo registrado, `vista` o `descartada`. Si algo no cuadra, dilo antes del commit.

### M5. El commit

Como en el paso 9: el `status`, el `git add` explícito y anclado con `:/` de lo que tocó este modo (la matriz, los destinos y `evidencia.md`), y el commit sin volver a preguntar, salvo con `"ask_before_commit": true`. El registro local está fuera del repo y no entra.

```bash
git commit -m "chore(reglas): gradúa memorias del proyecto"
```

### Qué decir al final del modo

La cobertura de cada fuente, lo graduado (slug, ID y destino), lo registrado como `vista` o `descartada`, lo de motor, el hash del commit y, si hubo engram, que sus candidatos pueden volver a salir.
