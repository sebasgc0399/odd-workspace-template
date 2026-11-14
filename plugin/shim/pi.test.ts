import { after, test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import extension, { ARCHIVO_DE_HOOKS, PLAZO_DE_CONFIRMACION, PLUGIN, registrar } from "./pi.ts";
import { leerLista, pythonDe } from "./nucleo.ts";

const SHIM = dirname(fileURLToPath(import.meta.url));
const BASE = mkdtempSync(join(tmpdir(), "odd-ws-pi-"));
const CONFIG_DE_GIT = join(BASE, "gitconfig");
writeFileSync(CONFIG_DE_GIT, "");
for (const clave of Object.keys(process.env)) {
  if (/^(GIT_|CLAUDE_|PYTHON)/i.test(clave)) {
    delete process.env[clave];
  }
}
process.env.GIT_CONFIG_GLOBAL = CONFIG_DE_GIT;
process.env.GIT_CONFIG_SYSTEM = CONFIG_DE_GIT;
process.env.GIT_CONFIG_NOSYSTEM = "1";
after(() => rmSync(BASE, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }));

const PYTHON = pythonDe(leerLista(join(PLUGIN, ARCHIVO_DE_HOOKS)));
const SIN_PANTALLA = "Esta sesión de Pi no tiene pantalla para pedir confirmación, así que este comando queda bloqueado";
const FALLA_EN_PRE = "Como un guard de odd-ws no pudo correr, esta herramienta queda bloqueada.";
const FALLA_EN_POST = "Como un guard de odd-ws no pudo correr, este resultado no se revisó.";
const SIN_CONFIRMAR = "No se confirmó (el usuario dijo que no, cerró el diálogo o venció el plazo de 60 s), así que este comando queda bloqueado.";
const SKILL_SQL = "---\nname: capa-sql\n---\n# capa-sql\n\n<!-- no-negociables -->\n- NN-SQL: regla uno de la capa\n<!-- /no-negociables -->\n";
const REGLAS_SQL = [
  "def verificar(ctx):",
  "    return [{\"id\": \"T-01\", \"modo\": \"bloqueo\", \"severidad\": \"CRITICAL\", \"linea\": n, \"fragmento\": \"MALO\",",
  "             \"mensaje\": \"no va, molde: x/y.sql\"} for n, t in ctx[\"agregadas\"] if \"MALO\" in t]",
  "",
].join("\n");
const ECO = [
  "import json, os, sys",
  "datos = json.loads(sys.stdin.buffer.read())",
  "sys.stdout.write(json.dumps({'accion': 'contexto', 'texto': json.dumps({'entrada': datos, 'cwd': os.getcwd()})}))",
  "",
].join("\n");
const RESPONDE = "import sys\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(sys.argv[1].encode('utf-8'))\n";

type Manejador = (evento: any, ctx: any) => unknown;

function piFalso() {
  const manejadores = new Map<string, Manejador[]>();
  return {
    on(evento: string, manejador: Manejador): void {
      manejadores.set(evento, [...(manejadores.get(evento) ?? []), manejador]);
    },
    eventos(): string[] {
      return [...manejadores.keys()];
    },
    manejador(evento: string): Manejador {
      const lista = manejadores.get(evento) ?? [];
      assert.equal(lista.length, 1, `un manejador para ${evento}`);
      return lista[0];
    },
    async emitir(evento: any, ctx: any): Promise<any> {
      const lista = manejadores.get(evento.type) ?? [];
      assert.equal(lista.length, 1, `un manejador para ${evento.type}`);
      return lista[0](evento, ctx);
    },
  };
}

interface OpcionesDelPrompt {
  customPrompt?: string;
  forceSystemPrompt?: string;
  appendSystemPrompt: string;
  sections: Record<string, string>;
}

function normalizar(base: Partial<OpcionesDelPrompt> = {}): OpcionesDelPrompt {
  return { customPrompt: base.customPrompt, forceSystemPrompt: base.forceSystemPrompt, appendSystemPrompt: base.appendSystemPrompt ?? "",
    sections: { ...(base.sections ?? {}) } };
}

function construir(opciones: OpcionesDelPrompt): string {
  if (opciones.forceSystemPrompt !== undefined) {
    return opciones.forceSystemPrompt;
  }
  const partes = [opciones.customPrompt ?? "PI-BASE"];
  if (opciones.appendSystemPrompt) {
    partes.push(`<addendum>\n${opciones.appendSystemPrompt}\n</addendum>`);
  }
  for (const [nombre, texto] of Object.entries(opciones.sections)) {
    if (texto) {
      partes.push(`<${nombre}>\n${texto}\n</${nombre}>`);
    }
  }
  return partes.join("\n\n");
}

async function turno(manejadores: Manejador[], ctx: unknown, base: Partial<OpcionesDelPrompt> = {}) {
  const opciones = normalizar(base);
  const devueltos: any[] = [];
  for (const manejador of manejadores) {
    const evento = { type: "before_agent_start", messageType: "user", prompt: "hola", get systemPrompt() { return construir(opciones); },
      systemPromptOptions: opciones };
    const devuelto: any = await manejador(evento, ctx);
    devueltos.push(devuelto);
    if (devuelto && devuelto.systemPrompt !== undefined) {
      opciones.forceSystemPrompt = devuelto.systemPrompt;
    }
  }
  return { pi: construir(opciones), puente: construir({ ...opciones, forceSystemPrompt: undefined }), devueltos, opciones };
}

const ARNES = "ARNES-DE-GENTLE-SHELL";

function comoGentleShell(evento: any): undefined {
  const opciones = evento.systemPromptOptions;
  const actual = opciones.appendSystemPrompt ?? "";
  if (!actual.includes(ARNES)) {
    opciones.appendSystemPrompt = actual ? `${actual}\n\n${ARNES}` : ARNES;
  }
  return undefined;
}

function veces(texto: string, parte: string): number {
  return texto.split(parte).length - 1;
}

interface Confirmacion {
  titulo: string;
  mensaje: string;
  opciones: unknown;
}

function ctxFalso(cwd: string, opciones: { hasUI?: boolean; sesion?: string; responder?: () => Promise<boolean> } = {}) {
  const confirmaciones: Confirmacion[] = [];
  return {
    cwd,
    hasUI: opciones.hasUI ?? false,
    mode: opciones.hasUI ? "interactive" : "print",
    sessionManager: { getSessionId: () => opciones.sesion ?? "s1" },
    ui: {
      async confirm(titulo: string, mensaje: string, extra: unknown): Promise<boolean> {
        confirmaciones.push({ titulo, mensaje, opciones: extra });
        return opciones.responder ? opciones.responder() : false;
      },
    },
    confirmaciones,
  };
}

function llamada(toolName: string, input: Record<string, unknown>) {
  return { type: "tool_call", toolCallId: "c1", toolName, input };
}

function resultado(toolName: string, input: Record<string, unknown>) {
  return { type: "tool_result", toolCallId: "c1", toolName, input, content: [{ type: "text", text: "salida de la herramienta" }],
    isError: false, details: undefined };
}

function git(carpeta: string, ...args: string[]): void {
  execFileSync("git", ["-c", "user.name=prueba", "-c", "user.email=prueba@example.com", "-c", "commit.gpgsign=false",
    "-c", "core.autocrlf=false", ...args], { cwd: carpeta, stdio: "pipe" });
}

function escribir(raiz: string, relativa: string, texto: string): void {
  mkdirSync(dirname(join(raiz, relativa)), { recursive: true });
  writeFileSync(join(raiz, relativa), texto);
}

function mundo(nombre: string) {
  const raiz = join(BASE, nombre);
  const inst = join(raiz, "inst");
  const db = join(raiz, "repos", "db");
  const api = join(raiz, "repos", "api");
  const repos: [string, Record<string, string>][] = [[inst, { "README.md": "x\n" }], [db, { "x.sql": "SELECT 1;\n" }], [api, { "a.txt": "x\n" }]];
  for (const [repo, archivos] of repos) {
    mkdirSync(repo, { recursive: true });
    git(repo, "init", "-q");
    for (const [relativa, texto] of Object.entries(archivos)) {
      escribir(repo, relativa, texto);
    }
    git(repo, "add", "-A");
    git(repo, "commit", "-q", "-m", "base");
  }
  escribir(inst, "workspace.config.json", JSON.stringify({ schema_version: 1, repos: { db: {}, api: { agent_readonly: true } },
    layers: { sql: { extensions: [".sql"], repos: ["db"] } } }));
  escribir(inst, "workspace.local.json", JSON.stringify({ repos: { db: { path: db }, api: { path: api } } }));
  escribir(inst, ".claude/skills/capa-sql/SKILL.md", SKILL_SQL);
  escribir(inst, ".claude/reglas/verificar_sql.py", REGLAS_SQL);
  escribir(db, "malo.sql", "SELECT 1; -- MALO\n");
  return { inst, db, api };
}

function pluginFalso(nombre: string, scripts: Record<string, string>, hooks: unknown, python = PYTHON): string {
  const raiz = join(BASE, nombre, "plugin");
  for (const [script, codigo] of Object.entries(scripts)) {
    escribir(raiz, join("scripts", script), codigo);
  }
  escribir(raiz, ARCHIVO_DE_HOOKS, JSON.stringify({ description: "prueba", python, pythonWindows: python, hooks }));
  return raiz;
}

function enTodo(script: string, args: string[], timeout = 20) {
  const uno = [{ hooks: [{ script, args, timeout }] }];
  return { session_start: uno, session_compact: uno, tool_call: uno, tool_result: uno };
}

function conPi(plugin?: string) {
  const pi = piFalso();
  if (plugin === undefined) {
    extension(pi);
  } else {
    registrar(pi, plugin);
  }
  return pi;
}

function aPosix(ruta: string): string {
  return ruta.replace(/\\/g, "/");
}

test("la extension registra sus cinco eventos y su plugin es la carpeta padre del shim", () => {
  assert.deepEqual(conPi().eventos().sort(), ["before_agent_start", "session_compact", "session_start", "tool_call", "tool_result"]);
  assert.equal(PLUGIN, dirname(SHIM));
  assert.equal(ARCHIVO_DE_HOOKS, "hooks/hooks.pi.json");
  assert.equal(PLAZO_DE_CONFIRMACION, 60000);
});

test("de punta a punta: git push --force se bloquea por bash y por powershell, y lo demas pasa", async () => {
  const { inst } = mundo("push");
  const pi = conPi();
  for (const herramienta of ["bash", "powershell"]) {
    const bloqueo = await pi.emitir(llamada(herramienta, { command: "git push --force origin main" }), ctxFalso(inst));
    assert.equal(bloqueo.block, true, herramienta);
    assert.match(bloqueo.reason, /^guard-comandos bloqueó el comando: /, herramienta);
    assert.equal(await pi.emitir(llamada(herramienta, { command: "git status" }), ctxFalso(inst)), undefined, herramienta);
  }
});

test("de punta a punta: el primer toque bloquea el edit y el reintento pasa; si antes hubo un read, da el contexto", async () => {
  const { inst, db } = mundo("primer-toque");
  const pi = conPi();
  const edicion = llamada("edit", { path: join(db, "x.sql"), edits: [] });
  const ctx = ctxFalso(inst, { sesion: "toque" });
  const bloqueo = await pi.emitir(edicion, ctx);
  assert.equal(bloqueo.block, true);
  assert.match(bloqueo.reason, /^primer toque \(capa-sql\): este edit no se aplicó/);
  assert.match(bloqueo.reason, /NN-SQL/);
  assert.equal(await pi.emitir(edicion, ctx), undefined, "el reintento pasa");
  const lector = ctxFalso(inst, { sesion: "lectura" });
  const leido = await pi.emitir(resultado("read", { path: join(db, "x.sql") }), lector);
  assert.equal(leido.isError, undefined);
  assert.equal(leido.content.length, 2);
  assert.deepEqual(leido.content[0], { type: "text", text: "salida de la herramienta" });
  assert.equal(leido.content[1].type, "text");
  assert.match(leido.content[1].text, /^primer toque \(capa-sql\): los no negociables/);
  assert.equal(await pi.emitir(edicion, lector), undefined, "el read ya fue el primer toque");
});

test("de punta a punta: el post con bloqueo marca el resultado como error y suma el motivo al contenido", async () => {
  const { inst, db } = mundo("post");
  const devuelto = await conPi().emitir(resultado("edit", { path: join(db, "malo.sql"), edits: [] }), ctxFalso(inst));
  assert.equal(devuelto.isError, true);
  assert.equal(devuelto.content.length, 2);
  assert.deepEqual(devuelto.content[0], { type: "text", text: "salida de la herramienta" });
  assert.equal(devuelto.content[1].type, "text");
  assert.match(devuelto.content[1].text, /T-01/);
});

test("de punta a punta: preguntar con pantalla confirma con timeout, y sin pantalla ya llega bloqueado", async () => {
  const { inst, api } = mundo("preguntar");
  const comando = `git -C ${aPosix(api)} commit -m x`;
  const pi = conPi();
  const si = ctxFalso(inst, { hasUI: true, responder: async () => true });
  assert.equal(await pi.emitir(llamada("bash", { command: comando }), si), undefined);
  assert.equal(si.confirmaciones.length, 1);
  assert.equal(si.confirmaciones[0].titulo, "odd-ws pide confirmación");
  assert.match(si.confirmaciones[0].mensaje, /^guard-comandos pregunta antes de correr el comando: .*«api»/);
  assert.deepEqual(si.confirmaciones[0].opciones, { timeout: 60000 });
  const no = ctxFalso(inst, { hasUI: true, responder: async () => false });
  const negado = await pi.emitir(llamada("bash", { command: comando }), no);
  assert.equal(negado.block, true);
  assert.equal(negado.reason, `${no.confirmaciones[0].mensaje}\n\n${SIN_CONFIRMAR}`);
  for (const raro of [undefined, "true", 1]) {
    const dudoso = ctxFalso(inst, { hasUI: true, responder: async () => raro as unknown as boolean });
    assert.deepEqual(await pi.emitir(llamada("bash", { command: comando }), dudoso),
      { block: true, reason: `${dudoso.confirmaciones[0].mensaje}\n\n${SIN_CONFIRMAR}` }, String(raro));
  }
  const fallido = ctxFalso(inst, { hasUI: true, responder: async () => { throw new Error("se cerró la pantalla"); } });
  const roto = await pi.emitir(llamada("bash", { command: comando }), fallido);
  assert.equal(roto.block, true);
  assert.match(roto.reason, /^guard-comandos pregunta antes de correr el comando: /);
  assert.match(roto.reason, /odd-ws no pudo pedir la confirmación \(se cerró la pantalla\), así que este comando queda bloqueado\.$/);
  const sin = ctxFalso(inst, { hasUI: false, responder: async () => true });
  const bloqueado = await pi.emitir(llamada("bash", { command: comando }), sin);
  assert.equal(bloqueado.block, true);
  assert.match(bloqueado.reason, /^guard-comandos pregunta antes de correr el comando: /);
  assert.ok(bloqueado.reason.includes(SIN_PANTALLA), bloqueado.reason);
  assert.equal(sin.confirmaciones.length, 0, "sin pantalla no se pregunta");
});

test("de punta a punta: el contexto de inicio llega al modelo y a un puente, y se renueva en cada inicio", async () => {
  const { inst } = mundo("inicio");
  escribir(inst, "workspace.config.json", "{roto");
  const pi = conPi();
  const ctx = ctxFalso(inst);
  const odd = pi.manejador("before_agent_start");
  const aviso = "odd-ws: la configuración de esta instancia está rota";
  const antes = await turno([odd], ctx);
  assert.deepEqual([antes.devueltos, antes.opciones.appendSystemPrompt], [[undefined], ""], "antes de iniciar no hay nada");
  assert.equal(await pi.emitir({ type: "session_start", reason: "startup" }, ctx), undefined);
  const iniciado = await turno([odd], ctx);
  assert.deepEqual(iniciado.devueltos, [undefined]);
  assert.match(iniciado.opciones.appendSystemPrompt, /^odd-ws: la configuración de esta instancia está rota/);
  assert.equal(veces(iniciado.pi, aviso), 1);
  assert.equal(veces(iniciado.puente, aviso), 1);
  await pi.emitir({ type: "session_compact", reason: "manual", compactionEntry: {}, fromExtension: false, willRetry: false }, ctx);
  assert.equal(veces((await turno([odd], ctx)).pi, aviso), 0, "compact no avisa");
  await pi.emitir({ type: "session_start", reason: "resume" }, ctx);
  assert.equal(veces((await turno([odd], ctx)).pi, aviso), 1);
  await pi.emitir({ type: "session_start", reason: "new" }, ctx);
  assert.equal(veces((await turno([odd], ctx)).pi, aviso), 0, "new es clear y no avisa");
});

const AVISO = "AVISO-DE-ODD-WS";

function conAviso(nombre: string) {
  const plugin = pluginFalso(nombre, { "x.py": RESPONDE }, enTodo("x.py", [JSON.stringify({ accion: "contexto", texto: AVISO })]));
  return conPi(plugin);
}

test("en los dos ordenes con gentle-shell, Pi y un puente que solo reenvia systemPromptOptions ven el arnes y el aviso una vez", async () => {
  const pi = conAviso("con-gentle");
  const ctx = ctxFalso(BASE);
  await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
  const odd = pi.manejador("before_agent_start");
  for (const [nombre, orden] of [["gentle-shell antes", [comoGentleShell, odd]], ["odd-ws antes", [odd, comoGentleShell]]] as [string, Manejador[]][]) {
    const visto = await turno(orden, ctx);
    assert.deepEqual(visto.devueltos, [undefined, undefined], `${nombre}: nadie fuerza el prompt`);
    assert.equal(visto.opciones.forceSystemPrompt, undefined, nombre);
    for (const [quien, texto] of [["Pi", visto.pi], ["el puente", visto.puente]]) {
      assert.equal(veces(texto, ARNES), 1, `${nombre}: ${quien} ve el arnés`);
      assert.equal(veces(texto, AVISO), 1, `${nombre}: ${quien} ve el aviso`);
    }
  }
});

test("sin el prompt forzado, el shim no devuelve systemPrompt: suma el aviso a appendSystemPrompt despues de lo que ya trae", async () => {
  const pi = conAviso("sin-forzar");
  const ctx = ctxFalso(BASE);
  await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
  const visto = await turno([pi.manejador("before_agent_start")], ctx, { appendSystemPrompt: "DE --append-system-prompt" });
  assert.deepEqual(visto.devueltos, [undefined]);
  assert.equal(visto.opciones.appendSystemPrompt, `DE --append-system-prompt\n\n${AVISO}`);
});

test("con el prompt ya forzado por otra extension, devuelve systemPrompt encadenado, y el puente igual ve el aviso", async () => {
  const pi = conAviso("forzado");
  const ctx = ctxFalso(BASE);
  await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
  const fuerza = () => ({ systemPrompt: "FORZADO-POR-OTRA" });
  const visto = await turno([fuerza, pi.manejador("before_agent_start")], ctx);
  assert.deepEqual(visto.devueltos[1], { systemPrompt: `FORZADO-POR-OTRA\n\n${AVISO}` });
  assert.equal(visto.pi, `FORZADO-POR-OTRA\n\n${AVISO}`);
  assert.equal(veces(visto.puente, AVISO), 1);
});

test("idempotencia: ni dos corridas en el mismo turno ni dos turnos seguidos duplican el aviso", async () => {
  const pi = conAviso("idempotente");
  const ctx = ctxFalso(BASE);
  await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
  const odd = pi.manejador("before_agent_start");
  for (let vuelta = 0; vuelta < 2; vuelta += 1) {
    const visto = await turno([odd, comoGentleShell, odd], ctx);
    assert.deepEqual([veces(visto.pi, AVISO), veces(visto.puente, AVISO)], [1, 1], `turno ${vuelta}`);
  }
  const primero = await turno([odd], ctx);
  const segundo = await turno([odd], ctx, primero.opciones);
  assert.deepEqual(segundo.devueltos, [undefined]);
  assert.equal(veces(segundo.opciones.appendSystemPrompt, AVISO), 1, "con las opciones del turno anterior");
  const forzado = await turno([() => ({ systemPrompt: "FORZADO" }), odd, odd], ctx);
  assert.deepEqual(forzado.devueltos.slice(1), [{ systemPrompt: `FORZADO\n\n${AVISO}` }, undefined]);
  assert.deepEqual([veces(forzado.pi, AVISO), veces(forzado.puente, AVISO)], [1, 1]);
});

test("un evento sin systemPromptOptions recibe el aviso encadenado en systemPrompt", async () => {
  const pi = conAviso("sin-opciones");
  const ctx = ctxFalso(BASE);
  await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
  assert.deepEqual(await pi.emitir({ type: "before_agent_start", systemPrompt: "P" }, ctx), { systemPrompt: `P\n\n${AVISO}` });
});

test("el JSON por stdin lleva el evento y el ctx, sin oddWs, y el hook corre en ctx.cwd", async () => {
  const plugin = pluginFalso("eco", { "eco.py": ECO }, enTodo("eco.py", ["--plazo", "8", "--host", "pi"]));
  const cwd = join(BASE, "eco", "cwd");
  mkdirSync(cwd, { recursive: true });
  const pi = conPi(plugin);
  const devuelto = await pi.emitir(resultado("read", { path: "a.txt" }), ctxFalso(cwd, { hasUI: true, sesion: "sesion-eco" }));
  const visto = JSON.parse(devuelto.content[1].text);
  assert.deepEqual(visto.entrada, { type: "tool_result", toolName: "read", input: { path: "a.txt" }, isError: false,
    ctx: { cwd, sessionId: "sesion-eco", hasUI: true, mode: "interactive" } });
  assert.equal(realpathSync.native(visto.cwd).toLowerCase(), realpathSync.native(cwd).toLowerCase());
  await pi.emitir({ type: "session_compact", reason: "threshold", compactionEntry: { x: 1 }, fromExtension: false, willRetry: true },
    ctxFalso(cwd));
  const inicio = JSON.parse((await turno([pi.manejador("before_agent_start")], ctxFalso(cwd))).opciones.appendSystemPrompt);
  assert.deepEqual(inicio.entrada, { type: "session_compact", reason: "threshold", ctx: { cwd, sessionId: "s1", hasUI: false, mode: "print" } });
});

test("cada falla del nucleo cierra el pre, y en el post marca el resultado como error", async () => {
  const casos: [string, string, Record<string, string>, unknown, RegExp][] = [
    ["python inexistente", "python-que-no-existe-odd-ws", { "x.py": RESPONDE }, enTodo("x.py", [""]), /no se pudo lanzar python-que-no-existe-odd-ws \(ENOENT\)/],
    ["timeout", PYTHON, { "x.py": "import time\ntime.sleep(60)\n" }, enTodo("x.py", [], 1), /se pasó de 1 s y se cortó/],
    ["exit 3", PYTHON, { "x.py": "import sys\nsys.exit(3)\n" }, enTodo("x.py", []), /salió con 3/],
    ["no JSON", PYTHON, { "x.py": RESPONDE }, enTodo("x.py", ["no es json"]), /su salida no es JSON/],
    ["accion desconocida", PYTHON, { "x.py": RESPONDE }, enTodo("x.py", ['{"accion": "aprobar", "texto": "x"}']), /acción desconocida/],
  ];
  for (const [nombre, python, scripts, hooks, motivo] of casos) {
    const plugin = pluginFalso(`falla-${nombre.replace(/ /g, "-")}`, scripts, hooks, python);
    const pi = conPi(plugin);
    const ctx = ctxFalso(BASE);
    const bloqueo = await pi.emitir(llamada("bash", { command: "ls" }), ctx);
    assert.equal(bloqueo.block, true, nombre);
    assert.match(bloqueo.reason, /^odd-ws: el hook x\.py no pudo correr \(/, nombre);
    assert.match(bloqueo.reason, motivo, nombre);
    assert.ok(bloqueo.reason.endsWith(`\n\n${FALLA_EN_PRE}`), nombre);
    const post = await pi.emitir(resultado("bash", { command: "ls" }), ctx);
    assert.equal(post.isError, true, nombre);
    assert.equal(post.content.length, 2, nombre);
    assert.match(post.content[1].text, motivo, nombre);
    assert.ok(post.content[1].text.endsWith(`\n\n${FALLA_EN_POST}`), nombre);
    await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
    assert.equal(await pi.emitir({ type: "before_agent_start", systemPrompt: "P" }, ctx), undefined, `${nombre}: sin contexto`);
  }
});

test("una accion fuera de lugar falla cerrada: contexto o seguir en el pre bloquean, y preguntar en el post es error", async () => {
  for (const accion of ["contexto", "seguir"]) {
    const plugin = pluginFalso(`fuera-${accion}`, { "x.py": RESPONDE }, enTodo("x.py", [JSON.stringify({ accion, texto: "fuera de lugar" })]));
    const bloqueo = await conPi(plugin).emitir(llamada("bash", { command: "ls" }), ctxFalso(BASE));
    assert.deepEqual(bloqueo, { block: true, reason: "fuera de lugar" }, accion);
  }
  const plugin = pluginFalso("fuera-preguntar", { "x.py": RESPONDE }, enTodo("x.py", [JSON.stringify({ accion: "preguntar", texto: "en post" })]));
  const post = await conPi(plugin).emitir(resultado("read", { path: "a" }), ctxFalso(BASE));
  assert.equal(post.isError, true);
  assert.equal(post.content[1].text, "en post");
});

test("un error del propio shim cierra el pre, marca el post como error y deja el inicio sin contexto", async () => {
  const roto = { ...ctxFalso(BASE), sessionManager: { getSessionId: () => { throw new Error("sesion ilegible"); } } };
  const pi = conPi();
  const bloqueo = await pi.emitir(llamada("edit", { path: "a.sql", edits: [] }), roto);
  assert.equal(bloqueo.block, true);
  assert.equal(bloqueo.reason, `odd-ws: el shim de Pi no pudo correr sus guards (sesion ilegible).\n\n${FALLA_EN_PRE}`);
  const post = await pi.emitir(resultado("read", { path: "a.sql" }), roto);
  assert.equal(post.isError, true);
  assert.equal(post.content[1].text, `odd-ws: el shim de Pi no pudo correr sus guards (sesion ilegible).\n\n${FALLA_EN_POST}`);
  await pi.emitir({ type: "session_start", reason: "startup" }, roto);
  assert.equal(await pi.emitir({ type: "before_agent_start", systemPrompt: "P" }, roto), undefined);
});

test("sin hooks.pi.json, o con uno roto, el pre se cierra y el post es error", async () => {
  const sinArchivo = join(BASE, "sin-archivo", "plugin");
  mkdirSync(sinArchivo, { recursive: true });
  const rotoPlugin = pluginFalso("archivo-roto", {}, { tool_call: [{ hooks: [{ script: "../fuera.py", args: [], timeout: 1 }] }] });
  for (const [plugin, motivo] of [[sinArchivo, /no se puede leer/], [rotoPlugin, /no tiene la forma/]] as [string, RegExp][]) {
    const pi = conPi(plugin);
    const bloqueo = await pi.emitir(llamada("bash", { command: "ls" }), ctxFalso(BASE));
    assert.equal(bloqueo.block, true);
    assert.match(bloqueo.reason, /^odd-ws: el shim de Pi no pudo correr sus guards \(/);
    assert.match(bloqueo.reason, motivo);
    const post = await pi.emitir(resultado("read", { path: "a" }), ctxFalso(BASE));
    assert.equal(post.isError, true);
    assert.match(post.content[1].text, motivo);
  }
});

test("una herramienta sin hooks pasa sin lanzar nada", async () => {
  const plugin = pluginFalso("sin-hooks", {}, { tool_call: [{ tools: ["edit"], hooks: [{ script: "x.py", args: [], timeout: 1 }] }] },
    "python-que-no-existe-odd-ws");
  const pi = conPi(plugin);
  assert.equal(await pi.emitir(llamada("grep", { pattern: "x" }), ctxFalso(BASE)), undefined);
  assert.equal(await pi.emitir(resultado("ls", { path: "." }), ctxFalso(BASE)), undefined);
});
