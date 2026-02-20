import React from 'react'

import PageHeader from '../ui/PageHeader'

type Props = {
  profile: any
  lastSessionLabel?: string | null
  onStartNewGame: () => void
  onLoadGame: () => void
  onGoToCharacters: () => void
  onGoToCampaigns: () => void
  onGoToExplore: () => void
  onGoToGuides: () => void
  notificationsPending?: boolean
  onNotificationsClick?: () => void
  // legacy aliases kept for backward compat
  onQuickstartNewGame?: () => void
  onStartLastCampaign?: () => void
}

export default function DashboardHome({
  profile,
  onStartNewGame,
  onLoadGame,
  onGoToCharacters,
  onGoToCampaigns,
  onGoToExplore,
  onGoToGuides,
  notificationsPending,
  onNotificationsClick,
  onQuickstartNewGame,
  onStartLastCampaign,
}: Props) {
  const handleStartNewGame = onStartNewGame ?? onQuickstartNewGame ?? (() => {})
  const handleLoadGame = onLoadGame ?? onStartLastCampaign ?? (() => {})

  const quickActions = [
    {
      label: 'Start New Game',
      icon: '⚔️',
      description: 'Create a new campaign and begin your adventure.',
      onClick: handleStartNewGame,
    },
    {
      label: 'Load a Game',
      icon: '📖',
      description: 'Continue from one of your existing campaigns.',
      onClick: handleLoadGame,
    },
    {
      label: 'Manage Characters',
      icon: '🧙',
      description: 'View, create, and import your characters.',
      onClick: onGoToCharacters,
    },
    {
      label: 'Manage Campaigns',
      icon: '🗺️',
      description: 'Configure campaigns, players, and documents.',
      onClick: onGoToCampaigns,
    },
    {
      label: 'Explore',
      icon: '🔭',
      description: 'Browse lore and world details discovered in your campaigns.',
      onClick: onGoToExplore,
    },
    {
      label: 'Guides',
      icon: '📜',
      description: 'Best practices and help for all TavernTails tools.',
      onClick: onGoToGuides,
    },
  ]

  return (
    <section className="dashboard-panel stack home-panel">
      <PageHeader
        title={`Welcome${profile?.name ? `, ${profile.name}` : ''}`}
        subtitle="What would you like to do today?"
        notificationsPending={notificationsPending}
        onNotificationsClick={onNotificationsClick}
      />

      <div className="home-quick-grid">
        {quickActions.map((action) => (
          <button
            key={action.label}
            className="home-qa-card"
            type="button"
            onClick={action.onClick}
          >
            <div className="home-qa-icon">{action.icon}</div>
            <div className="home-qa-label">{action.label}</div>
            <div className="home-qa-desc">{action.description}</div>
          </button>
        ))}
      </div>
    </section>
  )
}
