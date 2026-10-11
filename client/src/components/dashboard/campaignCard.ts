/**
 * Campaign Card types and the pure rules the creation screen follows.
 *
 * The server reads the player's description into a card whose fields are
 * "said" (the player's own words), "guessed" (shown so they can change it) or
 * "open" (left for play, or asked as a follow-up). Anything the player edits
 * becomes "said": it is their words now.
 */

export type FieldStatus = 'said' | 'guessed' | 'open'

export type CardField = { value: string | number; status: FieldStatus }

export type FollowUp = { id: string; field: string; question: string; placeholder: string }

export type CampaignCard = {
  fields: Record<string, CardField>
  people: { name: string; role?: string; status: FieldStatus }[]
  factions: { name: string; status: FieldStatus }[]
  themes: string[]
  content_limits: string[]
  open_questions: string[]
  follow_ups: FollowUp[]
  derived: { canon_policy: string; ai_creativity_level: string; creation_posture: string }
  diagnostics: { source: 'model' | 'fallback'; reason?: string }
  text: string
  has_lore: boolean
  starter: Record<string, string>
}

export type WorldVisibility = 'surprise' | 'show'

export type WorldPieceName = 'truth' | 'factions' | 'npcs' | 'clock'

export type WorldState = {
  status: 'not_started' | 'pending' | 'running' | 'ready' | 'partial' | 'failed' | 'interrupted'
  visibility: WorldVisibility
  pieces: Record<WorldPieceName, { status: 'pending' | 'ready' | 'failed'; data?: any }>
}

export const WORLD_PIECES: { id: WorldPieceName; label: string }[] = [
  { id: 'truth', label: 'What is really going on' },
  { id: 'factions', label: 'Factions and what they want' },
  { id: 'npcs', label: 'Key people and their secrets' },
  { id: 'clock', label: 'What gets worse if nobody acts' },
]

export const MAIN_FIELDS: { key: string; label: string; multiline?: boolean }[] = [
  { key: 'name', label: 'Campaign name' },
  { key: 'premise', label: 'Premise', multiline: true },
  { key: 'genre', label: 'Genre' },
  { key: 'tone', label: 'Tone' },
  { key: 'world_name', label: 'World' },
  { key: 'starting_place', label: 'Where it opens' },
  { key: 'opening_trouble', label: "What's going wrong", multiline: true },
  { key: 'ruleset', label: 'Game system' },
  { key: 'starting_level', label: 'Starting level' },
]

export const GENRE_OPTIONS = [
  'fantasy', 'horror', 'sci-fi', 'mystery', 'political', 'post-apocalyptic', 'thriller', 'western', 'modern',
]

export const FREEDOM_OPTIONS = [
  { id: 'low', label: 'Stick to what I wrote' },
  { id: 'medium', label: 'Fill the gaps' },
  { id: 'high', label: 'Surprise me' },
]

/** Set a field to the player's own value; clearing it leaves the field open. */
export function editField(card: CampaignCard, key: string, value: string | number): CampaignCard {
  const empty = value === '' || value === null || value === undefined
  return {
    ...card,
    fields: { ...card.fields, [key]: { value: empty ? '' : value, status: empty ? 'open' : 'said' } },
  }
}

/**
 * Field keys grouped by the status the card arrived with. Grouping by the
 * arrival status keeps a field in place while the player edits it.
 */
export function groupFields(card: CampaignCard, keys: string[]): Record<FieldStatus, string[]> {
  const groups: Record<FieldStatus, string[]> = { said: [], guessed: [], open: [] }
  for (const key of keys) {
    const status = card.fields[key]?.status ?? 'open'
    groups[status].push(key)
  }
  return groups
}

/** Follow-up fields are asked as questions, not shown again in the "still open" list. */
export function openFieldsWithoutFollowUps(card: CampaignCard, openKeys: string[]): string[] {
  const asked = new Set(card.follow_ups.map((q) => q.field))
  return openKeys.filter((key) => !asked.has(key))
}

export type CreateCardInput = {
  card: CampaignCard
  answers: Record<string, string>
  fallbackName: string
  visibility: WorldVisibility
  generateWorld: boolean
  lore: string
  owner: { owner_role: 'player' | 'dm'; owner_character_id: number | null }
}

/** The POST /campaigns body for a confirmed card. */
export function buildCreatePayload(input: CreateCardInput) {
  let card = input.card
  const name = String(card.fields.name?.status === 'open' ? '' : card.fields.name?.value ?? '').trim()
  if (!name) {
    card = { ...card, fields: { ...card.fields, name: { value: input.fallbackName, status: 'guessed' } } }
  }
  const answers: Record<string, string> = {}
  for (const [key, value] of Object.entries(input.answers)) {
    if (value.trim()) answers[key] = value.trim()
  }
  return {
    name: name || input.fallbackName,
    card,
    follow_up_answers: answers,
    world_visibility: input.visibility,
    generate_world: input.generateWorld,
    imported_lore_summary: input.lore.trim() || null,
    create_session: true,
    ...input.owner,
  }
}

/** True while the world skeleton is still being built and worth polling. */
export function worldInProgress(world: WorldState | null): boolean {
  return Boolean(world && (world.status === 'pending' || world.status === 'running'))
}

/** One poll's outcome: the world, a deliberate "not for you / not here" (403, 404), or a transport error. */
export type WorldPoll = { kind: 'ok'; world: WorldState | null } | { kind: 'gone' } | { kind: 'error' }

export const MAX_POLL_ERRORS = 12

/**
 * What the panel shows after a poll, and whether to poll again. A transient error keeps the last
 * known world and keeps polling (up to MAX_POLL_ERRORS in a row), so one dropped request does not
 * hide a world that is still being built; 403/404 stop.
 */
export function afterPoll(
  poll: WorldPoll,
  previous: WorldState | null,
  errorsInARow: number,
): { world: WorldState | null; again: boolean; errorsInARow: number } {
  if (poll.kind === 'ok') return { world: poll.world, again: worldInProgress(poll.world), errorsInARow: 0 }
  if (poll.kind === 'gone') return { world: null, again: false, errorsInARow: 0 }
  const errors = errorsInARow + 1
  const unknownOrBuilding = previous === null || worldInProgress(previous)
  return { world: previous, again: unknownOrBuilding && errors < MAX_POLL_ERRORS, errorsInARow: errors }
}
