# Escribir un archivo de capa por la shell

Objetivo: que las reglas de la capa corran aunque un agente que no es writer escriba un archivo de capa por la shell, en Claude Code, Codex y Pi. Son dos capas, como en el writer: un bloqueo antes del comando (parte A, R1 del roadmap) y una revisión al final del turno (parte B, R1b). Rama: `fix/capa-por-shell`, desde `origin/main` (`4761041`). Entrega: un commit por unidad; push de la rama con destino explícito; `main` y etiquetas solo con autorización. Runner: Python sin pytest, `python <x>.tests.py`. Espejo en Engram: `odd/capa-por-shell/tasks`.

## Specs

- **S0, el problema (X17 parte 2).** Textual: «X17, parte 2: escribir un archivo de capa por shell, fuera de un writer, se saltea el chequeo en cualquier CLI.»
- **S1, bloquear antes (parte A).** Fuera de un writer, un comando de shell que escribe contenido en un archivo de capa se bloquea antes de correr. El mensaje pide la herramienta de edición del host, así el agente sigue viendo las no-negociables en el primer toque. En A1 se decide qué cuenta como escritura y si Claude Code bloquea o pregunta.
- **S2, revisar al final del turno (parte B).** Al final de cada turno del agente principal, los archivos de capa que cambiaron durante el turno pasan por las reglas de su capa, sin importar cómo se escribieron. Un hallazgo de bloqueo hace seguir al agente. El diseño se decide en B1, con la investigación de B0.
- **S3, los tres CLI.** Claude Code, Codex y Pi. Lo que un host no pueda expresar se declara en el manifiesto de capacidades y nunca se vuelve un OK falso.
- **S4, el rigor.** Textual: «bien analicemos todo, en conjunto como vamos hacer cada paso para que lleguemos a la mejor solucion de manera rigurosa». En la práctica:
  - cada decisión de diseño se toma con evidencia medida y queda en el Log;
  - los tests van en rojo antes del código;
  - se corre un diferencial contra la base;
  - cada parte lleva un verificador independiente, porque las dos tocan guards o compuertas (ítem 2);
  - se hace una prueba de humo en cada CLI.
- **Riesgo:** ítem 2 (un guard y una compuerta nueva) e ítem 3 (cambia lo que un agente puede hacer por la shell).

## Tasks

| ID | Specs | Qué | Ruta | Estado |
|---|---|---|---|---|
| A0 | S1, S4 | Línea base, en dos partes:<br>• qué devuelve `writer_guard.destinos` para cada forma de escritura, en bash y PowerShell, con rutas relativas y absolutas, sobre archivos de capa y de no capa;<br>• la latencia actual de `guard_comandos` por comando | inline | hecho (L6) |
| A1 | S1 | Las decisiones, con la evidencia de A0:<br>• D1, dónde vive: `guard_comandos` llamando a `destinos`, o `writer_guard` abierto al principal con una zona de solo capas;<br>• D2, qué cuenta como escritura: el contenido sí, los borrados no, y `cp` o `mv` hacia una ruta de capa sí;<br>• D3, si Claude Code bloquea o pregunta (Codex y Pi solo bloquean);<br>• D4, a qué agentes aplica: a todos los que no son writer | inline; D3 la decide el usuario | hecho: D1, D2 y D4 con evidencia (L7); D3, bloquear (L8) |
| A2 | S1 | Tests en rojo:<br>• fuera de un writer se bloquea cada forma de D2, en los dos dialectos;<br>• pasan un archivo del repo que no es de capa, el scratch, las lecturas y los borrados;<br>• un writer sigue frenado por `writer_guard` | inline | hecho (L9) |
| A3 | S1, S3 | El cambio en verde, con los docs: `Doc/diseno.md` (el guard y su «No ve»), `Doc/hooks.md`, la fila X17 de `multi-host.md` y las notas de la próxima versión | inline | hecho (L10); las notas, con la entrega |
| A4 | S4 | Diferencial: el guard viejo contra el nuevo sobre el corpus de comandos de los tests. Solo se admiten diferencias en escrituras de capa fuera de un writer, y la latencia se compara con la de A0 | inline | hecho (L11): 0 regresiones; +30 ms por comando |
| A5 | S1, S4 | Verificador independiente (ítem 2), con sondas en un scratch aparte | delegado | hecho: B1 y B2 corregidos en `634ce47` y cerrados en la revisión (L12-L14) |
| B0 | S2, S3 | Investigación por host, con la doc y la versión instalada:<br>• Claude Code: `Stop` y `UserPromptSubmit`;<br>• Codex: `Stop` (L4);<br>• Pi: `agent_before_settle` en el padre, y si hay un evento de inicio de turno.<br>Salen las filas P11 (fin de turno del principal) y P12 (inicio de turno) en la tabla de capacidades de `multi-host.md`; P6 a P10 ya están ocupadas | delegado: un investigador, porque pasa del presupuesto | hecho (L15) |
| B1 | S2 | Diseño:<br>• la foto al inicio del turno: qué se guarda y cuánto cuesta en un repo grande;<br>• cómo no culpar al agente de lo que cambió el usuario;<br>• qué hallazgos hacen seguir al agente;<br>• cómo no repetir lo que ya chequeó la edición;<br>• el tope de vueltas;<br>• la degradación en un host sin el evento | inline, con el usuario | hecho (L16) |
| B2a | S2, S3 | El modelo neutral: `InicioTurno` y `FinTurno` en `eventos.py`, los puntos de evento y P11/P12 en `capacidades.py` (en los tres manifiestos, «no disponible» hasta B2c-B2e), con sus tests | delegado: writer W1, junto con B2b, por el respaldo de contexto de una sesión larga (L17) | hecho (L18) |
| B2b | S2 | El script `revisar_turno.py`: la foto al inicio, la revisión al final contra la foto o HEAD, una vuelta por turno, la foto pendiente si el turno se corta. Con sus tests | delegado: W1 | hecho (L18) |
| B2c | S2, S3 | Claude Code: `Stop` y `UserPromptSubmit` en el adaptador y en `hooks.json`, con sus tests | delegado: writer W2, después de W1, junto con B2d a B2f; los tests de paridad atan los tres hosts y no se pueden partir (L17) | hecho (L19) |
| B2d | S2, S3 | Codex: `Stop` y `UserPromptSubmit` (solo el hilo raíz) en el adaptador y en `hooks.codex.json`, con sus tests | delegado: W2 | hecho (L19) |
| B2e | S2, S3 | Pi: el settle del padre y `before_agent_start` en el shim, el adaptador y `hooks.pi.json`, y la regla del doctor sobre el settle; con sus tests de Python y TS | delegado: W2 | hecho (L19) |
| B2f | S3 | El doctor (cobertura y degradado) y los docs: `Doc/hooks.md`, `Doc/diseno.md` y las filas P11 y P12 de `multi-host.md`. La costura la cierra el padre, con la suite completa una vez | delegado: W2; la costura, inline | hecho (L19); la costura, en el pre-commit |
| VB | S2, S3, S4 | Verificador independiente de la parte B, con todo el documento | delegado | pendiente |
| H | S3, S4 | Prueba de humo en Claude Code, Codex y Pi, cada uno con su home aparte | inline; el usuario hace los logins | pendiente |
| F1 | — | Seguimiento: los hooks ponen `dont_write_bytecode` y un plugin instalado compila sus módulos en cada corrida. Con caché, `guard_comandos` ahorra unos 60 ms (L11) | aparte | anotado |

## Log

- **L1 (2026-11-16), el pedido.** De la lista ordenada del usuario, textual: «3. X17, parte 2: escribir un archivo de capa por shell, fuera de un writer, se saltea el chequeo en cualquier CLI.»
- **L2 (2026-11-16), el mapa.** Lo hizo un explorador de solo lectura; el padre comprobó `verificar_capa.py:273`.
  - **El chequeo de capa** corre solo con la herramienta de edición (`_edicion_verificable`); `_pre_tool_use` y `_post_tool_use` dejan pasar lo demás.
  - **`writer_guard`** bloquea las escrituras por shell solo dentro de un writer, y su zona es más ancha que la capa: todo archivo de un repo declarado.
    - `destinos()` devuelve los destinos sin decidir. No expande variables y solo une rutas relativas si recibe un `cwd`.
    - `config_loader.clasificar` es el filtro que deja solo los archivos de capa.
  - **`guard_comandos`** corre antes de cada comando, en todos los agentes, pero no detecta escrituras.
  - **No hay hook** después de un comando de shell ni compuerta de fin de turno para el principal. Los tres adaptadores ya pueden devolver Bloquear y Contexto en `post`.
- **L3 (2026-11-16), las opciones y la decisión.**
  - **Las tres opciones:** bloquear antes (1), chequear después (2) o revisar al final del turno (3).
  - **La pregunta del usuario,** textual: «Pero esto esto es la mejor solucion?}».
  - **El análisis:** la 1 es un parser, así que no ve scripts ni variables. La 3 es la única completa, porque mira el resultado y no el comando.
  - **La decisión:** el patrón del writer, con dos capas. La 1 va ahora y la 3 queda como R1b. Textual: «Si me parece, bien analicemos todo, en conjunto como vamos hacer cada paso para que lleguemos a la mejor solucion de manera rigurosa».
- **L4 (2026-11-16), Codex tiene `Stop`.**
  - La doc de hooks de Codex (https://learn.chatgpt.com/docs/hooks) lista `Stop`, con `turn_id`, `stop_hook_active` y `last_assistant_message`.
  - En `Stop`, `decision: "block"` no corta el turno: hace seguir al agente con `reason` como prompt nuevo.
  - La misma doc también lista `PostToolUse` para `Bash`.
  - Falta probarlo en la versión instalada (B0).
- **L5 (2026-11-16), el plan aprobado.** A la pregunta «¿Le cambiarías algo al plan antes de arrancar A0?», textual: «Vale tomare tu recomendacion».
- **L6 (2026-11-16), A0: la línea base.**
  - **El montaje:** una instancia en el scratch con un repo `app` y la capa `sql`, y 70 comandos. Son 17 formas en bash y 16 en PowerShell, cada una con ruta relativa (con `cwd` en el repo) y absoluta, más un archivo que no es de capa, el scratch y un `cd` previo.
  - **Lo que `destinos()` + `clasificar` reconoce como capa:** todas las formas literales de los dos dialectos:
    - redirecciones, `tee`, `dd of=` y los heredocs de `cat` y de Python;
    - `cp`, `copy` y `Copy-Item`, y `mv` y `Move-Item`;
    - `sed -i`, `perl -pi` y `python -c`;
    - `Set-Content`, `Add-Content`, `Out-File`, `New-Item`, un `[IO.File]` literal y un here-string;
    - lo que corre dentro de `bash -c` y `cmd /c`, y la ruta relativa después de un `cd`.
  - **Lo que no ve:** rutas en una variable (`$F`, `$f`), un `[IO.File]` con `"$PWD\…"`, `git checkout -- <archivo>` y un script (`python3 gen.py`). Un `README.md` y el scratch no son capa.
  - **No distingue la operación:** `rm` y `Remove-Item` devuelven la ruta igual que una escritura, y `mv` y `Move-Item` devuelven el origen y el destino.
  - **La latencia** por comando, en Windows (p50 de 21 corridas):

    | Medición | p50 |
    |---|---|
    | Python vacío | 56 ms |
    | `guard_comandos`, con cualquier agente | 210 ms |
    | `writer_guard` en el principal (el prefiltro `writer-` corta antes) | 79 ms |
    | `writer_guard` en un writer | 196 ms |
    | `destinos()` en proceso | 0,12 ms de mediana, 0,57 ms de máximo |
    | Importar `writer_guard` | 7 ms |

    `guard_comandos` ya carga la config de la instancia (`config_loader.cargar`).
  - **Una trampa del montaje:** en Windows, el scratch de los guards es `%TEMP%\claude`. Una instancia de prueba dentro de esa carpeta cuenta entera como scratch, y `writer_guard` no bloquea nada. La medición del writer se repitió con `TEMP` en otra carpeta, y ahí sí bloquea (exit 2).
- **L7 (2026-11-16), A1: las decisiones, con la evidencia de L6.**
  - **D1, dónde vive:** en `guard_comandos`, que llama al parser de `writer_guard` y a `clasificar`. Cuesta unos 7 ms sobre 210. Abrir `writer_guard` al principal le quita el prefiltro y lleva cada comando de 79 a unos 196 ms. Se vuelve a medir en A4.
  - **D2, qué cuenta como escritura:** lo que deja contenido nuevo en un archivo de capa, es decir, escribir, copiar y el destino de un movimiento.
    - No cuentan borrar (`rm`, `Remove-Item`, `unlink`…), vaciar (`truncate`, `Clear-Content`), `touch` ni el origen de un movimiento. Ninguno agrega líneas. Además, Claude Code no tiene herramienta para borrar, así que bloquearlos dejaría al agente sin forma de hacerlo. Codex sí puede borrar, con `*** Delete File` de `apply_patch`.
    - Hace falta que el parser diga la operación: una función nueva al lado de `destinos()`, que no cambia.
    - Un caso para A2: `Rename-Item` resuelve el nombre nuevo contra la carpeta del archivo, no contra el `cwd`.
  - **D4, a quién aplica:** a todo agente que no es writer. En un writer manda `writer_guard`, con una zona más ancha, y `guard_comandos` no repite.
  - **D3, bloquear o preguntar en Claude Code:** pendiente del usuario. La recomendación es bloquear: preguntar dejaría aprobar una escritura que se salta las reglas, justo lo que se quiere evitar, y Codex y Pi ya solo bloquean.
  - **Al «No ve»:** las variables, las rutas compuestas, los scripts y las escrituras con git (`git checkout -- <archivo>`, `git apply`). Las atrapa R1b.
- **L8 (2026-11-16), D3: bloquear.** Las razones:
  - preguntar deja aprobar con un clic la escritura que se salta las reglas;
  - el mensaje manda a Edit o Write, así que el agente no queda trabado;
  - Codex y Pi solo bloquean, y con esto los tres CLI se portan igual.

  El costo: un cambio masivo, como un `sed` sobre 50 archivos, se hace archivo por archivo con Edit. El usuario tomó la recomendación, textual: «tomare tu recomendacion».
- **L9 (2026-11-16), A2: el rojo.**
  - **`guard_comandos.tests.py`** suma 7 tests `test_capa_*`, sobre una instancia con un repo `app`, la capa `sql` y el taller `taller/*.sql`.
    - Fallan los 5 que bloquean. Cubren 20 formas en los dos dialectos (2 más en Windows), la raíz de la instancia como `cwd`, otro subagente (`Explore`), el taller, el mensaje, Codex y Pi.
    - Pasan los 2 que fijan lo que debe seguir pasando: un archivo del repo que no es de capa, el scratch, una ruta fuera de todo, las lecturas, los borrados, vaciar, `touch`, el `mv` de un archivo de capa al scratch y `git mv`; y la config rota.
  - **`writer_guard.tests.py`** suma `test_escrituras_deja_solo_lo_que_recibe_contenido_nuevo`. Da error porque `escrituras` no existe.
  - Resultado: 72/77 y 120/121.
- **L10 (2026-11-16), A3: el verde y los docs.**
  - **`writer_guard`:**
    - `_recoger` anota, además, la operación de cada destino, y `escrituras()` devuelve solo los que reciben contenido.
    - La operación sale del comando: los `SIN_CONTENIDO`, el origen de los `MUEVEN`, el Python que solo borra (`PY_SIN_CONTENIDO`) y `[IO.File]::Delete`.
    - El destino de un movimiento o una copia hacia una carpeta se anota como `<carpeta>/<nombre>`, y el nombre nuevo de `Rename-Item`, `ren` y `rni`, junto al archivo.
    - Esos dos casos de carpeta salieron al implementar. Se sumaron al rojo: `cp`, `mv` y `Copy-Item -Destination` hacia `db`.
    - `destinos()` y el análisis del writer no cambian; se prueba en A4.
  - **`guard_comandos`:**
    - `Protegidos` guarda la config.
    - `_escritura_de_capa` corre fuera de un writer, después de la Capa 1 y antes de la Capa 2, con el plazo del guard pasado a `writer_guard`.
    - `_mensaje_de_capa` manda a la herramienta de edición de cada host y a `git mv`.
  - **Suites:**

    | Suite | Resultado |
    |---|---|
    | `guard_comandos` | 77/77 |
    | `writer_guard` | 121/121 |
    | `writer_stop` | 57/57 |
    | `plantilla_writer` | 33/33 |
    | `doctor` | 182/182 |
    | `capacidades` | 33/33 |
    | `comun` | 62/62 |
    | `codex` | 41/41 |
    | `pi` | 62/62 |

  - **El «No ve», probado antes de escribirlo:** una variable (`$F`, `$f`), un `[IO.File]` con `"$PWD/…"`, `python3 gen.py`, `git checkout --`, `git apply`, `xcopy` hacia una carpeta, `robocopy` (lee `/otra` como una opción), `find -exec` (deja `{}`) y `xargs`. `Rename-Item -NewName` sí resuelve el nombre junto al archivo.
  - **Los docs:**
    - `Doc/diseno.md` suma el punto «Escrituras de capa» en el guard de comandos, con su «No ve».
    - `Doc/hooks.md` lo suma a la fila «Antes de un comando de shell».
    - La fila X17 de `multi-host.md` apunta a este documento.
    - El CHANGELOG va con la entrega.
- **L11 (2026-11-16), A4: el diferencial y la latencia.**
  - **El diferencial:** la base (`4761041`, sacada con `git archive` al scratch) contra la rama, sobre las 2822 cadenas de `guard_comandos.tests.py` y `writer_guard.tests.py`.
    - Cada cadena corre en tres variantes: Bash y PowerShell con `cwd` en el repo, y Bash con `cwd` en la instancia. En total, 8466 casos.
    - La instancia tiene un repo de capa, un repo `agent_readonly` y el taller.
    - Se compara la decisión de `guard_comandos` en el principal, la de `writer_guard` en un writer y la salida de `destinos()`.
  - **Resultado:** 0 regresiones. `writer_guard` y `destinos()` no cambian en ningún caso.
  - **Las 81 diferencias de `guard_comandos`** son todas el bloqueo nuevo. Cada una apunta a un `.sql` del repo de capa o del taller, sin ninguna fuera de eso:
    - `db/a.sql`: 42
    - `f.sql`: 18
    - `x.sql`: 8
    - `db/p.sql`: 6
    - y 7 más.
  - **La latencia:** el hook como subproceso, 25 corridas intercaladas, con las dos copias del código sin bytecode propio, como en un plugin instalado (todos los hooks ponen `dont_write_bytecode`).

    | Comando | Antes | Después |
    |---|---|---|
    | `git status` | 238 ms | 271 ms |
    | `echo x > db/a.sql` | 247 ms | 278 ms (y ahora bloquea) |
    | `Set-Content` | 241 ms | 272 ms |
    | `ls … \| grep` | 241 ms | 270 ms |

    Son unos +30 ms por comando: compilar `writer_guard.py`. El +7 ms de A0 era con bytecode en caché.
  - **Dos mediciones descartadas, por el montaje:**
    - La copia nueva usaba el bytecode que dejaron los tests y salía 20 ms más rápida.
    - Con `PYTHONPYCACHEPREFIX` vacío se compila también la biblioteca estándar, y todo sube a unos 480 ms.
  - **La decisión:** se aceptan los +30 ms sin prefiltro, porque un prefiltro que no lea igual que el parser abriría un hueco nuevo en un guard.
  - **Seguimiento F1:** los hooks nunca guardan bytecode. Con caché, `guard_comandos` baja de 271 a 213 ms, unos 60 ms, más de lo que suma este cambio. Va al roadmap.
- **L12 (2026-11-16), A5: el verificador independiente sobre `a6c3e93`.** Corrió 139 sondas propias contra la base, en copias hechas con `git archive`. El CI de `a6c3e93` está en verde en los tres sistemas.
  - **Cumplen:** S0, S3 y S4, y D1, D3 y D4.
    - `destinos()` y la decisión del writer no cambian en ninguna sonda.
    - La latencia se reproduce: +29 a +37 ms.
    - Codex y Pi bloquean, y Pi también con `bash_background`, `monitor` y `powershell`.
    - Una escritura de capa bloquea aunque la Capa 2 pregunte.
  - **No cumple S1: B1.** En PowerShell, una opción con valor antes de la ruta esconde el destino:
    - `Set-Content -Encoding UTF8 -Path db/a.sql`, `Out-File -Width 200 -FilePath …` y `New-Item -Path db -Name c.sql` dan exit 0;
    - es lo que pasó en la grabación de X17, con Codex en Windows;
    - la causa: en modo colector, `PRIMER_POSICIONAL` toma el primer posicional, y `_posicionales` deja el valor de cada opción.
  - **D2 a medias: B2,** un falso positivo causado por el cambio. Un Python que solo lee un archivo de capa bloquea, igual que `os.rename('db/a.sql', 'db/a.txt')`. La causa: si `PY_ESCRIBE` encuentra algo en el código, toda cadena con `/` o `.` cuenta como destino.
  - **Avisos:**
    - A1: con más de 100 destinos, el colector se llena y deja pasar.
    - A2: una carpeta destino se decide con `isdir` cuando corre el hook, y la copia recursiva de una carpeta no se ve.
    - A3: herramientas que el writer tampoco ve en la base (`rsync`, `curl -o`, `Invoke-WebRequest -OutFile`, `Tee-Object -FilePath`…).
    - A4: `\\?\C:\…` no se clasifica; fuera de dominio.
    - A5: una excepción o el plazo siguen la regla general de «Fallas».
    - A6: un `New-Item` vacío bloquea.
  - **Scratch del verificador,** para borrar a mano: `%TEMP%\tmp.PbMaPBroZX`.
- **L13 (2026-11-16), la corrección de B1 y B2,** en un solo lote.
  - **El rojo:** 13 casos nuevos en `guard_comandos.tests.py` y 8 en `writer_guard.tests.py`. Dieron 75/77 y 120/121: 9 formas de PowerShell que no bloqueaban y 3 falsos positivos de Python.
  - **El arreglo,** solo en el camino de `escrituras()`. `destinos()` sigue tomando el mismo primer posicional, y hay un test que lo fija.
    - `_destino_de_cmdlet` lee `-Path`, `-LiteralPath`, `-FilePath`, `-PSPath` y `-LP`, también con `:`. Salta los valores de las otras opciones y los interruptores conocidos, y en `New-Item` une `-Path` con `-Name`.
    - `_py_destinos` lee el destino de cada llamada que escribe. Si alguna no tiene una ruta literal, cae al comportamiento conservador de antes.
  - **El verde:** 77/77 y 121/121, con `writer_stop`, `plantilla_writer`, `doctor`, `capacidades`, `comun`, `codex` y `pi` también en verde.
  - **El diferencial repetido** contra `4761041`: 2852 cadenas y 8556 casos, sin regresiones. `writer_guard` y `destinos()` no cambian. Las 107 diferencias son el bloqueo nuevo y apuntan todas a un `.sql` de la capa.
  - **Los avisos A1, A2, A3 y A5** pasan al «No ve» y a «Fallas» en `Doc/diseno.md`. A4 y A6 quedan como están.
  - **El commit:** `634ce47`.
- **L14 (2026-11-16), la revisión limitada a B1 y B2: los dos cerrados.**
  - **B1:** las sondas p05 a p08, p24, p45 y p46 bloquean ahora en Claude Code y en Codex, con el destino real.
  - **B2:** f19, f20 y los Python que solo leen pasan, como en la base. Las escrituras reales a la capa siguen bloqueando: `os.rename` hacia la capa, `write_text` y `shutil.copy`.
  - **Los invariantes se mantienen:** `destinos()` y la decisión del writer son iguales a `4761041` en las 139 sondas originales y en las 15 de la revisión. Frente a `a6c3e93`, solo cambia el conjunto de B1 y B2.
  - **Scratch del verificador,** para borrar a mano: `%TEMP%\tmp.m00xdEbDdv`, además de `%TEMP%\tmp.PbMaPBroZX`.
  - **La parte A queda cerrada.** El CI de `634ce47` está en verde en los tres sistemas.
- **L15 (2026-11-16), B0: los eventos de turno por host.**
  - **Cómo se investigó:** un investigador de solo lectura, con la doc oficial, el código de los upstream leído como dato y las versiones instaladas. El padre comprobó que P6 a P10 ya están ocupadas en `capacidades.py`.
  - **Claude Code 2.1.319:**
    - Fin de turno, `Stop`: solo en el principal (los subagentes disparan `SubagentStop`). Hace seguir al agente con `decision: block` y `reason`. Tiene un tope de 8 continuaciones seguidas, que se reinicia con cada herramienta. Si el hook se cae, el turno cierra igual.
    - Inicio de turno, `UserPromptSubmit`: trae `prompt_id`. También corre con tareas programadas y con los avisos de subagentes en segundo plano.
  - **Codex 0.144 (instalado):**
    - Fin de turno, `Stop`: solo en el hilo raíz. Se usa `decision: block` por JSON con exit 0. El motivo entra como prompt dentro del mismo `turn_id`, y `stop_hook_active` queda en true el resto del turno. No tiene tope, y si el hook falla deja cerrar.
    - Inicio de turno, `UserPromptSubmit` con `turn_id`: corre también dentro de los subagentes (con `agent_id`) y no corre en la continuación.
  - **Pi 1.5.2 con gentle-shell 4.8.0:**
    - Fin de turno, `agent_before_settle` en el padre. Hace seguir con `custom_message` y `continue: true`. No tiene tope ni timeout, un error falla abierto y un abort lo saltea. gentle-ai ya lo usa en el padre.
    - Inicio de turno, `before_agent_start`, sin id de turno; la continuación no lo dispara.
  - **El repo hoy:** no tiene ninguno de los dos eventos.
    - `eventos.py` solo conoce `Herramienta`, `InicioSesion` y `FinSubagente`.
    - Los adaptadores de Claude Code y Codex descartan `Stop` y `UserPromptSubmit`.
    - `pi.leer` toma todo `agent_before_settle` como fin de subagente.
    - El shim registra el settle solo en el hijo.
  - **Archivos que toca la parte B:**
    - `eventos.py`, `capacidades.py` y los tres adaptadores, con sus tests;
    - `hooks.json`, `hooks.codex.json` y `hooks.pi.json`;
    - `shim/pi.ts`;
    - un script nuevo para la revisión de fin de turno;
    - `doctor.py`;
    - los docs.
  - **Costo de la foto:** `git status --porcelain` tardó entre 145 y 225 ms por repo en esta máquina.
  - **Scratch del investigador:** `scratchpad/codex-src/` y `scratchpad/cc-changelog.md`, dentro de la sesión.
- **L16 (2026-11-16), B1: el diseño aprobado.**
  - **Al empezar el turno:** se saca una foto de los archivos de capa que ya están modificados (`git status` de cada repo declarado y del taller), con su contenido, como las fotos del writer. Un subagente no saca foto.
  - **Al terminar el turno:** se buscan los archivos de capa que cambiaron respecto de la foto, sin importar cómo se escribieron. Se les corren las reglas solo sobre las líneas nuevas del turno: contra la foto si el archivo estaba modificado, y contra HEAD si estaba limpio.
  - **Si hay un bloqueo:** el agente sigue y lo corrige, una sola vez por turno, como `writer_stop`. Los avisos van en el mismo mensaje.
  - **Si el turno se corta:** la foto no se reemplaza hasta que corre una revisión, así que el turno siguiente revisa todo lo pendiente.
  - **Si el hook se cae:** el turno cierra igual, porque ningún CLI deja cerrar en falso. Se declara degradado en el manifiesto y en el doctor.
  - **En Claude Code:** `decision: block`, como `writer_stop`.
  - **El costo aceptado:** el revisor no distingue quién escribió el cambio. Si el usuario edita un archivo de capa durante el turno, el agente recibe una vuelta, con el mensaje «si este cambio no es tuyo, avísale al usuario y no lo toques». Cuesta unos 200 ms por repo y por mensaje del usuario.
  - **La aprobación,** a la pregunta «¿Vamos con este diseño?», textual: «Vale me parece bien».
- **L17 (2026-11-17), la ruta de B2.**
  - **Primero, W1 (B2a y B2b):** el modelo neutral y el script, con P11 y P12 «no disponible» en los tres manifiestos. Así su suite queda en verde y se commitea sola.
  - **Después, W2 (B2c a B2f):** los tres hosts, el doctor y los docs. Van juntos porque `capacidades.tests.py` cruza los manifiestos y los tres archivos de hooks, así que un writer por host no podría verificarse solo.
  - **La razón para delegar:** el respaldo de contexto. Esta sesión ya hizo la parte A, su verificación y B0.
  - **Los tests:** el pre-commit y el CI descubren las suites con `git ls-files -- '*.tests.py'`, así que una suite nueva corre en cuanto queda trackeada.
- **L18 (2026-11-17), W1: B2a y B2b.**
  - **El modelo neutral:** `InicioTurno` y `FinTurno`, los puntos `inicio_turno` y `fin_turno`, y P11 y P12 con sus requisitos:
    - P11: `(FIN_TURNO, Seguir)`.
    - P12: `(INICIO_TURNO, Permitir)`, porque una tupla vacía cumpliría con `all(())`.
    - En los tres manifiestos, P11 y P12 quedan «no disponible».
  - **`revisar_turno.py`:**
    - **La foto:** va en `.claude/estado/turnos/<sesion>/`, con un `.foto` por archivo y un `manifiesto.json` escrito de una vez. Sale de `git status --porcelain -z -uall` en cada repo, en sus worktrees y en la raíz de la instancia, y se filtra con `clasificar`.
    - **La revisión:** corre `verificar_archivo` y filtra los hallazgos preexistentes contra la foto.
    - **El mensaje:** nombra la herramienta de edición de cada host y cierra con «si este cambio no es tuyo, avísale al usuario y no lo toques».
  - **Los tests:** `revisar_turno.tests.py` tiene 19 tests, en rojo antes del código.
    - Dos tests nuevos en `capacidades.tests.py`: ningún requisito vacío, y un punto que el adaptador no alcanza figura «no disponible».
    - Un control fija P11 y P12 en «no disponible» hasta W2.
  - **Mutación:** 18 mutantes, 17 detectados. El sobreviviente quita un atajo que no cambia el resultado.
  - **La decisión que pidió el writer:** dos aserciones fijaban el manifiesto completo, en `claude_code.tests.py` y `pi.tests.py`, fuera de su superficie. Las ajustó el padre: son consecuencia directa de P11 y P12.
  - **Las suites, corridas por el padre:**

    | Suite | Resultado |
    |---|---|
    | `eventos` | 8/8 |
    | `capacidades` | 35/35 |
    | `revisar_turno` | 19/19 |
    | `claude_code` | 37/37 |
    | `codex` | 41/41 |
    | `pi` | 62/62 |
    | `doctor` | 182/182 |
    | `writer_stop` | 57/57 |
    | `verificar_capa` | 87/87 |

  - **Pendiente para W2:**
    - `EXPRESABLES` de `INICIO_TURNO` y `FIN_TURNO` en cada host;
    - sacar el control de P11 y P12;
    - sumar `revisar_turno` a `HOOKS` en `capacidades.tests.py`;
    - las dos aserciones de los adaptadores;
    - `Doc/diseno.md:131`, que dice «P1 a P10».
  - **Scratch del writer,** para borrar a mano: `%TEMP%\tmp.EseIW9Eohu`.
  - **El commit:** `b524566`, con el CI en verde en los tres sistemas.
- **L19 (2026-11-17), W2: B2c a B2f.**
  - **Claude Code:**
    - `Stop` se lee como `FinTurno`, con `continuado` sacado de `stop_hook_active`.
    - `UserPromptSubmit` se lee como `InicioTurno`, con `turno` sacado de `prompt_id`. Toma solo `agent_id`, porque `agent_type` también llega con `--agent`.
    - `Seguir` sale como `decision: block`, igual que en `writer_stop`.
  - **Codex:** los mismos dos eventos, con `turn_id`. Un `UserPromptSubmit` de un subagente trae `agente`, así que no saca foto. Responde por JSON con exit 0.
  - **Pi:**
    - Cada grupo de `before_agent_start` y de `agent_before_settle` en `hooks.pi.json` lleva `agente: "writer" | "principal"`, y el shim los compara exactos. Así el padre y el hijo no pueden correr la misma compuerta.
    - El settle del padre manda `oddWs.child: false`, y `pi.py` lo lee como `FinTurno`.
    - `before_agent_start` del padre corre la foto y el shim la espera, porque Pi 1.5.2 hace `await` de esos handlers.
  - **Hooks:**
    - Al inicio, `--plazo 8` con timeout 10.
    - Al fin, `--plazo 50` con timeout 60, como `writer_stop`.
    - Sin `matcher`, porque Codex y Claude Code lo ignoran en esos eventos.
  - **Manifiestos:** P11 queda `degradado` en los tres, porque si el hook se cae el turno cierra igual. P12 queda `soportado`.
  - **Doctor:**
    - `hooks-host` cuenta los hooks nuevos.
    - En Codex, `codex-hooks` pide la confianza de los dos handlers nuevos.
    - En Pi:
      - revisa la cobertura por agente;
      - marca los grupos muertos;
      - la regla del settle pasa a ser por agente: el writer corre `writer_stop` y el principal, `revisar_turno`.
  - **Docs:**
    - `Doc/hooks.md` suma las filas de inicio y de fin de turno.
    - `Doc/diseno.md` suma la subsección «Revisión del fin del turno» y corrige «P1 a P10».
    - `multi-host.md` suma las filas P11 y P12.
  - **Rojo antes del código:**

    | Suite | Resultado |
    |---|---|
    | `capacidades` | 26/37 |
    | `claude_code` | 35/40 |
    | `codex` | 37/44 |
    | `pi` | 58/66 |
    | `doctor` | 180/184 |
    | `revisar_turno` | 19/21 |
    | TS | 66/77 |

  - **Verde:** los 46 archivos `*.tests.py` y 85/85 en TypeScript. El padre volvió a correr TypeScript y le dio 85/85.
  - **Lo que agregó el padre:** W2 avisó que en Claude Code un writer en segundo plano puede seguir escribiendo cuando corre el `Stop` del principal. Así, el principal recibiría la vuelta por un trabajo a medias, con un mensaje que culpa al usuario.
    - `revisar_turno` ahora deja fuera un archivo que tiene una foto de un writer en curso de la misma sesión (`writers/<sesion>/<agente>.fotos/`), porque lo revisa `writer_stop`.
    - Compara la clave de la ruta y la de su `realpath`.
    - Un test, en rojo antes del código, cubre también que la foto de otra sesión no saca el archivo. `revisar_turno` queda en 22/22.
  - **Notas de W2, sin bloqueo:**
    - cada mensaje del usuario lanza ahora un proceso Python en los tres hosts, que sin instancia sale enseguida;
    - registrar `agent_before_settle` en el padre lleva a Pi a su camino de cierre por frontera, el mismo que ya usa gentle-ai en gentle-shell.
  - **Scratch de W2,** para borrar a mano: `%TEMP%\tmp.Q9obgKEw14` y `%TEMP%\tmp.kzTQUXKgG2`.
