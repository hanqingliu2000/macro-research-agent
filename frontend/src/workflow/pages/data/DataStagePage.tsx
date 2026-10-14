import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { CheckpointBar } from "../../components/CheckpointBar";
import { ImpactDialog } from "../../components/ImpactDialog";
import { DATA_PREVIEW_PAGE_SIZE, PreviewTable } from "../../components/PreviewTable";
import { StaleBanner } from "../../components/StaleBanner";
import { AssistantProposalPanel, AssistantRequestBox } from "../../components/AssistantProposalPanel";
import { useWorkflowSession } from "../../components/useWorkflowSession";
import type { DataOperationKind, WorkflowCommand, WorkflowStage } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { OperationHistory } from "./OperationHistory";
import { DataMergeReview } from "./DataMergeReview";
import { QuickCleanToolbar } from "./QuickCleanToolbar";
import { RoundTripExport } from "./RoundTripExport";
import { SchemaMappingWizard } from "./SchemaMappingWizard";
import { SourceRunPanel } from "./SourceRunPanel";
import { SourceSchemaMapping } from "./SourceSchemaMapping";

export function DataStagePage() {
  const session = useWorkflowSession();
  const { execute, previewData } = useWorkflow();
  const navigate = useNavigate();
  const [pendingCommand, setPendingCommand] = useState<WorkflowCommand>();
  const active = session.data.snapshots.find((snapshot) => snapshot.id === session.data.activeSnapshotId);
  const [previewOffset, setPreviewOffset] = useState(0);
  const [previewRows, setPreviewRows] = useState(
    active?.rows.slice(0, DATA_PREVIEW_PAGE_SIZE) ?? [],
  );
  const [previewTotal, setPreviewTotal] = useState(session.data.quality.observations);
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewLimit = DATA_PREVIEW_PAGE_SIZE;
  const stale = session.stageHealth.data === "stale";
  const downstream: WorkflowStage[] = ["transformation", "output"].filter(
    (stage) =>
      session.reachedStages.includes(stage as WorkflowStage) &&
      session.stageHealth[stage as WorkflowStage] !== "stale",
  ) as WorkflowStage[];

  const requestDataChange = (command: WorkflowCommand) => {
    if (downstream.length) setPendingCommand(command);
    else execute(session.id, command);
  };

  useEffect(() => {
    if (!active) return;
    let current = true;
    setPreviewLoading(true);
    setPreviewRows(previewOffset === 0 ? active.rows.slice(0, previewLimit) : []);
    void previewData(session.id, previewOffset, previewLimit).then((page) => {
      if (!current || page.snapshot_id !== active.id) return;
      setPreviewRows(page.rows);
      setPreviewTotal(page.total_rows);
    }).catch(() => undefined).finally(() => {
      if (current) setPreviewLoading(false);
    });
    return () => { current = false; };
  }, [active, previewData, previewOffset, session.id]);

  useEffect(() => {
    setPreviewOffset(0);
    setPreviewRows(active?.rows.slice(0, previewLimit) ?? []);
    setPreviewTotal(session.data.quality.observations);
  }, [active?.id, session.data.quality.observations]);

  if (!active) {
    return (
      <div className="workflow-stage-layout data-stage-layout">
        <div className="data-control-column">
          <SourceRunPanel session={session} />
          {session.data.pendingAssistantProposal ? (
            <AssistantProposalPanel
              disabled={stale}
              agent={session.data.pendingAssistantProposal.agent}
              diagnostics={session.data.pendingAssistantProposal.diagnostics}
              items={(session.data.pendingAssistantProposal.sourceMappings ?? []).map((item) => ({
                id: item.id,
                label: `${item.sourceColumn} → ${item.role}`,
                rationale: item.rationale,
                detail: "Controlled schema role mapping",
              }))}
              onApply={(acceptedItemIds) => execute(session.id, { type: "apply_data_assistance", acceptedItemIds })}
              onReject={() => execute(session.id, { type: "reject_data_assistance" })}
              summary={session.data.pendingAssistantProposal.summary}
              target={session.data.pendingAssistantProposal.targetSnapshotHash}
              title="Source mapping proposal"
            />
          ) : (
            <AssistantRequestBox
              disabled={stale}
              label="Ask Data AI"
              onSubmit={(request) => execute(session.id, { type: "propose_data_assistance", request })}
              placeholder="For example: map this local file to the canonical research schema."
            />
          )}
          <SourceSchemaMapping session={session} />
        </div>
        <aside className="data-preview-column">
          <p className="workspace-notice">Map the uploaded columns to load the active dataset.</p>
        </aside>
      </div>
    );
  }

  return (
    <>
      <StaleBanner session={session} stage="data" />
      <div className="workflow-stage-layout data-stage-layout">
        <div className="data-control-column">
          <SourceRunPanel session={session} />
          <DataMergeReview
            disabled={stale}
            onApprove={() => execute(session.id, { type: "approve_data_merge" })}
            session={session}
          />
          {session.data.pendingAssistantProposal ? (
            <AssistantProposalPanel
              disabled={stale}
              agent={session.data.pendingAssistantProposal.agent}
              diagnostics={session.data.pendingAssistantProposal.diagnostics}
              items={session.data.pendingAssistantProposal.operations.map((item) => ({
                id: item.id,
                label: item.operation.replaceAll("_", " "),
                rationale: item.rationale,
                detail: JSON.stringify(item.parameters),
              }))}
              onApply={(acceptedItemIds) => requestDataChange({ type: "apply_data_assistance", acceptedItemIds })}
              onReject={() => execute(session.id, { type: "reject_data_assistance" })}
              summary={session.data.pendingAssistantProposal.summary}
              target={session.data.pendingAssistantProposal.targetSnapshotHash}
              title="Data preparation proposal"
            />
          ) : (
            <AssistantRequestBox
              disabled={stale}
              label="Ask Data AI"
              onSubmit={(request) => execute(session.id, { type: "propose_data_assistance", request })}
              placeholder="For example: review missing values and prepare a reproducible cleaning sequence."
            />
          )}
          <OperationHistory session={session} />
          <RoundTripExport disabled={stale} session={session} />
          <SchemaMappingWizard disabled={stale} onCommit={() => requestDataChange({ type: "commit_round_trip" })} session={session} />
        </div>
        <aside className="data-preview-column">
          <section className="quality-strip">
            <div><strong>{session.data.quality.observations}</strong><span>Rows</span></div><div><strong>{session.data.quality.missingShare}%</strong><span>Missing observations</span></div><div><strong>{session.data.quality.duplicateKeys}</strong><span>Duplicate keys</span></div>
          </section>
          <PreviewTable
            caption={active.label}
            columns={session.data.columns}
            loading={previewLoading}
            rowOffset={previewOffset}
            rows={previewRows}
          />
          <div className="data-preview-pagination" aria-label="Data preview pagination">
            <button
              disabled={previewLoading || previewOffset === 0}
              onClick={() => setPreviewOffset((offset) => Math.max(0, offset - previewLimit))}
              type="button"
            >Previous</button>
            <span>
              {previewLoading
                ? "Loading…"
                : `${previewTotal === 0 ? "0" : `${previewOffset + 1}–${previewOffset + previewRows.length}`} of ${previewTotal}`}
            </span>
            <button
              disabled={previewLoading || previewOffset + previewLimit >= previewTotal}
              onClick={() => setPreviewOffset((offset) => offset + previewLimit)}
              type="button"
            >Next</button>
          </div>
          <QuickCleanToolbar
            disabled={stale}
            onApply={(operation: DataOperationKind) => requestDataChange({ type: "apply_data_operation", operation })}
            onUndo={() => requestDataChange({ type: "undo_data_operation" })}
            session={session}
          />
          <CheckpointBar actionLabel="Next: configure pipeline" compact disabled={stale} onAction={async () => {
            const updated = await execute(session.id, { type: "data_next" });
            if (updated?.activeStage === "transformation") navigate(`/sessions/${session.id}/transformation`);
          }} />
        </aside>
      </div>
      {pendingCommand && (
        <ImpactDialog
          onCancel={() => setPendingCommand(undefined)}
          onConfirm={() => { execute(session.id, pendingCommand); setPendingCommand(undefined); }}
          stages={downstream}
          title="Change the active dataset?"
        />
      )}
    </>
  );
}
