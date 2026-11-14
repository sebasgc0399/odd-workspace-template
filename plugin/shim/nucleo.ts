import { spawn } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface Hook { script: string; args: string[]; timeout: number }
export interface Grupo { tools?: string[]; hooks: Hook[] }
export interface ListaDeHooks { python: string; pythonWindows: string; writer?: string; hooks: Record<string, Grupo[]> }
export type Accion = "bloquear" | "preguntar" | "contexto" | "seguir";
export type Tipo = "permitir" | "falla" | Accion;
export interface Resultado { tipo: Tipo; script: string; texto: string }
export interface Decision { tipo: Tipo; texto: string }
export interface Corrida {
  lista: ListaDeHooks;
  plugin: string;
  evento: string;
  herramienta?: string;
  entrada: unknown;
  cwd: string;
}

const SCRIPT = /^[A-Za-z0-9_]+\.py$/;
const ACCIONES: readonly string[] = ["bloquear", "preguntar", "contexto", "seguir"];
const PRECEDENCIA: readonly Tipo[] = ["falla", "bloquear", "seguir", "preguntar", "contexto"];
const RECORTE = 200;

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function esTexto(valor: unknown): valor is string {
  return typeof valor === "string" && valor !== "";
}

function esHook(valor: unknown): valor is Hook {
  return esObjeto(valor) && typeof valor.script === "string" && SCRIPT.test(valor.script) && Array.isArray(valor.args)
    && valor.args.every((argumento) => typeof argumento === "string") && typeof valor.timeout === "number"
    && Number.isFinite(valor.timeout) && valor.timeout > 0;
}

function esGrupo(valor: unknown): valor is Grupo {
  return esObjeto(valor) && (valor.tools === undefined || (Array.isArray(valor.tools) && valor.tools.every(esTexto)))
    && Array.isArray(valor.hooks) && valor.hooks.every(esHook);
}

function esRegex(valor: unknown): valor is string {
  if (!esTexto(valor)) {
    return false;
  }
  try {
    new RegExp(valor);
    return true;
  } catch {
    return false;
  }
}

function esLista(valor: unknown): valor is ListaDeHooks {
  return esObjeto(valor) && esTexto(valor.python) && esTexto(valor.pythonWindows) && (valor.writer === undefined || esRegex(valor.writer))
    && esObjeto(valor.hooks) && Object.values(valor.hooks).every((grupos) => Array.isArray(grupos) && grupos.every(esGrupo));
}

function mensaje(error: unknown): string {
  if (esObjeto(error) && typeof error.code === "string") {
    return error.code;
  }
  return error instanceof Error ? error.message : String(error);
}

function recorte(texto: string): string {
  const plano = texto.replace(/\s+/g, " ").trim();
  return plano.length > RECORTE ? `${plano.slice(0, RECORTE)}...` : plano;
}

export function leerLista(ruta: string): ListaDeHooks {
  let texto: string;
  try {
    texto = readFileSync(ruta, "utf8");
  } catch (error) {
    throw new Error(`${ruta} no se puede leer (${mensaje(error)})`);
  }
  let datos: unknown;
  try {
    datos = JSON.parse(texto);
  } catch (error) {
    throw new Error(`${ruta} no es JSON (${mensaje(error)})`);
  }
  if (!esLista(datos)) {
    throw new Error(`${ruta} no tiene la forma de una lista de hooks: python y pythonWindows, writer opcional (una regex), y en hooks, `
      + "por evento, grupos con tools opcional y hooks con script (un .py de scripts/), args y timeout en segundos");
  }
  return datos;
}

export function writerDe(lista: ListaDeHooks): RegExp {
  if (lista.writer === undefined) {
    throw new Error("la lista de hooks no trae la regex de los writers (writer)");
  }
  return new RegExp(lista.writer);
}

export function pythonDe(lista: ListaDeHooks, plataforma: string = process.platform): string {
  return plataforma === "win32" ? lista.pythonWindows : lista.python;
}

export function hooksDe(lista: ListaDeHooks, evento: string, herramienta?: string): Hook[] {
  const grupos = Object.hasOwn(lista.hooks, evento) ? lista.hooks[evento] : [];
  return grupos.filter((grupo) => grupo.tools === undefined || (herramienta !== undefined && grupo.tools.includes(herramienta)))
    .flatMap((grupo) => grupo.hooks);
}

function falla(script: string, motivo: string): Resultado {
  return { tipo: "falla", script, texto: `odd-ws: el hook ${script} no pudo correr (${motivo}).` };
}

function ultimaLinea(texto: string): string {
  const lineas = texto.split(/\r?\n/).map((linea) => linea.trim()).filter((linea) => linea !== "");
  return lineas.length > 0 ? `: ${recorte(lineas[lineas.length - 1])}` : "";
}

function interpretar(script: string, codigo: number | null, senal: string | null, salida: string, errores: string): Resultado {
  if (codigo !== 0) {
    return falla(script, codigo === null ? `terminó con la señal ${senal}` : `salió con ${codigo}${ultimaLinea(errores)}`);
  }
  if (salida === "") {
    return { tipo: "permitir", script, texto: "" };
  }
  let datos: unknown;
  try {
    datos = JSON.parse(salida);
  } catch {
    return falla(script, `su salida no es JSON: ${recorte(salida)}`);
  }
  if (!esObjeto(datos) || typeof datos.accion !== "string" || !ACCIONES.includes(datos.accion) || typeof datos.texto !== "string") {
    return falla(script, `devolvió una acción desconocida: ${recorte(salida)}`);
  }
  return { tipo: datos.accion as Accion, script, texto: datos.texto };
}

function correrHook(python: string, plugin: string, hook: Hook, entrada: string, cwd: string): Promise<Resultado> {
  return new Promise((resolver) => {
    let terminado = false;
    let reloj: ReturnType<typeof setTimeout> | undefined;
    let hijo: ChildProcess;
    const terminar = (resultado: Resultado): void => {
      if (!terminado) {
        terminado = true;
        clearTimeout(reloj);
        resolver(resultado);
      }
    };
    try {
      hijo = spawn(python, [join(plugin, "scripts", hook.script), ...hook.args],
        { cwd, shell: false, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
    } catch (error) {
      terminar(falla(hook.script, `no se pudo lanzar ${python} (${mensaje(error)})`));
      return;
    }
    const salida: Buffer[] = [];
    const errores: Buffer[] = [];
    hijo.stdout?.on("data", (parte: Buffer) => salida.push(parte));
    hijo.stderr?.on("data", (parte: Buffer) => errores.push(parte));
    hijo.on("error", (error) => {
      hijo.kill("SIGKILL");
      terminar(falla(hook.script, `no se pudo lanzar ${python} (${mensaje(error)})`));
    });
    hijo.on("close", (codigo, senal) => terminar(interpretar(hook.script, codigo, senal,
      Buffer.concat(salida).toString("utf8"), Buffer.concat(errores).toString("utf8"))));
    reloj = setTimeout(() => {
      hijo.kill("SIGKILL");
      terminar(falla(hook.script, `se pasó de ${hook.timeout} s y se cortó`));
    }, hook.timeout * 1000);
    hijo.stdin?.on("error", () => undefined);
    hijo.stdin?.end(entrada);
  });
}

export async function correrEvento(corrida: Corrida): Promise<Resultado[]> {
  const hooks = hooksDe(corrida.lista, corrida.evento, corrida.herramienta);
  if (hooks.length === 0) {
    return [];
  }
  const entrada = JSON.stringify(corrida.entrada);
  const python = pythonDe(corrida.lista);
  return Promise.all(hooks.map((hook) => correrHook(python, corrida.plugin, hook, entrada, corrida.cwd)));
}

export function combinar(resultados: Resultado[]): Decision {
  const tipo = PRECEDENCIA.find((candidato) => resultados.some((resultado) => resultado.tipo === candidato)) ?? "permitir";
  const texto = resultados.map((resultado) => resultado.texto).filter((parte) => parte !== "").join("\n\n");
  return { tipo, texto };
}

export function contexto(resultados: Resultado[]): string {
  return resultados.filter((resultado) => resultado.tipo === "contexto").map((resultado) => resultado.texto)
    .filter((parte) => parte !== "").join("\n\n");
}
