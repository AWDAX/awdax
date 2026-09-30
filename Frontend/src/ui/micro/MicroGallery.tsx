import { useState } from 'react'
import type { ReactNode } from 'react'
import { VoicePill } from './VoicePill.tsx'
import { ThoughtLine } from './ThoughtLine.tsx'
import { CallChip } from './CallChip.tsx'
import { BellToggle } from './BellToggle.tsx'
import { FuseButton } from './FuseButton.tsx'
import { CopyButton } from './CopyButton.tsx'
import { AssistantOrb } from './AssistantOrb.tsx'
import { ToastProvider } from '../toast/ToastHost.tsx'
import { useToast } from '../toast/toastContext.ts'

function Cell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-panel border-2 border-ink p-4">
      <h3 className="text-small font-semibold text-ink">{title}</h3>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  )
}

function ToastDemo() {
  const { toast } = useToast()
  return (
    <button
      type="button"
      onClick={() =>
        toast({ title: 'Row just found', description: '3 new rows arrived', tone: 'success', actionLabel: 'View', duration: 5000 })
      }
      className="rounded-control border-2 border-ink bg-surface px-3 py-1.5 text-small font-semibold text-ink hover:bg-sunken"
    >
      Fire a toast
    </button>
  )
}

/** Not a route: a temporary visual check grid for all eight ported micro components. */
export function MicroGallery() {
  const [retryCount, setRetryCount] = useState(0)

  return (
    <ToastProvider>
      <div className="grid gap-4 p-6 sm:grid-cols-2">
        <Cell title="VoicePill">
          <VoicePill ariaLabel="Dictate" />
        </Cell>

        <Cell title="ThoughtLine">
          <ThoughtLine label="Searching sources…" steps={['Read plan', 'Fetch page', 'Extract rows']} working />
        </Cell>

        <Cell title="CallChip">
          <CallChip icon="terminal" name="bash" argument="npm test" status="running" />
          <CallChip icon="file" name="read" argument="report.csv" status="done" />
          <CallChip icon="search" name="search" argument="query" status="error" onRetry={() => setRetryCount((c) => c + 1)} />
          <span className="text-micro text-ink-3">retries: {retryCount}</span>
        </Cell>

        <Cell title="SwipeToast / ToastHost">
          <ToastDemo />
        </Cell>

        <Cell title="BellToggle">
          <BellToggle defaultPressed={false} count={3} />
          <BellToggle defaultPressed size="sm" iconOnly />
        </Cell>

        <Cell title="FuseButton">
          <FuseButton label="Delete chat" tone="danger" undoWindow={4000} />
          <FuseButton label="Delete" tone="danger" iconOnly />
        </Cell>

        <Cell title="CopyButton">
          <CopyButton text="https://awdax.example/report/1" />
        </Cell>

        <Cell title="AssistantOrb">
          <AssistantOrb size="sm" />
          <AssistantOrb size="md" working />
          <AssistantOrb size="lg" label="AWDAX assistant" />
        </Cell>
      </div>
    </ToastProvider>
  )
}
