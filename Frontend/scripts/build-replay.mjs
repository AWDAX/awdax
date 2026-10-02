// Turns a raw recording (scripts/recordings/<slug>.json, from record-demo.mjs) into the replay the app plays:
// public/demo/<slug>.json, in the Recording shape of src/app/demo/replay.ts.
//
//   node scripts/build-replay.mjs <slug> ["Title shown in the replay"]
import { mkdir, readFile, writeFile } from 'node:fs/promises'

const [slug, title] = process.argv.slice(2)
if (!slug) {
  console.error('usage: node scripts/build-replay.mjs <slug> ["title"]')
  process.exit(2)
}
const raw = JSON.parse(await readFile(new URL(`./recordings/${slug}.json`, import.meta.url), 'utf8'))
const start = Date.parse(raw.recordedAt)

// A live track can keep re-checking past the recorder's limit without ever saying "complete". Its first
// "Live — next check in…" with rows is the moment the first pass was done and up to date: end the replay there.
if (raw.outcome !== 'succeeded') {
  const cut = raw.frames.find((f) => (f.event === 'status' || f.event === 'poll') && f.data?.latest_run?.phase === 'live' && f.data.rows_total > 0)
  if (!cut) {
    console.error(`this run ended "${raw.outcome}" and never finished a first pass with rows: not building a replay`)
    process.exit(1)
  }
  raw.frames = raw.frames.filter((f) => f.t <= cut.t)
  console.warn(`note: run ended "${raw.outcome}"; replay ends at its first up-to-date state, ${Math.round(cut.t / 1000)} s in, ${cut.data.rows_total} rows`)
}

const steps = []
let lastStatus = ''
const seenEvents = new Set()
for (const f of raw.frames) {
  const d = f.data
  // Frames from before the run existed (the stream's first hello) would read "Tracking paused": skip them.
  if ((f.event === 'status' || f.event === 'poll') && d?.latest_run) {
    // The stream and the 3 s poll repeat the same state; keep each change once.
    const r = d.latest_run
    const key = JSON.stringify([d.enabled, d.rows_total, r?.phase, r?.status, r?.detail, r?.rows_total])
    if (key !== lastStatus) steps.push({ t: f.t, kind: 'status', state: d })
    lastStatus = key
  } else if (f.event === 'run_event' && d?.phase && !seenEvents.has(d.id)) {
    seenEvents.add(d.id)
    steps.push({ t: f.t, kind: 'event', event: d })
  } else if (f.event === 'source' && d?.url) {
    steps.push({ t: f.t, kind: 'source', source: d })
  }
}

// Messages land when the backend wrote them; system notes are not shown in the app, nor anything after a cut.
const limitT = raw.outcome === 'succeeded' ? Infinity : (raw.frames.at(-1)?.t ?? 0)
raw.final.messages
  .filter((m) => m.role !== 'system' && Date.parse(m.created_at) - start <= limitT)
  .forEach((m, i) => {
    const t = Math.max(0, Date.parse(m.created_at) - start)
    steps.push({ t, kind: 'message', message: { id: i + 1, role: m.role === 'user' ? 'user' : 'bot', text: m.content, created_at: m.created_at } })
  })

steps.sort((a, b) => a.t - b.t)
const end = steps.at(-1)?.t ?? 0
steps.push({ t: end, kind: 'done' })

const { dataset, sources, stats } = raw.final
const out = {
  slug,
  prompt: raw.prompt,
  title: title ?? raw.prompt,
  recordedAt: raw.recordedAt,
  durationMs: end,
  steps,
  final: {
    dataset: { columns: dataset.columns ?? [], rows: dataset.rows ?? [], row_count: dataset.row_count ?? dataset.rows?.length ?? 0, records: dataset.records ?? [] },
    sources: sources.sources ?? [],
    stats,
  },
}
const dir = new URL('../public/demo/', import.meta.url)
await mkdir(dir, { recursive: true })
const json = JSON.stringify(out)
await writeFile(new URL(`${slug}.json`, dir), json)
const kinds = Object.groupBy(steps, (s) => s.kind)
console.log(
  `public/demo/${slug}.json: ${(json.length / 1024).toFixed(0)} KB, ${out.final.dataset.rows.length} rows, real run ${Math.round(end / 1000)} s, ` +
    Object.entries(kinds).map(([k, v]) => `${v.length} ${k}`).join(', '),
)
