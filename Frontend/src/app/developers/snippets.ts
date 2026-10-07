/**
 * What the Developers page shows: the copy-paste snippets for a key, and the API's operations grouped for reading.
 * Pure (no browser, no network), so Node tests can run it.
 */

export type ApiKeyInfo = {
  id: string
  name: string
  prefix: string
  scopes: string[]
  created_at: string
  last_used_at: string | null
}

export type CreatedApiKey = ApiKeyInfo & { key: string }

export type Operation = { method: string; path: string; summary: string; tag: string; description: string }

type Spec = { paths?: Record<string, Record<string, { summary?: string; tags?: string[]; description?: string }>>; tags?: { name: string }[] }

const METHODS = ['get', 'post', 'patch', 'put', 'delete']
const METHOD_ORDER = new Map(METHODS.map((m, i) => [m, i]))

/** Every operation in the OpenAPI document, in reading order: its tags as the document lists them, then by path. */
export function operationsOf(spec: Spec): Operation[] {
  const tagOrder = new Map((spec.tags ?? []).map((t, i) => [t.name, i]))
  const out: Operation[] = []
  for (const [path, ops] of Object.entries(spec.paths ?? {})) {
    for (const [method, op] of Object.entries(ops)) {
      if (!METHOD_ORDER.has(method)) continue
      out.push({ method: method.toUpperCase(), path, summary: op.summary ?? '', tag: op.tags?.[0] ?? 'Other', description: op.description ?? '' })
    }
  }
  return out.sort(
    (a, b) =>
      (tagOrder.get(a.tag) ?? 99) - (tagOrder.get(b.tag) ?? 99) ||
      a.path.localeCompare(b.path) ||
      (METHOD_ORDER.get(a.method.toLowerCase()) ?? 0) - (METHOD_ORDER.get(b.method.toLowerCase()) ?? 0),
  )
}

export function groupByTag(ops: Operation[]): [string, Operation[]][] {
  const groups = new Map<string, Operation[]>()
  for (const op of ops) groups.set(op.tag, [...(groups.get(op.tag) ?? []), op])
  return [...groups]
}

const trimmed = (origin: string) => origin.replace(/\/+$/, '')
export const PLACEHOLDER_KEY = 'awx_YOUR_KEY'

export function curlSnippet(origin: string, key = PLACEHOLDER_KEY): string {
  return `curl ${trimmed(origin)}/api/instances \\\n  -H "Authorization: Bearer ${key}"`
}

/** Start a research run and read the table back: three calls. */
export function researchSnippet(origin: string, key = PLACEHOLDER_KEY): string {
  const base = trimmed(origin)
  return [
    `AUTH="Authorization: Bearer ${key}"`,
    `ID=$(curl -s -X POST ${base}/api/instances -H "$AUTH" -H "Content-Type: application/json" -d '{}' | jq -r .id)`,
    `curl -s -X POST ${base}/api/instances/$ID/messages -H "$AUTH" -H "Content-Type: application/json" \\`,
    `  -d '{"content": "cafes in Pune with phone numbers"}'`,
    `curl -s ${base}/api/instances/$ID/live -H "$AUTH"      # poll until latest_run.status is "succeeded"`,
    `curl -s ${base}/api/instances/$ID/dataset -H "$AUTH"`,
  ].join('\n')
}

export function claudeCodeCommand(origin: string, key = PLACEHOLDER_KEY): string {
  return `claude mcp add --transport http awdax ${trimmed(origin)}/api/mcp --header "Authorization: Bearer ${key}"`
}

/** claude_desktop_config.json for Claude Desktop, through the mcp-remote bridge. */
export function claudeDesktopConfig(origin: string, key = PLACEHOLDER_KEY): string {
  return JSON.stringify(
    {
      mcpServers: {
        awdax: {
          command: 'npx',
          args: ['-y', 'mcp-remote', `${trimmed(origin)}/api/mcp`, '--header', `Authorization: Bearer ${key}`],
        },
      },
    },
    null,
    2,
  )
}

export const scopeLabel = (scopes: string[]) => (scopes.includes('write') ? 'Read and write' : 'Read only')
