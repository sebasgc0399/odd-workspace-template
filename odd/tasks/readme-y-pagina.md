# El README y la página: que se entienda rápido, se vea profesional y esté al día (R17)

Objetivo: quien llega al README o a la página entiende en segundos qué es odd-ws, encuentra la instalación sin buscarla y lee solo cosas ciertas.
Rama: `feat/readme-y-pagina`, en `D:/Project/odd-ws-wt/readme`, desde `origin/main` (`1a11fdf`, la `0.13.3`). La página va en la rama `gh-pages` (worktree `D:/Project/odd-ws-wt/pages`, `8a86aa1`). Entrega: un commit por unidad y un push del README y otro de la página, con el ok del autor. No toca `plugin/`, así que no hay versión.
Pruebas: `python tools/entrega.tests.py`, el chequeo de S7 de la `0.13.3` sobre el commit (`desfases_de_la_entrega`), y capturas en escritorio y celular, claro y oscuro.

## Specs

El origen es el pedido del autor (L1). Lo marcado como **decisión de diseño** lo decidió el orquestador, con la autorización del autor «Vale te lo dejo a tu criterio» (L1).

- **S1** (lo que está mal o viejo). «y si también la informacion que este al dia». Se corrigen los hallazgos de la auditoría (L2), con el texto correcto que lleva cada uno:
  1. La página dice «Un falso positivo no te frena el trabajo». Pasa a: si un bloqueo es un falso positivo, una disputa lo vuelve aviso hasta que se arregle el chequeo.
  2. Lo de engram lo hace `/odd-ws:cerrar memorias`, no `/odd-ws:cerrar`.
  3. `Doc/uso.md:39`, sobre el RDD de gentle-ai, dice lo mismo que el README: el doctor propone apagarlo solo en el clon de una instancia completa, y lo aplica con tu sí.
  4. `Doc/uso.md:35`: el doctor sí consulta gentle-ai, engram y jq, y con tu sí apaga el RDD. Ningún hook los necesita.
  5. La fila de Codex en los requisitos, igual en el README y la página: «0.144 o más; 0.167 o más para los writers. En Windows, sus hooks lanzan `python`». `Doc/uso.md` nombra también a Pi, y `Doc/hooks.md` dice qué Python lanza cada CLI.
  6. La descripción del doctor: «Revisar tu máquina y la instancia, y decir cómo arreglar lo que falta».
  7. Las filas de skills:
     - `enlaces` sirve con un ticket o con cualquier `.md`;
     - `paquetes` también lista;
     - la página suma «con `memorias`» en `cerrar`;
     - `conocimiento` dice que necesita la clave `knowledge` en la config.
  8. El camino para quien usa gentle-ai: `controles` si quiere conservar su revisión; si no, el perfil completo, y el doctor le propone apagar el RDD en el clon.
  9. «Detecta tus repos» pasa a: los toma del `.code-workspace` o te pregunta cuáles son.
  10. Se dice cómo se crea una instancia desde Codex (`$bootstrap`) o Pi (`/skill:bootstrap`), y que `["codex"]` o `["pi"]` solos también valen. La página enlaza «Usarlo desde Codex» y «Usarlo desde gentle-shell».
  11. Se dice que una instancia nueva arranca sin reglas: se suman al cerrar tickets, o se traen con `/odd-ws:paquetes`.
  12. Se dicen los límites de los guards: no frenan a un agente que los esquiva a propósito, para eso está el sandbox, y fuera de una instancia dejan pasar todo.
  13. Se dice que `/odd-ws:abrir` y `/odd-ws:cerrar` commitean en la instancia, salvo con `ask_before_commit`.
  14. Los detalles:
      - `Doc/uso.md:3` dice «tres pasos»;
      - la página enlaza los requisitos de `Doc/uso.md` y no «el README»;
      - la página lista `Doc/diseno.md` y `CONTRIBUTING.md` en Documentación;
      - «Tu repo de código, intacto» se matiza para un repo `own`.
- **S2** (el README). «me gustaria que lo evaluemos que quiero que se abastante intuitivo y un gran experiencia de usuario». **Decisión de diseño:**
  - Arriba, en este orden:
    1. el título `odd-ws`, en lugar del nombre del repo;
    2. un banner en imagen con el nombre y la frase, en el estilo de la tarjeta y el GIF, con un `alt` que dice todo su texto;
    3. la línea «Funciona con Claude Code · Codex CLI · gentle-shell (Pi)», en texto;
    4. los accesos a la instalación de cada CLI, la guía, la página y el video;
    5. un inicio rápido de 3 pasos con el comando de Claude Code copiable;
    6. recién después, el GIF.
  - «Cómo funciona» parte del problema y trae un glosario corto: instancia, capa, regla, ticket.
  - La referencia (skills, gentle-ai y engram, dónde funciona) va al final.
  - Como mucho un alert de GitHub.
  - Ningún bloque de código se sale de su caja: el mensaje del bloqueo va en un formato que corta la línea.
  - Se conservan la línea «Versión actual:», la sección `## Instalación` con la tabla de requisitos (las lee el chequeo de S7) y las anclas que citan otros docs.
- **S3** (la página). «tambien de la pagina no estaria mal, tambien revisarla para que sea mucho mas profesional». **Decisión de diseño:**
  - Sigue siendo un `index.html` estático, sin build.
  - Lleva:
    - un hero con el comando de instalación copiable;
    - una navegación fija;
    - pestañas por CLI en la instalación;
    - tarjetas con íconos genéricos (SVG en línea, sin marcas);
    - el problema contado antes que la solución;
    - una FAQ corta;
    - favicon, modo oscuro y botón de copiar en cada bloque de código;
    - ningún bloque que se salga.
  - Usa las fuentes de la marca, Shantell Sans para los títulos y Red Hat Mono para el código, servidas desde la página con su licencia OFL. El resto va con la fuente del sistema.
  - Se conservan `id="instalar"`, la línea «Versión actual:», el pie con la versión y la tabla de requisitos igual a la del README (S7 de la `0.13.3`).
- **S4** (sin logos). El autor: «Ejemplo utilizar iconos reales ejemplo de claude o de codex y de Gentle Shell o Pi». Después de ver las guías de marca: «Vale, sin logos, la fila en texto». La compatibilidad va en texto, sin logos de Anthropic, OpenAI ni Pi.
- **S5** (imagen solo donde el texto no alcanza). El autor: «Y si hay texto que con solo .md no es posible mejorar, pues usa texto que puedas crear y no se si sean imagenes», y «te lo dejo a tu criterio». **Decisión de diseño:** van en imagen el banner y nada que cambie con cada versión. Comandos, requisitos y números quedan en texto.
- **S6** (la prueba). «puedes utilizar playwrigth para tomar imagenes del diseño y evaluarlo mejor».
  - Capturas del README renderizado y de la página, en escritorio (1440) y celular (390), en modo claro y oscuro, antes del push.
  - El chequeo de S7 de la `0.13.3` sin desfases.
  - Las anclas y los links resuelven.
- **S7** (nada se rompe). No cambia nada fuera del README, `Doc/`, `CONTRIBUTING.md` si hace falta, la página y sus archivos.

## Tareas

| ID | Specs | Qué | Ruta | Estado | Commit |
|----|-------|-----|------|--------|--------|
| T0 | todas | Este documento, su espejo en engram y R17 en el roadmap | inline | hecha | (con T1) |
| T1 | S1, S2, S4, S5 | El README nuevo, el banner y las correcciones de `Doc/` | inline | hecha (L4) | |
| T2 | S1, S3, S4 | La página nueva | delegada: writer en `D:/Project/odd-ws-wt/pages`, en paralelo con T1 (dos unidades independientes de más de 100 líneas, en ramas distintas) | pendiente | |
| T3 | S6, S7 | Las capturas, el chequeo de S7 y los links; la entrega, con el ok del autor | inline | pendiente | |

## Log

- **L1** (2026-11-23) El autor, tal cual:
  - «Estaba pensando si podiamos mejorar mas el readme, me gustaria que lo evaluemos que quiero que se abastante intuitivo y un gran experiencia de usuario buscar varios opciones o herramientas que podamos reutilizar o extrapolar para mejorar esa experiencia de entender que es el proyecto, necesitas revisar el diseño del readme, y tambien de la pagina no estaria mal, tambien revisarla para que sea mucho mas profesional tamien readme y la pagina, y si tambien la informacion que este al dia. Miremoslo por diferentes frentes, puedes utilizar playwrigth para tomar imagenes del diseño y evaluarlo mejor».
  - «Ejemplo utilizar iconos reales ejemplo de claude o de codex y de Gentle Shell o Pi no se, como ese tipo de detalles tambien importan, la parte visual».
  - «Y si hay texto que con solo .md no es posible mejorar, pues usa texto que puedas crear y no se si sean imagenes».
  - «Vale te lo dejo a tu criterio».
  - «Vale, sin logos, la fila en texto».
  - A «¿Lo hago ahora, antes de R15?»: «Si, hazlo ahora antes de R15».
- **L2** (2026-11-23) La evidencia, de tres frentes:
  - **Las capturas** (Playwright, 1440 y 390):
    - el README abre con el nombre del repo y un GIF de 560 px antes de decir qué es;
    - los comandos de instalación llegan cerca de los 4300 px de 7300;
    - «Qué te da» usa jerga antes de definirla;
    - el mensaje del bloqueo se sale de su caja en el README y en la página;
    - la página tiene 6800 px en una sola columna, sin navegación ni favicon (404), y los bloques de código no tienen botón de copiar.
  - **La auditoría** (un explorador sobre `1a11fdf` y `8a86aa1`): los 14 hallazgos de S1, con `ruta:línea`. Lo que se sostiene: los requisitos contra el doctor, las afirmaciones de features, «Dónde funciona», la versión y las anclas.
  - **La investigación** (fuentes primarias):
    - arriba del pliegue van un one-liner, pocos badges, el demo y la instalación cerca (uv, ruff, opencode, Codex);
    - el estudio de Evil Martians sobre más de 100 landings: hero, confianza, features, CTA final y una FAQ, con el problema antes que la lista de features;
    - GitHub pide como mucho uno o dos alerts;
    - el social preview mide 1280×640;
    - las guías de marca de Anthropic y de OpenAI no dejan usar sus logos sin aprobación, y gentle-ai y superpowers muestran la compatibilidad en texto.
- **L3** (2026-11-23) Lo que se reusa:
  - **El estilo de la tarjeta y del GIF** (`video-studio/projects/odd-ws-tarjeta/compositions/tarjeta.html`): papel `#fbf8f1` con puntos `#e3dccb`, Shantell Sans 700, Red Hat Mono 500, tarjetas blancas, rojo `#d93a2b`, azul `#2b59c3` y etiqueta `#f1e6bf`.
  - **Las fuentes:** salen de `video-studio/library/fonts/`.
  - **El render:** Chrome headless con `--screenshot` sobre un `file://`, como el banner de YouTube (`video-studio/library/brands/sebasgc-dev/BRAND.md`).
  - **Risk:** none (docs y página, nada de `plugin/` ni de `tools/`).
- **L4** (2026-11-23) T1, inline:
  - **El banner** (`Doc/img/odd-ws-banner.png`, 1600×500, 94 KB):
    - Lleva el nombre y la frase, con «el mismo error» en azul subrayado, y a la derecha la línea `FROM proveedores;` en un óvalo rojo y el chequeo `[SQL-01 CRITICAL]` de `verificar-capa`, en el estilo de la tarjeta.
    - Su fuente está en `Doc/img/banner.html`, con el comando de render en un comentario. Se renderizó con Chrome headless, y llevó tres vueltas hasta que los trazos rodearon y subrayaron sin tachar.
    - Es el título del README (`# ![alt](banner)`), así que el nombre no aparece dos veces. El `alt` dice todo su texto.
  - **El README:**
    - El orden: el banner, los badges, el one-liner, «Funciona con» en texto (S4), «Versión actual:», los accesos, el inicio rápido de 3 pasos, el GIF, «Cómo funciona» desde el problema con el glosario de 4 palabras, el bloqueo, «Qué te da», «Por dónde empezar», «Instalación», las skills, gentle-ai y engram, «Dónde funciona» y la documentación.
    - El mensaje del bloqueo va en una cita, que corta la línea.
    - No lleva ningún alert: GitHub no los muestra dentro de una lista, y el de `--scope project` quedó en negrita.
    - Se conservan las anclas `#instalación`, `#dónde-funciona`, `#junto-a-gentle-ai-y-engram` y las de cada CLI.
  - **S1 en el README y `Doc/`:** los ítems 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13 y la parte de `Doc/uso.md:3` del 14.
    - `/skill:bootstrap` crea una instancia desde cualquier carpeta (`Doc/hooks.md:61`, `Doc/diseno.md:326`).
    - `["codex"]` solo también vale (`Doc/diseno.md:360`).
    - Una instancia de Codex que ya existe sigue necesitando `--arreglar codex-config` y `codex-agentes` (`Doc/uso.md:52`).
  - **La prueba:**
    - El README se renderizó con `gh api markdown` (modo `markdown`) y el CSS de GitHub, en claro y oscuro, y se capturó a 1440. A 390 se capturó con Playwright, servido por localhost, porque Playwright no abre `file://`.
    - En el celular nada se sale: `scrollWidth` 300 contra un viewport de 312 px CSS, y solo los bloques de código tienen su propio scroll.
    - El chequeo de S7 sobre el texto: la tabla del README se encuentra, y `version_actual_desfasada` y `comandos_desfasados` dan vacío en el README, `Doc/uso.md` y `Doc/actualizar.md`.
    - El diagrama Mermaid no se ve en el render local porque necesita el JS de GitHub; en GitHub ya se veía.
  - **Lo que aprendí del método:**
    - La API de markdown en modo `gfm` convierte cada salto de línea en `<br>`; el README se ve como en GitHub en modo `markdown`.
    - Una captura de página completa con Playwright, con escala 1.25, sale recortada aunque la página no se salga: lo que vale es la captura del viewport.
