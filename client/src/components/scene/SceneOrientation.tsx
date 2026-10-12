import React from 'react'
import type { RoundRecap, SceneView } from './sceneAssistApi'
import './SceneAssist.css'

type Props = {
  view?: SceneView | null
  /** What the table did last round, kept with the scene it led to. */
  recap?: RoundRecap | null
  /** What this player's character picks up on; private to them. */
  notice?: string
  /** Names the current player acts under, so only their own actions offer a clarification. */
  mine?: string[]
  onClarify?: (text: string) => void
}

/** Who is here and the one question the scene leaves open. Information only: nothing here suggests an action. */
export function SceneFacts({ view }: { view?: SceneView | null }) {
  const people = view?.present || []
  const hook = (view?.hook || '').trim()
  if (!people.length && !hook) return null
  return (
    <div className="scene-facts">
      {people.length > 0 ? (
        <ul className="scene-present" aria-label="Who is here">
          {people.map(p => (
            <li key={p.name} className="scene-person" title={p.seen || undefined}>
              <strong>{p.name}</strong>
              {p.role ? <span>{p.role}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {hook ? (
        <p className="scene-hook">
          <span className="scene-hook-label">Unanswered</span> {hook}
        </p>
      ) : null}
    </div>
  )
}

/** "What you did" for the round that led to this scene, so every action visibly mattered. */
export function RoundRecapStrip({ recap, mine = [], onClarify }: { recap?: RoundRecap | null; mine?: string[]; onClarify?: (text: string) => void }) {
  const actions = recap?.actions || []
  const rolls = recap?.rolls || []
  if (!actions.length && !rolls.length) return null
  const own = mine.map(n => n.trim().toLowerCase()).filter(Boolean)
  return (
    <details className="scene-recap">
      <summary>Last round · {actions.length} {actions.length === 1 ? 'action' : 'actions'}{rolls.length ? ` · ${rolls.length} ${rolls.length === 1 ? 'roll' : 'rolls'}` : ''}</summary>
      <ul>
        {actions.map((a, i) => (
          <li key={`a-${i}`}>
            <strong>{a.by}</strong> {a.text}
            {onClarify && own.includes(a.by.trim().toLowerCase()) ? (
              <button type="button" className="scene-recap-fix" onClick={() => onClarify(`To be clear, I meant: ${a.text}`)}>
                Not what I meant
              </button>
            ) : null}
          </li>
        ))}
        {rolls.map((r, i) => (
          <li key={`r-${i}`} className="scene-recap-roll">
            <strong>{r.by}</strong> rolled {r.expression || 'a die'}{r.total != null ? `: ${r.total}` : ''}
          </li>
        ))}
      </ul>
    </details>
  )
}

export default function SceneOrientation({ view, recap, notice, mine, onClarify }: Props) {
  return (
    <div className="scene-orientation">
      <SceneFacts view={view} />
      {notice ? <p className="scene-notice" aria-label="What you notice">{notice}</p> : null}
      <RoundRecapStrip recap={recap} mine={mine} onClarify={onClarify} />
    </div>
  )
}
