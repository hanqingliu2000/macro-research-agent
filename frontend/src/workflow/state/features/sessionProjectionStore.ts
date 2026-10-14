import type {
  StageHealth,
  WorkflowNode,
  WorkflowSession,
  WorkflowSessionStatus,
  WorkflowStage,
} from "../../domain/types";
import { mapSessions, type WorkflowStoreAction } from "./storeAction";

export interface SessionProjection {
  id: string;
  title: string;
  request: string;
  status: WorkflowSessionStatus;
  activeStage: WorkflowStage;
  reachedStages: WorkflowStage[];
  stageHealth: Record<WorkflowStage, StageHealth>;
  createdAt: string;
  updatedAt: string;
  archived: boolean;
  nodes: WorkflowNode[];
  lastNotice?: string;
}

export interface SessionProjectionStore {
  order: string[];
  byId: Record<string, SessionProjection>;
}

export function projectSession(session: WorkflowSession): SessionProjection {
  return {
    id: session.id,
    title: session.title,
    request: session.request,
    status: session.status,
    activeStage: session.activeStage,
    reachedStages: session.reachedStages,
    stageHealth: session.stageHealth,
    createdAt: session.createdAt,
    updatedAt: session.updatedAt,
    archived: session.archived,
    nodes: session.nodes,
    lastNotice: session.lastNotice,
  };
}

export function createSessionProjectionStore(
  sessions: WorkflowSession[],
): SessionProjectionStore {
  return {
    order: sessions.map((session) => session.id),
    byId: mapSessions(sessions, projectSession),
  };
}

export function sessionProjectionReducer(
  state: SessionProjectionStore,
  action: WorkflowStoreAction,
): SessionProjectionStore {
  if (action.type === "replace") return createSessionProjectionStore(action.sessions);
  return {
    order: state.order.includes(action.session.id)
      ? state.order
      : [action.session.id, ...state.order],
    byId: { ...state.byId, [action.session.id]: projectSession(action.session) },
  };
}
