export function StageChatComposer({
  actionLabel,
  disabled,
  id,
  label,
  onChange,
  onSubmit,
  placeholder,
  value,
}: {
  actionLabel: string;
  disabled: boolean;
  id: string;
  label: string;
  onChange(value: string): void;
  onSubmit(): void;
  placeholder: string;
  value: string;
}) {
  return (
    <form className="stage-chat-composer" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <label className="sr-only" htmlFor={id}>{label}</label>
      <textarea disabled={disabled} id={id} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} rows={3} value={value} />
      <div><button className="composer-send" disabled={disabled || !value.trim()} type="submit">{actionLabel}</button></div>
    </form>
  );
}
