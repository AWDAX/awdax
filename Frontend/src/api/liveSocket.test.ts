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
