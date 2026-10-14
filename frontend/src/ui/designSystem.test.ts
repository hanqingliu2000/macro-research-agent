import { readFileSync, readdirSync } from "node:fs";
import { extname, join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const root = join(process.cwd(), "src");
const read = (relativePath: string) => readFileSync(resolve(root, relativePath), "utf8");

function runtimeSource(directory: string): string {
  const absolute = resolve(root, directory);
  return runtimeSourceAt(absolute);
}

function runtimeSourceAt(absolute: string): string {
  return readdirSync(absolute, { withFileTypes: true }).map((entry) => {
    const path = join(absolute, entry.name);
    if (entry.isDirectory()) return runtimeSourceAt(path);
    if (![".ts", ".tsx"].includes(extname(entry.name)) || entry.name.includes(".test.")) return "";
    return readFileSync(path, "utf8");
  }).join("\n");
}

describe("Research Workbench design-system boundaries", () => {
  it("keeps shared and mode styles root-scoped", () => {
    for (const file of [
      "ui/styles/tokens.css",
      "ui/styles/workbench.css",
      "workflow/styles/stages.css",
      "agent/styles/agent.css",
    ]) {
      const unscoped = read(file)
        .split("\n")
        .filter((line) => /^\s*\.[a-z]/.test(line) && !line.trimStart().startsWith(".research-workbench"));
      expect(unscoped, file).toEqual([]);
    }
  });

  it("keeps the app stylesheet limited to reset and base utilities", () => {
    const base = read("app/styles.css");
    expect(base.split("\n").length).toBeLessThan(150);
    expect(base).not.toContain("agent-shell");
    expect(base).not.toContain("workflow-stage-layout");
    expect(base).not.toContain("Georgia");
  });

  it("ships one local vector asset family without structural Unicode icons", () => {
    const source = runtimeSource(".");
    expect(source).not.toMatch(/[＋✓↑↓×↶]/u);
    expect(read("ui/components/WorkbenchIcon.tsx")).toContain('strokeWidth="1.7"');
    expect(read("../public/mra-mark.svg")).toContain("<svg");
  });

  it("keeps neutral UI independent from both mode domains", () => {
    const source = runtimeSource("ui");
    expect(source).not.toMatch(/from\s+["'][^"']*(agent|workflow)/u);
  });

  it("composes shared chrome and Workflow primitives from focused components", () => {
    const shell = read("ui/components/WorkbenchShell.tsx");
    const planChat = read("workflow/pages/plan/PlanChat.tsx");
    const outputChat = read("workflow/pages/output/OutputRevisionChat.tsx");

    expect(shell).toContain("WorkbenchActivityBar");
    expect(shell).toContain("WorkbenchExplorer");
    expect(shell).toContain("WorkbenchStatusBar");
    expect(shell).not.toContain("NavLink");
    expect(planChat).toContain("StageChatComposer");
    expect(outputChat).toContain("StageChatComposer");
    expect(runtimeSource("workflow/pages").match(/SectionHeading/g)?.length ?? 0).toBeGreaterThanOrEqual(8);
  });

  it("retains responsive and reduced-motion contracts", () => {
    const shared = read("ui/styles/workbench.css");
    const agent = read("agent/styles/agent.css");
    const workflow = read("workflow/styles/stages.css");
    expect(shared).toContain("@media (max-width: 900px)");
    expect(shared).toContain("@media (max-width: 720px)");
    expect(shared).toContain("@media (max-width: 560px)");
    expect(shared).toContain("@media (prefers-reduced-motion: reduce)");
    expect(shared).not.toContain("min-height: 620px");
    expect(agent).toContain("@media (max-width: 1180px)");
    expect(workflow).toContain("@media (max-width: 1180px)");
  });

  it("bounds ultrawide workspaces and readable content", () => {
    const tokens = read("ui/styles/tokens.css");
    const agent = read("agent/styles/agent.css");
    const workflow = read("workflow/styles/stages.css");

    expect(tokens).toContain("--wb-workspace-max: 2360px");
    expect(tokens).toContain("--wb-agent-workspace-max: 2020px");
    expect(tokens).toContain("--wb-readable-width: 72ch");
    expect(workflow).toContain("width: clamp(420px, 32vw, 720px)");
    expect(agent).toContain("grid-template-columns: minmax(0, 1fr) clamp(320px, 18vw, 420px)");

    for (const viewport of [1440, 1920, 2560, 3840]) {
      const desktopMain = viewport - 48 - 244;
      const workflowWorkspace = Math.min(desktopMain, 2360);
      const workflowControl = Math.min(720, Math.max(420, viewport * 0.32));
      const agentWorkspace = Math.min(desktopMain, 2020);
      const agentProgress = Math.min(420, Math.max(320, viewport * 0.18));

      expect(workflowControl).toBeLessThanOrEqual(720);
      expect(workflowWorkspace - workflowControl).toBeGreaterThanOrEqual(680);
      expect(agentProgress).toBeGreaterThanOrEqual(320);
      expect(agentWorkspace - agentProgress).toBeLessThanOrEqual(1600);
    }
  });

  it("keeps compact Workflow controls inside their panels", () => {
    const workflow = read("workflow/styles/stages.css");

    expect(workflow).toContain("grid-template-columns: minmax(0, 1fr) auto");
    expect(workflow).toContain(".operation-catalog > .secondary-button");
    expect(workflow).toContain("max-width: 100%");
    expect(workflow).toContain(".stage-action-bar-compact");
    expect(workflow).toContain("background: #111a2a");
    expect(workflow).toContain(".pipeline-control-column > .stage-action-bar");
    expect(workflow).toContain("bottom: -12px");
    expect(workflow).toContain(".data-transfer-button");
    expect(workflow).toContain("white-space: normal");
  });
});
