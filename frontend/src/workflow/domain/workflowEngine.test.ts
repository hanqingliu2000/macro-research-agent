import { describe, expect, it } from "vitest";

import {
  WorkflowConflict,
  createWorkflowSession,
  currentSnapshotHash,
  executeWorkflowCommand,
  isPlanReady,
  makeCommandEnvelope,
} from "./workflowEngine";
import type { WorkflowCommand, WorkflowSession } from "./types";

function apply(session: WorkflowSession, command: WorkflowCommand) {
  return executeWorkflowCommand(session, makeCommandEnvelope(session, command));
}

function planned() {
  let session = createWorkflowSession("Compare inflation across selected economies.");
  session = apply(session, {
    type: "submit_clarification",
    answers: {
      geography: "United States, euro area and Japan",
      period: "2015–2025, monthly",
      emphasis: "Comparative trends",
    },
  });
  return session;
}

function completed() {
  let session = planned();
  session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
  session = apply(session, { type: "plan_next" });
  session = apply(session, { type: "data_next" });
  session = apply(session, { type: "run_pipeline" });
  session = apply(session, { type: "request_output_review" });
  session = apply(session, { type: "finalize_output" });
  return session;
}

describe("four-stage Workflow engine", () => {
  it("builds a genuinely completed reviewed session for immutable-state tests", () => {
    const session = completed();

    expect(session.status).toBe("completed");
    expect(session.output.reviewReport?.status).toBe("pass");
    expect(session.output.finalizedAt).toBeDefined();
  });

  it("requires confirmed group membership before Plan Next", () => {
    let session = planned();
    expect(isPlanReady(session)).toBe(false);

    session = apply(session, { type: "plan_next" });
    expect(session.activeStage).toBe("plan");
    expect(session.reachedStages).toEqual(["plan"]);

    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    expect(isPlanReady(session)).toBe(true);
    session = apply(session, { type: "plan_next" });
    expect(session.activeStage).toBe("data");
    expect(session.approvedPlanSnapshotId).toBeDefined();
  });

  it("does not block Plan readiness on an explicitly non-blocking discovery alternative", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session.currentPlan = {
      ...session.currentPlan!,
      unresolvedItems: [
        "Confirm whether a future connector admission should be pursued for a discovery-only IMF dataset; this does not block the executable WEO plan.",
      ],
    };

    expect(isPlanReady(session)).toBe(true);
  });

  it("rejects a command based on an outdated snapshot", () => {
    const session = planned();
    const envelope = makeCommandEnvelope(session, {
      type: "save_plan",
      changes: { objective: "Revised objective" },
    });
    envelope.meta.expectedSnapshotHash = "outdated";

    expect(() => executeWorkflowCommand(session, envelope)).toThrow(WorkflowConflict);
    expect(currentSnapshotHash(session)).not.toBe("outdated");
  });

  it("rejects an AI Plan patch after a manual Plan save", () => {
    let session = planned();
    session = apply(session, {
      type: "propose_plan_patch",
      request: "Add a robustness check.",
    });
    session = apply(session, {
      type: "save_plan",
      changes: { objective: "A human-authored objective." },
    });

    expect(() => apply(session, { type: "apply_plan_patch" })).toThrow(WorkflowConflict);
    expect(session.currentPlan?.objective).toBe("A human-authored objective.");
    expect(session.pendingPlanPatch).toBeDefined();
  });

  it("creates immutable data snapshots and undoes by pointer", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    const initialId = session.data.activeSnapshotId;
    const initialCount = session.data.snapshots.length;

    session = apply(session, { type: "apply_data_operation", operation: "filter_missing" });
    expect(session.data.activeSnapshotId).not.toBe(initialId);
    expect(session.data.snapshots).toHaveLength(initialCount + 1);
    expect(session.data.quality.observations).toBe(11);

    session = apply(session, { type: "undo_data_operation" });
    expect(session.data.activeSnapshotId).toBe(initialId);
    expect(session.data.snapshots).toHaveLength(initialCount + 1);
    expect(session.data.operations).toHaveLength(0);
  });

  it("requires complete and unique canonical mappings before round-trip commit", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "start_round_trip_import", filename: "cleaned.xlsx" });
    session = apply(session, { type: "map_round_trip_column", sourceColumn: "series_id", role: "ignore" });
    session = apply(session, { type: "validate_round_trip" });
    expect(session.data.roundTripDraft?.state).toBe("invalid");
    expect(session.data.roundTripDraft?.errors[0]).toContain("series_id");

    session = apply(session, { type: "map_round_trip_column", sourceColumn: "series_id", role: "series_id" });
    session = apply(session, { type: "validate_round_trip" });
    expect(session.data.roundTripDraft?.state).toBe("validated");
    session = apply(session, { type: "commit_round_trip" });
    expect(session.data.roundTripDraft).toBeUndefined();
    expect(session.data.snapshots.at(-1)?.sourceKind).toBe("external_round_trip");
    expect(session.data.snapshots.at(-1)?.parentSnapshotId).toBeUndefined();
    expect(session.data.columns.at(-1)?.role).toBe("attribute");
    expect(session.data.activeRoundTripManifest?.manifestVerified).toBe(true);
    expect(session.data.operations).toHaveLength(0);
  });

  it("validates operation dependencies when the chain is reordered", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_pipeline_operation", operation: "deflate" });
    expect(session.pipeline.lastValidationError).toContain("must follow Merge");
    const deflate = session.pipeline.operations.at(-1)!;

    session = apply(session, { type: "add_pipeline_operation", operation: "merge" });
    const merge = session.pipeline.operations.at(-1)!;
    session = apply(session, { type: "move_pipeline_operation", operationId: merge.id, direction: "up" });
    expect(session.pipeline.lastValidationError).toBeUndefined();
    const mergeIndex = session.pipeline.operations.findIndex((item) => item.id === merge.id);
    const deflateIndex = session.pipeline.operations.findIndex((item) => item.id === deflate.id);
    expect(mergeIndex).toBeLessThan(deflateIndex);
  });

  it("creates a reviewable Transformation draft from the approved Plan", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });

    expect(session.pipeline.draftSource).toBe("approved_plan");
    expect(session.pipeline.sourcePlanSnapshotId).toBe(session.approvedPlanSnapshotId);
    expect(session.pipeline.operations.map((item) => item.kind)).toEqual([
      "yoy_growth",
      "group_aggregation",
    ]);
    expect(session.pipeline.operations[0].target.indicators).toEqual(["CPI"]);
    expect(session.pipeline.models.map((item) => item.kind)).toEqual(["descriptive"]);
    expect(session.pipeline.models[0].variables).toEqual(["CPI"]);
    expect(session.pipeline.runStatus).toBe("editing");
  });

  it("preserves reviewed Pipeline edits when Data is re-approved under the same Plan", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_pipeline_operation", operation: "difference" });
    const reviewedOperationIds = session.pipeline.operations.map((item) => item.id);

    session = { ...session, activeStage: "data" };
    session = apply(session, { type: "data_next" });

    expect(session.pipeline.operations.map((item) => item.id)).toEqual(reviewedOperationIds);
    expect(session.pipeline.operations.at(-1)?.kind).toBe("difference");
  });

  it("supports typed pipeline edits, deletion and undo without arbitrary code", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    const initialCount = session.pipeline.operations.length;

    session = apply(session, { type: "add_pipeline_operation", operation: "lead" });
    const lead = session.pipeline.operations.at(-1)!;
    expect(lead.parameters).toEqual({ periods: 1 });
    session = apply(session, {
      type: "update_pipeline_parameters",
      operationId: lead.id,
      parameters: { periods: 2 },
    });
    expect(session.pipeline.operations.at(-1)?.parameters).toEqual({ periods: 2 });

    session = apply(session, { type: "undo_pipeline_edit" });
    expect(session.pipeline.operations.at(-1)?.parameters).toEqual({ periods: 1 });
    session = apply(session, { type: "delete_pipeline_operation", operationId: lead.id });
    expect(session.pipeline.operations).toHaveLength(initialCount);
    session = apply(session, { type: "undo_pipeline_edit" });
    expect(session.pipeline.operations).toHaveLength(initialCount + 1);
  });

  it("lets multiple model jobs select registered pipeline outputs", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_model_job", model: "descriptive" });
    const model = session.pipeline.models.at(-1)!;
    const inputRef = session.pipeline.operations[0].outputRef;
    session = apply(session, { type: "update_model_input", modelId: model.id, inputRef });
    expect(session.pipeline.models.at(-1)?.inputRef).toBe(inputRef);
    session = apply(session, {
      type: "update_model_specification",
      modelId: model.id,
      variables: ["CPI", "POLICY_RATE"],
      dependentVariables: [],
      independentVariables: [],
      parameters: { missing: "drop", addConstant: true, covariance: "HC1", maxLags: 1 },
    });
    expect(session.pipeline.models.at(-1)?.variables).toEqual(["CPI", "POLICY_RATE"]);
    expect(session.pipeline.models.at(-1)?.parameters.covariance).toBe("HC1");

    session = apply(session, {
      type: "update_model_input",
      modelId: model.id,
      inputRef: "arbitrary:python",
    });
    expect(session.pipeline.lastValidationError).toContain("registered pipeline output");
    expect(session.pipeline.models.at(-1)?.inputRef).toBe(inputRef);
  });

  it("atomically rebinds a model when its input operation is deleted", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_model_job", model: "descriptive" });
    const model = session.pipeline.models.at(-1)!;
    const finalOperation = session.pipeline.operations.at(-1)!;
    expect(model.inputRef).toBe(finalOperation.outputRef);

    session = apply(session, {
      type: "delete_pipeline_operation",
      operationId: finalOperation.id,
    });

    expect(session.pipeline.models.at(-1)?.inputRef).toBe(
      session.pipeline.operations.at(-1)?.outputRef ?? "active_dataset",
    );
    expect(session.pipeline.lastBindingNotice).toContain("was deleted");
  });

  it("creates a typed ADF job without inventing regression variables", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_model_job", model: "adf" });
    const model = session.pipeline.models.at(-1)!;
    expect(model.kind).toBe("adf");
    expect(model.dependentVariables).toEqual([]);
    expect(model.independentVariables).toEqual([]);
    session = apply(session, {
      type: "update_model_specification",
      modelId: model.id,
      variables: ["CPI"],
      dependentVariables: [],
      independentVariables: [],
      parameters: {
        missing: "drop",
        addConstant: false,
        covariance: "nonrobust",
        maxLags: 4,
        regression: "ct",
        autolag: "BIC",
      },
    });
    expect(session.pipeline.models.at(-1)?.parameters).toMatchObject({
      regression: "ct",
      autolag: "BIC",
      maxLags: 4,
    });
  });

  it("creates a typed ARIMA job with bounded forecast defaults", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_model_job", model: "arima" });
    const model = session.pipeline.models.at(-1)!;

    expect(model.kind).toBe("arima");
    expect(model.dependentVariables).toEqual(["inflation_yoy"]);
    expect(model.independentVariables).toEqual([]);
    expect(model.parameters).toMatchObject({
      orderP: 1,
      orderD: 0,
      orderQ: 0,
      forecastSteps: 4,
      confidenceLevel: 0.95,
      enforceStationarity: true,
      enforceInvertibility: true,
    });
  });

  it("creates a VAR job with optional IRF disabled by default", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_model_job", model: "var" });
    const model = session.pipeline.models.at(-1)!;

    expect(model.kind).toBe("var");
    expect(model.variables).toEqual([]);
    expect(model.parameters).toMatchObject({
      maxLags: 1,
      lagSelection: "fixed",
      trend: "c",
      includeIrf: false,
      irfPeriods: 12,
      impulseVariables: [],
      orthogonalized: true,
      confidenceLevel: 0.95,
    });
  });

  it("creates reviewed harmonization defaults and durable mock lineage", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "add_pipeline_operation", operation: "frequency_conversion" });
    expect(session.pipeline.operations.at(-1)?.parameters).toEqual({
      method: "mean",
      targetFrequency: "quarterly",
      calendar: "calendar",
      fiscalYearEndMonth: 12,
      incompletePeriod: "keep",
    });
    session = apply(session, { type: "run_pipeline" });
    expect(session.pipeline.bundle?.operationLineage?.at(-1)).toMatchObject({
      operation: "frequency_conversion",
      inputRows: session.data.quality.observations,
      outputRows: session.data.quality.observations,
    });
  });

  it("preserves stale analytical and output history after a Plan scope change", () => {
    let session = completed();
    const artifacts = session.output.artifacts;
    expect(session.pipeline.bundle).toBeDefined();

    session = apply(session, {
      type: "save_plan",
      changes: { objective: "Revised scope with a longer sample." },
    });

    expect(session.stageHealth.data).toBe("stale");
    expect(session.stageHealth.transformation).toBe("stale");
    expect(session.stageHealth.output).toBe("stale");
    expect(session.pipeline.bundle).toBeUndefined();
    expect(session.pipeline.bundleHistory).toHaveLength(1);
    expect(session.output.artifactHistory[0]).toHaveLength(artifacts.length);
    expect(session.output.artifacts.every((artifact) => artifact.status === "stale")).toBe(true);
  });

  it("invalidates only Output when deliverables change", () => {
    let session = completed();
    session = apply(session, {
      type: "save_plan",
      changes: {
        deliverables: { ...session.currentPlan!.deliverables, researchReport: false },
      },
    });

    expect(session.stageHealth.data).toBe("completed");
    expect(session.stageHealth.transformation).toBe("completed");
    expect(session.stageHealth.output).toBe("stale");
  });

  it("opens an explicit analysis revision and preserves stale Output history", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "run_pipeline" });
    const artifactCount = session.output.artifacts.length;

    session = apply(session, { type: "start_pipeline_revision" });

    expect(session.activeStage).toBe("transformation");
    expect(session.status).toBe("pipeline_editing");
    expect(session.pipeline.runStatus).toBe("editing");
    expect(session.stageHealth.output).toBe("stale");
    expect(session.output.artifactHistory.at(-1)).toHaveLength(artifactCount);
    expect(session.output.artifacts.every((artifact) => artifact.status === "stale")).toBe(true);
  });

  it("keeps Plan and Output chat commands in separate threads", () => {
    let session = planned();
    session = apply(session, { type: "confirm_geography", resolutionId: "geo-euro-area" });
    session = apply(session, { type: "plan_next" });
    session = apply(session, { type: "data_next" });
    session = apply(session, { type: "run_pipeline" });
    session = apply(session, { type: "request_output_review" });
    const outputCount = session.outputThread.length;
    session = apply(session, { type: "propose_plan_patch", request: "Add a robustness check." });
    expect(session.planThread.at(-1)?.commandType).toBe("plan_patch");
    expect(session.outputThread).toHaveLength(outputCount);

    session = apply(session, { type: "propose_output_revision", request: "Shorten the chart title." });
    expect(session.outputThread.at(-1)?.commandType).toBe("output_revision");
    expect(session.pendingPlanPatch).toBeDefined();
  });
});
