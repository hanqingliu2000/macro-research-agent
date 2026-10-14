import { type ReactNode, useEffect, useMemo, useReducer, useState } from "react";

import { appendAgentMessage, completeAgentRun, createAgentSession } from "../domain/agentWorkflow";
import type { AgentAttachment, AgentSession } from "../domain/types";
import { agentService, type AgentService } from "../mock/agentService";
import { HttpAgentService } from "../services/httpAgentService";
import { AgentContext, type AgentContextValue } from "./AgentContextCore";

type AgentAction =
  | { type: "replace"; sessions: AgentSession[] }
  | { type: "upsert"; session: AgentSession };

function reducer(state: AgentSession[], action: AgentAction): AgentSession[] {
  const newest = (old: AgentSession, incoming: AgentSession) => {
    if (!old.remote || !incoming.remote) return incoming;
    if (old.remote.run_id === incoming.remote.run_id) return incoming.remote.version >= old.remote.version ? incoming : old;
    return incoming.createdAt >= old.createdAt ? incoming : old;
  };
  if (action.type === "replace") return action.sessions.map(incoming => {
    const previous = state.find(item => item.id === incoming.id);
    return previous ? newest(previous, incoming) : incoming;
  }).concat(state.filter(item => !action.sessions.some(incoming => incoming.id === item.id)));
  const exists = state.some((session) => session.id === action.session.id);
  return exists
    ? state.map((session) => (session.id === action.session.id ? newest(session, action.session) : session))
    : [action.session, ...state];
}

const defaultService = import.meta.env.MODE === "test" ? agentService : new HttpAgentService();

export function AgentProvider({
  children,
  service = defaultService,
}: {
  children: ReactNode;
  service?: AgentService;
}) {
  const [sessions, dispatch] = useReducer(reducer, undefined, () => service.listSessions());
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(service instanceof HttpAgentService);
  const activeSubscriptions = sessions.filter(session => session.remote &&
    ["requested", "queued", "running", "clarifying"].includes(session.status))
    .map(session => `${session.id}~${session.remote?.run_id}`).join("|");
  useEffect(() => {
    if (!(service instanceof HttpAgentService)) return;
    let stopped = false;
    const load = () => service.loadSessions().then(items => {
      if (!stopped) { dispatch({ type: "replace", sessions: items }); setLoading(false); setError(previous => previous.startsWith("The Agent service") ? "" : previous); }
    }).catch(reason => { if (!stopped) setError(String(reason.message ?? reason)); });
    void load();
    const polling = window.setInterval(() => void load(), 10000);
    return () => { stopped = true; window.clearInterval(polling); };
  }, [service]);
  useEffect(() => {
    if (!(service instanceof HttpAgentService)) return;
    const unsubscribe = activeSubscriptions.split("|").filter(Boolean).map(pair => {
      const [sessionId, runId] = pair.split("~");
      return service.subscribe(sessionId, runId, () => {
        void service.refresh(sessionId).then(updated => dispatch({ type: "upsert", session: updated })).catch(() => undefined);
      });
    });
    return () => unsubscribe.forEach(stop => stop());
  }, [service, activeSubscriptions]);

  const value = useMemo<AgentContextValue>(() => {
    const commit = (session: AgentSession) => {
      const exists = sessions.some((item) => item.id === session.id);
      const next = exists
        ? sessions.map((item) => (item.id === session.id ? session : item))
        : [session, ...sessions];
      if (!(service instanceof HttpAgentService)) service.saveSessions(next);
      dispatch({ type: "upsert", session });
    };
    const find = (sessionId: string) => sessions.find((session) => session.id === sessionId);

    const execute = async (sessionId: string, type: string, args: Record<string, unknown> = {}) => {
      const session = find(sessionId);
      if (!session || pending[sessionId] || !(service instanceof HttpAgentService)) return;
      setPending(current => ({ ...current, [sessionId]: true })); setError("");
      try { commit(await service.command(session, type, args)); }
      catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
      finally { setPending(current => ({ ...current, [sessionId]: false })); }
    };
    return {
      sessions,
      execute, pending, error, loading,
      createSession(request: string, attachments: AgentAttachment[], files: File[] = []) {
        if (service instanceof HttpAgentService) {
          return service.createSession(request, attachments, files).then(session => { commit(session); return session; });
        }
        const session = createAgentSession(request, attachments);
        commit(session);
        return session;
      },
      submitClarifications(sessionId, answers) {
        if (service instanceof HttpAgentService) { void execute(sessionId, "answer_clarification", { answers }); return; }
        const session = find(sessionId);
        if (session) commit(completeAgentRun(session, answers));
      },
      sendMessage(sessionId, body) {
        if (service instanceof HttpAgentService) { void execute(sessionId, "message", { message: body }); return; }
        const session = find(sessionId);
        if (session) commit(appendAgentMessage(session, body));
      },
      resetDemo() {
        dispatch({ type: "replace", sessions: service.reset() });
      },
    };
  }, [service, sessions, pending, error, loading]);

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>;
}
