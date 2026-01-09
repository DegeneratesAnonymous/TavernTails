import React, { useEffect, useState } from 'react'
import { apiFetch } from '../api'

type Campaign = {
  id: string
  name: string
  description?: string
  sessions?: Array<{ id: string; meta?: string; files?: string }>
}

export default function CampaignsMenu() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function fetchCampaigns() {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch('/campaigns')
      if (res.ok) {
        const j = await res.json()
        setCampaigns(j.campaigns || [])
      } else {
        const detail = await res.json().catch(() => ({}))
        setError(detail?.detail || 'Failed to load campaigns')
      }
    } catch (e) {
      setError((e as Error).message || 'Network error loading campaigns')
    }
    setLoading(false)
  }

  useEffect(() => { fetchCampaigns() }, [])

  async function create() {
    if (!name.trim()) {
      setError('Campaign name is required')
      return
    }
    setError(null)
    try {
      const res = await apiFetch('/campaigns', { method: 'POST', body: JSON.stringify({ name, description: desc }) })
      if (res.ok) {
        setName('')
        setDesc('')
        fetchCampaigns()
      } else {
        const err = await res.json().catch(()=>({}));
        setError(err?.detail || 'Failed to create campaign')
      }
    } catch (e) {
      setError((e as Error).message || 'Network error creating campaign')
    }
  }

  return (
    <div style={{ padding: 12 }}>
      <h3>Campaigns</h3>
      {loading && <p style={{fontSize:12,color:'#aaa'}}>Loading campaigns…</p>}
      {error && <p style={{color:'#ff8080'}}>{error}</p>}
      <div>
        <input placeholder="Name" value={name} onChange={e => setName(e.target.value)} />
        <input placeholder="Description" value={desc} onChange={e => setDesc(e.target.value)} />
        <button onClick={create}>Create</button>
        <button style={{marginLeft:8}} onClick={fetchCampaigns}>Refresh</button>
      </div>
      {campaigns.length === 0 && !loading ? (
        <p style={{color:'#aaa',marginTop:12}}>No campaigns yet.</p>
      ) : (
        <ul>
        {campaigns.map(c => (
          <li key={c.id} style={{marginBottom:8}}>
            <div style={{display:'flex',alignItems:'center',gap:8}}>
              <div style={{flex:1}}>
                <strong>{c.name}</strong> — {c.description}
                {Array.isArray(c.sessions) && c.sessions.length>0 && (
                  <div style={{fontSize:12,color:'#aaa',marginTop:6}}>
                    Sessions: {c.sessions.map((s:any)=>s.id).join(', ')}
                  </div>
                )}
              </div>
              <div>
                <button className="btn" onClick={async ()=>{
                  try{
                    const res = await apiFetch(`/campaigns/${c.id}/create_session`, { method: 'POST' })
                    if(res.ok){ const j = await res.json(); window.alert(`Session created: ${j.session_id}`); fetchCampaigns() }
                    else { const e = await res.json().catch(()=>({})); alert(e.detail || 'Failed') }
                  }catch(e){ alert('Network error') }
                }}>Create Session</button>
              </div>
            </div>
          </li>
        ))}
      </ul>
      )}
    </div>
  )
}
