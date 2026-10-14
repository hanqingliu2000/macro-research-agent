export type WorkflowStage = "plan" | "data" | "transformation" | "output";

export type WorkflowSessionStatus =
  | "clarifying"
  | "plan_review"
  | "acquiring"
  | "data_review"
  | "pipeline_editing"
  | "pipeline_running"
  | "output_generating"
  | "output_review"
  | "completed"
  | "failed"
  | "cancelled";

export type StageHealth = "not_reached" | "current" | "completed" | "stale";

export type WorkflowNodeKind =
  | "research_request"
  | "clarification_batch"
  | "research_plan"
  | "geography_resolution"
  | "data_acquisition"
  | "data_preparation"
  | "external_round_trip"
  | "transformation_pipeline"
  | "model_execution"
  | "stage_handoff"
  | "output_generation"
  | "output_revision"
  | "output_compliance_review"
  | "visual_artifact_review"
  | "semantic_report_review"
  | "reproduction_manifest";

export type WorkflowNodeStatus =
  | "pending"
  | "ready"
  | "in_progress"
  | "waiting_for_review"
  | "approved"
  | "completed"
  | "stale"
  | "failed"
  | "cancelled";

export interface WorkflowNode {
  id: string;
  kind: WorkflowNodeKind;
  status: WorkflowNodeStatus;
  inputSnapshotIds: string[];
  outputSnapshotId?: string;
  staleReason?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ClarificationQuestion {
  id: string;
  prompt: string;
  options: string[];
}

export interface ClarificationBatch {
  id: string;
  round?: number;
  questions: ClarificationQuestion[];
  answers: Record<string, string>;
  submitted: boolean;
}

export interface StageMessage {
  id: string;
  stage: WorkflowStage;
  role: "user" | "agent" | "system";
  body: string;
  createdAt: string;
  targetSnapshotHash: string;
  commandType:
    | "clarification"
    | "plan_patch"
    | "data_assistance"
    | "analysis_assistance"
    | "output_revision"
    | "report_authoring"
    | "report_review"
    | "notice";
  label?: string;
}

export interface ResearchPeriod {
  start: string;
  end: string;
  frequency: "monthly" | "quarterly" | "annual";
}

export interface AggregationSpec {
  method: "sum" | "simple_mean" | "weighted_mean";
  weightIndicator?: string;
  weightSource?: string;
  missingPolicy: "available_members" | "balanced_members";
  coverageThreshold: number;
  membershipPolicy: "period_specific" | "fixed_snapshot";
}

export interface GeographyResolution {
  id: string;
  label: string;
  kind: "country" | "country_group";
  memberCodes: string[];
  membershipSource: string;
  effectivePeriod: string;
  confirmed: boolean;
  aggregation?: AggregationSpec;
}

export interface DataSourcePlan {
  id: string;
  connectorId: string;
  provider: string;
  dataset: string;
  indicators: string[];
  queryIntent: string;
  enabled: boolean;
}

export interface PlannedCapabilityIntent {
  id: string;
  label: string;
  enabled: boolean;
  targetIndicators?: string[];
}

export type ModelVariableRole =
  | "system"
  | "descriptive"
  | "dependent"
  | "independent"
  | "exogenous";

export interface ModelVariable {
  indicatorCode: string;
  role: ModelVariableRole;
  order: number;
}

export interface ForecastHorizon {
  steps: number;
  unit: "periods";
  confidenceLevel: number;
}

export interface PlannedModelIntent {
  capabilityId: string;
  /** Compatibility projection for older clients and stored sessions. */
  id: string;
  purpose: string;
  /** Compatibility projection for older clients and stored sessions. */
  label: string;
  enabled: boolean;
  variables: ModelVariable[];
  forecastHorizon?: ForecastHorizon;
  /** Derived from variables; never edited independently. */
  targetIndicators: string[];
}

export interface PlannedCapabilityInvocation {
  capabilityId: string;
  capabilityVersion: string;
  stage: WorkflowStage;
  purpose: string;
  availability: "available" | "planned" | "disabled";
  approvalGate?: "research_plan" | "pipeline_execution" | "final_outputs";
}

export type DeliverableKey =
  | "charts"
  | "tables"
  | "cleanData"
  | "python"
  | "stata"
  | "researchReport";

export type DeliverableSelection = Record<DeliverableKey, boolean>;

export interface PlanDraft {
  objective: string;
  geographyIntent: string;
  period: ResearchPeriod;
  geographyResolutions: GeographyResolution[];
  dataSources: DataSourcePlan[];
  transformationIntents: PlannedCapabilityIntent[];
  modelIntents: PlannedModelIntent[];
  capabilityInvocations: PlannedCapabilityInvocation[];
  deliverables: DeliverableSelection;
  assumptions: string[];
  warnings: string[];
  unresolvedItems: string[];
}

export interface PlanSnapshot {
  id: string;
  hash: string;
  plan: PlanDraft;
  actor: "user" | "agent";
  createdAt: string;
}

export interface PlanPatchProposal {
  id: string;
  summary: string;
  request: string;
  changes: Partial<PlanDraft>;
  affectedStages: WorkflowStage[];
  targetSnapshotHash: string;
}

export type LogicalRole =
  | "series_id"
  | "entity_code"
  | "indicator_code"
  | "frequency"
  | "period"
  | "value"
  | "attribute"
  | "ignore";

export interface DatasetColumn {
  id: string;
  label: string;
  dataType: "string" | "number" | "period";
  role: LogicalRole;
  required: boolean;
  key: boolean;
}

export type DatasetCell = string | number | null;
export type DatasetRow = Record<string, DatasetCell>;

export interface DatasetSnapshot {
  id: string;
  hash: string;
  schemaId: string;
  label: string;
  sourceKind: "connector" | "prepared" | "external_round_trip" | "analytical";
  parentSnapshotId?: string;
  rows: DatasetRow[];
  createdAt: string;
}

export interface SourceRun {
  id: string;
  provider: string;
  dataset: string;
  connectorId: string;
  query: string;
  status: "ready" | "running" | "completed" | "failed";
  retrievedAt?: string;
  requestedPeriodStart?: string;
  resolvedPeriodStart?: string;
  requestedPeriodEnd?: string;
  resolvedPeriodEnd?: string;
  periodResolution?: "query_upper_bound" | "calendar_year_mapping";
}

export type DataOperationKind =
  | "filter_missing"
  | "keep_columns"
  | "drop_columns"
  | "rename_columns"
  | "map_codes"
  | "cast_types"
  | "missing_value_rule"
  | "deduplicate"
  | "sort";

export interface DataPreparationOperation {
  id: string;
  kind: DataOperationKind;
  label: string;
  inputSnapshotId: string;
  outputSnapshotId: string;
  createdAt: string;
  parameters?: Record<string, unknown>;
}

export interface DataAssistantProposal {
  id: string;
  request: string;
  summary: string;
  operations: Array<{
    id: string;
    operation: DataOperationKind;
    parameters: Record<string, unknown>;
    rationale: string;
  }>;
  sourceMappings?: Array<{
    id: string;
    sourceColumn: string;
    role: LogicalRole;
    rationale: string;
  }>;
  diagnostics?: Array<{
    kind: "missing_observations" | "limitation";
    summary: string;
    details: string[];
  }>;
  targetSnapshotId: string;
  targetSnapshotHash: string;
  agent?: AgentRuntimeDescriptor;
}

export interface AgentRuntimeDescriptor {
  role: "planner" | "data_steward" | "analyst" | "report_author" | "report_reviewer";
  authority: "clarify" | "diagnose" | "propose" | "author" | "review";
  providerProfile: string;
  modelId: string;
  status: "available" | "unavailable" | "degraded";
  limitations?: string[];
}

export interface HandoffDecision {
  id: string;
  category: string;
  summary: string;
  status: "confirmed" | "inferred" | "needs_confirmation";
  sourceRefs: string[];
}

export interface StageHandoffEnvelopeV1 {
  schemaVersion: "mra-stage-handoff-v1";
  handoffId: string;
  sessionId: string;
  sourceStage: WorkflowStage;
  sourceSnapshotRefs: string[];
  sourceHash: string;
  researchSpec: Record<string, unknown>;
  dataSpec: Record<string, unknown>;
  analysisSpec: Record<string, unknown>;
  deliverables: Partial<Record<DeliverableKey, boolean>>;
  decisions: HandoffDecision[];
  unresolvedItems: string[];
  agents: AgentRuntimeDescriptor[];
  supersedesHandoffId?: string;
  createdAt: string;
}

export interface DataMergeReview {
  status: "waiting_for_review" | "approved";
  strategy: "canonical_union";
  inputSnapshotIds: string[];
  outputSnapshotId: string;
  identityKeys: string[];
  frequencyPolicy: string;
  unitPolicy: string;
  missingPolicy: string;
  lineageColumns: string[];
  reviewedAt?: string;
  reviewedBy?: "user" | "agent";
}

export interface RoundTripImportDraft {
  id: string;
  filename: string;
  workbookChecksum: string;
  manifestVerified: boolean;
  formulasMaterialized: boolean;
  sourceColumns: string[];
  mappings: Record<string, LogicalRole>;
  state: "mapping" | "validated" | "invalid";
  errors: string[];
  warnings: string[];
}

export interface DataWorkspaceState {
  schemaId: string;
  columns: DatasetColumn[];
  sourceRuns: SourceRun[];
  snapshots: DatasetSnapshot[];
  activeSnapshotId: string;
  approvedSnapshotId?: string;
  operations: DataPreparationOperation[];
  quality: {
    missingShare: number;
    duplicateKeys: number;
    observations: number;
    warning: string;
  };
  sourceMappingDraft?: {
    uploadId: string;
    filename: string;
    sourceColumns: string[];
    mappings: Record<string, LogicalRole>;
    state: "mapping" | "invalid";
    errors: string[];
  };
  roundTripDraft?: RoundTripImportDraft;
  activeRoundTripManifest?: {
    workbookChecksum: string;
    sourceSnapshotId: string;
    schemaId: string;
    manifestVerified: boolean;
  };
  lastExportedPackage?: {
    id?: string;
    filename: string;
    sheets: string[];
    snapshotId: string;
    schemaId: string;
    checksum: string;
    manifestLocked: boolean;
    downloadUrl?: string;
  };
  pendingAssistantProposal?: DataAssistantProposal;
  mergeReview?: DataMergeReview;
}

export type TransformationOperationKind =
  | "lag"
  | "lead"
  | "difference"
  | "yoy_growth"
  | "period_growth"
  | "log"
  | "rebase_index"
  | "unit_conversion"
  | "deflate"
  | "per_capita"
  | "frequency_conversion"
  | "merge"
  | "rolling_mean"
  | "seasonal_rule"
  | "group_aggregation";

export interface TargetSelector {
  inputRef: string;
  indicators: string[];
  entities: string[];
  fields: string[];
  periodStart?: string;
  periodEnd?: string;
  frequency?: string;
}

export interface PipelineOperation {
  id: string;
  kind: TransformationOperationKind;
  label: string;
  enabled: boolean;
  target: TargetSelector;
  parameters: Record<string, string | number | boolean>;
  inputRef: string;
  outputRef: string;
  status: "not_run" | "completed" | "stale" | "failed";
  requiresOperation?: TransformationOperationKind;
}

export type ModelKind = "descriptive" | "correlation" | "ols" | "adf" | "arima" | "sarimax" | "var";
export type ExecutableModelKind = "descriptive" | "correlation" | "ols" | "adf" | "arima" | "sarimax" | "var";
export type CovarianceKind = "nonrobust" | "HC1" | "HAC";

export interface ModelJob {
  id: string;
  kind: ModelKind;
  label: string;
  inputRef: string;
  variables: string[];
  dependentVariables: string[];
  independentVariables: string[];
  parameters: {
    missing: "drop";
    addConstant: boolean;
    covariance: CovarianceKind;
    maxLags: number;
    regression?: "c" | "ct" | "ctt" | "n";
    autolag?: "AIC" | "BIC" | "t-stat" | "none";
    orderP?: number;
    orderD?: number;
    orderQ?: number;
    seasonalP?: number;
    seasonalD?: number;
    seasonalQ?: number;
    seasonalPeriod?: number;
    trend?: "n" | "c" | "t" | "ct" | "ctt";
    forecastSteps?: number;
    confidenceLevel?: number;
    enforceStationarity?: boolean;
    enforceInvertibility?: boolean;
    lagSelection?: "fixed" | "aic" | "bic" | "hqic" | "fpe";
    includeIrf?: boolean;
    irfPeriods?: number;
    impulseVariables?: string[];
    orthogonalized?: boolean;
  };
  resultRef?: string;
  status: "not_run" | "completed" | "stale" | "failed";
}

export interface ModelResult {
  id: string;
  jobId: string;
  kind: ExecutableModelKind;
  inputSnapshotId: string;
  inputSnapshotHash: string;
  specificationHash: string;
  resultHash: string;
  sample: { observations: number; dropped: number };
  result: Record<string, unknown>;
  diagnostics: string[];
  warnings: string[];
  createdAt: string;
}

export interface AnalyticalBundle {
  id: string;
  inputDatasetId: string;
  finalDatasetRef: string;
  operationIds: string[];
  operationSnapshotRefs?: Record<string, string>;
  outputSnapshotRefs?: Record<string, string>;
  operationLineage?: Array<{
    operationId: string;
    operation: TransformationOperationKind;
    inputRef: string;
    outputRef: string;
    inputSnapshotId: string;
    inputSnapshotHash: string;
    outputSnapshotId: string;
    outputSnapshotHash: string;
    specificationHash: string;
    inputRows: number;
    outputRows: number;
  }>;
  modelResultIds: string[];
  pythonCodeRef?: string;
  stataCodeRef?: string;
  diagnostics: string[];
  warnings: string[];
  pythonCode?: string;
  stataCode?: string;
  createdAt: string;
}

export interface CodeArtifact {
  id: string;
  bundleId: string;
  language: "python" | "stata";
  filename: string;
  mediaType: string;
  checksum: string;
  specificationHash: string;
  warnings: string[];
  createdAt: string;
}

export interface PipelineEditSnapshot {
  operations: PipelineOperation[];
  models: ModelJob[];
  selectedOperationId?: string;
}

export interface AnalysisAssistantProposal {
  id: string;
  request: string;
  summary: string;
  operations: Array<{
    id: string;
    operation: TransformationOperationKind;
    parameters: Record<string, string | number | boolean>;
    indicators: string[];
    entities: string[];
    fields: string[];
    rationale: string;
  }>;
  models: Array<{
    id: string;
    model: ExecutableModelKind;
    variables: string[];
    dependentVariables: string[];
    independentVariables: string[];
    parameters: Record<string, string | number | boolean>;
    rationale: string;
  }>;
  modelRemovals: Array<{
    id: string;
    modelJobId: string;
    label: string;
    rationale: string;
  }>;
  targetStateHash: string;
  targetSnapshotId: string;
  agent?: AgentRuntimeDescriptor;
}

export interface PipelineState {
  operations: PipelineOperation[];
  models: ModelJob[];
  modelResults?: ModelResult[];
  modelResultHistory?: ModelResult[];
  codeArtifacts?: CodeArtifact[];
  codeArtifactHistory?: CodeArtifact[];
  selectedOperationId?: string;
  runStatus: "editing" | "running" | "completed" | "stale";
  lastValidationError?: string;
  lastBindingNotice?: string;
  bundle?: AnalyticalBundle;
  bundleHistory: AnalyticalBundle[];
  editHistory: PipelineEditSnapshot[];
  lastRunApprovedAt?: string;
  pendingAssistantProposal?: AnalysisAssistantProposal;
  draftSource?: "approved_plan" | "manual" | "assistant";
  sourcePlanSnapshotId?: string;
  outputGeneration?: {
    status: "failed" | "completed";
    attempt: number;
    bundleId: string;
    retryable: boolean;
    lastAttemptAt?: string;
    completedAt?: string;
    artifactSetId?: string;
    error?: {
      code: string;
      message: string;
      issues: Array<{
        attempt: number;
        path: string;
        code: string;
        message: string;
      }>;
    };
  };
}

export type ArtifactFormat = "xlsx" | "png" | "svg" | "csv" | "python" | "stata_do" | "json" | "report";

export interface Artifact {
  id: string;
  kind?: string;
  name: string;
  format: ArtifactFormat;
  mediaType?: string;
  description: string;
  hash: string;
  status: "ready" | "stale" | "frozen";
  exportSelected: boolean;
  createdAt?: string;
  specification?: Record<string, unknown>;
}

export interface OutputRevisionProposal {
  id: string;
  request: string;
  summary: string;
  artifactIds: string[];
  patches: OutputArtifactPatch[];
  reportDirectives?: ReportRevisionDirective[];
  targetArtifactSetHash: string;
  targetArtifactHashes: Record<string, string>;
}

export interface ReportRevisionDirective {
  directiveId: string;
  artifactId: string;
  targetSectionIds: string[];
  issue: string;
  preserveEvidenceRefs: string[];
  acceptanceCriteria: string[];
  requiresUpstreamStage: boolean;
  upstreamStage?: "data" | "transformation";
}

export interface OutputArtifactPatch {
  id: string;
  groupId?: string;
  artifactId: string;
  rationale: string;
  changes: Record<string, string | string[]>;
}

export interface OutputReviewFinding {
  id: string;
  ruleId: string;
  severity: "warning" | "fail";
  message: string;
  artifactIds: string[];
  blocking: boolean;
  proposedPatchIds: string[];
  evidenceRefs?: string[];
  requiresUpstreamStage?: boolean;
  upstreamStage?: "data" | "transformation";
}

export interface OutputReviewReport {
  id: string;
  status: "pass" | "warning" | "fail";
  providerProfile: string;
  modelId: string;
  targetArtifactSetHash: string;
  guidelineVersion: string;
  iteration: number;
  reviewedArtifactIds: string[];
  reviewRenderHashes: Record<string, string>;
  dataAccessId: string;
  inspectedRowCount: number;
  findings: OutputReviewFinding[];
  patches: OutputArtifactPatch[];
  reportDirectives?: ReportRevisionDirective[];
  semanticReportStatus?: "not_applicable" | "pass" | "fail" | "requires_upstream_stage";
  visualRubricVersion?: string | null;
  visualRubricHash?: string | null;
  visualRubricStatus?: "placeholder" | null;
  createdAt: string;
}

export interface OutputRevisionHistoryEntry {
  id: string;
  revision: number;
  request: string;
  acceptedPatchIds: string[];
  acceptedDirectiveIds?: string[];
  previousArtifactSetHash: string;
  artifactSetHash: string;
  artifacts: Array<{
    previousArtifactId: string;
    artifactId: string;
    name: string;
    format: "svg" | "csv" | "xlsx" | "report";
    previousHash: string;
    hash: string;
  }>;
  appliedAt: string;
  reviewIteration: number;
  reviewReportId: string;
  reviewStatus: "pass" | "warning" | "fail";
}

export interface OutputState {
  chartSelfChecks?: Array<{
    id: string;
    provider: string;
    model: string;
    artifactSetHash: string;
    status: "pass" | "fail";
    createdAt: string;
    rounds: Array<{ round: number; status: "pass" | "fail" | "error"; issues: string[] }>;
  }>;
  artifactSetId?: string;
  artifactSetHash?: string;
  artifacts: Artifact[];
  selectedArtifactId?: string;
  pendingProposal?: OutputRevisionProposal;
  artifactSpecifications?: Record<string, Record<string, unknown>>;
  reviewRenderHashes?: Record<string, string>;
  reviewRenderRefs?: Record<string, { id: string; hash: string; width: number; height: number; specHash: string; dataHash: string }>;
  preflightFindings?: OutputReviewFinding[];
  reviewReport?: OutputReviewReport;
  reviewHistory?: OutputReviewReport[];
  revisionHistory?: OutputRevisionHistoryEntry[];
  reviewIteration?: number;
  maxReviewIterations?: number;
  guidelineVersion: string;
  workbookTemplateVersion?: string;
  limitations?: string[];
  revisionCapability?: boolean;
  reportSemanticStatus?: "pending" | "not_applicable" | "pass" | "fail" | "requires_upstream_stage";
  reportDrafts?: Record<string, Record<string, unknown>>;
  evidenceLedgers?: Record<string, Array<Record<string, unknown>>>;
  manifestArtifactId?: string;
  finalizedAt?: string;
  artifactHistory: Artifact[][];
}

export interface WorkflowSession {
  id: string;
  title: string;
  request: string;
  status: WorkflowSessionStatus;
  activeStage: WorkflowStage;
  reachedStages: WorkflowStage[];
  stageHealth: Record<WorkflowStage, StageHealth>;
  createdAt: string;
  updatedAt: string;
  archived: boolean;
  clarification: ClarificationBatch;
  planThread: StageMessage[];
  outputThread: StageMessage[];
  stageThreads?: Partial<Record<WorkflowStage, StageMessage[]>>;
  handoffs?: StageHandoffEnvelopeV1[];
  currentHandoff?: StageHandoffEnvelopeV1;
  currentPlan?: PlanDraft;
  planSnapshots: PlanSnapshot[];
  currentPlanSnapshotId?: string;
  approvedPlanSnapshotId?: string;
  pendingPlanPatch?: PlanPatchProposal;
  data: DataWorkspaceState;
  pipeline: PipelineState;
  output: OutputState;
  nodes: WorkflowNode[];
  lastNotice?: string;
  lineage?: {
    relationship: "import" | "fork";
    sourceSessionId: string;
    sourceStatus: WorkflowSessionStatus;
    sourceArchiveChecksum: string;
    createdAt: string;
  };
}

export interface CommandMeta {
  commandId: string;
  idempotencyKey: string;
  sessionId: string;
  expectedActiveStage: WorkflowStage;
  expectedSnapshotHash: string;
  requestedAt: string;
  actor: "user" | "agent";
}

export type WorkflowCommand =
  | { type: "request_plan_clarification" }
  | { type: "submit_clarification"; answers: Record<string, string> }
  | { type: "confirm_geography"; resolutionId: string }
  | { type: "save_plan"; changes: Partial<PlanDraft>; actor?: "user" | "agent" }
  | { type: "propose_plan_patch"; request: string }
  | { type: "apply_plan_patch"; acceptedFields?: string[] }
  | { type: "reject_plan_patch" }
  | { type: "plan_next" }
  | { type: "prepare_round_trip_export" }
  | { type: "start_round_trip_import"; filename: string }
  | { type: "map_round_trip_column"; sourceColumn: string; role: LogicalRole }
  | { type: "validate_round_trip" }
  | { type: "commit_round_trip" }
  | { type: "apply_data_operation"; operation: DataOperationKind; parameters?: Record<string, unknown> }
  | { type: "propose_data_assistance"; request: string }
  | { type: "apply_data_assistance"; acceptedItemIds: string[] }
  | { type: "reject_data_assistance" }
  | { type: "map_source_column"; sourceColumn: string; role: LogicalRole }
  | { type: "validate_source_mapping" }
  | { type: "undo_data_operation" }
  | { type: "approve_data_merge" }
  | { type: "data_next" }
  | { type: "add_pipeline_operation"; operation: TransformationOperationKind }
  | { type: "move_pipeline_operation"; operationId: string; direction: "up" | "down" }
  | { type: "toggle_pipeline_operation"; operationId: string }
  | { type: "delete_pipeline_operation"; operationId: string }
  | { type: "undo_pipeline_edit" }
  | { type: "select_pipeline_operation"; operationId: string }
  | { type: "update_pipeline_target"; operationId: string; target: Partial<TargetSelector> }
  | { type: "update_pipeline_parameters"; operationId: string; parameters: PipelineOperation["parameters"] }
  | { type: "add_model_job"; model: ModelKind }
  | { type: "update_model_input"; modelId: string; inputRef: string }
  | {
      type: "update_model_specification";
      modelId: string;
      variables: string[];
      dependentVariables: string[];
      independentVariables: string[];
      parameters: ModelJob["parameters"];
    }
  | { type: "delete_model_job"; modelId: string }
  | { type: "start_pipeline_revision" }
  | { type: "run_pipeline" }
  | { type: "retry_output_generation" }
  | { type: "propose_analysis_assistance"; request: string }
  | { type: "apply_analysis_assistance"; acceptedItemIds: string[] }
  | { type: "reject_analysis_assistance" }
  | { type: "confirm_decisions"; decisionIds: string[] }
  | { type: "resolve_decision"; decisionId: string; value: string }
  | { type: "select_artifact"; artifactId: string }
  | { type: "toggle_artifact_export"; artifactId: string }
  | { type: "request_output_review" }
  | { type: "propose_output_revision"; request: string }
  | { type: "apply_output_revision"; acceptedPatchIds: string[]; acceptedDirectiveIds?: string[] }
  | { type: "reject_output_revision" }
  | { type: "finalize_output"; acceptWarnings?: boolean };

export interface WorkflowCommandEnvelope {
  meta: CommandMeta;
  command: WorkflowCommand;
}

export const STAGE_LABELS: Record<WorkflowStage, string> = {
  plan: "Plan",
  data: "Data",
  transformation: "Transformation",
  output: "Output",
};

export const SESSION_STATUS_LABELS: Record<WorkflowSessionStatus, string> = {
  clarifying: "Clarifying scope",
  plan_review: "Plan review",
  acquiring: "Acquiring data",
  data_review: "Data review",
  pipeline_editing: "Pipeline editing",
  pipeline_running: "Pipeline running",
  output_generating: "Generating outputs",
  output_review: "Output review",
  completed: "Completed",
  failed: "Needs attention",
  cancelled: "Cancelled",
};

export const DELIVERABLE_LABELS: Record<DeliverableKey, string> = {
  charts: "Charts",
  tables: "Tables",
  cleanData: "Clean data",
  python: "Python",
  stata: "Stata",
  researchReport: "Research report",
};
