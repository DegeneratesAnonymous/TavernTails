import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import { apiFetch, buildApiUrl } from '../api'
import './DocumentsPanel.css'

type DocumentMeta = {
  id: string
  session_id: string
  name: string
  category: string
  visibility: string
  size: number
  created_at: string
  filename?: string
  folder?: string
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
  folder?: string
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
  const [category, setCategory] = useState<'core' | 'flavor'>('core')
  const [visibility, setVisibility] = useState<'shared' | 'hidden'>('shared')
  const [isHost, setIsHost] = useState(false)
  const [auditLog, setAuditLog] = useState<Array<Record<string, any>>>([])
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState<string | null>(null)
  const [showAuditLog, setShowAuditLog] = useState(false)
  const [uploads, setUploads] = useState<UploadEntry[]>([])
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [refs, setRefs] = useState<Array<{id:string, meta:any}>>([])
  const [refLoading, setRefLoading] = useState(false)
  const [refError, setRefError] = useState<string | null>(null)
  const [currentFolder, setCurrentFolder] = useState<string>('')
  const [folders, setFolders] = useState<string[]>([])
  const [showNewFolderForm, setShowNewFolderForm] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [movingDocId, setMovingDocId] = useState<string | null>(null)
  const [moveDestination, setMoveDestination] = useState<string>('')
  const uploadControllers = useRef<Record<string, () => void>>({})

  const hasSession = Boolean(sessionId)
  const hasActiveUploads = useMemo(() => uploads.some(u => u.status === 'uploading'), [uploads])
  const canClearUploads = useMemo(() => uploads.some(u => u.status !== 'uploading'), [uploads])

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
      const list: DocumentMeta[] = Array.isArray(data) ? data : []
      // Hide AI-GM private docs from the player-facing UI.
      setDocs(list.filter(d => !((d.visibility || '').toLowerCase() === 'hidden' && (d.category || '').toLowerCase() === 'gm')))
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

  const loadReferences = useCallback(async () => {
    setRefLoading(true)
    setRefError(null)
    try{
      const res = await apiFetch('/references/list')
      if(!res.ok) throw new Error('Failed to load references')
      const data = await res.json()
      setRefs(Array.isArray(data) ? data : [])
    }catch(err:any){
      setRefError(err?.message || 'References unavailable')
      setRefs([])
    }finally{
      setRefLoading(false)
    }
  },[])

  const loadFolders = useCallback(async () => {
    if(!sessionId) return
    try{
      const res = await apiFetch(`/documents/${sessionId}/folders`)
      if(res.ok){
        const data = await res.json()
        setFolders(Array.isArray(data?.folders) ? data.folders : [])
      }
    }catch{ /* silently ignore */ }
  },[sessionId])

  useEffect(()=>{
    loadDocuments()
    loadReferences()
    loadFolders()
  },[loadDocuments, loadReferences, loadFolders])

  useEffect(()=>{
    if(!sessionId){
      setIsHost(false)
      setCategory('core')
      setVisibility('shared')
      setCurrentFolder('')
      setFolders([])
      return
    }
    let canceled = false
    ;(async ()=>{
      try{
        const res = await apiFetch(`/sessions/${sessionId}/meta`)
        if(!res.ok) throw new Error('meta fetch failed')
        const meta = await res.json()
        const owner = (meta?.owner || '').toString().trim().toLowerCase()
        const email = (window.localStorage.getItem('user_email') || '').trim().toLowerCase()
        const username = (window.localStorage.getItem('user_username') || '').trim().toLowerCase()
        const identifier = email || username
        const host = Boolean(identifier && owner && identifier === owner)
        if(!canceled){
          setIsHost(host)
          if(!host){
            setVisibility(prev => prev === 'hidden' ? 'shared' : prev)
          }
        }
      }catch(e){
        if(!canceled) setIsHost(false)
      }
    })()
    return ()=>{ canceled = true }
  },[sessionId, visibility])

  useEffect(()=>{
    if(!sessionId){
      setName('Session Note')
      setContent('')
      setCategory('core')
      setVisibility('shared')
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
        const registerRes = await apiFetch(`/documents/${sessionId}/register`, { method: 'POST', body: JSON.stringify({ filename: key, name: entry.name, size: entry.size, category, visibility: isHost ? visibility : 'shared', folder: entry.folder ?? '' }) })
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
      form.append('category', category)
      form.append('visibility', isHost ? visibility : 'shared')
      form.append('folder', entry.folder ?? '')
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
  },[sessionId, updateUpload, loadDocuments, loadDetail, registerCancel, clearCancel, category, visibility, isHost])

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

  const dismissUpload = useCallback((id: string) => {
    setUploads(list => {
      const entry = list.find(u => u.id === id)
      if(entry?.previewUrl){
        try{ URL.revokeObjectURL(entry.previewUrl) }catch{}
      }
      return list.filter(u => u.id !== id)
    })
  },[])

  const clearCompletedUploads = useCallback(() => {
    setUploads(list => {
      for(const entry of list){
        if(entry.status !== 'uploading' && entry.previewUrl){
          try{ URL.revokeObjectURL(entry.previewUrl) }catch{}
        }
      }
      return list.filter(u => u.status === 'uploading')
    })
  },[])

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
        body: JSON.stringify({ name: name.trim(), content, category, visibility: isHost ? visibility : 'shared' })
      })
      if(!res.ok){
        const detail = await res.json().catch(()=>null)
        throw new Error(detail?.detail || 'Unable to save document')
      }
      const saved = await res.json()
      setName('Session Note')
      setContent('')
      setCategory('core')
      setVisibility('shared')
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
        folder: currentFolder,
      }
    })
    setUploads(current => [...current, ...entries])
    entries.forEach(entry => {
      void startUpload(entry)
    })
    if(e.target) e.target.value = ''
    // also support uploading as a reference if the filename suggests a rules doc
  }

  async function handleReferenceUpload(e: React.ChangeEvent<HTMLInputElement>){
    const files = e.target.files
    if(!files || files.length === 0) return
    setRefError(null)
    const token = window.localStorage.getItem('access_token')
    for(const f of Array.from(files)){
      try{
        const form = new FormData()
        form.append('file', f)
        form.append('title', f.name)
        const res = await fetch(buildApiUrl('/references/upload'), {
          method: 'POST',
          body: form,
          headers: token ? { 'Authorization': `Bearer ${token}` } : undefined,
        })
        if(!res.ok){ const d = await res.json().catch(()=>null); throw new Error(d?.detail || 'Upload failed') }
        // refresh list
        await loadReferences()
      }catch(err:any){
        setRefError(err?.message || 'Reference upload failed')
      }
    }
    if(e.target) e.target.value = ''
  }

  const handleReindex = useCallback(async (id: string) => {
    if(!window.confirm('Rebuild embeddings for this reference?')) return
    try{
      const res = await apiFetch(`/references/${encodeURIComponent(id)}/reindex`, { method: 'POST' })
      if(!res.ok){ const d = await res.json().catch(()=>null); throw new Error(d?.detail||'Reindex failed') }
      await loadReferences()
      alert('Reindex started/completed')
    }catch(err:any){ alert(err?.message || 'Reindex failed') }
  }, [loadReferences])

  const loadAuditLog = useCallback(async () => {
    if (!sessionId || !isHost) return
    setAuditLoading(true)
    setAuditError(null)
    try {
      const res = await apiFetch(`/documents/${sessionId}/audit`)
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        throw new Error(d?.detail || `Failed to load audit log (${res.status})`)
      }
      const data = await res.json()
      setAuditLog(Array.isArray(data?.entries) ? data.entries : [])
    } catch (err: any) {
      setAuditError(err?.message || 'Could not load audit log')
    } finally {
      setAuditLoading(false)
    }
  }, [sessionId, isHost])

  const sortedDocs = useMemo(() => {
    return [...docs].sort((a,b)=> new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  },[docs])

  const selectedHasReadableText = useMemo(() => {
    if(!selected) return false
    if(!selected.content) return false
    // If it looks like we fell back to hex for binary, treat as non-previewable.
    return !/^[0-9a-f]{128,}$/i.test(selected.content.trim())
  },[selected])

  // ── Folder-derived state ─────────────────────
  const directChildFolders = useMemo(() => {
    return folders.filter(f => {
      if(currentFolder === '') return !f.includes('/')
      return f.startsWith(currentFolder + '/') && !f.slice(currentFolder.length + 1).includes('/')
    })
  }, [folders, currentFolder])

  const docsInCurrentFolder = useMemo(() => {
    return sortedDocs.filter(d => (d.folder ?? '') === currentFolder)
  }, [sortedDocs, currentFolder])

  const breadcrumb = useMemo(() => {
    if(!currentFolder) return []
    return currentFolder.split('/')
  }, [currentFolder])

  // ── Folder handlers ──────────────────────────
  async function handleFolderUpload(e: React.ChangeEvent<HTMLInputElement>) {
    if(!sessionId) return
    const files = e.target.files
    if(!files || files.length === 0) return
    setError(null)
    const makeId = () => typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`
    // Derive all unique folder paths from webkitRelativePath
    const folderPaths = new Set<string>()
    Array.from(files).forEach(file => {
      const rel = (file as any).webkitRelativePath as string || file.name
      const parts = rel.split('/')
      for(let i = 1; i < parts.length; i++){
        const seg = parts.slice(0, i).join('/')
        const full = currentFolder ? `${currentFolder}/${seg}` : seg
        folderPaths.add(full)
      }
    })
    await Promise.all(Array.from(folderPaths).map(fp =>
      apiFetch(`/documents/${sessionId}/folders`, { method: 'POST', body: JSON.stringify({ folder: fp }) }).catch(() => {})
    ))
    await loadFolders()
    const entries: UploadEntry[] = Array.from(files).map(file => {
      const rel = (file as any).webkitRelativePath as string || file.name
      const parts = rel.split('/')
      const fileFolder = parts.length > 1
        ? (currentFolder ? `${currentFolder}/${parts.slice(0, -1).join('/')}` : parts.slice(0, -1).join('/'))
        : currentFolder
      const isImage = file.type.startsWith('image/') || /(png|jpe?g|gif|webp)$/i.test(file.name)
      return {
        id: makeId(),
        name: file.name,
        progress: 0,
        status: 'uploading' as const,
        file,
        previewUrl: isImage ? URL.createObjectURL(file) : undefined,
        size: file.size,
        folder: fileFolder,
      }
    })
    setUploads(cur => [...cur, ...entries])
    entries.forEach(entry => { void startUpload(entry) })
    if(e.target) e.target.value = ''
  }

  async function handleCreateFolder(e: React.FormEvent) {
    e.preventDefault()
    if(!sessionId || !newFolderName.trim()) return
    const path = currentFolder ? `${currentFolder}/${newFolderName.trim()}` : newFolderName.trim()
    setError(null)
    try{
      const res = await apiFetch(`/documents/${sessionId}/folders`, {
        method: 'POST',
        body: JSON.stringify({ folder: path }),
      })
      if(!res.ok){
        const d = await res.json().catch(() => null)
        throw new Error(d?.detail || 'Create folder failed')
      }
      setNewFolderName('')
      setShowNewFolderForm(false)
      await loadFolders()
    }catch(err:any){
      setError(err?.message || 'Create folder failed')
    }
  }

  async function handleDeleteFolder(folderPath: string) {
    if(!sessionId) return
    if(!window.confirm(`Delete folder "${folderPath}"? (Only works if the folder is empty.)`)) return
    setError(null)
    try{
      const res = await apiFetch(`/documents/${sessionId}/folders/${folderPath}`, { method: 'DELETE' })
      if(!res.ok){
        const d = await res.json().catch(() => null)
        throw new Error(d?.detail || 'Delete folder failed')
      }
      if(currentFolder === folderPath || currentFolder.startsWith(folderPath + '/')) setCurrentFolder('')
      await loadFolders()
    }catch(err:any){
      setError(err?.message || 'Unable to delete folder')
    }
  }

  async function handleMoveDoc(docId: string, targetFolder: string) {
    if(!sessionId) return
    setError(null)
    try{
      const res = await apiFetch(`/documents/${sessionId}/${docId}/move`, {
        method: 'PATCH',
        body: JSON.stringify({ folder: targetFolder }),
      })
      if(!res.ok){
        const d = await res.json().catch(() => null)
        throw new Error(d?.detail || 'Move failed')
      }
      setMovingDocId(null)
      await loadDocuments()
    }catch(err:any){
      setError(err?.message || 'Move failed')
    }
  }

  return (
    <div className="docsPanel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <h3 className="docsPanel__title" style={{ margin: 0 }}>Session Docs</h3>
        {isHost && hasSession && (
          <button
            type="button"
            className="docsPanel__tinyBtn"
            style={{ marginLeft: 'auto' }}
            onClick={() => {
              setShowAuditLog(v => {
                if (!v) loadAuditLog()
                return !v
              })
            }}
            title="Toggle access log"
            aria-label="Toggle access log"
          >
            {showAuditLog ? 'Hide Log' : 'Access Log'}
          </button>
        )}
      </div>
      {isHost && showAuditLog && (
        <div className="docsPanel__auditLog">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <strong style={{ fontSize: 13 }}>Access Log</strong>
            <button type="button" className="docsPanel__tinyBtn" onClick={loadAuditLog} disabled={auditLoading}>
              {auditLoading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
          {auditError && <div className="docsPanel__error">{auditError}</div>}
          {!auditLoading && auditLog.length === 0 && <div className="docsPanel__hint">No audit entries yet.</div>}
          <div style={{ maxHeight: 200, overflow: 'auto' }}>
            {auditLog.slice().reverse().map((entry, i) => (
              <div key={i} className="docsPanel__auditRow">
                <span className="docsPanel__auditTs">{entry.ts ? new Date(entry.ts).toLocaleString() : '—'}</span>
                <span className={`docsPanel__auditAction ${entry.ok === false ? 'docsPanel__auditAction--denied' : ''}`}>
                  {entry.action}
                </span>
                {entry.actor && <span className="docsPanel__auditActor">{entry.actor}</span>}
                {entry.doc_id && <span className="docsPanel__auditDoc">{entry.doc_id}</span>}
                {entry.detail && <span className="docsPanel__auditDetail">{entry.detail}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
      {!hasSession && <div className="docsPanel__hint">Open a session to create shared documents.</div>}
      {error && <div className="docsPanel__error">{error}</div>}

      {/* Folder navigation bar */}
      {hasSession && (
        <div className="docsPanel__folderNav">
          <div className="docsPanel__breadcrumb">
            <button
              type="button"
              className={`docsPanel__breadcrumbItem${currentFolder === '' ? ' docsPanel__breadcrumbItem--active' : ''}`}
              onClick={() => setCurrentFolder('')}
            >
              📂 root
            </button>
            {breadcrumb.map((seg, i) => {
              const path = breadcrumb.slice(0, i + 1).join('/')
              return (
                <React.Fragment key={path}>
                  <span className="docsPanel__breadcrumbSep">/</span>
                  <button
                    type="button"
                    className={`docsPanel__breadcrumbItem${i === breadcrumb.length - 1 ? ' docsPanel__breadcrumbItem--active' : ''}`}
                    onClick={() => setCurrentFolder(path)}
                  >
                    {seg}
                  </button>
                </React.Fragment>
              )
            })}
          </div>
          <button
            type="button"
            className="docsPanel__tinyBtn"
            onClick={() => setShowNewFolderForm(v => !v)}
            title="Create new folder"
          >
            {showNewFolderForm ? '✕ Cancel' : '+ Folder'}
          </button>
        </div>
      )}
      {showNewFolderForm && hasSession && (
        <form onSubmit={handleCreateFolder} className="docsPanel__newFolderForm">
          <input
            value={newFolderName}
            onChange={e => setNewFolderName(e.target.value)}
            placeholder={currentFolder ? `New folder inside "${currentFolder}"` : 'New folder name'}
            className="docsPanel__input"
            autoFocus
          />
          <button type="submit" className="docsPanel__tinyBtn" disabled={!newFolderName.trim()}>Create</button>
        </form>
      )}

      <div className="docsPanel__list">
        {loading && <div className="docsPanel__loading">Loading…</div>}
        {!loading && !docsInCurrentFolder.length && !directChildFolders.length && (
          <div className="docsPanel__loading">
            {currentFolder ? `No documents in "${currentFolder}".` : 'No documents yet.'}
          </div>
        )}
        {/* Folder items appear above files */}
        {directChildFolders.map(folderPath => {
          const folderName = currentFolder ? folderPath.slice(currentFolder.length + 1) : folderPath
          return (
            <div key={folderPath} className="docsPanel__folderRow">
              <button
                type="button"
                className="docsPanel__docButton docsPanel__folderBtn"
                onClick={() => setCurrentFolder(folderPath)}
              >
                <span className="docsPanel__folderIcon">📁</span>
                <span className="docsPanel__folderName">{folderName}/</span>
              </button>
              <button
                type="button"
                className="docsPanel__deleteBtn"
                onClick={() => handleDeleteFolder(folderPath)}
                aria-label="Delete folder"
                title="Delete (only if empty)"
              >
                ✕
              </button>
            </div>
          )
        })}
        {/* Documents in current folder */}
        {docsInCurrentFolder.map(doc => (
          <div key={doc.id} className="docsPanel__docRow">
            <button type="button" className="docsPanel__docButton" onClick={()=>loadDetail(doc.id)} disabled={!hasSession}>
              <div className="docsPanel__docName">
                {doc.name}
                {isHost && doc.visibility === 'hidden' && <span className="docsPanel__tag">(Hidden)</span>}
              </div>
              <div className="docsPanel__docMeta">{new Date(doc.created_at).toLocaleString()} · {formatBytes(doc.size)} · {doc.category}</div>
            </button>
            {hasSession && (
              <div className="docsPanel__docActions">
                {movingDocId === doc.id ? (
                  <div className="docsPanel__moveMenu">
                    <select
                      className="docsPanel__select docsPanel__moveSelect"
                      value={moveDestination}
                      onChange={e => setMoveDestination(e.target.value)}
                    >
                      <option value="">/ root</option>
                      {folders.map(f => <option key={f} value={f}>{f}/</option>)}
                    </select>
                    <button type="button" className="docsPanel__tinyBtn" onClick={() => handleMoveDoc(doc.id, moveDestination)}>OK</button>
                    <button type="button" className="docsPanel__tinyBtn" onClick={() => setMovingDocId(null)}>✕</button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="docsPanel__tinyBtn"
                    onClick={() => { setMovingDocId(doc.id); setMoveDestination(doc.folder ?? '') }}
                    title="Move to folder"
                  >
                    Move
                  </button>
                )}
                <button type="button" className="docsPanel__deleteBtn" onClick={()=>handleDelete(doc.id)} aria-label="Delete document">✕</button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 14 }}>
        <h4 style={{ margin: '8px 0' }}>Reference Documents</h4>
        <div style={{ color: '#aaa', fontSize: 12, marginBottom: 6 }}>
          Supported: PDF, Word (.docx), Excel (.xlsx), HTML, plain text (.txt/.md/.csv), JSON. The AI uses these as learning data during gameplay.
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
          <input type="file" accept=".pdf,.docx,.doc,.xlsx,.xls,.html,.htm,.txt,.md,.csv,.json" multiple onChange={handleReferenceUpload} />
          <div style={{ color: '#999', fontSize: 13 }}>{refLoading ? 'Refreshing…' : `${refs.length} references`}</div>
        </div>
        {refError && <div className="docsPanel__error">{refError}</div>}
        {refs.length === 0 && !refLoading ? <div className="docsPanel__hint">No references uploaded.</div> : null}
        <div style={{ maxHeight: 160, overflow: 'auto', border: '1px solid rgba(255,255,255,0.04)', padding: 8 }}>
          {refs.map(r => (
            <div key={r.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0' }}>
              <div>
                <div style={{ fontWeight: 700 }}>{r.meta?.title || r.id}</div>
                <div className="muted" style={{ fontSize: 12 }}>{r.meta?.filename || ''} · {r.meta?.pages || 0} chunk{(r.meta?.pages || 0) !== 1 ? 's' : ''}</div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <a className="docsPanel__link" href={buildApiUrl(`/references/${encodeURIComponent(r.id)}/raw`)} target="_blank" rel="noreferrer">Open</a>
                <button type="button" className="docsPanel__tinyBtn" onClick={()=>handleReindex(r.id)}>Reindex</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="docsPanel__viewer">
          <div className="docsPanel__viewerLabel">Viewing</div>
          <div className="docsPanel__viewerGrid">
            <div className="docsPanel__viewerBody">
              <div className="docsPanel__viewerCard">
                <div className="docsPanel__viewerTitle">{selected.name}</div>
                {selectedHasReadableText ? (
                  <pre className="docsPanel__viewerPre">{selected.content}</pre>
                ) : (
                  <div className="docsPanel__hint">Preview unavailable for this file type. Use Download.</div>
                )}
              </div>
              <div className="docsPanel__viewerActions">
                <a href={buildApiUrl(`/documents/${sessionId}/${selected.id}/raw`)} target="_blank" rel="noreferrer" className="docsPanel__link">Download</a>
                <button type="button" onClick={()=>{navigator.clipboard?.writeText(buildApiUrl(`/documents/${sessionId}/${selected.id}/raw`))}} className="docsPanel__copyBtn">Copy URL</button>
              </div>
            </div>
            {previewUrl && (
              <div className="docsPanel__imagePreview">
                <img src={previewUrl} alt={selected.name} />
              </div>
            )}
          </div>
        </div>
      )}

      <div className="docsPanel__uploads">
        <h4 style={{ margin: '8px 0 4px' }}>Upload File</h4>
        <div className="docsPanel__uploadsTop">
          <input type="file" multiple onChange={handleUpload} disabled={!hasSession} />
          <label className={`docsPanel__tinyBtn docsPanel__folderUploadLabel${!hasSession ? ' docsPanel__tinyBtn--disabled' : ''}`} title="Upload a folder (preserves folder structure)">
            📂 Folder
            <input
              type="file"
              {...({ webkitdirectory: 'true' } as React.InputHTMLAttributes<HTMLInputElement>)}
              style={{ display: 'none' }}
              onChange={handleFolderUpload}
              disabled={!hasSession}
            />
          </label>
          {hasActiveUploads && <div className="docsPanel__uploadsHint">Uploading…</div>}
          {!hasActiveUploads && uploads.length > 0 && <div className="docsPanel__uploadsHint">Uploads</div>}
          {canClearUploads && (
            <button type="button" onClick={clearCompletedUploads} className="docsPanel__tinyBtn">Clear completed</button>
          )}
        </div>
        {uploads.length > 0 && (
          <div className="docsPanel__uploadsList">
            {uploads.map(u => (
              <div key={u.id} className="docsPanel__uploadRow">
                {u.previewUrl && (
                  <img src={u.previewUrl} alt={u.name} className="docsPanel__uploadThumb" />
                )}
                <div className="docsPanel__uploadBody">
                  <div className="docsPanel__uploadName">{u.name}</div>
                  <div className="docsPanel__uploadMeta">
                    {formatBytes(u.size)} · {u.status === 'uploading' ? `${u.progress}%` : u.status === 'done' ? 'Uploaded' : u.status === 'error' ? 'Error' : 'Canceled'}
                  </div>
                  <div className="docsPanel__bar">
                    <div
                      className="docsPanel__barFill"
                      style={{
                        width: `${u.status==='done' ? 100 : u.progress}%`,
                        background: u.status==='error' ? '#c65b5b' : u.status==='done' ? '#3fcf8e' : '#39f'
                      }}
                    />
                  </div>
                  {u.error && <div className="docsPanel__uploadErr">{u.error}</div>}
                </div>
                <div className="docsPanel__uploadActions">
                  {u.status === 'uploading' && (
                    <button type="button" onClick={()=>cancelUpload(u.id)} className="docsPanel__tinyBtn">Cancel</button>
                  )}
                  {(u.status === 'error' || u.status === 'canceled') && (
                    <button type="button" onClick={()=>retryUpload(u.id)} className="docsPanel__tinyBtn">Retry</button>
                  )}
                  {u.status !== 'uploading' && (
                    <button type="button" onClick={()=>dismissUpload(u.id)} className="docsPanel__tinyBtn">Dismiss</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <form onSubmit={handleCreate} className="docsPanel__form">
        <h4 style={{ margin: '8px 0 4px' }}>Create Text Document</h4>
        <input value={name} onChange={e=>setName(e.target.value)} placeholder="Document name" disabled={!hasSession || formBusy} className="docsPanel__input" />
        <div className="docsPanel__row">
          <label className="docsPanel__label">Category</label>
          <select value={category} onChange={e=>setCategory(e.target.value as any)} disabled={!hasSession || formBusy} className="docsPanel__select">
            <option value="core">Core</option>
            <option value="flavor">Flavor</option>
          </select>
          <label className="docsPanel__label">Visibility</label>
          <select value={isHost ? visibility : 'shared'} onChange={e=>setVisibility(e.target.value as any)} disabled={!hasSession || formBusy || !isHost} className="docsPanel__select" style={{opacity: isHost ? 1 : 0.6}}>
            <option value="shared">Shared</option>
            <option value="hidden">Hidden (host only)</option>
          </select>
          {!isHost && hasSession && <span className="docsPanel__note">Hidden docs require host.</span>}
        </div>
        <textarea value={content} onChange={e=>setContent(e.target.value)} placeholder="Content" rows={4} disabled={!hasSession || formBusy} className="docsPanel__textarea" />
        <button type="submit" disabled={!hasSession || formBusy} className="docsPanel__saveBtn">
          {formBusy ? 'Saving…' : 'Save Document'}
        </button>
      </form>
    </div>
  )
}
