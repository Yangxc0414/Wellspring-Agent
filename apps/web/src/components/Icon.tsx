import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "logo"
  | "plus"
  | "search"
  | "folder"
  | "chevron"
  | "tasks"
  | "panel"
  | "command"
  | "download"
  | "sliders"
  | "globe"
  | "play"
  | "grid"
  | "more"
  | "close"
  | "send"
  | "check"
  | "alert"
  | "lock"
  | "external"
  | "copy"
  | "spark"
  | "cpu"
  | "evidence"
  | "evolution"
  | "pause"
  | "step"
  | "stop"
  | "refresh"
  | "trash"
  | "arrow"
  | "bot"
  | "clock"
  | "branch"
  | "shield"
  | "terminal"
  | "book"
  | "paperclip"
  | "chart"
  | "eye"
  | "database"
  | "compass"
  | "info";

interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  size?: number;
}

const paths: Record<IconName, ReactNode> = {
  logo: (
    <>
      <path d="M4.8 7.3 12 3.8l7.2 3.5v9.4L12 20.2l-7.2-3.5V7.3Z" />
      <path d="M4.8 7.3 12 10.8l7.2-3.5M12 10.8v9.4" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  search: (
    <>
      <circle cx="10.8" cy="10.8" r="5.6" />
      <path d="m15 15 4.2 4.2" />
    </>
  ),
  folder: <path d="M3.8 6.7h6l1.8 2h8.6v9.1a1.7 1.7 0 0 1-1.7 1.7H5.5a1.7 1.7 0 0 1-1.7-1.7V6.7Z" />,
  chevron: <path d="m9.5 6.5 5.5 5.5-5.5 5.5" />,
  tasks: (
    <>
      <path d="M5 6.5h14M5 12h14M5 17.5h9" />
      <path d="M2.8 6.5h.1M2.8 12h.1M2.8 17.5h.1" strokeWidth="2.4" strokeLinecap="round" />
    </>
  ),
  panel: (
    <>
      <rect x="3.4" y="4.4" width="17.2" height="15.2" rx="1.4" />
      <path d="M14.7 4.4v15.2" />
    </>
  ),
  command: (
    <path d="M9 9V6.6a2.6 2.6 0 1 0-2.6 2.6H9Zm0 0h6m-6 0v6m6-6V6.6a2.6 2.6 0 1 1 2.6 2.6H15Zm0 0v6m0 0h2.4a2.6 2.6 0 1 1-2.4 2.6V15Zm-6 0H6.6A2.6 2.6 0 1 0 9 17.6V15Z" />
  ),
  download: <path d="M12 4v10m0 0 3.7-3.7M12 14l-3.7-3.7M4.5 16.5v2.2h15v-2.2" />,
  sliders: (
    <>
      <path d="M4 7h7M15.5 7H20M4 17h3.5M11 17h9" />
      <circle cx="13.2" cy="7" r="2.1" />
      <circle cx="8.8" cy="17" r="2.1" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M3.9 12h16.2M12 3.8c2.1 2.2 3.2 5 3.2 8.2s-1.1 6-3.2 8.2c-2.1-2.2-3.2-5-3.2-8.2S9.9 6 12 3.8Z" />
    </>
  ),
  play: <path d="m8 5.8 9.2 6.2L8 18.2V5.8Z" />,
  grid: (
    <>
      <rect x="3.8" y="3.8" width="6.1" height="6.1" rx=".7" />
      <rect x="14.1" y="3.8" width="6.1" height="6.1" rx=".7" />
      <rect x="3.8" y="14.1" width="6.1" height="6.1" rx=".7" />
      <rect x="14.1" y="14.1" width="6.1" height="6.1" rx=".7" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="12" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="19" cy="12" r="1.1" fill="currentColor" stroke="none" />
    </>
  ),
  close: <path d="m6 6 12 12M18 6 6 18" />,
  send: <path d="M4.2 11.7 20 4.8l-4.4 14.4-3.8-5.8-7.6-1.7Zm7.6 1.7 4.6-5.1" />,
  check: <path d="m5 12.5 4.3 4.3L19 6.8" />,
  alert: (
    <>
      <path d="M12 4.2 21 19.4H3L12 4.2Z" />
      <path d="M12 9.3v4.6M12 16.8h.1" strokeWidth="1.8" strokeLinecap="round" />
    </>
  ),
  lock: (
    <>
      <rect x="5.2" y="10.2" width="13.6" height="9.4" rx="1.4" />
      <path d="M8.3 10.2V7.7a3.7 3.7 0 0 1 7.4 0v2.5M12 13.7v2.5" />
    </>
  ),
  external: <path d="M14 4.8h5.2V10M19 5 10.3 13.7M19.2 13.5v5.3a1.4 1.4 0 0 1-1.4 1.4H5.2a1.4 1.4 0 0 1-1.4-1.4V6.2a1.4 1.4 0 0 1 1.4-1.4h5.3" />,
  copy: (
    <>
      <rect x="8.4" y="8.4" width="11.2" height="11.2" rx="1.4" />
      <path d="M15.6 8.4V6.2a1.4 1.4 0 0 0-1.4-1.4H5.2a1.4 1.4 0 0 0-1.4 1.4v9a1.4 1.4 0 0 0 1.4 1.4h3.2" />
    </>
  ),
  spark: (
    <>
      <path d="M12 3.8 13.6 9l5.2 1.6-5.2 1.6L12 17.4l-1.6-5.2L5.2 10.6 10.4 9 12 3.8Z" />
      <path d="M18.8 3.6v3.2M17.2 5.2H20.4" />
    </>
  ),
  cpu: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="1.4" />
      <rect x="10" y="10" width="4" height="4" rx=".5" />
      <path d="M9 3.8v2.7M15 3.8v2.7M9 17.5v2.7M15 17.5v2.7M3.8 9h2.7M3.8 15h2.7M17.5 9h2.7M17.5 15h2.7" />
    </>
  ),
  evidence: (
    <>
      <path d="M9.2 14.8 14.8 9.2" />
      <path d="M8.2 10.8 6.5 12.5a3.5 3.5 0 1 0 5 5l1.7-1.7M15.8 13.2l1.7-1.7a3.5 3.5 0 1 0-5-5l-1.7 1.7" />
    </>
  ),
  evolution: (
    <>
      <circle cx="12" cy="12" r="2.5" />
      <path d="M12 3.8c4.5 0 8.2 3.7 8.2 8.2M12 20.2c-4.5 0-8.2-3.7-8.2-8.2" />
      <path d="m17.3 4.8 2.9.8-.8 2.9M6.7 19.2l-2.9-.8.8-2.9" />
    </>
  ),
  pause: <path d="M8.5 5.5v13M15.5 5.5v13" strokeWidth="2.6" strokeLinecap="round" />,
  step: (
    <>
      <path d="m6 5.8 8.4 6.2L6 18.2V5.8Z" />
      <path d="M18 5.8v12.4" strokeWidth="2" strokeLinecap="round" />
    </>
  ),
  stop: <rect x="5.8" y="5.8" width="12.4" height="12.4" rx="1.2" />,
  refresh: <path d="M4.6 9.2A8 8 0 0 1 19.4 11M19.4 5.2v5.8h-5.8M19.4 14.8A8 8 0 0 1 4.6 13M4.6 18.8V13h5.8" />,
  trash: (
    <>
      <path d="M4.8 6.8h14.4M9.3 4.4h5.4v2.4H9.3V4.4ZM6.5 6.8l.8 13h9.4l.8-13" />
      <path d="M10 10.3v6M14 10.3v6" />
    </>
  ),
  arrow: <path d="M4.8 12h13.4m0 0-4.6-4.6M18.2 12l-4.6 4.6" />,
  bot: (
    <>
      <rect x="4.4" y="7.4" width="15.2" height="11.2" rx="2.2" />
      <path d="M12 4v3.4M8.3 12h.1M15.6 12h.1M8.8 15.2h6.4" strokeLinecap="round" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7.6v4.8l3.2 1.8" />
    </>
  ),
  branch: (
    <>
      <circle cx="6.5" cy="6" r="2" />
      <circle cx="6.5" cy="18" r="2" />
      <circle cx="17.5" cy="8" r="2" />
      <path d="M6.5 8v8M8.5 15.2c5.4 0 7-2.1 7-5.2" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.8 19 6v5.5c0 4.2-2.8 6.9-7 8.7-4.2-1.8-7-4.5-7-8.7V6l7-2.2Z" />
      <path d="m9 11.8 2.1 2.1 4-4.2" />
    </>
  ),
  terminal: (
    <>
      <rect x="3.4" y="4.6" width="17.2" height="14.8" rx="1.6" />
      <path d="m7 9 3 3-3 3M13 15h4" />
    </>
  ),
  book: (
    <>
      <path d="M4.2 5.2h6.2A2.6 2.6 0 0 1 13 7.8v11.4a2.6 2.6 0 0 0-2.6-2.6H4.2V5.2ZM19.8 5.2h-6.2A2.6 2.6 0 0 0 11 7.8v11.4a2.6 2.6 0 0 1 2.6-2.6h6.2V5.2Z" />
    </>
  ),
  paperclip: <path d="M9.2 12.8 15 7a3.1 3.1 0 0 1 4.4 4.4l-7.8 7.8a5 5 0 0 1-7.1-7.1l7.2-7.2" />,
  chart: (
    <>
      <path d="M4 4.5V20h16" />
      <path d="M8 16.5v-4M12 16.5V8M16 16.5v-6" />
    </>
  ),
  eye: (
    <>
      <path d="M2.8 12s3.4-6 9.2-6 9.2 6 9.2 6-3.4 6-9.2 6-9.2-6-9.2-6Z" />
      <circle cx="12" cy="12" r="2.6" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="6" rx="7.2" ry="2.7" />
      <path d="M4.8 6v6c0 1.5 3.2 2.7 7.2 2.7s7.2-1.2 7.2-2.7V6M4.8 12v6c0 1.5 3.2 2.7 7.2 2.7s7.2-1.2 7.2-2.7v-6" />
    </>
  ),
  compass: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="m15.5 8.5-2.1 4.9-4.9 2.1 2.1-4.9 4.9-2.1Z" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 10.5v5M12 7.6h.1" strokeWidth="2" strokeLinecap="round" />
    </>
  )
};

export function Icon({ name, size = 14, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {paths[name]}
    </svg>
  );
}
