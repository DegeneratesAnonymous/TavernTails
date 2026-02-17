import React from 'react'

type Props = {
  campaigns: Array<any>
  activeCampaignId: string | null
  onSetActiveCampaignId: (id: string | null) => void | Promise<void>

  sessions: Array<{ id: string }>
  sessionMetaById: Record<string, any>
  activeSessionId: string | null
  onSetActiveSessionId: (id: string | null) => void

  hideSessionSelect?: boolean

  characters: Array<any>
  activeCharacterId: number | null
  onSetActiveCharacterId: (id: number | null) => void
  onSetSessionCharacter: (id: number | null) => Promise<void>

  onNewCharacter: () => void
  onNewCampaign: () => void

  onStartSession?: () => Promise<void> | void
  startSessionBusy?: boolean

  onGoToCampaignSetup?: () => void
  onGoToCharacters?: () => void
  onGoToImport?: () => void

  activeCampaignName: string | null

  notificationsPending?: boolean
  onNotificationsClick?: () => void
}

const BellIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" />
  </svg>
)

const BellUnreadIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0M10.5 8.25h3l-3 4.5h3" />
  </svg>
)

export default function GameplayHeader({
  campaigns,
  activeCampaignId,
  onSetActiveCampaignId,
  sessions,
  sessionMetaById,
  activeSessionId,
  onSetActiveSessionId,
  hideSessionSelect,
  characters,
  activeCharacterId,
  onSetActiveCharacterId,
  onSetSessionCharacter,
  onNewCharacter,
  onNewCampaign,
  onStartSession,
  startSessionBusy,
  onGoToCampaignSetup,
  onGoToCharacters,
  onGoToImport,
  activeCampaignName,
  notificationsPending = false,
  onNotificationsClick,
}: Props) {
  return (
    <div className="gameplay-toolbar">
      <div>
        <div className="gameplay-toolbar-title">Narrative</div>
        <div className="session-label">
          {activeCampaignName ? `Campaign: ${activeCampaignName}` : 'No campaign selected'}
          {activeSessionId ? ` • Session: ${(sessionMetaById[activeSessionId]?.name || activeSessionId)}` : ' • No session selected'}
        </div>
      </div>

      <div className="row-wrap" style={{ justifyContent: 'flex-end', alignItems: 'center' }}>
        <button
          className={`notification-bell ${notificationsPending ? 'notification-bell--pending' : ''}`}
          type="button"
          aria-label={notificationsPending ? 'Unread notifications' : 'No notifications'}
          title={notificationsPending ? 'Unread notifications' : 'No notifications'}
          onClick={onNotificationsClick}
          disabled={!onNotificationsClick}
        >
          {notificationsPending ? <BellUnreadIcon /> : <BellIcon />}
        </button>
        {activeSessionId && onStartSession ? (
          <button className="btn" type="button" onClick={onStartSession} disabled={Boolean(startSessionBusy)}>
            {startSessionBusy ? 'Starting…' : 'Start / Restart Scene'}
          </button>
        ) : null}
        {onGoToCampaignSetup ? (
          <button className="btn btn-secondary" type="button" onClick={onGoToCampaignSetup}>
            Campaign Setup
          </button>
        ) : null}
        {onGoToCharacters ? (
          <button className="btn btn-secondary" type="button" onClick={onGoToCharacters}>
            Characters
          </button>
        ) : null}
        {onGoToImport ? (
          <button className="btn btn-secondary" type="button" onClick={onGoToImport}>
            Import
          </button>
        ) : null}

        <select className="input" value={activeCampaignId || ''} onChange={e => onSetActiveCampaignId(e.target.value || null)}>
          <option value="">Select campaign…</option>
          {campaigns.map(c => (
            <option key={c.id} value={String(c.id)}>
              {c.name}
            </option>
          ))}
        </select>

        {!hideSessionSelect ? (
          <select
            className="input"
            value={activeSessionId || ''}
            onChange={e => onSetActiveSessionId(e.target.value || null)}
            disabled={!activeCampaignId || sessions.length === 0}
            aria-disabled={!activeCampaignId || sessions.length === 0}
          >
            <option value="">Select session…</option>
            {sessions.map(s => {
              const sid = String(s.id)
              const name = sessionMetaById[sid]?.name || sid
              return (
                <option key={sid} value={sid}>
                  {name}
                </option>
              )
            })}
          </select>
        ) : null}

        <select
          className="input"
          value={activeCharacterId === null ? '' : String(activeCharacterId)}
          onChange={async e => {
            const value = e.target.value
            const parsed = value ? Number(value) : null
            onSetActiveCharacterId(parsed)
            await onSetSessionCharacter(parsed)
          }}
          disabled={!activeSessionId}
          aria-disabled={!activeSessionId}
        >
          <option value="">No character</option>
          {characters.map(c => (
            <option key={c.id} value={String(c.id)}>
              {c.name}
              {c.class_name ? ` (${c.class_name})` : ''}
            </option>
          ))}
        </select>

        <button className="btn" onClick={onNewCharacter}>
          Creating a Character
        </button>

        <button className="btn" onClick={onNewCampaign}>
          New Campaign
        </button>
      </div>
    </div>
  )
}
