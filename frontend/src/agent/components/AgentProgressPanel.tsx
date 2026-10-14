import { WorkbenchIcon } from "../../ui/components/WorkbenchIcon";
import type { AgentSession } from "../domain/types";

export function AgentProgressPanel({ session }: { session: AgentSession }) {
  return (
    <aside aria-label="Agent research progress" className="agent-progress-panel">
      <div className="agent-panel-heading">
        <div><p className="panel-kicker">RESEARCH OUTLINE</p><h2>Autonomous route</h2></div>
        <span>{session.steps.filter((step) => step.status === "completed").length}/{session.steps.length}</span>
      </div>
      <ol>
        {session.steps.map((step, index) => (
          <li
            aria-current={step.status === "in_progress" ? "step" : undefined}
            className={`agent-progress-${step.status}`}
            key={step.id}
          >
            <span aria-hidden="true">
              {step.status === "completed" ? <WorkbenchIcon name="check" /> : index + 1}
            </span>
            <div>
              <strong>{step.label}</strong>
              <small>{step.status.replace("_", " ")}</small>
              <p>{step.summary}</p>
            </div>
          </li>
        ))}
      </ol>
      {session.attachments.length > 0 && (
        <section className="agent-attached-panel" aria-label="Run attachments">
          <p className="panel-kicker">ATTACHMENTS</p>
          {session.attachments.map((attachment) => (
            <span key={attachment.id}><WorkbenchIcon name="paperclip" />{attachment.name}</span>
          ))}
        </section>
      )}
    </aside>
  );
}
