# La fila de la matriz: sus columnas, el script, la evidencia, el sembrado y las disputas

Detalle del paso 5 del `SKILL.md` de `/odd-ws:cerrar`, que también usa M4 del modo memorias. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`, y los pasos que se citan son los del `SKILL.md`.

## Las columnas

Las columnas, en este orden, son `id, origen, tipo, destino, severidad, numeros, resumen, motivo`:

- `id`: el siguiente libre de la capa, `<rule_prefix>-NN` (por ejemplo `EJ-01`, `EJ-02`). El script de abajo lo calcula con la matriz y con los ids que ya usa `.claude/reglas/verificar_<capa>.py`, porque una instancia puede traer reglas propias sin fila en la matriz.
- `origen`: fijado a un commit que ya existe, `<ruta>@<hash>:<ini>-<fin>` (el rango es de líneas, base 1), normalmente la decisión del ticket o su bitácora. **Si la fuente todavía no está commiteada, hay que commitearla antes** (con el sí del usuario): compruébalo con `git status --short -- <ruta>`, que tiene que salir vacío, y saca el hash con `git log -1 --format=%h -- <ruta>`. Una memoria va como `memoria:<slug>` y no lleva hash.
- `tipo`: qué clase de conocimiento es la regla, uno de `CE` (convención de escritura), `CC` (convención con caso), `PR` (procedimiento de revisión), `CR` (contexto de repos), `MT` (matiz transversal) o `META` (los metadatos del agente, como su frontmatter). Propón el que corresponda y confírmalo con el usuario; si dudas, mira el de una fila vecina de la matriz con el mismo destino.
- `destino`: **uno solo**: `chequeo`, `pasiva`, `skill`, `reviewer-PR`, `criterios`, `evidencia` o `descarte`. Son archivos de la instancia: `chequeo` es `.claude/reglas/verificar_<capa>.py`; `pasiva` es el bloque `no-negociables` de `.claude/skills/capa-<capa>/SKILL.md`; `skill` es ese mismo archivo, fuera del bloque; `reviewer-PR` es `.claude/agents/revisor-<capa>.md`; `criterios` es `.claude/skills/criterios/SKILL.md` (o su `references/`); `evidencia` es `.claude/reglas/evidencia.md`.
- `severidad`: `CRITICAL`, `WARNING`, `SUGGESTION` o vacía. `numeros`: cifras que la regla tiene que citar, separadas por `;`, o vacío. `resumen` y `motivo`: texto, no pueden quedar vacíos.
- Una regla transversal lleva una fila por cada capa a la que aplica, y se deja escrito por qué no a las otras.

## El script que la agrega

Se agrega **al final**, con el módulo `csv` de Python (para que el resto del archivo quede byte a byte), con LF y sin BOM. Guarda este script con la herramienta Write en un archivo fuera de la instancia, completa los campos y córrelo desde la raíz de la instancia:

```python
import csv, re

RUTA = ".claude/reglas/matriz.csv"
REGLAS = ".claude/reglas/verificar_<capa>.py"
PREFIJO = "<rule_prefix>"
FILA = ["", "<ruta>@<hash>:<ini>-<fin>", "<tipo>", "<destino>", "<severidad>", "<numeros>", "<resumen>", "<motivo>"]

ID = re.escape(PREFIJO) + r"-([0-9]{2,})"
ultimo = 0
with open(RUTA, encoding="utf-8", newline="") as f:
    for reg in csv.reader(f):
        m = re.fullmatch(ID, reg[0]) if reg else None
        if m:
            ultimo = max(ultimo, int(m.group(1)))
try:
    with open(REGLAS, encoding="utf-8", errors="replace") as f:
        for m in re.finditer(r"\b" + ID + r"\b", f.read()):
            ultimo = max(ultimo, int(m.group(1)))
except FileNotFoundError:
    pass
FILA[0] = "%s-%02d" % (PREFIJO, ultimo + 1)
with open(RUTA, "a", encoding="utf-8", newline="") as f:
    csv.writer(f, lineterminator="\n").writerow(FILA)
print(FILA[0])
```

Imprime el ID asignado. Después escribe la regla **en su destino, con ese ID**, en una línea o párrafo que además contenga la severidad y los números de la fila (el chequeo busca el ID y su segmento, hasta la línea en blanco siguiente).

## La evidencia

Una medición es una fila con `destino` `evidencia`: su ID tiene que aparecer **una sola vez** en `.claude/reglas/evidencia.md`, con su fuente (por ejemplo, bajo un encabezado con el ID). La evidencia de una regla que va a otro destino también se anota ahí citando su ID, salvo que la fila sea `descarte`: el chequeo exige que un descarte no aparezca en ningún destino. Una regla sin evidencia no entra a la matriz.

## Un chequeo que tiene que bloquear

Una regla que va a `chequeo` con `modo` `bloqueo` empieza avisando: bloquea solo después de calibrarse.

- **Su sembrado.** En su objeto de `REGLAS` lleva `sembrado`: un texto con el defecto que la regla tiene que atrapar. Si la regla mira la ruta del archivo o una extensión que no es la primera de la capa, el `sembrado` es `{"ruta": "<ruta relativa, con />", "texto": "<el defecto>"}`, porque un texto solo le llega como `sembrado<primera extensión>`. Va en la propuesta del paso 4, junto a la fila. Una regla de estilo que solo avisa no lo necesita.
- **Su calibración.** Después de escribirla, corre `python3 "<S>/reglas.py" --calibrar <capa> <carpeta> --guardar`, con código real de la capa (o una carpeta vacía en un proyecto sin código todavía), y muestra la línea de la regla: `puede bloquear`, o `solo avisa:` con el porqué. Si solo avisa, dilo y anótalo como pendiente; no lo escondas.
- **El registro** `.claude/registro/calibracion.json` entra en el commit de cierre (paso 9). Calibrar reescribe la entrada de todas las reglas de la capa y de sus paquetes, porque cambiar el módulo deja vieja la calibración de toda la capa.

## Un bloqueo que estuvo mal: la disputa

Si el ticket anota que una regla bloqueó algo correcto, propón en el paso 4 su disputa: el archivo `.claude/registro/disputas/<ID>.md`, con quién la abre, qué bloqueo (archivo y línea) y por qué. Mientras exista, la regla solo avisa. Se escribe con el sí, como todo: ningún script abre una disputa solo. Si este cierre arregla el chequeo de una regla disputada, el mismo commit borra su archivo y lleva la recalibración. Una regla de un paquete se arregla en el repo del paquete, no aquí: su disputa queda abierta hasta que `actualizar` traiga el arreglo. El formato está en «Las disputas» de `Doc/capas-y-reglas.md`, en el repo del plugin.
