import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import ActionAssist from './ActionAssist'
import RecapDialog from './RecapDialog'
import { RoundRecapStrip, SceneFacts } from './SceneOrientation'
import NarrativeView from '../NarrativeView'
import { AWAY_MS, markSeen, shouldShowRecap } from './sceneAssistApi'

type Handler = (init?: RequestInit) => unknown
type Routes = Record<string, Handler | unknown>

/** Answers fetches by URL fragment; records every call so a test can say what was (not) requested. */
function mockFetch(routes: Routes) {
  const calls: { url: string; method: string; body?: string }[] = []
  const original = global.fetch
  global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const href = String(url)
    calls.push({ url: href, method: init?.method || 'GET', body: typeof init?.body === 'string' ? init.body : undefined })
    const key = Object.keys(routes).find(k => href.includes(k))
    const value = key ? routes[key] : {}
    const body = typeof value === 'function' ? (value as Handler)(init) : value
    return { ok: true, status: 200, json: async () => body } as Response
  }) as unknown as typeof fetch
  return { calls, restore: () => { global.fetch = original } }
}

const ROUND = { members: [], waiting_on: [], quiet: [], all_ready: false, paused: false, avoid: [] }

beforeEach(() => window.localStorage.clear())

describe('who is here and what is open', () => {
  test('people and the open question are shown as plain information, never as actions', () => {
    render(<SceneFacts view={{ present: [{ name: 'Ada Reed', role: 'clerk', seen: 'Ada Reed leans over a desk.' }], hook: 'What is behind the bricked-up ward?' }} />)
    expect(screen.getByLabelText('Who is here')).toHaveTextContent('Ada Reed')
    expect(screen.getByLabelText('Who is here')).toHaveTextContent('clerk')
    expect(screen.getByText(/What is behind the bricked-up ward\?/)).toBeInTheDocument()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  test('nothing is drawn when the scene has neither', () => {
    const { container } = render(<SceneFacts view={{ present: [] }} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('last round', () => {
  const recap = { actions: [{ by: 'Arin', text: 'I check the records.' }, { by: 'Mox', text: 'I follow the cart.' }], rolls: [{ by: 'Arin', expression: '1d20', total: 17 }] }

  test('shows what the table did and rolled', () => {
    render(<RoundRecapStrip recap={recap} />)
    expect(screen.getByText(/I check the records\./)).toBeInTheDocument()
    expect(screen.getByText(/rolled 1d20: 17/)).toBeInTheDocument()
  })

  test('only your own actions offer "Not what I meant", which puts a clarification in your text box', () => {
    const onClarify = jest.fn()
    render(<RoundRecapStrip recap={recap} mine={['arin']} onClarify={onClarify} />)
    const buttons = screen.getAllByRole('button', { name: 'Not what I meant' })
    expect(buttons).toHaveLength(1)
    fireEvent.click(buttons[0])
    expect(onClarify).toHaveBeenCalledWith('To be clear, I meant: I check the records.')
  })
})

describe('the Suggest button', () => {
  function setup(value = '', extra: Partial<React.ComponentProps<typeof ActionAssist>> = {}, routes: Routes = {}) {
    const onFill = jest.fn()
    const server = mockFetch({ '/round': ROUND, '/suggest-action': { suggestion: 'I ask Ada Reed what she has noticed.' }, ...routes })
    window.localStorage.setItem('tt:hint-dismissed', '1')
    const view = render(<ActionAssist sessionId="s1" value={value} onFill={onFill} idleNudgeMs={0} {...extra} />)
    return { onFill, server, ...view }
  }

  test('nothing is suggested until the player asks', async () => {
    const { server } = setup()
    await screen.findByRole('button', { name: 'Suggest' })
    expect(server.calls.some(c => c.url.includes('/suggest-action'))).toBe(false)
    expect(screen.queryByText(/Ada Reed/)).not.toBeInTheDocument()
    server.restore()
  })

  test('pressing it puts one idea in the text box', async () => {
    const { onFill, server } = setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest' }))
    await waitFor(() => expect(onFill).toHaveBeenCalledWith('I ask Ada Reed what she has noticed.'))
    server.restore()
  })

  test('it never overwrites what the player has typed; it offers the idea instead', async () => {
    const { onFill, server } = setup('I pick the lock')
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest' }))
    expect(await screen.findByText(/Idea: I ask Ada Reed/)).toBeInTheDocument()
    expect(onFill).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Use this instead' }))
    expect(onFill).toHaveBeenCalledWith('I ask Ada Reed what she has noticed.')
    server.restore()
  })

  test('asking again tells the server what was already offered', async () => {
    let n = 0
    const { server } = setup('', {}, { '/suggest-action': () => ({ suggestion: `idea ${++n}` }) })
    const button = await screen.findByRole('button', { name: 'Suggest' })
    fireEvent.click(button)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Suggest' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'Suggest' }))
    await waitFor(() => expect(server.calls.filter(c => c.url.includes('/suggest-action'))).toHaveLength(2))
    const second = server.calls.filter(c => c.url.includes('/suggest-action'))[1]
    expect(JSON.parse(second.body || '{}').previous).toEqual(['idea 1'])
    server.restore()
  })

  test('a failed request says so and leaves the box alone', async () => {
    const { onFill, server } = setup('', {}, { '/suggest-action': { suggestion: '' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/No idea came to mind/)
    expect(onFill).not.toHaveBeenCalled()
    server.restore()
  })

  test('the player can turn the button off, and the choice is remembered', async () => {
    const { server } = setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Table' }))
    fireEvent.click(screen.getByLabelText('Show the Suggest button'))
    expect(screen.queryByRole('button', { name: 'Suggest' })).not.toBeInTheDocument()
    expect(window.localStorage.getItem('tt:suggest')).toBe('0')
    server.restore()
  })
})

describe('a suggestion belongs to the scene it was asked for', () => {
  test('one that arrives after the scene changed is discarded, not put in the new scene\'s box', async () => {
    window.localStorage.setItem('tt:hint-dismissed', '1')
    let release: (v: unknown) => void = () => {}
    const slow = new Promise(resolve => { release = resolve })
    const original = global.fetch
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes('/suggest-action')) { await slow; return { ok: true, status: 200, json: async () => ({ suggestion: 'I ask about the old scene.' }) } as Response }
      return { ok: true, status: 200, json: async () => ROUND } as Response
    }) as unknown as typeof fetch
    const onFill = jest.fn()
    const { rerender } = render(<ActionAssist sessionId="s1" value="" onFill={onFill} sceneKey="a" idleNudgeMs={0} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest' }))
    rerender(<ActionAssist sessionId="s1" value="" onFill={onFill} sceneKey="b" idleNudgeMs={0} />)
    await act(async () => { release(null); await slow })
    expect(onFill).not.toHaveBeenCalled()
    global.fetch = original
  })

  test('the character the player is acting as is sent with the request', async () => {
    window.localStorage.setItem('tt:hint-dismissed', '1')
    const server = mockFetch({ '/round': ROUND, '/suggest-action': { suggestion: 'I look around.' } })
    render(<ActionAssist sessionId="s1" value="" onFill={() => {}} idleNudgeMs={0} characterId={42} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest' }))
    await waitFor(() => expect(server.calls.some(c => c.url.includes('/suggest-action'))).toBe(true))
    expect(JSON.parse(server.calls.find(c => c.url.includes('/suggest-action'))?.body || '{}').character_id).toBe(42)
    server.restore()
  })
})

describe('guidance', () => {
  test('a first-time tip explains the box, and stays dismissed', async () => {
    const server = mockFetch({ '/round': ROUND })
    const { unmount } = render(<ActionAssist sessionId="s1" value="" onFill={() => {}} idleNudgeMs={0} />)
    expect(screen.getByText(/Say what you do in your own words/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Dismiss tip'))
    expect(screen.queryByText(/Say what you do in your own words/)).not.toBeInTheDocument()
    unmount()
    render(<ActionAssist sessionId="s1" value="" onFill={() => {}} idleNudgeMs={0} />)
    expect(screen.queryByText(/Say what you do in your own words/)).not.toBeInTheDocument()
    await act(async () => { await Promise.resolve() })
    server.restore()
  })

  test('someone staring at an empty box gets a gentle nudge, and typing removes it', async () => {
    jest.useFakeTimers()
    window.localStorage.setItem('tt:hint-dismissed', '1')
    const server = mockFetch({ '/round': ROUND })
    const { rerender } = render(<ActionAssist sessionId="s1" value="" onFill={() => {}} idleNudgeMs={5000} />)
    await act(async () => { await Promise.resolve() }) // the first look at the table settles
    expect(screen.queryByText(/Not sure what to try/)).not.toBeInTheDocument()
    act(() => { jest.advanceTimersByTime(5100) })
    expect(screen.getByText(/Not sure what to try/)).toBeInTheDocument()
    rerender(<ActionAssist sessionId="s1" value="I" onFill={() => {}} idleNudgeMs={5000} />)
    expect(screen.queryByText(/Not sure what to try/)).not.toBeInTheDocument()
    server.restore()
    jest.useRealTimers()
  })
})

describe('the table', () => {
  test('says who has not yet said what they do, and who the table is waiting for', async () => {
    window.localStorage.setItem('tt:hint-dismissed', '1')
    const server = mockFetch({ '/round': { ...ROUND, quiet: ['Mox'], waiting_on: ['Mox', 'Arin'] } })
    const { rerender } = render(<ActionAssist sessionId="s1" value="" onFill={() => {}} idleNudgeMs={0} />)
    expect(await screen.findByText("Mox hasn't said what they do yet")).toBeInTheDocument()
    rerender(<ActionAssist sessionId="s1" value="" onFill={() => {}} idleNudgeMs={0} playerReady />)
    expect(await screen.findByText('Waiting on Mox, Arin')).toBeInTheDocument()
    server.restore()
  })

  test('any player can pause, ask to skip something, and see when the table is paused', async () => {
    window.localStorage.setItem('tt:hint-dismissed', '1')
    let paused = false
    const server = mockFetch({
      '/round': () => ({ ...ROUND, paused }),
      '/table-safety': (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body || '{}'))
        paused = body.kind === 'pause'
        return { ok: true, paused, message: body.kind === 'pause' ? 'You paused the table.' : 'You asked the story to leave that out.' }
      },
    })
    render(<ActionAssist sessionId="s1" value="" onFill={() => {}} idleNudgeMs={0} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Table' }))
    fireEvent.change(screen.getByPlaceholderText('What should the story avoid?'), { target: { value: 'spiders' } })
    fireEvent.click(screen.getByRole('menuitem', { name: 'Skip this' }))
    expect(await screen.findByText('You asked the story to leave that out.')).toBeInTheDocument()
    expect(JSON.parse(server.calls.filter(c => c.url.includes('/table-safety'))[0].body || '{}')).toEqual({ kind: 'skip', topic: 'spiders' })
    fireEvent.click(screen.getByRole('button', { name: 'Table' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Pause the table' }))
    expect(await screen.findByText('The table is paused.')).toBeInTheDocument()
    server.restore()
  })
})

describe('coming back', () => {
  test('a recap is offered only after a long absence', () => {
    const now = Date.now()
    expect(shouldShowRecap('s1', now)).toBe(false) // first visit
    markSeen('s1', now - AWAY_MS - 1000)
    expect(shouldShowRecap('s1', now)).toBe(true)
    markSeen('s1', now - 60 * 1000)
    expect(shouldShowRecap('s1', now)).toBe(false)
  })

  test('the recap says what happened, where things stand and what is open, and closes on Escape', async () => {
    const server = mockFetch({
      '/recap': {
        title: 'Grimward', previously: ['Arin reached the gate at dawn.', 'A bell rang twice.'], right_now: 'Ada Reed traces a page.',
        place: 'Records room', present: [{ name: 'Ada Reed', role: 'clerk' }], open_question: 'What is behind the ward?',
      },
    })
    const onClose = jest.fn()
    render(<RecapDialog sessionId="s1" open onClose={onClose} />)
    expect(await screen.findByText('Arin reached the gate at dawn.')).toBeInTheDocument()
    expect(screen.getByText('A bell rang twice.')).toBeInTheDocument()
    expect(screen.getByText('Ada Reed traces a page.')).toBeInTheDocument()
    expect(screen.getByText(/Here: Ada Reed \(clerk\)/)).toBeInTheDocument()
    expect(screen.getByText(/What is behind the ward\?/)).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
    server.restore()
  })

  test('focus moves into the dialog, stays there, and returns to what opened it', async () => {
    const server = mockFetch({ '/recap': { previously: ['One.'], present: [] } })
    const Host = () => {
      const [open, setOpen] = React.useState(false)
      return (<><button type="button" onClick={() => setOpen(true)}>Open recap</button><RecapDialog sessionId="s1" open={open} onClose={() => setOpen(false)} /></>)
    }
    render(<Host />)
    const trigger = screen.getByRole('button', { name: 'Open recap' })
    trigger.focus()
    fireEvent.click(trigger)
    const close = await screen.findByRole('button', { name: 'Close' })
    expect(close).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('button', { name: 'Back to the story' })).toHaveFocus() // wraps, never reaches the page behind
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(trigger).toHaveFocus())
    server.restore()
  })

  test('says so plainly when the recap is unavailable', async () => {
    const original = global.fetch
    global.fetch = jest.fn(async () => ({ ok: false, status: 500, json: async () => ({}) } as Response)) as unknown as typeof fetch
    render(<RecapDialog sessionId="s1" open onClose={() => {}} />)
    expect(await screen.findByText(/recap is not available/)).toBeInTheDocument()
    global.fetch = original
  })
})

describe('the scene on screen', () => {
  const SCENE = {
    id: 'scene-1', title: 'Records', location: 'Grimward Asylum', time_of_day: 'day', weather: 'clear',
    narrative_body: 'The scent of wet ink hangs over the records room.\n\nAda Reed leans over a desk.',
    player_prompt: 'What does Arin do?', choices: [{ id: 'a', label: 'Inspect the clue' }, { id: 'b', label: 'Question the clerk' }],
    suggested_actions: ['Inspect the clue'],
    scene_view: { present: [{ name: 'Ada Reed', role: 'clerk' }], hook: 'What is behind the bricked-up ward?' },
    round_recap: { actions: [{ by: 'Arin', text: 'I check the records.' }] },
  }

  function openScene() {
    return mockFetch({
      '/file/scene.json': SCENE,
      '/notice': { notice: 'You notice how Ada Reed keeps one hand flat on the page.' },
    })
  }

  test('shows where, who and what is open — and no list of choices', async () => {
    const server = openScene()
    render(<NarrativeView sessionId="s1" entities={[]} presentationMode="play" mine={['Arin']} />)
    expect(await screen.findByText(/scent of wet ink/)).toBeInTheDocument()
    expect(screen.getByLabelText('Who is here')).toHaveTextContent('Ada Reed')
    expect(screen.getByText(/What is behind the bricked-up ward\?/)).toBeInTheDocument()
    expect(screen.getByText(/I check the records\./)).toBeInTheDocument()
    expect(screen.queryByText(/Show choices/)).not.toBeInTheDocument()
    expect(screen.queryByText('Inspect the clue')).not.toBeInTheDocument()
    expect(screen.queryByText('Question the clerk')).not.toBeInTheDocument()
    server.restore()
  })

  test('"Previously" asks for the recap', async () => {
    const server = openScene()
    const heard = jest.fn()
    window.addEventListener('narrative:recap', heard)
    render(<NarrativeView sessionId="s1" entities={[]} presentationMode="play" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Previously' }))
    expect(heard).toHaveBeenCalled()
    window.removeEventListener('narrative:recap', heard)
    server.restore()
  })

  test('tells the player what their character notices', async () => {
    const server = openScene()
    render(<NarrativeView sessionId="s1" entities={[]} presentationMode="play" />)
    expect(await screen.findByLabelText('What you notice')).toHaveTextContent('You notice how Ada Reed keeps one hand flat on the page.')
    server.restore()
  })

  test('text size can be changed and is remembered', async () => {
    const server = openScene()
    render(<NarrativeView sessionId="s1" entities={[]} presentationMode="play" />)
    const paragraph = await screen.findByText(/scent of wet ink/)
    expect(paragraph).toHaveStyle({ fontSize: '15.5px' })
    fireEvent.click(screen.getByRole('button', { name: 'Larger text' }))
    expect(screen.getByText(/scent of wet ink/)).toHaveStyle({ fontSize: '18px' })
    expect(window.localStorage.getItem('tt:text-size')).toBe('l')
    fireEvent.click(screen.getByRole('button', { name: 'Smaller text' }))
    fireEvent.click(screen.getByRole('button', { name: 'Smaller text' }))
    expect(screen.getByRole('button', { name: 'Smaller text' })).toBeDisabled()
    server.restore()
  })
})
