import type { WorkflowSession } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";

export function OperationHistory({ session }: { session: WorkflowSession }) {
  return (
    <section className="data-control-card">
      <SectionHeading eyebrow="PREPARATION HISTORY" meta={<span>{session.data.operations.length}</span>} title="Reversible data operations" />
      {session.data.operations.length ? (
        <ol className="operation-history">
          {session.data.operations.map((operation, index) => (
            <li key={operation.id}><span>{index + 1}</span><div><strong>{operation.label}</strong><small>{operation.inputSnapshotId} → {operation.outputSnapshotId}</small></div></li>
          ))}
        </ol>
      ) : <p className="empty-copy">No preparation operation has changed the connector snapshot.</p>}
    </section>
  );
}
