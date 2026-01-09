import React, {useRef, useState, useEffect, useCallback} from 'react'
import { apiFetch, buildWsUrl } from '../api'

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
}

const rollRegex = /^\s*(\d*)d(\d+)([+-]\d+)?\s*$/i

export default function Chat({sessionId}: Props){
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
    if(listRef.current){
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
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
        if(!canceled) setError(err?.message || 'Chat failed to load')
      }finally{
        if(!canceled) setLoading(false)
      }
    }
    load()
    return ()=>{ canceled = true }
  },[sessionId])

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
      setError(err?.message || 'Unable to send message')
    }
  }

  async function sendRoll(expr: string){
    try{
      const res = await apiFetch('/rolls', {
        method:'POST',
        body: JSON.stringify({ expression: expr, reason: `chat:${sessionId || 'local'}`, session_id: sessionId })
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

  const advancedTools: AdvancedTool[] = [
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
    if(tool.command){
      await handleSend(tool.command)
    }
    if(tool.systemText){
      const helperText = tool.systemText
      appendMessage({id:`tool-${tool.id}-${Date.now()}`,who:'system',text:helperText})
    }
    if(tool.emit){
      const detail: any = { sessionId, tool: tool.id, requestedAt: new Date().toISOString() }
      if(tool.id === 'scene'){
        const recentGm = [...messages].reverse().find(m => m.who === 'gm')
        const actionSamples = messages.filter(m => m.who !== 'gm' && m.who !== 'system').slice(-4).map(m => m.text)
        detail.scene = recentGm?.text || 'Current encounter'
        detail.actions = actionSamples
      }
      if(tool.id === 'npc-snapshot'){
        const nameInput = window.prompt('NPC name to spotlight?')
        if(!nameInput){
          setToolbarMessage('NPC snapshot canceled — no name provided.')
          return
        }
        const modInput = window.prompt('Initiative modifier (e.g. +2 or -1)?', '+0') || ''
        const parsedMod = parseInt(modInput.replace(/[^0-9-+]/g,''), 10)
        const stats: Record<string, number> = {}
        if(!Number.isNaN(parsedMod)){
          stats.initiative = parsedMod
        }
        detail.npc = { name: nameInput.trim(), stats }
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
    if(rollRegex.test(text)){
      await sendRoll(text)
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
    <div className="chat-root" style={{height:'100%',display:'flex',flexDirection:'column'}}>
      <div style={{padding:'0 0 8px 0'}}>
        <div style={{display:'flex',flexWrap:'wrap',gap:8,marginBottom:showInviteForm||showToolsPanel?8:4}}>
          <button type="button" disabled={!sessionId || inviteBusy} onClick={()=>setShowInviteForm(v=>!v)} style={{padding:'6px 12px'}}>
            {showInviteForm? 'Close Invite' : 'Invite Friend'}
          </button>
          <button type="button" disabled={!messages.length || exporting} onClick={handleExportLog} style={{padding:'6px 12px'}}>
            {exporting? 'Exporting…' : 'Export Log'}
          </button>
          <button type="button" disabled={!sessionId} onClick={()=>setShowToolsPanel(v=>!v)} style={{padding:'6px 12px'}}>
            {showToolsPanel? 'Hide Tools' : 'Advanced Tools'}
          </button>
        </div>
        {toolbarMessage && <div style={{fontSize:12,color:'#67d5ff',marginBottom:6}}>{toolbarMessage}</div>}
        {showInviteForm && (
          <div style={{border:'1px solid rgba(255,255,255,0.08)',borderRadius:6,padding:8,marginBottom:8,background:'#101010'}}>
            <div style={{fontSize:12,letterSpacing:0.3,color:'#ccc',marginBottom:4}}>Send a quick invite</div>
            <input value={inviteEmail} onChange={e=>setInviteEmail(e.target.value)} placeholder="friend@example.com" style={{width:'100%',padding:6,marginBottom:6,borderRadius:4,border:'1px solid rgba(255,255,255,0.08)',background:'#0b0b0b',color:'#fff'}} disabled={inviteBusy} />
            <textarea value={inviteNote} onChange={e=>setInviteNote(e.target.value)} placeholder="Optional note" rows={2} style={{width:'100%',padding:6,borderRadius:4,border:'1px solid rgba(255,255,255,0.08)',background:'#0b0b0b',color:'#fff'}} disabled={inviteBusy}></textarea>
            <div style={{textAlign:'right',marginTop:8}}>
              <button type="button" onClick={handleInviteSubmit} disabled={inviteBusy}>{inviteBusy ? 'Sending…' : 'Send Invite'}</button>
            </div>
          </div>
        )}
        {showToolsPanel && (
          <div style={{border:'1px solid rgba(255,255,255,0.08)',borderRadius:6,padding:8,marginBottom:8,background:'#101010'}}>
            <div style={{fontSize:12,letterSpacing:0.3,color:'#ccc',marginBottom:6}}>Session tools</div>
            <div style={{display:'flex',flexDirection:'column',gap:6}}>
              {advancedTools.map(tool=>(
                <div key={tool.id} style={{display:'flex',justifyContent:'space-between',gap:8,alignItems:'center'}}>
                  <div style={{flex:1}}>
                    <div style={{fontSize:13,fontWeight:600}}>{tool.label}</div>
                    <div style={{fontSize:11,color:'#aaa'}}>{tool.description}</div>
                  </div>
                  <button type="button" disabled={!sessionId} onClick={()=>runAdvancedTool(tool)}>Run</button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <div ref={listRef} style={{flex:1,overflowY:'auto',padding:8,background:'#0b0b0b',borderRadius:6}}>
        {loading && <div style={{fontSize:12,color:'#aaa',marginBottom:8}}>Loading chat…</div>}
        {messages.map(m=> (
          <div key={m.id} style={{marginBottom:8,opacity:m.who==='system'?0.8:1}}>
            <div style={{fontSize:12,color:'#999'}}>{m.who.toUpperCase()}</div>
            <div style={{padding:6,background:m.who==='you'? '#122':'#111',borderRadius:6}}>{m.text}</div>
            {!!m.mentions?.length && (
              <div style={{fontSize:11,color:'#8fe0ff',marginTop:4}}>Mentions: {m.mentions.join(', ')}</div>
            )}
          </div>
        ))}
      </div>
      {error && <p style={{color:'#ffaaaa',fontSize:12,marginTop:6}}>{error}</p>}
      <form style={{display:'flex',marginTop:8}} onSubmit={(e)=>{e.preventDefault(); handleSend()}}>
        <input value={value} onChange={e=>setValue(e.target.value)} style={{flex:1,padding:8,borderRadius:6,border:'1px solid rgba(255,255,255,0.06)'}} placeholder={sessionId ? "Type a message or roll (e.g. 1d20+3)" : "Select a session to chat"} disabled={!sessionId} />
        <button style={{marginLeft:8}} type="submit" disabled={!sessionId}>Send</button>
      </form>
    </div>
  )
}
