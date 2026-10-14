import { useWorkflow } from "../state/WorkflowContextCore";

const connectors = [
  ["AVAILABLE", "Local XLSX / CSV / JSON", "Local intake and controlled workbook round trip."],
  ["PLANNED", "IMF Data", "SDMX discovery and fetch do not have an executable handler yet."],
  ["P1", "World Bank", "Planned controlled API connector."],
  ["P1", "OECD / Eurostat / ECB / BIS", "Planned regional provider adapters."],
];

export function WorkflowSettingsPage() {
  const { resetDemo } = useWorkflow();
  return (
    <main className="settings-page">
      <header className="simple-page-header">
        <div><p className="eyebrow">SETTINGS</p><h1>Local environment</h1><p>Review the current runtime and controlled connector boundary.</p></div>
        <button className="secondary-button" onClick={() => { void resetDemo(); }} type="button">Reset Workflow demo</button>
      </header>
      <section className="settings-grid">
        <article className="settings-card">
          <p className="panel-kicker">MODEL PROFILE</p><h2>Development runtime</h2>
          <dl className="definition-list">
            <div><dt>Local provider</dt><dd>Deterministic offline adapter</dd></div>
            <div><dt>Remote Output review</dt><dd><span className="configuration-status">Not configured</span></dd></div>
            <div><dt>Provider / model</dt><dd>To be selected</dd></div>
            <div><dt>API credential</dt><dd>Not configured</dd></div>
            <div><dt>LLM data boundary</dt><dd>Read-only, session- and stage-bound values</dd></div>
          </dl>
          <p className="settings-helper">Remote artifact and data disclosure remains disabled until an approved provider profile, model and credential are configured.</p>
        </article>
        <article className="settings-card">
          <p className="panel-kicker">STORAGE</p><h2>Isolated Workflow v2</h2>
          <dl className="definition-list"><div><dt>Sessions</dt><dd>Mode-isolated durable store</dd></div><div><dt>Trace</dt><dd>Append-only backend audit trail</dd></div></dl>
        </article>
      </section>
      <section className="connector-section">
        <div className="section-title-row"><div><p className="eyebrow">CONTROLLED SOURCES</p><h2>P0 and P1 roadmap</h2></div></div>
        <div className="connector-grid">
          {connectors.map(([priority, name, description]) => (
            <article className="connector-card" key={name}><span className="priority-tag">{priority}</span><h3>{name}</h3><p>{description}</p></article>
          ))}
        </div>
      </section>
    </main>
  );
}
