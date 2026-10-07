import { useEffect, useState } from 'react'
import { awdax } from '../../api/awdax.ts'
import { download } from '../export/download.ts'
import { failedLinksCsv } from './failedLinks.ts'
import type { FailedLinksResponse } from './failedLinks.ts'

type Props = {
  instanceId: string
  /** Changes when the run starts or finishes, so the lists are read again. */
  refreshKey: unknown
}

/**
 * The web-research step's ranking (the order the websites were tried in) and the links that failed their plain
 * web request (blocked, not found, unreachable, CAPTCHA), downloadable as CSV.
 */
export function FailedLinks({ instanceId, refreshKey }: Props) {
  const [data, setData] = useState<FailedLinksResponse | null>(null)

  useEffect(() => {
    let alive = true
    awdax
      .getFailedLinks(instanceId)
      .then((res) => alive && setData(res))
      .catch(() => alive && setData(null))
    return () => {
      alive = false
    }
  }, [instanceId, refreshKey])

  if (!data || (data.research.length === 0 && data.rows.length === 0)) return null
  const save = () => download(new Blob([failedLinksCsv(data)], { type: 'text/csv;charset=utf-8' }), `failed-links-${instanceId}.csv`)

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {data.research.length > 0 && (
        <details className="rounded-panel border-2 border-line p-3" open>
          <summary className="cursor-pointer text-small font-semibold">Web research: top {data.research.length} websites, tried in this order</summary>
          <ol className="mt-2 flex flex-col gap-1.5 text-small">
            {data.research.map((s) => (
              <li key={s.url} className="flex flex-col">
                <span>
                  <span className="font-mono text-micro text-ink-3">{s.rank}.</span>{' '}
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
                    {s.site_name || s.domain || s.url}
                  </a>
                </span>
                {s.what_it_has && <span className="text-micro text-ink-2">{s.what_it_has}</span>}
              </li>
            ))}
          </ol>
        </details>
      )}
      {data.rows.length > 0 && (
        <details className="rounded-panel border-2 border-line p-3">
          <summary className="cursor-pointer text-small font-semibold">Failed links ({data.rows.length})</summary>
          <p className="mt-1 text-micro text-ink-2">Links that failed a plain web request: refused, missing, unreachable or behind a CAPTCHA.</p>
          <ul className="mt-2 flex max-h-56 flex-col gap-1.5 overflow-y-auto text-micro" data-lenis-prevent>
            {data.rows.map((r) => (
              <li key={r.url} className="flex flex-col">
                <a href={r.url} target="_blank" rel="noopener noreferrer" className="truncate font-mono underline underline-offset-2" title={r.url}>
                  {r.url}
                </a>
                <span className="text-ink-2">
                  {r.outcome}
                  {r.http_status ? ` (HTTP ${r.http_status})` : ''} · {r.stage} · {r.reason}
                </span>
              </li>
            ))}
          </ul>
          <button type="button" onClick={save} className="mt-2 rounded-control border-2 border-line px-3 py-1 text-micro font-semibold hover:border-line-strong">
            Download CSV
          </button>
        </details>
      )}
    </div>
  )
}
