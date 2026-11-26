# Actualizar sin miedo: el doctor no solo dice qué plantillas quedaron viejas, ayuda a fusionarlas, y avisa cuando lo que se carga siempre crece de más (R21)

Objetivo: que fusionar una plantilla editada sea un diff exacto y una propuesta de 3 vías y no una lectura a mano (I96), que el doctor avise cuando lo que se carga entero pasa de un tope (I95), y cerrar los seguimientos de la `0.14.0` y dos de costo y uso.
Rama: `feat/actualizar-sin-miedo`, en `D:/Project/odd-ws-wt/actualizar`. Está apilada sobre la punta de la R20 (la `0.18.0` sin publicar): lo que la R20 sume después se integra hacia acá con un merge. Entrega: un commit por unidad. Sale en la `0.19.0`, sin publicar: publicar lleva el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py`, `python plugin/plantillas/*.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites, con el `GIT_INDEX_FILE` del commit en el entorno.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap o en el plan. Lo marcado como **decisión de diseño** lo decidió el orquestador con la autonomía del loop (L1), y queda a ratificar por el autor.

- **S1** (I96, la fusión asistida). «Una fusión asistida para las copias editadas de las plantillas, que lleva I85 un paso más allá. Primero muestra el diff exacto de la plantilla entre la versión de tu copia y la actual, y después propone la fusión de 3 vías.»
  - **Decisión de diseño:**
    - **El historial.** `plugin/plantillas/historial/<hex>` guarda el texto de cada plantilla de cada versión publicada, en su forma: LF, sin BOM y con `{{nombre}}` sin renderizar. El nombre de cada archivo es el sha256 de su contenido, el mismo hash que ya está en `huellas.json`, así que cada archivo se verifica solo. Son 14 textos, unos 82 KB, más el pre-commit de la R20.
    - **Quién lo escribe y quién lo revisa.** Lo escribe `tools/huellas.py`, que ya lee los blobs de cada etiqueta en un solo `cat-file --batch`. Solo suma archivos, nunca borra. El pre-push de `tools/entrega.py` exige que cada hash de la tabla tenga su archivo y que el archivo dé ese hash. Ese chequeo no necesita etiquetas.
    - **El comando.** Un script nuevo, `plugin/scripts/fusionar_plantillas.py`:
      - `--diff <ruta>`, de solo lectura, muestra el diff de la plantilla entre la versión de la copia y la actual, las dos renderizadas con el nombre de la copia (`difflib`);
      - `--fusionar <ruta>` hace la fusión de 3 vías con `git merge-file -p`, con temporales reales, porque en Windows no acepta `/dev/null` ni la entrada estándar;
        - si sale limpia, la muestra, y con `--escribir` la escribe con `archivos.reemplazar`;
        - si choca, muestra solo los bloques en conflicto y nunca escribe marcadores en un archivo que se carga.
    - **Dónde se usa.** La skill del doctor (`skills/doctor/SKILL.md:61`, «Ofrece fusionar las editadas primero») lo usa: muestra el diff, propone la fusión y escribe con el sí del usuario. El doctor sigue de solo lectura.
    - **El chequeo de voseo.** `registro.tests.py` no barre `historial/`, porque son textos publicados que no cambian.
- **S2** (I95, el tope de lo que se carga entero). «El doctor avisa cuando un archivo que se carga entero pasa de un tope: el `CLAUDE.md` de la instancia, el núcleo de una skill o el `CLAUDE.md` de un ticket, cuya bitácora crece. Primero solo observa.»
  - **Decisión de diseño:**
    - **El ítem.** Un ítem nuevo del doctor, solo AVISO y sin arreglo, que mide bytes y no líneas. Por eso no repite el chequeo de `conocimiento` (`index_max_lines`, que cuenta líneas del índice). Los topes:
      - `CLAUDE.md` de la instancia: 16 KiB;
      - `CLAUDE.md` de cada ticket activo (`entregas.activos`): 32 KiB;
      - cada `SKILL.md` de `.claude/skills/` de la instancia: 17 KiB, como el núcleo de `revisar`.
    - Sin config por ahora: primero observa.
- **S3** (los seguimientos de la `0.14.0`). Del plan: «Actualizar sin miedo … con los seguimientos de la `0.14.0` (la versión deducida de una instancia sin clave y A3 a A6)».
  - **Decisión de diseño:**
    - **W2.** `Revision` suma `hasta`, el máximo de las versiones comunes. El doctor dice «de la X a la Y» cuando difieren, y la lógica sigue con el mínimo, que es el lado seguro.
    - **A3.** Con el historial de S1, una copia se compara contra cada versión renderizada con su nombre. Así, el nombre del proyecto que aparece también en el texto de la plantilla ya no la marca como editada.
    - **A4.** Si el ítem `config` del doctor está en FALTA, `plantillas` sale NO APLICA y `--arreglar plantillas` no escribe.
    - **A5.** `bootstrap.validar_spec` rechaza un `config.plantillas` distinto de la versión del plugin al crear una instancia, como ya rechaza `local.plugin_root`.
    - **A6.** El pre-push y `huellas.py` listan las versiones de la tabla cuya etiqueta local falta:
      - el pre-push frena con «faltan las etiquetas locales X: corre `git fetch --tags`»;
      - `huellas.py` sale con 2 en lugar de borrar entradas.
- **S4** (el costo del triaje). Del plan: «agrupar por repo los git de `verificar_capa.armar_ctx` (unos 250 ms por archivo en el triaje)».
  - **Decisión de diseño.**
    - `verificar_archivo` y `armar_ctx` aceptan un `previo` opcional con lo que el triaje ya sabe (la raíz, la ruta relativa, si es nuevo y el diff). Con `None`, el hook sigue igual.
    - El triaje hace un solo `git diff -U0 <base>` por repo, partido por archivo, y lee los contenidos con un solo `cat-file --batch`.
    - Los archivos del taller siguen por el camino de hoy.
- **S5** (la fatiga de `quitado`). Del plan: «un atajo en lote para `quitado` en `cerrar`».
  - **Decisión de diseño.** Solo en `cerrar/references/quitado.md`, porque al núcleo de `cerrar` le quedan 10 bytes:
    1. se numera la lista;
    2. se pregunta una vez cuáles no pueden volver («números, o "ninguno"»), como en `enlaces`;
    3. se pide el porqué solo de los elegidos.
- **S7** (la huella del recibo por lotes). El autor: «Vale, sigue con el loop, ten los en cuenta para corregir esos 2 puntos», sobre los dos hallazgos de T3 (L4).
  - `recibo.calcular` corre 3 procesos de git por archivo (`cat-file -e`, `ls-files --error-unmatch` y el diff con `--binary`): son unos 150 de los 169 del triaje con 50 archivos.
  - **Decisión de diseño:** agruparlos por repo, con una restricción dura: la huella sale idéntica, byte a byte, para el mismo diff, así que los recibos que ya existen siguen valiendo. Lo prueba una diferencial de `recibo.py` (la huella calculada y `--check`) contra la base.
- **S8** (el pathspec literal). Del mismo pedido: el diff y el `ls-files` por archivo de `armar_ctx` no usan `--literal-pathspecs`, así que para `x/[ab].sql` el diff trae también los hunks de `x/a.sql`. El defecto ya estaba en la base.
  - **Decisión de diseño:**
    - esas llamadas leen la ruta como literal;
    - la salida del hook cambia solo para una ruta con comodines o con magia de pathspec, que es lo correcto;
    - con eso sobra el camino archivo por archivo que el triaje dejó para esas rutas (L4), y se quita.
- **S6** (la versión). Se actualizan:
  - el CHANGELOG de la `0.19.0`;
  - `Doc/actualizar.md`;
  - la versión en los dos `plugin.json` y en `package.json`, el README y `Doc/`;
  - `tools/huellas.py` y el historial.

  Después, un verificador independiente. Publicar lleva el ok del autor.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento y su espejo en engram | inline | hecha | |
| T1 | S1, S3 (W2, A3, A6) | El historial, `fusionar_plantillas.py` y los seguimientos que tocan las huellas y las plantillas | un writer, en paralelo con T3 (motivo: dos unidades independientes con superficies disjuntas, de varios minutos cada una) | hecha (L3) | `caf81df` |
| T3 | S4, S5 | El triaje sin un git por archivo y el atajo de `quitado` | un writer, en paralelo con T1 | hecha (L4) | `be1e7b7` |
| T2 | S2, S3 (A4, A5) | El tope de lo que se carga y los seguimientos del doctor y el bootstrap | un writer, después de T1, porque los dos tocan `doctor.py` | hecha (L6) | |
| T5 | S7, S8 | La huella del recibo por lotes y el pathspec literal | un writer, en paralelo con T2 (motivo: superficies disjuntas, de varios minutos cada una) | en curso | |
| T4 | S6 | El CHANGELOG, la versión y el verificador | docs inline; verificador delegado | pendiente | |

## Log

- **L1** (2026-11-26) El autor:
  - aprobó el plan de la R20 a la R22: «Sí, va ese orden»;
  - dejó el loop a criterio del orquestador: «Vale, te dejare trabajando en loop termina con las publicacion y las version tu te organizas trabaja como te deje ayer».
  - Los candidatos de costo y uso (S4, S5) salen de la revisión de Gemini que el autor pidió anotar y verificar: «solo para tenerlo en cuenta y verificarlo o anotarlo».
- **L2** (2026-11-26) El mapa del explorador, sobre la R20 en curso (engram `odd/actualizar-sin-miedo/mapa`).
  - **S1:**
    - Se reusan `plantillas_instancia`: `copias`, `huella`, `forma_de_la_plantilla`, `renderizar`, `nombre_de` y `revisar`.
    - El historial suma 14 textos y unos 82 KB.
    - `git merge-file` funciona fuera de un repo, pero pide temporales reales.
    - La skill del doctor ya tiene el paso de fusionar a mano (`skills/doctor/SKILL.md:61`).
  - **S2:** el único tope que existe hoy es el de líneas del índice (`conocimiento.chequear_tope_del_indice`).
  - **S3:**
    - W2 sale de `doctor.py:389-394` y `plantillas_instancia.py:151`;
    - A3, de `plantillas_instancia.py:127`;
    - A4, de que `revisar` no valida `sin_capa`;
    - A5, de `bootstrap.py:244-248`;
    - A6, de `entrega.py:352-371` y `huellas.py:36-42`.
    - La A7 ya la cerró la R20.
  - **S4:** `armar_ctx` (`verificar_capa.py:128-171`) corre `rev-parse`, `ls-files`, `cat-file -e` y `diff` por archivo, cuando `triaje.recolectar_repo` (`:228-276`) ya sabe todo eso.
  - **S5:** la pregunta por ítem está en `cerrar/references/quitado.md:24-30`.
  - **Las trampas:**
    - los núcleos de `cerrar` y `revisar` casi llenos;
    - la plantilla del pre-commit en ASCII y con LF;
    - el tuteo;
    - el barrido de la lista negra;
    - `.gitattributes` con `eol=lf`.
- **L3** (2026-11-26) T1, un writer, desde `7823093`. Cubrió S1 y, de S3, W2, A3 y A6.
  - **El historial:** 15 textos, 82.561 bytes. Cada uno da el sha256 de su nombre, sin CR ni BOM.
  - **`fusionar_plantillas.py`:**
    - `--diff`, con `difflib`;
    - `--fusionar`, con `git merge-file -p` sobre temporales;
    - `--escribir`, atómico y nunca a través de un enlace;
    - con conflictos, solo los bloques, sin escribir nada.
    - Sale con 0, con la cantidad de conflictos o con 255 por un error. Respeta el `merge.conflictStyle` del usuario.
    - La skill del doctor lo usa.
  - **W2:** «de la X a la Y».
  - **A3:** la copia del `CLAUDE.md` se compara renderizando cada texto del historial con su nombre, sin camino de respaldo.
  - **A6:** `huellas.py` y el pre-push salen con 2 si a una versión de la tabla le falta su etiqueta local, con «corre `git fetch --tags`».
  - **El pre-push** exige además el historial completo.
  - **`registro.tests.py`** no barre `historial/`.
  - **Decisiones del writer que se aceptan:**
    - A3 sin respaldo: si falta un texto del historial, esa versión no se reconoce y la copia cuenta como editada;
    - `Revision` suma también `revisadas`;
    - `huellas.py` reescribe un archivo del historial que no da su nombre, y avisa en una segunda línea cuando escribió;
    - A6 toma como «vino de una etiqueta» a toda versión de la tabla que no es la del `plugin.json` del commit;
    - quedan en el historial los textos intermedios sin publicar, porque solo suma.
  - **Las pruebas,** cada regla vista en RED y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `fusionar_plantillas` 5/5, `plantillas_instancia` 11/11 y `doctor` 245/245;
    - `registro` 8/8, `huellas` 5/5, `entrega` 45/45 y `bootstrap` 212/212.
  - **La diferencial contra `7823093`:**
    - el ítem `plantillas` da lo mismo en las instancias nueva, vieja sin tocar y editada;
    - solo cambian los casos buscados: W2, y A3 con un texto publicado real;
    - `tools/entrega.py` da lo mismo en 5 casos.
  - **El orquestador integró el texto de T1 en `Doc/diseno.md`.**
  - **Risk: ítems 3 y 5.** Cambian el contrato de la entrega y los campos de `Revision`, y el pre-push frena por el historial y por las etiquetas.
  - **Scratch del writer:** `%TEMP%\t1-actualizar.P5O1Dv`. Va a la limpieza del autor.
- **L4** (2026-11-26) T3, un writer, desde `7823093`. Lo cortó el límite de 5 horas y se lo retomó con su contexto. Cubrió S4 y S5.
  - **S4:**
    - `armar_ctx` y `verificar_archivo` aceptan un `previo` y, con él, no corren git. Con `None`, el hook sigue igual;
    - el triaje hace, por repo, un `diff -U0 --no-textconv`, un `cat-file --batch` y el diff con la forma del hook (`diffs_por_archivo`), porque un `textconv` cambia los hunks;
    - los prefijos van fijos y los submódulos con `--submodule=short`, para que la config del usuario no rompa el corte.
    - Con 50 archivos de una capa, el triaje pasó de 25,6 s a 9,7 s, y de 466 a 169 procesos de git.
  - **S5:** la referencia de `quitado` numera la lista y pregunta una sola vez cuáles no pueden volver («números, o "ninguno"»).
  - **Las pruebas,** cada regla vista en RED y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `verificar_capa` 164/164, `triaje` 114/114, `revisar_turno` 34/34 y `recibo` 116/116;
    - `quitado` 28/28, `memorias` 43/43 y `registro` 8/8.
    - Dos mutantes, atrapados.
  - **La diferencial contra `7823093`:** 52 de 52 comparaciones idénticas, entre el triaje y el hook en los tres hosts.
  - **Decisiones del writer que se aceptan:**
    - dos diffs por repo, por el `textconv`;
    - el camino archivo por archivo para el taller, las rutas con comodines o con `:` al principio y los estados raros;
    - el aislamiento de la config de git en `triaje.tests.py`.
  - **Dos hallazgos, que el autor pidió corregir en esta versión:** «Vale, sigue con el loop, ten los en cuenta para corregir esos 2 puntos».
    1. **La huella del recibo.** `recibo.calcular` corre 3 procesos de git por archivo, unos 150 de los 169. Se agrupa por repo sin cambiar la huella: los recibos que ya existen siguen valiendo.
    2. **Un defecto que ya estaba en la base.** El diff y el `ls-files` por archivo de `armar_ctx` no usan `--literal-pathspecs`, así que `x/[ab].sql` mezcla los hunks de `x/a.sql`. Arreglarlo cambia la salida del hook solo para esas rutas, que es lo correcto. Con eso sobra el camino aparte para las rutas con comodines.
  - **El orquestador integró el texto de T3 en `Doc/diseno.md`.**
  - **Risk: ítem 3.** `armar_ctx` y `verificar_archivo` los comparten los hooks, `revisar_turno` y `writer_stop`. Con `previo=None` no cambian.
  - **Scratch del writer:** `%TEMP%\t3-actualizar-5ytzfd`, más `triaje-plantilla-0slr59gv` y `triaje-test-i2sqwn4y`. Va a la limpieza del autor.
- **L5** (2026-11-26) T3 quedó en `be1e7b7`. El autor pidió sumar los dos hallazgos de T3 a esta versión: son S7 y S8, en una tarea nueva, T5. T2 y T5 corren en paralelo: T2 toca el doctor y el bootstrap, y T5 toca `recibo`, `armar_ctx` y el triaje.
- **L6** (2026-11-26) T2, un writer, desde `be1e7b7`, en paralelo con T5. Cubrió S2 y, de S3, A4 y A5.
  - **S2:** el ítem nuevo `carga-entera` va después de `desviaciones`. Es AVISO sin arreglo y mide bytes: el `CLAUDE.md` raíz (16 KiB), el de cada ticket activo (32 KiB) y cada `SKILL.md` de la instancia (17 KiB). Con el tope justo, OK.
  - **A4:** con el ítem `config` en FALTA, `plantillas` sale NO APLICA y `--arreglar plantillas` no escribe. Antes, con un `sin_capa` inválido, el arreglo reescribía la config rota.
  - **A5:** al crear la instancia, `validar_spec` rechaza un `config.plantillas` distinto de la versión del plugin. Va al final, así que lo que la base ya rechazaba conserva su mensaje.
  - **Las pruebas,** cada regla vista en RED y después GREEN, en el entorno normal y con un `GIT_INDEX_FILE` ajeno:
    - `doctor` 251/251, `bootstrap` 214/214 y `bootstrap_cli` 19/19;
    - `plantillas_instancia` 11/11 y `registro` 8/8.
  - **La diferencial contra `be1e7b7`:** solo cambian la línea nueva, A4 y A5. Los códigos de salida son iguales, salvo A5.
  - **Decisiones del writer que se aceptan:**
    - AVISO solo si un archivo pasa estrictamente su tope;
    - el peso es el del disco, con CRLF y BOM;
    - solo se miden los `SKILL.md` de `.claude/skills/` de la instancia;
    - A4 se arregla solo en el doctor, sin tocar `revisar` ni el aviso del inicio.
  - **El orquestador integró el texto de T2 en `Doc/diseno.md`.**
  - **Risk: none.** Cambia lo que el bootstrap acepta y el doctor suma una fila, pero las dos cosas se pidieron y ningún helper compartido cambió.
  - **Scratch del writer:** `%TEMP%\t2-actualizar.p91xPQ`. Va a la limpieza del autor.
