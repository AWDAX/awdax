import { useCallback, useEffect, useState } from 'react'
import type { TableProfile } from '../../analytics/profile.ts'
import { columnSignature } from '../../analytics/signature.ts'
import { newAnswer, parseAnswers } from './answerStore.ts'
import type { NewAnswer, SavedAnswer } from './answerStore.ts'

export type { SavedAnswer } from './answerStore.ts'

const key = (id: string) => `awdax.answers.${id}`

/** Stores a first question before its page opens (a new upload that came with a question). */
export function seedAnswer(instanceKey: string, a: NewAnswer, profile: TableProfile) {
  try {
    localStorage.setItem(key(instanceKey), JSON.stringify([newAnswer(a, columnSignature(profile))]))
  } catch {
    // storage blocked: the question just isn't pre-answered
  }
}

function load(id: string): SavedAnswer[] {
  try {
    return parseAnswers(localStorage.getItem(key(id)))
  } catch {
    return []
  }
}

export function useAnswers(instanceId: string, profile: TableProfile) {
  const [items, setItems] = useState<SavedAnswer[]>(() => load(instanceId))
  const signature = columnSignature(profile)

  useEffect(() => {
    try {
      localStorage.setItem(key(instanceId), JSON.stringify(items))
    } catch {
      // storage full or blocked
    }
  }, [instanceId, items])

  const add = useCallback(
    (a: NewAnswer) => {
      const item = newAnswer(a, signature)
      setItems((prev) => [...prev, item])
      return item.id
    },
    [signature],
  )
  const remove = useCallback((id: string) => setItems((prev) => prev.filter((x) => x.id !== id)), [])

  return { items, add, remove }
}
