import { useRef, useState } from 'react'
import { useLenis } from 'lenis/react'
import { sampleByKey } from '../../domain/fixtures/index.ts'
import { formatValue } from '../../domain/format.ts'
import type { Cell, Column, Method, Row } from '../../domain/types.ts'
import { CellReceipt } from '../../product/CellReceipt.tsx'
import { Container } from '../../ui/Container.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { Section, SectionHead } from '../SectionHead.tsx'

const { dataset, plan, label } = sampleByKey.jobs
// Nine rows: one with no stipend on any source, one where two sources disagree, one read by AI.
const ROWS = dataset.rows.slice(0, 9)
const KEYS = ['title', 'company', 'stipend', 'posted_at']
const COLUMNS = KEYS.map((k) => dataset.columns.find((c) => c.key === k)!)
// Company hides on phones so the stipend stays readable.
const HIDE: Record<string, string> = { company: 'hidden sm:table-cell' }

const methodOf = (row: Row): Method => plan.sources.find((s) => s.id === row.sourceIds[0])?.method ?? 'content'
const rowLabel = (row: Row) => `${row.cells.title.value} · ${row.cells.company.value}`

export function Receipts() {
  const [sel, setSel] = useState({ row: 0, key: 'stipend' })
  const receiptRef = useRef<HTMLDivElement>(null)
  const lenis = useLenis()
  const row = ROWS[sel.row]
  const column = COLUMNS.find((c) => c.key === sel.key)!

  const choose = (r: number, key: string) => {
    setSel({ row: r, key })
    // Stacked layout: bring the receipt into view if it sits below the fold. Through Lenis when it
    // runs, so the page glides instead of jumping and snapping back; it honours scroll-mt-24.
    const el = receiptRef.current
    if (el && el.getBoundingClientRect().top > window.innerHeight - 120) {
      if (lenis) lenis.scrollTo(el)
      else el.scrollIntoView({ block: 'nearest' })
    }
  }

  return (
    <Section labelledBy="receipts-title">
      <Container>

        <SectionHead
          id="receipts-title"
          index="03"
          kicker="Every value has a source"
          title={(seen) => (
            <>
              Every value comes with <Mark on={seen} delay={350}>a receipt.</Mark>
            </>
          )}
          lede="Select any cell to see the page it came from, when, how it was read and the exact sentence. Missing values stay empty."
        />

        <div className="mt-10 grid grid-cols-[minmax(0,1fr)] items-start gap-8 md:mt-12 lg:mt-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-12">
          <table className="w-full table-fixed border-collapse text-small">
            <caption className="mb-3 text-left text-small text-ink-3">
              Sample run: {label}. Select a cell to see its receipt.
            </caption>
            <thead>
              <tr className="border-b-2 border-ink text-left">
                {COLUMNS.map((c) => (
                  <th key={c.key} scope="col" className={`h-9 px-2 font-medium text-ink-3 ${HIDE[c.key] ?? ''} ${c.key === 'title' ? 'w-[40%]' : ''}`}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r, i) => (
                <tr key={r.id} className="border-b border-line">
                  {COLUMNS.map((c) => (
                    <td key={c.key} className={`p-0 ${HIDE[c.key] ?? ''}`}>
                      <CellButton
                        column={c}
                        cell={r.cells[c.key]}
                        method={methodOf(r)}
                        selected={sel.row === i && sel.key === c.key}
                        onSelect={() => choose(i, c.key)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <div ref={receiptRef} id="receipt" aria-live="polite" className="scroll-mt-24">
            <CellReceipt
              key={`${row.id}:${column.key}`}
              column={column}
              cell={row.cells[column.key]}
              rowLabel={rowLabel(row)}
              fallbackMethod={methodOf(row)}
            />
          </div>
        </div>
      </Container>
    </Section>
  )
}

type CellButtonProps = { column: Column; cell: Cell; method: Method; selected: boolean; onSelect: () => void }

function CellButton({ column, cell, method, selected, onSelect }: CellButtonProps) {
  const missing = cell.status === 'not_found'
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-controls="receipt"
      onClick={onSelect}
      className={`block h-10 w-full truncate px-2 text-left outline-offset-[-2px] hover:bg-sunken focus-visible:outline-2 focus-visible:outline-ink ${
        selected ? 'outline-2 outline-ink' : ''
      } ${missing ? 'text-ink-3' : 'text-ink'}`}
    >
      {missing ? (
        'Not found'
      ) : (
        <Mark ink={cell.method ?? method} on={selected}>
          {formatValue(cell.value, column, true)}
        </Mark>
      )}
      {cell.status === 'conflict' && (
        <span className="ml-1 text-ink-3" title="Sources disagree on this value">
          <span aria-hidden>≠</span>
          <span className="sr-only">(sources disagree)</span>
        </span>
      )}
    </button>
  )
}
