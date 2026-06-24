import React, { useState } from 'react'
import './StoryDashboard.css'

// ---- Types matching story_state.py dashboard payload ----
type StoryMetrics = { tension: number; mystery: number; danger: number; player_agency: number; thread_momentum: number; npc_activity: number; world_pressure: number }
type EmotionalState = { hope: number; fear: number; wonder: number; trust: number; urgency: number; triumph: number; curiosity: number }
type ThreadHealth = { stage: string; importance: number; health_score: number; needs_attention: boolean; scenes_since_progress: number; next_beat: string }

export type StoryDashboardData = {
  director?: {
    recommended_scene_type?: string
    scene_purpose?: string
    pacing_notes?: string
    next_story_beat?: string
    target_tension?: number
    threads_to_advance?: string[]
    spotlight_target?: string
    mystery_guidance?: string
    recommended_consequence?: string
    source?: string
  }
  story_state?: {
    scene_count?: number
    metrics?: StoryMetrics
    emotional_state?: EmotionalState
    tension_curve?: number[]
    threads?: Record<string, ThreadHealth>
    recent_scene_types?: string[]
    player_intents?: { intent: string; owner: string; status: string; priority: number }[]
    character_hooks?: { hook: string; owner: string; spotlight_recommended: boolean }[]
    setups?: { setup_id: string; description: string; payoff_due: boolean }[]
    promises?: { promise: string; importance: number }[]
    mysteries?: Record<string, { central_question: string; clues_found: string[]; clues_remaining: string[]; reveal_ready: boolean }>
    consequences?: { action: string; severity: string; consequence_due: boolean }[]
    npc_activity?: Record<string, { goal: string; last_active_scene: number; activity_recommended: boolean }>
    campaign_dna?: { themes: string[]; recurring_symbols: string[]; recurring_questions: string[]; recurring_moods: string[] }
    scene_history_summary?: { scene_number: number; scene_type: string; scene_purpose: string; tension: number; threads_advanced: string[]; story_score: number }[]
  }
  story_validator?: {
    score?: number
    passed?: boolean
    bonuses?: [string, number][]
    penalties?: [string, number][]
  }
}

type Props = {
  data: StoryDashboardData
  onClose: () => void
}

function MetricBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="sd-metric">
      <span className="sd-metric-label">{label}</span>
      <div className="sd-metric-bar">
        <div className="sd-metric-fill" style={{ width: `${value}%`, background: color }} />
        <span className="sd-metric-val">{value}</span>
      </div>
    </div>
  )
}

function EmotionChip({ name, value }: { name: string; value: number }) {
  const color = value > 70 ? '#e05252' : value > 40 ? '#c8941a' : 'rgba(255,255,255,0.55)'
  return (
    <div className="sd-emotion-chip">
      <span className="sd-emotion-name">{name.slice(0, 5)}</span>
      <span className="sd-emotion-val" style={{ color }}>{value}</span>
    </div>
  )
}

function TensionCurve({ values }: { values: number[] }) {
  if (!values.length) return null
  const max = Math.max(...values, 10)
  return (
    <div className="sd-curve">
      {values.map((v, i) => (
        <div
          key={i}
          className="sd-curve-bar"
          style={{
            height: `${Math.max(10, (v / max) * 100)}%`,
            background: v > 70 ? 'rgba(220,60,40,0.6)' : v > 40 ? 'rgba(200,148,26,0.6)' : 'rgba(60,160,80,0.55)',
          }}
          title={`Scene ${values.length - (values.length - i)}: tension ${v}`}
        />
      ))}
    </div>
  )
}

function SceneTypeChip({ type }: { type: string }) {
  const cls = `sd-pacing-chip sd-pacing-chip--${type.toLowerCase()}`
  return <span className={cls}>{type}</span>
}

function Collapsible({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div>
      <div className="sd-collapsible-header" onClick={() => setOpen(v => !v)}>
        <span className="sd-collapsible-title">{title}</span>
        <span className="sd-collapsible-chevron">{open ? '▾' : '▸'}</span>
      </div>
      {open ? children : null}
    </div>
  )
}

export default function StoryDashboard({ data, onClose }: Props) {
  const state = data.story_state || {}
  const director = data.director || {}
  const validator = data.story_validator

  const metrics = state.metrics
  const es = state.emotional_state
  const threads = state.threads || {}
  const dna = state.campaign_dna || { themes: [] as string[], recurring_symbols: [] as string[], recurring_questions: [] as string[], recurring_moods: [] as string[] }
  const historyScores = (state.scene_history_summary || []).map(s => s.story_score).filter(s => s > 0)
  const avgScore = historyScores.length ? Math.round(historyScores.reduce((a, b) => a + b, 0) / historyScores.length) : 0
  const scoreClass = avgScore >= 80 ? 'sd-health-num--good' : avgScore >= 60 ? 'sd-health-num--ok' : avgScore > 0 ? 'sd-health-num--bad' : ''

  return (
    <div className="sd-root">
      <div className="sd-header">
        <span className="sd-title">Story Dashboard</span>
        <span className="sd-scene-count">Scene #{state.scene_count ?? '—'}</span>
        <button className="sd-close" onClick={onClose}>✕</button>
      </div>

      <div className="sd-body">

        {/* Director Recommendation */}
        {director.recommended_scene_type && (
          <>
            <div className="sd-section-label">Director Recommendation</div>
            <div className="sd-director">
              <div className="sd-director-type">{director.recommended_scene_type}</div>
              {director.scene_purpose && (
                <div className="sd-director-purpose">Purpose: {director.scene_purpose}</div>
              )}
              {director.pacing_notes && (
                <div className="sd-director-note">{director.pacing_notes}</div>
              )}
              {director.next_story_beat && (
                <div className="sd-director-note" style={{ marginTop: 4, color: 'rgba(200,148,26,0.75)' }}>
                  Next beat: {director.next_story_beat}
                </div>
              )}
              {director.source && (
                <div className="sd-director-note" style={{ marginTop: 4, fontSize: 9, opacity: 0.5 }}>
                  Source: {director.source} {director.threads_to_advance?.length ? `· Advance: ${director.threads_to_advance.join(', ')}` : ''}
                </div>
              )}
            </div>
          </>
        )}

        {/* Story Health + Tension */}
        <div className="sd-section-label">Story Health</div>
        <div className="sd-health-score">
          <div>
            <div className={`sd-health-num ${scoreClass}`}>{avgScore || '—'}</div>
            <div className="sd-health-label">Avg Score</div>
          </div>
          {validator && (
            <div style={{ marginLeft: 12 }}>
              <div className={`sd-health-num ${validator.score! >= 80 ? 'sd-health-num--good' : validator.score! >= 60 ? 'sd-health-num--ok' : 'sd-health-num--bad'}`}>
                {validator.score ?? '—'}
              </div>
              <div className="sd-health-label">Last Scene</div>
            </div>
          )}
          <div style={{ flex: 1, marginLeft: 16 }}>
            {state.tension_curve?.length ? (
              <>
                <div className="sd-health-label">Tension Curve</div>
                <TensionCurve values={state.tension_curve.slice(-12)} />
              </>
            ) : null}
          </div>
        </div>

        {/* Story Metrics */}
        {metrics && (
          <>
            <div className="sd-section-label">Story Metrics</div>
            <div className="sd-metric-grid">
              <MetricBar label="Tension" value={metrics.tension} color={metrics.tension > 70 ? 'rgba(220,60,40,0.7)' : metrics.tension > 40 ? 'rgba(200,148,26,0.7)' : 'rgba(60,160,80,0.7)'} />
              <MetricBar label="Mystery" value={metrics.mystery} color="rgba(140,60,200,0.7)" />
              <MetricBar label="Danger" value={metrics.danger} color="rgba(200,80,40,0.65)" />
              <MetricBar label="Agency" value={metrics.player_agency} color="rgba(80,130,220,0.7)" />
              <MetricBar label="Momentum" value={metrics.thread_momentum} color="rgba(80,200,100,0.65)" />
              <MetricBar label="World Pressure" value={metrics.world_pressure} color="rgba(200,148,26,0.6)" />
            </div>
          </>
        )}

        {/* Emotional State */}
        {es && (
          <>
            <div className="sd-section-label">Emotional State</div>
            <div className="sd-emotion-grid">
              {(Object.entries(es) as [string, number][]).map(([name, val]) => (
                <EmotionChip key={name} name={name} value={val} />
              ))}
            </div>
          </>
        )}

        {/* Pacing Pattern */}
        {state.recent_scene_types?.length ? (
          <>
            <div className="sd-section-label">Recent Pacing</div>
            <div className="sd-pacing-row">
              {state.recent_scene_types.map((t, i) => <SceneTypeChip key={i} type={t} />)}
            </div>
          </>
        ) : null}

        {/* Story Threads */}
        {Object.keys(threads).length > 0 && (
          <Collapsible title="Story Threads" defaultOpen>
            {Object.entries(threads)
              .sort((a, b) => b[1].health_score - a[1].health_score)
              .map(([title, t]) => (
                <div key={title} className={`sd-thread ${t.needs_attention ? 'sd-thread--alert' : ''}`}>
                  <span className="sd-thread-title" title={t.next_beat || title}>{title}</span>
                  <span className="sd-thread-stage">{t.stage}</span>
                  <span className="sd-thread-imp">imp:{t.importance}</span>
                  <span className="sd-thread-health" style={{
                    color: t.health_score > 70 ? 'rgba(220,100,40,0.9)' : t.health_score > 40 ? 'rgba(200,148,26,0.8)' : 'rgba(80,200,100,0.8)'
                  }}>{t.health_score}</span>
                </div>
              ))}
          </Collapsible>
        )}

        {/* Campaign DNA */}
        {(dna.themes?.length || dna.recurring_symbols?.length) ? (
          <Collapsible title="Campaign DNA">
            {dna.themes?.length ? (
              <div style={{ padding: '4px 0' }}>
                {dna.themes.map(t => <span key={t} className="sd-tag sd-tag--dna">{t}</span>)}
              </div>
            ) : null}
            {dna.recurring_symbols?.length ? (
              <div>
                {dna.recurring_symbols.map(s => <span key={s} className="sd-tag sd-tag--symbol">{s}</span>)}
              </div>
            ) : null}
            {dna.recurring_questions?.map(q => (
              <div key={q} className="sd-list-item" style={{ fontSize: 9, marginTop: 3 }}>{q}</div>
            ))}
          </Collapsible>
        ) : null}

        {/* Mysteries */}
        {Object.keys(state.mysteries || {}).length > 0 && (
          <Collapsible title="Mysteries">
            {Object.entries(state.mysteries || {}).map(([title, m]) => (
              <div key={title} className="sd-list-item">
                <strong>{title}</strong>: {m.clues_found.length}/{m.clues_found.length + m.clues_remaining.length} clues
                {m.reveal_ready ? ' · REVEAL READY' : ''}
              </div>
            ))}
          </Collapsible>
        )}

        {/* Pending Consequences */}
        {state.consequences?.filter(c => c.consequence_due).length ? (
          <Collapsible title="Pending Consequences">
            {state.consequences!.filter(c => c.consequence_due).map((c, i) => (
              <div key={i} className="sd-list-item sd-list-item--alert">
                <span className="sd-tag sd-tag--consequence">{c.severity}</span> {c.action}
              </div>
            ))}
          </Collapsible>
        ) : null}

        {/* Setups Awaiting Payoff */}
        {state.setups?.filter(s => s.payoff_due).length ? (
          <Collapsible title="Setups Due Payoff">
            {state.setups!.filter(s => s.payoff_due).map((s, i) => (
              <div key={i} className="sd-list-item">
                <span className="sd-tag sd-tag--setup">SETUP</span> {s.description}
              </div>
            ))}
          </Collapsible>
        ) : null}

        {/* Player Intents */}
        {state.player_intents?.length ? (
          <Collapsible title="Player Intents">
            {state.player_intents.map((intent, i) => (
              <div key={i} className="sd-list-item">
                {intent.owner && <strong>{intent.owner}: </strong>}{intent.intent}
              </div>
            ))}
          </Collapsible>
        ) : null}

        {/* NPC Activity */}
        {Object.keys(state.npc_activity || {}).length > 0 && (
          <Collapsible title="NPC Activity">
            {Object.entries(state.npc_activity || {})
              .sort((a, b) => (b[1].activity_recommended ? 1 : 0) - (a[1].activity_recommended ? 1 : 0))
              .slice(0, 8)
              .map(([name, npc]) => (
                <div key={name} className="sd-npc-row">
                  <span className="sd-npc-name">{name}</span>
                  {npc.activity_recommended
                    ? <span className="sd-npc-alert">NEEDS SCENE</span>
                    : <span className="sd-npc-idle">scene {npc.last_active_scene}</span>}
                </div>
              ))}
          </Collapsible>
        )}

        {/* Story Validator Detail */}
        {validator && (validator.bonuses?.length || validator.penalties?.length) ? (
          <Collapsible title={`Story Validator (${validator.score ?? 0}${validator.passed ? ' ✓' : ' ✗'})`}>
            {validator.bonuses?.map(([label, pts], i) => (
              <div key={i} className="sd-list-item" style={{ color: 'rgba(80,200,100,0.8)' }}>+{pts} {label}</div>
            ))}
            {validator.penalties?.map(([label, pts], i) => (
              <div key={i} className="sd-list-item sd-list-item--alert">{pts} {label}</div>
            ))}
          </Collapsible>
        ) : null}

      </div>
    </div>
  )
}
