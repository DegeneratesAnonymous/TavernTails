import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import { apiFetch, buildApiUrl } from '../api'

type DocumentMeta = {
  id: string
  session_id: string
  name: string
  category: string
  visibility: string
  size: number
  created_at: string
  filename?: string
}

type DocumentDetail = DocumentMeta & { content: string }

type UploadEntry = {
  id: string
  name: string
  progress: number
  status: 'uploading' | 'done' | 'error' | 'canceled'
  error?: string
  file: File
  previewUrl?: string
  size: number
}

const formatBytes = (size: number) => {
  if(size < 1024) return `${size} B`
  if(size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

type Props = {
  sessionId?: string | null
}

export default function DocumentsPanel({sessionId}: Props){
  const [docs, setDocs] = useState<DocumentMeta[]>([])
  const [selected, setSelected] = useState<DocumentDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [formBusy, setFormBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('Session Note')
  const [content, setContent] = useState('')
  const [uploads, setUploads] = useState<UploadEntry[]>([])
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const uploadControllers = useRef<Record<string, () => void>>({})

  const hasSession = Boolean(sessionId)
  const hasActiveUploads = useMemo(() => uploads.some(u => u.status === 'uploading'), [uploads])

  const updateUpload = useCallback((id: string, patch: Partial<UploadEntry> | ((prev: UploadEntry) => UploadEntry)) => {
    setUploads(list => list.map(item => {
      if(item.id !== id) return item
      if(typeof patch === 'function'){
        return patch(item)
      }
      return {...item, ...patch}
    }))
  },[])

  const registerCancel = useCallback((id: string, cancelFn: () => void) => {
    uploadControllers.current[id] = cancelFn
  },[])

  const clearCancel = useCallback((id: string) => {
    delete uploadControllers.current[id]
  },[])

  const loadDocuments = useCallback(async () => {
    if(!sessionId){
      setDocs([])
      setSelected(null)
      return
    }
    setLoading(true)
    setError(null)
    try{
      const res = await apiFetch(`/documents/${sessionId}`)
      if(!res.ok) throw new Error('Unable to load documents')
      const data = await res.json()
      setDocs(Array.isArray(data) ? data : [])
    }catch(err:any){
      setError(err?.message || 'Documents unavailable')
      setDocs([])
    }finally{
      setLoading(false)
    }
  },[sessionId])

  const loadDetail = useCallback(async (docId: string) => {
    if(!sessionId) return
    try{
      const res = await apiFetch(`/documents/${sessionId}/${docId}`)
      if(!res.ok) throw new Error('Failed to fetch document')
      const data = await res.json()
      setSelected(data)
      // If the document filename looks like an image, prepare raw preview URL
      const imgExt = data.filename?.split('.').pop()?.toLowerCase()
      if(imgExt && ['png','jpg','jpeg','gif','webp'].includes(imgExt)){
        setPreviewUrl(buildApiUrl(`/documents/${sessionId}/${docId}/raw`))
      } else {
        setPreviewUrl(null)
      }
    }catch(err:any){
      setError(err?.message || 'Could not open document')
    }
  },[sessionId])

  useEffect(()=>{
    loadDocuments()
  },[loadDocuments])

  useEffect(()=>{
    if(!sessionId){
      setName('Session Note')
      setContent('')
    }
  },[sessionId])

  const startUpload = useCallback(async (entry: UploadEntry) => {
    if(!sessionId) return
    setError(null)
    updateUpload(entry.id, prev => ({...prev, status:'uploading', progress:0, error: undefined}))
    const token = window.localStorage.getItem('access_token')

    const handleSuccess = async (savedId: string) => {
      await loadDocuments()
      await loadDetail(savedId)
      updateUpload(entry.id, prev => ({...prev, progress:100, status:'done'}))
    }

    const attemptPresignedUpload = async () => {
      try{
        const presignRes = await apiFetch(`/documents/${sessionId}/presign`, { method: 'POST', body: JSON.stringify({ filename: entry.name, content_type: entry.file.type || 'application/octet-stream' }) })
        if(!presignRes.ok) return false
        const presign = await presignRes.json()
        await new Promise<void>((resolve, reject) => {
          const form = new FormData()
          Object.keys(presign.fields || {}).forEach(k => form.append(k, presign.fields[k]))
          form.append('file', entry.file)
          const xhr = new XMLHttpRequest()
          xhr.open('POST', presign.url, true)
          registerCancel(entry.id, () => {
            xhr.abort()
            reject(new Error('Upload canceled'))
          })
          xhr.upload.onprogress = (ev) => {
            if(ev.lengthComputable){
              const pct = Math.round((ev.loaded / ev.total) * 100)
              updateUpload(entry.id, prev => ({...prev, progress: pct}))
            }
          }
          xhr.onload = () => {
            if(xhr.status >= 200 && xhr.status < 300){
              resolve()
            } else {
              reject(new Error(`Upload failed ${xhr.status}`))
            }
          }
          xhr.onerror = () => reject(new Error('Network error'))
          xhr.onabort = () => reject(new Error('Upload canceled'))
          xhr.send(form)
        })
        clearCancel(entry.id)
        const key = presign.fields?.key || presign.fields?.Key || presign.key || `${sessionId}/docs/${entry.name}`
        const registerRes = await apiFetch(`/documents/${sessionId}/register`, { method: 'POST', body: JSON.stringify({ filename: key, name: entry.name, size: entry.size }) })
        const registerBody = await registerRes.json().catch(() => null)
        if(!registerRes.ok){
          throw new Error(registerBody?.detail || 'Register failed')
        }
        const savedId = registerBody?.id
        if(!savedId){
          throw new Error('Register response missing document id')
        }
        await handleSuccess(savedId)
        return true
      }catch(err){
        if((err as Error)?.message !== 'Upload canceled'){
          setError((err as Error)?.message || 'Upload failed')
        }
        throw err
      }
    }

    const uploadViaBackend = async () => {
      const form = new FormData()
      form.append('file', entry.file)
      form.append('name', entry.name)
      const controller = new AbortController()
      registerCancel(entry.id, () => controller.abort())
      const res = await fetch(buildApiUrl(`/documents/${sessionId}/upload`), {
        method: 'POST',
        body: form,
        headers: token ? { 'Authorization': `Bearer ${token}` } : undefined,
        signal: controller.signal,
      })
      clearCancel(entry.id)
      const body = await res.json().catch(() => null)
      if(!res.ok){
        throw new Error(body?.detail || 'Upload failed')
      }
      const savedId = body?.id
      if(!savedId){
        throw new Error('Upload response missing document id')
      }
      await handleSuccess(savedId)
    }

    try{
      const presignWorked = await attemptPresignedUpload()
      if(presignWorked) return
    }catch(err:any){
      clearCancel(entry.id)
      if(err?.message === 'Upload canceled' || err?.name === 'AbortError'){
        updateUpload(entry.id, prev => ({...prev, status:'canceled', error:'Upload canceled'}))
        return
      }
      updateUpload(entry.id, prev => ({...prev, status:'error', error: err?.message || 'Upload failed'}))
      return
    }

    try{
      await uploadViaBackend()
    }catch(err:any){
      clearCancel(entry.id)
      if(err?.name === 'AbortError' || err?.message === 'Upload canceled'){
        updateUpload(entry.id, prev => ({...prev, status:'canceled', error:'Upload canceled'}))
        return
      }
      const msg = err?.message || 'Upload failed'
      updateUpload(entry.id, prev => ({...prev, status:'error', error: msg}))
      setError(msg)
    }
  },[sessionId, updateUpload, loadDocuments, loadDetail, registerCancel, clearCancel])

  const cancelUpload = useCallback((id: string) => {
    const cancel = uploadControllers.current[id]
    if(cancel){
      cancel()
      clearCancel(id)
    } else {
      updateUpload(id, prev => ({...prev, status:'canceled', error:'Upload canceled'}))
    }
  },[updateUpload, clearCancel])

  const retryUpload = useCallback((id: string) => {
    const entry = uploads.find(u => u.id === id)
    if(entry){
      startUpload(entry)
    }
  },[uploads, startUpload])

  async function handleCreate(e: React.FormEvent){
    e.preventDefault()
    if(!sessionId) return
    if(!name.trim()){
      setError('Document name required')
      return
    }
    setFormBusy(true)
    setError(null)
    try{
      const res = await apiFetch(`/documents/${sessionId}`, {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), content })
      })
      if(!res.ok){
        const detail = await res.json().catch(()=>null)
        throw new Error(detail?.detail || 'Unable to save document')
      }
      const saved = await res.json()
      setName('Session Note')
      setContent('')
      await loadDocuments()
      await loadDetail(saved.id)
    }catch(err:any){
      setError(err?.message || 'Document save failed')
    }finally{
      setFormBusy(false)
    }
  }

  async function handleDelete(docId: string){
    if(!sessionId) return
    if(!window.confirm('Delete this document?')) return
    try{
      const res = await apiFetch(`/documents/${sessionId}/${docId}`, { method: 'DELETE' })
      if(!res.ok) throw new Error('Delete failed')
      if(selected?.id === docId){
        setSelected(null)
      }
      await loadDocuments()
    }catch(err:any){
      setError(err?.message || 'Unable to delete document')
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>){
    if(!sessionId) return
    const files = e.target.files
    if(!files || files.length === 0) return
    setError(null)
    const makeId = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`)
    const entries: UploadEntry[] = Array.from(files).map(file => {
      const isImage = file.type.startsWith('image/') || /(png|jpe?g|gif|webp)$/i.test(file.name)
      return {
        id: makeId(),
        name: file.name,
        progress: 0,
        status: 'uploading',
        file,
        previewUrl: isImage ? URL.createObjectURL(file) : undefined,
        size: file.size,
      }
    })
    setUploads(current => [...current, ...entries])
    entries.forEach(entry => {
      void startUpload(entry)
    })
    if(e.target) e.target.value = ''
  }

  const sortedDocs = useMemo(() => {
    return [...docs].sort((a,b)=> new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  },[docs])

  return (
    <div style={{marginTop:16, borderTop:'1px solid #222', paddingTop:12}}>
      <h3 style={{marginTop:0}}>Session Docs</h3>
      {!hasSession && <div style={{fontSize:12, color:'#aaa'}}>Open a session to create shared documents.</div>}
      {error && <div style={{color:'#ff9f9f', fontSize:12, marginBottom:8}}>{error}</div>}
      <div style={{maxHeight:140, overflowY:'auto', border:'1px solid #222', borderRadius:6, padding:8, background:'#0c0c0c'}}>
        {loading && <div style={{fontSize:12,color:'#888'}}>Loading…</div>}
        {!loading && !sortedDocs.length && <div style={{fontSize:12,color:'#888'}}>No documents yet.</div>}
        {sortedDocs.map(doc => (
          <div key={doc.id} style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6}}>
            <button type="button" style={{flex:1, textAlign:'left'}} onClick={()=>loadDetail(doc.id)} disabled={!hasSession}>
              <div style={{fontSize:13}}>{doc.name}</div>
              <div style={{fontSize:11,color:'#888'}}>{new Date(doc.created_at).toLocaleString()} · {doc.size < 1024 ? `${doc.size} B` : `${(doc.size/1024).toFixed(1)} KB`}</div>
            </button>
            <button type="button" style={{marginLeft:8}} onClick={()=>handleDelete(doc.id)} disabled={!hasSession}>✕</button>
          </div>
        ))}
      </div>

      {selected && (
        <div style={{marginTop:12}}>
          <div style={{fontSize:12,color:'#888', marginBottom:4}}>Viewing</div>
          <div style={{display:'flex', gap:12}}>
            <div style={{flex:1}}>
              <div style={{border:'1px solid #2c2c2c', borderRadius:6, padding:8, background:'#0b0b0b', maxHeight:120, overflowY:'auto'}}>
                <div style={{fontWeight:600, marginBottom:4}}>{selected.name}</div>
                <pre style={{whiteSpace:'pre-wrap', fontFamily:'inherit', margin:0}}>{selected.content || '—'}</pre>
              </div>
              <div style={{marginTop:8, display:'flex', gap:8}}>
                <a href={buildApiUrl(`/documents/${sessionId}/${selected.id}/raw`)} target="_blank" rel="noreferrer" style={{color:'#9cf'}}>Download</a>
                <button type="button" onClick={()=>{navigator.clipboard?.writeText(buildApiUrl(`/documents/${sessionId}/${selected.id}/raw`))}} style={{background:'none',border:'none',color:'#888'}}>Copy URL</button>
              </div>
            </div>
            {previewUrl && (
              <div style={{width:160}}>
                <img src={previewUrl} alt={selected.name} style={{maxWidth:'100%', borderRadius:6, border:'1px solid #222'}} />
              </div>
            )}
          </div>
        </div>
      )}

      <form onSubmit={handleCreate} style={{marginTop:12, display:'flex', flexDirection:'column', gap:8}}>
        <input value={name} onChange={e=>setName(e.target.value)} placeholder="Document name" disabled={!hasSession || formBusy} style={{padding:6, borderRadius:6, border:'1px solid #333', background:'#0b0b0b', color:'#f8f8f8'}} />
        <textarea value={content} onChange={e=>setContent(e.target.value)} placeholder="Content" rows={4} disabled={!hasSession || formBusy} style={{padding:6, borderRadius:6, border:'1px solid #333', background:'#0b0b0b', color:'#f8f8f8'}} />
        <button type="submit" disabled={!hasSession || formBusy} style={{padding:'6px 10px'}}>
          {formBusy ? 'Saving…' : 'Save Document'}
        </button>
        <div style={{display:'flex', gap:8, alignItems:'center', flexDirection:'column'}}>
          <input type="file" multiple onChange={handleUpload} disabled={!hasSession} />
          {hasActiveUploads && <div style={{fontSize:12,color:'#888'}}>Uploading…</div>}
          {uploads.length > 0 && (
            <div style={{width:'100%'}}>
              {uploads.map(u => (
                <div key={u.id} style={{display:'flex', alignItems:'center', gap:10, marginTop:8, padding:8, border:'1px solid #1a1a1a', borderRadius:6, background:'#080808'}}>
                  {u.previewUrl && (
                    <img src={u.previewUrl} alt={u.name} style={{width:48, height:48, objectFit:'cover', borderRadius:6, border:'1px solid #222'}} />
                  )}
                  <div style={{flex:1}}>
                    <div style={{fontSize:12, fontWeight:600}}>{u.name}</div>
                    <div style={{fontSize:11, color:'#888'}}>
                      {formatBytes(u.size)} · {u.status === 'uploading' ? `${u.progress}%` : u.status === 'done' ? 'Uploaded' : u.status === 'error' ? 'Error' : 'Canceled'}
                    </div>
                    <div style={{height:8, background:'#111', borderRadius:4, overflow:'hidden', marginTop:4}}>
                      <div style={{width:`${u.status==='done' ? 100 : u.progress}%`, height:'100%', transition:'width 0.2s ease', background: u.status==='error' ? '#c65b5b' : u.status==='done' ? '#3fcf8e' : '#39f'}} />
                    </div>
                    {u.error && <div style={{fontSize:11, color:'#ff9f9f', marginTop:4}}>{u.error}</div>}
                  </div>
                  <div style={{display:'flex', flexDirection:'column', gap:4}}>
                    {u.status === 'uploading' && (
                      <button type="button" onClick={()=>cancelUpload(u.id)} style={{fontSize:11}}>Cancel</button>
                    )}
                    {(u.status === 'error' || u.status === 'canceled') && (
                      <button type="button" onClick={()=>retryUpload(u.id)} style={{fontSize:11}}>Retry</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </form>
    </div>
  )
}
