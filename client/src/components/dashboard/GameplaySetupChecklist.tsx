import React from 'react'

import EmptyState from '../ui/EmptyState'

type Props = {
  campaignCount: number
  activeCampaignId: string | null
  activeCampaignName: string | null
  sessionCount: number
  activeSessionId: string | null
  characterCount: number
  activeCharacterId: number | null

  onCreateCampaign: () => void
  onCreateSession: () => Promise<void>
  onGoToCampaignSetup: () => void
  onGoToCharacters: () => void
  onGoToImport: () => void
  onGoToCreateCharacter: () => void
  onQuickstart?: () => void
}

export default function GameplaySetupChecklist({
  campaignCount,
  activeCampaignId,
  activeCampaignName,
  sessionCount,
  activeSessionId,
  characterCount,
  activeCharacterId,
  onCreateCampaign,
  onCreateSession,
  onGoToCampaignSetup,
  onGoToCharacters,
  onGoToImport,
  onGoToCreateCharacter,
  onQuickstart,
}: Props) {
  const hasCampaign = Boolean(activeCampaignId)
  const hasSession = Boolean(activeSessionId)
  const hasCharacter = activeCharacterId !== null

  if (!hasCampaign && campaignCount === 0) {
    return (
      <EmptyState
        title="Welcome — let’s set up your first campaign"
        description="Create a campaign to hold sessions, characters, and your world setup."
        actions={
          <>
            <button className="btn" type="button" onClick={onCreateCampaign}>
              Create campaign
            </button>
            {onQuickstart && (
              <button className="btn btn-secondary" type="button" onClick={onQuickstart}>
                Quickstart (auto-playtest)
              </button>
            )}
            <button className="btn btn-secondary" type="button" onClick={onGoToCampaignSetup}>
              Campaign setup
            </button>
          </>
        }
      />
    )
  }

  if (!hasCampaign) {
    return (
      <EmptyState
        title="Pick a campaign to start"
        description="Select a campaign in the top toolbar, or create a new one."
        actions={
          <>
            <button className="btn" type="button" onClick={onCreateCampaign}>
              New campaign
            </button>
            {onQuickstart && (
              <button className="btn btn-secondary" type="button" onClick={onQuickstart}>
                Quickstart (auto-playtest)
              </button>
            )}
            <button className="btn btn-secondary" type="button" onClick={onGoToCampaignSetup}>
              Campaign setup
            </button>
          </>
        }
      />
    )
  }

  if (hasCampaign && !hasSession && sessionCount === 0) {
    return (
      <EmptyState
        title={`Campaign ready: ${activeCampaignName || activeCampaignId}`}
        description="Next step: create a session to play in."
        actions={
          <>
            <button className="btn" type="button" onClick={onCreateSession}>
              Create session
            </button>
            {onQuickstart && (
              <button className="btn btn-secondary" type="button" onClick={onQuickstart}>
                Quickstart (auto-bootstrap)
              </button>
            )}
            <button className="btn btn-secondary" type="button" onClick={onGoToCampaignSetup}>
              Configure campaign
            </button>
          </>
        }
      />
    )
  }

  if (hasCampaign && !hasSession) {
    return (
      <EmptyState
        title="Pick a session to play"
        description="Select a session in the top toolbar, or create a new one for this campaign."
        actions={
          <>
            <button className="btn" type="button" onClick={onCreateSession}>
              New session
            </button>
            {onQuickstart && (
              <button className="btn btn-secondary" type="button" onClick={onQuickstart}>
                Quickstart (auto-bootstrap)
              </button>
            )}
            <button className="btn btn-secondary" type="button" onClick={onGoToCampaignSetup}>
              Campaign setup
            </button>
          </>
        }
      />
    )
  }

  if (!hasCharacter && characterCount === 0) {
    return (
      <EmptyState
        title="Add your first character"
        description="Create a quick character, import JSON, or store a D&D Beyond link as a reference."
        actions={
          <>
            <button className="btn" type="button" onClick={onGoToCreateCharacter}>
              Create character
            </button>
            <button className="btn btn-secondary" type="button" onClick={onGoToImport}>
              Import character
            </button>
          </>
        }
      />
    )
  }

  if (!hasCharacter) {
    return (
      <EmptyState
        title="Pick a character for this session"
        description="Select a character in the top toolbar to unlock combat stats and richer play." 
        actions={
          <>
            <button className="btn" type="button" onClick={onGoToCharacters}>
              Manage characters
            </button>
            <button className="btn btn-secondary" type="button" onClick={onGoToImport}>
              Import character
            </button>
          </>
        }
      />
    )
  }

  return null
}
