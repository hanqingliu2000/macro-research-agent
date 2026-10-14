import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createWorkflowSession } from "../../domain/workflowEngine";
import type { Artifact, WorkflowSession } from "../../domain/types";
import type { WorkflowService } from "../../services";
import { WorkflowProvider } from "../../state/WorkflowContext";
import { ArtifactPreview } from "./ArtifactPreview";

describe("ArtifactPreview comparison", () => {
  it("summarizes value, specification, and file changes against the latest version", async () => {
    const oldArtifact: Artifact = {
      id: "chart-old",
      kind: "chart",
      name: "analytical_chart.svg",
      format: "svg",
      description: "Previous chart",
      hash: "sha256:old",
      status: "stale",
      exportSelected: true,
    };
    const currentArtifact: Artifact = {
      ...oldArtifact,
      id: "chart-new",
      description: "Current chart",
      hash: "sha256:new",
      status: "ready",
    };
    const session: WorkflowSession = {
      ...createWorkflowSession("Compare output versions."),
      output: {
        ...createWorkflowSession("Compare output versions.").output,
        artifacts: [currentArtifact],
        artifactHistory: [[oldArtifact]],
        selectedArtifactId: currentArtifact.id,
      },
    };
    const service = {
      initialSessions: () => [session],
      getOutputArtifactPreview: vi.fn().mockResolvedValue({
        id: currentArtifact.id,
        format: "svg",
        previewKind: "image",
        content: "data:image/svg+xml,%3Csvg%2F%3E",
      }),
      compareOutputArtifacts: vi.fn().mockResolvedValue({
        schema_version: "mra-artifact-comparison-v1",
        baseline_artifact_id: oldArtifact.id,
        current_artifact_id: currentArtifact.id,
        artifact_format: "svg",
        status: "presentation_changed",
        baseline_hash: oldArtifact.hash,
        current_hash: currentArtifact.hash,
        hash_changed: true,
        specification_changes: [{ field: "title", before: "Old", after: "New" }],
        value_comparison: {
          status: "unchanged",
          source: "specification",
          changed_sheets: [],
        },
      }),
      outputArtifactDownloadUrl: vi.fn().mockReturnValue("#download"),
    } as unknown as WorkflowService;

    render(
      <WorkflowProvider service={service}>
        <ArtifactPreview selectedArtifactId={currentArtifact.id} session={session} />
      </WorkflowProvider>,
    );

    expect(await screen.findByText("Presentation changed")).toBeInTheDocument();
    expect(screen.getByText("Data values").parentElement).toHaveTextContent("unchanged");
    expect(screen.getByText("1 fields changed")).toBeInTheDocument();
    expect(service.compareOutputArtifacts).toHaveBeenCalledWith(
      session.id,
      currentArtifact.id,
      oldArtifact.id,
    );
  });
});
