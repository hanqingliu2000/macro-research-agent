import { HttpWorkflowService } from "./httpWorkflowService";
import { MockWorkflowService } from "./mockWorkflowService";

export type { WorkflowService } from "./workflowService";
export { WorkflowHttpConflict } from "./workflowService";

export const workflowService =
  import.meta.env.VITE_WORKFLOW_ADAPTER === "http"
    ? new HttpWorkflowService()
    : new MockWorkflowService();
