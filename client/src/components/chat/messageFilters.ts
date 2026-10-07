export type ChatFilter = 'all' | 'story' | 'player' | 'dice' | 'system'

// Count tabs and select visible messages in one pass; dice remain visible in All.
export function selectMessages<T extends { who: string; text: string }>(messages: readonly T[], filter: ChatFilter) {
  const filterCounts: Record<ChatFilter, number> = { all: 0, story: 0, player: 0, dice: 0, system: 0 }
  const categories = Object.keys(filterCounts) as ChatFilter[]
  const visibleMessages: T[] = []
  for (const message of messages) {
    const system = message.who === 'system'
    const dice = system && /roll|→|\b\d+d\d+/i.test(message.text || '')
    const matches: Record<ChatFilter, boolean> = {
      all: !system || dice,
      story: message.who === 'gm',
      player: message.who === 'you' || message.who === 'ally',
      dice,
      system,
    }
    for (const category of categories) {
      if (matches[category]) filterCounts[category]++
    }
    if (matches[filter]) visibleMessages.push(message)
  }
  return { visibleMessages, filterCounts }
}
