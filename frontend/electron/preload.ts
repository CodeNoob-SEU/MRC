import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("mrc", {
  backendUrl: process.env.MRC_BACKEND_URL ?? "http://127.0.0.1:8765"
});

