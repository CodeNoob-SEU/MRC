import { app, BrowserWindow, shell } from "electron";
import path from "node:path";
import fs from "node:fs";
import { execFileSync, spawn, ChildProcessWithoutNullStreams } from "node:child_process";

const BACKEND_PORT = process.env.MRC_BACKEND_PORT ?? "7876";
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcessWithoutNullStreams | null = null;

function clearBackendPort(): void {
  if (process.env.MRC_SKIP_PORT_CLEANUP === "1" || process.platform !== "win32") {
    return;
  }
  const repoRoot = path.resolve(__dirname, "..", "..");
  const scriptPath = path.join(repoRoot, "scripts", "ensure_backend_port_windows.ps1");
  if (!fs.existsSync(scriptPath)) {
    console.warn(`[backend] port cleanup script not found: ${scriptPath}`);
    return;
  }
  try {
    execFileSync(
      "powershell.exe",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath, "-Port", BACKEND_PORT],
      { cwd: repoRoot, stdio: "inherit" }
    );
  } catch (error) {
    console.warn(`[backend] port cleanup failed: ${String(error)}`);
  }
}

function startBackend(): void {
  if (backendProcess) {
    return;
  }
  clearBackendPort();
  const backendDir = path.resolve(__dirname, "..", "..", "backend");
  const venvPython =
    process.platform === "win32"
      ? path.join(backendDir, ".venv", "Scripts", "python.exe")
      : path.join(backendDir, ".venv", "bin", "python");
  const python =
    process.env.MRC_PYTHON ??
    (fs.existsSync(venvPython) ? venvPython : process.platform === "win32" ? "python" : "python3");
  backendProcess = spawn(python, ["-m", "mrc_backend.run_backend"], {
    cwd: backendDir,
    env: {
      ...process.env,
      PYTHONPATH: backendDir,
      MRC_BACKEND_PORT: BACKEND_PORT
    }
  });

  backendProcess.stdout.on("data", (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.stderr.on("data", (data) => {
    console.error(`[backend] ${data.toString().trim()}`);
  });
  backendProcess.on("exit", (code, signal) => {
    console.log(`[backend] exited code=${code} signal=${signal}`);
    backendProcess = null;
  });
}

function stopBackend(): void {
  if (!backendProcess) {
    return;
  }
  if (process.platform === "win32" && backendProcess.pid) {
    spawn("taskkill.exe", ["/PID", String(backendProcess.pid), "/T", "/F"], {
      windowsHide: true
    });
  } else {
    backendProcess.kill();
  }
  backendProcess = null;
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 680,
    backgroundColor: "#f6f7f9",
    title: "MRC Integrated Acquisition",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (!app.isPackaged) {
    mainWindow.loadURL("http://127.0.0.1:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(() => {
  process.env.MRC_BACKEND_URL = BACKEND_URL;
  startBackend();
  createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  stopBackend();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
