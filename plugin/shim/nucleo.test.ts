import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { combinar, contexto, correrEvento, hooksDe, leerLista, pythonDe, writerDe } from "./nucleo.ts";
import type { Hook, ListaDeHooks, Resultado } from "./nucleo.ts";

const PLUGIN = dirname(dirname(fileURLToPath(import.meta.url)));
const PYTHON = pythonDe(leerLista(join(PLUGIN, "hooks", "hooks.pi.json")));
const RESPONDE = "import sys\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(sys.argv[1].encode('utf-8'))\n";
const ECO = [
  "import json, os, sys",
  "datos = json.loads(sys.stdin.buffer.read())",
  "texto = json.dumps({'entrada': datos, 'cwd': os.getcwd(), 'args': sys.argv[1:]})",
  "sys.stdout.write(json.dumps({'accion': 'contexto', 'texto': texto}))",
  "",
].join("\n");
const SALE_CON_3 = "import sys\nsys.stdin.read()\nsys.stderr.write('primera linea\\nalgo se rompio\\n')\nsys.exit(3)\n";
const DUERME = "import os, sys, time\nopen(sys.argv[1], 'w').write(str(os.getpid()))\ntime.sleep(60)\n";
const ESPERA = [
  "import os, sys, time",
  "sys.stdin.read()",
  "fin = time.time() + 8",
  "while time.time() < fin:",
  "    if os.path.exists(sys.argv[1]):",
  "        sys.exit(0)",
  "    time.sleep(0.05)",
  "sys.stdout.write('{\"accion\": \"bloquear\", \"texto\": \"corrieron en serie\"}')",
  "",
].join("\n");
const MARCA = "import sys\nsys.stdin.read()\nopen(sys.argv[1], 'w').close()\n";

const OCUPADO = ["EPERM", "EBUSY", "ENOTEMPTY"];
const INTENTOS_DE_BORRADO = 50;

async function borrar(base: string): Promise<void> {
  for (let intento = 1; ; intento += 1) {
    try {
      rmSync(base, { recursive: true, force: true });
      return;
    } catch (fallo) {
      if (intento >= INTENTOS_DE_BORRADO || !OCUPADO.includes(String((fallo as { code?: unknown }).code))) {
        throw fallo;
      }
      await new Promise((listo) => setTimeout(listo, 200));
    }
  }
}

function conTemporal(prueba: (base: string) => Promise<void>): () => Promise<void> {
  return async () => {
    const base = mkdtempSync(join(tmpdir(), "odd-ws-nucleo-"));
    let error: unknown;
    try {
      await prueba(base);
    } catch (fallo) {
      error = fallo;
    }
    try {
      await borrar(base);
    } catch (fallo) {
      error ??= fallo;
    }
    if (error !== undefined) {
      throw error;
    }
  };
}

function pluginFalso(base: string, scripts: Record<string, string>): string {
  const raiz = join(base, "plugin");
  mkdirSync(join(raiz, "scripts"), { recursive: true });
  for (const [nombre, codigo] of Object.entries(scripts)) {
    writeFileSync(join(raiz, "scripts", nombre), codigo);
  }
  return raiz;
}

function hook(script: string, args: string[] = [], timeout = 20): Hook {
  return { script, args, timeout };
}

function lista(hooks: ListaDeHooks["hooks"], python = PYTHON): ListaDeHooks {
  return { python, pythonWindows: python, hooks };
}

async function correrUno(base: string, codigo: string, args: string[] = [], timeout = 20, python = PYTHON): Promise<Resultado> {
  const lugar = mkdtempSync(join(base, "caso-"));
  const plugin = pluginFalso(lugar, { "prueba.py": codigo });
  const resultados = await correrEvento({
    lista: lista({ tool_call: [{ hooks: [hook("prueba.py", args, timeout)] }] }, python),
    plugin,
    evento: "tool_call",
    herramienta: "bash",
    entrada: { type: "tool_call", toolName: "bash" },
    cwd: lugar,
  });
  assert.equal(resultados.length, 1);
  return resultados[0];
}

function escribirLista(base: string, texto: string): string {
  const ruta = join(base, "hooks.pi.json");
  writeFileSync(ruta, texto);
  return ruta;
}

function canonica(ruta: string): string {
  const real = realpathSync.native(ruta);
  return process.platform === "win32" ? real.toLowerCase() : real;
}

function vivo(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

test("leerLista acepta hooks.pi.json y nombra lo que no tiene la forma", conTemporal(async (base) => {
  const real = leerLista(join(PLUGIN, "hooks", "hooks.pi.json"));
  assert.equal(typeof real.python, "string");
  assert.ok(real.hooks.tool_call.length > 0);
  const sana = { python: "p3", pythonWindows: "pw", hooks: { tool_call: [{ tools: ["bash"], hooks: [hook("a.py", ["--x"], 5)] }] } };
  assert.deepEqual(leerLista(escribirLista(base, JSON.stringify(sana))), sana);
  assert.throws(() => leerLista(join(base, "no-existe.json")), /no se puede leer/);
  assert.throws(() => leerLista(escribirLista(base, "{roto")), /no es JSON/);
  const rotas: unknown[] = [
    [],
    { ...sana, python: "" },
    { ...sana, pythonWindows: 7 },
    { python: "p", pythonWindows: "p" },
    { ...sana, hooks: { tool_call: {} } },
    { ...sana, hooks: { tool_call: [{ tools: "bash", hooks: [] }] } },
    { ...sana, hooks: { tool_call: [{ tools: [""], hooks: [] }] } },
    { ...sana, hooks: { tool_call: [{ hooks: {} }] } },
    { ...sana, hooks: { tool_call: [{ hooks: [{ ...hook("a.py"), script: "../fuera.py" }] }] } },
    { ...sana, hooks: { tool_call: [{ hooks: [{ ...hook("a.py"), script: "a.sh" }] }] } },
    { ...sana, hooks: { tool_call: [{ hooks: [{ ...hook("a.py"), args: "--host pi" }] }] } },
    { ...sana, hooks: { tool_call: [{ hooks: [{ ...hook("a.py"), args: ["--plazo", 8] }] }] } },
    { ...sana, hooks: { tool_call: [{ hooks: [{ ...hook("a.py"), timeout: 0 }] }] } },
    { ...sana, hooks: { tool_call: [{ hooks: [{ ...hook("a.py"), timeout: "10" }] }] } },
  ];
  for (const rota of rotas) {
    assert.throws(() => leerLista(escribirLista(base, JSON.stringify(rota))), /no tiene la forma/, JSON.stringify(rota));
  }
}));

test("writer es opcional en la lista; si esta, es una regex que compila, y writerDe la da o dice que falta", conTemporal(async (base) => {
  const sana = { python: "p3", pythonWindows: "pw", writer: "^writer-[a-z0-9][a-z0-9-]*$", hooks: {} };
  const leida = leerLista(escribirLista(base, JSON.stringify(sana)));
  assert.deepEqual(leida, sana);
  const regex = writerDe(leida);
  assert.deepEqual(["writer-sql", "writer-", "xwriter-sql", "writer-sql\n"].map((nombre) => regex.test(nombre)), [true, false, false, false]);
  for (const rota of [{ ...sana, writer: "" }, { ...sana, writer: 7 }, { ...sana, writer: "^writer-[" }]) {
    assert.throws(() => leerLista(escribirLista(base, JSON.stringify(rota))), /no tiene la forma/, JSON.stringify(rota));
  }
  const sin = leerLista(escribirLista(base, JSON.stringify({ ...sana, writer: undefined })));
  assert.equal(sin.writer, undefined);
  assert.throws(() => writerDe(sin), /la lista de hooks no trae la regex de los writers \(writer\)/);
}));

test("pythonDe lanza pythonWindows en Windows y python en lo demas, los dos de la lista", () => {
  const propia = lista({});
  propia.python = "python-de-unix";
  propia.pythonWindows = "python-de-windows";
  assert.equal(pythonDe(propia, "win32"), "python-de-windows");
  assert.equal(pythonDe(propia, "linux"), "python-de-unix");
  assert.equal(pythonDe(propia, "darwin"), "python-de-unix");
  assert.equal(pythonDe(propia), process.platform === "win32" ? "python-de-windows" : "python-de-unix");
});

test("hooksDe elige los hooks del evento que matchean la herramienta, en el orden del archivo", () => {
  const [a, b, c] = [hook("a.py"), hook("b.py"), hook("c.py")];
  const propia = lista({ tool_call: [{ tools: ["edit", "write"], hooks: [a] }, { tools: ["bash", "edit"], hooks: [b] }, { hooks: [c] }] });
  assert.deepEqual(hooksDe(propia, "tool_call", "edit"), [a, b, c]);
  assert.deepEqual(hooksDe(propia, "tool_call", "bash"), [b, c]);
  assert.deepEqual(hooksDe(propia, "tool_call", "read"), [c]);
  assert.deepEqual(hooksDe(propia, "tool_call"), [c]);
  for (const evento of ["tool_result", "session_start", "constructor", "__proto__", "toString"]) {
    assert.deepEqual(hooksDe(propia, evento, "edit"), [], evento);
  }
});

test("lanza python con el script y sus args sin shell, el JSON por stdin y el cwd pedido", conTemporal(async (base) => {
  const raros = ["--plazo", "8", "--host", "pi", "con espacio & ; | $HOME `x` \"comillas\" 'simples' ñ"];
  const resultado = await correrUno(base, ECO, raros);
  assert.equal(resultado.tipo, "contexto");
  assert.equal(resultado.script, "prueba.py");
  const visto = JSON.parse(resultado.texto);
  assert.deepEqual(visto.entrada, { type: "tool_call", toolName: "bash" });
  assert.deepEqual(visto.args, raros);
  assert.equal(canonica(dirname(visto.cwd)), canonica(base));
  assert.match(basename(visto.cwd), /^caso-/);
}));

test("un exit 0 con stdout vacio es permitir, y un JSON valido es su accion con su texto", conTemporal(async (base) => {
  assert.deepEqual(await correrUno(base, RESPONDE, [""]), { tipo: "permitir", script: "prueba.py", texto: "" });
  for (const accion of ["bloquear", "preguntar", "contexto", "seguir"]) {
    const texto = `motivo de ${accion}: ñ y  `;
    assert.deepEqual(await correrUno(base, RESPONDE, [JSON.stringify({ accion, texto })]), { tipo: accion, script: "prueba.py", texto });
  }
}));

test("cada falla del nucleo es una falla con su motivo: python inexistente, exit distinto de 0, salida no JSON y accion desconocida",
  conTemporal(async (base) => {
    const casos: [string, () => Promise<Resultado>, RegExp][] = [
      ["python inexistente", () => correrUno(base, RESPONDE, [""], 20, "python-que-no-existe-odd-ws"),
        /no se pudo lanzar python-que-no-existe-odd-ws \(ENOENT\)/],
      ["exit 3", () => correrUno(base, SALE_CON_3), /salió con 3: algo se rompio\)\.$/],
      ["no JSON", () => correrUno(base, RESPONDE, ["esto no es json"]), /su salida no es JSON: esto no es json\)\.$/],
      ["solo un salto", () => correrUno(base, RESPONDE, ["\n"]), /su salida no es JSON/],
      ["accion desconocida", () => correrUno(base, RESPONDE, ['{"accion": "aprobar", "texto": "x"}']),
        /devolvió una acción desconocida: .*aprobar/],
      ["sin texto", () => correrUno(base, RESPONDE, ['{"accion": "bloquear"}']), /devolvió una acción desconocida/],
      ["texto que no es texto", () => correrUno(base, RESPONDE, ['{"accion": "bloquear", "texto": 7}']), /devolvió una acción desconocida/],
      ["una lista", () => correrUno(base, RESPONDE, ["[]"]), /devolvió una acción desconocida: \[\]/],
      ["un texto suelto", () => correrUno(base, RESPONDE, ['"bloquear"']), /devolvió una acción desconocida/],
    ];
    for (const [nombre, correr, motivo] of casos) {
      const resultado = await correr();
      assert.equal(resultado.tipo, "falla", nombre);
      assert.match(resultado.texto, /^odd-ws: el hook prueba\.py no pudo correr \(/, nombre);
      assert.match(resultado.texto, motivo, nombre);
    }
  }));

test("el timeout propio corta el hook a su plazo y mata el proceso", conTemporal(async (base) => {
  const archivo = join(base, "pid.txt");
  const inicio = Date.now();
  const resultado = await correrUno(base, DUERME, [archivo], 1);
  assert.equal(resultado.tipo, "falla");
  assert.match(resultado.texto, /^odd-ws: el hook prueba\.py no pudo correr \(se pasó de 1 s y se cortó\)\.$/);
  assert.ok(Date.now() - inicio < 15000, `tardó ${Date.now() - inicio} ms`);
  assert.ok(existsSync(archivo), "el hook arrancó");
  const pid = Number(readFileSync(archivo, "utf8"));
  const limite = Date.now() + 5000;
  while (vivo(pid) && Date.now() < limite) {
    await new Promise((listo) => setTimeout(listo, 100));
  }
  assert.equal(vivo(pid), false, `el proceso ${pid} sigue vivo`);
}));

test("los hooks de un evento corren en paralelo", conTemporal(async (base) => {
  const marca = join(base, "marca");
  const plugin = pluginFalso(base, { "espera.py": ESPERA, "marca.py": MARCA });
  const resultados = await correrEvento({
    lista: lista({ tool_call: [{ hooks: [hook("espera.py", [marca])] }, { hooks: [hook("marca.py", [marca])] }] }),
    plugin,
    evento: "tool_call",
    herramienta: "bash",
    entrada: {},
    cwd: base,
  });
  assert.deepEqual(resultados.map((r) => [r.tipo, r.script]), [["permitir", "espera.py"], ["permitir", "marca.py"]]);
}));

test("un evento sin hooks no lanza nada", conTemporal(async (base) => {
  const resultados = await correrEvento({
    lista: lista({ tool_call: [{ tools: ["edit"], hooks: [hook("x.py")] }] }, "python-que-no-existe-odd-ws"),
    plugin: base,
    evento: "tool_call",
    herramienta: "bash",
    entrada: {},
    cwd: base,
  });
  assert.deepEqual(resultados, []);
}));

function r(tipo: Resultado["tipo"], texto: string, script = "x.py"): Resultado {
  return { tipo, script, texto };
}

test("combinar: una falla o un bloquear gana, despues preguntar y despues contexto, y los textos se juntan en orden", () => {
  assert.deepEqual(combinar([r("contexto", "a"), r("preguntar", "b"), r("bloquear", "c")]), { tipo: "bloquear", texto: "a\n\nb\n\nc" });
  assert.deepEqual(combinar([r("contexto", "a"), r("falla", "f"), r("bloquear", "c")]), { tipo: "falla", texto: "a\n\nf\n\nc" });
  assert.deepEqual(combinar([r("permitir", ""), r("falla", "f")]), { tipo: "falla", texto: "f" });
  assert.deepEqual(combinar([r("permitir", ""), r("contexto", "a"), r("preguntar", "b")]), { tipo: "preguntar", texto: "a\n\nb" });
  assert.deepEqual(combinar([r("contexto", "a"), r("permitir", ""), r("contexto", "b")]), { tipo: "contexto", texto: "a\n\nb" });
  assert.deepEqual(combinar([r("seguir", "s"), r("preguntar", "b")]), { tipo: "seguir", texto: "s\n\nb" });
  assert.deepEqual(combinar([r("bloquear", "c"), r("seguir", "s")]), { tipo: "bloquear", texto: "c\n\ns" });
  assert.deepEqual(combinar([r("permitir", ""), r("permitir", "")]), { tipo: "permitir", texto: "" });
  assert.deepEqual(combinar([]), { tipo: "permitir", texto: "" });
});

test("contexto junta solo los textos de contexto, sin las fallas ni los bloqueos", () => {
  assert.equal(contexto([r("contexto", "a"), r("falla", "f"), r("permitir", ""), r("bloquear", "c"), r("contexto", "b")]), "a\n\nb");
  assert.equal(contexto([r("falla", "f")]), "");
  assert.equal(contexto([]), "");
});
