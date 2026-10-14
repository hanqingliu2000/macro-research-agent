import type { ReactNode } from "react";

export function CheckpointBar({
  actionLabel,
  compact = false,
  detail,
  disabled,
  leading,
  onAction,
  title,
}: {
  actionLabel: string;
  compact?: boolean;
  detail?: string;
  disabled: boolean;
  leading?: ReactNode;
  onAction(): void;
  title?: string;
}) {
  return (
    <div className={`stage-action-bar${compact ? " stage-action-bar-compact" : ""}`}>
      {!compact && <div>{leading ?? <><strong>{title}</strong><span>{detail}</span></>}</div>}
      <button className="primary-button" disabled={disabled} onClick={onAction} type="button">
        {actionLabel}
      </button>
    </div>
  );
}
