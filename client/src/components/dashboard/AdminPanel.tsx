import React, { useCallback, useEffect, useState } from 'react'

import { apiFetch } from '../../api'
import PageHeader from '../ui/PageHeader'

type SiteStats = {
  total_users: number
  verified_users: number
  total_campaigns: number
  active_campaigns: number
  total_characters: number
  total_messages: number
}

type AdminUser = {
  id: number
  email: string | null
  username: string | null
  name: string | null
  verified: boolean
  admin: boolean
}

type AdminCampaign = {
  id: string
  name: string
  description: string | null
  archived: boolean
  created_at: string | null
  owner_id: number
  owner_name: string | null
}

type Tab = 'stats' | 'users' | 'campaigns' | 'search'

type Props = {
  onBack?: () => void
}

export default function AdminPanel({ onBack }: Props) {
  const [tab, setTab] = useState<Tab>('stats')

  // Stats
  const [stats, setStats] = useState<SiteStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState<string | null>(null)

  // Users
  const [users, setUsers] = useState<AdminUser[]>([])
  const [usersLoading, setUsersLoading] = useState(false)
  const [usersError, setUsersError] = useState<string | null>(null)

  // Campaigns
  const [campaigns, setCampaigns] = useState<AdminCampaign[]>([])
  const [campaignsLoading, setCampaignsLoading] = useState(false)
  const [campaignsError, setCampaignsError] = useState<string | null>(null)

  // Search
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<{ users: AdminUser[]; campaigns: AdminCampaign[] } | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  // User action modals
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [actionModal, setActionModal] = useState<'warn' | 'message' | 'reset-password' | null>(null)
  const [actionInput, setActionInput] = useState('')
  const [actionInput2, setActionInput2] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  const loadStats = useCallback(async () => {
    setStatsLoading(true)
    setStatsError(null)
    try {
      const res = await apiFetch('/admin/stats')
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setStatsError(d?.detail || `Error ${res.status}`)
        return
      }
      setStats(await res.json())
    } catch {
      setStatsError('Network error loading stats.')
    } finally {
      setStatsLoading(false)
    }
  }, [])

  const loadUsers = useCallback(async () => {
    setUsersLoading(true)
    setUsersError(null)
    try {
      const res = await apiFetch('/admin/users?limit=100')
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setUsersError(d?.detail || `Error ${res.status}`)
        return
      }
      const data = await res.json()
      setUsers(data.users || [])
    } catch {
      setUsersError('Network error loading users.')
    } finally {
      setUsersLoading(false)
    }
  }, [])

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true)
    setCampaignsError(null)
    try {
      const res = await apiFetch('/admin/campaigns?limit=100')
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setCampaignsError(d?.detail || `Error ${res.status}`)
        return
      }
      const data = await res.json()
      setCampaigns(data.campaigns || [])
    } catch {
      setCampaignsError('Network error loading campaigns.')
    } finally {
      setCampaignsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tab === 'stats') loadStats()
    else if (tab === 'users') loadUsers()
    else if (tab === 'campaigns') loadCampaigns()
  }, [tab, loadStats, loadUsers, loadCampaigns])

  const handleSearch = useCallback(async () => {
    if (searchQuery.trim().length < 2) {
      setSearchResults({ users: [], campaigns: [] })
      return
    }
    setSearchLoading(true)
    setSearchError(null)
    try {
      const res = await apiFetch(`/admin/search?q=${encodeURIComponent(searchQuery.trim())}`)
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setSearchError(d?.detail || `Error ${res.status}`)
        return
      }
      setSearchResults(await res.json())
    } catch {
      setSearchError('Network error searching.')
    } finally {
      setSearchLoading(false)
    }
  }, [searchQuery])

  const openAction = (user: AdminUser, action: typeof actionModal) => {
    setSelectedUser(user)
    setActionModal(action)
    setActionInput('')
    setActionInput2('')
    setActionError(null)
    setActionSuccess(null)
  }

  const closeAction = () => {
    setActionModal(null)
    setSelectedUser(null)
    setActionInput('')
    setActionInput2('')
    setActionError(null)
    setActionSuccess(null)
  }

  const submitAction = async () => {
    if (!selectedUser || !actionModal) return
    setActionBusy(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      let endpoint = ''
      let body: Record<string, string> = {}
      if (actionModal === 'warn') {
        endpoint = `/admin/users/${selectedUser.id}/warn`
        body = { message: actionInput }
      } else if (actionModal === 'message') {
        endpoint = `/admin/users/${selectedUser.id}/message`
        body = { title: actionInput, body: actionInput2 }
      } else if (actionModal === 'reset-password') {
        endpoint = `/admin/users/${selectedUser.id}/reset-password`
        body = { new_password: actionInput }
      }
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setActionError(d?.detail || `Error ${res.status}`)
        return
      }
      setActionSuccess('Action completed successfully.')
    } catch {
      setActionError('Network error.')
    } finally {
      setActionBusy(false)
    }
  }

  const archiveCampaign = async (campaignId: string) => {
    if (!window.confirm('Archive this campaign? It will be deactivated but not deleted.')) return
    try {
      const res = await apiFetch(`/admin/campaigns/${campaignId}/archive`, { method: 'POST' })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        alert(d?.detail || `Error ${res.status}`)
        return
      }
      setCampaigns((prev) => prev.map((c) => (c.id === campaignId ? { ...c, archived: true } : c)))
    } catch {
      alert('Network error archiving campaign.')
    }
  }

  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="Admin Panel"
        subtitle="Site administration tools and reports"
        actions={
          onBack ? (
            <button className="btn btn-secondary" type="button" onClick={onBack}>
              ← Back
            </button>
          ) : undefined
        }
      />

      <div className="tab-bar" role="tablist">
        {(['stats', 'users', 'campaigns', 'search'] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`tab-btn${tab === t ? ' active' : ''}`}
            type="button"
            onClick={() => setTab(t)}
          >
            {t === 'stats' && 'Site Stats'}
            {t === 'users' && 'Users'}
            {t === 'campaigns' && 'Campaigns'}
            {t === 'search' && 'Global Search'}
          </button>
        ))}
      </div>

      {/* ── Stats ── */}
      {tab === 'stats' && (
        <div className="card card-pad">
          <div className="section-title">Site Statistics</div>
          {statsLoading && <div className="loading-text">Loading…</div>}
          {statsError && <div className="error-text">{statsError}</div>}
          {stats && (
            <div className="stats-grid">
              <div className="stat-card"><div className="stat-value">{stats.total_users}</div><div className="stat-label">Total Users</div></div>
              <div className="stat-card"><div className="stat-value">{stats.verified_users}</div><div className="stat-label">Verified Users</div></div>
              <div className="stat-card"><div className="stat-value">{stats.total_campaigns}</div><div className="stat-label">Total Campaigns</div></div>
              <div className="stat-card"><div className="stat-value">{stats.active_campaigns}</div><div className="stat-label">Active Campaigns</div></div>
              <div className="stat-card"><div className="stat-value">{stats.total_characters}</div><div className="stat-label">Characters</div></div>
              <div className="stat-card"><div className="stat-value">{stats.total_messages}</div><div className="stat-label">Chat Messages</div></div>
            </div>
          )}
        </div>
      )}

      {/* ── Users ── */}
      {tab === 'users' && (
        <div className="card card-pad">
          <div className="section-title">User Management</div>
          {usersLoading && <div className="loading-text">Loading…</div>}
          {usersError && <div className="error-text">{usersError}</div>}
          {!usersLoading && !usersError && (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name / Username</th>
                  <th>Email</th>
                  <th>Verified</th>
                  <th>Role</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.id}</td>
                    <td>{u.name || u.username || '—'}</td>
                    <td>{u.email || '—'}</td>
                    <td>{u.verified ? '✓' : '✗'}</td>
                    <td>{u.admin ? 'Admin' : 'Player'}</td>
                    <td className="admin-actions-cell">
                      <button className="btn btn-sm btn-secondary" type="button" onClick={() => openAction(u, 'warn')}>Warn</button>
                      <button className="btn btn-sm btn-secondary" type="button" onClick={() => openAction(u, 'message')}>Message</button>
                      <button className="btn btn-sm btn-secondary" type="button" onClick={() => openAction(u, 'reset-password')}>Reset PW</button>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr><td colSpan={6}><span className="empty-text">No users found.</span></td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Campaigns ── */}
      {tab === 'campaigns' && (
        <div className="card card-pad">
          <div className="section-title">Campaign Audit</div>
          {campaignsLoading && <div className="loading-text">Loading…</div>}
          {campaignsError && <div className="error-text">{campaignsError}</div>}
          {!campaignsLoading && !campaignsError && (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Owner</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td>{c.name}</td>
                    <td>{c.owner_name || c.owner_id}</td>
                    <td>{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</td>
                    <td>{c.archived ? <span className="badge badge-muted">Archived</span> : <span className="badge badge-active">Active</span>}</td>
                    <td>
                      {!c.archived && (
                        <button className="btn btn-sm btn-secondary" type="button" onClick={() => archiveCampaign(c.id)}>Archive</button>
                      )}
                    </td>
                  </tr>
                ))}
                {campaigns.length === 0 && (
                  <tr><td colSpan={6}><span className="empty-text">No campaigns found.</span></td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Search ── */}
      {tab === 'search' && (
        <div className="card card-pad">
          <div className="section-title">Global Search</div>
          <div className="row-wrap" style={{ gap: 8, marginBottom: 16 }}>
            <input
              className="input"
              type="text"
              placeholder="Search users, campaigns…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button className="btn" type="button" onClick={handleSearch} disabled={searchLoading}>
              {searchLoading ? 'Searching…' : 'Search'}
            </button>
          </div>
          {searchError && <div className="error-text">{searchError}</div>}
          {searchResults && (
            <>
              <div className="section-subtitle">Users ({searchResults.users.length})</div>
              {searchResults.users.length > 0 ? (
                <table className="admin-table">
                  <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Role</th></tr></thead>
                  <tbody>
                    {searchResults.users.map((u) => (
                      <tr key={u.id}><td>{u.id}</td><td>{u.name || u.username || '—'}</td><td>{u.email || '—'}</td><td>{u.admin ? 'Admin' : 'Player'}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="empty-text">No users found.</div>}

              <div className="section-subtitle" style={{ marginTop: 16 }}>Campaigns ({searchResults.campaigns.length})</div>
              {searchResults.campaigns.length > 0 ? (
                <table className="admin-table">
                  <thead><tr><th>ID</th><th>Name</th><th>Owner ID</th><th>Status</th></tr></thead>
                  <tbody>
                    {searchResults.campaigns.map((c) => (
                      <tr key={c.id}><td>{c.id}</td><td>{c.name}</td><td>{c.owner_id}</td><td>{c.archived ? 'Archived' : 'Active'}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="empty-text">No campaigns found.</div>}
            </>
          )}
        </div>
      )}

      {/* ── User action modal ── */}
      {actionModal && selectedUser && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-box">
            <div className="modal-header">
              <div className="modal-title">
                {actionModal === 'warn' && `Warn: ${selectedUser.name || selectedUser.email}`}
                {actionModal === 'message' && `Message: ${selectedUser.name || selectedUser.email}`}
                {actionModal === 'reset-password' && `Reset Password: ${selectedUser.name || selectedUser.email}`}
              </div>
              <button className="modal-close" type="button" onClick={closeAction} aria-label="Close">✕</button>
            </div>
            <div className="modal-body stack" style={{ gap: 10 }}>
              {actionModal === 'warn' && (
                <label className="field-label">
                  Warning message
                  <textarea className="input" rows={3} value={actionInput} onChange={(e) => setActionInput(e.target.value)} placeholder="Describe the warning…" />
                </label>
              )}
              {actionModal === 'message' && (
                <>
                  <label className="field-label">
                    Title
                    <input className="input" type="text" value={actionInput} onChange={(e) => setActionInput(e.target.value)} placeholder="Message title" />
                  </label>
                  <label className="field-label">
                    Body
                    <textarea className="input" rows={3} value={actionInput2} onChange={(e) => setActionInput2(e.target.value)} placeholder="Message body (optional)" />
                  </label>
                </>
              )}
              {actionModal === 'reset-password' && (
                <label className="field-label">
                  New password (min 8 characters)
                  <input className="input" type="text" value={actionInput} onChange={(e) => setActionInput(e.target.value)} placeholder="New password" />
                </label>
              )}
              {actionError && <div className="error-text">{actionError}</div>}
              {actionSuccess && <div className="success-text">{actionSuccess}</div>}
            </div>
            <div className="modal-footer row-wrap">
              <button className="btn btn-secondary" type="button" onClick={closeAction}>Cancel</button>
              <button className="btn" type="button" onClick={submitAction} disabled={actionBusy || Boolean(actionSuccess)}>
                {actionBusy ? 'Sending…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
