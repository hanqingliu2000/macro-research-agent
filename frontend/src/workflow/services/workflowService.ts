import type { WorkflowCommand, WorkflowSession, WorkflowStage } from "../domain/types";

export interface WorkflowConflictState {
  message: string;
  currentStage: WorkflowStage;
  currentSnapshotHash: string;
}

export class WorkflowHttpConflict extends Error {
  constructor(public readonly conflict: WorkflowConflictState) {
    super(conflict.message);
  }
}

export interface WorkflowUploadSummary {
  upload_id: string;
  filename: string;
  checksum: string;
  byte_size: number;
  tables: Array<{
    name: string;
    row_count: number;
    column_count: number;
    columns: Array<{ name: string; inferred_type: string }>;
  }>;
}

export interface DatasetPreviewPage {
  snapshot_id: string;
  offset: number;
  limit: number;
  total_rows: number;
  rows: Array<Record<string, string | number | null>>;
}

export interface PipelinePreviewPage {
  operation_id: string | null;
  offset: number;
  limit: number;
  total_rows: number;
  columns: string[];
  rows: Array<Record<string, string | number | null>>;
}

export interface PipelineCodeContent {
  id: string;
  language: "python" | "stata";
  filename: string;
  checksum: string;
  specification_hash: string;
  content: string;
}

export interface OutputArtifactPreview {
  id: string;
  format: string;
  previewKind?: "table" | "text" | "workbook" | "image";
  columns?: string[];
  rows?: Array<Record<string, string | number | null>>;
  content?: string;
  sheetNames?: string[];
}

export interface ArtifactComparisonReport {
  schema_version: "mra-artifact-comparison-v1";
  baseline_artifact_id: string;
  current_artifact_id: string;
  artifact_format: string;
  status: "unchanged" | "presentation_changed" | "data_changed" | "incompatible";
  baseline_hash: string;
  current_hash: string;
  hash_changed: boolean;
  specification_changes: Array<{ field: string; before: unknown; after: unknown }>;
  value_comparison: {
    status: "unchanged" | "changed" | "unavailable";
    source: "csv" | "workbook" | "specification" | "unavailable";
    baseline_value_hash?: string;
    current_value_hash?: string;
    baseline_row_count?: number;
    current_row_count?: number;
    baseline_column_count?: number;
    current_column_count?: number;
    added_row_count?: number;
    removed_row_count?: number;
    changed_sheets: string[];
  };
}

export interface WorkflowService {
  initialSessions?(): WorkflowSession[];
  listSessions(): Promise<WorkflowSession[]>;
  createSession(request: string): Promise<WorkflowSession>;
  setSessionDeleted(sessionId: string, deleted: boolean): Promise<WorkflowSession>;
  importSession(file: File): Promise<WorkflowSession>;
  forkSession(sessionId: string, title?: string): Promise<WorkflowSession>;
  sessionArchiveDownloadUrl(sessionId: string): string;
  uploadSource(sessionId: string, file: File): Promise<WorkflowUploadSummary>;
  importRoundTrip(session: WorkflowSession, file: File): Promise<WorkflowSession>;
  previewData(sessionId: string, offset: number, limit: number): Promise<DatasetPreviewPage>;
  previewPipeline(
    sessionId: string,
    operationId: string | undefined,
    offset: number,
    limit: number,
  ): Promise<PipelinePreviewPage>;
  getPipelineCode(sessionId: string, artifactId: string): Promise<PipelineCodeContent>;
  getOutputArtifactPreview(sessionId: string, artifactId: string): Promise<OutputArtifactPreview>;
  compareOutputArtifacts(
    sessionId: string,
    currentArtifactId: string,
    baselineArtifactId: string,
  ): Promise<ArtifactComparisonReport>;
  outputArtifactDownloadUrl(sessionId: string, artifactId: string): string;
  execute(session: WorkflowSession, command: WorkflowCommand): Promise<WorkflowSession>;
  reset(): Promise<WorkflowSession[]>;
}
