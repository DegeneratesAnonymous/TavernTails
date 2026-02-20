import React from 'react'

import './HomePage.css'

type Props = {
  onGetStarted: () => void
  onSignIn: () => void
  onSignUp: () => void
}

type QuickAction = {
  label: string
  description: string
  icon: string
  onClick: () => void
}

export default function HomePage({ onGetStarted, onSignIn, onSignUp }: Props) {
  const quickActions: QuickAction[] = [
    {
      label: 'Start New Game',
      description: 'Create a new campaign and jump into your adventure.',
      icon: '⚔️',
      onClick: onGetStarted,
    },
    {
      label: 'Load a Game',
      description: 'Pick up where you left off in one of your campaigns.',
      icon: '📖',
      onClick: onSignIn,
    },
    {
      label: 'Manage Characters',
      description: 'Create, import, and manage your character roster.',
      icon: '🧙',
      onClick: onSignIn,
    },
    {
      label: 'Manage Campaigns',
      description: 'Configure settings, players, and documents for your campaigns.',
      icon: '🗺️',
      onClick: onSignIn,
    },
    {
      label: 'Explore',
      description: 'Browse the lore and world details revealed through your adventures.',
      icon: '🔭',
      onClick: onSignIn,
    },
    {
      label: 'Guides',
      description: 'Learn best practices for tools and systems in TavernTails.',
      icon: '📜',
      onClick: onSignIn,
    },
  ]

  return (
    <div className="tt-home">
      <div className="tt-home-bg" />
      <div className="tt-home-content">
        <div className="tt-home-hero">
          <div className="tt-home-tag">TavernTails</div>
          <h1>Story-first AI GM, built for real tables.</h1>
          <p>
            Import characters, spin up campaigns, and keep the session moving with narrative cues,
            dice prompts, and live recap support.
          </p>
          <div className="tt-home-auth-actions">
            <button className="btn btn-secondary" type="button" onClick={onSignIn}>Sign In</button>
            <button className="btn btn-ghost" type="button" onClick={onSignUp}>Create Account</button>
          </div>
        </div>

        <div className="tt-home-quick-actions">
          {quickActions.map((action) => (
            <button
              key={action.label}
              className="tt-home-qa-card"
              type="button"
              onClick={action.onClick}
            >
              <div className="tt-home-qa-icon">{action.icon}</div>
              <div className="tt-home-qa-label">{action.label}</div>
              <div className="tt-home-qa-desc">{action.description}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
