import React, { useState } from 'react'
import { apiFetch } from '../api'

type StoryboardResponse = {
  storyboard: {
    scene: string
    choices: string[]
    unresolved: string[]
    completed: string[]
  }
  next_focus: string
}

const StoryboardAgent: React.FC = () => {
  const [scene, setScene] = useState('')
  const [choicesInput, setChoicesInput] = useState('')
  const [unresolvedInput, setUnresolvedInput] = useState('')
  const [completedInput, setCompletedInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<StoryboardResponse | null>(null)

  const parseList = (value: string) =>
    value
      .split('\n')
      .map((v) => v.trim())
      .filter(Boolean)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const payload = {
        scene: scene.trim(),
        choices: parseList(choicesInput),
        unresolved: parseList(unresolvedInput),
        completed: parseList(completedInput),
      }
      const res = await apiFetch('/storyboard/update', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        throw new Error(`Storyboard request failed (${res.status})`)
      }
      const data: StoryboardResponse = await res.json()
      setResponse(data)
    } catch (err: any) {
      setError(err?.message ?? 'Failed to contact storyboard agent')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="agent-card">
      <h3>Storyboard Agent</h3>
      <form onSubmit={handleSubmit} className="agent-form">
        <label>
          Scene summary
          <textarea value={scene} onChange={(e) => setScene(e.target.value)} rows={4} required />
        </label>
        <label>
          Branching choices (one per line)
          <textarea value={choicesInput} onChange={(e) => setChoicesInput(e.target.value)} rows={3} />
        </label>
        <label>
          Unresolved hooks (one per line)
          <textarea value={unresolvedInput} onChange={(e) => setUnresolvedInput(e.target.value)} rows={3} />
        </label>
        <label>
          Completed beats (one per line)
          <textarea value={completedInput} onChange={(e) => setCompletedInput(e.target.value)} rows={2} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Updating…' : 'Update Storyboard'}
        </button>
      </form>
      {error && <p className="agent-error">{error}</p>}
      {response && (
        <div className="agent-result">
          <h4>Next Focus</h4>
          <p>{response.next_focus}</p>
          <h4>Storyboard State</h4>
          <pre>{JSON.stringify(response.storyboard, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

export default StoryboardAgent
