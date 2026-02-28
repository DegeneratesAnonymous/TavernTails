import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

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

const TICKET_STATUSES = ['open', 'in_progress', 'resolved', 'closed'] as const
const MODERATION_LIST_LIMIT = 100
/** Users shown per page in the user management table. */
const USERS_PER_PAGE = 10
/** Debounce delay (ms) before filtering the user list after typing. */
const USER_SEARCH_DEBOUNCE_MS = 300

type Props = {
  onBack?: () => void
}

export default function AdminPanel({ onBack }: Props) {
  // Stats
  const [stats, setStats] = useState<SiteStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState<string | null>(null)

  // Users (auto-loaded on mount, paginated)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [usersLoading, setUsersLoading] = useState(false)
  const [usersError, setUsersError] = useState<string | null>(null)
  const [userSearch, setUserSearch] = useState('')
  const [userPage, setUserPage] = useState(0)
  const userSearchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Campaigns
  const [campaigns, setCampaigns] = useState<AdminCampaign[]>([])
  const [campaignsLoading, setCampaignsLoading] = useState(false)
  const [campaignsError, setCampaignsError] = useState<string | null>(null)
  const [campaignSearch, setCampaignSearch] = useState('')

  // User actions drawer
  const [drawerUser, setDrawerUser] = useState<AdminUser | null>(null)

  // User action modals
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [actionModal, setActionModal] = useState<'warn' | 'message' | 'reset-password' | 'impersonate' | null>(null)
  const [actionInput, setActionInput] = useState('')
  const [actionInput2, setActionInput2] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)

  // View user's tickets/campaigns (in modal)
  const [userDetailModal, setUserDetailModal] = useState<'tickets' | 'campaigns' | null>(null)
  const [userDetailUser, setUserDetailUser] = useState<AdminUser | null>(null)

  // Tickets
  const [tickets, setTickets] = useState<AdminTicket[]>([])
  const [ticketsLoading, setTicketsLoading] = useState(false)
  const [ticketsError, setTicketsError] = useState<string | null>(null)
  const [ticketStatusFilter, setTicketStatusFilter] = useState<string>('')
  const [ticketSearch, setTicketSearch] = useState('')
  const [expandedTicketId, setExpandedTicketId] = useState<number | null>(null)
  const [ticketActionBusy, setTicketActionBusy] = useState(false)
  const [ticketActionError, setTicketActionError] = useState<string | null>(null)

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
      const res = await apiFetch('/admin/users?limit=200')
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

  // Load stats, campaigns, tickets, bans on mount
  useEffect(() => {
    loadStats()
    loadUsers()
    loadCampaigns()
    loadTickets()
    loadBans()
  }, [loadStats, loadUsers, loadCampaigns, loadTickets, loadBans])

  // Reset to page 0 whenever the search query changes
  useEffect(() => {
    if (userSearchTimeout.current) clearTimeout(userSearchTimeout.current)
    userSearchTimeout.current = setTimeout(() => {
      setUserPage(0)
    }, USER_SEARCH_DEBOUNCE_MS)
    return () => {
      if (userSearchTimeout.current) clearTimeout(userSearchTimeout.current)
    }
  }, [userSearch])

  // ── Client-side filtered views ──────────────────────────────────────────────

  const sortedUsers = useMemo(() => {
    return [...users].sort((a, b) => {
      const nameA = (a.name || a.username || a.email || '').toLowerCase()
      const nameB = (b.name || b.username || b.email || '').toLowerCase()
      return nameA.localeCompare(nameB)
    })
  }, [users])

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase()
    if (!q) return sortedUsers
    return sortedUsers.filter(
      (u) =>
        (u.name || '').toLowerCase().includes(q) ||
        (u.username || '').toLowerCase().includes(q) ||
        (u.email || '').toLowerCase().includes(q),
    )
  }, [sortedUsers, userSearch])

  const userTotalPages = Math.max(1, Math.ceil(filteredUsers.length / USERS_PER_PAGE))
  const pagedUsers = filteredUsers.slice(userPage * USERS_PER_PAGE, (userPage + 1) * USERS_PER_PAGE)

  const filteredCampaigns = useMemo(() => {
    const q = campaignSearch.trim().toLowerCase()
    if (!q) return campaigns
    return campaigns.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.owner_name || '').toLowerCase().includes(q) ||
        String(c.owner_id).includes(q),
    )
  }, [campaigns, campaignSearch])

  const filteredTickets = useMemo(() => {
    const q = ticketSearch.trim().toLowerCase()
    if (!q) return tickets
    return tickets.filter(
      (t) =>
        String(t.id).includes(q) ||
        t.subject.toLowerCase().includes(q) ||
        (t.user_name || '').toLowerCase().includes(q) ||
        (t.user_email || '').toLowerCase().includes(q),
    )
  }, [tickets, ticketSearch])

  // Campaigns/tickets filtered for a specific user in the detail modal
  const userDetailCampaigns = useMemo(() => {
    if (!userDetailUser) return []
    return campaigns.filter(c => c.owner_id === userDetailUser.id)
  }, [campaigns, userDetailUser])

  const userDetailTickets = useMemo(() => {
    if (!userDetailUser) return []
    return tickets.filter(t => t.user_id === userDetailUser.id)
  }, [tickets, userDetailUser])

  // ── Actions ──────────────────────────────────────────────────────────────────

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

  const deleteCampaign = async (campaignId: string, campaignName: string) => {
    if (!window.confirm(`Permanently delete campaign "${campaignName}"? This cannot be undone.`)) return
    try {
      const res = await apiFetch(`/admin/campaigns/${campaignId}`, { method: 'DELETE' })
      if (!res.ok) {
        const d = await res.json().catch(() => null)
        alert(d?.detail || `Error ${res.status}`)
        return
      }
      setCampaigns((prev) => prev.filter((c) => c.id !== campaignId))
    } catch {
      alert('Network error deleting campaign.')
    }
  }

  const openDrawer = (user: AdminUser) => setDrawerUser(user)
  const closeDrawer = () => setDrawerUser(null)

  const openUserDetail = (user: AdminUser, mode: 'tickets' | 'campaigns') => {
    setUserDetailUser(user)
    setUserDetailModal(mode)
    closeDrawer()
    // Ensure data is loaded
    if (mode === 'tickets' && tickets.length === 0) loadTickets()
    if (mode === 'campaigns' && campaigns.length === 0) loadCampaigns()
  }

  const closeUserDetail = () => {
    setUserDetailModal(null)
    setUserDetailUser(null)
  }

  const deleteUserDetailCampaign = (campaignId: string, campaignName: string) => {
    deleteCampaign(campaignId, campaignName)
    closeUserDetail()
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <section className="admin-panel-root stack" style={{ gap: 16 }}>
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

      {/* ── Site Statistics ── */}
      <div className="admin-section">
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

      {/* ── Two-column grid: User Management + Campaign Management ── */}
      <div className="admin-two-col-grid">
        {/* ── User Management ── */}
        <div className="admin-section" style={{ margin: 0 }}>
          <div className="section-title">User Management</div>
          <div className="row-wrap" style={{ gap: 8, margin: '12px 0' }}>
            <input
              className="input"
              type="search"
              placeholder="Search by name, username, or email…"
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              style={{ flex: 1, minWidth: 160 }}
            />
            {users.length > 0 && (
              <span className="muted" style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
                {userSearch ? `${filteredUsers.length} of ` : ''}{users.length} user{users.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
          {usersLoading && <div className="loading-text">Loading…</div>}
          {usersError && <div className="error-text">{usersError}</div>}

          {!usersLoading && !usersError && (
            <>
              <div className="admin-scroll-box">
                {filteredUsers.length === 0 ? (
                  <div className="empty-text" style={{ padding: '20px 0' }}>
                    {userSearch ? 'No users match your search.' : 'No users found.'}
                  </div>
                ) : (
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>Name / Username</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedUsers.map((u) => (
                        <tr key={u.id}>
                          <td>
                            <div style={{ fontWeight: 600, fontSize: 13 }}>{u.name || u.username || '—'}</div>
                            {u.username && u.name && <div className="muted" style={{ fontSize: 11 }}>@{u.username}</div>}
                          </td>
                          <td style={{ fontSize: 12 }}>{u.email || '—'}</td>
                          <td>
                            {u.admin
                              ? <span className="badge badge-active">Admin</span>
                              : <span className="badge badge-muted">{u.verified ? 'Player' : 'Unverified'}</span>}
                          </td>
                          <td className="admin-actions-cell">
                            <button
                              className="btn btn-sm btn-secondary"
                              type="button"
                              onClick={() => openDrawer(u)}
                            >
                              Actions ▾
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              {/* Pagination controls */}
              {userTotalPages > 1 && (
                <div className="admin-pagination">
                  <button
                    className="btn btn-sm btn-secondary"
                    type="button"
                    disabled={userPage === 0}
                    onClick={() => setUserPage((p) => Math.max(0, p - 1))}
                  >
                    ← Prev
                  </button>
                  <span className="muted" style={{ fontSize: 13 }}>
                    Page {userPage + 1} of {userTotalPages}
                  </span>
                  <button
                    className="btn btn-sm btn-secondary"
                    type="button"
                    disabled={userPage >= userTotalPages - 1}
                    onClick={() => setUserPage((p) => Math.min(userTotalPages - 1, p + 1))}
                  >
                    Next →
                  </button>
                </div>
              )}
            </>
          )}

          {/* ── Bans / Suspensions ── */}
          <div style={{ marginTop: 28 }}>
            <div className="section-title">Email Bans &amp; Suspensions</div>
            <form className="stack" style={{ gap: 10, marginBottom: 16, marginTop: 12 }} onSubmit={submitBan}>
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
              <div className="admin-scroll-box">
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
              </div>
            )}
          </div>
        </div>

        {/* ── Campaign Management ── */}
        <div className="admin-section" style={{ margin: 0 }}>
          <div className="section-title">Campaign Management</div>
          <div className="row-wrap" style={{ gap: 8, margin: '12px 0' }}>
            <input
              className="input"
              type="search"
              placeholder="Search by campaign name or owner…"
              value={campaignSearch}
              onChange={(e) => setCampaignSearch(e.target.value)}
              style={{ flex: 1, minWidth: 160 }}
            />
            {campaignSearch && (
              <span className="muted" style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
                {filteredCampaigns.length} of {campaigns.length} shown
              </span>
            )}
          </div>
          {campaignsLoading && <div className="loading-text">Loading…</div>}
          {campaignsError && <div className="error-text">{campaignsError}</div>}
          {!campaignsLoading && !campaignsError && (
            <div className="admin-scroll-box">
              {filteredCampaigns.length === 0 ? (
                <div className="empty-text" style={{ padding: '20px 0' }}>
                  {campaignSearch ? 'No campaigns match your search.' : 'No campaigns found.'}
                </div>
              ) : (
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Owner</th>
                      <th>Created</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCampaigns.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <div style={{ fontWeight: 600, fontSize: 13 }}>{c.name}</div>
                          <div className="muted" style={{ fontSize: 11 }}>{c.id}</div>
                        </td>
                        <td>{c.owner_name || `User #${c.owner_id}`}</td>
                        <td>{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</td>
                        <td>{c.archived ? <span className="badge badge-muted">Archived</span> : <span className="badge badge-active">Active</span>}</td>
                        <td className="admin-actions-cell">
                          {!c.archived && (
                            <button className="btn btn-sm btn-secondary" type="button" onClick={() => archiveCampaign(c.id)}>Archive</button>
                          )}
                          <button className="btn btn-sm btn-danger" type="button" onClick={() => deleteCampaign(c.id, c.name)}>Delete</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Support Tickets ── */}
      <div className="admin-section">
        <div className="section-title">Support Tickets</div>
        <div className="row-wrap" style={{ gap: 8, margin: '12px 0', flexWrap: 'wrap' }}>
          <input
            className="input"
            type="search"
            placeholder="Search by ticket #, user, or subject…"
            value={ticketSearch}
            onChange={(e) => setTicketSearch(e.target.value)}
            style={{ maxWidth: 300 }}
          />
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
            <option value="">All statuses</option>
            {TICKET_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button className="btn btn-sm btn-secondary" type="button" onClick={() => loadTickets(ticketStatusFilter || undefined)} disabled={ticketsLoading}>
            {ticketsLoading ? '…' : 'Refresh'}
          </button>
          {ticketSearch && (
            <span className="muted" style={{ fontSize: 13 }}>{filteredTickets.length} of {tickets.length} shown</span>
          )}
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
              {filteredTickets.map((t) => (
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
                      <td colSpan={6} className="admin-expanded-row">
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
              {filteredTickets.length === 0 && (
                <tr><td colSpan={6}><span className="empty-text">{ticketSearch ? 'No tickets match your search.' : 'No tickets found.'}</span></td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* ── User Actions Drawer ── */}
      {drawerUser && (
        <div className="admin-drawer-overlay" onClick={closeDrawer} role="presentation">
          <div
            className="admin-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={`Actions for ${drawerUser.name || drawerUser.email}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="admin-drawer-header">
              <div className="admin-drawer-title">
                <span style={{ fontSize: 13, color: 'var(--muted-text)' }}>Actions</span>
                <div style={{ fontWeight: 700, fontSize: 15, marginTop: 2 }}>
                  {drawerUser.name || drawerUser.username || drawerUser.email || `User #${drawerUser.id}`}
                </div>
                {drawerUser.email && drawerUser.name && (
                  <div style={{ fontSize: 12, color: 'var(--muted-text)' }}>{drawerUser.email}</div>
                )}
              </div>
              <button className="modal-close" type="button" onClick={closeDrawer} aria-label="Close">✕</button>
            </div>
            <div className="admin-drawer-body">
              <button
                className="admin-drawer-action"
                type="button"
                onClick={() => { openAction(drawerUser, 'warn'); closeDrawer() }}
              >
                <span className="admin-drawer-action-icon">⚠️</span>
                <div>
                  <div className="admin-drawer-action-label">Warn</div>
                  <div className="admin-drawer-action-desc">Send a warning message to this user</div>
                </div>
              </button>
              <button
                className="admin-drawer-action"
                type="button"
                onClick={() => { openAction(drawerUser, 'message'); closeDrawer() }}
              >
                <span className="admin-drawer-action-icon">✉️</span>
                <div>
                  <div className="admin-drawer-action-label">Message</div>
                  <div className="admin-drawer-action-desc">Send a direct admin notification</div>
                </div>
              </button>
              <button
                className="admin-drawer-action"
                type="button"
                onClick={() => { openAction(drawerUser, 'reset-password'); closeDrawer() }}
              >
                <span className="admin-drawer-action-icon">🔑</span>
                <div>
                  <div className="admin-drawer-action-label">Reset Password</div>
                  <div className="admin-drawer-action-desc">Set a new password for this user</div>
                </div>
              </button>
              <button
                className="admin-drawer-action"
                type="button"
                onClick={() => { openAction(drawerUser, 'impersonate'); closeDrawer() }}
              >
                <span className="admin-drawer-action-icon">👤</span>
                <div>
                  <div className="admin-drawer-action-label">Login As</div>
                  <div className="admin-drawer-action-desc">Impersonate this user's session</div>
                </div>
              </button>
              <div className="admin-drawer-divider" />
              <button
                className="admin-drawer-action"
                type="button"
                onClick={() => openUserDetail(drawerUser, 'tickets')}
              >
                <span className="admin-drawer-action-icon">🎫</span>
                <div>
                  <div className="admin-drawer-action-label">View Support Tickets</div>
                  <div className="admin-drawer-action-desc">See tickets submitted by this user</div>
                </div>
              </button>
              <button
                className="admin-drawer-action"
                type="button"
                onClick={() => openUserDetail(drawerUser, 'campaigns')}
              >
                <span className="admin-drawer-action-icon">⚔️</span>
                <div>
                  <div className="admin-drawer-action-label">View Campaigns</div>
                  <div className="admin-drawer-action-desc">See campaigns owned by this user</div>
                </div>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── User detail modal (tickets / campaigns for a specific user) ── */}
      {userDetailModal && userDetailUser && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-box" style={{ maxWidth: 680 }}>
            <div className="modal-header">
              <div className="modal-title">
                {userDetailModal === 'tickets'
                  ? `Support Tickets — ${userDetailUser.name || userDetailUser.email}`
                  : `Campaigns — ${userDetailUser.name || userDetailUser.email}`}
              </div>
              <button className="modal-close" type="button" onClick={closeUserDetail} aria-label="Close">✕</button>
            </div>
            <div className="modal-body" style={{ padding: 0 }}>
              {userDetailModal === 'tickets' && (
                <>
                  {userDetailTickets.length === 0 ? (
                    <div className="empty-text" style={{ padding: 20 }}>No support tickets found for this user.</div>
                  ) : (
                    <table className="admin-table">
                      <thead>
                        <tr><th>#</th><th>Subject</th><th>Status</th><th>Submitted</th></tr>
                      </thead>
                      <tbody>
                        {userDetailTickets.map(t => (
                          <tr key={t.id}>
                            <td>{t.id}</td>
                            <td>{t.subject}</td>
                            <td>
                              <span className={`badge ${t.status === 'open' ? 'badge-active' : 'badge-muted'}`}>{t.status}</span>
                            </td>
                            <td>{t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
              {userDetailModal === 'campaigns' && (
                <>
                  {userDetailCampaigns.length === 0 ? (
                    <div className="empty-text" style={{ padding: 20 }}>No campaigns found for this user.</div>
                  ) : (
                    <table className="admin-table">
                      <thead>
                        <tr><th>ID</th><th>Name</th><th>Created</th><th>Status</th><th>Actions</th></tr>
                      </thead>
                      <tbody>
                        {userDetailCampaigns.map(c => (
                          <tr key={c.id}>
                            <td><span className="admin-id-chip">{c.id.slice(0, 8)}</span></td>
                            <td>{c.name}</td>
                            <td>{c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}</td>
                            <td>{c.archived ? <span className="badge badge-muted">Archived</span> : <span className="badge badge-active">Active</span>}</td>
                            <td className="admin-actions-cell">
                              {!c.archived && (
                                <button className="btn btn-sm btn-secondary" type="button" onClick={() => archiveCampaign(c.id)}>Archive</button>
                              )}
                              <button className="btn btn-sm btn-danger" type="button" onClick={() => deleteUserDetailCampaign(c.id, c.name)}>Delete</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" type="button" onClick={closeUserDetail}>Close</button>
            </div>
          </div>
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
                <>
                  <div className="inline-alert inline-alert-error" style={{ fontSize: 13 }}>
                    ⚠️ You are about to reset the password for <strong>{selectedUser.name || selectedUser.email}</strong>. This action cannot be undone. The user will need to use the new password to log in.
                  </div>
                  <label className="field-label">
                    New password (min 8 characters)
                    <input className="input" type="text" value={actionInput} onChange={(e) => setActionInput(e.target.value)} placeholder="Enter new password…" />
                  </label>
                </>
              )}
              {actionModal === 'impersonate' && (
                <>
                  <div className="inline-alert inline-alert-error" style={{ fontSize: 13 }}>
                    ⚠️ You are about to log in as <strong>{selectedUser.name || selectedUser.email}</strong>. This will issue a 15-minute session token and replace your current admin session. You will need to log back in as yourself afterwards.
                  </div>
                  <div className="muted" style={{ fontSize: 13 }}>
                    Confirm you want to proceed with impersonation.
                  </div>
                </>
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
