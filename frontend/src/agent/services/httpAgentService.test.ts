import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpAgentService } from "./httpAgentService";
import type { BackendAgentRun } from "../domain/types";

function run(): BackendAgentRun {
  return { run_id: "agent-run-1", session_id: "agent-session-1", request: "Research question",
    status: "paused", phase: "analysis", version: 8, created_at: "2026-10-06", updated_at: "2026-10-06",
    answers: { scope: "Custom response" }, attachments: [], messages: [], nodes: [], data: {}, output: {},
    ledger: { limits: { model_calls: 40 }, used: { model_calls: 12 }, reservations: {} } };
}

afterEach(() => vi.unstubAllGlobals());

describe("Agent HTTP ownership", () => {
  it("uses backend projections and versioned commands without localStorage writes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ sessions: [{ run: run() }] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ sessions: [{ run: run() }] })));
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpAgentService();
    const sessions = await service.loadSessions();
    expect(sessions[0].remote?.ledger.used.model_calls).toBe(12);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ run: { ...run(), status: "queued" } })));
    await service.command(sessions[0], "resume");
    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.expected_version).toBe(8);
    expect(body.command_id).toBe(body.idempotency_key);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/agent/");
    expect(() => service.saveSessions()).toThrow("backend");
  });

  it("reports provider/contract failures without falling back to fixtures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: "provider_unavailable", message: "DeepSeek credential missing" },
    }), { status: 422 })));
    await expect(new HttpAgentService().loadSessions()).rejects.toThrow("DeepSeek credential missing");
  });

  it("does not mistake an intervention reply for clarification authorization", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ sessions: [{ run: {
      ...run(), status: "clarifying", authorizations: [], answers: { intervention_retry: "retry" },
      clarification: { questions: [{ question_id: "scope", prompt: "Which country?", options: ["CHN", "USA"] }] },
    } }] }))));
    const [session] = await new HttpAgentService().loadSessions();
    expect(session.clarification.submitted).toBe(false);
    expect(session.clarification.questions).toHaveLength(1);
  });

  it("coalesces SSE bursts and resumes at the last delivered cursor", () => {
    vi.useFakeTimers();
    const instances: FakeEvents[] = [];
    class FakeEvents {
      handler?: (event: MessageEvent) => void;
      close = vi.fn();
      constructor(readonly url: string) { instances.push(this); }
      addEventListener(_name: string, handler: (event: MessageEvent) => void) { this.handler = handler; }
    }
    vi.stubGlobal("EventSource", FakeEvents);
    const service = new HttpAgentService();
    const callback = vi.fn();
    const stop = service.subscribe("s", "r", callback);
    for (let id = 1; id <= 20; id++) instances[0].handler?.(new MessageEvent("progress", { lastEventId: String(id) }));
    vi.advanceTimersByTime(750);
    expect(callback).toHaveBeenCalledTimes(1);
    stop();
    service.subscribe("s", "r", callback)();
    expect(instances[1].url).toContain("after=20");
    vi.useRealTimers();
  });
});
