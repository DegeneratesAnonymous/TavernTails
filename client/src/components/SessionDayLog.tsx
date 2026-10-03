import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../api'
import './SessionDayLog.css'

type StoryEntry = {
  type?: string
  ts?: string
  text?: string
  roll?: {
    expression?: string
    rolls?: number[]
    mod?: number
    total?: number
    by?: string | null
  }
}

type Props = {
  sessionId?: string | null
}

function formatTime(ts?: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function entryDateKey(entry: StoryEntry): string {
  const d = entry.ts ? new Date(entry.ts) : new Date()
  if (Number.isNaN(d.getTime())) return new Date().toDateString()
  return d.toDateString()
}

function entryLabel(type?: string): string {
  const t = String(type || '').toLowerCase()
  if (t === 'player_action') return 'Action'
  if (t === 'roll') return 'Roll'
  if (t === 'narration' || t === 'narrative.scene') return 'TavernTails'
  if (t === 'note') return 'Note'
  return 'Event'
}

function cleanNarration(text: string): string {
  return text.replace(/\n\nWhat does [\s\S]+?\?$/, '').trim()
}

function typeClass(type?: string): string {
  return String(type || 'event').toLowerCase().replace(/[^a-z0-9_-]+/g, '-')
}

export default function SessionDayLog({ sessionId }: Props) {
  const [story, setStory] = useState<StoryEntry[]>([])
  const [activeTab, setActiveTab] = useState<'story' | 'player' | 'dice' | 'system'>('story')
  const [loading, setLoading] = useState(false)
  const [savingIdx, setSavingIdx] = useState<number | null>(null)
  const feedRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    if (!sessionId) {
      setStory([])
      return
    }
    setLoading(true)
    try {
      const res = await apiFetch(`/sessions/${sessionId}/file/story.json`)
      if (!res.ok) {
        setStory([])
        return
      }
      const data = await res.json().catch(() => null)
      setStory(Array.isArray(data) ? data : [])
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const handler = () => { load() }
    window.addEventListener('narrative:scene', handler)
    window.addEventListener('chat:message', handler)
    window.addEventListener('rolls:result', handler)
    return () => {
      window.removeEventListener('narrative:scene', handler)
      window.removeEventListener('chat:message', handler)
      window.removeEventListener('rolls:result', handler)
    }
  }, [load])

  const todaysEntries = useMemo(() => {
    const sorted = [...story]
      .filter(entry => entry?.text && entry.type !== 'meta')
      .sort((a, b) => String(a.ts || '').localeCompare(String(b.ts || '')))
    const todayKey = new Date().toDateString()
    const today = sorted.filter(entry => entryDateKey(entry) === todayKey)
    const base = today.length ? today : sorted.slice(-16)
    return base.filter(entry => {
      const type = String(entry.type || '').toLowerCase()
      if (activeTab === 'story') return type === 'narration' || type === 'narrative.scene' || type === 'scene'
      if (activeTab === 'player') return type === 'player_action' || type === 'note'
      if (activeTab === 'dice') return type === 'roll'
      return type !== 'narration' && type !== 'narrative.scene' && type !== 'scene' && type !== 'player_action' && type !== 'note' && type !== 'roll'
    })
  }, [activeTab, story])

  useEffect(() => {
    if (!feedRef.current) return
    feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [todaysEntries.length])

  const markNoteworthy = useCallback(async (entry: StoryEntry, idx: number) => {
    if (!sessionId || !entry.text) return
    setSavingIdx(idx)
    try {
      const text = cleanNarration(entry.text).slice(0, 900)
      await apiFetch('/notes/log', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, notes: [`Noteworthy: ${text}`] }),
      })
      window.dispatchEvent(new CustomEvent('journal:refresh'))
    } finally {
      setSavingIdx(null)
    }
  }, [sessionId])

  if (!sessionId) return null

  return (
    <section className="daylog-root" aria-label="Today's session chronicle">
      <div className="daylog-header">
        <div>
          <div className="daylog-title">Today</div>
          <div className="daylog-subtitle">Actions, rolls, and narration</div>
        </div>
        <button className="daylog-refresh" type="button" onClick={load} disabled={loading} title="Refresh">
          {loading ? '...' : '↻'}
        </button>
      </div>
      <div className="daylog-tabs" role="tablist" aria-label="Session log sections">
        {([
          ['story', 'Story'],
          ['player', 'Player'],
          ['dice', 'Dice'],
          ['system', 'System'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={activeTab === key}
            className={`daylog-tab ${activeTab === key ? 'active' : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="daylog-feed" ref={feedRef}>
        {todaysEntries.length ? todaysEntries.map((entry, idx) => {
          const type = String(entry.type || '').toLowerCase()
          const text = cleanNarration(entry.text || '')
          return (
            <article key={`${entry.ts || idx}-${idx}`} className={`daylog-entry daylog-entry--${typeClass(type)}`}>
              <div className="daylog-entry-meta">
                <span>{entryLabel(type)}</span>
                {entry.ts ? <time>{formatTime(entry.ts)}</time> : null}
                <button
                  type="button"
                  className="daylog-note-btn"
                  onClick={() => markNoteworthy(entry, idx)}
                  disabled={savingIdx === idx}
                >
                  {savingIdx === idx ? 'Saving' : 'Note'}
                </button>
              </div>
              <div className="daylog-entry-text">{text}</div>
            </article>
          )
        }) : (
          <div className="daylog-empty">The day’s chronicle will appear here as play unfolds.</div>
        )}
      </div>
    </section>
  )
}
