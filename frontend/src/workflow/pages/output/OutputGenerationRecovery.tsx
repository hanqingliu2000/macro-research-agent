import type { WorkflowSession } from "../../domain/types";

export function OutputGenerationRecovery({
  onRetry,
  pending,
  session,
}: {
  onRetry(): void;
  pending: boolean;
  session: WorkflowSession;
}) {
  const generation = session.pipeline.outputGeneration;
  if (generation?.status !== "failed") return null;
  const error = generation.error;

  return (
    <section
      aria-labelledby="output-generation-error-title"
      aria-live="assertive"
      className="output-generation-recovery"
      role="alert"
    >
      <p className="panel-kicker">OUTPUT GENERATION</p>
      <h2 id="output-generation-error-title">Analysis is safe; Output needs attention</h2>
      <p>
        The approved data, analytical bundle and model results were preserved. Retrying regenerates
        Output only—it does not rerun the analysis.
      </p>
      {error && (
        <div className="output-generation-error-summary">
          <strong>{error.code.replaceAll("_", " ")}</strong>
          <span>{error.message}</span>
        </div>
      )}
      {error?.issues.length ? (
        <details className="output-generation-error-details">
          <summary>Contract details ({error.issues.length})</summary>
          <ul>
            {error.issues.map((issue, index) => (
              <li key={`${issue.attempt}-${issue.path}-${issue.code}-${index}`}>
                <code>{issue.path}</code>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <div className="output-generation-recovery-actions">
        <button
          className="primary-button"
          disabled={pending || !generation.retryable}
          onClick={onRetry}
          type="button"
        >
          {pending ? "Retrying Output generation…" : "Retry Output generation"}
        </button>
        {!generation.retryable && (
          <span>This error requires revising the upstream analysis.</span>
        )}
      </div>
    </section>
  );
}
