import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSseSupervisor, type SseLike } from './sseSupervisor.ts'

class FakeSource implements SseLike {
  readyState = 0
  closed = 0
  listeners = new Map<string, (() => void)[]>()
  addEventListener(type: 'open' | 'error', listener: () => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }
  close() { this.closed++; this.readyState = 2 }
  emit(type: 'open' | 'error', readyState: number) {
    this.readyState = readyState
    this.listeners.get(type)?.forEach((listener) => listener())
  }
}

function setup(options: { random?: () => number; maxMs?: number } = {}) {
  const sources: FakeSource[] = []
  const timers = new Map<number, { fn: () => void; ms: number }>()
  const errors = { count: 0 }
  let nextId = 1
  const supervisor = createSseSupervisor({
    open: () => { const source = new FakeSource(); sources.push(source); return source },
    schedule: (fn, ms) => { timers.set(nextId, { fn, ms }); return nextId++ },
    cancel: (handle) => { timers.delete(handle) },
    random: () => 0,
    onError: () => { errors.count++ },
    ...options,
  })
  // Fires the one pending reopen, removing it first as a browser would.
  const fire = () => {
    assert.equal(timers.size, 1)
    const [[id, timer]] = [...timers]
    timers.delete(id)
    timer.fn()
    return timer.ms
  }
  const last = () => sources[sources.length - 1]
  return { supervisor, sources, timers, errors, fire, last }
}

test('a closed stream is reopened after 1 s, 2 s, 4 s', () => {
  const { supervisor, sources, timers, fire, last } = setup()
  supervisor.start()
  last().emit('error', 2)
  assert.equal(sources[0].closed, 1)
  assert.deepEqual([...timers.values()].map((timer) => timer.ms), [1000])
  assert.equal(fire(), 1000)
  assert.equal(sources.length, 2)
  last().emit('error', 2)
  assert.equal(fire(), 2000)
  last().emit('error', 2)
  assert.equal(fire(), 4000)
  assert.equal(sources.length, 4)
  supervisor.stop()
})

test('the delay is capped at maxMs, jitter included', () => {
  const { supervisor, fire, last } = setup({ maxMs: 5000, random: () => 0.999 })
  supervisor.start()
  const delays: number[] = []
  for (let i = 0; i < 6; i++) {
    last().emit('error', 2)
    delays.push(fire())
  }
  assert.ok(delays[0] >= 1000 && delays[0] < 1250)
  assert.ok(delays[1] >= 2000 && delays[1] < 2250)
  assert.deepEqual(delays.slice(3), [5000, 5000, 5000])
  supervisor.stop()
})

test('the default cap is 30 s', () => {
  const { supervisor, fire, last } = setup()
  supervisor.start()
  const delays: number[] = []
  for (let i = 0; i < 8; i++) {
    last().emit('error', 2)
    delays.push(fire())
  }
  assert.deepEqual(delays, [1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000])
  supervisor.stop()
})

test('an open event resets the backoff', () => {
  const { supervisor, fire, last } = setup()
  supervisor.start()
  last().emit('error', 2)
  fire()
  last().emit('error', 2)
  assert.equal(fire(), 2000)
  last().emit('open', 1)
  last().emit('error', 2)
  assert.equal(fire(), 1000)
  supervisor.stop()
})

test('an error while the browser is reconnecting schedules nothing', () => {
  const { supervisor, sources, timers, errors, last } = setup()
  supervisor.start()
  last().emit('open', 1)
  last().emit('error', 0)
  assert.equal(timers.size, 0)
  assert.equal(sources.length, 1)
  assert.equal(sources[0].closed, 0)
  assert.equal(supervisor.isOpen(), false)
  assert.equal(errors.count, 1)
  last().emit('open', 1)
  assert.equal(supervisor.isOpen(), true)
  supervisor.stop()
})

test('stop() during a pending reopen cancels it and never opens again', () => {
  const { supervisor, sources, timers, last } = setup()
  supervisor.start()
  last().emit('error', 2)
  assert.equal(timers.size, 1)
  supervisor.stop()
  assert.equal(timers.size, 0)
  assert.equal(sources.length, 1)
  assert.equal(supervisor.isOpen(), false)
})

test('stop() closes the live source and ignores its late events', () => {
  const { supervisor, sources, timers, errors } = setup()
  supervisor.start()
  sources[0].emit('open', 1)
  assert.equal(supervisor.isOpen(), true)
  supervisor.stop()
  assert.equal(sources[0].closed, 1)
  assert.equal(supervisor.isOpen(), false)
  sources[0].emit('error', 2)
  assert.equal(timers.size, 0)
  assert.equal(errors.count, 0)
})

test('start() twice opens one source, also while a reopen is pending', () => {
  const { supervisor, sources, last } = setup()
  supervisor.start()
  supervisor.start()
  assert.equal(sources.length, 1)
  last().emit('error', 2)
  supervisor.start()
  assert.equal(sources.length, 1)
  supervisor.stop()
})

test('isOpen() follows the source state', () => {
  const { supervisor, last } = setup()
  assert.equal(supervisor.isOpen(), false)
  supervisor.start()
  assert.equal(supervisor.isOpen(), false)
  last().emit('open', 1)
  assert.equal(supervisor.isOpen(), true)
  last().emit('error', 2)
  assert.equal(supervisor.isOpen(), false)
  supervisor.stop()
})
