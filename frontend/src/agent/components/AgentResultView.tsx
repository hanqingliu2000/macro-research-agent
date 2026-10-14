import { useState } from "react";

import { WorkbenchIcon } from "../../ui/components/WorkbenchIcon";
import type { AgentSession } from "../domain/types";
import { AgentDataPreview } from "./AgentDataPreview";

function CopyCodeButton({ code, label }: { code: string; label: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(code);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };
  const copied = copyState === "copied";
  return (
    <button aria-live="polite" className="agent-icon-button" onClick={copy} type="button">
      <WorkbenchIcon name={copied ? "check" : "file"} />
      {copied ? "Copied" : copyState === "failed" ? "Copy unavailable" : `Copy ${label}`}
    </button>
  );
}

export function AgentResultView({ session }: { session: AgentSession }) {
  const result = session.result;
  if (!result) return null;
  const latestInflation = result.data.filter((row) => row.period === "2024");
  const approved = !session.remote || ["completed", "awaiting_final_confirmation"].includes(session.status);

  return (
    <article className="agent-result">
      <div className="agent-result-heading">
        <div><p className="panel-kicker">{approved ? "RESEARCH DELIVERY" : "CANDIDATE OUTPUT"}</p><h2>{session.status === "completed" ? "Delivered research package" : approved ? "Research package ready for confirmation" : "Research package under review"}</h2></div>
        <span className="artifact-state artifact-ready">{approved ? "reviewed" : "candidate"}</span>
      </div>
      <p className="agent-conclusion">{result.conclusion}</p>

      <section className="agent-result-section">
        <h3>Key findings</h3>
        <ul>{result.findings.map((finding) => <li key={finding}>{finding}</li>)}</ul>
      </section>

      {!session.remote && <figure aria-describedby="agent-chart-source" className="agent-chart">
        <figcaption>Illustrative inflation comparison · 2024</figcaption>
        {latestInflation.map((row) => (
          <div className="agent-chart-row" key={row.economy}>
            <span>{row.economy}</span>
            <div aria-hidden="true"><i style={{ width: `${row.inflation * 22}px` }} /></div>
            <strong>{row.inflation.toFixed(1)}%</strong>
          </div>
        ))}
        <p id="agent-chart-source">Values are also available in the underlying data table.</p>
      </figure>}
      {session.remote && result.artifacts.filter(artifact => artifact.format === "svg").map(artifact => (
        <figure className="agent-chart" key={artifact.id}>
          <figcaption>{artifact.name}</figcaption><img alt={artifact.description} src={artifact.href} />
        </figure>
      ))}

      <section className="agent-result-section">
        <h3>Underlying data</h3>
        {session.remote && result.table ? <AgentDataPreview key={session.remote.run_id} initial={result.table} run={session.remote} /> : <>
        <div className="agent-data-table-scroll">
          <table className="agent-data-table">
            <caption className="sr-only">{session.remote ? "Underlying acquired data preview" : "Underlying mock inflation and policy-rate data"}</caption>
            {result.table ? <>
              <thead><tr>{result.table.columns.map(column => <th scope="col" key={column}>{column}</th>)}</tr></thead>
              <tbody>{result.table.rows.map((row, index) => <tr key={index}>{result.table?.columns.map(column =>
                <td key={column}>{row[column] === null ? "…" : String(row[column] ?? "")}</td>)}</tr>)}</tbody>
            </> : <><thead><tr><th scope="col">Economy</th><th scope="col">Period</th><th scope="col">Inflation</th><th scope="col">Policy rate</th></tr></thead>
            <tbody>{result.data.map((row) => (
              <tr key={`${row.economy}-${row.period}`}><th scope="row">{row.economy}</th><td>{row.period}</td><td>{row.inflation}</td><td>{row.policyRate}</td></tr>
            ))}</tbody></>}
          </table>
        </div>
        </>}
      </section>

      {(result.pythonCode || result.stataCode) && <div className="agent-code-grid">
        <section><div><h3>Python</h3><CopyCodeButton code={result.pythonCode} label="Python" /></div><pre><code>{result.pythonCode}</code></pre></section>
        <section><div><h3>Stata</h3><CopyCodeButton code={result.stataCode} label="Stata" /></div><pre><code>{result.stataCode}</code></pre></section>
      </div>}

      <section className="agent-result-section">
        <h3>Output files</h3>
        <ul className="agent-artifacts">
          {result.artifacts.map((artifact) => (
            <li key={artifact.id}><WorkbenchIcon name="file" /><span>
              {artifact.href ? <a download={artifact.name} href={artifact.href}>{artifact.name}</a> : <strong>{artifact.name}</strong>}
              <small>{artifact.format.replace("_", " ")} · {artifact.description}</small></span><span className="artifact-state artifact-ready">{session.status === "completed" ? "delivered" : "candidate"}</span></li>
          ))}
        </ul>
      </section>

      <details className="agent-provenance">
        <summary>Sources and caveats</summary>
        <section><h3>Sources</h3><ul>{result.sources.map((source) => <li key={source.dataset}>{source.provider} · {source.dataset} · {source.retrievedAt}</li>)}</ul></section>
        <section><h3>Caveats</h3><ul>{result.caveats.map((caveat) => <li key={caveat}>{caveat}</li>)}</ul></section>
      </details>
    </article>
  );
}
