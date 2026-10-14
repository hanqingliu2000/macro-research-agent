import type {
  AnalyticalBundle,
  Artifact,
  DataOperationKind,
  DataPreparationOperation,
  DataWorkspaceState,
  DatasetRow,
  DatasetSnapshot,
  DeliverableKey,
  GeographyResolution,
  LogicalRole,
  ModelKind,
  ModelJob,
  OutputReviewReport,
  OutputState,
  PipelineOperation,
  PipelineState,
  PlanDraft,
  PlanPatchProposal,
  PlanSnapshot,
  SourceRun,
  StageMessage,
  TransformationOperationKind,
  WorkflowCommand,
  WorkflowCommandEnvelope,
  WorkflowNode,
  WorkflowNodeKind,
  WorkflowSession,
  WorkflowStage,
} from "./types";
import { normalizePlanGuidance } from "./planGuidance";

export class WorkflowConflict extends Error {}

const stageOrder: WorkflowStage[] = ["plan", "data", "transformation", "output"];

function now() {
  return new Date().toISOString();
}

function identifier(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function hashValue(value: unknown) {
  const text = JSON.stringify(value);
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `mock-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function message(
  stage: StageMessage["stage"],
  role: StageMessage["role"],
  body: string,
  targetSnapshotHash: string,
  commandType: StageMessage["commandType"],
  label?: string,
): StageMessage {
  return {
    id: identifier(`${stage}-message`),
    stage,
    role,
    body,
    createdAt: now(),
    targetSnapshotHash,
    commandType,
    label,
  };
}

function node(
  kind: WorkflowNodeKind,
  status: WorkflowNode["status"],
  inputSnapshotIds: string[] = [],
  outputSnapshotId?: string,
): WorkflowNode {
  const createdAt = now();
  return {
    id: identifier(`${kind}-node`),
    kind,
    status,
    inputSnapshotIds,
    outputSnapshotId,
    createdAt,
    updatedAt: createdAt,
  };
}

function clarificationBatch() {
  return {
    id: identifier("clarification"),
    round: 1,
    submitted: false,
    answers: {},
    questions: [
      {
        id: "geography",
        prompt: "Which economies or regional group should define the sample?",
        options: [
          "United States, euro area and Japan",
          "G7 economies",
          "Advanced and emerging economy groups",
        ],
      },
      {
        id: "period",
        prompt: "Which period and frequency should anchor the research?",
        options: ["2015–2025, monthly", "2010–2025, quarterly", "2000–2025, annual"],
      },
      {
        id: "emphasis",
        prompt: "Which analytical emphasis should the plan use?",
        options: ["Comparative trends", "Econometric relationship", "Forecast and scenarios"],
      },
    ],
  };
}

function defaultGeographies(): GeographyResolution[] {
  return [
    {
      id: "geo-usa",
      label: "United States",
      kind: "country",
      memberCodes: ["USA"],
      membershipSource: "IMF country code registry",
      effectivePeriod: "All requested periods",
      confirmed: true,
    },
    {
      id: "geo-euro-area",
      label: "Euro area",
      kind: "country_group",
      memberCodes: ["DEU", "FRA", "ITA", "ESP", "NLD"],
      membershipSource: "Versioned ECB membership resolver",
      effectivePeriod: "Period-specific membership",
      confirmed: false,
      aggregation: {
        method: "weighted_mean",
        weightIndicator: "NGDPD",
        weightSource: "IMF WEO nominal GDP",
        missingPolicy: "available_members",
        coverageThreshold: 0.85,
        membershipPolicy: "period_specific",
      },
    },
    {
      id: "geo-jpn",
      label: "Japan",
      kind: "country",
      memberCodes: ["JPN"],
      membershipSource: "IMF country code registry",
      effectivePeriod: "All requested periods",
      confirmed: true,
    },
  ];
}

export function defaultPlan(request: string, confirmedGroups = false): PlanDraft {
  return {
    objective: request,
    geographyIntent: "United States, euro area and Japan",
    period: { start: "2015-01", end: "2025-12", frequency: "monthly" },
    geographyResolutions: defaultGeographies().map((resolution) => ({
      ...resolution,
      confirmed: resolution.kind === "country" || confirmedGroups,
    })),
    dataSources: [
      {
        id: "source-imf-cpi",
        connectorId: "imf_data",
        provider: "IMF Data",
        dataset: "Consumer Price Index",
        indicators: ["CPI"],
        queryIntent: "Retrieve member-country CPI levels and inflation rates.",
        enabled: true,
      },
      {
        id: "source-imf-policy",
        connectorId: "imf_data",
        provider: "IMF Data",
        dataset: "International Financial Statistics",
        indicators: ["POLICY_RATE"],
        queryIntent: "Retrieve policy rates for the same country-period sample.",
        enabled: true,
      },
    ],
    transformationIntents: [
      { id: "yoy_growth", label: "Calculate year-on-year inflation", enabled: true },
      { id: "group_aggregation", label: "Aggregate member-country series", enabled: true },
    ],
    modelIntents: [
      {
        capabilityId: "descriptive",
        id: "descriptive",
        purpose: "Summarize the inflation series.",
        label: "Summarize the inflation series.",
        enabled: true,
        variables: [
          { indicatorCode: "CPI", role: "descriptive", order: 1 },
        ],
        targetIndicators: ["CPI"],
      },
    ],
    capabilityInvocations: [
      { capabilityId: "connector.imf_data", capabilityVersion: "1.0.0", stage: "data", purpose: "Acquire reviewed macroeconomic series.", availability: "planned", approvalGate: "research_plan" },
      { capabilityId: "transformation.apply", capabilityVersion: "1.0.0", stage: "transformation", purpose: "Apply reviewed transformations.", availability: "available", approvalGate: "pipeline_execution" },
      { capabilityId: "model.ols", capabilityVersion: "1.0.0", stage: "transformation", purpose: "Run the reviewed model specification.", availability: "available", approvalGate: "pipeline_execution" },
      { capabilityId: "artifact.report.generate", capabilityVersion: "1.0.0", stage: "output", purpose: "Author an evidence-bound Research Report.", availability: "available", approvalGate: "pipeline_execution" },
      { capabilityId: "output.review.visual", capabilityVersion: "1.0.0", stage: "output", purpose: "Review rendered analytical outputs.", availability: "available", approvalGate: "final_outputs" },
      { capabilityId: "output.review.semantic_report", capabilityVersion: "1.0.0", stage: "output", purpose: "Review Research Report claims against approved evidence.", availability: "available", approvalGate: "final_outputs" },
    ],
    deliverables: {
      charts: true,
      tables: true,
      cleanData: true,
      python: true,
      stata: true,
      researchReport: true,
    },
    assumptions: ["Country-group aggregation is performed locally from member-country data."],
    warnings: ["Euro-area membership and aggregation weights require confirmation."],
    unresolvedItems: confirmedGroups ? [] : ["Confirm euro-area members and aggregation method."],
  };
}

const datasetRows: DatasetRow[] = [
  { series_id: "USA.CPI", entity_code: "USA", indicator_code: "CPI", frequency: "A", period: "2022", value: 8.0 },
  { series_id: "USA.CPI", entity_code: "USA", indicator_code: "CPI", frequency: "A", period: "2023", value: 4.1 },
  { series_id: "USA.CPI", entity_code: "USA", indicator_code: "CPI", frequency: "A", period: "2024", value: 2.9 },
  { series_id: "DEU.CPI", entity_code: "DEU", indicator_code: "CPI", frequency: "A", period: "2022", value: 8.7 },
  { series_id: "DEU.CPI", entity_code: "DEU", indicator_code: "CPI", frequency: "A", period: "2023", value: 6.0 },
  { series_id: "DEU.CPI", entity_code: "DEU", indicator_code: "CPI", frequency: "A", period: "2024", value: 2.5 },
  { series_id: "FRA.CPI", entity_code: "FRA", indicator_code: "CPI", frequency: "A", period: "2022", value: 5.9 },
  { series_id: "FRA.CPI", entity_code: "FRA", indicator_code: "CPI", frequency: "A", period: "2023", value: 5.7 },
  { series_id: "FRA.CPI", entity_code: "FRA", indicator_code: "CPI", frequency: "A", period: "2024", value: null },
  { series_id: "JPN.CPI", entity_code: "JPN", indicator_code: "CPI", frequency: "A", period: "2022", value: 2.5 },
  { series_id: "JPN.CPI", entity_code: "JPN", indicator_code: "CPI", frequency: "A", period: "2023", value: 3.2 },
  { series_id: "JPN.CPI", entity_code: "JPN", indicator_code: "CPI", frequency: "A", period: "2024", value: 2.7 },
];

function baseDataWorkspace(): DataWorkspaceState {
  const createdAt = now();
  const base: DatasetSnapshot = {
    id: "dataset-connector-v1",
    hash: hashValue(datasetRows),
    schemaId: "macro-long-v1",
    label: "Normalized connector data",
    sourceKind: "connector",
    rows: datasetRows,
    createdAt,
  };
  const sourceRuns: SourceRun[] = [
    {
      id: "run-imf-cpi",
      provider: "IMF Data",
      dataset: "Consumer Price Index",
      connectorId: "imf_data",
      query: "member countries · CPI · 2015–2025",
      status: "completed",
      retrievedAt: createdAt,
    },
    {
      id: "run-imf-ifs",
      provider: "IMF Data",
      dataset: "International Financial Statistics",
      connectorId: "imf_data",
      query: "member countries · policy rate · 2015–2025",
      status: "completed",
      retrievedAt: createdAt,
    },
  ];
  return {
    schemaId: "macro-long-v1",
    columns: [
      { id: "series_id", label: "Series ID", dataType: "string", role: "series_id" as const, required: true, key: true },
      { id: "entity_code", label: "Entity code", dataType: "string", role: "entity_code" as const, required: true, key: true },
      { id: "indicator_code", label: "Indicator", dataType: "string", role: "indicator_code" as const, required: true, key: true },
      { id: "frequency", label: "Frequency", dataType: "string", role: "frequency" as const, required: true, key: true },
      { id: "period", label: "Period", dataType: "period" as const, role: "period" as const, required: true, key: true },
      { id: "value", label: "Value", dataType: "number" as const, role: "value" as const, required: true, key: false },
    ],
    sourceRuns,
    snapshots: [base],
    activeSnapshotId: base.id,
    operations: [] as DataPreparationOperation[],
    quality: {
      missingShare: 8.3,
      duplicateKeys: 0,
      observations: base.rows.length,
      warning: "One mock observation is missing. Review before pipeline execution.",
    },
  };
}

function defaultPipeline(): PipelineState {
  const first: PipelineOperation = {
    id: "pipeline-yoy",
    kind: "yoy_growth",
    label: "Year-on-year growth",
    enabled: true,
    target: {
      inputRef: "active_dataset",
      indicators: ["CPI"],
      entities: ["USA", "DEU", "FRA", "JPN"],
      fields: ["value"],
      frequency: "A",
    },
    parameters: { periods: 1 },
    inputRef: "active_dataset",
    outputRef: "step:yoy_growth",
    status: "not_run",
  };
  const second: PipelineOperation = {
    id: "pipeline-aggregate",
    kind: "group_aggregation",
    label: "Euro-area weighted aggregation",
    enabled: true,
    target: {
      inputRef: first.outputRef,
      indicators: ["CPI"],
      entities: ["DEU", "FRA", "ITA", "ESP", "NLD"],
      fields: ["value"],
      frequency: "A",
    },
    parameters: { method: "weighted_mean", coverageThreshold: 0.85 },
    inputRef: first.outputRef,
    outputRef: "step:group_aggregation",
    status: "not_run",
  };
  const model: ModelJob = {
    id: "model-ols",
    kind: "ols",
    label: "Inflation persistence · OLS/HAC",
    inputRef: second.outputRef,
    variables: [],
    dependentVariables: ["inflation_yoy"],
    independentVariables: ["lag_inflation", "policy_rate_change"],
    parameters: { missing: "drop", addConstant: true, covariance: "HAC", maxLags: 1 },
    status: "not_run",
  };
  return {
    operations: [first, second],
    models: [model],
    selectedOperationId: first.id,
    runStatus: "editing",
    bundleHistory: [],
    editHistory: [],
  };
}

function emptyOutput(): OutputState {
  return {
    artifacts: [],
    artifactHistory: [],
    guidelineVersion: "publication-v1",
    workbookTemplateVersion: "research-workbook-v1",
  };
}

function initialStageHealth() {
  return {
    plan: "current" as const,
    data: "not_reached" as const,
    transformation: "not_reached" as const,
    output: "not_reached" as const,
  };
}

export function createWorkflowSession(request: string): WorkflowSession {
  const createdAt = now();
  return {
    id: identifier("workflow-session"),
    title: request,
    request,
    status: "clarifying",
    activeStage: "plan",
    reachedStages: ["plan"],
    stageHealth: initialStageHealth(),
    createdAt,
    updatedAt: createdAt,
    archived: false,
    clarification: clarificationBatch(),
    planThread: [
      message("plan", "user", request, "request", "clarification"),
      message(
        "plan",
        "agent",
        "I will clarify geography, period and analytical emphasis before drafting the current Plan.",
        "request",
        "clarification",
        "Clarification",
      ),
    ],
    outputThread: [],
    planSnapshots: [],
    data: baseDataWorkspace(),
    pipeline: defaultPipeline(),
    output: emptyOutput(),
    nodes: [node("research_request", "completed", [], "request")],
  };
}

function makePlanSnapshot(plan: PlanDraft, actor: PlanSnapshot["actor"]): PlanSnapshot {
  const createdAt = now();
  return {
    id: identifier("plan-snapshot"),
    hash: hashValue(plan),
    plan,
    actor,
    createdAt,
  };
}

export function isPlanReady(session: WorkflowSession) {
  const plan = session.currentPlan;
  if (!plan) return false;
  const { blockers } = normalizePlanGuidance(plan.unresolvedItems, plan.warnings);
  return (
    plan.objective.trim().length > 0 &&
    plan.dataSources.some((source) => source.enabled) &&
    plan.geographyResolutions.every((resolution) => resolution.confirmed) &&
    blockers.length === 0
  );
}

export function currentSnapshotHash(session: WorkflowSession) {
  return hashValue({
    plan: session.currentPlanSnapshotId,
    data: session.data.activeSnapshotId,
    pipeline: session.pipeline.operations,
    models: session.pipeline.models,
    output: session.output.artifacts.map((artifact) => artifact.hash),
  });
}

export function makeCommandEnvelope(
  session: WorkflowSession,
  command: WorkflowCommand,
): WorkflowCommandEnvelope {
  const requestedAt = now();
  const commandId = identifier("command");
  return {
    meta: {
      commandId,
      idempotencyKey: commandId,
      sessionId: session.id,
      expectedActiveStage: session.activeStage,
      expectedSnapshotHash: currentSnapshotHash(session),
      requestedAt,
      actor: "user",
    },
    command,
  };
}

export function reachableStages(session: WorkflowSession) {
  return stageOrder.filter((stage) => session.reachedStages.includes(stage));
}

export function latestReachableStage(session: WorkflowSession): WorkflowStage {
  return reachableStages(session).at(-1) ?? "plan";
}

export function isStageReachable(session: WorkflowSession, stage: WorkflowStage) {
  return session.reachedStages.includes(stage);
}

function addReached(session: WorkflowSession, stage: WorkflowStage) {
  return session.reachedStages.includes(stage)
    ? session.reachedStages
    : [...session.reachedStages, stage].sort(
        (left, right) => stageOrder.indexOf(left) - stageOrder.indexOf(right),
      );
}

function staleNodes(session: WorkflowSession, stages: WorkflowStage[], reason: string) {
  const kindsByStage: Record<WorkflowStage, WorkflowNodeKind[]> = {
    plan: ["research_plan", "geography_resolution"],
    data: ["data_acquisition", "data_preparation", "external_round_trip"],
    transformation: ["transformation_pipeline", "model_execution"],
    output: ["output_generation", "output_revision", "reproduction_manifest"],
  };
  const kinds = new Set(stages.flatMap((stage) => kindsByStage[stage]));
  return session.nodes.map((item) =>
    kinds.has(item.kind) && !["pending", "stale"].includes(item.status)
      ? { ...item, status: "stale" as const, staleReason: reason, updatedAt: now() }
      : item,
  );
}

function invalidate(
  session: WorkflowSession,
  stages: WorkflowStage[],
  reason: string,
): WorkflowSession {
  if (stages.length === 0) return session;
  const next = structuredClone(session);
  next.nodes = staleNodes(session, stages, reason);
  for (const stage of stages) {
    if (next.reachedStages.includes(stage)) next.stageHealth[stage] = "stale";
  }
  if (stages.includes("data")) {
    next.data.approvedSnapshotId = undefined;
  }
  if (stages.includes("transformation")) {
    if (next.pipeline.bundle) {
      next.pipeline.bundleHistory = [...next.pipeline.bundleHistory, next.pipeline.bundle];
    }
    next.pipeline.runStatus = "stale";
    next.pipeline.bundle = undefined;
    next.pipeline.operations = next.pipeline.operations.map((operation) => ({
      ...operation,
      status: "stale",
    }));
    next.pipeline.models = next.pipeline.models.map((model) => ({ ...model, status: "stale" }));
    next.pipeline.editHistory = [];
  }
  if (stages.includes("output")) {
    if (next.output.artifacts.some((artifact) => artifact.status !== "stale")) {
      next.output.artifactHistory = [
        ...next.output.artifactHistory,
        next.output.artifacts.map((artifact) => ({
          ...artifact,
          status: "stale",
          specification: next.output.artifactSpecifications?.[artifact.id],
        })),
      ];
    }
    next.output.finalizedAt = undefined;
    next.output.artifacts = next.output.artifacts.map((artifact) => ({
      ...artifact,
      status: "stale",
    }));
  }
  next.lastNotice = `${stages.map(capitalize).join(", ")} marked stale: ${reason}`;
  return next;
}

function capitalize(value: string) {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

export function impactForPlanChanges(
  session: WorkflowSession,
  changes: Partial<PlanDraft>,
): WorkflowStage[] {
  if (!session.currentPlan) return [];
  const affected = new Set<WorkflowStage>();
  const scopeKeys: Array<keyof PlanDraft> = ["objective", "geographyIntent", "period", "geographyResolutions", "dataSources"];
  if (scopeKeys.some((key) => key in changes)) {
    affected.add("data");
    affected.add("transformation");
    affected.add("output");
  }
  if ("transformationIntents" in changes || "modelIntents" in changes) {
    affected.add("transformation");
    affected.add("output");
  }
  if ("deliverables" in changes) affected.add("output");
  return stageOrder.filter(
    (stage) =>
      affected.has(stage) &&
      session.reachedStages.includes(stage) &&
      session.stageHealth[stage] !== "stale",
  );
}

function applyPlanChanges(
  session: WorkflowSession,
  changes: Partial<PlanDraft>,
  actor: PlanSnapshot["actor"],
): WorkflowSession {
  if (!session.currentPlan) return session;
  const affected = impactForPlanChanges(session, changes);
  let next = invalidate(session, affected, "The current Plan changed.");
  const plan: PlanDraft = { ...next.currentPlan!, ...structuredClone(changes) };
  const snapshot = makePlanSnapshot(plan, actor);
  next = {
    ...next,
    currentPlan: plan,
    currentPlanSnapshotId: snapshot.id,
    planSnapshots: [...next.planSnapshots, snapshot],
    approvedPlanSnapshotId: affected.includes("data") ? undefined : next.approvedPlanSnapshotId,
    activeStage: "plan",
    status: "plan_review",
    stageHealth: { ...next.stageHealth, plan: "current" },
    updatedAt: now(),
    nodes: [
      ...next.nodes,
      node("research_plan", "waiting_for_review", [], snapshot.id),
    ],
  };
  return next;
}

function dataRowsAfterOperation(rows: DatasetRow[], operation: DataOperationKind) {
  if (operation === "filter_missing") return rows.filter((row) => row.value !== null);
  if (operation === "deduplicate") {
    const seen = new Set<string>();
    return rows.filter((row) => {
      const key = `${row.series_id}|${row.entity_code}|${row.indicator_code}|${row.frequency}|${row.period}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
  if (operation === "sort") {
    return [...rows].sort((left, right) =>
      `${left.entity_code}|${left.period}`.localeCompare(`${right.entity_code}|${right.period}`),
    );
  }
  if (operation === "map_codes") {
    return rows.map((row) => ({ ...row, canonical_entity: row.entity_code }));
  }
  if (operation === "rename_columns") {
    return rows.map((row) => ({ ...row, entity_name: row.canonical_entity ?? row.entity_code }));
  }
  if (operation === "drop_columns") {
    return rows.map((row) => {
      const next = { ...row };
      delete next.canonical_entity;
      return next;
    });
  }
  if (operation === "cast_types") {
    return rows.map((row) => ({ ...row, value: row.value === null ? null : Number(row.value) }));
  }
  if (operation === "missing_value_rule") {
    return rows.map((row) => ({ ...row, missing_value: row.value === null ? "missing" : "observed" }));
  }
  return rows.map((row) => ({
    series_id: row.series_id,
    entity_code: row.entity_code,
    indicator_code: row.indicator_code,
    frequency: row.frequency,
    period: row.period,
    value: row.value,
  }));
}

const dataOperationLabels: Record<DataOperationKind, string> = {
  filter_missing: "Filter missing observations",
  keep_columns: "Keep canonical columns",
  drop_columns: "Drop non-canonical attributes",
  rename_columns: "Rename mapped attributes",
  map_codes: "Map canonical entity codes",
  cast_types: "Cast value and period types",
  missing_value_rule: "Apply missing-value rule",
  deduplicate: "Remove duplicate keys",
  sort: "Sort entity and period",
};

function applyDataOperation(
  session: WorkflowSession,
  operationKind: DataOperationKind,
  parameters: Record<string, unknown> = {},
): WorkflowSession {
  const active = session.data.snapshots.find(
    (snapshot) => snapshot.id === session.data.activeSnapshotId,
  );
  if (!active) return session;
  let next = invalidate(session, ["transformation", "output"], "The active dataset changed.");
  const rows = dataRowsAfterOperation(active.rows, operationKind);
  const snapshot: DatasetSnapshot = {
    id: identifier("dataset-prepared"),
    hash: hashValue(rows),
    schemaId: session.data.schemaId,
    label: dataOperationLabels[operationKind],
    sourceKind: "prepared",
    parentSnapshotId: active.id,
    rows,
    createdAt: now(),
  };
  const operation: DataPreparationOperation = {
    id: identifier("data-operation"),
    kind: operationKind,
    label: dataOperationLabels[operationKind],
    inputSnapshotId: active.id,
    outputSnapshotId: snapshot.id,
    createdAt: now(),
    parameters,
  };
  next = {
    ...next,
    status: "data_review",
    activeStage: "data",
    updatedAt: now(),
    stageHealth: { ...next.stageHealth, data: "current" },
    data: {
      ...next.data,
      snapshots: [...next.data.snapshots, snapshot],
      activeSnapshotId: snapshot.id,
      approvedSnapshotId: undefined,
      operations: [...next.data.operations, operation],
      quality: {
        ...next.data.quality,
        observations: rows.length,
        missingShare: rows.length
          ? Math.round((rows.filter((row) => row.value === null).length / rows.length) * 1000) / 10
          : 0,
      },
    },
    nodes: [...next.nodes, node("data_preparation", "completed", [active.id], snapshot.id)],
  };
  return next;
}

function undoDataOperation(session: WorkflowSession): WorkflowSession {
  const latest = session.data.operations.at(-1);
  if (!latest) return session;
  let next = invalidate(session, ["transformation", "output"], "A data preparation operation was undone.");
  next = {
    ...next,
    status: "data_review",
    activeStage: "data",
    updatedAt: now(),
    stageHealth: { ...next.stageHealth, data: "current" },
    data: {
      ...next.data,
      activeSnapshotId: latest.inputSnapshotId,
      approvedSnapshotId: undefined,
      operations: next.data.operations.slice(0, -1),
    },
  };
  return next;
}

const pipelineLabels: Record<TransformationOperationKind, string> = {
  lag: "Lag",
  lead: "Lead",
  difference: "First difference",
  yoy_growth: "Year-on-year growth",
  period_growth: "Period-on-period growth",
  log: "Natural logarithm",
  rebase_index: "Rebase index",
  unit_conversion: "Unit conversion",
  deflate: "Deflate nominal series",
  per_capita: "Per-capita conversion",
  frequency_conversion: "Frequency conversion",
  merge: "Merge datasets",
  rolling_mean: "Rolling mean",
  seasonal_rule: "Seasonal rule",
  group_aggregation: "Group aggregation",
};

function relinkPipeline(operations: PipelineOperation[]) {
  let inputRef = "active_dataset";
  return operations.map((operation) => {
    const next = {
      ...operation,
      inputRef,
      target: { ...operation.target, inputRef },
      outputRef: `step:${operation.id}`,
    };
    inputRef = next.outputRef;
    return next;
  });
}

function rebindModelsAfterDelete(
  models: ModelJob[],
  deletedIndex: number,
  operations: PipelineOperation[],
) {
  const allowed = new Set(["active_dataset", ...operations.map((item) => item.outputRef)]);
  const fallback = deletedIndex > 0 && operations.length
    ? operations[deletedIndex - 1].outputRef
    : "active_dataset";
  const rebound: string[] = [];
  const repaired = models.map((model) => {
    if (allowed.has(model.inputRef)) return model;
    rebound.push(model.label);
    return { ...model, inputRef: fallback };
  });
  return {
    models: repaired,
    notice: rebound.length
      ? `Rebound ${rebound.join(", ")} to ${fallback} because its input operation was deleted.`
      : undefined,
  };
}

function validatePipelineOrder(operations: PipelineOperation[]) {
  for (let index = 0; index < operations.length; index += 1) {
    const requirement = operations[index].requiresOperation;
    if (!requirement) continue;
    const dependencyIndex = operations.findIndex((operation) => operation.kind === requirement);
    if (dependencyIndex < 0 || dependencyIndex > index) {
      return `${operations[index].label} must follow ${pipelineLabels[requirement]}.`;
    }
  }
  return undefined;
}

function defaultPipelineParameters(
  operation: TransformationOperationKind,
): PipelineOperation["parameters"] {
  if (["lag", "lead", "difference", "yoy_growth", "period_growth"].includes(operation)) {
    return { periods: 1 };
  }
  if (operation === "rolling_mean") return { window: 4, minimumPeriods: 3 };
  if (operation === "rebase_index") return { basePeriod: "2019", baseValue: 100 };
  if (operation === "unit_conversion") return { sourceUnit: "percent", targetUnit: "basis points", factor: 100, offset: 0 };
  if (operation === "frequency_conversion") return { method: "mean", targetFrequency: "quarterly", calendar: "calendar", fiscalYearEndMonth: 12, incompletePeriod: "keep" };
  if (operation === "group_aggregation") {
    return { method: "weighted_mean", coverageThreshold: 0.85 };
  }
  return {};
}

function defaultModelParameters(kind: ModelKind): ModelJob["parameters"] {
  return {
    missing: "drop",
    addConstant: true,
    covariance: "nonrobust",
    maxLags: 1,
    ...(kind === "adf" ? { regression: "c" as const, autolag: "AIC" as const } : {}),
    ...(["arima", "sarimax"].includes(kind) ? {
      orderP: 1,
      orderD: 0,
      orderQ: 0,
      seasonalP: 0,
      seasonalD: 0,
      seasonalQ: 0,
      seasonalPeriod: 0,
      trend: "c" as const,
      forecastSteps: 4,
      confidenceLevel: 0.95,
      enforceStationarity: true,
      enforceInvertibility: true,
    } : {}),
    ...(kind === "var" ? {
      lagSelection: "fixed" as const,
      trend: "c" as const,
      includeIrf: false,
      irfPeriods: 12,
      impulseVariables: [],
      orthogonalized: true,
      confidenceLevel: 0.95,
    } : {}),
  };
}

function planPipelineDraft(session: WorkflowSession): PipelineState {
  const active = session.data.snapshots.find((item) => item.id === session.data.activeSnapshotId);
  const observedIndicators = [...new Set(
    (active?.rows ?? []).map((row) => String(row.indicator_code ?? "").trim().toUpperCase()).filter(Boolean),
  )];
  const requestedIndicators = (session.currentPlan?.dataSources ?? [])
    .filter((source) => source.enabled)
    .flatMap((source) => source.indicators.map((indicator) => indicator.trim().toUpperCase()));
  const indicators = [
    ...new Set([
      ...requestedIndicators.filter((indicator) => observedIndicators.includes(indicator)),
      ...observedIndicators,
    ]),
  ];
  let inputRef = "active_dataset";
  const operations = (session.currentPlan?.transformationIntents ?? []).flatMap((intent) => {
    if (!intent.enabled || !(intent.id in pipelineLabels)) return [];
    const kind = intent.id as TransformationOperationKind;
    const id = identifier("pipeline-operation");
    const operation: PipelineOperation = {
      id,
      kind,
      label: intent.label || pipelineLabels[kind],
      enabled: true,
      target: {
        inputRef,
        indicators,
        entities: [],
        fields: ["value"],
        frequency: session.currentPlan?.period.frequency,
      },
      parameters: defaultPipelineParameters(kind),
      inputRef,
      outputRef: `step:${id}`,
      status: "not_run",
    };
    inputRef = operation.outputRef;
    return [operation];
  });
  const supportedModels = new Set<ModelKind>(["descriptive", "correlation", "ols", "adf", "arima", "sarimax", "var"]);
  const models = (session.currentPlan?.modelIntents ?? []).flatMap((intent) => {
    const kind = (intent.capabilityId ?? intent.id) as ModelKind;
    if (!intent.enabled || !supportedModels.has(kind)) return [];
    const ordered = [...(intent.variables ?? [])].sort((a, b) => a.order - b.order);
    if (ordered.some((variable) => !indicators.includes(variable.indicatorCode))) return [];
    const role = (name: typeof ordered[number]["role"]) => ordered.filter((variable) => variable.role === name).map((variable) => variable.indicatorCode);
    const targets = ["adf", "arima"].includes(kind) ? role("dependent") : [undefined];
    return targets.map((target) => {
      const parameters = defaultModelParameters(kind);
      if (intent.forecastHorizon) {
        parameters.forecastSteps = intent.forecastHorizon.steps;
        parameters.confidenceLevel = intent.forecastHorizon.confidenceLevel;
      }
      return {
        id: identifier("model-job"),
        kind,
        label: target ? `${intent.purpose ?? intent.label} [${target}]` : intent.purpose ?? intent.label,
        inputRef,
        variables: kind === "var" ? role("system") : ["descriptive", "correlation"].includes(kind) ? role("descriptive") : [],
        dependentVariables: target ? [target] : role("dependent"),
        independentVariables: kind === "sarimax" ? role("exogenous") : kind === "ols" ? role("independent") : [],
        parameters,
        status: "not_run" as const,
      };
    });
  });
  return {
    operations,
    models,
    selectedOperationId: operations[0]?.id,
    runStatus: "editing",
    bundleHistory: [],
    editHistory: [],
    draftSource: "approved_plan",
    sourcePlanSnapshotId: session.approvedPlanSnapshotId,
  };
}

function pipelineForDataApproval(session: WorkflowSession): PipelineState {
  const firstTransformationEntry = !session.reachedStages.includes("transformation");
  const planChanged = Boolean(
    session.pipeline.sourcePlanSnapshotId
      && session.pipeline.sourcePlanSnapshotId !== session.approvedPlanSnapshotId,
  );
  if (firstTransformationEntry || planChanged) return planPipelineDraft(session);
  return {
    ...session.pipeline,
    runStatus: "editing",
    bundle: undefined,
    operations: session.pipeline.operations.map((operation) => ({ ...operation, status: "not_run" })),
    models: session.pipeline.models.map((model) => ({ ...model, status: "not_run" })),
    editHistory: [],
  };
}

function invalidateOutputForPipeline(session: WorkflowSession, reason: string) {
  const next = invalidate(session, ["output"], reason);
  return {
    ...next,
    status: "pipeline_editing" as const,
    activeStage: "transformation" as const,
    updatedAt: now(),
    pipeline: {
      ...next.pipeline,
      runStatus: "editing" as const,
      bundle: undefined,
      operations: next.pipeline.operations.map((operation) => ({ ...operation, status: "not_run" as const })),
      models: next.pipeline.models.map((model) => ({ ...model, status: "not_run" as const })),
      editHistory: [
        ...next.pipeline.editHistory,
        {
          operations: structuredClone(session.pipeline.operations),
          models: structuredClone(session.pipeline.models),
          selectedOperationId: session.pipeline.selectedOperationId,
        },
      ],
    },
    stageHealth: { ...next.stageHealth, transformation: "current" as const },
  };
}

function makeArtifacts(plan: PlanDraft): Artifact[] {
  const definitions: Array<[DeliverableKey, string, Artifact["format"], string]> = [
    ["charts", "inflation_comparison.png", "png", "Publication chart preview"],
    ["tables", "research_tables.xlsx", "xlsx", "Styled research tables"],
    ["cleanData", "analysis_data.csv", "csv", "Underlying analytical data"],
    ["python", "run_research.py", "python", "Generated typed Python workflow"],
    ["stata", "run_research.do", "stata_do", "Generated supported Stata workflow"],
    ["researchReport", "research_report.md", "report", "Narrative research report"],
  ];
  return definitions
    .filter(([key]) => plan.deliverables[key])
    .map(([key, name, format, description]) => ({
      id: `artifact-${key}`,
      name,
      format,
      description,
      hash: hashValue({ key, name, description, created: now() }),
      status: "ready",
      exportSelected: true,
    }));
}

function makeArtifactSpecifications(artifacts: Artifact[], plan: PlanDraft) {
  return Object.fromEntries(
    artifacts.map((artifact) => [
      artifact.id,
      {
        schema_version: "mra-output-spec-v2",
        title: plan.objective,
        unit: "As reported",
        source_note: "Source: approved analytical snapshot",
        number_format: "0.00",
        alt_text: `Preview of ${artifact.name}`,
        guideline_version: "publication-v1",
        data_hash: "mock:approved-data",
      },
    ]),
  );
}

function makeOutputReview(
  output: OutputState,
  inspectedRowCount: number,
  iteration: number,
): OutputReviewReport {
  const selected = output.artifacts.filter((artifact) => artifact.exportSelected);
  return {
    id: identifier("output-review"),
    status: "pass",
    providerProfile: "deterministic-local",
    modelId: "deterministic-output-review-v1",
    targetArtifactSetHash: output.artifactSetHash ?? "",
    guidelineVersion: output.guidelineVersion,
    iteration,
    reviewedArtifactIds: selected.map((artifact) => artifact.id),
    reviewRenderHashes: output.reviewRenderHashes ?? {},
    dataAccessId: "mock-output-data-grant",
    inspectedRowCount,
    findings: [],
    patches: [],
    semanticReportStatus: selected.some((artifact) => artifact.format === "report")
      ? "pass"
      : "not_applicable",
    createdAt: now(),
  };
}

function analyticalBundle(session: WorkflowSession): AnalyticalBundle {
  const enabled = session.pipeline.operations.filter((operation) => operation.enabled);
  return {
    id: identifier("analytical-bundle"),
    inputDatasetId: session.data.activeSnapshotId,
    finalDatasetRef: session.pipeline.operations.at(-1)?.outputRef ?? "active_dataset",
    operationIds: enabled.map((operation) => operation.id),
    operationLineage: enabled.map((operation) => ({
      operationId: operation.id,
      operation: operation.kind,
      inputRef: operation.inputRef,
      outputRef: operation.outputRef,
      inputSnapshotId: operation.inputRef === "active_dataset" ? session.data.activeSnapshotId : `mock:${operation.inputRef}`,
      inputSnapshotHash: hashValue([operation.inputRef, "input"]),
      outputSnapshotId: `mock:${operation.outputRef}`,
      outputSnapshotHash: hashValue([operation.outputRef, "output"]),
      specificationHash: hashValue({ kind: operation.kind, target: operation.target, parameters: operation.parameters }),
      inputRows: session.data.quality.observations,
      outputRows: session.data.quality.observations,
    })),
    modelResultIds: session.pipeline.models.map((model) => `result:${model.id}`),
    diagnostics: ["Typed pipeline validation passed.", "Model input schemas are compatible."],
    warnings: ["Mock results are for interaction validation only."],
    pythonCode: "df = run_typed_pipeline(data, operations)\nresults = run_model_jobs(df, model_jobs)",
    stataCode: "* Generated from reviewed typed operations\ndo pipeline_steps.do\ndo model_jobs.do",
    createdAt: now(),
  };
}

function handleCommand(session: WorkflowSession, command: WorkflowCommand): WorkflowSession {
  if (command.type === "request_plan_clarification" && session.currentPlan) {
    const clarification = clarificationBatch();
    clarification.round = (session.clarification.round ?? 1) + 1;
    return {
      ...session,
      status: "plan_review",
      updatedAt: now(),
      clarification,
      planThread: [
        ...session.planThread,
        message(
          "plan",
          "agent",
          "Please confirm the additional research details before I revise the Plan.",
          currentSnapshotHash(session),
          "clarification",
          `Clarification round ${clarification.round}`,
        ),
      ],
      nodes: [
        ...session.nodes,
        node(
          "clarification_batch",
          "in_progress",
          [session.currentPlanSnapshotId ?? currentSnapshotHash(session)],
          clarification.id,
        ),
      ],
    };
  }

  if (command.type === "submit_clarification") {
    const plan = defaultPlan(session.request);
    const snapshot = makePlanSnapshot(plan, "agent");
    return {
      ...session,
      status: "plan_review",
      updatedAt: now(),
      clarification: { ...session.clarification, answers: command.answers, submitted: true },
      currentPlan: plan,
      currentPlanSnapshotId: snapshot.id,
      planSnapshots: [...session.planSnapshots, snapshot],
      planThread: [
        ...session.planThread,
        message("plan", "user", Object.values(command.answers).join(" · "), snapshot.hash, "clarification", "Clarification answers"),
        message("plan", "agent", "I drafted the current Plan. Confirm the country-group resolution or edit any field before continuing.", snapshot.hash, "notice", "Plan ready"),
      ],
      nodes: [
        ...session.nodes,
        node("clarification_batch", "completed", [], session.clarification.id),
        node("research_plan", "waiting_for_review", [session.clarification.id], snapshot.id),
        node("geography_resolution", "waiting_for_review", [snapshot.id]),
      ],
    };
  }

  if (command.type === "confirm_geography" && session.currentPlan) {
    const geographyResolutions = session.currentPlan.geographyResolutions.map((resolution) =>
      resolution.id === command.resolutionId ? { ...resolution, confirmed: true } : resolution,
    );
    const unresolvedItems = geographyResolutions.every((resolution) => resolution.confirmed)
      ? []
      : session.currentPlan.unresolvedItems;
    const warnings = geographyResolutions.every((resolution) => resolution.confirmed)
      ? session.currentPlan.warnings.filter((warning) => !warning.includes("require confirmation"))
      : session.currentPlan.warnings;
    return applyPlanChanges(session, { geographyResolutions, unresolvedItems, warnings }, "user");
  }

  if (command.type === "save_plan") {
    return applyPlanChanges(session, command.changes, command.actor ?? "user");
  }

  if (command.type === "propose_plan_patch" && session.currentPlan) {
    const lower = command.request.toLowerCase();
    const changes: PlanPatchProposal["changes"] = lower.includes("report")
      ? { deliverables: { ...session.currentPlan.deliverables, researchReport: true } }
      : lower.includes("period") || lower.includes("start")
        ? { period: { ...session.currentPlan.period, start: "2010" } }
        : {
            objective: `${session.currentPlan.objective} Incorporate the requested robustness comparison.`,
            assumptions: [...session.currentPlan.assumptions, command.request],
          };
    const affectedStages = impactForPlanChanges(session, changes);
    const proposal = {
      id: identifier("plan-patch"),
      summary: lower.includes("report")
        ? "Enable the Research Report deliverable."
        : lower.includes("period") || lower.includes("start")
          ? "Extend the sample start to 2010."
          : "Add the requested robustness comparison to the objective and assumptions.",
      request: command.request,
      changes,
      affectedStages,
      targetSnapshotHash: session.planSnapshots.at(-1)?.hash ?? "plan",
    };
    return {
      ...session,
      pendingPlanPatch: proposal,
      updatedAt: now(),
      planThread: [
        ...session.planThread,
        message("plan", "user", command.request, proposal.targetSnapshotHash, "plan_patch"),
        message("plan", "agent", "I prepared a typed Plan patch. Review the exact change and downstream impact before applying it.", proposal.targetSnapshotHash, "plan_patch", "Patch proposed"),
      ],
    };
  }

  if (command.type === "apply_plan_patch" && session.pendingPlanPatch) {
    const proposal = session.pendingPlanPatch;
    const currentPlanHash = session.planSnapshots.at(-1)?.hash ?? "plan";
    if (proposal.targetSnapshotHash !== currentPlanHash) {
      throw new WorkflowConflict(
        "The Plan changed after this proposal was created. Request a new proposal.",
      );
    }
    const accepted = command.acceptedFields ?? Object.keys(proposal.changes);
    const changes = Object.fromEntries(Object.entries(proposal.changes).filter(([field]) => accepted.includes(field))) as Partial<PlanDraft>;
    const applied = applyPlanChanges(session, changes, "agent");
    return {
      ...applied,
      pendingPlanPatch: undefined,
      planThread: [
        ...applied.planThread,
        message("plan", "system", `Applied: ${proposal.summary}`, currentSnapshotHash(applied), "notice", "Patch applied"),
      ],
    };
  }

  if (command.type === "reject_plan_patch" && session.pendingPlanPatch) {
    return {
      ...session,
      pendingPlanPatch: undefined,
      updatedAt: now(),
      planThread: [
        ...session.planThread,
        message("plan", "user", "Rejected the proposed Plan change.", currentSnapshotHash(session), "notice", "Patch rejected"),
      ],
    };
  }

  if (command.type === "plan_next" && isPlanReady(session) && session.currentPlanSnapshotId) {
    const snapshotId = session.currentPlanSnapshotId;
    const reacquiring = session.stageHealth.data === "stale";
    const reacquiredSnapshot: DatasetSnapshot | undefined = reacquiring
      ? {
          id: identifier("dataset-reacquired"),
          hash: hashValue({ rows: datasetRows, plan: snapshotId }),
          schemaId: session.data.schemaId,
          label: "Reacquired normalized connector data",
          sourceKind: "connector",
          rows: structuredClone(datasetRows),
          createdAt: now(),
        }
      : undefined;
    const activeSnapshotId = reacquiredSnapshot?.id ?? session.data.activeSnapshotId;
    return {
      ...session,
      status: "data_review",
      activeStage: "data",
      reachedStages: addReached(session, "data"),
      stageHealth: { ...session.stageHealth, plan: "completed", data: "current" },
      approvedPlanSnapshotId: snapshotId,
      data: {
        ...session.data,
        snapshots: reacquiredSnapshot
          ? [...session.data.snapshots, reacquiredSnapshot]
          : session.data.snapshots,
        activeSnapshotId,
        approvedSnapshotId: undefined,
        operations: reacquiredSnapshot ? [] : session.data.operations,
      },
      updatedAt: now(),
      lastNotice: "Plan confirmed. Mock connector acquisition completed.",
      nodes: [
        ...session.nodes.map((item) =>
          item.kind === "research_plan" && item.outputSnapshotId === snapshotId
            ? { ...item, status: "approved" as const, updatedAt: now() }
            : item,
        ),
        node("data_acquisition", "completed", [snapshotId], activeSnapshotId),
      ],
    };
  }

  if (command.type === "prepare_round_trip_export") {
    const checksum = hashValue({
      sessionId: session.id,
      snapshotId: session.data.activeSnapshotId,
      schemaId: session.data.schemaId,
    });
    return {
      ...session,
      updatedAt: now(),
      data: {
        ...session.data,
        lastExportedPackage: {
          filename: `mra_roundtrip_${session.id}.xlsx`,
          sheets: ["Data", "Schema", "Provenance", "Instructions", "_MRA_MANIFEST"],
          snapshotId: session.data.activeSnapshotId,
          schemaId: session.data.schemaId,
          checksum,
          manifestLocked: true,
        },
      },
    };
  }

  if (command.type === "start_round_trip_import") {
    const sourceColumns = ["series_id", "economy_code", "indicator", "frequency", "date", "observation_value", "analyst_note"];
    return {
      ...session,
      updatedAt: now(),
      data: {
        ...session.data,
        roundTripDraft: {
          id: identifier("roundtrip-import"),
          filename: command.filename,
          workbookChecksum: hashValue({ filename: command.filename, importedAt: now() }),
          manifestVerified: true,
          formulasMaterialized: true,
          sourceColumns,
          mappings: {
            series_id: "series_id",
            economy_code: "entity_code",
            indicator: "indicator_code",
            frequency: "frequency",
            date: "period",
            observation_value: "value",
            analyst_note: "attribute",
          },
          state: "mapping",
          errors: [],
          warnings: ["Mock preview: formula cells must be materialized before production import."],
        },
      },
    };
  }

  if (command.type === "map_round_trip_column" && session.data.roundTripDraft) {
    return {
      ...session,
      updatedAt: now(),
      data: {
        ...session.data,
        roundTripDraft: {
          ...session.data.roundTripDraft,
          state: "mapping",
          mappings: {
            ...session.data.roundTripDraft.mappings,
            [command.sourceColumn]: command.role,
          },
        },
      },
    };
  }

  if (command.type === "validate_round_trip" && session.data.roundTripDraft) {
    const required: LogicalRole[] = ["series_id", "entity_code", "indicator_code", "frequency", "period", "value"];
    const selected = Object.values(session.data.roundTripDraft.mappings);
    const errors = required
      .filter((role) => !selected.includes(role))
      .map((role) => `Map one source column to required role: ${role}.`);
    const duplicateRoles = required.filter(
      (role) => selected.filter((selectedRole) => selectedRole === role).length > 1,
    );
    errors.push(...duplicateRoles.map((role) => `Required role ${role} is mapped more than once.`));
    if (!session.data.roundTripDraft.manifestVerified) {
      errors.push("The locked _MRA_MANIFEST does not match this Workflow session.");
    }
    if (!session.data.roundTripDraft.formulasMaterialized) {
      errors.push("Formula cells in Data must be converted to values before import.");
    }
    return {
      ...session,
      updatedAt: now(),
      data: {
        ...session.data,
        roundTripDraft: {
          ...session.data.roundTripDraft,
          state: errors.length ? "invalid" : "validated",
          errors,
        },
      },
    };
  }

  if (command.type === "commit_round_trip" && session.data.roundTripDraft?.state === "validated") {
    const draft = session.data.roundTripDraft;
    let next = invalidate(session, ["transformation", "output"], "The active dataset was replaced by an external round trip.");
    const active = next.data.snapshots.find((snapshot) => snapshot.id === next.data.activeSnapshotId);
    if (!active) return session;
    const rows = active.rows.map((row, index) => ({
      ...row,
      analyst_note: index === 0 ? "Reviewed externally" : "",
    }));
    const schemaId = `${next.data.schemaId}:roundtrip:${draft.id}`;
    const snapshot: DatasetSnapshot = {
      id: identifier("dataset-roundtrip"),
      hash: hashValue({ rows, filename: draft.filename }),
      schemaId,
      label: `External cleaning · ${draft.filename}`,
      sourceKind: "external_round_trip",
      rows,
      createdAt: now(),
    };
    next = {
      ...next,
      status: "data_review",
      activeStage: "data",
      updatedAt: now(),
      stageHealth: { ...next.stageHealth, data: "current" },
      data: {
        ...next.data,
        schemaId,
        columns: next.data.columns.some((column) => column.id === "analyst_note")
          ? next.data.columns
          : [
              ...next.data.columns,
              {
                id: "analyst_note",
                label: "Analyst note",
                dataType: "string",
                role: "attribute",
                required: false,
                key: false,
              },
            ],
        snapshots: [...next.data.snapshots, snapshot],
        activeSnapshotId: snapshot.id,
        approvedSnapshotId: undefined,
        operations: [],
        roundTripDraft: undefined,
        activeRoundTripManifest: {
          workbookChecksum: draft.workbookChecksum,
          sourceSnapshotId: active.id,
          schemaId,
          manifestVerified: draft.manifestVerified,
        },
      },
      nodes: [...next.nodes, node("external_round_trip", "completed", [active.id], snapshot.id)],
      lastNotice: "Validated external workbook is now the active dataset. Original snapshots remain preserved.",
    };
    return next;
  }

  if (command.type === "propose_data_assistance") {
    const active = session.data.snapshots.find((item) => item.id === session.data.activeSnapshotId);
    if (!active) return session;
    const operations = [
      ...(active.rows.some((row) => row.value === null)
        ? [{ id: "data-filter-missing", operation: "filter_missing" as const, parameters: { column: "value" }, rationale: "Remove rows without an analytical value." }]
        : []),
      { id: "data-sort", operation: "sort" as const, parameters: {}, rationale: "Create a deterministic canonical row order." },
    ];
    return {
      ...session,
      updatedAt: now(),
      data: {
        ...session.data,
        pendingAssistantProposal: {
          id: identifier("data-assistant"),
          request: command.request,
          summary: `Prepared ${operations.length} registered cleaning steps.`,
          operations,
          targetSnapshotId: active.id,
          targetSnapshotHash: active.hash,
        },
      },
    };
  }

  if (command.type === "apply_data_assistance" && session.data.pendingAssistantProposal) {
    const proposal = session.data.pendingAssistantProposal;
    const active = session.data.snapshots.find((item) => item.id === session.data.activeSnapshotId);
    if (!active || active.id !== proposal.targetSnapshotId || active.hash !== proposal.targetSnapshotHash) {
      throw new WorkflowConflict("The active dataset changed after this proposal was created.");
    }
    let next: WorkflowSession = {
      ...session,
      data: { ...session.data, pendingAssistantProposal: undefined },
    };
    for (const item of proposal.operations) {
      if (command.acceptedItemIds.includes(item.id)) {
        next = applyDataOperation(next, item.operation, item.parameters);
      }
    }
    return next;
  }

  if (command.type === "reject_data_assistance") {
    return {
      ...session,
      updatedAt: now(),
      data: { ...session.data, pendingAssistantProposal: undefined },
    };
  }

  if (command.type === "apply_data_operation") {
    return applyDataOperation(session, command.operation, command.parameters);
  }

  if (command.type === "undo_data_operation") {
    return undoDataOperation(session);
  }

  if (command.type === "approve_data_merge") {
    if (session.data.mergeReview?.status !== "waiting_for_review") {
      throw new WorkflowConflict("There is no cross-source merge awaiting review.");
    }
    return {
      ...session,
      updatedAt: now(),
      data: {
        ...session.data,
        mergeReview: {
          ...session.data.mergeReview,
          status: "approved",
          reviewedAt: now(),
          reviewedBy: "user",
        },
      },
    };
  }

  if (command.type === "data_next") {
    if (session.data.mergeReview?.status === "waiting_for_review") {
      throw new WorkflowConflict(
        "Review and approve the cross-source merge before configuring the pipeline.",
      );
    }
    const preparedFromPlan = !session.reachedStages.includes("transformation") || Boolean(
      session.pipeline.sourcePlanSnapshotId
        && session.pipeline.sourcePlanSnapshotId !== session.approvedPlanSnapshotId,
    );
    const pipeline = pipelineForDataApproval(session);
    const analysisCount = pipeline.operations.length + pipeline.models.length;
    return {
      ...session,
      status: "pipeline_editing",
      activeStage: "transformation",
      reachedStages: addReached(session, "transformation"),
      stageHealth: { ...session.stageHealth, data: "completed", transformation: "current" },
      updatedAt: now(),
      data: { ...session.data, approvedSnapshotId: session.data.activeSnapshotId },
      pipeline,
      lastNotice: analysisCount && preparedFromPlan
        ? "Plan analysis draft prepared. Review transformations and model jobs before Run."
        : analysisCount
        ? "Approved data linked to the reviewed pipeline. Review it before Run."
        : "Active dataset approved. The Plan requests no transformations or model jobs.",
    };
  }

  if (command.type === "start_pipeline_revision") {
    if (session.activeStage !== "output" || session.pipeline.runStatus !== "completed") {
      return session;
    }
    return {
      ...invalidateOutputForPipeline(session, "The user started an analysis revision."),
      lastNotice: "Analysis revision started. Previous Output is stale and preserved in history; review the changes and run the updated analysis.",
    };
  }

  if (command.type === "propose_analysis_assistance") {
    const targetStateHash = hashValue({
      approvedSnapshotId: session.data.approvedSnapshotId,
      operations: session.pipeline.operations,
      models: session.pipeline.models,
    });
    return {
      ...session,
      updatedAt: now(),
      pipeline: {
        ...session.pipeline,
        pendingAssistantProposal: {
          id: identifier("analysis-assistant"),
          request: command.request,
          summary: "Prepared a registered transformation and descriptive model proposal.",
          operations: [{
            id: "analysis-yoy-growth",
            operation: "yoy_growth",
            parameters: { periods: 1 },
            indicators: ["CPI"],
            entities: ["USA", "DEU", "FRA", "JPN"],
            fields: ["value"],
            rationale: "Calculate a comparable year-on-year change.",
          }],
          models: [{
            id: "analysis-descriptive",
            model: "descriptive",
            variables: ["CPI"],
            dependentVariables: [],
            independentVariables: [],
            parameters: { missing: "drop", addConstant: true, covariance: "nonrobust", maxLags: 1 },
            rationale: "Summarize the reviewed transformed series.",
          }],
          modelRemovals: [],
          targetStateHash,
          targetSnapshotId: session.data.approvedSnapshotId ?? "active_dataset",
        },
      },
    };
  }

  if (command.type === "apply_analysis_assistance" && session.pipeline.pendingAssistantProposal) {
    const proposal = session.pipeline.pendingAssistantProposal;
    const currentHash = hashValue({
      approvedSnapshotId: session.data.approvedSnapshotId,
      operations: session.pipeline.operations,
      models: session.pipeline.models,
    });
    if (currentHash !== proposal.targetStateHash) {
      throw new WorkflowConflict("The Pipeline changed after this proposal was created.");
    }
    let next: WorkflowSession = {
      ...session,
      pipeline: { ...session.pipeline, pendingAssistantProposal: undefined },
    };
    for (const item of proposal.operations) {
      if (command.acceptedItemIds.includes(item.id)) {
        next = handleCommand(next, { type: "add_pipeline_operation", operation: item.operation });
      }
    }
    for (const item of proposal.models) {
      if (command.acceptedItemIds.includes(item.id)) {
        next = handleCommand(next, { type: "add_model_job", model: item.model });
      }
    }
    const removalIds = new Set(
      (proposal.modelRemovals ?? [])
        .filter((item) => command.acceptedItemIds.includes(item.id))
        .map((item) => item.modelJobId),
    );
    if (removalIds.size) {
      next = {
        ...next,
        pipeline: {
          ...next.pipeline,
          models: next.pipeline.models.filter((item) => !removalIds.has(item.id)),
        },
      };
    }
    return next;
  }

  if (command.type === "reject_analysis_assistance") {
    return {
      ...session,
      updatedAt: now(),
      pipeline: { ...session.pipeline, pendingAssistantProposal: undefined },
    };
  }

  if (command.type === "add_pipeline_operation") {
    const base = invalidateOutputForPipeline(session, "The transformation pipeline changed.");
    const operation: PipelineOperation = {
      id: identifier("pipeline-operation"),
      kind: command.operation,
      label: pipelineLabels[command.operation],
      enabled: true,
      target: {
        inputRef: "active_dataset",
        indicators: ["CPI"],
        entities: ["USA", "DEU", "FRA", "JPN"],
        fields: ["value"],
      },
      parameters: defaultPipelineParameters(command.operation),
      inputRef: "active_dataset",
      outputRef: "",
      status: "not_run",
      requiresOperation: command.operation === "deflate" ? "merge" : undefined,
    };
    const operations = relinkPipeline([...base.pipeline.operations, operation]);
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        operations,
        selectedOperationId: operation.id,
        lastValidationError: validatePipelineOrder(operations),
      },
    };
  }

  if (command.type === "move_pipeline_operation") {
    const index = session.pipeline.operations.findIndex((operation) => operation.id === command.operationId);
    const target = command.direction === "up" ? index - 1 : index + 1;
    if (index < 0 || target < 0 || target >= session.pipeline.operations.length) return session;
    const candidate = [...session.pipeline.operations];
    [candidate[index], candidate[target]] = [candidate[target], candidate[index]];
    const validationError = validatePipelineOrder(candidate);
    if (validationError) {
      return { ...session, pipeline: { ...session.pipeline, lastValidationError: validationError } };
    }
    const base = invalidateOutputForPipeline(session, "The transformation order changed.");
    return {
      ...base,
      pipeline: { ...base.pipeline, operations: relinkPipeline(candidate), lastValidationError: undefined },
    };
  }

  if (command.type === "toggle_pipeline_operation") {
    const base = invalidateOutputForPipeline(session, "A transformation was enabled or disabled.");
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        operations: base.pipeline.operations.map((operation) =>
          operation.id === command.operationId
            ? { ...operation, enabled: !operation.enabled }
            : operation,
        ),
      },
    };
  }

  if (command.type === "delete_pipeline_operation") {
    const base = invalidateOutputForPipeline(session, "A transformation was deleted.");
    const deletedIndex = base.pipeline.operations.findIndex(
      (operation) => operation.id === command.operationId,
    );
    const operations = relinkPipeline(
      base.pipeline.operations.filter((operation) => operation.id !== command.operationId),
    );
    const binding = rebindModelsAfterDelete(base.pipeline.models, deletedIndex, operations);
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        operations,
        models: binding.models,
        lastBindingNotice: binding.notice,
        selectedOperationId:
          base.pipeline.selectedOperationId === command.operationId
            ? operations[0]?.id
            : base.pipeline.selectedOperationId,
        lastValidationError: validatePipelineOrder(operations),
      },
    };
  }

  if (command.type === "undo_pipeline_edit") {
    const previous = session.pipeline.editHistory.at(-1);
    if (!previous) return session;
    const next = invalidate(session, ["output"], "The latest pipeline edit was undone.");
    return {
      ...next,
      status: "pipeline_editing",
      activeStage: "transformation",
      updatedAt: now(),
      stageHealth: { ...next.stageHealth, transformation: "current" },
      pipeline: {
        ...next.pipeline,
        operations: structuredClone(previous.operations),
        models: structuredClone(previous.models),
        selectedOperationId: previous.selectedOperationId,
        runStatus: "editing",
        bundle: undefined,
        editHistory: session.pipeline.editHistory.slice(0, -1),
        lastValidationError: validatePipelineOrder(previous.operations),
      },
    };
  }

  if (command.type === "select_pipeline_operation") {
    return { ...session, pipeline: { ...session.pipeline, selectedOperationId: command.operationId } };
  }

  if (command.type === "update_pipeline_target") {
    const operationIndex = session.pipeline.operations.findIndex(
      (operation) => operation.id === command.operationId,
    );
    const allowedInputs = [
      "active_dataset",
      ...session.pipeline.operations.slice(0, operationIndex).map((operation) => operation.outputRef),
    ];
    if (
      command.target.inputRef &&
      (operationIndex < 0 || !allowedInputs.includes(command.target.inputRef))
    ) {
      return {
        ...session,
        pipeline: {
          ...session.pipeline,
          lastValidationError: "A transformation may only read the active dataset or an upstream operation output.",
        },
      };
    }
    const base = invalidateOutputForPipeline(session, "A transformation target changed.");
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        operations: base.pipeline.operations.map((operation) =>
          operation.id === command.operationId
            ? {
                ...operation,
                inputRef: command.target.inputRef ?? operation.inputRef,
                target: { ...operation.target, ...command.target },
              }
            : operation,
        ),
      },
    };
  }

  if (command.type === "update_pipeline_parameters") {
    const base = invalidateOutputForPipeline(session, "Transformation parameters changed.");
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        operations: base.pipeline.operations.map((operation) =>
          operation.id === command.operationId
            ? { ...operation, parameters: command.parameters }
            : operation,
        ),
      },
    };
  }

  if (command.type === "add_model_job") {
    const base = invalidateOutputForPipeline(session, "A model job was added.");
    const inputRef = base.pipeline.operations.at(-1)?.outputRef ?? "active_dataset";
    const model: ModelJob = {
      id: identifier("model-job"),
      kind: command.model,
      label: `${command.model.toUpperCase()} model`,
      inputRef,
      variables: [],
      dependentVariables: ["ols", "arima", "sarimax"].includes(command.model) ? ["inflation_yoy"] : [],
      independentVariables: command.model === "ols" ? ["lag_inflation", "policy_rate_change"] : [],
      parameters: defaultModelParameters(command.model),
      status: "not_run",
    };
    return { ...base, pipeline: { ...base.pipeline, models: [...base.pipeline.models, model] } };
  }

  if (command.type === "update_model_input") {
    const allowedInputs = [
      "active_dataset",
      ...session.pipeline.operations.map((operation) => operation.outputRef),
    ];
    if (!allowedInputs.includes(command.inputRef)) {
      return {
        ...session,
        pipeline: {
          ...session.pipeline,
          lastValidationError: "A model must read the active dataset or a registered pipeline output.",
        },
      };
    }
    const base = invalidateOutputForPipeline(session, "A model input changed.");
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        lastBindingNotice: undefined,
        models: base.pipeline.models.map((model) =>
          model.id === command.modelId ? { ...model, inputRef: command.inputRef } : model,
        ),
      },
    };
  }

  if (command.type === "update_model_specification") {
    const base = invalidateOutputForPipeline(session, "A model specification changed.");
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        models: base.pipeline.models.map((model) =>
          model.id === command.modelId
            ? {
                ...model,
                variables: command.variables,
                dependentVariables: command.dependentVariables,
                independentVariables: command.independentVariables,
                parameters: command.parameters,
              }
            : model,
        ),
      },
    };
  }

  if (command.type === "delete_model_job") {
    const base = invalidateOutputForPipeline(session, "A model job was deleted.");
    return {
      ...base,
      pipeline: {
        ...base.pipeline,
        models: base.pipeline.models.filter((model) => model.id !== command.modelId),
      },
    };
  }

  if (
    command.type === "run_pipeline" &&
    session.data.approvedSnapshotId &&
    !session.pipeline.lastValidationError
  ) {
    const bundle = analyticalBundle(session);
    const plan = session.currentPlan ?? defaultPlan(session.request, true);
    const artifacts = makeArtifacts(plan);
    const artifactSpecifications = makeArtifactSpecifications(artifacts, plan);
    return {
      ...session,
      status: "output_review",
      activeStage: "output",
      reachedStages: addReached(session, "output"),
      stageHealth: {
        ...session.stageHealth,
        transformation: "completed",
        output: "current",
      },
      updatedAt: now(),
      pipeline: {
        ...session.pipeline,
        runStatus: "completed",
        bundle,
        operations: session.pipeline.operations.map((operation) => ({ ...operation, status: "completed" })),
        models: session.pipeline.models.map((model) => ({ ...model, status: "completed" })),
      },
      output: {
        ...session.output,
        artifactSetId: identifier("artifact-set"),
        artifactSetHash: hashValue(
          artifacts.map((artifact) => ({
            artifactHash: artifact.hash,
            specification: artifactSpecifications[artifact.id],
          })),
        ),
        artifacts,
        selectedArtifactId: artifacts.find((artifact) =>
          ["svg", "csv", "xlsx"].includes(artifact.format)
        )?.id ?? artifacts[0]?.id,
        pendingProposal: undefined,
        finalizedAt: undefined,
        guidelineVersion: "publication-v1",
        workbookTemplateVersion: "research-workbook-v1",
        revisionCapability: true,
        artifactSpecifications,
        reviewRenderHashes: Object.fromEntries(
          artifacts.filter((artifact) => artifact.format === "png" || artifact.format === "svg").map((artifact) => [artifact.id, hashValue([artifact.hash, "review-render"])]),
        ),
        preflightFindings: [],
        reviewReport: undefined,
        reviewHistory: [],
        revisionHistory: [],
        reviewIteration: 0,
        maxReviewIterations: 3,
        reportSemanticStatus: artifacts.some((artifact) => artifact.format === "report")
          ? "pending"
          : "not_applicable",
      },
      outputThread: [
        ...session.outputThread,
        message("output", "agent", "The typed pipeline completed. Review current artifacts or request a targeted revision.", bundle.id, "notice", "Outputs ready"),
      ],
      nodes: [
        ...session.nodes,
        node("transformation_pipeline", "completed", [session.data.approvedSnapshotId], bundle.id),
        node("model_execution", "completed", [bundle.id], `model-results:${bundle.id}`),
        node("output_generation", "waiting_for_review", [bundle.id], `artifacts:${bundle.id}`),
      ],
    };
  }

  if (command.type === "select_artifact") {
    return { ...session, output: { ...session.output, selectedArtifactId: command.artifactId } };
  }

  if (command.type === "toggle_artifact_export") {
    return {
      ...session,
      output: {
        ...session.output,
        reviewReport: undefined,
        pendingProposal: undefined,
        artifacts: session.output.artifacts.map((artifact) =>
          artifact.id === command.artifactId
            ? { ...artifact, exportSelected: !artifact.exportSelected }
            : artifact,
        ),
      },
    };
  }

  if (command.type === "request_output_review") {
    const iteration = (session.output.reviewIteration ?? 0) + 1;
    if (iteration > (session.output.maxReviewIterations ?? 3)) return session;
    const report = makeOutputReview(
      session.output,
      session.data.snapshots.find((item) => item.id === session.data.activeSnapshotId)?.rows.length ?? 0,
      iteration,
    );
    return {
      ...session,
      updatedAt: now(),
      output: {
        ...session.output,
        reviewIteration: iteration,
        reviewHistory: [
          ...(session.output.reviewHistory ?? []),
          ...(session.output.reviewReport ? [session.output.reviewReport] : []),
        ],
        reviewReport: report,
        reportSemanticStatus: report.semanticReportStatus,
      },
      nodes: [
        ...session.nodes,
        node("output_compliance_review", "completed", [session.output.artifactSetHash ?? ""], `review:${iteration}:compliance`),
        node("visual_artifact_review", "completed", [session.output.artifactSetHash ?? ""], `review:${iteration}:visual`),
        ...(report.semanticReportStatus === "not_applicable" ? [] : [
          node("semantic_report_review", "completed", [session.output.artifactSetHash ?? ""], `review:${iteration}:report`),
        ]),
      ],
    };
  }

  if (command.type === "propose_output_revision") {
    if ((session.output.reviewIteration ?? 0) >= (session.output.maxReviewIterations ?? 3)) {
      return session;
    }
    const artifact = session.output.artifacts.find(
      (item) => item.id === session.output.selectedArtifactId,
    ) ?? session.output.artifacts.find((item) => ["svg", "csv", "xlsx"].includes(item.format));
    if (!artifact || !["svg", "csv", "xlsx"].includes(artifact.format)) return session;
    const targetSnapshotHash = currentSnapshotHash(session);
    const proposal = {
      id: identifier("output-revision"),
      request: command.request,
      summary: `Revise ${artifact.name} without regenerating unrelated artifacts.`,
      artifactIds: [artifact.id],
      patches: [{
        id: identifier("output-patch"),
        artifactId: artifact.id,
        rationale: "Apply the request through the versioned artifact specification.",
        changes: { title: command.request },
      }],
      targetArtifactSetHash: session.output.artifactSetHash ?? targetSnapshotHash,
      targetArtifactHashes: { [artifact.id]: artifact.hash },
    };
    return {
      ...session,
      updatedAt: now(),
      output: { ...session.output, pendingProposal: proposal },
      outputThread: [
        ...session.outputThread,
        message("output", "user", command.request, targetSnapshotHash, "output_revision"),
        message("output", "agent", "I prepared a targeted artifact revision. Apply it to regenerate only the named output.", targetSnapshotHash, "output_revision", "Revision proposed"),
      ],
    };
  }

  if (command.type === "reject_output_revision" && session.output.pendingProposal) {
    return {
      ...session,
      updatedAt: now(),
      output: { ...session.output, pendingProposal: undefined },
    };
  }

  if (command.type === "apply_output_revision" && session.output.pendingProposal) {
    const proposal = session.output.pendingProposal;
    const selectedPatches = proposal.patches.filter((patch) => command.acceptedPatchIds.includes(patch.id));
    const selectedArtifactIds = new Set(selectedPatches.map((patch) => patch.artifactId));
    if (
      (session.output.reviewIteration ?? 0) >= (session.output.maxReviewIterations ?? 3)
      || session.output.artifacts.some(
        (artifact) => selectedArtifactIds.has(artifact.id) && !["svg", "csv", "xlsx"].includes(artifact.format),
      )
    ) return session;
    const nextArtifacts = session.output.artifacts.map((artifact) =>
      selectedArtifactIds.has(artifact.id)
        ? {
            ...artifact,
            id: `${artifact.id}-revision-${(session.output.reviewIteration ?? 0) + 1}`,
            description: `${artifact.description} · selectively regenerated`,
            hash: hashValue({ artifact, selectedPatches }),
            status: "ready" as const,
          }
        : artifact,
    );
    const replacementIds = Object.fromEntries(
      session.output.artifacts.map((artifact, index) => [artifact.id, nextArtifacts[index].id]),
    );
    const changesByArtifact = Object.fromEntries(
      selectedPatches.map((patch) => [patch.artifactId, patch.changes]),
    );
    const nextSpecifications = Object.fromEntries(
      Object.entries(session.output.artifactSpecifications ?? {}).map(([artifactId, specification]) => [
        replacementIds[artifactId] ?? artifactId,
        { ...specification, ...(changesByArtifact[artifactId] ?? {}) },
      ]),
    );
    const nextRenderHashes = Object.fromEntries(
      Object.entries(session.output.reviewRenderHashes ?? {}).map(([artifactId, renderHash]) => {
        const nextArtifactId = replacementIds[artifactId] ?? artifactId;
        return [nextArtifactId, nextArtifactId === artifactId ? renderHash : hashValue([renderHash, selectedPatches])];
      }),
    );
    const nextArtifactSetHash = hashValue(
      nextArtifacts.map((artifact) => ({
        artifactHash: artifact.hash,
        specification: nextSpecifications[artifact.id],
      })),
    );
    const iteration = (session.output.reviewIteration ?? 0) + 1;
    const nextOutput: OutputState = {
      ...session.output,
      finalizedAt: undefined,
      pendingProposal: undefined,
      artifactHistory: [
        ...session.output.artifactHistory,
        session.output.artifacts.map((artifact) => ({
          ...artifact,
          specification: session.output.artifactSpecifications?.[artifact.id],
        })),
      ],
      artifacts: nextArtifacts,
      artifactSpecifications: nextSpecifications,
      reviewRenderHashes: nextRenderHashes,
      artifactSetHash: nextArtifactSetHash,
      reviewHistory: [
        ...(session.output.reviewHistory ?? []),
        ...(session.output.reviewReport ? [session.output.reviewReport] : []),
      ],
      reviewIteration: iteration,
      reviewReport: undefined,
    };
    nextOutput.reviewReport = makeOutputReview(
      nextOutput,
      session.data.snapshots.find((item) => item.id === session.data.activeSnapshotId)?.rows.length ?? 0,
      iteration,
    );
    nextOutput.reportSemanticStatus = nextOutput.reviewReport.semanticReportStatus;
    nextOutput.revisionHistory = [
      ...(session.output.revisionHistory ?? []),
      {
        id: proposal.id,
        revision: (session.output.revisionHistory?.length ?? 0) + 1,
        request: proposal.request,
        acceptedPatchIds: selectedPatches.map((patch) => patch.id).sort(),
        previousArtifactSetHash: session.output.artifactSetHash ?? "",
        artifactSetHash: nextArtifactSetHash,
        artifacts: session.output.artifacts
          .filter((artifact) => selectedArtifactIds.has(artifact.id))
          .map((artifact) => {
            const replacement = nextArtifacts.find(
              (candidate) => candidate.id === replacementIds[artifact.id],
            )!;
            return {
              previousArtifactId: artifact.id,
              artifactId: replacement.id,
              name: replacement.name,
              format: replacement.format as "svg" | "csv" | "xlsx",
              previousHash: artifact.hash,
              hash: replacement.hash,
            };
          }),
        appliedAt: now(),
        reviewIteration: iteration,
        reviewReportId: nextOutput.reviewReport.id,
        reviewStatus: nextOutput.reviewReport.status,
      },
    ];
    return {
      ...session,
      status: "output_review",
      activeStage: "output",
      updatedAt: now(),
      output: nextOutput,
      outputThread: [
        ...session.outputThread,
        message("output", "system", `Applied: ${proposal.summary}`, currentSnapshotHash(session), "notice", "Revision applied"),
      ],
      nodes: [
        ...session.nodes,
        node("output_revision", "completed", proposal.artifactIds, proposal.id),
        node("output_compliance_review", "completed", [nextArtifactSetHash], `review:${iteration}:compliance`),
        node("visual_artifact_review", "completed", [nextArtifactSetHash], `review:${iteration}:visual`),
        ...(nextOutput.reviewReport.semanticReportStatus === "not_applicable" ? [] : [
          node("semantic_report_review", "completed", [nextArtifactSetHash], `review:${iteration}:report`),
        ]),
      ],
    };
  }

  if (command.type === "finalize_output") {
    if (!session.output.reviewReport || session.output.pendingProposal) return session;
    if (session.output.reviewReport.status === "fail") return session;
    if (session.output.reviewReport.status === "warning" && !command.acceptWarnings) return session;
    const finalizedAt = now();
    return {
      ...session,
      status: "completed",
      activeStage: "output",
      updatedAt: finalizedAt,
      stageHealth: { ...session.stageHealth, output: "completed" },
      output: {
        ...session.output,
        finalizedAt,
        artifacts: session.output.artifacts.map((artifact) =>
          artifact.exportSelected ? { ...artifact, status: "frozen" } : artifact,
        ),
      },
      nodes: [...session.nodes, node("reproduction_manifest", "completed", session.output.artifacts.map((artifact) => artifact.id), "manifest-current")],
      lastNotice: "Selected artifacts and the reproduction manifest are frozen.",
    };
  }

  return session;
}

export function executeWorkflowCommand(
  session: WorkflowSession,
  envelope: WorkflowCommandEnvelope,
): WorkflowSession {
  if (envelope.meta.sessionId !== session.id) {
    throw new WorkflowConflict("Command session does not match the current Workflow session.");
  }
  if (envelope.meta.expectedActiveStage !== session.activeStage) {
    throw new WorkflowConflict("The Workflow stage changed before this command was applied.");
  }
  if (envelope.meta.expectedSnapshotHash !== currentSnapshotHash(session)) {
    throw new WorkflowConflict("The Workflow snapshot changed before this command was applied.");
  }
  return handleCommand(session, envelope.command);
}
