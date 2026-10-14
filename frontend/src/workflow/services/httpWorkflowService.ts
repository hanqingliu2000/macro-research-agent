import { makeCommandEnvelope } from "../domain/workflowEngine";
import type {
  WorkflowCommand,
  WorkflowCommandEnvelope,
  WorkflowSession,
} from "../domain/types";
import {
  WorkflowHttpConflict,
  type WorkflowConflictState,
  type WorkflowService,
} from "./workflowService";

interface StoredSessionResponse {
  session: WorkflowSession;
  projection: {
    current_snapshot_hash: string;
  };
}

interface CommandResponse extends StoredSessionResponse {
  idempotent_replay: boolean;
}

interface ConflictResponse {
  detail?: {
    message?: string;
    current_stage?: WorkflowConflictState["currentStage"];
    current_snapshot_hash?: string;
  };
}

interface ApiErrorResponse {
  detail?: string | { code?: string; message?: string };
}

const API_ERROR_LABELS: Record<string, string> = {
  invalid_model_contract: "Invalid model contract",
  provider_unavailable: "AI provider unavailable",
  connector_unavailable: "Data connector unavailable",
  handoff_incomplete: "Stage handoff incomplete",
  deterministic_contract_violation: "Offline test contract violation",
  invalid_report_contract: "Invalid report contract",
};

function displayApiError(status: number, detail?: ApiErrorResponse["detail"]) {
  const rawMessage = typeof detail === "string" ? detail : detail?.message;
  const prefixedCode = typeof detail === "string" ? /^\[([^\]]+)\]\s*/.exec(detail)?.[1] : undefined;
  const code = typeof detail === "string" ? prefixedCode : detail?.code;
  const message = prefixedCode && rawMessage ? rawMessage.replace(/^\[[^\]]+\]\s*/, "") : rawMessage;
  const category = code ? API_ERROR_LABELS[code] ?? code : undefined;
  if (category && message) return `${category} (${code}): ${message}`;
  if (message) return `Workflow API request failed (${status}): ${message}`;
  return `Workflow API request failed (${status}).`;
}

const PLAN_COMMAND_TYPES = new Set([
  "request_plan_clarification",
  "submit_clarification",
  "confirm_geography",
  "save_plan",
  "propose_plan_patch",
  "apply_plan_patch",
  "reject_plan_patch",
  "plan_next",
]);

const DATA_COMMAND_TYPES = new Set([
  "apply_data_operation",
  "map_source_column",
  "validate_source_mapping",
  "undo_data_operation",
  "approve_data_merge",
  "map_round_trip_column",
  "validate_round_trip",
  "prepare_round_trip_export",
  "commit_round_trip",
  "data_next",
  "propose_data_assistance",
  "apply_data_assistance",
  "reject_data_assistance",
]);

const PIPELINE_COMMAND_TYPES = new Set([
  "add_pipeline_operation",
  "move_pipeline_operation",
  "toggle_pipeline_operation",
  "delete_pipeline_operation",
  "undo_pipeline_edit",
  "select_pipeline_operation",
  "update_pipeline_target",
  "update_pipeline_parameters",
  "add_model_job",
  "update_model_input",
  "update_model_specification",
  "delete_model_job",
  "start_pipeline_revision",
  "run_pipeline",
  "retry_output_generation",
  "propose_analysis_assistance",
  "apply_analysis_assistance",
  "reject_analysis_assistance",
]);

const OUTPUT_COMMAND_TYPES = new Set([
  "select_artifact",
  "toggle_artifact_export",
  "request_output_review",
  "propose_output_revision",
  "apply_output_revision",
  "reject_output_revision",
  "finalize_output",
]);

const HANDOFF_COMMAND_TYPES = new Set(["confirm_decisions", "resolve_decision"]);

export function serializeCommandEnvelope(envelope: WorkflowCommandEnvelope) {
  return {
    command_id: envelope.meta.commandId,
    idempotency_key: envelope.meta.idempotencyKey,
    session_id: envelope.meta.sessionId,
    expected_stage: envelope.meta.expectedActiveStage,
    expected_snapshot_hash: envelope.meta.expectedSnapshotHash,
    actor: envelope.meta.actor,
    requested_at: envelope.meta.requestedAt,
  };
}

export class HttpWorkflowService implements WorkflowService {
  private readonly snapshotHashes = new Map<string, string>();

  constructor(private readonly baseUrl = "/api/v1/workflow") {}

  private async json<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
    const response = await fetch(input, init);
    if (response.status === 409) {
      const body = (await response.json()) as ConflictResponse;
      throw new WorkflowHttpConflict({
        message: body.detail?.message ?? "The Workflow session changed on the server.",
        currentStage: body.detail?.current_stage ?? "plan",
        currentSnapshotHash: body.detail?.current_snapshot_hash ?? "unknown",
      });
    }
    if (!response.ok) {
      let detail: ApiErrorResponse["detail"];
      try {
        const body = (await response.json()) as ApiErrorResponse;
        detail = body.detail;
      } catch {
        // Preserve the status-only fallback when the server did not return JSON.
      }
      throw new Error(displayApiError(response.status, detail));
    }
    return (await response.json()) as T;
  }

  async listSessions() {
    const records = await this.json<StoredSessionResponse[]>(`${this.baseUrl}/sessions`);
    records.forEach((record) => {
      this.snapshotHashes.set(record.session.id, record.projection.current_snapshot_hash);
    });
    return records.map((record) => record.session);
  }

  async createSession(request: string) {
    const record = await this.json<StoredSessionResponse>(`${this.baseUrl}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request }),
    });
    this.snapshotHashes.set(record.session.id, record.projection.current_snapshot_hash);
    return record.session;
  }

  async setSessionDeleted(sessionId: string, deleted: boolean) {
    const record = await this.json<StoredSessionResponse>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}${deleted ? "" : "/restore"}`,
      { method: deleted ? "DELETE" : "POST" },
    );
    this.snapshotHashes.set(sessionId, record.projection.current_snapshot_hash);
    return record.session;
  }

  async importSession(file: File) {
    const form = new FormData();
    form.append("file", file);
    const record = await this.json<StoredSessionResponse>(`${this.baseUrl}/sessions/import`, {
      method: "POST",
      body: form,
    });
    this.snapshotHashes.set(record.session.id, record.projection.current_snapshot_hash);
    return record.session;
  }

  async forkSession(sessionId: string, title?: string) {
    const record = await this.json<StoredSessionResponse>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/fork`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      },
    );
    this.snapshotHashes.set(record.session.id, record.projection.current_snapshot_hash);
    return record.session;
  }

  sessionArchiveDownloadUrl(sessionId: string) {
    return `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/archive`;
  }

  async uploadSource(sessionId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return this.json<import("./workflowService").WorkflowUploadSummary>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/sources/uploads`,
      { method: "POST", body: form },
    );
  }

  async importRoundTrip(session: WorkflowSession, file: File) {
    const command = { type: "start_round_trip_import", filename: file.name } as const;
    const envelope = makeCommandEnvelope(session, command);
    envelope.meta.expectedSnapshotHash =
      this.snapshotHashes.get(session.id) ?? envelope.meta.expectedSnapshotHash;
    const form = new FormData();
    form.append("meta_json", JSON.stringify(serializeCommandEnvelope(envelope)));
    form.append("file", file);
    const result = await this.json<CommandResponse>(
      `${this.baseUrl}/sessions/${encodeURIComponent(session.id)}/data/roundtrip/imports`,
      { method: "POST", body: form },
    );
    this.snapshotHashes.set(result.session.id, result.projection.current_snapshot_hash);
    return result.session;
  }

  async previewData(sessionId: string, offset: number, limit: number) {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    return this.json<import("./workflowService").DatasetPreviewPage>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/data/preview?${query}`,
    );
  }

  async previewPipeline(
    sessionId: string,
    operationId: string | undefined,
    offset: number,
    limit: number,
  ) {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (operationId) query.set("operation_id", operationId);
    return this.json<import("./workflowService").PipelinePreviewPage>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/pipeline/preview?${query}`,
    );
  }

  async getPipelineCode(sessionId: string, artifactId: string) {
    return this.json<import("./workflowService").PipelineCodeContent>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/pipeline/code/${encodeURIComponent(artifactId)}`,
    );
  }

  async getOutputArtifactPreview(sessionId: string, artifactId: string) {
    return this.json<import("./workflowService").OutputArtifactPreview>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/output/artifacts/${encodeURIComponent(artifactId)}`,
    );
  }

  async compareOutputArtifacts(
    sessionId: string,
    currentArtifactId: string,
    baselineArtifactId: string,
  ) {
    return this.json<import("./workflowService").ArtifactComparisonReport>(
      `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/output/artifacts/${encodeURIComponent(currentArtifactId)}/compare/${encodeURIComponent(baselineArtifactId)}`,
    );
  }

  outputArtifactDownloadUrl(sessionId: string, artifactId: string) {
    return `${this.baseUrl}/sessions/${encodeURIComponent(sessionId)}/output/artifacts/${encodeURIComponent(artifactId)}/download`;
  }

  async execute(session: WorkflowSession, command: WorkflowCommand) {
    const envelope = makeCommandEnvelope(session, command);
    envelope.meta.expectedSnapshotHash =
      this.snapshotHashes.get(session.id) ?? envelope.meta.expectedSnapshotHash;
    if (HANDOFF_COMMAND_TYPES.has(command.type)) {
      const result = await this.json<CommandResponse>(
        `${this.baseUrl}/sessions/${encodeURIComponent(session.id)}/handoff/commands`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ meta: serializeCommandEnvelope(envelope), command }),
        },
      );
      this.snapshotHashes.set(result.session.id, result.projection.current_snapshot_hash);
      return result.session;
    }
    if (PLAN_COMMAND_TYPES.has(command.type)) {
      const result = await this.json<CommandResponse>(
        `${this.baseUrl}/sessions/${encodeURIComponent(session.id)}/plan/commands`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ meta: serializeCommandEnvelope(envelope), command }),
        },
      );
      this.snapshotHashes.set(result.session.id, result.projection.current_snapshot_hash);
      return result.session;
    }
    if (DATA_COMMAND_TYPES.has(command.type)) {
      const result = await this.json<CommandResponse>(
        `${this.baseUrl}/sessions/${encodeURIComponent(session.id)}/data/commands`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ meta: serializeCommandEnvelope(envelope), command }),
        },
      );
      this.snapshotHashes.set(result.session.id, result.projection.current_snapshot_hash);
      return result.session;
    }
    if (PIPELINE_COMMAND_TYPES.has(command.type)) {
      const result = await this.json<CommandResponse>(
        `${this.baseUrl}/sessions/${encodeURIComponent(session.id)}/pipeline/commands`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ meta: serializeCommandEnvelope(envelope), command }),
        },
      );
      this.snapshotHashes.set(result.session.id, result.projection.current_snapshot_hash);
      return result.session;
    }
    if (OUTPUT_COMMAND_TYPES.has(command.type)) {
      const result = await this.json<CommandResponse>(
        `${this.baseUrl}/sessions/${encodeURIComponent(session.id)}/output/commands`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ meta: serializeCommandEnvelope(envelope), command }),
        },
      );
      this.snapshotHashes.set(result.session.id, result.projection.current_snapshot_hash);
      return result.session;
    }
    throw new Error(`No typed HTTP endpoint is registered for ${command.type}.`);
  }

  async reset() {
    return this.listSessions();
  }
}
