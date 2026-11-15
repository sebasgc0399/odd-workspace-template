# README: más profesional y con ilustraciones, sin abrumar

Objetivo: rehacer el `README.md` para que llegue a más gente, con ilustraciones y revelando el detalle de a poco. Rama: `docs/readme`, creada desde `origin/main` (`782128a`), sin upstream. Entrega: `ask-on-risk`, un commit por unidad, push de la rama para el CI; push a `main` solo con autorización. Runner: no aplica (documentación); la verificación es estructural (anclas, enlaces, render de Mermaid). Espejo en Engram: `odd/readme/tasks`.

## Specs

- **S1. El pedido (L1).** «deberiamos, mejorar el readme a uno mas profesional vamos a llegar a mas personas con mas ilustracion del proyecto pero si abrumar al usuario toca pensarlo bien».
- **S2. El idioma (L2).** «Dejemoslo en español».
- **S3. Los visuales (L2).** «puedes apoyarte del proyecto de que tengo aca, que es donde hice videos sobre esto, puedes hablar con esta sesion para que trabajen en conjunto». La sesión de video es `odd-ws-video-9c`.
- **S4. La estructura propuesta y aceptada (L1, L2).**
  1. Portada: título, frase, insignias y un GIF de un bloqueo.
  2. Cómo funciona: un diagrama del ciclo, en Mermaid.
  3. Qué te da.
  4. Junto a gentle-ai y engram.
  5. Instalación, con un bloque plegable por CLI.
  6. Dónde funciona, con las notas plegadas.
  7. Documentación y licencia.
- **S5. Sin perder información.** Lo que sale del README queda en `Doc/`. Las anclas `#instalación` y `#dónde-funciona` se conservan, porque `Doc/uso.md` las enlaza.
- **S6. Repo público.** Nada de nombres de la empresa ni del dominio del usuario; ejemplos neutros.

## Tasks

- [x] **T1** (S1, S2, S4-S6), inline: texto del README y el ítem de `${CLAUDE_PLUGIN_ROOT}` movido a `Doc/uso.md`. Hecho (L3); el commit es el primero de la rama.
- [x] **T2** (S3), con la sesión de video: el GIF de la portada y, si suman, imágenes fijas en `Doc/img/`. Hecho (L4): `Doc/img/odd-ws-portada.gif`.
- [x] **T3** (S1-S6), inline: lectura estructural, commit y push de la rama para el CI. Hecho (L5): `main` en `1b3f6e2`.

## Log

- **L1** (2026-11-15): «Ahora que lo pienso deberiamos, mejorar el readme a uno mas profesional vamos a llegar a mas personas con mas ilustracion del proyecto pero si abrumar al usuario toca pensarlo bien». Diagnóstico: el README no tiene ninguna imagen; la instalación en gentle-shell ocupa unas 25 líneas de casos borde que ya están en `Doc/uso.md`; y no responde lo que preguntaron en Discord, si odd-ws choca con engram o gentle-ai. Se propuso la estructura de S4.
- **L2** (2026-11-15): «Dejemoslo en español, puedes apoyarte del proyecto de que tengo aca, que es donde hice videos sobre esto, puedes hablar con esta sesion para que trabajen en conjunto». Se le pidió a `odd-ws-video-9c` el inventario de escenas y una propuesta de GIF. El mensaje quedó retenido hasta que el usuario lo apruebe en esa sesión.
- **L3** (2026-11-15): T1 hecha, en `README.md` y `Doc/uso.md`. El texto conserva las anclas `#instalación` y `#dónde-funciona`. Codex y gentle-shell quedan plegados, Claude Code abierto, y las limitaciones plegadas bajo «Dónde funciona». Lo único de gentle-shell que no estaba en `Doc/` era el ítem de `${CLAUDE_PLUGIN_ROOT}`, que se movió a «Usarlo desde gentle-shell». Lectura estructural con un script del scratch: los enlaces y las anclas de `README.md` y `Doc/*.md` resuelven. 9 líneas del README viejo no están tal cual, y las 9 son paráfrasis cubiertas: 8 por `Doc/uso.md` (líneas 65 y 72-75) o `Doc/actualizar.md` (sección «En gentle-shell (Pi)»), y la del marketplace quedó partida en dos oraciones. Pendiente: ver en GitHub que Mermaid y los `<details>` se dibujan. Risk: none (solo documentación).
- **L4** (2026-11-15): T1 quedó en `1e17e2c`, y la rama se subió a `origin/docs/readme`. En GitHub, la página carga las insignias, el visor de Mermaid y los bloques plegables. Se leyó del árbol de accesibilidad y no se vio el diagrama dibujado: eso lo confirma el usuario. Playwright solo puede escribir en la carpeta de trabajo de la sesión, que aquí es de solo lectura, así que se dejó de usar y se borraron sus dos archivos. El mensaje a `odd-ws-video-9c` venció sin aprobarse, y el usuario pegó el pedido en esa sesión. El cuadro de prueba (1280x640, estilo cuaderno del v6) se aprobó con un cambio: que el GIF se reproduzca una sola vez. El GIF salió de `projects/odd-ws-readme-cover` del estudio. Se verificó leyendo sus bytes: 420 307 bytes, 1280x640, 150 cuadros y sin bloque NETSCAPE2.0, o sea sin repetición. Se copió a `Doc/img/odd-ws-portada.gif` (igual byte a byte) y va en la portada, con texto alternativo. El PNG de 1280x640 (97 KB) no entra al repo: es para la vista previa social, que el usuario sube en la configuración de GitHub.
- **L5** (2026-11-15): T2 quedó en el commit `1b3f6e2`. El CI de la rama pasó en Ubuntu, macOS y Windows, tanto en `1e17e2c` como en `1b3f6e2`. El usuario revisó el README en GitHub y autorizó: «Listo, todo bien autorizo». Push a `main` por fast-forward, `782128a..1b3f6e2`; el pre-push dio el barrido limpio y la entrega limpia. Este registro queda solo en la rama hasta el próximo push a `main`.
