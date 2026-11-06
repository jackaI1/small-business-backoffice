import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
const children = [
  spawn(process.execPath, ["--import", "tsx", "server/src/index.ts"], {
    stdio: "inherit",
  }),
  spawn(process.execPath, ["node_modules/@angular/cli/bin/ng.js", "serve"], {
    cwd: "web",
    stdio: "inherit",
  }),
  spawn(
    process.execPath,
    ["node_modules/@angular/cli/bin/ng.js", "serve", "--port", "4201"],
    {
      stdio: "inherit",
    },
  ),
];
mkdirSync(".runtime", { recursive: true });
writeFileSync(
  ".runtime/dev.json",
  JSON.stringify({
    owner: "venue dev command",
    pid: process.pid,
    started: new Date().toISOString(),
    children: children.map((child, i) => ({
      pid: child.pid,
      port: [3000, 4200, 4201][i],
    })),
    cleanup: `kill -TERM ${process.pid}`,
  }),
);
let stopping = false;
function stop() {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill("SIGTERM");
}
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, stop);
for (const child of children)
  child.on("exit", (code) => {
    if (code && !stopping) process.exitCode = code;
    stop();
  });
process.on("exit", () => rmSync(".runtime/dev.json", { force: true }));
