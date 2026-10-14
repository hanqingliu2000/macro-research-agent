import { useState } from "react";

import { ImpactDialog } from "../../components/ImpactDialog";
import type { WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";

export function ExportMenu({ session, disabled, onFinish, onContinue }: { session: WorkflowSession; disabled: boolean; onFinish(acceptWarnings: boolean): void; onContinue(): void }) {
  const { execute, sessionArchiveDownloadUrl } = useWorkflow();
  const [acceptWarnings, setAcceptWarnings] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const selected = session.output.artifacts.filter((artifact) => artifact.exportSelected);
  const review = session.output.reviewReport;
  const limitations = session.output.limitations ?? [];
  const completed = session.status === "completed";
  const pendingProposal = Boolean(session.output.pendingProposal);
  const selectedReport = selected.some((artifact) => artifact.format === "report");
  const semanticBlocksFinish = selectedReport && session.output.reportSemanticStatus !== "pass";
  const reviewBlocksFinish = !review || review.status === "fail" || pendingProposal || semanticBlocksFinish;
  const warningNeedsAcknowledgement = review?.status === "warning" && !acceptWarnings;
  return (
    <section className="export-menu">
      <div><p className="panel-kicker">SELECTIVE EXPORT</p><h3>{selected.length} artifact(s) selected</h3></div>
      <div className="export-checks">
        {session.output.artifacts.map((artifact) => <label key={artifact.id}><input checked={artifact.exportSelected} disabled={disabled || artifact.status === "stale"} onChange={() => execute(session.id, { type: "toggle_artifact_export", artifactId: artifact.id })} type="checkbox" /><span>{artifact.name}</span></label>)}
      </div>
      {review?.status === "warning" && (
        <label className="review-warning-acknowledgement">
          <input checked={acceptWarnings} onChange={(event) => setAcceptWarnings(event.target.checked)} type="checkbox" />
          <span>I reviewed and acknowledge the documented warnings.</span>
        </label>
      )}
      {!completed && !review && <p className="finish-requirement">Run Output review before Finish.</p>}
      {!completed && pendingProposal && <p className="finish-requirement">Apply or reject the pending correction first.</p>}
      {!completed && semanticBlocksFinish && <p className="finish-requirement">The selected Research Report must pass semantic review before Finish.</p>}
      {!completed && <button className="primary-button" disabled={disabled || selected.length === 0 || reviewBlocksFinish || warningNeedsAcknowledgement} onClick={() => setConfirming(true)} type="button">Finish and freeze selected</button>}
      {session.output.finalizedAt && <p className="export-complete" role="status">Frozen at {session.output.finalizedAt}</p>}
      <div className="portable-session-actions">
        <a className="secondary-button" download href={sessionArchiveDownloadUrl(session.id)}>Export session</a>
        {completed && <button className="secondary-button" onClick={onContinue} type="button">Continue in a new session</button>}
      </div>
      {session.lineage && (
        <p className="portable-lineage">
          {session.lineage.relationship === "fork" ? "Continued" : "Imported"} from a verified
          session archive.
        </p>
      )}
      {confirming && (
        <ImpactDialog
          confirmLabel="Confirm and freeze"
          kicker="FINAL ARTIFACT SET"
          onCancel={() => setConfirming(false)}
          onConfirm={() => { setConfirming(false); onFinish(acceptWarnings); }}
          showImpactSummary={false}
          stages={[]}
          title="Confirm the exact package to freeze"
        >
          <p>The following reviewed artifacts will become immutable:</p>
          <ul>{selected.map((artifact) => <li key={artifact.id}>{artifact.name}</li>)}</ul>
          <p>Recorded limitations:</p>
          {limitations.length > 0 ? <ul>{limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>None recorded.</p>}
        </ImpactDialog>
      )}
    </section>
  );
}
