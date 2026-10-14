import type { ModelResult } from "../../domain/types";
import { SectionHeading } from "../../components/SectionHeading";

function display(value: unknown) {
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 5 });
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value ?? "—");
}

export function ModelResultPreview({ results }: { results: ModelResult[] }) {
  if (!results.length) return null;
  return <section className="model-result-preview">
    <SectionHeading eyebrow="MODEL RESULTS" meta={<span>{results.length}</span>} title="Executed analysis" />
    {results.map((item) => {
      const rows = (item.result.statistics ??
        item.result.coefficients ??
        item.result.matrix ??
        item.result.groups) as Array<Record<string, unknown>> | undefined;
      const nullHypothesis = item.result.nullHypothesis;
      const forecasts = item.result.forecasts as Array<Record<string, unknown>> | undefined;
      const impulseResponses = item.result.impulseResponses as Array<Record<string, unknown>> | undefined;
      return <article key={item.id}>
        <header><strong>{item.kind.toUpperCase()}</strong><span>{item.sample.observations} observations · {item.sample.dropped} dropped</span></header>
        {typeof nullHypothesis === "string" ? <p className="model-result-hypothesis"><strong>Null hypothesis:</strong> {nullHypothesis}</p> : null}
        {rows?.length ? <div className="model-result-table-wrap"><table><thead><tr>{Object.keys(rows[0]).map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{Object.keys(rows[0]).map((column) => <td key={column}>{display(row[column])}</td>)}</tr>)}</tbody></table></div> : null}
        {forecasts?.length ? <div className="model-forecast-results"><h4>Forecast</h4><div className="model-result-table-wrap"><table><thead><tr>{Object.keys(forecasts[0]).map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{forecasts.map((row, index) => <tr key={index}>{Object.keys(forecasts[0]).map((column) => <td key={column}>{display(row[column])}</td>)}</tr>)}</tbody></table></div></div> : null}
        {impulseResponses?.length ? <div className="model-forecast-results"><h4>Impulse responses</h4><div className="model-result-table-wrap"><table><thead><tr>{Object.keys(impulseResponses[0]).map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{impulseResponses.map((row, index) => <tr key={index}>{Object.keys(impulseResponses[0]).map((column) => <td key={column}>{display(row[column])}</td>)}</tr>)}</tbody></table></div></div> : null}
        {item.result.fit ? <pre>{JSON.stringify(item.result.fit, null, 2)}</pre> : null}
        {item.warnings.length ? <ul className="model-result-warnings" aria-label="Model warnings">{item.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
        <small>Input {item.inputSnapshotHash.slice(0, 18)}… · Result {item.resultHash.slice(0, 18)}…</small>
      </article>;
    })}
  </section>;
}
