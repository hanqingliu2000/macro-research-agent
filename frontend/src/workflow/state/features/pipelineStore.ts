import type { PipelineState, WorkflowSession } from "../../domain/types";
import { mapSessions, type WorkflowStoreAction } from "./storeAction";

export type PipelineStore = Record<string, PipelineState>;

export function createPipelineStore(sessions: WorkflowSession[]): PipelineStore {
  return mapSessions(sessions, (session) => session.pipeline);
}

export function pipelineReducer(
  state: PipelineStore,
  action: WorkflowStoreAction,
): PipelineStore {
  if (action.type === "replace") return createPipelineStore(action.sessions);
  return { ...state, [action.session.id]: action.session.pipeline };
}
