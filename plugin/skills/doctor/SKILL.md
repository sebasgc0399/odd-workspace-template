---
name: doctor
description: Chequeo de la máquina (Capa 0) para trabajar con la plantilla ODD. Usar al estrenar portátil, después de clonar el repo de la plantilla, cuando un hook no corre o cuando el usuario pide revisar el entorno. Muestra una tabla OK / FALTA / AVISO y arregla de a un ítem, solo con autorización.
---

# /odd-ws:doctor

Corre el diagnóstico desde el directorio del proyecto (si es un clon de `odd-workspace-template`, también revisa sus hooks y la lista negra; si es una instancia, `plugin-root`: la ruta del plugin que usa su pre-commit, anotada en `workspace.local.json`, un ítem `writer-<capa>` por cada capa declarada, que revisa `.claude/agents/writer-<capa>.md` contra la plantilla del plugin, y dos ítems de sus agentes: `agentes-skills`, que las skills precargadas con `skills:` existan y se precarguen de verdad, y `agentes-hooks`, que ningún agente declare `hooks:` en el frontmatter):

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
```

Sale con 0 si no hay ninguna FALTA y con 1 si hay alguna. Los AVISO no hacen fallar.

## Cómo presentarlo

1. Mostrá la tabla tal cual sale.
2. Para cada FALTA y cada AVISO, explicá en una línea qué rompe si no se arregla.
3. **Ofrecé los arreglos de a uno.** Si el ítem tiene arreglo automático (la línea `arreglo: --arreglar <id>`), preguntá si lo aplicás. Corré `--arreglar <id>` **solo** después de un sí explícito para **ese** ítem:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --arreglar <id>
   ```

4. Si el ítem no tiene arreglo automático, pasale al usuario el texto de `cómo:`. No lo hagas por tu cuenta: son cambios de la máquina (PATH, instaladores, la lista negra).

## Reglas

- **`rdd`:** el interruptor del RDD de gentle-ai es del usuario. `--arreglar rdd` se corre solo si el usuario pide apagarlo; un AVISO no es permiso.
- **gentle-ai:** nunca le pases `--help` ni invoques `upgrade` (`gentle-ai upgrade --help` ejecuta el upgrade). El doctor solo usa `version`, `review mode status` y `telemetry status`.
- **`lista-negra`:** nunca leas ni muestres el contenido de la lista negra; es confidencial. Si falta, el usuario la crea.
- **`writer-<capa>`:** `--arreglar` escribe en la instancia: crea el writer que falta o regenera el atrasado, y conserva su `description` y sus bloques `<!-- instancia:... -->`. Antes de pedir el sí, decí qué archivo va a escribir. Un writer editado fuera de los bloques o escrito a mano es FALTA sin arreglo: no lo borres ni lo muevas por tu cuenta, pasale al usuario el texto de `cómo:`.
- **`agentes-skills` y `agentes-hooks`:** no tienen arreglo automático. Pasale al usuario el texto de `cómo:` y no edites los agentes ni las skills por tu cuenta.
- Después de cada arreglo, el doctor vuelve a chequear el ítem: reportá ese resultado, no el que esperabas.
