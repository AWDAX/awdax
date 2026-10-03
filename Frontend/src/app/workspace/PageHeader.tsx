import type { ReactNode } from 'react'

/** The title row at the top of a workspace view (projects report, ask database). */
export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b-2 border-ink pb-5">
      <div>
        <p className="font-mono text-micro text-ink-3">{eyebrow}</p>
        <h1 className="mt-2 font-display text-h2 font-extrabold">{title}</h1>
      </div>
      {children}
    </header>
  )
}
