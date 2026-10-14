import type {
  ClarificationBatch,
  PlanDraft,
  PlanPatchProposal,
  PlanSnapshot,
  StageMessage,
  WorkflowSession,
} from "../../domain/types";
import { mapSessions, type WorkflowStoreAction } from "./storeAction";

export interface PlanFeatureState {
  clarification: ClarificationBatch;
  planThread: StageMessage[];
  currentPlan?: PlanDraft;
  planSnapshots: PlanSnapshot[];
  currentPlanSnapshotId?: string;
  approvedPlanSnapshotId?: string;
  pendingPlanPatch?: PlanPatchProposal;
}

export type PlanStore = Record<string, PlanFeatureState>;

export function projectPlan(session: WorkflowSession): PlanFeatureState {
  return {
    clarification: session.clarification,
    planThread: session.planThread,
    currentPlan: session.currentPlan,
    planSnapshots: session.planSnapshots,
    currentPlanSnapshotId: session.currentPlanSnapshotId,
    approvedPlanSnapshotId: session.approvedPlanSnapshotId,
    pendingPlanPatch: session.pendingPlanPatch,
  };
}

export function createPlanStore(sessions: WorkflowSession[]): PlanStore {
  return mapSessions(sessions, projectPlan);
}

export function planReducer(state: PlanStore, action: WorkflowStoreAction): PlanStore {
  if (action.type === "replace") return createPlanStore(action.sessions);
  return { ...state, [action.session.id]: projectPlan(action.session) };
}
