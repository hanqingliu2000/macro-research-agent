import type { AgentArtifact, AgentAttachment, AgentSession, BackendAgentRun } from "../domain/types";
import type { AgentService } from "../mock/agentService";

const baseUrl = import.meta.env.VITE_AGENT_API_BASE_URL ?? "";

export function agentRunPath(run: BackendAgentRun) {
  return `${baseUrl}/api/v1/agent/sessions/${run.session_id}/runs/${run.run_id}`;
}

export function agentAdminPath(run: BackendAgentRun) {
  return `${baseUrl}/api/v1/admin/agent/sessions/${run.session_id}/runs/${run.run_id}`;
}

function project(run: BackendAgentRun): AgentSession {
  const candidate = run.output.candidate;
  const draft = Object.values(candidate?.drafts ?? {})[0];
  const root = agentRunPath(run);
  return {
    id: run.session_id, title: run.request.slice(0, 100), request: run.request,
    status: run.status, createdAt: run.created_at, updatedAt: run.updated_at,
    attachments: run.attachments.map(item => ({ id: item.id, name: item.name, mediaType: "data", size: item.row_count })),
    messages: run.messages.map(item => ({ id: item.id, role: item.role, body: item.body, createdAt: item.created_at })),
    clarification: { questions: (run.clarification?.questions ?? []).map(question => ({
      id: question.question_id, prompt: question.prompt, options: question.options })),
      answers: run.answers, submitted: Boolean(run.authorizations?.length) },
    steps: run.nodes.map(node => ({ id: node.node_id, nodeKind: "route_decision", label: node.kind.replaceAll(":", " · "),
      status: node.status === "running" ? "in_progress" : node.status === "completed" ? "completed"
        : node.status === "failed" || node.status === "cancelled" ? "failed" : "pending",
      summary: node.status === "stale" ? "Superseded version retained in history." : "" })),
    remote: run,
    result: candidate ? {
      conclusion: draft?.sections.find(section => section.heading === "Results")?.body ?? "Current research artifacts are available below.",
      findings: draft?.claims.map(claim => claim.statement) ?? [], caveats: draft?.limitations ?? [],
      data: [], table: run.preview, pythonCode: "", stataCode: "",
      artifacts: candidate.artifacts.map((artifact): AgentArtifact => ({ ...artifact, href: `${root}/artifacts/${artifact.id}` })),
      sources: (run.data.sources ?? []).map(item => ({ provider: item.provenance.provider ?? "User data",
        dataset: item.provenance.dataset ?? "Uploaded file", retrievedAt: item.provenance.retrieved_at ?? run.created_at })),
    } : undefined,
  };
}

export class HttpAgentService implements AgentService {
  readonly remote = true;
  private cursors = new Map<string, number>();
  listSessions(): AgentSession[] { return []; }
  saveSessions(): void { throw new Error("Agent state is owned by the backend."); }
  reset(): AgentSession[] { return []; }

  private async request<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, options);
    const raw = await response.text();
    let payload;
    try { payload = JSON.parse(raw); }
    catch { throw new Error(`The Agent service is unavailable or returned an incomplete response (${response.status}). Retry after it reconnects.`); }
    if (!response.ok) throw new Error(payload.detail?.message ?? payload.detail ?? `Agent request failed (${response.status}).`);
    return payload as T;
  }

  async loadSessions() {
    const response = await this.request<{ sessions: Array<{ run: BackendAgentRun }> }>(`${baseUrl}/api/v1/agent/sessions`);
    return response.sessions.map(item => project(item.run));
  }

  async createSession(request: string, attachments: AgentAttachment[], files: File[] = []) {
    let response = await this.request<{ run: BackendAgentRun }>(`${baseUrl}/api/v1/agent/sessions`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request, defer_clarification: attachments.length > 0 }),
    });
    for (const file of files) {
      const data = new FormData(); data.append("file", file);
      response = await this.request<{ run: BackendAgentRun }>(`${agentRunPath(response.run)}/attachments`, { method: "POST", body: data });
    }
    if (attachments.length > 0) return this.command(project(response.run), "start");
    return project(response.run);
  }

  async refresh(sessionId: string) {
    const response = await this.request<{ run: BackendAgentRun }>(`${baseUrl}/api/v1/agent/sessions/${sessionId}`);
    return project(response.run);
  }

  async command(session: AgentSession, type: string, args: Record<string, unknown> = {}) {
    if (!session.remote) throw new Error("This is an offline demonstration session.");
    const id = crypto.randomUUID();
    const response = await this.request<{ run: BackendAgentRun }>(`${agentRunPath(session.remote)}/commands`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command_id: id, idempotency_key: id, expected_version: session.remote.version,
        type, arguments: args, actor: "user" }),
    });
    return project(response.run);
  }

  subscribe(sessionId: string, runId: string, callback: () => void) {
    if (typeof EventSource === "undefined") return () => undefined;
    const events = new EventSource(`${baseUrl}/api/v1/agent/sessions/${sessionId}/runs/${runId}/events?after=${this.cursors.get(runId) ?? 0}`);
    let timer: ReturnType<typeof setTimeout> | undefined;
    events.addEventListener("progress", event => {
      const id = Number((event as MessageEvent).lastEventId);
      if (Number.isFinite(id)) this.cursors.set(runId, Math.max(id, this.cursors.get(runId) ?? 0));
      if (timer === undefined) timer = setTimeout(() => { timer = undefined; callback(); }, 750);
    });
    return () => { events.close(); if (timer !== undefined) clearTimeout(timer); };
  }
}
