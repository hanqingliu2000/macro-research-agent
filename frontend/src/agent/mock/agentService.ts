import type { AgentSession } from "../domain/types";
import { seedAgentSessions } from "./fixtures";

export const AGENT_SESSION_STORAGE_KEY =
  "macro-research-agent.agent.mock.sessions.v1";

function storageAvailable() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export interface AgentService {
  listSessions(): AgentSession[];
  saveSessions(sessions: AgentSession[]): void;
  reset(): AgentSession[];
}

export class MockAgentService implements AgentService {
  listSessions(): AgentSession[] {
    if (!storageAvailable()) return seedAgentSessions();
    const stored = window.localStorage.getItem(AGENT_SESSION_STORAGE_KEY);
    if (!stored) {
      const seeded = seedAgentSessions();
      this.saveSessions(seeded);
      return seeded;
    }
    try {
      return JSON.parse(stored) as AgentSession[];
    } catch {
      return this.reset();
    }
  }

  saveSessions(sessions: AgentSession[]) {
    if (storageAvailable()) {
      window.localStorage.setItem(AGENT_SESSION_STORAGE_KEY, JSON.stringify(sessions));
    }
  }

  reset() {
    const seeded = seedAgentSessions();
    this.saveSessions(seeded);
    return seeded;
  }
}

export const agentService = new MockAgentService();
