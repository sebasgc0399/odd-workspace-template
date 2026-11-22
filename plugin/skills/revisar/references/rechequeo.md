# El rechequeo: qué entra, su base, su modo y su recibo

Detalle de la sección 9 del `SKILL.md` de `/odd-ws:revisar`. `<S>` es la carpeta `scripts` del plugin, como en el `SKILL.md`, y las secciones y los pasos que se citan son los del `SKILL.md`.

## Por qué una corrección y un rechequeo

Una revisión se cierra así, para que corregir no se vuelva un bucle ni cueste una revisión entera por vuelta. En un ticket real, la re-revisión después de una corrección volvió a revisar la unidad entera, al mismo costo que la primera, y no se podía sellar una parcial; los hallazgos que quedaron para después terminaron dentro de la tabla de Tareas, y la rompieron.

## Cómo se arma

Un rechequeo verifica los hallazgos anteriores y revisa solo lo que cambió desde la ronda anterior:

- **Qué entra.** Los rechequeados son los archivos que nombra `recibo.py --check "<carpeta de la ronda anterior>"` cuando sale con 1 (los que cambiaron), más los que el triaje lista y el recibo anterior no tiene (los que sumó la corrección, como un test nuevo). Si `--check` sale con 0 y la corrección no sumó archivos, no hay nada que rechequear. Un archivo sumado nunca se salta: sin su rechequeo queda sin revisar y `--sellar` rechaza el commit que lo trae.
- **La base** es la del recibo anterior, y el triaje con `--ticket` da esa misma mientras la unidad no se selle. **El modo** es el de la ronda anterior, y la carpeta es la ronda siguiente (`<fecha>-<modo>-<n>`); `recibo.py` no deja bajarlo, tampoco con una fecha posterior. Si el triaje de ahora da otra base o propone un modo más alto, no es un rechequeo: es una revisión nueva de la unidad entera, que pide su sí.
- **Después de una bajada** (el recibo anterior trae `bajada`), el rechequeo se mide contra el modo bajado: sigue en `rapido`, y que el triaje vuelva a proponer `completo` no es un modo más alto. Un riesgo real nuevo sí lo es, y la revisión nueva va en `completo`. El recibo del rechequeo hereda la bajada sin volver a pasarla, y `recibo.py` valida el `triaje.json` de la entrada de esta ronda: sin él, con un riesgo real o si no es de este diff (los archivos de toda la unidad, con su huella de ahora), sale con 2 sin escribir nada.
- **Las corridas** son una de `revisor-diseno` más una por cada capa de los archivos rechequeados, `1 + <capas>`, tanto en `rapido` como en `completo`, sobre un diff que trae solo esos archivos. En modo `0` son cero. El rechequeo verifica una corrección acotada y no repite las tres corridas de `completo`: en un ticket real, dos rechequeos de una corrida, con los hallazgos anteriores en el prompt, cerraron bien. Un rechequeo corre `revisor-diseno` ×1 más `revisor-<capa>` ×1 por cada capa de los rechequeados, también en modo `completo`: sin orden barajado ni frecuencias. Si los rechequeados tocan una capa que el mensaje del lote no anunció, el costo cambió: anuncia el nuevo, con las corridas y el último costo medido, y pide el sí.
- **La entrada** es el diff de los rechequeados contra la base, con su `triaje.json` (paso 3). El prompt suma los hallazgos de la ronda anterior, con su ubicación, su regla y su severidad, copiados del `consolidado.md`, y pide decir de cada uno si quedó resuelto. La regla de no leer `revision/` sigue.

## El recibo del rechequeo

El recibo hereda lo que no cambió:

```bash
python3 "<S>/recibo.py" --write --ticket "<ticket>" --repo <repo>#<base> [--repo …] --archivo <rechequeado> [--archivo …] --previo "<ticket>/revision/<carpeta de la ronda anterior>" --modo <modo> --fecha <AAAA-MM-DD> --ronda <n> --reviewer <agente> [--reviewer …] --verificacion "<comando>: <resultado>" [--verificacion …] --estado <limpio|con-hallazgos|pendiente> [--derivado "<hallazgo>=<destino>" …]
```

- `--archivo` lista solo lo rechequeado, y el recibo cubre la unidad entera: lo rechequeado, con su hash de ahora, y cada archivo del recibo anterior que no se pasó, que tiene que estar igual que entonces. Un repo del recibo anterior sin nada rechequeado no se pasa: se hereda entero. Un `--repo` sin `#<base>` toma la base del recibo anterior.
- Un archivo nuevo de la unidad que la corrección quitó se pasa con `--archivo`: queda en `retirados`, fuera del recibo.
- **Exit 1**, sin escribir nada: un archivo del recibo anterior cambió y no está en `--archivo` (rechequéalo), o la base no es la del recibo anterior.
- **Exit 2:** `--previo` no es un recibo de este ticket, `--modo` es más bajo que el suyo, o el rechequeo no queda después de él: tiene que ir en la misma fecha y modo con una `--ronda` más alta, o en una fecha posterior.
- Con eso, `--check` y `--sellar` valen para la unidad entera.

## Lo que trae el rechequeo

- un hallazgo `CRITICAL`, nuevo o uno anterior que sigue abierto, se corrige en esta unidad, como un lote nuevo con su rechequeo, y los dos siguen esta misma regla;
- un hallazgo que no es `CRITICAL`, nuevo o uno anterior que sigue abierto, **se deriva**: no se corrige en esta unidad, sino que va a otra tarea, otro ticket o el backlog. Anótalo en el recibo con `--derivado "<hallazgo>=<destino>"` y en `## Seguimientos` del ticket, una línea por hallazgo (`<fecha>: <qué> → <destino>`), nunca en la tabla de Tareas;
- con eso la revisión queda cerrada: el recibo del rechequeo es el de la unidad, y después del commit se sella.
