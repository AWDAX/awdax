import type { SVGProps } from 'react'
import { Icon } from './icons.tsx'

// App icons in the same 16px, 1.5-stroke line style as icons.tsx. Decorative by default: pair with text
// or give the button an aria-label.
type P = SVGProps<SVGSVGElement>

export const PlusIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 3v10M3 8h10" />
  </Icon>
)
export const SearchIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="7" cy="7" r="4.25" />
    <path d="M10.2 10.2L13.5 13.5" />
  </Icon>
)
export const SidebarIcon = (p: P) => (
  <Icon {...p}>
    <rect x="2" y="2.75" width="12" height="10.5" rx="1.5" />
    <path d="M6 2.75v10.5" />
  </Icon>
)
export const MenuIcon = (p: P) => (
  <Icon {...p}>
    <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" />
  </Icon>
)
export const CloseIcon = (p: P) => (
  <Icon {...p}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Icon>
)
export const ReportIcon = (p: P) => (
  <Icon {...p}>
    <rect x="2.5" y="2.5" width="11" height="11" rx="1" />
    <path d="M5.5 10.5V8M8 10.5V5.5M10.5 10.5V7" />
  </Icon>
)
export const DatabaseIcon = (p: P) => (
  <Icon {...p}>
    <ellipse cx="8" cy="4" rx="5" ry="1.75" />
    <path d="M3 4v8c0 1 2.2 1.75 5 1.75S13 13 13 12V4M3 8c0 1 2.2 1.75 5 1.75S13 9 13 8" />
  </Icon>
)
export const TrashIcon = (p: P) => (
  <Icon {...p}>
    <path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5" />
  </Icon>
)
export const LogoutIcon = (p: P) => (
  <Icon {...p}>
    <path d="M6.5 13.5H3.5v-11h3M10 5l3 3-3 3M13 8H6.5" />
  </Icon>
)
export const ChevronIcon = (p: P) => (
  <Icon {...p}>
    <path d="M6 4l4 4-4 4" />
  </Icon>
)
export const MicIcon = (p: P) => (
  <Icon {...p}>
    <rect x="6" y="2" width="4" height="7.5" rx="2" />
    <path d="M3.75 7.5a4.25 4.25 0 0 0 8.5 0M8 11.75V14" />
  </Icon>
)
export const StopIcon = (p: P) => (
  <Icon {...p}>
    <rect x="4.5" y="4.5" width="7" height="7" rx="1" fill="currentColor" />
  </Icon>
)
export const SendIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 13V3M4 7l4-4 4 4" />
  </Icon>
)
export const CopyIcon = (p: P) => (
  <Icon {...p}>
    <rect x="5.5" y="5.5" width="8" height="8" rx="1" />
    <path d="M10.5 5.5V3.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2" />
  </Icon>
)
export const ErrorIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="5.5" />
    <path d="M6 6l4 4M10 6l-4 4" />
  </Icon>
)
export const BellIcon = (p: P) => (
  <Icon {...p}>
    <path d="M4 11.5V7.5a4 4 0 0 1 8 0v4l1 1H3z" />
    <path d="M6.75 14h2.5" />
  </Icon>
)
export const BellOffIcon = (p: P) => (
  <Icon {...p}>
    <path d="M5.2 4.2A4 4 0 0 1 12 7.5v3M4 7.5v4l-1 1h8.5M6.75 14h2.5M2.5 2.5l11 11" />
  </Icon>
)
export const SparkleIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 2.5l1.3 3.2 3.2 1.3-3.2 1.3L8 11.5 6.7 8.3 3.5 7l3.2-1.3z" fill="currentColor" stroke="none" />
    <path d="M12.5 11l.5 1.3 1.3.5-1.3.5-.5 1.2-.5-1.2-1.2-.5 1.2-.5z" fill="currentColor" stroke="none" />
  </Icon>
)
export const TerminalIcon = (p: P) => (
  <Icon {...p}>
    <rect x="2" y="3" width="12" height="10" rx="1.5" />
    <path d="M4.75 6.25L6.75 8l-2 1.75M8.5 10h2.75" />
  </Icon>
)
export const FileIcon = (p: P) => (
  <Icon {...p}>
    <path d="M9.5 2H4.5v12h7V4z" />
    <path d="M9.5 2v2h2M6.25 7.5h3.5M6.25 10h3.5" />
  </Icon>
)
export const EditIcon = (p: P) => (
  <Icon {...p}>
    <path d="M10.5 3l2.5 2.5-7 7H3.5V10z" />
  </Icon>
)
export const GripIcon = (p: P) => (
  <Icon {...p}>
    <path d="M6 4h.01M10 4h.01M6 8h.01M10 8h.01M6 12h.01M10 12h.01" strokeWidth={2.2} />
  </Icon>
)
export const DownloadIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 2.5v8M4.5 7.5L8 11l3.5-3.5M3 13.5h10" />
  </Icon>
)
export const FilterIcon = (p: P) => (
  <Icon {...p}>
    <path d="M2.5 3.5h11L9.25 8.5v4l-2.5 1v-5z" />
  </Icon>
)
export const TableIcon = (p: P) => (
  <Icon {...p}>
    <rect x="2.5" y="3" width="11" height="10" rx="1" />
    <path d="M2.5 6.5h11M2.5 9.75h11M6.5 6.5V13" />
  </Icon>
)
export const MoreIcon = (p: P) => (
  <Icon {...p}>
    <path d="M3.5 8h.01M8 8h.01M12.5 8h.01" strokeWidth={2.4} />
  </Icon>
)
export const ChartIcon = (p: P) => (
  <Icon {...p}>
    <path d="M2.5 13.5h11M4.5 11V8M8 11V4.5M11.5 11V6.5" />
  </Icon>
)
export const ResizeIcon = (p: P) => (
  <Icon {...p}>
    <path d="M13 7.5L7.5 13M13 11l-2 2" />
  </Icon>
)
export const LinkIcon = (p: P) => (
  <Icon {...p}>
    <path d="M7 9a2.5 2.5 0 0 0 3.5 0l2-2A2.5 2.5 0 0 0 9 3.5l-.75.75M9 7a2.5 2.5 0 0 0-3.5 0l-2 2A2.5 2.5 0 0 0 7 12.5l.75-.75" />
  </Icon>
)

export const BracesIcon = (p: P) => (
  <Icon {...p}>
    <path d="M6.5 3.5c-1 0-1.5.5-1.5 1.5v2c0 1-.5 1-1.5 1 1 0 1.5 0 1.5 1v2c0 1 .5 1.5 1.5 1.5M9.5 3.5c1 0 1.5.5 1.5 1.5v2c0 1 .5 1 1.5 1-1 0-1.5 0-1.5 1v2c0 1-.5 1.5-1.5 1.5" />
  </Icon>
)

export const CodeIcon = (p: P) => (
  <Icon {...p}>
    <path d="M5.5 5L2 8l3.5 3M10.5 5L14 8l-3.5 3M9.5 3l-3 10" />
  </Icon>
)

export const ExcelIcon = (p: P) => (
  <Icon {...p}>
    <rect x="2.5" y="2.5" width="11" height="11" rx="1" />
    <path d="M6 6l4 4M10 6l-4 4" />
  </Icon>
)

export const ListLinesIcon = (p: P) => (
  <Icon {...p}>
    <path d="M5 4.5h8M5 8h8M5 11.5h8M2.5 4.5h.01M2.5 8h.01M2.5 11.5h.01" strokeWidth={2.4} />
  </Icon>
)

export const MarkdownIcon = (p: P) => (
  <Icon {...p}>
    <rect x="2.5" y="3.5" width="11" height="9" rx="1.5" />
    <path d="M4.5 10.5V6l1.5 2 1.5-2v4.5M11.5 6v4.5M9.5 8.5l2 2 2-2" />
  </Icon>
)
