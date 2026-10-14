import type { WorkflowSession } from "../domain/types";
import { createDataStore, dataReducer, type DataStore } from "./features/dataStore";
import { createOutputStore, outputReducer, type OutputStore } from "./features/outputStore";
import { createPipelineStore, pipelineReducer, type PipelineStore } from "./features/pipelineStore";
import { createPlanStore, planReducer, type PlanStore } from "./features/planStore";
import {
  createSessionProjectionStore,
  sessionProjectionReducer,
  type SessionProjectionStore,
} from "./features/sessionProjectionStore";
import type { WorkflowStoreAction } from "./features/storeAction";

export interface WorkflowStoreState {
  sessionProjection: SessionProjectionStore;
  plan: PlanStore;
  data: DataStore;
  pipeline: PipelineStore;
  output: OutputStore;
}

export function createWorkflowStore(sessions: WorkflowSession[]): WorkflowStoreState {
  return {
    sessionProjection: createSessionProjectionStore(sessions),
    plan: createPlanStore(sessions),
    data: createDataStore(sessions),
    pipeline: createPipelineStore(sessions),
    output: createOutputStore(sessions),
  };
}

export function workflowStoreReducer(
  state: WorkflowStoreState,
  action: WorkflowStoreAction,
): WorkflowStoreState {
  return {
    sessionProjection: sessionProjectionReducer(state.sessionProjection, action),
    plan: planReducer(state.plan, action),
    data: dataReducer(state.data, action),
    pipeline: pipelineReducer(state.pipeline, action),
    output: outputReducer(state.output, action),
  };
}

export function selectWorkflowSessions(state: WorkflowStoreState): WorkflowSession[] {
  return state.sessionProjection.order.flatMap((sessionId) => {
    const projection = state.sessionProjection.byId[sessionId];
    const plan = state.plan[sessionId];
    const data = state.data[sessionId];
    const pipeline = state.pipeline[sessionId];
    const output = state.output[sessionId];
    if (!projection || !plan || !data || !pipeline || !output) return [];
    return [{ ...projection, ...plan, data, pipeline, ...output }];
  });
}
