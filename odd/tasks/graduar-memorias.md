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
| T1 | S1, S3 | `memorias.py`: resolución del directorio en el adaptador de Claude Code, enumeración, frontmatter, estados `graduada` y `nueva` contra la matriz, filtro por tipo, cobertura y exit 2. Más sus tests | delegado: un writer, por el respaldo de contexto de una sesión larga | hecho (`c1a1938`, L3) |
| T2 | S3, S4 | El registro local: `vista`, `descartada` y `cambiada`, y el subcomando para registrar. Más sus tests | delegado, por la misma razón | hecho (`e018699`, L4) |
| T3 | S2, S5, S6, S7 | La skill: el modo `memorias` de `cerrar`, el paso opcional de engram, las reglas de privacidad y el aviso del cierre de ticket. Los docs: `Doc/uso.md`, `Doc/diseno.md` y el CHANGELOG | delegado, por la misma razón; después, un verificador independiente (ítem 2: exposición de datos personales hacia un repo) | hecho (L5, L6) |
| X1 | S3 | Seguimiento (A7): una memoria `graduada` que cambia sigue `graduada`, sin aviso, y su fila puede quedar desfasada | inline, aparte | pendiente |
| X2 | S3, S4 | Seguimiento (A11): `--registrar` acepta slugs `user` y `reference`; la frase «modified de hoy» del help; `autoMemoryDirectory` de policy y de `--settings`; exigir `name` y `description` | inline, aparte | pendiente |
| X3 | S6 | Seguimiento (V1): si `matriz.py` pide corregir la fila, la regla o la evidencia, la corrección se escribe sin volver a mostrarse. Una línea en M4.1: mostrarla y pedir el sí | inline, aparte | pendiente |
| X4 | S6 | Seguimiento (V2): M3.2 no dice cómo calcular el ID, y el script del paso 5 también mira `verificar_<capa>.py`. Una línea: calcularlo igual que el script | inline, aparte | pendiente |
| X5 | S6 | Seguimiento: `test_las_reglas_del_modo_y_la_propuesta_nombran_la_evidencia` deja vivos dos mutantes. Comprobar la primera oración de la regla 2, agregar M4.1 y sumar un control por mutación | inline, aparte | pendiente |
| X6 | S5 | Seguimiento: Codex tiene su propia memoria (`$CODEX_HOME/memories_v2/`, apagada por defecto y sin formato documentado) | cuando se documente su formato | pendiente |
| X7 | S1 | El lector del `ratchet-handoff/v1` de `gentle-contribution-skills` | cuando se acuerde el issue #1 | pendiente |

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
- **L4 (2026-11-12), T2 hecha (S3 y S4).**
  - **Las opciones nuevas:**
    - `--registro ARCHIVO`, que por defecto es `~/.odd-ws/memorias/<proyecto>.json`, con el nombre de T1 sobre `raiz_del_proyecto`;
    - `--registrar SLUG... --como vista|descartada`, la única escritura del script. Después de escribir, lista igual que sin la opción.
  - **La precedencia:** `graduada` > `ilegible` > `cambiada` > `descartada` > `vista` > `nueva`. La tabla ordena primero lo accionable.
  - **El registro:**
    - `{"version": 1, "memorias": {"<slug>@<modified>": {slug, modified, estado, fecha}}}`, con una entrada por slug;
    - la escritura es atómica e idempotente, y conserva la fecha si nada cambió;
    - si falta, cuenta como vacío y no se crea; si está ilegible, sale con 2 sin pisarlo;
    - un slug inexistente sale con 2 sin escribir.
  - **Lo que no cambió:** sin registro, la salida es byte a byte la de T1. El diferencial da 12 de 13 casos iguales; la única diferencia es el `usage:` de argparse, que ahora lista las opciones nuevas.
  - **Pruebas:**
    - `memorias` 28/28, `claude_code` 37/37 y `matriz` 51/51;
    - 16 mutantes, uno por regla, todos muertos;
    - el padre repitió `memorias`: 28/28.
  - **Pendientes para T3:**
    - documentar las opciones nuevas;
    - no hay opción para olvidar una entrada: se borra a mano;
    - las entradas de memorias borradas siguen contando en `REGISTRO (n)`.
  - **Risk:** none. Es un archivo local y nuevo, fuera del repo.
- **L5 (2026-11-12), T3 escrita y su verificador independiente.**
  - **T3:**
    - `cerrar/SKILL.md` suma el «Modo memorias» (M1 a M5), el paso 10 («N memorias sin triar») y un párrafo de entrada; los pasos 1 a 9 quedan byte a byte;
    - `Doc/uso.md` y `Doc/diseno.md` cubren el modo y `memorias.py`;
    - el CHANGELOG suma `## Sin publicar`, con el crédito a Denver2828.
    - El replay sintético dio `graduada`, `vista` y Codex «no disponible».
  - **El verificador:** S1 a S5 y S7 cumplen, y S6 es parcial.
  - **B1:** la entrada de `evidencia.md` se escribe sin mostrarse en la propuesta, y ninguna regla le prohíbe nombres.
  - **Advisories que entran en la corrección:**
    - **A1:** la búsqueda de engram en la matriz es por subcadena (`engram-12` contra `engram-123`).
    - **A2:** las herramientas `mem_*` pueden llegar diferidas detrás de ToolSearch.
    - **A3:** `mem_current_project` sin la raíz de la instancia.
    - **A4:** una observación sobre una persona cuenta como `user`.
    - **A5:** «no la gradúes», sin inventar otro slug.
    - **A6:** `cambiada` depende solo de `modified`.
    - **A8:** el aviso dice `derivada` o `pasada`.
    - **A9:** las excepciones del paso 5 en M4.1.
    - **A10:** `descripcion` también es texto de la memoria.
  - **Seguimientos:** A7 (una graduada que cambia sigue `graduada`) y A11 (detalles menores de T1 y T2).
  - **La corrección:** una tanda para B1 y esos avisos, más las sondas del verificador como tests de regresión, devuelta al writer de T3. Después, un rechequeo limitado a B1.
- **L6 (2026-11-12), la corrección de T3 y su rechequeo.**
  - **La corrección:**
    - B1 cerrado en la skill: la regla 2 cubre la fila, el destino y la evidencia, y nombra `descripcion`; la regla 4 y M3.2 muestran la evidencia; M4.1 escribe la misma.
    - A1 a A6, A8 a A10 y la decisión 1, en la skill y en los docs.
    - 6 tests nuevos de regresión, cada uno con su RED: el contrato de los comandos de la skill contra el parser, las claves del JSON, la evidencia en las reglas, el origen exacto de punta a punta, el límite de `modified`, y `## Sin publicar` en `entrega.tests`.
  - **Pruebas:** `memorias` 33/33, `entrega` 31/31, `notas` 11/11, `matriz` 51/51 y 21 links sin rotos. El padre repitió `memorias`: 33/33.
  - **El rechequeo (limitado a B1): cerrado.** Con la reproducción al pie de la letra, lo escrito en `matriz.csv`, `criterios` y `evidencia.md` es igual a lo mostrado, y el nombre y la frase literal no aparecen. Las variantes y la debilidad del test quedan como seguimientos X3 a X5: un hallazgo nuevo no abre otra tanda.
  - **La entrega:** el CHANGELOG lleva `## Sin publicar`, con el crédito a Denver2828. Al entregar se renombra a `## <versión>`, nunca se agrega una sección aparte.
- **La entrega:** el pronóstico es de unas 700 a 850 líneas, en tres commits de unidad. No hay PR: `main` avanza por fast-forward con autorización, como en la `0.3.1`. La revisión nativa de gentle-ai está apagada (`review mode status`: off, global), así que el riesgo lo cubre el verificador independiente de T3.
