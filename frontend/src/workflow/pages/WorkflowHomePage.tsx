import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { SESSION_STATUS_LABELS } from "../domain/types";
import { useWorkflow } from "../state/WorkflowContextCore";
import { WorkbenchIcon } from "../../ui/components/WorkbenchIcon";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function WorkflowHomePage() {
  const { sessions, createSession, importSession, uploadSource, setSessionDeleted, error, loading, pending } = useWorkflow();
  const [showDeleted, setShowDeleted] = useState(false);
  const [notice, setNotice] = useState("");
  const [request, setRequest] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const navigate = useNavigate();

  const changeDeleted = async (sessionId: string, title: string, deleted: boolean) => {
    if (deleted && !window.confirm(`Move “${title}” to Trash? You can restore it later. Files and research history will be retained.`)) return;
    try {
      await setSessionDeleted(sessionId, deleted);
      setNotice(deleted ? "Session moved to Trash. You can restore it below." : "Session restored.");
    } catch {
      // Keep the row available for retry; the provider exposes the error.
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = request.trim();
    if (!trimmed) return;
    try {
      const session = await createSession(trimmed);
      for (const file of files) await uploadSource(session.id, file);
      navigate(`/sessions/${session.id}/plan`);
    } catch {
      // Provider exposes the user-visible error while retaining the current form input.
    }
  };

  const importArchive = async (file?: File) => {
    if (!file) return;
    try {
      const session = await importSession(file);
      navigate(`/sessions/${session.id}/${session.activeStage}`);
    } catch {
      // Provider keeps the archive available for retry and exposes the error.
    }
  };

  return (
    <main className="home-page">
      <header className="page-topbar">
        <div>
          <h1>Macro Research Workbench</h1>
        </div>
      </header>

      <section className="home-grid">
        <div className="new-research-panel">
          <form onSubmit={submit}>
            <label className="sr-only" htmlFor="research-request">Research request</label>
            <textarea
              id="research-request"
              onChange={(event) => setRequest(event.target.value)}
              placeholder="Describe the question, economies, period and expected deliverables…"
              rows={6}
              value={request}
            />
            <div className="form-footer">
              <label className="home-file-button" htmlFor="workflow-source-files">
                <WorkbenchIcon name="paperclip" />
                {files.length ? `${files.length} file${files.length === 1 ? "" : "s"}` : "Attach data"}
              </label>
              <input
                accept=".csv,.json,.xlsx"
                className="sr-only"
                id="workflow-source-files"
                multiple
                onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                type="file"
              />
              <button className="primary-button" disabled={!request.trim() || pending} type="submit">
                Start planning
              </button>
            </div>
          </form>
        </div>

        <aside className="principles-panel">
          <p className="panel-kicker">FOUR STAGES</p>
          <ol>
            {["Clarify and confirm the Plan", "Review and prepare Data", "Configure and run Transformation", "Review and export Output"].map((label, index) => (
              <li key={label}><span>0{index + 1}</span><div><strong>{label}</strong></div></li>
            ))}
          </ol>
        </aside>
      </section>

      {error && <p className="workspace-notice" role="alert">{error}</p>}
      {notice && <p className="workspace-notice" role="status">{notice}</p>}

      <section className="sessions-section" aria-labelledby="sessions-title">
        <div className="section-title-row">
          <div><p className="eyebrow">WORKFLOW SESSIONS</p><h2 className="sr-only" id="sessions-title">Workflow sessions</h2></div>
          <div className="session-section-actions">
            <span>{sessions.filter((session) => !session.archived).length} active</span>
            <button className="secondary-button" aria-pressed={showDeleted} onClick={() => setShowDeleted(!showDeleted)} type="button">
              {showDeleted ? "Show active" : "Trash"}
            </button>
            <label className="compact-file-button" htmlFor="portable-session-import">
              Import session
            </label>
            <input
              accept=".zip,.mra.zip,application/zip"
              className="sr-only"
              disabled={pending}
              id="portable-session-import"
              onChange={(event) => {
                void importArchive(event.target.files?.[0]);
                event.target.value = "";
              }}
              type="file"
            />
          </div>
        </div>
        <div className="session-table" role="table" aria-label="Workflow sessions">
          <div className="session-table-head" role="row">
            <span role="columnheader">Research</span><span role="columnheader">Status</span><span role="columnheader">Updated</span><span />
          </div>
          {loading && <p className="workspace-notice" role="status">Loading Workflow sessions…</p>}
          {sessions.filter((session) => session.archived === showDeleted).map((session) => (
            <div className="session-row" key={session.id} role="row">
              <span className="session-name" role="cell">
                {session.archived ? <strong>{session.title}</strong> : <Link to={`/sessions/${session.id}/${session.activeStage}`}><strong>{session.title}</strong></Link>}
                <small>{session.request}</small>
              </span>
              <span role="cell"><span className={`status-badge status-${session.status}`}>{SESSION_STATUS_LABELS[session.status]}</span></span>
              <span role="cell">{formatDate(session.updatedAt)}</span>
              <span role="cell"><button className="secondary-button session-delete-button" disabled={pending} aria-label={`${session.archived ? "Restore" : "Delete"} ${session.title}`} onClick={() => void changeDeleted(session.id, session.title, !session.archived)} type="button">{session.archived ? "Restore" : "Delete"}</button></span>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
