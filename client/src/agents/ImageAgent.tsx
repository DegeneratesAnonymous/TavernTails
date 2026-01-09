import React, { useState } from 'react'
import { apiFetch } from '../api'

type ImageResponse = {
  prompt: string
  style: string
  image_url: string
  guidance: string
}

const ImageAgent: React.FC = () => {
  const [prompt, setPrompt] = useState('')
  const [style, setStyle] = useState('realistic')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<ImageResponse | null>(null)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const res = await apiFetch('/image/generate', {
        method: 'POST',
        body: JSON.stringify({ prompt: prompt.trim(), style }),
      })
      if (!res.ok) {
        throw new Error(`Image request failed (${res.status})`)
      }
      const data: ImageResponse = await res.json()
      setResponse(data)
    } catch (err: any) {
      setError(err?.message ?? 'Failed to contact image agent')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="agent-card">
      <h3>Image Agent</h3>
      <form onSubmit={handleSubmit} className="agent-form">
        <label>
          Prompt
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} required />
        </label>
        <label>
          Style
          <select value={style} onChange={(e) => setStyle(e.target.value)}>
            <option value="realistic">Realistic</option>
            <option value="painterly">Painterly</option>
            <option value="comic">Comic Book</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Generating…' : 'Generate Placeholder'}
        </button>
      </form>
      {error && <p className="agent-error">{error}</p>}
      {response && (
        <div className="agent-result">
          <p>{response.guidance}</p>
          <img
            src={response.image_url}
            alt={response.prompt}
            style={{ maxWidth: '100%', border: '1px solid #ccc', marginTop: '0.5rem' }}
          />
          <p>
            Prompt echoed as <strong>{response.prompt}</strong> in {response.style} style.
          </p>
        </div>
      )}
    </div>
  )
}

export default ImageAgent
