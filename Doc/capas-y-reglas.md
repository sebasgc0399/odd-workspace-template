# Capas y reglas propias

La plantilla trae una sola biblioteca de reglas, la de T-SQL (`odd_ws.tsql`). Para cualquier otro stack, las reglas de cada capa se escriben en la instancia, o se traen de otro repo como un [paquete de reglas](#paquetes-de-reglas).

- **El módulo.** Cada capa tiene su `.claude/reglas/verificar_<capa>.py`. El bootstrap lo deja vacío: `REGLAS = ()` y `verificar(ctx)` devuelve `[]`. Su `verificar_<capa>.tests.py` valida el contrato.
- **El contrato.** `verificar(ctx)` recibe el archivo editado (`ruta`, `texto`, `agregadas`, `hunks`, `es_nuevo`, entre otros). Devuelve una lista de hallazgos `{id, modo, severidad, linea, fragmento, mensaje}`, con `modo` en `bloqueo` o `aviso`. El detalle está en [Contrato de los módulos de capa](diseno.md#contrato-de-los-módulos-de-capa-p1), en `Doc/diseno.md`.
- **Correrlas sin Claude.** `reglas.py` está en `scripts/` del plugin; su ruta queda en `plugin_root` de `workspace.local.json`.

  ```text
  python3 "<plugin_root>/scripts/reglas.py" --test [CAPA]
  python3 "<plugin_root>/scripts/reglas.py" --calibrar CAPA CARPETA [--detalle] [--guardar]
  ```

  `--test` corre las pruebas de las reglas. `--calibrar` pasa las reglas sobre una carpeta de código real y cuenta cuántas veces salta cada una; con `--guardar`, además escribe la calibración que deja bloquear (abajo). Las dos aceptan `--raiz <instancia>`.
- **La matriz.** Cada convención nueva entra como una fila de `.claude/reglas/matriz.csv`, con su id `<prefijo>-NN`, su origen, su tipo, su destino y su severidad. `/odd-ws:cerrar` la agrega por ti.
- **Agregar una capa a una instancia que ya existe.** Suma la capa a `workspace.config.json` y la ruta de sus repos a `workspace.local.json`, a mano. Después vuelve a correr `/odd-ws:bootstrap`: genera lo que falta de la capa nueva sin tocar lo que ya existe.

Cuándo corren estas reglas durante una sesión está en [Hooks](hooks.md#cuándo-corre-cada-uno).

## Cuándo bloquea una regla

Una regla empieza observando: el `modo` que pide el módulo es un techo, no una orden. Vale igual para el módulo de la capa y para el de un [paquete](#paquetes-de-reglas). Un hallazgo bloquea solo si se cumple todo esto:

1. el módulo pide `bloqueo` (una regla de estilo puede avisar para siempre);
2. la regla declara su defecto sembrado: un atributo `sembrado` en su objeto de `REGLAS`, con el defecto que la regla tiene que atrapar (un texto, o una ruta con su texto);
3. la calibración guardada atrapó ese sembrado y dio 0 aciertos en bloqueo en el corpus;
4. el módulo no cambió desde la calibración (para un paquete, la huella de su lock no cambió);
5. no hay una [disputa](#las-disputas) abierta para su ID.

```python
import types

REGLAS = (
    types.SimpleNamespace(id="EJ-01", sembrado="SELECT * FROM t"),
    types.SimpleNamespace(id="EJ-02", sembrado={"ruta": "Migrations/0001_alta.sql", "texto": "DROP TABLE t;"}),
)
```

**Las dos formas del `sembrado`.** Un texto le llega a la calibración como un archivo nuevo `sembrado<extensión>`, con la primera extensión de la capa, en la raíz del corpus. Una regla que mira la ruta (por ejemplo, solo los archivos bajo `Migrations/`, o el nombre del archivo) o una extensión que no es la primera de la capa nunca atraparía ese archivo. Para ella, el `sembrado` es un objeto `{"ruta": ..., "texto": ...}`: el texto le llega como un archivo nuevo del repo con esa ruta y su extensión, como `EJ-02` arriba. La ruta es relativa al repo, con `/`, y nombra un archivo: sin `/` al principio, sin unidad, sin `\`, sin `.` ni `..` y sin barras de más. Un `sembrado` con otra forma es lo mismo que no tenerlo: un texto vacío, o un objeto sin `ruta` o sin `texto`, con un texto vacío, con una clave de más o con una ruta que no cumple.

Una regla sin `sembrado`, o un módulo sin `REGLAS`, no puede bloquear. La suite que genera el bootstrap comprueba que cada `sembrado` tenga una de las dos formas y que su regla lo atrape. El bootstrap no pisa la suite de una instancia que ya existe, así que ahí esa prueba se copia a mano desde [`plugin/plantillas/reglas/verificar.tests.py`](../plugin/plantillas/reglas/verificar.tests.py).

**La calibración.** `reglas.py --calibrar <capa> <carpeta> --guardar` escribe `.claude/registro/calibracion.json`, que se commitea con la instancia. Por cada regla de `REGLAS` guarda la huella del módulo, si atrapó su sembrado, los aciertos (todos y los que piden bloqueo), los archivos del corpus, el corpus (`repo`, `commit` y `ruta` relativa al repo, nunca una ruta absoluta) y la fecha. Al final dice qué regla puede bloquear y por qué no las demás.

- Reemplaza entera la calibración de esa capa y conserva la de las otras.
- Calibra también, con el mismo corpus, cada paquete de la capa que el hook carga. Cada uno queda aparte, bajo `paquetes.<capa>.<nombre>`, con la huella de su lock, así que la entrada de un paquete no se confunde con la de la capa. La salida muestra cada paquete tras una línea `== <capa>/<paquete>: <ruta de su verificar.py>`.
- Una capa sin módulo propio, pero con paquetes, calibra solo sus paquetes.
- No escribe si hubo errores (sale con 1) ni si el módulo no declara `REGLAS` (sale con 2). Un paquete que no carga, revienta o devuelve un hallazgo inválido es un error. También lo es un paquete cuya carpeta no coincide con la huella de su lock: lo copiado cambió desde que se importó, y se reimporta antes de calibrar.
- Un paquete sin `REGLAS` no se calibra: lo dice, y sus reglas solo avisan.
- Con el lock de los paquetes roto, `--guardar` sale con 2 sin escribir.
- Un corpus vacío vale, con `archivos_del_corpus: 0`: un proyecto `propio` sin código todavía también puede bloquear.
- Una carpeta fuera de los repos declarados queda registrada solo por su nombre, con un aviso.
- Sin `--guardar`, `--calibrar` no escribe nada, no corre los paquetes y su salida no cambia.

**La huella.** Es el sha256 del módulo con CRLF pasado a LF, como la de los paquetes. Cualquier otro cambio en el archivo del módulo, aunque sea en otra regla, deja vieja la calibración de toda la capa. La huella no ve los archivos que el módulo importa: si una regla vive en un helper, recalibra cuando cambie. Para un paquete cuenta la huella de su lock: `actualizar` a otra etiqueta la cambia y deja vieja su calibración. El hook no relee la carpeta del paquete: una edición a mano de lo copiado la ve el doctor, no la calibración.

**Cuando no bloquea.** El hallazgo llega como aviso, con el motivo y lo que hay que correr: `disputada`, `disputas ilegibles`, `sin calibrar`, `calibración vieja`, `no pasó la calibración` o `registro de calibración roto` (un `calibracion.json` ilegible o con otra forma: ninguna regla bloquea hasta arreglarlo o borrarlo). Un hallazgo sin `modo` válido también llega como aviso, con el motivo `modo inválido`, y uno que pide bloqueo sin un `id` de texto, con el motivo `id inválido`. Si la regla es de un paquete y le falta el `sembrado` o no pasa la calibración, el aviso dice que se arregla en el repo del paquete, con una etiqueta nueva.

### Las disputas

Una disputa dice que un bloqueo está mal y que su chequeo hay que arreglarlo. Mientras esté abierta, la regla vuelve a avisar, aunque esté calibrada. Vale igual para una regla de la capa y para una de un paquete.

- **Abrirla.** Un archivo por disputa, `.claude/registro/disputas/<ID>.md`, con el ID exacto de la regla (`SQL-03.md`). Lo escribe el usuario, o el agente con su sí: ningún script abre una disputa solo. El contenido no se valida, pero lleva al menos quién la abre, qué bloqueo (el archivo y la línea) y por qué:

  ```markdown
  Abre: Ana
  Bloqueo: SQL-03 en src/sp/pedidos.sql, línea 42
  Por qué: salta sobre un comentario, no sobre código
  ```

- **Mientras está abierta,** cada hallazgo de esa regla llega como aviso, con el motivo `disputada` y cómo cerrarla. `reglas.py --calibrar … --guardar` guarda la calibración igual, y su línea de la regla dice `solo avisa: disputada`.
- **Cerrarla.** Se borra el archivo en el mismo commit que arregla el chequeo. Arreglar el chequeo cambia la huella, así que después la regla pide recalibrar: se corre `--calibrar … --guardar` y se commitea `.claude/registro/`. En un paquete, el arreglo va a su repo, con una etiqueta nueva, y se trae con `actualizar`.
- **Una carpeta de disputas ilegible** (por ejemplo, un archivo con ese nombre en vez de una carpeta) no deja bloquear a ninguna regla: todo llega como aviso, con el motivo `disputas ilegibles`.
- Un archivo que no termina en `.md` no es una disputa. El ID se compara sin distinguir mayúsculas.

## Paquetes de reglas

Un paquete trae las reglas de una capa desde otro repo git, fijadas a una etiqueta: por ejemplo, las de Go o las de SQL que comparten varias instancias. Se copia a la instancia y se commitea con ella, así que corre sin red y llega a cada dev con `git pull`. No es un submódulo.

### Qué lleva un paquete

En la raíz del repo del paquete, y nada más:

| Archivo | Qué lleva |
|---|---|
| `odd-ws-paquete.json` | El manifiesto |
| `verificar.py` | Las reglas, con el mismo contrato que `verificar_<capa>.py` |
| `verificar.tests.py` | Su suite |
| `matriz.csv` | Sus filas, con las mismas columnas que la matriz de la instancia |
| `no-negociables.md` | Lo que se suma al primer toque de la capa |
| `evidencia.md` | La evidencia de sus reglas |
| `LICENSE` | Opcional |

Nada más se copia: ni otro archivo (un `README.md`, una carpeta `.github/`) ni una subcarpeta. Ninguno de esos archivos puede ser un enlace.

El manifiesto, `odd-ws-paquete.json`:

```json
{"formato": 1, "nombre": "go-basico", "prefijo": "GOB", "odd_ws_api": 1, "descripcion": "Reglas básicas para Go"}
```

- **`nombre`:** minúsculas, dígitos y guiones, empezando por letra o dígito. Es la carpeta del paquete en la instancia.
- **`prefijo`:** mayúsculas y dígitos, empezando por letra. Los IDs del paquete son `<prefijo>-NN` (`GOB-01`); un hallazgo con otro ID invalida todos los del paquete. No puede ser el `rule_prefix` de una capa de la instancia ni el prefijo de otro paquete.
- **`odd_ws_api`:** la versión de la biblioteca `odd_ws` que necesita. Hoy es 1. Si pide una mayor que la del plugin, no se importa ni se carga.
- **`descripcion`:** un texto. Una clave que no es de estas cinco invalida el manifiesto.

`verificar.py`:

```python
import types

PANIC = types.SimpleNamespace(id="GOB-01", sembrado="func f() {\n\tpanic(err)\n}\n")
REGLAS = (PANIC,)


def verificar(ctx):
    return [{"id": PANIC.id, "modo": "bloqueo", "severidad": "WARNING", "linea": n, "fragmento": "panic(",
             "mensaje": "evita panic fuera de main: devuelve el error"}
            for n, t in ctx["agregadas"] if "panic(" in t]
```

Una regla de un paquete que tiene que bloquear sigue las [mismas condiciones](#cuándo-bloquea-una-regla) que una de la capa: declara su `sembrado` en `REGLAS`, y cada instancia la calibra con su propio código (`reglas.py --calibrar <capa> <carpeta> --guardar`). Sin `sembrado`, o sin `REGLAS`, solo avisa. El ID va una sola vez en el archivo (en `REGLAS`, y el hallazgo usa `PANIC.id`), porque el destino `chequeo` de la matriz lo cuenta.

`verificar.tests.py` busca su módulo por la ruta de su propio archivo, porque la carpeta del paquete no está en el path de Python:

```python
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("verificar_gob", Path(__file__).with_name("verificar.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

assert [h["id"] for h in M.verificar({"agregadas": [(1, "panic(err)")]})] == ["GOB-01"]
assert M.verificar({"agregadas": [(1, "return err")]}) == []
print("ok")
sys.exit(0)
```

`matriz.csv`:

```text
id,origen,tipo,destino,severidad,numeros,resumen,motivo
GOB-01,memoria:panic-fuera-de-main,CE,chequeo,WARNING,,panic fuera de main,un panic tumba el servicio
GOB-02,memoria:errores-envueltos,CE,pasiva,,,envolver los errores,sin el contexto el error no se entiende
```

Los destinos de un paquete son cuatro: `chequeo` (el ID aparece una vez en `verificar.py`), `pasiva` (una vez en `no-negociables.md`, en todo el archivo), `evidencia` (una vez en `evidencia.md`) y `descarte` (en ninguno). Otro destino es un error.

`no-negociables.md`:

```markdown
- **GOB-02** Envuelve el error con `fmt.Errorf("...: %w", err)` antes de devolverlo.
```

Y `evidencia.md`, con lo que respalda cada regla, por ejemplo su calibración con `reglas.py --calibrar`.

### Publicar un paquete

1. **Un repo git** con esos archivos en la raíz.
2. **Pruébalo antes de publicar.** El importador solo acepta etiquetas, así que crea una local sin empujarla (`git tag v1.0.0-rc1`) e impórtala en una instancia de prueba con la ruta local del repo: `reglas.py --test` corre su suite, `matriz.py --destinos --capa <capa>` valida su matriz (abajo) y `reglas.py --calibrar <capa> <carpeta> --guardar` dice qué regla puede bloquear y por qué no las demás.
3. **Etiqueta cada versión,** anotada o liviana: `git tag -a v1.0.0 -m "go-basico 1.0.0"` y `git push origin v1.0.0`. Una instancia se fija a una etiqueta: una rama o un hash no se importan. Para cambiar algo, haz una etiqueta nueva.

Fuera de esta versión: textos para el revisor (`reviewer-PR`) o los `criterios` desde un paquete, subcarpetas dentro del paquete, dependencias entre paquetes y un índice de paquetes de la comunidad.

### Importar, actualizar y quitar

Con `/odd-ws:paquetes`, que solo invocas tú. La skill corre el ensayo, te muestra el plan, escribe solo con tu sí, te pide leer el código copiado en el diff y te ofrece el commit con un segundo sí. Por debajo corre `paquetes.py`:

```text
python3 "<plugin_root>/scripts/paquetes.py" importar <fuente> --etiqueta <etiqueta> --capa <capa> [--ensayo]
python3 "<plugin_root>/scripts/paquetes.py" actualizar <nombre> --etiqueta <etiqueta> [--ensayo]
python3 "<plugin_root>/scripts/paquetes.py" quitar <nombre>
python3 "<plugin_root>/scripts/paquetes.py" listar
```

- **Qué hace `importar`.** Comprueba que la etiqueta existe, clona solo esa etiqueta en una carpeta temporal fuera de la instancia, valida el paquete, copia los archivos de arriba a `.claude/reglas/paquetes/<nombre>/` y escribe el lock, `.claude/reglas/paquetes.json`, con la capa, el prefijo, la fuente, la etiqueta, el commit y la huella de lo copiado. **Nunca ejecuta código del paquete.**
- **La capa** tiene que estar declarada en `workspace.config.json` y tener `rule_prefix`.
- **La fuente.** Una URL https o ssh (también `git@host:repo`), `git://` o una ruta local. Una ruta local se guarda absoluta y solo sirve en tu máquina: el script lo avisa. Una URL con usuario o contraseña se rechaza, porque iría al lock que se commitea: las credenciales van en git. `http://` sin TLS no vale.
- **Un repo privado.** Autentícate antes con git (un credential helper o ssh): el script nunca pide credenciales.
- **Lo copiado no se edita a mano.** El arreglo va al repo del paquete, con una etiqueta nueva, y se trae con `actualizar`. `actualizar` a la misma etiqueta vuelve a copiar lo de esa etiqueta.
- **`quitar`** borra la carpeta y la entrada del lock; sin paquetes, borra también el lock y la instancia vuelve a funcionar como antes.
- **Sale con 0** si anduvo, **con 1** si rechaza (una etiqueta que no existe, un paquete inválido, un nombre o un prefijo que choca) y **con 2** por el entorno (sin git, sin red, un protocolo que no vale, un lock o una config rota).

### Qué hace en la instancia

- **El hook** corre, para un archivo de la capa, primero su `verificar_<capa>.py` y después el `verificar.py` de cada paquete de la capa, por orden de nombre. Un paquete roto se calla él solo: no calla la capa ni a los otros paquetes. Un `bloqueo` de un paquete frena solo si su regla está calibrada con la huella actual del lock y sin disputa: ver [Cuándo bloquea una regla](#cuándo-bloquea-una-regla).
- **`actualizar` deja vieja su calibración,** porque cambia la huella del lock: después de leer el código nuevo, se recalibra la capa.
- **El primer toque** suma el `no-negociables.md` de cada paquete al bloque de la capa, con la línea `Del paquete <nombre> (fuente: <ruta>):` encima.
- **`reglas.py --test`** corre también la suite de cada paquete, en su propio proceso; el pre-commit de la instancia la incluye.
- **`matriz.py --capa <capa>`** valida la matriz de la instancia y después la de cada paquete de la capa contra sus propios archivos, con líneas que empiezan con `paquete <nombre>:`. La numeración de `/odd-ws:cerrar` sigue siendo solo la de la instancia.

### Qué revisa el doctor

El ítem `paquetes` de `/odd-ws:doctor` da NO APLICA sin lock y OK si todo está en orden. Da FALTA, con el detalle, si:

- el lock no se puede leer o no es válido;
- la capa de un paquete no está declarada;
- falta su carpeta o un archivo obligatorio;
- su carpeta o un archivo es un enlace o apunta fuera de su lugar;
- la huella no coincide, porque alguien editó lo copiado;
- su prefijo es el de una capa o el de otro paquete;
- el manifiesto no es válido o no dice el nombre y el prefijo del lock;
- pide un `odd_ws_api` mayor que el del plugin.

No tiene `--arreglar`: el arreglo es reimportar con `/odd-ws:paquetes`.

### El modelo de seguridad

El código de un paquete corre en tus hooks, con tus permisos, como cualquier dependencia. No hay contenedor: los hooks tienen un tope de unos segundos y Docker sería una dependencia pesada para cada dev. La defensa es otra:

- **El lock fija el commit,** así que una etiqueta movida en el repo del paquete no cambia lo que corre hasta que alguien actualiza.
- **El código se lee en el diff** antes del commit, y en el pull request del equipo.
- **La huella** detecta una edición local de lo copiado.
- **El importador nunca ejecuta código del paquete,** no copia enlaces ni subcarpetas y solo habla https, ssh, `git://` y rutas locales.

El porqué de cada decisión está en [Paquetes de reglas](diseno.md#paquetes-de-reglas-odd_wspaquetes-d2-d3-d4-y-el-doctor-de-d6) e [Importar paquetes](diseno.md#importar-paquetes-paquetespy-d1-y-d5), en `Doc/diseno.md`.
