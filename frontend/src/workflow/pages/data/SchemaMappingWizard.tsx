import type { ChangeEvent } from "react";

import type { LogicalRole, WorkflowSession } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { WorkbenchIcon } from "../../../ui/components/WorkbenchIcon";

const roles: LogicalRole[] = ["series_id", "entity_code", "indicator_code", "frequency", "period", "value", "attribute", "ignore"];

export function SchemaMappingWizard({
  disabled,
  onCommit,
  session,
}: {
  disabled: boolean;
  onCommit(): void;
  session: WorkflowSession;
}) {
  const { execute, importRoundTrip } = useWorkflow();
  const draft = session.data.roundTripDraft;
  const chooseFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) importRoundTrip(session.id, file);
  };
  if (!draft) {
    return (
      <div className="data-inline-control">
        <label className={`data-transfer-button data-transfer-import file-label${disabled ? " disabled" : ""}`} htmlFor="roundtrip-import"><WorkbenchIcon name="import" />Reimport cleaned XLSX</label>
        <input accept=".xlsx" className="sr-only" disabled={disabled} id="roundtrip-import" onChange={chooseFile} type="file" />
      </div>
    );
  }
  return (
    <section className="data-control-card mapping-wizard">
      <SectionHeading eyebrow="REIMPORT" meta={<span className={`mapping-state mapping-${draft.state}`}>{draft.state}</span>} title="Schema mapping wizard" />
      <p><strong>{draft.filename}</strong></p>
      <p className="mapping-manifest">Manifest {draft.manifestVerified ? "verified" : "mismatch"} · checksum {draft.workbookChecksum} · formulas {draft.formulasMaterialized ? "materialized" : "detected"}</p>
      <div className="mapping-grid">
        <strong>Workbook column</strong><strong>Canonical role</strong>
        {draft.sourceColumns.map((column) => (
          <label key={column}><span>{column}</span><select aria-label={`Map ${column}`} value={draft.mappings[column] ?? "ignore"} onChange={(event) => execute(session.id, { type: "map_round_trip_column", sourceColumn: column, role: event.target.value as LogicalRole })}>{roles.map((role) => <option key={role} value={role}>{role}</option>)}</select></label>
        ))}
      </div>
      {draft.warnings.map((warning) => <p className="mapping-warning" key={warning}>{warning}</p>)}
      {draft.errors.map((error) => <p className="mapping-error" key={error}>{error}</p>)}
      <div className="mapping-actions">
        <button className="secondary-button" onClick={() => execute(session.id, { type: "validate_round_trip" })} type="button">Validate mapping</button>
        <button className="primary-button" disabled={draft.state !== "validated"} onClick={onCommit} type="button">Use as active dataset</button>
      </div>
    </section>
  );
}
