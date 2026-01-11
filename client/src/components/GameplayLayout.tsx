import React, {useEffect, useMemo, useState} from 'react'
import './GameplayLayout.css'
import SiteMenu from './SiteMenu'
import NarrativeView from './NarrativeView'
import Chat from './Chat'
import CharacterPanel, {CharacterSummary, SceneCue} from './CharacterPanel'
import DocumentsPanel from './DocumentsPanel'
import PlayerStatusBar from './PlayerStatusBar'
import { apiFetch, buildWsUrl } from '../api'
type Props = {
  sessionId?: string | null
  roster?: CharacterSummary[]
  selectedCharId?: string | null
  onSelectCharId?: (id: string) => void
}

type Banner = {
  id: string
  title: string
  subtitle?: string
}

const defaultSuggestions = [
  'Survey the immediate area',
  'Address the NPC who spoke',
  'Ready an action or spell',
]

export default function GameplayLayout({sessionId, roster = [], selectedCharId = null, onSelectCharId}: Props){
  const [drawerOpen, setDrawerOpen] = useState(false)
  const openDrawer = () => setDrawerOpen(true)
  const closeDrawer = () => setDrawerOpen(false)
  const [campaignTitle, setCampaignTitle] = useState('Current Campaign')
  const [waitingOverride, setWaitingOverride] = useState<{player: string, expiresAt: number} | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [turnState, setTurnState] = useState<{order: string[]; active?: string | null}>({order: [], active: null})
  const [remoteRoll, setRemoteRoll] = useState<{by?: string | null; total?: number | null; expression?: string | null} | null>(null)
  const [sceneCues, setSceneCues] = useState<SceneCue[]>([])
  const [npcSpotlight, setNpcSpotlight] = useState<Array<{name: string; initiative_hint?: string}>>([])
  useEffect(()=>{
    if(!waitingOverride) return
    const ms = Math.max(0, waitingOverride.expiresAt - Date.now())
    const id = window.setTimeout(()=>setWaitingOverride(null), ms || 0)
    return ()=>window.clearTimeout(id)
  },[waitingOverride])
  useEffect(()=>{
    if(!remoteRoll) return
    const id = window.setTimeout(()=>setRemoteRoll(null), 8000)
    return ()=>window.clearTimeout(id)
  },[remoteRoll])

  useEffect(()=>{
    const handler = (event: Event)=>{
      const detail = (event as CustomEvent).detail
      if(detail?.title){
        setCampaignTitle(detail.title)
      }
    }
    // @ts-ignore
    window.addEventListener('session:campaign', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('session:campaign', handler)
    }
  },[])

  useEffect(()=>{
    const handler = (event: Event)=>{
      const detail = (event as CustomEvent).detail || {}
      const player = detail.player || null
      if(!player){
        setWaitingOverride(null)
        return
      }
      const ttl = typeof detail.expiresMs === 'number' ? detail.expiresMs : 6000
      setWaitingOverride({player, expiresAt: Date.now() + Math.max(1000, ttl)})
    }
    // @ts-ignore
    window.addEventListener('session:waiting', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('session:waiting', handler)
    }
  },[])

  useEffect(()=>{
    const handler = (event: Event)=>{
      const detail = (event as CustomEvent).detail
      if(Array.isArray(detail?.suggestions)){
        setSuggestions(detail.suggestions)
      }
    }
    // @ts-ignore
    window.addEventListener('narrative:suggestions', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('narrative:suggestions', handler)
    }
  },[])

  useEffect(()=>{
    if(!sessionId){
      setTurnState({order: [], active: null})
      setSceneCues([])
      setNpcSpotlight([])
      return
    }
    async function loadTurnState(){
      try{
        const res = await apiFetch(`/turns/${sessionId}`)
        if(!res.ok) throw new Error('turn fetch failed')
        const data = await res.json()
        setTurnState({order: data.order || [], active: data.active || null})
      }catch(err){
        setTurnState({order: [], active: null})
      }
    }
    loadTurnState()
  },[sessionId])

  useEffect(()=>{
    if(!sessionId) return
    const token = encodeURIComponent(window.localStorage.getItem('access_token') || '')
    const wsUrl = buildWsUrl(`/ws/sessions/${sessionId}?token=${token}`)
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (event)=>{
      try{
        const data = JSON.parse(event.data)
        if(data?.type === 'suggestions.update' && Array.isArray(data?.suggestions)){
          window.dispatchEvent(new CustomEvent('narrative:suggestions',{detail:{suggestions:data.suggestions}}))
        }
        if(data?.type === 'turns.update'){
          setTurnState({order: data.order || [], active: data.active})
        }
        if(data?.type === 'beyond20.roll'){
          setRemoteRoll({by: data.by, total: data.total, expression: data.expression})
          if(data?.by){
            window.dispatchEvent(new CustomEvent('session:waiting',{detail:{player: data.by, reason: 'beyond20', expiresMs: 6000}}))
          }
        }
        if(data?.type === 'scene.cues'){
          const dice: any[] = Array.isArray(data?.dice_rolls) ? data.dice_rolls : []
          let prompts: string[] = Array.isArray(data?.prompts) ? data.prompts : []
          if(!prompts.length && dice.length){
            prompts = dice.map(rec => rec?.reason || `Roll a ${rec?.type || 'd20'}`)
          }
          if(prompts.length){
            const timestamp = Date.now()
            const entries: SceneCue[] = prompts.map((prompt, idx) => ({
              id: `${timestamp}-${idx}-${Math.random().toString(16).slice(2,6)}`,
              prompt,
              roll: dice[idx] ? {
                type: dice[idx]?.type,
                skill: dice[idx]?.skill,
                reason: dice[idx]?.reason,
              } : undefined,
            }))
            setSceneCues(prev => [...entries, ...prev].slice(0, 5))
          }
        }
        if(data?.type === 'npc.profile'){
          const name = data?.profile?.name || 'Unknown NPC'
          setNpcSpotlight(prev => {
            const existing = prev.filter(entry => entry.name !== name)
            return [{name, initiative_hint: data?.initiative_hint}, ...existing].slice(0, 4)
          })
        }
      }catch(err){
        console.warn('WS parse error', err)
      }
    }
    ws.onerror = ()=>{
      ws.close()
    }
    return ()=>{
      ws.close()
    }
  },[sessionId])

  useEffect(()=>{
    const handler = (event: Event)=>{
      if(!sessionId) return
      const detail = (event as CustomEvent).detail || {}
      const actions = Array.isArray(detail.actions) && detail.actions.length ? detail.actions : suggestions.slice(0, 3)
      const payload = {
        scene: detail.scene || campaignTitle,
        actions,
        session_id: sessionId,
      }
      apiFetch('/scene/analyze', {
        method: 'POST',
        body: JSON.stringify(payload)
      }).catch(()=>{})
    }
    // @ts-ignore
    window.addEventListener('scene:diagnostics', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('scene:diagnostics', handler)
    }
  },[sessionId, suggestions, campaignTitle])

  const triggerCueRoll = React.useCallback(async (cue: SceneCue) => {
    if(!sessionId) throw new Error('Session not active')
    if(!cue.roll) throw new Error('No roll details provided')
    const normalizedType = (cue.roll.type || '').toLowerCase()
    let expression = '1d20'
    if(/^[0-9]+d[0-9]+$/.test(normalizedType)){
      expression = normalizedType
    }else if(/^d[0-9]+$/.test(normalizedType)){
      expression = `1${normalizedType}`
    }
    const body = {
      expression,
      reason: cue.roll.reason || cue.prompt,
      session_id: sessionId,
    }
    const res = await apiFetch('/rolls', { method: 'POST', body: JSON.stringify(body) })
    if(!res.ok){
      const detail = await res.json().catch(()=>null)
      throw new Error(detail?.detail || 'Roll failed')
    }
    await res.json().catch(()=>null)
  },[sessionId])

  useEffect(()=>{
    const handler = (event: Event)=>{
      if(!sessionId) return
      const detail = (event as CustomEvent).detail || {}
      const npc = detail.npc || {}
      if(!npc.name) return
      const payload = {
        name: npc.name,
        traits: npc.traits || {},
        motivations: npc.motivations || [],
        stats: npc.stats || {},
        quirks: npc.quirks || [],
        session_id: sessionId,
      }
      apiFetch('/npc/manage', {
        method: 'POST',
        body: JSON.stringify(payload)
      }).catch(()=>{})
    }
    // @ts-ignore
    window.addEventListener('npc:profile', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('npc:profile', handler)
    }
  },[sessionId])

  useEffect(()=>{
    let canceled = false
    if(!sessionId){
      setSuggestions([])
      return
    }
    async function loadSuggestions(){
      try{
        const res = await apiFetch(`/suggestions?session_id=${sessionId}`)
        if(!res.ok) throw new Error('Failed to fetch suggestions')
        const data = await res.json()
        if(!canceled && Array.isArray(data?.suggestions)){
          setSuggestions(data.suggestions)
        }
      }catch(err){
        if(!canceled){
          setSuggestions([])
        }
      }
    }
    loadSuggestions()
    const id = window.setInterval(loadSuggestions, 20000)
    return ()=>{
      canceled = true
      window.clearInterval(id)
    }
  },[sessionId])

  const waitingDisplay = waitingOverride?.player ?? (turnState.active || null)

  const banners: Banner[] = useMemo(()=>{
    const entries: Banner[] = [
      {id:'title', title: campaignTitle, subtitle: sessionId ? `Session ${sessionId}` : 'Session overview'},
    ]
    if(waitingDisplay){
      entries.push({id:'waiting', title: `Waiting on ${waitingDisplay}`, subtitle: 'Ready when they are'})
    }
    return entries
  }, [campaignTitle, waitingDisplay, sessionId])

  const [bannerIndex, setBannerIndex] = useState(0)
  useEffect(()=>{
    if(!banners.length) return
    const id = window.setInterval(()=>{
      setBannerIndex((i)=> (i + 1) % banners.length)
    }, 6000)
    return ()=>window.clearInterval(id)
  }, [banners.length])
  const activeBanner = banners[bannerIndex % (banners.length || 1)]
  const visibleSuggestions = suggestions.length ? suggestions : defaultSuggestions
  const selectedCharacter = useMemo(() => {
    if(!roster.length) return undefined
    if(!selectedCharId) return roster[0]
    return roster.find(c => c.id === selectedCharId) ?? roster[0]
  }, [roster, selectedCharId])

  const playerStats = selectedCharacter

  return (
    <div className="gameplay-root" style={{height:'100%', minHeight:0, display:'flex', background:'#18181a'}}>
      <button className="drawer-toggle" aria-label="Open command drawer" aria-expanded={drawerOpen} onClick={openDrawer}>
        Menu
      </button>
      <div className={`drawer-scrim ${drawerOpen ? 'visible' : ''}`} onClick={closeDrawer} aria-hidden={!drawerOpen} />
      <aside className={`command-drawer ${drawerOpen ? 'open' : ''}`} aria-label="Command drawer">
        <SiteMenu onClose={closeDrawer} />
      </aside>
      <main className="gameplay-main" style={{flex:1,display:'flex',flexDirection:'column'}}>
        <section className="session-banner" aria-live="polite">
          <div className="session-banner-title">{activeBanner?.title}</div>
          {activeBanner?.subtitle && <div className="session-banner-subtitle">{activeBanner.subtitle}</div>}
        </section>
        <section className="scene-area" style={{flex:'1 1 60%',position:'relative',padding:'0 0 0 0'}}>
          <NarrativeView sessionId={sessionId} />
        </section>
        <section className="suggestions-bar" aria-label="Agent suggestions">
          <span className="suggestions-label">Suggestions</span>
          <div className="suggestions-list">
            {visibleSuggestions.map((text, idx)=>(
              <button key={`${text}-${idx}`} className="suggestion-pill" type="button">
                {text}
              </button>
            ))}
            {remoteRoll && (
              <div className="suggestion-pill" style={{background:'#122b34', border:'1px solid #1c7ea9'}}>
                <strong>Beyond20:</strong>&nbsp;
                {remoteRoll.by || 'Remote player'} &rarr; {remoteRoll.expression || 'roll'} = {remoteRoll.total ?? '—'}
              </div>
            )}
          </div>
        </section>
        {turnState.order.length > 0 && (
          <section className="turn-tracker" aria-label="Turn order" style={{display:'flex',alignItems:'center',gap:16,padding:'8px 16px',borderBottom:'1px solid #222'}}>
            <div style={{fontWeight:600,fontSize:14}}>Current Turn:</div>
            <div style={{fontSize:14}}>{turnState.active || '—'}</div>
            <div style={{fontSize:12,color:'#888'}}>
              Queue: {turnState.order.join(' → ')}
            </div>
          </section>
        )}
        {playerStats && (
          <PlayerStatusBar
            name={playerStats.name}
            ac={playerStats.ac}
            hp={{ current: playerStats.hp.current, max: playerStats.hp.max }}
            tempHp={playerStats.hp.temp || 0}
            deathSaves={{ success: 1, failure: 0 }}
            exhaustion={0}
            spellSaveDc={playerStats.spellSave || 10}
          />
        )}
        <div className="bottom-row" style={{display:'flex',height:'40%',minHeight:'220px'}}>
          <section className="chat-area" aria-label="Chat" style={{flex:'1 1 70%',borderTop:'1px solid #222',padding:'12px'}}><Chat sessionId={sessionId || undefined}/></section>
          <aside className="chars-area" aria-label="Character Management" style={{width:'320px',borderLeft:'1px solid #222',padding:'12px', overflowY:'auto'}}>
            <CharacterPanel
              roster={roster}
              selectedId={selectedCharId}
              onSelect={onSelectCharId}
              sceneCues={sceneCues}
              npcSpotlight={npcSpotlight}
              onCueRoll={triggerCueRoll}
            />
            <DocumentsPanel sessionId={sessionId} />
          </aside>
        </div>
      </main>
    </div>
  )
}
