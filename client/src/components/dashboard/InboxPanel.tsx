import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../api'

type DirectMessage = {
  id: number
  sender_id: number
  recipient_id: number
  sender_name?: string | null
  recipient_name?: string | null
  body: string
  read: boolean
  created_at: string | null
}

type Friend = {
  id: number
  name?: string
  username?: string
  email?: string
}

type Props = {
  profile?: any
  visible?: boolean
}

type Tab = 'inbox' | 'sent' | 'compose'

export default function InboxPanel({ profile, visible = true }: Props) {
  const [tab, setTab] = useState<Tab>('inbox')
  const [inbox, setInbox] = useState<DirectMessage[]>([])
  const [sent, setSent] = useState<DirectMessage[]>([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Compose state
  const [friends, setFriends] = useState<Friend[]>([])
  const [recipientId, setRecipientId] = useState<string>('')
  const [composeBody, setComposeBody] = useState('')
  const [sending, setSending] = useState(false)
  const [sendMsg, setSendMsg] = useState<string | null>(null)

  const loadInbox = useCallback(async () => {
    if (!visible) return
    setLoading(true)
    setError(null)
    try {
      const r = await apiFetch('/messages/inbox')
      if (!r.ok) throw new Error('Could not load inbox')
      const data = await r.json()
      setInbox(data.messages || [])
      setUnread(data.unread || 0)
    } catch (err: any) {
      setError(err?.message || 'Failed to load inbox')
    } finally {
      setLoading(false)
    }
  }, [visible])

  const loadSent = useCallback(async () => {
    if (!visible) return
    setLoading(true)
    setError(null)
    try {
      const r = await apiFetch('/messages/sent')
      if (!r.ok) throw new Error('Could not load sent messages')
      const data = await r.json()
      setSent(data.messages || [])
    } catch (err: any) {
      setError(err?.message || 'Failed to load sent messages')
    } finally {
      setLoading(false)
    }
  }, [visible])

  const loadFriends = useCallback(async () => {
    try {
      const r = await apiFetch('/player/friends')
      if (!r.ok) return
      const data = await r.json()
      const accepted: Friend[] = (Array.isArray(data.friends) ? data.friends : []).map((f: any) => ({
        id: f.id ?? f.user_id,
        name: f.profile?.name || f.name,
        username: f.username,
        email: f.email,
      }))
      setFriends(accepted)
    } catch { /* non-critical */ }
  }, [])

  useEffect(() => {
    if (visible) {
      loadInbox()
      loadFriends()
    }
  }, [visible, loadInbox, loadFriends])

  useEffect(() => {
    if (tab === 'sent') loadSent()
    if (tab === 'inbox') loadInbox()
    if (tab === 'compose') loadFriends()
  }, [tab, loadSent, loadInbox, loadFriends])

  async function handleMarkRead(msgId: number) {
    await apiFetch(`/messages/${msgId}/read`, { method: 'POST' })
    setInbox(prev => prev.map(m => m.id === msgId ? { ...m, read: true } : m))
    setUnread(u => Math.max(0, u - 1))
  }

  async function handleDelete(msgId: number, source: 'inbox' | 'sent') {
    await apiFetch(`/messages/${msgId}`, { method: 'DELETE' })
    if (source === 'inbox') setInbox(prev => prev.filter(m => m.id !== msgId))
    else setSent(prev => prev.filter(m => m.id !== msgId))
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    if (!composeBody.trim() || !recipientId) return
    setSending(true)
    setSendMsg(null)
    try {
      const r = await apiFetch('/messages/send', {
        method: 'POST',
        body: JSON.stringify({ recipient_id: Number(recipientId), body: composeBody.trim() }),
      })
      if (!r.ok) {
        const d = await r.json().catch(() => null)
        throw new Error(d?.detail || 'Failed to send message')
      }
      setComposeBody('')
      setRecipientId('')
      setSendMsg('Message sent!')
      setTab('sent')
      loadSent()
    } catch (err: any) {
      setSendMsg(err?.message || 'Send failed')
    } finally {
      setSending(false)
    }
  }

  function friendLabel(f: Friend) {
    return f.name || f.username || f.email || `User ${f.id}`
  }

  function formatDate(iso: string | null) {
    if (!iso) return ''
    try { return new Date(iso).toLocaleString() } catch { return iso }
  }

  return (
    <div className="inbox-panel stack">
      <div className="inbox-tabs" role="tablist">
        <button
          role="tab"
          className={`inbox-tab${tab === 'inbox' ? ' active' : ''}`}
          onClick={() => setTab('inbox')}
        >
          Inbox {unread > 0 ? <span className="inbox-badge">{unread}</span> : null}
        </button>
        <button
          role="tab"
          className={`inbox-tab${tab === 'sent' ? ' active' : ''}`}
          onClick={() => setTab('sent')}
        >
          Sent
        </button>
        <button
          role="tab"
          className={`inbox-tab${tab === 'compose' ? ' active' : ''}`}
          onClick={() => setTab('compose')}
        >
          ✦ Compose
        </button>
      </div>

      {error ? <div className="inline-alert inline-alert-error">{error}</div> : null}

      {tab === 'inbox' && (
        <div className="inbox-list">
          {loading ? <div className="muted">Loading…</div> : null}
          {!loading && inbox.length === 0 ? (
            <div className="muted" style={{ padding: '12px 0' }}>No messages yet.</div>
          ) : null}
          {inbox.map(msg => (
            <div key={msg.id} className={`inbox-item${msg.read ? '' : ' inbox-item--unread'}`}>
              <div className="inbox-item-header">
                <span className="inbox-item-from">From: {msg.sender_name || `User ${msg.sender_id}`}</span>
                <span className="inbox-item-date">{formatDate(msg.created_at)}</span>
              </div>
              <div className="inbox-item-body">{msg.body}</div>
              <div className="inbox-item-actions">
                {!msg.read ? (
                  <button className="btn btn-sm btn-quiet" type="button" onClick={() => handleMarkRead(msg.id)}>
                    Mark read
                  </button>
                ) : null}
                <button className="btn btn-sm btn-quiet" type="button" onClick={() => handleDelete(msg.id, 'inbox')}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'sent' && (
        <div className="inbox-list">
          {loading ? <div className="muted">Loading…</div> : null}
          {!loading && sent.length === 0 ? (
            <div className="muted" style={{ padding: '12px 0' }}>No sent messages.</div>
          ) : null}
          {sent.map(msg => (
            <div key={msg.id} className="inbox-item">
              <div className="inbox-item-header">
                <span className="inbox-item-from">To: {msg.recipient_name || `User ${msg.recipient_id}`}</span>
                <span className="inbox-item-date">{formatDate(msg.created_at)}</span>
              </div>
              <div className="inbox-item-body">{msg.body}</div>
              <div className="inbox-item-actions">
                <button className="btn btn-sm btn-quiet" type="button" onClick={() => handleDelete(msg.id, 'sent')}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'compose' && (
        <form className="stack" style={{ gap: 10 }} onSubmit={handleSend}>
          {sendMsg ? (
            <div className={`inline-alert${sendMsg === 'Message sent!' ? '' : ' inline-alert-error'}`}>{sendMsg}</div>
          ) : null}
          <div>
            <label className="muted" style={{ fontSize: 13 }}>To (friend)</label>
            <select
              className="input"
              value={recipientId}
              onChange={e => setRecipientId(e.target.value)}
              disabled={sending}
            >
              <option value="">— Select a friend —</option>
              {friends.map(f => (
                <option key={f.id} value={String(f.id)}>{friendLabel(f)}</option>
              ))}
            </select>
            {friends.length === 0 ? (
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                You need to add friends before you can send messages.
              </div>
            ) : null}
          </div>
          <div>
            <label className="muted" style={{ fontSize: 13 }}>Message</label>
            <textarea
              className="input"
              rows={4}
              placeholder="Write your message…"
              value={composeBody}
              onChange={e => setComposeBody(e.target.value)}
              disabled={sending}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-sm" type="submit" disabled={sending || !recipientId || !composeBody.trim()}>
              {sending ? 'Sending…' : 'Send Message'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
