import type { WorkflowSession } from "../../domain/types";

export type WorkflowStoreAction =
  | { type: "replace"; sessions: WorkflowSession[] }
  | { type: "upsert"; session: WorkflowSession };

export function mapSessions<T>(
  sessions: WorkflowSession[],
  project: (session: WorkflowSession) => T,
) {
  return Object.fromEntries(sessions.map((session) => [session.id, project(session)]));
}
