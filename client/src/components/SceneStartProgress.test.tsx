import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SceneStartProgress, { formatElapsed } from './SceneStartProgress'

const STAGES = [
  { id: 'planning', label: 'Planning the opening' },
  { id: 'scene', label: 'Building the scene' },
  { id: 'composing', label: 'Shaping the narration' },
  { id: 'writing', label: 'Writing the prose' },
  { id: 'finishing', label: 'Saving the scene' },
]

function status(overrides: Record<string, unknown>) {
  return { state: 'running', stage: 'writing', stages: STAGES, elapsed_s: 42, error: null, scene_ready: false, ...overrides }
}

function mockServer(statuses: Record<string, unknown>[]) {
  const calls: { url: string; method: string }[] = []
  let i = 0
  const original = global.fetch
  global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const href = String(url)
    calls.push({ url: href, method: init?.method || 'GET' })
    if (href.includes('/start-status')) {
      const next = statuses[Math.min(i, statuses.length - 1)]
      i += 1
      return { ok: true, status: 200, json: async () => next } as Response
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response
  }) as unknown as typeof fetch
  return { calls, restore: () => { global.fetch = original } }
}

test('formats elapsed time as m:ss', () => {
  expect(formatElapsed(0)).toBe('0:00')
  expect(formatElapsed(42.9)).toBe('0:42')
  expect(formatElapsed(185)).toBe('3:05')
})

test('shows every stage with the current one marked and the elapsed time', async () => {
  const server = mockServer([status({})])
  try {
    render(<SceneStartProgress sessionId="s1" onReady={jest.fn()} />)
    expect(await screen.findByText('Writing your opening')).toBeInTheDocument()
    STAGES.forEach(step => expect(screen.getByText(step.label)).toBeInTheDocument())
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(STAGES.length)
    expect(items[3]).toHaveAttribute('aria-current', 'step')
    expect(items[0]).not.toHaveAttribute('aria-current')
    expect(screen.getByText('0:42 elapsed')).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  } finally { server.restore() }
})

test('hands over to the scene as soon as the server says it is ready', async () => {
  const onReady = jest.fn()
  const server = mockServer([status({ state: 'done', scene_ready: true })])
  try {
    render(<SceneStartProgress sessionId="s1" onReady={onReady} />)
    await waitFor(() => expect(onReady).toHaveBeenCalledTimes(1))
  } finally { server.restore() }
})

test('starts a scene that nobody started, exactly once', async () => {
  const server = mockServer([status({ state: 'idle', stage: 'planning' }), status({ state: 'running' })])
  try {
    render(<SceneStartProgress sessionId="s1" onReady={jest.fn()} />)
    await waitFor(() => expect(server.calls.filter(c => c.method === 'POST' && c.url.endsWith('/sessions/s1/start'))).toHaveLength(1))
  } finally { server.restore() }
})

test('a failed start explains itself and offers to try again', async () => {
  const server = mockServer([status({ state: 'failed', error: 'model unavailable' })])
  try {
    render(<SceneStartProgress sessionId="s1" onReady={jest.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('The opening scene didn’t finish')
    expect(screen.getByText('model unavailable')).toBeInTheDocument()
    expect(screen.getByText(/won’t lose anything/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(server.calls.some(c => c.method === 'POST' && c.url.endsWith('/sessions/s1/start'))).toBe(true))
  } finally { server.restore() }
})

test('says so when the opening questions have not been answered', async () => {
  const server = mockServer([status({ state: 'needs_setup' })])
  try {
    render(<SceneStartProgress sessionId="s1" onReady={jest.fn()} />)
    expect(await screen.findByText('One more step before the story begins')).toBeInTheDocument()
    const opened = jest.fn()
    window.addEventListener('session:open-opening-setup', opened)
    fireEvent.click(screen.getByRole('button', { name: 'Continue setup' }))
    expect(opened).toHaveBeenCalledTimes(1)
    expect((opened.mock.calls[0][0] as CustomEvent).detail).toEqual({ sessionId: 's1' })
    window.removeEventListener('session:open-opening-setup', opened)
  } finally { server.restore() }
})
