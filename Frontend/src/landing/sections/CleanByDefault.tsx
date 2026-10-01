import { useRef } from 'react'
import { Container } from '../../ui/Container.tsx'
import { BanIcon } from '../../ui/icons.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { Strike } from '../../ui/Strike.tsx'
import { useSeen } from '../../ui/useSeen.ts'
import { RAW, SUMMARY, UNIQUE } from '../clean/mergeRows.ts'
import { TraceLayer } from '../hero/TraceLayer.tsx'
import { Section, SectionHead } from '../SectionHead.tsx'

const colHead = 'flex items-baseline justify-between gap-3 border-b-2 border-ink pb-3 text-small font-semibold text-ink'

/**
 * Raw rows as the sources returned them, traced into the unique rows they became. Rows that fail a
 * check are struck through with the reason. On wide screens the lines draw once the section is in view.
 */
export function CleanByDefault() {
  const sceneRef = useRef<HTMLDivElement>(null)
  const seen = useSeen(sceneRef, 0.4)

  return (
    <Section labelledBy="clean-title">
      <Container data-tour="landing-clean">
        <SectionHead
          id="clean-title"
          index="04"
          kicker="Clean by default"
          title={(s) => (
            <>
              Sources overlap. <Mark on={s} delay={350}>You get each row once.</Mark>
            </>
          )}
          lede="Duplicates merge, rows that fail your filters are set aside and disagreements are shown. You review a short list."
        />

        <div
          ref={sceneRef}
          className="relative mt-10 grid grid-cols-[minmax(0,1fr)] gap-12 md:mt-12 lg:mt-8 lg:grid-cols-[minmax(0,1fr)_6rem_minmax(0,1fr)] lg:gap-0"
        >
          <div className="min-w-0">
            <h3 className={colHead}>
              What the sources returned <span className="font-mono text-micro font-normal text-ink-3">{SUMMARY.raw} rows</span>
            </h3>
            <ul>
              {RAW.map((r, i) => (
                <li
                  key={r.id}
                  data-from={`clean:${r.id}`}
                  data-target={r.into ? `clean:${r.into}` : undefined}
                  data-method={r.method}
                  className="grid h-8.5 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-b border-line text-small"
                >
                  {r.rejected ? (
                    <>
                      <span className="truncate text-ink-2">
                        <Strike on={seen} delay={500 + i * 70}>
                          {r.name}
                        </Strike>
                      </span>
                      <span className="inline-flex items-center gap-1.5 text-micro text-ink-2">
                        <BanIcon className="size-3.5 text-blocked" />
                        <span className="sr-only">Set aside:</span> {r.rejected}
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="truncate text-ink">
                        {r.name} <span className="text-ink-3">· {r.tier}</span>
                      </span>
                      <span className="font-mono text-micro text-ink">
                        <Mark ink={r.method}>{r.domain.split('.')[0]}</Mark>
                      </span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div aria-hidden className="hidden lg:block" />

          <div className="flex min-w-0 flex-col">
            <h3 className={colHead}>
              What you get <span className="font-mono text-micro font-normal text-ink-3">{SUMMARY.unique} rows</span>
            </h3>
            <ul>
              {UNIQUE.map((u) => (
                <li key={u.id} data-to={`clean:${u.id}`} className="flex flex-col border-b border-line py-1 text-small">
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="truncate font-medium text-ink">{u.name}</span>
                    <span className="shrink-0 text-ink-2">
                      {u.tier}
                      {u.conflict && (
                        <span className="text-ink-3" title="Sources disagree on this value">
                          {' '}
                          ≠ {u.conflict}
                        </span>
                      )}
                    </span>
                  </span>
                  <span className="truncate font-mono text-micro text-ink-3">
                    {u.sources.map((d) => d.split('.')[0]).join(' + ')}
                    {u.merged > 1 && <span className="font-sans"> · {u.conflict ? 'kept by rule, both shown' : `${u.merged} merged`}</span>}
                  </span>
                </li>
              ))}
            </ul>

            <dl className="mt-auto grid grid-cols-2 gap-x-6 gap-y-4 pt-6 sm:grid-cols-4">
              <Stat value={SUMMARY.raw} label="raw rows" />
              <Stat value={SUMMARY.unique} label="unique rows" mark={seen} />
              <Stat value={SUMMARY.duplicates} label="duplicates merged" />
              <Stat value={SUMMARY.rejected} label="set aside" />
            </dl>
            <p className="mt-3 text-small text-ink-3">
              Sample run: {SUMMARY.label}, first rows. Same row means the {SUMMARY.matchedOn.toLowerCase()}.
            </p>
          </div>

          <TraceLayer sceneRef={sceneRef} rowId={seen ? 'clean' : null} />
        </div>
      </Container>
    </Section>
  )
}

function Stat({ value, label, mark }: { value: number; label: string; mark?: boolean }) {
  return (
    <div className="flex flex-col-reverse gap-0.5 border-t-2 border-ink pt-2">
      <dt className="text-small text-ink-2">{label}</dt>
      <dd className="font-display font-wide text-h2 font-extrabold text-ink tabular-nums">
        {mark === undefined ? value : <Mark on={mark} delay={900}>{value}</Mark>}
      </dd>
    </div>
  )
}
