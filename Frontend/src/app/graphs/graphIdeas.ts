import { runQuery } from '../../analytics/aggregate.ts'
import { isGroupable } from '../../analytics/profile.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import type { ChartSpec, ChartType } from '../../analytics/spec.ts'
import { measures, timeColumn, timeBucket } from '../../analytics/suggest.ts'

/** A row axis is only needed when numeric data has no usable date or label column. */
export function graphProfile(profile: TableProfile): TableProfile {
  if (!profile.rowCount || profile.columns.some((column) => isGroupable(column) && column.distinct >= 2)) return profile
  const index = profile.columns.length
  return {
    ...profile,
    columns: [...profile.columns, {
      index, name: 'Observation', label: 'Observation', kind: 'category',
      filled: profile.rowCount, missing: 0, distinct: profile.rowCount,
      labels: profile.raw.map((_, row) => `Row ${row + 1}`), excluded: [], scale: 0, virtual: true,
    }],
  }
}

const spec = (id: string, type: ChartType, title: string, reason: string, query: ChartSpec['query']): ChartSpec =>
  ({ id, type, title, reason, query, labels: false })

/** One useful chart per numeric field, plus distributions for categorical fields. */
export function graphIdeas(profile: TableProfile): ChartSpec[] {
  if (!profile.rowCount) return []
  const candidateDate = timeColumn(profile)
  const date = candidateDate?.grain === 'day' && profile.rowCount > 5 && candidateDate.distinct >= profile.rowCount * 0.8
    ? undefined : candidateDate
  const groups = profile.columns.filter(isGroupable).filter((c) => c.distinct >= 2 && c.filled > 0)
  const category = groups.filter((c) => c.kind === 'category' || c.kind === 'text').sort((a, b) => a.distinct - b.distinct)[0]
    ?? groups.find((c) => c.kind === 'url')
    ?? groups.find((c) => c.name === 'Observation')
  const out: ChartSpec[] = []

  for (const measure of measures(profile)) {
    const group = date ?? category ?? candidateDate
    if (!group) {
      out.push(spec(`measure-${measure.index}`, 'kpi', measure.label, 'One numeric field with no useful grouping column.', { measure: measure.index, agg: 'avg' }))
      continue
    }
    const isDate = group.kind === 'period'
    const eventDate = isDate && group === candidateDate && !date
    const additive = /count|qty|quantity|units|sales|sold|revenue|total|volume|downloads|views|registrations/i.test(measure.name)
    const agg = additive ? 'sum' : 'avg'
    const query: ChartSpec['query'] = {
      groupBy: group.index, measure: measure.index, agg,
      sort: isDate ? 'time' : 'value-desc',
      bucket: isDate ? timeBucket(group) : undefined,
      limit: isDate ? undefined : 15, other: !isDate,
    }
    out.push(spec(`measure-${measure.index}`, eventDate ? 'column' : isDate ? 'line' : 'bar', `${agg === 'avg' ? 'Average' : 'Total'} ${measure.label} by ${group.label}`,
      eventDate ? `Columns compare values across event dates.` : isDate ? `A line follows ${group.label} in time order.` : `Bars compare ${measure.label} across ${group.label}.`, query))
  }

  for (const group of groups.filter((c) => c.kind !== 'period' && c.name !== 'Observation').slice(0, 5)) {
    const query: ChartSpec['query'] = { groupBy: group.index, agg: 'count', sort: 'value-desc', limit: group.distinct > 10 ? 10 : undefined, other: group.distinct > 10 }
    const type: ChartType = group.distinct <= 6 ? 'donut' : 'bar'
    out.push(spec(`count-${group.index}`, type, `Rows by ${group.label}`,
      type === 'donut' ? `A few ${group.label} groups make a readable share chart.` : `Bars compare how many rows each ${group.label} has.`, query))
  }
  if (date && measures(profile).length === 0) {
    out.unshift(spec(`count-${date.index}`, 'line', `Rows by ${date.label}`, `A line follows row counts in time order.`,
      { groupBy: date.index, agg: 'count', sort: 'time', bucket: timeBucket(date) }))
  }
  return out.filter((chart) => chart.type === 'kpi' || runQuery(profile, chart.query).used > 0)
}
