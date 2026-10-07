import { useEffect, useMemo, useState } from 'react'
import { awdax } from '../../api/awdax.ts'
import { groupByTag, operationsOf } from './snippets.ts'
import type { Operation } from './snippets.ts'

/** Every call the API has, straight from its OpenAPI document, so this list can't drift from the server. */
export function EndpointList() {
  const [ops, setOps] = useState<Operation[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    awdax.openApi().then((spec) => alive && setOps(operationsOf(spec))).catch(() => alive && setFailed(true))
    return () => {
      alive = false
    }
  }, [])
  const groups = useMemo(() => (ops ? groupByTag(ops) : []), [ops])

  return (
    <section aria-labelledby="endpoints-h" className="mt-10">
      <h2 id="endpoints-h" className="font-display text-h3 font-extrabold">Endpoints</h2>
      <p className="mt-1 max-w-prose text-small text-ink-2">
        Send <code className="font-mono">Authorization: Bearer awx_…</code>. The full description is at{' '}
        <a href="/api/openapi.json" className="underline underline-offset-2">/api/openapi.json</a> (OpenAPI 3.1).
      </p>
      {failed && <p role="alert" className="mt-4 text-small text-ink-2">Couldn’t load the endpoint list.</p>}
      {!ops && !failed && <p className="mt-4 text-small text-ink-3">Loading…</p>}
      {groups.map(([tag, list]) => (
        <div key={tag} className="mt-5">
          <h3 className="font-mono text-micro text-ink-3">{tag}</h3>
          <ul className="mt-1 divide-y-2 divide-line border-y-2 border-line">
            {list.map((op) => (
              <li key={`${op.method} ${op.path}`} className="flex flex-wrap items-baseline gap-x-3 py-2">
                <span className="inline-block w-14 shrink-0 font-mono text-micro font-bold">{op.method}</span>
                <code className="font-mono text-small">{op.path}</code>
                <span className="text-small text-ink-2">{op.summary}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}
