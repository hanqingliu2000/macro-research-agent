import { createContext, useContext } from "react";

import type { AgentAttachment, AgentSession } from "../domain/types";

export interface AgentContextValue {
  sessions: AgentSession[];
  createSession(request: string, attachments: AgentAttachment[], files?: File[]): AgentSession | Promise<AgentSession>;
  submitClarifications(sessionId: string, answers: Record<string, string>): void;
  sendMessage(sessionId: string, body: string): void;
  resetDemo(): void;
  execute(sessionId: string, type: string, args?: Record<string, unknown>): Promise<void>;
  pending: Record<string, boolean>;
  error: string;
  loading?: boolean;
}

export const AgentContext = createContext<AgentContextValue | null>(null);

export function useAgent() {
  const context = useContext(AgentContext);
  if (!context) throw new Error("useAgent must be used inside AgentProvider");
  return context;
}
