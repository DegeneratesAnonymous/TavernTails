import React, { useCallback, useEffect, useRef, useState } from 'react'
import { addGoal, applyGoal, dismissSuggestion, fetchGoals, reviewGoals } from './goalsApi'
import type { CharacterGoals, Goal, GoalList } from './goalsApi'
import './SceneAssist.css'

type Props = { sessionId: string | null | undefined; open: boolean; onClose: () => void }

const TERM_LABEL: Record<Goal['term'], string> = { long: 'Long', mid: 'Mid', short: 'Short' }
const SUGGESTION_LABEL = { progressed: 'moved forward', done: 'looks finished', blocked: 'ran into trouble' } as const

/**
 * Everyone's goals, shared with the table. The story can suggest that a goal has moved (with the words that show
 * it); only a character's own player changes anything, and a finished goal prompts for a new one.
 */
export default function GoalsDialog({ sessionId, open, onClose }: Props) {
  const [list, setList] = useState<GoalList | null>(null)
  const [failed, setFailed] = useState(false)
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState('')
  const [adding, setAdding] = useState<{ characterId: number; term: Goal['term']; text: string; because: string } | null>(null)
  const dialog = useRef<HTMLDivElement | null>(null)
  const opener = useRef<Element | null>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  const load = useCallback(async () => {
    if (!sessionId) return
    const result = await fetchGoals(sessionId)
    if (result) { setList(result); setFailed(false) } else setFailed(true)
  }, [sessionId])

  useEffect(() => {
    if (!open) return
    setMessage('')
    setAdding(null)
    void load()
  }, [open, load])

  useEffect(() => {
    if (!open) return
    opener.current = document.activeElement
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button, input, select, [tabindex]:not([tabindex="-1"])') || [])
    focusable()[0]?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { closeRef.current(); return }
      if (e.key !== 'Tab') return
      const items = focusable()
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      if (opener.current instanceof HTMLElement) opener.current.focus()
    }
  }, [open])

  if (!open) return null

  async function check() {
    if (!sessionId) return
    setChecking(true)
    setMessage('')
    const result = await reviewGoals(sessionId)
    setChecking(false)
    if (!result) { setMessage('Could not check the story just now. Nothing was marked as checked; try again.'); return }
    await load()
    if (result.more) setMessage('There are more scenes to read. Check again to continue.')
    else if (!result.suggestions.length) setMessage('Nothing in the recent story clearly moved a goal.')
  }

  async function change(character: CharacterGoals, goal: Goal, status: Goal['status']) {
    if (!sessionId) return
    const result = await applyGoal(sessionId, { character_id: character.character_id, goal_id: goal.id, status })
    if (!result) { setMessage('Could not change that goal.'); return }
    await load()
    if (status === 'done') setAdding({ characterId: character.character_id, term: goal.term === 'short' ? 'mid' : 'long', text: '', because: '' })
  }

  async function dismiss(characterId: number, goalId: string) {
    if (!sessionId) return
    if (await dismissSuggestion(sessionId, { character_id: characterId, goal_id: goalId })) await load()
  }

  async function submitNew() {
    if (!sessionId || !adding || !adding.text.trim()) return
    const result = await addGoal(sessionId, { character_id: adding.characterId, term: adding.term, text: adding.text.trim(), because: adding.because.trim() })
    if (!result) { setMessage('Could not add that goal. You may have plenty already, or it is already on the list.'); return }
    setAdding(null)
    setMessage('')
    await load()
  }

  return (
    <div className="recap-backdrop" onClick={onClose}>
      <div className="recap-dialog goals-dialog" ref={dialog} role="dialog" aria-modal="true" aria-label="Goals" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Goals</h2>
          <button type="button" className="assist-x" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <p className="recap-empty">Everyone’s goals are shared with the table. Only you change your own.</p>
        {failed ? <p>Goals are not available right now.</p> : null}
        {!list && !failed ? <p>Loading…</p> : null}
        {list?.characters.map((c) => (
          <section key={c.character_id} aria-label={`${c.name}’s goals`}>
            <h3>{c.name}{c.you ? ' (you)' : ''}</h3>
            {c.goals.length ? (
              <ul className="goal-list">
                {c.goals.map((g) => {
                  const suggestion = list.suggestions?.find((s) => s.goal_id === g.id && s.character_id === c.character_id)
                  return (
                    <li key={g.id} className={`goal goal--${g.status}`}>
                      <span><strong>{TERM_LABEL[g.term]}:</strong> {g.text}{g.because ? `, because ${g.because}` : ''}{g.but ? `, but ${g.but}` : ''}</span>
                      {g.status !== 'active' ? <em> ({g.status === 'done' ? 'done' : 'dropped'})</em> : null}
                      {suggestion ? (
                        <p className="goal-suggestion" role="status">
                          The story suggests this {SUGGESTION_LABEL[suggestion.status]}: “{suggestion.evidence}”
                          {c.you ? <button type="button" onClick={() => void dismiss(c.character_id, g.id)}>Not really</button> : null}
                        </p>
                      ) : null}
                      {c.you ? (
                        <span className="goal-actions">
                          {g.status === 'active' ? (
                            <>
                              <button type="button" onClick={() => void change(c, g, 'done')}>Done</button>
                              <button type="button" onClick={() => void change(c, g, 'dropped')}>Drop</button>
                            </>
                          ) : <button type="button" onClick={() => void change(c, g, 'active')}>Reopen</button>}
                        </span>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            ) : <p className="recap-empty">No goals yet.</p>}
            {c.you && adding?.characterId === c.character_id ? (
              <div className="goal-new">
                <strong>What does {c.name} want next?</strong>
                <select aria-label="How long a goal" value={adding.term} onChange={(e) => setAdding({ ...adding, term: e.target.value as Goal['term'] })}>
                  <option value="short">Short</option><option value="mid">Mid</option><option value="long">Long</option>
                </select>
                <input aria-label="New goal" value={adding.text} maxLength={300} placeholder={`${c.name} wants to…`} onChange={(e) => setAdding({ ...adding, text: e.target.value })} />
                <input aria-label="Because" value={adding.because} maxLength={300} placeholder="…because" onChange={(e) => setAdding({ ...adding, because: e.target.value })} />
                <button type="button" onClick={() => void submitNew()} disabled={!adding.text.trim()}>Add goal</button>
                <button type="button" onClick={() => setAdding(null)}>Not now</button>
              </div>
            ) : c.you && !adding ? (
              <button type="button" className="goal-add" onClick={() => setAdding({ characterId: c.character_id, term: 'mid', text: '', because: '' })}>Add a goal</button>
            ) : null}
          </section>
        ))}
        {message ? <p role="status">{message}</p> : null}
        <footer>
          <button type="button" className="assist-suggest" onClick={() => void check()} disabled={checking || !list}>
            {checking ? 'Reading the story…' : `Check what changed${list && list.scenes_since_review ? ` (${list.scenes_since_review} new)` : ''}`}
          </button>
          <button type="button" className="assist-suggest" onClick={onClose}>Back to the story</button>
        </footer>
      </div>
    </div>
  )
}
