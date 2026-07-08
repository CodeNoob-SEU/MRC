import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import type { OpenDialogOptions } from "electron";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";
import { execFileSync, spawn, ChildProcessWithoutNullStreams } from "node:child_process";

const BACKEND_PORT = process.env.MRC_BACKEND_PORT ?? "7876";
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcessWithoutNullStreams | null = null;
let quitInProgress = false;

function clearBackendPort(): boolean {
  if (process.env.MRC_SKIP_PORT_CLEANUP === "1" || process.platform !== "win32") {
    return true;
  }
  const repoRoot = path.resolve(__dirname, "..", "..");
  const scriptPath = path.join(repoRoot, "scripts", "ensure_backend_port_windows.ps1");
  if (!fs.existsSync(scriptPath)) {
    console.warn(`[backend] port cleanup script not found: ${scriptPath}`);
    return true;
  }
  try {
    execFileSync(
      "powershell.exe",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath, "-Port", BACKEND_PORT],
      { cwd: repoRoot, stdio: "inherit" }
    );
    return true;
  } catch (error) {
    console.warn(`[backend] port cleanup failed: ${String(error)}`);
    return false;
  }
}

function startBackend(): void {
  if (backendProcess) {
    return;
  }
  if (!clearBackendPort()) {
    return;
  }
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
  backendProcess.on("error", (error) => {
    console.error(`[backend] failed to start: ${String(error)}`);
    backendProcess = null;
  });
  backendProcess.on("exit", (code, signal) => {
    console.log(`[backend] exited code=${code} signal=${signal}`);
    backendProcess = null;
  });
}

function postShutdownFast(timeoutMs: number): Promise<boolean> {
  if (process.env.MRC_FAST_BACKEND_SHUTDOWN === "0") {
    return Promise.resolve(false);
  }
  return new Promise((resolve) => {
    const request = http.request(
      { host: "127.0.0.1", port: Number(BACKEND_PORT), path: "/shutdown-fast", method: "POST" },
      (response) => {
        response.resume();
        resolve((response.statusCode ?? 500) < 400);
      }
    );
    request.setTimeout(timeoutMs, () => {
      request.destroy();
      resolve(false);
    });
    request.on("error", () => resolve(false));
    request.end();
  });
}

function waitForBackendExit(timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    const child = backendProcess;
    if (!child || child.exitCode !== null) {
      resolve(true);
      return;
    }
    const onExit = () => {
      clearTimeout(timer);
      resolve(true);
    };
    const timer = setTimeout(() => {
      child.off("exit", onExit);
      resolve(false);
    }, timeoutMs);
    child.once("exit", onExit);
  });
}

function killBackendTree(): void {
  const child = backendProcess;
  if (!child || child.exitCode !== null || !child.pid) {
    return;
  }
  if (process.platform === "win32") {
    try {
      execFileSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
        timeout: 3000
      });
    } catch (error) {
      console.warn(`[backend] taskkill failed: ${String(error)}`);
    }
  } else {
    child.kill("SIGKILL");
  }
}

async function stopBackendAsync(): Promise<void> {
  const child = backendProcess;
  if (!child) {
    return;
  }
  if (process.platform === "win32") {
    if (await postShutdownFast(1500)) {
      if (await waitForBackendExit(4000)) {
        backendProcess = null;
        return;
      }
    }
    killBackendTree();
  } else {
    child.kill();
    if (!(await waitForBackendExit(5000))) {
      child.kill("SIGKILL");
    }
  }
  await waitForBackendExit(2000);
  backendProcess = null;
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 960,
    minWidth: 1280,
    minHeight: 760,
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
  ipcMain.handle("select-output-directory", async () => {
    const options: OpenDialogOptions = {
      title: "选择输出根目录",
      properties: ["openDirectory", "createDirectory"]
    };
    const result = mainWindow
      ? await dialog.showOpenDialog(mainWindow, options)
      : await dialog.showOpenDialog(options);
    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }
    return result.filePaths[0];
  });
  process.env.MRC_BACKEND_URL = BACKEND_URL;
  startBackend();
  createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", (event) => {
  if (quitInProgress || !backendProcess) {
    return;
  }
  quitInProgress = true;
  event.preventDefault();
  const hardDeadline = new Promise<void>((resolve) => setTimeout(resolve, 8000));
  void Promise.race([stopBackendAsync(), hardDeadline]).finally(() => app.exit(0));
});

process.once("SIGINT", () => {
  app.quit();
});

process.once("SIGTERM", () => {
  app.quit();
});

process.once("exit", () => {
  // Last-resort synchronous cleanup; normally the backend is already gone.
  killBackendTree();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
