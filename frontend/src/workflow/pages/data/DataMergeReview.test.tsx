import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { WorkflowSession } from "../../domain/types";
import { DataMergeReview } from "./DataMergeReview";

function sessionWithMerge(status: "waiting_for_review" | "approved") {
  return {
    data: {
      mergeReview: {
        status,
        strategy: "canonical_union",
        inputSnapshotIds: ["dataset-imf", "dataset-wdi"],
        outputSnapshotId: "dataset-merged",
        identityKeys: ["entity_code", "indicator_code", "frequency", "period"],
        frequencyPolicy: "Preserve each source frequency; no implicit conversion.",
        unitPolicy: "Preserve source unit metadata; no implicit conversion.",
        missingPolicy: "Preserve missing observations for Data review.",
        lineageColumns: [
          "source_connector_id",
          "source_dataset",
          "source_snapshot_id",
        ],
      },
    },
  } as WorkflowSession;
}

it("requires an explicit action and shows progress while approving a merge", async () => {
  let finish: (() => void) | undefined;
  const onApprove = vi.fn(
    () => new Promise<void>((resolve) => { finish = resolve; }),
  );
  render(
    <DataMergeReview disabled={false} onApprove={onApprove} session={sessionWithMerge("waiting_for_review")} />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("Review required");
  expect(screen.getByText(/2 source snapshots/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Approve merged dataset" }));
  expect(onApprove).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "Approving…" })).toBeDisabled();
  finish?.();
  await waitFor(() => expect(screen.getByRole("button")).not.toBeDisabled());
});

it("keeps approved merge history visible without another approval control", () => {
  render(
    <DataMergeReview disabled={false} onApprove={vi.fn()} session={sessionWithMerge("approved")} />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Approved");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
