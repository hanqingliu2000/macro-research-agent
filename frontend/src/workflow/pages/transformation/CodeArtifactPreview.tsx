import { useEffect, useState } from "react";

import type { CodeArtifact } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";
import { useWorkflow } from "../../state/WorkflowContextCore";

export function CodeArtifactPreview({ sessionId, artifacts }: { sessionId: string; artifacts: CodeArtifact[] }) {
  const { getPipelineCode } = useWorkflow();
  const [selectedId, setSelectedId] = useState(artifacts[0]?.id ?? "");
  const [content, setContent] = useState("");
  const selected = artifacts.find((artifact) => artifact.id === selectedId) ?? artifacts[0];

  useEffect(() => {
    if (!selected) return;
    let current = true;
    void getPipelineCode(sessionId, selected.id).then((record) => {
      if (current) setContent(record.content);
    }).catch(() => {
      if (current) setContent("");
    });
    return () => { current = false; };
  }, [getPipelineCode, selected, sessionId]);

  if (!selected) return null;
  return <section className="code-artifact-preview">
    <SectionHeading eyebrow="REPRODUCTION CODE" meta={<span>{artifacts.length}</span>} title="Generated from reviewed specifications" />
    <div className="code-artifact-tabs">{artifacts.map((artifact) => <button aria-pressed={artifact.id === selected.id} className={artifact.id === selected.id ? "selected" : ""} key={artifact.id} onClick={() => setSelectedId(artifact.id)} type="button">{artifact.language}</button>)}</div>
    <pre><code>{content}</code></pre>
    <footer><small>{selected.checksum.slice(0, 24)}…</small><a className="secondary-button" download href={`/api/v1/workflow/sessions/${encodeURIComponent(sessionId)}/pipeline/code/${encodeURIComponent(selected.id)}/download`}>Download {selected.filename}</a></footer>
  </section>;
}
