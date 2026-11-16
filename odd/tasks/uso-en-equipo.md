# Guía de uso en equipo

Objetivo: documentar cómo trabaja un equipo con una instancia compartida por git, sin nube, con cada paso probado antes en dos clones de una instancia de prueba. Rama: `docs/uso-en-equipo`, desde `origin/main` (`088caf4`). Entrega: un commit por unidad en la rama; push de la rama con destino explícito; `main` y etiquetas solo con autorización. Runner: Python sin pytest, `python <x>.tests.py`. Espejo en Engram: `odd/uso-en-equipo/tasks`.

## Specs

- **S0, el marco (decidido).** «Hoy ni el README ni Doc/uso.md dicen cómo trabaja un equipo con una instancia compartida. La idea, ya decidida: sin nube; las convenciones viajan en el repo de la instancia (matriz.csv, verificar_<capa>.py y las skills de capa), y workspace.local.json queda fuera, en el .gitignore.»
- **S1.** «qué hace cada dev al clonar la instancia: su workspace.local.json, el doctor y la instalación del plugin;»
- **S2.** «quién gradúa las reglas con /odd-ws:cerrar y cómo se revisa la matriz en un PR;»
- **S3.** «cómo encaja engram cloud: comparte las memorias del equipo, cerrar las gradúa a reglas, y las reglas viajan por git.»
- **S4, la prueba.** «Pruébalo con dos clones de una instancia de prueba, en una carpeta del scratch, antes de documentar. No supongas nada que no probaste.»
- **S5, la corrección (aprobada en L7).** `cerrar memorias` anota en el `origen` el `sync_id` de engram (`memoria:engram-<sync_id>`), que es el mismo en todas las máquinas, en lugar del id numérico, que es local. Si un resultado no trae `sync_id`, usa el id numérico y avisa que solo se reconoce en esa máquina. Una fila anterior, con el id numérico, se sigue reconociendo.
- **Riesgo:** ninguno en la guía (documentación pasiva). T2 cambia el formato del `origen` que `cerrar memorias` persiste en la matriz (ítem 1).

## Tasks

| ID | Specs | Qué | Ruta | Estado |
|---|---|---|---|---|
| P | S4 | Prueba con dos clones en el scratch: instalación, bootstrap, clon, doctor, graduación en ramas paralelas, primer toque tras el pull y engram entre dos almacenes | inline | hecho (L2-L6) |
| T1 | S0-S3 | `Doc/equipo.md` con lo probado, enlazada desde el README, `Doc/uso.md` y la estructura de CONTRIBUTING | inline: documentación, sin razón de writer | hecho (L10) |
| T2 | S3, S5 | `cerrar memorias` anota el `sync_id` de engram en el `origen`, porque el id numérico es local de cada máquina (L6): la skill, `Doc/uso.md` y una prueba de `matriz.py` que fija que ese origen es válido | inline: un cambio entendido | hecho: `161be57` (L8, L9) |
| V | S5 | Un verificador independiente sobre T2 | delegado (ítem 1) | hecho: S5 cumple, sin blockers (L9) |
| F1 | S2 | Seguimiento: el pre-commit de la instancia no valida la matriz; una unión a ciegas de dos filas pasa en verde (L5) | aparte | anotado |
| F2 | S1 | Seguimiento: en un clon, el bootstrap en modo completar no pide las rutas de los repos y el ítem `config` del doctor no tiene arreglo: la ruta se escribe a mano (L3) | aparte | anotado |

## Log

- **L1 (2026-11-16), el pedido.** Textual:
  > ## La tarea: guía de uso en equipo
  > Hoy ni el README ni Doc/uso.md dicen cómo trabaja un equipo con una instancia compartida. La idea, ya decidida: sin nube; las convenciones viajan en el repo de la instancia (matriz.csv, verificar_<capa>.py y las skills de capa), y workspace.local.json queda fuera, en el .gitignore. La guía tiene que cubrir:
  > - qué hace cada dev al clonar la instancia: su workspace.local.json, el doctor y la instalación del plugin;
  > - quién gradúa las reglas con /odd-ws:cerrar y cómo se revisa la matriz en un PR;
  > - cómo encaja engram cloud: comparte las memorias del equipo, cerrar las gradúa a reglas, y las reglas viajan por git.
  > Es trabajo ODD grande: crea odd/tasks/uso-en-equipo.md con su espejo en engram (odd/uso-en-equipo/tasks). Pruébalo con dos clones de una instancia de prueba, en una carpeta del scratch, antes de documentar. No supongas nada que no probaste.
- **L2 (2026-11-16), el escenario.** En `<scratch>/equipo`: un remoto bare (`origen.git`), un repo de código con un clon por dev, git aislado (`GIT_CONFIG_GLOBAL` y `GIT_CONFIG_SYSTEM` al scratch, `GIT_CONFIG_NOSYSTEM=1`) y un `CLAUDE_CONFIG_DIR` por dev, para que cada uno sea una máquina nueva. Plugin 0.6.2 desde el marketplace de GitHub, Claude Code 2.1.319.
  - **Dev A:** `marketplace add` + `install --scope project` en la carpeta vacía deja `.claude/settings.json` con solo `enabledPlugins`; el marketplace queda en los settings de usuario (`extraKnownMarketplaces`), y el registro de la instalación guarda la ruta del proyecto (`installed_plugins.json`, `projectPath`). El bootstrap crea `.gitignore` con `workspace.local.json` y `.claude/estado/`, respeta el `settings.json` que ya existía, hace `git init` y pone `core.hooksPath`. El primer commit corre el pre-commit (`reglas.py --test`, 3/3) y se empuja.
- **L3 (2026-11-16), el clon del dev B** (carpeta con otro nombre). Recién clonado: sin `core.hooksPath` y sin `workspace.local.json`. Los mismos dos comandos de instalación, en su clon, dejan el árbol limpio (`settings.json` ya traía el `enabledPlugins`). El doctor da 3 FALTA: `plugin-root` y `instancia-hooks`, con arreglo, y `config` («falta la ruta del repo 'app' en workspace.local.json»), sin arreglo. `--arreglar plugin-root` crea `workspace.local.json` solo con `plugin_root`; la ruta del repo se agrega a mano (`repos.app.path`); `--arreglar instancia-hooks` pone `core.hooksPath`. Después: 0 FALTA y el árbol limpio.
- **L4 (2026-11-16), graduar en paralelo.** Cada dev, en su rama desde el mismo `main`, emula lo que escribe `cerrar` (la fila con el script de su paso 5, la regla en el bloque no-negociables y la evidencia): los dos sacan `SQ-01`, `matriz.py --destinos` y `--severidad` dan 0 fallas en cada rama y el pre-commit pasa. Mergeado el PR de B, el de A choca en `matriz.csv`, `capa-sql/SKILL.md` y `evidencia.md`. Rehacer la graduación de A sobre el `main` nuevo da `SQ-02`, 0 fallas, y el merge entra limpio.
- **L5 (2026-11-16), lo que frena una mala unión.** Resolver el choque uniendo las dos filas a ciegas (`git merge-file --union`) deja dos `SQ-01`: el pre-commit pasa en verde, porque solo corre `reglas.py --test`, y `matriz.py --destinos --capa sql` sale con 1 («id duplicado 'SQ-01'» y «aparece 2 veces» en el bloque). En un PR, la matriz se revisa con `matriz.py`.
- **L6 (2026-11-16), engram.**
  - **El proyecto:** `mem_current_project` en los dos clones (carpetas `instancia` y `mi-copia`) devuelve el mismo proyecto, `origen`, con fuente `git_remote`.
  - **Los ids:** con dos almacenes aislados (`ENGRAM_DATA_DIR`, 0 observaciones al empezar), B con dos memorias propias, A guarda una del proyecto, la exporta con `engram sync --project origen` y B la importa con `engram sync --import`. La misma memoria es `#1` en A y `#3` en B; su `sync_id` es el mismo en los dos (`obs-d2a572e53ec05212`). Como `cerrar memorias` anota `memoria:engram-<id>`, una memoria que gradúa A vuelve a salir como candidata en B, y un `#N` de B puede ser otra memoria. Probado con la sincronización por chunks de engram; su cloud no se pudo levantar (pide Postgres) y no se probó.
  - **Las reglas por git:** tras el `pull` del dev B, el primer toque simulado (`verificar_capa.py` con un `Edit` de un `.sql` de su repo) le entrega `SQ-01` y `SQ-02`, y el árbol sigue limpio.
- **L7 (2026-11-16), la decisión del usuario.** A la pregunta «¿Corrijo `cerrar memorias` para que anote el `sync_id`, como un commit aparte antes de la guía?», textual:
  > Si corrigelo
- **L8 (2026-11-16), T2 implementado.**
  - **Sin RED en código:** el `origen` lo escribe el modelo siguiendo `cerrar/SKILL.md`, y la regex de `matriz.py` (`memoria:([\w.\-]+)`) ya acepta `engram-obs-<hex>`. La prueba nueva de `matriz.tests.py` (`test_origen_de_engram_con_sync_id`) fija esa dependencia y pasa desde el principio.
  - **RED y GREEN del escenario, en el scratch:** A gradúa la memoria (`#1` en A) con los dos formatos. En B, donde es `#3`, el chequeo actual con su id da `False` (rojo) y el nuevo, con el `sync_id` y su id, da `True` (verde). Una memoria distinta da `False`, y en A la fila con su id numérico se sigue reconociendo (`True`). `matriz.py --destinos` y `--severidad`: 0 fallas con las dos filas; `memorias.py` no avisa por ellas.
  - **El cambio:** M2 de `cerrar/SKILL.md` (el origen, el reconocimiento con los dos argumentos y el límite del id numérico), el candidato de M3 y la línea de engram de `Doc/uso.md`. El CHANGELOG va con la entrega.
  - **Suites:** `matriz` 52/52 y `memorias` 34/34.
- **L9 (2026-11-16), el verificador independiente: S5 cumple, sin blockers.**
  - **La skill:** el origen con `sync_id`, el respaldo numérico con su aviso y el reconocimiento de las filas viejas son coherentes con M3, M4 y el resumen final. `mem_search` devuelve `sync_id` en `results[]` (leído en el código de engram 3.5.1), con la forma `obs-<hex>`, que la regex de `matriz.py` acepta.
  - **El comando de reconocimiento:** con dos argumentos reconoce el `sync_id`, la fila vieja y una pieza en medio de un origen con `;`, y no confunde `engram-12` con `engram-123`. Con un argumento, 11 entradas dan lo mismo que la base, con LF y con CRLF.
  - **`matriz.py` y `memorias.py`:** 52/52 y 34/34; una fila con `memoria:engram-obs-…` da 0 fallas y `memorias.py` no avisa por ella.
  - **Avisos:** A1, M3 no nombraba el respaldo numérico: corregido antes del commit. A2, en otra máquina una fila vieja con id numérico puede tapar otra observación con el mismo número; pasaba igual en la base y la skill lo documenta. A3, el CHANGELOG va con la entrega.
- **L10 (2026-11-16), T1: la guía.** `Doc/equipo.md`, solo con lo probado en L2-L6 y L8: qué viaja y qué no, los pasos al clonar (instalar en el clon, los tres FALTA del doctor y la ruta a mano), quién gradúa y cómo rehacer una graduación que choca, la revisión de la matriz en el pull request con `matriz.py` (y la salida real de una fila duplicada) y el reparto con engram, con la nota de que engram cloud no se probó. Enlazada desde la tabla de documentación del README, la introducción de `Doc/uso.md` y la estructura de CONTRIBUTING. Lectura estructural: 29 enlaces y anclas en los cuatro docs, 0 rotos, con un chequeador que sí detecta un ancla y un archivo rotos en una prueba aparte. Los seguimientos F1 y F2 quedan fuera: la guía documenta el comportamiento actual.
