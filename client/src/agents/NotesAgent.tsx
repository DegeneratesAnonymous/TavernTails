import React, { useState } from 'react'
import { apiFetch } from '../api'

type NotesResponse = {
  session_id: string
  notes_logged: number
  recap: string
}

const NotesAgent: React.FC = () => {
  const [sessionId, setSessionId] = useState('')
  const [notesInput, setNotesInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<NotesResponse | null>(null)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const notes = notesInput
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      const res = await apiFetch('/notes/log', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId.trim(), notes }),
      })
      if (!res.ok) {
        throw new Error(`Notes request failed (${res.status})`)
      }
      const data: NotesResponse = await res.json()
      setResponse(data)
    } catch (err: any) {
      setError(err?.message ?? 'Failed to log notes')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="agent-card">
      <h3>Notes Agent</h3>
      <form onSubmit={handleSubmit} className="agent-form">
        <label>
          Session ID
          <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} required />
        </label>
        <label>
          Notes (one per line)
          <textarea value={notesInput} onChange={(e) => setNotesInput(e.target.value)} rows={5} required />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Logging…' : 'Log Notes'}
        </button>
      </form>
      {error && <p className="agent-error">{error}</p>}
      {response && (
        <div className="agent-result">
          <p>
            Logged {response.notes_logged} notes for <strong>{response.session_id}</strong>
          </p>
          <p>
            Latest recap: <em>{response.recap}</em>
          </p>
        </div>
      )}
    </div>
  )
}

export default NotesAgent
