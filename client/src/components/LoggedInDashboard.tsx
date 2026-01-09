import React, { useState, useEffect, useMemo } from 'react';
import '../LoggedIn.css';
import './LoggedInDashboard.css';
import Beyond20Agent from '../agents/Beyond20Agent';
import GameplayLayout from './GameplayLayout'
import SessionSettings from './SessionSettings'
import { buildApiUrl, apiFetch } from '../api'
import CampaignsMenu from './CampaignsMenu'

type Props = {
  profile: any;
  onLogout: () => void;
};

const LoggedInDashboard: React.FC<Props> = ({ profile, onLogout }) => {
  const [view, setView] = useState<string>('gameplay');
  const [campaigns, setCampaigns] = useState<Array<any>>([])
  const [activeCampaignId, setActiveCampaignId] = useState<string | null>(null)
  const [sessionMetaById, setSessionMetaById] = useState<Record<string, any>>({})
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [settingsSession, setSettingsSession] = useState<string| null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newCampaignName, setNewCampaignName] = useState('')
  const [newCampaignDescription, setNewCampaignDescription] = useState('')

  const [characters, setCharacters] = useState<Array<any>>([])
  const [activeCharacterId, setActiveCharacterId] = useState<number | null>(null)
  const [newCharacterName, setNewCharacterName] = useState('')
  const [newCharacterLevel, setNewCharacterLevel] = useState<number>(1)
  const [newCharacterClass, setNewCharacterClass] = useState('')

  const activeCampaign = campaigns.find(c => String(c.id) === String(activeCampaignId)) || null
  const activeCampaignSessions: Array<{id: string}> = useMemo(() => (activeCampaign?.sessions || []), [activeCampaign])

  async function fetchCampaigns(){
    try{
      const res = await apiFetch('/campaigns')
      if(res.ok){
        const data = await res.json()
        const rows = Array.isArray(data?.campaigns) ? data.campaigns : []
        setCampaigns(rows)
        if(!activeCampaignId && rows.length > 0){
          setActiveCampaignId(String(rows[0].id))
        }
      }
    }catch(e){/*ignore*/}
  }

  async function fetchCharacters(){
    try{
      const res = await apiFetch('/characters')
      if(res.ok){
        const data = await res.json()
        const rows = Array.isArray(data?.characters) ? data.characters : []
        setCharacters(rows)
      }
    }catch(e){/*ignore*/}
  }

  useEffect(()=>{
    fetchCampaigns()
    fetchCharacters()
  },[profile, fetchCampaigns, fetchCharacters])

  useEffect(()=>{
    if(!activeCampaignId) return
    const nextCampaign = campaigns.find(c => String(c.id) === String(activeCampaignId))
    if(!nextCampaign) return
    const sessionsList: Array<any> = nextCampaign.sessions || []
    if(sessionsList.length > 0){
      const firstId = String(sessionsList[0].id)
      setActiveSession(prev => prev || firstId)
    } else {
      setActiveSession(null)
    }
  },[activeCampaignId, campaigns])

  useEffect(()=>{
    async function ensureSessionMetas(){
      const sessionIds = activeCampaignSessions.map(s => String(s.id))
      const missing = sessionIds.filter(id => !sessionMetaById[id])
      if(missing.length === 0) return
      try{
        const results = await Promise.all(missing.map(async (id) => {
          const res = await apiFetch(`/sessions/${id}/meta`)
          if(!res.ok) return null
          const data = await res.json()
          return { id, meta: data }
        }))
        const next: Record<string, any> = { ...sessionMetaById }
        for(const item of results){
          if(item?.id){
            next[item.id] = item.meta
          }
        }
        setSessionMetaById(next)
      }catch(e){/*ignore*/}
    }
    ensureSessionMetas()
  },[activeCampaignId, activeCampaignSessions, sessionMetaById])

  useEffect(()=>{
    async function loadSessionCharacterSelection(){
      if(!activeSession) return
      try{
        const res = await apiFetch(`/sessions/${activeSession}/meta`)
        if(!res.ok) return
        const meta = await res.json()
        const email = (localStorage.getItem('user_email') || '').trim().toLowerCase()
        const username = (localStorage.getItem('user_username') || '').trim().toLowerCase()
        const identifier = email || username
        const members = Array.isArray(meta?.members) ? meta.members : []
        const me = members.find((m: any) => String(m?.email || '').trim().toLowerCase() === identifier)
        if(me && (me.character_id === null || typeof me.character_id === 'number')){
          setActiveCharacterId(me.character_id)
        }
      }catch(e){/*ignore*/}
    }
    loadSessionCharacterSelection()
  },[activeSession])

  async function setSessionCharacter(characterId: number | null){
    if(!activeSession) return
    try{
      await apiFetch(`/sessions/${activeSession}/character`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: characterId })
      })
    }catch(e){/*ignore*/}
  }

  return (
    <div className="dashboard-root">
      <aside className="dashboard-sidebar">
        <div className="dashboard-brand">Solo TTRPG</div>
        <div className="dashboard-user">{profile?.name}</div>
        <nav className="dashboard-nav">
          <button className={`nav-btn ${view==='gameplay'?'active':''}`} onClick={() => setView('gameplay')}>Gameplay</button>
          <button className={`nav-btn ${view==='home'?'active':''}`} onClick={() => setView('home')}>Home</button>
          <button className={`nav-btn ${view==='view-characters'?'active':''}`} onClick={() => setView('view-characters')}>View Characters</button>
          <button className={`nav-btn ${view==='create-character'?'active':''}`} onClick={() => setView('create-character')}>Create Character</button>
          <button className={`nav-btn ${view==='campaigns'?'active':''}`} onClick={() => setView('campaigns')}>Campaigns</button>
          <button className={`nav-btn ${view==='campaign-settings'?'active':''}`} onClick={() => setView('campaign-settings')}>Campaign Settings</button>
          <button className={`nav-btn ${view==='account'?'active':''}`} onClick={() => setView('account')}>Your Account</button>
          <button className={`nav-btn ${view==='beyond20'?'active':''}`} onClick={() => setView('beyond20')}>Beyond20</button>
        </nav>
        <div className="sidebar-footer">
          <button className="btn-logout" onClick={onLogout}>Sign out</button>
        </div>
      </aside>
      <main className="dashboard-main">
        {view === 'gameplay' && (
          <section className="gameplay-panel">
            <div className="gameplay-toolbar">
              <div>
                <div className="gameplay-toolbar-title">Narrative</div>
                <div className="session-label">
                  {activeCampaign ? `Campaign: ${activeCampaign.name}` : 'No campaign selected'}
                  {activeSession ? ` • Session: ${(sessionMetaById[activeSession]?.name || activeSession)}` : ' • No session selected'}
                </div>
              </div>
              <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap',justifyContent:'flex-end'}}>
                <select className="input" value={activeCampaignId || ''} onChange={e => { setActiveCampaignId(e.target.value || null); }}>
                  <option value="">Select campaign…</option>
                  {campaigns.map(c => (
                    <option key={c.id} value={String(c.id)}>{c.name}</option>
                  ))}
                </select>

                <select className="input" value={activeSession || ''} onChange={e => { const v = e.target.value || null; setActiveSession(v); }} disabled={!activeCampaignId || activeCampaignSessions.length === 0} aria-disabled={!activeCampaignId || activeCampaignSessions.length === 0}>
                  <option value="">Select session…</option>
                  {activeCampaignSessions.map(s => {
                    const sid = String(s.id)
                    const name = sessionMetaById[sid]?.name || sid
                    return <option key={sid} value={sid}>{name}</option>
                  })}
                </select>

                <select className="input" value={activeCharacterId === null ? '' : String(activeCharacterId)} onChange={async e => {
                  const value = e.target.value
                  const parsed = value ? Number(value) : null
                  setActiveCharacterId(parsed)
                  await setSessionCharacter(parsed)
                }} disabled={!activeSession} aria-disabled={!activeSession}>
                  <option value="">No character</option>
                  {characters.map(c => (
                    <option key={c.id} value={String(c.id)}>{c.name}{c.class_name ? ` (${c.class_name})` : ''}</option>
                  ))}
                </select>

                <button className="btn" onClick={() => setShowCreateModal(true)}>New Campaign</button>
              </div>
            </div>
            <div className="gameplay-content">
              <GameplayLayout sessionId={activeSession} />
            </div>
          </section>
        )}
        {view === 'home' && (
          <section className="dashboard-panel">
            <h2>Welcome, {profile?.name}</h2>
            <p>Pick an option from the left to get started.</p>
            <div style={{ marginTop: 12 }}>
              <button className="btn" onClick={() => setShowCreateModal(true)}>Create Campaign</button>
            </div>
          </section>
        )}

        {view === 'view-characters' && (
          <section>
            <h2>Your Characters</h2>
            {characters.length === 0 ? (
              <p style={{color:'#888'}}>No characters yet.</p>
            ) : (
              <ul>
                {characters.map(c => (
                  <li key={c.id} style={{marginBottom:8,display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
                    <button className="btn" onClick={async ()=>{
                      setActiveCharacterId(c.id)
                      await setSessionCharacter(c.id)
                      setView('gameplay')
                    }} disabled={!activeSession} aria-disabled={!activeSession} style={!activeSession?{opacity:0.5}:{}}>
                      Select for Session
                    </button>
                    <span>{c.name}{c.class_name ? ` (${c.class_name})` : ''} — L{c.level}</span>
                    <button className="btn" onClick={async ()=>{
                      if(!window.confirm('Delete this character?')) return
                      const res = await apiFetch(`/characters/${c.id}`, { method: 'DELETE' })
                      if(res.ok) await fetchCharacters()
                    }}>Delete</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {view === 'create-character' && (
          <section>
            <h2>Create Character</h2>
            <div style={{maxWidth:520,display:'grid',gap:10}}>
              <input className="input" placeholder="Name" value={newCharacterName} onChange={e=>setNewCharacterName(e.target.value)} />
              <input className="input" placeholder="Class (optional)" value={newCharacterClass} onChange={e=>setNewCharacterClass(e.target.value)} />
              <input className="input" type="number" min={1} max={20} value={newCharacterLevel} onChange={e=>setNewCharacterLevel(Number(e.target.value || 1))} />
              <div style={{display:'flex',gap:8}}>
                <button className="btn" onClick={async ()=>{
                  if(!newCharacterName.trim()) return alert('Enter a name')
                  const payload: any = { name: newCharacterName.trim(), level: Math.max(1, Math.min(20, Number(newCharacterLevel)||1)) }
                  if(newCharacterClass.trim()) payload.class_name = newCharacterClass.trim()
                  const res = await apiFetch('/characters', { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify(payload) })
                  if(res.ok){
                    setNewCharacterName('')
                    setNewCharacterClass('')
                    setNewCharacterLevel(1)
                    await fetchCharacters()
                    setView('view-characters')
                  } else {
                    const err = await res.json().catch(()=>({}))
                    alert(err?.detail || 'Failed to create character')
                  }
                }}>Create</button>
                <button className="btn" onClick={()=>{ setView('view-characters') }}>Cancel</button>
              </div>
            </div>
          </section>
        )}

        {view === 'campaigns' && (
          <section>
            <h2>Campaigns</h2>
            <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap',marginBottom:12}}>
              <button className="btn" onClick={() => setShowCreateModal(true)}>Create Campaign</button>
              {activeCampaignId && (
                <button className="btn" onClick={async ()=>{
                  const res = await apiFetch(`/campaigns/${activeCampaignId}/create_session`, { method: 'POST' })
                  if(res.ok){
                    const data = await res.json()
                    const sid = String(data?.session_id || '')
                    await fetchCampaigns()
                    if(sid) setActiveSession(sid)
                    setView('gameplay')
                  } else {
                    const err = await res.json().catch(()=>({}))
                    alert(err?.detail || 'Failed to create session')
                  }
                }}>Create Session</button>
              )}
            </div>

            {campaigns.length === 0 ? (
              <p style={{color:'#888'}}>No campaigns yet.</p>
            ) : (
              <ul>
                {campaigns.map(c => (
                  <li key={c.id} style={{marginBottom:10}}>
                    <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
                      <button className="btn" onClick={()=>{ setActiveCampaignId(String(c.id)); setView('gameplay'); }}>
                        Open
                      </button>
                      <strong>{c.name}</strong>
                      <span style={{color:'#888'}}>{(c.sessions || []).length} session(s)</span>
                    </div>
                    {(String(c.id) === String(activeCampaignId) && (c.sessions || []).length > 0) && (
                      <ul style={{marginTop:8}}>
                        {(c.sessions || []).map((s: any) => {
                          const sid = String(s.id)
                          const name = sessionMetaById[sid]?.name || sid
                          return (
                            <li key={sid} style={{marginBottom:6,display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
                              <button className="btn" onClick={()=>{ setActiveSession(sid); setView('gameplay'); }}>{name}</button>
                              <button className="btn" aria-label="Session options" onClick={()=>setSettingsSession(sid)}>...</button>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {settingsSession && (
          <SessionSettings sessionId={settingsSession} onClose={async ()=>{ setSettingsSession(null); await fetchCampaigns() }} />
        )}

        {view === 'start-adventure' && (
          <section>
            <h2>Start New Adventure</h2>
            <p>Generate or configure a new adventure to play. (Placeholder)</p>
          </section>
        )}

        {view === 'campaign-settings' && (
          <section>
            <h2>Campaign Settings</h2>
            <CampaignsMenu />
          </section>
        )}

        {view === 'account' && (
          <section>
            <h2>Your Account</h2>
            <pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(profile, null, 2)}</pre>
          </section>
        )}

        {view === 'beyond20' && (
          <section>
            <h2>Beyond20 Domains</h2>
            <Beyond20Agent />
          </section>
        )}
        {showCreateModal && (
          <div style={{position:'fixed',inset:0,display:'flex',alignItems:'center',justifyContent:'center',background:'rgba(0,0,0,0.5)'}}>
            <div style={{background:'#0b0b0b',padding:16,borderRadius:8,width:420}}>
              <h3 style={{marginTop:0}}>Create Campaign</h3>
              <input className="input" placeholder="Campaign name" value={newCampaignName} onChange={e=>setNewCampaignName(e.target.value)} />
              <textarea className="input" placeholder="Description (optional)" value={newCampaignDescription} onChange={e=>setNewCampaignDescription(e.target.value)} />
              <div style={{display:'flex',gap:8,marginTop:12}}>
                <button className="btn" onClick={async ()=>{
                  if(!newCampaignName.trim()) return alert('Enter a name')
                  try{
                    const token = localStorage.getItem('access_token')
                    const headers: any = { 'Content-Type':'application/json' }
                    if(token) headers['Authorization'] = `Bearer ${token}`
                    const body = {name: newCampaignName.trim(), description: newCampaignDescription.trim(), create_session: true}
                    const res = await fetch(buildApiUrl('/campaigns'), {method:'POST',headers,body: JSON.stringify(body)})
                    if(res.ok){
                      const data = await res.json()
                      const campaign = data?.campaign
                      if(campaign?.id){
                        setActiveCampaignId(String(campaign.id))
                        const firstSession = Array.isArray(campaign.sessions) && campaign.sessions.length > 0 ? String(campaign.sessions[0].id) : null
                        setActiveSession(firstSession)
                      }
                      setView('gameplay')
                      setShowCreateModal(false)
                      setNewCampaignName('')
                      setNewCampaignDescription('')
                      await fetchCampaigns()
                    } else {
                      const e = await res.json(); alert(e.detail || 'Failed to create session')
                    }
                  }catch(e){ alert('Network error creating session') }
                }}>Create</button>
                <button className="btn" onClick={()=>{ setShowCreateModal(false); setNewCampaignName(''); setNewCampaignDescription('') }}>Cancel</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default LoggedInDashboard;