import { useEffect, useId, useRef, useState } from 'react'
import type { ClipboardEvent, DragEvent, KeyboardEvent, ReactNode } from 'react'
import { CloseIcon, FileIcon, SendIcon } from '../../ui/appIcons.tsx'
import { ACCEPT, formatBytes } from '../files/readFile.ts'
import { VoiceInput } from '../voice/VoiceInput.tsx'

type Props = {
  value: string
  onChange: (v: string) => void
  onSubmit: (text: string, files: File[]) => void
  busy?: boolean
  placeholder?: string
  /** Allow attaching data files (drag and drop, paste, or a control outside that opens `fileInputId`). */
  allowFiles?: boolean
  /** Files can be attached from outside too (a "Try" card, the strip below). */
  files?: File[]
  onFilesChange?: (files: File[]) => void
  size?: 'lg' | 'md'
  autoFocus?: boolean
  /** A strip attached under the box, like ChatGPT's "Choose project · Files". */
  footer?: ReactNode
  /** An id for the hidden file input, so a <label htmlFor> elsewhere can open it. */
  fileInputId?: string
  label: string
}

/**
 * The one prompt box, used to start a chat and to ask follow-ups. Grows with the text, takes voice (speech to
 * text) and, where allowed, data files by drag and drop, paste or the strip's "Upload a file". Enter sends; Shift +
 * Enter breaks.
 */
export function PromptBox({
  value, onChange, onSubmit, busy = false, placeholder, allowFiles = false, files = [], onFilesChange,
  size = 'md', autoFocus, footer, fileInputId, label,
}: Props) {
  const area = useRef<HTMLTextAreaElement>(null)
  const [interim, setInterim] = useState('')
  const [dragging, setDragging] = useState(false)
  const autoId = useId()
  const inputId = fileInputId ?? `${autoId}-files`
  const shown = interim ? `${value}${value && !value.endsWith(' ') ? ' ' : ''}${interim}` : value
  const canSend = !busy && (value.trim() !== '' || files.length > 0)

  useEffect(() => {
    const el = area.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [shown])

  const addFiles = (list: FileList | File[]) => {
    if (!allowFiles || !onFilesChange) return
    const next = [...files, ...Array.from(list)].slice(0, 3)
    onFilesChange(next)
  }
  const send = () => canSend && onSubmit(value.trim(), files)
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send()
    }
  }
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    if (allowFiles && e.clipboardData.files.length) {
      e.preventDefault()
      addFiles(e.clipboardData.files)
    }
  }
  const drag = (on: boolean) => (e: DragEvent) => {
    if (!allowFiles) return
    e.preventDefault()
    setDragging(on)
  }

  const big = size === 'lg'
  return (
    <div>
      <div
        onDragOver={drag(true)}
        onDragLeave={drag(false)}
        onDrop={(e) => {
          drag(false)(e)
          if (allowFiles) addFiles(e.dataTransfer.files)
        }}
        className={`relative z-10 rounded-panel border-2 bg-surface p-2.5 transition-colors duration-300 ease-soft ${dragging ? 'border-dashed border-ink bg-signal-soft' : 'border-ink'}`}
      >
        {files.length > 0 && (
          <ul className="mb-2 flex flex-wrap gap-2 px-1 pt-1">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`} className="flex items-center gap-2 rounded-control border-2 border-line bg-sunken py-1 pr-1 pl-2 text-small">
                <FileIcon className="shrink-0 text-ink-2" />
                <span className="max-w-48 truncate font-medium">{f.name}</span>
                <span className="font-mono text-micro text-ink-3">{formatBytes(f.size)}</span>
                <button type="button" aria-label={`Remove ${f.name}`} onClick={() => onFilesChange?.(files.filter((_, j) => j !== i))} className="grid size-6 place-items-center rounded-control hover:bg-surface">
                  <CloseIcon />
                </button>
              </li>
            ))}
          </ul>
        )}
        <label htmlFor={`${inputId}-text`} className="sr-only">
          {label}
        </label>
        <textarea
          id={`${inputId}-text`}
          ref={area}
          value={shown}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKey}
          onPaste={onPaste}
          rows={big ? 2 : 1}
          disabled={busy}
          autoFocus={autoFocus}
          placeholder={placeholder}
          className={`block w-full resize-none bg-transparent px-2 outline-none placeholder:text-ink-3 ${big ? 'min-h-16 py-1.5 text-lead' : 'min-h-9 py-1.5 text-body'}`}
        />
        <div className="mt-1 flex items-center gap-1.5">
          {/* No attach button in the box: "Upload a file" under it opens this input by id. */}
          {allowFiles && (
            <input
              id={inputId}
              aria-label="Attach a data file"
              type="file"
              accept={ACCEPT}
              multiple
              tabIndex={-1}
              className="sr-only"
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files)
                e.target.value = ''
              }}
            />
          )}
          <span className="ml-auto" />
          <VoiceInput
            disabled={busy}
            onInterim={setInterim}
            onTranscript={(t) => {
              setInterim('')
              onChange(`${value}${value && !value.endsWith(' ') ? ' ' : ''}${t}`.trimStart())
              area.current?.focus()
            }}
          />
          <button
            type="button"
            onClick={send}
            disabled={!canSend}
            aria-label="Send"
            title="Send (Enter)"
            className="grid size-9 place-items-center rounded-control border-2 border-ink bg-signal transition-[background-color,color,opacity,scale] duration-300 ease-soft hover:bg-ink hover:text-signal active:scale-97 disabled:opacity-35"
          >
            {busy ? <span aria-hidden className="size-4 animate-spin rounded-full border-2 border-current border-r-transparent" /> : <SendIcon />}
          </button>
        </div>
        {dragging && (
          <p className="pointer-events-none absolute inset-0 grid place-items-center rounded-panel text-small font-medium">Drop a CSV, Excel or JSON file</p>
        )}
      </div>
      {footer && <div className="-mt-1 mx-3 rounded-b-panel border-2 border-t-0 border-ink bg-sunken px-3 pt-2.5 pb-2">{footer}</div>}
    </div>
  )
}
