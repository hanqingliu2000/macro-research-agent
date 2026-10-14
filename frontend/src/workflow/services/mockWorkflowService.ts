import {
  createWorkflowSession,
  executeWorkflowCommand,
  makeCommandEnvelope,
} from "../domain/workflowEngine";
import type { WorkflowCommand, WorkflowSession } from "../domain/types";
import { seedWorkflowSessions } from "../mock/fixtures";
import type { WorkflowService } from "./workflowService";

export const WORKFLOW_SESSION_STORAGE_KEY =
  "macro-research-agent.workflow.mock.sessions.v3";

function storageAvailable() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export class MockWorkflowService implements WorkflowService {
  private read(): WorkflowSession[] {
    if (!storageAvailable()) return seedWorkflowSessions();
    const stored = window.localStorage.getItem(WORKFLOW_SESSION_STORAGE_KEY);
    if (!stored) {
      const seeded = seedWorkflowSessions();
      this.write(seeded);
      return seeded;
    }
    try {
      return JSON.parse(stored) as WorkflowSession[];
    } catch {
      return this.resetSync();
    }
  }

  private write(sessions: WorkflowSession[]) {
    if (storageAvailable()) {
      window.localStorage.setItem(WORKFLOW_SESSION_STORAGE_KEY, JSON.stringify(sessions));
    }
  }

  private resetSync() {
    const seeded = seedWorkflowSessions();
    this.write(seeded);
    return seeded;
  }

  initialSessions() {
    return this.read();
  }

  async listSessions() {
    return this.read();
  }

  async createSession(request: string) {
    const session = createWorkflowSession(request);
    this.write([session, ...this.read()]);
    return session;
  }

  async setSessionDeleted(sessionId: string, deleted: boolean) {
    const sessions = this.read();
    const session = sessions.find((item) => item.id === sessionId);
    if (!session) throw new Error("Session not found.");
    session.archived = deleted;
    session.updatedAt = new Date().toISOString();
    this.write(sessions);
    return session;
  }

  async importSession(file: File) {
    void file;
    const source = this.read()[0] ?? createWorkflowSession("Imported research session");
    const now = new Date().toISOString();
    const session = structuredClone(source);
    session.id = `workflow-import-${Date.now()}`;
    session.updatedAt = now;
    session.lineage = {
      relationship: "import",
      sourceSessionId: source.id,
      sourceStatus: source.status,
      sourceArchiveChecksum: "mock:archive",
      createdAt: now,
    };
    this.write([session, ...this.read()]);
    return session;
  }

  async forkSession(sessionId: string, title?: string) {
    const source = this.read().find((item) => item.id === sessionId);
    if (!source || source.status !== "completed") {
      throw new Error("Only a completed Workflow session can be continued.");
    }
    const now = new Date().toISOString();
    const session = structuredClone(source);
    session.id = `workflow-fork-${Date.now()}`;
    session.title = title?.trim() || `${source.title} — continued`;
    session.status = "output_review";
    session.activeStage = "output";
    session.stageHealth.output = "current";
    session.updatedAt = now;
    session.output.finalizedAt = undefined;
    session.output.manifestArtifactId = undefined;
    session.output.reviewReport = undefined;
    session.output.pendingProposal = undefined;
    session.output.artifacts = session.output.artifacts
      .filter((item) => item.kind !== "manifest")
      .map((item) => ({ ...item, status: "ready" }));
    session.lineage = {
      relationship: "fork",
      sourceSessionId: source.id,
      sourceStatus: source.status,
      sourceArchiveChecksum: "mock:archive",
      createdAt: now,
    };
    this.write([session, ...this.read()]);
    return session;
  }

  sessionArchiveDownloadUrl(sessionId: string) {
    return `#mock-session-archive-${sessionId}`;
  }

  async uploadSource(_sessionId: string, file: File) {
    return {
      upload_id: `mock-upload-${file.name}`,
      filename: file.name,
      checksum: `mock:${file.size}`,
      byte_size: file.size,
      tables: [],
    };
  }

  async importRoundTrip(session: WorkflowSession, file: File) {
    return this.execute(session, { type: "start_round_trip_import", filename: file.name });
  }

  async previewData(sessionId: string, offset: number, limit: number) {
    const session = this.read().find((item) => item.id === sessionId);
    const snapshot = session?.data.snapshots.find(
      (item) => item.id === session.data.activeSnapshotId,
    );
    const rows = snapshot?.rows ?? [];
    return {
      snapshot_id: snapshot?.id ?? "",
      offset,
      limit,
      total_rows: rows.length,
      rows: rows.slice(offset, offset + limit),
    };
  }

  async previewPipeline(
    sessionId: string,
    operationId: string | undefined,
    offset: number,
    limit: number,
  ) {
    const session = this.read().find((item) => item.id === sessionId);
    const active = session?.data.snapshots.find(
      (item) => item.id === session.data.activeSnapshotId,
    );
    const rows = (active?.rows ?? []).map((row) => ({
      ...row,
      derived_preview: row.value === null ? null : Number(row.value),
    }));
    return {
      operation_id: operationId ?? null,
      offset,
      limit,
      total_rows: rows.length,
      columns: [...(session?.data.columns.map((column) => column.id) ?? []), "derived_preview"],
      rows: rows.slice(offset, offset + limit),
    };
  }

  async getPipelineCode(_sessionId: string, artifactId: string) {
    return {
      id: artifactId,
      language: "python" as const,
      filename: "reproduce_research.py",
      checksum: "mock:code",
      specification_hash: "mock:specification",
      content: "# Mock adapter code preview",
    };
  }

  async getOutputArtifactPreview(sessionId: string, artifactId: string) {
    const session = this.read().find((item) => item.id === sessionId);
    const artifact = session?.output.artifacts.find((item) => item.id === artifactId);
    if (artifact?.format === "png" || artifact?.format === "svg") {
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500"><rect width="100%" height="100%" fill="#fff"/><text x="48" y="64" font-family="Arial" font-size="24">Deterministic fixture chart</text><path d="M70 400 L240 300 L410 335 L580 190 L760 145" fill="none" stroke="#1976d2" stroke-width="5"/></svg>';
      return { id: artifactId, format: artifact.format, previewKind: "image" as const, content: `data:image/svg+xml,${encodeURIComponent(svg)}` };
    }
    if (artifact?.format === "python" || artifact?.format === "stata_do" || artifact?.format === "report") {
      return { id: artifactId, format: artifact.format, previewKind: "text" as const, content: artifact.description };
    }
    const rows = session?.data.snapshots.find((item) => item.id === session.data.activeSnapshotId)?.rows.slice(0, 12) ?? [];
    return { id: artifactId, format: artifact?.format ?? "csv", previewKind: "table" as const, columns: rows.length ? Object.keys(rows[0]) : [], rows };
  }

  async compareOutputArtifacts(
    sessionId: string,
    currentArtifactId: string,
    baselineArtifactId: string,
  ) {
    const session = this.read().find((item) => item.id === sessionId);
    const artifacts = [
      ...(session?.output.artifacts ?? []),
      ...(session?.output.artifactHistory.flat() ?? []),
    ];
    const current = artifacts.find((item) => item.id === currentArtifactId);
    const baseline = artifacts.find((item) => item.id === baselineArtifactId);
    const hashChanged = current?.hash !== baseline?.hash;
    return {
      schema_version: "mra-artifact-comparison-v1" as const,
      baseline_artifact_id: baselineArtifactId,
      current_artifact_id: currentArtifactId,
      artifact_format: current?.format ?? "unknown",
      status: hashChanged ? ("presentation_changed" as const) : ("unchanged" as const),
      baseline_hash: baseline?.hash ?? "",
      current_hash: current?.hash ?? "",
      hash_changed: hashChanged,
      specification_changes: [],
      value_comparison: {
        status: "unchanged" as const,
        source: "specification" as const,
        baseline_value_hash: "mock:approved-data",
        current_value_hash: "mock:approved-data",
        changed_sheets: [],
      },
    };
  }

  outputArtifactDownloadUrl(_sessionId: string, artifactId: string) {
    return `#mock-download-${artifactId}`;
  }

  async execute(session: WorkflowSession, command: WorkflowCommand) {
    const updated = executeWorkflowCommand(session, makeCommandEnvelope(session, command));
    this.write(this.read().map((item) => (item.id === session.id ? updated : item)));
    return updated;
  }

  async reset() {
    return this.resetSync();
  }
}
