import type { ReactNode } from "react";

export type WorkbenchMode = "agent" | "workflow";

export interface WorkbenchRecentItem {
  id: string;
  title: string;
  status: string;
  to: string;
}

export interface WorkbenchStatusItem {
  icon?: "database" | "file" | "paperclip";
  label: string;
}

export interface WorkbenchShellProps {
  brandMark: string;
  children: ReactNode;
  explorerLabel: string;
  footerDetail?: string;
  footerTitle?: string;
  homePath: string;
  mode: WorkbenchMode;
  newLabel: string;
  recent: WorkbenchRecentItem[];
  recentLabel: string;
  settingsPath?: string;
  showExplorerHeader?: boolean;
  showRailFooter?: boolean;
  showStatusBar?: boolean;
  statusItems?: WorkbenchStatusItem[];
  statusLabel?: string;
}
