import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import GoalsDialog from './GoalsDialog'

const LIST = {
  scenes_since_review: 3,
  characters: [
    { character_id: 1, name: 'Mira', you: true, goals: [{ id: 'g1', term: 'long', text: 'find who burned the granary', because: 'my street went hungry', but: '', status: 'active', note: '' }] },
    { character_id: 2, name: 'Tam', you: false, goals: [{ id: 'g2', term: 'long', text: 'repay the ferry debt', because: '', but: '', status: 'active', note: '' }] },
  ],
}

function server(extra: Record<string, unknown> = {}) {
  const calls: { url: string; method: string; body: any }[] = []
  const original = global.fetch
  global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const href = String(url)
    calls.push({ url: href, method: init?.method || 'GET', body: init?.body ? JSON.parse(String(init.body)) : null })
    const key = Object.keys(extra).find((k) => href.endsWith(k))
    const body = key ? extra[key] : href.endsWith('/goals') ? LIST : {}
    return { ok: true, status: 200, json: async () => body } as Response
  }) as unknown as typeof fetch
  return { calls, restore: () => { global.fetch = original } }
}

test('everyone’s goals are shown, but only your own can be changed', async () => {
  const s = server()
  try {
    render(<GoalsDialog sessionId="s1" open onClose={() => {}} />)
    const mira = await screen.findByRole('region', { name: 'Mira’s goals' })
    expect(mira).toHaveTextContent('find who burned the granary, because my street went hungry')
    expect(mira).toHaveTextContent('(you)')
    expect(mira.querySelectorAll('button')).not.toHaveLength(0)
    const tam = screen.getByRole('region', { name: 'Tam’s goals' })
    expect(tam).toHaveTextContent('repay the ferry debt')
    expect(Array.from(tam.querySelectorAll('button'))).toHaveLength(0)
  } finally { s.restore() }
})

test('the story’s suggestion is shown with its quote and changes nothing until the player acts', async () => {
  const s = server({
    '/goals/review': { suggestions: [{ character: 'mira', character_id: 1, goal_id: 'g1', goal: 'find who burned the granary', status: 'progressed', evidence: 'knew the granary fire was no accident', you: true }] },
  })
  try {
    render(<GoalsDialog sessionId="s1" open onClose={() => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: /check what changed \(3 new\)/i }))
    expect(await screen.findByText(/knew the granary fire was no accident/)).toBeInTheDocument()
    expect(s.calls.some((c) => c.url.endsWith('/goals/apply'))).toBe(false)
  } finally { s.restore() }
})

test('finishing a goal asks what is wanted next and can add it', async () => {
  const s = server()
  try {
    render(<GoalsDialog sessionId="s1" open onClose={() => {}} />)
    const mira = await screen.findByRole('region', { name: 'Mira’s goals' })
    fireEvent.click(Array.from(mira.querySelectorAll('button')).find((b) => b.textContent === 'Done')!)
    fireEvent.change(await screen.findByLabelText('New goal'), { target: { value: 'bring the Court to account' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add goal' }))
    await waitFor(() => expect(s.calls.some((c) => c.url.endsWith('/goals/add') && c.body.text === 'bring the Court to account')).toBe(true))
    expect(s.calls.find((c) => c.url.endsWith('/goals/apply'))?.body).toMatchObject({ character_id: 1, goal_id: 'g1', status: 'done' })
  } finally { s.restore() }
})
