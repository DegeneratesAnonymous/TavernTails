import React, { useCallback, useEffect, useMemo, useState } from 'react'

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

type SessionZeroData = {
  session_zero?: any
  campaign_interpretation?: any
  campaign_contract?: any
  confirmed?: boolean
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
  ruleset: '',
  starting_level: 1,
  house_rules: '',
}

/** Known structured ruleset options surfaced in the UI. */
const RULESET_OPTIONS = [
  { value: 'srd-5.2', label: 'D&D 5e — SRD 5.2 (CC-BY-4.0)' },
  { value: 'pathfinder-2e', label: 'Pathfinder 2e (Paizo / ORC License)' },
  { value: 'osr', label: 'OSR / Old-School Essentials' },
  { value: 'custom', label: 'Custom / Homebrew' },
]

/** Return the select value: the matching known id or 'custom' for freetext. */
function rulesetSelectValue(ruleset: string): string {
  if (!ruleset) { return '' }
  return RULESET_OPTIONS.some((o) => o.value === ruleset) ? ruleset : 'custom'
}

function asString(v: any): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v)
}

function asNumber(v: any, fallback: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : fallback
}

function listText(value: any, fallback = 'Not specified'): string {
  if (Array.isArray(value)) return value.filter(Boolean).join(', ') || fallback
  if (typeof value === 'string') return value || fallback
  return fallback
}

function policyLabel(value: any, key: string, fallback = 'Not specified'): string {
  const raw = value?.[key]
  if (typeof raw === 'string') return raw.replace(/_/g, ' ')
  return fallback
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
  const [sessionZero, setSessionZero] = useState<SessionZeroData | null>(null)
  const [sessionZeroLoading, setSessionZeroLoading] = useState(false)
  const [sessionZeroBusy, setSessionZeroBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)

  const canEdit = Boolean(activeCampaignId)

  const loadSessionZero = useCallback(async () => {
    if (!activeCampaignId) {
      setSessionZero(null)
      return null
    }
    setSessionZeroLoading(true)
    try {
      const res = await apiFetch(`/campaigns/${activeCampaignId}/session-zero`)
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to load Session Zero')
      }
      const data = await res.json().catch(() => ({} as SessionZeroData))
      setSessionZero(data)
      return data
    } finally {
      setSessionZeroLoading(false)
    }
  }, [activeCampaignId])

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

  useEffect(() => {
    void loadSessionZero().catch(() => {
      setSessionZero(null)
    })
  }, [loadSessionZero])

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
      await loadSessionZero().catch(() => null)
      setMessage({ kind: 'info', text: 'Saved.' })
    } finally {
      setSaving(false)
    }
  }

  async function saveAndPlay() {
    try {
      await saveAll()
      if (activeCampaignId && !sessionZero?.confirmed) {
        await confirmSessionZero()
      }
      await onPlay()
      onClose()
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.message || 'Failed to start playing' })
    }
  }

  async function confirmSessionZero() {
    if (!activeCampaignId) return
    setSessionZeroBusy(true)
    setMessage(null)
    try {
      const res = await apiFetch(`/campaigns/${activeCampaignId}/contract/confirm`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to confirm Session Zero')
      }
      await loadSessionZero()
      setMessage({ kind: 'info', text: 'Session Zero confirmed.' })
    } finally {
      setSessionZeroBusy(false)
    }
  }

  async function regenerateSessionZero() {
    if (!activeCampaignId) return
    setSessionZeroBusy(true)
    setMessage(null)
    try {
      const res = await apiFetch(`/campaigns/${activeCampaignId}/interpretation/regenerate`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to regenerate Session Zero')
      }
      await loadSessionZero()
      setMessage({ kind: 'info', text: 'Session Zero regenerated.' })
    } finally {
      setSessionZeroBusy(false)
    }
  }

  const sessionZeroSummary = sessionZero?.session_zero?.summary || {}
  const sessionZeroHooks = sessionZero?.session_zero?.character_hooks || []
  const campaignContract = sessionZero?.campaign_contract || {}
  const campaignInterpretation = sessionZero?.campaign_interpretation || {}

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
                value={rulesetSelectValue(settings.ruleset)}
                onChange={(e) => {
                  const v = e.target.value
                  if (v !== 'custom') {
                    setSettings((prev) => ({ ...prev, ruleset: v }))
                  } else {
                    setSettings((prev) => ({ ...prev, ruleset: '' }))
                  }
                }}
                disabled={!canEdit}
                aria-disabled={!canEdit}
              >
                <option value="">Select ruleset…</option>
                {RULESET_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>

              {rulesetSelectValue(settings.ruleset) === 'custom' && (
                <input
                  className="input"
                  value={settings.ruleset}
                  onChange={(e) => setSettings((prev) => ({ ...prev, ruleset: e.target.value }))}
                  placeholder="Describe your ruleset (e.g. Knave 2e, GURPS)"
                  disabled={!canEdit}
                  aria-disabled={!canEdit}
                />
              )}

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
            <div style={{ fontWeight: 750 }}>Session Zero Review</div>
            <div className="muted">Confirm how TavernTails understands this campaign before play begins.</div>

            <div className="card card-pad stack" style={{ gap: 10, background: 'rgba(0,0,0,0.18)' }}>
              {sessionZeroLoading ? (
                <div className="muted">Loading interpretation…</div>
              ) : (
                <>
                  <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 750 }}>Campaign Contract</div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {sessionZero?.confirmed ? 'Confirmed' : 'Needs confirmation'}
                      </div>
                    </div>
                    <div className="row-wrap" style={{ justifyContent: 'flex-end' }}>
                      <button className="btn btn-secondary" type="button" disabled={!canEdit || sessionZeroBusy} onClick={regenerateSessionZero}>
                        Regenerate
                      </button>
                      <button className="btn" type="button" disabled={!canEdit || sessionZeroBusy || sessionZero?.confirmed} onClick={confirmSessionZero}>
                        {sessionZeroBusy ? 'Working…' : sessionZero?.confirmed ? 'Confirmed' : 'Confirm'}
                      </button>
                    </div>
                  </div>

                  <div className="wizard-review-grid">
                    <div className="wizard-review-row">
                      <span className="wizard-review-label">Tone</span>
                      <span className="wizard-review-value">{policyLabel(sessionZeroSummary, 'tone')}</span>
                    </div>
                    <div className="wizard-review-row">
                      <span className="wizard-review-label">Creation Flow</span>
                      <span className="wizard-review-value">{policyLabel(campaignInterpretation, 'creation_posture')}</span>
                    </div>
                    <div className="wizard-review-row">
                      <span className="wizard-review-label">Canon</span>
                      <span className="wizard-review-value">{policyLabel(campaignContract?.canon_policy, 'mode')}</span>
                    </div>
                    <div className="wizard-review-row">
                      <span className="wizard-review-label">AI Creativity</span>
                      <span className="wizard-review-value">{policyLabel(campaignContract?.ai_creativity_policy, 'level')}</span>
                    </div>
                    <div className="wizard-review-row">
                      <span className="wizard-review-label">Play Pillars</span>
                      <span className="wizard-review-value">{listText(campaignInterpretation?.primary_play_pillars)}</span>
                    </div>
                    <div className="wizard-review-row">
                      <span className="wizard-review-label">UI Emphasis</span>
                      <span className="wizard-review-value">{listText(campaignContract?.ui_policy?.primary_widgets)}</span>
                    </div>
                  </div>

                  {sessionZeroHooks.length ? (
                    <div className="stack" style={{ gap: 6 }}>
                      <div style={{ fontWeight: 700, fontSize: 13 }}>Backstory Hooks</div>
                      {sessionZeroHooks.slice(0, 4).map((item: any, idx: number) => (
                        <div key={`${item?.character || idx}`} className="muted" style={{ fontSize: 12 }}>
                          <strong>{item?.character || 'Character'}:</strong> {listText(item?.hooks, 'No hooks yet')}
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {Array.isArray(sessionZero?.session_zero?.low_confidence_items) && sessionZero.session_zero.low_confidence_items.length ? (
                    <div className="inline-alert">
                      {sessionZero.session_zero.low_confidence_items.length} assumption(s) should be reviewed in campaign settings.
                    </div>
                  ) : null}
                </>
              )}
            </div>

            <div className="muted">When you start, TavernTails will generate the opening scene using this contract.</div>
            <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
              <button className="btn btn-secondary" type="button" onClick={() => setStep('world')}>
                Back
              </button>
              <button className="btn" type="button" disabled={!canEdit || Boolean(playBusy) || sessionZeroBusy} onClick={saveAndPlay}>
                {playBusy ? 'Starting…' : 'Start Campaign'}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
