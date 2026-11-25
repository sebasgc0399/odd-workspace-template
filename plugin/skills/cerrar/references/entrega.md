# La foto de la entrega, el worktree y la entrega después del cierre

Detalle de los pasos 6, 7 y 9 del `SKILL.md` de `/odd-ws:cerrar`. Los pasos que se citan son los del `SKILL.md`.

## La foto de la entrega

Va en la última entrada de la bitácora (paso 6), por repo: la rama con su hash, o qué falta subir y de quién (también en la `Nota de estado`). Se saca con git de solo lectura: `git -C <repo> log -1 --format=%h <rama>` y, si está pusheada, `git -C <repo> branch -r --contains <hash>`. Si el `origin` puede estar atrasado, propón el `git fetch` de ese repo y córrelo solo con el sí del usuario, porque habla con el remoto; sin fetch ni forma de comprobarlo, se anota **«no verificado»**.

## El worktree

Mira «Worktree y rama» del ticket. Si usó un worktree:

- **En un repo con `"own": true`**, desármalo tú, igual que `abrir` lo armó. Antes, comprueba dos cosas: que esté limpio (`git -C <ruta del worktree> status --porcelain` no imprime nada) y que su rama ya esté en `origin` (`git -C <repo> branch -r --contains <hash de la rama>` imprime al menos una rama, con el `fetch` de la foto si hizo falta). Con las dos, corre los dos comandos de abajo y muestra lo que salió. Si falta una, no lo toques: di cuál y déjaselo al usuario.
- **En un repo del equipo**, recuérdale al usuario que lo desarme a mano, porque los comandos en esos repos los corre él.

```bash
git -C <repo> worktree remove <ruta del worktree>
git -C <repo> worktree prune
```

**La rama no se borra** en este paso: su merge lo decide quien lo autoriza, no el cierre. Si la entrega todavía no está, el worktree se queda: se desarma en «La entrega después del cierre», abajo.

## La entrega después del cierre

El cierre gradúa cuando el conocimiento está verificado, no cuando el código sale, así que un ticket puede cerrarse `en revisión` y entregarse después. En un ticket real, la entrega falló después del cierre: el arreglo, el `Estado` y un segundo commit se improvisaron, y el usuario tuvo que pedirlo. Cuando la entrega queda hecha (el usuario lo dice, o la hiciste tú en un repo propio con su sí), no se vuelve a correr el cierre:

1. **Comprueba la entrega** con git de solo lectura, como en «La foto de la entrega», arriba: la rama o el merge con su hash, y `git -C <repo> branch -r --contains <hash>`. El `fetch` previo, con el sí del usuario si es un repo del equipo.
2. **Si la entrega cambió código después de la revisión**, ese cambio pasa antes por `/odd-ws:revisar`: el cierre no lo cubre.
3. **En el `CLAUDE.md` del ticket:** `Estado` pasa a `listo`, la `Nota de estado` se vacía o dice lo que quede, y una entrada nueva de la bitácora trae la foto nueva de la entrega y lo que cambió desde el cierre.
4. **Commitea en la raíz de la instancia**, con `git add` por ruta, sin preguntar salvo `"ask_before_commit": true`, y sin push: `git commit -m "chore(<id>): entrega"`.
5. **Sácale la marca de ticket activo** (`ticket.py --desactivar <id>`) y, en un repo propio, desarma el worktree como en el paso 7.
