import type { ReactNode } from "react";
import { Link, Navigate, Outlet, useLocation, useParams } from "react-router-dom";

import {
  isStageReachable,
  latestReachableStage,
} from "../domain/workflowEngine";
import {
  SESSION_STATUS_LABELS,
  type WorkflowStage,
} from "../domain/types";
import { useWorkflow } from "../state/WorkflowContextCore";
import { StageNavigation } from "./StageNavigation";
import { WorkbenchIcon } from "../../ui/components/WorkbenchIcon";
import { useWorkflowSession } from "./useWorkflowSession";

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function WorkflowSessionLayout() {
  const { sessionId = "" } = useParams();
  const { conflict, error, loading, sessions } = useWorkflow();
  const session = sessions.find((item) => item.id === sessionId);
  const location = useLocation();

  if (loading) {
    return <main className="workflow-workspace"><p className="workspace-notice" role="status">Loading Workflow session…</p></main>;
  }

  if (!session) {
    return <Navigate replace to="/not-found" />;
  }
  if (session.archived) return <Navigate replace to="/" />;

  const routeNotice = (location.state as { guardNotice?: string } | null)?.guardNotice;

  return (
    <main className="workflow-workspace">
      <header className="workflow-workspace-header">
        <div className="workbench-toolbar">
          <div className="workspace-breadcrumbs">
            <Link className="back-link" to="/"><WorkbenchIcon name="chevron-left" /> Sessions</Link>
            <span>/</span>
            <strong>{session.title}</strong>
          </div>
          <div className="workspace-header-meta">
            <span className={`status-badge status-${session.status}`}>
              {SESSION_STATUS_LABELS[session.status]}
            </span>
            <span className="saved-state"><WorkbenchIcon name="check" /> Saved {formatTime(session.updatedAt)}</span>
          </div>
        </div>
        <StageNavigation session={session} />
        {(routeNotice || session.lastNotice) && (
          <p className="workspace-notice" role="status"><WorkbenchIcon name="info" />{routeNotice ?? session.lastNotice}</p>
        )}
        {error && <p className="workspace-notice" role="alert">{error}</p>}
        {conflict && (
          <p className="workspace-notice" role="status">
            Server state reloaded at {conflict.currentStage} ({conflict.currentSnapshotHash}).
          </p>
        )}
      </header>
      <Outlet context={session} />
    </main>
  );
}

export function WorkflowSessionIndex() {
  const session = useWorkflowSession();
  return <Navigate replace to={`/sessions/${session.id}/${latestReachableStage(session)}`} />;
}

export function StageGuard({
  stage,
  children,
}: {
  stage: WorkflowStage;
  children: ReactNode;
}) {
  const session = useWorkflowSession();
  if (!isStageReachable(session, stage)) {
    const fallback = latestReachableStage(session);
    return (
      <Navigate
        replace
        state={{ guardNotice: `${stage} is not ready. Complete ${fallback} first.` }}
        to={`/sessions/${session.id}/${fallback}`}
      />
    );
  }
  return children;
}
