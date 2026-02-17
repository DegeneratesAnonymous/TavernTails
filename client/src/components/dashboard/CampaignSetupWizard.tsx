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
}

type Props = {
  activeCampaignId: string | null
  activeCampaign: Campaign | null
  onCampaignUpdated: () => Promise<void> | void

  onPlay: () => Promise<void> | void
  playBusy?: boolean

  onClose: () => void
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

type StepKey = 'details' | 'world' | 'ready'

export default function CampaignSetupWizard({
  activeCampaignId,
  activeCampaign,
  onCampaignUpdated,
  onPlay,
  playBusy,
  onClose,
}: Props) {
  const [step, setStep] = useState<StepKey>('details')

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
        const data = await res.json().catch(() => ({} as any))
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

  const stepIndex = useMemo(() => {
    if (step === 'details') return 0
    if (step === 'world') return 1
    return 2
  }, [step])

  async function saveAll() {
    if (!activeCampaignId) {
      setMessage({ kind: 'error', text: 'Select or create a campaign first.' })
      return
    }

    setSaving(true)
    setMessage(null)
    try {
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
      setMessage({ kind: 'info', text: 'Saved.' })
    } finally {
      setSaving(false)
    }
  }

  async function saveAndPlay() {
    try {
      await saveAll()
      await onPlay()
      onClose()
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.message || 'Failed to start playing' })
    }
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <PageHeader
        title="Campaign Setup"
        subtitle={
          'One-time setup. Once your first scene starts, this disappears.'
        }
        actions={
          <>
            <button className="btn btn-secondary" type="button" onClick={onClose}>
              Back to Menu
            </button>
          </>
        }
      />

      <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
        <div className="muted" style={{ fontSize: 12 }}>
          Step {stepIndex + 1} of 3
        </div>
        <div className="row-wrap" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" type="button" disabled={!canEdit || saving || Boolean(playBusy)} onClick={saveAll}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button className="btn" type="button" disabled={!canEdit || Boolean(playBusy)} onClick={saveAndPlay}>
            {playBusy ? 'Starting…' : 'Save & Start'}
          </button>
        </div>
      </div>

      {message ? (
        <div className={`inline-alert ${message.kind === 'error' ? 'inline-alert-error' : ''}`}>
          {message.text}
        </div>
      ) : null}

      {!activeCampaignId ? (
        <div className="inline-alert inline-alert-error">
          No campaign selected. Create/select a campaign first.
        </div>
      ) : null}

      <div className="card card-pad" style={{ opacity: loading ? 0.7 : 1 }}>
        {step === 'details' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div style={{ fontWeight: 750 }}>Campaign details</div>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Campaign name" disabled={!canEdit} />
            <textarea
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description (optional)"
              rows={3}
              disabled={!canEdit}
            />
            <div className="row-wrap" style={{ justifyContent: 'flex-end' }}>
              <button className="btn" type="button" disabled={!canEdit} onClick={() => setStep('world')}>
                Next
              </button>
            </div>
          </div>
        ) : null}

        {step === 'world' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div style={{ fontWeight: 750 }}>World & game settings</div>

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

            <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
              <button className="btn btn-secondary" type="button" onClick={() => setStep('details')}>
                Back
              </button>
              <button className="btn" type="button" onClick={() => setStep('ready')}>
                Next
              </button>
            </div>
          </div>
        ) : null}

        {step === 'ready' ? (
          <div className="stack" style={{ gap: 10 }}>
            <div style={{ fontWeight: 750 }}>Ready</div>
            <div className="muted">
              When you click Start, TavernTails will generate your opening scene and begin the campaign.
            </div>
            <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
              <button className="btn btn-secondary" type="button" onClick={() => setStep('world')}>
                Back
              </button>
              <button className="btn" type="button" disabled={!canEdit || Boolean(playBusy)} onClick={saveAndPlay}>
                {playBusy ? 'Starting…' : 'Start Campaign'}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
