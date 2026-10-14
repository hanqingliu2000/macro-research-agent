import { type ReactNode, useCallback, useEffect, useMemo, useReducer, useState } from "react";

import type { WorkflowCommand, WorkflowSession } from "../domain/types";
import { workflowService, WorkflowHttpConflict, type WorkflowService } from "../services";
import { WorkflowContext, type WorkflowContextValue } from "./WorkflowContextCore";
import {
  createWorkflowStore,
  selectWorkflowSessions,
  workflowStoreReducer,
} from "./workflowStore";

export function WorkflowProvider({
  children,
  service = workflowService,
}: {
  children: ReactNode;
  service?: WorkflowService;
}) {
  const [store, dispatch] = useReducer(
    workflowStoreReducer,
    undefined,
    () => createWorkflowStore(service.initialSessions?.() ?? []),
  );
  const [loading, setLoading] = useState(!service.initialSessions);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [conflict, setConflict] = useState<WorkflowContextValue["conflict"]>();
  const sessions = useMemo(() => selectWorkflowSessions(store), [store]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      dispatch({ type: "replace", sessions: await service.listSessions() });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load Workflow sessions.");
    } finally {
      setLoading(false);
    }
  }, [service]);

  useEffect(() => {
    if (!service.initialSessions) void reload();
  }, [reload, service]);

  const value = useMemo<WorkflowContextValue>(() => {
    const commit = (session: WorkflowSession) => {
      dispatch({ type: "upsert", session });
    };
    const handleFailure = (caught: unknown) => {
      if (caught instanceof WorkflowHttpConflict) {
        setConflict(caught.conflict);
        setError(caught.message);
      } else {
        setError(caught instanceof Error ? caught.message : "Workflow operation failed.");
      }
    };
    return {
      sessions,
      loading,
      pending,
      error,
      conflict,
      reload,
      async setSessionDeleted(sessionId, deleted) {
        setPending(true);
        setError(undefined);
        try {
          const session = await service.setSessionDeleted(sessionId, deleted);
          commit(session);
          return session;
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        } finally {
          setPending(false);
        }
      },
      async createSession(request) {
        setPending(true);
        setError(undefined);
        setConflict(undefined);
        try {
          const session = await service.createSession(request);
          commit(session);
          return session;
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        } finally {
          setPending(false);
        }
      },
      async importSession(file) {
        setPending(true);
        setError(undefined);
        try {
          const session = await service.importSession(file);
          commit(session);
          return session;
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        } finally {
          setPending(false);
        }
      },
      async forkSession(sessionId, title) {
        setPending(true);
        setError(undefined);
        try {
          const session = await service.forkSession(sessionId, title);
          commit(session);
          return session;
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        } finally {
          setPending(false);
        }
      },
      sessionArchiveDownloadUrl(sessionId) {
        return service.sessionArchiveDownloadUrl(sessionId);
      },
      async uploadSource(sessionId, file) {
        setPending(true);
        setError(undefined);
        try {
          return await service.uploadSource(sessionId, file);
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        } finally {
          setPending(false);
        }
      },
      async importRoundTrip(sessionId, file) {
        const session = sessions.find((item) => item.id === sessionId);
        if (!session) return undefined;
        setPending(true);
        setError(undefined);
        setConflict(undefined);
        try {
          const updated = await service.importRoundTrip(session, file);
          commit(updated);
          return updated;
        } catch (caught) {
          handleFailure(caught);
          if (caught instanceof WorkflowHttpConflict) await reload();
          return undefined;
        } finally {
          setPending(false);
        }
      },
      async previewData(sessionId, offset, limit) {
        try {
          return await service.previewData(sessionId, offset, limit);
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        }
      },
      async previewPipeline(sessionId, operationId, offset, limit) {
        try {
          return await service.previewPipeline(sessionId, operationId, offset, limit);
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        }
      },
      async getPipelineCode(sessionId, artifactId) {
        try {
          return await service.getPipelineCode(sessionId, artifactId);
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        }
      },
      async getOutputArtifactPreview(sessionId, artifactId) {
        try {
          return await service.getOutputArtifactPreview(sessionId, artifactId);
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        }
      },
      async compareOutputArtifacts(sessionId, currentArtifactId, baselineArtifactId) {
        try {
          return await service.compareOutputArtifacts(
            sessionId,
            currentArtifactId,
            baselineArtifactId,
          );
        } catch (caught) {
          handleFailure(caught);
          throw caught;
        }
      },
      outputArtifactDownloadUrl(sessionId, artifactId) {
        return service.outputArtifactDownloadUrl(sessionId, artifactId);
      },
      async execute(sessionId: string, command: WorkflowCommand) {
        const session = sessions.find((item) => item.id === sessionId);
        if (!session) return;
        setPending(true);
        setError(undefined);
        setConflict(undefined);
        try {
          const updated = await service.execute(session, command);
          commit(updated);
          return updated;
        } catch (caught) {
          handleFailure(caught);
          if (caught instanceof WorkflowHttpConflict) await reload();
          return undefined;
        } finally {
          setPending(false);
        }
      },
      async resetDemo() {
        dispatch({ type: "replace", sessions: await service.reset() });
      },
    };
  }, [conflict, error, loading, pending, reload, service, sessions]);

  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>;
}
