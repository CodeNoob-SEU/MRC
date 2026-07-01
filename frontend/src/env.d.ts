/// <reference types="vite/client" />

interface Window {
  mrc?: {
    backendUrl: string;
    selectOutputDirectory?: () => Promise<string | null>;
  };
}
