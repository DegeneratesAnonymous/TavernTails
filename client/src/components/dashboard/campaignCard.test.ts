import { MAX_POLL_ERRORS, afterPoll, buildCreatePayload, editField, groupFields, openFieldsWithoutFollowUps, worldInProgress, type CampaignCard } from './campaignCard'

function card(): CampaignCard {
  return {
    fields: {
      name: { value: '', status: 'open' },
      premise: { value: 'A harbor town where the keeper vanished.', status: 'said' },
      tone: { value: 'grim', status: 'guessed' },
      starting_place: { value: '', status: 'open' },
      world_name: { value: '', status: 'open' },
    },
    people: [],
    factions: [],
    themes: [],
    content_limits: [],
    open_questions: [],
    follow_ups: [{ id: 'starting_place', field: 'starting_place', question: 'Where does the story open?', placeholder: '' }],
    derived: { canon_policy: 'guided_canon', ai_creativity_level: 'balanced', creation_posture: 'player_fast_start' },
    diagnostics: { source: 'model' },
    text: 'A harbor town where the keeper vanished.',
    has_lore: false,
    starter: {},
  }
}

test('an edited field becomes the player\'s words; clearing it leaves it open', () => {
  const edited = editField(card(), 'tone', 'cozy')
  expect(edited.fields.tone).toEqual({ value: 'cozy', status: 'said' })
  expect(editField(edited, 'tone', '').fields.tone).toEqual({ value: '', status: 'open' })
})

test('fields are grouped by the status they arrived with, and follow-ups are not listed twice', () => {
  const groups = groupFields(card(), ['name', 'premise', 'tone', 'starting_place', 'world_name'])
  expect(groups).toEqual({ said: ['premise'], guessed: ['tone'], open: ['name', 'starting_place', 'world_name'] })
  expect(openFieldsWithoutFollowUps(card(), groups.open)).toEqual(['name', 'world_name'])
})

test('the create payload fills a missing name and drops blank answers', () => {
  const payload = buildCreatePayload({
    card: card(),
    answers: { starting_place: '  the Gull Steps ', opening_trouble: '   ' },
    fallbackName: 'The Last Lantern',
    visibility: 'show',
    generateWorld: true,
    lore: '',
    owner: { owner_role: 'dm', owner_character_id: null },
  })
  expect(payload.name).toBe('The Last Lantern')
  expect(payload.card.fields.name).toEqual({ value: 'The Last Lantern', status: 'guessed' })
  expect(payload.follow_up_answers).toEqual({ starting_place: 'the Gull Steps' })
  expect(payload.world_visibility).toBe('show')
  expect(payload.imported_lore_summary).toBeNull()
  expect(payload.owner_role).toBe('dm')
})

test('only pending and running worlds are polled', () => {
  const base = { visibility: 'surprise' as const, pieces: {} as never }
  expect(worldInProgress({ ...base, status: 'running' })).toBe(true)
  expect(worldInProgress({ ...base, status: 'interrupted' })).toBe(false)
  expect(worldInProgress(null)).toBe(false)
})

test('a dropped poll keeps the last world and keeps polling; 403/404 stop', () => {
  const building = { status: 'running' as const, visibility: 'surprise' as const, pieces: {} as never }
  const error = afterPoll({ kind: 'error' }, building, 0)
  expect(error).toEqual({ world: building, again: true, errorsInARow: 1 })
  expect(afterPoll({ kind: 'error' }, null, 0).again).toBe(true)
  expect(afterPoll({ kind: 'error' }, building, MAX_POLL_ERRORS - 1).again).toBe(false)
  expect(afterPoll({ kind: 'gone' }, building, 3)).toEqual({ world: null, again: false, errorsInARow: 0 })
  const done = { ...building, status: 'ready' as const }
  expect(afterPoll({ kind: 'ok', world: done }, building, 5)).toEqual({ world: done, again: false, errorsInARow: 0 })
})
