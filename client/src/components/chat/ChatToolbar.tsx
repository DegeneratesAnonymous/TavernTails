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
      <div className="row-wrap">
        <button className="btn btn-sm" type="button" disabled={!sessionId || inviteBusy} onClick={onToggleInvite}>
          {showInviteForm ? 'Close Invite' : 'Invite Friend'}
        </button>
        <button className="btn btn-sm btn-secondary" type="button" disabled={!hasMessages || exporting} onClick={onExport}>
          {exporting ? 'Exporting…' : 'Export Log'}
        </button>
        <button className="btn btn-sm btn-secondary" type="button" disabled={!sessionId} onClick={onToggleTools}>
          {showToolsPanel ? 'Hide Tools' : 'Advanced Tools'}
        </button>
      </div>
      {toolbarMessage ? <div className="chat-toolbar-message">{toolbarMessage}</div> : null}
    </div>
  )
}
