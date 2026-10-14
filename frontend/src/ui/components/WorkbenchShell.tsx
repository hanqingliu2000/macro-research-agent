import { useEffect, useState } from "react";

import { WorkbenchActivityBar } from "./WorkbenchActivityBar";
import { WorkbenchExplorer } from "./WorkbenchExplorer";
import { WorkbenchStatusBar } from "./WorkbenchStatusBar";
import type { WorkbenchShellProps } from "./workbenchTypes";

export type { WorkbenchRecentItem, WorkbenchShellProps, WorkbenchStatusItem } from "./workbenchTypes";

export function WorkbenchShell({
  brandMark,
  children,
  explorerLabel,
  footerDetail,
  footerTitle,
  homePath,
  mode,
  newLabel,
  recent,
  recentLabel,
  settingsPath,
  showExplorerHeader = true,
  showRailFooter = true,
  showStatusBar = true,
  statusItems = [],
  statusLabel,
}: WorkbenchShellProps) {
  const explorerStorageKey = `workbench-explorer-collapsed-${mode}-${explorerLabel}`;
  const [explorerCollapsed, setExplorerCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(explorerStorageKey) === "true";
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(explorerStorageKey, String(explorerCollapsed));
  }, [explorerCollapsed, explorerStorageKey]);

  return (
    <div
      className={`research-workbench research-workbench-${mode}${explorerCollapsed ? " workbench-explorer-collapsed" : ""}${showStatusBar ? "" : " workbench-no-status-bar"}`}
    >
      <a className="workbench-skip-link" href="#research-workbench-main">Skip to research workspace</a>
      <WorkbenchActivityBar brandMark={brandMark} homePath={homePath} mode={mode} settingsPath={settingsPath} />
      <WorkbenchExplorer
        collapsed={explorerCollapsed}
        onToggle={() => setExplorerCollapsed((current) => !current)}
        explorerLabel={explorerLabel}
        footerDetail={footerDetail}
        footerTitle={footerTitle}
        homePath={homePath}
        mode={mode}
        newLabel={newLabel}
        recent={recent}
        recentLabel={recentLabel}
        showFooter={showRailFooter}
        showHeader={showExplorerHeader}
      />
      <div className="workbench-main" id="research-workbench-main" tabIndex={-1}>{children}</div>
      {showStatusBar && <WorkbenchStatusBar items={statusItems} label={statusLabel} />}
    </div>
  );
}
