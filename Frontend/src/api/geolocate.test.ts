import assert from 'node:assert/strict'
import { test } from 'node:test'
import { currentPosition, wantsMyLocation } from './geolocate.ts'

test('only a request about the person’s surroundings asks for their position', () => {
  for (const yes of ['cafes near me', 'Nearby pharmacies', 'dentists around me', 'gyms close to me', 'shops in my area', 'clinics near by']) {
    assert.equal(wantsMyLocation(yes), true, yes)
  }
  for (const no of ['list all local business leads in delhi ncr for web development', 'EV prices in India', 'gazette notifications', 'nearly new cars']) {
    assert.equal(wantsMyLocation(no), false, no)
  }
})

test('no geolocation support is simply no position', async () => {
  assert.equal(await currentPosition(), null)
})

test('a position is rounded and a refusal is no position', async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  const fake = (call: (ok: (p: unknown) => void, fail: () => void) => void) =>
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { geolocation: { getCurrentPosition: call } } })
  try {
    fake((ok) => ok({ coords: { latitude: 28.613939, longitude: 77.209021 } }))
    assert.deepEqual(await currentPosition(), { lat: 28.614, lng: 77.209 })
    fake((_ok, fail) => fail())
    assert.equal(await currentPosition(), null)
  } finally {
    if (original) Object.defineProperty(globalThis, 'navigator', original)
    else Reflect.deleteProperty(globalThis, 'navigator')
  }
})
