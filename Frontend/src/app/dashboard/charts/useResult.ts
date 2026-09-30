import { useMemo } from 'react'
import { runQuery } from '../../../analytics/aggregate.ts'
import type { Filter, QueryResult } from '../../../analytics/aggregate.ts'
import type { TableProfile } from '../../../analytics/profile.ts'
import type { ChartSpec } from '../../../analytics/spec.ts'

/** A tile's exact result: its own query plus the dashboard's filters. */
export function useResult(profile: TableProfile, spec: ChartSpec, filters: Filter[] = []): QueryResult {
  return useMemo(
    () => runQuery(profile, { ...spec.query, filters: [...(spec.query.filters ?? []), ...filters] }),
    [profile, spec.query, filters],
  )
}
