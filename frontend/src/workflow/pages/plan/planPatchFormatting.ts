import type { PlanDraft } from "../../domain/types";

const FIELD_LABELS: Partial<Record<keyof PlanDraft, string>> = {
  objective: "Research objective",
  geographyIntent: "Geography intent",
  period: "Research period",
  geographyResolutions: "Geography resolution",
  dataSources: "Data sources",
  transformationIntents: "Transformations",
  modelIntents: "Models",
  capabilityInvocations: "Capability plan",
  deliverables: "Deliverables",
  assumptions: "Assumptions",
  warnings: "Cautions",
  unresolvedItems: "Blocking requirements",
};

export function planPatchFieldLabel(field: string) {
  return FIELD_LABELS[field as keyof PlanDraft] ?? humanize(field);
}

function humanize(value: string) {
  const spaced = value.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replaceAll("_", " ");
  return `${spaced.charAt(0).toUpperCase()}${spaced.slice(1)}`;
}
