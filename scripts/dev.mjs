import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const portIndex = args.indexOf("--port");
const port = portIndex >= 0 ? args[portIndex + 1] : process.env.PORT || "3000";
const python =
  process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
const readiness = spawnSync(python, ["-c", "import sys; assert sys.version_info[:2] == (3, 12); import uvicorn, fastapi, pydantic, httpx"], { cwd: root, encoding: "utf8" });
if (readiness.error || readiness.status !== 0) {
  console.error("Backend environment is incomplete or uses another Python version. Run bash scripts/install.sh with Python 3.12. On Windows, create .venv using py -3.12.");
  process.exit(1);
}
const backend = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "backend.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
  ],
  { cwd: root, stdio: "inherit", env: process.env },
);
const frontend = spawn(
  process.execPath,
  [
    path.join(root, "frontend", "node_modules", "next", "dist", "bin", "next"),
    "dev",
    "--hostname",
    "0.0.0.0",
    "--port",
    port,
  ],
  { cwd: path.join(root, "frontend"), stdio: "inherit", env: process.env },
);
let closing = false;
function close(code = 0) {
  if (closing) return;
  closing = true;
  backend.kill("SIGTERM");
  frontend.kill("SIGTERM");
  process.exitCode = code;
}
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => close());
backend.on("error", (e) => {
  console.error(e.message);
  close(1);
});
frontend.on("error", (e) => {
  console.error(e.message);
  close(1);
});
backend.on("exit", (code) => close(code ?? 0));
frontend.on("exit", (code) => close(code ?? 0));
