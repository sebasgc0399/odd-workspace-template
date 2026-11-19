---
name: enlaces
description: Lista los enlaces de un ticket de la instancia o de cualquier documento .md, con su ruta absoluta y con los rotos y las rutas de la máquina aparte, y abre o copia el que elige el usuario. Usar cuando el usuario pide abrir, revisar, copiar o depurar los enlaces de un ticket o de un .md.
---

# /odd-ws:enlaces

Muestra los enlaces de un ticket, o de cualquier `.md`, para revisarlos o depurarlos, y abre el que elige el usuario. Con un id corre desde la raíz de la instancia o desde dentro de un ticket; con la ruta de un `.md`, desde cualquier carpeta, como un `odd/tasks/<feature>.md` del ODD de gentle-ai. En los comandos, `<S>` es `${CLAUDE_PLUGIN_ROOT}/scripts`, y `<id | ruta>` es el id del ticket o la ruta al `.md`. En Windows con Codex, los comandos van con `python` en lugar de `python3`.

## Reglas duras

1. **Nunca abrís un enlace por tu cuenta**, ni siquiera cuando la lista tiene uno solo: abrir lanza un programa del sistema, y lo decide el usuario cada vez.
2. **Solo se abre un número de la lista**, con `--abrir <n>`. Los rotos y los que llevan esquema no tienen número y no se abren, y ninguna ruta se abre por otro camino.
3. **Esta skill no edita el documento.** Arreglar un roto o una ruta de la máquina es editarlo: proponé el cambio y hacelo solo con el sí del usuario.

## Pasos

1. **La lista.** Solo lee:

   ```bash
   python3 "<S>/ticket.py" --enlaces <id | ruta>
   ```

   Si el id tiene varias carpetas, el mensaje las nombra: preguntale al usuario cuál es y pasale la ruta de su `CLAUDE.md`.
2. **Mostrala tal cual**, con dos grupos aparte:
   - **los rotos**, bajo `rotos: <n>`, cada uno con `no existe`: su destino no está;
   - **las rutas de la máquina**, las líneas que terminan en `(ruta de la máquina)`, numeradas o rotas: un destino absoluto (`C:\…`, `/home/…`, `~/…`) funciona en esta máquina, pero se rompe en el clon de otra persona.

   Si no hay ninguno de los dos, decilo en una línea.
3. **Preguntale cuál quiere abrir**, por su número. Si no quiere abrir ninguno, terminá ahí.
4. **Con su elección, y solo con ella:**

   ```bash
   python3 "<S>/ticket.py" --enlaces <id | ruta> --abrir <n>
   ```

   Una carpeta se abre en el gestor de archivos, y un documento, un dato o una imagen, con su programa. Cualquier otro archivo (un script, un ejecutable) se muestra en su carpeta sin abrirlo, porque abrirlo podría ejecutarlo. La última línea dice qué se abrió y cómo. Si sale con 1 y dice `no se abrió <ruta>: <motivo>`, pasale esa línea al usuario tal cual: la ruta está ahí para que la abra a mano o la copie. No lo reintentes de otra forma.
5. **Si quiere las rutas**, en vez de abrir:

   ```bash
   python3 "<S>/ticket.py" --enlaces <id | ruta> --copiar
   ```

   Manda las rutas absolutas, sanas y rotas, al portapapeles, una por línea. Si no hay con qué copiar, avisa por stderr y la lista sale igual: decíselo al usuario, que la copia de la pantalla.

## Cuándo no abre

`--abrir` sale con 1, sin abrir, y dice por qué:

- en una sesión remota (`SSH_CONNECTION`) o sin pantalla, porque se abriría en otra máquina o no hay dónde;
- sin el abridor del sistema en el `PATH` (`explorer`, `open` o `xdg-open`; en WSL, `explorer.exe` y `wslpath`), o si falla o no responde en 15 s;
- en Windows y WSL, con una coma en la ruta, porque `explorer` separa las rutas en las comas y podría abrir otra cosa;
- con un número que no está en la lista: el mensaje dice cuántos tiene.

En Windows y WSL, el código de salida de `explorer` no cuenta, porque suele ser 1 aunque abra: ahí, «abierto» quiere decir que se lanzó.

## Scripts

| Script | Para qué | Salidas |
|---|---|---|
| `ticket.py --enlaces <id \| ruta a un .md> [--copiar \| --abrir <n>]` | lista los enlaces del `CLAUDE.md` del ticket, o de cualquier `.md`, con su ruta absoluta y si es archivo o carpeta; los que existen van numerados, y los rotos y los de esquema, aparte. `--copiar` manda además las rutas al portapapeles. `--abrir <n>` abre el enlace `<n>` que eligió el usuario; sin él, solo lee | 0 `enlaces de <documento>: <n>` y la lista, aunque haya rotos (sin portapapeles avisa por stderr y la lista sale igual); con `--abrir`, una línea más que dice qué se abrió y cómo · 1 id sin carpeta, con varias o sin `CLAUDE.md`, una ruta que no es un `.md`, `--raiz` con una ruta, un número que no está en la lista, o `no se abrió <ruta>: <motivo>` · 2 error de uso (`--abrir` sin un entero, o junto a `--copiar`), o con un id, sin instancia o config rota |
