import React, { useEffect, useMemo, useState } from 'react'

import { apiFetch, API_BASE, buildApiUrl } from '../../api'
import PageHeader from '../ui/PageHeader'
import Modal from '../ui/Modal'

type CharacterPreview = {
  name: string
  level: number
  class_name?: string | null
  sheet?: any
}

type ExistingCharacter = {
  id: number
  name: string
  level: number
  class_name?: string | null
}

function normalizeName(name: string): string {
  return (name || '').trim().toLowerCase()
}

function suggestUniqueName(baseName: string, existingNames: string[]): string {
  const base = (baseName || '').trim() || 'Imported Character'
  const existing = new Set(existingNames.map(normalizeName))
  if (!existing.has(normalizeName(base))) return base
  for (let i = 2; i <= 99; i++) {
    const candidate = `${base} ${i}`
    if (!existing.has(normalizeName(candidate))) return candidate
  }
  return `${base} 2`
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

type Props = {
  activeSessionId: string | null
  onRefreshCharacters: () => Promise<void>
  onAssignCharacterToSession: (characterId: number | null) => Promise<void>
  onSetActiveCharacterId: (characterId: number | null) => void
  onDone: () => void
  onGoToGameplay: () => void
  initialMode?: 'ddb-link' | 'paste' | 'file' | 'pdf'
}

export default function ImportCharacterView({
  activeSessionId,
  onRefreshCharacters,
  onAssignCharacterToSession,
  onSetActiveCharacterId,
  onDone,
  onGoToGameplay,
  initialMode,
}: Props) {
  const [mode, setMode] = useState<'ddb-link' | 'paste' | 'file' | 'pdf'>(initialMode || 'paste')
  const [rawJson, setRawJson] = useState('')
  const [ddbUrl, setDdbUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [pdfName, setPdfName] = useState('')
  const [pdfLevel, setPdfLevel] = useState('')
  const [pdfClassName, setPdfClassName] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [messageKind, setMessageKind] = useState<'ok' | 'error'>('ok')
  const [autoAssignToSession, setAutoAssignToSession] = useState(true)

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [featureOpen, setFeatureOpen] = useState(false)
  const [featureText, setFeatureText] = useState<string | null>(null)
  const [featureRefs, setFeatureRefs] = useState<any[] | null>(null)
  const [featureRefLoading, setFeatureRefLoading] = useState(false)
  const [previewSource, setPreviewSource] = useState<'paste' | 'file' | 'pdf' | null>(null)
  const [preview, setPreview] = useState<CharacterPreview | null>(null)
  const [nameConflict, setNameConflict] = useState<ExistingCharacter | null>(null)

  const [reviewAction, setReviewAction] = useState<'create' | 'overwrite'>('create')
  const [reviewOverwriteId, setReviewOverwriteId] = useState<number | null>(null)
  const [reviewName, setReviewName] = useState('')
  const [reviewLevel, setReviewLevel] = useState('')
  const [reviewClassName, setReviewClassName] = useState('')
  const [includeClassName, setIncludeClassName] = useState(true)
  const [includeDdbLink, setIncludeDdbLink] = useState(true)
  const [includeRawJson, setIncludeRawJson] = useState(true)
  const [includePdfText, setIncludePdfText] = useState(true)

  const [backendChecked, setBackendChecked] = useState(false)
  const [backendCheckError, setBackendCheckError] = useState<string | null>(null)
  const [backendPaths, setBackendPaths] = useState<Record<string, any> | null>(null)

  const backendCaps = useMemo(() => {
    const hasPath = (path: string) => Boolean(backendPaths && Object.prototype.hasOwnProperty.call(backendPaths, path))
    return {
      importJson: hasPath('/characters/import/preview') || hasPath('/characters/import') || hasPath('/characters/import/file'),
      importPdf: hasPath('/characters/import/pdf/preview') || hasPath('/characters/import/pdf'),
      importLink: hasPath('/characters/import/link'),
    }
  }, [backendPaths])

  function shortPreview(text: string, limit = 140) {
    if (!text) return ''
    const collapsed = text.replace(/\s+/g, ' ').trim()
    if (collapsed.length <= limit) return collapsed
    return collapsed.slice(0, limit).trim() + '…'
  }

  const pdfPreview = useMemo(() => {
    if (previewSource !== 'pdf' || !preview?.sheet || typeof preview.sheet !== 'object') return null
    const sheet = preview.sheet as any
    const stats = (sheet?.stats && typeof sheet.stats === 'object') ? sheet.stats : {}
    const hp = (sheet?.hp && typeof sheet.hp === 'object') ? sheet.hp : {}
    const ac = typeof sheet?.ac === 'number' ? sheet.ac : null
    const features = Array.isArray(sheet?.features) ? sheet.features : []
    const importMeta = (sheet?.import && typeof sheet.import === 'object') ? sheet.import : {}
    const widgets = (importMeta?.pdf_widgets && typeof importMeta.pdf_widgets === 'object') ? importMeta.pdf_widgets : {}
    const widgetCount = typeof widgets?.count === 'number' ? widgets.count : null
    const rawTextLen = typeof importMeta?.raw_text_len === 'number'
      ? importMeta.raw_text_len
      : typeof sheet?.raw_text === 'string'
        ? sheet.raw_text.length
        : null
    const extracted = (importMeta?.extracted && typeof importMeta.extracted === 'object') ? importMeta.extracted : {}
    const overrides = (importMeta?.overrides && typeof importMeta.overrides === 'object') ? importMeta.overrides : {}

    return {
      stats,
      hp,
      ac,
      featuresCount: features.length,
      widgetCount,
      rawTextLen,
      extracted,
      overrides,
    }
  }, [previewSource, preview])

  useEffect(() => {
    if (initialMode) setMode(initialMode)
  }, [initialMode])

  useEffect(() => {
    let canceled = false
    async function checkBackendCapabilities() {
      setBackendChecked(false)
      setBackendCheckError(null)
      try {
        const res = await fetch(buildApiUrl('/openapi.json'), { method: 'GET' })
        if (!res.ok) throw new Error(`Backend returned ${res.status}`)
        const data = await res.json().catch(() => null)
        const paths = data?.paths && typeof data.paths === 'object' ? data.paths : null
        if (!canceled) {
          setBackendPaths(paths)
          setBackendChecked(true)
        }
      } catch (e: any) {
        if (!canceled) {
          setBackendPaths(null)
          setBackendChecked(true)
          setBackendCheckError(e?.message || 'Unable to reach backend')
        }
      }
    }
    checkBackendCapabilities()
    return () => {
      canceled = true
    }
  }, [])

  const showMessage = (kind: 'ok' | 'error', text: string) => {
    setMessageKind(kind)
    setMessage(text)
  }

  const resetConfirmState = () => {
    setConfirmOpen(false)
    setConfirmBusy(false)
    setConfirmError(null)
    setPreviewSource(null)
    setPreview(null)
    setNameConflict(null)
    setReviewAction('create')
    setReviewOverwriteId(null)
    setReviewName('')
    setReviewLevel('')
    setReviewClassName('')
    setIncludeClassName(true)
    setIncludeDdbLink(true)
    setIncludeRawJson(true)
    setIncludePdfText(true)
  }

  const handleFeatureClick = async (text: string) => {
    setFeatureText(text)
    setFeatureOpen(true)
    setFeatureRefs(null)
    setFeatureRefLoading(true)
    try {
      const q = encodeURIComponent(text || '')
      const res = await apiFetch(`/references/search?q=${q}&top_k=3`)
      if (!res.ok) {
        setFeatureRefs([])
      } else {
        const data = await res.json().catch(() => null)
        setFeatureRefs((data && data.results) || [])
      }
    } catch {
      setFeatureRefs([])
    } finally {
      setFeatureRefLoading(false)
    }
  }

  const openConfirmForPreview = async (source: 'paste' | 'file' | 'pdf', nextPreview: CharacterPreview) => {
    setPreviewSource(source)
    setPreview(nextPreview)
    setConfirmError(null)
    setConfirmOpen(true)

    // Initialize review fields.
    setReviewName(nextPreview?.name || '')
    setReviewLevel(String(nextPreview?.level || 1))
    setReviewClassName(nextPreview?.class_name || '')
    setIncludeClassName(Boolean(nextPreview?.class_name))
    setIncludeDdbLink(Boolean(ddbUrl.trim()))
    setIncludeRawJson(true)
    setIncludePdfText(true)

    // Fetch existing characters to detect name conflicts.
    try {
      const res = await apiFetch('/characters', { method: 'GET' })
      if (!res.ok) return
      const data = await res.json().catch(() => ({}))
      const list = Array.isArray(data?.characters) ? data.characters : []
      const cleaned: ExistingCharacter[] = list
        .filter((c: any) => typeof c?.id === 'number')
        .map((c: any) => ({
          id: c.id,
          name: String(c?.name || ''),
          level: typeof c?.level === 'number' ? c.level : 1,
          class_name: c?.class_name ?? null,
        }))

      const existingNames = cleaned.map((c) => c.name)
      const match = cleaned.find((c) => normalizeName(c.name) === normalizeName(nextPreview?.name || '')) || null
      setNameConflict(match)

      if (match) {
        // Default to creating a new character with a safe unique name.
        setReviewAction('create')
        setReviewOverwriteId(match.id)
        setReviewName(suggestUniqueName(nextPreview?.name || 'Imported Character', existingNames))
      }
    } catch {
      // Non-fatal.
    }
  }

  const beginJsonPreview = async (raw: string, source: 'paste' | 'file') => {
    if (!raw.trim()) {
      showMessage('error', 'Paste JSON to import.')
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const res = await apiFetch('/characters/import/preview', {
        method: 'POST',
        body: JSON.stringify({ raw_json: raw, ddb_url: ddbUrl.trim() || null, source }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        showMessage('error', err?.detail || 'Failed to preview import')
        return
      }
      const data = await res.json().catch(() => ({}))
      const p = data?.preview
      if (!p || typeof p?.name !== 'string') {
        showMessage('error', 'Backend preview response was invalid.')
        return
      }
      await openConfirmForPreview(source, p)
    } catch {
      showMessage('error', 'Network error')
    } finally {
      setBusy(false)
    }
  }

  const beginPdfPreview = async () => {
    if (!file) {
      showMessage('error', 'Choose a PDF file.')
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const form = new FormData()
      form.append('file', file)
      if (pdfName.trim()) form.append('name', pdfName.trim())
      if (pdfClassName.trim()) form.append('class_name', pdfClassName.trim())
      if (pdfLevel.trim()) form.append('level', pdfLevel.trim())
      const qs = new URLSearchParams()
      qs.set('source', 'pdf')
      if (ddbUrl.trim()) qs.set('ddb_url', ddbUrl.trim())
      const res = await apiFetch(`/characters/import/pdf/preview?${qs.toString()}`, {
        method: 'POST',
        body: form,
        headers: {},
      })
      if (!res.ok) {
        if (res.status === 405) {
          showMessage(
            'error',
            `PDF import preview endpoint is not available on the backend (${API_BASE}). Restart the backend (recommended: run start-app.ps1 again) and try the upload again.`
          )
          return
        }
        const err = await res.json().catch(() => ({}))
        showMessage('error', err?.detail || 'Failed to preview PDF import')
        return
      }
      const data = await res.json().catch(() => ({}))
      const p = data?.preview
      if (!p || typeof p?.name !== 'string') {
        showMessage('error', 'Backend preview response was invalid.')
        return
      }
      await openConfirmForPreview('pdf', p)
    } catch {
      showMessage('error', 'Network error')
    } finally {
      setBusy(false)
    }
  }

  const finalizeImport = async () => {
    if (!preview) return

    const name = reviewName.trim() || preview.name
    const parsedLevel = (() => {
      const n = parseInt((reviewLevel || '').trim(), 10)
      return Number.isNaN(n) ? null : n
    })()
    const safeLevel = parsedLevel ? Math.max(1, Math.min(20, parsedLevel)) : preview.level
    const finalClass = includeClassName ? (reviewClassName.trim() || null) : null

    if (!name.trim()) {
      setConfirmError('Character name is required.')
      return
    }

    // Build sheet with user-selected sections.
    const sheet = cloneJson(preview.sheet || {})
    if (!includeDdbLink) {
      if (sheet?.import) {
        delete sheet.import.ddb_url
      }
    } else {
      if (sheet?.import && ddbUrl.trim()) {
        sheet.import.ddb_url = ddbUrl.trim()
      }
    }

    if (previewSource === 'paste' || previewSource === 'file') {
      if (!includeRawJson) {
        delete sheet.raw
      }
    }
    if (previewSource === 'pdf') {
      if (!includePdfText) {
        delete sheet.raw_text
        if (sheet?.import) {
          delete sheet.import.raw_text_len
        }
      }
    }

    setConfirmBusy(true)
    setConfirmError(null)
    try {
      if (reviewAction === 'overwrite' && reviewOverwriteId) {
        const res = await apiFetch(`/characters/${reviewOverwriteId}`, {
          method: 'PUT',
          body: JSON.stringify({ name, level: safeLevel, class_name: finalClass, sheet }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          setConfirmError(err?.detail || 'Failed to overwrite character')
          return
        }
        const data = await res.json().catch(() => ({}))
        const updatedId = typeof data?.character?.id === 'number' ? data.character.id : reviewOverwriteId
        resetConfirmState()
        await handleSaved(updatedId, 'updated')
        return
      }

      // If we have an active session and a PDF file, upload the raw PDF to session documents
      if (previewSource === 'pdf' && file && activeSessionId) {
        try {
          const df = new FormData()
          df.append('file', file)
          df.append('name', name)
          const uploadRes = await fetch(`${API_BASE}/documents/${activeSessionId}/upload`, {
            method: 'POST',
            body: df,
          })
          if (uploadRes.ok) {
            const uploaded = await uploadRes.json().catch(() => ({}))
            if (uploaded?.id) {
              if (!sheet.import) sheet.import = {}
              ;(sheet.import as any).document_id = uploaded.id
              ;(sheet.import as any).document_session_id = activeSessionId
            }
          }
        } catch (e) {
          // non-fatal — continue with import even if document upload failed
        }
      }

      const res = await apiFetch('/characters', {
        method: 'POST',
        body: JSON.stringify({ name, level: safeLevel, class_name: finalClass, sheet }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setConfirmError(err?.detail || 'Failed to create character')
        return
      }
      const data = await res.json().catch(() => ({}))
      const createdId = typeof data?.character?.id === 'number' ? data.character.id : null
      resetConfirmState()
      await handleSaved(createdId, 'created')
    } catch {
      setConfirmError('Network error')
    } finally {
      setConfirmBusy(false)
    }
  }

  const handleSaved = async (characterId: number | null, verb: 'created' | 'updated' = 'created') => {
    setRawJson('')
    setFile(null)
    setPdfName('')
    setPdfLevel('')
    setPdfClassName('')
    await onRefreshCharacters()

    // If auto-assign is enabled and session is active, assign but still go to Manage Characters.
    if (activeSessionId && characterId !== null && autoAssignToSession) {
      onSetActiveCharacterId(characterId)
      await onAssignCharacterToSession(characterId)
      showMessage('ok', `Character ${verb} and assigned to active session.`)
      // Do NOT auto-navigate to gameplay; bring user to Manage characters so they can see the list.
      if (typeof onDone === 'function') {
        onDone()
      }
      return
    }

    // Default: go to the manage characters page so user can view all listed characters.
    showMessage('ok', `Character ${verb}.`)
    if (typeof onDone === 'function') {
      onDone()
    }
  }

  return (
    <section className="dashboard-panel stack">
      <Modal
        open={confirmOpen}
        title="Review Import"
        onClose={() => {
          if (confirmBusy) return
          resetConfirmState()
        }}
      >
        {!preview ? (
          <div className="inline-alert inline-alert-error">No preview available.</div>
        ) : (
          <div className="stack">
            {confirmError ? <div className="inline-alert inline-alert-error">{confirmError}</div> : null}

            {nameConflict ? (
              <div className="inline-alert" style={{ borderColor: 'rgba(255, 190, 110, 0.35)', background: 'rgba(255, 190, 110, 0.08)' }}>
                A character named <b>{nameConflict.name}</b> already exists.
              </div>
            ) : null}

            <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div style={{ fontWeight: 750 }}>Basic info</div>
              <div className="row-wrap" style={{ gap: 10 }}>
                <div className="stack" style={{ gap: 6, minWidth: 240, flex: 1 }}>
                  <label className="muted">Name</label>
                  <input className="input" value={reviewName} onChange={(e) => setReviewName(e.target.value)} disabled={confirmBusy} />
                </div>
                <div className="stack" style={{ gap: 6, minWidth: 140 }}>
                  <label className="muted">Level</label>
                  <input
                    className="input"
                    inputMode="numeric"
                    value={reviewLevel}
                    onChange={(e) => setReviewLevel(e.target.value)}
                    disabled={confirmBusy}
                  />
                </div>
                <div className="stack" style={{ gap: 6, minWidth: 220, flex: 1 }}>
                  <label className="muted">Class</label>
                  <input
                    className="input"
                    value={reviewClassName}
                    onChange={(e) => setReviewClassName(e.target.value)}
                    disabled={confirmBusy || !includeClassName}
                    placeholder="(optional)"
                  />
                  <label className="row" style={{ gap: 8, userSelect: 'none' }}>
                    <input type="checkbox" checked={includeClassName} onChange={(e) => setIncludeClassName(e.target.checked)} disabled={confirmBusy} />
                    <span className="muted">Import class</span>
                  </label>
                </div>
              </div>
            </div>

            <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div style={{ fontWeight: 750 }}>What to include</div>
              <label className="row" style={{ gap: 10, userSelect: 'none' }}>
                <input type="checkbox" checked={includeDdbLink} onChange={(e) => setIncludeDdbLink(e.target.checked)} disabled={confirmBusy} />
                <span className="muted">Store D&amp;D Beyond link reference (if provided)</span>
              </label>

              {previewSource === 'paste' || previewSource === 'file' ? (
                <label className="row" style={{ gap: 10, userSelect: 'none' }}>
                  <input type="checkbox" checked={includeRawJson} onChange={(e) => setIncludeRawJson(e.target.checked)} disabled={confirmBusy} />
                  <span className="muted">Store raw JSON for future parsing improvements</span>
                </label>
              ) : null}

              {previewSource === 'pdf' ? (
                <label className="row" style={{ gap: 10, userSelect: 'none' }}>
                  <input type="checkbox" checked={includePdfText} onChange={(e) => setIncludePdfText(e.target.checked)} disabled={confirmBusy} />
                  <span className="muted">Store extracted PDF text for future parsing improvements</span>
                </label>
              ) : null}
            </div>

            {pdfPreview ? (
              <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
                <div style={{ fontWeight: 750 }}>PDF extraction summary</div>
                <div className="row-wrap" style={{ gap: 14 }}>
                  <div className="stack" style={{ gap: 6, minWidth: 200 }}>
                    <div className="muted">Ability scores</div>
                    <div className="row-wrap" style={{ gap: 8 }}>
                      {(['str', 'dex', 'con', 'int', 'wis', 'cha'] as const).map((k) => (
                        <div key={k} className="input input-mono" style={{ padding: '6px 8px' }}>
                          <strong>{k.toUpperCase()}:</strong> {typeof (pdfPreview.stats as any)[k] === 'number' ? (pdfPreview.stats as any)[k] : '—'}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="stack" style={{ gap: 6, minWidth: 180 }}>
                    <div className="muted">Combat</div>
                    <div><strong>AC:</strong> {pdfPreview.ac ?? '—'}</div>
                    <div><strong>HP:</strong> {pdfPreview.hp?.current ?? '—'} / {pdfPreview.hp?.max ?? '—'}</div>
                    <div><strong>Temp:</strong> {pdfPreview.hp?.temp ?? '—'}</div>
                  </div>
                  <div className="stack" style={{ gap: 6, minWidth: 160 }}>
                    <div className="muted">Features</div>
                    <div>{pdfPreview.featuresCount} detected</div>
                  </div>
                  <div className="stack" style={{ gap: 6, minWidth: 180 }}>
                    <div className="muted">Extraction</div>
                    <div><strong>Widgets:</strong> {pdfPreview.widgetCount ?? '—'}</div>
                    <div><strong>Text chars:</strong> {pdfPreview.rawTextLen ?? '—'}</div>
                  </div>
                </div>

                {(pdfPreview.extracted?.name || pdfPreview.extracted?.level || pdfPreview.extracted?.class_name) ? (
                  <div className="muted" style={{ fontSize: 12 }}>
                    Extracted: {pdfPreview.extracted?.name ? `Name “${pdfPreview.extracted.name}”` : 'Name —'} •
                    {pdfPreview.extracted?.level ? ` Level ${pdfPreview.extracted.level}` : ' Level —'} •
                    {pdfPreview.extracted?.class_name ? ` Class ${pdfPreview.extracted.class_name}` : ' Class —'}
                  </div>
                ) : null}

                {(pdfPreview.overrides?.name || pdfPreview.overrides?.level || pdfPreview.overrides?.class_name) ? (
                  <div className="muted" style={{ fontSize: 12 }}>
                    Overrides: {pdfPreview.overrides?.name ? `Name “${pdfPreview.overrides.name}”` : 'Name —'} •
                    {pdfPreview.overrides?.level ? ` Level ${pdfPreview.overrides.level}` : ' Level —'} •
                    {pdfPreview.overrides?.class_name ? ` Class ${pdfPreview.overrides.class_name}` : ' Class —'}
                  </div>
                ) : null}
              </div>
            ) : null}

            {/* Grouped features & detected spells */}
            {((Array.isArray(preview?.sheet?.classFeatures) && preview.sheet.classFeatures.length > 0) ||
              (Array.isArray(preview?.sheet?.racialFeatures) && preview.sheet.racialFeatures.length > 0) ||
              (Array.isArray(preview?.sheet?.otherFeatures) && preview.sheet.otherFeatures.length > 0) ||
              (Array.isArray(preview?.sheet?.spells) && preview.sheet.spells.length > 0)) ? (
              <>
                {(Array.isArray(preview?.sheet?.classFeatures) && preview.sheet.classFeatures.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
                    <div style={{ fontWeight: 750 }}>{preview?.class_name ? `${preview.class_name} Features` : 'Class Features'}</div>
                    <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>Click a feature to view more details.</div>
                    <div style={{ maxHeight: 220, overflowY: 'auto', display: 'grid', gap: 6 }}>
                      {preview.sheet.classFeatures.map((f: any, idx: number) => (
                        <button
                          key={`class-${idx}`}
                          type="button"
                          className="btn btn-ghost"
                          style={{ textAlign: 'left', padding: '8px 10px' }}
                          onClick={() => handleFeatureClick(typeof f === 'string' ? f : JSON.stringify(f, null, 2))}
                        >
                          <div style={{ whiteSpace: 'normal', overflow: 'hidden', textOverflow: 'ellipsis' }}>{shortPreview(String(f || ''))}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {(Array.isArray(preview?.sheet?.racialFeatures) && preview.sheet.racialFeatures.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
                    <div style={{ fontWeight: 750 }}>{preview?.sheet?.import?.extracted?.class_name ? `${preview.sheet.import.extracted.class_name} Species Traits` : 'Species Traits'}</div>
                    <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>Click a trait to view more details.</div>
                    <div style={{ maxHeight: 220, overflowY: 'auto', display: 'grid', gap: 6 }}>
                      {preview.sheet.racialFeatures.map((f: any, idx: number) => (
                        <button
                          key={`race-${idx}`}
                          type="button"
                          className="btn btn-ghost"
                          style={{ textAlign: 'left', padding: '8px 10px' }}
                          onClick={() => handleFeatureClick(typeof f === 'string' ? f : JSON.stringify(f, null, 2))}
                        >
                          <div style={{ whiteSpace: 'normal', overflow: 'hidden', textOverflow: 'ellipsis' }}>{shortPreview(String(f || ''))}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {(Array.isArray(preview?.sheet?.otherFeatures) && preview.sheet.otherFeatures.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
                    <div style={{ fontWeight: 750 }}>Other Features</div>
                    <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>Click a feature to view more details.</div>
                    <div style={{ maxHeight: 220, overflowY: 'auto', display: 'grid', gap: 6 }}>
                      {preview.sheet.otherFeatures.map((f: any, idx: number) => (
                        <button
                          key={`other-${idx}`}
                          type="button"
                          className="btn btn-ghost"
                          style={{ textAlign: 'left', padding: '8px 10px' }}
                          onClick={() => handleFeatureClick(typeof f === 'string' ? f : JSON.stringify(f, null, 2))}
                        >
                          <div style={{ whiteSpace: 'normal', overflow: 'hidden', textOverflow: 'ellipsis' }}>{shortPreview(String(f || ''))}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {(Array.isArray(preview?.sheet?.spells) && preview.sheet.spells.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
                    <div style={{ fontWeight: 750 }}>Detected spells</div>
                    <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>Spells extracted from the PDF (one per line).</div>
                    <div style={{ maxHeight: 220, overflowY: 'auto' }}>
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {preview.sheet.spells.map((s: any, idx: number) => (
                          <li key={`spell-${idx}`}>{String(s)}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ) : null}
              </>
            ) : null}

            {nameConflict ? (
              <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
                <div style={{ fontWeight: 750 }}>Name conflict</div>
                <div className="muted" style={{ fontSize: 13 }}>
                  Choose whether to overwrite the existing character or create a new one.
                </div>

                <div className="stack" style={{ gap: 8 }}>
                  <label className="row" style={{ gap: 10, userSelect: 'none' }}>
                    <input
                      type="radio"
                      name="import-conflict"
                      checked={reviewAction === 'create'}
                      onChange={() => setReviewAction('create')}
                      disabled={confirmBusy}
                    />
                    <span>Create new character</span>
                  </label>
                  <label className="row" style={{ gap: 10, userSelect: 'none' }}>
                    <input
                      type="radio"
                      name="import-conflict"
                      checked={reviewAction === 'overwrite'}
                      onChange={() => {
                        setReviewAction('overwrite')
                        setReviewOverwriteId(nameConflict.id)
                      }}
                      disabled={confirmBusy}
                    />
                    <span>
                      Overwrite <b>{nameConflict.name}</b> (L{nameConflict.level}{nameConflict.class_name ? ` ${nameConflict.class_name}` : ''})
                    </span>
                  </label>
                </div>
              </div>
            ) : null}

            <div className="row-wrap" style={{ justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" type="button" onClick={resetConfirmState} disabled={confirmBusy}>
                Cancel
              </button>
              <button className="btn" type="button" onClick={finalizeImport} disabled={confirmBusy}>
                {confirmBusy ? 'Importing…' : reviewAction === 'overwrite' ? 'Overwrite' : 'Import'}
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={featureOpen} title="Feature" onClose={() => setFeatureOpen(false)}>
        <div className="stack" style={{ gap: 8 }}>
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{featureText}</div>

          <div>
            <div className="muted" style={{ fontSize: 13 }}>Reference matches</div>
            {featureRefLoading ? (
              <div className="muted">Searching references…</div>
            ) : featureRefs && featureRefs.length > 0 ? (
              <ul style={{ margin: '6px 0 12px 18px' }}>
                {featureRefs.map((r: any, i: number) => (
                  <li key={`ref-${i}`} style={{ marginBottom: 8 }}>
                    <a href={`${API_BASE}/references/${r.source_id}/raw#page=${r.page}`} target="_blank" rel="noreferrer">
                      [{r.source_id} p{r.page}]
                    </a>{' '}
                    <span className="muted" style={{ fontSize: 13 }}> — {r.snippet}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="muted">No matches found.</div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" type="button" onClick={() => setFeatureOpen(false)}>Close</button>
          </div>
        </div>
      </Modal>

      <PageHeader
        title="Import Character"
        subtitle="Import a character from JSON (paste or upload), or store a D&D Beyond link as a reference. We keep your raw data so future parsing improvements can enrich sheets without losing information."
        actions={
          <div className="row-wrap" style={{ justifyContent: 'flex-end', gap: 8 }}>
            {activeSessionId ? (
              <button className="btn btn-secondary" type="button" disabled={busy} onClick={onGoToGameplay}>
                Back to Play
              </button>
            ) : null}
            <button className="btn btn-quiet" type="button" disabled={busy} onClick={onDone}>
              Done
            </button>
          </div>
        }
      />

      {message ? (
        <div className={`inline-alert ${messageKind === 'error' ? 'inline-alert-error' : ''}`} role={messageKind === 'error' ? 'alert' : undefined}>
          {message}
        </div>
      ) : null}

      {backendChecked && (backendCheckError || (backendPaths && (mode === 'pdf' ? !backendCaps.importPdf : false))) ? (
        <div className="inline-alert inline-alert-error" role="alert">
          {backendCheckError ? (
            <>
              Cannot reach backend at <b>{API_BASE}</b>. Imports may fail until the backend is running.
            </>
          ) : (
            <>
              Your backend at <b>{API_BASE}</b> does not advertise <b>/characters/import/pdf/preview</b>. PDF uploads will fail.
              Restart the backend (recommended: run <b>start-app.ps1</b> again) and refresh.
            </>
          )}
        </div>
      ) : null}

      <div className="card card-pad stack" style={{ maxWidth: 980 }}>
        <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="stack" style={{ gap: 6 }}>
            <div className="muted">1) Choose import method</div>
            <div className="segmented" role="group" aria-label="Import method">
              <button type="button" aria-pressed={mode === 'paste'} onClick={() => setMode('paste')} disabled={busy}>
                Paste JSON
              </button>
              <button type="button" aria-pressed={mode === 'file'} onClick={() => setMode('file')} disabled={busy}>
                Upload JSON
              </button>
              <button type="button" aria-pressed={mode === 'pdf'} onClick={() => setMode('pdf')} disabled={busy}>
                Upload DDB PDF
              </button>
              <button type="button" aria-pressed={mode === 'ddb-link'} onClick={() => setMode('ddb-link')} disabled={busy}>
                DDB link
              </button>
            </div>
          </div>

          <label className="row" style={{ gap: 8, userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={autoAssignToSession}
              onChange={(e) => setAutoAssignToSession(e.target.checked)}
              disabled={!activeSessionId}
            />
            <span className="muted">Auto-select for active session</span>
          </label>
        </div>

        <div className="stack" style={{ gap: 6 }}>
          <label className="muted">D&amp;D Beyond character link (optional)</label>
          <input
            className="input"
            placeholder="https://www.dndbeyond.com/characters/123456"
            value={ddbUrl}
            onChange={(e) => setDdbUrl(e.target.value)}
            disabled={busy}
          />
        </div>

        {mode === 'paste' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="muted">2) Paste JSON export</div>
            <textarea
              className="input input-mono"
              placeholder='{"name":"Minsc","level":3,"class_name":"Ranger"}'
              value={rawJson}
              onChange={(e) => setRawJson(e.target.value)}
              style={{ minHeight: 190 }}
              disabled={busy}
            />

            <div className="row-wrap">
              <button
                className="btn"
                disabled={busy}
                onClick={async () => {
                  await beginJsonPreview(rawJson, 'paste')
                }}
              >
                Review Import
              </button>
              <button
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => {
                  setRawJson('')
                  setMessage(null)
                }}
              >
                Clear
              </button>
            </div>
          </div>
        ) : null}

        {mode === 'file' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="muted">2) Upload JSON file</div>
            <div className="row-wrap" style={{ alignItems: 'center' }}>
              <input
                className="input"
                type="file"
                accept="application/json,.json"
                onChange={(e) => {
                  const f = e.target.files && e.target.files[0] ? e.target.files[0] : null
                  setFile(f)
                }}
                disabled={busy}
                style={{ maxWidth: 420 }}
              />
              <button
                className="btn"
                disabled={busy}
                onClick={async () => {
                  if (!file) {
                    showMessage('error', 'Choose a JSON file.')
                    return
                  }
                  setBusy(true)
                  setMessage(null)
                  try {
                    const text = await file.text()
                    await beginJsonPreview(text, 'file')
                  } catch {
                    showMessage('error', 'Unable to read file.')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Upload & Review
              </button>
            </div>
          </div>
        ) : null}

        {mode === 'pdf' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="muted">2) Upload D&amp;D Beyond PDF character sheet</div>
            <div className="inline-alert">
              We only parse files you upload. No D&amp;D Beyond scraping. PDF parsing is best-effort; some DDB PDFs don’t contain extractable text. Use overrides if needed.
            </div>

            <div className="card card-pad stack" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div style={{ fontWeight: 750 }}>How to get the PDF from D&amp;D Beyond</div>
              <div className="muted" style={{ fontSize: 13 }}>
                On your D&amp;D Beyond character sheet, use the print/export option to download a PDF, then upload it here.
                Fillable PDFs work great because we can read the field values directly.
              </div>
            </div>

            <div className="row-wrap" style={{ gap: 10 }}>
              <div className="stack" style={{ gap: 6, minWidth: 240 }}>
                <label className="muted">Override name (optional)</label>
                <input
                  className="input"
                  placeholder="Spaceman Wil"
                  value={pdfName}
                  onChange={(e) => setPdfName(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="stack" style={{ gap: 6, minWidth: 140 }}>
                <label className="muted">Override level (optional)</label>
                <input
                  className="input"
                  placeholder="3"
                  inputMode="numeric"
                  value={pdfLevel}
                  onChange={(e) => setPdfLevel(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="stack" style={{ gap: 6, minWidth: 220 }}>
                <label className="muted">Override class (optional)</label>
                <input
                  className="input"
                  placeholder="Ranger"
                  value={pdfClassName}
                  onChange={(e) => setPdfClassName(e.target.value)}
                  disabled={busy}
                />
              </div>
            </div>

            <div className="row-wrap" style={{ alignItems: 'center' }}>
              <input
                className="input"
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => {
                  const f = e.target.files && e.target.files[0] ? e.target.files[0] : null
                  setFile(f)
                }}
                disabled={busy}
                style={{ maxWidth: 420 }}
              />
              <button
                className="btn"
                disabled={busy || (backendChecked && !backendCheckError && !backendCaps.importPdf)}
                onClick={async () => {
                  await beginPdfPreview()
                }}
              >
                Upload &amp; Review
              </button>
            </div>
          </div>
        ) : null}

        {mode === 'ddb-link' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="muted">2) Store link as reference</div>
            <div className="inline-alert">
              This creates a placeholder character you can “View” later (it stores the URL). We do not scrape D&amp;D Beyond.
            </div>
            <div className="row-wrap">
              <button
                className="btn"
                disabled={busy}
                onClick={async () => {
                  if (!ddbUrl.trim()) {
                    showMessage('error', 'Paste a D&D Beyond character link first.')
                    return
                  }
                  setBusy(true)
                  setMessage(null)
                  try {
                    const res = await apiFetch('/characters/import/link', {
                      method: 'POST',
                      body: JSON.stringify({ ddb_url: ddbUrl.trim() })
                    })
                    if (res.ok) {
                      const data = await res.json().catch(() => ({}))
                      const createdId = typeof data?.character?.id === 'number' ? data.character.id : null
                      await handleSaved(createdId, 'created')
                    } else {
                      const err = await res.json().catch(() => ({}))
                      showMessage('error', err?.detail || 'Failed to create character from link')
                    }
                  } catch (e) {
                    showMessage('error', 'Network error')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Create Placeholder
              </button>
            </div>
          </div>
        ) : null}

        <div className="muted" style={{ fontSize: 12 }}>
          Tip: Select a session in Gameplay first if you want one-click auto-select.
        </div>
      </div>
    </section>
  )
}
