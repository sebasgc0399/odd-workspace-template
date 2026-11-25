# Los chequeos antes de lanzar

Detalle del paso 2 del `SKILL.md` de `/odd-ws:revisar`. Las secciones y los pasos que se citan son los del `SKILL.md`.

## Qué corre el triaje

Antes de que se lance nada, el triaje corre lo determinista sobre el diff, sin gastar una corrida (I47):

- **Las reglas de cada capa tocada.** Cada archivo del diff que tiene capa y no es un doc pasa por el chequeo de su capa (`verificar_<capa>.py` de la instancia y los paquetes de esa capa), con la calibración aplicada y contra la base del triaje: una línea que ya estaba en la base nunca da un hallazgo. Un archivo del taller se mide contra su contraparte, como en las señales. Un archivo sin capa no se chequea.
- **Los marcadores de conflicto.** Cada archivo del diff, docs incluidos y también los sin trackear, se revisa en busca de un `<<<<<<<` y un `>>>>>>>` agregados en un mismo archivo. Un `=======` suelto no cuenta, porque es un subrayado de Markdown; los binarios no se miran, y un archivo con `conflict-marker-size` en `.gitattributes` se mide con su tamaño.

El resultado va en la clave `chequeos` de `triaje.json` (`archivos`, `hallazgos`, `marcadores`, `sin_chequear` y `corregir_antes_de_lanzar`) y al final del texto. Sin nada que mostrar, es una sola línea: `chequeos: sin hallazgos ni marcadores de conflicto (…)`. Los chequeos no cambian el modo: solo suman información.

## Qué haces con ellos

- **Si el triaje termina con «corregir antes de lanzar»,** muestra cada hallazgo, marcador y archivo sin chequear, y propón corregir antes de lanzar: es lo que no hace falta pagarle a un revisor para encontrarlo. Después de corregir, corre el triaje de nuevo, que vuelve a correr los chequeos, y anuncia con lo que salga.
- **Lanzar sin corregir pide un sí aparte,** además del sí del modo y su costo: que el usuario diga que se lanza con eso sin corregir. Sin ese sí, no se lanza.
- **Si se lanza sin corregir,** los hallazgos y los marcadores entran al prompt de cada corrida como ya detectados (`references/prompt.md`), para que nadie gaste en reemitirlos. En la consolidación van aparte, como «de los chequeos», con su ubicación y su regla.
- **«no se pudo chequear»** también lleva a «corregir antes de lanzar»: el chequeo de ese archivo falló o no pudo leerlo, y eso nunca quiere decir que esté limpio. Dile al usuario cuál y por qué. Corregirlo es arreglar el chequeo; si el usuario prefiere no hacerlo, lanzar pide su sí aparte, como con un hallazgo.
