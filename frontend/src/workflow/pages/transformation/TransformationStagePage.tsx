import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { CheckpointBar } from "../../components/CheckpointBar";
import { ImpactDialog } from "../../components/ImpactDialog";
import { StaleBanner } from "../../components/StaleBanner";
import { AssistantProposalPanel, AssistantRequestBox } from "../../components/AssistantProposalPanel";
import { useWorkflowSession } from "../../components/useWorkflowSession";
import type { WorkflowCommand } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { ModelJobList } from "./ModelJobList";
import { OperationCatalog } from "./OperationCatalog";
import { ParameterEditor } from "./ParameterEditor";
import { PipelineList } from "./PipelineList";
import { PipelinePreview } from "./PipelinePreview";
import { TargetSelector } from "./TargetSelector";

export function TransformationStagePage() {
  const session = useWorkflowSession();
  const { execute } = useWorkflow();
  const navigate = useNavigate();
  const [pendingCommand, setPendingCommand] = useState<WorkflowCommand>();
  const selected = session.pipeline.operations.find((operation) => operation.id === session.pipeline.selectedOperationId);
  const stale = session.stageHealth.transformation === "stale";
  const analysisCompleted = session.pipeline.runStatus === "completed";
  const workflowCompleted = session.status === "completed";
  const revisionRequired = analysisCompleted && session.activeStage === "output" && !workflowCompleted;
  const editingDisabled = stale || analysisCompleted;
  const hasPriorOutput = session.output.artifacts.length > 0 || session.output.artifactHistory.length > 0;
  const revisingPriorRun = session.pipeline.runStatus === "editing" && hasPriorOutput;
  const outputWouldBeInvalidated =
    session.reachedStages.includes("output") && session.stageHealth.output !== "stale";
  const requestPipelineChange = (command: WorkflowCommand) => {
    if (outputWouldBeInvalidated) setPendingCommand(command);
    else execute(session.id, command);
  };
  return (
    <>
      <StaleBanner session={session} stage="transformation" />
      <div className="workflow-stage-layout transformation-stage-layout">
        <div className="pipeline-control-column">
          {revisionRequired && (
            <section aria-labelledby="analysis-revision-title" className="pipeline-card pipeline-revision-gate">
              <p className="panel-kicker">COMPLETED ANALYSIS</p>
              <h2 id="analysis-revision-title">Review before changing the analysis</h2>
              <button className="primary-button" onClick={() => setPendingCommand({ type: "start_pipeline_revision" })} type="button">Revise analysis</button>
            </section>
          )}
          {workflowCompleted && analysisCompleted && (
            <section aria-labelledby="completed-analysis-title" className="pipeline-card pipeline-revision-gate">
              <p className="panel-kicker">COMPLETED RESEARCH</p>
              <h2 id="completed-analysis-title">The finalized analysis is read-only</h2>
              <p>Continue in a new session to revise this frozen result.</p>
              <Link className="secondary-button" to={`/sessions/${session.id}/output`}>Open final Output</Link>
            </section>
          )}
          {revisingPriorRun && session.stageHealth.output === "stale" && (
            <p className="pipeline-revision-status" role="status">
              Analysis revision in progress. Previous Output is stale and preserved in history; run the updated analysis to rebuild it.
            </p>
          )}
          {session.pipeline.pendingAssistantProposal ? (
            <AssistantProposalPanel
              agent={session.pipeline.pendingAssistantProposal.agent}
              disabled={editingDisabled}
              items={[
                ...session.pipeline.pendingAssistantProposal.operations.map((item) => ({
                  id: item.id,
                  label: item.operation.replaceAll("_", " "),
                  rationale: item.rationale,
                  detail: JSON.stringify({ target: item.indicators, parameters: item.parameters }),
                })),
                ...session.pipeline.pendingAssistantProposal.models.map((item) => ({
                  id: item.id,
                  label: `${item.model} model`,
                  rationale: item.rationale,
                  detail: JSON.stringify({ variables: item.variables, parameters: item.parameters }),
                })),
                ...(session.pipeline.pendingAssistantProposal.modelRemovals ?? []).map((item) => ({
                  id: item.id,
                  label: `Remove ${item.label}`,
                  rationale: item.rationale,
                  detail: `Existing model job: ${item.modelJobId}`,
                })),
              ]}
              onApply={(acceptedItemIds) => requestPipelineChange({ type: "apply_analysis_assistance", acceptedItemIds })}
              onReject={() => execute(session.id, { type: "reject_analysis_assistance" })}
              summary={session.pipeline.pendingAssistantProposal.summary}
              target={session.pipeline.pendingAssistantProposal.targetStateHash}
              title="Analysis proposal"
            />
          ) : (
            <AssistantRequestBox
              disabled={editingDisabled}
              label="Ask Analysis AI"
              onSubmit={(request) => execute(session.id, { type: "propose_analysis_assistance", request })}
              placeholder="For example: compare year-on-year changes and add descriptive diagnostics."
            />
          )}
          <OperationCatalog disabled={editingDisabled} onAdd={(operation) => requestPipelineChange({ type: "add_pipeline_operation", operation })} />
          <PipelineList
            disabled={editingDisabled}
            onDelete={(operationId) => requestPipelineChange({ type: "delete_pipeline_operation", operationId })}
            onMove={(operationId, direction) => requestPipelineChange({ type: "move_pipeline_operation", operationId, direction })}
            onSelect={(operationId) => execute(session.id, { type: "select_pipeline_operation", operationId })}
            onToggle={(operationId) => requestPipelineChange({ type: "toggle_pipeline_operation", operationId })}
            onUndo={() => requestPipelineChange({ type: "undo_pipeline_edit" })}
            session={session}
          />
          <TargetSelector disabled={editingDisabled} operation={selected} onChange={(target) => selected && requestPipelineChange({ type: "update_pipeline_target", operationId: selected.id, target })} session={session} />
          <ParameterEditor disabled={editingDisabled} operation={selected} onChange={(parameters) => selected && requestPipelineChange({ type: "update_pipeline_parameters", operationId: selected.id, parameters })} />
          <ModelJobList disabled={editingDisabled} onAdd={(model) => requestPipelineChange({ type: "add_model_job", model })} onDelete={(modelId) => requestPipelineChange({ type: "delete_model_job", modelId })} onInputChange={(modelId, inputRef) => requestPipelineChange({ type: "update_model_input", modelId, inputRef })} onSpecificationChange={(modelId, specification) => requestPipelineChange({ type: "update_model_specification", modelId, ...specification })} session={session} />
          <CheckpointBar actionLabel={analysisCompleted ? "Analysis completed" : revisingPriorRun ? "Run updated analysis" : "Run analysis"} detail={analysisCompleted ? `Completed ${session.pipeline.operations.filter((item) => item.enabled).length} registered operations and ${session.pipeline.models.length} model jobs.` : `Run ${session.pipeline.operations.filter((item) => item.enabled).length} registered operations and ${session.pipeline.models.length} model jobs.`} disabled={analysisCompleted || stale || Boolean(session.pipeline.lastValidationError) || !session.data.approvedSnapshotId || (!session.pipeline.operations.some((item) => item.enabled) && !session.pipeline.models.length)} onAction={async () => {
            const updated = await execute(session.id, { type: "run_pipeline" });
            if (updated?.activeStage === "output") navigate(`/sessions/${session.id}/output`);
          }} title="Execution checkpoint" />
        </div>
        <PipelinePreview session={session} />
      </div>
      {pendingCommand && (
        <ImpactDialog
          onCancel={() => setPendingCommand(undefined)}
          onConfirm={() => {
            execute(session.id, pendingCommand);
            setPendingCommand(undefined);
          }}
          stages={["output"]}
          confirmLabel={pendingCommand.type === "start_pipeline_revision" ? "Begin revision" : "Confirm change"}
          title={pendingCommand.type === "start_pipeline_revision" ? "Revise the completed analysis?" : "Change the analytical pipeline?"}
        >
          {pendingCommand.type === "start_pipeline_revision" && (
            <p>You can edit the pipeline after this confirmation. The current Output will remain available as stale history until you run the revised analysis.</p>
          )}
        </ImpactDialog>
      )}
    </>
  );
}
