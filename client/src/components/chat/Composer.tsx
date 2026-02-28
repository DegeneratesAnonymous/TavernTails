import React from 'react'

const DICE_SIDES = [4, 6, 8, 10, 12, 20]

/** Given the current input value, return an updated value with the chosen die incremented or set. */
function addDieToInput(current: string, sides: number): string {
  const trimmed = current.trim()
  // If the input is exactly "NdM" for this die type, increment N
  const exactMatch = new RegExp(`^(\\d+)d${sides}$`, 'i')
  const m = trimmed.match(exactMatch)
  if (m) {
    return `${parseInt(m[1], 10) + 1}d${sides}`
  }
  // Otherwise start fresh with this die type
  return `1d${sides}`
}

type Props = {
  sessionId: string | null | undefined
  value: string
  onChange: (v: string) => void
  onSend: () => void
}

export default function Composer({ sessionId, value, onChange, onSend }: Props) {
  return (
    <div className="chat-composer-wrap">
      <div className="chat-dice-tray" aria-label="Dice roller">
        {DICE_SIDES.map(sides => (
          <button
            key={sides}
            type="button"
            className="chat-die-btn"
            title={`Add d${sides}`}
            aria-label={`Roll d${sides}`}
            disabled={!sessionId}
            onClick={() => onChange(addDieToInput(value, sides))}
          >
            d{sides}
          </button>
        ))}
      </div>
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
    </div>
  )
}
