import { awdax } from '../../api/awdax.ts'
import type { DatasetTable } from '../../api/types.ts'
import { getLocal } from '../files/localProjects.ts'

/** Pauses or resumes a web project; PATCH /live answers with the new status, so no read-back is needed. */
export function setLiveAndSnapshot(id: string, enabled: boolean) {
  return awdax.setLive(id, enabled)
}

/** A project's table: from the backend's dashboard endpoint for a web request, from this browser for a file. */
export async function loadTable(kind: 'web' | 'file', id: string): Promise<DatasetTable | null> {
  if (kind === 'file') return (await getLocal(id))?.table ?? null
  return (await awdax.getDashboard(id)).table
}
