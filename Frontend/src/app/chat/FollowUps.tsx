import type { FollowUp } from '../../analytics/suggest.ts'
import { SparkleIcon } from '../../ui/appIcons.tsx'

/** Follow-up questions as chips, read off the table's shape. Each one is answered exactly from the data. */
export function FollowUps({ items, onPick }: { items: FollowUp[]; onPick: (f: FollowUp) => void }) {
  if (items.length === 0) return null
  return (
    <div>
      <p className="flex items-center gap-1.5 font-mono text-micro text-ink-3">
        <SparkleIcon /> Ask next
      </p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {items.map((f) => (
          <li key={f.id}>
            <button
              type="button"
              onClick={() => onPick(f)}
              className="rounded-control border-2 border-line px-3 py-1.5 text-left text-small text-ink-2 transition-colors duration-300 ease-soft hover:border-ink hover:bg-signal-soft hover:text-ink"
            >
              {f.text}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
