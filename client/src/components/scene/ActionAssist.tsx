import React, { useCallback, useEffect, useRef, useState } from 'react'
import { fetchRound, fetchSuggestion, postSafety, store } from './sceneAssistApi'
import type { RoundStatus, SafetyKind } from './sceneAssistApi'
import './SceneAssist.css'

const HINT_KEY = 'tt:hint-dismissed'
const SUGGEST_KEY = 'tt:suggest'
const ROUND_POLL_MS = 6000

type Props = {
  sessionId: string | null | undefined
  /** The text box's current content: a suggestion never overwrites something the player has typed. */
  value: string
  onFill: (text: string) => void
  /** Changes when a new scene arrives, so earlier suggestions and the idle timer start over. */
  sceneKey?: string
  playerReady?: boolean
  /** How long an empty box can sit before a gentle "not sure what to try?" appears. */
  idleNudgeMs?: number
  /** Forces the button off; otherwise the player's own choice in the Table menu decides. */
  showSuggest?: boolean
}

/**
 * What sits above the player's text box. It never lists actions: an idea appears only when the player presses
 * Suggest, and then it goes into their own box where they can change it or ignore it.
 */
export default function ActionAssist({ sessionId, value, onFill, sceneKey = '', playerReady = false, idleNudgeMs = 90000, showSuggest: allowSuggest = true }: Props) {
  const [hintOpen, setHintOpen] = useState(() => store.get(HINT_KEY) !== '1')
  const [suggestOn, setSuggestOn] = useState(() => store.get(SUGGEST_KEY) !== '0')
  const showSuggest = allowSuggest && suggestOn
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [offered, setOffered] = useState('')
  const [nudge, setNudge] = useState(false)
  const [round, setRound] = useState<RoundStatus | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [topic, setTopic] = useState('')
  const [note, setNote] = useState('')
  const previous = useRef<string[]>([])
  const lastFilled = useRef('')
  const valueRef = useRef(value)
  valueRef.current = value

  // A new scene: forget the suggestions made for the old one.
  useEffect(() => {
    previous.current = []
    lastFilled.current = ''
    setOffered('')
    setError('')
    setNudge(false)
  }, [sceneKey])

  // Gentle nudge for someone staring at an empty box.
  useEffect(() => {
    if (!sessionId || value.trim() || !idleNudgeMs) {
      setNudge(false)
      return
    }
    const timer = window.setTimeout(() => setNudge(true), idleNudgeMs)
    return () => window.clearTimeout(timer)
  }, [sessionId, value, sceneKey, idleNudgeMs])

  // Who the table is waiting for.
  useEffect(() => {
    if (!sessionId) return
    let alive = true
    const load = async () => {
      if (typeof document !== 'undefined' && document.hidden) return
      const next = await fetchRound(sessionId)
      if (alive && next) setRound(next)
    }
    void load()
    const timer = window.setInterval(load, ROUND_POLL_MS)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [sessionId, sceneKey])

  const suggest = useCallback(async () => {
    if (!sessionId || busy) return
    setBusy(true)
    setError('')
    const result = await fetchSuggestion(sessionId, previous.current)
    setBusy(false)
    const text = (result?.suggestion || '').trim()
    if (!text) {
      setError('No idea came to mind right now. Try again in a moment.')
      return
    }
    previous.current = [...previous.current, text].slice(-6)
    const current = valueRef.current
    if (!current.trim() || current === lastFilled.current) {
      lastFilled.current = text
      setOffered('')
      onFill(text)
    } else {
      setOffered(text) // they have typed their own: offer, never overwrite
    }
    setNudge(false)
  }, [sessionId, busy, onFill])

  const useOffered = () => {
    lastFilled.current = offered
    onFill(offered)
    setOffered('')
  }

  const dismissHint = () => {
    store.set(HINT_KEY, '1')
    setHintOpen(false)
  }

  const sendSafety = async (kind: SafetyKind) => {
    if (!sessionId) return
    const result = await postSafety(sessionId, kind, kind === 'skip' || kind === 'soften' ? topic : '')
    setNote(result?.message || (kind === 'resume' ? 'Only the table owner can resume.' : 'Could not reach the table. Try again.'))
    setMenuOpen(false)
    setTopic('')
    const next = await fetchRound(sessionId)
    if (next) setRound(next)
  }

  const waiting = (round?.waiting_on || []).filter(Boolean)
  const quiet = (round?.quiet || []).filter(Boolean)
  const paused = !!round?.paused

  return (
    <div className="action-assist">
      {paused ? (
        <div className="assist-paused" role="status">
          <span>The table is paused.</span>
          <button type="button" onClick={() => sendSafety('resume')}>Resume</button>
        </div>
      ) : null}
      {hintOpen ? (
        <p className="assist-hint">
          Say what you do in your own words. Stuck? Press <strong>Suggest</strong> for an idea.
          <button type="button" className="assist-x" aria-label="Dismiss tip" onClick={dismissHint}>×</button>
        </p>
      ) : null}
      {nudge && showSuggest && !hintOpen ? <p className="assist-nudge">Not sure what to try? Press Suggest for an idea.</p> : null}
      {offered ? (
        <p className="assist-offered">
          Idea: {offered}{' '}
          <button type="button" onClick={useOffered}>Use this instead</button>
        </p>
      ) : null}
      {error ? <p className="assist-error" role="alert">{error}</p> : null}
      {note ? <p className="assist-note" role="status">{note}</p> : null}
      <div className="assist-row">
        {showSuggest ? (
          <button type="button" className="assist-suggest" onClick={suggest} disabled={!sessionId || busy}>
            {busy ? 'Thinking…' : 'Suggest'}
          </button>
        ) : null}
        <span className="assist-status" aria-live="polite">
          {playerReady && waiting.length ? `Waiting on ${waiting.join(', ')}` : !playerReady && quiet.length ? `${quiet.join(', ')} ${quiet.length === 1 ? "hasn't" : "haven't"} said what they do yet` : ''}
        </span>
        <span className="assist-menu-wrap">
          <button type="button" className="assist-table" aria-expanded={menuOpen} onClick={() => setMenuOpen(o => !o)}>Table</button>
          {menuOpen ? (
            <div className="assist-menu" role="menu" aria-label="Table safety">
              <button type="button" role="menuitem" onClick={() => sendSafety('pause')}>Pause the table</button>
              <label>
                <span>Leave out (optional)</span>
                <input value={topic} maxLength={120} onChange={e => setTopic(e.target.value)} placeholder="What should the story avoid?" />
              </label>
              <button type="button" role="menuitem" onClick={() => sendSafety('skip')}>Skip this</button>
              <button type="button" role="menuitem" onClick={() => sendSafety('soften')}>Soften this</button>
              <label className="assist-check">
                <input
                  type="checkbox"
                  checked={suggestOn}
                  onChange={e => { setSuggestOn(e.target.checked); store.set(SUGGEST_KEY, e.target.checked ? '1' : '0') }}
                />
                <span>Show the Suggest button</span>
              </label>
            </div>
          ) : null}
        </span>
      </div>
    </div>
  )
}
