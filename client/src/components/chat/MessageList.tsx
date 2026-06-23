import React, { useState, useMemo } from 'react'

type Msg = {
  id: number | string
  who: 'gm' | 'you' | 'system' | 'ally'
  text: string
  createdAt?: string
  mentions?: string[]
  senderId?: number | null
  pinned?: boolean
}

type Props = {
  loading: boolean
  messages: Msg[]
  currentUserId?: number | null
  onPin?: (id: number | string) => void
  onDelete?: (id: number | string) => void
}

function formatTime(ts?: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const MessageList = React.forwardRef<HTMLDivElement, Props>(function MessageList(
  { loading, messages, currentUserId, onPin, onDelete },
  ref,
) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchText, setSearchText] = useState('')

  const filtered = useMemo(() => {
    if (!searchText.trim()) return messages
    const q = searchText.trim().toLowerCase()
    return messages.filter(m => m.text.toLowerCase().includes(q))
  }, [messages, searchText])

  return (
    <div className="chat-messages-wrapper">
      {searchOpen ? (
        <div className="chat-search-bar">
          <input
            className="chat-search-input"
            type="text"
            autoFocus
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            placeholder="Search messages…"
          />
          <button className="chat-search-close" type="button"
            onClick={() => { setSearchOpen(false); setSearchText('') }}>✕</button>
        </div>
      ) : null}

      <div className="chat-messages" ref={ref}>
        {loading ? <div className="chat-loading">Loading…</div> : null}

        {filtered.length === 0 && !loading ? (
          <div className="chat-empty">
            {messages.length === 0 ? 'The session begins in silence.' : 'No messages match.'}
          </div>
        ) : null}

        {filtered.map((m) => {
          const ts = formatTime(m.createdAt)
          const canDelete = onDelete && typeof m.id === 'number' && m.senderId !== null && m.senderId !== undefined && m.senderId === currentUserId
          const canPin = onPin && typeof m.id === 'number'

          if (m.who === 'gm') {
            return (
              <div key={m.id} className={`chat-msg chat-msg--gm ${m.pinned ? 'chat-msg--pinned' : ''}`}>
                <div className="chat-msg-gm-text">{m.text}</div>
                <div className="chat-msg-footer">
                  {ts ? <span className="chat-msg-ts">{ts}</span> : null}
                  {m.pinned ? <span className="chat-msg-pin-badge" title="Pinned">⊙</span> : null}
                  <div className="chat-msg-actions">
                    {canPin ? <button className="chat-action-btn" type="button" title={m.pinned ? 'Pinned' : 'Pin'} onClick={() => onPin!(m.id)}>pin</button> : null}
                    {canDelete ? <button className="chat-action-btn chat-action-btn--danger" type="button" onClick={() => onDelete!(m.id)}>✕</button> : null}
                  </div>
                </div>
              </div>
            )
          }

          if (m.who === 'system') {
            return (
              <div key={m.id} className="chat-msg chat-msg--system">
                <span className="chat-msg-system-text">{m.text}</span>
                {ts ? <span className="chat-msg-ts">{ts}</span> : null}
              </div>
            )
          }

          const isYou = m.who === 'you'
          return (
            <div key={m.id} className={`chat-msg ${isYou ? 'chat-msg--you' : 'chat-msg--ally'} ${m.pinned ? 'chat-msg--pinned' : ''}`}>
              {!isYou ? <div className="chat-msg-who">Player</div> : null}
              <div className={`chat-msg-bubble ${isYou ? 'chat-msg-bubble--you' : ''}`}>
                {m.text}
              </div>
              <div className="chat-msg-footer">
                {ts ? <span className="chat-msg-ts">{ts}</span> : null}
                {m.pinned ? <span className="chat-msg-pin-badge">⊙</span> : null}
                {!!m.mentions?.length ? <span className="chat-msg-mention">@{m.mentions.join(', @')}</span> : null}
                <div className="chat-msg-actions">
                  {canPin ? <button className="chat-action-btn" type="button" title={m.pinned ? 'Pinned' : 'Pin'} onClick={() => onPin!(m.id)}>pin</button> : null}
                  {canDelete ? <button className="chat-action-btn chat-action-btn--danger" type="button" onClick={() => onDelete!(m.id)}>✕</button> : null}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <button
        className="chat-search-toggle"
        type="button"
        title="Search messages"
        onClick={() => setSearchOpen(v => !v)}
        aria-label="Search"
      >
        {searchOpen ? '⊗' : '🔍'}
      </button>
    </div>
  )
})

export default MessageList
