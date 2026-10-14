import { type ChangeEvent, type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { WorkbenchIcon } from "../../ui/components/WorkbenchIcon";
import type { AgentAttachment } from "../domain/types";
import { AGENT_STATUS_LABELS } from "../domain/types";
import { useAgent } from "../state/AgentContextCore";

const allowedExtensions = new Set(["csv", "json", "xlsx"]);

function extension(name: string) {
  return name.split(".").at(-1)?.toLowerCase() ?? "";
}

function metadata(file: File): AgentAttachment {
  return {
    id: `attachment-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    name: file.name,
    mediaType: file.type || `application/${extension(file.name)}`,
    size: file.size,
  };
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  return `${Math.round(value / 102.4) / 10} KB`;
}

export function AgentHomePage() {
  const { sessions, createSession } = useAgent();
  const [request, setRequest] = useState("");
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const [fileError, setFileError] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const chooseFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    const rejected = files.filter((file) => !allowedExtensions.has(extension(file.name)));
    if (rejected.length) {
      setFileError("Only .csv, .json and .xlsx attachments are accepted.");
      return;
    }
    setFileError("");
    setAttachments(files.map(metadata));
    setFiles(files);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = request.trim();
    if (!trimmed) return;
    const created = createSession(trimmed, attachments, files.filter(file => attachments.some(item => item.name === file.name)));
    if (created instanceof Promise) {
      setCreating(true);
      void created.then(session => navigate(`/agent/${session.id}`)).catch(reason => setFileError(reason.message))
        .finally(() => setCreating(false));
    } else navigate(`/agent/${created.id}`);
  };

  return (
    <main className="agent-home-page">
      <header className="agent-page-header">
        <div>
          <h1>Agent Research Workbench</h1>
        </div>
      </header>

      <section className="agent-prompt-card">
        <form onSubmit={submit}>
          <label className="sr-only" htmlFor="agent-request">Research question</label>
          <textarea
            id="agent-request"
            rows={7}
            value={request}
            onChange={(event) => setRequest(event.target.value)}
            placeholder="For example: Compare inflation normalization and monetary policy across the US, euro area and Japan…"
          />
          <div className="agent-attachment-row">
            <label className="secondary-button agent-file-button" htmlFor="agent-files">
              <WorkbenchIcon name="paperclip" />Attach data
              <input
                accept=".csv,.json,.xlsx"
                aria-describedby={fileError ? "agent-file-error" : undefined}
                aria-invalid={Boolean(fileError)}
                className="sr-only"
                id="agent-files"
                multiple
                onChange={chooseFiles}
                type="file"
              />
            </label>
          </div>
          {fileError && <p className="agent-file-error" id="agent-file-error" role="alert">{fileError}</p>}
          {attachments.length > 0 && (
            <ul className="agent-file-list" aria-label="Selected attachments">
              {attachments.map((attachment) => (
                <li key={attachment.id}>
                  <WorkbenchIcon name="paperclip" />
                  <span><strong>{attachment.name}</strong><small>{formatBytes(attachment.size)} · {attachment.mediaType}</small></span>
                  <button aria-label={`Remove ${attachment.name}`} onClick={() => setAttachments(attachments.filter((item) => item.id !== attachment.id))} type="button"><WorkbenchIcon name="trash" /></button>
                </li>
              ))}
            </ul>
          )}
          <div className="agent-submit-row">
            <button className="primary-button" disabled={creating || !request.trim()} type="submit">
              <WorkbenchIcon name="agent" />{creating ? "Starting…" : "Start agent run"}
            </button>
          </div>
        </form>
      </section>

      <section className="agent-session-section" aria-labelledby="agent-sessions-title">
        <div className="section-title-row">
          <div>
            <p className="eyebrow">AGENT SESSIONS</p>
            <h2 id="agent-sessions-title">Independent experimental runs</h2>
          </div>
          <span>{sessions.length} total</span>
        </div>
        <div className="agent-session-grid">
          {sessions.map((session) => (
            <Link key={session.id} title={session.title} to={`/agent/${session.id}`}>
              <WorkbenchIcon name="file" />
              <span><strong>{session.title}</strong><small>{session.attachments.length} attachment(s)</small></span>
              <span className={`status-badge status-${session.status}`}>{AGENT_STATUS_LABELS[session.status]}</span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
