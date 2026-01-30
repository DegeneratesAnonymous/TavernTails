import React, { useState } from 'react'

import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'

type Props = {
  activeSessionId: string | null
  onRefreshCharacters: () => Promise<void>
  onAssignCharacterToSession: (characterId: number | null) => Promise<void>
  onSetActiveCharacterId: (characterId: number | null) => void
  onDone: () => void
  onGoToGameplay: () => void
}

export default function ImportCharacterView({
  activeSessionId,
  onRefreshCharacters,
  onAssignCharacterToSession,
  onSetActiveCharacterId,
  onDone,
  onGoToGameplay,
}: Props) {
  const [mode, setMode] = useState<'ddb-link' | 'paste' | 'file' | 'pdf'>('paste')
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

  const showMessage = (kind: 'ok' | 'error', text: string) => {
    setMessageKind(kind)
    setMessage(text)
  }

  const handleCreated = async (createdId: number | null) => {
    setRawJson('')
    setFile(null)
    setPdfName('')
    setPdfLevel('')
    setPdfClassName('')
    await onRefreshCharacters()

    if (activeSessionId && createdId !== null && autoAssignToSession) {
      onSetActiveCharacterId(createdId)
      await onAssignCharacterToSession(createdId)
      showMessage('ok', 'Character created and assigned to active session.')
      onGoToGameplay()
      return
    }

    showMessage('ok', 'Character created.')
    onDone()
  }

  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="Import Character"
        subtitle="Import a character from JSON (paste or upload), or store a D&D Beyond link as a reference. We keep your raw data so future parsing improvements can enrich sheets without losing information."
        actions={
          <button className="btn btn-quiet" type="button" disabled={busy} onClick={onDone}>
            Done
          </button>
        }
      />

      {message ? (
        <div className={`inline-alert ${messageKind === 'error' ? 'inline-alert-error' : ''}`} role={messageKind === 'error' ? 'alert' : undefined}>
          {message}
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
                Upload PDF
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
                  if (!rawJson.trim()) {
                    showMessage('error', 'Paste JSON to import.')
                    return
                  }
                  setBusy(true)
                  setMessage(null)
                  try {
                    const res = await apiFetch('/characters/import', {
                      method: 'POST',
                      body: JSON.stringify({ raw_json: rawJson, ddb_url: ddbUrl.trim() || null, source: 'paste' })
                    })
                    if (res.ok) {
                      const data = await res.json().catch(() => ({}))
                      const createdId = typeof data?.character?.id === 'number' ? data.character.id : null
                      await handleCreated(createdId)
                    } else {
                      const err = await res.json().catch(() => ({}))
                      showMessage('error', err?.detail || 'Failed to import character')
                    }
                  } catch (e) {
                    showMessage('error', 'Network error')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Import JSON
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
                    const form = new FormData()
                    form.append('file', file)
                    const qs = new URLSearchParams()
                    qs.set('source', 'file')
                    if (ddbUrl.trim()) qs.set('ddb_url', ddbUrl.trim())
                    const res = await apiFetch(`/characters/import/file?${qs.toString()}`, {
                      method: 'POST',
                      body: form,
                      headers: {}
                    })
                    if (res.ok) {
                      const data = await res.json().catch(() => ({}))
                      const createdId = typeof data?.character?.id === 'number' ? data.character.id : null
                      await handleCreated(createdId)
                    } else {
                      const err = await res.json().catch(() => ({}))
                      showMessage('error', err?.detail || 'Failed to import character')
                    }
                  } catch (e) {
                    showMessage('error', 'Network error')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Upload & Import
              </button>
            </div>
          </div>
        ) : null}

        {mode === 'pdf' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="muted">2) Upload PDF character sheet</div>
            <div className="inline-alert">
              We only parse files you upload. No D&amp;D Beyond scraping. PDF parsing is best-effort; some DDB PDFs don’t contain extractable text. Use overrides if needed.
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
                disabled={busy}
                onClick={async () => {
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
                    const res = await apiFetch(`/characters/import/pdf?${qs.toString()}`, {
                      method: 'POST',
                      body: form,
                      headers: {}
                    })
                    if (res.ok) {
                      const data = await res.json().catch(() => ({}))
                      const createdId = typeof data?.character?.id === 'number' ? data.character.id : null
                      await handleCreated(createdId)
                    } else {
                      const err = await res.json().catch(() => ({}))
                      showMessage('error', err?.detail || 'Failed to import character')
                    }
                  } catch (e) {
                    showMessage('error', 'Network error')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Upload &amp; Import
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
                      await handleCreated(createdId)
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
