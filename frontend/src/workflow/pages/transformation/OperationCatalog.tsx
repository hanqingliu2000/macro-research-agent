import { useState } from "react";

import type { TransformationOperationKind } from "../../domain/types";

const catalog: Array<[TransformationOperationKind, string, string]> = [
  ["lag", "Lag", "Shift a selected series backward."],
  ["lead", "Lead", "Shift a selected series forward."],
  ["difference", "Difference", "Calculate a first or seasonal difference."],
  ["yoy_growth", "Year-on-year growth", "Calculate frequency-aware annual growth."],
  ["period_growth", "Period growth", "Calculate period-on-period growth."],
  ["log", "Natural logarithm", "Apply log after value validation."],
  ["rebase_index", "Rebase index", "Set a reviewed base period to 100."],
  ["unit_conversion", "Unit conversion", "Apply an explicit factor and offset and update the unit."],
  ["frequency_conversion", "Frequency conversion", "Aggregate with reviewed calendar and completeness rules."],
  ["rolling_mean", "Rolling mean", "Create a typed rolling window."],
  ["group_aggregation", "Group aggregation", "Use confirmed members and an allowlisted aggregator."],
];

export function OperationCatalog({
  disabled,
  onAdd,
}: {
  disabled: boolean;
  onAdd(operation: TransformationOperationKind): void;
}) {
  const [selected, setSelected] = useState<TransformationOperationKind>("lag");
  const current = catalog.find(([kind]) => kind === selected)!;
  return (
    <section className="pipeline-card operation-catalog">
      <p className="panel-kicker">OPERATION CATALOG</p>
      <h2>Add a typed transformation</h2>
      <select aria-label="Transformation operation" disabled={disabled} onChange={(event) => setSelected(event.target.value as TransformationOperationKind)} value={selected}>
        {catalog.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
      </select>
      <p>{current[2]}</p>
      <button className="secondary-button" disabled={disabled} onClick={() => onAdd(selected)} type="button">Add to operation chain</button>
    </section>
  );
}
