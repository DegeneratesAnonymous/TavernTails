import React, { useState } from 'react'

import { apiFetch } from '../../api'
import Modal from './Modal'

type Props = {
  open: boolean
  onClose: () => void
}

type TicketStatus = 'idle' | 'submitting' | 'success' | 'error'

export default function ContactModal({ open, onClose }: Props) {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [status, setStatus] = useState<TicketStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setSubject('')
    setBody('')
    setStatus('idle')
    setError(null)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!subject.trim()) {
      setError('Please provide a subject.')
      return
    }
    if (body.trim().length < 10) {
      setError('Please describe your issue in a bit more detail (at least 10 characters).')
      return
    }
    setStatus('submitting')
    setError(null)
    try {
      const res = await apiFetch('/support/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: subject.trim(), body: body.trim() }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setError(d?.detail || `Failed to submit your message (error ${res.status}). Please try again later.`)
        setStatus('error')
        return
      }
      setStatus('success')
    } catch {
      setError('Network error. Please try again.')
      setStatus('error')
    }
  }

  return (
    <Modal open={open} title="Contact Us" onClose={handleClose}>
      {status === 'success' ? (
        <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>✅</div>
          <p style={{ marginBottom: '1rem' }}>Your message has been sent! We'll get back to you soon.</p>
          <button className="btn btn-primary" onClick={handleClose}>
            Close
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label htmlFor="contact-subject" style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 500 }}>
              Subject
            </label>
            <input
              id="contact-subject"
              type="text"
              className="form-input"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Brief summary of your issue"
              maxLength={200}
              required
              disabled={status === 'submitting'}
            />
          </div>
          <div>
            <label htmlFor="contact-body" style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 500 }}>
              Message
            </label>
            <textarea
              id="contact-body"
              className="form-input"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Describe your issue or question in detail…"
              rows={6}
              maxLength={5000}
              required
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
              {status === 'submitting' ? 'Sending…' : 'Send message'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}
