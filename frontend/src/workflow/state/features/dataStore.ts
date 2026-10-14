import type { DataWorkspaceState, WorkflowSession } from "../../domain/types";
import { mapSessions, type WorkflowStoreAction } from "./storeAction";

export type DataStore = Record<string, DataWorkspaceState>;

export function createDataStore(sessions: WorkflowSession[]): DataStore {
  return mapSessions(sessions, (session) => session.data);
}

export function dataReducer(state: DataStore, action: WorkflowStoreAction): DataStore {
  if (action.type === "replace") return createDataStore(action.sessions);
  return { ...state, [action.session.id]: action.session.data };
}
