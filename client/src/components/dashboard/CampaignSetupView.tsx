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

type Campaign = {
  id: string
  name: string
  description?: string | null
}

type Character = {
  id: number
  name: string
  class_name?: string | null
  level?: number
  sheet?: any
}

type CampaignSettings = {
  world_name: string
  setting_summary: string
  genre: string
  tone: string
  ruleset: string
  starting_level: number
  house_rules: string
  player_run_mode: boolean
}

type CampaignVariables = {
  themes: string[]
  pacing: string
  narrative_style: string
  factions: FactionEntry[]
  npc_archetypes: string[]
  naming_style: string
  content_rating: string
}

type FactionEntry = {
  name: string
  alignment: string
  goals: string[]
  members: string[]
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
  characters?: Character[]
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
  genre: 'fantasy',
  tone: '',
  ruleset: 'custom',
  starting_level: 1,
  house_rules: '',
  player_run_mode: false,
}

const DEFAULT_VARIABLES: CampaignVariables = {
  themes: [],
  pacing: 'moderate',
  narrative_style: 'balanced',
  factions: [],
  npc_archetypes: [],
  naming_style: '',
  content_rating: 'pg-13',
}

function asString(v: any): string {
  return typeof v === 'string' ? v : v == null ? '' : String(v)
}

function asNumber(v: any, fallback: number): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : fallback
}

function parseThemesInput(raw: string): string[] {
  return raw.split(',').map((t) => t.trim()).filter(Boolean)
}

export default function CampaignSetupView({
  activeCampaignId,
  activeCampaign,
  campaigns,
  characters = [],
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
  const [variables, setVariables] = useState<CampaignVariables>(DEFAULT_VARIABLES)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [message, setMessage] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)
  
  const [players, setPlayers] = useState<Player[]>([])
  const [gmAssignment, setGmAssignment] = useState<GMAssignment>({ gm_user_id: null, gm_mode: 'ai' })
  const [loadingGM, setLoadingGM] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviting, setInviting] = useState(false)
  const [inviteMatches, setInviteMatches] = useState<Array<{id?: number; username?: string | null; email?: string | null; name?: string | null}>>([])
  const [inviteMatchBusy, setInviteMatchBusy] = useState(false)

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
          genre: asString(s?.genre) || DEFAULT_SETTINGS.genre,
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

  // Username search for invite autocomplete
  useEffect(() => {
    let canceled = false
    const raw = inviteEmail.trim()
    if (!raw || raw.includes('@') || raw.length < 2) {
      setInviteMatches([])
      return
    }
    setInviteMatchBusy(true)
    const id = window.setTimeout(async () => {
      try {
        const res = await apiFetch(`/users/search?q=${encodeURIComponent(raw)}&limit=8`)
        if (!res.ok) throw new Error('search failed')
        const data = await res.json().catch(() => null)
        const results = Array.isArray(data?.results) ? data.results : []
        if (!canceled) setInviteMatches(results)
      } catch {
        if (!canceled) setInviteMatches([])
      } finally {
        if (!canceled) setInviteMatchBusy(false)
      }
    }, 250)
    return () => {
      canceled = true
      window.clearTimeout(id)
    }
  }, [inviteEmail])

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

  // Load campaign variables
  useEffect(() => {
    let canceled = false
    async function loadVariables() {
      if (!activeCampaignId) {
        setVariables(DEFAULT_VARIABLES)
        return
      }
      try {
        const res = await apiFetch(`/campaigns/${activeCampaignId}/variables`)
        if (!res.ok) return
        const data = await res.json()
        const v = data?.variables
        if (!canceled && v) {
          setVariables({
            themes: Array.isArray(v.themes) ? v.themes : DEFAULT_VARIABLES.themes,
            pacing: asString(v.pacing) || DEFAULT_VARIABLES.pacing,
            narrative_style: asString(v.narrative_style) || DEFAULT_VARIABLES.narrative_style,
            factions: Array.isArray(v.factions) ? v.factions : DEFAULT_VARIABLES.factions,
            npc_archetypes: Array.isArray(v.npc_archetypes) ? v.npc_archetypes : DEFAULT_VARIABLES.npc_archetypes,
            naming_style: asString(v.naming_style),
            content_rating: asString(v.content_rating) || DEFAULT_VARIABLES.content_rating,
          })
        }
      } catch (e) {
        if (!canceled) setVariables(DEFAULT_VARIABLES)
      }
    }
    loadVariables()
    return () => {
      canceled = true
    }
  }, [activeCampaignId])

  const title = useMemo(() => {
    if (viewMode === 'list' || !activeCampaignId) return 'Manage Campaigns'
    const base = asString(activeCampaign?.name) || activeCampaignId
    const suffix =
      viewMode === 'settings'
        ? 'Settings'
        : viewMode === 'documents'
        ? 'Documents'
        : 'Players'
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

  async function handleDeleteCampaign() {
    if (!activeCampaignId) return
    if (!window.confirm(`Delete campaign "${activeCampaign?.name ?? activeCampaignId}"? This cannot be undone.`)) return
    setDeleting(true)
    setMessage(null)
    try {
      const res = await apiFetch(`/campaigns/${activeCampaignId}`, { method: 'DELETE' })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to delete campaign')
      }
      onSelectCampaign(null)
      setViewMode('list')
      await onCampaignUpdated()
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.message || 'Failed to delete campaign' })
    } finally {
      setDeleting(false)
    }
  }

  async function handleInvitePlayer() {
    const email = inviteEmail.trim().toLowerCase()
    if (!email || !activeCampaignId) return
    setInviting(true)
    setMessage(null)
    try {
      const res = await apiFetch(`/campaigns/${activeCampaignId}/players`, {
        method: 'POST',
        body: JSON.stringify({ email }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to invite player')
      }
      setInviteEmail('')
      setMessage({ kind: 'info', text: `Invited ${email} to the campaign.` })
      // Refresh players list
      const listRes = await apiFetch(`/campaigns/${activeCampaignId}/players`)
      if (listRes.ok) {
        const data = await listRes.json()
        if (data?.players) setPlayers(data.players)
      }
    } catch (e: any) {
      setMessage({ kind: 'error', text: e?.message || 'Failed to invite player' })
    } finally {
      setInviting(false)
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

      // Persist all campaign variables
      const res3 = await apiFetch(`/campaigns/${activeCampaignId}/variables`, {
        method: 'PUT',
        body: JSON.stringify(variables),
      })
      if (!res3.ok) {
        const err = await res3.json().catch(() => null)
        throw new Error(err?.detail || `Failed to save campaign variables (HTTP ${res3.status})`)
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
                  const associatedChars = characters.filter(
                    (c) => c?.sheet?.associations?.campaign_id === String(campaign.id)
                  )
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
                          {associatedChars.length > 0 ? (
                            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                              {associatedChars.map((c) => (
                                <span key={c.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginRight: 8 }}>
                                  🧙 {c.name}{c.class_name ? ` (${c.class_name})` : ''}{c.level ? ` L${c.level}` : ''}
                                </span>
                              ))}
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

              <div className="card card-pad" style={{ background: 'var(--surface-dark)', marginTop: 12 }}>
                <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                  <div className="muted">Campaign details</div>
                  <div className="row-wrap" style={{ gap: 8 }}>
                    {onPlay && activeCampaignId ? (
                      <button className="btn" type="button" disabled={!canEdit || Boolean(playBusy)} onClick={onPlay}>
                        {playBusy ? 'Starting…' : 'Start Session'}
                      </button>
                    ) : null}
                    <button
                      className="btn btn-secondary"
                      type="button"
                      disabled={!canEdit || saving}
                      onClick={onSave}
                    >
                      {saving ? 'Saving…' : 'Save Settings'}
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

              <div className="card card-pad" style={{ opacity: loading ? 0.7 : 1, background: 'var(--surface-dark)', marginTop: 12 }}>
                <div className="stack" style={{ gap: 10 }}>
                  <div className="muted">Settings</div>

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

                  <div className="stack" style={{ gap: 6 }}>
                    <label className="muted" style={{ fontSize: 13 }}>World Name</label>
                    <input
                      className="input"
                      value={settings.world_name}
                      onChange={(e) => setSettings((prev) => ({ ...prev, world_name: e.target.value }))}
                      placeholder="e.g. Faerûn, The Shattered Isles"
                      disabled={!canEdit}
                    />
                  </div>

                  <div className="stack" style={{ gap: 6 }}>
                    <label className="muted" style={{ fontSize: 13 }}>Setting Summary</label>
                    <textarea
                      className="input"
                      value={settings.setting_summary}
                      onChange={(e) => setSettings((prev) => ({ ...prev, setting_summary: e.target.value }))}
                      placeholder="Describe the campaign world, its history, and key locations…"
                      rows={3}
                      disabled={!canEdit}
                    />
                  </div>

                  <div className="row-wrap" style={{ gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <label className="muted" style={{ fontSize: 13 }}>Genre</label>
                      <select
                        className="input"
                        value={settings.genre}
                        onChange={(e) => setSettings((prev) => ({ ...prev, genre: e.target.value }))}
                        disabled={!canEdit}
                      >
                        <option value="fantasy">Fantasy</option>
                        <option value="sci-fi">Sci-Fi</option>
                        <option value="horror">Horror</option>
                        <option value="western">Western</option>
                        <option value="steampunk">Steampunk</option>
                        <option value="modern">Modern</option>
                        <option value="post-apocalyptic">Post-Apocalyptic</option>
                        <option value="other">Other</option>
                      </select>
                    </div>

                    <div style={{ flex: 1 }}>
                      <label className="muted" style={{ fontSize: 13 }}>Tone</label>
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
                        <option value="dark-fantasy">Dark Fantasy</option>
                        <option value="comedy">Comedy</option>
                        <option value="horror">Horror</option>
                        <option value="balanced">Balanced</option>
                      </select>
                    </div>

                    <div style={{ flex: 1 }}>
                      <label className="muted" style={{ fontSize: 13 }}>Content Rating</label>
                      <select
                        className="input"
                        value={variables.content_rating}
                        onChange={(e) => setVariables((prev) => ({ ...prev, content_rating: e.target.value }))}
                        disabled={!canEdit}
                      >
                        <option value="family">PG (Family-friendly)</option>
                        <option value="pg-13">PG-13</option>
                        <option value="mature">R (Mature)</option>
                      </select>
                    </div>
                  </div>

                  <div className="row-wrap" style={{ gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <label className="muted" style={{ fontSize: 13 }}>Ruleset</label>
                      <input
                        className="input"
                        value={settings.ruleset}
                        onChange={(e) => setSettings((prev) => ({ ...prev, ruleset: e.target.value }))}
                        placeholder="e.g. 5th Edition SRD, OSR, custom homebrew"
                        disabled={!canEdit}
                      />
                    </div>

                    <div style={{ flex: '0 0 120px' }}>
                      <label className="muted" style={{ fontSize: 13 }}>Starting Level</label>
                      <input
                        className="input"
                        type="number"
                        min={1}
                        max={20}
                        value={settings.starting_level}
                        onChange={(e) => setSettings((prev) => ({ ...prev, starting_level: Math.max(1, Math.min(20, Number(e.target.value) || 1)) }))}
                        disabled={!canEdit}
                      />
                    </div>
                  </div>

                  <div className="row-wrap" style={{ gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <label className="muted" style={{ fontSize: 13 }}>Pacing</label>
                      <select
                        className="input"
                        value={variables.pacing}
                        onChange={(e) => setVariables((prev) => ({ ...prev, pacing: e.target.value }))}
                        disabled={!canEdit}
                      >
                        <option value="slow">Slow</option>
                        <option value="moderate">Moderate</option>
                        <option value="fast">Fast</option>
                      </select>
                    </div>

                    <div style={{ flex: 1 }}>
                      <label className="muted" style={{ fontSize: 13 }}>Narrative Style</label>
                      <select
                        className="input"
                        value={variables.narrative_style}
                        onChange={(e) => setVariables((prev) => ({ ...prev, narrative_style: e.target.value }))}
                        disabled={!canEdit}
                      >
                        <option value="balanced">Balanced</option>
                        <option value="epic">Epic</option>
                        <option value="intimate">Intimate</option>
                        <option value="gritty">Gritty</option>
                        <option value="lighthearted">Lighthearted</option>
                      </select>
                    </div>

                    <div style={{ flex: 1 }}>
                      <label className="muted" style={{ fontSize: 13 }}>Naming Style</label>
                      <input
                        className="input"
                        value={variables.naming_style}
                        onChange={(e) => setVariables((prev) => ({ ...prev, naming_style: e.target.value }))}
                        placeholder="e.g. Norse, Elvish, Latin"
                        disabled={!canEdit}
                      />
                    </div>
                  </div>

                  <div className="stack" style={{ gap: 6 }}>
                    <label className="muted" style={{ fontSize: 13 }}>Themes <span className="muted" style={{ fontWeight: 400 }}>(comma-separated)</span></label>
                    <input
                      className="input"
                      value={variables.themes.join(', ')}
                      onChange={(e) => {
                        setVariables((prev) => ({ ...prev, themes: parseThemesInput(e.target.value) }))
                      }}
                      placeholder="e.g. redemption, betrayal, survival"
                      disabled={!canEdit}
                    />
                  </div>

                  <div className="stack" style={{ gap: 6 }}>
                    <label className="muted" style={{ fontSize: 13 }}>House Rules</label>
                    <textarea
                      className="input"
                      value={settings.house_rules}
                      onChange={(e) => setSettings((prev) => ({ ...prev, house_rules: e.target.value }))}
                      placeholder="Any custom rules the AI should follow…"
                      rows={3}
                      disabled={!canEdit}
                    />
                  </div>

                  <div className="stack" style={{ gap: 6 }}>
                    <label className="muted" style={{ fontSize: 13 }}>Player-run Mode</label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: canEdit ? 'pointer' : 'default' }}>
                      <input
                        type="checkbox"
                        checked={settings.player_run_mode}
                        onChange={(e) => setSettings((prev) => ({ ...prev, player_run_mode: e.target.checked }))}
                        disabled={!canEdit}
                      />
                      <span style={{ fontSize: 13 }}>Disable AI narration — players run the session manually</span>
                    </label>
                    <div className="muted" style={{ fontSize: 12 }}>
                      When enabled, AI agents are disabled for narration but note-taking, NPC tracking, and dice rolls remain active.
                    </div>
                  </div>
                </div>
              </div>

              {gmAssignment.gm_mode === 'player' && (
                <div className="card card-pad" style={{ background: 'var(--surface-dark)', marginTop: 12 }}>
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

              <div className="card card-pad" style={{ background: 'var(--surface-dark)', marginTop: 12 }}>
                <div className="muted" style={{ marginBottom: 8, fontWeight: 700 }}>Danger Zone</div>
                <button
                  className="btn btn-quiet"
                  type="button"
                  disabled={deleting}
                  style={{ color: 'var(--tt-error, #c0392b)' }}
                  onClick={handleDeleteCampaign}
                >
                  {deleting ? 'Deleting…' : 'Delete Campaign'}
                </button>
              </div>
            </>
          ) : null}

          {viewMode === 'documents' ? (
            <>
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => setViewMode('list')}>
                ← Back to campaigns
              </button>
              <div className="card card-pad" style={{ background: 'var(--surface-dark)', marginTop: 12 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Campaign Documents</div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Upload PDFs, campaign modules, random tables, or instruction sets. The AI uses these during gameplay.
                </div>
                <div className="row-wrap" style={{ gap: 8, alignItems: 'center' }}>
                  <label className="btn" style={{ cursor: 'pointer', margin: 0 }} title="Upload Document" aria-label="Upload Document">
                    <AddDocumentIcon />
                    <span style={{ marginLeft: 6 }}>Upload Document</span>
                    <input
                      type="file"
                      accept=".pdf,.txt,.md,.json,.doc,.docx"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        // TODO: wire to server document upload endpoint
                        if (file) setMessage({ kind: 'info', text: `Selected: ${file.name} (upload coming soon)` })
                        e.target.value = ''
                      }}
                    />
                  </label>
                  <button
                    className="btn btn-secondary"
                    type="button"
                    title="Create Folder"
                    onClick={() => {
                      // TODO: wire to server folder creation endpoint
                      const folderName = window.prompt('Folder name:')
                      if (folderName?.trim()) setMessage({ kind: 'info', text: `Folder "${folderName.trim()}" (folder creation coming soon)` })
                    }}
                  >
                    <NewIcon />
                    <span style={{ marginLeft: 6 }}>Create Folder</span>
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
              <div className="card card-pad" style={{ background: 'var(--surface-dark)', marginTop: 12 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Players</div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Invite players by username or email to grant access to this campaign.
                </div>
                <div style={{ gap: 8, marginBottom: 12 }}>
                  <div style={{ flex: 1, marginBottom: 6 }}>
                    <label className="muted" style={{ fontSize: 12 }}>Username or email</label>
                    <input
                      className="input"
                      placeholder="Search by username or enter email"
                      value={inviteEmail}
                      onChange={(e) => { setInviteEmail(e.target.value) }}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleInvitePlayer() } }}
                      disabled={inviting}
                    />
                  </div>
                  {inviteMatchBusy ? (
                    <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Searching…</div>
                  ) : inviteMatches.length > 0 ? (
                    <div className="card" style={{ padding: 8, marginBottom: 8, display: 'grid', gap: 4 }}>
                      <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Matches</div>
                      {inviteMatches.map((m) => {
                        const key = String(m?.id ?? m?.email ?? m?.username ?? Math.random())
                        const label = m?.username ? `@${m.username}` : (m?.email || 'user')
                        const sub = m?.name && m?.name !== m?.username ? String(m.name) : (m?.email || '')
                        return (
                          <button
                            key={key}
                            className="btn btn-secondary btn-sm"
                            type="button"
                            onClick={() => {
                              setInviteEmail(m?.username || m?.email || '')
                              setInviteMatches([])
                            }}
                            style={{ textAlign: 'left' }}
                          >
                            <div style={{ fontWeight: 700 }}>{label}</div>
                            {sub ? <div className="muted" style={{ fontSize: 12 }}>{sub}</div> : null}
                          </button>
                        )
                      })}
                    </div>
                  ) : null}
                  <button
                    className="btn"
                    type="button"
                    disabled={inviting || !inviteEmail.trim()}
                    onClick={handleInvitePlayer}
                  >
                    <AddPlayerIcon />
                    <span style={{ marginLeft: 6 }}>{inviting ? 'Inviting…' : 'Add Player'}</span>
                  </button>
                </div>
                {players.length > 0 ? (
                  <div className="stack" style={{ gap: 6 }}>
                    {players.map((player) => (
                      <div key={player.id} className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--tt-border)' }}>
                        <div>
                          <div>{player.username || player.email || 'Unnamed Player'}</div>
                          {player.email && player.username ? <div className="muted" style={{ fontSize: 12 }}>{player.email}</div> : null}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="inline-alert">No players listed yet.</div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </section>
  )
}
