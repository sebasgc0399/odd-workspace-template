# T8: `/bootstrap`, generar una instancia desde cero

Objetivo: que una instancia del plugin `odd-ws` se genere con `/odd-ws:bootstrap` en lugar de armarse a mano. Rama: `feat/bootstrap`, creada desde `main` (`718bd32`). Entrega: como la T7, con un commit por unidad, push solo con autorización y fast-forward de `main` al cerrar. Runner: Python sin pytest, `<nombre>.tests.py` junto a cada script. Espejo en Engram: `odd/bootstrap/tasks`.

## Specs

- **S1. Alcance aprobado (L1).** La T8 lleva el núcleo:
  - la config;
  - las skills `criterios` y `capa-<capa>`, y el revisor;
  - las reglas vacías;
  - la instalación (`settings.json`, pre-commit y `plugin_root`);
  - una plantilla de `CLAUDE.md` liviana y una de ticket en `tickets/<T>/`, sin tracker;
  - los ítems de instancia del doctor;
  - la skill `/odd-ws:bootstrap`;
  - una prueba de punta a punta.
- **S2. Fuera de la T8 (L1).**
  - Las skills de ciclo de vida (apertura, cierre y `/odd-ws:revisar`) van a una T9.
  - Los moldes sintéticos y las listas `molde`/`no_molde` quedan fuera: se escribe `mold_source`, nada más.
- **S3. Forma (decisión técnica, L1).** Una skill que entrevista y arma una spec en JSON, y un script determinista que genera desde esa spec, como el doctor.
- **S4. Sin pisar nada (decisión técnica, L1).**
  - Sirve tanto para una instancia nueva como para completar una existente.
  - Un archivo que ya existe no se toca, y la salida lo dice.
  - Se verifica contra la instancia de prueba (`D:\Project\odd-instancia-prueba`).
- **S5. Reglas vacías (decisión técnica, L1).** El motor no trae reglas (principio 2), así que:
  - la matriz arranca solo con el encabezado de `matriz.ENCABEZADO`;
  - `verificar_<capa>.py` es un stub con su suite;
  - el `rule_prefix` se deriva de la capa y la entrevista lo confirma.
- **S6. Git (decisión técnica, L1).** Hace `git init` y configura `core.hooksPath` solo si hace falta. El primer commit es del usuario.
- **S7. Los huecos de lo entregado se cierran en la T8 (L1).**
  - El doctor detecta la ruta de un repo que falta en `workspace.local.json`, que hoy deja los hooks mudos.
  - El doctor revisa el `core.hooksPath` y el `enabledPlugins` de la instancia.
  - Una config rota se avisa al arrancar la sesión, como promete P3 en `Doc/diseno.md`. Hoy el matcher de `SessionStart` es solo `compact|clear` y el dispatcher se calla.
- **S8. Reglas transversales de la T7, que siguen vigentes.**
  - Test primero y datos sintéticos: ningún literal del dominio del origen entra al repo, y el barrido lo bloquea.
  - Diferencial y mutaciones con control positivo.
  - Las rutas de la instancia salen de `odd_ws/capas.py` (R-8) y la raíz, de `config_loader` (R-1).
  - La salida va en UTF-8 y los archivos generados, en LF sin BOM (R-5).
  - Una sección opcional de la config se valida en su propia función, nunca dentro de `cargar()`.

## Tasks

| ID | Unidad | S# | Ruta | Riesgo | Estado |
|---|---|---|---|---|---|
| B1 | Formato de la spec (JSON) y motor de generación (plan, aplicación sin pisar, informe, `--ensayo` y registro de generadores), más el núcleo de config: `workspace.config.json`, `workspace.local.json` y `.gitignore`, validados con `config_loader.cargar` sobre una copia en un temporal | S3, S4 | delegado (writer Sonnet, respaldo de contexto del padre, L2) | **1** (la garantía de no pisar archivos del usuario vive acá) → commit propio y verificador independiente | hecho (L3); verificador pendiente |
| B2 | Generador de plantillas genérico (bloques de instancia y huella, a partir de `plantilla_writer`), y las plantillas de `criterios` y `capa-<capa>`: con CENTINELA y el bloque no-negociables, sin `paths:` ni `disable-model-invocation` | S1, S4 | a decidir tras B1 (candidata a writer en paralelo) | ninguno | pendiente |
| B3 | Plantilla de `revisor-<capa>` con el generador de B2 | S1 | con B2 | ninguno | pendiente |
| B4 | Reglas vacías: `matriz.csv` con el encabezado, `evidencia.md`, el stub `verificar_<capa>.py` con su suite y el `rule_prefix` | S1, S5 | a decidir tras B1 | ninguno | pendiente |
| B5 | Instalación: `settings.json` con `enabledPlugins`, el pre-commit con el bit de ejecución, `core.hooksPath`, `git init` y `plugin_root` | S1, S6 | a decidir tras B1 | ninguno | pendiente |
| B6 | Textos: la plantilla de `CLAUDE.md` (menos de 200 líneas, solo metodología genérica) y la del ticket en `tickets/<T>/` | S1 | a decidir tras B1 | ninguno | pendiente |
| B7 | Huecos de lo entregado: ítems de instancia del doctor (rutas locales, `hooksPath`, `enabledPlugins`) y el aviso de config rota al arrancar | S7 | a decidir tras B1 | ninguno | pendiente |
| B8 | La skill `/odd-ws:bootstrap` (entrevista, spec, script y doctor al final) y el cableado de los generadores de B2 a B6 en el registro de B1 | S3, S4 | inline o writer, tras B1–B7 | ninguno, si no cambia el motor de aplicación de B1; si lo cambia, **1** | pendiente |
| B9 | Prueba de punta a punta: una instancia sintética en un temporal y completar la instancia de prueba | S1, S4 | inline | ninguno | pendiente |

## Log

- **L1 (2026-10-30): pedido y alcance.**
  - **Las respuestas del usuario:**
    - a «¿Cierro la T7 (fast-forward de `main` y push) y arranco la exploración de `/bootstrap`?» respondió, literal: «Si prosigue»;
    - a «¿Va la T8 con ese alcance?» respondió: «Si vamos», y después: «Tomare tu recomendacion».
  - **El alcance aprobado** es S1 y S2. Las decisiones técnicas, contadas en la misma propuesta, son S3 a S7.
  - **Mapa:** lo hizo un explorador de solo lectura (~200 mil tokens).
    - Una instancia necesita unos 15 artefactos, y el plugin solo trae plantilla para el writer y el pre-commit.
    - Del plan v0 quedó viejo:
      - los tres modos de gobierno, que reemplazó `mold_source` por capa (hoy solo se valida y no lo usa nadie);
      - el esquema de config del plan;
      - los nombres `<slug>-<capa>-*`;
      - la copia de hooks a la instancia.
    - Encontró tres huecos en lo entregado, que pasan a S7.
  - **Estimación:** entre 2 500 y 3 500 líneas con las pruebas. La estrategia de entrega es la misma que la de la T7, ya aceptada: una rama, un commit por unidad y fast-forward de `main` al cerrar.
- **L2 (2026-10-30): diseño de B1, decisión técnica del padre.**
  - **La spec embebe la config tal cual:** `{"spec_version": 1, "config": <workspace.config.json exacto>, "local": <workspace.local.json sin plugin_root>, …}`, y las unidades siguientes suman sus claves.
    - No hay un segundo esquema: las capas, los repos y `knowledge` salen de `config`.
    - La validación es el mismo `config_loader`, corrido sobre una copia en un temporal **antes** de escribir nada en la instancia.
  - **Plan y aplicación por separado:** el plan lista `(ruta, contenido, modo)` y la aplicación crea cada archivo de forma exclusiva (`open(..., "x")`). Lo que ya existe se informa como «ya existía» y no se toca.
  - **Un `.gitignore` existente tampoco se modifica:** el informe dice qué líneas faltan.
  - **`--ensayo`** muestra el plan sin escribir nada.
  - **Por qué B1 lleva el riesgo 1:** la garantía de no pisar vive en el motor de aplicación.
  - **Ruta:** writer Sonnet, por el respaldo de contexto. El padre lleva una sesión larga (T7 entera más el inicio de la T8).
- **L3 (2026-10-30): B1 hecho, a la espera del verificador independiente.** Lo escribió un writer Sonnet (~175 mil tokens, 12 minutos).
  - **Archivos:** `bootstrap.py` (315 líneas), su suite (50 pruebas) y `plantillas/bootstrap.ejemplo.json`. `capas.py` suma `ESTADO` y `GITIGNORE`.
  - **RED:** solo el módulo inexistente (`ModuleNotFoundError`), no un ROJO por regla. Queda dicho tal cual. **GREEN:** 50/50.
  - **Mutaciones:** 47, con 45 muertas.
    - De las 24 que rompen la garantía de no pisar murieron 22. Por ejemplo: `xb` → `wb`, el plan siempre en `crear`, el `.gitignore` en `ab` o reescrito, la carrera sin manejar, escribir antes de validar y `--ensayo` que escribe.
    - Las 2 vivas son equivalentes: quitar `..` ya lo cubre la regla del segmento que termina en punto, y crear la raíz ya lo hace `makedirs`.
  - **Agregados del writer,** dentro de la garantía:
    - rechaza los enlaces que salen de la raíz, los ancestros que son archivos y los choques entre archivo y carpeta;
    - un error a mitad de la aplicación deja un informe parcial;
    - cada generador puede tener su propio validador;
    - `local.plugin_root` se rechaza.
  - **Desvío:** el writer armó un script con heredoc de Bash, contra la regla.
  - **Docs:** la sección «Bootstrap» de `Doc/diseno.md` y el README.
