# La desviación conocida: su fila y el script que la agrega

Detalle de los pasos 2, 4 y 5 del `SKILL.md` de `/odd-ws:cerrar`. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`, y los pasos que se citan son los del `SKILL.md`.

Una desviación conocida es código que parece un error y es a propósito, con su porqué: por ejemplo, un `CATCH` que no relanza porque así lo pide un contrato, o un nombre mal escrito que otro sistema ya consume. Vale para toda la instancia: `/odd-ws:revisar` se la pasa a cada revisor como «no la reemitas», en cualquier ticket. Por eso entra solo con un porqué verificado (una decisión del ticket, o quién lo confirmó), nunca para callar un hallazgo que nadie aprobó. No es una fila de la matriz: no es una regla de una capa, y no tiene un destino donde escribirse.

## Las columnas

Van en `.claude/reglas/desviaciones.csv`, con el encabezado `id,ubicacion,resumen,porque,fecha`:

- `id`: corto, descriptivo y único en el archivo (por ejemplo, `catch-silencioso-ventas`). Es el nombre con que un revisor la cita. Propónlo y confírmalo con el usuario.
- `ubicacion`: dónde está, en una de dos formas:
  - código de un repo de la config: `<repo>:<ruta>@<hash>:<ini>-<fin>`, con la clave del repo en `workspace.config.json`, la ruta relativa a la raíz del repo, el commit donde está ese código y el rango de líneas (base 1). El hash sale con git de solo lectura, `git -C <ruta del repo> log -1 --format=%h -- <ruta>`, y fija el rango aunque el archivo cambie después;
  - un archivo de la instancia: su `<ruta>`, relativa a la raíz de la instancia y sin rango.
- `resumen`: qué parece un error, en una línea.
- `porque`: por qué es a propósito, con su fuente (la decisión del ticket, o quién lo confirmó).
- `fecha`: la de hoy, `AAAA-MM-DD`.

En la propuesta del paso 4 va la fila exacta, con sus cinco campos.

## El script que la agrega

Se agrega **al final**, con el módulo `csv` de Python (para que el resto del archivo quede byte a byte), con LF y sin BOM. Si el archivo no existe, lo crea con su encabezado. Guarda este script con la herramienta Write en un archivo fuera de la instancia, completa la fila y córrelo desde la raíz de la instancia:

```python
import csv, os

RUTA = ".claude/reglas/desviaciones.csv"
ENCABEZADO = ["id", "ubicacion", "resumen", "porque", "fecha"]
FILA = ["<id>", "<ubicacion>", "<resumen>", "<porque>", "<AAAA-MM-DD>"]

if not os.path.exists(RUTA) or os.path.getsize(RUTA) == 0:
    os.makedirs(os.path.dirname(RUTA), exist_ok=True)
    with open(RUTA, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerow(ENCABEZADO)
with open(RUTA, encoding="utf-8-sig", newline="") as f:
    if any(reg and reg[0].strip() == FILA[0] for reg in csv.reader(f)):
        raise SystemExit("el id %s ya está en %s: elige otro" % (FILA[0], RUTA))
with open(RUTA, "rb") as f:
    con_salto = f.read().endswith(b"\n")
with open(RUTA, "a", encoding="utf-8", newline="") as f:
    if not con_salto:
        f.write("\n")
    csv.writer(f, lineterminator="\n").writerow(FILA)
print(FILA[0])
```

Imprime el id. Después corre `python3 "<S>/desviaciones.py"`: tiene que salir con 0 y mostrar la fila nueva, en una línea. Si sale con 1, corrige la fila que nombra (una ubicación sin hash, un repo que no está en la config, una fecha mal escrita) antes de seguir; con 2, muestra el mensaje tal cual. El archivo entra en el commit de cierre (paso 9).
