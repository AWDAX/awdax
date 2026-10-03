import { useEffect, useMemo, useState } from 'react'
import type { SVGProps } from 'react'
import type { TableProfile } from '../../analytics/profile.ts'
import { CloseIcon, DownloadIcon, TableIcon, ExcelIcon, BracesIcon, ListLinesIcon, DatabaseIcon, FileIcon, CodeIcon, MarkdownIcon } from '../../ui/appIcons.tsx'
import { Button } from '../../ui/Button.tsx'
import { Select } from '../../ui/Select.tsx'
import { CopyButton } from '../../ui/micro/CopyButton.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { useFocusTrap } from '../../ui/useFocusTrap.ts'
import { download } from './download.ts'
import { toCSV, toJSON, toJSONL, toMarkdown, toTSV, toXML } from './formats.ts'
import { buildSheet, fileBase } from './scope.ts'
import type { ExportScope } from './scope.ts'
import { DIALECT_LABEL, tableIdentifier, toSQL } from './sql.ts'
import type { Dialect } from './sql.ts'

type Format = 'csv' | 'xlsx' | 'json' | 'jsonl' | 'sql' | 'tsv' | 'xml' | 'md'

const FORMATS: { id: Format; label: string; ext: string; mime: string; note: string; icon: (p: SVGProps<SVGSVGElement>) => React.JSX.Element }[] = [
  { id: 'csv', label: 'CSV', ext: 'csv', mime: 'text/csv', note: 'Excel, Power BI, Google Sheets', icon: TableIcon },
  { id: 'xlsx', label: 'Excel', ext: 'xlsx', mime: '', note: 'Typed numbers and dates, plus an About sheet', icon: ExcelIcon },
  { id: 'json', label: 'JSON', ext: 'json', mime: 'application/json', note: 'An array of objects', icon: BracesIcon },
  { id: 'jsonl', label: 'JSON Lines', ext: 'jsonl', mime: 'application/x-ndjson', note: 'One object per line', icon: ListLinesIcon },
  { id: 'sql', label: 'SQL', ext: 'sql', mime: 'application/sql', note: 'CREATE TABLE + INSERT', icon: DatabaseIcon },
  { id: 'tsv', label: 'TSV', ext: 'tsv', mime: 'text/tab-separated-values', note: 'Tab-separated', icon: FileIcon },
  { id: 'xml', label: 'XML', ext: 'xml', mime: 'application/xml', note: 'One <row> per row', icon: CodeIcon },
  { id: 'md', label: 'Markdown', ext: 'md', mime: 'text/markdown', note: 'A table for docs and READMEs', icon: MarkdownIcon },
]

type Props = { profile: TableProfile; scope: ExportScope; title: string; onClose: () => void }

/** Export exactly what's on screen (all rows, filtered rows, or one chart's numbers) as data. */
export function ExportDialog({ profile, scope, title, onClose }: Props) {
  const { toast } = useToast()
  const trap = useFocusTrap<HTMLDivElement>(true)
  const [format, setFormat] = useState<Format>('csv')
  const [raw, setRaw] = useState(false)
  const [dialect, setDialect] = useState<Dialect>('postgres')
  const [table, setTable] = useState(() => tableIdentifier(title) || 'awdax_data')
  const [busy, setBusy] = useState(false)
  const sheet = useMemo(() => buildSheet(profile, scope), [profile, scope])
  const meta = useMemo(
    () => ({ title, source: profile.sourceUrl, filters: scope.label === 'All rows' ? undefined : scope.label }),
    [title, profile.sourceUrl, scope.label],
  )
  const spec = FORMATS.find((f) => f.id === format)!

  const text = useMemo(() => {
    const o = { raw }
    switch (format) {
      case 'csv': return toCSV(sheet, o)
      case 'tsv': return toTSV(sheet, o)
      case 'json': return toJSON(sheet, o)
      case 'jsonl': return toJSONL(sheet, o)
      case 'xml': return toXML(sheet, o)
      case 'md': return toMarkdown(sheet, o)
      case 'sql': return toSQL(sheet, dialect, table || 'awdax_data', meta)
      default: return ''
    }
  }, [format, raw, sheet, dialect, table, meta])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const save = async () => {
    const name = `${fileBase(title, scope.label)}.${spec.ext}`
    setBusy(true)
    try {
      if (format === 'xlsx') {
        const { toXLSX } = await import('./xlsx.ts')
        download(await toXLSX(sheet, { ...meta, raw }), name)
      } else {
        download(new Blob([text], { type: `${spec.mime};charset=utf-8` }), name)
      }
      toast({ title: 'Export ready', description: `${name} · ${sheet.rows.length} rows`, tone: 'success' })
      onClose()
    } catch (err) {
      toast({ title: 'Export failed', description: err instanceof Error ? err.message : String(err), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const preview = text.split('\n').slice(0, 14).join('\n')
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 sm:p-10" data-lenis-prevent onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={trap} role="dialog" aria-modal="true" aria-label="Export data" className="w-full max-w-3xl rounded-panel border-2 border-ink bg-surface p-5">
        <div className="mb-4 flex items-start gap-4 border-b-2 border-ink pb-3">
          <div>
            <h2 className="font-display text-h3 font-extrabold">Export data</h2>
            <p className="text-small text-ink-2">
              {scope.label} · {sheet.rows.length.toLocaleString('en-IN')} rows × {sheet.columns.length} columns
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="ml-auto grid size-8 place-items-center rounded-control hover:bg-sunken">
            <CloseIcon />
          </button>
        </div>

        <fieldset className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <legend className="sr-only">Format</legend>
          {FORMATS.map((f) => (
            <label key={f.id} className={`flex cursor-pointer flex-col gap-1.5 rounded-panel border-2 p-2.5 ${format === f.id ? 'border-ink bg-signal-soft' : 'border-line hover:border-ink'}`}>
              <input type="radio" name="format" value={f.id} checked={format === f.id} onChange={() => setFormat(f.id)} className="sr-only" />
              <div className="flex items-center gap-2">
                <f.icon className={format === f.id ? 'text-ink' : 'text-ink-2'} />
                <span className="text-small font-semibold">{f.label}</span>
              </div>
              <span className="text-micro text-ink-3">{f.note}</span>
            </label>
          ))}
        </fieldset>

        <div className="mt-4 flex flex-wrap items-end gap-4 text-small">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={raw} onChange={(e) => setRaw(e.target.checked)} className="size-4 accent-ink" />
            Values exactly as scraped (text), not parsed numbers
          </label>
          {format === 'sql' && (
            <>
              <label className="flex flex-col gap-1">
                <span className="text-micro text-ink-3">Database</span>
                <Select
                  label="Database"
                  value={dialect}
                  onChange={(d) => setDialect(d)}
                  options={(Object.keys(DIALECT_LABEL) as Dialect[]).map((d) => ({ value: d, label: DIALECT_LABEL[d] }))}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-micro text-ink-3">Table name</span>
                <input value={table} onChange={(e) => setTable(tableIdentifier(e.target.value))} className="h-9 w-80 max-w-full rounded-control border-2 border-line px-2 font-mono focus:border-ink focus:outline-none" />
              </label>
            </>
          )}
        </div>

        {format !== 'xlsx' && (
          <div className="relative mt-4">
            <pre className="max-h-64 overflow-auto rounded-panel bg-sunken p-3 font-mono text-micro whitespace-pre" data-lenis-prevent>
              {preview}
              {text.split('\n').length > 14 && '\n…'}
            </pre>
            <CopyButton text={() => text} label={`Copy the ${spec.label}`} className="absolute top-2 right-2 bg-surface" />
          </div>
        )}
        <p className="mt-3 text-micro text-ink-3">
          Missing values stay empty (NULL in SQL), never 0. Text cells starting with = + − @ get a leading ' in CSV and TSV so spreadsheets don’t run them as formulas.
          {!raw && profile.columns.some((c) => c.ranged) && ' Ranges are exported as their lowest value; tick “Values exactly as scraped” to keep the text.'}
        </p>

        <div className="mt-4 flex gap-2">
          <Button onClick={save} loading={busy}>
            <DownloadIcon /> Download .{spec.ext}
          </Button>
          <Button variant="secondary" onClick={onClose}>
            <CloseIcon /> Cancel
          </Button>
        </div>
      </div>
    </div>
  )
}
