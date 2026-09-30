import { useCallback, useEffect, useState } from 'react'
import type { Query } from '../../analytics/aggregate.ts'
import type { ChartType } from '../../analytics/spec.ts'
import type { Intent } from '../../analytics/suggest.ts'

/**
 * Questions asked about one chat's data, kept in this browser. Only the question and its query are stored;
 * the numbers are recomputed from the current table every time, so an answer never goes stale.
 */
export interface SavedAnswer {
  id: string
  question: string
  intent: Intent
  chart: ChartType
  query: Query
  createdAt: string
}

const key = (id: string) => `awdax.answers.${id}`

/** Stores a first question before its page opens (a new upload that came with a question). */
export function seedAnswer(instanceKey: string, a: Omit<SavedAnswer, 'id' | 'createdAt'>) {
  try {
    const item: SavedAnswer = { ...a, id: `q${Date.now().toString(36)}`, createdAt: new Date().toISOString() }
    localStorage.setItem(key(instanceKey), JSON.stringify([item]))
  } catch {
    // storage blocked: the question just isn't pre-answered
  }
}

function load(id: string): SavedAnswer[] {
  try {
    const v = JSON.parse(localStorage.getItem(key(id)) ?? '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

export function useAnswers(instanceId: string) {
  const [items, setItems] = useState<SavedAnswer[]>(() => load(instanceId))

  useEffect(() => {
    try {
      localStorage.setItem(key(instanceId), JSON.stringify(items))
    } catch {
      // storage full or blocked
    }
  }, [instanceId, items])

  const add = useCallback((a: Omit<SavedAnswer, 'id' | 'createdAt'>) => {
    const item = { ...a, id: `q${Date.now().toString(36)}`, createdAt: new Date().toISOString() }
    setItems((prev) => [...prev, item])
    return item.id
  }, [])
  const remove = useCallback((id: string) => setItems((prev) => prev.filter((x) => x.id !== id)), [])

  return { items, add, remove }
}
