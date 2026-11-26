# Que la entrega no se pierda: el aviso de lo que quedó sin subir y la auditoría de ramas antes de publicar (R19)

Objetivo: que el trabajo que quedó sin subir vuelva solo al arrancar la sesión (I83), y que antes de publicar un comando de solo lectura muestre qué ramas de los tickets no llegaron (I84).
Rama: `feat/entrega-no-se-pierde`, en `D:/Project/odd-ws-wt/entrega`. Está apilada sobre la punta de R18 (`3aff040`, la `0.16.0` sin publicar): si R15, R16 o R18 cambian, se integran hacia acá con un merge. Va un agente por vez (L1). Entrega: un commit por unidad. Sale en la `0.17.0`, con el ok del autor.
Pruebas: `python plugin/scripts/<script>.tests.py` y `python tools/<herramienta>.tests.py` (en Linux y macOS, `python3`), y `node --test plugin/shim/*.test.ts`. El pre-commit corre todas las suites, con el `GIT_INDEX_FILE` del commit en el entorno.

## Specs

El origen es el plan que aprobó el autor (L1). Cada Spec cita el texto de su idea en el roadmap.
- Lo marcado como **decisión de diseño** lo decidió el orquestador con la autonomía de la jornada (L1), y queda a ratificar por el autor y su auditor.
- El diseño de las dos ideas sale del flujo a medida del que nació odd-ws, como dice el roadmap.

- **S1** (I83, lo que quedó sin subir vuelve solo). «Lo que quedó sin subir vuelve solo: el hook de inicio de sesión avisa de cada ticket con la entrega pendiente hasta que se confirme que llegó, y calla cuando no hay nada.» Del roadmap: «solo refs locales y sin `fetch`, para que sea rápido y funcione sin red; silencio total si no hay pendientes, porque un hook que habla siempre se ignora; y una huella de los archivos al confirmar, para que un cambio posterior vuelva a preguntar».
  - **Decisión de diseño:**
    - **Qué es una entrega pendiente.** Por cada ticket de la instancia y cada repo de su «Worktree y rama» (sin tickets archivados), cuenta como pendiente:
      - un cambio sin commitear en la carpeta que tiene esa rama;
      - un commit de la rama que no está en su `refs/remotes/origin/<rama>`;
      - una rama que nunca se empujó, porque no tiene `origin/<rama>`.
      
      Solo con las refs locales, sin `fetch`.
    - **Dónde avisa.** En `verificar_capa._session_start`, aislado como los demás avisos del inicio. Una línea por ticket pendiente: el ticket, el repo, la rama y qué le falta. Si no hay nada, calla del todo.
    - **Cómo se confirma.** Un script nuevo, `entregas.py`, con `--confirmar <ticket>`, anota en `.claude/estado/entregas.json` una huella del estado de ese ticket: las cabezas de sus ramas y la huella de sus archivos sin commitear.
      - Mientras la huella no cambie, ese ticket calla.
      - Un cambio posterior vuelve a avisar.
      - Sin argumentos, el mismo script lista lo pendiente.
    - **El tiempo.** El plazo del inicio de sesión no cambia, el tope es de 20 tickets, y todo git corre con el entorno limpio. Si se vence el plazo, el aviso lo dice en una línea y no se cuenta como limpio.
  - **Decisión de diseño (sumada en L3, después del mapa del explorador):**
    - **Qué ramas tiene un ticket.** «Worktree y rama» es prosa libre, sin clave de repo, así que git es la fuente de verdad y la prosa solo nombra:
      - de esa línea y sus viñetas se toman los fragmentos entre backticks;
      - un fragmento que es una carpeta de un repo de la config (`config_loader.repo_de`) da ese repo y la rama que esa carpeta tiene en `HEAD`;
      - cualquier otro fragmento es un candidato a rama: cuenta en cada repo de la config que tenga `refs/heads/<fragmento>`, y la carpeta es la del repo o la del worktree que tiene esa rama;
      - un ticket sin nada reconocible no tiene nada que chequear y calla.
    - **Qué ticket está archivado.** Cuenta solo un hijo directo de `tickets/` (`tickets/<id>-<slug>/CLAUDE.md`), sin `_plantilla`. Uno más hondo, como `tickets/archivo/2025/…`, está archivado.
    - **Cuándo avisa.** Con los mismos orígenes que el aviso de la config rota (`ORIGENES_DEL_AVISO`: startup, resume y fork), no en cada `compact`.
    - **Dónde va.** Un `str|None` más en el inicio, después de las fallas anotadas y antes del resumen del ticket, que sigue al final. Se protege con su propio try/except, porque una excepción que escapa deja mudo todo el inicio.
    - **El plazo.** La biblioteca `odd_ws/entregas.py` recibe un límite, como `porque.hasta`, y la usan el hook y el CLI. La línea de «no alcanzó el tiempo» sale solo si había algo que chequear.
- **S2** (I84, la auditoría de ramas antes de publicar). «Una auditoría de ramas antes de publicar: un comando de solo lectura que hace `fetch` en cada repo de la config y lista las ramas de los tickets con cambios sin commitear, commits sin empujar o trabajo que no llegó a la rama principal.» Del roadmap: «diagnostica y no opera, sin ningún verbo que escriba; si el `fetch` de un repo falla, ese repo sale en rojo en vez de seguir con datos viejos; y la clasificación de cada rama es una función pura que se prueba con datos sintéticos». Y el caso para sembrar: «un push a una rama cuyo PR ya se mergeó sale bien, no corre CI y el commit nunca llega a la rama principal».
  - **Decisión de diseño:**
    - **El comando.** Un script nuevo, `auditar_ramas.py`, que hace `fetch` de cada repo de la config, con el entorno limpio y un plazo por repo. El `fetch` actualiza solo las refs remotas: no toca ramas ni archivos.
      - Si el `fetch` de un repo falla, ese repo sale en rojo y no se juzga con datos viejos.
      - Para cada rama de los tickets: cambios sin commitear, commits sin empujar, y trabajo que no llegó a la rama principal del repo (`origin/HEAD`, y si no hay, `main` o `master`).
      - Para no confundir un squash con trabajo perdido, se comparan los parches con `git cherry`.
    - **El caso sembrado.** Una rama con commits nuevos después de que su trabajo anterior ya llegó a la rama principal sale como «trabajo que no llegó», aunque esté empujada.
    - **La clasificación.** Es una función pura, `clasificar_rama(datos) -> estado`, probada con datos sintéticos que incluyen el caso sembrado.
    - **La salida.** Una línea por ticket y repo, un resumen al final y `--json`. Sale con:
      - 0 si todo llegó;
      - 1 si hay algo pendiente o algún repo en rojo;
      - 2 por un error de uso.
    - **Dónde se usa.** El paso de la entrega de `cerrar` la nombra en su referencia, y `Doc/uso.md` la documenta. No se crea una skill nueva.
- **S3** (la versión). Se actualizan:
  - el CHANGELOG de la `0.17.0`;
  - `Doc/actualizar.md`, si cambia alguna plantilla;
  - la versión en los dos `plugin.json` y en `package.json`, el README y `Doc/`;
  - `tools/huellas.py`.

  Después, un verificador independiente. Publicar lleva el ok del autor y su auditor.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento y su espejo en engram | inline | hecha | `83237a3` |
| T1 | S1 | El aviso de lo que quedó sin subir | un explorador corto (L3) y después un solo writer (motivo: el respaldo de contexto del orquestador) | hecha (L4) | `7ae8339` |
| T1b | S1 | La latencia del aviso: los `git status` en paralelo, con un pool acotado, y otra medición (L5, L6) | un writer, después de T2 (motivo: el respaldo de contexto del orquestador) | pendiente | |
| T2 | S2 | La auditoría de ramas | un writer (motivo: el respaldo de contexto del orquestador) | hecha (L7) | este commit |
| T3 | S3 | El CHANGELOG, la versión, el verificador y publicar con el ok del autor | docs inline; verificador delegado | pendiente | |

## Log

- **L1** (2026-11-24 y 2026-11-25) El autor:
  - aceptó el orden de las versiones, con la `0.17.0` = I83 e I84: «Si, va ese orden, arranca con la 0.14.0»;
  - dejó la jornada a criterio del orquestador: «Apartir de ahora te dejo a tu criterio, probablemente antes de sacar la version enviare un auditor, asi que tu sigue trabajando el resto de versiones solo dejalas listas que mañana miramos en que quedamos ya te dejo libremente espero que nada que interrumpa»;
  - pidió, solo para ese loop: «intenta trabajar con menos agentes paso a paso solo lo necesario»;
  - y al volver: «Sigue con la 0.16.0 y la 0.17.0», y después «Dale, cerrá primero la 0.16.0 y después la 0.17.0».
- **L2** (2026-11-25) R18 cerró en `3aff040`, y la rama avanzó hasta ahí sin merge, porque no tenía commits propios.
  - Lo que sale de R18 para esta feature:
    - todo git sobre un repo de la config usa el entorno limpio (`comun.entorno_git()` o `recibo._entorno()`), porque el pre-commit corre las suites con `GIT_INDEX_FILE`;
    - las pruebas y los ejemplos usan nombres genéricos, porque el barrido de la lista negra frena el commit.
  - Sigue T1: un explorador corto y después un solo writer.
- **L3** (2026-11-25) T0 quedó en `83237a3`. El mapa del explorador, sobre `3aff040`:
  - **Lo que no existe y hay que construir:**
    - un lector de «Worktree y rama», que es prosa libre (`plugin/plantillas/ticket.md:35`);
    - la noción de ticket archivado: `ticket._recorrer` recorre todo, archivados incluidos;
    - el cálculo de commits sin empujar o de una rama nunca empujada (lo más cercano: `tools/barrido.py:144` y `revisar_turno._estado`);
    - una escritura atómica compartida: se calca `fallas._reemplazar`.
  - **El inicio de sesión** (`verificar_capa.py:687-703`) une avisos `str|None`. El resumen del ticket va último (pruebas 1374 y 1701), y la prueba 1701 pide que no salga ninguna línea de tiempo si no había nada que chequear.
  - **La latencia.** El inicio tiene `--plazo 8` en los tres hosts, y un `git status` cuesta de 145 a 225 ms. Por eso, un `for-each-ref` por repo y un `status` solo en las carpetas que tienen una rama de un ticket.
  - **Los límites.** El núcleo de `cerrar` tiene 10 bytes libres, así que `entregas.py` se nombra en `references/entrega.md`. Todo texto en español va en tú (`registro.tests.py`).
  - Las decisiones que el mapa obligó a tomar están en S1, «sumada en L3».
- **L4** (2026-11-25) El autor dejó la R19 en pausa: «Dejalo que termine su T1». T1, un writer, desde `83237a3`, cubrió S1 con los dos bloques de diseño. Queda **sin commitear** hasta que el autor retome el loop.
  - **Lo nuevo:**
    - `odd_ws/entregas.py` y su CLI `entregas.py`, cada uno con su prueba;
    - el aviso en `verificar_capa._session_start`;
    - `capas.py`;
    - los docs: `Doc/diseno.md`, `Doc/hooks.md`, `Doc/uso.md` y `cerrar/references/entrega.md`.
  - **Las pruebas:**
    - 26 pruebas escritas antes del código, vistas en RED;
    - 13 mutantes, todos atrapados;
    - las 62 suites de Python en verde, también con un `GIT_INDEX_FILE` ajeno, y el shim en 97/97.
  - **La diferencial contra `83237a3`:** 3 hosts, todos los orígenes y 3 instancias (sin tickets, ticket entregado, ticket entregado y activo). 45 corridas, 0 diferencias.
  - **Decisiones del writer, a ratificar:**
    - `--confirmar` acepta la carpeta o un id que sea prefijo de un solo ticket activo.
    - Un fragmento cuenta como carpeta solo si es absoluto. Las rutas UNC se saltan.
    - La huella es un sha256 por rama: el repo, la rama, su cabeza, la de `origin`, la carpeta, el `status -z -uall` y el contenido de cada archivo nombrado (más de 2 MB entra por tamaño y fecha).
    - El plazo del hook es `min(4 s, lo que le queda)`.
    - Las salidas del CLI son 0, 1 y 2.
    - En `compact` y `clear` no corre git.
  - **Para decidir al retomar:**
    - **La latencia del inicio de sesión.** Con 20 tickets de 1 worktree, pasa de unos 0,31 s a 2 a 2,9 s. Con 2 worktrees, a 3,9 a 4,3 s, y el plazo de 4 s corta 5 tickets. Cada `git status` cuesta unos 80 ms, en serie. Paralelizar los `status` la bajaría, pero suma el ítem 4 de riesgo (concurrencia).
    - **Una rama recién abierta sin commits ni `origin` cuenta como «nunca se empujó».** Cada ticket nuevo avisa hasta su primer push o una confirmación.
    - **Con más de 20 tickets activos,** la línea «sin revisar» sale en cada inicio.
  - **Scratch del writer**, todo en `%TEMP%`: `tmp.AxfvAp9kZX`, `tmp.MgCJmfO2ES`, `tmp.U4sxVcbXxA`, `tmp.iXWTe0G7hR` y `tmp.sHCkT4mSGd`. Va a la limpieza del autor.
- **L5** (2026-11-25) Una segunda opinión externa (Gemini) sobre la latencia, que el autor pidió anotar y verificar: «solo para tenerlo en cuenta y verificarlo o anotarlo».
  - **Lo que propone:** correr los `git status` en paralelo con `--no-optional-locks`, en un pool de unos 4 hilos y sin repetir la misma carpeta. Estima menos de 0,6 s con 20 tickets.
  - **La verificación:**
    - el choque por `.git/index.lock` ya no puede pasar: `comun.entorno_git()` pone `GIT_OPTIONAL_LOCKS=0`, que equivale a `--no-optional-locks`;
    - el riesgo de concurrencia que queda es de código: hilos, el plazo compartido y lanzar procesos en Windows;
    - la cifra de 0,6 s es una estimación sin medir.
  - **Para el writer al retomar:**
    - paralelizar con un pool acotado;
    - repetir una carpeta solo si es la misma ruta física;
    - repartir el plazo entre los hilos;
    - medir otra vez con 20 tickets de 1 y de 2 worktrees.
    - Evaluar también si `-uall` hace falta, porque recorrer todo lo que no está trackeado es lo caro en un repo grande.
- **L6** (2026-11-25) El autor retomó el loop: «Vale, te dejare trabajando en loop termina con las publicacion y las version tu te organizas trabaja como te deje ayer».
  - **T1 quedó en `7ae8339`.**
  - **La `0.16.0` entró con un merge limpio** (`b4f8a16`, desde `225113f`), y `huellas.py` deja el árbol igual.
  - **Dos writers, uno después del otro.** Los dos tocan `odd_ws/entregas.py`: T2 expone el lector de las ramas de un ticket y T1b cambia cómo corren los `status`, así que no van en paralelo.
    - **T1b, la latencia de S1:** paraleliza los `git status`, mide otra vez y evalúa `-uall` (L5).
    - **T2, S2:** reusa de `odd_ws/entregas.py` el lector de las ramas de un ticket, para que el aviso y la auditoría digan lo mismo.
    - Primero T2, que es la grande, y después T1b, sobre lo que T2 deje.
- **L7** (2026-11-25) T2, un writer, desde `b4f8a16`. Cubrió S2.
  - **Lo nuevo:** `odd_ws/auditoria_de_ramas.py`, con la función pura `clasificar_rama` y su prueba, y `auditar_ramas.py`, con la suya.
  - **En `entregas.py`,** una sola función pública que suma y no cambia nada: `entregas_de(config, tickets, limite)`. Reusa el lector de las ramas de un ticket con un solo `_Revisor`, que lee las refs una vez por repo. `_Revisor` queda igual.
  - **Docs:** `Doc/diseno.md:1205`, `Doc/uso.md` y `cerrar/references/entrega.md`, que dice que se corre con el sí del usuario porque habla con cada remoto.
  - **Las pruebas:**
    - 28 pruebas vistas en RED y 13 mutantes, todos atrapados;
    - `auditar_ramas` 16/16, `auditoria_de_ramas` 13/13, `entregas` 14/14 y 6/6, `verificar_capa` 157/157, `registro` 7/7 y `memorias` 43/43, también con un `GIT_INDEX_FILE` ajeno.
  - **La diferencial contra `b4f8a16`:** el inicio de sesión y `entregas.py`, en 14 corridas, dan 0 diferencias.
  - **Decisiones del writer, a ratificar:**
    - **El fetch es `git fetch --quiet --no-tags --no-prune --no-recurse-submodules --no-write-fetch-head origin +refs/heads/*:refs/remotes/origin/*`,** sin gc ni mantenimiento automático y sin pedir credenciales.
      - Escribe solo `refs/remotes/origin/*`, y no crea `origin/HEAD`, así que la rama principal sale de `main` o `master`.
      - Pide git 2.29 o más: con uno más viejo, cada repo sale en rojo.
    - **Un squash de varios commits:** `git cherry` solo lo toma como perdido, así que se compara además el `patch-id` del diff entero de la rama desde su merge-base. En ese caso, la cuenta de lo que no llegó es un tope.
    - **Lo que se juzga contra la rama principal:** sin empujar y nunca empujada solo cuentan si hay trabajo fuera de la rama principal. Una rama nueva sin commits propios cuenta como llegada.
    - **La cabeza remota también se juzga,** y eso atrapa el caso sembrado empujado desde otra máquina.
    - **Un ticket sin ramas reconocibles** no tiene línea; `--json` lo lista en `tickets_sin_ramas`.
    - **Los plazos:** 60 s por fetch, por la resolución y por repo. Lo que se vence sale en rojo o «sin juzgar», con salida 1.
    - **El `status` es propio de la auditoría,** así que T1b no lo cambia sin querer. Si T1b deja `-uall`, hay que decidir si la auditoría lo sigue.
  - **Risk: ítem 1.** El comando corre `git fetch` en cada repo de la config, también en los del equipo, y escribe `refs/remotes/origin/*`. Lo fija una prueba que compara, antes y después, las refs que no son de `origin`, el índice, `HEAD`, la config, `FETCH_HEAD` y los árboles. Lo revisa el verificador de la versión.
  - **Scratch del writer**, todo en `%TEMP%`:
    - `tmp.lhRKm25HGL`, `tmp.zg3wIH4yRd`, `tmp.Pjlk38cEAQ`, `tmp.mluQGsqfgT`, `tmp.m2ZIPx5xd5` y `tmp.lamo0vVoyh`;
    - los `odd-t2-*.txt`;
    - 16 carpetas `auditar-ramas-*` y `auditar-ramas-plantilla-lajc7ftk`;
    - `recibo-test-ahb2u6k5`.

    Va a la limpieza del autor.
