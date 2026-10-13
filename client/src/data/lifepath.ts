/**
 * Stages for the world builder and the character backstory builder.
 *
 * Both builders are a list of stages. Each stage offers cards and always has room for the player's own words.
 * The answers become entries for the server, which drafts a narrative of the choices for the player to edit.
 * Nothing here touches ability scores, skills or proficiencies: it is roleplay only.
 *
 * A backstory is the B plot. The "link" stage requires it to touch the world's main trouble (the A plot).
 */

export type Option = {
  id: string
  label: string
  /** The choice as part of a sentence. A character's is a predicate ("was raised in X"), a world's a full sentence. */
  clause: string
}

export type StageKind = 'choice' | 'text' | 'powers' | 'places' | 'ties' | 'traits' | 'link' | 'goals'

export type Stage = {
  id: string
  title: string
  question: string
  hint?: string
  kind: StageKind
  required?: boolean
  /** Options can depend on earlier answers (the places a world has, the factions a link can name). */
  options?: (answers: Answers) => Option[]
  typedLabel?: string
  typedPlaceholder?: string
}

export type StageAnswer = {
  picked: string[]
  typed: string
  fields: Record<string, string>
}

export type Answers = Record<string, StageAnswer>

export type WorldContext = {
  world_name: string
  conflict: string
  factions: string[]
  places: string[]
  tone: string
  narrative: string
}

export type Entry = {
  stage: string
  question: string
  answer: string
  clause: string
  source: 'option' | 'typed'
}

export type LinkChoice = { kind: 'faction' | 'place' | 'conflict' | 'tie' | 'story'; name: string }

export type Goal = { term: 'short' | 'mid' | 'long'; text: string; because: string; but: string }

export const emptyAnswer = (): StageAnswer => ({ picked: [], typed: '', fields: {} })
export const answerFor = (answers: Answers, id: string): StageAnswer => answers[id] ?? emptyAnswer()

const opt = (id: string, label: string, clause: string = label): Option => ({ id, label, clause })
const clean = (value: string | undefined) => (value ?? '').replace(/\s+/g, ' ').trim()
const lowerFirst = (value: string) => (value ? value[0].toLowerCase() + value.slice(1) : value)
const list = (items: string[]) =>
  items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`

// ─────────────────────────────────────────────
// World
// ─────────────────────────────────────────────

const TONES = [
  opt('grim', 'Grim and grounded', 'The tone is grim and grounded.'),
  opt('cozy', 'Warm and cozy', 'The tone is warm and cozy.'),
  opt('heroic', 'Cinematic heroism', 'The tone is cinematic heroism.'),
  opt('strange', 'Dark and strange', 'The tone is dark and strange.'),
  opt('witty', 'Light and witty', 'The tone is light and witty.'),
]

const GENRES = [
  opt('fantasy', 'Fantasy', 'It is a fantasy world.'),
  opt('horror', 'Horror', 'It is a horror setting.'),
  opt('sci-fi', 'Science fiction', 'It is a science-fiction setting.'),
  opt('mystery', 'Mystery', 'It is a world of mysteries.'),
  opt('political', 'Political intrigue', 'It is a world of political intrigue.'),
  opt('post-apocalyptic', 'Survival', 'It is a world where survival is not guaranteed.'),
]

const CONFLICTS = [
  opt('sickness', 'A sickness no healer can name', 'A sickness spreads that no healer can name.'),
  opt('missing-ruler', 'A ruler has vanished', 'The ruler has vanished.'),
  opt('war', 'Two powers on the brink of war', 'Two powers stand one provocation from war.'),
  opt('waking', 'Something old is waking', 'Something old is waking beneath the land.'),
  opt('debt', 'A debt is coming due', 'A debt is coming due for the whole region.'),
  opt('scarcity', 'Supplies are failing', 'Supplies are failing and neighbours are turning on each other.'),
  opt('silent-gods', 'The old gods have gone silent', 'The old gods have gone silent.'),
  opt('claimant', 'A stranger claims the throne', 'A stranger has arrived with a claim to the throne.'),
]

const EVERYDAY = [
  opt('hard', 'Hard and hand-to-mouth', 'Ordinary people live hard, hand to mouth.'),
  opt('settled', 'Settled and comfortable', 'Ordinary people live settled, comfortable lives.'),
  opt('watched', 'Watched and afraid', 'Ordinary people live watched and afraid.'),
  opt('free', 'Free and fast-changing', 'Ordinary people live free, in a world that changes fast.'),
]

const placesOf = (answers: Answers) =>
  [0, 1, 2, 3].map((i) => clean(answerFor(answers, 'places').fields[`p${i}`])).filter(Boolean)

export const worldStages = (): Stage[] => [
  { id: 'name', title: 'Name', question: 'What is this world called?', kind: 'text', typedPlaceholder: 'Saltmere, the Hollow Coast… (or leave blank)' },
  { id: 'tone', title: 'Tone', question: 'What should it feel like at the table?', hint: 'The tone and ground rules everyone has agreed to.', kind: 'choice', required: true, options: () => TONES, typedLabel: 'Something else' },
  { id: 'genre', title: 'Genre', question: 'What kind of world is it?', kind: 'choice', required: true, options: () => GENRES, typedLabel: 'Something else' },
  { id: 'conflict', title: 'The trouble', question: 'What is going wrong?', hint: 'The main conflict. Every character’s story will connect to it.', kind: 'choice', required: true, options: () => CONFLICTS, typedLabel: 'Describe it your way' },
  { id: 'powers', title: 'Powers', question: 'Who holds power, and what does each want?', hint: 'Factions have goals of their own, and so will the story.', kind: 'powers', required: true },
  { id: 'places', title: 'Places', question: 'Name a few places that matter.', kind: 'places', required: true },
  {
    id: 'start', title: 'The start', question: 'Where does the story open?', kind: 'choice', required: true, typedLabel: 'Somewhere else',
    options: (answers) => placesOf(answers).map((p, i) => opt(`start-${i}`, p, `The story opens in ${p}.`)),
  },
  { id: 'life', title: 'Everyday life', question: 'How do ordinary people live?', kind: 'choice', options: () => EVERYDAY, typedLabel: 'Something else' },
  { id: 'rules', title: 'Table rules', question: 'Anything the table wants left out, or a rule of the world?', hint: 'For example: magic is rare; no harm to children.', kind: 'text', typedPlaceholder: 'Optional' },
]

// ─────────────────────────────────────────────
// Character
// ─────────────────────────────────────────────

const RAISED = [
  opt('parents', 'By my parents', 'was raised by their parents'),
  opt('grandparent', 'By a grandparent', 'was raised by a grandparent'),
  opt('order', 'By an order or guild', 'was raised by an order or guild'),
  opt('found', 'By a found family', 'was raised by a found family'),
  opt('alone', 'Largely alone', 'was left largely to raise themselves'),
]

const EVENTS = [
  opt('loss', 'I lost someone close', 'lost someone close, and carries the cost'),
  opt('betrayal', 'Someone I trusted betrayed me', 'was betrayed by someone they trusted'),
  opt('disaster', 'I survived a disaster', 'survived a disaster that took others'),
  opt('debt', 'I took on a debt', 'took on a debt that is still owed'),
  opt('secret', 'I learned something I should not have', 'learned something they were never meant to know'),
  opt('exile', 'I was driven out', 'was driven from home'),
  opt('regret', 'I did something I regret', 'did something they still regret'),
]

const IDEALS = [
  opt('brave', 'Courage', 'courage'), opt('kind', 'Kindness', 'kindness'), opt('just', 'Justice', 'justice'),
  opt('wise', 'Wisdom', 'wisdom'), opt('free', 'Freedom', 'freedom'), opt('loyal', 'Loyalty', 'loyalty'),
]
const FLAWS = [
  opt('reckless', 'Reckless', 'reckless'), opt('stubborn', 'Stubborn', 'stubborn'), opt('greedy', 'Greedy', 'greedy'),
  opt('secretive', 'Secretive', 'secretive'), opt('proud', 'Proud', 'proud'), opt('fearful', 'Fearful', 'fearful'),
]
const BONDS = [
  opt('family', 'My family', 'family'), opt('cause', 'A cause I serve', 'a cause'), opt('debt', 'A debt I owe', 'a debt'),
  opt('secret', 'A secret I keep', 'a secret'), opt('place', 'A place I protect', 'a place'), opt('power', 'Power I seek', 'power'),
]
export const TRAIT_OPTIONS = { ideals: IDEALS, flaws: FLAWS, bonds: BONDS }
export const ALIGNMENTS = [
  'Lawful Good', 'Neutral Good', 'Chaotic Good', 'Lawful Neutral', 'True Neutral', 'Chaotic Neutral',
  'Lawful Evil', 'Neutral Evil', 'Chaotic Evil', 'Unaligned',
]

const tieNames = (answers: Answers) => {
  const f = answerFor(answers, 'ties').fields
  return ['ally', 'rival', 'patron'].map((k) => clean(f[k])).filter(Boolean)
}

export const characterStages = (world: WorldContext): Stage[] => [
  {
    id: 'roots', title: 'Roots', question: 'Where do you come from in this world?', kind: 'choice', required: true, typedLabel: 'Somewhere else',
    options: () => [
      ...world.places.slice(0, 4).map((p, i) => opt(`place-${i}`, `From ${p}`, `grew up in ${p}`)),
      ...world.factions.slice(0, 3).map((f, i) => opt(`faction-${i}`, `Under ${f}`, `grew up where ${f} held sway`)),
      opt('road', 'On the road', 'grew up on the road, with no fixed home'),
      opt('far', 'Far from here', 'grew up far from where the story begins'),
    ],
  },
  { id: 'raised', title: 'Family', question: 'Who raised you?', kind: 'choice', options: () => RAISED, typedLabel: 'Someone else' },
  { id: 'event', title: 'Turning point', question: 'What happened that shaped you?', hint: 'And what did it cost you?', kind: 'choice', required: true, options: () => EVENTS, typedLabel: 'Something else' },
  { id: 'ties', title: 'Ties', question: 'Who is on your side, who is against you, who backs you?', hint: 'An ally, a rival or enemy, and a patron. Name people, or describe them. All optional.', kind: 'ties' },
  { id: 'traits', title: 'Who you are', question: 'What are you like?', kind: 'traits' },
  {
    id: 'link', title: 'The main trouble', question: `How does your story touch ${world.conflict ? `“${world.conflict}”` : 'the main trouble'}?`,
    hint: 'Your story is a second thread woven through the main one. It has to connect.', kind: 'link', required: true,
    options: (answers) => [
      ...(world.conflict ? [opt('conflict', 'The trouble itself', `is caught up in the main trouble: ${world.conflict}`)] : []),
      ...world.factions.slice(0, 4).map((f, i) => opt(`faction-${i}`, f, `is entangled with ${f}`)),
      ...world.places.slice(0, 4).map((p, i) => opt(`place-${i}`, p, `has ties to ${p}`)),
      ...tieNames(answers).map((t, i) => opt(`tie-${i}`, t, `is tied to the main trouble through ${t}`)),
      opt('story', 'Let the story decide', ''),
    ],
    typedLabel: 'Something else',
  },
  { id: 'goals', title: 'Goals', question: 'What do you want?', hint: 'A long goal is what the campaign is about. A short goal is a first step toward it.', kind: 'goals', required: true },
  { id: 'extra', title: 'Anything else', question: 'Anything else about this character?', kind: 'text', typedPlaceholder: 'Optional' },
]

// ─────────────────────────────────────────────
// Answers → what the server and the sheet need
// ─────────────────────────────────────────────

export function stageOptions(stage: Stage, answers: Answers): Option[] {
  return stage.options ? stage.options(answers) : []
}

export function stageDone(stage: Stage, answers: Answers): boolean {
  const a = answerFor(answers, stage.id)
  const f = a.fields
  switch (stage.kind) {
    case 'choice':
    case 'link':
      return !stage.required || a.picked.length > 0 || !!clean(a.typed)
    case 'powers':
      return !stage.required || !!clean(f.name0)
    case 'places':
      return !stage.required || !!clean(f.p0)
    case 'goals':
      return !stage.required || !!clean(f.long_text)
    default:
      return true
  }
}

const goalClause = (g: Goal) => `wants to ${lowerFirst(g.text)}${g.because ? ` because ${lowerFirst(g.because)}` : ''}${g.but ? `, but ${lowerFirst(g.but)}` : ''}`

export function goalsOf(answers: Answers): Goal[] {
  const f = answerFor(answers, 'goals').fields
  return (['long', 'mid', 'short'] as const)
    .map((term) => ({ term, text: clean(f[`${term}_text`]), because: clean(f[`${term}_because`]), but: clean(f[`${term}_but`]) }))
    .filter((g) => g.text)
}

export function linkOf(stages: Stage[], answers: Answers, world: WorldContext): LinkChoice | null {
  const stage = stages.find((s) => s.kind === 'link')
  if (!stage) return null
  const a = answerFor(answers, stage.id)
  const picked = stageOptions(stage, answers).find((o) => o.id === a.picked[0])
  if (picked) {
    if (picked.id === 'story') return { kind: 'story', name: '' }
    if (picked.id === 'conflict') return { kind: 'conflict', name: world.conflict }
    return { kind: picked.id.startsWith('faction') ? 'faction' : picked.id.startsWith('place') ? 'place' : 'tie', name: picked.label }
  }
  return clean(a.typed) ? { kind: 'tie', name: clean(a.typed) } : null
}

export function entriesFor(stages: Stage[], answers: Answers): Entry[] {
  const out: Entry[] = []
  const push = (stage: Stage, answer: string, clause: string, source: 'option' | 'typed' = 'option') => {
    if (clean(answer)) out.push({ stage: stage.id, question: stage.question, answer: clean(answer), clause: clean(clause), source })
  }
  for (const stage of stages) {
    const a = answerFor(answers, stage.id)
    const f = a.fields
    switch (stage.kind) {
      case 'choice': {
        const o = stageOptions(stage, answers).find((x) => x.id === a.picked[0])
        if (o) push(stage, o.label, o.clause)
        if (clean(a.typed)) push(stage, a.typed, '', 'typed')
        break
      }
      case 'link': {
        const o = stageOptions(stage, answers).find((x) => x.id === a.picked[0])
        if (o && o.id !== 'story') push(stage, o.label, o.clause)
        if (clean(a.typed)) push(stage, a.typed, `is tied to the main trouble through ${clean(a.typed)}`, 'typed')
        break
      }
      case 'text': {
        const text = clean(a.typed)
        if (stage.id === 'name' && text) push(stage, text, `The world is called ${text}.`, 'typed')
        else if (text) push(stage, text, '', 'typed')
        break
      }
      case 'powers':
        for (const i of [0, 1, 2]) {
          const name = clean(f[`name${i}`])
          const wants = clean(f[`wants${i}`])
          if (name) push(stage, wants ? `${name} — wants ${lowerFirst(wants)}` : name, wants ? `${name} wants ${lowerFirst(wants)}.` : `${name} holds power.`, 'typed')
        }
        break
      case 'places': {
        const names = [0, 1, 2, 3].map((i) => clean(f[`p${i}`])).filter(Boolean)
        if (names.length) push(stage, names.join(', '), `The places that matter are ${list(names)}.`, 'typed')
        break
      }
      case 'ties':
        if (clean(f.ally)) push(stage, `An ally: ${clean(f.ally)}`, `counts ${clean(f.ally)} as an ally`, 'typed')
        if (clean(f.rival)) push(stage, `A rival: ${clean(f.rival)}`, `has a rival in ${clean(f.rival)}`, 'typed')
        if (clean(f.patron)) push(stage, `A patron: ${clean(f.patron)}`, `is backed by ${clean(f.patron)}`, 'typed')
        break
      case 'traits': {
        const labels = (key: 'ideals' | 'flaws' | 'bonds') =>
          TRAIT_OPTIONS[key].filter((o) => (a.fields[`${key}_picked`] ?? '').split(',').includes(o.id)).map((o) => o.clause)
        const extra = (key: string) => clean(f[`${key}_t`])
        if (clean(f.alignment) && clean(f.alignment) !== 'Unaligned') push(stage, f.alignment, `leans ${f.alignment}`)
        const ideals = [...labels('ideals'), ...(extra('ideals') ? [extra('ideals')] : [])]
        if (ideals.length) push(stage, `Values ${list(ideals)}`, `prizes ${list(ideals)}`)
        const flaws = [...labels('flaws'), ...(extra('flaws') ? [extra('flaws')] : [])]
        if (flaws.length) push(stage, `Flaws: ${list(flaws)}`, `struggles with being ${list(flaws)}`)
        const bonds = [...labels('bonds'), ...(extra('bonds') ? [extra('bonds')] : [])]
        if (bonds.length) push(stage, `Bound to ${list(bonds)}`, `is bound to ${list(bonds)}`)
        if (extra('traits')) push(stage, extra('traits'), '', 'typed')
        break
      }
      case 'goals':
        for (const g of goalsOf(answers)) push(stage, `${g.term} goal: ${g.text}`, goalClause(g), 'typed')
        break
    }
  }
  return out
}

/** The world as the next builder (and the server) sees it. */
export function worldContextFromAnswers(stages: Stage[], answers: Answers, narrative = ''): WorldContext {
  const f = (id: string) => answerFor(answers, id).fields
  const choice = (id: string) => {
    const stage = stages.find((s) => s.id === id)
    const a = answerFor(answers, id)
    const o = stage ? stageOptions(stage, answers).find((x) => x.id === a.picked[0]) : undefined
    return o?.label ?? clean(a.typed)
  }
  return {
    world_name: clean(answerFor(answers, 'name').typed),
    conflict: choice('conflict'),
    factions: [0, 1, 2].map((i) => clean(f('powers')[`name${i}`])).filter(Boolean),
    places: [0, 1, 2, 3].map((i) => clean(f('places')[`p${i}`])).filter(Boolean),
    tone: choice('tone'),
    narrative,
  }
}

export type CharacterPayload = {
  backstory: string
  label: string
  bonds: string
  flaws: string
  ideals: string
  personality_traits: string
  alignment: string
  allies: string[]
  rivals: string[]
  patron: string
  goals: Goal[]
  link: LinkChoice | null
  lifepath: Record<string, unknown>
}

export function characterPayload(stages: Stage[], answers: Answers, world: WorldContext, narrative: string, label: string): CharacterPayload {
  const t = answerFor(answers, 'traits')
  const picked = (key: 'ideals' | 'flaws' | 'bonds') =>
    [...TRAIT_OPTIONS[key].filter((o) => (t.fields[`${key}_picked`] ?? '').split(',').includes(o.id)).map((o) => o.label), clean(t.fields[`${key}_t`])]
      .filter(Boolean)
      .join('\n')
  const ties = answerFor(answers, 'ties').fields
  return {
    backstory: narrative.trim(),
    label,
    bonds: picked('bonds'),
    flaws: picked('flaws'),
    ideals: picked('ideals'),
    personality_traits: clean(t.fields.traits_t),
    alignment: clean(t.fields.alignment),
    allies: clean(ties.ally) ? [clean(ties.ally)] : [],
    rivals: clean(ties.rival) ? [clean(ties.rival)] : [],
    patron: clean(ties.patron),
    goals: goalsOf(answers),
    link: linkOf(stages, answers, world),
    lifepath: { label, answers, saved_at: new Date().toISOString() },
  }
}

/** A world context from a campaign's confirmed card, so the backstory builder can start from any campaign. */
export function worldContextFromCard(card: {
  fields?: Record<string, { value?: string | number } | undefined>
  factions?: Array<{ name: string } | string>
  premise?: string
} | null | undefined): WorldContext {
  const v = (key: string) => clean(String(card?.fields?.[key]?.value ?? ''))
  return {
    world_name: v('world_name'),
    conflict: v('opening_trouble'),
    factions: (card?.factions ?? []).map((f) => clean(typeof f === 'string' ? f : f?.name)).filter(Boolean),
    places: [v('starting_place')].filter(Boolean),
    tone: v('tone'),
    narrative: v('premise') || clean(card?.premise),
  }
}
