import React, { useEffect, useMemo, useState } from 'react'

import { apiFetch, API_BASE, buildApiUrl } from '../../api'
import PageHeader from '../ui/PageHeader'
import Modal from '../ui/Modal'

// Known TTRPG systems available for the game-system selector.
// Listing these names in a UI dropdown is purely referential – the same as
// any file-format selector – and does not reproduce copyrighted rules content.
const KNOWN_TTRPG_SYSTEMS: { name: string; publisher: string }[] = [
  { name: 'D&D 5e', publisher: 'Wizards of the Coast' },
  { name: 'Pathfinder 2e', publisher: 'Paizo' },
  { name: 'Pathfinder 1e', publisher: 'Paizo' },
  { name: 'Starfinder', publisher: 'Paizo' },
  { name: 'Call of Cthulhu', publisher: 'Chaosium' },
  { name: 'Star Trek Adventures', publisher: 'Modiphius' },
  { name: 'Shadow of the Demon Lord', publisher: 'Schwalb Entertainment' },
  { name: 'Warhammer Fantasy Roleplay', publisher: 'Cubicle 7' },
  { name: 'Alien RPG', publisher: 'Free League Publishing' },
  { name: 'Shadowrun', publisher: 'Catalyst Game Labs' },
]

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
  initialMode?: 'pdf' | 'beyond20'
  notificationsPending?: boolean
  onNotificationsClick?: () => void
}

export default function ImportCharacterView({
  activeSessionId,
  onRefreshCharacters,
  onAssignCharacterToSession,
  onSetActiveCharacterId,
  onDone,
  onGoToGameplay,
  initialMode,
  notificationsPending,
  onNotificationsClick,
}: Props) {
  const [mode, setMode] = useState<'pdf' | 'beyond20'>(initialMode || 'pdf')
  const [file, setFile] = useState<File | null>(null)
  const [pdfName, setPdfName] = useState('')
  const [pdfLevel, setPdfLevel] = useState('')
  const [pdfClassName, setPdfClassName] = useState('')
  const [pdfSystem, setPdfSystem] = useState('')
  const [availableSystems, setAvailableSystems] = useState<{ name: string; publisher: string }[]>(KNOWN_TTRPG_SYSTEMS)
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
    }
  }, [backendPaths])

  function featureLabel(f: any): string {
    if (typeof f === 'string') return f
    if (f && typeof f === 'object') {
      const name = String(f.name || '').trim()
      const src = f.source ? String(f.source).trim() : ''
      return src ? `${name} — ${src}` : name
    }
    return String(f || '')
  }

  function featureDetailText(f: any): string {
    if (typeof f === 'string') return f
    if (f && typeof f === 'object') {
      const name = String(f.name || '').trim()
      const src = f.source ? ` (${f.source})` : ''
      const desc = f.description ? `\n\n${f.description}` : ''
      return `${name}${src}${desc}`
    }
    return String(f || '')
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
    const detectedSystem = (sheet?.detected_system && typeof sheet.detected_system === 'object') ? sheet.detected_system : null
    const sheetType = typeof sheet?.sheet_type === 'string' ? sheet.sheet_type : 'character'
    const heritage = typeof sheet?.heritage === 'string' ? sheet.heritage : null
    const classDc = typeof sheet?.class_dc === 'number' ? sheet.class_dc : null
    const focusPoints = (sheet?.focus_points && typeof sheet.focus_points === 'object') ? sheet.focus_points as { max?: number; current?: number } : null
    const staAttributes = (sheet?.attributes && typeof sheet.attributes === 'object') ? sheet.attributes as Record<string, number> : null
    const staDisciplines = (sheet?.disciplines && typeof sheet.disciplines === 'object') ? sheet.disciplines as Record<string, number> : null

    return {
      stats,
      hp,
      ac,
      featuresCount: features.length,
      widgetCount,
      rawTextLen,
      extracted,
      overrides,
      detectedSystem,
      sheetType,
      heritage,
      classDc,
      focusPoints,
      staAttributes,
      staDisciplines,
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

  useEffect(() => {
    let canceled = false
    async function fetchSystems() {
      try {
        const res = await apiFetch('/characters/import/systems')
        if (!res.ok) return
        const data = await res.json().catch(() => null)
        const list = Array.isArray(data?.systems) ? data.systems : null
        if (list && list.length > 0 && !canceled) {
          setAvailableSystems(list)
        }
      } catch {
        // Non-fatal: fall back to KNOWN_TTRPG_SYSTEMS already set as default
      }
    }
    fetchSystems()
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
      if (pdfSystem.trim()) form.append('game_system', pdfSystem.trim())
      const qs = new URLSearchParams()
      qs.set('source', 'pdf')
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

            <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
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

            <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
              <div style={{ fontWeight: 750 }}>What to include</div>

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
              <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
                <div style={{ fontWeight: 750 }}>PDF extraction summary</div>

                {pdfPreview.sheetType === 'ship' ? (
                  <div className="inline-alert" style={{ background: 'rgba(251,191,36,0.15)', borderColor: '#fbbf24', color: '#fbbf24', fontSize: 13 }}>
                    ⚓ Ship/Vehicle Sheet detected — This PDF appears to be a ship or vehicle sheet, not a character sheet. You can still import it; consider also adding it as a campaign document.
                  </div>
                ) : null}

                {pdfPreview.detectedSystem && pdfPreview.detectedSystem.system_name && pdfPreview.detectedSystem.system_name !== 'Unknown' ? (
                  <div className="muted" style={{ fontSize: 12 }}>
                    {Array.isArray(pdfPreview.detectedSystem.evidence) && pdfPreview.detectedSystem.evidence[0] === 'user-selected'
                      ? <>Game system: <strong style={{ color: 'var(--tt-accent, #c084fc)' }}>{pdfPreview.detectedSystem.system_name}</strong>{pdfPreview.detectedSystem.publisher ? ` (${pdfPreview.detectedSystem.publisher})` : ''} — <em>manually selected</em></>
                      : <>Detected system: <strong style={{ color: 'var(--tt-accent, #c084fc)' }}>{pdfPreview.detectedSystem.system_name}</strong>{pdfPreview.detectedSystem.publisher ? ` (${pdfPreview.detectedSystem.publisher})` : ''}{typeof pdfPreview.detectedSystem.confidence === 'number' ? ` — ${Math.round(pdfPreview.detectedSystem.confidence * 100)}% confidence` : ''}</>
                    }
                  </div>
                ) : null}

                <div className="row-wrap" style={{ gap: 14 }}>
                  {pdfPreview.staAttributes ? (
                    <>
                      <div className="stack" style={{ gap: 6, minWidth: 200 }}>
                        <div className="muted">Attributes</div>
                        <div className="row-wrap" style={{ gap: 8 }}>
                          {(['control', 'daring', 'fitness', 'insight', 'presence', 'reason'] as const).map((k) => (
                            <div key={k} style={{ padding: '5px 8px', background: 'rgba(200,148,26,0.1)', border: '1px solid rgba(200,148,26,0.2)', borderRadius: 5, fontFamily: 'monospace', fontSize: 13 }}>
                              <strong>{k.slice(0, 3).charAt(0).toUpperCase() + k.slice(1, 3)}:</strong> {typeof (pdfPreview.staAttributes as any)[k] === 'number' ? (pdfPreview.staAttributes as any)[k] : '—'}
                            </div>
                          ))}
                        </div>
                      </div>
                      {pdfPreview.staDisciplines ? (
                        <div className="stack" style={{ gap: 6, minWidth: 200 }}>
                          <div className="muted">Disciplines</div>
                          <div className="row-wrap" style={{ gap: 8 }}>
                            {(['command', 'conn', 'engineering', 'medicine', 'science', 'security'] as const).map((k) => (
                              <div key={k} style={{ padding: '5px 8px', background: 'rgba(200,148,26,0.1)', border: '1px solid rgba(200,148,26,0.2)', borderRadius: 5, fontFamily: 'monospace', fontSize: 13 }}>
                                <strong>{k.slice(0, 3).charAt(0).toUpperCase() + k.slice(1, 3)}:</strong> {typeof (pdfPreview.staDisciplines as any)[k] === 'number' ? (pdfPreview.staDisciplines as any)[k] : '—'}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className="stack" style={{ gap: 6, minWidth: 200 }}>
                      <div className="muted">Ability scores</div>
                      <div className="row-wrap" style={{ gap: 8 }}>
                        {(['str', 'dex', 'con', 'int', 'wis', 'cha'] as const).map((k) => (
                          <div key={k} style={{ padding: '5px 8px', background: 'rgba(200,148,26,0.1)', border: '1px solid rgba(200,148,26,0.2)', borderRadius: 5, fontFamily: 'monospace', fontSize: 13 }}>
                            <strong style={{ color: 'var(--accent, #c8941a)' }}>{k.toUpperCase()}</strong> {typeof (pdfPreview.stats as any)[k] === 'number' ? (pdfPreview.stats as any)[k] : '—'}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="stack" style={{ gap: 6, minWidth: 180 }}>
                    <div className="muted">Combat</div>
                    <div><strong>AC:</strong> {pdfPreview.ac ?? '—'}</div>
                    <div><strong>HP:</strong> {pdfPreview.hp?.current ?? '—'} / {pdfPreview.hp?.max ?? '—'}</div>
                    <div><strong>Temp:</strong> {pdfPreview.hp?.temp ?? '—'}</div>
                    {pdfPreview.classDc != null ? <div><strong>Class DC:</strong> {pdfPreview.classDc}</div> : null}
                    {pdfPreview.focusPoints != null ? (
                      <div><strong>Focus Points:</strong> {pdfPreview.focusPoints.current ?? '—'} / {pdfPreview.focusPoints.max ?? '—'}</div>
                    ) : null}
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
                    Extracted: {pdfPreview.extracted?.name ? `Name "${pdfPreview.extracted.name}"` : 'Name —'} •
                    {pdfPreview.extracted?.level ? ` Level ${pdfPreview.extracted.level}` : ' Level —'} •
                    {pdfPreview.extracted?.class_name ? ` Class ${pdfPreview.extracted.class_name}` : ' Class —'}
                  </div>
                ) : null}

                {(pdfPreview.overrides?.name || pdfPreview.overrides?.level || pdfPreview.overrides?.class_name) ? (
                  <div className="muted" style={{ fontSize: 12 }}>
                    Overrides: {pdfPreview.overrides?.name ? `Name "${pdfPreview.overrides.name}"` : 'Name —'} •
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
                  <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
                    <div style={{ fontWeight: 700, fontSize: 10, color: 'var(--accent, #c8941a)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{preview?.class_name ? `${preview.class_name} Features` : 'Class Features'}</div>
                    <div style={{ display: 'grid', gap: 4 }}>
                      {preview.sheet.classFeatures.map((f: any, idx: number) => (
                        <button
                          key={`class-${idx}`}
                          type="button"
                          onClick={() => handleFeatureClick(featureDetailText(f))}
                          style={{ textAlign: 'left', padding: '6px 10px', background: 'rgba(200,148,26,0.06)', border: '1px solid rgba(200,148,26,0.15)', borderRadius: 5, cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
                        >
                          <span style={{ fontWeight: 600, fontSize: 12 }}>{featureLabel(f)}</span>
                          {(f && typeof f === 'object' && f.description) ? <span style={{ fontSize: 10, opacity: 0.5, flexShrink: 0 }}>▼</span> : null}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {(Array.isArray(preview?.sheet?.racialFeatures) && preview.sheet.racialFeatures.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
                    <div style={{ fontWeight: 700, fontSize: 10, color: 'var(--accent, #c8941a)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Species Traits</div>
                    <div style={{ display: 'grid', gap: 4 }}>
                      {preview.sheet.racialFeatures.map((f: any, idx: number) => (
                        <button
                          key={`race-${idx}`}
                          type="button"
                          onClick={() => handleFeatureClick(featureDetailText(f))}
                          style={{ textAlign: 'left', padding: '6px 10px', background: 'rgba(200,148,26,0.06)', border: '1px solid rgba(200,148,26,0.15)', borderRadius: 5, cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
                        >
                          <span style={{ fontWeight: 600, fontSize: 12 }}>{featureLabel(f)}</span>
                          {(f && typeof f === 'object' && f.description) ? <span style={{ fontSize: 10, opacity: 0.5, flexShrink: 0 }}>▼</span> : null}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {(Array.isArray(preview?.sheet?.otherFeatures) && preview.sheet.otherFeatures.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
                    <div style={{ fontWeight: 700, fontSize: 10, color: 'var(--accent, #c8941a)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Other Features</div>
                    <div style={{ maxHeight: 260, overflowY: 'auto', display: 'grid', gap: 4 }}>
                      {preview.sheet.otherFeatures.map((f: any, idx: number) => (
                        <button
                          key={`other-${idx}`}
                          type="button"
                          onClick={() => handleFeatureClick(featureDetailText(f))}
                          style={{ textAlign: 'left', padding: '6px 10px', background: 'rgba(200,148,26,0.06)', border: '1px solid rgba(200,148,26,0.15)', borderRadius: 5, cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
                        >
                          <span style={{ fontWeight: 600, fontSize: 12 }}>{featureLabel(f)}</span>
                          {(f && typeof f === 'object' && f.description) ? <span style={{ fontSize: 10, opacity: 0.5, flexShrink: 0 }}>▼</span> : null}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}


                {(Array.isArray(preview?.sheet?.spellbook) && preview.sheet.spellbook.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
                    <div style={{ fontWeight: 750 }}>Detected spellbook</div>
                    <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
                      Spells parsed from the PDF table (name + columns).
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                        <thead>
                          <tr style={{ textAlign: 'left' }}>
                            <th style={{ padding: '6px 8px' }}>Name</th>
                            <th style={{ padding: '6px 8px' }}>Source</th>
                            <th style={{ padding: '6px 8px' }}>Save/Atk</th>
                            <th style={{ padding: '6px 8px' }}>Time</th>
                            <th style={{ padding: '6px 8px' }}>Range</th>
                            <th style={{ padding: '6px 8px' }}>Comp</th>
                            <th style={{ padding: '6px 8px' }}>Duration</th>
                            <th style={{ padding: '6px 8px' }}>Page</th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.sheet.spellbook.slice(0, 80).map((spell: any, idx: number) => (
                            <tr key={`spellbook-${idx}`} style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                              <td style={{ padding: '6px 8px', fontWeight: 600 }}>{String(spell?.name || '')}</td>
                              <td style={{ padding: '6px 8px' }}>{String(spell?.source || '')}</td>
                              <td style={{ padding: '6px 8px' }}>{String(spell?.save_hit || '')}</td>
                              <td style={{ padding: '6px 8px' }}>{String(spell?.time || '')}</td>
                              <td style={{ padding: '6px 8px' }}>{String(spell?.range || '')}</td>
                              <td style={{ padding: '6px 8px' }}>{String(spell?.components || '')}</td>
                              <td style={{ padding: '6px 8px' }}>{String(spell?.duration || '')}</td>
                              <td style={{ padding: '6px 8px' }}>{String(spell?.page || '')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (Array.isArray(preview?.sheet?.spells) && preview.sheet.spells.length > 0) ? (
                  <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
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
              <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
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
        subtitle="Import a character from a D&D Beyond PDF export or connect the Beyond 20 browser extension."
        actions={
          <div className="row-wrap" style={{ justifyContent: 'flex-end', gap: 8 }}>
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
              <button type="button" aria-pressed={mode === 'pdf'} onClick={() => setMode('pdf')} disabled={busy}>
                Upload PDF
              </button>
              <button type="button" aria-pressed={mode === 'beyond20'} onClick={() => setMode('beyond20')} disabled={busy}>
                Beyond 20
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

        {mode === 'beyond20' ? (
          <div className="stack" style={{ gap: 12 }}>
            <div className="inline-alert">
              Beyond 20 is a free browser extension that reads your D&amp;D Beyond rolls and sends them to TavernTails. The only install required is the Beyond 20 extension itself — no additional software needed.
            </div>
            <div className="card card-pad stack" style={{ background: 'var(--muted-surface)', gap: 8 }}>
              <div style={{ fontWeight: 750 }}>Step 1 — Install the Beyond 20 extension</div>
              <div className="muted" style={{ fontSize: 13 }}>
                Install Beyond 20 from the Chrome Web Store or Firefox Add-ons. Once installed, it will automatically detect rolls on your D&amp;D Beyond character sheet.
              </div>
              <div className="row-wrap" style={{ gap: 8 }}>
                <a
                  className="btn btn-secondary"
                  href="https://chrome.google.com/webstore/detail/beyond-20/gnblbpbepfbfmoobegdogkglpbhcjofh"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Chrome Web Store
                </a>
                <a
                  className="btn btn-secondary"
                  href="https://addons.mozilla.org/en-US/firefox/addon/beyond-20/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Firefox Add-ons
                </a>
              </div>
            </div>
            <div className="card card-pad stack" style={{ background: 'var(--muted-surface)', gap: 8 }}>
              <div style={{ fontWeight: 750 }}>Step 2 — Roll on D&amp;D Beyond</div>
              <div className="muted" style={{ fontSize: 13 }}>
                With a session open in TavernTails, click any roll button on your D&amp;D Beyond character sheet. Beyond 20 will relay the result directly into your TavernTails session chat.
              </div>
            </div>
          </div>
        ) : null}

        {mode === 'pdf' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="muted">2) Upload D&amp;D Beyond PDF character sheet</div>
            <div className="inline-alert">
              We only parse files you upload. No D&amp;D Beyond scraping. PDF parsing is best-effort; some DDB PDFs don’t contain extractable text. Use overrides if needed.
            </div>

            <div className="card card-pad stack" style={{ background: 'var(--muted-surface)' }}>
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
              <div className="stack" style={{ gap: 6, minWidth: 220 }}>
                <label className="muted">Game system (optional)</label>
                <select
                  className="input"
                  value={pdfSystem}
                  onChange={(e) => setPdfSystem(e.target.value)}
                  disabled={busy}
                >
                  <option value="">Auto-detect</option>
                  {availableSystems.map((sys) => (
                    <option key={sys.name} value={sys.name}>
                      {sys.name} — {sys.publisher}
                    </option>
                  ))}
                </select>
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

        <div className="muted" style={{ fontSize: 12 }}>
          Tip: Select a session in Gameplay first if you want one-click auto-select.
        </div>
      </div>
    </section>
  )
}
