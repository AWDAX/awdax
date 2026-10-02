import assert from 'node:assert/strict'
import { test } from 'node:test'
import { openLiveSocket } from './liveSocket.ts'

const WATCHDOG_MS = 10_000

// Installs fake WebSocket/window/document globals and restores them afterwards.
function withFakes(run: (env: Env) => void) {
  const originalSocket = globalThis.WebSocket
  const originalWindow = globalThis.window
  const originalDocument = globalThis.document
  const originalNow = Date.now
  const env: Env = { now: 1000, sockets: [], timers: new Map(), fallback: 0, states: [] }
  let nextId = 1
  class FakeSocket {
    readyState = 0
    listeners = new Map<string, (() => void)[]>()
    constructor(url: string) { assert.equal(url, 'ws://example.test/live'); env.sockets.push(this) }
    addEventListener(type: string, listener: () => void) {
      this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
    }
    emit(type: string) {
      if (type === 'open') this.readyState = 1
      this.listeners.get(type)?.forEach((listener) => listener())
    }
    close() { this.readyState = 3; this.emit('close') }
  }
  try {
    Date.now = () => env.now
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket
    globalThis.window = {
      setTimeout: (fn: () => void, delay: number) => { const id = nextId++; env.timers.set(id, { fn, delay }); return id },
      clearTimeout: (id: number) => { env.timers.delete(id) },
    } as unknown as Window & typeof globalThis
    globalThis.document = { addEventListener: () => {}, removeEventListener: () => {} } as unknown as Document
    run(env)
  } finally {
    globalThis.WebSocket = originalSocket
    globalThis.window = originalWindow
    globalThis.document = originalDocument
    Date.now = originalNow
  }
}

type FakeSocket = {
  readyState: number
  emit: (type: string) => void
  close: () => void
}
type Env = {
  now: number
  sockets: FakeSocket[]
  timers: Map<number, { fn: () => void; delay: number }>
  fallback: number
  states: string[]
}

const open = (env: Env) => openLiveSocket('ws://example.test/live', {
  onMessage: () => {},
  onConnection: (state) => { env.states.push(state) },
  onFallback: () => { env.fallback++ },
})

const pending = (env: Env, isWatchdog: boolean) =>
  [...env.timers.entries()].filter(([, t]) => (t.delay === WATCHDOG_MS) === isWatchdog)

// Fires the single pending timer of the given kind, removing it first like a real timer.
function fire(env: Env, isWatchdog: boolean) {
  const [entry] = pending(env, isWatchdog)
  assert.ok(entry, 'expected a pending timer')
  env.timers.delete(entry[0])
  entry[1].fn()
}

test('two repeatedly aborted socket connections fall back to events', () => {
  withFakes((env) => {
    const stop = open(env)
    env.sockets[0].emit('open')
    env.now += 14_000
    env.sockets[0].emit('close')
    assert.equal(env.fallback, 0)
    fire(env, false)
    env.sockets[1].emit('open')
    env.now += 14_000
    env.sockets[1].emit('close')
    assert.equal(env.fallback, 1)
    assert.equal(env.timers.size, 0)
    stop()
  })
})

test('a socket stuck connecting is closed by the watchdog and falls back after two hangs', () => {
  withFakes((env) => {
    const stop = open(env)
    fire(env, true)
    assert.equal(env.sockets[0].readyState, 3)
    assert.deepEqual(env.states, ['reconnecting'])
    assert.equal(env.fallback, 0)
    assert.equal(pending(env, false).length, 1)
    fire(env, false)
    assert.equal(env.sockets.length, 2)
    fire(env, true)
    assert.equal(env.fallback, 1)
    assert.equal(env.timers.size, 0)
    stop()
  })
})

test('a socket that opens in time clears the watchdog and stays open', () => {
  withFakes((env) => {
    const stop = open(env)
    assert.equal(pending(env, true).length, 1)
    env.sockets[0].emit('open')
    assert.equal(pending(env, true).length, 0)
    assert.equal(env.sockets[0].readyState, 1)
    stop()
  })
})

test('stopping while connecting clears the watchdog without falling back', () => {
  withFakes((env) => {
    const stop = open(env)
    stop()
    assert.equal(env.timers.size, 0)
    assert.equal(env.fallback, 0)
  })
})
