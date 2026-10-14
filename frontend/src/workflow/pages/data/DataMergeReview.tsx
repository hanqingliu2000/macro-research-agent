import { useState } from "react";

import type { WorkflowSession } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";

interface DataMergeReviewProps {
  disabled: boolean;
  onApprove: () => Promise<unknown>;
  session: WorkflowSession;
}

export function DataMergeReview({ disabled, onApprove, session }: DataMergeReviewProps) {
  const review = session.data.mergeReview;
  const [submitting, setSubmitting] = useState(false);
  if (!review) return null;

  const approved = review.status === "approved";
  const approve = async () => {
    setSubmitting(true);
    try {
      await onApprove();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="data-control-card data-merge-review">
      <SectionHeading
        eyebrow="CROSS-SOURCE REVIEW"
        meta={<span role="status">{approved ? "Approved" : "Review required"}</span>}
        title="Canonical data merge"
      />
      <p>
        {review.inputSnapshotIds.length} source snapshots are appended into one long-form dataset.
        Source rows remain traceable to their connector, dataset and original snapshot.
      </p>
      <dl>
        <div><dt>Identity</dt><dd>{review.identityKeys.join(" · ")}</dd></div>
        <div><dt>Frequency</dt><dd>{review.frequencyPolicy}</dd></div>
        <div><dt>Units</dt><dd>{review.unitPolicy}</dd></div>
        <div><dt>Missing</dt><dd>{review.missingPolicy}</dd></div>
      </dl>
      {!approved && (
        <button
          className="primary-button"
          disabled={disabled || submitting}
          onClick={() => void approve()}
          type="button"
        >
          {submitting ? "Approving…" : "Approve merged dataset"}
        </button>
      )}
      {approved && review.reviewedAt && (
        <small>Approved {new Date(review.reviewedAt).toLocaleString()}</small>
      )}
    </section>
  );
}
