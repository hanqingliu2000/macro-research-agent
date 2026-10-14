import type { OutputState, StageMessage, WorkflowSession } from "../../domain/types";
import { mapSessions, type WorkflowStoreAction } from "./storeAction";

export interface OutputFeatureState {
  outputThread: StageMessage[];
  output: OutputState;
}

export type OutputStore = Record<string, OutputFeatureState>;

export function projectOutput(session: WorkflowSession): OutputFeatureState {
  return { outputThread: session.outputThread, output: session.output };
}

export function createOutputStore(sessions: WorkflowSession[]): OutputStore {
  return mapSessions(sessions, projectOutput);
}

export function outputReducer(state: OutputStore, action: WorkflowStoreAction): OutputStore {
  if (action.type === "replace") return createOutputStore(action.sessions);
  return { ...state, [action.session.id]: projectOutput(action.session) };
}
