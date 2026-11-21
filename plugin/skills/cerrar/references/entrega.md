# El worktree y la entrega después del cierre

Detalle de los pasos 7 y 9 del `SKILL.md` de `/odd-ws:cerrar`. Los pasos que se citan son los del `SKILL.md`.

## El worktree

Mirá «Worktree y rama» del ticket. Si usó un worktree:

- **En un repo con `"own": true`**, desarmalo vos, igual que `abrir` lo armó. Antes, comprobá dos cosas: que esté limpio (`git -C <ruta del worktree> status --porcelain` no imprime nada) y que su rama ya esté en `origin` (`git -C <repo> branch -r --contains <hash de la rama>` imprime al menos una rama, con el `fetch` del paso 6 si hizo falta). Con las dos, corré los dos comandos de abajo y mostrá lo que salió. Si falta una, no lo toques: decí cuál y dejáselo al usuario.
- **En un repo del equipo**, recordale al usuario que lo desarme a mano, porque los comandos en esos repos los corre él.

```bash
git -C <repo> worktree remove <ruta del worktree>
git -C <repo> worktree prune
```

**La rama no se borra** en este paso: su merge lo decide quien lo autoriza, no el cierre. Si la entrega todavía no está, el worktree se queda: se desarma en «La entrega después del cierre», abajo.

## La entrega después del cierre

El cierre gradúa cuando el conocimiento está verificado, no cuando el código sale, así que un ticket puede cerrarse `en revisión` y entregarse después. En un ticket real, la entrega falló después del cierre: el arreglo, el `Estado` y un segundo commit se improvisaron, y el usuario tuvo que pedirlo. Cuando la entrega queda hecha (el usuario lo dice, o la hiciste vos en un repo propio con su sí), no se vuelve a correr el cierre:

1. **Comprobá la entrega** con git de solo lectura, como en la foto del paso 6: la rama o el merge con su hash, y `git -C <repo> branch -r --contains <hash>`. El `fetch` previo, con el sí del usuario si es un repo del equipo.
2. **Si la entrega cambió código después de la revisión**, ese cambio pasa antes por `/odd-ws:revisar`: el cierre no lo cubre.
3. **En el `CLAUDE.md` del ticket:** `Estado` pasa a `listo`, la `Nota de estado` se vacía o dice lo que quede, y una entrada nueva de la bitácora trae la foto nueva de la entrega y lo que cambió desde el cierre.
4. **Commiteá en la raíz de la instancia**, con `git add` por ruta, sin preguntar salvo `"ask_before_commit": true`, y sin push: `git commit -m "chore(<id>): entrega"`.
5. **Sacale la marca de ticket activo** (`ticket.py --desactivar <id>`) y, en un repo propio, desarmá el worktree como en el paso 7.
