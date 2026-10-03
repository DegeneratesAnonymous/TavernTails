import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import { buildApiUrl } from '../api'
import './NarrativeView.css'

type VisualStateMeta = {
  visual_type?: string
  location_name?: string
  mood?: string
  threat_level?: string
  last_refresh_reason?: string
  image_refresh_required?: boolean
}

type Scene = {
  id: string
  title: string
  image?: string | {
    url?: string | null
    visual_type?: string
    location?: string
    mood?: string
    weather?: string
    refresh_reason?: string
  } | null
  text: string
  narrative_body?: string   // preferred: just the story paragraphs, no player question
  player_prompt?: string    // preferred: just the player-facing question
  choices: Array<{id:string,label:string}>
  visual_state?: VisualStateMeta
  location?: string
  weather?: string
  time_of_day?: string
  immediate_stakes?: string
  active_threads?: string[]
  hooks?: string[]
  world_moves?: string[]
  suggested_actions?: string[]
  visible_clues?: string[]
  current_objective?: string
  active_thread?: string
  current_situation?: Record<string, any>
  scene_summary?: {
    objective?: string
    observed?: string
    risk?: string
  }
  world_clock?: Record<string, any>
  experience_mode?: string
  memory_updates?: Record<string, any>
  dice_rolls?: any[]
}

export type EntityHint = {
  name: string
  role?: string
  description?: string
}

type Props = {
  sessionId?: string | null
  showChoicesInScene?: boolean
  entities?: EntityHint[]
  presentationMode?: 'read' | 'play' | 'world'
  focusMode?: boolean
  onExitRead?: () => void
}

function displayText(value: any): string {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    return String(value.name || value.title || value.description || '')
  }
  return ''
}

function EntityMention({ entity, children }: { entity: EntityHint; children: string }) {
  const openJournal = () => {
    window.dispatchEvent(new CustomEvent('journal:focus-entity', {
      detail: { entityType: 'people', name: entity.name },
    }))
  }
  return (
    <button className="entity-mention" type="button" onClick={openJournal}>
      {children}
      <span className="entity-tooltip">
        <span className="entity-tooltip-name">{entity.name}</span>
        {entity.role ? <span className="entity-tooltip-role">{entity.role}</span> : null}
        {entity.description ? <span className="entity-tooltip-desc">{entity.description}</span> : null}
      </span>
    </button>
  )
}

function annotateText(text: string, entities: EntityHint[]): React.ReactNode {
  if (!entities.length) return text
  const sorted = [...entities]
    .filter(e => e.name && e.name.length >= 2)
    .sort((a, b) => b.name.length - a.name.length)
  const escaped = sorted.map(e => e.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const pattern = new RegExp(`\\b(${escaped.join('|')})\\b`, 'gi')
  const parts: React.ReactNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const hit = match[0]
    const entity = sorted.find(e => e.name.toLowerCase() === hit.toLowerCase())
    parts.push(entity
      ? <EntityMention key={`${match.index}`} entity={entity}>{hit}</EntityMention>
      : hit
    )
    last = pattern.lastIndex
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

export default function NarrativeView({sessionId, showChoicesInScene = false, entities = [], presentationMode = 'play', focusMode = false, onExitRead}: Props){
  // Scene ownership is intentionally local: this component fetches and renders
  // prose/art, then broadcasts scene metadata for the surrounding play layout.
  const [scene, setScene] = useState<Scene|null>(null)
  const [choicesOpen, setChoicesOpen] = useState(false)
  const [imageError, setImageError] = useState(false)
  const narrativeCardRef = useRef<HTMLDivElement | null>(null)
  const [bookPage, setBookPage] = useState(0)
  const touchStartX = useRef<number | null>(null)

  const choose = useCallback(async (id: string) => {
    try{
      const token = localStorage.getItem('access_token')
      const headers: any = { 'Content-Type': 'application/json' }
      if(token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch(buildApiUrl('/content/advance'),{
          method:'POST',headers,
          body: JSON.stringify({sceneId: scene?.id, choiceId: id, sessionId})
        })
      const data = await res.json()
      window.dispatchEvent(new CustomEvent('narrative:advance',{detail:data}))
      if(data.nextScene) setScene(data.nextScene)
    }catch(e){
      console.error('choice failed',e)
    }
  }, [scene?.id, sessionId])

  useEffect(() => { setImageError(false) }, [scene?.id])

  useEffect(() => {
    if (narrativeCardRef.current) {
      narrativeCardRef.current.scrollTop = 0
    }
    setBookPage(0)
  }, [scene?.id, scene?.text, scene?.narrative_body])

  useEffect(() => {
    if (presentationMode !== 'read') return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setBookPage(p => Math.max(0, p - 2))
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        setBookPage(p => p + 2)
      } else if (event.key === 'Escape') {
        onExitRead?.()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [presentationMode, onExitRead])

  useEffect(() => {
    if(!scene) return
    setChoicesOpen(false)
    window.dispatchEvent(new CustomEvent('narrative:choices', {
      detail: {
        sceneId: scene.id,
        title: scene.title,
        choices: Array.isArray(scene.choices) ? scene.choices : [],
      }
    }))
    // Broadcast full scene for session banner, summary strip, roll drawers, and
    // world/archive panels. Consumers choose the slices they need.
    window.dispatchEvent(new CustomEvent('narrative:scene-meta', { detail: scene }))
  }, [scene])

  useEffect(()=>{
    let mounted = true
    setScene(null)
    const token = localStorage.getItem('access_token')
    const headers: any = { 'Content-Type': 'application/json' }
    if(token) headers['Authorization'] = `Bearer ${token}`
    const seedUrl = sessionId ? buildApiUrl(`/sessions/${sessionId}/file/scene.json`) : buildApiUrl('/content/campaigns/seed')
    const load = async () => {
      try{
        const r = await fetch(seedUrl, { headers })
        if(!r.ok) throw new Error('scene missing')
        const data = await r.json()
        if(!mounted) return
        const normalized: Scene = {
          ...data,
          choices: Array.isArray(data?.choices) ? data.choices : []
        }
        setScene(normalized)
      }catch{
        if(sessionId){
          try{
            await fetch(buildApiUrl(`/sessions/${sessionId}/start`), { method:'POST', headers, body: JSON.stringify({}) })
            const r2 = await fetch(seedUrl, { headers })
            if(r2.ok){
              const data2 = await r2.json()
              if(mounted){
                setScene({ ...data2, choices: Array.isArray(data2?.choices) ? data2.choices : [] })
                return
              }
            }
          }catch{/* ignore */}
        }
        if(mounted){
          setScene({
            id:'seed',
            title:'The Abandoned Mill',
            image:'',
            text:'The wind howls as you step into the mill. Broken gears and faded banners tell a story of a sudden evacuation...',
            choices:[{id:'search',label:'Search the sacks'},{id:'listen',label:'Listen at the door'}]
          })
        }
      }
    }
    load()
    return ()=>{ mounted=false }
  },[sessionId])

  useEffect(()=>{
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail || {}
      const next = detail.scene
      if(next && typeof next === 'object'){
        setScene({
          ...(next as Scene),
          choices: Array.isArray((next as any)?.choices) ? (next as any).choices : [],
        })
      }
    }
    // @ts-ignore
    window.addEventListener('narrative:scene', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('narrative:scene', handler)
    }
  },[])

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail || {}
      const choiceId = String(detail.choiceId || detail.id || '').trim()
      if(!choiceId) return
      choose(choiceId)
    }
    // @ts-ignore
    window.addEventListener('narrative:choose', handler)
    return () => {
      // @ts-ignore
      window.removeEventListener('narrative:choose', handler)
    }
  }, [choose])

  // Annotations depend on scene text — must be before any early return to satisfy hooks rules.
  // narration is derived from scene below; use scene?.text as dependency proxy.
  const annotatedNarration = useMemo(() => {
    if (!scene) return null
    const parsed = scene.narrative_body || scene.text || ''
    // strip citations block for annotation (full parsing happens after guard)
    const main = parsed.includes('\n\nCitations: ') ? parsed.slice(0, parsed.indexOf('\n\nCitations: ')).trim() : parsed
    return annotateText(main, entities)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene?.id, scene?.text, scene?.narrative_body, entities.length])

  if(!scene) return <div className="narrative-loading">Loading scene…</div>

  const hasChoices = Array.isArray(scene.choices) && scene.choices.length > 0

  const parseCitations = (text: string) => {
    const marker = '\n\nCitations: '
    const idx = text.indexOf(marker)
    if (idx === -1) return { main: text, citations: [] }
    const main = text.slice(0, idx).trim()
    const rest = text.slice(idx + marker.length).trim()
    const parts = rest.split(' | ').map(p => p.trim()).filter(Boolean)
    const citations = parts.map(p => {
      const m = p.match(/\[([^\s\]]+)\s+p(\d+)\]\s*(.*)/)
      if (m) return { source_id: m[1], page: Number(m[2]), snippet: m[3] || '' }
      return { raw: p }
    })
    return { main, citations }
  }

  // Use narrative_body/player_prompt when available. Older cached scenes may
  // still include the player question at the end of `text`, so this fallback
  // peels that prompt off for UI placement.
  const splitNarrativePrompt = (text: string): { narration: string; playerPrompt: string } => {
    const lastQ = text.lastIndexOf('?')
    if (lastQ === -1) return { narration: text, playerPrompt: '' }
    const before = text.slice(0, lastQ + 1).trimEnd()
    const sentenceStart = Math.max(
      before.lastIndexOf('\n'),
      before.lastIndexOf('. '),
    ) + 1
    const prompt = before.slice(sentenceStart).trim()
    const narration = before.slice(0, sentenceStart).trim()
    if (!narration) return { narration: text, playerPrompt: '' }
    return { narration, playerPrompt: prompt }
  }

  const parsed = parseCitations(scene.narrative_body || scene.text || '')
  const narrativeParagraphs = parsed.main.split(/\n{2,}/).map(p => p.trim()).filter(Boolean)
  // Two-column prose only helps after the body is long enough; tune this with
  // the matching `.narrative-prose-flow--columns` CSS.
  const narrativeWordCount = parsed.main.split(/\s+/).filter(Boolean).length
  const playerPromptFallback = splitNarrativePrompt(parsed.main)
  const playerPrompt = scene.player_prompt || playerPromptFallback.playerPrompt

  const locationName = scene.visual_state?.location_name || displayText(scene.location)
  const mood = scene.visual_state?.mood || ''
  const imageUrl = typeof scene.image === 'string' ? scene.image : scene.image?.url || ''
  const imageMeta = typeof scene.image === 'object' && scene.image ? scene.image : null
  const hasImage = !!(imageUrl && !imageError)

  // Parse title into location and chapter label
  // Title format from backend: "Scene Title — Location Name" or just title
  const rawTitle = scene.title || ''
  const dashIdx = rawTitle.indexOf(' — ')
  const chapterLabel = dashIdx > -1 ? rawTitle.slice(0, dashIdx) : rawTitle
  const locationLabel = dashIdx > -1 ? rawTitle.slice(dashIdx + 3) : (locationName || '')
  const timeLabel = scene.time_of_day
    ? scene.time_of_day.charAt(0).toUpperCase() + scene.time_of_day.slice(1)
    : ''

  const bookPages = (() => {
    const source = parsed.main.trim()
    const paragraphs = source.split(/\n{2,}/).map(p => p.trim()).filter(Boolean)
    const chunks: string[] = []
    let current = ''
    const target = 105
    for (const paragraph of paragraphs) {
      const next = current ? `${current}\n\n${paragraph}` : paragraph
      const words = next.split(/\s+/).filter(Boolean).length
      if (current && words > target) {
        chunks.push(current)
        current = paragraph
      } else {
        current = next
      }
    }
    if (current) chunks.push(current)
    if (!chunks.length) chunks.push(source)
    return chunks
  })()
  const maxBookPage = Math.max(0, bookPages.length - 1)
  const safeBookPage = Math.min(bookPage, maxBookPage)
  const visibleBookPages = [safeBookPage, safeBookPage + 1].filter(i => i <= maxBookPage)
  const onTouchEnd = (x: number) => {
    if (touchStartX.current == null) return
    const delta = x - touchStartX.current
    touchStartX.current = null
    if (Math.abs(delta) < 45) return
    setBookPage(p => delta < 0 ? Math.min(maxBookPage, p + 1) : Math.max(0, p - 1))
  }

  // Opening setup pending state. Older cached sessions may still contain the
  // pre-scene generic approach choices; do not show them as playable fiction.
  const isOpeningPlaceholder = scene.id === 'opening' && !scene.narrative_body && hasChoices
  if (isOpeningPlaceholder && presentationMode !== 'read') {
    return (
      <div className="opening-approach-view">
        <h2 className="opening-approach-title">Opening scene pending.</h2>
        <p className="opening-approach-subtitle">Complete the campaign brief and character setup to generate the first playable scene.</p>
      </div>
    )
  }

  if (presentationMode === 'read') {
    const chapterTitle = locationLabel || chapterLabel || 'Current Scene'
    return (
      <div
        className="book-read-view"
        onTouchStart={(e) => { touchStartX.current = e.touches[0]?.clientX ?? null }}
        onTouchEnd={(e) => onTouchEnd(e.changedTouches[0]?.clientX ?? 0)}
      >
        <div className={`book-spread ${visibleBookPages.length === 1 ? 'book-spread--single' : ''}`} aria-label="Read mode book spread">
          {visibleBookPages.map((pageIndex) => {
            const isFirst = pageIndex === 0
            const isLast = pageIndex === maxBookPage
            return (
              <article key={pageIndex} className="book-page">
                {hasImage && isFirst ? (
                  <img className="book-page-image" src={imageUrl} alt={imageMeta?.location ? `Scene art for ${imageMeta.location}` : 'Scene art'} onError={() => setImageError(true)} />
                ) : null}
                <div className="book-page-content">
                  {isFirst ? (
                    <>
                      <div className="book-page-eyebrow">{[timeLabel, scene.weather].filter(Boolean).join(' · ')}</div>
                      <h2 className="book-page-title">{chapterTitle}</h2>
                      <div className="book-page-divider" aria-hidden="true">❖ ❖ ❖</div>
                    </>
                  ) : null}
                  <p className={`book-page-prose ${isFirst ? 'book-page-prose--opening' : ''}`}>
                    {annotateText(bookPages[pageIndex] || '', entities)}
                  </p>
                  {isLast && playerPrompt ? (
                    <div className="book-page-prompt">{playerPrompt}</div>
                  ) : null}
                </div>
                <div className="book-page-number">{pageIndex + 1}</div>
              </article>
            )
          })}
        </div>
        <div className="book-page-controls">
          <button type="button" onClick={() => setBookPage(p => Math.max(0, p - 2))} disabled={safeBookPage <= 0}>← Previous</button>
          <span>Page {safeBookPage + 1}{visibleBookPages.length > 1 ? `-${visibleBookPages[visibleBookPages.length - 1] + 1}` : ''} of {bookPages.length}</span>
          <button type="button" onClick={() => setBookPage(p => Math.min(maxBookPage, p + 2))} disabled={safeBookPage >= maxBookPage}>Next →</button>
        </div>
      </div>
    )
  }

  return (
    <div className="narrative-view">

      {/* ── Scene: image fills container, narrative card overlays bottom ── */}
      <div className={`narrative-scene ${hasImage ? '' : 'narrative-scene--no-image'}`}>

        {hasImage ? (
          <img src={imageUrl} alt={imageMeta?.location ? `Scene art for ${imageMeta.location}` : 'Scene art'} onError={() => setImageError(true)} />
        ) : (
          <div className="narrative-image-placeholder">
            <span>✦</span>
          </div>
        )}

        {/* Location chip — top-left of image */}
        {locationName ? (
          <div className="scene-location-chip">
            <span className="scene-location-name">{locationName}</span>
            {mood ? <span className="scene-mood-badge">{mood}</span> : null}
          </div>
        ) : null}

        {/* Narrative card — overlays the lower portion of the image */}
        <div className="narrative-overlay">
          <div className="narrative-card" ref={narrativeCardRef}>

            {/* Book-style chapter header */}
            <div className="narrative-chapter-header">
              {timeLabel ? (
                <div className="narrative-chapter-eyebrow">
                  {[timeLabel, scene.weather].filter(Boolean).join(' · ')}
                </div>
              ) : null}
              {locationLabel ? (
                <div className="narrative-chapter-location">{locationLabel}</div>
              ) : chapterLabel ? (
                <div className="narrative-chapter-location">{chapterLabel}</div>
              ) : null}
            </div>

            <div className="narrative-divider" aria-hidden="true">❖ ❖ ❖</div>

            <div className={`narrative-prose-flow ${narrativeWordCount >= 150 ? 'narrative-prose-flow--columns' : ''}`}>
              {narrativeParagraphs.length > 0 ? (
                narrativeParagraphs.map((paragraph, index) => (
                  <p key={index} className="narrative-text">{annotateText(paragraph, entities)}</p>
                ))
              ) : (
                <p className="narrative-text">{annotatedNarration}</p>
              )}
            </div>

            {playerPrompt && presentationMode !== 'play' ? (
              <div className="narrative-player-prompt">{playerPrompt}</div>
            ) : null}

            {parsed.citations && parsed.citations.length > 0 ? (
              <div className="narrative-citations">
                <div className="narrative-citations-label">Sources</div>
                <ul>
                  {parsed.citations.map((c: any, i: number) => (
                    <li key={`cit-${i}`}>
                      {c.source_id ? (
                        <a href={buildApiUrl(`/references/${c.source_id}/raw`) + `#page=${c.page}`} target="_blank" rel="noreferrer">
                          [{c.source_id} p{c.page}]
                        </a>
                      ) : null}{' '}
                      <span className="muted">— {c.snippet || c.raw}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {showChoicesInScene && hasChoices ? (
              <div className="narrative-choices-wrap">
                <button
                  type="button"
                  className="narrative-choices-toggle"
                  aria-expanded={choicesOpen}
                  onClick={() => setChoicesOpen(v => !v)}
                >
                  {choicesOpen ? 'Hide choices' : `Show choices (${scene.choices.length})`}
                </button>
                {choicesOpen ? (
                  <div className="narrative-choices">
                    {scene.choices.map(c => (
                      <button key={c.id} className="narrative-choice-btn" onClick={() => choose(c.id)}>
                        {c.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

          </div>{/* /narrative-card */}
        </div>{/* /narrative-overlay */}

      </div>{/* /narrative-scene */}
    </div>
  )
}
