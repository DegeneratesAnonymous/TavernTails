import React, { useState } from 'react'

type PinnedMsg = {
  id: number | string
  text: string
  who: string
}

type Props = {
  pins: PinnedMsg[]
  onUnpin?: (id: number | string) => void
}

export default function PinnedBar({ pins, onUnpin }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  if (!pins.length) return null
  return (
    <div className="chat-pinned-bar">
      <div className="chat-pinned-bar-header" onClick={() => setCollapsed(v => !v)} style={{ cursor: 'pointer', userSelect: 'none' }}>
        <span className="chat-pinned-bar-icon">📌</span>
        <span className="chat-pinned-bar-title">{pins.length} pinned</span>
        <span className="chat-pinned-bar-toggle">{collapsed ? '▲' : '▼'}</span>
      </div>
      {!collapsed && (
        <div className="chat-pinned-bar-list">
          {pins.map(p => (
            <div key={p.id} className="chat-pinned-bar-item">
              <span className="chat-pinned-bar-who">{p.who.toUpperCase()}</span>
              <span className="chat-pinned-bar-text">{p.text}</span>
              {onUnpin && (
                <button
                  className="chat-pinned-bar-unpin"
                  type="button"
                  title="Unpin"
                  onClick={() => onUnpin(p.id)}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
