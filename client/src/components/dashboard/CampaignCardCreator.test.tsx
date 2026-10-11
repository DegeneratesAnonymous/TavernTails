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
  themes: [],
  content_limits: [],
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
