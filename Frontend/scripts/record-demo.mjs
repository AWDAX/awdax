// Records one real AWDAX run for the demo replays: every live-stream frame with its time, the run status every
// 3 s, then the final messages, rows, sources and stats. Needs the backend running (local: app.py on :8000).
//
//   node scripts/record-demo.mjs <slug> "<prompt>" [apiBase]
//
// Writes scripts/recordings/<slug>.json. scripts/build-replay.mjs turns that into the app's replay fixture.
import { mkdir, writeFile } from 'node:fs/promises'

const [slug, prompt, base = 'http://127.0.0.1:8000'] = process.argv.slice(2)
if (!slug || !prompt) {
  console.error('usage: node scripts/record-demo.mjs <slug> "<prompt>" [apiBase]')
  process.exit(2)
}
const LIMIT_MS = Number(process.env.RECORD_LIMIT_MS ?? 30 * 60_000)
const DONE = ['succeeded', 'failed', 'cancelled']
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function api(path, init = {}) {
  const res = await fetch(base + path, { ...init, headers: { 'content-type': 'application/json', ...init.headers } })
  if (!res.ok) throw new Error(`${init.method ?? 'GET'} ${path}: ${res.status} ${await res.text()}`)
  return res.status === 204 ? null : res.json()
}

const created = await api('/api/instances', { method: 'POST', body: JSON.stringify({ title: prompt.slice(0, 80) }) })
const id = created.id
const t0 = Date.now()
const frames = []
const ctrl = new AbortController()

// The same server-sent events the app listens to, kept verbatim with their time since the start.
const stream = (async () => {
  const res = await fetch(`${base}/api/instances/${id}/live/stream`, { signal: ctrl.signal })
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) return
    buf += value
    for (let cut = buf.indexOf('\n\n'); cut >= 0; cut = buf.indexOf('\n\n')) {
      const block = buf.slice(0, cut)
      buf = buf.slice(cut + 2)
      let event = 'message'
      const data = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (!data.length) continue
      try {
        frames.push({ t: Date.now() - t0, event, data: JSON.parse(data.join('\n')) })
      } catch {
        // a frame that isn't JSON is skipped, like the app does
      }
    }
  }
})().catch((err) => {
  if (!ctrl.signal.aborted) console.error('stream:', err.message)
})

await sleep(500)
await api(`/api/instances/${id}/messages`, { method: 'POST', body: JSON.stringify({ content: prompt }) })
console.log(`recording ${slug}: instance ${id}`)

let last = ''
let final = null
while (Date.now() - t0 < LIMIT_MS) {
  await sleep(3000)
  const live = await api(`/api/instances/${id}/live`).catch(() => null)
  const run = live?.latest_run
  frames.push({ t: Date.now() - t0, event: 'poll', data: live })
  const line = run ? `${run.phase}/${run.status} rows=${run.rows_total ?? 0} ${run.detail ?? ''}` : 'no run yet'
  if (line !== last) console.log(`${Math.round((Date.now() - t0) / 1000)}s ${line}`)
  last = line
  if (run && DONE.includes(run.status)) {
    final = run
    break
  }
}

// Trailing frames (final scoring, batch_complete) land just after the run says it's done.
await sleep(10_000)
ctrl.abort()
await stream

const [messages, dataset, sources, stats] = await Promise.all([
  api(`/api/instances/${id}/messages`),
  api(`/api/instances/${id}/dataset?limit=5000&include_partial=false`),
  api(`/api/instances/${id}/sources`),
  api(`/api/instances/${id}/dataset/stats`).catch(() => null),
])

const out = {
  slug,
  prompt,
  instanceId: id,
  recordedAt: new Date(t0).toISOString(),
  durationMs: Date.now() - t0,
  outcome: final?.status ?? 'timeout',
  frames,
  final: { run: final, messages, dataset, sources, stats },
}
const dir = new URL('./recordings/', import.meta.url)
await mkdir(dir, { recursive: true })
await writeFile(new URL(`${slug}.json`, dir), JSON.stringify(out, null, 1))
console.log(`saved scripts/recordings/${slug}.json: ${out.outcome}, ${dataset.rows?.length ?? 0} rows, ${frames.length} frames, ${Math.round(out.durationMs / 1000)} s`)
