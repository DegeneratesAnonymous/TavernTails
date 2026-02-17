import React from 'react'

import PageHeader from '../ui/PageHeader'

type Props = {
  profile: any
  lastSessionLabel?: string | null
  onQuickstartNewGame: () => void
  onStartLastCampaign: () => void
  onGoToCampaigns: () => void
  onGoToCharacters: () => void
  notificationsPending?: boolean
  onNotificationsClick?: () => void
}

export default function DashboardHome({
  profile,
  lastSessionLabel,
  onQuickstartNewGame,
  onStartLastCampaign,
  onGoToCampaigns,
  onGoToCharacters,
  notificationsPending,
  onNotificationsClick,
}: Props) {
  return (
    <section className="dashboard-panel stack home-panel">
      <PageHeader
        title="Home"
        subtitle={`Welcome${profile?.name ? `, ${profile.name}` : ''}. Pick up where you left off or jump into prep.`}
        notificationsPending={notificationsPending}
        onNotificationsClick={onNotificationsClick}
      />

      <div className="card card-pad home-card">
        <div className="home-card-title">Quick actions</div>
        <div className="row-wrap home-actions">
          <button className="btn" type="button" onClick={onQuickstartNewGame}>
            Quickstart New Game
          </button>
          <button className="btn btn-secondary" type="button" onClick={onStartLastCampaign}>
            Start Last Campaign{lastSessionLabel ? `: ${lastSessionLabel}` : ''}
          </button>
          <button className="btn btn-secondary" type="button" onClick={onGoToCampaigns}>Manage Campaigns</button>
          <button className="btn btn-secondary" type="button" onClick={onGoToCharacters}>Manage Characters</button>
        </div>
      </div>

      <div className="card card-pad home-card">
        <div className="home-card-title">Getting started</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Start a campaign, import your characters, and then jump into gameplay. You can always return here from the sidebar.
        </div>
      </div>
    </section>
  )
}
