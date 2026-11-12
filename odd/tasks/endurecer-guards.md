# Endurecer los guards antes de Pi

Objetivo: cerrar cuatro formas conocidas de esquivar los guards (X2, X9, X10 y X11 de `odd/tasks/multi-host.md`) antes de sumar Pi como host, porque Pi va a heredar los mismos guards. Rama: `feat/endurecer-guards`, desde `main` (`f012ca0`). Entrega: un commit por unidad en la rama; push y avance de `main` solo con autorización. Runner: Python sin pytest, `python <x>.tests.py`. Espejo en Engram: `odd/endurecer-guards/tasks`.

## Specs

- **S1. El pedido (L1).** «Hagamos una tanda de guards». El alcance son los cuatro seguimientos que se le propusieron al usuario: X2, X9, X10 y X11. X12 (pwsh sobre POSIX) queda fuera de dominio.
- **S2. X2: el escape de PowerShell en `guard_comandos`.** En el dialecto PowerShell, ``g`it push --force origin main`` pasa, porque el backtick es un carácter de escape (``g`it`` es `git`). Tiene que bloquearse igual que `git push --force origin main`, en Claude Code y en Codex.
- **S3. X9: `.\.` en Bash, en Windows.** Con Git Bash, `rm -rf <scratch>/.\./.\./fuera/x` pasa la capa 1, porque Bash lee `\.` como `.` y el guard lee `\` como separador. En POSIX ya falla cerrado desde M3 (L42 de `multi-host.md`). Tiene que fallar cerrado también en Windows. Ahora se permite cambiar la salida en Windows, pero solo en este caso: el resto tiene que dar idéntico.
- **S4. X10: los escapes del scratch de `writer_guard`.** `echo x > <scratch>/.\./.\./<repo>/x`, `echo x > <scratch>/<enlace a un repo>/../x` y `[IO.File]::WriteAllText((Join-Path '<scratch>' '../../<repo>/x'), 'x')` tienen que bloquear como cualquier escritura sobre el repo.
- **S5. X11: el `..` como texto en `rutas.ubicar`.** En POSIX, `rutas.ubicar` colapsa `..` antes de `canonica`, así que la capa 2 y `writer_guard` no ven un `<enlace>/..` (`git -C /tmp/l/.. push`, con `l` apuntando dentro de un repo protegido). En POSIX, el `..` lo tiene que resolver `realpath`, después de los enlaces, como el kernel. En Windows, el `..` textual es la semántica real de Win32 y no cambia.
- **S6. Sin regresión.** Cada cambio lleva un diferencial contra `f012ca0` sobre el juego de casos de los guards. Solo pueden cambiar los casos que S2 a S5 nombran, y toda diferencia que nadie pidió es blocker.

## Tasks

| ID | Specs | Qué | Ruta | Estado |
|---|---|---|---|---|
| U1 | S2, S3, S6 | `guard_comandos`: el backtick de PowerShell (X2) y `.\.` en Bash en Windows (X9) | delegado: writer en paralelo con U2 (Writer trigger a, superficies disjuntas), con el respaldo de contexto | hecho (L4) |
| U2 | S4, S5, S6 | `rutas.ubicar` resuelve `..` con `realpath` en POSIX (X11), y los escapes del scratch de `writer_guard` (X10) | delegado: writer en paralelo con U1 | hecho (L2, L3) |
| V | S1-S6 | Un verificador independiente sobre las dos unidades, con las sondas de punta a punta de la capa 2 en POSIX (`git -C <enlace>/.. push`) | delegado (ítem 2) | pendiente |

## Log

- **L1 (2026-11-12), el pedido.** Textual: «Hagamos una tanda de guards». Respondía a la propuesta de cerrar X2, X9, X10 y X11 antes de Pi, porque Pi hereda los guards. Todos son previos a M3 y piden que el agente los arme a propósito.
- **La entrega:** dos commits de unidad y el verificador al final. La revisión nativa de gentle-ai está apagada.
- **L2 (2026-11-12), U2 de vuelta y decisiones del padre.**
  - **U2:**
    - **S5:** en POSIX, `ubicar` deja los `..` para `canonica`.
    - **S4:** las lecturas de Bash, con `\` como separador, como escape y las combinaciones, con un tope de 6 y falla cerrada al pasarlo. Join-Path con `..` se decide con la ruta unida.
    - **Pruebas:** 15 mutantes muertos. El diferencial contra `f012ca0` con un oráculo da 0 diferencias sin explicar; las que pasan a dejar pasar son solo `<repo>/<enlace hacia afuera>/..`, que es la semántica del kernel.
    - **Suites:** `rutas` 14/14, `writer_guard` 116/116, `comun` 62/62, `config_loader` 83/83 y `guard_comandos` 58/58.
  - **La costura:** con el cambio de `ubicar`, `guard_comandos.Protegidos._canonica` pega como texto el resto inexistente. En POSIX, `git -C /tmp/noexiste/../repo push` pasa de `ask` a `None`. El parche (`..` es `dirname`, `.` se salta) va a U1, que es el dueño, junto con los tests de punta a punta de la capa 2 en POSIX.
  - **Decisión del padre, el alcance de las lecturas:** se aplican a toda pieza de Bash, no solo al scratch, porque `.\.` llegaba a un repo desde cualquier carpeta. Fallan cerrado; el costo es bloquear de más rutas de Windows citadas en Bash, del tipo `'<repo>\..\x'`.
  - **Se suma a U2, por ser la misma clase que X10:** `[IO.Path]::Combine('<scratch>', '<ruta absoluta del repo>')` pasaba, porque bastaba que un literal fuera scratch. La exención se decide con el resultado de la combinación.
- **L3 (2026-11-12), el delta de U2: `Combine`.**
  - **El arreglo:** `CLR_COMBINAR` reconoce `[IO.Path]::Combine` y `[System.IO.Path]::Combine`. Un hijo con raíz reemplaza lo anterior, como en .NET, y la exención se decide con el resultado.
  - **`Join-Path` no aplica:** verificado en PowerShell 5.1, concatena (`C:\a\C:\b\x`) en vez de reemplazar.
  - **Pruebas:**
    - 10 casos RED pasaban y ahora bloquean;
    - 4 mutantes muertos;
    - el diferencial suma filas de `Combine`, y las 62 208 filas anteriores en Windows y las 52 306 en POSIX no cambian, con 0 sin explicar;
    - `writer_guard` 117/117 y `rutas` 14/14.
  - **Un borde en la dirección segura:** `_con_raiz` no ve las comillas, así que puede bloquear de más, nunca de menos.
  - **Commit:** U2 quedó en `4cee24f`.
- **L4 (2026-11-12), U1 de vuelta.**
  - **S2 (X2):** una segunda pasada de la capa 1 sobre el texto sin los escapes de PowerShell. Solo suma bloqueos, y respeta las comillas simples, las curvas, los here-strings y los escapes especiales. Medido en `powershell.exe` 5.1.
  - **S3 (X9):** en Bash, una pieza con `\` fuera de comillas no cuenta como scratch, en cualquier sistema. Entre comillas dobles, en Windows, sigue separando, porque Bash la deja literal y MSYS la lee como separador. Medido en el `bash.exe` de Git for Windows.
    - Se descartó (b), fallar ante toda `\`, porque bloquearía `rm -rf "C:\…\Temp\claude\x"`: 1944 filas legítimas.
  - **La costura con U2:** el parche léxico de U2 lo tumbó el oráculo, porque un `..` léxico sobre una cola inexistente diverge de `realpath` si después viene un enlace. Tampoco servía el caché de prefijos. El arreglo: en POSIX, toda ruta con `..` va directo a `config_loader.canonica`, sin caché.
  - **Pruebas:**
    - 9 sondas de punta a punta de la capa 2 en POSIX emulado, más una con un enlace real que en Windows se saltea;
    - 17 de 18 mutantes muertos; el vivo era equivalente y se quitó el chequeo redundante;
    - el diferencial da 139 701 filas, 6052 distintas y 0 inesperadas: 5164 de S2 y 888 de S3. La capa 2 en POSIX da 0 diferencias contra el oráculo;
    - `guard_comandos` 60/60, `comun` 62/62, `codex` 41/41 y `claude_code` 37/37. El padre repitió `rutas`, `writer_guard` y `guard_comandos`: 14/14, 117/117 y 60/60.
  - **Ofuscaciones previas que siguen sin cubrir, avisos de U1:**
    - `& 'git' push --force`;
    - en Bash, `"git" push --force`, `gi''t push --force` y `g\it push --force`;
    - ``git push --fo"rce"``;
    - `iex '…'`, `Invoke-Expression` y `bash -c "…"` en la capa 1;
    - `$g='git'; & $g`;
    - `Start-Process git`;
    - la capa 2 a través de los escapes.
  - **Un falso permitido previo:** `Remove-Item … /c/Users/<u>/…/claude/x` en PowerShell resuelve a `C:\c\Users\…`. Todo esto queda para decidir el modelo de amenaza con el usuario.
