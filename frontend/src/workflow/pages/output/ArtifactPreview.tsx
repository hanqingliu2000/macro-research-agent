import { useEffect, useState } from "react";

import { SectionHeading } from "../../components/SectionHeading";
import type { Artifact, WorkflowSession } from "../../domain/types";
import type {
  ArtifactComparisonReport,
  OutputArtifactPreview as OutputArtifactPreviewPayload,
} from "../../services/workflowService";
import { useWorkflow } from "../../state/WorkflowContextCore";

function TablePreview({ preview }: { preview: OutputArtifactPreviewPayload }) {
  const columns = preview.columns ?? [];
  return (
    <div className="artifact-table-scroll">
      <table className="artifact-data-table">
        <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>{(preview.rows ?? []).map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function PreviewContent({ artifact, preview, imageUrl }: { artifact: Artifact; preview?: OutputArtifactPreviewPayload; imageUrl: string }) {
  if (artifact.format === "svg" || artifact.format === "png") {
    return <img alt={artifact.name} className="output-image-preview" src={preview?.content ?? imageUrl} />;
  }
  if (preview?.previewKind === "table") return <TablePreview preview={preview} />;
  if (preview?.previewKind === "text") return <pre className="artifact-code"><code>{preview.content}</code></pre>;
  if (preview?.previewKind === "workbook") {
    return <div className="workbook-preview"><p>Workbook sheets</p><ul>{preview.sheetNames?.map((name) => <li key={name}>{name}</li>)}</ul></div>;
  }
  return <p className="artifact-preview-loading">Loading artifact metadata…</p>;
}

function comparisonLabel(status: ArtifactComparisonReport["status"]) {
  if (status === "unchanged") return "No change";
  if (status === "presentation_changed") return "Presentation changed";
  if (status === "data_changed") return "Data changed";
  return "Cannot compare";
}

function ArtifactComparison({ comparison }: { comparison: ArtifactComparisonReport }) {
  const values = comparison.value_comparison;
  return (
    <section aria-label="Artifact version comparison" className="artifact-comparison">
      <div className="artifact-comparison-heading">
        <span>Compared with previous version</span>
        <strong data-status={comparison.status}>{comparisonLabel(comparison.status)}</strong>
      </div>
      <dl className="artifact-comparison-summary">
        <div><dt>Data values</dt><dd>{values.status === "unavailable" ? "Not applicable" : values.status}</dd></div>
        <div><dt>Specification</dt><dd>{comparison.specification_changes.length} fields changed</dd></div>
        <div><dt>File</dt><dd>{comparison.hash_changed ? "Hash changed" : "Identical hash"}</dd></div>
      </dl>
      {(values.added_row_count || values.removed_row_count || values.changed_sheets.length > 0) && (
        <p className="artifact-comparison-detail">
          {values.added_row_count || 0} rows added · {values.removed_row_count || 0} rows removed
          {values.changed_sheets.length ? ` · Changed sheets: ${values.changed_sheets.join(", ")}` : ""}
        </p>
      )}
      {comparison.specification_changes.length > 0 && (
        <details>
          <summary>Review specification changes</summary>
          <ul>
            {comparison.specification_changes.map((change) => (
              <li key={change.field}>
                <span>{change.field}</span>
                <code>{JSON.stringify(change.before) ?? "—"} → {JSON.stringify(change.after) ?? "—"}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function ArtifactPreview({ session, selectedArtifactId }: { session: WorkflowSession; selectedArtifactId?: string }) {
  const { compareOutputArtifacts, getOutputArtifactPreview, outputArtifactDownloadUrl } = useWorkflow();
  const artifact = session.output.artifacts.find((item) => item.id === selectedArtifactId) ?? session.output.artifacts[0];
  const baseline = artifact
    ? [...session.output.artifactHistory]
        .reverse()
        .flat()
        .find(
          (item) =>
            item.id !== artifact.id &&
            item.kind === artifact.kind &&
            item.format === artifact.format,
        )
    : undefined;
  const [preview, setPreview] = useState<OutputArtifactPreviewPayload>();
  const [comparison, setComparison] = useState<ArtifactComparisonReport>();
  const [comparisonError, setComparisonError] = useState<string>();
  useEffect(() => {
    setPreview(undefined);
    if (!artifact) return;
    void getOutputArtifactPreview(session.id, artifact.id).then(setPreview).catch(() => undefined);
  }, [artifact?.id, getOutputArtifactPreview, session.id]);
  useEffect(() => {
    let active = true;
    setComparison(undefined);
    setComparisonError(undefined);
    if (!artifact || !baseline) return () => { active = false; };
    void compareOutputArtifacts(session.id, artifact.id, baseline.id)
      .then((result) => { if (active) setComparison(result); })
      .catch(() => { if (active) setComparisonError("Version comparison is unavailable."); });
    return () => { active = false; };
  }, [artifact?.id, baseline?.id, compareOutputArtifacts, session.id]);
  if (!artifact) return <section className="artifact-preview"><p>No current artifact is available.</p></section>;
  const downloadUrl = outputArtifactDownloadUrl(session.id, artifact.id);
  return (
    <section aria-label={`${artifact.name}, ${artifact.status}`} className="artifact-preview">
      <SectionHeading className="preview-title-row" eyebrow="ARTIFACT PREVIEW" title={artifact.name} />
      <PreviewContent artifact={artifact} imageUrl={downloadUrl} preview={preview} />
      <div className="artifact-metadata"><span>Hash: {artifact.hash}</span><span>{artifact.description}</span></div>
      {baseline && !comparison && !comparisonError && <p className="artifact-comparison-loading">Comparing with the previous version…</p>}
      {comparison && <ArtifactComparison comparison={comparison} />}
      {comparisonError && <p className="artifact-comparison-error" role="status">{comparisonError}</p>}
      {session.status !== "completed" && (
        <p className="finish-requirement">This version will not be finalized until output approval.</p>
      )}
      <a className="secondary-button artifact-download" download href={downloadUrl}>Download {session.status === "completed" ? "" : "draft "}{artifact.name}</a>
    </section>
  );
}
