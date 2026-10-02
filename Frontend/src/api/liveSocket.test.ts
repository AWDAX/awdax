import assert from 'node:assert/strict'
import { test } from 'node:test'
import { openLiveSocket } from './liveSocket.ts'

test('two repeatedly aborted socket connections fall back to events', () => {
  const originalSocket = globalThis.WebSocket
  const originalWindow = globalThis.window
  const originalDocument = globalThis.document
  const originalNow = Date.now
  let now = 1000
  const sockets: FakeSocket[] = []
  let scheduled: (() => void) | undefined
  let fallback = 0
  class FakeSocket {
    listeners = new Map<string, (() => void)[]>()
    constructor(url: string) { assert.equal(url, 'ws://example.test/live'); sockets.push(this) }
    addEventListener(type: string, listener: () => void) {
      this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
    }
    emit(type: string) { this.listeners.get(type)?.forEach((listener) => listener()) }
    close() { this.emit('close') }
  }
  try {
    Date.now = () => now
    globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket
    globalThis.window = { setTimeout: (fn: () => void) => { scheduled = fn; return 1 }, clearTimeout: () => { scheduled = undefined } } as unknown as Window & typeof globalThis
    globalThis.document = { addEventListener: () => {}, removeEventListener: () => {} } as unknown as Document
    const stop = openLiveSocket('ws://example.test/live', {
      onMessage: () => {}, onConnection: () => {}, onFallback: () => { fallback++ },
    })
    sockets[0].emit('open')
    now += 14_000
    sockets[0].emit('close')
    assert.equal(fallback, 0)
    const reconnect = scheduled
    scheduled = undefined
    reconnect?.()
    sockets[1].emit('open')
    now += 14_000
    sockets[1].emit('close')
    assert.equal(fallback, 1)
    assert.equal(scheduled, undefined)
    stop()
  } finally {
    globalThis.WebSocket = originalSocket
    globalThis.window = originalWindow
    globalThis.document = originalDocument
    Date.now = originalNow
  }
})

// The watchdog tests need a socket with a readyState and a window whose timers can be listed and fired;
// the test above only remembers the last timer set.
const LIVE_URL = 'ws://example.test/live'

type Timer = { fn: () => void; ms: number }

function fakeBrowser() {
  const originalSocket = globalThis.WebSocket
  const originalWindow = globalThis.window
  const originalDocument = globalThis.document
  const sockets: FakeSocket[] = []
  const timers = new Map<number, Timer>()
  const states: string[] = []
  let nextId = 1
  let fallbacks = 0
  class FakeSocket {
    static CONNECTING = 0
    listeners = new Map<string, (() => void)[]>()
    readyState = 0
    closed = 0
    constructor(url: string) { assert.equal(url, LIVE_URL); sockets.push(this) }
    addEventListener(type: string, listener: () => void) {
      this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
    }
    emit(type: string) {
      if (type === 'open') this.readyState = 1
      this.listeners.get(type)?.forEach((listener) => listener())
    }
    close() { this.closed++; this.readyState = 3; this.emit('close') }
  }
  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket
  globalThis.window = {
    setTimeout: (fn: () => void, ms: number) => { timers.set(nextId, { fn, ms }); return nextId++ },
    clearTimeout: (id: number) => { timers.delete(id) },
  } as unknown as Window & typeof globalThis
  globalThis.document = { addEventListener: () => {}, removeEventListener: () => {} } as unknown as Document
  return {
    sockets,
    timers,
    states,
    get fallbacks() { return fallbacks },
    start: () => openLiveSocket(LIVE_URL, {
      onMessage: () => {}, onConnection: (state) => { states.push(state) }, onFallback: () => { fallbacks++ },
    }),
    pending: (ms: number) => [...timers.values()].filter((timer) => timer.ms === ms).length,
    // Fires the one pending timer (the one of `ms`, when given), removing it first as a browser does.
    run: (ms?: number) => {
      const due = [...timers].filter(([, timer]) => ms === undefined || timer.ms === ms)
      assert.equal(due.length, 1)
      const [[id, timer]] = due
      timers.delete(id)
      timer.fn()
    },
    restore: () => {
      globalThis.WebSocket = originalSocket
      globalThis.window = originalWindow
      globalThis.document = originalDocument
    },
  }
}

test('a handshake that never opens is closed after 10 s and counts toward the fallback', () => {
  const browser = fakeBrowser()
  try {
    const stop = browser.start()
    browser.run(10_000)
    assert.equal(browser.sockets[0].closed, 1)
    assert.deepEqual(browser.states, ['reconnecting'])
    assert.equal(browser.fallbacks, 0)
    browser.run()
    assert.equal(browser.sockets.length, 2)
    browser.run(10_000)
    assert.equal(browser.sockets[1].closed, 1)
    assert.equal(browser.fallbacks, 1)
    assert.equal(browser.sockets.length, 2)
    assert.equal(browser.timers.size, 0)
    stop()
  } finally {
    browser.restore()
  }
})

test('an opened socket is not closed by the watchdog', () => {
  const browser = fakeBrowser()
  try {
    const stop = browser.start()
    assert.equal(browser.pending(10_000), 1)
    const [watchdog] = browser.timers.values()
    browser.sockets[0].emit('open')
    assert.equal(browser.pending(10_000), 0)
    // A firing that slipped past the clear must still leave an open socket alone.
    watchdog.fn()
    assert.equal(browser.sockets[0].closed, 0)
    stop()
  } finally {
    browser.restore()
  }
})

test('stop() clears every timer', () => {
  const browser = fakeBrowser()
  try {
    const stop = browser.start()
    assert.equal(browser.pending(10_000), 1)
    const socket = browser.sockets[0]
    // A browser fires `close` only after close() returns, so stop() must not rely on that event to clear the watchdog.
    socket.close = () => { socket.closed++ }
    stop()
    assert.equal(browser.timers.size, 0)
    assert.equal(socket.closed, 1)
    socket.emit('close')
    assert.equal(browser.timers.size, 0)
    assert.deepEqual(browser.states, [])
  } finally {
    browser.restore()
  }
})

test('a handshake that fails by itself clears the watchdog', () => {
  const browser = fakeBrowser()
  try {
    const stop = browser.start()
    browser.sockets[0].emit('close')
    assert.equal(browser.pending(10_000), 0)
    browser.run()
    assert.equal(browser.pending(10_000), 1)
    stop()
    assert.equal(browser.timers.size, 0)
  } finally {
    browser.restore()
  }
})
