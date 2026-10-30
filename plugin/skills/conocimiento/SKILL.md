---
name: conocimiento
description: Diagnostica la salud del conocimiento de la instancia (su índice, sus docs de dominio y las afirmaciones verificables) y enruta los hallazgos. Usar cuando el usuario pide revisar si los docs están sanos, buscar links o anclas rotos, docs vencidos o cifras que se contradicen entre docs.
disable-model-invocation: true
---

# /odd-ws:conocimiento

**Diagnostica, no opera.** Es de solo lectura: la salida es triaje para el usuario. No edites docs por tu cuenta.

Corre desde la carpeta de la instancia. Dónde viven los docs lo dice la sección opcional `knowledge` de `workspace.config.json` (ver `Doc/diseno.md`, «Conocimiento»):

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/conocimiento.py" [--v]
python "${CLAUDE_PLUGIN_ROOT}/scripts/conocimiento.py" --cruce
```

## Niveles

Son niveles de **naturaleza distinta**: nunca los sumes en un mismo conteo. Un veredicto presentado como sugerencia se ignora, y una sugerencia presentada como veredicto acusa en falso.

| Nivel | Comando | Naturaleza |
|---|---|---|
| 1, mecánico | `conocimiento.py [--v]` | **Hallazgos**, y aparte una worklist que no es deuda. Revisa los docs indexados, los links, las anclas, las cifras en los headings, el tope de líneas del índice, la frescura por frontmatter y lo que falta commitear. |
| 3, cruce | `conocimiento.py --cruce`, más leer | **Candidatos**, no hallazgos: el script propone y vos juzgás. Busca entidades repetidas en muchos docs y cifras del mismo sustantivo que difieren entre docs. |

Corré el nivel 1 siempre, porque es barato y determinista. El cruce, solo si lo piden o si el nivel 1 sale limpio y quedan dudas de contenido. Su precisión medida en el proyecto de origen fue de alrededor del 8 %: a esa tasa, reportar sus candidatos como hallazgos sería ruido nueve de cada diez veces.

**Salidas del nivel 1:**
- 0: sano, aunque haya worklist;
- 1: algún FAIL;
- 3: solo deuda (warn);
- 2: error (sin instancia, config rota o git roto).

El cruce sale siempre con 0.

## Reglas duras del cruce

1. **Nunca reportes una cifra sin la frase que la rodea.** Dos cifras distintas del mismo sustantivo pueden ser correctas las dos (por ejemplo, una lista filtrada y el catálogo completo).
2. **El script propone; vos decidís.** No se reporta nada sin haber leído las dos frases.
3. **Desempate: gana el doc autoritativo** (`rol: autoritativo` en el frontmatter) sobre el resumen (`rol: resumen`). Si los dos discrepan, se verifica contra el código o la base. **Nunca promedies ni concilies en una tercera cifra.**
4. **Priorizá los resúmenes:** es donde suelen estar las divergencias reales.
5. **Al corregir un dato, buscá sus copias** antes de cerrar.

## Al cerrar

Para cada hallazgo, proponé un destino (el ticket que lo originó, un ticket nuevo o el cierre del ticket en curso) y preguntá antes de escribir nada.
