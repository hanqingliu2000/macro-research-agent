export type AgentSessionStatus =
  | "requested"
  | "queued"
  | "running"
  | "waiting_for_user"
  | "paused"
  | "budget_exhausted"
  | "awaiting_final_confirmation"
  | "clarifying"
  | "routing"
  | "acquiring"
  | "transforming"
  | "analyzing"
  | "reporting"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentNodeKind =
  | "agent_request"
  | "attachment_inspection"
  | "clarification_batch"
  | "route_decision"
  | "data_acquisition"
  | "transformation"
  | "model_execution"
  | "report_generation"
  | "final_response";

export interface AgentAttachment {
  id: string;
  name: string;
  mediaType: string;
  size: number;
}

export interface AgentMessage {
  id: string;
  role: "user" | "agent";
  body: string;
  createdAt: string;
  label?: string;
}

export interface AgentClarificationQuestion {
  id: string;
  prompt: string;
  options: string[];
}

export interface AgentClarification {
  questions: AgentClarificationQuestion[];
  answers: Record<string, string>;
  submitted: boolean;
}

export interface AgentStep {
  id: string;
  nodeKind: AgentNodeKind;
  label: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  summary: string;
}

export interface AgentDataRow {
  economy: string;
  period: string;
  inflation: number;
  policyRate: number;
}

export interface AgentArtifact {
  id: string;
  name: string;
  format: "xlsx" | "csv" | "png" | "svg" | "report" | "parquet" | "json" | "python" | "stata_do";
  description: string;
  href?: string;
  hash?: string;
}

export interface AgentResult {
  conclusion: string;
  findings: string[];
  caveats: string[];
  data: AgentDataRow[];
  table?: { columns: string[]; rows: Array<Record<string, unknown>>; total_rows: number };
  pythonCode: string;
  stataCode: string;
  artifacts: AgentArtifact[];
  sources: Array<{ provider: string; dataset: string; retrievedAt: string }>;
}

export interface AgentSession {
  id: string;
  title: string;
  request: string;
  status: AgentSessionStatus;
  createdAt: string;
  updatedAt: string;
  attachments: AgentAttachment[];
  messages: AgentMessage[];
  clarification: AgentClarification;
  steps: AgentStep[];
  result?: AgentResult;
  remote?: BackendAgentRun;
}

export interface BackendAgentRun {
  recovery?: {
    code: string; message: string;
    action: "retry_failed_task" | "provide_input" | "start_linked_run" | "extend_budget" | "repair_evidence";
    can_retry: boolean; requires_provider_confirmation: boolean; failed_step: string;
    remaining: { task_calls: number | null; task_attempts: number | null; phase_attempts: number | null;
      model_calls: number; tokens: number; active_seconds: number; output_candidates: number; formal_reviews: number };
  } | null;
  active_role?: { label: string; provider: string; model: string; state: string };
  run_id: string;
  session_id: string;
  request: string;
  status: AgentSessionStatus;
  phase: string;
  version: number;
  created_at: string;
  updated_at: string;
  clarification?: { questions: Array<{ question_id: string; prompt: string; options: string[] }> };
  answers: Record<string, string>;
  authorizations?: Array<{ envelope_id: string; version: number }>;
  attachments: Array<{ id: string; name: string; row_count: number }>;
  messages: Array<{ id: string; role: "user" | "agent"; body: string; created_at: string }>;
  ledger: { limits: Record<string, number>; used: Record<string, number>; reservations: Record<string, Record<string, number>> };
  nodes: Array<{ node_id: string; kind: string; status: string; input_refs: string[]; output_refs: string[] }>;
  data: { sources?: Array<{ provenance: { provider?: string; dataset?: string; retrieved_at?: string } }> };
  output: {
    history?: unknown[];
    manifest?: { id: string; hash: string };
    candidate?: {
      candidate: number;
      artifact_set_hash: string;
      artifacts: Array<{ id: string; name: string; format: AgentArtifact["format"]; description: string; hash: string }>;
      drafts: Record<string, { sections: Array<{ heading: string; body: string }>; claims: Array<{ statement: string }>; limitations: string[] }>;
      self_checks: Array<{ round: number; status: string; issues: string[]; provider: string; model: string }>;
      review?: { status: string; provider_profile: string; model_id: string; semantic_report_status: string; findings: Array<{ rule_id: string; message: string; severity: string }> };
    };
  };
  intervention?: { reason: string; message: string; options: string[]; details_ref?: string };
  error?: { code: string; message: string; details_ref: string };
  preview?: AgentResult["table"];
}

export const AGENT_STATUS_LABELS: Record<AgentSessionStatus, string> = {
  requested: "Request captured",
  queued: "Queued",
  running: "Research running",
  waiting_for_user: "Your input is needed",
  paused: "Paused",
  budget_exhausted: "Budget exhausted",
  awaiting_final_confirmation: "Ready for final confirmation",
  clarifying: "Clarifying scope",
  routing: "Selecting tools",
  acquiring: "Acquiring data",
  transforming: "Preparing data",
  analyzing: "Running analysis",
  reporting: "Preparing outputs",
  completed: "Completed",
  failed: "Needs attention",
  cancelled: "Cancelled",
};
