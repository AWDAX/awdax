import { parseQuestion } from '../../analytics/ask.ts'
import { profileTable } from '../../analytics/profile.ts'
import { newLocalId, saveLocal } from '../files/localProjects.ts'
import { readDataFile } from '../files/readFile.ts'
import { seedAnswer } from './useAnswers.ts'

/**
 * A new chat from an uploaded file: read it, keep it in this browser, and pre-answer the question typed
 * with it (if the question can be read). Returns the new project's id, or the reason it couldn't be read.
 */
export async function startFromFile(file: File, question: string): Promise<{ id: string } | { error: string }> {
  const read = await readDataFile(file)
  if (!read.ok) return { error: read.reason }
  if (read.table.rows.length === 0) return { error: `${file.name} has a header but no rows.` }
  const id = newLocalId()
  const now = new Date().toISOString()
  await saveLocal({
    id,
    title: question || file.name.replace(/\.[^.]+$/, ''),
    fileName: file.name,
    fileSize: file.size,
    created_at: now,
    updated_at: now,
    table: read.table,
    note: read.note,
  })
  if (question) {
    const profile = profileTable(read.table)
    const parsed = parseQuestion(profile, question)
    if (parsed.ok) seedAnswer(`file-${id}`, { question, intent: parsed.intent, chart: parsed.chart, query: parsed.query }, profile)
  }
  return { id }
}
