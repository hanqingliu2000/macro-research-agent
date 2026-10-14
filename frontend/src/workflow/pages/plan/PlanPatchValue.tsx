import type { ReactNode } from "react";

import { DELIVERABLE_LABELS } from "../../domain/types";

const HIDDEN_KEYS = new Set(["id", "capabilityVersion"]);

export function PlanPatchValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="patch-empty">None</span>;
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (typeof value === "string" || typeof value === "number") return <span>{value}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="patch-empty">None</span>;
    if (value.every((item) => typeof item !== "object" || item === null)) {
      return (
        <ul className="patch-value-list">
          {value.map((item, index) => <li key={`${String(item)}-${index}`}>{scalar(item)}</li>)}
        </ul>
      );
    }
    return (
      <div className="patch-value-collection">
        {value.map((item, index) => (
          <article className="patch-value-card" key={index}>
            <ObjectPreview value={item as Record<string, unknown>} />
          </article>
        ))}
      </div>
    );
  }
  return <ObjectPreview value={value as Record<string, unknown>} />;
}

function ObjectPreview({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value).filter(([key]) => !HIDDEN_KEYS.has(key));
  return (
    <dl className="patch-value-details">
      {entries.map(([key, item]) => (
        <div key={key}>
          <dt>{nestedLabel(key)}</dt>
          <dd><PlanPatchValue value={item} /></dd>
        </div>
      ))}
    </dl>
  );
}

function nestedLabel(key: string) {
  if (key in DELIVERABLE_LABELS) {
    return DELIVERABLE_LABELS[key as keyof typeof DELIVERABLE_LABELS];
  }
  return humanize(key);
}

function humanize(value: string) {
  const spaced = value.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replaceAll("_", " ");
  return `${spaced.charAt(0).toUpperCase()}${spaced.slice(1)}`;
}

function scalar(value: unknown): ReactNode {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
