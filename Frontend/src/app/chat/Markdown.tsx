import { useState } from 'react'
import type { ReactNode } from 'react'

/**
 * The bot's messages: a little Markdown (**bold**, _italic_, `code`, [links](…), | tables |) inside a plain-text
 * run report (indented bullets, "URL: …" lines). Rendered as React nodes, never as HTML, so scraped text can't
 * inject markup. Links open only for http(s). Long reports fold after a few lines.
 */
const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\)|https?:\/\/[^\s)]+|(?<![\w*])_[^_\n]+_(?![\w]))/g

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let i = 0
  for (const m of text.matchAll(INLINE)) {
    const t = m[0]
    if (m.index > last) out.push(text.slice(last, m.index))
    const k = `${key}-${i++}`
    if (t.startsWith('**')) out.push(<strong key={k}>{t.slice(2, -2)}</strong>)
    else if (t.startsWith('`')) out.push(<code key={k} className="rounded-sm bg-sunken px-1 font-mono text-[0.9em]">{t.slice(1, -1)}</code>)
    else if (t.startsWith('[')) {
      const label = t.slice(1, t.indexOf(']'))
      out.push(<Ext key={k} href={m[2]}>{label}</Ext>)
    } else if (t.startsWith('http')) out.push(<Ext key={k} href={t}>{t}</Ext>)
    else out.push(<em key={k}>{t.slice(1, -1)}</em>)
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="break-all underline decoration-line-strong underline-offset-2 hover:decoration-ink">
      {children}
    </a>
  )
}

type Block = { kind: 'table'; rows: string[][] } | { kind: 'text'; lines: string[] }

function blocks(text: string): Block[] {
  const out: Block[] = []
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const isRow = /^\s*\|.*\|\s*$/.test(line)
    const prev = out[out.length - 1]
    if (isRow) {
      if (/^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$/.test(line)) continue // the | --- | divider
      const cells = line.trim().slice(1, -1).split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'))
      if (prev?.kind === 'table') prev.rows.push(cells)
      else out.push({ kind: 'table', rows: [cells] })
    } else if (prev?.kind === 'text') prev.lines.push(line)
    else out.push({ kind: 'text', lines: [line] })
  }
  return out
}

function renderBlock(b: Block, i: number): ReactNode {
  if (b.kind === 'table') {
    const [head, ...body] = b.rows
    return (
      <div key={i} className="my-2 overflow-x-auto rounded-control border-2 border-line" data-lenis-prevent>
        <table className="w-full min-w-max text-small">
          <thead>
            <tr className="border-b-2 border-ink text-left">
              {head.map((c, j) => (
                <th key={j} className="px-2 py-1 font-medium">{inline(c, `h${i}${j}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((r, k) => (
              <tr key={k} className="border-b border-line">
                {r.map((c, j) => (
                  <td key={j} className="px-2 py-1 font-mono text-micro">{inline(c, `c${i}${k}${j}`)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return (
    <div key={i} className="whitespace-pre-wrap">
      {b.lines.map((line, j) => {
        // "=== AWDAX SOURCE DISCOVERY ===" banners in the run report read as headings.
        const banner = /^=+\s*(.+?)\s*=+$/.exec(line.trim())
        const heading = !!banner || /^#{1,4}\s+/.test(line) || /^[A-Z][A-Z0-9 ()/-]{3,}$/.test(line.trim())
        const body = banner ? banner[1] : line.replace(/^#{1,4}\s+/, '')
        return (
          <div key={j} className={heading ? 'mt-2 font-semibold' : line.trim() === '---' ? 'my-1 border-t border-line' : undefined}>
            {line.trim() === '---' ? null : body === '' ? <br /> : inline(body, `l${i}${j}`)}
          </div>
        )
      })}
    </div>
  )
}

const FOLD_LINES = 14

export function Markdown({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const lines = text.split('\n').length
  const long = lines > FOLD_LINES
  const shown = long && !open ? text.split('\n').slice(0, FOLD_LINES).join('\n') : text
  return (
    <div className="text-body leading-relaxed text-ink">
      {blocks(shown).map(renderBlock)}
      {long && (
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="mt-2 text-small font-medium underline underline-offset-2 hover:text-ink-2">
          {open ? 'Show less' : `Show the full run report (${lines} lines)`}
        </button>
      )}
    </div>
  )
}
