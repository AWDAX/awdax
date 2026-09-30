import type { Plan } from '../domain/types.ts'

export type PlanDensity = 'compact' | 'full'

/** What PlanCard shows, in reveal order. Compact keeps one interpretation. */
export function planSections(plan: Plan, density: PlanDensity) {
  return {
    columns: plan.columns,
    filters: plan.filters,
    interpretations: density === 'compact' ? plan.interpretations.slice(0, 1) : plan.interpretations,
    sources: plan.sources,
  }
}

/** How many items PlanCard reveals one by one; the hero timeline paces itself on this. */
export function planItemCount(plan: Plan, density: PlanDensity): number {
  const s = planSections(plan, density)
  return s.columns.length + s.filters.length + s.interpretations.length + s.sources.length
}
