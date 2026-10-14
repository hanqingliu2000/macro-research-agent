import type { WorkflowSession } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";

export function SourceRunPanel({ session }: { session: WorkflowSession }) {
  return (
    <section className="data-control-card">
      <SectionHeading eyebrow="CONTROLLED ACQUISITION" meta={<span>{session.data.sourceRuns.length} runs</span>} title="Sources and queries" />
      <div className="source-run-list">
        {session.data.sourceRuns.map((run) => (
          <article key={run.id}>
            <span className={`source-run-status source-run-${run.status}`} />
            <div>
              <strong>{run.provider} · {run.dataset}</strong>
              <p>{run.query}</p>
              <small>{run.connectorId} · {run.retrievedAt ?? "Not retrieved"}</small>
              {run.periodResolution === "query_upper_bound" && (
                <small>
                  Requested “{run.requestedPeriodEnd}”; queried through {run.resolvedPeriodEnd}.
                  Returned coverage remains authoritative.
                </small>
              )}
              {run.periodResolution === "calendar_year_mapping" && (
                <small>
                  Requested {run.requestedPeriodStart}–{run.requestedPeriodEnd}; queried
                  {" "}{run.resolvedPeriodStart}–{run.resolvedPeriodEnd}. Fiscal years map to
                  their ending calendar year for this source.
                </small>
              )}
            </div>
            <span>{run.status}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
