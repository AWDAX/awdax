import { useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { awdax } from '../../api/awdax.ts'
import { ApiError } from '../../api/client.ts'
import { useInstances } from '../../api/instancesContext.ts'
import { notifyInstancesChanged } from '../../api/instancesSync.ts'
import { ChartIcon, ChevronIcon, FileIcon, SearchIcon, SparkleIcon } from '../../ui/appIcons.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { PromptBox } from '../prompt/PromptBox.tsx'
import { startFromFile } from './startFromFile.ts'

const FILE_INPUT = 'new-chat-files'

// A web card plays a recorded real run of its prompt (public/demo/<demo>.json), so it is quick on stage; the
// replay's "Run it live" brings the prompt back here for a genuine run.
const CARDS: { icon: ReactNode; title: string; body: string; demo?: { slug: string; prompt: string } }[] = [
  {
    icon: <ChartIcon />,
    title: 'Track a number over time',
    body: 'Every RBI repo rate change since 2019, with its date, kept up to date in the background.',
    demo: { slug: 'repo-rate', prompt: 'RBI repo rate changes since 2019 with date and rate' },
  },
  {
    icon: <SearchIcon />,
    title: 'Compare products across sites',
    body: 'Electric cars under ₹20 lakh with price and range, from several Indian sites.',
    demo: { slug: 'ev-under-20-lakh', prompt: 'Electric cars under ₹20 lakh in India with price and range' },
  },
  {
    icon: <FileIcon />,
    title: 'Dashboard from your own file',
    body: 'Drop in a CSV or Excel file and ask about it. It stays on this device.',
  },
]

/**
 * A new chat, laid out like ChatGPT's start screen: one prompt box (text, voice, or a data file with the +) and
 * cards to try. A sentence starts a web scrape on the backend; a file becomes a dashboard straight away, in the
 * browser.
 */
export default function NewChat() {
  // "Run it live" on a recorded run arrives with its prompt, ready to send.
  const handed = (useLocation().state as { prompt?: string } | null)?.prompt
  const [text, setText] = useState(handed ?? '')
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
      const created = await awdax.createInstance(goal.trim().slice(0, 80))
      try {
        const started = await awdax.startTracking(created.id, goal)
        upsert(started)
        notifyInstancesChanged('create')
        navigate(`/app/c/${started.id}`)
      } catch (err) {
        const status = err instanceof ApiError ? err.status : 0
        // Only a clear refusal deletes the new chat. A 500 can come after the run already started, so it counts as unknown.
        if (status === 409 || ![400, 401, 403, 404, 422].includes(status)) {
          // The run exists, or the outcome is unknown: keep the chat, never delete or retry.
          upsert(created)
          notifyInstancesChanged('create')
          navigate(`/app/c/${created.id}`)
          if (status !== 409) {
            toast({ title: 'The server didn’t confirm the start', description: 'This chat will update when the server answers.', tone: 'error' })
          }
          return
        }
        await awdax.deleteInstance(created.id).catch(() => {})
        throw err
      }
    } catch (err) {
      setBusy(false)
      toast({ title: 'Couldn’t start that request', description: err instanceof Error ? err.message : String(err), tone: 'error' })
    }
  }

  // The file card opens the prompt box's file picker, like the + inside the box.
  const pickFile = () => (document.getElementById(FILE_INPUT) as HTMLInputElement | null)?.click()

  // The prompt rides along, so a replay that can't load still offers the live run.
  const tryCard = (demo?: { slug: string; prompt: string }) =>
    demo ? navigate(`/app/demo/${demo.slug}`, { state: { prompt: demo.prompt } }) : pickFile()

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-5 py-8">
      {/* Normal width, not the landing's 125% display width: at app sizes the wide cut read as stretched. */}
      <h1 className="text-center font-display text-h2 font-extrabold text-balance">What data do you need?</h1>
      <p className="mx-auto mt-2 mb-7 max-w-[60ch] text-center text-body text-pretty text-ink-2">
        Describe it and AWDAX finds it on the web, or drop in a file you already have. Either way you get a dashboard you can shape and question.
      </p>

      <div>
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
        />
      </div>

      {/* Whole-card buttons: icon and title on one line, the example under it (hidden on phones, where the
          three cards stack and would otherwise push the page into a scroll). */}
      <section className="mt-8" aria-labelledby="try-heading">
        <h2 id="try-heading" className="flex items-center gap-2 text-small font-semibold text-ink-2">
          <SparkleIcon /> See what AWDAX can do
        </h2>
        <ul className="mt-2.5 grid gap-2.5 sm:grid-cols-3">
          {CARDS.map((c) => (
            <li key={c.title}>
              <button
                type="button"
                onClick={() => tryCard(c.demo)}
                disabled={busy}
                className="group flex h-full w-full flex-col gap-1.5 rounded-panel border-2 border-line bg-surface p-3 text-left transition-[border-color,opacity] duration-300 ease-soft hover:border-ink disabled:pointer-events-none disabled:opacity-50 focus-visible:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                <span className="flex w-full items-center gap-2.5">
                  <span className="grid size-7 shrink-0 place-items-center rounded-control bg-signal">{c.icon}</span>
                  <span className="min-w-0 flex-1 text-small leading-snug font-semibold">{c.title}</span>
                  <ChevronIcon className="shrink-0 text-ink-3 transition-[translate,color] duration-300 ease-soft group-hover:translate-x-0.5 group-hover:text-ink" />
                </span>
                <span className="hidden text-small text-ink-2 sm:block">{c.body}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

