# Changelog

Las notas de cada entrega de `odd-ws`. Cada versión es una sección `## <versión>`, y su contenido es el cuerpo del release que publica `.github/workflows/release.yml` cuando llega la etiqueta `odd-ws--v<versión>`. El pre-push no deja entregar una versión sin su sección.

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
