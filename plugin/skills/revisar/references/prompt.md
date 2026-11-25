# El prompt de cada corrida

Plantilla de la sección 4 del `SKILL.md` de `/odd-ws:revisar`: se copia tal cual y se completan los `<…>`.

**Orden barajado (modo `completo`).** La primera corrida de diseño recibe los archivos en el orden del triaje; la segunda, en el orden inverso; la tercera, en un orden barajado. El orden va escrito en el prompt como lectura sugerida. Con un solo archivo el orden es el mismo y las 3 son muestras independientes: no lo anuncies como «en otro orden».

**La forma del prompt:**

```
Revisa <el diseño | el código de la capa <capa>> del ticket <id> (<título>) antes del commit.

Entrada:
- Diff de <repo>: <ruta de <repo>.diff> (base <commit>, rama <rama>). El código completo está en <ruta del repo o worktree>: lee ahí el código, sus hermanos y sus consumidores.
- (una línea por cada repo tocado)
- Carpeta del ticket: <ruta>. Lee su CLAUDE.md del disco, aunque ya tengas uno cargado: el que cargaste al arrancar puede ser anterior al Paso 0. No leas su carpeta revision/: trae reportes de otras revisiones.
- <solo capa> Archivos de tu capa: <lista>.
- <solo diseño, modo completo> Orden de lectura sugerido: <lista>.

Ya decidido en el ticket (## Decisiones), no lo vuelvas a plantear como hallazgo; si un CRITICAL lo contradice, repórtalo y nombra la decisión:
- <una línea por decisión, copiada de ## Decisiones, o «ninguna»>

Entrega el reporte con tu contrato. En cada hallazgo, justo después de la severidad, cita el ID de la regla de la matriz que rompe, o `sin ID` si no viene de una regla con ID:
[SEVERIDAD] <ID de la regla | sin ID> ruta:línea — qué viola — cómo debe quedar

Escribe el reporte entero como tu último bloque de texto y, en la misma respuesta, devuelve solo esta línea, con tus cuentas:
VEREDICTO: <n> CRITICAL, <n> WARNING, <n> SUGGESTION
```

- **El reporte va en el último bloque de texto y la devolución es una línea (I35).** Cada reporte, de 14k a 27k caracteres, entraba entero al contexto del orquestador. Ahora el orquestador recibe solo el `VEREDICTO:`, y `rescatar.py` lee el reporte del texto que el revisor escribió justo antes de devolverlo. Si el revisor devuelve solo el veredicto, sin el reporte antes, el rescate falla en voz alta y no escribe nada. Para leer los hallazgos, el orquestador abre el `<nombre>.md` rescatado. La regla va en el prompt y no en las plantillas, por la misma razón que el ID de la regla.
- **Las decisiones van copiadas en el prompt**, no solo en el `CLAUDE.md` del ticket: en un ticket real, tres corridas de un `completo` pidieron quitar algo que el usuario ya había aprobado.
- **El ID de la regla también va en el prompt**, y no en las plantillas de los revisores: un cambio de plantilla no llega a los revisores ya generados. `revisor-diseno` solo ve los IDs de `criterios`, así que `sin ID` es una respuesta normal. Nunca pongas un ID de ejemplo en el prompt: el revisor lo copiaría.
- **En un rechequeo**, el prompt suma los hallazgos de la ronda anterior (sección 9) y no lleva orden barajado.
- Si el agente no existe (por ejemplo, `revisor-diseno` en una instancia que se generó antes de que el plugin lo trajera), no lo reemplaces con otro: dile al usuario que complete la instancia con `/odd-ws:bootstrap`, y que si el agente es nuevo en esta sesión hace falta reabrirla.
