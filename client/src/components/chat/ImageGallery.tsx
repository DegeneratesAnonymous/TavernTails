import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../api'

type ImageEntry = {
  id: string
  prompt: string
  style: string
  image_url: string
  generated_at: string
  cached: boolean
}

type Props = {
  sessionId: string | null | undefined
  /** When true the panel is visible and will load images. */
  visible?: boolean
}

export default function ImageGallery({ sessionId, visible = true }: Props) {
  const [images, setImages] = useState<ImageEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [style, setStyle] = useState('realistic')

  const load = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch(`/image/gallery/${sessionId}`)
      if (!res.ok) throw new Error('Could not load image gallery.')
      const data = await res.json()
      setImages(data.images || [])
    } catch (err: any) {
      setError(err?.message || 'Gallery load failed.')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    if (visible) load()
  }, [visible, load])

  async function handleGenerate() {
    if (!prompt.trim() || !sessionId) return
    setGenerating(true)
    setError(null)
    try {
      const res = await apiFetch('/image/generate', {
        method: 'POST',
        body: JSON.stringify({ prompt: prompt.trim(), style, session_id: sessionId }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || 'Generation failed.')
      }
      const entry: ImageEntry = await res.json()
      setImages(prev => {
        if (prev.some(img => img.id === entry.id)) return prev
        return [entry, ...prev]
      })
      setPrompt('')
    } catch (err: any) {
      setError(err?.message || 'Could not generate image.')
    } finally {
      setGenerating(false)
    }
  }

  if (!sessionId) {
    return (
      <div className="image-gallery-empty">Start or load a session to use the image gallery.</div>
    )
  }

  return (
    <div className="image-gallery">
      <div className="image-gallery-composer">
        <input
          className="input image-gallery-prompt"
          type="text"
          placeholder="Describe the scene…"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleGenerate() }}
          disabled={generating}
        />
        <select
          className="image-gallery-style"
          value={style}
          onChange={e => setStyle(e.target.value)}
          disabled={generating}
          aria-label="Art style"
        >
          <option value="realistic">Realistic</option>
          <option value="comic">Comic</option>
          <option value="watercolour">Watercolour</option>
          <option value="sketch">Sketch</option>
          <option value="oil">Oil painting</option>
        </select>
        <button
          className="btn btn-sm"
          type="button"
          disabled={generating || !prompt.trim()}
          onClick={handleGenerate}
        >
          {generating ? '…' : '✦ Generate'}
        </button>
      </div>

      {error ? <div className="inline-alert inline-alert-error" style={{ marginTop: 6 }}>{error}</div> : null}
      {loading ? <div className="image-gallery-loading">Loading gallery…</div> : null}

      {!loading && images.length === 0 ? (
        <div className="image-gallery-empty">No images yet — generate your first scene image above.</div>
      ) : null}

      <div className="image-gallery-grid">
        {images.map(img => (
          <div key={img.id} className="image-gallery-item">
            <img
              src={img.image_url}
              alt={img.prompt}
              className="image-gallery-img"
              loading="lazy"
              onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
            />
            <div className="image-gallery-meta">
              <span className="image-gallery-prompt-label">{img.prompt}</span>
              <span className="image-gallery-style-badge">{img.style}</span>
              {img.cached ? <span className="image-gallery-cached" title="Returned from cache">↩ cached</span> : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
