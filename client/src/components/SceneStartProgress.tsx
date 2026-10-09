import React, { useCallback, useEffect, useRef, useState } from 'react'
import { buildApiUrl } from '../api'
import './SceneStartProgress.css'

type StartStatus = {
  state: 'idle' | 'running' | 'done' | 'failed' | 'needs_setup'
  stage: string
  stages: { id: string; label: string }[]
  elapsed_s: number
  error: string | null
  scene_ready: boolean
}

type Props = {
  sessionId: string
  onReady: () => void
}

const POLL_MS = 2000
const SLOW_AFTER_S = 150

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token')
  return token ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } : { 'Content-Type': 'application/json' }
}

export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

/** Shown while the opening scene is being written: real stages, elapsed time, and a way back from failure. */
export default function SceneStartProgress({ sessionId, onReady }: Props) {
  const [status, setStatus] = useState<StartStatus | null>(null)
  const [pollError, setPollError] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const autoStarted = useRef(false)
  const readyFired = useRef(false)

  const startScene = useCallback(async () => {
    try {
      // The server joins an already-running start, so this can never double the work.
      await fetch(buildApiUrl(`/sessions/${sessionId}/start`), { method: 'POST', headers: authHeaders(), body: JSON.stringify({}) })
    } catch { /* the next status poll reports what happened */ }
  }, [sessionId])

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const res = await fetch(buildApiUrl(`/sessions/${sessionId}/start-status`), { headers: authHeaders() })
        if (!res.ok) throw new Error(String(res.status))
        const next = (await res.json()) as StartStatus
        if (cancelled) return
        setStatus(next)
        setPollError(false)
        if (next.scene_ready && !readyFired.current) {
          readyFired.current = true
          onReady()
          return
        }
        if (next.state === 'idle' && !autoStarted.current) {
          autoStarted.current = true
          void startScene()
        }
      } catch {
        if (!cancelled) setPollError(true)
      }
      if (!cancelled) timer = setTimeout(poll, POLL_MS)
    }
    void poll()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [sessionId, onReady, startScene])

  const retry = async () => {
    setRetrying(true)
    setStatus(prev => (prev ? { ...prev, state: 'running', error: null, elapsed_s: 0 } : prev))
    await startScene()
    setRetrying(false)
  }

  if (!status) {
    return (
      <div className="scene-start" role="status" aria-live="polite">
        <div className="scene-start__card">
          <h2 className="scene-start__title">{pollError ? 'Can’t reach the game server' : 'Preparing your scene'}</h2>
          <p className="scene-start__note">{pollError ? 'Retrying every couple of seconds…' : 'Checking where your adventure stands…'}</p>
        </div>
      </div>
    )
  }

  if (status.state === 'failed') {
    return (
      <div className="scene-start" role="alert">
        <div className="scene-start__card scene-start__card--error">
          <h2 className="scene-start__title">The opening scene didn’t finish</h2>
          <p className="scene-start__note">{status.error || 'The story engine stopped before the scene was ready.'}</p>
          <p className="scene-start__note">Your character and setup are saved. Trying again won’t lose anything.</p>
          <button type="button" className="scene-start__button" onClick={retry} disabled={retrying}>
            {retrying ? 'Starting…' : 'Try again'}
          </button>
        </div>
      </div>
    )
  }

  if (status.state === 'needs_setup') {
    return (
      <div className="scene-start" role="status" aria-live="polite">
        <div className="scene-start__card">
          <h2 className="scene-start__title">One more step before the story begins</h2>
          <p className="scene-start__note">Answer the opening questions for this session, then your first scene will be written.</p>
          <button
            type="button"
            className="scene-start__button"
            onClick={() => window.dispatchEvent(new CustomEvent('session:open-opening-setup', { detail: { sessionId } }))}
          >
            Continue setup
          </button>
        </div>
      </div>
    )
  }

  const currentIndex = Math.max(0, status.stages.findIndex(s => s.id === status.stage))
  const slow = status.elapsed_s > SLOW_AFTER_S
  return (
    <div className="scene-start" role="status" aria-live="polite">
      <div className="scene-start__card">
        <h2 className="scene-start__title">Writing your opening</h2>
        <ol className="scene-start__steps">
          {status.stages.map((step, index) => {
            const state = index < currentIndex ? 'done' : index === currentIndex ? 'active' : 'pending'
            return (
              <li key={step.id} className={`scene-start__step scene-start__step--${state}`} aria-current={state === 'active' ? 'step' : undefined}>
                <span className="scene-start__mark" aria-hidden="true">{state === 'done' ? '✓' : state === 'active' ? '●' : '○'}</span>
                <span>{step.label}</span>
              </li>
            )
          })}
        </ol>
        <div className="scene-start__meter" aria-hidden="true">
          <div className="scene-start__meter-fill" style={{ width: `${Math.round(((currentIndex + 0.5) / status.stages.length) * 100)}%` }} />
        </div>
        <p className="scene-start__elapsed">{formatElapsed(status.elapsed_s)} elapsed</p>
        <p className="scene-start__note">
          {slow
            ? 'This is taking longer than usual — the model is busy. Your scene is still being written.'
            : 'A scene usually takes a minute or two. You can leave this page; it keeps writing.'}
        </p>
        {pollError && <p className="scene-start__note scene-start__note--warn">Lost contact with the server; still trying…</p>}
      </div>
    </div>
  )
}
