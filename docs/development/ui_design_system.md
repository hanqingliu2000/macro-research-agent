# Research Workbench UI design system

Updated: 2026-08-24

## Scope and isolation

Slate Workbench is the shared visual language for Workflow Mode and Agent Mode. Both use the same
dark tokens, Activity Bar, Explorer, main editor and local SVG icon family. Both modes omit redundant
Explorer headers/footers and the status bar so research controls receive the available height. Visual
sharing is limited to stateless presentation modules under `frontend/src/ui`.

The two modes continue to own separate route trees, providers, domain types, commands, sessions,
storage keys and future API repositories. `WorkbenchShell` receives already formatted display props;
it cannot import either mode's state or domain. A shared appearance does not authorize cross-mode
session lookup, conversion or mutation.

The product is a dense, persistent and inspectable developer workbench rather than a marketing
dashboard. It borrows familiar IDE organization without copying VS Code assets or controls.

## Workbench anatomy

Both modes use the same desktop grid, with mode-specific chrome density:

1. A 48 px Activity Bar for new work, Workflow Mode, Agent Mode and mode-appropriate settings.
2. A mode-specific Explorer containing only that mode's recent sessions. Both modes omit the
   repeated Explorer heading and store footer.
3. A compact page or session toolbar.
4. The current editor surface.
5. An optional 24 px status-bar slot in the shared shell. It is hidden in both current modes.

Workflow renders Plan, Data, Transformation and Output as editor tabs. Agent renders a prompt
editor on Home and a chat editor with a high-level autonomous-route outline. Below 900 px the
Explorer is hidden; below 560 px the Activity Bar becomes horizontal. Workflow split panels stack
below 1180 px, and Agent chat/progress panels also stack below 1180 px. Session rows collapse to their
essential name and state columns below 720 px.

Ultrawide screens use bounded editor surfaces rather than scaling every control with the viewport.
The Workflow session surface is capped at 2360 px and its control pane uses a 420–720 px clamp. The
Agent session surface is capped at 2020 px, with a 320–420 px route outline and no more than 1600 px
for the conversation. Home surfaces may use up to 1520 px in Workflow and 1440 px in Agent. Textual
research conclusions and chat messages use a 72-character readable measure; tables, code and data
grids retain their own wider overflow contracts.

## Tokens and typography

Shared tokens live in `frontend/src/ui/styles/tokens.css` below `.research-workbench`.

| Role | Token | Default |
|---|---|---|
| Canvas | `--wb-bg` | `#0f172a` |
| Activity bar | `--wb-activity` | `#0b1220` |
| Explorer | `--wb-sidebar` | `#111827` |
| Panel | `--wb-panel` | `#172033` |
| Raised panel | `--wb-panel-raised` | `#1b263b` |
| Primary text | `--wb-text` | `#f8fafc` |
| Secondary text | `--wb-text-secondary` | `#cbd5e1` |
| Muted text | `--wb-text-muted` | `#94a3b8` |
| Focus / selection | `--wb-blue` / `--wb-focus` | `#60a5fa` / `#93c5fd` |
| Execute / approve | `--wb-green-strong` | `#22c55e` |
| Warning / stale | `--wb-yellow` | `#fbbf24` |
| Error | `--wb-red` | `#fb7185` |

IBM Plex Sans and JetBrains Mono are preferred when installed locally. System UI, SFMono,
Consolas and Menlo are explicit offline fallbacks; the application does not make a runtime font
request. Controls use low-radius borders and restrained motion.

Do not enlarge the entire interface solely because a display is 4K. CSS viewport width, device
pixel ratio and browser/OS scaling are separate inputs. Dense metadata may remain compact, while
status text, analytical prose and tabular values must stay readable at the user's effective scale.

## Mode patterns

### Workflow

- Plan places stage-scoped chat beside the editable Plan.
- Data places source/preparation controls beside an IDE-like grid preview.
- Transformation uses an ordered operation outline, typed property editors and model jobs.
- Output uses an artifact explorer, preview and separate revision thread. Phase 1E adds a compact
  Review panel for deterministic and AI findings, guideline rule IDs, affected artifact, severity
  and typed patch diff. It does not expose model reasoning or raw tool payloads.
- Visual Review AI sees the direct artifact render. The web UI displays that same immutable render
  and structured findings; it does not capture its own page as review input.
- Checkpoints remain visible and upstream edits explicitly mark dependent work stale.
- The normal UI renders concise state-graph projections (stage availability, current/stale state,
  pending review and impact). Raw node/edge/attempt payloads remain an administrative or
  reproducibility surface rather than another end-user workflow panel.

### Agent

- Home uses an editor-style research prompt with optional CSV, JSON or XLSX attachments.
- Chat uses a message log with a separate high-level autonomous-route outline; raw trace stays in
  backend administration.
- Clarification remains a bounded form within the conversation.
- Results use dark chart/data/code/artifact panels with a semantic data table and copyable code.
- Agent status, attachment count and session history remain isolated in the Agent provider even
  when compact chrome does not display all of that metadata.

Green is reserved for explicit execution, approval and completed work. Blue denotes navigation,
focus and selection. Yellow denotes reviewable or in-progress state. Red denotes invalid or failed
state. State always includes text or an icon in addition to color.

## Assets

- `frontend/src/ui/components/WorkbenchIcon.tsx` is the local inline SVG family. Decorative SVGs
  are hidden from assistive technology; icon-only controls require an accessible name.
- `frontend/public/mra-mark.svg` is the application favicon/mark.
- Structural controls must not use Unicode or emoji as icons.
- No raster imagery or remote font asset is required for the current interface.

## Interaction and accessibility

- A skip link in both modes targets the shared main editor.
- Every interactive element has a visible `:focus-visible` outline.
- Modal dialogs move focus to Cancel, trap Tab/Shift+Tab, close on Escape and restore prior focus.
- Selected operations and artifacts expose `aria-pressed`.
- Agent file errors use an alert and are associated with the file input.
- Agent messages use a labelled live log; result data uses a native table with headers.
- Workflow stage icons, labels and semantic attributes communicate availability; active, stale and
  completed states also use font/icon color. Agent route steps retain explicit state text.
- Narrow-screen form controls use at least 16 px text and critical controls use 44 px targets.
- `prefers-reduced-motion: reduce` disables non-essential transitions.
- Automated acceptance uses DOM, accessibility, reducer, build and API assertions. Responsive
  contracts cover 1440, 1920, 2560 and 3840 px numerically while preserving the 560/720/900/1180
  px collapse points. It must not use a model-controlled browser or screenshot comparison.

## Maintenance boundaries

- `frontend/src/app/styles.css`: reset and genuinely global non-themed utilities only.
- `frontend/src/ui/styles/tokens.css`: shared Slate tokens.
- `frontend/src/ui/styles/workbench.css`: shared Workbench chrome, common controls, Workflow Home
  and Workflow Settings surfaces.
- `frontend/src/workflow/styles/stages.css`: Workflow-only routed stage surfaces, scoped under
  `.research-workbench-workflow`.
- `frontend/src/agent/styles/agent.css`: Agent-only prompt, chat, progress and result surfaces,
  scoped under `.research-workbench-agent`.

The neutral `ui` namespace cannot import `agent` or `workflow`; ESLint enforces this boundary.
Mode-specific visual components call their existing mode-specific service/context commands.

### Component ownership

- `WorkbenchShell` only composes the shared grid. `WorkbenchActivityBar`, `WorkbenchExplorer` and
  `WorkbenchStatusBar` own their individual navigation/chrome regions and consume presentation-only
  types from `workbenchTypes.ts`.
- Repeated Workflow headings use `SectionHeading`; Plan and Output text entry use
  `StageChatComposer`. These components receive values and callbacks but never dispatch commands or
  read Workflow context directly.
- Capability and skill availability badges consume registry projection props. Placeholder controls
  are disabled with an explanation and never dispatch an execution command.
- Domain-aware attachment handling stays in Agent Mode, and command-aware Plan/Data/Pipeline/Output
  controls stay in Workflow Mode. Similar appearance alone is not a reason to move business state
  into shared UI.
