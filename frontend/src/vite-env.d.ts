/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WORKFLOW_ADAPTER?: "mock" | "http";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
