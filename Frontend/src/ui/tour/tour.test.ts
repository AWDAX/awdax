import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { TOURS, getTour } from './tourRegistry.ts'

describe('Tour Registry & Step Integrity', () => {
  it('registers all required core tours', () => {
    const required = ['landing-tour', 'new-chat-tour', 'chat-view-tour', 'projects-tour', 'sidebar-tour']
    for (const id of required) {
      const tour = getTour(id)
      assert.ok(tour, `Tour '${id}' must exist in the registry`)
      assert.equal(tour.id, id)
      assert.ok(tour.title.length > 0, `Tour '${id}' must have a non-empty title`)
      assert.ok(tour.steps.length > 0, `Tour '${id}' must have at least one step`)
    }
  })

  it('ensures each tour step has valid properties and selectors', () => {
    for (const [tourId, tour] of Object.entries(TOURS)) {
      const stepIds = new Set<string>()
      for (const step of tour.steps) {
        assert.ok(step.id, `Step in tour '${tourId}' missing ID`)
        assert.ok(!stepIds.has(step.id), `Duplicate step ID '${step.id}' in tour '${tourId}'`)
        stepIds.add(step.id)

        assert.ok(step.target.length > 0, `Step '${step.id}' in tour '${tourId}' missing target selector`)
        assert.ok(step.title.length > 0, `Step '${step.id}' in tour '${tourId}' missing title`)
        assert.ok(step.content.length > 0, `Step '${step.id}' in tour '${tourId}' missing content`)
      }
    }
  })

  it('supports finding existing and non-existing tours gracefully', () => {
    assert.ok(getTour('landing-tour'))
    assert.equal(getTour('non-existent-tour'), undefined)
  })

  it('contains comprehensive feature tour coverage across key platform pages', () => {
    const landing = getTour('landing-tour')
    assert.ok(landing)
    assert.ok(landing.steps.some((s) => s.target.includes('landing-hero')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-liverun')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-how')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-plan')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-receipts')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-clean')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-dashboards')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-sources')))
    assert.ok(landing.steps.some((s) => s.target.includes('landing-faq')))

    const newChat = getTour('new-chat-tour')
    assert.ok(newChat)
    assert.ok(newChat.steps.some((s) => s.target.includes('new-chat-prompt')))
    assert.ok(newChat.steps.some((s) => s.target.includes('new-chat-shortcuts')))
    assert.ok(newChat.steps.some((s) => s.target.includes('new-chat-cards')))

    const projects = getTour('projects-tour')
    assert.ok(projects)
    assert.ok(projects.steps.some((s) => s.target.includes('projects-kpis')))
    assert.ok(projects.steps.some((s) => s.target.includes('projects-table')))
  })
})
