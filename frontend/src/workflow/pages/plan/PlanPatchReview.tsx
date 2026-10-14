import { useState } from "react";

import { ImpactDialog } from "../../components/ImpactDialog";
import type { PlanPatchProposal } from "../../domain/types";
import { planPatchFieldLabel } from "./planPatchFormatting";
import { PlanPatchValue } from "./PlanPatchValue";

export function PlanPatchReview({
  proposal,
  onApply,
  onReject,
  disabled,
}: {
  proposal: PlanPatchProposal;
  disabled: boolean;
  onApply(fields: string[]): void;
  onReject(): void;
}) {
  const [confirming, setConfirming] = useState(false);
  const fields = Object.keys(proposal.changes);
  const [acceptedFields, setAcceptedFields] = useState(fields);
  const apply = () => {
    if (proposal.affectedStages.length > 0) setConfirming(true);
    else onApply(acceptedFields);
  };
  return (
    <section aria-label="Proposed Plan changes" className="plan-patch-card">
      <header className="patch-heading">
        <span>PROPOSED PLAN CHANGES</span>
        <h3>{proposal.summary}</h3>
        <p>{proposal.request}</p>
      </header>
      {proposal.affectedStages.length > 0 && (
        <div aria-label="Affected stages" className="patch-stage-list">
          <span>Affects</span>
          {proposal.affectedStages.map((stage) => <strong key={stage}>{stage}</strong>)}
        </div>
      )}
      <fieldset className="patch-field-selection">
        <legend>Select the changes to apply</legend>
        {Object.entries(proposal.changes).map(([field, value]) => (
          <label className={acceptedFields.includes(field) ? "selected" : ""} key={field}>
            <input
              checked={acceptedFields.includes(field)}
              onChange={() => setAcceptedFields(acceptedFields.includes(field) ? acceptedFields.filter((item) => item !== field) : [...acceptedFields, field])}
              type="checkbox"
            />
            <span className="patch-field-content">
              <strong>{planPatchFieldLabel(field)}</strong>
              <span className="patch-field-value"><PlanPatchValue value={value} /></span>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="patch-footer">
        <small>Applies to Plan version {proposal.targetSnapshotHash.slice(0, 12)}</small>
        <div className="button-row"><button className="primary-button" disabled={disabled || acceptedFields.length === 0} onClick={apply} type="button">Apply selected changes</button><button className="secondary-button" disabled={disabled} onClick={onReject} type="button">Reject proposal</button></div>
      </div>
      {confirming && (
        <ImpactDialog
          onCancel={() => setConfirming(false)}
          onConfirm={() => onApply(acceptedFields)}
          stages={proposal.affectedStages}
          title="Apply this Plan patch?"
        >
          <p>{proposal.request}</p>
        </ImpactDialog>
      )}
    </section>
  );
}
