import type { WorkflowSession } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";

export function DeliverableControls({ session, disabled, selectedArtifactId, onSelect }: { session: WorkflowSession; disabled: boolean; selectedArtifactId?: string; onSelect: (artifactId: string) => void }) {
  return (
    <section className="output-control-card">
      <SectionHeading eyebrow="ARTIFACT SET" meta={<span>{session.output.guidelineVersion}</span>} title="Generated deliverables" />
      <div className="output-artifact-list">
        {session.output.artifacts.map((artifact) => (
          <button aria-label={`${artifact.name}, ${artifact.status}`} aria-pressed={selectedArtifactId === artifact.id} className={selectedArtifactId === artifact.id ? "selected" : ""} disabled={disabled} key={artifact.id} onClick={() => onSelect(artifact.id)} type="button">
            <span className="artifact-format">{artifact.format.replace("_", " ")}</span>
            <div><strong>{artifact.name}</strong><small>{artifact.description}</small></div>
          </button>
        ))}
      </div>
    </section>
  );
}
