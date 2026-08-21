#!/usr/bin/env node

import { spawn } from "node:child_process";

const child = spawn("liteyuki-dev", process.argv.slice(2), {
  stdio: "inherit",
  shell: process.platform === "win32",
});

child.on("error", (error) => {
  console.error(`liteyuki-dev is not installed: ${error.message}`);
  process.exitCode = 127;
});
child.on("exit", (code, signal) => {
  process.exitCode = signal ? 1 : code ?? 1;
});
