import React, {useEffect, useState} from 'react'
import { buildApiUrl } from '../api'

type Props = { sessionId: string, onClose: ()=>void }

export default function SessionSettings({sessionId,onClose}: Props){
  const [files, setFiles] = useState<string[]>([])
  const [selected, setSelected] = useState<string| null>(null)
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [meta, setMeta] = useState<any>(null)
  const [inviteEmail, setInviteEmail] = useState('')

  useEffect(()=>{
    const token = localStorage.getItem('access_token')
    const headers: any = { 'Content-Type': 'application/json' }
    if(token) headers['Authorization'] = `Bearer ${token}`
    fetch(buildApiUrl(`/sessions/${sessionId}/files`), { headers }).then(r=>r.ok? r.json():Promise.reject('err')).then((d:any)=>{
      setFiles(d.files||[])
    }).catch(()=>setFiles([]))
    fetch(buildApiUrl(`/sessions/${sessionId}/meta`), { headers }).then(r=>r.ok? r.json():Promise.reject('err')).then((m:any)=>{
      setMeta(m)
    }).catch(()=>setMeta(null))
  },[sessionId])

  function openFile(fname:string){
    setSelected(fname)
    setLoading(true)
    const token = localStorage.getItem('access_token')
    const headers: any = { 'Content-Type': 'application/json' }
    if(token) headers['Authorization'] = `Bearer ${token}`
    fetch(buildApiUrl(`/sessions/${sessionId}/file/${fname}`), { headers }).then(r=>r.ok? r.json():Promise.reject('err')).then((d:any)=>{
      if(d && typeof d === 'object' && d.content) setContent(d.content)
      else setContent(JSON.stringify(d,null,2))
      setLoading(false)
    }).catch(()=>{ setContent(''); setLoading(false) })
  }

  async function save(){
    if(!selected) return
    setMessage('Saving...')
    try{
      const token = localStorage.getItem('access_token')
      const headers: any = { 'Content-Type': 'application/json' }
      if(token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch(buildApiUrl(`/sessions/${sessionId}/file/${selected}`),{
        method:'POST',headers,body: JSON.stringify({content})
      })
      if(res.ok) setMessage('Saved')
      else setMessage('Save failed')
    }catch(e){ setMessage('Network error') }
    setTimeout(()=>setMessage(''),1500)
  }

  return (
    <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.5)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1200}}>
      <div style={{width:'840px',maxWidth:'96%',height:'80%',background:'#0b0b0b',borderRadius:8,padding:12,display:'flex',gap:12}}>
        <div style={{width:260,overflow:'auto'}}>
          <div style={{fontWeight:700,marginBottom:8}}>Session Files</div>
          <div style={{display:'flex',flexDirection:'column',gap:8}}>
            <button className="btn" onClick={()=>openFile('notes.md')}>Notes</button>
            <button className="btn" onClick={()=>openFile('npcs.json')}>NPCs</button>
            <button className="btn" onClick={()=>openFile('pcs.json')}>Player Characters</button>
            <button className="btn" onClick={()=>openFile('story.json')}>Story Log</button>
          </div>
          <div style={{marginTop:12}}>
            <div style={{fontWeight:700,marginTop:12}}>Other Files</div>
            <ul style={{listStyle:'none',padding:0,margin:0}}>
              {files.filter(f=>!['notes.md','npcs.json','pcs.json','story.json'].includes(f)).map(f=> (
                <li key={f} style={{marginBottom:8}}>
                  <div style={{display:'flex',gap:8}}>
                    <button className="btn" onClick={()=>openFile(f)} style={{flex:1}}>{f}</button>
                    <button className="btn" onClick={async ()=>{ if(window.confirm('Delete file?')){ try{ const token = localStorage.getItem('access_token'); const headers: any = {}; if(token) headers['Authorization'] = `Bearer ${token}`; const res = await fetch(buildApiUrl(`/sessions/${sessionId}/file/${f}`),{method:'DELETE', headers}); if(res.ok){ setFiles(prev=>prev.filter(x=>x!==f)); if(selected===f) { setSelected(null); setContent('') } } else { alert('Delete failed') } }catch(e){ alert('Network error') } } }}>del</button>
                  </div>
                </li>
              ))}
            </ul>
            <div style={{marginTop:12}}>
              <button className="btn" onClick={()=>{
                const name = window.prompt('Filename (e.g. notes.md)')
                if(!name) return
                setFiles(f=>[...f, name])
                openFile(name)
              }}>New File</button>
            </div>
          </div>
        </div>

        <div style={{flex:1,display:'flex',flexDirection:'column'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
            <div style={{fontWeight:700}}>{sessionId} — Settings</div>
            <div>
              <button className="btn" onClick={onClose}>Close</button>
            </div>
          </div>

          <div style={{marginTop:8,flex:1,display:'flex',flexDirection:'column'}}>
            <div style={{marginBottom:8}}>
              <div><strong>Owner:</strong> {meta?.owner || 'unknown'}</div>
              <div style={{marginTop:6}}><strong>Invited:</strong> {Array.isArray(meta?.invites) ? meta.invites.join(', ') : 'none'}</div>
                <div style={{marginTop:8,display:'flex',gap:8}}>
                <input className="input" placeholder="Invite email" value={inviteEmail} onChange={e=>setInviteEmail(e.target.value)} />
                <button className="btn" onClick={async ()=>{
                  if(!inviteEmail) return alert('Enter email')
                  try{
                    const token = localStorage.getItem('access_token')
                    const headers: any = {'Content-Type':'application/json'}
                    if(token) headers['Authorization'] = `Bearer ${token}`
                    const res = await fetch(buildApiUrl(`/sessions/${sessionId}/invite`),{method:'POST',headers,body: JSON.stringify({email: inviteEmail})})
                    if(res.ok){
                      const d = await res.json(); setMeta((prev: any) => ({...(prev||{}), invites: d.invites}))
                      setInviteEmail('')
                    } else { alert('Invite failed') }
                  }catch(e){ alert('Network error') }
                }}>Invite</button>
              </div>
            </div>
            {!selected ? (
              <div style={{color:'#888'}}>Select a file to view and edit.</div>
            ) : (
              <>
                <div style={{marginBottom:6,display:'flex',gap:8}}>
                  <strong>{selected}</strong>
                  <button className="btn" onClick={save}>Save</button>
                  <span style={{color:'#999'}}>{message}</span>
                </div>
                {loading && <div style={{color:'#bbb',marginBottom:6}}>Loading…</div>}
                <textarea value={content} onChange={e=>setContent(e.target.value)} style={{flex:1,width:'100%',background:'#0b0b0b',color:'#fff',border:'1px solid #222',padding:8,borderRadius:6,resize:'none'}} />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
