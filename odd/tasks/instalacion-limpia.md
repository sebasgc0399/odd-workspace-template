# La instalación limpia (R7, `0.10.0`)

Objetivo: que la instalación salga limpia para el video de la `0.10.0`. Abarca lo que entra al primer commit de la instancia, el bootstrap en la raíz de un repo de código, la propuesta de extensiones y los docs. El video se publica después de la `0.10.0` y tiene que mostrar el producto funcionando bien.
Rama: `feat/instalacion-limpia`, desde `de07bf8`, la rama de R6 con R5 adentro. Entrega: un commit por unidad; el push a main y la etiqueta, solo con autorización.
Pruebas: `python3 plugin/scripts/<script>.tests.py`, todas con el bucle de `CONTRIBUTING.md`, y `node --test plugin/shim/*.test.ts`.

## Specs

Cada spec cita al autor tal cual. La evidencia de cada idea es su fila del [roadmap](../roadmap.md#ideas) y la toma real de L2.

- **S1. El alcance.** «Si para que el video de una quede bien, porque primero voy a sacar la proxima version antes de subir este video, entonces de una vez que quede actualizado» y «Si necesito que vaya todo que una vez dejemos lo mas estable y bien hecho esta version para hacer un buen video y no solo mostrar defectos, si encontramos otro defecto o algo malo lo corregimos para que el video salga digamos perfecto, no mostrando errores». Entran I55 a I60, y la versión es la `0.10.0`.
- **S2. El `settings.json` en el primer commit (I55).** A la pregunta «¿Meto I55 en la próxima versión?», el autor respondió «Si». Si `.claude/settings.json` ya existe, no está trackeado y tiene el contenido que el bootstrap habría escrito, entra al primer commit. Si es distinto, no se commitea en silencio: el mensaje final lo nombra y dice que lo commitee el usuario si es suyo.
- **S3. El `.code-workspace` en el primer commit (I58).** El autor: «Me parece bien», sobre «que entre al primer commit cuando sus carpetas usen rutas relativas, y que si alguna es absoluta quede sin trackear y el mensaje final lo diga». Supuesto: es el `.code-workspace` de la raíz de la instancia, el mismo que lee `bootstrap.py --proponer`.
- **S4. La raíz de un repo de código (I56).** Aprobado junto con S1:
  - Cuando la raíz de la sesión es un repo de código, el bootstrap pregunta siempre antes de usarlo como instancia y recomienda una carpeta aparte. Un repo de código es uno con archivos versionados y sin `workspace.config.json`.
  - `workspace.local.json` nunca entra a un commit, diga lo que diga el `.gitignore`.
- **S5. La propuesta de extensiones (I59).** La propuesta del bootstrap solo ofrece sumar a una capa extensiones de su mismo lenguaje, como dice la ayuda de `capas-cobertura`. Un `.json` no se ofrece para la capa `ts`.
- **S6. La raíz frente a la subcarpeta en los docs (I57).** `Doc/uso.md:9` distingue los dos casos: en una subcarpeta, la instancia pierde su git; en la raíz de un repo, el bootstrap pregunta (S4).
- **S7. La nota del marketplace (I60).** El README explica qué hacer si `claude plugin marketplace add` falla con «its source doesn't match its extraKnownMarketplaces entry»: el marketplace ya está registrado, y se sigue con `plugin install`.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|---|---|---|---|---|---|
| T0 | S1 | Este documento y la fila de R7 en el roadmap | inline, va en el primer commit del writer | hecho | |
| T1 | S2, S3 | Lo que entra al primer commit: el `settings.json` y el `.code-workspace` | delegada. Risk: item 1, porque decide qué se commitea; lleva verificador | hecho; verificador: S2 PASS, S3 con B1 corregido en C1 (L5) | `bb003bf` |
| T2 | S4 | La raíz de un repo de código: preguntar siempre, y `workspace.local.json` nunca en un commit | delegada, después de T1, porque toca la misma función. Risk: item 1; lleva verificador | hecho; verificador: PASS (L5) | `d26d82e` |
| T3 | S5 | La propuesta de extensiones del mismo lenguaje | delegada, con T1 y T2 | hecho | `550a7fe` |
| T4 | S6, S7 | `Doc/uso.md:9` y la nota del README | inline: el writer se cortó antes, y son solo docs (L4). Risk: none | hecho; la línea del CHANGELOG va con la entrega | `69e524c` |
| C1 | S3 | Corrección del bloqueante B1 del verificador: un `.code-workspace` ignorado con nombre no ASCII hacía fallar el primer commit (L5) | inline. Risk: item 1 | hecho; rechequeo de B1 en curso | este commit |
| F1 | S2, S3 | Seguimiento (A1 del verificador): sin repo git todavía, el ensayo no mira un `.gitignore` que ya existía, y promete en el commit un `settings.json` o un `.code-workspace` que la aplicación deja afuera. Va en la dirección segura (L5) | aparte | anotado | |
| F2 | S3 | Seguimiento (A2): un `.code-workspace` con comentarios o comas finales (el JSONC de VS Code) queda afuera aunque sus rutas sean relativas; la salida lo explica. Es el mismo límite de `--proponer` (L5) | aparte | anotado | |
| F3 | S2, S3 | Seguimiento (A4): la línea `commit: falló …` dice que quedaron en el índice «los archivos nuevos», y también quedan los que ya existían (L5) | aparte | anotado | |

## Log

- **L1** (2026-11-19) Los pedidos del autor, tal cual: son los de S1, S2 y S3. Venían de la revisión del video «Instalar odd-ws», verificada contra la `0.9.1`.
- **L2** (2026-11-19) La toma real con el marketplace: Claude Code 2.1.327, Windows y la `0.9.1` instalada con `--scope project`.
  - El primer commit tuvo 16 archivos.
  - `git status --short --ignored` dio `?? .claude/settings.json`, `?? mi-proyecto.code-workspace` y `!! workspace.local.json`.
  - `.claude/settings.json` quedó como lo dejó `plugin install`: `{"enabledPlugins": {"odd-ws@odd-workspace-template": true}}`. Es idéntico a `tickets/_plantilla/.claude/settings.json`.
  - El repo de código quedó intacto.
  - `marketplace add` falló porque el marketplace ya estaba registrado con la URL git completa.
- **L3** (2026-11-19) Plan. Un writer hace T1 a T4 en orden, porque T1 y T2 cambian la misma función (`commitear` del bootstrap). En paralelo, otro carril cierra los seguimientos de R5 y R6 en `fix/seguimientos-0-10`. T1 y T2 llevan verificador independiente.
- **L4** (2026-11-19) T1 a T3 quedaron commiteados por el writer; el autor pidió parar antes de T4, y T4 se hizo inline al retomar.
  - **Los docs.** `Doc/uso.md` distingue la subcarpeta de la raíz de un repo de código (S6) y explica lo que entra al primer commit, la pregunta en la raíz de un repo, la propuesta del mismo lenguaje y el `.code-workspace` relativo. `Doc/diseno.md` §Bootstrap suma `--confirmar-repo`, `repo_de_codigo`, `mismo_lenguaje`, las reglas del primer commit con sus líneas tal cual y los casos nuevos de la prueba de punta a punta.
  - **La nota del marketplace (S7)** va en el README y también en `Doc/equipo.md`, que repite el mismo comando para quien clona la instancia.
  - **Lo que falta de I57:** la línea del CHANGELOG que distingue la subcarpeta de la raíz. La sección de la `0.9.1` ya se publicó, así que la aclaración va en la de la `0.10.0`, al armar la entrega.
  - **El verificador de T1 y T2** se lanzó al retomar, contra `de07bf8`.
- **L5** (2026-11-19) El verificador de T1 y T2: S2 PASS, S4 PASS y S3 FAIL por un bloqueante.
  - **Lo que probó.** Corrió más de 60 sondas sobre copias de `de07bf8` y `d26d82e`:
    - el `settings.json` real de L2 con varios formatos;
    - workspaces con rutas absolutas de todas las formas;
    - la raíz de un repo de código con worktrees, HEAD separado y la ruta escrita de varias maneras;
    - `workspace.local.json` con `!workspace.local.json` en el `.gitignore`;
    - las invariantes contra la base.

    `bootstrap.tests.py` dio 183/183 y `bootstrap_e2e.tests.py` 26/26.
  - **B1.** Un `*.code-workspace` de la raíz con nombre no ASCII que el `.gitignore` ignora hacía fallar el primer commit entero, y en la base se commiteaba bien.
    - **Causa.** `_ignorados` leía `git check-ignore` sin `-z`, y git cita esos nombres (`"dise\303\261o.code-workspace"`), así que el archivo pasaba por no ignorado y `git add` lo rechazaba.
    - **Daño.** En un repo de código confirmado, además, dejaba 16 archivos stageados en el índice del usuario.
  - **La corrección (C1).**
    - `_ignorados` usa ahora `check-ignore -z --stdin`, y `_git` acepta una `entrada` opcional. Los dos tests que reemplazan `_git` la reenvían.
    - El test nuevo `test_un_code_workspace_ignorado_con_nombre_no_ascii_no_frena_el_primer_commit` dio RED antes del arreglo (`commit: falló (hint: …)`) y GREEN después.
    - Las suites dan 183/183 y 27/27.
  - **Avisos.** A1, A2 y A4 quedan como F1 a F3. A3 (entradas de `folders` fuera del esquema de VS Code) es entrada fuera de dominio y no se anota.
