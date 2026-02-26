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

type AdminTicket = {
  id: number
  user_id: number
  user_email?: string | null
  user_name?: string | null
  subject: string
  body: string
  status: string
  created_at: string | null
  updated_at: string | null
}

type AdminReport = {
  id: number
  reporter_id: number
  reported_id: number
  reporter_name?: string | null
  reported_name?: string | null
  reason: string
  details: string
  status: string
  created_at: string | null
  reviewed_at: string | null
}

const TICKET_STATUSES = ['open', 'in_progress', 'resolved', 'closed'] as const
const REPORT_STATUSES = ['open', 'reviewed', 'dismissed'] as const
const MODERATION_LIST_LIMIT = 100

type Tab = 'stats' | 'users' | 'campaigns' | 'search' | 'tickets' | 'reports' | 'bans'

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
  const [actionModal, setActionModal] = useState<'warn' | 'message' | 'reset-password' | 'impersonate' | null>(null)
  const [actionInput, setActionInput] = useState('')
  const [actionInput2, setActionInput2] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  // Tickets
  const [tickets, setTickets] = useState<AdminTicket[]>([])
  const [ticketsLoading, setTicketsLoading] = useState(false)
  const [ticketsError, setTicketsError] = useState<string | null>(null)
  const [ticketStatusFilter, setTicketStatusFilter] = useState<string>('')
  const [expandedTicketId, setExpandedTicketId] = useState<number | null>(null)
  const [ticketActionBusy, setTicketActionBusy] = useState(false)
  const [ticketActionError, setTicketActionError] = useState<string | null>(null)

  // Reports
  const [reports, setReports] = useState<AdminReport[]>([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [reportsError, setReportsError] = useState<string | null>(null)
  const [reportStatusFilter, setReportStatusFilter] = useState<string>('')
  const [expandedReportId, setExpandedReportId] = useState<number | null>(null)
  const [reportActionBusy, setReportActionBusy] = useState(false)
  const [reportActionError, setReportActionError] = useState<string | null>(null)

  // Bans
  type BanRecord = { id: number; email: string; reason: string; ban_type: string; suspended_until: string | null; created_at: string | null }
  const [bans, setBans] = useState<BanRecord[]>([])
  const [bansLoading, setBansLoading] = useState(false)
  const [bansError, setBansError] = useState<string | null>(null)
  const [banEmail, setBanEmail] = useState('')
  const [banReason, setBanReason] = useState('')
  const [banType, setBanType] = useState<'ban' | 'suspend'>('ban')
  const [banUntil, setBanUntil] = useState('')
  const [banBusy, setBanBusy] = useState(false)
  const [banMsg, setBanMsg] = useState<string | null>(null)

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

  const loadTickets = useCallback(async (statusFilter?: string) => {
    setTicketsLoading(true)
    setTicketsError(null)
    try {
      const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}&limit=${MODERATION_LIST_LIMIT}` : `?limit=${MODERATION_LIST_LIMIT}`
      const res = await apiFetch('/support/tickets' + qs)
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setTicketsError(d?.detail || `Error ${res.status}`)
        return
      }
      const data = await res.json()
      setTickets(data.tickets || [])
    } catch {
      setTicketsError('Network error loading tickets.')
    } finally {
      setTicketsLoading(false)
    }
  }, [])

  const loadReports = useCallback(async (statusFilter?: string) => {
    setReportsLoading(true)
    setReportsError(null)
    try {
      const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}&limit=${MODERATION_LIST_LIMIT}` : `?limit=${MODERATION_LIST_LIMIT}`
      const res = await apiFetch('/moderation/reports' + qs)
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setReportsError(d?.detail || `Error ${res.status}`)
        return
      }
      const data = await res.json()
      setReports(data.reports || [])
    } catch {
      setReportsError('Network error loading reports.')
    } finally {
      setReportsLoading(false)
    }
  }, [])

  const loadBans = useCallback(async () => {
    setBansLoading(true)
    setBansError(null)
    try {
      const res = await apiFetch('/admin/bans')
      if (!res.ok) { const d = await res.json().catch(() => null); setBansError(d?.detail || `Error ${res.status}`); return }
      const data = await res.json()
      setBans(data.bans || [])
    } catch { setBansError('Network error loading bans.') }
    finally { setBansLoading(false) }
  }, [])

  const removeBan = async (email: string) => {
    if (!window.confirm(`Remove ban for ${email}?`)) return
    try {
      const r = await apiFetch(`/admin/bans/${encodeURIComponent(email)}`, { method: 'DELETE' })
      if (!r.ok) { const d = await r.json().catch(() => null); alert(d?.detail || `Error ${r.status}`); return }
      setBans(prev => prev.filter(b => b.email !== email))
    } catch { alert('Network error.') }
  }

  const submitBan = async (e: React.FormEvent) => {
    e.preventDefault()
    setBanBusy(true)
    setBanMsg(null)
    try {
      const body: Record<string, string> = { email: banEmail.trim(), reason: banReason.trim(), ban_type: banType }
      if (banType === 'suspend' && banUntil) body.suspended_until = new Date(banUntil).toISOString()
      const r = await apiFetch('/admin/bans', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (!r.ok) { const d = await r.json().catch(() => null); setBanMsg(d?.detail || `Error ${r.status}`); return }
      setBanMsg('Saved.')
      setBanEmail(''); setBanReason(''); setBanType('ban'); setBanUntil('')
      loadBans()
    } catch { setBanMsg('Network error.') }
    finally { setBanBusy(false) }
  }

  useEffect(() => {
    if (tab === 'stats') loadStats()
    else if (tab === 'users') loadUsers()
    else if (tab === 'campaigns') loadCampaigns()
    else if (tab === 'tickets') loadTickets()
    else if (tab === 'reports') loadReports()
    else if (tab === 'bans') loadBans()
  }, [tab, loadStats, loadUsers, loadCampaigns, loadTickets, loadReports, loadBans])

  const updateTicketStatus = async (ticketId: number, status: string) => {
    setTicketActionBusy(true)
    setTicketActionError(null)
    try {
      const res = await apiFetch(`/support/tickets/${ticketId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setTicketActionError(d?.detail || `Error ${res.status}`)
        return
      }
      const data = await res.json()
      setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, ...data.ticket } : t)))
    } catch {
      setTicketActionError('Network error updating ticket.')
    } finally {
      setTicketActionBusy(false)
    }
  }

  const updateReportStatus = async (reportId: number, status: string) => {
    setReportActionBusy(true)
    setReportActionError(null)
    try {
      const res = await apiFetch(`/moderation/reports/${reportId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setReportActionError(d?.detail || `Error ${res.status}`)
        return
      }
      const data = await res.json()
      setReports((prev) => prev.map((r) => (r.id === reportId ? { ...r, ...data.report } : r)))
    } catch {
      setReportActionError('Network error updating report.')
    } finally {
      setReportActionBusy(false)
    }
  }

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
      } else if (actionModal === 'impersonate') {
        endpoint = `/admin/users/${selectedUser.id}/impersonate`
      }
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: actionModal === 'impersonate' ? undefined : JSON.stringify(body),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        setActionError(d?.detail || `Error ${res.status}`)
        return
      }
      if (actionModal === 'impersonate') {
        const d = await res.json()
        const token = d.access_token
        if (token) {
          localStorage.setItem('access_token', token)
          setActionSuccess(`Logged in as ${selectedUser.name || selectedUser.email}. Reloading…`)
          setTimeout(() => window.location.reload(), 1200)
        }
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
        {(['stats', 'users', 'campaigns', 'search', 'tickets', 'reports', 'bans'] as Tab[]).map((t) => (
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
            {t === 'tickets' && 'Support Tickets'}
            {t === 'reports' && 'User Reports'}
            {t === 'bans' && '🚫 Bans'}
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
                      <button className="btn btn-sm btn-secondary" type="button" onClick={() => openAction(u, 'impersonate')}>Login As</button>
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

      {/* ── Support Tickets ── */}
      {tab === 'tickets' && (
        <div className="card card-pad">
          <div className="section-title">Support Tickets</div>
          <div className="row-wrap" style={{ gap: 8, marginBottom: 12, alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: 13 }}>Filter by status:</span>
            <select
              className="input"
              style={{ width: 'auto' }}
              value={ticketStatusFilter}
              onChange={(e) => {
                const v = e.target.value
                setTicketStatusFilter(v)
                loadTickets(v || undefined)
              }}
            >
              <option value="">All</option>
              {TICKET_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button className="btn btn-sm btn-secondary" type="button" onClick={() => loadTickets(ticketStatusFilter || undefined)} disabled={ticketsLoading}>
              {ticketsLoading ? '…' : 'Refresh'}
            </button>
          </div>
          {ticketsError && <div className="error-text">{ticketsError}</div>}
          {ticketActionError && <div className="error-text">{ticketActionError}</div>}
          {!ticketsLoading && !ticketsError && (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>User</th>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Submitted</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tickets.map((t) => (
                  <React.Fragment key={t.id}>
                    <tr
                      style={{ cursor: 'pointer' }}
                      onClick={() => setExpandedTicketId((prev) => (prev === t.id ? null : t.id))}
                    >
                      <td>{t.id}</td>
                      <td>{t.user_name || t.user_email || t.user_id}</td>
                      <td>{t.subject}</td>
                      <td>
                        <span className={`badge ${t.status === 'open' ? 'badge-active' : t.status === 'resolved' || t.status === 'closed' ? 'badge-muted' : 'badge-warn'}`}>
                          {t.status}
                        </span>
                      </td>
                      <td>{t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <select
                          className="input"
                          style={{ width: 'auto', fontSize: 12 }}
                          value={t.status}
                          disabled={ticketActionBusy}
                          onChange={(e) => updateTicketStatus(t.id, e.target.value)}
                        >
                          {TICKET_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </td>
                    </tr>
                    {expandedTicketId === t.id && (
                      <tr>
                        <td colSpan={6} style={{ background: 'var(--tt-surface, #1a1a2e)', padding: '10px 16px' }}>
                          <div style={{ fontWeight: 600, marginBottom: 4 }}>From: {t.user_name || t.user_email || `User ${t.user_id}`}</div>
                          <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6 }}>{t.body}</div>
                          {t.updated_at && (
                            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                              Last updated: {new Date(t.updated_at).toLocaleString()}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {tickets.length === 0 && (
                  <tr><td colSpan={6}><span className="empty-text">No tickets found.</span></td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── User Reports ── */}
      {tab === 'reports' && (
        <div className="card card-pad">
          <div className="section-title">User Reports</div>
          <div className="row-wrap" style={{ gap: 8, marginBottom: 12, alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: 13 }}>Filter by status:</span>
            <select
              className="input"
              style={{ width: 'auto' }}
              value={reportStatusFilter}
              onChange={(e) => {
                const v = e.target.value
                setReportStatusFilter(v)
                loadReports(v || undefined)
              }}
            >
              <option value="">All</option>
              {REPORT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <button className="btn btn-sm btn-secondary" type="button" onClick={() => loadReports(reportStatusFilter || undefined)} disabled={reportsLoading}>
              {reportsLoading ? '…' : 'Refresh'}
            </button>
          </div>
          {reportsError && <div className="error-text">{reportsError}</div>}
          {reportActionError && <div className="error-text">{reportActionError}</div>}
          {!reportsLoading && !reportsError && (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Reporter</th>
                  <th>Reported</th>
                  <th>Reason</th>
                  <th>Status</th>
                  <th>Filed</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <React.Fragment key={r.id}>
                    <tr
                      style={{ cursor: r.details ? 'pointer' : 'default' }}
                      onClick={() => r.details && setExpandedReportId((prev) => (prev === r.id ? null : r.id))}
                    >
                      <td>{r.id}</td>
                      <td>{r.reporter_name || r.reporter_id}</td>
                      <td>{r.reported_name || r.reported_id}</td>
                      <td><span className="badge badge-warn">{r.reason.replace('_', ' ')}</span></td>
                      <td>
                        <span className={`badge ${r.status === 'open' ? 'badge-active' : 'badge-muted'}`}>
                          {r.status}
                        </span>
                      </td>
                      <td>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <select
                          className="input"
                          style={{ width: 'auto', fontSize: 12 }}
                          value={r.status}
                          disabled={reportActionBusy}
                          onChange={(e) => updateReportStatus(r.id, e.target.value)}
                        >
                          {REPORT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </td>
                    </tr>
                    {expandedReportId === r.id && r.details && (
                      <tr>
                        <td colSpan={7} style={{ background: 'var(--tt-surface, #1a1a2e)', padding: '10px 16px' }}>
                          <div style={{ fontWeight: 600, marginBottom: 4 }}>
                            {r.reporter_name || r.reporter_id} → {r.reported_name || r.reported_id}
                          </div>
                          <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6 }}>{r.details}</div>
                          {r.reviewed_at && (
                            <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                              Reviewed: {new Date(r.reviewed_at).toLocaleString()}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {reports.length === 0 && (
                  <tr><td colSpan={7}><span className="empty-text">No reports found.</span></td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Bans / Suspensions ── */}
      {tab === 'bans' && (
        <div className="card card-pad">
          <div className="section-title">Email Bans &amp; Suspensions</div>
          <form className="stack" style={{ gap: 10, marginBottom: 16 }} onSubmit={submitBan}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input
                className="input"
                style={{ flex: 2, minWidth: 160 }}
                placeholder="email or @domain.com"
                value={banEmail}
                onChange={e => setBanEmail(e.target.value)}
                required
              />
              <input
                className="input"
                style={{ flex: 2, minWidth: 120 }}
                placeholder="Reason"
                value={banReason}
                onChange={e => setBanReason(e.target.value)}
              />
              <select className="input" style={{ flex: 1, minWidth: 100 }} value={banType} onChange={e => setBanType(e.target.value as 'ban' | 'suspend')}>
                <option value="ban">Ban</option>
                <option value="suspend">Suspend</option>
              </select>
              {banType === 'suspend' ? (
                <input
                  className="input"
                  type="datetime-local"
                  style={{ flex: 1, minWidth: 140 }}
                  placeholder="Suspend until"
                  value={banUntil}
                  onChange={e => setBanUntil(e.target.value)}
                />
              ) : null}
              <button className="btn btn-sm" type="submit" disabled={banBusy || !banEmail.trim()}>
                {banBusy ? '…' : 'Add'}
              </button>
            </div>
            {banMsg ? <div className={`inline-alert${banMsg === 'Saved.' ? '' : ' inline-alert-error'}`}>{banMsg}</div> : null}
          </form>

          {bansLoading ? <div className="loading-text">Loading…</div> : null}
          {bansError ? <div className="error-text">{bansError}</div> : null}
          {!bansLoading && bans.length === 0 ? <div className="empty-text">No active bans or suspensions.</div> : null}
          {bans.length > 0 && (
            <table className="admin-table">
              <thead><tr><th>Email</th><th>Type</th><th>Reason</th><th>Until</th><th>Created</th><th></th></tr></thead>
              <tbody>
                {bans.map(b => (
                  <tr key={b.id}>
                    <td>{b.email}</td>
                    <td>{b.ban_type}</td>
                    <td>{b.reason || '—'}</td>
                    <td>{b.suspended_until ? new Date(b.suspended_until).toLocaleDateString() : '∞'}</td>
                    <td>{b.created_at ? new Date(b.created_at).toLocaleDateString() : '—'}</td>
                    <td>
                      <button className="btn btn-sm btn-secondary" type="button" onClick={() => removeBan(b.email)}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
                {actionModal === 'impersonate' && `Login As: ${selectedUser.name || selectedUser.email}`}
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
              {actionModal === 'impersonate' && (
                <div className="muted" style={{ fontSize: 13 }}>
                  This will issue a 15-minute session token for <strong>{selectedUser.name || selectedUser.email}</strong>. Your current session will be replaced. Refresh the page after confirming.
                </div>
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
