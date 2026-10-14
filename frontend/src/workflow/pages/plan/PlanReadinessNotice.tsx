import { normalizePlanGuidance } from "../../domain/planGuidance";

export function PlanReadinessNotice({
  unresolvedItems,
  warnings,
}: {
  unresolvedItems: string[];
  warnings: string[];
}) {
  const { blockers, cautions } = normalizePlanGuidance(unresolvedItems, warnings);
  if (blockers.length === 0 && cautions.length === 0) return null;

  const hasBlockers = blockers.length > 0;
  return (
    <section
      aria-label="Plan readiness"
      className="plan-readiness plan-warning"
      role={hasBlockers ? "alert" : "status"}
    >
      <strong>Before acquiring data</strong>
      {hasBlockers && (
        <div>
          <span>Resolve these blockers</span>
          <ul>{blockers.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </div>
      )}
      {cautions.length > 0 && (
        <div>
          <span>Review these cautions</span>
          <ul>{cautions.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </div>
      )}
    </section>
  );
}
