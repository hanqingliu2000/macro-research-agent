import { createContext, useContext } from "react";

import type { WorkflowCommand, WorkflowSession } from "../domain/types";
import type { WorkflowConflictState } from "../services/workflowService";
import type { ArtifactComparisonReport, DatasetPreviewPage, OutputArtifactPreview, PipelineCodeContent, PipelinePreviewPage, WorkflowUploadSummary } from "../services/workflowService";

export interface WorkflowContextValue {
  sessions: WorkflowSession[];
  loading: boolean;
  pending: boolean;
  error?: string;
  conflict?: WorkflowConflictState;
  createSession(request: string): Promise<WorkflowSession>;
  setSessionDeleted(sessionId: string, deleted: boolean): Promise<WorkflowSession>;
  importSession(file: File): Promise<WorkflowSession>;
  forkSession(sessionId: string, title?: string): Promise<WorkflowSession>;
  sessionArchiveDownloadUrl(sessionId: string): string;
  uploadSource(sessionId: string, file: File): Promise<WorkflowUploadSummary>;
  importRoundTrip(sessionId: string, file: File): Promise<WorkflowSession | undefined>;
  previewData(sessionId: string, offset: number, limit: number): Promise<DatasetPreviewPage>;
  previewPipeline(sessionId: string, operationId: string | undefined, offset: number, limit: number): Promise<PipelinePreviewPage>;
  getPipelineCode(sessionId: string, artifactId: string): Promise<PipelineCodeContent>;
  getOutputArtifactPreview(sessionId: string, artifactId: string): Promise<OutputArtifactPreview>;
  compareOutputArtifacts(sessionId: string, currentArtifactId: string, baselineArtifactId: string): Promise<ArtifactComparisonReport>;
  outputArtifactDownloadUrl(sessionId: string, artifactId: string): string;
  execute(sessionId: string, command: WorkflowCommand): Promise<WorkflowSession | undefined>;
  resetDemo(): Promise<void>;
  reload(): Promise<void>;
}

export const WorkflowContext = createContext<WorkflowContextValue | null>(null);

export function useWorkflow() {
  const context = useContext(WorkflowContext);
  if (!context) throw new Error("useWorkflow must be used inside WorkflowProvider");
  return context;
}
