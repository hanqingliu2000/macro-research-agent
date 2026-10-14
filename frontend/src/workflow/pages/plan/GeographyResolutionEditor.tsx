import type { GeographyResolution, WorkflowSession } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";
import { useWorkflow } from "../../state/WorkflowContextCore";

function Resolution({
  disabled,
  resolution,
  sessionId,
}: {
  disabled: boolean;
  resolution: GeographyResolution;
  sessionId: string;
}) {
  const { execute } = useWorkflow();
  return (
    <article className={`geography-card ${resolution.confirmed ? "confirmed" : "unresolved"}`}>
      <div className="geography-heading">
        <div><strong>{resolution.label}</strong><span>{resolution.kind.replace("_", " ")}</span></div>
        <span>{resolution.confirmed ? "Confirmed" : "Review required"}</span>
      </div>
      <p>{resolution.memberCodes.join(" · ")}</p>
      <dl>
        <div><dt>Membership</dt><dd>{resolution.membershipSource}</dd></div>
        <div><dt>Effective</dt><dd>{resolution.effectivePeriod}</dd></div>
        {resolution.aggregation && (
          <>
            <div><dt>Aggregation</dt><dd>{resolution.aggregation.method.replace("_", " ")}</dd></div>
            <div><dt>Weights</dt><dd>{resolution.aggregation.weightIndicator} · {resolution.aggregation.weightSource}</dd></div>
            <div><dt>Coverage</dt><dd>{Math.round(resolution.aggregation.coverageThreshold * 100)}%</dd></div>
          </>
        )}
      </dl>
      {!resolution.confirmed && (
        <button className="secondary-button" disabled={disabled} onClick={() => execute(sessionId, { type: "confirm_geography", resolutionId: resolution.id })} type="button">
          Confirm members and aggregation
        </button>
      )}
    </article>
  );
}

export function GeographyResolutionEditor({
  disabled,
  session,
}: {
  disabled: boolean;
  session: WorkflowSession;
}) {
  if (!session.currentPlan) return null;
  return (
    <section className="plan-editor-section">
      <SectionHeading eyebrow="GEOGRAPHY RESOLUTION" level={3} title="" />
      <div className="geography-list">
        {session.currentPlan.geographyResolutions.map((resolution) => <Resolution disabled={disabled} key={resolution.id} resolution={resolution} sessionId={session.id} />)}
      </div>
      {disabled && <p className="plan-warning">Save the pending manual Plan edits before confirming a geography resolution.</p>}
    </section>
  );
}
