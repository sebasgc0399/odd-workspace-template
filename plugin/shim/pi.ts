import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { combinar, contexto, correrEvento, leerLista } from "./nucleo.ts";
import type { Resultado } from "./nucleo.ts";

export const PLUGIN = dirname(dirname(fileURLToPath(import.meta.url)));
export const ARCHIVO_DE_HOOKS = "hooks/hooks.pi.json";
export const PLAZO_DE_CONFIRMACION = 60000;
const TITULO = "odd-ws pide confirmación";
const FALLA_EN_PRE = "Como un guard de odd-ws no pudo correr, esta herramienta queda bloqueada.";
const FALLA_EN_POST = "Como un guard de odd-ws no pudo correr, este resultado no se revisó.";
const SIN_CONFIRMAR = "No se confirmó (el usuario dijo que no, cerró el diálogo o venció el plazo de 60 s), así que este comando queda "
  + "bloqueado.";

interface ContextoDePi {
  cwd: string;
  hasUI: boolean;
  mode: string;
  sessionManager: { getSessionId(): string };
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

function mensaje(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function conLinea(texto: string, linea: string): string {
  return texto === "" ? linea : `${texto}\n\n${linea}`;
}

function sinCorrer(error: unknown): string {
  return `odd-ws: el shim de Pi no pudo correr sus guards (${mensaje(error)}).`;
}

function carga(evento: EventoDePi, ctx: ContextoDePi) {
  return {
    type: evento.type,
    toolName: evento.toolName,
    input: evento.input,
    isError: evento.isError,
    reason: evento.reason,
    ctx: { cwd: ctx.cwd, sessionId: ctx.sessionManager.getSessionId(), hasUI: ctx.hasUI, mode: ctx.mode },
  };
}

function correr(plugin: string, evento: EventoDePi, ctx: ContextoDePi): Promise<Resultado[]> {
  const entrada = carga(evento, ctx);
  return correrEvento({ lista: leerLista(join(plugin, ARCHIVO_DE_HOOKS)), plugin, evento: evento.type, herramienta: evento.toolName,
    entrada, cwd: ctx.cwd });
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

async function antesDeLaHerramienta(plugin: string, evento: EventoDePi, ctx: ContextoDePi): Promise<Bloqueo | undefined> {
  try {
    const decision = combinar(await correr(plugin, evento, ctx));
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

async function despuesDeLaHerramienta(plugin: string, evento: EventoDePi, ctx: ContextoDePi): Promise<Revision | undefined> {
  try {
    const decision = combinar(await correr(plugin, evento, ctx));
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

async function alIniciar(plugin: string, evento: EventoDePi, ctx: ContextoDePi): Promise<string> {
  try {
    return contexto(await correr(plugin, evento, ctx));
  } catch {
    return "";
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

export function registrar(pi: ApiDePi, plugin: string = PLUGIN): void {
  let deInicio = "";
  const iniciar = async (evento: EventoDePi, ctx: ContextoDePi): Promise<void> => {
    deInicio = "";
    deInicio = await alIniciar(plugin, evento, ctx);
  };
  pi.on("tool_call", (evento: EventoDePi, ctx: ContextoDePi) => antesDeLaHerramienta(plugin, evento, ctx));
  pi.on("tool_result", (evento: EventoDePi, ctx: ContextoDePi) => despuesDeLaHerramienta(plugin, evento, ctx));
  pi.on("session_start", iniciar);
  pi.on("session_compact", iniciar);
  pi.on("before_agent_start", (evento: EventoDePi) => alEmpezarElTurno(evento, deInicio));
}

export default function (pi: ApiDePi): void {
  registrar(pi);
}
