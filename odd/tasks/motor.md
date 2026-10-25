# T7: extraer el motor al plugin

Objetivo: portar el motor del proyecto de origen al plugin `odd-ws` por unidades chicas, cada una con sus pruebas, reescrita contra `config_loader` y pasando por el barrido. Rama: `feat/motor` (se crea al arrancar la primera unidad). Runner: Python sin pytest, `<nombre>.tests.py` junto a cada script.
El mapa detallado, con la evidencia del proyecto de origen, vive en el cuaderno local, **fuera del repo**: se lee, nunca se copia (el barrido bloquea sus términos). Espejo en Engram: `odd/motor/tasks`.

## Specs

- **S1** — Plan aprobado (fundación, L17 y doctor, L5): «extraer el motor: primer toque, writers con compuerta, triaje y recibo. Es lo más valioso y lo más grande. Va por partes, y cada una pasa por el barrido.»
- **S2** — Cada unidad respeta el diseño (`Doc/diseno.md`): tres niveles de P1 (motor y biblioteca en el plugin; reglas de dominio en la instancia), raíz de la instancia por P3, estado por tipo de P5, plazo junto a su timeout de P6.
- **S3** — Test primero en cada unidad. Las suites del proyecto de origen son la especificación de comportamiento, pero sus datos se reescriben **sintéticos**: ningún literal del dominio entra al repo.
- **S4** — Chequeo diferencial por unidad: las mismas entradas pasan por la pieza original y por la portada, y cualquier diferencia que nadie pidió es una regresión.
- **S5** — Commits por unidad en `feat/motor`; push solo con autorización explícita.

## Reglas transversales (del mapa, 2026-10-24)

- **R-1 Raíz.** En el origen, diez piezas calculan la raíz subiendo directorios desde su propio archivo. En un plugin ese archivo vive en la caché: **toda** pieza obtiene la raíz con `config_loader.encontrar_raiz`.
- **R-2 Importación.** Hoy la cadena va por `importlib` y nombres de archivo hermanos con guion. P1(a) exige que la instancia importe la biblioteca del plugin: hay que decidir el mecanismo (`sys.path` desde `CLAUDE_PLUGIN_ROOT`, paquete con nombre estable) y su versionado **en U0**, antes de portar nada que dependa de él.
- **R-3 Clasificación.** La detección de capa del origen tiene lógica de dominio embebida que `config_loader.clasificar` todavía no cubre: worktrees con un patrón de nombre, una extensión que solo cuenta bajo una carpeta (los `.xml` de recursos), y la forma del nombre del taller (carpeta de ticket con un hijo directo y un prefijo de esquema). Se resuelve en la config, en forma genérica, antes de U3. Abierto: si alcanza con `fnmatch` o el config tiene que aceptar una regex.
- **R-4 Plazos.** El `writer-stop` del origen llama a la verificación **sin plazo** (timeout 60 s; la verificación del AST puede gastar ~20 s por archivo), y el guard de comandos no tiene timeout. En el plugin, todo hook lleva `--plazo` (P6), y la prueba que cruza plazo y timeout lee `hooks/hooks.json`.
- **R-5 Codificación y fallas.** El stderr de bloqueo sale en bytes UTF-8 (`print` saldría en cp1252); el JSON del helper de AST va a un archivo sin BOM; los `.sql` son CRLF sin BOM. Todas las piezas fallan abiertas, **salvo** la capa 2 del guard de comandos, que falla cerrada (pregunta): un guard que lanza sale con 1, y eso cuenta como permitir.
- **R-6 Estado.** El aviso de trabajo parqueado del origen guarda descargos con autoridad en `.claude/estado/` (ignorado): si su idea se porta, va a `.claude/registro/` (P5).
- **R-7 Nombres.** El `doctor.py` del plugin (Capa 0, la máquina) y el doctor de conocimiento del origen son conceptos distintos: mantener nombres separados.

## Tasks

| ID | Unidad | Nivel | Ruta | Riesgo (lista de alto riesgo) | Estado |
|---|---|---|---|---|---|
| U0 | `comun.py`: entorno de git (`diff.autoRefreshIndex=false` por proceso), validación de IDs, decodificación, salida UTF-8 en bytes, raíz vía `config_loader`. Hoy está triplicado. **Incluye la decisión R-2** | motor | inline | ninguno | pendiente |
| U1 | `recibo.py`: recibo atado al sha256 del diff (formato v1) | motor | inline | ninguno | pendiente |
| U2 | Validador de la matriz y `partir_bloque` (sin el modo de cobertura del origen) | motor | inline | 3 (contrato con el dispatcher) | pendiente |
| U3 | Dispatcher: contexto, filtro de preexistentes, `--plazo`, `verificar_archivo`. **U3b:** primer toque. Antes, cerrar R-3 | motor | inline | 6 si las suites no cubren el primer toque | pendiente |
| U4 | Biblioteca T-SQL: limpieza de comentarios y literales, helper de AST, chequeos genéricos (SQL dinámico), normalizador | biblioteca | inline | ninguno | pendiente |
| U5 | El chequeo SQL del origen reescrito como **cliente** de U4, en una instancia de prueba. Es la prueba de aceptación de P1(a) | dominio (instancia) | inline | ninguno | pendiente |
| U6 | `writer-guard`, después `writer-stop` (con plazo propio, R-4), la plantilla única de writer y el contrato `## Resultado` | motor | inline | **2** (guard) → verificador independiente | pendiente |
| U7 | `triaje.py`: los marcadores, los clones y la rama base pasan a la instancia o a la config | motor + dominio | inline | ninguno | pendiente |
| U8 | Guard de comandos (PowerShell). Va tarde: mayor riesgo de regresión, y `writer-guard` ya cubre a los writers. Se decide si se reescribe en Python | motor | inline | **2** (guard) → verificador independiente | pendiente |
| U9 | Salud del workspace recortada (casi todo era paridad entre carpetas de ticket, que el plugin elimina), dentro de `/odd-ws:doctor` | motor | inline | ninguno | pendiente |
| U10 | Bibliotecas C# y Java/Android: solo con un segundo consumidor real | biblioteca | — | — | en espera |
| U11 | `eval-reviewers` (medir reviewers contra revisiones reales) | motor | inline | ninguno | pendiente |
| U12 | Doctor de conocimiento, en 3 cortes: chequeos genéricos de documentos, motor de afirmaciones, cruce | motor parcial | inline | ninguno | pendiente |

**No se portan** (se documentan como ideas cuando valga la pena): el ritual de publicación con su auditoría de ramas, el aviso de trabajo parqueado, el aviso de SP del repo del equipo, el espejo del dispositivo (retirado), transcripción y redacción de mensajes, la matriz de reglas del origen y sus fixtures sembrados.

Ruta: todo inline salvo que el disparador de writer lo justifique (unidades paralelas e independientes de varios minutos cada una, o el respaldo de contexto). U4 y U6 podrían ir en paralelo con superficies disjuntas.

## Log

- **L1 (2026-10-24, Sebastián):** «Si quieres preparemos todo, y arrancamos en una sesion, y me dejas el prompt».
- **L2 (2026-10-24): mapa del motor.** Un explorador (solo lectura, Sonnet, ~236 mil tokens) recorrió las piezas del origen. Tamaños aproximados: dispatcher 584 líneas (suite de 1389), chequeo SQL 696 (1011), helper de AST 232 (304), chequeos C# 494 y Android 433, `writer-guard` 957 (921), `writer-stop` 447 (898), guard de comandos 678 (896), salud del workspace 463 (658), triaje 778 (716), recibo 426 (771), validador de la matriz 616 (1376), doctor de conocimiento 2359 (2902), `eval-reviewers` 1811 en 4 scripts. Acoplamiento al origen por pieza: de ~2 (recibo) a 100+ (ritual de publicación). **Control del padre:** R-4 verificado en el código del origen: el `writer-stop` llama a la verificación sin argumento de plazo. El mapa completo, con citas `ruta:línea`, está en el cuaderno local.
