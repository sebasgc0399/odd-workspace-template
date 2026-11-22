# La primera impresión: bootstrap, doctor y registro (I66 a I69, I72 a I74)

Objetivo: que lo primero que ve quien instala odd-ws (la propuesta del bootstrap, la salida del doctor, los avisos de las reglas y el registro de todo el texto) quede bien, antes de regrabar el video de instalación. Salió de regrabar ese video en la `0.12.1`, que destapó fricciones reales en pantalla.
Rama: `feat/primera-impresion`, en `D:/Project/odd-ws-wt/feat`, desde `origin/main` (`7c16c91`, la `0.12.1` más documentación). Entrega: un commit por unidad, como en las features anteriores (rama de entrega con merge `--no-ff`, sin PR); el push y la publicación, solo con el ok explícito del autor. Sale en la `0.13.0`.
Pruebas: `python plugin/scripts/<script>.tests.py` (en Linux y macOS, `python3`) y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites.

## Specs

El origen es el pedido del autor (L1) y el criterio que fijó (L2): la calidad, no el tiempo. El alcance son las ideas I66 a I69 y I72 a I74 del roadmap, con el diseño que el autor aprobó (L5). La evidencia está en L3 (los mapas de los exploradores) y L4 (las tomas de la `0.12.1`). Lo marcado como **decisión de diseño** no lo pidió el autor con esas palabras: es cómo se cumple su pedido, y lo aprobó con «Dale, avanza con el documento de la feature».

- **S1** (I66, la propuesta del bootstrap). En una terminal normal (unas 24 filas), lo que el usuario decide queda a la vista sin subir, junto a la pregunta.
  - **Decisión de diseño:** se mantiene la «una sola parada» de la `0.9.0`. La respuesta del paso 3 se reordena: primero lo detectado y el ensayo (con sus explicaciones, que siguen ahí: el video dice «cada término viene explicado»); al final, un bloque corto «Lo que decides» con el perfil en la primera fila, después los tickets (prefijo o tracker) y si el repo es tuyo (`own`), y la pregunta justo debajo.
  - El perfil se explica en una línea llana: si ya usas tu propia orquestación o revisión (por ejemplo gentle-ai), `controles`; si no, `completo`.
  - Los tests que fijan la estructura del paso 3 (`bootstrap.tests.py`, el de la propuesta del perfil) se adaptan a la estructura nueva y siguen exigiendo lo que exigen hoy.
- **S2** (I67, una instancia nueva sin avisos). En una instancia recién creada sobre un repo TypeScript, el doctor da 0 AVISO.
  - **Decisión de diseño:** los archivos de datos y configuración sin capa son esperados y no dan AVISO: `.json`, `.jsonc`, `.yml`, `.yaml`, `.toml`, `.lock`, `.ini` y los archivos sin extensión (`.gitignore`, `Dockerfile`…). Se nombran en el detalle de la fila OK, con su conteo, y con la nota de que un cambio en ellos lleva `/odd-ws:revisar` a modo `completo`. Una extensión que no es de ese grupo (por ejemplo `.mjs` en un repo sin capa `js`) sigue dando AVISO.
  - `config_loader.cobertura_de_los_repos` lo comparten el doctor y `ticket.py --cobertura` (que usa `abrir`): los dos aplican la misma separación, con el mismo texto.
  - **Fuera de alcance:** el triaje de `revisar` no cambia (cuenta por su cuenta y lo estudia la I44).
- **S3** (I69, el comando de calibrar). El aviso de una regla sin calibrar trae un comando que se puede correr tal cual desde la raíz de la instancia: la ruta absoluta del `reglas.py` del plugin entre comillas, la capa y la carpeta real.
  - La carpeta sale, en este orden: de una regla ya calibrada de la capa (como hoy), del `path` del primer repo de la capa en la config. Solo si no hay ninguna de las dos queda `<carpeta>`.
  - El comando funciona igual con espacios en las rutas, y en Windows, Linux y macOS.
- **S4** (I72, el doctor legible). La salida del doctor separa en grupos con su encabezado: primero lo de la plantilla (solo tiene sentido en un clon de odd-workspace-template), después lo de tu máquina (Python, git, los CLI, gentle-ai, `rdd`, telemetría, engram, jq y `plugin-root`), y al final lo de esta instancia, con la línea de resumen («0 FALTA, 1 AVISO») debajo, como hoy.
  - **Decisión de diseño:** el resumen queda al final y no arriba, como decía la idea, porque en una terminal lo que se ve sin subir es el final. La agrupación se hace al imprimir: `diagnosticar` conserva su orden y sus nombres, que fijan los tests y que importan otros tests.
  - Un ítem nuevo que no figure en el grupo de la plantilla ni en el de la máquina cae en el de la instancia.
- **S5** (I73, `plugin-root` sin la ruta del usuario). En la fila OK, la ruta del plugin se muestra relativa al home (`~` más el resto, con el separador del sistema) si está bajo el home; si no, absoluta. Los FALTA y su arreglo siguen con la ruta absoluta, porque se copian. `workspace.local.json` no cambia: el pre-commit de la instancia lee esa ruta absoluta.
- **S6** (I74, un resumen que no cambia en cada corrida). **Decisión de diseño, conservadora:**
  - el doctor (su skill y el paso del bootstrap que lo corre) muestra la tabla tal cual en un bloque de código, y comenta solo cada FALTA y AVISO, en una línea cada uno;
  - el cierre del bootstrap («Lo que sigue») es un texto fijo por perfil, escrito en el skill, que el modelo pega tal cual.
  - Se valida con dos corridas reales seguidas del bootstrap en una carpeta temporal: la estructura de la respuesta tiene que salir igual.
- **S7** (I68, el registro). Todo el texto del producto que lee el usuario o el agente pasa a tuteo neutro: los skills y sus references, los mensajes de los scripts (incluidos los de los hosts y del shim), y las tres líneas de `Doc/diseno.md`. Las plantillas ya están en tuteo.
  - **Decisión de diseño:** se hace a mano, no con un reemplazo masivo, porque los skills mezclan formas de voseo con clíticos que ya son de tuteo («Déjalo»). Va al final, para que el texto nuevo de S1 a S6 ya nazca en tuteo.
  - Un test nuevo falla si vuelve a aparecer una forma de voseo en `plugin/` o en `Doc/`, con una lista de formas y una lista de excepciones (`esté`, `caché`, `así`…). Así un cambio futuro escrito en voseo se detecta solo.
  - **Fuera de alcance:** `odd/` (notas internas) y las secciones viejas del `CHANGELOG`.
- **S8** (nada se rompe). Cada comando existente que comparte el código que se toca conserva su comportamiento: `ticket.py --cobertura` (salvo la separación de S2), el triaje, `doctor.py --arreglar`, `reglas.py --calibrar`, las firmas de `chequear_*` y `diagnosticar`, y el orden de sus ids. Las instancias que ya existen no tienen que editar nada. Se actualizan la ayuda de los comandos tocados, `Doc/uso.md`, `Doc/capas-y-reglas.md`, el README si cambia algo que muestra, y el `CHANGELOG` con la `0.13.0`.
- **S9** (la prueba real). El verificador arma una instancia con la `0.13.0` en una carpeta temporal, sobre un repo TypeScript de ejemplo, y comprueba con salidas literales:
  - el doctor da `0 FALTA, 0 AVISO`, con los grupos de S4 y la ruta de S5;
  - una regla de chequeo sin calibrar avisa con un comando que, copiado tal cual y corrido desde la raíz de la instancia, calibra (exit 0);
  - `ticket.py --cobertura` y el triaje dan lo mismo que la `0.12.1` sobre el mismo diff, salvo lo que pide S2.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento, su espejo en engram y las ideas I73 e I74 en el roadmap | inline | en curso | |
| T1 | S1 | La propuesta del bootstrap con «Lo que decides» al final | delegada a un writer (respaldo de contexto del orquestador), en paralelo con T2 y T3 (superficies disjuntas) | pendiente | |
| T2 | S3 | El comando de calibrar que se corre tal cual | delegada, en paralelo con T1 y T3 | pendiente | |
| T3 | S4, S5 | El doctor en grupos y `plugin-root` relativa al home | delegada, en paralelo con T1 y T2 | pendiente | |
| T4 | S2 | La cobertura con archivos esperados, en el doctor y en `ticket.py --cobertura` | delegada, después de T3 (comparten `doctor.py` y sus tests) | pendiente | |
| T5 | S6 | El resumen fijo del doctor y el cierre fijo del bootstrap | delegada, después de T1, T3 y T4 (comparten los dos skills) | pendiente | |
| T6 | S7 | El tuteo en todo el producto y el test que lo cuida | delegada, al final | pendiente | |
| T7 | S8, S9 | Los docs, el CHANGELOG, el verificador independiente y su único lote de corrección | inline, con el verificador delegado | pendiente | |

## Log

- **L1** (2026-11-21) El autor, tal cual:
  - al ver las ideas I66 a I72: «Tambien esto puede servir, si notas que toca hacer mejoras, como autocritico para que lo anotes en el roadmap de ideas diferentes criterios como experiencia de usuario o otros»;
  - el pedido: «Sabes hagamos las mejoras primeros y publicamos un nueva version y volvemos a grabar seria buena idea, para que quede bien el video».
- **L2** (2026-11-21) El criterio, tal cual. Ante la pregunta de la I68 (A: todas las skills a tuteo; B: solo bootstrap y doctor), el autor respondió «Como quieras», y enseguida: «Ah pero tomate tu tiempo si tu decision es por tiempo no deberia ser criterio el criterio es que quede bien». Por eso la I68 va completa (S7) y la I49 queda fuera: no cambia nada de lo que muestra el video.
- **L3** (2026-11-21) Los mapas de dos exploradores de solo lectura sobre la `0.12.1`:
  - **El voseo:** unas 300 líneas de producto en 29 archivos (unas 190 en 17 skills y references, unas 115 en 12 scripts, 3 en `Doc/diseno.md`) y unas 60 en 21 archivos de tests. Las plantillas ya están en tuteo. El riesgo está en los tests de `bootstrap` (unas 14 frases repetidas en cuatro archivos, una usada como separador en `bootstrap.tests.py:1554`), en `memorias.tests.py:839-846` y en `recibo.tests.py:1598,1643`, que leen frases de los skills. `recibo.py` y `reglas.py` escriben sin tildes.
  - **I66:** el perfil es la última fila de la tabla del paso 3 (`skills/bootstrap/SKILL.md:56`); el flujo de la propuesta es solo del skill; `bootstrap.tests.py:2329` fija la estructura del paso 3.
  - **I67:** `doctor.py:269-286` y `config_loader.py:494-514`; `AYUDA_COBERTURA` lo comparten el doctor, `ticket.py:288-297` y `triaje.py:488`; el triaje cuenta por su cuenta (`triaje.py:478-541`).
  - **I69:** el `<carpeta>` literal sale de `calibracion._carpeta` (`odd_ws/calibracion.py:232-238`) cuando no hay regla calibrada; ningún script conoce la ruta del plugin salvo por `__file__`; unos 11 asserts fijan la cadena (`calibracion.tests.py`, `revisar_turno.tests.py:304`).
  - **I72:** `doctor.py:778-819`; no hay modo JSON; `doctor.tests.py:907-957` fija el orden de los ids, y `bootstrap_e2e.tests.py:22-28` y `bootstrap_instalacion.tests.py:192` llaman a `chequear_*`.
  - **I73:** `doctor.py:195,233-237`; `workspace.local.json` y el pre-commit dependen de la ruta absoluta.
  - **I74:** hoy el modelo reformula la salida del doctor y del bootstrap en cada corrida; un texto fijo gana consistencia y pierde la explicación de cada aviso, por eso S6 deja un comentario por FALTA o AVISO.
- **L4** (2026-11-21) Las tomas de la `0.12.1` del video, en `D:/dev-cache/instalar-odd-ws/tomas/` (`TOMAS.md` y `fin-aparte-pantalla.txt`): la propuesta se imprime entera y la terminal solo muestra su final (la fila del perfil queda fuera); el doctor da `0 FALTA, 1 AVISO` por `.json` y `.gitignore`, 9 de sus 20 filas son de la máquina, y `plugin-root` muestra el usuario de Windows; el aviso de calibrar trae `<carpeta>` literal. La sesión del estudio sumó dos ideas: la ruta de `plugin-root` (I73) y el resumen determinista (I74).
- **L5** (2026-11-21) El diseño de S1 a S7 se le presentó al autor, con la diferencia de S4 respecto de la idea (el resumen al final). El autor: «Dale, avanza con el documento de la feature».
- **L6** (2026-11-21) Rutas. Por el respaldo de contexto del orquestador (la sesión ya es larga), las unidades van a writers, cada uno en su worktree con superficies explícitas; el orquestador es dueño de git y commitea cada unidad, de a un pre-commit por vez. `Doc/uso.md`, el README y el CHANGELOG son de T7, para que ninguna unidad paralela los comparta. Estimado: unas 900 líneas en total (casi la mitad, S7); el tope de unas 400 por tarea es solo una guía.
