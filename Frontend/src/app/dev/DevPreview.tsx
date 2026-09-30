import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'
import { evCars, evSales } from '../../analytics/fixtures.ts'
import { profileTable } from '../../analytics/profile.ts'
import { MicroGallery } from '../../ui/micro/MicroGallery.tsx'
import { Dashboard } from '../dashboard/Dashboard.tsx'
import { useDashboard } from '../dashboard/useDashboard.ts'

const TABLES = { sales: evSales, cars: evCars }

/**
 * Dev-only checks at /app/dev (AppRoot mounts it only when import.meta.env.DEV, so production never ships it).
 * ?view=micro: the ported micro components. ?view=dashboard&table=sales|cars: the dashboard on sample tables,
 * for checking without a live scrape.
 */
export default function DevPreview() {
  const [params] = useSearchParams()
  const view = params.get('view') ?? 'micro'
  const table = (params.get('table') ?? 'sales') as keyof typeof TABLES
  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <p className="mb-4 flex gap-4 font-mono text-micro text-ink-3">
        Dev preview · {view}
        <Link to="?view=micro" className="underline">micro</Link>
        <Link to="?view=dashboard&table=sales" className="underline">dashboard: sales</Link>
        <Link to="?view=dashboard&table=cars" className="underline">dashboard: cars</Link>
      </p>
      {view === 'micro' && <MicroGallery />}
      {view === 'dashboard' && <SampleDashboard key={table} name={table} />}
    </div>
  )
}

function SampleDashboard({ name }: { name: keyof typeof TABLES }) {
  const profile = useMemo(() => profileTable(TABLES[name]), [name])
  const dash = useDashboard(`dev-${name}`, profile)
  return <Dashboard profile={profile} dash={dash} title={TABLES[name].name ?? name} />
}
