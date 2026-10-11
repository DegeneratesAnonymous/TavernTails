import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import CampaignCardCreator from './CampaignCardCreator'

const CARD = {
  fields: {
    name: { value: 'The Dark Lamp', status: 'guessed' },
    premise: { value: 'A grim harbor town where the keeper vanished.', status: 'said' },
    genre: { value: 'mystery', status: 'guessed' },
    tone: { value: 'grim', status: 'said' },
    world_name: { value: '', status: 'open' },
    starting_place: { value: '', status: 'open' },
    opening_trouble: { value: '', status: 'open' },
    ruleset: { value: 'D&D 5e', status: 'said' },
    starting_level: { value: 3, status: 'said' },
    pacing: { value: 'slow', status: 'guessed' },
    content_rating: { value: 'pg-13', status: 'guessed' },
    ai_freedom: { value: 'medium', status: 'guessed' },
  },
  people: [{ name: 'Maren Vey', role: 'keeper', status: 'said' }],
  factions: [],
  themes: ['corruption', 'loyalty'],
  content_limits: ['harm to children'],
  open_questions: ['Who profits from the dark lamp?'],
  follow_ups: [
    { id: 'starting_place', field: 'starting_place', question: 'Where does the story open?', placeholder: '' },
    { id: 'opening_trouble', field: 'opening_trouble', question: "What's going wrong when the story begins?", placeholder: '' },
  ],
  derived: { canon_policy: 'guided_canon', ai_creativity_level: 'balanced', creation_posture: 'player_fast_start' },
  diagnostics: { source: 'model' },
  text: 'A grim harbor town where the keeper vanished.',
  has_lore: false,
  starter: {},
}

function mockServer() {
  const calls: { url: string; method: string; body: any }[] = []
  const original = global.fetch
  global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const href = String(url)
    const body = init?.body ? JSON.parse(String(init.body)) : null
    calls.push({ url: href, method: init?.method || 'GET', body })
    if (href.endsWith('/campaigns/card')) return { ok: true, status: 200, json: async () => ({ card: CARD }) } as Response
    if (href.endsWith('/campaigns')) {
      return { ok: true, status: 201, json: async () => ({ campaign: { id: 'c1', sessions: [{ id: 's1' }] } }) } as Response
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response
  }) as unknown as typeof fetch
  return { calls, restore: () => { global.fetch = original } }
}

test('describe, read it back, answer a follow-up, and create', async () => {
  const server = mockServer()
  const onCreated = jest.fn()
  try {
    render(
      <CampaignCardCreator
        seat={<div>seat</div>}
        owner={{ owner_role: 'dm', owner_character_id: null }}
        validateSeat={() => null}
        fallbackName="The Last Lantern"
        onCreated={onCreated}
        onClassic={() => {}}
      />,
    )
    const readBack = screen.getByRole('button', { name: /read it back/i })
    expect(readBack).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /mystery/i }))
    expect((screen.getByLabelText('Describe your campaign') as HTMLTextAreaElement).value).toMatch(/mystery campaign/)
    fireEvent.change(screen.getByLabelText('Describe your campaign'), { target: { value: CARD.text } })
    fireEvent.click(readBack)

    expect(await screen.findByText("Here's what I heard")).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'You said' })).toHaveTextContent('Maren Vey')
    expect(screen.getByLabelText('Tone')).toHaveValue('grim')
    expect(screen.getByText('Who profits from the dark lamp?')).toBeInTheDocument()
    const cardRequest = server.calls.find((c) => c.url.endsWith('/campaigns/card'))
    expect(cardRequest?.body.starter).toEqual({ genre: 'mystery' })

    // Everything Create will save is visible first, and a wrong guess can be removed.
    expect(screen.getByRole('region', { name: 'Limits and themes' })).toHaveTextContent('harm to children')
    fireEvent.click(screen.getByRole('button', { name: 'Remove theme: loyalty' }))
    expect(screen.queryByText('loyalty')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Genre'), { target: { value: 'horror' } })
    expect(screen.getByText('edited')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Where does the story open?'), { target: { value: 'the Gull Steps' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Show me the world' }))
    fireEvent.click(screen.getByRole('button', { name: /create campaign/i }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('c1', 's1'))
    const create = server.calls.find((c) => c.url.endsWith('/campaigns') && c.method === 'POST')
    expect(create?.body.card.fields.genre).toEqual({ value: 'horror', status: 'said' })
    expect(create?.body.follow_up_answers).toEqual({ starting_place: 'the Gull Steps' })
    expect(create?.body.world_visibility).toBe('show')
    expect(create?.body.card.themes).toEqual(['corruption'])
    expect(create?.body.card.content_limits).toEqual(['harm to children'])
    expect(create?.body.owner_role).toBe('dm')
  } finally {
    server.restore()
  }
})

test('a missing seat stops creation before any request', async () => {
  const server = mockServer()
  try {
    render(
      <CampaignCardCreator
        seat={null}
        owner={{ owner_role: 'player', owner_character_id: null }}
        validateSeat={() => 'Choose which character you are joining with, or designate yourself as DM.'}
        fallbackName="The Last Lantern"
        onCreated={() => {}}
        onClassic={() => {}}
      />,
    )
    fireEvent.change(screen.getByLabelText('Describe your campaign'), { target: { value: CARD.text } })
    fireEvent.click(screen.getByRole('button', { name: /read it back/i }))
    fireEvent.click(await screen.findByRole('button', { name: /create campaign/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/choose which character/i)
    expect(server.calls.some((c) => c.url.endsWith('/campaigns') && c.method === 'POST')).toBe(false)
  } finally {
    server.restore()
  }
})

test('switching genre replaces the starter sentence but never the player\'s own words', () => {
  render(
    <CampaignCardCreator
      seat={null}
      owner={{ owner_role: 'dm', owner_character_id: null }}
      validateSeat={() => null}
      fallbackName="The Last Lantern"
      onCreated={() => {}}
      onClassic={() => {}}
    />,
  )
  const box = screen.getByLabelText('Describe your campaign') as HTMLTextAreaElement
  fireEvent.click(screen.getByRole('button', { name: /fantasy/i }))
  expect(box.value).toMatch(/fantasy campaign/)
  fireEvent.click(screen.getByRole('button', { name: /horror/i }))
  expect(box.value).toMatch(/horror campaign/)
  fireEvent.click(screen.getByRole('button', { name: /horror/i }))
  expect(box.value).toBe('')
  fireEvent.change(box, { target: { value: 'My own idea about haunted canals.' } })
  fireEvent.click(screen.getByRole('button', { name: /sci-fi/i }))
  expect(box.value).toBe('My own idea about haunted canals.')
})

test('the description is frozen while it is being read back', async () => {
  let release: (value: Response) => void = () => {}
  const original = global.fetch
  global.fetch = jest.fn(() => new Promise<Response>((resolve) => { release = resolve })) as unknown as typeof fetch
  try {
    render(
      <CampaignCardCreator
        seat={null}
        owner={{ owner_role: 'dm', owner_character_id: null }}
        validateSeat={() => null}
        fallbackName="The Last Lantern"
        onCreated={() => {}}
        onClassic={() => {}}
      />,
    )
    const box = screen.getByLabelText('Describe your campaign')
    fireEvent.change(box, { target: { value: CARD.text } })
    fireEvent.click(screen.getByRole('button', { name: /read it back/i }))
    expect(box).toBeDisabled()
    expect(screen.getByRole('button', { name: /mystery/i })).toBeDisabled()
    release({ ok: true, status: 200, json: async () => ({ card: CARD }) } as Response)
    expect(await screen.findByText("Here's what I heard")).toBeInTheDocument()
  } finally {
    global.fetch = original
  }
})

test('"Stick to what I wrote" says nothing is invented ahead of play', async () => {
  const server = mockServer()
  try {
    render(
      <CampaignCardCreator
        seat={null}
        owner={{ owner_role: 'dm', owner_character_id: null }}
        validateSeat={() => null}
        fallbackName="The Last Lantern"
        onCreated={() => {}}
        onClassic={() => {}}
      />,
    )
    fireEvent.change(screen.getByLabelText('Describe your campaign'), { target: { value: CARD.text } })
    fireEvent.click(screen.getByRole('button', { name: /read it back/i }))
    expect(await screen.findByRole('radio', { name: 'Show me the world' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'Stick to what I wrote' }))
    expect(screen.queryByRole('radio', { name: 'Show me the world' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'The world' })).toHaveTextContent(/nothing is invented ahead of play/)
  } finally {
    server.restore()
  }
})

test('a mistaken person can be removed and a missing limit added before Create', async () => {
  const server = mockServer()
  const onCreated = jest.fn()
  try {
    render(
      <CampaignCardCreator
        seat={null}
        owner={{ owner_role: 'dm', owner_character_id: null }}
        validateSeat={() => null}
        fallbackName="The Last Lantern"
        onCreated={onCreated}
        onClassic={() => {}}
      />,
    )
    fireEvent.change(screen.getByLabelText('Describe your campaign'), { target: { value: CARD.text } })
    fireEvent.click(screen.getByRole('button', { name: /read it back/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Remove person: Maren Vey' }))
    fireEvent.change(screen.getByLabelText('Add something to keep out of the story'), { target: { value: 'graphic gore' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.click(screen.getByRole('button', { name: /create campaign/i }))
    await waitFor(() => expect(onCreated).toHaveBeenCalled())
    const create = server.calls.find((c) => c.url.endsWith('/campaigns') && c.method === 'POST')
    expect(create?.body.card.people).toEqual([])
    expect(create?.body.card.content_limits).toEqual(['harm to children', 'graphic gore'])
  } finally {
    server.restore()
  }
})

test('open questions can be removed and limits stop at the server cap', async () => {
  const server = mockServer()
  try {
    render(
      <CampaignCardCreator
        seat={null}
        owner={{ owner_role: 'dm', owner_character_id: null }}
        validateSeat={() => null}
        fallbackName="The Last Lantern"
        onCreated={() => {}}
        onClassic={() => {}}
      />,
    )
    fireEvent.change(screen.getByLabelText('Describe your campaign'), { target: { value: CARD.text } })
    fireEvent.click(screen.getByRole('button', { name: /read it back/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Remove question: Who profits from the dark lamp?' }))
    expect(screen.queryByText('Who profits from the dark lamp?')).not.toBeInTheDocument()
    const input = screen.getByLabelText('Add something to keep out of the story')
    for (let i = 0; i < 10; i += 1) {
      fireEvent.change(input, { target: { value: `limit ${i}` } })
      fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    }
    expect(screen.getAllByRole('button', { name: /Remove limit:/ })).toHaveLength(8)
    expect(input).toBeDisabled()
  } finally {
    server.restore()
  }
})
