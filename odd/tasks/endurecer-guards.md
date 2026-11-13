# Endurecer los guards antes de Pi

Objetivo: cerrar cuatro formas conocidas de esquivar los guards (X2, X9, X10 y X11 de `odd/tasks/multi-host.md`) antes de sumar Pi como host, porque Pi va a heredar los mismos guards. Rama: `feat/endurecer-guards`, desde `main` (`f012ca0`). Entrega: un commit por unidad en la rama; push y avance de `main` solo con autorización. Runner: Python sin pytest, `python <x>.tests.py`. Espejo en Engram: `odd/endurecer-guards/tasks`.

## Specs

- **S1. El pedido (L1).** «Hagamos una tanda de guards». El alcance son los cuatro seguimientos que se le propusieron al usuario: X2, X9, X10 y X11. X12 (pwsh sobre POSIX) queda fuera de dominio.
- **S2. X2: el escape de PowerShell en `guard_comandos`.** En el dialecto PowerShell, ``g`it push --force origin main`` pasa, porque el backtick es un carácter de escape (``g`it`` es `git`). Tiene que bloquearse igual que `git push --force origin main`, en Claude Code y en Codex.
- **S3. X9: `.\.` en Bash, en Windows.** Con Git Bash, `rm -rf <scratch>/.\./.\./fuera/x` pasa la capa 1, porque Bash lee `\.` como `.` y el guard lee `\` como separador. En POSIX ya falla cerrado desde M3 (L42 de `multi-host.md`). Tiene que fallar cerrado también en Windows. Ahora se permite cambiar la salida en Windows, pero solo en este caso: el resto tiene que dar idéntico.
- **S4. X10: los escapes del scratch de `writer_guard`.** `echo x > <scratch>/.\./.\./<repo>/x`, `echo x > <scratch>/<enlace a un repo>/../x` y `[IO.File]::WriteAllText((Join-Path '<scratch>' '../../<repo>/x'), 'x')` tienen que bloquear como cualquier escritura sobre el repo.
- **S5. X11: el `..` como texto en `rutas.ubicar`.** En POSIX, `rutas.ubicar` colapsa `..` antes de `canonica`, así que la capa 2 y `writer_guard` no ven un `<enlace>/..` (`git -C /tmp/l/.. push`, con `l` apuntando dentro de un repo protegido). En POSIX, el `..` lo tiene que resolver `realpath`, después de los enlaces, como el kernel. En Windows, el `..` textual es la semántica real de Win32 y no cambia.
- **S6. Sin regresión.** Cada cambio lleva un diferencial contra `f012ca0` sobre el juego de casos de los guards. Solo pueden cambiar los casos que S2 a S5 nombran, y toda diferencia que nadie pidió es blocker.
- **S7. El modelo de amenaza (Y6, L9).** Los guards cubren los errores y los atajos del agente, no a un agente que los esquiva a propósito. `Doc/diseno.md` lo deja escrito, con la lista de formas conocidas que quedan fuera de alcance: `gi''t`, `g\it`, `--fo"rce"`, un comando en una variable de PowerShell (`$g='git'; & $g push --force`), `Start-Process git -ArgumentList`, un decodificador (`echo … | base64 -d | xargs git`), `-EncodedCommand`, un texto que llega a un shell por una tubería (`'…' | iex`), las comillas escapadas que esconden el comando (B3) y las sustituciones entre comillas dobles.
- **S8. La capa 1 lee dentro de un shell.** El texto entre comillas que recibe un shell en el mismo segmento (`bash -c`, `sh -c`, `eval`, `cmd /c`, `powershell -Command`, `pwsh -c`, `iex`, `Invoke-Expression`, `wsl`), y el here-string que recibe `iex`, pasa por las mismas reglas de la capa 1, hasta dos niveles. Bloquean `bash -c 'git push --force origin main'`, `powershell -Command "git push --force"`, `iex 'git push --force'`, `Invoke-Expression "git push --force"` y `bash -c 'rm -rf <fuera del scratch>'`. Sigue pasando `bash -c 'rm -rf <scratch>/x'`.
- **S9. La capa 1 reconoce git llamado por una ruta entre comillas.** `& "C:\Program Files\Git\cmd\git.exe" push --force`, `"/c/Program Files/Git/cmd/git.exe" push --force` y `& 'git' push --force` bloquean como `git push --force`, y lo mismo pasa con `reset --hard` y `clean -f`.
- **S10. Sin regresión de la segunda tanda.** Diferencial contra `3d01497`: solo pueden cambiar los casos de S8 y S9. El texto entre comillas que no recibe un shell sigue siendo dato: `git commit -m "no uses git push --force"` y `echo "git push --force"` siguen pasando.

## Tasks

| ID | Specs | Qué | Ruta | Estado |
|---|---|---|---|---|
| U1 | S2, S3, S6 | `guard_comandos`: el backtick de PowerShell (X2) y `.\.` en Bash en Windows (X9) | delegado: writer en paralelo con U2 (Writer trigger a, superficies disjuntas), con el respaldo de contexto | hecho (L4) |
| U2 | S4, S5, S6 | `rutas.ubicar` resuelve `..` con `realpath` en POSIX (X11), y los escapes del scratch de `writer_guard` (X10) | delegado: writer en paralelo con U1 | hecho (L2, L3) |
| V | S1-S6 | Un verificador independiente sobre las dos unidades, con las sondas de punta a punta de la capa 2 en POSIX (`git -C <enlace>/.. push`) | delegado (ítem 2) | hecho: B1 y B2 corregidos y cerrados en el rechequeo (L5-L7) |
| Y1 | — | Seguimiento: formas del modo físico que el parser no ve (`set -eo physical`, `set -euo pipefail -P`, `bash -P -c`, `bash -o physical -c`) | inline, aparte | pendiente |
| Y2 | — | Seguimiento: `CDPATH` no se modela (`CDPATH=<x> cd <nombre>`). Previo | inline, aparte | pendiente |
| Y3 | — | Seguimiento: la capa 2 no sigue cadenas de `cd` (`cd <repo>/out && cd .. && git commit`). Previo | inline, aparte | pendiente |
| Y4 | — | Seguimiento: `\\` sin comillas en las lecturas de Bash cuenta como dos `\` (bloquea de más `\\srv\…`) | inline, aparte | pendiente |
| Y5 | — | Seguimiento: `test_u6g_muchos_heredocs_en_una_linea_cuestan_lineal` es inestable con la máquina cargada (tope de 2 s, tardó 2.6 s). Previo | inline, aparte | pendiente |
| Y7 | — | Seguimiento: el emulador de POSIX de los tests no es fiel en la capa 2 con enlaces (dio `None` donde el real da `ask`, L8) | inline, aparte | pendiente |
| Y6 | — | A decidir con el usuario, el modelo de amenaza. Las ofuscaciones previas sin cubrir: `& 'git'`, `gi''t`, `g\it`, `--fo"rce"`, `iex`, `bash -c`, `$g`, `Start-Process`, las comillas escapadas que esconden el comando (B3), las sustituciones entre comillas dobles y la capa 2 a través de los escapes | decisión | decidido (L9): pasa a S7-S10 |
| W1 | S7-S10 | La capa 1 lee dentro de un shell (S8) y reconoce git por una ruta entre comillas (S9), y `Doc/diseno.md` escribe el modelo de amenaza (S7) | inline: un cambio entendido en un archivo de código, sin razón de writer | en curso |
| V2 | S7-S10 | Un verificador independiente sobre W1 | delegado (ítem 2: un guard) | pendiente |

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
  - **Commit:** U1 quedó en `338be1b`.
- **L5 (2026-11-12), el verificador independiente: S1 y S3 cumplen, S2, S4 y S5 parciales, S6 no cumple.**
  - **B1 (nuevo, blocker):** el `cd` de Bash es lógico, porque quita el `..` como texto antes de seguir enlaces, pero U2 lo dejó físico. En POSIX, `cd <enlace>/.. && echo x > repo/f` pasa en `writer_guard`, y `cd <repo>/<enlace>/.. && git push --force-with-lease` deja de preguntar en la capa 2. En macOS aparece sin preparar nada, por `/tmp`. Un test fijaba el error (`cd afuera/.. && echo x > db/x`).
  - **B2 (previo, de la clase de S4, blocker por el brief):** `cd` con `.\.` hacia una carpeta que no es zona, seguido de una escritura relativa con `..`, pasa. `_cd` solo toma una lectura alternativa si cae en una zona.
  - **B3 (previo):** las comillas escapadas (`` `' `` o `\'`) alrededor de un `git push --force` lo esconden de la capa 1. Lo bajó a advisory el padre: es la clase del recorte de comillas, no la del escape, y la forma sin backtick también pasa. Va a la decisión del modelo de amenaza.
  - **Advisories previos:**
    - una sustitución entre comillas dobles (`"$(git push --force …)"`);
    - los avisos de U1;
    - las rutas relativas a una unidad y las variables en `Combine` y `Join-Path`;
    - `Set-Content -Path (Join-Path …)`;
    - `` `u{66} `` en pwsh 7, sin verificar.
  - **El diferencial propio:**
    - Windows: 260 cambios, todos más estrictos y todos de S3 o S4.
    - POSIX: 1154 más estrictos; las 506 más laxas son la semántica del kernel, salvo 114 con `cd`/`pushd`, que son B1.
  - **Suites:** 42 de 42 en verde.
  - **La corrección:** una tanda para B1 y B2, con sus sondas como tests, devuelta al writer de U2, que ahora toma también `guard_comandos`. Después, un rechequeo limitado a B1 y B2.
- **L6 (2026-11-12), la corrección de B1 y B2.**
  - **B1:**
    - `rutas.ubicar` y `resolver` reciben `logica=False`;
    - `_cd` de `writer_guard` es lógico, salvo con `-P` o después de `set -P` o `set -o physical`;
    - en la capa 2, las menciones preguntan con la lectura física o con la lógica, y `git -C` sigue físico;
    - los tres casos de test que fijaban el error quedaron corregidos.
  - **B2:** el cwd ambiguo, con las carpetas posibles, protege si alguna protege. Falla cerrada con el tope de lecturas o con más de 64 carpetas.
  - **Decisión del padre:** la primera reproducción de B2 en Windows no llega al repo, porque contando los niveles cae en `C:/Users/Proyecto`. Se fijó la variante con 4 `..`, que sí llega. Se eligen las carpetas posibles y no la falla cerrada simple: 8 filas de Windows bloquean de más, contra 148.
  - **Pruebas:**
    - 15 mutantes muertos;
    - en el corpus del verificador, las filas de B1 dan igual que `f012ca0`, y en Windows cambian solo 8 filas de B2, todas a bloquear;
    - `rutas` 15/15, `guard_comandos` 62/62 y `writer_guard` 120/120.
  - **Seguimientos:**
    - `\\` sin comillas en las lecturas de Bash cuenta como dos `\`, y bloquea de más `\\srv\…`;
    - `test_u6g_muchos_heredocs_en_una_linea_cuestan_lineal` tiene un tope de 2 s, y con la máquina cargada tardó 2.6 s (inestable, previo).
  - **`Doc/diseno.md`:** el padre sumó el `cd` lógico, `set -P`, el cwd ambiguo y la doble lectura de la capa 2.
- **L7 (2026-11-12), el rechequeo, limitado a B1 y B2: cerrados.**
  - **B1:** todas las sondas, en Linux y darwin, en `writer_guard` y en la capa 2, dan lo mismo que la base. Las 123 filas de B1 vuelven a dar igual que `f012ca0`. Ninguna fila con `cd` se afloja frente a la base, y las 371 más laxas son la clase del kernel, ya aceptada.
  - **B2:** bloquea la variante con 4 `..` y las demás reproducciones. Los casos legítimos del scratch siguen pasando.
  - **Lo que confirmó:** el verificador da por buena la cuenta del writer. La primera reproducción de Windows cae en `C:/Users/Proyecto`, fuera del repo.
  - **Suites:** `rutas` 15/15, `writer_guard` 120/120 y `guard_comandos` 62/62.
  - **Avisos previos:** pasan a Y1, Y2 y Y3. B3 y las ofuscaciones, a Y6.
- **L8 (2026-11-12), el CI de la rama.**
  - **El rojo:** el push de `be6ea69` dio Windows en verde, pero en Ubuntu y macOS falló `test_en_posix_un_enlace_real_seguido_de_dos_puntos_en_la_capa_2`, que en Windows se saltea.
  - **El diagnóstico:** con `34383d5`, el test informa su resultado. En POSIX real, `git -C <repo>/afuera/.. push`, con `afuera` apuntando afuera, da `ask`, porque el texto de `-C` también cuenta como mención y su lectura lógica cae en el repo.
  - **La decisión del padre:** se acepta `ask`. Coincide con la base `f012ca0` y es el lado conservador, ya que git no entraría al repo. Se corrigen la expectativa del test y la frase de `Doc/diseno.md`.
  - **Y7 (seguimiento):** el emulador de POSIX daba `None` para este caso y el POSIX real da `ask`, así que no es fiel ahí. Antes de confiar en una sonda emulada de la capa 2 con enlaces, hay que contrastarla con un enlace real en el CI.
- **L9 (2026-11-13), el modelo de amenaza (Y6).**
  - **La sonda:** de 20 variantes de `git push --force` contra `3d01497`, sin repos protegidos, pasan sin bloqueo `bash -c '…'`, `sh -c "…"`, `eval '…'`, `powershell -Command "…"`, `iex '…'`, `Invoke-Expression "…"`, `& 'git' …`, `& "C:\Program Files\Git\cmd\git.exe" …` y `"/c/Program Files/Git/cmd/git.exe" …`, además de las ofuscaciones de S7. La capa 2 ya lee dentro de `bash -c`, `eval` e `iex`, pero la capa 1 no.
  - **La propuesta:** se recomendó documentar que los guards cubren errores y atajos, no un agente que los esquiva, y cerrar en la capa 1 las formas que un agente escribe sin querer esquivar nada (un shell que recibe el comando, git por una ruta entre comillas). Se descartó preguntar ante cualquier comando entre comillas, porque `& "C:\Program Files\…\gh.exe"` es lo común en Windows.
  - **La respuesta del usuario, textual:** «Si me parece bien».
