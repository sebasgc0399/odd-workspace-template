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
| T1 | S2, S3 | Lo que entra al primer commit: el `settings.json` y el `.code-workspace` | delegada. Risk: item 1, porque decide qué se commitea; lleva verificador | hecho; verificador en curso (L4) | `bb003bf` |
| T2 | S4 | La raíz de un repo de código: preguntar siempre, y `workspace.local.json` nunca en un commit | delegada, después de T1, porque toca la misma función. Risk: item 1; lleva verificador | hecho; verificador en curso (L4) | `d26d82e` |
| T3 | S5 | La propuesta de extensiones del mismo lenguaje | delegada, con T1 y T2 | hecho | `550a7fe` |
| T4 | S6, S7 | `Doc/uso.md:9` y la nota del README | inline: el writer se cortó antes, y son solo docs (L4). Risk: none | hecho; la línea del CHANGELOG va con la entrega | este commit |

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
