# Instalar solo los controles (I62, R10)

Objetivo: que quien ya usa gentle-ai completo (su orquestación y su RDD) pueda instalar solo los controles de odd-ws: guards, reglas por capa y doctor, sin `revisar`, recibos, tickets ni writers. Absorbe la I5, el interruptor por hook.
Rama: `feat/solo-controles`, en `D:/Project/odd-ws-wt/i62`, desde la `0.11.0`. Entrega: dos unidades con un commit cada una, la I5 (T1) y el perfil (T2); el push y la publicación, solo con autorización del autor.
Pruebas: `python plugin/scripts/<script>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`.

## Specs

Origen: la I62 del roadmap, tal cual: «Instalar solo los controles: guards, reglas por capa y doctor, sin `revisar`, recibos, tickets ni writers.» El diseño sale del mapa del explorador (L2), y el autor lo aprobó tal como se le mostró (L1).

- **S1** (la elección). Una clave opcional `"profile"` en `workspace.config.json`, con los valores `"completo"` y `"controles"`. Sin la clave es `completo`, y todo sigue como hoy, byte a byte. Un valor inválido es config rota para el bootstrap y FALTA en el ítem `config` del doctor. El bootstrap la propone como una fila más de su tabla, en `completo`, y pasa a `controles` si el usuario dice que ya tiene su propia orquestación o revisión, igual que hace con `hosts`.
- **S2** (qué genera `controles`, en los tres hosts). Genera:
  - la config y el `.gitignore`;
  - las reglas por capa y cada `capa-<capa>`, porque de ahí lee `verificar_capa` los no negociables;
  - el pre-commit, `.gitattributes` y `.claude/settings.json`, más `git init` y `core.hooksPath`;
  - `.codex/config.toml`, si se declara Codex.

  No genera los writers, los revisores, `revisor-diseno` ni `criterios`, ni sus derivados de Codex y Pi, ni `tickets/_plantilla`. El filtro va dentro de cada generador, porque el registro de los generadores pasa antes de leer la spec.
- **S3** (el `CLAUDE.md` raíz). En `controles`, una plantilla reducida de unas 45 líneas. Dice qué controla la instancia y cómo nacen las reglas: con `/odd-ws:cerrar` en modo memorias y con la matriz. También dice que `abrir`, `cerrar` en su modo normal, `revisar` y `eval-reviewers` no aplican, porque la revisión es la de tu herramienta, y así no choca con la orquestación de gentle-ai. Lleva una línea de marca, para que el doctor avise si sigue ahí con el perfil `completo`.
- **S4** (el doctor en `controles`).
  - `writers` da un solo NO APLICA, sin proponer crear writers.
  - `rdd` encendido es OK, porque ahí el RDD es tu revisión; apagado es AVISO sin arreglo, porque la instancia queda sin revisión.
  - Los ítems de Pi no hablan de writers.
  - La ayuda de `capas-cobertura` no menciona `revisar`.
  - En `completo`, todo sigue como en la `0.11.0`.
- **S5** (las skills). En una instancia `controles`, `revisar`, `abrir`, `cerrar` en su modo normal y `eval-reviewers` avisan que no aplican y no corren. `cerrar` en modo memorias sigue funcionando: es por donde nacen las reglas sin tickets.
- **S6** (la I5). Una clave opcional `"disabled_hooks"`: una lista con nombres de los cinco scripts de hook (`verificar_capa`, `guard_comandos`, `revisar_turno`, `writer_guard` y `writer_stop`).
  - Cada script la chequea en su decisión, después de cargar la config, en los tres hosts, porque un plugin no puede desregistrar un hook por proyecto.
  - Un valor inválido no apaga nada (falla hacia los controles prendidos) y es FALTA en el ítem `config` del doctor.
  - El doctor suma el ítem `hooks-apagados`: AVISO cuando hay alguno apagado, con su nombre.
  - `controles` no apaga ninguno por defecto.
- **S7** (pasar a completo). Se quita `profile` y se corre `/odd-ws:bootstrap`, que completa lo que falta sin pisar nada. La skill dice que borres antes el `CLAUDE.md` reducido si no lo editaste. Bajar de completo a controles no se soporta en esta versión: los archivos quedan.
- **S8** (las instancias que ya existen). Ninguna cambia si no agrega las claves: la segunda corrida del bootstrap no cambia ningún byte, y sin `profile` ni `disabled_hooks` los hooks y el doctor hacen lo mismo que en la `0.11.0`.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T1 | S6, S8 | La I5: `disabled_hooks` en `config_loader`, en los cinco hooks y en el ítem `hooks-apagados` del doctor | delegada a un writer, por el respaldo de contexto del padre y para avanzar en paralelo con la entrega de la `0.11.0`. Risk: item 2, porque es un interruptor que apaga guards; lleva verificador, al final de la feature | hecha (L3) | `9049346` |
| T2 | S1, S2, S3, S4, S5, S7, S8 | El perfil `controles`: la clave, los generadores, la plantilla reducida, el doctor, las skills y los docs | delegada a un writer, después de T1, porque comparte `config_loader.py` y `doctor.py` | escrita y en verde (L4); el verificador va al final de la feature | |
| T3 | todas | El verificador independiente de la feature y el cierre | inline | pendiente | |

## Log

- **L1** (2026-11-20) El pedido del autor, tal cual: «podriamos plantearnos trabajar en varios worktree para avanzar mas rapido». Aprobó el reparto en frentes con «Si». Después aprobó con «Vale» el diseño de la I62 que se le mostró: la clave `profile`, lo que genera y lo que no, el `CLAUDE.md` corto, el doctor sin writers ni la propuesta de apagar el RDD, las skills que avisan que no aplican, la I5 con `disabled_hooks` y el aviso del doctor, y el paso a completo.
- **L2** (2026-11-20) Mapa del explorador, de solo lectura, sobre la `0.10.1`.
  - Ningún hook depende de tickets, recibos ni de la skill `revisar`. `writer_guard` y `writer_stop` quedan dormidos sin writers.
  - `revisar` puede invocarla el modelo solo: no tiene `disable-model-invocation`.
  - El bootstrap registra los generadores antes de leer la spec (`bootstrap.py:1040-1043` contra `:995`), así que el perfil se filtra dentro de cada `generar`.
  - `config_loader` acepta claves sueltas; las claves opcionales siguen el patrón de `hosts` y `aprobacion_de_commits` (`config_loader.py:280-331`).
  - Estimación: unas 700 líneas, la I5 unas 250 y el perfil unas 450.
  - Decisiones tomadas con las recomendadas: el enum y no booleanos por pieza (P3); los cinco hooks se pueden apagar, con el aviso del doctor (P5); `controles` no apaga `revisar_turno` por defecto (P6); una línea de guarda en las skills que no aplican (P7); se saltea `criterios` (P8); y no se baja de completo a controles (P9).
  - R9, ya en la `0.11.0`, cambió el ítem `rdd`. Por eso la rama parte de la `0.11.0`.
- **L3** (2026-11-20) T1, la I5, escrita por un writer en `i62`. Son +429/−8 en 20 archivos: unas 66 líneas de código, 335 de tests y 32 de docs.
  - **La clave:**
    - `config_loader` suma `HOOKS` (los cinco nombres, fijados por un test contra los tres `hooks*.json`), `hooks_apagados_de` y `hooks_apagados`, con el patrón de `hosts`.
    - El chequeo compartido es `hook_apagado(raiz, nombre)`: ante una config inválida devuelve `False`, así que los controles siguen prendidos.
    - Un hook apagado devuelve `Permitir` antes de tocar el disco.
  - **El doctor:** el ítem `config` valida la clave, y suma `hooks-apagados`: OK sin hooks apagados, AVISO nombrándolos y con el riesgo si uno es `guard_comandos`, y NO APLICA con la clave inválida. El bootstrap rechaza un valor inválido.
  - **Las suites:** `config_loader` 100/100, `verificar_capa` 111/111, `guard_comandos` 79/79, `revisar_turno` 32/32, `writer_guard` 123/123, `writer_stop` 59/59, `doctor` 208/208, `bootstrap` 184/184 y el shim de Pi 68/68. Rojo observado en cada regla. El padre repitió `config_loader`: 100/100.
  - **El diferencial contra `2ef0c3b`:** 15 payloads de hooks, el doctor y dos corridas del bootstrap dan iguales, salvo la línea nueva de `hooks-apagados`.
  - **Decisiones del writer, que el padre acepta:**
    - `hook_apagado` lee solo la clave y `schema_version`, así que un hook apagado sigue callado con el resto de la config roto.
    - `hooks-apagados` va en su propia función, porque `bootstrap_instalacion.tests.py:193` fija los ids de `chequear_instancia`.
    - Cada nombre apaga solo su hook.
    - Una foto de turno pendiente no se toca.
    - Un nombre repetido es inválido, y una lista vacía es válida.
  - **Para T2:** no cambiar el conjunto de ids de `chequear_instancia` sin actualizar ese test. El CHANGELOG y el README van con la entrega.
  - **Scratch del writer, a borrar a mano:** `%TEMP%	mp.Eav07ZDPhh`.
- **L4** (2026-11-20) T2, el perfil `controles`, escrita por un writer en `i62`. Son +638/−36 en 25 archivos, más la plantilla nueva `CLAUDE.controles.md` (47 líneas).
  - **La clave y su lectura:** `config_loader` suma `PERFILES`, `perfil_de`, `perfil` y `es_controles`, este último tolerante: ante una config rota devuelve `False`. Los generadores leen el perfil de la spec, y el doctor y Pi con `es_controles`.
  - **Los generadores:** `agentes` deja solo `capa-<capa>` y les pasa una lista vacía a los adaptadores, así que Codex queda con su `config.toml` y Pi sin nada. `textos` escribe el `CLAUDE.md` reducido, sin la plantilla de tickets, e `instalacion` saltea el `settings.json` de la plantilla.
  - **El doctor:** `writers` es un solo NO APLICA. `rdd` encendido es OK, y apagado o ilegible es AVISO sin arreglo. `capas-cobertura` lleva una ayuda sin `revisar`. El ítem nuevo `perfil` es condicional: aparece solo si la marca `<!-- odd-ws:perfil controles -->` sigue en el `CLAUDE.md` raíz con el perfil `completo`. Los ítems de Pi no hablan de writers.
  - **Las skills:** una línea de guarda en `revisar`, `abrir`, `cerrar` y `eval-reviewers`. El bootstrap suma la fila del perfil y el paso a completo.
  - **Las suites:** `config_loader` 105/105, `bootstrap` 186/186, `bootstrap_agentes` 56/56, `bootstrap_textos` 33/33, `bootstrap_instalacion` 14/14, `bootstrap_reglas` 22/22, `bootstrap_e2e` 29/29, `doctor` 217/217, `pi.tests` 69/69, `codex.tests` 46/46 y el shim 68/68. Rojo observado en cada regla. El padre repitió `config_loader`: 105/105.
  - **El diferencial sin la clave contra `9049346`:** 0 diferencias. El control positivo, con `controles`, da 10.
  - **El chequeo del señuelo:** con `GIT_DIR` apuntando a un repo de prueba, las suites dieron verde y el señuelo quedó intacto. El control positivo lo movió.
  - **Decisiones del writer, que el padre acepta:**
    - Un perfil inválido es FALTA en `config`, y lo demás se comporta como `completo` hasta corregirlo.
    - `gentle-shell` ausente es NO APLICA en `controles`.
    - El bootstrap no pregunta por tickets en `controles`.
    - `AYUDA_RDD_CONTROLES` dice que se encienda con el mismo `--scope` con que se apagó. El padre lo verificó con la ayuda de gentle-ai: `enable` y `disable` aceptan `--scope global|clone`.
  - **El padre sumó** la plantilla nueva a la lista de `CONTRIBUTING.md:70`. El CHANGELOG va con la entrega.
  - **Scratch del writer, a borrar a mano:** `%TEMP%	mp.kcgJLhhq64`, `tmp.kcgJLhhq64-red`, `diferencial-i62-tpmqzacc`, `diferencial-i62-8g4_p6f5`, `tmp.J3gi3eZ5d6` y `tmp.SS3gUehwqe`.
