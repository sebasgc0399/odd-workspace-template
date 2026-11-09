---
name: conocimiento
description: Diagnostica la salud del conocimiento de la instancia (su índice, sus docs de dominio y las afirmaciones verificables) y enruta los hallazgos. Usar cuando el usuario pide revisar si los docs están sanos, buscar links o anclas rotos, docs vencidos o cifras que se contradicen entre docs.
disable-model-invocation: true
---

# /odd-ws:conocimiento

**Diagnostica, no opera.** Es de solo lectura: la salida es triaje para el usuario. No edites docs por tu cuenta.

Corre desde la carpeta de la instancia. Dónde viven los docs lo dice la sección opcional `knowledge` de `workspace.config.json` (ver `Doc/diseno.md`, «Conocimiento»):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/conocimiento.py" [--v]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/conocimiento.py" --cruce
```

En Windows con Codex, los comandos van con `python` en lugar de `python3`.

## Niveles

Son niveles de **naturaleza distinta**: nunca los sumes en un mismo conteo. Un veredicto presentado como sugerencia se ignora, y una sugerencia presentada como veredicto acusa en falso.

| Nivel | Comando | Naturaleza |
|---|---|---|
| 1, mecánico | `conocimiento.py [--v]` | **Hallazgos**, y aparte una worklist que no es deuda. Revisa los docs indexados, los links, las anclas, las cifras en los headings, el tope de líneas del índice, la frescura por frontmatter, la cobertura de afirmaciones y lo que falta commitear. |
| 2, afirmaciones | `conocimiento.py --claims` | **Veredictos.** Lintea el archivo de afirmaciones, ejecuta las de `repo` con una lista blanca de comandos de solo lectura y las juzga: `ok`, `+` (creció), `ROJO` o `err`. Las SQL todavía no se juzgan. |
| 3, cruce | `conocimiento.py --cruce`, más leer | **Candidatos**, no hallazgos: el script propone y vos juzgás. Busca entidades repetidas en muchos docs y cifras del mismo sustantivo que difieren entre docs. |

Corré los niveles 1 y 2 siempre, porque son baratos y deterministas. El cruce, solo si lo piden o si el nivel 1 sale limpio y quedan dudas de contenido. Su precisión medida en el proyecto de origen fue de alrededor del 8 %: a esa tasa, reportar sus candidatos como hallazgos sería ruido nueve de cada diez veces.

**Salidas del nivel 1:**
- 0: sano, aunque haya worklist;
- 1: algún FAIL;
- 3: solo deuda (warn);
- 2: error (sin instancia, config rota o git roto).

El cruce sale siempre con 0.

**Salidas del nivel 2:**
- 0: todo verde (un `+` no es un hallazgo: se mueve la línea base);
- 1: algún `ROJO`, algún `err`, un FAIL del lint o un archivo que no carga;
- 2: config rota.

Si aparece `TIER 2 ABIERTO`, quedan afirmaciones SQL sin veredicto, y ese nivel no está cerrado aunque salga con 0.

## Afirmaciones (nivel 2)

- Viven en el archivo de `knowledge.claims` (por defecto, `<docs>/_claims.json`), en JSON.
- Cada afirmación declara un `comando` de solo lectura sobre un repo de la config (`repo` es su clave en `repos`) y el valor `expected`. Un invariante que cambia sale `ROJO`; un inventario que sube sale `+`.
- El comando se valida token por token y corre tal cual se validó. Fuera de comillas no valen `{ } * ? [ ] ~` ni las redirecciones, así que un ref relativo va entre comillas: `'{ref}~1'`. Si el lint lo rechaza, lo dice con su motivo.
- **Un `ROJO` se resuelve leyendo el código**, no tocando el `expected`. O el doc quedó viejo, y se corrige con sus copias, o el código rompió lo que el doc afirma, y se avisa.
- El motor no hace fetch: si avisa que el último fetch de un repo es viejo, el veredicto puede estar desactualizado. El fetch lo hace el usuario.

## Reglas duras del cruce

1. **Nunca reportes una cifra sin la frase que la rodea.** Dos cifras distintas del mismo sustantivo pueden ser correctas las dos (por ejemplo, una lista filtrada y el catálogo completo).
2. **El script propone; vos decidís.** No se reporta nada sin haber leído las dos frases.
3. **Desempate: gana el doc autoritativo** (`rol: autoritativo` en el frontmatter) sobre el resumen (`rol: resumen`). Si los dos discrepan, se verifica contra el código o la base. **Nunca promedies ni concilies en una tercera cifra.**
4. **Priorizá los resúmenes:** es donde suelen estar las divergencias reales.
5. **Al corregir un dato, buscá sus copias** antes de cerrar.

## Al cerrar

Para cada hallazgo, proponé un destino (el ticket que lo originó, un ticket nuevo o el cierre del ticket en curso) y preguntá antes de escribir nada.
