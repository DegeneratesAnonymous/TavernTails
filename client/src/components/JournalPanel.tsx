import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '../api'
import './JournalPanel.css'

type StoryEntry = {
  type?: string
  ts?: string
  text?: string
}

type Props = {
  sessionId?: string | null
}

const TYPE_COLORS: Record<string, string> = {
  narration: '#c8941a',
  scene:     '#5b9fd4',
  note:      '#4caf82',
  roll:      '#9b59b6',
  system:    'rgba(255,255,255,0.3)',
}

function typeColor(t?: string): string {
  if (!t) return TYPE_COLORS.system
  return TYPE_COLORS[t.toLowerCase()] ?? TYPE_COLORS.system
}

function formatTs(ts?: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  return sameDay
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function JournalPanel({ sessionId }: Props) {
  const [story, setStory] = useState<StoryEntry[]>([])
  const [notesMd, setNotesMd] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [noteDraft, setNoteDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const feedRef = useRef<HTMLDivElement | null>(null)

  const canLoad = Boolean(sessionId)

  const load = useCallback(async () => {
    if (!sessionId) { setStory([]); setNotesMd(''); return }
    setLoading(true)
    setError(null)
    try {
      const [storyRes, notesRes] = await Promise.all([
        apiFetch(`/sessions/${sessionId}/file/story.json`),
        apiFetch(`/sessions/${sessionId}/file/notes.md`),
      ])
      if (storyRes.ok) {
        const data = await storyRes.json().catch(() => null)
        setStory(Array.isArray(data) ? data : [])
      } else { setStory([]) }
      if (notesRes.ok) {
        const data = await notesRes.json().catch(() => null)
        setNotesMd(typeof data?.content === 'string' ? data.content : '')
      } else { setNotesMd('') }
    } catch (e: any) {
      setError(e?.message || 'Failed to load journal')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { load() }, [load])

  // Scroll feed to bottom when entries change
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [story])

  const sortedStory = useMemo(() => {
    const list = Array.isArray(story) ? [...story] : []
    const hasTs = list.some((e) => typeof e?.ts === 'string' && e.ts)
    if (!hasTs) return list
    return list.sort((a, b) => String(a?.ts || '').localeCompare(String(b?.ts || '')))
  }, [story])

  const addNote = useCallback(async () => {
    const value = noteDraft.trim()
    if (!value || !sessionId) return
    setSaving(true)
    setError(null)
    try {
      const res = await apiFetch('/notes/log', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, notes: [value] }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || `Failed to save note (${res.status})`)
      }
      setNoteDraft('')
      await load()
    } catch (e: any) {
      setError(e?.message || 'Failed to save note')
    } finally {
      setSaving(false)
    }
  }, [load, noteDraft, sessionId])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      addNote()
    }
  }

  return (
    <div className="jrnl-root">

      {/* Header */}
      <div className="jrnl-header">
        <span className="jrnl-title">Journal</span>
        <button
          className="jrnl-refresh"
          type="button"
          onClick={load}
          disabled={!canLoad || loading}
          title="Refresh journal"
          aria-label="Refresh"
        >
          {loading ? '…' : '↺'}
        </button>
      </div>

      {error ? <div className="jrnl-error">{error}</div> : null}

      {!canLoad ? (
        <div className="jrnl-empty">Select a session to view the journal.</div>
      ) : null}

      {/* Story feed */}
      {sortedStory.length > 0 ? (
        <div className="jrnl-feed" ref={feedRef}>
          {sortedStory.map((entry, idx) => {
            const color = typeColor(entry?.type)
            return (
              <div key={`${entry?.ts || 'e'}-${idx}`} className="jrnl-entry" style={{ borderLeftColor: color }}>
                <div className="jrnl-entry-meta">
                  {entry?.type ? <span className="jrnl-entry-type" style={{ color }}>{entry.type}</span> : null}
                  {entry?.ts ? <span className="jrnl-entry-ts">{formatTs(entry.ts)}</span> : null}
                </div>
                {entry?.text ? <div className="jrnl-entry-text">{entry.text}</div> : null}
              </div>
            )
          })}
        </div>
      ) : canLoad ? (
        <div className="jrnl-empty">No session events yet.</div>
      ) : null}

      {/* Notes from notes.md */}
      {notesMd ? (
        <div className="jrnl-notes-block">
          <div className="jrnl-notes-label">Notes</div>
          <div className="jrnl-notes-content">{notesMd}</div>
        </div>
      ) : null}

      {/* Composer */}
      {canLoad ? (
        <div className="jrnl-composer">
          <textarea
            className="jrnl-composer-input"
            rows={2}
            placeholder="Add a note… (⌘Enter to save)"
            value={noteDraft}
            onChange={(e) => setNoteDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={saving}
          />
          <button
            className="jrnl-composer-btn"
            type="button"
            onClick={addNote}
            disabled={saving || !noteDraft.trim()}
          >
            {saving ? '…' : 'Add'}
          </button>
        </div>
      ) : null}

    </div>
  )
}
