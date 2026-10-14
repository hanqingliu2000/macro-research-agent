import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { WorkbenchIcon } from "../../ui/components/WorkbenchIcon";
import { AgentProgressPanel } from "../components/AgentProgressPanel";
import { AgentResultView } from "../components/AgentResultView";
import { AgentRunControls } from "../components/AgentRunControls";
import { AGENT_STATUS_LABELS } from "../domain/types";
import { useAgent } from "../state/AgentContextCore";

export function AgentChatPage() {
  const { agentSessionId = "" } = useParams();
  const { sessions, submitClarifications, sendMessage, pending, error, execute, loading } = useAgent();
  const session = sessions.find((item) => item.id === agentSessionId);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [followUp, setFollowUp] = useState("");
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({});

  if (!session) {
    if (loading) return <main className="not-found-page"><p role={error ? "alert" : "status"}>{error || "Loading saved Agent run…"}</p></main>;
    return (
      <main className="not-found-page">
        <p className="eyebrow">AGENT SESSION NOT FOUND</p>
        <h1>This run does not exist in the Agent store.</h1>
        <Link className="primary-button" to="/agent">Return to Agent Mode</Link>
      </main>
    );
  }

  const effectiveAnswers = Object.fromEntries(session.clarification.questions.map(question => [question.id,
    customAnswers[question.id]?.trim() || answers[question.id] || ""]));
  const clarificationComplete = session.clarification.questions.length > 0 && session.clarification.questions.every(
    (question) => effectiveAnswers[question.id],
  );
  const canStartLinkedRun = Boolean(session.remote) && ["completed", "cancelled", "failed", "budget_exhausted"].includes(session.status);

  const submitAnswers = (event: FormEvent) => {
    event.preventDefault();
    if (clarificationComplete) submitClarifications(session.id, effectiveAnswers);
  };

  const submitFollowUp = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = followUp.trim();
    if (!trimmed) return;
    sendMessage(session.id, trimmed);
    setFollowUp("");
  };

  return (
    <main className="agent-chat-page">
      <header className="agent-chat-header">
        <div className="agent-chat-breadcrumbs">
          <Link to="/agent"><WorkbenchIcon name="chevron-left" /> Agent runs</Link>
          <span>/</span>
          <h1>{session.title}</h1>
        </div>
        <div className="agent-chat-actions">
          <span aria-atomic="true" className={`status-badge status-${session.status}`} role="status">{AGENT_STATUS_LABELS[session.status]}</span>
          <Link className="secondary-button" to="/agent"><WorkbenchIcon name="plus" />New run</Link>
        </div>
      </header>

      <div className="agent-chat-layout">
        <section className="agent-conversation" aria-label="Agent conversation">
          <div className="agent-conversation-heading"><div><p className="panel-kicker">AGENT CHAT</p><h2>Research conversation</h2></div><span>Typed autonomous route</span></div>
          <div className="agent-messages">
            {error && <p role="alert">{error}</p>}
            {session.remote && ["requested", "queued", "running"].includes(session.status) && !session.clarification.questions.length && !session.result &&
              <p aria-live="polite" role="status">Preparing clarification…</p>}
            <div aria-label="Agent message log" aria-live="polite" aria-relevant="additions text" className="agent-message-log" role="log">
              {session.messages.map((item) => (
                <article className={`agent-message agent-message-${item.role}`} key={item.id}>
                  <small>{item.label ?? (item.role === "user" ? "You" : "Agent")}</small>
                  <p>{item.body}</p>
                </article>
              ))}
            </div>

            {!session.clarification.submitted && (
              <form className="agent-clarification-card" onSubmit={submitAnswers}>
                <div>
                  <p className="panel-kicker">CLARIFICATION</p>
                  <h2>Confirm the research frame</h2>
                </div>
                {session.clarification.questions.map((question) => (
                  <label key={question.id}>
                    <span>{question.prompt}</span>
                    <select
                      aria-label={question.prompt}
                      value={answers[question.id] ?? ""}
                      onChange={(event) =>
                        setAnswers({ ...answers, [question.id]: event.target.value })
                      }
                    >
                      <option value="">Select one…</option>
                      {question.options.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </select>
                    <input aria-label={`Custom answer: ${question.prompt}`} placeholder="Or enter your own answer…"
                      value={customAnswers[question.id] ?? ""} onChange={event => setCustomAnswers({ ...customAnswers, [question.id]: event.target.value })} />
                  </label>
                ))}
                <button
                  className="primary-button"
                  disabled={pending[session.id] || !clarificationComplete}
                  type="submit"
                >
                  {pending[session.id] ? "Submitting…" : "Run research"}
                </button>
              </form>
            )}

            {session.result && <AgentResultView session={session} />}
            <AgentRunControls session={session} />
          </div>

          <form className="agent-follow-up" onSubmit={submitFollowUp}>
            <label className="sr-only" htmlFor="agent-follow-up">Follow-up request</label>
            <textarea
              disabled={Boolean(pending[session.id]) || (!session.result && !canStartLinkedRun)}
              id="agent-follow-up"
              onChange={(event) => setFollowUp(event.target.value)}
              placeholder="Ask a follow-up after the initial run…"
              rows={2}
              value={followUp}
            />
            <button
              className="composer-send"
              disabled={Boolean(pending[session.id]) || !session.result || !followUp.trim()}
              type="submit"
            >
              Send
            </button>
            {canStartLinkedRun &&
              <button className="secondary-button" disabled={pending[session.id] || !followUp.trim()} type="button"
                onClick={() => void execute(session.id, "new_run", { request: followUp.trim() })}>Start linked research run</button>}
          </form>
        </section>

        <AgentProgressPanel session={session} />
      </div>
    </main>
  );
}
