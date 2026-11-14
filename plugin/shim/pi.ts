import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { combinar, contexto, correrEvento, leerLista, writerDe } from "./nucleo.ts";
import type { ListaDeHooks, Resultado } from "./nucleo.ts";

export const PLUGIN = dirname(dirname(fileURLToPath(import.meta.url)));
export const ARCHIVO_DE_HOOKS = "hooks/hooks.pi.json";
export const PLAZO_DE_CONFIRMACION = 60000;
export const VARIABLE_DEL_HIJO = "GENTLE_PI_AGENTS_CHILD";
const LANZAR = "subagent_run";
const SUBAGENTES: readonly string[] = [LANZAR, "subagent_continue", "subagent_send_message"];
const TIPO_DEL_MENSAJE = "odd-ws";
const MARCA = /^<!-- odd-ws:agente (\S+) -->$/;
const MARCAS = /<!--\s*odd-ws[\s\S]*?-->[ \t]*(?:\r?\n)?/gi;
const TITULO = "odd-ws pide confirmación";
const FALLA_EN_PRE = "Como un guard de odd-ws no pudo correr, esta herramienta queda bloqueada.";
const FALLA_EN_POST = "Como un guard de odd-ws no pudo correr, este resultado no se revisó.";
const SIN_CONFIRMAR = "No se confirmó (el usuario dijo que no, cerró el diálogo o venció el plazo de 60 s), así que este comando queda "
  + "bloqueado.";

interface ContextoDePi {
  cwd: string;
  hasUI: boolean;
  mode: string;
  sessionManager: { getSessionId(): string; getBranch?(): unknown };
  ui: { confirm(titulo: string, mensaje: string, opciones?: { timeout?: number }): Promise<boolean> };
}

interface EventoDePi {
  type: string;
  toolName?: string;
  input?: unknown;
  isError?: boolean;
  reason?: string;
  content?: unknown[];
  systemPrompt?: string;
  systemPromptOptions?: unknown;
  prompt?: unknown;
  entries?: unknown;
  continue?: boolean;
  context?: unknown;
  outcome?: string;
}

interface OpcionesDelPrompt {
  appendSystemPrompt?: string;
  forceSystemPrompt?: string;
}

interface ApiDePi {
  on(evento: string, manejador: (evento: any, ctx: any) => unknown): void;
}

interface Bloqueo { block: true; reason: string }
interface Revision { isError?: true; content: unknown[] }
interface Continuacion { entries: unknown[]; continue: true }
interface Lanzamiento { agent: string; task: string; context?: string }
interface Identidad { agent: string | null; agentId: string | null }
interface Estado { hijo: boolean; fijada: boolean; identidad: Identidad; continuado: boolean }

function esObjeto(valor: unknown): valor is Record<string, any> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function mensaje(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function conLinea(texto: string, linea: string): string {
  return texto === "" ? linea : `${texto}\n\n${linea}`;
}

function sinCorrer(error: unknown): string {
  return `odd-ws: el shim de Pi no pudo correr sus guards (${mensaje(error)}).`;
}

function lista(plugin: string): ListaDeHooks {
  return leerLista(join(plugin, ARCHIVO_DE_HOOKS));
}

function identidadDe(estado: Estado): Identidad | undefined {
  return estado.hijo ? { ...estado.identidad } : undefined;
}

function carga(evento: EventoDePi, ctx: ContextoDePi, oddWs?: object) {
  return {
    type: evento.type,
    toolName: evento.toolName,
    input: evento.input,
    isError: evento.isError,
    reason: evento.reason,
    ctx: { cwd: ctx.cwd, sessionId: ctx.sessionManager.getSessionId(), hasUI: ctx.hasUI, mode: ctx.mode },
    ...(oddWs === undefined ? {} : { oddWs }),
  };
}

function correr(plugin: string, hooks: ListaDeHooks, evento: EventoDePi, ctx: ContextoDePi, oddWs?: object): Promise<Resultado[]> {
  return correrEvento({ lista: hooks, plugin, evento: evento.type, herramienta: evento.toolName, entrada: carga(evento, ctx, oddWs),
    cwd: ctx.cwd });
}

function sinMarcas(texto: string): string {
  let previo: string;
  do {
    previo = texto;
    texto = texto.replace(MARCAS, "");
  } while (texto !== previo);
  return texto;
}

function limpiar(valor: unknown): unknown {
  if (typeof valor === "string") {
    return sinMarcas(valor);
  }
  if (Array.isArray(valor) || esObjeto(valor)) {
    const partes = valor as Record<string, unknown>;
    for (const clave of Object.keys(partes)) {
      const limpio = limpiar(partes[clave]);
      if (limpio !== partes[clave]) {
        partes[clave] = limpio;
      }
    }
  }
  return valor;
}

function nombresDeAgente(valor: unknown): string[] {
  if (Array.isArray(valor)) {
    return valor.flatMap(nombresDeAgente);
  }
  if (!esObjeto(valor)) {
    return [];
  }
  return Object.entries(valor).flatMap(([clave, dentro]) => [
    ...(clave === "agent" || clave === "agents" ? [dentro].flat().filter((nombre): nombre is string => typeof nombre === "string") : []),
    ...nombresDeAgente(dentro),
  ]);
}

function sabeMarcar(entrada: unknown): entrada is Lanzamiento {
  return esObjeto(entrada) && typeof entrada.agent === "string" && typeof entrada.task === "string"
    && (entrada.context === undefined || typeof entrada.context === "string");
}

function marca(nombre: string): string {
  return `<!-- odd-ws:agente ${nombre} -->`;
}

function noSeMarca(nombre: string): string {
  return `odd-ws: este subagent_run lanza un writer (${nombre}), pero su entrada no tiene la forma que odd-ws sabe marcar (agent y task `
    + "de texto, context opcional de texto y ningún otro writer), así que queda bloqueado: sin la marca, el writer correría sin sus "
    + "guards ni su compuerta de cierre.";
}

function marcar(evento: EventoDePi, hooks: ListaDeHooks): Bloqueo | undefined {
  if (evento.toolName !== LANZAR) {
    limpiar(evento.input);
    return undefined;
  }
  const regex = writerDe(hooks);
  const entrada = limpiar(evento.input);
  const writers = nombresDeAgente(entrada).filter((nombre) => regex.test(nombre));
  if (writers.length === 0) {
    return undefined;
  }
  if (!sabeMarcar(entrada) || writers.length !== 1 || writers[0] !== entrada.agent) {
    return { block: true, reason: noSeMarca(writers[0]) };
  }
  if (entrada.task.trim() !== "") {
    entrada.task = `${entrada.task}\n${marca(entrada.agent)}`;
  }
  return undefined;
}

function textoDe(contenido: unknown): string {
  if (typeof contenido === "string") {
    return contenido;
  }
  if (!Array.isArray(contenido)) {
    return "";
  }
  return contenido.filter((parte) => esObjeto(parte) && parte.type === "text" && typeof parte.text === "string")
    .map((parte) => parte.text as string).join("\n");
}

function primerPrompt(evento: EventoDePi, ctx: ContextoDePi): string {
  let rama: unknown = [];
  try {
    rama = ctx.sessionManager.getBranch?.() ?? [];
  } catch {
    rama = [];
  }
  const primero = (Array.isArray(rama) ? rama : []).find((entrada): entrada is Record<string, any> => esObjeto(entrada)
    && entrada.type === "message" && esObjeto(entrada.message) && entrada.message.role === "user");
  if (primero !== undefined) {
    return textoDe(primero.message.content);
  }
  return typeof evento.prompt === "string" ? evento.prompt : "";
}

function nombreMarcado(texto: string): string | null {
  const marcas = texto.split("\n").map((linea) => MARCA.exec(linea.replace(/\r$/, ""))).filter((encontrada) => encontrada !== null);
  return marcas.length === 1 ? marcas[0][1] : null;
}

function fijarIdentidad(estado: Estado, evento: EventoDePi, ctx: ContextoDePi): void {
  if (!estado.hijo || estado.fijada) {
    return;
  }
  estado.fijada = true;
  let agent: string | null = null;
  let agentId: string | null = null;
  try {
    agent = nombreMarcado(primerPrompt(evento, ctx));
  } catch {
    agent = null;
  }
  try {
    const sesion = ctx.sessionManager.getSessionId();
    agentId = typeof sesion === "string" ? sesion : null;
  } catch {
    agentId = null;
  }
  estado.identidad = { agent, agentId };
}

function conTexto(evento: EventoDePi, texto: string): unknown[] {
  return [...(Array.isArray(evento.content) ? evento.content : []), { type: "text", text: texto }];
}

async function confirmar(ctx: ContextoDePi, texto: string): Promise<Bloqueo | undefined> {
  let confirmado: boolean;
  try {
    confirmado = await ctx.ui.confirm(TITULO, texto, { timeout: PLAZO_DE_CONFIRMACION });
  } catch (error) {
    return { block: true, reason: conLinea(texto, `odd-ws no pudo pedir la confirmación (${mensaje(error)}), así que este comando queda bloqueado.`) };
  }
  return confirmado === true ? undefined : { block: true, reason: conLinea(texto, SIN_CONFIRMAR) };
}

async function antesDeLaHerramienta(plugin: string, evento: EventoDePi, ctx: ContextoDePi, estado: Estado): Promise<Bloqueo | undefined> {
  try {
    const hooks = lista(plugin);
    if (evento.toolName !== undefined && SUBAGENTES.includes(evento.toolName)) {
      const bloqueo = marcar(evento, hooks);
      if (bloqueo !== undefined) {
        return bloqueo;
      }
    }
    const decision = combinar(await correr(plugin, hooks, evento, ctx, identidadDe(estado)));
    if (decision.tipo === "permitir") {
      return undefined;
    }
    if (decision.tipo === "preguntar") {
      return await confirmar(ctx, decision.texto);
    }
    return { block: true, reason: decision.tipo === "falla" ? conLinea(decision.texto, FALLA_EN_PRE) : decision.texto };
  } catch (error) {
    return { block: true, reason: conLinea(sinCorrer(error), FALLA_EN_PRE) };
  }
}

async function despuesDeLaHerramienta(plugin: string, evento: EventoDePi, ctx: ContextoDePi, estado: Estado): Promise<Revision | undefined> {
  try {
    const decision = combinar(await correr(plugin, lista(plugin), evento, ctx, identidadDe(estado)));
    if (decision.tipo === "permitir") {
      return undefined;
    }
    if (decision.tipo === "contexto") {
      return { content: conTexto(evento, decision.texto) };
    }
    return { isError: true, content: conTexto(evento, decision.tipo === "falla" ? conLinea(decision.texto, FALLA_EN_POST) : decision.texto) };
  } catch (error) {
    return { isError: true, content: conTexto(evento, conLinea(sinCorrer(error), FALLA_EN_POST)) };
  }
}

async function alIniciar(plugin: string, evento: EventoDePi, ctx: ContextoDePi, estado: Estado): Promise<string> {
  try {
    return contexto(await correr(plugin, lista(plugin), evento, ctx, identidadDe(estado)));
  } catch {
    return "";
  }
}

function ultimoDelAsistente(evento: EventoDePi): string {
  const mensajes = esObjeto(evento.context) ? evento.context.llmMessages : undefined;
  if (!Array.isArray(mensajes)) {
    return "";
  }
  for (let indice = mensajes.length - 1; indice >= 0; indice -= 1) {
    if (esObjeto(mensajes[indice]) && mensajes[indice].role === "assistant") {
      return textoDe(mensajes[indice].content);
    }
  }
  return "";
}

async function alAsentarse(plugin: string, evento: EventoDePi, ctx: ContextoDePi, estado: Estado): Promise<Continuacion | undefined> {
  if (evento.continue === true) {
    return undefined;
  }
  const continuado = estado.continuado;
  estado.continuado = false;
  if (evento.outcome !== "completed") {
    return undefined;
  }
  try {
    const hooks = lista(plugin);
    const { agent, agentId } = estado.identidad;
    if (agent === null || !writerDe(hooks).test(agent)) {
      return undefined;
    }
    const decision = combinar(await correr(plugin, hooks, evento, ctx,
      { agent, agentId, lastAssistantMessage: ultimoDelAsistente(evento), continued: continuado }));
    if (decision.tipo !== "seguir" || continuado) {
      return undefined;
    }
    estado.continuado = true;
    const previas = Array.isArray(evento.entries) ? evento.entries : [];
    return { entries: [...previas, { type: "custom_message", customType: TIPO_DEL_MENSAJE, content: decision.texto, display: true }],
      continue: true };
  } catch {
    return undefined;
  }
}

function sonOpciones(valor: unknown): valor is OpcionesDelPrompt {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor)
    && ["string", "undefined"].includes(typeof (valor as OpcionesDelPrompt).appendSystemPrompt);
}

function encadenado(previo: string, texto: string): string {
  return previo === "" ? texto : `${previo}\n\n${texto}`;
}

function alEmpezarElTurno(evento: EventoDePi, texto: string): { systemPrompt: string } | undefined {
  if (texto === "") {
    return undefined;
  }
  const opciones = evento.systemPromptOptions;
  if (sonOpciones(opciones)) {
    const agregado = opciones.appendSystemPrompt ?? "";
    if (!agregado.includes(texto)) {
      opciones.appendSystemPrompt = encadenado(agregado, texto);
    }
    if (opciones.forceSystemPrompt === undefined) {
      return undefined;
    }
  }
  const actual = evento.systemPrompt ?? "";
  return actual.includes(texto) ? undefined : { systemPrompt: encadenado(actual, texto) };
}

export function registrar(pi: ApiDePi, plugin: string = PLUGIN, entorno: Record<string, string | undefined> = process.env): void {
  const estado: Estado = { hijo: entorno[VARIABLE_DEL_HIJO] === "1", fijada: false, identidad: { agent: null, agentId: null }, continuado: false };
  let deInicio = "";
  const iniciar = async (evento: EventoDePi, ctx: ContextoDePi): Promise<void> => {
    deInicio = "";
    deInicio = await alIniciar(plugin, evento, ctx, estado);
  };
  pi.on("tool_call", (evento: EventoDePi, ctx: ContextoDePi) => antesDeLaHerramienta(plugin, evento, ctx, estado));
  pi.on("tool_result", (evento: EventoDePi, ctx: ContextoDePi) => despuesDeLaHerramienta(plugin, evento, ctx, estado));
  pi.on("session_start", iniciar);
  pi.on("session_compact", iniciar);
  pi.on("before_agent_start", (evento: EventoDePi, ctx: ContextoDePi) => {
    fijarIdentidad(estado, evento, ctx);
    return alEmpezarElTurno(evento, deInicio);
  });
  if (estado.hijo) {
    pi.on("agent_before_settle", (evento: EventoDePi, ctx: ContextoDePi) => alAsentarse(plugin, evento, ctx, estado));
  }
}

export default function (pi: ApiDePi): void {
  registrar(pi);
}
