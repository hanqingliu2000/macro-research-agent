import { SectionHeading } from "../../components/SectionHeading";
import type { OutputReviewFinding, WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";

function shortHash(value: string) {
  return value.replace("sha256:", "").slice(0, 8);
}

type StoredPreflightFinding = OutputReviewFinding & {
  artifact_ids?: string[];
  finding_id?: string;
  rule_id?: string;
};

function preflightFindingDetails(finding: OutputReviewFinding, index: number) {
  const stored = finding as StoredPreflightFinding;
  const artifactIds = finding.artifactIds ?? stored.artifact_ids ?? [];
  const ruleId = finding.ruleId ?? stored.rule_id ?? "OUTPUT-PREFLIGHT";
  return {
    artifactIds,
    key: finding.id ?? stored.finding_id ?? `${ruleId}-${index}`,
    ruleId,
  };
}

function findingIdentity(finding: OutputReviewFinding) {
  const stored = finding as StoredPreflightFinding;
  const artifacts = finding.artifactIds ?? stored.artifact_ids ?? [];
  return `${[...artifacts].sort().join(",")}|${finding.ruleId ?? stored.rule_id}|${finding.message}`;
}

export function OutputReviewPanel({
  session,
  disabled,
}: {
  session: WorkflowSession;
  disabled: boolean;
}) {
  const { execute, pending } = useWorkflow();
  const selectedArtifactIds = new Set(
    session.output.artifacts
      .filter((artifact) => artifact.exportSelected)
      .map((artifact) => artifact.id),
  );
  const preflight = (session.output.preflightFindings ?? []).filter((finding, index) => {
    const artifactIds = preflightFindingDetails(finding, index).artifactIds;
    return artifactIds.length === 0 || artifactIds.some((id) => selectedArtifactIds.has(id));
  });
  const report = session.output.reviewReport;
  const preflightIdentities = new Set(preflight.map(findingIdentity));
  const reportFindings = report?.findings.filter(
    (finding, index, findings) =>
      !preflightIdentities.has(findingIdentity(finding))
      && findings.findIndex((candidate) => findingIdentity(candidate) === findingIdentity(finding)) === index,
  ) ?? [];
  const failed = preflight.filter((item) => item.severity === "fail").length;
  const maximum = 3;
  const iteration = session.output.reviewIteration ?? 0;
  const limitReached = iteration >= maximum;
  const reviews = [
    ...(session.output.reviewHistory ?? []),
    ...(report ? [report] : []),
  ].filter((item, index, items) => items.findIndex((candidate) => candidate.id === item.id) === index);
  const revisions = session.output.revisionHistory ?? [];
  const artifactNames = new Map(
    session.output.artifacts.map((artifact) => [artifact.id, artifact.name]),
  );
  const legacyArtifactSets = session.output.artifactHistory.slice(
    0,
    Math.max(session.output.artifactHistory.length - revisions.length, 0),
  );
  const events = [
    ...reviews.map((item) => ({
      id: `review-${item.id}`,
      at: item.createdAt,
      kind: "review" as const,
      review: item,
    })),
    ...revisions.map((item) => ({
      id: `revision-${item.id}-${item.revision}`,
      at: item.appliedAt,
      kind: "revision" as const,
      revision: item,
    })),
  ].sort((left, right) => left.at.localeCompare(right.at));
  return (
    <section className="output-review-card" aria-label="Output review">
      <SectionHeading
        eyebrow="REVIEW AI"
        meta={
          <span className={`review-status review-status-${report?.status ?? "pending"}`}>
            {report?.status ?? "not run"}
          </span>
        }
        title="Artifact quality review"
      />
      <div className="preflight-summary" role="status">
        <strong>Deterministic preflight</strong>
        <span>{failed ? `${failed} publication blocker(s)` : "Passed"}</span>
      </div>
      <div className="chart-self-checks" aria-label="Chart author self-checks">
        <strong>Chart author self-checks</strong>
        <p>Before every Review AI handoff: two DeepSeek checks of data/specification and final SVG structure. These do not consume the three review rounds or replace visual review.</p>
        {(session.output.chartSelfChecks ?? []).map((check) => (
          <details key={check.id} open={check === session.output.chartSelfChecks?.at(-1)}>
            <summary>{check.provider} · {check.model} · {check.status} · {shortHash(check.artifactSetHash)}</summary>
            {check.rounds.map((round) => (
              <div key={round.round}>
                <strong>Self-check {round.round}/2: {round.status}</strong>
                {round.issues.map((issue, index) => <p key={index}>{issue}</p>)}
              </div>
            ))}
            {check.status === "fail" && <p>Not handed to Review AI. Correct the chart or retry; Finish remains locked.</p>}
          </details>
        ))}
      </div>
      {report?.visualRubricVersion && (
        <p className="preflight-review-note">
          Visual standard: {report.visualRubricVersion} · {report.visualRubricStatus}
        </p>
      )}
      {failed > 0 && (
        <p className="preflight-review-note">
          You can still run Output review for diagnosis and correction guidance. Final publication remains locked until these findings are resolved.
        </p>
      )}
      <div className="output-review-progress" role="status" aria-live="polite">
        <div>
          <strong>Review and revision progress</strong>
          <span>{iteration}/{maximum} review rounds</span>
        </div>
        <progress aria-label={`${iteration} of ${maximum} Output review rounds used`} max={maximum} value={iteration} />
        <small>
          {limitReached
            ? "Maximum reached. Finish with the current reviewed version or revise upstream."
            : `${maximum - iteration} review round(s) remain. Applying a correction automatically uses the next round.`}
        </small>
      </div>
      {session.output.reportSemanticStatus !== "not_applicable" && (
        <div className="preflight-summary" role="status">
          <strong>Research Report semantic review</strong>
          <span>{session.output.reportSemanticStatus ?? "pending"}</span>
        </div>
      )}
      {preflight.length > 0 && (
        <ul className="review-finding-list">
          {preflight.map((finding, index) => {
            const details = preflightFindingDetails(finding, index);
            return (
              <li className={`review-finding review-finding-${finding.severity}`} key={details.key}>
                <strong>{details.ruleId}</strong>
                <span>{finding.message}</span>
                {details.artifactIds.length > 0 && (
                  <small>
                    {details.artifactIds
                      .map((artifactId) => artifactNames.get(artifactId) ?? artifactId)
                      .join(", ")}
                  </small>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {report && (
        <div className="review-report-summary">
          <p>
            Reviewed {report.reviewedArtifactIds.length} artifact(s) and {report.inspectedRowCount} underlying row(s).
          </p>
          <p className="review-provider-note">
            Iteration {report.iteration}/{session.output.maxReviewIterations ?? 3}
          </p>
          {reportFindings.length === 0 ? (
            <p className="review-pass-message">No structural, visual or semantic findings.</p>
          ) : (
            <ul className="review-finding-list">
              {reportFindings.map((finding, index) => (
                <li className={`review-finding review-finding-${finding.severity}`} key={`${findingIdentity(finding)}-${index}`}>
                  <strong>{finding.ruleId}</strong>
                  <span>{finding.message}</span>
                  {finding.requiresUpstreamStage && (
                    <small>Return to {finding.upstreamStage ?? "an upstream stage"}; rewriting the report cannot resolve this.</small>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {events.length + legacyArtifactSets.length > 0 && (
        <details className="output-review-history">
          <summary>Version and review history <span>{events.length + legacyArtifactSets.length}</span></summary>
          <ol>
            {legacyArtifactSets.map((artifacts, index) => (
              <li key={`legacy-artifact-set-${index + 1}`}>
                <div><strong>Earlier artifact set {index + 1}</strong><span>{artifacts.length} artifact(s)</span></div>
                <ul>
                  {artifacts.map((artifact) => (
                    <li key={artifact.id}>{artifact.name} · {artifact.format.toUpperCase()} · {shortHash(artifact.hash)}</li>
                  ))}
                </ul>
                <p>Created before detailed revision-event tracking was available.</p>
              </li>
            ))}
            {events.map((event) => (
              <li key={event.id}>
                {event.kind === "review" ? (
                  <>
                    <div><strong>Review {event.review.iteration}</strong><span className={`review-status review-status-${event.review.status}`}>{event.review.status}</span></div>
                    <p>{event.review.findings.length} finding(s) · report {event.review.semanticReportStatus ?? "not applicable"} · set {shortHash(event.review.targetArtifactSetHash)}</p>
                    <time dateTime={event.review.createdAt}>{new Date(event.review.createdAt).toLocaleString()}</time>
                  </>
                ) : (
                  <>
                    <div><strong>Revision {event.revision.revision}</strong><span>{event.revision.artifacts.length} artifact(s)</span></div>
                    <p>{event.revision.request}</p>
                    <ul>
                      {event.revision.artifacts.map((artifact) => (
                        <li key={`${event.revision.id}-${artifact.artifactId}`}>
                          {artifact.name} · {artifact.format.toUpperCase()} · {shortHash(artifact.previousHash)} → {shortHash(artifact.hash)}
                        </li>
                      ))}
                    </ul>
                    <time dateTime={event.revision.appliedAt}>{new Date(event.revision.appliedAt).toLocaleString()}</time>
                  </>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
      <button
        className="secondary-button output-review-action"
        disabled={disabled || pending || limitReached}
        onClick={() => void execute(session.id, { type: "request_output_review" })}
        type="button"
      >
        {pending ? "Reviewing…" : limitReached ? "Review limit reached" : report ? "Run review again" : "Run output review"}
      </button>
    </section>
  );
}
