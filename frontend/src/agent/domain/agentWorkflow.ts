import type {
  AgentAttachment,
  AgentMessage,
  AgentResult,
  AgentSession,
  AgentStep,
} from "./types";

function now() {
  return new Date().toISOString();
}

function identifier(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function message(role: AgentMessage["role"], body: string, label?: string): AgentMessage {
  return { id: identifier("agent-message"), role, body, label, createdAt: now() };
}

export const agentClarificationQuestions = [
  {
    id: "geography",
    prompt: "Which geographic scope should I use?",
    options: ["United States, euro area and Japan", "Advanced economies", "Emerging markets"],
  },
  {
    id: "period",
    prompt: "Which period and frequency should anchor the analysis?",
    options: ["2019–latest, quarterly", "2010–latest, annual", "Use the attached data coverage"],
  },
  {
    id: "deliverable",
    prompt: "What should the primary deliverable emphasize?",
    options: ["Research note with charts", "Clean dataset and code", "Model results and robustness"],
  },
];

function initialSteps(): AgentStep[] {
  return [
    {
      id: "understand",
      nodeKind: "clarification_batch",
      label: "Understand the question",
      status: "in_progress",
      summary: "Confirm scope, period and expected output.",
    },
    {
      id: "acquire",
      nodeKind: "data_acquisition",
      label: "Acquire approved data",
      status: "pending",
      summary: "Use configured connectors and attached files only.",
    },
    {
      id: "prepare",
      nodeKind: "transformation",
      label: "Prepare the dataset",
      status: "pending",
      summary: "Map identifiers, filter observations and document transformations.",
    },
    {
      id: "analyze",
      nodeKind: "model_execution",
      label: "Analyze",
      status: "pending",
      summary: "Run the selected descriptive or econometric workflow.",
    },
    {
      id: "report",
      nodeKind: "final_response",
      label: "Package results",
      status: "pending",
      summary: "Return conclusions, charts, data and reproducible code.",
    },
  ];
}

export function createAgentSession(
  request: string,
  attachments: AgentAttachment[],
): AgentSession {
  const createdAt = now();
  return {
    id: identifier("agent-session"),
    title: request.length > 54 ? `${request.slice(0, 51)}…` : request,
    request,
    status: "clarifying",
    createdAt,
    updatedAt: createdAt,
    attachments,
    messages: [
      message("user", request),
      message(
        "agent",
        "I need three choices before I can select data tools and run the research workflow.",
        "Clarification",
      ),
    ],
    clarification: {
      questions: agentClarificationQuestions,
      answers: {},
      submitted: false,
    },
    steps: initialSteps(),
  };
}

function mockResult(): AgentResult {
  return {
    conclusion:
      "Inflation fell across the comparison group after its 2022 peak, but the pace of normalization and the associated policy-rate path differed materially.",
    findings: [
      "The euro area shows the largest peak-to-latest decline in this illustrative sample.",
      "Japan's inflation path is lower and later, alongside a smaller policy-rate adjustment.",
      "The cross-country result is descriptive and should not be interpreted as a causal policy estimate.",
    ],
    caveats: [
      "This screen uses deterministic mock observations; production runs must record connector query parameters and vintages.",
      "Definitions and seasonal-adjustment conventions require review before publication.",
    ],
    data: [
      { economy: "United States", period: "2022", inflation: 8.0, policyRate: 4.4 },
      { economy: "United States", period: "2024", inflation: 2.9, policyRate: 4.3 },
      { economy: "Euro area", period: "2022", inflation: 8.4, policyRate: 2.5 },
      { economy: "Euro area", period: "2024", inflation: 2.4, policyRate: 3.0 },
      { economy: "Japan", period: "2022", inflation: 2.5, policyRate: -0.1 },
      { economy: "Japan", period: "2024", inflation: 2.7, policyRate: 0.25 },
    ],
    pythonCode: `import pandas as pd\n\ndf = pd.read_csv("analysis_data.csv")\nsummary = df.groupby("economy")[["inflation", "policy_rate"]].mean()\nprint(summary)`,
    stataCode: `import delimited "analysis_data.csv", clear\nencode economy, gen(economy_id)\nxtset economy_id year\ncollapse (mean) inflation policy_rate, by(economy)\nlist`,
    artifacts: [
      { id: "agent-note", name: "research_note.xlsx", format: "xlsx", description: "Charts, tables and source notes" },
      { id: "agent-data", name: "analysis_data.csv", format: "csv", description: "Tidy underlying mock data" },
      { id: "agent-chart", name: "inflation_comparison.png", format: "png", description: "Publication-style chart" },
      { id: "agent-python", name: "run_research.py", format: "python", description: "Reproducible Python workflow" },
      { id: "agent-stata", name: "run_research.do", format: "stata_do", description: "Equivalent Stata workflow" },
    ],
    sources: [
      { provider: "IMF", dataset: "Mock WEO extract", retrievedAt: now() },
      { provider: "World Bank", dataset: "Mock WDI extract", retrievedAt: now() },
    ],
  };
}

export function completeAgentRun(
  session: AgentSession,
  answers: Record<string, string>,
): AgentSession {
  const updatedAt = now();
  const answerSummary = session.clarification.questions
    .map((question) => answers[question.id])
    .filter(Boolean)
    .join(" · ");
  return {
    ...session,
    status: "completed",
    updatedAt,
    clarification: { ...session.clarification, answers, submitted: true },
    steps: session.steps.map((step) => ({ ...step, status: "completed" as const })),
    result: mockResult(),
    messages: [
      ...session.messages,
      message("user", answerSummary, "Clarification answers"),
      message(
        "agent",
        "The mock run is complete. I selected allowlisted data connectors, prepared the sample and packaged the findings with data and code.",
        "Research complete",
      ),
    ],
  };
}

export function appendAgentMessage(session: AgentSession, body: string): AgentSession {
  return {
    ...session,
    updatedAt: now(),
    messages: [
      ...session.messages,
      message("user", body),
      message(
        "agent",
        "I recorded that follow-up for this Agent session. A production run would route it through a new typed decision without changing Workflow sessions.",
      ),
    ],
  };
}
