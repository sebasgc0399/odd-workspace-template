# Mudar la instancia a otro computador (I45)

Estudio para decidir. Base: odd-ws 0.9.0. No trae cambios de código.

Las citas a scripts omiten `plugin/scripts/`, y las de skills, `plugin/skills/`. Las de docs van con `Doc/`.

## 1. El escenario

Cambias de computador. Los repos de código están en un remoto y se vuelven a clonar, pero la instancia es un repo solo local.
La idea del autor: comprimir la carpeta, descomprimirla en la máquina nueva y pedirle al agente que la deje configurada.
La pregunta: qué se rompe en el traslado, quién lo nota y cuál es el camino más seguro.

## 2. Qué viaja y qué no

| Pieza | Dónde vive | Clon | Zip | Qué se rompe si falta o llega vieja | Quién lo nota hoy |
|---|---|---|---|---|---|
| Lo versionado: config, reglas, skills, agentes, `CLAUDE.md`, tickets | el repo de la instancia (`Doc/equipo.md:9-16`) | sí | sí | nada | no aplica |
| Rutas de los repos | `workspace.local.json`, en `.gitignore` (`bootstrap.py:27`) | no | sí, las viejas | config rota: los hooks no verifican nada (`verificar_capa.py:629-630`, `writer_guard.py:1488-1490`) y todo git que escribe pregunta (`guard_comandos.py:788-790`) | aviso al arrancar o reanudar (`verificar_capa.py:27`, `:598-605`) y doctor `config` en FALTA (`doctor.py:287-291`). **Nadie** si la ruta vieja existe en la máquina nueva: solo se comprueba que sea una carpeta (`config_loader.py:87-88`) |
| `plugin_root` | el mismo archivo (`bootstrap.py:224`) | no | sí, viejo | el pre-commit falla cerrado (`plugin/plantillas/pre-commit:25-28`) | doctor `plugin-root`, con arreglo (`doctor.py:220-226`) |
| `core.hooksPath` | `.git/config`, con `--local` (`bootstrap.py:508-510`) | no | sí, y sirve: es relativo (`doctor.py:75`) | no corre el pre-commit, que prueba las reglas | doctor `instancia-hooks`, con arreglo (`doctor.py:306-333`) |
| Bit ejecutable del pre-commit | el índice de git (`bootstrap/SKILL.md:102`) | sí | según el compresor | fuera de Windows, git ignora un hook sin `+x` | nadie: el doctor mira que exista, no el modo (`doctor.py:315`) |
| Estado de sesiones: ticket activo, turnos, fotos de writers | `.claude/estado/`, en `.gitignore` (`odd_ws/capas.py:22-29`) | no | sí, viejo e inofensivo: va por sesión (`writer_stop.py:256`) | sin ticket activo, la sesión de la raíz no recibe su resumen | nadie; se arregla con `ticket.py --activar <id>` (`abrir/SKILL.md:149`) |
| Recibos y sellos de revisión | `<ticket>/revision/*/recibo.json`, versionado, con la ruta absoluta de cada repo (`recibo.py:194`) | sí | sí | con otra ruta, el triaje no ve los sellos y vuelve al merge-base (`triaje.py:232-241`, `:263-265`); `--sellar` y `--previo` sobre un recibo viejo fallan (`recibo.py:450-451`; `:246` con `:64-66`) | el triaje dice de dónde sacó la base (`revisar/SKILL.md:52`), pero no que fue por la mudanza |
| `.code-workspace` | la raíz; lo versiona `abrir` (`abrir/SKILL.md:108`, `:127`) | sí | sí | VS Code muestra carpetas que no existen | nadie: el doctor no lo lee |
| Paquetes de reglas con fuente local | el lock, versionado, con la ruta absoluta (`paquetes.py:95`) | sí | sí | `actualizar` no encuentra la fuente (`Doc/capas-y-reglas.md:116`) | nadie al mudarse |
| Plugin instalado | Claude Code lo registra por carpeta (`Doc/equipo.md:14`); Codex y Pi, aparte (`README.md:57`) | no | no | sin hooks ni skills | nada de odd-ws: sin plugin no hay doctor |
| Confianza de Codex: proyecto y hooks | `~/.codex/config.toml`, por ruta (`odd_ws/hosts/codex.py:472-475`, `:502-506`) | no | no | Codex no carga `.codex/` ni corre los hooks | doctor, en AVISO (`codex.py:509`, `:460-461`) |
| Auto-memoria de Claude Code | `~/.claude/projects/<slug de la ruta>/memory` (`odd_ws/hosts/claude_code.py:250-251`, `:336-337`) | no | no | con otra ruta, memoria vacía; lo mismo con la memoria de cada repo (`Doc/diseno.md:973`) | solo `/odd-ws:cerrar memorias`, que sale con 2 y nombra la carpeta que probó (`Doc/diseno.md:970`) |
| Registro de memorias vistas | `~/.odd-ws/memorias/<slug>.json` (`memorias.py:32`, `:204-207`) | no | no | lo visto o descartado vuelve como nuevo | nadie |
| engram | su base, en el home (`~/.engram`); el proyecto sale del remoto (`Doc/equipo.md:110`) | no | no | sin memorias ni el espejo `odd/<id>/tasks` (`abrir/SKILL.md:121`); las filas citadas por número solo valen en la máquina que las escribió (`Doc/equipo.md:111`) | el doctor solo mira la versión (`doctor.py:733`) |
| `~/.odd-ws/denylist.txt` | el home (`CONTRIBUTING.md:9`) | no | no | solo en un clon del plugin: el barrido bloquea todo commit | doctor `lista-negra`, solo en ese clon (`doctor.py:174-181`) |
| Worktrees en curso de los repos de código | fuera de la instancia | no | no | ramas sin push; la línea «Worktree y rama» del ticket queda con rutas viejas (`plugin/plantillas/ticket.md:35`) | nadie: la config solo lista los que existen (`config_loader.py:93-111`) |
| Python, credenciales de git, CLIs | la máquina | no | no | los hooks no arrancan | doctor (`doctor.py:546-590`) |

### Tres correcciones a la premisa

- **El zip con rutas viejas sí se nota** cuando la ruta vieja no existe: aviso al arrancar, doctor `config` en FALTA y el guard pregunta antes de cada git que escribe. Lo silencioso es lo contrario: una ruta vieja que existe en la máquina nueva y es otra carpeta.
- **`/odd-ws:bootstrap` no rehidrata.** Exige que la spec traiga `workspace.local.json` tal cual (`bootstrap/SKILL.md:16-20`, `bootstrap.py:189-193`) y lo carga, así que con rutas que no existen la rechaza (`bootstrap.py:121`, `:127-128`). En un clon, la vía documentada es el doctor (`Doc/equipo.md:30-50`).
- **`.code-workspace`:** la skill no fija si la ruta es absoluta o relativa. El worktree vive fuera de la instancia y su ruta sale del comando del paso 6 (`abrir/SKILL.md:95`), así que en la práctica queda absoluta. El lector del bootstrap acepta las dos (`bootstrap.py:633`).

### El atajo que más arregla

Usa en la máquina nueva las mismas rutas absolutas, fuera de la carpeta del usuario (por ejemplo `C:\code\mi-repo`). Rutas, sellos, confianza de Codex y slug de la memoria comparan la ruta, así que siguen valiendo (`triaje.py:241`, `codex.py:472-475`, `claude_code.py:250-251`).

## 3. Dos caminos: zip o remoto privado

| | Zip de la carpeta | Remoto privado |
|---|---|---|
| Qué lleva | todo, también lo ignorado y lo sin commitear | solo lo commiteado |
| Cómo llega | con `workspace.local.json` y `.claude/estado/` viejos, que parecen válidos | limpio, con los tres FALTA conocidos del doctor (`Doc/equipo.md:30-36`) |
| `core.hooksPath` | viaja | lo arregla el doctor |
| Bit `+x` del hook | depende del compresor | lo restaura git |
| Respaldo | una copia puntual | historia fuera de la máquina; se puede seguir sincronizando |
| Proyecto de engram | sin remoto, sin garantía | sale del remoto, igual en cada clon (`Doc/equipo.md:110`) |
| Exposición | ninguna, salvo que el zip pase por una nube | todo el contenido queda en el host |
| Guía hoy | ninguna | `Doc/equipo.md:18-50` |

**El riesgo del remoto.** La instancia guarda tickets, bitácoras y notas de dominio, y en ella no corre ningún barrido de confidencialidad (`Doc/equipo.md:86`). Los recibos llevan rutas absolutas, que suelen incluir el nombre del usuario (`recibo.py:194`). Si el contenido es de tu empleador, subirlo a una cuenta personal puede violar su política: el host tiene que ser uno que esa política permita, y el repo, privado. Una carpeta sincronizada en la nube para pasar el zip también es un host.

**Una vía sin host.** `git bundle create instancia.bundle --all` en la máquina vieja y `git clone instancia.bundle <carpeta>` en la nueva. Llega como un clon (limpio, con historia y con el `+x`) sin pasar por ningún servidor. Después, quita el `origin`, que apunta al archivo.

**Recomendación: el camino del clon.** Remoto privado si tienes un host que la política permita para ese contenido; si no, el bundle. El zip no conviene para la instancia: llega con estado viejo que parece bueno, y su único caso silencioso (una ruta vieja que existe) es justo el que nadie detecta.

## 4. Antes de irte y al llegar

Funciona hoy con 0.9.0, sin cambios de código.

**Antes de irte**

1. Commitea todo en la instancia, hasta que `git status` quede limpio: lo sin commitear no viaja en un clon.
2. Por cada ticket abierto, anota en su bitácora la base de cada repo que muestra el triaje (`repo … (base …, sellada en revision/…)`, `revisar/SKILL.md:52`). Si las rutas cambian, ese sello deja de valer (`triaje.py:241`).
3. En los repos de código, decide qué pasa con cada worktree en curso (`git worktree list`): las ramas sin push no viajan. El push es tuyo, con destino explícito.
4. Lleva por tu cuenta lo que vive en el home: la carpeta de memoria de la instancia y la de cada repo (`claude_code.py:336-337`), `~/.odd-ws/memorias/` (`memorias.py:207`) y engram, con su propio mecanismo (`Doc/equipo.md:113` lo probó con `engram sync`). Si colaboras en el plugin, también `~/.odd-ws/denylist.txt`, sin abrirlo.
5. Sube la instancia a su remoto privado, o crea el bundle.

**Al llegar**

1. Clona los repos de código; si puedes, en las mismas rutas.
2. Clona la instancia. Con bundle, quita después el `origin`.
3. Instala el plugin desde la raíz de la instancia (`Doc/equipo.md:22-27`); en Codex o Pi, como dice `README.md:57`.
4. Corre `/odd-ws:doctor` y aplica, de a uno: `--arreglar plugin-root`, las rutas a mano en `workspace.local.json` y `--arreglar instancia-hooks` (`Doc/equipo.md:30-48`). Repite hasta que no quede ninguna FALTA (`Doc/equipo.md:50`).
5. Comprueba que cada ruta sea la raíz de su repo, porque el doctor no lo mira: `git -C <ruta> rev-parse --show-toplevel` tiene que devolver la misma ruta.
6. En Codex, confía el proyecto y los hooks en `/hooks` (`Doc/actualizar.md:21`).
7. Copia la memoria a la carpeta del slug nuevo: la ruta, con cada carácter que no sea letra o dígito ASCII cambiado por `-` (`claude_code.py:250-251`). Renombra el registro de `~/.odd-ws/memorias/` al mismo slug.
8. Restaura engram y confirma el proyecto con `mem_current_project`.
9. Recrea los worktrees con el comando de `abrir` (`abrir/SKILL.md:95`) y corrige la línea «Worktree y rama» del ticket y el `.code-workspace`.
10. Marca el ticket en curso: `ticket.py --activar <id>` (`abrir/SKILL.md:149`).
11. En la primera revisión de un ticket en curso, pasa la base anotada: `--repo <repo>#<sha>` (`triaje.py:261-262`). No uses `--previo` con un recibo de la máquina vieja: revisa la unidad entera.

Si igual usas el zip: en el paso 4, `plugin-root` y las rutas se corrigen en el archivo que llegó, y el paso 5 deja de ser opcional. Fuera de Windows, `chmod +x .githooks/pre-commit`.

## 5. Qué cambiaría en odd-ws

Dos chequeos que la idea proponía ya existen: el doctor marca las rutas que no existen (`doctor.py:287-291`) y el `core.hooksPath` sin configurar, con arreglo (`doctor.py:322-333`), además de `plugin_root` (`doctor.py:220-226`). Lo que falta es otra cosa.

| Opción | Tamaño | Qué resuelve | Tradeoff | Valor |
|---|---|---|---|---|
| A. `Doc/mudanza.md`: la tabla y la checklist de arriba, enlazando a `Doc/equipo.md` en vez de repetirlo | S, solo doc | todo I45, desde ya | se desactualiza si cambia el estado local; hay que revisarla en cada versión | 5/5 |
| B. Doctor: cada ruta de `workspace.local.json` es la raíz de un repo git | S | el único caso silencioso (`config_loader.py:87-88`) | un `git rev-parse` por repo, solo en el doctor; en el cargador sumaría latencia a cada hook | 4/5 |
| C. Doctor: «la instancia se movió». `workspace.local.json` anota la raíz donde se escribió y, si la actual es otra, sale un AVISO con la lista de lo que hay que revisar | S a M | nombra la mudanza, sea por clon, zip o copia | un campo más en un archivo local, sin contrato con nadie; el arreglo solo reanota la raíz | 4/5 |
| D. Bootstrap «rehidratar» | M | reescribe las rutas y `hooksPath` | duplica dos arreglos del doctor y rompe la regla de no pisar (`bootstrap.py:189-193`); las rutas las da el usuario igual | 2/5 |
| E. Recibos con el nombre del repo de la config además de `ruta`; triaje, `--sellar` y `--previo` buscan por nombre y caen a la ruta en los recibos viejos | M | los sellos sobreviven a la mudanza y a mover un repo | cambia un formato persistido y versionado, así que lee los dos; los worktrees se mapean con la config (`config_loader.py:392`), y el filtro de ancestros ya descarta sellos ajenos (`triaje.py:251-252`) | 3/5 |
| F. Memoria: si su carpeta no existe, `cerrar memorias` lista las de `~/.claude/projects/` que terminan en el mismo nombre de carpeta | S | la memoria «vacía» tras mudarse | es una heurística; solo avisa y no escribe fuera de la instancia, como con Codex (`codex.py:117-118`) | 3/5 |

Una variante útil de D, sin sus costos: que el doctor proponga las rutas que faltan leyendo el `.code-workspace`, como ya hace `--proponer` (`bootstrap.py:621-650`), y las escriba con el sí del usuario.

## 6. Recomendación y orden

1. **A ahora.** Cierra I45 sin código y le da al autor el camino para esta mudanza.
2. **B y C juntos,** en una versión menor: son del doctor, chicos y sin contrato con nadie.
3. **F** cuando alguien reporte la memoria vacía.
4. **E solo con un caso real.** Hoy no tenerlo cuesta una revisión más ancha (en un ticket real, 83 archivos en vez de 21, `revisar/SKILL.md:224`), no un error.
5. **D, no.**

## 7. Preguntas para el autor

1. ¿La guía va en un archivo propio o como sección de `Doc/equipo.md`? Propuesta: `Doc/mudanza.md`, enlazado desde el README y desde equipo, porque quien se muda solo no busca en «equipo».
2. ¿La guía nombra un host? Propuesta: no; dice «un remoto privado que tu organización permita para ese contenido» y ofrece el bundle.
3. ¿El doctor puede escribir fuera de la instancia, por ejemplo para copiar la memoria? Propuesta: no; avisa y da el comando, como hace con Codex.
4. ¿E entra ahora o espera un caso real? Propuesta: espera.
