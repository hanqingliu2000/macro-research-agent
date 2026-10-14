import { NavLink } from "react-router-dom";

import { WorkbenchIcon } from "./WorkbenchIcon";
import type { WorkbenchMode, WorkbenchRecentItem } from "./workbenchTypes";

export function WorkbenchExplorer({
  explorerLabel,
  collapsed,
  onToggle,
  footerDetail,
  footerTitle,
  homePath,
  mode,
  newLabel,
  recent,
  recentLabel,
  showHeader,
  showFooter,
}: {
  explorerLabel: string;
  collapsed: boolean;
  onToggle(): void;
  footerDetail?: string;
  footerTitle?: string;
  homePath: string;
  mode: WorkbenchMode;
  newLabel: string;
  recent: WorkbenchRecentItem[];
  recentLabel: string;
  showHeader: boolean;
  showFooter: boolean;
}) {
  const contentId = `workbench-explorer-content-${mode}`;
  return (
    <aside aria-label={explorerLabel} className="workbench-explorer">
      <button
        aria-controls={contentId}
        aria-expanded={!collapsed}
        aria-label={collapsed ? `Expand ${explorerLabel}` : `Collapse ${explorerLabel}`}
        className="explorer-toggle"
        onClick={onToggle}
        type="button"
      >
        <WorkbenchIcon name={collapsed ? "chevron-right" : "chevron-left"} />
        <span>{collapsed ? "Expand" : "Collapse"} {explorerLabel}</span>
      </button>
      {showHeader && (
        <header className="explorer-header">
          <span>{explorerLabel}</span><small>{mode}</small>
        </header>
      )}
      <div className="workbench-explorer-content" id={contentId}>
        <NavLink className="new-research-button" end to={homePath}>
          <WorkbenchIcon name="plus" />{newLabel}
        </NavLink>
        <div className="rail-section">
          <p className="rail-label"><span>{recentLabel}</span><small>{recent.length}</small></p>
          <div className="recent-list">
            {recent.map((item) => (
              <NavLink className="recent-session" key={item.id} title={item.title} to={item.to}>
                <WorkbenchIcon name="file" />
                <span><strong>{item.title}</strong><small>{item.status}</small></span>
              </NavLink>
            ))}
          </div>
        </div>
        {showFooter && footerTitle && footerDetail && (
          <div className="rail-footer">
            <span className="status-dot" />
            <span><strong>{footerTitle}</strong><small>{footerDetail}</small></span>
          </div>
        )}
      </div>
    </aside>
  );
}
