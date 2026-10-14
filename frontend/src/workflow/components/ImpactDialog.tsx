import { type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";

import { STAGE_LABELS, type WorkflowStage } from "../domain/types";

export function ImpactDialog({
  title,
  stages,
  children,
  kicker = "UPSTREAM CHANGE",
  confirmLabel = "Confirm change",
  showImpactSummary = true,
  onCancel,
  onConfirm,
}: {
  title: string;
  stages: WorkflowStage[];
  children?: ReactNode;
  kicker?: string;
  confirmLabel?: string;
  showImpactSummary?: boolean;
  onCancel(): void;
  onConfirm(): void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => previous?.focus();
  }, []);

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
      return;
    }
    if (event.key !== "Tab") return;
    const controls = dialogRef.current?.querySelectorAll<HTMLElement>(
      "button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled)",
    );
    if (!controls?.length) return;
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="impact-backdrop" role="presentation">
      <section aria-labelledby="impact-title" aria-modal="true" className="impact-dialog" onKeyDown={handleKeyDown} ref={dialogRef} role="dialog">
        <p className="panel-kicker">{kicker}</p>
        <h2 id="impact-title">{title}</h2>
        {children}
        {showImpactSummary && (stages.length > 0 ? (
          <>
            <p>The current outputs below will remain readable but become stale:</p>
            <ul>{stages.map((stage) => <li key={stage}>{STAGE_LABELS[stage]}</li>)}</ul>
          </>
        ) : (
          <p>No reached downstream stage will be invalidated.</p>
        ))}
        {showImpactSummary && <p className="impact-note">Nothing reruns automatically.</p>}
        <div className="dialog-actions">
          <button className="secondary-button" onClick={onCancel} ref={cancelRef} type="button">Cancel</button>
          <button className="primary-button" onClick={onConfirm} type="button">{confirmLabel}</button>
        </div>
      </section>
    </div>
  );
}
