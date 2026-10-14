import { WorkbenchIcon } from "./WorkbenchIcon";
import type { WorkbenchStatusItem } from "./workbenchTypes";

export function WorkbenchStatusBar({ items, label }: { items: WorkbenchStatusItem[]; label?: string }) {
  return (
    <footer aria-label="Research status bar" className="workbench-status-bar">
      <span><WorkbenchIcon name="branch" /> main</span>
      <span><span className="status-dot" /> Local runtime</span>
      <span className="status-spacer" />
      {items.map((item) => (
        <span key={`${item.icon ?? "status"}-${item.label}`}>
          {item.icon && <WorkbenchIcon name={item.icon} />}{item.label}
        </span>
      ))}
      {label && <span>{label}</span>}
    </footer>
  );
}
