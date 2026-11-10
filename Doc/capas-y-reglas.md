# Capas y reglas propias

La plantilla trae una sola biblioteca de reglas, la de T-SQL (`odd_ws.tsql`). Para cualquier otro stack, las reglas de cada capa se escriben en la instancia.

- **El módulo.** Cada capa tiene su `.claude/reglas/verificar_<capa>.py`. El bootstrap lo deja vacío: `REGLAS = ()` y `verificar(ctx)` devuelve `[]`. Su `verificar_<capa>.tests.py` valida el contrato.
- **El contrato.** `verificar(ctx)` recibe el archivo editado (`ruta`, `texto`, `agregadas`, `hunks`, `es_nuevo`, entre otros). Devuelve una lista de hallazgos `{id, modo, severidad, linea, fragmento, mensaje}`, con `modo` en `bloqueo` o `aviso`. El detalle está en [Contrato de los módulos de capa](diseno.md#contrato-de-los-módulos-de-capa-p1), en `Doc/diseno.md`.
- **Correrlas sin Claude.** `reglas.py` está en `scripts/` del plugin; su ruta queda en `plugin_root` de `workspace.local.json`.

  ```text
  python3 "<plugin_root>/scripts/reglas.py" --test [CAPA]
  python3 "<plugin_root>/scripts/reglas.py" --calibrar CAPA CARPETA [--detalle]
  ```

  `--test` corre las pruebas de las reglas. `--calibrar` pasa las reglas sobre una carpeta de código real y cuenta cuántas veces salta cada una. Las dos aceptan `--raiz <instancia>`.
- **La matriz.** Cada convención nueva entra como una fila de `.claude/reglas/matriz.csv`, con su id `<prefijo>-NN`, su origen, su tipo, su destino y su severidad. `/odd-ws:cerrar` la agrega por ti.
- **Agregar una capa a una instancia que ya existe.** Suma la capa a `workspace.config.json` y la ruta de sus repos a `workspace.local.json`, a mano. Después vuelve a correr `/odd-ws:bootstrap`: genera lo que falta de la capa nueva sin tocar lo que ya existe.

Cuándo corren estas reglas durante una sesión está en [Hooks](hooks.md#cuándo-corre-cada-uno).
