import React, { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'

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
  player_run_mode: boolean
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
}

const DEFAULT_SETTINGS: CampaignSettings = {
  world_name: '',
  setting_summary: '',
  tone: '',
  ruleset: '5e',
  starting_level: 1,
  house_rules: '',
  player_run_mode: false,
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
}: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const [settings, setSettings] = useState<CampaignSettings>(DEFAULT_SETTINGS)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)

  const canEdit = Boolean(activeCampaignId)

  useEffect(() => {
    setName(asString(activeCampaign?.name))
    setDescription(asString(activeCampaign?.description))
  }, [activeCampaignId, activeCampaign?.name, activeCampaign?.description])

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
          player_run_mode: Boolean(s?.player_run_mode),
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

  const title = useMemo(() => {
    if (!activeCampaignId) return 'Manage Campaigns'
    return `Manage Campaigns: ${asString(activeCampaign?.name) || activeCampaignId}`
  }, [activeCampaignId, activeCampaign?.name])

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
      />

      <div className="row-wrap" style={{ gap: 16, alignItems: 'stretch' }}>
        <div style={{ minWidth: 260, flex: '1 1 260px' }}>
          <div className="card card-pad stack" style={{ gap: 10 }}>
            <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="muted">Campaigns</div>
              <button className="btn btn-secondary btn-sm" type="button" onClick={onCreateCampaign}>
                New Campaign
              </button>
            </div>

            {sortedCampaigns.length === 0 ? (
              <div className="muted" style={{ fontSize: 13 }}>
                No campaigns yet. Create one to set the world and session settings.
              </div>
            ) : (
              <div className="stack" style={{ gap: 6 }}>
                {sortedCampaigns.map((campaign) => {
                  const isActive = String(campaign.id) === String(activeCampaignId)
                  return (
                    <button
                      key={campaign.id}
                      type="button"
                      className="btn btn-quiet"
                      style={{
                        textAlign: 'left',
                        justifyContent: 'space-between',
                        background: isActive ? 'rgba(255,255,255,0.06)' : 'transparent',
                      }}
                      onClick={() => onSelectCampaign(String(campaign.id))}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {campaign.name}
                        </div>
                        {campaign.description ? (
                          <div className="muted" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {campaign.description}
                          </div>
                        ) : null}
                      </div>
                      {isActive ? <span className="muted" style={{ fontSize: 12 }}>Selected</span> : null}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        <div style={{ minWidth: 320, flex: '2 1 520px' }}>
          {!activeCampaignId ? (
            <div className="inline-alert">
              Select a campaign to view and edit settings, or create a new campaign.
            </div>
          ) : null}

          {message ? (
            <div className={`inline-alert ${message.kind === 'error' ? 'inline-alert-error' : ''}`}>
              {message.text}
            </div>
          ) : null}

          <div className="card card-pad">
            <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
              <div className="muted">Campaign details</div>
              <div className="row-wrap" style={{ gap: 8 }}>
                {onPlay && activeCampaignId ? (
                  <button className="btn" type="button" disabled={!canEdit || Boolean(playBusy)} onClick={onPlay}>
                    {playBusy ? 'Starting…' : 'Start / Restart Scene'}
                  </button>
                ) : null}
                <button className="btn" type="button" disabled={!canEdit || saving} onClick={onSave}>
                  {saving ? 'Saving…' : 'Save'}
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

          <div className="card card-pad" style={{ opacity: loading ? 0.7 : 1 }}>
            <div className="stack" style={{ gap: 10 }}>
              <div className="muted">World & game settings</div>

              <label className="row" style={{ gap: 8, alignItems: 'center', userSelect: 'none' }}>
                <input
                  type="checkbox"
                  checked={settings.player_run_mode}
                  onChange={(e) => setSettings((prev) => ({ ...prev, player_run_mode: e.target.checked }))}
                  disabled={!canEdit}
                />
                <span>
                  Player‑run session mode (AI optional). Keeps notes/NPC organization active.
                </span>
              </label>

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
                  value={settings.ruleset}
                  onChange={(e) => setSettings((prev) => ({ ...prev, ruleset: e.target.value }))}
                  disabled={!canEdit}
                  aria-disabled={!canEdit}
                >
                  <option value="5e">D&D 5e</option>
                  <option value="pf2">Pathfinder 2e</option>
                  <option value="osr">OSR</option>
                  <option value="other">Other</option>
                </select>

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
        </div>
      </div>
    </section>
  )
}
