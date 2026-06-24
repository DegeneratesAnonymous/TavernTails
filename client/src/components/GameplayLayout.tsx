import React, {useCallback, useEffect, useMemo, useState} from 'react'
import './GameplayLayout.css'
import NarrativeView from './NarrativeView'
import CharacterPanel, {CharacterSummary, SceneCue} from './CharacterPanel'
import DocumentsPanel from './DocumentsPanel'
import JournalPanel from './JournalPanel'
import WorldPanel from './WorldPanel'
import ContextDebugPanel from './ContextDebugPanel'
import StoryDashboard, { StoryDashboardData } from './StoryDashboard'
import { apiFetch, buildWsUrl } from '../api'
import SiteMenu from './SiteMenu'
import SiteNavMenu from './SiteNavMenu'
type Props = {
  sessionId?: string | null
  roster?: CharacterSummary[]
  selectedCharId?: string | null
  onSelectCharId?: (id: string) => void
  onNavigate?: (key: string) => void
  onLogout?: () => void

  currentUserEmail?: string | null
  currentUsername?: string | null

  activeCampaignId?: string | null
  activeCampaign?: any | null
  onCampaignUpdated?: () => Promise<void> | void
  onStartCampaign?: () => Promise<void> | void
  startCampaignBusy?: boolean

  campaigns?: Array<any>
  onSelectCampaign?: (id: string | null) => void | Promise<void>
  onNewCampaign?: () => void
  onQuickstart?: () => void

  activeCharacterId?: number | null
  onGoToCharacters?: () => void
  onGoToImport?: () => void
  playerRunMode?: boolean

  notificationsPending?: boolean
  onNotificationsClick?: () => void
  isAdmin?: boolean
  onRefreshRoster?: () => void
}

const BellIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
  </svg>
)

const BellUnreadIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0M10.5 8.25h3l-3 4.5h3" />
  </svg>
)

type Banner = {
  id: string
  title: string
  subtitle?: string
}

export default function GameplayLayout({
  sessionId,
  roster = [],
  selectedCharId = null,
  onSelectCharId,
  onNavigate,
  onLogout,
  onRefreshRoster,
  currentUserEmail,
  currentUsername,
  activeCampaignId,
  activeCampaign,
  onCampaignUpdated,
  onStartCampaign,
  startCampaignBusy,
  campaigns = [],
  onSelectCampaign,
  onNewCampaign,
  onQuickstart,
  activeCharacterId,
  onGoToCharacters,
  onGoToImport,
  playerRunMode = false,
  notificationsPending = false,
  onNotificationsClick,
  isAdmin = false,
}: Props){
  const [drawerOpen, setDrawerOpen] = useState(false)
  const openDrawer = () => setDrawerOpen(true)
  const closeDrawer = () => setDrawerOpen(false)

  const [rightTab, setRightTab] = useState<'character' | 'journal' | 'world'>('character')
  const [drawerView, setDrawerView] = useState<'site' | 'panels' | 'party' | 'documents'>('panels')
  const [partySelectedId, setPartySelectedId] = useState<string | null>(null)
  const [showInviteForm, setShowInviteForm] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteNote, setInviteNote] = useState('')
  const [inviteBusy, setInviteBusy] = useState(false)
  const [inviteMessage, setInviteMessage] = useState<string | null>(null)
  const [inviteMatches, setInviteMatches] = useState<Array<{id?: number; username?: string | null; email?: string | null; name?: string | null}>>([])
  const [inviteMatchBusy, setInviteMatchBusy] = useState(false)

  const [partyData, setPartyData] = useState<any | null>(null)
  const [partyError, setPartyError] = useState<string | null>(null)

  const handleSheetUpdate = useCallback((_characterId: string, _patch: Record<string, any>) => {
    onRefreshRoster?.()
  }, [onRefreshRoster])

  const [composerInject, setComposerInject] = useState<string | null>(null)
  const handleQuickAction = useCallback((action: {type: string; detail?: string}) => {
    if (!action.detail) return
    const tag = '@' + action.detail.replace(/\s+/g, '_') + ' '
    setComposerInject(tag)
  }, [])
  const [sessionStarted, setSessionStarted] = useState(false)
  const [settingsMenuOpen, setSettingsMenuOpen] = useState(false)
  const [campaignTitle, setCampaignTitle] = useState('Current Campaign')
  const [waitingOverride, setWaitingOverride] = useState<{player: string, expiresAt: number} | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [turnState, setTurnState] = useState<{order: string[]; active?: string | null}>({order: [], active: null})
  const [remoteRoll, setRemoteRoll] = useState<{by?: string | null; total?: number | null; expression?: string | null} | null>(null)
  const [sceneCues, setSceneCues] = useState<SceneCue[]>([])
  const [npcSpotlight, setNpcSpotlight] = useState<Array<{name: string; initiative_hint?: string}>>([])
  const [contextDebug, setContextDebug] = useState<any | null>(null)
  const [showContextDebug, setShowContextDebug] = useState(false)
  const [storyDebug, setStoryDebug] = useState<StoryDashboardData | null>(null)
  const [showStoryDash, setShowStoryDash] = useState(false)

  useEffect(()=>{
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail
      if(detail) setContextDebug(detail)
    }
    // @ts-ignore
    window.addEventListener('context:debug', handler)
    return () => { // @ts-ignore
      window.removeEventListener('context:debug', handler)
    }
  }, [])

  useEffect(()=>{
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail
      if(detail) setStoryDebug(detail)
    }
    // @ts-ignore
    window.addEventListener('story:debug', handler)
    return () => { // @ts-ignore
      window.removeEventListener('story:debug', handler)
    }
  }, [])
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
        if(data?.type === 'narrative.scene' && data?.scene){
          window.dispatchEvent(new CustomEvent('narrative:scene',{detail:{scene:data.scene}}))
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

  useEffect(() => {
    let canceled = false
    async function loadStarted() {
      if (!sessionId) {
        setSessionStarted(false)
        return
      }
      try {
        const res = await apiFetch(`/sessions/${sessionId}/file/story.json`)
        if (!res.ok) throw new Error('story missing')
        const data = await res.json().catch(() => null)
        const entries = Array.isArray(data) ? data : []
        const hasNarration = entries.some((e: any) => e?.type === 'narration')
        if (!canceled) setSessionStarted(Boolean(hasNarration))
      } catch {
        if (!canceled) setSessionStarted(false)
      }
    }
    loadStarted()
    return () => {
      canceled = true
    }
  }, [sessionId])

  useEffect(()=>{
    const handler = ()=>{
      setDrawerView('documents')
      openDrawer()
    }
    window.addEventListener('gameplay:open-documents', handler)
    return ()=>{
      window.removeEventListener('gameplay:open-documents', handler)
    }
  },[])

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
    if(playerRunMode){
      entries.push({id:'player-run', title: 'Player-run session', subtitle: 'AI narration disabled'})
    }
    if(waitingDisplay){
      entries.push({id:'waiting', title: `Waiting on ${waitingDisplay}`, subtitle: 'Ready when they are'})
    }
    return entries
  }, [campaignTitle, waitingDisplay, sessionId, playerRunMode])

  const [bannerIndex, setBannerIndex] = useState(0)
  useEffect(()=>{
    if(!banners.length) return
    const id = window.setInterval(()=>{
      setBannerIndex((i)=> (i + 1) % banners.length)
    }, 6000)
    return ()=>window.clearInterval(id)
  }, [banners.length])
  const activeBanner = banners[bannerIndex % (banners.length || 1)]
  const selectedCharacter = useMemo(() => {
    if(!roster.length) return undefined
    if(!selectedCharId) return roster[0]
    return roster.find(c => c.id === selectedCharId) ?? roster[0]
  }, [roster, selectedCharId])

  const playerStats = selectedCharacter

  const partyRoster = useMemo((): CharacterSummary[] => {
    const members = Array.isArray(partyData?.members) ? partyData.members : []
    const meEmail = (currentUserEmail || '').trim().toLowerCase()
    const meUser = (currentUsername || '').trim().toLowerCase()

    const toNum = (value: any): number | null => {
      const parsed = typeof value === 'number' ? value : Number(value)
      return Number.isFinite(parsed) ? parsed : null
    }

    const toStringArray = (value: any): string[] => {
      if(Array.isArray(value)) return value.map(v => String(v))
      return []
    }

    const toSkillArray = (value: any): { name: string; mod: number }[] => {
      if(!Array.isArray(value)) return []
      return value
        .map((raw: any) => {
          if(typeof raw === 'string') return { name: raw, mod: 0 }
          const name = String(raw?.name ?? '').trim()
          const mod = toNum(raw?.mod) ?? 0
          if(!name) return null
          return { name, mod }
        })
        .filter(Boolean) as any
    }

    return members
      .filter((m: any) => {
        const email = String(m?.email || '').toLowerCase()
        const username = String(m?.username || '').toLowerCase()
        if(meEmail && email && email === meEmail) return false
        if(meUser && username && username === meUser) return false
        return true
      })
      .map((m: any) => {
        const ch = m?.character
        if(!ch) return null
        const sheet = (ch?.sheet && typeof ch.sheet === 'object') ? ch.sheet : {}
        const hpCurrent = toNum(sheet?.hp?.current ?? sheet?.hp_current) ?? 10
        const hpMax = toNum(sheet?.hp?.max ?? sheet?.hp_max) ?? Math.max(hpCurrent, 10)
        const hpTemp = toNum(sheet?.hp?.temp ?? sheet?.hp_temp) ?? 0
        const ac = toNum(sheet?.ac) ?? 10
        const spellSave = toNum(sheet?.spell_save ?? sheet?.spellSave ?? sheet?.spell_save_dc ?? sheet?.spellSaveDc) ?? 10
        const stats = (sheet?.stats && typeof sheet.stats === 'object') ? sheet.stats : {}
        const inventory = toStringArray(sheet?.inventory)
        const spells = toStringArray(sheet?.spells)
        const spellbook = Array.isArray(sheet?.spellbook) ? sheet.spellbook : []
        const features = toStringArray(sheet?.features)
        const skills = toSkillArray(sheet?.skills)
        const exhaustion = typeof sheet?.exhaustion === 'number' ? sheet.exhaustion : 0
        const rawDs = sheet?.death_saves ?? sheet?.deathSaves
        const deathSaves = rawDs && typeof rawDs === 'object'
          ? { successes: toNum(rawDs.successes) ?? 0, failures: toNum(rawDs.failures) ?? 0 }
          : { successes: 0, failures: 0 }
        const spellSlots = (sheet?.spell_slots && typeof sheet.spell_slots === 'object') ? sheet.spell_slots : undefined
        const id = String(ch?.id ?? '')
        if(!id) return null
        return {
          id,
          name: String(ch?.name ?? m?.character_name ?? m?.name ?? 'Party member'),
          level: toNum(ch?.level) ?? 1,
          hp: { current: hpCurrent, max: hpMax, temp: hpTemp || undefined },
          ac,
          spellSave,
          stats: {
            str: toNum(stats?.str) ?? 10,
            dex: toNum(stats?.dex) ?? 10,
            wis: toNum(stats?.wis) ?? 10,
          },
          features,
          inventoryCount: typeof sheet?.inventoryCount === 'number' ? sheet.inventoryCount : inventory.length,
          journalEntries: typeof sheet?.journalEntries === 'number' ? sheet.journalEntries : 0,
          skills,
          inventory,
          spells,
          spellbook,
          exhaustion,
          deathSaves,
          spellSlots,
        } as CharacterSummary
      })
      .filter(Boolean) as CharacterSummary[]
  }, [partyData, currentUserEmail, currentUsername])

  useEffect(() => {
    // Keep the party selection valid as the remote party changes.
    if(!partyRoster.length){
      setPartySelectedId(null)
      return
    }
    if(partySelectedId && partyRoster.some(c => String(c.id) === String(partySelectedId))) return
    setPartySelectedId(String(partyRoster[0].id))
  }, [partyRoster, partySelectedId])

  useEffect(() => {
    let canceled = false
    async function loadParty(){
      if(!sessionId){
        setPartyData(null)
        setPartyError(null)
        return
      }
      try{
        const res = await apiFetch(`/sessions/${sessionId}/party`)
        if(!res.ok) throw new Error('party fetch failed')
        const data = await res.json().catch(() => null)
        if(!canceled) {
          setPartyData(data)
          setPartyError(null)
        }
      }catch(err: any){
        if(!canceled) {
          setPartyError(err?.message || 'Unable to load party')
          setPartyData(null)
        }
      }
    }
    loadParty()
    return () => { canceled = true }
  }, [sessionId])

  useEffect(() => {
    // Refresh party data when the Party drawer is opened.
    let canceled = false
    async function refresh(){
      if(!sessionId) return
      if(!(drawerOpen && drawerView === 'party')) return
      try{
        const res = await apiFetch(`/sessions/${sessionId}/party`)
        if(!res.ok) return
        const data = await res.json().catch(() => null)
        if(!canceled) {
          setPartyData(data)
          setPartyError(null)
        }
      }catch{
        // ignore
      }
    }
    refresh()
    return () => { canceled = true }
  }, [drawerOpen, drawerView, sessionId])

  useEffect(() => {
    // Username search for invite autocomplete
    let canceled = false
    const raw = inviteEmail.trim()
    if(!raw || raw.includes('@') || raw.length < 2){
      setInviteMatches([])
      return
    }
    setInviteMatchBusy(true)
    const id = window.setTimeout(async () => {
      try{
        const res = await apiFetch(`/users/search?q=${encodeURIComponent(raw)}&limit=8`)
        if(!res.ok) throw new Error('search failed')
        const data = await res.json().catch(() => null)
        const results = Array.isArray(data?.results) ? data.results : []
        if(!canceled) setInviteMatches(results)
      }catch{
        if(!canceled) setInviteMatches([])
      }finally{
        if(!canceled) setInviteMatchBusy(false)
      }
    }, 250)
    return () => {
      canceled = true
      window.clearTimeout(id)
    }
  }, [inviteEmail])

  async function handleInviteSubmit(){
    if(!sessionId){
      setInviteMessage('No active session to invite into.')
      return
    }
    if(!inviteEmail.trim()){
      setInviteMessage('Enter an email to invite.')
      return
    }
    setInviteBusy(true)
    setInviteMessage(null)
    try{
      const res = await apiFetch(`/sessions/${sessionId}/invite`,{
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: inviteEmail.trim(), note: inviteNote.trim() || undefined })
      })
      if(!res.ok){
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || 'Invite failed')
      }
      setInviteEmail('')
      setInviteNote('')
      setInviteMessage('Invite sent.')
      setShowInviteForm(false)
      try{
        const res2 = await apiFetch(`/sessions/${sessionId}/party`)
        if(res2.ok){
          const data2 = await res2.json().catch(() => null)
          setPartyData(data2)
        }
      }catch{
        // ignore
      }
    }catch(err: any){
      setInviteMessage(err?.message || 'Unable to send invite right now.')
    }finally{
      setInviteBusy(false)
    }
  }

  const drawerWidth = (drawerView === 'party' || drawerView === 'documents') ? 520 : 320

  return (
    <div
      className={`gameplay-root ${drawerOpen ? 'drawer-open' : ''}`}
      style={{ ['--drawer-width' as any]: `${drawerWidth}px` }}
    >
      <div className={`drawer-scrim ${drawerOpen ? 'visible' : ''}`} onClick={closeDrawer} aria-hidden={!drawerOpen} />
      <aside className={`site-panel ${drawerOpen ? 'open' : ''}`} aria-label="Site Panel">
        {drawerView === 'party' ? (
          <div className="site-menu-panel">
            <header className="site-menu-header">
              <div>
                <div className="site-menu-title">Party</div>
                <div className="site-menu-subtitle">Other party members (NPCs or invited players)</div>
              </div>
              <div style={{display:'flex',gap:8,alignItems:'center'}}>
                <button
                  className="btn btn-secondary btn-sm"
                  type="button"
                  onClick={() => { setInviteMessage(null); setShowInviteForm(v => !v) }}
                  disabled={!sessionId}
                  title={!sessionId ? 'Start or select a session first' : undefined}
                >
                  Invite Player
                </button>
                <button className="site-menu-close" onClick={() => { setDrawerView('panels'); closeDrawer() }} aria-label="Close menu">
                  ✕
                </button>
              </div>
            </header>

            {showInviteForm ? (
              <div className="card card-pad" style={{display:'grid',gap:10}}>
                <div style={{fontWeight:750}}>Invite a player</div>
                <input
                  className="input"
                  placeholder="username or email"
                  value={inviteEmail}
                  onChange={(e)=>setInviteEmail(e.target.value)}
                  disabled={inviteBusy}
                />
                {inviteMatchBusy ? (
                  <div className="muted" style={{fontSize:12}}>Searching…</div>
                ) : inviteMatches.length ? (
                  <div className="card" style={{padding:10, display:'grid', gap:8}}>
                    <div className="muted" style={{fontSize:12}}>Matches</div>
                    {inviteMatches.map((m) => {
                      const key = String(m?.id ?? m?.email ?? m?.username ?? Math.random())
                      const label = m?.username ? `@${m.username}` : (m?.email || 'user')
                      const sub = m?.name && m?.name !== m?.username ? String(m.name) : (m?.email || '')
                      return (
                        <button
                          key={key}
                          className="btn btn-secondary btn-sm"
                          type="button"
                          onClick={() => {
                            setInviteEmail(m?.username || m?.email || '')
                            setInviteMatches([])
                          }}
                          style={{textAlign:'left'}}
                        >
                          <div style={{fontWeight:700}}>{label}</div>
                          {sub ? <div className="muted" style={{fontSize:12}}>{sub}</div> : null}
                        </button>
                      )
                    })}
                  </div>
                ) : null}
                <textarea
                  className="input"
                  placeholder="Optional note"
                  rows={2}
                  value={inviteNote}
                  onChange={(e)=>setInviteNote(e.target.value)}
                  disabled={inviteBusy}
                />
                {inviteMessage ? <div className="muted" style={{fontSize:12}}>{inviteMessage}</div> : null}
                <div style={{display:'flex',justifyContent:'flex-end',gap:8}}>
                  <button className="btn btn-quiet btn-sm" type="button" onClick={() => setShowInviteForm(false)} disabled={inviteBusy}>
                    Cancel
                  </button>
                  <button className="btn btn-sm" type="button" onClick={handleInviteSubmit} disabled={inviteBusy}>
                    {inviteBusy ? 'Sending…' : 'Send Invite'}
                  </button>
                </div>
              </div>
            ) : inviteMessage ? (
              <div className="inline-alert" style={{marginBottom: 12}}>{inviteMessage}</div>
            ) : null}

            {partyError ? (
              <div className="inline-alert inline-alert-error">{partyError}</div>
            ) : null}

            {Array.isArray(partyData?.invites) && partyData.invites.length ? (
              <div className="character-panel-block" style={{marginTop: 0}}>
                <div className="character-panel-block-title">Invited players</div>
                <ul className="character-panel-npcs">
                  {partyData.invites.map((inv: any) => (
                    <li key={String(inv?.email)}>
                      <strong>{inv?.username ? `@${inv.username}` : inv?.email}</strong>
                      {inv?.note ? <span className="muted"> — {String(inv.note)}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {Array.isArray(partyData?.npcs) && partyData.npcs.length ? (
              <div className="character-panel-block" style={{marginTop: 0}}>
                <div className="character-panel-block-title character-panel-block-title--npc">NPCs</div>
                <ul className="character-panel-npcs">
                  {partyData.npcs.map((npc: any) => (
                    <li key={String(npc?.name || Math.random())}>
                      <strong>{String(npc?.name || 'Unknown NPC')}</strong>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <CharacterPanel
              title="Other party members"
              roster={partyRoster}
              selectedId={partySelectedId}
              onSelect={(id) => setPartySelectedId(id)}
              showRoster={true}
            />
          </div>
        ) : drawerView === 'documents' ? (
          <div className="site-menu-panel">
            <header className="site-menu-header">
              <div>
                <div className="site-menu-title">Documents</div>
                <div className="site-menu-subtitle">Reference notes and uploaded files</div>
              </div>
              <button className="site-menu-close" onClick={() => { setDrawerView('panels'); closeDrawer() }} aria-label="Close menu">
                ✕
              </button>
            </header>
            <DocumentsPanel sessionId={sessionId} />
          </div>
        ) : drawerView === 'site' ? (
          <SiteNavMenu
            onClose={() => {
              closeDrawer()
            }}
            onNavigate={(key) => {
              closeDrawer()
              onNavigate?.(key)
            }}
            isAdmin={isAdmin}
          />
        ) : (
          <SiteMenu
            onClose={() => {
              setDrawerView('panels')
              closeDrawer()
            }}
            onOpenCharacters={() => { setDrawerView('party'); openDrawer() }}
            onOpenDocuments={() => { setDrawerView('documents'); openDrawer() }}
          />
        )}
      </aside>
      <main className="gameplay-main">
        <section className="session-banner" aria-live="polite">
          <div className="session-banner-row">
            <div style={{ minWidth: 0 }}>
              <div className="session-banner-title">{activeCampaign?.name || activeBanner?.title}</div>
              <div className="session-banner-subtitle">
                {sessionStarted ? 'In play' : 'Not started yet'}
              </div>
            </div>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
              <button
                className={`notification-bell ${notificationsPending ? 'notification-bell--pending' : ''}`}
                type="button"
                aria-label={notificationsPending ? 'Unread notifications' : 'No notifications'}
                title={notificationsPending ? 'Unread notifications' : 'No notifications'}
                onClick={onNotificationsClick}
                disabled={!onNotificationsClick}
              >
                {notificationsPending ? <BellUnreadIcon /> : <BellIcon />}
              </button>
              <div style={{ position: 'relative' }}>
                <button
                  className="btn btn-secondary btn-sm"
                  type="button"
                  onClick={() => setSettingsMenuOpen((v) => !v)}
                  aria-label="Session settings"
                >
                  ⚙ Settings
                </button>
                {settingsMenuOpen && (
                  <>
                    <div
                      style={{ position: 'fixed', inset: 0, zIndex: 499 }}
                      onClick={() => setSettingsMenuOpen(false)}
                    />
                    <div
                      style={{
                        position: 'absolute',
                        top: '100%',
                        right: 0,
                        marginTop: 4,
                        background: 'var(--surface-dark)',
                        border: '1px solid var(--tt-border)',
                        borderRadius: 8,
                        boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
                        minWidth: 200,
                        zIndex: 500,
                        padding: '6px 0',
                      }}
                    >
                      <button
                        className="btn btn-quiet"
                        type="button"
                        style={{ width: '100%', textAlign: 'left', padding: '8px 14px', borderRadius: 0, fontSize: 13 }}
                        onClick={() => {
                          setSettingsMenuOpen(false)
                          setDrawerView('documents')
                          openDrawer()
                        }}
                      >
                        📄 Manage Session Documents
                      </button>
                      <button
                        className="btn btn-quiet"
                        type="button"
                        style={{ width: '100%', textAlign: 'left', padding: '8px 14px', borderRadius: 0, fontSize: 13 }}
                        onClick={() => {
                          setSettingsMenuOpen(false)
                          setDrawerView('party')
                          openDrawer()
                        }}
                      >
                        👥 Manage Session Characters
                      </button>
                      <div style={{ borderTop: '1px solid var(--tt-border)', margin: '4px 0' }} />
                      <button
                        className="btn btn-quiet"
                        type="button"
                        style={{ width: '100%', textAlign: 'left', padding: '8px 14px', borderRadius: 0, fontSize: 13 }}
                        onClick={async () => {
                          setSettingsMenuOpen(false)
                          if (!sessionId) return alert('No active session')
                          try {
                            const res = await apiFetch('/narrative/regenerate', { method: 'POST', body: JSON.stringify({ session_id: sessionId }) })
                            if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d?.detail || 'Failed') }
                            const data = await res.json()
                            if (data?.narrative) {
                              window.dispatchEvent(new CustomEvent('narrative:scene', {
                                detail: {
                                  scene: {
                                    id: `regen-${Date.now()}`,
                                    title: 'Regenerated Scene',
                                    text: `${data.narrative}\n\n${data.prompt || ''}`.trim(),
                                    image: null,
                                    choices: [
                                      { id: 'investigate', label: 'Investigate the most immediate clue' },
                                      { id: 'talk',        label: 'Talk to someone nearby' },
                                      { id: 'press_on',   label: 'Press on toward the obvious destination' },
                                      { id: 'plan',        label: 'Huddle and make a plan' },
                                    ],
                                  }
                                }
                              }))
                            }
                          } catch (err: any) { alert(err?.message || 'Failed to regenerate scene') }
                        }}
                      >
                        🔄 Regenerate Scene
                      </button>
                    </div>
                  </>
                )}
              </div>
              <button className="btn btn-primary btn-sm" type="button" onClick={async ()=>{
                if(!sessionId) return alert('No active session')
                try{
                  const res = await apiFetch(`/sessions/${sessionId}/advance-scene`, { method: 'POST', body: JSON.stringify({}) })
                  if(!res.ok){ const d = await res.json().catch(()=>({})); throw new Error(d?.detail||'Failed') }
                  const data = await res.json()
                  if(data?.scene && typeof data.scene === 'object'){
                    window.dispatchEvent(new CustomEvent('narrative:scene',{ detail: { scene: data.scene } }))
                  }
                  if(data?.context_debug){
                    setContextDebug(data.context_debug)
                  }
                  if(data?.story_debug){
                    setStoryDebug(data.story_debug)
                  }
                }catch(err:any){ alert(err?.message || 'Failed to continue scene') }
              }}>Continue</button>
            </div>
          </div>
        </section>
        <section className="gameplay-body" aria-label="HomeScreen">
          <div className="home-screen" aria-label="HomeScreen">
            <section className="zork-screen" aria-label="Main view screen">
              <div className="zork-screen-inner">
                <section className="scene-area" aria-label="Scene view">
                  <NarrativeView sessionId={sessionId} showChoicesInScene={true} />
                </section>
              </div>
            </section>
          </div>

          <aside className="session-panel" aria-label="Session Panel">
            <div className="session-panel-tabs" role="tablist" aria-label="Session Panel tabs">
              <button
                type="button"
                role="tab"
                className={rightTab === 'character' ? 'session-panel-tab active' : 'session-panel-tab'}
                aria-selected={rightTab === 'character'}
                onClick={() => setRightTab('character')}
              >
                Character
              </button>

              <button
                type="button"
                role="tab"
                className={rightTab === 'journal' ? 'session-panel-tab active' : 'session-panel-tab'}
                aria-selected={rightTab === 'journal'}
                onClick={() => setRightTab('journal')}
              >
                Journal
              </button>
              <button
                type="button"
                role="tab"
                className={rightTab === 'world' ? 'session-panel-tab active' : 'session-panel-tab'}
                aria-selected={rightTab === 'world'}
                onClick={() => setRightTab('world')}
              >
                World
              </button>
            </div>

            <div className="session-panel-body" role="tabpanel">
              {rightTab === 'character' ? (
                <div className="player-sheet" aria-label="Your character sheet">
                  <div className="player-sheet-inner">
                    {roster.length > 1 ? (
                      <div className="row-wrap" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
                        <label className="muted" style={{ fontSize: 12 }}>
                          Active character
                        </label>
                        <select
                          className="input"
                          style={{ maxWidth: 220 }}
                          value={selectedCharId || roster[0]?.id}
                          onChange={(e) => {
                            const nextId = e.target.value
                            if (nextId && onSelectCharId) onSelectCharId(nextId)
                          }}
                        >
                          {roster.map((entry) => (
                            <option key={entry.id} value={entry.id}>
                              {entry.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    ) : null}
                    <CharacterPanel
                      title="Your character"
                      roster={playerStats ? [playerStats] : []}
                      selectedId={playerStats ? String(playerStats.id) : null}
                      showRoster={false}
                      sceneCues={sceneCues}
                      npcSpotlight={npcSpotlight}
                      onCueRoll={triggerCueRoll}
                      onGoToCharacters={onGoToCharacters}
                      onGoToImport={onGoToImport}
                      onSheetUpdate={handleSheetUpdate}
                      onQuickAction={handleQuickAction}
                      sessionId={sessionId || null}
                    />
                  </div>
                </div>
              ) : null}

              {rightTab === 'journal' ? (
                <JournalPanel sessionId={sessionId || null} />
              ) : null}

              {rightTab === 'world' ? (
                <WorldPanel campaignId={activeCampaignId} />
              ) : null}
            </div>
          </aside>
        </section>
      </main>

      {/* Context Debug Panel — dev mode only */}
      {process.env.NODE_ENV === 'development' && contextDebug ? (
        <>
          <button
            className="context-debug-trigger"
            title="Context Debug"
            onClick={() => setShowContextDebug(v => !v)}
          >
            {showContextDebug ? '✕' : '🔍'}
          </button>
          {showContextDebug ? (
            <ContextDebugPanel
              data={contextDebug}
              onClose={() => setShowContextDebug(false)}
            />
          ) : null}
        </>
      ) : null}

      {/* Story Dashboard — dev mode only */}
      {process.env.NODE_ENV === 'development' && storyDebug ? (
        <>
          <button
            className="sd-trigger"
            title="Story Dashboard"
            onClick={() => setShowStoryDash(v => !v)}
          >
            {showStoryDash ? '✕' : '📖'}
          </button>
          {showStoryDash ? (
            <StoryDashboard
              data={storyDebug}
              onClose={() => setShowStoryDash(false)}
            />
          ) : null}
        </>
      ) : null}
    </div>
  )
}
