import { ArrowIcon } from '../../ui/icons.tsx'

type Props = {
  text: string
  typed: number
  /** The request has been sent for planning. */
  sent: boolean
}

/**
 * The request typing itself. The full sentence sits underneath, invisible, so the bar is
 * already its final height and nothing below it moves while the letters appear.
 */
export function RequestBar({ text, typed, sent }: Props) {
  const typing = typed < text.length
  return (
    <div className="flex flex-col gap-3 border-b border-line py-5 sm:flex-row sm:items-center sm:gap-6">
      <p className="sr-only">Sample request: {text}</p>
      <div aria-hidden className="grid flex-1 text-h3 font-medium text-ink">
        <span className="invisible col-start-1 row-start-1">{text}</span>
        <span className="col-start-1 row-start-1">
          {text.slice(0, typed)}
          {(typing || !sent) && (
            <span className="ml-px inline-block h-[1.1em] w-0.5 translate-y-[0.2em] animate-caret bg-ink" />
          )}
          {typed === 0 && <span className="text-ink-3">Describe the data you need</span>}
        </span>
      </div>
      <span
        aria-hidden
        className={`inline-flex h-10 shrink-0 items-center gap-2 self-start rounded-control border-2 border-ink px-4 text-small font-semibold text-ink transition-colors duration-500 ease-soft sm:self-auto ${
          sent ? 'bg-signal' : 'bg-surface'
        }`}
      >
        {sent ? 'Planned' : 'Plan it'}
        <ArrowIcon />
      </span>
    </div>
  )
}
