import type { ReactNode } from 'react'
import type { ChartSpec } from '../../domain/charts.ts'
import { sampleByKey } from '../../domain/fixtures/index.ts'
import { AutoChart } from '../../product/AutoChart.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { Strike } from '../../ui/Strike.tsx'

type TileProps = { title: string; note?: string; className?: string; children: ReactNode }

/** A bento tile: 2px ink frame, a small header, content that fills the rest of the cell. */
export function Tile({ title, note, className = '', children }: TileProps) {
  return (
    <article className={`flex min-w-0 flex-col gap-3 rounded-panel border-2 border-ink bg-surface p-4 ${className}`}>
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-small font-semibold text-ink">{title}</h3>
        {note && <p className="font-mono text-micro text-ink-3">{note}</p>}
      </header>
      {children}
    </article>
  )
}

export function ChartTile({ spec, sample, className = '' }: { spec: ChartSpec; sample: string; className?: string }) {
  return (
    <Tile title={spec.title} note={`Sample run: ${sample}`} className={className}>
      <div className="flex flex-1 flex-col justify-center">
        <AutoChart spec={spec} compact />
      </div>
    </Tile>
  )
}

const jobs = sampleByKey.jobs
const byCompany = (name: string) => jobs.dataset.rows.find((r) => r.cells.company.value === name)!
const inr = (n: unknown) => `₹${Number(n).toLocaleString('en-IN')}`

/** A sample monitor: the big number, then the change list. Labeled as a sample, not a live count. */
export function MonitorTile({ seen, className = '' }: { seen: boolean; className?: string }) {
  const orbitly = byCompany('Orbitly').cells.stipend
  const added = [byCompany('Quillbyte'), byCompany('Ledgerly')]
  return (
    <Tile title="Monitor" note="Sample, not a live count" className={className}>
      <div className="flex flex-col gap-1">
        <p className="text-h3 font-bold text-ink">Frontend internships in Bengaluru</p>
        <p className="font-mono text-micro text-ink-2">Every Monday, 09:00 IST · a new version each run</p>
      </div>

      <div className="flex flex-1 flex-col justify-center py-2">
        <p className="font-display font-wide text-display font-extrabold text-ink">
          <Mark on={seen} delay={400}>
            37
          </Mark>
        </p>
        <p className="text-h3 font-bold text-ink">new rows since Monday</p>
      </div>

      <div className="flex flex-col border-t-2 border-ink">
        <h4 className="py-2.5 text-small font-semibold text-ink">What changed</h4>
        <ul className="flex flex-col text-small">
          {added.map((r, i) => (
            <Change key={r.id} sign="+" label="Added">
              <Mark on={seen} delay={700 + i * 180}>
                {String(r.cells.title.value)} · {String(r.cells.company.value)}
              </Mark>
            </Change>
          ))}
          <Change sign="~" label="Changed">
            Orbitly: stipend {inr(orbitly.alternatives?.[0].value)} → {inr(orbitly.value)}
          </Change>
          <Change sign="−" label="Removed">
            <Strike on={seen} delay={1100}>
              Frontend Intern · Arclight
            </Strike>{' '}
            <span className="text-ink-3">outside the 14 days</span>
          </Change>
          <li className="pt-2 pl-8 text-ink-3">and 35 more new rows</li>
        </ul>
      </div>
    </Tile>
  )
}

function Change({ sign, label, children }: { sign: string; label: string; children: ReactNode }) {
  return (
    <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 border-b border-line py-2">
      <span className="font-mono text-ink" aria-label={label}>
        {sign}
      </span>
      <span className="min-w-0 text-ink lg:truncate">{children}</span>
    </li>
  )
}

/** One real value of the Internships sample as it exports: the value travels with its receipt. */
export function ExportTile({ className = '' }: { className?: string }) {
  const c = jobs.dataset.rows[0].cells.stipend
  const excerpt = { stipend: { value: c.value, source_url: c.sourceUrl, captured_at: c.capturedAt, quote: c.quote } }
  return (
    <Tile title="Export, CSV or JSON" note="Receipts included" className={className}>
      <pre className="flex-1 overflow-x-auto rounded-control bg-sunken p-3 font-mono text-micro whitespace-pre-wrap break-all text-ink">
        {JSON.stringify(excerpt, null, 2)}
      </pre>
    </Tile>
  )
}
