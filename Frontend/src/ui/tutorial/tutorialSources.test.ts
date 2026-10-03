import assert from 'node:assert/strict'
import test from 'node:test'
import { playableSources } from './tutorialSources.ts'

const MP4 = { src: '/t.mp4', type: 'video/mp4' }
const WEBM = { src: '/t.webm', type: 'video/webm' }

test('keeps the sources the browser may play, in order', () => {
  const both = (t: string) => (t === 'video/mp4' ? 'probably' : 'maybe')
  assert.deepEqual(playableSources([MP4, WEBM], both), [MP4, WEBM])
})

test('drops a format the browser cannot play, so the other one is tried', () => {
  const noH264 = (t: string) => (t === 'video/mp4' ? '' : 'maybe')
  assert.deepEqual(playableSources([MP4, WEBM], noH264), [WEBM])
})

test('nothing playable gives an empty list', () => {
  assert.deepEqual(playableSources([MP4, WEBM], () => ''), [])
})

test('a source without a type is kept: only loading it can tell', () => {
  const override = { src: 'https://cdn.example/tutorial', type: '' }
  assert.deepEqual(playableSources([override], () => ''), [override])
})
