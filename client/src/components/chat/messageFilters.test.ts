import { ChatFilter, selectMessages } from './messageFilters'

const messages = [
  { id: 1, who: 'gm', text: 'Ada waits.' },
  { id: 2, who: 'you', text: 'I roll a 1d20.' },
  { id: 3, who: 'ally', text: 'I follow.' },
  { id: 4, who: 'system', text: 'Session joined.' },
  { id: 5, who: 'system', text: 'Ada rolled Athletics: 15' },
  { id: 6, who: 'system', text: '1d6 = 3' },
  { id: 7, who: 'system', text: '14 → 17' },
]

test.each<[ChatFilter, number[]]>([
  ['all', [1, 2, 3, 5, 6, 7]], ['story', [1]], ['player', [2, 3]],
  ['dice', [5, 6, 7]], ['system', [4, 5, 6, 7]],
])('%s keeps message order and counts every tab', (filter, ids) => {
  const result = selectMessages(messages, filter)
  expect(result.visibleMessages.map(m => m.id)).toEqual(ids)
  expect(result.filterCounts).toEqual({ all: 6, story: 1, player: 2, dice: 3, system: 4 })
  expect(result.visibleMessages[0]).toBe(messages.find(m => m.id === ids[0]))
})

test('empty logs have no visible messages or counts', () => {
  expect(selectMessages([], 'all')).toEqual({
    visibleMessages: [], filterCounts: { all: 0, story: 0, player: 0, dice: 0, system: 0 },
  })
})
