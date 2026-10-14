import { Link } from "react-router-dom";

export function WorkflowNotFoundPage() {
  return (
    <main className="not-found-page">
      <p className="eyebrow">NOT FOUND</p>
      <h1>This Workflow view does not exist.</h1>
      <Link className="primary-button" to="/">Return to sessions</Link>
    </main>
  );
}
