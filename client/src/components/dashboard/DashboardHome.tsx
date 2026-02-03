import React from 'react'

import PageHeader from '../ui/PageHeader'

type Props = {
  profile: any
  lastSessionLabel?: string | null
  onQuickJoin: () => void
  onGoToCampaigns: () => void
  onGoToCharacters: () => void
  onGoToImport: () => void
}

export default function DashboardHome({
  profile,
  lastSessionLabel,
  onQuickJoin,
  onGoToCampaigns,
  onGoToCharacters,
  onGoToImport,
}: Props) {
  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="Home"
        subtitle={`Welcome${profile?.name ? `, ${profile.name}` : ''}. Pick up where you left off or jump into prep.`}
      />

      <div className="card card-pad">
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Quick actions</div>
        <div className="row-wrap" style={{ gap: 10 }}>
          <button className="btn" type="button" onClick={onQuickJoin}>
            Quick-join{lastSessionLabel ? `: ${lastSessionLabel}` : ''}
          </button>
          <button className="btn btn-secondary" type="button" onClick={onGoToCampaigns}>Manage Campaigns</button>
          <button className="btn btn-secondary" type="button" onClick={onGoToCharacters}>Manage Characters</button>
          <button className="btn btn-ghost" type="button" onClick={onGoToImport}>Import Character</button>
        </div>
      </div>

      <div className="card card-pad">
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Getting started</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Start a campaign, import your characters, and then jump into gameplay. You can always return here from the sidebar.
        </div>
      </div>
    </section>
  )
}
