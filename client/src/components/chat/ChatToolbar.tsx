import React from 'react'

type Props = {
  sessionId: string | null | undefined
  inviteBusy: boolean
  exporting: boolean
  hasMessages: boolean
  showInviteForm: boolean
  showToolsPanel: boolean
  onToggleInvite: () => void
  onExport: () => void
  onToggleTools: () => void
  toolbarMessage: string | null
}

export default function ChatToolbar({
  sessionId,
  inviteBusy,
  exporting,
  hasMessages,
  showInviteForm,
  showToolsPanel,
  onToggleInvite,
  onExport,
  onToggleTools,
  toolbarMessage,
}: Props) {
  return (
    <div className="chat-toolbar">
      <div className="chat-toolbar-row">
        <button
          className={`chat-tool-chip ${showInviteForm ? 'chat-tool-chip--active' : ''}`}
          type="button"
          disabled={!sessionId || inviteBusy}
          onClick={onToggleInvite}
          title="Invite a friend"
        >
          + Invite
        </button>
        <button
          className={`chat-tool-chip ${showToolsPanel ? 'chat-tool-chip--active' : ''}`}
          type="button"
          disabled={!sessionId}
          onClick={onToggleTools}
          title="Advanced tools"
        >
          ⚙ Tools
        </button>
        <button
          className="chat-tool-chip"
          type="button"
          disabled={!hasMessages || exporting}
          onClick={onExport}
          title="Export chat log"
        >
          {exporting ? '…' : '↓ Log'}
        </button>
      </div>
      {toolbarMessage ? <div className="chat-toolbar-message">{toolbarMessage}</div> : null}
    </div>
  )
}
