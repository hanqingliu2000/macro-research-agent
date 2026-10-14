import { Route, Routes } from "react-router-dom";

import { AgentShell } from "../agent/components/AgentShell";
import { AgentHomePage } from "../agent/pages/AgentHomePage";
import { AgentChatPage } from "../agent/pages/AgentChatPage";
import { AgentProvider } from "../agent/state/AgentContext";
import { NotFoundPage } from "../pages/NotFoundPage";
import {
  StageGuard,
  WorkflowSessionIndex,
  WorkflowSessionLayout,
} from "../workflow/components/WorkflowSessionLayout";
import { WorkflowShell } from "../workflow/components/WorkflowShell";
import { DataStagePage } from "../workflow/pages/data/DataStagePage";
import { OutputStagePage } from "../workflow/pages/output/OutputStagePage";
import { PlanStagePage } from "../workflow/pages/plan/PlanStagePage";
import { TransformationStagePage } from "../workflow/pages/transformation/TransformationStagePage";
import { WorkflowHomePage } from "../workflow/pages/WorkflowHomePage";
import { WorkflowNotFoundPage } from "../workflow/pages/WorkflowNotFoundPage";
import { WorkflowSettingsPage } from "../workflow/pages/WorkflowSettingsPage";
import { WorkflowProvider } from "../workflow/state/WorkflowContext";

function WorkflowArea() {
  return (
    <WorkflowProvider>
      <WorkflowShell>
        <Routes>
          <Route element={<WorkflowHomePage />} index />
          <Route element={<WorkflowSettingsPage />} path="settings" />
          <Route element={<WorkflowSessionLayout />} path="sessions/:sessionId">
            <Route element={<WorkflowSessionIndex />} index />
            <Route
              element={<StageGuard stage="plan"><PlanStagePage /></StageGuard>}
              path="plan"
            />
            <Route
              element={<StageGuard stage="data"><DataStagePage /></StageGuard>}
              path="data"
            />
            <Route
              element={<StageGuard stage="transformation"><TransformationStagePage /></StageGuard>}
              path="transformation"
            />
            <Route
              element={<StageGuard stage="output"><OutputStagePage /></StageGuard>}
              path="output"
            />
          </Route>
          <Route element={<WorkflowNotFoundPage />} path="not-found" />
          <Route element={<WorkflowNotFoundPage />} path="*" />
        </Routes>
      </WorkflowShell>
    </WorkflowProvider>
  );
}

function AgentArea() {
  return (
    <AgentProvider>
      <AgentShell>
        <Routes>
          <Route element={<AgentHomePage />} index />
          <Route element={<AgentChatPage />} path=":agentSessionId" />
          <Route element={<NotFoundPage />} path="*" />
        </Routes>
      </AgentShell>
    </AgentProvider>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AgentArea />} path="/agent/*" />
      <Route element={<WorkflowArea />} path="/*" />
    </Routes>
  );
}
