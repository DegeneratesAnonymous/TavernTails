import React, { useState, useMemo } from 'react'
import { CharacterSummary } from '../CharacterPanel'

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
  character?: CharacterSummary | null
}

function formatTime(ts?: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// Parse message text into segments: plain text and @tag tokens
type TextSegment = { kind: 'text'; text: string }
type TagSegment = { kind: 'tag'; tag: string; result: string | null }
type Segment = TextSegment | TagSegment

function parseSegments(text: string): Segment[] {
  const segments: Segment[] = []
  // Match @tagname or @tagname[result]
  const re = /@([\w+\-']+)(?:\[([^\]]+)\])?/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) segments.push({ kind: 'text', text: text.slice(last, m.index) })
    const tag = m[1]
    const resultStr = m[2] ?? null
    segments.push({ kind: 'tag', tag, result: resultStr })
    last = m.index + m[0].length
  }
  if (last < text.length) segments.push({ kind: 'text', text: text.slice(last) })
  return segments
}

function extractTotal(result: string): string {
  // result like "14+3=17" or "9-2=7" — extract the final number
  const m = result.match(/=(-?\d+)$/)
  return m ? m[1] : result
}

function renderSegments(segments: Segment[]): React.ReactNode {
  return segments.map((seg, i) => {
    if (seg.kind === 'text') return seg.text || null
    const display = seg.tag.replace(/_/g, ' ')
    if (seg.result !== null) {
      const total = extractTotal(seg.result)
      return (
        <span key={i} className="chat-tag chat-tag--roll" title={`${display}: ${seg.result}`}>
          {display} <span className="chat-tag-result">{total}</span>
        </span>
      )
    }
    return (
      <span key={i} className="chat-tag chat-tag--ref">
        @{display}
      </span>
    )
  })
}

function RenderText({ text }: { text: string }) {
  const segs = useMemo(() => parseSegments(text), [text])
  const hasTag = segs.some(s => s.kind === 'tag')
  if (!hasTag) return <>{text}</>
  return <>{renderSegments(segs)}</>
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
                <div className="chat-msg-gm-text"><RenderText text={m.text} /></div>
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
                <span className="chat-msg-system-text"><RenderText text={m.text} /></span>
                {ts ? <span className="chat-msg-ts">{ts}</span> : null}
              </div>
            )
          }

          const isYou = m.who === 'you'
          return (
            <div key={m.id} className={`chat-msg ${isYou ? 'chat-msg--you' : 'chat-msg--ally'} ${m.pinned ? 'chat-msg--pinned' : ''}`}>
              {!isYou ? <div className="chat-msg-who">Player</div> : null}
              <div className={`chat-msg-bubble ${isYou ? 'chat-msg-bubble--you' : ''}`}>
                <RenderText text={m.text} />
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
