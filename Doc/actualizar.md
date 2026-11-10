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
