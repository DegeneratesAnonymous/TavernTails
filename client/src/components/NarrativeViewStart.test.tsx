import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import NarrativeView from './NarrativeView'

const PLACEHOLDER = {
  id: 'opening',
  title: 'The Empty Caravan - Setup Pending',
  text: 'Complete the campaign brief and character setup to begin the opening scene.',
  narrative_body: 'Complete the campaign brief and character setup to begin the opening scene.',
  choices: [],
  setup_pending: true,
}

const REAL = {
  id: 'opening',
  title: 'Old River Road Toll Crossing',
  narrative_body: 'Mist lifts off the river as the lead wagon rolls in empty.',
  choices: [],
}

function mockServer(opts: { scene: Record<string, unknown>; status?: Record<string, unknown> }) {
  const calls: { url: string; method: string }[] = []
  const original = global.fetch
  global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const href = String(url)
    calls.push({ url: href, method: init?.method || 'GET' })
    if (href.includes('/file/scene.json')) return { ok: true, status: 200, json: async () => opts.scene } as Response
    if (href.includes('/start-status')) {
      return { ok: true, status: 200, json: async () => ({ state: 'running', stage: 'scene', stages: [{ id: 'planning', label: 'Planning the opening' }, { id: 'scene', label: 'Building the scene' }], elapsed_s: 12, error: null, scene_ready: false, ...opts.status }) } as Response
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response
  }) as unknown as typeof fetch
  return { calls, restore: () => { global.fetch = original } }
}

test('the setup placeholder is shown as progress, not as the story, and never fires its own start', async () => {
  const server = mockServer({ scene: PLACEHOLDER })
  try {
    render(<NarrativeView sessionId="s1" />)
    expect(await screen.findByText('Writing your opening')).toBeInTheDocument()
    expect(screen.queryByText(/Complete the campaign brief/)).not.toBeInTheDocument()
    await waitFor(() => expect(server.calls.some(c => c.url.includes('/start-status'))).toBe(true))
    expect(server.calls.filter(c => c.method === 'POST')).toHaveLength(0)
  } finally { server.restore() }
})

test('a real scene is shown straight away with no progress panel', async () => {
  const server = mockServer({ scene: REAL })
  try {
    render(<NarrativeView sessionId="s1" />)
    expect(await screen.findByText(/lead wagon rolls in empty/)).toBeInTheDocument()
    expect(screen.queryByText('Writing your opening')).not.toBeInTheDocument()
    expect(server.calls.some(c => c.url.includes('/start-status'))).toBe(false)
  } finally { server.restore() }
})

test('a session that has not been started is started by the progress panel, once', async () => {
  const server = mockServer({ scene: PLACEHOLDER, status: { state: 'idle', stage: 'planning' } })
  try {
    render(<NarrativeView sessionId="s1" />)
    await waitFor(() => expect(server.calls.filter(c => c.method === 'POST' && c.url.endsWith('/sessions/s1/start'))).toHaveLength(1))
  } finally { server.restore() }
})
