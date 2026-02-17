import React, { useCallback, useEffect, useMemo, useState } from 'react'
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

function formatTimestamp(ts?: string) {
  if (!ts) return ''
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return ts
  return date.toLocaleString()
}

export default function JournalPanel({ sessionId }: Props) {
  const [story, setStory] = useState<StoryEntry[]>([])
  const [notesMd, setNotesMd] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [noteDraft, setNoteDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const canLoad = Boolean(sessionId)

  const load = useCallback(async () => {
    if (!sessionId) {
      setStory([])
      setNotesMd('')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const [storyRes, notesRes] = await Promise.all([
        apiFetch(`/sessions/${sessionId}/file/story.json`),
        apiFetch(`/sessions/${sessionId}/file/notes.md`),
      ])

      if (storyRes.ok) {
        const data = await storyRes.json().catch(() => null)
        const entries = Array.isArray(data) ? data : []
        setStory(entries)
      } else {
        setStory([])
      }

      if (notesRes.ok) {
        const data = await notesRes.json().catch(() => null)
        const content = typeof data?.content === 'string' ? data.content : ''
        setNotesMd(content)
      } else {
        setNotesMd('')
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to load journal')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    load()
  }, [load])

  const sortedStory = useMemo(() => {
    const list = Array.isArray(story) ? [...story] : []
    // Preserve insertion order by default, but if timestamps exist, sort by ts.
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

  return (
    <div className="journal-root" aria-label="Journal">
      {!canLoad ? (
        <div className="journal-empty">Select a session to view the journal.</div>
      ) : null}

      {error ? <div className="inline-alert inline-alert-error">{error}</div> : null}

      <div className="journal-toolbar">
        <button className="btn btn-secondary" type="button" onClick={load} disabled={!canLoad || loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="journal-section">
        <div className="journal-section-title">Player Notes</div>
        <div className="journal-note-row">
          <textarea
            className="journal-note-input"
            rows={3}
            placeholder="Add a quick note (what happened, what we decided, loose ends)…"
            value={noteDraft}
            onChange={(e) => setNoteDraft(e.target.value)}
            disabled={!canLoad || saving}
          />
          <button className="btn" type="button" onClick={addNote} disabled={!canLoad || saving || !noteDraft.trim()}>
            {saving ? 'Saving…' : 'Add'}
          </button>
        </div>

        <pre className="journal-notes">{notesMd || '(No notes yet)'}</pre>
      </div>

      <div className="journal-section">
        <div className="journal-section-title">Session History</div>
        {sortedStory.length === 0 ? (
          <div className="journal-empty">(No story entries yet)</div>
        ) : (
          <div className="journal-story">
            {sortedStory.map((entry, idx) => (
              <div key={`${entry?.ts || 'entry'}-${idx}`} className="journal-story-entry">
                <div className="journal-story-meta">
                  <span className="journal-story-type">{entry?.type || 'entry'}</span>
                  {entry?.ts ? <span className="journal-story-ts">{formatTimestamp(entry.ts)}</span> : null}
                </div>
                <div className="journal-story-text">{entry?.text || ''}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
