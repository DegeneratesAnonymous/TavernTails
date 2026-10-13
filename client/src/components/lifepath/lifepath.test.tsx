import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import LifePathBuilder from './LifePathBuilder'
import BackstoryWizard from './BackstoryWizard'
import {
  characterPayload, characterStages, entriesFor, linkOf, stageDone, worldContextFromAnswers, worldContextFromCampaign, worldStages,
  type Answers, type WorldContext,
} from '../../data/lifepath'

const WORLD: WorldContext = {
  world_name: 'Saltmere', conflict: 'The granaries are burning', factions: ['Salt Court'], places: ['Ashen Market'], tone: 'grim', narrative: '',
}

const a = (over: Partial<Answers[string]> = {}) => ({ picked: [], typed: '', fields: {}, ...over })

describe('stages and answers', () => {
  test('a character stage list is built from the world and requires a link to the main trouble', () => {
    const stages = characterStages(WORLD)
    const link = stages.find((s) => s.kind === 'link')!
    expect(link.required).toBe(true)
    expect(stageDone(link, {})).toBe(false)
    const ids = link.options!({}).map((o) => o.label)
    expect(ids).toEqual(expect.arrayContaining(['The trouble itself', 'Salt Court', 'Ashen Market', 'Let the story decide']))
    expect(stageDone(link, { link: a({ picked: ['story'] }) })).toBe(true)
  })

  test('typing your own link also satisfies the requirement', () => {
    const link = characterStages(WORLD).find((s) => s.kind === 'link')!
    expect(stageDone(link, { link: a({ typed: 'my old master' }) })).toBe(true)
  })

  test('the long goal is required, short and mid are not', () => {
    const goals = characterStages(WORLD).find((s) => s.id === 'goals')!
    expect(stageDone(goals, {})).toBe(false)
    expect(stageDone(goals, { goals: a({ fields: { short_text: 'a first step' } }) })).toBe(false)
    expect(stageDone(goals, { goals: a({ fields: { long_text: 'find the arsonist' } }) })).toBe(true)
  })

  test('answers become entries; links resolve to the world', () => {
    const stages = characterStages(WORLD)
    const answers: Answers = {
      roots: a({ picked: ['place-0'] }),
      link: a({ picked: ['faction-0'] }),
      goals: a({ fields: { long_text: 'find who burned the granary', long_because: 'my street went hungry', long_but: 'the witness left' } }),
      ties: a({ fields: { ally: 'Tam, a ferryman' } }),
    }
    const entries = entriesFor(stages, answers)
    expect(entries.find((e) => e.stage === 'roots')?.clause).toBe('grew up in Ashen Market')
    expect(entries.find((e) => e.stage === 'goals')?.clause).toBe('wants to find who burned the granary because my street went hungry, but the witness left')
    expect(entries.find((e) => e.stage === 'ties')?.clause).toBe('counts Tam, a ferryman as an ally')
    expect(linkOf(stages, answers, WORLD)).toEqual({ kind: 'faction', name: 'Salt Court' })
  })

  test('the payload writes roleplay fields only', () => {
    const stages = characterStages(WORLD)
    const answers: Answers = {
      traits: a({ fields: { alignment: 'Chaotic Good', ideals_picked: 'free', flaws_picked: 'proud', flaws_t: 'Never asks for help' } }),
      ties: a({ fields: { rival: 'a magistrate', patron: 'the guild' } }),
      goals: a({ fields: { long_text: 'clear the market name' } }),
      link: a({ picked: ['story'] }),
    }
    const payload = characterPayload(stages, answers, WORLD, 'Story.', 'Saltmere')
    expect(payload).toMatchObject({ alignment: 'Chaotic Good', ideals: 'Freedom', flaws: 'Proud\nNever asks for help', rivals: ['a magistrate'], patron: 'the guild' })
    expect(payload.goals[0]).toMatchObject({ term: 'long', text: 'clear the market name' })
    for (const key of ['stats', 'skills', 'proficiencies', 'abilityScores']) expect(payload).not.toHaveProperty(key)
  })

  test('a world builds its own context from its answers', () => {
    const stages = worldStages()
    const answers: Answers = {
      name: a({ typed: 'Saltmere' }),
      conflict: a({ picked: ['war'] }),
      powers: a({ fields: { name0: 'Salt Court', wants0: 'to control the grain', name1: 'Reed Guild' } }),
      places: a({ fields: { p0: 'Ashen Market', p1: 'Low Dock' } }),
    }
    const ctx = worldContextFromAnswers(stages, answers)
    expect(ctx).toMatchObject({ world_name: 'Saltmere', conflict: 'Two powers on the brink of war', factions: ['Salt Court', 'Reed Guild'], places: ['Ashen Market', 'Low Dock'] })
    const start = stages.find((s) => s.id === 'start')!
    expect(start.options!(answers).map((o) => o.label)).toEqual(['Ashen Market', 'Low Dock'])
  })
})

describe('the builder', () => {
  const realFetch = global.fetch
  afterEach(() => { global.fetch = realFetch })

  function stubNarrative(text = 'Mira grew up in the Ashen Market. She is tied to the Salt Court.') {
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      const body = String(url).includes('/lifepath/narrative') ? { narrative: text, source: 'model', issues: [] } : { committed: false, changes: [] }
      return { ok: true, status: 200, json: async () => body } as Response
    }) as unknown as typeof fetch
  }

  test('you cannot continue past the link stage without choosing one, then the story is drafted and editable', async () => {
    stubNarrative()
    const done = jest.fn()
    render(
      <LifePathBuilder
        kind="character" title="Mira" stages={characterStages(WORLD).filter((s) => ['roots', 'link', 'goals'].includes(s.id))}
        name="Mira" world={WORLD} doneLabel="Save" onCancel={() => {}} onDone={done}
      />,
    )
    fireEvent.click(screen.getByRole('radio', { name: 'From Ashen Market' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    const next = screen.getByRole('button', { name: 'Next' })
    expect(next).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent(/main trouble/i)
    fireEvent.click(screen.getByRole('radio', { name: 'Salt Court' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.change(screen.getAllByLabelText('My character wants to…')[0], { target: { value: 'find the arsonist' } })
    fireEvent.click(screen.getByRole('button', { name: 'Write it up' }))
    const box = await screen.findByLabelText('Narrative')
    await waitFor(() => expect(box).toHaveValue('Mira grew up in the Ashen Market. She is tied to the Salt Court.'))
    fireEvent.change(box, { target: { value: 'My own words.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(done).toHaveBeenCalled())
    expect(done.mock.calls[0][0].narrative).toBe('My own words.')
    expect(done.mock.calls[0][0].link).toEqual({ kind: 'faction', name: 'Salt Court' })
  })

  test('replacing an edited draft asks first', async () => {
    stubNarrative()
    const confirm = jest.spyOn(window, 'confirm').mockReturnValue(false)
    render(
      <LifePathBuilder
        kind="character" title="Mira" stages={[characterStages(WORLD).find((s) => s.id === 'extra')!]}
        name="Mira" world={WORLD} doneLabel="Save" onCancel={() => {}} onDone={() => {}}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Write it up|Skip/ }))
    const box = await screen.findByLabelText('Narrative')
    await waitFor(() => expect(box).toHaveValue('Mira grew up in the Ashen Market. She is tied to the Salt Court.'))
    fireEvent.change(box, { target: { value: 'Mine.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Write it again' }))
    expect(confirm).toHaveBeenCalled()
    expect(box).toHaveValue('Mine.')
    confirm.mockRestore()
  })
})

describe('saving a backstory', () => {
  const realFetch = global.fetch
  afterEach(() => { global.fetch = realFetch })

  function server(calls: Array<{ url: string; body: any }>) {
    global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const href = String(url)
      calls.push({ url: href, body: init?.body ? JSON.parse(String(init.body)) : null })
      const body = href.includes('/lifepath/narrative')
        ? { narrative: 'Mira grew up in the Ashen Market.', source: 'model', issues: [] }
        : { committed: true, changes: [{ field: 'backstory', before: 'Old tale.', after: 'Mira grew up in the Ashen Market.' }], ok: true }
      return { ok: true, status: 200, json: async () => body } as Response
    }) as unknown as typeof fetch
  }

  async function reachEnd() {
    fireEvent.click(screen.getByRole('radio', { name: 'From Ashen Market' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))          // roots
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))          // family
    fireEvent.click(screen.getByRole('radio', { name: 'I lost someone close' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))          // turning point
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))          // ties
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))          // traits
    fireEvent.click(screen.getByRole('radio', { name: 'Let the story decide' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))          // link
    fireEvent.change(screen.getAllByLabelText('My character wants to…')[0], { target: { value: 'find the arsonist' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))          // goals
    fireEvent.click(screen.getByRole('button', { name: /Write it up|Skip/ })) // anything else
    await screen.findByLabelText('Narrative')
  }

  test('with an existing backstory the player chooses add, replace or this campaign only, and sees what changes', async () => {
    const calls: Array<{ url: string; body: any }> = []
    server(calls)
    render(
      <BackstoryWizard
        character={{ id: 7, name: 'Mira', sheet: { backstory: 'Old tale.' } }} campaignId="c1" world={WORLD}
        onFinished={() => {}} onCancel={() => {}}
      />,
    )
    await reachEnd()
    const group = screen.getByRole('group', { name: /where should this go/i })
    expect(group).toHaveTextContent('Add to my character’s backstory')
    expect(group).toHaveTextContent('Replace my character’s backstory (you can undo)')
    expect(group).toHaveTextContent('Keep it for this campaign only')
    // A campaign is in play and the character already has a story, so the safe choice is the default.
    expect(screen.getByRole('radio', { name: /this campaign only/ })).toBeChecked()
    fireEvent.click(screen.getByRole('radio', { name: /^Replace/ }))
    expect(await screen.findByText(/Before: Old tale\./)).toBeInTheDocument()
    expect(calls.some((c) => c.url.includes('/apply') && c.body.mode === 'overwrite' && c.body.commit === false)).toBe(true)
    expect(calls.some((c) => c.url.includes('/apply') && c.body.commit === true)).toBe(false) // nothing is written yet
  })

  test('saving to the campaign only never calls the character route', async () => {
    const calls: Array<{ url: string; body: any }> = []
    server(calls)
    render(
      <BackstoryWizard
        character={{ id: 7, name: 'Mira', sheet: { backstory: 'Old tale.' } }} campaignId="c1" world={WORLD}
        onFinished={() => {}} onCancel={() => {}}
      />,
    )
    await reachEnd()
    await waitFor(() => expect(screen.getByLabelText('Narrative')).toHaveValue('Mira grew up in the Ashen Market.'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Kept for this campaign.')).toBeInTheDocument()
    expect(calls.some((c) => c.url.includes('/lifepath/campaigns/c1/characters/7'))).toBe(true)
    expect(calls.some((c) => c.url.includes('/lifepath/characters/7/apply') && c.body.commit)).toBe(false)
  })

  test('replacing offers undo afterwards', async () => {
    const calls: Array<{ url: string; body: any }> = []
    server(calls)
    render(
      <BackstoryWizard
        character={{ id: 7, name: 'Mira', sheet: { backstory: 'Old tale.' } }} world={WORLD}
        onFinished={() => {}} onCancel={() => {}}
      />,
    )
    await reachEnd()
    await waitFor(() => expect(screen.getByLabelText('Narrative')).toHaveValue('Mira grew up in the Ashen Market.'))
    fireEvent.click(screen.getByRole('radio', { name: /^Replace/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(calls.some((c) => c.url.includes('/lifepath/characters/7/undo'))).toBe(true))
  })
})

describe('review fixes', () => {
  test('a classic campaign with no card still gives the builder its world from settings', () => {
    const ctx = worldContextFromCampaign({
      settings: { world_name: 'Saltmere', opening_trouble: 'Grain is burning', starting_location: 'Ashen Market', tone: 'grim' },
      variables: { factions: [{ name: 'Salt Court' }] },
    })
    expect(ctx).toMatchObject({ world_name: 'Saltmere', conflict: 'Grain is burning', places: ['Ashen Market'], factions: ['Salt Court'], tone: 'grim' })
  })

  test('typing your own answer replaces a chosen card, and choosing a card clears the typed text', () => {
    const stages = worldStages().filter((s) => s.id === 'tone')
    render(<LifePathBuilder kind="world" title="W" stages={stages} name="" world={WORLD} doneLabel="Save" onCancel={() => {}} onDone={() => {}} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Grim and grounded' }))
    expect(screen.getByRole('radio', { name: 'Grim and grounded' })).toBeChecked()
    fireEvent.change(screen.getByLabelText('Something else'), { target: { value: 'cozy but with teeth' } })
    expect(screen.getByRole('radio', { name: 'Grim and grounded' })).not.toBeChecked()
    fireEvent.click(screen.getByRole('radio', { name: 'Warm and cozy' }))
    expect(screen.getByLabelText('Something else')).toHaveValue('')
  })
})
