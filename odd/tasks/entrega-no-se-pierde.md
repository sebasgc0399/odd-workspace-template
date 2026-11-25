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
| T0 | todas | Este documento y su espejo en engram | inline | hecha | |
| T1 | S1 | El aviso de lo que quedó sin subir | un explorador corto y después un solo writer, cuando R18 cierre | pendiente | |
| T2 | S2 | La auditoría de ramas | un solo writer, después de T1 | pendiente | |
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
