import { useEffect, useMemo, useState } from 'react'
import { ReplayIcon } from '../../ui/icons.tsx'
import { Button } from '../../ui/Button.tsx'
import { ChatView } from '../chat/ChatView.tsx'
import type { Visit } from '../sources/buildSources.ts'
import { BEATS, stateAt } from './sampleScript.ts'

/**
 * A sample run, for seeing the whole chat work before the backend has a Gemini key: the same ChatView the
 * real page uses, fed a script in the backend's exact shapes (phases, report text, master table). Fictional
 * data on .example sites, labelled as such. Nothing is sent to the backend.
 */
export default function SampleRun() {
  const [step, setStep] = useState(0)
  const [run, setRun] = useState(0)

  useEffect(() => {
    if (step >= BEATS.length - 1) return
    const t = window.setTimeout(() => setStep((s) => s + 1), BEATS[step + 1].at - BEATS[step].at)
    return () => window.clearTimeout(t)
  }, [step, run])

  const { messages, live } = useMemo(() => stateAt(step), [step])
  const visits = useMemo<Visit[]>(() => {
    const out: Visit[] = []
    for (const b of BEATS.slice(0, step + 1)) if (b.source && out[out.length - 1]?.source !== b.source) out.push({ source: b.source, phase: b.phase, at: new Date().toISOString() })
    return out
  }, [step])
  const finished = step >= BEATS.length - 1

  return (
    <ChatView
      instanceKey="sample-run"
      title="EV sales in India, by month and segment"
      meta={finished ? 'Sample run · finished · refreshes are simulated' : 'Sample run · running now'}
      badge={<p className="mb-1 inline-block rounded-control bg-signal px-2 py-0.5 font-mono text-micro">Sample run · fictional data on .example sites</p>}
      messages={messages}
      live={live}
      visits={visits}
      onRetry={() => undefined}
      actions={
        <>
          {!finished && (
            <Button variant="secondary" onClick={() => setStep(BEATS.length - 1)}>
              Skip to the result
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => {
              setStep(0)
              setRun((r) => r + 1)
            }}
          >
            <ReplayIcon /> Replay
          </Button>
        </>
      }
    />
  )
}
