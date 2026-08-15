import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import net from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const webuiRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(webuiRoot, "..");
const options = parseOptions(process.argv.slice(2));
const workspace = resolve(options.workspace ?? join(repositoryRoot, "tmp", "webui-daemon"));
const descriptor = join(workspace, ".liteyuki", "instances", options.instance, "daemon.json");

await ensureDaemon();
const handoff = await requestControl("webui.open");
if (!handoff || typeof handoff.url !== "string") throw new Error("daemon returned an invalid WebUI handoff URL");

const daemonUrl = new URL(handoff.url);
const ticket = daemonUrl.hash;
if (!/^#ticket=[^&]+$/.test(ticket)) throw new Error("daemon returned an invalid WebUI ticket");

const viteArguments = [
  join(webuiRoot, "node_modules", "vite", "bin", "vite.js"), "--host", "127.0.0.1", "--port", String(options.port), "--strictPort",
];
if (!options.noOpen) viteArguments.push("--open", `/${ticket}`);
if (!existsSync(viteArguments[0])) throw new Error("Vite is not installed; run `pnpm --dir webui install --frozen-lockfile`");

console.log(`Proxying /api to ${daemonUrl.origin}; daemon workspace: ${workspace}`);
const vite = spawn(process.execPath, viteArguments, {
  cwd: webuiRoot,
  env: { ...process.env, LITEYUKI_WEBUI_PROXY_TARGET: daemonUrl.origin },
  stdio: "inherit",
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => vite.kill(signal));
}
vite.once("exit", (code, signal) => process.exitCode = code ?? (signal ? 1 : 0));

async function ensureDaemon() {
  try {
    await requestControl("status");
    return;
  } catch {
    if (!existsSync(join(workspace, "liteyuki.toml"))) {
      await run("uv", ["run", "--extra", "webui", "liteyuki", "--workspace", workspace, "init", "--non-interactive", "--locale", "en-US"]);
    }
    await run("uv", [
      "run", "--extra", "webui", "liteyuki", "--workspace", workspace, "--instance", options.instance,
      "--set", "webui.mode=always", "--set", "webui.port=0", "run", "--detach",
    ]);
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await delay(250);
      try {
        await requestControl("status");
        return;
      } catch {
        // The detached daemon has not published its descriptor yet.
      }
    }
    throw new Error(`daemon did not become ready; inspect ${join(workspace, ".liteyuki", "instances", options.instance, "logs", "daemon.log")}`);
  }
}

async function requestControl(command) {
  const value = JSON.parse(await readFile(descriptor, "utf8"));
  if (
    value?.protocol !== 1 || value.host !== "127.0.0.1" || !Number.isInteger(value.port)
    || value.port < 1 || value.port > 65535 || typeof value.token !== "string" || !value.token
  ) {
    throw new Error(`invalid daemon descriptor: ${descriptor}`);
  }
  return await new Promise((resolveResponse, reject) => {
    const socket = net.createConnection({ host: value.host, port: value.port });
    let buffer = "";
    const timeout = setTimeout(() => socket.destroy(new Error("daemon control request timed out")), 5000);
    socket.setEncoding("utf8");
    socket.once("connect", () => socket.write(`${JSON.stringify({ token: value.token, command })}\n`));
    socket.on("data", (chunk) => {
      buffer += chunk;
      if (!buffer.includes("\n")) return;
      socket.end();
      try {
        const response = JSON.parse(buffer);
        if (!response?.ok) throw new Error(response?.error ?? "invalid daemon control response");
        resolveResponse(response.result);
      } catch (error) {
        reject(error);
      }
    });
    socket.once("error", reject);
    socket.once("close", () => clearTimeout(timeout));
  });
}

function run(command, arguments_) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(command, arguments_, { cwd: repositoryRoot, stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code) => code === 0 ? resolveRun() : reject(new Error(`${command} exited with ${code}`)));
  });
}

function parseOptions(arguments_) {
  const options_ = { instance: "default", port: 5173, workspace: undefined, noOpen: false };
  for (let index = 0; index < arguments_.length; index += 1) {
    const value = arguments_[index];
    if (value === "--workspace") options_.workspace = requiredValue(arguments_, ++index, value);
    else if (value === "--instance") options_.instance = requiredValue(arguments_, ++index, value);
    else if (value === "--port") options_.port = Number(requiredValue(arguments_, ++index, value));
    else if (value === "--no-open") options_.noOpen = true;
    else if (value === "--help") {
      console.log("Usage: pnpm run web -- [--workspace PATH] [--instance NAME] [--port PORT] [--no-open]");
      process.exit(0);
    } else throw new Error(`unknown option: ${value}`);
  }
  if (!Number.isInteger(options_.port) || options_.port < 1 || options_.port > 65535) throw new Error("--port must be 1..65535");
  if (!/^[a-z0-9](?:[a-z0-9-]{0,62})$/.test(options_.instance)) throw new Error("--instance must use lower-case ASCII letters, digits, or hyphens");
  return options_;
}

function requiredValue(arguments_, index, option) {
  const value = arguments_[index];
  if (!value || value.startsWith("--")) throw new Error(`${option} requires a value`);
  return value;
}

function delay(milliseconds) {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}
