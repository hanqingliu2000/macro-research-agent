import { useEffect, useMemo, useState } from "react";

import { PreviewTable } from "../../components/PreviewTable";
import type { DatasetColumn, DatasetRow, WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { ModelResultPreview } from "./ModelResultPreview";
import { CodeArtifactPreview } from "./CodeArtifactPreview";

export function PipelinePreview({ session }: { session: WorkflowSession }) {
  const { previewPipeline } = useWorkflow();
  const selected = session.pipeline.operations.find(
    (operation) => operation.id === session.pipeline.selectedOperationId,
  );
  const active = session.data.snapshots.find(
    (snapshot) => snapshot.id === session.data.activeSnapshotId,
  );
  const [rows, setRows] = useState<DatasetRow[]>(active?.rows ?? []);
  const [columnIds, setColumnIds] = useState<string[]>(
    session.data.columns.map((column) => column.id),
  );
  const lineage = selected
    ? session.pipeline.bundle?.operationLineage?.find((item) => item.operationId === selected.id)
    : undefined;

  useEffect(() => {
    if (!session.data.approvedSnapshotId) return;
    let current = true;
    void previewPipeline(session.id, selected?.id, 0, 100)
      .then((preview) => {
        if (!current) return;
        setRows(preview.rows);
        setColumnIds(preview.columns);
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [previewPipeline, selected?.id, session.data.approvedSnapshotId, session.id, session.pipeline]);

  const columns = useMemo<DatasetColumn[]>(
    () =>
      columnIds.map((id) => {
        const known = session.data.columns.find((column) => column.id === id);
        return known ?? {
          id,
          label: id,
          dataType: id === "value" || id === "aggregation_coverage" ? "number" : "string",
          role: "attribute",
          required: false,
          key: false,
        };
      }),
    [columnIds, session.data.columns],
  );

  if (!active) return null;
  return (
    <div className="pipeline-preview-column">
      <PreviewTable
        caption={selected ? `After: ${selected.label}` : active.label}
        columns={columns}
        rows={rows}
      />
      <section className="lineage-card">
        <p className="panel-kicker">LINEAGE</p>
        <h3>Selected operation</h3>
        <dl>
          <div><dt>Input</dt><dd>{lineage?.inputSnapshotId ?? selected?.inputRef ?? active.id}</dd></div>
          <div><dt>Output</dt><dd>{lineage?.outputSnapshotId ?? selected?.outputRef ?? "No operation selected"}</dd></div>
          <div><dt>Specification</dt><dd>{lineage?.specificationHash ?? "Preview only"}</dd></div>
          <div><dt>Rows</dt><dd>{lineage ? `${lineage.inputRows} → ${lineage.outputRows}` : "—"}</dd></div>
        </dl>
      </section>
      <ModelResultPreview results={session.pipeline.modelResults ?? []} />
      <CodeArtifactPreview artifacts={session.pipeline.codeArtifacts ?? []} sessionId={session.id} />
    </div>
  );
}
