import React, { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'

const SettingsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 0 1 1.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.559.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.894.149c-.424.07-.764.383-.929.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 0 1-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.398.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 0 1-.12-1.45l.527-.737c.25-.35.272-.806.108-1.204-.165-.397-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 0 1 .12-1.45l.773-.773a1.125 1.125 0 0 1 1.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894Z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
  </svg>
)

const NewIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
)


const AddPlayerIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M18 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0ZM3 19.235v-.11a6.375 6.375 0 0 1 12.75 0v.109A12.318 12.318 0 0 1 9.374 21c-2.331 0-4.512-.645-6.374-1.766Z" />
  </svg>
)

const RemovePlayerIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M22 10.5h-6m-2.25-4.125a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0ZM4 19.235v-.11a6.375 6.375 0 0 1 12.75 0v.109A12.318 12.318 0 0 1 10.374 21c-2.331 0-4.512-.645-6.374-1.766Z" />
  </svg>
)

const PlayersIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
  </svg>
)

const DocumentsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 3.75V16.5L12 14.25 7.5 16.5V3.75m9 0H18A2.25 2.25 0 0 1 20.25 6v12A2.25 2.25 0 0 1 18 20.25H6A2.25 2.25 0 0 1 3.75 18V6A2.25 2.25 0 0 1 6 3.75h1.5m9 0h-9" />
  </svg>
)

const AddDocumentIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m3.75 9v6m3-3H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
  </svg>
)

const RemoveDocumentIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m6.75 12H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
  </svg>
)

type Campaign = {
  id: string
  name: string
  description?: string | null
}

type CampaignSettings = {
  world_name: string
  setting_summary: string
  tone: string
  ruleset: string
  starting_level: number
  house_rules: string
}

type Player = {
  id: number
  username: string | null
  email: string | null
}

type GMAssignment = {
  gm_user_id: number | null
  gm_mode: string
}

type Props = {
  activeCampaignId: string | null
  activeCampaign: Campaign | null
  campaigns: Campaign[]
  onSelectCampaign: (id: string | null) => void
  onCampaignUpdated: () => Promise<void> | void
  onCreateCampaign: () => void

  onPlay?: () => Promise<void> | void
  playBusy?: boolean

  notificationsPending?: boolean
  onNotificationsClick?: () => void
  showAdminControls?: boolean
  onDeleteTestCampaigns?: () => void
}

const DEFAULT_SETTINGS: CampaignSettings = {
  world_name: '',
  setting_summary: '',
  tone: '',
  ruleset: '5e',
  starting_level: 1,
  house_rules: '',
}

function asString(v: any): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v)
}

function asNumber(v: any, fallback: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : fallback
}

export default function CampaignSetupView({
  activeCampaignId,
  activeCampaign,
  campaigns,
  onSelectCampaign,
  onCampaignUpdated,
  onCreateCampaign,
  onPlay,
  playBusy,
  notificationsPending,
  onNotificationsClick,
  showAdminControls = false,
  onDeleteTestCampaigns,
}: Props) {
  const [viewMode, setViewMode] = useState<'list' | 'settings' | 'documents' | 'players'>('list')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const [settings, setSettings] = useState<CampaignSettings>(DEFAULT_SETTINGS)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)
  
  const [players, setPlayers] = useState<Player[]>([])
  const [gmAssignment, setGmAssignment] = useState<GMAssignment>({ gm_user_id: null, gm_mode: 'ai' })
  const [loadingGM, setLoadingGM] = useState(false)

  const canEdit = Boolean(activeCampaignId)

  useEffect(() => {
    setName(asString(activeCampaign?.name))
    setDescription(asString(activeCampaign?.description))
  }, [activeCampaignId, activeCampaign?.name, activeCampaign?.description])

  useEffect(() => {
    if (!activeCampaignId && viewMode !== 'list') {
      setViewMode('list')
    }
  }, [activeCampaignId, viewMode])

  useEffect(() => {
    let canceled = false
    async function load() {
      if (!activeCampaignId) {
        setSettings(DEFAULT_SETTINGS)
        return
      }
      setLoading(true)
      setMessage(null)
      try {
        const res = await apiFetch(`/campaigns/${activeCampaignId}/settings`)
        if (!res.ok) {
          const err = await res.json().catch(() => null)
          throw new Error(err?.detail || 'Failed to load campaign settings')
        }
        const data = await res.json()
        const s = data?.settings
        const next: CampaignSettings = {
          world_name: asString(s?.world_name),
          setting_summary: asString(s?.setting_summary),
          tone: asString(s?.tone),
          ruleset: asString(s?.ruleset) || DEFAULT_SETTINGS.ruleset,
          starting_level: Math.max(1, Math.min(20, asNumber(s?.starting_level, DEFAULT_SETTINGS.starting_level))),
          house_rules: asString(s?.house_rules),
        }
        if (!canceled) setSettings(next)
      } catch (e: any) {
        if (!canceled) {
          setSettings(DEFAULT_SETTINGS)
          setMessage({ kind: 'error', text: e?.message || 'Failed to load campaign settings' })
        }
      } finally {
        if (!canceled) setLoading(false)
      }
    }
    load()
    return () => {
      canceled = true
    }
  }, [activeCampaignId])

  // Load players for the campaign
  useEffect(() => {
    let canceled = false
    async function loadPlayers() {
      if (!activeCampaignId) {
        setPlayers([])
        return
      }
      try {
        const res = await apiFetch(`/campaigns/${activeCampaignId}/players`)
        if (!res.ok) return
        const data = await res.json()
        if (!canceled && data?.players) {
          setPlayers(data.players)
        }
      } catch (e) {
        if (!canceled) setPlayers([])
      }
    }
    loadPlayers()
    return () => {
      canceled = true
    }
  }, [activeCampaignId])

  // Load GM assignment
  useEffect(() => {
    let canceled = false
    async function loadGM() {
      if (!activeCampaignId) {
        setGmAssignment({ gm_user_id: null, gm_mode: 'ai' })
        return
      }
      try {
        const res = await apiFetch(`/campaigns/${activeCampaignId}/gm`)
        if (!res.ok) return
        const data = await res.json()
        if (!canceled && data) {
          setGmAssignment({
            gm_user_id: data.gm_user_id,
            gm_mode: data.gm_mode || 'ai',
          })
        }
      } catch (e) {
        if (!canceled) setGmAssignment({ gm_user_id: null, gm_mode: 'ai' })
      }
    }
    loadGM()
    return () => {
      canceled = true
    }
  }, [activeCampaignId])

  const title = useMemo(() => {
    if (viewMode === 'list' || !activeCampaignId) return 'Manage Campaigns'
    const base = asString(activeCampaign?.name) || activeCampaignId
    const suffix = viewMode === 'settings' ? 'Settings' : viewMode === 'documents' ? 'Documents' : 'Players'
    return `Manage Campaigns: ${base} — ${suffix}`
  }, [activeCampaignId, activeCampaign?.name, viewMode])

  const openCampaignView = (campaignId: string, mode: 'settings' | 'documents' | 'players') => {
    onSelectCampaign(campaignId)
    setViewMode(mode)
  }

  async function handleGMChange(selectedValue: string) {
    if (!activeCampaignId) return
    
    setLoadingGM(true)
    setMessage(null)
    try {
      const gm_user_id = selectedValue === 'ai' ? null : Number(selectedValue)
      const res = await apiFetch(`/campaigns/${activeCampaignId}/gm`, {
        method: 'PUT',
        body: JSON.stringify({ gm_user_id }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to assign GM')
      }
      const data = await res.json()
      setGmAssignment({
        gm_user_id: data.gm_user_id,
        gm_mode: data.gm_mode || 'ai',
      })
      setMessage({ kind: 'info', text: 'GM assignment updated.' })
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.message || 'Failed to assign GM' })
    } finally {
      setLoadingGM(false)
    }
  }

  async function handleGenerateContent(type: 'npc' | 'location' | 'loot') {
    if (!activeCampaignId) return
    
    setMessage(null)
    try {
      const endpoint = `/generate/${type}`
      const res = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify({ campaign_id: activeCampaignId }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || `Failed to generate ${type}`)
      }
      const data = await res.json()
      // For now, just show a success message
      // In the future, this could open a modal with the generated content
      const itemName = data[type]?.name || 'Content'
      setMessage({ kind: 'info', text: `Generated: ${itemName}` })
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.message || `Failed to generate ${type}` })
    }
  }

  async function onSave() {
    if (!activeCampaignId) {
      setMessage({ kind: 'error', text: 'Select or create a campaign first.' })
      return
    }

    setSaving(true)
    setMessage(null)
    try {
      // Update campaign name/description
      const res1 = await apiFetch(`/campaigns/${activeCampaignId}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: name.trim() || undefined,
          description: description,
        }),
      })
      if (!res1.ok) {
        const err = await res1.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to save campaign details')
      }

      // Update campaign settings
      const res2 = await apiFetch(`/campaigns/${activeCampaignId}/settings`, {
        method: 'PUT',
        body: JSON.stringify({
          ...settings,
          starting_level: Math.max(1, Math.min(20, Number(settings.starting_level) || 1)),
        }),
      })
      if (!res2.ok) {
        const err = await res2.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to save campaign settings')
      }

      await onCampaignUpdated()
      setMessage({ kind: 'info', text: 'Campaign settings saved.' })
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.message || 'Failed to save campaign settings' })
    } finally {
      setSaving(false)
    }
  }

  const sortedCampaigns = useMemo(() => {
    return [...campaigns].sort((a, b) => a.name.localeCompare(b.name))
  }, [campaigns])

  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title={title}
        subtitle="Create, configure, and start/restart scenes."
        notificationsPending={notificationsPending}
        onNotificationsClick={onNotificationsClick}
        actions={
          showAdminControls && onDeleteTestCampaigns ? (
            <button className="btn btn-quiet" type="button" onClick={onDeleteTestCampaigns}>
              Delete test campaigns
            </button>
          ) : undefined
        }
      />

      <div className="row-wrap" style={{ gap: 16, alignItems: 'stretch' }}>
        <div style={{ minWidth: 260, flex: '1 1 260px' }}>
          <div className="card card-pad stack" style={{ gap: 10, background: 'var(--surface-dark)' }}>
            <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="muted">Campaigns</div>
              <button className="btn btn-secondary btn-sm btn-icon-only" type="button" onClick={onCreateCampaign} title="New Campaign" aria-label="New Campaign">
                <NewIcon />
              </button>
            </div>

            {sortedCampaigns.length === 0 ? (
              <div className="muted" style={{ fontSize: 13 }}>
                No campaigns yet. Create one to set the world and session settings.
              </div>
            ) : (
              <div className="stack" style={{ gap: 10 }}>
                {sortedCampaigns.map((campaign) => {
                  const isActive = String(campaign.id) === String(activeCampaignId)
                  return (
                    <div
                      key={campaign.id}
                      className="card"
                      style={{
                        padding: 10,
                        background: 'rgba(71,66,61,0.6)',
                        borderColor: isActive ? 'rgba(173,136,95,0.6)' : 'var(--tt-border)',
                      }}
                    >
                      <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {campaign.name}
                          </div>
                          {campaign.description ? (
                            <div className="muted" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {campaign.description}
                            </div>
                          ) : null}
                          {isActive ? <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Selected</div> : null}
                        </div>
                        <div className="row-wrap" style={{ gap: 6, justifyContent: 'flex-end' }}>
                          <button className="btn btn-secondary btn-sm btn-icon-only" type="button" onClick={() => openCampaignView(String(campaign.id), 'settings')} title="Settings" aria-label="Settings">
                            <SettingsIcon />
                          </button>
                          <button className="btn btn-secondary btn-sm btn-icon-only" type="button" onClick={() => openCampaignView(String(campaign.id), 'documents')} title="Documents" aria-label="Documents">
                            <DocumentsIcon />
                          </button>
                          <button className="btn btn-secondary btn-sm btn-icon-only" type="button" onClick={() => openCampaignView(String(campaign.id), 'players')} title="Players" aria-label="Players">
                            <PlayersIcon />
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        <div style={{ minWidth: 320, flex: '2 1 520px' }}>
          {viewMode === 'list' ? (
            <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
              <div className="muted" style={{ marginBottom: 8 }}>Select a campaign action</div>
              <div className="muted" style={{ fontSize: 13 }}>
                Choose Settings, Documents, or Players on the left to manage a campaign. Settings covers world details and tone.
              </div>
            </div>
          ) : !activeCampaignId ? (
            <div className="inline-alert">
              Select a campaign to view and edit settings, or create a new campaign.
            </div>
          ) : null}

          {message ? (
            <div className={`inline-alert ${message.kind === 'error' ? 'inline-alert-error' : ''}`}>
              {message.text}
            </div>
          ) : null}

          {viewMode === 'settings' ? (
            <>
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => setViewMode('list')}>
                ← Back to campaigns
              </button>

              <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
                <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                  <div className="muted">Campaign details</div>
                  <div className="row-wrap" style={{ gap: 8 }}>
                    {onPlay && activeCampaignId ? (
                      <button className="btn" type="button" disabled={!canEdit || Boolean(playBusy)} onClick={onPlay}>
                        {playBusy ? 'Starting…' : 'Start / Restart Scene'}
                      </button>
                    ) : null}
                    <button
                      className="btn btn-icon-only"
                      type="button"
                      disabled={!canEdit || saving}
                      onClick={onSave}
                      title={saving ? 'Saving…' : 'Save'}
                      aria-label={saving ? 'Saving…' : 'Save'}
                    >
                      <SettingsIcon />
                    </button>
                  </div>
                </div>

                <div className="stack" style={{ gap: 10, marginTop: 10 }}>
                  <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Campaign name" disabled={!canEdit} />
                  <textarea
                    className="input"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Description (optional)"
                    rows={3}
                    disabled={!canEdit}
                  />
                </div>
              </div>

              <div className="card card-pad" style={{ opacity: loading ? 0.7 : 1, background: 'var(--surface-dark)' }}>
                <div className="stack" style={{ gap: 10 }}>
                  <div className="muted">World & game settings</div>

                  <div className="stack" style={{ gap: 6 }}>
                    <label className="muted" style={{ fontSize: 13 }}>
                      Game Master
                    </label>
                    <select
                      className="input"
                      value={gmAssignment.gm_user_id?.toString() || 'ai'}
                      onChange={(e) => handleGMChange(e.target.value)}
                      disabled={!canEdit || loadingGM}
                    >
                      <option value="ai">AI Game Master</option>
                      {players.map((player) => (
                        <option key={player.id} value={player.id.toString()}>
                          {player.username || player.email || `Player ${player.id}`}
                        </option>
                      ))}
                    </select>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {gmAssignment.gm_mode === 'ai' 
                        ? 'AI will actively narrate and drive the campaign.' 
                        : 'Selected player will run the session. AI provides note-taking and organization.'}
                    </div>
                  </div>

                  <input
                    className="input"
                    value={settings.world_name}
                    onChange={(e) => setSettings((prev) => ({ ...prev, world_name: e.target.value }))}
                    placeholder="World name (e.g. Eldervale)"
                    disabled={!canEdit}
                  />

                  <textarea
                    className="input"
                    value={settings.setting_summary}
                    onChange={(e) => setSettings((prev) => ({ ...prev, setting_summary: e.target.value }))}
                    placeholder="Setting summary (factions, hooks, vibe)"
                    rows={4}
                    disabled={!canEdit}
                  />

                  <div className="row-wrap">
                    <select
                      className="input"
                      value={settings.tone}
                      onChange={(e) => setSettings((prev) => ({ ...prev, tone: e.target.value }))}
                      disabled={!canEdit}
                      aria-disabled={!canEdit}
                    >
                      <option value="">Tone…</option>
                      <option value="heroic">Heroic</option>
                      <option value="grim">Grim</option>
                      <option value="dark-fantasy">Dark fantasy</option>
                      <option value="comedy">Comedy</option>
                      <option value="horror">Horror</option>
                    </select>

                    <input
                      className="input"
                      type="number"
                      min={1}
                      max={20}
                      value={settings.starting_level}
                      onChange={(e) => setSettings((prev) => ({ ...prev, starting_level: asNumber(e.target.value, 1) }))}
                      disabled={!canEdit}
                    />
                  </div>

                  <textarea
                    className="input"
                    value={settings.house_rules}
                    onChange={(e) => setSettings((prev) => ({ ...prev, house_rules: e.target.value }))}
                    placeholder="House rules / table rules"
                    rows={3}
                    disabled={!canEdit}
                  />

                  <div className="muted" style={{ fontSize: 12 }}>
                    These settings are stored on the campaign and can be used by agents later to keep narration/rules consistent.
                  </div>
                </div>
              </div>

              {gmAssignment.gm_mode === 'player' && (
                <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
                  <div className="stack" style={{ gap: 10 }}>
                    <div className="muted">GM Generative Tools</div>
                    <div className="muted" style={{ fontSize: 13 }}>
                      Generate content that fits your campaign setting and tone.
                    </div>
                    <div className="row-wrap" style={{ gap: 8 }}>
                      <button 
                        className="btn btn-secondary" 
                        type="button"
                        onClick={() => handleGenerateContent('npc')}
                        disabled={!canEdit}
                      >
                        Generate NPC
                      </button>
                      <button 
                        className="btn btn-secondary" 
                        type="button"
                        onClick={() => handleGenerateContent('location')}
                        disabled={!canEdit}
                      >
                        Generate Location
                      </button>
                      <button 
                        className="btn btn-secondary" 
                        type="button"
                        onClick={() => handleGenerateContent('loot')}
                        disabled={!canEdit}
                      >
                        Generate Loot
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : null}

          {viewMode === 'documents' ? (
            <>
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => setViewMode('list')}>
                ← Back to campaigns
              </button>
              <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Shared Documents Library</div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Documents here are shared across campaigns (tables, lore, guides, and system references).
                </div>
                <div className="row-wrap" style={{ gap: 8 }}>
                  <button className="btn btn-icon-only" type="button" title="Upload Document" aria-label="Upload Document">
                    <AddDocumentIcon />
                  </button>
                  <button className="btn btn-secondary btn-icon-only" type="button" title="Create Folder" aria-label="Create Folder">
                    <NewIcon />
                  </button>
                  <button className="btn btn-secondary btn-icon-only" type="button" title="Remove Document" aria-label="Remove Document">
                    <RemoveDocumentIcon />
                  </button>
                </div>
                <div className="inline-alert" style={{ marginTop: 12 }}>
                  No documents yet. Upload a PDF or document file to build your library.
                </div>
              </div>
            </>
          ) : null}

          {viewMode === 'players' ? (
            <>
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => setViewMode('list')}>
                ← Back to campaigns
              </button>
              <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Players</div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Manage access to this campaign. (Invite and role controls coming next.)
                </div>
                <div className="row-wrap" style={{ gap: 8, marginBottom: 12 }}>
                  <button className="btn btn-icon-only" type="button" title="Add Player" aria-label="Add Player">
                    <AddPlayerIcon />
                  </button>
                  <button className="btn btn-secondary btn-icon-only" type="button" title="Remove Player" aria-label="Remove Player">
                    <RemovePlayerIcon />
                  </button>
                </div>
                <div className="inline-alert">No players listed yet.</div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </section>
  )
}
