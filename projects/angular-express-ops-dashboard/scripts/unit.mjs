import { spawn } from "node:child_process";
import { chromium } from "@playwright/test";
const child = spawn(
  process.execPath,
  ["node_modules/@angular/cli/bin/ng.js", "test", "--watch=false"],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      CHROME_BIN: chromium.executablePath(),
      NG_CLI_ANALYTICS: "false",
    },
  },
);
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
