import { afterEach, describe, expect, it, vi } from "vitest";

import contract from "../../../../contracts/workflow_phase1a.json";
import { createWorkflowSession, makeCommandEnvelope } from "../domain/workflowEngine";
import { SESSION_STATUS_LABELS, STAGE_LABELS, type WorkflowSession } from "../domain/types";
import { HttpWorkflowService, serializeCommandEnvelope } from "./httpWorkflowService";

afterEach(() => vi.unstubAllGlobals());

describe("Workflow HTTP serialization contract", () => {
  it("creates only from the research request and never uploads frontend mock state", async () => {
    const session = createWorkflowSession("Backend creates the authoritative session.");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session, projection: { current_snapshot_hash: "sha256:new" } }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");

    await service.createSession("Backend creates the authoritative session.");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({ request: "Backend creates the authoritative session." });
    expect(body.session).toBeUndefined();
  });

  it("matches the shared stage and status vocabulary", () => {
    expect(Object.keys(STAGE_LABELS)).toEqual(contract.stages);
    expect(Object.keys(SESSION_STATUS_LABELS)).toEqual(contract.statuses);
  });

  it("uses recoverable delete and restore endpoints", async () => {
    const session = createWorkflowSession("Lifecycle request");
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({ session, projection: { current_snapshot_hash: "sha256:new" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");
    await service.setSessionDeleted(session.id, true);
    await service.setSessionDeleted(session.id, false);
    expect(fetchMock.mock.calls[0][0]).toBe(`http://test/api/v1/workflow/sessions/${session.id}`);
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(fetchMock.mock.calls[1][0]).toBe(`http://test/api/v1/workflow/sessions/${session.id}/restore`);
    expect(fetchMock.mock.calls[1][1].method).toBe("POST");
  });

  it("serializes camel-case UI metadata to the canonical command envelope", () => {
    const session = createWorkflowSession("Validate the HTTP command contract.");
    const envelope = makeCommandEnvelope(session, {
      type: "submit_clarification",
      answers: {},
    });
    envelope.meta = {
      commandId: contract.command_meta.command_id,
      idempotencyKey: contract.command_meta.idempotency_key,
      sessionId: contract.command_meta.session_id,
      expectedActiveStage: "plan",
      expectedSnapshotHash: contract.command_meta.expected_snapshot_hash,
      actor: "user",
      requestedAt: contract.command_meta.requested_at,
    };

    expect(serializeCommandEnvelope(envelope)).toEqual(contract.command_meta);
  });

  it("surfaces a typed 409 conflict instead of overwriting server state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              message: "Workflow session changed since it was loaded.",
              current_stage: "data",
              current_snapshot_hash: "sha256:newer",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const service = new HttpWorkflowService("http://test/api/v1/workflow");
    const session = createWorkflowSession("Test stale command handling.");

    await expect(
      service.execute(session, { type: "submit_clarification", answers: {} }),
    ).rejects.toMatchObject({
      conflict: {
        message: "Workflow session changed since it was loaded.",
        currentStage: "data",
        currentSnapshotHash: "sha256:newer",
      },
    });
  });

  it("surfaces the backend detail for a rejected workflow command", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Planning provider returned invalid PlanDraft at period.frequency.",
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const service = new HttpWorkflowService("http://test/api/v1/workflow");
    const session = createWorkflowSession("Test provider validation feedback.");

    await expect(
      service.execute(session, { type: "submit_clarification", answers: {} }),
    ).rejects.toThrow(
      "Workflow API request failed (422): Planning provider returned invalid PlanDraft at period.frequency.",
    );
  });

  it.each([
    ["invalid_model_contract", "Invalid model contract"],
    ["provider_unavailable", "AI provider unavailable"],
    ["connector_unavailable", "Data connector unavailable"],
    ["handoff_incomplete", "Stage handoff incomplete"],
    ["deterministic_contract_violation", "Offline test contract violation"],
  ])("distinguishes the %s workflow error category", async (code, label) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code, message: "Correct this field and retry." } }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const service = new HttpWorkflowService("http://test/api/v1/workflow");
    const session = createWorkflowSession("Test categorized feedback.");

    await expect(
      service.execute(session, { type: "submit_clarification", answers: {} }),
    ).rejects.toThrow(`${label} (${code}): Correct this field and retry.`);
  });

  it("routes Plan commands to the backend-owned endpoint without a result session", async () => {
    const session = createWorkflowSession("Backend-owned planning.");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session,
          projection: { current_snapshot_hash: "sha256:server" },
          idempotent_replay: false,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");

    await service.execute(session, { type: "submit_clarification", answers: {} });

    expect(fetchMock.mock.calls[0][0]).toContain(`/sessions/${session.id}/plan/commands`);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.result_session).toBeUndefined();
  });

  it("uploads Workflow source files through multipart form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          upload_id: "upload-1",
          filename: "macro.csv",
          checksum: "sha256:test",
          byte_size: 10,
          tables: [],
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");
    await service.uploadSource("session-1", new File(["a,b\n1,2"], "macro.csv"));

    expect(fetchMock.mock.calls[0][0]).toContain("/sessions/session-1/sources/uploads");
    expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(FormData);
    expect(fetchMock.mock.calls[0][1].headers).toBeUndefined();
  });

  it("routes Data commands to the backend-owned Data endpoint", async () => {
    const session: WorkflowSession = {
      ...createWorkflowSession("Prepare local data."),
      activeStage: "data" as const,
      reachedStages: ["plan", "data"],
      status: "data_review" as const,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session,
          projection: { current_snapshot_hash: "sha256:data-server" },
          idempotent_replay: false,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");

    await service.execute(session, { type: "apply_data_operation", operation: "deduplicate" });

    expect(fetchMock.mock.calls[0][0]).toContain(`/sessions/${session.id}/data/commands`);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.result_session).toBeUndefined();
  });

  it("routes Pipeline commands and previews to backend-owned endpoints", async () => {
    const session: WorkflowSession = {
      ...createWorkflowSession("Run typed transformations."),
      activeStage: "transformation" as const,
      reachedStages: ["plan", "data", "transformation"],
      status: "pipeline_editing" as const,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            session,
            projection: { current_snapshot_hash: "sha256:pipeline-server" },
            idempotent_replay: false,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            operation_id: "operation-1",
            offset: 0,
            limit: 50,
            total_rows: 1,
            columns: ["value"],
            rows: [{ value: 2 }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "code-python",
            language: "python",
            filename: "reproduce_research.py",
            checksum: "sha256:code",
            specification_hash: "sha256:spec",
            content: "print('reviewed')",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");

    await service.execute(session, { type: "add_pipeline_operation", operation: "lag" });
    await service.previewPipeline(session.id, "operation-1", 0, 50);
    const code = await service.getPipelineCode(session.id, "code-python");

    expect(fetchMock.mock.calls[0][0]).toContain(`/sessions/${session.id}/pipeline/commands`);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).result_session).toBeUndefined();
    expect(fetchMock.mock.calls[1][0]).toContain(
      `/sessions/${session.id}/pipeline/preview?offset=0&limit=50&operation_id=operation-1`,
    );
    expect(fetchMock.mock.calls[2][0]).toContain(
      `/sessions/${session.id}/pipeline/code/code-python`,
    );
    expect(code.content).toBe("print('reviewed')");
  });

  it("routes Output approval and artifact reads to backend-owned endpoints", async () => {
    const session: WorkflowSession = {
      ...createWorkflowSession("Review governed outputs."),
      activeStage: "output" as const,
      reachedStages: ["plan", "data", "transformation", "output"],
      status: "output_review" as const,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            session,
            projection: { current_snapshot_hash: "sha256:output-server" },
            idempotent_replay: false,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "artifact-data",
            format: "csv",
            previewKind: "table",
            columns: ["value"],
            rows: [{ value: 2 }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            schema_version: "mra-artifact-comparison-v1",
            baseline_artifact_id: "artifact-old",
            current_artifact_id: "artifact-new",
            artifact_format: "svg",
            status: "presentation_changed",
            baseline_hash: "sha256:old",
            current_hash: "sha256:new",
            hash_changed: true,
            specification_changes: [],
            value_comparison: {
              status: "unchanged",
              source: "specification",
              changed_sheets: [],
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");

    await service.execute(session, { type: "finalize_output" });
    const preview = await service.getOutputArtifactPreview(session.id, "artifact-data");

    expect(fetchMock.mock.calls[0][0]).toContain(`/sessions/${session.id}/output/commands`);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).result_session).toBeUndefined();
    expect(fetchMock.mock.calls[1][0]).toContain(
      `/sessions/${session.id}/output/artifacts/artifact-data`,
    );
    expect(preview.rows).toEqual([{ value: 2 }]);
    expect(service.outputArtifactDownloadUrl(session.id, "artifact-data")).toContain(
      `/sessions/${session.id}/output/artifacts/artifact-data/download`,
    );

    await service.compareOutputArtifacts(session.id, "artifact-new", "artifact-old");
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining(
        `/sessions/${session.id}/output/artifacts/artifact-new/compare/artifact-old`,
      ),
      undefined,
    );
  });

  it("sends cleaned workbooks with command metadata as multipart data", async () => {
    const session: WorkflowSession = {
      ...createWorkflowSession("Round-trip local data."),
      activeStage: "data" as const,
      reachedStages: ["plan", "data"],
      status: "data_review" as const,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          session,
          projection: { current_snapshot_hash: "sha256:imported" },
          idempotent_replay: false,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");

    await service.importRoundTrip(session, new File(["xlsx"], "cleaned.xlsx"));

    expect(fetchMock.mock.calls[0][0]).toContain("/data/roundtrip/imports");
    const form = fetchMock.mock.calls[0][1].body as FormData;
    expect(form.get("file")).toBeInstanceOf(File);
    expect(JSON.parse(form.get("meta_json") as string).expected_stage).toBe("data");
  });

  it("imports, exports and forks portable Workflow sessions", async () => {
    const source = createWorkflowSession("Portable research.");
    const imported = { ...source, id: "workflow-imported" };
    const forked = {
      ...source,
      id: "workflow-forked",
      status: "output_review" as const,
      activeStage: "output" as const,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            session: imported,
            projection: { current_snapshot_hash: "sha256:imported" },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            session: forked,
            projection: { current_snapshot_hash: "sha256:forked" },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const service = new HttpWorkflowService("http://test/api/v1/workflow");

    await service.importSession(new File(["archive"], "research.mra.zip"));
    await service.forkSession(source.id, "Continued research");

    expect(fetchMock.mock.calls[0][0]).toContain("/sessions/import");
    expect(fetchMock.mock.calls[0][1].body).toBeInstanceOf(FormData);
    expect(fetchMock.mock.calls[1][0]).toContain(`/sessions/${source.id}/fork`);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({
      title: "Continued research",
    });
    expect(service.sessionArchiveDownloadUrl(source.id)).toContain(
      `/sessions/${source.id}/archive`,
    );
  });
});
