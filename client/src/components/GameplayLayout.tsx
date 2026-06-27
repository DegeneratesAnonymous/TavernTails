import React, {useCallback, useEffect, useMemo, useState} from 'react'
import './GameplayLayout.css'
import NarrativeView, { EntityHint } from './NarrativeView'
import CharacterPanel, {CharacterSummary, SceneCue} from './CharacterPanel'
import DocumentsPanel from './DocumentsPanel'
import JournalPanel from './JournalPanel'
import SessionDayLog from './SessionDayLog'
import WorldPanel from './WorldPanel'
import ContextDebugPanel from './ContextDebugPanel'
import StoryDashboard, { StoryDashboardData } from './StoryDashboard'
import Chat from './Chat'
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
  const [sessionMode, setSessionMode] = useState<'read' | 'play' | 'world'>('play')
  const [focusMode, setFocusMode] = useState(false)
  const [mobileTab, setMobileTab] = useState<'story' | 'action' | 'character' | 'journal' | 'world'>('story')
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

  const handleQuickAction = useCallback((action: {type: string; detail?: string}) => {
    if (!action.detail) return
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
  const [sceneQuality, setSceneQuality] = useState<{score: number; passed: boolean; detail: any} | null>(null)
  const [actionDraft, setActionDraft] = useState<string | null>(null)
  const [experienceMode, setExperienceMode] = useState<string>('quiet_scene')
  const [memoryUpdates, setMemoryUpdates] = useState<any | null>(null)
  const [worldClock, setWorldClock] = useState<Record<string, any>>({})

  // Live situation context (populated from scene data)
  const [situation, setSituation] = useState<{
    location?: string
    weather?: string
    timeOfDay?: string
    mood?: string
    threat?: string
    threads?: string[]
    stakes?: string
    hooks?: string[]         // "The World Moves" legacy field
    worldMoves?: string[]    // preferred: scene world_moves
    visibleClues?: string[]
    currentObjective?: string
    activeThread?: string
    knownDanger?: string
    timePressure?: string
    storyThreads?: Array<{title?: string; status?: string; last_update?: string}>
    relationshipsChanged?: any[]
  }>({})

  // Situation-aware UI payload (from content bundle)
  const [uiPayload, setUiPayload] = useState<Record<string, any>>({})
  const [situationType, setSituationType] = useState<string>('')
  const [resolutionState, setResolutionState] = useState<string>('idle')

  // Developer debug overlay
  const [debugPayload, setDebugPayload] = useState<Record<string, any>>({})
  const [showDebugOverlay, setShowDebugOverlay] = useState(false)

  // Read Mode drawers
  const [readLeftOpen, setReadLeftOpen] = useState(false)
  const [readRightOpen, setReadRightOpen] = useState(false)

  const [situationOpen, setSituationOpen] = useState(false)
  const [worldMovesOpen, setWorldMovesOpen] = useState(false)
  const [rollToolsOpen, setRollToolsOpen] = useState(false)

  // Session round-flow state
  const [phase, setPhase] = useState<'player_turn' | 'advancing'>('player_turn')
  const [phaseLabel, setPhaseLabel] = useState('')
  const [playerReady, setPlayerReady] = useState(false)
  const [chatLogCollapsed, setChatLogCollapsed] = useState(false)
  const [diceRolls, setDiceRolls] = useState<Array<{type: string; skill?: string; reason?: string}>>([])

  useEffect(() => {
    setChatLogCollapsed(false)
  }, [sessionId])

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
    const handler = (event: Event)=>{
      const action = String((event as CustomEvent).detail?.action || '').trim()
      if(!action) return
      setActionDraft(action)
    }
    window.addEventListener('narrative:suggest-action', handler)
    return ()=>window.removeEventListener('narrative:suggest-action', handler)
  },[])

  useEffect(() => {
    if (sessionMode === 'world') setRightTab('journal')
    if (sessionMode === 'play') setRightTab('character')
  }, [sessionMode])

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
          window.dispatchEvent(new CustomEvent('rolls:result', { detail: data }))
          if(data?.by){
            window.dispatchEvent(new CustomEvent('session:waiting',{detail:{player: data.by, reason: 'beyond20', expiresMs: 6000}}))
          }
        }
        if(data?.type === 'rolls.result'){
          const res = data?.result || {}
          setRemoteRoll({by: res.by, total: res.total, expression: res.expression})
          window.dispatchEvent(new CustomEvent('rolls:result', { detail: data }))
        }
        if(data?.type === 'chat.message'){
          window.dispatchEvent(new CustomEvent('chat:message', { detail: data.message }))
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

  const doAdvanceScene = useCallback(async (openingApproach?: string) => {
    if (!sessionId) return
    setPhase('advancing')
    setPhaseLabel('Analysing player actions…')
    setPlayerReady(false)
    setDiceRolls([])
    const labelTimer = window.setTimeout(() => setPhaseLabel('Directing the scene…'), 8000)
    const labelTimer2 = window.setTimeout(() => setPhaseLabel('Writing the narrative…'), 22000)
    try {
      const body: Record<string, unknown> = {}
      if (openingApproach) body.opening_approach = openingApproach
      const res = await apiFetch(`/sessions/${sessionId}/advance-scene`, { method: 'POST', body: JSON.stringify(body) })
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d?.detail || d?.error || 'Failed to advance scene') }
      const data = await res.json()
      if (data?.scene && typeof data.scene === 'object') {
        setPhaseLabel('Scene ready!')
        window.dispatchEvent(new CustomEvent('narrative:scene', { detail: { scene: data.scene } }))
      }
      if (Array.isArray(data?.dice_rolls) && data.dice_rolls.length) {
        setDiceRolls(data.dice_rolls)
      }
      if (data?.context_debug) setContextDebug(data.context_debug)
      if (data?.simulation_debug) setContextDebug((prev: any) => ({ ...(prev || {}), simulation: data.simulation_debug }))
      if (data?.story_debug) setStoryDebug(data.story_debug)
      // Capture full debug payload for developer overlay
      if (data?.simulation_debug || data?.ui_payload || data?.situation_type) {
        setDebugPayload({
          campaign_contract: data?.simulation_debug?.campaign_contract || {},
          world_tick: data?.simulation_debug?.time_resolver || {},
          simulation_delta: data?.simulation_debug?.simulation_delta || {},
          situation_type: data?.situation_type || '',
          situation_classification: data?.situation_classification || {},
          content_bundle: data?.simulation_debug?.content_bundle || {},
          situation_validation: data?.simulation_debug?.content_bundle?.validation_result || {},
          director_output: data?.simulation_debug?.director_guidance || {},
          narrative_validation: data?.simulation_debug?.scene_validator || {},
          memory_delta: data?.simulation_debug?.memory_delta || {},
          canon_changes: data?.simulation_debug?.canon_changes || {},
          canon_validation: data?.canon_validation || {},
          ui_payload: data?.ui_payload || {},
        })
      }
      if (data?.simulation_debug?.scene_validator?.score !== undefined) {
        setSceneQuality({
          score: data.simulation_debug.scene_validator.score,
          passed: data.simulation_debug.scene_validator.score >= 75,
          detail: { failed_checks: data.simulation_debug.scene_validator.issues || [] },
        })
      } else if (data?.scene_debug?.scene_score !== undefined) {
        setSceneQuality({
          score: data.scene_debug.scene_score,
          passed: data.scene_debug.scene_score_passed,
          detail: data.scene_debug.scene_score_detail,
        })
      }
    } catch (err: any) {
      alert(err?.message || 'Failed to advance scene')
    } finally {
      window.clearTimeout(labelTimer)
      window.clearTimeout(labelTimer2)
      setPhase('player_turn')
      setPhaseLabel('')
    }
  }, [sessionId])

  useEffect(() => {
    const handler = (event: Event) => {
      const label = String((event as CustomEvent).detail?.label || '').trim()
      if (!label) return
      doAdvanceScene(label)
    }
    // @ts-ignore
    window.addEventListener('narrative:start-approach', handler)
    return () => {
      // @ts-ignore
      window.removeEventListener('narrative:start-approach', handler)
    }
  }, [doAdvanceScene])

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

  // Sync situation data from scene-meta events emitted by NarrativeView
  useEffect(() => {
    const handler = (event: Event) => {
      const s = (event as CustomEvent).detail as any
      if (!s) return
      const clock = s.world_clock || {}
      const currentSituation = s.current_situation || {}
      // Prefer world_moves (new field); fall back to hooks (legacy)
      const cleanList = (items: any[]) => items.map(item => String(item || '').trim()).filter(Boolean)
      const sceneWorldMoves = cleanList(Array.isArray(s.world_moves) ? s.world_moves : [])
      const hookMoves = cleanList(Array.isArray(s.hooks) ? s.hooks : [])
      const worldMoves = sceneWorldMoves.length > 0 ? sceneWorldMoves : hookMoves
      setWorldClock(clock)
      setExperienceMode(s.experience_mode || 'quiet_scene')
      setMemoryUpdates(s.memory_updates || null)
      if(Array.isArray(s.dice_rolls) && s.dice_rolls.length) setDiceRolls(s.dice_rolls)
      if (s.ui_payload && typeof s.ui_payload === 'object') setUiPayload(s.ui_payload)
      if (s.full_ui_payload && typeof s.full_ui_payload === 'object') {
        const rp = s.full_ui_payload.resolution_panel || {}
        if (rp.state) setResolutionState(rp.state)
      }
      if (s.situation_type) setSituationType(s.situation_type)
      setSituation({
        location: s.visual_state?.location_name || s.location || s.image?.location || '',
        weather: clock.weather || s.weather || '',
        timeOfDay: clock.time_block || s.time_of_day || '',
        mood: currentSituation.current_mood || s.visual_state?.mood || '',
        threat: currentSituation.current_threat || clock.threat_level || s.visual_state?.threat_level || '',
        threads: Array.isArray(s.active_threads) ? s.active_threads : [],
        stakes: currentSituation.immediate_stakes || s.immediate_stakes || '',
        hooks: hookMoves,
        worldMoves,
        visibleClues: Array.isArray(currentSituation.visible_clues) ? currentSituation.visible_clues : (Array.isArray(s.visible_clues) ? s.visible_clues : []),
        currentObjective: currentSituation.current_objective || s.current_objective || '',
        activeThread: currentSituation.active_thread || s.active_thread || '',
        knownDanger: currentSituation.known_danger || '',
        timePressure: currentSituation.time_pressure || '',
        storyThreads: Array.isArray(s.story_threads) ? s.story_threads : [],
        relationshipsChanged: Array.isArray(s.relationships_changed) ? s.relationships_changed : [],
      })
    }
    // @ts-ignore
    window.addEventListener('narrative:scene-meta', handler)
    return () => {
      // @ts-ignore
      window.removeEventListener('narrative:scene-meta', handler)
    }
  }, [])

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
  const formatClockPart = (value: any) => String(value || '').replace(/_/g, ' ')
  const experienceLabel = experienceMode.replace(/_/g, ' ')
  const selectedCharacter = useMemo(() => {
    if(!roster.length) return undefined
    if(!selectedCharId) return roster[0]
    return roster.find(c => c.id === selectedCharId) ?? roster[0]
  }, [roster, selectedCharId])

  const playerStats = selectedCharacter
  const observedSummary = (situation.visibleClues || []).slice(0, 3).join(', ')
  const currentRisk = situation.timePressure || situation.knownDanger || situation.stakes || ''
  const situationPreview = [
    situation.currentObjective || situation.activeThread || null,
    situation.stakes ? `Stakes: ${situation.stakes}` : null,
  ].filter(Boolean).join(' • ')
  const worldMovesPreview = (
    situation.worldMoves && situation.worldMoves.length > 0
      ? situation.worldMoves[0]
      : (situation.hooks || [])[0]
  ) || ''
  const encounterActive = /combat|encounter|imminent|danger/i.test(experienceMode)
    || Boolean(situation.threat && !/safe|quiet|none/i.test(situation.threat))
    || npcSpotlight.length > 0
    || sceneCues.length > 0
  const playerInitiativeMod = Math.floor(((Number(playerStats?.stats?.dex) || 10) - 10) / 2)
  const resolutionOptions = suggestions.slice(0, 5)

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

  // Entity hints for NarrativeView — character names/roles the player can hover to recall.
  const entityHints = useMemo((): EntityHint[] => {
    const hints: EntityHint[] = []
    // Other party members (PCs)
    for (const c of partyRoster) {
      if (!c.name) continue
      hints.push({
        name: c.name,
        role: [c.class_name, c.level ? `Lv.${c.level}` : ''].filter(Boolean).join(' ') || 'Party member',
      })
    }
    // NPCs present in the session
    for (const npc of (Array.isArray(partyData?.npcs) ? partyData.npcs : [])) {
      if (!npc?.name) continue
      hints.push({
        name: String(npc.name),
        role: npc.role ?? npc.type ?? 'NPC',
        description: npc.description ?? npc.notes ?? undefined,
      })
    }
    // NPC spotlight (from live scene analysis)
    for (const n of npcSpotlight) {
      if (!n.name || hints.some(h => h.name.toLowerCase() === n.name.toLowerCase())) continue
      hints.push({ name: n.name, role: 'NPC' })
    }
    return hints
  }, [partyRoster, partyData, npcSpotlight])

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
      className={`gameplay-root session-mode-${sessionMode} mobile-tab-${mobileTab} ${focusMode ? 'focus-mode' : ''} ${drawerOpen ? 'drawer-open' : ''}`}
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
            <div className="session-banner-main">
              <div className="session-banner-title">{activeCampaign?.name || activeBanner?.title}</div>
              <div className="session-world-line">
                {sessionStarted ? (
                  <span className="session-banner-context">
                    {worldClock.campaign_day ? (
                      <span>Day {worldClock.campaign_day}</span>
                    ) : null}
                    {situation.timeOfDay ? (
                      <span>{situation.timeOfDay.charAt(0).toUpperCase() + situation.timeOfDay.slice(1)}</span>
                    ) : null}
                    {situation.weather ? (
                      <span>{situation.weather}</span>
                    ) : null}
                    {worldClock.wind_direction ? (
                      <span>{`Wind ${String(worldClock.wind_direction).toUpperCase()}${worldClock.wind_strength ? ` ${formatClockPart(worldClock.wind_strength)}` : ''}`}</span>
                    ) : null}
                    {worldClock.moon_phase ? (
                      <span>{formatClockPart(worldClock.moon_phase)}</span>
                    ) : null}
                  </span>
                ) : 'Not started yet'}
              </div>
              <div className="session-location-line">
                {sessionStarted ? (
                  <>
                    {situation.location ? (
                      <span>{situation.location}</span>
                    ) : null}
                    {situation.activeThread ? (
                      <span>Thread: {situation.activeThread}</span>
                    ) : null}
                    {situation.threat ? (
                      <span className="session-threat-text">Threat: {situation.threat}</span>
                    ) : null}
                  </>
                ) : activeBanner?.subtitle}
              </div>
            </div>
            <div className="session-banner-controls">
              <div className="session-mode-switch" role="tablist" aria-label="Session view mode">
                {(['read', 'play', 'world'] as const).map(mode => (
                  <button
                    key={mode}
                    type="button"
                    role="tab"
                    className={`session-mode-btn ${sessionMode === mode ? 'active' : ''}`}
                    aria-selected={sessionMode === mode}
                    onClick={() => {
                      setSessionMode(mode)
                      if (mode === 'world') setRightTab('journal')
                      if (mode === 'read') setRightTab('character')
                      setMobileTab(mode === 'world' ? 'world' : 'story')
                    }}
                  >
                    {mode.charAt(0).toUpperCase() + mode.slice(1)}
                  </button>
                ))}
              </div>
              <button
                className={`session-focus-btn ${focusMode ? 'active' : ''}`}
                type="button"
                onClick={() => {
                  setFocusMode(v => {
                    const next = !v
                    if (next) {
                      setSessionMode('play')
                      setMobileTab('story')
                    }
                    return next
                  })
                }}
                aria-pressed={focusMode}
              >
                Focus
              </button>
              <button
                className={`session-debug-btn ${showDebugOverlay ? 'active' : ''}`}
                type="button"
                onClick={() => setShowDebugOverlay(v => !v)}
                aria-pressed={showDebugOverlay}
                title="Developer debug overlay"
              >
                Debug
              </button>
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
                  className="session-settings-btn"
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
                          setPhase('advancing')
                          setPhaseLabel('Regenerating scene…')
                          const t1 = window.setTimeout(() => setPhaseLabel('Writing narrative…'), 10000)
                          try {
                            const res = await apiFetch('/narrative/regenerate', {
                              method: 'POST',
                              body: JSON.stringify({ session_id: sessionId, player: playerStats?.name || undefined })
                            })
                            if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d?.detail || d?.error || 'Failed to regenerate scene') }
                            const data = await res.json()
                            if (data?.narrative) {
                              setPhaseLabel('Scene ready!')
                              // Reload from scene.json so we get the full scene with location/image
                              const sceneRes = await apiFetch(`/sessions/${sessionId}/file/scene.json`).catch(() => null)
                              const sceneData = sceneRes?.ok ? await sceneRes.json().catch(() => null) : null
                              window.dispatchEvent(new CustomEvent('narrative:scene', {
                                detail: {
                                  scene: sceneData ?? {
                                    id: `regen-${Date.now()}`,
                                    title: situation.location || 'Scene',
                                    narrative_body: data.narrative,
                                    player_prompt: data.prompt || '',
                                    text: `${data.narrative}\n\n${data.prompt || ''}`.trim(),
                                    image: null,
                                    choices: [],
                                  }
                                }
                              }))
                            }
                          } catch (err: any) {
                            alert(err?.message || 'Failed to regenerate scene')
                          } finally {
                            window.clearTimeout(t1)
                            setPhase('player_turn')
                            setPhaseLabel('')
                          }
                        }}
                      >
                        {phase === 'advancing' ? '⏳ Regenerating…' : '🔄 Regenerate Scene'}
                      </button>
                    </div>
                  </>
                )}
              </div>
              {/* Ready button lives here — far from the chat send button */}
              {sessionId && (
                <button
                  className={`btn btn-sm session-ready-btn ${playerReady || phase === 'advancing' ? 'session-ready-btn--done' : 'btn-gold'}`}
                  disabled={playerReady || phase === 'advancing'}
                  type="button"
                  onClick={async () => {
                    if (!sessionId || playerReady || phase === 'advancing') return
                    setPlayerReady(true)
                    setChatLogCollapsed(true)
                    try {
                      const res = await apiFetch(`/sessions/${sessionId}/player-ready`, {
                        method: 'POST',
                        body: JSON.stringify({ done: true }),
                      })
                      if (!res.ok) throw new Error('Ready signal failed')
                      const data = await res.json()
                      if (data?.all_ready) await doAdvanceScene()
                    } catch {
                      setPlayerReady(false)
                      setChatLogCollapsed(false)
                    }
                  }}
                >
                  {phase === 'advancing'
                    ? '⏳ Generating…'
                    : playerReady
                    ? '✓ Ready'
                    : "I'm Ready"}
                </button>
              )}
              {isAdmin && !playerReady && phase !== 'advancing' && (
                <button
                  className="btn btn-secondary btn-sm"
                  type="button"
                  onClick={() => doAdvanceScene()}
                >
                  Force Advance
                </button>
              )}
            </div>
          </div>
        </section>
        <section className="gameplay-body" aria-label="HomeScreen">
          <div className="session-workspace-row">
          <div className="home-screen" aria-label="HomeScreen">
            <section className={`zork-screen experience-mode-${experienceMode}`} aria-label="Main view screen">
              <div className="zork-screen-inner">
                {/* Scene generation overlay */}
                {phase === 'advancing' && (
                  <div className="scene-generating-overlay" aria-live="polite" aria-label="Generating scene">
                    <div className="scene-generating-card">
                      <div className="scene-generating-spinner" aria-hidden="true" />
                      <span className="scene-generating-label">
                        {phaseLabel || 'Steward is preparing the next scene…'}
                      </span>
                    </div>
                  </div>
                )}

                {/* Scrollable narrative + situation area */}
                <section className="scene-area" aria-label="Scene view">
                  <NarrativeView
                    sessionId={sessionId}
                    entities={entityHints}
                    presentationMode={sessionMode}
                    focusMode={focusMode}
                    onExitRead={() => setSessionMode('play')}
                  />

                  {/* World Mode archive dashboard */}
                  {sessionMode === 'world' && (
                    <div className="archive-dashboard">
                      <div className="archive-dashboard-header">
                        <h2 className="archive-dashboard-title">Campaign Archive</h2>
                        <span className="archive-dashboard-subtitle">Entities, threads, and clues encountered so far</span>
                      </div>
                      {/* Recently updated */}
                      {memoryUpdates && (memoryUpdates.new_npcs?.length > 0 || memoryUpdates.new_locations?.length > 0 || memoryUpdates.new_clues?.length > 0) ? (
                        <section className="archive-section">
                          <h3 className="archive-section-title">Recently discovered</h3>
                          <div className="archive-card-grid">
                            {(memoryUpdates.new_npcs || []).slice(0, 4).map((npc: any, i: number) => (
                              <div key={`npc-${i}`} className="archive-card archive-card--npc">
                                <span className="archive-card-type">NPC</span>
                                <strong className="archive-card-name">{typeof npc === 'string' ? npc : npc?.name || '—'}</strong>
                                {typeof npc === 'object' && npc?.role ? <span className="archive-card-detail">{npc.role}</span> : null}
                                <span className={`archive-card-status archive-card-status--${typeof npc === 'object' ? (npc.canon_status || 'provisional') : 'provisional'}`}>
                                  {typeof npc === 'object' ? (npc.canon_status || 'provisional') : 'provisional'}
                                </span>
                              </div>
                            ))}
                            {(memoryUpdates.new_locations || []).slice(0, 4).map((loc: any, i: number) => (
                              <div key={`loc-${i}`} className="archive-card archive-card--location">
                                <span className="archive-card-type">Location</span>
                                <strong className="archive-card-name">{typeof loc === 'string' ? loc : loc?.name || '—'}</strong>
                                {typeof loc === 'object' && loc?.type ? <span className="archive-card-detail">{loc.type}</span> : null}
                                <span className="archive-card-status archive-card-status--provisional">provisional</span>
                              </div>
                            ))}
                            {(memoryUpdates.new_clues || []).slice(0, 3).map((clue: string, i: number) => (
                              <div key={`clue-${i}`} className="archive-card archive-card--clue">
                                <span className="archive-card-type">Clue</span>
                                <strong className="archive-card-name">{clue}</strong>
                                <span className="archive-card-status archive-card-status--canon">discovered</span>
                              </div>
                            ))}
                          </div>
                        </section>
                      ) : null}
                      {/* Active threads */}
                      {situation.threads && situation.threads.length > 0 ? (
                        <section className="archive-section">
                          <h3 className="archive-section-title">Active threads</h3>
                          <div className="archive-card-grid">
                            {situation.threads.slice(0, 6).map((thread: string, i: number) => (
                              <div key={i} className="archive-card archive-card--thread">
                                <span className="archive-card-type">Thread</span>
                                <strong className="archive-card-name">{thread}</strong>
                              </div>
                            ))}
                          </div>
                        </section>
                      ) : null}
                      {/* Current scene summary in world mode */}
                      {situation.currentObjective ? (
                        <section className="archive-section">
                          <h3 className="archive-section-title">Current scene</h3>
                          <div className="archive-scene-summary">
                            {situation.currentObjective ? <div className="archive-summary-row"><span>Objective</span><strong>{situation.currentObjective}</strong></div> : null}
                            {situation.location ? <div className="archive-summary-row"><span>Location</span><strong>{situation.location}</strong></div> : null}
                            {situation.stakes ? <div className="archive-summary-row"><span>Stakes</span><strong>{situation.stakes}</strong></div> : null}
                            {situationType ? <div className="archive-summary-row"><span>Situation</span><strong>{situationType.replace(/_/g, ' ')}</strong></div> : null}
                          </div>
                        </section>
                      ) : null}
                      {!memoryUpdates && !situation.currentObjective ? (
                        <div className="archive-empty">
                          <p>No data yet. Archive updates after each scene.</p>
                        </div>
                      ) : null}
                    </div>
                  )}

                  {/* Situation strip — current context at a glance */}
                  {(situation.location || situation.mood || situation.currentObjective || (situation.threads && situation.threads.length > 0)) && (
                    <div className="situation-strip">
                      <button
                        className="situation-strip-toggle"
                        type="button"
                        onClick={() => setSituationOpen(v => !v)}
                        aria-expanded={situationOpen}
                      >
                        <span className="situation-strip-title">
                          Current Situation
                          {!situationOpen && situationPreview ? (
                            <span className="situation-strip-preview"> — {situationPreview}</span>
                          ) : null}
                        </span>
                        <span className="situation-strip-chevron">{situationOpen ? '▲' : '▼'}</span>
                      </button>

                      {situationOpen && (
                        <div className="situation-strip-body">
                          <div className="experience-mode-label">{experienceLabel}</div>
                          <div className="situation-grid">
                            {situation.location ? (
                              <div className="situation-item">
                                <span className="situation-label">Location</span>
                                <span className="situation-value">{situation.location}</span>
                              </div>
                            ) : null}
                            {situation.timeOfDay ? (
                              <div className="situation-item">
                                <span className="situation-label">Time</span>
                                <span className="situation-value">{situation.timeOfDay.charAt(0).toUpperCase() + situation.timeOfDay.slice(1)}</span>
                              </div>
                            ) : null}
                            {situation.weather ? (
                              <div className="situation-item">
                                <span className="situation-label">Weather</span>
                                <span className="situation-value">{situation.weather}</span>
                              </div>
                            ) : null}
                            {situation.mood ? (
                              <div className="situation-item">
                                <span className="situation-label">Mood</span>
                                <span className="situation-value">{situation.mood}</span>
                              </div>
                            ) : null}
                            {situation.threat ? (
                              <div className="situation-item">
                                <span className="situation-label">Threat</span>
                                <span className="situation-value situation-value--threat">{situation.threat}</span>
                              </div>
                            ) : null}
                          </div>
                          {situation.currentObjective ? (
                            <div className="situation-stakes">
                              <span className="situation-label">Current Objective</span>
                              <span className="situation-stakes-text">{situation.currentObjective}</span>
                            </div>
                          ) : null}
                          {situation.stakes ? (
                            <div className="situation-stakes">
                              <span className="situation-label">Immediate Stakes</span>
                              <span className="situation-stakes-text">{situation.stakes}</span>
                            </div>
                          ) : null}
                          {situation.knownDanger ? (
                            <div className="situation-stakes">
                              <span className="situation-label">Known Danger</span>
                              <span className="situation-stakes-text">{situation.knownDanger}</span>
                            </div>
                          ) : null}
                          {situation.timePressure ? (
                            <div className="situation-stakes">
                              <span className="situation-label">Time Pressure</span>
                              <span className="situation-stakes-text">{situation.timePressure}</span>
                            </div>
                          ) : null}
                          {situation.visibleClues && situation.visibleClues.length > 0 ? (
                            <div className="situation-threads">
                              <span className="situation-label">Observed Details</span>
                              <ul className="situation-thread-list">
                                {situation.visibleClues.slice(0, 4).map((c, i) => (
                                  <li key={i} className="situation-thread-item">
                                    <span className="situation-thread-dot" />
                                    {c}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          {situation.activeThread ? (
                            <div className="situation-stakes">
                              <span className="situation-label">Active Thread</span>
                              <span className="situation-stakes-text">{situation.activeThread}</span>
                            </div>
                          ) : null}
                          {situation.threads && situation.threads.length > 0 ? (
                            <div className="situation-threads">
                              <span className="situation-label">Story Threads</span>
                              <ul className="situation-thread-list">
                                {situation.threads.slice(0, 4).map((t, i) => (
                                  <li key={i} className="situation-thread-item">
                                    <span className="situation-thread-dot" />
                                    {t}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          {situation.relationshipsChanged && situation.relationshipsChanged.length > 0 ? (
                            <div className="situation-threads">
                              <span className="situation-label">Relationships</span>
                              <ul className="situation-thread-list">
                                {situation.relationshipsChanged.slice(0, 3).map((item, i) => (
                                  <li key={i} className="situation-thread-item">
                                    <span className="situation-thread-dot" />
                                    {typeof item === 'string' ? item : (item?.name || item?.summary || JSON.stringify(item))}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Meanwhile — living-world events happening outside the immediate scene */}
                  {((situation.worldMoves && situation.worldMoves.length > 0) || (situation.hooks && situation.hooks.length > 0)) && (
                    <div className="world-moves-strip">
                      <button
                        className="world-moves-toggle"
                        onClick={() => setWorldMovesOpen(o => !o)}
                        aria-expanded={worldMovesOpen}
                        type="button"
                      >
                        <span className="world-moves-title">
                          Meanwhile
                          {!worldMovesOpen && worldMovesPreview ? (
                            <span className="world-moves-preview"> — {worldMovesPreview}</span>
                          ) : null}
                        </span>
                        <span className="world-moves-chevron">{worldMovesOpen ? '▲' : '▼'}</span>
                      </button>
                      {worldMovesOpen && (
                        <ul className="world-moves-list">
                          {(situation.worldMoves && situation.worldMoves.length > 0
                            ? situation.worldMoves
                            : situation.hooks || []
                          ).map((item, i) => (
                            <li key={i} className="world-moves-item">
                              <span className="world-moves-dot" />
                              {item}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  <aside className="resolution-panel" aria-label="Resolution panel">
                    <div className="resolution-panel-header">
                      <div>
                        <span className="resolution-panel-kicker">Resolution</span>
                        <strong>
                          {diceRolls.length > 0
                            ? `${diceRolls.length} check${diceRolls.length === 1 ? '' : 's'} pending`
                            : encounterActive
                            ? 'Encounter state'
                            : 'Scene state'}
                        </strong>
                      </div>
                      {diceRolls.length > 0 ? (
                        <button className="resolution-dismiss" type="button" onClick={() => setDiceRolls([])}>
                          Clear
                        </button>
                      ) : null}
                    </div>

                    {remoteRoll ? (
                      <section className="resolution-section resolution-roll-result" aria-live="polite">
                        <span className="resolution-section-label">{remoteRoll.expression || 'Roll result'}</span>
                        <div className="resolution-roll-total">{remoteRoll.total ?? '—'}</div>
                        {remoteRoll.by ? <div className="resolution-roll-by">{remoteRoll.by}</div> : null}
                      </section>
                    ) : null}

                    {diceRolls.length > 0 ? (
                      <section className="resolution-section">
                        <span className="resolution-section-label">Pending checks</span>
                        <div className="resolution-check-list">
                          {diceRolls.slice(0, 5).map((roll, i) => (
                            <button
                              key={i}
                              type="button"
                              className="resolution-check-card"
                              onClick={() => setActionDraft(`/roll 1d20 ${roll.skill || roll.type || ''}`.trim())}
                            >
                              <span>{roll.skill || roll.type || 'Roll'}</span>
                              {roll.reason ? <strong>{roll.reason}</strong> : null}
                            </button>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {encounterActive ? (
                      <section className="resolution-section">
                        <span className="resolution-section-label">Turn state</span>
                        <div className="resolution-row">
                          <span>Active</span>
                          <strong>{turnState.active || waitingDisplay || 'No active turn yet'}</strong>
                        </div>
                        {playerStats ? (
                          <div className="resolution-row">
                            <span>{playerStats.name}</span>
                            <strong>Initiative {playerInitiativeMod >= 0 ? '+' : ''}{playerInitiativeMod}</strong>
                          </div>
                        ) : null}
                        {npcSpotlight.slice(0, 4).map((npc, i) => (
                          <div key={`${npc.name}-${i}`} className="resolution-row">
                            <span>{npc.name}</span>
                            <strong>{npc.initiative_hint || 'watching'}</strong>
                          </div>
                        ))}
                      </section>
                    ) : null}

                    {/* Opening / New Scene Bundle */}
                    {(situationType === 'campaign_opening' || situationType === 'new_scene_opening') && uiPayload.objective ? (
                      <section className="resolution-section resolution-opening">
                        <span className="resolution-section-label">Scene hook</span>
                        {uiPayload.objective ? (
                          <div className="resolution-row">
                            <span>Problem</span>
                            <strong>{uiPayload.objective}</strong>
                          </div>
                        ) : null}
                        {uiPayload.key_npc ? (
                          <div className="resolution-row">
                            <span>Key NPC</span>
                            <strong>{uiPayload.key_npc}</strong>
                          </div>
                        ) : null}
                        {uiPayload.starting_question ? (
                          <div className="resolution-row resolution-row--question">
                            <span>First question</span>
                            <strong>{uiPayload.starting_question}</strong>
                          </div>
                        ) : null}
                        {Array.isArray(uiPayload.suggested_first_actions) && uiPayload.suggested_first_actions.length > 0 ? (
                          <div className="resolution-lead-list">
                            {uiPayload.suggested_first_actions.slice(0, 3).map((action: string, i: number) => (
                              <button key={i} type="button" className="resolution-lead" onClick={() => setActionDraft(action)}>
                                {action}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {/* Combat Bundle */}
                    {(situationType === 'combat_setup' || situationType === 'combat_round') && (uiPayload.enemy_cards?.length > 0 || uiPayload.victory_conditions?.length > 0) ? (
                      <section className="resolution-section resolution-combat">
                        <span className="resolution-section-label">Encounter</span>
                        {Array.isArray(uiPayload.enemy_cards) && uiPayload.enemy_cards.map((card: any, i: number) => (
                          <div key={i} className="resolution-enemy-card">
                            <span className="resolution-enemy-name">{card.name}</span>
                            {card.hp != null ? <span className="resolution-enemy-stat">HP {card.hp}</span> : null}
                            {card.ac != null ? <span className="resolution-enemy-stat">AC {card.ac}</span> : null}
                            {card.tactics ? <span className="resolution-enemy-tactics">{card.tactics}</span> : null}
                          </div>
                        ))}
                        {Array.isArray(uiPayload.terrain_features) && uiPayload.terrain_features.length > 0 ? (
                          <div className="resolution-row">
                            <span>Terrain</span>
                            <strong>{uiPayload.terrain_features.slice(0, 2).join(', ')}</strong>
                          </div>
                        ) : null}
                        {Array.isArray(uiPayload.non_combat_options) && uiPayload.non_combat_options.length > 0 ? (
                          <div className="resolution-row">
                            <span>Alternatives</span>
                            <strong>{uiPayload.non_combat_options.slice(0, 3).join(' · ')}</strong>
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {/* Dialogue / Interrogation / Social Bundle */}
                    {(situationType === 'interrogation' || situationType === 'social_conflict' || situationType === 'conversation' || situationType === 'npc_reappearance') && uiPayload.npc_name ? (
                      <section className="resolution-section resolution-dialogue">
                        <span className="resolution-section-label">
                          {situationType === 'interrogation' ? 'Interrogation' : situationType === 'social_conflict' ? 'Social conflict' : 'Conversation'}
                        </span>
                        <div className="resolution-row">
                          <span>{uiPayload.npc_name}</span>
                          <strong className={`resolution-attitude resolution-attitude--${uiPayload.npc_attitude || 'neutral'}`}>
                            {uiPayload.npc_attitude || 'neutral'}
                          </strong>
                        </div>
                        {uiPayload.npc_goal ? (
                          <div className="resolution-row">
                            <span>Wants</span>
                            <strong>{uiPayload.npc_goal}</strong>
                          </div>
                        ) : null}
                        {Array.isArray(uiPayload.known_leverage) && uiPayload.known_leverage.length > 0 ? (
                          <div className="resolution-row">
                            <span>Leverage</span>
                            <strong>{uiPayload.known_leverage.slice(0, 2).join(', ')}</strong>
                          </div>
                        ) : null}
                        {Array.isArray(uiPayload.possible_checks) && uiPayload.possible_checks.length > 0 ? (
                          <div className="resolution-lead-list">
                            {uiPayload.possible_checks.slice(0, 3).map((check: string, i: number) => (
                              <button key={i} type="button" className="resolution-lead"
                                onClick={() => setActionDraft(`I attempt ${check} against ${uiPayload.npc_name}`)}>
                                {check}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {/* Investigation Bundle */}
                    {(situationType === 'investigation' || situationType === 'mystery_reveal') && (uiPayload.mystery_question || (uiPayload.visible_clues?.length > 0)) ? (
                      <section className="resolution-section resolution-investigation">
                        <span className="resolution-section-label">Investigation</span>
                        {uiPayload.mystery_question ? (
                          <div className="resolution-row resolution-row--question">
                            <span>Question</span>
                            <strong>{uiPayload.mystery_question}</strong>
                          </div>
                        ) : null}
                        {Array.isArray(uiPayload.visible_clues) && uiPayload.visible_clues.length > 0 ? (
                          <div className="resolution-lead-list">
                            {uiPayload.visible_clues.slice(0, 4).map((clue: string, i: number) => (
                              <button key={i} type="button" className="resolution-lead"
                                onClick={() => setActionDraft(`I examine ${clue}`)}>
                                {clue}
                              </button>
                            ))}
                          </div>
                        ) : null}
                        {uiPayload.time_pressure ? (
                          <div className="resolution-row resolution-row--urgent">
                            <span>Time pressure</span>
                            <strong>{uiPayload.time_pressure}</strong>
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {/* Travel Bundle */}
                    {(situationType === 'travel' || situationType === 'arrival' || situationType === 'return_to_known_location') && uiPayload.destination ? (
                      <section className="resolution-section resolution-travel">
                        <span className="resolution-section-label">
                          {situationType === 'return_to_known_location' ? 'Return' : situationType === 'arrival' ? 'Arrival' : 'Travel'}
                        </span>
                        {uiPayload.destination ? (
                          <div className="resolution-row">
                            <span>Heading to</span>
                            <strong>{uiPayload.destination}</strong>
                          </div>
                        ) : null}
                        {uiPayload.travel_time ? (
                          <div className="resolution-row">
                            <span>Est. time</span>
                            <strong>{uiPayload.travel_time}</strong>
                          </div>
                        ) : null}
                        {uiPayload.weather ? (
                          <div className="resolution-row">
                            <span>Weather</span>
                            <strong>{uiPayload.weather}</strong>
                          </div>
                        ) : null}
                        {uiPayload.encounter_risk && uiPayload.encounter_risk !== 'low' ? (
                          <div className="resolution-row resolution-row--urgent">
                            <span>Road risk</span>
                            <strong>{uiPayload.encounter_risk}</strong>
                          </div>
                        ) : null}
                        {uiPayload.what_changed ? (
                          <div className="resolution-row">
                            <span>Changed</span>
                            <strong>{uiPayload.what_changed}</strong>
                          </div>
                        ) : null}
                      </section>
                    ) : null}

                    {/* Legacy: investigation leads from situation strip (fallback when no bundle) */}
                    {!uiPayload.visible_clues && situation.visibleClues && situation.visibleClues.length > 0 ? (
                      <section className="resolution-section">
                        <span className="resolution-section-label">Investigation leads</span>
                        <div className="resolution-lead-list">
                          {situation.visibleClues.slice(0, 4).map((lead, i) => (
                            <button
                              key={i}
                              type="button"
                              className="resolution-lead"
                              onClick={() => setActionDraft(`I examine ${lead}`)}
                            >
                              {lead}
                            </button>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {resolutionOptions.length > 0 ? (
                      <section className="resolution-section">
                        <span className="resolution-section-label">Approaches</span>
                        <div className="resolution-option-list">
                          {resolutionOptions.map((option, i) => (
                            <button
                              key={`${option}-${i}`}
                              type="button"
                              className="resolution-option"
                              onClick={() => setActionDraft(option)}
                            >
                              {option}
                            </button>
                          ))}
                        </div>
                      </section>
                    ) : null}

                    {!remoteRoll && diceRolls.length === 0 && !encounterActive && !observedSummary && resolutionOptions.length === 0 ? (
                      <section className="resolution-section resolution-empty">
                        <span className="resolution-section-label">No check required</span>
                        <p>Describe what {playerStats?.name || 'the character'} does next. TavernTails will call for resolution when the fiction needs it.</p>
                      </section>
                    ) : null}
                  </aside>
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
                Archive
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
                      sceneCues={[]}
                      npcSpotlight={[]}
                      onCueRoll={triggerCueRoll}
                      onGoToCharacters={onGoToCharacters}
                      onGoToImport={onGoToImport}
                      onSheetUpdate={handleSheetUpdate}
                      onQuickAction={handleQuickAction}
                    />
                  </div>
                </div>
              ) : null}

              {rightTab === 'journal' ? (
                <div className="world-archive-stack">
                  <JournalPanel sessionId={sessionId || null} memoryUpdates={memoryUpdates} />
                  <SessionDayLog sessionId={sessionId || null} />
                </div>
              ) : null}

              {rightTab === 'world' ? (
                <WorldPanel
                  campaignId={activeCampaignId}
                  situation={situation}
                  worldClock={worldClock}
                  memoryUpdates={memoryUpdates}
                />
              ) : null}
            </div>
          </aside>

          <aside className="world-character-panel" aria-label="World character panel">
            <div className="player-sheet" aria-label="Your character sheet">
              <div className="player-sheet-inner">
                <CharacterPanel
                  title="Your character"
                  roster={playerStats ? [playerStats] : []}
                  selectedId={playerStats ? String(playerStats.id) : null}
                  showRoster={false}
                  sceneCues={[]}
                  npcSpotlight={[]}
                  onCueRoll={triggerCueRoll}
                  onGoToCharacters={onGoToCharacters}
                  onGoToImport={onGoToImport}
                  onSheetUpdate={handleSheetUpdate}
                  onQuickAction={handleQuickAction}
                />
              </div>
            </div>
          </aside>
          </div>

          {sessionId && (
            <section className={`player-action-area action-console ${chatLogCollapsed ? 'action-console--chat-collapsed' : ''}`} aria-label="Action Console">
              {(situation.currentObjective || observedSummary || currentRisk) ? (
                <div
                  className="scene-summary-strip"
                  aria-label="Scene summary"
                  role="button"
                  tabIndex={0}
                  onClick={() => setSituationOpen(v => !v)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setSituationOpen(v => !v)
                    }
                  }}
                >
                  {situation.currentObjective ? (
                    <div className="scene-summary-item">
                      <span>Objective</span>
                      <strong>{situation.currentObjective}</strong>
                    </div>
                  ) : null}
                  {observedSummary ? (
                    <div className="scene-summary-item">
                      <span>Observed</span>
                      <strong>{observedSummary}</strong>
                    </div>
                  ) : null}
                  {currentRisk ? (
                    <div className="scene-summary-item scene-summary-item--risk">
                      <span>Risk</span>
                      <strong>{currentRisk}</strong>
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="action-console-header">
                <div>
                  <div className="player-action-prompt-text">
                    {playerStats?.name
                      ? `What does ${playerStats.name} do?`
                      : 'What do you do?'}
                  </div>
                  <div className="action-console-subtitle">Describe an action, roll dice, use a skill, cast a spell, or reference someone with @.</div>
                </div>
                {remoteRoll ? (
                  <div className="dice-result-card" aria-live="polite">
                    <span className="dice-result-label">{remoteRoll.expression || 'Roll'}</span>
                    <span className="dice-result-total">{remoteRoll.total ?? '—'}</span>
                    {remoteRoll.by ? <span className="dice-result-by">{remoteRoll.by}</span> : null}
                  </div>
                ) : null}
              </div>

              {diceRolls.length > 0 && (
                <div className="pending-roll-tray" aria-label="Pending dice rolls">
                  <span className="pending-roll-title">{diceRolls.length > 1 ? 'Pending Rolls' : 'Pending Roll'}</span>
                  <div className="pending-roll-cards">
                    {diceRolls.slice(0, 3).map((roll, i) => (
                      <button
                        key={i}
                        type="button"
                        className="pending-roll-card"
                        onClick={() => setActionDraft(`/roll 1d20 ${roll.skill || roll.type || ''}`.trim())}
                      >
                        <span>{roll.skill || roll.type || 'Roll'}</span>
                        {roll.reason ? <strong>{roll.reason}</strong> : null}
                      </button>
                    ))}
                  </div>
                  <button className="pending-roll-dismiss" type="button" onClick={() => setDiceRolls([])}>Dismiss</button>
                </div>
              )}

              <div className="action-console-tools">
                <div className="action-tool-menu">
                  <button
                    type="button"
                    className="action-tool-primary"
                    aria-haspopup="menu"
                    aria-expanded={rollToolsOpen}
                    onClick={() => setRollToolsOpen(v => !v)}
                  >
                    Roll Dice
                  </button>
                  {rollToolsOpen ? (
                    <div className="action-tool-popover" role="menu">
                      {[
                        ['Roll d20', '/roll 1d20'],
                        ['Roll d12', '/roll 1d12'],
                        ['Roll d10', '/roll 1d10'],
                        ['Roll d8', '/roll 1d8'],
                        ['Roll d6', '/roll 1d6'],
                        ['Roll d4', '/roll 1d4'],
                        ['Use skill', '@Perception'],
                        ['Cast spell', 'I cast '],
                        ['Use item', 'I use '],
                        ['Reference NPC', '@'],
                      ].map(([label, draft]) => (
                        <button
                          key={label}
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            setActionDraft(draft)
                            setRollToolsOpen(false)
                          }}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="player-chat-wrap">
                <Chat
                  sessionId={sessionId}
                  variant="dock"
                  character={playerStats ?? null}
                  composerInject={actionDraft}
                  onComposerInjectConsumed={() => setActionDraft(null)}
                  compactLog={chatLogCollapsed}
                  onExpandLog={() => setChatLogCollapsed(false)}
                  onMessageSent={() => setChatLogCollapsed(false)}
                />
              </div>
            </section>
          )}
          <nav className="mobile-session-nav" aria-label="Session sections">
            {([
              ['story', 'Story'],
              ['action', 'Action'],
              ['character', 'Character'],
              ['journal', 'Journal'],
              ['world', 'World'],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`mobile-session-nav-btn ${mobileTab === key ? 'active' : ''}`}
                onClick={() => {
                  setMobileTab(key)
                  if (key === 'world') {
                    setSessionMode('world')
                    setRightTab('journal')
                    return
                  }
                  if (sessionMode === 'world') setSessionMode('play')
                  if (key === 'character') setRightTab('character')
                  if (key === 'journal') setRightTab('journal')
                }}
              >
                {label}
              </button>
            ))}
          </nav>
        </section>
      </main>

      {/* Narrative score chip — dev mode only */}
      {process.env.NODE_ENV === 'development' && sceneQuality ? (
        <div
          className={`scene-score-chip ${sceneQuality.passed ? 'scene-score-chip--pass' : 'scene-score-chip--fail'}`}
          title={sceneQuality.detail?.failed_checks?.join('\n') || ''}
        >
          {sceneQuality.passed ? '✓' : '✗'} {sceneQuality.score}
        </div>
      ) : null}

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

      {/* Pipeline Debug Overlay */}
      {showDebugOverlay ? (
        <div className="debug-overlay" role="dialog" aria-label="Pipeline debug overlay">
          <div className="debug-overlay-header">
            <strong>Pipeline Inspector</strong>
            <button className="debug-overlay-close" type="button" onClick={() => setShowDebugOverlay(false)}>✕</button>
          </div>
          <div className="debug-overlay-body">
            {[
              { label: 'Situation Type', value: debugPayload.situation_type || situationType || '—' },
              { label: 'Resolution State', value: resolutionState || '—' },
            ].map(row => (
              <div key={row.label} className="debug-row">
                <span className="debug-row-label">{row.label}</span>
                <span className="debug-row-value">{row.value}</span>
              </div>
            ))}
            {[
              { label: 'Situation Classification', data: debugPayload.situation_classification },
              { label: 'Content Bundle', data: debugPayload.content_bundle },
              { label: 'Situation Validation', data: debugPayload.situation_validation },
              { label: 'Simulation Delta', data: debugPayload.simulation_delta },
              { label: 'Narrative Validation', data: debugPayload.narrative_validation },
              { label: 'Memory Delta', data: debugPayload.memory_delta },
              { label: 'Canon Validation', data: debugPayload.canon_validation },
              { label: 'Canon Changes', data: debugPayload.canon_changes },
              { label: 'Campaign Contract', data: debugPayload.campaign_contract },
              { label: 'Director Output', data: debugPayload.director_output },
              { label: 'UI Payload', data: debugPayload.ui_payload },
            ].map(section => section.data && Object.keys(section.data).length > 0 ? (
              <details key={section.label} className="debug-section">
                <summary className="debug-section-title">{section.label}</summary>
                <pre className="debug-section-body">{JSON.stringify(section.data, null, 2)}</pre>
              </details>
            ) : null)}
          </div>
        </div>
      ) : null}

      {/* Read Mode — Left Drawer (Character / Party) */}
      {sessionMode === 'read' && (
        <>
          <button
            className={`read-drawer-toggle read-drawer-toggle--left ${readLeftOpen ? 'active' : ''}`}
            type="button"
            onClick={() => setReadLeftOpen(v => !v)}
            aria-label="Character drawer"
          >
            {readLeftOpen ? '◀ Character' : '▶'}
          </button>
          {readLeftOpen ? (
            <aside className="read-drawer read-drawer--left" aria-label="Character">
              <div className="read-drawer-header">
                <strong>Character</strong>
                <button type="button" onClick={() => setReadLeftOpen(false)}>✕</button>
              </div>
              <div className="read-drawer-body">
                <CharacterPanel
                  title="Your character"
                  roster={playerStats ? [playerStats] : []}
                  selectedId={playerStats ? String(playerStats.id) : null}
                  showRoster={false}
                  sceneCues={[]}
                  npcSpotlight={[]}
                  onCueRoll={triggerCueRoll}
                  onGoToCharacters={onGoToCharacters}
                  onGoToImport={onGoToImport}
                  onSheetUpdate={handleSheetUpdate}
                  onQuickAction={handleQuickAction}
                />
              </div>
            </aside>
          ) : null}

          <button
            className={`read-drawer-toggle read-drawer-toggle--right ${readRightOpen ? 'active' : ''}`}
            type="button"
            onClick={() => setReadRightOpen(v => !v)}
            aria-label="Journal drawer"
          >
            {readRightOpen ? 'Journal ▶' : '◀'}
          </button>
          {readRightOpen ? (
            <aside className="read-drawer read-drawer--right" aria-label="Journal">
              <div className="read-drawer-header">
                <strong>Journal</strong>
                <button type="button" onClick={() => setReadRightOpen(false)}>✕</button>
              </div>
              <div className="read-drawer-body">
                <JournalPanel sessionId={sessionId || null} memoryUpdates={memoryUpdates} />
                <SessionDayLog sessionId={sessionId || null} />
              </div>
            </aside>
          ) : null}
        </>
      )}
    </div>
  )
}
