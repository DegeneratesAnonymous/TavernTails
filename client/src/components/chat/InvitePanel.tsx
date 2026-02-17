import React from 'react'

type Props = {
  inviteEmail: string
  inviteNote: string
  inviteBusy: boolean
  onChangeEmail: (v: string) => void
  onChangeNote: (v: string) => void
  onSubmit: () => void
}

export default function InvitePanel({ inviteEmail, inviteNote, inviteBusy, onChangeEmail, onChangeNote, onSubmit }: Props) {
  return (
    <div className="chat-panel stack">
      <div className="chat-panel-title">Send a quick invite</div>
      <input
        className="input"
        value={inviteEmail}
        onChange={(e) => onChangeEmail(e.target.value)}
        placeholder="friend@example.com"
        disabled={inviteBusy}
      />
      <textarea
        className="input"
        value={inviteNote}
        onChange={(e) => onChangeNote(e.target.value)}
        placeholder="Optional note"
        rows={2}
        disabled={inviteBusy}
      />
      <div style={{ textAlign: 'right' }}>
        <button className="btn btn-sm" type="button" onClick={onSubmit} disabled={inviteBusy}>
          {inviteBusy ? 'Sending…' : 'Send Invite'}
        </button>
      </div>
    </div>
  )
}
