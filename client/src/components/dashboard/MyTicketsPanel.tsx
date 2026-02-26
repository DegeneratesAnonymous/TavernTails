import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../api'

type Ticket = {
  id: number
  subject: string
  body: string
  status: string
  created_at: string | null
  updated_at: string | null
}

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  in_progress: 'In Progress',
  resolved: 'Resolved',
  closed: 'Closed',
}

const STATUS_COLORS: Record<string, string> = {
  open: 'rgba(250, 200, 60, 0.85)',
  in_progress: 'rgba(80, 160, 240, 0.85)',
  resolved: 'rgba(60, 200, 120, 0.85)',
  closed: 'rgba(160, 160, 160, 0.7)',
}

type Props = {
  visible?: boolean
  onContact?: () => void
}

export default function MyTicketsPanel({ visible = true, onContact }: Props) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!visible) return
    setLoading(true)
    setError(null)
    try {
      const r = await apiFetch('/support/my-tickets')
      if (!r.ok) throw new Error('Could not load tickets')
      const data = await r.json()
      setTickets(data.tickets || [])
    } catch (err: any) {
      setError(err?.message || 'Failed to load tickets')
    } finally {
      setLoading(false)
    }
  }, [visible])

  useEffect(() => {
    if (visible) load()
  }, [visible, load])

  function formatDate(iso: string | null) {
    if (!iso) return ''
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  return (
    <div className="my-tickets stack">
      {error ? <div className="inline-alert inline-alert-error">{error}</div> : null}
      {loading ? <div className="muted">Loading…</div> : null}

      {!loading && tickets.length === 0 ? (
        <div className="muted" style={{ padding: '12px 0' }}>
          No support tickets yet.{' '}
          {onContact ? (
            <button className="btn btn-quiet btn-sm" type="button" onClick={onContact}>
              Submit a ticket
            </button>
          ) : null}
        </div>
      ) : null}

      {tickets.map(t => (
        <div key={t.id} className="card card-pad" style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
            <div style={{ fontWeight: 700, flex: 1 }}>{t.subject}</div>
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                borderRadius: 8,
                background: STATUS_COLORS[t.status] ?? 'rgba(160,160,160,0.5)',
                color: '#fff',
                whiteSpace: 'nowrap',
              }}
            >
              {STATUS_LABELS[t.status] ?? t.status}
            </span>
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            Submitted {formatDate(t.created_at)}
            {t.updated_at && t.updated_at !== t.created_at ? ` · Updated ${formatDate(t.updated_at)}` : ''}
          </div>
          <div style={{ fontSize: 13, marginTop: 6, color: 'rgba(255,255,255,0.7)' }}>
            {t.body.length > 200 ? `${t.body.slice(0, 200)}…` : t.body}
          </div>
        </div>
      ))}

      {!loading && tickets.length > 0 && onContact ? (
        <div style={{ marginTop: 8 }}>
          <button className="btn btn-secondary btn-sm" type="button" onClick={onContact}>
            Submit a new ticket
          </button>
        </div>
      ) : null}
    </div>
  )
}
