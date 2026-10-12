import React, { useEffect, useState } from 'react'
import { fetchRecap } from './sceneAssistApi'
import type { Recap } from './sceneAssistApi'
import './SceneAssist.css'

type Props = { sessionId: string | null | undefined; open: boolean; onClose: () => void }

/** "Previously": where the story stands, for someone returning to it or who lost the thread. */
export default function RecapDialog({ sessionId, open, onClose }: Props) {
  const [recap, setRecap] = useState<Recap | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!open || !sessionId) return
    let alive = true
    setRecap(null)
    setFailed(false)
    void fetchRecap(sessionId).then(result => {
      if (!alive) return
      if (result) setRecap(result)
      else setFailed(true)
    })
    return () => { alive = false }
  }, [open, sessionId])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  const earlier = recap?.previously || []
  return (
    <div className="recap-backdrop" onClick={onClose}>
      <div className="recap-dialog" role="dialog" aria-modal="true" aria-label="Previously" onClick={e => e.stopPropagation()}>
        <header>
          <h2>Previously{recap?.title ? ` in ${recap.title}` : ''}</h2>
          <button type="button" className="assist-x" aria-label="Close" onClick={onClose}>×</button>
        </header>
        {failed ? <p>The recap is not available right now.</p> : null}
        {!recap && !failed ? <p>Gathering the story so far…</p> : null}
        {recap ? (
          <>
            {earlier.length ? (
              <ol className="recap-earlier">
                {earlier.map((line, i) => <li key={i}>{line}</li>)}
              </ol>
            ) : <p className="recap-empty">This is where the story begins.</p>}
            <section>
              <h3>Right now{recap.place ? ` · ${recap.place}` : ''}</h3>
              {recap.right_now ? <p>{recap.right_now}</p> : null}
              {recap.present?.length ? (
                <p className="recap-people">
                  Here: {recap.present.map(p => (p.role ? `${p.name} (${p.role})` : p.name)).join(', ')}
                </p>
              ) : null}
              {recap.open_question ? <p className="scene-hook"><span className="scene-hook-label">Unanswered</span> {recap.open_question}</p> : null}
            </section>
          </>
        ) : null}
        <footer><button type="button" className="assist-suggest" onClick={onClose}>Back to the story</button></footer>
      </div>
    </div>
  )
}
