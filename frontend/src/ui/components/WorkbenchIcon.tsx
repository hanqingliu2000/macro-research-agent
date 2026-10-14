import type { ReactNode, SVGProps } from "react";

export type WorkbenchIconName =
  | "agent"
  | "alert"
  | "branch"
  | "check"
  | "chevron-down"
  | "chevron-left"
  | "chevron-right"
  | "chevron-up"
  | "database"
  | "file"
  | "export"
  | "import"
  | "info"
  | "lock"
  | "paperclip"
  | "plus"
  | "research"
  | "settings"
  | "trash"
  | "undo";

const paths: Record<WorkbenchIconName, ReactNode> = {
  agent: <><rect height="11" rx="2" width="14" x="5" y="7" /><path d="M9 11h.01M15 11h.01M9 15h6M12 3v4M8 21h8" /></>,
  alert: <><path d="M12 3 2.8 20h18.4L12 3Z" /><path d="M12 9v5M12 17.5v.01" /></>,
  branch: <><circle cx="6" cy="5" r="2" /><circle cx="18" cy="7" r="2" /><circle cx="6" cy="19" r="2" /><path d="M6 7v10M8 8c4 0 4-1 8-1" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  "chevron-left": <path d="m15 18-6-6 6-6" />,
  "chevron-right": <path d="m9 18 6-6-6-6" />,
  "chevron-up": <path d="m6 15 6-6 6 6" />,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" /></>,
  file: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v5h5M10 12h5M10 16h5" /></>,
  export: <><path d="M12 3v12M7 8l5-5 5 5" /><path d="M5 13v8h14v-8" /></>,
  import: <><path d="M12 3v12M7 10l5 5 5-5" /><path d="M5 17v4h14v-4" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7v.01" /></>,
  lock: <><rect height="10" rx="2" width="14" x="5" y="11" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  paperclip: <path d="m9 12 5.6-5.6a3 3 0 0 1 4.2 4.2l-7.4 7.4a5 5 0 0 1-7.1-7.1l7-7" />,
  plus: <path d="M12 5v14M5 12h14" />,
  research: <><circle cx="10" cy="10" r="6" /><path d="m14.5 14.5 5 5M8 10h4M10 8v4" /></>,
  settings: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 5v4M8 15v4" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>,
  trash: <><path d="M5 7h14M9 7V4h6v3M8 10v8M12 10v8M16 10v8M7 7l1 14h8l1-14" /></>,
  undo: <><path d="m9 8-4 4 4 4" /><path d="M5 12h8a6 6 0 0 1 6 6" /></>,
};

export function WorkbenchIcon({
  name,
  ...props
}: { name: WorkbenchIconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="18"
      viewBox="0 0 24 24"
      width="18"
      {...props}
    >
      <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">
        {paths[name]}
      </g>
    </svg>
  );
}
