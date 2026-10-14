import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createWorkflowSession } from "../../domain/workflowEngine";
import type { Artifact, OutputReviewFinding, OutputReviewReport, WorkflowSession } from "../../domain/types";
import type { WorkflowService } from "../../services";
import { WorkflowProvider } from "../../state/WorkflowContext";
import { OutputReviewPanel } from "./OutputReviewPanel";
import { OutputRevisionChat } from "./OutputRevisionChat";

const chart: Artifact = {
  id: "chart-current",
  kind: "chart",
  name: "inflation.svg",
  format: "svg",
  description: "Current chart",
  hash: "sha256:current",
  status: "ready",
  exportSelected: true,
};

function review(iteration: number, status: OutputReviewReport["status"]): OutputReviewReport {
  return {
    id: `review-${iteration}`,
    status,
    providerProfile: "codex-local",
    modelId: "codex-configured-default",
    targetArtifactSetHash: `sha256:set-${iteration}`,
    guidelineVersion: "publication-v1",
    iteration,
    reviewedArtifactIds: [chart.id],
    reviewRenderHashes: { [chart.id]: chart.hash },
    dataAccessId: "grant-1",
    inspectedRowCount: 24,
    findings: [],
    patches: [],
    createdAt: `2026-09-12T10:0${iteration}:00.000Z`,
  };
}

function renderWithSession(session: WorkflowSession, child: React.ReactNode) {
  const service = {
    initialSessions: () => [session],
    execute: vi.fn(),
  } as unknown as WorkflowService;
  render(<WorkflowProvider service={service}>{child}</WorkflowProvider>);
  return service;
}

describe("Output review and revision progress", () => {
  it("shows both author checks without spending a reviewer round", () => {
    const session = createWorkflowSession("Chart delivery");
    session.output.chartSelfChecks = [{
      id: "self-1", provider: "deepseek-development", model: "configured-model",
      artifactSetHash: "sha256:test", createdAt: "2026-09-28T17:00:00Z", status: "fail",
      rounds: [{ round: 1, status: "pass", issues: [] },
        { round: 2, status: "fail", issues: ["Title clips"] }],
    }];
    renderWithSession(session, <OutputReviewPanel disabled={false} session={session} />);
    expect(screen.getByText("Self-check 1/2: pass")).toBeInTheDocument();
    expect(screen.getByText("Self-check 2/2: fail")).toBeInTheDocument();
    expect(screen.getByText("0/3 review rounds")).toBeInTheDocument();
    expect(screen.getByText(/Not handed to Review AI/)).toBeInTheDocument();
  });
  it("identifies the actual versioned placeholder without changing the round limit", () => {
    const base = createWorkflowSession("Review a publication chart.");
    const session: WorkflowSession = {
      ...base,
      output: {
        ...base.output,
        artifacts: [chart],
        reviewIteration: 2,
        reviewReport: {
          ...review(2, "warning"),
          visualRubricVersion: "academic-publication-placeholder-v1",
          visualRubricStatus: "placeholder",
          visualRubricHash: "sha256:rubric",
        },
      },
    };
    renderWithSession(session, <OutputReviewPanel disabled={false} session={session} />);
    expect(screen.getByText(/Visual standard: academic-publication-placeholder-v1/)).toBeInTheDocument();
    expect(screen.getByText("2/3 review rounds")).toBeInTheDocument();
  });

  it("keeps review available when preflight finds publication blockers", () => {
    const base = createWorkflowSession("Review a wide publication table.");
    const table: Artifact = {
      ...chart,
      id: "table-wide",
      name: "india-employment.csv",
      format: "csv",
    };
    const session: WorkflowSession = {
      ...base,
      output: {
        ...base.output,
        artifacts: [table],
        selectedArtifactId: table.id,
        preflightFindings: [{
          finding_id: "finding-table-columns",
          rule_id: "TABLE-COLUMNS-001",
          severity: "fail",
          message: "Table contains more columns than the publication guideline permits.",
          artifact_ids: [table.id],
          blocking: true,
          proposed_patch_ids: [],
        } as unknown as OutputReviewFinding],
      },
    };

    renderWithSession(session, <OutputReviewPanel disabled={false} session={session} />);

    expect(screen.getByText("1 publication blocker(s)")).toBeInTheDocument();
    expect(screen.getByText("TABLE-COLUMNS-001")).toBeInTheDocument();
    expect(screen.getByText("india-employment.csv")).toBeInTheDocument();
    expect(screen.getByText(/You can still run Output review/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run output review" })).toBeEnabled();
  });

  it("shows an identical preflight and AI finding only once", () => {
    const base = createWorkflowSession("Review a wide publication table.");
    const finding = {
      id: "finding-table-columns",
      ruleId: "TABLE-COLUMNS-001",
      severity: "fail" as const,
      message: "Table contains more columns than the publication guideline permits.",
      artifactIds: [chart.id],
      blocking: true,
      proposedPatchIds: [],
    };
    const session: WorkflowSession = {
      ...base,
      output: {
        ...base.output,
        artifacts: [chart],
        selectedArtifactId: chart.id,
        preflightFindings: [finding],
        reviewReport: { ...review(1, "fail"), findings: [finding] },
      },
    };

    renderWithSession(session, <OutputReviewPanel disabled={false} session={session} />);

    expect(screen.getAllByText(finding.message)).toHaveLength(1);
  });

  it("does not show an artifact finding after that artifact is excluded", () => {
    const base = createWorkflowSession("Review a selective publication package.");
    const excludedTable: Artifact = {
      ...chart,
      id: "table-excluded",
      name: "wide-table.csv",
      format: "csv",
      exportSelected: false,
    };
    const session: WorkflowSession = {
      ...base,
      output: {
        ...base.output,
        artifacts: [chart, excludedTable],
        selectedArtifactId: chart.id,
        preflightFindings: [{
          id: "finding-table-columns",
          ruleId: "TABLE-COLUMNS-001",
          severity: "fail",
          message: "Excluded table contains too many columns.",
          artifactIds: [excludedTable.id],
          blocking: true,
          proposedPatchIds: [],
        }],
      },
    };

    renderWithSession(session, <OutputReviewPanel disabled={false} session={session} />);

    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.queryByText("Excluded table contains too many columns.")).not.toBeInTheDocument();
  });

  it("shows the bounded review timeline and immutable artifact version transition", () => {
    const base = createWorkflowSession("Review an inflation chart.");
    const session: WorkflowSession = {
      ...base,
      output: {
        ...base.output,
        artifacts: [chart],
        artifactHistory: [
          [{ ...chart, id: "chart-legacy", hash: "sha256:legacy" }],
          [{ ...chart, id: "chart-old", hash: "sha256:old" }],
        ],
        selectedArtifactId: chart.id,
        reviewIteration: 3,
        maxReviewIterations: 3,
        reviewHistory: [review(1, "warning")],
        reviewReport: review(3, "pass"),
        revisionHistory: [{
          id: "proposal-1",
          revision: 1,
          request: "Shorten the chart title",
          acceptedPatchIds: ["patch-1"],
          previousArtifactSetHash: "sha256:set-1",
          artifactSetHash: "sha256:set-2",
          artifacts: [{
            previousArtifactId: "chart-old",
            artifactId: chart.id,
            name: chart.name,
            format: "svg",
            previousHash: "sha256:old",
            hash: chart.hash,
          }],
          appliedAt: "2026-09-12T10:02:00.000Z",
          reviewIteration: 2,
          reviewReportId: "review-2",
          reviewStatus: "pass",
        }],
      },
    };

    renderWithSession(session, <OutputReviewPanel disabled={false} session={session} />);

    expect(screen.getByText("3/3 review rounds")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "3 of 3 Output review rounds used" })).toHaveValue(3);
    expect(screen.getByRole("button", { name: "Review limit reached" })).toBeDisabled();
    expect(screen.getByText("Version and review history")).toBeInTheDocument();
    expect(screen.getByText("Revision 1")).toBeInTheDocument();
    expect(screen.getByText("Earlier artifact set 1")).toBeInTheDocument();
    expect(screen.getByText(/old → current/)).toBeInTheDocument();
  });

  it("disables revision requests for non-chart and non-table artifacts", () => {
    const base = createWorkflowSession("Review generated code.");
    const codeArtifact: Artifact = {
      ...chart,
      id: "code-1",
      name: "analysis.py",
      format: "python",
    };
    const session: WorkflowSession = {
      ...base,
      output: {
        ...base.output,
        artifacts: [codeArtifact],
        artifactHistory: [],
        selectedArtifactId: codeArtifact.id,
        reviewIteration: 1,
        maxReviewIterations: 3,
      },
    };

    renderWithSession(session, <OutputRevisionChat disabled={false} session={session} />);

    expect(screen.getByText(/Code and manifests are read-only/)).toBeInTheDocument();
    expect(screen.getByLabelText("Request an output revision")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Propose revision" })).toBeDisabled();
  });

  it("shows semantic report progress and an approvable section directive", () => {
    const base = createWorkflowSession("Review a generated report.");
    const reportArtifact: Artifact = {
      ...chart,
      id: "report-1",
      name: "research_report.md",
      format: "report",
    };
    const session: WorkflowSession = {
      ...base,
      output: {
        ...base.output,
        artifacts: [reportArtifact],
        selectedArtifactId: reportArtifact.id,
        reportSemanticStatus: "fail",
        pendingProposal: {
          id: "proposal-report",
          request: "Apply selected Review AI corrections.",
          summary: "Review AI proposed a bounded report correction.",
          artifactIds: [reportArtifact.id],
          patches: [],
          reportDirectives: [{
            directiveId: "directive-1",
            artifactId: reportArtifact.id,
            targetSectionIds: ["section-results"],
            issue: "State the forecast horizon.",
            preserveEvidenceRefs: ["sha256:data"],
            acceptanceCriteria: ["Name the horizon and uncertainty."],
            requiresUpstreamStage: false,
          }],
          targetArtifactSetHash: "sha256:set",
          targetArtifactHashes: { [reportArtifact.id]: reportArtifact.hash },
        },
      },
    };

    renderWithSession(session, <OutputRevisionChat disabled={false} session={session} />);

    expect(screen.getByText("section-results")).toBeInTheDocument();
    expect(screen.getByText("State the forecast horizon.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply selected corrections" })).toBeEnabled();
    expect(screen.getByLabelText("Request an output revision")).toBeDisabled();
  });
});
