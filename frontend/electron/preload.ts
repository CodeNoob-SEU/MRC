import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("mrc", {
  backendUrl: process.env.MRC_BACKEND_URL ?? "http://127.0.0.1:7876",
  selectOutputDirectory: () => ipcRenderer.invoke("select-output-directory"),
  openLogDirectory: () => ipcRenderer.invoke("open-log-directory")
});
