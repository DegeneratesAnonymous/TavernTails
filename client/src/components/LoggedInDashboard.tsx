import React, { useState, useEffect } from 'react';
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
  const [sessions, setSessions] = useState<Array<any>>([])
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [settingsSession, setSettingsSession] = useState<string| null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newSessionName, setNewSessionName] = useState('')

  async function fetchSessions(){
    try{
      const res = await apiFetch('/sessions')
      if(res.ok){
        const data = await res.json()
        if(Array.isArray(data)) setSessions(data)
      }
    }catch(e){/*ignore*/}
  }

  useEffect(()=>{ fetchSessions() },[profile])

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
          <button className={`nav-btn ${view==='load-adventure'?'active':''}`} onClick={() => setView('load-adventure')} disabled={sessions.length===0} aria-disabled={sessions.length===0} style={sessions.length===0?{opacity:0.5}:{}}>Load Adventure</button>
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
                <div className="session-label">{activeSession ? `Session: ${activeSession}` : 'No session selected yet'}</div>
              </div>
              <button className="btn" onClick={() => setShowCreateModal(true)}>Start New Adventure</button>
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
              <button className="btn" onClick={() => setShowCreateModal(true)}>Start New Adventure</button>
            </div>
          </section>
        )}

        {view === 'view-characters' && (
          <section>
            <h2>Your Characters</h2>
            <p>Here you will see your saved characters. (Placeholder)</p>
          </section>
        )}

        {view === 'create-character' && (
          <section>
            <h2>Create Character</h2>
            <p>Character creation UI goes here. (Placeholder)</p>
          </section>
        )}

        {view === 'load-adventure' && (
          <section>
            <h2>Load Adventure</h2>
            {sessions.length===0 ? (
              <p style={{color:'#888'}}>No saved adventures. Create one from Home.</p>
            ) : (
              <ul>
                {sessions.map(s=> (
                  <li key={s.id} style={{marginBottom:8,display:'flex',gap:8,alignItems:'center'}}>
                    <button className="btn" onClick={()=>{ setActiveSession(s.id); setView('gameplay'); }}>{s.name}</button>
                    <button className="btn" aria-label="Session options" onClick={()=>setSettingsSession(s.id)}>...</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {settingsSession && (
          <SessionSettings sessionId={settingsSession} onClose={async ()=>{ setSettingsSession(null); await fetchSessions() }} />
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
              <h3 style={{marginTop:0}}>Create Session</h3>
              <input className="input" placeholder="Session name" value={newSessionName} onChange={e=>setNewSessionName(e.target.value)} />
              <div style={{display:'flex',gap:8,marginTop:12}}>
                <button className="btn" onClick={async ()=>{
                  if(!newSessionName.trim()) return alert('Enter a name')
                  try{
                    const token = localStorage.getItem('access_token')
                    const headers: any = { 'Content-Type':'application/json' }
                    if(token) headers['Authorization'] = `Bearer ${token}`
                    const body = {name: newSessionName.trim()}
                    const res = await fetch(buildApiUrl('/sessions'), {method:'POST',headers,body: JSON.stringify(body)})
                    if(res.ok){
                      const data = await res.json()
                      setActiveSession(data.id)
                      setView('gameplay')
                      setShowCreateModal(false)
                      setNewSessionName('')
                      await fetchSessions()
                    } else {
                      const e = await res.json(); alert(e.detail || 'Failed to create session')
                    }
                  }catch(e){ alert('Network error creating session') }
                }}>Create</button>
                <button className="btn" onClick={()=>{ setShowCreateModal(false); setNewSessionName('') }}>Cancel</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default LoggedInDashboard;
