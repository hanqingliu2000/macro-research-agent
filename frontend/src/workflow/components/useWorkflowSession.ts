import { useOutletContext } from "react-router-dom";

import type { WorkflowSession } from "../domain/types";

export function useWorkflowSession() {
  return useOutletContext<WorkflowSession>();
}
