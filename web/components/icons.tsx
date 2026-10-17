// Small inline icons (stroke = currentColor), so they follow light and dark themes.

type P = { className?: string };
const base = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
  "aria-hidden": true,
};

export const ChartIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M4 19h16M6 15l4-5 3 3 5-7" />
  </svg>
);
export const CarIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M5 16v2m14-2v2M4 16h16v-4l-2-5H6l-2 5v4Zm3-2h.01M17 14h.01" />
  </svg>
);
export const PlaneIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M10 14 3 11l1.5-1.5 7 1L16 6a2 2 0 0 1 3 3l-4.5 4.5 1 7L14 22l-3-7-3 3v2l-1.5 1.5-1-3.5L2 17l1.5-1.5h2l3-3" />
  </svg>
);
export const FolderIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
  </svg>
);
export const ToolIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-.5-.5-2.5 2.5-2.5Z" />
  </svg>
);
export const CheckIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="m5 12 5 5 9-10" />
  </svg>
);
export const CrossIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);
export const SparkIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="M12 3v4m0 10v4M3 12h4m10 0h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" />
  </svg>
);
export const StackIcon = ({ className }: P) => (
  <svg {...base} className={className}>
    <path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5" />
  </svg>
);

export function DomainIcon({ domain, className }: { domain: string; className?: string }) {
  if (domain === "Vehicle") return <CarIcon className={className} />;
  if (domain === "Travel") return <PlaneIcon className={className} />;
  if (domain === "Trading") return <ChartIcon className={className} />;
  return <FolderIcon className={className} />;
}
