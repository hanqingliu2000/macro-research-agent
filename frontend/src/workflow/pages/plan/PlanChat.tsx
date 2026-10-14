import { useEffect, useState } from "react";

import { AsyncButtonContent } from "../../../ui/components/AsyncButtonContent";
import { StageChatComposer } from "../../components/StageChatComposer";
import type { WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { PlanPatchReview } from "./PlanPatchReview";

export function PlanChat({
  manualEditPending,
  session,
}: {
  manualEditPending: boolean;
  session: WorkflowSession;
}) {
  const { execute, pending } = useWorkflow();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({});
  const [customQuestions, setCustomQuestions] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState("");
  const [draftingPlan, setDraftingPlan] = useState(false);
  const [planningAction, setPlanningAction] = useState<"revision" | "clarification">();
  const clarificationReady = session.clarification.questions.every(
    (question) => Boolean(answers[question.id]?.trim()),
  );

  useEffect(() => {
    setAnswers({});
    setCustomAnswers({});
    setCustomQuestions({});
  }, [session.clarification.id]);

  const submitClarification = async () => {
    if (!clarificationReady || draftingPlan || pending || manualEditPending) return;
    setDraftingPlan(true);
    try {
      await execute(session.id, { type: "submit_clarification", answers });
    } finally {
      setDraftingPlan(false);
    }
  };

  const submitChat = async () => {
    if (manualEditPending || pending || planningAction) return;
    const request = draft.trim();
    if (!request) return;
    setPlanningAction("revision");
    try {
      const updated = await execute(session.id, { type: "propose_plan_patch", request });
      if (updated) setDraft("");
    } finally {
      setPlanningAction(undefined);
    }
  };

  return (
    <section className="stage-chat" aria-label="Plan conversation">
      <div className="stage-message-list">
        {session.planThread.map((item) => (
          <article className={`stage-message stage-message-${item.role}`} key={item.id}>
            <p>{item.body}</p>
          </article>
        ))}

        {!session.clarification.submitted && (
          <form
            aria-busy={draftingPlan}
            className="clarification-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submitClarification();
            }}
          >
            <p className="panel-kicker">CLARIFICATION</p>
            <h3>Confirm the research frame</h3>
            {session.clarification.questions.map((question) => (
              <fieldset disabled={draftingPlan || pending} key={question.id}>
                <legend>{question.prompt}</legend>
                {question.options.map((option) => (
                  <label key={option}>
                    <input
                      checked={!customQuestions[question.id] && answers[question.id] === option}
                      name={question.id}
                      onChange={() => {
                        setCustomQuestions((current) => ({ ...current, [question.id]: false }));
                        setAnswers((current) => ({ ...current, [question.id]: option }));
                      }}
                      type="radio"
                    />
                    <span>{option}</span>
                  </label>
                ))}
                <label className="clarification-custom-choice">
                  <input
                    aria-label={`Write another answer for: ${question.prompt}`}
                    checked={Boolean(customQuestions[question.id])}
                    name={question.id}
                    onChange={() => {
                      setCustomQuestions((current) => ({ ...current, [question.id]: true }));
                      setAnswers((current) => ({
                        ...current,
                        [question.id]: customAnswers[question.id] ?? "",
                      }));
                    }}
                    type="radio"
                  />
                  <span>Write another answer</span>
                </label>
                {customQuestions[question.id] && (
                  <label
                    className="clarification-custom-answer"
                    htmlFor={`clarification-custom-${question.id}`}
                  >
                    <span>Your answer</span>
                    <input
                      aria-label={`Custom answer for: ${question.prompt}`}
                      autoFocus
                      id={`clarification-custom-${question.id}`}
                      onChange={(event) => {
                        const value = event.target.value;
                        setCustomAnswers((current) => ({ ...current, [question.id]: value }));
                        setAnswers((current) => ({ ...current, [question.id]: value }));
                      }}
                      placeholder="Enter the answer that best matches your research"
                      type="text"
                      value={customAnswers[question.id] ?? ""}
                    />
                  </label>
                )}
              </fieldset>
            ))}
            <button
              aria-busy={draftingPlan}
              className="primary-button"
              disabled={!clarificationReady || draftingPlan || pending || manualEditPending}
              type="submit"
            >
              <AsyncButtonContent
                busy={draftingPlan}
                busyLabel="Drafting Plan…"
                idleLabel="Submit answers and draft Plan"
              />
            </button>
            {draftingPlan && <p className="sr-only" role="status">Drafting Plan. Please wait.</p>}
          </form>
        )}

        {session.currentPlan && session.clarification.submitted && !session.pendingPlanPatch && (
          <button
            className="secondary-button clarification-follow-up"
            disabled={manualEditPending || pending || Boolean(planningAction)}
            onClick={async () => {
              setPlanningAction("clarification");
              try {
                const updated = await execute(session.id, { type: "request_plan_clarification" });
                if (updated) setAnswers({});
              } finally {
                setPlanningAction(undefined);
              }
            }}
            type="button"
          >
            <AsyncButtonContent busy={planningAction === "clarification"} busyLabel="Preparing questions…" idleLabel="Ask follow-up questions" />
          </button>
        )}

        {session.pendingPlanPatch && (
          <PlanPatchReview
            key={session.pendingPlanPatch.id}
            disabled={manualEditPending || pending || Boolean(planningAction)}
            onApply={(acceptedFields) => execute(session.id, { type: "apply_plan_patch", acceptedFields })}
            onReject={() => execute(session.id, { type: "reject_plan_patch" })}
            proposal={session.pendingPlanPatch}
          />
        )}
      </div>

      {planningAction && <p role="status">{planningAction === "revision" ? "Preparing Plan changes…" : "Preparing follow-up questions…"}</p>}
      <StageChatComposer actionLabel={planningAction === "revision" ? "Preparing changes…" : "Propose change"} disabled={!session.currentPlan || manualEditPending || pending || Boolean(planningAction) || draftingPlan} id="plan-chat-input" label="Request a Plan revision" onChange={setDraft} onSubmit={submitChat} placeholder="Ask the model to change the current Plan…" value={draft} />
    </section>
  );
}
