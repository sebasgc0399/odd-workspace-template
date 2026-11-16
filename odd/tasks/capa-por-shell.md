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
| A5 | S1, S4 | Verificador independiente (ítem 2), con sondas en un scratch aparte | delegado | pendiente |
| B0 | S2, S3 | Investigación por host, con la doc y la versión instalada:<br>• Claude Code: `Stop` y `UserPromptSubmit`;<br>• Codex: `Stop` (L4);<br>• Pi: `agent_before_settle` en el padre, y si hay un evento de inicio de turno.<br>Sale una fila P6 en la tabla de capacidades de `multi-host.md` | inline; un explorador si pasa del presupuesto | pendiente |
| B1 | S2 | Diseño:<br>• la foto al inicio del turno: qué se guarda y cuánto cuesta en un repo grande;<br>• cómo no culpar al agente de lo que cambió el usuario;<br>• qué hallazgos hacen seguir al agente;<br>• cómo no repetir lo que ya chequeó la edición;<br>• el tope de vueltas;<br>• la degradación en un host sin el evento | inline, con el usuario | pendiente |
| B2 | S2, S3 | Las tareas de implementación salen de B1 | — | pendiente |
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
