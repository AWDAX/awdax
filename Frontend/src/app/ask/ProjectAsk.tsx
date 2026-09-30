import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { DatasetTable } from '../../api/types.ts'
import { profileTable } from '../../analytics/profile.ts'
import type { ChartSpec } from '../../analytics/spec.ts'
import { suggestFollowUps } from '../../analytics/suggest.ts'
import { ChartIcon } from '../../ui/appIcons.tsx'
import { Button } from '../../ui/Button.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { FollowUps } from '../chat/FollowUps.tsx'
import { useAnswers } from '../chat/useAnswers.ts'
import { ChartBuilder } from '../dashboard/ChartBuilder.tsx'
import { useDashboard } from '../dashboard/useDashboard.ts'
import { AnswerCard } from './AnswerCard.tsx'
import { AskBox } from './AskBox.tsx'

type Props = { table: DatasetTable; title: string; instanceKey: string; path: string }

/** Questions about one project's table. Answers and pinned charts are the same ones its chat shows. */
export function ProjectAsk({ table, title, instanceKey, path }: Props) {
  const profile = useMemo(() => profileTable(table), [table])
  const answers = useAnswers(instanceKey)
  const dash = useDashboard(instanceKey, profile)
  const followUps = useMemo(() => suggestFollowUps(profile), [profile])
  const asked = new Set(answers.items.map((a) => a.question))
  const [building, setBuilding] = useState(false)
  const { toast } = useToast()
  const navigate = useNavigate()

  const pin = (spec: ChartSpec) => {
    dash.add(spec)
    toast({ title: 'Added to the dashboard', description: title, tone: 'success', actionLabel: 'Open', onAction: () => navigate(path) })
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display font-wide text-h3 font-extrabold">{title}</h2>
          <p className="mt-1 text-small text-ink-2">
            {profile.rowCount.toLocaleString('en-IN')} rows · {profile.columns.filter((c) => !c.virtual).map((c) => c.label).join(', ')}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setBuilding((b) => !b)} aria-expanded={building}>
            <ChartIcon /> {building ? 'Close the query builder' : 'Build a query'}
          </Button>
          <Link to={path} className="inline-flex h-10 items-center rounded-control px-3 text-small underline underline-offset-2">
            Open the dashboard
          </Link>
        </div>
      </div>

      {building && (
        <div className="rounded-panel border-2 border-ink p-4">
          <ChartBuilder
            profile={profile}
            onCancel={() => setBuilding(false)}
            onSave={(spec) => {
              pin(spec)
              setBuilding(false)
            }}
          />
        </div>
      )}

      {answers.items.length > 0 && (
        <ol className="flex flex-col gap-6">
          {answers.items.map((a) => (
            <li key={a.id}>
              <AnswerCard profile={profile} saved={a} title={title} onAddToDashboard={pin} onRemove={() => answers.remove(a.id)} />
            </li>
          ))}
        </ol>
      )}
      <FollowUps items={followUps.filter((f) => !asked.has(f.text))} onPick={(f) => answers.add({ question: f.text, intent: f.intent, chart: f.chart, query: f.query })} />
      <AskBox profile={profile} onAnswer={answers.add} suggestions={followUps} />
    </div>
  )
}
