import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const PRE_COMMIT = join(REPO, ".githooks", "pre-commit");
const SONDA = join(REPO, ".githooks", "python.sh");
const PRUEBAS = join(REPO, ".github", "workflows", "pruebas.yml");
const EN_WINDOWS = process.platform === "win32";
const SUITES = {
  "verde.tests.py": "print('1/1 pruebas en verde')\n",
  "rojo.tests.py": "import sys\nprint('FALLA test_rojo: no')\nsys.exit(1)\n",
  "verde.test.ts": "import { test } from \"node:test\";\nconst x: number = 1;\ntest(\"verde\", () => {});\n",
  "rojo.test.ts": "import { test } from \"node:test\";\nimport assert from \"node:assert/strict\";\ntest(\"rojo\", () => { assert.equal(1, 2); });\n",
};

type Suite = keyof typeof SUITES;

function enElPath(nombre: string, path = process.env.PATH ?? ""): string | undefined {
  for (const carpeta of path.split(delimiter).filter((parte) => parte !== "")) {
    for (const extension of EN_WINDOWS ? [".exe", ""] : [""]) {
      const ruta = join(carpeta, nombre + extension);
      if (existsSync(ruta)) {
        return ruta;
      }
    }
  }
  return undefined;
}

function deGit(nombre: string): string {
  const directo = EN_WINDOWS ? undefined : enElPath(nombre);
  if (directo !== undefined) {
    return directo;
  }
  const git = enElPath("git");
  assert.ok(git, "hace falta git en el PATH");
  for (let carpeta = dirname(git), nivel = 0; nivel < 4; carpeta = dirname(carpeta), nivel += 1) {
    for (const relativa of [["bin"], ["usr", "bin"]]) {
      const candidato = join(carpeta, ...relativa, `${nombre}.exe`);
      if (existsSync(candidato)) {
        return candidato;
      }
    }
  }
  throw new Error(`no hay un ${nombre} de git para correr los hooks`);
}

function pythonReal(): string {
  for (const nombre of ["python3", "python"]) {
    try {
      return execFileSync(nombre, ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
    } catch {
      continue;
    }
  }
  throw new Error("no hay un python que corra");
}

function entorno(base: string, extra: Record<string, string> = {}): Record<string, string> {
  const propio: Record<string, string> = {};
  for (const [clave, valor] of Object.entries(process.env)) {
    if (valor !== undefined && !/^(GIT_|NODE_TEST|NODE_OPTIONS)/i.test(clave)) {
      propio[clave] = valor;
    }
  }
  const config = join(base, "gitconfig");
  writeFileSync(config, "");
  return { ...propio, GIT_CONFIG_GLOBAL: config, GIT_CONFIG_SYSTEM: config, GIT_CONFIG_NOSYSTEM: "1", ...extra };
}

function interpretes(base: string): string {
  const carpeta = join(base, "interpretes");
  mkdirSync(carpeta, { recursive: true });
  const real = pythonReal().replace(/\\/g, "/");
  for (const nombre of ["python3", "python"]) {
    const ruta = join(carpeta, nombre);
    writeFileSync(ruta, `#!/bin/sh\nexec "${real}" "$@"\n`);
    chmodSync(ruta, 0o755);
  }
  return carpeta;
}

function sinNode(base: string): string {
  const sh = deGit("sh");
  const git = enElPath("git");
  assert.ok(git);
  let carpetas: string[];
  if (EN_WINDOWS) {
    carpetas = [dirname(git), dirname(sh)];
  } else {
    const sistema = join(base, "sistema");
    mkdirSync(sistema);
    symlinkSync(git, join(sistema, "git"));
    symlinkSync(sh, join(sistema, "sh"));
    carpetas = [sistema];
  }
  const path = [interpretes(base), ...carpetas].join(delimiter);
  assert.equal(enElPath("node", path), undefined, `node sigue en ${path}`);
  return path;
}

function repo(base: string, suites: Suite[]): string {
  const raiz = join(base, "repo");
  mkdirSync(join(raiz, ".githooks"), { recursive: true });
  mkdirSync(join(raiz, "tools"));
  mkdirSync(join(raiz, "sub"));
  copyFileSync(PRE_COMMIT, join(raiz, ".githooks", "pre-commit"));
  copyFileSync(SONDA, join(raiz, ".githooks", "python.sh"));
  writeFileSync(join(raiz, "tools", "barrido.py"), "import sys\nsys.exit(0)\n");
  for (const suite of suites) {
    writeFileSync(join(raiz, "sub", suite), SUITES[suite]);
  }
  const env = entorno(base);
  execFileSync("git", ["init", "-q"], { cwd: raiz, env });
  execFileSync("git", ["add", "-A"], { cwd: raiz, env });
  return raiz;
}

function conRepo(suites: Suite[], prueba: (base: string, raiz: string) => void): () => void {
  return () => {
    const base = mkdtempSync(join(tmpdir(), "odd-ws-corredores-"));
    let error: unknown;
    try {
      prueba(base, repo(base, suites));
    } catch (fallo) {
      error = fallo;
    }
    try {
      rmSync(base, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
    } catch (fallo) {
      error ??= fallo;
    }
    if (error !== undefined) {
      throw error;
    }
  };
}

function preCommit(base: string, raiz: string, path?: string) {
  const hook = join(raiz, ".githooks", "pre-commit").replace(/\\/g, "/");
  const env = entorno(base, path === undefined ? {} : { PATH: path });
  return spawnSync(deGit("sh"), [hook], { cwd: raiz, env, encoding: "utf8", timeout: 240000 });
}

function guionDelCi(): string {
  const lineas = readFileSync(PRUEBAS, "utf8").split(/\r?\n/);
  const paso = lineas.findIndex((linea) => linea.trim() === "- name: Todas las suites");
  assert.ok(paso >= 0, "el CI tiene el paso «Todas las suites»");
  const run = lineas.findIndex((linea, indice) => indice > paso && linea.trim() === "run: |");
  assert.ok(run > paso, "el paso corre un guion");
  const sangria = lineas[run].length - lineas[run].trimStart().length;
  const cuerpo: string[] = [];
  for (const linea of lineas.slice(run + 1)) {
    if (linea.trim() !== "" && linea.length - linea.trimStart().length <= sangria) {
      break;
    }
    cuerpo.push(linea);
  }
  const minima = Math.min(...cuerpo.filter((linea) => linea.trim() !== "").map((linea) => linea.length - linea.trimStart().length));
  return cuerpo.map((linea) => linea.slice(minima)).join("\n");
}

function ci(base: string, raiz: string) {
  const env = entorno(base, { RUNNER_TEMP: base, PATH: [interpretes(base), process.env.PATH ?? ""].join(delimiter) });
  return spawnSync(deGit("bash"), ["-c", guionDelCi()], { cwd: raiz, env, encoding: "utf8", timeout: 240000 });
}

test("pre-commit: con todas las suites en verde, las de Python y las de TypeScript, deja commitear",
  conRepo(["verde.tests.py", "verde.test.ts"], (base, raiz) => {
    const corrida = preCommit(base, raiz);
    assert.equal(corrida.status, 0, corrida.stdout + corrida.stderr);
  }));

test("pre-commit: una suite de Python en rojo sigue frenando el commit con su nombre",
  conRepo(["verde.tests.py", "rojo.tests.py", "verde.test.ts"], (base, raiz) => {
    const corrida = preCommit(base, raiz);
    assert.equal(corrida.status, 1, corrida.stdout + corrida.stderr);
    assert.match(corrida.stdout, /^suite en rojo: sub\/rojo\.tests\.py \(correla a mano para ver el detalle\)$/m);
  }));

test("pre-commit: una suite de TypeScript en rojo frena el commit con su nombre",
  conRepo(["verde.tests.py", "verde.test.ts", "rojo.test.ts"], (base, raiz) => {
    const corrida = preCommit(base, raiz);
    assert.equal(corrida.status, 1, corrida.stdout + corrida.stderr);
    assert.match(corrida.stdout, /^suite en rojo: sub\/rojo\.test\.ts \(correla a mano con node --test para ver el detalle\)$/m);
  }));

test("pre-commit: sin node y con suites de TypeScript, falla fuerte en vez de saltearlas",
  conRepo(["verde.tests.py", "verde.test.ts"], (base, raiz) => {
    const corrida = preCommit(base, raiz, sinNode(base));
    assert.equal(corrida.status, 1, corrida.stdout + corrida.stderr);
    assert.match(corrida.stderr, /pre-commit: node no corre desde el PATH o no corre TypeScript sin flags/);
    assert.doesNotMatch(corrida.stdout, /suite en rojo/);
  }));

test("pre-commit: sin node y sin suites de TypeScript, las de Python bastan",
  conRepo(["verde.tests.py"], (base, raiz) => {
    const corrida = preCommit(base, raiz, sinNode(base));
    assert.equal(corrida.status, 0, corrida.stdout + corrida.stderr);
  }));

test("CI: el paso de las suites corre las de Python y las de TypeScript y cuenta las verdes",
  conRepo(["verde.tests.py", "verde.test.ts"], (base, raiz) => {
    const corrida = ci(base, raiz);
    assert.equal(corrida.status, 0, corrida.stdout + corrida.stderr);
    assert.match(corrida.stdout, /^ok {4}sub\/verde\.tests\.py 1\/1 pruebas en verde$/m);
    assert.match(corrida.stdout, /^ok {4}sub\/verde\.test\.ts # pass 1 # fail 0$/m);
    assert.match(corrida.stdout, /^suites con falla: 0$/m);
  }));

test("CI: una suite de TypeScript en rojo se anota como error y el paso falla, sin cortar las demas",
  conRepo(["verde.tests.py", "rojo.tests.py", "verde.test.ts", "rojo.test.ts"], (base, raiz) => {
    const corrida = ci(base, raiz);
    assert.notEqual(corrida.status, 0, corrida.stdout + corrida.stderr);
    assert.match(corrida.stdout, /^::error title=suite en rojo: sub\/rojo\.tests\.py::.*FALLA test_rojo/m);
    assert.match(corrida.stdout, /^::error title=suite en rojo: sub\/rojo\.test\.ts::.*not ok/m);
    assert.match(corrida.stdout, /^ok {4}sub\/verde\.tests\.py /m);
    assert.match(corrida.stdout, /^ok {4}sub\/verde\.test\.ts /m);
    assert.match(corrida.stdout, /^suites con falla: 2$/m);
  }));

test("CI: instala Node 24 antes de las suites, en los tres sistemas", () => {
  const texto = readFileSync(PRUEBAS, "utf8");
  assert.match(texto, /os: \[ubuntu-latest, windows-latest, macos-latest\]/);
  const node = texto.indexOf("- uses: actions/setup-node@v4\n        with:\n          node-version: \"24\"\n");
  assert.ok(node > texto.indexOf("- uses: actions/setup-python@v5"), "setup-node con node-version \"24\", después de setup-python");
  assert.ok(node < texto.indexOf("- name: Todas las suites"), "y antes de las suites");
});
