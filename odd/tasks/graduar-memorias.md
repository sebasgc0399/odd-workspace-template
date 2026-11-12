# Graduar memorias: las memorias del proyecto como fuente de candidatos

Objetivo: que `/odd-ws:cerrar` pueda graduar lo que ya está en las memorias del proyecto (la memoria en archivos de Claude Code y, opcional, engram), sin depender del formato de handoff que se propuso en el issue #1 de `gentle-contribution-skills`. Rama: `feat/graduar-memorias`, desde `main` (`dec68d4`). Entrega: un commit por unidad en la rama; push y avance de `main` solo con autorización. Runner: Python sin pytest, `python <x>.tests.py`. Espejo en Engram: `odd/graduar-memorias/tasks`.

## Specs

- **S1. El pedido (L1).** «quiero hacer lo que seria de parte mia, sin depender de el hasta que es complete el issues, que seria leer memorias» y «Si expora como meter esas memorias en la graduacion». El lector del JSON de handoff queda fuera hasta que el issue se acuerde.
- **S2. Dónde vive (propuesta aprobada en L2).** Un modo aparte, `/odd-ws:cerrar memorias`, que reusa el triaje, la aprobación y la escritura de la matriz de `cerrar`. El cierre de un ticket no tría memorias: solo avisa en una línea «N memorias sin triar».
- **S3. El script `memorias.py` (propuesta aprobada en L2).** Determinista y con tests:
  - **Resuelve el directorio** en este orden: `--memorias <dir>`, `autoMemoryDirectory`, y `CLAUDE_CONFIG_DIR` (o `~/.claude`) más `projects/<slug>/memory`. El slug sale de la raíz del repo de la instancia, con todo lo que no es alfanumérico cambiado por `-`. La resolución vive en el adaptador de Claude Code.
  - **Si el directorio no existe, sale con 2 y nombra la ruta que probó.** Nunca responde «0 candidatos» (principio 4 de `Doc/diseno.md`).
  - **Enumera** los `*.md` menos `MEMORY.md`, y acepta `type` y `modified` en la raíz del frontmatter o bajo `metadata:`.
  - **Estado de cada memoria:** `graduada` (su slug está en un `origen` de la matriz), `vista`, `descartada` o `cambiada` (según el registro de S4 y su `modified`) y `nueva`.
  - **Filtro:** por defecto solo `feedback`; `project` con una opción; `user` y `reference`, nunca.
  - **Salida:** una tabla, `--json`, y una línea de cobertura `COBERTURA claude-code: completa (N, <dir>, pasada|derivada)`.
- **S4. Lo visto o descartado (propuesta aprobada en L2).** Va en un registro local de la máquina, fuera del repo, en `~/.odd-ws/memorias/<slug-instancia>.json`, con la clave `slug@modified`. Lo escribe el script, a pedido de la skill, después del sí del usuario.
- **S5. engram (propuesta aprobada en L2).** Es una fuente opcional que consulta la skill, no el script. El origen va como `memoria:engram-<id>`, que el regex actual ya acepta. La cobertura se declara parcial, con las consultas que llegaron al tope («20/20: puede haber más»). Sin las herramientas de engram, o sin proyecto resuelto, se dice y se omite.
- **S6. Privacidad (propuesta aprobada en L2).** Las memorias `user` quedan afuera. La fila de la matriz no copia texto literal ni nombres de personas. La propuesta muestra exactamente lo que va a quedar escrito. La matriz viaja en el repo de la instancia, y ahí no corre ningún barrido.
- **S7. El crédito (L1 del contexto).** El CHANGELOG da crédito a la idea de usar las memorias como fuente de candidatos («te doy el credito», mensaje del usuario a Denver2828).

**Supuestos a verificar:**
- En Codex, la memoria de Claude Code no aplica: el modo dice «no disponible» y sigue con engram si está. Se verifica en T1.
- La ruta que carga la sesión es la mejor fuente para `--memorias`, y la derivación es el respaldo. Si Claude Code usa la ruta lógica o la resuelta cuando hay junctions es una pregunta abierta: la derivación se rotula «derivada».

## Tasks

| ID | Specs | Qué | Ruta | Estado |
|---|---|---|---|---|
| T1 | S1, S3 | `memorias.py`: resolución del directorio en el adaptador de Claude Code, enumeración, frontmatter, estados `graduada` y `nueva` contra la matriz, filtro por tipo, cobertura y exit 2. Más sus tests | delegado: un writer, por el respaldo de contexto de una sesión larga | hecho (L3) |
| T2 | S3, S4 | El registro local: `vista`, `descartada` y `cambiada`, y el subcomando para registrar. Más sus tests | delegado, por la misma razón | pendiente |
| T3 | S2, S5, S6, S7 | La skill: el modo `memorias` de `cerrar`, el paso opcional de engram, las reglas de privacidad y el aviso del cierre de ticket. Los docs: `Doc/uso.md`, `Doc/diseno.md` y el CHANGELOG | delegado, por la misma razón; después, un verificador independiente (ítem 2: exposición de datos personales hacia un repo) | pendiente |

## Log

- **L1 (2026-11-12), el pedido.** Textual: «No si exacto quiero hacer lo que seria de parte mia, sin depender de el hasta que es complete el issues, que seria leer memorias / Si expora como meter esas memorias en la graduacion».
- **El contexto:** el usuario abrió el issue #1 en `Denver2828/gentle-contribution-skills`, que propone un `ratchet-handoff/v1`. Le escribió a Denver2828: «De mi lado quiero tomar la idea de usar las memorias como fuente de candidatos y te doy el credito».
- **La exploración (resumen):**
  - Hoy `cerrar` solo saca candidatos del ticket (`plugin/skills/cerrar/SKILL.md:22`).
  - `memoria:<slug>` ya es un origen válido sin `@hash` (`plugin/scripts/matriz.py:22`), pero nada comprueba que la memoria exista.
  - En el hermano de origen, el slug de `memoria:` es el nombre del archivo sin `.md`.
  - La memoria de Claude Code está en `<config>/projects/<slug>/memory/`. El slug es la ruta con lo no alfanumérico cambiado por `-` (verificado en 7 de 7 carpetas locales), y la memoria se comparte por repo git. En Windows, la mayúscula de la unidad varía (`c--`).
  - En los archivos locales, `type` y `modified` van bajo `metadata:`.
  - En engram, `mem_search` devuelve como mucho 20, sin fechas ni cursor.
- **L2 (2026-11-12), la aprobación.** Textual: «Si me parece bien hagamos un plan, analizamos todo bien y arrancamos». El usuario aprobó la propuesta: el modo `cerrar memorias`, el script con tests, engram opcional, el registro local y las reglas de privacidad.
- **L3 (2026-11-12), T1 hecha (S1 y S3).**
  - **`memorias.py`** (`--memorias`, `--raiz`, `--host`, `--con-project` y `--json`):
    - sale con 0, o con 2 y la ruta que probó; el 1 no se usa;
    - los estados son `graduada`, `ilegible` y `nueva`; T2 suma los suyos en `ORDEN`;
    - las líneas `AVISO` cubren las huérfanas, los links rotos y las filas de la matriz con errores;
    - después van `EXCLUIDAS` y `COBERTURA`.
  - **En `odd_ws.hosts`:**
    - `claude_code.directorio_de_memorias`, con el orden `--memorias` → `autoMemoryDirectory` → `CLAUDE_CODE_PROJECT_DIR_NAME` → `<config>/projects/<proyecto>/memory`;
    - la raíz del repo sale de subir por el disco, sin `realpath` ni git, y un worktree da el repo principal;
    - en Windows, la carpeta se busca sin distinguir mayúsculas;
    - con más de 200 caracteres, sale con 2 y pide `--memorias`.
  - **Codex** declara `MEMORIAS = NO_DISPONIBLE`, con un test de paridad en `capacidades.tests.py`.
  - **Agregado por el writer, aceptado:** `CLAUDE_CODE_PROJECT_DIR_NAME`, documentado desde la 2.1.234.
  - **El supuesto de Codex quedó refutado en parte:** Codex tiene su propia memoria local, apagada por defecto, en `$CODEX_HOME/memories_v2/` y sin formato documentado. No se implementa ahora; queda como seguimiento.
  - **Pruebas:**
    - RED observado en cada regla;
    - `memorias` 15/15, `claude_code` 37/37, `codex` 41/41, `capacidades` 24/24 y `matriz` 51/51; 42 de 42 suites en verde;
    - el diferencial por AST de `hosts` contra `HEAD`: 0 definiciones cambiadas, solo agregados;
    - el padre repitió `memorias`: 15/15.
  - **Risk:** ninguno de los ítems altos. Agregar un puerto a `hosts` sin cambiar nada existente no es el ítem 3, así que no lleva verificador.
- **La entrega:** el pronóstico es de unas 700 a 850 líneas, en tres commits de unidad. No hay PR: `main` avanza por fast-forward con autorización, como en la `0.3.1`. La revisión nativa de gentle-ai está apagada (`review mode status`: off, global), así que el riesgo lo cubre el verificador independiente de T3.
