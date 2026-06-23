import React, { useRef } from 'react'

const DICE = [4, 6, 8, 10, 12, 20]

function addDie(current: string, sides: number): string {
  const trimmed = current.trim()
  const m = trimmed.match(new RegExp(`^(\\d+)d${sides}$`, 'i'))
  return m ? `${parseInt(m[1], 10) + 1}d${sides}` : `1d${sides}`
}

type Props = {
  sessionId: string | null | undefined
  value: string
  onChange: (v: string) => void
  onSend: () => void
}

export default function Composer({ sessionId, value, onChange, onSend }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDie = (sides: number) => {
    onChange(addDie(value, sides))
    inputRef.current?.focus()
  }

  return (
    <div className="chat-composer-wrap">
      <form className="chat-composer-row" onSubmit={e => { e.preventDefault(); onSend() }}>
        <div className="chat-composer-dice">
          {DICE.map(s => (
            <button
              key={s}
              type="button"
              className="chat-die-btn"
              title={`d${s}`}
              disabled={!sessionId}
              onClick={() => handleDie(s)}
            >
              d{s}
            </button>
          ))}
        </div>
        <input
          ref={inputRef}
          className="chat-composer-input"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={sessionId ? 'Message or roll (e.g. 1d20+3)…' : 'Select a session'}
          disabled={!sessionId}
        />
        <button
          className="chat-composer-send"
          type="submit"
          disabled={!sessionId || !value.trim()}
          aria-label="Send"
        >
          ↑
        </button>
      </form>
    </div>
  )
}
