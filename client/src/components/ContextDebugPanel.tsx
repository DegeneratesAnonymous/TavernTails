import React, { useState } from 'react'
import './ContextDebugPanel.css'

type Props = {
  data: {
    entity_scores?: Record<string, number>
    token_estimate?: number
    generated_at?: string
    sections?: {
      scene?: Record<string, any>
      player_character?: Record<string, any>
      recent_history?: Record<string, any>
      active_npcs?: Record<string, any>[]
      location?: Record<string, any>
      story_threads?: Record<string, any>[]
      factions?: Record<string, any>[]
      clues?: Record<string, any>
      rules?: Record<string, any>
      constraints?: Record<string, any>
    }
  }
  onClose: () => void
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.round((score / 300) * 100))
  const color = pct > 66 ? '#c8941a' : pct > 33 ? '#8ecae6' : '#666'
  return (
    <span className="cdp-score-bar">
      <span className="cdp-score-fill" style={{ width: `${pct}%`, background: color }} />
      <span className="cdp-score-val">{score}</span>
    </span>
  )
}

function SectionCard({ title, data }: { title: string; data: any }) {
  const [open, setOpen] = useState(false)
  if (!data) return null
  const isEmpty = Array.isArray(data) ? data.length === 0 : Object.values(data).every(v => !v || (Array.isArray(v) && v.length === 0))
  return (
    <div className={`cdp-section ${isEmpty ? 'cdp-section--empty' : ''}`}>
      <button className="cdp-section-header" onClick={() => setOpen(v => !v)}>
        <span>{open ? '▾' : '▸'} {title}</span>
        {isEmpty ? <span className="cdp-badge cdp-badge--empty">empty</span> : null}
      </button>
      {open ? (
        <pre className="cdp-section-body">{JSON.stringify(data, null, 2)}</pre>
      ) : null}
    </div>
  )
}

export default function ContextDebugPanel({ data, onClose }: Props) {
  const scores = data.entity_scores || {}
  const sortedScores = Object.entries(scores).sort((a, b) => b[1] - a[1])
  const sections = data.sections || {}

  return (
    <div className="cdp-root">
      <div className="cdp-header">
        <span className="cdp-title">Context Debug</span>
        <div className="cdp-header-meta">
          {data.token_estimate ? (
            <span className="cdp-badge">~{data.token_estimate} tokens</span>
          ) : null}
          {data.generated_at ? (
            <span className="cdp-badge cdp-badge--ts">{new Date(data.generated_at).toLocaleTimeString()}</span>
          ) : null}
        </div>
        <button className="cdp-close" onClick={onClose}>✕</button>
      </div>

      <div className="cdp-body">
        {/* Entity Scores */}
        {sortedScores.length > 0 ? (
          <div className="cdp-scores">
            <div className="cdp-scores-title">Entity Scores</div>
            {sortedScores.map(([name, score]) => (
              <div key={name} className="cdp-score-row">
                <span className="cdp-score-name">{name}</span>
                <ScoreBar score={score} />
              </div>
            ))}
          </div>
        ) : null}

        {/* Context Sections */}
        <div className="cdp-sections-title">Context Sections</div>
        <SectionCard title="Scene" data={sections.scene} />
        <SectionCard title="Player Character" data={sections.player_character} />
        <SectionCard title="Recent History" data={sections.recent_history} />
        <SectionCard title="Active NPCs" data={sections.active_npcs} />
        <SectionCard title="Location" data={sections.location} />
        <SectionCard title="Story Threads" data={sections.story_threads} />
        <SectionCard title="Factions" data={sections.factions} />
        <SectionCard title="Clues" data={sections.clues} />
        <SectionCard title="Rules" data={sections.rules} />
        <SectionCard title="Constraints" data={sections.constraints} />
      </div>
    </div>
  )
}
