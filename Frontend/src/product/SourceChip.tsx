import type { Method } from '../domain/types.ts'
import { Mark } from '../ui/Mark.tsx'
import { METHOD, METHOD_ORDER } from './meta.ts'

type Props = {
  domain: string
  method: Method
  /** How many other sources the same row was found on. */
  more?: number
  /** Inside a narrow @container, show only the domain's first label ("fundwire"). The title keeps the full one. */
  shortWhenNarrow?: boolean
  className?: string
}

/** The source a value came from: the domain, highlighted in its method's color. The title names the method. */
export function SourceChip({ domain, method, more = 0, shortWhenNarrow = false, className = '' }: Props) {
  return (
    <span
      title={`${METHOD[method].label} from ${domain}${more ? `, also found on ${more} more` : ''}`}
      className={`inline-flex max-w-full min-w-0 items-baseline gap-1.5 font-mono text-micro text-ink ${className}`}
    >
      <Mark ink={method} className="min-w-0 truncate">
        {shortWhenNarrow ? (
          <>
            <span className="@lg:hidden">{domain.split('.')[0]}</span>
            <span className="hidden @lg:inline">{domain}</span>
          </>
        ) : (
          domain
        )}
      </Mark>
      {more > 0 && <span className="shrink-0 text-ink-3">+{more}</span>}
    </span>
  )
}

export function MethodLegend({ className = '' }: { className?: string }) {
  return (
    <ul aria-label="Collection methods" className={`flex flex-wrap gap-x-4 gap-y-1 text-small text-ink ${className}`}>
      {METHOD_ORDER.map((m) => (
        <li key={m}>
          <Mark ink={m}>{METHOD[m].label}</Mark>
        </li>
      ))}
    </ul>
  )
}
