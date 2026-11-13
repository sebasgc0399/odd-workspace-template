# Actualizar el plugin

La versión está fijada en `plugin.json` y la actualización automática viene apagada, así que se actualiza a mano, entre tickets. Qué trae cada versión está en el [CHANGELOG](../CHANGELOG.md).

## En Claude Code

```text
claude plugin marketplace update odd-workspace-template
claude plugin update odd-ws@odd-workspace-template
```

Después, `/plugin` dentro de una sesión debe mostrar la versión nueva, con la pestaña de errores vacía.

## En Codex

```text
codex plugin marketplace upgrade odd-workspace-template
codex plugin add odd-ws@odd-workspace-template
```

Después, abre `codex` y vuelve a confiar los hooks en `/hooks`. `/odd-ws:doctor` (en Codex, `$doctor`) avisa si a alguno le falta la confianza.

## Después de actualizar: regenerar los writers

Corre `/odd-ws:doctor` (en Codex, `$doctor`). Si una versión cambia la plantilla de los writers, cada `writer-<capa>` sale **atrasado**: aplica su arreglo (`--arreglar writer-<capa>`) y, si usas Codex, después `--arreglar codex-agentes`, que deriva los TOML desde el `.md` ya regenerado. Regenerar conserva la `description` y los bloques `<!-- instancia:... -->` de cada writer.

Mientras un writer siga en la plantilla vieja, la compuerta de cierre le pide lo que la plantilla nueva agrega. Por ejemplo, desde la plantilla 2 un writer de la plantilla 1 cierra sin `limites:`, se come el único bloqueo de la compuerta y pasa en el segundo cierre. No se traba, pero cada cierre gasta ese aviso hasta que lo regeneres.
