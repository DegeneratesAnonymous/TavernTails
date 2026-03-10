import React from 'react'
import { Sword, BookOpen, Wand2, Map, Telescope, Scroll } from 'lucide-react'
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
      icon: <Sword size={28} />,
      description: 'Create a new campaign and begin your adventure.',
      onClick: handleStartNewGame,
    },
    {
      label: 'Load a Game',
      icon: <BookOpen size={28} />,
      description: 'Continue from one of your existing campaigns.',
      onClick: handleLoadGame,
    },
    {
      label: 'Manage Characters',
      icon: <Wand2 size={28} />,
      description: 'View, create, and import your characters.',
      onClick: onGoToCharacters,
    },
    {
      label: 'Manage Campaigns',
      icon: <Map size={28} />,
      description: 'Configure campaigns, players, and documents.',
      onClick: onGoToCampaigns,
    },
    {
      label: 'Explore',
      icon: <Telescope size={28} />,
      description: 'Browse lore and world details discovered in your campaigns.',
      onClick: onGoToExplore,
    },
    {
      label: 'Guides',
      icon: <Scroll size={28} />,
      description: 'Best practices and help for all TavernTails tools.',
      onClick: onGoToGuides,
    },
  ]

  return (
    <section className="dashboard-panel stack home-panel">
      <PageHeader
        title={`Welcome${profile?.name ? `, ${profile.name}` : ''}`}
        subtitle="What would you like to do today?"
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
