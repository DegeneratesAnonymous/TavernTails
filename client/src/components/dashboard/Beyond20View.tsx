import React, { useMemo, useState } from 'react'

import Beyond20Agent from '../../agents/Beyond20Agent'
import { API_BASE, apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'

type Props = {
  activeSessionId: string | null
  identifier?: string | null
  notificationsPending?: boolean
  onNotificationsClick?: () => void
}

async function copyToClipboard(text: string) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (e) {
    // Fallback for non-secure contexts or blocked clipboard access
    window.prompt('Copy to clipboard:', text)
    return false
  }
}

export default function Beyond20View({ activeSessionId, identifier, notificationsPending, onNotificationsClick }: Props) {
  const [relayToken, setRelayToken] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string>('')

  const suggestedBaseUrl = useMemo(() => API_BASE, [])

  const configSnippet = useMemo(() => {
    const sessionId = activeSessionId || '<SESSION_ID>'
    const token = relayToken || '<RELAY_TOKEN>'
    return `// TavernTails relay config\nconst TAVERNTAILS_BASE_URL = '${suggestedBaseUrl}';\nconst SESSION_ID = '${sessionId}';\nconst RELAY_TOKEN = '${token}';\n`
  }, [activeSessionId, relayToken, suggestedBaseUrl])

  return (
    <section className="stack-lg">
      <div className="card card-pad stack">
        <PageHeader
          title="Beyond20"
          subtitle="Relay Beyond20 roll events into your TavernTails session chat."
        />
        <p className="muted" style={{ marginTop: 0 }}>
          Option A relay: run a userscript on D&amp;D Beyond that listens for Beyond20 roll events and forwards them into your TavernTails session chat.
        </p>

        <div className="row-wrap">
          <button
            className="btn"
            disabled={loading}
            onClick={async () => {
              setLoading(true)
              setMessage('')
              try {
                const res = await apiFetch('/player/beyond20/relay-token')
                const data = await res.json().catch(() => ({}))
                if (res.ok) {
                  setRelayToken(String(data?.relay_token || ''))
                  setMessage('Relay token loaded.')
                } else {
                  setMessage(data?.detail || 'Failed to load relay token')
                }
              } catch (e) {
                setMessage('Network error')
              } finally {
                setLoading(false)
              }
            }}
          >
            {loading ? 'Loading…' : 'Get Relay Token'}
          </button>

          <button
            className="btn btn-secondary"
            disabled={loading}
            onClick={async () => {
              if (!window.confirm('Rotate relay token? Any existing userscript config will stop working.')) return
              setLoading(true)
              setMessage('')
              try {
                const res = await apiFetch('/player/beyond20/relay-token/rotate', { method: 'POST' })
                const data = await res.json().catch(() => ({}))
                if (res.ok) {
                  setRelayToken(String(data?.relay_token || ''))
                  setMessage('Relay token rotated.')
                } else {
                  setMessage(data?.detail || 'Failed to rotate relay token')
                }
              } catch (e) {
                setMessage('Network error')
              } finally {
                setLoading(false)
              }
            }}
          >
            Rotate Token
          </button>

          {message ? <span className="muted">{message}</span> : null}
        </div>

        <div className="stack">
          <div className="stack" style={{ gap: 6 }}>
            <label className="muted">Active session id</label>
            <div className="row-wrap">
              <input className="input input-mono" value={activeSessionId || ''} readOnly placeholder="Select a session in Gameplay" />
              <button className="btn btn-quiet btn-sm" type="button" disabled={!activeSessionId} onClick={() => copyToClipboard(activeSessionId || '')}>
                Copy
              </button>
            </div>
          </div>

          <div className="stack" style={{ gap: 6 }}>
            <label className="muted">Relay token</label>
            <div className="row-wrap">
              <input className="input input-mono" value={relayToken} readOnly placeholder="Click Get Relay Token" />
              <button className="btn btn-quiet btn-sm" type="button" disabled={!relayToken} onClick={() => copyToClipboard(relayToken)}>
                Copy
              </button>
            </div>
          </div>

          <div className="stack" style={{ gap: 6 }}>
            <label className="muted">Userscript</label>
            <div className="muted">
              Install Tampermonkey/Violentmonkey, then create a new userscript from <code>tools/beyond20-relay.user.js</code> and paste these values into the config section:
            </div>
            <div className="code-block">
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{configSnippet}</pre>
            </div>
            <div className="row-wrap">
              <button className="btn btn-quiet btn-sm" type="button" onClick={() => copyToClipboard(configSnippet)}>
                Copy snippet
              </button>
              <span className="muted">Then roll on D&amp;D Beyond; results should appear in TavernTails chat.</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card card-pad stack">
        <h3 className="section-title">Beyond20 Custom Domains</h3>
        <Beyond20Agent identifier={identifier ?? null} />
      </div>
    </section>
  )
}
