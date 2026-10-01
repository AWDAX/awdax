import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import { awdax } from '../../api/awdax.ts'
import { useInstances } from '../../api/instancesContext.ts'
import { notifyInstancesChanged } from '../../api/instancesSync.ts'
import { ChartIcon, DatabaseIcon, FileIcon, ReportIcon, SearchIcon, SparkleIcon } from '../../ui/appIcons.tsx'
import { PlayIcon } from '../../ui/icons.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { FEATURES } from '../features.ts'
import { PromptBox } from '../prompt/PromptBox.tsx'
import { startFromFile } from './startFromFile.ts'

const FILE_INPUT = 'new-chat-files'

const CARDS: { icon: ReactNode; title: string; body: string; prompt?: string }[] = [
  {
    icon: <ChartIcon />,
    title: 'Track a number over time',
    body: 'Indian EV sales every month from 2024 to 2026, kept up to date in the background.',
    prompt: 'Track Indian EV sales every month from 2024 to 2026',
  },
  {
    icon: <SearchIcon />,
    title: 'Compare products across sites',
    body: 'Electric cars under ₹20 lakh with price and range, from several Indian sites.',
    prompt: 'Electric cars under ₹20 lakh in India with price and range',
  },
  {
    icon: <FileIcon />,
    title: 'Dashboard from your own file',
    body: 'Drop in a CSV or Excel file and ask about it. It stays on this device.',
  },
]

/**
 * A new chat, laid out like ChatGPT's start screen: one big prompt box (text, voice, or a data file), a strip
 * of shortcuts under it, and cards to try. A sentence starts a web scrape on the backend; a file becomes a
 * dashboard straight away, in the browser.
 */
export default function NewChat() {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const { upsert } = useInstances()
  const { toast } = useToast()

  const submit = async (goal: string, attached: File[]) => {
    setBusy(true)
    try {
      if (attached.length > 0) {
        const res = await startFromFile(attached[0], goal)
        if ('error' in res) {
          toast({ title: 'Couldn’t read that file', description: res.error, tone: 'error' })
          setBusy(false)
          return
        }
        navigate(`/app/f/${res.id}`)
        return
      }
      const created = await awdax.createInstance(goal.trim())
      const started = await awdax.startTracking(created.id, goal)
      upsert(started)
      notifyInstancesChanged('create')
      navigate(`/app/c/${started.id}`)
    } catch (err) {
      setBusy(false)
      toast({ title: 'Couldn’t start that request', description: err instanceof Error ? err.message : String(err), tone: 'error' })
    }
  }

  // Real buttons (keyboard-reachable) that open the prompt box's file picker.
  const pickFile = () => (document.getElementById(FILE_INPUT) as HTMLInputElement | null)?.click()

  const stripItem = 'flex items-center gap-1.5 rounded-sm transition-colors duration-300 ease-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink'
  // Shortcuts on the left, the refresh note on the right, one centred line; on a narrow box the note wraps
  // under the shortcuts, left-aligned, instead of hanging off to the right on its own.
  const strip = (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-ink-2">
        <button type="button" onClick={pickFile} className={stripItem}>
          <FileIcon /> Upload a file
        </button>
        <Link to="/app/projects" className={stripItem}>
          <ReportIcon /> Projects report
        </Link>
        {FEATURES.askDatabase && (
          <Link to="/app/ask" className={stripItem}>
            <DatabaseIcon /> Ask database
          </Link>
        )}
        <Link to="/app/sample" className={stripItem}>
          <PlayIcon /> Watch a sample run
        </Link>
      </div>
      <span className="hidden font-mono text-micro leading-none tracking-normal text-ink-3 sm:inline">Web requests refresh every 5 min</span>
    </div>
  )

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-5 py-10">
      <h1 className="text-center font-display font-wide text-h1 font-extrabold">What data do you need?</h1>
      <p className="mx-auto mt-3 mb-8 max-w-[54ch] text-center text-lead text-ink-2">
        Describe it and AWDAX finds it on the web, or drop in a file you already have. Either way you get a dashboard you can shape and question.
      </p>

      <PromptBox
        label="Your data request"
        value={text}
        onChange={setText}
        onSubmit={(t, f) => void submit(t, f)}
        busy={busy}
        size="lg"
        autoFocus
        allowFiles
        files={files}
        onFilesChange={(f) => setFiles(f.slice(-1))}
        fileInputId={FILE_INPUT}
        placeholder={files.length ? 'Ask something about this file (optional), then send' : 'e.g. Track Indian EV sales every month from 2024 to 2026'}
        footer={strip}
      />

      <section className="mt-10" aria-labelledby="try-heading">
        <h2 id="try-heading" className="flex items-center gap-2 text-body font-semibold">
          <SparkleIcon /> See what AWDAX can do
        </h2>
        <ul className="mt-3 grid gap-3 sm:grid-cols-3">
          {CARDS.map((c) => (
            <li key={c.title} className="flex flex-col rounded-panel border-2 border-line p-4 transition-colors duration-300 ease-soft hover:border-ink">
              <div className="flex items-start justify-between">
                <span className="grid size-8 place-items-center rounded-control bg-signal">{c.icon}</span>
                {c.prompt ? (
                  <button type="button" onClick={() => setText(c.prompt!)} aria-label={`Try: ${c.title}`} className="rounded-control border-2 border-ink px-2.5 py-0.5 text-small font-semibold hover:bg-ink hover:text-on-ink">
                    Try
                  </button>
                ) : (
                  <button type="button" onClick={pickFile} aria-label={`Try: ${c.title}`} className="rounded-control border-2 border-ink px-2.5 py-0.5 text-small font-semibold hover:bg-ink hover:text-on-ink">
                    Try
                  </button>
                )}
              </div>
              <p className="mt-3 font-semibold">{c.title}</p>
              <p className="mt-1 text-small text-ink-2">{c.body}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
