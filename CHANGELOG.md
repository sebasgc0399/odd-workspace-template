# Changelog

Las notas de cada entrega de `odd-ws`. Cada versión es una sección `## <versión>`, y su contenido es el cuerpo del release que publica `.github/workflows/release.yml` cuando llega la etiqueta `odd-ws--v<versión>`. El pre-push no deja entregar una versión sin su sección.

## 0.3.1

- **macOS y Linux.** Los hooks arrancan con `python3`, el único que traen de fábrica macOS, Ubuntu y Debian.
  - En Claude Code 2.1.295 o más van con `onFailure: "block"`: si Python no arranca, la herramienta se bloquea con el error en vez de pasar sin el chequeo.
  - Codex lanza `python3`, y `python` en Windows.
- **Windows con el instalador clásico de python.org, winget o choco:** no crean `python3`, así que en Claude Code los hooks de pre y post bloquean hasta que lo haya. Lo crean el Python install manager y la Microsoft Store. `/odd-ws:doctor` revisa el intérprete que lanza cada host declarado y da el arreglo.
- **Los guards en macOS y Linux:**
  - En macOS, un push o un commit sobre un repo protegido escrito con otras mayúsculas o en otra forma Unicode ya no pasa.
  - La excepción del scratch reconoce el de Claude Code en cada sistema: `/tmp/claude-<uid>` en macOS y `<TMPDIR>/claude-<uid>` en Linux. Un borrado ya no se escapa del scratch por un enlace seguido de `..` ni por `.\.`.
  - `git -C //<repo>` ya no esquiva la capa 2.
- **`/odd-ws:conocimiento --claims` en macOS:** las afirmaciones corren sin `/usr/bin/timeout`. La lista blanca cierra formas de `uniq` y `sort` que, con el getopt de BSD (también el de Git for Windows), escribían archivos.
- `auditar_lecturas` ve una lectura prohibida aunque la ruta pase por un enlace, y el doctor y `scriptdom.ps1` funcionan fuera de Windows.
- **Instancias existentes:** su `.githooks/pre-commit` sigue llamando a `python`. En macOS, Ubuntu o Debian, copia encima el de `plugin/plantillas/pre-commit`, que prueba `python3`, `python` y `py`.

## 0.3.0

- **Soporte para Codex CLI.** El plugin trae su manifiesto para Codex (`.codex-plugin/plugin.json`) y sus hooks (`hooks/hooks.codex.json`). Los hooks corren con `--host codex` y bloquean por JSON, también en Windows. En Codex, cada hook necesita tu confianza en `/hooks`, y en la 0.167 la vuelve a pedir con cada actualización del plugin.
- **`hosts` en `workspace.config.json`.** Declara los CLI del workspace, por ejemplo `["claude-code", "codex"]`. Sin la clave, el workspace es solo de Claude Code y nada cambia. Con `codex`, la instalación genera `.codex/agents/*.toml` a partir de los mismos agentes, y `.codex/config.toml` para que Codex lea los `CLAUDE.md`.
- **`/odd-ws:doctor` por host.** Con Codex declarado, revisa:
  - la versión, el plugin y la confianza de los hooks y del proyecto;
  - `.codex/config.toml` y los agentes TOML: `--arreglar codex-config` y `--arreglar codex-agentes` los generan o los ponen al día a partir del `.md`.

  `hooks-host` avisa si un hook tiene el `--host` mal puesto.
- **Writers en Codex.**
  - **La compuerta de cierre:** también funciona en Codex. Los archivos y comandos del writer salen de una bitácora que anota `writer_guard`.
  - **El primer toque:** frena también a sus writers.
  - **Codex 0.167 o más:** hace falta para lanzar un writer por su rol.
  - **En Windows:** un writer que escribe en los repos de las capas necesita `[windows] sandbox` y esos repos como `writable_roots` en la config de Codex. Ver `Doc/diseno.md`.
  - **Pendiente conocido:** con el sandbox `unelevated`, la medición de líneas reales del writer da 0/0.
- Para leer la config de Codex, el doctor necesita Python 3.11 o más.

## 0.2.2

- `/odd-ws:doctor` marca gentle-ai, engram, jq y el `credential.helper` de git como **AVISO opcional**, no como FALTA: el plugin no los necesita.
- La plantilla del `CLAUDE.md` de la instancia explica qué ajusta del ODD de gentle-ai si también lo usas.

## 0.2.1

- El triaje cuenta los consumidores en la base explícita de un repo sin remoto (`--repo RUTA#BASE`).
- `/odd-ws:abrir` crea la rama con `--no-track`, y `/odd-ws:revisar` ya no anuncia «otro orden» cuando el cambio tiene un solo archivo.

## 0.2.0

- Las skills del ciclo de un ticket: `/odd-ws:abrir`, `/odd-ws:revisar` y `/odd-ws:cerrar`.
- Los revisores leen el `CLAUDE.md` del ticket desde el disco, el recibo distingue `limpio`, `pendiente` y `con-hallazgos`, y `/odd-ws:cerrar` no repite el id de una regla.
