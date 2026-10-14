import { useEffect, useState } from "react";

import { SectionHeading } from "../../components/SectionHeading";
import { StageChatComposer } from "../../components/StageChatComposer";
import type { WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";

export function OutputRevisionChat({ session, disabled }: { session: WorkflowSession; disabled: boolean }) {
  const { execute, pending } = useWorkflow();
  const [draft, setDraft] = useState("");
  const patches = session.output.pendingProposal?.patches ?? [];
  const directives = session.output.pendingProposal?.reportDirectives ?? [];
  const [selectedPatchIds, setSelectedPatchIds] = useState<string[]>(patches.map((item) => item.id));
  const [selectedDirectiveIds, setSelectedDirectiveIds] = useState<string[]>(directives.map((item) => item.directiveId));
  const selectedArtifact = session.output.artifacts.find(
    (item) => item.id === session.output.selectedArtifactId,
  ) ?? session.output.artifacts.find((item) => ["svg", "csv", "xlsx"].includes(item.format));
  const revisionEligible = Boolean(
    selectedArtifact && ["svg", "csv", "xlsx"].includes(selectedArtifact.format),
  );
  const limitReached = (session.output.reviewIteration ?? 0) >= 3;
  const hasReviewProposal = patches.length > 0 || directives.length > 0;
  const revisionDisabled = disabled || pending || !revisionEligible || limitReached;
  const proposalDisabled = disabled || pending || !hasReviewProposal || limitReached;
  useEffect(() => {
    setSelectedPatchIds(patches.map((item) => item.id));
    setSelectedDirectiveIds(directives.map((item) => item.directiveId));
  }, [session.output.pendingProposal?.id]);
  const submit = () => {
    const request = draft.trim();
    if (!request) return;
    execute(session.id, { type: "propose_output_revision", request });
    setDraft("");
  };
  const setPatchSelected = (patchId: string, groupId: string | undefined, checked: boolean) => {
    const affectedIds = new Set(
      patches
        .filter((patch) => groupId ? patch.groupId === groupId : patch.id === patchId)
        .map((patch) => patch.id),
    );
    setSelectedPatchIds((current) => checked
      ? [...new Set([...current, ...affectedIds])]
      : current.filter((id) => !affectedIds.has(id)));
  };
  return (
    <section className="output-chat">
      <SectionHeading className="stage-panel-heading" eyebrow="OUTPUT CHAT" meta={<span>Separate thread</span>} title="Targeted revisions" />
      <p className="output-revision-scope" role="status">
        {limitReached
          ? "The three-round review limit has been reached."
          : revisionEligible
            ? `Editing ${selectedArtifact?.name}. Chart and table changes use typed patches.`
            : selectedArtifact?.format === "report"
              ? "Reports can be revised only after you approve a section-bound Review AI directive."
              : "Select a chart or table to request a revision. Code and manifests are read-only."}
      </p>
      <div className="output-message-list">
        {session.outputThread.map((item) => <article className={`stage-message stage-message-${item.role}`} key={item.id}><p>{item.body}</p></article>)}
        {session.output.pendingProposal && (
          <section className="output-proposal-card">
            <p className="panel-kicker">OUTPUT REVISION PROPOSAL</p>
            <h3>{session.output.pendingProposal.summary}</h3>
            <p>{session.output.pendingProposal.request}</p>
            <dl><div><dt>Affected</dt><dd>{session.output.pendingProposal.artifactIds.join(", ")}</dd></div><div><dt>Unchanged</dt><dd>All other artifacts</dd></div></dl>
            <fieldset className="output-patch-list">
              <legend>Select corrections</legend>
              {patches.map((patch) => (
                <label key={patch.id}>
                  <input
                    checked={selectedPatchIds.includes(patch.id)}
                    onChange={(event) => setPatchSelected(patch.id, patch.groupId, event.target.checked)}
                    type="checkbox"
                  />
                  <span><strong>{Object.keys(patch.changes).join(", ")}</strong><small>{patch.rationale}</small>{patch.groupId && <small>Applied together with related corrections</small>}</span>
                </label>
              ))}
            </fieldset>
            {directives.length > 0 && (
              <fieldset className="output-patch-list">
                <legend>Select report revisions</legend>
                {directives.map((directive) => (
                  <label key={directive.directiveId}>
                    <input
                      checked={selectedDirectiveIds.includes(directive.directiveId)}
                      onChange={(event) => setSelectedDirectiveIds((current) => event.target.checked
                        ? [...new Set([...current, directive.directiveId])]
                        : current.filter((id) => id !== directive.directiveId))}
                      type="checkbox"
                    />
                    <span>
                      <strong>{directive.targetSectionIds.join(", ")}</strong>
                      <small>{directive.issue}</small>
                      <small>Acceptance: {directive.acceptanceCriteria.join("; ")}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            <div className="output-proposal-actions">
              <button className="primary-button" disabled={proposalDisabled || selectedPatchIds.length + selectedDirectiveIds.length === 0} onClick={() => execute(session.id, { type: "apply_output_revision", acceptedPatchIds: selectedPatchIds, acceptedDirectiveIds: selectedDirectiveIds })} type="button">{pending ? "Applying and reviewing…" : "Apply selected corrections"}</button>
              <button className="secondary-button" disabled={pending} onClick={() => execute(session.id, { type: "reject_output_revision" })} type="button">Reject proposal</button>
            </div>
          </section>
        )}
      </div>
      <StageChatComposer actionLabel="Propose revision" disabled={revisionDisabled} id="output-chat-input" label="Request an output revision" onChange={setDraft} onSubmit={submit} placeholder="For example: simplify the chart title and clarify the source note…" value={draft} />
    </section>
  );
}
