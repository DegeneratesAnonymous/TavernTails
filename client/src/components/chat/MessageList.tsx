import React, { useState, useMemo } from 'react'

type Msg = {
  id: number | string
  who: 'gm' | 'you' | 'system' | 'ally'
  text: string
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

const ROLE_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'you', label: 'You' },
  { value: 'gm', label: 'GM' },
  { value: 'ally', label: 'Others' },
  { value: 'system', label: 'System' },
]

const MessageList = React.forwardRef<HTMLDivElement, Props>(function MessageList(
  { loading, messages, currentUserId, onPin, onDelete },
  ref,
) {
  const [roleFilter, setRoleFilter] = useState('')
  const [searchText, setSearchText] = useState('')

  const filtered = useMemo(() => {
    let list = messages
    if (roleFilter) list = list.filter(m => m.who === roleFilter)
    if (searchText.trim()) {
      const q = searchText.trim().toLowerCase()
      list = list.filter(m => m.text.toLowerCase().includes(q))
    }
    return list
  }, [messages, roleFilter, searchText])

  return (
    <div className="chat-messages-wrapper">
      <div className="chat-filter-bar">
        <select
          className="chat-filter-select"
          value={roleFilter}
          onChange={e => setRoleFilter(e.target.value)}
          aria-label="Filter by role"
        >
          {ROLE_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <input
          className="chat-filter-search input"
          type="text"
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          placeholder="Search messages…"
          aria-label="Search chat"
        />
        {(roleFilter || searchText) && (
          <button
            className="btn btn-sm btn-secondary"
            type="button"
            onClick={() => { setRoleFilter(''); setSearchText('') }}
            aria-label="Clear filters"
          >
            ✕
          </button>
        )}
      </div>
      <div className="chat-messages" ref={ref}>
        {loading ? <div className="chat-loading">Loading chat…</div> : null}
        {filtered.length === 0 && !loading ? (
          <div className="chat-empty">
            {messages.length === 0 ? 'No messages yet.' : 'No messages match the current filter.'}
          </div>
        ) : null}
        {filtered.map((m) => {
          const canDelete = onDelete && typeof m.id === 'number' && m.senderId !== null && m.senderId !== undefined && m.senderId === currentUserId
          const canPin = onPin && typeof m.id === 'number'
          return (
            <div key={m.id} className={`chat-message ${m.who === 'system' ? 'chat-message-system' : ''} ${m.pinned ? 'chat-message-pinned' : ''}`}>
              <div className="chat-message-who">{m.who.toUpperCase()}</div>
              <div className={`chat-message-bubble ${m.who === 'you' ? 'chat-message-you' : ''}`}>{m.text}</div>
              {m.pinned ? <span className="chat-pin-badge" title="Pinned">📌</span> : null}
              {!!m.mentions?.length ? <div className="chat-message-mentions">Mentions: {m.mentions.join(', ')}</div> : null}
              <div className="chat-message-actions">
                {canPin ? (
                  <button
                    className="chat-action-btn"
                    type="button"
                    title={m.pinned ? 'Pinned' : 'Pin message'}
                    onClick={() => onPin!(m.id)}
                    aria-label="Pin message"
                  >
                    📌
                  </button>
                ) : null}
                {canDelete ? (
                  <button
                    className="chat-action-btn chat-action-btn--danger"
                    type="button"
                    title="Delete message"
                    onClick={() => onDelete!(m.id)}
                    aria-label="Delete message"
                  >
                    🗑
                  </button>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
})

export default MessageList

