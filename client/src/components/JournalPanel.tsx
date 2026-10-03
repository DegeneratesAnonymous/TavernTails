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
  memoryUpdates?: Record<string, any> | null
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

function asList(value: any): any[] {
  return Array.isArray(value) ? value.filter(Boolean) : []
}

function itemLabel(item: any): string {
  return typeof item === 'string' ? item : (item?.name || item?.title || item?.summary || JSON.stringify(item))
}

function dedupeItems(items: any[]): any[] {
  const seen = new Set<string>()
  const out: any[] = []
  for (const item of items) {
    const label = itemLabel(item).trim()
    const key = label.toLowerCase()
    if (!label || seen.has(key)) continue
    seen.add(key)
    out.push(item)
  }
  return out
}

export default function JournalPanel({ sessionId, memoryUpdates }: Props) {
  const [story, setStory] = useState<StoryEntry[]>([])
  const [archiveTab, setArchiveTab] = useState<'overview' | 'people' | 'places' | 'threads' | 'clues' | 'timeline' | 'notes' | 'factions'>('overview')
  const [notesMd, setNotesMd] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [noteDraft, setNoteDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [focusedEntityName, setFocusedEntityName] = useState<string | null>(null)
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

  useEffect(() => {
    const handler = () => { load() }
    window.addEventListener('journal:refresh', handler)
    return () => window.removeEventListener('journal:refresh', handler)
  }, [load])

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail || {}
      const name = String(detail?.name || '').trim()
      if (!name) return
      setArchiveTab(detail?.entityType === 'places' ? 'places' : 'people')
      setFocusedEntityName(name)
      window.setTimeout(() => setFocusedEntityName(null), 2400)
    }
    window.addEventListener('journal:focus-entity', handler)
    return () => window.removeEventListener('journal:focus-entity', handler)
  }, [])

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

  const archiveSections = useMemo(() => ({
    people: dedupeItems(asList(memoryUpdates?.new_npcs).concat(asList(memoryUpdates?.updated_npcs))),
    places: dedupeItems(asList(memoryUpdates?.new_locations).concat(asList(memoryUpdates?.updated_locations))),
    threads: dedupeItems(
      asList(memoryUpdates?.new_threads)
        .concat(asList(memoryUpdates?.updated_threads))
        .concat(asList(memoryUpdates?.new_consequences))
    ),
    clues: dedupeItems(asList(memoryUpdates?.new_clues).concat(asList(memoryUpdates?.updated_clues))),
    factions: dedupeItems(asList(memoryUpdates?.new_factions).concat(asList(memoryUpdates?.updated_factions))),
  }), [memoryUpdates])

  const memoryItems = archiveTab === 'people' || archiveTab === 'places' || archiveTab === 'threads' || archiveTab === 'clues' || archiveTab === 'factions'
    ? archiveSections[archiveTab]
    : []

  const emptyText: Record<string, string> = {
    people: 'No people recorded yet. Characters will appear here after the party meets or meaningfully observes them.',
    places: 'No places recorded yet. Locations will appear here as the party explores.',
    threads: 'No threads recorded yet. Active story threads will appear as consequences take shape.',
    clues: 'No clues discovered yet. Investigate the scene to reveal noteworthy evidence.',
    factions: 'No factions recorded yet. Groups and allegiances will appear when they matter.',
  }

  const archiveCards = useMemo(() => ([
    {
      key: 'people' as const,
      label: 'People',
      count: archiveSections.people.length,
      detail: archiveSections.people.length ? 'Known faces and NPCs.' : 'No people recorded yet.',
    },
    {
      key: 'places' as const,
      label: 'Places',
      count: archiveSections.places.length,
      detail: archiveSections.places.length ? 'Visited or observed locations.' : 'No places recorded yet.',
    },
    {
      key: 'threads' as const,
      label: 'Threads',
      count: archiveSections.threads.length,
      detail: archiveSections.threads.length ? 'Open story pressure and consequences.' : 'No story threads recorded yet.',
    },
    {
      key: 'clues' as const,
      label: 'Noteworthy',
      count: archiveSections.clues.length,
      detail: archiveSections.clues.length ? 'Player-marked evidence and observations.' : 'Mark text as noteworthy to collect it here.',
    },
    {
      key: 'timeline' as const,
      label: 'Timeline',
      count: sortedStory.length,
      detail: sortedStory.length ? 'Session events in order.' : 'No timeline entries yet.',
    },
    {
      key: 'notes' as const,
      label: 'Notes',
      count: notesMd.trim() ? notesMd.trim().split(/\n+/).length : 0,
      detail: notesMd.trim() ? 'Saved player notes.' : 'No player notes yet.',
    },
    {
      key: 'factions' as const,
      label: 'Factions',
      count: archiveSections.factions.length,
      detail: archiveSections.factions.length ? 'Groups, allegiances, and pressure.' : 'No factions recorded yet.',
    },
  ]), [archiveSections, notesMd, sortedStory.length])

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
        <span className="jrnl-title">Journal Archive</span>
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

      <div className="jrnl-archive-tabs" role="tablist" aria-label="Archive categories">
        {([
          ['overview', 'Overview'],
          ['people', 'People'],
          ['places', 'Places'],
          ['threads', 'Threads'],
          ['clues', 'Noteworthy'],
          ['timeline', 'Timeline'],
          ['notes', 'Notes'],
          ['factions', 'Factions'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={archiveTab === key}
            className={`jrnl-archive-tab ${archiveTab === key ? 'active' : ''}`}
            onClick={() => setArchiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {archiveTab === 'overview' ? (
        <div className="jrnl-category-dashboard" aria-label="Archive dashboard">
          {archiveCards.map((card) => (
            <button
              key={card.key}
              type="button"
              className="jrnl-category-card"
              onClick={() => setArchiveTab(card.key)}
            >
              <span className="jrnl-category-count">{card.count}</span>
              <strong>{card.label}</strong>
              <span>{card.detail}</span>
            </button>
          ))}
        </div>
      ) : null}

      {archiveTab === 'people' || archiveTab === 'places' || archiveTab === 'threads' || archiveTab === 'clues' || archiveTab === 'factions' ? (
        <div className="jrnl-card-grid">
          {memoryItems.length ? memoryItems.slice(0, 12).map((item, idx) => {
            const label = itemLabel(item)
            const isFocused = focusedEntityName && label.toLowerCase() === focusedEntityName.toLowerCase()
            return (
            <article key={idx} className={`jrnl-memory-card${isFocused ? ' is-focused' : ''}`}>
              <div className="jrnl-memory-card-title">{itemLabel(item)}</div>
              {typeof item !== 'string' && item?.summary ? (
                <div className="jrnl-memory-card-body">{String(item.summary)}</div>
              ) : null}
              {typeof item !== 'string' && item?.status ? (
                <div className="jrnl-memory-card-meta">{String(item.status)}</div>
              ) : null}
            </article>
            )
          }) : (
            <div className="jrnl-empty jrnl-empty--useful">{emptyText[archiveTab]}</div>
          )}
        </div>
      ) : null}

      {archiveTab === 'timeline' && sortedStory.length > 0 ? (
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
      ) : archiveTab === 'timeline' && canLoad ? (
        <div className="jrnl-empty jrnl-empty--useful">The story has just begun. Major events will appear here as the session unfolds.</div>
      ) : null}

      {/* Notes from notes.md */}
      {archiveTab === 'notes' && notesMd ? (
        <div className="jrnl-notes-block">
          <div className="jrnl-notes-label">Notes</div>
          <div className="jrnl-notes-content">{notesMd}</div>
        </div>
      ) : archiveTab === 'notes' ? (
        <div className="jrnl-empty jrnl-empty--useful">No player notes yet. Mark important discoveries or plans here.</div>
      ) : null}

      {/* Composer */}
      {canLoad && archiveTab === 'notes' ? (
        <div className="jrnl-composer">
          <textarea
            className="jrnl-composer-input"
            rows={2}
            placeholder="Add a noteworthy note… (⌘Enter to save)"
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
