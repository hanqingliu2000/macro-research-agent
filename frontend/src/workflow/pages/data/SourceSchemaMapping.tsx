import type { LogicalRole, WorkflowSession } from "../../domain/types";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { SectionHeading } from "../../components/SectionHeading";

const roles: LogicalRole[] = [
  "entity_code",
  "indicator_code",
  "frequency",
  "period",
  "value",
  "attribute",
  "ignore",
];

export function SourceSchemaMapping({ session }: { session: WorkflowSession }) {
  const { execute } = useWorkflow();
  const draft = session.data.sourceMappingDraft;
  if (!draft) return null;
  return (
    <section className="data-control-card mapping-wizard source-schema-mapping">
      <SectionHeading eyebrow="SOURCE SCHEMA" title="Map uploaded columns" />
      <p><strong>{draft.filename}</strong></p>
      <div className="mapping-grid">
        <strong>Uploaded column</strong><strong>Logical role</strong>
        {draft.sourceColumns.map((column) => (
          <label key={column}>
            <span>{column}</span>
            <select
              aria-label={`Map uploaded ${column}`}
              onChange={(event) => execute(session.id, {
                type: "map_source_column",
                sourceColumn: column,
                role: event.target.value as LogicalRole,
              })}
              value={draft.mappings[column] ?? "attribute"}
            >
              {roles.map((role) => <option key={role} value={role}>{role}</option>)}
            </select>
          </label>
        ))}
      </div>
      {draft.errors.map((error) => <p className="mapping-error" key={error}>{error}</p>)}
      <div className="mapping-actions">
        <button
          className="primary-button"
          onClick={() => execute(session.id, { type: "validate_source_mapping" })}
          type="button"
        >
          Validate and load data
        </button>
      </div>
    </section>
  );
}
