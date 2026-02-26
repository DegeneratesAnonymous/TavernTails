import React, { useEffect, useState } from 'react'

import { apiFetch } from '../../api'
import Modal from './Modal'

type TargetUser = {
  id: number
  name: string
}

type Mode = 'block' | 'report'
type Status = 'idle' | 'submitting' | 'success' | 'error'

type Props = {
  open: boolean
  targetUser: TargetUser | null
  initialMode?: Mode
  onClose: () => void
  onBlocked?: (userId: number) => void
}

const REPORT_REASONS: { value: string; label: string }[] = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'spam', label: 'Spam' },
  { value: 'hate_speech', label: 'Hate speech' },
  { value: 'cheating', label: 'Cheating' },
  { value: 'other', label: 'Other' },
]

export default function BlockReportModal({ open, targetUser, initialMode = 'report', onClose, onBlocked }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode)
  const [reason, setReason] = useState('harassment')
  const [details, setDetails] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setMode(initialMode)
      setReason('harassment')
      setDetails('')
      setStatus('idle')
      setError(null)
    }
  }, [open, initialMode])

  const handleClose = () => {
    setStatus('idle')
    setError(null)
    onClose()
  }

  const handleBlock = async () => {
    if (!targetUser) return
    setStatus('submitting')
    setError(null)
    try {
      const res = await apiFetch('/moderation/block/' + targetUser.id, { method: 'POST' })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setError(d?.detail || 'Failed to block user. Please try again.')
        setStatus('error')
        return
      }
      setStatus('success')
      onBlocked?.(targetUser.id)
    } catch {
      setError('Network error. Please try again.')
      setStatus('error')
    }
  }

  const handleReport = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!targetUser) return
    setStatus('submitting')
    setError(null)
    try {
      const res = await apiFetch('/moderation/report/' + targetUser.id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason, details: details.trim() }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setError(d?.detail || 'Failed to submit report. Please try again.')
        setStatus('error')
        return
      }
      setStatus('success')
    } catch {
      setError('Network error. Please try again.')
      setStatus('error')
    }
  }

  const title = mode === 'block' ? `Block ${targetUser?.name ?? 'User'}` : `Report ${targetUser?.name ?? 'User'}`

  return (
    <Modal open={open} title={title} onClose={handleClose}>
      {status === 'success' ? (
        <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{mode === 'block' ? '🚫' : '✅'}</div>
          <p style={{ marginBottom: '1rem' }}>
            {mode === 'block'
              ? `${targetUser?.name ?? 'User'} has been blocked. You will no longer see their activity.`
              : 'Your report has been submitted. Thank you for helping keep the community safe.'}
          </p>
          <button className="btn btn-primary" onClick={handleClose}>
            Close
          </button>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
            <button
              type="button"
              className={mode === 'report' ? 'btn btn-primary btn-sm' : 'btn btn-quiet btn-sm'}
              onClick={() => setMode('report')}
            >
              Report
            </button>
            <button
              type="button"
              className={mode === 'block' ? 'btn btn-primary btn-sm' : 'btn btn-quiet btn-sm'}
              onClick={() => setMode('block')}
            >
              Block
            </button>
          </div>

          {mode === 'block' ? (
            <div>
              <p style={{ marginBottom: '1rem', color: 'var(--text-muted, #aaa)' }}>
                Blocking <strong>{targetUser?.name}</strong> will hide their messages from you and prevent them from
                interacting with you. You can unblock them later from your account settings.
              </p>
              {error && <p className="tt-auth-error">{error}</p>}
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-quiet" onClick={handleClose} disabled={status === 'submitting'}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={handleBlock}
                  disabled={status === 'submitting'}
                >
                  {status === 'submitting' ? 'Blocking…' : 'Block user'}
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleReport} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label htmlFor="report-reason" style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 500 }}>
                  Reason
                </label>
                <select
                  id="report-reason"
                  className="form-input"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  disabled={status === 'submitting'}
                >
                  {REPORT_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="report-details" style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 500 }}>
                  Additional details <span style={{ fontWeight: 400, color: 'var(--text-muted, #aaa)' }}>(optional)</span>
                </label>
                <textarea
                  id="report-details"
                  className="form-input"
                  value={details}
                  onChange={(e) => setDetails(e.target.value)}
                  placeholder="Describe what happened…"
                  rows={4}
                  maxLength={2000}
                  disabled={status === 'submitting'}
                  style={{ resize: 'vertical' }}
                />
              </div>
              {error && <p className="tt-auth-error">{error}</p>}
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-quiet" onClick={handleClose} disabled={status === 'submitting'}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={status === 'submitting'}>
                  {status === 'submitting' ? 'Submitting…' : 'Submit report'}
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </Modal>
  )
}
