import { useCallback, useEffect, useState } from 'react'
import { awdax } from '../../api/awdax.ts'
import { apiDate, timeAgo } from '../../api/dates.ts'
import { Button } from '../../ui/Button.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { CodeBlock } from './CodeBlock.tsx'
import { scopeLabel } from './snippets.ts'
import type { ApiKeyInfo, CreatedApiKey } from './snippets.ts'

const chip = (on: boolean) =>
  `rounded-control border-2 px-2.5 py-1 text-small transition-colors duration-300 ease-soft ${on ? 'border-ink bg-ink text-on-ink' : 'border-line hover:border-ink'}`

/**
 * This account's API keys: make one (its secret is shown once), see when each was last used, revoke one.
 * `onCreated` hands the new key up so the snippets beside it can show it.
 */
export function KeysPanel({ onCreated }: { onCreated: (key: string | null) => void }) {
  const { toast } = useToast()
  const [keys, setKeys] = useState<ApiKeyInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [write, setWrite] = useState(false)
  const [busy, setBusy] = useState(false)
  const [fresh, setFresh] = useState<CreatedApiKey | null>(null)

  const load = useCallback(async () => {
    try {
      setKeys(await awdax.listApiKeys())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load your keys')
    }
  }, [])
  useEffect(() => {
    const t = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(t)
  }, [load])

  const create = async () => {
    setBusy(true)
    try {
      const made = await awdax.createApiKey({ name: name.trim(), scopes: write ? ['read', 'write'] : ['read'] })
      setFresh(made)
      onCreated(made.key)
      setName('')
      await load()
    } catch (err) {
      toast({ title: 'Couldn’t create the key', description: err instanceof Error ? err.message : String(err), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (key: ApiKeyInfo) => {
    if (!window.confirm(`Revoke “${key.name}”? Anything using it stops working at once.`)) return
    try {
      await awdax.revokeApiKey(key.id)
      if (fresh?.id === key.id) {
        setFresh(null)
        onCreated(null)
      }
      await load()
    } catch (err) {
      toast({ title: 'Couldn’t revoke the key', description: err instanceof Error ? err.message : String(err), tone: 'error' })
    }
  }

  return (
    <section aria-labelledby="keys-h" className="mt-8">
      <h2 id="keys-h" className="font-display text-h3 font-extrabold">API keys</h2>
      <p className="mt-1 max-w-prose text-small text-ink-2">
        A key lets a script, or Claude, work as you without signing in. It sees only your chats. Keep it secret, like a password.
      </p>

      {fresh && (
        <div role="status" className="mt-4 rounded-control border-2 border-ink bg-signal-soft p-4">
          <p className="font-medium">Your new key. Copy it now: it is not shown again.</p>
          <div className="mt-2">
            <CodeBlock code={fresh.key} label="your new API key" />
          </div>
          <Button variant="secondary" className="mt-3" onClick={() => setFresh(null)}>I have saved it</Button>
        </div>
      )}

      <form
        className="mt-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <label className="flex min-w-48 flex-1 flex-col gap-1 text-small">
          <span className="text-ink-2">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={60}
            placeholder="e.g. my script, Claude"
            className="h-10 rounded-control border-2 border-line bg-transparent px-2.5 outline-none focus:border-ink"
          />
        </label>
        <fieldset className="flex flex-col gap-1 text-small">
          <legend className="mb-1 text-ink-2">Can</legend>
          <div className="flex gap-1.5">
            <button type="button" aria-pressed={!write} onClick={() => setWrite(false)} className={chip(!write)}>Read only</button>
            <button type="button" aria-pressed={write} onClick={() => setWrite(true)} className={chip(write)}>Read and write</button>
          </div>
        </fieldset>
        <Button type="submit" loading={busy}>Create key</Button>
      </form>

      {error && <p role="alert" className="mt-4 text-small text-ink-2">{error}</p>}
      {keys && keys.length === 0 && !error && <p className="mt-4 text-small text-ink-2">No keys yet.</p>}
      {keys && keys.length > 0 && (
        <ul className="mt-4 divide-y-2 divide-line border-y-2 border-line">
          {keys.map((k) => (
            <li key={k.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{k.name}</p>
                <p className="font-mono text-micro text-ink-3">{k.prefix}… · {scopeLabel(k.scopes)}</p>
              </div>
              <p className="text-small text-ink-2" title={apiDate(k.created_at)?.toLocaleString()}>
                {k.last_used_at ? `Used ${timeAgo(k.last_used_at)}` : 'Never used'}
              </p>
              <Button variant="ghost" onClick={() => void revoke(k)} aria-label={`Revoke ${k.name}`}>Revoke</Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
