# Que se vea lo que hoy pasa callado: la falla de un hook, los hooks de un repo, las plantillas viejas, las extensiones sin capa a propósito y dos defectos de plantilla (R15)

Objetivo: que el doctor y el inicio de sesión muestren lo que hoy pasa en silencio (I2, I36, I85 e I87) y cerrar dos defectos de las plantillas de la instancia (I88 e I89).
Rama: `feat/fallas-calladas`, en `D:/Project/odd-ws-wt/fallas`, desde `origin/main` (`0b44438`). Los writers trabajan en sus propios worktrees desde `origin/main` y el orquestador integra sus ramas con `--no-ff`. Entrega: un commit por unidad. Sale en la `0.14.0`, con el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap.
- Lo marcado como **decisión de diseño** no lo pidió el autor con esas palabras: es cómo se cumple su pedido.
- Lo marcado como **supuesto** está por confirmar.

- **S1** (I2, la falla de un hook). «Que la falla de un hook quede a la vista: se anota en `.claude/estado` y el doctor o la sesión siguiente la muestra.» El porqué, del roadmap: «Una falla de la infraestructura nunca se vuelve una respuesta».
  - **Decisión de diseño:** los hooks siguen fallando abiertos, y ningún guard cambia su veredicto. Lo nuevo es el rastro.
    - Cada excepción que hoy se tragan `correr()` de cada hook y `comun.correr_hook` se anota en un archivo de `.claude/estado/`: el hook, el evento, la fecha y el tipo y mensaje de la excepción. Nunca el payload del evento. El archivo tiene un tope de entradas.
    - La sesión siguiente la muestra una vez, por `verificar_capa._session_start`.
    - El doctor suma un ítem con las últimas fallas, en AVISO, y `--arreglar` lo vacía.
  - **Supuesto:** las capturas silenciosas internas, como `revisar_turno.py:223,306`, `writer_guard.py:1406,1455,1479` y `writer_stop.py:171,223,277,293`, son degradaciones previstas y no se anotan. Solo se anota lo que llega al `except` de `correr()` o de `correr_hook`.
- **S2** (I36, los hooks propios de un repo). «`abrir` y el doctor avisan cuando un repo trae hooks propios en su `.claude/settings.json`, porque no corren si la sesión arranca en la instancia.» El porqué: «El guard y el formateador del repo no corrieron en toda una sesión desde la raíz».
  - **Decisión de diseño:**
    - Una sola función compartida, como en I67, lista los repos de la config cuyo `.claude/settings.json` o `.claude/settings.local.json` declaran `hooks`.
    - `ticket.py --cobertura`, el paso 8 de `abrir`, imprime un `aviso` con su `cómo:`: esos hooks corren solo si la sesión arranca en el repo.
    - El doctor suma un ítem en AVISO.
    - Un archivo que no se puede leer, o que no trae `hooks`, no avisa.
- **S3** (I87, sin capa a propósito). «Las extensiones que van sin capa a propósito, como imágenes, recursos o archivos de build, se reconocen una vez y el AVISO de `capas-cobertura` se apaga.»
  - **Decisión de diseño:**
    - Una clave opcional `sin_capa` en `workspace.config.json`: una lista de extensiones con su punto.
    - Se valida con el par `sin_capa_de(config)` / `sin_capa(raiz)`, como `hooks_apagados`, y se registra en `bootstrap._cargar_en_temporal` y en `doctor.chequear_config`.
    - Las extensiones listadas pasan a las esperadas, que salen en OK con su nota, en el doctor, en `ticket.py --cobertura` y en el triaje.
    - El `cómo:` del AVISO muestra la línea exacta de la clave con las extensiones del aviso, para que el usuario saque las que sí son código. No hay `--arreglar`, porque reconocer todo de una vez taparía código sin capa.
- **S4** (I85, las plantillas viejas). «El doctor avisa cuando una plantilla copiada a la instancia quedó en una versión vieja, y la primera sesión después de actualizar dice qué copiar.» Las plantillas copiadas son el `CLAUDE.md` raíz, `tickets/_plantilla/CLAUDE.md`, `.githooks/pre-commit` y `.claude/reglas/verificar_<capa>.tests.py`. **Decisión de diseño:** pendiente de la pregunta al autor (L2).
- **S5** (I88, el `__pycache__`). «Correr las pruebas de reglas copiadas a la instancia no deja `__pycache__`.»
  - `verificar.tests.py` y `pre-commit.tests.py` ponen `sys.dont_write_bytecode = True` antes de cargar nada.
  - `verificar.py` no lo necesita, porque lo carga su prueba con el flag ya puesto.
  - Una prueba corre la plantilla copiada en un temporal y comprueba que no queda `__pycache__`.
- **S6** (I89, el `/compact`). «El `CLAUDE.md` de la instancia dice una sola cosa sobre lo que vuelve después de un `/compact`.»
  - Lo correcto, del roadmap: «el `CLAUDE.md` del ticket no vuelve entero, pero el ticket activo vuelve como resumen (I13)».
  - Lleva su entrada en `Doc/actualizar.md`.
- **S7** (la versión). Se actualizan:
  - el CHANGELOG de la `0.14.0`;
  - `Doc/actualizar.md`, con las plantillas que cambian en la `0.14.0`;
  - la versión en `plugin/.claude-plugin/plugin.json`, `plugin/.codex-plugin/plugin.json`, `package.json`, el README, `Doc/` y la página.

  Después, un verificador independiente revisa toda la feature. Publicar lleva el ok del autor.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento, su espejo en engram y la cola del roadmap con el orden nuevo | inline | hecha | (con T1) |
| T1 | S5, S6 | El `__pycache__` y el `/compact` | inline (unidad chica) | hecha (L3) | |
| T2 | S1 | La falla de un hook a la vista | delegada: writer A en `D:/Project/odd-ws-wt/fallas-hooks`, en paralelo con T3 (motivo: el respaldo de contexto del orquestador y dos unidades independientes de más de 100 líneas; comparten `doctor.py`, `doctor.tests.py` y el SKILL del doctor, que integra el orquestador) | en curso | |
| T3 | S2, S3 | Los hooks de un repo y las extensiones sin capa | delegada: writer B en `D:/Project/odd-ws-wt/fallas-cobertura`, en paralelo con T2 | en curso | |
| T4 | S4 | Las plantillas viejas | delegada tras la decisión de L2 y la integración de T2 y T3 | pendiente | |
| T5 | S7 | El CHANGELOG, la versión, el verificador independiente y publicar con el ok del autor | docs inline; verificador delegado | pendiente | |

## Log

- **L1** (2026-11-24) El autor, tal cual, en orden:
  - «Debemos retomar y empezar con lo nuestro reorganizar que ideas van a salair y que versiones como para volver a organizar y deberiamos empezar».
  - A la propuesta, aceptó este orden:
    - `0.14.0`: I2, I36, I85, I87, I88 e I89.
    - `0.15.0`: I47, I35, I92 e I86.
    - `0.16.0`: I90 e I91.
    - `0.17.0`: I83 e I84.
    - Los estudios de I80 con I63 y de I78 con I79 van en paralelo.

    Su respuesta: «Si, va ese orden, arranca con la 0.14.0».
- **L2** (2026-11-24) El mapa del explorador:
  - El plugin instalado no trae etiquetas ni historia de git: la fuente del marketplace es `./plugin`. Las huellas por versión tienen que viajar como datos bajo `plugin/`, generadas al publicar.
  - Una cabecera en `verificar*.py` choca con `bootstrap_reglas.tests.py:158-162`, que prohíbe comentarios.
  - La I85 queda pendiente de una pregunta al autor sobre su diseño.
- **L3** (2026-11-24) T1, hecha inline.
  - **S5:**
    - RED con `test_correr_a_mano_la_suite_copiada_de_la_plantilla_no_deja_pycache` (`reglas.tests.py`). Dejaba `verificar_sql.cpython-314.pyc`.
    - GREEN con `sys.dont_write_bytecode = True` al principio de `verificar.tests.py`, igual que en los scripts del plugin.
    - `pre-commit.tests.py` lleva el mismo flag por consistencia. No hay RED posible ahí, porque no carga ningún módulo local.
  - **S6:**
    - RED con `test_la_raiz_dice_una_sola_cosa_sobre_lo_que_vuelve_tras_compactar` (`bootstrap_textos.tests.py`).
    - GREEN con la línea 14-16 de `plantillas/CLAUDE.md`: «tras `/compact` no vuelve entero: del ticket activo vuelve un resumen».
  - **Suites:** `reglas` 56/56, `bootstrap_reglas` 22/22, `pre-commit.tests` 16/16, `bootstrap_textos` 34/34, `bootstrap` 208/208.
  - La entrada de `Doc/actualizar.md` para la `0.14.0` va con T5.
- **L4** (2026-11-24) El autor, tal cual: «Como yo te dejare trabajando en loop todo el dia, por si llegas el limite deberias poder seguir trabajando apenas se renicie el limite de 5h».
  - Queda un cron de la sesión que retoma desde este documento cada 30 minutos.
  - Fuera de su alcance quedan el push a `main`, la etiqueta y la publicación.
  - **Sobre S4:** se le preguntó al autor por el diseño de la I85. Si no responde, se sigue con la opción recomendada, marcada como «a ratificar»:
    - la instancia anota con qué versión quedaron sus plantillas;
    - el plugin trae las huellas por versión;
    - `--arreglar` reemplaza las copias sin tocar y, después de fusionar las editadas, anota la versión nueva.
