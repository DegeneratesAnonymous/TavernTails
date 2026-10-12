import React, { useEffect, useRef, useState } from 'react'
import { fetchRecap } from './sceneAssistApi'
import type { Recap } from './sceneAssistApi'
import './SceneAssist.css'

type Props = { sessionId: string | null | undefined; open: boolean; onClose: () => void }

/** "Previously": where the story stands, for someone returning to it or who lost the thread. */
export default function RecapDialog({ sessionId, open, onClose }: Props) {
  const [recap, setRecap] = useState<Recap | null>(null)
  const [failed, setFailed] = useState(false)
  const dialog = useRef<HTMLDivElement | null>(null)
  const opener = useRef<Element | null>(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose // the caller's handler changes every render; the focus effect must not restart for it

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

  // Focus moves into the dialog, stays inside it, and goes back to what opened it.
  useEffect(() => {
    if (!open) return
    opener.current = document.activeElement
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button, [href], input, [tabindex]:not([tabindex="-1"])') || [])
    focusable()[0]?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { closeRef.current(); return }
      if (e.key !== 'Tab') return
      const items = focusable()
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      if (opener.current instanceof HTMLElement) opener.current.focus()
    }
  }, [open])

  if (!open) return null
  const earlier = recap?.previously || []
  return (
    <div className="recap-backdrop" onClick={onClose}>
      <div className="recap-dialog" ref={dialog} role="dialog" aria-modal="true" aria-label="Previously" onClick={e => e.stopPropagation()}>
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
