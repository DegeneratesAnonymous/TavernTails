import React, {useRef, useState, useEffect, useCallback} from 'react'
import './Chat.css'
import { apiFetch, buildWsUrl } from '../api'
import ChatToolbar from './chat/ChatToolbar'
import InvitePanel from './chat/InvitePanel'
import AdvancedToolsPanel from './chat/AdvancedToolsPanel'
import MessageList from './chat/MessageList'
import Composer from './chat/Composer'
import NpcSnapshotModal from './chat/NpcSnapshotModal'

type Msg = {
  id: number|string
  who:'gm'|'you'|'system'|'ally'
  text:string
  createdAt?: string
  mentions?: string[]
}

type AdvancedTool = {
  id: string
  label: string
  description: string
  command?: string
  emit?: string
  systemText?: string
}

type Props = {
  sessionId?: string | null
  variant?: 'full' | 'dock'
  aboveComposer?: React.ReactNode
}

const rollRegex = /^\s*(\d*)d(\d+)([+-]\d+)?\s*$/i
const slashRollRegex = /^\s*\/(r|roll)\b\s*(.*)$/i

function normalizeRollExpression(expr: string){
  const trimmed = (expr || '').trim()
  if(!trimmed) return ''
  if(/^d\d+$/i.test(trimmed)) return `1${trimmed}`
  return trimmed
}

const ADVANCED_TOOLS: AdvancedTool[] = [
  {
    id:'recap',
    label:'Request Recap',
    description:'Ping the Notes agent for a quick session summary.',
    command:'!notes quick recap',
    systemText:'Notes agent ping queued — expect a recap shortly.'
  },
  {
    id:'scene',
    label:'Scene Diagnostics',
    description:'Ask the Scene Analysis agent to flag rolls or rule triggers.',
    systemText:'Scene diagnostics requested. Watch for roll prompts.',
    emit:'scene:diagnostics'
  },
  {
    id:'image',
    label:'Inspire Image',
    description:'Forward the latest narration to the Image agent for art ideas.',
    systemText:'Image agent request queued with current scene context.',
    emit:'image:generate'
  },
  {
    id:'npc-snapshot',
    label:'NPC Snapshot',
    description:'Send a quick stat ping to the NPC agent for initiative cues.',
    systemText:'NPC agent request queued for the highlighted foe.',
    emit:'npc:profile'
  }
]

const ADVANCED_TOOLS_FOR_PANEL = ADVANCED_TOOLS.map((t) => ({ id: t.id, label: t.label, description: t.description }))

export default function Chat({sessionId, variant = 'full', aboveComposer}: Props){
  const [messages, setMessages] = useState<Msg[]>([])
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string|null>(null)
  const [toolbarMessage, setToolbarMessage] = useState<string|null>(null)
  const [showInviteForm, setShowInviteForm] = useState(false)
  const [showToolsPanel, setShowToolsPanel] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteNote, setInviteNote] = useState('')
  const [inviteBusy, setInviteBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [npcModalOpen, setNpcModalOpen] = useState(false)
  const listRef = useRef<HTMLDivElement|null>(null)
  const notifyMentions = useCallback((list?: string[])=>{
    if(!list || !list.length) return
    const target = list[0]
    if(!target) return
    const pretty = target.charAt(0).toUpperCase() + target.slice(1)
    window.dispatchEvent(new CustomEvent('session:waiting',{detail:{player: pretty, reason:'mention', expiresMs: 8000}}))
  },[])
  const appendMessage = useCallback((msg: Msg)=>{
    setMessages(prev => {
      if(prev.some(existing => existing.id === msg.id)) return prev
      return [...prev, msg]
    })
  },[])

  useEffect(()=>{ // auto-scroll to bottom when messages change
    if(!listRef.current) return
    const el = listRef.current
    const raf = window.requestAnimationFrame(()=>{
      el.scrollTop = el.scrollHeight
    })
    return ()=>window.cancelAnimationFrame(raf)
  },[messages])

  useEffect(()=>{
    function onAdvance(e: CustomEvent){
      const detail = e.detail
      if(!detail) return
      const text = detail.narration || detail.text || JSON.stringify(detail)
      appendMessage({id:`gm-${Date.now()}`,who:'gm',text})
    }
    // @ts-ignore
    window.addEventListener('narrative:advance', onAdvance as EventListener)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('narrative:advance', onAdvance as EventListener)
    }
  },[appendMessage])

  useEffect(()=>{
    if(!sessionId){
      setMessages([])
      return
    }
    let canceled = false
    async function load(){
      setLoading(true)
      setError(null)
      try{
        const res = await apiFetch(`/chat?session_id=${sessionId}`)
        if(!res.ok) throw new Error('Failed to load chat log')
        const data = await res.json()
        if(!canceled){
          const mapped: Msg[] = (Array.isArray(data)?data:data?.messages||[]).map((m:any)=>({
            id: m.id ?? `${m.session_id}-${m.created_at}` ?? Math.random(),
            who: m.role === 'gm' ? 'gm' : 'ally',
            text: m.message,
            createdAt: m.created_at,
            mentions: m.mentions || []
          }))
          setMessages(mapped)
        }
      }catch(err:any){
        if(!canceled){
          const msg = err?.message || 'Chat failed to load'
          if(variant === 'dock'){
            appendMessage({id:`chat-load-${Date.now()}`,who:'system',text:msg})
            setError(null)
          }else{
            setError(msg)
          }
        }
      }finally{
        if(!canceled) setLoading(false)
      }
    }
    load()
    return ()=>{ canceled = true }
  },[sessionId, appendMessage, variant])

  useEffect(()=>{
    if(!toolbarMessage) return
    const timer = setTimeout(()=>setToolbarMessage(null), 4000)
    return ()=>clearTimeout(timer)
  },[toolbarMessage])

  async function sendToBackend(text: string){
    if(!sessionId){
      appendMessage({id:`warn-${Date.now()}`,who:'system',text:'Create or load a session to send messages.'})
      return
    }
    try{
      const res = await apiFetch('/chat', {
        method:'POST',
        body: JSON.stringify({ message: text, session_id: sessionId })
      })
      if(!res.ok){
        const detail = await res.json().catch(()=>null)
        throw new Error(detail?.detail || 'Failed to send message')
      }
      const saved = await res.json()
      appendMessage({ id: saved.id, who:'you', text:saved.message, createdAt:saved.created_at, mentions: saved.mentions || [] })
      notifyMentions(saved.mentions)
    }catch(err:any){
      const msg = err?.message || 'Unable to send message'
      if(variant === 'dock'){
        appendMessage({id:`chat-send-${Date.now()}`,who:'system',text:msg})
        setError(null)
      }else{
        setError(msg)
      }
    }
  }

  async function sendRoll(expr: string){
    try{
      const normalized = normalizeRollExpression(expr)
      if(!normalized){
        appendMessage({id:`roll-${Date.now()}`,who:'system',text:'Usage: /r 1d20+3'})
        return
      }
      const res = await apiFetch('/rolls', {
        method:'POST',
        body: JSON.stringify({ expression: normalized, reason: `chat:${sessionId || 'local'}`, session_id: sessionId })
      })
      if(!res.ok){
        const detail = await res.json().catch(()=>null)
        throw new Error(detail?.detail || 'Roll failed')
      }
      const data = await res.json()
      const result = data?.result
      const summary = result ? `${result.expression} → ${result.rolls?.join(' + ')} ${result.mod ? (result.mod>0?`+ ${result.mod}`:`- ${Math.abs(result.mod)}`) : ''} = ${result.total}` : `Roll complete (${expr})`
      appendMessage({id:`roll-${Date.now()}`,who:'system',text:summary})
    }catch(err:any){
      appendMessage({id:`roll-${Date.now()}`,who:'system',text:`Roll error: ${err?.message || 'unknown error'}`})
    }
  }

  async function requestNotesRecap(){
    if(!sessionId){
      appendMessage({id:`notes-${Date.now()}`,who:'system',text:'Notes recap requires an active session.'})
      return
    }
    try{
      const recent = messages.slice(-5).map(m=>`[${m.who}] ${m.text}`)
      const res = await apiFetch('/notes/log', {
        method:'POST',
        body: JSON.stringify({ session_id: sessionId, notes: recent })
      })
      if(!res.ok) throw new Error('Notes agent unavailable')
      const data = await res.json()
      appendMessage({id:`notes-${Date.now()}`,who:'system',text:`Notes recap: ${data.recap}`})
    }catch(err:any){
      appendMessage({id:`notes-${Date.now()}`,who:'system',text:`Notes agent error: ${err?.message || 'unknown issue'}`})
    }
  }



  async function handleInviteSubmit(){
    if(!sessionId){
      setToolbarMessage('Select or create a session before inviting friends.')
      return
    }
    if(!inviteEmail.trim()){
      setToolbarMessage('Enter an email or username to invite.')
      return
    }
    try{
      setInviteBusy(true)
      const res = await apiFetch(`/sessions/${sessionId}/invite`,{
        method:'POST',
        body: JSON.stringify({ email: inviteEmail.trim(), note: inviteNote.trim() || undefined })
      })
      if(!res.ok){
        const detail = await res.json().catch(()=>null)
        throw new Error(detail?.detail || 'Invite failed')
      }
      setInviteEmail('')
      setInviteNote('')
      setToolbarMessage('Invite sent — they will see it in their dashboard.')
    }catch(err:any){
      setToolbarMessage(err?.message || 'Unable to send invite right now.')
    }finally{
      setInviteBusy(false)
    }
  }

  async function handleExportLog(){
    if(!messages.length){
      setToolbarMessage('No chat entries to export yet.')
      return
    }
    try{
      setExporting(true)
      const bundle = {
        exportedAt: new Date().toISOString(),
        sessionId: sessionId || null,
        entries: messages
      }
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {type:'application/json'})
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `taverntails-chat-${sessionId || 'local'}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      setToolbarMessage('Chat log exported.')
    }catch(err:any){
      setToolbarMessage(err?.message || 'Could not export chat log.')
    }finally{
      setExporting(false)
    }
  }

  async function runAdvancedTool(tool: AdvancedTool){
    if(tool.id === 'npc-snapshot'){
      setNpcModalOpen(true)
      return
    }
    if(tool.command){
      await handleSend(tool.command)
    }
    if(tool.systemText){
      appendMessage({id:`tool-${tool.id}-${Date.now()}`,who:'system',text:tool.systemText})
    }
    if(tool.emit){
      const detail: any = { sessionId, tool: tool.id, requestedAt: new Date().toISOString() }
      if(tool.id === 'scene'){
        const recentGm = [...messages].reverse().find(m => m.who === 'gm')
        const actionSamples = messages.filter(m => m.who !== 'gm' && m.who !== 'system').slice(-4).map(m => m.text)
        detail.scene = recentGm?.text || 'Current encounter'
        detail.actions = actionSamples
      }
      window.dispatchEvent(new CustomEvent(tool.emit,{detail}))
    }
    setToolbarMessage(`${tool.label} queued.`)
  }

  async function handleSend(override?: string){
    const pending = typeof override === 'string' ? override : value
    if(!pending.trim()) return
    const text = pending.trim()
    if(typeof override !== 'string'){
      setValue('')
    }
    if(text.toLowerCase().startsWith('!notes')){
      await requestNotesRecap()
      if(typeof override !== 'string') setValue('')
      return
    }
    const slashMatch = text.match(slashRollRegex)
    if(slashMatch){
      const expr = normalizeRollExpression(slashMatch[2] || '')
      await sendRoll(expr)
      return
    }
    if(rollRegex.test(text)){
      await sendRoll(normalizeRollExpression(text))
      return
    }
    await sendToBackend(text)
  }

  useEffect(()=>{
    if(!sessionId) return
    const token = encodeURIComponent(window.localStorage.getItem('access_token') || '')
    const ws = new WebSocket(buildWsUrl(`/ws/sessions/${sessionId}?token=${token}`))
    ws.onmessage = (event)=>{
      try{
        const data = JSON.parse(event.data)
        if(data?.type === 'chat.message' && data?.message){
          const payload = data.message
          const role = (payload.role || '').toLowerCase()
          const who: Msg['who'] = role === 'gm' ? 'gm' : role === 'system' ? 'system' : 'ally'
          appendMessage({
            id: payload.id,
            who,
            text: payload.message,
            createdAt: payload.created_at,
            mentions: payload.mentions || []
          })
          notifyMentions(payload.mentions)
        }
        if(data?.type === 'rolls.result' && data?.result){
          const res = data.result
          const prefix = data?.source === 'beyond20' ? '[Beyond20] ' : ''
          const breakdown = Array.isArray(res.rolls) && res.rolls.length ? res.rolls.join(' + ') : ''
          const modText = res.mod ? (res.mod>0?` + ${res.mod}`:` - ${Math.abs(res.mod)}`) : ''
          const detail = `${breakdown}${modText}`.trim()
          const arrow = detail ? ` → ${detail}` : ''
          const desc = `${prefix}${res.expression || 'Roll'}${arrow} = ${res.total}`
          appendMessage({id:`ws-roll-${Date.now()}`, who:'system', text: desc})
        }
      }catch(err){
        console.warn('Chat WS parse error', err)
      }
    }
    ws.onerror = ()=>ws.close()
    return ()=>{
      ws.close()
    }
  },[sessionId, appendMessage, notifyMentions])

  return (
    <div className={`chat-root ${variant === 'dock' ? 'chat-root--dock' : ''}`}>
      <NpcSnapshotModal
        open={npcModalOpen}
        onCancel={() => {
          setNpcModalOpen(false)
          setToolbarMessage('NPC snapshot canceled.')
        }}
        onSubmit={(payload) => {
          setNpcModalOpen(false)
          const stats: Record<string, number> = {}
          if (typeof payload.initiativeMod === 'number') stats.initiative = payload.initiativeMod
          // Snapshot modal provides name-only class/spell entries (quick entry path).
          // Full class/spell details (level, subclass, descriptions, tags) are set
          // via the NPC manage endpoint directly when using the full NPC editor.
          const classes = payload.classes.map((name) => ({ name }))
          const spells = payload.spells.map((name) => ({ name }))
          window.dispatchEvent(new CustomEvent('npc:profile', {
            detail: { sessionId, npc: { name: payload.name, stats, classes, spells } },
          }))
          setToolbarMessage('NPC Snapshot queued.')
        }}
      />

      <div>
        <ChatToolbar
          sessionId={sessionId}
          inviteBusy={inviteBusy}
          exporting={exporting}
          hasMessages={messages.length > 0}
          showInviteForm={showInviteForm}
          showToolsPanel={showToolsPanel}
          onToggleInvite={() => setShowInviteForm(v => !v)}
          onExport={handleExportLog}
          onToggleTools={() => setShowToolsPanel(v => !v)}
          toolbarMessage={toolbarMessage}
        />

        {showInviteForm ? (
          <InvitePanel
            inviteEmail={inviteEmail}
            inviteNote={inviteNote}
            inviteBusy={inviteBusy}
            onChangeEmail={setInviteEmail}
            onChangeNote={setInviteNote}
            onSubmit={handleInviteSubmit}
          />
        ) : null}

        {showToolsPanel ? (
          <AdvancedToolsPanel
            tools={ADVANCED_TOOLS_FOR_PANEL}
            disabled={!sessionId}
            onRun={(toolId) => {
              const tool = ADVANCED_TOOLS.find(t => t.id === toolId)
              if (!tool) return
              runAdvancedTool(tool)
            }}
          />
        ) : null}
      </div>

      <MessageList ref={listRef} loading={loading} messages={messages} />

      {error ? <div className="inline-alert inline-alert-error" style={{ marginTop: 10 }}>{error}</div> : null}

      {aboveComposer ? (
        <div className="chat-above-composer" aria-label="Suggested actions">
          {aboveComposer}
        </div>
      ) : null}

      <Composer sessionId={sessionId} value={value} onChange={setValue} onSend={() => handleSend()} />
    </div>
  )
}
