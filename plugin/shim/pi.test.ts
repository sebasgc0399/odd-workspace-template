import { after, test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import extension, { AGENTES_POR_EVENTO, ARCHIVO_DE_HOOKS, PLAZO_DE_CONFIRMACION, PLUGIN, registrar } from "./pi.ts";
import { leerLista, pythonDe, writerDe } from "./nucleo.ts";

const SHIM = dirname(fileURLToPath(import.meta.url));
const BASE = mkdtempSync(join(tmpdir(), "odd-ws-pi-"));
const CONFIG_DE_GIT = join(BASE, "gitconfig");
writeFileSync(CONFIG_DE_GIT, "");
for (const clave of Object.keys(process.env)) {
  if (/^(GIT_|CLAUDE_|PYTHON|GENTLE_PI_)/i.test(clave)) {
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
const MARCA_DE_ODD_WS = "[odd-ws] Lo que sigue no es parte del resultado de la herramienta: lo agrega odd-ws.";

function deOddWs(texto: string): string {
  const inicio = `\n${MARCA_DE_ODD_WS}\n`;
  assert.ok(texto.startsWith(inicio), texto);
  return texto.slice(inicio.length);
}
const SKILL_SQL = "---\nname: capa-sql\n---\n# capa-sql\n\n<!-- no-negociables -->\n- NN-SQL: regla uno de la capa\n<!-- /no-negociables -->\n";
const REGLAS_SQL = [
  "import types",
  "REGLAS = (types.SimpleNamespace(id=\"T-01\", sembrado=\"SELECT 1; -- MALO\"),)",
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
const WRITER = "^writer-[a-z0-9][a-z0-9-]*$";

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

function ctxFalso(cwd: string, opciones: { hasUI?: boolean; sesion?: string; responder?: () => Promise<boolean>; rama?: unknown[] } = {}) {
  const confirmaciones: Confirmacion[] = [];
  return {
    cwd,
    hasUI: opciones.hasUI ?? false,
    mode: opciones.hasUI ? "interactive" : "print",
    sessionManager: { getSessionId: () => opciones.sesion ?? "s1", getBranch: () => [...(opciones.rama ?? [])] },
    isProjectTrusted: () => true,
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
  const corpus = join(raiz, "corpus-vacio");
  mkdirSync(corpus, { recursive: true });
  execFileSync(PYTHON, [join(PLUGIN, "scripts", "reglas.py"), "--calibrar", "sql", corpus, "--guardar", "--raiz", inst], { stdio: "pipe" });
  escribir(db, "malo.sql", "SELECT 1; -- MALO\n");
  return { inst, db, api };
}

function pluginFalso(nombre: string, scripts: Record<string, string>, hooks: unknown, python = PYTHON, writer: string | null = WRITER): string {
  const raiz = join(BASE, nombre, "plugin");
  for (const [script, codigo] of Object.entries(scripts)) {
    escribir(raiz, join("scripts", script), codigo);
  }
  escribir(raiz, ARCHIVO_DE_HOOKS, JSON.stringify({ description: "prueba", python, pythonWindows: python, ...(writer === null ? {} : { writer }),
    hooks }));
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

const HIJO = { GENTLE_PI_AGENTS_CHILD: "1" };

function conPiEn(plugin: string, entorno: Record<string, string | undefined>) {
  const pi = piFalso();
  registrar(pi, plugin, entorno);
  return pi;
}

function aPosix(ruta: string): string {
  return ruta.replace(/\\/g, "/");
}

test("la extension registra sus siete eventos, en el padre y en el hijo, y su plugin es la carpeta padre del shim", () => {
  const siete = ["agent_before_settle", "before_agent_start", "resources_discover", "session_compact", "session_start", "tool_call", "tool_result"];
  assert.deepEqual(conPi().eventos().sort(), siete);
  assert.deepEqual(conPiEn(PLUGIN, HIJO).eventos().sort(), siete);
  assert.deepEqual(conPiEn(PLUGIN, { GENTLE_PI_AGENTS_CHILD: "0" }).eventos().sort(), conPi().eventos().sort(), "un 0 no es un hijo");
  assert.equal(PLUGIN, dirname(SHIM));
  assert.equal(ARCHIVO_DE_HOOKS, "hooks/hooks.pi.json");
  assert.equal(PLAZO_DE_CONFIRMACION, 60000);
  assert.deepEqual(AGENTES_POR_EVENTO, { before_agent_start: ["principal"], agent_before_settle: ["writer", "principal"] });
});

test("la extension define CLAUDE_PLUGIN_ROOT con la carpeta del plugin para los comandos de las skills, y no pisa uno que ya estaba", () => {
  const sinVariable: Record<string, string | undefined> = {};
  conPiEn(PLUGIN, sinVariable);
  assert.equal(sinVariable.CLAUDE_PLUGIN_ROOT, PLUGIN);
  const vacia: Record<string, string | undefined> = { CLAUDE_PLUGIN_ROOT: "" };
  conPiEn(PLUGIN, vacia);
  assert.equal(vacia.CLAUDE_PLUGIN_ROOT, PLUGIN);
  const otra: Record<string, string | undefined> = { CLAUDE_PLUGIN_ROOT: "/home/u/otro-plugin" };
  conPiEn(PLUGIN, otra);
  assert.equal(otra.CLAUDE_PLUGIN_ROOT, "/home/u/otro-plugin");
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

test("de punta a punta: bash_background y monitor de gentle-shell pasan por guard_comandos como bash: el push por refspec se bloquea y git status pasa", async () => {
  const { inst } = mundo("push-de-fondo");
  const pi = conPi();
  const extras: [string, Record<string, unknown>][] = [["bash", {}], ["bash_background", { label: "push" }], ["monitor", { timeout_seconds: 30 }]];
  for (const [herramienta, extra] of extras) {
    const bloqueo = await pi.emitir(llamada(herramienta, { ...extra, command: "git push origin +main" }), ctxFalso(inst));
    assert.equal(bloqueo?.block, true, herramienta);
    assert.match(bloqueo.reason, /^guard-comandos bloqueó el comando: git push con un refspec "\+"/, herramienta);
    assert.equal(await pi.emitir(llamada(herramienta, { ...extra, command: "git status" }), ctxFalso(inst)), undefined, herramienta);
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
  assert.match(deOddWs(leido.content[1].text), /^primer toque \(capa-sql\): los no negociables/);
  assert.equal(await pi.emitir(edicion, lector), undefined, "el read ya fue el primer toque");
});

test("lo que odd-ws suma al resultado abre con su marca, porque Pi junta los bloques en un solo texto", async () => {
  const { inst, db } = mundo("marca");
  const leido = await conPi().emitir(resultado("read", { path: join(db, "x.sql") }), ctxFalso(inst, { sesion: "marca" }));
  assert.equal(leido.isError, undefined);
  assert.equal(leido.content.length, 2);
  assert.deepEqual(leido.content[0], { type: "text", text: "salida de la herramienta" });
  assert.ok(leido.content[1].text.startsWith(`\n${MARCA_DE_ODD_WS}\nprimer toque (capa-sql): los no negociables`), leido.content[1].text);
  const devuelto = await conPi().emitir(resultado("edit", { path: join(db, "malo.sql"), edits: [] }), ctxFalso(inst));
  assert.equal(devuelto.isError, true);
  assert.ok(devuelto.content[1].text.startsWith(`\n${MARCA_DE_ODD_WS}\n`), devuelto.content[1].text);
  assert.match(devuelto.content[1].text, /T-01/);
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
  const visto = JSON.parse(deOddWs(devuelto.content[1].text));
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
  assert.equal(deOddWs(post.content[1].text), "en post");
});

test("un error del propio shim cierra el pre, marca el post como error y deja el inicio sin contexto", async () => {
  const roto = { ...ctxFalso(BASE), sessionManager: { getSessionId: () => { throw new Error("sesion ilegible"); } } };
  const pi = conPi();
  const bloqueo = await pi.emitir(llamada("edit", { path: "a.sql", edits: [] }), roto);
  assert.equal(bloqueo.block, true);
  assert.equal(bloqueo.reason, `odd-ws: el shim de Pi no pudo correr sus guards (sesion ilegible).\n\n${FALLA_EN_PRE}`);
  const post = await pi.emitir(resultado("read", { path: "a.sql" }), roto);
  assert.equal(post.isError, true);
  assert.equal(deOddWs(post.content[1].text), `odd-ws: el shim de Pi no pudo correr sus guards (sesion ilegible).\n\n${FALLA_EN_POST}`);
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

const MARCA_SQL = "<!-- odd-ws:agente writer-sql -->";
const MARCA_WEB = "<!-- odd-ws:agente writer-web -->";
const SIGUE = "writer-stop: todavía no puedes cerrar.";
const GUARDA = [
  "import json, sys",
  "datos = json.loads(sys.stdin.buffer.read())",
  "with open(sys.argv[1], 'a', encoding='utf-8') as f:",
  "    f.write(json.dumps(datos) + '\\n')",
  "sys.stdout.write(json.dumps({'accion': sys.argv[2], 'texto': sys.argv[3]}) if sys.argv[2] else '')",
  "",
].join("\n");
const RESULTADO_OK = "## Resultado\nestado: ok\nregla: ninguna\nintento: ninguno\npresupuesto: x.sql, techo 10 líneas\nreales: x\n"
  + "arbol: sucio (x.sql)\nverificacion:\n- python x: ok\nlimites:\n- no cubre la base\n";

const LARGO_DE_ETIQUETA = 72;

function etiquetaDeGentlePi(prompt: string): string {
  const primera = prompt.split("\n").map((linea) => linea.trim()).find((linea) => linea.length > 0) ?? "";
  const oracion = primera.split(/(?<=[.!?])\s/)[0] ?? primera;
  const compacta = oracion.replace(/\s+/g, " ").replace(/[.:]$/, "");
  return compacta.length > LARGO_DE_ETIQUETA ? `${compacta.slice(0, LARGO_DE_ETIQUETA - 1)}…` : compacta;
}

function promptDeGentlePi(entrada: { task: string; context?: string }): string {
  return entrada.context ? `${entrada.task}\n\n## Context\n${entrada.context}` : entrada.task;
}

function lanzamiento(input: unknown, toolName = "subagent_run") {
  return { type: "tool_call", toolCallId: "c9", toolName, input };
}

function turnoDelHijo(prompt: string) {
  return { type: "before_agent_start", messageType: "user", prompt, systemPrompt: "P", systemPromptOptions: { appendSystemPrompt: "" } };
}

function delUsuario(contenido: unknown) {
  return { type: "message", id: "m1", parentId: null, timestamp: "2026-11-13T00:00:00.000Z", message: { role: "user", content: contenido, timestamp: 1 } };
}

function delAsistente(...textos: string[]) {
  return { role: "assistant", content: [{ type: "thinking", thinking: "pienso" }, ...textos.map((text) => ({ type: "text", text }))], stopReason: "stop" };
}

function asentarse(mensajes: unknown[], extra: Record<string, unknown> = {}) {
  return { type: "agent_before_settle", outcome: "completed", entries: [], continue: false,
    context: { contextEntries: [], contextMessages: mensajes, llmMessages: mensajes, pendingMessages: [], canContinue: false }, ...extra };
}

function compuerta(nombre: string, accion: string, opciones: { python?: string; writer?: string | null; codigo?: string; timeout?: number } = {}) {
  const registro = join(BASE, nombre, "payloads.jsonl");
  const plugin = pluginFalso(nombre, { "stop.py": opciones.codigo ?? GUARDA },
    { agent_before_settle: [{ agente: "writer", hooks: [{ script: "stop.py", args: [registro, accion, SIGUE], timeout: opciones.timeout ?? 20 }] }] },
    opciones.python ?? PYTHON, opciones.writer === undefined ? WRITER : opciones.writer);
  return { plugin, registro };
}

const REVISA = "revisar-turno: todavía no cierres el turno.";

function delTurno(nombre: string, accion: string, opciones: { codigo?: string; timeout?: number; alEmpezar?: string } = {}) {
  const registros = { writer: join(BASE, nombre, "writer.jsonl"), inicio: join(BASE, nombre, "inicio.jsonl"), cierre: join(BASE, nombre, "cierre.jsonl") };
  const guarda = (registro: string, decision: string, texto: string, script = "stop.py") =>
    [{ script, args: [registro, decision, texto], timeout: opciones.timeout ?? 20 }];
  const plugin = pluginFalso(nombre, { "stop.py": GUARDA, "turno.py": opciones.codigo ?? GUARDA }, {
    before_agent_start: [{ agente: "principal", hooks: guarda(registros.inicio, opciones.alEmpezar ?? "", "", "turno.py") }],
    agent_before_settle: [{ agente: "writer", hooks: guarda(registros.writer, "seguir", SIGUE) },
      { agente: "principal", hooks: guarda(registros.cierre, accion, REVISA, "turno.py") }],
  });
  return { plugin, registros };
}

function payloads(registro: string): any[] {
  return existsSync(registro) ? readFileSync(registro, "utf8").split("\n").filter((linea) => linea !== "").map((linea) => JSON.parse(linea)) : [];
}

async function oddWsVisto(pi: ReturnType<typeof piFalso>, ctx: unknown): Promise<unknown> {
  return JSON.parse(deOddWs((await pi.emitir(resultado("read", { path: "a" }), ctx)).content[1].text)).entrada.oddWs;
}

test("la regex de los writers sale de hooks.pi.json y reconoce los mismos nombres que la de Python", () => {
  const regex = writerDe(leerLista(join(PLUGIN, ARCHIVO_DE_HOOKS)));
  assert.equal(regex.source, WRITER);
  const writers = ["writer-sql", "writer-web", "writer-a-b", "writer-9", "writer-x-"];
  const otros = ["writer-", "writer-Web", "Writer-web", "xwriter-web", "writer--x", "writer-web ", "revisor-web", "odd-ws:writer-web",
    "writer_web", "Explore", "writer-web\n"];
  assert.deepEqual(writers.map((nombre) => regex.test(nombre)), writers.map(() => true));
  assert.deepEqual(otros.map((nombre) => regex.test(nombre)), otros.map(() => false));
});

test("en el padre, subagent_run de un writer lleva su marca en la ultima linea de la tarea, y el de otro agente no", async () => {
  const pi = conPi();
  const ctx = ctxFalso(BASE);
  const writer = { agent: "writer-sql", task: "Cambia x.sql", label: "cambiar x", mode: "task" };
  assert.equal(await pi.emitir(lanzamiento(writer), ctx), undefined);
  assert.deepEqual(writer, { agent: "writer-sql", task: `Cambia x.sql\n${MARCA_SQL}`, label: "cambiar x", mode: "task" });
  const otro = { agent: "explorador", task: "Mira x.sql", context: "sin apuro" };
  assert.equal(await pi.emitir(lanzamiento(otro), ctx), undefined);
  assert.deepEqual(otro, { agent: "explorador", task: "Mira x.sql", context: "sin apuro" });
  for (const casi of ["writer-", "Writer-sql", "writer-sql ", "xwriter-sql", "writer_sql"]) {
    const entrada = { agent: casi, task: "t" };
    assert.equal(await pi.emitir(lanzamiento(entrada), ctx), undefined, casi);
    assert.equal(entrada.task, "t", casi);
  }
  const nieto = { agent: "writer-web", task: `${MARCA_SQL}\nHaz y` };
  assert.equal(await conPiEn(PLUGIN, HIJO).emitir(lanzamiento(nieto), ctx), undefined);
  assert.equal(nieto.task, `Haz y\n${MARCA_WEB}`, "un hijo que lanza también marca, con el nombre de lo que lanza");
});

test("la marca no cambia la etiqueta ni la primera linea que gentle-pi saca de la tarea", async () => {
  const pi = conPi();
  const ctx = ctxFalso(BASE);
  const larga = `Revisa ${"cada consulta del archivo ".repeat(4)}y deja todo igual`;
  const tareas = ["Cambia x.sql. Luego corre la prueba.", "\n\n  Primera parte: con dos puntos:\nsegunda línea", "Usa la plantilla /arreglar\nmás",
    larga, "Una sola línea sin punto"];
  for (const tarea of tareas) {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: tarea };
    assert.equal(await pi.emitir(lanzamiento(entrada), ctx), undefined, tarea);
    const marcada = entrada.task as string;
    assert.equal(etiquetaDeGentlePi(marcada), etiquetaDeGentlePi(tarea), tarea);
    assert.ok(marcada.startsWith(tarea), `la tarea empieza igual: ${JSON.stringify(marcada)}`);
    assert.equal("label" in entrada, false, "no inventa una etiqueta");
    const aviso = `Subagent writer-sql (task t1, "${etiquetaDeGentlePi(marcada)}") finished.`;
    assert.doesNotMatch(aviso, /odd-ws/, aviso);
  }
  assert.equal(etiquetaDeGentlePi("Cambia x.sql. Luego corre la prueba."), "Cambia x.sql", "la regla copiada da lo que da gentle-pi");
});

test("un writer con la tarea en blanco no se marca, para que gentle-pi lo rechace como antes", async () => {
  const pi = conPi();
  const ctx = ctxFalso(BASE);
  const blancas: Record<string, unknown>[] = [{ agent: "writer-sql", task: "" }, { agent: "writer-sql", task: "   " },
    { agent: "writer-sql", task: "\n\t \r\n" }, { agent: "writer-sql", task: "", context: "algo de contexto" },
    { agent: "writer-sql", task: MARCA_SQL }, { agent: "writer-sql", task: ` ${MARCA_WEB}\n` }];
  for (const entrada of blancas) {
    const antes = JSON.stringify(entrada);
    assert.equal(await pi.emitir(lanzamiento(entrada), ctx), undefined, antes);
    assert.equal((entrada.task as string).trim(), "", `gentle-pi la rechaza por vacía: ${antes} -> ${JSON.stringify(entrada.task)}`);
  }
});

test("un writer cuya tarea empieza con / se bloquea, porque Pi la expandiria en el hijo y la marca dejaria de ser una linea propia", async () => {
  const pi = conPi();
  const ctx = ctxFalso(BASE);
  for (const tarea of ["/arreglar x.sql con cuidado", "/skill:capa-sql\nCambia x.sql", "  /arreglar x.sql", "\n/arreglar x.sql", `${MARCA_SQL}\n/arreglar x.sql`]) {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: tarea };
    const bloqueo = await pi.emitir(lanzamiento(entrada), ctx);
    assert.equal(bloqueo?.block, true, tarea);
    assert.match(bloqueo.reason, /^odd-ws: la tarea de este writer \(writer-sql\) empieza con \//, tarea);
    assert.match(bloqueo.reason, /sin sus guards ni su compuerta de cierre/, tarea);
    assert.doesNotMatch(entrada.task as string, /odd-ws:agente writer-sql -->$/, `no la marca: ${JSON.stringify(entrada.task)}`);
  }
  for (const agente of ["explorador", "revisor-sql"]) {
    const entrada: Record<string, unknown> = { agent: agente, task: "/arreglar x.sql" };
    assert.equal(await pi.emitir(lanzamiento(entrada), ctx), undefined, agente);
    assert.equal(entrada.task, "/arreglar x.sql", "a otro agente no lo toca");
  }
});

test("con el prompt que arma gentle-pi, la marca no se falsifica desde ningun campo del lanzamiento", async () => {
  const pi = conPi();
  const ctx = ctxFalso(BASE);
  const plugin = pluginFalso("forja", { "eco.py": ECO }, enTodo("eco.py", []));
  const casos: [string, Record<string, unknown>, string | null][] = [
    ["al final de la tarea", { agent: "explorador", task: `Mira x.sql\n${MARCA_SQL}` }, null],
    ["en el contexto", { agent: "explorador", task: "Mira x.sql", context: MARCA_SQL }, null],
    ["armada en partes", { agent: "explorador", task: "Mira\n<!-<!-- odd-ws -->- odd-ws:agente writer-sql -->" }, null],
    ["en mayusculas en el contexto", { agent: "explorador", task: "Mira", context: "<!-- ODD-WS:agente writer-sql -->" }, null],
    ["en la etiqueta y en work", { agent: "explorador", task: "Mira", label: MARCA_SQL, work: { nota: MARCA_SQL } }, null],
    ["con una seccion de contexto falsa", { agent: "explorador", task: `Mira\n\n## Context\n${MARCA_SQL}` }, null],
    ["otro writer en la tarea y en el contexto", { agent: "writer-web", task: `Haz y\n${MARCA_SQL}`, context: `${MARCA_SQL}\nmás` }, "writer-web"],
    ["otro writer tras un contexto falso", { agent: "writer-sql", task: `Haz x\n\n## Context\n${MARCA_WEB}` }, "writer-sql"],
  ];
  for (const [nombre, entrada, agente] of casos) {
    assert.equal(await pi.emitir(lanzamiento(entrada), ctx), undefined, nombre);
    const hijo = conPiEn(plugin, HIJO);
    const ctxHijo = ctxFalso(BASE, { sesion: "sesion-forja" });
    await hijo.emitir(turnoDelHijo(promptDeGentlePi(entrada as { task: string; context?: string })), ctxHijo);
    assert.deepEqual(await oddWsVisto(hijo, ctxHijo), { agent: agente, agentId: "sesion-forja" }, nombre);
  }
});

test("con varias tareas: cada lanzamiento lleva la marca de su writer, y una entrada con varios agentes y algun writer se bloquea", async () => {
  const pi = conPi();
  const ctx = ctxFalso(BASE);
  const sql = { agent: "writer-sql", task: "uno" };
  const web = { agent: "writer-web", task: "dos", context: "tres" };
  await pi.emitir(lanzamiento(sql), ctx);
  await pi.emitir(lanzamiento(web), ctx);
  assert.deepEqual([sql.task, web.task, web.context], [`uno\n${MARCA_SQL}`, `dos\n${MARCA_WEB}`, "tres"]);
  const varias: unknown[] = [
    { agent: "explorador", task: "x", agents: ["writer-sql"] },
    { tasks: [{ agent: "explorador", task: "x" }, { agent: "writer-sql", task: "y" }] },
    { agent: "writer-sql", task: "x", tasks: [{ agent: "writer-web", task: "y" }] },
    { agent: "writer-sql", task: "x", extra: { agents: "writer-web" } },
  ];
  for (const entrada of varias) {
    const antes = JSON.stringify(entrada);
    const bloqueo = await pi.emitir(lanzamiento(entrada), ctx);
    assert.equal(bloqueo.block, true, antes);
    assert.match(bloqueo.reason, /^odd-ws: este subagent_run lanza un writer \(writer-(sql|web)\), pero su entrada no tiene la forma /, antes);
    assert.equal(JSON.stringify(entrada), antes, "lo que bloquea no se toca");
  }
  const sinWriter = { tasks: [{ agent: "explorador", task: `${MARCA_SQL}\nx` }, { agent: "revisor", task: "y" }] };
  assert.equal(await pi.emitir(lanzamiento(sinWriter), ctx), undefined);
  assert.deepEqual(sinWriter, { tasks: [{ agent: "explorador", task: "x" }, { agent: "revisor", task: "y" }] });
});

test("la marca que haya escrito el modelo se borra de la tarea y del contexto, sea del agente que sea, aunque venga armada en partes", async () => {
  const pi = conPi();
  const ctx = ctxFalso(BASE);
  const casos: [Record<string, unknown>, Record<string, unknown>][] = [
    [{ agent: "explorador", task: `${MARCA_SQL}\nMira x.sql` }, { agent: "explorador", task: "Mira x.sql" }],
    [{ agent: "explorador", task: "a <!--odd-ws:agente writer-sql--> b", context: `${MARCA_WEB}\nc` }, { agent: "explorador", task: "a b", context: "c" }],
    [{ agent: "explorador", task: "<!-<!-- odd-ws -->- odd-ws:agente writer-sql -->\nMira" }, { agent: "explorador", task: "Mira" }],
    [{ agent: "explorador", task: "<!-- ODD-WS:Agente writer-sql -->\r\nMira" }, { agent: "explorador", task: "Mira" }],
    [{ agent: "writer-web", task: `${MARCA_SQL}\nHaz y` }, { agent: "writer-web", task: `Haz y\n${MARCA_WEB}` }],
    [{ agent: "writer-web", task: "Haz y", context: `nota ${MARCA_SQL}` }, { agent: "writer-web", task: `Haz y\n${MARCA_WEB}`, context: "nota " }],
    [{ agent: "explorador", task: "un <!-- comentario --> normal" }, { agent: "explorador", task: "un <!-- comentario --> normal" }],
  ];
  for (const [entrada, esperada] of casos) {
    const antes = JSON.stringify(entrada);
    assert.equal(await pi.emitir(lanzamiento(entrada), ctx), undefined, antes);
    assert.deepEqual(entrada, esperada, antes);
  }
  for (const [herramienta, campo] of [["subagent_continue", "prompt"], ["subagent_send_message", "message"]]) {
    const entrada = { task_id: "t1", [campo]: `${MARCA_SQL}\nsigue` };
    assert.equal(await pi.emitir(lanzamiento(entrada, herramienta), ctx), undefined, herramienta);
    assert.deepEqual(entrada, { task_id: "t1", [campo]: "sigue" }, herramienta);
  }
  const escritura = { path: "nota.md", content: `${MARCA_SQL}\nla marca, documentada` };
  assert.equal(await conPi(pluginFalso("marca-en-write", {}, {})).emitir(llamada("write", escritura), ctx), undefined);
  assert.equal(escritura.content, `${MARCA_SQL}\nla marca, documentada`, "las demas herramientas no se tocan");
});

test("si lanza un writer y no lo puede marcar, bloquea el lanzamiento con el motivo", async () => {
  const ctx = ctxFalso(BASE);
  const pi = conPi();
  for (const entrada of [{ agent: "writer-sql", task: ["x"] }, { agent: "writer-sql" }, { agent: "writer-sql", task: "x", context: 7 }]) {
    const antes = JSON.stringify(entrada);
    const bloqueo = await pi.emitir(lanzamiento(entrada), ctx);
    assert.equal(bloqueo.block, true, antes);
    assert.match(bloqueo.reason, /^odd-ws: este subagent_run lanza un writer \(writer-sql\), pero su entrada no tiene la forma que odd-ws sabe marcar/, antes);
    assert.match(bloqueo.reason, /sin la marca, el writer correría sin sus guards ni su compuerta de cierre\.$/, antes);
    assert.equal(JSON.stringify(entrada), antes);
  }
  const sinRegex = conPi(pluginFalso("sin-regex", {}, {}, PYTHON, null));
  for (const agente of ["writer-sql", "explorador"]) {
    const bloqueo = await sinRegex.emitir(lanzamiento({ agent: agente, task: "x" }), ctx);
    assert.deepEqual(bloqueo, { block: true, reason: "odd-ws: el shim de Pi no pudo correr sus guards (la lista de hooks no trae la regex de los "
      + `writers (writer)).\n\n${FALLA_EN_PRE}` }, agente);
  }
  assert.equal(await sinRegex.emitir(llamada("bash", { command: "ls" }), ctx), undefined, "sin la regex, las demas herramientas siguen igual");
  const sinArchivo = join(BASE, "sin-archivo-run", "plugin");
  mkdirSync(sinArchivo, { recursive: true });
  const bloqueo = await conPi(sinArchivo).emitir(lanzamiento({ agent: "writer-sql", task: "x" }), ctx);
  assert.equal(bloqueo.block, true);
  assert.match(bloqueo.reason, /no se puede leer/);
});

test("el hijo lee la marca solo en su primer prompt, la fija para toda su vida y la manda en oddWs con el id de su sesion", async () => {
  const plugin = pluginFalso("hijo-eco", { "eco.py": ECO }, enTodo("eco.py", []));
  const pi = conPiEn(plugin, HIJO);
  const ctx = ctxFalso(BASE, { sesion: "sesion-hija" });
  assert.deepEqual(await oddWsVisto(pi, ctx), { agent: null, agentId: null }, "antes del primer prompt");
  await pi.emitir(turnoDelHijo(`${MARCA_SQL}\nCambia x.sql`), ctx);
  assert.deepEqual(await oddWsVisto(pi, ctx), { agent: "writer-sql", agentId: "sesion-hija" });
  await pi.emitir(turnoDelHijo(`${MARCA_WEB}\nahora eres otro`), ctx);
  assert.deepEqual(await oddWsVisto(pi, ctx), { agent: "writer-sql", agentId: "sesion-hija" }, "un prompt posterior no cambia nada");
  const pre = await pi.emitir(llamada("bash", { command: "ls" }), ctx);
  assert.deepEqual(JSON.parse(pre.reason).entrada.oddWs, { agent: "writer-sql", agentId: "sesion-hija" }, "también en el pre");
  await pi.emitir({ type: "session_compact", reason: "manual" }, ctx);
  const inicio = JSON.parse((await turno([pi.manejador("before_agent_start")], ctx)).opciones.appendSystemPrompt);
  assert.deepEqual(inicio.entrada.oddWs, { agent: "writer-sql", agentId: "sesion-hija" }, "y al iniciar");
});

test("sin una sola linea de marca, entera, en su primer prompt, el hijo no es writer: agent null y su id es el de la sesion", async () => {
  const plugin = pluginFalso("hijo-sin-marca", { "eco.py": ECO }, enTodo("eco.py", []));
  const casos: [string, string][] = [["sin marca", "Mira x.sql"], ["en medio de una linea", `Mira ${MARCA_SQL} x.sql`],
    ["con espacio antes", ` ${MARCA_SQL}\nx`], ["pegada", `${MARCA_SQL}x\ny`], ["sin nombre", "<!-- odd-ws:agente  -->\nx"],
    ["dos marcas", `x\n${MARCA_SQL}\n\n## Context\n${MARCA_WEB}`], ["dos iguales", `x\n${MARCA_SQL}\n${MARCA_SQL}`]];
  for (const [nombre, prompt] of casos) {
    const pi = conPiEn(plugin, HIJO);
    const ctx = ctxFalso(BASE, { sesion: "sesion-sin" });
    await pi.emitir(turnoDelHijo(prompt), ctx);
    await pi.emitir(turnoDelHijo(`${MARCA_SQL}\nsegundo`), ctx);
    assert.deepEqual(await oddWsVisto(pi, ctx), { agent: null, agentId: "sesion-sin" }, nombre);
  }
  for (const [nombre, prompt] of [["al final", `Cambia x.sql\n${MARCA_SQL}`], ["antes del contexto", `Cambia x.sql\n${MARCA_SQL}\n\n## Context\nnada`],
    ["con CRLF", `Cambia x.sql\r\n${MARCA_SQL}\r\n`]]) {
    const pi = conPiEn(plugin, HIJO);
    const ctx = ctxFalso(BASE, { sesion: "sesion-con" });
    await pi.emitir(turnoDelHijo(prompt), ctx);
    assert.deepEqual(await oddWsVisto(pi, ctx), { agent: "writer-sql", agentId: "sesion-con" }, nombre);
  }
  const padre = conPiEn(plugin, {});
  await padre.emitir(turnoDelHijo(`${MARCA_SQL}\nx`), ctxFalso(BASE));
  const visto = JSON.parse(deOddWs((await padre.emitir(resultado("read", { path: "a" }), ctxFalso(BASE))).content[1].text)).entrada;
  assert.equal("oddWs" in visto, false, "el padre no manda oddWs");
});

test("en una continuacion, otro proceso sobre la misma sesion, la identidad sale del primer mensaje del usuario de la sesion", async () => {
  const plugin = pluginFalso("continuacion", { "eco.py": ECO }, enTodo("eco.py", []));
  const casos: [string, unknown[], string, string | null][] = [
    ["writer retomado", [{ type: "session_info", id: "i" }, delUsuario([{ type: "text", text: `${MARCA_SQL}\nCambia x.sql` }]),
      { type: "message", message: delAsistente("listo") }, delUsuario("segunda")], "Sigue con lo que falta", "writer-sql"],
    ["contenido de texto", [delUsuario(`${MARCA_SQL}\nCambia`)], "Sigue", "writer-sql"],
    ["no era writer", [delUsuario("Mira x.sql")], `${MARCA_SQL}\nahora sí`, null],
    ["sesion nueva", [], `${MARCA_SQL}\nprimero`, "writer-sql"],
  ];
  for (const [nombre, rama, prompt, agente] of casos) {
    const pi = conPiEn(plugin, HIJO);
    const ctx = ctxFalso(BASE, { sesion: "sesion-retomada", rama });
    await pi.emitir(turnoDelHijo(prompt), ctx);
    assert.deepEqual(await oddWsVisto(pi, ctx), { agent: agente, agentId: "sesion-retomada" }, nombre);
  }
});

test("la compuerta del hijo writer: seguir agrega la entrada de odd-ws y continue: true una sola vez, con el ultimo mensaje y continued", async () => {
  const { plugin, registro } = compuerta("compuerta-seguir", "seguir");
  const pi = conPiEn(plugin, HIJO);
  const ctx = ctxFalso(BASE, { sesion: "sesion-w" });
  await pi.emitir(turnoDelHijo(`${MARCA_SQL}\nCambia x.sql`), ctx);
  const previa = { type: "custom", customType: "de-otra", data: 1 };
  const primero = await pi.emitir(asentarse([{ role: "user", content: "hola" }, delAsistente("parte uno", "parte dos")], { entries: [previa] }), ctx);
  assert.deepEqual(primero, { entries: [previa, { type: "custom_message", customType: "odd-ws", content: SIGUE, display: true }], continue: true });
  const segundo = await pi.emitir(asentarse([delAsistente("viejo"), { role: "user", content: SIGUE }, delAsistente("de nuevo"),
    { role: "toolResult", content: [] }]), ctx);
  assert.equal(segundo, undefined, "solo una vez");
  const tercero = await pi.emitir(asentarse([delAsistente("otro turno")]), ctx);
  assert.equal(tercero.continue, true, "después de dejar cerrar, el cierre siguiente vuelve a contar");
  const odd = (lastAssistantMessage: string, continued: boolean) => ({ type: "agent_before_settle",
    ctx: { cwd: BASE, sessionId: "sesion-w", hasUI: false, mode: "print" },
    oddWs: { agent: "writer-sql", agentId: "sesion-w", lastAssistantMessage, continued } });
  assert.deepEqual(payloads(registro), [odd("parte uno\nparte dos", false), odd("de nuevo", true), odd("otro turno", false)]);
});

test("si la compuerta misma falla, el writer cierra, como con un SubagentStop que no corre", async () => {
  const casos: [string, { plugin: string; registro: string }][] = [
    ["python inexistente", compuerta("cae-python", "seguir", { python: "python-que-no-existe-odd-ws" })],
    ["exit 3", compuerta("cae-exit", "seguir", { codigo: "import sys\nsys.exit(3)\n" })],
    ["timeout", compuerta("cae-timeout", "seguir", { codigo: "import time\ntime.sleep(60)\n", timeout: 1 })],
    ["salida rota", compuerta("cae-salida", "seguir", { codigo: "import sys\nsys.stdin.read()\nprint('no es json')\n" })],
    ["accion fuera de lugar", compuerta("cae-bloquear", "bloquear")],
    ["sin la regex de los writers", compuerta("cae-regex", "seguir", { writer: null })],
  ];
  const roto = join(BASE, "cae-lista", "plugin");
  escribir(roto, ARCHIVO_DE_HOOKS, "{roto");
  casos.push(["hooks.pi.json roto", { plugin: roto, registro: join(BASE, "cae-lista", "nada.jsonl") }]);
  for (const [nombre, { plugin }] of casos) {
    const pi = conPiEn(plugin, HIJO);
    const ctx = ctxFalso(BASE, { sesion: "sesion-cae" });
    await pi.emitir(turnoDelHijo(`${MARCA_SQL}\nx`), ctx);
    assert.equal(await pi.emitir(asentarse([delAsistente("Listo.")]), ctx), undefined, nombre);
  }
  const { plugin, registro } = compuerta("cae-sesion", "seguir");
  const pi = conPiEn(plugin, HIJO);
  await pi.emitir(turnoDelHijo(`${MARCA_SQL}\nx`), ctxFalso(BASE));
  const sinSesion = { ...ctxFalso(BASE), sessionManager: { getSessionId: () => { throw new Error("sesion ilegible"); }, getBranch: () => [] } };
  assert.equal(await pi.emitir(asentarse([delAsistente("Listo.")]), sinSesion), undefined, "un error del propio shim");
  assert.deepEqual(payloads(registro), []);
});

test("la compuerta no corre si el hijo no es writer, si otra extension ya pidio seguir, ni en el padre", async () => {
  const { plugin, registro } = compuerta("compuerta-quieta", "seguir");
  for (const prompt of ["Mira x.sql", "<!-- odd-ws:agente explorador -->\nMira x.sql"]) {
    const noWriter = conPiEn(plugin, HIJO);
    await noWriter.emitir(turnoDelHijo(prompt), ctxFalso(BASE));
    assert.equal(await noWriter.emitir(asentarse([delAsistente("x")]), ctxFalso(BASE)), undefined, prompt);
  }
  const writer = conPiEn(plugin, HIJO);
  await writer.emitir(turnoDelHijo(`${MARCA_SQL}\nx`), ctxFalso(BASE));
  const previa = { type: "custom_message", customType: "otra", content: "sigue", display: false };
  assert.equal(await writer.emitir(asentarse([delAsistente("x")], { entries: [previa], continue: true }), ctxFalso(BASE)), undefined);
  assert.deepEqual(payloads(registro), [], "writer_stop no se lanzó");
  assert.equal((await writer.emitir(asentarse([delAsistente("x")]), ctxFalso(BASE))).continue, true, "el cierre de verdad sí corre");
  assert.deepEqual(writer.eventos().sort(), ["agent_before_settle", "before_agent_start", "resources_discover", "session_compact",
    "session_start", "tool_call", "tool_result"]);
  assert.equal(payloads(registro).length, 1);
  const padre = conPiEn(plugin, {});
  await padre.emitir(turnoDelHijo(`${MARCA_SQL}\nx`), ctxFalso(BASE));
  assert.equal(await padre.emitir(asentarse([delAsistente("x")]), ctxFalso(BASE)), undefined, "el padre no corre la compuerta del writer");
  assert.equal(payloads(registro).length, 1, "writer_stop no se lanzó en el padre");
});

test("en el padre, el cierre corre solo el grupo del principal con child false, el ultimo mensaje y continued, y sigue una vez por turno", async () => {
  const { plugin, registros } = delTurno("turno-seguir", "seguir");
  const pi = conPiEn(plugin, {});
  const ctx = ctxFalso(BASE, { sesion: "sesion-p" });
  await pi.emitir(turnoDelHijo("Cambia x.sql"), ctx);
  const previa = { type: "custom", customType: "de-gentle-ai", data: 1 };
  const primero = await pi.emitir(asentarse([{ role: "user", content: "hola" }, delAsistente("parte uno", "parte dos")], { entries: [previa] }), ctx);
  assert.deepEqual(primero, { entries: [previa, { type: "custom_message", customType: "odd-ws", content: REVISA, display: true }], continue: true });
  assert.equal(await pi.emitir(asentarse([delAsistente("corregido")]), ctx), undefined, "una sola vuelta por turno");
  const odd = (lastAssistantMessage: string, continued: boolean) => ({ type: "agent_before_settle",
    ctx: { cwd: BASE, sessionId: "sesion-p", hasUI: false, mode: "print" }, oddWs: { child: false, lastAssistantMessage, continued } });
  assert.deepEqual(payloads(registros.cierre), [odd("parte uno\nparte dos", false), odd("corregido", true)]);
  assert.deepEqual(payloads(registros.writer), [], "el padre nunca corre writer_stop");
  const ajena = await pi.emitir(asentarse([delAsistente("x")], { entries: [previa], continue: true }), ctx);
  assert.equal(ajena, undefined, "si otra extensión ya pidió seguir, el padre no corre la revisión");
  assert.equal(payloads(registros.cierre).length, 2);
  for (const outcome of ["error", "aborted", undefined]) {
    assert.equal(await pi.emitir(asentarse([delAsistente("x")], { outcome }), ctx), undefined, String(outcome));
  }
  assert.equal(payloads(registros.cierre).length, 2, "un cierre que no es completed no revisa");
});

test("en el hijo writer, el cierre corre solo writer_stop y nunca la revision del turno, y el hijo no saca la foto", async () => {
  const { plugin, registros } = delTurno("turno-hijo", "seguir");
  const pi = conPiEn(plugin, HIJO);
  const ctx = ctxFalso(BASE, { sesion: "sesion-h" });
  await pi.emitir(turnoDelHijo(`${MARCA_SQL}\nCambia x.sql`), ctx);
  assert.deepEqual(payloads(registros.inicio), [], "el hijo no corre el inicio del turno");
  const frenado = await pi.emitir(asentarse([delAsistente("Listo.")]), ctx);
  assert.deepEqual(frenado.entries.map((entrada: any) => entrada.content), [SIGUE]);
  assert.deepEqual(payloads(registros.writer).map((carga) => carga.oddWs), [{ agent: "writer-sql", agentId: "sesion-h",
    lastAssistantMessage: "Listo.", continued: false }], "el payload del writer no cambia");
  assert.deepEqual(payloads(registros.cierre), []);
});

test("en el padre, before_agent_start corre el grupo del principal antes de devolver el prompt, sin oddWs ni el prompt", async () => {
  const { plugin, registros } = delTurno("turno-inicio", "", { alEmpezar: "" });
  const pi = conPiEn(plugin, {});
  const ctx = ctxFalso(BASE, { sesion: "sesion-i" });
  const visto = await turno([pi.manejador("before_agent_start")], ctx);
  assert.deepEqual(visto.devueltos, [undefined]);
  assert.deepEqual(payloads(registros.inicio), [{ type: "before_agent_start", ctx: { cwd: BASE, sessionId: "sesion-i", hasUI: false, mode: "print" } }],
    "la foto ya está cuando el turno arranca");
  await turno([pi.manejador("before_agent_start")], ctx);
  assert.equal(payloads(registros.inicio).length, 2, "cada turno saca su foto");
});

test("en el padre, una falla del inicio del turno no frena el turno ni cambia el prompt", async () => {
  const casos: [string, { codigo?: string; timeout?: number; alEmpezar?: string }][] = [
    ["exit 3", { codigo: "import sys\nsys.stdin.read()\nsys.exit(3)\n" }],
    ["timeout", { codigo: "import time\ntime.sleep(60)\n", timeout: 1 }],
    ["una accion fuera de lugar", { alEmpezar: "bloquear" }],
  ];
  for (const [nombre, opciones] of casos) {
    const { plugin } = delTurno(`turno-inicio-${nombre.replace(/ /g, "-")}`, "seguir", opciones);
    const pi = conPiEn(plugin, {});
    assert.deepEqual(await pi.emitir({ type: "before_agent_start", systemPrompt: "P" }, ctxFalso(BASE)), undefined, nombre);
  }
  const roto = { ...ctxFalso(BASE), sessionManager: { getSessionId: () => { throw new Error("sesion ilegible"); } } };
  const { plugin } = delTurno("turno-inicio-roto", "seguir");
  assert.equal(await conPiEn(plugin, {}).emitir({ type: "before_agent_start", systemPrompt: "P" }, roto), undefined);
});

test("en el padre, una falla de la revision deja cerrar el turno, y un turno nuevo vuelve a contar la vuelta", async () => {
  const casos: [string, { codigo?: string; timeout?: number }][] = [
    ["exit 3", { codigo: "import sys\nsys.stdin.read()\nsys.exit(3)\n" }],
    ["timeout", { codigo: "import time\ntime.sleep(60)\n", timeout: 1 }],
  ];
  for (const [nombre, opciones] of casos) {
    const { plugin } = delTurno(`turno-cae-${nombre.replace(/ /g, "-")}`, "seguir", opciones);
    assert.equal(await conPiEn(plugin, {}).emitir(asentarse([delAsistente("Listo.")]), ctxFalso(BASE)), undefined, nombre);
  }
  const { plugin, registros } = delTurno("turno-nuevo", "seguir");
  const pi = conPiEn(plugin, {});
  const ctx = ctxFalso(BASE);
  await pi.emitir(turnoDelHijo("uno"), ctx);
  assert.equal((await pi.emitir(asentarse([delAsistente("uno")]), ctx)).continue, true);
  await pi.emitir(turnoDelHijo("dos"), ctx);
  assert.equal((await pi.emitir(asentarse([delAsistente("dos")]), ctx)).continue, true,
    "si la continuación no llegó a cerrar, el turno siguiente igual tiene su vuelta");
  assert.deepEqual(payloads(registros.cierre).map((carga) => carga.oddWs.continued), [false, false]);
});

test("la compuerta corre solo en un cierre completed, como el handler de gentle-ai, y otro desenlace corta la cadena de continued", async () => {
  const { plugin, registro } = compuerta("compuerta-desenlace", "seguir");
  const pi = conPiEn(plugin, HIJO);
  const ctx = ctxFalso(BASE, { sesion: "sesion-d" });
  await pi.emitir(turnoDelHijo(`x\n${MARCA_SQL}`), ctx);
  for (const outcome of ["error", "aborted", undefined]) {
    assert.equal(await pi.emitir(asentarse([delAsistente("x")], { outcome }), ctx), undefined, String(outcome));
  }
  assert.deepEqual(payloads(registro), [], "writer_stop no se lanzó");
  assert.equal((await pi.emitir(asentarse([delAsistente("uno")]), ctx)).continue, true);
  assert.equal(await pi.emitir(asentarse([delAsistente("falló")], { outcome: "error" }), ctx), undefined);
  assert.equal((await pi.emitir(asentarse([delAsistente("de nuevo")]), ctx)).continue, true, "tras un error, el cierre siguiente vuelve a contar");
  assert.deepEqual(payloads(registro).map((carga) => carga.oddWs.continued), [false, false]);
});

test("de punta a punta, padre e hijo con los hooks reales: el writer marcado anota en la bitacora y writer_stop lo frena con un cierre malo y lo deja cerrar con uno bueno", async () => {
  const { inst, db } = mundo("writer-de-punta");
  const sql = join(db, "x.sql");
  const padre = conPi();
  const hijo = async (sesion: string) => {
    const entrada = { agent: "writer-sql", task: "Agrega una consulta a x.sql", context: "es una prueba" };
    assert.equal(await padre.emitir(lanzamiento(entrada), ctxFalso(inst, { sesion: "padre" })), undefined);
    const pi = conPiEn(PLUGIN, HIJO);
    const ctx = ctxFalso(inst, { sesion });
    await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
    await pi.emitir(turnoDelHijo(`${entrada.task}\n\n## Context\n${entrada.context}`), ctx);
    return { pi, ctx };
  };
  const escribirX = async (pi: ReturnType<typeof piFalso>, ctx: unknown, texto: string) => {
    const escritura = llamada("write", { path: sql, content: texto });
    assert.match((await pi.emitir(escritura, ctx)).reason, /^primer toque \(capa-sql\)/);
    assert.equal(await pi.emitir(escritura, ctx), undefined, "el reintento pasa");
    writeFileSync(sql, texto);
    await pi.emitir(resultado("write", { path: sql, content: texto }), ctx);
  };
  const malo = await hijo("hija-mala");
  const commit = await malo.pi.emitir(llamada("bash", { command: `git -C ${aPosix(db)} commit -am x` }), malo.ctx);
  assert.match(commit.reason, /^writer-guard bloqueó el comando\. `git [^`]*commit[^`]*`: los writers no commitean/, "writer_guard aplica las reglas del writer");
  await escribirX(malo.pi, malo.ctx, "SELECT 1;\nSELECT 2; -- MALO\n");
  const fotos = join(inst, ".claude", "estado", "writers", "hija-mala", "hija-mala.fotos");
  const bitacora = readFileSync(join(fotos, "bitacora.jsonl"), "ascii").split("\n").filter((linea) => linea !== "").map((linea) => JSON.parse(linea));
  assert.deepEqual(bitacora.filter((registro) => registro.tipo === "edicion"), [{ tipo: "edicion", rutas: [sql] }, { tipo: "edicion", rutas: [sql] }]);
  const frenado = await malo.pi.emitir(asentarse([delAsistente("Listo.")]), malo.ctx);
  assert.equal(frenado.continue, true);
  assert.equal(frenado.entries.length, 1);
  assert.deepEqual([frenado.entries[0].type, frenado.entries[0].customType, frenado.entries[0].display], ["custom_message", "odd-ws", true]);
  assert.match(frenado.entries[0].content, /^writer-stop: todavía no puedes cerrar\./);
  assert.match(frenado.entries[0].content, /T-01/);
  assert.match(frenado.entries[0].content, /## Resultado/);
  assert.equal(await malo.pi.emitir(asentarse([delAsistente("Listo, de nuevo.")]), malo.ctx), undefined, "el segundo cierre pasa");
  assert.equal(existsSync(fotos), false, "al dejar cerrar, writer_stop borra las fotos y la bitácora");
  const bueno = await hijo("hija-buena");
  await escribirX(bueno.pi, bueno.ctx, "SELECT 1;\nSELECT 2;\nSELECT 3;\n");
  assert.equal(await bueno.pi.emitir(asentarse([delAsistente(`Hecho.\n\n${RESULTADO_OK}`)]), bueno.ctx), undefined, "con un cierre bueno cierra a la primera");
  const sidecar = JSON.parse(readFileSync(join(inst, ".claude", "estado", "writers", "hija-buena", "hija-buena.json"), "utf8"));
  assert.deepEqual([sidecar.agent_type, sidecar.agent_id, sidecar.formato_ok, sidecar.archivos, sidecar.stop_hook_active],
    ["writer-sql", "hija-buena", true, [sql], false]);
  assert.equal(existsSync(join(inst, ".claude", "estado", "turnos")), false, "el hijo nunca saca la foto del turno ni la revisa");
});

test("de punta a punta, el padre con los hooks reales: saca la foto al empezar, y revisar_turno lo hace seguir una vez por un archivo de capa escrito por fuera", async () => {
  const { inst, db } = mundo("turno-de-punta");
  const pi = conPi();
  const ctx = ctxFalso(inst, { sesion: "padre-turno" });
  await pi.emitir({ type: "session_start", reason: "startup" }, ctx);
  await turno([pi.manejador("before_agent_start")], ctx);
  const foto = join(inst, ".claude", "estado", "turnos", "padre-turno");
  assert.ok(existsSync(join(foto, "manifiesto.json")), "la foto ya está cuando el turno arranca");
  writeFileSync(join(db, "x.sql"), "SELECT 1;\nSELECT 2; -- MALO\n");
  const frenado = await pi.emitir(asentarse([delAsistente("Listo.")]), ctx);
  assert.equal(frenado?.continue, true, JSON.stringify(frenado));
  assert.deepEqual([frenado.entries.length, frenado.entries[0].customType, frenado.entries[0].display], [1, "odd-ws", true]);
  assert.match(frenado.entries[0].content, /^revisar-turno: todavía no cierres el turno\./);
  assert.match(frenado.entries[0].content, /T-01/);
  assert.match(frenado.entries[0].content, /si este cambio no es tuyo, avísale al usuario y no lo toques/);
  assert.doesNotMatch(frenado.entries[0].content, /malo\.sql/, "lo que ya estaba sucio al empezar no es del turno");
  assert.equal(await pi.emitir(asentarse([delAsistente("Visto.")]), ctx), undefined, "una sola vuelta por turno");
  assert.equal(existsSync(foto), false, "al dejar cerrar, la revisión borra la foto");
});

test("de punta a punta, el hijo writer: writer_guard le aplica sus reglas en bash_background y monitor, y anota sus comandos en la bitacora", async () => {
  const { inst, db } = mundo("writer-de-fondo");
  const entrada = { agent: "writer-sql", task: "Revisa x.sql" };
  assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(inst, { sesion: "padre" })), undefined);
  const hijo = conPiEn(PLUGIN, HIJO);
  const ctx = ctxFalso(inst, { sesion: "hija-de-fondo" });
  await hijo.emitir(turnoDelHijo(entrada.task), ctx);
  const extras: [string, Record<string, unknown>][] = [["bash_background", { label: "x" }], ["monitor", { timeout_seconds: 5 }]];
  for (const [herramienta, extra] of extras) {
    const commit = await hijo.emitir(llamada(herramienta, { ...extra, command: `git -C ${aPosix(db)} commit -am x` }), ctx);
    assert.match(commit?.reason ?? "", /^writer-guard bloqueó el comando\. `git [^`]*commit[^`]*`: los writers no commitean/, herramienta);
    assert.equal(await hijo.emitir(llamada(herramienta, { ...extra, command: `ls -la ${herramienta}` }), ctx), undefined, herramienta);
  }
  const bitacora = join(inst, ".claude", "estado", "writers", "hija-de-fondo", "hija-de-fondo.fotos", "bitacora.jsonl");
  const registros = existsSync(bitacora) ? readFileSync(bitacora, "ascii").split("\n").filter((linea) => linea !== "").map((linea) => JSON.parse(linea)) : [];
  assert.deepEqual(registros, [{ tipo: "shell", comando: "ls -la bash_background", dialecto: "posix" },
    { tipo: "shell", comando: "ls -la monitor", dialecto: "posix" }]);
});

function hayGitArriba(desde: string): boolean {
  for (let actual = dirname(desde); ; actual = dirname(actual)) {
    if (existsSync(join(actual, ".git"))) {
      return true;
    }
    if (dirname(actual) === actual) {
      return false;
    }
  }
}

const AFUERA = /ahí sus guards y su compuerta de cierre no encuentran la instancia/;
const OTRA = /ahí sus guards y su compuerta de cierre usarían la config y el estado de esa otra instancia, no los de esta/;

test("en el padre, un writer con repository_root fuera de la instancia se bloquea con el writer, el repository_root y la raiz, sin marcar", async () => {
  const { inst, db } = mundo("raiz-afuera");
  const pi = conPi();
  const entrada: Record<string, unknown> = { agent: "writer-sql", task: "Cambia x.sql", repository_root: db };
  const antes = JSON.stringify(entrada);
  const bloqueo = await pi.emitir(lanzamiento(entrada), ctxFalso(inst));
  assert.equal(bloqueo?.block, true);
  assert.ok(bloqueo.reason.startsWith(`odd-ws: este writer (writer-sql) se lanza con repository_root ${db}, fuera de la raíz de la instancia (${inst}): `),
    bloqueo.reason);
  assert.match(bloqueo.reason, AFUERA);
  assert.match(bloqueo.reason, /Relánzalo sin repository_root: el writer edita los archivos de los repos por su ruta absoluta/);
  assert.equal(JSON.stringify(entrada), antes, "lo que bloquea no se marca");
  const relanzado: Record<string, unknown> = { agent: "writer-sql", task: "Cambia x.sql" };
  assert.equal(await pi.emitir(lanzamiento(relanzado), ctxFalso(inst)), undefined, "sin repository_root corre en la raíz de la instancia");
  assert.equal(relanzado.task, `Cambia x.sql\n${MARCA_SQL}`);
  const desdeSubcarpeta = await pi.emitir(lanzamiento({ agent: "writer-sql", task: "x", repository_root: db }), ctxFalso(join(inst, "tickets", "uno")));
  assert.equal(desdeSubcarpeta?.block, true, "la raíz de la instancia se busca subiendo desde ctx.cwd");
});

test("en el padre, un writer con repository_root dentro de la instancia pasa y se marca", async () => {
  const { inst } = mundo("raiz-adentro");
  const anidado = join(inst, "repos", "propio");
  mkdirSync(anidado, { recursive: true });
  git(anidado, "init", "-q");
  const pi = conPi();
  for (const raiz of [anidado, inst]) {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "Cambia x.sql", repository_root: raiz };
    assert.equal(await pi.emitir(lanzamiento(entrada), ctxFalso(inst)), undefined, raiz);
    assert.equal(entrada.task, `Cambia x.sql\n${MARCA_SQL}`, raiz);
  }
  for (const vacio of ["", 7, null]) {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x", repository_root: vacio };
    assert.equal(await pi.emitir(lanzamiento(entrada), ctxFalso(inst)), undefined, String(vacio));
    assert.equal(entrada.task, `x\n${MARCA_SQL}`, "un repository_root vacío o que no es texto no mueve el cwd: gentle-shell lo ignora o lo rechaza");
  }
});

test("en Windows, repository_root se compara con la raiz de la instancia sin distinguir mayusculas", { skip: process.platform !== "win32" }, async () => {
  const { inst } = mundo("raiz-mayusculas");
  const anidado = join(inst, "repos", "propio");
  mkdirSync(anidado, { recursive: true });
  for (const raiz of [anidado.toUpperCase(), anidado.toLowerCase(), join(inst.toUpperCase(), "repos", "NUEVO")]) {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x", repository_root: raiz };
    assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(inst.toLowerCase())), undefined, raiz);
    assert.equal(entrada.task, `x\n${MARCA_SQL}`, raiz);
  }
});

test("la raiz de la instancia y el repository_root se comparan por su ruta canonica: un enlace a la instancia no la saca de ella", async () => {
  const { inst, db } = mundo("raiz-enlace");
  const enlace = join(BASE, "raiz-enlace", "enlace-a-inst");
  symlinkSync(inst, enlace, "junction");
  const anidado = join(inst, "repos", "propio");
  mkdirSync(anidado, { recursive: true });
  const pi = conPi();
  const adentro: Record<string, unknown> = { agent: "writer-sql", task: "x", repository_root: realpathSync(anidado) };
  assert.equal(await pi.emitir(lanzamiento(adentro), ctxFalso(enlace)), undefined);
  assert.equal(adentro.task, `x\n${MARCA_SQL}`);
  const porElEnlace: Record<string, unknown> = { agent: "writer-sql", task: "x", repository_root: join(enlace, "repos", "propio") };
  assert.equal(await pi.emitir(lanzamiento(porElEnlace), ctxFalso(inst)), undefined);
  const afuera = await pi.emitir(lanzamiento({ agent: "writer-sql", task: "x", repository_root: db }), ctxFalso(enlace));
  assert.equal(afuera?.block, true);
  assert.match(afuera.reason, AFUERA);
});

test("en el padre, un agente que no es writer con repository_root fuera de la instancia pasa sin tocarse", async () => {
  const { inst, db } = mundo("raiz-otro-agente");
  for (const agente of ["explorador", "revisor-sql", "writer-", "Writer-sql"]) {
    const entrada: Record<string, unknown> = { agent: agente, task: "Mira x.sql", repository_root: db };
    const antes = JSON.stringify(entrada);
    assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(inst)), undefined, agente);
    assert.equal(JSON.stringify(entrada), antes, agente);
  }
});

test("si el padre no esta en una instancia, un writer con repository_root se marca como antes, sin bloqueo nuevo", async () => {
  const { db, api } = mundo("raiz-sin-instancia");
  const afuera = join(BASE, "raiz-sin-instancia", "repos");
  for (const raiz of [db, api, afuera]) {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "Cambia x.sql", repository_root: raiz };
    assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(api)), undefined, raiz);
    assert.equal(entrada.task, `Cambia x.sql\n${MARCA_SQL}`, raiz);
  }
});

test("en el padre, un writer con workspace_root en un worktree fuera de la instancia se bloquea, y dentro de ella pasa", async () => {
  const { inst } = mundo("worktree");
  const fuera = join(BASE, "worktree", "inst-wt");
  git(inst, "worktree", "add", "-q", "-b", "rama-wt", fuera);
  const pi = conPi();
  const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x", workspace_root: fuera };
  const bloqueo = await pi.emitir(lanzamiento(entrada), ctxFalso(inst));
  assert.equal(bloqueo?.block, true);
  assert.ok(bloqueo.reason.startsWith(`odd-ws: este writer (writer-sql) se lanza con workspace_root ${fuera} (gentle-shell lo correría en `),
    bloqueo.reason);
  assert.match(bloqueo.reason, /fuera de la raíz de la instancia/);
  assert.match(bloqueo.reason, AFUERA);
  assert.match(bloqueo.reason, /Relánzalo sin workspace_root/);
  assert.equal(entrada.task, "x");
  const dentro: Record<string, unknown> = { agent: "writer-sql", task: "x", workspace_root: join(inst, "tickets") };
  assert.equal(await pi.emitir(lanzamiento(dentro), ctxFalso(inst)), undefined, "gentle-shell lo corre en la raíz del worktree, que es la instancia");
  assert.equal(dentro.task, `x\n${MARCA_SQL}`);
});

async function conHome<T>(home: string, correr: () => Promise<T>): Promise<T> {
  const previos = { HOME: process.env.HOME, USERPROFILE: process.env.USERPROFILE };
  process.env.HOME = home;
  process.env.USERPROFILE = home;
  try {
    return await correr();
  } finally {
    for (const [clave, valor] of Object.entries(previos)) {
      if (valor === undefined) {
        delete process.env[clave];
      } else {
        process.env[clave] = valor;
      }
    }
  }
}

test("un workspace_root escrito con @, ~/ o ~/.. se lee como lo lee gentle-shell: hacia un worktree afuera se bloquea desde la raiz, una subcarpeta y un enlace", async () => {
  const { inst } = mundo("worktree-tilde");
  const home = join(BASE, "worktree-tilde", "casa");
  mkdirSync(home, { recursive: true });
  const fuera = join(BASE, "worktree-tilde", "inst-wt");
  const enCasa = join(home, "inst-wt-casa");
  git(inst, "worktree", "add", "-q", "-b", "rama-fuera", fuera);
  git(inst, "worktree", "add", "-q", "-b", "rama-casa", enCasa);
  mkdirSync(join(inst, "tickets"), { recursive: true });
  const enlace = join(BASE, "worktree-tilde", "enlace-a-inst");
  symlinkSync(inst, enlace, "junction");
  await conHome(home, async () => {
    const casos: [string, string][] = [[`@${fuera}`, fuera], ["~/inst-wt-casa", enCasa], ["~/../inst-wt", fuera]];
    for (const desde of [inst, join(inst, "tickets"), enlace]) {
      for (const [valor, destino] of casos) {
        const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x", workspace_root: valor };
        const bloqueo = await conPi().emitir(lanzamiento(entrada), ctxFalso(desde));
        assert.equal(bloqueo?.block, true, `${desde} ${valor}`);
        assert.ok(bloqueo.reason.startsWith(`odd-ws: este writer (writer-sql) se lanza con workspace_root ${valor} (gentle-shell lo correría en `
          + `${realpathSync.native(destino)}), fuera de la raíz de la instancia (`), bloqueo.reason);
        assert.match(bloqueo.reason, AFUERA);
        assert.equal(entrada.task, "x", `${desde} ${valor}`);
      }
    }
    for (const valor of [`@${join(inst, "tickets")}`, "@tickets", "@."]) {
      const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x", workspace_root: valor };
      assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(inst)), undefined, valor);
      assert.equal(entrada.task, `x\n${MARCA_SQL}`, valor);
    }
  });
});

test("un worktree enlazado dentro de la instancia (.worktrees/feat) se bloquea: sus guards encontrarian la config versionada del worktree", async () => {
  const { inst } = mundo("worktree-adentro");
  git(inst, "add", "workspace.config.json");
  git(inst, "commit", "-q", "-m", "config");
  const feat = join(inst, ".worktrees", "feat");
  git(inst, "worktree", "add", "-q", "-b", "feat", feat);
  assert.ok(existsSync(join(feat, "workspace.config.json")) && !existsSync(join(feat, "workspace.local.json")));
  const pi = conPi();
  for (const valor of [feat, join(feat, "sub")]) {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x", workspace_root: valor };
    const bloqueo = await pi.emitir(lanzamiento(entrada), ctxFalso(inst));
    assert.equal(bloqueo?.block, true, valor);
    assert.ok(bloqueo.reason.startsWith(`odd-ws: este writer (writer-sql) se lanza con workspace_root ${valor} (gentle-shell lo correría en `
      + `${realpathSync.native(feat)}), donde sus guards encuentran otra instancia (${realpathSync.native(feat)}) y no esta (${inst}): `), bloqueo.reason);
    assert.match(bloqueo.reason, OTRA);
    assert.match(bloqueo.reason, /Relánzalo sin workspace_root/);
    assert.equal(entrada.task, "x", valor);
  }
  const sinSelector: Record<string, unknown> = { agent: "writer-sql", task: "x" };
  assert.equal(await pi.emitir(lanzamiento(sinSelector), ctxFalso(inst)), undefined, "sin selector corre en la raíz de la instancia");
  assert.equal(sinSelector.task, `x\n${MARCA_SQL}`);
});

test("un repository_root en una instancia anidada se bloquea: sus guards usarian la config de la anidada y no la del padre", async () => {
  const { inst } = mundo("instancia-anidada");
  const anidada = instancia(join(inst, "sub", "otra"), false);
  git(anidada, "init", "-q");
  const propio = join(inst, "repos", "propio");
  mkdirSync(propio, { recursive: true });
  git(propio, "init", "-q");
  const pi = conPi();
  const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x", repository_root: anidada };
  const bloqueo = await pi.emitir(lanzamiento(entrada), ctxFalso(inst));
  assert.equal(bloqueo?.block, true);
  assert.ok(bloqueo.reason.startsWith(`odd-ws: este writer (writer-sql) se lanza con repository_root ${anidada}, donde sus guards encuentran otra `
    + `instancia (${realpathSync.native(anidada)}) y no esta (${inst}): `), bloqueo.reason);
  assert.match(bloqueo.reason, OTRA);
  assert.equal(entrada.task, "x");
  const enUnRepoPropio: Record<string, unknown> = { agent: "writer-sql", task: "x", repository_root: propio };
  assert.equal(await pi.emitir(lanzamiento(enUnRepoPropio), ctxFalso(inst)), undefined, "un repo propio sin instancia sigue siendo esta instancia");
  assert.equal(enUnRepoPropio.task, `x\n${MARCA_SQL}`);
  const desdeLaAnidada: Record<string, unknown> = { agent: "writer-sql", task: "x" };
  assert.equal(await pi.emitir(lanzamiento(desdeLaAnidada), ctxFalso(anidada)), undefined, "el padre en la anidada corre al hijo en ella");
  assert.equal(desdeLaAnidada.task, `x\n${MARCA_SQL}`);
});

test("sin selector, gentle-shell corre al writer en la raiz del repo git: con la instancia en una subcarpeta del repo, se bloquea", async () => {
  const repo = join(BASE, "monorepo");
  mkdirSync(repo, { recursive: true });
  git(repo, "init", "-q");
  const inst = instancia(join(repo, "equipo", "inst"), false);
  const pi = conPi();
  const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x" };
  const bloqueo = await pi.emitir(lanzamiento(entrada), ctxFalso(inst));
  assert.equal(bloqueo?.block, true);
  assert.ok(bloqueo.reason.startsWith(`odd-ws: gentle-shell correría este writer (writer-sql) en ${realpathSync.native(repo)}, la raíz del repo git que contiene la instancia, `
    + `fuera de la raíz de la instancia (${inst}): `), bloqueo.reason);
  assert.match(bloqueo.reason, AFUERA);
  assert.match(bloqueo.reason, /En gentle-shell, un writer necesita que la instancia sea la raíz de su repo git, o que no esté dentro de ninguno\.$/);
  assert.equal(entrada.task, "x");
  assert.equal(await pi.emitir(lanzamiento({ agent: "explorador", task: "x" }), ctxFalso(inst)), undefined, "a otro agente no lo toca");
  const conWorkspace: Record<string, unknown> = { agent: "writer-sql", task: "x", workspace_root: inst };
  const porWorkspace = await pi.emitir(lanzamiento(conWorkspace), ctxFalso(inst));
  assert.equal(porWorkspace?.block, true, "workspace_root dentro de la instancia, pero gentle-shell corre al hijo en la raíz de su repo");
  assert.ok(porWorkspace.reason.startsWith(`odd-ws: este writer (writer-sql) se lanza con workspace_root ${inst} (gentle-shell lo correría en `
    + `${realpathSync.native(repo)}), fuera de la raíz de la instancia (${inst}): `), porWorkspace.reason);
  assert.equal(conWorkspace.task, "x");
  git(inst, "init", "-q");
  const conRepoPropio: Record<string, unknown> = { agent: "writer-sql", task: "x" };
  assert.equal(await pi.emitir(lanzamiento(conRepoPropio), ctxFalso(inst)), undefined, "con su propio repo, la raíz de git es la instancia");
  assert.equal(conRepoPropio.task, `x\n${MARCA_SQL}`);
});

test("una carpeta .git cuenta como raiz git solo si tiene HEAD, objects y refs, como git; un .git archivo sigue contando", async () => {
  const repo = join(BASE, "monorepo-git-invalido");
  mkdirSync(repo, { recursive: true });
  git(repo, "init", "-q");
  const bloqueado = async (inst: string) => {
    const bloqueo = await conPi().emitir(lanzamiento({ agent: "writer-sql", task: "x" }), ctxFalso(inst));
    assert.equal(bloqueo?.block, true, inst);
    assert.ok(bloqueo.reason.startsWith(`odd-ws: gentle-shell correría este writer (writer-sql) en ${realpathSync.native(repo)}, la raíz del repo git que contiene la instancia, `), bloqueo.reason);
  };
  const pasa = async (inst: string) => {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x" };
    assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(inst)), undefined, inst);
    assert.equal(entrada.task, `x\n${MARCA_SQL}`);
  };
  const vacia = instancia(join(repo, "vacia"), false);
  mkdirSync(join(vacia, ".git"));
  await bloqueado(vacia);
  const sinObjects = instancia(join(repo, "sin-objects"), false);
  mkdirSync(join(sinObjects, ".git", "refs"), { recursive: true });
  writeFileSync(join(sinObjects, ".git", "HEAD"), "ref: refs/heads/main\n");
  await bloqueado(sinObjects);
  const sinHead = instancia(join(repo, "sin-head"), false);
  mkdirSync(join(sinHead, ".git", "refs"), { recursive: true });
  mkdirSync(join(sinHead, ".git", "objects"));
  await bloqueado(sinHead);
  const sinRefs = instancia(join(repo, "sin-refs"), false);
  mkdirSync(join(sinRefs, ".git", "objects"), { recursive: true });
  writeFileSync(join(sinRefs, ".git", "HEAD"), "ref: refs/heads/main\n");
  await bloqueado(sinRefs);
  const headCarpeta = instancia(join(repo, "head-carpeta"), false);
  mkdirSync(join(headCarpeta, ".git", "HEAD"), { recursive: true });
  mkdirSync(join(headCarpeta, ".git", "objects"));
  mkdirSync(join(headCarpeta, ".git", "refs"));
  await bloqueado(headCarpeta);
  const conCommondir = instancia(join(repo, "con-commondir"), false);
  mkdirSync(join(conCommondir, ".git"), { recursive: true });
  writeFileSync(join(conCommondir, ".git", "HEAD"), "ref: refs/heads/main\n");
  writeFileSync(join(conCommondir, ".git", "commondir"), join(repo, ".git"));
  await pasa(conCommondir);
  const objectsArchivo = instancia(join(repo, "objects-archivo"), false);
  mkdirSync(join(objectsArchivo, ".git", "refs"), { recursive: true });
  writeFileSync(join(objectsArchivo, ".git", "HEAD"), "ref: refs/heads/main\n");
  writeFileSync(join(objectsArchivo, ".git", "objects"), "");
  if (process.platform === "win32") {
    await pasa(objectsArchivo);
  } else {
    await bloqueado(objectsArchivo);
  }
  const headEnlace = instancia(join(repo, "head-enlace"), false);
  mkdirSync(join(headEnlace, ".git", "objects"), { recursive: true });
  mkdirSync(join(headEnlace, ".git", "refs"));
  let hayEnlaces = true;
  try {
    symlinkSync("refs/heads/no-existe", join(headEnlace, ".git", "HEAD"));
  } catch (error) {
    if ((error as { code?: string }).code !== "EPERM") {
      throw error;
    }
    hayEnlaces = false;
  }
  if (hayEnlaces) {
    await pasa(headEnlace);
  }
  const valida = instancia(join(repo, "valida"), false);
  git(valida, "init", "-q");
  await pasa(valida);
  const archivo = instancia(join(repo, "archivo"), false);
  writeFileSync(join(archivo, ".git"), "gitdir: ../.git/worktrees/archivo\n");
  await pasa(archivo);
});

test("un commondir cuenta solo si la carpeta que nombra tiene objects y refs, como git; si no, gentle-shell corre al writer en el repo de arriba", async () => {
  const repo = join(BASE, "monorepo-commondir");
  mkdirSync(repo, { recursive: true });
  git(repo, "init", "-q");
  git(repo, "commit", "-q", "--allow-empty", "-m", "base");
  const bloqueado = async (inst: string) => {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x" };
    const bloqueo = await conPi().emitir(lanzamiento(entrada), ctxFalso(inst));
    assert.equal(bloqueo?.block, true, inst);
    assert.ok(bloqueo.reason.startsWith(`odd-ws: gentle-shell correría este writer (writer-sql) en ${realpathSync.native(repo)}, la raíz del repo git que contiene la instancia, `), bloqueo.reason);
    assert.equal(entrada.task, "x");
  };
  const pasa = async (inst: string) => {
    const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x" };
    assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(inst)), undefined, inst);
    assert.equal(entrada.task, `x\n${MARCA_SQL}`);
  };
  const conCommondir = (nombre: string, contenido: string) => {
    const inst = instancia(join(repo, nombre), false);
    mkdirSync(join(inst, ".git"), { recursive: true });
    writeFileSync(join(inst, ".git", "HEAD"), "ref: refs/heads/main\n");
    writeFileSync(join(inst, ".git", "commondir"), contenido);
    return inst;
  };
  await bloqueado(conCommondir("a-una-que-no-existe", join(repo, "no-existe")));
  const vacia = join(repo, "comun-vacia");
  mkdirSync(vacia);
  await bloqueado(conCommondir("a-una-vacia", vacia));
  const sinRefs = join(repo, "comun-sin-refs");
  mkdirSync(join(sinRefs, "objects"), { recursive: true });
  await bloqueado(conCommondir("a-una-sin-refs", sinRefs));
  const sinObjects = join(repo, "comun-sin-objects");
  mkdirSync(join(sinObjects, "refs"), { recursive: true });
  await bloqueado(conCommondir("a-una-sin-objects", sinObjects));
  const conLosPropios = conCommondir("con-objects-y-refs-propios", vacia);
  mkdirSync(join(conLosPropios, ".git", "objects"));
  mkdirSync(join(conLosPropios, ".git", "refs"));
  await bloqueado(conLosPropios);
  await bloqueado(conCommondir("a-una-que-no-existe-con-espacio", `${join(repo, "no-existe")} `));
  await bloqueado(conCommondir("salto-antes-del-nul", `${join(repo, ".git")}\n\0basura`));
  await pasa(conCommondir("relativo-con-salto", "../../.git\n"));
  await pasa(conCommondir("absoluto-con-crlf", `${join(repo, ".git")}\r\n`));
  await pasa(conCommondir("cortado-en-el-nul", `${join(repo, ".git")}\0basura\n`));
  const valida = instancia(join(repo, "valida"), false);
  git(valida, "init", "-q");
  await pasa(valida);
  const worktree = join(repo, "worktree-real");
  git(repo, "worktree", "add", "-q", "-b", "rama-x18", worktree);
  await pasa(instancia(worktree, false));
  if (!hayGitArriba(BASE)) {
    const arriba = join(BASE, "arriba-commondir-roto");
    mkdirSync(join(arriba, ".git"), { recursive: true });
    writeFileSync(join(arriba, ".git", "HEAD"), "ref: refs/heads/main\n");
    writeFileSync(join(arriba, ".git", "commondir"), join(BASE, "no-existe"));
    await pasa(instancia(join(arriba, "inst"), false));
  }
});

test("un repo de arriba que git acepta con commondir, con objects como archivo o con HEAD como enlace no deja pasar al writer", async () => {
  const bloqueado = async (inst: string) => {
    const bloqueo = await conPi().emitir(lanzamiento({ agent: "writer-sql", task: "x" }), ctxFalso(inst));
    assert.equal(bloqueo?.block, true, inst);
  };
  const real = join(BASE, "repo-real-de-arriba");
  mkdirSync(real, { recursive: true });
  git(real, "init", "-q");
  const conCommondir = join(BASE, "arriba-commondir");
  mkdirSync(join(conCommondir, ".git"), { recursive: true });
  writeFileSync(join(conCommondir, ".git", "HEAD"), "ref: refs/heads/main\n");
  writeFileSync(join(conCommondir, ".git", "commondir"), join(real, ".git"));
  await bloqueado(instancia(join(conCommondir, "inst"), false));
  const objectsArchivo = join(BASE, "arriba-objects-archivo");
  mkdirSync(join(objectsArchivo, ".git", "refs"), { recursive: true });
  writeFileSync(join(objectsArchivo, ".git", "HEAD"), "ref: refs/heads/main\n");
  writeFileSync(join(objectsArchivo, ".git", "objects"), "");
  if (process.platform === "win32") {
    await bloqueado(instancia(join(objectsArchivo, "inst"), false));
  }
  const headEnlace = join(BASE, "arriba-head-enlace");
  mkdirSync(join(headEnlace, ".git", "objects"), { recursive: true });
  mkdirSync(join(headEnlace, ".git", "refs"));
  try {
    symlinkSync("refs/heads/no-existe", join(headEnlace, ".git", "HEAD"));
    await bloqueado(instancia(join(headEnlace, "inst"), false));
  } catch (error) {
    if ((error as { code?: string }).code !== "EPERM") {
      throw error;
    }
  }
});

function arribaConCommondir(nombre: string, contenido: string | Buffer): string {
  const arriba = join(BASE, "arriba-commondir-dudoso", nombre);
  mkdirSync(join(arriba, ".git"), { recursive: true });
  writeFileSync(join(arriba, ".git", "HEAD"), "ref: refs/heads/main\n");
  writeFileSync(join(arriba, ".git", "commondir"), contenido);
  return instancia(join(arriba, "inst"), false);
}

async function bloqueaPorElRepoDeArriba(inst: string): Promise<void> {
  const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x" };
  const bloqueo = await conPi().emitir(lanzamiento(entrada), ctxFalso(inst));
  assert.equal(bloqueo?.block, true, inst);
  assert.ok(bloqueo.reason.startsWith(`odd-ws: gentle-shell correría este writer (writer-sql) en ${realpathSync.native(dirname(inst))}, la raíz del repo git `
    + "que contiene la instancia, "), bloqueo.reason);
  assert.equal(entrada.task, "x");
}

test("arriba de la instancia, un commondir con un NUL se corta ahi, como en git, y el repo de arriba bloquea al writer", { skip: hayGitArriba(BASE) }, async () => {
  const real = join(BASE, "arriba-commondir-dudoso", "real");
  mkdirSync(real, { recursive: true });
  git(real, "init", "-q");
  await bloqueaPorElRepoDeArriba(arribaConCommondir("nul-y-basura", `${join(real, ".git")}\0basura`));
  await bloqueaPorElRepoDeArriba(arribaConCommondir("nul-y-salto", `${join(real, ".git")}\0basura\n`));
});

test("arriba de la instancia, un commondir que no es UTF-8 bloquea al writer: el shim no sabe que carpeta lee git", { skip: hayGitArriba(BASE) }, async (t) => {
  const carpeta = join(BASE, "arriba-commondir-dudoso", "no-utf8");
  const bytes = Buffer.concat([Buffer.from(join(carpeta, "comun")), Buffer.from([0xff])]);
  try {
    for (const sub of ["objects", "refs"]) {
      mkdirSync(process.platform === "win32" ? join(carpeta, "comunÿ", sub) : Buffer.concat([bytes, Buffer.from(`/${sub}`)]), { recursive: true });
    }
  } catch (error) {
    t.skip(`este sistema de archivos no acepta un nombre que no es UTF-8: ${(error as Error).message}`);
    return;
  }
  await bloqueaPorElRepoDeArriba(arribaConCommondir("no-utf8", bytes));
});

test("en Windows, arriba de la instancia, un commondir con espacios o un punto al final bloquea al writer: git los quita y el shim no puede",
  { skip: process.platform !== "win32" ? "solo Windows quita los espacios y los puntos del final de un nombre; en otro sistema git tampoco encuentra esa carpeta" : hayGitArriba(BASE) },
  async () => {
    const real = join(BASE, "arriba-commondir-dudoso", "real-windows");
    mkdirSync(real, { recursive: true });
    git(real, "init", "-q");
    const comun = join(real, ".git");
    const casos: [string, string][] = [["espacio-y-crlf", `${comun} \r\n`], ["dos-espacios", `${comun}  `], ["punto", `${comun}.`],
      ["espacio-y-salto", `${comun} \n`], ["separador-y-espacio", `${comun}\\ `]];
    for (const [nombre, contenido] of casos) {
      await bloqueaPorElRepoDeArriba(arribaConCommondir(nombre, contenido));
    }
  });

test("una instancia fuera de todo repo git: el writer sin selector corre en ctx.cwd y pasa", { skip: hayGitArriba(BASE) }, async () => {
  const inst = instancia(join(BASE, "sin-git", "inst"), false);
  const entrada: Record<string, unknown> = { agent: "writer-sql", task: "x" };
  assert.equal(await conPi().emitir(lanzamiento(entrada), ctxFalso(inst)), undefined);
  assert.equal(entrada.task, `x\n${MARCA_SQL}`);
});

test("un ctx.cwd que entra a la instancia por un enlace hacia afuera tambien se bloquea, con el pedido de abrir en la raiz", { skip: hayGitArriba(BASE) }, async () => {
  const inst = instancia(join(BASE, "enlace-afuera", "inst"), false);
  const destino = join(BASE, "enlace-afuera", "destino");
  mkdirSync(destino, { recursive: true });
  const enlace = join(inst, "por-aca");
  symlinkSync(destino, enlace, "junction");
  const bloqueo = await conPi().emitir(lanzamiento({ agent: "writer-sql", task: "x" }), ctxFalso(enlace));
  assert.equal(bloqueo?.block, true);
  assert.ok(bloqueo.reason.startsWith(`odd-ws: gentle-shell correría este writer (writer-sql) en ${realpathSync.native(destino)}, fuera de la raíz de la `
    + `instancia (${inst}): `), bloqueo.reason);
  assert.match(bloqueo.reason, AFUERA);
  assert.match(bloqueo.reason, /Abre gentle-shell en la raíz de la instancia, sin pasar por un enlace\.$/);
  const enLaRaiz: Record<string, unknown> = { agent: "writer-sql", task: "x" };
  assert.equal(await conPi().emitir(lanzamiento(enLaRaiz), ctxFalso(inst)), undefined);
  assert.equal(enLaRaiz.task, `x\n${MARCA_SQL}`);
});

const SCRIPTS = join(PLUGIN, "scripts");
const RAIZ_DE_PYTHON = [
  "import sys",
  "sys.path.insert(0, sys.argv[1])",
  "import config_loader",
  "raiz = config_loader.encontrar_raiz(sys.argv[2])",
  "sys.stdout.buffer.write(b'' if raiz is None else str(raiz).encode('utf-8'))",
].join("\n");

function instancia(raiz: string, conSkills = true): string {
  escribir(raiz, "workspace.config.json", JSON.stringify({ schema_version: 1 }));
  if (conSkills) {
    escribir(raiz, ".claude/skills/criterios/SKILL.md", "---\nname: criterios\ndescription: \"Criterios de prueba.\"\n---\n# criterios\n");
  }
  return raiz;
}

function descubrir(pi: ReturnType<typeof piFalso>, cwd: string, reason = "startup", ctx: unknown = ctxFalso(cwd)): Promise<any> {
  return pi.emitir({ type: "resources_discover", cwd, reason }, ctx);
}

function raizDePython(desde: string): string | null {
  const salida = execFileSync(PYTHON, ["-I", "-c", RAIZ_DE_PYTHON, SCRIPTS, desde], { encoding: "utf8" });
  return salida === "" ? null : salida;
}

test("resources_discover publica las skills de la instancia desde su raiz y desde cualquier subcarpeta, en el padre y en el hijo", async () => {
  const inst = instancia(join(BASE, "skills-inst"));
  const skills = join(inst, ".claude", "skills");
  mkdirSync(join(inst, "tickets", "uno"), { recursive: true });
  for (const desde of [inst, join(inst, "tickets"), join(inst, "tickets", "uno"), join(inst, "no", "existe")]) {
    for (const pi of [conPi(), conPiEn(PLUGIN, HIJO)]) {
      for (const reason of ["startup", "reload"]) {
        assert.deepEqual(await descubrir(pi, desde, reason), { skillPaths: [skills] }, `${desde} ${reason}`);
      }
    }
  }
});

test("la raiz de la instancia es la que encuentra config_loader: la carpeta mas cercana con workspace.config.json", async () => {
  const afuera = instancia(join(BASE, "skills-anidada"));
  const adentro = instancia(join(afuera, "sub", "otra"));
  mkdirSync(join(adentro, "x", "y"), { recursive: true });
  mkdirSync(join(afuera, "sub", "z"), { recursive: true });
  for (const desde of [afuera, join(afuera, "sub"), join(afuera, "sub", "z"), adentro, join(adentro, "x", "y"), join(adentro, "x", "no-existe")]) {
    const raiz = raizDePython(desde);
    assert.notEqual(raiz, null, desde);
    assert.equal(raiz, desde.startsWith(adentro) ? adentro : afuera, desde);
    assert.deepEqual(await descubrir(conPi(), desde), { skillPaths: [join(raiz as string, ".claude", "skills")] }, desde);
  }
});

test("fuera de una instancia, sin .claude/skills, o con un workspace.config.json que no es un archivo, no publica nada", async () => {
  const afuera = join(BASE, "skills-afuera", "a");
  mkdirSync(afuera, { recursive: true });
  assert.equal(raizDePython(afuera), null);
  assert.equal(await descubrir(conPi(), afuera), undefined);
  assert.equal(await descubrir(conPi(), instancia(join(BASE, "skills-sin"), false)), undefined);
  const conArchivo = instancia(join(BASE, "skills-archivo"), false);
  escribir(conArchivo, ".claude/skills", "no es una carpeta\n");
  assert.equal(await descubrir(conPi(), conArchivo), undefined);
  const conCarpeta = join(BASE, "skills-carpeta");
  mkdirSync(join(conCarpeta, "workspace.config.json"), { recursive: true });
  mkdirSync(join(conCarpeta, ".claude", "skills", "criterios"), { recursive: true });
  assert.equal(raizDePython(conCarpeta), null);
  assert.equal(await descubrir(conPi(), conCarpeta), undefined);
});

test("resources_discover sube desde ctx.cwd, sin el usa el cwd del evento, y un ctx que falla no rompe el arranque", async () => {
  const inst = instancia(join(BASE, "skills-cwd"));
  const otra = join(BASE, "skills-cwd-otra");
  mkdirSync(otra, { recursive: true });
  const skills = { skillPaths: [join(inst, ".claude", "skills")] };
  assert.deepEqual(await descubrir(conPi(), otra, "startup", ctxFalso(inst)), skills);
  assert.equal(await descubrir(conPi(), inst, "startup", ctxFalso(otra)), undefined);
  assert.deepEqual(await descubrir(conPi(), inst, "startup", { isProjectTrusted: () => true }), skills);
  assert.deepEqual(await descubrir(conPi(), inst, "startup", ctxFalso("")), skills);
  const roto = { get cwd(): string { throw new Error("ctx inactivo"); } };
  assert.equal(await descubrir(conPi(), inst, "startup", roto), undefined);
});

test("resources_discover publica las skills de la instancia solo si Pi dice que el proyecto tiene confianza", async () => {
  const inst = instancia(join(BASE, "skills-confianza"));
  const skills = { skillPaths: [join(inst, ".claude", "skills")] };
  assert.deepEqual(await descubrir(conPi(), inst, "startup", { ...ctxFalso(inst), isProjectTrusted: () => true }), skills);
  const sinConfianza: Record<string, unknown>[] = [
    { isProjectTrusted: () => false },
    { isProjectTrusted: () => "true" },
    { isProjectTrusted: () => 1 },
    { isProjectTrusted: true },
    { isProjectTrusted: () => { throw new Error("ctx inactivo"); } },
    {},
  ];
  for (const extra of sinConfianza) {
    const ctx: Record<string, unknown> = { ...ctxFalso(inst), ...extra };
    if (!("isProjectTrusted" in extra)) {
      delete ctx.isProjectTrusted;
    }
    assert.equal(await descubrir(conPi(), inst, "startup", ctx), undefined, String(extra.isProjectTrusted));
  }
});
