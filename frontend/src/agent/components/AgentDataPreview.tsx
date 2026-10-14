import { useState } from "react";
import type { AgentResult, BackendAgentRun } from "../domain/types";
import { agentRunPath } from "../services/httpAgentService";

type Page = NonNullable<AgentResult["table"]> & { offset?: number };

export function AgentDataPreview({ initial, run }: { initial: Page; run: BackendAgentRun }) {
  const [page, setPage] = useState(initial);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async (next: number) => {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${agentRunPath(run)}/data-preview?offset=${next}&limit=12`);
      if (!response.ok) throw new Error("The data page could not be loaded.");
      const data = await response.json() as Page;
      setPage(data); setOffset(next);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  return <>
    <div className="agent-data-table-scroll"><table className="agent-data-table">
      <caption className="sr-only">Underlying acquired data preview</caption>
      <thead><tr>{page.columns.map(column => <th scope="col" key={column}>{column}</th>)}</tr></thead>
      <tbody>{page.rows.map((row, index) => <tr key={offset + index}>{page.columns.map(column =>
        <td key={column}>{row[column] === null ? "…" : String(row[column] ?? "")}</td>)}</tr>)}</tbody>
    </table></div>
    <div className="agent-control-buttons" aria-label="Data pagination">
      <button type="button" className="secondary-button" disabled={busy || offset === 0} onClick={() => void load(Math.max(0, offset - 12))}>Previous rows</button>
      <span aria-live="polite">Rows {offset + 1}–{offset + page.rows.length} of {page.total_rows}</span>
      <button type="button" className="secondary-button" disabled={busy || offset + page.rows.length >= page.total_rows} onClick={() => void load(offset + 12)}>Next rows</button>
    </div>
    {error && <p role="alert">{error}</p>}
  </>;
}
