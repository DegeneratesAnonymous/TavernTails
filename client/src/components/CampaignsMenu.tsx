import React, { useEffect, useState } from 'react'
import { buildApiUrl, apiFetch } from '../api'

type Campaign = {
  id: string
  name: string
  description?: string
}

export default function CampaignsMenu() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')

  async function fetchCampaigns() {
    try {
      const res = await apiFetch('/campaigns')
      if (res.ok) {
        const j = await res.json()
        setCampaigns(j.campaigns || [])
      } else {
        console.error('Failed to load campaigns')
      }
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => { fetchCampaigns() }, [])

  async function create() {
    try {
      const res = await apiFetch('/campaigns', { method: 'POST', body: JSON.stringify({ name, description: desc }) })
      if (res.ok) {
        setName('')
        setDesc('')
        fetchCampaigns()
      } else {
        const err = await res.json().catch(()=>({}));
        console.error('Failed to create', err)
      }
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div style={{ padding: 12 }}>
      <h3>Campaigns</h3>
      <div>
        <input placeholder="Name" value={name} onChange={e => setName(e.target.value)} />
        <input placeholder="Description" value={desc} onChange={e => setDesc(e.target.value)} />
        <button onClick={create}>Create</button>
      </div>
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
    </div>
  )
}
