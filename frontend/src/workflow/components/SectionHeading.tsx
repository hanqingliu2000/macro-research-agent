import type { ReactNode } from "react";

export function SectionHeading({
  className = "section-heading-compact",
  eyebrow,
  level = 2,
  meta,
  title,
}: {
  className?: string;
  eyebrow: string;
  level?: 2 | 3;
  meta?: ReactNode;
  title: string;
}) {
  return (
    <div className={className}>
      <div>
        <p className="panel-kicker">{eyebrow}</p>
        {level === 2 ? <h2>{title}</h2> : <h3>{title}</h3>}
      </div>
      {meta}
    </div>
  );
}
