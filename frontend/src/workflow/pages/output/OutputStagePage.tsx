import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { StaleBanner } from "../../components/StaleBanner";
import { useWorkflowSession } from "../../components/useWorkflowSession";
import { useWorkflow } from "../../state/WorkflowContextCore";
import { ArtifactPreview } from "./ArtifactPreview";
import { DeliverableControls } from "./DeliverableControls";
import { ExportMenu } from "./ExportMenu";
import { OutputRevisionChat } from "./OutputRevisionChat";
import { OutputReviewPanel } from "./OutputReviewPanel";
import { OutputGenerationRecovery } from "./OutputGenerationRecovery";

export function OutputStagePage() {
  const session = useWorkflowSession();
  const { execute, forkSession, pending } = useWorkflow();
  const navigate = useNavigate();
  const stale = session.stageHealth.output === "stale";
  const [completedSelection, setCompletedSelection] = useState<string>();
  const selectedArtifactId = completedSelection ?? session.output.selectedArtifactId;
  const generationFailed = session.pipeline.outputGeneration?.status === "failed";
  const selectArtifact = (artifactId: string) => {
    if (session.status === "completed") {
      setCompletedSelection(artifactId);
      return;
    }
    void execute(session.id, { type: "select_artifact", artifactId });
  };
  return (
    <>
      <StaleBanner session={session} stage="output" />
      <div className="workflow-stage-layout output-stage-layout">
        <div className="output-control-column">
          {generationFailed ? (
            <OutputGenerationRecovery
              onRetry={() => execute(session.id, { type: "retry_output_generation" })}
              pending={pending}
              session={session}
            />
          ) : (
            <>
              <DeliverableControls disabled={stale} onSelect={selectArtifact} selectedArtifactId={selectedArtifactId} session={session} />
              <OutputReviewPanel disabled={stale || session.status === "completed"} session={session} />
              {session.output.revisionCapability !== false && <OutputRevisionChat disabled={stale || session.status === "completed"} session={session} />}
              {session.output.limitations?.length ? <section className="output-limitations"><p className="panel-kicker">LIMITATIONS</p><ul>{session.output.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
            </>
          )}
        </div>
        <aside className="output-preview-column">
          {!generationFailed && (
            <>
              <ArtifactPreview selectedArtifactId={selectedArtifactId} session={session} />
              <ExportMenu
                disabled={stale || session.status === "completed"}
                onContinue={() => {
                  void forkSession(session.id).then((child) => {
                    navigate(`/sessions/${child.id}/output`);
                  }).catch(() => undefined);
                }}
                onFinish={(acceptWarnings) => execute(session.id, { type: "finalize_output", acceptWarnings })}
                session={session}
              />
            </>
          )}
        </aside>
      </div>
    </>
  );
}
