import React from 'react'

type Props = {
  sessionId: string | null | undefined
  value: string
  onChange: (v: string) => void
  onSend: () => void
}

export default function Composer({ sessionId, value, onChange, onSend }: Props) {
  return (
    <form className="chat-composer" onSubmit={(e) => { e.preventDefault(); onSend() }}>
      <input
        className="input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={sessionId ? 'Type a message or roll (e.g. 1d20+3)' : 'Select a session to chat'}
        disabled={!sessionId}
      />
      <button className="btn" style={{ marginLeft: 8 }} type="submit" disabled={!sessionId}>
        Send
      </button>
    </form>
  )
}
