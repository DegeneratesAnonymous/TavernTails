import React, {useCallback, useEffect, useState} from 'react'
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
  image?: string
  text: string
  choices: Array<{id:string,label:string}>
  visual_state?: VisualStateMeta
}

type Props = {
  sessionId?: string | null
  showChoicesInScene?: boolean
}

export default function NarrativeView({sessionId, showChoicesInScene = false}: Props){
  const [scene, setScene] = useState<Scene|null>(null)
  const [choicesOpen, setChoicesOpen] = useState(false)
  const [imageError, setImageError] = useState(false)

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

  // Reset image error state when scene changes.
  useEffect(() => { setImageError(false) }, [scene?.id])

  // Broadcast the current set of choices so other layout areas (like chat) can render them.
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
  }, [scene])

  useEffect(()=>{
    let mounted = true
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

  // Allow external UI (like the chat dock) to trigger a scene choice.
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

  if(!scene) return <div style={{padding:12}}>Loading scene…</div>

  const hasChoices = Array.isArray(scene.choices) && scene.choices.length > 0

  // Parse citations block if appended by the server LLM (format: "\n\nCitations: [SRC pN] snippet | [SRC pM] snippet")
  const parseCitations = (text: string) => {
    const marker = '\n\nCitations: '
    const idx = text.indexOf(marker)
    if (idx === -1) return { main: text, citations: [] }
    const main = text.slice(0, idx).trim()
    const rest = text.slice(idx + marker.length).trim()
    const parts = rest.split(' | ').map(p => p.trim()).filter(Boolean)
    const citations = parts.map(p => {
      // Expect format: [SRC pN] snippet
      const m = p.match(/\[([^\s\]]+)\s+p(\d+)\]\s*(.*)/)
      if (m) return { source_id: m[1], page: Number(m[2]), snippet: m[3] || '' }
      return { raw: p }
    })
    return { main, citations }
  }

  const parsed = parseCitations(scene.text || '')

  return (
    <div className="narrative-view">
      <div className="narrative-scene">
        {scene.image && !imageError ? (
          <img src={scene.image} alt="scene" onError={() => setImageError(true)} />
        ) : null}

        {process.env.NODE_ENV === 'development' && scene.visual_state ? (
          <div className="narrative-visual-meta">
            {[
              scene.visual_state.visual_type,
              scene.visual_state.location_name,
              scene.visual_state.mood,
              scene.visual_state.threat_level ? `⚠ ${scene.visual_state.threat_level}` : null,
              scene.visual_state.image_refresh_required === false ? '♻ reused' : '🖼 new',
            ].filter(Boolean).join(' · ')}
          </div>
        ) : null}

        <div className="narrative-overlay">
          <div className="narrative-card">
            <h2 className="narrative-title">{scene.title}</h2>
            <p className="narrative-text">{parsed.main}</p>

            {parsed.citations && parsed.citations.length > 0 ? (
              <div className="narrative-citations" style={{ marginTop: 8 }}>
                <div className="muted" style={{ fontSize: 13 }}>Citations</div>
                <ul style={{ margin: '6px 0 0 18px' }}>
                  {parsed.citations.map((c: any, i: number) => (
                    <li key={`cit-${i}`} style={{ marginBottom: 6 }}>
                      {c.source_id ? (
                        <a href={buildApiUrl(`/references/${c.source_id}/raw`) + `#page=${c.page}`} target="_blank" rel="noreferrer">
                          [{c.source_id} p{c.page}]
                        </a>
                      ) : null}{' '}
                      <span className="muted" style={{ fontSize: 13 }}>— {c.snippet || c.raw}</span>
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
          </div>
        </div>
      </div>
    </div>
  )
}
