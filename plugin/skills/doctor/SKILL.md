---
name: doctor
description: Chequeo de la máquina y de la instancia para la plantilla ODD (Capa 0). Usar cuando un hook no corre, al estrenar portátil, después de clonar la plantilla o cuando el usuario pide revisar el entorno.
---

# /odd-ws:doctor

Corre el diagnóstico desde el directorio del proyecto (si es un clon de `odd-workspace-template`, también revisa sus hooks y la lista negra; si es una instancia, `plugin-root`: la ruta del plugin que usa su pre-commit, anotada en `workspace.local.json`; `config`, que la config carga entera, rutas locales incluidas; `instancia-hooks`, que su `core.hooksPath` apunte a `.githooks`; `instancia-eol`, que su `.gitattributes` deje el hook en LF; `capas-cobertura`, las extensiones versionadas de sus repos que ninguna capa cubre; `hooks-apagados`, los hooks que apaga `disabled_hooks` en `workspace.config.json`; `perfil`, solo si el `CLAUDE.md` raíz es el reducido del perfil `controles` y la config no lo declara; `instancia-plugin`, que su `.claude/settings.json` habilite el plugin; un ítem `writer-<capa>` por cada capa declarada, que revisa `.claude/agents/writer-<capa>.md` contra la plantilla del plugin (con `"profile": "controles"`, un solo `writers` en NO APLICA), y dos ítems de sus agentes: `agentes-skills`, que las skills precargadas con `skills:` existan y se precarguen de verdad, y `agentes-hooks`, que ningún agente declare `hooks:` en el frontmatter). Los ítems de cada CLI salen solo para los que declara la instancia en `hosts` (sin la clave, Claude Code: `claude` y `marketplace`, además de `instancia-plugin` y los de agentes). Con `codex` declarado, suma `codex` (versión ≥ 0.144), `codex-plugin` (instalado en el caché de Codex y habilitado en `[plugins]`), `codex-hooks` (cada hook con su confianza en `[hooks.state]`), `codex-proyecto` (la raíz o su repo con confianza en `[projects]`), `codex-config` (`.codex/config.toml` con el fallback a `CLAUDE.md`), `codex-agentes` (cada `.codex/agents/<agente>.toml` igual al que sale de su `.md`) y `hooks-host` (ningún hook con un `--host` desconocido, vacío o de otro host). Con `hosts` inválido sale un solo ítem `hosts` en FALTA:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
```

En Windows con Codex, los comandos van con `python` en lugar de `python3`. Sale con 0 si no hay ninguna FALTA y con 1 si hay alguna. Los AVISO no hacen fallar. gentle-ai, engram, `jq` y el `credential.helper` de git son opcionales: si faltan o están atrasados, salen como AVISO con «opcional» en el detalle.

## Cómo presentarlo

1. Mostrá la tabla tal cual sale.
2. Para cada FALTA y cada AVISO, explicá en una línea qué rompe si no se arregla. Un AVISO opcional no rompe el plugin: decilo así y no lo presentes como pendiente.
3. **Ofrecé los arreglos de a uno.** Si el ítem tiene arreglo automático (la línea `arreglo: --arreglar <id>`), preguntá si lo aplicás. Corré `--arreglar <id>` **solo** después de un sí explícito para **ese** ítem:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --arreglar <id>
   ```

4. Si el ítem no tiene arreglo automático, pasale al usuario el texto de `cómo:`. No lo hagas por tu cuenta: son cambios de la máquina (PATH, instaladores, la lista negra).

## Reglas

- **`rdd`:** el interruptor del RDD de gentle-ai es del usuario. `--arreglar rdd` se corre solo si el usuario pide apagarlo; un AVISO no es permiso. Lo apaga solo en el clon de la instancia (`--scope clone`), y fuera de una instancia el ítem no aplica. En una instancia con `"profile": "controles"`, el RDD es su revisión: encendido es OK, y apagado es AVISO sin arreglo, porque la instancia queda sin revisión. Ahí no propongas apagarlo ni lo prendas por tu cuenta: pasale al usuario el texto de `cómo:`.
- **gentle-ai:** nunca le pases `--help` ni invoques `upgrade` (`gentle-ai upgrade --help` ejecuta el upgrade). El doctor solo usa `version`, `review mode status` y `telemetry status`.
- **`lista-negra`:** nunca leas ni muestres el contenido de la lista negra; es confidencial. Si falta, el usuario la crea.
- **`writer-<capa>`:** `--arreglar` escribe en la instancia: crea el writer que falta o regenera el atrasado, y conserva su `description` y sus bloques `<!-- instancia:... -->`. Antes de pedir el sí, decí qué archivo va a escribir. Un writer editado fuera de los bloques o escrito a mano es FALTA sin arreglo: no lo borres ni lo muevas por tu cuenta, pasale al usuario el texto de `cómo:`. Con `"profile": "controles"` sale un solo ítem `writers` en NO APLICA: esa instancia no lleva writers, así que no propongas crearlos.
- **`perfil`:** sale solo si el `CLAUDE.md` raíz es el reducido del perfil `controles` y la config no declara `"profile": "controles"`. Es AVISO sin arreglo: para pasar a completo, el usuario borra ese `CLAUDE.md` (si no lo editó) y corre `/odd-ws:bootstrap`. No lo borres por tu cuenta.
- **`instancia-hooks`:** `--arreglar` configura `core.hooksPath` en el repo de la instancia, y solo si no tiene valor, no hay hooks propios que dejarían de correr y la raíz no es un worktree enlazado. Antes de pedir el sí, decí qué va a escribir. Si el ítem queda en falta sin arreglo, pasale al usuario el motivo y el texto de `cómo:`, y no configures nada por tu cuenta. `config` e `instancia-plugin` no tienen arreglo: `workspace.local.json` y `settings.json` son del usuario.
- **`instancia-eol`:** `--arreglar` agrega la línea `.githooks/* text eol=lf` al `.gitattributes` de la instancia (lo crea si falta) y no toca el resto. Antes de pedir el sí, decí qué va a escribir.
- **`capas-cobertura`:** es AVISO sin arreglo. Explicá que un cambio en esos archivos lleva el triaje a modo `completo` (con `"profile": "controles"`, que ninguna regla de capa los chequea), y si alguna extensión es del mismo lenguaje que una capa (por ejemplo, `.mjs` en una capa `ts`), proponé sumarla a sus `extensions` en `workspace.config.json`; la config es del usuario, así que no la edites sin su sí.
- **`hooks-apagados`:** es AVISO sin arreglo mientras `disabled_hooks` apague algún hook. Nombrá cuáles; si está `guard_comandos`, decí que nada frena un force push, un `reset --hard` ni un borrado recursivo del agente. Para prenderlo se saca de la lista, pero la config es del usuario: no la edites sin su sí. Con la clave inválida sale NO APLICA y no se apaga ninguno: el ítem `config` dice qué está mal.
- **`agentes-skills` y `agentes-hooks`:** no tienen arreglo automático. Pasale al usuario el texto de `cómo:` y no edites los agentes ni las skills por tu cuenta.
- **Codex:** el doctor solo lee la carpeta de Codex (`CODEX_HOME` o `~/.codex`) y nunca escribe ahí. `codex-plugin`, `codex-hooks` y `codex-proyecto` no tienen arreglo: instalar el plugin, confiar en los hooks desde `/hooks` y confiar en el proyecto los hace el usuario en Codex. Si prefiere escribir la confianza del proyecto a mano, pasale la tabla de `cómo:` tal cual: Codex compara la ruta como texto, así que otra forma de escribirla (con `/`, o con una barra al final) no le sirve. `codex-hooks` no verifica que el hash de la confianza siga fresco: después de actualizar el plugin, Codex la vuelve a pedir.
- **`codex-config`:** `--arreglar` solo crea `.codex/config.toml` si no existe. Si existe sin el fallback, pasale al usuario la línea de `cómo:`.
- **`codex-agentes`:** `--arreglar` escribe en `.codex/agents`: crea los TOML que faltan y re-deriva los atrasados desde su `.md`. Un TOML editado a mano, el de un agente que ya no existe o el de un `.md` editado fuera de sus bloques queda en AVISO: no lo borres ni lo edites por tu cuenta; el cambio va al `.md` (la description o un bloque `<!-- instancia:... -->`).
- **`hooks-host`:** no tiene arreglo. Pasale al usuario el hook y el valor que marca el detalle.
- **`claude` o `codex` en AVISO por «no está instalado»:** la instancia declara varios CLI y esta máquina trabaja con otro de ellos. No es pendiente: decilo así y no ofrezcas instalarlo salvo que el usuario quiera usar ese CLI. Con `claude` así, `marketplace` y `agentes-skills` salen en NO APLICA («claude no está instalado»), igual que los ítems de máquina de Codex sin `codex`. Si no está instalado ninguno de los declarados, el ítem es FALTA. Uno instalado pero viejo es FALTA siempre.
- **Sumar Codex a una instancia que ya existe:** agregá `"codex"` a `hosts` en `workspace.config.json` (por ejemplo, `"hosts": ["claude-code", "codex"]`) y corré `--arreglar codex-config` y `--arreglar codex-agentes`, cada uno con su sí. El bootstrap también crea `.codex/config.toml`, pero los TOML de los agentes que ya tenían su `.md` los deriva el doctor.
- Después de cada arreglo, el doctor vuelve a chequear el ítem: reportá ese resultado, no el que esperabas.
