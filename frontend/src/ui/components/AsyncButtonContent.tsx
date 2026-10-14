export function AsyncButtonContent({
  busy,
  busyLabel,
  idleLabel,
}: {
  busy: boolean;
  busyLabel: string;
  idleLabel: string;
}) {
  return (
    <span className="async-button-content">
      {busy && <span aria-hidden="true" className="async-button-spinner" />}
      <span>{busy ? busyLabel : idleLabel}</span>
    </span>
  );
}
